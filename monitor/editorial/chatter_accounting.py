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
from .persistence import _GRAPHICS_PREFIX, BudgetHeld, completed_text_cost

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
    frozen_scope = Q(config_snapshot__editorial__chatter__trial__scope=scope)
    if scope == "chatter":
        frozen_scope = Q(config_snapshot__editorial__chatter__trial=None)
    owners = OriginalContentRun.objects.filter(
        Q(pk__in=calls.values("run_id")) | (Q(workflow_key=WORKFLOW) & frozen_scope)
    )
    requests = CollectionRequest.objects.filter(scope_run__run__content_run__in=owners)
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


def linked_graphics_runs(run):
    """Read only source-verified producing runs; caller JSON grants no link."""
    from .graphics_chatter import source_for_run

    linked = []
    for package in OriginalContentRun.objects.filter(
        workflow_key="graphics-package", snapshot__request__run_id=run.pk,
    ).order_by("pk"):
        source = source_for_run(package)
        if source is None or source.run_id != run.pk:
            raise ValueError("Graphics package does not belong to this Chatter run")
        linked.append(package)
    return linked


def _model_category(call, source_run_id):
    if call.run_id != source_run_id:
        return "graphics"
    if re.fullmatch(r"selector:[0-9]+", call.stage):
        return "selector"
    if re.fullmatch(r"writer:[1-9][0-9]*:[a-zA-Z-]+", call.stage):
        return "writer"
    return {"trends-ranking-v1": "ranker", "discovery": "discovery",
            "advisory": "review", "review": "review"}.get(call.stage, "other_model")


