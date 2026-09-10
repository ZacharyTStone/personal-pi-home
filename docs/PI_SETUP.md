# The box

Nothing here is specific to a Raspberry Pi — an old laptop, a NUC or a
VPS all work, and the images build for both amd64 and arm64. A Pi is just
the cheapest thing that can sit somewhere and stay on.

## Hardware

Any Pi 3 or newer is plenty; this workload is idle almost all the time.
Two things worth spending on:

- **Storage.** SD cards die, usually after about a year of a service
  writing to them continuously. A USB SSD is the single biggest
  reliability upgrade, and a Pi 4+ can boot from one directly.
- **A real power supply.** Under-voltage causes filesystem corruption
  that looks exactly like random software bugs, and you will waste a
  weekend on it.

## First boot

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In
   the imager's settings, pre-set the hostname, your user, and your
   Wi-Fi, and **enable SSH with a public key** — that's the whole
   headless setup.
2. SSH in: `ssh you@raspberrypi.local`
3. Update and install Docker:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER      # then log out and back in
   ```
4. Give it a fixed address — a DHCP reservation in your router is easier
   than a static IP on the Pi, and survives reinstalls.

## Deploy

```bash
git clone <your fork> && cd personal-pi-home
cp .env.example .env && $EDITOR .env
$EDITOR hub/config.yaml         # timezone first
docker compose up -d
docker compose logs -f hub
```

Dashboard: `http://<pi-ip>:8090`.

## Updating

```bash
git pull
docker compose up -d --build
```

State lives in `hub/data` on the host, so rebuilds never lose track of
what has already been sent. **Back that directory up** if you'd miss it —
or don't, and accept that a rebuild from scratch means one round of
duplicate notifications.

## Reaching it from outside

Don't port-forward the dashboard. It has no authentication, by design —
it's a LAN status page, and adding auth to it is a whole project.

Use a private overlay network instead:

- **Tailscale** — `curl -fsSL https://tailscale.com/install.sh | sh`,
  then `sudo tailscale up`. Your devices see the Pi on a private address
  as if they were on the same LAN.
- **Raspberry Pi Connect** — official, browser-based, `rpi-connect` in
  Raspberry Pi OS.

Either gives you SSH and the dashboard from anywhere without opening a
single port to the internet.

## Keeping it alive

- `restart: unless-stopped` in compose means the stack comes back after a
  power cut. Docker starts on boot by default.
- Keep the `hello` job enabled. A daily heartbeat that stops arriving is
  how you find out the box died — the failure mode of an always-on box is
  silence, and silence looks exactly like "nothing happened today".
- Watch the disk on an SD card install: `df -h`. Logs rotate and old rows
  are pruned automatically, but SD cards fail in less graceful ways.
