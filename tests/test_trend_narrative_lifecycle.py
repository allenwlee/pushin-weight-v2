"""PostgreSQL contracts for the trend-narrative publication ledger."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from core.models import (
    Brand,
    BrandTrendNarrative,
    Product,
    TrendNarrative,
    TrendNarrativeProviderCall,
    TrendNarrativeRun,
    TrendNarrativeSubject,
    TrendNarrativeVisibleRun,
)
from monitor.trend_narrative_candidates import project_provider_packet
from monitor.trend_narrative_lifecycle import (
    abandon_expired_attempts,
    activate_trend_narrative_run,
    advance_current_check,
    claim_trend_narrative_provider_call,
    complete_trend_narrative_provider_call,
    fail_generation,
    mark_transport_completed,
    mark_transport_started,
    mark_trend_narrative_provider_call_ambiguous,
    mark_trend_narrative_provider_call_sent,
    prepare_brand_trend_narrative,
    prune_narrative_history,
    prune_per_brand_trend_narrative_history,
    publish_generation,
    reserve_generation,
    reserve_trend_narrative_provider_call,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _brand(key: str = "minimax") -> Brand:
    return Brand.objects.create(
        nickname=key,
        display_name=key.title(),
        display_name_en=key.title(),
        display_name_zh_cn=f"中{key}",
    )


def _facts(
    brand: Brand | None = None,
    *,
    as_of: datetime = NOW,
    narrative_type: str = "leader",
) -> dict:
    primary = None
    if brand is not None:
        primary = {
            "key": brand.pk,
            "display_name_en": brand.display_name_en,
            "display_name_zh_hans": brand.display_name_zh_cn,
            "recent_posts": 25,
            "recent_authors": 12,
            "earlier_posts": 20,
            "earlier_authors": 10,
        }
    return {
        "schema_version": 1,
        "window_days": 1,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "coverage": {"state": "sufficient", "ratio": "1.000000"},
        "narrative_type": narrative_type,
        "primary_brand": primary,
        "secondary_brand": None,
        "earlier_leader": None,
        "momentum": "rising" if primary else None,
    }


def _reserve(
    *,
    source_cycle_id: str = "cycle-a",
    window_days: int = 1,
    fingerprint: str = "a" * 64,
    facts_as_of: datetime = NOW,
    epoch: int = 1,
    owner: str = "worker-a",
    lease_seconds: int = 1_200,
    output_schema_version: int = 1,
    generation_facts: dict | None = None,
    prompt_version: str = "headline-v1",
    provider: str = "anthropic",
    provider_host: str = "api.anthropic.com",
    llm_model_name: str = "claude-haiku-4-5-20251001",
) -> TrendNarrative:
    brand = Brand.objects.filter(pk="minimax").first() or _brand()
    row = reserve_generation(
        source_cycle_id=source_cycle_id,
        window_days=window_days,
        facts_as_of=facts_as_of,
        semantic_fingerprint=fingerprint,
        generation_facts=(generation_facts or _facts(brand, as_of=facts_as_of)),
        publication_epoch=epoch,
        prompt_version=prompt_version,
        provider=provider,
        provider_host=provider_host,
        llm_model_name=llm_model_name,
        owner=owner,
        now=NOW,
        lease_seconds=lease_seconds,
        output_schema_version=output_schema_version,
    )
    assert row is not None
    return row


def _complete_transport(
    row: TrendNarrative,
    *,
    owner: str = "worker-a",
    now: datetime = NOW + timedelta(milliseconds=500),
) -> None:
    assert mark_transport_completed(
        row.pk,
        owner=owner,
        fence=row.claim_fence,
        now=now,
    )


def _schema_three_snapshot(brand: Brand) -> dict:
    return {
        "snapshot_schema_version": 1,
        "window_days": 1,
        "as_of": NOW.isoformat(),
        "coverage": {
            "selected": {"state": "sufficient", "ratio": "1.000000"},
            "prior": {"state": "sufficient", "ratio": "1.000000"},
        },
        "unresolved_backlog_intervals": [],
        "comparison_suppressed_reasons": [],
        "comparison_allowed": True,
        "thresholds": {"minimum_coverage": "0.800000"},
        "series_axis": {"coarse": {"bucket_count": 1}},
        "candidates": [
            {
                "candidate_id": "minimax:full_window",
                "brand_key": brand.pk,
                "display_name_en": brand.display_name_en,
                "display_name_zh_cn": brand.display_name_zh_cn,
                "kind": "full_window",
                "start_at": "2026-08-12T11:00:00Z",
                "end_at": "2026-08-12T12:00:00Z",
                "signals": [{"family": "volume", "rank": 1}],
                "family_facts": {
                    "volume": {
                        "selected_count": 30,
                        "prior_count": 20,
                        "change_pct": "50.000000",
                    }
                },
                "metadata_trajectories": {},
                "episodes": [],
                "series": {"coarse": {"post_counts": [30]}},
                "evidence_allocation": {},
                "evidence_support": {
                    "official_source_count": 0,
                    "distinct_author_group_count": 0,
                    "distinct_source_cluster_count": 0,
                    "event_claim_may_be_supported": False,
                    "evidence_only_entity_may_be_supported": False,
                },
                "evidence": [],
            }
        ],
    }


def _publish(
    row: TrendNarrative,
    *,
    owner: str = "worker-a",
    body_suffix: str = "",
    now: datetime | None = None,
) -> bool:
    started = mark_transport_started(
        row.pk,
        owner=owner,
        fence=row.claim_fence,
        now=NOW,
    )
    assert started
    _complete_transport(row, owner=owner)
    return publish_generation(
        row.pk,
        owner=owner,
        fence=row.claim_fence,
        body_en=f"MiniMax leads attention{body_suffix}.",
        body_zh_cn=f"MiniMax 引领关注{body_suffix}。",
        output_hash=("b" if not body_suffix else "c") * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=250,
        now=now or (NOW + timedelta(seconds=1)),
    )


def test_reservation_consumes_one_irreversible_slot_per_source_and_window():
    first = _reserve()
    duplicate = reserve_generation(
        source_cycle_id="cycle-a",
        window_days=1,
        facts_as_of=NOW,
        semantic_fingerprint="a" * 64,
        generation_facts=first.generation_facts,
        publication_epoch=1,
        prompt_version="headline-v1",
        provider="anthropic",
        provider_host="api.anthropic.com",
        llm_model_name="claude-haiku-4-5-20251001",
        owner="worker-b",
        now=NOW,
        lease_seconds=60,
    )

    assert duplicate is None
    assert TrendNarrative.objects.count() == 1
    first.refresh_from_db()
    assert first.status == TrendNarrative.Status.GENERATING
    assert first.call_slot_consumed is True
    assert first.claim_fence == 1


def test_failed_same_fingerprint_later_cycle_gets_one_new_slot():
    first = _reserve()
    assert fail_generation(
        first.pk,
        owner="worker-a",
        fence=first.claim_fence,
        error_code="provider_timeout",
        now=NOW + timedelta(seconds=10),
        next_attempt_at=NOW + timedelta(minutes=15),
    )

    second = _reserve(source_cycle_id="cycle-b", owner="worker-b")

    assert second.pk != first.pk
    assert (
        TrendNarrative.objects.filter(
            semantic_fingerprint="a" * 64,
            call_slot_consumed=True,
        ).count()
        == 2
    )


def test_publication_requires_a_completed_transport_marker():
    row = _reserve()
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )

    assert not publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax leads attention.",
        body_zh_cn="MiniMax 引领关注。",
        output_hash="f" * 64,
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        now=NOW + timedelta(seconds=1),
    )

    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.GENERATING
    assert row.transport_completed_at is None


def test_expired_lease_is_abandoned_and_never_reopened_for_same_cycle():
    row = _reserve(lease_seconds=60)

    assert (
        abandon_expired_attempts(
            now=NOW + timedelta(minutes=2),
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )
    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.ABANDONED
    assert row.call_slot_consumed is True
    assert row.consecutive_failures == 1
    assert row.next_attempt_at == NOW + timedelta(minutes=32)
    assert not mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW + timedelta(minutes=2),
    )
    assert not _publish_late(row)
    assert TrendNarrative.objects.count() == 1


def test_repeated_expired_leases_escalate_same_fingerprint_backoff():
    first = _reserve(lease_seconds=60)
    first_expired_at = NOW + timedelta(minutes=2)
    assert (
        abandon_expired_attempts(
            now=first_expired_at,
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )

    second = _reserve(
        source_cycle_id="cycle-b",
        owner="worker-b",
        lease_seconds=60,
    )
    second_expired_at = NOW + timedelta(minutes=3)
    assert (
        abandon_expired_attempts(
            now=second_expired_at,
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.consecutive_failures == 1
    assert second.consecutive_failures == 2
    assert second.next_attempt_at == second_expired_at + timedelta(minutes=60)


def test_repeated_transport_incomplete_leases_escalate_across_fingerprints():
    first = _reserve(lease_seconds=60, fingerprint="a" * 64)
    first_expired_at = NOW + timedelta(minutes=2)
    assert (
        abandon_expired_attempts(
            now=first_expired_at,
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )

    second = _reserve(
        source_cycle_id="cycle-b",
        fingerprint="b" * 64,
        owner="worker-b",
        lease_seconds=60,
    )
    second_expired_at = NOW + timedelta(minutes=3)
    assert (
        abandon_expired_attempts(
            now=second_expired_at,
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.semantic_fingerprint != second.semantic_fingerprint
    assert first.transport_completed_at is None
    assert second.transport_completed_at is None
    assert first.consecutive_failures == 1
    assert second.consecutive_failures == 2
    assert second.next_attempt_at == second_expired_at + timedelta(minutes=60)


def test_transport_backoff_does_not_cross_provider_configuration_identity():
    first = _reserve(lease_seconds=60)
    assert (
        abandon_expired_attempts(
            now=NOW + timedelta(minutes=2),
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )

    second = _reserve(
        source_cycle_id="cycle-b",
        owner="worker-b",
        lease_seconds=60,
        prompt_version="headline-v2",
        provider="deepseek",
        provider_host="api.deepseek.com",
        llm_model_name="deepseek-v4-pro",
    )
    second_expired_at = NOW + timedelta(minutes=3)
    assert (
        abandon_expired_attempts(
            now=second_expired_at,
            cadence_minutes={1: 30},
            stale_minutes={1: 60},
        )
        == 1
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.consecutive_failures == 1
    assert second.consecutive_failures == 1
    assert second.next_attempt_at == second_expired_at + timedelta(minutes=30)


def test_expired_worker_cannot_publish_before_cleanup_marks_abandoned():
    row = _reserve(lease_seconds=60)
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )

    assert not _publish_late(row)
    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.GENERATING
    assert row.is_current is False


def _publish_late(row: TrendNarrative) -> bool:
    return publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="Late English body.",
        body_zh_cn="迟到的中文内容。",
        output_hash="d" * 64,
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        now=NOW + timedelta(minutes=3),
    )


def test_publish_is_idempotent_and_only_one_current_row_exists():
    row = _reserve()

    assert _publish(row)
    assert _publish_late(row)
    row.refresh_from_db()

    assert row.status == TrendNarrative.Status.PUBLISHED
    assert row.is_current is True
    assert row.body_en == "MiniMax leads attention."
    assert row.body_zh_cn == "MiniMax 引领关注。"
    assert row.body_zh_hans == row.body_zh_cn
    assert row.llm_model_name == "claude-haiku-4-5-20251001"
    assert row.model_name == row.llm_model_name
    assert (
        TrendNarrative.objects.filter(
            window_days=1,
            is_current=True,
        ).count()
        == 1
    )


def test_schema_two_publication_persists_two_measured_subjects_atomically():
    second = _brand("deepseek")
    snapshot = {
        **_facts(Brand.objects.filter(pk="minimax").first() or _brand()),
        "candidates": [
            {
                "candidate_id": "minimax:full_window",
                "evidence": [{"evidence_id": "e_minimax"}],
            },
            {
                "candidate_id": "deepseek:episode:1",
                "evidence": [{"evidence_id": "e_deepseek"}],
            },
        ],
    }
    row = _reserve(
        output_schema_version=2,
        generation_facts=snapshot,
    )
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)
    subjects = [
        {
            "position": 0,
            "support_type": "measured_candidate",
            "entity_type": "brand",
            "identity_type": "brand",
            "canonical_key_snapshot": "minimax",
            "name_en_snapshot": "Minimax",
            "name_zh_cn_snapshot": "中minimax",
            "candidate_id": "minimax:full_window",
            "evidence_ids": [],
        },
        {
            "position": 1,
            "support_type": "measured_candidate",
            "entity_type": "brand",
            "identity_type": "brand",
            "canonical_key_snapshot": second.pk,
            "name_en_snapshot": "Deepseek",
            "name_zh_cn_snapshot": "中deepseek",
            "candidate_id": "deepseek:episode:1",
            "evidence_ids": [],
        },
    ]

    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax and DeepSeek are drawing exceptional attention.",
        body_zh_cn="MiniMax 与 DeepSeek 正获得异常高的关注。",
        output_hash="a" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=250,
        now=NOW + timedelta(seconds=1),
        observations_en=["Both brands accelerated across the measured window."],
        observations_zh_cn=["两个品牌在测量时段内均呈加速走势。"],
        selected_candidate_ids=[
            "minimax:full_window",
            "deepseek:episode:1",
        ],
        claims=[
            {"observation_index": -1, "family": "volume"},
            {"observation_index": 0, "family": "volume"},
        ],
        subjects=subjects,
    )

    row.refresh_from_db()
    assert row.output_schema_version == 2
    assert row.selected_candidate_ids == [
        "minimax:full_window",
        "deepseek:episode:1",
    ]
    assert row.observations_zh_cn == ["两个品牌在测量时段内均呈加速走势。"]
    assert list(
        row.subjects.values_list("position", "support_type", "canonical_key_snapshot")
    ) == [
        (0, "measured_candidate", "minimax"),
        (1, "measured_candidate", "deepseek"),
    ]
    assert row.primary_brand_id == "minimax"
    assert row.secondary_brand_id == "deepseek"


def test_schema_two_allows_one_measured_and_one_unresolved_evidence_subject():
    snapshot = {
        **_facts(Brand.objects.filter(pk="minimax").first() or _brand()),
        "candidates": [
            {
                "candidate_id": "minimax:full_window",
                "evidence": [{"evidence_id": "e_offlist_model"}],
            }
        ],
    }
    row = _reserve(
        output_schema_version=2,
        generation_facts=snapshot,
    )
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)

    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax rose as discussion connected it with OffListModel.",
        body_zh_cn="MiniMax 热度上升，讨论同时提及 OffListModel。",
        output_hash="b" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=250,
        now=NOW + timedelta(seconds=1),
        observations_en=["The evidence also names an unresolved model."],
        observations_zh_cn=["相关证据还提及一个尚未解析的模型。"],
        selected_candidate_ids=["minimax:full_window"],
        claims=[
            {"observation_index": -1, "evidence_ids": ["e_offlist_model"]},
            {"observation_index": 0, "evidence_ids": ["e_offlist_model"]},
        ],
        subjects=[
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "canonical_key_snapshot": "minimax",
                "name_en_snapshot": "Minimax",
                "name_zh_cn_snapshot": "中minimax",
                "candidate_id": "minimax:full_window",
                "evidence_ids": [],
            },
            {
                "position": 1,
                "support_type": "evidence_only",
                "entity_type": "model",
                "identity_type": "unresolved",
                "observed_name": "OffListModel",
                "canonical_key_snapshot": "",
                "name_en_snapshot": "OffListModel",
                "name_zh_cn_snapshot": "OffListModel",
                "candidate_id": "",
                "evidence_ids": ["e_offlist_model"],
            },
        ],
    )

    unresolved = row.subjects.get(position=1)
    assert unresolved.identity_type == TrendNarrativeSubject.IdentityType.UNRESOLVED
    assert unresolved.brand_id is None
    assert unresolved.product_id is None
    assert unresolved.observed_name == "OffListModel"
    assert not Brand.objects.filter(nickname="OffListModel").exists()


@pytest.mark.parametrize("identity", ["brand", "product", "ambiguous"])
def test_evidence_subject_resolves_one_exact_existing_identity(identity):
    if identity in {"brand", "ambiguous"}:
        Brand.objects.create(
            nickname="offlist",
            display_name="OffListModel",
            display_name_en="OffListModel",
            display_name_zh_cn="OffListModel",
        )
    if identity in {"product", "ambiguous"}:
        Product.objects.create(
            repo_id="vendor/OffListModel",
            display_name="OffListModel",
        )
    snapshot = {
        **_facts(Brand.objects.filter(pk="minimax").first() or _brand()),
        "candidates": [
            {
                "candidate_id": "minimax:full_window",
                "evidence": [
                    {"evidence_id": "e_one"},
                    {"evidence_id": "e_two"},
                ],
            }
        ],
    }
    row = _reserve(output_schema_version=2, generation_facts=snapshot)
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)

    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax rose as discussion mentioned OffListModel.",
        body_zh_cn="MiniMax 热度上升，讨论同时提及 OffListModel。",
        output_hash="9" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=250,
        now=NOW + timedelta(seconds=1),
        selected_candidate_ids=["minimax:full_window"],
        claims=[
            {
                "observation_index": -1,
                "candidate_ids": ["minimax:full_window"],
                "families": ["evidence"],
                "evidence_ids": ["e_one", "e_two"],
            }
        ],
        subjects=[
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "canonical_key_snapshot": "minimax",
                "name_en_snapshot": "Minimax",
                "name_zh_cn_snapshot": "中minimax",
                "candidate_id": "minimax:full_window",
                "evidence_ids": [],
            },
            {
                "position": 1,
                "support_type": "evidence_only",
                "entity_type": "model",
                "identity_type": "unresolved",
                "observed_name": "OffListModel",
                "canonical_key_snapshot": "",
                "name_en_snapshot": "OffListModel",
                "name_zh_cn_snapshot": "OffListModel",
                "candidate_id": "",
                "evidence_ids": ["e_one", "e_two"],
            },
        ],
    )

    subject = row.subjects.get(position=1)
    expected_identity = "unresolved" if identity == "ambiguous" else identity
    assert subject.identity_type == expected_identity
    assert subject.observed_name == ("OffListModel" if identity == "ambiguous" else "")
    assert (
        subject.canonical_key_snapshot
        == {
            "brand": "offlist",
            "product": "vendor/OffListModel",
            "ambiguous": "",
        }[identity]
    )
    assert bool(subject.brand_id) is (identity == "brand")
    assert bool(subject.product_id) is (identity == "product")


def test_invalid_schema_two_subjects_roll_back_the_whole_publication():
    snapshot = {
        **_facts(Brand.objects.filter(pk="minimax").first() or _brand()),
        "candidates": [{"candidate_id": "minimax:full_window", "evidence": []}],
    }
    row = _reserve(
        output_schema_version=2,
        generation_facts=snapshot,
    )
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)

    with pytest.raises(ValueError, match="selected candidates"):
        publish_generation(
            row.pk,
            owner="worker-a",
            fence=row.claim_fence,
            body_en="Unsupported publication body.",
            body_zh_cn="不受支持的发布内容。",
            output_hash="c" * 64,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            now=NOW + timedelta(seconds=1),
            observations_en=["Unsupported."],
            observations_zh_cn=["不受支持。"],
            selected_candidate_ids=["not-in-snapshot"],
            claims=[
                {
                    "observation_index": -1,
                    "candidate_ids": ["not-in-snapshot"],
                    "families": ["volume"],
                    "evidence_ids": [],
                },
                {
                    "observation_index": 0,
                    "candidate_ids": ["not-in-snapshot"],
                    "families": ["volume"],
                    "evidence_ids": [],
                },
            ],
            subjects=[
                {
                    "position": 0,
                    "support_type": "measured_candidate",
                    "entity_type": "brand",
                    "identity_type": "brand",
                    "canonical_key_snapshot": "minimax",
                    "name_en_snapshot": "Minimax",
                    "name_zh_cn_snapshot": "中minimax",
                    "candidate_id": "not-in-snapshot",
                    "evidence_ids": [],
                }
            ],
        )

    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.GENERATING
    assert row.body_en == ""
    assert not row.subjects.exists()


def test_schema_three_persists_cited_quantitative_why_metadata():
    brand = Brand.objects.filter(pk="minimax").first() or _brand()
    snapshot = _schema_three_snapshot(brand)
    fact = project_provider_packet(snapshot)["candidates"][0]["quantitative_facts"][0]
    row = _reserve(output_schema_version=3, generation_facts=snapshot)
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)

    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="Minimax post volume rose 50% in the measured window.",
        body_zh_cn="中minimax 在测量时段的帖子声量上升50%。",
        output_hash="d" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=250,
        now=NOW + timedelta(seconds=1),
        selected_candidate_ids=["minimax:full_window"],
        claims=[
            {
                "observation_index": -1,
                "candidate_ids": ["minimax:full_window"],
                "families": ["volume"],
                "evidence_ids": [],
                "quantitative_fact_ids": [fact["fact_id"]],
                "event_anchor": "",
                "explanation_type": "aggregate_trajectory",
                "evidence_confidence": "aggregate_only",
            }
        ],
        subjects=[
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "canonical_key_snapshot": "minimax",
                "name_en_snapshot": "Minimax",
                "name_zh_cn_snapshot": "中minimax",
                "candidate_id": "minimax:full_window",
                "evidence_ids": [],
            }
        ],
    )

    row.refresh_from_db()
    assert row.output_schema_version == 3
    assert row.claims[0]["quantitative_fact_ids"] == [fact["fact_id"]]


def test_schema_three_uncited_numeric_prose_rolls_back():
    brand = Brand.objects.filter(pk="minimax").first() or _brand()
    snapshot = _schema_three_snapshot(brand)
    row = _reserve(output_schema_version=3, generation_facts=snapshot)
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)

    with pytest.raises(ValueError, match="uncited digit"):
        publish_generation(
            row.pk,
            owner="worker-a",
            fence=row.claim_fence,
            body_en="Minimax post volume rose 50% in the measured window.",
            body_zh_cn="中minimax 在测量时段的帖子声量上升50%。",
            output_hash="e" * 64,
            input_tokens=100,
            output_tokens=40,
            latency_ms=250,
            now=NOW + timedelta(seconds=1),
            selected_candidate_ids=["minimax:full_window"],
            claims=[
                {
                    "observation_index": -1,
                    "candidate_ids": ["minimax:full_window"],
                    "families": ["volume"],
                    "evidence_ids": [],
                    "quantitative_fact_ids": [],
                    "event_anchor": "",
                    "explanation_type": "aggregate_trajectory",
                    "evidence_confidence": "aggregate_only",
                }
            ],
            subjects=[
                {
                    "position": 0,
                    "support_type": "measured_candidate",
                    "entity_type": "brand",
                    "identity_type": "brand",
                    "canonical_key_snapshot": "minimax",
                    "name_en_snapshot": "Minimax",
                    "name_zh_cn_snapshot": "中minimax",
                    "candidate_id": "minimax:full_window",
                    "evidence_ids": [],
                }
            ],
        )

    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.GENERATING
    assert row.body_en == ""


def test_schema_two_rejects_cross_candidate_evidence_at_publication_boundary():
    snapshot = {
        **_facts(Brand.objects.filter(pk="minimax").first() or _brand()),
        "candidates": [
            {"candidate_id": "minimax:full_window", "evidence": []},
            {
                "candidate_id": "deepseek:full_window",
                "evidence": [{"evidence_id": "e_deepseek"}],
            },
        ],
    }
    row = _reserve(output_schema_version=2, generation_facts=snapshot)
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    _complete_transport(row)

    with pytest.raises(ValueError, match="claim evidence"):
        publish_generation(
            row.pk,
            owner="worker-a",
            fence=row.claim_fence,
            body_en="MiniMax rose while evidence described another candidate.",
            body_zh_cn="MiniMax 热度上升，但证据描述的是另一个候选对象。",
            output_hash="e" * 64,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            now=NOW + timedelta(seconds=1),
            observations_en=["Unrelated evidence was attached."],
            observations_zh_cn=["附加了无关证据。"],
            selected_candidate_ids=["minimax:full_window"],
            claims=[
                {
                    "observation_index": -1,
                    "candidate_ids": ["minimax:full_window"],
                    "families": ["evidence"],
                    "evidence_ids": ["e_deepseek"],
                },
                {
                    "observation_index": 0,
                    "candidate_ids": ["minimax:full_window"],
                    "families": ["evidence"],
                    "evidence_ids": ["e_deepseek"],
                },
            ],
            subjects=[
                {
                    "position": 0,
                    "support_type": "measured_candidate",
                    "entity_type": "brand",
                    "identity_type": "brand",
                    "canonical_key_snapshot": "minimax",
                    "name_en_snapshot": "Minimax",
                    "name_zh_cn_snapshot": "中minimax",
                    "candidate_id": "minimax:full_window",
                    "evidence_ids": [],
                }
            ],
        )

    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.GENERATING
    assert not row.is_current


def test_newer_facts_replace_current_and_older_or_old_epoch_cannot_regress():
    first = _reserve(facts_as_of=NOW, epoch=2)
    assert _publish(first)

    newer = _reserve(
        source_cycle_id="cycle-new",
        fingerprint="e" * 64,
        facts_as_of=NOW + timedelta(minutes=15),
        epoch=2,
        owner="worker-new",
    )
    assert _publish(
        newer,
        owner="worker-new",
        body_suffix=" now",
        now=NOW + timedelta(minutes=16),
    )

    stale = _reserve(
        source_cycle_id="cycle-stale",
        fingerprint="f" * 64,
        facts_as_of=NOW - timedelta(minutes=15),
        epoch=2,
        owner="worker-stale",
    )
    assert not _publish(
        stale,
        owner="worker-stale",
        body_suffix=" stale",
        now=NOW + timedelta(minutes=17),
    )
    rollback = _reserve(
        source_cycle_id="cycle-old-epoch",
        fingerprint="0" * 64,
        facts_as_of=NOW + timedelta(hours=1),
        epoch=1,
        owner="worker-old",
    )
    assert not _publish(
        rollback,
        owner="worker-old",
        body_suffix=" old epoch",
        now=NOW + timedelta(minutes=18),
    )

    newer.refresh_from_db()
    first.refresh_from_db()
    stale.refresh_from_db()
    rollback.refresh_from_db()
    assert newer.is_current is True
    assert first.status == TrendNarrative.Status.SUPERSEDED
    assert stale.status == TrendNarrative.Status.SUPERSEDED
    assert rollback.status == TrendNarrative.Status.SUPERSEDED


def test_higher_epoch_can_replace_newer_facts_and_rollback_epoch_cannot():
    current = _reserve(facts_as_of=NOW + timedelta(hours=1), epoch=1)
    assert _publish(current)
    candidate = _reserve(
        source_cycle_id="cycle-epoch-2",
        fingerprint="2" * 64,
        facts_as_of=NOW,
        epoch=2,
        owner="worker-2",
    )

    assert _publish(candidate, owner="worker-2")
    candidate.refresh_from_db()
    assert candidate.is_current is True


@pytest.mark.django_db(transaction=True)
def test_concurrent_cold_publish_serializes_and_newer_facts_win():
    older = _reserve(
        source_cycle_id="concurrent-old",
        facts_as_of=NOW,
        owner="worker-old",
    )
    newer = _reserve(
        source_cycle_id="concurrent-new",
        fingerprint="7" * 64,
        facts_as_of=NOW + timedelta(minutes=15),
        owner="worker-new",
    )

    def publish(row_id: int, owner: str, fence: int) -> bool:
        close_old_connections()
        try:
            assert mark_transport_started(
                row_id,
                owner=owner,
                fence=fence,
                now=NOW,
            )
            _complete_transport(
                TrendNarrative.objects.get(pk=row_id),
                owner=owner,
                now=NOW + timedelta(minutes=15),
            )
            return publish_generation(
                row_id,
                owner=owner,
                fence=fence,
                body_en="MiniMax leads attention.",
                body_zh_cn="MiniMax 引领关注。",
                output_hash=f"{row_id:064x}",
                input_tokens=10,
                output_tokens=5,
                latency_ms=100,
                now=NOW + timedelta(minutes=16),
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda values: publish(*values),
                [
                    (older.pk, "worker-old", older.claim_fence),
                    (newer.pk, "worker-new", newer.claim_fence),
                ],
            )
        )

    assert sum(results) in {1, 2}
    current = TrendNarrative.objects.get(window_days=1, is_current=True)
    assert current.pk == newer.pk
    assert TrendNarrative.objects.filter(window_days=1, is_current=True).count() == 1


def test_same_fingerprint_advances_only_strictly_newer_complete_check_tuple():
    current = _reserve()
    assert _publish(current)
    before_count = TrendNarrative.objects.count()

    assert advance_current_check(
        window_days=1,
        semantic_fingerprint="a" * 64,
        source_cycle_id="cycle-b",
        checked_as_of=NOW + timedelta(minutes=15),
        checked_at=NOW + timedelta(minutes=16),
        facts={**current.generation_facts, "as_of": "2026-08-12T12:15:00Z"},
    )
    assert not advance_current_check(
        window_days=1,
        semantic_fingerprint="a" * 64,
        source_cycle_id="cycle-c",
        checked_as_of=NOW + timedelta(minutes=15),
        checked_at=NOW + timedelta(minutes=17),
        facts={"would": "regress"},
    )

    current.refresh_from_db()
    assert TrendNarrative.objects.count() == before_count
    assert current.latest_checked_source_cycle_id == "cycle-b"
    assert current.latest_checked_as_of == NOW + timedelta(minutes=15)
    assert current.latest_checked_facts["as_of"] == "2026-08-12T12:15:00Z"


def test_brand_snapshot_survives_brand_deletion():
    row = _reserve()
    assert _publish(row)

    Brand.objects.get(pk="minimax").delete()
    row.refresh_from_db()

    assert row.primary_brand is None
    assert row.primary_brand_key == "minimax"
    assert row.primary_brand_name_en == "Minimax"
    assert row.primary_brand_name_zh_hans == "中minimax"
    assert row.body_en


@pytest.mark.parametrize("window_days", [0, 2, 14, 366])
def test_database_rejects_illegal_windows(window_days: int):
    with transaction.atomic(), pytest.raises(IntegrityError):
        TrendNarrative.objects.create(
            source_cycle_id=f"invalid-{window_days}",
            window_days=window_days,
            status=TrendNarrative.Status.CHECKED,
            facts_as_of=NOW,
        )


def test_database_rejects_invalid_current_and_generation_shapes():
    with transaction.atomic(), pytest.raises(IntegrityError):
        TrendNarrative.objects.create(
            source_cycle_id="bad-current",
            window_days=1,
            status=TrendNarrative.Status.CHECKED,
            is_current=True,
            facts_as_of=NOW,
        )
    with transaction.atomic(), pytest.raises(IntegrityError):
        TrendNarrative.objects.create(
            source_cycle_id="bad-generating",
            window_days=1,
            status=TrendNarrative.Status.GENERATING,
            facts_as_of=NOW,
        )


def test_retention_keeps_current_generating_recent_and_newest_twenty():
    current = _reserve()
    assert _publish(current)
    generating = _reserve(source_cycle_id="active", fingerprint="9" * 64)
    old_ids: list[int] = []
    for index in range(25):
        row = _reserve(
            source_cycle_id=f"history-{index:02d}",
            fingerprint=f"{index:064x}",
            owner=f"worker-{index}",
        )
        assert fail_generation(
            row.pk,
            owner=f"worker-{index}",
            fence=row.claim_fence,
            error_code="fixture_failure",
            now=NOW - timedelta(days=100, minutes=index),
        )
        old_ids.append(row.pk)
        TrendNarrative.objects.filter(pk=row.pk).update(
            created_at=NOW - timedelta(days=100, minutes=index)
        )
    recent = _reserve(source_cycle_id="recent", fingerprint="8" * 64)
    assert fail_generation(
        recent.pk,
        owner="worker-a",
        fence=recent.claim_fence,
        error_code="fixture_failure",
        now=NOW - timedelta(days=5),
    )
    TrendNarrative.objects.filter(pk=recent.pk).update(
        created_at=NOW - timedelta(days=5)
    )

    removed = prune_narrative_history(now=NOW)

    assert removed == 7
    assert TrendNarrative.objects.filter(pk=current.pk).exists()
    assert TrendNarrative.objects.filter(pk=generating.pk).exists()
    assert TrendNarrative.objects.filter(pk=recent.pk).exists()
    assert TrendNarrative.objects.filter(pk__in=old_ids).count() == 18
    assert prune_narrative_history(now=NOW) == 0


def _run(*, cycle: str, facts_as_of: datetime, brands: list[str]) -> TrendNarrativeRun:
    return TrendNarrativeRun.objects.create(
        source_cycle_id=cycle,
        window_days=1,
        facts_as_of=facts_as_of,
        packet_schema_version=3,
        snapshot={"private": True},
        brand_manifest=brands,
        batch_manifest=[[brands]],
        internal_order=brands,
    )


def _approved(run: TrendNarrativeRun, brand: Brand, *, now=NOW) -> BrandTrendNarrative:
    return prepare_brand_trend_narrative(
        run=run,
        brand_key=brand.nickname,
        brand_name_en=brand.display_name_en,
        brand_name_zh_cn=brand.display_name_zh_cn,
        status=BrandTrendNarrative.Status.APPROVED,
        attempted_at=now,
        verified_at=now,
        headline_en="Why it matters",
        headline_zh_cn="为什么重要",
        secondary_en="Discussion changed.",
        secondary_zh_cn="讨论发生了变化。",
        critic_decision=BrandTrendNarrative.CriticDecision.APPROVE,
        narrative_kind=BrandTrendNarrative.NarrativeKind.CONTENT_SHIFT,
        confidence=BrandTrendNarrative.Confidence.HIGH,
        selected_evidence_packet={"evidence": ["e1"]},
        final_critic_payload={"decision": "approve"},
    )


def test_u2_provider_call_identity_claim_reclaim_and_post_send_ambiguity():
    run = _run(cycle="u2-call", facts_as_of=NOW, brands=[])
    call = reserve_trend_narrative_provider_call(
        run=run,
        stage=TrendNarrativeProviderCall.Stage.RANK,
        batch_key="",
        request_identity="u2-call:rank",
        request_hash="a" * 64,
        request_packet={"dossiers": []},
        now=NOW,
    )
    assert call is not None
    assert (
        reserve_trend_narrative_provider_call(
            run=run,
            stage=TrendNarrativeProviderCall.Stage.RANK,
            batch_key="",
            request_identity="different-id-is-not-a-second-call",
            request_hash="b" * 64,
            request_packet={},
            now=NOW,
        )
        is None
    )
    first = claim_trend_narrative_provider_call(
        call.pk, owner="worker-a", now=NOW, lease_seconds=10
    )
    assert first is not None and first.claim_fence == 1
    assert (
        claim_trend_narrative_provider_call(
            call.pk, owner="worker-b", now=NOW + timedelta(seconds=1), lease_seconds=10
        )
        is None
    )
    second = claim_trend_narrative_provider_call(
        call.pk, owner="worker-b", now=NOW + timedelta(seconds=11), lease_seconds=10
    )
    assert second is not None and second.claim_fence == 2
    assert mark_trend_narrative_provider_call_sent(
        call.pk, owner="worker-b", fence=2, now=NOW + timedelta(seconds=12)
    )
    assert mark_trend_narrative_provider_call_ambiguous(
        call.pk,
        owner="worker-b",
        fence=2,
        error_code="response_lost_after_send",
        now=NOW + timedelta(seconds=13),
    )
    call.refresh_from_db()
    assert call.state == TrendNarrativeProviderCall.State.AMBIGUOUS
    assert (
        claim_trend_narrative_provider_call(
            call.pk, owner="worker-c", now=NOW + timedelta(days=1), lease_seconds=10
        )
        is None
    )


def test_u2_complete_response_is_terminal_and_retains_response_proof():
    run = _run(cycle="u2-complete", facts_as_of=NOW, brands=[])
    call = reserve_trend_narrative_provider_call(
        run=run,
        stage=TrendNarrativeProviderCall.Stage.EDITOR,
        batch_key="001",
        request_identity="u2-complete:editor:001",
        request_hash="a" * 64,
        request_packet={"private_packet": True},
        now=NOW,
    )
    assert call is not None
    claimed = claim_trend_narrative_provider_call(
        call.pk, owner="worker", now=NOW, lease_seconds=10
    )
    assert claimed is not None
    assert mark_trend_narrative_provider_call_sent(
        call.pk, owner="worker", fence=claimed.claim_fence, now=NOW
    )
    assert complete_trend_narrative_provider_call(
        call.pk,
        owner="worker",
        fence=claimed.claim_fence,
        response_hash="c" * 64,
        response_payload={"response": "durable"},
        now=NOW + timedelta(seconds=1),
    )
    call.refresh_from_db()
    assert call.state == TrendNarrativeProviderCall.State.COMPLETED
    assert call.response_payload == {"response": "durable"}
    assert not mark_trend_narrative_provider_call_sent(
        call.pk,
        owner="worker",
        fence=claimed.claim_fence,
        now=NOW + timedelta(seconds=2),
    )


@pytest.mark.django_db(transaction=True)
def test_u2_concurrent_workers_cannot_claim_one_transport_twice():
    run = _run(cycle="u2-concurrent", facts_as_of=NOW, brands=[])
    call = reserve_trend_narrative_provider_call(
        run=run,
        stage=TrendNarrativeProviderCall.Stage.CRITIC,
        batch_key="001",
        request_identity="u2-concurrent:critic:001",
        request_hash="a" * 64,
        request_packet={},
        now=NOW,
    )
    assert call is not None

    def claim(owner: str):
        close_old_connections()
        try:
            result = claim_trend_narrative_provider_call(
                call.pk, owner=owner, now=NOW, lease_seconds=60
            )
            return result.claim_owner if result is not None else None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        owners = list(pool.map(claim, ["worker-a", "worker-b"]))
    assert sorted(owner for owner in owners if owner is not None) in [
        ["worker-a"],
        ["worker-b"],
    ]
    call.refresh_from_db()
    assert call.claim_fence == 1


def test_u2_prepared_rows_activate_only_as_one_newer_complete_cutoff_and_hold_last_good():
    minimax, deepseek = _brand("u2-minimax"), _brand("u2-deepseek")
    first = _run(
        cycle="u2-first", facts_as_of=NOW, brands=[minimax.nickname, deepseek.nickname]
    )
    first_minimax = _approved(first, minimax)
    assert first_minimax.critic_decision == "approve"
    assert first_minimax.narrative_kind == "content_shift"
    assert first_minimax.confidence == "high"
    _approved(first, deepseek)
    assert activate_trend_narrative_run(first.pk, now=NOW + timedelta(minutes=1))
    assert TrendNarrativeVisibleRun.objects.get(window_days=1).run_id == first.pk

    second = _run(
        cycle="u2-second",
        facts_as_of=NOW + timedelta(minutes=10),
        brands=[minimax.nickname, deepseek.nickname],
    )
    _approved(second, deepseek, now=NOW + timedelta(minutes=10))
    held = prepare_brand_trend_narrative(
        run=second,
        brand_key=minimax.nickname,
        brand_name_en=minimax.display_name_en,
        brand_name_zh_cn=minimax.display_name_zh_cn,
        status=BrandTrendNarrative.Status.HELD,
        attempted_at=NOW + timedelta(minutes=10),
        error_code="critic_hold",
    )
    assert held.status == BrandTrendNarrative.Status.HELD
    assert held.last_good_id == first_minimax.pk
    assert held.last_good.verified_at == first_minimax.verified_at
    assert activate_trend_narrative_run(second.pk, now=NOW + timedelta(minutes=11))
    assert TrendNarrativeVisibleRun.objects.get(window_days=1).run_id == second.pk
    first.refresh_from_db()
    assert first.status == TrendNarrativeRun.Status.SUPERSEDED
    assert first.activated_at == NOW + timedelta(minutes=1)

    third = _run(
        cycle="u2-third",
        facts_as_of=NOW + timedelta(minutes=20),
        brands=[minimax.nickname, deepseek.nickname],
    )
    _approved(third, deepseek, now=NOW + timedelta(minutes=20))
    held_again = prepare_brand_trend_narrative(
        run=third,
        brand_key=minimax.nickname,
        brand_name_en=minimax.display_name_en,
        brand_name_zh_cn=minimax.display_name_zh_cn,
        status=BrandTrendNarrative.Status.HELD,
        attempted_at=NOW + timedelta(minutes=20),
        error_code="critic_hold_again",
    )
    assert held_again.status == BrandTrendNarrative.Status.HELD
    assert held_again.last_good_id == first_minimax.pk
    assert activate_trend_narrative_run(third.pk, now=NOW + timedelta(minutes=21))

    older = _run(
        cycle="u2-older",
        facts_as_of=NOW + timedelta(minutes=5),
        brands=[minimax.nickname, deepseek.nickname],
    )
    _approved(older, minimax, now=NOW + timedelta(minutes=5))
    _approved(older, deepseek, now=NOW + timedelta(minutes=5))
    assert not activate_trend_narrative_run(older.pk, now=NOW + timedelta(minutes=12))
    assert TrendNarrativeVisibleRun.objects.get(window_days=1).run_id == third.pk


def test_u2_activation_requires_every_manifest_brand_to_be_terminal():
    minimax, deepseek = _brand("u2-pending-minimax"), _brand("u2-pending-deepseek")
    run = _run(
        cycle="u2-incomplete",
        facts_as_of=NOW,
        brands=[minimax.nickname, deepseek.nickname],
    )
    _approved(run, minimax)
    assert not activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=1))
    assert not TrendNarrativeVisibleRun.objects.filter(window_days=1).exists()
    prepare_brand_trend_narrative(
        run=run,
        brand_key=deepseek.nickname,
        brand_name_en=deepseek.display_name_en,
        brand_name_zh_cn=deepseek.display_name_zh_cn,
        status=BrandTrendNarrative.Status.DATA_QUALITY_UNAVAILABLE,
        attempted_at=NOW,
        error_code="enrichment_pending",
    )
    assert activate_trend_narrative_run(run.pk, now=NOW + timedelta(seconds=2))


@pytest.mark.django_db(transaction=True)
def test_u2_concurrent_first_pointer_activation_serializes_to_one_visible_run():
    alpha, beta = _brand("u2-cold-alpha"), _brand("u2-cold-beta")
    first = _run(cycle="u2-cold-first", facts_as_of=NOW, brands=[alpha.nickname])
    second = _run(cycle="u2-cold-second", facts_as_of=NOW, brands=[beta.nickname])
    _approved(first, alpha)
    _approved(second, beta)

    def activate(run_id: int) -> bool:
        close_old_connections()
        try:
            return activate_trend_narrative_run(run_id, now=NOW + timedelta(seconds=1))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate, [first.pk, second.pk]))
    assert results.count(True) == 1
    assert results.count(False) == 1
    assert TrendNarrativeVisibleRun.objects.filter(window_days=1).count() == 1


def test_u2_schema_pins_nullable_brand_snapshot_and_protected_last_good_proof():
    brand = _brand("u2-retained")
    run = _run(cycle="u2-retained-first", facts_as_of=NOW, brands=[brand.nickname])
    approved = _approved(run, brand)
    assert activate_trend_narrative_run(run.pk, now=NOW)
    later = _run(
        cycle="u2-retained-second",
        facts_as_of=NOW + timedelta(minutes=1),
        brands=[brand.nickname],
    )
    held = prepare_brand_trend_narrative(
        run=later,
        brand_key=brand.nickname,
        brand_name_en=brand.display_name_en,
        brand_name_zh_cn=brand.display_name_zh_cn,
        status=BrandTrendNarrative.Status.HELD,
        attempted_at=NOW + timedelta(minutes=1),
        error_code="hold",
    )
    brand.delete()
    approved.refresh_from_db()
    assert approved.brand is None
    assert approved.brand_key_snapshot == "u2-retained"
    with transaction.atomic(), pytest.raises(IntegrityError):
        BrandTrendNarrative.objects.filter(pk=approved.pk).delete()
    assert held.last_good_id == approved.pk


def test_u2_retention_keeps_visible_and_last_good_proof_runs():
    brand = _brand("u2-prune")
    original = _run(cycle="u2-prune-original", facts_as_of=NOW, brands=[brand.nickname])
    original_row = _approved(original, brand)
    assert activate_trend_narrative_run(original.pk, now=NOW)
    current = _run(
        cycle="u2-prune-current",
        facts_as_of=NOW + timedelta(minutes=1),
        brands=[brand.nickname],
    )
    prepare_brand_trend_narrative(
        run=current,
        brand_key=brand.nickname,
        brand_name_en=brand.display_name_en,
        brand_name_zh_cn=brand.display_name_zh_cn,
        status=BrandTrendNarrative.Status.HELD,
        attempted_at=NOW + timedelta(minutes=1),
        error_code="hold",
    )
    assert activate_trend_narrative_run(current.pk, now=NOW + timedelta(minutes=2))
    disposable = _run(
        cycle="u2-prune-disposable", facts_as_of=NOW - timedelta(minutes=1), brands=[]
    )
    TrendNarrativeRun.objects.filter(pk=disposable.pk).update(
        status=TrendNarrativeRun.Status.SUPERSEDED,
        activated_at=NOW - timedelta(days=100),
        created_at=NOW - timedelta(days=100),
    )
    TrendNarrativeRun.objects.filter(pk=original.pk).update(
        created_at=NOW - timedelta(days=100)
    )

    assert (
        prune_per_brand_trend_narrative_history(
            now=NOW, keep_days=30, keep_per_window=1
        )
        == 1
    )
    assert TrendNarrativeRun.objects.filter(pk=current.pk).exists()
    assert TrendNarrativeRun.objects.filter(pk=original.pk).exists()
    assert BrandTrendNarrative.objects.filter(pk=original_row.pk).exists()
    assert not TrendNarrativeRun.objects.filter(pk=disposable.pk).exists()
