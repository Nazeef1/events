import hashlib
import hmac

from conftest import auth_header

SECRET = "fake_secret"


def _sign(order_id: str, payment_id: str) -> str:
    return hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def test_create_order_for_own_pending_booking(client, mock_razorpay, mock_booking_service):
    headers, uid = auth_header("ATTENDEE")
    mock_booking_service["seed_booking"]("booking-1", user_id=uid, amount=1499.0)

    resp = client.post("/payments/order", json={"booking_id": "booking-1"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount_paise"] == 149900
    assert body["razorpay_key_id"] == "rzp_test_fake"
    assert body["razorpay_order_id"].startswith("order_")


def test_cannot_pay_for_someone_elses_booking(client, mock_razorpay, mock_booking_service):
    headers, _ = auth_header("ATTENDEE")
    mock_booking_service["seed_booking"]("booking-2", user_id="someone-else")

    resp = client.post("/payments/order", json={"booking_id": "booking-2"}, headers=headers)
    assert resp.status_code == 403


def test_verify_success_confirms_booking(client, mock_razorpay, mock_booking_service):
    headers, uid = auth_header("ATTENDEE")
    mock_booking_service["seed_booking"]("booking-3", user_id=uid, amount=500.0)
    order_resp = client.post("/payments/order", json={"booking_id": "booking-3"}, headers=headers)
    order_id = order_resp.json()["razorpay_order_id"]

    payment_id = "pay_abc123"
    signature = _sign(order_id, payment_id)

    resp = client.post("/payments/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCEEDED"
    assert "booking-3" in mock_booking_service["confirmed"]


def test_verify_rejects_bad_signature_and_does_not_confirm_booking(client, mock_razorpay, mock_booking_service):
    headers, uid = auth_header("ATTENDEE")
    mock_booking_service["seed_booking"]("booking-4", user_id=uid, amount=500.0)
    order_resp = client.post("/payments/order", json={"booking_id": "booking-4"}, headers=headers)
    order_id = order_resp.json()["razorpay_order_id"]

    resp = client.post("/payments/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": "pay_evil", "razorpay_signature": "tampered-signature",
    }, headers=headers)
    assert resp.status_code == 400
    assert "booking-4" not in mock_booking_service["confirmed"]


def test_mock_pay_is_disabled_unless_mock_mode(client, mock_razorpay, mock_booking_service):
    headers, _ = auth_header("ATTENDEE")
    resp = client.post("/payments/mock-pay", json={"razorpay_order_id": "order_x"}, headers=headers)
    assert resp.status_code == 404


def test_webhook_rejected_without_valid_signature(client, mock_razorpay, mock_booking_service):
    resp = client.post("/payments/webhook", content=b"{}", headers={"X-Razorpay-Signature": "forged"})
    assert resp.status_code == 400


def test_verify_is_idempotent_on_replay(client, mock_razorpay, mock_booking_service):
    headers, uid = auth_header("ATTENDEE")
    mock_booking_service["seed_booking"]("booking-5", user_id=uid, amount=750.0)
    order_id = client.post("/payments/order", json={"booking_id": "booking-5"}, headers=headers).json()["razorpay_order_id"]
    payment_id = "pay_dup"
    signature = _sign(order_id, payment_id)
    body = {"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature}

    r1 = client.post("/payments/verify", json=body, headers=headers)
    r2 = client.post("/payments/verify", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert mock_booking_service["confirmed"].count("booking-5") == 1  # confirm_booking only called once meaningfully
