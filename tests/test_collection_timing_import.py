"""Historical timing imports coexist with typed archives after ORM detachment."""

from io import StringIO

import pytest
from django.core.management import call_command

from core.benchmark_metric_store import persist_source
from core.benchmark_metric_timing_repair import FIELDS
from core.collection_capture import archive_legacy
from core.collection_pages import append_page_receipt
from core.collection_state import claim_job
from core.collection_timing_import import import_legacy_timing_batch
from core.models import (
    CollectionCorrection,
    CollectionEvidenceArchive,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    MetricValue,
)
from tests.test_backfill_collection import ready_job
from tests.test_benchmark_download_persistence import configured, payload
from tests.test_hf_catalog_retirement import denied_retirement_columns
from tests.test_metric_timing_retirement import _time_state

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _page(*, shared_scope_archive):
    claim = claim_job(
        ready_job().pk, invocation_id="timing-import-page",
        manual_authorized=True, typed=True,
    )
    run = CollectionRun.objects.get(pk=claim.run_id)
    scope = CollectionScopeRun.objects.create(
        run=run, scope_kind="x_query", scope_key="timing-import-page",
    )
    envelope = {"raw_count": 1, "received_post_ids": [None], "post_ids": []}
    archive = None
    if shared_scope_archive:
        archive = archive_legacy({
            "ownership": {}, "cursor_history": [], "envelopes": [envelope],
        })
    child = append_page_receipt(scope, envelope, legacy_archive=archive)
    return child.observations.get(observation_kind="x_page_checkpoint")


def _correction(*, contract=None):
    run = persist_source(contract or configured(), "hf", "b" * 64, payload())
    observation = run.observations.get()
    value = observation.values.get(source_metric__metric_key="downloads")
    before = dict.fromkeys(FIELDS)
    before.update(temporal_status="unknown", source_timezone="unknown")
    document = {
        "listing": {}, "dimensions": {},
        "source_metadata": {"timing_correction_v1": {str(value.pk): {
            "policy": "reported-time-v1", "before": before,
            "after": _time_state(value),
            "before_basis": None,
            "after_basis": {"policy": "reported-time-v1", "precision": "date"},
        }}},
    }
    observation.legacy_archive = archive_legacy(document)
    observation.save(update_fields=["legacy_archive"])
    return observation, value, document


def test_historical_timing_import_is_idempotent_and_refuses_changed_value():
    observation, value, document = _correction()
    options = {"after_id": observation.pk - 1, "batch_size": 1}
    with pytest.raises(ValueError, match="no typed root"):
        import_legacy_timing_batch(**options, verify_only=True)
    first = import_legacy_timing_batch(**options)
    assert first.selected_corrections == first.inserted_corrections == 1
    repeat = import_legacy_timing_batch(**options)
    assert repeat.selected_corrections == 1 and repeat.inserted_corrections == 0
    correction = CollectionCorrection.objects.get(metric_value=value)
    assert correction.recorded_at is None
    assert correction.recorded_at_precision == "unknown"
    assert correction.imported_at is not None
    assert correction.before_temporal_status == "unknown"
    assert correction.after_temporal_status == value.temporal_status
    verified = import_legacy_timing_batch(**options, verify_only=True)
    assert verified.selected_corrections == 1 and verified.inserted_corrections == 0

    # A new conflicting archive must be rejected; the original stays immutable.
    original = observation.legacy_archive
    document["source_metadata"]["timing_correction_v1"][str(value.pk)]["policy"] = "reported-time-v2"
    observation.legacy_archive = archive_legacy(document)
    observation.save(update_fields=["legacy_archive"])
    with pytest.raises(ValueError, match="conflicts with historical root"):
        import_legacy_timing_batch(**options, verify_only=True)
    observation.legacy_archive = original
    observation.save(update_fields=["legacy_archive"])
    MetricValue.objects.filter(pk=value.pk).update(temporal_status="unknown")
    with pytest.raises(ValueError, match="after-image differs"):
        import_legacy_timing_batch(**options)


