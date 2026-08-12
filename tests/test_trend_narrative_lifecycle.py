"""PostgreSQL contracts for the trend-narrative publication ledger."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from core.models import Brand, TrendNarrativeVersion
from monitor.trend_narrative_lifecycle import (
    abandon_expired_attempts,
    advance_current_check,
    fail_generation,
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
) -> TrendNarrativeVersion:
    brand = Brand.objects.filter(pk="minimax").first() or _brand()
    row = reserve_generation(
        source_cycle_id=source_cycle_id,
        window_days=window_days,
        facts_as_of=facts_as_of,
        semantic_fingerprint=fingerprint,
        generation_facts=_facts(brand, as_of=facts_as_of),
        publication_epoch=epoch,
        prompt_version="headline-v1",
        provider="anthropic",
        provider_host="api.anthropic.com",
        model_name="claude-haiku-4-5-20251001",
        owner=owner,
        now=NOW,
        lease_seconds=lease_seconds,
    )
    assert row is not None
    return row


def _publish(
    row: TrendNarrativeVersion,
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
    return publish_generation(
        row.pk,
        owner=owner,
        fence=row.claim_fence,
        body_en=f"MiniMax leads attention{body_suffix}.",
        body_zh_hans=f"MiniMax 引领关注{body_suffix}。",
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
        model_name="claude-haiku-4-5-20251001",
        owner="worker-b",
        now=NOW,
        lease_seconds=60,
    )

    assert duplicate is None
    assert TrendNarrativeVersion.objects.count() == 1
    first.refresh_from_db()
    assert first.status == TrendNarrativeVersion.Status.GENERATING
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
        TrendNarrativeVersion.objects.filter(
            semantic_fingerprint="a" * 64,
            call_slot_consumed=True,
        ).count()
        == 2
    )


def test_expired_lease_is_abandoned_and_never_reopened_for_same_cycle():
    row = _reserve(lease_seconds=60)

    assert abandon_expired_attempts(now=NOW + timedelta(minutes=2)) == 1
    row.refresh_from_db()
    assert row.status == TrendNarrativeVersion.Status.ABANDONED
    assert row.call_slot_consumed is True
    assert not mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW + timedelta(minutes=2),
    )
    assert not _publish_late(row)
    assert TrendNarrativeVersion.objects.count() == 1


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
    assert row.status == TrendNarrativeVersion.Status.GENERATING
    assert row.is_current is False


def _publish_late(row: TrendNarrativeVersion) -> bool:
    return publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="Late English body.",
        body_zh_hans="迟到的中文内容。",
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

    assert row.status == TrendNarrativeVersion.Status.PUBLISHED
    assert row.is_current is True
    assert row.body_en == "MiniMax leads attention."
    assert (
        TrendNarrativeVersion.objects.filter(
            window_days=1,
            is_current=True,
        ).count()
        == 1
    )


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
    assert first.status == TrendNarrativeVersion.Status.SUPERSEDED
    assert stale.status == TrendNarrativeVersion.Status.SUPERSEDED
    assert rollback.status == TrendNarrativeVersion.Status.SUPERSEDED


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
            return publish_generation(
                row_id,
                owner=owner,
                fence=fence,
                body_en="MiniMax leads attention.",
                body_zh_hans="MiniMax 引领关注。",
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
    current = TrendNarrativeVersion.objects.get(window_days=1, is_current=True)
    assert current.pk == newer.pk
    assert (
        TrendNarrativeVersion.objects.filter(window_days=1, is_current=True).count()
        == 1
    )


def test_same_fingerprint_advances_only_strictly_newer_complete_check_tuple():
    current = _reserve()
    assert _publish(current)
    before_count = TrendNarrativeVersion.objects.count()

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
    assert TrendNarrativeVersion.objects.count() == before_count
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
        TrendNarrativeVersion.objects.create(
            source_cycle_id=f"invalid-{window_days}",
            window_days=window_days,
            status=TrendNarrativeVersion.Status.CHECKED,
            facts_as_of=NOW,
        )


def test_database_rejects_invalid_current_and_generation_shapes():
    with transaction.atomic(), pytest.raises(IntegrityError):
        TrendNarrativeVersion.objects.create(
            source_cycle_id="bad-current",
            window_days=1,
            status=TrendNarrativeVersion.Status.CHECKED,
            is_current=True,
            facts_as_of=NOW,
        )
    with transaction.atomic(), pytest.raises(IntegrityError):
        TrendNarrativeVersion.objects.create(
            source_cycle_id="bad-generating",
            window_days=1,
            status=TrendNarrativeVersion.Status.GENERATING,
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
        TrendNarrativeVersion.objects.filter(pk=row.pk).update(
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
    TrendNarrativeVersion.objects.filter(pk=recent.pk).update(
        created_at=NOW - timedelta(days=5)
    )

    removed = prune_narrative_history(now=NOW)

    assert removed == 7
    assert TrendNarrativeVersion.objects.filter(pk=current.pk).exists()
    assert TrendNarrativeVersion.objects.filter(pk=generating.pk).exists()
    assert TrendNarrativeVersion.objects.filter(pk=recent.pk).exists()
    assert TrendNarrativeVersion.objects.filter(pk__in=old_ids).count() == 18
    assert prune_narrative_history(now=NOW) == 0
