import httpx
from eventsphere_common.bus import publish_event
from eventsphere_common.service_auth import require_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..event_client import event_service_client
from ..models import Booking, BookingStatus
from ..redis_holds import ticket_hold_store
from ..schemas import BookingOut

router = APIRouter(prefix="/internal/bookings", tags=["internal"])

# Who may call each internal route (zero trust: least privilege per route).
from_payment = [Depends(require_service("booking", "payment"))]
from_refund = [Depends(require_service("booking", "refund"))]
no_service = [Depends(require_service("booking"))]  # kept for tooling; no service calls these today


def _publish_safe(event_type: str, data: dict) -> None:
    try:
        publish_event(event_type, settings.service_name, data)
    except Exception:  # noqa: BLE001
        pass


def restock_booking(booking: Booking) -> None:
    """Returns a confirmed booking's tickets to sale. Idempotent per booking item."""
    for item in booking.items:
        event_service_client.increment_availability(
            ticket_type_id=item.ticket_type_id,
            quantity=item.quantity,
            idempotency_key=f"restock:{booking.id}:{item.id}",
        )


@router.post("/{booking_id}/confirm", response_model=BookingOut, dependencies=from_payment)
def confirm_booking(booking_id: str, payment_id: str, db: Session = Depends(get_db)):
    """Called by Payment Service after a Razorpay signature has been verified."""
    booking = db.get(Booking, booking_id, options=[selectinload(Booking.items)])
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    if booking.status == BookingStatus.CONFIRMED:
        return booking  # idempotent: already confirmed by an earlier webhook/callback

    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booking is {booking.status.value}, cannot confirm")

    summary = event_service_client.get_event_summary(booking.event_id)
    if summary and summary["status"] == "CANCELLED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has been cancelled")

    decremented = []
    try:
        for item in booking.items:
            event_service_client.decrement_availability(
                ticket_type_id=item.ticket_type_id,
                quantity=item.quantity,
                idempotency_key=f"confirm:{booking.id}:{item.id}",
            )
            decremented.append(item)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != status.HTTP_409_CONFLICT:
            raise
        for item in decremented:
            event_service_client.increment_availability(item.ticket_type_id, item.quantity, f"rollback:{booking.id}:{item.id}")
        raise HTTPException(status.HTTP_409_CONFLICT, "These tickets are no longer available") from exc

    for item in booking.items:
        ticket_hold_store.release(item.ticket_type_id, booking.reservation_id)

    booking.status = BookingStatus.CONFIRMED
    db.commit()
    db.refresh(booking)

    _publish_safe("BookingConfirmed", {
        "booking_id": booking.id, "user_id": booking.user_id, "event_id": booking.event_id,
        "organizer_id": booking.organizer_id, "amount": float(booking.total_amount), "payment_id": payment_id,
        "ticket_count": sum(i.quantity for i in booking.items),
    })
    return booking


@router.post("/{booking_id}/mark-expired", response_model=BookingOut, dependencies=no_service)
def mark_expired(booking_id: str, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id, options=[selectinload(Booking.items)])
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status != BookingStatus.PENDING_PAYMENT:
        return booking
    booking.status = BookingStatus.EXPIRED
    db.commit()
    db.refresh(booking)
    _publish_safe("BookingExpired", {"booking_id": booking.id, "user_id": booking.user_id, "event_id": booking.event_id})
    return booking


@router.get("/by-event/{event_id}", response_model=list[BookingOut], dependencies=from_refund)
def bookings_by_event(event_id: str, booking_status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Booking).options(selectinload(Booking.items)).where(Booking.event_id == event_id)
    if booking_status:
        stmt = stmt.where(Booking.status == booking_status)
    return db.execute(stmt).scalars().unique().all()


@router.get("/organizer/{organizer_id}", response_model=list[BookingOut], dependencies=no_service)
def bookings_by_organizer(organizer_id: str, db: Session = Depends(get_db)):
    stmt = select(Booking).options(selectinload(Booking.items)).where(Booking.organizer_id == organizer_id).order_by(Booking.created_at.desc())
    return db.execute(stmt).scalars().unique().all()


@router.post("/{booking_id}/mark-refund-pending", response_model=BookingOut, dependencies=from_refund)
def mark_refund_pending(booking_id: str, db: Session = Depends(get_db)):
    """Used when an organizer cancels an entire event: refund-service bulk-flags affected bookings."""
    booking = db.get(Booking, booking_id, options=[selectinload(Booking.items)])
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        return booking
    booking.status = BookingStatus.REFUND_PENDING
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/mark-refunded", response_model=BookingOut, dependencies=from_refund)
def mark_refunded(booking_id: str, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id, options=[selectinload(Booking.items)])
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status == BookingStatus.REFUNDED:
        return booking  # idempotent: refund-service may retry after a partial failure
    if booking.status != BookingStatus.REFUND_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booking is {booking.status.value}, expected REFUND_PENDING")
    restock_booking(booking)
    booking.status = BookingStatus.REFUNDED
    db.commit()
    db.refresh(booking)
    return booking
