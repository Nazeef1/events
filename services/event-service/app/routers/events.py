import re
import uuid
from datetime import datetime, timezone

from eventsphere_common.auth_deps import CurrentUser, get_optional_user, require_roles
from eventsphere_common.bus import publish_event
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..models import Event, EventCategory, EventStatus, TicketType
from ..schemas import EventCreate, EventOut, EventSummaryOut, EventUpdate, PaginatedEvents

router = APIRouter(prefix="/events", tags=["events"])


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _publish_safe(event_type: str, data: dict) -> None:
    try:
        publish_event(event_type, settings.service_name, data)
    except Exception:  # noqa: BLE001
        # Event publishing must never fail the primary request in this demo-scale system.
        pass


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, user: CurrentUser = Depends(require_roles("ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    event = Event(
        organizer_id=user.id,
        title=payload.title,
        slug=_slugify(payload.title),
        description=payload.description,
        category=payload.category,
        status=EventStatus.DRAFT,
        cover_image_url=payload.cover_image_url,
        venue_name=payload.venue_name,
        venue_address=payload.venue_address,
        city=payload.city,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    for tt in payload.ticket_types:
        event.ticket_types.append(
            TicketType(
                name=tt.name,
                description=tt.description,
                price=tt.price,
                quantity_total=tt.quantity_total,
                quantity_available=tt.quantity_total,
                sale_starts_at=tt.sale_starts_at,
                sale_ends_at=tt.sale_ends_at,
            )
        )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("", response_model=PaginatedEvents)
def list_events(
    q: str | None = None,
    category: EventCategory | None = None,
    city: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    mine: bool = False,
    admin_all: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser | None = Depends(get_optional_user),
):
    stmt = select(Event).options(selectinload(Event.ticket_types))

    if admin_all:
        if not user or user.role != "ADMIN":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
        # no status filter - admins moderate events in any state
    elif mine:
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required to view your events")
        stmt = stmt.where(Event.organizer_id == user.id)
    else:
        stmt = stmt.where(Event.status == EventStatus.PUBLISHED, Event.ends_at >= datetime.now(timezone.utc))

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Event.title).like(like), func.lower(Event.description).like(like), func.lower(Event.city).like(like)))
    if category:
        stmt = stmt.where(Event.category == category)
    if city:
        stmt = stmt.where(func.lower(Event.city) == city.lower())
    if date_from:
        stmt = stmt.where(Event.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Event.starts_at <= date_to)

    stmt = stmt.order_by(Event.starts_at.asc())

    all_events = db.execute(stmt).scalars().unique().all()

    summaries = []
    for e in all_events:
        prices = [float(t.price) for t in e.ticket_types] or [0]
        lo, hi = min(prices), max(prices)
        if min_price is not None and hi < min_price:
            continue
        if max_price is not None and lo > max_price:
            continue
        summaries.append(
            EventSummaryOut(
                id=e.id, organizer_id=e.organizer_id, title=e.title, slug=e.slug, category=e.category,
                status=e.status, cover_image_url=e.cover_image_url, city=e.city, starts_at=e.starts_at,
                min_price=lo, max_price=hi,
            )
        )

    total = len(summaries)
    start = (page - 1) * page_size
    page_items = summaries[start:start + page_size]
    return PaginatedEvents(items=page_items, total=total, page=page, page_size=page_size)


def _get_owned_event(event_id: str, user: CurrentUser, db: Session) -> Event:
    event = db.get(Event, event_id, options=[selectinload(Event.ticket_types)])
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if event.organizer_id != user.id and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this event")
    return event


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: str, db: Session = Depends(get_db), user: CurrentUser | None = Depends(get_optional_user)):
    event = db.get(Event, event_id, options=[selectinload(Event.ticket_types)])
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    is_owner = user and (user.id == event.organizer_id or user.role == "ADMIN")
    if event.status != EventStatus.PUBLISHED and not is_owner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    _publish_safe("EventViewed", {"event_id": event.id, "organizer_id": event.organizer_id, "viewer_id": user.id if user else None})
    return event


@router.patch("/{event_id}", response_model=EventOut)
def update_event(event_id: str, payload: EventUpdate, user: CurrentUser = Depends(require_roles("ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    event = _get_owned_event(event_id, user, db)
    if event.status == EventStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancelled events cannot be edited")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("starts_at", event.starts_at) >= changes.get("ends_at", event.ends_at):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The event must end after it starts")

    for field, value in changes.items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    _publish_safe("EventUpdated", {"event_id": event.id})
    return event


@router.post("/{event_id}/ticket-types", response_model=EventOut)
def add_ticket_type(event_id: str, payload: dict, user: CurrentUser = Depends(require_roles("ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    from ..schemas import TicketTypeCreate

    tt_payload = TicketTypeCreate.model_validate(payload)
    event = _get_owned_event(event_id, user, db)
    if event.status == EventStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancelled events cannot be edited")
    event.ticket_types.append(
        TicketType(
            name=tt_payload.name, description=tt_payload.description, price=tt_payload.price,
            quantity_total=tt_payload.quantity_total, quantity_available=tt_payload.quantity_total,
            sale_starts_at=tt_payload.sale_starts_at, sale_ends_at=tt_payload.sale_ends_at,
        )
    )
    db.commit()
    db.refresh(event)
    return event


@router.post("/{event_id}/publish", response_model=EventOut)
def publish_event_endpoint(event_id: str, user: CurrentUser = Depends(require_roles("ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    event = _get_owned_event(event_id, user, db)
    if event.status != EventStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot publish an event in status {event.status.value}")
    if not event.ticket_types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add at least one ticket type before publishing")

    event.status = EventStatus.PUBLISHED
    db.commit()
    db.refresh(event)
    _publish_safe("EventPublished", {"event_id": event.id, "organizer_id": event.organizer_id, "title": event.title})
    return event


@router.post("/{event_id}/cancel", response_model=EventOut)
def cancel_event(event_id: str, user: CurrentUser = Depends(require_roles("ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    event = _get_owned_event(event_id, user, db)
    if event.status == EventStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is already cancelled")

    event.status = EventStatus.CANCELLED
    db.commit()
    db.refresh(event)
    _publish_safe("EventCancelled", {"event_id": event.id, "organizer_id": event.organizer_id, "title": event.title})
    return event
