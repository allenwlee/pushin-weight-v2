"""Elapsed request limits shared by nested Each readers and ranking work."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from math import floor
from time import monotonic
from typing import ClassVar

from django.contrib.sessions.middleware import SessionMiddleware
from django.db import DatabaseError, connection, connections, transaction
from django.utils.connection import ConnectionProxy

from core.materializations import sqlstate

_active: ContextVar[EachRequestBudget | None] = ContextVar('each_request_budget', default=None)
_query_connection: ContextVar[object | None] = ContextVar('each_query_connection', default=None)
_configuring: ContextVar[bool] = ContextVar('each_configuring_timeout', default=False)


class EachChartUnavailable(Exception):
    """The chart cannot safely finish within its current request allowance."""


class EachRequestBudget:
    def __init__(self, *, seconds: float = 15, lock_seconds: float = .25):
        self.deadline = monotonic() + seconds
        self.lock_ms = max(1, floor(lock_seconds * 1000))
        self._token = None
        self.statement_cap_ms = 0
        self.lock_cap_ms = 0

    def __enter__(self):
        parent = _active.get()
        if parent is not None:
            if parent.deadline <= self.deadline and parent.lock_ms <= self.lock_ms:
                return parent
            self.deadline = min(self.deadline, parent.deadline)
            self.lock_ms = min(self.lock_ms, parent.lock_ms)
        self._token = _active.set(self)
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _active.reset(self._token)

    def remaining_ms(self) -> int:
        value = floor((self.deadline - monotonic()) * 1000)
        if value <= 0:
            raise EachChartUnavailable('Each request budget expired')
        return value

    def guard(self, execute, sql, params, many, context):
        if _configuring.get():
            return execute(sql, params, many, context)
        command = sql.lstrip().upper()
        if command.startswith(('ROLLBACK', 'RELEASE SAVEPOINT', 'SAVEPOINT', 'COMMIT', 'BEGIN')):
            return execute(sql, params, many, context)
        budget = _active.get() or self
        remaining = budget.remaining_ms()
        if sql.lstrip().upper().startswith('SET TRANSACTION '):
            return execute(sql, params, many, context)
        statement_ms = min(remaining, self.statement_cap_ms or remaining)
        lock_ms = min(remaining, budget.lock_ms, self.lock_cap_ms or remaining)
        limits = [f'{statement_ms}ms', f'{lock_ms}ms']
        db = context.get('connection')
        if db is None:
            execute("SELECT set_config('statement_timeout', %s, true), "
                    "set_config('lock_timeout', %s, true)", limits, False, context)
        else:
            # A server-side iterator cursor cannot execute SET/SELECT before its
            # DECLARE. Use a regular cursor, bypassing only this wrapper's recursion.
            token = _configuring.set(True)
            try:
                with db.cursor() as settings_cursor:
                    settings_cursor.execute(
                        "SELECT set_config('statement_timeout', %s, %s), "
                        "set_config('lock_timeout', %s, %s)",
                        [limits[0], db.in_atomic_block, limits[1], db.in_atomic_block],
                    )
            finally:
                _configuring.reset(token)
        try:
            result = execute(sql, params, many, context)
        except DatabaseError as error:
            if db is not None and db.in_atomic_block:
                transaction.set_rollback(True, using=db.alias)
            if sqlstate(error) in {'57014', '55P03'}:
                raise EachChartUnavailable('Each database allowance expired') from error
            raise
        budget.remaining_ms()
        return result

    def _io_generator(self, generator):
        """Check the active deadline on every psycopg nonblocking wait cycle."""
        try:
            operation = next(generator)
            while True:
                (_active.get() or self).remaining_ms()
                ready = yield operation
                (_active.get() or self).remaining_ms()
                operation = generator.send(ready)
        except StopIteration as done:
            return done.value
        finally:
            generator.close()

    @contextmanager
    def _connection_io_scope(self):
        """Scope IO hooks to this thread's Django wrapper and its raw connection.

        Django's initialization and initial pg_settings query run before the SQL
        wrapper can install timeouts. A connection-local psycopg wait hook also
        bounds those round trips. Synchronous DNS remains governed by the host's
        resolver; connect_timeout bounds each TCP/authentication attempt only.
        """
        from psycopg import Connection as PsycopgConnection
        from psycopg import OperationalError as PsycopgOperationalError

        db = connections[connection.alias] if isinstance(connection, ConnectionProxy) else connection
        attributes = ('get_connection_params', 'get_new_connection', 'Database')
        previous = {name: db.__dict__.get(name) for name in attributes}
        present = {name: name in db.__dict__ for name in attributes}
        original_params = db.get_connection_params
        original_new = db.get_new_connection
        original_driver = db.Database
        attached = []
        budget = self

        class DeadlineConnection(PsycopgConnection):
            @classmethod
            def _connect_gen(cls, *args, **kwargs):
                # All address attempts share this request's monotonic deadline.
                # Delegate authentication, adapters and connection construction
                # to psycopg, rather than maintaining a separate backend.
                # psycopg moved timeout handling out of this generator in
                # 3.3.9. Forward exactly the arguments its caller supplied.
                return budget._io_generator(super()._connect_gen(*args, **kwargs))

        class ScopedDriver:
            connect = staticmethod(DeadlineConnection.connect)

            def __getattr__(self, name):
                return getattr(original_driver, name)


        def attach(raw):
            if any(raw is item[0] for item in attached):
                return raw
            had_wait = 'wait' in raw.__dict__
            own_wait = raw.__dict__.get('wait')
            original_wait = raw.wait

            def wait(generator, interval=.1, **kwargs):
                try:
                    return original_wait(self._io_generator(generator),
                                         interval=max(.001, min(interval, .02)),
                                         **kwargs)
                except EachChartUnavailable:
                    # A blocked connection cannot safely restore GUCs or serve a
                    # later writer. Close it synchronously; no query worker is
                    # left running after the HTTP deadline.
                    if db.connection is raw:
                        db.close()
                    else:
                        raw.close()
                    raise

            attached.append((raw, had_wait, own_wait))
            raw.wait = wait
            return raw

        def parameters():
            result = original_params().copy()
            configured = int(result.get('connect_timeout') or 0)
            result['connect_timeout'] = min(configured, 2) if configured > 0 else 2
            return result

        def new_connection(params):
            (_active.get() or self).remaining_ms()
            try:
                raw = attach(original_new(params))
            except (DatabaseError, PsycopgOperationalError) as error:
                raise EachChartUnavailable('Each database connection unavailable') from error
            try:
                (_active.get() or self).remaining_ms()
            except EachChartUnavailable:
                raw.close()
                raise
            return raw

        db.get_connection_params = parameters
        db.get_new_connection = new_connection
        db.Database = ScopedDriver()
        try:
            if db.connection is not None:
                attach(db.connection)
            yield
        finally:
            for raw, had_wait, own_wait in reversed(attached):
                if had_wait:
                    raw.wait = own_wait
                else:
                    raw.__dict__.pop('wait', None)
            for name in attributes:
                if present[name]:
                    setattr(db, name, previous[name])
                else:
                    db.__dict__.pop(name, None)

    @contextmanager
    def query_scope(self):
        """Bound every SQL call while restoring a caller's connection settings."""
        if connection.vendor != 'postgresql':
            yield self
            self.remaining_ms()
            return
        if _query_connection.get() is connection:
            yield self
            self.remaining_ms()
            return
        with self._connection_io_scope():
            self.remaining_ms()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name, setting::bigint FROM pg_settings "
                                   "WHERE name IN ('statement_timeout', 'lock_timeout')")
                    previous = dict(cursor.fetchall())
            except DatabaseError as error:
                if sqlstate(error) in {'57014', '55P03'}:
                    if connection.in_atomic_block:
                        transaction.set_rollback(True, using=connection.alias)
                    raise EachChartUnavailable('Each settings discovery timed out') from error
                raise
            self.statement_cap_ms = previous['statement_timeout']
            self.lock_cap_ms = previous['lock_timeout']
            scope_token = _query_connection.set(connection)
            try:
                with connection.execute_wrapper(self.guard):
                    yield self
                    self.remaining_ms()
            finally:
                _query_connection.reset(scope_token)
                # Failed atomic work restores SET LOCAL through rollback. A
                # failed IO deadline closes the connection instead of reusing
                # unknown session state for a subsequent writer.
                if not connection.needs_rollback and connection.connection is not None:
                    token = _configuring.set(True)
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT set_config('statement_timeout', %s, %s), "
                                "set_config('lock_timeout', %s, %s)",
                                [f"{self.statement_cap_ms}ms", connection.in_atomic_block,
                                 f"{self.lock_cap_ms}ms", connection.in_atomic_block],
                            )
                    finally:
                        _configuring.reset(token)


