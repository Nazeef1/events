def test_register_and_login(client):
    resp = client.post("/auth/register", json={
        "email": "attendee@example.com",
        "full_name": "Ada Attendee",
        "password": "supersecret123",
        "role": "ATTENDEE",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "attendee@example.com"
    assert "access_token" in body

    resp = client.post("/auth/login", json={"email": "attendee@example.com", "password": "supersecret123"})
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "ATTENDEE"


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={
        "email": "u2@example.com", "full_name": "U Two", "password": "correcthorsebattery", "role": "ATTENDEE",
    })
    resp = client.post("/auth/login", json={"email": "u2@example.com", "password": "wrongpassword"})
    assert resp.status_code == 401


def test_duplicate_registration_rejected(client):
    payload = {"email": "dup@example.com", "full_name": "Dup", "password": "password123", "role": "ATTENDEE"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_admin_only_user_listing(client):
    client.post("/auth/register", json={"email": "org@example.com", "full_name": "Org", "password": "password123", "role": "ORGANIZER"})
    login = client.post("/auth/login", json={"email": "org@example.com", "password": "password123"})
    token = login.json()["access_token"]

    resp = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403  # organizer cannot list all users

    from eventsphere_common.security import create_access_token

    admin_token = create_access_token("admin-id", "ADMIN", "admin@example.com")
    resp = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200


def test_cannot_self_register_as_admin(client):
    resp = client.post("/auth/register", json={"email": "evil@example.com", "full_name": "Evil", "password": "password123", "role": "ADMIN"})
    assert resp.status_code == 422


def test_user_lookup_requires_auth_and_ownership(client):
    a = client.post("/auth/register", json={"email": "a@example.com", "full_name": "A", "password": "password123"}).json()
    b = client.post("/auth/register", json={"email": "b@example.com", "full_name": "B", "password": "password123"}).json()
    url = f"/users/{a['user']['id']}"

    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": f"Bearer {b['access_token']}"}).status_code == 403
    assert client.get(url, headers={"Authorization": f"Bearer {a['access_token']}"}).status_code == 200
