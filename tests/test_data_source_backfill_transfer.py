"""Reviewed backfill captures replay into another database only when every value matches."""
import json
from copy import deepcopy
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import connection, transaction

from core.benchmark_metric_store import aware_instant, persist_source
from core.data_source_backfill_cohort import (
    IDENTIFIERS,
    PRODUCT,
    PUBLISHER,
    configure_cohort,
)
from core.data_source_backfill_reuse import ORIGIN_RESOURCE, reuse_capture
from core.data_source_backfill_transfer import (
    apply_bundle,
    build_bundle,
    bundle_digest,
    classify_cells,
)
from core.measurement_taxonomy import digest
from core.models import (
    Account,
    Brand,
    BrandCompany,
    CollectionRun,
    DataSource,
    MetricCollectionContract,
    MetricValue,
    Product,
)
from tests.company_factory import company_with_label
from tests.test_benchmark_download_db_identity import setup_spec
from tests.test_data_source_backfill_cohort import reference

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

REVIEWER = 'fixture: transfer'


def hf_row(repo, day, downloads, revision, trending=None):
    raw = {'downloads': downloads, 'downloadsAllTime': downloads + 5, 'likes': 7}
    if trending is not None:
        raw['trendingScore'] = trending
    return {'repo_id': repo, 'status': 'ok', 'raw': raw, '_source_metadata': {
        'archive_snapshot_date': day, 'archive_snapshot_timezone': 'UTC', 'original_retrieved_at': None,
        'secondary_source': True, 'immutable_revision': revision, 'dataset_id': 'cfahlgren1/hub-stats',
        'archive_publisher': 'cfahlgren1'}}


ORIGIN_PAYLOADS = {
    'hf': {'status': 'ok', 'rows': [hf_row(IDENTIFIERS['hf'], '2026-09-06', 120, 'a' * 40),
                                    hf_row('other/model', '2026-09-06', 999, 'a' * 40)]},
    'arena': {'status': 'ok', 'config': 'text', 'rows': [
        {'model_name': IDENTIFIERS['arena'], 'leaderboard_publish_date': '2026-08-19', 'category': 'overall',
         'rating': 1442.5, 'rank': 55, 'rating_lower': 1431.25, 'rating_upper': 1453.75, 'variance': 33.5,
         'vote_count': 2654},
        {'model_name': 'other-model', 'leaderboard_publish_date': '2026-08-19', 'category': 'overall',
         'rating': 1300, 'rank': 90, 'rating_lower': 1290, 'rating_upper': 1310, 'variance': 9, 'vote_count': 5}]},
    'openrouter': {'status': 'ok', 'meta': {'version': 'v1'}, 'rows': [
        {'model_permaslug': IDENTIFIERS['openrouter'], 'date': '2026-08-13', 'total_tokens': '142872896552'},
        {'model_permaslug': IDENTIFIERS['openrouter'], 'date': '2026-08-14', 'total_tokens': '0'},
        {'model_permaslug': 'other/model', 'date': '2026-08-13', 'total_tokens': '5'}]},
}


def production_catalog():
    """The target already holds the reviewed product, without a recorded type."""
    from core.benchmark_metric_identity import register_definitions
    from core.product_vocabulary import metadata_references
    from core.publisher_accounts import register_publisher

    register_definitions(sources=IDENTIFIERS)
    DataSource.objects.filter(pk__in=IDENTIFIERS).update(enabled=True)
    account = Account.objects.create(account_key=PUBLISHER, data_source_id='hf', external_identifier='deepseek-ai',
        handle='deepseek-ai', identifier_kind='namespace', account_kind='organization')
    register_publisher(source='hf', identifier='deepseek-ai', company_id='deepseek_co', confirmed=True,
                       added_at=aware_instant('2026-10-08T08:51:01Z'))
    Product.objects.create(product_key=PRODUCT, repo_id=IDENTIFIERS['hf'], brand_id='deepseek',
        publisher_account=account, hf_type='model', display_name='DeepSeek-V4-Pro-0813', private=False,
        disabled=False, created_at=aware_instant('2026-08-13T03:05:06Z'),
        **metadata_references({'pipeline_tag': 'text-generation'}, source_id='hf'))


def production_origins(lab_spec):
    """An existing chart contract captured the 0813 rows without mapping them."""
    from core.benchmark_metric_identity import configure_collection

    spec = deepcopy(lab_spec)
    spec['source_configuration'] = {
        'hf': {'metrics': ['downloads', 'downloads_all_time', 'likes', 'trending_score'],
               'metric_versions': {'downloads': 2, 'downloads_all_time': 2}},
        'arena': {'metrics': ['rating', 'rank', 'rating_lower', 'rating_upper', 'variance', 'vote_count'],
                  'config': 'text', 'metric_versions': {'rating_lower': 2, 'rating_upper': 2, 'vote_count': 2}},
        'openrouter': {'metrics': ['total_tokens'], 'completed_day_lag': 1}}
    chart = configure_collection(spec)
    origins = {}
    for source, payload in ORIGIN_PAYLOADS.items():
        run = persist_source(chart, source, digest(['origin', source]), deepcopy(payload))
        origins[source] = {'resource': ORIGIN_RESOURCE, 'run_id': str(run.pk),
                           'archive_id': str(run.payload_archive_id), 'payload_sha256': run.payload_sha256}
    return chart, origins


