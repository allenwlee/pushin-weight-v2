"""The narrow, reviewed 0813 cohort; no collection or production promotion."""
import re

from django.db import transaction

from core.benchmark_metric_identity import configure_collection, register_definitions
from core.benchmark_metric_store import aware_instant
from core.data_source_backfill_target import validate_backfill_target
from core.measurement_taxonomy import (
    configure_taxonomy,
    digest,
    require,
    resolve_subject_id,
)
from core.models import Account, BrandCompany, CollectionJob, DataSource, Product
from core.product_vocabulary import metadata_references, product_type_id
from core.publisher_accounts import register_publisher

PRODUCT = '20d66250-db05-40bf-8fda-94b610bed0c7'
PUBLISHER = 'e004d8c0-d998-4c23-a295-f41f0e7b532b'
IDENTIFIERS = {
    'hf': 'deepseek-ai/DeepSeek-V4-Pro-0813',
    'opencode': 'deepseek/deepseek-v4-pro-0813',
    'arena': 'deepseek-v4-pro-high-20260813',
    'openrouter': 'deepseek/deepseek-v4-pro-20260813',
}
ENDPOINT = '/data/deepseek/deepseek-v4-pro-0813.json'
START = '2026-08-13T00:00:00Z'
END = '2026-09-11T00:00:00Z'


def preview_cohort(reference):
    """Validate copied reference evidence without creating a catalog record."""
    product, publisher, ownership = reference['product'], reference['publisher'], reference['ownership']
    require(product['product_key'] == PRODUCT and product['repo_id'] == IDENTIFIERS['hf']
            and product['brand_id'] == 'deepseek' and product['hf_type'] == 'model'
            and product['publisher_account_key'] == PUBLISHER
            and product['private'] is False and product['disabled'] is False,
            '0813 reference identity changed')
    require(publisher['account_key'] == PUBLISHER and publisher['data_source_id'] == 'hf'
            and publisher['external_identifier'] == publisher['normalized_identifier'] == 'deepseek-ai'
            and publisher['account_kind'] == 'organization', '0813 publisher identity changed')
    require(len(ownership) == 1 and ownership[0]['company_id'] == 'deepseek_co'
            and ownership[0]['account_key'] == PUBLISHER
            and ownership[0]['ownership_confirmed'] is True
            and ownership[0]['role_id'] == 'official', '0813 ownership evidence changed')
    require(reference['task']['data_source_id'] == 'hf'
            and reference['task']['code'] == 'text-generation', '0813 task evidence changed')
    require(aware_instant(product['created_at']) == aware_instant('2026-08-13T03:05:06Z'),
            '0813 creation clock changed')
    require(re.fullmatch('[0-9a-f]{24}', product.get('hf_archive_row_id', '')),
            '0813 native HF archive row identity required')
    require(isinstance(product.get('display_name'), str) and bool(product['display_name'].strip()),
            '0813 reviewed product label required')
    identity = {
        'product': {key: product[key] for key in ('product_key', 'repo_id', 'brand_id', 'hf_type',
            'publisher_account_key', 'private', 'disabled', 'display_name', 'hf_archive_row_id')},
        'publisher': {key: publisher[key] for key in ('account_key', 'data_source_id',
            'external_identifier', 'normalized_identifier', 'account_kind')},
        'ownership': {key: ownership[0][key] for key in ('company_id', 'account_key', 'role_id', 'ownership_confirmed')},
        'task': {key: reference['task'][key] for key in ('data_source_id', 'code')},
    }
    identity['product']['created_at'] = aware_instant(product['created_at']).isoformat()
    identity['ownership']['added_at'] = aware_instant(ownership[0]['added_at']).isoformat()
    return {'product_key': PRODUCT, 'identifiers': dict(IDENTIFIERS), 'endpoint_path': ENDPOINT,
            'start_at': START, 'end_at': END, 'reference_sha256': digest(identity),
            'local_product_type_review': 'llm-model', 'writes': 0}


