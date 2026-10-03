"""After-commit registration plus a catch-up scan for bulk/direct database writes."""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import (
    Account,
    BrandAccount,
    CompanyAccount,
    Person,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
)
from core.person_affiliations import active_claims
from core.person_identity import account_person, canonical_person
from core.person_names import record_name
from core.staff_assets.intake import ingest_record
from core.staff_assets.media import record_media
from core.staff_assets.population import is_official, staff_population
from core.staff_assets.queue import enqueue


def register_person(person_id):
    person = Person.objects.filter(pk=person_id).first()
    if person is None:
        return
    person = canonical_person(person.pk)
    roles = list(
        active_claims(
            person.brand_affiliations.filter(
                affiliation_type__in=["employment", "founder"]
            )
        )
        .order_by("pk")
        .values(
            "id", "claim_identity", "review_status", "title_raw", "location", "status"
        )
    )
    intakes = list(person.staff_intakes.order_by("id"))
    if not roles and not intakes:
        return
    # Explicit operational account membership remains its own eligibility source.
    operational = any(
        row.eligibility in {"db_staff", "call_a_person"} for row in intakes
    )
    if not operational and not any(role["status"] == "current" for role in roles):
        person.collection_work.filter(state__in=["queued", "retry_due"]).update(
            state="needs_review", error_category="no_current_staff_claim"
        )
        return
    links = list(
        person.account_links.exclude(resolution_status="rejected").select_related(
            "account"
        )
    )
    snapshots = []
    for link in links:
        if link.resolution_status != "confirmed":
            observed_person = account_person(link.account)
            if not observed_person or observed_person.pk != person.pk:
                continue
        if is_official(link.account_id):
            continue
        account = link.account
        snapshots.append(
            {
                "author_id": account.pk,
                "handle": account.handle,
                "display_name": account.display_name,
                "bio": account.profile_bio_text or account.bio,
                "location": account.location,
                "image": account.profile_picture,
            }
        )
        if account.profile_picture:
            record_media(
                person,
                {
                    "source_url": f"https://x.com/{account.handle}"
                    if account.handle
                    else f"https://x.com/i/user/{account.pk}",
                    "original_url": account.profile_picture,
                    "source_kind": "x_account",
                    "kind": "avatar",
                    "evidence": {
                        "account_id": account.pk,
                        "link_status": link.resolution_status,
                    },
                },
            )
    evidence_ids = list(
        PersonBrandAffiliationEvidence.objects.filter(affiliation__person=person)
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not person.names.exists():
        evidence = (
            PersonBrandAffiliationEvidence.objects.filter(affiliation__person=person)
            .select_related("source_post", "source_profile_snapshot")
            .order_by("id")
            .first()
        )
        if evidence:
            reference = evidence.source_url or (
                f"https://x.com/i/status/{evidence.source_post_id}"
                if evidence.source_post_id
                else f"profile-snapshot:{evidence.source_profile_snapshot_id}"
            )
            record_name(
                person,
                full_name=person.display_name,
                language="und",
                source_kind="employment_extraction",
                source_reference=reference,
                source_text=evidence.evidence_text,
                collection_method=evidence.extraction_method,
                observed_at=evidence.observed_at,
                review_reason="Extracted identity candidate; name wording and identity require review",
            )
    search = next(
        (row.payload for row in reversed(intakes) if "baidu_eligible" in row.payload),
        {},
    )
    return enqueue(
        person.pk,
        {
            "roles": roles,
            "affiliation_evidence_ids": evidence_ids,
            "accounts": snapshots,
            "intakes": [row.fingerprint for row in intakes],
            "baidu_eligible": search.get("baidu_eligible") is True,
            "baidu_query": search.get("baidu_query", ""),
        },
    )


def register_account(account_id, *, eligibility="db_staff"):
    if is_official(account_id):
        return
    account = Account.objects.filter(pk=account_id).first()
    if not account:
        return
    source = (
        f"https://x.com/{account.handle}"
        if account.handle
        else f"https://x.com/i/user/{account.pk}"
    )
    snapshots = list(
        account.profile_snapshots.order_by("id").values(
            "profile_hash",
            "display_name",
            "description",
            "profile_image_url",
            "profile_data",
        )
    )
    record = {
        "source_key": "x-account:" + account.pk,
        "account_id": account.pk,
        "display_name": account.display_name or account.handle or account.pk,
        "eligibility": eligibility,
        "profile": {
            "bio": account.profile_bio_text or account.bio,
            "location": account.location,
            "links": [source],
            "history": snapshots,
            "image": account.profile_picture,
        },
        "names": [
            {
                "full_name": account.display_name or account.handle or account.pk,
                "language": "und",
                "source_kind": "x_profile",
                "source_reference": source,
                "source_text": account.display_name or account.handle or account.pk,
                "collection_method": "stored_account",
            }
        ],
    }
    intake, _ = ingest_record(record)
    if intake.person_id and account.profile_picture:
        record_media(
            intake.person,
            {
                "source_url": source,
                "original_url": account.profile_picture,
                "source_kind": "x_account",
                "kind": "avatar",
                "evidence": {"account_id": account.pk},
            },
        )
    return intake


def catch_up(*, list_id):
    roster = staff_population(list_id=list_id)
    errors = []
    for entry in roster["accounts"]:
        try:
            register_account(
                entry["account_id"],
                eligibility="call_a_person"
                if "call_a" in entry["reasons"]
                else "db_staff",
            )
        except ValueError as exc:
            errors.append({"account_id": entry["account_id"], "error": str(exc)})
    for person_id in roster["people"]:
        register_person(person_id)
    return {**roster, "identity_review": errors}


@receiver(post_save, sender=BrandAccount, dispatch_uid="staff_brand_arrival")
@receiver(post_save, sender=CompanyAccount, dispatch_uid="staff_company_arrival")
def account_arrival(sender, instance, raw=False, **kwargs):
    if not raw and instance.role_id == "staff":
        transaction.on_commit(
            lambda: register_account(instance.account_id), robust=True
        )


@receiver(
    post_save, sender=PersonBrandAffiliation, dispatch_uid="staff_affiliation_arrival"
)
def person_arrival(sender, instance, raw=False, **kwargs):
    if not raw and instance.affiliation_type in {"employment", "founder"}:
        transaction.on_commit(lambda: register_person(instance.person_id), robust=True)


@receiver(
    post_save,
    sender=PersonBrandAffiliationEvidence,
    dispatch_uid="staff_evidence_arrival",
)
def evidence_arrival(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(
            lambda: register_person(instance.affiliation.person_id), robust=True
        )
