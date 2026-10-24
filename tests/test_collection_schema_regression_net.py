"""Exactly one table, safe rollback boundaries, and a complete column reference."""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.usefixtures("isolated_migration_database")
def test_one_table_delta_preserves_legacy_numeric_rows_and_refuses_evidence_loss():
    executor = MigrationExecutor(connection)
    executor.migrate([("core", "0080_collection_schema")])
    before = executor.loader.project_state([("core", "0080_collection_schema")]).apps
    before_tables = {
        m._meta.db_table
        for m in before.get_app_config("core").get_models()
        if m._meta.managed and not m._meta.proxy
    }
    executor = MigrationExecutor(connection)
    executor.migrate([("core", "0082_collection_catalog_mappings")])
    after = executor.loader.project_state(
        [("core", "0082_collection_catalog_mappings")]
    ).apps
    after_tables = {
        m._meta.db_table
        for m in after.get_app_config("core").get_models()
        if m._meta.managed and not m._meta.proxy
    }
    assert after_tables - before_tables == {"collection_jobs"}
    assert not before_tables - after_tables
    source = after.get_model("core", "DataSource").objects.get(pk="hf")
    job = after.get_model("core", "CollectionJob").objects.create(
        job_key="guard-proof",
        source=source,
        purpose="catalog",
        operation="hf_catalog",
        mode="manual",
        definition={},
        definition_sha256="a" * 64,
    )
    with pytest.raises(RuntimeError, match="preserve.*0081"):
        MigrationExecutor(connection).migrate([("core", "0080_collection_schema")])
    assert after.get_model("core", "CollectionJob").objects.filter(pk=job.pk).exists()


def test_reference_inventory_and_columns_match_all_concrete_application_tables():
    from core.geolocation_evidence import PROJECTIONS

    doc = (
        Path(__file__).resolve().parents[1] / "docs/reference/db-schema.md"
    ).read_text()
    models = [
        m
        for m in apps.get_app_config("core").get_models()
        if m._meta.managed and not m._meta.proxy
    ]
    # Explicit rolling-release inventory. Remove these entries only with the
    # corresponding physical deletion migration; never accept arbitrary drift.
    retained_tables = {"countries", "regions", "country_labels", "region_labels", "country_codes_region"}
    compatibility_columns = {
        "account_based_in_mappings": {"country_code", "region_key"},
        "account_profile_snapshots": {"location"},
        "accounts": {"based_in_region_key", "country_code", "location"},
        "companies": {"hq_country_id"},
        "event_dossier_claims": {"claim_kind", "event_timezone"},
        "event_dossiers": {"event_kind"},
        "job_listings": {"locations", "locations_raw"},
        "model_release_details": {"availability_state", "disclosure_state_id", "release_channel"},
        "model_releases": {"release_channel"},
        "opportunities": {"opportunity_type"},
        "people": {"nationality"},
        "people_brand_affiliations": {"affiliation_type", "location"},
        "people_names": {"name_type_id"},
        "person_citizenships": {"country_code"},
        "personnel_change_details": {"change_kind"},
        "posts": {"author_location"},
        "x_account_details": {"account_based_in"},
    }
    expected = {m._meta.db_table for m in models} | retained_tables
    headings = re.findall(r"^### `([^`]+)` —", doc, re.MULTILINE)
    assert set(headings) == expected and len(headings) == len(expected)
    inventory = re.findall(r"^\| \[([^]]+)\]\(#table-[^)]+\) \|", doc, re.MULTILINE)
    assert set(inventory) == expected and len(inventory) == len(expected)
    canonical = {model._meta.db_table: model for model in models}
    retained = MigrationExecutor(connection).loader.project_state([
        ("core", "0156_rg4_unknown_job_location_observations")
    ]).apps
    canonical.update({model._meta.db_table: model for model in retained.get_app_config("core").get_models()
                      if model._meta.db_table in retained_tables})
    for table, model in canonical.items():
        section = doc.split(f"### `{table}` —", 1)[1].split(
            "[Back to table inventory]", 1
        )[0]
        columns = re.findall(r"^\| `([^`]+)` \|", section, re.MULTILINE)
        orm_columns = {f.column for f in model._meta.local_fields if f.concrete}
        projection = PROJECTIONS.get(table)
        source_columns = {f.column for f in projection._meta.local_concrete_fields} if projection else set()
        expected_columns = orm_columns | source_columns | compatibility_columns.get(table, set())
        with connection.cursor() as cursor:
            physical_columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, table
                )
            }
        assert physical_columns == expected_columns, table
        assert set(columns) == expected_columns and len(columns) == len(expected_columns), table


@pytest.mark.usefixtures("isolated_migration_database")
def test_catalog_mapping_reverse_refuses_without_erasing_identity_evidence():
    executor = MigrationExecutor(connection)
    # The old 0082 rollback guard predates forward-only 0089; exercise that
    # historical boundary without first crossing the new cutover migration.
    executor.migrate([("core", "0088_archive_run_instructions")])
    from tests.test_collection_identity import admit, identities

    _, _, subject, repo = identities()
    mapping = admit(subject, repo)
    with pytest.raises(RuntimeError, match="preserve.*0082"):
        MigrationExecutor(connection).migrate([("core", "0081_collection_jobs")])
    mapping.refresh_from_db()
    assert mapping.contract_id is None and mapping.purpose == "catalog"