class _Discard(Exception):
    pass


@pytest.fixture
def transfer_case(monkeypatch):
    _, lab_spec = setup_spec()
    Brand.objects.create(nickname='deepseek', display_name='DeepSeek')
    BrandCompany.objects.create(brand_id='deepseek', company=company_with_label('deepseek_co', 'DeepSeek'))
    production_catalog()
    chart, origins = production_origins(lab_spec)
    monkeypatch.setattr('core.data_source_backfill_cohort.validate_backfill_target', lambda **_: {})
    monkeypatch.setattr('core.data_source_backfill_target.validate_backfill_target', lambda **_: {})
    captured = {}
    # Build the reviewed backfill contract, export it, then discard it so the
    # target starts from production-like state with fresh database IDs.
    with pytest.raises(_Discard), transaction.atomic():
        from core.product_vocabulary import product_type_id

        Product.objects.filter(product_key=PRODUCT).update(product_type_id=product_type_id('llm-model'))
        contract = MetricCollectionContract.objects.get(
            pk=configure_cohort(reference(), reviewed_by='fixture: backfill review')['contract_id'])
        for source in ('openrouter', 'arena', 'hf'):
            reuse_capture(contract, source=source, payload=deepcopy(ORIGIN_PAYLOADS[source]), origin=origins[source])
        archive = {'adapter_version': 'hf-model-v1', 'dataset_id': 'cfahlgren1/hub-stats',
                   'ingestion_mode': 'historical_import', 'secondary_source': True}
        for day, revision in (('2026-09-06', 'b' * 40), ('2026-09-07', 'c' * 40)):
            payload = {'status': 'ok', 'rows': [hf_row(IDENTIFIERS['hf'], day, 120, revision, trending=4.5)]}
            persist_source(contract, 'hf', digest(['archive', day]), payload, source_metadata=dict(archive),
                           isolated_review=True)
        captured['bundle'] = build_bundle(contract)
        captured['origin_contract'] = contract.pk
        raise _Discard
    monkeypatch.undo()
    assert not MetricCollectionContract.objects.filter(pk=captured['origin_contract']).exists()
    assert Product.objects.get(product_key=PRODUCT).product_type_code is None
    return captured['bundle'], chart


def current_database():
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        return cursor.fetchone()[0]


def footprint():
    return (MetricCollectionContract.objects.count(), CollectionRun.objects.count(), MetricValue.objects.count(),
            Product.objects.get(product_key=PRODUCT).product_type_code)


def test_rehearsal_writes_nothing_and_apply_reproduces_values_reader_and_reconciliation(transfer_case, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx.Client, 'send', lambda *_a, **_k: pytest.fail('transfer made HTTP'))
    bundle, chart = transfer_case
    assert bundle['value_count'] == 6 + 2 + 3 + 4 + 4
    before = footprint()
    rehearsal = apply_bundle(deepcopy(bundle), expected_database=current_database(), reviewed_by=REVIEWER)
    assert rehearsal['problems'] == [] and rehearsal['committed'] is False
    assert footprint() == before
    report = apply_bundle(deepcopy(bundle), expected_database=current_database(), reviewed_by=REVIEWER, commit=True)
    assert report['problems'] == [] and report['committed'] is True
    assert report['product_type_before'] is None
    assert Product.objects.get(product_key=PRODUCT).product_type_code == 'llm-model'
    origin = bundle['origin']
    contract = MetricCollectionContract.objects.get(pk=report['contract']['id'])
    assert report['contract']['created'] and str(contract.pk) != origin['contract_id']
    assert (contract.catalog_hash, contract.mapping_hash, contract.methodology_hash) == (
        origin['catalog_hash'], origin['mapping_hash'], origin['methodology_hash'])
    assert report['captures_created'] == len(bundle['captures']) == 5
    assert report['retained_origins_verified'] == 3
    values = MetricValue.objects.filter(observation__run__job__contract=contract)
    assert values.count() == bundle['value_count']
    assert all(value.observation.mapping.subject.product_id == contract.mappings.first().subject.product_id
               for value in values.select_related('observation__mapping__subject'))
    openrouter = values.get(source_metric__metric_key='total_tokens', period_label_date='2026-08-14')
    assert openrouter.integer_value == 0
    from core.collection_capture import read_document

    for run in CollectionRun.objects.filter(job__contract=contract):
        transfer = read_document(run.source_metadata_archive)['backfill_transfer_origin']
        assert transfer['bundle_sha256'] == bundle['bundle_sha256']
        assert transfer['payload_sha256'] == run.payload_sha256
    assert report['reader_observed_points'] == sum(len(rows) for rows in [
        [p for p in points if p['raw_value'] is not None and p['observed'] is not False]
        for points in bundle['expected_reader'].values()])
    reconciliation = report['reconciliation']
    assert reconciliation['summary'] == {'equivalent': 11, 'inserted_only': 5}
    assert all(row['existing'][0]['contract_id'] == str(chart.pk) for row in reconciliation['details'])
    assert '2026-08-15' in reconciliation['missing_requested_days']['openrouter']
    again = apply_bundle(deepcopy(bundle), expected_database=current_database(), reviewed_by=REVIEWER, commit=True)
    assert again['problems'] == [] and again['captures_created'] == 0 and not again['contract']['created']
    assert values.count() == bundle['value_count']


