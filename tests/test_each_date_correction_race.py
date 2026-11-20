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
def test_child_writer_sees_concurrent_recent_to_history_date_correction():
    assert connection.settings_dict['NAME'].startswith('test_')
    brand = Brand.objects.create(nickname='each-date-race')
    post = Post.objects.create(tweet_id='each-date-race', created_at=timezone.now())
    PostBrand.objects.create(post=post, brand=brand)
    ProductLabelKey.objects.get_or_create(key='bug')
    MaterializationState.objects.get_or_create(pk='each.brand_post_facts.v1')
    assert refresh_materialization(EACH_FACTS)["status"] == "refreshed"
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
        publication = refresh_materialization(EACH_FACTS)
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
        result = refresh_materialization(EACH_FACTS)
        assert result["status"] in {"refreshed", "skipped"}
        with connection.cursor() as cursor:
            cursor.execute("SELECT product_label_keys FROM each_brand_post_facts WHERE post_id=%s AND brand_id=%s", [post.pk, brand.pk])
            assert cursor.fetchone()[0] == ["bug"]
    finally:
        parent.rollback()
        parent.close()
        release.set()
        child.join(timeout=4)
