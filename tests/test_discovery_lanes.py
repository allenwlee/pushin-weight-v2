"""Provider-denied regression net for optional job/personnel discovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.discovery import plan_discovery_calls, record_discovery_run
from core.models import (
    Brand,
    JobDiscoveryRun,
    PersonnelDiscoveryRun,
    Post,
    PostBrand,
)
from monitor.cycle import CycleRunner, _advance_cursor, _cursor_key, _read_cursor_since
from x_monitor.config import DiscoveryLaneConfig, DiscoveryQueryConfig, load_config
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


def _query(query_id="JD_EN_ORG", *, language="en", family="organization"):
    return DiscoveryQueryConfig(
        query_id=query_id,
        language=language,
        query_family=family,
        primary_terms=['"AI company"'],
        co_occurrence=["hiring"],
    )


def _enabled_lane(query, **overrides):
    values = {
        "enabled": True,
        "query_pack_version": "test-v1",
        "cadence_minutes": 60,
        "max_lookback_hours": 24,
        "max_results": 20,
        "max_pages": 1,
        "max_per_page": 20,
        "request_timeout_seconds": 30,
        "per_cycle_call_ceiling": 1,
        "daily_credit_ceiling": 300,
        "credits_per_result": 15,
        "minimum_credits_per_call": 15,
        "queries": [query],
    }
    values.update(overrides)
    return DiscoveryLaneConfig(**values)


def test_checked_in_discovery_lanes_are_disabled_and_plan_zero_calls():
    cfg = load_config(REPO / "config.yaml")
    assert cfg.discovery.jobs.enabled is False
    assert cfg.discovery.personnel.enabled is False
    assert plan_discovery_calls(cfg, list_id=42, now=NOW) == []


def test_enabled_job_and_personnel_queries_have_separate_bounded_metadata():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs = _enabled_lane(_query())
    cfg.discovery.personnel = _enabled_lane(
        _query("PD_JA_TRANSITION", language="ja", family="transition")
    )

    calls = plan_discovery_calls(cfg, list_id=42, now=NOW)
    assert [call.discovery_lane for call in calls] == ["jobs", "personnel"]
    assert [call.call_id for call in calls] == ["JD_EN_ORG", "PD_JA_TRANSITION"]
    assert all(call.max_results == 20 for call in calls)
    assert all(call.max_pages == 1 for call in calls)
    assert all(call.request_timeout_seconds == 30 for call in calls)
    assert all(
        len(f"{call.query_string} since_time:1 until_time:2") <= 512 for call in calls
    )


def test_enabled_lane_fails_closed_without_queries_or_coherent_page_caps():
    with pytest.raises(ValidationError, match="requires at least one query"):
        DiscoveryLaneConfig(enabled=True, query_pack_version="bad", queries=[])
    with pytest.raises(ValidationError, match="must fit"):
        _enabled_lane(_query(), max_results=21, max_pages=1, max_per_page=20)


def test_cadence_and_daily_credit_ceiling_suppress_calls():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs = _enabled_lane(_query())
    cfg.discovery.personnel.enabled = False
    call = plan_discovery_calls(cfg, list_id=42, now=NOW)[0]
    record_discovery_run(
        call=call,
        run_id="first",
        window=(int((NOW.replace(hour=7)).timestamp()), int(NOW.timestamp())),
        outcome="ok",
        reviewed_post_count=20,
        accepted_post_count=20,
        provider_call_count=1,
        provider_credit_count=300,
    )

    assert plan_discovery_calls(cfg, list_id=42, now=NOW) == []
    assert JobDiscoveryRun.objects.get().provider_credit_count == 300


def test_discovery_cursor_survives_a_new_planner_instance():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs = _enabled_lane(_query())
    cfg.discovery.personnel.enabled = False
    first_call = plan_discovery_calls(cfg, list_id=42, now=NOW)[0]

    assert _advance_cursor(first_call, upper_bound=NOW, now=NOW) is True

    restarted_call = plan_discovery_calls(
        cfg, list_id=42, now=NOW.replace(hour=10)
    )[0]
    assert _cursor_key(restarted_call) == _cursor_key(first_call)
    assert _read_cursor_since(
        restarted_call, now=NOW.replace(hour=10), cfg=cfg
    ) == NOW - timedelta(seconds=cfg.cycle.cursor_overlap_seconds)


def test_remaining_daily_billing_credits_reduce_result_cap():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs = _enabled_lane(
        _query(),
        daily_credit_ceiling=450,
        credits_per_result=15,
        minimum_credits_per_call=15,
    )
    cfg.discovery.personnel.enabled = False
    first = plan_discovery_calls(cfg, list_id=42, now=NOW)[0]
    record_discovery_run(
        call=first,
        run_id="credit-used",
        window=(
            int(NOW.replace(hour=6).timestamp()),
            int(NOW.replace(hour=7).timestamp()),
        ),
        outcome="ok",
        reviewed_post_count=20,
        accepted_post_count=20,
        provider_call_count=1,
        provider_credit_count=300,
    )

    later = plan_discovery_calls(cfg, list_id=42, now=NOW.replace(hour=9))[0]
    assert later.max_results == 10
    assert later.credits_per_result == 15
    assert later.minimum_credits_per_call == 15


def test_personnel_run_keeps_anna_style_unknown_date_boundary():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs.enabled = False
    cfg.discovery.personnel = _enabled_lane(
        _query("PD_EN_TRANSITION", family="transition")
    )
    call = plan_discovery_calls(cfg, list_id=42, now=NOW)[0]
    row = record_discovery_run(
        call=call,
        run_id="anna-run",
        window=(int((NOW.replace(hour=7)).timestamp()), int(NOW.timestamp())),
        outcome="ok",
        reviewed_post_count=1,
        accepted_post_count=1,
        provider_call_count=1,
        provider_credit_count=1,
    )
    assert isinstance(row, PersonnelDiscoveryRun)
    assert row.query_family == "transition"
    assert row.extracted_affiliation_count == 0
    assert "worked" not in row.completion_reason


def test_discovery_run_separates_query_window_from_execution_timestamps():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs = _enabled_lane(_query())
    cfg.discovery.personnel.enabled = False
    call = plan_discovery_calls(cfg, list_id=42, now=NOW)[0]
    window_start = NOW.replace(hour=7)
    first_observation = NOW.replace(hour=8, minute=1)
    second_observation = NOW.replace(hour=8, minute=2)

    row = record_discovery_run(
        call=call,
        run_id="timestamped-run",
        window=(int(window_start.timestamp()), int(NOW.timestamp())),
        outcome="ok",
        reviewed_post_count=1,
        accepted_post_count=0,
        observed_at=first_observation,
    )
    row = record_discovery_run(
        call=call,
        run_id="timestamped-run",
        window=(int(window_start.timestamp()), int(NOW.timestamp())),
        outcome="ok",
        reviewed_post_count=1,
        accepted_post_count=1,
        observed_at=second_observation,
    )

    assert row.window_start == window_start
    assert row.window_end == NOW
    assert row.started_at == first_observation
    assert row.completed_at == second_observation


def test_fetch_respects_discovery_caps():
    cfg = load_config(REPO / "config.yaml")
    runner = CycleRunner(cfg=cfg)
    captured = {}

    class FakeApi:
        timeout_s = 30
        max_retries = 0

        def run_search(self, query, **kwargs):
            captured.update(kwargs)
            return [], False

    call = PlannedCall(
        call_id="JD_EN_ORG",
        call_kind="brand_wide",
        brand_id="*jobs",
        bucket=None,
        query_string='("AI company") (hiring) min_faves:0',
        query_length=39,
        discovery_lane="jobs",
        max_results=7,
        max_pages=1,
        max_per_page=7,
    )
    items, outcome = runner._fetch_tweets(
        call, FakeApi(), window=(1, 2), tip_only=False
    )
    assert items == []
    assert outcome == "ok"
    assert captured["max_results"] == 7
    assert captured["max_pages"] == 1
    assert captured["max_per_page"] == 7


def test_discovery_fetch_never_multiplies_its_result_budget_with_truncation_walks():
    cfg = load_config(REPO / "config.yaml")
    runner = CycleRunner(cfg=cfg)
    calls = 0

    class FakeApi:
        timeout_s = 30
        max_retries = 0

        def run_search(self, _query, **_kwargs):
            nonlocal calls
            calls += 1
            return (
                [
                    {
                        "id": f"result-{calls}",
                        "created_at": "2026-09-10T07:59:00Z",
                    }
                ],
                True,
            )

    call = PlannedCall(
        call_id="JD_EN_ORG",
        call_kind="brand_wide",
        brand_id="*jobs",
        bucket=None,
        query_string='("AI company") (hiring) min_faves:0',
        query_length=39,
        discovery_lane="jobs",
        max_results=20,
        max_pages=1,
        max_per_page=20,
    )

    items, outcome = runner._fetch_tweets(
        call, FakeApi(), window=(1, 2_000_000_000), tip_only=False
    )
    assert outcome == "truncated"
    assert len(items) == 1
    assert calls == 1


def test_fetch_rechecks_discovery_daily_credit_ceiling_before_provider_call():
    cfg = load_config(REPO / "config.yaml")
    cfg.discovery.jobs = _enabled_lane(_query(), daily_credit_ceiling=300)
    cfg.discovery.personnel.enabled = False
    call = plan_discovery_calls(cfg, list_id=42, now=NOW)[0]
    record_discovery_run(
        call=call,
        run_id="spent",
        window=(int(NOW.replace(hour=7).timestamp()), int(NOW.timestamp())),
        outcome="ok",
        reviewed_post_count=20,
        accepted_post_count=20,
        provider_call_count=1,
        provider_credit_count=300,
    )
    provider_called = False

    class FakeApi:
        timeout_s = 30
        max_retries = 0

        def run_search(self, _query, **_kwargs):
            nonlocal provider_called
            provider_called = True
            return [], False

    runner = CycleRunner(cfg=cfg, _clock=lambda: NOW)
    items, outcome = runner._fetch_tweets(
        call,
        FakeApi(),
        window=(int(NOW.replace(hour=7).timestamp()), int(NOW.timestamp())),
    )
    assert items == []
    assert outcome == "daily_credit_ceiling"
    assert provider_called is False


def test_cycle_call_chain_persists_untracked_discovery_post_and_run(monkeypatch):
    cfg = load_config(REPO / "config.yaml")
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    call = PlannedCall(
        call_id="JD_EN_ORG",
        call_kind="brand_wide",
        brand_id="*jobs",
        bucket=None,
        query_string='("AI company") (hiring) min_faves:0',
        query_length=39,
        discovery_lane="jobs",
        query_family="organization",
        language="en",
        query_pack_version="test-v1",
        max_lookback_hours=24,
        max_results=1,
        max_pages=1,
        max_per_page=1,
        daily_credit_ceiling=20,
    )

    class FakeApi:
        timeout_s = 30
        max_retries = 0

        def run_search(self, _query, **_kwargs):
            return (
                [
                    {
                        "id": "untracked-job",
                        "text": "A new AI company is hiring an engineer. Apply here.",
                        "created_at": "2026-09-10T07:59:00Z",
                        "author_id": "untracked-author",
                        "author_handle": "new_ai_company",
                        "author_name": "New AI Company",
                        "_author_present_fields": [
                            "author_handle",
                            "author_name",
                        ],
                    }
                ],
                False,
            )

    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda self: [call])
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda _models: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    monkeypatch.setattr(
        "monitor.cycle.TwitterApiClient.from_env", lambda _purpose: FakeApi()
    )
    monkeypatch.setattr(
        CycleRunner,
        "_run_post_fetch",
        lambda self, *args, **kwargs: {"n_classifications_published": 0},
    )
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist", lambda summary, api: summary
    )

    summary = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    assert summary["calls"][0]["discovery"]["lane"] == "jobs"
    assert Post.objects.filter(pk="untracked-job").exists()
    assert Post.objects.get(pk="untracked-job").source_query_id == "JD_EN_ORG"
    assert PostBrand.objects.filter(
        post_id="untracked-job", brand_id="_unattributed"
    ).exists()
    run = JobDiscoveryRun.objects.get()
    assert run.reviewed_post_count == 1
    assert run.accepted_post_count == 1
    assert run.provider_credit_count == 15
