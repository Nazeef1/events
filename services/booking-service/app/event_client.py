from __future__ import annotations

import httpx
from eventsphere_common.service_auth import service_headers

from .config import settings


def _auth() -> dict[str, str]:
    # A fresh short-lived token per call proves to Event Service that Booking Service is calling.
    return service_headers("booking", "event")


class EventServiceClient:
    def __init__(self) -> None:
        self._base = settings.event_service_url

    def get_ticket_type(self, ticket_type_id: str) -> dict | None:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{self._base}/internal/ticket-types/{ticket_type_id}", headers=_auth())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def get_event_summary(self, event_id: str) -> dict | None:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{self._base}/internal/events/{event_id}/summary", headers=_auth())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def decrement_availability(self, ticket_type_id: str, quantity: int, idempotency_key: str) -> dict:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{self._base}/internal/ticket-types/{ticket_type_id}/decrement",
                json={"quantity": quantity, "idempotency_key": idempotency_key},
                headers=_auth(),
            )
            resp.raise_for_status()
            return resp.json()

    def increment_availability(self, ticket_type_id: str, quantity: int, idempotency_key: str) -> dict:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{self._base}/internal/ticket-types/{ticket_type_id}/increment",
                json={"quantity": quantity, "idempotency_key": idempotency_key},
                headers=_auth(),
            )
            resp.raise_for_status()
            return resp.json()


event_service_client = EventServiceClient()
