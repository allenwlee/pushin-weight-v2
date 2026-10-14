import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from core.collection_reports import campaign_status, job_status
from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.models import CollectionRun
from tests.test_collection_jobs import ready

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_report_uses_attempt_and_success_clocks_and_locates_failed_scopes():
    job = ready(mode="manual")
    first = claim_job(job.pk)
    finish_run(first, status="success")
    second = claim_job(job.pk)
    checkpoint_scope(
        second, scope_key="missing", ownership={}, outcome="history_unavailable"
    )
    finish_run(
        second,
        status="failed",
        report={
            "coverage": [{"outcome": "history_unavailable", "reason": "outside_top50"}]
        },
    )
    # Simulate old unguarded JSON evidence, which reporting must also redact.
    run = CollectionRun.objects.get(pk=second.run_id)
    run.report["coverage"][0]["token"] = "never-display"
    run.save()
    report = job_status(job.pk)
    assert report["last_attempt"]["run_id"] == str(second.run_id)
    assert report["last_success"]["run_id"] == str(first.run_id)
    assert report["coverage"][0]["outcome"] == "history_unavailable"
    assert report["coverage"][0]["token"] == "[redacted]"
    assert report["scopes"][0]["key"] == "missing"
    out = StringIO()
    call_command("collection_status", job=str(job.pk), stdout=out)
    assert json.loads(out.getvalue()) == report
    assert "never-display" not in out.getvalue()


def test_expired_lease_is_distinct_from_successful_empty_enumeration():
    job = ready(mode="manual")
    claim = claim_job(job.pk)
    run = CollectionRun.objects.get(pk=claim.run_id)
    assert (
        job_status(job.pk, now=run.lease_expires_at + timedelta(seconds=1))["health"]
        == "expired_lease"
    )
    finish_run(claim, status="success")
    report = job_status(job.pk)
    assert report["last_success"]["selected_count"] == 0
    assert report["active_claim"] is None
    assert report["all_requested_history_available"] is False


def test_campaign_keeps_jobs_without_optional_role_key():
    job = ready()
    # Persist a valid immutable definition through a new registration.
    from core.collection_jobs import register_job

    definition = {
        **job.definition,
        "scope": {**job.definition["scope"], "cohort_hash": "f" * 64},
    }
    register_job(
        job_key="campaign",
        source=job.source,
        purpose=job.purpose,
        operation=job.operation,
        mode=job.mode,
        definition=definition,
    )
    report = campaign_status("f" * 64)
    assert report["job_count"] == 1 and not report["complete_public_history_claimed"]
