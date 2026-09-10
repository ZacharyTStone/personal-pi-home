# Notification channels

Set up **one**. You can add more later, and jobs never need changing when
you do — they call `ctx.send()`, and `config.yaml` decides where it lands.

| Channel | Setup | Good for |
|---|---|---|
| [ntfy](#ntfy) | 2 min, no account | Phone pushes, fastest start |
| [Telegram](#telegram) | 5 min | Phone pushes, a chat per person |
| [Discord](#discord) | 1 min | A server you already have |
| [email](#email) | 10 min | Anything you'll want to search later |
| [LINE](#line) | 30 min | Only if you already have a LINE Official Account |
| console | none | Local runs and `--dry-run` |

Check what's live at any point:

```bash
cd hub && python -m src.main --doctor
```

---

## ntfy

No account, no token, no signup.

1. Install the **ntfy** app (iOS / Android), or use the web app.
2. Invent a topic name. Make it unguessable — `kitchen-hub-7f3a91c2`, not
   `home`. **The topic name is the credential**: on the public server,
   anyone who knows it can read your notifications.
3. Subscribe to it in the app.
4. In `.env`:
   ```
   NTFY_TOPIC=kitchen-hub-7f3a91c2
   ```

Self-hosting it later is `NTFY_SERVER=https://ntfy.yourdomain` (plus
`NTFY_TOKEN` if you've turned on auth).

## Telegram

1. Message [@BotFather](https://t.me/botfather) → `/newbot` → copy the token.
2. Message your new bot once (it can't message you first).
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find
   `"chat":{"id":123456789}`.
4. In `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF…
   TELEGRAM_CHAT_IDS=123456789
   ```

`TELEGRAM_CHAT_IDS` is comma-separated, so a household gets one message
each. For a group chat, add the bot to the group and read the group's
(negative) id from the same `getUpdates` URL.

## Discord

The fastest one if you already have a server.

1. Server Settings → Integrations → Webhooks → **New Webhook**.
2. Pick a channel, **Copy Webhook URL**.
3. In `.env`:
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/…
   ```

Anyone with that URL can post to your channel — treat it as a secret.

## Email

Worth setting up even if you also push: chat messages are glanceable and
disposable, email is searchable three years later. Digest-shaped jobs
belong here.

Gmail needs an **App Password**, not your login password:

1. Turn on 2-Step Verification on the account.
2. Create one at <https://myaccount.google.com/apppasswords>.
3. In `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop     # spaces are fine, they're stripped
   MAIL_TO=you@gmail.com,someone@else.com
   ```

Other providers work the same way; for implicit TLS on port 465 set
`SMTP_PORT=465` and `SMTP_STARTTLS=false`.

## LINE

**Skip this unless you already have a LINE Official Account.** It's here
because in some countries LINE is what everyone actually uses, but
setting one up is a chore compared to every option above, and nothing in
this repo assumes you have one.

1. In the [LINE Developers Console](https://developers.line.biz/), create
   a provider and a **Messaging API** channel.
2. Issue a **long-lived channel access token**.
3. Everyone you want to push to must **add the bot as a friend** — a bot
   cannot message someone who hasn't.
4. Collect their `U…` user IDs (a webhook is the reliable way; the
   console shows your own).
5. In `.env`:
   ```
   LINE_CHANNEL_ACCESS_TOKEN=…
   LINE_USER_IDS=Uxxxxxxxx,Uyyyyyyyy
   ```

The free tier caps monthly pushes, so route chatty jobs elsewhere.

---

## Routing

`hub/config.yaml`:

```yaml
notify:
  default_channels: [ntfy]

  routes:
    hello:   [telegram]        # glanceable → phone
    reports: [email]           # searchable → inbox
    alerts:  [ntfy, email]     # important → both
```

Three rules the router enforces, so a half-configured box still behaves:

1. **`--dry-run` always wins.** It prints and never sends, whatever the
   config says.
2. **Unconfigured channels are skipped, not fatal.** No Telegram token
   just means no Telegram.
3. **Console is the floor.** If nothing is configured, messages go to the
   log rather than vanishing — which is what makes a fresh clone work.

## Adding a channel

A channel is a small class with `name`, `configured`, and `send()`. Copy
`hub/src/notify/discord.py` (about 30 lines), add it to `CHANNEL_TYPES`
in `hub/src/notify/__init__.py`, and it's available to every job by name.

Two things to get right, both learned the hard way:

- **Split long messages, don't truncate them.** Use `chunk_text()`. The
  item you needed is always the one that fell off the bottom.
- **Never raise out of `send()`.** Return `False`. A dead transport must
  not take down the job that used it — the router catches it either way,
  but returning cleanly keeps the logs readable.
