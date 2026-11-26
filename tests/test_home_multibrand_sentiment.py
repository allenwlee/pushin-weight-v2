"""Multi-brand chart eligibility is per Post, including orphan evidence."""
from unittest.mock import patch

import pytest

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.materializations import refresh_materialization
from core.models import (
    Brand,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandSignal,
    PostUnsanctionedFlag,
)
from monitor import home_sentiment_counts
from monitor.each_chart_facts import EACH_FACTS
from monitor.views import _build_home_chart_payload
from tests.test_each_chart_facts import NOW

pytest_plugins = ['tests.test_each_chart_facts']
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.mark.parametrize('selected', [
    ['negative'], ['negative', '__unclassified__'], ['__unclassified__'],
    ['positive', 'mixed'], [],
])
@pytest.mark.parametrize('days', [7, 30, 365])
@pytest.mark.parametrize('promotion,legacy_mode', [('any', 'any'), ('off', None), ('only', 'any')])
def test_multibrand_sentiment_matches_existing_post_filter(fact_brand, selected, days, promotion, legacy_mode):
    other = Brand.objects.create(nickname='other-multi', display_name='Other', accent_color='#120045')
    # One Post is associated with both brands; its classified sentiment differs.
    shared = Post.objects.get(pk='each-facts-3')
    PostBrand.objects.create(post=shared, brand=other)
    PostBrandClassificationState.objects.create(
        post=shared, brand=other, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='b'*64, outcome='classified', sentiment_id='negative',
    )
    # A qualifying classification for Other can exist even when this Post is
    # only associated with the first brand. Existing filters still match it.
    orphan = Post.objects.get(pk='each-facts-5')
    PostBrandClassificationState.objects.create(
        post=orphan, brand_id=other.pk.upper(), contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='c'*64, outcome='classified', sentiment_id='negative',
    )
    # A qualifying legacy signal may likewise lack the matching association.
    legacy = Post.objects.get(pk='each-facts-1')
    PostBrandSignal.objects.create(post=legacy, brand=other, post_type_id='releases_updates', sentiment_id='negative')
    PostUnsanctionedFlag.objects.create(post=legacy, flags='["test"]')
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    assert refresh_materialization(home_sentiment_counts.HOME_SENTIMENT)['status'] == 'refreshed'
    # Historical correction tests the live dirty arm after publication.
    PostBrandClassificationState.objects.filter(post_id='each-facts-5').update(sentiment_id='negative')
    brands=[fact_brand.pk,other.pk]
    filters={'brands':brands, 'sentiment':selected, 'untracked_brand_promotions':promotion}
    if legacy_mode is not None:
        filters['unsanctioned'] = legacy_mode
    projection=[{'nickname':b.pk,'accent_color':b.accent_color} for b in (fact_brand,other)]
    observed = []
    reader = home_sentiment_counts.read_home_multibrand_sentiment_counts

    def capture(**kwargs):
        result = reader(**kwargs)
        observed.append(result)
        return result

    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', side_effect=capture):
        actual=_build_home_chart_payload(days,filters,now=NOW,brand_projection=projection,bucket_timezone='Asia/Tokyo')
    assert len(observed) == 1 and observed[0] is not None
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts',return_value=None):
        expected=_build_home_chart_payload(days,filters,now=NOW,brand_projection=projection,bucket_timezone='Asia/Tokyo')
    assert actual['series']==expected['series']
    assert actual['totals']==expected['totals']


@pytest.mark.parametrize('scope', [None, '__all__'])
@pytest.mark.parametrize('selected', [
    ['negative'], ['negative', '__unclassified__'], ['__unclassified__'],
])
def test_all_brands_includes_hidden_orphan_evidence(fact_brand, scope, selected):
    visible = Brand.objects.create(nickname='visible-scope', accent_color='#001100')
    hidden = Brand.objects.create(nickname='hidden-evidence', accent_color='#002200')
    post = Post.objects.get(pk='each-facts-5')
    PostBrand.objects.create(post=post, brand=visible)
    PostBrandClassificationState.objects.create(
        post=post, brand=hidden, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='d'*64, outcome='classified', sentiment_id='negative',
    )
    assert refresh_materialization(home_sentiment_counts.HOME_SENTIMENT)['status'] == 'refreshed'
    filters = {'sentiment': selected, 'untracked_brand_promotions': 'any'}
    if scope is not None:
        filters['brands'] = scope
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, visible)]
    reader = home_sentiment_counts.read_home_multibrand_sentiment_counts
    observed = []
    def capture(**kwargs):
        result = reader(**kwargs)
        observed.append((kwargs, result))
        return result
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', side_effect=capture):
        actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert len(observed) == 1 and observed[0][0]['brands'] is None and observed[0][1] is not None
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']
    assert actual['totals'][visible.pk] > 0
