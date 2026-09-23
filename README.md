# USThing Timetable Service

Backend service for custom timetable events — USThing Backend Technical Test
2026, Task 1.

A REST API that lets each user create, read, update and delete custom events
in their own timetable, with a minimal token-based authorization layer and
per-user data isolation.

## Status

Work in progress — scaffolding stage.

## Stack

- Python 3.13 + FastAPI
- SQLite + SQLAlchemy
- uv (dependency management), ruff (lint + format), pytest (tests)

## Running (dev)

```sh
uv run uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs
