"""Old retry consents retain their exact unknown request and review evidence."""
from types import SimpleNamespace

import pytest
from django.db import transaction
from django.utils import timezone

from core.collection_capture import archive_legacy, begin_request, finish_request
from core.collection_staging import adopt_retry_reviews, has_retry_review
from core.collection_state import checkpoint_scope, claim_job
from core.models import (
    CollectionObservation,
    CollectionRequest,
    CollectionRun,
    CollectionScopeRun,
)
from monitor.backfill_prefetch import _endpoint, _request_identity
from monitor.backfill_staging import StagingPrefetcher
from tests.test_backfill_staging import staged_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def interrupted(monkeypatch, *, reviewed):
    job = staged_job(monkeypatch, 1)
    claim = claim_job(job.pk, invocation_id='interrupted', manual_authorized=True, typed=True)
    unit = job.scope['units'][0]
    checkpoint_scope(claim, scope_kind='x_query', scope_key=unit['scope_key'],
                     ownership=unit['ownership'], outcome='pending', typed=True)
    scope = CollectionScopeRun.objects.get(run_id=claim.run_id, scope_kind='x_query')
    run = CollectionRun.objects.get(pk=claim.run_id)
    request = begin_request(run.attempts.get(), scope, endpoint_url=_endpoint(scope),
        request_category='x_backfill_staging', request_config=_request_identity(scope))
    with transaction.atomic():
        request = finish_request(request, outcome='unknown', error_code='operator_reconciled_interruption')
    approval = {'reason': 'Earlier operator confirmed the process had stopped', 'at': timezone.now().isoformat()}
    run.legacy_archive = archive_legacy({'report': {'staging_unknown_retries': {
        str(request.pk): approval} if reviewed else {}}})
    run.save(update_fields=['legacy_archive'])
    prefetch = StagingPrefetcher.__new__(StagingPrefetcher)
    prefetch.claim = SimpleNamespace(job_id=job.pk)
    prefetch.metrics = {'lost_responses': 0}
    return job, run, scope, request, prefetch


def test_unknown_request_without_recorded_consent_still_requires_reconciliation(monkeypatch):
    job, run, scope, request, prefetch = interrupted(monkeypatch, reviewed=False)
    assert adopt_retry_reviews(run) == 0
    assert has_retry_review(request, job.pk) is False
    with pytest.raises(ValueError, match='outcome unknown'):
        prefetch._pending(scope)
    assert not CollectionObservation.objects.filter(observation_kind='x_staging_retry_approval').exists()


def test_recorded_review_adopts_once_without_changing_request_or_run(monkeypatch):
    job, run, scope, request, prefetch = interrupted(monkeypatch, reviewed=True)
    original = CollectionRequest.objects.filter(pk=request.pk).values().get()
    before_run = CollectionRun.objects.filter(pk=run.pk).values().get()
    assert adopt_retry_reviews(run) == 1
    assert adopt_retry_reviews(run, verify_only=True) == 0
    assert adopt_retry_reviews(run) == 0
    assert has_retry_review(request, job.pk) is True
    assert prefetch._pending(scope) == (None, str(request.pk))
    assert CollectionRequest.objects.filter(pk=request.pk).values().get() == original
    assert CollectionRun.objects.filter(pk=run.pk).values().get() == before_run
    assert request.response_bytes is None and request.accounting_complete is False
    assert CollectionObservation.objects.filter(observation_kind='x_staging_retry_approval').count() == 1
    # A second interrupted send has no inherited consent, even on the same query.
    begin_request(run.attempts.get(), scope, endpoint_url=_endpoint(scope),
        request_category='x_backfill_staging', request_config=_request_identity(scope))
    with pytest.raises(ValueError, match='outcome unknown'):
        prefetch._pending(scope)


def test_invalid_recorded_consent_cannot_create_a_review(monkeypatch):
    _, run, _, request, _ = interrupted(monkeypatch, reviewed=False)
    run.legacy_archive = archive_legacy({'report': {'staging_unknown_retries': {
        str(request.pk): {'reason': '', 'at': timezone.now().isoformat()}}}})
    run.save(update_fields=['legacy_archive'])
    with pytest.raises(ValueError, match='invalid historical retry review'):
        adopt_retry_reviews(run)
    assert not CollectionObservation.objects.filter(observation_kind='x_staging_retry_approval').exists()
