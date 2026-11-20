"""Nonblocking serialization for exact-name Product evidence changes."""

from django.db import connection


class ProductNameBusy(ValueError):
    """Another transaction is changing evidence for this exact Product name."""


def lock_product_evidence_names(names):
    """Hold name locks to commit, using PostgreSQL's case-insensitive comparison."""
    if not connection.in_atomic_block:
        raise ValueError("Product evidence locks require a transaction")
    if any(not isinstance(value, str) for value in names):
        raise ValueError("Invalid Product evidence name")
    values = sorted(set(names))
    with connection.cursor() as cursor:
        for value in values:
            cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(upper(%s), 64382063))", [value])
            if not cursor.fetchone()[0]:
                raise ProductNameBusy("Product evidence is busy; retry")
