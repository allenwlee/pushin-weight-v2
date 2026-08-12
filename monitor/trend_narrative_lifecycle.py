"""Transactional state changes for trend-narrative attempts and publication."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import IntegrityError, connection, transaction

from core.models import Brand, TrendNarrativeVersion

_ADVISORY_LOCK_NAMESPACE = 1_926_082_021
_TERMINAL_STATUSES = (
    TrendNarrativeVersion.Status.CHECKED,
    TrendNarrativeVersion.Status.SUPPRESSED,
    TrendNarrativeVersion.Status.ABANDONED,
    TrendNarrativeVersion.Status.FAILED,
    TrendNarrativeVersion.Status.PUBLISHED,
    TrendNarrativeVersion.Status.SUPERSEDED,
)


def record_no_call_check(
    *,
    source_cycle_id: str,
    window_days: int,
    facts_as_of,
    semantic_fingerprint: str,
    facts: dict[str, Any],
    checked_at,
    status: str,
    reason_code: str = "",
) -> TrendNarrativeVersion | None:
    """Record a due check that intentionally consumed no provider slot."""
    allowed = {
        TrendNarrativeVersion.Status.CHECKED,
        TrendNarrativeVersion.Status.SUPPRESSED,
    }
    if status not in allowed:
        raise ValueError("no-call rows must be checked or suppressed")
    primary = _brand_snapshot(facts.get("primary_brand"))
    secondary = _brand_snapshot(facts.get("secondary_brand"))
    try:
        with transaction.atomic():
            return TrendNarrativeVersion.objects.create(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                status=status,
                semantic_fingerprint=semantic_fingerprint,
                facts_as_of=facts_as_of,
                latest_checked_source_cycle_id=source_cycle_id,
                latest_checked_as_of=facts_as_of,
                latest_checked_at=checked_at,
                latest_checked_facts=facts,
                narrative_type=str(facts.get("narrative_type") or ""),
                coverage_state=str((facts.get("coverage") or {}).get("state") or ""),
                primary_brand=primary["brand"],
                primary_brand_key=primary["key"],
                primary_brand_name_en=primary["name_en"],
                primary_brand_name_zh_hans=primary["name_zh_hans"],
                secondary_brand=secondary["brand"],
                secondary_brand_key=secondary["key"],
                secondary_brand_name_en=secondary["name_en"],
                secondary_brand_name_zh_hans=secondary["name_zh_hans"],
                error_code=reason_code[:64],
            )
    except IntegrityError:
        if TrendNarrativeVersion.objects.filter(
            source_cycle_id=source_cycle_id,
            window_days=window_days,
        ).exists():
            return None
        raise


def reserve_generation(
    *,
    source_cycle_id: str,
    window_days: int,
    facts_as_of,
    semantic_fingerprint: str,
    generation_facts: dict[str, Any],
    publication_epoch: int,
    prompt_version: str,
    provider: str,
    provider_host: str,
    model_name: str,
    owner: str,
    now,
    lease_seconds: int,
) -> TrendNarrativeVersion | None:
    """Irreversibly consume one call slot for a source-cycle/window pair.

    A duplicate returns ``None``. It never reclaims or reopens the existing
    row, even if that row's worker later expires.
    """
    if not owner or lease_seconds < 1:
        raise ValueError("owner and a positive lease_seconds are required")
    primary = _brand_snapshot(generation_facts.get("primary_brand"))
    secondary = _brand_snapshot(generation_facts.get("secondary_brand"))
    try:
        with transaction.atomic():
            return TrendNarrativeVersion.objects.create(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                status=TrendNarrativeVersion.Status.GENERATING,
                semantic_fingerprint=semantic_fingerprint,
                publication_epoch=publication_epoch,
                facts_as_of=facts_as_of,
                generation_facts=generation_facts,
                narrative_type=str(generation_facts.get("narrative_type") or ""),
                coverage_state=str(
                    (generation_facts.get("coverage") or {}).get("state") or ""
                ),
                primary_brand=primary["brand"],
                primary_brand_key=primary["key"],
                primary_brand_name_en=primary["name_en"],
                primary_brand_name_zh_hans=primary["name_zh_hans"],
                secondary_brand=secondary["brand"],
                secondary_brand_key=secondary["key"],
                secondary_brand_name_en=secondary["name_en"],
                secondary_brand_name_zh_hans=secondary["name_zh_hans"],
                prompt_version=prompt_version,
                provider=provider,
                provider_host=provider_host,
                model_name=model_name,
                call_slot_consumed=True,
                claim_owner=owner[:128],
                claim_fence=1,
                claimed_at=now,
                claim_expires_at=now + timedelta(seconds=lease_seconds),
            )
    except IntegrityError:
        if TrendNarrativeVersion.objects.filter(
            source_cycle_id=source_cycle_id,
            window_days=window_days,
        ).exists():
            return None
        raise


def mark_transport_started(
    attempt_id: int,
    *,
    owner: str,
    fence: int,
    now,
) -> bool:
    with transaction.atomic():
        row = _locked_attempt(attempt_id)
        if not _owns_generating(row, owner=owner, fence=fence, now=now):
            return False
        if row.transport_started_at is not None:
            return True
        row.transport_started_at = now
        row.save(update_fields=["transport_started_at", "updated_at"])
        return True


def mark_transport_completed(
    attempt_id: int,
    *,
    owner: str,
    fence: int,
    now,
) -> bool:
    """Record a provider response without granting it publication authority."""
    with transaction.atomic():
        row = _locked_attempt(attempt_id)
        if (
            not row.call_slot_consumed
            or row.claim_owner != owner
            or row.claim_fence != fence
        ):
            return False
        if row.transport_completed_at is not None:
            return True
        row.transport_completed_at = now
        row.save(update_fields=["transport_completed_at", "updated_at"])
        return True


def fail_generation(
    attempt_id: int,
    *,
    owner: str,
    fence: int,
    error_code: str,
    now,
    next_attempt_at=None,
) -> bool:
    if not error_code:
        raise ValueError("error_code is required")
    with transaction.atomic():
        row = _locked_attempt(attempt_id)
        if row.status == TrendNarrativeVersion.Status.FAILED:
            return row.claim_owner == owner and row.claim_fence == fence
        if not _owns_generating(row, owner=owner, fence=fence, now=now):
            return False
        row.status = TrendNarrativeVersion.Status.FAILED
        row.error_code = error_code[:64]
        row.next_attempt_at = next_attempt_at
        row.save(
            update_fields=[
                "status",
                "error_code",
                "next_attempt_at",
                "updated_at",
            ]
        )
        return True


def abandon_expired_attempts(*, now) -> int:
    return TrendNarrativeVersion.objects.filter(
        status=TrendNarrativeVersion.Status.GENERATING,
        claim_expires_at__lte=now,
    ).update(
        status=TrendNarrativeVersion.Status.ABANDONED,
        error_code="lease_expired",
        next_attempt_at=None,
    )


def publish_generation(
    attempt_id: int,
    *,
    owner: str,
    fence: int,
    body_en: str,
    body_zh_hans: str,
    output_hash: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    now,
) -> bool:
    """Publish if this attempt strictly outranks the current row.

    The per-window advisory lock also serializes the no-current cold start,
    where row locks alone cannot protect a row that does not exist yet.
    """
    with transaction.atomic():
        row = _locked_attempt(attempt_id)
        _lock_window(row.window_days)
        row.refresh_from_db()
        if row.status in (
            TrendNarrativeVersion.Status.PUBLISHED,
            TrendNarrativeVersion.Status.SUPERSEDED,
        ):
            return row.is_current
        if not _owns_generating(row, owner=owner, fence=fence, now=now):
            return False
        if row.transport_started_at is None:
            return False

        current = (
            TrendNarrativeVersion.objects.select_for_update()
            .filter(window_days=row.window_days, is_current=True)
            .exclude(pk=row.pk)
            .first()
        )
        wins = current is None or _publication_key(row) > _publication_key(current)
        if wins and current is not None:
            current.is_current = False
            current.status = TrendNarrativeVersion.Status.SUPERSEDED
            current.save(update_fields=["is_current", "status", "updated_at"])

        row.status = (
            TrendNarrativeVersion.Status.PUBLISHED
            if wins
            else TrendNarrativeVersion.Status.SUPERSEDED
        )
        row.is_current = wins
        row.body_en = body_en
        row.body_zh_hans = body_zh_hans
        row.output_hash = output_hash
        row.transport_completed_at = now
        row.generated_at = now
        row.published_at = now
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.latency_ms = latency_ms
        row.latest_checked_source_cycle_id = row.source_cycle_id
        row.latest_checked_as_of = row.facts_as_of
        row.latest_checked_at = now
        row.latest_checked_facts = row.generation_facts
        row.error_code = ""
        row.next_attempt_at = None
        row.save(
            update_fields=[
                "status",
                "is_current",
                "body_en",
                "body_zh_hans",
                "output_hash",
                "transport_completed_at",
                "generated_at",
                "published_at",
                "input_tokens",
                "output_tokens",
                "latency_ms",
                "latest_checked_source_cycle_id",
                "latest_checked_as_of",
                "latest_checked_at",
                "latest_checked_facts",
                "error_code",
                "next_attempt_at",
                "updated_at",
            ]
        )
        return wins


def advance_current_check(
    *,
    window_days: int,
    semantic_fingerprint: str,
    source_cycle_id: str,
    checked_as_of,
    checked_at,
    facts: dict[str, Any],
) -> bool:
    """Advance freshness for semantically unchanged facts without a new row."""
    with transaction.atomic():
        _lock_window(window_days)
        row = (
            TrendNarrativeVersion.objects.select_for_update()
            .filter(
                window_days=window_days,
                is_current=True,
                semantic_fingerprint=semantic_fingerprint,
            )
            .first()
        )
        if row is None:
            return False
        prior_as_of = row.latest_checked_as_of or row.facts_as_of
        if checked_as_of <= prior_as_of or checked_at < checked_as_of:
            return False
        row.latest_checked_source_cycle_id = source_cycle_id
        row.latest_checked_as_of = checked_as_of
        row.latest_checked_at = checked_at
        row.latest_checked_facts = facts
        row.save(
            update_fields=[
                "latest_checked_source_cycle_id",
                "latest_checked_as_of",
                "latest_checked_at",
                "latest_checked_facts",
                "updated_at",
            ]
        )
        return True


def prune_narrative_history(
    *,
    now,
    keep_days: int = 90,
    keep_per_window: int = 20,
) -> int:
    """Delete only old terminal rows outside the newest per-window set."""
    if keep_days < 1 or keep_per_window < 1:
        raise ValueError("retention limits must be positive")
    cutoff = now - timedelta(days=keep_days)
    deleted = 0
    with transaction.atomic():
        for window_days in (1, 7, 30, 365):
            _lock_window(window_days)
            protected = set(
                TrendNarrativeVersion.objects.filter(
                    window_days=window_days,
                    status__in=_TERMINAL_STATUSES,
                )
                .order_by("-created_at", "-pk")
                .values_list("pk", flat=True)[:keep_per_window]
            )
            current_ids = set(
                TrendNarrativeVersion.objects.filter(
                    window_days=window_days,
                    is_current=True,
                ).values_list("pk", flat=True)
            )
            protected.update(current_ids)
            count, _ = TrendNarrativeVersion.objects.filter(
                window_days=window_days,
                status__in=_TERMINAL_STATUSES,
                created_at__lt=cutoff,
                is_current=False,
            ).exclude(pk__in=protected).delete()
            deleted += count
    return deleted


def _brand_snapshot(value: object) -> dict[str, Any]:
    snapshot = value if isinstance(value, dict) else {}
    key = str(snapshot.get("key") or "")
    return {
        "brand": Brand.objects.filter(pk=key).first() if key else None,
        "key": key,
        "name_en": str(snapshot.get("display_name_en") or ""),
        "name_zh_hans": str(snapshot.get("display_name_zh_hans") or ""),
    }


def _locked_attempt(attempt_id: int) -> TrendNarrativeVersion:
    return TrendNarrativeVersion.objects.select_for_update().get(pk=attempt_id)


def _owns_generating(
    row: TrendNarrativeVersion,
    *,
    owner: str,
    fence: int,
    now,
) -> bool:
    return (
        row.status == TrendNarrativeVersion.Status.GENERATING
        and row.call_slot_consumed
        and row.claim_owner == owner
        and row.claim_fence == fence
        and row.claim_expires_at is not None
        and row.claim_expires_at > now
    )


def _publication_key(row: TrendNarrativeVersion) -> tuple[int, Any]:
    return (row.publication_epoch, row.facts_as_of)


def _lock_window(window_days: int) -> None:
    if connection.vendor != "postgresql":
        raise RuntimeError("trend narrative publication requires PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [_ADVISORY_LOCK_NAMESPACE, window_days],
        )
