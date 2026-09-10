# Remote access

Optional. About 20 minutes.

## Why not port forwarding

The dashboard has no authentication — it's a LAN status page, and adding
logins to it would be a project in itself.

Forwarding port 8090 publishes what you're being notified about, when, and
a live log tail to anyone who scans for it, which happens within minutes
of a port opening. Forwarding SSH invites thousands of credential-stuffing
attempts a day against a device you set up once and stopped updating.

The alternative is to keep it off the public internet and put your devices
on the same private network as the Pi instead.

## What Tailscale does

A mesh VPN built on WireGuard. Each device gets a stable private address
(`100.x.y.z`) and connects directly to the others, encrypted, regardless
of physical location.

- Dashboard at `http://pi-hub:8090` from anywhere, with no auth layer
  needed, because the network is the boundary.
- `ssh you@pi-hub` from anywhere, with no open ports.
- No router configuration, no dynamic DNS, no static IP. Works behind
  CGNAT, which port forwarding cannot.
- Free tier: 100 devices, 3 users.

Trade-off: Tailscale's coordination service brokers connections and
manages keys. It cannot read your traffic — that's end-to-end encrypted
between devices — but it controls which devices may connect.
[Headscale](https://github.com/juanfont/headscale) is a self-hostable
implementation of the same control plane, and everything below works
against it.

## Setup

1. Create an account at [tailscale.com](https://tailscale.com).

2. On the Pi:

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --ssh
   ```

   It prints a URL — open it and sign in. `--ssh` uses your Tailscale
   identity for SSH instead of keys; omit it to keep using your own.

3. Install Tailscale on your laptop and phone, signed into the same
   account.

4. Enable **MagicDNS** in the [admin
   console](https://login.tailscale.com/admin/dns) so devices are
   reachable by name:

   ```bash
   ssh you@pi-hub
   open http://pi-hub:8090
   ```

## Two settings worth changing

**Disable key expiry for the Pi.** Device keys expire after 180 days by
default, and the device drops off the network silently. Admin console →
**Machines** → your Pi → **⋯** → **Disable key expiry**.

**Restrict the Pi with an ACL** (optional). Tag the machine so it can be
reached by your devices but cannot initiate connections to them.

## Extras

**HTTPS on the dashboard:**

```bash
sudo tailscale serve --bg 8090
```

Serves it at `https://pi-hub.<your-tailnet>.ts.net` with a valid
certificate, still only reachable inside your tailnet. Enable HTTPS in the
admin console first (**DNS** → **HTTPS Certificates**).

**Share one machine** with another person without giving them your whole
network: admin console → **Machines** → **Share**.

**Don't use `tailscale funnel`** for the dashboard — it publishes to the
public internet.

## Alternatives

- **[Raspberry Pi Connect](https://www.raspberrypi.com/software/connect/)**
  — official, browser-based, no client app. Simpler for shell access, less
  suited to reaching a port like 8090. `sudo apt install rpi-connect`.
- **[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)**
  — useful if you also want something public on your own domain, with an
  auth layer in front.
- **WireGuard on your router**, if supported. More setup, one fewer third
  party, and it needs a stable inbound address.
- **Nothing.** The hub pushes notifications to you. If you only need the
  dashboard at home, skip this.