def configure_cohort(reference, *, reviewed_by):
    """Resolve natural keys locally; production integer IDs are never imported.

    The local catalog review classifies this exact text-generation model as an
    LLM. The original production record and source-use evidence stay unchanged.
    """
    preview = preview_cohort(reference)
    require(bool(reviewed_by.strip()), 'cohort reviewer required')
    validate_backfill_target(require_write=True)
    with transaction.atomic():
        return _configure_cohort(reference, preview, reviewed_by)


def _configure_cohort(reference, preview, reviewed_by):
    require(BrandCompany.objects.filter(brand_id='deepseek', company_id='deepseek_co').exists(),
            '0813 brand ownership missing')
    register_definitions(sources=IDENTIFIERS)
    DataSource.objects.filter(pk__in=IDENTIFIERS).update(enabled=True)
    account = Account.objects.select_for_update().filter(
        data_source_id='hf', normalized_identifier='deepseek-ai').first()
    if account is None:
        require(not Account.objects.filter(pk=PUBLISHER).exists(), '0813 publisher UUID conflict')
        account = Account.objects.create(account_key=PUBLISHER, data_source_id='hf',
            external_identifier='deepseek-ai', handle='deepseek-ai', identifier_kind='namespace',
            account_kind='organization')
    require(str(account.pk) == PUBLISHER and account.account_kind == 'organization',
            '0813 publisher conflict')
    register_publisher(source='hf', identifier='deepseek-ai', company_id='deepseek_co',
        confirmed=True, added_at=aware_instant(reference['ownership'][0]['added_at']))
    product = Product.objects.select_for_update().filter(product_key=PRODUCT).first()
    if product is None:
        require(not Product.objects.filter(repo_id=IDENTIFIERS['hf']).exists(), '0813 product UUID conflict')
        product = Product.objects.create(product_key=PRODUCT, repo_id=IDENTIFIERS['hf'],
            brand_id='deepseek', publisher_account=account, hf_type='model',
            display_name=reference['product']['display_name'], private=False, disabled=False,
            product_type_id=product_type_id('llm-model'),
            created_at=aware_instant(reference['product']['created_at']),
            **metadata_references({'pipeline_tag': 'text-generation'}, source_id='hf'))
    require(product.repo_id == IDENTIFIERS['hf'] and product.brand_id == 'deepseek'
            and str(product.publisher_account_id) == PUBLISHER
            and product.product_type_code == 'llm-model'
            and product.private is False and product.disabled is False,
            'existing 0813 catalog conflicts with reviewed cohort')
    taxonomy = configure_taxonomy({'reviewed_by': reviewed_by,
        'subjects': [{'kind': 'product', 'key': PRODUCT}]})
    sid = str(resolve_subject_id('product', PRODUCT))
    mappings = []
    urls = {'hf': 'https://huggingface.co/' + IDENTIFIERS['hf'],
        'opencode': 'https://opencode.ai' + ENDPOINT,
        'arena': 'https://arena.ai/leaderboard/text/overall',
        'openrouter': 'https://openrouter.ai/' + IDENTIFIERS['openrouter']}
    for source, identifier in IDENTIFIERS.items():
        mappings.append({'source': source, 'external_identifier': identifier,
            'source_subject_kind': 'repository' if source == 'hf' else 'model',
            'identifier_scope': 'model' if source == 'hf' else '',
            'subject_id': sid, 'evidence_url': urls[source],
            **({'publisher_account_key': PUBLISHER} if source == 'hf' else {}),
            **({'identifier_metadata': {'archive_row_key': reference['product']['hf_archive_row_id']}}
               if source == 'hf' else {}),
            **({'identifier_metadata': {'endpoint_path': ENDPOINT}} if source == 'opencode' else {})})
    contract = configure_collection({'taxonomy_version': str(taxonomy.pk),
        'reviewed_by': reviewed_by, 'mappings': mappings,
        'source_configuration': {
            'hf': {'metrics': ['downloads', 'downloads_all_time', 'likes', 'trending_score'],
                   'metric_versions': {'downloads': 2, 'downloads_all_time': 2}},
            'arena': {'metrics': ['rating', 'rank', 'rating_lower', 'rating_upper', 'variance', 'vote_count'],
                      'config': 'text', 'metric_versions': {'rating_lower': 2, 'rating_upper': 2, 'vote_count': 2}},
            'openrouter': {'metrics': ['total_tokens'], 'completed_day_lag': 1},
            'opencode': {'metrics': ['tokens', 'unique_users', 'sessions']},
        }, 'methodology': {'aggregation': 'fixed_cohort',
            'backfill_reference_sha256': preview['reference_sha256'],
            'local_product_type_review': preview['local_product_type_review']}})
    return {**preview, 'writes': True, 'contract_id': str(contract.pk),
            'contract_hash': contract.contract_hash, 'taxonomy_id': str(taxonomy.pk), 'subject_id': sid}


