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


def test_scheduled_search_checks_remaining_time_between_pages(call, monkeypatch):
    from x_monitor.x_client import XClient

    class Deadline:
        @staticmethod
        def remaining():
            # Fast responses must not be capped at floor(400 / 188) == two pages.
            return 400.0

    api = XClient(api_key="fake", timeout_s=60, max_retries=2)
    requests = []

    def get(path, params):
        requests.append(dict(params))
        n = len(requests)
        return {
            "tweets": [{"id": str(n), "text": "DeepSeek"}],
            "has_next_page": n < 5, "next_cursor": str(n) if n < 5 else "",
        }

    monkeypatch.setattr(api, "_get", get)
    runner = CycleRunner(cfg=Config(enabled_models=["deepseek"], daily_ceiling=100, search=SearchConfig(max_results=100, max_pages=10)), cycle_kind="scheduled")
    items, outcome = runner._fetch_tweets(call, api, window=(100, 200), deadline=Deadline())
    assert outcome == "ok"
    assert [item["id"] for item in items] == ["1", "2", "3", "4", "5"]
    assert len(requests) == 5


def test_scheduled_429_wait_reserves_time_for_dispatch(call):
    from unittest.mock import Mock

    runner = _runner()
    runner.cycle_kind = "scheduled"
    api = CaptureApi()
    deadline = Mock()
    deadline.remaining.return_value = 194
    runner._fetch_tweets(call, api, window=(100, 200), deadline=deadline)
    assert api.kwargs["can_wait_for_rate_limit"](6)
    deadline.remaining.return_value = 193
    assert not api.kwargs["can_wait_for_rate_limit"](6)


def _routed_client():
    from x_monitor.x_client import XClient

    route = object()
    return XClient(api_key="", twexapi_key="fixture", circuit=route, twex_circuit=route,
                   provider_order=("twitterapi:scheduled", "twexapi"),
                   provider_circuits={"twitterapi:scheduled": route})


def test_single_provider_client_keeps_the_188_second_envelope(call, monkeypatch):
    """KTD6 regression net: the single-provider client still admits pages and
    waits on timeout_s * (max_retries + 1) + 8 = 188 s with no reserved tail."""
    from unittest.mock import Mock

    from x_monitor.x_client import XClient

    api = XClient(api_key="fake", timeout_s=60, max_retries=2)
    assert api.search_request_envelope() == 188
    captured = {}
    monkeypatch.setattr(api, "run_search", lambda query, **kwargs: captured.update(kwargs) or ([], False))
    runner = _runner()
    runner.cycle_kind = "scheduled"
    runner._unsent_calls_after = 15
    deadline = Mock()
    deadline.remaining.return_value = 188
    runner._fetch_tweets(call, api, window=(100, 200), deadline=deadline)
    assert captured["can_start_page"]()
    deadline.remaining.return_value = 187.9
    assert not captured["can_start_page"]()
    deadline.remaining.return_value = 194
    assert captured["can_wait_for_rate_limit"](6)
    deadline.remaining.return_value = 193
    assert not captured["can_wait_for_rate_limit"](6)


def test_routed_client_admits_on_its_derived_envelope_plus_tail(call, monkeypatch):
    """KTD6 (plan 2026-11-24-012909): this rewrites the 188 s pin for the
    multi-route client only. Its envelope is search timeout x attempts + the
    30 s TwexAPI pacing-slot wait + 8 s (15 + 30 + 8 = 53 s), and search keeps
    a derived tail: one metrics-refresh chunk envelope (188 s; rare-type lane
    disabled here). Waits also reserve one paced first page (6 s + 2 s) per
    call not yet sent."""
    from unittest.mock import Mock

    from x_monitor.config import search_tail_seconds

    api = _routed_client()
    assert api.search_request_envelope() == 53
    runner = _runner()
    runner.cycle_kind = "scheduled"
    assert search_tail_seconds(runner.cfg, metrics_request_envelope=188) == 188
    captured = {}
    monkeypatch.setattr(api, "run_search", lambda query, **kwargs: captured.update(kwargs) or ([], False))
    deadline = Mock()
    runner._unsent_calls_after = 3
    runner._fetch_tweets(call, api, window=(100, 200), deadline=deadline)
    deadline.remaining.return_value = 241
    assert captured["can_start_page"]()
    deadline.remaining.return_value = 240.9
    assert not captured["can_start_page"]()
    deadline.remaining.return_value = 6 + 53 + 188 + 3 * 8
    assert captured["can_wait_for_rate_limit"](6)
    deadline.remaining.return_value -= 0.1
    assert not captured["can_wait_for_rate_limit"](6)


def test_rare_type_drain_allocation_joins_the_tail_when_enabled():
    """KTD6: the tail is derived from settings, never a literal."""
    from x_monitor.config import search_tail_seconds

    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100)
    enabled = cfg.model_copy(deep=True)
    enabled.discovery.rare_types.enabled = True
    assert search_tail_seconds(enabled, metrics_request_envelope=188) == 188 + 60
    disabled = cfg.model_copy(deep=True)
    disabled.metrics_refresh.enabled = False
    assert search_tail_seconds(disabled, metrics_request_envelope=188) == 0
