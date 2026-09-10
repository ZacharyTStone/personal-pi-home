"""Job discovery: one module in this folder is one job.

There's no base class, no decorator and no registry to edit. A job is a
Python file with a `run(ctx)` function and a few constants:

    NAME     = "bin_day"                   # id, config key, database name
    SUMMARY  = "Which bin goes out tonight."
    SCHEDULE = {"daily_at": "19:00"}
    ENABLED  = True                        # ship it on or off
    OPTIONS  = {"start_week": "recycling"}  # defaults, overridable in config.yaml

    def run(ctx):
        ctx.send("Bins", "Tonight: recycling 🗑")

Drop the file in and it appears in `--list`, in `config.yaml` and on the
dashboard. Delete the file and it's gone. The list you have to update by
hand is the one that rots, so there isn't one.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import Dict

log = logging.getLogger(__name__)

_JOBS: Dict[str, ModuleType] = {}


def discover() -> Dict[str, ModuleType]:
    """Import every job module in this folder."""
    _JOBS.clear()
    for found in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if found.name.startswith("_") or found.name == "context":
            continue
        try:
            module = importlib.import_module(f"{__name__}.{found.name}")
        except Exception:  # noqa: BLE001 — one broken job file ≠ no hub
            log.exception("Could not load %r; skipping it.", found.name)
            continue
        name = getattr(module, "NAME", found.name)
        if not callable(getattr(module, "run", None)):
            log.warning("%s has no run(ctx) function; skipping it.", found.name)
            continue
        _JOBS[name] = module
    return dict(_JOBS)


def all_jobs() -> Dict[str, ModuleType]:
    return dict(_JOBS) if _JOBS else discover()


def get_job(name: str):
    return all_jobs().get(name)


discover()
