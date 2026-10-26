"""HF catalog capture/replay without the retiring columns (numeric drain separate)."""

import json
from io import StringIO

import httpx
import pytest
from django.core.management import call_command

from core.collection_capture import (
    observation_object_documents,
    read_document,
    run_report_document,
)
from core.collection_numeric_selection import numeric_fields
from core.model_inventory import execute_model_inventory
from scripts.benchmark_download_collector.sources import Budget
from tests.test_hf_catalog_retirement import denied_retirement_columns
from tests.test_hf_source_ingestion import ingestion_job
from tests.test_source_metric_projection import configured

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def capture_only(monkeypatch):
    # Shared numeric projection has its own retirement task. Real integration
    # remains covered by test_hf_source_ingestion on the additive schema.
    monkeypatch.setattr("core.source_metric_projection.enqueue_projection", lambda *a, **kw: None)
    monkeypatch.setattr("core.source_metric_projection.drain_pending_projections", lambda *a, **kw: {"pending": False})


def client(raw, *, limit=20, calls=None):
    def respond(request):
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path == "/api/models":
            # Inventory keeps the first selected observation and the raw count.
            return httpx.Response(200, json=[raw, {**raw, "downloads": 99}])
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab", "numFollowers": 3})
        return httpx.Response(200, json={**raw, "downloadsAllTime": "invalid" if "blobs" in request.url.params else 99,
                                       "siblings": [{"rfilename": "README.md", "blobId": "abc"}]})

    return Budget(httpx.Client(transport=httpx.MockTransport(respond)), max_requests=limit)


def test_capture_resume_and_command_report_avoid_retiring_columns(capture_only, monkeypatch):
    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    with denied_retirement_columns():
        first = execute_model_inventory(job.pk, budget=client(raw, limit=1))
        assert first.status == "partial"
        assert run_report_document(first)["items_this_invocation"] == 2
        assert run_report_document(first)["total_committed_items"] == 2
        listing = first.observations.get(observation_kind="creation_inventory")
        assert observation_object_documents(listing)[0] == raw
        assert numeric_fields(listing) is None
        assert read_document(listing.legacy_archive)["metadata"] == {"inventory_event": "baseline"}
        calls = []
        resumed = execute_model_inventory(job.pk, budget=client(raw, calls=calls))
        assert resumed.pk == first.pk and resumed.status == "success"
        assert len(calls) == 3 and not any("/api/models?" in url for url in calls)
        report = run_report_document(resumed)
        assert report["items_this_invocation"] == 0 and report["total_committed_items"] == 2
        assert report["bytes_this_invocation"] > 0
        assert report["physical_accounting_complete"] is True
        captures = list(resumed.observations.filter(observation_kind="hf_metadata").order_by("pk"))
        assert [numeric_fields(row) for row in captures] == [["downloadsAllTime"], []]
        assert observation_object_documents(captures[0])[0]["downloadsAllTime"] == "invalid"
        assert captures[0].resource_snapshot.file_change_kind in {"baseline", "setup_or_readme"}
        assert captures[0].resource_snapshot.prior_snapshot_id is None
        from core.collection_numeric_selection import (
            hf_numeric_selection_integrity_counts,
            project_hf_numeric_selections_batch,
        )
        from core.collection_resources import resource_snapshot_values

        assert resource_snapshot_values(captures[0])["file_change_kind"] == captures[0].resource_snapshot.file_change_kind
        assert project_hf_numeric_selections_batch(verify_only=True).scanned == 0
        assert hf_numeric_selection_integrity_counts() == {"unprojected": 0, "invalid_selection_owners": 0}
        assert read_document(captures[0].legacy_archive)["metadata"]["file_changes"]["changed_paths"] == ["README.md"]
        monkeypatch.setattr("core.management.commands.collect_model_inventory.execute_model_inventory", lambda *a, **kw: resumed)
        out = StringIO()
        call_command("collect_model_inventory", job=str(job.pk), execute=True, stdout=out)
        assert json.loads(out.getvalue())["report"] == report


@pytest.mark.parametrize("tamper", ["position", "checksum", "request_scope", "parent"])
def test_inventory_replay_rejects_changed_capture_ownership(capture_only, tamper):
    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    with denied_retirement_columns():
        run = execute_model_inventory(job.pk, budget=client(raw))
        listing = run.observations.get(observation_kind="creation_inventory")
        target = listing
        edge = listing.inputs.get(input_role="hf_inventory_capture")
        if tamper == "position":
            edge.row_locator = "01"
            edge.save(update_fields=["row_locator"])
        elif tamper == "checksum":
            edge.input_sha256 = "f" * 64
            edge.save(update_fields=["input_sha256"])
        elif tamper == "request_scope":
            edge.input_request = run.scopes.get(scope_kind="hf_profile").requests.get()
            edge.input_sha256 = edge.input_request.archive.content_sha256
            edge.save(update_fields=["input_request", "input_sha256"])
        else:
            target = run.observations.filter(observation_kind="hf_metadata").first()
            target.scope_run.resource_observation = None
            target.scope_run.save(update_fields=["resource_observation"])
        with pytest.raises(ValueError, match="HF"):
            observation_object_documents(target)


def test_historical_listing_resume_uses_archived_object_without_provider_refetch(capture_only):
    from core.collection_capture import archive_legacy

    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    first = execute_model_inventory(job.pk, budget=client(raw, limit=1))
    listing = first.observations.get(observation_kind="creation_inventory")
    documents = observation_object_documents(listing)
    listing.legacy_archive = archive_legacy(dict(zip(("listing", "dimensions", "source_metadata"), documents)))
    listing.save(update_fields=["legacy_archive"])
    with denied_retirement_columns():
        calls = []
        resumed = execute_model_inventory(job.pk, budget=client(raw, calls=calls))
        assert resumed.status == "success" and len(calls) == 3
        assert observation_object_documents(resumed.observations.get(pk=listing.pk))[0] == raw
        assert run_report_document(resumed)["total_committed_items"] == 2


def test_archive_sweep_preserves_typed_inventory_evidence_and_copies_legacy_neighbor(capture_only):
    from core.collection_storage_migration import (
        archive_legacy_batch,
        stale_legacy_archive_count,
    )
    from core.measurement_taxonomy import digest
    from core.models import CollectionObservation

    contract, raw, _, _ = configured()
    run = execute_model_inventory(ingestion_job(contract).pk, budget=client(raw))
    pointers = dict(run.observations.values_list("pk", "legacy_archive_id"))
    assert stale_legacy_archive_count("collection_observations", batch_size=1) == 0
    assert archive_legacy_batch("collection_observations", repair_stale=True).selected == 0
    legacy = CollectionObservation.objects.create(
        run=run, source_subject_kind="repository", source_identifier="lab/old",
        observation_key=digest(["historical-neighbor"]), listing={"id": "lab/old"},
    )
    assert stale_legacy_archive_count("collection_observations", batch_size=1) == 1
    assert archive_legacy_batch("collection_observations", repair_stale=True).selected == 1
    assert stale_legacy_archive_count("collection_observations", batch_size=1) == 0
    assert dict(run.observations.exclude(pk=legacy.pk).values_list("pk", "legacy_archive_id")) == pointers
