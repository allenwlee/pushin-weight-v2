---
title: "feat: migrate curated seed records from pushin_weight Postgres to x_monitoring.db"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

## Goal Capsule

A one-way, idempotent, dry-run-safe migration that copies the **curated seed layer** of the live `pushin_weight` Postgres database (29 brands, 20 companies, 49 accounts, 62 brands_accounts edges, 11 brands_companies, 21 hf_orgs, 72 brand_search_terms, plus the 6 lookup-table families) into the live `x_monitoring.db` (SQLite, v1.8 + migration 028). Source-of-truth is the live `pushin_weight` Postgres cluster (running locally on `localhost:5432`); the markdown snapshot in `pushin_weight/docs/reference/db-records-live.md` is stale and is **not** used. Posts/products/runs are out of scope — source is empty for those.

A live Postgres → SQLite dialect conversion is the bulk of the work: TEXT PK → INTEGER surrogate PK + UNIQUE nickname; TIMESTAMPTZ → ISO TEXT; boolean → INTEGER 0/1; `case_insensitive` collation → case-sensitive ASCII slugs. 6 source brand_ids need new rows in `x_monitoring.brands` (`chatglm`, `wenxin`, `seed`, `sensenova`, `kwaiyii`, `step` — each paired with a sibling brand already present); 3 target brand_ids are renamed in place (`xiaomi_mimo` → `mimo`, `nvidia_nemo` → `nemo_megatron`, `sakana` → `sakana_ai`) to match source. 2 discourse keys are aliased (`dunk` → `dunk_yingyang`, `other` → `advertising-marketing`); all other lookups port 1:1. Postgres-only columns (`raw_payload jsonb`, `notes`) are dropped silently and logged.

The migration runs as a CLI script (`scripts/2026-07-06-001-migrate-pushin-weight-records.py`), mirrors the dry-run/idempotent/CLI shape of `scripts/2026-06-25-005-seed-companies-brands-from-csv.py`, and emits a per-table structured diff report (rows_inserted / rows_skipped_duplicate / rows_added_to_brands / rows_renamed / rows_dropped_no_alias) to stdout + a sibling JSON file under `data/migration_logs/`. The script runs against a copy of the live DB by default; `--write` opts into the destructive apply.

## Product Contract

### Summary

One CLI script + a supporting SQL migration that materializes the pushin_weight curated seed into x_monitoring.db with explicit per-row diff visibility. Re-running the script against the same target is a no-op; running it after a source refresh is a delta apply. Brand and discourse aliases are operator-curated in a YAML config file alongside the script so future renames don't require code edits.

### Problem Frame

`pushin_weight` was an earlier Django/Postgres fork of x-monitor that the user maintained in parallel from late-May through early-July 2026. On 2026-06-30 the schema was migrated to natural-key PKs (`docs/plans/2026-06-30-191516-refactor-natural-key-pks-plan.md`); on 2026-07-01 the curated seed layer was loaded and a snapshot was exported to `docs/reference/db-records-live.md`. The live Postgres DB is still running locally (`localhost:5432/pushin_weight`) and contains a richer seed than x-monitor — 9 source brand_ids, 1 company, 3 hf_orgs, 11 brand_search_terms (count for the source-only brands), 10 discourse keys, 6 nationalism keys, plus the 3 generic-region sentinel brands. x-monitor only needs the curated layer (not posts/products/runs — source is empty).

The merge is non-trivial because the schemas have diverged:
- **PK shape**: source uses natural-key TEXT PKs (`brands.id varchar(64)`); target uses INTEGER surrogate + UNIQUE `nickname` TEXT. Source's `brands.id` IS the slug; target's `brands.nickname` is the slug.
- **Dialect**: source has `case_insensitive` collation, `boolean`, `jsonb`, `timestamp with time zone`. Target has none of these.
- **Naming drift**: source uses `mimo`, `nemo_megatron`, `sakana_ai`; target uses `xiaomi_mimo`, `nvidia_nemo`, `sakana` — same accounts, different slugs. Source has 6 brands absent from target (`chatglm`, `wenxin`, `seed`, `sensenova`, `kwaiyii`, `step`); target has 1 brand absent from source (`test_brand`, a test fixture, deliberately skipped).
- **Discourse taxonomy drift**: source's `dunk` was renamed `dunk_yingyang` in target (more descriptive); source's `other` was renamed `advertising-marketing` in target (specialized, not miscellaneous).
- **Sentinel sprawl**: source has 3 sentinels (`_unattributed`, `unattributed_chinese_models`, `unattributed_us_labs`); target has 1 (`_unattributed`). The 2 extra sentinels are dropped — `_unattributed` continues to be the canonical brandless fallback.

