"""Homepage classification selections retain the complete chart semantics."""
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.materializations import refresh_materialization
from core.models import Brand, Post, PostBrand, PostBrandClassificationState, PostBrandSignal
from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from monitor import home_sentiment_counts
from monitor.each_chart_facts import EACH_FACTS
from monitor.views import _build_home_chart_payload
from tests.test_each_chart_facts import NOW

pytest_plugins = ['tests.test_each_chart_facts']
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.mark.parametrize('days', [7, 30, 365])
@pytest.mark.parametrize('selection', [
    {'post_types': ['releases_updates']},
    {'post_types': ['hands_on_usage', '__unclassified__']},
    {'product_labels': ['ideas_requests', '__no_product_signal__']},
    {'product_labels': ['__unclassified__']},
    {'post_types': ['releases_updates', '__unclassified__'],
     'product_labels': ['ideas_requests', '__no_product_signal__'],
     'sentiment': ['mixed', '__unclassified__']},
])
def test_classification_matches_reference_across_windows(fact_brand, days, selection):
    other = Brand.objects.create(nickname='classification-other', accent_color='#135790')
    shared = Post.objects.get(pk='each-facts-3')
    PostBrand.objects.create(post=shared, brand=other)
    PostBrandClassificationState.objects.create(
        post=shared, brand=other, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='e'*64, outcome='classified', sentiment_id='mixed',
    )
    PostBrandSignal.objects.create(post=shared, brand=other, post_type_id='releases_updates', sentiment_id='mixed')
    # State and signals can qualify a post without a matching association.
    orphan = Post.objects.get(pk='each-facts-5')
    PostBrandClassificationState.objects.create(
        post=orphan, brand=other, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='f'*64, outcome='classified', sentiment_id='mixed',
    )
    PostBrandSignal.objects.create(post=orphan, brand=other, post_type_id='releases_updates', sentiment_id='mixed')
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    assert refresh_materialization(home_sentiment_counts.HOME_SENTIMENT)['status'] == 'refreshed'
    assert refresh_materialization(home_sentiment_counts.HOME_CLASSIFICATION)['status'] == 'refreshed'
    filters = {'brands': [fact_brand.pk, other.pk], 'untracked_brand_promotions': 'any', **selection}
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, other)]
    reader = home_sentiment_counts.read_home_multibrand_sentiment_counts
    observed = []

    def capture(**kwargs):
        result = reader(**kwargs)
        observed.append(result)
        return result

    with CaptureQueriesContext(connection) as queries, patch.object(
        home_sentiment_counts, 'read_home_multibrand_sentiment_counts', side_effect=capture
    ):
        actual = _build_home_chart_payload(days, filters, now=NOW, brand_projection=projection,
                                           bucket_timezone='Asia/Tokyo')
    assert len(observed) == 1 and observed[0] is not None, 'classification reader was not used'
    assert any('"home_post_classification_facts" saved' in query['sql'] for query in queries)
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(days, filters, now=NOW, brand_projection=projection,
                                             bucket_timezone='Asia/Tokyo')
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']

@pytest.mark.parametrize('scope', [None, '__all__', 'one', 'many'])
def test_live_type_and_product_changes_match_reference(fact_brand, scope):
    from core.models import PostBrandProductLabel

    other = Brand.objects.create(nickname='classification-live', accent_color='#246801')
    historical = Post.objects.get(pk='each-facts-5')
    PostBrand.objects.create(post=historical, brand=other)
    PostBrandClassificationState.objects.create(
        post=historical, brand=other, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='1'*64, outcome='classified', sentiment_id='mixed',
    )
    PostBrandSignal.objects.create(post=historical, brand=other,
                                   post_type_id='releases_updates', sentiment_id='mixed')
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    assert refresh_materialization(home_sentiment_counts.HOME_SENTIMENT)['status'] == 'refreshed'
    assert refresh_materialization(home_sentiment_counts.HOME_CLASSIFICATION)['status'] == 'refreshed'
    # Both changes occur after publication, and type-only updates need not mark
    # the sentiment projection dirty. The reader must still see live evidence.
    PostBrandSignal.objects.filter(post=historical, brand=other).update(post_type_id='performance_comparisons')
    PostBrandProductLabel.objects.create(post=historical, brand=other, product_label_id='ideas_requests')
    filters = {'untracked_brand_promotions': 'any',
               'post_types': ['hands_on_usage', '__unclassified__'],
               'product_labels': ['ideas_requests', '__no_product_signal__']}
    if scope is not None:
        filters['brands'] = {'__all__': '__all__', 'one': [other.pk],
                             'many': [fact_brand.pk, other.pk]}[scope]
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, other)]
    reader = home_sentiment_counts.read_home_multibrand_sentiment_counts
    observed = []

    def capture(**kwargs):
        result = reader(**kwargs)
        observed.append(result)
        return result

    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', side_effect=capture):
        with CaptureQueriesContext(connection) as queries:
            actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
        assert any('"home_post_classification_facts" saved' in q['sql'] for q in queries)
    assert len(observed) == 1 and observed[0] is not None
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']


