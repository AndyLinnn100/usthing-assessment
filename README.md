# USThing Timetable Service

Backend service for custom timetable events — USThing Backend Technical Test
2026, Task 1.

A REST API that lets each user create, read, update and delete custom events
in their own timetable, with a minimal token-based authorization layer and
per-user data isolation.

## Status

Feature-complete: multi-user auth, CRUD, `.ics` export, 22-test suite,
Docker packaging. See *Design & Architecture* below.

## Stack

- Python 3.13 + FastAPI
- SQLite + SQLAlchemy
- uv (dependency management), ruff (lint + format), pytest (tests)

## Design & Architecture

The service is layered with one rule: **dependencies point downward, never
upward.** The domain layer (`models.py`) knows nothing about sessions or
HTTP; the plumbing (`database.py`) knows nothing about HTTP; the Pydantic
border (`schemas.py`) touches neither. The routers are the only place the
worlds meet — which is where authentication hands off to per-resource
authorization.

```mermaid
flowchart TB
    C["Client<br/>(browser / curl / calendar app)"]

    subgraph entry["Entry & assembly — app/main.py"]
        UV["uvicorn server<br/>(Docker: 0.0.0.0:8000)"]
        LF["lifespan → init_db()<br/>(create tables once)"]
        APP["FastAPI app<br/>include_router(auth, events)"]
    end

    subgraph border["API border — app/schemas.py"]
        SC["Pydantic models: EventCreate / EventUpdate / EventRead,<br/>UserCreate / UserRead, Token<br/>validators: tz-aware datetimes, field limits, end after start"]
    end

    subgraph routers["HTTP layer — app/routers/"]
        AUTH["auth.py — authentication<br/>register (bcrypt, 409 on duplicates)<br/>login (mint bearer token)<br/>get_current_user (401 gate)"]
        EV["events.py — CRUD + /events/export.ics<br/>_owned_event: WHERE user_id = current_user.id"]
    end

    subgraph pure["Pure serializer — app/ics.py"]
        ICS["build_calendar(events)<br/>RFC 5545: escaping, folding, UTC"]
    end

    subgraph domain["Domain layer — app/models.py"]
        MOD["User / Event / AuthToken<br/>ISODatetime (exact ISO 8601 text),<br/>FK + ON DELETE CASCADE, unique + indexed columns"]
    end

    subgraph plumbing["Data plumbing — app/database.py"]
        GETDB["get_db(): one Session per request"]
        ENG["engine + connection pool<br/>PRAGMA foreign_keys = ON<br/>DATABASE_URL from env"]
    end

    DB[("SQLite — timetable.db<br/>(/data volume under Docker)")]

    C -->|"HTTP + Authorization: Bearer …"| UV
    UV --> APP
    LF -.->|"CREATE TABLE IF NOT EXISTS"| DB
    APP --> AUTH
    APP --> EV
    AUTH -->|"401 / Token"| C
    EV -->|"authenticate"| AUTH
    EV <-->|"validate request / shape response"| SC
    AUTH <-->|"UserCreate / Token"| SC
    EV --> ICS
    ICS -->|"text/calendar attachment"| C
    EV --> GETDB
    AUTH --> GETDB
    GETDB --> ENG
    ENG --> DB
    MOD -.->|"object ⇄ row mapping"| DB
    ENG -.->|"table definitions"| MOD
```

Layer responsibilities at a glance:

| Layer | File(s) | Owns | Never touches |
|---|---|---|---|
| Assembly | `main.py` | lifespan, router mounting | business logic |
| Border | `schemas.py` | input validation, output shaping | the database |
| HTTP | `routers/auth.py`, `routers/events.py` | authn gate, ownership scoping, stored-state rules | SQL details |
| Serialization | `ics.py` | RFC 5545 rendering | HTTP, SQL |
| Domain | `models.py` | tables, constraints, types | sessions, HTTP |
| Plumbing | `database.py` | engine, sessions, pool, env | business rules |

Lifecycle of one authenticated write (`POST /events`):

1. uvicorn → FastAPI routing; `get_current_user` resolves the bearer token
   (hash → `auth_tokens` row → `User`) — **who**
2. body validated into `EventCreate` — garbage dies as 422 at the border
3. handler stages `Event(user_id=current_user.id, …)` and commits —
   **ownership** assigned server-side, `INSERT` via `ISODatetime`
4. the ORM object is serialized through `EventRead` (`from_attributes`) —
   only schema-declared fields leave the service

## Running (dev)

```sh
uv run uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs
