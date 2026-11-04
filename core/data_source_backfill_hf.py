"""Bounded archive discovery retained as requests and typed page checkpoints."""
import re
from datetime import UTC, timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx
from django.db.models import Sum

from core.benchmark_metric_store import aware_instant
from core.collection_capture import (
    RequestCapture,
    archive_legacy,
    link_request,
    read_document,
)
from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
from core.hf_metadata_client import HFMetadataClient
from core.measurement_taxonomy import digest, require
from core.models import CollectionJob, CollectionObservation, CollectionRequest
from scripts.benchmark_download_collector.sources import SourceError

DATASET = 'cfahlgren1/hub-stats'
ROLE = 'backfill_archive_discovery'
KIND = 'hf_archive_catalog'


class ArchiveCaptureClient:
    """Retain range replies, including redirects, before selected-row import.

    Expiring public redirect signatures are omitted from saved URLs. The host,
    resource path, requested byte range and immutable scope revision remain.
    """
    def __init__(self, client, claim, scope, max_bytes):
        self.client, self.capture, self.scope = client, RequestCapture(claim), scope
        self.max_bytes = max_bytes

    def send(self, request, **kwargs):
        parsed = urlsplit(str(request.url))
        endpoint = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
        receipt = self.capture.start(self.scope, endpoint,
            request_config=request.headers['range'], request_category='hf_archive_range')
        try:
            response = self.client.send(request, **kwargs)
        except httpx.HTTPError as exc:
            self.capture.failed(receipt)
            raise SourceError('request_error') from exc
        return _RangeReply(response, self.capture, receipt, self.max_bytes)


class _RangeReply:
    def __init__(self, response, capture, receipt, max_bytes):
        self.response, self.capture, self.receipt = response, capture, receipt
        self.max_bytes, self.body, self.received, self.complete = max_bytes, bytearray(), 0, False
        self.closed = False

    def __getattr__(self, name):
        return getattr(self.response, name)

    def iter_bytes(self):
        try:
            # Preserve delivered partial chunks if the next read times out;
            # re-chunking would hide a buffered tail from request accounting.
            for block in self.response.iter_bytes():
                self.received += len(block)
                if len(self.body) + len(block) <= self.max_bytes:
                    self.body.extend(block)
                yield block
        except httpx.HTTPError as exc:
            raise SourceError('request_error') from exc
        self.complete = True

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.capture.received(self.receipt,
                body=bytes(self.body) if self.complete and len(self.body) == self.received else None,
                status=self.response.status_code, response_bytes=self.received,
                error_code=None if self.complete or self.response.is_redirect else 'range_body_incomplete',
                media_type='application/octet-stream')
        finally:
            self.response.close()


def validate_discovery(job):
    scope = job.scope
    require((job.source_id, job.purpose, job.operation, job.mode) == (
        'hf', 'catalog', 'model_history', 'historical')
        and scope.get('role') == ROLE and scope.get('dataset_id') == DATASET
        and type(scope.get('max_pages')) is int and 1 <= scope['max_pages'] <= 40,
        'invalid HF archive discovery instructions')
    start, end = aware_instant(scope['global_start_at']), aware_instant(scope['cutoff'])
    require(start.utcoffset() == end.utcoffset() == timedelta(0)
            and start.time().isoformat() == end.time().isoformat() == '00:00:00'
            and 0 < (end - start).days <= 366, 'invalid HF archive discovery window')


def validate_discovery_scope(job, key, ownership):
    validate_discovery(job)
    require(key == 'catalog' and ownership == {'dataset_id': DATASET},
            'HF archive catalog differs from frozen dataset')


