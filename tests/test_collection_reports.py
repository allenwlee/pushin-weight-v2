import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.collection_capture import archive_legacy
from core.collection_reports import campaign_status, job_status
from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.models import CollectionRun
from tests.test_collection_jobs import ready
from tests.test_github_catalog import configured

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_report_uses_attempt_and_success_clocks_and_locates_failed_scopes():
    job, _ = configured()
    first = claim_job(job.pk, typed=True)
    finish_run(first, status="success", typed=True,
               physical_accounting_complete=True, request_count=0)
    second = claim_job(job.pk, typed=True)
    owner = job.scope["publishers"][0]
    checkpoint_scope(
        second, scope_kind="publisher", scope_key=owner["native_id"],
        ownership=owner, outcome="history_unavailable", typed=True,
    )
    finish_run(
        second, status="failed", error_code="history_unavailable", typed=True,
        physical_accounting_complete=True, request_count=0,
    )
    report = job_status(job.pk)
    assert report["last_attempt"]["run_id"] == str(second.run_id)
    assert report["last_success"]["run_id"] == str(first.run_id)
    assert report["last_attempt"]["error_code"] == "history_unavailable"
    failed = next(scope for scope in report["scopes"] if scope["kind"] == "publisher")
    assert failed["key"] == owner["native_id"]
    assert failed["outcome"] == "history_unavailable"
    assert failed["enumeration_complete"] is False
    out = StringIO()
    call_command("collection_status", job=str(job.pk), stdout=out)
    assert json.loads(out.getvalue()) == report


def test_historical_report_coverage_and_redaction_use_retained_archive():
    job = ready(mode="manual")
    document = {
        "request_params": {}, "source_metadata": {}, "raw_payload": None,
        "invocations": [],
        "report": {"coverage": [{"outcome": "history_unavailable",
                                  "reason": "outside_top50", "token": "never-display"}]},
    }
    # Model an already completed historical run; do not manufacture execution.
    run = CollectionRun.objects.create(
        job=job, ingestion_key="a" * 64, status="failed",
        completed_at=timezone.now(), legacy_archive=archive_legacy(document),
    )
    job.last_attempt = run
    job.save(update_fields=["last_attempt"])
    report = job_status(job.pk)
    assert report["coverage"][0] == {
        "outcome": "history_unavailable", "reason": "outside_top50",
        "token": "[redacted]",
    }
    assert run.attempts.count() == 0
    out = StringIO()
    call_command("collection_status", job=str(job.pk), stdout=out)
    assert json.loads(out.getvalue()) == report
    assert "never-display" not in out.getvalue()


def test_expired_lease_is_distinct_from_successful_empty_enumeration():
    job, _ = configured()
    claim = claim_job(job.pk, typed=True)
    run = CollectionRun.objects.get(pk=claim.run_id)
    assert (
        job_status(job.pk, now=run.lease_expires_at + timedelta(seconds=1))["health"]
        == "expired_lease"
    )
    finish_run(claim, status="success", typed=True,
               physical_accounting_complete=True, request_count=0)
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
