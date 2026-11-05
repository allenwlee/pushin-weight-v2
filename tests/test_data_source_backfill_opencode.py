"""One sealed history selection through the actual facade, adapter and writer."""
import json
from copy import deepcopy
from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.data_source_backfill_opencode import select_history_window
from tests.test_benchmark_opencode import SELECTED, configured, endpoint, read


@pytest.fixture
def isolated_target(monkeypatch):
    for name in ['core.management.commands.backfiller_data_source.validate_backfill_target',
                 'core.data_source_backfill_target.validate_backfill_target']:
        monkeypatch.setattr(name, lambda **_: {'schema_ready': True, 'database': 'local-test'})


def specification(contract):
    mapping = contract.mappings.get(source_id='opencode')
    return {'job_key': 'opencode-history', 'source': 'opencode', 'purpose': 'metric',
        'operation': 'collect_metrics', 'contract': str(contract.pk),
        'definition': {'version': 2, 'options': {}},
        'campaign': {'kind': 'backfiller-data-source-v1', 'key': 'opencode-test',
            'cohort_hash': 'a' * 64, 'role': 'history', 'phase': 'acquire',
            'max_invocations': 4, 'max_requests': 40, 'contract_partition': str(contract.pk)},
        'settings': {'owner_kind': 'source', 'schedule_kind': 'manual',
            'schedule_driver': 'manual', 'max_requests': 10, 'max_bytes': 2 * 1024**2,
            'max_seconds': 60, 'max_items': 100},
        'targets': [{'target_key': str(mapping.pk), 'subject_id': str(mapping.subject_id),
            'mapping_id': str(mapping.pk), 'native_identifier': mapping.external_identifier,
            'target_kind': 'metric_subject', 'target_role': 'history', 'resolution_state': 'resolved',
            'requested_start_at': '2026-10-06T00:00:00Z',
            'requested_end_at': '2026-10-07T00:00:00Z'}]}


def command(**options):
    output = StringIO()
    call_command('backfiller_data_source', stdout=output, **options)
    return json.loads(output.getvalue())


def test_selection_keeps_zero_and_preserves_stray_year_without_repair():
    data = endpoint(tokens=0)
    data['usage']['daily'].append({'date': '2025-10-06', 'tokens': 7})
    payload = read(data)
    original = deepcopy(payload)
    selected = select_history_window(payload, '2026-10-06', '2026-10-06')
    assert len(selected['rows']) == 1 and selected['rows'][0]['tokens'] == 0
    assert selected['endpoint_checks'][0]['dates'] == ['2026-10-06']
    assert payload == original
    assert any(row['date'] == '2025-10-06' for row in payload['rows'])


