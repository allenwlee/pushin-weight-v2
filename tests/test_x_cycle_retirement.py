"""Scheduled capture and settled same-slot adoption without collection JSON."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.test import override_settings

from core.collection_capture import archive_legacy, read_document, run_report_document
from core.collection_jobs import set_job_state
from core.collection_state import BusyJob, claim_job, finish_run
from core.models import CollectionRun, Post
from core.x_cycle_lineage import ScheduledCycleLineage, register_scheduled_cycle
from tests.test_hf_catalog_retirement import denied_retirement_columns

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 10, 27, 0, 1, tzinfo=UTC)
CALL = SimpleNamespace(call_id="B1", query_string="product release")
LIMITS = {"requests": 10, "bytes": 100000, "seconds": 300, "items": 100}


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.now", lambda: NOW)


def archive_run_document(run, report):
    """Construct the retained historical shape after the old ORM fields retire."""
    run.legacy_archive = archive_legacy({"report": report, "invocations": [],
                                       "request_params": {}, "source_metadata": {}, "raw_payload": None})
    run.save(update_fields=["legacy_archive"])
    run.scopes.filter(scope_kind="x_cycle_execution").delete()


def legacy_partial():
    job = set_job_state(register_scheduled_cycle([CALL], limits=LIMITS).pk, "ready")
    claim = claim_job(job.pk, invocation_id="old", manual_authorized=True, typed=True)
    lineage = ScheduledCycleLineage(claim)
    scope_id = lineage.begin_call(CALL, since_epoch=1783809000, until_epoch=1783809300)
    request = lineage.begin_exchange(scope_id, endpoint_url="https://api.twitterapi.io/twitter/tweet/advanced_search",
                                     params={"query": CALL.query_string})
    lineage.finish_exchange(request, {"outcome": "received", "status_code": 200,
                                     "body": b'{"tweets":[{"id":"saved"}]}', "error_type": None})
    post = Post.objects.create(tweet_id="saved", text="product release")
    lineage.finish_call(scope_id, post_ids=[post.pk], page_by_post={str(post.pk): 1},
                        raw_count=1, outcome="truncated", complete=False)
    run = finish_run(claim, status="partial", request_count=1, typed=True,
                     physical_accounting_complete=True)
    archive_run_document(run, {"physical_accounting_complete": True})
    scope = run.scopes.get(scope_kind="x_query")
    scope.phase = None
    scope.legacy_archive = archive_legacy({"ownership": {}, "cursor_history": [], "envelopes": []})
    scope.save(update_fields=["phase", "legacy_archive"])
    row = run.observations.get()
    row.legacy_archive = archive_legacy({"listing": {}, "dimensions": {}, "source_metadata": {},
                                       "groups": {}, "envelopes": []})
    row.save(update_fields=["legacy_archive"])
    return run, scope, request


def test_same_slot_adoption_preserves_original_capture_and_adds_only_an_attempt(clock):
    original, scope, request = legacy_partial()
    original_attempt = original.attempts.get()
    with denied_retirement_columns():
        lineage = ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="typed-resume")
        assert lineage.claim.run_id == original.pk
        resumed = CollectionRun.objects.get(pk=original.pk)
        marker = resumed.scopes.get(scope_kind="x_cycle_execution")
        assert read_document(marker.legacy_archive)["report"] == {"physical_accounting_complete": True}
        assert resumed.started_at == original.started_at and resumed.scheduled_slot_at == original.scheduled_slot_at
        assert resumed.attempts.count() == 2 and resumed.attempts.get(pk=original_attempt.pk).actual_requests == 1
        assert resumed.scopes.get(scope_kind="x_query").pk == scope.pk
        assert resumed.observations.get().inputs.get().input_request_id == request.pk
        assert sum(attempt.requests.count() for attempt in resumed.attempts.all()) == 1
        lineage.finish(success=False)
        assert run_report_document(resumed) == {"physical_accounting_complete": True}


@pytest.mark.parametrize("defect", ["counter", "accounting_flag", "report", "scope", "missing_archive"])
def test_same_slot_adoption_rejects_changed_or_unavailable_evidence_atomically(clock, defect):
    original, scope, _ = legacy_partial()
    if defect == "counter":
        original.attempts.update(actual_requests=2)
    elif defect == "accounting_flag":
        original.attempts.update(accounting_complete=False)
    elif defect == "scope":
        scope.requested_end_at += timedelta(seconds=1)
        scope.save(update_fields=["requested_end_at"])
    elif defect == "report":
        original.legacy_archive = archive_legacy({"report": {"unexpected": True}, "invocations": [],
                                               "request_params": {}, "source_metadata": {}, "raw_payload": None})
        original.save(update_fields=["legacy_archive"])
    else:
        original.legacy_archive = None
        original.save(update_fields=["legacy_archive"])
    with denied_retirement_columns(), pytest.raises(ValueError, match="scheduled legacy"):
        ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="refused")
    original.refresh_from_db()
    assert original.status == "partial" and original.attempts.count() == 1
    assert not original.scopes.filter(scope_kind="x_cycle_execution").exists()


def test_new_slot_does_not_require_adopting_prior_run(clock, monkeypatch):
    original, _, _ = legacy_partial()
    original.legacy_archive = None
    original.save(update_fields=["legacy_archive"])
    monkeypatch.setattr("django.utils.timezone.now", lambda: NOW + timedelta(minutes=15))
    with denied_retirement_columns():
        fresh = ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="next-slot")
        assert fresh.claim.run_id != original.pk
        assert not original.scopes.filter(scope_kind="x_cycle_execution").exists()
        fresh.finish(success=False)


def test_running_legacy_cycle_remains_busy_without_adoption(clock):
    job = set_job_state(register_scheduled_cycle([CALL], limits=LIMITS).pk, "ready")
    claim = claim_job(job.pk, invocation_id="still-running", manual_authorized=True, typed=True)
    original = CollectionRun.objects.get(pk=claim.run_id)
    original.scopes.filter(scope_kind="x_cycle_execution").delete()
    with denied_retirement_columns(), pytest.raises(BusyJob, match="lease is active"):
        ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="too-soon")
    assert original.attempts.count() == 1 and not original.scopes.exists()


def test_pending_legacy_transport_cannot_be_adopted_as_settled(clock):
    job = set_job_state(register_scheduled_cycle([CALL], limits=LIMITS).pk, "ready")
    claim = claim_job(job.pk, invocation_id="unsettled", manual_authorized=True, typed=True)
    lineage = ScheduledCycleLineage(claim)
    scope_id = lineage.begin_call(CALL, since_epoch=1783809000, until_epoch=1783809300)
    lineage.begin_exchange(scope_id, endpoint_url="https://api.twitterapi.io/twitter/tweet/advanced_search",
                           params={"query": CALL.query_string})
    original = finish_run(claim, status="partial", request_count=0, typed=True,
                          physical_accounting_complete=False)
    archive_run_document(original, {"physical_accounting_complete": False})
    scope = original.scopes.get(scope_kind="x_query")
    scope.phase = None
    scope.legacy_archive = archive_legacy({"ownership": {}, "cursor_history": [], "envelopes": []})
    scope.save(update_fields=["phase", "legacy_archive"])
    with denied_retirement_columns(), pytest.raises(ValueError, match="request owner or outcome"):
        ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="refused")
    assert original.attempts.count() == 1
    assert not original.scopes.filter(scope_kind="x_cycle_execution").exists()


def test_expired_typed_attempt_with_pending_transport_refuses_same_slot_reclaim(clock, monkeypatch):
    with denied_retirement_columns():
        first = ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="pending-first")
        scope_id = first.begin_call(CALL, since_epoch=1783809000, until_epoch=1783809300)
        request = first.begin_exchange(
            scope_id, endpoint_url="https://api.twitterapi.io/twitter/tweet/advanced_search",
            params={"query": CALL.query_string},
        )
        monkeypatch.setattr("django.utils.timezone.now", lambda: NOW + timedelta(seconds=400))
        with pytest.raises(ValueError, match="previous request receipt is unfinished"):
            ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="pending-retry")
        original = CollectionRun.objects.get(pk=first.claim.run_id)
        assert original.attempts.count() == 1
        assert original.attempts.get().actual_requests == 0
        request.refresh_from_db()
        assert request.transport_outcome == "pending" and request.archive_id is None
        # The completion boundary also rejects an older pending receipt if a
        # caller acquired the shared claim directly instead of through start.
        direct = claim_job(original.job_id, invocation_id="direct-retry", manual_authorized=True, typed=True)
        assert original.attempts.count() == 2
        with pytest.raises(ValueError, match="request receipt is unfinished"):
            ScheduledCycleLineage(direct).finish(success=True)
        # An unrelated later slot can still proceed, retaining the unknown old receipt.
        monkeypatch.setattr("django.utils.timezone.now", lambda: NOW + timedelta(minutes=15))
        fresh = ScheduledCycleLineage.start([CALL], limits=LIMITS, invocation_id="later-slot")
        assert fresh.claim.run_id != original.pk
        fresh.finish(success=False)


def test_scheduled_runner_preserves_actual_request_post_and_accounting_without_retired_columns(
    monkeypatch, seeded_policy_keywords,
):
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner
    from scripts.harvest_cost import emit as cost_emit
    from x_monitor.config import load_config

    item = {"id": "typed-cycle", "author_id": "typed-author", "author_handle": "typed_author",
            "text": "Qwen3 released", "lang": "en", "created_at": "Sat Jul 25 12:00:00 +0000 2026"}
    body = json.dumps({"tweets": [item]}).encode()
    calls = []
    class Api:
        base_url = "https://api.twitterapi.io"
        timeout_s = 60
        max_retries = 0
        def run_search(self, query, **kwargs):
            calls.append((query, kwargs))
            request = self.on_exchange_start("/twitter/tweet/advanced_search", {"query": query})
            self.on_exchange_finish(request, {"outcome": "received", "status_code": 200,
                                               "body": body, "error_type": None})
            return [item], False
    plan = CycleRunner._plan_calls
    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda runner: plan(runner)[1:2])
    monkeypatch.setattr(cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls, purpose: Api()))
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda *a, **k: {})
    monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *a, **k: None)
    monkeypatch.setattr("monitor.metrics_refresh.run_metrics_refresh", lambda *a, **k: {})
    with denied_retirement_columns(), override_settings(
        X_MONITOR_CYCLE_SINCE_TIME=1785067200, X_MONITOR_CYCLE_UNTIL_TIME=1785067260,
        X_MONITOR_CYCLE_SKIP_FETCH=False,
    ):
        result = CycleRunner(cfg=load_config(Path("config.yaml")), cycle_kind="scheduled").run()
        assert "scheduled_lineage" not in result["degraded"]
        run = CollectionRun.objects.get(job__operation="x_cycle")
        assert len(calls) == run.request_count == 1
        assert calls[0][1]["since_time"] == 1785067200 and calls[0][1]["until_time"] == 1785067260
        request = run.attempts.get().requests.get()
        assert bytes(request.archive.body) == body and request.response_bytes == len(body)
        row = run.observations.get(source_subject_kind="post")
        assert row.post_id == item["id"] and row.inputs.get().input_request_id == request.pk
        assert row.projection_kind == "typed-x-membership-v1"
        assert run_report_document(run) == {"physical_accounting_complete": True}
