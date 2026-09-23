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

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

# File-based SQLite: data survives restarts — that is the point of a DB.
# TODO(auth milestone): move the URL into env-based config (pydantic-settings).
DATABASE_URL = "sqlite:///./timetable.db"

engine = create_engine(
    DATABASE_URL,
    # SQLite forbids using one connection across threads by default, but
    # FastAPI dispatches sync handlers ("def", not "async def") to a
    # threadpool — so any thread may pick up any pooled connection.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enforce_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
    """SQLite does NOT enforce FK constraints unless asked, per connection.

    Proven in the models smoke test: without this pragma, orphan events are
    accepted silently. This hook runs on every new pooled connection.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
