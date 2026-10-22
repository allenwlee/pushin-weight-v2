"""Real PostgreSQL + controlled HTTP + shared CycleRunner, with no paid traffic."""
import copy
import json
import re
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from django.core.management.base import CommandError

from core.collection_jobs import register_job, set_job_state
from core.models import (
    CollectionObservation,
    CollectionRequest,
    CollectionScopeRun,
    Post,
)
from monitor.backfill_collection import PageCheckpoint, execute_job
from tests.test_backfill_collection import ready_job
from tests.test_backfill_pipeline import page
from tests.test_backfill_pipeline import pipeline as captured_pipeline

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
pipeline = pytest.fixture(name="pipeline")(captured_pipeline.__wrapped__)
REAL_GET = requests.get
from datetime import UTC

from x_monitor.apify import TwitterApiClient

REAL_BOUNDED = TwitterApiClient._get_bounded


def job_for_scopes(count, *, request_cap=100, maximum=200, byte_cap=32 * 1024 * 1024):
    seed = ready_job()
    definition = copy.deepcopy(seed.definition)
    definition["budgets"].update(requests=request_cap, bytes=byte_cap, items=10000)
    definition["scope"].update(prior_api_requests=0, maximum_api_requests=maximum)
    unit = definition["scope"]["units"][0]
    definition["scope"]["units"] = []
    for i in range(count):
        value = copy.deepcopy(unit)
        value["scope_key"] = f"B1:{i}"
        value["ownership"]["query"] = f"Qwen marker{i}"
        definition["scope"]["units"].append(value)
    job = register_job(job_key="parallel-test", source=seed.source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    return set_job_state(job.pk, "ready")


@pytest.fixture
def http_pages(monkeypatch, pipeline):
    """Exercise real socket transport while routing its URL exclusively to localhost."""
    @contextmanager
    def serve(responder):
        state = {"requests": [], "active": 0, "peak": 0, "connections": set(), "activity": []}
        guard = threading.Lock()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                params = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
                with guard:
                    state["requests"].append(params)
                    state["connections"].add(self.client_address)
                    state["active"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                    state["activity"].append((time.monotonic(), state["active"]))
                try:
                    result = responder(params)
                    status, document = result if isinstance(result, tuple) else (200, result)
                    body = json.dumps(document).encode()
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    with guard:
                        state["active"] -= 1
                        state["activity"].append((time.monotonic(), state["active"]))
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def get(url, **kwargs):
            assert url.startswith("https://api.twitterapi.io/")
            return REAL_GET(f"http://127.0.0.1:{server.server_port}{urlsplit(url).path}", **kwargs)
        monkeypatch.setattr("x_monitor.apify.requests.get", get)
        def bounded(client, url, params, timeout):
            assert url.startswith("https://api.twitterapi.io/")
            local = f"http://127.0.0.1:{server.server_port}{urlsplit(url).path}"
            return REAL_BOUNDED(client, local, params, timeout)
        monkeypatch.setattr(TwitterApiClient, "_get_bounded", bounded)
        monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-only")
        try:
            yield state
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return serve


def test_twenty_fetches_use_exact_page_counts_and_shared_storage(http_pages):
    barrier = threading.Barrier(20)
    def response(params):
        i = int(re.search(r"marker(\d+)", params["query"]).group(1))
        barrier.wait(timeout=15)
        body = page(str(i + 1))
        if i % 2:
            body["tweets"] += page(str(i + 101))["tweets"]
        return body
    job = job_for_scopes(20)
    with http_pages(response) as state:
        result = execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 20})
    assert result["collection_drained"]
    assert state["peak"] == 20
    assert len(state["requests"]) == result["usage"]["api_requests"] == 20
    rows = CollectionScopeRun.objects.filter(run_id=result["run_id"]).order_by("scope_key")
    for row in rows:
        i = int(row.scope_key.split(":")[1])
        assert row.raw_count == 1 + (i % 2)
        assert row.envelopes[-1]["raw_count"] == row.raw_count
        assert row.envelopes[-1]["prefetch_request_id"]
    assert Post.objects.count() == 30
    assert CollectionObservation.objects.filter(run_id=result["run_id"]).count() == 30
    assert CollectionRequest.objects.filter(transport_outcome="received", archive__isnull=False).count() == 20


