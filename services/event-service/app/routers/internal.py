"""
Internal, service-to-service endpoints.

These are not exposed to the browser (the API gateway does not route
/internal/* publicly), and every request must carry a service token
(see eventsphere_common.service_auth). Booking Service is the only allowed
caller: it reads ticket-type pricing/availability during reservation, and
permanently adjusts inventory only after a payment is verified (decrement)
or a confirmed booking is refunded/cancelled (increment).
"""
from eventsphere_common.service_auth import require_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AvailabilityAdjustment, Event, TicketType
from ..schemas import AdjustAvailabilityRequest, TicketTypeOut

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_service("event", "booking"))])


@router.get("/ticket-types/{ticket_type_id}", response_model=TicketTypeOut)
def get_ticket_type(ticket_type_id: str, db: Session = Depends(get_db)):
    tt = db.get(TicketType, ticket_type_id)
    if not tt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket type not found")
    return tt


@router.get("/events/{event_id}/summary")
def get_event_summary(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return {"id": event.id, "title": event.title, "organizer_id": event.organizer_id, "status": event.status.value, "starts_at": event.starts_at.isoformat()}


@router.post("/ticket-types/{ticket_type_id}/decrement", response_model=TicketTypeOut)
def decrement_availability(ticket_type_id: str, payload: AdjustAvailabilityRequest, db: Session = Depends(get_db)):
    existing = db.get(AvailabilityAdjustment, payload.idempotency_key)
    tt = db.get(TicketType, ticket_type_id)
    if not tt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket type not found")
    if existing:
        return tt  # already applied - return current state, no double decrement

    if tt.quantity_available < payload.quantity:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not enough tickets available")

    tt.quantity_available -= payload.quantity
    db.add(AvailabilityAdjustment(idempotency_key=payload.idempotency_key, ticket_type_id=ticket_type_id, quantity=-payload.quantity))
    db.commit()
    db.refresh(tt)
    return tt


@router.post("/ticket-types/{ticket_type_id}/increment", response_model=TicketTypeOut)
def increment_availability(ticket_type_id: str, payload: AdjustAvailabilityRequest, db: Session = Depends(get_db)):
    existing = db.get(AvailabilityAdjustment, payload.idempotency_key)
    tt = db.get(TicketType, ticket_type_id)
    if not tt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket type not found")
    if existing:
        return tt

    tt.quantity_available = min(tt.quantity_total, tt.quantity_available + payload.quantity)
    db.add(AvailabilityAdjustment(idempotency_key=payload.idempotency_key, ticket_type_id=ticket_type_id, quantity=payload.quantity))
    db.commit()
    db.refresh(tt)
    return tt
