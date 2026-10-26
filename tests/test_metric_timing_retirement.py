"""Repair and rollback use immutable evidence and typed corrections after RG6."""

from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection

from core.benchmark_metric_history import import_history
from core.benchmark_metric_store import persist_source
from core.benchmark_metric_timing_repair import FIELDS, repair_batch, serial_fields
from core.collection_capture import archive_legacy
from core.collection_corrections import TIME_BASIS_FIELDS
from core.models import (
    CollectionCorrection,
    CollectionObservation,
    CollectionObservationInput,
    MetricValue,
)
from tests.test_benchmark_download_history import manifest
from tests.test_benchmark_download_persistence import configured, payload
from tests.test_hf_catalog_retirement import denied_retirement_columns

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _time_state(value):
    return serial_fields(
        {
            key: value.source_timezone_reference_id or "unknown"
            if key == "source_timezone"
            else getattr(value, key)
            for key in FIELDS
        }
    )


def _erase_timing():
    MetricValue.objects.all().update(
        window_start_at=None,
        window_end_at=None,
        period_label_date=None,
        temporal_status="unknown",
        **dict.fromkeys(TIME_BASIS_FIELDS),
    )


def test_hf_command_preserves_archive_day_native_creation_and_rollback_without_json():
    # The production model itself is detached; the denied-column wrapper is no
    # longer responsible for hiding legacy fields from this call chain.
    assert not {"listing", "dimensions", "source_metadata", "envelopes", "groups"} & {
        field.name for field in CollectionObservation._meta.fields
    }
    contract = configured()
    data = manifest(contract)
    for snapshot in data["snapshots"]:
        snapshot["payload"]["rows"][0]["raw"]["createdAt"] = "2024-07-01T11:22:33Z"
        from core.measurement_taxonomy import digest

        snapshot["raw_artifact_sha256"] = digest(snapshot["payload"])
    with denied_retirement_columns():
        run = import_history(data, apply=True)
        evidence = (run.payload_archive_id, bytes(run.payload_archive.body))
        _erase_timing()
        cutoff = MetricValue.objects.latest("pk").pk
        options = {
            "database_name": connection.settings_dict["NAME"],
            "cutoff_value_id": cutoff,
            "batch_size": 1,
            "max_batches": 10,
            "stdout": StringIO(),
        }
        call_command("repair_metric_timing", **options)
        assert not CollectionCorrection.objects.exists()
        call_command("repair_metric_timing", apply=True, backup_id="fixture", **options)
        assert CollectionCorrection.objects.count() == 4
        for value in MetricValue.objects.select_related("source_metric", "observation"):
            assert value.period_label_date == value.observation.archive_snapshot_date
            assert value.window_end_basis == "archive_snapshot_date"
            if value.source_metric.metric_key == "downloads_all_time":
                assert value.window_start_at == datetime(
                    2024, 7, 1, 11, 22, 33, tzinfo=UTC
                )
                assert value.window_start_basis == "native_repository_creation"
            assert value.window_start_unknown_reason is None
        call_command(
            "repair_metric_timing",
            apply=True,
            rollback=True,
            backup_id="fixture",
            **options,
        )
        assert CollectionCorrection.objects.count() == 8
        assert all(value.window_end_at is None for value in MetricValue.objects.all())
        assert (run.payload_archive_id, bytes(run.payload_archive.body)) == evidence