def test_saved_classification_projection_matches_live_source_and_tracks_changes(fact_brand):
    from core.models import MaterializationState, PostBrandProductLabel

    definition = home_sentiment_counts.HOME_CLASSIFICATION
    assert refresh_materialization(definition)['status'] == 'refreshed'
    fields = home_sentiment_counts._CLASS_FIELDS
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {fields} FROM home_post_classification_facts ORDER BY post_id COLLATE "C"')
        saved = cursor.fetchall()
        cutoff = MaterializationState.objects.get(pk=definition.dataset_key).cutoff
        cursor.execute(f'SELECT {fields} FROM home_post_classification_facts_source '
                       'WHERE created_at < %s ORDER BY post_id COLLATE "C"', [cutoff])
        assert saved == cursor.fetchall()
    assert saved
    post = Post.objects.get(pk='each-facts-5')
    PostBrandSignal.objects.filter(post=post, brand=fact_brand, post_type_id='performance_comparisons').update(
        post_type_id='releases_updates'
    )
    state = MaterializationState.objects.get(pk=definition.dataset_key)
    assert post.pk in state.dirty_post_ids
    assert refresh_materialization(definition, force=True)['status'] == 'refreshed'
    PostBrandProductLabel.objects.create(post=post, brand=fact_brand, product_label_id='ideas_requests')
    assert post.pk in MaterializationState.objects.get(pk=definition.dataset_key).dirty_post_ids


@pytest.mark.parametrize('migration_rehearsal_schema', [('core', '0246_home_classification_masks')], indirect=True)
def test_classification_projection_rolling_upgrade_and_rollback(migration_rehearsal_schema, fact_brand):
    from django.db.migrations.executor import MigrationExecutor
    from django.utils import timezone
    from datetime import timedelta

    definition = home_sentiment_counts.HOME_CLASSIFICATION
    old = home_sentiment_counts.HOME_SENTIMENT
    args = {'brands': [fact_brand.pk], 'output_brands': [fact_brand.pk], 'sentiments': None,
            'post_types': ['releases_updates', '__unclassified__'],
            'start': timezone.now()-timedelta(days=365), 'end': timezone.now(), 'at': timezone.now(),
            'timezone_name': 'UTC', 'promotion_mode': 'any', 'legacy_mode': 'any'}
    assert refresh_materialization(old, force=True)['status'] == 'refreshed'
    assert refresh_materialization(definition, force=True)['status'] == 'refreshed'
    expected = home_sentiment_counts.read_home_multibrand_sentiment_counts(**args)
    assert expected is not None
    MigrationExecutor(connection).migrate([('core', '0245_home_sentiment_recent_boundary')])
    try:
        assert refresh_materialization(definition, force=True)['status'] == 'unavailable'
        assert home_sentiment_counts.read_home_multibrand_sentiment_counts(**args) == expected
    finally:
        MigrationExecutor(connection).migrate([('core', '0246_home_classification_masks')])
    # Unpopulated v3 must continue using v2 until its first complete publication.
    assert home_sentiment_counts.read_home_multibrand_sentiment_counts(**args) == expected
    assert refresh_materialization(definition, force=True)['status'] == 'refreshed'
    assert home_sentiment_counts.read_home_multibrand_sentiment_counts(**args) == expected


