"""Deployment concurrency proof using real PostgreSQL sessions and concurrent DDL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connection, connections

from scripts.render_migrate import run_migrations

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_waiting_migration_runner_does_not_block_concurrent_index_builder():
    owned, polled, first_finished = Event(), Event(), Event()
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE pw_source_index_proof (id bigint PRIMARY KEY, value bigint)"
        )
        cursor.execute(
            "INSERT INTO pw_source_index_proof SELECT n, n FROM generate_series(1,100) AS n"
        )

    def first():
        db = connections["default"]
        try:

            def ddl():
                owned.set()
                assert polled.wait(5), "second build did not enter nonblocking polling"
                with db.cursor() as cursor:
                    cursor.execute("SET statement_timeout='5s'")
                    cursor.execute(
                        "CREATE UNIQUE INDEX CONCURRENTLY pw_source_index_proof_unique ON pw_source_index_proof(value)"
                    )
                first_finished.set()

            run_migrations(connection=db, execute_migrate=ddl, wait_seconds=10)
        finally:
            db.close()

    def second():
        assert owned.wait(5)
        db = connections["default"]
        try:

            def wait(_seconds):
                polled.set()
                assert first_finished.wait(7), "concurrent DDL waited for lock waiter"

            run_migrations(
                connection=db, execute_migrate=lambda: None, wait_seconds=10, sleep=wait
            )
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(first), pool.submit(second)]
            for result in results:
                result.result(timeout=15)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indisvalid, indisready FROM pg_index WHERE indexrelid='pw_source_index_proof_unique'::regclass"
            )
            assert cursor.fetchone() == (True, True)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE pw_source_index_proof CASCADE")