def chatter_call_report(run_id):
    """Report linked physical requests once, without treating estimates as bills."""
    from .chatter_trends import OFFICIAL_ENDPOINT, _saved_observation, checkpoint
    from .graphics_generation import reported_cost_usd

    run = OriginalContentRun.objects.get(pk=run_id, workflow_key=WORKFLOW)
    packages = linked_graphics_runs(run)
    owners = [run.pk, *(package.pk for package in packages)]
    counts = dict.fromkeys(("official_x", "official_x_refresh", "source", "ranker", "selector", "graphics"), 0)
    totals = {key: Decimal(0) for key in ("billed_usd", "estimated_usd", "reserved_usd", "reserved_only_usd")}
    unknown = reserved_only = 0
    rows = []
    model_ids = set()

    def add(identity, category, physical, state, reservation, *, billed=None, estimate=None, **details):
        nonlocal unknown, reserved_only
        if physical:
            counts[category] += 1
            unknown += int(billed is None)
        elif state == "reserved" and reservation is not None:
            reserved_only += 1
            totals["reserved_only_usd"] += reservation
        if billed is not None:
            totals["billed_usd"] += billed
        else:
            totals["reserved_usd"] += reservation or Decimal(0)
        if estimate is not None:
            totals["estimated_usd"] += estimate
        rows.append({"identity": identity, "category": category, "physical": physical,
            "state": state, "billing_state": "reported" if billed is not None else "estimated" if estimate is not None else "unknown" if physical else "reserved",
            "billed_usd": str(billed) if billed is not None else None,
            "estimated_usd": str(estimate) if estimate is not None else None,
            "reserved_usd": str(reservation) if reservation is not None else None, **details})

    for call in OriginalContentCall.objects.filter(run_id__in=owners).order_by("pk"):
        model_ids.add(call.pk)
        category = _model_category(call, run.pk)
        counts.setdefault(category, 0)
        billed = estimate = None
        receipt = call.provenance.get("graphics_billing_receipt", {})
        if receipt:
            if (receipt.get("schema_version") != "graphics-billing-receipt/v1"
                    or receipt.get("provider") != call.provider or receipt.get("unit") not in {"usd", "usd_ticks_1e-10"}):
                raise ValueError("invalid saved Graphics billing receipt")
            billed = Decimal(receipt["amount"])
            if receipt["unit"] == "usd_ticks_1e-10":
                billed /= Decimal(10_000_000_000)
            money(billed)
        elif call.provenance.get("billing_kind") == "reported":
            payload = call.response_payload
            if not isinstance(payload, dict) or call.response_hash != digest(payload):
                raise ValueError("invalid saved Chatter billing response")
            provider = "openrouter" if call.provider == "openrouter.ai" else call.provider
            billed = reported_cost_usd(provider, {"cost": payload.get("usage", {}).get("provider_reported_cost_usd")})
            if billed is None:
                raise ValueError("missing saved Chatter reported charge")
        elif call.actual_usd is not None:
            # Older native responses store token-rate calculations in this
            # column. Without a reported receipt these remain estimates.
            estimate = call.actual_usd
        elif call.provenance.get("estimated_usd") is not None:
            estimate = money(call.provenance["estimated_usd"])
        add(f"model:{call.pk}", category, call.sent_at is not None, call.state,
            call.reserved_usd, billed=billed, estimate=estimate,
            run_id=call.run_id, stage=call.stage, provider=call.provider)

    requests = CollectionRequest.objects.filter(
        Q(attempt__run__content_run_id__in=owners)
        | Q(scope_uses__scope_run__run__content_run_id__in=owners)
    ).filter(receipt_kind="physical").distinct().order_by("pk")
    for request in requests:
        if request.endpoint_url == "https://api.x.ai/v1/responses" and request.scope_run.content_call_id in model_ids:
            # Native discovery mirrors the model transport in the collection
            # ledger. Its OriginalContentCall already owns that physical send.
            continue
        official = request.endpoint_url == OFFICIAL_ENDPOINT
        add(f"collection:{request.pk}", "official_x" if official else "source",
            request.started_at is not None, request.transport_outcome, request.reserved_usd,
            estimate=None if official else request.estimated_usd, endpoint=request.endpoint_url)

    if run.scope_key == "chatter:personalized-trends:v1":
        state = checkpoint(run)
        if state.observation:
            request, _ = _saved_observation(run, state)
            for ordinal in range(state.observation.credential_refresh_requests):
                add(f"official-refresh:{request.pk}:{ordinal + 1}", "official_x_refresh", True,
                    "recorded_attempt", None)
    counts["total"] = sum(counts.values())
    return {"run_id": run.pk, "execution_state": run.execution_state, "outcome": run.outcome,
        "graphics_run_ids": [package.pk for package in packages], "physical_calls": counts,
        "charges": {**{key: str(value) for key, value in totals.items()},
                    "unknown_charge_calls": unknown, "reserved_only_calls": reserved_only},
        "calls": rows}


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
                if stage == "trends-ranking-v1":
                    from .chatter_trends import validate_rank_reply

                    if prior.response_hash != digest(prior.response_payload):
                        raise BudgetHeld("saved ranking response identity changed")
                    return validate_rank_reply(prior.response_payload)
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
            or guarded.filter(
                request_identity__startswith=_GRAPHICS_PREFIX, state="reserved",
                claim_expires_at__gt=now, run__lease_until__gt=now,
            ).exists()
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
        if stage == "trends-ranking-v1":
            from .chatter_trends import validate_rank_reply

            reply = validate_rank_reply(reply)
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
    provenance = None
    if metadata["provider"] == "openrouter.ai":
        # A token-rate calculation is an estimate, never a reported OpenRouter charge.
        from .graphics_generation import reported_cost_usd

        actual_reported = reported_cost_usd("openrouter", {"cost": reply.get("usage", {}).get("provider_reported_cost_usd")})
        provenance = {"schema_version": 1, "billing_kind": "reported" if actual_reported is not None else "unknown",
                      "estimated_usd": str(actual) if actual is not None else None}
        actual = money(actual_reported) if actual_reported is not None else None
    with transaction.atomic():
        advisory_lock("content-budget:" + budget_scope(cfg))
        # Report the full observed cost, including an unexpected overage.
        OriginalContentCall.objects.filter(pk=call.pk).update(
            actual_usd=actual, **({"provenance": provenance} if provenance is not None else {})
        )
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
