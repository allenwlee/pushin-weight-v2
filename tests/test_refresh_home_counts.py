"""Exercise the public maintenance command against native PostgreSQL storage."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from core.models import Brand, MaterializationState, Post, PostBrand

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def run_refresh():
    output = StringIO()
    call_command("refresh_home_counts", stdout=output)
    return json.loads(output.getvalue())


def test_command_and_source_writer_leave_other_dataset_publication_unchanged():
    from core.models import MaterializationState

    other = MaterializationState.objects.create(
        dataset_key="chart.attention_daily.v1",
        source_generation=12,
        published_generation=11,
        dirty_since=timezone.now() - timedelta(days=3),
        cutoff=timezone.now() - timedelta(days=1),
        refreshed_at=timezone.now(),
    )
    before = MaterializationState.objects.filter(pk=other.pk).values().get()
    post = history()
    assert run_refresh()["status"] == "refreshed"
    published = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert published.source_generation == published.published_generation
    Post.objects.filter(pk=post.pk).update(
        created_at=timezone.now() - timedelta(days=4)
    )
    assert run_refresh()["status"] == "refreshed"
    assert MaterializationState.objects.filter(pk=other.pk).values().get() == before


@pytest.fixture
def alternate_materialization():
    from core.materializations import MaterializationDefinition

    definition = MaterializationDefinition(
        dataset_key="test.independent_counts.v1",
        relation="materialization_fixture_counts",
        source_tables=("materialization_fixture_inputs",),
        lock_id=726_514_094,
        cutoff_sql="date_trunc('hour', transaction_timestamp(), 'UTC')",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE materialization_fixture_inputs (id integer PRIMARY KEY)"
        )
        cursor.execute(
            "CREATE MATERIALIZED VIEW materialization_fixture_counts AS "
            "SELECT 1 AS id, count(*)::bigint AS n FROM materialization_fixture_inputs WITH NO DATA"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX materialization_fixture_key ON materialization_fixture_counts (id)"
        )
        cursor.execute("""
            CREATE FUNCTION materialization_fixture_dirty() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                UPDATE materialization_state SET source_generation=source_generation+1,
                    dirty_since='0001-01-01 00:00:00+00'::timestamptz
                WHERE dataset_key='test.independent_counts.v1';
                RETURN NULL;
            END $$;
            CREATE TRIGGER materialization_fixture_dirty AFTER INSERT ON materialization_fixture_inputs
            FOR EACH STATEMENT EXECUTE FUNCTION materialization_fixture_dirty();
        """)
    try:
        yield definition
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP MATERIALIZED VIEW materialization_fixture_counts")
            cursor.execute("DROP TABLE materialization_fixture_inputs")
            cursor.execute("DROP FUNCTION materialization_fixture_dirty()")


def test_shared_refresh_honors_other_definition_clock_sources_and_lock(
    alternate_materialization,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from core.materializations import refresh_materialization
    from core.models import MaterializationState
    from monitor.home_count_summary import REFRESH_LOCK

    history()
    assert run_refresh()["status"] == "refreshed"
    home = (
        MaterializationState.objects.filter(pk="home.brand_time_counts.v1")
        .values()
        .get()
    )
    entered, release = Event(), Event()

    def hold_home_lock():
        db = connections["default"]
        try:
            with transaction.atomic(), db.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REFRESH_LOCK])
                entered.set()
                assert release.wait(5)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(hold_home_lock)
        try:
            assert entered.wait(5)
            assert (
                refresh_materialization(alternate_materialization)["status"]
                == "refreshed"
            )
        finally:
            release.set()
        worker.result(timeout=5)
    state = MaterializationState.objects.get(pk=alternate_materialization.dataset_key)
    with connection.cursor() as cursor:
        cursor.execute("SELECT date_trunc('hour', transaction_timestamp(), 'UTC')")
        assert state.cutoff == cursor.fetchone()[0]
        cursor.execute("INSERT INTO materialization_fixture_inputs VALUES (1), (2)")
    state.refresh_from_db()
    assert state.source_generation > state.published_generation
    assert refresh_materialization(alternate_materialization)["status"] == "refreshed"
    assert refresh_materialization(alternate_materialization)["status"] == "skipped"
    with connection.cursor() as cursor:
        cursor.execute("SELECT n FROM materialization_fixture_counts")
        assert cursor.fetchone()[0] == 2
    assert (
        MaterializationState.objects.filter(pk=home["dataset_key"]).values().get()
        == home
    )


def history():
    brand = Brand.objects.create(nickname="refresh-test", display_name="Refresh")
    post = Post.objects.create(
        tweet_id="refresh-history", created_at=timezone.now() - timedelta(days=2)
    )
    PostBrand.objects.create(post=post, brand=brand)
    return post


def test_command_populates_native_view_skips_healthy_poll_and_rebuilds_correction():
    post = history()
    assert run_refresh()["status"] == "refreshed"
    first = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert first.published_generation == first.source_generation
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] == 1
    assert run_refresh()["status"] == "skipped"
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now())
    assert run_refresh()["status"] == "refreshed"
    corrected = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert corrected.cutoff == first.cutoff
    assert (
        corrected.published_generation
        == corrected.source_generation
        > first.published_generation
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] is None


def test_live_day_write_does_not_dirty_history_or_force_an_extra_refresh():
    from monitor.home_count_summary import read_home_counts

    post = history()
    assert run_refresh()["status"] == "refreshed"
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    Post.objects.filter(pk=post.pk).update(text="metrics-only")
    live = Post.objects.create(
        tweet_id="refresh-live", created_at=timezone.now() - timedelta(seconds=1)
    )
    PostBrand.objects.create(post=live, brand_id="refresh-test")
    assert run_refresh()["status"] == "skipped"
    rows = read_home_counts(
        start=today - timedelta(days=7), end=timezone.now(), brand_ids=["refresh-test"]
    )
    assert rows is not None and sum(row["count"] for row in rows) == 2


def test_concurrent_historical_commit_cannot_publish_clean_and_does_not_wait_for_counting():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from monitor.home_count_summary import refresh_home_counts

    post = history()
    assert run_refresh()["status"] == "refreshed"
    old = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    Post.objects.filter(pk=post.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )
    observed = []

    def writer_and_reader():
        db = connections["default"]
        try:
            with db.cursor() as cursor:
                cursor.execute("SET statement_timeout = '2s'")
                cursor.execute(
                    "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
                )
                observed.append(cursor.fetchone()[0])
            # This commit must finish while REFRESH's transaction remains open.
            extra = Post.objects.create(
                tweet_id="concurrent-history",
                created_at=timezone.now() - timedelta(days=2),
            )
            PostBrand.objects.create(post=extra, brand_id="refresh-test")
        finally:
            db.close()

    def after_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(writer_and_reader).result(timeout=5)
        return result

    with connection.execute_wrapper(after_refresh):
        assert refresh_home_counts()["status"] == "changed"
    assert observed == [1], (
        "reader must see the previous committed view without blocking"
    )
    state = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert state.published_generation == old.published_generation
    assert state.source_generation > state.published_generation
    assert state.cutoff == old.cutoff
    assert run_refresh()["status"] == "refreshed"
    assert (
        MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).source_generation
        == state.source_generation
    )


def test_publication_exception_rolls_back_the_refresh_and_leaves_source_rows():
    post = history()
    assert run_refresh()["status"] == "refreshed"
    previous = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now())

    def crash(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            raise RuntimeError("publication fault injection")
        return result

    with (
        connection.execute_wrapper(crash),
        pytest.raises(RuntimeError, match="fault injection"),
    ):
        run_refresh()
    assert Post.objects.filter(pk=post.pk).exists()
    assert (
        MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).published_generation
        == previous.published_generation
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] == 1
    assert run_refresh()["status"] == "refreshed"


def test_a_second_maintenance_process_reports_busy_without_refreshing():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from monitor.home_count_summary import REFRESH_LOCK

    acquired, release = Event(), Event()

    def hold_lock():
        db = connections["default"]
        try:
            with transaction.atomic():
                with db.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REFRESH_LOCK])
                acquired.set()
                assert release.wait(5)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(hold_lock)
        try:
            assert acquired.wait(5)
            assert run_refresh()["status"] == "busy"
        finally:
            release.set()
        worker.result(timeout=5)


def test_missing_state_recovery_must_include_an_already_untracked_writer():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from monitor.home_count_summary import refresh_home_counts

    assert connection.vendor == "postgresql"
    brand = Brand.objects.create(nickname="missing-state-race")
    post = Post.objects.create(
        tweet_id="missing-state-race", created_at=timezone.now() - timedelta(days=2)
    )
    MaterializationState.objects.all().delete()
    entered, release = Event(), Event()

    def writer():
        db = connections["default"]
        try:
            with transaction.atomic():
                PostBrand.objects.create(post_id=post.pk, brand_id=brand.pk)
                entered.set()
                assert release.wait(5)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(writer)
        assert entered.wait(5)

        def interleave(execute, sql, params, many, context):
            # Safe initialization first drains existing source writers; the old
            # implementation doesn't and releases this writer after counting.
            if sql.startswith("LOCK TABLE"):
                release.set()
                worker.result(timeout=5)
            result = execute(sql, params, many, context)
            if sql.startswith("REFRESH MATERIALIZED VIEW"):
                release.set()
                worker.result(timeout=5)
            return result

        try:
            with connection.execute_wrapper(interleave):
                assert refresh_home_counts()["status"] == "refreshed"
        finally:
            release.set()
        worker.result(timeout=5)
    with connection.cursor() as c:
        c.execute(
            "SELECT coalesce(sum(post_count),0) FROM home_brand_time_counts WHERE brand_id='missing-state-race'"
        )
        assert c.fetchone()[0] == PostBrand.objects.filter(brand=brand).count() == 1


def test_missing_state_repair_reports_busy_until_an_untracked_writer_commits():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    brand = Brand.objects.create(nickname="busy-missing-state")
    post = Post.objects.create(
        tweet_id="busy-missing-state", created_at=timezone.now() - timedelta(days=2)
    )
    MaterializationState.objects.all().delete()
    entered, release = Event(), Event()

    def writer():
        db = connections["default"]
        try:
            with transaction.atomic():
                PostBrand.objects.create(post_id=post.pk, brand_id=brand.pk)
                entered.set()
                assert release.wait(5)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(writer)
        try:
            assert entered.wait(5)
            assert run_refresh()["status"] == "busy"
            assert not MaterializationState.objects.exists()
        finally:
            release.set()
        worker.result(timeout=5)
    assert run_refresh()["status"] == "refreshed"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts "
            "WHERE brand_id = 'busy-missing-state'"
        )
        assert cursor.fetchone()[0] == 1


def test_missing_state_repair_requires_its_own_commit_before_counting():
    from django.db import transaction

    history()
    MaterializationState.objects.all().delete()
    with (
        transaction.atomic(),
        pytest.raises(RuntimeError, match="outside a transaction"),
    ):
        run_refresh()
    assert not MaterializationState.objects.exists()
    assert run_refresh()["status"] == "refreshed"
