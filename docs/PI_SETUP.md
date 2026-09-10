# From a boxed Pi to a running hub

Start to finish, assuming nothing. About 45 minutes, most of it waiting
for downloads.

Nothing here is actually Pi-specific — an old laptop, a NUC or a cheap VPS
all work the same way, and the images build for both amd64 and arm64. A Pi
is just the cheapest thing that can sit on a shelf and stay on.

**Before you start:** [fork the repo](#0-fork-it) on GitHub. Everything
below clones *your* fork, because the whole point is that you'll be
committing your own jobs to it.

| | Step | Time |
|---|---|---|
| 0 | [Fork it](#0-fork-it) | 1 min |
| 1 | [Hardware](#1-hardware) | — |
| 2 | [Flash the card](#2-flash-the-card) | 15 min |
| 3 | [First boot](#3-first-boot) | 10 min |
| 4 | [Install Docker](#4-install-docker) | 5 min |
| 5 | [Get your fork onto the Pi](#5-get-your-fork-onto-the-pi) | 5 min |
| 6 | [Configure and start](#6-configure-and-start) | 5 min |
| 7 | [Check it's actually working](#7-check-its-actually-working) | 2 min |
| 8 | [The edit → push → deploy loop](#8-the-edit--push--deploy-loop) | — |
| 9 | [Reach it from anywhere](#9-reach-it-from-anywhere-optional) (optional) | 20 min |

---

## 0. Fork it

Click **Fork** at the top of the GitHub page, or:

```bash
gh repo fork <owner>/personal-pi-home --clone=false
```

Fork rather than clone-and-push-elsewhere: you get a normal `origin` you
can push your own jobs to, and you can still pull upstream fixes later.

**Public or private?** Your fork will contain `config.yaml` — which holds
decisions, not secrets — so public is fine, and it's the easier path.
`.env` is gitignored and never leaves your machines either way. If you'd
rather it were private, that's fine too; step 5 covers the extra key.

## 1. Hardware

Any Pi 3 or newer is plenty. This workload is idle roughly 99% of the
time — the hub spends its life asleep between ticks.

Two things worth spending money on:

- **Storage.** SD cards die, usually after about a year of a service
  writing to one continuously. A USB SSD is the single biggest
  reliability upgrade you can make, and a Pi 4 or 5 can boot from one
  directly (set the boot order in `raspi-config` → Advanced → Boot Order).
  If you stay on SD, buy an "endurance" card meant for dashcams.
- **A real power supply.** The official one, or an equivalent. Under-
  voltage causes filesystem corruption that presents as random,
  unreproducible software bugs, and you will lose a weekend to it before
  you suspect the plug.

You also want an ethernet cable or decent Wi-Fi, and that's it. No
monitor, no keyboard — everything below is headless.

## 2. Flash the card

Use **Raspberry Pi Imager** (free, all platforms).

1. **Choose OS** → Raspberry Pi OS (other) → **Raspberry Pi OS Lite
   (64-bit)**. Lite: you don't need a desktop on a box you'll never plug
   a monitor into.
2. **Choose Storage** → your card or SSD.
3. Click the **gear icon** (or *Edit Settings* when it asks). This is the
   part that saves you an hour:
   - **Set hostname**: `pi-hub` (it'll be reachable as `pi-hub.local`)
   - **Set username and password**: pick a username, use a real password
   - **Configure wireless LAN**: your Wi-Fi, if you're not using ethernet
   - **Set locale settings**: your timezone and keyboard
   - **Services** tab → **Enable SSH** → **Allow public-key
     authentication only**, and paste your public key
4. Write, wait, eject.

No public key yet? On your laptop:

```bash
ssh-keygen -t ed25519          # press enter three times
cat ~/.ssh/id_ed25519.pub      # paste this into the imager
```

## 3. First boot

Put the card in, plug in ethernet (if using), plug in power. Give it two
minutes — the first boot resizes the filesystem and reboots itself.

```bash
ssh <your-username>@pi-hub.local
```

If `.local` doesn't resolve (some networks, some Windows setups), find
the Pi's address in your router's client list and use that instead.

Then bring it up to date — on a fresh image this is usually a few hundred
packages, so put the kettle on:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

**Give it a fixed address.** In your router, find the Pi in the DHCP
client list and add a **reservation** for its MAC address. Do this in the
router rather than setting a static IP on the Pi — it survives reinstalls,
and it can't collide with the router's own pool.

## 4. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Then **log out and back in** (`exit`, then `ssh` again) so the group
change takes effect. Check:

```bash
docker run --rm hello-world
```

Docker starts on boot by default, and the compose file uses
`restart: unless-stopped`, so the stack comes back by itself after a
power cut. That's the whole "always-on" story — no systemd units to write.

## 5. Get your fork onto the Pi

**If your fork is public**, this is one command:

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home
```

You'll be able to `git pull`. To *push* from the Pi (you probably won't
need to — see step 8), you'd want a key, so set one up now if you like:

**If your fork is private**, or you want to push from the Pi, give it a
**deploy key**:

```bash
ssh-keygen -t ed25519 -C "pi-hub" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Copy that line, then on GitHub: your fork → **Settings** → **Deploy keys**
→ **Add deploy key** → paste → tick **Allow write access** only if you
intend to push from the Pi. Then:

```bash
git clone git@github.com:<you>/personal-pi-home.git
cd personal-pi-home
```

A deploy key is scoped to this one repository, which is exactly what you
want on a device sitting on a shelf. Don't copy your personal SSH key
onto it.

## 6. Configure and start

```bash
cp .env.example .env
nano .env                 # fill in ONE notification channel
nano hub/config.yaml      # set your timezone; turn jobs on
docker compose up -d
```

Two things to get right:

- **`timezone` in `hub/config.yaml`** — every schedule is local wall-clock
  time in that zone, whatever the host clock says. Set it to yours or your
  09:00 message arrives at 09:00 UTC.
- **One channel in `.env`** — [ntfy](NOTIFIERS.md#ntfy) takes two minutes
  and needs no account. You can skip this entirely and messages go to the
  container log, which is a fine way to start.

The first `up` builds the images, which takes a few minutes on a Pi
(it's compiling nothing, just downloading Python wheels). Later rebuilds
are seconds.

## 7. Check it's actually working

```bash
docker compose ps                    # both services 'running'?
docker compose logs -f hub           # ctrl-C to stop following
docker compose exec hub python -m src.main --doctor
```

`--doctor` is the command to come back to whenever something seems wrong.
It prints which channels have credentials, what timezone the hub thinks
it's in, where its state lives, and which jobs are on.

Send yourself something for real:

```bash
docker compose exec hub python -m src.main --run hello
```

Then open the dashboard: **`http://pi-hub.local:8090`** (or the Pi's IP).
You should see a `hello` card with a green dot and a fresh timestamp.

That green dot is the whole point of the `hello` job. It means: container
running, schedule firing, state volume writable, timezone correct,
messages being delivered. Five things that are each silently wrong on
somebody's first attempt, confirmed in one glance.

Now write the job you actually wanted — [ADD_A_JOB.md](ADD_A_JOB.md).

## 8. The edit → push → deploy loop

Write jobs **on your laptop**, not over SSH. You get your editor, and the
test suite runs offline in under a second:

```bash
# on your laptop
cd hub
.venv/bin/python -m src.main --run my_job --dry-run
.venv/bin/python -m pytest -q
git add . && git commit -m "Add my_job" && git push
```

Then on the Pi:

```bash
cd ~/personal-pi-home
./scripts/deploy.sh
```

`deploy.sh` pulls, rebuilds, restarts, and prunes old images. It refuses
to run if you've made uncommitted edits directly on the box — config
changes belong in git, or the next rebuild quietly undoes them.

**Optional: deploy automatically.** If you'd rather push and forget, have
the Pi check for changes every 15 minutes:

```bash
crontab -e
```

```cron
*/15 * * * * cd $HOME/personal-pi-home && ./scripts/deploy.sh >> /tmp/deploy.log 2>&1
```

It exits immediately when there's nothing new, so this is close to free.
Understand the trade first: anything you push to that branch runs on your
home network within fifteen minutes, unreviewed. Fine for a personal box,
worth thinking about if anyone else can push to your fork.

**Pulling upstream fixes** into your fork later:

```bash
git remote add upstream https://github.com/<original-owner>/personal-pi-home.git
git fetch upstream
git merge upstream/main
```

Your jobs live in their own files under `hub/src/jobs/`, so upstream
changes to the framework rarely conflict with them. `config.yaml` is the
one file likely to need a manual merge.

## 9. Reach it from anywhere (optional)

You almost certainly want this, and it takes twenty minutes:
**[TAILSCALE.md](TAILSCALE.md)**.

The short version of why: the dashboard has **no authentication**, by
design. It's a LAN status page. Do not port-forward it. Tailscale gives
you the dashboard and SSH from your phone anywhere in the world without
opening a single port on your router.

---

## Keeping it alive

Three habits, in descending order of how much they'll save you:

- **Keep the `hello` job enabled.** The failure mode of an always-on box
  is *silence*, and silence looks exactly like "nothing happened today".
  A daily heartbeat that stops arriving is how you find out.
- **Never delete `hub/data/`.** It's how the hub knows what it has
  already sent. Losing it means every job re-notifies you about
  everything. It's a host directory, so rebuilds and image changes don't
  touch it — only you can.
- **Watch the disk** if you're on an SD card: `df -h`. Logs rotate and
  old rows are pruned automatically, but SD cards fail in less graceful
  ways than filling up.

## When something's wrong

| Symptom | Try |
|---|---|
| Nothing arrives | `docker compose exec hub python -m src.main --doctor` |
| Messages at the wrong hour | `timezone` in `config.yaml` — not `TZ` |
| A job never runs | `--list` — is it `[on ]`? Is its window still ahead? |
| A job is quiet | Normal for most jobs. Check the run count on the dashboard. |
| A job is failing | Dashboard shows the error; `docker compose logs hub` has the traceback |
| Everything re-sent after a deploy | The `hub/data` directory was lost |
| Dashboard won't load | `docker compose ps` — is it running? Right IP? |
| `permission denied` on docker | You skipped the log out / log back in after step 4 |
