# pushin_weight migration procedure

> **Plan**: `docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md`
> **Status**: Implemented (commits `0823832` on `feat/pushin-weight-home-pages`).
> **Operator**: anyone running the seed-port script against a fresh or partial
> target database.

This document describes how to run the pushin_weight curated-seed migration
against an x_monitoring.db target database. The migration ports the
hand-curated layer (brands, companies, accounts, hf_orgs, brand_search_terms,
and the 4 lookup-table families with their labels) from the live
`pushin_weight` Postgres database into x_monitoring.db.

## When to run

Run the migration in any of these situations:

- A new x_monitoring.db is being initialized from a source-of-truth
  pushin_weight snapshot.
- The pushin_weight side has been refreshed (new brands, new accounts,
  new search terms) and the curated layer needs to be re-synced.
- A test fixture needs to be regenerated from the live source.

The migration is **idempotent**: re-running against a target that already
has the data is a no-op (every insert is `INSERT OR IGNORE`).

## Prerequisites

- The schema migration `030_brand_rename_to_pushin_weight_slugs.sql` must
  be applied first. This renames 3 brand slugs in place and adds 6 new
  brands + 9 new companies. Without 030, the script's FK lookups for
  `mimo`, `nemo_megatron`, `sakana_ai`, and the 9 new companies will fail
  and the script will drop those source rows with reason "brand not
  seeded" / "company not seeded".

  Apply 030 with: `python -m x_monitor migrate` (or open the target via
  `Store(auto_migrate=True)` which auto-applies on open).

- The pushin_weight Postgres database must be reachable. The script
  invokes `psql` (default path: `/opt/homebrew/opt/postgresql@17/bin/psql`)
  with the connection string passed to `--source-connstr`. If psql is
  installed elsewhere, edit `PSQL_BIN` at the top of the script.

- Python dependencies: `pyyaml` (for the alias map) and `sqlite3` (in
  the standard library). The script does **not** require `psycopg2`; it
  invokes `psql` via `subprocess`.

## Quick-start

```bash
# 1. (One-time) Apply the schema migration
python3 -c "from pathlib import Path; from x_monitor.store import Store; \
  s = Store(Path('data/x_monitoring.db'), auto_migrate=True); s.close()"

# 2. Dry-run to see what the script would do
python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py \
  --target-db data/x_monitoring.db \
  --alias-map scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml \
  --source-connstr "host=localhost port=5432 dbname=pushin_weight user=fuchitalee"

# 3. Inspect the JSON report (printed to stdout; saved to
#    data/migration_logs/migrate-pushin-weight-records-<ts>.json by default)

# 4. Apply for real
python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py \
  --target-db data/x_monitoring.db \
  --alias-map scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml \
  --source-connstr "host=localhost port=5432 dbname=pushin_weight user=fuchitalee" \
  --write
```

## CLI reference

| Flag | Required | Description |
|------|----------|-------------|
| `--target-db PATH` | yes | Path to the target x_monitoring.db |
| `--alias-map PATH` | yes | Path to the alias YAML |
| `--source-connstr STR` | one of | psql connection string |
| `--fixture PATH` | one of | Path to a SQLite fixture file (overrides `--source-connstr`) |
| `--write` | no | Apply changes (default is dry-run) |
| `--report-out PATH` | no | Override the JSON report output path |

The script exits 0 on success (dry-run or write) and 2 on bad arguments.
A failed write (e.g. FK violation) raises an exception with stderr output.

## Alias map

The alias map (`scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml`)
documents every source→target slug mapping the script applies. It has four
sections:

- **brands** — 3 in-place renames (`xiaomi_mimo`→`mimo`, `nvidia_nemo`→
  `nemo_megatron`, `sakana`→`sakana_ai`). The 6 new brands
  (`chatglm`, `wenxin`, `seed`, `sensenova`, `kwaiyii`, `step`) are 1:1
  and not listed.

