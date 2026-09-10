# Reaching your hub from anywhere

Optional, but you probably want it. Twenty minutes.

## Why not just forward a port?

Because the dashboard has **no authentication**, and that's deliberate.

It's a LAN status page: you leave it open on a tablet in the kitchen and
hand it to whoever asks whether the thing is working. Adding login,
sessions, and password resets to it would be a whole project, and a
worse-secured one than what's below.

So if you port-forward `8090`, you have published your home's status page
— what you're being notified about, when you're being notified, and a
live log tail — to everyone with an internet connection and a port
scanner. Scanners find new open ports within *minutes*, not days. The
same applies double to forwarding SSH: an SSH port open to the internet
gets thousands of credential-stuffing attempts a day, and a Pi you set up
once and forgot to update is exactly what that traffic is looking for.

The alternative isn't "secure the dashboard". It's **don't put it on the
internet at all** — put your devices and your Pi on the same private
network instead, wherever they physically are.

## What Tailscale actually does

It's a mesh VPN built on WireGuard. Every device you add gets a stable
private address (`100.x.y.z`), and they talk to each other directly,
encrypted, as though they were on the same LAN — whether that's your
laptop in a café, your phone on mobile data, or the Pi in your hallway.

What this buys you:

- The dashboard at `http://pi-hub:8090` **from anywhere**, with the same
  no-auth setup, because the network itself is the boundary now.
- `ssh you@pi-hub` from anywhere, with no port open to the world.
- **Zero router configuration.** No port forwarding, no dynamic DNS, no
  static IP, nothing that breaks when your ISP changes your address. It
  works behind CGNAT, which plain port-forwarding cannot.
- The free tier covers up to 100 devices and 3 users — comfortably more
  than a personal hub needs.

The trade-off, stated honestly: you're trusting Tailscale's coordination
service to broker connections and manage keys. It cannot read your
traffic — that's end-to-end encrypted between devices — but it does
decide which devices are allowed to connect. If that's not a trade you
want, [Headscale](https://github.com/juanfont/headscale) is a
self-hostable implementation of the same control plane, and everything
below works against it.

## Setting it up

**1. Make an account** at [tailscale.com](https://tailscale.com) — sign
in with GitHub or Google, no card needed for the free tier.

**2. Install it on the Pi:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
```

It prints a URL. Open it, sign in, and the Pi joins your network.

`--ssh` lets you SSH in using your Tailscale identity rather than
managing keys — nice, and optional. Drop it if you'd rather keep using
your own SSH keys.

**3. Install it on your laptop and phone.** Desktop apps for macOS,
Windows and Linux; apps on the App Store and Play Store. Sign in with the
same account.

**4. Turn on MagicDNS** in the [admin
console](https://login.tailscale.com/admin/dns) → **Enable MagicDNS**. Now
your devices are reachable by name instead of by `100.x.y.z`:

```bash
ssh you@pi-hub
open http://pi-hub:8090
```

That's it. The dashboard now works from your phone on mobile data, in
another country, with nothing exposed publicly.

## Two settings worth changing

**Disable key expiry for the Pi.** By default a device's key expires after
180 days and it silently drops off the network — which, on a headless box
in a cupboard, you will discover at the worst possible moment. In the
admin console → **Machines** → your Pi → **⋯** → **Disable key expiry**.

**Lock the Pi down** (optional, but sensible for a device you rarely
touch). In the admin console you can tag the machine and write an ACL so
it can only be *reached* by your devices and can't initiate connections
to them. Overkill for most people; genuinely useful if the Pi runs
anything that talks to the internet.

## Nice extras

**HTTPS on the dashboard**, with a real certificate and no configuration:

```bash
sudo tailscale serve --bg 8090
```

The dashboard becomes available at `https://pi-hub.<your-tailnet>.ts.net`
with a valid Let's Encrypt certificate, still only reachable from inside
your tailnet. Enable HTTPS in the admin console first
(**DNS** → **HTTPS Certificates**).

**Share it with one other person** — a partner who wants the dashboard —
without giving them your whole network: admin console → **Machines** →
**Share**. They get a link, and access to only that machine.

**Don't use `tailscale funnel`** for the dashboard. Funnel publishes a
service to the *public* internet, which puts you back at the top of this
document.

## Alternatives

- **[Raspberry Pi Connect](https://www.raspberrypi.com/software/connect/)**
  — official, browser-based, no client app to install. Easier for shell
  access, less flexible than Tailscale for reaching a port like `:8090`.
  `sudo apt install rpi-connect` then `rpi-connect signin`.
- **[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)**
  — good if you also want to expose something publicly on your own
  domain, and you're prepared to put an auth layer in front of it.
- **A plain WireGuard server** on your router, if it supports it. More
  setup, one fewer company involved, and it needs a stable inbound
  address (so: not behind CGNAT).
- **Nothing.** The hub pushes notifications *to* you. If you only ever
  want the dashboard while you're at home, you don't need any of this.
