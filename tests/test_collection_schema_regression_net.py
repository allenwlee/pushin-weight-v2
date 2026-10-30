"""Verify collection rollback boundaries and the physical application schema."""

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


def test_concrete_application_models_match_database_columns():
    from core.geolocation_evidence import PROJECTIONS

    models = [
        m
        for m in apps.get_app_config("core").get_models()
        if m._meta.managed and not m._meta.proxy
    ]
    canonical = {model._meta.db_table: model for model in models}
    for table, model in canonical.items():
        orm_columns = {f.column for f in model._meta.local_fields if f.concrete}
        projection = PROJECTIONS.get(table)
        source_columns = {f.column for f in projection._meta.local_concrete_fields} if projection else set()
        expected_columns = orm_columns | source_columns
        with connection.cursor() as cursor:
            physical_columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, table
                )
            }
        assert physical_columns == expected_columns, table


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
