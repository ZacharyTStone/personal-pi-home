# Setup

Do these in order. You can stop after step 2 and have a working hub on
your laptop; the box is step 4.

| # | What | For | Now? |
|---|------|-----|------|
| 1 | Run it once | Seeing it work | ✅ |
| 2 | One notification channel | Messages on your phone | ✅ |
| 3 | Edit `config.yaml` | Making it yours | ✅ |
| 4 | Docker on the box | Always-on | ⏳ when you have one |

---

## 1. Run it once

```bash
cd hub
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m src.main --list
.venv/bin/python -m src.main --run hello --dry-run
```

You should see a hello message printed to your terminal. That's the whole
pipeline working — schedule, state, rendering, delivery — with nothing
configured.

```bash
.venv/bin/python -m src.main --doctor
```

`--doctor` is the command to come back to whenever something isn't
working. It prints which channels have credentials, which timezone the
hub thinks it's in, where its state lives, and which jobs are on.

## 2. One notification channel

Pick one from [`NOTIFIERS.md`](NOTIFIERS.md) — **ntfy** takes about two
minutes and needs no account. Then:

```bash
cp .env.example .env
$EDITOR .env        # fill in that one channel
```

Point the jobs at it in `hub/config.yaml`:

```yaml
notify:
  default_channels: [ntfy]
```

Check it's live, then send yourself something for real:

```bash
cd hub
.venv/bin/python -m src.main --doctor        # your channel should show ✔
.venv/bin/python -m src.main --run hello     # no --dry-run: this actually sends
```

## 3. Make it yours

`hub/config.yaml` is the file you'll actually live in.

```yaml
hub_name: my-pi-home
timezone: Europe/Lisbon        # ← change this first
```

The timezone matters more than it looks: every schedule is local
wall-clock time in that zone, whatever the host clock says. Get it wrong
and your 07:00 message arrives at 07:00 UTC.

Then write the job you actually wanted. Copy `hub/src/jobs/hello.py`,
give it a new `NAME`, and drop it in — see [`ADD_A_JOB.md`](ADD_A_JOB.md).

## 4. On the box

```bash
cp .env.example .env      # the same values
$EDITOR .env
docker compose up -d
docker compose logs -f hub
```

Then open `http://<box-ip>:8090`.

The `hub/data` directory is mounted into the container and holds all the
SQLite state. **Don't delete it** — it's how the hub knows what it has
already sent. Losing it means every job re-notifies you about everything.

Hardware, flashing, remote access: [`PI_SETUP.md`](PI_SETUP.md).

---

## When something doesn't work

| Symptom | Where to look |
|---|---|
| Nothing arrives | `--doctor` — is your channel ✔? |
| Messages arrive at the wrong hour | `timezone` in `config.yaml`, not `TZ` |
| A job never runs | `--list` — is it `[on ]`? Is its window in the future? |
| A job runs but stays quiet | Normal for most jobs. Check the dashboard's run count. |
| A job is failing | Dashboard shows the error; `docker compose logs hub` has the traceback |
| It re-sent everything after a deploy | The `hub/data` volume was lost |
