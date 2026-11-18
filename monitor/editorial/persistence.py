"""Short PostgreSQL claims and pessimistic spend reservations; no network in locks."""

import json
from copy import deepcopy
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from hashlib import sha256

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import (
    EditorialAssessment,
    EditorialBudget,
    EditorialCall,
    EditorialHero,
    OriginalContentCall,
    OriginalContentRun,
)
from monitor.original_content import (
    advisory_lock,
    budget_totals,
    mirror_storage,
    shared_storage,
)
from monitor.original_content_backfill import import_assessment, import_call

from .contracts import ProviderReplyError, interval_start


class BudgetHeld(ValueError):
    pass


class CapacityHeld(BudgetHeld):
    """A temporary in-flight limit, rather than exhausted spending."""


def claim_assessment(cutoff, cycle_id, *, scope="editorial"):
    now = timezone.now()
    if cutoff > now + timedelta(minutes=1) or cutoff < now - timedelta(days=8):
        raise ValueError("cutoff outside supported replay horizon")
    with transaction.atomic():
        row, created = EditorialAssessment.objects.get_or_create(
            interval=interval_start(cutoff),
            scope=scope,
            defaults={
                "cutoff": cutoff,
                "source_cycle_id": cycle_id,
                "lease_until": now + timedelta(minutes=15),
            },
        )
        row = EditorialAssessment.objects.select_for_update().get(pk=row.pk)
        if not created:
            if row.state != "running" or row.lease_until > now:
                return None
            row.fence += 1
            row.lease_until = now + timedelta(minutes=15)
            row.save(update_fields=["fence", "lease_until"])
            # A crashed worker's uncertain requests stay charged and never resubmit.
            row.calls.filter(state="sent").update(
                state="ambiguous", error_code="lease_expired"
            )
        if mirror_storage():
            run = import_assessment(row)
            for call in row.calls.all():
                import_call(call, run)
        return row


def require_fence(row):
    current = EditorialAssessment.objects.select_for_update().get(pk=row.pk)
    if (
        current.state != "running"
        or current.fence != row.fence
        or current.lease_until <= timezone.now()
    ):
        raise BudgetHeld("stale assessment")
    return current


def completed_text_cost(response, request_metadata):
    """Missing or invalid billing evidence keeps the full reservation."""
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return None
    try:
        if "estimated_cost" in usage:
            cost = Decimal(str(usage["estimated_cost"]))
        else:
            rates = (request_metadata or {}).get("rates", {})
            cost = Decimal(0)
            for token_key, rate_key in (
                ("prompt_tokens", "input_usd_per_million"),
                ("completion_tokens", "output_usd_per_million"),
            ):
                tokens = usage[token_key]
                rate = Decimal(str(rates[rate_key]))
                if (
                    type(tokens) is not int
                    or tokens < 0
                    or not rate.is_finite()
                    or rate < 0
                ):
                    return None
                cost += tokens * rate / Decimal(1_000_000)
        if not cost.is_finite() or cost < 0:
            return None
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None



_GRAPHICS_PREFIX = "graphics:"
_GRAPHICS_CREATE = "graphics-create/v1"
_GRAPHICS_REVIEW = "graphics-review/v1"


def _finite_limit(value, maximum):
    try:
        result = Decimal(str(value)) if value is not None else maximum
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BudgetHeld("invalid budget limit") from exc
    if not result.is_finite() or result < 0:
        raise BudgetHeld("invalid budget limit")
    return min(result, maximum)


def _graphics_daily_total(day, budget):
    """Combine legacy and direct calls without recounting mirrored calls."""
    direct = OriginalContentCall.objects.filter(budget_scope="editorial", budget_day=day).exclude(
        Q(request_identity__startswith="legacy-editorial-call:")
        | Q(request_identity__startswith=_GRAPHICS_PREFIX)
    ).aggregate(total=Sum("reserved_usd"))["total"] or Decimal(0)
    carry = Decimal(0)
    for receipt in OriginalContentRun.objects.filter(
        workflow_key="reservation-carryforward", scope_key=f"budget:editorial:{day}"
    ):
        carry += Decimal(receipt.outcome["external_reserved_usd"])
    return max(budget.reserved_usd + direct + carry, budget_totals("editorial", day)["reserved_usd"])


