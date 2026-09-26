"""The witnessing tests: ownership scoping is now OBSERVABLE.

With one user, "list everything" and "list mine" are indistinguishable, so
no test could detect missing scoping (proven live during development by
deleting the user_id predicate and watching the suite stay green). These
tests seed two users; from here on, a scoping regression fails loudly.
"""

LECTURE = {
    "title": "Bob's Lecture",
    "start_time": "2026-09-26T09:00:00+08:00",
    "end_time": "2026-09-26T10:30:00+08:00",
}


def test_alices_list_excludes_bobs_events(client, auth_headers, second_headers):
    r = client.post("/events", json=LECTURE, headers=second_headers)
    assert r.status_code == 201
    assert client.get("/events", headers=auth_headers).json() == []


def test_cross_user_access_is_404(client, auth_headers, second_headers):
    eid = client.post("/events", json=LECTURE, headers=second_headers).json()["id"]

    assert client.get(f"/events/{eid}", headers=auth_headers).status_code == 404
    patch = client.patch(f"/events/{eid}", json={"title": "hijack"}, headers=auth_headers)
    assert patch.status_code == 404
    assert client.delete(f"/events/{eid}", headers=auth_headers).status_code == 404

    # Bob's event is untouched by all those attempts.
    assert client.get(f"/events/{eid}", headers=second_headers).status_code == 200
    assert client.get(f"/events/{eid}", headers=second_headers).json()["title"] == "Bob's Lecture"
