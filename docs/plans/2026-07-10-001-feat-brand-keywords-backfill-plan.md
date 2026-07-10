---
title: Backfill `brand_keywords` table from query yaml Q2 paren groups
date: 2026-07-10
type: feat
status: ready
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# Context

The `probe_filter_yield` probe reads `brand_keywords` from the live DB via `store.read_brand_keywords()` to compute `n_kept_after_filter`. The DB has 90 rows covering 8 of 20+ brands (deepseek, glm, inclusionai, llama, minimax, moonshot_kimi, qwen, xiaomi_mimo). The other 12+ brands have zero entries, which makes `_kept_after_filter` return 0 for any post mentioning those brands — even when the post text clearly contains a brand token like `NeMo` or `Upstage`.

The query yaml files at `data/queries/<brand>.yaml` are the operator-curated source of truth for brand tokens (per operator 2026-07-09: "yaml is canon for now, DB will be canon in the future"). The query construction path at `x_monitor/query_plan.py:_load_brand_tokens_per_model` already extracts brand tokens from Q2/Q3/Q5/Q6 paren groups. The backfill reuses that parser to populate the DB table, which moves us toward "DB will be canon" without changing what the tokens are.

**Outcome:** Every brand in `enabled_models` has at least its Q2 paren-group tokens in the `brand_keywords` table. The probe's `_kept_after_filter` returns nonzero for posts mentioning those brands. Production `attribute_to_brands` (which may also read from this index) gets the same coverage. Idempotent — re-running is a no-op.

# Files to modify

| File | Change |
|---|---|
| `x-monitoring/x_monitor/migrations/034_backfill_brand_keywords_from_yaml.sql` | **New file.** SQL that INSERT OR IGNOREs the parsed tokens into `brand_keywords`. Static — tokens enumerated explicitly per brand. |
| `x-monitoring/scripts/backfill_brand_keywords.py` | **New file.** One-shot script that reads `data/queries/*.yaml`, parses Q2 paren groups via the existing `_load_brand_tokens_per_model` logic (extracted to a reusable module-level helper if needed), INSERTs into `brand_keywords` for every brand currently in `enabled_models`. Idempotent. |
| `x-monitoring/x_monitor/query_plan.py` | Extract `_load_brand_tokens_per_model` into a stable import surface (e.g., expose via `from x_monitor.query_plan import parse_brand_tokens`) so the script can reuse it without duplicating the parser. |
| `x-monitoring/tests/test_backfill_brand_keywords.py` | **New file.** 5 tests: hermetic round-trip, idempotency, no-op when already populated, exact count of missing brands before/after, parser extracts expected tokens per brand. |
| `x-monitoring/tests/test_query_plan.py` (or wherever `_load_brand_tokens_per_model` is currently tested) | Adjust test if extraction changes the import path. |
| `docs/notes/2026-07-10-backfill-brand-keywords-apply-report.md` | **New file.** Apply report — pre/post row counts, probe rerun with new `kept` numbers, paren-group token counts per brand. |

Plan docs from earlier (`docs/plans/2026-07-09-001-feat-list-yaml-db-sync-plan.md`, `docs/plans/2026-07-08-004-feat-filter-yield-ramp-probe-plan.md`) are historical; no edits.

# Implementation

## 1. Extract reusable parser from `query_plan.py`

`x_monitor/query_plan.py:_load_brand_tokens_per_model` (lines 171-216) is the existing parser. It's currently a module-private helper used only by `plan_calls`. Promote it to a public surface:

- Rename to `parse_brand_tokens(enabled_models: list[str], queries_dir: Path) -> dict[str, list[str]]` (drop the `_load_` prefix, keep `_per_model` suffix optional — match the existing `compile_keyword_index` naming style).
- Move the inline paren parser to a tiny helper `_parse_first_paren_group(query_string: str) -> list[str]` so both the migration-time backfill and the runtime call share the exact same logic.
- Update `_build_brand_wide_query` to call the renamed function.
- One new test against `parse_brand_tokens` covering: empty yaml, missing yaml, multi-query yaml, paren with nested quotes, paren with multi-byte tokens like `サカナAI`.

## 2. `scripts/backfill_brand_keywords.py`

**New file, ~80 lines.** Mirrors the structure of `scripts/seed_list_handles_to_db.py` — argparse, idempotent INSERT OR IGNORE, hermetic tests via `--db` flag.

