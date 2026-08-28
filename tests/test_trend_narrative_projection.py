"""PostgreSQL contracts for the provider-free public headline projection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html import unescape

import pytest

from core.models import (
    Brand,
    BrandTrendNarrative,
    TrendNarrativeRun,
    TrendNarrativeSubject,
    TrendNarrativeVisibleRun,
)
from monitor.trend_narrative_lifecycle import (
    activate_trend_narrative_run,
    mark_transport_completed,
    mark_transport_started,
    prepare_brand_trend_narrative,
    publish_generation,
    record_no_call_check,
    reserve_generation,
)
from monitor.trend_narrative_projection import project_trend_narrative
from monitor.views import _build_home_chart_payload
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _config(
    *,
    enabled: bool = True,
    publication_source: str = "prefer_per_brand",
    legacy_fallback_enabled: bool = True,
) -> HeadlineNarrativeConfig:
    return HeadlineNarrativeConfig(
        serving_enabled=enabled,
        activation_state="owner_override",
        publication_source=publication_source,
        legacy_fallback_enabled=legacy_fallback_enabled,
    )


def _brand(key: str, name: str | None = None) -> Brand:
    display = name or key.replace("-", " ").title()
    return Brand.objects.create(
        nickname=key,
        display_name=display,
        display_name_en=display,
        display_name_zh_cn=display,
    )


def _per_brand_run(
    brands: list[Brand],
    *,
    cycle: str = "u5-run",
    facts_as_of: datetime = NOW,
    internal_order: list[str] | None = None,
) -> TrendNarrativeRun:
    keys = [brand.nickname for brand in brands]
    return TrendNarrativeRun.objects.create(
        source_cycle_id=cycle,
        window_days=1,
        facts_as_of=facts_as_of,
        packet_schema_version=3,
        snapshot={"private": True},
        brand_manifest=keys,
        batch_manifest=[keys],
        internal_order=internal_order or keys,
    )


def _per_brand_outcome(
    run: TrendNarrativeRun,
    brand: Brand,
    *,
    status: str = BrandTrendNarrative.Status.APPROVED,
    attempted_at: datetime = NOW,
    verified_at: datetime | None = NOW,
    headline_en: str | None = None,
    headline_zh_cn: str | None = None,
    secondary_en: str | None = None,
    secondary_zh_cn: str | None = None,
    error_code: str = "",
) -> BrandTrendNarrative:
    publishable = status == BrandTrendNarrative.Status.APPROVED
    return prepare_brand_trend_narrative(
        run=run,
        brand_key=brand.nickname,
        brand_name_en=brand.display_name_en,
        brand_name_zh_cn=brand.display_name_zh_cn,
        status=status,
        attempted_at=attempted_at,
        verified_at=verified_at if publishable else None,
        headline_en=(headline_en or f"{brand.display_name_en} changed this week.")
        if publishable
        else "",
        headline_zh_cn=(headline_zh_cn or f"{brand.display_name_zh_cn}本周出现变化。")
        if publishable
        else "",
        secondary_en=(secondary_en or "Posts discussed the change in detail.")
        if publishable
        else "",
        secondary_zh_cn=(secondary_zh_cn or "帖子详细讨论了这一变化。")
        if publishable
        else "",
        critic_decision=(
            BrandTrendNarrative.CriticDecision.APPROVE if publishable else ""
        ),
        narrative_kind=(
            BrandTrendNarrative.NarrativeKind.CONTENT_SHIFT if publishable else ""
        ),
        confidence=(BrandTrendNarrative.Confidence.HIGH if publishable else ""),
        error_code=error_code,
    )


def _publish(
    window_days: int = 1,
    *,
    coverage_state: str = "sufficient",
    output_schema_version: int = 2,
    body_en: str = "MiniMax leads attention across the market.",
    body_zh_cn: str = "MiniMax 当前在市场讨论中更受关注。",
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
        body_en=body_en,
        body_zh_cn=body_zh_cn,
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
    assert payload["body_prefix"] == ""
    assert payload["body_remainder"] == expected[len("MiniMax") :]
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


def test_projection_preserves_primary_brand_position_inside_quiet_context():
    body = (
        "In a mostly unremarkable week, MiniMax led with a small 0.1% rise "
        "in post volume."
    )
    _publish(body_en=body)

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert payload["body"] == body
    assert payload["body_prefix"] == "In a mostly unremarkable week, "
    assert payload["body_remainder"] == " led with a small 0.1% rise in post volume."


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


def test_pending_activation_blocks_raw_enabled_serving_with_current_row():
    _publish()
    config = HeadlineNarrativeConfig(
        serving_enabled=True,
        activation_state="pending",
    )

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW,
        config=config,
    )

    assert config.serving_enabled
    assert not config.serving_active
    assert payload["state"] == "disabled"
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


def test_ten_window_requests_are_database_only_and_apply_only_brand_selection(
    client,
    monkeypatch,
):
    _publish()
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config",
        lambda: _config(),
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.execute_per_brand_provider_request",
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
    assert len(set(bodies)) == 10
    assert all("trend summary is unavailable" in body for body in bodies)


def test_u5_per_brand_selection_modes_follow_visible_run_order():
    deepseek = _brand("deepseek", "DeepSeek")
    minimax = _brand("minimax", "MiniMax")
    glm = _brand("glm", "GLM")
    qwen = _brand("qwen", "Qwen")
    brands = [deepseek, minimax, glm, qwen]
    run = _per_brand_run(brands, internal_order=["deepseek", "minimax", "glm", "qwen"])
    for brand in brands:
        _per_brand_outcome(run, brand)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))

    only_glm = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["glm"],
        now=NOW + timedelta(minutes=10),
        config=_config(),
    )
    two = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["glm", "deepseek"],
        now=NOW + timedelta(minutes=10),
        config=_config(),
    )
    four = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["qwen", "glm", "minimax", "deepseek"],
        now=NOW + timedelta(minutes=10),
        config=_config(),
    )
    all_brands = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=10),
        config=_config(),
    )

    assert only_glm["schema_version"] == 3
    assert [item["brand"]["key"] for item in only_glm["items"]] == ["glm"]
    assert [item["brand"]["key"] for item in two["items"]] == [
        "deepseek",
        "glm",
    ]
    assert [item["brand"]["key"] for item in four["items"]] == [
        "deepseek",
        "minimax",
    ]
    assert four["selection"] == {
        "mode": "explicit",
        "requested_count": 4,
        "returned_count": 2,
        "truncated": True,
        "summary": "2 of 4 selected",
    }
    assert [item["brand"]["key"] for item in all_brands["items"]] == [
        "deepseek",
        "minimax",
    ]
    assert all_brands["selection"]["mode"] == "all"
    assert "rank" not in json.dumps(all_brands).casefold()


def test_u5_held_brand_serves_last_good_with_attempt_and_verification_freshness():
    minimax = _brand("minimax", "MiniMax")
    first = _per_brand_run([minimax], cycle="u5-last-good-first")
    last_good = _per_brand_outcome(
        first,
        minimax,
        verified_at=NOW,
        headline_en="MiniMax discussion shifted toward hands-on use.",
    )
    assert activate_trend_narrative_run(first.pk, now=NOW + timedelta(seconds=1))
    second = _per_brand_run(
        [minimax],
        cycle="u5-last-good-second",
        facts_as_of=NOW + timedelta(minutes=10),
    )
    held = _per_brand_outcome(
        second,
        minimax,
        status=BrandTrendNarrative.Status.HELD,
        attempted_at=NOW + timedelta(minutes=10),
        verified_at=None,
        error_code="critic_hold",
    )
    assert held.last_good_id == last_good.pk
    assert activate_trend_narrative_run(second.pk, now=NOW + timedelta(minutes=11))

    item = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["minimax"],
        now=NOW + timedelta(minutes=20),
        config=_config(),
    )["items"][0]

    assert item["id"] == f"brand-trend:{last_good.pk}"
    assert item["state"] == "stale"
    assert item["headline"] == "MiniMax discussion shifted toward hands-on use."
    assert item["verified_at"] == NOW.isoformat()
    assert item["attempted_at"] == (NOW + timedelta(minutes=10)).isoformat()
    assert item["freshness"]["relative"] == "last verified 20 min ago"
    assert item["state_label"] == "Stale · last verified 20 min ago"


def test_u5_terminal_empty_states_are_honest_and_rank_after_narratives():
    usable = _brand("usable", "Usable")
    empty = _brand("empty", "Empty")
    partial = _brand("partial", "Partial")
    failed = _brand("failed", "Failed")
    brands = [empty, partial, failed, usable]
    run = _per_brand_run(
        brands,
        internal_order=["empty", "partial", "failed", "usable"],
    )
    _per_brand_outcome(
        run,
        empty,
        status=BrandTrendNarrative.Status.NO_CONTENT,
        verified_at=None,
    )
    _per_brand_outcome(
        run,
        partial,
        status=BrandTrendNarrative.Status.DATA_QUALITY_UNAVAILABLE,
        verified_at=None,
        error_code="enrichment_pending",
    )
    _per_brand_outcome(
        run,
        failed,
        status=BrandTrendNarrative.Status.UNAVAILABLE,
        verified_at=None,
        error_code="critic_hold",
    )
    _per_brand_outcome(run, usable)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))

    default = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=5),
        config=_config(),
    )
    explicit_empty = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["empty"],
        now=NOW + timedelta(minutes=5),
        config=_config(),
    )["items"][0]
    explicit_partial = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["partial"],
        now=NOW + timedelta(minutes=5),
        config=_config(),
    )["items"][0]
    explicit_failed = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["failed"],
        now=NOW + timedelta(minutes=5),
        config=_config(),
    )["items"][0]

    assert default["items"][0]["brand"]["key"] == "usable"
    assert explicit_empty["state"] == "no_content"
    assert "no posts" in explicit_empty["headline"].casefold()
    assert explicit_partial["state"] == "data_quality_unavailable"
    assert "incomplete" in explicit_partial["secondary"].casefold()
    assert explicit_failed["state"] == "unavailable"
    assert explicit_failed["freshness"]["relative"] == "last attempt 5 min ago"


def test_u5_localized_absolute_and_relative_freshness_share_one_timestamp():
    brand = _brand("mimo", "MiMo")
    run = _per_brand_run([brand])
    _per_brand_outcome(run, brand)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))

    en = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(hours=2),
        config=_config(),
    )["items"][0]
    zh = project_trend_narrative(
        1,
        locale="zh_cn",
        now=NOW + timedelta(hours=2),
        config=_config(),
    )["items"][0]

    assert en["verified_at"] == zh["verified_at"] == NOW.isoformat()
    assert en["freshness"]["relative"] == "last verified 2 hr ago"
    assert zh["freshness"]["relative"] == "上次验证于2小时前"
    assert "Aug 12, 2026" in en["freshness"]["absolute"]
    assert "2026年8月12日" in zh["freshness"]["absolute"]


def test_u5_deleted_brand_keeps_snapshots_and_loses_only_url():
    brand = _brand("deleted", "Deleted Brand")
    run = _per_brand_run([brand])
    _per_brand_outcome(run, brand)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))
    brand.delete()

    item = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=5),
        config=_config(),
    )["items"][0]

    assert item["brand"] == {
        "key": "deleted",
        "display_name": "Deleted Brand",
        "url": None,
    }


def test_u5_per_brand_wins_but_legacy_only_is_an_explicit_rollback_source():
    legacy = _publish(body_en="Legacy shared headline.")
    minimax = Brand.objects.get(pk="minimax")
    run = _per_brand_run(
        [minimax], cycle="u5-new-source", facts_as_of=NOW + timedelta(minutes=5)
    )
    new = _per_brand_outcome(
        run,
        minimax,
        attempted_at=NOW + timedelta(minutes=5),
        verified_at=NOW + timedelta(minutes=5),
        headline_en="New per-brand headline.",
    )
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(minutes=6))

    preferred = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["minimax"],
        now=NOW + timedelta(minutes=10),
        config=_config(),
    )
    rollback = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["minimax"],
        now=NOW + timedelta(minutes=10),
        config=_config(publication_source="legacy_only"),
    )

    assert preferred["schema_version"] == 3
    assert preferred["items"][0]["id"] == f"brand-trend:{new.pk}"
    assert preferred["items"][0]["headline"] == "New per-brand headline."
    assert rollback["schema_version"] == 2
    assert rollback["body"] == legacy.body_en
    assert "items" not in rollback


def test_u5_legacy_only_requires_new_work_to_be_disabled():
    with pytest.raises(ValueError, match="legacy-only headline rollback"):
        HeadlineNarrativeConfig(
            activation_state="owner_override",
            serving_enabled=True,
            enqueue_enabled=True,
            provider_calls_enabled=False,
            publication_source="legacy_only",
        )


def test_u5_legacy_fallback_never_serves_an_unrelated_selected_brand():
    _publish(body_en="MiniMax legacy shared headline.")
    _brand("deepseek", "DeepSeek")

    payload = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["deepseek"],
        now=NOW + timedelta(minutes=5),
        config=_config(),
    )

    assert payload["schema_version"] == 3
    assert payload["items"][0]["brand"]["key"] == "deepseek"
    assert payload["items"][0]["state"] == "unavailable"
    assert "MiniMax legacy" not in json.dumps(payload)


def test_u5_disabling_legacy_fallback_makes_absence_explicit():
    _publish(body_en="Legacy shared headline.")

    payload = project_trend_narrative(
        1,
        locale="en",
        selected_brand_keys=["minimax"],
        now=NOW + timedelta(minutes=5),
        config=_config(legacy_fallback_enabled=False),
    )

    assert payload["schema_version"] == 3
    assert payload["items"][0]["state"] == "unavailable"
    assert "Legacy shared" not in json.dumps(payload)


def test_u5_projection_reads_only_the_one_visible_run():
    first_brand = _brand("first", "First")
    first = _per_brand_run([first_brand], cycle="u5-visible-first")
    _per_brand_outcome(first, first_brand, headline_en="Visible first cutoff.")
    assert activate_trend_narrative_run(first.pk, now=NOW + timedelta(seconds=1))

    second_brand = _brand("second", "Second")
    second = _per_brand_run(
        [second_brand],
        cycle="u5-not-visible-second",
        facts_as_of=NOW + timedelta(minutes=10),
    )
    _per_brand_outcome(second, second_brand, headline_en="Prepared newer cutoff.")

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(minutes=15),
        config=_config(),
    )

    assert TrendNarrativeVisibleRun.objects.get(window_days=1).run_id == first.pk
    assert [item["brand"]["key"] for item in payload["items"]] == ["first"]
    assert "Prepared newer cutoff" not in json.dumps(payload)


def test_u5_query_count_is_bounded_for_twenty_brands(django_assert_num_queries):
    brands = [_brand(f"brand-{index:02d}") for index in range(20)]
    run = _per_brand_run(brands)
    for brand in brands:
        _per_brand_outcome(run, brand)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))

    with django_assert_num_queries(2):
        payload = project_trend_narrative(
            1,
            locale="en",
            now=NOW + timedelta(minutes=5),
            config=_config(),
        )

    assert len(payload["items"]) == 2


def test_u5_chart_view_threads_only_normalized_brand_selection(monkeypatch):
    deepseek = _brand("deepseek", "DeepSeek")
    minimax = _brand("minimax", "MiniMax")
    run = _per_brand_run(
        [deepseek, minimax], internal_order=["deepseek", "minimax"]
    )
    _per_brand_outcome(run, deepseek)
    _per_brand_outcome(run, minimax)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config", lambda: _config()
    )

    first = _build_home_chart_payload(
        1,
        {"brands": ["minimax"], "sentiment": ["positive"]},
        now=NOW,
        locale="en",
    )["trend_narrative"]
    changed_non_brand = _build_home_chart_payload(
        1,
        {"brands": ["minimax"], "sentiment": ["negative"], "role": ["staff"]},
        now=NOW,
        locale="en",
    )["trend_narrative"]
    changed_brand = _build_home_chart_payload(
        1,
        {"brands": ["deepseek"], "sentiment": ["negative"]},
        now=NOW,
        locale="en",
    )["trend_narrative"]

    assert [item["id"] for item in first["items"]] == [
        item["id"] for item in changed_non_brand["items"]
    ]
    assert first["items"][0]["brand"]["key"] == "minimax"
    assert changed_brand["items"][0]["brand"]["key"] == "deepseek"


def test_u5_chart_endpoint_threads_brand_filter_to_dto_v3(client, monkeypatch):
    deepseek = _brand("deepseek", "DeepSeek")
    minimax = _brand("minimax", "MiniMax")
    run = _per_brand_run(
        [deepseek, minimax], internal_order=["deepseek", "minimax"]
    )
    _per_brand_outcome(run, deepseek)
    minimax_row = _per_brand_outcome(run, minimax)
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config", lambda: _config()
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.execute_per_brand_provider_request",
        lambda *_args, **_kwargs: pytest.fail("view request reached provider"),
    )

    response = client.get(
        "/chart/",
        {
            "window": 1,
            "filters": json.dumps(
                {
                    "brands": ["minimax"],
                    "sentiment": ["negative"],
                }
            ),
            "locale": "en",
        },
    )

    assert response.status_code == 200
    narrative = response.json()["trend_narrative"]
    assert narrative["schema_version"] == 3
    assert [item["id"] for item in narrative["items"]] == [
        f"brand-trend:{minimax_row.pk}"
    ]
    assert narrative["items"][0]["brand"]["key"] == "minimax"
