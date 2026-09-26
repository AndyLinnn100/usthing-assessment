"""Minimal hand-rolled iCalendar (RFC 5545) serializer.

Scope decisions (documented in README):
- Datetimes export as UTC ("...Z"): correct instants, simple format.
  Full TZID/VTIMEZONE support is explicitly out of scope.
- ``color`` exports as ``X-COLOR`` — the X- prefix is reserved for
  experimental properties (RFC 5545 §3.8.8.2), so this is legal.
- Content lines fold at 72 characters with a single-space continuation
  prefix (RFC 5545 §3.1). We fold on characters — never mid-character —
  so UTF-8 stays intact; the 75-OCTET limit is met conservatively for
  ASCII and approximated for multibyte text.

Pure functions with no HTTP/SQL knowledge: the router fetches owned
events, this module turns them into text. That split keeps both testable
alone (see tests/test_ics.py).
"""

from datetime import datetime, timezone

from app.models import Event

PRODID = "-//USThing Timetable Service//EN"

# RFC 5545 §3.1: content lines SHOULD be wrapped at 75 octets; we fold
# earlier (72 chars) to stay conservative.
_FOLD_AT = 72


def _escape(text: str) -> str:
    """RFC 5545 §3.3.11: escape backslash, semicolon, comma; newline → \\n."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def _fmt_utc(dt: datetime) -> str:
    """Aware datetime → UTC "basic form": 20260926T010000Z."""
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> list[str]:
    """Split a long content line into RFC-style continuation chunks."""
    if len(line) <= _FOLD_AT:
        return [line]
    chunks = [line[i : i + _FOLD_AT] for i in range(0, len(line), _FOLD_AT)]
    return [chunks[0]] + [" " + chunk for chunk in chunks[1:]]


def _vevent_lines(ev: Event, dtstamp: datetime) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{ev.id}@usthing-timetable",  # stable across exports
        f"DTSTAMP:{_fmt_utc(dtstamp)}",
        f"DTSTART:{_fmt_utc(ev.start_time)}",
        f"DTEND:{_fmt_utc(ev.end_time)}",
        f"SUMMARY:{_escape(ev.title)}",
    ]
    if ev.description is not None:
        lines.append(f"DESCRIPTION:{_escape(ev.description)}")
    if ev.location is not None:
        lines.append(f"LOCATION:{_escape(ev.location)}")
    if ev.color is not None:
        lines.append("X-COLOR:" + ev.color)
    lines.append("END:VEVENT")
    return lines


def build_calendar(events: list[Event], now: datetime) -> str:
    """Render owned events as a complete VCALENDAR document (CRLF lines)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
    ]
    for ev in events:
        lines.extend(_vevent_lines(ev, dtstamp=now))
    lines.append("END:VCALENDAR")

    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
