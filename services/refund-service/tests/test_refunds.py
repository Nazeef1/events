import time
import uuid

from conftest import auth_header


def test_manual_refund_trigger(client, mock_clients):
    headers, uid = auth_header("ATTENDEE")
    mock_clients["seed_payment"]("pay-1", "booking-1", user_id=uid, amount=1499.0)

    resp = client.post("/refunds", json={"booking_id": "booking-1"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["razorpay_refund_id"].startswith("rfnd_")
    assert "booking-1" in mock_clients["booking_marked_refunded"]
    assert mock_clients["refund_calls"] == ["pay-1"]


def test_refund_is_idempotent(client, mock_clients):
    headers, uid = auth_header("ATTENDEE")
    mock_clients["seed_payment"]("pay-2", "booking-2", user_id=uid)

    r1 = client.post("/refunds", json={"booking_id": "booking-2"}, headers=headers)
    r2 = client.post("/refunds", json={"booking_id": "booking-2"}, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    assert mock_clients["refund_calls"] == ["pay-2"]  # Razorpay refund only ever called once


def test_unrelated_organizer_cannot_refund(client, mock_clients):
    _, payer = auth_header("ATTENDEE")
    mock_clients["seed_payment"]("pay-3", "booking-3", user_id=payer)
    headers, _ = auth_header("ORGANIZER")

    resp = client.post("/refunds", json={"booking_id": "booking-3"}, headers=headers)
    assert resp.status_code == 403
    assert mock_clients["refund_calls"] == []  # rejected before any money moved


def test_refund_without_payment_returns_404(client, mock_clients):
    headers, _ = auth_header("ATTENDEE")
    resp = client.post("/refunds", json={"booking_id": "no-such-booking"}, headers=headers)
    assert resp.status_code == 404


def test_worker_processes_real_refund_requested_event(client, mock_clients):
    """Publishes a real RefundRequested event on RabbitMQ and confirms the consumer processes it end-to-end."""
    import threading

    from app.database import SessionLocal
    from app.models import Refund
    from app.worker import run_worker
    from eventsphere_common.bus import publish_event

    booking_id = f"booking-{uuid.uuid4().hex[:8]}"
    _, uid = auth_header("ATTENDEE")
    mock_clients["seed_payment"]("pay-e2e", booking_id, user_id=uid, amount=250.0)

    t = threading.Thread(target=run_worker, daemon=True)
    t.start()
    time.sleep(1.5)

    publish_event("RefundRequested", "test", {"booking_id": booking_id, "user_id": uid, "amount": 250.0})

    deadline = time.time() + 6
    refund = None
    db = SessionLocal()
    try:
        while time.time() < deadline:
            refund = db.query(Refund).filter(Refund.booking_id == booking_id).one_or_none()
            if refund and refund.status.value == "COMPLETED":
                break
            db.expire_all()
            time.sleep(0.3)
    finally:
        db.close()

    assert refund is not None
    assert refund.status.value == "COMPLETED"
