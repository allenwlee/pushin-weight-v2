from copy import deepcopy

import pytest

from core.official_company_offerings import qualification_decision
from core.official_company_response_recovery import recover_quote, recover_screen


def test_recovers_only_unique_typographic_match_as_literal_source():
    source = 'We build “useful AI”\n  for teams.'
    assert recover_quote('We build "useful AI" for teams.', source) == source
    assert recover_quote('We build "useful AI" for teams.', source + '\n' + source) is None


@pytest.mark.parametrize('quote,source', [
    ('We built 102 models', 'We built 10² models'),
    ('We build safe models', 'We do not build safe models'),
    ('We build “safe models”', 'We build unsafe models'),
    ('unknown passage', 'A different supported source'),
])
def test_non_equivalent_text_is_not_recovered(quote, source):
    assert recover_quote(quote, source) is None


def test_unresolved_claim_is_separate_and_original_is_untouched():
    evidence = {'sources': [{'id': 'profile', 'text': 'Example Lab builds an AI platform.'}]}
    response = {
        'organization_name': 'Example Lab', 'account_presentation': 'company_account',
        'identity_rationale': 'Company profile',
        'identity_citations': [{'source_id': 'profile', 'quote': 'Example Lab builds an AI platform.'}],
        'products': [
            {'name': 'Platform', 'type': ' OTHER ', 'contribution': 'own_platform_service',
             'rationale': 'Platform', 'citations': [{'source_id': 'profile', 'quote': 'Example Lab builds an AI platform.'}]},
            {'name': 'Unsupported model', 'type': 'model-llm', 'contribution': 'original_model',
             'rationale': 'Model', 'citations': [{'source_id': 'profile', 'quote': 'We train a language model.'}]},
            {'name': 'Inconsistent', 'type': 'agent', 'contribution': 'own_harness',
             'rationale': 'Tool', 'citations': [{'source_id': 'profile', 'quote': 'Example Lab builds an AI platform.'}]},
        ], 'uncertainties': [],
    }
    original = deepcopy(response)
    recovered, audit = recover_screen(response, evidence)
    assert response == original
    assert [p['name'] for p in recovered['products']] == ['Platform']
    assert recovered['products'][0]['type'] == 'other'
    assert 'product:1:unresolved' in audit
    assert 'product:2:unresolved_category_or_fields' in audit
    assert qualification_decision(recovered, evidence)['outcome'] == 'accepted'
    assert recovered['uncertainties']


def test_unsupported_identity_and_unhashable_category_stay_unresolved():
    evidence = {'sources': [{'id': 'profile', 'text': 'Example Lab builds an AI platform.'}]}
    response = {
        'organization_name': 'Example Lab', 'account_presentation': 'company_account',
        'identity_rationale': 'Company',
        'identity_citations': [{'source_id': 'profile', 'quote': 'This quote is invented.'}],
        'products': [{'name': 'Platform', 'type': ['other'], 'contribution': {},
                      'rationale': 'Platform', 'citations': [{'source_id': [], 'quote': 'Example Lab builds an AI platform.'}]}],
        'uncertainties': [],
    }
    recovered, audit = recover_screen(response, evidence)
    assert recovered['account_presentation'] == 'unclear'
    assert recovered['products'] == []
    assert qualification_decision(recovered, evidence)['outcome'] == 'review_needed'
    assert 'identity:unresolved' in audit


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_evaluator_saves_original_response_and_recovered_decision():
    import json

    from core.models import Account
    from core.official_company_accounts import enqueue_account, evaluate_account
    from x_monitor.config import OfficialCompanyConfig

    account = Account.objects.create(author_id='88120032', handle='examplelab',
                                     bio='Example Lab builds “useful AI” platforms.')
    state = enqueue_account(account)
    saved = {}

    def call(_system, evidence_json, _model, _max_tokens):
        source = json.loads(evidence_json)['sources'][0]
        citation = {'source_id': source['id'], 'quote': source['text'].replace('“', '"').replace('”', '"')}
        response = {
            'organization_name': 'Example Lab', 'account_presentation': 'company_account',
            'identity_rationale': 'Company profile', 'identity_citations': [citation],
            'products': [{'name': 'Platform', 'type': 'other', 'contribution': 'own_platform_service',
                          'rationale': 'Platform', 'citations': [citation]}],
            'uncertainties': [], 'usage': {'input_tokens': 10, 'output_tokens': 10},
        }
        saved.update(deepcopy(response))
        return response

    cfg = OfficialCompanyConfig(enabled=True, max_usd_per_cycle='1', max_usd_per_day='1')
    assert evaluate_account(state.pk, cfg=cfg, call=call, budget_scope='quote-recovery-test')
    state.refresh_from_db()
    attempt = state.attempt_records.get()
    assert attempt.status == 'completed'
    assert attempt.decision['raw_model_response'] == saved
    assert 'identity:recovered_citation' in attempt.decision['recovery_audit']
    assert state.decision['outcome'] == 'accepted'
    assert state.decision['offering_screen']['identity_citations'][0]['quote'] in attempt.evidence['sources'][0]['text']


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_malformed_response_is_saved_with_usage_without_replacing_evidence():
    from core.models import Account
    from core.official_company_accounts import enqueue_account, evaluate_account
    from x_monitor.config import OfficialCompanyConfig

    account = Account.objects.create(author_id='88120033', handle='unknownlab', bio='We build AI tools.')
    state = enqueue_account(account)
    old_evidence = deepcopy(state.evidence)
    response = {'unexpected': ['malformed'], 'usage': {'input_tokens': 10, 'output_tokens': 10}}
    cfg = OfficialCompanyConfig(enabled=True, max_usd_per_cycle='1', max_usd_per_day='1')
    assert evaluate_account(state.pk, cfg=cfg, call=lambda *_: response, budget_scope='invalid-response-test')
    state.refresh_from_db()
    attempt = state.attempt_records.get()
    assert attempt.status == 'failed'
    assert attempt.decision == response
    assert attempt.evidence == old_evidence == state.evidence
    assert state.status == 'review_needed'