def test_post_type_write_during_v3_refresh_stays_visible(fact_brand):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from django.db import connections
    from django.utils import timezone
    from core.models import MaterializationState

    now = timezone.now()
    post = Post.objects.get(pk='each-facts-5')
    Post.objects.filter(pk=post.pk).update(created_at=now-timedelta(hours=5))
    definition = home_sentiment_counts.HOME_CLASSIFICATION
    assert refresh_materialization(definition)['status'] == 'refreshed'

    def write():
        try:
            PostBrandSignal.objects.filter(post=post, brand=fact_brand,
                                           post_type_id='performance_comparisons').update(
                post_type_id='releases_updates'
            )
        finally:
            connections['default'].close()

    def after_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write).result(timeout=5)
        return result

    with connection.execute_wrapper(after_refresh):
        assert refresh_materialization(definition, force=True)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=definition.dataset_key)
    assert state.source_generation > state.published_generation
    assert state.dirty_post_ids == [post.pk]
    filters = {'brands': [fact_brand.pk], 'post_types': ['releases_updates'],
               'untracked_brand_promotions': 'any'}
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    actual = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']
    assert actual['totals'][fact_brand.pk] > 0


@pytest.mark.parametrize('scope', [None, '__all__', 'visible'])
def test_hidden_orphan_evidence_obeys_brand_scope(fact_brand, scope):
    from core.models import PostBrandProductLabel

    hidden = Brand.objects.create(nickname='classification-hidden', accent_color='#102030')
    post = Post.objects.get(pk='each-facts-5')
    PostBrandClassificationState.objects.create(
        post=post, brand=hidden, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='2'*64, outcome='classified', sentiment_id='mixed',
    )
    PostBrandSignal.objects.create(post=post, brand=hidden, post_type_id='releases_updates', sentiment_id='mixed')
    PostBrandProductLabel.objects.create(post=post, brand=hidden, product_label_id='ideas_requests')
    assert refresh_materialization(home_sentiment_counts.HOME_CLASSIFICATION)['status'] == 'refreshed'
    filters = {'post_types': ['releases_updates'], 'product_labels': ['ideas_requests'],
               'untracked_brand_promotions': 'any'}
    if scope is not None:
        filters['brands'] = '__all__' if scope == '__all__' else [fact_brand.pk]
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']
    PostBrandProductLabel.objects.filter(post=post, brand=hidden).delete()
    after = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    expected_difference = 0 if scope == 'visible' else 1
    assert actual['totals'][fact_brand.pk] - after['totals'][fact_brand.pk] == expected_difference


def test_sentiment_only_uses_small_live_tail_with_v3(fact_brand):
    assert refresh_materialization(home_sentiment_counts.HOME_CLASSIFICATION)['status'] == 'refreshed'
    filters = {'brands': '__all__', 'sentiment': ['mixed'], 'untracked_brand_promotions': 'any'}
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    with CaptureQueriesContext(connection) as queries:
        actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    chart_sql = [q['sql'] for q in queries if q['sql'].lstrip().startswith('WITH cfg AS MATERIALIZED')]
    assert len(chart_sql) == 1
    assert '"home_post_classification_facts" saved' in chart_sql[0]
    assert 'home_post_sentiment_facts_source' in chart_sql[0]
    assert 'home_post_classification_facts_source' not in chart_sql[0]
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']


def test_v3_overflow_uses_later_exact_v2_prefix(fact_brand):
    from datetime import timedelta
    from core.models import MaterializationState

    for definition in (home_sentiment_counts.HOME_SENTIMENT, home_sentiment_counts.HOME_CLASSIFICATION):
        assert refresh_materialization(definition)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=home_sentiment_counts.HOME_CLASSIFICATION.dataset_key)
    MaterializationState.objects.filter(pk=state.pk).update(
        source_generation=state.source_generation+1, dirty_since=NOW-timedelta(days=200), dirty_post_ids=None,
    )
    filters = {'brands': '__all__', 'sentiment': ['mixed'], 'untracked_brand_promotions': 'any'}
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    with CaptureQueriesContext(connection) as queries:
        actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert any('"home_post_sentiment_facts_v2" saved' in q['sql'] for q in queries)
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']