- **companies** — Two kinds: 9 new (added by migration 030) and 5
  slug-divergent (same company, different slug between source and
  target). The 5 divergent cases are:
  - `deepseek` → `deepseek_co`
  - `inclusion` → `inclusion_ai`
  - `mistral` → `mistral_ai`
  - `stepfun` → `stepfun_inc`
  - `zai` → `zhipu`

  The 11 existing target companies (alibaba, baidu, tencent, xiaomi,
  minimax, moonshot) are 1:1 and not listed.

- **discourse** — 2 aliases (`dunk`→`dunk_yingyang`, `other`→
  `advertising-marketing`). The other 8 keys are 1:1.

- **post_type** — Source has 4 keys (`criticism`, `release`, `other`,
  `hands_on_usage`); target has 6. The source keys are aliased to:
  - `criticism` → `feedback_questions`
  - `release` → `event_announcement`
  - `other` → `advertising_marketing` (underscore; **not** the hyphen
    form used by `discourse_keys`)
  - `hands_on_usage` → `hands_on_usage`

- **sentinels_dropped** — Source's 2 generic-region sentinels
  (`unattributed_chinese_models`, `unattributed_us_labs`) have no target
  equivalent. They are dropped with reason "sentinel-without-target-equivalent".

To edit a mapping, modify the YAML and re-run the script. The script
re-reads the alias map at startup; no code change needed.

## FK ordering

The script applies tables in dependency order to satisfy foreign keys:

1. **discourse_keys** (no FK) + **discourse_labels** (FK → discourse_keys)
2. **post_type_keys** + **post_type_labels**
3. **nationalism_keys** + **nationalism_labels**
4. **roles** + **role_labels**
5. **accounts** (no FK)
6. **brand_search_terms** (FK → brands)
7. **brands_accounts** (FK → brands, accounts, roles)
8. **brands_companies** (FK → brands, companies)
9. **hf_orgs** (FK → companies)

If a child row's parent FK doesn't resolve (e.g. the source brand maps to
a target brand that doesn't exist), the row is dropped with reason
"brand 'X' not seeded" (or similar) and recorded in the report's
`dropped_no_alias` array.

## Report schema

The script emits a structured JSON report. See
`docs/reference/migration-report-schema.md` for the full schema. The
report is printed to stdout and (by default) saved to
`data/migration_logs/migrate-pushin-weight-records-<timestamp>.json`.

## Testing

The companion test file is `tests/test_migrate_pushin_weight_records.py`.
31 tests cover:

- 10 alias resolver unit tests (brand, company, discourse, post_type, role)
- 6 type coercion tests (bool, TIMESTAMPTZ)
- 1 SQLite fixture reader test
- 4 end-to-end TargetWriter tests (dry-run, write, idempotency, dropped-columns)
- 4 lookup-table tests (1:1, alias, label renaming, FK chain)
- 3 brands_accounts FK chain tests
- 1 brands_companies alias test
- 1 hf_orgs alias test
- 1 report-schema stability test
- 1 live-source integration test (gated on `PUSHIN_WEIGHT_PG_CONNSTR`)

Run with:

```bash
PUSHIN_WEIGHT_PG_CONNSTR="host=localhost port=5432 dbname=pushin_weight user=fuchitalee" \
  python3 -m pytest tests/test_migrate_pushin_weight_records.py -v
```

The live-source integration test creates a fresh tmp DB, applies all
migrations 1-30, runs the script with `--write`, and verifies the
post-state row counts match the source.

## Rollback

To roll back the migration:

1. Restore the target DB from the most recent `.pre-U4-apply.*.bak`
   snapshot (the migration script does not create one; the operator
   should snapshot before running).
2. The migration does not modify the source Postgres database; no
   rollback is needed there.

## See also

- `docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md`
  — the plan
- `scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml`
  — the alias map
- `docs/reference/migration-report-schema.md` — the JSON report schema
- `tests/test_migrate_pushin_weight_records.py` — the test suite
