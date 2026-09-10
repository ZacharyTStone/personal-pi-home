"""Shared fixtures.

The rule the whole suite follows: **no network, no credentials, no
dependence on the real clock.** Every job here must be testable with an
empty `.env` on a laptop in a tunnel — because that's also the state a
fresh fork is in, and this suite is what keeps that state working.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import clock                      # noqa: E402
from src.config import Config              # noqa: E402
from src.jobs.context import JobContext    # noqa: E402
from src.notify import Message, Router     # noqa: E402
from src.store import JobStore             # noqa: E402


class RecordingChannel:
    """Captures instead of sending, so tests can assert on exactly what
    would have gone out."""

    name = "recording"

    def __init__(self, configured: bool = True):
        self.sent: list = []
        self._configured = configured

    @property
    def configured(self) -> bool:
        return self._configured

    def send(self, message: Message) -> bool:
        self.sent.append(message)
        return True


@pytest.fixture(autouse=True)
def fixed_timezone():
    """Pin the clock so a test that passes in Berlin passes in CI."""
    clock.set_timezone("UTC")
    yield
    clock.set_timezone("UTC")


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    """Make it impossible for the suite to use a developer's real keys."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS", "DISCORD_WEBHOOK_URL",
                "SMTP_PASSWORD", "MAIL_TO", "NTFY_TOPIC", "HUB_TIMEZONE"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def store(tmp_path) -> JobStore:
    with JobStore(tmp_path / "test.db") as job_store:
        yield job_store


@pytest.fixture
def channel() -> RecordingChannel:
    return RecordingChannel()


@pytest.fixture
def make_ctx(tmp_path, channel):
    """A JobContext wired to a temp database and a recording channel."""
    def _make(name: str = "test", options: dict = None,
              now: datetime = None, dry_run: bool = False) -> JobContext:
        router = Router(channels={"recording": channel, "console": channel},
                        default_channels=["recording"], dry_run=dry_run)
        return JobContext(name=name, options=options or {},
                          store=JobStore(tmp_path / f"{name}.db"),
                          notify=router.for_job(name),
                          now=now or datetime(2026, 6, 1, 9, 0),
                          dry_run=dry_run)
    return _make


@pytest.fixture
def config(tmp_path) -> Config:
    return Config({"hub_name": "test-hub", "timezone": "UTC",
                   "data_dir": str(tmp_path)}, path=None)
