"""One shared HTTP helper for every channel and job.

Small, but it exists for a reason: an always-on box that hangs forever on
a socket read is indistinguishable from a dead one. Every outbound call
in this repo goes through here so that a timeout and a real User-Agent
are impossible to forget.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
USER_AGENT = "personal-pi-home/1.0 (+https://github.com/)"

_session: Optional[requests.Session] = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT})
    return _session


def get(url: str, *, params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_TIMEOUT) -> Optional[requests.Response]:
    """GET that returns None instead of raising. Callers on an unattended
    box almost always want "no data this pass", not a traceback."""
    try:
        resp = session().get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as exc:  # noqa: BLE001
        log.warning("GET %s failed: %s", url, exc)
        return None


def post_json(url: str, payload: Dict[str, Any], *,
              headers: Optional[Dict[str, str]] = None,
              timeout: int = DEFAULT_TIMEOUT) -> bool:
    try:
        resp = session().post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("POST %s failed: %s", url, exc)
        return False
