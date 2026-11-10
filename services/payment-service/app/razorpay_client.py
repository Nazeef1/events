"""
Razorpay integration, TEST MODE.

Setup (documented in full in the root README):
  1. Create a free Razorpay account: https://dashboard.razorpay.com/signup
  2. Toggle "Test Mode" in the top-left of the dashboard.
  3. Settings -> API Keys -> Generate Test Key -> copy Key Id / Key Secret
     into RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET in your .env.
  4. Settings -> Webhooks -> Add Webhook -> point it at
     POST {PUBLIC_URL}/payments/webhook, subscribe to `payment.captured`
     and `payment.failed`, and copy the generated secret into
     RAZORPAY_WEBHOOK_SECRET.
  5. Use Razorpay's published test card numbers to complete checkout
     locally, e.g. card 4111 1111 1111 1111, any future expiry, any CVV.

The secret key is only ever used server-side in this module; the
frontend receives only `razorpay_key_id` and the `order_id`, exactly as
Razorpay's Standard Checkout flow requires.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid

import razorpay

from .config import settings


def _client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def is_mock() -> bool:
    return settings.payment_mode == "mock"


def to_paise(amount: float) -> int:
    return int(round(amount * 100))


def sign_payment(order_id: str, payment_id: str) -> str:
    return hmac.new(
        key=settings.razorpay_key_secret.encode("utf-8"),
        msg=f"{order_id}|{payment_id}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def create_order(amount: float, receipt: str, notes: dict) -> dict:
    if is_mock():
        return {"id": f"order_mock_{uuid.uuid4().hex[:14]}"}
    client = _client()
    return client.order.create({
        "amount": to_paise(amount),
        "currency": settings.currency,
        "receipt": receipt,
        "notes": notes,
        "payment_capture": 1,
    })


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verifies HMAC-SHA256(order_id + '|' + payment_id, key_secret) == signature,
    exactly as Razorpay's Standard Checkout success callback specifies.
    """
    return hmac.compare_digest(sign_payment(order_id, payment_id), signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    generated = hmac.new(
        key=settings.razorpay_webhook_secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


def create_refund(razorpay_payment_id: str, amount: float, notes: dict | None = None) -> dict:
    if is_mock():
        return {"id": f"rfnd_mock_{uuid.uuid4().hex[:14]}"}
    client = _client()
    return client.payment.refund(razorpay_payment_id, {"amount": to_paise(amount), "notes": notes or {}})
