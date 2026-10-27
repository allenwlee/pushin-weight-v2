"""Rehearse the frozen RG6 operations in the shared DB's disposable schema.

The helper is tested before the 0201 migration file is added, so the permanent
public schema/ledger do not need to advance merely to test physical retirement.
"""

import hashlib
import uuid
from contextlib import contextmanager

import psycopg
import pytest
from django.db import IntegrityError, OperationalError, connection, transaction
from psycopg import sql

from core.migrations._rg6_retirement_v1 import (
    ALIASES,
    FIELDS,
    PREDICATES,
    _predicate,
    alias_query,
    prepare_retirement,
    remove_storage,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0200_merge_rg6_enrichment_budget_contract")


def test_index_predicate_comparison_never_changes_quoted_marker_values():
    expected = PREDICATES["uq_source_statistics_typed"]
    assert _predicate("((projection_kind)::text = 'source-statistics-v1'::text)") == _predicate(expected)
    for marker in ("source-(statistics)-v1", "source- statistics-v1", "source-statistics-v1::text"):
        assert _predicate(f"projection_kind='{marker}'") != _predicate(expected)


def columns():
    with connection.cursor() as cursor:
        cursor.execute("""SELECT c.relname,a.attname FROM pg_class c
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE c.relnamespace=current_schema()::regnamespace AND c.relkind='r'
                AND a.attnum>0 AND NOT a.attisdropped""")
        return set(cursor.fetchall())


@contextmanager
def authorization(value="0201"):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('pushinweight.rg6_retirement_ready',true)")
        before = cursor.fetchone()[0] or ""
        cursor.execute("SELECT set_config('pushinweight.rg6_retirement_ready',%s,false)", [value])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('pushinweight.rg6_retirement_ready',%s,false)", [before])


def retire():
    # This is the 0201 migration's exact non-atomic preflight / atomic DDL split.
    with connection.schema_editor(atomic=False) as editor:
        prepare_retirement(None, editor)
        with transaction.atomic():
            remove_storage(None, editor)


def populated():
    from core.benchmark_metric_store import persist_source
    from core.models import CollectionEvidenceArchive
    from tests.test_benchmark_download_persistence import configured, payload

    run = persist_source(configured(), "hf", "6" * 64, payload(),
                         source_metadata={"retained_source": "原文"})
    observation = run.observations.first()
    scope = run.scopes.first()
    archives = {}
    # Every retired field carries a distinct value. No provider calls are made.
    with connection.cursor() as cursor:
        for table, key in (("collection_runs", run.pk), ("collection_scope_runs", scope.pk),
                           ("collection_observations", observation.pk)):
            for field in FIELDS[table]:
                cursor.execute(f"UPDATE {table} SET {field}=jsonb_build_object('field',%s::text,'evidence','原文') WHERE id=%s", [field, key])
            pairs = ",".join(f"'{field}',{field}" for field in FIELDS[table])
            cursor.execute(f"SELECT convert_to(jsonb_build_object({pairs})::text,'UTF8') FROM {table} WHERE id=%s", [key])
            body = bytes(cursor.fetchone()[0])
            archive = CollectionEvidenceArchive.objects.create(
                content_sha256=hashlib.sha256(body).hexdigest(), encoding="legacy-jsonb-text-v1",
                media_type="application/json", byte_count=len(body), body=body,
                capture_kind="legacy_collection",
            )
            cursor.execute(f"UPDATE {table} SET legacy_archive_id=%s WHERE id=%s", [archive.pk, key])
            archives[archive.pk] = body
    return run, observation, scope, archives


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_populated_drop_preserves_evidence_alias_grants_and_typed_uniqueness(migration_rehearsal_schema):
    from core.models import (
        CollectionEvidenceArchive,
        CollectionObservation,
        MetricValue,
    )

    run, observation, _scope, archives = populated()
    before = columns()
    value_ids = set(MetricValue.objects.values_list("pk", flat=True))
    reader, default_reader = ("rg6_reader_" + uuid.uuid4().hex[:16] for _ in range(2))
    with connection.cursor() as cursor:
        for role in (reader, default_reader):
            cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("GRANT SELECT ON metric_collection_runs TO {} WITH GRANT OPTION").format(sql.Identifier(reader)))
        cursor.execute(sql.SQL("GRANT SELECT(id), UPDATE(status), SELECT(source_metadata) ON metric_observations TO {}").format(sql.Identifier(reader)))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(sql.Identifier(migration_rehearsal_schema), sql.Identifier(default_reader)))
        cursor.execute("COMMENT ON VIEW metric_collection_runs IS 'Retain reviewed metric alias'")
        cursor.execute("SELECT source_metadata_archive_id FROM collection_runs WHERE id=%s", [run.pk])
        metadata_archive = cursor.fetchone()[0]
        assert metadata_archive is not None
    try:
        with authorization():
            retire()
        assert columns() == before - {(table, field) for table, fields in FIELDS.items() for field in fields}
        assert set(MetricValue.objects.values_list("pk", flat=True)) == value_ids
        assert {key: bytes(CollectionEvidenceArchive.objects.get(pk=key).body) for key in archives} == archives
        with connection.cursor() as cursor:
            cursor.execute("SELECT source_metadata_archive_id FROM collection_runs WHERE id=%s", [run.pk])
            assert cursor.fetchone() == (metadata_archive,)
            cursor.execute("SELECT count(*) FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey) WHERE c.conrelid='collection_runs'::regclass AND c.contype='f' AND a.attname='source_metadata_archive_id' AND c.convalidated")
            assert cursor.fetchone() == (1,)
            for name in ALIASES:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position", [name])
                table, old_columns = ALIASES[name]
                assert [row[0] for row in cursor.fetchall()] == [column for column in old_columns if column not in FIELDS[table]]
                cursor.execute(f"SELECT id FROM {name} WHERE id=%s", [run.pk if table == "collection_runs" else observation.pk])
                assert cursor.fetchone() is not None
                cursor.execute("SELECT has_table_privilege(%s,%s,'SELECT')", [default_reader, name])
                assert cursor.fetchone() == (False,)
            cursor.execute("SELECT has_table_privilege(%s,'metric_collection_runs','SELECT WITH GRANT OPTION')", [reader])
            assert cursor.fetchone() == (True,)
            cursor.execute("SELECT has_column_privilege(%s,'metric_observations','status','UPDATE'),has_column_privilege(%s,'metric_observations','id','SELECT'),has_table_privilege(%s,'metric_observations','SELECT')", [reader, reader, reader])
            assert cursor.fetchone() == (True, True, False)
            cursor.execute("SELECT obj_description('metric_collection_runs'::regclass,'pg_class')")
            assert cursor.fetchone() == ("Retain reviewed metric alias",)
            cursor.execute("SELECT to_regclass('uq_source_statistics_snapshot'),to_regclass('uq_source_statistics_crossformat')")
            assert cursor.fetchone() == (None, None)
        # Exercise the real writer with physical absence, then prove uniqueness
        # across runs so the older per-run constraint cannot mask this guard.
        from core.benchmark_metric_store import persist_source
        from tests.test_benchmark_download_persistence import payload

        second = persist_source(run.job.contract, "hf", "7" * 64, payload())
        another = second.observations.first()
        CollectionObservation.objects.filter(pk=observation.pk).update(projection_kind="source-statistics-v1")
        with pytest.raises(IntegrityError) as caught, transaction.atomic():
            CollectionObservation.objects.filter(pk=another.pk).update(
                observation_key=observation.observation_key,
                projection_kind="source-statistics-v1",
            )
        assert caught.value.__cause__.diag.constraint_name == "uq_source_statistics_typed"
    finally:
        with connection.cursor() as cursor:
            for role in (reader, default_reader):
                cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
