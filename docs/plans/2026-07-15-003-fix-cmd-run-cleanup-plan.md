---
title: cmd_run Cleanup - DB-Keyword Load, Q-String Emission, Counter Fix - Plan
type: fix
date: 2026-07-15
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

## Goal Capsule

- **Objective:** Make the `x_monitor run` JSON output trustworthy end-to-end: stop emitting `missing_queries:*` for retired `data/queries/*.yaml` files, stop emitting `Q1`/`Q5` strings in `query_id` rows, and stop reporting `n_classifications_written=0` when classifications actually land.
- **Authority:** User-confirmed scope from prior turn — three named fixes plus a re-run to confirm.
- **Execution profile:** Inline subagents (3 small units, single component, no parallel-isolation benefit).
- **Stop conditions:** All three fixes shipped to main; a live re-run on DS V4 produces a JSON with zero `missing_queries` entries, zero `query_id` values matching `Q[1-6]`, and `n_classifications_written` equal to the `posts_brands_signals` row count for the run.
- **Tail ownership:** Implementation + commit + push + re-run + verify (LFG-style end-to-end).

## Product Contract

### Summary

Three latent bugs in `cmd_run` make the live run summary misleading even though the pipeline itself works. Fix each in-place so the JSON reflects reality, then re-run the pipeline on DS V4 to confirm.

### Problem Frame

The 2026-07-15T082550 live DS V4 run (8 posts inserted, 15 classifications written to `posts_brands_signals`) reported in its summary JSON:

- 20 entries under `degraded.missing_queries:*` — one per brand — even though the run executed normally
- 4 rows with `query_id: "Q1"` or `"Q5"` even though `posts.call_id` writes A/B/C strings
- `n_classifications_written: 0` even though 15 classifications actually landed

Operators reading the JSON cannot distinguish "real failure" from "cosmetic noise," which defeats the purpose of the summary.

### Requirements

#### Bug 1: Missing-queries noise

- R1. `cmd_run` reads brand tokens from the DB (via `Store.read_brand_keywords(brand_id)`) instead of from `data/queries/<brand>.yaml`.
- R2. When the DB-keyword read succeeds, the run JSON `degraded.missing_queries:*` block is empty.
- R3. When the DB-keyword read fails for a brand, the failure surfaces as a per-brand `degraded.missing_brand_keywords:<brand>` entry (renamed for clarity), not as `missing_queries:*`.

#### Bug 2: Q-string emission

- R4. The `query_id` field in every per-query row of the run JSON matches the A/B/C call_id emitted by the planner (A for account, B1/B2/B3 for wide-net groups, C1/C2 for co-occurrence specs).
- R5. The `--queries` CLI flag help text reads `comma-separated query_id filter (A, B1, B2, B3, C1, C2)` instead of `Q1..Q6`.

#### Bug 3: Classification counter

- R6. The `n_classifications_written` counter on the run summary equals the number of rows inserted into `posts_brands_signals` during the run, capturing both the inline `insert_posts` path and the `_run_post_fetch` path.
- R7. The counter is read once after `_run_post_fetch` completes (not incrementally after `insert_posts`), so post-fetch writes count.

### Scope Boundaries

- **In scope:** the three named fixes + the live re-run verification.
- **Out of scope (deferred):**
  - Per-post retry `classify_post` thinking-default threading (deferred — the user explicitly retracted this from scope)
  - The `_max_tokens_for_batch` import wiring and any other `AnthropicClaudeClient()` construction sites — opportunistic grep audit only, not a refactor
  - `--queries` runtime behavior — only the help-text fix, no semantic change
  - General run-summary schema cleanup beyond the three named counters

## Planning Contract

### Key Technical Decisions

- KTD1. Read tokens from `Store.read_brand_keywords` (already exists per migration 030) rather than from a new method. Keeps the surface small and reuses the existing `brand_keywords` table that the q-retirement work populated.
- KTD2. Replace the literal `"Q1" if call.call_kind == "account" else "QX"` with `call.call_id` directly. `PlannedCall.call_id` is already populated by `query_plan.plan_calls` with the A/B/C strings, so no per-call conditional is needed.
- KTD3. Move the `n_classifications_written` read to after `_run_post_fetch` completes (after the post-fetch loop block in `cmd_run`), reading `store._classifications_written` once instead of incrementally. The inline `insert_posts` writer at `store.py:780` already bumps the counter — only the `insert_posts_brands_signals` writer needs to start bumping it too.

