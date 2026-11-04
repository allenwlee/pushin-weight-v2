"""Direct shared-call accounting for Chatter; no legacy assessment mirrors."""

import re
from decimal import ROUND_CEILING, Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import Case, DecimalField, F, Q, Sum, When
from django.utils import timezone

from core.models import (
    CollectionRequest,
    EditorialCall,
    OriginalContentCall,
    OriginalContentRun,
)
from monitor.original_content import advisory_lock, digest
from monitor.trend_narrative_lifecycle import (
    claim_trend_narrative_provider_call,
    complete_trend_narrative_provider_call,
    mark_trend_narrative_provider_call_ambiguous,
    mark_trend_narrative_provider_call_sent,
    reserve_original_content_call,
)

from .chatter_history import WORKFLOW, locked_run
from .contracts import ProviderReplyError
from .persistence import BudgetHeld, completed_text_cost

QUANTUM = Decimal("0.000001")


def money(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("invalid Chatter cost")
    return result.quantize(QUANTUM, rounding=ROUND_CEILING)


def budget_scope(cfg):
    return cfg.chatter.trial.scope if cfg.chatter.trial else "chatter"


def ensure_carry(cfg):
    trial = cfg.chatter.trial
    if trial is None:
        return
    expected = {
        "external_reserved_usd": str(money(trial.carry_usd)),
        "external_calls": int(bool(trial.carry_usd)),
    }
    row, _ = OriginalContentRun.objects.get_or_create(
        workflow_key="reservation-carryforward",
        scope_key=f"budget:{trial.scope}:all",
        defaults={
            "source_cycle_id": f"budget:{trial.scope}",
            "facts_as_of": timezone.now(),
            "packet_schema_version": 1,
            "snapshot": {},
            "outcome": expected,
        },
    )
    if row.outcome != expected:
        raise BudgetHeld("trial carry-forward identity changed")


def spent(cfg):
    scope = budget_scope(cfg)
    calls = OriginalContentCall.objects.filter(budget_scope=scope)
    cost = Case(
        When(actual_usd__isnull=False, then=F("actual_usd")),
        default=F("reserved_usd"),
        output_field=DecimalField(),
    )
    total = calls.aggregate(total=Sum(cost))["total"] or Decimal(0)
    requests = CollectionRequest.objects.filter(
        scope_run__run__content_run_id__in=calls.values("run_id")
    )
    cost = Case(
        When(estimated_usd__isnull=False, then=F("estimated_usd")),
        default=F("reserved_usd"),
        output_field=DecimalField(),
    )
    total += requests.aggregate(total=Sum(cost))["total"] or Decimal(0)
    carry = (
        OriginalContentRun.objects.filter(
            workflow_key="reservation-carryforward", scope_key=f"budget:{scope}:all"
        )
        .values_list("outcome", flat=True)
        .first()
    )
    if carry:
        total += money(carry["external_reserved_usd"])
    return total


def admit(cfg, ceiling):
    ceiling = money(ceiling)
    if ceiling <= 0 or ceiling > money(cfg.chatter.max_call_usd):
        raise BudgetHeld("Chatter per-call reservation exceeded")
    advisory_lock("content-budget:" + budget_scope(cfg))
    ensure_carry(cfg)
    if cfg.chatter.trial and spent(cfg) + ceiling > money(cfg.chatter.trial.limit_usd):
        raise BudgetHeld("Chatter validation budget exhausted")
    return ceiling


def call_once(run, stage, kind, ceiling, cfg, send, *, request_metadata=None):
    if kind != "text" or not request_metadata:
        raise BudgetHeld("Chatter requires a text request identity")
    metadata = request_metadata
    owner = str(uuid4())
    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        advisory_lock("content-budget:" + budget_scope(cfg))
        advisory_lock("editorial-provider-inflight")
        prior = OriginalContentCall.objects.filter(
            run=run, stage=stage, batch_key=""
        ).first()
        if prior:
            if prior.request_hash != metadata["request_hash"]:
                raise BudgetHeld("Chatter request identity changed")
            if prior.state == "completed":
                return prior.response_payload
            raise BudgetHeld("Chatter stage already sent; reconciliation required")
        amount = admit(cfg, ceiling)
        if current.provider_calls.count() >= cfg.chatter.max_calls_per_run:
            raise BudgetHeld("Chatter per-run call budget exhausted")
        guarded = OriginalContentCall.objects.filter(
            Q(budget_scope="editorial") | Q(workflow_key__in=[WORKFLOW, "social-brief"])
        )
        now = timezone.now()
        guarded.filter(state="sent").filter(
            Q(claim_expires_at__lte=now) | Q(run__lease_until__lte=now)
        ).update(state="ambiguous", error_code="lease_expired_after_send")
        EditorialCall.objects.filter(
            state="sent", assessment__lease_until__lte=now
        ).update(state="ambiguous", error_code="lease_expired")
        if (
            guarded.filter(state="sent").exists()
            or EditorialCall.objects.filter(state="sent").exists()
        ):
            raise BudgetHeld("editorial provider already in flight")
        packet = metadata["request_packet"]
        reference = metadata.get("input_reference")
        if reference:
            packet = {
                "schema_version": 1,
                "input_reference": reference,
                "request_sha256": metadata["request_hash"],
            }
        call = reserve_original_content_call(
            run=run,
            stage=stage,
            batch_key="",
            request_identity=digest([run.pk, stage, metadata["request_hash"]]),
            request_hash=metadata["request_hash"],
            request_packet=packet,
            now=now,
            workflow_key="social-brief" if stage.startswith("writer:") else WORKFLOW,
            workflow_version=metadata["workflow_version"],
            budget_scope=budget_scope(cfg),
            reserved_usd=amount,
            provider=metadata["provider"],
            model=metadata["model"],
        )
        if call is None:
            raise BudgetHeld("Chatter reservation conflict")
        claimed = claim_trend_narrative_provider_call(
            call.pk, owner=owner, now=now, lease_seconds=330
        )
        if claimed is None or not mark_trend_narrative_provider_call_sent(
            call.pk,
            owner=owner,
            fence=claimed.claim_fence,
            now=now,
        ):
            raise BudgetHeld("Chatter claim conflict")
    try:
        reply = send()
    except Exception as exc:
        code = exc.code if isinstance(exc, ProviderReplyError) else type(exc).__name__
        if not re.fullmatch(r"[a-zA-Z0-9_:-]{1,64}", code):
            code = "provider_failure"
        mark_trend_narrative_provider_call_ambiguous(
            call.pk,
            owner=owner,
            fence=claimed.claim_fence,
            error_code=code,
            now=timezone.now(),
        )
        raise
    actual = completed_text_cost(reply, metadata)
    with transaction.atomic():
        advisory_lock("content-budget:" + budget_scope(cfg))
        # Report the full observed cost, including an unexpected overage.
        OriginalContentCall.objects.filter(pk=call.pk).update(actual_usd=actual)
        completed = complete_trend_narrative_provider_call(
            call.pk,
            owner=owner,
            fence=claimed.claim_fence,
            response_hash=digest(reply),
            response_payload=reply,
            now=timezone.now(),
        )
    if not completed:
        raise BudgetHeld("Chatter completion lost its claim")
    return reply
