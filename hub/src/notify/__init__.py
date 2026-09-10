"""Notification transports, and the router that picks between them.

Jobs never name a transport. They build a `Message` and hand it to
`ctx.send(...)`; the router picks the destination from `config.yaml →
notify` plus whichever channels have credentials in the environment. That
makes switching channels a config change rather than a code change.

Three rules, so a half-configured box still behaves:

1. `--dry-run` prints and never sends.
2. Unconfigured channels are skipped, not treated as errors.
3. Console is the fallback: with nothing configured, messages go to the
   log rather than being discarded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

log = logging.getLogger(__name__)


@dataclass
class Message:
    """One notification, rendered once and adapted per channel.

    `text` is the source of truth — every channel can send it. `html` is
    an optional richer body that only email uses; chat channels ignore it.
    """

    subject: str
    text: str
    html: Optional[str] = None
    # Overrides the routing for this one message (rare — a job that wants
    # a noisy alert to also hit a channel it doesn't normally use).
    channels: Optional[List[str]] = None

    def preview(self, width: int = 200) -> str:
        flat = " ".join(self.text.split())
        return flat[:width] + ("…" if len(flat) > width else "")


class Channel(Protocol):
    """What every transport implements. Keep it this small."""

    name: str

    @property
    def configured(self) -> bool:
        """True when this channel has everything it needs to send."""

    def send(self, message: Message) -> bool:
        """Deliver. Return True if it went out. Never raise — a dead
        transport must not take down the job that used it."""


from .console import ConsoleChannel          # noqa: E402  (avoids a cycle)
from .discord import DiscordChannel          # noqa: E402
from .email import EmailChannel              # noqa: E402
from .line import LineChannel               # noqa: E402
from .ntfy import NtfyChannel                # noqa: E402
from .telegram import TelegramChannel        # noqa: E402

# Add your own here and it becomes available to every job by name.
CHANNEL_TYPES = {
    "console": ConsoleChannel,
    "discord": DiscordChannel,
    "email": EmailChannel,
    "line": LineChannel,
    "ntfy": NtfyChannel,
    "telegram": TelegramChannel,
}


@dataclass
class Router:
    """Fans one message out to the channels a job is routed to."""

    channels: Dict[str, Channel] = field(default_factory=dict)
    default_channels: List[str] = field(default_factory=lambda: ["console"])
    routes: Dict[str, List[str]] = field(default_factory=dict)
    dry_run: bool = False

    def for_job(self, job_name: str) -> "BoundRouter":
        return BoundRouter(self, job_name)

    def channels_for(self, job_name: str, override: Optional[List[str]] = None) -> List[str]:
        wanted = override or self.routes.get(job_name) or self.default_channels
        live = [name for name in wanted
                if name in self.channels and self.channels[name].configured]
        # Rule 3: never let a message disappear because nothing was set up.
        return live or ["console"]

    def send(self, job_name: str, message: Message) -> List[str]:
        """Returns the channels that actually accepted the message."""
        if self.dry_run:
            self.channels["console"].send(message)
            return []
        delivered: List[str] = []
        for name in self.channels_for(job_name, message.channels):
            channel = self.channels[name]
            try:
                if channel.send(message):
                    delivered.append(name)
            except Exception:  # noqa: BLE001 — rule 2: a dead transport is not fatal
                log.exception("Channel %s failed to send %r", name, message.subject)
        return delivered

    def status(self) -> Dict[str, bool]:
        """{channel: configured?} — what `--doctor` and the dashboard show."""
        return {name: bool(ch.configured) for name, ch in sorted(self.channels.items())}


@dataclass
class BoundRouter:
    """The router as one job sees it: `ctx.notify.send(subject, text)`."""

    router: Router
    job_name: str

    def send(self, subject: str, text: str, *, html: Optional[str] = None,
             channels: Optional[List[str]] = None) -> List[str]:
        if not text or not text.strip():
            log.debug("[%s] nothing to send (empty body).", self.job_name)
            return []
        return self.router.send(
            self.job_name,
            Message(subject=subject, text=text, html=html, channels=channels),
        )

    @property
    def dry_run(self) -> bool:
        return self.router.dry_run

    def targets(self) -> List[str]:
        return self.router.channels_for(self.job_name)


def build_router(notify_cfg: Optional[Dict[str, Any]] = None,
                 dry_run: bool = False) -> Router:
    """Instantiate every known channel and wire up the routing table.

    Channels read their own secrets from the environment — the config file
    only ever says *which* channels to use, never what the tokens are, so
    `config.yaml` stays committable.
    """
    cfg = notify_cfg or {}
    channels: Dict[str, Channel] = {}
    for name, factory in CHANNEL_TYPES.items():
        try:
            channels[name] = factory()
        except Exception:  # noqa: BLE001 — a broken channel config != broken hub
            log.exception("Could not initialise the %s channel; skipping it.", name)
    default = [str(c) for c in (cfg.get("default_channels") or ["console"])]
    routes = {str(job): [str(c) for c in (chans or [])]
              for job, chans in (cfg.get("routes") or {}).items()}
    return Router(channels=channels, default_channels=default,
                  routes=routes, dry_run=dry_run)
