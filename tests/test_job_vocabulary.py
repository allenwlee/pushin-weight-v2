"""Job source identity, typed classifications, and database write boundaries."""

import hashlib

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.intelligence_readers import job_listing_document
from core.job_vocabulary import (
    NORMALIZER_ID,
    compensation_references,
    write_job_classifications,
)
from core.models import (
    Brand,
    Company,
    Currency,
    DefinitionVersion,
    EmploymentType,
    JobEmploymentTypeAssignment,
    JobListing,
    JobListingEvidence,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def listing(key):
    brand, _ = Brand.objects.get_or_create(nickname="qwen")
    now = timezone.now()
    return JobListing.objects.create(
        brand=brand,
        hiring_organization="Qwen",
        title=key,
        listing_identity=key,
        first_seen_at=now,
        last_seen_at=now,
    )


def evidence(owner):
    return JobListingEvidence.objects.create(
        listing=owner,
        source_url="https://example.org/jobs/" + str(owner.pk),
        source_relationship="official",
        observed_at=owner.first_seen_at,
        extraction_method="structured_text",
        extraction_identity="source-fixture",
        evidence_hash=hashlib.sha256(str(owner.pk).encode()).hexdigest(),
    )


def assignment_fields(owner, source):
    return {
        "job_listing": owner,
        "evidence": source,
        "category": EmploymentType.objects.get(code="full_time"),
        "reported_value": "Full time",
        "source_value_sha256": hashlib.sha256(b"Full time").hexdigest(),
        "normalizer_version_id": NORMALIZER_ID,
        "resolution_state": "resolved",
    }


def test_bulk_and_sql_writes_enforce_evidence_owner_and_resolution():
    first, second = listing("first"), listing("second")
    source = evidence(first)
    row = assignment_fields(first, source)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobEmploymentTypeAssignment.objects.bulk_create(
            [JobEmploymentTypeAssignment(**(row | {"job_listing": second}))]
        )
    stored = JobEmploymentTypeAssignment.objects.create(**row)
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE job_listing_evidence SET listing_id=%s WHERE id=%s",
            [second.pk, source.pk],
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        JobEmploymentTypeAssignment.objects.filter(pk=stored.pk).update(category=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobEmploymentTypeAssignment.objects.filter(pk=stored.pk).update(
            source_value_sha256="0" * 64
        )


def test_assignment_requires_normalizer_domain_and_null_provenance_is_unique():
    owner = listing("domain")
    other = DefinitionVersion.objects.create(
        definition_domain="taxonomy",
        definition_key="test_taxonomy",
        reported_version_token="v1",
        identity_sha256="9" * 64,
        provenance_state="identity_only",
    )
    row = assignment_fields(owner, None)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobEmploymentTypeAssignment.objects.create(
            **(row | {"normalizer_version_id": other.pk})
        )
    row["normalizer_version_id"] = None
    JobEmploymentTypeAssignment.objects.create(**row)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobEmploymentTypeAssignment.objects.create(**row)


def test_currency_registry_and_single_hq_are_real_references(company_country_catalogue):
    with pytest.raises(IntegrityError), transaction.atomic():
        Currency.objects.bulk_create([Currency(code="FAK")])
    with pytest.raises(IntegrityError), transaction.atomic():
        Currency.objects.filter(pk="USD").update(code="EUR")
    company = Company.objects.create(nickname="one-hq", hq_geolocation_id=company_country_catalogue["CN"])
    Company.objects.filter(pk=company.pk).update(hq_geolocation_id=company_country_catalogue["JP"])
    company.refresh_from_db()
    assert company.hq_geolocation_id == company_country_catalogue["JP"]
    assert Company.objects.filter(pk=company.pk).count() == 1


def test_unresolved_compensation_keeps_captured_source_and_identity():
    from core.geolocation_evidence import source_evidence, write_source_evidence

    source_record = {
        "salary_currency": "dollars (unspecified)",
        "salary_period": "per release",
    }
    owner = listing("unresolved-compensation")
    write_source_evidence(owner, raw_payload=source_record)
    owner.content_hash = "a" * 64
    for field, value in compensation_references(source_record).items():
        setattr(owner, field, value)
    owner.save()
    source = evidence(owner)
    write_source_evidence(source, raw_evidence={"record": source_record})
    write_job_classifications(
        owner, {"employment_type": ["Full-time", "Contract"]}, evidence=source
    )
    document = job_listing_document(owner.pk)
    owner.refresh_from_db()
    source.refresh_from_db()
    assert owner.salary_currency_reference_id is None
    assert owner.salary_period_reference_id is None
    assert owner.listing_identity == "unresolved-compensation"
    assert owner.content_hash == "a" * 64
    assert source_evidence(owner).raw_payload == source_record
    assert source_evidence(source).raw_evidence == {"record": source_record}
    assert document["compensation"]["currency"] is None
    assert document["compensation"]["period"] is None
    assert document["organization"]["employment_type"] == "Full-time · Contract"


def test_unresolved_assignment_can_be_removed_with_its_own_listing():
    owner = listing("owned-cleanup")
    owner_id = owner.pk
    source = evidence(owner)
    write_job_classifications(
        owner, {"employment_type": "Unusual source phrase"}, evidence=source
    )
    owner.delete()
    assert not JobListingEvidence.objects.filter(pk=source.pk).exists()
    assert not JobEmploymentTypeAssignment.objects.filter(
        job_listing_id=owner_id
    ).exists()
