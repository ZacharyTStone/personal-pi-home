"""The runner's job is to make failure boring. These pin the guarantees
every job gets for free."""
from __future__ import annotations

import sys
import types

import pytest

from src.config import Config
from src.runner import run_due, run_job
from src.store import JobStore


@pytest.fixture
def fake_jobs(monkeypatch):
    """Register throwaway job modules for the duration of a test."""
    registry = {}
    monkeypatch.setattr("src.runner.all_jobs", lambda: registry)

    def add(name: str, run, **attrs):
        module = types.ModuleType(name)
        module.NAME = name
        module.SUMMARY = name
        module.SCHEDULE = attrs.pop("SCHEDULE", {"every": "1h"})
        module.ENABLED = attrs.pop("ENABLED", True)
        module.OPTIONS = attrs.pop("OPTIONS", {})
        module.run = run
        registry[name] = module
        return module

    return add


def _config(tmp_path) -> Config:
    return Config({"timezone": "UTC", "data_dir": str(tmp_path),
                   "notify": {"default_channels": ["console"]}}, path=None)


def test_a_job_that_raises_does_not_take_down_the_hub(fake_jobs, tmp_path):
    def explode(ctx):
        raise RuntimeError("upstream changed its HTML again")

    fake_jobs("exploding", explode)
    assert run_job("exploding", _config(tmp_path), force=True, dry_run=True) is False


def test_the_failure_is_recorded_so_a_broken_job_is_visible(fake_jobs, tmp_path):
    """A job quietly erroring for a week must not look like a healthy
    quiet job — that's what the runs table is for."""
    def explode(ctx):
        raise RuntimeError("boom")

    fake_jobs("exploding", explode)
    config = _config(tmp_path)
    run_job("exploding", config, force=True, dry_run=True)
    with JobStore(config.db_path("exploding")) as store:
        row = store.recent_runs()[0]
        assert row["status"] == "error" and "boom" in row["error"]


def test_a_failed_pass_leaves_the_schedule_window_open(fake_jobs, tmp_path):
    def explode(ctx):
        raise RuntimeError("the API was down")

    fake_jobs("flaky", explode)
    config = _config(tmp_path)
    run_job("flaky", config, force=True, dry_run=True)
    with JobStore(config.db_path("flaky")) as store:
        # No last_run → the next tick retries instead of skipping the day.
        assert store.last_run is None


def test_a_good_pass_consumes_the_window(fake_jobs, tmp_path):
    fake_jobs("fine", lambda ctx: None)
    config = _config(tmp_path)
    run_job("fine", config, force=True, dry_run=True)
    with JobStore(config.db_path("fine")) as store:
        assert store.last_run is not None


def test_a_job_that_is_not_due_is_skipped(fake_jobs, tmp_path):
    calls = []
    fake_jobs("counting", lambda ctx: calls.append(1))
    config = _config(tmp_path)
    assert run_job("counting", config, force=True, dry_run=True) is True
    assert run_job("counting", config, dry_run=True) is None      # not due yet
    assert len(calls) == 1


def test_unknown_job_is_reported_not_raised(fake_jobs, tmp_path):
    assert run_job("nope", _config(tmp_path), dry_run=True) is None


def test_one_bad_job_does_not_stop_the_others_in_a_sweep(fake_jobs, tmp_path):
    ran = []

    def explode(ctx):
        raise RuntimeError("nope")

    fake_jobs("bad", explode)
    fake_jobs("good", lambda ctx: ran.append("good"))
    results = run_due(_config(tmp_path), ["bad", "good"], dry_run=True)
    assert ran == ["good"]
    assert results == {"bad": False, "good": True}


def test_a_job_gets_its_own_database(fake_jobs, tmp_path):
    """Isolation: deleting one job's state must not touch another's."""
    fake_jobs("a", lambda ctx: ctx.store.set_meta("x", "1"))
    fake_jobs("b", lambda ctx: ctx.store.set_meta("x", "2"))
    config = _config(tmp_path)
    run_job("a", config, force=True, dry_run=True)
    run_job("b", config, force=True, dry_run=True)
    with JobStore(config.db_path("a")) as store:
        assert store.get_meta("x") == "1"


def test_job_options_come_from_config_merged_over_the_jobs_own_defaults(fake_jobs, tmp_path):
    seen = {}
    fake_jobs("tuned", lambda ctx: seen.update(ctx.options),
              OPTIONS={"threshold": 10, "label": "default"})
    config = Config({"timezone": "UTC", "data_dir": str(tmp_path),
                     "jobs": {"tuned": {"threshold": 99}}}, path=None)
    run_job("tuned", config, force=True, dry_run=True)
    assert seen == {"threshold": 99, "label": "default"}


def test_the_number_of_messages_sent_is_recorded(fake_jobs, tmp_path):
    """A quiet-but-healthy pass and a pass that did something must be
    distinguishable on the dashboard."""
    fake_jobs("chatty", lambda ctx: [ctx.send("a", "1"), ctx.send("b", "2")])
    config = _config(tmp_path)
    run_job("chatty", config, force=True, dry_run=True)
    with JobStore(config.db_path("chatty")) as store:
        assert store.recent_runs()[0]["sent"] == 2


def test_a_quiet_pass_records_zero_sends(fake_jobs, tmp_path):
    fake_jobs("quiet", lambda ctx: None)
    config = _config(tmp_path)
    run_job("quiet", config, force=True, dry_run=True)
    with JobStore(config.db_path("quiet")) as store:
        row = store.recent_runs()[0]
        assert row["status"] == "ok" and row["sent"] == 0
