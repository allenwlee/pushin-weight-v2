"""Command-to-service proof for database-only campaigns, with no live HTTP."""
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.collection_jobs import set_job_state
from core.collection_state import (
    BusyJob,
    StaleClaim,
    checkpoint_scope,
    claim_job,
    finish_run,
)
from core.models import CollectionAttempt, CollectionJob, CollectionRun
from tests.test_collection_jobs import job as base_job

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def specification():
    original = base_job()
    return {
        'job_key': 'campaign:github:history', 'source': 'github',
        'operation': 'github_catalog', 'purpose': 'catalog', 'contract': None,
        'definition': {**original.definition, 'campaign': {
            'kind': 'backfiller-data-source-v1', 'key': 'campaign', 'cohort_hash': 'a' * 64, 'role': 'history',
            'phase': 'acquire', 'max_invocations': 2, 'max_requests': 40,
            'contract_partition': None,
        }},
    }


def registered():
    from core.data_source_backfill import register_campaign
    return register_campaign([specification()])[0]


def legacy_campaign_job():
    from core.collection_jobs import validate_definition

    spec = specification()
    definition = spec["definition"]
    return CollectionJob.objects.create(
        job_key="legacy:campaign:github:history", source_id="github",
        purpose="catalog", operation="github_catalog", mode="historical",
        definition=definition,
        definition_sha256=validate_definition(
            source_id="github", purpose="catalog", operation="github_catalog",
            mode="historical", contract_id=None, definition=definition,
        ),
    )


def test_imported_campaign_reservation_is_preserved_without_guessing_attempts():
    from core.data_source_backfill import campaign_usage, project_legacy_campaigns

    job = legacy_campaign_job()
    now = timezone.now()
    run = CollectionRun.objects.create(
        job=job, ingestion_key="a" * 64, status="success",
        completed_at=now, request_count=10,
        report={"campaign_usage": {
            "invocations": 2, "reserved_requests": 30,
            "recorded_requests": 10,
        }},
    )
    for ordinal in (1, 2):
        CollectionAttempt.objects.create(
            run=run, attempt_key=f"legacy-campaign-{ordinal}", ordinal=ordinal,
            imported_at=now, outcome="success",
        )
    assert campaign_usage(job) == {
        "invocations": 2, "reserved_requests": 30, "recorded_requests": 10,
    }
    assert project_legacy_campaigns() == {
        "campaigns": 1, "jobs": 1, "legacy_runs": 1,
        "imported_attempts": 2, "imported_reserved_requests": 30,
    }
    job.refresh_from_db()
    assert job.campaign.imported_reserved_requests == 30
    assert job.campaign_role == "history" and job.campaign_phase == "acquire"
    assert campaign_usage(job) == {
        "invocations": 2, "reserved_requests": 30, "recorded_requests": 10,
    }
    assert project_legacy_campaigns(verify_only=True)["imported_reserved_requests"] == 30
    assert project_legacy_campaigns()["imported_reserved_requests"] == 30
    assert not CollectionAttempt.objects.filter(
        run=run, reserved_requests__isnull=False,
    ).exists()
    set_job_state(job.pk, "ready")
    with pytest.raises(ValueError, match="limit"):
        claim_job(job.pk)

    next_run = CollectionRun.objects.create(
        job=job, ingestion_key="b" * 64, status="success",
        completed_at=now, request_count=3,
    )
    CollectionAttempt.objects.create(
        run=next_run, attempt_key="typed-campaign-1", ordinal=1,
        reserved_requests=5, actual_requests=3, outcome="success",
    )
    assert campaign_usage(job) == {
        "invocations": 3, "reserved_requests": 35, "recorded_requests": 13,
    }
    assert project_legacy_campaigns(verify_only=True)["imported_reserved_requests"] == 30


@pytest.mark.django_db(transaction=True)
def test_legacy_campaign_import_reads_archived_reservations_after_json_retirement():
    from core.collection_storage_migration import archive_legacy_batch
    from core.data_source_backfill import campaign_usage, project_legacy_campaigns
    from tests.test_hf_catalog_retirement import denied_retirement_columns

    job = legacy_campaign_job()
    now = timezone.now()
    run = CollectionRun.objects.create(
        job=job, ingestion_key="d" * 64, status="success", completed_at=now,
        request_count=7,
        report={"campaign_usage": {
            "invocations": 1, "reserved_requests": 13, "recorded_requests": 7,
        }},
    )
    CollectionAttempt.objects.create(
        run=run, attempt_key="archived-campaign-1", ordinal=1,
        imported_at=now, outcome="success",
    )
    assert archive_legacy_batch("collection_runs").archived == 1
    CollectionRun.objects.filter(pk=run.pk).update(report={})

    with denied_retirement_columns():
        assert campaign_usage(job) == {
            "invocations": 1, "reserved_requests": 13, "recorded_requests": 7,
        }
        assert project_legacy_campaigns()["imported_reserved_requests"] == 13
        job.refresh_from_db()
        assert job.campaign.imported_reserved_requests == 13
        assert project_legacy_campaigns(verify_only=True)["legacy_runs"] == 1