def test_classification_overflow_keeps_v3_prefix_when_v2_is_newer(fact_brand):
    from datetime import timedelta
    from core.models import MaterializationState

    for definition in (home_sentiment_counts.HOME_SENTIMENT, home_sentiment_counts.HOME_CLASSIFICATION):
        assert refresh_materialization(definition)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=home_sentiment_counts.HOME_CLASSIFICATION.dataset_key)
    MaterializationState.objects.filter(pk=state.pk).update(
        source_generation=state.source_generation+1, dirty_since=NOW-timedelta(days=200), dirty_post_ids=None,
    )
    filters = {'brands': '__all__', 'post_types': ['releases_updates', '__unclassified__'],
               'untracked_brand_promotions': 'any'}
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    with CaptureQueriesContext(connection) as queries:
        actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert any('"home_post_classification_facts" saved' in q['sql'] for q in queries)
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
    assert actual['series'] == expected['series']
    assert actual['totals'] == expected['totals']


def test_independent_classification_axes_respect_scope_and_live_changes(fact_brand):
    from datetime import timedelta
    from core.models import PostBrandProductLabel, PostUnsanctionedFlag

    first = Brand.objects.create(nickname='classification-axis-a', accent_color='#123400')
    second = Brand.objects.create(nickname='classification-axis-b', accent_color='#001234')
    post = Post.objects.create(tweet_id='classification-cross-axis', created_at=NOW-timedelta(days=3))
    for brand in (first, second):
        PostBrand.objects.create(post=post, brand=brand)
        PostBrandClassificationState.objects.create(
            post=post, brand=brand, contract_version=CONTRACT_VERSION, taxonomy_version=TAXONOMY_VERSION,
            prompt_version='fixture', model='fixture', input_context_fingerprint='3'*64,
            outcome='classified', sentiment_id='mixed',
        )
    PostBrandSignal.objects.create(post=post, brand=first, post_type_id='releases_updates', sentiment_id='mixed')
    label = PostBrandProductLabel.objects.create(post=post, brand=second, product_label_id='ideas_requests')
    PostUnsanctionedFlag.objects.create(post=post, flags='[]')
    assert refresh_materialization(home_sentiment_counts.HOME_CLASSIFICATION)['status'] == 'refreshed'
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (first, second)]

    def chart(brands, legacy):
        filters = {'brands': brands, 'post_types': ['releases_updates'], 'product_labels': ['ideas_requests'],
                   'untracked_brand_promotions': 'any', 'unsanctioned': legacy}
        with CaptureQueriesContext(connection) as queries:
            actual = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
        assert any('"home_post_classification_facts" saved' in q['sql'] for q in queries)
        with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
            expected = _build_home_chart_payload(365, filters, now=NOW, brand_projection=projection)
        assert actual['series'] == expected['series']
        assert actual['totals'] == expected['totals']
        return actual['totals']

    assert chart([first.pk, second.pk], 'only') == {first.pk: 1, second.pk: 1}
    assert sum(chart([first.pk], 'only').values()) == 0
    assert sum(chart([second.pk], 'only').values()) == 0
    assert sum(chart([first.pk, second.pk], 'off').values()) == 0
    label.delete()
    assert sum(chart([first.pk, second.pk], 'only').values()) == 0


@pytest.mark.parametrize('selection', [
    {'post_types': ['releases_updates', '__unclassified__']},
    {'sentiment': ['mixed', 'negative', 'neutral', '__unclassified__']},
    {'product_labels': ['ideas_requests']},
    {'product_labels': ['ideas_requests', '__no_product_signal__', '__unclassified__']},
    {'post_types': ['releases_updates', '__unclassified__'],
     'product_labels': ['ideas_requests', '__no_product_signal__', '__unclassified__']},
])
@pytest.mark.parametrize('scope', ['scoped', 'all'])
@pytest.mark.parametrize('sort', ['created_at', 'like_count'])
def test_bounded_classification_feed_preserves_membership_and_pagination(fact_brand, selection, scope, sort):
    from monitor import views
    from core.models import PostBrandProductLabel

    for post_id in ('each-facts-1', 'each-facts-5'):
        PostBrandProductLabel.objects.create(post_id=post_id, brand=fact_brand, product_label_id='ideas_requests')

    filters = {'brands': [fact_brand.pk] if scope == 'scoped' else '__all__',
               'untracked_brand_promotions': 'any', **selection}
    original_filter = views._filter_home_posts_queryset

    def pages():
        cursor, ids = None, []
        for _ in range(10):
            posts, cursor, more, _ = views._feed_page_posts(
                window_days=365, filters=filters, sort=sort, order='desc',
                cursor=cursor, limit=2, now=NOW,
            )
            ids.extend(post.pk for post in posts)
            if not more:
                break
        else:
            pytest.fail('feed pagination did not terminate')
        return ids

    with CaptureQueriesContext(connection) as queries:
        actual = pages()
    bounded_sql = next(query['sql'] for query in queries if 'FROM "posts"' in query['sql'] and 'LIMIT' in query['sql'])
    assert len(actual) > 2 and len(actual) == len(set(actual))

    def reference(*args, **kwargs):
        kwargs['bounded_feed'] = False
        return original_filter(*args, **kwargs)

    with CaptureQueriesContext(connection) as reference_queries, patch.object(
        views, '_filter_home_posts_queryset', side_effect=reference
    ):
        assert pages() == actual
    reference_sql = next(query['sql'] for query in reference_queries
                         if 'FROM "posts"' in query['sql'] and 'LIMIT' in query['sql'])
    if sort == 'created_at':
        assert bounded_sql.count('OFFSET 0') > reference_sql.count('OFFSET 0')
    else:
        assert bounded_sql.count('OFFSET 0') == reference_sql.count('OFFSET 0')
    if 'post_types' in selection:
        assert 'posts_brands_signals' in bounded_sql
    if 'product_labels' in selection:
        assert 'posts_brands_product_labels' in bounded_sql
    if 'sentiment' in selection:
        assert 'posts_brands_classification_states' in bounded_sql


