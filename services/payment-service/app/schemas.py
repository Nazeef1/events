from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from .models import PaymentStatus


class CreateOrderRequest(BaseModel):
    booking_id: str


class CreateOrderResponse(BaseModel):
    razorpay_order_id: str
    razorpay_key_id: str
    amount_paise: int
    currency: str
    booking_id: str
    mode: str = "razorpay"


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class MockPayRequest(BaseModel):
    razorpay_order_id: str


class PaymentOut(BaseModel):
    id: str
    booking_id: str
    user_id: str
    organizer_id: str
    event_id: str
    razorpay_order_id: str
    razorpay_payment_id: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    failure_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
