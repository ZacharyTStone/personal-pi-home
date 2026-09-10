"""Prints the message.

The only channel that is always configured, so a box with nothing set up
still shows what it would have sent.
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
