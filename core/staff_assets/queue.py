"""Short database leases and paid-request reservations; no HTTP inside locks."""

import uuid
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from core.models import StaffCollectionWork, StaffProviderRequest
from core.person_names import digest

POLICY = "staff-v1"


def _lock():
    if connection.vendor != "postgresql":
        raise RuntimeError("Staff collection requires PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [71814001])


def enqueue(person_id, context):
    return StaffCollectionWork.objects.get_or_create(
        person_id=person_id,
        fingerprint=digest(context),
        policy_version=POLICY,
        defaults={"context": context},
    )[0]


@transaction.atomic
def claim(*, lease_seconds=180, max_attempts=3):
    _lock()
    now = timezone.now()
    for work in StaffCollectionWork.objects.select_for_update().filter(
        state="running", lease_expires_at__lte=now
    ):
        ambiguous = StaffProviderRequest.objects.filter(
            work=work, state="reserved"
        ).exists()
        work.state = (
            "needs_review"
            if ambiguous or work.attempts >= max_attempts
            else "retry_due"
        )
        work.error_category = "interrupted_request" if ambiguous else "expired_lease"
        work.lease_token = work.lease_expires_at = None
        work.save()
    # Shared concurrency cap = one, including other processes and runs.
    if StaffCollectionWork.objects.filter(state="running").exists():
        return None
    work = (
        StaffCollectionWork.objects.select_for_update(skip_locked=True)
        .filter(
            state__in=["queued", "retry_due"],
            person__merged_into__isnull=True,
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at", "id")
        .first()
    )
    if work:
        work.state = "running"
        work.lease_token = uuid.uuid4()
        work.lease_expires_at = now + timedelta(seconds=lease_seconds)
        work.attempts += 1
        work.save()
    return work


def finish(work, *, state, result=None, error="", retry_seconds=3600):
    return (
        StaffCollectionWork.objects.filter(
            pk=work.pk,
            state="running",
            lease_token=work.lease_token,
            lease_expires_at__gt=timezone.now(),
        ).update(
            state=state,
            result=result or {},
            error_category=error,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=timezone.now() + timedelta(seconds=retry_seconds),
            updated_at=timezone.now(),
        )
        == 1
    )


class BudgetExhausted(Exception):
    pass


class AmbiguousRequest(Exception):
    pass


@transaction.atomic
def reserve_request(
    work, *, run_id, provider, parameters, per_person, per_run, per_day
):
    if min(per_person, per_run, per_day) < 1:
        raise BudgetExhausted("Paid request budgets are disabled")
    _lock()
    if not StaffCollectionWork.objects.filter(
        pk=work.pk,
        state="running",
        lease_token=work.lease_token,
        lease_expires_at__gt=timezone.now(),
    ).exists():
        raise AmbiguousRequest("Work lease expired")
    key = {
        "person_id": work.person_id,
        "provider": provider,
        "fingerprint": digest(parameters),
    }
    from core.person_identity import identity_ids

    related_ids = identity_ids(work.person_id)
    matches = StaffProviderRequest.objects.filter(
        person_id__in=related_ids, provider=provider, fingerprint=key["fingerprint"]
    )
    if matches.exclude(state="complete").exists():
        raise AmbiguousRequest(
            "A matching request needs review; no automatic paid retry"
        )
    existing = matches.order_by("pk").first()
    if existing:
        if existing.state == "complete":
            return existing, False
        raise AmbiguousRequest(
            "A matching request needs review; no automatic paid retry"
        )
    day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    requests = StaffProviderRequest.objects.filter(provider=provider)
    if (
        requests.filter(person_id__in=related_ids).count() >= per_person
        or requests.filter(run_id=run_id).count() >= per_run
        or requests.filter(created_at__gte=day_start).count() >= per_day
    ):
        raise BudgetExhausted("Staff search request cap reached")
    return StaffProviderRequest.objects.create(
        **key, work=work, run_id=run_id, parameters=parameters
    ), True


def record_response(request, *, response=None, error=""):
    # Preserve late responses in the journal even if the work lease has expired.
    return StaffProviderRequest.objects.filter(pk=request.pk, state="reserved").update(
        state="needs_review" if error else "complete",
        response=response or {},
        error_category=error,
        completed_at=timezone.now(),
    )
