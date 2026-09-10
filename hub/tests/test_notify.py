"""Routing rules — the three that keep a half-configured box behaving."""
from __future__ import annotations

from src.notify import Message, Router, build_router
from src.notify.telegram import chunk_text


def test_dry_run_sends_nothing_anywhere(channel):
    router = Router(channels={"recording": channel, "console": channel},
                    default_channels=["recording"], dry_run=True)
    delivered = router.send("job", Message("Subject", "body"))
    assert delivered == []           # nothing was *delivered*…
    assert len(channel.sent) == 1    # …but you still saw it on the console


def test_unconfigured_channels_are_skipped_not_fatal(channel):
    from tests.conftest import RecordingChannel
    dead = RecordingChannel(configured=False)
    router = Router(channels={"live": channel, "dead": dead, "console": channel},
                    default_channels=["dead", "live"])
    assert router.send("job", Message("s", "b")) == ["live"]
    assert dead.sent == []


def test_console_is_the_floor(channel):
    """Nothing configured must never mean the message disappears."""
    from tests.conftest import RecordingChannel
    console = RecordingChannel()
    dead = RecordingChannel(configured=False)
    router = Router(channels={"console": console, "dead": dead},
                    default_channels=["dead"])
    assert router.send("job", Message("s", "b")) == ["console"]
    assert len(console.sent) == 1


def test_per_job_routes_override_the_default(channel):
    from tests.conftest import RecordingChannel
    other = RecordingChannel()
    router = Router(channels={"a": channel, "b": other, "console": channel},
                    default_channels=["a"], routes={"noisy": ["b"]})
    assert router.channels_for("quiet") == ["a"]
    assert router.channels_for("noisy") == ["b"]


def test_a_channel_that_raises_does_not_break_the_send(channel):
    class Exploding:
        name = "boom"
        configured = True

        def send(self, message):
            raise RuntimeError("the API is down")

    router = Router(channels={"boom": Exploding(), "ok": channel, "console": channel},
                    default_channels=["boom", "ok"])
    # The working channel still gets it — one dead transport is not an outage.
    assert router.send("job", Message("s", "b")) == ["ok"]


def test_empty_messages_are_not_sent(channel):
    router = Router(channels={"recording": channel, "console": channel},
                    default_channels=["recording"])
    assert router.for_job("job").send("Subject", "   ") == []
    assert channel.sent == []


def test_build_router_reads_config_not_secrets():
    router = build_router({"default_channels": ["email"],
                           "routes": {"bins": ["telegram"]}})
    assert router.default_channels == ["email"]
    assert router.routes == {"bins": ["telegram"]}
    # With no credentials in the environment, only console is live.
    assert [n for n, ok in router.status().items() if ok] == ["console"]


def test_message_preview_is_flattened_and_bounded():
    message = Message("s", "line one\n\n   line two   \n" + "x" * 400)
    assert "\n" not in message.preview()
    assert len(message.preview()) <= 201


# ── chunking: the shared "don't truncate" rule ──
def test_short_text_is_one_chunk():
    assert chunk_text("hello", 100) == ["hello"]


def test_long_text_splits_on_line_boundaries_losing_nothing():
    text = "\n".join(f"line {i}" for i in range(200))
    chunks = chunk_text(text, 100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # Truncation is the bug you find a month later: the item you needed
    # was the one that fell off the bottom.
    rejoined = "\n".join(chunks)
    for i in range(200):
        assert f"line {i}" in rejoined


def test_a_single_over_long_line_is_hard_split():
    chunks = chunk_text("x" * 250, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == "x" * 250