def test_import_advances_over_an_unmarked_page_without_skipping_later_corrections():
    contract = configured()
    first_run = persist_source(contract, "hf", "d" * 64, payload())
    first = first_run.observations.get()
    _, value, _ = _correction(contract=contract)
    first_page = import_legacy_timing_batch(after_id=first.pk - 1, batch_size=1)
    assert first_page.last_observation_id == first.pk
    assert first_page.scanned_observations == 1
    assert first_page.selected_corrections == first_page.inserted_corrections == 0
    assert not CollectionCorrection.objects.exists()
    with denied_retirement_columns():
        for verify_only, inserted in ((False, 1), (True, 0)):
            output = StringIO()
            call_command(
                "import_collection_timing_corrections", after_id=first.pk - 1,
                batch_size=1, max_batches=3, verify_only=verify_only, stdout=output,
            )
            assert "scanned_observations=2 selected_corrections=1" in output.getvalue()
            assert f"inserted_corrections={inserted}" in output.getvalue()
            assert "exhausted=true" in output.getvalue()
        assert CollectionCorrection.objects.get().metric_value_id == value.pk


@pytest.mark.parametrize("shared_scope_archive", [False, True])
def test_operator_import_crosses_typed_page_evidence_and_verifies_correction(
    shared_scope_archive,
):
    page = _page(shared_scope_archive=shared_scope_archive)
    observation, value, _ = _correction()
    evidence = bytes(page.legacy_archive.body)
    first_id = page.pk - 1
    expected_scanned = CollectionObservation.objects.filter(pk__gt=first_id).count()
    with denied_retirement_columns():
        # A page with no corrections must still advance the bounded owner cursor.
        empty = import_legacy_timing_batch(after_id=first_id, batch_size=1)
        assert (empty.last_observation_id, empty.scanned_observations) == (page.pk, 1)
        assert empty.selected_corrections == empty.inserted_corrections == 0
        for verify_only, inserted in ((False, 1), (False, 0), (True, 0)):
            output = StringIO()
            call_command(
                "import_collection_timing_corrections", after_id=first_id,
                batch_size=100, max_batches=2, verify_only=verify_only, stdout=output,
            )
            assert f"scanned_observations={expected_scanned}" in output.getvalue()
            assert "selected_corrections=1" in output.getvalue()
            assert f"inserted_corrections={inserted}" in output.getvalue()
            assert f"next_after_id={observation.pk} exhausted=true" in output.getvalue()
        root = CollectionCorrection.objects.get(metric_value=value)
        assert root.observation_id == observation.pk
        assert root.recorded_at is None and root.recorded_at_precision == "unknown"
        assert root.imported_at is not None
        assert bytes(page.legacy_archive.body) == evidence


@pytest.mark.parametrize(
    "malformation", ["partial_envelope", "marker_list", "marker_null", "root_marker"],
)
def test_import_refuses_malformed_historical_evidence(malformation):
    observation, _, document = _correction()
    if malformation == "partial_envelope":
        del document["listing"]
    elif malformation == "marker_list":
        document["source_metadata"]["timing_correction_v1"] = []
    elif malformation == "marker_null":
        document["source_metadata"]["timing_correction_v1"] = None
    else:
        document = {"timing_correction_v1": document["source_metadata"]["timing_correction_v1"]}
    observation.legacy_archive = archive_legacy(document)
    observation.save(update_fields=["legacy_archive"])
    with pytest.raises((TypeError, ValueError)):
        import_legacy_timing_batch(after_id=observation.pk - 1, batch_size=1)
    assert not CollectionCorrection.objects.exists()


@pytest.mark.parametrize("archive_owner", ["typed_page", "historical_correction"])
def test_import_checks_archive_bytes_before_selecting_markers(monkeypatch, archive_owner):
    observation = (
        _page(shared_scope_archive=False)
        if archive_owner == "typed_page" else _correction()[0]
    )
    from_db = CollectionEvidenceArchive.from_db

    def corrupt_loaded_body(cls, db, field_names, values):
        # Archives reject corruption on INSERT/UPDATE. Simulate damaged bytes
        # delivered by storage without weakening that database constraint.
        archive = from_db(db, field_names, values)
        if archive.pk == observation.legacy_archive_id and "body" in field_names:
            archive.body = b"{}"
        return archive

    monkeypatch.setattr(CollectionEvidenceArchive, "from_db", classmethod(corrupt_loaded_body))
    with pytest.raises(ValueError, match="capture checksum mismatch"):
        import_legacy_timing_batch(after_id=observation.pk - 1, batch_size=1)
    assert not CollectionCorrection.objects.exists()
