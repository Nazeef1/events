import logging
import uuid
from datetime import datetime, timezone

import httpx
from eventsphere_common.auth_deps import CurrentUser, get_current_user, require_roles
from eventsphere_common.bus import publish_event
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import razorpay_client
from ..booking_client import booking_service_client
from ..config import settings
from ..database import get_db
from ..models import Payment, PaymentStatus
from ..schemas import CreateOrderRequest, CreateOrderResponse, MockPayRequest, PaymentOut, VerifyPaymentRequest

logger = logging.getLogger("eventsphere.payment")
router = APIRouter(prefix="/payments", tags=["payments"])


def _publish_safe(event_type: str, data: dict) -> None:
    try:
        publish_event(event_type, settings.service_name, data)
    except Exception:  # noqa: BLE001
        pass


class BookingNoLongerAvailable(Exception):
    """The money was captured but the booking could not be honoured; it has been refunded."""


def _confirm_booking_or_refund(db: Session, payment: Payment) -> None:
    """
    A customer can finish paying just after their hold lapsed or the event was
    cancelled. Booking Service answers 409 then, and keeping the money without
    issuing tickets is never right, so return it automatically.
    """
    try:
        booking_service_client.confirm_booking(payment.booking_id, payment.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != status.HTTP_409_CONFLICT:
            raise
        razorpay_client.create_refund(payment.razorpay_payment_id, float(payment.amount), {"booking_id": payment.booking_id})
        payment.status = PaymentStatus.REFUNDED
        payment.failure_reason = "Booking no longer available; refunded automatically"
        db.commit()
        raise BookingNoLongerAvailable from exc


@router.post("/order", response_model=CreateOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: CreateOrderRequest,
    request: Request,
    user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")),
    db: Session = Depends(get_db),
):
    auth_header = {"Authorization": request.headers.get("authorization", "")}
    booking = booking_service_client.get_booking(payload.booking_id, auth_header)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking["user_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This booking does not belong to you")
    if booking["status"] != "PENDING_PAYMENT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booking is {booking['status']}, cannot pay for it")
    expires_at = booking.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_409_CONFLICT, "This reservation has expired")

    mode = settings.payment_mode
    existing =db.execute(select(Payment).where(Payment.booking_id == payload.booking_id)).scalar_one_or_none()
    if existing and existing.status == PaymentStatus.CREATED:
        return CreateOrderResponse(
            razorpay_order_id=existing.razorpay_order_id, razorpay_key_id=settings.razorpay_key_id,
            amount_paise=razorpay_client.to_paise(float(existing.amount)), currency=existing.currency, booking_id=booking["id"], mode=mode,
        )
    if existing and existing.status == PaymentStatus.SUCCEEDED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This booking has already been paid for")

    amount = float(booking["total_amount"])
    try:
        order = razorpay_client.create_order(amount=amount, receipt=booking["id"], notes={"booking_id": booking["id"], "user_id": user.id})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Razorpay order creation failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not initialize payment with Razorpay. Check RAZORPAY_KEY_ID/SECRET are configured.") from exc

    payment = existing or Payment(
        booking_id=booking["id"], user_id=user.id, organizer_id=booking["organizer_id"], event_id=booking["event_id"],
        amount=amount, currency=settings.currency,
    )
    payment.razorpay_order_id = order["id"]
    payment.status = PaymentStatus.CREATED
    if not existing:
        db.add(payment)
    db.commit()

    return CreateOrderResponse(
        razorpay_order_id=order["id"], razorpay_key_id=settings.razorpay_key_id,
        amount_paise=razorpay_client.to_paise(amount), currency=settings.currency, booking_id=booking["id"], mode=mode,
    )


