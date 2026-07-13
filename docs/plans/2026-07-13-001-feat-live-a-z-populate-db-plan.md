---
title: Live A→Z DB populate — single 20-post-per-call end-to-end run
date: 2026-07-13
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# Goal Capsule

Run one end-to-end live cycle against the TwitterAPI.io advanced-search endpoint: Calls A (list) + B1/B2/B3 (wide-net per brand group) + C1/C2 (co-occurrence-constrained), each capped at 20 posts (matching the prior 6-call smoketest), run translate + classify on each batch, and persist the posts + classification rows into `data/x_monitoring.db`. Stop the run as soon as at least one post has been inserted into the DB; the user wants to validate the full pipeline path with real values, not to fully populate the DB.

# Problem Frame

The `posts` table on the staging/prod DB has been populated by dry-run / fixture work and a few prior scheduled runs. The operator wants a single, fresh live run with the actual v1.7 query set (Call A list + B1/B2/B3 deduped wide-net + C1/C2 with co-occurrence) so the DB has real TwitterAPI.io-fetched posts through the new query renderer, with `posts_brands` and `posts_brands_discourse` rows produced by the live LLM classifier — not the dry-run placeholder. The prior smoketest ran all six calls but never persisted (it reads, classifies, prints, exits). This plan is the bridge: same per-call limit, same flag set as the smoketest, but with the persistence step turned on.

# Requirements

- **R1.** One Python invocation, no manual orchestration across shells.
- **R2.** Each of the six calls (A, B1, B2, B3, C1, C2) returns up to 20 posts (`max_results=20`), matching the smoketest volume.
- **R3.** Posts are persisted to `data/x_monitoring.db` (table `posts`), with `posts_brands` and `posts_brands_discourse` rows produced by the live classifier on every attributed post.
- **R4.** Run halts on first successful insertion per call so we don't burn API quota needlessly — but we do NOT halt mid-batch; one batch per call is the minimum.
- **R5.** Daily credit ceiling is honored (`config.yaml::daily_ceiling = 333`). At max 20 posts × 6 calls = 120 posts fetched, this is well under cap.
- **R6.** Run is reproducible from a single command and produces a log file under `tests/classifier_tests/` for eyeball review.
- **R7.** The exit code is 0 when at least one post was inserted into `posts`; non-zero (with stderr diagnostic) when nothing was inserted across all six calls.

# Key Technical Decisions