def test_any_value_difference_rolls_back_every_write(transfer_case, tmp_path):
    bundle, _ = transfer_case
    changed = deepcopy(bundle)
    capture = next(c for c in changed['captures'] if c['source'] == 'openrouter')
    row = next(r for r in capture['expected_values'] if r['period_label_date'] == '2026-08-13')
    row['integer_value'] = '142872896553'
    changed['bundle_sha256'] = bundle_digest(changed)
    before = footprint()
    report = apply_bundle(changed, expected_database=current_database(), reviewed_by=REVIEWER, commit=True)
    assert report['committed'] is False
    assert [p['fields'] for p in report['problems']] == [
        {'integer_value': {'expected': '142872896553', 'actual': '142872896552'}}]
    assert footprint() == before
    path = tmp_path / 'changed.json'
    path.write_text(json.dumps(changed))
    with pytest.raises(CommandError, match='verification failed'):
        call_command('transfer_backfill_contract', '--bundle', str(path), '--target-database', current_database(),
                     '--apply', stdout=StringIO())
    assert footprint() == before


def test_tampering_identity_and_target_are_refused_before_writes(transfer_case):
    bundle, _ = transfer_case
    before = footprint()
    database = current_database()
    tampered = deepcopy(bundle)
    tampered['captures'][0]['payload']['rows'][0]['total_tokens'] = '1'
    with pytest.raises(ValueError, match='bundle hash mismatch'):
        apply_bundle(tampered, expected_database=database, reviewed_by=REVIEWER)
    tampered['bundle_sha256'] = bundle_digest(tampered)
    with pytest.raises(ValueError, match='capture payload hash mismatch'):
        apply_bundle(tampered, expected_database=database, reviewed_by=REVIEWER)
    for target in ('xbackfiller', database + '_other', ''):
        with pytest.raises(ValueError, match='target'):
            apply_bundle(deepcopy(bundle), expected_database=target, reviewed_by=REVIEWER)
    from core.product_vocabulary import product_type_id

    Product.objects.filter(product_key=PRODUCT).update(product_type_id=product_type_id('other-ai-model'))
    with pytest.raises(ValueError, match='another reviewed type'):
        apply_bundle(deepcopy(bundle), expected_database=database, reviewed_by=REVIEWER, commit=True)
    Product.objects.filter(product_key=PRODUCT).update(product_type_id=None)
    origin_run = bundle['captures'][0]['source_metadata']['retained_capture_origin']['run_id']
    CollectionRun.objects.filter(pk=origin_run).update(payload_sha256='f' * 64)
    with pytest.raises(ValueError, match='retained origin'):
        apply_bundle(deepcopy(bundle), expected_database=database, reviewed_by=REVIEWER, commit=True)
    assert footprint() == before


def test_command_rehearsal_is_read_only(transfer_case, tmp_path):
    bundle, _ = transfer_case
    path = tmp_path / 'bundle.json'
    path.write_text(json.dumps(bundle))
    before = footprint()
    output = StringIO()
    call_command('transfer_backfill_contract', '--bundle', str(path), '--target-database', current_database(),
                 stdout=output)
    report = json.loads(output.getvalue())
    assert report['mode'] == 'rehearsal' and report['committed'] is False and report['problems'] == []
    assert report['provider_calls'] == 0
    assert footprint() == before


def test_cells_are_classified_without_resolving_disagreement():
    rows = classify_cells(
        {('hf', 'likes', '2026-09-06'): {'7'}, ('hf', 'likes', '2026-09-07'): {'7'},
         ('hf', 'likes', '2026-09-08'): {'7'}, ('hf', 'likes', '2026-09-09'): {'7', '8'}},
        {('hf', 'likes', '2026-09-06'): [('c', '7')], ('hf', 'likes', '2026-09-07'): [('c', '7'), ('d', '9')]})
    assert [row['state'] for row in rows] == [
        'equivalent', 'conflicting', 'inserted_only', 'transferred_captures_disagree']
