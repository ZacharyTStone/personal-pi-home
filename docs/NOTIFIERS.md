# Notification channels

Set up one. Adding more later requires no changes to your jobs — they call
`ctx.send()` and `config.yaml` decides the destination.

| Channel | Setup | Notes |
|---|---|---|
| [ntfy](#ntfy) | 2 min, no account | Fastest to get working |
| [Telegram](#telegram) | 5 min | One message per recipient |
| [Discord](#discord) | 1 min | If you already have a server |
| [email](#email) | 10 min | Searchable later; good for digests |
| [LINE](#line) | 30 min | Only if you already have an Official Account |
| console | none | Local runs and `--dry-run` |

Check what's configured:

```bash
cd hub && python -m src.main --doctor
```

---

## ntfy

No account or token.

1. Install the **ntfy** app (iOS / Android) or use the web app.
2. Choose a topic name. Make it unguessable — `kitchen-hub-7f3a91c2`, not
   `home`. On the public server, anyone who knows the topic can read your
   notifications, so the name is the credential.
3. Subscribe to it in the app.
4. In `.env`:
   ```
   NTFY_TOPIC=kitchen-hub-7f3a91c2
   ```

To self-host: set `NTFY_SERVER=https://ntfy.yourdomain`, plus `NTFY_TOKEN`
if you enable auth.

## Telegram

1. Message [@BotFather](https://t.me/botfather) → `/newbot` → copy the
   token.
2. Message your new bot once — a bot can't message you first.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find
   `"chat":{"id":123456789}`.
4. In `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF…
   TELEGRAM_CHAT_IDS=123456789
   ```

`TELEGRAM_CHAT_IDS` is comma-separated. For a group, add the bot to it and
read the group's (negative) id from the same URL.

## Discord

1. Server Settings → Integrations → Webhooks → **New Webhook**.
2. Choose a channel, **Copy Webhook URL**.
3. In `.env`:
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/…
   ```

Anyone with the URL can post to that channel — treat it as a secret.

## Email

Gmail requires an **App Password**, not your account password:

1. Enable 2-Step Verification.
2. Create one at <https://myaccount.google.com/apppasswords>.
3. In `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop     # spaces are stripped
   MAIL_TO=you@gmail.com,someone@else.com
   ```

For implicit TLS on port 465, set `SMTP_PORT=465` and
`SMTP_STARTTLS=false`.

## LINE

Skip unless you already have a LINE Official Account — the other options
are considerably less work.

1. In the [LINE Developers Console](https://developers.line.biz/), create
   a provider and a **Messaging API** channel.
2. Issue a **long-lived channel access token**.
3. Each recipient must **add the bot as a friend**; a bot cannot message
   someone who hasn't.
4. Collect their `U…` user IDs (via a webhook; the console shows your
   own).
5. In `.env`:
   ```
   LINE_CHANNEL_ACCESS_TOKEN=…
   LINE_USER_IDS=Uxxxxxxxx,Uyyyyyyyy
   ```

The free tier caps monthly pushes, so route frequent jobs elsewhere.

---

## Routing

In `hub/config.yaml`:

```yaml
notify:
  default_channels: [ntfy]

  routes:
    weather: [telegram]
    reports: [email]
    alerts:  [ntfy, email]
```

Rules the router applies:

1. `--dry-run` prints and never sends.
2. Unconfigured channels are skipped, not treated as errors.
3. If nothing is configured, messages go to the log rather than being
   discarded.

## Adding a channel

A channel is a class with `name`, `configured`, and `send()`. Copy
`hub/src/notify/discord.py` (about 30 lines) and add it to `CHANNEL_TYPES`
in `hub/src/notify/__init__.py`.

- Use `chunk_text()` to split long messages rather than truncating.
- Return `False` from `send()` on failure instead of raising.
