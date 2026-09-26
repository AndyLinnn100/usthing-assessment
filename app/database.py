"""Database plumbing: engine, session factory, request-scoped dependency.

Responsibility split (the layering you should internalize):
- ``models.py``    defines WHAT exists — tables, columns, constraints.
- ``database.py``  defines HOW we reach it — engine, pool, sessions.
- neither file knows anything about HTTP; that lives in the routers.

Three objects, three lifetimes:
- ``engine``        ONE per process. Owns the connection pool and the
                    dialect (SQLite-specific SQL generation).
- ``Session``       one per unit of work. Tracks ORM objects, stages
                    changes, and flushes them as SQL inside a transaction.
- ``get_db``        FastAPI glue: one Session per request, always closed.
"""

import os
from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

# File-based SQLite: data survives restarts — that is the point of a DB.
# Overridable via environment (12-factor): containers and test harnesses
# pin an ABSOLUTE path so the DB location never depends on the process's
# working directory. Full pydantic-settings was deliberately declined
# (single knob, not a graded requirement); revisit if config grows.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./timetable.db")

# --- Engine -----------------------------------------------------------------


def _attach_fk_pragma(eng: Engine) -> None:
    """SQLite does NOT enforce FK constraints unless asked, per connection.

    Proven in the models smoke test: without this pragma, orphan events are
    accepted silently. This hook runs on every new pooled connection.
    """

    @event.listens_for(eng, "connect")
    def _enforce_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_engine(url: str) -> Engine:
    """Engine factory — shared by the app and by test fixtures (isolation).

    check_same_thread=False: SQLite forbids sharing a connection across
    threads by default, but FastAPI dispatches sync handlers to a threadpool.
    """
    eng = create_engine(url, connect_args={"check_same_thread": False})
    _attach_fk_pragma(eng)
    return eng


engine = make_engine(DATABASE_URL)

# expire_on_commit=False: after commit(), objects keep their loaded attribute
# values instead of being marked stale. We serialize responses AFTER
# committing, and stale objects would re-emit a SELECT per attribute (or
# crash once the session closes). Standard companion to the per-request
# session pattern.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one Session per request.

    ``yield`` hands the session to the handler; everything after yield runs
    during response teardown — even if the handler raised. ``close()``
    returns the connection to the pool and discards uncommitted work.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables. Idempotent (CREATE IF NOT EXISTS).

    NOTE: create_all is a convenience, not a migration tool — it creates new
    tables but never alters existing ones. If the schema evolves mid-project,
    we graduate to Alembic (migrations) and note that in the README.
    """
    import app.models  # noqa: F401 — side-effect import: registers tables on Base.metadata

    Base.metadata.create_all(bind=engine)
