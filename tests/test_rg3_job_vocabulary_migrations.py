"""Rehearse RG3 against populated pre-cutover tables in an isolated schema."""

import hashlib

import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0131_rg2_remove_legacy_locale_columns")
CUTOVER = ("core", "0133_rg3_cutover_job_and_hq_fields")
DELETED = ("core", "0134_rg3_remove_legacy_job_and_hq_columns")


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_cutover_and_deletion_keep_listings_sources_and_reject_unpreserved_values(
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

    # A late old-image value must have a retained meaning or exact source
    # evidence. A NULL replacement reference by itself is not preservation.
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE job_listings SET salary_currency=%s WHERE id=%s",
            ["ZZZ", job.pk],
        )
    with pytest.raises(RuntimeError, match="unpreserved salary_currency"):
        MigrationExecutor(connection).migrate([DELETED])
    with connection.cursor() as cursor:
        cursor.execute("SELECT salary_currency FROM job_listings WHERE id=%s", [job.pk])
        assert cursor.fetchone()[0] == "ZZZ"
    retained.raw_evidence["record"]["salary_currency"] = "ZZZ"
    retained.save(update_fields=["raw_evidence"])

    # Simulate a missing plural part only in the isolated rehearsal schema.
    # Keep the original plural phrase so the deletion check must notice it.
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE job_employment_type_assignments "
            "DISABLE TRIGGER pw_rg3_dimension_to_legacy"
        )
        cursor.execute(
            "DELETE FROM job_employment_type_assignments "
            "WHERE job_listing_id=%s AND reported_value='Contract'",
            [job.pk],
        )
        assert cursor.rowcount == 1
        cursor.execute(
            "ALTER TABLE job_employment_type_assignments "
            "ENABLE TRIGGER pw_rg3_dimension_to_legacy"
        )
        with pytest.raises(RuntimeError, match="unpreserved employment_type"):
            MigrationExecutor(connection).migrate([DELETED])
        transaction.set_rollback(True)

    assignments_before = list(
        employment.objects.filter(job_listing_id=job.pk).order_by("pk").values()
    )
    evidence_before = current.get_model("core", "JobListingEvidence").objects.get(
        pk=source.pk
    )
    MigrationExecutor(connection).migrate([DELETED])
    with connection.cursor() as cursor:
        columns = {
            item.name
            for item in connection.introspection.get_table_description(
                cursor, "job_listings"
            )
        }
        assert not columns & {
            "salary_currency",
            "salary_period",
            "job_function",
            "seniority",
            "employment_type",
            "workplace_type",
            "organization_ai_relationship",
            "role_ai_relationship",
        }
        company_columns = {
            item.name
            for item in connection.introspection.get_table_description(
                cursor, "companies"
            )
        }
        assert "hq_country" not in company_columns
        cursor.execute(
            "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "WHERE NOT t.tgisinternal AND t.tgname LIKE 'pw_rg3_%' "
            "AND c.relnamespace=current_schema()::regnamespace"
        )
        triggers = [row[0] for row in cursor.fetchall()]
        assert triggers.count("pw_rg3_catalogue_identity") == 8
        assert triggers.count("pw_rg3_assignment_guard") == 6
        assert len(triggers) == 14
        cursor.execute(
            "SELECT proname FROM pg_proc WHERE pronamespace=current_schema()::regnamespace "
            "AND proname LIKE 'pw_rg3_%'"
        )
        assert {row[0] for row in cursor.fetchall()} == {
            "pw_rg3_catalogue_identity",
            "pw_rg3_assignment_guard",
        }
    assert (
        list(employment.objects.filter(job_listing_id=job.pk).order_by("pk").values())
        == assignments_before
    )
    after = current.get_model("core", "JobListing").objects.get(pk=job.pk)
    source_after = current.get_model("core", "JobListingEvidence").objects.get(
        pk=source.pk
    )
    assert after.listing_identity == "c" * 64 and after.content_hash == "d" * 64
    assert after.raw_payload == raw
    assert after.salary_currency_reference_id is None
    assert source_after.raw_evidence == evidence_before.raw_evidence
    assert source_after.source_url == "https://example.org/jobs/one"
    assert source_after.evidence_hash == "e" * 64
    assert source_after.evidence_text == "The original job listing"
    # New code continues to write both reference and assignment owners after
    # every temporary trigger/function and old column has gone.
    after.salary_currency_reference_id = "JPY"
    after.save(update_fields=["salary_currency_reference"])
    category = current.get_model("core", "EmploymentType").objects.get(code="part_time")
    employment.objects.create(
        job_listing_id=job.pk,
        category=category,
        reported_value="Part-time",
        source_value_sha256=hashlib.sha256(b"Part-time").hexdigest(),
        resolution_state="resolved",
        evidence_id=source.pk,
    )
    after.refresh_from_db()
    assert after.salary_currency_reference_id == "JPY"
    assert employment.objects.filter(job_listing_id=job.pk, category=category).exists()
