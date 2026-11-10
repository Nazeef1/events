import logging

from eventsphere_common.service_auth import require_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import razorpay_client
from ..database import get_db
from ..models import Payment, PaymentStatus
from ..schemas import PaymentOut

logger = logging.getLogger("eventsphere.payment.internal")
# Only Refund Service may use these (zero trust: see eventsphere_common.service_auth).
router = APIRouter(prefix="/internal/payments", tags=["internal"], dependencies=[Depends(require_service("payment", "refund"))])


@router.get("/booking/{booking_id}", response_model=PaymentOut)
def get_payment_for_booking(booking_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import select
    payment = db.execute(select(Payment).where(Payment.booking_id == booking_id)).scalar_one_or_none()
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


@router.post("/{payment_id}/mark-refunded", response_model=PaymentOut)
def mark_refunded(payment_id: str, db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if payment.status != PaymentStatus.SUCCEEDED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Payment is {payment.status.value}, expected SUCCEEDED")
    payment.status = PaymentStatus.REFUNDED
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/{payment_id}/process-refund")
def process_refund(payment_id: str, db: Session = Depends(get_db)):
    """
    Called by Refund Service. Issues a real Razorpay TEST MODE refund
    against the original captured payment, then marks the payment
    REFUNDED. Idempotent: replays against an already-refunded payment
    are a no-op success.
    """
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if payment.status == PaymentStatus.REFUNDED:
        return {"status": "already_refunded", "razorpay_refund_id": None}
    if payment.status != PaymentStatus.SUCCEEDED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Payment is {payment.status.value}, cannot refund")

    try:
        refund = razorpay_client.create_refund(
            razorpay_payment_id=payment.razorpay_payment_id,
            amount=float(payment.amount),
            notes={"booking_id": payment.booking_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Razorpay refund failed for payment %s", payment_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Razorpay refund failed") from exc

    payment.status = PaymentStatus.REFUNDED
    db.commit()
    return {"status": "refunded", "razorpay_refund_id": refund.get("id")}
