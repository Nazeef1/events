import logging

from eventsphere_common.bus import consume_forever
from eventsphere_common.events import EventEnvelope

from .clients import booking_service_client
from .database import SessionLocal
from .models import ProcessedEvent
from .refund_logic import process_refund_for_booking

logger = logging.getLogger("eventsphere.refund.worker")


def handle_event(envelope: EventEnvelope) -> None:
    db = SessionLocal()
    try:
        if db.get(ProcessedEvent, envelope.event_id):
            return

        if envelope.event_type == "RefundRequested":
            booking_id = envelope.data["booking_id"]
            process_refund_for_booking(db, booking_id, reason="Attendee-requested cancellation")

        elif envelope.event_type == "EventCancelled":
            event_id = envelope.data["event_id"]
            affected = booking_service_client.get_bookings_by_event(event_id, booking_status="CONFIRMED")
            for booking in affected:
                try:
                    booking_service_client.mark_refund_pending(booking["id"])
                    process_refund_for_booking(db, booking["id"], reason=f"Event '{envelope.data.get('title', event_id)}' was cancelled by the organizer")
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to refund booking %s for cancelled event %s", booking["id"], event_id)

        db.add(ProcessedEvent(event_id=envelope.event_id))
        db.commit()
    finally:
        db.close()


def run_worker() -> None:
    consume_forever(
        queue_name="refund-service.events",
        routing_keys=["eventsphere.refundrequested", "eventsphere.eventcancelled"],
        handler=handle_event,
    )
