"""After-commit registration plus a catch-up scan for bulk/direct database writes."""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.geolocation_evidence import source_evidence
from core.geolocations import geolocation_label
from core.models import (
    Account,
    BrandAccount,
    CompanyAccount,
    Person,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
)
from core.person_affiliations import active_claims, matching_moved_claim
from core.person_identity import account_person, canonical_person
from core.person_names import digest, record_name, selected_name_for
from core.staff_assets.intake import ingest_record, validate_record
from core.staff_assets.media import record_media
from core.staff_assets.population import is_official, staff_population
from core.staff_assets.queue import enqueue

_registration_suppressed = ContextVar("staff_registration_suppressed", default=False)


@contextmanager
def without_collection_registration():
    """Keep a data-only import from scheduling collection in its own context."""
    token = _registration_suppressed.set(True)
    try:
        yield
    finally:
        _registration_suppressed.reset(token)


def register_person(person_id):
    person = Person.objects.filter(pk=person_id).first()
    if person is None:
        return
    person = canonical_person(person.pk)
    roles = list(
        active_claims(
            person.brand_affiliations.filter(
                affiliation_type_reference__code__in=["employment", "founder"]
            )
        )
        .order_by("pk")
        .values(
            "id",
            "claim_identity",
            "review_status",
            "title_raw",
            "geolocation_id",
            "status",
        )
    )
    intakes = list(person.staff_intakes.order_by("id"))
    if not roles and not intakes:
        return
    evidence_only = [
        row for row in intakes if row.payload.get("collection_mode") == "evidence_only"
    ]
    normal_intakes = [
        row for row in intakes if row.payload.get("collection_mode") != "evidence_only"
    ]
    tagged = {}
    for row in evidence_only:
        validate_record(row.payload)
        for claim in row.payload["evidence_only"]["claims"]:
            tagged.setdefault(claim["claim_identity"], []).append(claim)
    evidence_only_pairs = {
        (identity, entry["evidence_hash"])
        for identity, entries in tagged.items()
        for entry in entries
    }
    normal_pairs = set()
    for row in normal_intakes:
        for original in row.payload.get("affiliations", []):
            role = dict(original)
            source_url, evidence_text = (
                role.pop("source_url", None),
                role.pop("evidence_text", None),
            )
            source_data = role.pop("source_data", {})
            role.pop("titles", None)
            if not source_url or not evidence_text or not role.get("brand_id"):
                continue
            role.setdefault("affiliation_type", "employment")
            role.setdefault("status", "unknown")
            role.setdefault("review_status", "pending")
            role.setdefault("observed_organization_name", role["brand_id"])
            moved = matching_moved_claim(
                person, lambda pk, claim=role: digest([str(pk), claim])
            )
            identity = moved.claim_identity if moved else digest([str(person.pk), role])
            normal_pairs.add(
                (identity, digest([source_url, evidence_text, source_data]))
            )
    if tagged:
        evidence_by_role = {}
        for (
            affiliation_id,
            evidence_hash,
        ) in PersonBrandAffiliationEvidence.objects.filter(
            affiliation__person=person
        ).values_list("affiliation_id", "evidence_hash"):
            evidence_by_role.setdefault(affiliation_id, set()).add(evidence_hash)
        filtered_roles = []
        for role in roles:
            entries = tagged.get(role["claim_identity"], [])
            tagged_hashes = {entry["evidence_hash"] for entry in entries}
            hashes = evidence_by_role.get(role["id"], set())
            if (
                not entries
                or any(entry["independent_before"] for entry in entries)
                or hashes - tagged_hashes
                or any(
                    (role["claim_identity"], value) in normal_pairs for value in hashes
                )
            ):
                filtered_roles.append(role)
        roles = filtered_roles
    if not roles and evidence_only and not normal_intakes:
        return
    # Explicit operational account membership remains its own eligibility source.
    operational = any(
        row.eligibility in {"db_staff", "call_a_person"} for row in normal_intakes
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
                "author_id": account.author_id,
                "handle": account.handle,
                "display_name": account.display_name,
                "bio": account.profile_bio_text or account.bio,
                "location": geolocation_label(account.profile_location)
                if account.profile_location_id
                else None,
                "image": account.profile_picture,
            }
        )
        if account.profile_picture:
            record_media(
                person,
                {
                    "source_url": f"https://x.com/{account.handle}"
                    if account.handle
                    else f"https://x.com/i/user/{account.author_id}",
                    "original_url": account.profile_picture,
                    "source_kind": "x_account",
                    "kind": "avatar",
                    "evidence": {
                        "account_key": str(account.pk),
                        "link_status": link.resolution_status,
                    },
                },
            )
    evidence_ids = [
        evidence_id
        for evidence_id, claim_identity, evidence_hash in PersonBrandAffiliationEvidence.objects.filter(
            affiliation__person=person
        )
        .order_by("id")
        .values_list("id", "affiliation__claim_identity", "evidence_hash")
        if (claim_identity, evidence_hash) not in evidence_only_pairs
        or (claim_identity, evidence_hash) in normal_pairs
    ]
    if not person.names.exists():
        evidence = (
            PersonBrandAffiliationEvidence.objects.filter(affiliation__person=person)
            .select_related("source_post", "source_profile_snapshot")
            .order_by("id")
            .first()
        )
        default_name = selected_name_for(person, "und")
        if evidence and default_name:
            reference = evidence.source_url or (
                f"https://x.com/i/status/{evidence.source_post_id}"
                if evidence.source_post_id
                else f"profile-snapshot:{evidence.source_profile_snapshot_id}"
            )
            record_name(
                person,
                full_name=default_name,
                language="und",
                source_kind="employment_extraction",
                source_reference=reference,
                source_text=evidence.evidence_text,
                collection_method=evidence.extraction_method,
                observed_at=evidence.observed_at,
                review_reason="Extracted identity candidate; name wording and identity require review",
            )
    search = next(
        (
            row.payload
            for row in reversed(normal_intakes)
            if "baidu_eligible" in row.payload
        ),
        {},
    )
    return enqueue(
        person.pk,
        {
            "roles": roles,
            "affiliation_evidence_ids": evidence_ids,
            "accounts": snapshots,
            "intakes": [row.fingerprint for row in normal_intakes],
            "baidu_eligible": search.get("baidu_eligible") is True,
            "baidu_query": search.get("baidu_query", ""),
        },
    )


