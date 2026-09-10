"""The always-available channel: print it.

This is what makes `--dry-run` a real preview and what catches messages
on a box where nothing else is set up yet. It is deliberately the only
channel that is always `configured`.
"""
from __future__ import annotations

from . import Message

_RULE = "─" * 62


class ConsoleChannel:
    name = "console"

    @property
    def configured(self) -> bool:
        return True

    def send(self, message: Message) -> bool:
        print(f"\n{_RULE}\n  {message.subject}\n{_RULE}")
        print(message.text)
        print(_RULE + "\n")
        return True
