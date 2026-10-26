"""Real command, shared runner and PostgreSQL: jobs never borrow scheduled keys."""
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from core.collection_jobs import register_job, set_job_state
from core.collection_state import StaleClaim
from core.models import CallState, CollectionRun, DataSource, HarvestBacklogWindow, Post
from monitor.backfill_collection import ADAPTER_VERSION, config_digest
from monitor.backfill_resources import bounded_backfill_config
from tests.test_backfill_pipeline import page
from tests.test_backfill_pipeline import pipeline as captured_pipeline
from x_monitor.apify import TwitterApiClient
from x_monitor.config import load_config
from x_monitor.reattribute import (
    build_relevancy_client_from_env as REAL_RELEVANCY_FACTORY,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
REAL_FACTORY = TwitterApiClient.__dict__["from_env"]
pipeline = pytest.fixture(name="pipeline")(captured_pipeline.__wrapped__)


@pytest.fixture(autouse=True)
def on_demand_test_environment(monkeypatch):
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "test-only-on-demand")


def ready_job(*, requests=1, maximum=20, cursor=None, complete=False, probe=False):
    cfg = bounded_backfill_config(load_config(Path("config.yaml")), enrichment_limit=1)
    source, _ = DataSource.objects.get_or_create(id="x", defaults={"name": "X", "source_type": "social"})
    definition = {
            "version": 1, "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": requests, "seconds": 300, "bytes": 1024*1024, "items": 100},
            "scope": {
                "adapter": ADAPTER_VERSION, "credential_purpose": "on-demand", "brands": ["qwen"],
                "since_epoch": 1786233600, "until_epoch": 1786234500,
                "config_digest": config_digest(cfg),
                "database": {k.lower(): settings.DATABASES["default"].get(k) for k in ("NAME", "USER")},
                "prior_api_requests": 3, "maximum_api_requests": maximum,
                "provenance": {"format": "pilot-v2", "file_sha256": "a"*64},
                "units": [{"scope_key": "B1:aug09", "scope_kind": "x_query",
                           "ownership": {"call_id": "B1", "query": "Qwen", "since_epoch": 1786233600,
                                         "until_epoch": 1786234500},
                           "cursor": cursor, "cursor_history": [cursor] if cursor else [],
                           "outcome": "complete" if complete else "pending", "enumeration_complete": complete}],
            },
        }
    if probe:
        import hashlib
        import json
        body = page("1")
        definition["scope"]["storage_probe"] = {
            "body": body, "body_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
            "ownership": definition["scope"]["units"][0]["ownership"],
        }
    obj = register_job(
        job_key="aug09-test", source=source, purpose="content", operation="x_backfill", mode="historical",
        definition=definition,
    )
    return set_job_state(obj.pk, "ready")


def run(job):
    output = StringIO()
    call_command("backfill", collection_job=str(job.pk), stdout=output)
    import json
    return json.loads(output.getvalue())


@pytest.fixture
def live_writer():
    """Hold the real live lock on a separate PostgreSQL session."""
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from threading import Event

    from django.db import connections

    from monitor.run_lock import harvest_writer_lock

    @contextmanager
    def hold():
        acquired, release = Event(), Event()

        def live():
            try:
                with harvest_writer_lock(execution_mode="live", entrypoint="test.live.wait") as lease:
                    assert lease.acquired
                    acquired.set()
                    assert release.wait(15), "test did not release live writer"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(live)
            try:
                assert acquired.wait(5)
                yield lambda: (release.set(), future.result(timeout=5))
            finally:
                release.set()
                future.result(timeout=5)

    return hold


@pytest.mark.parametrize("resuming", [False, True])
def test_live_writer_wait_creates_no_attempts_or_checkpoints(pipeline, live_writer, resuming):
    from core.models import CollectionAttempt, CollectionScopeRun

    job = ready_job()
    if resuming:
        pipeline.responses.append(page("1", cursor="saved-before-live"))
        run(job)
    job.refresh_from_db()
    before = (CollectionRun.objects.count(), CollectionScopeRun.objects.count(),
              CollectionAttempt.objects.count(), job.last_attempt_id, len(pipeline.requests))
    with live_writer():
        for _ in range(3):
            report = run(job)  # actual public command, not an admission-helper test
            assert report == {"job_id": str(job.pk), "state": "waiting_for_live_writer"}
        job.refresh_from_db()
        assert (CollectionRun.objects.count(), CollectionScopeRun.objects.count(),
                CollectionAttempt.objects.count(), job.last_attempt_id, len(pipeline.requests)) == before
        assert job.active_run_id is None
    pipeline.responses.append(page("2"))
    assert run(job)["collection_drained"]
    assert len(pipeline.requests) == before[-1] + 1
    if resuming:
        assert pipeline.requests[-1]["cursor"] == "saved-before-live"
    assert CollectionRun.objects.count() == before[0] + 1
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()


@pytest.mark.parametrize("expire", [False, True])
def test_campaign_waits_without_attempt_and_keeps_deadline(pipeline, live_writer, monkeypatch, expire):
    from datetime import timedelta

    from django.utils import timezone

    from scripts import backfill_campaign as campaign

    template = ready_job()
    cfg = load_config(Path("config.yaml"))
    now = timezone.now()
    clock = [now]
    frozen = {"campaign": "wait-test", "instruction_format": "x-backfill-campaign/v2",
              "direct_concurrency": 32,
              "deadline": (now + timedelta(hours=1)).isoformat()}
    window = {"index": 1, "maximum_api_requests": 20, "collection_definition": template.definition}
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "fake-on-demand")
    monkeypatch.setattr(campaign.timezone, "now", lambda: clock[0])
    monkeypatch.setattr(campaign.time, "monotonic", lambda: (clock[0] - now).total_seconds())
    class ReachedEnrichment(Exception):
        pass

    def reached(*args):
        raise ReachedEnrichment

    monkeypatch.setattr(campaign, "prepare_current_contract", reached)
    waits = []
    with live_writer() as release:
        def wait(seconds):
            waits.append(seconds)
            assert seconds == 15
            assert not CollectionRun.objects.exists()
            assert not pipeline.requests
            clock[0] += timedelta(hours=2) if expire else timedelta(minutes=16)
            if expire or len(waits) == 2:
                release()

        monkeypatch.setattr(campaign, "_wait", wait)
        pipeline.responses.append(page("2"))
        expected = RuntimeError if expire else ReachedEnrichment
        with pytest.raises(expected, match="campaign_deadline_exhausted" if expire else None):
            campaign.execute_window(window, frozen=frozen, cfg=cfg)
    assert len(waits) == (1 if expire else 2)
    assert len(pipeline.requests) == (0 if expire else 1)
    assert CollectionRun.objects.count() == (0 if expire else 1)


