"""Measurement FK cutover preserves public timing, immutable history and retries."""

import importlib
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.measurement_taxonomy import digest
from core.models import Actor, CollectionCorrection, MetricValue, TimeZone
from tests.collection_fixtures import evidence_job
from tests.test_source_metric_projection import configured

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.requires_postgres,
    pytest.mark.parametrize(
        "migration_rehearsal_schema",
        [("core", "0166_rg5_reference_source_guards")],
        indirect=True,
    ),
]


@pytest.fixture(autouse=True)
def pre_retirement_schema(migration_rehearsal_schema):
    """Bridge behavior belongs to the historical cutover schema."""
    return migration_rehearsal_schema


def measurement():
    TimeZone.objects.get_or_create(pk="UTC")
    contract, _, _, _ = configured()
    historical = MigrationExecutor(connection).loader.project_state(
        [("core", "0166_rg5_reference_source_guards")]
    ).apps
    job = evidence_job(source_id="hf", purpose="metric", contract_id=contract.pk)
    run = historical.get_model("core", "CollectionRun").objects.create(
        job_id=job.pk, ingestion_key=digest("rg5-timezone-fixture"),
        status="success", completed_at=timezone.now(), lease_expires_at=timezone.now(),
    )
    observation = historical.get_model("core", "CollectionObservation").objects.create(
        run_id=run.pk, source_identifier="lab/Model", source_subject_kind="repository",
        observation_key=digest("rg5-timezone-measurement"),
    )
    return MetricValue.objects.create(
        observation_id=observation.pk,
        source_metric_id=contract.source_configuration["hf"]["definitions"][0]["id"],
        integer_value=1,
    )


def remap():
    migration = importlib.import_module(
        "core.migrations.0162_rg5_measurement_timezone_references"
    )
    with connection.schema_editor(atomic=False) as editor:
        migration.expand_and_map(None, editor)


def test_metric_timezone_old_and_new_writers_share_reference_and_unknown():
    value = measurement()
    assert "source_timezone" not in {f.name for f in MetricValue._meta.fields}
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metric_values SET source_timezone='UTC' WHERE id=%s", [value.pk]
        )
    value.refresh_from_db()
    assert value.source_timezone_reference_id == "UTC"
    MetricValue.objects.filter(pk=value.pk).update(source_timezone_reference_id=None)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_timezone FROM metric_values WHERE id=%s", [value.pk]
        )
        assert cursor.fetchone() == ("unknown",)
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metric_values SET source_timezone='invented-zone' WHERE id=%s",
            [value.pk],
        )
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_timezone_copy_resumes_without_overwriting_canonical_updates():
    value = measurement()
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute(
            "ALTER TABLE metric_values DISABLE TRIGGER pw_rg5_source_timezone_bridge"
        )
        cursor.execute(
            "UPDATE metric_values SET source_timezone='UTC',source_timezone_id=NULL WHERE id=%s",
            [value.pk],
        )
        cursor.execute(
            "ALTER TABLE metric_values ENABLE TRIGGER pw_rg5_source_timezone_bridge"
        )
    remap()
    value.refresh_from_db()
    assert value.source_timezone_reference_id == "UTC"
    MetricValue.objects.filter(pk=value.pk).update(source_timezone_reference_id=None)
    remap()
    value.refresh_from_db()
    assert value.source_timezone_reference_id is None


def test_correction_keeps_original_fingerprint_and_guard_after_timezone_mapping():
    value = measurement()
    before = {"temporal_status": "unknown", "source_timezone": "unknown"}
    after = {"temporal_status": "unknown", "source_timezone": "UTC"}
    from core.collection_corrections import TIME_BASIS_FIELDS, TIME_STATE_FIELDS

    serialized = {
        f"{side}_{name}": state.get(name)
        for side, state in (("before", before), ("after", after))
        for name in (*TIME_STATE_FIELDS, *TIME_BASIS_FIELDS)
    }
    key = digest(
        {
            "value": value.pk,
            "predecessor": None,
            "policy": "fixture-v1",
            "reason": "fixture",
            "fields": serialized,
        }
    )
    identity = uuid.uuid5(
        uuid.NAMESPACE_URL, "pushinweight:timing-correction:" + key
    )
    # Seed the exact pre-RG6 owner shape. Current application writers are tested
    # on the current schema; this fixture tests the old migration and guard.
    actor = Actor.objects.create(actor_kind="system", actor_key="rg5-timezone-fixture")
    fields = dict(serialized)
    for side in ("before", "after"):
        zone = fields.pop(side + "_source_timezone")
        fields[side + "_source_timezone_reference_id"] = None if zone == "unknown" else zone
    correction = CollectionCorrection.objects.create(
        id=identity, observation_id=value.observation_id, metric_value=value,
        correction_kind="timing", policy_version="fixture-v1", actor=actor,
        reason_code="fixture", recorded_at=timezone.now(), recorded_at_precision="instant",
        **fields,
    )
    assert correction.before_source_timezone_reference_id is None
    assert correction.after_source_timezone_reference_id == "UTC"
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute(
            "ALTER TABLE collection_corrections DISABLE TRIGGER collection_correction_guard"
        )
        cursor.execute(
            "ALTER TABLE collection_corrections DISABLE TRIGGER pw_rg5_after_source_timezone_bridge"
        )
        cursor.execute(
            "UPDATE collection_corrections SET after_source_timezone_id=NULL WHERE id=%s",
            [correction.pk],
        )
        cursor.execute(
            "ALTER TABLE collection_corrections ENABLE TRIGGER pw_rg5_after_source_timezone_bridge"
        )
        cursor.execute(
            "ALTER TABLE collection_corrections ENABLE TRIGGER collection_correction_guard"
        )
    remap()
    correction.refresh_from_db()
    assert correction.pk == identity
    assert correction.after_source_timezone_reference_id == "UTC"
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionCorrection.objects.filter(pk=correction.pk).update(
            after_source_timezone_reference_id=None
        )
