"""The grouped saved build preserves the unchanged source's physical facts."""

from datetime import timedelta
from importlib import import_module
from time import perf_counter

import pytest
from django.db import connection

from core.models import (
    GeopoliticalModeKey,
    MaterializationState,
    PostBrandClassificationState,
    PostBrandGeopoliticalMode,
    PostBrandSignal,
    PostTypeKey,
    PostUntrackedBrandPromotion,
)
from tests import test_each_chart_facts as source_fixtures

NOW = source_fixtures.NOW
fact_brand = source_fixtures.fact_brand
positive_fact_cohort = source_fixtures.positive_fact_cohort

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
DATASET = "each.brand_post_facts.v1"
MIGRATION = "core.migrations.0235_each_chart_facts"


def relation_columns(name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,atttypid,atttypmod,attcollation,attnotnull "
            "FROM pg_attribute WHERE attrelid=%s::regclass "
            "AND attnum>0 AND NOT attisdropped ORDER BY attnum",
            [name],
        )
        return cursor.fetchall()


def assert_physical_parity():
    """Compare bounded key pages with typed, NULL-safe, binary comparisons.

    Each page reads source and saved facts in one statement snapshot. No whole-row
    JSON/text set operation is used, even when this helper sees a larger cohort.
    """
    migration = import_module(MIGRATION)
    columns = [column.strip() for column in migration.COLUMNS.split(",")]
    typed = {"created_at", "author_account_key", "state_present"}
    different = " OR ".join(
        f'e.{column} IS DISTINCT FROM a.{column}' if column in typed else
        f'e.{column} COLLATE "C" IS DISTINCT FROM a.{column} COLLATE "C"'
        for column in columns
    )
    last = ("", "")
    first_page = True
    expected_total = actual_total = 0
    while True:
        with connection.cursor() as cursor:
            cursor.execute(f"""
                WITH keys AS MATERIALIZED (
                    SELECT brand_id::text COLLATE "C" AS brand_id, post_id COLLATE "C" AS post_id
                    FROM each_brand_post_facts_source
                    WHERE created_at < date_trunc('day',transaction_timestamp(),'UTC') - interval '1 day'
                      AND (%s OR (brand_id::text COLLATE "C",post_id COLLATE "C") > (%s,%s))
                    UNION
                    SELECT brand_id::text COLLATE "C",post_id COLLATE "C"
                    FROM each_brand_post_facts
                    WHERE (%s OR (brand_id::text COLLATE "C",post_id COLLATE "C") > (%s,%s))
                    ORDER BY 1,2 LIMIT 256
                ), compared AS (
                    SELECT keys.brand_id,keys.post_id,
                        e.post_id IS NOT NULL AS expected, a.post_id IS NOT NULL AS actual,
                        (e.post_id IS NULL OR a.post_id IS NULL OR {different}) AS different
                    FROM keys
                    LEFT JOIN each_brand_post_facts_source e
                        ON e.brand_id::text COLLATE "C"=keys.brand_id AND e.post_id COLLATE "C"=keys.post_id
                        AND e.created_at < date_trunc('day',transaction_timestamp(),'UTC') - interval '1 day'
                    LEFT JOIN each_brand_post_facts a
                        ON a.brand_id::text COLLATE "C"=keys.brand_id AND a.post_id COLLATE "C"=keys.post_id
                )
                SELECT count(*),count(*) FILTER (WHERE expected),count(*) FILTER (WHERE actual),
                    count(*) FILTER (WHERE different),
                    (SELECT brand_id FROM keys ORDER BY brand_id DESC,post_id DESC LIMIT 1),
                    (SELECT post_id FROM keys ORDER BY brand_id DESC,post_id DESC LIMIT 1)
                FROM compared
            """, [first_page, *last, first_page, *last])
            size, expected, actual, differences, brand, post = cursor.fetchone()
        assert differences == 0
        expected_total += expected
        actual_total += actual
        if size == 0:
            break
        last = (brand, post)
        first_page = False
    assert expected_total > 0 and actual_total == expected_total
    assert relation_columns("each_brand_post_facts") == relation_columns("each_brand_post_facts_source")
    return expected_total


def refresh(concurrent=False):
    start = perf_counter()
    with connection.cursor() as cursor:
        cursor.execute(
            "REFRESH MATERIALIZED VIEW "
            + ("CONCURRENTLY " if concurrent else "")
            + "each_brand_post_facts"
        )
    return perf_counter() - start


def test_grouped_initial_and_concurrent_build_keep_physical_rows(
    fact_brand,
    positive_fact_cohort,
    record_property,
):
    from core.models import AudienceTopicConcept, PostBrandAudienceTopic

    # Binary brand/sentiment ownership, mixed-case raw aliases and NULL/conflict
    # scalar slots must survive grouping under case-insensitive FK collations.
    PostTypeKey.objects.get_or_create(key="other")
    PostBrandSignal.objects.create(
        post_id="each-facts-5",
        brand_id=fact_brand.pk.upper(),
        post_type_id="other",
        sentiment_id="positive",
    )
    PostBrandClassificationState.objects.filter(
        post_id="each-facts-4", brand=fact_brand
    ).update(brand_id=fact_brand.pk.upper(), sentiment_id="POSITIVE")
    for key, version in (
        ("reporting", "custom:u18a:two"),
        ("framework", "stage1-taxonomy-v4"),
    ):
        GeopoliticalModeKey.objects.get_or_create(key=key)
        PostBrandGeopoliticalMode.objects.create(
            post_id="each-facts-5",
            brand=fact_brand,
            geopolitical_mode_id=key,
            taxonomy_version=version,
        )
    concept, _ = AudienceTopicConcept.objects.get_or_create(
        scheme_id="ai_audience_topics/v1", key="grouped:unknown"
    )
    PostBrandAudienceTopic.objects.create(
        post_id="each-facts-5",
        brand=fact_brand,
        concept=concept,
        scheme_id="ai_audience_topics/v1",
        scheme_revision=12,
    )
    PostUntrackedBrandPromotion.objects.update_or_create(
        post_id="each-facts-5",
        defaults={
            "promotion_keys": ["spam", "spam", "Spam", None, 7, {"general": True}]
        },
    )

    first = refresh()
    first_rows = assert_physical_parity()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT legacy_sentiment_brand_ids,legacy_sentiment_values,promotion_keys FROM each_brand_post_facts WHERE brand_id=%s AND post_id='each-facts-5'",
            [fact_brand.pk],
        )
        brands, sentiments, promotions = cursor.fetchone()
    assert brands == sorted([fact_brand.pk, fact_brand.pk.upper()])
    assert sentiments == ["positive", None]
    assert promotions == ["Spam", "spam", "spam"]
    PostBrandClassificationState.objects.filter(
        post_id="each-facts-5", brand=fact_brand
    ).update(sentiment_id="negative")
    subsequent = refresh(concurrent=True)
    assert assert_physical_parity() == first_rows
    record_property("grouped_fixture_initial_seconds", first)
    record_property("grouped_fixture_concurrent_seconds", subsequent)
    record_property("grouped_fixture_physical_rows", first_rows)
    assert first < 90 and subsequent < 90

