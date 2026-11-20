"""Saved provider admission follows the existing scheduled harvest boundary."""

import pytest
from django.test import override_settings

from monitor.cycle import CycleRunner
from tests.test_post_enrichment_queue import _cfg

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.mark.parametrize("pipeline", ["two_role", "compressed8_pulse_v1"])
def test_scheduled_recovery_runs_without_pulse_or_provider_calls(monkeypatch, pipeline):
    from core import collection_matching
    from monitor import enrichment_worker

    calls = []
    monkeypatch.setattr(enrichment_worker, "process_enrichment_batch", lambda *args, **kwargs: {"fixture": "done"})
    monkeypatch.setattr(collection_matching, "drain_pending_publication_scopes", lambda **kwargs: calls.append(kwargs) or {"processed": 1})
    cfg = _cfg()
    cfg.llm.classifier_pipeline = pipeline
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled", dry_run=False)
    with override_settings(PRODUCT_RELEASE_BACKGROUND_ENABLED=False):
        result = runner._run_post_fetch([])
    recovery = result["provider_admission_recovery"]
    assert recovery["processed"] == 1 and recovery["provider_calls"] == 0
    assert recovery["queries"] == 0 and recovery["elapsed_ms"] >= 0
    assert calls == [{"max_jobs": 1, "max_seconds": 5}]


@pytest.mark.parametrize("kind,dry_run,kwargs", [
    ("scheduled", True, {}), ("manual", False, {}),
    ("scheduled", False, {"repair_manifest": {}}),
    ("scheduled", False, {"source_collection_job_id": "fixture"}),
])
def test_recovery_does_not_run_on_dry_or_special_paths(monkeypatch, kind, dry_run, kwargs):
    from core import collection_matching
    from monitor import enrichment_worker

    monkeypatch.setattr(collection_matching, "drain_pending_publication_scopes", lambda **kw: pytest.fail("unexpected recovery"))
    monkeypatch.setattr(enrichment_worker, "process_enrichment_batch", lambda *args, **kw: {})
    runner = CycleRunner(cfg=_cfg(), cycle_kind=kind, dry_run=dry_run)
    monkeypatch.setattr(runner, "_process_enrichment_claim_batch", lambda *args, **kw: {})
    with override_settings(PRODUCT_RELEASE_BACKGROUND_ENABLED=False):
        assert "provider_admission_recovery" not in runner._run_post_fetch([], **kwargs)


def test_recovery_error_is_reported_without_interrupting_post_fetch(monkeypatch):
    from core import collection_matching
    from monitor import enrichment_worker

    def fail(**kwargs):
        raise RuntimeError("saved admission failure")

    monkeypatch.setattr(collection_matching, "drain_pending_publication_scopes", fail)
    monkeypatch.setattr(enrichment_worker, "process_enrichment_batch", lambda *args, **kwargs: {"fixture": "done"})
    runner = CycleRunner(cfg=_cfg(), cycle_kind="scheduled", dry_run=False)
    with override_settings(PRODUCT_RELEASE_BACKGROUND_ENABLED=False):
        result = runner._run_post_fetch([])
    assert result["fixture"] == "done" and result["provider_admission_recovery"]["status"] == "error"
    assert result["provider_admission_recovery"]["provider_calls"] == 0


def test_scheduled_harvest_recovers_saved_one_off_collector_without_provider_calls(monkeypatch):
    import core.collection_matching as matching
    from core.model_history_collection import execute_model_history
    from core.models import CollectionJobTarget, CollectionScopeRun
    from monitor import enrichment_worker
    from tests.test_data_source_history_ingestion import (
        publication_scope,
        register,
        transport,
    )

    provider, _, scope = publication_scope("openrouter")
    original = matching.register_pending_publication_targets

    def fail(**kwargs):
        raise ValueError("temporary admission failure")

    monkeypatch.setattr(matching, "register_pending_publication_targets", fail)
    job = register(provider, scope)
    budget, requests = transport("openrouter", model="elsewhere/model")
    run = execute_model_history(job.pk, budget=budget, key="fixture")
    assert run.status == "success" and requests
    saved_requests = len(requests)
    admission = CollectionScopeRun.objects.get(run=run, scope_kind="pending_publication_admission")
    assert admission.outcome == "pending"
    # The first failed attempt deliberately backs off; the next scheduled
    # harvest runs after that short retry interval.
    from django.utils import timezone

    CollectionScopeRun.objects.filter(pk=admission.pk).update(retry_at=timezone.now())
    monkeypatch.setattr(matching, "register_pending_publication_targets", original)
    monkeypatch.setattr(enrichment_worker, "process_enrichment_batch", lambda *args, **kwargs: {})
    runner = CycleRunner(cfg=_cfg(), cycle_kind="scheduled", dry_run=False)
    with override_settings(PRODUCT_RELEASE_BACKGROUND_ENABLED=False):
        result = runner._run_post_fetch([])
    admission.refresh_from_db()
    assert result["provider_admission_recovery"]["processed"] == 1
    assert result["provider_admission_recovery"]["queries"] > 0
    assert result["provider_admission_recovery"]["affected_rows"] > 0
    assert result["provider_admission_recovery"]["provider_calls"] == 0
    assert admission.outcome == "complete"
    assert CollectionJobTarget.objects.filter(evidence_observation=admission.resource_observation,
           native_identifier="elsewhere/model", resolution_state="unresolved").exists()
    assert len(requests) == saved_requests
    with override_settings(PRODUCT_RELEASE_BACKGROUND_ENABLED=False):
        assert runner._run_post_fetch([])["provider_admission_recovery"]["processed"] == 0
    assert len(requests) == saved_requests
