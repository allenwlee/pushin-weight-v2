"""Native online indexes partition exact small/wide Post facts without data loss."""

from datetime import timedelta
from importlib import import_module
from random import Random
from string import ascii_letters, digits
from types import SimpleNamespace

import psycopg
import pytest
from django.db import OperationalError, connection, transaction
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
MIGRATION = "core.migrations.0235_each_chart_facts"


def migration():
    return import_module(MIGRATION)


def editor():
    return SimpleNamespace(connection=connection)


def statuses():
    with connection.cursor() as cursor:
        return {
            spec[0]: migration().index_status(cursor, spec[0])
            for spec in migration().INDEXES
        }


def drop_owned_index(name):
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX CONCURRENTLY " + connection.ops.quote_name(name))


def test_posts_each_cover_has_exact_native_projection():
    from core.models import Post

    mod = migration()
    for spec in mod.INDEXES:
        row = statuses()[spec[0]]
        assert row is not None
        mod.validate_index(row, spec)
        assert row["columns"] == list(spec[1])
        assert row["key_count"] == 1 and row["valid"] and row["ready"]
    cover = next(index for index in Post._meta.indexes if index.name == mod.COVER_NAME)
    wide = next(index for index in Post._meta.indexes if index.name == mod.WIDE_NAME)
    assert cover.fields == wide.fields == ["created_at"]
    assert list(cover.include) == ["tweet_id", "lang_detected", "lang", "author"]
    assert list(wide.include) == []
    assert wide.condition == ~cover.condition
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_indexdef('idx_posts_created_cover'::regclass)")
        assert "INCLUDE (tweet_id, author_account_key)" in cursor.fetchone()[0]
        cursor.execute("SELECT pg_get_viewdef('each_brand_post_facts'::regclass)")
        assert "UNION ALL" in cursor.fetchone()[0]


def test_valid_online_prebuild_adoption_is_exact_and_preserves_published_view():
    mod = migration()
    before = statuses()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 'each_brand_post_facts'::regclass::oid")
        view_oid = cursor.fetchone()[0]
        cursor.execute(
            "SELECT source_generation,published_generation,cutoff,refreshed_at FROM materialization_state WHERE dataset_key='each.brand_post_facts.v1'"
        )
        publication = cursor.fetchone()
    sql = []

    def capture(execute, query, params, many, context):
        sql.append(query)
        return execute(query, params, many, context)

    with connection.execute_wrapper(capture):
        result = mod.prebuild_indexes(None, editor())
    assert result == {mod.COVER_NAME: "adopted", mod.WIDE_NAME: "adopted"}
    assert {name: row["oid"] for name, row in statuses().items()} == {
        name: row["oid"] for name, row in before.items()
    }
    assert not any("CREATE INDEX" in query or "DROP " in query for query in sql)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 'each_brand_post_facts'::regclass::oid")
        assert cursor.fetchone()[0] == view_oid
        cursor.execute(
            "SELECT source_generation,published_generation,cutoff,refreshed_at FROM materialization_state WHERE dataset_key='each.brand_post_facts.v1'"
        )
        assert cursor.fetchone() == publication


def test_reverse_and_reapply_are_online_and_preserve_original_small_home_index():
    mod = migration()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 'idx_posts_created_cover'::regclass::oid")
        home_oid = cursor.fetchone()[0]
    try:
        mod.remove_indexes(None, editor())
        assert statuses() == {mod.COVER_NAME: None, mod.WIDE_NAME: None}
        with connection.cursor() as cursor:
            cursor.execute("SELECT 'idx_posts_created_cover'::regclass::oid")
            assert cursor.fetchone()[0] == home_oid
            cursor.execute("SELECT pg_get_viewdef('each_brand_post_facts'::regclass)")
            assert "UNION ALL" in cursor.fetchone()[0]
        result = mod.prebuild_indexes(None, editor())
        assert set(result.values()) == {"created"}
    finally:
        mod.prebuild_indexes(None, editor())
    test_posts_each_cover_has_exact_native_projection()


@pytest.mark.parametrize("kind", ["wrong_index", "wrong_predicate", "view"])
def test_conflicting_named_objects_are_not_adopted_removed_or_hidden(kind):
    mod = migration()
    for name in (mod.COVER_NAME, mod.WIDE_NAME):
        drop_owned_index(name)
    try:
        with connection.cursor() as cursor:
            if kind == "view":
                cursor.execute(
                    "CREATE VIEW " + mod.WIDE_NAME + " AS SELECT 1 AS fixture"
                )
            elif kind == "wrong_index":
                cursor.execute("CREATE INDEX " + mod.WIDE_NAME + " ON posts(lang)")
            else:
                cursor.execute(
                    "CREATE INDEX "
                    + mod.WIDE_NAME
                    + " ON posts(created_at) WHERE created_at IS NOT NULL"
                )
        original = statuses()[mod.WIDE_NAME]
        for operation in (mod.prebuild_indexes, mod.remove_indexes):
            with pytest.raises(RuntimeError, match="Refusing to change existing"):
                operation(None, editor())
            after = statuses()
            assert after[mod.COVER_NAME] is None
            assert after[mod.WIDE_NAME]["oid"] == original["oid"]
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                ("DROP VIEW " if kind == "view" else "DROP INDEX ") + mod.WIDE_NAME
            )
        mod.prebuild_indexes(None, editor())


def native_connection():
    config = connection.settings_dict
    return psycopg.connect(
        dbname=config["NAME"],
        user=config["USER"],
        password=config["PASSWORD"],
        host=config["HOST"],
        port=config["PORT"],
    )


