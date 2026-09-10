# Setup

Steps 1–4 run on your laptop (~20 minutes). Step 5 puts it on a box.

---

## 1. Run it

Fork on GitHub (or `gh repo fork <owner>/personal-pi-home`), then clone
your fork:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home/hub

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m src.main --list
.venv/bin/python -m src.main --run hello --dry-run
```

The hello message prints to your terminal.

## 2. Set your timezone

In `hub/config.yaml`:

```yaml
hub_name: my-pi-home
timezone: Europe/Lisbon        # IANA name
```

Every schedule is local wall-clock time in this zone, regardless of the
host clock. Verify:

```bash
.venv/bin/python -m src.main --list
```

The header shows the timezone and current local time. The **NEXT** column
shows when each job will fire.

## 3. Set up a notification channel

Pick one from [NOTIFIERS.md](NOTIFIERS.md). ntfy needs no account and
takes two minutes.

```bash
cd ..                   # repo root
cp .env.example .env
$EDITOR .env            # fill in one channel
```

Route jobs to it in `hub/config.yaml`:

```yaml
notify:
  default_channels: [ntfy]
```

Verify, then send for real:

```bash
cd hub
.venv/bin/python -m src.main --doctor      # your channel shows ✔ and is the default route
.venv/bin/python -m src.main --run hello   # without --dry-run, this sends
```

Credentials in `.env` do nothing on their own — `config.yaml` decides
where messages go. `--doctor` warns if a configured channel isn't routed
anywhere.

## 4. Write a job and commit

Copy `hub/src/jobs/hello.py`, change `NAME`, save it in
`hub/src/jobs/`:

```bash
.venv/bin/python -m src.main --list
.venv/bin/python -m src.main --run my_job --dry-run
```

See [ADD_A_JOB.md](ADD_A_JOB.md) for the full API and common job patterns.

Push it — your fork is what the box pulls from:

```bash
cd hub && .venv/bin/python -m pytest -q
cd .. && git add . && git commit -m "Add my_job" && git push
```

`.env` is gitignored. `config.yaml` is committed, so your schedules and
settings are versioned.

## 5. Put it on a box

Full walkthrough — Pi setup, Docker, pulling from your fork, and the
deploy loop: **[PI_SETUP.md](PI_SETUP.md)**.

Short version if Docker is already installed:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home
cp .env.example .env && $EDITOR .env
docker compose up -d
```

Dashboard: `http://<box-ip>:8090`. For access from outside your network,
use [Tailscale](TAILSCALE.md) rather than port forwarding — the dashboard
has no authentication.

Do not delete `hub/data/`. It holds the record of what has already been
sent; without it every job re-notifies you about everything.

---

## Troubleshooting

Start with `--doctor` (channels, timezone, state location, enabled jobs)
and `--list` (schedules and next run). On a box, prefix with
`docker compose exec hub`.

| Symptom | Cause / fix |
|---|---|
| Nothing arrives | `--doctor`: is your channel `✔`, and is it in `default_channels` or a route? A configured channel that nothing routes to is never used. |
| Wrong hour | `timezone` in `config.yaml`. `TZ` only affects log timestamps. |
| Started it, nothing happened | `--list` → **NEXT**. A `daily_at: "18:00"` job started at noon waits six hours. Use `--run <job>` to fire now. |
| A job never runs | `--list`: is it `[on ]`? Check `enabled` in `config.yaml` and `ENABLED` in the job file. |
| A job runs but sends nothing | Expected if the job had nothing to report. Check the run count on the dashboard. |
| A job is failing | Error on the dashboard; traceback in `docker compose logs hub` or `hub/data/hub.log`. |
| Edited `config.yaml`, no change | `docker compose restart hub` — config is read at startup. |
| Added a job file, not listed | `docker compose up -d --build` — job code is baked into the image. |
| Everything re-sent after a deploy | `hub/data/` was lost. |
