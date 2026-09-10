# Writing a job

A job is one file in `hub/src/jobs/`. It's discovered automatically —
there is no registry to edit.

```python
# hub/src/jobs/bin_day.py
"""Reminds me which bin goes out tonight."""

NAME = "bin_day"                          # id, config key, database filename
SUMMARY = "Which bin goes out tonight."   # shown in --list and the dashboard
SCHEDULE = {"daily_at": "19:00"}          # default; config.yaml can override
ENABLED = True                            # whether it's on by default
OPTIONS = {"start_week": "recycling"}     # defaults, overridable in config.yaml


def run(ctx):
    which = "recycling" if ctx.now.isocalendar().week % 2 else "general waste"
    ctx.send("Bins", f"Tonight: {which} 🗑")
```

```bash
python -m src.main --list
python -m src.main --run bin_day --dry-run
```

## The `ctx` object

| | |
|---|---|
| `ctx.now` | Local time in your configured timezone. Use this, not `datetime.now()` — the container clock is UTC. |
| `ctx.option(key, default)` | A value from `config.yaml → jobs.<name>`, falling back to `OPTIONS`. |
| `ctx.send(subject, text)` | Send a message. `config.yaml` decides the channel. |
| `ctx.get(url, params=…)` | GET and parse JSON. Returns `None` on any failure. |
| `ctx.store` | This job's SQLite database. See [State](#state). |
| `ctx.log` | A logger named for the job. |
| `ctx.dry_run` | True under `--dry-run`. |

## Return or raise

**Return without sending** when there's nothing to report. This is the
normal case for most jobs.

**Raise** when the job couldn't do its work. The hub logs it, records the
failed run for the dashboard, leaves the schedule window open, and
continues. The next tick retries.

```python
def run(ctx):
    data = ctx.get("https://api.example.com/thing")
    if data is None:
        raise RuntimeError("could not reach the API")   # retried next tick
    if not data["interesting"]:
        return                                          # nothing to report
    ctx.send("Thing", f"It's {data['value']} now")
```

Catching the error instead would mark the window as served, and the job
wouldn't run again until tomorrow.

## Schedules

```yaml
schedule: {every: 15m}               # 15m / 4h / 1d
schedule: {daily_at: "07:00"}
schedule: {weekly_at: "mon 08:00"}
```

`daily_at` and `weekly_at` catch up after downtime — a window missed while
the box was off fires when it comes back — and never fire twice for the
same window.

Use `every` when watching for something that can happen at any time. Use
`daily_at`/`weekly_at` when you want to be interrupted at a specific time.

## State

`ctx.store` is a SQLite file at `hub/data/<NAME>.db`, used only by this
job.

```python
count = int(ctx.store.get_meta("count", "0")) + 1
ctx.store.set_meta("count", str(count))

ctx.store.set_json("state", {"last_price": 42})
state = ctx.store.get_json("state", {})
```

For "have I already reported this?", use the `seen` table:

```python
for item in items:
    if ctx.store.is_known(item["id"]):
        continue
    ctx.send("New item", item["title"])
    ctx.store.mark_seen(item["id"])      # after sending, not before
```

Mark items seen *after* sending. If you mark first and the send fails, the
item is lost; the other order risks a duplicate, which is the better
failure.

Old rows are pruned automatically.

## Common patterns

**Daily push** — fetch, decide, send one message.

```python
SCHEDULE = {"daily_at": "07:00"}

def run(ctx):
    data = ctx.get("https://api.example.com/forecast",
                   params={"q": ctx.option("city")})
    if data is None:
        raise RuntimeError("forecast unavailable")
    ctx.send("Weather", "Take a jacket." if data["high"] < 15 else "Shorts weather.")
```

Send the conclusion rather than raw values. Prefer APIs that don't require
a key.

**Collect, then digest** — poll frequently so nothing is missed, but only
send on a schedule.

```python
SCHEDULE = {"every": "30m"}
OPTIONS = {"send_hours": [8, 20], "min_items": 3}

def run(ctx):
    # Collect on every tick.
    for item in fetch(ctx):
        if not ctx.store.is_known(item["id"]):
            ctx.store.mark_seen(item["id"], item)

    if not _window_open(ctx):
        return

    pending = [p for p in (ctx.store.payload_of(r["key"])
                           for r in ctx.store.seen_rows(50))
               if p and not p.get("sent")]
    if len(pending) < ctx.option("min_items", 3):
        return                                  # too few; wait for the next window

    ctx.send("Digest", "\n".join(p["title"] for p in pending))
    for item in pending:                        # mark sent only after delivery
        ctx.store.mark_seen(item["id"], {**item, "sent": True})
    ctx.store.set_meta("last_digest", ctx.now.isoformat())


def _window_open(ctx):
    """True once past a send hour that hasn't been served yet today."""
    from src.clock import parse_iso
    hours = [h for h in sorted(ctx.option("send_hours", [])) if ctx.now.hour >= h]
    if not hours:
        return False
    boundary = ctx.now.replace(hour=hours[-1], minute=0, second=0, microsecond=0)
    last = parse_iso(ctx.store.get_meta("last_digest"))
    return last is None or last < boundary
```

Two things this gets right:

- **Collecting every tick.** Feeds drop old items. Fetching only at digest
  time misses whatever scrolled past in between.
- **Tracking the last digest**, not just the current hour. On a 30-minute
  tick, checking `ctx.now.hour in send_hours` would send twice at 08:00
  and 08:30.

**Threshold alert** — check often, send once when a limit is crossed.

```python
SCHEDULE = {"every": "15m"}

def run(ctx):
    value = measure()
    limit, step = ctx.option("limit", 85), ctx.option("step", 5)
    alerted = ctx.store.get_json("alerted", {})

    if value > limit and value >= alerted.get("level", 0) + step:
        ctx.send("Over the line", f"{value} (limit {limit})")
        ctx.store.set_json("alerted", {"level": value})
    elif value <= limit and alerted:
        ctx.send("Recovered", f"Back to {value}")
        ctx.store.set_json("alerted", {})
```

Recording the level you last alerted at prevents repeat notifications
while a value hovers just over the limit.

## Configuration

Everything in `OPTIONS` is overridable. Config values are merged over the
defaults, so adding a new option to a job file won't break an existing
`config.yaml`:

```yaml
jobs:
  bin_day:
    enabled: true
    schedule: {daily_at: "20:00"}
    start_week: general waste
```

Settings go in `config.yaml`. Secrets go in `.env`, read with
`os.environ`.

## Testing

Tests run with no network and no credentials.

```python
def test_odd_weeks_are_recycling(make_ctx, channel):
    from src.jobs import bin_day
    ctx = make_ctx("bin_day", bin_day.OPTIONS, now=datetime(2026, 1, 8, 19, 0))
    bin_day.run(ctx)
    assert "recycling" in channel.sent[0].text
```

`make_ctx` and `channel` are fixtures in `hub/tests/conftest.py`: a context
with a temporary database, and a channel that captures messages instead of
sending them.

## Deploying a new job

On the box, job code is baked into the image, so a new or edited job needs
a rebuild:

```bash
./scripts/deploy.sh                  # pull, rebuild, restart
# or
docker compose up -d --build
```

Editing `config.yaml` alone only needs `docker compose restart hub`.

## Removing a job

Delete the file and its `config.yaml` block. Its database in `hub/data/`
becomes an unused file you can delete whenever.
