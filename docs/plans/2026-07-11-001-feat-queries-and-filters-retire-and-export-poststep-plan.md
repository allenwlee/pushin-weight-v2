---
title: Retire per-brand yaml runtime + filters; unify calls; export post-step JSON - Plan
type: feat
date: 2026-07-11
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

## Goal Capsule

- **Objective**: Make every per-cycle TwitterAPI query conform to the same `<tokens> (<co_occurrence>) min_faves:N` shape; route all runtime reads through `brand_keywords` (DB) and `x_query_specs` (renamed from `call_c_specs` in `config.yaml`); retire the per-brand `data/queries/*.yaml` and the entire `data/filters/` directory; export `data/brand_keywords.json` + `data/x_query_specs.json` after any migration that touches the relevant tables.
- **Authority hierarchy**: this plan is the authority. If implementation conflicts arise, surface them — do not silently override.
- **Execution profile**: inline/subagent, four units, dependency-ordered (U1 → U2 → U3 → U4). Each unit is independently committable on the feature branch; U4's post-step must work end-to-end after U1-U3 reach a working state.
- **Stop conditions**: full unit verification (per-unit + per-repo) before declaring each unit done; the four-unit gate must clear before the branch is PR-ready.
- **Tail ownership**: `ce-work` owns the entire implementation tail. Goal-mode is unavailable in this harness.
- **Out-of-scope deferrals**: a fourth "categories" call (Call D — high-signal AI chatter with no brand mention) is intentionally tabbed to the next version per user direction.

## Product Contract

### Summary

The pipeline currently emits six different TwitterAPI call shapes (Call A list-based, three Call B token-OR-chains, two Call C co-occurrence specs, per-account `from:`/`to:` strings) sourced from `data/queries/<brand>.yaml` and `config.yaml → call_c_specs`, then runs a second post-fetch filter stage from `data/filters/<brand>.yaml`. After this plan: a single uniform spec schema feeds a single renderer, runtime reads `brand_keywords` (DB) and `x_query_specs` (config) only, every per-cycle TwitterAPI call conforms to `<tokens> (<co_occurrence>) min_faves:N`, post-fetch filters are gone, and a migration post-step exports PR-reviewable JSON of the current state.

### Problem Frame

