"""Metric definitions use shared unit identities without changing frozen packets."""

import copy
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction

from core.benchmark_metric_identity import (
    configure_collection,
    definition_snapshot,
    register_definitions,
)
from core.metric_units import map_metric_units
from core.models import SourceMetric, TimeZone
from tests.test_benchmark_download_db_identity import setup_spec
from tests.test_metric_time_zones import LEGACY_SNAPSHOT_FIELDS

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def seed_utc_timezone():
    TimeZone.objects.get_or_create(pk="UTC")


def registered_metric():
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    return SourceMetric.objects.order_by("pk").first()


def test_definition_registration_and_v1_snapshot_use_only_canonical_unit_fields():
    _, spec = setup_spec()
    contract = configure_collection(spec)
    before = copy.deepcopy(contract.source_configuration)
    packets = {row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()}
    assert all(set(packet) == LEGACY_SNAPSHOT_FIELDS for packet in packets.values())

    field_names = {field.name for field in SourceMetric._meta.concrete_fields}
    assert not {"unit", "window_unit"} & field_names
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    replay = configure_collection(copy.deepcopy(spec))
    assert replay.pk == contract.pk and replay.contract_hash == contract.contract_hash
    assert replay.source_configuration == before
    assert {
        row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()
    } == packets
    assert all(row.unit_reference_id for row in SourceMetric.objects.all())
    for row in SourceMetric.objects.all():
        packet = definition_snapshot(row)
        assert packet["unit"] == row.unit_reference_id
        assert packet["window_unit"] == row.window_unit_reference_id


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_legacy_metric_writer_bridge_keeps_registered_units_consistent():
    from django.db.migrations.executor import MigrationExecutor

    MigrationExecutor(connection).migrate(
        [("core", "0126_remove_countrylabel_ck_country_label_locale_and_more")]
    )
    TimeZone.objects.get_or_create(pk="UTC")
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    registered_metric()
    metric = SourceMetric.objects.filter(window_unit_reference_id="day").first()
    assert metric is not None
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metrics SET unit='bytes',window_unit='second' WHERE id=%s",
            [metric.pk],
        )
    metric.refresh_from_db()
    assert metric.unit_reference_id == "bytes"
    assert metric.window_unit_reference_id == "second"

    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metrics SET unit='unregistered_provider_unit' WHERE id=%s",
            [metric.pk],
        )
    metric.refresh_from_db()
    assert metric.unit_reference_id == "bytes"


def test_raw_sql_rejects_unregistered_or_role_invalid_unit_references():
    metric = registered_metric()
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE metrics SET unit_id='missing' WHERE id=%s", [metric.pk])
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    timed = SourceMetric.objects.filter(window_unit_reference_id="day").first()
    assert timed is not None
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metrics SET window_unit_id='bytes' WHERE id=%s", [timed.pk]
        )


def test_map_metric_units_is_a_read_only_foreign_key_audit():
    registered_metric()
    result = map_metric_units()
    assert result["operation"] == "audit"
    assert result["healthy"] is True
    assert result["metric_count"] == SourceMetric.objects.count()
    assert result["updated"] == 0
    output = StringIO()
    call_command("map_metric_units", stdout=output)
    assert json.loads(output.getvalue())["healthy"] is True
