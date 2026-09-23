"""Events router — CRUD for custom timetable events (single-user scope).

Design notes
------------
- **Ownership scoping**: every query filters by ``user_id == DEV_USER_ID``.
  This is the authorization pattern; the auth milestone only swaps the
  constant for ``current_user.id``. Rows that aren't yours are
  indistinguishable from rows that don't exist → 404, never 403 (do not
  leak that other users' events exist).
- **404 is decided here, not in the database**: a missing row makes the
  SELECT return nothing — the DB never raises. Handlers translate
  "empty result" into HTTPException(404).
- **PATCH semantics**: absent field = unchanged; explicit ``null`` clears
  the field. ``model_dump(exclude_unset=True)`` is what distinguishes them.
- **The end-after-start invariant on PATCH** is checked here against stored
  values — the schema only sees the patch payload, not the row.
- POST path is ``""`` (not ``"/"``): with ``prefix="/events"`` the latter
  would produce the distinct URL ``/events/`` — FastAPI does not merge them.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import DEV_USER_ID, get_db
from app.models import Event
from app.schemas import EventCreate, EventRead, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])


def _owned_event(db: Session, event_id: int) -> Event | None:
    """Fetch one event scoped to its owner; None means "not found"."""
    return db.scalars(
        select(Event).where(Event.id == event_id, Event.user_id == DEV_USER_ID)
    ).first()


@router.post("", status_code=201, response_model=EventRead)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> Event:
    """Create an event. 201 + the full stored representation."""
    event = Event(user_id=DEV_USER_ID, **payload.model_dump())
    db.add(event)  # stage only — no SQL yet (unit of work)
    db.commit()  # INSERT goes out here; id was assigned at flush
    return event  # serialized via EventRead (from_attributes), no re-query


@router.get("", response_model=list[EventRead])
def list_events(db: Session = Depends(get_db)) -> list[Event]:
    """List own events, chronological. Ordering on ISO text is exact within
    one offset — safe because the query is user-scoped (see models.py)."""
    stmt = select(Event).where(Event.user_id == DEV_USER_ID).order_by(Event.start_time)
    return list(db.scalars(stmt))


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: Session = Depends(get_db)) -> Event:
    event = _owned_event(db, event_id)
    if event is None:  # empty result → our decision to 404
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=EventRead)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)) -> Event:
    event = _owned_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    changes = payload.model_dump(exclude_unset=True)  # absent ≠ explicit null
    for field, value in changes.items():
        setattr(event, field, value)

    # Invariant needs stored state: fall back to the row for the bound that
    # wasn't patched. 422 keeps one error family for validation failures.
    start = changes.get("start_time", event.start_time)
    end = changes.get("end_time", event.end_time)
    if end <= start:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    db.commit()  # UPDATE emitted; onupdate=_utcnow refreshes updated_at
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db)) -> None:
    event = _owned_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()
    # 204 = success, deliberately no body — return None and FastAPI obeys.
