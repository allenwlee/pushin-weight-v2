"""Shared unit identities preserve source definitions and installed packets."""

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event
from unittest.mock import patch

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
from core.metric_units import map_metric_units
from core.models import MeasurementUnit, SourceMetric, TimeZone
from tests.test_benchmark_download_db_identity import setup_spec
from tests.test_metric_time_zones import LEGACY_SNAPSHOT_FIELDS

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def seed_utc_timezone():
    TimeZone.objects.get_or_create(pk="UTC")


def test_original_unit_wording_and_real_collection_packet_characterization():
    _, spec = setup_spec()
    contract = configure_collection(spec)
    before = copy.deepcopy(contract.source_configuration)
    packets = {row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()}
    assert all(set(packet) == LEGACY_SNAPSHOT_FIELDS for packet in packets.values())
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    replay = configure_collection(copy.deepcopy(spec))
    assert replay.pk == contract.pk and replay.contract_hash == contract.contract_hash
    assert replay.source_configuration == before
    assert {
        row.pk: definition_snapshot(row) for row in SourceMetric.objects.all()
    } == packets


def test_old_definition_registration_resolves_both_exact_unit_roles():
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    rows = list(SourceMetric.objects.all())
    codes = set(MeasurementUnit.objects.values_list("code", flat=True))
    assert rows and any(row.window_unit == "day" for row in rows)
    for row in rows:
        assert row.unit_reference_id == (row.unit if row.unit in codes else None)
        assert row.window_unit_reference_id == row.window_unit


def test_late_mapping_preserves_unknown_wording_and_resumes_without_packet_changes():
    register_definitions()
    row = SourceMetric.objects.filter(window_unit__isnull=True).first()
    SourceMetric.objects.filter(pk=row.pk).update(unit="provider_native_units")
    before = {m.pk: definition_snapshot(m) for m in SourceMetric.objects.all()}
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    codes = set(MeasurementUnit.objects.values_list("code", flat=True))
    expected_unknown = sum(packet["unit"] not in codes for packet in before.values())
    first = map_metric_units(apply=True, batch_size=1, max_batches=1)
    assert first["updated"] == first["examined"] == 1
    second = map_metric_units(
        apply=True,
        after_metric_id=first["after_metric_id"],
        batch_size=2,
        max_batches=100,
    )
    assert second["remaining_resolvable"] == 0
    assert second["unmatched_unit_count"] == expected_unknown >= 1
    assert second["unmatched_window_unit_count"] == 0
    assert map_metric_units(apply=True)["updated"] == 0
    row.refresh_from_db()
    assert row.unit == "provider_native_units" and row.unit_reference_id is None
    assert {m.pk: definition_snapshot(m) for m in SourceMetric.objects.all()} == before


def test_roles_resolve_independently_when_only_the_window_code_is_registered():
    register_definitions()
    MeasurementUnit.objects.create(code="day")
    result = map_metric_units(apply=True)
    assert result["updated"] == SourceMetric.objects.filter(window_unit="day").count()
    assert not SourceMetric.objects.filter(unit_reference__isnull=False).exists()
    assert (
        not SourceMetric.objects.filter(window_unit="day")
        .exclude(window_unit_reference_id="day")
        .exists()
    )
    assert (
        not SourceMetric.objects.filter(window_unit__isnull=True)
        .filter(window_unit_reference__isnull=False)
        .exists()
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"batch_size": 0},
        {"max_batches": 10001},
        {"after_metric_id": -1},
        {"apply": True, "dry_run": True},
    ],
)
def test_invalid_or_conflicting_command_controls_fail_without_writes(kwargs):
    register_definitions()
    MeasurementUnit.objects.create(code="downloads")
    with pytest.raises(CommandError):
        call_command("map_metric_units", **kwargs)
    assert not SourceMetric.objects.filter(unit_reference__isnull=False).exists()


def test_command_preview_reports_eligibility_without_writing():
    register_definitions()
    MeasurementUnit.objects.create(code="downloads")
    output = StringIO()
    call_command("map_metric_units", stdout=output)
    result = json.loads(output.getvalue())
    assert result["apply"] is False and result["updated"] == 0
    assert result["examined"] == result["remaining_resolvable"] > 0
    assert not SourceMetric.objects.filter(unit_reference__isnull=False).exists()


def test_old_raw_writers_keep_roles_separate_and_preserve_window_shape():
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    row = SourceMetric.objects.filter(window_unit="day").first()
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metrics SET unit='bytes',window_unit='second' WHERE id=%s",
            [row.pk],
        )
    row.refresh_from_db()
    assert row.unit_reference_id == row.unit == "bytes"
    assert row.window_unit_reference_id == row.window_unit == "second"
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metrics SET unit='raw_unknown',window_mode='since_origin',"
            "window_unit=NULL,window_amount=NULL,window_duration_basis='none',"
            "window_alignment=NULL WHERE id=%s",
            [row.pk],
        )
    row.refresh_from_db()
    assert row.unit == "raw_unknown" and row.unit_reference_id is None
    assert row.window_unit is None and row.window_unit_reference_id is None
    with pytest.raises(ProtectedError):
        MeasurementUnit.objects.get(pk="downloads").delete()


