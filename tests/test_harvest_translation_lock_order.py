from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from django.db import close_old_connections

from core.models import Post, PostEnrichmentState
from monitor import cycle
from monitor.enrichment_queue import request_post_translation
from x_monitor.config import Config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize('state_exists', [False, True])
def test_collector_serializes_with_translation_request_before_post_update(monkeypatch, state_exists):
    post = Post.objects.create(tweet_id='lock-order-post', text='Original')
    if state_exists:
        PostEnrichmentState.objects.create(post=post)
    entered, release, request_started = Event(), Event(), Event()
    original_upsert = cycle._upsert_post

    def paused_upsert(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original_upsert(*args, **kwargs)

    monkeypatch.setattr(cycle, '_upsert_post', paused_upsert)
    item = {'id': post.pk, 'text': 'Updated', '_discovery_lane': True}

    def collect():
        close_old_connections()
        try:
            return cycle.CycleRunner(cfg=Config(enabled_models=['deepseek'], daily_ceiling=100))._persist_items([item])
        finally:
            close_old_connections()

    def request():
        close_old_connections()
        try:
            request_started.set()
            return request_post_translation(str(post.pk)).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        collector = pool.submit(collect)
        try:
            assert entered.wait(10)
            demand = pool.submit(request)
            assert request_started.wait(10)
            with pytest.raises(TimeoutError):
                demand.result(timeout=0.5)
        finally:
            release.set()
        assert collector.result(timeout=10) == (0, 1, 0, 0)
        assert demand.result(timeout=10) == post.pk
    post.refresh_from_db()
    assert post.text == 'Updated'
    assert PostEnrichmentState.objects.get(post=post).translation_requested


def test_collector_retries_if_another_collector_inserted_after_existence_check(monkeypatch):
    original_upsert = cycle._upsert_post
    calls = 0

    def racing_upsert(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            def insert():
                close_old_connections()
                try:
                    post = Post.objects.create(tweet_id='concurrent-insert', text='Other collector')
                    PostEnrichmentState.objects.create(post=post)
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(insert).result(timeout=10)
        return original_upsert(*args, **kwargs)

    monkeypatch.setattr(cycle, '_upsert_post', racing_upsert)
    item = {'id': 'concurrent-insert', 'text': 'This collector', '_discovery_lane': True}
    runner = cycle.CycleRunner(cfg=Config(enabled_models=['deepseek'], daily_ceiling=100))
    assert runner._persist_items([item]) == (0, 1, 0, 0)
    assert calls == 2
    assert Post.objects.get(pk='concurrent-insert').text == 'This collector'
    assert item['_db_inserted'] is False
