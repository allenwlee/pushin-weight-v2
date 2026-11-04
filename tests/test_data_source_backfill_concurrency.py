"""Independent X and numeric jobs commit and resume in the same PostgreSQL DB."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from threading import Event

import httpx
import pytest
from django.db import close_old_connections

from core.collection_jobs import register_job, set_job_state
from core.collection_pages import append_page_receipt, page_receipts
from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
from core.data_source_backfill import execute_phase, register_campaign
from core.models import (
    CollectionRequest,
    CollectionRun,
    CollectionScopeRun,
    DataSource,
    MetricValue,
)
from tests.test_backfill_collection import ready_job
from tests.test_benchmark_opencode import configured, endpoint
from tests.test_data_source_backfill_opencode import specification

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_x_page_and_numeric_commit_with_independent_resume_and_budgets(monkeypatch):
    monkeypatch.setattr('core.data_source_backfill_target.validate_backfill_target', lambda **_: {})
    contract = configured()
    DataSource.objects.filter(pk='opencode').update(enabled=True)
    spec = specification(contract)
    spec['targets'][0].update(requested_start_at='2026-08-13T00:00:00Z', requested_end_at='2026-08-14T00:00:00Z')
    numeric = register_campaign([spec])[0]
    set_job_state(numeric.pk, 'ready')
    interrupted = claim_job(numeric.pk, typed=True)
    numeric_scope = checkpoint_scope(interrupted, scope_kind='metric_fetch', scope_key='source', typed=True,
        ownership={'contract_id': str(contract.pk)}, projection_contract=contract)
    finish_run(interrupted, typed=True, status='partial', request_count=0, physical_accounting_complete=True)

    old_x = ready_job()
    definition = deepcopy(old_x.definition)
    since = int(datetime(2026, 7, 17, tzinfo=UTC).timestamp())
    definition['scope'].update(since_epoch=since, until_epoch=since + 900)
    unit = definition['scope']['units'][0]
    unit.update(scope_key='B1:jul17')
    unit['ownership'].update(since_epoch=since, until_epoch=since + 900)
    x = register_job(job_key='july-concurrent', source=old_x.source, purpose='content',
        operation='x_backfill', mode='historical', definition=definition)
    set_job_state(x.pk, 'ready')
    first = claim_job(x.pk, manual_authorized=True, typed=True)
    scope = checkpoint_scope(first, scope_kind='x_query', scope_key=unit['scope_key'],
        ownership=unit['ownership'], typed=True, cursor='july-first')
    append_page_receipt(scope, {'post_ids': [], 'raw_count': 0, 'received_post_ids': []})
    finish_run(first, typed=True, status='partial', request_count=0, physical_accounting_complete=True)
    second = claim_job(x.pk, manual_authorized=True, typed=True, continue_from=first.run_id)
    locked, release = Event(), Event()

    def advance_x():
        close_old_connections()
        try:
            with fenced_run(second):
                locked.set()
                assert release.wait(15), 'numeric writer waited on unrelated X ownership'
                current = CollectionScopeRun.objects.get(run_id=second.run_id, scope_kind='x_query')
                append_page_receipt(current, {'post_ids': [], 'raw_count': 0, 'received_post_ids': []})
                checkpoint_scope(second, scope_kind='x_query', scope_key=unit['scope_key'],
                    ownership=unit['ownership'], typed=True, cursor='july-second')
            finish_run(second, typed=True, status='success', request_count=0, physical_accounting_complete=True)
        finally:
            close_old_connections()

    data = endpoint(tokens=0, updated='2026-08-15T12:00:00Z')
    data['usage']['daily'] = [{'date': '2026-08-13', 'tokens': 0, 'uniqueUsers': 2, 'sessions': 3}]
    monkeypatch.setattr(httpx.Client, 'send', lambda _self, request, **_: httpx.Response(200, json=data, request=request))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(advance_x)
        try:
            assert locked.wait(5)
            result = execute_phase(numeric.pk)
            assert result.status == 'success'
            assert MetricValue.objects.filter(observation__run=result).count() == 3
        finally:
            release.set()
        pending.result(timeout=10)
    assert CollectionRequest.objects.filter(attempt__run__job=numeric).count() == 1
    assert CollectionRequest.objects.filter(attempt__run__job=x).count() == 0
    assert CollectionRun.objects.get(pk=first.run_id).request_count == 0
    assert CollectionScopeRun.objects.get(run_id=first.run_id, scope_kind='x_query').cursor == 'july-first'
    resumed = CollectionScopeRun.objects.get(run_id=second.run_id, scope_kind='x_query')
    assert resumed.cursor == 'july-second' and len(page_receipts(resumed)) == 2
    assert result.pk == interrupted.run_id
    assert result.attempts.count() == 2
    assert result.scopes.get(scope_kind='metric_fetch').pk == numeric_scope.pk
