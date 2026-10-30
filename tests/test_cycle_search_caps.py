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
    from x_monitor.apify import TwitterApiClient

    class Deadline:
        @staticmethod
        def remaining():
            # Fast responses must not be capped at floor(400 / 188) == two pages.
            return 400.0

    api = TwitterApiClient(api_key="fake", timeout_s=60, max_retries=2)
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


class NoHttpApi:
    """A captured page must be read from the capture, never re-requested."""

    timeout_s = 30
    max_retries = 0

    def run_search_pages(self, *args, **kwargs):
        pytest.fail("captured page triggered an HTTP request")


class AlmostExpiredDeadline:
    @staticmethod
    def remaining():
        # Below the 30s * 1 attempt + 8s = 38s request envelope.
        return 10.0


def _captured(*, staging_capture):
    from monitor.backfill_resources import BackfillBudget, BackfillContext
    from x_monitor.apify import search_page_from_response

    received = search_page_from_response({
        "tweets": [{"id": "7", "text": "DeepSeek release", "lang": "en",
                    "createdAt": "Sun Aug 09 00:10:00 +0000 2026",
                    "author": {"id": "author-7", "userName": "user7"}}],
        "has_next_page": False, "next_cursor": "",
    })
    pages = iter([received])
    runner = CycleRunner(
        cfg=Config(enabled_models=["deepseek"], daily_ceiling=100),
        cycle_kind="backfill",
        _backfill_context=BackfillContext(
            budget=BackfillBudget(max_api_requests=1, max_llm_calls=0, run_seconds=120),
            captured_pages=pages, staging_capture=staging_capture,
        ),
    )
    return runner, pages


# 2026-08-09 00:00-00:15 UTC contains the captured post's createdAt.
CAPTURED_WINDOW = (1786233600, 1786234500)


def test_staging_capture_is_committed_with_less_than_one_request_envelope(call):
    runner, pages = _captured(staging_capture=True)
    items, outcome = runner._fetch_tweets(
        call, NoHttpApi(), window=CAPTURED_WINDOW, deadline=AlmostExpiredDeadline(),
    )
    assert (outcome, [item["id"] for item in items]) == ("ok", ["7"])
    receipt = runner._backfill_fetch_receipt
    assert receipt["pages_received"] == 1 and receipt["drained"] is True
    assert next(pages, None) is None


def test_archive_capture_keeps_the_request_envelope_budget(call):
    # Archive-mode Prefetcher captures replay a stored body on the next run,
    # so they keep today's deadline check and the page stays unread.
    runner, pages = _captured(staging_capture=False)
    assert runner._fetch_tweets(
        call, NoHttpApi(), window=CAPTURED_WINDOW, deadline=AlmostExpiredDeadline(),
    ) == ([], "truncated")
    assert runner._backfill_fetch_receipt == {}
    assert next(pages, None) is not None
