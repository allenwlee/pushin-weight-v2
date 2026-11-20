"""Bound actual cold PostgreSQL acquisition and first settings-discovery IO."""
from copy import deepcopy
from socket import AF_INET, SOCK_STREAM, socket
from threading import Event, Thread
from time import monotonic

import pytest
from django.db import connection
from django.db.backends.postgresql.base import DatabaseWrapper
from django.test import RequestFactory

from monitor import each_request_budget
from monitor.each_request_budget import EachChartUnavailable, EachRequestBudget


@pytest.fixture
def silent_postgres_endpoint():
    """Own one local test server; all accepted sockets and its thread are joined."""
    stopped = Event()
    accepted = Event()
    with socket(AF_INET, SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(.05)

        def serve():
            while not stopped.is_set():
                try:
                    client, _ = listener.accept()
                except TimeoutError:
                    continue
                with client:
                    accepted.set()
                    stopped.wait(5)
                break

        worker = Thread(target=serve, name='each-silent-postgres')
        worker.start()
        try:
            yield listener.getsockname(), accepted
        finally:
            stopped.set()
            worker.join(timeout=1)
            assert not worker.is_alive()


def test_cold_unresponsive_postgres_is_bounded_and_restores_only_wrapper_options(
    silent_postgres_endpoint, monkeypatch, django_db_blocker,
):
    endpoint, accepted = silent_postgres_endpoint
    configuration = deepcopy(connection.settings_dict)
    configuration.update({
        'HOST': endpoint[0], 'PORT': str(endpoint[1]), 'NAME': 'each_probe',
        'USER': 'each_probe', 'PASSWORD': '',
        # The old path has a finite three-second test ceiling, so its red run
        # cannot hang even though the application has no acquisition guard yet.
        'OPTIONS': {'connect_timeout': 3, 'sslmode': 'disable'},
    })
    probe = DatabaseWrapper(configuration, alias='each_connection_probe')
    before = deepcopy(probe.settings_dict)
    monkeypatch.setattr(each_request_budget, 'connection', probe)
    reached = []

    @each_request_budget.bounded_each_request(seconds=3)
    def view(request):
        reached.append(True)
        raise AssertionError('unavailable database must fail before the view')

    started = monotonic()
    try:
        with django_db_blocker.unblock():
            response = view(RequestFactory().get('/dashboard/each/chart/'))
        elapsed = monotonic() - started
        assert response.status_code == 503
        assert response['Retry-After'] == '60'
        assert elapsed < 2.8
        assert accepted.is_set() and not reached
        assert probe.settings_dict == before
        assert 'get_connection_params' not in probe.__dict__
        assert 'get_new_connection' not in probe.__dict__
        assert 'Database' not in probe.__dict__
    finally:
        probe.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_initial_settings_discovery_consumes_the_same_request_io_deadline():
    # Open before the clock starts, then delay only the previously unguarded
    # discovery round trip on that actual driver connection.
    connection.ensure_connection()
    started = monotonic()

    def delay_discovery(execute, sql, params, many, context):
        if 'FROM pg_settings' in sql:
            execute('SELECT pg_sleep(.3)', None, False, context)
        return execute(sql, params, many, context)

    with (connection.execute_wrapper(delay_discovery), pytest.raises(EachChartUnavailable),
          EachRequestBudget(seconds=.06) as budget, budget.query_scope()):
        raise AssertionError('delayed setup cannot enter the request body')
    assert monotonic() - started < .25
    assert connection.connection is None or connection.connection.closed
    # A timed-out connection is discarded, not reused with unknown session GUCs.
    with (EachRequestBudget(seconds=3) as recovery, recovery.query_scope(),
          connection.cursor() as cursor):
        cursor.execute('SELECT 1')
        assert cursor.fetchone() == (1,)


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_warm_scope_restores_driver_wait_and_shorter_caller_guards():
    connection.ensure_connection()
    raw = connection.connection
    had_wait = 'wait' in raw.__dict__
    original_wait = raw.__dict__.get('wait')
    with connection.cursor() as cursor:
        cursor.execute('SHOW statement_timeout')
        original_statement = cursor.fetchone()[0]
        cursor.execute('SHOW lock_timeout')
        original_lock = cursor.fetchone()[0]
        cursor.execute("SET statement_timeout='40ms'")
        cursor.execute("SET lock_timeout='30ms'")
    try:
        with (EachRequestBudget(seconds=1) as budget, budget.query_scope(),
              connection.cursor() as cursor):
            cursor.execute('SHOW statement_timeout')
            assert cursor.fetchone() == ('40ms',)
            cursor.execute('SHOW lock_timeout')
            assert cursor.fetchone() == ('30ms',)
        assert ('wait' in raw.__dict__) == had_wait
        assert raw.__dict__.get('wait') is original_wait
        with connection.cursor() as cursor:
            cursor.execute('SHOW statement_timeout')
            assert cursor.fetchone() == ('40ms',)
            cursor.execute('SHOW lock_timeout')
            assert cursor.fetchone() == ('30ms',)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, false), "
                           "set_config('lock_timeout', %s, false)",
                           [original_statement, original_lock])


def test_connection_attempt_generators_share_one_deadline(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(each_request_budget, 'monotonic', lambda: clock[0])
    closed = []

    def attempt():
        try:
            yield (17, 1)
            yield (17, 2)
        finally:
            closed.append(True)

    with EachRequestBudget(seconds=3) as budget:
        first = budget._io_generator(attempt())
        assert next(first) == (17, 1)
        clock[0] += 2.1
        assert first.send(1) == (17, 2)
        first.close()
        second = budget._io_generator(attempt())
        assert next(second) == (17, 1)
        clock[0] += 1.0
        with pytest.raises(EachChartUnavailable):
            second.send(1)
    assert closed == [True, True]


@pytest.mark.parametrize('accepts_timeout', [False, True])
def test_connection_generator_forwards_only_the_installed_driver_arguments(
    accepts_timeout, monkeypatch,
):
    """Pin both psycopg 3.3.4 and 3.3.9 calling conventions without network IO."""
    import psycopg

    observed = []

    def operation(arguments):
        observed.append(arguments)
        yield (17, 1)
        return 'connected'

    if accepts_timeout:
        def driver_connect(cls, conninfo='', *, timeout):
            return operation((conninfo, {'timeout': timeout}))
        arguments = {'timeout': 1.25}
    else:
        def driver_connect(cls, conninfo=''):
            return operation((conninfo, {}))
        arguments = {}

    monkeypatch.setattr(psycopg.Connection, '_connect_gen', classmethod(driver_connect))
    with EachRequestBudget(seconds=3) as budget, budget._connection_io_scope():
        scoped_class = connection.Database.connect.__self__
        generator = scoped_class._connect_gen('dbname=each_probe', **arguments)
        assert next(generator) == (17, 1)
        with pytest.raises(StopIteration) as finished:
            generator.send(1)
        assert finished.value.value == 'connected'
    assert observed == [('dbname=each_probe', arguments)]



@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_budgeted_cold_connection_initializes_with_the_installed_driver():
    configuration = deepcopy(connection.settings_dict)
    connection.close()
    assert connection.connection is None
    with (EachRequestBudget(seconds=3) as budget, budget.query_scope(),
          connection.cursor() as cursor):
        cursor.execute('SELECT 1')
        assert cursor.fetchone() == (1,)
    assert connection.settings_dict == configuration
    assert 'Database' not in connection._connections[connection.alias].__dict__
