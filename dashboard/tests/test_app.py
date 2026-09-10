from __future__ import annotations

import sqlite3

from tests.conftest import make_job_db


def test_status_on_a_box_that_has_never_run(client):
    """A fresh clone must render, not 500. This is the first thing a new
    user sees, and an error page here reads as 'the whole thing is broken'."""
    body = client.get("/api/status").json()
    assert body["jobs"] == []
    assert body["hub_name"] == "test-hub"


def test_status_reports_each_job(client):
    make_job_db(client.data_dir / "hello.db")
    make_job_db(client.data_dir / "bins.db")
    jobs = {j["name"]: j for j in client.get("/api/status").json()["jobs"]}
    assert set(jobs) == {"hello", "bins"}
    assert jobs["hello"]["healthy"] is True
    assert jobs["hello"]["schedule"] == "daily at 09:00"
    assert jobs["hello"]["last_run"]["sent"] == 1


def test_a_failed_job_is_visibly_unhealthy(client):
    """The one thing this page exists to make obvious."""
    make_job_db(client.data_dir / "bins.db", status="error",
                error="feed unreachable", sends=0)
    job = client.get("/api/status").json()["jobs"][0]
    assert job["healthy"] is False
    assert job["last_run"]["error"] == "feed unreachable"


def test_a_job_not_in_config_still_shows_up(client):
    """State on disk is the source of truth for what's running — a job
    someone removed from config.yaml but left running must not vanish."""
    make_job_db(client.data_dir / "mystery.db")
    names = [j["name"] for j in client.get("/api/status").json()["jobs"]]
    assert "mystery" in names


def test_an_older_schema_does_not_break_the_page(client):
    """The dashboard is read-only and can't migrate anything, so a table a
    newer hub hasn't created yet must read as 'no rows', not a 500."""
    path = client.data_dir / "old.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")
    conn.commit()
    conn.close()
    job = [j for j in client.get("/api/status").json()["jobs"] if j["name"] == "old"][0]
    assert job["last_run"] is None and job["counts"]["runs"] == 0


def test_job_detail(client):
    make_job_db(client.data_dir / "hello.db")
    body = client.get("/api/jobs/hello").json()
    assert len(body["runs"]) == 1
    assert body["meta"]["last_run"] == "2026-06-01T09:00:00"


def test_job_detail_404s_for_an_unknown_job(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_log_tail_when_there_is_no_log(client):
    assert client.get("/api/log").json()["lines"] == []


def test_log_tail_returns_the_end_of_the_file(client):
    (client.data_dir / "hub.log").write_text(
        "\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    lines = client.get("/api/log?lines=10").json()["lines"]
    assert lines[-1] == "line 499" and len(lines) == 10


def test_config_endpoint_does_not_leak_routing_secrets(client):
    """Nothing secret is supposed to be in config.yaml, but this page may
    end up more exposed than intended — so it doesn't rely on that."""
    body = client.get("/api/config").json()
    assert body["hub_name"] == "test-hub"
    assert set(body["notify"]) == {"default_channels"}


def test_index_serves_the_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "personal-pi-home" in response.text


def test_the_dashboard_never_writes_to_job_state(client):
    """The read-only mount is the real guarantee; this pins the intent."""
    make_job_db(client.data_dir / "hello.db")
    import app as app_module
    conn = app_module.connect("hello")
    try:
        with conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('x','y')")
    except sqlite3.OperationalError as exc:
        assert "readonly" in str(exc).lower()
    else:                                   # pragma: no cover
        raise AssertionError("the dashboard opened a writable connection")
