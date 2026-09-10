"""The scheduler is the part that's wrong in subtle ways for weeks before
you notice, so it gets the most tests: every one of these encodes a bug
that is easy to write and hard to spot in production."""
from __future__ import annotations

from datetime import datetime

import pytest

from src.schedule import Schedule, ScheduleError, parse_duration


# ── parsing ──
@pytest.mark.parametrize("spec,seconds", [
    ("30s", 30), ("15m", 900), ("4h", 14400), ("1d", 86400),
    ("90", 5400),        # a bare number means minutes
    (45, 2700),          # …including a real int from YAML
])
def test_parse_duration(spec, seconds):
    assert parse_duration(spec) == seconds


@pytest.mark.parametrize("spec", ["", "soon", "-5m", "0h", "5 weeks"])
def test_bad_durations_are_rejected_loudly(spec):
    # Loudly, at load time: a job that silently never runs is the worst
    # failure mode this repo has.
    with pytest.raises(ScheduleError):
        parse_duration(spec)


def test_shorthand_string_is_an_interval():
    assert Schedule.parse("15m") == Schedule.parse({"every": "15m"})


def test_schedule_needs_exactly_one_shape():
    with pytest.raises(ScheduleError):
        Schedule.parse({"every": "1h", "daily_at": "07:00"})
    with pytest.raises(ScheduleError):
        Schedule.parse({})


def test_weekly_spec_parsing():
    weekly = Schedule.parse({"weekly_at": "mon 08:00"})
    assert weekly.kind == "weekly" and weekly.weekday == 0
    assert weekly.at.hour == 8
    assert weekly.describe() == "Mon at 08:00"
    with pytest.raises(ScheduleError):
        Schedule.parse({"weekly_at": "someday 08:00"})


# ── interval ──
def test_interval_runs_immediately_when_never_run():
    # Not "wait one full interval first" — a fresh box should do something.
    assert Schedule.parse("1h").is_due(None, datetime(2026, 6, 1, 9, 0))


def test_interval_waits_out_its_period():
    schedule = Schedule.parse("1h")
    last = datetime(2026, 6, 1, 9, 0)
    assert not schedule.is_due(last, datetime(2026, 6, 1, 9, 59))
    assert schedule.is_due(last, datetime(2026, 6, 1, 10, 0))


# ── daily windows: catch-up, and never twice ──
def test_daily_not_due_before_the_hour():
    schedule = Schedule.parse({"daily_at": "07:00"})
    assert not schedule.is_due(None, datetime(2026, 6, 1, 6, 59))


def test_daily_due_at_the_hour():
    schedule = Schedule.parse({"daily_at": "07:00"})
    assert schedule.is_due(None, datetime(2026, 6, 1, 7, 0))


def test_daily_catches_up_after_downtime():
    """The box was off at 07:00 and booted at 11:00. A missed window is a
    late message, not a lost one."""
    schedule = Schedule.parse({"daily_at": "07:00"})
    yesterday = datetime(2026, 5, 31, 7, 0)
    assert schedule.is_due(yesterday, datetime(2026, 6, 1, 11, 0))


def test_daily_never_sends_twice_for_one_window():
    schedule = Schedule.parse({"daily_at": "07:00"})
    sent = datetime(2026, 6, 1, 7, 0)
    for hour in (7, 12, 18, 23):
        assert not schedule.is_due(sent, datetime(2026, 6, 1, hour, 30))
    # …and opens again the next day.
    assert schedule.is_due(sent, datetime(2026, 6, 2, 7, 0))


def test_yesterdays_late_send_does_not_satisfy_today():
    """Sent at 23:00 yesterday (a catch-up), so today's 07:00 must still
    fire — comparing against 'last 24h' instead of the boundary is the
    classic version of this bug."""
    schedule = Schedule.parse({"daily_at": "07:00"})
    assert schedule.is_due(datetime(2026, 5, 31, 23, 0), datetime(2026, 6, 1, 7, 30))


# ── weekly windows ──
def test_weekly_fires_on_its_day_and_not_before():
    schedule = Schedule.parse({"weekly_at": "mon 08:00"})
    monday_7am = datetime(2026, 6, 1, 7, 0)      # 2026-06-01 is a Monday
    assert not schedule.is_due(datetime(2026, 5, 25, 8, 0), monday_7am)
    assert schedule.is_due(datetime(2026, 5, 25, 8, 0), datetime(2026, 6, 1, 8, 0))


def test_weekly_stays_quiet_for_the_rest_of_the_week():
    schedule = Schedule.parse({"weekly_at": "mon 08:00"})
    sent = datetime(2026, 6, 1, 8, 0)
    assert not schedule.is_due(sent, datetime(2026, 6, 4, 12, 0))    # Thursday
    assert schedule.is_due(sent, datetime(2026, 6, 8, 8, 0))         # next Monday


def test_weekly_catches_up_later_in_the_week():
    """Box was off on Monday; it should still send when it comes back."""
    schedule = Schedule.parse({"weekly_at": "mon 08:00"})
    assert schedule.is_due(datetime(2026, 5, 25, 8, 0), datetime(2026, 6, 3, 9, 0))


# ── poll cadence ──
def test_poll_seconds():
    assert Schedule.parse("15m").poll_seconds() == 900
    # Window jobs wake often enough to make catch-up granular.
    assert Schedule.parse({"daily_at": "07:00"}).poll_seconds() == 900
