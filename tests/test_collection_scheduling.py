"""Real command paths prove scheduler authority and fenced numeric admission."""

import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import httpx
import pytest
from django.core.management import call_command

from core.benchmark_metric_identity import configure_collection
from core.collection_budgets import invocation_budget
from core.collection_jobs import register_job, set_job_state
from core.collection_scheduling import dispatch_due, due_job, take_metric_authority
from core.collection_state import claim_job, finish_run
from core.models import CollectionRun, DataSource, MetricValue
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
NOW = datetime(2026, 10, 13, 11, tzinfo=UTC)


def scheduled(settings):
    settings.BENCHMARK_COLLECTION_ENABLED = True
    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    contract = configure_collection(spec)
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.save()
    job = register_job(
        job_key="daily",
        source=source,
        purpose="metric",
        operation="collect_metrics",
        contract=contract,
        mode="recurring",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "daily_utc", "hour": 10, "driver": "shared"},
            "budgets": {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    return set_job_state(job.pk, "ready", now=NOW)


def test_registration_preserves_legacy_then_takeover_blocks_both_paths(
    settings, monkeypatch
):
    job = scheduled(settings)
    assert due_job(job, now=NOW)["reason"] == "legacy_scheduler_owns_dispatch"
    take_metric_authority(job.pk)
    job.refresh_from_db()
    assert due_job(job, now=NOW)["due"]
    set_job_state(job.pk, "paused")
    monkeypatch.setattr(
        httpx, "Client", lambda **_: (_ for _ in ()).throw(AssertionError("dry client"))
    )
    out = StringIO()
    call_command("collect_benchmark_due", contract=str(job.contract_id), stdout=out)
    assert json.loads(out.getvalue())[0]["authority"] == "shared"
    assert not json.loads(out.getvalue())[0]["due"]
    assert CollectionRun.objects.count() == 0


def test_utc_slot_and_failure_cooldown_are_separate_from_success(settings):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    job.refresh_from_db()
    assert not due_job(job, now=NOW.replace(hour=9))["due"]
    claim = claim_job(job.pk, now=NOW)
    run = finish_run(
        claim, status="failed", retry_at=NOW + timedelta(minutes=15), now=NOW
    )
    job.refresh_from_db()
    assert job.last_success_id is None and job.last_attempt_id == run.pk
    assert due_job(job, now=NOW + timedelta(minutes=14))["reason"] == "cooldown"
    assert due_job(job, now=NOW + timedelta(minutes=16))["slot"].endswith(
        "10:00:00+00:00"
    )


def test_metric_due_command_writes_values_to_claimed_run_once(settings, monkeypatch):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    seen = []

    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 0, "downloadsAllTime": 100}
        )

    factory = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr("core.collection_scheduling.timezone.now", lambda: NOW)
    call_command("collect_jobs_due", job=str(job.pk), execute=True, stdout=StringIO())
    job.refresh_from_db()
    assert job.last_success_id == job.last_attempt_id
    run = job.last_success
    assert run.purpose == "metric" and run.status == "success" and run.job_id == job.pk
    assert run.observations.count() == 1 and MetricValue.objects.count() == 2
    assert run.request_count == 1
    assert run.report["schedule_slot"] == NOW.replace(hour=10).isoformat()
    assert len(seen) == 1
    request = run.attempts.get().requests.get()
    assert request.archive_id and request.http_status == 200
    assert run.observations.get().inputs.get().input_request_id == request.pk
    # The legacy command sees shared ownership and cannot fetch the same slot again.
    call_command(
        "collect_benchmark_due",
        contract=str(job.contract_id),
        apply=True,
        stdout=StringIO(),
    )
    assert len(seen) == 1 and CollectionRun.objects.count() == 1


