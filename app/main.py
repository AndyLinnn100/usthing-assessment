from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import ensure_dev_user, init_db
from app.routers import events


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once per process: schema + single-user bootstrap, then serve."""
    init_db()
    ensure_dev_user()  # single-user scaffolding; removed at the auth milestone
    yield


app = FastAPI(title="USThing Timetable Service", version="0.1.0", lifespan=lifespan)
app.include_router(events.router)


@app.get("/healthz")
def read_health() -> dict[str, str]:
    """Liveness probe — used later by container orchestration."""
    return {"status": "ok"}
