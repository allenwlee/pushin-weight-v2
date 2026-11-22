"""Staging transport through real HTTP, PostgreSQL and the shared page writer."""
import copy
import re
import threading
import time

import pytest
from django.conf import settings
from django.core.management.base import CommandError

from core.collection_jobs import register_job, set_job_state
from core.collection_staging import staging_receipt
from core.models import (
    CollectionEvidenceArchive,
    CollectionObservation,
    CollectionRequest,
    CollectionScopeRun,
    Post,
)
from monitor.backfill_collection import PageCheckpoint, execute_job
from tests.test_backfill_pipeline import page
from tests.test_backfill_prefetch import (  # noqa: F401
    http_pages,
    job_for_scopes,
    pipeline,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

# Only execution/checkpoint/model receipts may accompany lightweight X pages.
DERIVED_ARCHIVE_KINDS = {'legacy_snapshot', 'x_checkpoint_import', 'x_backfill_result', 'x_model_response'}


def staged_job(monkeypatch, count, **kwargs):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    seed = job_for_scopes(count, **kwargs)
    definition = copy.deepcopy(seed.definition)
    definition["scope"].update(response_storage="staging", staging_host=settings.DATABASES["default"]["HOST"])
    job = register_job(job_key="staging-test", source=seed.source, purpose="content", operation="x_backfill",
                       mode="historical", definition=definition)
    return set_job_state(job.pk, "ready")


def result_for(params):
    return page(re.search(r"marker(\d+)", params["query"]).group(1))


def test_twenty_simultaneous_requests_without_body_archives(http_pages, monkeypatch):  # noqa: F811
    barrier = threading.Barrier(20)
    job = staged_job(monkeypatch, 20)
    def response(params):
        barrier.wait(timeout=25)
        return result_for(params)
    with http_pages(response) as state:
        report = execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 20})
    assert state["peak"] == 20
    assert report["collection_drained"]
    assert report["prefetch"]["max_buffered"] == 20
    assert Post.objects.count() == CollectionObservation.objects.filter(run_id=report["run_id"], source_subject_kind="post").count() == 20
    # Derived execution/checkpoint evidence has its own archive kinds.
    assert not CollectionEvidenceArchive.objects.exclude(capture_kind__in=DERIVED_ARCHIVE_KINDS).exists()
    assert CollectionRequest.objects.filter(request_category="x_backfill_staging", archive__isnull=True,
        transport_outcome="received", accounting_complete=True).count() == 20
    from core.models import CollectionScopeRequestUse

    assert CollectionScopeRequestUse.objects.filter(scope_run__run_id=report["run_id"], scope_run__scope_kind="x_query").count() == 20
    job.refresh_from_db()
    receipts = [staging_receipt(request) for request in CollectionRequest.objects.filter(attempt__run=job.last_attempt)]
    assert len(receipts) == 20
    assert all(len(r["returned_ids"]) == r["raw_count"] == 1 for r in receipts)
    from core.collection_capture import run_report_document

    assert "staging_responses" not in run_report_document(job.last_attempt)


