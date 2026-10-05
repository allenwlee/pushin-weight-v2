"""Short PostgreSQL claims and pessimistic spend reservations; no network in locks."""

from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import (
    EditorialAssessment,
    EditorialBudget,
    EditorialCall,
    EditorialHero,
)
from .contracts import interval_start


class BudgetHeld(ValueError):
    pass


def claim_assessment(cutoff, cycle_id):
    now = timezone.now()
    if cutoff > now + timedelta(minutes=1) or cutoff < now - timedelta(days=8):
        raise ValueError("cutoff outside supported replay horizon")
    with transaction.atomic():
        row, created = EditorialAssessment.objects.get_or_create(
            interval=interval_start(cutoff),
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


def call_once(row, stage, kind, ceiling, cfg, send):
    """Charge the entire configured ceiling even on errors; usage is reported separately."""
    ceiling = Decimal(str(ceiling)).quantize(
        Decimal("0.000001"), rounding=ROUND_CEILING
    )
    if ceiling <= 0:
        raise BudgetHeld("positive reservation required")
    day = timezone.now().date()
    with transaction.atomic():
        require_fence(row)
        prior = EditorialCall.objects.filter(assessment=row, stage=stage).first()
        if prior:
            if prior.state == "complete":
                return prior.response
            raise BudgetHeld("stage already sent; operator reconciliation required")
        EditorialHero.objects.get_or_create(key="provider-lock")
        EditorialHero.objects.select_for_update().get(pk="provider-lock")
        EditorialBudget.objects.get_or_create(day=day)
        budget = EditorialBudget.objects.select_for_update().get(pk=day)
        spent = row.calls.aggregate(total=Sum("reserved_usd"))["total"] or Decimal(0)
        if (
            budget.reserved_usd + ceiling > Decimal(str(cfg.daily_usd))
            or spent + ceiling > Decimal(str(cfg.assessment_usd))
            or budget.calls >= cfg.daily_calls
            or row.calls.count() >= cfg.assessment_calls
            or (kind == "media" and budget.media_calls >= cfg.media_daily_calls)
        ):
            raise BudgetHeld("budget exhausted")
        # Queue concurrency is one today; this also protects future overlapping workers.
        if EditorialCall.objects.filter(state="sent").exists():
            raise BudgetHeld("provider already in flight")
        call = EditorialCall.objects.create(
            assessment=row, stage=stage, kind=kind, reserved_usd=ceiling, budget_day=day
        )
        budget.reserved_usd += ceiling
        budget.calls += 1
        budget.media_calls += int(kind == "media")
        budget.save()
    try:
        response = send()
    except Exception as exc:
        EditorialCall.objects.filter(pk=call.pk, state="sent").update(
            state="ambiguous", error_code=type(exc).__name__[:80]
        )
        raise
    EditorialCall.objects.filter(pk=call.pk, state="sent").update(
        state="complete", response=response
    )
    return response


def finish_assessment(row, outcome):
    with transaction.atomic():
        current = require_fence(row)
        current.state = "complete"
        current.outcome = outcome
        current.save(update_fields=["state", "outcome"])
