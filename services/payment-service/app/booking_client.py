from __future__ import annotations

import httpx
from eventsphere_common.service_auth import service_headers

from .config import settings


class BookingServiceClient:
    def __init__(self) -> None:
        self._base = settings.booking_service_url

    def get_booking(self, booking_id: str, auth_header: dict) -> dict | None:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{self._base}/bookings/{booking_id}", headers=auth_header)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def confirm_booking(self, booking_id: str, payment_id: str) -> dict:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{self._base}/internal/bookings/{booking_id}/confirm",
                params={"payment_id": payment_id},
                headers=service_headers("payment", "booking"),
            )
            resp.raise_for_status()
            return resp.json()


booking_service_client = BookingServiceClient()
