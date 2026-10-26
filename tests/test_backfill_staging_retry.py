"""Recovery through real HTTP, CollectionRun checkpoints and the shared writer."""
import copy
import re
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import CollectionRequest, Post
from monitor.backfill_collection import BackfillProviderSafetyError, execute_job
from monitor.backfill_retry import POLICY, RetryControl
from tests.test_backfill_pipeline import page
from tests.test_backfill_staging import (  # noqa: F401
    http_pages,
    pipeline,
    result_for,
    staged_job,
)
from x_monitor.apify import TwitterApiClient

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        offset = timedelta()
        base = datetime.now(UTC)

        @classmethod
        def now(cls, tz=None):
            return (cls.base + cls.offset).astimezone(tz)

        @classmethod
        def advance(cls, job):
            job.refresh_from_db()
            cls.offset += job.next_retry_at - cls.now(UTC) + timedelta(seconds=1)

    for path in ("monitor.backfill_staging.datetime", "monitor.backfill_collection.datetime",
                 "monitor.backfill_prefetch.datetime"):
        monkeypatch.setattr(path, Clock, raising=False)
    monkeypatch.setattr(timezone, "now", lambda: Clock.now(UTC))
    return Clock


def lose_response(monkeypatch, predicate):
    original = TwitterApiClient._get_bounded

    def bounded(self, url, params, timeout):
        response = original(self, url, params, timeout)
        if predicate(params):
            raise requests.Timeout("fixture lost reply")
        return response

    monkeypatch.setattr(TwitterApiClient, "_get_bounded", bounded)


def test_timeout_retries_exact_cursor_without_rewriting_unknown_receipt(http_pages, monkeypatch, clock):  # noqa: F811
    job = staged_job(monkeypatch, 2)
    lost = []

    def fail(params):
        if params.get("cursor") and not lost:
            lost.append(params.copy())
            return True
        return False

    def response(params):
        if "marker0" in params["query"]:
            return page("second" if params.get("cursor") else "first",
                        cursor=None if params.get("cursor") else "continuation")
        return page("independent")

    with http_pages(response) as state:
        lose_response(monkeypatch, fail)
        first = execute_job(job.pk, collection_options={"concurrency": 2})
        assert first["state"] == "waiting_for_provider"
        assert Post.objects.count() == 2
        failed = CollectionRequest.objects.get(error_code="Timeout")
        immutable = CollectionRequest.objects.filter(pk=failed.pk).values().get()
        assert failed.accounting_complete is False and failed.response_bytes is None
        assert job.runs.get(pk=first["run_id"]).report["staging_responses"][str(failed.pk)]["raw_count"] is None
        with pytest.raises(BackfillProviderSafetyError):
            execute_job(job.pk)
        assert len(state["requests"]) == 3
        clock.advance(job)
        report = execute_job(job.pk, collection_options={"concurrency": 2})
    assert report["collection_drained"] and report["cumulative_api_requests"] == 4
    # HTTP query parameters arrive as strings, including the numeric limit.
    assert state["requests"][-1] == {key: str(value) for key, value in lost[0].items()}
    assert CollectionRequest.objects.filter(pk=failed.pk).values().get() == immutable
    retry = CollectionRequest.objects.get(request_group=str(failed.pk))
    assert retry.request_revision == POLICY and retry.accounting_complete
    assert Post.objects.count() == 3


@pytest.mark.parametrize("failure", ["timeout", 401, 403])
def test_twenty_in_flight_cluster_saves_successes_and_resumes_after_cooldown(http_pages, monkeypatch, clock, failure):  # noqa: F811
    job = staged_job(monkeypatch, 40)
    barrier = threading.Barrier(20)
    wave = {"initial": True}
    lost = set()
    limits = []
    original_limit = RetryControl.limit

    def limit(self, configured, now):
        result = original_limit(self, configured, now)
        limits.append(result)
        return result

    monkeypatch.setattr(RetryControl, "limit", limit)

    def response(params):
        if wave["initial"]:
            barrier.wait(timeout=25)
            marker = int(re.search(r"marker(\d+)", params["query"]).group(1))
            if marker < 3 and failure != "timeout":
                return failure, {"error": "fixture rejected key"}
            if marker >= 3:
                time.sleep(1)
        return result_for(params)

    def fail(params):
        marker = int(re.search(r"marker(\d+)", params["query"]).group(1))
        if failure == "timeout" and marker < 3 and marker not in lost:
            lost.add(marker)
            return True
        return False

    with http_pages(response) as state:
        lose_response(monkeypatch, fail)
        first = execute_job(job.pk, collection_options={"concurrency": 20, "starts_per_second": 20})
        assert state["peak"] == 20 and len(state["requests"]) == 20
        assert first["state"] == "waiting_for_provider" and first["scopes_complete"] == 17
        assert Post.objects.count() == 17
        job.refresh_from_db()
        assert job.state == "ready" and job.active_run_id is None
        saved = job.last_attempt.report["staging_retry"]
        assert saved["phase"] == "open" and saved["cooldowns"] == 1
        assert 45 <= (job.next_retry_at - clock.now(UTC)).total_seconds() <= 60
        # Neither a row lock nor a live-writer lease survives the cooldown.
        from monitor.run_lock import harvest_writer_lock
        with harvest_writer_lock(execution_mode="live", entrypoint="fixture") as lease:
            assert lease.acquired
        wave["initial"] = False
        limits.clear()
        clock.advance(job)
        report = execute_job(job.pk, collection_options={"concurrency": 20})
    assert report["collection_drained"] and report["cumulative_api_requests"] == 43
    assert limits[0] == 1 and 4 in limits and limits[-1] == 20
    assert report["prefetch"]["retry_requests"] == 3
    assert Post.objects.count() == 40
    assert CollectionRequest.objects.filter(accounting_complete=False).count() == (3 if failure == "timeout" else 0)