def campaign_specifications(contract, *, discovery_job_id=None):
    """Freeze conservative byte/time ceilings through existing attempt limits.

    Forty attempts at 25 MiB / 80 seconds reserve at most 1,000 MiB /
    3,200 seconds. The campaign's shared request counter separately caps all
    physical requests and uncertain reservations at 1,000.
    """
    from core.data_source_backfill_hf import DATASET, ROLE, discovered_revisions
    from core.models import MetricCollectionContract

    if isinstance(contract, str):
        contract = MetricCollectionContract.objects.get(pk=contract)
    mappings = list(contract.mappings.select_related('subject'))
    require({m.source_id: m.external_identifier for m in mappings} == IDENTIFIERS
            and all(str(m.subject.product_id) == PRODUCT for m in mappings)
            and len(mappings) == len(IDENTIFIERS), '0813 campaign contract changed')
    product = Product.objects.get(product_key=PRODUCT)
    row_key = next(m for m in mappings if m.source_id == 'hf').identifier_metadata.get('archive_row_key')
    require(isinstance(row_key, str) and re.fullmatch('[0-9a-f]{24}', row_key),
            '0813 HF archive row identity missing from reviewed contract')
    cohort = digest({'contract_hash': contract.contract_hash, 'identifiers': IDENTIFIERS,
        'start_at': START, 'end_at': END, 'max_attempts': 40, 'max_requests': 1000,
        'attempt_seconds': 80, 'attempt_bytes': 25 * 1024**2})
    key = '0813:' + cohort[:24]
    campaign = {'kind': 'backfiller-data-source-v1', 'key': key, 'cohort_hash': cohort,
        'role': 'history', 'phase': 'acquire', 'max_invocations': 40, 'max_requests': 1000,
        'contract_partition': None}
    budgets = {'requests': 100, 'bytes': 25 * 1024**2, 'seconds': 80, 'items': 100}
    models = [{'product_key': PRODUCT, 'creation': {'source': 'hf',
        'native_identifier': IDENTIFIERS['hf'], 'at': product.created_at.isoformat(),
        'hf_archive_row_id': row_key}, 'provider_pins': []}]
    common = {'brand_id': 'deepseek', 'cohort_hash': cohort, 'global_start_at': START,
        'cutoff': END, 'numeric_contract_id': str(contract.pk), 'models': models}

    def catalog(source, suffix, scope):
        return {'job_key': key + ':' + suffix, 'source': source, 'purpose': 'catalog',
            'operation': 'model_history', 'contract': None,
            'definition': {'version': 1, 'scope': scope, 'campaign': dict(campaign),
                'schedule': {'kind': 'manual', 'driver': 'manual'},
                # Arena's shared window retains the provider population before
                # selecting this exact model. Byte/time/request caps still apply.
                'budgets': {**budgets, 'items': 100000 if source == 'arena' else 100}}}

    if discovery_job_id:
        discovery = CollectionJob.objects.get(pk=discovery_job_id)
        require(discovery.campaign_id and discovery.campaign.cohort_hash == cohort,
                '0813 archive catalog belongs to another campaign')
        coordinates = discovered_revisions(discovery_job_id)
        return [catalog('hf', 'hf:' + revision['snapshot_date'], {**common,
            'backfill_archive_only': True, 'hf_archive': {'dataset_id': DATASET,
                'archive_publisher': 'cfahlgren1', 'revisions': [revision]}})
            for revision in coordinates['revisions']]
    mapping = next(m for m in mappings if m.source_id == 'opencode')
    opencode = {'job_key': key + ':opencode', 'source': 'opencode', 'purpose': 'metric',
        'operation': 'collect_metrics', 'contract': str(contract.pk),
        'definition': {'version': 2, 'options': {}},
        'campaign': {**campaign, 'contract_partition': str(contract.pk)},
        'settings': {'owner_kind': 'source', 'schedule_kind': 'manual', 'schedule_driver': 'manual',
            **{'max_' + name: value for name, value in budgets.items()}},
        'targets': [{'target_key': str(mapping.pk), 'subject_id': str(mapping.subject_id),
            'mapping_id': str(mapping.pk), 'native_identifier': mapping.external_identifier,
            'target_kind': 'metric_subject', 'target_role': 'history', 'resolution_state': 'resolved',
            'requested_start_at': START, 'requested_end_at': END}]}
    return [catalog('hf', 'archive-discovery', {**common, 'role': ROLE, 'dataset_id': DATASET,
                'max_pages': 40}), opencode,
            catalog('arena', 'arena-native', {**common, 'models': [], 'arena_config': 'text',
                'native_publication_identifiers': [IDENTIFIERS['arena']]})]


