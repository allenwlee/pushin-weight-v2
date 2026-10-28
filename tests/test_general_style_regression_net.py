"""Server outputs the General-style homepage port must leave unchanged.

The baseline under ``tests/fixtures/general_style_baseline/`` was captured from
the deployed revision before any product change, with the clock fixed and the
deterministic v22 fixture seeded. Set ``GENERAL_STYLE_BASELINE_CAPTURE=1`` to
rewrite it; a normal run compares every key and value. Values the port changes
on purpose are listed in ``INTENDED_CHANGES`` and checked against their new
strings instead.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from monitor.views import _clear_home_pulse_cache, _each_tab_entries
from tests.test_chart_harvest_coverage import record_harvest
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

BASELINE_DIR = Path(__file__).parent / "fixtures" / "general_style_baseline"
FIXED_NOW = datetime(2026, 10, 27, 12, 2, 30, tzinfo=dt_timezone.utc)
LOCALES = ("en", "zh_cn", "ja")
WINDOWS = (1, 7, 30, 365)
EACH_BRAND = "deepseek"
CAPTURE = os.environ.get("GENERAL_STYLE_BASELINE_CAPTURE") == "1"
VOLATILE_KEYS = frozenset({"id", "pk", "post_id", "account_id", "run_id"})

# Exact replacements the port makes on purpose: {baseline string: new string}.
INTENDED_CHANGES: dict[str, str] = {}

_DATA_HOME = re.compile(r"data-home='([^']*)'")


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _apply_intended(value: Any) -> Any:
    if isinstance(value, str):
        for old, new in INTENDED_CHANGES.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, dict):
        return {key: _apply_intended(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_apply_intended(item) for item in value]
    return value


def _chart_payload(client, window: int, locale: str) -> dict:
    _clear_home_pulse_cache()
    response = client.get(
        "/chart.html", {"window": window, "locale": locale, "timezone": "UTC"}
    )
    assert response.status_code == 200
    match = _DATA_HOME.search(response.content.decode())
    assert match, "chart fragment carries no data-home payload"
    return json.loads(html.unescape(match.group(1)))


def _each_payload(client, tab: str, window: int, locale: str) -> dict:
    _clear_home_pulse_cache()
    response = client.get(
        "/dashboard/each/chart/",
        {"brand": EACH_BRAND, "tab": tab, "window": window, "locale": locale},
    )
    assert response.status_code == 200, response.content
    return response.json()


def _feed_pages(client, locale: str) -> list[dict]:
    pages = []
    cursor = None
    for _ in range(2):
        params = {"locale": locale, "limit": 25}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/feed/", params)
        assert response.status_code == 200
        payload = response.json()
        pages.append(payload)
        cursor = payload.get("next_cursor")
        if not cursor:
            break
    return pages


@pytest.fixture
def frozen_home(db, settings):
    settings.SECURE_SSL_REDIRECT = False
    with patch("django.utils.timezone.now", return_value=FIXED_NOW):
        seed_real_home_orm(fixture_from_oracle())
        record_harvest(FIXED_NOW, finished_at=FIXED_NOW, staggered=False)
        _clear_home_pulse_cache()
        yield


def _captures(client) -> dict[str, Any]:
    captures: dict[str, Any] = {}
    for locale in LOCALES:
        for window in WINDOWS:
            captures[f"chart-{window}d-{locale}"] = _chart_payload(client, window, locale)
            for tab in _each_tab_entries(locale):
                captures[f"each-{tab}-{window}d-{locale}"] = _each_payload(
                    client, tab, window, locale
                )
        captures[f"feed-{locale}"] = _feed_pages(client, locale)
    return captures


def test_server_outputs_match_the_pre_port_baseline(client, frozen_home):
    with patch("django.utils.timezone.now", return_value=FIXED_NOW):
        captures = {name: _normalize(value) for name, value in _captures(client).items()}

    if CAPTURE:
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        for name, value in captures.items():
            (BASELINE_DIR / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return

    stored = sorted(path.stem for path in BASELINE_DIR.glob("*.json"))
    assert stored == sorted(captures), "baseline set differs from the captured surfaces"
    for name, value in captures.items():
        baseline = json.loads((BASELINE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert value == _apply_intended(baseline), f"{name} changed outside the intended edits"
