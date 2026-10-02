"""Reviewed job conclusions; observation date alone never replaces a claim."""

from django.db import transaction
from django.utils import timezone

from core.models import (
    PersonBrandAffiliation,
    PersonIdentityCorrection,
    StaffCollectionWork,
)
from core.staff_assets.queue import _lock


def active_claims(queryset=None):
    if queryset is None:
        queryset = PersonBrandAffiliation.objects.all()
    return queryset.filter(superseded_by__isnull=True).exclude(review_status="rejected")


def is_active_claim(row):
    return row.superseded_by_id is None and row.review_status != "rejected"


def matching_moved_claim(person, identity_for):
    """Reuse a moved claim's original key; historical IDs do not merge people.

    A correction changes ownership, not the source's claim fingerprint. Restrict
    this lookup to rows already owned by the resolved person, including splits.
    """
    seen, frontier = {person.pk}, {person.pk}
    while frontier:
        previous = (
            set(
                PersonIdentityCorrection.objects.filter(
                    target_id__in=frontier, kind__in=["merge", "split"]
                ).values_list("source_id", flat=True)
            )
            - seen
        )
        seen.update(previous)
        frontier = previous
    if len(seen) == 1:
        return None
    return (
        PersonBrandAffiliation.objects.filter(
            person=person, claim_identity__in=[identity_for(pk) for pk in seen]
        )
        .order_by("pk")
        .first()
    )


@transaction.atomic
def replace_claim(old_id, new_id, *, reviewer, reason, apply=True):
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer and reason are required")
    _lock()
    rows = {
        row.pk: row
        for row in PersonBrandAffiliation.objects.select_for_update()
        .filter(pk__in=[old_id, new_id])
        .order_by("pk")
    }
    old, new = rows[old_id], rows[new_id]
    if old_id == new_id:
        raise ValueError("A replacement cannot create a cycle")
    if (old.person_id, old.brand_id, old.brand_discovery_candidate_id) != (
        new.person_id,
        new.brand_id,
        new.brand_discovery_candidate_id,
    ):
        raise ValueError("Replacement must refer to the same person and organization")
    if old.superseded_by_id:
        if (
            old.superseded_by_id,
            old.superseded_by_reviewer,
            old.supersession_reason,
        ) == (new_id, reviewer, reason):
            return {"applied": apply, "old": old_id, "replacement": new_id}
        raise ValueError("This claim was already replaced")
    if new.superseded_by_id or new.review_status == "rejected":
        raise ValueError("Replacement is already replaced or rejected")
    if StaffCollectionWork.objects.filter(person=old.person, state="running").exists():
        raise ValueError("Cannot change collection context while a worker is running")
    preview = {
        "applied": apply,
        "old": old_id,
        "replacement": new_id,
        "person": str(old.person_id),
        "old_status": old.status,
        "new_status": new.status,
        "reviewer": reviewer,
        "reason": reason,
    }
    if not apply:
        return preview
    now = timezone.now()
    PersonBrandAffiliation.objects.filter(pk=old.pk).update(
        superseded_by=new,
        superseded_at=now,
        superseded_by_reviewer=reviewer,
        supersession_reason=reason,
    )
    PersonBrandAffiliation.objects.filter(pk=new.pk).update(
        review_status="confirmed",
        reviewed_at=now,
        review_note=reviewer + ": " + reason,
    )
    StaffCollectionWork.objects.filter(
        person=old.person, state__in=["queued", "retry_due"]
    ).update(state="needs_review", error_category="affiliation_corrected")
    from core.staff_assets.arrivals import register_person

    transaction.on_commit(lambda: register_person(old.person_id))
    return preview