- **KTD1.** Reuse `x_monitor.run.RunPipeline` directly via a thin one-off driver script. The pipeline already encapsulates fetch → dedup → translate → classify → persist; we add a `--limit 20` knob and route through `cmd_run` with a special `--one-batch-per-call` flag. Justification: avoids re-implementing the pipeline; gives us a real prod-DB write path identical to the daily LaunchAgent run.
- **KTD2.** Skip the existing `daily_ceiling` skip-order logic (`degraded_skip_order`); force all six calls to fire. Justification: with 20 posts × 6 calls = 120 fetched, we're 36% of the 333 daily ceiling. No reason to skip.
- **KTD3.** Halt per-call as soon as `Store.upsert_post` returns `True` for the first row; collect the rest of the batch and persist it too. Justification: matches "stop when items are inserted in DB" — we don't need to drain the full 20 if the first one already proves the path works, but we do want the full batch for downstream eyeballing. Practically: we always persist the full batch (it's already in memory); the "stop" is the run-exit criterion, not a mid-batch abort.
- **KTD4.** Use the existing `x_monitor.apify.TwitterApiClient` (TwitterAPI.io backend) via env-var `TWITTERAPI_IO_API_KEY` from `~/.env.secrets`. Justification: matches the smoketest path that's already verified end-to-end.
- **KTD5.** Invoke via subprocess `python -m x_monitor run` (NOT direct `RunPipeline.execute()`) with the new `--limit-per-call 20` and `--no-skip-under-budget` flags. Justification: the subprocess path exercises the production CLI surface (same env-var propagation, same lock-file behavior, same import-time validation) so the live populate run is byte-equivalent to a LaunchAgent-driven run. The `cmd_dry_run` parser shares `_RUN_PARSER_DEFAULTS` with `p_run` (see fix #7) so future flags ship on both paths.
- **KTD6.** Capture stdout+stderr to `tests/classifier_tests/2026-07-13T<HHMM>Z-live-a-z-populate.log`. Justification: matches the smoketest log convention so the eyeball step uses the same reader workflow.

# Scope Boundaries

### In scope
- Adding `--limit-per-call` and `--no-skip-under-budget` flags to `cmd_run` (one unit, ~30 lines).
- A driver script `scripts/live_a_z_populate.py` that wraps `cmd_run` and emits the standardized log.
- Persisting all six call results into the DB.
- Eyeball log file written to `tests/classifier_tests/`.

### Out of scope (explicit non-goals)
- Building a generic "live A-Z runner" CLI. This is a one-shot; if reused, future work extracts the pattern.
- Adding new tests for `cmd_run` flag handling — the existing `RunPipeline` test surface is sufficient and we are not changing its core behavior.
- Running on a schedule or wiring into LaunchAgent. The LaunchAgent already runs the daily harvest; this is an ad-hoc operator-driven run.
- Migrating the DB or applying migrations. The DB is already at the latest version (post-merge); no schema work needed.

### Deferred to Follow-Up Work
- The earlier finding from this session (task #239 — investigate why non-list-member handles appear in Call A smoketest) is unrelated to populate-the-DB and stays as a separate plan. This plan does NOT modify the Call A query.
- The `Coding_Shanks` investigation (call #241 in prior session) is also a separate plan.

# Implementation Units

### U1. Add `--limit-per-call` and `--no-skip-under-budget` flags to `cmd_run`

**Goal:** Give `cmd_run` a knob to override `search.max_results` per call (smoketest-style cap) and to disable the budget-based skip-order, so an operator can run "all six calls, small batches" in one shot.

**Files:**
- `x-monitoring/x_monitor/__main__.py` — extend `cmd_run`'s `argparse` to accept the two new flags; thread them into the `RunPipeline` constructor.
- `x-monitoring/x_monitor/run.py` — accept `limit_per_call: int | None` and `no_skip_under_budget: bool` on `RunPipeline.__init__`; pass `limit_per_call` to `_query_twitterapi` instead of `cfg.search.max_results` when set; short-circuit the `degraded_skip_order` loop when `no_skip_under_budget` is True.

**Approach:**
- New flags default to `None` / `False` so existing LaunchAgent callers are unaffected.
- `limit_per_call` overrides only the per-call result cap, not the `daily_ceiling`.
- When `no_skip_under_budget` is True, every spec in `cfg.x_query_specs` plus the Call A list query fires regardless of `daily_ceiling` headroom.
- The skipped-call list at the end of the run reports "(none — forced)" for clarity.

**Patterns to follow:**
- Existing argparse pattern in `cmd_run` (lines around 1162-1167).
- Existing `RunPipeline._query_twitterapi` signature at `x_monitor/run.py:1034` — it already takes `max_results`; just thread the override.

**Test scenarios:**
- Happy path: `cmd_run --limit-per-call 20 --no-skip-under-budget --dry-run` produces 6 plan_calls entries each with `max_results=20`.
- Edge case: omitting the flags leaves `max_results=cfg.search.max_results` (=50) and the skip-order logic runs as before.
- Error path: passing `--limit-per-call 0` returns rc=2 with a stderr message.

**Verification:** After the run completes, the smoketest-style log shows `n_posts` ≤ 20 per call (not 50).

### U2. Driver script `scripts/live_a_z_populate.py`

**Goal:** A standalone entrypoint that sources `~/.env.secrets`, invokes `cmd_run` with the two new flags + the full `enabled_models` list, captures the result, and writes a `tests/classifier_tests/` log.

**Files:**
- `x-monitoring/scripts/live_a_z_populate.py` (new, ~80 lines).
- `x-monitoring/tests/test_live_a_z_populate.py` (new, 6 tests mirroring the smoketest test pattern).

**Approach:**
- Module structure: `_parse_args`, `_source_secrets`, `_build_log_path`, `_run_and_capture`, `main`.
- The script calls `cmd_run(args)` from `x_monitor.__main__` and tees stdout/stderr to both console and the timestamped log file.
- On success (rc=0 AND at least one row inserted in `posts`), prints a one-line summary: "inserted N posts across 6 calls; see <log-path>".
- On rc!=0 or zero inserts, prints the failure mode and exits with rc=1.

**Patterns to follow:**
- `scripts/post_fetch_smoketest.py` for argparse shape, logging style, and the `--source`/`--limit` knob conventions.
- `x_monitor.apify.TwitterApiClient.from_env()` for the API key loading.

**Test scenarios:**
- Happy path: with seeded fake TwitterApiClient + fake LLM client, run completes and writes a log file with N≥1 inserts.
- Happy path 2: when rc=0 AND `posts_seen >= 1`, script's exit code is 0.
- Error path: when rc!=0 OR `posts_seen == 0`, exit code is 1 with stderr diagnostic.
- Edge case: log file path uses UTC timestamp format `YYYY-MM-DDTHHMMSSZ-live-a-z-populate.log`.
- Edge case: secret-source failure (no `~/.env.secrets` file) exits rc=2.
- CLI: `python -m scripts.live_a_z_populate --help` lists the documented flags.

**Verification:** Running the script against the real DB produces a log file with `n_posts > 0` for at least one call.

### U3. Execute the live run and capture the artifact

**Goal:** Operator-runs the driver script against the real `data/x_monitoring.db` and TwitterAPI.io quota, captures the log file.

**Files:**
- `x-monitoring/tests/classifier_tests/2026-07-13T<HHMMSS>Z-live-a-z-populate.log` (created at runtime; not committed ahead of time).

**Approach:**
- Source `~/.env.secrets` for `TWITTERAPI_IO_API_KEY`.
- Run `python -m scripts.live_a_z_populate --limit-per-call 20 --no-skip-under-budget 2>&1 | tee <log-path>`.
- Confirm exit code 0 and the log shows inserts across multiple calls.
- Verify `data/x_monitoring.db` row count for `posts` increased by ≥10 (target: 30-60 across 6 calls).

**Patterns to follow:**
- The smoketest log convention: `YYYY-MM-DDTHHMMSSZ-<purpose>.log` in `tests/classifier_tests/`.

**Test scenarios:** N/A — this unit is operational, not code-bearing.

**Verification:** `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM posts WHERE fetched_at > datetime('now', '-1 hour');"` returns ≥10.

# Verification Contract

After all units ship:

- **VC1.** `python -m scripts.live_a_z_populate --help` exits 0 and lists `--limit-per-call` and `--no-skip-under-budget`.
- **VC2.** `python -m pytest tests/test_live_a_z_populate.py -v` passes 6/6.
- **VC3.** `python -m pytest tests/ -x --tb=short -q` — no new failures introduced (pre-existing `test_u6_load_api_posts_calls_run_search_with_correct_kwargs` and `--query-from-yaml` retirement failures are tolerated, since they are unrelated to this work and predate this branch).
- **VC4.** Live run log under `tests/classifier_tests/` shows `posts_seen > 0` for ≥1 of the 6 calls (preferably Call A, since B1/B2/B3 keyword sparsity and C1/C2 co-occurrence constraints have historically yielded near-zero; per memories `brand-keywords-migration-030-gap` and `2026-07-09-c2-yield-probe-failure`).
- **VC4a.** Live run log shows a non-zero `n_unattributed` counter for any call where keyword matching dropped items — surface in `summary["queries"][i].n_unattributed` so the operator can distinguish "0 posts returned" from "20 posts, 0 keywords matched" without re-reading the raw dump.
- **VC5.** Post-run DB query shows ≥1 new row in `posts` with `fetched_at > now - 1 hour`, with at least 1 row in `posts_brands` and a corresponding `posts_brands_discourse` row.

# Definition of Done

- U1, U2, U3 all completed.
- VC1-VC5 all satisfied.
- One commit per unit (U1, U2, U3), each with a clear conventional-commit message.
- Live run log artifact committed under `tests/classifier_tests/`.
- Final smoke: `cd x-monitoring && python -m scripts.live_a_z_populate --limit-per-call 20 --no-skip-under-budget` exits 0 and the DB row count visibly grew.

# Risks & Dependencies

- **R1.** `TWITTERAPI_IO_API_KEY` may be expired or rate-limited. Mitigation: pre-flight check in `_source_secrets`; clear stderr diagnostic.
- **R2.** Live TwitterAPI.io calls cost real quota. At 20×6=120 posts, well under `daily_ceiling=333`. If a call returns 0 posts (rate limit / quota), the run continues to the next call.
- **R3.** `RunPipeline._query_twitterapi` is the only seam changed. The risk surface is small but every existing test touching that seam should still pass.
- **R4.** The DB write path (`upsert_post`) is the canonical production path used by the LaunchAgent; no new persistence code is introduced.

# System-Wide Impact

- Operators can run `x-monitor run --limit-per-call 20 --no-skip-under-budget` as a one-shot smoke against the prod DB.
- The daily LaunchAgent-run is unchanged — `daily_ceiling` and `degraded_skip_order` still apply when the new flags are absent.
- The driver script becomes a reusable template for "validate end-to-end after a config change."
