"""A bounded archive lookup resumes from saved provider pages, without files."""
import httpx
import pytest

from core.data_source_backfill_hf import DATASET, ROLE, discovered_revisions
from scripts.benchmark_download_collector.sources import Budget

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_discovery_resumes_saved_immutable_head_and_pages(monkeypatch):
    from core.data_source_backfill import execute_phase, register_campaign
    from core.models import (
        CollectionObservation,
        CollectionRequest,
        CollectionRun,
        DataSource,
    )
    from tests.test_data_source_backfill import specification

    monkeypatch.setattr('core.data_source_backfill_target.validate_backfill_target', lambda **_: {})
    spec = specification()
    source, _ = DataSource.objects.get_or_create(pk='hf', defaults={'name': 'Hugging Face', 'source_type': 'model_adoption'})
    source.enabled, source.adapter_key = True, 'hf-model-v1'
    source.save(update_fields=['enabled', 'adapter_key'])
    spec.update(job_key='campaign:hf:archive-discovery', source='hf', operation='model_history')
    spec['definition']['scope'] = {'role': ROLE, 'dataset_id': DATASET, 'max_pages': 4,
        'global_start_at': '2026-08-13T00:00:00Z', 'cutoff': '2026-09-11T00:00:00Z'}
    job = register_campaign([spec])[0]
    seen = []
    def send(request):
        seen.append(str(request.url))
        assert 'authorization' not in request.headers
        if request.url.path == '/api/datasets/' + DATASET:
            return httpx.Response(200, json={'sha': 'a' * 40})
        assert request.url.path == '/api/datasets/' + DATASET + '/commits/' + 'a' * 40
        if not request.url.params.get('cursor'):
            return httpx.Response(200, json=[{'id': 'b' * 40, 'date': '2026-08-20T04:00:00Z',
                'title': 'Update models.parquet'}], headers={
                'link': '<https://huggingface.co' + request.url.path + '?cursor=older>; rel="next"'})
        assert request.url.params['cursor'] == 'older'
        return httpx.Response(200, json=[{'id': 'c' * 40, 'date': '2026-08-12T04:00:00Z',
            'title': 'Update models.parquet'}])
    client = httpx.Client(transport=httpx.MockTransport(send))
    first = execute_phase(job.pk, budget=Budget(client, max_requests=2, max_bytes=100000, cumulative=True))
    assert first.status == 'partial'
    assert len(seen) == 2
    with pytest.raises(ValueError, match='discovery is incomplete'):
        discovered_revisions(job.pk)
    second = execute_phase(job.pk, budget=Budget(client, max_requests=20, max_bytes=100000, cumulative=True))
    assert second.status == 'success'
    assert len(seen) == 3
    result = discovered_revisions(job.pk)
    assert result['revisions'] == [{'id': 'b' * 40, 'date': '2026-08-20T04:00:00Z', 'snapshot_date': '2026-08-20'}]
    assert result['examined_head'] == 'a' * 40 and result['pages'] == 2
    assert CollectionObservation.objects.filter(observation_kind='hf_archive_catalog').count() == 3
    assert CollectionRequest.objects.count() == 3
    assert all(CollectionRun.objects.values_list('physical_bytes_received', flat=True))


def test_archive_only_captures_ranges_and_replays_zero_without_http(monkeypatch):
    import io
    from datetime import UTC, datetime

    import pyarrow as pa
    import pyarrow.parquet as pq

    from core.benchmark_metric_identity import configure_collection
    from core.data_source_backfill_hf import replay_archives
    from core.model_history_collection import execute_model_history
    from core.models import CollectionRequest, DataSource, MetricValue
    from tests.test_benchmark_download_db_identity import setup_spec
    from tests.test_model_history_collection import history_job

    product, spec = setup_spec()
    spec['source_configuration']['hf'].update(
        metrics=['downloads', 'downloads_all_time', 'likes', 'trending_score'],
        metric_versions={'downloads': 2, 'downloads_all_time': 2})
    contract = configure_collection(spec)
    product.created_at = datetime(2026, 9, 1, tzinfo=UTC)
    product.save(update_fields=['created_at'])
    source = DataSource.objects.get(pk='hf')
    source.enabled = True
    source.save(update_fields=['enabled'])
    job = history_job(source, product.brand, product,
        creation={'at': product.created_at.isoformat(), 'source': 'hf', 'native_identifier': product.repo_id},
        extra={'backfill_archive_only': True, 'numeric_contract_id': str(contract.pk),
            'hf_archive': {'dataset_id': DATASET, 'archive_publisher': 'cfahlgren1',
                'revisions': [{'id': 'a' * 40, 'date': '2026-09-10T01:00:00Z', 'snapshot_date': '2026-09-10'}]}})
    output = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([{'id': product.repo_id, 'downloads': 0, 'likes': 0}]), output)
    binary = output.getvalue()
    def send(request):
        import re
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', request.headers['range']).groups())
        return httpx.Response(206, content=binary[start:end + 1],
            headers={'content-range': f'bytes {start}-{end}/{len(binary)}'})
    client = httpx.Client(transport=httpx.MockTransport(send))
    run = execute_model_history(job.pk, budget=Budget(client, max_requests=30, max_bytes=1000000, cumulative=True))
    assert run.status == 'success' and run.success_count == 1
    requests = list(CollectionRequest.objects.filter(attempt__run=run))
    assert requests and all(r.request_category == 'hf_archive_range' and r.request_config.startswith('bytes=')
                            and r.archive_id and r.accounting_complete for r in requests)
    assert run.request_count == len(requests)
    assert run.physical_bytes_received == sum(r.response_bytes for r in requests)
    assert sorted(MetricValue.objects.values_list('source_metric__metric_key', 'integer_value')) == [
        ('downloads', 0), ('likes', 0)]
    job.refresh_from_db()
    monkeypatch.setattr(httpx.Client, 'send', lambda *_a, **_k: pytest.fail('HF replay made HTTP'))
    replay = replay_archives(job)
    assert replay['provider_calls'] == 0 and len(replay['numeric_run_ids']) == 1
    assert MetricValue.objects.count() == 2


def test_existing_file_archive_command_keeps_its_output_and_shared_selection(monkeypatch, tmp_path):
    import io
    import json
    import re
    from io import StringIO

    import pyarrow as pa
    import pyarrow.parquet as pq
    from django.core.management import call_command

    from tests.test_benchmark_download_persistence import configured

    contract = configured()
    cohort = tmp_path / 'cohort.json'
    cohort.write_text(json.dumps({'repositories': [{'identifier': 'lab/Model'}]}))
    output = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([{'id': 'lab/Model', 'downloads': 0, 'downloadsAllTime': 10}]), output)
    binary = output.getvalue()
    def send(request):
        if request.url.path == '/api/datasets/' + DATASET + '/commits/main':
            return httpx.Response(200, json=[{'id': 'a' * 40, 'date': '2026-09-10T01:00:00Z',
                'title': 'Update models.parquet'}])
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', request.headers['range']).groups())
        return httpx.Response(206, content=binary[start:end + 1],
            headers={'content-range': f'bytes {start}-{end}/{len(binary)}'})
    factory = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **_: factory(transport=httpx.MockTransport(send)))
    root = tmp_path / 'archive'
    call_command('backfill_hf_archive', str(cohort), contract=str(contract.pk), output=str(root),
                 max_requests=30, max_bytes=1000000, max_seconds=30, stdout=StringIO())
    coverage = json.loads((root / 'coverage.json').read_text())
    assert coverage['complete'] is True and len(coverage['completed']) == 1
    snapshot = json.loads((root / 'snapshot-2026-09-10.json').read_text())
    assert snapshot['data']['revision'] == 'a' * 40
    assert snapshot['data']['rows'] == [{'id': 'lab/Model', 'downloads': 0, 'downloadsAllTime': 10}]
