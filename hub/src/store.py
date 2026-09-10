"""Per-job SQLite state: what we've seen, what we've sent, how runs went.

**One file per job** (`data/<job>.db`). Sharing one database would let a
schema change or a lock in one job affect another, and would make removing
a job's state a careful DELETE rather than an `rm`.

Four tables, created for every job whether it uses them or not:

* ``meta``  — key/value storage. Holds ``last_run``, which is what makes
  catch-up scheduling work.
* ``seen``  — deduplication, keyed on whatever stable id the job computes.
* ``sends`` — messages actually delivered; what the dashboard shows.
* ``runs``  — one row per attempt, including failures, so a job that has
  been erroring for a week is distinguishable from a job with nothing to
  report.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .clock import parse_iso, utc_stamp

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS seen (
    key        TEXT PRIMARY KEY,
    payload    TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_last ON seen(last_seen);

CREATE TABLE IF NOT EXISTS sends (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    subject  TEXT,
    preview  TEXT,
    channels TEXT,
    sent_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sends_at ON sends(sent_at);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,   -- 'running' | 'ok' | 'error'
    sent        INTEGER DEFAULT 0,
    detail      TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
"""


class JobStore:
    """SQLite state for one job. Use as a context manager."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        # WAL keeps the read-only dashboard from blocking a writing job.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "JobStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── meta: the key/value scratch space ──
    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def get_json(self, key: str, default: Any = None) -> Any:
        raw = self.get_meta(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default

    def set_json(self, key: str, value: Any) -> None:
        self.set_meta(key, json.dumps(value, ensure_ascii=False))

    # ── last_run: what the scheduler reads (see schedule.Schedule.is_due) ──
    @property
    def last_run(self) -> Optional[datetime]:
        return parse_iso(self.get_meta("last_run"))

    def mark_run(self, when: datetime) -> None:
        """Record a *successful* pass. Deliberately not written when a job
        errors: a failed fetch leaves the window open so the next tick
        retries, instead of eating the day's message."""
        self.set_meta("last_run", when.isoformat(timespec="seconds"))

    # ── seen: dedup ──
    def is_known(self, key: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM seen WHERE key = ?", (key,)
        ).fetchone() is not None

    def mark_seen(self, key: str, payload: Any = None) -> None:
        """Record that this item has been handled.

        `first_seen` is never overwritten, so an item that keeps appearing
        in a feed keeps its original date; `last_seen` moves forward so
        pruning can't age out something still live. Passing a payload
        again refreshes it — that's how an item goes from collected to
        sent without a second table.
        """
        stamp = utc_stamp()
        encoded = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        self.conn.execute(
            "INSERT INTO seen (key, payload, first_seen, last_seen) VALUES (?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET last_seen = excluded.last_seen,"
            " payload = COALESCE(excluded.payload, seen.payload)",
            (key, encoded, stamp, stamp),
        )
        self.conn.commit()

    def payload_of(self, key: str) -> Any:
        row = self.conn.execute("SELECT payload FROM seen WHERE key = ?", (key,)).fetchone()
        if row is None or not row["payload"]:
            return None
        try:
            return json.loads(row["payload"])
        except (TypeError, ValueError):
            return None

    def seen_rows(self, limit: int = 100) -> List[sqlite3.Row]:
        """Most-recently-first-seen rows, for jobs that queue items up."""
        return self.conn.execute(
            "SELECT key, payload, first_seen FROM seen ORDER BY first_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()

    # ── sends: the delivery audit log ──
    def record_send(self, subject: str, preview: str, channels: List[str]) -> None:
        self.conn.execute(
            "INSERT INTO sends (subject, preview, channels, sent_at) VALUES (?,?,?,?)",
            (subject, preview[:500], ",".join(channels), utc_stamp()),
        )
        self.conn.commit()

    def recent_sends(self, limit: int = 20) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM sends ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # ── runs: one row per attempt, successes and failures alike ──
    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
            (utc_stamp(),),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, status: str, sent: int = 0,
                   detail: Optional[Dict[str, Any]] = None,
                   error: Optional[str] = None) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, sent = ?, detail = ?,"
            " error = ? WHERE id = ?",
            (utc_stamp(), status, sent,
             json.dumps(detail or {}, ensure_ascii=False, default=str),
             error, run_id),
        )
        self.conn.commit()

    def recent_runs(self, limit: int = 20) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # ── housekeeping ──
    def prune(self, *, seen_days: int = 90, sends_days: int = 365,
              runs_days: int = 30) -> Dict[str, int]:
        """Keep the file small. Called by the runner after every pass, so
        an unattended box never grows a database it can't fit on its SD
        card. `seen` is pruned by *last* seen, so a still-live item can
        never age out and re-notify."""
        counts = {}
        for table, column, days in (("seen", "last_seen", seen_days),
                                    ("sends", "sent_at", sends_days),
                                    ("runs", "started_at", runs_days)):
            cur = self.conn.execute(
                f"DELETE FROM {table} WHERE {column} < datetime('now', ?)",
                (f"-{int(days)} days",),
            )
            counts[table] = cur.rowcount
        self.conn.commit()
        return counts

    def stats(self) -> Dict[str, Any]:
        def count(table: str) -> int:
            return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return {"seen": count("seen"), "sends": count("sends"), "runs": count("runs")}
