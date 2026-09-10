"""CLI entry point for the hub.

    python -m src.main --list                  # every job, on/off, schedule
    python -m src.main --doctor                # what's configured, what isn't
    python -m src.main --run hello --dry-run   # one job, now, printed not sent
    python -m src.main --once                  # every due job, once
    python -m src.main --loop                  # the daemon (what Docker runs)
    python -m src.main --loop hello bins       # …only these jobs

`--dry-run` needs no credentials at all — it prints instead of sending.
That's the first thing to try in a fresh fork, and it's what CI runs.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import List

from . import clock
from .config import Config, load_env
from .jobs import all_jobs
from .notify import build_router
from .runner import loop, run_due, run_job


def setup_logging(verbose: bool, log_path: Path, retention_days: int = 14) -> None:
    """Console at INFO (DEBUG with -v), plus a rotating DEBUG file.

    The file is DEBUG on purpose: when a job misbehaves you want the
    detailed per-source trail from *yesterday*, and you won't have thought
    to turn it on. Rotating daily and keeping N days makes that trail
    survive regardless of how chatty a day was.
    """
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt)

    handlers: List[logging.Handler] = [console]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_path, when="midnight", backupCount=max(1, retention_days),
            encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)
    except OSError as exc:  # read-only volume, full disk — still run
        console.handle(logging.LogRecord(
            "hub", logging.WARNING, __file__, 0,
            "No log file (%s); console only.", (exc,), None))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)      # the handlers do the filtering
    root.handlers[:] = handlers
    # Keep third-party chatter out of even the DEBUG file — we want our trail.
    for noisy in ("urllib3", "requests", "httpx", "httpcore", "anthropic", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def cmd_list(config: Config) -> int:
    registry = all_jobs()
    if not registry:
        print("No jobs found. Add one in hub/src/jobs/ — see docs/ADD_A_JOB.md.")
        return 0
    print(f"\n{config.hub_name} — {len(registry)} job(s), timezone {clock.timezone_name()}\n")
    for name, module in sorted(registry.items()):
        settings = config.settings_for(module)
        flag = "on " if settings.enabled else "off"
        summary = getattr(module, "SUMMARY", "")
        print(f"  [{flag}] {name:<12} {settings.schedule.describe():<18} {summary}")
    print("\nRun one now:  python -m src.main --run <name> --dry-run\n")
    return 0


def cmd_doctor(config: Config) -> int:
    """Tell a fresh fork exactly what it still needs — and what already works."""
    router = build_router(config.notify_cfg)
    print(f"\n{config.hub_name} — setup check\n")
    print(f"  config      {config.path if config.path else '(defaults)'}")
    print(f"  data dir    {config.data_dir}")
    print(f"  timezone    {clock.timezone_name()}   (local time now: "
          f"{clock.now():%Y-%m-%d %H:%M})")

    print("\n  channels")
    for name, ok in router.status().items():
        mark = "✔" if ok else "·"
        note = "" if ok else "  (not configured — see docs/NOTIFIERS.md)"
        print(f"    {mark} {name}{note}")
    print(f"    default route: {', '.join(router.default_channels)}")

    registry = all_jobs()
    enabled = config.enabled_job_names(registry)
    print(f"\n  jobs        {len(enabled)} enabled of {len(registry)}: "
          f"{', '.join(enabled) or 'none'}")
    live = [name for name, ok in router.status().items() if ok and name != "console"]
    if not live:
        print("\n  Nothing is wired to a real channel yet, so messages will print "
              "to the log.\n  That's a working hub — set up a channel in .env when "
              "you want it on your phone.")
    print()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="hub", description="personal-pi-home — your always-on box")
    parser.add_argument("--list", action="store_true",
                        help="list every job with its schedule and state")
    parser.add_argument("--doctor", action="store_true",
                        help="show what's configured and what's still missing")
    parser.add_argument("--run", metavar="JOB",
                        help="run one job now, ignoring its schedule")
    parser.add_argument("--once", action="store_true",
                        help="run every enabled job that is due, then exit")
    parser.add_argument("--loop", action="store_true",
                        help="run forever (this is what the container runs)")
    parser.add_argument("jobs", nargs="*",
                        help="limit --loop/--once to these jobs")
    parser.add_argument("--dry-run", action="store_true",
                        help="print messages instead of sending them")
    parser.add_argument("-c", "--config", metavar="PATH", help="config.yaml to use")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    load_env()
    config = Config.load(Path(args.config) if args.config else None)
    setup_logging(args.verbose, config.log_path, config.log_retention_days)

    if args.list:
        return cmd_list(config)
    if args.doctor:
        return cmd_doctor(config)

    if args.run:
        outcome = run_job(args.run, config, dry_run=args.dry_run, force=True)
        return 0 if outcome is not False else 1

    registry = all_jobs()
    names = args.jobs or config.enabled_job_names(registry)
    unknown = [n for n in names if n not in registry]
    if unknown:
        print(f"Unknown job(s): {', '.join(unknown)}. Try --list.", file=sys.stderr)
        return 2

    if args.loop:
        loop(config, names, dry_run=args.dry_run)
        return 0

    # Default: one sweep of everything due.
    run_due(config, names, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
