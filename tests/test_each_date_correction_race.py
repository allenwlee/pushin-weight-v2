"""A child writer must invalidate the parent's committed historical date."""
from datetime import timedelta
from threading import Event, Thread

import psycopg
import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from core.materializations import refresh_materialization
from core.models import (
    Brand,
    MaterializationState,
    Post,
    PostBrand,
    PostBrandProductLabel,
    ProductLabelKey,
)
from monitor.each_chart_facts import EACH_FACTS


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_child_writer_sees_concurrent_recent_to_history_date_correction(monkeypatch):
    from dataclasses import replace

    # The writer is intentionally held until the refresh returns busy.
    # Keep the production retry budget from outlasting the test writer.
    monkeypatch.setattr('core.materializations._ONLINE_BARRIER_ATTEMPTS', 2)
    monkeypatch.setattr('core.materializations._ONLINE_BARRIER_RETRY_SECONDS', 0.1)
    definition = replace(EACH_FACTS, online_barrier_attempts=2)
    assert connection.settings_dict['NAME'].startswith('test_')
    brand = Brand.objects.create(nickname='each-date-race')
    post = Post.objects.create(tweet_id='each-date-race', created_at=timezone.now())
    PostBrand.objects.create(post=post, brand=brand)
    ProductLabelKey.objects.get_or_create(key='bug')
    MaterializationState.objects.get_or_create(pk='each.brand_post_facts.v1')
    assert refresh_materialization(definition)["status"] == "refreshed"
    historical = timezone.now()-timedelta(days=5)
    config = connection.settings_dict
    parent = psycopg.connect(dbname=config['NAME'], host=config['HOST'], port=config['PORT'],
                             user=config['USER'], password=config['PASSWORD'])
    parent.execute("SET LOCAL statement_timeout='3s'")
    parent.execute('UPDATE posts SET created_at=%s WHERE tweet_id=%s', [historical, post.pk])
    inserted, release = Event(), Event()
    errors = []

    def write_child():
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout='3s'")
                PostBrandProductLabel.objects.create(post_id=post.pk, brand_id=brand.pk, product_label_id='bug')
                inserted.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release child commit')
        except Exception as error:  # noqa: BLE001 -- forward thread failures to the test.
            errors.append(error)
        finally:
            connection.close()

    child = Thread(target=write_child)
    child.start()
    try:
        # The broken trigger returns using the old recent timestamp. A safe
        # trigger waits for the correction; both schedules commit child last.
        inserted.wait(1)
        parent.commit()
        assert inserted.wait(2)
        publication = refresh_materialization(definition)
        release.set()
        child.join(timeout=4)
        assert not child.is_alive()
        assert not errors, errors
        if publication["status"] == "refreshed":
            with connection.cursor() as cursor:
                cursor.execute("SELECT product_label_keys FROM each_brand_post_facts WHERE post_id=%s AND brand_id=%s", [post.pk, brand.pk])
                assert cursor.fetchone()[0] == ["bug"], "Publication passed while an older child writer was still in flight"
        else:
            assert publication["status"] == "busy"
        # A busy observation retains exact live fallback, and a later ordinary
        # refresh must include the committed child without inventing dirtiness.
        result = refresh_materialization(definition)
        assert result["status"] in {"refreshed", "skipped"}
        with connection.cursor() as cursor:
            cursor.execute("SELECT product_label_keys FROM each_brand_post_facts WHERE post_id=%s AND brand_id=%s", [post.pk, brand.pk])
            assert cursor.fetchone()[0] == ["bug"]
    finally:
        parent.rollback()
        parent.close()
        release.set()
        child.join(timeout=4)

@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_each_invalidation_tracks_changes_during_refresh():
    brand = Brand.objects.create(nickname='each-refresh-tracking')
    historical = timezone.now() - timedelta(days=5)
    post = Post.objects.create(tweet_id='each-refresh-tracking', created_at=historical)
    PostBrand.objects.create(post=post, brand=brand)
    ProductLabelKey.objects.get_or_create(key='bug')
    state, _ = MaterializationState.objects.get_or_create(pk='each.brand_post_facts.v1')
    state.refresh_generation = state.source_generation
    state.refresh_dirty_since = None
    state.save(update_fields=['refresh_generation', 'refresh_dirty_since'])
    PostBrandProductLabel.objects.create(post=post, brand=brand, product_label_id='bug')
    state.refresh_from_db()
    assert state.refresh_dirty_since == historical
    assert state.source_generation > state.refresh_generation

@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_each_brand_identity_change_tracks_full_refresh_invalidation():
    brand = Brand.objects.create(nickname='each-brand-before')
    state, _ = MaterializationState.objects.get_or_create(pk='each.brand_post_facts.v1')
    state.refresh_generation = state.source_generation
    state.refresh_dirty_since = None
    state.save(update_fields=['refresh_generation', 'refresh_dirty_since'])
    Brand.objects.filter(pk=brand.pk).update(nickname='each-brand-after')
    state.refresh_from_db()
    assert state.refresh_dirty_since.year == 1
    assert state.source_generation > state.refresh_generation

@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_each_online_refresh_preserves_concurrent_historical_write():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    brand = Brand.objects.create(nickname='each-online-race')
    post = Post.objects.create(tweet_id='each-online-race', created_at=timezone.now() - timedelta(days=5))
    PostBrand.objects.create(post=post, brand=brand)
    ProductLabelKey.objects.get_or_create(key='bug')
    MaterializationState.objects.get_or_create(pk='each.brand_post_facts.v1')
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    Post.objects.filter(pk=post.pk).update(lang='en')

    def write():
        try:
            PostBrandProductLabel.objects.create(post_id=post.pk, brand_id=brand.pk, product_label_id='bug')
        finally:
            connections['default'].close()

    def after_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write).result(timeout=5)
        return result

    with connection.execute_wrapper(after_refresh):
        assert refresh_materialization(EACH_FACTS, force=True)['status'] == 'refreshed'
    state = MaterializationState.objects.get(pk='each.brand_post_facts.v1')
    assert state.source_generation > state.published_generation
    assert state.dirty_since <= post.created_at
    assert state.refresh_generation is None
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    with connection.cursor() as cursor:
        cursor.execute('SELECT product_label_keys FROM each_brand_post_facts WHERE post_id=%s AND brand_id=%s', [post.pk, brand.pk])
        assert cursor.fetchone()[0] == ['bug']

@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_each_online_refresh_preserves_concurrent_brand_identity_change():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    Brand.objects.create(nickname='each-online-brand-before')
    MaterializationState.objects.get_or_create(pk='each.brand_post_facts.v1')
    assert refresh_materialization(EACH_FACTS)['status'] == 'refreshed'
    timeouts = []

    def rename():
        try:
            Brand.objects.filter(pk='each-online-brand-before').update(nickname='each-online-brand-after')
        finally:
            connections['default'].close()

    def after_refresh(execute, sql, params, many, context):
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('statement_timeout')")
                timeouts.append(cursor.fetchone()[0])
        result = execute(sql, params, many, context)
        if sql.startswith('REFRESH MATERIALIZED VIEW'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(rename).result(timeout=5)
        return result

    with connection.execute_wrapper(after_refresh):
        assert refresh_materialization(EACH_FACTS, force=True)['status'] == 'refreshed'
    assert timeouts == ['5min']
    state = MaterializationState.objects.get(pk='each.brand_post_facts.v1')
    assert state.source_generation > state.published_generation
    assert state.dirty_since.year == 1
    assert state.refresh_generation is None
