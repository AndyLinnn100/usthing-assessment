# AGENTS.md — USThing Backend Technical Test 2026 (Task 1)

## Task context
Customizable Timetable Service: CRUD for custom events, minimal auth
(multi-user, per-user isolation), required extra features (candidate: .ics
export), documentation, Docker. Deadline 26 Sep 2026 23:59 HKT.
Grading: completeness, organization, architectural choices, creativity.
Commit history is graded. Task 2 (code review) is out of scope until Task 1
is done.

## Working mode (IMPORTANT — overrides defaults)
- The user is new to backend development and is learning by doing.
  Fully AI-generated code is an explicit fail condition for this assessment.
- Division of labor:
  - Assistant RUNS all shell commands (scaffolding, deps, git, tests) and
    explicitly explains what each command does and why it is needed, before
    or immediately after running it. No silent commands.
  - The user writes application code (models, schemas, routers, business
    logic) by hand. Assistant guides with TODO-style steps, short
    illustrative snippets (< ~10 lines), doc references, and the reasoning
    behind conventions (REST semantics, layering, sessions, status codes,
    authn vs authz).
  - Assistant may author non-code artifacts (.gitignore, README, tool
    config, AGENTS.md).
- Code review: identify issues, explain the cause, let the user fix them.
  Only rewrite when explicitly asked.
- Flag theory gaps proactively as they come up.

## Project conventions
- Python + FastAPI, REST. uv for deps; ruff for lint/format;
  pytest + TestClient for tests.
- SQLite + SQLAlchemy (task explicitly blesses a local DB).
- Layout: app/{main,config,database,models,schemas}.py, app/routers/, tests/.
- Pydantic at API boundaries only; ORM models stay separate.
- Auth (planned): OAuth2 password flow, bcrypt password hashes, opaque
  bearer tokens stored in DB, every query scoped by user_id; foreign
  resources return 404 (do not leak existence).
- Small meaningful commits after each working step; keep README current.