The script needs to do the conversion in one pass with a visible diff, so the operator can audit exactly what was inserted, what was renamed, and what was dropped before committing.

### Requirements

- **R1**: Migrate the curated seed tables (`brands`, `companies`, `accounts`, `brands_accounts`, `brands_companies`, `hf_orgs`, `brand_search_terms`, `roles`, `role_labels`, `hf_types`, `hf_type_labels`, `post_types`, `post_type_labels`, `sentiments`, `sentiment_labels`, `discourse`, `discourse_labels`, `nationalism`, `nationalism_labels`) from the live `pushin_weight` Postgres DB to `x_monitoring.db`.
- **R2**: Skip all post-related tables (`posts`, `posts_brands`, `posts_brands_mentions`, `posts_brands_signals`, `posts_brands_discourse`, `account_post_appearances`) and the `runs` table — source is empty for these, and the live x-monitor `runs` table is the canonical state for the main loop.
- **R3**: The migration must be **idempotent** — re-running it against an already-migrated target is a no-op (`INSERT OR IGNORE` on natural keys; FK resolution by slug).
- **R4**: The migration must be **dry-run by default** — the script prints the diff to stdout and writes the structured report to `data/migration_logs/migrate-pushin-weight-records-<timestamp>.json`, but does not touch the target DB until `--write` is passed.
- **R5**: 9 source brand_ids require reconciliation: 6 need new rows in `brands` (`chatglm`, `wenxin`, `seed`, `sensenova`, `kwaiyii`, `step` — none in target), and 3 are present in target under different slugs (`xiaomi_mimo` ↔ `mimo`, `nvidia_nemo` ↔ `nemo_megatron`, `sakana` ↔ `sakana_ai`) and require in-place rename. The alias map (YAML) documents the source↔target mapping for the script; the SQL migration performs the 3 in-place renames. Each rename/add is logged in the diff report.
- **R6**: 3 target brand_ids (`xiaomi_mimo`, `nvidia_nemo`, `sakana`) must be renamed to source slugs (`mimo`, `nemo_megatron`, `sakana_ai`) via a SQL migration. Since child FK columns are INTEGER-storing-id (per migration 020/023), the rename is a single `UPDATE brands SET nickname=… WHERE nickname=…` — no FK cascade is needed because the surrogate ids are unchanged. After rename, all `enabled_models` entries in `config.yaml` update to the new slugs.
- **R7**: 9 missing source companies (`meta`, `nvidia`, `bytedance`, `sensetime`, `lg_ai`, `sakana`, `kuaishou_co`, `upstage_co`, `01ai`) must be added as new rows in `x_monitoring.companies`. The existing 11 companies stay as-is.
- **R8**: 2 discourse-key aliases (`dunk` → `dunk_yingyang`, `other` → `advertising-marketing`) and all other discourse/nationalism/post_type/sentiment/hf_type/role labels port 1:1. The `advertising-marketing` key is **not** a miscellaneous fallback — it's a specialized taxonomy key with its own classifier prompt (future work); for this migration it aliases source `other` cleanly.
- **R9**: 2 source-only sentinels (`unattributed_chinese_models`, `unattributed_us_labs`) are dropped — only `_unattributed` survives. All brandless posts continue to route to `_unattributed`.
- **R10**: Postgres-only columns (`raw_payload jsonb`, `notes`) and any non-NULL `bio`/`bio_en`/`bio_zh_cn` data are dropped silently and logged per-row in the diff report.
- **R11**: The script must emit a structured diff report (JSON) with per-table counts and per-row detail for: rows_inserted, rows_skipped_duplicate, rows_added_to_brands, rows_renamed, rows_dropped_no_alias.
- **R12**: The script must validate that the live Postgres DB is reachable before doing anything destructive, and refuse to run if `--write` is passed but the DB is unreachable.
- **R13**: Tests cover the per-table migration logic, the alias maps, the dry-run vs. write semantics, and the diff-report schema. Tests do NOT require a live Postgres — they use a captured fixture dump or a SQLite-shimmed stub.

### Scope Boundaries

#### In scope

- The 19 source tables listed in R1.
- A SQL migration for the 3 in-place brand-id renames (R6) and the 6 new brands + 9 new companies (R5 + R7).
- An alias map (YAML) for brand, company, discourse, and any other lookup-table rename.
- The migration script (CLI, dry-run, idempotent).
- The diff-report writer (stdout + JSON file).
- Tests for the script.

