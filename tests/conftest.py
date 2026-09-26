"""Shared test fixtures.

Key trick: FastAPI *dependency override* — swap ``get_db`` for a session
bound to a throwaway per-test database. This is the payoff of ``Depends()``:
the app never hardcodes its session source, so tests choose their own.

Isolation choice: a file DB under pytest's ``tmp_path``, one per test —
production-like, zero cross-test bleed. Alternative: in-memory SQLite +
``StaticPool`` (faster, one extra pooling subtlety) — noted for honesty,
not used.

Auth helpers: ``register_and_login()`` returns ready-made Authorization
headers; ``auth_headers`` / ``second_headers`` provide two distinct users
so isolation (scoping) is actually observable in tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db, make_engine
from app.main import app
from app.models import Base


@pytest.fixture()
def db_engine(tmp_path):
    """Fresh engine + schema per test; torn down after."""
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    """App client whose requests hit the isolated engine, not timetable.db."""

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Deliberately NOT a context manager: entering TestClient would run the
    # real lifespan (init_db against the real timetable.db). tests/test_db.py
    # covers lifespan separately; requests need neither.
    yield TestClient(app)
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, username: str, password: str) -> dict[str, str]:
    """Register (tolerating 409 on re-register) + login → auth headers."""
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth_headers(client):
    """Alice's Authorization header (fresh user per test)."""
    return register_and_login(client, "alice", "alice-pass-1")


@pytest.fixture()
def second_headers(client):
    """Bob's Authorization header — the second user isolation tests need."""
    return register_and_login(client, "bob", "bob-pass-123")
