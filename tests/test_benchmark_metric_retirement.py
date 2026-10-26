"""Scheduled and direct metric callers with retiring collection columns denied."""
from datetime import date
from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.benchmark_metric_store import persist_source
from core.collection_capture import read_document, run_report_document
from core.collection_scheduling import take_metric_authority
from core.models import CollectionObservation, CollectionRun, MetricValue
from tests.test_benchmark_download_persistence import configured, payload
from tests.test_collection_scheduling import NOW, scheduled
from tests.test_hf_catalog_retirement import denied_retirement_columns

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("fail", [False, True])
def test_shared_scheduler_retains_slot_accounting_and_rows_without_retired_columns(settings, monkeypatch, fail):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    calls = []
    factory = httpx.Client
    def response(request):
        calls.append(str(request.url))
        return httpx.Response(500 if fail else 200, json={
            "id": "lab/Model", "downloads": 0, "downloadsAllTime": 100,
        })
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: factory(transport=httpx.MockTransport(response)))
    monkeypatch.setattr("core.collection_scheduling.timezone.now", lambda: NOW)
    if not fail:
        def checked_command(*args, **kwargs):
            try:
                return call_command(*args, **kwargs)
            except CommandError as exc:
                raise AssertionError(str(exc)) from exc
        monkeypatch.setattr("core.collection_scheduling.call_command", checked_command)
    with denied_retirement_columns():
        output = StringIO()
        call_command("collect_jobs_due", job=str(job.pk), execute=True, stdout=output)
        job.refresh_from_db()
        assert job.last_attempt_id, output.getvalue()
        run = job.last_attempt
        assert run.scheduled_slot_at == NOW.replace(hour=10)
        requests = list(run.attempts.get().requests.order_by("ordinal"))
        assert run.request_count == len(calls) == len(requests) == (3 if fail else 1)
        assert run.physical_bytes_received == sum(request.response_bytes for request in requests) > 0
        report = run_report_document(run)
        assert report["schedule_slot"] == run.scheduled_slot_at.isoformat()
        assert report["physical_bytes_received"] == run.physical_bytes_received
        assert all(request.http_status == (500 if fail else 200) for request in requests)
        request = requests[0]
        scope = run.scopes.get(scope_kind="metric_fetch")
        assert scope.projection_contract_id == job.contract_id
        assert scope.requested_start_date == scope.requested_end_date == NOW.date()
        assert request.archive_id
        if fail:
            assert run.status == "failed" and not MetricValue.objects.exists()
        else:
            assert job.last_success_id == run.pk and run.status == "success"
            assert sorted(MetricValue.objects.values_list("integer_value", flat=True)) == [0, 100]
            assert run.observations.get().inputs.get().input_request_id == request.pk
            call_command("collect_jobs_due", job=str(job.pk), execute=True, stdout=StringIO())
            assert len(calls) == 1 and CollectionRun.objects.count() == 1


def test_direct_import_preserves_timing_and_request_coordinates_without_json_columns():
    contract = configured()
    params = {"start_date": "2026-09-01", "end_date": "2026-09-30", "cursor": "opaque"}
    with denied_retirement_columns():
        run = persist_source(contract, "hf", "a" * 64, payload(), request_params=params)
        assert run.status == "success" and read_document(run.payload_archive) == payload()
        assert run_report_document(run)["schedule_slot"] is None
        assert persist_source(contract, "hf", "a" * 64, payload(), request_params=params).pk == run.pk
        assert CollectionObservation.objects.count() == 1
        scope = run.scopes.get(scope_kind="metric_fetch")
        assert scope.projection_contract_id == contract.pk
        assert (scope.requested_start_date, scope.requested_end_date, scope.cursor) == (
            date(2026, 9, 1), date(2026, 9, 30), "opaque",
        )
        assert not scope.requests.exists()
        cumulative = MetricValue.objects.get(source_metric__metric_key="downloads_all_time")
        assert cumulative.window_start_unknown_reason == "missing_repository_creation"
        assert cumulative.window_end_at == cumulative.observation.observed_at


def test_direct_metric_command_captures_response_without_retired_columns(monkeypatch):
    contract = configured()
    calls = []
    factory = httpx.Client
    def response(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": "lab/Model", "downloads": 5, "downloadsAllTime": 100})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: factory(transport=httpx.MockTransport(response)))
    with denied_retirement_columns():
        call_command("collect_benchmark_metrics", contract=str(contract.pk), source="hf",
                     start_date="2026-10-13", end_date="2026-10-13", apply=True, stdout=StringIO())
        run = CollectionRun.objects.get()
        request = run.attempts.get().requests.get()
        assert run.status == "success" and calls == ["/api/models/lab/Model"]
        assert run.request_count == 1 and run.physical_bytes_received == request.response_bytes
        assert run.observations.get().inputs.get().input_request_id == request.pk
        assert run_report_document(run)["physical_bytes_received"] == request.response_bytes
        assert sorted(MetricValue.objects.values_list("integer_value", flat=True)) == [5, 100]


def test_wrong_scheduler_slot_fails_before_provider_dispatch(settings, monkeypatch):
    job = scheduled(settings)
    monkeypatch.setattr("core.collection_state.timezone.now", lambda: NOW)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: pytest.fail("bad slot started transport"))
    with denied_retirement_columns(), pytest.raises(CommandError, match="schedule slot"):
        call_command("collect_benchmark_metrics", contract=str(job.contract_id), source="hf",
                     start_date="2026-10-13", end_date="2026-10-13", job=str(job.pk),
                     slot="2026-10-12T10:00:00+00:00", apply=True, stdout=StringIO())
