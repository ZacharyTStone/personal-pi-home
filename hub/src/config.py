"""config.yaml + .env — and the line between them.

The split is the important part, and it's the one thing to keep intact
when you fork this:

* **config.yaml** holds every *decision*: which jobs are on, when they
  run, where you live, what thresholds matter to you. It is committed. It
  is the file you actually edit, and its diff is the history of how your
  hub was tuned.
* **.env** holds every *secret*: tokens, passwords, API keys. It is
  gitignored, injected by Docker, and never read by anything except the
  channel or client that needs it.

So a job's config block can be shared, reviewed and version-controlled
without ever risking a credential leak — and `git log config.yaml` stays
readable.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import clock
from .schedule import Schedule, ScheduleError

log = logging.getLogger(__name__)

# hub/src/config.py → hub/ → repo root
_HUB_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _HUB_ROOT.parent

DEFAULT_CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "") or _HUB_ROOT / "config.yaml")
DEFAULT_DATA_DIR = Path(os.environ.get("DATA_DIR", "") or _HUB_ROOT / "data")


def load_env() -> None:
    """Load `.env` for bare local runs.

    Under Docker, compose injects these via `env_file`, so a missing file
    here is normal. Real environment variables always win over the file —
    that's what lets you override one value for a single command.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional at runtime
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)


class JobSettings:
    """One job's resolved settings: enabled, schedule, and its options."""

    def __init__(self, name: str, *, enabled: bool, schedule: Schedule,
                 options: Dict[str, Any]):
        self.name = name
        self.enabled = enabled
        self.schedule = schedule
        self.options = options

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "on" if self.enabled else "off"
        return f"<JobSettings {self.name} {state} {self.schedule.describe()}>"


class Config:
    """The parsed config.yaml, plus the job settings resolved against it."""

    def __init__(self, data: Dict[str, Any], path: Optional[Path] = None):
        self._data = data or {}
        self.path = path
        clock.set_timezone(self.timezone)

    @classmethod
    def load(cls, path: Path = None) -> "Config":
        path = Path(path or DEFAULT_CONFIG_PATH)
        if not path.exists():
            log.warning("No config at %s — running on defaults.", path)
            return cls({}, path)
        with open(path, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f) or {}, path)

    # ── top-level settings ──
    @property
    def timezone(self) -> str:
        return (os.environ.get("HUB_TIMEZONE", "").strip()
                or str(self._data.get("timezone", "") or "").strip()
                or clock.DEFAULT_TIMEZONE)

    @property
    def hub_name(self) -> str:
        """Shown on the dashboard and in email subjects. Name your box."""
        return str(self._data.get("hub_name", "") or "personal-pi-home")

    @property
    def data_dir(self) -> Path:
        configured = str(self._data.get("data_dir", "") or "").strip()
        return Path(os.environ.get("DATA_DIR", "") or configured or DEFAULT_DATA_DIR)

    @property
    def log_path(self) -> Path:
        return self.data_dir / "hub.log"

    @property
    def log_retention_days(self) -> int:
        raw = (os.environ.get("LOG_RETENTION_DAYS", "").strip()
               or str(self._data.get("logging", {}).get("retention_days", "")).strip())
        try:
            return max(1, int(raw)) if raw else 14
        except (TypeError, ValueError):
            return 14

    @property
    def notify_cfg(self) -> Dict[str, Any]:
        return self._data.get("notify", {}) or {}

    @property
    def jobs_cfg(self) -> Dict[str, Any]:
        return self._data.get("jobs", {}) or {}

    def db_path(self, job_name: str) -> Path:
        """One SQLite file per job — see store.JobStore for why."""
        return self.data_dir / f"{job_name}.db"

    # ── per-job resolution ──
    def settings_for(self, job_module) -> JobSettings:
        """Merge a job module's declared defaults with the user's config.

        Precedence, lowest to highest: the module's `OPTIONS`, then the
        `config.yaml → jobs.<name>` block. Merging rather than replacing
        is what lets a fork override the one threshold it cares about
        without restating every other knob — and means editing the job
        file to add a new option doesn't break anyone's config.
        """
        name = getattr(job_module, "NAME", "")
        block = self.jobs_cfg.get(name) or {}
        if not isinstance(block, dict):
            log.warning("jobs.%s should be a mapping — ignoring it.", name)
            block = {}

        options = dict(getattr(job_module, "OPTIONS", {}) or {})
        options.update({k: v for k, v in block.items()
                        if k not in ("enabled", "schedule")})

        fallback = getattr(job_module, "SCHEDULE", {"daily_at": "09:00"})
        try:
            schedule = Schedule.parse(block.get("schedule") or fallback)
        except ScheduleError as exc:
            log.error("jobs.%s.schedule is invalid (%s) — using the job's own "
                      "default instead.", name, exc)
            schedule = Schedule.parse(fallback)

        enabled = bool(block.get("enabled", getattr(job_module, "ENABLED", True)))
        return JobSettings(name, enabled=enabled, schedule=schedule, options=options)

    def enabled_job_names(self, registry: Dict[str, Any]) -> List[str]:
        return [name for name, module in sorted(registry.items())
                if self.settings_for(module).enabled]

    def raw(self) -> Dict[str, Any]:
        return dict(self._data)
