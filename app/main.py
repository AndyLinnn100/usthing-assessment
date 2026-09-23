from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once per process: create tables before serving, nothing after."""
    init_db()
    yield


app = FastAPI(title="USThing Timetable Service", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def read_health() -> dict[str, str]:
    """Liveness probe — used later by container orchestration."""
    return {"status": "ok"}
