from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

import pytest
from django.db import close_old_connections
from django.test import Client, override_settings
from django.utils.crypto import salted_hmac

from core.models import Post, PostEnrichmentState, PostSynthesisRateLimitBucket

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@override_settings(POST_TRANSLATION_DAILY_REQUEST_LIMIT=1)
def test_concurrent_distinct_readers_cannot_exceed_daily_capacity():
    posts = [Post.objects.create(tweet_id=f'capacity-race-{i}', text='Bonjour', lang='fr') for i in range(2)]
    barrier = Barrier(2)

    def request(index):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return Client(REMOTE_ADDR=f'192.0.2.{index + 1}').post(
                '/api/v2/post-translation-demands/',
                data=json.dumps({'post_ids': [posts[index].pk]}),
                content_type='application/json', secure=True,
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(request, range(2)))
    assert sorted(statuses) == [200, 429]
    assert PostEnrichmentState.objects.filter(post__in=posts, translation_requested=True).count() == 1
    scope = salted_hmac('post-translation-capacity', 'all', algorithm='sha256').hexdigest()
    assert PostSynthesisRateLimitBucket.objects.get(scope_hash=scope).count == 1