@pytest.mark.parametrize("resume_options", [None, {"concurrency": 2}])
def test_restart_replays_archives_across_legacy_runs_without_paid_refetch(http_pages, monkeypatch, resume_options):
    job = job_for_scopes(2)
    def response(params):
        return page(re.search(r"marker(\d+)", params["query"]).group(1))
    original = PageCheckpoint.persist
    def crash(*args, **kwargs):
        raise RuntimeError("fixture before Post commit")
    monkeypatch.setattr(PageCheckpoint, "persist", crash)
    with http_pages(response) as state:
        with pytest.raises(CommandError):
            execute_job(job.pk, collection_options={"concurrency": 2})
        assert Post.objects.count() == 0
        assert CollectionRequest.objects.count() == 2
        monkeypatch.setattr(PageCheckpoint, "persist", original)
        result = execute_job(job.pk, collection_options=resume_options)
        assert len(state["requests"]) == 2
    assert result["collection_drained"] and result["usage"]["api_requests"] == 0
    assert result["prefetch"]["replayed_pages"] == 2
    assert result["cumulative_api_requests"] == 2
    assert Post.objects.count() == 2
    assert CollectionRequest.objects.count() == 2


def test_live_writer_can_acquire_during_http_and_blocks_replay(http_pages):
    from django.db import connections

    from monitor.run_lock import harvest_writer_lock
    entered, acquired, release = threading.Event(), threading.Event(), threading.Event()
    errors = []
    def live():
        try:
            assert entered.wait(10)
            with harvest_writer_lock(execution_mode="live", entrypoint="test.prefetch.live") as lease:
                assert lease.acquired
                acquired.set()
                assert release.wait(15)
        except BaseException as exc:  # noqa: BLE001 - propagate thread assertions to the test caller
            errors.append(exc)
            acquired.set()
        finally:
            connections.close_all()
    thread = threading.Thread(target=live)
    def response(params):
        entered.set()
        assert acquired.wait(10), "live writer blocked by network wait"
        return page("1")
    job = job_for_scopes(20)
    thread.start()
    try:
        with http_pages(response) as state:
            result = execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 1})
        assert not errors
        assert len(state["requests"]) == 1
        assert Post.objects.count() == 0
        assert not result["collection_drained"]
        assert CollectionRequest.objects.filter(archive__isnull=False).count() == 1
    finally:
        release.set()
        thread.join(timeout=10)
    assert not errors


def test_live_writer_gets_priority_with_twenty_http_calls_outstanding(http_pages):
    import os
    from pathlib import Path

    from django.db import connections

    from monitor.run_lock import harvest_writer_lock

    entered, acquired, release = threading.Event(), threading.Event(), threading.Event()
    barrier = threading.Barrier(20, action=entered.set)
    errors, wait_seconds = [], []

    def live():
        try:
            assert entered.wait(25), "twenty HTTP calls never became outstanding"
            started = time.monotonic()
            with harvest_writer_lock(execution_mode="live", entrypoint="test.prefetch.twenty.live") as lease:
                assert lease.acquired
                wait_seconds.append(time.monotonic() - started)
                acquired.set()
                assert release.wait(25)
        except BaseException as exc:  # noqa: BLE001 - propagate fixture-thread assertions
            errors.append(exc)
            acquired.set()
        finally:
            connections.close_all()

    def response(params):
        barrier.wait(timeout=20)
        assert acquired.wait(10), "live writer blocked behind outstanding HTTP"
        return page(re.search(r"marker(\d+)", params["query"]).group(1))

    job = job_for_scopes(40)
    thread = threading.Thread(target=live)
    thread.start()
    try:
        with http_pages(response) as state:
            result = execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 20})
            assert not errors
            assert state["peak"] == 20 and len(state["requests"]) == 20
            assert Post.objects.count() == 0, "historical replay bypassed the live writer"
            assert not result["collection_drained"]
            assert CollectionRequest.objects.filter(archive__isnull=False).count() == 20
            release.set()
            thread.join(timeout=10)
            assert not thread.is_alive() and not errors
            resumed = execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 20})
            assert resumed["collection_drained"]
            assert resumed["prefetch"]["replayed_pages"] == 20
            assert len(state["requests"]) == resumed["cumulative_api_requests"] == 40
            assert Post.objects.count() == 40
        receipt = {
            "http_peak": state["peak"], "requests_before_live_release": 20,
            "posts_before_live_release": 0, "archived_before_live_release": 20,
            "live_writer_wait_seconds": round(wait_seconds[0], 3),
            "requests_after_resume": 40, "posts_after_resume": 40,
            "replayed_without_refetch": 20,
        }
        target = os.environ.get("PW_BACKFILL_TWENTY_PRIORITY_RECEIPT")
        if target:
            Path(target).write_text(json.dumps(receipt, sort_keys=True))
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive() and not errors


