"""One import path for curated site research, existing accounts and new arrivals."""

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    StaffIntake,
)
from core.person_identity import IdentityConflict, manifest_person
from core.person_names import digest, record_name, review_name, select_names
from core.person_text import record_text
from core.staff_assets.population import is_official

ELIGIBLE = {"staff", "former_staff", "dated_staff", "call_a_person", "db_staff"}


def observed_time(value):
    if not value:
        return timezone.now()
    result = parse_datetime(value) if isinstance(value, str) else value
    if result is None or timezone.is_naive(result):
        raise ValueError("Observation time must include a timezone")
    return result


def validate_record(record):
    if not record.get("source_key") or not record.get("display_name"):
        raise ValueError("Stable source_key and display_name are required")
    if record.get("eligibility") in {
        "staff",
        "former_staff",
        "dated_staff",
    } and not record.get("affiliations"):
        raise ValueError("Staff eligibility requires separate employment evidence")
    if (
        record.get("baidu_eligible") is True
        and not record.get("baidu_query", "").strip()
    ):
        raise ValueError("Baidu eligibility requires an explicit disambiguated query")
    for role in record.get("affiliations", []):
        if role.get("affiliation_type", "employment") not in {"employment", "founder"}:
            raise ValueError("Contributor-only affiliations do not establish staff")
        if not role.get("source_url") or not role.get("evidence_text"):
            raise ValueError("Affiliations require source URL and employment excerpt")
    observed_time(record.get("observed_at"))
    return record


def resolve_person(record, *, create=False):
    return manifest_person(record, create=create)


@transaction.atomic
def ingest_record(record):
    validate_record(record)
    source_key = record["source_key"]
    fingerprint = digest(record)
    previous = StaffIntake.objects.filter(
        source_key=source_key, fingerprint=fingerprint
    ).first()
    if previous and previous.eligibility != "needs_review":
        return previous, False
    observed = observed_time(record.get("observed_at"))
    eligibility = record.get("eligibility", "unestablished")
    if record.get("account_id") and is_official(record["account_id"]):
        eligibility = "official_account"
    if eligibility not in ELIGIBLE:
        return StaffIntake.objects.get_or_create(
            source_key=source_key,
            fingerprint=fingerprint,
            defaults={
                "eligibility": eligibility,
                "payload": record,
                "observed_at": observed,
            },
        )[0], False
    try:
        person, account = resolve_person(record, create=True)
    except IdentityConflict:
        return StaffIntake.objects.get_or_create(
            source_key=source_key,
            fingerprint=fingerprint,
            defaults={
                "eligibility": "needs_review",
                "payload": record,
                "observed_at": observed,
            },
        )
    # Serialize concurrent versions for the same person before adding evidence.
    Person.objects.select_for_update().get(pk=person.pk)
    if account:
        PersonAccount.objects.get_or_create(
            person=person,
            account=account,
            defaults={
                "first_observed_at": observed,
                "last_observed_at": observed,
                "resolution_status": "pending",
            },
        )
    selected = {"primary": person.primary_name, "english": person.english_name}
    recorded = {}
    for entry in record.get("names", []):
        entry = dict(entry)
        ref = entry.pop("key", str(len(recorded)))
        derived_key = entry.pop("derived_from_key", None)
        if derived_key and derived_key not in recorded:
            raise ValueError("Derived name must follow its original in the manifest")
        review = entry.pop("review", None)
        selection = entry.pop("selection", None)
        row = record_name(
            person,
            observed_at=observed,
            derived_from=recorded.get(derived_key),
            **entry,
        )
        recorded[ref] = row
        if review and (
            not row.review_history
            or row.review_history[-1].get("reason") != review["reason"]
            or row.review_status != review["status"]
        ):
            review_name(row, review["status"], review["reviewer"], review["reason"])
        if selection:
            if selection not in selected:
                raise ValueError("Unknown name selection")
            selected[selection] = row
    select_names(person, **selected)
    for entry in record.get("affiliations", []):
        role = dict(entry)
        source_url, evidence_text = role.pop("source_url"), role.pop("evidence_text")
        source_data = role.pop("source_data", {})
        title_texts = role.pop("titles", [])
        role.setdefault("affiliation_type", "employment")
        role.setdefault("status", "unknown")
        role.setdefault("review_status", "pending")
        role.setdefault("observed_organization_name", role["brand_id"])
        affiliation, _ = PersonBrandAffiliation.objects.get_or_create(
            claim_identity=digest([str(person.pk), role]),
            defaults={"person": person, **role},
        )
        PersonBrandAffiliationEvidence.objects.get_or_create(
            affiliation=affiliation,
            evidence_hash=digest([source_url, evidence_text, source_data]),
            defaults={
                "source_url": source_url,
                "evidence_text": evidence_text,
                "observed_at": observed,
                "extracted_claim_data": source_data,
                "extraction_method": "staff-manifest-v1",
            },
        )
        originals = {}
        for title in title_texts:
            entry = dict(title)
            key = entry.pop("key", str(len(originals)))
            parent = entry.pop("derived_from_key", None)
            if parent and parent not in originals:
                raise ValueError("A translated title must follow its original")
            originals[key] = record_text(person, affiliation=affiliation, kind="title",
                                         observed_at=observed, derived_from=originals.get(parent), **entry)
    for entry in record.get("texts", []):
        record_text(person, observed_at=observed, **entry)
    intake, created = StaffIntake.objects.get_or_create(
        source_key=source_key,
        fingerprint=fingerprint,
        defaults={
            "person": person,
            "eligibility": eligibility,
            "payload": record,
            "observed_at": observed,
        },
    )
    if intake.person_id is None:
        intake.person = person
        intake.eligibility = eligibility
        intake.save(update_fields=["person", "eligibility"])
    from core.staff_assets.arrivals import register_person

    transaction.on_commit(lambda: register_person(person.pk))
    return intake, created
