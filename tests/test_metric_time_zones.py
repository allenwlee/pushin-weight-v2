"""Canonical timezone references replace metric definition strings."""

import copy

import pytest
from django.core.management import call_command

from core.benchmark_metric_identity import (
    configure_collection,
    definition_snapshot,
    register_definitions,
)
from core.models import SourceMetric
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


def test_frozen_definition_snapshot_keeps_its_shape_from_the_fk():
    call_command("seed_shared_vocabulary", catalogue=["time_zones"], verbosity=0)
    register_definitions()
    rows = list(SourceMetric.objects.all())
    assert rows
    assert "source_timezone" not in {field.name for field in SourceMetric._meta.fields}
    snapshots = {row.pk: definition_snapshot(row) for row in rows}
    assert all(
        set(snapshot) == LEGACY_SNAPSHOT_FIELDS for snapshot in snapshots.values()
    )
    assert all(
        snapshot["source_timezone"] == (row.source_timezone_reference_id or "unknown")
        for row in rows
        for snapshot in [snapshots[row.pk]]
    )
    assert any(snapshot["source_timezone"] == "UTC" for snapshot in snapshots.values())
    assert any(
        snapshot["source_timezone"] == "unknown" for snapshot in snapshots.values()
    )


def test_saved_collection_replays_with_the_original_v1_snapshot_shape():
    call_command("seed_shared_vocabulary", catalogue=["time_zones"], verbosity=0)
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


def test_definitions_store_known_zones_only_in_the_shared_reference():
    call_command("seed_shared_vocabulary", catalogue=["time_zones"], verbosity=0)
    register_definitions()
    rows = list(SourceMetric.objects.all())
    assert rows
    assert all(row.source_timezone_reference_id in {None, "UTC"} for row in rows)
    assert any(row.source_timezone_reference_id == "UTC" for row in rows)
    assert any(row.source_timezone_reference_id is None for row in rows)
