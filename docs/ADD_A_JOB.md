# Adding a job

This is the document that matters. Everything else in the repo exists so
that this stays short.

## The contract

One file in `hub/src/jobs/`. Five things:

```python
# hub/src/jobs/bin_day.py
"""Reminds me which bin goes out tonight."""

NAME = "bin_day"                          # id, config key, database filename
SUMMARY = "Which bin goes out tonight."   # shown by --list and the dashboard
SCHEDULE = {"daily_at": "19:00"}          # default; config.yaml can override
ENABLED = True                            # ship it on or off
OPTIONS = {"start_week": "recycling"}     # defaults, overridable in config.yaml


def run(ctx):
    which = "recycling" if ctx.now.isocalendar().week % 2 else "general waste"
    ctx.send("Bins", f"Tonight: {which} 🗑")
```

Drop it in. It's live:

```bash
python -m src.main --list
python -m src.main --run bin_day --dry-run
```

No base class, no decorator, no registry to edit — the list you have to
update by hand is the one that rots.

## What `ctx` gives you

| | |
|---|---|
| `ctx.now` | Local wall-clock time in your configured timezone. **Use this, never `datetime.now()`** — the container's clock is UTC. |
| `ctx.option(key, default)` | A knob from `config.yaml → jobs.<name>`, falling back to your `OPTIONS`. |
| `ctx.send(subject, text)` | Send a message. Where it goes is `config.yaml`'s business, not yours. |
| `ctx.get(url, params=…)` | GET some JSON, or `None` if anything went wrong. |
| `ctx.store` | This job's own SQLite file. Survives restarts and rebuilds. |
| `ctx.log` | A logger named for your job. |
| `ctx.dry_run` | True under `--dry-run`, if you need to behave differently. |

## The two rules

**Nothing to say? Just return.** Most passes of most jobs are quiet, and
that's the normal case rather than a failure. A hub that pings you to
confirm everything is fine is one you learn to ignore.

**Couldn't do the work? `raise`.** The hub logs it, records the failed
run so the dashboard shows it, leaves the schedule window open, and
carries on. The next tick retries. That's the entire error contract — no
result objects, no status codes.

```python
def run(ctx):
    data = ctx.get("https://api.example.com/thing")
    if data is None:
        raise RuntimeError("could not reach the API")   # retried next tick
    if not data["interesting"]:
        return                                          # nothing to say
    ctx.send("Thing", f"It's {data['value']} now")
```

Swallowing the error instead would mark the window served, and you'd get
nothing until tomorrow.

## Scheduling

```yaml
schedule: {every: 15m}               # poll:  15m / 4h / 1d
schedule: {daily_at: "07:00"}        # once a day
schedule: {weekly_at: "mon 08:00"}   # once a week
```

The two window shapes catch up after downtime — a missed 07:00 sends when
the box comes back — and never fire twice for the same window. You don't
have to do anything to get that; it's in `schedule.py`.

Pick `every` when you're watching for something that could happen at any
time. Pick `daily_at` / `weekly_at` when *you* want to be interrupted at a
particular hour.

## Remembering things

`ctx.store` is a SQLite file at `hub/data/<name>.db`, yours alone.

```python
count = int(ctx.store.get_meta("count", "0")) + 1
ctx.store.set_meta("count", str(count))

ctx.store.set_json("state", {"last_price": 42})
state = ctx.store.get_json("state", {})
```

For "have I already told them about this?", use the `seen` table — it's
what stops a hub from re-notifying you about the same thing forever:

```python
for item in items:
    if ctx.store.is_known(item["id"]):
        continue
    ctx.send("New thing", item["title"])
    ctx.store.mark_seen(item["id"])      # mark AFTER sending, not before
```

Mark it seen *after* you've sent. If you mark first and the send fails,
the item is gone for good; the other way round you might occasionally get
a duplicate, which is the failure you'd rather have.

Old rows are pruned automatically, so an unattended box won't fill its SD
card.

## Three shapes worth knowing

Most home-hub jobs are one of these.

**Daily push** — fetch something, decide something, say one useful thing.
Schedule with `daily_at`. Say the *decision*, not the data: not "17°C,
60% chance of rain" but "jacket, take the umbrella". A notification you
have to interpret is one you start ignoring.

```python
def run(ctx):
    data = ctx.get("https://api.example.com/forecast", params={"q": ctx.option("city")})
    if data is None:
        raise RuntimeError("forecast unavailable")     # retried next tick
    ctx.send("Weather", "Take a jacket." if data["high"] < 15 else "Shorts weather.")
```

Prefer APIs that need no key. A hub that needs five accounts set up is a
hub you never finish.

**Collect, then digest** — poll on a short `every` so nothing rolls off a
feed unseen, store what you find with `mark_seen`, and only send when
you've got enough to be worth an interruption. The split matters: if you
only look at digest time, you silently miss whatever scrolled past in
between, and you never find out.

**Threshold alert** — check often, stay silent, speak once when something
crosses a line. The trick is not to nag: record the level you last
alerted at, and only speak again when it gets materially worse.

```python
alerted = ctx.store.get_json("alerted", {})
if value > limit and value >= alerted.get("level", 0) + step:
    ctx.send("Over the line", f"{value} (limit {limit})")
    ctx.store.set_json("alerted", {"level": value})
elif value <= limit:
    ctx.store.set_json("alerted", {})       # recovered — arm it again
```

## Making it configurable

Everything in `OPTIONS` is overridable, and merged *under* the user's
config — so adding a new option to a job file can't break an existing
`config.yaml`:

```yaml
jobs:
  bin_day:
    enabled: true
    schedule: {daily_at: "20:00"}
    start_week: general waste
```

Put decisions in `config.yaml`. Put secrets in `.env` and read them with
`os.environ` — never in the file that gets committed.

## Testing it

Tests run with no network and no credentials, which is also the state a
fresh fork is in. Keep your rendering pure and it's easy:

```python
def test_odd_weeks_are_recycling(make_ctx, channel):
    from src.jobs import bin_day
    ctx = make_ctx("bin_day", bin_day.OPTIONS, now=datetime(2026, 1, 8, 19, 0))
    bin_day.run(ctx)
    assert "recycling" in channel.sent[0].text
```

`make_ctx` and `channel` are fixtures in `hub/tests/conftest.py` — a
context with a temp database, and a channel that captures messages
instead of sending them.

## Deleting a job

Delete the file, and drop its block from `config.yaml`. Its database in
`hub/data/` is then just a stale file you can remove whenever. That's the
other reason each job gets its own: cleaning up is `rm`, not a migration.
