"""Typed projection results retain source/output counts and exact capture lineage."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from core.collection_capture import archive_legacy, run_report_document
from core.models import CollectionObservation, MetricValue
from core.source_metric_projection import projection_report
from tests.test_hf_catalog_retirement import denied_retirement_columns
from tests.test_source_metric_projection import CAPTURED, configured, evidence, project

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def retain(snapshot):
    snapshot.legacy_archive = archive_legacy({
        "listing": snapshot.listing, "dimensions": snapshot.dimensions,
        "source_metadata": snapshot.source_metadata,
    })
    snapshot.save(update_fields=["legacy_archive"])
    return snapshot


@pytest.mark.parametrize("supplement", [False, True])
def test_shared_output_counts_each_new_value_once_and_preserves_both_sources(supplement):
    contract, raw, _, _ = configured()
    first = evidence("hf", {"id": raw["id"], "downloads": 0} if supplement else raw)
    second = evidence("hf", raw, observed_at=CAPTURED + timedelta(hours=1))
    for snapshot in (first, second):
        snapshot.source_metadata = {"numeric_snapshot_identity": {"period": "2026-10-01", "revision": "v1"}}
        snapshot.save(update_fields=["source_metadata"])
        retain(snapshot)
    with denied_retirement_columns():
        run = project(contract, "hf", [first, second])
        report = projection_report(run)
        assert run.status == "success" and run.selected_count == run.success_count == 2
        assert report["selected_resources"] == report["admitted_resources"] == 2
        assert report["written_values"] == 2 and report["written_observations"] == 1
        outputs = list(run.scopes.filter(scope_kind="numeric_projection_output").order_by("pk"))
        assert [row.phase for row in outputs] == ["written", "reused"]
        assert [row.raw_count for row in outputs] == ([1, 1] if supplement else [2, 0])
        assert outputs[0].resource_observation_id == outputs[1].resource_observation_id
        assert MetricValue.objects.count() == 2
        assert list(run.scopes.filter(scope_kind="numeric_projection_result").order_by("pk").values_list(
            "resource_observation_id", flat=True,
        )) == [first.pk, second.pk]
        assert run_report_document(run)["projection"] == report


def test_real_hf_capture_to_numbers_and_report_need_no_retiring_columns(monkeypatch):
    from core.model_inventory import execute_model_inventory
    from tests.test_hf_inventory_retirement import client
    from tests.test_hf_source_ingestion import ingestion_job

    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    with denied_retirement_columns():
        run = execute_model_inventory(job.pk, budget=client(raw))
        assert run.status == "success"
        assert MetricValue.objects.count() == 3
        assert not run.scopes.filter(scope_kind="numeric_projection_item", outcome="pending").exists()
        numeric_run = MetricValue.objects.first().observation.run
        before = projection_report(numeric_run)
        monkeypatch.setattr("core.collection_capture.read_document", lambda *_: pytest.fail("typed report read an evidence archive"))
        assert projection_report(numeric_run) == before


def test_failed_projection_keeps_a_typed_marker_and_preserved_error():
    from core.collection_capture import read_document
    from core.models import CollectionRun

    contract, raw, _, _ = configured()
    snapshot = retain(evidence("hf", raw))
    with denied_retirement_columns():
        project(contract, "hf", [snapshot])
        numeric = CollectionObservation.objects.get(projection_kind="source-statistics-v1")
        numeric.original_retrieved_at = CAPTURED
        numeric.save(update_fields=["original_retrieved_at"])
        with pytest.raises(ValueError, match="immutable snapshot clock conflict"):
            project(contract, "hf", [snapshot], key="invalid-clock")
        failed = CollectionRun.objects.get(status="failed")
        parent = failed.scopes.get(scope_kind="numeric_projection", scope_key="saved-evidence")
        assert parent.phase == "projection_results_v1" and parent.outcome == "failed"
        assert "immutable snapshot clock conflict" in read_document(parent.legacy_archive)["projection_error"]
        assert run_report_document(failed)["projection"]["selected_resources"] == 0


def test_new_writer_reuses_verified_legacy_marker_without_duplicate_output():
    contract, raw, _, _ = configured()
    snapshot = retain(evidence("hf", raw))
    first = project(contract, "hf", [snapshot])
    numeric = first.observations.get()
    CollectionObservation.objects.filter(pk=numeric.pk).update(
        projection_kind=None, source_metadata={"projection_kind": "source-statistics-v1"},
    )
    with denied_retirement_columns():
        repeated = project(contract, "hf", [snapshot], key="legacy-marker")
        report = projection_report(repeated)
        assert report["written_values"] == report["written_observations"] == 0
        assert report["reused_observation_ids"] == [numeric.pk]
        assert MetricValue.objects.count() == 2
        assert CollectionObservation.objects.filter(projection_kind="source-statistics-v1").get().pk == numeric.pk


@pytest.mark.parametrize("legacy_first", [False, True])
def test_statistics_identity_guard_spans_old_and_typed_writers(legacy_first):
    from core.models import CollectionRun
    from tests.collection_fixtures import evidence_job

    contract, _, _, _ = configured()
    job = evidence_job(source_id="hf", purpose="metric", contract_id=contract.pk)
    lifecycle = {"status": "success", "started_at": CAPTURED, "completed_at": CAPTURED,
                 "lease_expires_at": CAPTURED + timedelta(seconds=60)}
    first = CollectionRun.objects.create(job=job, ingestion_key="1" * 64, **lifecycle)
    second = CollectionRun.objects.create(job=job, ingestion_key="2" * 64, **lifecycle)
    legacy = {"source_metadata": {"projection_kind": "source-statistics-v1"}}
    typed = {"projection_kind": "source-statistics-v1"}
    fields = {"source_identifier": "lab/Model", "source_subject_kind": "repository", "observation_key": "3" * 64}
    CollectionObservation.objects.create(run=first, **fields, **(legacy if legacy_first else typed))
    with pytest.raises(IntegrityError, match="uq_source_statistics_cross"), transaction.atomic():
        CollectionObservation.objects.create(run=second, **fields, **(typed if legacy_first else legacy))
