# Migration report schema

> **Plan**: `docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md`
> **Status**: Implemented (commits `0823832` on `feat/pushin-weight-home-pages`).

This document is the JSON-schema reference for the structured diff report
emitted by `scripts/2026-07-06-001-migrate-pushin-weight-records.py`.
The report is the operator's primary signal for understanding what a
migration run did, whether in dry-run or write mode.

The script prints the report to stdout and (by default) saves it to
`data/migration_logs/migrate-pushin-weight-records-<timestamp>.json`.

## Top-level shape

```json
{
  "mode": "dry-run | write",
  "target_db": "/path/to/x_monitoring.db",
  "source": "postgres:connstr | fixture:/path",
  "alias_map": "/path/to/aliases.yaml",
  "started_at": "2026-07-06T08:32:00+00:00",
  "finished_at": "2026-07-06T08:32:08+00:00",
  "<table>": { "...": "..." },
  "target_row_counts": { "<table>": <int>, "...": "..." }
}
```

- `mode` — `"dry-run"` if `--write` was not passed, `"write"` otherwise.
- `source` — `"postgres:<connstr>"` when reading from live Postgres,
  `"fixture:/path"` when reading from a SQLite fixture.
- `target_row_counts` — final row count per key table, captured at end
  of run. Useful for verifying the migration achieved its expected
  post-state without re-querying the DB.

## Per-table shape

Each per-table entry has the following shape (varies slightly between
table types — see below):

```json
{
  "table": "<target_table_name>",
  "source_rows": <int>,
  "inserted": <int>,
  "skipped_duplicate": <int>,
  "dropped_no_alias": <int>,
  "dropped_samples": [{ "row": {...}, "reason": "<string>" }, ...],
  "renamed": [{ "from": "<source_key>", "to": "<target_key>" }, ...]
}
```

- `table` — the target table the script wrote to.
- `source_rows` — number of source rows read.
- `inserted` — number of rows the script inserted (or would have
  inserted in dry-run mode).
- `skipped_duplicate` — number of rows that already existed in the
  target (UNIQUE constraint violation, treated as no-op via
  `INSERT OR IGNORE`).
- `dropped_no_alias` — number of source rows whose FK chain failed
  to resolve (e.g. source brand maps to a target brand that doesn't
  exist; source X user id (`accounts.author_id`) has no matching
  `accounts` row; source brand is a sentinel that the alias map drops).
- `dropped_samples` — first 5 dropped rows with their `reason` field.
  The full dropped list is **not** included to keep the report
  manageable; the `dropped_no_alias` count is the canonical signal.
- `renamed` — for lookup tables (discourse, post_type, roles,
  nationalism), an array of `{from, to}` records describing which
  source keys were aliased to which target keys.

## Per-table variants

| Table | Has `renamed`? | Has `dropped_samples`? | Notes |
|---|---|---|---|
| `discourse_keys` | yes | no | |
| `post_type_keys` | yes | no | |
| `nationalism_keys` | yes | no | |
| `roles` | yes | no | |
| `discourse_labels` | no | yes | |
| `post_type_labels` | no | yes | |
| `nationalism_labels` | no | yes | |
| `role_labels` | no | yes | |
| `accounts` | no | no | The `accounts` table doesn't take aliases (`accounts.author_id` is the natural key); there's no `dropped_no_alias` field — only `inserted` + `skipped_duplicate`. |
| `brand_search_terms` | no | yes | |
| `brands_accounts` | no | yes | |
| `brands_companies` | no | yes | |
| `hf_orgs` | no | yes | |

The `accounts` table is intentionally different: source `accounts` rows
have natural-key `author_id` (TEXT) that maps 1:1 to target's
`accounts.author_id`. There's no slug translation and no aliasing
needed. The script just inserts with `INSERT OR IGNORE`. The
`dropped_no_alias` field is omitted from this entry.

## Drop reasons

The `dropped_samples[].reason` field is a free-form string but follows
these conventions:

- `"sentinel-without-target-equivalent"` — source brand is in the
  `sentinels_dropped` list of the alias map.
- `"brand 'X' not seeded"` — the source brand maps to target brand
  `X`, but the target `brands` table has no row for that slug. The
  migration 030 should have added it; if not, the script is being run
  against a DB that's missing migration 030.
- `"company 'X' not seeded"` — same as above for companies.
- `"account 'X' not seeded"` — the source `brands_accounts` row's
  `author_id` has no matching row in target's `accounts`. The script
  processes `accounts` before `brands_accounts`, so this only fires if
  the account insertion failed silently (which currently it can't).
- `"role 'X' not seeded"` — source role key has no matching row in
  target's `roles` table.
- `"<lookup> parent not resolved"` — the source label's parent key
  (e.g. discourse_key) doesn't resolve via the alias map.

## Worked example

A successful dry-run report (truncated) looks like:

```json
{
  "mode": "dry-run",
  "target_db": "data/staging.db",
  "source": "postgres:host=localhost port=5432 dbname=pushin_weight user=fuchitalee",
  "alias_map": "scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml",
  "started_at": "2026-07-06T08:32:00+00:00",
  "discourse_keys": {
    "table": "discourse_keys",
    "source_rows": 10,
    "inserted": 10,
    "skipped_duplicate": 0,
    "renamed": [
      {"from": "dunk", "to": "dunk_yingyang"},
      {"from": "other", "to": "advertising-marketing"}
    ],
    "dropped_no_alias": 0
  },
  "accounts": {
    "table": "accounts",
    "source_rows": 49,
    "inserted": 49,
    "skipped_duplicate": 0
  },
  "brands_accounts": {
    "table": "brands_accounts",
    "source_rows": 62,
    "inserted": 62,
    "skipped_duplicate": 0,
    "dropped_no_alias": 0
  },
  "target_row_counts": {
    "discourse_keys": 10,
    "post_type_keys": 6,
    "nationalism_keys": 6,
    "roles": 3,
    "accounts": 1571,
    "brands_accounts": 62,
    "brands_companies": 11,
    "hf_orgs": 22,
    "brand_search_terms": 72
  },
  "finished_at": "2026-07-06T08:32:08+00:00"
}
```

## Backward compatibility

The report schema is part of the operator contract — `docs/notes/2026-07-06-pushin-weight-migration-procedure.md`
references these field names in its troubleshooting section. Renaming a
field is a breaking change and must be coordinated with the operator
runbook.

## See also

- `docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md`
  — the plan
- `docs/notes/2026-07-06-pushin-weight-migration-procedure.md` —
  the operator procedure
- `scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml`
  — the alias map
- `tests/test_migrate_pushin_weight_records.py` — the test suite