def test_imported_campaign_rejects_receipt_attempt_disagreement():
    from core.data_source_backfill import project_legacy_campaigns

    job = legacy_campaign_job()
    CollectionRun.objects.create(
        job=job, ingestion_key="c" * 64, status="success",
        completed_at=timezone.now(), report={"campaign_usage": {
            "invocations": 1, "reserved_requests": 8, "recorded_requests": 0,
        }},
    )
    with pytest.raises(ValueError, match="aggregate does not match"):
        project_legacy_campaigns()
    job.refresh_from_db()
    assert job.campaign_id is None


def command(**kwargs):
    out = StringIO()
    call_command('backfiller_data_source', stdout=out, **kwargs)
    return json.loads(out.getvalue())


def test_default_inspect_and_registration_preview_are_nonmutating(monkeypatch):
    spec = specification()
    before = list(CollectionJob.objects.values())
    monkeypatch.setattr('httpx.Client.send', lambda *a, **k: pytest.fail('HTTP forbidden'))
    assert command()['applied'] is False
    preview = command(operation='register', specifications=json.dumps([spec]))
    assert preview['applied'] is False
    assert list(CollectionJob.objects.values()) == before
    assert not CollectionRun.objects.exists()


def test_registration_is_paused_idempotent_and_rejects_changed_partition():
    from core.data_source_backfill import register_campaign
    spec = specification()
    first = register_campaign([spec])[0]
    assert first.state == 'paused'
    assert first.campaign.campaign_key == 'campaign'
    assert first.campaign.max_attempts == 2
    assert register_campaign([spec])[0].pk == first.pk
    spec['definition']['campaign']['cohort_hash'] = 'b' * 64
    with pytest.raises(ValueError, match='immutable|cohort'):
        register_campaign([spec])


def test_command_resume_reconstructs_committed_scope_without_files(monkeypatch, tmp_path):
    from core import data_source_backfill
    job = registered()
    seen = []
    def execute(current, decision, budget):
        claim = claim_job(current.pk)
        run = CollectionRun.objects.get(pk=claim.run_id)
        scopes = list(run.scopes.values_list('cursor', flat=True))
        seen.append(scopes)
        checkpoint_scope(claim, scope_key='repo', ownership={}, cursor='page2', outcome='pending')
        return finish_run(claim, status='partial', report={'coverage': [{'outcome': 'retryable_failure'}]})
    monkeypatch.setattr(data_source_backfill, 'execute_due_job', execute)
    monkeypatch.chdir(tmp_path)
    first = command(operation='execute', job=str(job.pk), apply=True)
    assert first['cells'][0]['last_attempt']['status'] == 'partial'
    assert command(operation='resume', job=str(job.pk), apply=True)['cells'][0]['scopes'][0]['has_continuation']
    assert seen == [[], ['page2']]
    assert CollectionRun.objects.filter(job=job).count() == 1
    with pytest.raises(ValueError, match='limit'):
        data_source_backfill.execute_phase(job.pk)


def test_crashed_reservation_survives_reclaim_and_pause_fences_response():
    from core.data_source_backfill import campaign_usage

    job = registered()
    set_job_state(job.pk, 'ready')
    first = claim_job(job.pk)
    with pytest.raises(BusyJob):
        claim_job(job.pk)
    CollectionRun.objects.filter(pk=first.run_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    second = claim_job(job.pk)
    assert campaign_usage(job)['reserved_requests'] == 40
    set_job_state(job.pk, 'paused')
    with pytest.raises(StaleClaim):
        checkpoint_scope(second, scope_key='late', ownership={})
    set_job_state(job.pk, 'ready')
    with pytest.raises(ValueError, match='limit'):
        claim_job(job.pk)


def test_successful_reclaim_keeps_previous_ambiguous_request_reservation():
    from core.data_source_backfill import campaign_usage

    job = registered()
    set_job_state(job.pk, 'ready')
    first = claim_job(job.pk)
    CollectionRun.objects.filter(pk=first.run_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1))
    successor = claim_job(job.pk)
    # The recovered invocation can account for its own three physical requests.
    # It cannot establish how many requests the crashed invocation dispatched.
    finish_run(successor, status='success', request_count=3,
               report={'physical_accounting_complete': True})
    assert campaign_usage(job) == {
        'invocations': 2, 'reserved_requests': 23, 'recorded_requests': 3}