def test_invalid_concurrent_build_is_rejected_without_deleting_its_native_object():
    from core.models import Post

    mod = migration()
    Post.objects.create(tweet_id="each-index-invalid-blocker", text="Original")
    drop_owned_index(mod.WIDE_NAME)
    with connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        previous = cursor.fetchone()[0]
    blocker = native_connection()
    try:
        with blocker.cursor() as cursor:
            cursor.execute(
                "UPDATE posts SET text='held' WHERE tweet_id='each-index-invalid-blocker'"
            )
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout='100ms'")
            with pytest.raises(OperationalError) as error:
                cursor.execute(
                    "CREATE INDEX CONCURRENTLY "
                    + mod.WIDE_NAME
                    + " ON posts(created_at) WHERE NOT "
                    + mod.SHORT_SQL
                )
            assert error.value.__cause__.sqlstate == "55P03"
        blocker.rollback()
        invalid = statuses()[mod.WIDE_NAME]
        assert invalid is not None and not invalid["valid"]
        for operation in (mod.prebuild_indexes, mod.remove_indexes):
            with pytest.raises(RuntimeError, match="incompatible or invalid"):
                operation(None, editor())
            assert statuses()[mod.WIDE_NAME]["oid"] == invalid["oid"]
    finally:
        blocker.rollback()
        blocker.close()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('lock_timeout',%s,false)", [previous])
        drop_owned_index(mod.WIDE_NAME)
        mod.prebuild_indexes(None, editor())


def test_nonwaiting_index_gate_does_not_block_source_writes_and_timeouts_restore():
    from core.models import Post

    mod = migration()
    blocker = native_connection()
    blocker.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        original_statement = cursor.fetchone()[0]
        cursor.execute("SHOW lock_timeout")
        original_lock = cursor.fetchone()[0]
        cursor.execute(
            "SELECT set_config('statement_timeout','35s',false),set_config('lock_timeout','3s',false)"
        )
    try:
        with blocker.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [mod.INDEX_LOCK])
            assert cursor.fetchone()[0]
        with pytest.raises(RuntimeError, match="already running"):
            mod.prebuild_indexes(None, editor())
        Post.objects.create(tweet_id="each-cover-source-writer", lang="ja")
        with blocker.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [mod.INDEX_LOCK])
        assert set(mod.prebuild_indexes(None, editor()).values()) == {"adopted"}
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone()[0] == "35s"
            cursor.execute("SHOW lock_timeout")
            assert cursor.fetchone()[0] == "3s"
    finally:
        blocker.close()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('statement_timeout',%s,false),set_config('lock_timeout',%s,false)",
                [original_statement, original_lock],
            )


def test_wide_null_and_multibyte_facts_keep_exact_rows_through_both_index_paths():
    from core.models import Brand, MaterializationState, Post, PostBrand
    from tests.test_each_chart_facts_grouped_build import (
        assert_physical_parity,
        refresh,
    )

    mod = migration()
    brand = Brand.objects.create(nickname="each-index-width", display_name="Width")
    random = Random(1337)
    raw = lambda n: "".join(random.choices(ascii_letters + digits, k=n))
    cases = [
        ("width-null", None, None, True),
        ("width-empty", "", "", True),
        ("width-normal", "en", "ja", True),
        ("width-byte-boundary", "a" * 256, "b" * 256, True),
        ("width-unicode-short", "界" * 85, None, True),
        ("width-unicode-wide", "界" * 86, None, False),
        ("width-detected-wide", None, raw(1300), False),
        ("width-combined-" + raw(500), raw(1300), raw(1300), False),
        ("界" * 100 + "wide-id", None, None, False),
    ]
    created = timezone.now() - timedelta(days=5)
    for identity, source, detected, _short in cases:
        post = Post.objects.create(
            tweet_id=identity, lang=source, lang_detected=detected, created_at=created
        )
        PostBrand.objects.create(post=post, brand=brand)
    MaterializationState.objects.get_or_create(pk="each.brand_post_facts.v1")
    with connection.cursor() as cursor:
        cursor.execute("SELECT tweet_id," + mod.SHORT_SQL + " FROM posts")
        assert dict(cursor.fetchall()) == {
            identity: short for identity, _source, _detected, short in cases
        }
        cursor.execute(
            "SELECT tweet_id,lang,lang_detected FROM ("
            + mod.POST_PROJECTION
            + ") facts"
        )
        assert {
            identity: (source, detected)
            for identity, source, detected in cursor.fetchall()
        } == {
            identity: (source, detected) for identity, source, detected, _short in cases
        }
    mod.prebuild_indexes(None, editor())
    refresh()
    assert assert_physical_parity() == len(cases)
    refresh(concurrent=True)
    assert assert_physical_parity() == len(cases)
    with connection.cursor() as cursor:
        cursor.execute("VACUUM (ANALYZE) posts")
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan=off")
        cursor.execute(
            "EXPLAIN (FORMAT JSON) SELECT * FROM ("
            + mod.POST_PROJECTION
            + ") facts WHERE created_at < now()-interval '2 days'"
        )
        plan = cursor.fetchone()[0][0]["Plan"]

    def used_indexes(node):
        names = {node["Index Name"]} if "Index Name" in node else set()
        for child in node.get("Plans", []):
            names |= used_indexes(child)
        return names

    assert used_indexes(plan) == {mod.COVER_NAME, mod.WIDE_NAME}