def test_empty_and_underfilled_continuations_are_consumed_until_terminal_false(http_pages):
    def response(params):
        cursor = params.get("cursor")
        if cursor is None:
            return {"tweets": [], "has_next_page": True, "next_cursor": "empty-next"}
        if cursor == "empty-next":
            return page("1", cursor="last")
        result = page("2")
        result["next_cursor"] = "ignore-terminal-cursor"
        return result
    job = job_for_scopes(1)
    with http_pages(response) as state:
        result = execute_job(job.pk, collection_options={"concurrency": 20})
    assert result["collection_drained"] and Post.objects.count() == 2
    assert [p.get("cursor") for p in state["requests"]] == [None, "empty-next", "last"]
    assert result["usage"]["api_requests"] == 3


def test_request_allowance_bounds_started_wave(http_pages):
    job = job_for_scopes(20, request_cap=1)
    with http_pages(lambda params: page("1")) as state:
        result = execute_job(job.pk, collection_options={"concurrency": 20})
    assert not result["collection_drained"]
    assert len(state["requests"]) == result["usage"]["api_requests"] == 1


def test_zero_per_response_byte_allowance_does_not_reserve_a_physical_start(http_pages):
    job = job_for_scopes(2, byte_cap=1)
    with http_pages(lambda params: pytest.fail("no response allowance")) as state:
        result = execute_job(job.pk, collection_options={"concurrency": 2})
    assert not result["collection_drained"]
    assert not state["requests"] and not CollectionRequest.objects.exists()
    assert result["usage"]["api_requests"] == 0


def test_unknown_physical_outcome_is_not_automatically_sent_again(monkeypatch):
    from datetime import datetime

    from monitor.backfill_prefetch import TransportResult
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-only")
    job = job_for_scopes(1)
    calls = []
    def lost(*args, **kwargs):
        calls.append(1)
        return TransportResult(None, {}, "Timeout", datetime.now(UTC), 0)
    monkeypatch.setattr("monitor.backfill_prefetch.fetch_page", lost)
    for options in [{"concurrency": 20}, None]:
        with pytest.raises(CommandError):
            execute_job(job.pk, collection_options=options)
    assert len(calls) == 1
    assert CollectionRequest.objects.count() == 1


@pytest.mark.parametrize("status", [401, 429, 503])
def test_provider_failure_stops_admission_and_saves_paid_body(http_pages, status):
    job = job_for_scopes(20)
    with http_pages(lambda params: (status, {"error": "fixture rejection"})) as state, pytest.raises(CommandError):
        execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 1})
    assert len(state["requests"]) == 1
    request = CollectionRequest.objects.get()
    assert request.http_status == status and request.archive_id
    assert request.transport_outcome == "received"
    assert not Post.objects.exists()
    assert not CollectionScopeRun.objects.filter(enumeration_complete=True).exists()
    job.refresh_from_db()
    if status == 429:
        assert job.next_retry_at is not None


def test_byte_cap_retains_unknown_receipt_and_cursor(http_pages):
    job = job_for_scopes(1)
    # Larger than the fixed1MiB per-response ceiling, even though the run permits32MiB.
    result = page("1")
    result["tweets"][0]["text"] = "Qwen " + "x" * (1024 * 1024)
    with http_pages(lambda params: result) as state, pytest.raises(CommandError):
        execute_job(job.pk, collection_options={"concurrency": 20})
    assert len(state["requests"]) == 1
    assert not Post.objects.exists()
    assert CollectionRequest.objects.get().transport_outcome == "transport_error"
    assert CollectionScopeRun.objects.get(run__job=job).cursor is None