### Approach

Single file (`x_monitor/run.py`) holds all three fix sites. `_run_post_fetch` is unchanged in shape; only its caller's post-condition (where `n_classifications_written` is read back) moves. Tests for each fix live in `x-monitoring/tests/test_run.py` (existing file) or new `tests/test_cmd_run_summary.py` if existing test structure doesn't fit.

### Sequencing

U1 → U2 → U3 → U4. Each unit is independently committable but the live re-run in U4 needs U1-U3 done to validate against.

## Implementation Units

### U1. Load brand tokens from DB in cmd_run

- **Goal:** Replace `load_queries(m, self.data_dir)` with a DB-backed read so the run no longer dead-ends on the retired `data/queries/*.yaml` files.
- **Requirements:** R1, R2, R3
- **Files:**
  - `x-monitoring/x_monitor/run.py` (modify `cmd_run` query-loading loop)
  - `x-monitoring/x_monitor/store.py` (add `read_brand_keywords_for_models` if missing — confirm first)
  - `x-monitoring/tests/test_cmd_run_keywords.py` (new — pin the DB-keyword load path)
- **Approach:**
  - Confirm `Store.read_brand_keywords(brand_id) -> list[str]` exists; if not, add it (read from the `brand_keywords` table that migration 030 introduced).
  - In `cmd_run`, build a `{brand_id: list[str]}` map by iterating `self.config.enabled_models` and calling the DB method. Replace the `queries_per_model` map with the DB-fed map.
  - Change the `missing_queries:<m>` exception handler key to `missing_brand_keywords:<m>` and update the message accordingly.
- **Test scenarios:**
  - Happy: `cmd_run` with a config whose enabled brands all have rows in `brand_keywords` — `degraded.missing_brand_keywords` is empty, every brand has tokens loaded.
  - Edge: a brand present in `enabled_models` but missing from `brand_keywords` — surfaces as `missing_brand_keywords:<brand>` with a clear message.
  - Integration: a live run end-to-end writes zero `missing_*` entries.
- **Verification:** `python3 -m pytest tests/test_cmd_run_keywords.py` passes; `x_monitor.run` with the current DB and config produces an empty `missing_*` block.

### U2. Replace Q-string query_id emission in run JSON

- **Goal:** Run JSON `query_id` field uses the planner's A/B/C strings.
- **Requirements:** R4, R5
- **Files:**
  - `x-monitoring/x_monitor/run.py` (modify `cmd_run` per-query row construction at the two `"Q1" if … else "QX"` sites)
  - `x-monitoring/x_monitor/__main__.py` (modify `--queries` help text)
  - `x-monitoring/tests/test_run_post_fetch.py` (extend per-query row assertions if any)
- **Approach:**
  - Replace both `"Q1" if call.call_kind == "account" else "QX"` literals with `call.call_id`.
  - Update `__main__.py:1170` help text from `(Q1..Q6)` to `(A, B1, B2, B3, C1, C2)`.
- **Test scenarios:**
  - Happy: the per-query row's `query_id` for the account call is `A`; for a `call_b_groups` row it is `B1`/`B2`/`B3`; for a `call_c_specs` row it is `C1`/`C2`.
  - Edge: the `degraded.dry_run` path also uses `call.call_id` (same literal replacement).
  - Integration: live run JSON shows A/B/C strings only.
- **Verification:** grep `x_monitor/run.py` for `Q[1-6]` returns zero matches; `--queries` help text shows the new strings.

### U3. Fix n_classifications_written counter

- **Goal:** Counter captures both `insert_posts` inline writes and `_run_post_fetch` post-fetch writes.
- **Requirements:** R6, R7
- **Files:**
  - `x-monitoring/x_monitor/store.py` (bump `self._classifications_written` in `insert_posts_brands_signals`)
  - `x-monitoring/x_monitor/run.py` (move the `n_classifications_written` read to after `_run_post_fetch`)
  - `x-monitoring/tests/test_run_post_fetch.py` or `tests/test_store.py` (extend counter tests)