def test_repeated_failures_slow_down_without_ending_campaign(http_pages, monkeypatch, clock):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    fail = {"enabled": True}
    with http_pages(result_for) as state:
        lose_response(monkeypatch, lambda _: fail["enabled"])
        for _ in range(6):
            report = execute_job(job.pk)
            assert not report["collection_drained"]
            clock.advance(job)
        fail["enabled"] = False
        assert execute_job(job.pk)["collection_drained"]
    assert len(state["requests"]) == 7
    assert CollectionRequest.objects.filter(error_code="Timeout", accounting_complete=False).count() == 6


def test_timeout_does_not_reset_window_request_allowance(http_pages, monkeypatch, clock):  # noqa: F811
    job = staged_job(monkeypatch, 1, maximum=1)
    with http_pages(result_for) as state:
        lose_response(monkeypatch, lambda _: True)
        first = execute_job(job.pk)
        if first.get("retry_at"):
            clock.advance(job)
        second = execute_job(job.pk)
    assert len(state["requests"]) == 1
    assert not second["collection_drained"] and second["cumulative_api_requests"] == 1


@pytest.mark.parametrize("status", [402, 400])
def test_permanent_http_errors_still_stop(http_pages, monkeypatch, status):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    with http_pages(lambda _: (status, {"error": "fixture"})) as state, pytest.raises((CommandError, BackfillProviderSafetyError)):
        execute_job(job.pk)
    assert len(state["requests"]) == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503, 504])
def test_transient_http_response_can_recover(http_pages, monkeypatch, clock, status):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    replies = iter([(status, {"error": "fixture"}), page("recovered")])
    with http_pages(lambda _: next(replies)) as state:
        first = execute_job(job.pk)
        assert first["state"] == "waiting_for_provider"
        clock.advance(job)
        last = execute_job(job.pk)
    assert last["collection_drained"] and len(state["requests"]) == 2


def test_recovery_policy_escalates_and_ramps_without_replaying_old_failures():
    policy = RetryControl()
    for now in (10, 11, 12):
        policy.failed(now)
    assert policy.until == 72 and policy.limit(20, 71) == 0
    policy.failed(13)  # Late in-flight failure is the same incident.
    assert policy.until == 72 and policy.cooldowns == 1
    restored = RetryControl.restore(copy.deepcopy(policy.snapshot()))
    assert restored.limit(20, 72) == 1
    restored.failed(73)
    assert restored.until == 373 and restored.cooldowns == 2
    assert restored.limit(20, 373) == 1
    restored.failed(374)
    assert restored.until == 1274 and restored.cooldowns == 3
    assert restored.limit(20, 1274) == 1
    restored.succeeded()
    assert restored.limit(20, 1275) == 4
    for _ in range(4):
        restored.succeeded()
    assert restored.limit(20, 1276) == 20 and restored.cooldowns == 0


def test_retry_after_is_not_shortened():
    policy = RetryControl()
    policy.failed(10, retry_after=180, rate_limited=True)
    assert policy.until == 190
    policy.failed(15, retry_after=200, rate_limited=True)
    assert policy.until == 215 and policy.cooldowns == 1


def test_previous_retry_receipt_remains_usable():
    original = RetryControl().snapshot() | {"policy": "staging-get-retry/v1"}
    assert RetryControl.restore(original).snapshot()["policy"] == POLICY
    assert original["policy"] == "staging-get-retry/v1"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_retries_slow_down_and_keep_all_receipts(http_pages, monkeypatch, clock, status):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    rejected = {"enabled": True}
    with http_pages(lambda _: (status, {"error": "fixture"}) if rejected["enabled"] else page("recovered")) as state:
        for index in range(6):
            result = execute_job(job.pk)
            assert result["state"] == "waiting_for_provider"
            job.refresh_from_db()
            if index >= 2:
                assert (job.next_retry_at - clock.now(UTC)).total_seconds() >= 890
            clock.advance(job)
        rejected["enabled"] = False
        assert execute_job(job.pk)["collection_drained"]
    assert len(state["requests"]) == 7
    assert CollectionRequest.objects.filter(http_status=status).count() == 6
    assert Post.objects.count() == 1


