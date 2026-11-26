"""The General ordering index can be built online and retried safely."""

from importlib import import_module
from types import SimpleNamespace

import psycopg
import pytest
from django.db import OperationalError, connection

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def migration():
    return import_module("core.migrations.0242_general_feed_recent_index")


def editor():
    return SimpleNamespace(connection=connection)


def native_connection():
    config = connection.settings_dict
    return psycopg.connect(
        dbname=config["NAME"], user=config["USER"], password=config["PASSWORD"],
        host=config["HOST"], port=config["PORT"],
    )


def status():
    mod = migration()
    base = import_module("core.migrations.0235_each_chart_facts")
    with connection.cursor() as cursor:
        return base.index_status(cursor, mod.NAME)


def test_existing_exact_index_is_adopted_and_can_be_rebuilt():
    mod = migration()
    before = status()
    mod.create_index(None, editor())
    assert status()["oid"] == before["oid"]
    try:
        mod.remove_index(None, editor())
        assert status() is None
        mod.create_index(None, editor())
        assert all(status()[key] for key in ("valid", "ready", "live"))
    finally:
        mod.create_index(None, editor())


@pytest.mark.parametrize(
    "definition",
    [
        "posts(lang)",
        'posts(fetched_at, tweet_id COLLATE "C")',
        "posts(fetched_at DESC, tweet_id)",
    ],
)
def test_incompatible_index_is_not_adopted_or_removed(definition):
    mod = migration()
    mod.remove_index(None, editor())
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE INDEX "{mod.NAME}" ON {definition}')
        before = status()
        with pytest.raises(RuntimeError, match="incompatible"):
            mod.create_index(None, editor())
        with pytest.raises(RuntimeError, match="incompatible"):
            mod.remove_index(None, editor())
        assert status()["oid"] == before["oid"]
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{mod.NAME}"')
        mod.create_index(None, editor())


def test_interrupted_matching_build_is_repaired_without_losing_posts():
    from core.models import Post

    mod = migration()
    post = Post.objects.create(tweet_id="general-index-held")
    mod.remove_index(None, editor())
    blocker = native_connection()
    try:
        with blocker.cursor() as cursor:
            cursor.execute("UPDATE posts SET text='held' WHERE tweet_id=%s", [post.pk])
        with connection.cursor() as cursor:
            cursor.execute("SHOW lock_timeout")
            old_timeout = cursor.fetchone()[0]
            cursor.execute("SET lock_timeout='100ms'")
            try:
                with pytest.raises(OperationalError) as error:
                    cursor.execute(
                        f'CREATE INDEX CONCURRENTLY "{mod.NAME}" '
                        'ON posts(fetched_at DESC, tweet_id COLLATE "C")'
                    )
                assert error.value.__cause__.sqlstate == "55P03"
            finally:
                cursor.execute("SELECT set_config('lock_timeout',%s,false)", [old_timeout])
        blocker.rollback()
        invalid = status()
        assert invalid and not invalid["valid"]
        mod.create_index(None, editor())
        assert status()["oid"] != invalid["oid"]
        assert status()["valid"]
        assert Post.objects.filter(pk=post.pk).exists()
    finally:
        blocker.rollback()
        blocker.close()
        mod.create_index(None, editor())


def test_busy_index_gate_does_not_wait_or_block_source_writes():
    from core.models import Post

    mod = migration()
    base = import_module("core.migrations.0235_each_chart_facts")
    blocker = native_connection()
    blocker.autocommit = True
    try:
        blocker.execute("SELECT pg_advisory_lock(%s)", [base.INDEX_LOCK])
        with pytest.raises(RuntimeError, match="already running"):
            mod.create_index(None, editor())
        assert Post.objects.create(tweet_id="general-index-writer").pk
    finally:
        blocker.execute("SELECT pg_advisory_unlock(%s)", [base.INDEX_LOCK])
        blocker.close()


def test_concurrent_index_build_allows_post_writes(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from time import monotonic, sleep

    from django.db import connections

    from core.models import Post

    mod = migration()
    base = import_module("core.migrations.0235_each_chart_facts")
    monkeypatch.setattr(base, "LOCK_TIMEOUT", "10s")
    Post.objects.create(tweet_id="general-index-build-holder")
    mod.remove_index(None, editor())
    blocker = native_connection()

    def build():
        db = connections["default"]
        try:
            mod.create_index(None, SimpleNamespace(connection=db))
        finally:
            db.close()

    try:
        blocker.execute(
            "UPDATE posts SET text='held' WHERE tweet_id='general-index-build-holder'"
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(build)
            try:
                deadline = monotonic() + 5
                active = False
                while monotonic() < deadline and not active:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT EXISTS(SELECT 1 FROM pg_stat_progress_create_index "
                            "WHERE relid='posts'::regclass)"
                        )
                        active = cursor.fetchone()[0]
                    if not active:
                        sleep(0.02)
                assert active, "concurrent index build did not start"
                assert Post.objects.create(tweet_id="general-index-during-build").pk
                with pytest.raises(RuntimeError, match="already running"):
                    mod.create_index(None, editor())
            finally:
                blocker.rollback()
            future.result(timeout=20)
        assert status()["valid"]
    finally:
        blocker.rollback()
        blocker.close()
        mod.create_index(None, editor())


def test_retry_never_drops_a_matching_index_while_another_build_is_active():
    from concurrent.futures import ThreadPoolExecutor
    from time import monotonic, sleep

    from core.models import Post

    mod = migration()
    Post.objects.create(tweet_id="general-index-active-holder")
    mod.remove_index(None, editor())
    blocker = native_connection()

    def external_build():
        with native_connection() as db:
            db.autocommit = True
            db.execute(
                f'CREATE INDEX CONCURRENTLY "{mod.NAME}" '
                'ON posts(fetched_at DESC, tweet_id COLLATE "C")'
            )

    try:
        blocker.execute("UPDATE posts SET text='held' WHERE tweet_id='general-index-active-holder'")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(external_build)
            try:
                deadline = monotonic() + 5
                building = None
                while monotonic() < deadline:
                    building = status()
                    if building is not None:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT EXISTS(SELECT 1 FROM pg_stat_progress_create_index WHERE index_relid=%s)",
                                [building["oid"]],
                            )
                            if cursor.fetchone()[0]:
                                break
                    sleep(0.02)
                else:
                    pytest.fail("concurrent index build did not appear")
                with pytest.raises(RuntimeError, match="still active"):
                    mod.create_index(None, editor())
                assert status()["oid"] == building["oid"]
            finally:
                blocker.rollback()
            future.result(timeout=20)
        assert status()["valid"]
        assert status()["oid"] == building["oid"]
    finally:
        blocker.rollback()
        blocker.close()
        mod.create_index(None, editor())
