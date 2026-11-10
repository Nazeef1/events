import uuid
from datetime import datetime, timedelta, timezone

from eventsphere_common.auth_deps import CurrentUser, require_roles
from eventsphere_common.bus import publish_event
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..event_client import event_service_client
from ..models import Booking, BookingItem, BookingStatus, IdempotentRequest
from ..redis_holds import ticket_hold_store
from ..schemas import BookingOut, ReserveRequest
from .internal import confirm_booking, restock_booking

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _publish_safe(event_type: str, data: dict) -> None:
    try:
        publish_event(event_type, settings.service_name, data)
    except Exception:  # noqa: BLE001
        pass


@router.post("/reserve", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def reserve_tickets(
    payload: ReserveRequest,
    user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        existing = db.get(IdempotentRequest, idempotency_key)
        if existing:
            booking = db.get(Booking, existing.booking_id, options=[selectinload(Booking.items)])
            if booking and booking.user_id == user.id:
                return booking

    ticket_ids = [item.ticket_type_id for item in payload.items]
    if len(ticket_ids) != len(set(ticket_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each ticket type can only appear once in a reservation")

    event_summary = event_service_client.get_event_summary(payload.event_id)
    if not event_summary:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if event_summary["status"] != "PUBLISHED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This event is not open for booking")

    now = datetime.now(timezone.utc)
    if event_summary.get("starts_at") and _parse_utc(event_summary["starts_at"]) <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has already started")

    reservation_id = str(uuid.uuid4())
    reserved_types: list[str] = []
    items: list[BookingItem] = []
    total = 0

    try:
        for item in payload.items:
            tt = event_service_client.get_ticket_type(item.ticket_type_id)
            if not tt:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ticket type {item.ticket_type_id} not found")
            if tt.get("event_id", payload.event_id) != payload.event_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{tt['name']}' does not belong to this event")
            if tt.get("sale_starts_at") and now < _parse_utc(tt["sale_starts_at"]):
                raise HTTPException(status.HTTP_409_CONFLICT, f"'{tt['name']}' is not on sale yet")
            if tt.get("sale_ends_at") and now > _parse_utc(tt["sale_ends_at"]):
                raise HTTPException(status.HTTP_409_CONFLICT, f"Sales for '{tt['name']}' have ended")

            success, held = ticket_hold_store.try_reserve(
                ticket_type_id=item.ticket_type_id,
                reservation_id=reservation_id,
                quantity=item.quantity,
                available_capacity=tt["quantity_available"],
            )
            if not success:
                remaining = max(tt["quantity_available"] - held, 0)
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"Only {remaining} '{tt['name']}' ticket(s) remaining" if remaining else f"'{tt['name']}' is sold out",
                )
            reserved_types.append(item.ticket_type_id)

            unit_price = float(tt["price"])
            total += unit_price * item.quantity
            items.append(
                BookingItem(
                    ticket_type_id=item.ticket_type_id,
                    ticket_type_name=tt["name"],
                    unit_price=unit_price,
                    quantity=item.quantity,
                )
            )
    except HTTPException:
        for tt_id in reserved_types:
            ticket_hold_store.release(tt_id, reservation_id)
        raise

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.reservation_ttl_seconds)
    booking_id = str(uuid.uuid4())
    booking = Booking(
        id=booking_id,
        reservation_id=reservation_id,
        user_id=user.id,
        event_id=payload.event_id,
        organizer_id=event_summary["organizer_id"],
        status=BookingStatus.PENDING_PAYMENT,
        total_amount=total,
        expires_at=expires_at,
        items=items,
    )
    db.add(booking)
    if idempotency_key:
        db.add(IdempotentRequest(idempotency_key=idempotency_key, booking_id=booking_id))
    db.commit()
    db.refresh(booking)

    _publish_safe("BookingCreated", {
        "booking_id": booking.id, "user_id": user.id, "event_id": payload.event_id,
        "amount": float(total), "ticket_ids": [i.ticket_type_id for i in items],
    })
    if total == 0:
        # Nothing to charge (and Razorpay rejects zero-value orders).
        return confirm_booking(booking.id, payment_id="free", db=db)
    return booking


@router.get("", response_model=list[BookingOut])
def list_my_bookings(user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    stmt = select(Booking).options(selectinload(Booking.items)).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())
    return db.execute(stmt).scalars().unique().all()


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: str, user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id, options=[selectinload(Booking.items)])
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.user_id != user.id and booking.organizer_id != user.id and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot view this booking")
    return booking


@router.get("/event/{event_id}", response_model=list[BookingOut])
def list_bookings_for_event(event_id: str, user: CurrentUser = Depends(require_roles("ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    """Organizer-facing: attendees & bookings for one of the organizer's own events."""
    stmt = select(Booking).options(selectinload(Booking.items)).where(Booking.event_id == event_id).order_by(Booking.created_at.desc())
    results = db.execute(stmt).scalars().unique().all()
    if results and results[0].organizer_id != user.id and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot view bookings for another organizer's event")
    return results


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: str, user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id, options=[selectinload(Booking.items)])
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot cancel this booking")

    if booking.status == BookingStatus.PENDING_PAYMENT:
        for item in booking.items:
            ticket_hold_store.release(item.ticket_type_id, booking.reservation_id)
        booking.status = BookingStatus.CANCELLED
    elif booking.status == BookingStatus.CONFIRMED and float(booking.total_amount) == 0:
        restock_booking(booking)
        booking.status = BookingStatus.CANCELLED
    elif booking.status == BookingStatus.CONFIRMED:
        booking.status = BookingStatus.REFUND_PENDING
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booking in status {booking.status.value} cannot be cancelled")

    db.commit()
    db.refresh(booking)
    # Published only after commit: the consumers read this state back.
    if booking.status == BookingStatus.REFUND_PENDING:
        _publish_safe("RefundRequested", {
            "booking_id": booking.id, "user_id": booking.user_id, "amount": float(booking.total_amount),
        })
    if booking.status == BookingStatus.CANCELLED:
        _publish_safe("BookingCancelled", {"booking_id": booking.id, "user_id": booking.user_id, "event_id": booking.event_id})
    return booking
