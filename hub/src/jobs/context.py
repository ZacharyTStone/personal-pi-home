"""What a job is handed when it runs.

A job never reaches outside this object. That's not architecture for its
own sake — it's what lets the runner give every job the same guarantees
(the right clock, its own state file, a working notifier, a retry when
the network is down) without any job having to ask for them.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..notify import BoundRouter
from ..notify._http import get as http_get
from ..store import JobStore


class JobContext:
    def __init__(self, name: str, options: Dict[str, Any], store: JobStore,
                 notify: BoundRouter, now: datetime, dry_run: bool):
        self.name = name
        self.options = options
        #: This job's own SQLite file. See store.py — get/set, and a `seen`
        #: table for "have I already told them about this?".
        self.store = store
        #: Local wall-clock time in your configured timezone — NOT the
        #: container's UTC clock. Always use this, never datetime.now().
        self.now = now
        self.dry_run = dry_run
        self.log = logging.getLogger(f"job.{name}")
        self._notify = notify
        #: How many messages this pass sent — the runner records it so the
        #: dashboard can show "quiet but healthy" apart from "did something".
        self.sent = 0

    def option(self, key: str, default: Any = None) -> Any:
        """A tuning knob from config.yaml → jobs.<name>."""
        return self.options.get(key, default)

    def send(self, subject: str, text: str) -> List[str]:
        """Send a message. Where it goes is config.yaml's business, not
        yours — that's what makes swapping Telegram for email one line."""
        channels = self._notify.send(subject, text)
        if channels or self.dry_run:
            self.store.record_send(subject, text, channels)
            self.sent += 1
        return channels

    def get(self, url: str, **kwargs) -> Optional[Any]:
        """GET some JSON, or None if anything at all went wrong.

        Deliberately forgiving: on an unattended box "no data this pass"
        is a normal outcome, not an exception. If you need the job to
        *retry*, raise — see the module docstring in runner.py.
        """
        response = http_get(url, **kwargs)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            self.log.warning("%s did not return JSON.", url)
            return None
