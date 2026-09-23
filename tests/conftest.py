"""Shared test fixtures.

Key trick: FastAPI *dependency override* — swap ``get_db`` for a session
bound to a throwaway per-test database. This is the payoff of ``Depends()``:
the app never hardcodes its session source, so tests choose their own.

Isolation choice: a file DB under pytest's ``tmp_path``, one per test —
production-like, zero cross-test bleed. Alternative: in-memory SQLite +
``StaticPool`` (faster, one extra pooling subtlety) — noted for honesty,
not used.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import DEV_USER_ID, get_db, make_engine
from app.main import app
from app.models import Base, User


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
    # Seed the single-user boundary the events router scopes to.
    with session_factory() as db:
        if db.get(User, DEV_USER_ID) is None:
            db.add(User(id=DEV_USER_ID, username="dev", password_hash="x"))
            db.commit()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Deliberately NOT a context manager: entering TestClient would run the
    # real lifespan (init_db/ensure_dev_user against the real timetable.db).
    # tests/test_db.py covers lifespan separately; requests need neither.
    yield TestClient(app)
    app.dependency_overrides.clear()