def test_capture_accounting_crash_is_repaired_once_before_replay(http_pages, monkeypatch):
    from core.models import CollectionRun
    from monitor.backfill_collection import DurableBudget
    job = job_for_scopes(1)
    original = DurableBudget.record_captured_response
    def crash(*args, **kwargs):
        raise RuntimeError("fixture lost process after immutable capture")
    monkeypatch.setattr(DurableBudget, "record_captured_response", crash)
    with http_pages(lambda params: page("1")) as state:
        with pytest.raises(CommandError):
            execute_job(job.pk, collection_options={"concurrency": 20})
        request = CollectionRequest.objects.select_related("scope_run").get()
        owner = CollectionRun.objects.get(pk=request.scope_run.run_id)
        assert request.archive_id and owner.selected_count == 0
        monkeypatch.setattr(DurableBudget, "record_captured_response", original)
        report = execute_job(job.pk)  # Omitting the flag must still recover captures.
        assert report["collection_drained"]
        assert len(state["requests"]) == 1
    owner.refresh_from_db()
    assert owner.selected_count == 1
    assert owner.report["response_bytes"] == request.response_bytes
    assert owner.report["prefetch_accounted_requests"] == [str(request.pk)]
    assert execute_job(job.pk)["state"] == "completed"


def test_parallel_rare_capture_keeps_its_own_raw_count_and_shared_gate(http_pages, monkeypatch, tmp_path):
    from decimal import Decimal

    from django.db import connection

    from core.models import RareTypeSearchHit, RareTypeSearchRun
    from tests.test_backfill_collection import policy_job
    from x_monitor.jev_decisions import QUESTION_SET, JevDecisionsClient, JevResponse

    job = policy_job(monkeypatch, tmp_path, calls={"B1", "RARE_EXTRA"}, rare=True)
    rare_query = next(u["ownership"]["query"] for u in job.scope["units"]
                      if u["ownership"]["call_id"] == "RARE_EXTRA")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-only")
    model_calls = []

    def decide(self, request_bytes, **kwargs):
        assert not connection.in_atomic_block
        assert RareTypeSearchHit.objects.count() == 1
        model_calls.append(request_bytes)
        probabilities = dict.fromkeys(QUESTION_SET, .1)
        probabilities.update(ai_related=.95, role_opening=.95)
        return JevResponse("fixture-decision", probabilities, 1200, 0, Decimal("0.00005"))

    monkeypatch.setattr(JevDecisionsClient, "submit", decide)

    def response(params):
        if params["query"].startswith(rare_query + " "):
            return page("rare-kept")
        body = page("ordinary-1")
        body["tweets"] += page("ordinary-2")["tweets"]
        return body

    with http_pages(response) as state:
        report = execute_job(job.pk, collection_options={"concurrency": 20})
    assert report["collection_drained"] and report["rare_gate_pending"] == 0
    assert len(state["requests"]) == 2 and len(model_calls) == 1
    assert set(Post.objects.values_list("pk", flat=True)) == {"rare-kept", "ordinary-1", "ordinary-2"}
    scopes = CollectionScopeRun.objects.filter(run_id=report["run_id"])
    for call, expected in (("RARE_EXTRA", 1), ("B1", 2)):
        scope = scopes.get(scope_key=call)
        pages = [entry for entry in scope.envelopes if entry.get("prefetch_request_id")]
        assert len(pages) == 1 and pages[0]["raw_count"] == expected
        assert scope.raw_count == expected
    assert RareTypeSearchRun.objects.get().raw_result_count == 1
    assert RareTypeSearchHit.objects.get().post_id == "rare-kept"


