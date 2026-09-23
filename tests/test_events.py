"""CRUD behavior of the events router against an isolated database."""

from app.database import DEV_USER_ID

LECTURE = {
    "title": "Lecture",
    "description": "COMP 1021",
    "start_time": "2026-09-26T09:00:00+08:00",
    "end_time": "2026-09-26T10:30:00+08:00",
}
LAB = {
    "title": "Lab",
    "start_time": "2026-09-26T11:00:00+08:00",
    "end_time": "2026-09-26T12:00:00+08:00",
}


def test_create_201_and_offset_echo(client):
    resp = client.post("/events", json=LECTURE)
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["id"], int)
    assert body["user_id"] == DEV_USER_ID
    assert body["title"] == "Lecture"
    assert body["start_time"].endswith("+08:00")  # client offset echoed exactly


def test_list_is_chronological(client):
    client.post("/events", json=LAB)  # inserted out of order on purpose
    client.post("/events", json=LECTURE)
    resp = client.get("/events")
    assert resp.status_code == 200
    assert [e["title"] for e in resp.json()] == ["Lecture", "Lab"]


def test_get_one_and_404(client):
    eid = client.post("/events", json=LECTURE).json()["id"]
    assert client.get(f"/events/{eid}").status_code == 200
    assert client.get("/events/99999").status_code == 404
    assert client.get("/events/abc").status_code == 422  # path param typing


def test_validation_422(client):
    missing_title = {k: v for k, v in LECTURE.items() if k != "title"}
    assert client.post("/events", json=missing_title).status_code == 422
    naive = {**LECTURE, "start_time": "2026-09-26T09:00:00"}
    assert client.post("/events", json=naive).status_code == 422


def test_patch_partial_and_stored_state_invariant(client):
    eid = client.post("/events", json=LECTURE).json()["id"]

    resp = client.patch(f"/events/{eid}", json={"title": "Renamed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Renamed"
    assert body["description"] == "COMP 1021"  # untouched by partial patch

    # end_time BEFORE the stored start_time — the schema cannot catch this;
    # only the handler, which sees the row, can.
    bad = {"end_time": "2026-09-26T08:00:00+08:00"}
    assert client.patch(f"/events/{eid}", json=bad).status_code == 422


def test_patch_explicit_null_clears_optional_field(client):
    eid = client.post("/events", json=LECTURE).json()["id"]
    resp = client.patch(f"/events/{eid}", json={"description": None})
    assert resp.status_code == 200
    assert resp.json()["description"] is None


def test_delete_204_with_empty_body_then_404(client):
    eid = client.post("/events", json=LECTURE).json()["id"]
    resp = client.delete(f"/events/{eid}")
    assert resp.status_code == 204
    assert resp.text == ""  # 204 = no body, by definition
    assert client.get(f"/events/{eid}").status_code == 404
