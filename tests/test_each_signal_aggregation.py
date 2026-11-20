"""The accepted signal build preserves exact physical facts and publication safety."""

from datetime import timedelta
from hashlib import sha256
from importlib import import_module
from time import perf_counter

import pytest
from django.db import connection
from django.utils import timezone

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.models import (
    Brand,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandSignal,
    PostTypeKey,
    SentimentKey,
)
from tests import test_each_chart_facts as fixtures

fact_brand = fixtures.fact_brand
positive_fact_cohort = fixtures.positive_fact_cohort
pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
MIGRATION = "core.migrations.0235_each_chart_facts"
EXPECTED_SHA256 = "44cc964d723f1224afb906288d2bbe92bc7ee209bf98c2d48179f17ee7435960"
SQL = import_module(MIGRATION).OPTIMIZED_SELECT


def attributes(relation):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,atttypid,atttypmod,attcollation,attnotnull FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum",
            [relation],
        )
        return cursor.fetchall()


def compare_build():
    from tests.test_each_chart_facts_grouped_build import assert_physical_parity

    count = assert_physical_parity()
    assert len(attributes("each_brand_post_facts")) == 20
    return count, count, 0, 0


def rebuild(concurrent=False):
    start = perf_counter()
    with connection.cursor() as cursor:
        cursor.execute(
            "REFRESH MATERIALIZED VIEW "
            + ("CONCURRENTLY " if concurrent else "")
            + "each_brand_post_facts"
        )
    return perf_counter() - start


def test_signal_build_matches_accepted_body_and_complete_dimension_fixture(
    fact_brand, positive_fact_cohort, record_property
):
    migration = import_module(MIGRATION)
    assert migration.Migration.atomic is False
    assert migration.SQL_SHA256 == EXPECTED_SHA256
    assert sha256(SQL.encode()).hexdigest() == EXPECTED_SHA256
    first = rebuild()
    counts = compare_build()
    subsequent = rebuild(concurrent=True)
    assert compare_build() == counts
    record_property("accepted_sql_sha256", EXPECTED_SHA256)
    record_property("source_actual_missing_extra", str(counts))
    record_property("initial_fixture_seconds", first)
    record_property("concurrent_fixture_seconds", subsequent)


def test_signal_build_all_rare_cases_preserve_binary_arrays_and_nulls(
    fact_brand, record_property
):
    SentimentKey.objects.get_or_create(key="")
    unicode_brand = Brand.objects.create(
        nickname="signal-é-品牌", display_name="Unicode signal"
    )
    cases = [
        ("none", fact_brand, []),
        ("single", fact_brand, [("类型-a", "positive", False)]),
        ("blank", fact_brand, [("类型-a", "", False)]),
        (
            "multi-same",
            fact_brand,
            [("类型-a", "positive", False), ("类型-b", "positive", False)],
        ),
        (
            "multi-conflict",
            fact_brand,
            [("类型-a", "positive", False), ("类型-b", "negative", False)],
        ),
        ("all-blank", fact_brand, [("类型-a", "", False), ("类型-b", "", False)]),
        (
            "blank-positive",
            fact_brand,
            [("类型-a", "", False), ("类型-b", "positive", False)],
        ),
        (
            "literal-sentiment",
            fact_brand,
            [("类型-a", "positive", False), ("类型-b", "POSITIVE", False)],
        ),
        (
            "raw-brand",
            fact_brand,
            [("类型-a", "positive", False), ("类型-b", "negative", True)],
        ),
        (
            "raw-brand-same",
            fact_brand,
            [("类型-a", "positive", False), ("类型-b", "positive", True)],
        ),
        (
            "raw-brand-conflict",
            fact_brand,
            [
                ("类型-a", "positive", False),
                ("类型-b", "negative", False),
                ("类型-c", "mixed", True),
            ],
        ),
        (
            "unicode-brand",
            unicode_brand,
            [("类型-a", "positive", False), ("类型-b", "negative", True)],
        ),
    ]
    created = timezone.now() - timedelta(days=5)
    for name, brand, edges in cases:
        post = Post.objects.create(
            tweet_id="signal-variant-" + name,
            created_at=created,
            lang=None,
            lang_detected=None,
        )
        PostBrand.objects.create(post=post, brand=brand)
        # Current-state explicit NULL is separately preserved. Legacy raw SQL
        # has NOT NULL sentiment, so empty values exercise nullif/array NULLs.
        PostBrandClassificationState.objects.create(
            post=post,
            brand=brand,
            contract_version=CONTRACT_VERSION,
            taxonomy_version=TAXONOMY_VERSION,
            prompt_version="fixture",
            model="fixture",
            input_context_fingerprint="a" * 64,
            outcome="classified",
            sentiment_id=None,
        )
        for kind, sentiment, upper in edges:
            PostTypeKey.objects.get_or_create(key=kind)
            PostBrandSignal.objects.create(
                post=post,
                brand_id=brand.pk.upper() if upper else brand.pk,
                post_type_id=kind,
                sentiment_id=sentiment,
            )
    rebuild()
    counts = compare_build()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT legacy_sentiment_values FROM each_brand_post_facts WHERE post_id='signal-variant-all-blank'"
        )
        assert cursor.fetchone()[0] == [None]
        cursor.execute(
            "SELECT legacy_sentiment_values FROM each_brand_post_facts WHERE post_id='signal-variant-literal-sentiment'"
        )
        assert cursor.fetchone()[0] == [None]
        cursor.execute(
            "SELECT legacy_sentiment_brand_ids,legacy_sentiment_values FROM each_brand_post_facts WHERE post_id='signal-variant-raw-brand-conflict'"
        )
        assert cursor.fetchone() == (
            [fact_brand.pk.upper(), fact_brand.pk],
            ["mixed", None],
        )
        cursor.execute(
            "SELECT legacy_sentiment_brand_ids,legacy_sentiment_values FROM each_brand_post_facts WHERE post_id='signal-variant-unicode-brand'"
        )
        assert cursor.fetchone() == (
            [unicode_brand.pk.upper(), unicode_brand.pk],
            ["negative", "positive"],
        )
    PostBrandSignal.objects.filter(post_id="signal-variant-single").update(
        sentiment_id="negative"
    )
    rebuild(concurrent=True)
    assert compare_build() == counts
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT legacy_sentiment_values FROM each_brand_post_facts WHERE post_id='signal-variant-single'"
        )
        assert cursor.fetchone()[0] == ["negative"]
    record_property("accepted_sql_sha256", EXPECTED_SHA256)
    record_property("source_actual_missing_extra", str(counts))

