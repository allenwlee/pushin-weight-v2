"""Coordinate bounded ingestion with writers of the same identity.

Ordinary writers take shared transaction locks, which do not block each other.
The one-time ingestion takes exclusive locks without waiting. Callers own the
transaction and must use a short transaction timeout for ingestion.
"""

from django.db import connection

# Separate seeds keep organization names, nicknames, and relationship subjects
# in distinct namespaces. PostgreSQL's collation-aware hash matches database
# equality; Python casefold does not match all of the supported Unicode cases.
_KEY_EXPRESSIONS = {
    "name": "hashtextextended(UPPER(%s::text), 871001)",
    "nickname": 'hashtextextended(%s::text COLLATE "case_insensitive", 871002)',
    "brand": 'hashtextextended(%s::text COLLATE "case_insensitive", 871003)',
    "company": 'hashtextextended(%s::text COLLATE "case_insensitive", 871004)',
    "account": "hashtextextended(%s::text, 871005)",
    "state": "hashtextextended(%s::text, 871006)",
}


def organization_lock_keys(**identities):
    """Return deterministic, globally sorted advisory keys for supplied identities."""
    if identities.keys() - _KEY_EXPRESSIONS.keys():
        raise ValueError("unknown organization identity lock kind")
    values = [
        (kind, str(value)) for kind, value in identities.items() if value is not None
    ]
    if not values:
        return []
    query = " UNION ALL ".join("SELECT " + _KEY_EXPRESSIONS[kind] for kind, _ in values)
    with connection.cursor() as cursor:
        cursor.execute(query, [value for _, value in values])
        return sorted({row[0] for row in cursor.fetchall()})


def _require_transaction():
    if connection.vendor != "postgresql" or not connection.in_atomic_block:
        raise ValueError("identity coordination requires a PostgreSQL transaction")


def acquire_ingestion_identity_locks(keys):
    """Try all exclusive keys; the caller must end the transaction on a miss."""
    _require_transaction()
    with connection.cursor() as cursor:
        for key in sorted(set(keys)):
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
            if not cursor.fetchone()[0]:
                return False
    return True


def acquire_writer_identity_locks(keys):
    """Wait only for a conflicting ingestion transaction, never another writer."""
    _require_transaction()
    with connection.cursor() as cursor:
        for key in sorted(set(keys)):
            cursor.execute("SELECT pg_advisory_xact_lock_shared(%s)", [key])
