# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard._resolve_combined_window (Unit 2, v2.0 plan).

Mirrors _resolve_polarity_window's cookie-read pattern but with the wider
window set (1/7/14/30/60/90/180/360) and no clamp.

ALLOWED_COMBINED_WINDOWS = (1, 7, 14, 30, 60, 90, 180, 360)

_resolve_combined_window(req, default=30) reads the `combined_window`
cookie; falls back to default for absent, malformed, or out-of-range
values. Does NOT clamp to window_days.
"""

from __future__ import annotations

from x_monitor.dashboard import (
    ALLOWED_COMBINED_WINDOWS,
    _resolve_combined_window,
)


class _FakeReq:
    """Minimal Flask request shim — just .cookies.get(name)."""

    def __init__(self, cookie_value):
        self._cookies = {} if cookie_value is None else {"combined_window": cookie_value}

    @property
    def cookies(self):
        return self._cookies


# ---------------------------------------------------------------------------
# ALLOWED_COMBINED_WINDOWS constant
# ---------------------------------------------------------------------------


def test_allowed_combined_windows_constant_matches_plan():
    """Plan specifies: 1 / 7 / 14 / 30 / 60 / 90 / 180 / 360."""
    assert ALLOWED_COMBINED_WINDOWS == (1, 7, 14, 30, 60, 90, 180, 360)


# ---------------------------------------------------------------------------
# _resolve_combined_window happy path
# ---------------------------------------------------------------------------


def test_resolve_combined_window_cookie_30_returns_30():
    req = _FakeReq("30")
    assert _resolve_combined_window(req, default=30) == 30


def test_resolve_combined_window_cookie_180_returns_180():
    req = _FakeReq("180")
    assert _resolve_combined_window(req, default=30) == 180


def test_resolve_combined_window_cookie_360_returns_360():
    req = _FakeReq("360")
    assert _resolve_combined_window(req, default=30) == 360


# ---------------------------------------------------------------------------
# _resolve_combined_window edge cases
# ---------------------------------------------------------------------------


def test_resolve_combined_window_no_cookie_returns_default():
    req = _FakeReq(None)
    assert _resolve_combined_window(req, default=30) == 30


def test_resolve_combined_window_malformed_cookie_returns_default():
    """Non-numeric cookie falls back silently (matches _resolve_polarity_window)."""
    req = _FakeReq("abc")
    assert _resolve_combined_window(req, default=30) == 30


def test_resolve_combined_window_empty_string_returns_default():
    req = _FakeReq("")
    assert _resolve_combined_window(req, default=30) == 30


def test_resolve_combined_window_out_of_range_returns_default():
    """400 is not in ALLOWED_COMBINED_WINDOWS, falls back to default."""
    req = _FakeReq("400")
    assert _resolve_combined_window(req, default=30) == 30


def test_resolve_combined_window_negative_returns_default():
    """Negative window is nonsensical, falls back to default."""
    req = _FakeReq("-7")
    assert _resolve_combined_window(req, default=30) == 30


def test_resolve_combined_window_default_override():
    """Default parameter is honored when no cookie is present."""
    req = _FakeReq(None)
    assert _resolve_combined_window(req, default=14) == 14
    assert _resolve_combined_window(req, default=90) == 90