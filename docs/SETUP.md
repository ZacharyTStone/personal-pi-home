# Setup

Fork it, follow these, done. Four steps, and you can stop after step 2
with a working hub on your laptop — the Pi is step 4.

| # | What | For | Do it now? |
|---|------|-----|------------|
| 0 | [Fork and run it](#0-fork-and-run-it) | Seeing it work | ✅ 5 min |
| 1 | [One notification channel](#1-one-notification-channel) | Messages on your phone | ✅ 2 min |
| 2 | [Make it yours](#2-make-it-yours) | Your timezone, your jobs | ✅ 10 min |
| 3 | [Commit it](#3-commit-it) | Your fork is your hub | ✅ 1 min |
| 4 | [Put it on a box](#4-put-it-on-a-box) | Always-on | ⏳ when you have one |

---

## 0. Fork and run it

Click **Fork** on GitHub — or `gh repo fork <owner>/personal-pi-home` —
then clone **your** fork:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home/hub

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m src.main --list
.venv/bin/python -m src.main --run hello --dry-run
```

You should see a hello message printed to your terminal. That's the whole
pipeline — schedule, state, rendering, delivery — working with nothing
configured, no `.env`, and no accounts.

```bash
.venv/bin/python -m src.main --doctor
```

`--doctor` is the command to come back to whenever something isn't
working. It prints which channels have credentials, what timezone the hub
thinks it's in, where its state lives, and which jobs are on.

## 1. One notification channel

Pick one from [`NOTIFIERS.md`](NOTIFIERS.md). **ntfy** takes about two
minutes and needs no account at all, so start there unless you have a
preference.

```bash
cp .env.example .env
$EDITOR .env            # fill in that one channel
```

Point the jobs at it in `hub/config.yaml`:

```yaml
notify:
  default_channels: [ntfy]
```

Check it's live, then send yourself something for real:

```bash
cd hub
.venv/bin/python -m src.main --doctor      # your channel should show ✔
.venv/bin/python -m src.main --run hello   # no --dry-run: this actually sends
```

If that arrives on your phone, everything after this is just writing jobs.

## 2. Make it yours

**`hub/config.yaml` first:**

```yaml
hub_name: my-pi-home
timezone: Europe/Lisbon        # ← change this before anything else
```

The timezone matters more than it looks. Every schedule is local
wall-clock time in that zone, whatever the host clock says — get it wrong
and your 07:00 message arrives at 07:00 UTC.

**Then write a job.** Copy `hub/src/jobs/hello.py`, give it a new `NAME`,
and drop it in `hub/src/jobs/`. It's live immediately — no registry to
edit:

```bash
.venv/bin/python -m src.main --list
.venv/bin/python -m src.main --run my_job --dry-run
```

Full walkthrough, including the three shapes most home-hub jobs take:
[`ADD_A_JOB.md`](ADD_A_JOB.md).

Keep `hello` enabled even once you have real jobs. A daily heartbeat that
stops arriving is how you find out the box died — the failure mode of an
always-on box is silence, and silence looks exactly like a quiet day.

## 3. Commit it

Your fork *is* your hub. Push your jobs and your config to it — that's
what the box will pull from.

```bash
cd hub && .venv/bin/python -m pytest -q     # takes under a second
cd .. && git add . && git commit -m "My jobs" && git push
```

`.env` is gitignored, so your secrets stay on your machines. `config.yaml`
is committed on purpose: `git log config.yaml` becomes the record of how
your hub got tuned, which is genuinely useful six months later when you
wonder why something is set to 40.

## 4. Put it on a box

Full walkthrough from a boxed Pi to a running hub, including getting it
pulling from your fork and the edit → push → deploy loop:
**[`PI_SETUP.md`](PI_SETUP.md)**.

The short version, if you already have Docker on something:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home
cp .env.example .env && $EDITOR .env
docker compose up -d
```

Dashboard at `http://<box-ip>:8090`. To reach it from outside the house,
don't port-forward it — see [`TAILSCALE.md`](TAILSCALE.md).

**Don't delete `hub/data/`.** It holds the SQLite state that tells the hub
what it has already sent. Losing it means every job re-notifies you about
everything.

---

## When something doesn't work

| Symptom | Where to look |
|---|---|
| Nothing arrives | `--doctor` — is your channel ✔? |
| Messages at the wrong hour | `timezone` in `config.yaml`, not `TZ` |
| A job never runs | `--list` — is it `[on ]`? Is its window still ahead? |
| A job runs but stays quiet | Normal for most jobs. Check the run count on the dashboard. |
| A job is failing | Dashboard shows the error; `docker compose logs hub` has the traceback |
| Everything re-sent after a deploy | The `hub/data` directory was lost |