def test_fast_page_commits_and_refills_before_slow_request_finishes(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 3)
    refill = threading.Event()
    committed = threading.Event()
    original = PageCheckpoint.persist
    def persist(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        if self.scoped.scope_key == "B1:1":
            committed.set()
        return value
    monkeypatch.setattr(PageCheckpoint, "persist", persist)
    def response(params):
        i = re.search(r"marker(\d+)", params["query"]).group(1)
        if i == "0":
            assert refill.wait(20), "whole-wave barrier retained"
            assert committed.is_set(), "refilled before committing the completed page"
        if i == "2":
            refill.set()
        return result_for(params)
    with http_pages(response) as state:
        report = execute_job(job.pk, collection_options={"concurrency": 2})
    assert report["collection_drained"]
    assert len(state["requests"]) == Post.objects.count() == 3
    assert report["prefetch"]["max_buffered"] <= 2


@pytest.mark.parametrize("after_commit", [False, True])
def test_interrupted_page_retries_only_when_uncommitted(http_pages, monkeypatch, after_commit):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    original = PageCheckpoint.persist
    def crash(self, *args, **kwargs):
        if after_commit:
            original(self, *args, **kwargs)
        raise RuntimeError("fixture interruption")
    monkeypatch.setattr(PageCheckpoint, "persist", crash)
    with http_pages(result_for) as state:
        with pytest.raises(CommandError):
            execute_job(job.pk)
        assert Post.objects.count() == int(after_commit)
        received = CollectionRequest.objects.get(request_category="x_backfill_staging")
        assert received.raw_count == received.received_appearances.count() == 1
        assert received.selection_accounted and received.body_lost is False
        assert received.received_appearances.get().scope_run_id is None
        scope = CollectionScopeRun.objects.filter(run__job=job, scope_kind="x_query").latest("id")
        assert scope.enumeration_complete == after_commit
        # Typed receipt and request-use state alone survive a restart.
        monkeypatch.setattr(PageCheckpoint, "persist", original)
        report = execute_job(job.pk)
    assert report["collection_drained"]
    assert len(state["requests"]) == (1 if after_commit else 2)
    assert report["prefetch"]["lost_responses"] == int(not after_commit)
    assert Post.objects.count() == 1
    assert not CollectionEvidenceArchive.objects.exclude(capture_kind__in=DERIVED_ARCHIVE_KINDS).exists()


def test_unknown_outcome_is_not_automatically_refetched(http_pages, monkeypatch):  # noqa: F811
    from monitor.backfill_staging import StagingPrefetcher
    job = staged_job(monkeypatch, 1)
    original = StagingPrefetcher._save
    monkeypatch.setattr(StagingPrefetcher, "_save", lambda *a: (_ for _ in ()).throw(RuntimeError("receipt lost")))
    with http_pages(result_for) as state:
        with pytest.raises(CommandError):
            execute_job(job.pk)
        monkeypatch.setattr(StagingPrefetcher, "_save", original)
        with pytest.raises(CommandError, match="ValueError"):
            execute_job(job.pk)
    assert len(state["requests"]) == 1
    assert CollectionRequest.objects.get(request_category="x_backfill_staging").transport_outcome == "pending"


@pytest.mark.parametrize("fault", ["environment", "host"])
def test_wrong_target_refused_before_paid_request(http_pages, monkeypatch, fault):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    if fault == "environment":
        monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    else:
        monkeypatch.setitem(settings.DATABASES["default"], "HOST", "different-host")
    with pytest.raises(ValueError, match="staging"):
        execute_job(job.pk)
    assert not CollectionRequest.objects.exists()


def test_error_drains_every_started_request_and_keeps_cursors(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 3)
    barrier = threading.Barrier(3)
    def response(params):
        barrier.wait(timeout=20)
        if "marker0" in params["query"]:
            return 403, {"error": "denied"}
        time.sleep(0.2)
        return result_for(params)
    with http_pages(response) as state, pytest.raises(CommandError):
        execute_job(job.pk, collection_options={"concurrency": 3})
    assert len(state["requests"]) == 3
    assert CollectionRequest.objects.filter(transport_outcome="received").count() == 3
    assert not CollectionEvidenceArchive.objects.exclude(capture_kind__in=DERIVED_ARCHIVE_KINDS).exists()
    assert not CollectionScopeRun.objects.filter(run__job=job, scope_kind='x_query', enumeration_complete=True).exists()


def test_underfilled_pages_follow_cursor_and_deduplicate(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    def response(params):
        return page("same", cursor=None if params.get("cursor") else "next")
    with http_pages(response) as state:
        report = execute_job(job.pk, collection_options={"concurrency": 2})
    assert report["collection_drained"] and len(state["requests"]) == 2
    assert Post.objects.count() == CollectionObservation.objects.filter(run_id=report["run_id"], source_subject_kind="post").count() == 1


@pytest.mark.parametrize("kept", [False, True])
def test_staging_rare_gate_still_controls_admission(http_pages, monkeypatch, tmp_path, kept):  # noqa: F811
    from decimal import Decimal

    from core.models import RareTypeSearchHit
    from tests.test_backfill_collection import policy_job
    from x_monitor.jev_decisions import QUESTION_SET, JevDecisionsClient, JevResponse

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-only")
    template = policy_job(monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True,
                          selected_calls=["RARE_EXTRA"])
    definition = copy.deepcopy(template.definition)
    definition["scope"].update(response_storage="staging", staging_host=settings.DATABASES["default"]["HOST"])
    job = register_job(job_key="staging-rare-test", source=template.source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    set_job_state(job.pk, "ready")
    calls = []
    def decide(self, request_bytes, **kwargs):
        calls.append(request_bytes)
        probabilities = dict.fromkeys(QUESTION_SET, .1)
        if kept:
            probabilities.update(ai_related=.95, role_opening=.95)
        return JevResponse("fixture", probabilities, 1200, 0, Decimal("0.00005"))
    monkeypatch.setattr(JevDecisionsClient, "submit", decide)
    with http_pages(lambda p: page("rare-staging")):
        report = execute_job(job.pk, collection_options={"concurrency": 20})
    assert report["collection_drained"] and report["rare_gate_pending"] == 0
    assert len(calls) == 1
    assert Post.objects.filter(pk="rare-staging").exists() == kept
    assert CollectionObservation.objects.filter(run__job=job, post_id="rare-staging").exists() == kept
    assert RareTypeSearchHit.objects.get(provider_post_id="rare-staging").gate_state == ("kept" if kept else "junk")
    assert not CollectionEvidenceArchive.objects.exclude(capture_kind__in=DERIVED_ARCHIVE_KINDS).exists()


def test_staging_request_ceiling_survives_resume(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 3, request_cap=1, maximum=1)
    with http_pages(result_for) as state:
        first = execute_job(job.pk, collection_options={"concurrency": 20})
        second = execute_job(job.pk, collection_options={"concurrency": 20})
    assert len(state["requests"]) == 1
    assert not first["collection_drained"] and not second["collection_drained"]
    assert second["cumulative_api_requests"] == 1


def test_no_bytes_for_concurrent_responses_makes_no_request(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 2, byte_cap=1)
    with http_pages(lambda p: pytest.fail("insufficient byte allowance")) as state:
        execute_job(job.pk, collection_options={"concurrency": 20})
    assert not state["requests"]
    assert not CollectionRequest.objects.exists()


def test_staging_uses_twex_after_both_twitter_circuits_fail(pipeline, monkeypatch):  # noqa: F811
    import json
    from datetime import UTC, datetime
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    from monitor.backfill_prefetch import PrefetchRoute, TransportResult
    from tests.test_backfill_prefetch import REAL_FROM_ENV

    job = staged_job(monkeypatch, 1)
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-ondemand")
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fixture-scheduled")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fixture-twex")
    monkeypatch.setenv("TWEXAPI_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    monkeypatch.setattr(XClient, "from_env", classmethod(REAL_FROM_ENV))
    router = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    for circuit in router.provider_circuits.values():
        circuit.record_failure(datetime.now(UTC))
    calls = []
    def fetch(route, params, *, max_bytes, timeout):
        assert isinstance(route, PrefetchRoute)
        calls.append(route.name)
        raw = json.dumps({"code": 200, "data": [{"tweet_id": "991", "full_text": "Qwen release", "lang": "en", "created_at": "Sun Aug 09 00:10:00 +0000 2026", "user": {"screen_name": "tester"}}], "has_next_page": False, "next_cursor": None}).encode()
        return TransportResult(raw, {"status_code": 200, "raw_results": 1, "response_bytes": len(raw), "provider": "twexapi"}, None, datetime.now(UTC), 0.01)
    monkeypatch.setattr("monitor.backfill_staging.fetch_page", fetch)
    report = execute_job(job.pk, collection_options={"concurrency": 1})
    assert report["collection_drained"] and calls == ["twexapi"]
    receipt = CollectionRequest.objects.get(attempt__run__job=job)
    assert receipt.http_method == "POST" and receipt.endpoint_url == "https://api.twexapi.io/twitter/advanced_search/page"
    assert receipt.archive_id is None and Post.objects.filter(pk="991").exists()


@pytest.mark.parametrize("failure_status", [401, 503])
def test_staging_records_each_failure_before_switching_to_next_provider(pipeline, monkeypatch, failure_status):  # noqa: F811
    import json
    from datetime import UTC, datetime
    from x_monitor.x_client import XClient
    from monitor.backfill_prefetch import PrefetchRoute, TransportResult
    from tests.test_backfill_prefetch import REAL_FROM_ENV
    job = staged_job(monkeypatch, 1)
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-ondemand")
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fixture-scheduled")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fixture-twex")
    monkeypatch.setenv("TWEXAPI_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    monkeypatch.setattr(XClient, "from_env", classmethod(REAL_FROM_ENV))
    calls = []
    def fetch(route, params, *, max_bytes, timeout):
        assert isinstance(route, PrefetchRoute)
        calls.append(route.name)
        if route.name != "twexapi":
            raw = json.dumps({"error": failure_status}).encode()
            return TransportResult(raw, {"status_code": failure_status, "raw_results": 0, "response_bytes": len(raw)}, "XClientAuthError" if failure_status == 401 else "XClientServerError", datetime.now(UTC), 0.01)
        raw = json.dumps({"code": 200, "data": [{"tweet_id": "992", "full_text": "Qwen release", "lang": "en", "created_at": "Sun Aug 09 00:10:00 +0000 2026", "user": {"screen_name": "tester"}}], "has_next_page": False, "next_cursor": None}).encode()
        return TransportResult(raw, {"status_code": 200, "raw_results": 1, "response_bytes": len(raw), "provider": "twexapi"}, None, datetime.now(UTC), 0.01)
    monkeypatch.setattr("monitor.backfill_staging.fetch_page", fetch)
    report = execute_job(job.pk, collection_options={"concurrency": 1})
    assert report["collection_drained"]
    assert calls == ["twitterapi:on_demand", "twitterapi:scheduled", "twexapi"]
    receipts = list(CollectionRequest.objects.filter(attempt__run__job=job).order_by("ordinal"))
    assert [r.http_status for r in receipts] == [failure_status, failure_status, 200]
    assert [r.http_method for r in receipts] == ["GET", "GET", "POST"]
    assert all(r.accounting_complete for r in receipts)
    assert Post.objects.filter(pk="992").exists()


def test_staging_twex_pagination_waits_and_keeps_cursor(pipeline, monkeypatch):  # noqa: F811
    import json
    from datetime import UTC, datetime
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    from monitor.backfill_prefetch import PrefetchRoute, TransportResult
    from tests.test_backfill_prefetch import REAL_FROM_ENV
    job = staged_job(monkeypatch, 1)
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-ondemand")
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fixture-scheduled")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fixture-twex")
    monkeypatch.setenv("TWEXAPI_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("TWEXAPI_INTERVAL_SECONDS", "0.1")
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    monkeypatch.setattr(XClient, "from_env", classmethod(REAL_FROM_ENV))
    router = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    for circuit in router.provider_circuits.values(): circuit.record_failure(datetime.now(UTC))
    calls = []
    def fetch(route, params, *, max_bytes, timeout):
        assert isinstance(route, PrefetchRoute) and route.name == "twexapi"
        calls.append(params.get("cursor"))
        first = len(calls) == 1
        raw = json.dumps({"code": 200, "data": [{"tweet_id": "993" if first else "994", "full_text": "Qwen release", "lang": "en", "created_at": "Sun Aug 09 00:10:00 +0000 2026", "user": {"screen_name": "tester"}}], "has_next_page": first, "next_cursor": "cursor-twex" if first else None}).encode()
        return TransportResult(raw, {"status_code": 200, "raw_results": 1, "response_bytes": len(raw), "provider": "twexapi"}, None, datetime.now(UTC), 0.01)
    monkeypatch.setattr("monitor.backfill_staging.fetch_page", fetch)
    report = execute_job(job.pk, collection_options={"concurrency": 1})
    assert report["collection_drained"] and calls == [None, "cursor-twex"]
    receipts = list(CollectionRequest.objects.filter(attempt__run__job=job).order_by("ordinal"))
    assert receipts[1].cursor_before == "twexapi:cursor-twex"
    assert set(Post.objects.filter(pk__in=["993", "994"]).values_list("pk", flat=True)) == {"993", "994"}
