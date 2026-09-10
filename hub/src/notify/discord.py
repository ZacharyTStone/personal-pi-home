"""Discord — a webhook URL and nothing else.

No bot, no OAuth, no account beyond the server you already have:
Server Settings → Integrations → Webhooks → Copy URL, paste it into
`DISCORD_WEBHOOK_URL`. The easiest channel to get working in under a
minute, which makes it a good first one to try in a fresh fork.
"""
from __future__ import annotations

import os

from . import Message
from ._http import post_json
from .telegram import chunk_text

_LIMIT = 1900   # Discord's hard cap is 2000 characters per message


class DiscordChannel:
    name = "discord"

    def __init__(self) -> None:
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, message: Message) -> bool:
        if not self.configured:
            return False
        body = f"**{message.subject}**\n{message.text}" if message.subject else message.text
        ok = False
        for chunk in chunk_text(body, _LIMIT):
            if post_json(self.webhook_url, {"content": chunk}):
                ok = True
        return ok
