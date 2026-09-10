"""The dashboard is tested against *fixture databases it builds itself*,
not against a running hub.

That's the point of the two images not sharing code: the contract between
them is the SQLite schema, so the tests state that schema explicitly. If
the hub ever changes it, these fail — which is the warning you want.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mirrors hub/src/store.py.
SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE seen (key TEXT PRIMARY KEY, payload TEXT, first_seen TEXT NOT NULL,
                   last_seen TEXT NOT NULL);
CREATE TABLE sends (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT,
                    preview TEXT, channels TEXT, sent_at TEXT NOT NULL);
CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
                   finished_at TEXT, status TEXT NOT NULL, sent INTEGER DEFAULT 0,
                   detail TEXT, error TEXT);
"""


def make_job_db(path: Path, *, status: str = "ok", error: str = None,
                sends: int = 1) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO runs (started_at, finished_at, status, sent, detail, error)"
        " VALUES ('2026-06-01T09:00:00', '2026-06-01T09:00:02', ?, ?, '{}', ?)",
        (status, sends, error))
    for i in range(sends):
        conn.execute(
            "INSERT INTO sends (subject, preview, channels, sent_at)"
            " VALUES (?, 'body', 'console', '2026-06-01T09:00:01')",
            (f"Message {i}",))
    conn.execute("INSERT INTO meta (key, value) VALUES ('last_run', '2026-06-01T09:00:00')")
    conn.execute("INSERT INTO seen (key, payload, first_seen, last_seen)"
                 " VALUES ('k', '{}', '2026-06-01T09:00:00', '2026-06-01T09:00:00')")
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient pointed at a temp data dir and config."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(
        "hub_name: test-hub\ntimezone: UTC\n"
        "notify:\n  default_channels: [console]\n"
        "jobs:\n  hello:\n    enabled: true\n    schedule: {daily_at: '09:00'}\n",
        encoding="utf-8")

    import app as app_module
    monkeypatch.setattr(app_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(app_module, "CONFIG_PATH", config)
    monkeypatch.setattr(app_module, "LOG_PATH", data_dir / "hub.log")

    from fastapi.testclient import TestClient
    test_client = TestClient(app_module.app)
    test_client.data_dir = data_dir
    return test_client
