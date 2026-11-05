"""Exact 0813 references reuse shared identities without touching X authority."""
from copy import deepcopy

import pytest

from core.data_source_backfill_cohort import (
    ENDPOINT,
    IDENTIFIERS,
    PRODUCT,
    PUBLISHER,
    configure_cohort,
    preview_cohort,
)


def reference():
    return {'product': {'product_key': PRODUCT, 'repo_id': IDENTIFIERS['hf'],
        'brand_id': 'deepseek', 'hf_type': 'model', 'publisher_account_key': PUBLISHER,
        'private': False, 'disabled': False, 'display_name': 'DeepSeek-V4-Pro-0813',
        'created_at': '2026-08-13T03:05:06Z', 'hf_archive_row_id': '1' * 24},
        'publisher': {'account_key': PUBLISHER, 'data_source_id': 'hf',
            'external_identifier': 'deepseek-ai', 'normalized_identifier': 'deepseek-ai',
            'account_kind': 'organization'},
        'ownership': [{'company_id': 'deepseek_co', 'account_key': PUBLISHER,
            'ownership_confirmed': True, 'role_id': 'official', 'added_at': '2026-10-08T08:51:01Z'}],
        'task': {'data_source_id': 'hf', 'code': 'text-generation'}}


@pytest.mark.parametrize('identifier', ['deepseek-ai/DeepSeek-V4-Pro', 'deepseek-ai/DeepSeek-V4-Pro-Preview'])
def test_preview_rejects_other_release_without_database(identifier):
    value = reference()
    value['product']['repo_id'] = identifier
    with pytest.raises(ValueError, match='reference identity changed'):
        preview_cohort(value)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_reviewed_cohort_is_idempotent_exact_and_preserves_x(monkeypatch):
    from core.benchmark_metric_identity import configure_collection
    from core.models import Account, Brand, BrandCompany, DataSource, Product
    from tests.company_factory import company_with_label
    from tests.test_benchmark_download_db_identity import setup_spec

    _, spec = setup_spec()
    configure_collection(spec)
    Brand.objects.create(nickname='deepseek', display_name='DeepSeek')
    company = company_with_label('deepseek_co', 'DeepSeek')
    BrandCompany.objects.create(brand_id='deepseek', company=company)
    monkeypatch.setattr('core.data_source_backfill_cohort.validate_backfill_target', lambda **_: {})
    before = DataSource.objects.filter(pk='x').values().get()
    refs = reference()
    original = deepcopy(refs)
    assert preview_cohort(refs)['writes'] == 0
    assert not Product.objects.filter(product_key=PRODUCT).exists()
    result = configure_cohort(refs, reviewed_by='fixture: exact 0813 references')
    assert configure_cohort(refs, reviewed_by='fixture: exact 0813 references') == result
    refreshed = deepcopy(refs)
    refreshed['product'].update(id=9876, downloads=999, updated_at='2026-11-05T01:00:00Z')
    refreshed['task']['id'] = 9876
    assert configure_cohort(refreshed, reviewed_by='fixture: exact 0813 references') == result
    from core.models import MetricCollectionContract
    contract = MetricCollectionContract.objects.get(pk=result['contract_id'])
    mappings = list(contract.mappings.select_related('subject'))
    assert {m.source_id: m.external_identifier for m in mappings} == IDENTIFIERS
    assert all(str(m.subject.product_id) == PRODUCT for m in mappings)
    # Exercise adapter-to-mapping admission: a model's kind is not its scope.
    # Other source adapters emit the empty scope; HF requires model explicitly.
    assert {m.source_id: m.identifier_scope_code for m in mappings} == {
        'hf': 'model', 'arena': '', 'openrouter': '', 'opencode': ''}
    from core.benchmark_metric_store import prepare_rows
    for source, payload in {
        'openrouter': {'meta': {'version': 'v1'}, 'rows': [{'model_permaslug': IDENTIFIERS['openrouter'],
            'date': '2026-08-19', 'total_tokens': '0'}]},
        'arena': {'config': 'text', 'rows': [{'model_name': IDENTIFIERS['arena'],
            'leaderboard_publish_date': '2026-08-19', 'category': 'overall',
            'rating': 1500, 'rank': 1, 'rating_lower': 1490, 'rating_upper': 1510,
            'variance': 5, 'vote_count': 100}]},
        'opencode': {'rows': [{'model_id': IDENTIFIERS['opencode'],
            'date': '2026-08-19', 'tokens': 0, 'uniqueUsers': 2, 'sessions': 3,
            '_source_metadata': {'updated_at': '2026-08-20T12:00:00Z',
                                 'period_status': 'completed'}}]},
    }.items():
        prepared = prepare_rows(contract, source, {'status': 'ok', **payload})
        assert len(prepared) == 1
        observation, values = prepared[0]
        assert observation['status'] == 'ok' and values
        assert str(observation['mapping'].subject.product_id) == PRODUCT
    assert next(m for m in mappings if m.source_id == 'opencode').identifier_metadata == {'endpoint_path': ENDPOINT}
    assert str(Account.objects.get(data_source_id='hf', normalized_identifier='deepseek-ai').pk) == PUBLISHER
    assert DataSource.objects.filter(pk='x').values().get() == before
    assert refs == original

    # The public command's preview uses the same references without writes.
    import json
    from io import StringIO

    from django.core.management import call_command
    monkeypatch.setattr('core.management.commands.backfiller_data_source.validate_backfill_target',
                        lambda **_: {'schema_ready': True})
    output = StringIO()
    call_command('backfiller_data_source', operation='prepare-0813',
                 reference=json.dumps(refs), stdout=output)
    assert json.loads(output.getvalue())['writes'] == 0
    output = StringIO()
    call_command('backfiller_data_source', operation='plan-0813',
                 contract=str(contract.pk), stdout=output)
    specifications = json.loads(output.getvalue())['specifications']
    from core.data_source_backfill import prepare_campaign
    prepared = prepare_campaign(specifications)
    assert {job['source'].pk for job in prepared} == {'hf', 'arena', 'opencode'}
    # The narrow native-publication route must reach acquisition. A product
    # with empty provider_pins instead returns unmapped without any request.
    from core.data_source_backfill import execute_phase, register_campaign
    monkeypatch.setattr('core.data_source_backfill_target.validate_backfill_target', lambda **_: {})
    acquired = []

    def publication(claim, job, model, pins, budget, *, key):
        acquired.append(job.scope['native_publication_identifiers'])
        return [], {'outcome': 'history_unavailable', 'reason': 'fixture_no_publications'}

    monkeypatch.setattr('core.model_history_collection._publication_evidence', publication)
    arena = register_campaign([spec for spec in specifications if spec['source'] == 'arena'])[0]
    execute_phase(arena.pk)
    assert acquired == [[IDENTIFIERS['arena']]]
    assert all(spec.get('campaign', spec['definition'].get('campaign'))['max_invocations'] == 40
               for spec in specifications)
    expanded = deepcopy(specifications)
    expanded[0]['definition']['budgets']['bytes'] = 32 * 1024**2
    with pytest.raises(ValueError, match='attempt ceiling exceeded'):
        prepare_campaign(expanded)
    changed_window = deepcopy(specifications)
    changed_window[1]['targets'][0]['requested_start_at'] = '2026-08-12T00:00:00Z'
    with pytest.raises(ValueError, match='requested interval changed'):
        prepare_campaign(changed_window)

    # A changed UUID fails atomically rather than adopting another product.
    changed = reference()
    changed['product']['product_key'] = '00000000-0000-0000-0000-000000000001'
    with pytest.raises(ValueError, match='reference identity changed'):
        configure_cohort(changed, reviewed_by='fixture')
    assert Product.objects.filter(product_key=PRODUCT).count() == 1