Operators have signaled in the v1.7 conversation that the working product shape is narrow: list-based wide net (Call A) plus co-occurrence AND-filter for polysemous brands (Call C1/C2). This convergence is asserted from operator input, not yet measured — a future version should confirm it via per-call TwitterAPI credit consumption. The Q1-Q6 yaml framework, the per-brand account calls, and the post-fetch `data/filters/` stage predate that consensus and reflect an older signal taxonomy (release/question/criticism/reply/benchmark/praise) that the v1.7 redesign already retired from PlannedCall. Keeping those surfaces alive costs TwitterAPI credits (B1/B2/B3 + per-account fans in same cycle as Call A), creates two parallel configuration surfaces (`data/queries/` vs `config.yaml`) that the v1.7 hybrid-by-design contract explicitly flagged as drift-prone, and complicates PR review (yaml changes need a WatchPaths loop to land; config changes don't). Under the new shape, `brand_keywords` is already DB-canonical (per migration 004/017/029/034 and the 2026-07-10 backfill), the curated list already routes official-account signal through Call A, and the AND-filter already excludes the named hijack cases (F1 Kimi, Sesame Street ERNIE) — so retiring the redundant surfaces is cleanup work, not recall work.

### Requirements

#### Schema + config

- R1. `config.yaml` block `call_c_specs:` is renamed to `x_query_specs:` and the field carries Call A (list-based), Call C (co-occurrence), and any future call kinds — all rendered through one uniform shape.
- R2. Every spec in `x_query_specs` carries `brands: {brand_id: [tokens]}` plus optional `co_occurrence: [terms]` plus `min_faves: N` and a stable `call_id` label.
- R3. Call A is represented as a single spec whose `brands` map is empty and whose `co_occurrence` is empty (handled specially: renderer substitutes `(list:<x_monitor_list_id>) min_faves:1`).

#### Runtime pipeline

- R4. The per-cycle planner emits one TwitterAPI call per spec in `x_query_specs`, all with the same `<tokens> (<co_occurrence>) min_faves:N` rendering, regardless of call kind.
- R5. The pipeline does not read `data/queries/*.yaml` at runtime. Source-of-truth token data is `brand_keywords` (DB) plus `x_query_specs.brands` (config); both flow into renderer.
- R6. The pipeline does not read `data/filters/*.yaml` at runtime. The `filter_and_review` stage's relevance filter step is removed; only the legacy banned-token review-queue and low-engagement steps remain.
- R7. The `_build_brand_wide_query` and `parse_brand_tokens` helpers in `x_monitor/query_plan.py` are deleted (call B path retired).
- R8. The `load_filter`, `RelevanceConfig`, `_BRAND_FILTER_REQUIRED_FLAGS`, and per-cycle `filter_and_review` filter branch in `x_monitor/run.py` are removed.

#### Post-step export

- R9. `Store.apply_migrations` gains a post-step that, after any migration touching `brand_keywords` or `x_query_specs`-relevant tables, exports `data/brand_keywords.json` and `data/x_query_specs.json` to the project root for PR review.
- R10. The JSON files are deterministic (sorted keys, no whitespace bloat) so PR diffs are minimal.
- R11. A migration version that touched neither `brand_keywords` nor `brands_accounts` does NOT trigger the export — that keeps unrelated migrations from churning the JSON files.

#### Migration

- R12. Migration 035 creates an `_applied_config_snapshot` table (single-row, holds last-exported-content-hash for each JSON file) so the post-step can skip the write when nothing changed.
- R13. Migration 035 also performs a one-time `INSERT OR IGNORE INTO brand_keywords` for any token that lives in `data/queries/*.yaml` Q2 paren groups but is missing from the current `brand_keywords` table — this is the consolidation read of the per-brand yamls. The output of this read is captured into `_applied_config_snapshot.checksum_seed_yaml` so reviewers see the consolidation in the same PR.

#### Smoketest

- R14. The smoketest drops `--query-from-yaml` and the `_resolve_query_from_yaml` helper. `--source=api-query` still works against live TwitterAPI but the operator passes query strings inline or via `x_query_specs[].rendered`.
- R15. The smoketest's `--source=latest-cycle` and `--source=latest-n` modes keep working — they do not depend on yaml or filters.

#### Documentation + operational

- R16. The `x-monitor` LaunchAgent `WatchPaths` plist retargets from `data/queries/` to the project root (or its `config.yaml`-bearing directory), since `config.yaml` is now the operator-editable surface.
- R17. `docs/reference/` entries that mention yaml Q1-Q6 syntax (`lookup-tables.md`, `twitterapi-live-queries-by-model.md`) are updated to point at `x_query_specs` and the uniform renderer.

### Scope Boundaries

- **In scope**: yaml runtime reads (off), filters runtime reads (off), config field rename, uniform renderer schema, post-step JSON export, smoketest --query-from-yaml removal, migration 035, plist retarget, reference doc updates.
- **Deferred for later (next version)**:
  - A fourth "categories" call (Call D) for high-signal AI chatter that does not mention any brand — operator decision from the scoping conversation. Tracked in operator memory for v(n+1) planning.
  - Reconciliation of `data/accounts/*.yaml` against `brands_accounts.role='official'` plus a drift-detection step (the source-vs-DB mismatch risk this plan surfaces in A1). Currently parked; needs its own plan.
  - "Operator converged" premise — future version should measure per-call credit consumption under the post-consolidation shape to validate the recall argument. Currently unmeasured.
- **Outside this plan's identity**: dashboard grid changes, TwitterAPI client rate-limit tuning, locale translation of brand tokens (already handled by `cmd_translate_registry`), the pre-existing test failures in `test_brand_search_terms_populate.py` and `test_probe_filter_yield.py` (unrelated surfaces), migration 030's legacy `xiaomi_mimo` rename (already in DB), the `data/accounts/*.yaml` file itself (kept; its migration-to-DB path is deferred — see above).
- **NOT retired by this plan (explicit non-action)**: `data/accounts/*.yaml` stays as operator-edit surface for per-brand official handles. KTD2 makes explicit that this file is NOT in this plan's cut; the follow-up reconciler is in `Deferred for later`.

## Planning Contract

### High-Level Technical Design

A single renderer unifies every call kind. The planner iterates `x_query_specs`; `_build_query` dispatches on the spec shape — empty `brands` is Call A, non-empty is the prior Call C body — and writes one `PlannedCall` per spec. Call A's `brands` map can carry a `__list_handles__` virtual brand whose tokens are the official-account handles joined by OR, so the renderer stays pure-string-input.

```mermaid
flowchart LR
  Config[x_query_specs<br/>in config.yaml] --> Planner[plan_calls]
  Accounts[brands_accounts<br/>role=official, DB] --> Planner
  Planner -->|for each spec| BuildQ[_build_query<br/>single renderer]
  BuildQ -->|spec.brands={}| ListCall[(list:<id>)<br/>min_faves:1]
  BuildQ -->|spec.brands={b:toks}| TokenCall[(<toks>) (<cooc>)<br/>min_faves:N]
  BuildQ --> PlanCalls[PlannedCall list]
  PlanCalls --> Twitter[TwitterAPI]
  Migration[Migration 035+] --> StoreMig[Store.apply_migrations]
  StoreMig --> PostStep[_post_migration_step]
  PostStep --> HashCheck{content hash<br/>changed?}
  HashCheck -->|yes| WriteJSON[write data/brand_keywords.json<br/>+ data/x_query_specs.json]
  HashCheck -->|no| Skip[no write]
```

### Key Technical Decisions

- **KTD1 — Render path is one function.** All specs (`x_query_specs` entries, including Call A) render through `_build_query(spec) -> str`. The function has exactly one intentional branch: when `not spec.brands`, render `(list:<x_monitor_list_id>) min_faves:1` (Call A degenerate); otherwise render `(tokens) (co_occurrence) min_faves:N` (Call C body). No other call kinds get a separate renderer; if a future Call D is added, its shape must conform to the same `brands + co_occurrence + min_faves` field set or this KTD is revised. Rationale: the unification was the explicit goal of this work; introducing additional renderers per call kind defeats it. The branch is documented polymorphism — not a dispatch on type — and is the only allowed special case.
- **KTD2 — Call A's wide net is the curated X-list, not `brands_accounts.role='official'`.** `_build_query` for Call A renders `(list:<x_monitor_list_id>) min_faves:1`; the list ID comes from `config.yaml → x_monitor_list_id`, which is the operator-curated list on the X/Twitter side. `brands_accounts.role='official'` is the post-fetch `attribute_to_brands` source for joining each result post back to a brand, NOT the Call A query-construction source. The two surfaces are deliberately separate because the X-list membership is curated externally (operators update it on twitter.com); reading it from `brands_accounts` would re-introduce drift between the list and DB. `data/accounts/*.yaml` stays alive for now — the migration-035 to `brands_accounts` reconciliation is a deferred follow-up (see Scope Boundaries), not part of this plan.
- **KTD3 — Post-step lives inside `Store.apply_migrations`, not as a separate script.** The migration runner is the single chokepoint that fires on PR merge; tying the export to it keeps the JSON artifacts in lockstep with DB state. A standalone script would require operators to remember to invoke it. Rationale: same drift problem as KTD1 — fewer moving parts means fewer ways for the artifact to go stale.
- **KTD4 — Export gate by content hash, with mandatory `ORDER BY` for determinism.** `_applied_config_snapshot` holds `(artifact_name, content_hash)`. Both `export_brand_keywords_json` and `export_query_specs_json` SELECT with explicit `ORDER BY` columns (`brand_id, pattern` for `brand_keywords`; configurable for `x_query_specs`) so SHA256 hashes are stable across VACUUM, REINDEX, and SQLite engine upgrades. First-run behavior: when the snapshot row does not exist, the export is treated as content-changed and the file is written. Crash-recovery behavior: if a migration fails mid-apply, `_migrations` does not record the version, so the post-step never fires for that version on retry. Rationale: hash-only gating without `ORDER BY` would generate false-positive rewrites on row-order drift.
- **KTD5 — `x_query_specs` schema is the existing `CallCBrandSpec` schema, with the field name flipped.** No new dataclass. The renamed config field loads the same shape via `Config.x_query_specs: list[XQuerySpec]` where `XQuerySpec` is the type-renamed dataclass (`call_id` defaulted; `min_faves=0`; `co_occurrence` empty for Call A). For Call A the `co_occurrence` and `min_faves` fields are semantically inert — they exist for uniformity but the renderer substitutes the list-based form. Rationale: the schema was already uniform for Call C, and Call A's degenerate-empty-brands case fits the same shape.
- **KTD6 — Filters retire hard, not archive-but-ignore.** `data/filters/*.yaml` and `x_monitor.filters.load_filter` are deleted; `_BRAND_FILTER_REQUIRED_FLAGS` is removed; the **relevance-filter step** inside `filter_and_review` is removed. The `filter_and_review` function itself stays — its banned-token review-queue and low-engagement-filter steps are independent of `data/filters/*.yaml` and live in-code (via `review_queue_path`); they must not be removed. Operators who want per-brand hijack exclusions add terms to the relevant spec's `co_occurrence` list (which is config-side and PR-reviewable) instead. Rationale: the user's "for ever" direction; an archive directory would re-introduce drift risk on the same surface.
- **KTD7 — Post-step is gated by an explicit migration-level header convention, not a substring scan.** Migration SQL files declare which post-step artifacts they touch via a header comment: `-- post_step_touches: brand_keywords,brands_accounts` (or `x_query_specs`). The runner reads that line; if absent, the post-step fires nothing. Rationale: substring scanning for `brand_keywords` produces false positives (e.g., migration 030 mentions the table in a rename statement, migration 029's regex patterns), and explicit declarations are reviewable in PR.

### Assumptions

- **A1.** The curated X-list is operator-managed on the X/Twitter side, and `config.yaml → x_monitor_list_id` is the canonical handle to it. This plan does not touch `data/accounts/*.yaml` and does not require that file's contents to match `brands_accounts.role='official'`. The follow-up to migrate `data/accounts/*.yaml` into `brands_accounts` and detect drift is deferred to a separate plan (parked in operator memory).
- **A2.** The 23-or-21-term `co_occurrence` lists for C1/C2 cover the named hijack cases (F1 driver Kimi, Sesame Street ERNIE, etc.). Operator confirmed in the scoping conversation that AND-filter coverage is sufficient.
- **A3.** `brand_keywords` already covers the 20 production `enabled_models` brands (207 rows; the 21st brand `xiaomi_mimo` is the post-migration-030 legacy name retained alongside `mimo`, and is already covered). Migration 035's residual-seed step is a static SQL file at authoring time; its INSERT rows are no-ops on the live DB (because every `enabled_models` brand is already represented), but the file is included so reviewers see the consolidation explicitly in the same PR.
- **A4.** No operator currently uses `--query-from-yaml` as part of a daily workflow beyond ad-hoc smoketest eyeball checks. The flag is dropped without a deprecation cycle; if A4 turns out to be wrong, the operator-visible impact is "live smoketest queries now require explicit `--query <string>`".

### Implementation Units

#### U1. Migration 035 — schema cleanup, config block rename, residual seed

- **Goal**: Lay the database + config surface that the rest of the plan builds on. Create `_applied_config_snapshot` table, perform the residual seed of `brand_keywords` from pre-computed rows (i.e., this is a static SQL file at authoring time — no Python hook in the runner), rename `data/queries/*` Q2-token derivation in one commit, and update `config.yaml` to use `x_query_specs:` (renamed from `call_c_specs:`).
- **Requirements**: R1, R2, R12, R13.
- **Dependencies**: none.
- **Files**:
  - `x-monitoring/x_monitor/migrations/035_rename_call_c_specs_and_residual_seed.sql` (NEW — pure SQL, header `-- post_step_touches: brand_keywords,x_query_specs` per KTD7)
  - `x-monitoring/x_monitor/migrations/_authoring/seed_residual_keywords.py` (NEW — one-shot CLI used at authoring time, not at apply time. Reads `data/queries/*.yaml`, emits INSERT OR IGNORE lines. Lives outside `migrations/` so it is not picked up by `apply_migrations()`.)
  - `x-monitoring/config.yaml` (MODIFY — rename `call_c_specs:` block to `x_query_specs:`)
  - `x-monitoring/tests/test_migration_035.py` (NEW)
  - `x-monitoring/tests/golden/query_plan_v17_strings.txt` (NEW — golden output snapshot from pre-rename `_build_call_c_query` for U2's byte-equality test; collected in this unit before U2's rename lands)
- **Approach**: The migration is pure SQL, three sections: (1) `CREATE TABLE IF NOT EXISTS _applied_config_snapshot (artifact TEXT PRIMARY KEY, content_hash TEXT NOT NULL, written_at TEXT NOT NULL)`, (2) a flat block of pre-computed `INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES (?, ?, ?, ?)` rows derived from `data/queries/*.yaml` Q2 paren groups via the authoring-time `seed_residual_keywords.py` script (run once during U1's authoring; the rows become the static content of the SQL file), (3) leaves `brand_keywords` rows untouched when already present (INSERT OR IGNORE behavior). The migration runner records version 035 in `_migrations` after success; no Python hook in the runner. `config.yaml` block rename happens in a separate commit so reviewers can see the field rename independently of the schema work. Before U2 lands, U1's commit also snapshots golden query-plan output strings to `tests/golden/query_plan_v17_strings.txt` (one entry per `x_query_specs` spec, byte-equal to the live planner's output). U2's rename test reads the golden file rather than calling the deleted function.
- **Test scenarios**:
  - Happy path: fresh DB migrates to v35 without errors; `_applied_config_snapshot` exists empty (no rows until first post-step fire); `brand_keywords` row count is exactly equal to the pre-migration count (no duplicate rows, INSERT OR IGNORE no-ops on existing tokens); the static INSERT block survives idempotency.
  - Edge case: replay-safe — running the migration twice on the same DB leaves row counts unchanged (INSERT OR IGNORE + CREATE TABLE IF NOT EXISTS).
  - Edge case: a `data/queries/` directory absent leaves the residual-seed block as no-op rows (since the authoring script was run before the directory was deleted in U3); migration completes with zero rows inserted.
  - Integration: `x_monitor.config.load_config(Path("config.yaml"))` parses `x_query_specs:` successfully and reports exactly 3 specs (C1 + C2 + the new Call A spec) per the KTD2 retarget — verified against the live config snapshot pre-rename (which had 2 specs: C1 + C2).
  - Edge case: an explicit `git grep -rn "call_c_specs" --exclude-dir=.git` returns no hits in source/docs/scripts (operator-facing rename is complete).
  - Edge case: the new migration file's first non-comment line is `-- post_step_touches: brand_keywords,x_query_specs` (KTD7), and `Store.apply_migrations()` reads that line on apply.
- **Verification**: `cd x-monitoring && python3 -m pytest tests/test_migration_035.py -v` exits 0. Live DB at v35 with `brand_keywords` row count unchanged (no rows lost, no rows added if migration 034 was already applied). `config.yaml → x_query_specs:` parses through `load_config` without error and equals the prior `call_c_specs:` set. Golden file `tests/golden/query_plan_v17_strings.txt` matches `scripts/probe_filter_yield.py` output for the live planner.

#### U2. `query_plan.py` — uniform renderer + planner

- **Goal**: Replace the three-renderer layout (`_build_brand_wide_query` for Call B, `_build_call_c_query` for Call C, hardcoded `(list:<id>)` for Call A) with one `_build_query(spec)` that handles every spec kind, including Call A's degenerate-empty-brands case. Delete `parse_brand_tokens` and `_parse_first_paren_group` (no longer needed — runtime no longer reads yaml; tokens come from spec or DB).
- **Requirements**: R3, R4, R7.
- **Dependencies**: U1.
- **Files**:
  - `x-monitoring/x_monitor/query_plan.py` (MODIFY — delete `_build_brand_wide_query`, `parse_brand_tokens`, `_parse_first_paren_group`; rename `_build_call_c_query` → `_build_query`; generalize dataclass `CallCBrandSpec` → `XQuerySpec` with no schema break)
  - `x-monitoring/x_monitor/config.py` (MODIFY — rename `call_c_specs` → `x_query_specs` field)
  - `x-monitoring/x_monitor/run.py` (MODIFY — update import sites)
  - `x-monitoring/tests/test_query_plan_uniform.py` (NEW — replaces the Call-B-specific tests in `test_query_plan_v17.py`)
- **Approach**: Step (1) rename the dataclass `CallCBrandSpec` → `XQuerySpec` and the field `call_c_specs` → `x_query_specs` everywhere; the schema is identical. Step (2) `_build_query` is the existing `_build_call_c_query` with one extra branch at the top — when `not spec.brands`, render `(list:<x_monitor_list_id>) min_faves:1` using a class-level helper (or an injected `x_monitor_list_id` argument). Step (3) `plan_calls` shrinks to a single loop: for each spec in `x_query_specs`, build a `PlannedCall` via `_build_query(spec)`; never read yaml; never call `parse_brand_tokens`. Step (4) delete `parse_brand_tokens`, `_parse_first_paren_group`, `_build_brand_wide_query`. Length-cap assertion (`assert_under_length_cap`) remains the caller's responsibility in the planner, unchanged.
- **Test scenarios**:
  - Happy path: `_build_query(spec)` with the live C1 spec reads its expected query string from `tests/golden/query_plan_v17_strings.txt` (captured in U1) and returns byte-equal output. This decouples U2's rename from `_build_call_c_query`'s deletion.
  - Happy path: `_build_query` with `spec.brands={}` and injected `x_monitor_list_id=2067062923525275922` renders `(list:2067062923525275922) min_faves:1`.
  - Edge case: `_build_query` with `spec.brands={'minimax': []}` (empty token list for a brand) renders the empty brand as a no-op — the resulting query string omits that brand's contribution but remains syntactically valid (no double-parens).
  - Edge case: `_build_query` with `spec.min_faves=0` and no `co_occurrence` emits the standard `(tokens) (co_occurrence) min_faves:N` form (the trailing `min_faves:0` is still present per KTD1's documented form).
  - Integration: `plan_calls` with `[Call_A_spec, C1_spec, C2_spec]` from `x_query_specs` emits exactly 3 `PlannedCall` rows of kind `brand_wide` (or `account` for Call A specifically, preserved from the v1.7 contract).
  - Error path: `plan_calls` with empty `x_query_specs` emits an empty list (not a `(empty)` literal); matches v1.7 behavior.
- **Verification**: `cd x-monitoring && python3 -m pytest tests/test_query_plan_uniform.py tests/test_query_plan_v17.py -v` exits 0. `plan_calls` round-trip on the live `x_query_specs` config emits the same per-call query strings the prior `_build_call_c_query` produced (golden-file check from U1).

#### U3. `RunPipeline` — drop yaml + filters runtime reads

- **Goal**: Remove all runtime reads of `data/queries/*.yaml` and `data/filters/*.yaml`. Drop the `_brand_tokens_map`, `_log_brand_search_terms_drift`, `load_filter`, `RelevanceConfig`, and `filter_and_review` filter branch. Retarget the LaunchAgent WatchPaths plist.
- **Requirements**: R5, R6, R8, R16.
- **Dependencies**: U1 (config rename), U2 (planner no longer needs `parse_brand_tokens`).
- **Files**:
  - `x-monitoring/x_monitor/run.py` (MODIFY — delete `_brand_tokens_map`, `_log_brand_search_terms_drift`, `load_filter`, `_BRAND_FILTER_REQUIRED_FLAGS`, the relevance-filter step in `filter_and_review`)
  - `x-monitoring/x_monitor/filters.py` (DELETE — entire file consumed by `RunPipeline`)
  - `x-monitoring/data/queries/` (DELETE — directory + 23 yaml files)
  - `x-monitoring/data/filters/` (DELETE — directory + ~7 yaml files)
  - `x-monitoring/deploy/com.fuchitalee.x-monitor.plist` (MODIFY — retarget WatchPaths)
  - `x-monitoring/deploy/run-pipeline-watchpaths.sh` (MODIFY — update comment block)
  - `x-monitoring/tests/test_run_pipeline_yaml_free.py` (NEW — confirms `RunPipeline.__init__` doesn't accept a `data/queries/` reference; `query_plan.plan_calls` is invoked without `data_dir/"queries"` reads)
- **Approach**: Step (1) in `RunPipeline.__init__`, remove the `self.queries_dir` attribute assignment (`x_monitor/run.py:811`). Step (2) in `RunPipeline.execute`, remove the `load_filter(m, self.data_dir)` line and the surrounding dict comprehension (`x_monitor/run.py:948-950`); remove all `_brand_tokens_map` call sites (currently `x_monitor/run.py:991` and `x_monitor/run.py:1329` — both must be removed); remove the `_log_brand_search_terms_drift` call (`x_monitor/run.py:1000-1002`). Step (3) update `filter_and_review` to remove only the relevance-filter step; the banned-token review-queue and low-engagement-filter steps stay (they are in-code, not yaml-driven — see KTD6). Step (4) `data/queries/` and `data/filters/` are deleted in a single `git rm -r` commit so they appear in the diff as a clean removal. Step (5) WatchPaths plist retarget: the plist's `WatchPaths` array changes from its current state (currently `[data/queries]` with an absolute path) to `[config.yaml]` with the absolute path the launchd convention requires (the operator resolves the project's actual launchd `WorkingDirectory` when applying the edit, since that exact path is environment-specific). Only config needs the rerun trigger; the DB is canonical, so DB-touching migrations don't need WatchPaths. Step (6) runtime reads from `cwd` resolve relative to the launchd `WorkingDirectory`, which is the project root `x-monitoring/`; the verification commands in this unit's `Verification` row run from that directory explicitly using `cd x-monitoring`.
- **Test scenarios**:
  - Happy path: `RunPipeline(config, data_dir, db_path)` constructs without raising when `data/queries/` does not exist; the constructor does not reference `data/"queries"` anywhere.
  - Happy path: `RunPipeline.execute(...)` does not call `_brand_tokens_map`, `_log_brand_search_terms_drift`, or `load_filter` — confirmed via a `monkeypatch` test that asserts the symbol is never imported (or was removed). The test covers both call sites of `_brand_tokens_map` (was just one reference in U3 approach but revised to two).
  - Integration: end-to-end cycle on a DB seeded only from `brand_keywords` + `brand_search_terms` + `x_monitor_list_id` produces query strings identical to the prior v1.7 cycle for Call A and the two Call C specs.
  - Edge case: `_log_brand_search_terms_drift` is gone, so any test asserting a "drift detected" log line for the old yaml-vs-DB mismatch fails to set up; the test file is rewritten to assert the drift logger is absent.
  - Operational: `cat deploy/com.fuchitalee.x-monitor.plist | grep WatchPaths` returns only the `config.yaml` absolute path and not `data/queries`. `git ls-files data/queries data/filters` returns empty (confirms the deletion actually shipped in this branch, not just locally).
- **Verification**: `cd x-monitoring && python3 -m pytest tests/test_run_pipeline_yaml_free.py tests/test_run_pipeline_*.py tests/test_run_pipeline_integration.py -v` exits 0. The 23 `data/queries/*.yaml` files and the `data/filters/` directory are deleted in the commit; `git ls-files data/queries data/filters` returns empty.

#### U4. Smoketest cleanup + migration post-step JSON export

- **Goal**: Drop the smoketest's `--query-from-yaml` path. Build `Store.export_query_specs_json(target_path)` and `Store.export_brand_keywords_json(target_path)` helpers; wire them into `Store.apply_migrations`'s post-step so any migration touching `brand_keywords` or `brands_accounts` triggers JSON export with content-hash gating.
- **Requirements**: R9, R10, R11, R14, R15, R17.
- **Dependencies**: U1, U2, U3.
- **Files**:
  - `x-monitoring/x_monitor/store.py` (MODIFY — add `export_query_specs_json`, `export_brand_keywords_json`, `_post_migration_step` invocation in `apply_migrations`)
  - `x-monitoring/scripts/post_fetch_smoketest.py` (MODIFY — delete `_resolve_query_from_yaml`, `--query-from-yaml` flag, helper imports)
  - `x-monitoring/x_monitor/__main__.py` (MODIFY — delete `--query-from-yaml` flag, forwarder in `cmd_smoketest`)
  - `x-monitoring/tests/test_store_export.py` (NEW)
  - `x-monitoring/tests/test_post_fetch_smoketest_no_yaml.py` (NEW — replaces `test_post_fetch_smoketest_api_source.py` for the deleted path)
  - `x-monitoring/docs/reference/lookup-tables.md` (MODIFY — point at `x_query_specs`)
  - `x-monitoring/docs/reference/twitterapi-live-queries-by-model.md` (MODIFY — same)
- **Approach**: Step (1) `Store.export_brand_keywords_json(target)` SELECTs `brand_id, pattern, is_regex` from `brand_keywords ORDER BY brand_id, pattern`, computes a SHA256 over the canonical-JSON form (sorted keys, no whitespace, UTF-8), compares to `_applied_config_snapshot.content_hash` for that artifact, writes the JSON only on difference. Step (2) `export_query_specs_json(target)` SELECTs from a new `x_query_specs` table (populated from `config.yaml` at startup via a small helper script run once on migration 035 apply) with explicit `ORDER BY`, applies the same hash gate. (NB: this means `x_query_specs` becomes DB-canonical at runtime even though its authoring source is `config.yaml`; the config file is the operator-edit surface, and the DB row is the runtime read. This resolves KTD4/E concerns about coupling the migration runner to filesystem mtime watching.) Step (3) `_post_migration_step(applied_version)` is invoked from `Store.apply_migrations` immediately after the migration's INSERT into `_migrations`. It reads the migration file's first comment line `-- post_step_touches: <artifacts>` (per KTD7); absent or empty = skip. Step (4) smoketest deletes the yaml-dependent flag and helper; tests asserting `--query-from-yaml` are deleted; the `test_post_fetch_smoketest_api_source.py` test that synthesizes a yaml under tmp_path is rewritten to use `--query <inline string>`.
- **Test scenarios**:
  - Happy path: `Store.export_brand_keywords_json(Path("/tmp/brand_keywords.json"))` on a DB writes a JSON; round-trip parse matches the SELECT result.
  - Happy path: re-invoking the same export on an unchanged DB does NOT rewrite the JSON file (mtime unchanged); the snapshot row holds the same hash.
  - Edge case: applying migration 035 (which has `-- post_step_touches: brand_keywords,x_query_specs`) changes the JSON; the second apply with no DB change does not.
  - Edge case: applying a migration without the post-step header does NOT trigger the export (no regex hit, no substring fallback).
  - Edge case: applying a migration whose header lists a wrong artifact (e.g., `brands_accounts`) does NOT trigger the `brand_keywords` export.
  - Determinism: reordering rows via `REINDEX` does not change the SHA256 hash (because of explicit `ORDER BY`).
  - Integration: `Store.apply_migrations()` on a fresh DB running migrations 001-035 writes `data/brand_keywords.json` and `data/x_query_specs.json` to disk; both files exist and parse.
  - Smoketest: `sm.main(["--source", "latest-cycle"])` runs without error; `sm.main(["--query-from-yaml", "minimax"])` raises an argparse error (flag removed).
  - Operational: a git status check after a no-op migration shows `data/brand_keywords.json` and `data/x_query_specs.json` as unmodified.
- **Verification**: `cd x-monitoring && python3 -m pytest tests/test_store_export.py tests/test_post_fetch_smoketest_no_yaml.py -v` exits 0. After `Store.apply_migrations()` runs end-to-end, `data/brand_keywords.json` and `data/x_query_specs.json` exist on disk and round-trip-parse. `data/queries/` and `data/filters/` do not exist. `--query-from-yaml` raises `argparse: unrecognized arguments`.

## Verification Contract

| Unit | Repo command | Pass criterion |
|---|---|---|
| U1 | `cd x-monitoring && python3 -m pytest tests/test_migration_035.py -v` | All tests pass; live DB at v35 with `brand_keywords` row count unchanged from pre-U1 (no rows lost, residual seed is no-op on a DB where migration 034 already applied) |
| U1 | `cd x-monitoring && python3 -c "from x_monitor.config import load_config; c=load_config(Path('config.yaml')); print(len(c.x_query_specs))"` | Prints 3 (C1 + C2 + new Call A spec); the prior `call_c_specs` count was 2 |
| U2 | `cd x-monitoring && python3 -m pytest tests/test_query_plan_uniform.py tests/test_query_plan_v17.py -v` | All tests pass |
| U3 | `cd x-monitoring && python3 -m pytest tests/test_run_pipeline_yaml_free.py tests/test_run_pipeline_*.py tests/test_run_pipeline_integration.py -v` | All tests pass |
| U3 | `cd x-monitoring && grep -rn "load_filter\|RelevanceConfig\|_brand_tokens_map\|parse_brand_tokens" x_monitor/ scripts/` | Returns no runtime hits |
| U3 | `cd x-monitoring && ls data/queries data/filters` | Both `ls` errors with "No such file or directory" |
| U4 | `cd x-monitoring && python3 -m pytest tests/test_store_export.py tests/test_post_fetch_smoketest_no_yaml.py -v` | All tests pass |
| U4 | `cd x-monitoring && python3 -c "from x_monitor.store import Store; s=Store(); s.apply_migrations(); s.close(); import json; print(len(json.load(open('data/brand_keywords.json'))))"` | Prints the row count |
| All | `cd x-monitoring && python3 -m pytest tests/ -v -x` | Full suite exits 0, excluding the pre-existing failures (2 in `test_brand_search_terms_populate.py`, 2 in `test_probe_filter_yield.py`) which are unrelated to this plan and explicitly scoped out |
| All | `git status` in `docs/reference/` | No uncommitted changes to `lookup-tables.md` or `twitterapi-live-queries-by-model.md` other than the U4 modifications |

## Definition of Done

- **Global**: `x_query_specs:` is the only operator-facing config surface for query construction; `brand_keywords` is the only runtime source for per-brand tokens; `data/queries/` and `data/filters/` directories are deleted; the migration post-step exports both JSON files deterministically (hash stable across VACUUM/REINDEX via explicit `ORDER BY`); the smoketest does not expose yaml-query flags; `git log --oneline` on the feature branch shows four logical commits (one per unit) with no scope creep across them.
- **Per unit**: each unit's Verification Contract row exits 0.
- **Cleanup**: no abandoned-attempt code or dead imports in the diff; no commented-out yaml-loading helpers left behind for "just in case"; no `git grep` hits for `call_c_specs` (string rename is complete).
- **Re-baseline**: the per-cycle fan-out on a production-shaped `x_query_specs` is exactly `len(x_query_specs)` TwitterAPI calls (currently 3: Call A + C1 + C2; parameterized so a future Call D doesn't require redefining DoD). Confirmed by a one-shot `scripts/probe_filter_yield.py` style dry-run that prints the planned calls without hitting the API.