def validate_campaign_specification(spec, campaign_definition):
    """The 0813 campaign hash cannot authorize larger jobs or another interval."""
    from core.models import MetricCollectionContract

    campaign = campaign_definition['campaign']
    if not campaign['key'].startswith('0813:'):
        return
    scope = spec['definition'].get('scope', {})
    contract = MetricCollectionContract.objects.get(pk=spec.get('contract') or scope.get('numeric_contract_id'))
    frozen = campaign_specifications(contract)
    expected = frozen[0]['definition']['campaign']
    require(all(campaign[name] == expected[name] for name in (
        'key', 'cohort_hash', 'kind', 'max_invocations', 'max_requests', 'role', 'phase')),
        '0813 campaign identity or ceilings changed')
    maxima = frozen[2 if spec['source'] == 'arena' else 0]['definition']['budgets']
    require(all(type(campaign_definition['budgets'].get(name)) is int
                and 0 < campaign_definition['budgets'][name] <= maximum
                for name, maximum in maxima.items()), '0813 attempt ceiling exceeded')
    if spec['source'] == 'opencode':
        require(all(aware_instant(target['requested_start_at']) == aware_instant(START)
                    and aware_instant(target['requested_end_at']) == aware_instant(END)
                    for target in spec['targets']), '0813 requested interval changed')
    else:
        expected_scope = frozen[2 if spec['source'] == 'arena' else 0]['definition']['scope']
        require(scope.get('models') == expected_scope['models']
                and scope.get('brand_id') == 'deepseek' and scope.get('cohort_hash') == expected['cohort_hash']
                and scope.get('global_start_at') == START and scope.get('cutoff') == END,
                '0813 product selection or interval changed')
        require(spec['source'] == 'hf' or spec['source'] == 'arena'
                and scope.get('arena_config') == 'text'
                and scope.get('native_publication_identifiers') == [IDENTIFIERS['arena']],
                '0813 acquisition source or Arena variant changed')
