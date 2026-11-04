"""Copied source captures preserve dates, zeros and cross-database provenance."""
from copy import deepcopy
from uuid import uuid4

import pytest

from core.data_source_backfill_cohort import IDENTIFIERS, configure_cohort
from core.data_source_backfill_reuse import ORIGIN_RESOURCE, reuse_capture
from core.measurement_taxonomy import digest
from core.models import Brand, BrandCompany, MetricCollectionContract, MetricValue
from tests.company_factory import company_with_label
from tests.test_benchmark_download_db_identity import setup_spec
from tests.test_data_source_backfill_cohort import reference

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def retained_contract(monkeypatch):
    setup_spec()
    Brand.objects.create(nickname='deepseek', display_name='DeepSeek')
    company = company_with_label('deepseek_co', 'DeepSeek')
    BrandCompany.objects.create(brand_id='deepseek', company=company)
    monkeypatch.setattr('core.data_source_backfill_cohort.validate_backfill_target', lambda **_: {})
    monkeypatch.setattr('core.data_source_backfill_target.validate_backfill_target', lambda **_: {})
    result = configure_cohort(reference(), reviewed_by='fixture: retained evidence')
    contract = MetricCollectionContract.objects.get(pk=result['contract_id'])
    return contract


def test_retained_hf_capture_selects_one_product_and_replays_without_duplicate_values(monkeypatch, retained_contract):
    contract = retained_contract
    payload = {'status': 'ok', 'rows': [{
        'repo_id': IDENTIFIERS['hf'], 'status': 'ok',
        'raw': {'downloads': 0, 'downloadsAllTime': 10, 'likes': 2},
        '_source_metadata': {'archive_snapshot_date': '2026-09-06', 'archive_snapshot_timezone': 'UTC',
            'original_retrieved_at': '2026-10-07T02:45:45Z', 'secondary_source': True,
            'immutable_revision': 'a' * 40, 'dataset_id': 'cfahlgren1/hub-stats',
            'archive_publisher': 'cfahlgren1'},
    }, {'repo_id': 'other/model', 'status': 'ok', 'raw': {'downloads': 999}}]}
    before = deepcopy(payload)
    origin = {'resource': ORIGIN_RESOURCE, 'run_id': str(uuid4()), 'archive_id': str(uuid4()),
        'payload_sha256': digest(payload)}
    run = reuse_capture(contract, source='hf', payload=payload, origin=origin)
    assert run.status == 'success' and run.request_count == 0
    assert reuse_capture(contract, source='hf', payload=payload, origin=origin).pk == run.pk
    assert MetricValue.objects.count() == 3
    downloads = MetricValue.objects.get(source_metric__metric_key='downloads')
    assert downloads.integer_value == 0
    assert downloads.period_label_date.isoformat() == '2026-09-06'
    assert downloads.observation.original_retrieved_at.isoformat() == '2026-10-07T02:45:45+00:00'
    assert payload == before
    changed = deepcopy(payload)
    changed['rows'][0]['raw']['downloads'] = 1
    with pytest.raises(ValueError, match='origin/hash mismatch'):
        reuse_capture(contract, source='hf', payload=changed, origin=origin)
    assert MetricValue.objects.count() == 3
    import httpx

    from core.data_source_backfill_reuse import replay_retained_run

    monkeypatch.setattr(httpx.Client, 'send', lambda *_a, **_k: pytest.fail('retained replay made HTTP'))
    # The committed run is sufficient; the original file/payload is not an input.
    assert replay_retained_run(run.pk).pk == run.pk
    assert MetricValue.objects.count() == 3

    import json
    from io import StringIO

    from django.core.management import call_command
    monkeypatch.setattr('core.management.commands.backfiller_data_source.validate_backfill_target',
                        lambda **_: {'schema_ready': True})
    for apply in (False, True):
        output = StringIO()
        arguments = ['backfiller_data_source', '--operation', 'replay-retained', '--run', str(run.pk)]
        if apply:
            arguments.append('--apply')
        call_command(*arguments, stdout=output)
        report = json.loads(output.getvalue())
        assert report['run_id'] == str(run.pk)
        assert report['provider_calls'] == 0
        assert MetricValue.objects.count() == 3


@pytest.mark.parametrize('source', ['arena', 'openrouter'])
def test_retained_native_models_persist_under_exact_product_and_contract(monkeypatch, retained_contract, source):
    import httpx

    from core.data_source_backfill_cohort import PRODUCT
    from core.data_source_backfill_reuse import replay_retained_run

    monkeypatch.setattr(httpx.Client, 'send', lambda *_a, **_k: pytest.fail('retained import made HTTP'))
    contract = retained_contract
    payloads = {
        'arena': {'status': 'ok', 'config': 'text', 'rows': [{
            'model_name': IDENTIFIERS['arena'], 'leaderboard_publish_date': '2026-08-19',
            'category': 'overall', 'rating': 1500, 'rank': 1, 'rating_lower': 1490,
            'rating_upper': 1510, 'variance': 5, 'vote_count': 100}]},
        'openrouter': {'status': 'ok', 'meta': {'version': 'v1'}, 'rows': [{
            'model_permaslug': IDENTIFIERS['openrouter'], 'date': '2026-08-19', 'total_tokens': '0'}]},
    }
    payload = payloads[source]
    origin = {'resource': ORIGIN_RESOURCE, 'run_id': str(uuid4()), 'archive_id': str(uuid4()),
              'payload_sha256': digest(payload)}
    run = reuse_capture(contract, source=source, payload=payload, origin=origin)
    assert run.status == 'success' and run.success_count == 1
    values = list(MetricValue.objects.filter(observation__run=run).select_related('observation__mapping__subject'))
    assert len(values) == (6 if source == 'arena' else 1)
    assert all(value.observation.mapping.contract_id == contract.pk
               and str(value.observation.mapping.subject.product_id) == PRODUCT for value in values)
    if source == 'openrouter':
        assert values[0].integer_value == 0
    before = MetricValue.objects.count()
    assert replay_retained_run(run.pk).pk == run.pk
    assert MetricValue.objects.count() == before
