"""Real command, shared runner and PostgreSQL: jobs never borrow scheduled keys."""
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
    assert second["enrichment_pending_count"] == 2
    old_scope.refresh_from_db()
    assert old_scope.cursor == "second-page" and not old_scope.enumeration_complete
    assert pipeline.requests[1]["cursor"] == "second-page"
    assert pipeline.requests[0]["query"] == pipeline.requests[1]["query"]
    assert not CallState.objects.exists() and not HarvestBacklogWindow.objects.exists()
    assert not list(pipeline.directory.glob("*.json"))


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
