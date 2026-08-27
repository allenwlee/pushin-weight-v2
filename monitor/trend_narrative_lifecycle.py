"""Transactional state changes for trend-narrative attempts and publication."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.db.models import Q, QuerySet

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
from monitor.trend_narrative_coverage import selected_coverage_state

_ADVISORY_LOCK_NAMESPACE = 1_926_082_021
_TERMINAL_STATUSES = (
    TrendNarrative.Status.CHECKED,
    TrendNarrative.Status.SUPPRESSED,
    TrendNarrative.Status.ABANDONED,
    TrendNarrative.Status.FAILED,
    TrendNarrative.Status.PUBLISHED,
    TrendNarrative.Status.SUPERSEDED,
)
_FAILURE_STATUSES = (
    TrendNarrative.Status.FAILED,
    TrendNarrative.Status.ABANDONED,
)
_TERMINAL_BRAND_STATUSES = frozenset(
    {
        BrandTrendNarrative.Status.APPROVED,
        BrandTrendNarrative.Status.HELD,
        BrandTrendNarrative.Status.UNAVAILABLE,
        BrandTrendNarrative.Status.NO_CONTENT,
        BrandTrendNarrative.Status.DATA_QUALITY_UNAVAILABLE,
    }
)


def reserve_trend_narrative_provider_call(
    *,
    run: TrendNarrativeRun,
    stage: str,
    batch_key: str,
    request_identity: str,
    request_hash: str,
    request_packet: dict[str, Any],
    now,
) -> TrendNarrativeProviderCall | None:
    """Durably reserve one immutable transport identity for a stage/batch."""
    if stage not in TrendNarrativeProviderCall.Stage.values:
        raise ValueError("unsupported trend narrative provider stage")
    if not request_identity or not request_hash:
        raise ValueError("request identity and hash are required")
    try:
        with transaction.atomic():
            return TrendNarrativeProviderCall.objects.create(
                run=run,
                stage=stage,
                batch_key=batch_key,
                request_identity=request_identity,
                request_hash=request_hash,
                request_packet=request_packet,
                reserved_at=now,
            )
    except IntegrityError:
        return None


def claim_trend_narrative_provider_call(
    call_id: int,
    *,
    owner: str,
    now,
    lease_seconds: int,
) -> TrendNarrativeProviderCall | None:
    """Claim or reclaim only an unsent reservation under a growing fence."""
    if not owner or lease_seconds < 1:
        raise ValueError("owner and positive lease_seconds are required")
    with transaction.atomic():
        call = TrendNarrativeProviderCall.objects.select_for_update().get(pk=call_id)
        if call.state != TrendNarrativeProviderCall.State.RESERVED:
            return None
        if call.claim_expires_at is not None and call.claim_expires_at > now:
            return None
        call.claim_owner = owner[:128]
        call.claim_fence += 1
        call.claimed_at = now
        call.claim_expires_at = now + timedelta(seconds=lease_seconds)
        call.save(
            update_fields=[
                "claim_owner",
                "claim_fence",
                "claimed_at",
                "claim_expires_at",
                "updated_at",
            ]
        )
        return call


def mark_trend_narrative_provider_call_sent(
    call_id: int, *, owner: str, fence: int, now
) -> bool:
    """Set ``sent`` immediately before outbound transport; never reopen it."""
    with transaction.atomic():
        call = TrendNarrativeProviderCall.objects.select_for_update().get(pk=call_id)
        if not _owns_provider_call(call, owner=owner, fence=fence, now=now):
            return False
        call.state = TrendNarrativeProviderCall.State.SENT
        call.sent_at = now
        call.save(update_fields=["state", "sent_at", "updated_at"])
        return True


def complete_trend_narrative_provider_call(
    call_id: int,
    *,
    owner: str,
    fence: int,
    response_hash: str,
    response_payload: dict[str, Any],
    now,
) -> bool:
    """Persist a response once; a completed call cannot become a new send."""
    if not response_hash:
        raise ValueError("response_hash is required")
    with transaction.atomic():
        call = TrendNarrativeProviderCall.objects.select_for_update().get(pk=call_id)
        if call.state == TrendNarrativeProviderCall.State.COMPLETED:
            return call.claim_owner == owner and call.claim_fence == fence
        if call.state != TrendNarrativeProviderCall.State.SENT:
            return False
        if call.claim_owner != owner or call.claim_fence != fence:
            return False
        call.state = TrendNarrativeProviderCall.State.COMPLETED
        call.response_hash = response_hash
        call.response_payload = response_payload
        call.completed_at = now
        call.save(
            update_fields=[
                "state", "response_hash", "response_payload", "completed_at", "updated_at"
            ]
        )
        return True


def mark_trend_narrative_provider_call_ambiguous(
    call_id: int, *, owner: str, fence: int, error_code: str, now
) -> bool:
    """Record post-send uncertainty as terminal instead of retrying transport."""
    if not error_code:
        raise ValueError("error_code is required")
    with transaction.atomic():
        call = TrendNarrativeProviderCall.objects.select_for_update().get(pk=call_id)
        if call.state == TrendNarrativeProviderCall.State.AMBIGUOUS:
            return call.claim_owner == owner and call.claim_fence == fence
        if call.state != TrendNarrativeProviderCall.State.SENT:
            return False
        if call.claim_owner != owner or call.claim_fence != fence:
            return False
        call.state = TrendNarrativeProviderCall.State.AMBIGUOUS
        call.error_code = error_code[:64]
        call.save(update_fields=["state", "error_code", "updated_at"])
        return True


def prepare_brand_trend_narrative(
    *,
    run: TrendNarrativeRun,
    brand_key: str,
    brand_name_en: str,
    brand_name_zh_cn: str,
    status: str,
    attempted_at,
    verified_at=None,
    headline_en: str = "",
    headline_zh_cn: str = "",
    secondary_en: str = "",
    secondary_zh_cn: str = "",
    critic_decision: str = "",
    narrative_kind: str = "",
    confidence: str = "",
    selected_evidence_packet: dict[str, Any] | None = None,
    final_critic_payload: dict[str, Any] | None = None,
    error_code: str = "",
) -> BrandTrendNarrative:
    """Write one immutable per-brand terminal/prepared outcome for a run."""
    if status not in BrandTrendNarrative.Status.values:
        raise ValueError("unsupported brand narrative status")
    with transaction.atomic():
        existing = BrandTrendNarrative.objects.select_for_update().filter(
            run=run, brand_key_snapshot=brand_key
        ).first()
        if existing is not None:
            return existing
        last_good = None
        if status == BrandTrendNarrative.Status.HELD:
            visible = TrendNarrativeVisibleRun.objects.select_for_update().filter(
                window_days=run.window_days
            ).select_related("run").first()
            if visible is not None:
                last_good = BrandTrendNarrative.objects.filter(
                    run=visible.run,
                    brand_key_snapshot=brand_key,
                    status=BrandTrendNarrative.Status.APPROVED,
                ).first()
            if last_good is None:
                status = BrandTrendNarrative.Status.UNAVAILABLE
        return BrandTrendNarrative.objects.create(
            run=run,
            brand=Brand.objects.filter(pk=brand_key).first(),
            brand_key_snapshot=brand_key,
            brand_name_en_snapshot=brand_name_en,
            brand_name_zh_cn_snapshot=brand_name_zh_cn,
            status=status,
            headline_en=headline_en,
            headline_zh_cn=headline_zh_cn,
            secondary_en=secondary_en,
            secondary_zh_cn=secondary_zh_cn,
            critic_decision=critic_decision,
            narrative_kind=narrative_kind,
            confidence=confidence,
            selected_evidence_packet=selected_evidence_packet,
            final_critic_payload=final_critic_payload,
            attempted_at=attempted_at,
            verified_at=verified_at,
            error_code=error_code[:64],
            last_good=last_good,
        )


def activate_trend_narrative_run(run_id: int, *, now) -> bool:
    """Advance a visible cutoff only after every manifest brand is terminal."""
    with transaction.atomic():
        run = TrendNarrativeRun.objects.select_for_update().get(pk=run_id)
        # Row locking cannot serialize first-pointer creation because no
        # pointer row exists yet. The window advisory lock covers that cold
        # path and the ordinary pointer replacement path alike.
        _lock_window(run.window_days)
        manifest = [str(key) for key in run.brand_manifest]
        if len(manifest) != len(set(manifest)):
            raise ValueError("run brand manifest must have unique keys")
        outcomes = list(
            BrandTrendNarrative.objects.select_for_update().filter(run=run)
        )
        if (
            {row.brand_key_snapshot for row in outcomes} != set(manifest)
            or any(row.status not in _TERMINAL_BRAND_STATUSES for row in outcomes)
        ):
            return False
        pointer = TrendNarrativeVisibleRun.objects.select_for_update().filter(
            window_days=run.window_days
        ).select_related("run").first()
        if pointer is not None and run.facts_as_of <= pointer.facts_as_of:
            return False
        if pointer is not None:
            previous = pointer.run
            if previous.status == TrendNarrativeRun.Status.ACTIVE:
                previous.status = TrendNarrativeRun.Status.SUPERSEDED
                # Historical activation marks the moment this cutoff became
                # visible, not the later moment a newer cutoff superseded it.
                previous.save(update_fields=["status", "updated_at"])
            pointer.run = run
            pointer.facts_as_of = run.facts_as_of
            pointer.activated_at = now
            pointer.save(update_fields=["run", "facts_as_of", "activated_at", "updated_at"])
        else:
            TrendNarrativeVisibleRun.objects.create(
                window_days=run.window_days,
                run=run,
                facts_as_of=run.facts_as_of,
                activated_at=now,
            )
        run.status = TrendNarrativeRun.Status.ACTIVE
        run.activated_at = now
        run.save(update_fields=["status", "activated_at", "updated_at"])
        return True


def prune_per_brand_trend_narrative_history(
    *, now, keep_days: int = 90, keep_per_window: int = 20
) -> int:
    """Prune only unreferenced old runs; visible and last-good proof pins win."""
    if keep_days < 1 or keep_per_window < 1:
        raise ValueError("retention limits must be positive")
    cutoff = now - timedelta(days=keep_days)
    deleted = 0
    with transaction.atomic():
        pinned_run_ids = set(
            TrendNarrativeVisibleRun.objects.values_list("run_id", flat=True)
        )
        pinned_run_ids.update(
            BrandTrendNarrative.objects.filter(last_good__isnull=False).values_list(
                "last_good__run_id", flat=True
            )
        )
        for window_days in (1, 7, 30, 365):
            _lock_window(window_days)
            newest_ids = set(
                TrendNarrativeRun.objects.filter(window_days=window_days)
                .order_by("-created_at", "-pk")
                .values_list("pk", flat=True)[:keep_per_window]
            )
            protected = pinned_run_ids | newest_ids
            count, _ = TrendNarrativeRun.objects.filter(
                window_days=window_days,
                created_at__lt=cutoff,
                status=TrendNarrativeRun.Status.SUPERSEDED,
            ).exclude(pk__in=protected).delete()
            deleted += count
    return deleted


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
) -> TrendNarrative | None:
    """Record a due check that intentionally consumed no provider slot."""
    allowed = {
        TrendNarrative.Status.CHECKED,
        TrendNarrative.Status.SUPPRESSED,
    }
    if status not in allowed:
        raise ValueError("no-call rows must be checked or suppressed")
    primary = _brand_snapshot(facts.get("primary_brand"))
    secondary = _brand_snapshot(facts.get("secondary_brand"))
    try:
        with transaction.atomic():
            return TrendNarrative.objects.create(
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
                coverage_state=selected_coverage_state(facts),
                primary_brand=primary["brand"],
                primary_brand_key=primary["key"],
                primary_brand_name_en=primary["name_en"],
                primary_brand_name_zh_hans=primary["name_zh_cn"],
                secondary_brand=secondary["brand"],
                secondary_brand_key=secondary["key"],
                secondary_brand_name_en=secondary["name_en"],
                secondary_brand_name_zh_hans=secondary["name_zh_cn"],
                error_code=reason_code[:64],
            )
    except IntegrityError:
        if TrendNarrative.objects.filter(
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
    llm_model_name: str,
    owner: str,
    now,
    lease_seconds: int,
    output_schema_version: int = 1,
) -> TrendNarrative | None:
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
            return TrendNarrative.objects.create(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                status=TrendNarrative.Status.GENERATING,
                semantic_fingerprint=semantic_fingerprint,
                publication_epoch=publication_epoch,
                facts_as_of=facts_as_of,
                generation_facts=generation_facts,
                output_schema_version=output_schema_version,
                narrative_type=str(generation_facts.get("narrative_type") or ""),
                coverage_state=selected_coverage_state(generation_facts),
                primary_brand=primary["brand"],
                primary_brand_key=primary["key"],
                primary_brand_name_en=primary["name_en"],
                primary_brand_name_zh_hans=primary["name_zh_cn"],
                secondary_brand=secondary["brand"],
                secondary_brand_key=secondary["key"],
                secondary_brand_name_en=secondary["name_en"],
                secondary_brand_name_zh_hans=secondary["name_zh_cn"],
                prompt_version=prompt_version,
                provider=provider,
                provider_host=provider_host,
                model_name=llm_model_name,
                llm_model_name=llm_model_name,
                call_slot_consumed=True,
                claim_owner=owner[:128],
                claim_fence=1,
                claimed_at=now,
                claim_expires_at=now + timedelta(seconds=lease_seconds),
            )
    except IntegrityError:
        if TrendNarrative.objects.filter(
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
    consecutive_failures: int = 1,
) -> bool:
    if not error_code or consecutive_failures < 1:
        raise ValueError("error_code and a positive failure count are required")
    with transaction.atomic():
        row = _locked_attempt(attempt_id)
        if row.status == TrendNarrative.Status.FAILED:
            return row.claim_owner == owner and row.claim_fence == fence
        if not _owns_generating(row, owner=owner, fence=fence, now=now):
            return False
        row.status = TrendNarrative.Status.FAILED
        row.error_code = error_code[:64]
        row.next_attempt_at = next_attempt_at
        row.consecutive_failures = consecutive_failures
        row.save(
            update_fields=[
                "status",
                "error_code",
                "next_attempt_at",
                "consecutive_failures",
                "updated_at",
            ]
        )
        return True


def next_failure_backoff(
    failures: QuerySet[TrendNarrative],
    *,
    window_days: int,
    now,
    cadence_minutes: Mapping[int, int],
    stale_minutes: Mapping[int, int],
) -> tuple[int, Any]:
    """Return the durable count and bounded retry time for one failure scope."""
    latest_failure = failures.order_by("-created_at", "-pk").first()
    previous_failures = (
        latest_failure.consecutive_failures
        if latest_failure and latest_failure.consecutive_failures
        else failures.count()
    )
    consecutive_failures = previous_failures + 1
    delay_minutes = cadence_minutes[window_days]
    for _ in range(consecutive_failures - 1):
        delay_minutes = min(delay_minutes * 2, stale_minutes[window_days])
        if delay_minutes == stale_minutes[window_days]:
            break
    return consecutive_failures, now + timedelta(minutes=delay_minutes)


def generation_failure_history(
    *,
    window_days: int,
    semantic_fingerprint: str,
    publication_epoch: int,
    prompt_version: str,
    provider: str,
    provider_host: str,
    llm_model_name: str,
    transport_completed: bool,
) -> QuerySet[TrendNarrative]:
    """Select failures that share the applicable retry identity.

    A provider response makes a failure content-specific, so its retry scope
    stays on the semantic fingerprint. Failures before a response represent
    transport/runtime availability and must survive changing harvested
    evidence, while remaining isolated to the exact provider configuration.
    """
    failures = TrendNarrative.objects.filter(
        window_days=window_days,
        status__in=_FAILURE_STATUSES,
    )
    if transport_completed:
        return failures.filter(
            semantic_fingerprint=semantic_fingerprint,
            transport_completed_at__isnull=False,
        )
    return failures.filter(
        publication_epoch=publication_epoch,
        prompt_version=prompt_version,
        provider=provider,
        provider_host=provider_host,
        llm_model_name=llm_model_name,
        transport_completed_at__isnull=True,
    )


def has_active_generation_backoff(
    *,
    window_days: int,
    semantic_fingerprint: str,
    publication_epoch: int,
    prompt_version: str,
    provider: str,
    provider_host: str,
    llm_model_name: str,
    now,
) -> bool:
    """Check content-specific and transport-wide backoff in one query."""
    content_scope = Q(
        semantic_fingerprint=semantic_fingerprint,
        transport_completed_at__isnull=False,
    )
    transport_scope = Q(
        publication_epoch=publication_epoch,
        prompt_version=prompt_version,
        provider=provider,
        provider_host=provider_host,
        llm_model_name=llm_model_name,
        transport_completed_at__isnull=True,
    )
    return TrendNarrative.objects.filter(
        content_scope | transport_scope,
        window_days=window_days,
        status__in=_FAILURE_STATUSES,
        next_attempt_at__gt=now,
    ).exists()


def attempt_failure_history(
    attempt: TrendNarrative,
    *,
    transport_completed: bool,
) -> QuerySet[TrendNarrative]:
    """Select retry history using the persisted attempt identity."""
    return generation_failure_history(
        window_days=attempt.window_days,
        semantic_fingerprint=attempt.semantic_fingerprint,
        publication_epoch=attempt.publication_epoch,
        prompt_version=attempt.prompt_version,
        provider=attempt.provider,
        provider_host=attempt.provider_host,
        llm_model_name=attempt.llm_model_name or attempt.model_name,
        transport_completed=transport_completed,
    )


def abandon_expired_attempts(
    *,
    now,
    cadence_minutes: Mapping[int, int],
    stale_minutes: Mapping[int, int],
) -> int:
    """Abandon expired leases without erasing their applicable backoff."""
    with transaction.atomic():
        expired = list(
            TrendNarrative.objects.select_for_update()
            .filter(
                status=TrendNarrative.Status.GENERATING,
                claim_expires_at__lte=now,
            )
            .order_by("claim_expires_at", "pk")
        )
        for row in expired:
            prior_failures = attempt_failure_history(
                row,
                transport_completed=row.transport_completed_at is not None,
            ).exclude(pk=row.pk)
            failures, next_attempt_at = next_failure_backoff(
                prior_failures,
                window_days=row.window_days,
                now=now,
                cadence_minutes=cadence_minutes,
                stale_minutes=stale_minutes,
            )
            row.status = TrendNarrative.Status.ABANDONED
            row.error_code = "lease_expired"
            row.consecutive_failures = failures
            row.next_attempt_at = next_attempt_at
            row.save(
                update_fields=[
                    "status",
                    "error_code",
                    "consecutive_failures",
                    "next_attempt_at",
                    "updated_at",
                ]
            )
        return len(expired)


def publish_generation(
    attempt_id: int,
    *,
    owner: str,
    fence: int,
    body_en: str,
    body_zh_cn: str,
    output_hash: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    now,
    observations_en: Sequence[str] = (),
    observations_zh_cn: Sequence[str] = (),
    selected_candidate_ids: Sequence[str] = (),
    claims: Sequence[Mapping[str, Any]] = (),
    subjects: Sequence[Mapping[str, Any]] = (),
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
            TrendNarrative.Status.PUBLISHED,
            TrendNarrative.Status.SUPERSEDED,
        ):
            return row.is_current
        if not _owns_generating(row, owner=owner, fence=fence, now=now):
            return False
        if row.transport_started_at is None or row.transport_completed_at is None:
            return False

        publication = _validate_publication_payload(
            row,
            body_en=body_en,
            body_zh_cn=body_zh_cn,
            observations_en=observations_en,
            observations_zh_cn=observations_zh_cn,
            selected_candidate_ids=selected_candidate_ids,
            claims=claims,
            subjects=subjects,
        )

        current = (
            TrendNarrative.objects.select_for_update()
            .filter(window_days=row.window_days, is_current=True)
            .exclude(pk=row.pk)
            .first()
        )
        wins = current is None or _publication_key(row) > _publication_key(current)
        if wins and current is not None:
            current.is_current = False
            current.status = TrendNarrative.Status.SUPERSEDED
            current.save(update_fields=["is_current", "status", "updated_at"])

        row.status = (
            TrendNarrative.Status.PUBLISHED
            if wins
            else TrendNarrative.Status.SUPERSEDED
        )
        row.is_current = wins
        row.body_en = body_en
        row.body_zh_cn = body_zh_cn
        row.body_zh_hans = body_zh_cn
        row.observations_en = publication["observations_en"]
        row.observations_zh_cn = publication["observations_zh_cn"]
        row.selected_candidate_ids = publication["selected_candidate_ids"]
        row.claims = publication["claims"]
        if publication["subjects"]:
            _write_subjects(row, publication["subjects"])
            _write_legacy_subject_snapshots(row, publication["subjects"])
        row.output_hash = output_hash
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
                "body_zh_cn",
                "body_zh_hans",
                "observations_en",
                "observations_zh_cn",
                "selected_candidate_ids",
                "claims",
                "primary_brand",
                "primary_brand_key",
                "primary_brand_name_en",
                "primary_brand_name_zh_hans",
                "secondary_brand",
                "secondary_brand_key",
                "secondary_brand_name_en",
                "secondary_brand_name_zh_hans",
                "output_hash",
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
            TrendNarrative.objects.select_for_update()
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
                TrendNarrative.objects.filter(
                    window_days=window_days,
                    status__in=_TERMINAL_STATUSES,
                )
                .order_by("-created_at", "-pk")
                .values_list("pk", flat=True)[:keep_per_window]
            )
            current_ids = set(
                TrendNarrative.objects.filter(
                    window_days=window_days,
                    is_current=True,
                ).values_list("pk", flat=True)
            )
            protected.update(current_ids)
            count, _ = TrendNarrative.objects.filter(
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
        "name_zh_cn": str(
            snapshot.get("display_name_zh_cn")
            or snapshot.get("display_name_zh_hans")
            or ""
        ),
    }


def _validate_publication_payload(
    row: TrendNarrative,
    *,
    body_en: str,
    body_zh_cn: str,
    observations_en: Sequence[str],
    observations_zh_cn: Sequence[str],
    selected_candidate_ids: Sequence[str],
    claims: Sequence[Mapping[str, Any]],
    subjects: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "observations_en": list(observations_en),
        "observations_zh_cn": list(observations_zh_cn),
        "selected_candidate_ids": list(selected_candidate_ids),
        "claims": [dict(claim) for claim in claims],
        "subjects": [dict(subject) for subject in subjects],
    }
    if row.output_schema_version == 1:
        if any(payload.values()):
            raise ValueError("schema-1 publications cannot contain schema-2 output")
        return payload
    if row.output_schema_version not in {2, 3}:
        raise ValueError("unsupported trend narrative output schema")
    payload["subjects"] = _resolve_evidence_subject_identities(
        payload["subjects"]
    )
    if len(payload["observations_en"]) != len(payload["observations_zh_cn"]):
        raise ValueError("schema-2 observations must be bilingual")
    if len(payload["observations_en"]) > 2:
        raise ValueError("schema-2 supports at most two observations")
    if len(payload["claims"]) != len(payload["observations_en"]) + 1 or [
        claim.get("observation_index") for claim in payload["claims"]
    ] != [-1, *range(len(payload["observations_en"]))]:
        raise ValueError("schema-2 claims must cover headline then observations")
    if row.output_schema_version == 3:
        _validate_schema_three_claims(
            row,
            body_en=body_en,
            body_zh_cn=body_zh_cn,
            payload=payload,
        )
    if len(payload["selected_candidate_ids"]) not in {1, 2} or len(
        set(payload["selected_candidate_ids"])
    ) != len(payload["selected_candidate_ids"]):
        raise ValueError("schema-2 candidate selection must contain one or two IDs")
    candidates = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in (row.generation_facts or {}).get("candidates", [])
        if isinstance(candidate, Mapping) and candidate.get("candidate_id")
    }
    if not candidates or any(
        candidate_id not in candidates
        for candidate_id in payload["selected_candidate_ids"]
    ):
        raise ValueError("selected candidates must exist in generation facts")
    if len(payload["subjects"]) not in {1, 2}:
        raise ValueError("schema-2 publications require one or two subjects")
    positions = [subject.get("position") for subject in payload["subjects"]]
    if positions != list(range(len(payload["subjects"]))):
        raise ValueError("subject positions must be contiguous and ordered")
    measured = [
        subject
        for subject in payload["subjects"]
        if subject.get("support_type")
        == TrendNarrativeSubject.SupportType.MEASURED_CANDIDATE
    ]
    evidence_only = [
        subject
        for subject in payload["subjects"]
        if subject.get("support_type")
        == TrendNarrativeSubject.SupportType.EVIDENCE_ONLY
    ]
    if payload["subjects"][0].get("support_type") != (
        TrendNarrativeSubject.SupportType.MEASURED_CANDIDATE
    ):
        raise ValueError("the primary subject must be a measured candidate")
    measured_ids = [str(subject.get("candidate_id") or "") for subject in measured]
    if measured_ids != payload["selected_candidate_ids"]:
        raise ValueError("measured subjects must match selected candidates")
    evidence_owners: dict[str, set[str]] = {}
    for candidate_id, candidate in candidates.items():
        for evidence in candidate.get("evidence", []):
            if isinstance(evidence, Mapping) and evidence.get("evidence_id"):
                evidence_owners.setdefault(
                    str(evidence["evidence_id"]), set()
                ).add(candidate_id)
    selected_ids = set(payload["selected_candidate_ids"])
    for claim in payload["claims"]:
        claim_candidate_ids = set(
            claim.get("candidate_ids") or payload["selected_candidate_ids"]
        )
        for evidence_id in claim.get("evidence_ids") or []:
            owners = evidence_owners.get(str(evidence_id))
            if not owners or not owners.intersection(claim_candidate_ids):
                raise ValueError("claim evidence must belong to its candidates")
    for subject in evidence_only:
        evidence_ids = list(subject.get("evidence_ids") or [])
        if not evidence_ids or any(
            not evidence_owners.get(str(evidence_id), set()).intersection(
                selected_ids
            )
            for evidence_id in evidence_ids
        ):
            raise ValueError(
                "evidence-only subjects require selected-candidate evidence"
            )
    if len(measured) == 2:
        measured_keys = [
            str(subject.get("canonical_key_snapshot") or "")
            for subject in measured
        ]
        if not all(measured_keys) or len(set(measured_keys)) != 2:
            raise ValueError("two measured subjects must have distinct identities")
    elif len(measured) != 1 or len(evidence_only) > 1:
        raise ValueError("invalid measured/evidence-only subject combination")
    return payload


def _validate_schema_three_claims(
    row: TrendNarrative,
    *,
    body_en: str,
    body_zh_cn: str,
    payload: Mapping[str, Any],
) -> None:
    try:
        packet = project_provider_packet(row.generation_facts or {})
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("schema-3 generation facts are invalid") from exc
    facts = {
        str(fact["fact_id"]): fact
        for candidate in packet.get("candidates", [])
        for fact in candidate.get("quantitative_facts", [])
        if fact.get("fact_id")
    }
    names_en = {
        str(subject.get("name_en_snapshot") or "")
        for subject in payload["subjects"]
        if subject.get("name_en_snapshot")
    }
    names_zh_cn = {
        str(subject.get("name_zh_cn_snapshot") or "")
        for subject in payload["subjects"]
        if subject.get("name_zh_cn_snapshot")
    }
    texts_en = [body_en, *payload["observations_en"]]
    texts_zh_cn = [body_zh_cn, *payload["observations_zh_cn"]]
    for position, claim in enumerate(payload["claims"]):
        required = {
            "quantitative_fact_ids",
            "explanation_type",
            "evidence_confidence",
        }
        if not required.issubset(claim):
            raise ValueError("schema-3 claims require why-first metadata")
        fact_ids = claim.get("quantitative_fact_ids")
        if not isinstance(fact_ids, list) or len(fact_ids) != len(set(fact_ids)):
            raise ValueError("schema-3 quantitative fact IDs must be unique")
        claim_candidates = set(claim.get("candidate_ids") or [])
        claim_families = set(claim.get("families") or [])
        cited = []
        for fact_id in fact_ids:
            fact = facts.get(str(fact_id))
            if fact is None:
                raise ValueError("schema-3 quantitative fact is unavailable")
            if fact.get("candidate_id") not in claim_candidates:
                raise ValueError("schema-3 quantitative candidate mismatch")
            if fact.get("family") not in claim_families:
                raise ValueError("schema-3 quantitative family mismatch")
            cited.append(fact)
        text_en = texts_en[position]
        text_zh_cn = texts_zh_cn[position]
        for fact in cited:
            if (
                str(fact["display_en"]) not in text_en
                or str(fact["display_zh_cn"]) not in text_zh_cn
            ):
                raise ValueError("schema-3 quantitative fact must be bilingual")
        if _uncited_digit(
            text_en,
            names_en.union(str(fact["display_en"]) for fact in cited),
        ) or _uncited_digit(
            text_zh_cn,
            names_zh_cn.union(
                str(fact["display_zh_cn"]) for fact in cited
            ),
        ):
            raise ValueError("schema-3 prose contains an uncited digit")


def _uncited_digit(value: str, allowed_spans: set[str]) -> bool:
    remainder = value
    for span in sorted(allowed_spans, key=len, reverse=True):
        if any(character.isdigit() for character in span):
            remainder = re.sub(
                re.escape(span),
                "",
                remainder,
                flags=re.IGNORECASE,
            )
    return any(character.isdigit() for character in remainder)


def _write_subjects(
    row: TrendNarrative,
    subjects: Sequence[Mapping[str, Any]],
) -> None:
    if row.subjects.exists():
        raise ValueError("published subjects are immutable")
    records = []
    for subject in subjects:
        identity_type = str(subject.get("identity_type") or "")
        canonical_key = str(subject.get("canonical_key_snapshot") or "")
        brand = (
            Brand.objects.filter(pk=canonical_key).first()
            if identity_type == TrendNarrativeSubject.IdentityType.BRAND
            and canonical_key
            else None
        )
        product = None
        if identity_type == TrendNarrativeSubject.IdentityType.PRODUCT:
            product_id = subject.get("product_id")
            if product_id is not None:
                product = Product.objects.filter(pk=product_id).first()
            if product is None and canonical_key:
                product = Product.objects.filter(repo_id=canonical_key).first()
        if (
            identity_type == TrendNarrativeSubject.IdentityType.BRAND
            and brand is None
        ):
            raise ValueError("known brand subjects require an existing brand")
        if (
            identity_type == TrendNarrativeSubject.IdentityType.PRODUCT
            and product is None
        ):
            raise ValueError("known product subjects require an existing product")
        records.append(
            TrendNarrativeSubject(
                trend_narrative=row,
                position=subject.get("position"),
                support_type=subject.get("support_type"),
                entity_type=subject.get("entity_type"),
                identity_type=identity_type,
                brand=brand,
                product=product,
                observed_name=str(subject.get("observed_name") or ""),
                canonical_key_snapshot=canonical_key,
                name_en_snapshot=str(subject.get("name_en_snapshot") or ""),
                name_zh_cn_snapshot=str(
                    subject.get("name_zh_cn_snapshot") or ""
                ),
                candidate_id=str(subject.get("candidate_id") or ""),
                evidence_ids=list(subject.get("evidence_ids") or []),
            )
        )
    TrendNarrativeSubject.objects.bulk_create(records)


def _resolve_evidence_subject_identities(
    subjects: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve exact unique Brand/Product names without creating catalog rows."""
    resolved: list[dict[str, Any]] = []
    for source in subjects:
        subject = dict(source)
        if (
            subject.get("support_type")
            != TrendNarrativeSubject.SupportType.EVIDENCE_ONLY
            or subject.get("identity_type")
            != TrendNarrativeSubject.IdentityType.UNRESOLVED
        ):
            resolved.append(subject)
            continue
        observed_name = str(subject.get("observed_name") or "")
        brands = list(
            Brand.objects.filter(
                Q(nickname__iexact=observed_name)
                | Q(display_name__iexact=observed_name)
                | Q(display_name_en__iexact=observed_name)
                | Q(display_name_zh_cn__iexact=observed_name)
            )
            .distinct()
            .order_by("nickname")[:2]
        )
        products = list(
            Product.objects.filter(
                Q(repo_id__iexact=observed_name)
                | Q(display_name__iexact=observed_name)
            )
            .distinct()
            .order_by("repo_id")[:2]
        )
        if len(brands) == 1 and not products:
            brand = brands[0]
            name_en = brand.display_name_en or brand.display_name or brand.nickname
            subject.update(
                identity_type=TrendNarrativeSubject.IdentityType.BRAND,
                observed_name="",
                canonical_key_snapshot=brand.nickname,
                name_en_snapshot=name_en,
                name_zh_cn_snapshot=brand.display_name_zh_cn or name_en,
            )
        elif len(products) == 1 and not brands:
            product = products[0]
            name = product.display_name or product.repo_id
            subject.update(
                identity_type=TrendNarrativeSubject.IdentityType.PRODUCT,
                product_id=product.pk,
                observed_name="",
                canonical_key_snapshot=product.repo_id,
                name_en_snapshot=name,
                name_zh_cn_snapshot=name,
            )
        resolved.append(subject)
    return resolved


