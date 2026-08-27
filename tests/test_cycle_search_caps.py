from __future__ import annotations

import pytest
from django.test import override_settings

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.config import Config, SearchConfig
from x_monitor.query_plan import PlannedCall


@pytest.fixture
def call():
    return PlannedCall(
        call_id="B1",
        call_kind="brand_wide",
        brand_id="deepseek",
        bucket=None,
        query_string="deepseek",
        query_length=8,
    )


@pytest.fixture(autouse=True)
def clear_runtime_search_overrides(monkeypatch):
    for name in (
        "X_MONITOR_CYCLE_LIMIT_PER_CALL",
        "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL",
        "X_MONITOR_CYCLE_MAX_PER_PAGE",
    ):
        monkeypatch.delattr(cycle_mod.settings, name, raising=False)


class CaptureApi:
    def __init__(self):
        self.kwargs = None

    def run_search(self, query, **kwargs):
        self.kwargs = kwargs
        return [], False


def _runner():
    return CycleRunner(
        cfg=Config(
            enabled_models=["deepseek"],
            daily_ceiling=100,
            search=SearchConfig(max_results=37, max_pages=3, max_per_page=11),
        )
    )


def test_fetch_uses_config_search_caps_by_default(call):
    api = CaptureApi()
    assert _runner()._fetch_tweets(call, api, window=(100, 200)) == ([], "ok")
    assert api.kwargs["max_results"] == 37
    assert api.kwargs["max_pages"] == 3
    assert api.kwargs["max_per_page"] == 11


def test_explicit_runtime_search_cap_overrides_win(call):
    with override_settings(
        X_MONITOR_CYCLE_LIMIT_PER_CALL=17,
        X_MONITOR_CYCLE_MAX_PAGES_PER_CALL=2,
        X_MONITOR_CYCLE_MAX_PER_PAGE=7,
    ):
        api = CaptureApi()
        _runner()._fetch_tweets(call, api, window=(100, 200))
    assert api.kwargs["max_results"] == 17
    assert api.kwargs["max_pages"] == 2
    assert api.kwargs["max_per_page"] == 7


def test_deadline_reduces_deep_page_budget_before_starting(call):
    class Deadline:
        @staticmethod
        def remaining():
            # Default client envelope is 60s * 3 attempts + 8s = 188s.
            return 400.0

    api = CaptureApi()
    _runner()._fetch_tweets(call, api, window=(100, 200), deadline=Deadline())
    assert api.kwargs["max_pages"] == 2
    assert api.kwargs["max_results"] == 22
