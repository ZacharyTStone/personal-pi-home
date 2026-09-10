"""Config resolution — including the precedence rule that lets a fork
override one knob without restating the rest."""
from __future__ import annotations

import types

from src import clock
from src.config import Config


def _job(name="sample", **attrs):
    module = types.ModuleType(name)
    module.NAME = name
    module.SUMMARY = "a sample job"
    module.SCHEDULE = attrs.pop("SCHEDULE", {"daily_at": "09:00"})
    module.ENABLED = attrs.pop("ENABLED", True)
    module.OPTIONS = attrs.pop("OPTIONS", {"threshold": 10, "label": "default label"})
    module.run = lambda ctx: None
    return module


def test_job_defaults_apply_when_config_is_silent():
    settings = Config({}).settings_for(_job())
    assert settings.enabled is True
    assert settings.options == {"threshold": 10, "label": "default label"}
    assert settings.schedule.describe() == "daily at 09:00"


def test_config_overrides_one_knob_and_keeps_the_rest():
    """Merging rather than replacing means adding an option to a job file
    can't break somebody's existing config.yaml."""
    options = Config({"jobs": {"sample": {"threshold": 99}}}).settings_for(_job()).options
    assert options == {"threshold": 99, "label": "default label"}


def test_schedule_can_be_overridden():
    config = Config({"jobs": {"sample": {"schedule": {"every": "5m"}}}})
    assert config.settings_for(_job()).schedule.describe() == "every 5m"


def test_a_broken_schedule_falls_back_instead_of_crashing_the_hub():
    config = Config({"jobs": {"sample": {"schedule": {"every": "whenever"}}}})
    assert config.settings_for(_job()).schedule.describe() == "daily at 09:00"


def test_a_non_mapping_job_block_is_ignored():
    config = Config({"jobs": {"sample": "yes please"}})
    assert config.settings_for(_job()).options["threshold"] == 10


def test_enabled_flag_can_be_flipped_either_way():
    assert Config({"jobs": {"sample": {"enabled": False}}}).settings_for(_job()).enabled is False
    off_by_default = _job(ENABLED=False)
    assert Config({"jobs": {"sample": {"enabled": True}}}).settings_for(off_by_default).enabled is True


def test_loading_config_sets_the_hub_timezone():
    Config({"timezone": "Asia/Tokyo"})
    assert clock.timezone_name() == "Asia/Tokyo"


def test_an_unknown_timezone_degrades_to_utc_rather_than_crashing():
    Config({"timezone": "Mars/Olympus_Mons"})
    assert clock.timezone_name() == "UTC"


def test_env_overrides_the_config_file(monkeypatch):
    monkeypatch.setenv("HUB_TIMEZONE", "Europe/Berlin")
    assert Config({"timezone": "Asia/Tokyo"}).timezone == "Europe/Berlin"


def test_one_database_file_per_job(tmp_path):
    config = Config({"data_dir": str(tmp_path)})
    assert config.db_path("bins") == tmp_path / "bins.db"
    assert config.db_path("hello") != config.db_path("bins")


def test_enabled_job_names_is_sorted_and_filtered():
    registry = {"sample": _job(), "off_job": _job("off_job", ENABLED=False)}
    assert Config({}).enabled_job_names(registry) == ["sample"]
