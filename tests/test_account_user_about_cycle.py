"""Scheduled User About lane follows the real selector, claim, and Account gateway."""

import time
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import Account, AccountUserAboutActivation, Post
from monitor.account_user_about_lane import run_scheduled_user_about_lane
from monitor.twitterapi.user_about import (
    FetchBatchResult,
    FetchOutcome,
    UserAboutObservation,
)
from monitor.twitterapi.user_about_service import claim_account
from x_monitor.config import Config, MonotonicDeadline
from x_monitor.query_plan import PlannedCall
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_scheduled_command_reaches_real_runner_and_lane_after_activation(monkeypatch):
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner

    cfg = _cfg()
    calls = [
        PlannedCall(
            call_id="B1", call_kind="brand_wide", brand_id="deepseek",
            bucket=None, query_string="DeepSeek", query_length=8,
        )
    ]
    events = []

    @contextmanager
    def fake_writer_lock(**kwargs):
        yield SimpleNamespace(acquired=True, contention=None)

    class FakeApi:
        pass

    def fake_fetch(self, call, api, **kwargs):
        assert AccountUserAboutActivation.objects.filter(key=1).exists()
        events.append("search_after_activation")
        return [], "ok"

    def fake_lane(**kwargs):
        assert kwargs["cfg"] is cfg
        assert kwargs["cycle_kind"] == "scheduled"
        assert kwargs["dry_run"] is False
        assert isinstance(kwargs["deadline"], MonotonicDeadline)
        assert kwargs["watermark"] == AccountUserAboutActivation.objects.get(
            key=1
        ).activated_at
        events.append("lane_after_search")
        return {"status": "no_due_accounts", "stop_reason": None}

    monkeypatch.setattr("x_monitor.config.load_config", lambda path: cfg)
    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda self: calls)
    monkeypatch.setattr(CycleRunner, "_fetch_tweets", fake_fetch)
    monkeypatch.setattr(
        CycleRunner, "_resolve_window", lambda self, call, now: (1, 2, False)
    )
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda self, *a, **kw: {})
    monkeypatch.setattr(CycleRunner, "_drain_rare_type_hits", lambda self, **kw: {})
    monkeypatch.setattr(CycleRunner, "_request_synthesis_prewarm", lambda self, *a: {})
    monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda self, **kw: [])
    monkeypatch.setattr(cycle_mod, "_build_brand_index", lambda models: object())
    monkeypatch.setattr(cycle_mod, "_load_brand_search_terms", dict)
    monkeypatch.setattr(cycle_mod, "_resolve_x_monitor_list_id", lambda cfg: None)
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env",
        classmethod(
            lambda cls, purpose: (
                FakeApi()
                if purpose is TwitterApiCredentialPurpose.SCHEDULED
                else pytest.fail("scheduled command used the wrong credential purpose")
            )
        ),
    )
    monkeypatch.setattr(
        "monitor.account_user_about_lane.run_scheduled_user_about_lane", fake_lane
    )
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh", lambda *a, **kw: {}
    )
    monkeypatch.setattr(
        "monitor.run_lock.harvest_writer_lock", fake_writer_lock
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_relevancy_client_from_env",
        lambda cfg: None,
    )
    monkeypatch.setattr(
        "x_monitor.relevancy.build_binary_relevancy_llm_call", lambda **kw: None
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_dispatch.dispatch_harvest_completion",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist", lambda summary, api: summary
    )

    output = StringIO()
    call_command("run_cycle", "--scheduled", "--json", stdout=output)

    assert events == ["search_after_activation", "lane_after_search"]


def _cfg(*, enabled=True):
    return Config(
        enabled_models=["minimax"],
        daily_ceiling=100,
        harvest={
            "user_about": {
                "enabled": enabled,
                "provider_qps": 1 if enabled else None,
            }
        },
    )


def _deadline(seconds):
    now = time.monotonic()
    return MonotonicDeadline(
        started_at=now,
        deadline_at=now + seconds,
        tip_target_at=now,
    )


def test_scheduled_lane_uses_scheduled_key_and_persists_success_empty(monkeypatch):
    account = Account.objects.create(author_id="501", handle="scheduled")
    Post.objects.create(tweet_id="5001", author=account)
    keys = []

    def fake_key(purpose):
        keys.append(purpose.value)
        return "test-key"

    monkeypatch.setattr(
        "monitor.account_user_about_lane.require_twitterapi_api_key", fake_key
    )

    async def fake_fetch(selections, **kwargs):
        assert [(item.author_id, item.handle) for item in selections] == [
            ("501", "scheduled")
        ]
        assert kwargs["api_key"] == "test-key"
        observation = UserAboutObservation(
            author_id="501",
            candidates={
                "account_based_in": "",
                "country_code": None,
                "based_in_region_key": None,
                "account_based_in_fetched_at": timezone.now(),
            },
            present_fields={
                "account_based_in",
                "country_code",
                "based_in_region_key",
                "account_based_in_fetched_at",
            },
        )
        return FetchBatchResult(
            outcomes=[FetchOutcome("501", observation, "success", 200, 1)],
            attempts=1,
            retries=0,
            projected_credits=18,
            latencies_ms=[1],
            wall_seconds=0.01,
            stop_reason=None,
        )

    result = run_scheduled_user_about_lane(
        cfg=_cfg(),
        deadline=_deadline(120),
        watermark=timezone.now() - timedelta(minutes=1),
        cycle_kind="scheduled",
        dry_run=False,
        primary_aborted=False,
        fetcher=fake_fetch,
    )

    account.refresh_from_db()
    assert keys == ["scheduled"]
    assert result["attempted"] == 1
    assert result["oldest_due_age_seconds"] is not None
    assert result["accepted"] == 1
    assert result["success_empty"] == 1
    assert account.account_based_in_fetched_at is not None


def test_short_deadline_leaves_first_post_due_without_key_or_http(monkeypatch):
    account = Account.objects.create(author_id="502", handle="deferred")
    Post.objects.create(tweet_id="5002", author=account)

    def no_key(purpose):
        raise AssertionError("deadline should refuse before credentials")

    monkeypatch.setattr(
        "monitor.account_user_about_lane.require_twitterapi_api_key", no_key
    )
    result = run_scheduled_user_about_lane(
        cfg=_cfg(),
        deadline=_deadline(20),
        watermark=timezone.now() - timedelta(minutes=1),
        cycle_kind="scheduled",
        dry_run=False,
        primary_aborted=False,
    )

    assert result["attempted"] == 0
    assert result["deferred"] >= 1
    assert result["oldest_due_age_seconds"] is not None
    assert account.account_based_in_fetched_at is None


def test_scheduled_lane_reports_manual_claim_without_http(monkeypatch):
    account = Account.objects.create(author_id="503", handle="manual-owned")
    Post.objects.create(tweet_id="5003", author=account)
    assert claim_account(author_id="503", owner="manual") is not None
    monkeypatch.setattr(
        "monitor.account_user_about_lane.require_twitterapi_api_key",
        lambda purpose: "test-key",
    )

    async def no_fetch(selections, **kwargs):
        raise AssertionError("claimed account reached HTTP")

    result = run_scheduled_user_about_lane(
        cfg=_cfg(),
        deadline=_deadline(120),
        watermark=timezone.now() - timedelta(minutes=1),
        cycle_kind="scheduled",
        dry_run=False,
        primary_aborted=False,
        fetcher=no_fetch,
    )

    assert result["status"] == "no_due_accounts"
    assert result["attempted"] == 0
