"""Rehearse the populated merge and restore, including overlapping identities."""

import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BEFORE = [("core", "0079_original_content_physical_names")]
AFTER = [("core", "0080_collection_schema")]


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def oid(table):
    with connection.cursor() as cursor:
        cursor.execute("SELECT %s::regclass::oid", [table])
        return cursor.fetchone()[0]


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.parametrize("consumed_sequence", [None, 100])
def test_populated_merge_restore_and_replay_preserve_history_and_references(
    consumed_sequence,
):
    old = migrate(BEFORE)
    Source = old.get_model("core", "DataSource")
    source = Source.objects.get(pk="hf")
    taxonomy = old.get_model("core", "TaxonomyVersion").objects.create(
        version_hash="a" * 64, snapshot={}, reviewed_by="test"
    )
    contract = old.get_model("core", "MetricCollectionContract").objects.create(
        taxonomy_version=taxonomy,
        contract_hash="b" * 64,
        catalog_hash="c" * 64,
        mapping_hash="d" * 64,
        methodology_hash="e" * 64,
        catalog_snapshot={},
        source_configuration={},
        methodology={},
        reviewed_by="test",
    )
    kind = old.get_model("core", "MetricType").objects.create(
        id="fixture", name="Fixture"
    )
    definition = old.get_model("core", "SourceMetric").objects.create(
        source=source,
        metric_type=kind,
        metric_key="fixture",
        version=1,
        name="Fixture",
        unit="count",
        value_kind="integer",
        quantity_form="count",
        measurement_kind="state",
    )
    run_id = uuid.uuid4()
    timestamp = timezone.now().replace(microsecond=123456)
    numeric = old.get_model("core", "MetricCollectionRun").objects.create(
        id=run_id,
        contract=contract,
        source=source,
        ingestion_key="f" * 64,
        lease_expires_at=timestamp,
        started_at=timestamp,
        status="partial",
        completed_at=timestamp,
        raw_payload={"keep": [False, 0]},
        source_metadata={"revision": "original"},
    )
    numeric_obs = old.get_model("core", "MetricObservation").objects.create(
        id=1,
        run=numeric,
        source_identifier="publisher/model",
        source_subject_kind="repository",
        observation_key="1" * 64,
        observed_at=timestamp,
        source_metadata={"native": {"sha": "abc"}},
    )
    value = old.get_model("core", "MetricValue").objects.create(
        observation=numeric_obs, source_metric=definition, integer_value=Decimal(42)
    )
    catalog = old.get_model("core", "HFModelCatalogRun").objects.create(
        id=run_id,
        scope={"namespaces": ["publisher"]},
        outcome="partial",
        invocations=[{"requests": 3}],
        report={"coverage": "partial"},
    )
    old.get_model("core", "HFModelCatalogRun").objects.filter(pk=run_id).update(
        started_at=timestamp, updated_at=timestamp
    )
    scope = old.get_model("core", "HFModelCatalogNamespaceRun").objects.create(
        run=catalog,
        namespace="publisher",
        ownership={"brand": "fixture"},
        cursor="next",
        cursor_history=[{"page": 1}],
        raw_count=1,
    )
    product = old.get_model("core", "Product").objects.create(
        repo_id="publisher/model",
        display_name="Curated",
        hf_metadata={
            "field_sources": {
                "sha": {
                    "observation": {"id": 1, "run_id": str(run_id)},
                    "group": "detail",
                }
            }
        },
    )
    old.get_model("core", "HFModelCatalogObservation").objects.create(
        id=1,
        namespace_run=scope,
        repo_key="publisher/model",
        repo_id="publisher/Model",
        product=product,
        listing={"downloads": 0},
        envelopes=[{"sha": "abc"}],
        groups={"detail": {"status": "ok", "payload": {"future": False}}},
        outcome="partial",
        created_product=True,
    )
    old.get_model("core", "HFModelCatalogObservation").objects.filter(pk=1).update(
        observed_at=timestamp, updated_at=timestamp
    )
    old.get_model("core", "HFModelCatalogObservation").objects.create(
        id=5,
        namespace_run=scope,
        repo_key="publisher/sparse",
        repo_id="publisher/sparse",
    )
    original_oids = [
        oid(t)
        for t in (
            "metric_collection_runs",
            "metric_observations",
            "hf_model_catalog_namespace_runs",
        )
    ]
    if consumed_sequence:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('metric_observations', 'id'), %s, true)",
                [consumed_sequence],
            )
    import psycopg

    with (
        psycopg.connect(
            dbname=connection.settings_dict["NAME"],
            host=connection.settings_dict["HOST"],
            port=connection.settings_dict["PORT"],
            user=connection.settings_dict["USER"],
            password=connection.settings_dict["PASSWORD"],
        ) as blocker,
        blocker.cursor() as cursor,
    ):
        cursor.execute("SELECT pg_advisory_lock(6842060924)")
        with pytest.raises(RuntimeError, match="active HF catalog"):
            migrate(AFTER)
        assert oid("metric_observations") == original_oids[1]
    new = migrate(AFTER)
    assert [
        oid(t)
        for t in ("collection_runs", "collection_observations", "collection_scope_runs")
    ] == original_oids
    Run = new.get_model("core", "CollectionRun")
    Observation = new.get_model("core", "CollectionObservation")
    imported_run = Run.objects.get(purpose="catalog")
    # Runtime consumers target the current schema; historical models above
    # still characterize 0080 and the legacy writable aliases below.
    migrate([("core", "0082_collection_catalog_mappings")])
    from core.hf_catalog import resolve_catalog_run

    assert resolve_catalog_run(run_id).pk == imported_run.pk
    assert imported_run.pk != run_id
    assert imported_run.started_at == imported_run.updated_at == timestamp
    assert imported_run.scope == catalog.scope
    assert imported_run.invocations == catalog.invocations
    imported = Observation.objects.get(run=imported_run, resource_key="publisher/model")
    assert imported.pk > numeric_obs.pk
    if consumed_sequence:
        assert imported.pk > consumed_sequence
    assert imported.observed_at == imported.updated_at == timestamp
    assert imported.groups == {"detail": {"status": "ok", "payload": {"future": False}}}
    assert imported.envelopes == [{"sha": "abc"}]
    assert imported.listing == {"downloads": 0} and imported.created_product
    assert (
        new.get_model("core", "MetricValue").objects.get(pk=value.pk).observation_id
        == 1
    )
    pointer = (
        new.get_model("core", "Product")
        .objects.get(pk=product.pk)
        .hf_metadata["field_sources"]["sha"]["observation"]
    )
    assert pointer == {"id": imported.pk, "run_id": str(imported_run.pk)}
    assert (
        new.get_model("core", "CollectionScopeRun").objects.get(pk=scope.pk).cursor
        == "next"
    )
    # Old numeric readers/writers continue to use the same physical rows.
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metric_observations SET source_metadata = source_metadata WHERE id = 1 RETURNING id"
        )
        assert cursor.fetchone() == (1,)
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence('collection_observations', 'id'))"
        )
        assert cursor.fetchone()[0] > imported.pk
        cursor.execute("SELECT count(*) FROM metric_collection_runs")
        assert cursor.fetchone() == (1,)
        cursor.execute("SELECT count(*) FROM metric_observations")
        assert cursor.fetchone() == (1,)
    old_writer = old.get_model("core", "MetricCollectionRun").objects.create(
        contract=contract,
        source=source,
        ingestion_key="4" * 64,
        lease_expires_at=timestamp,
    )
    old.get_model("core", "MetricObservation").objects.create(
        run=old_writer,
        source_identifier="legacy-process",
        source_subject_kind="repository",
        observation_key="5" * 64,
    )
    # A new post-migration record must also survive restore; it has no legacy ID.
    new_run = Run.objects.create(
        source_id=source.pk, purpose="catalog", status="pending", ingestion_key="2" * 64
    )
    new_scope = new.get_model("core", "CollectionScopeRun").objects.create(
        run=new_run, scope_key="new", ownership={}
    )
    later = Observation.objects.create(
        run=new_run,
        scope_run=new_scope,
        resource_key="new/repo",
        source_identifier="new/repo",
        source_subject_kind="repository",
        observation_key="3" * 64,
        processing_outcome="pending",
    )
    restored = migrate(BEFORE)
    assert oid("metric_observations") == original_oids[1]
    restored_obs = restored.get_model("core", "HFModelCatalogObservation").objects.get(
        pk=1
    )
    assert restored_obs.groups == imported.groups
    assert restored_obs.updated_at == timestamp
    assert (
        restored.get_model("core", "HFModelCatalogObservation")
        .objects.filter(repo_id="new/repo")
        .exists()
    )
    restored_product = restored.get_model("core", "Product").objects.get(pk=product.pk)
    assert restored_product.hf_metadata["field_sources"]["sha"]["observation"] == {
        "id": 1,
        "run_id": str(run_id),
    }
    assert (
        restored.get_model("core", "MetricValue").objects.get(pk=value.pk).integer_value
        == 42
    )
    replay = migrate(AFTER)
    assert replay.get_model("core", "CollectionRun").objects.get(
        pk=run_id
    ).raw_payload == {"keep": [False, 0]}
    assert (
        replay.get_model("core", "CollectionObservation")
        .objects.filter(source_identifier=later.source_identifier)
        .exists()
    )
