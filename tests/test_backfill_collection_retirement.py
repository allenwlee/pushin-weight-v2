"""Real backfill caller, typed recovery and denied retiring collection columns."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError

from core.collection_capture import archive_legacy, read_document, run_report_document
from core.collection_pages import page_receipts
from core.collection_state import claim_job, finish_run
from core.models import CollectionRequest, CollectionRun, CollectionScopeRun, Post
from monitor.backfill_collection import (
    DurableBudget,
    adopt_completed_backfill_result,
    execute_job,
)
from monitor.backfill_resources import BackfillBudgetExhausted
from tests.test_backfill_collection import (
    pipeline as captured_pipeline,
)
from tests.test_backfill_collection import (
    policy_job,
    ready_job,
)
from tests.test_backfill_pipeline import page
from tests.test_hf_catalog_retirement import denied_retirement_columns
from x_monitor.config import load_config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
pipeline = pytest.fixture(name="pipeline")(captured_pipeline.__wrapped__)


@pytest.fixture(autouse=True)
def on_demand_key(monkeypatch):
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "test-only")


def test_serial_page_resume_report_and_bytes_without_retired_columns(pipeline):
    job = ready_job()
    first_body, second_body = page("1", cursor="next"), page("2")
    pipeline.responses.extend([first_body, second_body])
    with denied_retirement_columns():
        first = execute_job(job.pk)
        original = CollectionRun.objects.get(pk=first["run_id"])
        assert original.physical_bytes_received == len(json.dumps(first_body).encode())
        assert original.scopes.get(scope_kind="x_query").recorded_cursors == ["next"]
        second = execute_job(job.pk)
        assert second["collection_drained"] and second["recovered_post_ids"] == ["1", "2"]
        assert len(pipeline.requests) == 2 and pipeline.requests[1]["cursor"] == "next"
        current = CollectionRun.objects.get(pk=second["run_id"])
        assert current.physical_bytes_received == len(json.dumps(second_body).encode())
        receipts = page_receipts(current.scopes.get(scope_kind="x_query"))
        assert [row["post_ids"] for row in receipts] == [["1"], ["2"]]
        assert run_report_document(current)["post_membership"]["distinct_posts"] == 2
        assert execute_job(job.pk)["report"]["collection_drained"]


@pytest.mark.parametrize("interrupt", [False, True])
def test_model_relevance_replay_survives_failure_without_retired_columns(pipeline, monkeypatch, tmp_path, interrupt):
    job = policy_job(monkeypatch, tmp_path, calls={"A"})
    cfg = load_config(Path("config.yaml"))
    calls = []
    class Client:
        def messages_create_text(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="KEEP", provider_usage={"cost_usd": "0.0001"})
    monkeypatch.setattr("x_monitor.reattribute.build_relevancy_client_from_env", lambda *a, **k: Client())
    with denied_retirement_columns():
        first = claim_job(job.pk, invocation_id="one", manual_authorized=True)
        budget = DurableBudget(first, job, 300)
        assert budget.relevance(cfg)("system", "user") == "KEEP"
        if interrupt:
            finish_run(first, status="failed", typed=True, request_count=0, physical_accounting_complete=False)
            claim = claim_job(job.pk, invocation_id="two", manual_authorized=True, continue_from=first.run_id)
            budget = DurableBudget(claim, job, 300)
        assert budget.relevance(cfg)("system", "user") == "KEEP"
        assert len(calls) == 1
        reserved = CollectionScopeRun.objects.get(scope_kind="x_model_call")
        assert reserved.run_id == first.run_id and reserved.raw_count == 1 and reserved.outcome == "returned"
        assert read_document(reserved.legacy_archive)["usage"] == {"cost_usd": "0.0001"}


def test_unknown_model_outcome_and_historical_reservation_never_get_reissued(pipeline, monkeypatch, tmp_path):
    job = policy_job(monkeypatch, tmp_path, calls={"A"})
    cfg = load_config(Path("config.yaml"))
    identity = hashlib.sha256(json.dumps([cfg.llm.model_dump(mode="json"), "system", "user"], sort_keys=True).encode()).hexdigest()
    first = claim_job(job.pk, invocation_id="historical", manual_authorized=True)
    original = CollectionRun.objects.get(pk=first.run_id)
    old = {"model_requests": job.scope["maximum_model_requests"], "response_bytes": 123,
           "staff_relevance": {identity: {"status": "sent", "model": cfg.llm.relevancy_model}}}
    original.legacy_archive = archive_legacy({"report": old})
    original.save(update_fields=["legacy_archive"])
    finish_run(first, status="failed", report=old)
    with denied_retirement_columns():
        claim = claim_job(job.pk, invocation_id="resume", manual_authorized=True, continue_from=first.run_id)
        budget = DurableBudget(claim, job, 300)
        monkeypatch.setattr("x_monitor.reattribute.build_relevancy_client_from_env", lambda *a, **k: pytest.fail("resent model"))
        with pytest.raises(ValueError, match="outcome unknown"):
            budget.relevance(cfg)("system", "user")
        with pytest.raises(BackfillBudgetExhausted, match="durable model allowance"):
            budget.claim_llm_request()
        assert CollectionScopeRun.objects.get(run_id=first.run_id, scope_kind="x_model_usage").raw_count == old["model_requests"]


def test_archived_prefetch_capture_accounting_crash_replays_once(pipeline, monkeypatch):
    from django.utils import timezone

    from monitor.backfill_prefetch import TransportResult
    body = json.dumps(page("1")).encode()
    calls = []
    def fetch(*a, **k):
        calls.append(True)
        return TransportResult(body, {"raw_results": 1, "response_bytes": len(body), "status_code": 200}, None, timezone.now(), 0.01)
    monkeypatch.setattr("monitor.backfill_prefetch.fetch_page", fetch)
    original = DurableBudget.record_captured_response
    monkeypatch.setattr(DurableBudget, "record_captured_response", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash after capture")))
    job = ready_job()
    with denied_retirement_columns():
        with pytest.raises(CommandError):
            execute_job(job.pk, collection_options={"concurrency": 1})
        request = CollectionRequest.objects.get()
        assert request.selection_accounted is False and request.archive_id is not None
        assert not Post.objects.exists()
        monkeypatch.setattr(DurableBudget, "record_captured_response", original)
        report = execute_job(job.pk)
        request.refresh_from_db()
        owner = CollectionRun.objects.get(pk=request.attempt.run_id)
        assert request.selection_accounted and request.raw_count == owner.selected_count == 1
        assert owner.physical_bytes_received == request.response_bytes == len(body)
        assert report["collection_drained"] and report["usage"]["api_requests"] == 0
        assert len(calls) == Post.objects.count() == 1
        assert execute_job(job.pk)["state"] == "completed"


def _historical_result(job, report):
    run = CollectionRun.objects.get(pk=report["run_id"])
    run.scopes.filter(scope_kind="x_backfill_result").delete()
    run.report = report
    run.legacy_archive = archive_legacy({"report": report})
    run.save(update_fields=["report", "legacy_archive"])
    return run


def test_completed_result_adoption_preserves_exact_evidence_and_execution_owners(pipeline):
    job = ready_job()
    pipeline.responses.append(page("1"))
    report = execute_job(job.pk)
    run = _historical_result(job, report)
    before = (CollectionRun.objects.count(), run.attempts.count(), run.started_at, run.completed_at)
    with denied_retirement_columns():
        copied = adopt_completed_backfill_result(run.pk)
        assert copied == {"run_id": str(run.pk), "copied": True, "distinct_posts": 1}
        assert adopt_completed_backfill_result(run.pk, verify_only=True)["copied"] is False
        run.refresh_from_db()
        assert (CollectionRun.objects.count(), run.attempts.count(), run.started_at, run.completed_at) == before
        marker = run.scopes.get(scope_kind="x_backfill_result")
        assert read_document(marker.legacy_archive) == report
        assert run_report_document(run)["recovered_post_ids"] == ["1"]


@pytest.mark.parametrize("defect", ["missing_empty", "wrong_count", "wrong_post"])
def test_completed_result_adoption_rejects_uncertified_or_mismatched_membership(pipeline, defect):
    job = ready_job(complete=defect == "missing_empty")
    if defect != "missing_empty":
        pipeline.responses.append(page("1"))
    report = execute_job(job.pk)
    if defect == "missing_empty":
        report.pop("post_membership")
    elif defect == "wrong_count":
        report["post_membership"]["distinct_posts"] = 0
    else:
        report["recovered_post_ids"] = ["not-the-typed-post"]
    run = _historical_result(job, report)
    with denied_retirement_columns(), pytest.raises(ValueError, match="historical membership"):
        adopt_completed_backfill_result(run.pk)
    assert not run.scopes.filter(scope_kind="x_backfill_result").exists()
