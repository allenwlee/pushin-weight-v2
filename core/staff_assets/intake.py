"""One import path for curated site research, existing accounts and new arrivals."""

import re

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    Account,
    AffiliationType,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    StaffIntake,
)
from core.person_affiliations import matching_moved_claim, require_claim_owner
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
    mode = record.get("collection_mode")
    policy = record.get("evidence_only")
    if mode is None:
        if policy is not None:
            raise ValueError("Evidence-only policy requires collection mode")
    elif (
        mode != "evidence_only"
        or not isinstance(policy, dict)
        or set(policy) != {"schema", "claims"}
        or policy.get("schema") != "staff-evidence-only/v1"
        or not isinstance(policy.get("claims"), list)
    ):
        raise ValueError("Invalid evidence-only collection policy")
    else:
        if not record.get("observed_at"):
            raise ValueError("Evidence-only intake requires an observation time")
        if any(
            "selection" in name or "review" in name for name in record.get("names", [])
        ):
            raise ValueError(
                "Evidence-only intake cannot change name selection or review"
            )
        seen = set()
        for claim in policy["claims"]:
            if (
                not isinstance(claim, dict)
                or set(claim)
                != {"claim_identity", "evidence_hash", "independent_before"}
                or type(claim["independent_before"]) is not bool
                or any(
                    not isinstance(claim[key], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", claim[key])
                    for key in ("claim_identity", "evidence_hash")
                )
            ):
                raise ValueError("Invalid evidence-only prepared claim")
            pair = (claim["claim_identity"], claim["evidence_hash"])
            if pair in seen:
                raise ValueError("Duplicate evidence-only prepared claim")
            seen.add(pair)
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
    account_key = record.get("account_key")
    if not account_key and record.get("account_id"):
        account_key = (
            Account.x.filter(author_id=str(record["account_id"]))
            .values_list("pk", flat=True)
            .first()
        )
    if account_key and is_official(account_key):
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
        with transaction.atomic():
            return _ingest_resolved(
                record,
                source_key=source_key,
                fingerprint=fingerprint,
                observed=observed,
                eligibility=eligibility,
            )
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


def _ingest_resolved(record, *, source_key, fingerprint, observed, eligibility):
    # Until account-link provenance is represented in the evidence-only policy,
    # do not let a newly linked account alter an independently eligible person's
    # avatar or collection context on a later catch-up run.
    prior_account_links = None
    if record.get("collection_mode") == "evidence_only":
        links = PersonAccount.objects.all()
        if record.get("account_key"):
            links = links.filter(account_id=record["account_key"])
        elif record.get("account_id"):
            links = links.filter(account__author_id=str(record["account_id"]))
        else:
            links = links.none()
        prior_account_links = set(links.values_list("person_id", "account_id"))
    person, account = resolve_person(record, create=True)
    if (
        account
        and prior_account_links is not None
        and (person.pk, account.pk) not in prior_account_links
    ):
        raise IdentityConflict("Source-only account link requires review")
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
    evidence_policy = (
        record.get("evidence_only")
        if record.get("collection_mode") == "evidence_only"
        else None
    )
    prepared_claims = (
        {
            (entry["claim_identity"], entry["evidence_hash"]): entry
            for entry in evidence_policy["claims"]
        }
        if evidence_policy
        else {}
    )
    seen_claims = set()
    prior_policies = [
        row.payload["evidence_only"]
        for row in person.staff_intakes.all()
        if row.payload.get("collection_mode") == "evidence_only"
        and isinstance(row.payload.get("evidence_only"), dict)
    ]
    prior_claims = [
        entry for policy in prior_policies for entry in policy.get("claims", [])
    ]
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
        moved = matching_moved_claim(
            person, lambda pk, claim=role: digest([str(pk), claim])
        )
        # The source spelling remains in the published claim fingerprint.
        type_code = role["affiliation_type"]
        affiliation, affiliation_created = PersonBrandAffiliation.objects.get_or_create(
            claim_identity=moved.claim_identity
            if moved
            else digest([str(person.pk), role]),
            defaults={
                "person": person,
                **{
                    key: value
                    for key, value in role.items()
                    if key not in {"affiliation_type", "location"}
                },
                "affiliation_type_reference": AffiliationType.objects.get(
                    code=type_code
                ),
            },
        )
        from core.geolocation_evidence import write_source_evidence

        if affiliation_created and "location" in role:
            write_source_evidence(affiliation, reported_location=role["location"])
        require_claim_owner(affiliation, person)
        if evidence_policy is not None:
            evidence_hash = digest([source_url, evidence_text, source_data])
            pair = (affiliation.claim_identity, evidence_hash)
            prepared = prepared_claims.get(pair)
            if prepared is None:
                raise ValueError("Evidence-only claim was not prepared")
            tagged = [
                entry
                for entry in prior_claims
                if entry["claim_identity"] == affiliation.claim_identity
            ]
            tagged_hashes = {entry["evidence_hash"] for entry in tagged}
            existing_hashes = set(
                affiliation.evidence.values_list("evidence_hash", flat=True)
            )
            independent_before = not affiliation_created and (
                not tagged
                or any(entry["independent_before"] for entry in tagged)
                or bool(existing_hashes - tagged_hashes)
            )
            if prepared["independent_before"] != independent_before:
                raise ValueError("Evidence-only prepared independence is stale")
            seen_claims.add(pair)
        source_row, source_created = (
            PersonBrandAffiliationEvidence.objects.get_or_create(
                affiliation=affiliation,
                evidence_hash=digest([source_url, evidence_text, source_data]),
                defaults={
                    "source_url": source_url,
                    "evidence_text": evidence_text,
                    "observed_at": observed,
                    "extraction_method": "staff-manifest-v1",
                },
            )
        )
        if source_created:
            write_source_evidence(source_row, extracted_claim_data=source_data)
        originals = {}
        for title in title_texts:
            entry = dict(title)
            key = entry.pop("key", str(len(originals)))
            parent = entry.pop("derived_from_key", None)
            if parent and parent not in originals:
                raise ValueError("A translated title must follow its original")
            originals[key] = record_text(
                person,
                affiliation=affiliation,
                kind="title",
                observed_at=observed,
                derived_from=originals.get(parent),
                **entry,
            )
    for entry in record.get("texts", []):
        record_text(person, observed_at=observed, **entry)
    if evidence_policy is not None and seen_claims != set(prepared_claims):
        raise ValueError("Evidence-only prepared claims do not match input")
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
