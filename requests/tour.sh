#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Guided HTTP tour of the USThing Timetable Service (manual testing aid).
#
#   ./requests/tour.sh [BASE_URL]        # default: http://localhost:8001
#
# Prereqs: curl + python3, and the server running:
#   uv run uvicorn app.main:app --reload --port 8001
#
# This is a DEMO, not a test suite (that's pytest's job): every step prints
# its HTTP status; "[expect NNN]" marks what you should see. Exported .ics
# files land in the CURRENT directory. Re-runnable without wiping the DB —
# registration steps tolerate 409.
# ---------------------------------------------------------------------------
BASE="${1:-http://localhost:8001}"
PW_A=alice-pass-1
PW_B=bob-pass-123

say()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
jget() { python3 -c 'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$1"; }
show() { curl -s -w '\n   [status] %{http_code}\n' "$@"; }

LECTURE='{"title":"COMP 1021 Lecture","description":"LT-B","location":"Rm 2405","color":"#1e90ff","start_time":"2026-09-26T09:00:00+08:00","end_time":"2026-09-26T10:30:00+08:00"}'
LAB='{"title":"Lab","start_time":"2026-09-26T11:00:00+08:00","end_time":"2026-09-26T12:00:00+08:00"}'

say "0. health"
show "$BASE/healthz"                                                    # [expect 200]

say "1. register alice & bob (201 first run, 409 on re-runs — both fine)"
show -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
     -d "{\"username\":\"alice\",\"password\":\"$PW_A\"}"
show -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
     -d "{\"username\":\"bob\",\"password\":\"$PW_B\"}"

say "2. logins -> tokens"
TOKEN_A=$(curl -s -X POST "$BASE/auth/login" -d "username=alice&password=$PW_A" | jget access_token)
TOKEN_B=$(curl -s -X POST "$BASE/auth/login" -d "username=bob&password=$PW_B" | jget access_token)
AUTH_A="Authorization: Bearer $TOKEN_A"
AUTH_B="Authorization: Bearer $TOKEN_B"
echo "   alice token: ${TOKEN_A:0:12}...   bob token: ${TOKEN_B:0:12}..."

say "3. auth failures (uniform 401 — no hint which part was wrong)"
show -X POST "$BASE/auth/login" -d "username=alice&password=wrong-wrong"   # [expect 401]
show -X POST "$BASE/auth/login" -d "username=ghost&password=whatever-123"  # [expect 401]
show "$BASE/events"                                                        # [expect 401] no token

say "4. alice creates two events"
EID=$(curl -s -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' -d "$LECTURE" | jget id)
echo "   created lecture id=$EID"
show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' -d "$LAB"   # [expect 201]

say "5. validation gallery — all 422, each a different rule"
show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
     -d '{"start_time":"2026-09-26T09:00:00+08:00","end_time":"2026-09-26T10:00:00+08:00"}'          # missing title
show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
     -d '{"title":"naive","start_time":"2026-09-26T09:00:00","end_time":"2026-09-26T10:00:00+08:00"}' # no UTC offset
show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
     -d '{"title":"backwards","start_time":"2026-09-26T11:00:00+08:00","end_time":"2026-09-26T10:00:00+08:00"}' # end<start
show "$BASE/events/abc" -H "$AUTH_A"                                      # path param typing

say "6. reads"
show "$BASE/events" -H "$AUTH_A"          # [expect 200] chronological
show "$BASE/events/$EID" -H "$AUTH_A"     # [expect 200]
show "$BASE/events/99999" -H "$AUTH_A"    # [expect 404]

say "7. patch semantics"
show -X PATCH "$BASE/events/$EID" -H "$AUTH_A" -H 'Content-Type: application/json' \
     -d '{"title":"Renamed Lecture"}'                                     # partial: rest untouched
show -X PATCH "$BASE/events/$EID" -H "$AUTH_A" -H 'Content-Type: application/json' \
     -d '{"description":null}'                                            # explicit null clears
show -X PATCH "$BASE/events/$EID" -H "$AUTH_A" -H 'Content-Type: application/json' \
     -d '{"end_time":"2026-09-26T08:00:00+08:00"}'                        # 422 vs STORED start

say "8. delete the Lab event"
LAB_ID=$(curl -s "$BASE/events" -H "$AUTH_A" | python3 -c 'import sys,json
evs=json.load(sys.stdin)
print(next((e["id"] for e in evs if e["title"]=="Lab"), ""))')
if [ -n "$LAB_ID" ]; then
  show -X DELETE "$BASE/events/$LAB_ID" -H "$AUTH_A"    # [expect 204, empty body]
  show "$BASE/events/$LAB_ID" -H "$AUTH_A"              # [expect 404]
else
  echo "   (no Lab event found — already deleted on a previous run)"
fi

say "9. isolation — bob vs alice's event"
show "$BASE/events" -H "$AUTH_B"            # bob's list: none of alice's events
show "$BASE/events/$EID" -H "$AUTH_B"       # [expect 404]
show -X PATCH "$BASE/events/$EID" -H "$AUTH_B" -H 'Content-Type: application/json' \
     -d '{"title":"hijack"}'                 # [expect 404]
show -X DELETE "$BASE/events/$EID" -H "$AUTH_B"   # [expect 404]
show "$BASE/events/$EID" -H "$AUTH_A"       # alice's event survived it all

say "10. iCalendar export (files land in the current directory)"
curl -s "$BASE/events/export.ics" -H "$AUTH_A" -o alice.ics -w '   alice.ics  [status] %{http_code}\n'
head -c 320 alice.ics; echo; echo
curl -s "$BASE/events/export.ics" -H "$AUTH_B" -o bob.ics -w '   bob.ics    [status] %{http_code}\n'
echo "   (bob.ics has no VEVENT — isolation holds in exports too)"

say "done — try importing alice.ics into Google/Apple Calendar"
