"""Native inventory resumes and replays with all retiring collection fields denied."""

import json
from datetime import UTC, datetime
from io import StringIO

import httpx
import pytest
from django.core.management import call_command

from core.collection_capture import (
    observation_object_documents,
    read_document,
    run_report_document,
)
from core.model_inventory import execute_model_inventory, inventory_report
from core.models import (
    CollectionObservationInput,
    CollectionRequest,
    CollectionRun,
    MetricValue,
    Product,
)
from scripts.benchmark_download_collector.sources import Budget
from tests.test_hf_catalog_retirement import denied_retirement_columns
from tests.test_model_inventory import inventory_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def row(identity="publisher/model"):
    return {
        "id": identity,
        "canonical_slug": identity + "-different",
        "created": 1700000000,
    }


def client(handler, *, limit=10):
    return Budget(
        httpx.Client(transport=httpx.MockTransport(handler)),
        max_requests=limit,
        sleep=lambda _: None,
    )


def pages(seen, *, repeated=False):
    def respond(request):
        seen.append(str(request.url))
        assert request.url.params["model_authors"] == "publisher"
        assert request.headers["authorization"] == "Bearer fixture-project"
        later = request.url.params["offset"] == "1"
        return httpx.Response(
            200,
            json={
                "data": [
                    row(
                        "publisher/model"
                        if repeated or not later
                        else "publisher/second"
                    )
                ],
                "links": {
                    "next": None
                    if later
                    else "https://openrouter.ai/api/v1/models?offset=1&limit=500"
                },
                "total_count": 2,
            },
        )

    return respond


def test_openrouter_partial_resume_preserves_native_ids_clocks_and_physical_report(
    monkeypatch,
):
    job = inventory_job("openrouter", {"authors": ["publisher"]})
    seen = []
    with denied_retirement_columns():
        first = execute_model_inventory(
            job.pk, budget=client(pages(seen), limit=1), key="fixture-project"
        )
        assert first.status == "partial" and first.error_code == "request_cap", (
            inventory_report(first)
        )
        report = run_report_document(first)
        assert report["items_this_invocation"] == report["total_committed_items"] == 1
        scope = first.scopes.get(scope_kind="model_catalog")
        assert scope.cursor == "1" and scope.recorded_cursors == ["0"]
        original = first.observations.get()
        original_time = original.observed_at
        resumed = execute_model_inventory(
            job.pk, budget=client(pages(seen)), key="fixture-project"
        )
        assert resumed.pk == first.pk and resumed.status == "success"
        assert resumed.request_count == len(seen) == 2
        assert resumed.selected_count == resumed.success_count == 1
        report = inventory_report(resumed)
        assert report == run_report_document(resumed)
        assert (
            report["items_this_invocation"] == 1
            and report["total_committed_items"] == 2
        )
        assert report["physical_accounting_complete"] is True
        assert (
            report["catalog_is_release_adjudication"]
            is report["usage_mapping_inferred"]
            is False
        )
        assert (
            report["missing_numeric_fields"] == []
            and report["numeric_projection"] is None
        )
        original.refresh_from_db()
        assert original.observed_at == original_time
        assert observation_object_documents(original)[0] == row()
        assert original.resource_snapshot.provider_created_at == datetime.fromtimestamp(
            1700000000, UTC
        )
        assert (
            original.source_identifier
            != observation_object_documents(original)[2]["canonical_slug"]
        )
        assert original.legacy_archive_id is None
        assert Product.objects.count() == MetricValue.objects.count() == 0
        for observation in resumed.observations.all():
            receipt = observation.inputs.get(
                input_role="openrouter_catalog_object"
            ).input_request
            assert receipt.archive_id is not None
            assert len(read_document(receipt.archive)["data"]) == 1
            assert receipt.raw_count is None  # Reserved for X staging receipts.
        scope.refresh_from_db()
        assert scope.recorded_cursors == ["0", "1"] and scope.cursor is None
        assert scope.enumeration_complete and scope.raw_count == 2
        assert sorted(resumed.attempts.values_list("actual_items", flat=True)) == [1, 1]
        monkeypatch.setattr(
            httpx.Client, "send", lambda *a, **kw: pytest.fail("replay fetched HTTP")
        )
        assert [
            observation_object_documents(item)[0]
            for item in resumed.observations.order_by("pk")
        ] == [row(), row("publisher/second")]


def test_repeated_page_object_keeps_first_capture_without_losing_raw_count():
    job = inventory_job("openrouter", {"authors": ["publisher"]})
    seen = []
    with denied_retirement_columns():
        run = execute_model_inventory(
            job.pk, budget=client(pages(seen, repeated=True)), key="fixture-project"
        )
        assert run.status == "success" and run.observations.count() == 1, (
            inventory_report(run)
        )
        observation = run.observations.get()
        assert observation.inputs.count() == 1
        assert observation.inputs.get().input_request.cursor_before is None
        assert (
            run.request_count == 2
            and run_report_document(run)["total_committed_items"] == 2
        )
        assert observation_object_documents(observation)[0] == row()


def test_retry_and_empty_success_remain_distinct_from_absence_due_to_error():
    job = inventory_job("openrouter", {"authors": []})
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return (
            httpx.Response(429)
            if len(calls) == 1
            else httpx.Response(200, json={"data": [], "total_count": 0})
        )

    with denied_retirement_columns():
        run = execute_model_inventory(
            job.pk, budget=client(respond), key="fixture-project"
        )
        assert run.status == "success" and run.request_count == 2
        assert run.observations.count() == MetricValue.objects.count() == 0
        assert list(
            run.attempts.get()
            .requests.order_by("ordinal")
            .values_list("http_status", flat=True)
        ) == [429, 200]
        assert run_report_document(run)["items_this_invocation"] == 0
        assert run.scopes.get(scope_kind="model_catalog").enumeration_complete