@pytest.mark.parametrize("fault", ["gate", "stale_gate", "archive", "dependency", "index", "alias", "rule", "statistics"])
def test_unready_retirement_refuses_without_partial_deletion(migration_rehearsal_schema, fault):
    run, _observation, _scope, _archives = populated()
    before = columns()
    with connection.cursor() as cursor:
        if fault == "archive":
            cursor.execute("UPDATE collection_runs SET legacy_archive_id=NULL WHERE id=%s", [run.pk])
        elif fault == "dependency":
            cursor.execute("CREATE VIEW unreviewed_rg6_consumer AS SELECT report FROM collection_runs")
        elif fault == "index":
            cursor.execute("DROP INDEX uq_source_statistics_typed")
            cursor.execute("CREATE UNIQUE INDEX uq_source_statistics_typed ON collection_observations(observation_key) WHERE projection_kind='wrong'")
        elif fault == "alias":
            cursor.execute("CREATE OR REPLACE VIEW metric_observations AS " + alias_query("metric_observations", retired=False).replace("='metric'", "='catalog'") + " WITH LOCAL CHECK OPTION")
        elif fault == "rule":
            cursor.execute("CREATE RULE unreviewed_alias_rule AS ON UPDATE TO metric_collection_runs DO ALSO UPDATE collection_runs SET report=report WHERE false")
        elif fault == "statistics":
            cursor.execute("UPDATE collection_observations SET source_metadata='{}'::jsonb || jsonb_build_object('projection_kind','source-statistics-v1'),projection_kind=NULL WHERE run_id=%s", [run.pk])
    expected = {"gate": "explicit connection authorization", "stale_gate": "explicit connection authorization",
                "archive": "Unarchived RG6",
                "dependency": "Unreviewed RG6 dependency", "index": "Unready RG6 statistics index",
                "alias": "Unreviewed RG6 compatibility view", "rule": "Unreviewed RG6 dependency",
                "statistics": "legacy statistics lack the typed uniqueness owner"}[fault]
    gate = {"gate": "0200", "stale_gate": "0199"}.get(fault, "0201")
    with authorization(gate), pytest.raises(RuntimeError, match=expected):
        retire()
    assert columns() == before
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('metric_collection_runs'),to_regclass('metric_observations')")
        assert all(cursor.fetchone())


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_writer_lock_rolls_back_alias_drop_and_can_retry(migration_rehearsal_schema):
    populated()
    before = columns()
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        path = cursor.fetchone()[0]
        cursor.execute("SHOW lock_timeout")
        previous_timeout = cursor.fetchone()[0]
        cursor.execute("SELECT pg_get_viewdef('metric_collection_runs'::regclass)")
        view_before = cursor.fetchone()
    with psycopg.connect(**connection.get_connection_params()) as writer, authorization():
        writer.execute("SELECT set_config('search_path',%s,false)", [path])
        writer.execute("LOCK TABLE collection_runs IN ROW EXCLUSIVE MODE")
        with pytest.raises(OperationalError) as caught:
            retire()
        assert caught.value.__cause__.sqlstate == "55P03"
        assert columns() == before
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_viewdef('metric_collection_runs'::regclass)")
            assert cursor.fetchone() == view_before
            cursor.execute("SHOW lock_timeout")
            assert cursor.fetchone() == (previous_timeout,)
        writer.rollback()
        retire()
    assert all((table, field) not in columns() for table, fields in FIELDS.items() for field in fields)


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_empty_install_needs_no_populated_authorization(migration_rehearsal_schema):
    with authorization(""):
        retire()
    assert all((table, field) not in columns() for table, fields in FIELDS.items() for field in fields)


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_fresh_typed_records_need_no_archive_of_empty_compatibility_defaults(migration_rehearsal_schema):
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_persistence import configured, payload

    run = persist_source(configured(), "hf", "8" * 64, payload())
    assert run.legacy_archive_id is None
    observation = run.observations.first()
    assert observation.legacy_archive_id is None
    with authorization(""), pytest.raises(RuntimeError, match="explicit connection authorization"):
        retire()
    with authorization():
        retire()
    observation.refresh_from_db()
    assert observation.values.exists()
