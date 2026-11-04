"""Command-to-service proof for database-only campaigns, with no live HTTP."""
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.account_identity import upsert_account
from core.collection_capture import archive_legacy
from core.collection_jobs import set_job_state
from core.collection_state import (
    BusyJob,
    StaleClaim,
    checkpoint_scope,
    claim_job,
    finish_run,
)
from core.models import (
    CollectionAttempt,
    CollectionJob,
    CollectionRun,
    CollectionScopeRun,
)
from tests.test_collection_jobs import job as base_job

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def isolated_campaign_target(monkeypatch):
    """Campaign behavior uses local fixtures; target checks have their own tests."""
    monkeypatch.setattr(
        'core.management.commands.backfiller_data_source.validate_backfill_target',
        lambda **_: {'schema_ready': True, 'database': 'local-test'},
    )
    monkeypatch.setattr('core.data_source_backfill_target.validate_backfill_target',
                       lambda **_: {'schema_ready': True, 'database': 'local-test'})


def specification():
    original = base_job()
    publisher = upsert_account(source="github", external_identifier="42",
                               handle="publisher", account_kind="organization")
    return {
        'job_key': 'campaign:github:history', 'source': 'github',
        'operation': 'github_catalog', 'purpose': 'catalog', 'contract': None,
        'definition': {**original.definition, 'scope': {"publishers": [{
            "account_key": str(publisher.pk), "native_id": "42",
            "login": "publisher", "account_kind": "organization",
        }]}, 'campaign': {
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


def campaign_archive(**usage):
    return archive_legacy({
        "request_params": {}, "source_metadata": {}, "raw_payload": None,
        "invocations": [], "report": {"campaign_usage": usage},
    })


def test_imported_campaign_reservation_is_preserved_without_guessing_attempts():
    from core.data_source_backfill import campaign_usage, project_legacy_campaigns

    job = legacy_campaign_job()
    now = timezone.now()
    run = CollectionRun.objects.create(
        job=job, ingestion_key="a" * 64, status="success",
        completed_at=now, request_count=10,
        legacy_archive=campaign_archive(invocations=2, reserved_requests=30,
                                        recorded_requests=10),
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
    CollectionScopeRun.objects.create(
        run=next_run, scope_kind="catalog_execution", scope_key="execution",
        phase="typed-github-catalog-v1",
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
    from core.data_source_backfill import campaign_usage, project_legacy_campaigns
    from tests.test_hf_catalog_retirement import denied_retirement_columns

    job = legacy_campaign_job()
    now = timezone.now()
    run = CollectionRun.objects.create(
        job=job, ingestion_key="d" * 64, status="success", completed_at=now,
        request_count=7,
        legacy_archive=campaign_archive(invocations=1, reserved_requests=13,
                                        recorded_requests=7),
    )
    CollectionAttempt.objects.create(
        run=run, attempt_key="archived-campaign-1", ordinal=1,
        imported_at=now, outcome="success",
    )
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
        completed_at=timezone.now(),
        legacy_archive=campaign_archive(invocations=1, reserved_requests=8,
                                        recorded_requests=0),
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


def test_campaign_report_is_paged_and_usage_is_shared(monkeypatch):
    from copy import deepcopy

    from core import data_source_backfill as service

    first = specification()
    second = deepcopy(first)
    second['job_key'] += ':second'
    service.register_campaign([first, second])
    calls = []
    monkeypatch.setattr(service, 'campaign_usage', lambda job: (
        calls.append(job.pk) or {'invocations': 0, 'reserved_requests': 0, 'recorded_requests': 0}))
    page = service.report_campaign(campaign_key='campaign', limit=1)
    assert page['job_count'] == 1 and page['total_job_count'] == 2
    assert page['next_after'] == first['job_key']
    next_page = service.report_campaign(campaign_key='campaign', limit=1,
                                        after_job_key=page['next_after'])
    assert next_page['cells'][0]['job_key'] == second['job_key']
    assert next_page['next_after'] is None
    calls.clear()
    assert service.report_campaign(campaign_key='campaign', limit=2)['job_count'] == 2
    assert len(calls) == 1


def test_command_reports_use_readonly_transactions(monkeypatch):
    from django.db import connection

    from core import data_source_backfill as service

    registered()
    original = service.report_campaign
    seen = []

    def inspect(**kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only')")
            seen.append(cursor.fetchone()[0])
        return original(**kwargs)

    monkeypatch.setattr(service, 'report_campaign', inspect)
    assert command()['applied'] is False
    assert seen == ['on']


def test_campaign_report_does_not_parse_full_last_attempt_payload(monkeypatch):
    from core.data_source_backfill import report_campaign

    job = registered()
    set_job_state(job.pk, 'ready')
    claim = claim_job(job.pk, invocation_id='summary', manual_authorized=True, typed=True)
    finish_run(claim, status='success', typed=True, request_count=0,
               physical_accounting_complete=True)
    monkeypatch.setattr('core.collection_reports.run_report_document',
                        lambda *_: pytest.fail('summary parsed full run report'))
    cell = report_campaign(campaign_key='campaign')['cells'][0]
    assert cell['last_attempt']['run_id'] == str(claim.run_id)
    assert cell['run_report_included'] is False


def test_legacy_usage_streams_archives_instead_of_caching_all_bodies(monkeypatch):
    from django.db.models import QuerySet

    from core.data_source_backfill import campaign_usage

    job = legacy_campaign_job()
    CollectionRun.objects.create(job=job, ingestion_key='b' * 64, status='success',
        completed_at=timezone.now(), request_count=2,
        legacy_archive=campaign_archive(invocations=1, reserved_requests=3, recorded_requests=2))
    original = QuerySet.__iter__

    def forbid_archive_cache(query):
        if query.model is CollectionRun and query.query.select_related:
            pytest.fail('campaign usage cached archive-bearing run rows')
        return original(query)

    monkeypatch.setattr(QuerySet, '__iter__', forbid_archive_cache)
    assert campaign_usage(job) == {'invocations': 1, 'reserved_requests': 3, 'recorded_requests': 2}


def test_legacy_usage_refuses_oversize_archive_before_reading_body(monkeypatch):
    from core.data_source_backfill import campaign_usage
    job = legacy_campaign_job()
    archive = archive_legacy({'report': {'padding': 'x' * (16 * 1024 * 1024)}})
    CollectionRun.objects.create(job=job, ingestion_key='d' * 64,
        status='success', completed_at=timezone.now(), legacy_archive=archive)
    monkeypatch.setattr('core.collection_capture.read_document',
                        lambda *_: pytest.fail('oversize archive body was read'))
    with pytest.raises(ValueError, match='archive exceeds report byte limit'):
        campaign_usage(job)


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
        claim = claim_job(current.pk, typed=True)
        run = CollectionRun.objects.get(pk=claim.run_id)
        scopes = list(run.scopes.filter(scope_kind='publisher_repos').values_list('cursor', flat=True))
        seen.append(scopes)
        owner = current.scope['publishers'][0]
        checkpoint_scope(claim, scope_kind='publisher_repos', scope_key=owner['native_id'],
                         ownership=owner, cursor='page2', outcome='retryable_failure', typed=True)
        return finish_run(claim, status='partial', typed=True,
                          physical_accounting_complete=False, request_count=0)
    monkeypatch.setattr(data_source_backfill, 'execute_due_job', execute)
    monkeypatch.chdir(tmp_path)
    first = command(operation='execute', job=str(job.pk), apply=True)
    assert first['cells'][0]['last_attempt']['status'] == 'partial'
    resumed = command(operation='resume', job=str(job.pk), apply=True)
    scope = next(row for row in resumed['cells'][0]['scopes'] if row['kind'] == 'publisher_repos')
    assert scope['has_continuation'] and scope['outcome'] == 'retryable_failure'
    assert seen == [[], ['page2']]
    assert CollectionRun.objects.filter(job=job).count() == 1
    with pytest.raises(ValueError, match='limit'):
        data_source_backfill.execute_phase(job.pk)


def test_crashed_reservation_survives_reclaim_and_pause_fences_response():
    from core.data_source_backfill import campaign_usage

    job = registered()
    set_job_state(job.pk, 'ready')
    first = claim_job(job.pk, typed=True)
    with pytest.raises(BusyJob):
        claim_job(job.pk, typed=True)
    CollectionRun.objects.filter(pk=first.run_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    second = claim_job(job.pk, typed=True)
    assert campaign_usage(job)['reserved_requests'] == 40
    set_job_state(job.pk, 'paused')
    with pytest.raises(StaleClaim):
        checkpoint_scope(second, scope_key='late', ownership={}, typed=True)
    set_job_state(job.pk, 'ready')
    with pytest.raises(ValueError, match='limit'):
        claim_job(job.pk, typed=True)


def test_successful_reclaim_keeps_previous_ambiguous_request_reservation():
    from core.data_source_backfill import campaign_usage

    job = registered()
    set_job_state(job.pk, 'ready')
    first = claim_job(job.pk, typed=True)
    CollectionRun.objects.filter(pk=first.run_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1))
    successor = claim_job(job.pk, typed=True)
    # The recovered invocation can account for its own three physical requests.
    # It cannot establish how many requests the crashed invocation dispatched.
    finish_run(successor, status='success', request_count=3, typed=True,
               physical_accounting_complete=True)
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
    claim = claim_job(first.pk, typed=True)
    # Complete physical accounting is an explicit adapter promise; absent that
    # promise all unused reservation remains charged, including across crashes.
    finish_run(claim, status='success', request_count=3, typed=True,
               physical_accounting_complete=True)
    assert campaign_usage(second) == {'invocations': 1, 'reserved_requests': 3, 'recorded_requests': 3}
    run = CollectionRun.objects.get(pk=claim.run_id)
    assert not hasattr(run, 'report') and run.legacy_archive_id is None
    assert campaign_usage(second) == {'invocations': 1, 'reserved_requests': 3, 'recorded_requests': 3}
    set_job_state(second.pk, 'ready')
    second_claim = claim_job(second.pk, typed=True)
    assert campaign_usage(first)['reserved_requests'] == 23
    finish_run(second_claim, status='partial', typed=True,
               physical_accounting_complete=False, request_count=0)
    with pytest.raises(ValueError, match='limit'):
        claim_job(second.pk, typed=True)


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
    first = claim_job(job.pk, typed=True)
    checkpoint_scope(first, scope_kind='metric_fetch', scope_key='source',
                     ownership={'contract_id': str(job.contract_id)},
                     projection_contract=job.contract, cursor='second', raw_count=3, typed=True)
    previous = finish_run(first, status='partial', request_count=1,
                          typed=True, physical_accounting_complete=False)
    second = claim_job(job.pk, typed=True)
    assert second.run_id != first.run_id
    resumed = CollectionRun.objects.get(pk=second.run_id)
    assert resumed.scopes.get(scope_kind='metric_fetch').cursor == 'second'
    assert resumed.scopes.filter(scope_kind='metric_execution').count() == 1
    assert resumed.continuation_of_id == first.run_id
    assert previous.scopes.get(scope_kind='metric_fetch').cursor == 'second'
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
            return claim_job(job.pk, typed=True)
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
    first_claim = claim_job(first.pk, typed=True)
    finish_run(first_claim, status='partial', request_count=1,
               typed=True, physical_accounting_complete=False)
    set_job_state(second.pk, 'ready')
    with pytest.raises(ValueError, match='request limit'):
        claim_job(second.pk, typed=True)
    assert not second.runs.exists()


def revision_budget_jobs(requests):
    from copy import deepcopy

    from core.collection_jobs import register_job
    from core.models import DataSource

    spec = specification()
    spec['definition']['campaign'].update(key='0813:revision-a', max_invocations=40, max_requests=1000)
    spec['definition']['budgets']['requests'] = requests
    second = deepcopy(spec)
    second['definition']['campaign']['key'] = '0813:revision-b'
    jobs = []
    # Isolate the locked claim guard from the separate narrow cohort validator.
    # These two immutable owners stand for the two already-observed revisions.
    for index, value in enumerate((spec, second)):
        jobs.append(register_job(job_key=f'0813:revision-{index}:guard',
            source=DataSource.objects.get(pk=value['source']), purpose=value['purpose'],
            operation=value['operation'], mode='historical', definition=value['definition']))
    return jobs


@pytest.mark.parametrize('limit', ['requests', 'attempts'])
def test_0813_contract_revisions_share_exhausted_budget(limit):
    from core.data_source_backfill import campaign_usage

    jobs = revision_budget_jobs(100 if limit == 'requests' else 1)
    for _ in range(10 if limit == 'requests' else 40):
        set_job_state(jobs[0].pk, 'ready')
        claim = claim_job(jobs[0].pk, typed=True)
        finish_run(claim, status='partial', typed=True, request_count=0,
                   error_code='fixture_interrupted', physical_accounting_complete=False)
    assert campaign_usage(jobs[1]) == {'invocations': 0, 'reserved_requests': 0, 'recorded_requests': 0}
    set_job_state(jobs[1].pk, 'ready')
    before = CollectionAttempt.objects.count()
    with pytest.raises(ValueError, match='campaign invocation/request limit exhausted'):
        claim_job(jobs[1].pk, typed=True)
    assert CollectionAttempt.objects.count() == before


def test_0813_revisions_serialize_the_last_request_reservation():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    from core.data_source_backfill import campaign_budget_usage

    jobs = revision_budget_jobs(100)
    for _ in range(9):
        set_job_state(jobs[0].pk, 'ready')
        claim = claim_job(jobs[0].pk, typed=True)
        finish_run(claim, status='partial', typed=True, request_count=0,
                   error_code='fixture_interrupted', physical_accounting_complete=False)
    for job in jobs:
        set_job_state(job.pk, 'ready')
    ready = Barrier(2)

    def reserve(job_id):
        close_old_connections()
        try:
            ready.wait(timeout=10)
            try:
                claim_job(job_id, typed=True)
                return 'claimed'
            except ValueError as exc:
                assert str(exc) == 'campaign invocation/request limit exhausted'
                return 'limited'
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, [job.pk for job in jobs]))
    assert sorted(outcomes) == ['claimed', 'limited']
    assert campaign_budget_usage(jobs[0])['reserved_requests'] == 1000