def reserve_graphics_call(
    *, run, stage, kind, request_hash, request_packet, provider, model, ceiling,
    owner, lease_seconds, workflow_key, per_run_limit=None, daily_limit=None,
    configured_daily_limit=None, review=False, load_bytes=None,
):
    """Reserve and claim one immutable provider request without sending it.

    Returns (call, True) for a newly claimed unsent request and (call, False)
    for a previously claimed/sent/finished identity. Callers must never send
    when False; a sent or ambiguous request remains reserved and unrepeated.
    """
    if stage not in {"C1", "G0", "G1", "S1", "S2", "I-A", "I-B", "V1", "V-B", "E1"}:
        raise ValueError("unsupported graphics stage")
    if workflow_key not in {"social-brief", "development-report", "brand-window"}:
        raise ValueError("unsupported graphics output workflow")
    if review != (stage == "E1") or kind not in {"text", "media"}:
        raise ValueError("invalid graphics lane or kind")
    if (kind == "media") != (stage in {"I-A", "I-B", "V1", "V-B"}):
        raise ValueError("invalid graphics stage kind")
    if not owner or len(owner) > 128 or type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
        raise ValueError("invalid graphics claim")
    if not isinstance(request_packet, dict):
        raise TypeError("invalid graphics request packet")
    # Persist exactly the snapshot validated here, even if the caller later
    # mutates its dictionary while this transaction waits for a budget lock.
    request_packet = deepcopy(request_packet)
    if request_packet.get("schema_version") == "graphics-request/v2":
        # Read and verify all referenced bytes before acquiring any DB lock.
        # submit_once reconstructs and checks again immediately before send.
        from .graphics_generation import reconstruct_request

        reconstruct_request(request_packet, request_hash, load_bytes=load_bytes)
    elif request_packet.get("schema_version") == "graphics-request/v1":
        if set(request_packet) != {"schema_version", "request_json"}:
            raise ValueError("invalid graphics request packet")
        raw = request_packet["request_json"]
        if not isinstance(raw, str) or len(raw.encode()) > 300000 or sha256(raw.encode()).hexdigest() != request_hash:
            raise ValueError("invalid graphics request hash")
        try:
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise TypeError("request must be an object")
            from .graphics_generation import _transform

            # Binary media must use versioned references, never embedded data URLs.
            _transform(decoded, {}, {}, reject_data=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid graphics request JSON or embedded asset") from exc
    else:
        raise ValueError("invalid graphics request packet")
    if not isinstance(provider, str) or not provider or len(provider) > 80 or not isinstance(model, str) or not model or len(model) > 160:
        raise ValueError("invalid graphics model route")
    try:
        ceiling = Decimal(str(ceiling)).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BudgetHeld("invalid reservation") from exc
    if not ceiling.is_finite() or ceiling <= 0:
        raise BudgetHeld("positive reservation required")
    if stage in {"S1", "S2"} and (provider != "exa" or model != "exa-auto" or ceiling < Decimal("0.02")):
        raise ValueError("invalid Graphics search reservation")
    run_cap = _finite_limit(per_run_limit, Decimal(4))
    daily_cap = min(_finite_limit(daily_limit, Decimal(40)), _finite_limit(configured_daily_limit, Decimal(40)))
    now = timezone.now()
    day = now.date()
    identity = f"{_GRAPHICS_PREFIX}{run.pk}:{stage}"
    lane = _GRAPHICS_REVIEW if review else _GRAPHICS_CREATE
    with transaction.atomic():
        advisory_lock(f"content-budget:editorial:{day}")
        advisory_lock("editorial-provider-inflight")
        run = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        if run.execution_state != "running" or not run.lease_until or run.lease_until <= now:
            raise BudgetHeld("stale graphics run")
        previous = OriginalContentCall.objects.filter(request_identity=identity).first()
        if previous:
            if (previous.request_hash != request_hash or previous.kind != kind or previous.batch_key != lane
                or previous.workflow_key != workflow_key or previous.provider != provider or previous.model != model):
                raise BudgetHeld("graphics identity has different request")
            if previous.state != "reserved" or (previous.claim_expires_at and previous.claim_expires_at > now):
                return previous, False
        # Expired sent calls remain charged and are never submitted again.
        OriginalContentCall.objects.filter(
            request_identity__startswith=_GRAPHICS_PREFIX, state="sent", claim_expires_at__lte=now
        ).update(state="ambiguous", error_code="lease_expired_after_send")
        active = OriginalContentCall.objects.filter(
            request_identity__startswith=_GRAPHICS_PREFIX, batch_key=lane
        ).filter(Q(state="sent") | Q(state="reserved", claim_expires_at__gt=now))
        if active.filter(run=run).exists():
            raise CapacityHeld("graphics run already in flight")
        # Staging's Chatter caller owns an exclusive provider lane. Honor that
        # contract in both directions without counting Graphics' own social-brief calls.
        chatter_active = OriginalContentCall.objects.filter(
            workflow_key__in=["chatter-discovery", "social-brief"], state="sent",
        ).exclude(request_identity__startswith=_GRAPHICS_PREFIX)
        chatter_active.filter(
            Q(claim_expires_at__lte=now) | Q(run__lease_until__lte=now)
        ).update(state="ambiguous", error_code="lease_expired_after_send")
        if chatter_active.exists():
            raise CapacityHeld("Chatter provider already in flight")
        if review:
            if active.count() >= 1:
                raise CapacityHeld("graphics review capacity exhausted")
        else:
            legacy_active = EditorialCall.objects.filter(state="sent", assessment__lease_until__gt=now).count()
            other_direct = OriginalContentCall.objects.filter(budget_scope="editorial").exclude(
                Q(request_identity__startswith="legacy-editorial-call:")
                | Q(request_identity__startswith=_GRAPHICS_PREFIX)
            ).filter(Q(state="sent") | Q(state="reserved", claim_expires_at__gt=now)).count()
            if legacy_active or other_direct or active.count() >= 2:
                raise CapacityHeld("graphics creation capacity exhausted")
        if previous:
            from monitor.trend_narrative_lifecycle import (
                claim_trend_narrative_provider_call,
            )
            claim = claim_trend_narrative_provider_call(previous.pk, owner=owner, now=now, lease_seconds=lease_seconds)
            return (claim or previous), bool(claim)
        EditorialBudget.objects.get_or_create(day=day)
        budget = EditorialBudget.objects.select_for_update().get(pk=day)
        spent = OriginalContentCall.objects.filter(run=run, request_identity__startswith=_GRAPHICS_PREFIX).aggregate(total=Sum("reserved_usd"))["total"] or Decimal(0)
        if spent + ceiling > run_cap or _graphics_daily_total(day, budget) + ceiling > daily_cap:
            raise BudgetHeld("graphics budget exhausted")
        from monitor.trend_narrative_lifecycle import (
            claim_trend_narrative_provider_call,
            reserve_original_content_call,
        )

        call = reserve_original_content_call(
            run=run, stage=f"gfx:{run.pk}:{stage}", batch_key=lane,
            request_identity=identity, request_hash=request_hash,
            request_packet=request_packet, now=now, workflow_key=workflow_key,
            workflow_version="graphics-package/v1", budget_scope="editorial",
            reserved_usd=ceiling, provider=provider, model=model,
        )
        if call is None:
            raise BudgetHeld("graphics reservation identity conflict")
        if kind != "text":
            call.kind = kind
            call.save(update_fields=["kind", "updated_at"])
        call = claim_trend_narrative_provider_call(
            call.pk, owner=owner, now=now, lease_seconds=lease_seconds
        )
        if call is None:
            raise BudgetHeld("graphics claim conflict")
        budget.reserved_usd += ceiling
        budget.calls += int(stage not in {"S1", "S2"})
        budget.media_calls += int(kind == "media")
        budget.save()
        return call, True



def fail_graphics_presend_call(call_id, *, owner, fence, error_code, now=None):
    """Fence a failed unsent reconstruction and release its unused reservation.

    Only a live owner of a never-sent call can prove there was no provider charge.
    A terminal call cannot be reclaimed or submitted again.
    """
    if error_code != "pre_send:request_reconstruction":
        raise ValueError("invalid pre-send failure code")
    now = now or timezone.now()
    observed = OriginalContentCall.objects.get(pk=call_id)
    if not observed.budget_day:
        raise ValueError("graphics call has no budget day")
    with transaction.atomic():
        advisory_lock(f"content-budget:editorial:{observed.budget_day}")
        call = OriginalContentCall.objects.select_for_update().get(pk=call_id)
        if not call.request_identity.startswith(_GRAPHICS_PREFIX):
            raise ValueError("not a graphics call")
        if call.state == "failed":
            return (
                call.sent_at is None
                and call.claim_owner == owner
                and call.claim_fence == fence
                and call.error_code == error_code
            )
        if (
            call.state != "reserved"
            or call.sent_at is not None
            or call.claim_owner != owner
            or call.claim_fence != fence
            or call.claim_expires_at is None
            or call.claim_expires_at <= now
        ):
            return False
        budget = EditorialBudget.objects.select_for_update().get(pk=call.budget_day)
        budget.reserved_usd -= call.reserved_usd
        budget.save(update_fields=["reserved_usd"])
        call.state = "failed"
        call.error_code = error_code
        call.actual_usd = Decimal(0)
        call.reserved_usd = Decimal(0)
        call.save(update_fields=["state", "error_code", "actual_usd", "reserved_usd", "updated_at"])
        return True


def _graphics_billing_receipt(provider, value):
    """Keep the precise provider amount separately from the rounded budget debit."""
    try:
        exact = Decimal(str(value))
        if not exact.is_finite() or not 0 <= exact <= Decimal('999999.999999'):
            raise ValueError('invalid actual cost')
        rounded = exact.quantize(Decimal('0.000001'), rounding=ROUND_CEILING)
        if provider == 'xai':
            ticks = exact * Decimal(10_000_000_000)
            if ticks != ticks.to_integral_value():
                raise ValueError('xAI cost is not whole billing ticks')
            unit, amount = 'usd_ticks_1e-10', str(int(ticks))
        else:
            unit, amount = 'usd', str(exact)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('invalid actual cost') from exc
    return rounded, {'schema_version': 'graphics-billing-receipt/v1',
                     'provider': provider, 'unit': unit, 'amount': amount}


def complete_graphics_call(
    call_id, *, owner, fence, response_hash, response_payload, actual_usd=None, now=None
):
    """Save a provider response and adjust the original day's reservation once."""
    from monitor.original_content import digest
    from monitor.trend_narrative_lifecycle import complete_trend_narrative_provider_call

    if not isinstance(response_payload, dict) or response_hash != digest(response_payload):
        raise ValueError("graphics response hash mismatch")
    observed = OriginalContentCall.objects.get(pk=call_id)
    if not observed.request_identity.startswith(_GRAPHICS_PREFIX) or not observed.budget_day:
        raise ValueError("not a graphics call")
    actual_usd, receipt = (_graphics_billing_receipt(observed.provider, actual_usd)
                           if actual_usd is not None else (None, None))
    with transaction.atomic():
        advisory_lock(f"content-budget:editorial:{observed.budget_day}")
        call = OriginalContentCall.objects.select_for_update().get(pk=call_id)
        if call.state == "completed":
            return (call.claim_owner == owner and call.claim_fence == fence
                    and call.response_hash == response_hash and call.actual_usd == actual_usd
                    and call.provenance.get('graphics_billing_receipt') == receipt)
        if call.state != "sent" or call.claim_owner != owner or call.claim_fence != fence:
            return False
        if not complete_trend_narrative_provider_call(
            call_id, owner=owner, fence=fence, response_hash=response_hash,
            response_payload=response_payload, now=now or timezone.now(),
        ):
            return False
        if actual_usd is not None:
            budget = EditorialBudget.objects.select_for_update().get(pk=call.budget_day)
            budget.reserved_usd += actual_usd - call.reserved_usd
            budget.save(update_fields=["reserved_usd"])
            provenance = {**call.provenance, 'graphics_billing_receipt': receipt}
            OriginalContentCall.objects.filter(pk=call_id).update(
                reserved_usd=actual_usd, actual_usd=actual_usd, provenance=provenance)
        return True


def record_graphics_video_cost(call_id, *, request_id, actual_usd):
    """Reconcile an accepted video call once when its saved job reports a cost."""
    from monitor.original_content import digest

    actual, receipt = _graphics_billing_receipt('xai', actual_usd)
    observed = OriginalContentCall.objects.get(pk=call_id)
    if not observed.budget_day:
        raise ValueError('video call has no budget day')
    with transaction.atomic():
        advisory_lock(f'content-budget:editorial:{observed.budget_day}')
        call = OriginalContentCall.objects.select_for_update().get(pk=call_id)
        if (not call.request_identity.startswith(_GRAPHICS_PREFIX)
                or not call.request_identity.endswith((':V1', ':V-B'))
                or call.provider != 'xai' or call.kind != 'media' or call.state != 'completed'
                or not isinstance(call.response_payload, dict)
                or call.response_hash != digest(call.response_payload)
                or call.response_payload.get('request_id') != request_id):
            raise ValueError('video cost does not match completed request')
        if call.actual_usd is not None:
            return (call.actual_usd == actual
                    and call.provenance.get('graphics_billing_receipt') == receipt)
        budget = EditorialBudget.objects.select_for_update().get(pk=call.budget_day)
        budget.reserved_usd += actual - call.reserved_usd
        budget.save(update_fields=['reserved_usd'])
        call.actual_usd = call.reserved_usd = actual
        call.provenance = {**call.provenance, 'graphics_billing_receipt': receipt}
        call.save(update_fields=['actual_usd', 'reserved_usd', 'provenance', 'updated_at'])
        return True

def call_once(row, stage, kind, ceiling, cfg, send, *, request_metadata=None):
    """Reserve before sending; release unused allowance for confirmed text usage."""
    ceiling = Decimal(str(ceiling)).quantize(
        Decimal("0.000001"), rounding=ROUND_CEILING
    )
    if ceiling <= 0:
        raise BudgetHeld("positive reservation required")
    if shared_storage() and not request_metadata:
        raise BudgetHeld("shared transport requires the actual request identity")
    day = timezone.now().date()
    with transaction.atomic():
        advisory_lock(f"content-budget:editorial:{day}")
        advisory_lock("editorial-provider-inflight")
        require_fence(row)
        EditorialHero.objects.get_or_create(key="provider-lock")
        EditorialHero.objects.select_for_update().get(pk="provider-lock")
        # A picture can be revisited in a later interval after a worker died.
        # Its media stage belongs to the picture, not to that later assessment.
        stages = EditorialCall.objects.filter(stage=stage, kind=kind)
        prior = (stages if kind == "media" else stages.filter(assessment=row)).first()
        if prior:
            if prior.state == "complete":
                return prior.response
            raise BudgetHeld("stage already sent; operator reconciliation required")
        run = import_assessment(row) if mirror_storage() else None
        if run is not None and request_metadata:
            run.config_snapshot = cfg.model_dump(mode="json")
            run.workflow_version = request_metadata["workflow_version"]
            run.save(update_fields=["config_snapshot", "workflow_version"])
        if run is not None:
            attempts = OriginalContentCall.objects.filter(stage=stage, kind=kind)
            canonical = (
                attempts if kind == "media" else attempts.filter(run=run)
            ).first()
            if canonical:
                if canonical.state == "completed":
                    return canonical.response_payload
                raise BudgetHeld("stage already sent; operator reconciliation required")
        EditorialBudget.objects.get_or_create(day=day)
        budget = EditorialBudget.objects.select_for_update().get(pk=day)
        spent = row.calls.aggregate(total=Sum("reserved_usd"))["total"] or Decimal(0)
        totals = (
            budget_totals("editorial", day)
            if shared_storage()
            else {
                "reserved_usd": budget.reserved_usd,
                "calls": budget.calls,
                "media_calls": budget.media_calls,
            }
        )
        if (
            totals["reserved_usd"] + ceiling > Decimal(str(cfg.daily_usd))
            or spent + ceiling > Decimal(str(cfg.assessment_usd))
            or totals["calls"] >= cfg.daily_calls
            or row.calls.count() >= cfg.assessment_calls
            or (kind == "media" and totals["media_calls"] >= cfg.media_daily_calls)
        ):
            raise BudgetHeld("budget exhausted")
        # Queue concurrency is one today; this also protects future overlapping workers.
        EditorialCall.objects.filter(
            state="sent", assessment__lease_until__lt=timezone.now()
        ).update(state="ambiguous", error_code="lease_expired")
        if EditorialCall.objects.filter(state="sent").exists():
            raise BudgetHeld("provider already in flight")
        OriginalContentCall.objects.filter(
            request_identity__startswith=_GRAPHICS_PREFIX, state="sent",
            claim_expires_at__lte=timezone.now(),
        ).update(state="ambiguous", error_code="lease_expired_after_send")
        if run is None and OriginalContentCall.objects.filter(
            request_identity__startswith=_GRAPHICS_PREFIX,
        ).filter(
            Q(state="sent") | Q(state="reserved", claim_expires_at__gt=timezone.now(),
                                 run__lease_until__gt=timezone.now())
        ).exclude(batch_key=_GRAPHICS_REVIEW).exists():
            raise BudgetHeld("provider already in flight")
        if run is not None:
            OriginalContentCall.objects.filter(
                budget_scope="editorial",
                state="sent",
                run__lease_until__lt=timezone.now(),
            ).exclude(request_identity__startswith=_GRAPHICS_PREFIX).update(state="ambiguous", error_code="lease_expired")
            if OriginalContentCall.objects.filter(
                Q(budget_scope="editorial")
                | Q(workflow_key__in=["chatter-discovery", "social-brief"])
            ).filter(
                Q(state="sent") | Q(state="reserved", request_identity__startswith=_GRAPHICS_PREFIX,
                                     claim_expires_at__gt=timezone.now(), run__lease_until__gt=timezone.now())
            ).exclude(batch_key=_GRAPHICS_REVIEW).exists():
                raise BudgetHeld("provider already in flight")
        call = EditorialCall.objects.create(
            assessment=row, stage=stage, kind=kind, reserved_usd=ceiling, budget_day=day
        )
        budget.reserved_usd += ceiling
        budget.calls += 1
        budget.media_calls += int(kind == "media")
        budget.save()
        if run is not None:
            import_call(call, run, request_metadata=request_metadata)
    try:
        response = send()
    except Exception as exc:
        failure = {"state": "ambiguous", "error_code": type(exc).__name__[:80]}
        if isinstance(exc, ProviderReplyError):
            failure.update(error_code=exc.code, response={"failure": exc.diagnostics})
        with transaction.atomic():
            EditorialCall.objects.filter(pk=call.pk, state="sent").update(**failure)
            if run is not None:
                call.refresh_from_db()
                import_call(call, run, request_metadata=request_metadata)
        raise
    cost = completed_text_cost(response, request_metadata) if kind == "text" else None
    charged = min(call.reserved_usd, cost) if cost is not None else call.reserved_usd
    with transaction.atomic():
        advisory_lock(f"content-budget:editorial:{call.budget_day}")
        completed = EditorialCall.objects.filter(pk=call.pk, state="sent").update(
            state="complete", response=response, reserved_usd=charged
        )
        if completed and charged < call.reserved_usd:
            budget = EditorialBudget.objects.select_for_update().get(pk=call.budget_day)
            budget.reserved_usd -= call.reserved_usd - charged
            budget.save(update_fields=["reserved_usd"])
        if run is not None:
            call.refresh_from_db()
            import_call(
                call, run, request_metadata=request_metadata, finished_at=timezone.now()
            )
    return response


def finish_assessment(row, outcome):
    with transaction.atomic():
        current = require_fence(row)
        current.state = "complete"
        current.outcome = outcome
        current.save(update_fields=["state", "outcome"])
        if mirror_storage():
            import_assessment(current)