@pytest.mark.parametrize("tamper", [None, "input_hash", "source_identity"])
def test_primary_numeric_input_owns_native_creation(tamper):
    contract = configured()
    run = persist_source(contract, "hf", "1" * 64, payload())
    observation = run.observations.get()
    origin = CollectionObservation.objects.create(
        run=run,
        observation_key="2" * 64,
        source_identifier=observation.source_identifier,
        source_subject_kind="repository",
        legacy_archive=archive_legacy(
            {
                "listing": {"createdAt": "2025-01-01T12:00:00Z"},
                "dimensions": {},
                "source_metadata": {},
            }
        ),
    )
    CollectionObservationInput.objects.create(
        observation=observation,
        input_observation=origin,
        input_role="numeric_projection",
        input_sha256=origin.observation_key,
    )
    if tamper == "input_hash":
        observation.inputs.update(input_sha256="3" * 64)
    elif tamper == "source_identity":
        CollectionObservation.objects.filter(pk=origin.pk).update(
            source_identifier="other/model"
        )
    _erase_timing()
    with denied_retirement_columns():
        if tamper:
            with pytest.raises(ValueError, match="origin changed"):
                repair_batch(cutoff=MetricValue.objects.latest("pk").pk, apply=True)
            assert not CollectionCorrection.objects.exists()
        else:
            repair_batch(cutoff=MetricValue.objects.latest("pk").pk, apply=True)
            value = MetricValue.objects.get(
                source_metric__metric_key="downloads_all_time"
            )
            assert value.window_start_at == datetime(2025, 1, 1, 12, tzinfo=UTC)
            assert value.window_end_at == observation.observed_at


def test_unimported_historical_marker_fails_closed_without_retired_columns():
    run = persist_source(configured(), "hf", "4" * 64, payload())
    value = MetricValue.objects.order_by("pk").first()
    before = {name: None for name in FIELDS}
    before.update(temporal_status="unknown", source_timezone="unknown")
    legacy = archive_legacy(
        {
            "listing": {},
            "dimensions": {},
            "source_metadata": {
                "timing_correction_v1": {
                    str(value.pk): {
                        "policy": "reported-time-v1",
                        "before": before,
                        "after": _time_state(value),
                    }
                },
            },
        }
    )
    run.observations.update(legacy_archive=legacy)
    with (
        denied_retirement_columns(),
        pytest.raises(ValueError, match="must be imported"),
    ):
        repair_batch(cutoff=value.pk, apply=True, rollback=True)
    assert not CollectionCorrection.objects.exists()


@pytest.mark.parametrize("tamper", ["missing", "wrong_payload"])
def test_repair_refuses_unavailable_or_unrelated_capture(tamper):
    run = persist_source(configured(), "hf", "5" * 64, payload())
    _erase_timing()
    if tamper == "missing":
        type(run).objects.filter(pk=run.pk).update(payload_archive=None)
    else:
        run.observations.update(observation_key="6" * 64)
    with (
        denied_retirement_columns(),
        pytest.raises(ValueError, match="retained source"),
    ):
        repair_batch(cutoff=MetricValue.objects.latest("pk").pk, apply=True)
    assert not CollectionCorrection.objects.exists()


def test_opencode_partial_update_and_typed_rollback_preserve_original_capture():
    from tests.test_benchmark_opencode import configured as opencode_contract
    from tests.test_benchmark_opencode import endpoint, read

    contract = opencode_contract()
    source = read(endpoint())
    with denied_retirement_columns():
        run = persist_source(contract, "opencode", "7" * 64, source)
        partial = run.observations.get(period_status="partial")
        values = MetricValue.objects.filter(observation=partial)
        expected = {value.pk: _time_state(value) for value in values.all()}
        values.update(
            window_end_at=None, window_end_basis=None, reported_time_policy=None
        )
        before = {value.pk: _time_state(value) for value in values.all()}
        batch = repair_batch(cutoff=MetricValue.objects.latest("pk").pk, apply=True)
        assert batch["changed_values"] == batch["correction_records"] == 3
        assert {value.pk: _time_state(value) for value in values.all()} == expected
        assert values.first().window_end_basis == "published_partial_update"
        repair_batch(
            cutoff=MetricValue.objects.latest("pk").pk, apply=True, rollback=True
        )
        assert {value.pk: _time_state(value) for value in values.all()} == before
        assert CollectionCorrection.objects.count() == 6


