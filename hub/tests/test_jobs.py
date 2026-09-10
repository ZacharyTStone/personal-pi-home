"""The example job, entirely offline.

`hello` is the file people copy, so these tests double as a statement of
what a job has to get right.
"""
from __future__ import annotations

from datetime import datetime

from src.jobs import all_jobs, discover
from src.jobs import hello


# ══ discovery — one file is one job ═══════════════════════════════════
def test_every_job_file_is_discovered():
    jobs = discover()
    assert "hello" in jobs


def test_every_job_declares_what_the_runner_needs():
    for name, module in all_jobs().items():
        assert getattr(module, "NAME", None) == name
        assert getattr(module, "SUMMARY", ""), f"{name} needs a SUMMARY for --list"
        assert callable(module.run)
        # OPTIONS is the documented surface: config.yaml can only sensibly
        # override knobs the job actually declares.
        assert isinstance(getattr(module, "OPTIONS", {}), dict)


def test_a_file_without_run_is_skipped_not_fatal(tmp_path, monkeypatch):
    """A half-written job file must not stop the hub from starting."""
    import src.jobs as jobs_pkg
    broken = tmp_path / "broken.py"
    broken.write_text("NAME = 'broken'\n", encoding="utf-8")
    monkeypatch.setattr(jobs_pkg, "__file__", str(tmp_path / "__init__.py"))
    assert "broken" not in discover()
    discover()   # put the real registry back for the rest of the suite


# ══ hello — the do-nothing daily ══════════════════════════════════════
def test_hello_says_hello(make_ctx, channel):
    ctx = make_ctx("hello", hello.OPTIONS)
    hello.run(ctx)
    assert len(channel.sent) == 1
    assert "Hello from your hub" in channel.sent[0].text


def test_hello_counts_across_runs(make_ctx, channel):
    """State survives the process — the point of the per-job database."""
    ctx = make_ctx("hello", hello.OPTIONS)
    hello.run(ctx)
    hello.run(ctx)
    assert ctx.store.get_meta("count") == "2"
    assert "Run number 2" in channel.sent[-1].text


def test_hello_uses_the_configured_greeting(make_ctx, channel):
    ctx = make_ctx("hello", {"greeting": "Oi"})
    hello.run(ctx)
    assert channel.sent[0].subject == "Oi"


def test_hello_uses_the_hubs_clock_not_the_hosts(make_ctx, channel):
    ctx = make_ctx("hello", hello.OPTIONS, now=datetime(2026, 6, 1, 7, 30))
    hello.run(ctx)
    assert "Monday 01 June, 07:30" in channel.sent[0].text
