# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.apify and x_monitor.cookies."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from x_monitor.apify import (
    ApifyAuthError,
    ApifyClient,
    ApifyRateLimitError,
    ApifyServerError,
    PROBE_HANDLE,
)
from x_monitor.cookies import CookieMissingError, load_cookies


# --- cookies --------------------------------------------------------------


def test_load_cookies_missing_file():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(CookieMissingError, match="not found"):
            load_cookies(Path(d) / "nonexistent.json")


def test_load_cookies_empty_auth_token():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cookies.json"
        p.write_text(json.dumps({"auth_token": "", "ct0": "abc"}))
        with pytest.raises(CookieMissingError, match="auth_token"):
            load_cookies(p)


def test_load_cookies_empty_ct0():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cookies.json"
        p.write_text(json.dumps({"auth_token": "abc", "ct0": ""}))
        with pytest.raises(CookieMissingError, match="ct0"):
            load_cookies(p)


def test_load_cookies_valid():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cookies.json"
        p.write_text(json.dumps({"auth_token": "abc", "ct0": "def"}))
        os.chmod(p, 0o600)
        c = load_cookies(p)
        assert c["auth_token"] == "abc"
        assert c["ct0"] == "def"


def test_load_cookies_invalid_json():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cookies.json"
        p.write_text("not json {")
        with pytest.raises(CookieMissingError, match="JSON"):
            load_cookies(p)


# --- ApifyClient error mapping -------------------------------------------


def _mock_response(status: int, body: dict | list | str = {}) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.text = json.dumps(body) if isinstance(body, (dict, list)) else body
    m.json.return_value = body
    m.raise_for_status = MagicMock()
    return m


def test_run_search_raises_auth_error_on_401():
    client = ApifyClient(token="x")
    with patch.object(requests, "post", return_value=_mock_response(401, "unauth")):
        with pytest.raises(ApifyAuthError):
            client.run_search("from:x")


def test_run_search_raises_rate_limit_on_429():
    client = ApifyClient(token="x", max_retries=0)
    with patch.object(requests, "post", return_value=_mock_response(429, "rate")):
        with pytest.raises(ApifyRateLimitError):
            client.run_search("from:x")


def test_run_search_raises_server_error_on_500():
    client = ApifyClient(token="x", max_retries=0)
    with patch.object(requests, "post", return_value=_mock_response(500, "boom")):
        with pytest.raises(ApifyServerError):
            client.run_search("from:x")


def test_run_search_returns_empty_on_unfinished_run():
    client = ApifyClient(token="x", max_retries=0)
    # Run with no datasetId AND not finished — _wait_for_run should be called
    # and return a "still no dataset" result that produces an empty list.
    run_resp = {"id": "run-1", "status": "RUNNING", "defaultDatasetId": None}
    finished_resp = {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": None}
    with patch.object(requests, "post", return_value=_mock_response(201, run_resp)):
        with patch.object(client, "_wait_for_run", return_value=finished_resp):
            out = client.run_search("from:x", max_results=5)
            assert out == []


# --- probe_cookie ---------------------------------------------------------


def test_probe_cookie_returns_false_on_401():
    client = ApifyClient(token="x", max_retries=0)
    with patch.object(client, "run_search", side_effect=ApifyAuthError("unauth")):
        assert client.probe_cookie(cookies={"auth_token": "a", "ct0": "b"}) is False


def test_probe_cookie_returns_false_on_zero_results():
    client = ApifyClient(token="x", max_retries=0)
    with patch.object(client, "run_search", return_value=[]):
        assert client.probe_cookie(cookies={"auth_token": "a", "ct0": "b"}) is False


def test_probe_cookie_returns_true_on_results():
    client = ApifyClient(token="x", max_retries=0)
    with patch.object(client, "run_search", return_value=[{"id": "1", "text": "hi"}]):
        assert client.probe_cookie(cookies={"auth_token": "a", "ct0": "b"}) is True


def test_probe_cookie_does_not_treat_transient_as_rot():
    client = ApifyClient(token="x", max_retries=0)
    with patch.object(client, "run_search", side_effect=ApifyServerError("5xx")):
        # 5xx is transient; probe_cookie should return True (do not flag
        # cookie rot on transient errors).
        assert client.probe_cookie(cookies={"auth_token": "a", "ct0": "b"}) is True


# --- run_followers -------------------------------------------------------


def test_run_followers_normalizes_response():
    client = ApifyClient(token="x", max_retries=0)
    run_resp = {
        "id": "run-1",
        "status": "SUCCEEDED",
        "defaultDatasetId": "ds-1",
    }
    with patch.object(requests, "post", return_value=_mock_response(201, run_resp)):
        with patch.object(
            requests,
            "get",
            return_value=_mock_response(
                200,
                [
                    {"userName": "alice", "name": "Alice", "followers_count": 100},
                    {"screen_name": "bob", "display_name": "Bob", "followerCount": 50},
                ],
            ),
        ):
            out = client.run_followers("MiniMaxAI")
            assert len(out) == 2
            assert out[0]["handle"] == "alice"
            assert out[0]["follower_count"] == 100
            assert out[1]["handle"] == "bob"
            assert out[1]["follower_count"] == 50


def test_from_env_requires_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    with pytest.raises(CookieMissingError, match="APIFY_API_TOKEN"):
        ApifyClient.from_env()


def test_from_env_reads_token(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "abc")
    c = ApifyClient.from_env()
    assert c.token == "abc"
    assert c.actor == "automation-lab/twitter-scraper"
