"""The deployed hourly command reaches shared acquisition and numeric storage."""

import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import httpx
import pytest
from django.core.management import call_command

from core.collection_jobs import register_job, set_job_state
from core.models import CollectionJob, MetricValue
from tests.test_hf_source_ingestion import ingestion_job
from tests.test_source_metric_projection import configured

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
NOW = datetime(2026, 10, 16, 11, tzinfo=UTC)


def routine_job(settings, *, key="routine-hf", role="inventory:lab"):
    settings.BENCHMARK_COLLECTION_ENABLED = True
    contract, raw, _, _ = configured()
    original = ingestion_job(contract)
    definition = {
        **original.definition,
        "scope": {**original.definition["scope"], "routine_role": role},
        "schedule": {"kind": "daily_utc", "hour": 10, "driver": "shared"},
    }
    obj = register_job(
        job_key=key,
        source=original.source,
        purpose="catalog",
        operation="hf_catalog",
        mode="recurring",
        definition=definition,
    )
    return set_job_state(obj.pk, "ready"), contract, raw


def test_real_hourly_entry_collects_reviewed_source_role_and_leaves_benchmark_flags(
    settings, monkeypatch
):
    from core.collection_scheduling import take_collection_authority

    job, contract, raw = routine_job(settings)
    take_collection_authority(job.pk)
    original_flags = contract.source_configuration
    seen = []

    def respond(request):
        seen.append(str(request.url))
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[raw])
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab", "numFollowers": 0})
        return httpx.Response(200, json=raw)

    factory = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr("core.collection_scheduling.timezone.now", lambda: NOW)
    output = StringIO()
    call_command(
        "collect_benchmark_due", contract=str(contract.pk), apply=True, stdout=output
    )
    rows = json.loads(output.getvalue())
    assert any(r.get("job_id") == str(job.pk) and r["applied"] for r in rows)
    assert MetricValue.objects.count() == 3 and len(seen) == 4
    contract.refresh_from_db()
    assert contract.source_configuration == original_flags
    assert not contract.source_configuration["hf"]["scheduling_enabled"]
    before = len(seen)
    call_command(
        "collect_benchmark_due",
        contract=str(contract.pk),
        apply=True,
        stdout=StringIO(),
    )
    assert len(seen) == before
    report = StringIO()
    call_command(
        "collection_status",
        contract=str(contract.pk),
        source="hf",
        identifier="lab/Model",
        stdout=report,
    )
    numbers = json.loads(report.getvalue())["values"]
    assert {v["metric"] for v in numbers} == {"downloads", "likes"}
    assert all(
        v["native_only"] and v["temporal_status"] == "unknown" and v["as_of_at"] is None
        for v in numbers
    )
    assert all(v["source_evidence"]["origin_observation_id"] for v in numbers)


def test_source_authority_inspection_is_network_free_and_preserves_ten_utc_slot(
    settings, monkeypatch
):
    from core.collection_scheduling import take_collection_authority

    job, contract, _ = routine_job(settings)
    take_collection_authority(job.pk)
    monkeypatch.setattr(
        "core.collection_scheduling.timezone.now", lambda: NOW.replace(hour=9)
    )
    monkeypatch.setattr(
        httpx, "Client", lambda **_: pytest.fail("dry inspection constructed client")
    )
    output = StringIO()
    call_command("collect_benchmark_due", contract=str(contract.pk), stdout=output)
    row = next(
        r for r in json.loads(output.getvalue()) if r.get("job_id") == str(job.pk)
    )
    assert not row["due"] and row["reason"] == "before_slot"
    assert not MetricValue.objects.exists()


def test_role_takeover_is_explicit_unique_and_rollback_preserves_registry(settings):
    from core.collection_scheduling import due_job, take_collection_authority

    job, _, _ = routine_job(settings)
    assert due_job(job, now=NOW)["reason"] == "unclaimed_collection_role"
    take_collection_authority(job.pk)
    other = register_job(
        job_key="other-hf",
        source=job.source,
        purpose="catalog",
        operation=job.operation,
        mode="recurring",
        definition=job.definition,
    )
    with pytest.raises(ValueError, match="another job"):
        take_collection_authority(other.pk)
    job.source.refresh_from_db()
    assert job.source.metadata["collection_role_authorities"]["inventory:lab"] == str(
        job.pk
    )
    assert CollectionJob.objects.get(pk=other.pk).state == "paused"


def test_fair_selection_excludes_old_manual_jobs_before_limit_and_preserves_cooldown(
    settings,
):
    from core.collection_budgets import invocation_budget
    from core.collection_scheduling import dispatch_due, take_collection_authority
    from core.collection_state import claim_job, finish_run

    job, contract, _ = routine_job(settings)
    take_collection_authority(job.pk)
    for i in range(3):
        register_job(
            job_key=f"old-replay:{i}",
            source=job.source,
            purpose="metric",
            operation="collect_metrics",
            mode="manual",
            contract=contract,
            definition={
                **job.definition,
                "scope": {},
                "schedule": {"kind": "manual", "driver": "manual"},
            },
        )
    called = []

    def execute(candidate, decision, budget):
        called.append(candidate.pk)
        claim = claim_job(candidate.pk, now=NOW)
        return finish_run(
            claim, status="partial", retry_at=NOW + timedelta(hours=4), now=NOW
        )

    monkey_budget = invocation_budget(
        httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("provider")))
    )
    rows = dispatch_due(
        execute=True, now=NOW, budget=monkey_budget, limit=1, executor=execute
    )
    assert called == [job.pk] and rows[0]["applied"]
    job.refresh_from_db()
    assert job.next_retry_at >= NOW + timedelta(hours=4)


def test_partial_continuation_does_not_wait_for_next_days_fresh_inventory_slot(settings):
    from core.collection_scheduling import due_job, take_collection_authority
    from core.collection_state import claim_job, finish_run

    job, _, _ = routine_job(settings)
    take_collection_authority(job.pk)
    previous = NOW - timedelta(days=1)
    claim = claim_job(job.pk, now=previous)
    finish_run(claim, status="partial", now=previous + timedelta(minutes=1))
    job.refresh_from_db()
    decision = due_job(job, now=NOW.replace(hour=9))
    assert decision["due"]
    assert decision["slot"] == previous.replace(hour=10).isoformat()
