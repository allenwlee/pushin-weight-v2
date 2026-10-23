"""Advisory-lock inspection must ignore identical keys in another database.

The existing PostgreSQL maintenance database supplies a second lock namespace.
Only session advisory locks are used there; no tables, rows or databases are
created, changed or removed. Each test owns fresh random keys and closes every
connection. The regular Django connection must already be an isolated test DB.
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection

from monitor.run_lock import (
    _lock_keys,
    _owner_context,
    backfill_yield_requested,
    harvest_writer_lock,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def other_database():
    assert connection.settings_dict['NAME'].startswith('test_')
    params = connection.get_connection_params()
    params['dbname'] = 'postgres'
    params['connect_timeout'] = 5
    connections = []

    def connect():
        database = connection.Database.connect(**params)
        database.autocommit = True
        connections.append(database)
        return database

    yield connect
    for database in connections:
        database.close()


def test_owner_lookup_ignores_same_keys_in_another_database(other_database):
    environment = 'cross-database-' + uuid.uuid4().hex
    signed_class, signed_object, class_id, object_id = _lock_keys(environment)
    foreign = other_database()
    with foreign.cursor() as cursor:
        cursor.execute("SET application_name='harvest:backfill:test.foreign-owner'")
        cursor.execute('SELECT pg_advisory_lock(%s,%s)', [signed_class, signed_object])
    with connection.cursor() as cursor:
        assert _owner_context(cursor, class_id, object_id) == (None, 'unknown')
    with harvest_writer_lock(execution_mode='live', entrypoint='test.actual-owner', environment=environment) as lease:
        assert lease.acquired
        with connection.cursor() as cursor:
            pid, context = _owner_context(cursor, class_id, object_id)
        assert pid == lease.backend_pid
        assert context.startswith('harvest:live:test.actual-owner:')


def test_foreign_database_live_waiter_does_not_pause_this_backfill(other_database):
    environment = 'cross-database-' + uuid.uuid4().hex
    signed_class, signed_object, _, _ = _lock_keys(environment)
    holder, waiter = other_database(), other_database()
    with holder.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_lock(%s,%s)', [signed_class, signed_object])
    with waiter.cursor() as cursor:
        cursor.execute("SET application_name='harvest:live:test.foreign-waiter'")
        cursor.execute("SET lock_timeout='10s'")
        cursor.execute('SELECT pg_backend_pid()')
        waiting_pid = cursor.fetchone()[0]

    def wait_foreign():
        with waiter.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(%s,%s)', [signed_class, signed_object])

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(wait_foreign)
        try:
            deadline = time.monotonic() + 5
            while True:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND locktype='advisory' AND NOT granted)", [waiting_pid])
                    queued = cursor.fetchone()[0]
                if queued or time.monotonic() >= deadline:
                    break
                time.sleep(.01)
            assert queued, 'foreign waiter was never queued'
            with harvest_writer_lock(execution_mode='backfill', entrypoint='test.local', environment=environment) as lease:
                assert lease.acquired
                assert not backfill_yield_requested()
        finally:
            with holder.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s,%s)', [signed_class, signed_object])
            future.result(timeout=10)
