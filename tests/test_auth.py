"""Auth surface: registration, login, and the token gate."""

CRED = {"username": "carol", "password": "carol-pass"}


def test_register_201_no_password_leak(client):
    r = client.post("/auth/register", json=CRED)
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "carol"
    assert isinstance(body["id"], int)
    # Write-only by construction: neither raw nor hash may ever appear.
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_409(client):
    client.post("/auth/register", json=CRED)
    assert client.post("/auth/register", json=CRED).status_code == 409


def test_register_short_password_422(client):
    r = client.post("/auth/register", json={"username": "dave", "password": "short"})
    assert r.status_code == 422


def test_login_success_returns_bearer_token(client):
    client.post("/auth/register", json=CRED)
    r = client.post("/auth/login", data=CRED)  # form-encoded, not JSON (OAuth2)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) >= 32  # token_urlsafe(32)


def test_login_failures_are_uniform_401(client):
    client.post("/auth/register", json=CRED)
    wrong_pw = client.post("/auth/login", data={"username": "carol", "password": "nope-nope"})
    unknown_user = client.post("/auth/login", data={"username": "ghost", "password": "whatever1"})
    assert wrong_pw.status_code == unknown_user.status_code == 401
    assert wrong_pw.json() == unknown_user.json()  # indistinguishable outcomes


def test_endpoints_require_valid_token(client):
    assert client.get("/events").status_code == 401
    bogus = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/events", headers=bogus).status_code == 401