def test_native_page_yields_to_scheduled_tick_and_resumes_exact_cursor(pipeline, monkeypatch):
    """Real native command, runner, transport and checkpoint meet a live tick."""
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from monitor.management.commands.run_cycle import Command
    from tests.test_cycle_run_lock import wait_for_live_queue
    from x_monitor import apify

    job = ready_job(requests=3)
    pipeline.responses.extend([page("1", cursor="after-paid-page"), page("2")])
    original_get = apify.requests.get
    scheduled_futures = []
    live_saw_checkpoint = []

    def execute_live(self, *args, **options):
        # The queued scheduled command executes only after the paid historical
        # page has committed membership and its exact continuation.
        old = CollectionRun.objects.filter(job=job).order_by("started_at").first()
        saved_scope = old.scopes.get()
        live_saw_checkpoint.append((saved_scope.cursor, Post.objects.filter(pk="1").exists()))
        Post.objects.create(tweet_id="live-tick-proof", text="scheduled collection proof")

    monkeypatch.setattr(Command, "_handle", execute_live)

    def scheduled():
        try:
            call_command("run_cycle", scheduled=True, stdout=StringIO(), stderr=StringIO())
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        def fetch(*args, **kwargs):
            if not scheduled_futures:
                scheduled_futures.append(pool.submit(scheduled))
                wait_for_live_queue()
            return original_get(*args, **kwargs)

        monkeypatch.setattr("x_monitor.apify.requests.get", fetch)
        first = run(job)
        scheduled_futures[0].result(timeout=5)
    assert len(pipeline.requests) == 1
    assert live_saw_checkpoint == [("after-paid-page", True)]
    assert Post.objects.filter(pk="live-tick-proof").exists()
    first_run = CollectionRun.objects.get(pk=first["run_id"])
    assert first_run.request_count == 1
    assert first_run.scopes.get().cursor == "after-paid-page"
    monkeypatch.setattr("x_monitor.apify.requests.get", original_get)
    resumed = run(job)
    assert resumed["collection_drained"]
    assert pipeline.requests[1]["cursor"] == "after-paid-page"
    assert pipeline.requests[0]["query"] == pipeline.requests[1]["query"]
    assert resumed["recovered_post_ids"] == ["1", "2"]
    first_run.refresh_from_db()
    assert first_run.request_count == 1
    assert first_run.scopes.get().cursor == "after-paid-page"
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()


def test_database_job_resumes_exact_page_and_preserves_previous_attempt(pipeline):
    job = ready_job()
    pipeline.responses.append(page("1", cursor="second-page"))
    first = run(job)
    old = CollectionRun.objects.get(pk=first["run_id"])
    old_scope = old.scopes.get()
    assert old.status == "partial" and old.request_count == 1
    assert old_scope.cursor == "second-page"
    assert old_scope.envelopes[-1]["post_ids"] == ["1"]
    assert old_scope.raw_count == 1
    assert old.report["checkpoint_import"]["historical_attempt_timestamps"] is None
    pipeline.responses.append(page("2"))
    second = run(job)
    assert second["collection_drained"]
    assert second["cumulative_api_requests"] == 5  # three actual imported starts plus two live starts
    assert second["recovered_post_ids"] == ["1", "2"]
    assert second["post_membership"] == {"version": 1, "distinct_posts": 2}
    assert second["enrichment_pending_count"] == 2
    old_scope.refresh_from_db()
    assert old_scope.cursor == "second-page" and not old_scope.enumeration_complete
    assert pipeline.requests[1]["cursor"] == "second-page"
    assert pipeline.requests[0]["query"] == pipeline.requests[1]["query"]
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()
    assert not list(pipeline.directory.glob("*.json"))


def test_complete_page_report_certifies_typed_membership(pipeline):
    job = ready_job()
    pipeline.responses.append(page("1"))
    report = run(job)
    assert report["collection_drained"]
    assert report["post_membership"] == {"version": 1, "distinct_posts": 1}
    assert CollectionRun.objects.get(pk=report["run_id"]).status == "success"


def test_page_failure_rolls_back_all_posts_and_keeps_cursor(pipeline, monkeypatch):
    job = ready_job(cursor="previous")
    body = page("1", cursor="must-not-advance")
    body["tweets"].extend(page("2")["tweets"])
    pipeline.responses.append(body)
    save = Post.save
    def fail(self, *args, **kwargs):
        if str(self.pk) == "2":
            raise RuntimeError("injected second-item failure")
        return save(self, *args, **kwargs)
    monkeypatch.setattr(Post, "save", fail)
    with pytest.raises(CommandError, match="checkpoint retained"):
        run(job)
    attempt = CollectionRun.objects.get(job=job)
    assert attempt.status == "failed" and attempt.request_count == 1
    assert attempt.scopes.get().cursor == "previous"
    assert not Post.objects.filter(pk__in=["1", "2"]).exists()


def test_pausing_during_fetch_rejects_post_and_cursor(pipeline, monkeypatch):
    job = ready_job(cursor="previous")
    pipeline.responses.append(page("1"))
    original = __import__("x_monitor.apify", fromlist=["requests"]).requests.get
    def get(*args, **kwargs):
        assert not connection.in_atomic_block
        response = original(*args, **kwargs)
        set_job_state(job.pk, "paused")
        return response
    monkeypatch.setattr("x_monitor.apify.requests.get", get)
    with pytest.raises(StaleClaim):
        run(job)
    assert not Post.objects.filter(pk="1").exists()
    assert CollectionRun.objects.get(job=job).scopes.get().cursor == "previous"


