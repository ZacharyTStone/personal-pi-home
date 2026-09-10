"""Example job: runs daily, does nothing.

Its purpose is to confirm the setup works. If `hello` appears on the
dashboard with a recent timestamp, then the container is running, the
schedule is firing, the state volume is writable, the timezone is correct,
and messages are being delivered.

Copy this file to write your first real job. See docs/ADD_A_JOB.md.
"""
from __future__ import annotations

# ── the four constants that make a file a job ────────────────────────
NAME = "hello"
SUMMARY = "Does nothing, daily. Proves the wiring works."
SCHEDULE = {"daily_at": "09:00"}
ENABLED = True

# Defaults for this job's settings. Anything here can be overridden in
# config.yaml → jobs.hello, and is read below with ctx.option().
OPTIONS = {
    "greeting": "Hello from your hub",
}


def run(ctx) -> None:
    """Do the work, and send a message if there's something to report.

    The return value is ignored. Return without sending when there's
    nothing to say — that's the normal case for most jobs. Raise if the
    job couldn't do its work: the failure is recorded and the next tick
    retries, instead of consuming today's schedule window.
    """
    # ctx.store is this job's own SQLite file, at hub/data/hello.db.
    # Its contents survive restarts, rebuilds and image changes.
    count = int(ctx.store.get_meta("count", "0")) + 1
    ctx.store.set_meta("count", str(count))

    # ctx.now is local time in the configured timezone, not the
    # container's UTC clock.
    text = (f"{ctx.option('greeting')} 👋\n"
            f"It is {ctx.now:%A %d %B, %H:%M}.\n"
            f"Run number {count}.")

    # The destination is set in config.yaml → notify. The job doesn't know
    # whether this is Telegram, email or the log.
    ctx.send(ctx.option("greeting"), text)
