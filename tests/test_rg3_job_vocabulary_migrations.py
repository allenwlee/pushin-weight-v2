"""Rehearse RG3 against populated pre-cutover tables in an isolated schema."""

import hashlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0131_rg2_remove_legacy_locale_columns")
CUTOVER = ("core", "0133_rg3_cutover_job_and_hq_fields")


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_cutover_keeps_listing_source_and_legacy_writer_coverage(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([BASE]).apps
    old.get_model("core", "Brand").objects.create(
        nickname="rg3-source", display_name="RG3 source"
    )
    company = old.get_model("core", "Company").objects.create(
        nickname="rg3-hq", hq_country="CN"
    )
    raw = {
        "salary_currency": "USD",
        "salary_period": "yearly",
        "employment_type": "Full-time/Contract",
    }
    now = timezone.now()
    job = old.get_model("core", "JobListing").objects.create(
        brand_id="rg3-source",
        hiring_organization="RG3 source",
        title="Engineer",
        job_function="{'name': '其它'}",
        employment_type=raw["employment_type"],
        workplace_type="Remote",
        role_ai_relationship="Builds systems used by AI researchers",
        salary_currency="USD",
        salary_period="yearly",
        salary_min=100,
        listing_identity="c" * 64,
        content_hash="d" * 64,
        raw_payload=raw,
        first_seen_at=now,
        last_seen_at=now,
    )
    source = old.get_model("core", "JobListingEvidence").objects.create(
        listing=job,
        source_url="https://example.org/jobs/one",
        source_relationship="official",
        evidence_text="The original job listing",
        raw_evidence={"record": raw},
        observed_at=now,
        extraction_method="structured_text",
        extraction_identity="source-v1",
        evidence_hash="e" * 64,
    )
    MigrationExecutor(connection).migrate([CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([CUTOVER]).apps
    migrated = current.get_model("core", "JobListing").objects.get(pk=job.pk)
    retained = current.get_model("core", "JobListingEvidence").objects.get(pk=source.pk)
    assert migrated.listing_identity == "c" * 64
    assert migrated.content_hash == "d" * 64
    assert migrated.raw_payload == raw
    assert retained.raw_evidence == {"record": raw}
    assert retained.evidence_text == "The original job listing"
    assert migrated.salary_currency_reference_id == "USD"
    assert migrated.salary_period_reference.code == "year"
    assert (
        current.get_model("core", "Company")
        .objects.get(pk=company.pk)
        .hq_country_reference_id
        == "CN"
    )
    employment = current.get_model("core", "JobEmploymentTypeAssignment")
    assert set(
        employment.objects.filter(job_listing_id=job.pk).values_list(
            "category__code", flat=True
        )
    ) == {"full_time", "contract"}
    unknown = current.get_model("core", "JobFunctionAssignment").objects.get(
        job_listing_id=job.pk
    )
    assert unknown.reported_value == "{'name': '其它'}"
    assert unknown.category_id is None
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE job_listings SET workplace_type=%s WHERE id=%s",
            ["new old-image wording", job.pk],
        )
    bridged = current.get_model("core", "JobWorkplaceTypeAssignment").objects.get(
        job_listing_id=job.pk
    )
    assert bridged.reported_value == "new old-image wording"
    assert bridged.normalizer_version_id is None
    assert (
        bridged.source_value_sha256
        == hashlib.sha256(b"new old-image wording").hexdigest()
    )
    assert retained.pk == source.pk
