"""PostgreSQL contracts for the trend-narrative publication ledger."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from core.models import Brand, Product, TrendNarrative, TrendNarrativeSubject
from monitor.trend_narrative_lifecycle import (
    abandon_expired_attempts,
    advance_current_check,
    fail_generation,
    mark_transport_completed,
    mark_transport_started,
    prune_narrative_history,
    publish_generation,
    reserve_generation,
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
) -> TrendNarrative:
    brand = Brand.objects.filter(pk="minimax").first() or _brand()
    row = reserve_generation(
        source_cycle_id=source_cycle_id,
        window_days=window_days,
        facts_as_of=facts_as_of,
        semantic_fingerprint=fingerprint,
        generation_facts=(
            generation_facts or _facts(brand, as_of=facts_as_of)
        ),
        publication_epoch=epoch,
        prompt_version="headline-v1",
        provider="anthropic",
        provider_host="api.anthropic.com",
        llm_model_name="claude-haiku-4-5-20251001",
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
    assert abandon_expired_attempts(
        now=first_expired_at,
        cadence_minutes={1: 30},
        stale_minutes={1: 60},
    ) == 1

    second = _reserve(
        source_cycle_id="cycle-b",
        owner="worker-b",
        lease_seconds=60,
    )
    second_expired_at = NOW + timedelta(minutes=3)
    assert abandon_expired_attempts(
        now=second_expired_at,
        cadence_minutes={1: 30},
        stale_minutes={1: 60},
    ) == 1

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.consecutive_failures == 1
    assert second.consecutive_failures == 2
    assert second.next_attempt_at == second_expired_at + timedelta(minutes=60)


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
        row.subjects.values_list(
            "position", "support_type", "canonical_key_snapshot"
        )
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
    assert subject.observed_name == (
        "OffListModel" if identity == "ambiguous" else ""
    )
    assert subject.canonical_key_snapshot == {
        "brand": "offlist",
        "product": "vendor/OffListModel",
        "ambiguous": "",
    }[identity]
    assert bool(subject.brand_id) is (identity == "brand")
    assert bool(subject.product_id) is (identity == "product")


def test_invalid_schema_two_subjects_roll_back_the_whole_publication():
    snapshot = {
        **_facts(Brand.objects.filter(pk="minimax").first() or _brand()),
        "candidates": [
            {"candidate_id": "minimax:full_window", "evidence": []}
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
                    "candidate_id": "not-in-snapshot",
                    "evidence_ids": [],
                }
            ],
        )

    row.refresh_from_db()
    assert row.status == TrendNarrative.Status.GENERATING
    assert row.body_en == ""
    assert not row.subjects.exists()


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
    assert (
        TrendNarrative.objects.filter(window_days=1, is_current=True).count()
        == 1
    )


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
