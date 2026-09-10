"""LINE Messaging API — multicast push.

Worth knowing before you wire it up: a bot can only push to people who
have added it as a friend, and the free tier caps how many messages you
can send per month — so route chatty jobs elsewhere.

    LINE_CHANNEL_ACCESS_TOKEN=…     # a long-lived channel access token
    LINE_USER_IDS=Uxxxx,Uyyyy       # everyone who has friended the bot

See docs/NOTIFIERS.md for how to get both.
"""
from __future__ import annotations

import os
from typing import List

from . import Message
from ._http import post_json
from .telegram import chunk_text

_MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"
_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_LIMIT = 4800            # LINE's per-message cap is 5000 characters
_MSGS_PER_REQUEST = 5    # …and at most 5 message objects per request


class LineChannel:
    name = "line"

    def __init__(self) -> None:
        self.token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        raw = os.environ.get("LINE_USER_IDS", "")
        self.user_ids = [u.strip() for u in raw.split(",") if u.strip()]

    @property
    def configured(self) -> bool:
        return bool(self.token and self.user_ids)

    def send(self, message: Message) -> bool:
        if not self.configured:
            return False
        body = f"{message.subject}\n\n{message.text}" if message.subject else message.text
        headers = {"Authorization": f"Bearer {self.token}"}
        ok = False
        for batch in _batched(chunk_text(body, _LIMIT), _MSGS_PER_REQUEST):
            payload = {"messages": [{"type": "text", "text": c} for c in batch]}
            # multicast needs a list and at least two recipients to be worth
            # it; push is the one-recipient endpoint.
            if len(self.user_ids) > 1:
                payload["to"] = self.user_ids
                url = _MULTICAST_URL
            else:
                payload["to"] = self.user_ids[0]
                url = _PUSH_URL
            if post_json(url, payload, headers=headers):
                ok = True
        return ok


def _batched(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]
