#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Guided HTTP tour of the USThing Timetable Service (manual testing aid).
#
#   ./requests/tour.sh                # interactive menu
#   ./requests/tour.sh 3 5 9          # run sections 3, 5, 9 only
#   ./requests/tour.sh all            # full tour, non-interactive
#   BASE_URL=http://host:8080 ./tour.sh ...   # override target
#
# Sections depend on each other (PATCH needs an event; events need tokens).
# Selecting a section AUTO-RUNS its prerequisites first, in canonical order.
# This is a DEMO, not a test suite (that's pytest's job): every request
# prints its HTTP status; "[expect NNN]" marks what you should see.
# Exported .ics files land in the CURRENT directory.
# ---------------------------------------------------------------------------
BASE="${BASE_URL:-http://localhost:8001}"
PW_A=alice-pass-1
PW_B=bob-pass-123

say()  { printf '\n\033[1;36m== §%s %s ==\033[0m\n' "$1" "$2"; }
jget() { python3 -c 'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$1"; }
show() { curl -s -w '\n   [status] %{http_code}\n' "$@"; }

LECTURE='{"title":"COMP 1021 Lecture","description":"LT-B","location":"Rm 2405","color":"#1e90ff","start_time":"2026-09-26T09:00:00+08:00","end_time":"2026-09-26T10:30:00+08:00"}'
LAB='{"title":"Lab","start_time":"2026-09-26T11:00:00+08:00","end_time":"2026-09-26T12:00:00+08:00"}'

declare -A TITLE DEPS
TITLE[0]="health";                 DEPS[0]=""
TITLE[1]="register alice & bob";   DEPS[1]=""
TITLE[2]="login -> tokens";        DEPS[2]="1"
TITLE[3]="auth failures (401s)";   DEPS[3]="1 2"
TITLE[4]="create events";          DEPS[4]="1 2"
TITLE[5]="validation gallery";     DEPS[5]="1 2"
TITLE[6]="reads";                  DEPS[6]="1 2 4"
TITLE[7]="patch semantics";        DEPS[7]="1 2 4"
TITLE[8]="delete";                 DEPS[8]="1 2 4"
TITLE[9]="isolation";              DEPS[9]="1 2 4"
TITLE[10]="ics export";            DEPS[10]="1 2 4"

run_section() {
  case "$1" in
    0)
      show "$BASE/healthz"                                                    # [expect 200]
      ;;
    1)
      show -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
           -d "{\"username\":\"alice\",\"password\":\"$PW_A\"}"               # 201 (409 on re-runs)
      show -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
           -d "{\"username\":\"bob\",\"password\":\"$PW_B\"}"
      ;;
    2)
      TOKEN_A=$(curl -s -X POST "$BASE/auth/login" -d "username=alice&password=$PW_A" | jget access_token)
      TOKEN_B=$(curl -s -X POST "$BASE/auth/login" -d "username=bob&password=$PW_B" | jget access_token)
      AUTH_A="Authorization: Bearer $TOKEN_A"
      AUTH_B="Authorization: Bearer $TOKEN_B"
      echo "   alice token: ${TOKEN_A:0:12}...   bob token: ${TOKEN_B:0:12}..."
      ;;
    3)
      show -X POST "$BASE/auth/login" -d "username=alice&password=wrong-wrong"   # [expect 401]
      show -X POST "$BASE/auth/login" -d "username=ghost&password=whatever-123"  # [expect 401]
      show "$BASE/events"                                                        # [expect 401] no token
      ;;
    4)
      # Reuse the tour's own events across runs; create only what's missing.
      local info has_lab
      info=$(curl -s "$BASE/events" -H "$AUTH_A" | python3 -c '
import sys, json
evs = json.load(sys.stdin)
eid = next((e["id"] for e in evs if e["title"] == "COMP 1021 Lecture"), "")
lab = "y" if any(e["title"] == "Lab" for e in evs) else ""
print(eid, lab)')
      EID=${info%% *}
      has_lab=${info##* }
      if [ -n "$EID" ]; then
        echo "   reusing existing lecture id=$EID"
      else
        EID=$(curl -s -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
              -d "$LECTURE" | jget id)
        echo "   created lecture id=$EID"
      fi
      if [ "$has_lab" != "y" ]; then
        show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' -d "$LAB"  # [expect 201]
      else
        echo "   Lab already exists"
      fi
      ;;
    5)
      show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
           -d '{"start_time":"2026-09-26T09:00:00+08:00","end_time":"2026-09-26T10:00:00+08:00"}'          # missing title
      show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
           -d '{"title":"naive","start_time":"2026-09-26T09:00:00","end_time":"2026-09-26T10:00:00+08:00"}' # no UTC offset
      show -X POST "$BASE/events" -H "$AUTH_A" -H 'Content-Type: application/json' \
           -d '{"title":"backwards","start_time":"2026-09-26T11:00:00+08:00","end_time":"2026-09-26T10:00:00+08:00"}' # end<start
      show "$BASE/events/abc" -H "$AUTH_A"                                      # path param typing
      ;;
    6)
      show "$BASE/events" -H "$AUTH_A"          # [expect 200] chronological
      show "$BASE/events/$EID" -H "$AUTH_A"     # [expect 200]
      show "$BASE/events/99999" -H "$AUTH_A"    # [expect 404]
      ;;
    7)
      show -X PATCH "$BASE/events/$EID" -H "$AUTH_A" -H 'Content-Type: application/json' \
           -d '{"title":"Renamed Lecture"}'                                     # partial: rest untouched
      show -X PATCH "$BASE/events/$EID" -H "$AUTH_A" -H 'Content-Type: application/json' \
           -d '{"description":null}'                                            # explicit null clears
      show -X PATCH "$BASE/events/$EID" -H "$AUTH_A" -H 'Content-Type: application/json' \
           -d '{"end_time":"2026-09-26T08:00:00+08:00"}'                        # 422 vs STORED start
      ;;
    8)
      local lab_id
      lab_id=$(curl -s "$BASE/events" -H "$AUTH_A" | python3 -c '
import sys, json
evs = json.load(sys.stdin)
print(next((e["id"] for e in evs if e["title"] == "Lab"), ""))')
      if [ -n "$lab_id" ]; then
        show -X DELETE "$BASE/events/$lab_id" -H "$AUTH_A"    # [expect 204, empty body]
        show "$BASE/events/$lab_id" -H "$AUTH_A"              # [expect 404]
      else
        echo "   (no Lab event found — already deleted on a previous run)"
      fi
      ;;
    9)
      show "$BASE/events" -H "$AUTH_B"            # bob's list: none of alice's events
      show "$BASE/events/$EID" -H "$AUTH_B"       # [expect 404]
      show -X PATCH "$BASE/events/$EID" -H "$AUTH_B" -H 'Content-Type: application/json' \
           -d '{"title":"hijack"}'                 # [expect 404]
      show -X DELETE "$BASE/events/$EID" -H "$AUTH_B"   # [expect 404]
      show "$BASE/events/$EID" -H "$AUTH_A"       # alice's event survived it all
      ;;
    10)
      curl -s "$BASE/events/export.ics" -H "$AUTH_A" -o alice.ics -w '   alice.ics  [status] %{http_code}\n'
      head -c 320 alice.ics; echo; echo
      curl -s "$BASE/events/export.ics" -H "$AUTH_B" -o bob.ics -w '   bob.ics    [status] %{http_code}\n'
      echo "   (bob.ics has no VEVENT — isolation holds in exports too)"
      ;;
  esac
}