def test_dispatch_invocation_budget_stops_before_second_job(settings):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    job.refresh_from_db()
    # Definition registration now includes the existing GitHub provider identity.
    source = DataSource.objects.get(pk="github")
    source.enabled = True
    source.save(update_fields=["enabled"])
    other = register_job(
        job_key="catalog",
        source=source,
        purpose="catalog",
        operation="github_catalog",
        mode="recurring",
        definition={
            "version": 1,
            "scope": {"publishers": []},
            "schedule": {"kind": "interval", "seconds": 86400, "driver": "shared"},
            "budgets": {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(other.pk, "ready", now=NOW)
    calls = []
    budget = invocation_budget(
        httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        ),
        requests=1,
        max_bytes=10000,
    )

    def execute(obj, decision, child):
        calls.append(obj.pk)
        child.hf_counts("lab/model")
        claim = claim_job(obj.pk, now=NOW)
        return finish_run(claim, status="success", request_count=1, now=NOW)

    rows = dispatch_due(budget=budget, now=NOW, execute=True, executor=execute)
    assert calls == [job.pk] and budget.remaining == 0
    assert rows[-1]["reason"] == "invocation_budget_exhausted"


def test_external_x_cron_is_never_due_even_when_ready():
    source, _ = DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    source.enabled = False
    source.save()
    job = register_job(
        job_key="x-external",
        source=source,
        purpose="content",
        operation="x_cycle",
        mode="recurring",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {
                "kind": "interval",
                "seconds": 900,
                "driver": "external_render_cron",
            },
            "budgets": {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    job = set_job_state(job.pk, "ready", now=NOW)
    assert due_job(job, now=NOW)["reason"] == "external_or_manual_driver"
    with pytest.raises(ValueError, match="caller authorization"):
        claim_job(job.pk, now=NOW)
    # Existing scheduled/on-demand authority is explicit and independent of metric flags.
    claim = claim_job(job.pk, manual_authorized=True, now=NOW)
    finish_run(claim, status="success", now=NOW)


def test_late_metric_response_cannot_write_after_job_is_paused(settings, monkeypatch):
    job = scheduled(settings)
    factory = httpx.Client

    def response(request):
        set_job_state(job.pk, "paused")
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 1, "downloadsAllTime": 100}
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(response))
    )
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command(
            "collect_benchmark_metrics",
            contract=str(job.contract_id),
            source="hf",
            start_date="2026-10-13",
            end_date="2026-10-13",
            job=str(job.pk),
            apply=True,
            stdout=StringIO(),
        )
    assert MetricValue.objects.count() == 0
    job.refresh_from_db()
    assert job.active_run_id is None and job.last_attempt.status == "aborted"


def test_failed_readiness_rolls_back_scheduling_takeover(settings):
    from django.core.management.base import CommandError

    job = scheduled(settings)
    job.source.enabled = False
    job.source.save()
    with pytest.raises(CommandError):
        call_command(
            "collection_job_state",
            job=str(job.pk),
            state="ready",
            take_metric_authority=True,
            apply=True,
            stdout=StringIO(),
        )
    job.source.refresh_from_db()
    assert "collection_job_authorities" not in job.source.metadata


def test_existing_legacy_source_lock_prevents_paid_shared_fetch(settings, monkeypatch):
    import psycopg
    from django.core.management.base import CommandError
    from django.db import connection

    from core.measurement_taxonomy import digest

    job = scheduled(settings)
    factory = httpx.Client

    def unexpected(request):
        raise AssertionError("provider called while legacy source is active")

    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(unexpected))
    )
    config = connection.settings_dict
    with (
        psycopg.connect(
            dbname=config["NAME"],
            host=config["HOST"],
            port=config["PORT"],
            user=config["USER"],
            password=config["PASSWORD"],
        ) as db,
        db.cursor() as cursor,
    ):
        key = int(digest(["benchmark-metrics-v1", str(job.contract_id), "hf"])[:15], 16)
        cursor.execute("SELECT pg_advisory_lock(%s)", [key])
        with pytest.raises(CommandError, match="already running"):
            call_command(
                "collect_benchmark_metrics",
                contract=str(job.contract_id),
                source="hf",
                start_date="2026-10-13",
                end_date="2026-10-13",
                job=str(job.pk),
                apply=True,
                stdout=StringIO(),
            )
    job.refresh_from_db()
    assert job.last_attempt.status == "failed" and job.last_attempt.request_count == 0
