"""Bounded historical invalidations must preserve exact chart results."""
from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction

from core.materializations import refresh_materialization
from core.models import MaterializationState, Post, PostBrand
from monitor.each_chart_facts import EACH_FACTS, read_each_fact_groups
from monitor.views import _each_chart_payload, _each_tab_entries
from tests.each_reference import reference_each_chart_payload
from tests.test_each_chart_facts import DATASET, NOW

pytest_plugins = ['tests.test_each_chart_facts']

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_historical_correction_tracks_only_changed_post_and_all_tabs_match(fact_brand):
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=DATASET)
    assert state.dirty_post_ids == []
    Post.objects.filter(pk='each-facts-5').update(lang='ja', lang_detected=None)
    state.refresh_from_db()
    assert state.dirty_post_ids == ['each-facts-5']
    for tab in _each_tab_entries('en'):
        for days in (3, 7, 30, 365):
            options = {'now': NOW, 'bucket_timezone': 'Asia/Tokyo', '_rank': False}
            assert _each_chart_payload(fact_brand.pk, tab, days, 'en', **options) == reference_each_chart_payload(fact_brand.pk, tab, days, 'en', **options)
    # A successful publication atomically discards the old invalidation set.
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    state.refresh_from_db()
    assert state.dirty_post_ids == []


def test_refresh_tracks_new_writes_and_global_invalidation_falls_back(fact_brand):
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=DATASET)
    state.refresh_generation = state.source_generation
    state.refresh_dirty_post_ids = []
    state.save(update_fields=['refresh_generation', 'refresh_dirty_post_ids'])
    Post.objects.filter(pk='each-facts-5').update(lang='ja')
    state.refresh_from_db()
    assert state.dirty_post_ids == ['each-facts-5']
    assert state.refresh_dirty_post_ids == ['each-facts-5']
    with connection.cursor() as cursor:
        cursor.execute('TRUNCATE posts_brands_classification_states')
    state.refresh_from_db()
    assert state.dirty_post_ids is None
    assert state.refresh_dirty_post_ids is None


def test_helper_deduplicates_binary_ids_and_overflow_disables_tracking():
    with connection.cursor() as cursor:
        cursor.execute("SELECT each_dirty_append(ARRAY['a']::text[], 'A'), each_dirty_append(ARRAY['a']::text[], 'a'), each_dirty_append(ARRAY(SELECT i::text FROM generate_series(1,512) i), 'extra'), each_dirty_append(ARRAY[]::text[], repeat('x',257))")
        assert cursor.fetchone() == (['a', 'A'], ['a'], None, None)


def test_overflow_falls_back_and_invalid_arrays_are_rejected(fact_brand):
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    MaterializationState.objects.filter(pk=DATASET).update(dirty_post_ids=[str(i) for i in range(512)])
    Post.objects.filter(pk='each-facts-5').update(lang='ja')
    assert MaterializationState.objects.get(pk=DATASET).dirty_post_ids is None
    options = {'now': NOW, 'bucket_timezone': 'UTC', '_rank': False}
    assert _each_chart_payload(fact_brand.pk, 'lang', 365, 'en', **options) == reference_each_chart_payload(fact_brand.pk, 'lang', 365, 'en', **options)
    for invalid in ([str(i) for i in range(513)], ['x' * 257], [None]):
        with pytest.raises(DatabaseError), transaction.atomic():
            MaterializationState.objects.filter(pk=DATASET).update(dirty_post_ids=invalid)


def test_failed_refresh_keeps_existing_dirty_ids(fact_brand):
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    Post.objects.filter(pk='each-facts-5').update(lang='ja')

    def fail_after_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            raise RuntimeError('simulate failed publication')
        return result

    with connection.execute_wrapper(fail_after_refresh), pytest.raises(RuntimeError):
        refresh_materialization(EACH_FACTS, force=True)
    state = MaterializationState.objects.get(pk=DATASET)
    assert state.dirty_post_ids == ['each-facts-5']
    assert state.refresh_generation is None
    assert state.refresh_dirty_post_ids is None


def test_older_refresher_keeps_safe_superset_during_mixed_versions(fact_brand):
    from dataclasses import replace

    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    Post.objects.filter(pk='each-facts-5').update(lang='ja')
    old_definition = replace(EACH_FACTS, online_dirty_ids_capability=None)
    assert refresh_materialization(old_definition, force=True)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk=DATASET)
    assert state.dirty_post_ids == ['each-facts-5']
    Post.objects.filter(pk='each-facts-4').update(lang='fr')
    state.refresh_from_db()
    assert set(state.dirty_post_ids) == {'each-facts-4', 'each-facts-5'}
    options = {'now': NOW, 'bucket_timezone': 'UTC', '_rank': False}
    assert _each_chart_payload(fact_brand.pk, 'lang', 365, 'en', **options) == reference_each_chart_payload(fact_brand.pk, 'lang', 365, 'en', **options)


def test_removed_brand_and_date_move_remain_exact(fact_brand):
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    PostBrand.objects.filter(post_id='each-facts-3', brand=fact_brand).delete()
    Post.objects.filter(pk='each-facts-5').update(created_at=NOW-timedelta(hours=1))
    state = MaterializationState.objects.get(pk=DATASET)
    assert set(state.dirty_post_ids) == {'each-facts-3', 'each-facts-5'}
    for tab in ('sentiment', 'post_types', 'lang'):
        options = {'now': NOW, 'bucket_timezone': 'UTC', '_rank': False}
        assert _each_chart_payload(fact_brand.pk, tab, 365, 'en', **options) == reference_each_chart_payload(fact_brand.pk, tab, 365, 'en', **options)
    assert read_each_fact_groups(fact_brand.pk, 'lang', NOW-timedelta(days=365), NOW, 'day', 'UTC', NOW)