def test_imported_historical_correction_rolls_back_without_inventing_correction_time():
    from core.collection_timing_import import import_legacy_timing_batch

    run = persist_source(configured(), "hf", "8" * 64, payload())
    value = MetricValue.objects.get(source_metric__metric_key="downloads")
    before = {name: None for name in FIELDS}
    before.update(temporal_status="unknown", source_timezone="unknown")
    basis = {
        "policy": value.reported_time_policy,
        "precision": value.provenance_precision,
        "basis": value.window_end_basis,
        "start_basis": value.window_start_basis,
    }
    archived = archive_legacy(
        {
            "listing": {},
            "dimensions": {},
            "source_metadata": {
                "timing_correction_v1": {
                    str(value.pk): {
                        "policy": "reported-time-v1",
                        "before": before,
                        "after": _time_state(value),
                        "before_basis": None,
                        "after_basis": basis,
                    }
                },
            },
        }
    )
    run.observations.update(legacy_archive=archived)
    import_legacy_timing_batch(after_id=value.observation_id - 1, batch_size=1)
    root = CollectionCorrection.objects.get(metric_value=value)
    with denied_retirement_columns():
        outcome = repair_batch(cutoff=value.pk, apply=True, rollback=True)
        assert outcome["changed_values"] == 1
        root.refresh_from_db()
        assert root.recorded_at is None and root.recorded_at_precision == "unknown"
        assert root.imported_at is not None
        successor = CollectionCorrection.objects.get(predecessor=root)
        assert (
            successor.recorded_at is not None
            and successor.recorded_at_precision == "instant"
        )
        value.refresh_from_db()
        assert _time_state(value) == before
        assert all(getattr(value, field) is None for field in TIME_BASIS_FIELDS)
        assert bytes(archived.body) == bytes(run.observations.get().legacy_archive.body)


@pytest.mark.parametrize("changed_clock", [False, True])
def test_original_retrieval_is_never_replaced_by_import_or_repair_time(changed_clock):
    data = payload()
    data["rows"][0]["_source_metadata"] = {
        "original_retrieved_at": "2025-05-05T10:00:00Z"
    }
    run = persist_source(configured(), "hf", "9" * 64, data)
    _erase_timing()
    if changed_clock:
        run.observations.update(
            original_retrieved_at=datetime(2025, 6, 5, 10, tzinfo=UTC)
        )
    with denied_retirement_columns():
        cutoff = MetricValue.objects.latest("pk").pk
        if changed_clock:
            with pytest.raises(ValueError, match="capture clock changed"):
                repair_batch(cutoff=cutoff, apply=True)
            assert not CollectionCorrection.objects.exists()
        else:
            repair_batch(cutoff=cutoff, apply=True)
            assert all(
                value.window_end_at == datetime(2025, 5, 5, 10, tzinfo=UTC)
                for value in MetricValue.objects.all()
            )


def test_github_state_uses_publication_date_without_inventing_midnight():
    from datetime import date

    from core.models import CollectionRun, SourceMetric
    from tests.collection_fixtures import evidence_job

    configured()  # Installs the reviewed source definitions used by the fixture.
    with denied_retirement_columns():
        run = CollectionRun.objects.create(
            job=evidence_job(source_id="github"),
            ingestion_key="a" * 64,
            status="success",
            completed_at=datetime.now(UTC),
        )
        observation = CollectionObservation.objects.create(
            run=run,
            source_identifier="123",
            source_subject_kind="repository",
            observation_key="b" * 64,
            published_date=date(2026, 9, 3),
            publication_precision="date",
            legacy_archive=archive_legacy(
                {
                    "listing": {"id": 123, "stargazers_count": 0},
                    "dimensions": {},
                    "source_metadata": {},
                }
            ),
        )
        value = MetricValue.objects.create(
            observation=observation,
            source_metric=SourceMetric.objects.get(
                source_id="github", metric_key="stars"
            ),
            integer_value=0,
        )
        result = repair_batch(cutoff=value.pk, apply=True)
        assert result["changed_values"] == 1
        value.refresh_from_db()
        assert value.integer_value == 0 and value.as_of_at is None
        assert (
            value.as_of_date == date(2026, 9, 3)
            and value.temporal_status == "date_only"
        )
        assert value.as_of_basis == "publication_date"
        repair_batch(cutoff=value.pk, apply=True, rollback=True)
        value.refresh_from_db()
        assert value.temporal_status == "unknown" and value.as_of_date is None
