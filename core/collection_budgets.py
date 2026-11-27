"""One finite physical request/byte/deadline budget per dispatcher invocation."""

from contextlib import contextmanager

from django.db import OperationalError, connection, transaction

from core.collection_jobs import BUDGET_LIMITS
from core.measurement_taxonomy import require
from scripts.benchmark_download_collector.sources import Budget


def invocation_budget(client, *, requests=20, seconds=120, max_bytes=8388608):
    for value, maximum in (
        (requests, BUDGET_LIMITS["requests"]),
        (seconds, BUDGET_LIMITS["seconds"]),
        (max_bytes, BUDGET_LIMITS["bytes"]),
    ):
        require(
            type(value) is int and 0 < value <= maximum, "invalid invocation budget"
        )
    return Budget(
        client,
        max_requests=requests,
        max_seconds=seconds,
        max_bytes=max_bytes,
        cumulative=True,
    )


def job_budget(parent, job):
    parent.check()
    limits = job.budgets
    child = Budget(
        parent.client,
        max_requests=min(parent.remaining, limits["requests"]),
        max_seconds=min(parent.deadline - parent.clock(), limits["seconds"]),
        max_bytes=min(parent.max_bytes - parent.total_bytes_read, limits["bytes"]),
        clock=parent.clock,
        sleep=parent.sleep,
        cumulative=True,
    )
    return child


def charge(parent, child, initial_requests):
    parent.remaining -= initial_requests - child.remaining
    parent.total_bytes_read += child.total_bytes_read


class PlanningDeadline(TimeoutError):
    """No work was claimed; the next wake can retry the ordinary selector."""


@contextmanager
def bounded_planning(budget):
    """Bound database-only selection and enrollment. Never wrap a provider call."""

    def check(execute, sql, params, many, context):
        if budget.clock() >= budget.deadline and sql.lstrip().upper().startswith(
            ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
        ):
            raise PlanningDeadline
        return execute(sql, params, many, context)

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            remaining_ms = int(1000 * (budget.deadline - budget.clock()))
            if remaining_ms <= 0:
                raise PlanningDeadline
            cursor.execute("""SELECT current_setting('statement_timeout'), current_setting('lock_timeout'),
                             (SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'),
                             (SELECT setting::bigint FROM pg_settings WHERE name='lock_timeout')""")
            prior_statement, prior_lock, statement_ms, lock_ms = cursor.fetchone()
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                [
                    f"{min(remaining_ms, statement_ms or 1500, 1500)}ms",
                    f"{min(remaining_ms, lock_ms or 250, 250)}ms",
                ],
            )
            with connection.execute_wrapper(check):
                yield
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                [prior_statement, prior_lock],
            )
    except OperationalError as exc:
        if getattr(exc.__cause__, "sqlstate", None) not in {"55P03", "57014"}:
            raise
        raise PlanningDeadline from exc
