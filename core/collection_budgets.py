"""One finite physical request/byte/deadline budget per dispatcher invocation."""

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
    limits = job.definition["budgets"]
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
