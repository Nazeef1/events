import os
import threading

from conftest import auth_header
from eventsphere_common.service_auth import service_headers

os.environ["INTERNAL_KEY_PAYMENT_TO_BOOKING"] = "test-payment-to-booking-key"
os.environ["INTERNAL_KEY_REFUND_TO_BOOKING"] = "test-refund-to-booking-key"


def test_confirm_route_only_accepts_payment_service(client, mock_event_service):
    mock_event_service["seed_event"]("evt-z")
    mock_event_service["seed_ticket"]("tt-z", quantity_available=5)
    headers, _ = auth_header("ATTENDEE")
    booking_id = client.post("/bookings/reserve", json={"event_id": "evt-z", "items": [{"ticket_type_id": "tt-z", "quantity": 1}]}, headers=headers).json()["id"]
    url = f"/internal/bookings/{booking_id}/confirm?payment_id=pay-1"

    assert client.post(url).status_code == 401  # no service token
    assert client.post(url, headers=service_headers("refund", "booking")).status_code == 403  # real service, wrong one
    resp = client.post(url, headers=service_headers("payment", "booking"))
    assert resp.status_code == 200 and resp.json()["status"] == "CONFIRMED"


def test_reserve_success_and_conflict_on_insufficient_stock(client, mock_event_service):
    mock_event_service["seed_event"]("evt-1")
    mock_event_service["seed_ticket"]("tt-1", quantity_available=2)
    headers, _ = auth_header("ATTENDEE")

    resp = client.post("/bookings/reserve", json={"event_id": "evt-1", "items": [{"ticket_type_id": "tt-1", "quantity": 2}]}, headers=headers)
    assert resp.status_code == 201
    booking = resp.json()
    assert booking["status"] == "PENDING_PAYMENT"
    assert float(booking["total_amount"]) == 1000.0

    # No stock left (2 of 2 already held) -> next reservation attempt must fail
    resp2 = client.post("/bookings/reserve", json={"event_id": "evt-1", "items": [{"ticket_type_id": "tt-1", "quantity": 1}]}, headers=headers)
    assert resp2.status_code == 409


def test_cancel_pending_booking_releases_hold(client, mock_event_service):
    mock_event_service["seed_event"]("evt-2")
    mock_event_service["seed_ticket"]("tt-2", quantity_available=1)
    headers, _ = auth_header("ATTENDEE")

    resp = client.post("/bookings/reserve", json={"event_id": "evt-2", "items": [{"ticket_type_id": "tt-2", "quantity": 1}]}, headers=headers)
    booking_id = resp.json()["id"]

    cancel = client.post(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    # hold released -> another attendee can now reserve the same ticket
    headers2, _ = auth_header("ATTENDEE")
    resp2 = client.post("/bookings/reserve", json={"event_id": "evt-2", "items": [{"ticket_type_id": "tt-2", "quantity": 1}]}, headers=headers2)
    assert resp2.status_code == 201


def test_only_owner_can_cancel(client, mock_event_service):
    mock_event_service["seed_event"]("evt-3")
    mock_event_service["seed_ticket"]("tt-3", quantity_available=5)
    headers, _ = auth_header("ATTENDEE")
    resp = client.post("/bookings/reserve", json={"event_id": "evt-3", "items": [{"ticket_type_id": "tt-3", "quantity": 1}]}, headers=headers)
    booking_id = resp.json()["id"]

    other_headers, _ = auth_header("ATTENDEE")
    resp = client.post(f"/bookings/{booking_id}/cancel", headers=other_headers)
    assert resp.status_code == 403


def test_reserve_with_idempotency_key_returns_same_booking_on_retry(client, mock_event_service):
    """Regression test: booking.id must be assigned before being referenced by the
    IdempotentRequest row, or this 500s with a NOT NULL constraint violation."""
    mock_event_service["seed_event"]("evt-5")
    mock_event_service["seed_ticket"]("tt-5", quantity_available=10)
    headers, _ = auth_header("ATTENDEE")

    body = {"event_id": "evt-5", "items": [{"ticket_type_id": "tt-5", "quantity": 1}]}
    r1 = client.post("/bookings/reserve", json=body, headers={**headers, "Idempotency-Key": "regress-key-1"})
    assert r1.status_code == 201

    r2 = client.post("/bookings/reserve", json=body, headers={**headers, "Idempotency-Key": "regress-key-1"})
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]  # same booking returned, not a duplicate


def test_last_ticket_concurrent_reservation_never_oversells(client, mock_event_service):
    """
    The single most important correctness property of the Booking Service:
    with exactly 1 ticket remaining, 10 simultaneous requests race for it,
    and AT MOST ONE may succeed.
    """
    mock_event_service["seed_event"]("evt-4")
    mock_event_service["seed_ticket"]("last-ticket", quantity_available=1)

    results = []
    lock = threading.Lock()

    def attempt():
        headers, _ = auth_header("ATTENDEE")
        resp = client.post("/bookings/reserve", json={"event_id": "evt-4", "items": [{"ticket_type_id": "last-ticket", "quantity": 1}]}, headers=headers)
        with lock:
            results.append(resp.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = results.count(201)
    conflicts = results.count(409)
    assert successes == 1, f"expected exactly 1 success, got {successes} (results={results})"
    assert conflicts == 9
