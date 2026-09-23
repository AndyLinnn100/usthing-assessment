from fastapi import FastAPI

app = FastAPI(title="USThing Timetable Service", version="0.1.0")


@app.get("/healthz")
def read_health() -> dict[str, str]:
    """Liveness probe — used later by container orchestration."""
    return {"status": "ok"}
