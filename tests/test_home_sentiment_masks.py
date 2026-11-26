"""Summary publication remains exact through dirty writes and refresh races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, connections, transaction

from core.materializations import refresh_materialization, sqlstate
from core.models import (
    Brand,
    MaterializationState,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandProductLabel,
    PostUnsanctionedFlag,
)
from monitor.home_sentiment_counts import (
    HOME_SENTIMENT,
    read_home_multibrand_sentiment_counts,
)
from monitor.views import _build_home_chart_payload
from tests.test_each_chart_facts import NOW

pytest_plugins = ['tests.test_each_chart_facts']
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def _state():
    return MaterializationState.objects.get(pk=HOME_SENTIMENT.dataset_key)


def test_saved_masks_equal_live_source_for_historical_posts(fact_brand):
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    with connection.cursor() as c:
        c.execute('''SELECT post_id,created_at,brands,unclassified,positive,negative,neutral,mixed,promotion_flag,legacy_flag
                     FROM home_post_sentiment_facts ORDER BY post_id COLLATE "C"''')
        saved = c.fetchall()
        c.execute('''SELECT post_id,created_at,brands,unclassified,positive,negative,neutral,mixed,promotion_flag,legacy_flag
                     FROM home_post_sentiment_facts_source
                     WHERE created_at < date_trunc('day',transaction_timestamp(),'UTC')-interval '1 day'
                     ORDER BY post_id COLLATE "C"''')
        assert saved == c.fetchall()
    assert saved


def test_bounded_dirty_defers_rebuild_but_overflow_and_forced_refresh_rebuild(fact_brand):
    other = Brand.objects.create(nickname='overflow-other', accent_color='#001100')
    PostBrand.objects.create(post_id='each-facts-5', brand=other)
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    PostBrandClassificationState.objects.filter(post_id='each-facts-5').update(sentiment_id='negative')
    state = _state()
    assert state.dirty_post_ids == ['each-facts-5']
    deferred = refresh_materialization(HOME_SENTIMENT)
    assert deferred['status'] == 'skipped' and deferred['reason'] == 'bounded_dirty'
    assert _state().dirty_post_ids == ['each-facts-5']
    assert refresh_materialization(HOME_SENTIMENT, force=True)['status'] == 'refreshed'
    assert _state().dirty_post_ids == []
    MaterializationState.objects.filter(pk=HOME_SENTIMENT.dataset_key).update(
        source_generation=_state().source_generation + 1,
        dirty_post_ids=[f'threshold-{i}' for i in range(383)],
        dirty_since=NOW - timedelta(days=200),
    )
    assert refresh_materialization(HOME_SENTIMENT)['reason'] == 'bounded_dirty'
    MaterializationState.objects.filter(pk=HOME_SENTIMENT.dataset_key).update(
        dirty_post_ids=[f'threshold-{i}' for i in range(384)],
    )
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    MaterializationState.objects.filter(pk=HOME_SENTIMENT.dataset_key).update(dirty_post_ids=[str(i) for i in range(512)])
    PostBrandClassificationState.objects.filter(post_id='each-facts-5').update(sentiment_id='positive')
    assert _state().dirty_post_ids is None
    filters = {'brands': [fact_brand.pk, other.pk], 'sentiment': ['positive'],
               'untracked_brand_promotions': 'any'}
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, other)]
    observed = []
    def capture(**kwargs):
        result = read_home_multibrand_sentiment_counts(**kwargs)
        observed.append(result)
        return result
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', side_effect=capture):
        actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert len(observed) == 1 and observed[0] is not None
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']
    assert actual['totals'][other.pk] > 0
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    assert _state().dirty_post_ids == []


def test_only_relevant_source_changes_invalidate_summary(fact_brand):
    other = Brand.objects.create(nickname='flag-other', accent_color='#001100')
    PostBrand.objects.create(post_id='each-facts-5', brand=other)
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    before = _state().source_generation
    Post.objects.filter(pk='each-facts-5').update(lang='fr')
    PostBrandProductLabel.objects.create(post_id='each-facts-5', brand=fact_brand, product_label_id='bug')
    assert _state().source_generation == before
    flag = PostUnsanctionedFlag.objects.create(post_id='each-facts-5', flags='[]')
    assert _state().dirty_post_ids == ['each-facts-5']
    assert refresh_materialization(HOME_SENTIMENT, force=True)['status'] == 'refreshed'
    assert _state().dirty_post_ids == []
    flag.delete()
    assert _state().dirty_post_ids == ['each-facts-5']
    filters = {'brands': [fact_brand.pk, other.pk], 'sentiment': ['__unclassified__'],
               'untracked_brand_promotions': 'any', 'unsanctioned': 'off'}
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, other)]
    actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']
    assert actual['totals'][other.pk] > 0


def test_reader_falls_back_when_projection_or_contract_is_unavailable(fact_brand):
    args = {'brands': [fact_brand.pk, 'other'], 'output_brands': [fact_brand.pk], 'sentiments': ['positive'],
                'start': NOW-timedelta(days=30), 'end': NOW, 'at': NOW, 'timezone_name': 'UTC',
                'promotion_mode': 'any', 'legacy_mode': 'any'}
    assert read_home_multibrand_sentiment_counts(**args) is None
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    with patch('monitor.home_sentiment_counts.CONTRACT_VERSION', 'future-contract'):
        assert read_home_multibrand_sentiment_counts(**args) is None
    assert read_home_multibrand_sentiment_counts(**(args | {'sentiments': ['future-sentiment']})) is None


def test_write_during_refresh_remains_dirty_and_chart_matches_source(fact_brand):
    other = Brand.objects.create(nickname='concurrent-other', accent_color='#001100')
    post = Post.objects.get(pk='each-facts-5')
    PostBrand.objects.create(post=post, brand=other)
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'

    def write():
        try:
            PostBrandClassificationState.objects.filter(post=post, brand=fact_brand).update(sentiment_id='negative')
        finally:
            connections['default'].close()

    def after_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write).result(timeout=5)
        return result

    with connection.execute_wrapper(after_refresh):
        assert refresh_materialization(HOME_SENTIMENT, force=True)['status'] == 'refreshed'
    state = _state()
    assert state.source_generation > state.published_generation
    assert state.dirty_post_ids == [post.pk]
    # A duplicated tracked ID must neither duplicate nor drop the changed Post.
    MaterializationState.objects.filter(pk=HOME_SENTIMENT.dataset_key).update(
        dirty_post_ids=[post.pk, post.pk]
    )
    filters = {'brands': [fact_brand.pk, other.pk], 'sentiment': ['negative'], 'untracked_brand_promotions': 'any'}
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, other)]
    observed = []
    def capture(**kwargs):
        result = read_home_multibrand_sentiment_counts(**kwargs)
        observed.append(result)
        return result
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', side_effect=capture):
        actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert len(observed) == 1 and observed[0] is not None
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']
    assert any(actual['totals'].values())


def test_reverse_guard_rejects_an_active_summary_refresh():
    migration = import_module('core.migrations.0244_home_sentiment_masks')
    def attempt():
        try:
            with transaction.atomic(), connections['default'].cursor() as c:
                c.execute(migration._GUARD)
        except DatabaseError as error:
            return sqlstate(error)
        finally:
            connections['default'].close()
        return None

    with connection.cursor() as c:
        c.execute('SELECT pg_advisory_lock(%s)', [HOME_SENTIMENT.lock_id])
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(attempt).result(timeout=5) == '55P03'
    finally:
        with connection.cursor() as c:
            c.execute('SELECT pg_advisory_unlock(%s)', [HOME_SENTIMENT.lock_id])
