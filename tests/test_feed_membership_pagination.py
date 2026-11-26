"""Multi-brand feed pages must not duplicate posts or lose cursor positions."""

from datetime import timedelta

import pytest
from django.db import connection
from django.db.models.functions import Coalesce
from django.test.utils import CaptureQueriesContext

from core.models import Brand, Post, PostBrand
from monitor.views import (
    _feed_page_posts,
    _filter_home_posts_queryset,
    _normalize_home_filters,
)
from tests.test_each_chart_facts import NOW
from tests.test_each_chart_facts import fact_brand as each_brand_fixture  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("sort", ["created_at", "like_count"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_multi_brand_classification_pages_match_distinct_reference(request, sort, order):
    brand = request.getfixturevalue("each_brand_fixture")
    other = Brand.objects.create(nickname="feed-membership-other")
    for post in Post.objects.filter(tweet_id__in=["each-facts-0", "each-facts-1"]):
        PostBrand.objects.create(post=post, brand=other)
    filters = {"brands": [brand.pk, other.pk], "sentiment": ["positive", "__unclassified__"],
               "untracked_brand_promotions": "any"}
    normalized = _normalize_home_filters(filters)
    reference = _filter_home_posts_queryset(
        365, normalized, now=NOW, created_at_start=NOW - timedelta(days=365), created_at_end=NOW,
    )
    if sort == "like_count":
        reference = reference.annotate(_feed_sort_value=Coalesce("like_count", 0))
        sort_field = "_feed_sort_value"
    else:
        sort_field = "created_at"
    prefix = "-" if order == "desc" else ""
    expected = list(reference.order_by(f"{prefix}{sort_field}", f"{prefix}tweet_id").values_list("tweet_id", flat=True))
    actual = []
    cursor = None
    with CaptureQueriesContext(connection) as queries:
        for _ in range(10):
            page, cursor, has_more, _ = _feed_page_posts(
                window_days=365, filters=filters, sort=sort, order=order, cursor=cursor,
                limit=2, now=NOW, created_at_start=NOW - timedelta(days=365), created_at_end=NOW,
            )
            actual.extend(post.pk for post in page)
            if not has_more:
                break
        else:
            pytest.fail("feed pagination did not finish")
    assert len(actual) == len(set(actual))
    assert actual == expected
    first_page_sql = next(row["sql"] for row in queries.captured_queries if 'FROM "posts"' in row["sql"])
    assert "SELECT DISTINCT" not in first_page_sql
