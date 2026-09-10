"""Wall-clock helpers pinned to *your* timezone, not the host's.

Every schedule in this hub ("email me at 07:00", "push the forecast at
13:00") is a statement about local wall-clock time where you live. The
host clock is only that by luck: it's UTC in Docker and in CI, and
whatever the laptop is set to on your desk. Left alone, a send window
would silently drift by hours depending on where the process runs.

So: one place decides what "now" means, everything else asks it. The
timezone comes from `config.yaml → timezone` (or the `HUB_TIMEZONE` env
var), and these return *naive* datetimes carrying the local wall-clock
value so call sites can compare them without every one of them having to
become timezone-aware.

Audit stamps written and read purely in UTC (the `*_at` columns in
`store.py`) are correct as they are and deliberately stay UTC.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

log = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"

_tz: Optional[timezone | ZoneInfo] = None
_tz_name: str = ""


def set_timezone(name: str) -> None:
    """Point the whole hub at one IANA timezone (e.g. ``Asia/Tokyo``).

    Called once by `Config.load()`. An unknown name falls back to UTC with
    a loud warning rather than crashing the daemon — a bad config line
    should degrade the schedule, not take the box down.
    """
    global _tz, _tz_name
    name = (name or "").strip() or DEFAULT_TIMEZONE
    try:
        _tz = ZoneInfo(name)
        _tz_name = name
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Unknown timezone %r — falling back to UTC.", name)
        _tz = timezone.utc
        _tz_name = "UTC"


def timezone_name() -> str:
    _ensure()
    return _tz_name


def _ensure() -> None:
    if _tz is None:
        set_timezone(os.environ.get("HUB_TIMEZONE", "").strip() or DEFAULT_TIMEZONE)


def now() -> datetime:
    """Current local wall-clock time, as a naive datetime."""
    _ensure()
    return datetime.now(_tz).replace(tzinfo=None)


def today() -> date:
    """Current local calendar date."""
    return now().date()


def utc_stamp() -> str:
    """A UTC audit stamp for DB rows — comparable across machines."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Best-effort ISO parse that never raises — a corrupted state value
    should read as "no value", not kill the run."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def humanize_delta(then: Optional[datetime], reference: Optional[datetime] = None) -> str:
    """"3 min ago" / "2 days ago" — for logs and the dashboard."""
    if then is None:
        return "never"
    ref = reference or now()
    delta: timedelta = ref - then
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "in the future"
    for unit, size in (("day", 86400), ("hour", 3600), ("min", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"