declare -A RAN=()
run_one() {  # depth-first prerequisite resolution, canonical order, no repeats
  local n="$1" d
  [ -n "${RAN[$n]:-}" ] && return 0
  for d in ${DEPS[$n]}; do run_one "$d"; done
  say "$n" "${TITLE[$n]}"
  run_section "$n"
  RAN[$n]=1
}

valid_section() { [[ "$1" =~ ^[0-9]+$ ]] && [ -n "${TITLE[$1]:-}" ]; }

menu() {
  local ans n
  while true; do
    echo
    echo "Tour sections (prerequisites run automatically):"
    for n in 0 1 2 3 4 5 6 7 8 9 10; do
      printf '  %2d  %-26s deps: %s\n' "$n" "${TITLE[$n]}" "${DEPS[$n]:-none}"
    done
    echo "   a  run ALL        q  quit"
    printf 'run which? (e.g. "7" or "3 5 9"): '
    read -r ans || return 0        # EOF (piped input) = quit
    case "$ans" in
      "") : ;;                     # just re-show the menu
      q|Q) return 0 ;;
      a|A|all)
        for n in 0 1 2 3 4 5 6 7 8 9 10; do run_one "$n"; done ;;
      *)
        for n in $ans; do
          if valid_section "$n"; then run_one "$n"
          else echo "unknown section: $n"; fi
        done ;;
    esac
  done
}

if [ $# -eq 0 ]; then
  menu
elif [ "$1" = "all" ]; then
  for n in 0 1 2 3 4 5 6 7 8 9 10; do run_one "$n"; done
else
  for n in "$@"; do
    if valid_section "$n"; then :; else echo "unknown section: $n" >&2; exit 2; fi
  done
  for n in "$@"; do run_one "$n"; done
fi
