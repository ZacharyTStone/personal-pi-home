"""When a job is allowed to run.

Three shapes cover essentially everything an always-on box wants to do,
and each one is a single line in `config.yaml`:

    schedule: {every: 15m}          # poll  — "check often"
    schedule: {daily_at: "07:00"}   # daily — "once a day, in the morning"
    schedule: {weekly_at: "mon 08:00"}  # weekly — "Monday's report"

The two window shapes (`daily_at` / `weekly_at`) implement the behaviour
that took the longest to get right in practice:

* **Catch-up, not skip.** If the box was off (or the network was down) at
  07:00, the next tick that day still sends. A missed window is a late
  message, not a lost one.
* **Never twice.** Once a window has been served, it stays served until
  the next boundary — no matter how often the loop ticks.

That's why `is_due()` takes the *last successful run*, not a countdown:
state lives in the job's SQLite file, so a restart can't replay or lose a
window either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional

_WEEKDAYS = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])?\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# How often a window-shaped job's loop wakes up just to *notice* that its
# window has opened. Most of those passes do nothing, which is the point:
# it makes catch-up granular without making the job expensive.
WINDOW_POLL_SECONDS = 15 * 60


class ScheduleError(ValueError):
    """A schedule spec that can't be parsed. Raised at load time, loudly,
    because a job that silently never runs is the worst failure mode."""


def parse_duration(value: Any, *, field: str = "every") -> int:
    """``"15m"`` / ``"4h"`` / ``90`` (bare number = minutes) → seconds."""
    if isinstance(value, (int, float)):
        return max(1, int(value) * 60)
    match = _DURATION_RE.match(str(value))
    if not match:
        raise ScheduleError(f"{field}: cannot read duration {value!r} (try '15m', '4h', '1d')")
    amount, unit = int(match.group(1)), (match.group(2) or "m").lower()
    if amount <= 0:
        raise ScheduleError(f"{field}: duration must be positive, got {value!r}")
    return amount * _UNIT_SECONDS[unit]


def _parse_clock(value: Any, *, field: str) -> time:
    text = str(value).strip()
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?$", text)
    if not match:
        raise ScheduleError(f"{field}: cannot read a time from {value!r} (try '07:00')")
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ScheduleError(f"{field}: {value!r} is not a valid time of day")
    return time(hour=hour, minute=minute)


@dataclass(frozen=True)
class Schedule:
    """A parsed schedule. Build one with `Schedule.parse()`."""

    kind: str                      # "interval" | "daily" | "weekly"
    interval_seconds: int = 0      # interval only
    at: time = time(0, 0)          # daily / weekly only
    weekday: int = 0               # weekly only (0 = Monday)

    # ── construction ──
    @classmethod
    def parse(cls, spec: Any) -> "Schedule":
        """Read a schedule out of config. Accepts the mapping form
        (``{daily_at: "07:00"}``) or the shorthand string (``"15m"``)."""
        if spec is None:
            raise ScheduleError("missing schedule")
        if isinstance(spec, str):
            spec = {"every": spec}
        if not isinstance(spec, dict):
            raise ScheduleError(f"cannot read schedule from {spec!r}")

        keys = [k for k in ("every", "daily_at", "weekly_at") if spec.get(k) is not None]
        if len(keys) != 1:
            raise ScheduleError(
                "schedule needs exactly one of every / daily_at / weekly_at, "
                f"got {sorted(spec)}"
            )
        key = keys[0]
        if key == "every":
            return cls(kind="interval",
                       interval_seconds=parse_duration(spec["every"]))
        if key == "daily_at":
            return cls(kind="daily", at=_parse_clock(spec["daily_at"], field="daily_at"))

        raw = str(spec["weekly_at"]).strip()
        parts = raw.split()
        if len(parts) != 2 or parts[0].lower() not in _WEEKDAYS:
            raise ScheduleError(
                f"weekly_at: expected '<day> <hh:mm>' like 'mon 08:00', got {raw!r}"
            )
        return cls(kind="weekly",
                   at=_parse_clock(parts[1], field="weekly_at"),
                   weekday=_WEEKDAYS[parts[0].lower()])

    # ── the two questions the runner asks ──
    def is_due(self, last_run: Optional[datetime], now: datetime) -> bool:
        """Should this job run on this tick?"""
        if self.kind == "interval":
            if last_run is None:
                return True     # never run → run now, don't wait a full interval
            return (now - last_run).total_seconds() >= self.interval_seconds
        boundary = self.window_start(now)
        if boundary is None:
            return False        # today's window hasn't opened yet
        return last_run is None or last_run < boundary

    def poll_seconds(self) -> int:
        """How long the loop may sleep before it must look again."""
        if self.kind == "interval":
            return max(1, self.interval_seconds)
        return WINDOW_POLL_SECONDS

    # ── helpers ──
    def window_start(self, now: datetime) -> Optional[datetime]:
        """The most recent boundary at or before `now`, or None if the
        current one hasn't opened yet (window shapes only)."""
        if self.kind == "daily":
            boundary = datetime.combine(now.date(), self.at)
            return boundary if now >= boundary else None
        if self.kind == "weekly":
            days_since = (now.weekday() - self.weekday) % 7
            day: date = now.date() - timedelta(days=days_since)
            boundary = datetime.combine(day, self.at)
            if now >= boundary:
                return boundary
            # Today is the right weekday but it's still before the hour —
            # the live window is last week's.
            return boundary - timedelta(days=7) if days_since == 0 else None
        return None

    def describe(self) -> str:
        if self.kind == "interval":
            seconds = self.interval_seconds
            for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
                if seconds >= size and seconds % size == 0:
                    return f"every {seconds // size}{unit}"
            return f"every {seconds}s"
        clock = self.at.strftime("%H:%M")
        if self.kind == "daily":
            return f"daily at {clock}"
        return f"{_WEEKDAY_NAMES[self.weekday]} at {clock}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable form — what the dashboard shows."""
        return {"kind": self.kind, "describe": self.describe()}