def test_replay_rejects_acquisition_phase_and_never_falls_back_to_acquisition():
    from core.data_source_backfill import execute_phase
    job = registered()
    with pytest.raises(ValueError, match='replay.*phase mismatch'):
        execute_phase(job.pk, replay=True)
    job.refresh_from_db()
    assert job.state == 'paused'
    assert not job.runs.exists()


def test_campaign_ceiling_is_shared_across_source_jobs_and_accounting_can_release():
    from core.data_source_backfill import campaign_usage, register_campaign
    first_spec = specification()
    second_spec = {**first_spec, 'job_key': 'campaign:github:second'}
    first, second = register_campaign([first_spec, second_spec])
    set_job_state(first.pk, 'ready')
    claim = claim_job(first.pk)
    # Complete physical accounting is an explicit adapter promise; absent that
    # promise all unused reservation remains charged, including across crashes.
    finish_run(claim, status='success', request_count=3,
               report={'physical_accounting_complete': True})
    assert campaign_usage(second) == {'invocations': 1, 'reserved_requests': 3, 'recorded_requests': 3}
    run = CollectionRun.objects.get(pk=claim.run_id)
    run.report = {}
    run.save(update_fields=['report'])
    assert campaign_usage(second) == {'invocations': 1, 'reserved_requests': 3, 'recorded_requests': 3}
    set_job_state(second.pk, 'ready')
    second_claim = claim_job(second.pk)
    assert campaign_usage(first)['reserved_requests'] == 23
    finish_run(second_claim, status='partial')
    with pytest.raises(ValueError, match='limit'):
        claim_job(second.pk)


def test_terminal_metric_partial_copies_only_checkpoint_into_new_attempt(settings):
    from core.data_source_backfill import register_campaign
    from tests.test_collection_scheduling import scheduled
    original = scheduled(settings)
    spec = specification()
    spec.update(source='hf', purpose='metric', operation='collect_metrics',
                contract=str(original.contract_id))
    spec['definition']['campaign']['contract_partition'] = str(original.contract_id)
    job = register_campaign([spec])[0]
    set_job_state(job.pk, 'ready')
    first = claim_job(job.pk)
    checkpoint_scope(first, scope_key='batch', ownership={}, cursor='second', raw_count=3)
    previous = finish_run(first, status='partial', request_count=1)
    second = claim_job(job.pk)
    assert second.run_id != first.run_id
    resumed = CollectionRun.objects.get(pk=second.run_id)
    assert resumed.scopes.get().cursor == 'second'
    assert resumed.continuation_of_id == first.run_id
    assert previous.scopes.get().cursor == 'second'
    previous.refresh_from_db()
    assert previous.status == 'partial' and previous.request_count == 1


@pytest.mark.django_db(transaction=True)
def test_two_campaign_workers_cannot_own_one_phase():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections
    job = registered()
    set_job_state(job.pk, 'ready')
    def claim():
        close_old_connections()
        try:
            return claim_job(job.pk)
        except BusyJob:
            return None
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert len([result for result in results if result is not None]) == 1
    run = CollectionRun.objects.get(job=job)
    assert run.attempts.count() == 1


def test_real_command_dispatches_existing_github_adapter_to_saved_evidence(monkeypatch):
    import httpx

    from core.data_source_backfill import register_campaign
    from tests.test_github_catalog import configured, responses
    original, repo = configured()
    spec = specification()
    spec['definition'] = {**spec['definition'], 'scope': original.definition['scope']}
    job = register_campaign([spec])[0]
    calls = []
    factory = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **_: factory(
        transport=httpx.MockTransport(responses(repo, calls))))
    result = command(operation='execute', job=str(job.pk), apply=True)
    job.refresh_from_db()
    assert result['cells'][0]['last_attempt']['status'] == 'success'
    assert job.last_success.observations.count() > 4
    assert job.last_success.request_count > 0
    assert calls


def test_ambiguous_reservation_blocks_other_source_phase():
    from core.data_source_backfill import register_campaign
    first_spec = specification()
    first_spec['definition']['campaign']['max_requests'] = 20
    second_spec = {**first_spec, 'job_key': 'campaign:second'}
    first, second = register_campaign([first_spec, second_spec])
    set_job_state(first.pk, 'ready')
    first_claim = claim_job(first.pk)
    finish_run(first_claim, status='partial', request_count=1)
    set_job_state(second.pk, 'ready')
    with pytest.raises(ValueError, match='request limit'):
        claim_job(second.pk)
    assert not second.runs.exists()
