"""Summary publication remains exact through dirty writes and refresh races."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from io import StringIO
from threading import Event
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
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
from monitor.each_chart_facts import EACH_FACTS
from monitor.home_sentiment_counts import (
    HOME_CLASSIFICATION,
    HOME_SENTIMENT,
    HOME_SENTIMENT_V1,
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
                     FROM home_post_sentiment_facts_v2 ORDER BY post_id COLLATE "C"''')
        saved = c.fetchall()
        c.execute('SELECT cutoff FROM materialization_state WHERE dataset_key=%s', [HOME_SENTIMENT.dataset_key])
        cutoff = c.fetchone()[0]
        c.execute('''SELECT post_id,created_at,brands,unclassified,positive,negative,neutral,mixed,promotion_flag,legacy_flag
                     FROM home_post_sentiment_facts_source
                     WHERE created_at < %s
                     ORDER BY post_id COLLATE "C"''', [cutoff])
        assert saved == c.fetchall()
    assert saved


def test_recent_publication_boundary_has_no_gap_or_overlap(fact_brand):
    with connection.cursor() as c:
        c.execute(f'SELECT {HOME_SENTIMENT.cutoff_sql}')
        cutoff = c.fetchone()[0]
    moments = {}
    for generation, boundary in enumerate((cutoff, cutoff+timedelta(hours=2))):
        for label, when in (
            ('before', boundary-timedelta(microseconds=1)),
            ('at', boundary),
            ('after', boundary+timedelta(microseconds=1)),
        ):
            post = Post.objects.create(tweet_id=f'recent-cutoff-{generation}-{label}', created_at=when)
            PostBrand.objects.create(post=post, brand=fact_brand)
            moments[post.pk] = when
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    with connection.cursor() as c:
        c.execute('SELECT cutoff FROM materialization_state WHERE dataset_key=%s', [HOME_SENTIMENT.dataset_key])
        cutoff = c.fetchone()[0]
        c.execute("SELECT post_id FROM home_post_sentiment_facts_v2 WHERE post_id LIKE 'recent-cutoff-%'")
        assert {row[0] for row in c.fetchall()} == {key for key, when in moments.items() if when < cutoff}
    now = timezone.now()
    result = read_home_multibrand_sentiment_counts(
        brands=None, output_brands=[fact_brand.pk], sentiments=['__unclassified__'],
        start=cutoff-timedelta(microseconds=1), end=cutoff+timedelta(microseconds=2),
        at=now, timezone_name='UTC',
        promotion_mode='any', legacy_mode='any',
    )
    assert result is not None
    # The three boundary posts remain visible whether read from saved or live facts.
    assert sum(row['count'] for row in result) == 3


def test_overflow_uses_later_safe_v1_prefix_when_available(fact_brand):
    for definition in (HOME_SENTIMENT_V1, HOME_SENTIMENT):
        assert refresh_materialization(definition)['status'] == 'refreshed'
    MaterializationState.objects.filter(pk=HOME_SENTIMENT.dataset_key).update(
        source_generation=_state().source_generation+1,
        dirty_since=timezone.now()-timedelta(days=100), dirty_post_ids=None,
    )
    queries = []
    def capture(execute, sql, params, many, context):
        if sql.lstrip().startswith('WITH cfg AS MATERIALIZED'):
            queries.append(sql)
        return execute(sql, params, many, context)
    now = timezone.now()
    filters = {'brands': '__all__', 'sentiment': ['mixed'], 'untracked_brand_promotions': 'any'}
    projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
    with connection.execute_wrapper(capture):
        actual = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    assert len(queries) == 1 and '"home_post_sentiment_facts" saved' in queries[0]
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']


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
    now = timezone.now()
    other = Brand.objects.create(nickname='flag-other', accent_color='#001100')
    PostBrand.objects.create(post_id='each-facts-5', brand=other)
    Post.objects.filter(pk='each-facts-5').update(created_at=now-timedelta(hours=5))
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
    actual = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']
    assert actual['totals'][other.pk] > 0


def test_recent_saved_correction_invalidates_home_but_not_each(fact_brand):
    now = timezone.now()
    other = Brand.objects.create(nickname='recent-boundary-other', accent_color='#001100')
    post = Post.objects.create(tweet_id='recent-boundary-post', created_at=now-timedelta(hours=5))
    PostBrand.objects.create(post=post, brand=fact_brand)
    PostBrand.objects.create(post=post, brand=other)
    state = PostBrandClassificationState.objects.create(
        post=post, brand=other, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='e'*64, outcome='classified', sentiment_id='mixed',
    )
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
    each_before = MaterializationState.objects.get(pk=EACH_FACTS.dataset_key).source_generation
    state.sentiment_id = 'negative'
    state.save(update_fields=['sentiment'])
    assert MaterializationState.objects.get(pk=EACH_FACTS.dataset_key).source_generation == each_before
    assert _state().dirty_post_ids == [post.pk]
    filters = {'brands': [fact_brand.pk, other.pk], 'sentiment': ['negative'],
               'untracked_brand_promotions': 'any'}
    projection = [{'nickname': b.pk, 'accent_color': b.accent_color} for b in (fact_brand, other)]
    actual = _build_home_chart_payload(7, filters, now=now, brand_projection=projection)
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(7, filters, now=now, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']
    assert actual['totals'][other.pk] > 0


@pytest.mark.parametrize('migration_rehearsal_schema', [('core', '0245_home_sentiment_recent_boundary')], indirect=True)
def test_older_worker_and_reader_are_safe_during_boundary_migration(migration_rehearsal_schema, fact_brand):
    old_definition = HOME_SENTIMENT_V1
    args = {'brands': None, 'output_brands': [fact_brand.pk], 'sentiments': ['mixed'],
            'start': timezone.now()-timedelta(days=365), 'end': timezone.now(),
            'at': timezone.now(), 'timezone_name': 'UTC', 'promotion_mode': 'any', 'legacy_mode': 'any'}
    try:
        MigrationExecutor(connection).migrate([('core', '0244_home_sentiment_masks')])
        output = StringIO()
        call_command('refresh_materializations', stdout=output)
        fallback = json.loads(output.getvalue())[HOME_CLASSIFICATION.dataset_key]
        assert fallback['status'] == 'refreshed' and fallback['fallback_dataset'] == old_definition.dataset_key
        assert read_home_multibrand_sentiment_counts(**args) is not None
        MigrationExecutor(connection).migrate([('core', '0245_home_sentiment_recent_boundary')])
        assert read_home_multibrand_sentiment_counts(**args) is not None
        # An older worker continues refreshing v1 while v2 is unpopulated;
        # the new reader must keep returning exact rows from v1.
        assert refresh_materialization(old_definition, force=True)['status'] == 'refreshed'
        assert _state().published_generation is None
        assert read_home_multibrand_sentiment_counts(**args) is not None
        filters = {'brands': '__all__', 'sentiment': ['mixed'], 'untracked_brand_promotions': 'any'}
        projection = [{'nickname': fact_brand.pk, 'accent_color': fact_brand.accent_color}]
        now = timezone.now()
        actual = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
        with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
            reference = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
        assert actual['series'] == reference['series']
        assert actual['totals'] == reference['totals']
        assert refresh_materialization(HOME_SENTIMENT)['status'] == 'refreshed'
        assert _state().published_generation is not None
        queries = []
        def capture(execute, sql, params, many, context):
            if sql.lstrip().startswith('WITH cfg AS MATERIALIZED'):
                queries.append(sql)
            return execute(sql, params, many, context)
        with connection.execute_wrapper(capture):
            assert read_home_multibrand_sentiment_counts(**args) is not None
        assert len(queries) == 1 and '"home_post_sentiment_facts_v2" saved' in queries[0]
    finally:
        MigrationExecutor(connection).migrate([('core', '0245_home_sentiment_recent_boundary')])


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
    now = timezone.now()
    other = Brand.objects.create(nickname='concurrent-other', accent_color='#001100')
    post = Post.objects.get(pk='each-facts-5')
    post.created_at = now - timedelta(hours=5)
    post.save(update_fields=['created_at'])
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
        actual = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    assert len(observed) == 1 and observed[0] is not None
    with patch('monitor.home_sentiment_counts.read_home_multibrand_sentiment_counts', return_value=None):
        reference = _build_home_chart_payload(365, filters, now=now, brand_projection=projection)
    assert actual['series'] == reference['series']
    assert actual['totals'] == reference['totals']
    assert any(actual['totals'].values())


def test_mixed_age_transactions_lock_publication_rows_in_one_order(fact_brand):
    now = timezone.now()
    recent = Post.objects.create(tweet_id='mixed-age-recent', created_at=now-timedelta(hours=5))
    PostBrand.objects.create(post=recent, brand=fact_brand)
    PostBrandClassificationState.objects.create(
        post=recent, brand=fact_brand, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version='fixture', model='fixture',
        input_context_fingerprint='f'*64, outcome='classified', sentiment_id='mixed',
    )
    for definition in (EACH_FACTS, HOME_SENTIMENT_V1, HOME_SENTIMENT):
        assert refresh_materialization(definition)['status'] == 'refreshed'
    recent_locked, old_started = Event(), Event()
    pids = {}

    def newer_then_older():
        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    c.execute('SELECT pg_backend_pid()')
                    pids['recent'] = c.fetchone()[0]
                PostBrandClassificationState.objects.filter(post=recent, brand=fact_brand).update(sentiment_id='negative')
                recent_locked.set()
                assert old_started.wait(5)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with connection.cursor() as c:
                        c.execute('SELECT pg_blocking_pids(%s)', [pids['old']])
                        if pids['recent'] in c.fetchone()[0]:
                            break
                    time.sleep(0.02)
                else:
                    raise AssertionError('older writer never blocked behind recent writer')
                PostBrandClassificationState.objects.filter(post_id='each-facts-4', brand=fact_brand).update(sentiment_id='negative')
        finally:
            connections['default'].close()

    def older():
        try:
            assert recent_locked.wait(5)
            with transaction.atomic():
                with connection.cursor() as c:
                    c.execute('SELECT pg_backend_pid()')
                    pids['old'] = c.fetchone()[0]
                old_started.set()
                PostBrandClassificationState.objects.filter(post_id='each-facts-5', brand=fact_brand).update(sentiment_id='negative')
        finally:
            connections['default'].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(newer_then_older)
        second = pool.submit(older)
        first.result(timeout=10)
        second.result(timeout=10)
    for definition, expected in (
        (EACH_FACTS, {'each-facts-4', 'each-facts-5'}),
        (HOME_SENTIMENT_V1, {'each-facts-4', 'each-facts-5'}),
        (HOME_SENTIMENT, {'mixed-age-recent', 'each-facts-4', 'each-facts-5'}),
    ):
        assert set(MaterializationState.objects.get(pk=definition.dataset_key).dirty_post_ids) == expected


@pytest.mark.parametrize('migration_rehearsal_schema', [('core', '0245_home_sentiment_recent_boundary')], indirect=True)
def test_boundary_migration_refuses_an_active_state_snapshot(migration_rehearsal_schema):
    with connection.cursor() as c:
        c.execute("SELECT current_setting('search_path')")
        search_path = c.fetchone()[0]

    def attempt(target):
        try:
            with connections['default'].cursor() as c:
                c.execute("SELECT set_config('search_path', %s, false)", [search_path])
            MigrationExecutor(connections['default']).migrate([('core', target)])
        except DatabaseError as error:
            return sqlstate(error)
        finally:
            connections['default'].close()
        return None

    try:
        with connection.cursor() as c:
            c.execute('SELECT pg_advisory_lock(%s)', [HOME_SENTIMENT.lock_id])
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(attempt, '0244_home_sentiment_masks').result(timeout=5) == '55P03'
        finally:
            with connection.cursor() as c:
                c.execute('SELECT pg_advisory_unlock(%s)', [HOME_SENTIMENT.lock_id])
        with transaction.atomic(), connection.cursor() as c:
            c.execute('SELECT dataset_key FROM materialization_state LIMIT 1')
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(attempt, '0244_home_sentiment_masks').result(timeout=5) == '55P03'
        MigrationExecutor(connection).migrate([('core', '0244_home_sentiment_masks')])
        with transaction.atomic(), connection.cursor() as c:
            c.execute('SELECT dataset_key FROM materialization_state LIMIT 1')
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(attempt, '0245_home_sentiment_recent_boundary').result(timeout=5) == '55P03'
    finally:
        MigrationExecutor(connection).migrate([('core', '0245_home_sentiment_recent_boundary')])


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
