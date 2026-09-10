"""ntfy.sh — push notifications with no account at all.

Pick an unguessable topic name, install the ntfy app, subscribe to it,
and set `NTFY_TOPIC`. That's the entire setup: no bot, no token, no
signup. Self-host it later by pointing `NTFY_SERVER` at your own box.

The trade-off is honest and worth stating in the code: on the public
server, anyone who knows your topic name can read your notifications.
Treat the topic as a secret, or don't route private jobs here.
"""
from __future__ import annotations

import logging
import os

from . import Message
from ._http import session

log = logging.getLogger(__name__)


class NtfyChannel:
    name = "ntfy"

    def __init__(self) -> None:
        self.server = (os.environ.get("NTFY_SERVER", "").strip()
                       or "https://ntfy.sh").rstrip("/")
        self.topic = os.environ.get("NTFY_TOPIC", "").strip()
        self.token = os.environ.get("NTFY_TOKEN", "").strip()   # only for private servers

    @property
    def configured(self) -> bool:
        return bool(self.topic)

    def send(self, message: Message) -> bool:
        if not self.configured:
            return False
        headers = {"Title": message.subject.encode("utf-8").decode("latin-1", "replace")}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            resp = session().post(f"{self.server}/{self.topic}",
                                  data=message.text.encode("utf-8"),
                                  headers=headers, timeout=20)
            resp.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("ntfy push failed: %s", exc)
            return False