def validate_archive_only(job):
    from core.models import MetricCollectionContract, Product

    scope = job.scope
    require(job.source_id == 'hf' and job.operation == 'model_history'
            and job.mode == 'historical' and scope.get('backfill_archive_only') is True
            and scope.get('numeric_contract_id') and len(scope.get('models', [])) == 1,
            'bounded HF archive-only profile required')
    model = scope['models'][0]
    product = Product.objects.get(product_key=model['product_key'])
    creation = model['creation']
    require(creation.get('source') == 'hf' and creation.get('native_identifier') == product.repo_id
            and product.created_at == aware_instant(creation['at']),
            'HF archive creation identity changed')
    contract = MetricCollectionContract.objects.get(pk=scope['numeric_contract_id'])
    mappings = list(contract.mappings.filter(source_id='hf', purpose='metric').select_related('subject'))
    require(len(mappings) == 1 and mappings[0].subject.product_id == product.product_key
            and mappings[0].external_identifier == product.repo_id,
            'HF archive metric contract differs from product')
    if creation.get('hf_archive_row_id') is not None:
        require(re.fullmatch('[0-9a-f]{24}', creation['hf_archive_row_id'])
                and mappings[0].identifier_metadata.get('archive_row_key') == creation['hf_archive_row_id'],
                'HF archive row identity differs from reviewed contract')
    archive = scope.get('hf_archive', {})
    require(archive.get('dataset_id') == DATASET and archive.get('archive_publisher') == 'cfahlgren1',
            'unreviewed HF archive dataset')
    revisions = archive.get('revisions')
    require(isinstance(revisions, list) and 0 < len(revisions) <= job.budgets['items'],
            'bounded immutable HF archive revisions required')
    require(len({row['snapshot_date'] for row in revisions}) == len(revisions)
            and all(re.fullmatch('[0-9a-f]{40}', row['id'])
                and aware_instant(row['date']).astimezone(UTC).date().isoformat() == row['snapshot_date']
                and aware_instant(scope['global_start_at']).date().isoformat() <= row['snapshot_date']
                < aware_instant(scope['cutoff']).date().isoformat()
                for row in revisions), 'HF archive revision dates changed')


def _saved_pages(job):
    pages = []
    rows = CollectionObservation.objects.filter(run__job=job, observation_kind=KIND).select_related(
        'legacy_archive').defer('legacy_archive__body').order_by('resource_key')
    for observation in rows[:42]:
        require(observation.resource_key == f'{len(pages):04d}' and observation.legacy_archive.byte_count <= 2 * 1024**2,
                'HF archive catalog checkpoint is ambiguous or oversized')
        page = read_document(observation.legacy_archive)
        require(digest(page) == observation.payload_sha256, 'HF archive catalog checkpoint changed')
        pages.append(page)
    require(len(pages) <= job.scope['max_pages'] + 1, 'HF archive catalog page cap')
    return pages


def execute_discovery(job, decision, budget):
    """Resume from committed pages at one immutable dataset head; no local files."""
    validate_discovery(job)
    claim = claim_job(job.pk, typed=True)
    client = HFMetadataClient(budget.client, max_requests=budget.remaining,
        max_seconds=max(0.001, budget.deadline - budget.clock()),
        max_bytes=min(2 * 1024**2, budget.max_bytes - budget.total_bytes_read),
        max_total_bytes=budget.max_bytes - budget.total_bytes_read,
        clock=budget.clock, sleep=budget.sleep)
    scope = checkpoint_scope(claim, scope_kind=KIND, scope_key='catalog', typed=True,
        ownership={'dataset_id': DATASET})
    client.capture, client.collection_scope = RequestCapture(claim), scope
    try:
        # A lost acknowledgement is a reconciliation task, not permission to
        # issue an identical request and silently forget the uncertain send.
        require(not CollectionRequest.objects.filter(attempt__run__job=job,
            transport_outcome__in=['pending', 'unknown']).exists(),
            'HF archive request requires reconciliation')
        pages = _saved_pages(job)
        while not pages or not pages[-1]['complete']:
            require(len(pages) <= job.scope['max_pages'], 'HF archive catalog page cap')
            if not pages:
                result = client._get('/datasets/' + DATASET)
                require(result.outcome == 'ok' and isinstance(result.payload, dict)
                        and re.fullmatch('[0-9a-f]{40}', result.payload.get('sha', '')),
                        'HF archive head unavailable')
                page = {'head': result.payload['sha'], 'rows': [], 'cursor': None, 'complete': False}
            else:
                result = client.history_page(DATASET, pages[0]['head'], 'commits',
                    pages[-1]['cursor'], repo_type='dataset')
                require(result.outcome == 'ok', 'HF archive catalog incomplete: ' + result.outcome)
                rows = result.payload
                dates = [aware_instant(row['date']) for row in rows]
                require(dates == sorted(dates, reverse=True), 'HF archive commit order changed')
                if len(pages) > 1 and rows and pages[-1]['rows']:
                    require(dates[0] <= aware_instant(pages[-1]['rows'][-1]['date']),
                            'HF archive page order changed')
                page = {'head': pages[0]['head'], 'rows': rows, 'cursor': result.next_cursor,
                    'complete': result.next_cursor is None or bool(dates) and dates[-1] < aware_instant(job.scope['global_start_at'])}
            request_id = result.attempts[-1]['collection_request_id']
            with fenced_run(claim) as (_, run):
                observation = CollectionObservation.objects.create(run=run, scope_run=scope,
                    source_subject_kind='aggregate', source_identifier=DATASET,
                    observation_kind=KIND, resource_key=f'{len(pages):04d}',
                    observation_key=digest([KIND, str(job.pk), len(pages)]),
                    payload_sha256=digest(page), legacy_archive=archive_legacy(page))
                link_request(observation, CollectionRequest.objects.get(pk=request_id), role='archive_catalog_page')
            pages.append(page)
        checkpoint_scope(claim, scope_kind=KIND, scope_key='catalog', typed=True,
            ownership={'dataset_id': DATASET}, enumeration_complete=True, outcome='observed')
        status, error = 'success', None
    except (ValueError, KeyError, TypeError) as exc:
        status, error = 'partial', str(exc)[:64]
    finally:
        budget.remaining -= client.requests
        budget.total_bytes_read += client.bytes_received
    requests = CollectionRequest.objects.filter(attempt__run_id=claim.run_id)
    accounted = not requests.filter(accounting_complete=False).exists()
    with fenced_run(claim) as (_, run):
        run.physical_bytes_received = requests.aggregate(total=Sum('response_bytes'))['total'] if accounted else None
        run.save(update_fields=['physical_bytes_received'])
    return finish_run(claim, typed=True, status=status, error_code=error,
        request_count=requests.count(), selected_count=len(_saved_pages(job)),
        physical_accounting_complete=accounted)