#### Deferred for later

- Posts/products/runs (out of scope per R2 — source is empty; main loop remains canonical).
- The specialized `advertising-marketing` classifier prompt — the migration renames source `other` → target `advertising-marketing` cleanly, but a dedicated prompt for the latter is future work (captured in `### Assumptions`).
- A reverse-direction sync (x-monitor → pushin_weight) — not requested.
- Real-time source freshness checks — the script always reads the live DB at run time; if the live DB is unreachable, the script errors out per R12. There is no fallback to the markdown snapshot.

#### Outside this product's identity

- Postgres → SQLite for the `runs` table (x-monitor runs are file-based under `data/runs/`).
- Any schema change to x-monitor beyond the migration that does the 3 brand renames + 18 new rows.

### Key Technical Decisions

- **KTD1**: Live `pushin_weight` Postgres is the canonical source; the markdown snapshot is explicitly **not** used. The script validates the DB is reachable via `psycopg2` / `pg_isready` before doing anything (R12). Reason: snapshot is 5 days stale and missing the 2 generic-region sentinels + the 10th discourse key (`other`).
- **KTD2**: The 3 brand renames (`xiaomi_mimo`→`mimo`, `nvidia_nemo`→`nemo_megatron`, `sakana`→`sakana_ai`) are done via a new SQL migration (`029_brand_rename_to_pushin_weight_slugs.sql`) with `PRAGMA foreign_keys=OFF` around the UPDATE statements (mirroring the migration-runner pattern from migration 020). Since child FK columns are INTEGER-storing-id (per migration 020/023), the rename is a single `UPDATE brands SET nickname=…` — no FK cascade is needed because surrogate ids are unchanged. Reason: this preserves all FK references automatically.
- **KTD3**: 6 new brands and 9 new companies are added via the same migration (`029_…`), with `INSERT OR IGNORE` semantics so the migration is itself idempotent. The 6 new brands (`chatglm`, `wenxin`, `seed`, `sensenova`, `kwaiyii`, `step`) use the source's accent_color + display_name values — note that target's `accent_color` is currently `#9ca3af` (default gray) for most, but source has actual curated colors (e.g. `#84cc16` for mimo, `#dc2626` for ernie).
- **KTD4**: The migration script's data layer uses direct SQL (`INSERT OR IGNORE` on the TEXT-natural-key columns, then resolving the surrogate INTEGER id via `last_insert_rowid()` or a follow-up SELECT) rather than the existing `Store` Python API. Reason: `Store.upsert_account` gates on `brand_id in KNOWN_MODELS` (raises ValueError for any brand not in the hardcoded frozenset), and the 9 source-only brands aren't in that frozenset. The script opens its own `sqlite3` connection in addition to `Store` (which it uses for read-back verification only).
- **KTD5**: Postgres TIMESTAMPTZ values are converted to ISO TEXT via Python's `datetime.isoformat()` (preserves the `+09:00` offset that source emits). boolean → `int(bool)` (0/1). `jsonb raw_payload` → dropped. `case_insensitive` collation → case-sensitive ASCII slugs (target's `brands.nickname` is `TEXT` without collation, so `"Kuaishou"` ≠ `"kuaishou"` — but source uses lowercase slugs consistently, so no collisions in practice).
- **KTD6**: The alias map lives in a YAML file (`scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml`) for operator-editability without code changes. Schema: `{ brands: {target_slug: source_slug}, companies: {…}, discourse: {…} }`. The script reads this at startup and merges it with the hardcoded brand-rename migration (KTD2) — the YAML is the runtime layer, the SQL migration is the schema layer.
- **KTD7**: The diff report uses a stable JSON schema (`docs/notes/2026-07-06-migration-report-schema.md`) with per-table objects: `{ table, source_rows, target_rows_before, target_rows_after, inserted: [...], skipped_duplicate: [...], renamed: [{from, to}], dropped_no_alias: [...] }`. Each row carries its source row as a JSON snapshot for auditability.
- **KTD8**: The script's dry-run mode prints the report to stdout AND writes it to disk (so the operator can `git diff` the JSON). The `--write` flag is required to apply; without it, the script exits before opening a write transaction on the target.
- **KTD9**: Tests use a synthetic Postgres fixture (a SQLite file mimicking the source schema, generated from a captured `pg_dump` snapshot) rather than mocking psycopg2. Reason: `psycopg2` mocking hides real shape bugs; a fixture-derived SQLite stub lets the tests exercise the actual SQL translation logic.

