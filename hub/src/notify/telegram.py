"""Telegram Bot API — the lowest-friction phone push there is.

Two values in `.env` and you're done (docs/NOTIFIERS.md):

    TELEGRAM_BOT_TOKEN=123456:ABC…      # from @BotFather
    TELEGRAM_CHAT_IDS=11111,22222       # you, your partner, a group…

Comma-separated recipients so a household gets one message each, which is
the shape almost every job in a home hub wants.
"""
from __future__ import annotations

import logging
import os
from typing import List

from . import Message
from ._http import post_json

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"
# Telegram rejects anything over 4096 characters outright.
_LIMIT = 3900


class TelegramChannel:
    name = "telegram"

    def __init__(self) -> None:
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        raw = os.environ.get("TELEGRAM_CHAT_IDS", "")
        self.chat_ids = [c.strip() for c in raw.split(",") if c.strip()]

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_ids)

    def send(self, message: Message) -> bool:
        if not self.configured:
            return False
        body = f"{message.subject}\n\n{message.text}" if message.subject else message.text
        ok = False
        for chunk in chunk_text(body, _LIMIT):
            for chat_id in self.chat_ids:
                url = _API.format(token=self.token)
                if post_json(url, {"chat_id": chat_id, "text": chunk,
                                   "disable_web_page_preview": True}):
                    ok = True
        return ok


def chunk_text(text: str, limit: int) -> List[str]:
    """Split on line boundaries rather than truncating.

    Truncation is the bug you find a month later: the interesting item was
    the one that fell off the bottom. Splitting keeps every line, and
    keeps them readable by never cutting mid-line unless a single line is
    itself longer than the limit.
    """
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:            # a single monster line
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current.rstrip("\n"))
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip("\n"))
    return chunks
