"""Historical corrections retain exact value history and unknown event clocks."""

import pytest

from core.benchmark_metric_timing import TIME_FIELDS
from core.collection_timing_import import import_legacy_timing_batch
from core.models import CollectionCorrection, CollectionObservation, MetricValue
from tests.test_benchmark_download_persistence import configured, payload

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _state(value):
    result = {}
    for field in TIME_FIELDS:
        current = getattr(value, field)
        result[field] = current.isoformat() if current is not None else None
    return result | {
        "temporal_status": value.temporal_status,
        "source_timezone": value.source_timezone_reference_id or "unknown",
    }


def test_historical_timing_import_is_idempotent_and_refuses_changed_value():
    from core.benchmark_metric_store import persist_source

    run = persist_source(configured(), "hf", "c" * 64, payload())
    value = MetricValue.objects.filter(observation__run=run).order_by("pk").first()
    observation = CollectionObservation.objects.get(pk=value.observation_id)
    before = {field: None for field in TIME_FIELDS}
    before.update(temporal_status="unknown", source_timezone="unknown")
    after = _state(value)
    observation.source_metadata["timing_correction_v1"] = {
        str(value.pk): {
            "policy": "reported-time-v1",
            "before": before,
            "after": after,
            "before_basis": None,
            "after_basis": {"policy": "reported-time-v1", "precision": "date"},
        }
    }
    observation.save(update_fields=["source_metadata"])

    with pytest.raises(ValueError, match="no typed root"):
        import_legacy_timing_batch(
            after_id=observation.pk - 1, batch_size=1, verify_only=True
        )
    first = import_legacy_timing_batch(
        after_id=observation.pk - 1, batch_size=1
    )
    assert first.selected_corrections == first.inserted_corrections == 1
    repeat = import_legacy_timing_batch(
        after_id=observation.pk - 1, batch_size=1
    )
    assert repeat.selected_corrections == 1 and repeat.inserted_corrections == 0
    correction = CollectionCorrection.objects.get(metric_value=value)
    assert correction.recorded_at is None
    assert correction.recorded_at_precision == "unknown"
    assert correction.imported_at is not None
    assert correction.before_temporal_status == "unknown"
    assert correction.after_temporal_status == value.temporal_status
    verified = import_legacy_timing_batch(
        after_id=observation.pk - 1, batch_size=1, verify_only=True
    )
    assert verified.selected_corrections == 1
    assert verified.inserted_corrections == 0

    observation.source_metadata["timing_correction_v1"][str(value.pk)][
        "policy"
    ] = "reported-time-v2"
    observation.save(update_fields=["source_metadata"])
    with pytest.raises(ValueError, match="conflicts with historical root"):
        import_legacy_timing_batch(
            after_id=observation.pk - 1, batch_size=1, verify_only=True
        )
    observation.source_metadata["timing_correction_v1"][str(value.pk)][
        "policy"
    ] = "reported-time-v1"
    observation.save(update_fields=["source_metadata"])

    MetricValue.objects.filter(pk=value.pk).update(temporal_status="unknown")
    with pytest.raises(ValueError, match="after-image differs"):
        import_legacy_timing_batch(after_id=observation.pk - 1, batch_size=1)


def test_import_advances_over_an_unmarked_page_without_skipping_later_corrections():
    from io import StringIO

    from django.core.management import call_command

    from core.benchmark_metric_store import persist_source

    contract = configured()
    first_run = persist_source(contract, "hf", "d" * 64, payload())
    second_run = persist_source(contract, "hf", "e" * 64, payload())
    first = CollectionObservation.objects.get(run=first_run)
    second = CollectionObservation.objects.get(run=second_run)
    value = MetricValue.objects.filter(observation=second).order_by("pk").first()
    before = {field: None for field in TIME_FIELDS}
    before.update(temporal_status="unknown", source_timezone="unknown")
    second.source_metadata["timing_correction_v1"] = {
        str(value.pk): {
            "policy": "reported-time-v1", "before": before,
            "after": _state(value), "before_basis": None,
            "after_basis": {"policy": "reported-time-v1", "precision": "date"},
        },
    }
    second.save(update_fields=["source_metadata"])

    first_page = import_legacy_timing_batch(after_id=first.pk - 1, batch_size=1)
    assert first_page.last_observation_id == first.pk
    assert first_page.scanned_observations == 1
    assert first_page.selected_corrections == first_page.inserted_corrections == 0
    assert not CollectionCorrection.objects.exists()

    output = StringIO()
    call_command(
        "import_collection_timing_corrections", after_id=first.pk - 1,
        batch_size=1, max_batches=3, stdout=output,
    )
    assert "scanned_observations=2 selected_corrections=1 inserted_corrections=1" in output.getvalue()
    assert "exhausted=true" in output.getvalue()
    assert CollectionCorrection.objects.get().metric_value_id == value.pk

    output = StringIO()
    call_command(
        "import_collection_timing_corrections", after_id=first.pk - 1,
        batch_size=1, max_batches=3, verify_only=True, stdout=output,
    )
    assert "mode=verify scanned_observations=2 selected_corrections=1 inserted_corrections=0" in output.getvalue()
    assert "exhausted=true" in output.getvalue()