### Acceptance Examples

- **AE1**: With `--dry-run` against an empty `x_monitoring.db`, the report shows `{brands: inserted=[…6 new brands + 3 renames…], companies: inserted=[…9 new companies…], …}` and zero rows are written to the target DB.
- **AE2**: With `--write` against an empty target, after the script exits the target has 27 brands + 1 sentinel (vs 21 before), 20 companies (vs 11 before), 49 accounts, 62 brands_accounts, etc.
- **AE3**: Re-running the script with `--write` against the post-migration target is a no-op — every row is `skipped_duplicate` and the diff report's `inserted` arrays are empty.
- **AE4**: When source has `discourse_key='dunk'` and target has `dunk_yingyang`, the diff report's `renamed` array contains `{from: 'dunk', to: 'dunk_yingyang', row_count: 1}`.
- **AE5**: When source `brands` contains `unattributed_chinese_models`, the diff report's `dropped_no_alias` array contains `{row: {id: 'unattributed_chinese_models', …}, reason: 'sentinel-without-target-equivalent'}`.

## Planning Contract

### Implementation Units

### U1. Migration 029: brand rename + new rows

**Goal**: SQL migration that renames 3 target brand_ids to source slugs, adds 6 new brands, and adds 9 new companies. Idempotent via `INSERT OR IGNORE` and conditional UPDATE.

**Requirements**: R5, R6, R7.

**Dependencies**: —

**Files**:
- `x-monitoring/x_monitor/migrations/029_brand_rename_to_pushin_weight_slugs.sql` (create)
- `x-monitoring/tests/test_migration_029_brand_rename.py` (create)

**Approach**: Single migration with `PRAGMA foreign_keys=OFF` around the UPDATE/INSERT block (mirrors migration 020). Three sections:
1. **Renames** — `UPDATE brands SET nickname='mimo' WHERE nickname='xiaomi_mimo'`, plus the 2 other renames. Since child FK columns are INTEGER-storing-id (per migration 020/023), no FK cascade is needed — the rename only touches `brands.nickname`, surrogate ids are unchanged, and all FK references remain valid automatically.
2. **New brands** — `INSERT OR IGNORE INTO brands(nickname, display_name, accent_color, is_sentinel, created_at, display_name_en, display_name_zh_cn) VALUES (?, ?, ?, 0, datetime('now'), ?, ?)` for each of the 6 truly-new brands: `chatglm`, `sensenova`, `step`, `kwaiyii`, `wenxin`, `seed`. Use accent_color + display_name from `pushin_weight.brands`.
3. **New companies** — `INSERT OR IGNORE INTO companies(nickname, display_name, hq_country, created_at, display_name_en, display_name_zh_cn)` for each of `meta`, `nvidia`, `bytedance`, `sensetime`, `lg_ai`, `sakana`, `kuaishou_co`, `upstage_co`, `01ai`. Use display values from `pushin_weight.companies`.

Re-enable FKs at the end. Update `config.yaml` `enabled_models` to use new slugs (`mimo`, `nemo_megatron`, `sakana_ai`) — handled separately in U5.

**Patterns to follow**: `x-monitoring/x_monitor/migrations/020_text_to_integer_pks_all_tables.sql` for the FK-off/rename/FK-on pattern; `x-monitoring/x_monitor/migrations/024_seed_missing_brands.sql` for the brand-seed INSERT shape.

