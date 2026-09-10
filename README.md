# personal-pi-home

Boilerplate for the always-on box in the corner of your flat.

Fork it, tell it where to reach you, and start adding small useful things
that happen on a schedule. It ships with **one job that does nothing** —
on purpose — a **status page**, and a **Docker setup**. Everything else is
yours to write.

**Fork it**, then:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home/hub
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m src.main --list                  # what's in the box
.venv/bin/python -m src.main --run hello --dry-run   # a real run, printed not sent
.venv/bin/python -m src.main --doctor                # what still needs setting up
```

No `.env`, no API keys, no Raspberry Pi needed. It runs, prints to your
terminal, and tells you what's missing. That's deliberate: you should see
the whole thing work before committing to setting anything up.

Then: [set up a channel and write a job](docs/SETUP.md) → [put it on a
box](docs/PI_SETUP.md) → [reach it from anywhere](docs/TAILSCALE.md).

---

## What you get

```
personal-pi-home/
├── docker-compose.yml     # the hub + the dashboard
├── .env.example           # secrets — copy to .env
├── hub/
│   ├── config.yaml        # ⭐ the file you actually edit
│   └── src/
│       ├── jobs/
│       │   └── hello.py   # ⭐ the only job — copy it
│       ├── notify/        # ntfy, Telegram, Discord, email, LINE, console
│       ├── schedule.py    # every / daily_at / weekly_at, with catch-up
│       ├── store.py       # per-job SQLite state
│       └── runner.py      # the loop
├── dashboard/             # read-only status page on :8090
├── scripts/deploy.sh      # pull from your fork, rebuild, restart
└── docs/                  # setup, channels, adding a job, design notes
```

### `hello` — the job that does nothing

It runs once a day, says hello, and stops. That sounds useless and for
the first twenty minutes it's the most useful thing here: if `hello`
shows up on the dashboard with a fresh timestamp, then the container is
up, the schedule is firing, the state volume is writable, the timezone is
the one you meant, and messages are reaching your phone. Each of those is
a thing that silently isn't true on somebody's first attempt.

Then you copy it and write the job you actually wanted.

---

## Writing a job

A job is one file in `hub/src/jobs/`. No base class, no decorator, no
registry to edit — drop the file in and it appears in `--list`, in
`config.yaml`, and on the dashboard.

```python
# hub/src/jobs/bin_day.py
NAME = "bin_day"
SUMMARY = "Which bin goes out tonight."
SCHEDULE = {"daily_at": "19:00"}
ENABLED = True
OPTIONS = {"start_week": "recycling"}

def run(ctx):
    which = "recycling" if ctx.now.isocalendar().week % 2 else "general waste"
    ctx.send("Bins", f"Tonight: {which} 🗑")
```

That's the whole contract. `ctx` gives you `now` (in your timezone),
`option()`, `send()`, `get()` for JSON APIs, `store` for anything that
must survive a restart, and `log`.

- **Nothing to say?** Just return. Most passes of most jobs are quiet.
- **Couldn't do the work?** `raise`. The hub records it and retries next
  tick rather than burning the day's window.

Full walkthrough: [`docs/ADD_A_JOB.md`](docs/ADD_A_JOB.md).

## Scheduling

```yaml
schedule: {every: 15m}               # poll — 15m / 4h / 1d
schedule: {daily_at: "07:00"}        # once a day
schedule: {weekly_at: "mon 08:00"}   # once a week
```

The two window shapes **catch up**: if the box was off at 07:00, the next
tick that day still sends — and never twice for the same window. That's
one of the few things here that's genuinely fiddly, so it's done once, in
`schedule.py`, with tests.

## Where notifications go

Set up whichever you'll actually read — one is enough:

**ntfy** (no account at all) · **Telegram** · **Discord** (one webhook
URL) · **email** · **LINE** · **console**

Jobs never name a channel. They call `ctx.send()`, and `config.yaml`
decides where it lands — so switching from Discord to Telegram is one
line, not a refactor. If nothing is configured, messages go to the log,
which is why a fresh clone works. See
[`docs/NOTIFIERS.md`](docs/NOTIFIERS.md).

---

## Running it on the box

```bash
cp .env.example .env      # fill in one channel
$EDITOR hub/config.yaml   # set your timezone, turn jobs on
docker compose up -d
```

Status page at `http://<its-ip>:8090` — what ran, what it sent, what
broke, and a live log tail. It mounts the data volume **read-only**, so
it can't corrupt the thing it's reporting on.

Then the loop is: write and test jobs on your laptop, `git push`, and on
the box `./scripts/deploy.sh` (pull, rebuild, restart) — or a cron line,
if you'd rather push and forget.

Same Python and same images on your laptop and on a Pi (they build for
arm64 too).

| | |
|---|---|
| [`docs/SETUP.md`](docs/SETUP.md) | Fork → channel → your first job → committed |
| [`docs/PI_SETUP.md`](docs/PI_SETUP.md) | A boxed Pi to a running hub, start to finish |
| [`docs/TAILSCALE.md`](docs/TAILSCALE.md) | Reaching it from anywhere — and why not to port-forward |
| [`docs/ADD_A_JOB.md`](docs/ADD_A_JOB.md) | The one that matters |
| [`docs/NOTIFIERS.md`](docs/NOTIFIERS.md) | Per-channel walkthroughs |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Why it's built this way |

## Tests

```bash
cd hub && python -m pytest -q          # 76 tests, no network, no keys
cd dashboard && python -m pytest -q
```

Offline **on purpose**: "works with an empty `.env`" is exactly the state
a fresh fork is in, so the suite is what keeps that state working.

---

## Five things this repo is opinionated about

Learned the annoying way. Longer version in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

1. **Silence is a feature.** A hub that pings you to say everything is
   fine is one you stop reading — and then it can't reach you when it
   matters.
2. **A missed window is a late message, not a lost one.** The box will be
   off sometimes. Schedules catch up; they never double-send.
3. **"Nothing works without keys" is a bug.** A fresh clone should do
   something real on the first run.
4. **One bad job must not take down the daemon.** Sources change their
   HTML and APIs get retired. A hub that dies at 3am stops being trusted.
5. **Decisions in git, secrets in `.env`.** `config.yaml` is committed, so
   its history is the story of how your hub got tuned.

## Licence

MIT — see [LICENSE](LICENSE). Make it yours.
