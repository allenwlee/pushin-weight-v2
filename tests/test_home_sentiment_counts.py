"""Saved-fact sentiment charts retain the existing post-filter semantics."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db.models import Count, Subquery
from django.db.models.functions import TruncDate

from core.models import MaterializationState, PostBrand, PostBrandClassificationState
from monitor.home_sentiment_counts import read_home_sentiment_counts
from monitor.views import (
    _build_home_chart_payload,
    _filter_home_posts_queryset,
    _normalize_home_filters,
)
from tests.test_each_chart_facts import DATASET, NOW, populate
from tests.test_each_chart_facts import fact_brand as each_brand_fixture  # noqa: F401

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def _source_counts(brand, selected, start, end, promotion_mode, legacy_mode, zone):
    filters = {"brands": [brand.pk], "sentiment": selected,
               "untracked_brand_promotions": promotion_mode}
    if legacy_mode is not None:
        filters["unsanctioned"] = legacy_mode
    normalized = _normalize_home_filters(filters)
    posts = _filter_home_posts_queryset(
        365, normalized, now=end, created_at_start=start, created_at_end=end,
    ).order_by().values("tweet_id")
    rows = (PostBrand.objects.filter(brand=brand, post_id__in=Subquery(posts))
            .annotate(day=TruncDate("post__created_at", tzinfo=ZoneInfo(zone)))
            .values("day").annotate(count=Count("pk")))
    return {row["day"]: row["count"] for row in rows}


def test_saved_and_live_sentiment_matches_existing_filter_for_windows_and_corrections(request):
    fact_brand = request.getfixturevalue("each_brand_fixture")
    # One historical post has conflicting legacy values and no current state.
    PostBrandClassificationState.objects.filter(post_id="each-facts-5").delete()
    populate()
    # A historical correction invalidates the saved suffix, while an older
    # untouched prefix remains usable in the same database snapshot.
    PostBrandClassificationState.objects.filter(post_id="each-facts-3").update(sentiment_id="negative")
    for days in (7, 30, 365):
        start = NOW - timedelta(days=days)
        for sentiments in (["mixed"], ["positive"], ["negative", "__unclassified__"], ["__unclassified__"]):
            for promotion_mode, legacy_mode, zone in (
                ("any", "any", "UTC"), ("off", None, "Asia/Tokyo"), ("only", "any", "UTC")
            ):
                actual = read_home_sentiment_counts(
                    brand=fact_brand.pk, sentiments=sentiments, start=start, end=NOW, at=NOW,
                    timezone_name=zone, promotion_mode=promotion_mode, legacy_mode=legacy_mode,
                )
                assert actual is not None
                assert {row["day"]: row["count"] for row in actual} == _source_counts(
                    fact_brand, sentiments, start, NOW, promotion_mode, legacy_mode, zone,
                )


@pytest.mark.parametrize("invalid", ["missing_state", "global_dirty"])
def test_missing_or_globally_dirty_publication_falls_back(request, invalid):
    fact_brand = request.getfixturevalue("each_brand_fixture")
    populate()
    state = MaterializationState.objects.get(pk=DATASET)
    if invalid == "missing_state":
        state.delete()
    else:
        state.source_generation += 1
        state.dirty_since = NOW - timedelta(days=400)
        state.save(update_fields=["source_generation", "dirty_since"])
    assert read_home_sentiment_counts(
        brand=fact_brand.pk, sentiments=["mixed"], start=NOW - timedelta(days=30),
        end=NOW, at=NOW, timezone_name="UTC", promotion_mode="any", legacy_mode="any",
    ) is None


def test_chart_uses_saved_reader_and_matches_existing_query(request):
    brand = request.getfixturevalue("each_brand_fixture")
    populate()
    filters = {"brands": [brand.pk], "sentiment": ["mixed", "__unclassified__"],
               "untracked_brand_promotions": "any"}
    projection = [{"nickname": brand.pk, "accent_color": brand.accent_color}]
    observed = []

    def capture(**kwargs):
        result = read_home_sentiment_counts(**kwargs)
        observed.append(result)
        return result

    with patch("monitor.home_sentiment_counts.read_home_sentiment_counts", side_effect=capture):
        actual = _build_home_chart_payload(30, filters, now=NOW, brand_projection=projection)
    assert len(observed) == 1 and observed[0] is not None
    with patch("monitor.home_sentiment_counts.read_home_sentiment_counts", return_value=None):
        expected = _build_home_chart_payload(30, filters, now=NOW, brand_projection=projection)
    assert actual["series"] == expected["series"]
    assert actual["totals"] == expected["totals"]


@pytest.mark.parametrize("selection", [
    {"sentiment": ["positive"]},
    {"sentiment": ["negative", "__unclassified__"]},
    {"sentiment": ["__unclassified__"]},
    {"sentiment": ["positive"], "post_types": ["releases_updates"]},
])
def test_one_day_bounded_chart_matches_distinct_reference(request, selection):
    from tests.test_chart_harvest_coverage import record_harvest

    brand = request.getfixturevalue("each_brand_fixture")
    record_harvest(NOW, finished_at=NOW, staggered=False)
    filters = {"brands": [brand.pk], "untracked_brand_promotions": "any", **selection}
    projection = [{"nickname": brand.pk, "accent_color": brand.accent_color}]
    actual = _build_home_chart_payload(1, filters, now=NOW, brand_projection=projection)

    def distinct_reference(*args, **kwargs):
        kwargs["deduplicate"] = True
        return _filter_home_posts_queryset(*args, **kwargs)

    with patch("monitor.views._filter_home_posts_queryset", side_effect=distinct_reference):
        expected = _build_home_chart_payload(1, filters, now=NOW, brand_projection=projection)
    assert actual["days"] == expected["days"]
    assert actual["series"] == expected["series"]
    assert actual["totals"] == expected["totals"]


def test_reader_snapshot_keeps_a_concurrent_historical_change_visible_on_next_read(request):
    from django.db import connection, connections

    brand = request.getfixturevalue("each_brand_fixture")
    populate()
    options = {"brand": brand.pk, "sentiments": ["positive"], "start": NOW - timedelta(days=30),
               "end": NOW, "at": NOW, "timezone_name": "UTC", "promotion_mode": "any", "legacy_mode": "any"}

    def change():
        try:
            PostBrandClassificationState.objects.filter(post_id="each-facts-4").update(sentiment_id="positive")
        finally:
            connections["default"].close()

    def after_boundary(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "FROM materialization_state WHERE dataset_key=" in sql:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(change).result(timeout=5)
        return result

    with connection.execute_wrapper(after_boundary):
        before = read_home_sentiment_counts(**options)
    after = read_home_sentiment_counts(**options)
    day = (NOW - timedelta(days=20)).date()
    assert day not in {row["day"] for row in before}
    assert {row["day"]: row["count"] for row in after}[day] == 1


def test_other_classification_combinations_keep_existing_chart_path(request):
    brand = request.getfixturevalue("each_brand_fixture")
    populate()
    filters = {"brands": [brand.pk], "sentiment": ["mixed"],
               "post_types": ["releases_updates"], "untracked_brand_promotions": "any"}
    projection = [{"nickname": brand.pk, "accent_color": brand.accent_color}]
    with patch("monitor.home_sentiment_counts.read_home_sentiment_counts") as reader:
        _build_home_chart_payload(30, filters, now=NOW, brand_projection=projection)
    reader.assert_not_called()
    assert read_home_sentiment_counts(
        brand=brand.pk, sentiments=["mixed"], start=NOW - timedelta(days=30),
        end=NOW, at=NOW, timezone_name="UTC", promotion_mode=["general"], legacy_mode="any",
    ) is None


def test_chart_falls_back_after_saved_relation_disappears_during_read(request):
    from django.db import connection, connections

    brand = request.getfixturevalue("each_brand_fixture")
    populate()
    filters = {"brands": [brand.pk], "sentiment": ["mixed", "__unclassified__"],
               "untracked_brand_promotions": "any"}
    projection = [{"nickname": brand.pk, "accent_color": brand.accent_color}]
    with patch("monitor.home_sentiment_counts.read_home_sentiment_counts", return_value=None):
        expected = _build_home_chart_payload(30, filters, now=NOW, brand_projection=projection)
    moved = []

    def rename_saved_relation():
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("ALTER MATERIALIZED VIEW each_brand_post_facts RENAME TO each_facts_test_unavailable")
        finally:
            connections["default"].close()

    def after_boundary(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "FROM materialization_state WHERE dataset_key=" in sql and not moved:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(rename_saved_relation).result(timeout=5)
            moved.append(True)
        return result

    try:
        with connection.execute_wrapper(after_boundary):
            actual = _build_home_chart_payload(30, filters, now=NOW, brand_projection=projection)
        assert moved
        assert actual["series"] == expected["series"]
        assert actual["totals"] == expected["totals"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    finally:
        if moved:
            with connection.cursor() as cursor:
                cursor.execute("ALTER MATERIALIZED VIEW each_facts_test_unavailable RENAME TO each_brand_post_facts")
