"""Durable per-person research on the existing Graphics worker pool."""

import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import Person, StaffCollectionWork, StaffProviderRequest
from core.person_names import digest
from core.staff_assets.queue import finish

POLICY = "person-intake-v1"
OPEN = ("queued", "running", "retry_due")
logger = logging.getLogger(__name__)


def collect_missing(identity, subject, evidence, needs, *, apply=True, portrait_reader=None):
    """Complete known facts first. Reserve only work still needed for this subject."""
    from monitor.editorial.graphics_cast import portrait_asset

    pid = identity.get("person_id")
    result = {**identity, "asset": None, "work_id": None}
    if not pid:
        return result
    cache_checked_at = timezone.now()
    if "portrait" in needs:
        result["asset"] = (portrait_reader or portrait_asset)(pid, subject, [])
    wants_jobs = bool(identity.get("jobs"))
    missing = "portrait" in needs and result["asset"] is None
    if not (missing or wants_jobs) or not apply:
        return result
    route = "china" if identity.get("china") else "general"
    options = {
        "route": route,
        "facematch": bool(identity.get("facematch")),
        "jobs": wants_jobs,
        "portrait": missing,
    }
    # Repeated publications with the same source share the completed result, while
    # concurrent publications with new evidence join any matching active request.
    if identity.get("affiliation") and not evidence.get("affiliation"):
        evidence = {**evidence, "affiliation": identity["affiliation"]}
    source = {
        key: evidence.get(key)
        for key in ("source_id", "source_url", "source_urls", "passage", "affiliation")
    }
    fingerprint = digest([options, subject, source])
    with transaction.atomic():
        Person.objects.select_for_update().get(pk=pid)
        works = StaffCollectionWork.objects.filter(person_id=pid, policy_version=POLICY)
        work = works.filter(fingerprint=fingerprint).first()
        if work is None:
            work = (
                works.filter(context__options=options)
                .filter(
                    Q(state__in=OPEN)
                    | Q(state="complete", updated_at__gte=cache_checked_at)
                )
                .order_by("-updated_at")
                .first()
            )
        if work is None:
            work = works.create(
                person_id=pid,
                policy_version=POLICY,
                fingerprint=fingerprint,
                context={
                    "version": 1,
                    "subject": subject,
                    "evidence": evidence,
                    "options": options,
                    "needs": sorted(needs),
                },
            )
        result["work_id"] = work.pk
        if work.state in ("queued", "retry_due"):
            transaction.on_commit(lambda: dispatch_due(work.pk))
    return result


@transaction.atomic
def resume_after_configuration(work_id):
    """Explicitly resume after a missing runtime/credential is supplied by the operator."""
    work = StaffCollectionWork.objects.select_for_update().get(
        pk=work_id, policy_version=POLICY
    )
    gaps = work.result.get("gaps") or []
    missing = any(
        "runtime_missing:" in gap or gap.endswith("credential_unavailable")
        for gap in gaps
    )
    if (
        not missing
        or work.state != "needs_evidence"
        or StaffProviderRequest.objects.filter(work=work)
        .exclude(state="complete")
        .exists()
    ):
        raise ValueError("Only a settled prerequisite failure can be resumed")
    work.state = "retry_due"
    work.next_attempt_at = timezone.now()
    work.error_category = ""
    work.context = {
        **work.context,
        "resumed_after_configuration_at": work.next_attempt_at.isoformat(),
    }
    work.save(
        update_fields=[
            "state",
            "context",
            "next_attempt_at",
            "error_category",
            "updated_at",
        ]
    )
    transaction.on_commit(lambda: dispatch_due(work.pk))
    return work.pk


def dispatch_due(work_id):
    """A lost broker message is rediscovered by the existing Graphics reconciler."""
    from monitor.editorial.graphics_dispatch import REVIEW_QUEUE, _enqueue
    from monitor.tasks import research_chatter_person

    now = timezone.now()
    due = StaffCollectionWork.objects.filter(pk=work_id, policy_version=POLICY).filter(
        Q(state__in=("queued", "retry_due"), next_attempt_at__lte=now)
        | Q(state="running", lease_expires_at__lte=now, next_attempt_at__lte=now)
    )
    if not due.update(next_attempt_at=now + timedelta(seconds=45)):
        return False
    return _enqueue(research_chatter_person, [work_id], queue=REVIEW_QUEUE)


def recover_due():
    now = timezone.now()
    rows = StaffCollectionWork.objects.filter(
        policy_version=POLICY, next_attempt_at__lte=now
    ).filter(
        Q(state__in=("queued", "retry_due"))
        | Q(state="running", lease_expires_at__lte=now)
    )
    for work_id in rows.order_by("next_attempt_at", "pk").values_list("pk", flat=True)[
        :10
    ]:
        dispatch_due(work_id)


@transaction.atomic
def claim_research(work_id):
    work = (
        StaffCollectionWork.objects.select_for_update()
        .filter(pk=work_id, policy_version=POLICY)
        .first()
    )
    now = timezone.now()
    if (
        not work
        or work.state not in OPEN
        or work.state == "running"
        and work.lease_expires_at > now
    ):
        return None
    if work.state == "running" and (
        work.attempts >= 2
        or StaffProviderRequest.objects.filter(work=work)
        .exclude(state="complete")
        .exists()
    ):
        work.state = "needs_review"
        work.lease_token = work.lease_expires_at = None
        work.error_category = "interrupted_research"
        work.save()
        return None
    work.state = "running"
    work.attempts += 1
    work.lease_token = uuid.uuid4()
    work.lease_expires_at = now + timedelta(minutes=9)
    work.save()
    return work


def run_research(work_id):
    from core.staff_assets.person_intake import create_or_update_person

    work = claim_research(work_id)
    if work is None:
        return "already_claimed_or_finished"
    ctx = work.context
    options = ctx["options"]
    try:
        if work.person.merged_into_id:
            outcome = {"status": "needs_review", "gaps": ["person_merged"]}
        elif options["route"] == "china":
            from core.staff_assets.person_china import research_china_portrait

            outcome = research_china_portrait(
                person=work.person,
                subject=ctx["subject"],
                evidence=ctx["evidence"],
                facematch=options["facematch"],
                jobs=options["jobs"],
                work=work,
            )
        else:
            from core.staff_assets.person_portrait import research_general_portrait

            outcome = research_general_portrait(
                person=work.person,
                subject=ctx["subject"],
                evidence=ctx["evidence"],
                facematch=options["facematch"],
                work=work,
                jobs=options["jobs"],
                portrait=options["portrait"],
            )
        # Bind returned observations to this work only when the adapter attests the
        # named subject. Preserve personal account / identity conflicts in the result.
        for evidence in outcome.get("evidence", []):
            if not isinstance(evidence, dict) or str(
                evidence.get("person_id", work.person_id)
            ) != str(work.person_id):
                continue
            updated = create_or_update_person(
                ctx["subject"],
                {**evidence, "person_id": str(work.person_id)},
                needs=set(
                    ctx.get("needs")
                    or ({"portrait", "jobs"} if options["jobs"] else {"portrait"})
                ),
                collect=False,
            )
            outcome.setdefault("gaps", []).extend(updated.get("gaps", []))
        status = outcome.get("status")
        state = (
            "complete"
            if status == "complete"
            else "needs_review"
            if status in ("needs_review", "identity_unresolved")
            else "needs_evidence"
        )
    except Exception as exc:
        logger.exception("Person research stopped for work %s", work.pk)
        state = "needs_review"
        outcome = {"status": state, "gaps": [type(exc).__name__]}
    finish(work, state=state, result=outcome)
    return state
