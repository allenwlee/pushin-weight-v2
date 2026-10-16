"""Database-backed campaign facade over the shared collection services.

Definitions are reviewed inputs, never local checkpoints. Adapters retain ownership
of their actual run, lease, evidence and checkpoints. Replay uses the shared saved-evidence projector and can never fall through to acquisition.
"""
from __future__ import annotations

from django.db import transaction

from core.collection_jobs import (
    register_job,
    set_job_state,
    validate_definition,
    validate_job,
)
from core.collection_reports import job_status
from core.collection_scheduling import execute_due_job
from core.measurement_taxonomy import require
from core.model_history_cohort import HISTORY_SOURCES
from core.models import (
    CollectionJob,
    CollectionRun,
    DataSource,
    MetricCollectionContract,
)


def validate_campaign(definition, *, contract_id):
    campaign = definition.get('campaign')
    require(isinstance(campaign, dict) and campaign.get('kind') == 'backfiller-data-source-v1',
            'typed campaign instructions required')
    require(isinstance(campaign.get('key'), str) and 0 < len(campaign['key']) <= 128,
            'campaign key required')
    cohort = campaign.get('cohort_hash')
    require(isinstance(cohort, str) and len(cohort) == 64
            and all(c in '0123456789abcdef' for c in cohort), 'cohort hash required')
    require(campaign.get('role') in {'inventory', 'history', 'projection'}, 'invalid campaign role')
    require(campaign.get('phase') in {'acquire', 'replay'}, 'invalid campaign phase')
    require(campaign.get('contract_partition') == (str(contract_id) if contract_id else None),
            'immutable contract partition mismatch')
    for name in ('max_invocations', 'max_requests'):
        require(type(campaign.get(name)) is int and 0 < campaign[name] <= 1000000,
                f'invalid campaign {name}')
    require(campaign['max_requests'] >= definition['budgets']['requests'],
            'campaign request limit below invocation budget')
    scope_hash = definition['scope'].get('cohort_hash')
    require(scope_hash in (None, cohort), 'frozen scope/cohort mismatch')
    return campaign


def prepare_campaign(specifications):
    """Resolve reviewed source/contract records without creating anything."""
    require(isinstance(specifications, list) and 0 < len(specifications) <= 1000,
            'bounded source job specifications required')
    prepared, identities, keys = [], set(), set()
    for spec in specifications:
        require(isinstance(spec, dict), 'source job specification required')
        require(spec.get('source') in HISTORY_SOURCES, 'unsupported campaign source')
        require(spec.get('job_key') not in keys, 'duplicate job key')
        keys.add(spec.get('job_key'))
        source = DataSource.objects.get(pk=spec['source'])
        contract = (MetricCollectionContract.objects.get(pk=spec['contract'])
                    if spec.get('contract') else None)
        definition = spec['definition']
        validate_definition(source_id=source.pk, purpose=spec['purpose'],
                            operation=spec['operation'], mode='historical',
                            contract_id=contract.pk if contract else None, definition=definition)
        campaign = validate_campaign(definition, contract_id=contract.pk if contract else None)
        require((campaign['role'] != 'inventory' or spec['operation'] != 'model_history'),
                'inventory cannot own deep history')
        identities.add((campaign['key'], campaign['cohort_hash'],
                        campaign['max_invocations'], campaign['max_requests']))
        prepared.append({'job_key': spec['job_key'], 'source': source, 'contract': contract,
                             'purpose': spec['purpose'], 'operation': spec['operation'],
                             'mode': 'historical', 'definition': definition})
    require(len(identities) == 1, 'mixed campaign keys or cohorts')
    key, cohort, maximum_invocations, maximum_requests = next(iter(identities))
    for existing in CollectionJob.objects.filter(definition__campaign__key=key):
        validate_job(existing)
        require((existing.definition['campaign']['cohort_hash'],
                 existing.definition['campaign']['max_invocations'],
                 existing.definition['campaign']['max_requests'])
                == (cohort, maximum_invocations, maximum_requests),
                'immutable campaign cohort changed')
    return prepared


