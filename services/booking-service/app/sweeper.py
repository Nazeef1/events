import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .database import SessionLocal
from .models import Booking, BookingStatus
from .redis_holds import ticket_hold_store
from eventsphere_common.bus import publish_event
from .config import settings

logger = logging.getLogger("eventsphere.booking.sweeper")


def sweep_expired_reservations() -> int:
    db = SessionLocal()
    count = 0
    try:
        now = datetime.now(timezone.utc)
        stmt = select(Booking).where(Booking.status == BookingStatus.PENDING_PAYMENT, Booking.expires_at < now)
        expired = db.execute(stmt).scalars().all()
        for booking in expired:
            booking.status = BookingStatus.EXPIRED
            for item in booking.items:
                ticket_hold_store.release(item.ticket_type_id, booking.reservation_id)
            try:
                publish_event("BookingExpired", settings.service_name, {"booking_id": booking.id, "user_id": booking.user_id, "event_id": booking.event_id})
            except Exception:  # noqa: BLE001
                pass
            count += 1
        db.commit()
    finally:
        db.close()
    return count


async def sweeper_loop(interval_seconds: int = 30) -> None:
    while True:
        try:
            swept = sweep_expired_reservations()
            if swept:
                logger.info("Expired %s reservation(s)", swept)
        except Exception:  # noqa: BLE001
            logger.exception("Reservation sweep failed")
        await asyncio.sleep(interval_seconds)
