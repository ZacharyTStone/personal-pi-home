"""SMTP email — the channel for anything you'll want to search later.

Chat pushes are glanceable and disposable; email persists, threads, and
is full-text searchable three years on. Digest-shaped jobs (a daily
reading list, a weekly report) belong here even if you also push them.

Defaults target Gmail, which requires an **App Password** — not your
login password. Turn on 2-Step Verification, then create one at
https://myaccount.google.com/apppasswords . Full walkthrough in
docs/NOTIFIERS.md.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate
from typing import List

from . import Message

log = logging.getLogger(__name__)


class EmailChannel:
    name = "email"

    def __init__(self) -> None:
        self.host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
        self.port = int(os.environ.get("SMTP_PORT", "587").strip() or "587")
        self.user = os.environ.get("SMTP_USER", "").strip()
        # Gmail shows App Passwords in groups of four; the spaces aren't
        # part of the secret, and pasting them in is the single most common
        # way to get an inexplicable auth failure. Strip them.
        self.password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip()
        self.starttls = os.environ.get("SMTP_STARTTLS", "true").strip().lower() != "false"
        self.mail_from = os.environ.get("MAIL_FROM", "").strip() or self.user
        raw = os.environ.get("MAIL_TO", "")
        self.recipients: List[str] = [a.strip() for a in raw.split(",") if a.strip()]

    @property
    def configured(self) -> bool:
        return bool(self.password and self.recipients and self.mail_from)

    def send(self, message: Message) -> bool:
        if not self.configured:
            return False
        msg = EmailMessage()
        msg["Subject"] = message.subject or "(no subject)"
        msg["From"] = self.mail_from
        msg["To"] = ", ".join(self.recipients)
        msg["Date"] = formatdate(localtime=True)
        msg.set_content(message.text)
        if message.html:
            msg.add_alternative(message.html, subtype="html")
        try:
            context = ssl.create_default_context()
            if self.starttls:
                with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                    server.starttls(context=context)
                    if self.user:
                        server.login(self.user, self.password)
                    server.send_message(msg)
            else:  # implicit TLS, port 465
                with smtplib.SMTP_SSL(self.host, self.port, context=context,
                                      timeout=30) as server:
                    if self.user:
                        server.login(self.user, self.password)
                    server.send_message(msg)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("SMTP send failed (%s:%s): %s", self.host, self.port, exc)
            return False