- **Approach:**
  - In `Store.insert_posts_brands_signals` (around line 1624), after the successful `INSERT OR UPDATE`, bump `self._classifications_written += 1`. Mirror the pattern at line 780.
  - In `cmd_run`, remove the incremental read at line 1293 (`summary["totals"]["n_classifications_written"] += store._classifications_written`). After the post-fetch loop completes, set the counter once from `store._classifications_written`.
- **Test scenarios:**
  - Happy: a write through `insert_posts_brands_signals` increments `store._classifications_written` (unit test).
  - Edge: the dropped path (allow-list validation failure) does NOT increment the counter.
  - Integration: a live run reports `n_classifications_written == COUNT(*) FROM posts_brands_signals WHERE post_id IN (...run's posts...)`.
- **Verification:** unit test for the writer; live run JSON `n_classifications_written` matches the DB row count for the run.

### U4. Re-run pipeline on DS V4 and verify

- **Goal:** Confirm all three fixes produce a clean, accurate run JSON end-to-end.
- **Requirements:** R2, R4, R6 (the integration assertions)
- **Files:** none modified — verification only
- **Approach:**
  - Invoke `X_MONITOR_CLASSIFIER_BASE_URL=https://api.deepseek.com/anthropic ANTHROPIC_MODEL=deepseek-v4-pro python3 -m x_monitor run --limit-per-call 20` and capture the run JSON.
  - Assert: zero `missing_*` entries; every `query_id` matches `^[ABC][123]?$`; `n_classifications_written` equals the DB-side count for the run's posts.
  - Persist the run summary + stdout log to `data/runs/dsv4-live-pipeline-<run_id>.{json,log}`.
- **Verification:** the run JSON satisfies all three integration assertions; the DB row counts match the summary totals.

## Verification Contract

| Gate | Command | Pass criterion |
|---|---|---|
| U1 unit tests | `python3 -m pytest tests/test_cmd_run_keywords.py` | All pass |
| U2 unit tests | `python3 -m pytest tests/test_run.py tests/test_run_post_fetch.py` | All pass; no `Q[1-6]` in run JSON in fixture output |
| U3 unit tests | `python3 -m pytest tests/test_store.py` | All pass; counter assertion holds |
| Static grep | `grep -nE 'Q[1-6]' x_monitor/run.py x_monitor/__main__.py` | Zero matches in active code paths |
| Integration | `X_MONITOR_CLASSIFIER_BASE_URL=… python3 -m x_monitor run --limit-per-call 20` | Run JSON satisfies all three integration assertions (zero `missing_*`, A/B/C strings only, counter matches DB) |
| DB parity | `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM posts_brands_signals WHERE post_id IN (SELECT tweet_id FROM posts WHERE fetched_at > '<run_start>')"` | Equals `totals.n_classifications_written` in run JSON |

## Definition of Done

- U1, U2, U3 merged to main via commit(s).
- U4 live re-run produces a run JSON with empty `missing_*`, all-A/B/C `query_id` values, and `n_classifications_written` matching the DB.
- Run artifacts persisted under `data/runs/dsv4-live-pipeline-*.{json,log}`.
- Working tree clean, `main` pushed to origin.

## Sources

- `x-monitoring/x_monitor/run.py:949` — `load_queries(m, self.data_dir)` call site (the file-load path that misses for every brand)
- `x-monitoring/x_monitor/run.py:1067,1173` — the two `"Q1" if … else "QX"` emission sites
- `x-monitoring/x_monitor/run.py:1293` — the premature `n_classifications_written` read
- `x-monitoring/x_monitor/store.py:780` (existing counter bump pattern) and `:1624` (`insert_posts_brands_signals` — needs the same bump)
- `x-monitoring/x_monitor/__main__.py:1170` — stale `--queries` help text
- `data/runs/dsv4-live-pipeline-20260715T082550.json` — the prior run whose misleading output motivated these fixes