def register_account(account_id, *, eligibility="db_staff"):
    if is_official(account_id):
        return
    account = Account.x.filter(pk=account_id).first()
    if not account:
        return
    source = (
        f"https://x.com/{account.handle}"
        if account.handle
        else f"https://x.com/i/user/{account.author_id}"
    )
    snapshots = [
        {
            **{
                key: getattr(row, key)
                for key in (
                    "profile_hash",
                    "display_name",
                    "description",
                    "profile_image_url",
                )
            },
            "profile_data": source_evidence(row).profile_data,
        }
        for row in account.profile_snapshots.order_by("id")
    ]
    record = {
        "source_key": "x-account:" + account.author_id,
        "account_key": str(account.pk),
        "display_name": account.display_name or account.handle or account.author_id,
        "eligibility": eligibility,
        "profile": {
            "bio": account.profile_bio_text or account.bio,
            "location": source_evidence(account).reported_profile_location,
            "links": [source],
            "history": snapshots,
            "image": account.profile_picture,
        },
        "names": [
            {
                "full_name": account.display_name
                or account.handle
                or account.author_id,
                "language": "und",
                "source_kind": "x_profile",
                "source_reference": source,
                "source_text": account.display_name
                or account.handle
                or account.author_id,
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
                "evidence": {"account_key": str(account.pk)},
            },
        )
    return intake


def catch_up(*, list_id):
    roster = staff_population(list_id=list_id)
    errors = []
    for entry in roster["accounts"]:
        try:
            register_account(
                entry["account_key"],
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
    if not raw and not _registration_suppressed.get() and instance.role_id == "staff":
        transaction.on_commit(
            lambda: register_account(instance.account_id), robust=True
        )


@receiver(
    post_save, sender=PersonBrandAffiliation, dispatch_uid="staff_affiliation_arrival"
)
def person_arrival(sender, instance, raw=False, **kwargs):
    if not raw and not _registration_suppressed.get() and instance.affiliation_type_reference.code in {
        "employment",
        "founder",
    }:
        transaction.on_commit(lambda: register_person(instance.person_id), robust=True)


@receiver(
    post_save,
    sender=PersonBrandAffiliationEvidence,
    dispatch_uid="staff_evidence_arrival",
)
def evidence_arrival(sender, instance, raw=False, **kwargs):
    if not raw and not _registration_suppressed.get():
        transaction.on_commit(
            lambda: register_person(instance.affiliation.person_id), robust=True
        )