@transaction.atomic
def register_campaign(specifications):
    """Register paused source phases atomically; identical re-registration is safe."""
    # Existing source rows serialize concurrent initial registrations as well as
    # later additions, when no campaign job exists yet to lock.
    list(DataSource.objects.select_for_update().filter(pk__in=HISTORY_SOURCES).order_by('pk'))
    return [register_job(**spec) for spec in prepare_campaign(specifications)]


def campaign_jobs(*, campaign_key=None, job_id=None):
    jobs = CollectionJob.objects.filter(
        definition__campaign__kind='backfiller-data-source-v1')
    if campaign_key:
        jobs = jobs.filter(definition__campaign__key=campaign_key)
    if job_id:
        jobs = jobs.filter(pk=job_id)
    return jobs.select_related('source', 'contract').order_by('created_at', 'job_key')


def report_campaign(*, campaign_key=None, job_id=None):
    cells = []
    for job in campaign_jobs(campaign_key=campaign_key, job_id=job_id):
        validate_job(job)
        campaign = validate_campaign(job.definition, contract_id=job.contract_id)
        cells.append({**job_status(job.pk), 'campaign': campaign,
                      'usage': campaign_usage(job)})
    require(not job_id or len(cells) == 1, 'campaign job not found')
    return {'schema_version': 1, 'job_count': len(cells), 'cells': cells,
            'complete_public_history_claimed': False}


def campaign_usage(job):
    """Reservations bound crash exposure; request_count remains actual usage."""
    usage = {'invocations': 0, 'reserved_requests': 0, 'recorded_requests': 0}
    for run in CollectionRun.objects.filter(
            job__definition__campaign__kind='backfiller-data-source-v1',
            job__definition__campaign__key=job.definition['campaign']['key']):
        reservation = run.report.get('campaign_usage', {})
        usage['invocations'] += reservation.get('invocations', 0)
        usage['reserved_requests'] += reservation.get('reserved_requests', 0)
        usage['recorded_requests'] += run.request_count
    return usage


def execute_phase(job_id, *, budget=None, executor=None, replay=False, projector=None):
    """Run one explicitly selected phase; adapter acquires the shared fenced claim.

    Acquisition executors follow execute_due_job(job, decision, budget). Projectors
    follow projector(job_id), acquire the same claim and consume saved evidence only.
    No invocation here takes normal scheduling authority or alters X jobs.
    """
    job = campaign_jobs(job_id=job_id).get()
    validate_job(job)
    campaign = validate_campaign(job.definition, contract_id=job.contract_id)
    require(replay == (campaign['phase'] == 'replay'), 'campaign replay phase mismatch')
    if replay and projector is None:
        from core.source_metric_projection import replay_saved_evidence

        projector = replay_saved_evidence
    require(executor is not None or replay or job.operation != 'collect_metrics',
            'direct metric acquisition hook is unavailable')
    usage = campaign_usage(job)
    require(usage['invocations'] < campaign['max_invocations']
            and usage['reserved_requests'] + job.definition['budgets']['requests'] <= campaign['max_requests'],
            'campaign invocation/request limit exhausted')
    # Activation is explicit. claim_job rechecks state, limits and lease under lock.
    if job.state == 'paused':
        set_job_state(job.pk, 'ready')
    if replay:
        return projector(job.pk)
    if budget is None:
        import httpx

        from core.collection_budgets import invocation_budget
        limits = job.definition['budgets']
        with httpx.Client(trust_env=False) as client:
            budget = invocation_budget(client, requests=limits['requests'],
                                       seconds=limits['seconds'], max_bytes=limits['bytes'])
            return (executor or execute_due_job)(job, {'slot': None}, budget)
    return (executor or execute_due_job)(job, {'slot': None}, budget)
