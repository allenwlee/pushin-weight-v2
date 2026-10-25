"""Acquisition leases fence projection acknowledgements after numeric commit."""

from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from core.collection_jobs import register_job, set_job_state
from core.collection_state import StaleClaim, claim_job
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    MetricValue,
    TimeZone,
)
from core.source_metric_projection import drain_pending_projections, enqueue_projection
from scripts.benchmark_download_collector.sources import Budget
from tests.test_source_metric_projection import configured

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def seed_utc_timezone():
    TimeZone.objects.get_or_create(pk="UTC")


def capture(operation="hf_catalog", *, queued=True):
    source = "hf" if operation == "hf_catalog" else "github"
    contract, raw, _, _ = configured(source)
    job = register_job(
        job_key="capture:" + operation,
        source=contract.mappings.first().source,
        purpose="catalog",
        operation=operation,
        mode="manual",
        definition={
            "version": 1,
            "scope": {
                "numeric_contract_id": str(contract.pk),
                "publishers": [{"account_id": "unused"}],
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 10, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(job.pk, "ready")
    claim = claim_job(job.pk)
    snapshot = CollectionObservation.objects.create(
        run_id=claim.run_id,
        source_identifier=str(raw["id"]),
        source_subject_kind="repository",
        observation_key="b" * 64,
        listing=raw,
        dimensions={"kind": "repository"} if source == "github" else {},
    )
    if queued:
        from core.collection_state import fenced_run

        with fenced_run(claim):
            enqueue_projection(claim, contract=contract, evidence_ids=[snapshot.pk])
    return job, claim, snapshot


def execute(operation, job, monkeypatch):
    """Use real acquisition entry points and shared drain; no provider work."""
    from core.github_catalog import execute_github_catalog
    from core.github_metadata_client import GitHubMetadataClient
    from core.model_history_collection import execute_model_history
    from core.model_inventory import execute_model_inventory

    monkeypatch.setattr("core.model_inventory._hf", lambda *args: 0)
    monkeypatch.setattr("core.github_catalog._publisher_inventory", lambda *args: [])
    monkeypatch.setattr(
        "httpx.Client.send", lambda *args, **kwargs: pytest.fail("HTTP forbidden")
    )
    budget = Budget(httpx.Client())
    if operation == "hf_catalog":
        return execute_model_inventory(job.pk, budget=budget)
    if operation == "github_catalog":
        return execute_github_catalog(job.pk, client=GitHubMetadataClient(budget))
    return execute_model_history(job.pk, budget=budget)


@pytest.mark.parametrize("operation", ["hf_catalog", "github_catalog", "model_history"])
def test_reclaimed_acquisition_cannot_acknowledge_committed_projection(
    operation, monkeypatch
):
    from core.source_metric_projection import project_evidence

    job, abandoned, snapshot = capture(operation)
    # Resume a persisted queue through the real acquisition entry point.
    CollectionRun.objects.filter(pk=abandoned.run_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    successor = []

    def pause_after_numeric_commit(*args, **kwargs):
        numeric = project_evidence(*args, **kwargs)
        if not successor:
            assert MetricValue.objects.exists()
            set_job_state(job.pk, "paused")
            set_job_state(job.pk, "ready")
            successor.append(claim_job(job.pk))
        return numeric

    monkeypatch.setattr(
        "core.source_metric_projection.project_evidence", pause_after_numeric_commit
    )
    with pytest.raises(StaleClaim):
        execute(operation, job, monkeypatch)

    queue = CollectionRun.objects.get(pk=abandoned.run_id).scopes.get(
        scope_kind="numeric_projection"
    )
    assert queue.envelopes == [{"observation_id": snapshot.pk}]
    assert queue.outcome == "pending" and queue.cursor is None
    committed_values = list(MetricValue.objects.order_by("pk").values())
    assert len(committed_values) == (2 if operation == "hf_catalog" else 3)
    numeric = CollectionRun.objects.get(job__purpose="metric")
    assert numeric.status == "success"

    recovered = drain_pending_projections(job.pk, origin_claim=successor[0])
    queue.refresh_from_db()
    assert recovered["acknowledged"] == recovered["reused_resources"] == 1
    assert recovered["written_values"] == 0 and recovered["pending"] is False
    assert queue.envelopes == [] and queue.outcome == "complete"
    assert list(MetricValue.objects.order_by("pk").values()) == committed_values
    assert numeric.observations.get().run_id == numeric.pk


@pytest.mark.parametrize("operation", ["hf_catalog", "github_catalog", "model_history"])
def test_acquisition_passes_its_held_claim_to_both_drains(operation, monkeypatch):
    from core.collection_state import fenced_run

    job, abandoned, _ = capture(operation, queued=False)
    CollectionRun.objects.filter(pk=abandoned.run_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    claims = []

    def inspect_drain(job_id, *, origin_claim=None, budget=None):
        assert origin_claim is not None
        assert origin_claim.job_id == job_id
        with fenced_run(origin_claim):
            pass
        claims.append(origin_claim)
        return {"pending": False}

    monkeypatch.setattr(
        "core.source_metric_projection.drain_pending_projections", inspect_drain
    )
    monkeypatch.setattr(
        "core.model_history_collection.drain_pending_projections", inspect_drain
    )
    run = execute(operation, job, monkeypatch)
    assert run.status == "success"
    assert len(claims) == 2 and claims[0] == claims[1]
    assert claims[0].lease_token != abandoned.lease_token


def test_stale_origin_stops_before_creating_a_metric_execution():
    job, stale, _ = capture()
    set_job_state(job.pk, "paused")
    set_job_state(job.pk, "ready")
    claim_job(job.pk)
    with pytest.raises(StaleClaim):
        drain_pending_projections(job.pk, origin_claim=stale)
    assert not CollectionJob.objects.filter(purpose="metric").exists()
    assert not MetricValue.objects.exists()


def test_standalone_saved_queue_recovery_requires_an_idle_origin():
    job, _, _ = capture()
    with pytest.raises(
        ValueError, match="active catalog projection requires origin claim"
    ):
        drain_pending_projections(job.pk)
    assert not CollectionJob.objects.filter(purpose="metric").exists()
    set_job_state(job.pk, "paused")
    recovered = drain_pending_projections(job.pk)
    assert recovered["acknowledged"] == 1 and not recovered["pending"]
    assert MetricValue.objects.count() == 2


def test_claim_from_another_job_cannot_authorize_queue_recovery():
    job, _, _ = capture()
    other = register_job(
        job_key="other-capture",
        source=job.source,
        purpose=job.purpose,
        operation=job.operation,
        mode=job.mode,
        definition=job.definition,
    )
    set_job_state(other.pk, "ready")
    claim = claim_job(other.pk)
    with pytest.raises(ValueError, match="projection origin claim mismatch"):
        drain_pending_projections(job.pk, origin_claim=claim)
    assert not CollectionJob.objects.filter(purpose="metric").exists()


def test_replaced_origin_stops_between_metric_registration_and_execution(monkeypatch):
    job, stale, _ = capture()

    def register_then_replace_origin(**kwargs):
        metric = register_job(**kwargs)
        set_job_state(job.pk, "paused")
        set_job_state(job.pk, "ready")
        claim_job(job.pk)
        return metric

    monkeypatch.setattr(
        "core.collection_jobs.register_job", register_then_replace_origin
    )
    with pytest.raises(StaleClaim):
        drain_pending_projections(job.pk, origin_claim=stale)
    assert not CollectionRun.objects.filter(job__purpose="metric").exists()
    assert not MetricValue.objects.exists()


def test_standalone_recovery_cannot_acknowledge_after_acquisition_starts(monkeypatch):
    from core.source_metric_projection import project_evidence

    job, _, snapshot = capture()
    set_job_state(job.pk, "paused")

    def start_acquisition_after_commit(*args, **kwargs):
        numeric = project_evidence(*args, **kwargs)
        set_job_state(job.pk, "ready")
        claim_job(job.pk)
        return numeric

    monkeypatch.setattr(
        "core.source_metric_projection.project_evidence", start_acquisition_after_commit
    )
    with pytest.raises(
        ValueError, match="active catalog projection requires origin claim"
    ):
        drain_pending_projections(job.pk)
    queue = CollectionRun.objects.get(job__purpose="catalog").scopes.get(
        scope_kind="numeric_projection"
    )
    assert queue.envelopes == [{"observation_id": snapshot.pk}]
    assert queue.outcome == "pending" and MetricValue.objects.count() == 2


def test_origin_locks_are_released_before_metric_registration_claim_and_projection(
    monkeypatch,
):
    from django.db import connection

    from core.source_metric_projection import project_evidence

    job, origin_claim, _ = capture()
    phases = []

    def probe_origin_locks(phase):
        # A separate PostgreSQL connection must acquire both origin rows NOWAIT.
        # Holding either across metric claim could invert campaign peer locks.
        probe = connection.copy(alias=connection.alias)
        try:
            with probe.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM collection_jobs WHERE id = %s FOR UPDATE NOWAIT",
                    [job.pk],
                )
                cursor.execute(
                    "SELECT id FROM collection_runs WHERE id = %s FOR UPDATE NOWAIT",
                    [origin_claim.run_id],
                )
        finally:
            probe.close()
        phases.append(phase)

    def register_metric(**kwargs):
        probe_origin_locks("registration")
        return register_job(**kwargs)

    def claim_metric(*args, **kwargs):
        probe_origin_locks("claim")
        return claim_job(*args, **kwargs)

    def project_metric(*args, **kwargs):
        probe_origin_locks("projection")
        return project_evidence(*args, **kwargs)

    monkeypatch.setattr("core.collection_jobs.register_job", register_metric)
    monkeypatch.setattr("core.source_metric_projection.claim_job", claim_metric)
    monkeypatch.setattr(
        "core.source_metric_projection.project_evidence", project_metric
    )
    result = drain_pending_projections(job.pk, origin_claim=origin_claim)
    assert result["acknowledged"] == 1
    assert phases == ["registration", "claim", "projection"]