CLI:
```
python3 -m scripts.backfill_brand_keywords                # apply to data/x_monitoring.db
python3 -m scripts.backfill_brand_keywords --dry-run     # print what would be inserted
python3 -m scripts.backfill_brand_keywords --db path     # apply to a different DB
python3 -m scripts.backfill_brand_keywords --queries-dir path   # different yaml dir
```

Logic:
1. Load `config.yaml` via `load_config`.
2. Get `enabled_models` from the config.
3. Call `parse_brand_tokens(enabled_models, queries_dir)` to get `dict[brand, list[token]]`.
4. For each (brand, token) pair, INSERT OR IGNORE INTO `brand_keywords (brand_id, pattern, is_regex, added_at) VALUES (?, ?, 0, datetime('now'))`.
5. Print a per-brand report: tokens inserted vs skipped (already present).
6. Return rc=0 on success, rc=2 if any enabled brand has zero tokens parsed (operator-visible warning).

**Important:** This is a script, not a migration. Same rationale as `seed_list_handles_to_db.py`: the source is a yaml file (operator-curated, not deterministic), so re-running shouldn't be blocked by a migration ledger entry. The migration file in step 3 is the static fallback for hermetic apply paths; the script is the dynamic source.

## 3. Migration `034_backfill_brand_keywords_from_yaml.sql`

**Static SQL** that hard-codes the parsed tokens for the 12+ missing brands. Mirrors the migration 033 pattern: explicit INSERT OR IGNORE rows, one per (brand, token) pair.

Why both a migration AND a script:
- The migration is the "deterministic" apply path — useful for fresh DBs, CI seeding, and the migration ledger. It runs from `store.apply_migrations`.
- The script is the "dynamic" path — picks up new tokens as yaml files evolve, works against any DB (not just tracked migrations). Operators who add a new brand's yaml just rerun the script.

The migration content matches the script's output exactly at the time of writing. Future drift between yaml and the static migration is a known cost — the script is the source of truth going forward; the migration is a snapshot for hermeticity.

The static content for the 12+ missing brands (as of 2026-07-10):

```sql
-- nemo_megatron
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
  ('nemo_megatron', 'NeMo', 0, datetime('now')),
  ('nemo_megatron', 'Megatron', 0, datetime('now')),
  ('nemo_megatron', 'NVIDIA NeMo', 0, datetime('now')),
  ('nemo_megatron', 'Megatron-LM', 0, datetime('now'));

-- exaone
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
  ('exaone', 'EXAONE', 0, datetime('now')),
  ('exaone', 'LG AI', 0, datetime('now')),
  ('exaone', 'LG EXAONE', 0, datetime('now'));

-- sakana_ai
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
  ('sakana_ai', 'Sakana', 0, datetime('now')),
  ('sakana_ai', 'Sakana AI', 0, datetime('now')),
  ('sakana_ai', 'Sakana Labs', 0, datetime('now')),
  ('sakana_ai', 'サカナAI', 0, datetime('now'));

-- kuaishou
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
  ('kuaishou', 'KwaiYii', 0, datetime('now')),
  ('kuaishou', '快意', 0, datetime('now')),
  ('kuaishou', 'KwaiYii LLM', 0, datetime('now')),
  ('kuaishou', 'Kuaishou', 0, datetime('now'));

-- upstage
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
  ('upstage', 'Upstage', 0, datetime('now')),
  ('upstage', 'Solar', 0, datetime('now')),
  ('upstage', 'Solar Pro', 0, datetime('now')),
  ('upstage', 'Solar Mini', 0, datetime('now')),
  ('upstage', 'Solar Pro 3', 0, datetime('now')),
  ('upstage', 'Solar Pro 2', 0, datetime('now')),
  ('upstage', 'Solar Open', 0, datetime('now'));
-- (Plus the other 7+ missing brands as of 2026-07-10: doubao, ernie, hunyuan, mistral, sensechat, stepfun, yi)
-- (Will be expanded when the implementer enumerates the full list at execution time.)
```

The implementer must enumerate the full list of missing brands at execution time — `data/queries/<brand>.yaml` is the source.

## 4. Apply report

After running the script + migration, write `docs/notes/2026-07-10-backfill-brand-keywords-apply-report.md` with:
- Pre/post `brand_keywords` row count and per-brand coverage
- Rerun of `probe_filter_yield` at n=50 — new B3 kept count (target: >0; ideally matches the n_results since B3 query is well-formed and posts do contain brand tokens)
- Token count per brand, sanity check vs yaml Q2 paren-group size

# Tests (`tests/test_backfill_brand_keywords.py`)

