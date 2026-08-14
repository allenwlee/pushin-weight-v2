"""PostgreSQL contracts for the provider-free public headline projection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html import unescape

import pytest

from core.models import Brand, TrendNarrativeSubject
from monitor.trend_narrative_lifecycle import (
    mark_transport_completed,
    mark_transport_started,
    publish_generation,
    record_no_call_check,
    reserve_generation,
)
from monitor.trend_narrative_projection import project_trend_narrative
from monitor.views import _build_home_chart_payload
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _config(*, enabled: bool = True) -> HeadlineNarrativeConfig:
    return HeadlineNarrativeConfig(serving_enabled=enabled)


def _publish(
    window_days: int = 1,
    *,
    coverage_state: str = "sufficient",
    output_schema_version: int = 2,
):
    brand = Brand.objects.create(
        nickname="minimax",
        display_name="MiniMax",
        display_name_en="MiniMax",
        display_name_zh_cn="MiniMax",
    )
    facts = {
        "snapshot_schema_version": 1,
        "window_days": window_days,
        "as_of": NOW.isoformat().replace("+00:00", "Z"),
        "coverage": {
            "selected": {
                "state": coverage_state,
                "ratio": "0.500000" if coverage_state == "limited" else "1.000000",
                "earliest_at": "2025-10-01T00:00:00+00:00",
            },
            "prior": {
                "state": "limited",
                "ratio": "0.000000",
                "earliest_at": "2025-10-01T00:00:00+00:00",
            },
        },
        "unresolved_backlog_intervals": [],
        "comparison_suppressed_reasons": [],
        "comparison_allowed": False,
        "thresholds": {"minimum_coverage": "0.800000"},
        "series_axis": {"coarse": {"bucket_count": 1}},
        "candidates": [
            {
                "candidate_id": "minimax:full_window",
                "brand_key": brand.pk,
                "display_name_en": "MiniMax",
                "display_name_zh_cn": "MiniMax",
                "kind": "full_window",
                "start_at": "2026-08-12T11:00:00Z",
                "end_at": "2026-08-12T12:00:00Z",
                "signals": [{"family": "volume", "rank": 1}],
                "family_facts": {"volume": {"change_pct": None}},
                "metadata_trajectories": {},
                "episodes": [],
                "series": {"coarse": {"post_counts": [1]}},
                "evidence_allocation": {},
                "evidence_support": {},
                "evidence": [],
            }
        ],
        "legacy_primary_brand": {
            "key": brand.pk,
            "display_name_en": "MiniMax",
            "display_name_zh_cn": "MiniMax",
        },
    }
    row = reserve_generation(
        source_cycle_id="cycle-a",
        window_days=window_days,
        facts_as_of=NOW,
        semantic_fingerprint="a" * 64,
        generation_facts=facts,
        publication_epoch=1,
        prompt_version="headline-v1",
        provider="anthropic",
        provider_host="api.anthropic.com",
        llm_model_name="claude-haiku-4-5-20251001",
        owner="worker-a",
        now=NOW,
        lease_seconds=90,
        output_schema_version=output_schema_version,
    )
    assert row is not None
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    assert mark_transport_completed(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW + timedelta(milliseconds=500),
    )
    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax leads attention across the market.",
        body_zh_cn="MiniMax 当前在市场讨论中更受关注。",
        output_hash="b" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=200,
        now=NOW + timedelta(seconds=1),
        observations_en=["Attention rises and then holds."],
        observations_zh_cn=["讨论热度上升后保持稳定。"],
        selected_candidate_ids=["minimax:full_window"],
        claims=[
            {
                "observation_index": -1,
                "candidate_ids": ["minimax:full_window"],
                "families": ["volume"],
                "evidence_ids": [],
                **(
                    {
                        "quantitative_fact_ids": [],
                        "explanation_type": "aggregate_trajectory",
                        "evidence_confidence": "aggregate_only",
                    }
                    if output_schema_version == 3
                    else {}
                ),
            },
            {
                "observation_index": 0,
                "candidate_ids": ["minimax:full_window"],
                "families": ["volume"],
                "evidence_ids": [],
                **(
                    {
                        "quantitative_fact_ids": [],
                        "explanation_type": "aggregate_trajectory",
                        "evidence_confidence": "aggregate_only",
                    }
                    if output_schema_version == 3
                    else {}
                ),
            }
        ],
        subjects=[
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "canonical_key_snapshot": "minimax",
                "name_en_snapshot": "MiniMax",
                "name_zh_cn_snapshot": "MiniMax",
                "candidate_id": "minimax:full_window",
                "evidence_ids": [],
            }
        ],
    )
    row.refresh_from_db()
    return row


def _record_no_story(
    *,
    window_days: int,
    facts_as_of: datetime,
    checked_at: datetime,
    source_cycle_id: str = "no-story-cycle",
):
    return record_no_call_check(
        source_cycle_id=source_cycle_id,
        window_days=window_days,
        facts_as_of=facts_as_of,
        semantic_fingerprint="f" * 64,
        facts={
            "snapshot_schema_version": 1,
            "window_days": window_days,
            "as_of": facts_as_of.isoformat(),
            "coverage": {
                "selected": {"state": "sufficient", "ratio": "1.000000"},
                "prior": {"state": "sufficient", "ratio": "1.000000"},
            },
            "candidates": [],
        },
        checked_at=checked_at,
        status="checked",
        reason_code="insufficient_data",
    )


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "MiniMax leads attention across the market."),
        ("original", "MiniMax leads attention across the market."),
        ("zh_cn", "MiniMax 当前在市场讨论中更受关注。"),
        ("zh-CN", "MiniMax 当前在市场讨论中更受关注。"),
        ("zh_hans", "MiniMax 当前在市场讨论中更受关注。"),
    ],
)
def test_available_projection_selects_locale_and_public_brand_link(locale, expected):
    row = _publish()

    payload = project_trend_narrative(
        1,
        locale=locale,
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert payload["schema_version"] == 2
    assert payload["window_days"] == 1
    assert payload["state"] == "available"
    assert payload["state_label"] == (
        "可用" if locale in {"zh_cn", "zh-CN", "zh_hans"} else "Available"
    )
    assert payload["body"] == expected
    assert payload["body_remainder"] == expected.removeprefix("MiniMax ")
    assert payload["observations"] == (
        ["讨论热度上升后保持稳定。"]
        if locale in {"zh_cn", "zh-CN", "zh_hans"}
        else ["Attention rises and then holds."]
    )
    assert payload["subjects"] == [
        {
            "position": 0,
            "support_type": "measured_candidate",
            "entity_type": "brand",
            "identity_type": "brand",
            "key": "minimax",
            "display_name": "MiniMax",
            "url": "/brands/minimax/",
        }
    ]
    assert payload["primary_brand"] == payload["subjects"][0]
    assert payload["generated_at"] == row.generated_at.isoformat()
    assert "provider" not in payload
    assert "error" not in payload
    assert "claim" not in payload


def test_schema_three_row_keeps_the_public_browser_dto_at_schema_two():
    row = _publish(output_schema_version=3)

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert row.output_schema_version == 3
    assert payload["schema_version"] == 2
    assert payload["body"] == "MiniMax leads attention across the market."
    assert "claims" not in payload


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "No clear conversation story emerged in this window."),
        ("zh_hans", "这一时间段内没有出现明确的讨论主题。"),
    ],
)
def test_newer_no_candidate_check_supersedes_an_older_story(locale, expected):
    _publish()
    no_story = _record_no_story(
        window_days=1,
        facts_as_of=NOW + timedelta(hours=1),
        checked_at=NOW + timedelta(hours=1, seconds=1),
    )

    payload = project_trend_narrative(
        1,
        locale=locale,
        now=NOW + timedelta(hours=1, minutes=1),
        config=_config(),
    )

    assert payload["schema_version"] == 2
    assert payload["state"] == "available"
    assert payload["body"] == expected
    assert payload["body_remainder"] == expected
    assert payload["subjects"] == []
    assert payload["primary_brand"] is None
    assert payload["observations"] == []
    assert payload["generated_at"] is None
    assert payload["checked_at"] == no_story.latest_checked_at.isoformat()


def test_older_no_candidate_check_and_newer_failure_preserve_last_good():
    current = _publish()
    _record_no_story(
        window_days=1,
        facts_as_of=NOW - timedelta(hours=1),
        checked_at=NOW + timedelta(seconds=2),
    )
    record_no_call_check(
        source_cycle_id="newer-provider-failure",
        window_days=1,
        facts_as_of=NOW + timedelta(hours=2),
        semantic_fingerprint="9" * 64,
        facts=current.generation_facts,
        checked_at=NOW + timedelta(hours=2, seconds=1),
        status="suppressed",
        reason_code="provider_request_failed",
    )

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert payload["body"] == current.body_en
    assert payload["primary_brand"]["key"] == "minimax"


def test_no_story_checked_time_breaks_an_equal_facts_as_of_tie():
    _publish()
    _record_no_story(
        window_days=1,
        facts_as_of=NOW,
        checked_at=NOW + timedelta(seconds=2),
    )

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(seconds=3),
        config=_config(),
    )

    assert payload["body"] == (
        "No clear conversation story emerged in this window."
    )


def test_stale_uses_last_good_body_and_deleted_brand_loses_only_link():
    row = _publish()
    Brand.objects.get(pk="minimax").delete()

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(hours=2),
        config=_config(),
    )

    assert payload["state"] == "stale"
    assert payload["state_label"] == "Stale"
    assert payload["body"] == row.body_en
    assert payload["primary_brand"]["display_name"] == "MiniMax"
    assert payload["primary_brand"]["url"] is None


def test_analytical_limited_coverage_adds_dated_qualifier():
    row = _publish(365, coverage_state="limited")

    payload = project_trend_narrative(
        365,
        locale="en",
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert row.coverage_state == "limited"
    assert payload["coverage_state"] == "limited"
    assert payload["body"].endswith(
        "Based on available data since 2025-10-01."
    )


def test_schema_one_projection_uses_both_legacy_subject_snapshots():
    primary = Brand.objects.create(
        nickname="minimax",
        display_name="MiniMax",
        display_name_en="MiniMax",
        display_name_zh_cn="MiniMax",
    )
    secondary = Brand.objects.create(
        nickname="deepseek",
        display_name="DeepSeek",
        display_name_en="DeepSeek",
        display_name_zh_cn="DeepSeek",
    )
    facts = {
        "schema_version": 1,
        "window_days": 1,
        "as_of": NOW.isoformat(),
        "coverage": {"state": "sufficient", "ratio": "1.000000"},
        "primary_brand": {
            "key": primary.pk,
            "display_name_en": "MiniMax",
            "display_name_zh_hans": "MiniMax",
        },
        "secondary_brand": {
            "key": secondary.pk,
            "display_name_en": "DeepSeek",
            "display_name_zh_hans": "DeepSeek",
        },
    }
    row = reserve_generation(
        source_cycle_id="legacy-two-subjects",
        window_days=1,
        facts_as_of=NOW,
        semantic_fingerprint="c" * 64,
        generation_facts=facts,
        publication_epoch=1,
        prompt_version="headline-v1",
        provider="anthropic",
        provider_host="api.anthropic.com",
        llm_model_name="claude-haiku-4-5-20251001",
        owner="worker-a",
        now=NOW,
        lease_seconds=90,
        output_schema_version=1,
    )
    assert row is not None
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    assert mark_transport_completed(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW + timedelta(milliseconds=500),
    )
    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax and DeepSeek share attention.",
        body_zh_cn="MiniMax 与 DeepSeek 共同受到关注。",
        output_hash="d" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=200,
        now=NOW + timedelta(seconds=1),
    )

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert [subject["key"] for subject in payload["subjects"]] == [
        "minimax",
        "deepseek",
    ]


def test_projection_exposes_two_safe_subjects_without_claim_or_evidence_data():
    row = _publish()
    TrendNarrativeSubject.objects.create(
        trend_narrative=row,
        position=1,
        support_type="evidence_only",
        entity_type="model",
        identity_type="unresolved",
        observed_name="OffListModel",
        name_en_snapshot="OffListModel",
        name_zh_cn_snapshot="OffListModel",
        evidence_ids=["private_evidence_id"],
    )

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert payload["subjects"][1] == {
        "position": 1,
        "support_type": "evidence_only",
        "entity_type": "model",
        "identity_type": "unresolved",
        "key": "OffListModel",
        "display_name": "OffListModel",
        "url": None,
    }
    assert "private_evidence_id" not in json.dumps(payload["subjects"])
    assert "claims" not in payload


@pytest.mark.parametrize(
    ("locale", "phrase"),
    [
        ("en", "Trend summary is warming up"),
        ("original", "Trend summary is warming up"),
        ("zh_cn", "趋势摘要正在准备中"),
    ],
)
def test_cold_fallback_is_localized_and_readable(locale, phrase):
    payload = project_trend_narrative(
        30,
        locale=locale,
        now=NOW,
        config=_config(),
    )

    assert payload["state"] == "unavailable"
    assert payload["state_label"] == ("准备中" if locale == "zh_cn" else "Warming up")
    assert phrase in payload["body"]
    assert payload["observations"] == []
    assert payload["primary_brand"] is None


def test_serving_control_off_returns_disabled_copy_even_with_current_row():
    _publish()

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW,
        config=_config(enabled=False),
    )

    assert payload["state"] == "disabled"
    assert payload["state_label"] == "Disabled"
    assert payload["observations"] == []
    assert payload["primary_brand"] is None
    assert "unavailable" in payload["body"].lower()


def test_chart_payload_has_one_identity_for_chart_pulse_narrative_and_voices(
    monkeypatch,
):
    _publish()
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config",
        lambda: _config(),
    )

    payload = _build_home_chart_payload(1, {}, now=NOW, locale="en")

    assert payload["window_days"] == payload["pulse"]["window_days"]
    assert payload["window_days"] == payload["trend_narrative"]["window_days"]
    assert payload["window_days"] == payload["top_voices"]["window_days"]
    assert payload["computed_at"] == payload["pulse"]["computed_at"]
    assert payload["computed_at"] == payload["trend_narrative"]["computed_at"]
    assert payload["computed_at"] == payload["top_voices"]["computed_at"]


def test_ten_window_requests_are_database_only_and_ignore_filters(
    client,
    monkeypatch,
):
    _publish()
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config",
        lambda: _config(),
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.generate_trend_narrative",
        lambda *_args, **_kwargs: pytest.fail("web request reached provider"),
    )
    monkeypatch.setattr(
        "monitor.tasks.refresh_trend_narratives.apply_async",
        lambda *_args, **_kwargs: pytest.fail("web request enqueued worker"),
    )
    bodies = []
    for index in range(10):
        window = [1, 7, 30, 365][index % 4]
        response = client.get(
            "/chart.html",
            {
                "window": window,
                "filters": json.dumps(
                    {"window": window, "brands": [f"filter-{index}"]}
                ),
                "locale": "en",
            },
        )
        assert response.status_code == 200
        raw = response.content.decode("utf-8")
        marker = "data-home='"
        encoded = raw.split(marker, 1)[1].split("'", 1)[0]
        payload = json.loads(unescape(encoded))
        bodies.append(payload["trend_narrative"]["body"])
    assert bodies[0] == bodies[4] == bodies[8]
