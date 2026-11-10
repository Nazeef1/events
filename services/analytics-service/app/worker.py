import logging

from eventsphere_common.bus import consume_forever
from eventsphere_common.events import EventEnvelope
from sqlalchemy import select

from .database import SessionLocal
from .models import EventStats, ProcessedEvent

logger = logging.getLogger("eventsphere.analytics.worker")


def _get_or_create_stats(db, event_id: str, organizer_id: str = "") -> EventStats:
    stats = db.get(EventStats, event_id)
    if not stats:
        stats = EventStats(event_id=event_id, organizer_id=organizer_id, views=0, bookings_created=0, bookings_confirmed=0, bookings_cancelled=0, tickets_sold=0, revenue=0, refunds_count=0, refunds_amount=0, attendance_count=0)
        db.add(stats)
        db.flush()
    if organizer_id and not stats.organizer_id:
        stats.organizer_id = organizer_id
    return stats


def handle_event(envelope: EventEnvelope) -> None:
    db = SessionLocal()
    try:
        if db.get(ProcessedEvent, envelope.event_id):
            return

        data = envelope.data
        event_id = data.get("event_id")

        if envelope.event_type == "EventViewed" and event_id:
            stats = _get_or_create_stats(db, event_id, data.get("organizer_id", ""))
            stats.views += 1

        elif envelope.event_type == "BookingCreated" and event_id:
            stats = _get_or_create_stats(db, event_id)
            stats.bookings_created += 1

        elif envelope.event_type == "BookingConfirmed" and event_id:
            stats = _get_or_create_stats(db, event_id, data.get("organizer_id", ""))
            stats.bookings_confirmed += 1
            stats.tickets_sold += int(data.get("ticket_count", 1))

        elif envelope.event_type in ("BookingCancelled", "BookingExpired") and event_id:
            stats = _get_or_create_stats(db, event_id)
            stats.bookings_cancelled += 1

        elif envelope.event_type == "PaymentSucceeded" and event_id:
            stats = _get_or_create_stats(db, event_id, data.get("organizer_id", ""))
            stats.revenue = float(stats.revenue) + float(data.get("amount", 0))

        elif envelope.event_type == "RefundProcessed" and event_id:
            stats = _get_or_create_stats(db, event_id)
            stats.refunds_count += 1
            stats.refunds_amount = float(stats.refunds_amount) + float(data.get("amount", 0))

        elif envelope.event_type == "AttendanceRecorded" and event_id:
            stats = _get_or_create_stats(db, event_id)
            stats.attendance_count += 1

        db.add(ProcessedEvent(event_id=envelope.event_id))
        db.commit()
    finally:
        db.close()


def run_worker() -> None:
    consume_forever(
        queue_name="analytics-service.events",
        routing_keys=["eventsphere.#"],
        handler=handle_event,
    )
