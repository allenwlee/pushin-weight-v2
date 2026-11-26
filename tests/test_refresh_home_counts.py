"""Exercise the public maintenance command against native PostgreSQL storage."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from core.models import Brand, MaterializationState, Post, PostBrand

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def run_refresh(*, all_results=False, command="refresh_home_counts"):
    output = StringIO()
    call_command(command, stdout=output)
    result = json.loads(output.getvalue())
    datasets = result["materializations"] if command == "refresh_home_counts" else result
    return datasets if all_results else datasets["home.brand_time_counts.v1"]


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


@pytest.mark.parametrize("write_kind", ["recent", "historic", "global"])
def test_concurrent_write_is_preserved_after_publication_without_blocking(write_kind):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from monitor.home_count_summary import refresh_home_counts

    post = history()
    assert run_refresh()["status"] == "refreshed"
    global_brand = Brand.objects.create(nickname="global-invalidation")
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
            if write_kind == "global":
                Brand.objects.filter(pk=global_brand.pk).update(nickname="GLOBAL-INVALIDATION")
            else:
                extra = Post.objects.create(
                    tweet_id="concurrent-" + write_kind,
                    created_at=timezone.now() - timedelta(days=2 if write_kind == "historic" else 0),
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
        assert refresh_home_counts()["status"] == "refreshed"
    assert observed == [1], (
        "reader must see the previous committed view without blocking"
    )
    state = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert state.published_generation > old.published_generation
    assert state.source_generation > state.published_generation
    assert state.cutoff == old.cutoff
    assert state.refresh_generation is None
    assert state.refresh_dirty_since is None
    if write_kind == "global":
        assert state.dirty_since.year == 1
    elif write_kind == "historic":
        assert state.dirty_since < state.cutoff
    else:
        assert state.dirty_since >= state.cutoff
    assert run_refresh()["status"] == ("skipped" if write_kind == "recent" else "refreshed")
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
        pytest.raises(CommandError, match="Materialization refresh failed"),
    ):
        run_refresh()
    assert Post.objects.filter(pk=post.pk).exists()
    failed_state = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert failed_state.refresh_generation is None
    assert failed_state.refresh_dirty_since is None
    assert failed_state.dirty_since is not None
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


def test_failed_refresh_preserves_concurrent_writer_and_original_dirty_boundary():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    post = history()
    assert run_refresh()["status"] == "refreshed"
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=4))
    before = MaterializationState.objects.get(pk="home.brand_time_counts.v1")

    def writer():
        db = connections["default"]
        try:
            extra = Post.objects.create(
                tweet_id="failed-refresh-writer", created_at=timezone.now() - timedelta(days=8)
            )
            PostBrand.objects.create(post=extra, brand_id="refresh-test")
        finally:
            db.close()

    def crash(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("REFRESH MATERIALIZED VIEW") and "home_brand_time_counts" in sql:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(writer).result(timeout=5)
            raise RuntimeError("publication fault after concurrent commit")
        return result

    with connection.execute_wrapper(crash), pytest.raises(CommandError):
        run_refresh()
    state = MaterializationState.objects.get(pk=before.pk)
    assert Post.objects.filter(pk="failed-refresh-writer").exists()
    assert state.published_generation == before.published_generation
    assert state.dirty_since < before.dirty_since
    assert state.refresh_generation is None
    assert state.refresh_dirty_since is None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] == 1
    assert run_refresh()["status"] == "refreshed"


def test_stale_refresh_marker_is_recovered_before_publication():
    post = history()
    assert run_refresh()["status"] == "refreshed"
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=4))
    state = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    original_dirty_since = state.dirty_since
    MaterializationState.objects.filter(pk=state.pk).update(
        refresh_generation=state.source_generation,
        refresh_dirty_since=timezone.now() - timedelta(days=8),
    )

    assert run_refresh()["status"] == "refreshed"
    state.refresh_from_db()
    assert state.refresh_generation is None
    assert state.refresh_dirty_since is None
    assert state.published_generation == state.source_generation
    assert state.dirty_since is None
    assert original_dirty_since is not None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] == 1


def test_write_after_marker_before_counting_is_conservatively_dirty():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    post = history()
    assert run_refresh()["status"] == "refreshed"
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=3))

    def writer():
        db = connections["default"]
        try:
            with db.cursor() as cursor:
                cursor.execute("SET statement_timeout = '2s'")
            added = Post.objects.create(
                tweet_id="before-counting", created_at=timezone.now() - timedelta(days=2)
            )
            PostBrand.objects.create(post=added, brand_id="refresh-test")
        finally:
            db.close()

    def before_refresh(execute, sql, params, many, context):
        if sql.startswith("REFRESH MATERIALIZED VIEW") and "home_brand_time_counts" in sql:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(writer).result(timeout=5)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(before_refresh):
        assert run_refresh()["status"] == "refreshed"
    state = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert state.source_generation > state.published_generation
    assert state.dirty_since < state.cutoff
    assert state.refresh_generation is None
    assert state.refresh_dirty_since is None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] == 2


def test_online_refresh_with_older_frozen_cutoff_does_not_double_count():
    from dataclasses import replace

    from core.materializations import refresh_materialization
    from monitor.home_count_summary import HOME_COUNTS, read_home_counts

    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    brand = Brand.objects.create(nickname="midnight-boundary")
    post = Post.objects.create(tweet_id="midnight-boundary", created_at=today - timedelta(hours=12))
    PostBrand.objects.create(post=post, brand=brand)
    # Simulate a marker taken before midnight and a view built after midnight.
    definition = replace(
        HOME_COUNTS,
        cutoff_sql="date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'",
    )
    assert refresh_materialization(definition)["status"] == "refreshed"
    end = today - timedelta(hours=6)
    rows = read_home_counts(start=end - timedelta(days=7), end=end, brand_ids=[brand.pk])
    assert rows is not None
    assert sum(row["count"] for row in rows) == 1


def test_home_online_refresh_does_not_queue_behind_inflight_brand_writer(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from core import materializations
    from monitor.home_count_summary import refresh_home_counts

    post = history()
    assert run_refresh()["status"] == "refreshed"
    entered, release = Event(), Event()

    def hold_brand_writer():
        db = connections["default"]
        try:
            with transaction.atomic(), db.cursor() as cursor:
                cursor.execute("LOCK TABLE posts_brands IN ROW EXCLUSIVE MODE")
                entered.set()
                assert release.wait(10)
        finally:
            db.close()

    monkeypatch.setattr(materializations.time, "sleep", lambda _: None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(hold_brand_writer)
        try:
            assert entered.wait(5)
            Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=3))
            assert refresh_home_counts()["status"] == "busy"
        finally:
            release.set()
        writer.result(timeout=5)
    assert refresh_home_counts()["status"] == "refreshed"


def test_online_marker_commits_with_writer_barrier_before_refresh():
    from monitor.home_count_summary import refresh_home_counts

    post = history()
    assert refresh_home_counts()["status"] == "refreshed"
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=3))
    transactions = {}

    def capture(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith((
            "LOCK TABLE", "UPDATE materialization_state SET refresh_generation = %s",
        )):
            with connection.cursor() as cursor:
                cursor.execute("SELECT txid_current()")
                transactions["barrier" if sql.startswith("LOCK TABLE") else "marker"] = cursor.fetchone()[0]
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            with connection.cursor() as cursor:
                cursor.execute("SELECT txid_current()")
                transactions["refresh"] = cursor.fetchone()[0]
        return result

    with connection.execute_wrapper(capture):
        assert refresh_home_counts()["status"] == "refreshed"
    assert transactions["barrier"] == transactions["marker"]
    assert transactions["refresh"] != transactions["marker"]


def test_online_barrier_releases_source_locks_when_state_row_is_busy(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections, transaction

    from core import materializations
    from monitor.home_count_summary import refresh_home_counts

    history()
    assert refresh_home_counts()["status"] == "refreshed"
    entered, release = Event(), Event()
    attempts = []

    def hold_state():
        db = connections["default"]
        try:
            with transaction.atomic(), db.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM materialization_state WHERE dataset_key = %s FOR UPDATE",
                    ["home.brand_time_counts.v1"],
                )
                entered.set()
                assert release.wait(10)
        finally:
            db.close()

    def check_no_source_locks(delay):
        assert delay == 0.2
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE pid = pg_backend_pid() "
                "AND mode = 'ShareLock' AND relation IN "
                "(to_regclass('posts'), to_regclass('posts_brands'))"
            )
            assert cursor.fetchone()[0] == 0
        attempts.append(delay)

    monkeypatch.setattr(materializations.time, "sleep", check_no_source_locks)
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(hold_state)
        try:
            assert entered.wait(5)
            assert refresh_home_counts()["status"] == "busy"
        finally:
            release.set()
        writer.result(timeout=5)
    assert len(attempts) == 9


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

    from monitor.home_count_summary import refresh_home_counts

    history()
    MaterializationState.objects.all().delete()
    with transaction.atomic():
        with pytest.raises(RuntimeError, match="outside a transaction"):
            refresh_home_counts()
        with pytest.raises(CommandError, match="Materialization refresh failed"):
            run_refresh()
    assert not MaterializationState.objects.exists()
    assert run_refresh()["status"] == "refreshed"


@pytest.mark.parametrize("command", ["refresh_home_counts", "refresh_materializations"])
def test_existing_maintenance_entry_runs_each_registered_dataset_once(command, monkeypatch):
    from monitor.management.commands import refresh_materializations

    calls = []

    def observe(definition):
        calls.append(definition)
        return {"status": "busy"}

    monkeypatch.setattr(refresh_materializations, "refresh_materialization", observe)
    result = run_refresh(all_results=True, command=command)
    expected = refresh_materializations.registered_definitions()
    assert calls == list(expected)
    assert result == {definition.dataset_key: {"status": "busy"} for definition in expected}


def test_one_failed_dataset_does_not_skip_the_other(monkeypatch):
    from monitor.management.commands import refresh_materializations

    calls = []

    def fail_first(definition):
        calls.append(definition.dataset_key)
        if len(calls) == 1:
            raise RuntimeError("refresh failure")
        return {"status": "busy"}

    monkeypatch.setattr(refresh_materializations, "refresh_materialization", fail_first)
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("refresh_home_counts", stdout=output)
    assert calls == [definition.dataset_key for definition in refresh_materializations.registered_definitions()]
    result = json.loads(output.getvalue())
    assert result['status'] == 'unavailable'
    assert result['error'] == 'RuntimeError'
    assert result['materializations'] == {
        calls[0]: {"status": "unavailable", "error": "RuntimeError"}, calls[1]: {"status": "busy"},
    }


def test_each_advance_barrier_busy_does_not_queue_a_later_source_writer(
    alternate_materialization, monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Event

    from django.db import connections, transaction

    from core import materializations

    definition = replace(alternate_materialization, advance_barrier=True)
    assert materializations.refresh_materialization(definition)["status"] == "refreshed"
    state = MaterializationState.objects.get(pk=definition.dataset_key)
    MaterializationState.objects.filter(pk=state.pk).update(cutoff=state.cutoff - timedelta(hours=1))
    before = MaterializationState.objects.filter(pk=state.pk).values().get()
    entered, release = Event(), Event()
    attempts = []

    def hold_source_transaction():
        db = connections["default"]
        try:
            with transaction.atomic(), db.cursor() as cursor:
                cursor.execute("LOCK TABLE materialization_fixture_inputs IN ROW EXCLUSIVE MODE")
                entered.set()
                assert release.wait(10)
        finally:
            db.close()

    def later_writer():
        db = connections["default"]
        try:
            with db.cursor() as cursor:
                cursor.execute("SET statement_timeout = '500ms'")
                cursor.execute("INSERT INTO materialization_fixture_inputs VALUES (10)")
        finally:
            db.close()

    def between_attempts(delay):
        assert not connection.in_atomic_block, "source locks must not survive an attempt"
        assert delay == 0.2
        if not attempts:
            with ThreadPoolExecutor(max_workers=1) as writer_pool:
                writer_pool.submit(later_writer).result(timeout=2)
        attempts.append(delay)

    monkeypatch.setattr(materializations.time, "sleep", between_attempts)
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(hold_source_transaction)
        try:
            assert entered.wait(5)
            assert materializations.refresh_materialization(definition) == {"status": "busy"}
        finally:
            release.set()
        held.result(timeout=5)
    assert len(attempts) == 9
    after = MaterializationState.objects.filter(pk=state.pk).values().get()
    assert after["cutoff"] == before["cutoff"]
    assert after["published_generation"] == before["published_generation"]
    assert after["source_generation"] > before["source_generation"]
    assert materializations.refresh_materialization(definition)["status"] == "refreshed"
    with connection.cursor() as cursor:
        cursor.execute("SELECT n FROM materialization_fixture_counts")
        assert cursor.fetchone()[0] == 1


def test_each_advance_barrier_commits_before_counting_and_generation_publication(
    alternate_materialization,
):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace

    from django.db import connections

    from core.materializations import refresh_materialization

    definition = replace(alternate_materialization, advance_barrier=True, refresh_timeout="5s")
    assert refresh_materialization(definition)["status"] == "refreshed"
    state = MaterializationState.objects.get(pk=definition.dataset_key)
    MaterializationState.objects.filter(pk=state.pk).update(cutoff=state.cutoff - timedelta(hours=1))
    observed = []

    def writer():
        db = connections["default"]
        try:
            with db.cursor() as cursor:
                cursor.execute("SET statement_timeout = '500ms'")
                cursor.execute("INSERT INTO materialization_fixture_inputs VALUES (20)")
        finally:
            db.close()

    def during_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                observed.append(cursor.fetchone()[0])
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(writer).result(timeout=2)
        return result

    with connection.execute_wrapper(during_refresh):
        assert refresh_materialization(definition)["status"] == "changed"
    assert observed == ["5s"]
    state.refresh_from_db()
    assert state.source_generation > state.published_generation
    assert refresh_materialization(definition)["status"] == "refreshed"


def test_unchanged_cutoff_still_drains_source_writers_when_history_is_dirty(
    alternate_materialization,
):
    from dataclasses import replace

    from core.materializations import refresh_materialization

    definition = replace(alternate_materialization, advance_barrier=True)
    assert refresh_materialization(definition)["status"] == "refreshed"
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO materialization_fixture_inputs VALUES (30)")
    locks = []

    def capture(execute, sql, params, many, context):
        if sql.startswith("LOCK TABLE"):
            locks.append(sql)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture):
        assert refresh_materialization(definition)["status"] == "refreshed"
    assert locks == ['LOCK TABLE "materialization_fixture_inputs" IN SHARE MODE NOWAIT']


def test_advance_publication_never_uses_a_clock_newer_than_its_source_barrier(
    alternate_materialization,
):
    from dataclasses import replace
    from datetime import datetime

    from core.materializations import refresh_materialization

    # A continuously advancing clock makes the midnight race reproducible
    # without changing the machine or PostgreSQL clock.
    definition = replace(
        alternate_materialization,
        advance_barrier=True,
        cutoff_sql="clock_timestamp()",
    )
    barrier_times = []

    def capture_barrier_clock(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("LOCK TABLE") and "IN SHARE MODE NOWAIT" in sql:
            with connection.cursor() as cursor:
                cursor.execute("SELECT clock_timestamp()")
                barrier_times.append(cursor.fetchone()[0])
        return result

    with connection.execute_wrapper(capture_barrier_clock):
        result = refresh_materialization(definition)
    assert result["status"] == "refreshed"
    assert len(barrier_times) == 1
    assert datetime.fromisoformat(result["cutoff"]) <= barrier_times[0]


@pytest.mark.parametrize("failure", [False, True])
def test_refresh_settings_are_scoped_and_bootstrap_has_its_own_cap(
    alternate_materialization, failure,
):
    from dataclasses import replace

    from core.materializations import refresh_materialization

    definition = replace(
        alternate_materialization,
        refresh_timeout="90s", bootstrap_timeout="120s", refresh_work_mem="8MB",
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('work_mem'),current_setting('statement_timeout')")
        original = cursor.fetchone()
    observed = []

    def capture(execute, sql, params, many, context):
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('work_mem'),current_setting('statement_timeout')")
                observed.append(cursor.fetchone())
            if failure:
                raise RuntimeError("refresh settings fault injection")
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture):
        if failure:
            with pytest.raises(RuntimeError, match="settings fault injection"):
                refresh_materialization(definition)
        else:
            assert refresh_materialization(definition)["status"] == "refreshed"
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO materialization_fixture_inputs VALUES (51)")
            assert refresh_materialization(definition)["status"] == "refreshed"
    assert observed == ([("8MB", "2min")] if failure else [("8MB", "2min"), ("8MB", "90s")])
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('work_mem'),current_setting('statement_timeout')")
        assert cursor.fetchone() == original


def test_materialization_optional_settings_validate_and_homepage_defaults_hold():
    from dataclasses import replace

    from monitor.home_count_summary import HOME_COUNTS

    assert HOME_COUNTS.refresh_timeout == "120s"
    assert HOME_COUNTS.bootstrap_timeout is None
    assert HOME_COUNTS.refresh_work_mem is None
    assert HOME_COUNTS.advance_barrier is False
    for field, invalid in (
        ("refresh_timeout", "0s"), ("refresh_timeout", "90s; SELECT 1"),
        ("bootstrap_timeout", "0s"), ("refresh_work_mem", "0MB"),
        ("refresh_work_mem", "8MB; SELECT 1"), ("refresh_work_mem", "8 GB"),
    ):
        with pytest.raises(ValueError):
            replace(HOME_COUNTS, **{field: invalid})


def test_optional_memory_restores_inside_a_callers_existing_transaction(alternate_materialization):
    from dataclasses import replace

    from django.db import transaction

    from core.materializations import refresh_materialization

    definition = replace(alternate_materialization, refresh_timeout="90s", refresh_work_mem="8MB")
    MaterializationState.objects.create(dataset_key=definition.dataset_key)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('work_mem'),current_setting('statement_timeout')")
        previous = cursor.fetchone()
        assert refresh_materialization(definition)["status"] == "refreshed"
        cursor.execute("SELECT current_setting('work_mem'),current_setting('statement_timeout')")
        assert cursor.fetchone() == previous


def test_explicit_force_refreshes_clean_publication_concurrently_without_invalidation(
    alternate_materialization,
):
    from dataclasses import replace

    from core.materializations import refresh_materialization

    definition = replace(
        alternate_materialization,
        refresh_timeout="90s", bootstrap_timeout="120s", refresh_work_mem="8MB",
        advance_barrier=True,
    )
    assert refresh_materialization(definition)["status"] == "refreshed"
    before = MaterializationState.objects.get(pk=definition.dataset_key)
    settings_sql = "SELECT current_setting('work_mem'),current_setting('statement_timeout')"
    with connection.cursor() as cursor:
        cursor.execute(settings_sql)
        original_settings = cursor.fetchone()
    refreshes = []
    observed_settings = []
    locks = []

    def capture(execute, sql, params, many, context):
        if sql.startswith("LOCK TABLE"):
            locks.append(sql)
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            refreshes.append(sql)
            with connection.cursor() as cursor:
                cursor.execute(settings_sql)
                observed_settings.append(cursor.fetchone())
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture):
        assert refresh_materialization(definition) == {
            "status": "skipped", "cutoff": before.cutoff.isoformat(),
        }
        assert refreshes == []
        skipped = MaterializationState.objects.get(pk=definition.dataset_key)
        assert skipped.refreshed_at == before.refreshed_at
        assert refresh_materialization(definition, force=True) == {
            "status": "refreshed", "cutoff": before.cutoff.isoformat(),
            "generation": before.source_generation,
        }
    assert refreshes == ['REFRESH MATERIALIZED VIEW CONCURRENTLY "materialization_fixture_counts"']
    assert observed_settings == [("8MB", "90s")]
    assert locks == ['LOCK TABLE "materialization_fixture_inputs" IN SHARE MODE NOWAIT'] * 2, "clean and forced checks drain older writers without advancing the cutoff"
    after = MaterializationState.objects.get(pk=definition.dataset_key)
    assert (after.cutoff, after.source_generation, after.published_generation) == (
        before.cutoff, before.source_generation, before.published_generation,
    )
    assert after.dirty_since == before.dirty_since is None
    assert after.refreshed_at > before.refreshed_at
    with connection.cursor() as cursor:
        cursor.execute(settings_sql)
        assert cursor.fetchone() == original_settings
