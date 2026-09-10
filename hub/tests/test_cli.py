"""The two commands people run when something isn't working."""
from __future__ import annotations

from src.config import Config
from src.main import cmd_doctor, cmd_list


def _config(tmp_path, **overrides):
    data = {"hub_name": "test-hub", "timezone": "UTC", "data_dir": str(tmp_path)}
    data.update(overrides)
    return Config(data, path=None)


def test_list_shows_schedule_and_next_run(tmp_path, capsys):
    cmd_list(_config(tmp_path))
    out = capsys.readouterr().out
    assert "hello" in out
    assert "daily at 09:00" in out
    assert "NEXT" in out and "never" in out


def test_list_does_not_create_databases(tmp_path):
    """--list must be safe on a machine that has never run the hub."""
    cmd_list(_config(tmp_path))
    assert list(tmp_path.glob("*.db")) == []


def test_doctor_reports_console_as_the_only_live_channel(tmp_path, capsys):
    cmd_doctor(_config(tmp_path))
    out = capsys.readouterr().out
    assert "✔ console" in out
    assert "· telegram" in out


def test_doctor_warns_when_a_channel_is_configured_but_unrouted(tmp_path, capsys,
                                                                monkeypatch):
    """Credentials in .env do nothing until config.yaml routes to them —
    the most likely reason for 'it says ✔ but nothing arrives'."""
    monkeypatch.setenv("NTFY_TOPIC", "some-topic")
    cmd_doctor(_config(tmp_path, notify={"default_channels": ["console"]}))
    out = capsys.readouterr().out
    assert "ntfy configured but nothing is routed to it" in out


def test_doctor_is_quiet_once_the_channel_is_routed(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "some-topic")
    cmd_doctor(_config(tmp_path, notify={"default_channels": ["ntfy"]}))
    assert "nothing is routed" not in capsys.readouterr().out


def test_doctor_does_not_warn_about_a_channel_used_by_one_job(tmp_path, capsys,
                                                              monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "some-topic")
    cmd_doctor(_config(tmp_path, notify={"default_channels": ["console"],
                                         "routes": {"hello": ["ntfy"]}}))
    assert "nothing is routed" not in capsys.readouterr().out
