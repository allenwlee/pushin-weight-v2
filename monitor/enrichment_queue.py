"""Durable enrichment ownership, due times and actual-attempt accounting.

The collection cycle and continuous worker share these rules. Waiting in this
queue never consumes an attempt or makes a post expire.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import PostEnrichmentState

STAGES = ("translation", "classification")


def stage_due_q(stage: str, now: datetime) -> Q:
    if stage not in STAGES:
        raise ValueError(f"unknown enrichment stage: {stage}")
    return Q(**{f"{stage}_status": "pending"}) & (
        Q(**{f"{stage}_next_attempt_at__isnull": True})
        | Q(**{f"{stage}_next_attempt_at__lte": now})
    )


def stage_is_due(state: PostEnrichmentState, stage: str, now: datetime) -> bool:
    retry_at = getattr(state, f"{stage}_next_attempt_at")
    return getattr(state, f"{stage}_status") == "pending" and (
        state.source_collection_job_id is not None
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
) -> EnrichmentClaimBatch:
    now = now or timezone.now()
    available = Q(source_collection_job_id=source_collection_job_id) & (
        Q(claim_expires_at__isnull=True) | Q(claim_expires_at__lte=now)
    )
    if post_ids is not None:
        available &= Q(post_id__in=post_ids)
    due = stage_due_q("translation", now) | stage_due_q("classification", now)
    if source_collection_job_id is not None:
        # Historical jobs own request/replay timing in their collection budget.
        # Reusing a saved paid reply must not wait for the scheduled retry lane.
        due = Q(translation_status="pending") | Q(classification_status="pending")
    quarantined = 0
    with transaction.atomic():
        # A crashed final attempt still terminates on the next claim. Retain
        # its diagnostic cause; never substitute queue age for that cause.
        if source_collection_job_id is None:
            exhausted = (
                PostEnrichmentState.objects.select_for_update(skip_locked=True)
                .filter(
                    available,
                    Q(
                        translation_status="pending",
                        translation_attempts__gte=cfg.max_attempts,
                    )
                    | Q(
                        classification_status="pending",
                        classification_attempts__gte=cfg.max_attempts,
                    ),
                )
                .order_by("post_id")
            )
            for state in exhausted:
                for stage in STAGES:
                    if (
                        getattr(state, f"{stage}_status") == "pending"
                        and getattr(state, f"{stage}_attempts") >= cfg.max_attempts
                    ):
                        setattr(state, f"{stage}_status", "failed")
                        setattr(state, f"{stage}_next_attempt_at", None)
                        if not getattr(state, f"{stage}_error_code"):
                            setattr(state, f"{stage}_error_code", "attempts_exhausted")
                if all(getattr(state, f"{s}_status") != "pending" for s in STAGES):
                    quarantined += 1
                state.save()

        eligible = (
            PostEnrichmentState.objects.select_for_update(skip_locked=True)
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
            current = list(
                eligible.filter(created_at__gte=cutoff)[: cfg.fresh_batch_size]
            )
            carryover = list(
                eligible.filter(created_at__lt=cutoff)[
                    : cfg.batch_size - cfg.fresh_batch_size
                ]
            )
            remainder = cfg.batch_size - len(current) - len(carryover)
            if remainder:
                selected = [s.pk for s in current + carryover]
                for state in eligible.exclude(pk__in=selected)[:remainder]:
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
                    state.source_collection_job_id is None
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
                    if state.source_collection_job_id is not None or post_id in (
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
