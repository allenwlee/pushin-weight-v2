"""Rehearse source-reading compatibility in the permanent DB's isolated schema."""
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.data_source_backfill_upgrade import (
    EXPAND,
    legacy_projection_models,
    project_batch,
)
from core.migrations._rg6_retirement_v1 import FIELDS
from core.models import CollectionRun, CollectionScopeRun

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ('core', '0183_rg6_typed_statistics_identity')


@pytest.mark.parametrize('migration_rehearsal_schema', [BASE], indirect=True)
def test_0183_additive_upgrade_projects_original_invocation_and_cursor(migration_rehearsal_schema):
    from core.collection_capture import archive_legacy, read_document, run_report_document
    from core.models import CollectionObservation
    from core.collection_pages import page_receipts
    from core.collection_storage_migration import (
        archive_legacy_batch,
        stale_legacy_archive_count,
    )
    from monitor.backfill_collection import execute_job
    from tests.test_backfill_collection import ready_job

    # Write actual 0183 records before the additive migrations. No current ORM
    # run/receipt fields or fabricated migration ledger are used for this seed.
    historical = MigrationExecutor(connection).loader.project_state([BASE]).apps
    OldRun = historical.get_model('core', 'CollectionRun')
    OldScope = historical.get_model('core', 'CollectionScopeRun')
    job = ready_job()
    at = timezone.now() - timedelta(hours=1)
    report = {'response_bytes': 0, 'usage': {'llm_requests': 7}}
    run = OldRun.objects.create(job_id=job.pk, ingestion_key='1' * 64, status='partial',
        started_at=at, completed_at=at + timedelta(minutes=1),
        invocations=[{'invocation_id': 'original-operator', 'started_at': at.isoformat()}],
        report=report)
    old_scope = OldScope.objects.create(run_id=run.pk, scope_kind='x_query', scope_key='B1:aug09',
        ownership=job.scope['units'][0]['ownership'], cursor='saved-cursor',
        cursor_history=['saved-cursor'], outcome='pending',
        envelopes=[{'post_ids': [], 'collection_drained': False, 'raw_count': 0}])
    job.last_attempt_id = run.pk
    job.save(update_fields=['last_attempt'])
    MigrationExecutor(connection).migrate([EXPAND])
    original_fields = tuple(CollectionRun._meta.fields)
    copied = project_batch('invocations')
    assert copied.scanned == 1
    project_batch('invocations', verify_only=True)
    assert CollectionRun.objects.get(pk=run.pk).attempts.get().source_invocation_id == 'original-operator'
    project_batch('cursors')
    # An old writer advances while storage is additive. The delta sweep must
    # preserve that checkpoint too; no writer was paused to make the copy easy.
    old_scope.cursor = 'late-cursor'
    old_scope.cursor_history.append('late-cursor')
    old_scope.save(update_fields=['cursor', 'cursor_history'])
    project_batch('cursors')
    project_batch('cursors', verify_only=True)
    scope = CollectionScopeRun.objects.get(run_id=run.pk)
    assert scope.recorded_cursors == ['saved-cursor', 'late-cursor']
    project_batch('bounds')
    project_batch('targets')
    scope.refresh_from_db()
    assert scope.job_target_id is not None
    assert int(scope.requested_start_at.timestamp()) == job.scope['since_epoch']
    assert int(scope.requested_end_at.timestamp()) == job.scope['until_epoch']
    assert tuple(CollectionRun._meta.fields) == original_fields
    from core.models import CollectionRequest
    from monitor.backfill_retry import RetryControl
    current_run = CollectionRun.objects.get(pk=run.pk)
    request = CollectionRequest.objects.create(attempt=current_run.attempts.get(), scope_run_id=old_scope.pk,
        ordinal=1, http_method='GET', endpoint_url='https://api.twitterapi.io/twitter/tweet/advanced_search',
        request_category='x_backfill_staging', transport_outcome='received', http_status=200,
        response_bytes=270, accounting_complete=True, received_at=at)
    staging_metadata = {'raw_count': 3, 'returned_ids': ['kept', None, ''],
                        'body_sha256': 'a' * 64, 'body_lost': True}
    report.update(response_bytes=270, staging_retry=RetryControl().snapshot(),
        staging_responses={str(request.pk): staging_metadata}, prefetch_accounted_requests=[str(request.pk)])
    run.report, run.request_count = report, 1
    run.save(update_fields=['report', 'request_count'])
    review_evidence = {'reason': 'Previously recorded consent', 'at': at.isoformat()}
    with legacy_projection_models():
        review = CollectionObservation.objects.create(run_id=run.pk,
            source_subject_kind='aggregate', source_identifier='historical-request',
            observation_kind='x_staging_retry_approval', observation_key='e' * 64,
            observed_at=at, processing_outcome='approved',
            legacy_archive=archive_legacy(review_evidence))
    for table in FIELDS:
        while archive_legacy_batch(table, batch_size=100).more_unarchived:
            pass
    project_batch('x_runtime')
    project_batch('x_runtime', verify_only=True)
    assert CollectionScopeRun.objects.get(run_id=run.pk, scope_kind='x_model_usage').raw_count == 7
    request.refresh_from_db()
    from core.collection_staging import staging_receipt
    assert staging_receipt(request) == staging_metadata
    assert request.archive_id is None and request.selection_accounted is True
    assert CollectionRun.objects.get(pk=run.pk).physical_bytes_received == 270
    # Empty obsolete observation JSON must not replace typed review evidence.
    review.refresh_from_db()
    assert read_document(review.legacy_archive) == review_evidence
    assert project_batch('pages').updated == 1
    assert project_batch('pages', verify_only=True).updated == 0
    # Independent parity must inspect receipt contents, not just child counts.
    child = CollectionScopeRun.objects.get(parent_scope_id=scope.pk, scope_kind='x_page_checkpoint')
    CollectionScopeRun.objects.filter(pk=child.pk).update(raw_count=1)
    with pytest.raises(ValueError, match='differ from their saved checkpoint'):
        project_batch('pages', verify_only=True)
    CollectionScopeRun.objects.filter(pk=child.pk).update(raw_count=0)
    assert project_batch('pages', verify_only=True).updated == 0
    assert all(stale_legacy_archive_count(table) == 0 for table in FIELDS)
    MigrationExecutor(connection).migrate([('core', '0200_merge_rg6_enrichment_budget_contract')])
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('pushinweight.rg6_retirement_ready','0201',false)")
    try:
        MigrationExecutor(connection).migrate([('core', '0221_affiliation_trigger_column_permissions')])
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET pushinweight.rg6_retirement_ready")
    current = CollectionRun.objects.get(pk=run.pk)
    assert run_report_document(current) == report
    assert execute_job(job.pk, read_only=True)['report'] == report
    scope = CollectionScopeRun.objects.get(pk=old_scope.pk)
    assert scope.recorded_cursors == ['saved-cursor', 'late-cursor']
    assert page_receipts(scope) == [{'post_ids': [], 'collection_drained': False,
                                   'raw_count': 0, 'reason': None}]


def test_projection_context_restores_model_fields_on_failure(monkeypatch):
    class PhysicalColumns:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): pass
        def fetchall(self):
            return [(table, name, 'jsonb') for table, names in FIELDS.items() for name in names]
    monkeypatch.setattr(connection, 'cursor', PhysicalColumns)
    with pytest.raises(RuntimeError, match='injected interruption'), legacy_projection_models():
        assert hasattr(CollectionRun, 'report')
        raise RuntimeError('injected interruption')
    assert not hasattr(CollectionRun, 'report')
    assert not set(FIELDS['collection_scope_runs']).intersection(f.name for f in CollectionScopeRun._meta.fields)
    with legacy_projection_models():
        assert hasattr(CollectionRun, 'report')


def test_projection_refuses_current_database_without_retiring_columns():
    with pytest.raises(ValueError, match='all thirteen'), legacy_projection_models():
        pytest.fail('current schema admitted as legacy source')
