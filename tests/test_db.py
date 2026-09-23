"""Verifies the lifespan wiring: startup must create all tables."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.database import engine
from app.main import app


def test_startup_creates_tables() -> None:
    # `with` is load-bearing: only the context manager triggers lifespan
    # (and therefore init_db). A bare TestClient(app) would skip it.
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    tables = set(inspect(engine).get_table_names())
    assert {"users", "events"} <= tables
