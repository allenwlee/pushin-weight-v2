"""Exercise the public maintenance command against native PostgreSQL storage."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from core.models import Brand, HomeCountSnapshot, Post, PostBrand

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def run_refresh():
    output = StringIO()
    call_command("refresh_home_counts", stdout=output)
    return json.loads(output.getvalue())


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
    first = HomeCountSnapshot.objects.get(pk=1)
    assert first.published_generation == first.source_generation
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sum(post_count) FROM home_brand_time_counts WHERE brand_id = 'refresh-test'"
        )
        assert cursor.fetchone()[0] == 1
    assert run_refresh()["status"] == "skipped"
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now())
    assert run_refresh()["status"] == "refreshed"
    corrected = HomeCountSnapshot.objects.get(pk=1)
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
    old = HomeCountSnapshot.objects.get(pk=1)
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
    state = HomeCountSnapshot.objects.get(pk=1)
    assert state.published_generation == old.published_generation
    assert state.source_generation > state.published_generation
    assert state.cutoff == old.cutoff
    assert run_refresh()["status"] == "refreshed"
    assert (
        HomeCountSnapshot.objects.get(pk=1).source_generation == state.source_generation
    )


def test_publication_exception_rolls_back_the_refresh_and_leaves_source_rows():
    post = history()
    assert run_refresh()["status"] == "refreshed"
    previous = HomeCountSnapshot.objects.get(pk=1)
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
        HomeCountSnapshot.objects.get(pk=1).published_generation
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
    HomeCountSnapshot.objects.all().delete()
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
    HomeCountSnapshot.objects.all().delete()
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
            assert not HomeCountSnapshot.objects.exists()
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
    HomeCountSnapshot.objects.all().delete()
    with (
        transaction.atomic(),
        pytest.raises(RuntimeError, match="outside a transaction"),
    ):
        run_refresh()
    assert not HomeCountSnapshot.objects.exists()
    assert run_refresh()["status"] == "refreshed"
