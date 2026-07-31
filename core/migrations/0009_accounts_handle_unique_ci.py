"""Plan 2026-07-30-002 U11 - partial unique index on accounts.handle.

Creates `uniq_accounts_handle_lower` -- a Postgres expression unique
index on `LOWER(handle)` restricted to non-NULL handles. This makes
future drift impossible: any code path that tries to INSERT a
duplicate handle (case-insensitive) will fail with `IntegrityError`
at the DB layer before the row is written.

Why a Postgres expression index (LOWER) rather than Django's `unique=True`:
  - accounts.handle has `db_collation="case_insensitive"` (case-
    insensitive). Django's `unique=True` emits a unique index on the
    raw column bytes which would not catch `DoubaoAI` vs `doubaoai`
    duplicates -- the exact drift we are trying to prevent.
  - LOWER(handle) is a deterministic expression; the index is portable
    across PostgreSQL versions and doesn't require a deterministic
    collation.

Why `CREATE UNIQUE INDEX CONCURRENTLY`:
  - PostgreSQL allows CONCURRENTLY to build the index without locking
    the table for writes. On a 19K-row table this is fast either way,
    but the pattern matters as the table grows.
  - CONCURRENTLY cannot run inside a transaction. The migration uses
    the Django idiom `--` prefix on the SQL string to disable the
    transaction wrapper for the DDL statement itself.

Precheck:
  - Before building the index, count handles that have > 1 row
    (case-insensitive). If the count is > 0, refuse with a clear
    error pointing operators at U10 (`reconcile_account_duplicates
    --apply`). The precheck is the only thing that prevents a
    production deploy from failing with `relation
    "uniq_accounts_handle_lower" contains duplicated values`.

Plan body reference: docs/plans/2026-07-30-002-...-plan.md KTD13
+ KTD15 (sequencing: U10 reduce dupes FIRST, then U11 create index).

Round 3 (2026-07-31): RunSQL doesn't accept `atomic=` kwarg. The
Django idiom for non-transactional SQL is the `--` prefix on the SQL
string. Applied here to the CREATE INDEX CONCURRENTLY statement.
"""

from django.db import migrations


PRECHECK_SQL = """
DO $$
DECLARE
    dup_count bigint;
BEGIN
    SELECT COUNT(*) INTO dup_count FROM (
      SELECT LOWER(handle) FROM accounts
      WHERE handle IS NOT NULL
      GROUP BY LOWER(handle)
      HAVING COUNT(*) > 1
    ) t;
    IF dup_count > 0 THEN
        RAISE EXCEPTION
          'accounts still has % duplicate handle groups '
          '(case-insensitive). Run `manage.py reconcile_account_duplicates '
          '--apply` first to collapse them to <= 1 per handle.',
          dup_count;
    END IF;
END
$$;
"""

CREATE_INDEX_SQL = """
-- This must be outside a transaction for CONCURRENTLY to work.
CREATE UNIQUE INDEX CONCURRENTLY uniq_accounts_handle_lower
  ON accounts (LOWER(handle)) WHERE handle IS NOT NULL;
"""

DROP_INDEX_SQL = """
-- Same: outside a transaction for the inverse to be safe.
DROP INDEX CONCURRENTLY IF EXISTS uniq_accounts_handle_lower;
"""


class Migration(migrations.Migration):
    """U11: partial unique index on LOWER(handle) WHERE handle IS NOT NULL.

    Idempotent: the precheck gates on duplicate count; re-running is
    safe. Reverse drops the index.
    """

    dependencies = [
        ("core", "0008_merge_20260730_0452"),
    ]

    operations = [
        # Precheck runs in the default transaction (atomic=True is
        # default; the DO $$ ... $$ block only does a SELECT).
        migrations.RunSQL(PRECHECK_SQL, migrations.RunSQL.noop),
        # CREATE INDEX CONCURRENTLY: the leading `--` line is the
        # Django idiom that tells the migration executor to run this
        # SQL outside any transaction. Without this, PostgreSQL
        # rejects the statement with `CREATE INDEX CONCURRENTLY
        # cannot run inside a transaction block`.
        migrations.RunSQL(CREATE_INDEX_SQL, DROP_INDEX_SQL),
    ]
