"""Shared zone references preserve the installed metric-definition contract."""

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from core.benchmark_metric_identity import (
    configure_collection,
    definition_snapshot,
    register_definitions,
)
from core.models import SourceMetric, TimeZone
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

LEGACY_SNAPSHOT_FIELDS = {
    "id",
    "source_id",
    "metric_type_id",
    "metric_key",
    "version",
    "name",
    "unit",
    "value_kind",
    "quantity_form",
    "value_role",
    "measurement_kind",
    "window_mode",
    "window_amount",
    "window_unit",
    "window_duration_basis",
    "window_alignment",
    "source_timezone",
    "required",
    "definition_metadata",
}


def test_definition_snapshot_characterization_is_the_existing_nineteen_fields():
    register_definitions()
    before = {row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()}
    assert before
    assert all(set(value) == LEGACY_SNAPSHOT_FIELDS for value in before.values())
    call_command("seed_shared_vocabulary", catalogue=["time_zones"], verbosity=0)
    register_definitions()
    assert {
        row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()
    } == before


def test_real_collection_replay_after_catalogue_seed_preserves_saved_contract():
    _, spec = setup_spec()
    contract = configure_collection(spec)
    before = copy.deepcopy(contract.source_configuration)
    original_hash = contract.contract_hash
    call_command("seed_shared_vocabulary", catalogue=["time_zones"], verbosity=0)
    register_definitions()
    replay = configure_collection(copy.deepcopy(spec))
    assert replay.pk == contract.pk and replay.contract_hash == original_hash
    assert replay.source_configuration == before
    assert all(
        set(row) == LEGACY_SNAPSHOT_FIELDS
        for settings in before.values()
        for row in settings["definitions"]
    )


def test_late_registry_mapping_is_bounded_idempotent_and_preserves_snapshots():
    register_definitions()
    expected = {row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()}
    TimeZone.objects.create(code="UTC")
    call_command("map_metric_time_zones", apply=True, batch_size=1, max_batches=1)
    known = SourceMetric.objects.filter(source_timezone="UTC")
    assert known.filter(source_timezone_reference_id="UTC").count() == 1
    call_command("map_metric_time_zones", apply=True, batch_size=2, max_batches=100)
    assert not known.filter(source_timezone_reference_id__isnull=True).exists()
    assert (
        not SourceMetric.objects.filter(source_timezone="unknown")
        .exclude(source_timezone_reference_id=None)
        .exists()
    )
    call_command("map_metric_time_zones", apply=True)
    assert {
        row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()
    } == expected


def test_mapping_preview_does_not_write_and_bad_limits_fail():
    register_definitions()
    TimeZone.objects.create(code="UTC")
    output = StringIO()
    call_command("map_metric_time_zones", stdout=output)
    assert '"apply": false' in output.getvalue()
    assert not SourceMetric.objects.filter(
        source_timezone_reference__isnull=False
    ).exists()
    with pytest.raises(CommandError, match="bounded"):
        call_command("map_metric_time_zones", apply=True, batch_size=0)
    assert not SourceMetric.objects.filter(
        source_timezone_reference__isnull=False
    ).exists()


def test_python_command_call_rejects_apply_and_preview_before_any_write():
    register_definitions()
    TimeZone.objects.create(code="UTC")
    with pytest.raises(CommandError, match="cannot be combined"):
        call_command("map_metric_time_zones", apply=True, dry_run=True)
    assert not SourceMetric.objects.filter(
        source_timezone_reference__isnull=False
    ).exists()


def test_old_writer_changes_keep_exact_reference_or_unknown_without_guessing():
    TimeZone.objects.bulk_create([TimeZone(code="UTC"), TimeZone(code="US/Eastern")])
    register_definitions()
    row = SourceMetric.objects.filter(source_timezone="UTC").first()
    assert row.source_timezone_reference_id == "UTC"
    for raw, reference in [
        ("US/Eastern", "US/Eastern"),
        ("CST", None),
        ("unknown", None),
        ("UTC", "UTC"),
    ]:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE metrics SET source_timezone=%s WHERE id=%s", [raw, row.pk]
            )
        row.refresh_from_db()
        assert (
            row.source_timezone == raw and row.source_timezone_reference_id == reference
        )
    with pytest.raises(ProtectedError):
        TimeZone.objects.get(pk="UTC").delete()