def test_malformed_catalog_records_typed_diagnostic_without_committing_rows():
    job = inventory_job("openrouter", {"authors": []})
    with denied_retirement_columns():
        run = execute_model_inventory(
            job.pk,
            budget=client(
                lambda _: httpx.Response(200, json={"data": [row()], "total_count": 0})
            ),
            key="fixture-project",
        )
        assert (
            run.status == "partial"
            and run.error_code == "invalid_or_unqualified_catalog"
        )
        report = run_report_document(run)
        assert report["catalog_error"] == "invalid catalog total"
        assert report["total_committed_items"] == report["items_this_invocation"] == 0
        assert not run.observations.exists()
        assert run.attempts.get().requests.get().archive_id is not None


def test_unadopted_openrouter_scope_stops_before_provider_dispatch():
    job = inventory_job("openrouter", {"authors": ["publisher"]})
    with denied_retirement_columns():
        first = execute_model_inventory(
            job.pk, budget=client(pages([]), limit=1), key="fixture-project"
        )
        first.scopes.filter(scope_kind="model_catalog").update(phase=None)
        run = execute_model_inventory(
            job.pk,
            budget=client(lambda _: pytest.fail("unadopted scope fetched HTTP")),
            key="fixture-project",
        )
        assert run.status == "partial" and run.request_count == 1
        assert run_report_document(run)["items_this_invocation"] == 0


@pytest.mark.parametrize(
    "tamper",
    [
        "position",
        "checksum",
        "native_id",
        "request_owner",
        "authors",
        "request_method",
        "receipt_kind",
    ],
)
def test_openrouter_replay_rejects_corrupted_native_capture(tamper):
    job = inventory_job("openrouter", {"authors": ["publisher"]})
    with denied_retirement_columns():
        run = execute_model_inventory(
            job.pk, budget=client(pages([])), key="fixture-project"
        )
        observation = run.observations.order_by("pk").first()
        edge = observation.inputs.get(input_role="openrouter_catalog_object")
        if tamper == "position":
            CollectionObservationInput.objects.filter(pk=edge.pk).update(
                row_locator="01"
            )
        elif tamper == "checksum":
            CollectionObservationInput.objects.filter(pk=edge.pk).update(
                input_sha256="a" * 64
            )
        elif tamper == "native_id":
            observation.source_identifier = "publisher/different"
        else:
            request = edge.input_request
            if tamper == "request_owner":
                other = CollectionRequest.objects.create(
                    attempt=request.attempt,
                    scope_run=run.scopes.get(scope_kind="inventory_execution"),
                    ordinal=3,
                    http_method="GET",
                    endpoint_url=request.endpoint_url,
                    transport_outcome="received",
                    http_status=200,
                    archive=request.archive,
                    request_group=request.request_group,
                    cursor_before=request.cursor_before,
                )
                edge.input_request = other
                edge.save(update_fields=["input_request"])
            elif tamper == "authors":
                request.endpoint_url = request.endpoint_url.replace(
                    "model_authors=publisher", "model_authors=stranger"
                )
                request.save(update_fields=["endpoint_url"])
            else:
                field = "http_method" if tamper == "request_method" else "receipt_kind"
                setattr(
                    request,
                    field,
                    "POST" if field == "http_method" else "legacy_receipt",
                )
                request.save(update_fields=[field])
        with pytest.raises(ValueError, match="OpenRouter"):
            observation_object_documents(observation)


@pytest.mark.parametrize("entrypoint", ["command", "scheduler"])
def test_inventory_entrypoint_returns_typed_openrouter_report(monkeypatch, entrypoint):
    job = inventory_job("openrouter", {"authors": ["publisher"]})
    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(pages([])))
    )
    monkeypatch.setenv("BENCHMARK_OPENROUTER_API_KEY", "fixture-project")
    with denied_retirement_columns():
        if entrypoint == "command":
            output = StringIO()
            call_command(
                "collect_model_inventory", job=str(job.pk), execute=True, stdout=output
            )
            result = json.loads(output.getvalue())
            run = CollectionRun.objects.get(pk=result["run_id"])
        else:
            from core.collection_scheduling import execute_due_job

            run = execute_due_job(job, {}, Budget(httpx.Client()))
            result = {"status": run.status, "report": run_report_document(run)}
        assert result["status"] == "success" and result["report"] == inventory_report(
            run
        )


def test_hf_metadata_parent_is_checked_before_retry_dispatch():
    from core.models import TimeZone
    from tests.test_hf_inventory_retirement import client as hf_client
    from tests.test_hf_source_ingestion import ingestion_job
    from tests.test_source_metric_projection import configured

    TimeZone.objects.get_or_create(pk="UTC")
    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    with denied_retirement_columns():
        first = execute_model_inventory(job.pk, budget=hf_client(raw, limit=1))
        scope = first.scopes.get(
            scope_kind="hf_metadata", scope_key=raw["id"] + ":detail"
        )
        scope.resource_observation = None
        scope.save(update_fields=["resource_observation"])
        calls = []
        resumed = execute_model_inventory(job.pk, budget=hf_client(raw, calls=calls))
        assert (
            resumed.status == "partial"
            and resumed.error_code == "invalid_or_unqualified_catalog"
        )
        assert calls == []
