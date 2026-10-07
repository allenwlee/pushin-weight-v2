"""One discovery writer/evaluator, independent of the harvest post writer."""

from contextlib import contextmanager

from monitor.run_lock import harvest_writer_lock


@contextmanager
def official_company_writer_lock(**context):
    with harvest_writer_lock(lock_scope="official-company", **context) as lease:
        yield lease