def test_expired_interrupted_run_resumes_committed_cursor_without_recollection(http_pages, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from core.collection_state import StaleClaim
    from core.models import CollectionRun
    from monitor import backfill_collection as collection
    from scripts import backfill_month as month

    job = job_for_scopes(1, request_cap=1)
    finish = collection.finish_run

    def interrupted(*args, **kwargs):
        raise StaleClaim("fixture interruption after page commit")

    monkeypatch.setattr(collection, "finish_run", interrupted)
    with http_pages(lambda params: page("2") if params.get("cursor") else page("1", cursor="next")) as state:
        with pytest.raises(StaleClaim, match="fixture interruption"):
            execute_job(job.pk, collection_options={"concurrency": 20})
        old = CollectionRun.objects.get(job=job)
        assert old.status == "running" and old.scopes.get().cursor == "next"
        with pytest.raises(RuntimeError, match="historical_run_active"):
            month._check_saved_jobs({"campaign": "parallel-test"})
        CollectionRun.objects.filter(pk=old.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        month._check_saved_jobs({"campaign": "parallel-test"})
        monkeypatch.setattr(collection, "finish_run", finish)
        result = execute_job(job.pk)
    old.refresh_from_db()
    assert old.status == "aborted" and old.error_code == "expired_lease"
    assert old.attempts.get().outcome == "interrupted"
    assert [p.get("cursor") for p in state["requests"]] == [None, "next"]
    assert result["collection_drained"] and result["cumulative_api_requests"] == 2
    assert set(Post.objects.values_list("pk", flat=True)) == {"1", "2"}
    assert CollectionRequest.objects.count() == 2


@pytest.mark.parametrize("held_lock", ["month", "campaign"])
def test_phase_controller_respects_real_month_and_legacy_campaign_sessions(monkeypatch, held_lock):
    import hashlib
    import os

    import psycopg

    from scripts import backfill_campaign as campaign
    from scripts import backfill_month as month

    frozen = {"campaign": "locked-campaign", "database": campaign.database_identity(),
              "direct_concurrency": 32, "deadline": "2099-01-01T00:00:00+00:00", "windows": [{"index": 1}]}
    calls = []
    monkeypatch.setattr(month, "_validate_campaign_runtime", lambda *args: None)
    monkeypatch.setattr(campaign, "collect_window", lambda *args, **kwargs:
                        calls.append("collect") or {"status": "verified"})
    namespace = "x-manual-month-controller:" if held_lock == "month" else frozen["campaign"]
    key = int(hashlib.sha256((namespace + str(frozen["database"])).encode()).hexdigest()[:15], 16)
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as other:
        assert other.execute("SELECT pg_try_advisory_lock(%s)", [key]).fetchone()[0]
        with pytest.raises(RuntimeError, match="controller_already_running"):
            month.run_phases(frozen, object(), phase="collect")
        assert not calls
    assert month.run_phases(frozen, object(), phase="collect") == [{"status": "verified"}]
    assert calls == ["collect"]


def test_public_collection_phase_recovers_missing_summary_without_searching_again(http_pages, monkeypatch, tmp_path, settings):
    from io import StringIO

    from django.core.management import call_command

    from core.models import (
        CollectionJob,
        CollectionRun,
        DataSource,
        OriginalContentCall,
    )
    from scripts import backfill_campaign as campaign

    settings.X_MONITOR_LIST_ID = 123
    DataSource.objects.get_or_create(id="x", defaults={"name": "X", "source_type": "social"})
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "fixture-only")
    monkeypatch.setattr(campaign, "prepare_current_contract", lambda *args: pytest.fail("collection started enrichment"))
    output = StringIO()
    call_command("run_backfill", since="2026-08-09T00:00:00Z", until="2026-08-09T00:15:00Z",
                 campaign_name="phase-summary-recovery", stdout=output)
    frozen = json.loads(output.getvalue())
    path = tmp_path / "frozen.json"
    path.write_text(output.getvalue())
    with http_pages(lambda params: {"tweets": [], "has_next_page": False}) as state:
        call_command("run_backfill", manifest=path, phase="collect", collection_concurrency=20, execute=True)
        job = CollectionJob.objects.get(job_key="phase-summary-recovery/1")
        run = CollectionRun.objects.get(job=job)
        receipt = run.report["backfill_campaign"]["collection"]
        assert receipt["status"] == "verified" and receipt["checked_posts"] == 0
        assert receipt["phase_usage"]["twitterapi_requests"] == len(frozen["windows"][0]["collection_definition"]["scope"]["units"])
        paid = len(state["requests"])
        run.report.pop("backfill_campaign")
        run.save(update_fields=["report"])
        call_command("run_backfill", manifest=path, phase="collect", collection_concurrency=20, execute=True)
        assert len(state["requests"]) == paid
    run.refresh_from_db()
    assert run.report["backfill_campaign"]["collection"]["status"] == "verified"
    assert CollectionRun.objects.filter(job=job).count() == 1
    assert not OriginalContentCall.objects.exists()