def test_api_start_is_durable_before_http_and_not_reset_after_interruption(pipeline, monkeypatch):
    import requests
    job = ready_job(maximum=4)  # three old starts, one remaining
    pipeline.responses.append(requests.ReadTimeout("timeout"))
    original = __import__("x_monitor.apify", fromlist=["requests"]).requests.get
    def get(*args, **kwargs):
        assert not connection.in_atomic_block
        assert CollectionRun.objects.get(job=job).request_count == 1
        return original(*args, **kwargs)
    monkeypatch.setattr("x_monitor.apify.requests.get", get)
    with pytest.raises(CommandError):
        run(job)
    second = run(job)
    assert not second["collection_drained"] and second["cumulative_api_requests"] == 4
    assert len(pipeline.requests) == 1


def test_on_demand_key_is_selected_with_all_three_keys_present(pipeline, monkeypatch):
    monkeypatch.setattr(TwitterApiClient, "from_env", REAL_FACTORY)
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "test-on-demand")
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "test-scheduled")
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "test-legacy")
    original = __import__("x_monitor.apify", fromlist=["requests"]).requests.get
    def get(*args, **kwargs):
        assert kwargs["headers"]["X-API-Key"] == "test-on-demand"
        return original(*args, **kwargs)
    monkeypatch.setattr("x_monitor.apify.requests.get", get)
    pipeline.responses.append(page("1"))
    assert run(ready_job())["collection_drained"]


def test_missing_on_demand_key_never_falls_back_or_claims(pipeline, monkeypatch):
    monkeypatch.delenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", raising=False)
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "test-scheduled")
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "test-legacy")
    with pytest.raises(RuntimeError, match="TWITTERAPI_IO_ON_DEMAND_API_KEY"):
        run(ready_job())
    assert not pipeline.requests and not CollectionRun.objects.exists()


def test_completed_import_finishes_without_new_provider_calls(pipeline):
    result = run(ready_job(complete=True))
    assert result["collection_drained"]
    assert CollectionRun.objects.get().request_count == 0
    assert not pipeline.requests