@router.post("/mock-pay")
def mock_pay(payload: MockPayRequest, user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    """Stands in for Razorpay Checkout in PAYMENT_MODE=mock; /verify then runs unchanged."""
    if not razorpay_client.is_mock():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    payment = db.execute(select(Payment).where(Payment.razorpay_order_id == payload.razorpay_order_id)).scalar_one_or_none()
    if not payment or payment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment order not found")
    payment_id = f"pay_mock_{uuid.uuid4().hex[:14]}"
    return {
        "razorpay_order_id": payload.razorpay_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": razorpay_client.sign_payment(payload.razorpay_order_id, payment_id),
    }


@router.post("/verify", response_model=PaymentOut)
def verify_payment(payload: VerifyPaymentRequest, user: CurrentUser = Depends(require_roles("ATTENDEE", "ORGANIZER", "ADMIN")), db: Session = Depends(get_db)):
    payment = db.execute(select(Payment).where(Payment.razorpay_order_id == payload.razorpay_order_id)).scalar_one_or_none()
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment order not found")
    if payment.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This payment does not belong to you")

    if payment.status == PaymentStatus.SUCCEEDED:
        return payment  # idempotent: duplicate success callback

    valid = razorpay_client.verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature)
    if not valid:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Signature verification failed"
        db.commit()
        _publish_safe("PaymentFailed", {"payment_id": payment.id, "booking_id": payment.booking_id, "user_id": payment.user_id, "reason": "invalid_signature"})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")

    payment.razorpay_payment_id = payload.razorpay_payment_id
    payment.razorpay_signature = payload.razorpay_signature
    payment.status = PaymentStatus.SUCCEEDED
    db.commit()
    db.refresh(payment)

    try:
        _confirm_booking_or_refund(db, payment)
    except BookingNoLongerAvailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your reservation was no longer available, so your payment has been refunded.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to confirm booking after verified payment %s", payment.id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Payment verified but booking confirmation failed; contact support") from exc

    _publish_safe("PaymentSucceeded", {
        "payment_id": payment.id, "booking_id": payment.booking_id, "user_id": payment.user_id,
        "organizer_id": payment.organizer_id, "event_id": payment.event_id, "amount": float(payment.amount),
    })
    return payment


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(default=""), db: Session = Depends(get_db)):
    """
    Handles Razorpay server-to-server webhooks as a defense-in-depth
    complement to the client-driven /verify flow (covers cases like the
    browser tab closing before the success callback fires).
    """
    body = await request.body()
    if not settings.razorpay_webhook_secret or not razorpay_client.verify_webhook_signature(body, x_razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    razorpay_payment_id = entity.get("id")

    if not order_id:
        return {"status": "ignored"}

    payment = db.execute(select(Payment).where(Payment.razorpay_order_id == order_id)).scalar_one_or_none()
    if not payment:
        return {"status": "ignored"}

    if event == "payment.captured" and payment.status != PaymentStatus.SUCCEEDED:
        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = PaymentStatus.SUCCEEDED
        db.commit()
        try:
            _confirm_booking_or_refund(db, payment)
        except BookingNoLongerAvailable:
            return {"status": "refunded"}
        except Exception:  # noqa: BLE001
            logger.exception("Webhook-driven booking confirmation failed for payment %s", payment.id)
        _publish_safe("PaymentSucceeded", {
            "payment_id": payment.id, "booking_id": payment.booking_id, "user_id": payment.user_id,
            "organizer_id": payment.organizer_id, "event_id": payment.event_id, "amount": float(payment.amount),
        })
    elif event == "payment.failed" and payment.status == PaymentStatus.CREATED:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = entity.get("error_description", "Payment failed")
        db.commit()
        _publish_safe("PaymentFailed", {"payment_id": payment.id, "booking_id": payment.booking_id, "user_id": payment.user_id, "reason": payment.failure_reason})

    return {"status": "processed"}


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if payment.user_id != user.id and payment.organizer_id != user.id and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot view this payment")
    return payment


@router.get("/booking/{booking_id}", response_model=PaymentOut)
def get_payment_by_booking(booking_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.execute(select(Payment).where(Payment.booking_id == booking_id)).scalar_one_or_none()
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if payment.user_id != user.id and payment.organizer_id != user.id and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot view this payment")
    return payment
