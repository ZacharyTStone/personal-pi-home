# personal-pi-home

Boilerplate for a Raspberry Pi (or any always-on box) that runs scheduled
jobs and sends you the results. Extracted from a personal Pi hub running
10+ jobs.

Ships with one example job, a status page, and a Docker setup. You add
the jobs.

## Try it

Fork on GitHub, then:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home/hub
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m src.main --list
.venv/bin/python -m src.main --run hello --dry-run
```

```
my-pi-home — 1 job(s), timezone UTC (local time now: 09:14)

        JOB          SCHEDULE           NEXT       LAST RUN     WHAT IT DOES
  [on ] hello        daily at 09:00     in 23h     just now     Does nothing, daily. Proves the wiring works.
```

Works with no `.env` and no API keys — messages print to the terminal
until you configure a channel.

**Next: [SETUP.md](docs/SETUP.md).**

## Writing a job

One file in `hub/src/jobs/`. It's picked up automatically — no registry
to edit.

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

`ctx` provides:

| | |
|---|---|
| `ctx.now` | Local time in your configured timezone |
| `ctx.option(key, default)` | A value from `config.yaml`, falling back to `OPTIONS` |
| `ctx.send(subject, text)` | Send a message; `config.yaml` decides the channel |
| `ctx.get(url, params=…)` | GET JSON, or `None` on failure |
| `ctx.store` | Per-job SQLite: `get_meta`/`set_meta`, `is_known`/`mark_seen` |
| `ctx.log` | Logger |

Return without sending if there's nothing to report. `raise` if the job
couldn't do its work — it's recorded and retried on the next tick.

Schedules:

```yaml
schedule: {every: 15m}               # poll
schedule: {daily_at: "07:00"}        # once a day
schedule: {weekly_at: "mon 08:00"}   # once a week
```

`daily_at` and `weekly_at` catch up after downtime and never fire twice
for the same window.

Details: [ADD_A_JOB.md](docs/ADD_A_JOB.md).

## Notification channels

ntfy, Telegram, Discord, email, LINE, console. Configure one or more in
`.env`; route per job in `config.yaml`. Jobs never name a channel.
Unconfigured channels are skipped; if none are configured, messages go to
the log.

Setup for each: [NOTIFIERS.md](docs/NOTIFIERS.md).

## Layout

```
personal-pi-home/
├── docker-compose.yml     # hub + dashboard
├── .env.example           # secrets — copy to .env
├── hub/
│   ├── config.yaml        # jobs, schedules, routing — you edit this
│   └── src/
│       ├── jobs/hello.py  # the example job
│       ├── notify/        # the channels
│       ├── schedule.py    # every / daily_at / weekly_at
│       ├── store.py       # per-job SQLite state
│       └── runner.py      # the loop
├── dashboard/             # read-only status page on :8090
├── scripts/deploy.sh      # pull, rebuild, restart
└── docs/
```

| Doc | |
|---|---|
| [SETUP.md](docs/SETUP.md) | Start here: fork → channel → first job |
| [PI_SETUP.md](docs/PI_SETUP.md) | Pi from scratch to running hub |
| [ADD_A_JOB.md](docs/ADD_A_JOB.md) | Writing jobs |
| [NOTIFIERS.md](docs/NOTIFIERS.md) | Channel setup |
| [TAILSCALE.md](docs/TAILSCALE.md) | Remote access (optional) |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design decisions |

## Tests

```bash
cd hub       && .venv/bin/python -m pytest -q    # 89 tests
cd dashboard && .venv/bin/python -m pytest -q    # 12 tests
```

No network or credentials required.

## Licence

MIT — see [LICENSE](LICENSE).