def _write_legacy_subject_snapshots(
    row: TrendNarrative,
    subjects: Sequence[Mapping[str, Any]],
) -> None:
    primary = subjects[0]
    row.primary_brand = _subject_brand(primary)
    row.primary_brand_key = str(primary.get("canonical_key_snapshot") or "")[:64]
    row.primary_brand_name_en = str(primary.get("name_en_snapshot") or "")
    row.primary_brand_name_zh_hans = str(
        primary.get("name_zh_cn_snapshot") or ""
    )
    secondary = subjects[1] if len(subjects) == 2 else None
    row.secondary_brand = _subject_brand(secondary)
    row.secondary_brand_key = (
        str(secondary.get("canonical_key_snapshot") or "")[:64]
        if secondary
        else ""
    )
    row.secondary_brand_name_en = (
        str(secondary.get("name_en_snapshot") or "") if secondary else ""
    )
    row.secondary_brand_name_zh_hans = (
        str(secondary.get("name_zh_cn_snapshot") or "") if secondary else ""
    )


def _subject_brand(subject: Mapping[str, Any] | None) -> Brand | None:
    if not subject or subject.get("identity_type") != (
        TrendNarrativeSubject.IdentityType.BRAND
    ):
        return None
    key = str(subject.get("canonical_key_snapshot") or "")
    return Brand.objects.filter(pk=key).first() if key else None


def _locked_attempt(attempt_id: int) -> TrendNarrative:
    return TrendNarrative.objects.select_for_update().get(pk=attempt_id)


def _owns_generating(
    row: TrendNarrative,
    *,
    owner: str,
    fence: int,
    now,
) -> bool:
    return (
        row.status == TrendNarrative.Status.GENERATING
        and row.call_slot_consumed
        and row.claim_owner == owner
        and row.claim_fence == fence
        and row.claim_expires_at is not None
        and row.claim_expires_at > now
    )


def _owns_provider_call(
    call: TrendNarrativeProviderCall,
    *,
    owner: str,
    fence: int,
    now,
) -> bool:
    return (
        call.state == TrendNarrativeProviderCall.State.RESERVED
        and call.claim_owner == owner
        and call.claim_fence == fence
        and call.claim_expires_at is not None
        and call.claim_expires_at > now
    )


def _publication_key(row: TrendNarrative) -> tuple[int, Any]:
    return (row.publication_epoch, row.facts_as_of)


def _lock_window(window_days: int) -> None:
    if connection.vendor != "postgresql":
        raise RuntimeError("trend narrative publication requires PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [_ADVISORY_LOCK_NAMESPACE, window_days],
        )