@pytest.mark.parametrize("reference", ["US/Eastern", "Missing/Zone"])
def test_raw_sql_rejects_reference_that_disagrees_with_reported_definition(reference):
    TimeZone.objects.bulk_create([TimeZone(code="UTC"), TimeZone(code="US/Eastern")])
    register_definitions()
    row = SourceMetric.objects.filter(source_timezone="UTC").first()
    with (
        pytest.raises(IntegrityError, match="timezone reference"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE metrics SET source_timezone_id=%s WHERE id=%s", [reference, row.pk]
        )
    row.refresh_from_db()
    assert row.source_timezone_reference_id == row.source_timezone == "UTC"


@pytest.mark.django_db(transaction=True)
def test_mapping_rechecks_a_reported_timezone_changed_while_waiting_for_its_lock():
    from django.db import connections

    from core.metric_time_zones import map_metric_time_zones

    register_definitions()
    TimeZone.objects.create(code="UTC")
    row = SourceMetric.objects.filter(source_timezone="UTC").order_by("pk").first()
    started = Event()
    backend = []

    def map_one():
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend.append(cursor.fetchone()[0])
            started.set()
            return map_metric_time_zones(apply=True, batch_size=1, max_batches=1)
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT id FROM metrics WHERE id=%s FOR UPDATE", [row.pk])
            future = pool.submit(map_one)
            assert started.wait(10)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                cursor.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND NOT granted)",
                    [backend[0]],
                )
                if cursor.fetchone() == (True,):
                    break
                time.sleep(0.01)
            else:
                pytest.fail("Mapper did not reach the expected row-lock wait")
            cursor.execute(
                "UPDATE metrics SET source_timezone='CST' WHERE id=%s", [row.pk]
            )
        result = future.result(timeout=10)
    row.refresh_from_db()
    assert result["updated"] == 0
    assert row.source_timezone == "CST" and row.source_timezone_reference_id is None


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_populated_mapping_and_reverse_preserve_original_packets_and_old_writers():
    from django.db.migrations.executor import MigrationExecutor

    from tests.collection_fixtures import historical_fixture_models

    base = ("core", "0115_shared_actors_and_correction_identity")
    target = ("core", "0116_metric_source_timezone_reference")
    MigrationExecutor(connection).migrate([base])
    old = MigrationExecutor(connection).loader.project_state([base]).apps
    OldMetric = old.get_model("core", "SourceMetric")
    old.get_model("core", "TimeZone").objects.create(code="UTC")
    with historical_fixture_models(old):
        _, spec = setup_spec()
        contract = configure_collection(spec)
    original_hash = contract.contract_hash
    before = list(OldMetric.objects.order_by("pk").values())
    before_packets = {
        row.pk: definition_snapshot(row) for row in OldMetric.objects.all()
    }
    MigrationExecutor(connection).migrate([target])
    after = list(SourceMetric.objects.order_by("pk").values())
    for row in after:
        reference = row.pop("source_timezone_reference_id")
        assert reference == ("UTC" if row["source_timezone"] == "UTC" else None)
    assert after == before
    assert {
        row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()
    } == before_packets
    replay = configure_collection(copy.deepcopy(spec))
    assert replay.pk == contract.pk and replay.contract_hash == original_hash
    fields = next(row for row in before if row["source_timezone"] == "UTC").copy()
    fields.pop("id")
    fields["metric_key"] = "legacy-zone-writer"
    legacy = OldMetric.objects.create(**fields)
    assert SourceMetric.objects.get(pk=legacy.pk).source_timezone_reference_id == "UTC"
    OldMetric.objects.filter(pk=legacy.pk).update(source_timezone="CST")
    assert SourceMetric.objects.get(pk=legacy.pk).source_timezone_reference_id is None
    MigrationExecutor(connection).migrate([base])
    assert (
        list(OldMetric.objects.exclude(pk=legacy.pk).order_by("pk").values()) == before
    )
    assert OldMetric.objects.get(pk=legacy.pk).source_timezone == "CST"
    MigrationExecutor(connection).migrate([target])
