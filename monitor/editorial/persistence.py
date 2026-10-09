"""Short PostgreSQL claims and pessimistic spend reservations; no network in locks."""

from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import (
    EditorialAssessment,
    EditorialBudget,
    EditorialCall,
    EditorialHero,
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


def call_once(row, stage, kind, ceiling, cfg, send, *, request_metadata=None):
    """Charge the entire configured ceiling even on errors; usage is reported separately."""
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
            from core.models import OriginalContentCall

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
        if run is not None:
            from core.models import OriginalContentCall

            OriginalContentCall.objects.filter(
                budget_scope="editorial",
                state="sent",
                run__lease_until__lt=timezone.now(),
            ).update(state="ambiguous", error_code="lease_expired")
            if OriginalContentCall.objects.filter(
                budget_scope="editorial", state="sent"
            ).exists():
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
    with transaction.atomic():
        EditorialCall.objects.filter(pk=call.pk, state="sent").update(
            state="complete", response=response
        )
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
