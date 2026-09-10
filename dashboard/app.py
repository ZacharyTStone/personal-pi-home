"""A read-only window into the hub.

Its own container, its own image, and — this is the part that matters —
the data volume is mounted **read-only**. The dashboard physically cannot
write to a job's state. That constraint is deliberate: a status page is
the thing you leave open on a tablet in the kitchen and hand to whoever
asks "is it working?", and it should be impossible for it to corrupt the
thing it's reporting on.

It reads what `hub/src/store.py` writes: one SQLite file per job, plus
the rotating log. There's no shared code between the two images on
purpose — the dashboard understands the *schema*, not the hub's Python,
so you can restart, rebuild, or rewrite either one without the other
noticing.

    DATA_DIR=hub/data uvicorn app:app --reload --port 8090
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/app/config.yaml"))
LOG_PATH = Path(os.environ.get("LOG_PATH", "")) if os.environ.get("LOG_PATH") \
    else DATA_DIR / "hub.log"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="personal-pi-home dashboard")


# ── config (read-only, the same file the hub reads) ──
def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}


# ── job databases (read-only URIs — see the module docstring) ──
def job_names() -> List[str]:
    if not DATA_DIR.exists():
        return []
    return sorted(p.stem for p in DATA_DIR.glob("*.db"))


def connect(job: str) -> Optional[sqlite3.Connection]:
    path = DATA_DIR / f"{job}.db"
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    """Tolerate a table a newer hub hasn't created yet: this connection is
    read-only and can't migrate anything, so an unknown table is 'no rows',
    not a 500 on the page you check when things are already broken."""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return []
        raise


def _rows(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def _age_seconds(stamp: Optional[str]) -> Optional[float]:
    """Rows are stamped in UTC (store.utc_stamp), so age is comparable no
    matter what timezone the dashboard container thinks it's in."""
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc).replace(tzinfo=None) - then).total_seconds()


# ── API ──
@app.get("/api/status")
def status() -> Dict[str, Any]:
    """Everything the page needs, in one request."""
    config = load_config()
    jobs_cfg = config.get("jobs", {}) or {}
    jobs: List[Dict[str, Any]] = []

    for name in job_names():
        conn = connect(name)
        if conn is None:
            continue
        with conn:
            runs = _rows(query(conn, "SELECT * FROM runs ORDER BY id DESC LIMIT 5"))
            sends = _rows(query(conn, "SELECT * FROM sends ORDER BY id DESC LIMIT 5"))
            meta = {r["key"]: r["value"] for r in query(conn, "SELECT * FROM meta")}
            counts = {}
            for table in ("seen", "sends", "runs"):
                found = query(conn, f"SELECT COUNT(*) AS n FROM {table}")
                counts[table] = found[0]["n"] if found else 0

        last = runs[0] if runs else None
        block = jobs_cfg.get(name) or {}
        jobs.append({
            "name": name,
            "enabled": bool(block.get("enabled", True)),
            "schedule": _describe_schedule(block.get("schedule")),
            "last_run": last,
            "last_run_age": _age_seconds(last["started_at"]) if last else None,
            # A job whose last run errored is the one thing this page exists
            # to make obvious.
            "healthy": bool(last and last.get("status") == "ok"),
            "runs": runs,
            "sends": sends,
            "counts": counts,
            "last_success": meta.get("last_run"),
        })

    return {
        "hub_name": config.get("hub_name", "personal-pi-home"),
        "timezone": config.get("timezone", "UTC"),
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(
            timespec="seconds"),
        "jobs": jobs,
    }


@app.get("/api/jobs/{name}")
def job_detail(name: str) -> Dict[str, Any]:
    conn = connect(name)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"No state for job {name!r}")
    with conn:
        return {
            "name": name,
            "runs": _rows(query(conn, "SELECT * FROM runs ORDER BY id DESC LIMIT 50")),
            "sends": _rows(query(conn, "SELECT * FROM sends ORDER BY id DESC LIMIT 50")),
            "meta": {r["key"]: r["value"] for r in query(conn, "SELECT * FROM meta")},
        }


@app.get("/api/log")
def log_tail(lines: int = 200) -> Dict[str, Any]:
    """Last N lines of the hub log — the thing you actually want at 2am."""
    if not LOG_PATH.exists():
        return {"path": str(LOG_PATH), "lines": []}
    lines = max(1, min(int(lines), 2000))
    try:
        # Read the tail rather than the file: a DEBUG log on a busy box is
        # large, and the page must stay cheap enough to poll.
        with open(LOG_PATH, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            window = min(size, 256 * 1024)
            handle.seek(size - window)
            text = handle.read().decode("utf-8", errors="replace")
        return {"path": str(LOG_PATH), "lines": text.splitlines()[-lines:]}
    except OSError as exc:
        return {"path": str(LOG_PATH), "lines": [f"(cannot read log: {exc})"]}


@app.get("/api/config")
def config_summary() -> Dict[str, Any]:
    """The committed config, minus anything that could be a secret.

    Nothing secret is *supposed* to be in config.yaml — that's the whole
    split described in hub/src/config.py — but this page may well end up
    exposed further than you intended, so it doesn't rely on that.
    """
    config = load_config()
    return {k: v for k, v in config.items() if k not in ("notify",)} | {
        "notify": {"default_channels":
                   (config.get("notify", {}) or {}).get("default_channels", [])},
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def _describe_schedule(spec: Any) -> str:
    """Mirrors hub/src/schedule.Schedule.describe() for display.

    Duplicated rather than imported: the dashboard is a separate image
    with its own dependencies, and coupling the two would mean they have
    to be deployed together forever.
    """
    if not spec:
        return "—"
    if isinstance(spec, str):
        return f"every {spec}"
    if isinstance(spec, dict):
        if spec.get("every"):
            return f"every {spec['every']}"
        if spec.get("daily_at"):
            return f"daily at {spec['daily_at']}"
        if spec.get("weekly_at"):
            return str(spec["weekly_at"])
    return "—"
