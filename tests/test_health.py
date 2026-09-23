from fastapi.testclient import TestClient

from app.main import app

# Constructed once per module: TestClient is reusable across tests.
client = TestClient(app)


def test_health() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