**Test scenarios**:
- Migration 029 applies on a fresh DB (migrations 001-028 + 029) without error.
- Idempotency: re-applying 029 is a no-op (no duplicate nicknames, no row count change).
- After apply, `brands.nickname IN ('mimo', 'nemo_megatron', 'sakana_ai')` — old slugs gone.
- After apply, `brands` has 30 rows (29 source + `_unattributed` sentinel — but `unattributed_chinese_models` and `unattributed_us_labs` are NOT added since this migration only renames/adds, doesn't drop source sentinels; the script handles source-sentinel collapse in U4).
- FK references updated: any `brand_search_terms.brand_id` that pointed at the old slugs now points at the new slugs (the migration cascades via direct UPDATE before FKs are re-enabled).
- `companies` has 20 rows (11 existing + 9 new) with no duplicates.
- Full-stack: apply migrations 001-029 in sequence on a fresh DB, then assert brand + company counts match.

**Verification**: `pytest tests/test_migration_029_brand_rename.py` passes; `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands"` returns 27 (20 + 6 new + sentinel); `SELECT COUNT(*) FROM companies` returns 20.

---

### U2. Alias map YAML

**Goal**: Operator-editable alias map for brand slugs, company slugs, and discourse keys that the migration script reads at startup.

**Requirements**: R5, R8.

**Dependencies**: — (read by U4, but the file itself is independent of U1/U3).

**Files**:
- `x-monitoring/scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml` (create)

**Approach**: YAML schema:
```yaml
# Brand slug aliases. Each entry is `target_slug: source_slug`.
# The SQL migration in U1 performs the 3 in-place renames; this map
# documents the source→target mapping for operator reference and is
# consulted by the script when reading source data.
brands:
  mimo: mimo
  nemo_megatron: nemo_megatron
  sakana_ai: sakana_ai
  # chatglm, sensenova, step, kwaiyii, wenxin, seed are 1:1 (no alias)
  # _unattributed, unattributed_chinese_models, unattributed_us_labs:
  #   handled by sentinel-collapse rule (see discourse/sentinels below)

companies:
  meta: meta
  nvidia: nvidia
  bytedance: bytedance
  sensetime: sensetime
  lg_ai: lg_ai
  sakana: sakana_co
  kuaishou_co: kuaishou_co
  upstage_co: upstage_co
  01ai: 01ai
  # the 11 existing target companies (mistral, alibaba, baidu, etc.)
  # are 1:1 with source.

discourse:
  dunk_yingyang: dunk
  advertising-marketing: other
  # absurdist_meme, ai_slop_critique, cope, distillation_accusation,
  # fud, genuine_hype, sarcasm, self_deprecation are 1:1.

sentinels_dropped:
  - unattributed_chinese_models
  - unattributed_us_labs

# Lookup tables not listed above (nationalism, post_type, sentiment,
# hf_type, role) are treated as 1:1 by slug match on the key column.
# If a future migration requires aliasing for one of these families,
# add a section here.
```

**Patterns to follow**: `x-monitoring/config.yaml` for YAML formatting style.

**Test scenarios**: YAML file parses; each alias key resolves to a non-empty value; all source brand_ids referenced by `brands_accounts` are covered (either 1:1 or via alias); all source discourse_keys referenced by labels are covered.

**Verification**: `python -c "import yaml; yaml.safe_load(open('scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml'))"` exits 0; manual review of all 27 source brands + 20 source companies + 10 source discourse_keys against the map shows 100% coverage.

---

### U3. Postgres fixture (SQLite shim) for tests

**Goal**: A SQLite file that mimics the live `pushin_weight` Postgres schema and contains a captured snapshot of the curated seed tables, so tests don't need a live Postgres.

**Requirements**: R13.

**Dependencies**: — (built once, then read by U4 tests).

**Files**:
- `x-monitoring/tests/fixtures/pushin_weight_seed.sqlite` (create, checked in)
- `x-monitoring/tests/fixtures/build_pushin_weight_fixture.py` (create, regenerates the fixture from a live DB; CI runs it nightly to refresh)

**Approach**: The fixture script connects to live `pushin_weight` via `psycopg2`, reads the 19 source tables, and writes them into a SQLite file with the same column names but converted types (TIMESTAMPTZ → ISO TEXT, boolean → INTEGER 0/1, `case_insensitive` collation stripped). The fixture file is checked in (~50KB) so tests run offline. The builder script is checked in too, so the fixture can be regenerated when the source DB evolves.

Schema mismatch: the source has natural-key TEXT PKs (no INTEGER surrogate). The fixture preserves that shape — when the migration script reads from the fixture, it sees `brands.id='mimo'` directly, not `brands.nickname='mimo'` + `brands.id=42`. The script has a small adapter that handles both shapes (live and fixture).

**Patterns to follow**: `x-monitoring/tests/fixtures/` (if exists) for fixture-file conventions; `x-monitoring/scripts/post_fetch_smoketest.py` for "build a fixture for offline use" shape.

**Test scenarios**: Fixture file exists and is <100KB; builder script runs against a live DB (skip if no DB); fixture contains 29 brands, 20 companies, 49 accounts, etc.

**Verification**: `ls -lh tests/fixtures/pushin_weight_seed.sqlite` shows <100KB; `sqlite3 tests/fixtures/pushin_weight_seed.sqlite "SELECT COUNT(*) FROM brands"` returns 29.

---

### U4. Migration script

**Goal**: The CLI script `scripts/2026-07-06-001-migrate-pushin-weight-records.py` that reads source from live Postgres (or fixture), applies the alias map, and writes to x_monitoring.db with dry-run semantics by default.

**Requirements**: R1, R2, R3, R4, R8, R9, R10, R11, R12.

**Dependencies**: U1 (schema must be ready — 3 brand renames applied), U2 (alias map), U3 (fixture for tests).

**Files**:
- `x-monitoring/scripts/2026-07-06-001-migrate-pushin-weight-records.py` (create)
- `x-monitoring/tests/test_migrate_pushin_weight_records.py` (create)

**Approach**: Three-layer script:

**Layer 1 — Source reader.** Connect to live Postgres via `psycopg2` (or read fixture SQLite via `sqlite3`). Per table, read all rows. Convert types: TIMESTAMPTZ → ISO TEXT (via `datetime.isoformat()`), `bool` → `int(bool)`, drop `raw_payload` and `notes`. Yield a stream of `dict[str, Any]` rows.

**Layer 2 — Alias resolver.** Load `aliases.yaml`. For each source row, look up the target slug via the alias map. If a source brand/company has no alias and no 1:1 match, classify as `dropped_no_alias` with a reason. For discourse keys, apply `discourse` aliases.

**Layer 3 — Target writer.** Open target `x_monitoring.db` via a fresh `sqlite3` connection (NOT via `Store`, since `Store.upsert_account` rejects unknown brand_ids). Per table:
1. Resolve the TEXT slug to the INTEGER surrogate id (via `SELECT id FROM brands WHERE nickname=?`).
2. `INSERT OR IGNORE` on the natural key (e.g., `accounts.author_id`).
3. `SELECT id FROM accounts WHERE author_id=?` to get the surrogate id for cross-table FKs.
4. `INSERT OR IGNORE` on the FK table (e.g., `brands_accounts`).

In dry-run mode, build the report but never open a write transaction. In write mode, wrap each table in a `BEGIN/COMMIT` block.

The diff report accumulates per-table objects: `{ table, source_rows: int, target_rows_before: int, target_rows_after: int, inserted: [row_dict, …], skipped_duplicate: [row_dict, …], renamed: [{from, to, row}, …], dropped_no_alias: [{row, reason}, …] }`. Print to stdout; write to `data/migration_logs/migrate-pushin-weight-records-<timestamp>.json`.

**CLI**:
```
python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py \
    --source-db "postgres://pushin_weight:pushin_weight@localhost:5432/pushin_weight" \
    --target-db data/x_monitoring.db \
    --alias-map scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml \
    [--write] [--fixture tests/fixtures/pushin_weight_seed.sqlite]
```

`--write` is required for any side-effecting write to the target. Without it, the script is fully dry-run. `--fixture` overrides `--source-db` for offline testing.

**Patterns to follow**: `x-monitoring/scripts/2026-06-25-005-seed-companies-brands-from-csv.py` for CLI/dry-run/JSON-report shape; `x-monitoring/scripts/dump_http_log.py` for CLI argument style.

**Test scenarios**:
- **Source connection validation**: script exits non-zero if `--source-db` is unreachable and `--fixture` is not given.
- **Dry-run vs. write**: with `--dry-run` (default), target DB is unchanged after script exit (verify via mtime).
- **Idempotency**: running `--write` twice produces the same final state; second run's report shows `inserted=[]` and `skipped_duplicate=[…all rows…]`.
- **Per-table coverage**: report shows rows_inserted + rows_skipped_duplicate + rows_dropped for each of the 19 source tables.
- **Brand rename propagation**: source brand `mimo` rows end up in target brand `mimo` (post-U1-rename); source brand `xiaomi_mimo` rows (if any in source) end up mapped to `mimo` too via the alias map.
- **Discourse aliasing**: source `discourse_key='dunk'` ends up as `discourse_key='dunk_yingyang'` in target.
- **Sentinel collapse**: source `unattributed_chinese_models` rows are in `dropped_no_alias` with reason `"sentinel-without-target-equivalent"`.
- **FK ordering**: brands → companies → accounts → brands_accounts → brands_companies → hf_orgs → brand_search_terms → lookup-table parents → lookup-table labels (each parent inserted before its children reference it).
- **raw_payload drop**: source rows with non-NULL `raw_payload` are inserted into target with `raw_payload` silently dropped; the report's `dropped_no_alias` (or a separate `dropped_column` list) contains one entry per dropped column.
- **TIMESTAMPTZ conversion**: source `last_seen_at=2026-07-01T15:06:46.248525+09:00` ends up as the same string in target's TEXT column (no TZ normalization).
- **Report schema stability**: the JSON report conforms to `docs/notes/2026-07-06-migration-report-schema.md`.

**Verification**: `pytest tests/test_migrate_pushin_weight_records.py` passes (≥15 tests covering dry-run, write, idempotency, alias resolution, FK ordering, sentinel collapse, raw_payload drop, TIMESTAMPTZ conversion, report schema); manual smoke run against a copy of the live target DB shows the report has the expected shape.

---

### U5. config.yaml update for renamed slugs

**Goal**: Update `enabled_models` (and any other brand-slug references in config.yaml) to use the new slugs (`mimo`, `nemo_megatron`, `sakana_ai`).

**Requirements**: R6.

**Dependencies**: U1 (SQL migration must be applied first so the FK targets exist).

**Files**:
- `x-monitoring/config.yaml` (modify: 3 line edits in `enabled_models` and 3 line edits in `call_b_groups`)

**Approach**: Mechanical find/replace:
- `xiaomi_mimo` → `mimo`
- `nvidia_nemo` → `nemo_megatron`
- `sakana` → `sakana_ai`

Apply to all sections of `config.yaml` that reference these slugs (`enabled_models`, `call_b_groups`, possibly `query_rot_streak_threshold_per_model` — but that's empty for these 3). Verify with `grep -n -E "xiaomi_mimo|nvidia_nemo|^.*sakana$" config.yaml` after the edit (the `sakana$` check is a bit loose; also grep for `sakana:` to catch any other reference).

**Patterns to follow**: Existing `config.yaml` formatting.

**Test scenarios**: After edit, `grep -n -E "xiaomi_mimo|nvidia_nemo" config.yaml` returns no matches; `grep -n "sakana" config.yaml` shows only `sakana_ai` (no bare `sakana:` line); the YAML still parses (`python -c "import yaml; yaml.safe_load(open('config.yaml'))"` exits 0).

**Verification**: `pytest tests/test_config_yaml.py` (or whatever validates config.yaml structure) passes; the dashboard's `read_brands()` returns the renamed brands; no test fails that was passing before.

---

### U6. End-to-end smoke test + docs

**Goal**: A test that runs the full pipeline (U1 + U4 + U5) against the fixture, and a docs note describing the migration procedure for future operators.

**Requirements**: R1-R13 (system-level).

**Dependencies**: U1, U2, U3, U4, U5.

**Files**:
- `x-monitoring/tests/test_migrate_pushin_weight_e2e.py` (create)
- `x-monitoring/docs/notes/2026-07-06-pushin-weight-migration-procedure.md` (create)
- `x-monitoring/docs/reference/migration-report-schema.md` (create)

**Approach**: The e2e test:
1. Spin up a temp target SQLite DB with migrations 001-028.
2. Apply migration 029 (U1).
3. Update a copy of `config.yaml` to the renamed slugs (U5).
4. Run the migration script with `--source-db=fixture --target-db=temp_target --write` (U4).
5. Assert the temp target has 27 brands + 1 sentinel. Source contributes 27 real brands after sentinel-collapse; U1 adds 6 new brands and renames 3 in place. Target starts at 21 (20 + 1 sentinel), goes to 27 after U1; the script's `INSERT OR IGNORE` is a no-op for the 6 already-present new brands and the 3 just-renamed ones, plus the 18 source brands that map 1:1 to existing target brands.
6. Assert 20 companies (11 existing + 9 from U1).
7. Assert 49 accounts, 62 brands_accounts, 21 hf_orgs, 72 brand_search_terms.
8. Assert `discourse_labels` has 20 rows (target already has 10 keys × 2 locales = 20 labels including the renamed `dunk_yingyang` and `advertising-marketing`; the script's `INSERT OR IGNORE` is a no-op for all 20 labels).

The test asserts these counts and asserts the diff report is non-empty (operator did get to see what happened).

The docs note describes the procedure: when to run this migration, what the alias map is for, how to add new aliases, what the sentinel-collapse rule means, and where the report files live. The schema doc pins the JSON report shape.

**Patterns to follow**: `x-monitoring/tests/test_seed_companies_brands_from_csv.py` for e2e test shape; `x-monitoring/docs/notes/` for procedural notes.

**Test scenarios**: Full pipeline runs in <30s; all assertions pass; the docs files exist and are non-empty.

**Verification**: `pytest tests/test_migrate_pushin_weight_e2e.py` passes; the docs files are readable and cover the procedure end-to-end.

### Open Questions

- **Q1**: Should the migration also port `runs` table rows from source? Currently scoped out (R2) because source has 0 `runs` rows. If source grows, this becomes a follow-up unit in a separate plan. **Tracked here so it's not silently dropped.**
- **Q2**: The 3 brand renames (`xiaomi_mimo`→`mimo` etc.) are operator-confirmed in this session, but the renames also affect `data/queries/<brand>.yaml` and `data/accounts/<brand>.yaml` — those files are not in the migration's scope. **Tracked as a follow-up unit in a separate plan if needed after U1 lands.**
- **Q3**: The `advertising-marketing` discourse key needs a dedicated classifier prompt in the future (per session-2026-07-06). The migration aliases source `other` to it cleanly (R8), but the prompt + taxonomy refinement is a separate plan.

### Deferred to Follow-Up Work

- **D1**: A specialized classifier prompt for `advertising-marketing` (mentioned in session-2026-07-06). Will be tracked in a future `feat/discourse-advertising-marketing-prompt` plan.
- **D2**: Re-homing `data/queries/` and `data/accounts/` files under the new brand slugs (`mimo`, `nemo_megatron`, `sakana_ai`) if/when the existing files are accessed by slug rather than by display_name.
- **D3**: Reverse-direction sync (x-monitor → pushin_weight) — explicitly out of scope this round, but the JSON report schema is designed to be reusable.

### Verification Contract

The plan is complete when:

1. Migration 029 applies on a fresh DB; brand and company counts match R5+R6+R7.
2. `config.yaml` uses new slugs and still parses.
3. The migration script runs against the fixture in dry-run mode and emits a non-empty, valid JSON report.
4. The migration script runs against the fixture in `--write` mode and produces a target DB with the expected row counts.
5. Re-running the script with `--write` against the same target is a no-op (idempotency).
6. All tests pass: `pytest tests/test_migration_029_brand_rename.py tests/test_migrate_pushin_weight_records.py tests/test_migrate_pushin_weight_e2e.py`.
7. The docs files describe the procedure end-to-end and pin the report schema.

### Definition of Done

The migration is "done" when an operator can:

1. Read `docs/notes/2026-07-06-pushin-weight-migration-procedure.md` and understand what the script does.
2. Run `python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py --target-db data/x_monitoring.db` and see a dry-run report in stdout + JSON.
3. Inspect the JSON report and verify the alias resolutions are correct.
4. Re-run with `--write` to apply.
5. Re-run with `--write` a second time and see all rows classified as `skipped_duplicate`.
6. Continue using the dashboard normally (no broken FKs, no missing brands).

### Assumptions

- **A1**: The live `pushin_weight` Postgres DB at `localhost:5432` is reachable from the migration runner's machine (it is from the dev's local box). The script validates this with `pg_isready` and exits cleanly if not (R12).
- **A2**: The 3 brand renames (`xiaomi_mimo`→`mimo`, `nvidia_nemo`→`nemo_megatron`, `sakana`→`sakana_ai`) are the correct canonical names — confirmed by the user in session-2026-07-06 ("mimo and nemo_megatron are not separate, they should just be renamed (rename the target)"). The renames apply to all FK references in the target DB, including any future tables that reference `brands.nickname`.
- **A3**: The 2 discourse-key aliases (`dunk`→`dunk_yingyang`, `other`→`advertising-marketing`) are semantically correct — confirmed by the user. **`advertising-marketing` is a specialized taxonomy key with its own future classifier prompt, NOT a miscellaneous fallback.** The migration aliases source `other` → target `advertising-marketing` because both are "the catch-all bucket" at the time of migration, but the target taxonomy will tighten this key with a dedicated prompt later (D1).
- **A4**: Posts/products/runs are out of scope because source has 0 rows in each. The live x-monitor `runs` table remains the canonical state for the main loop.
- **A5**: The fixture file (`tests/fixtures/pushin_weight_seed.sqlite`) is checked in for offline tests and regenerated nightly by the builder script. The fixture uses SQLite types, not Postgres types, so the migration script's type-conversion logic is exercised against both (live and fixture) in the e2e test.
- **A6**: Source bios (`bio`, `bio_en`, `bio_zh_cn`) are all NULL in the live DB (verified in session-2026-07-06), so the drop is silent in practice. If a future pushin_weight DB has populated bios, they'll be dropped with a per-row log entry (R10).
- **A7**: The `unattributed_chinese_models` and `unattributed_us_labs` sentinels are intentionally dropped (R9) — confirmed by the user. All brandless posts continue to route to `_unattributed`. If future x-monitor work needs generic-region sentinels, they can be added back as new rows in `brands` with `is_sentinel=1`.