**New file**, 5 tests. Mirror the structure of `test_seed_list_handles_to_db.py` (hermetic SQLite via Store).

| Test | Asserts |
|---|---|
| `test_backfill_inserts_q2_paren_tokens_for_each_enabled_brand` | Fresh DB with `enabled_models = ['nemo_megatron', 'exaone']`. Run script (no API). Assert `brand_keywords` has rows for both brands with the exact tokens parsed from their Q2 paren groups. |
| `test_backfill_is_idempotent` | Run twice. Second run inserts 0 rows, prints all skipped. Total row count unchanged. |
| `test_backfill_skips_brand_with_no_query_yaml` | `enabled_models = ['nonexistent_brand']`. Run script. Assert rc=2, warning printed, no rows inserted (but doesn't crash). |
| `test_backfill_existing_rows_are_preserved` | Pre-seed a custom row like `('nemo_megatron', 'CustomToken', 0, ...)`. Run backfill. Assert the custom row still present after. |
| `test_parse_brand_tokens_extracts_first_paren_group_only` | Test the extracted helper directly. yaml with Q1, Q2 (paren with multi-byte + quoted), Q3, Q5. Assert only Q2's tokens are returned, in order, no duplicates. |

# Verification

1. Run new test file: `cd x-monitoring && python3 -m pytest tests/test_backfill_brand_keywords.py -v` — all 5 tests pass.
2. Run existing query_plan tests to confirm the rename didn't break the call path: `python3 -m pytest tests/test_query_plan.py -v`.
3. Apply the script to live DB: `python3 -m scripts.backfill_brand_keywords`. Confirm rc=0 and report shows inserts.
4. Rerun probe: `python3 -m scripts.probe_filter_yield --max-results 50 --output /tmp/filter_yield_post_backfill.csv`. Compare B3 `kept` column against the pre-backfill baseline CSV (`docs/notes/probe_evidence/2026-07-09T093500Z-filter_yield_post_u3_apply.csv`). Target: B3 kept > 0.
5. Apply migration 034 to live DB: `python3 -m x_monitor.store --apply-migrations 034`. Confirm `SELECT MAX(version) FROM _migrations = 34`.

# Commit strategy

Two commits:

```
refactor(x-monitor): extract parse_brand_tokens from query_plan

Promotes _load_brand_tokens_per_model to a stable import surface
(parse_brand_tokens + _parse_first_paren_group helper). Same
behavior, used by both runtime call construction and the new
backfill script.

- x_monitor/query_plan.py: rename + extract _parse_first_paren_group.
- tests/test_query_plan.py: adjust import if needed; one new test
  for the paren-group parser covering edge cases.
```

```
feat(x-monitor): migration 034 + backfill script for brand_keywords

The probe's _kept_after_filter reads from brand_keywords in the
live DB. 12+ brands have zero entries there, which makes the probe
return 0 kept for B3 posts even when they clearly contain brand
tokens. This commit populates brand_keywords from data/queries/
<brand>.yaml Q2 paren groups — the operator-curated source of
truth — so the probe (and any production code that uses the same
index) gets full brand coverage.

- x_monitor/migrations/034_backfill_brand_keywords_from_yaml.sql:
  static INSERT OR IGNORE rows for the 12+ missing brands.
- scripts/backfill_brand_keywords.py: dynamic one-shot, reads
  yaml at apply time and inserts any brand/token pair not yet
  present. Idempotent.
- tests/test_backfill_brand_keywords.py: 5 hermetic tests.
- docs/notes/2026-07-10-backfill-brand-keywords-apply-report.md:
  apply report with pre/post counts and probe rerun.
```

# Out of scope (explicit)

- **Changing `attribute_to_brands`** in production code — this plan only populates the data; if the production code reads from a different source, that's a separate investigation.
- **Reverting the dryrun DB backup** — `data/x_monitoring.db.dryrun-mig033.*.db` (74M) stays gitignored.
- **The C2 spec triage** (probe shows 1/50) — partially addressed by this plan. As of 2026-07-10, ERNIE has 0 entries in `brand_keywords` (verified via `store.read_brand_keywords()`), so the probe's `_kept_after_filter` was silently dropping ERNIE mentions. This backfill will populate ERNIE's Q2 paren tokens (`ERNIE`, `文心一言`) into the table, which should improve the C2 probe's kept count. If after backfill C2 kept is still <5/50, then the AND-filter is independently too narrow (memory: `2026-07-09-c2-yield-probe-failure` triage tree) and needs its own follow-up.