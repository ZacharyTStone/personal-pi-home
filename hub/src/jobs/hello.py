"""EXAMPLE JOB — the smallest one that can possibly work. Start here.

It runs once a day and does nothing: says hello, counts how many times it
has said hello, stops.

That sounds pointless, and for the first twenty minutes it's the most
useful file in the repo. It answers the only question that matters when
you first stand a box up: **is the plumbing working?** If `hello` turns
up on the dashboard with a fresh timestamp, then the container is
running, the schedule is firing, the state volume is writable, the
timezone is the one you meant, and messages are reaching your phone.
Every one of those silently isn't true on somebody's first attempt.

Copy this file when you write your first real job. Delete it when you've
got two you care about — or keep it: a daily heartbeat is a cheap way to
notice the box has quietly died.
"""
from __future__ import annotations

# ── the four things that make a file a job ───────────────────────────
NAME = "hello"
SUMMARY = "Does nothing, daily. Proves the wiring works."
SCHEDULE = {"daily_at": "09:00"}
ENABLED = True

# Defaults for this job's knobs. Anything here can be overridden in
# config.yaml → jobs.hello, and read below with ctx.option().
OPTIONS = {
    "greeting": "Hello from your hub",
}


def run(ctx) -> None:
    """Do the thing. Send a message if there's something to say.

    Return value is ignored. Say nothing by simply returning — most passes
    of most jobs have nothing to report, and that's the normal case, not a
    failure. If you *couldn't* do your work (the API was down), raise: the
    hub records the failure and retries on the next tick instead of
    burning today's window.
    """
    # ctx.store is this job's own SQLite file. What you put in it survives
    # restarts, rebuilds, and image changes.
    count = int(ctx.store.get_meta("count", "0")) + 1
    ctx.store.set_meta("count", str(count))

    # ctx.now is local wall-clock time in your configured timezone.
    text = (f"{ctx.option('greeting')} 👋\n"
            f"It is {ctx.now:%A %d %B, %H:%M}.\n"
            f"Run number {count}. Nothing else happened, which is exactly "
            f"what was supposed to happen.")

    # Where this goes is config.yaml's business (notify → routes). The job
    # doesn't know whether it's Telegram, email or the log, which is what
    # makes switching one line instead of a refactor.
    ctx.send(ctx.option("greeting"), text)
