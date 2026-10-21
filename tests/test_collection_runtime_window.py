"""Rolling publication bounds belong to a logical collection, including resume."""

from datetime import UTC, datetime, timedelta

import pytest

from core.collection_jobs import register_job, set_job_state
from core.collection_state import claim_job, finish_run
from core.model_history_collection import _runtime_publication_window
from core.models import CollectionCampaign, CollectionRun, DataSource

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("version", [1, 2])
def test_runtime_window_survives_resume_after_legacy_envelopes_are_cleared(
    monkeypatch, version
):
    now = datetime(2026, 10, 20, 11, tzinfo=UTC)
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    source = DataSource.objects.create(
        pk="openrouter",
        name="OpenRouter",
        source_type="model_adoption",
        enabled=True,
        adapter_key="openrouter-v1",
    )
    campaign = CollectionCampaign.objects.create(
        campaign_key="runtime-window",
        cohort_hash="a" * 64,
        policy_version="backfiller-data-source-v1",
        max_attempts=10,
        max_requests=20,
    )
    limits = {"requests": 1, "bytes": 10000, "seconds": 30, "items": 100}
    options = {
        "publication_window_policy": "rolling-completed-days-v1",
        "publication_recheck_days": 7,
    }
    extras = {}
    if version == 1:
        definition = {
            "version": 1,
            "scope": {**options, "cohort_hash": "a" * 64},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": limits,
        }
    else:
        definition = {"version": 2, "options": options}
        extras["settings"] = {
            "owner_kind": "source",
            "campaign_id": campaign.pk,
            "campaign_role": "history",
            "campaign_phase": "acquire",
            "schedule_kind": "manual",
            "schedule_driver": "manual",
            **{"max_" + name: value for name, value in limits.items()},
        }
    job = register_job(
        job_key="runtime-window",
        source=source,
        purpose="catalog",
        operation="model_history",
        mode="historical",
        definition=definition,
        **extras,
    )
    job = set_job_state(job.pk, "ready")
    first = claim_job(job.pk)
    view = _runtime_publication_window(first, job)
    expected_end = now.replace(hour=0)
    expected_start = expected_end - timedelta(days=7)
    assert view.scope["cutoff"] == expected_end.isoformat()
    assert view.scope["publication_start_at"] == expected_start.isoformat()
    assert "cutoff" not in job.scope  # per-run bounds do not mutate sealed instructions
    run = CollectionRun.objects.get(pk=first.run_id)
    scoped = run.scopes.get(scope_kind="publication_runtime")
    assert (
        scoped.requested_start_at == expected_start
        and scoped.requested_end_at == expected_end
    )
    finish_run(first, status="partial", request_count=0)
    scoped.envelopes = []
    scoped.save(update_fields=["envelopes"])
    monkeypatch.setattr("django.utils.timezone.now", lambda: now + timedelta(days=1))
    next_claim = claim_job(job.pk)
    resumed = _runtime_publication_window(next_claim, job)
    assert next_claim.run_id == first.run_id
    assert resumed.scope["cutoff"] == expected_end.isoformat()
    assert resumed.scope["publication_start_at"] == expected_start.isoformat()
    assert resumed.scope["acquisition_generation"] == str(first.run_id)
