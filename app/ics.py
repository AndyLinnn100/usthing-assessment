"""Minimal hand-rolled iCalendar (RFC 5545) serializer.

Pure functions with no HTTP/SQL knowledge: the router fetches owned
events, this module turns them into text. That split keeps both testable
alone (see tests/test_ics.py).
"""

from datetime import datetime, timezone

from app.models import Event

PRODID = "-//USThing Timetable Service//EN"

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
