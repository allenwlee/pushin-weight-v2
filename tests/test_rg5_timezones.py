"""Measurement FK cutover preserves public timing, immutable history and retries."""

import importlib
import uuid

import pytest
from django.db import IntegrityError, connection, transaction

from core.collection_corrections import record_timing_correction
from core.measurement_taxonomy import digest
from core.models import CollectionCorrection, MetricValue, TimeZone
from tests.test_source_metric_projection import configured, evidence, project

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def measurement():
    TimeZone.objects.get_or_create(pk="UTC")
    contract, raw, _, _ = configured()
    run = project(contract, "hf", [evidence("hf", raw)])
    return run.observations.get().values.order_by("pk").first()


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
    correction = record_timing_correction(
        value, before=before, after=after, policy="fixture-v1", reason="fixture"
    )
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
    assert correction.pk == uuid.uuid5(
        uuid.NAMESPACE_URL, "pushinweight:timing-correction:" + key
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
    assert correction.after_source_timezone_reference_id == "UTC"
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionCorrection.objects.filter(pk=correction.pk).update(
            after_source_timezone_reference_id=None
        )
