import logging

from eventsphere_common.bus import publish_event
from sqlalchemy import select
from sqlalchemy.orm import Session

from .clients import booking_service_client, payment_service_client
from .config import settings
from .models import Refund, RefundStatus

logger = logging.getLogger("eventsphere.refund")


def _publish_safe(event_type: str, data: dict) -> None:
    try:
        publish_event(event_type, settings.service_name, data)
    except Exception:  # noqa: BLE001
        pass


def process_refund_for_booking(db: Session, booking_id: str, reason: str = "Attendee-requested cancellation") -> Refund:
    """
    Idempotent core refund workflow:
      existing Refund row? -> return as-is (no duplicate Razorpay call)
      else: look up the payment, call payment-service to issue the
      Razorpay TEST MODE refund, record it, tell booking-service the
      booking is REFUNDED, publish RefundProcessed.
    """
    existing = db.execute(select(Refund).where(Refund.booking_id == booking_id)).scalar_one_or_none()
    if existing and existing.status == RefundStatus.COMPLETED:
        # The money already moved; finish any booking update a prior attempt missed.
        booking_service_client.mark_refunded(booking_id)
        return existing

    payment = payment_service_client.get_payment_for_booking(booking_id)
    if not payment:
        raise ValueError(f"No payment found for booking {booking_id}; cannot refund")

    refund = existing or Refund(
        booking_id=booking_id, payment_id=payment["id"], user_id=payment["user_id"],
        amount=payment["amount"], reason=reason, status=RefundStatus.PENDING,
    )
    if not existing:
        db.add(refund)
        db.commit()
        db.refresh(refund)

    try:
        result = payment_service_client.process_refund(payment["id"])
    except Exception as exc:  # noqa: BLE001
        refund.status = RefundStatus.FAILED
        refund.failure_reason = str(exc)
        db.commit()
        logger.exception("Refund failed for booking %s", booking_id)
        raise

    refund.status = RefundStatus.COMPLETED
    refund.failure_reason = None
    refund.razorpay_refund_id = result.get("razorpay_refund_id") or refund.razorpay_refund_id
    db.commit()
    db.refresh(refund)

    booking_service_client.mark_refunded(booking_id)

    _publish_safe("RefundProcessed", {
        "refund_id": refund.id, "booking_id": booking_id, "user_id": refund.user_id, "amount": float(refund.amount),
        "event_id": payment.get("event_id"),
    })
    return refund
