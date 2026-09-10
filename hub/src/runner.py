"""The loop that keeps the box useful — and keeps it alive.

Everything a job doesn't have to think about happens here.

**A job that raises is a job that retries.** That's the whole error
contract: if you can't do your work, raise. The hub logs it, records the
failed run so the dashboard shows it, leaves the schedule window open,
and moves on. Nothing else in the process notices.

That last part matters more than it sounds. Sources change their HTML,
APIs get retired, and the job you added at midnight has a typo in it. A
hub that dies at 3am because one feed went away is worse than no hub: you
stop trusting it, and then you stop noticing when the *other* jobs stop
too.

**A failed pass doesn't consume the window.** `last_run` is only written
after a clean pass, so a job that couldn't fetch at 07:00 sends at 07:15
instead of skipping the day.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from . import clock
from .config import Config
from .jobs import all_jobs
from .jobs.context import JobContext
from .notify import Router, build_router
from .store import JobStore

log = logging.getLogger(__name__)

# Never sleep longer than this, so a long-interval job still logs a
# heartbeat and a restart is noticed promptly.
MAX_SLEEP_SECONDS = 300


def run_job(name: str, config: Config, *, router: Optional[Router] = None,
            dry_run: bool = False, force: bool = False) -> Optional[bool]:
    """Run one job if it's due (or forced).

    Returns True on a clean pass, False if the job failed, None if it
    wasn't due. Never raises — the caller is usually a daemon that has to
    survive whatever the job did.
    """
    module = all_jobs().get(name)
    if module is None:
        log.error("No job named %r. Try --list.", name)
        return None

    settings = config.settings_for(module)
    router = router or build_router(config.notify_cfg, dry_run=dry_run)
    now = clock.now()

    with JobStore(config.db_path(name)) as store:
        if not force and not settings.schedule.is_due(store.last_run, now):
            log.debug("[%s] not due (%s, last run %s).", name,
                      settings.schedule.describe(),
                      clock.humanize_delta(store.last_run, now))
            return None

        ctx = JobContext(name=name, options=settings.options, store=store,
                         notify=router.for_job(name), now=now, dry_run=dry_run)

        run_id = store.start_run()
        try:
            module.run(ctx)
        except Exception as exc:  # noqa: BLE001 — one bad job ≠ a dead hub
            log.exception("[%s] failed; the hub keeps running.", name)
            store.finish_run(run_id, status="error",
                             error=f"{type(exc).__name__}: {exc}")
            # Window deliberately left open: the next tick retries.
            return False

        store.finish_run(run_id, status="ok", sent=ctx.sent)
        store.mark_run(now)
        store.prune()
        log.info("[%s] ok — %d message(s) sent.", name, ctx.sent)
        return True


def run_due(config: Config, names: List[str], *, router: Optional[Router] = None,
            dry_run: bool = False) -> Dict[str, bool]:
    """One sweep: run every named job that's due right now."""
    router = router or build_router(config.notify_cfg, dry_run=dry_run)
    results: Dict[str, bool] = {}
    for name in names:
        outcome = run_job(name, config, router=router, dry_run=dry_run)
        if outcome is not None:
            results[name] = outcome
    return results


def loop(config: Config, names: List[str], *, dry_run: bool = False) -> None:
    """Run forever: sweep, sleep, repeat.

    One process ticking a handful of jobs is the right default for a small
    box — a few MB of RAM rather than a container each. If you ever want a
    job isolated so it can restart on its own, give it a second compose
    service with `--loop <name>`; the code is identical either way.
    """
    if not names:
        log.warning("No jobs enabled — nothing to do. Check config.yaml → jobs.")
        return

    registry = all_jobs()
    tick = min((config.settings_for(registry[n]).schedule.poll_seconds()
                for n in names if n in registry), default=MAX_SLEEP_SECONDS)
    tick = max(30, min(tick, MAX_SLEEP_SECONDS))

    router = build_router(config.notify_cfg, dry_run=dry_run)
    live = [name for name, ok in router.status().items() if ok]
    log.info("Starting hub: %d job(s) [%s], ticking every %ds, channels: %s",
             len(names), ", ".join(names), tick, ", ".join(live))

    while True:
        started = time.monotonic()
        for name in names:
            run_job(name, config, router=router, dry_run=dry_run)
        time.sleep(max(1.0, tick - (time.monotonic() - started)))