@pytest.mark.parametrize(
    "assignment",
    [
        "unit_id='bytes'",
        "unit_id='missing_unit'",
        "window_unit_id='second'",
        "window_unit_id='missing_unit'",
        "window_unit='bytes'",  # A registered unit is not a valid time-window unit.
    ],
)
def test_raw_sql_rejects_contradictory_references_or_non_time_window(assignment):
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    row = SourceMetric.objects.filter(unit="downloads", window_unit="day").first()
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"UPDATE metrics SET {assignment} WHERE id=%s", [row.pk])
    row.refresh_from_db()
    assert (
        row.unit_reference_id == "downloads" and row.window_unit_reference_id == "day"
    )


def test_a_reference_cannot_be_attached_to_an_absent_window():
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"])
    register_definitions()
    row = SourceMetric.objects.filter(window_unit__isnull=True).first()
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceMetric.objects.filter(pk=row.pk).update(window_unit_reference_id="day")


@pytest.mark.django_db(transaction=True)
def test_mapper_rechecks_both_roles_after_a_concurrent_old_writer():
    from django.db import connections

    register_definitions()
    row = SourceMetric.objects.filter(window_unit="day").order_by("pk").first()
    MeasurementUnit.objects.bulk_create(
        [
            MeasurementUnit(code=row.unit),
            MeasurementUnit(code="day"),
        ]
    )
    started = Event()
    backend = []

    def map_one():
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend.append(cursor.fetchone()[0])
            started.set()
            return map_metric_units(
                apply=True, after_metric_id=row.pk - 1, batch_size=1, max_batches=1
            )
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT id FROM metrics WHERE id=%s FOR UPDATE", [row.pk])
            future = pool.submit(map_one)
            assert started.wait(5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                cursor.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                    [backend[0]],
                )
                if cursor.fetchone() == ("Lock",):
                    break
                time.sleep(0.01)
            else:
                pytest.fail("Mapper did not reach the expected row-lock wait")
            cursor.execute(
                "UPDATE metrics SET unit='new_unknown',window_unit='second' WHERE id=%s",
                [row.pk],
            )
        result = future.result(timeout=10)
    row.refresh_from_db()
    assert result["updated"] == 0
    assert row.unit == "new_unknown" and row.unit_reference_id is None
    assert row.window_unit == "second" and row.window_unit_reference_id is None


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_populated_migration_reverse_and_old_image_writes_preserve_original_fields():
    from django.db.migrations.executor import MigrationExecutor

    from tests.collection_fixtures import historical_fixture_models

    base = ("core", "0116_metric_source_timezone_reference")
    target = ("core", "0117_metric_unit_references")
    MigrationExecutor(connection).migrate([base])
    old = MigrationExecutor(connection).loader.project_state([base]).apps
    OldMetric = old.get_model("core", "SourceMetric")
    old.get_model("core", "MeasurementUnit").objects.bulk_create(
        [
            old.get_model("core", "MeasurementUnit")(code=code)
            for code in ("downloads", "day", "second")
        ]
    )
    with historical_fixture_models(old):
        from core.benchmark_metric_identity import definition_rows

        historical_rows = definition_rows()
        for row in historical_rows:
            row["source_timezone_reference_id"] = None
        with patch(
            "core.benchmark_metric_identity.definition_rows",
            return_value=historical_rows,
        ):
            _, spec = setup_spec()
        contract = configure_collection(spec)
    before = list(OldMetric.objects.order_by("pk").values())
    packets = {m.pk: definition_snapshot(m) for m in OldMetric.objects.all()}
    MigrationExecutor(connection).migrate([target])
    target_apps = MigrationExecutor(connection).loader.project_state([target]).apps
    TargetMetric = target_apps.get_model("core", "SourceMetric")
    after = list(TargetMetric.objects.order_by("pk").values())
    for row in after:
        assert row.pop("unit_reference_id") == (
            "downloads" if row["unit"] == "downloads" else None
        )
        assert row.pop("window_unit_reference_id") == row["window_unit"]
    assert after == before
    assert {m.pk: definition_snapshot(m) for m in SourceMetric.objects.all()} == packets
    replay = configure_collection(copy.deepcopy(spec))
    assert replay.pk == contract.pk and replay.contract_hash == contract.contract_hash
    fields = next(r for r in before if r["window_unit"] == "day").copy()
    fields.pop("id")
    fields["metric_key"] = "old-image-unit-writer"
    fields["unit"] = "downloads"
    legacy = OldMetric.objects.create(**fields)
    current = SourceMetric.objects.get(pk=legacy.pk)
    assert current.unit_reference_id == "downloads"
    assert current.window_unit_reference_id == "day"
    OldMetric.objects.filter(pk=legacy.pk).update(
        unit="raw_unknown", window_unit="second"
    )
    current.refresh_from_db()
    assert (
        current.unit_reference_id is None
        and current.window_unit_reference_id == "second"
    )
    MigrationExecutor(connection).migrate([base])
    assert (
        list(OldMetric.objects.exclude(pk=legacy.pk).order_by("pk").values()) == before
    )
    assert OldMetric.objects.get(pk=legacy.pk).unit == "raw_unknown"
    MigrationExecutor(connection).migrate([target])
