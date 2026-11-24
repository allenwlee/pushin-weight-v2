"""Durable enrichment ownership, due times and actual-attempt accounting.

The collection cycle and continuous worker share these rules. Waiting in this
queue never consumes an attempt or makes a post expire.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.contrib.postgres.fields import ArrayField
from django.db import transaction
from django.db.models import CharField, Exists, F, Func, OuterRef, Q
from django.utils import timezone

from core.models import (
    OriginalContentCall,
    PostBrand,
    PostEnrichmentState,
    TargetedExtractionState,
)

STAGES = ("translation", "classification")
HISTORICAL_SCRIPT_DEMAND = "requested_historical_script_detection"


def targeted_release_due_q(now):
    return Q(status="pending", updated_at__lte=now - timedelta(minutes=1)) | Q(
        status="failed", updated_at__lte=now - timedelta(minutes=5)
    )


def _outstanding_historical_translations(states) -> set[str]:
    """Find paid historical translations that have not finished importing."""
    calls = OriginalContentCall.objects.filter(
        provider_batch__isnull=False, stage="translation", import_state="pending",
        state__in=("reserved", "sent", "ambiguous", "completed"),
    )
    historical = {str(s.pk): s for s in states if s.source_collection_job_id}
    if not historical:
        return set()
    calls = calls.filter(member_post_ids__overlap=list(historical))
    return {post_id for status, members in calls.values_list("state", "member_post_ids")
            for post_id in members if post_id in historical and
            (status != "completed" or historical[post_id].translation_error_code != HISTORICAL_SCRIPT_DEMAND)}


def request_post_translation(post_id: str) -> PostEnrichmentState:
    """Coalesce an explicit request into the existing shared post queue."""
    from core.models import Post
    from monitor.post_artifacts import literal_translation_artifact_complete

    with transaction.atomic():
        PostEnrichmentState.objects.get_or_create(post_id=post_id)
        state = PostEnrichmentState.objects.select_for_update().get(pk=post_id)
        # Publishers lock the state before the post; keep the same ordering.
        post = Post.objects.select_for_update().get(pk=post_id)
        if literal_translation_artifact_complete(post):
            return state
        first_request = not state.translation_requested
        state.translation_requested = True
        if first_request or state.translation_status != PostEnrichmentState.Status.PENDING:
            state.translation_status = PostEnrichmentState.Status.PENDING
            state.translation_next_attempt_at = None
            state.translation_attempts = 0
            state.translation_first_attempt_at = None
            state.translation_last_attempt_at = None
            state.translation_error_code = ""
        state.save(update_fields=[
            "translation_requested", "translation_status", "translation_next_attempt_at",
            "translation_attempts", "translation_first_attempt_at", "translation_last_attempt_at",
            "translation_error_code", "updated_at",
        ])
        return state


def stage_due_q(stage: str, now: datetime) -> Q:
    if stage not in STAGES:
        raise ValueError(f"unknown enrichment stage: {stage}")
    requested = Q(translation_requested=True) if stage == "translation" else Q()
    return requested & Q(**{f"{stage}_status": "pending"}) & (
        Q(**{f"{stage}_next_attempt_at__isnull": True})
        | Q(**{f"{stage}_next_attempt_at__lte": now})
    )


def scheduled_due_q(now: datetime) -> Q:
    """Runnable scheduled work, including discovery-sentinel PostBrand rows."""
    has_classification_target = Exists(PostBrand.objects.filter(post_id=OuterRef("post_id")))
    return stage_due_q("translation", now) | (
        stage_due_q("classification", now) & Q(has_classification_target)
    )


def classification_batch_wait_until(
    tweets: list[dict[str, Any]], states: list[PostEnrichmentState], now: datetime,
) -> datetime | None:
    """Give an otherwise idle worker a bounded window to combine a small batch."""
    from x_monitor.attribution import MAX_FIXED_DECISION_SLOTS

    if not 1 <= len(tweets) <= 5:
        return None
    if sum(len(tweet["brand_ids"]) for tweet in tweets) >= MAX_FIXED_DECISION_SLOTS:
        return None
    ids = {tweet["tweet_id"] for tweet in tweets}
    oldest_ready = min(
        state.classification_next_attempt_at or state.created_at for state in states if state.pk in ids
    )
    due = oldest_ready + timedelta(seconds=60)
    return due if now < due else None


def stage_is_due(state: PostEnrichmentState, stage: str, now: datetime) -> bool:
    if stage == "translation" and not state.translation_requested:
        return False
    retry_at = getattr(state, f"{stage}_next_attempt_at")
    return getattr(state, f"{stage}_status") == "pending" and (
        (state.source_collection_job_id is not None and stage == "classification")
        or retry_at is None
        or retry_at <= now
    )


@dataclass(frozen=True)
class EnrichmentClaimBatch:
    current_cycle_states: tuple[PostEnrichmentState, ...] = ()
    carryover_states: tuple[PostEnrichmentState, ...] = ()
    quarantined: int = 0

    @property
    def states(self) -> tuple[PostEnrichmentState, ...]:
        return self.current_cycle_states + self.carryover_states

    @property
    def current_cycle_post_ids(self) -> tuple[str, ...]:
        return tuple(str(state.pk) for state in self.current_cycle_states)

    @property
    def carryover_post_ids(self) -> tuple[str, ...]:
        return tuple(str(state.pk) for state in self.carryover_states)


def _first_attempt_share(ordered, limit: int, now: datetime) -> list[PostEnrichmentState]:
    """Reserve most slots for first classifications, keeping other due work moving."""
    if limit <= 0:
        return []
    first_due = (
        Q(classification_attempts=0, source_collection_job_id__isnull=True)
        & stage_due_q("classification", now)
        & Q(Exists(PostBrand.objects.filter(post_id=OuterRef("post_id"))))
    )
    # Production allocations reserve 80% for first attempts and 20% for
    # retries/translation. Small allocations retain at least one other slot.
    other_limit = max(1, limit // 5) if limit > 1 else 0
    first = list(ordered.filter(first_due)[: limit - other_limit])
    other_due = ordered.exclude(first_due)
    other = list(other_due[:other_limit])
    if other_limit >= 2 and (len(first) == limit - other_limit or len(other) == other_limit) and not any(
        stage_is_due(state, "translation", now) for state in first + other
    ):
        requested = ordered.filter(stage_due_q("translation", now)).annotate(first_due=first_due).first()
        if requested is not None:
            lane = first if requested.first_due else other
            if lane:
                lane[-1] = requested
    selected = first + other
    remaining = limit - len(selected)
    if remaining:
        selected += list(ordered.exclude(pk__in=[s.pk for s in selected])[:remaining])
    return selected


def claim_enrichment_states(
    *,
    cfg: Any,
    run_id: str,
    now: datetime | None = None,
    prefer_created_before: datetime | None = None,
    post_ids: set[str] | None = None,
    defer_translation_attempts: bool = False,
    source_collection_job_id: Any | None = None,
    fair_queue: bool = False,
    include_targeted_release: bool = False,
) -> EnrichmentClaimBatch:
    now = now or timezone.now()
    available = (
        Q(claim_expires_at__isnull=True) | Q(claim_expires_at__lte=now)
    )
    if source_collection_job_id is None:
        # A reader can request a translation even when a historical job owns
        # classification. Never claim that job's classification here.
        available &= Q(source_collection_job_id__isnull=True) | stage_due_q("translation", now)
    else:
        available &= Q(source_collection_job_id=source_collection_job_id)
    if post_ids is not None:
        available &= Q(post_id__in=post_ids)
    if source_collection_job_id is not None:
        # Historical jobs own request/replay timing in their collection budget.
        # Reusing a saved paid reply must not wait for the scheduled retry lane.
        due = (Q(translation_requested=True, translation_status="pending")
               | Q(classification_status="pending"))
    else:
        due = scheduled_due_q(now)
        if include_targeted_release:
            release_due = TargetedExtractionState.objects.filter(
                post_id=OuterRef("post_id"), role="model_release_extraction",
                prompt_version="model-release-extraction-v2", attempts__lt=cfg.max_attempts,
            ).filter(targeted_release_due_q(now))
            due |= Q(Exists(release_due), classification_status="succeeded", source_collection_job_id__isnull=True)
    quarantined = 0
    with transaction.atomic():
        # Historical batches retain their paid reply after a worker lease
        # expires. Exclude those posts from the ordinary queue before slicing,
        # otherwise a full page of pending batches could starve live work.
        if source_collection_job_id is None and PostEnrichmentState.objects.filter(
            available, source_collection_job_id__isnull=False,
        ).exists():
            outstanding = OriginalContentCall.objects.filter(
                provider_batch__isnull=False, stage="translation", import_state="pending",
                state__in=("reserved", "sent", "ambiguous", "completed"),
                member_post_ids__contains=Func(
                    OuterRef("post_id"), template="ARRAY[%(expressions)s]",
                    output_field=ArrayField(CharField(max_length=128)),
                ),
            )
            blocked = Exists(outstanding.exclude(state="completed")) | (
                ~Q(translation_error_code=HISTORICAL_SCRIPT_DEMAND) & Q(Exists(outstanding))
            )
            available &= ~(Q(source_collection_job_id__isnull=False) & blocked)
        # A crashed final attempt still terminates on the next claim. Retain
        # its diagnostic cause; never substitute queue age for that cause.
        if source_collection_job_id is None:
            exhausted = (
                PostEnrichmentState.objects.select_for_update(skip_locked=True)
                .filter(
                    available,
                    Q(
                        translation_status="pending", translation_requested=True,
                        translation_attempts__gte=cfg.max_attempts,
                    )
                    | Q(
                        source_collection_job_id__isnull=True, classification_status="pending",
                        classification_attempts__gte=cfg.max_attempts,
                    ),
                )
                .order_by("post_id")
            )
            exhausted = list(exhausted)
            blocked = _outstanding_historical_translations(exhausted)
            for state in exhausted:
                if str(state.pk) in blocked and state.source_collection_job_id:
                    continue
                for stage in STAGES:
                    if (
                        getattr(state, f"{stage}_status") == "pending"
                        and getattr(state, f"{stage}_attempts") >= cfg.max_attempts
                        and (stage != "translation" or state.translation_requested)
                        and (stage != "classification" or state.source_collection_job_id is None)
                    ):
                        setattr(state, f"{stage}_status", "failed")
                        setattr(state, f"{stage}_next_attempt_at", None)
                        if not getattr(state, f"{stage}_error_code"):
                            setattr(state, f"{stage}_error_code", "attempts_exhausted")
                if all(getattr(state, f"{s}_status") != "pending" for s in STAGES):
                    quarantined += 1
                state.save()

        # Lease only the queue entry. Locking the joined post also blocks
        # foreign-key checks when a reader requests commentary for it.
        eligible = (
            PostEnrichmentState.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("post")
            .filter(
                available,
                due,
            )
            .order_by("created_at", "post_id")
        )
        current, carryover = [], []
        if source_collection_job_id is not None:
            carryover = list(
                eligible.order_by("post_id")[
                    : min(cfg.claim_per_cycle, cfg.carryover_claim_per_cycle)
                ]
            )
        elif fair_queue:
            cutoff = now - timedelta(minutes=cfg.fresh_minutes)
            fresh = eligible.filter(created_at__gte=cutoff)
            newest_count = (cfg.fresh_batch_size + 1) // 2
            newest = _first_attempt_share(
                fresh.order_by(F("post__created_at").desc(nulls_last=True), "-post_id"),
                newest_count, now,
            )
            oldest = _first_attempt_share(
                fresh.exclude(pk__in=[state.pk for state in newest]),
                cfg.fresh_batch_size - len(newest), now,
            )
            current = newest + oldest
            carryover = _first_attempt_share(
                eligible.filter(created_at__lt=cutoff),
                cfg.batch_size - cfg.fresh_batch_size, now,
            )
            remainder = cfg.batch_size - len(current) - len(carryover)
            if remainder:
                selected = [s.pk for s in current + carryover]
                for state in _first_attempt_share(eligible.exclude(pk__in=selected), remainder, now):
                    (current if state.created_at >= cutoff else carryover).append(state)
        elif prefer_created_before is None:
            carryover = list(
                eligible[: min(cfg.claim_per_cycle, cfg.carryover_claim_per_cycle)]
            )
        else:
            # Retain collection's current/carryover reporting contract. Only
            # the independent worker uses the fresh/backlog allocation.
            carryover = list(
                eligible.filter(created_at__lt=prefer_created_before)[
                    : cfg.carryover_claim_per_cycle
                ]
            )
            current = list(
                eligible.filter(created_at__gte=prefer_created_before)[
                    : min(
                        cfg.current_cycle_claim_per_cycle,
                        cfg.claim_per_cycle - len(carryover),
                    )
                ]
            )
        # Recheck after locking the selected state rows. A reservation that
        # committed after the initial query must win before we issue a claim.
        if source_collection_job_id is None:
            blocked = _outstanding_historical_translations(current + carryover)
            current = [s for s in current if not (s.source_collection_job_id and str(s.pk) in blocked)]
            carryover = [s for s in carryover if not (s.source_collection_job_id and str(s.pk) in blocked)]
        for state in current + carryover:
            state.claim_owner = f"enrichment:{run_id}"[:128]
            state.claim_run_id = str(run_id)[:128]
            state.claimed_at = now
            state.claim_expires_at = now + timedelta(seconds=cfg.claim_ttl_seconds)
            state.save(
                update_fields=[
                    "claim_owner",
                    "claim_run_id",
                    "claimed_at",
                    "claim_expires_at",
                    "updated_at",
                ]
            )
    return EnrichmentClaimBatch(tuple(current), tuple(carryover), quarantined)


def release_enrichment_claim(post_id: str, *, run_id: str) -> bool:
    return bool(
        PostEnrichmentState.objects.filter(
            post_id=post_id, claim_run_id=str(run_id)[:128]
        ).update(
            claim_owner="",
            claim_run_id="",
            claimed_at=None,
            claim_expires_at=None,
        )
    )


def mark_stage_started(
    *, post_ids: list[str], run_id: str, stage: str, now: datetime | None = None
) -> None:
    """Checkpoint once per claimed stage, immediately before physical dispatch.

    Call inside the dispatch reservation transaction when a budget applies.
    A classifier's two roles and its transport retries share one attempt.
    """
    if stage not in STAGES or not post_ids:
        raise ValueError("enrichment_request_identity_missing")
    now = now or timezone.now()
    with transaction.atomic():
        states = list(
            PostEnrichmentState.objects.select_for_update()
            .filter(
                post_id__in=set(post_ids),
                claim_run_id=str(run_id)[:128],
                claim_expires_at__gt=now,
            )
            .order_by("post_id")
        )
        if len(states) != len(set(post_ids)) or any(
            not stage_is_due(s, stage, now) for s in states
        ):
            from x_monitor.attribution import LLMCallBudgetExhausted

            raise LLMCallBudgetExhausted("enrichment_claim_lost")
        for state in states:
            last = getattr(state, f"{stage}_last_attempt_at")
            if last is not None and last >= state.claimed_at:
                continue
            setattr(state, f"{stage}_attempts", getattr(state, f"{stage}_attempts") + 1)
            if getattr(state, f"{stage}_first_attempt_at") is None:
                setattr(state, f"{stage}_first_attempt_at", now)
            setattr(state, f"{stage}_last_attempt_at", now)
            state.save(
                update_fields=[
                    f"{stage}_attempts",
                    f"{stage}_first_attempt_at",
                    f"{stage}_last_attempt_at",
                    "updated_at",
                ]
            )


def finish_enrichment_stage(
    *,
    post_ids: list[str],
    run_id: str,
    stage: str,
    succeeded_ids: set[str],
    error_code: str,
    cfg: Any,
    now: datetime | None = None,
    called_ids: set[str] | None = None,
    progressed_ids: set[str] | None = None,
    error_codes: dict[str, str] | None = None,
    diagnostics: dict[str, dict[str, str]] | None = None,
    attempts_recorded: bool = False,
) -> int:
    if stage not in STAGES:
        raise ValueError(f"unknown enrichment stage: {stage}")
    now = now or timezone.now()
    failed = 0
    with transaction.atomic():
        states = (
            PostEnrichmentState.objects.select_for_update()
            .filter(
                post_id__in=post_ids,
                claim_run_id=str(run_id)[:128],
                claim_expires_at__gt=now,
            )
            .order_by("post_id")
        )
        for state in states:
            if getattr(state, f"{stage}_status") != "pending":
                continue
            post_id = str(state.post_id)
            called = post_id in (called_ids or set())
            fields = [
                f"{stage}_status",
                f"{stage}_next_attempt_at",
                f"{stage}_error_code",
                "updated_at",
            ]
            if stage == "translation" and called_ids is not None:
                state.translation_diagnostics = (diagnostics or {}).get(post_id, {})
                fields.append("translation_diagnostics")
                if called and not attempts_recorded:
                    state.translation_last_attempt_at = now
                    state.translation_first_attempt_at = (
                        state.translation_first_attempt_at or now
                    )
                    if post_id not in (progressed_ids or set()):
                        state.translation_attempts += 1
                    fields.extend(
                        [
                            "translation_attempts",
                            "translation_first_attempt_at",
                            "translation_last_attempt_at",
                        ]
                    )
                elif called and post_id in (progressed_ids or set()):
                    # Successful long-post chunks are progress, not failures.
                    state.translation_attempts = max(0, state.translation_attempts - 1)
                    fields.append("translation_attempts")
            if post_id in succeeded_ids:
                setattr(state, f"{stage}_status", "succeeded")
                setattr(state, f"{stage}_next_attempt_at", None)
                setattr(state, f"{stage}_error_code", "")
            else:
                attempts = getattr(state, f"{stage}_attempts")
                exhausted = (
                    (state.source_collection_job_id is None or stage == "translation")
                    and attempts >= cfg.max_attempts
                )
                setattr(
                    state,
                    f"{stage}_error_code",
                    str((error_codes or {}).get(post_id, error_code) or "stage_failed")[
                        :128
                    ],
                )
                if exhausted:
                    setattr(state, f"{stage}_status", "failed")
                    setattr(state, f"{stage}_next_attempt_at", None)
                    failed += 1
                else:
                    # No-call deferrals also wait briefly: a missing credential
                    # or exhausted allowance must not create a hot polling loop.
                    minutes = (
                        min(360, 5 * 2 ** min(max(attempts - 1, 0), 7)) if called else 1
                    )
                    if (stage != "translation" and state.source_collection_job_id is not None) or post_id in (
                        progressed_ids or set()
                    ):
                        minutes = 0
                    setattr(
                        state,
                        f"{stage}_next_attempt_at",
                        now + timedelta(minutes=minutes),
                    )
            state.save(update_fields=fields)
    return failed
