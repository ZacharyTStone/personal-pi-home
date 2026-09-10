"""State is what separates a hub from a cron job that spams you. These
tests pin the behaviours that keep it from double-notifying, forgetting,
or filling the SD card."""
from __future__ import annotations

from datetime import datetime

from src.store import JobStore


def test_meta_roundtrip(store: JobStore):
    assert store.get_meta("missing") is None
    assert store.get_meta("missing", "fallback") == "fallback"
    store.set_meta("key", "value")
    assert store.get_meta("key") == "value"
    store.set_meta("key", "updated")       # upsert, not a duplicate row
    assert store.get_meta("key") == "updated"


def test_json_meta_survives_garbage(store: JobStore):
    store.set_json("state", {"a": 1, "b": [2, 3]})
    assert store.get_json("state") == {"a": 1, "b": [2, 3]}
    store.set_meta("state", "not json at all")
    # A corrupted value reads as "no value" rather than crashing a run.
    assert store.get_json("state", {}) == {}


def test_last_run_is_only_written_on_success(store: JobStore):
    assert store.last_run is None
    when = datetime(2026, 6, 1, 7, 0)
    store.mark_run(when)
    assert store.last_run == when


def test_seen_dedup(store: JobStore):
    assert not store.is_known("abc")
    store.mark_seen("abc", {"title": "hello"})
    assert store.is_known("abc")
    assert store.payload_of("abc") == {"title": "hello"}


def test_reseeing_an_item_keeps_first_seen_but_can_update_payload(store: JobStore):
    store.mark_seen("abc", {"sent": False})
    first = store.conn.execute(
        "SELECT first_seen FROM seen WHERE key='abc'").fetchone()["first_seen"]
    store.mark_seen("abc", {"sent": True})
    row = store.conn.execute(
        "SELECT first_seen FROM seen WHERE key='abc'").fetchone()
    assert row["first_seen"] == first        # position in the queue is stable
    assert store.payload_of("abc") == {"sent": True}


def test_marking_seen_without_a_payload_does_not_erase_it(store: JobStore):
    store.mark_seen("abc", {"title": "keep me"})
    store.mark_seen("abc")                   # a bare "still there" touch
    assert store.payload_of("abc") == {"title": "keep me"}


def test_runs_record_failures_too(store: JobStore):
    run_id = store.start_run()
    store.finish_run(run_id, status="error", error="boom")
    row = store.recent_runs()[0]
    assert row["status"] == "error" and row["error"] == "boom"
    assert row["finished_at"] is not None


def test_run_in_progress_has_no_finish(store: JobStore):
    store.start_run()
    assert store.recent_runs()[0]["status"] == "running"
    assert store.recent_runs()[0]["finished_at"] is None


def test_sends_are_logged_with_their_channels(store: JobStore):
    store.record_send("Subject", "a long body " * 100, ["telegram", "email"])
    row = store.recent_sends()[0]
    assert row["subject"] == "Subject"
    assert row["channels"] == "telegram,email"
    assert len(row["preview"]) <= 500       # bounded, so the DB stays small


def test_prune_keeps_recent_and_drops_old(store: JobStore):
    store.mark_seen("fresh", {"x": 1})
    store.conn.execute(
        "INSERT INTO seen (key, payload, first_seen, last_seen)"
        " VALUES ('stale', NULL, '2000-01-01T00:00:00', '2000-01-01T00:00:00')")
    store.conn.commit()
    counts = store.prune(seen_days=30)
    assert counts["seen"] == 1
    assert store.is_known("fresh") and not store.is_known("stale")


def test_stats(store: JobStore):
    store.mark_seen("a")
    store.record_send("s", "t", ["console"])
    assert store.stats() == {"seen": 1, "sends": 1, "runs": 0}
