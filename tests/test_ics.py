"""The .ics export: structure, escaping, auth, and user scoping."""

LECTURE = {
    "title": "Lecture",
    "description": "COMP 1021",
    "location": "LT-B",
    "color": "#1e90ff",
    "start_time": "2026-09-26T09:00:00+08:00",  # = 01:00Z in UTC
    "end_time": "2026-09-26T10:30:00+08:00",  # = 02:30Z in UTC
}


def test_export_requires_token(client):
    assert client.get("/events/export.ics").status_code == 401


def test_export_headers_and_structure(client, auth_headers):
    eid = client.post("/events", json=LECTURE, headers=auth_headers).json()["id"]

    resp = client.get("/events/export.ics", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert 'attachment; filename="timetable.ics"' in resp.headers["content-disposition"]

    body = resp.text
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert body.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in body
    assert f"UID:{eid}@usthing-timetable" in body
    assert "DTSTART:20260926T010000Z" in body  # +08:00 converted to UTC
    assert "DTEND:20260926T023000Z" in body
    assert "X-COLOR:#1e90ff" in body  # legal X- experimental property
    assert "\r\n" in body  # RFC 5545 requires CRLF line endings


def test_export_escapes_special_characters(client, auth_headers):
    nasty = {
        **LECTURE,
        "title": "Seminar; Group, A",
        "description": "line one\nline two",
    }
    client.post("/events", json=nasty, headers=auth_headers)
    body = client.get("/events/export.ics", headers=auth_headers).text
    assert "SUMMARY:Seminar\\; Group\\, A" in body
    assert "DESCRIPTION:line one\\nline two" in body


def test_export_is_user_scoped(client, auth_headers, second_headers):
    client.post("/events", json=LECTURE, headers=second_headers)
    body = client.get("/events/export.ics", headers=auth_headers).text
    assert "VEVENT" not in body  # bob's event never reaches alice's calendar


def test_empty_export_is_valid_empty_calendar(client, auth_headers):
    body = client.get("/events/export.ics", headers=auth_headers).text
    assert "BEGIN:VEVENT" not in body
    assert "BEGIN:VCALENDAR" in body