def test_missing_interval_is_explicitly_unavailable_with_no_synthetic_rows():
    selected = select_history_window(read(endpoint()), '2026-08-13', '2026-09-10')
    assert selected['status'] == 'partial'
    assert selected['rows'][0]['error_code'] == 'requested_history_unavailable'
    assert selected['rows'][0]['status'] == 'error'
    assert 'tokens' not in selected['rows'][0]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_real_command_captures_only_pinned_history_and_replays_without_http(monkeypatch, isolated_target):
    from core.benchmark_attribution import UseNotPermitted, enforce_source_collection
    from core.collection_capture import read_document
    from core.models import (
        CollectionJob,
        CollectionRequest,
        CollectionRun,
        DataSource,
        MetricValue,
    )

    monkeypatch.setattr('core.management.commands.backfiller_data_source.validate_backfill_target',
                        lambda **_: {'schema_ready': True, 'database': 'local-test'})
    contract = configured()
    source = DataSource.objects.get(pk='opencode')
    # Test condition: unresolved current policy. The owner-selected internal
    # review path must leave that evidence unchanged after collection/replay.
    unresolved = {'collection': {'status': 'unresolved'}, 'retention': {'status': 'unresolved'}}
    source.metadata = {**source.metadata, 'use_policy': unresolved}
    source.enabled = True
    source.save(update_fields=['metadata', 'enabled'])
    with pytest.raises(UseNotPermitted):
        enforce_source_collection(contract, 'opencode')
    spec = specification(contract)
    calls = []
    data = endpoint(tokens=0)
    def send(client, request, **options):
        assert str(request.url) == 'https://opencode.ai' + SELECTED[0]['endpoint_path']
        calls.append(request)
        return httpx.Response(200, json=data, request=request)
    monkeypatch.setattr(httpx.Client, 'send', send)
    preview = command(operation='register', specifications=json.dumps([spec]))
    assert preview['writes'] == 0 and not calls and not CollectionJob.objects.exists()
    command(operation='register', specifications=json.dumps([spec]), apply=True)
    job = CollectionJob.objects.get(job_key=spec['job_key'])
    assert job.instruction_version == 2 and job.campaign_id is not None
    command(operation='execute', job=str(job.pk), apply=True)
    assert len(calls) == 1
    run = CollectionRun.objects.get(job=job)
    assert run.status == 'success'
    values = list(MetricValue.objects.filter(observation__run=run).select_related('source_metric'))
    assert {value.source_metric.metric_key for value in values} == {'tokens', 'unique_users', 'sessions'}
    tokens = next(value for value in values if value.source_metric.metric_key == 'tokens')
    assert tokens.integer_value == 0
    assert tokens.window_start_at.isoformat() == '2026-10-06T00:00:00+00:00'
    assert tokens.window_end_at.isoformat() == '2026-10-07T00:00:00+00:00'
    requests = CollectionRequest.objects.filter(attempt__run=run)
    assert requests.count() == 1
    assert read_document(requests.get().archive)['usage']['daily'] == data['usage']['daily']
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('replay made HTTP request'))
    command(operation='replay', job=str(job.pk), apply=True)
    assert CollectionRun.objects.filter(job=job).count() == 1
    assert MetricValue.objects.filter(observation__run=run).count() == 3
    source.refresh_from_db()
    assert source.metadata['use_policy'] == unresolved
    with pytest.raises(UseNotPermitted):
        enforce_source_collection(contract, 'opencode')


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('change', ['naive', 'partial_day', 'ambiguous', 'identifier'])
def test_invalid_history_preview_fails_before_registration_or_http(monkeypatch, change, isolated_target):
    from core.models import CollectionJob

    monkeypatch.setattr('core.management.commands.backfiller_data_source.validate_backfill_target',
                        lambda **_: {'schema_ready': True, 'database': 'local-test'})
    spec = specification(configured())
    target = spec['targets'][0]
    if change == 'identifier':
        target['native_identifier'] = 'deepseek/generic-pro'
    else:
        target['requested_start_at'] = {'naive': '2026-10-06T00:00:00',
            'partial_day': '2026-10-06T01:00:00Z', 'ambiguous': '1006'}[change]
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('preview made HTTP request'))
    with pytest.raises(CommandError):
        command(operation='register', specifications=json.dumps([spec]))
    assert not CollectionJob.objects.exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_direct_typed_claim_rejects_partial_day_before_creating_attempt(isolated_target):
    from core.collection_jobs import register_job, set_job_state
    from core.collection_state import claim_job
    from core.models import CollectionAttempt, DataSource

    contract = configured()
    spec = specification(contract)
    spec['targets'][0]['requested_start_at'] = '2026-10-06T01:00:00Z'
    source = DataSource.objects.get(pk='opencode')
    source.enabled = True
    source.save(update_fields=['enabled'])
    job = register_job(job_key='direct-history', source=source, contract=contract,
        purpose='metric', operation='collect_metrics', mode='historical',
        definition=spec['definition'], settings=spec['settings'], targets=spec['targets'])
    set_job_state(job.pk, 'ready')
    with pytest.raises(ValueError, match='whole explicit UTC days'):
        claim_job(job.pk, typed=True)
    assert not CollectionAttempt.objects.exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_unavailable_history_retains_real_response_without_success_or_values(monkeypatch, isolated_target):
    from core.models import CollectionRequest, CollectionRun, DataSource, MetricValue

    spec = specification(configured())
    spec['targets'][0].update(requested_start_at='2026-08-13T00:00:00Z',
                              requested_end_at='2026-09-11T00:00:00Z')
    DataSource.objects.filter(pk='opencode').update(enabled=True)
    calls = []
    def send(client, request, **options):
        calls.append(request)
        return httpx.Response(200, json=endpoint(), request=request)
    monkeypatch.setattr(httpx.Client, 'send', send)
    registered = command(operation='register', specifications=json.dumps([spec]), apply=True)
    job_id = registered['cells'][0]['job_id']
    with pytest.raises(CommandError, match='Collection failed'):
        command(operation='execute', job=job_id, apply=True)
    run = CollectionRun.objects.get(job_id=job_id)
    assert run.status == 'failed'
    assert len(calls) == 1 and CollectionRequest.objects.get(attempt__run=run).archive_id
    assert run.observations.filter(status='error', error_code='requested_history_unavailable').exists()
    assert not MetricValue.objects.filter(observation__run=run).exists()