def current_budget() -> EachRequestBudget | None:
    return _active.get()


def _unavailable_response(request, *, error, html=False, error_locale=None):
    from django.http import HttpResponse, JsonResponse

    if html:
        locale = (error_locale(request) if error_locale is not None
                  else request.GET.get('locale', 'en')).lower()
        message = ('页面加载超时，请稍后重试。' if locale.startswith('zh') else
                   '読み込みがタイムアウトしました。しばらくしてから再試行してください。' if locale.startswith('ja') else
                   'This page took too long to load. Please try again shortly.')
        response = HttpResponse(message, status=503)
    else:
        response = JsonResponse({'error': error}, status=503)
    response['Retry-After'] = '60'
    response['Cache-Control'] = 'no-store'
    return response


class EachSessionMiddleware(SessionMiddleware):
    """Keep the existing session lifecycle inside the Each-only allowance."""

    async_capable = False
    scopes: ClassVar[dict[str, tuple[int, str, bool]]] = {
        '/dashboard/each': (15, 'chart_timeout', True),
        '/dashboard/each/chart/': (15, 'chart_timeout', False),
        '/api/v2/dashboard/each/headline/': (3, 'headline_timeout', False),
    }

    def __call__(self, request):
        scope = self.scopes.get(request.path_info)
        if scope is None or (request.path_info == '/api/v2/dashboard/each/headline/'
                             and request.method != 'GET'):
            return super().__call__(request)
        seconds, error, html = scope
        try:
            with EachRequestBudget(seconds=seconds) as budget, budget.query_scope():
                # SessionMiddleware.process_response saves directly inside this
                # call, before Django converts a middleware exception to a 500.
                return super().__call__(request)
        except EachChartUnavailable:
            from monitor.views import _resolve_locale

            return _unavailable_response(
                request, error=error, html=html,
                error_locale=lambda request: _resolve_locale(request, persist=False),
            )


def bounded_each_request(*, seconds=15, error='chart_timeout', html=False, error_locale=None):
    """Bound validation, reads and rendering under one public request deadline."""
    from functools import wraps

    def decorate(view):
        @wraps(view)
        def bounded(request, *args, **kwargs):
            try:
                with EachRequestBudget(seconds=seconds) as budget, budget.query_scope():
                    return view(request, *args, **kwargs)
            except EachChartUnavailable:
                return _unavailable_response(
                    request, error=error, html=html, error_locale=error_locale,
                )
        return bounded
    return decorate
