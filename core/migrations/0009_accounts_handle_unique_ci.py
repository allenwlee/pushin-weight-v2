"""Plan 2026-07-30-002 U11 - partial unique index on accounts.handle.

Creates `uniq_accounts_handle_lower` — a Postgres expression unique
index on `LOWER(handle)` restricted to non-NULL handles. This makes
future drift impossible: any code path that tries to INSERT a
duplicate handle (case-insensitive) will fail with `IntegrityError`
at the DB layer before the row is written.

Why a Postgres expression index (LOWER) rather than Django's `unique=True`:
  - accounts.handle has `db_collation="case_insensitive"` (case-
    insensitive). Django's `unique=True` emits a unique index on the
    raw column bytes which would not catch `DoubaoAI` vs `doubaoai`
    duplicates — the exact drift we are trying to prevent.
  - LOWER(handle) is a deterministic expression; the index is portable
    across PostgreSQL versions and doesn't require a deterministic
    collation.

Why `CREATE UNIQUE INDEX CONCURRENTLY`:
  - PostgreSQL allows CONCURRENTLY to build the index without locking
    the table for writes. On a 19K-row table this is fast either way,
    but the pattern matters as the table grows.
  - CONCURRENTLY cannot run inside a transaction. The migration uses
    `migrations.RunSQL(..., atomic=False)` to opt out of the
    transaction wrapper.

Precheck:
  - Before building the index, count handles that have > 1 row
    (case-insensitive). If the count is > 0, refuse with a clear
    error pointing operators at U10 (`reconcile_account_duplicates
    --apply`). The precheck is the only thing that prevents a
    production deploy from failing with `relation
    "uniq_accounts_handle_lower" contains duplicated values`.

Plan body reference: docs/plans/2026-07-30-002-...-plan.md KTD13
+ KTD15 (sequencing: U10 reduce dupes FIRST, then U11 create index).
"""

from django.db import migrations


PRECHECK_SQL = """
SELECT COUNT(*) FROM (
  SELECT LOWER(handle) FROM accounts
  WHERE handle IS NOT NULL
  GROUP BY LOWER(handle)
  HAVING COUNT(*) > 1
) t;
"""

CREATE_INDEX_SQL = """
CREATE UNIQUE INDEX CONCURRENTLY uniq_accounts_handle_lower
  ON accounts (LOWER(handle)) WHERE handle IS NOT NULL;
"""

DROP_INDEX_SQL = "DROP INDEX IF EXISTS uniq_accounts_handle_lower;"


def _create_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from django.db import connection

    with connection.cursor() as cur:
        # KTD15 precheck: refuse if any handle still has duplicates.
        cur.execute(PRECHECK_SQL)
        dup_count = cur.fetchone()[0]
        if dup_count > 0:
            raise RuntimeError(
                f"accounts still has {dup_count} duplicate handle groups "
                f"(case-insensitive). Run `manage.py reconcile_account_duplicates "
                f"--apply` first to collapse them to <= 1 per handle."
            )
        cur.execute(CREATE_INDEX_SQL)


def _drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(DROP_INDEX_SQL)


class Migration(migrations.Migration):
    """U11: partial unique index on LOWER(handle) WHERE handle IS NOT NULL.

    Idempotent: the precheck gates on duplicate count; re-running is
    safe. Reverse drops the index.
    """

    dependencies = [
        ("core", "0008_merge_20260730_0452"),
    ]

    operations = [
        migrations.RunPython(_create_index, _drop_index, atomic=False),
    ]