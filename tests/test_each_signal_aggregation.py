"""The accepted signal build preserves exact physical facts and publication safety."""

from datetime import timedelta
from hashlib import sha256
from importlib import import_module
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

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
MIGRATION = "core.migrations.0234_each_signal_aggregation"
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
    columns = import_module("core.migrations.0228_each_chart_facts").COLUMNS
    with connection.cursor() as cursor:
        cursor.execute(f"""
            WITH expected AS (
                SELECT {columns} FROM each_brand_post_facts_source
                WHERE created_at < date_trunc('day',transaction_timestamp(),'UTC') - interval '1 day'
            ), actual AS (SELECT {columns} FROM each_brand_post_facts),
            missing AS (
                SELECT row_to_json(e)::text COLLATE "C" FROM expected e
                EXCEPT ALL SELECT row_to_json(a)::text COLLATE "C" FROM actual a
            ), extra AS (
                SELECT row_to_json(a)::text COLLATE "C" FROM actual a
                EXCEPT ALL SELECT row_to_json(e)::text COLLATE "C" FROM expected e
            )
            SELECT (SELECT count(*) FROM expected),(SELECT count(*) FROM actual),
                   (SELECT count(*) FROM missing),(SELECT count(*) FROM extra)
        """)
        counts = cursor.fetchone()
    assert counts[0] > 0 and counts == (counts[0], counts[0], 0, 0)
    assert attributes("each_brand_post_facts") == attributes(
        "each_brand_post_facts_source"
    )
    assert len(attributes("each_brand_post_facts")) == 20
    return counts


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
    assert migration.Migration.atomic is True
    assert migration.SQL_SHA256 == EXPECTED_SHA256
    assert sha256(SQL.encode()).hexdigest() == EXPECTED_SHA256
    migration.forwards(None, SimpleNamespace(connection=connection))
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
    import_module(MIGRATION).forwards(None, SimpleNamespace(connection=connection))
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


def stable_objects():
    from tests.test_each_chart_facts_grouped_build import acl_snapshot

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 'each_brand_post_facts_source'::regclass::oid, pg_get_viewdef('each_brand_post_facts_source'::regclass)"
        )
        source = cursor.fetchone()
        cursor.execute(
            "SELECT c.relname,i.indexrelid,pg_get_indexdef(i.indexrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid='posts'::regclass ORDER BY c.relname"
        )
        source_indexes = cursor.fetchall()
        cursor.execute(
            "SELECT indexname,indexdef FROM pg_indexes WHERE tablename='each_brand_post_facts' ORDER BY indexname"
        )
        saved_indexes = cursor.fetchall()
        cursor.execute(
            "SELECT tgrelid,tgname,tgfoid FROM pg_trigger WHERE tgname LIKE 'each_facts_%' ORDER BY 1,2"
        )
        triggers = cursor.fetchall()
    return source, source_indexes, saved_indexes, triggers, acl_snapshot()


def test_signal_forward_reverse_keep_source_indexes_triggers_access_and_generations(
    fact_brand,
):
    from core.models import MaterializationState

    migration = import_module(MIGRATION)
    reader = "each_signal_reader_" + uuid4().hex[:12]
    with connection.cursor() as cursor:
        cursor.execute("CREATE ROLE " + connection.ops.quote_name(reader) + " NOLOGIN")
        cursor.execute(
            "GRANT SELECT ON each_brand_post_facts TO "
            + connection.ops.quote_name(reader)
            + " WITH GRANT OPTION"
        )
        cursor.execute(
            "GRANT SELECT (lang_detected) ON each_brand_post_facts TO "
            + connection.ops.quote_name(reader)
            + " WITH GRANT OPTION"
        )
    before = stable_objects()
    for direction in (migration.forwards, migration.backwards, migration.forwards):
        rebuild()
        state = MaterializationState.objects.get(pk="each.brand_post_facts.v1")
        state.published_generation = state.source_generation
        state.cutoff = timezone.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        state.refreshed_at = timezone.now()
        state.save(update_fields=["published_generation", "cutoff", "refreshed_at"])
        generation, dirty = state.source_generation, state.dirty_since
        direction(None, SimpleNamespace(connection=connection))
        state.refresh_from_db()
        assert state.source_generation == generation and state.dirty_since == dirty
        assert (state.published_generation, state.cutoff, state.refreshed_at) == (
            None,
            None,
            None,
        )
        assert stable_objects() == before
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relispopulated FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
            )
            assert cursor.fetchone() == (False,)
            cursor.execute("SELECT pg_get_viewdef('each_brand_post_facts'::regclass)")
            body = cursor.fetchone()[0]
            assert ("signal_stats" in body) == (direction == migration.forwards)
        rebuild()
        compare_build()
