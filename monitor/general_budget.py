"""One request clock for General's SQL, queue waits and candidate batches."""

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from math import ceil
from time import monotonic

from django.db import DatabaseError, connection, transaction


class GeneralReadTimeout(TimeoutError):
    """The request cannot complete within its data-read budget."""


_active_budget = ContextVar("general_read_budget", default=None)


def check_read_deadline():
    budget = _active_budget.get()
    if budget is not None:
        budget.remaining()


def current_read_budget():
    return _active_budget.get()


class GeneralReadBudget:
    def __init__(self, seconds):
        self.deadline = monotonic() + seconds

    def remaining(self):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise GeneralReadTimeout("General read deadline exceeded")
        return remaining

    @contextmanager
    def on_connection(self):
        if _active_budget.get() is self:
            yield
            return
        self.remaining()
        token = _active_budget.set(self)
        original = None
        # Only caller-owned transactions need a savepoint. Autocommit readers
        # retain ownership of their Repeatable Read transaction and its setup.

        def execute(executor, sql, params, many, context):
            statement = str(sql).lstrip().upper()
            # Cleanup must work after expiry. SET TRANSACTION must precede any
            # query in a new snapshot, including set_config's SELECT.
            if statement.startswith(("SAVEPOINT ", "RELEASE SAVEPOINT ", "ROLLBACK", "SET TRANSACTION ")):
                return executor(sql, params, many, context)
            milliseconds = ceil(self.remaining() * 1000)
            if original:
                milliseconds = min(milliseconds, original)
            if connection.vendor == "postgresql":
                executor("SELECT set_config('statement_timeout', %s, false)", [str(milliseconds)], False, context)
            return executor(sql, params, many, context)

        try:
            guard = transaction.atomic() if connection.in_atomic_block or not connection.get_autocommit() else nullcontext()
            with guard:
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'")
                        original = cursor.fetchone()[0]
                        milliseconds = ceil(self.remaining() * 1000)
                        cursor.execute("SELECT set_config('statement_timeout', %s, false)", [str(min(milliseconds, original) if original else milliseconds)])
                with connection.execute_wrapper(execute):
                    yield
                    self.remaining()
        except DatabaseError as error:
            if getattr(error.__cause__, "sqlstate", None) == "57014":
                raise GeneralReadTimeout("General query deadline exceeded") from error
            raise
        finally:
            try:
                if original is not None and connection.connection is not None and not connection.needs_rollback:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT set_config('statement_timeout', %s, false)", [str(original)])
            finally:
                _active_budget.reset(token)