def test_lease_expiring_during_storage_rolls_back_page(pipeline, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone
    job = ready_job(cursor="previous")
    pipeline.responses.append(page("1"))
    before = timezone.now()
    save = Post.save
    def expires(self, *args, **kwargs):
        result = save(self, *args, **kwargs)
        monkeypatch.setattr("core.collection_state.timezone.now", lambda: before + timedelta(seconds=400))
        return result
    monkeypatch.setattr(Post, "save", expires)
    with pytest.raises(StaleClaim):
        run(job)
    assert not Post.objects.filter(pk="1").exists()
    assert CollectionRun.objects.get(job=job).scopes.get().cursor == "previous"


def test_storage_probe_updates_same_page_without_http_or_new_posts(pipeline):
    pipeline.responses.append(page("1"))
    pipeline.run(batch=True)
    job = ready_job(complete=True, probe=True)
    run(job)
    before = len(pipeline.requests)
    output = StringIO()
    call_command("backfill", collection_job=str(job.pk), storage_probe=True, stdout=output)
    import json
    report = json.loads(output.getvalue())
    assert report["provider_requests"] == report["model_requests"] == 0
    assert report["updated_posts"] == 1 and Post.objects.count() == 1
    assert len(pipeline.requests) == before


def test_headline_revision_does_not_change_batch_collection_identity(pipeline, monkeypatch):
    job = ready_job()
    monkeypatch.setenv("X_MONITOR_HEADLINE_CONTROL_REVISION", "unrelated-headline-release")
    pipeline.responses.append(page("1"))
    assert run(job)["collection_drained"]


def test_collection_configuration_change_is_rejected_before_claim(pipeline, monkeypatch):
    job = ready_job()
    original = load_config
    def changed(path):
        cfg = original(path)
        cfg.enabled_models = ["qwen"]
        return cfg
    monkeypatch.setattr("monitor.backfill_collection.load_config", changed)
    with pytest.raises(ValueError, match="configuration changed"):
        run(job)
    assert not pipeline.requests and not CollectionRun.objects.exists()


def test_blocked_page_retains_valid_post_evidence_without_advancing_cursor(pipeline):
    job = ready_job(cursor="previous")
    body = page("1", cursor="unsafe-next")
    outside = page("outside")["tweets"][0]
    outside["createdAt"] = "Mon Aug 10 00:10:00 +0000 2026"
    body["tweets"].append(outside)
    pipeline.responses.append(body)
    result = run(job)
    scope = CollectionRun.objects.get(pk=result["run_id"]).scopes.get()
    assert scope.outcome == "blocked" and scope.cursor == "previous"
    assert result["recovered_post_ids"] == ["1"]
    assert scope.raw_count == 2
    assert Post.objects.filter(pk="1").exists() and not Post.objects.filter(pk="outside").exists()


def test_current_policy_job_command_plans_all_routes_without_provider(pipeline, monkeypatch, tmp_path):
    from tests.test_rare_type_cycle import _enable
    cfg = load_config(Path("config.yaml"))
    _enable(cfg, tmp_path)
    monkeypatch.setattr("monitor.management.commands.backfill.load_config", lambda path: cfg)
    output = StringIO()
    call_command("backfill", plan_collection_job="history-test", since="2026-08-09",
                 until="2026-08-10", dry_run=True, stdout=output)
    import json
    definition = json.loads(output.getvalue())["definition"]
    scope = definition["scope"]
    assert {unit["ownership"]["call_id"] for unit in scope["units"]} == {
        "A", "B1", "B2", "B3", "C1", "C2", "C3", "C4", "RARE_EXTRA",
    }
    assert scope["author_scope"]["historical_membership_reconstructed"] is False
    assert scope["maximum_model_requests"] > 0
    assert not pipeline.requests and not CollectionRun.objects.exists()


def test_recoverable_scope_error_does_not_starve_independent_queries(pipeline):
    import copy

    import requests
    job = ready_job(requests=2)
    definition = copy.deepcopy(job.definition)
    second = copy.deepcopy(definition["scope"]["units"][0])
    second["scope_key"] = "B1:independent"
    definition["scope"]["units"].append(second)
    job.delete()
    source = DataSource.objects.get(pk="x")
    job = register_job(job_key="two-scopes", source=source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    job = set_job_state(job.pk, "ready")
    pipeline.responses.extend([requests.ReadTimeout("scope unavailable"), page("survivor")])
    with pytest.raises(CommandError):
        run(job)
    attempt = CollectionRun.objects.get(job=job)
    assert Post.objects.filter(pk="survivor").exists()
    assert attempt.scopes.get(scope_key="B1:independent").enumeration_complete
    assert not attempt.scopes.get(scope_key="B1:aug09").enumeration_complete
    for scoped in attempt.scopes.all():
        assert scoped.requested_start_at == datetime.fromtimestamp(1786233600, UTC)
        assert scoped.requested_end_at == datetime.fromtimestamp(1786234500, UTC)
        assert scoped.job_target.search_query.query_text == "Qwen"
        assert scoped.job_target.target_role == "B1"


def policy_job(monkeypatch, tmp_path, *, calls, rare=False, selected_calls=None):
    from monitor.backfill_collection import plan_job_definition
    cfg = load_config(Path("config.yaml"))
    if rare:
        from tests.test_rare_type_cycle import _enable
        _enable(cfg, tmp_path)
    monkeypatch.setattr("monitor.backfill_collection.load_config", lambda path: cfg)
    extra = {"call_ids": selected_calls} if selected_calls is not None else {}
    definition = plan_job_definition(
        cfg=cfg, since_epoch=1786233600, until_epoch=1786234500, brands=["qwen"],
        requests=3, model_requests=60, seconds=300, maximum_requests=20, maximum_models=100,
        **extra,
    )
    for unit in definition["scope"]["units"]:
        if unit["ownership"]["call_id"] not in calls:
            unit.update(outcome="complete", enumeration_complete=True)
    source, _ = DataSource.objects.get_or_create(id="x", defaults={"name": "X", "source_type": "social"})
    job = register_job(job_key="policy-test", source=source, purpose="content", operation="x_backfill",
                       mode="historical", definition=definition)
    return set_job_state(job.pk, "ready")


def test_historical_call_a_frozen_official_role_bypasses_body_matching(pipeline, monkeypatch, tmp_path):
    from core.models import PostBrandMention, TwitterListMembership
    from monitor.cycle import _resolve_x_monitor_list_id
    from tests.test_call_a_role_routing import _seed_author
    account = _seed_author(edges=[("qwen", "official")])
    list_id = _resolve_x_monitor_list_id(load_config(Path("config.yaml")))
    TwitterListMembership.objects.filter(account=account).update(list_id=list_id)
    job = policy_job(monkeypatch, tmp_path, calls={"A"})
    TwitterListMembership.objects.filter(account=account).update(active=False)
    body = page("1")
    body["tweets"][0]["text"] = "A release announcement without any tracked keyword"
    pipeline.responses.append(body)
    result = run(job)
    assert result["collection_drained"] and result["recovered_post_ids"] == ["1"]
    assert PostBrandMention.objects.filter(post_id="1", brand_id="qwen", source="author_account").exists()
    assert not TwitterListMembership.objects.get(account=account).active
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()


@pytest.mark.parametrize("role", ["official", "staff"])
def test_historical_call_a_matches_normal_roles_outside_keyword_brands(
    pipeline, monkeypatch, tmp_path, role,
):
    from core.models import PostBrand, TwitterListMembership
    from monitor.cycle import (
        CycleRunner,
        _build_brand_index,
        _resolve_x_monitor_list_id,
    )
    from tests.test_call_a_role_routing import _call, _seed_author
    from x_monitor.apify import _normalize_tweet

    account = _seed_author(edges=[("outside-keyword-brands", role)])
    cfg = load_config(Path("config.yaml"))
    list_id = _resolve_x_monitor_list_id(cfg)
    TwitterListMembership.objects.filter(account=account).update(list_id=list_id)
    job = policy_job(monkeypatch, tmp_path, calls={"A"})
    body = page("1")
    body["tweets"][0]["text"] = "An announcement for our community."
    normal = _normalize_tweet(body["tweets"][0])
    normal["id"] = "normal-role-parity"
    runner = CycleRunner(cfg=cfg, _relevancy_llm_call=lambda system, user: "KEEP")
    runner._prepare_call_a_roles([normal], list_id=list_id)
    runner._attribute_items([normal], _build_brand_index(["qwen"]), {})
    runner._route_and_persist(_call(), [normal])
    expected = set(PostBrand.objects.filter(post_id="normal-role-parity").values_list("brand_id", flat=True))
    assert expected == {"outside-keyword-brands"}

    pipeline.responses.append(body)
    report = run(job)
    assert report["recovered_post_ids"] == ["1"]
    assert set(PostBrand.objects.filter(post_id="1").values_list("brand_id", flat=True)) == expected
    assert job.definition["scope"]["brands"] == ["qwen"]


def test_explicit_current_policy_a_only_job_uses_real_scope_without_fake_completions(
    pipeline, monkeypatch, tmp_path,
):
    job = policy_job(monkeypatch, tmp_path, calls={"A"}, selected_calls=["A"])
    scope = job.definition["scope"]
    assert scope["selected_call_ids"] == scope["required_call_ids"] == ["A"]
    assert len(scope["units"]) == 1 and not scope["units"][0].get("enumeration_complete")
    pipeline.responses.append(page("1"))
    report = run(job)
    assert report["collection_drained"] and report["scopes_complete"] == report["scopes_total"] == 1
    assert len(pipeline.requests) == 1 and "list:" in pipeline.requests[0]["query"]


@pytest.mark.parametrize("selection", [[], ["UNRECOGNIZED"], ["A", "A"], [None], "A"])
def test_explicit_route_selection_rejects_empty_or_unknown_before_claim(
    pipeline, monkeypatch, tmp_path, selection,
):
    with pytest.raises(ValueError, match="route selection"):
        policy_job(monkeypatch, tmp_path, calls={"A"}, selected_calls=selection)
    assert not CollectionRun.objects.exists() and not pipeline.requests


def test_saved_explicit_route_selection_cannot_hide_a_different_missing_route(
    pipeline, monkeypatch, tmp_path,
):
    import copy

    job = policy_job(monkeypatch, tmp_path, calls={"A"}, selected_calls=["A"])
    definition = copy.deepcopy(job.definition)
    definition["scope"]["selected_call_ids"] = ["B1"]
    source = job.source
    job.delete()
    job = register_job(job_key="tampered-selection", source=source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    job = set_job_state(job.pk, "ready")
    with pytest.raises(ValueError, match="route omitted"):
        run(job)
    assert not CollectionRun.objects.exists() and not pipeline.requests


@pytest.mark.parametrize(("verdict", "interrupt"), [("KEEP", False), ("DROP", False), ("KEEP", True)])
def test_historical_call_a_staff_uses_on_demand_model_and_durable_usage(pipeline, monkeypatch, tmp_path, verdict, interrupt):
    from types import SimpleNamespace

    from core.models import TwitterListMembership
    from monitor.cycle import _resolve_x_monitor_list_id
    from tests.test_call_a_role_routing import _seed_author
    from x_monitor.deepinfra import DeepInfraChatCompletionsClient
    account = _seed_author(edges=[("qwen", "staff")])
    list_id = _resolve_x_monitor_list_id(load_config(Path("config.yaml")))
    TwitterListMembership.objects.filter(account=account).update(list_id=list_id)
    job = policy_job(monkeypatch, tmp_path, calls={"A"})
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "test-on-demand")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test-scheduled")
    monkeypatch.setattr("x_monitor.reattribute.build_relevancy_client_from_env", REAL_RELEVANCY_FACTORY)
    calls = []
    def model(self, **kwargs):
        assert not connection.in_atomic_block
        attempt = CollectionRun.objects.get(job=job)
        assert attempt.report["model_requests"] == 1
        assert next(iter(attempt.report["staff_relevance"].values()))["status"] == "sent"
        assert self.api_key == "test-on-demand"
        calls.append(kwargs)
        return SimpleNamespace(text=verdict, provider_usage={"cost_usd": "0.0001"})
    monkeypatch.setattr(DeepInfraChatCompletionsClient, "messages_create_text", model)
    body = page("1")
    body["tweets"][0]["text"] = "We released our next-generation model"
    sibling = dict(body["tweets"][0], id="2")
    body["tweets"].append(sibling)
    pipeline.responses.append(body)
    if interrupt:
        original = Post.save
        def fail(self, *args, **kwargs):
            raise RuntimeError("storage interrupted after paid relevance reply")
        monkeypatch.setattr(Post, "save", fail)
        with pytest.raises(CommandError):
            run(job)
        assert not Post.objects.exists()
        monkeypatch.setattr(Post, "save", original)
        pipeline.responses.append(body)
    report = run(job)
    assert report["collection_drained"] and len(calls) == 1
    attempt = CollectionRun.objects.filter(job=job).order_by("started_at").first()
    assert attempt.report["model_responses"][0]["usage"]["cost_usd"] == "0.0001"
    assert report["recovered_post_ids"] == (["1", "2"] if verdict == "KEEP" else [])
    assert CollectionRun.objects.get(pk=report["run_id"]).scopes.get(scope_key="A").raw_count == 2
    evidence = CollectionRun.objects.get(pk=report["run_id"]).scopes.get(scope_key="A").envelopes[-1]
    assert evidence["received_post_ids"] == ["1", "2"]
    assert {entry["reason"] for entry in evidence["exclusions"]} == ({"relevance_drop"} if verdict == "DROP" else set())
    assert len(evidence["post_ids"]) + len(evidence["exclusions"]) == 2


def test_historical_rare_inbox_precedes_gate_and_never_uses_live_slot(pipeline, monkeypatch, tmp_path):
    from decimal import Decimal

    from core.collection_storage_migration import (
        project_scope_rare_hits_batch,
        scope_rare_hit_mismatch_counts,
    )
    from core.models import (
        CollectionScopeRareHit,
        CollectionScopeRun,
        RareTypeDecisionProcessingCycle,
        RareTypeSearchHit,
        RareTypeSearchRun,
    )
    from x_monitor.jev_decisions import QUESTION_SET, JevDecisionsClient, JevResponse
    job = policy_job(monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe")
    def model(self, request_bytes, **kwargs):
        assert not connection.in_atomic_block
        assert RareTypeSearchHit.objects.count() == 1 and not Post.objects.exists()
        assert CollectionRun.objects.get(job=job).report["model_requests"] == 1
        probabilities = {key: .1 for key in QUESTION_SET}
        probabilities.update(ai_related=.95, role_opening=.95)
        return JevResponse("test-response", probabilities, 1200, 0, Decimal("0.00005"))
    monkeypatch.setattr(JevDecisionsClient, "submit", model)
    from monitor import backfill_enrichment
    reopen = backfill_enrichment.reopen_incomplete_successes
    reopened = []
    def inspect_reopen(job, observations):
        reopened.extend(observations.values_list("post_id", flat=True))
        return reopen(job, observations)
    monkeypatch.setattr(backfill_enrichment, "reopen_incomplete_successes", inspect_reopen)
    pipeline.responses.append(page("rare-kept"))
    report = run(job)
    assert report["collection_drained"] and report["rare_gate_pending"] == 0
    assert report["recovered_post_ids"] == ["rare-kept"]
    assert RareTypeSearchHit.objects.get().post_id == "rare-kept"
    assert not RareTypeSearchRun.objects.filter(lane="rare_types").exists()
    assert not RareTypeDecisionProcessingCycle.objects.filter(lane="rare_types").exists()
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()
    assert reopened == ["rare-kept"]
    scoped = CollectionRun.objects.get(pk=report["run_id"]).scopes.get(scope_key="RARE_EXTRA")
    evidence = scoped.envelopes[0]
    assert evidence["received_post_ids"] == evidence["inbox_post_ids"] == ["rare-kept"]
    assert evidence["raw_count"] == 1 and len(evidence["rare_hit_ids"]) == 1
    assert list(scoped.rare_hit_memberships.values_list("rare_hit_id", flat=True)) == evidence["rare_hit_ids"]
    assert scope_rare_hit_mismatch_counts() == (0, 0)
    CollectionScopeRareHit.objects.filter(scope_run=scoped).delete()
    replay = CollectionScopeRun.objects.create(
        run=scoped.run, scope_kind="x_query", scope_key="rare-replay",
        ownership=scoped.ownership,
        envelopes=[{"rare_hit_ids": evidence["rare_hit_ids"]}],
    )
    assert scope_rare_hit_mismatch_counts() == (2, 0)
    assert project_scope_rare_hits_batch(after_id=scoped.pk - 1).inserted == 2
    assert set(CollectionScopeRareHit.objects.filter(
        rare_hit_id=evidence["rare_hit_ids"][0]
    ).values_list("scope_run_id", flat=True)) == {scoped.pk, replay.pk}
    assert scope_rare_hit_mismatch_counts() == (0, 0)
    assert not evidence["exclusions"]


def test_historical_rare_resume_uses_saved_inbox_and_exact_cursor(pipeline, monkeypatch, tmp_path):
    from decimal import Decimal

    import requests

    from core.models import CollectionScopeRun, RareTypeSearchHit
    from x_monitor.jev_decisions import QUESTION_SET, JevDecisionsClient, JevResponse
    job = policy_job(monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe")
    model_calls = []
    def model(self, request_bytes, **kwargs):
        assert not connection.in_atomic_block
        model_calls.append(request_bytes)
        probabilities = {key: .1 for key in QUESTION_SET}
        probabilities.update(ai_related=.95, role_opening=.95)
        return JevResponse("test-response", probabilities, 1200, 0, Decimal("0.00005"))
    monkeypatch.setattr(JevDecisionsClient, "submit", model)
    pipeline.responses.extend([page("first", cursor="next"), requests.ReadTimeout("temporary")])
    with pytest.raises(CommandError):
        run(job)
    assert RareTypeSearchHit.objects.count() == 1 and not model_calls and not Post.objects.exists()
    CollectionScopeRun.objects.filter(run__job=job).update(envelopes=[])
    pipeline.responses.append(page("second"))
    report = run(job)
    assert report["collection_drained"] and report["rare_gate_pending"] == 0
    assert report["recovered_post_ids"] == ["first", "second"]
    assert pipeline.requests[-1]["cursor"] == "next"
    assert len(model_calls) == 2 and RareTypeSearchHit.objects.count() == 2


def test_current_policy_omitted_route_is_rejected_before_claim(pipeline, monkeypatch, tmp_path):
    import copy
    job = policy_job(monkeypatch, tmp_path, calls={"A"})
    definition = copy.deepcopy(job.definition)
    definition["scope"]["units"] = definition["scope"]["units"][1:]
    definition["scope"]["required_call_ids"] = [u["ownership"]["call_id"] for u in definition["scope"]["units"]]
    source = job.source
    job.delete()
    job = register_job(job_key="omitted-route", source=source, purpose="content", operation="x_backfill",
                       mode="historical", definition=definition)
    job = set_job_state(job.pk, "ready")
    with pytest.raises(ValueError, match="route omitted"):
        run(job)
    assert not CollectionRun.objects.exists() and not pipeline.requests


def test_historical_rare_unknown_model_outcome_is_not_resent(pipeline, monkeypatch, tmp_path):
    from core.models import RareTypeDecisionAttempt
    from x_monitor.jev_decisions import JevDecisionError, JevDecisionsClient
    job = policy_job(monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe")
    calls = []
    def timeout(self, request_bytes, **kwargs):
        calls.append(request_bytes)
        raise JevDecisionError("timeout")
    monkeypatch.setattr(JevDecisionsClient, "submit", timeout)
    pipeline.responses.append(page("unknown"))
    first = run(job)
    assert first["collection_drained"] and first["rare_gate_pending"] == 1
    second = run(job)
    assert second["collection_drained"] and second["rare_gate_pending"] == 1
    assert len(calls) == len(pipeline.requests) == 1
    attempt = RareTypeDecisionAttempt.objects.get()
    assert attempt.state == "retained" and attempt.error_code == "timeout"


def test_terminal_rare_review_finishes_collection_and_verifies_saved_posts(pipeline, monkeypatch, tmp_path):
    from decimal import Decimal

    from core.models import PostEnrichmentState, RareTypeSearchHit
    from monitor.backfill_enrichment import execute_enrichment, policy_snapshot
    from monitor.cycle import CycleRunner
    from scripts.backfill_verify import verify_window
    from tests.test_backfill_direct_enrichment import DirectProvider
    from x_monitor.deepinfra import DeepInfraChatCompletionsClient
    from x_monitor.jev_decisions import QUESTION_SET, JevDecisionsClient, JevResponse

    job = policy_job(
        monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True,
        selected_calls=["RARE_EXTRA"],
    )
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe")
    outcomes = iter(["kept", "review", "junk"])
    gate_calls = []

    def model(self, request_bytes, **kwargs):
        outcome = next(outcomes)
        gate_calls.append(outcome)
        probabilities = {key: .1 for key in QUESTION_SET}
        if outcome == "kept":
            probabilities.update(ai_related=.95, role_opening=.95)
        elif outcome == "review":
            probabilities.update(ai_related=.5, role_opening=.95)
        return JevResponse("response-" + outcome, probabilities, 1200, 0, Decimal("0.00005"))

    monkeypatch.setattr(JevDecisionsClient, "submit", model)
    body = page("rare-kept")
    body["tweets"][0]["text"] = "I tried Qwen today."
    body["tweets"].extend(page("rare-review")["tweets"] + page("rare-junk")["tweets"])
    pipeline.responses.append(body)
    report = run(job)
    assert report["collection_drained"] and report["rare_gate_pending"] == 0
    assert report["rare_gate_review_needed"] == 1
    assert report["rare_gate_state_counts"] == {"kept": 1, "review_needed": 1, "junk": 1}
    review = RareTypeSearchHit.objects.get(provider_post_id="rare-review")
    assert report["rare_gate_review_hit_ids"] == [review.pk]
    job.refresh_from_db()
    assert job.state == "completed" and job.last_success.status == "success"
    assert run(job)["report"]["rare_gate_review_needed"] == 1
    assert gate_calls == ["kept", "review", "junk"]
    assert len(pipeline.requests) == 1

    # Restore the real shared publisher replaced by the collection fixture.
    # A real verifier then inspects the accepted Post, independently of review.
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", pipeline.post_fetch_method)
    call_command("seed_i18n_labels", stdout=StringIO())
    cfg = load_config(Path("config.yaml"))
    cfg.llm.literal_translation_v2_enabled = True
    provider = DirectProvider()
    delegates = {
        role: DeepInfraChatCompletionsClient(
            api_key="test", model=model, request_profile=profile,
            transport=lambda *a, **k: pytest.fail("uncaptured inference"),
        ) for role, model, profile in [
            ("translation", cfg.llm.translator_model, cfg.llm.translator_deepinfra_request_profile),
            ("classification", cfg.llm.classifier_model, cfg.llm.classifier_deepinfra_request_profile),
        ]
    }
    from datetime import timedelta

    from django.utils import timezone

    policy = policy_snapshot(max_usd="5", deadline=timezone.now() + timedelta(hours=1))
    for turn in range(8):
        result = execute_enrichment(
            job.pk, cfg=cfg, api_key="test", delegates=delegates,
            policy=policy if turn == 0 else None, transport="direct",
            direct_client_factory=provider.factory,
        )
        if result["status"] == "completed":
            break
    verified = verify_window(job.pk, cfg=cfg)
    assert verified["status"] == "verified" and verified["checked_posts"] == 1
    PostEnrichmentState.objects.filter(post_id="rare-kept").update(translation_status="pending")
    failed = verify_window(job.pk, cfg=cfg)
    assert failed["status"] == "failed" and failed["checked_posts"] == 1
    assert gate_calls == ["kept", "review", "junk"]


@pytest.mark.parametrize("gate_state", ["decision_pending", "provider_failed", "expired_unprocessed"])
@pytest.mark.parametrize("posted", [False, True])
def test_rare_unfinished_states_stay_pending_even_with_an_existing_post(
    pipeline, monkeypatch, tmp_path, gate_state, posted,
):
    from core.models import RareTypeSearchHit
    from monitor.backfill_collection import _report
    from x_monitor.jev_decisions import JevDecisionError, JevDecisionsClient

    job = policy_job(monkeypatch, tmp_path, calls={"RARE_EXTRA"}, rare=True)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe")
    monkeypatch.setattr(JevDecisionsClient, "submit", lambda *a, **k: (_ for _ in ()).throw(JevDecisionError("timeout")))
    pipeline.responses.append(page("unresolved"))
    first = run(job)
    hit = RareTypeSearchHit.objects.get()
    hit.gate_state = gate_state
    if posted:
        hit.post = Post.objects.create(tweet_id="unresolved", text="Qwen model release")
    hit.save()
    report = _report(job, first["run_id"])
    assert report["rare_gate_pending"] == 1
    assert report["rare_gate_pending_hit_ids"] == [hit.pk]
    assert report["rare_gate_review_needed"] == 0


def test_page_ledger_reconciles_duplicate_ids_and_every_deterministic_rejection(pipeline, monkeypatch):
    from dataclasses import replace

    from monitor import cycle
    original = cycle.plan_calls_for_cycle
    monkeypatch.setattr(cycle, "plan_calls_for_cycle", lambda *args, **kwargs: [
        replace(call, not_include=["forbidden"]) if call.call_id == "B1" else call
        for call in original(*args, **kwargs)
    ])
    body = page("kept")
    body["tweets"].append(dict(body["tweets"][0]))
    unmatched = page("unmatched")["tweets"][0]
    unmatched["text"] = "ordinary lunch without tracked terms"
    excluded = page("excluded")["tweets"][0]
    excluded["text"] = "Qwen forbidden"
    outside = page("outside")["tweets"][0]
    outside["createdAt"] = "Mon Aug 10 00:10:00 +0000 2026"
    invalid = page("invalid")["tweets"][0]
    invalid["createdAt"] = "not a date"
    body["tweets"].extend([unmatched, excluded, outside, invalid])
    pipeline.responses.append(body)
    report = run(ready_job())
    row = CollectionRun.objects.get(pk=report["run_id"]).scopes.get()
    evidence = row.envelopes[-1]
    assert row.raw_count == 6
    assert evidence["received_post_ids"] == ["kept", "kept", "unmatched", "excluded", "outside", "invalid"]
    assert evidence["post_ids"] == ["kept"]
    assert {entry["appearance"]: entry["reason"] for entry in evidence["exclusions"]} == {
        1: "duplicate_native_id", 2: "unmatched_attribution", 3: "not_include",
        4: "out_of_window", 5: "invalid_time",
    }
    assert len(evidence["post_ids"]) + len(evidence["exclusions"]) == row.raw_count
    assert evidence["distinct_received_count"] == 5 and not row.enumeration_complete


def test_all_rejected_page_retains_receipt_and_can_truthfully_drain(pipeline):
    body = page("rejected")
    body["tweets"][0]["text"] = "ordinary lunch without tracked terms"
    pipeline.responses.append(body)
    report = run(ready_job())
    row = CollectionRun.objects.get(pk=report["run_id"]).scopes.get()
    evidence = row.envelopes[-1]
    assert report["collection_drained"] and not report["recovered_post_ids"]
    assert row.raw_count == 1 and evidence["received_post_ids"] == ["rejected"]
    assert evidence["exclusions"] == [{"post_id": "rejected", "appearance": 0, "reason": "unmatched_attribution"}]


def test_staff_timeout_preserves_shared_fail_open_and_continues_pages_and_routes(pipeline, monkeypatch, tmp_path):
    from core.models import TwitterListMembership
    from monitor.cycle import _resolve_x_monitor_list_id
    from tests.test_call_a_role_routing import _seed_author
    from x_monitor.deepinfra import DeepInfraChatCompletionsClient
    account = _seed_author(edges=[("qwen", "staff")])
    list_id = _resolve_x_monitor_list_id(load_config(Path("config.yaml")))
    TwitterListMembership.objects.filter(account=account).update(list_id=list_id)
    job = policy_job(monkeypatch, tmp_path, calls={"A", "B1"})
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "test-on-demand")
    monkeypatch.setattr("x_monitor.reattribute.build_relevancy_client_from_env", REAL_RELEVANCY_FACTORY)
    model_calls = []
    def timeout(self, **kwargs):
        model_calls.append(kwargs)
        raise TimeoutError("unknown provider outcome")
    monkeypatch.setattr(DeepInfraChatCompletionsClient, "messages_create_text", timeout)
    first = page("1", cursor="second")
    second = page("2")
    for body in (first, second):
        body["tweets"][0]["author"]["id"] = "author-1"
        body["tweets"][0]["text"] = "We released our next-generation model"
    pipeline.responses.extend([first, second, page("independent")])
    report = run(job)
    assert report["collection_drained"] and report["recovered_post_ids"] == ["1", "2", "independent"]
    assert len(model_calls) == 1 and len(pipeline.requests) == 3
    assert pipeline.requests[1]["cursor"] == "second"
    attempt = CollectionRun.objects.get(job=job)
    evidence = attempt.scopes.get(scope_key="A").envelopes
    assert all(row["relevancy_degraded"] for row in evidence)
    assert next(iter(attempt.report["staff_relevance"].values()))["status"] == "sent"


def test_clipped_page_records_received_tail_ids_without_advancing(pipeline):
    body = page("0")
    body["tweets"] = [page(str(index))["tweets"][0] for index in range(21)]
    pipeline.responses.append(body)
    report = run(ready_job())
    row = CollectionRun.objects.get(pk=report["run_id"]).scopes.get()
    evidence = row.envelopes[-1]
    assert not row.enumeration_complete and row.cursor is None
    assert row.raw_count == evidence["raw_count"] == 21
    assert evidence["received_post_ids"] == [str(index) for index in range(21)]
    assert len(evidence["post_ids"]) == 20
    assert evidence["exclusions"] == [{"post_id": "20", "appearance": 20, "reason": "clipped_page_tail"}]


@pytest.mark.parametrize("http_status", [401, 402, 403, 429])
def test_provider_safety_response_stops_all_scopes_and_preserves_cursor(pipeline, monkeypatch, http_status, caplog):
    import copy
    from types import SimpleNamespace
    job = ready_job(requests=2, cursor="committed-cursor")
    definition = copy.deepcopy(job.definition)
    second = copy.deepcopy(definition["scope"]["units"][0])
    second["scope_key"] = "independent"
    definition["scope"]["units"].append(second)
    source = job.source
    job.delete()
    job = register_job(job_key="provider-safety", source=source, purpose="content", operation="x_backfill",
                       mode="historical", definition=definition)
    job = set_job_state(job.pk, "ready")
    requests = []
    secret_body = "credential-sensitive-provider-body-never-log"
    def get(*args, **kwargs):
        requests.append(kwargs["params"])
        return SimpleNamespace(status_code=http_status, content=secret_body.encode(), text=secret_body,
                               headers={"Retry-After": "999999"}, json=lambda: {"error": secret_body})
    monkeypatch.setattr("x_monitor.apify.requests.get", get)
    with pytest.raises(CommandError) as caught:
        run(job)
    assert len(requests) == 1
    assert caught.value.response_status_code == http_status
    assert caught.value.permanent is (http_status != 429)
    assert secret_body not in str(caught.value) and secret_body not in caplog.text
    attempt = CollectionRun.objects.get(job=job)
    assert attempt.request_count == 1 and attempt.status == "failed"
    assert not attempt.report["collection_drained"]
    assert attempt.report["global_failure"]["response_status_code"] == http_status
    for row in attempt.scopes.all():
        assert row.cursor == "committed-cursor" and not row.enumeration_complete
    receipt = attempt.scopes.get(scope_key="B1:aug09").envelopes[-1]
    assert receipt["response_status_code"] == http_status and receipt["pages_received"] == 0
    assert secret_body not in str(attempt.report) and secret_body not in str(receipt)
    if http_status == 429:
        job.refresh_from_db()
        assert job.next_retry_at is not None
        assert attempt.report["global_failure"]["retry_after_seconds"] == 300
        with pytest.raises(CommandError):
            run(job)
        assert len(requests) == CollectionRun.objects.filter(job=job).count() == 1


def test_backfill_provider_entities_reach_shared_post_writer(pipeline, provider_tweet_entities):
    from core.product_verification import source_repo_evidence
    from x_monitor.attribution import attribute_to_brands
    body = page("99112234")
    body["tweets"][0]["entities"] = provider_tweet_entities
    pipeline.responses.append(body)
    report = run(ready_job())
    assert report["collection_drained"]
    post = Post.objects.get(pk="99112234")
    assert post.entities == provider_tweet_entities
    assert source_repo_evidence(post, "Qwen/Qwen3-4B")["exact_hf_repo_link"]
    mentions = attribute_to_brands(
        {"tweet_id": post.pk, "created_at": post.created_at.isoformat(), "entities": post.entities},
        brands_accounts={"1001": "qwen"}, brand_hashtags={"qwen": "qwen"},
        compiled_keyword_index=(None, {}), search_query=[], brand_search_terms={},
    )
    assert {(m.brand_id, m.source) for m in mentions} == {("qwen", "user_mention"), ("qwen", "hashtag")}