def test_unlimited_requests_resumes_exhausted_job_without_refetching_completed_scope(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 2, maximum=1)
    before = copy.deepcopy(job.definition)
    with http_pages(result_for) as state:
        first = execute_job(job.pk)
        assert not first["collection_drained"] and len(state["requests"]) == 1
        exhausted = execute_job(job.pk)
        assert not exhausted["collection_drained"] and len(state["requests"]) == 1
        result = execute_job(job.pk, collection_options={"unlimited_requests": True})
    assert result["collection_drained"] and result["cumulative_api_requests"] == 2
    assert len(state["requests"]) == Post.objects.count() == 2
    job.refresh_from_db()
    assert job.definition == before
    assert job.last_attempt.report["collection_options"]["unlimited_requests"] is True


def test_expired_campaign_and_exhausted_cap_can_be_explicitly_overridden(http_pages, monkeypatch, clock):  # noqa: F811
    from core.models import CollectionJob
    from scripts import backfill_campaign as campaign
    from x_monitor.config import load_config

    template = staged_job(monkeypatch, 2, maximum=1)
    definition = copy.deepcopy(template.definition)
    deadline = (clock.now(UTC) - timedelta(days=1)).isoformat()
    definition["scope"]["deadline"] = deadline
    frozen = {"campaign": "override-campaign", "instruction_format": "x-backfill-campaign/v2", "deadline": deadline}
    window = {"index": 1, "maximum_api_requests": 1, "collection_definition": definition}
    before = copy.deepcopy((frozen, window))
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "fixture-only")
    with http_pages(lambda _: {"tweets": [], "has_next_page": False}) as state:
        with pytest.raises(RuntimeError, match="campaign_deadline_exhausted"):
            campaign.collect_window(window, frozen=frozen, cfg=load_config(Path("config.yaml")))
        job = CollectionJob.objects.get(job_key="override-campaign/1")
        with pytest.raises(ValueError, match="campaign deadline exhausted"):
            execute_job(job.pk)
        assert not state["requests"]
        result = campaign.collect_window(window, frozen=frozen, cfg=load_config(Path("config.yaml")),
            collection_options={"no_deadline": True, "unlimited_requests": True, "starts_per_second": 20})
    assert result["status"] == "verified" and len(state["requests"]) == 2
    assert (frozen, window) == before
    job.refresh_from_db()
    options = job.last_attempt.report["collection_options"]
    assert options["no_deadline"] and options["unlimited_requests"] and options["starts_per_second"] == 20
    assert job.last_attempt.report["usage"]["api_limit"] == job.budgets["requests"]


def test_malformed_success_is_not_retried(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    with http_pages(lambda _: {"tweets": "invalid"}) as state, pytest.raises(CommandError):
        execute_job(job.pk)
    assert len(state["requests"]) == 1


def test_changed_timeout_identity_cannot_be_retried(http_pages, monkeypatch, clock):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    with http_pages(result_for) as state:
        lose_response(monkeypatch, lambda _: True)
        execute_job(job.pk)
        CollectionRequest.objects.filter(error_code="Timeout").update(request_config="changed")
        clock.advance(job)
        with pytest.raises(CommandError, match="ValueError"):
            execute_job(job.pk)
    assert len(state["requests"]) == 1


@pytest.mark.parametrize("expire", [False, True])
def test_campaign_waits_and_retries_without_overriding_deadline(http_pages, monkeypatch, clock, expire):  # noqa: F811
    from core.models import CollectionJob
    from monitor.run_lock import harvest_writer_lock
    from scripts import backfill_campaign as campaign
    from x_monitor.config import load_config

    template = staged_job(monkeypatch, 1)
    frozen = {"campaign": "retry-campaign", "instruction_format": "x-backfill-campaign/v2",
              "deadline": (clock.now(UTC) + timedelta(hours=1)).isoformat()}
    window = {"index": 1, "maximum_api_requests": 20, "collection_definition": template.definition}
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "fixture-only")
    lost, waits = [], []

    def fail(_):
        lost.append(True)
        return len(lost) == 1

    def wait(seconds):
        waits.append(seconds)
        job = CollectionJob.objects.get(job_key="retry-campaign/1")
        assert job.state == "ready" and job.active_run_id is None
        with harvest_writer_lock(execution_mode="live", entrypoint="fixture") as lease:
            assert lease.acquired
        if expire:
            clock.offset += timedelta(hours=2)
        else:
            clock.advance(job)

    monkeypatch.setattr(campaign, "_wait", wait)
    with http_pages(lambda _: {"tweets": [], "has_next_page": False}) as state:
        lose_response(monkeypatch, fail)
        if expire:
            with pytest.raises(RuntimeError, match="campaign_deadline_exhausted"):
                campaign.collect_window(window, frozen=frozen, cfg=load_config(Path("config.yaml")))
        else:
            report = campaign.collect_window(window, frozen=frozen, cfg=load_config(Path("config.yaml")))
            assert report["status"] == "verified" and report["phase_usage"]["twitterapi_requests"] == 2
    assert len(waits) == 1 and len(state["requests"]) == (1 if expire else 2)