def test_last_product_label_deleted_during_v3_refresh_becomes_no_signal(fact_brand):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from django.db import connections
    from django.utils import timezone
    from core.models import MaterializationState, PostBrandProductLabel

    now = timezone.now()
    post = Post.objects.get(pk='each-facts-0')
    Post.objects.filter(pk=post.pk).update(created_at=now-timedelta(hours=5))
    PostBrandProductLabel.objects.filter(post=post, brand=fact_brand).exclude(product_label_id='ideas_requests').delete()
    definition = home_sentiment_counts.HOME_CLASSIFICATION
    assert refresh_materialization(definition)['status'] == 'refreshed'

    def write():
        try:
            PostBrandProductLabel.objects.filter(post=post, brand=fact_brand).delete()
        finally:
            connections['default'].close()

    def after_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write).result(timeout=5)
        return result

    with connection.execute_wrapper(after_refresh):
        assert refresh_materialization(definition, force=True)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=definition.dataset_key)
    assert state.source_generation > state.published_generation and state.dirty_post_ids == [post.pk]
    filters = {'brands': [fact_brand.pk], 'product_labels': ['__no_product_signal__'],
               'untracked_brand_promotions': 'any'}
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    with CaptureQueriesContext(connection) as queries:
        actual = _build_home_chart_payload(7, filters, now=now, brand_projection=projection)
    assert any('"home_post_classification_facts" saved' in q['sql'] for q in queries)
    with patch.object(home_sentiment_counts, 'read_home_multibrand_sentiment_counts', return_value=None):
        expected = _build_home_chart_payload(7, filters, now=now, brand_projection=projection)
    assert actual['series'] == expected['series'] and actual['totals'] == expected['totals']
    assert actual['totals'][fact_brand.pk] > 0


@pytest.mark.parametrize('selection', [
    {'post_types': ['releases_updates']},
    {'product_labels': ['ideas_requests']},
])
def test_bounded_classification_feed_handles_unknown_brand(fact_brand, selection):
    import re
    from monitor.views import _feed_page_posts

    with CaptureQueriesContext(connection) as queries:
        posts, cursor, more, _ = _feed_page_posts(
            window_days=7,
            filters={'brands': ['brand-does-not-exist'], 'untracked_brand_promotions': 'any', **selection},
            sort='created_at', order='desc', cursor=None, limit=20, now=NOW,
        )
    assert posts == [] and cursor is None and more is False
    query = next(q['sql'] for q in queries if 'FROM "posts"' in q['sql'] and 'LIMIT' in q['sql'])
    brand = re.search(r'EXISTS\(SELECT 1 AS "a" FROM "posts_brands" U0 .*? LIMIT 1( OFFSET 0)?\)', query)
    assert brand and brand.group(1) is None, 'brand membership must remain planner-optimizable'
    assert 'LIMIT 1 OFFSET 0' in query, 'classification evidence must stay bounded'
