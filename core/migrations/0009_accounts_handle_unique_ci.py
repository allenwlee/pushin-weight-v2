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

Why NOT `CREATE UNIQUE INDEX CONCURRENTLY`:
  - build.sh runs `manage.py migrate` inside a single Python process
    holding a Postgres session-scoped advisory lock. CONCURRENTLY
    explicitly refuses to run when a transaction is active; the
    session advisory lock counts.
  - The `--` prefix idiom (Django opt-out from the migration
    transaction wrapper) is silently ignored when the advisory
    lock is held at the session level.
  - For a ~17K-row table, the brief AccessExclusiveLock taken by
    a non-concurrent CREATE UNIQUE INDEX is acceptable -- the
    acquire+build is sub-second on this table size. CONCURRENTLY
    would be required only when the table is hot during deploy.

Precheck:
  - Before building the index, count handles that have > 1 row
    (case-insensitive). If the count is > 0, refuse with a clear
    error pointing operators at U10 (`reconcile_account_duplicates
    --apply`).

Plan body reference: docs/plans/2026-07-30-002-...-plan.md KTD13
+ KTD15 (sequencing: U10 reduce dupes FIRST, then U11 create index).

Round 4 (2026-07-31): dropped CONCURRENTLY. The build.sh advisory
lock prevents CONCURRENTLY from working even with the `--` prefix.
A regular CREATE UNIQUE INDEX runs in the migration transaction,
acquires AccessExclusiveLock for ~1 second on a 17K-row table,
then commits. Subsequent INSERTs are protected by the unique
constraint.

TODO (out of band): once the table is hot, re-create the index as
CONCURRENTLY via a separate maintenance script (not in the migration
ledger) that runs outside the advisory lock.
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
CREATE UNIQUE INDEX uniq_accounts_handle_lower
  ON accounts (LOWER(handle)) WHERE handle IS NOT NULL;
"""

DROP_INDEX_SQL = "DROP INDEX IF EXISTS uniq_accounts_handle_lower;"


class Migration(migrations.Migration):
    """U11: partial unique index on LOWER(handle) WHERE handle IS NOT NULL.

    Idempotent: the precheck gates on duplicate count; re-running is
    safe. Reverse drops the index.
    """

    dependencies = [
        ("core", "0008_merge_20260730_0452"),
    ]

    operations = [
        # Precheck runs in the default transaction (DO $$ ... $$ is
        # just a SELECT).
        migrations.RunSQL(PRECHECK_SQL, migrations.RunSQL.noop),
        # Plain CREATE UNIQUE INDEX (no CONCURRENTLY). Runs inside the
        # migration transaction; takes AccessExclusiveLock on the
        # table for ~1s on a 17K-row table.
        migrations.RunSQL(CREATE_INDEX_SQL, DROP_INDEX_SQL),
    ]
