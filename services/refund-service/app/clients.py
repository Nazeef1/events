from __future__ import annotations

import httpx
from eventsphere_common.service_auth import service_headers

from .config import settings


class PaymentServiceClient:
    def __init__(self) -> None:
        self._base = settings.payment_service_url

    def get_payment_for_booking(self, booking_id: str) -> dict | None:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{self._base}/internal/payments/booking/{booking_id}", headers=service_headers("refund", "payment"))
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def process_refund(self, payment_id: str) -> dict:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self._base}/internal/payments/{payment_id}/process-refund", headers=service_headers("refund", "payment"))
            resp.raise_for_status()
            return resp.json()


class BookingServiceClient:
    def __init__(self) -> None:
        self._base = settings.booking_service_url

    def get_bookings_by_event(self, event_id: str, booking_status: str | None = None) -> list[dict]:
        params = {"booking_status": booking_status} if booking_status else {}
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{self._base}/internal/bookings/by-event/{event_id}", params=params, headers=service_headers("refund", "booking")
            )
            resp.raise_for_status()
            return resp.json()

    def mark_refund_pending(self, booking_id: str) -> None:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{self._base}/internal/bookings/{booking_id}/mark-refund-pending", headers=service_headers("refund", "booking")
            ).raise_for_status()

    def mark_refunded(self, booking_id: str) -> None:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{self._base}/internal/bookings/{booking_id}/mark-refunded", headers=service_headers("refund", "booking")
            ).raise_for_status()


payment_service_client = PaymentServiceClient()
booking_service_client = BookingServiceClient()