def discovered_revisions(job_id):
    from scripts.benchmark_download_collector.hf_archive import select_model_revisions

    job = CollectionJob.objects.get(pk=job_id)
    validate_discovery(job)
    pages = _saved_pages(job)
    require(pages and pages[-1]['complete'], 'HF archive discovery is incomplete')
    selected = select_model_revisions([row for page in pages for row in page['rows']],
        start_date=aware_instant(job.scope['global_start_at']).date().isoformat(),
        end_date=aware_instant(job.scope['cutoff']).date().isoformat())
    return {'revisions': [{'id': selected[day]['id'], 'date': selected[day]['date'], 'snapshot_date': day}
                         for day in sorted(selected)],
            'examined_head': pages[0]['head'], 'pages': len(pages) - 1,
            'catalog_job_id': str(job.pk)}


def replay_archives(job):
    from core.benchmark_metric_history import import_history
    from core.model_history_archives import observation_documents

    validate_archive_only(job)
    require(job.state == 'completed' and job.last_attempt_id, 'completed HF archive job required')
    observations = list(job.last_attempt.observations.filter(
        projection_kind='hf-archive-snapshot-v1').select_related('legacy_archive')
        .defer('legacy_archive__body')[:job.budgets['items'] + 1])
    revisions = job.scope['hf_archive']['revisions']
    require(len(observations) == len(revisions) <= job.budgets['items'], 'HF replay snapshot count differs')
    expected = {(r['id'], r['snapshot_date']) for r in revisions}
    seen = set()
    runs = []
    for observation in observations:
        require(observation.legacy_archive.byte_count <= job.budgets['bytes'], 'HF replay snapshot byte cap')
        snap = observation_documents(observation)[0]
        identity = (snap['immutable_revision'], snap['date'])
        require(digest(snap) == observation.payload_sha256 and identity in expected and identity not in seen,
                'HF replay snapshot changed')
        seen.add(identity)
        if not snap['payload']['rows']:
            continue
        run = import_history({'schema_version': 1, 'contract_id': job.scope['numeric_contract_id'],
            'source': 'hf', 'dataset_id': DATASET, 'archive_publisher': 'cfahlgren1',
            'artifact_kind': 'selected_json', 'start_date': snap['date'], 'end_date': snap['date'],
            'snapshots': [snap]}, apply=True)
        runs.append(str(run.pk))
    require(seen == expected, 'HF replay snapshot identities differ')
    return {'provider_calls': 0, 'numeric_run_ids': runs, 'snapshots': len(observations)}
