"""Durable demand, leasing, and fenced publication for rich post synthesis."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import (
    Post,
    PostSynthesisArtifact,
    PostSynthesisDailyBudget,
    PostSynthesisDemand,
    PostSynthesisRateLimitBucket,
)
from monitor.post_artifacts import (
    publish_post_synthesis,
    record_post_synthesis_failure,
    synthesis_context_fingerprint,
)

REASON_PRIORITY = {
    PostSynthesisDemand.Reason.PREWARM: 10,
    PostSynthesisDemand.Reason.LOOKAHEAD: 20,
    PostSynthesisDemand.Reason.VISIBLE: 50,
    PostSynthesisDemand.Reason.EXPANDED: 80,
    PostSynthesisDemand.Reason.OPERATOR: 100,
}


def post_context(post: Post) -> tuple[dict[str, str], str, list[dict[str, str]]]:
    parent_text = ""
    if post.in_reply_to_id:
        parent_text = str(
            Post.objects.filter(pk=post.in_reply_to_id)
            .values_list("text", flat=True)
            .first()
            or ""
        )
    context = {
        "source": post.text or "",
        "stored_quote": post.quoted_text or "",
        "local_parent": parent_text,
    }
    provenance = []
    if context["source"]:
        provenance.append({"kind": "source", "post_id": str(post.pk)})
    if context["stored_quote"]:
        provenance.append(
            {
                "kind": "stored_quote",
                "post_id": str(post.quoted_status_id_id or "external"),
            }
        )
    if context["local_parent"]:
        provenance.append(
            {"kind": "local_parent", "post_id": str(post.in_reply_to_id)}
        )
    return context, synthesis_context_fingerprint(post, parent_text=parent_text), provenance


def request_post_synthesis(
    *, post_ids: list[str], reason: str, config, now=None
) -> list[PostSynthesisDemand]:
    """Create or upgrade bounded shared demand rows for existing posts."""
    if reason not in PostSynthesisDemand.Reason.values:
        raise ValueError("unsupported synthesis demand reason")
    unique_ids = list(dict.fromkeys(str(post_id) for post_id in post_ids if post_id))
    if len(unique_ids) > config.demand_batch_limit:
        raise ValueError("synthesis demand batch limit exceeded")
    requested_at = now or timezone.now()
    posts = {str(post.pk): post for post in Post.objects.filter(pk__in=unique_ids)}
    rows = []
    for post_id in unique_ids:
        post = posts.get(post_id)
        if post is None:
            continue
        _context, fingerprint, _provenance = post_context(post)
        rows.append(
            _upsert_demand(
                post=post,
                fingerprint=fingerprint,
                reason=reason,
                config=config,
                now=requested_at,
            )
        )
    return rows


def _upsert_demand(*, post: Post, fingerprint: str, reason: str, config, now):
    identity = {
        "post": post,
        "input_context_fingerprint": fingerprint,
        "prompt_version": config.prompt_version,
        "model": config.model,
        "output_schema_version": config.output_schema_version,
    }
    priority = REASON_PRIORITY[reason]
    expiry_minutes = (
        config.lookahead_expiry_minutes
        if reason in {"lookahead", "prewarm"}
        else config.visible_expiry_minutes
    )
    expires_at = None if reason == "operator" else now + timedelta(minutes=expiry_minutes)
    artifact = PostSynthesisArtifact.objects.filter(
        post=post,
        input_context_fingerprint=fingerprint,
        prompt_version=config.prompt_version,
        model=config.model,
        output_schema_version=config.output_schema_version,
        state=PostSynthesisArtifact.State.SUCCEEDED,
    ).first()
    for attempt in range(2):
        try:
            with transaction.atomic():
                demand = (
                    PostSynthesisDemand.objects.select_for_update()
                    .filter(**identity)
                    .first()
                )
                if demand is None:
                    return PostSynthesisDemand.objects.create(
                        **identity,
                        reason=reason,
                        priority=priority,
                        first_requested_at=now,
                        last_requested_at=now,
                        not_before=now,
                        expires_at=expires_at,
                        state=(
                            PostSynthesisDemand.State.SUCCEEDED
                            if artifact is not None
                            else PostSynthesisDemand.State.PENDING
                        ),
                        artifact=artifact,
                    )
                demand.request_count += 1
                demand.last_requested_at = now
                if priority >= demand.priority:
                    demand.priority = priority
                    demand.reason = reason
                if expires_at is None:
                    demand.expires_at = None
                elif demand.expires_at is not None:
                    demand.expires_at = max(demand.expires_at, expires_at)
                if artifact is not None:
                    demand.state = PostSynthesisDemand.State.SUCCEEDED
                    demand.artifact = artifact
                    demand.last_error = ""
                elif demand.state == PostSynthesisDemand.State.CANCELLED:
                    demand.state = PostSynthesisDemand.State.PENDING
                    demand.not_before = now
                demand.save()
                return demand
        except IntegrityError:
            if attempt:
                raise
    raise RuntimeError("synthesis demand upsert failed")


def claim_synthesis_demands(*, config, owner: str | None = None, now=None):
    """Claim disjoint due rows with short SKIP LOCKED transactions."""
    current = now or timezone.now()
    PostSynthesisRateLimitBucket.objects.filter(
        bucket_start__lt=current - timedelta(days=2)
    ).delete()
    claim_owner = (owner or f"synthesis:{uuid4()}")[:128]
    with transaction.atomic():
        PostSynthesisDemand.objects.filter(
            state=PostSynthesisDemand.State.PENDING,
            expires_at__isnull=False,
            expires_at__lte=current,
        ).update(state=PostSynthesisDemand.State.CANCELLED, last_error="expired")
        due = (
            PostSynthesisDemand.objects.select_for_update(skip_locked=True)
            .filter(
                Q(state=PostSynthesisDemand.State.PENDING)
                | Q(
                    state=PostSynthesisDemand.State.PROCESSING,
                    lease_expires_at__lte=current,
                ),
                not_before__lte=current,
                attempts__lt=config.max_attempts,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=current))
            .select_related("post")
        )
        budget, _created = PostSynthesisDailyBudget.objects.get_or_create(
            usage_date=current.date(),
            control_revision=config.control_revision,
            provider=config.provider,
            model=config.model,
        )
        budget = PostSynthesisDailyBudget.objects.select_for_update().get(pk=budget.pk)
        capacity = min(
            config.batch_size,
            max(0, config.daily_request_cap - budget.reserved_requests),
            max(
                0,
                (
                    config.daily_input_token_cap - budget.reserved_input_tokens
                )
                // config.max_input_tokens_per_post,
            ),
            max(
                0,
                (
                    config.daily_output_token_cap - budget.reserved_output_tokens
                )
                // config.max_output_tokens_per_post,
            ),
        )
        claimed = list(due.order_by("-priority", "first_requested_at", "pk")[:capacity])
        for demand in claimed:
            demand.state = PostSynthesisDemand.State.PROCESSING
            demand.lease_owner = claim_owner
            demand.lease_fence += 1
            demand.lease_expires_at = current + timedelta(seconds=config.lease_seconds)
            demand.attempts += 1
            demand.budget = budget
            demand.save()
        if claimed:
            budget.reserved_requests += len(claimed)
            budget.reserved_input_tokens += (
                len(claimed) * config.max_input_tokens_per_post
            )
            budget.reserved_output_tokens += (
                len(claimed) * config.max_output_tokens_per_post
            )
            budget.save()
        return claimed


def publish_claimed_synthesis(
    *, demand_id: int, owner: str, fence: int, response, config, now=None
) -> PostSynthesisArtifact | None:
    current = now or timezone.now()
    with transaction.atomic():
        demand = (
            PostSynthesisDemand.objects.select_for_update()
            .select_related("post")
            .get(pk=demand_id)
        )
        if not _owns(demand, owner=owner, fence=fence, now=current):
            return None
        _context, current_fingerprint, provenance = post_context(demand.post)
        if current_fingerprint != demand.input_context_fingerprint:
            _cancel_locked(demand, "context_obsolete")
            return None
        artifact = publish_post_synthesis(
            post=demand.post,
            values=response.texts,
            context_fingerprint=current_fingerprint,
            prompt_version=demand.prompt_version,
            model=demand.model,
            output_schema_version=demand.output_schema_version,
            evidence_provenance=provenance,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            attempts=demand.attempts,
            now=current,
        )
        if artifact is None:
            return _fail_locked(demand, "synthesis_validation_failed", config, current)
        if demand.budget_id:
            budget = PostSynthesisDailyBudget.objects.select_for_update().get(
                pk=demand.budget_id
            )
            budget.observed_input_tokens += max(0, int(response.input_tokens or 0))
            budget.observed_output_tokens += max(0, int(response.output_tokens or 0))
            budget.save()
        demand.state = PostSynthesisDemand.State.SUCCEEDED
        demand.artifact = artifact
        demand.lease_owner = ""
        demand.lease_expires_at = None
        demand.last_error = ""
        demand.save()
        return artifact


def fail_synthesis_claim(
    *, demand_id: int, owner: str, fence: int, error_code: str, config, now=None
) -> bool:
    current = now or timezone.now()
    with transaction.atomic():
        demand = PostSynthesisDemand.objects.select_for_update().get(pk=demand_id)
        if not _owns(demand, owner=owner, fence=fence, now=current):
            return False
        _fail_locked(demand, error_code, config, current)
        return True


def _fail_locked(demand, error_code: str, config, now):
    record_post_synthesis_failure(
        post=demand.post,
        context_fingerprint=demand.input_context_fingerprint,
        prompt_version=demand.prompt_version,
        model=demand.model,
        output_schema_version=demand.output_schema_version,
        error_code=error_code,
        attempts=demand.attempts,
        now=now,
    )
    exhausted = demand.attempts >= config.max_attempts
    demand.state = (
        PostSynthesisDemand.State.FAILED
        if exhausted
        else PostSynthesisDemand.State.PENDING
    )
    demand.not_before = now + timedelta(seconds=min(300, 2 ** demand.attempts))
    demand.lease_owner = ""
    demand.lease_expires_at = None
    demand.last_error = str(error_code or "synthesis_failed")[:128]
    demand.save()


def _cancel_locked(demand, error_code: str) -> None:
    demand.state = PostSynthesisDemand.State.CANCELLED
    demand.lease_owner = ""
    demand.lease_expires_at = None
    demand.last_error = error_code[:128]
    demand.save()


def _owns(demand, *, owner: str, fence: int, now) -> bool:
    return bool(
        demand.state == PostSynthesisDemand.State.PROCESSING
        and demand.lease_owner == owner
        and demand.lease_fence == fence
        and demand.lease_expires_at
        and demand.lease_expires_at >= now
    )


def process_synthesis_batch(*, config, client, owner: str | None = None, now=None):
    """Perform provider work outside database locks, then publish by fence."""
    from x_monitor.synthesis import synthesize_post

    if not config.provider_calls_active:
        return {
            "status": "provider_disabled",
            "claimed": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
        }
    current = now or timezone.now()
    claimed = claim_synthesis_demands(config=config, owner=owner, now=current)
    succeeded = 0
    failed = 0
    cancelled = 0
    for demand in claimed:
        context, fingerprint, _provenance = post_context(demand.post)
        if fingerprint != demand.input_context_fingerprint:
            cancel_synthesis_claim(
                demand_id=demand.pk,
                owner=demand.lease_owner,
                fence=demand.lease_fence,
                error_code="context_obsolete",
                now=current,
            )
            cancelled += 1
            continue
        try:
            response = synthesize_post(
                post_id=str(demand.post_id),
                context=context,
                client=client,
                config=config,
                telemetry_context={"stage": "post_synthesis", "call_id": demand.pk},
            )
            artifact = publish_claimed_synthesis(
                demand_id=demand.pk,
                owner=demand.lease_owner,
                fence=demand.lease_fence,
                response=response,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary maps to safe state
            fail_synthesis_claim(
                demand_id=demand.pk,
                owner=demand.lease_owner,
                fence=demand.lease_fence,
                error_code=type(exc).__name__,
                config=config,
            )
            artifact = None
        if artifact is None:
            failed += 1
        else:
            succeeded += 1
    return {
        "status": "processed",
        "claimed": len(claimed),
        "succeeded": succeeded,
        "failed": failed,
        "cancelled": cancelled,
    }


def cancel_synthesis_claim(
    *, demand_id: int, owner: str, fence: int, error_code: str, now=None
) -> bool:
    current = now or timezone.now()
    with transaction.atomic():
        demand = PostSynthesisDemand.objects.select_for_update().get(pk=demand_id)
        if not _owns(demand, owner=owner, fence=fence, now=current):
            return False
        _cancel_locked(demand, error_code)
        return True
