"""Pydantic schemas — the API boundary contracts.

Schemas are separated by direction of travel:
- ``Create``: what a client may send when creating a resource (no
  server-assigned fields such as ``id``).
- ``Update``: what a client may send when patching; an absent field means
  "leave unchanged".
- ``Read``: what the API returns; built from ORM objects via
  ``from_attributes``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    """Payload for ``POST /events``."""

    title: str = Field(min_length=1, max_length=100, examples=["COMP 1021 Lecture"])
    description: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        """Reject naive datetimes: without a UTC offset, "9:30" is ambiguous."""
        if v.tzinfo is None:
            raise ValueError("timestamps must include a UTC offset (ISO 8601)")
        return v

    @model_validator(mode="after")
    def _times_ordered(self) -> "EventCreate":
        """Domain invariant: an event cannot end before (or exactly when) it starts."""
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EventUpdate(BaseModel):
    """Payload for ``PATCH /events/{event_id}``; absent fields stay unchanged.

    Note: the end-after-start invariant cannot be enforced here — when only
    one bound is patched, validity depends on the *stored* value. The router
    must re-check it against the database row.
    """

    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    start_time: datetime | None = None
    end_time: datetime | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def _require_timezone(cls, v: datetime | None) -> datetime | None:
        """Same timezone rule as EventCreate, applied only to provided values."""
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must include a UTC offset (ISO 8601)")
        return v


class EventRead(BaseModel):
    """Representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str | None
    location: str | None
    color: str | None
    start_time: datetime
    end_time: datetime
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# User / auth
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """Registration payload. The password is write-only: never echoed back."""

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    # 72 max: bcrypt only considers the first 72 BYTES — refuse longer
    # secrets at the border rather than silently truncating them.
    password: str = Field(min_length=8, max_length=72)


class UserRead(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class Token(BaseModel):
    """Response of ``POST /auth/login`` (OAuth2 password flow)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
