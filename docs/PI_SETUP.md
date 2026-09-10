# Raspberry Pi setup

From an unopened Pi to a running hub. About 45 minutes, mostly downloads.

Nothing here is Pi-specific — an old laptop, a NUC or a VPS work the same
way, and the images build for amd64 and arm64.

[Fork the repo](https://github.com/) first. Everything below clones your
fork, since that's where your jobs will live.

---

## 1. Hardware

Any Pi 3 or newer. The workload is idle almost all the time.

- **Storage.** SD cards fail after roughly a year of continuous writes. A
  USB SSD is the biggest reliability improvement available; a Pi 4 or 5
  can boot from one directly (`raspi-config` → Advanced → Boot Order). On
  SD, buy an "endurance" card.
- **Power supply.** Use the official one. Under-voltage causes filesystem
  corruption that presents as random software bugs.

Ethernet or Wi-Fi. No monitor or keyboard needed.

## 2. Flash the card

Use **Raspberry Pi Imager**.

1. **Choose OS** → Raspberry Pi OS (other) → **Raspberry Pi OS Lite
   (64-bit)**.
2. **Choose Storage** → your card or SSD.
3. Click the **gear icon** (or *Edit Settings*) and set:
   - **Hostname**: `pi-hub` → reachable as `pi-hub.local`
   - **Username and password**
   - **Wireless LAN**, if not using ethernet
   - **Locale**: timezone and keyboard
   - **Services** → **Enable SSH** → **Allow public-key authentication
     only**, and paste your public key
4. Write and eject.

To generate a key:

```bash
ssh-keygen -t ed25519          # accept the defaults
cat ~/.ssh/id_ed25519.pub      # paste this into the imager
```

## 3. First boot

Insert the card, connect ethernet, connect power. Wait two minutes — the
first boot resizes the filesystem and reboots.

```bash
ssh <username>@pi-hub.local
```

If `.local` doesn't resolve, get the IP from your router's client list.

Update:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

In your router, add a **DHCP reservation** for the Pi's MAC address. This
is preferable to a static IP on the Pi: it survives reinstalls and can't
collide with the router's pool.

## 4. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

**Log out and back in** for the group change to apply, then verify:

```bash
docker run --rm hello-world
```

Docker starts on boot, and the compose file uses `restart: unless-stopped`,
so the stack returns after a power cut. No systemd units to write.

## 5. Clone your fork

**Public fork:**

```bash
git clone https://github.com/<you>/personal-pi-home.git
cd personal-pi-home
```

**Private fork, or if you want to push from the Pi** — use a deploy key:

```bash
ssh-keygen -t ed25519 -C "pi-hub" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

On GitHub: your fork → **Settings** → **Deploy keys** → **Add deploy key**
→ paste. Tick **Allow write access** only if you'll push from the Pi.

```bash
git clone git@github.com:<you>/personal-pi-home.git
cd personal-pi-home
```

A deploy key is scoped to one repository. Don't copy your personal SSH key
onto the Pi.

## 6. Configure and start

```bash
cp .env.example .env
nano .env                 # one notification channel
nano hub/config.yaml      # timezone; enable jobs
docker compose up -d
```

- **`timezone` in `hub/config.yaml`** determines when schedules fire,
  regardless of the host clock.
- **`.env` is optional.** Without it, messages go to the container log.

The first build takes a few minutes on a Pi. Later rebuilds take seconds.

## 7. Verify

```bash
docker compose ps                                    # both 'running'
docker compose exec hub python -m src.main --doctor  # channels, timezone, state
docker compose exec hub python -m src.main --list    # schedules and next run
```

The **NEXT** column answers "why hasn't it done anything yet" — a
`daily_at: "09:00"` job started at noon won't fire until tomorrow.

Send one now instead of waiting:

```bash
docker compose exec hub python -m src.main --run hello
```

Open `http://pi-hub.local:8090`. The `hello` card should show a green dot
and a recent timestamp, which confirms the container is running, the
schedule fired, the state volume is writable, the timezone is right, and
the message was delivered.

## 8. Edit, push, deploy

Write jobs on your laptop, where you have your editor and the test suite:

```bash
cd hub
.venv/bin/python -m src.main --run my_job --dry-run
.venv/bin/python -m pytest -q
cd .. && git add . && git commit -m "Add my_job" && git push
```

On the Pi:

```bash
cd ~/personal-pi-home
./scripts/deploy.sh
```

`deploy.sh` pulls, rebuilds, restarts and prunes old images. It refuses to
run if there are uncommitted changes on the box, since a rebuild would
discard them.

**Restart or rebuild:**

| Changed | Command | Why |
|---|---|---|
| `hub/config.yaml` | `docker compose restart hub` | Live-mounted, read at startup |
| `.env` | `docker compose up -d` | Environment is set at container creation |
| Anything in `hub/src/` | `docker compose up -d --build` | Code is baked into the image |

`deploy.sh` does the last one, which covers all three.

To make job edits take effect on a restart instead of a rebuild, add
`- ./hub/src:/app/src:ro` to the `hub` service's volumes. Useful while
iterating; remove it once settled so the image matches what's running.

**Automatic deploys** (optional) — check every 15 minutes:

```cron
*/15 * * * * cd $HOME/personal-pi-home && ./scripts/deploy.sh >> /tmp/deploy.log 2>&1
```

It exits immediately when there's nothing new. Note that anything pushed
to that branch then runs on your home network within 15 minutes without
review.

**Pulling upstream changes** into your fork:

```bash
git remote add upstream https://github.com/<original-owner>/personal-pi-home.git
git fetch upstream
git merge upstream/main
```

Your jobs are separate files, so framework updates rarely conflict.
`config.yaml` is the file most likely to need a manual merge.

## 9. Remote access (optional)

The dashboard has no authentication and should not be port-forwarded. To
reach it and SSH from outside your network, use
**[Tailscale](TAILSCALE.md)** — about 20 minutes, no router configuration.

---

## Maintenance

- **Keep `hello` enabled.** A daily heartbeat that stops arriving is how
  you notice the box has stopped.
- **Don't delete `hub/data/`.** It records what has already been sent.
- **Watch disk usage** on SD cards: `df -h`. Logs rotate and old rows are
  pruned automatically.

## Troubleshooting

General problems are in [SETUP.md → Troubleshooting](SETUP.md#troubleshooting).
Start with:

```bash
docker compose exec hub python -m src.main --doctor
docker compose exec hub python -m src.main --list
docker compose logs -f hub
```

Box-specific:

| Symptom | Cause / fix |
|---|---|
| `permission denied` from docker | You didn't log out and back in after step 4 |
| `pi-hub.local` doesn't resolve | No mDNS on some networks — use the IP |
| Dashboard won't load | `docker compose ps`; check IP and port 8090 |
| Build fails or hangs | Usually memory. A Pi 3 with 1 GB is tight |
| Random corruption or crashes | Under-voltage or a failing SD card: `dmesg \| grep -i voltage` |
| Everything re-sent after a deploy | `hub/data/` was lost |
