"""SQLAlchemy ORM models — the domain layer.

Single source of truth for what data exists and which rules the *database
itself* enforces (uniqueness, referential integrity, NOT NULL). Pydantic
schemas in schemas.py are API-facing projections of these tables — kept
deliberately separate (see that file's docstring).

Design notes
------------
- Timestamps are persisted as exact ISO 8601 text via ``ISODatetime``.
  Rationale: SQLite's DATETIME storage silently drops ``tzinfo`` (its format
  is offset-less), so we store the string verbatim instead. This preserves
  the client's original offset (e.g. ``+08:00`` for HK timetables).
  Trade-off: ordering on these columns is correct for rows sharing one
  offset; cross-offset instant ordering is not guaranteed. Safe here
  because every event query is scoped to a single user.
- Server-generated timestamps (``created_at``/``updated_at``) always use
  UTC (``+00:00``); user-supplied event times echo the client's offset.
- Naive datetimes are refused at this layer as well — same contract as the
  API border in schemas.py (aware or rejected).
- Navigation via ``relationship()`` on both sides (design decision):
  lazy-loads fire hidden queries — when listing users together with their
  events, use ``selectinload(User.events)`` to avoid the N+1 problem.
  Authorization scoping still uses explicit ``user_id`` filters, never
  relationship traversal.
- ``passive_deletes=True`` hands child deletion to the database's
  ``ON DELETE CASCADE`` instead of the ORM issuing per-child DELETEs.
"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Registry of all tables; ``Base.metadata`` drives ``create_all``."""


def _utcnow() -> datetime:
    """Aware 'now' for column defaults (always UTC — see module docstring)."""
    return datetime.now(timezone.utc)


class ISODatetime(TypeDecorator):
    """Timezone-aware datetime persisted as exact ISO 8601 text.

    ``impl`` is what the column becomes in the database (a short string);
    the two ``process_*`` hooks convert at the storage boundary so Python
    code always handles real ``datetime`` objects.
    """

    impl = String(64)  # "2026-09-26T09:00:00.123456+08:00" = 35 chars max
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # Same rule as schemas.py — fail loud, never store ambiguity.
            raise ValueError("naive datetime refused: timezone-aware required")
        return value.isoformat()

    def process_result_value(self, value: str | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)  # int PK => autoincrement
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # bcrypt hashes are ~60 chars; headroom for algorithm changes.
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(ISODatetime, default=_utcnow)

    events: Mapped[list["Event"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tokens: Mapped[list["AuthToken"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Ownership: FK integrity (no orphan events) + CASCADE on user delete +
    # indexed, because every event query filters on this column.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    location: Mapped[str | None] = mapped_column(String(100), default=None)
    color: Mapped[str | None] = mapped_column(String(7), default=None)
    # tz-aware by contract (schemas.py enforces this at the API border).
    start_time: Mapped[datetime] = mapped_column(ISODatetime)
    end_time: Mapped[datetime] = mapped_column(ISODatetime)
    created_at: Mapped[datetime] = mapped_column(ISODatetime, default=_utcnow)
    # onupdate re-fires on every UPDATE, keeping updated_at honest.
    updated_at: Mapped[datetime] = mapped_column(ISODatetime, default=_utcnow, onupdate=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="events")

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r} start={self.start_time}>"


class AuthToken(Base):
    """A bearer token: the raw value lives only with the client.

    Design decisions:
    - Stored as sha256 hash — a database leak exposes no usable
      credentials. sha256 (fast) is fine because the raw token has 256
      bits of entropy: brute-forcing the hash space is infeasible.
    - No expiry (deliberate scope choice): revocation = delete the row.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(ISODatetime, default=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="tokens")

    def __repr__(self) -> str:
        return f"<AuthToken id={self.id} user_id={self.user_id}>"
