---
title: "cmd_run JSON summary emitted degraded noise, legacy Q-strings, and a zero counter"
module: "x_monitor.run (cmd_run)"
date: "2026-07-16"
problem_type: "runtime_error"
component: "service_object"
severity: "high"
symptoms:
  - "degraded.missing_queries:<brand> block emitted one entry per brand even when the run executed normally"
  - "per-query rows in run JSON reported query_id='Q1' or query_id='Q5' while posts.call_id carried A/B/C strings"
  - "totals.n_classifications_written reported 0 even when posts_brands_signals rows actually landed"
root_cause: "config_error"
resolution_type: "code_fix"
tags:
  - "cmd_run"
  - "run-summary"
  - "json-emission"
  - "brand-keywords"
  - "db-vs-yaml"
  - "call_id"
  - "classification-counter"
related_components:
  - "x_monitor.store"
  - "x_monitor.__main__"
  - "x_monitor.query_plan"
related_plans:
  - "docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md"
  - "docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md"
  - "docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md"
  - "docs/plans/2026-07-13-001-feat-live-a-z-populate-db-plan.md"
related_memory:
  - "memory/2026-07-13-q-retirement-status.md"
  - "memory/brand-keywords-migration-030-gap.md"
  - "memory/b-call-revival-user-direction.md"
  - "memory/x-monitor-migration-rollout.md"
---

## Problem

`x_monitor run` wrote a misleading JSON summary even when the pipeline itself worked: every run reported 20 `degraded.missing_queries:*` entries for retired yaml files, emitted legacy `Q1`/`Q5`/`QX` strings in the per-query `query_id` field (instead of the planner's `A`/`B1`/`B2`/`B3`/`C1`/`C2` call_ids), and reported `n_classifications_written: 0` even when classifications actually landed in `posts_brands_signals`. Operators could not distinguish a real failure from cosmetic noise.

## Symptoms

- Live run JSON (e.g. `data/runs/20260715T091026_0000-2ad50d2d.json`, pre-fix) contained `degraded.missing_queries:<brand>` entries — one per brand in `enabled_models` — every time, regardless of run outcome.
- The `summary.queries[*].query_id` field showed literal `Q1` / `Q5` / `QX` strings. All 4 observable rows in the original 2026-07-15T082550 run had legacy Q-string ids despite `posts.call_id` storing A/B/C strings.
- `totals.n_classifications_written` always read `0` on the live re-run, even when `SELECT COUNT(*) FROM posts_brands_signals WHERE post_id IN (SELECT tweet_id FROM posts WHERE fetched_at >= <run_start>)` returned 15–26 rows.
- Post-fix U4 v3 run (`20260715T091026_0000-2ad50d2d.json`):
  - `degraded: {}` (was 20 entries)
  - All 6 query rows: `query_id ∈ {A, B1, B2, B3, C1, C2}` matching `^[ABC][123]?$`
  - `n_classifications_written: 45` (was 0). 45 = upsert attempts; the unique-row DB count for the same window is 26 (45 = 17 inline writes + 28 post-fetch writes; 19 of the post-fetch writes hit `ON CONFLICT`).

## What Didn't Work

- **U2 v1 (commit `6e15b60`) — literal-replace missed a third call site.** The first U2 pass replaced the two `"Q1" if call.call_kind == "account" else "QX"` literals at the dry-run and per-call error paths in `cmd_run`. Unit tests passed. But the live `completed` row at `run.py:1371` was using `synth_q.id` — a stub `Query` variable populated by `_planned_call_to_query` whose `id` field is the v1.6 `Q`-string id. The literal grep pass missed it; U4 v1's live re-run revealed `Q1`/`Q5` strings still flowing into the JSON. Caught only because the integration assertion ran against a real run (session history).
- **U3 v1 — counter read inside the per-cycle loop.** The pre-fix `cmd_run` accumulated `summary["totals"]["n_classifications_written"] += store._classifications_written` inside the per-call loop. Since `_run_post_fetch` runs once after the loop, the read happened before the post-fetch writer had fired. The counter reported `0` even when the post-fetch path had already inserted rows. Static reading of the pre-fix code looked correct — the counter was being "updated" — but the semantics were wrong (session history).
- **`Store.insert_posts_brands_signals` did not bump the run-level counter at all.** Even after moving the read site, the post-fetch writer at `store.py:1624+` never incremented `self._classifications_written`. The inline writer at `store.py:780` did (legacy path through `insert_posts`). Any fix that moved only the read site without the writer-site bump would still report `0`.

## Solution

Four commits, all landed on `main`:

### U1 — Load brand tokens from `Store.read_primary_brand_keywords()` (`404cb7f`)

In `cmd_run` at `run.py:944`:

```python
# Before: load_queries(m, self.data_dir) — reads retired data/queries/<m>.yaml
# After:
store = Store(self.db_path)
try:
    primary_keywords = store.read_primary_brand_keywords()
except Exception as e:
    summary["degraded"]["missing_brand_keywords"] = str(e)
    primary_keywords = {}
for m in models:
    if m not in primary_keywords:
        summary["degraded"][f"missing_brand_keywords:{m}"] = (
            f"no rows in brand_keywords for brand_id={m!r}"
        )
queries_per_model: dict[str, list[Query]] = {
    m: [
        Query(
            id="Q5",  # legacy Q-id; never reaches the DB
            query_string="(placeholder)",
            enabled=True,
        )
    ]
    for m in models
}
```

The legacy `Query` stub is preserved only to satisfy `apply_skip_order`'s type signature; the v1.7 budget/skip-order machinery is a no-op (cost <= budget always), so the stub never reaches the planner.

### U2 — Emit planner `A/B/C` call_id (`6e15b60`, two sites)

Replace both `"Q1" if call.call_kind == "account" else "QX"` literals with `call.call_id`:

```python
# Before:
"query_id": "Q1" if call.call_kind == "account" else "QX",
# After (dry-run path at run.py:~1067):
"query_id": call.call_id,
# After (completed / per-call row at run.py:1371):
"query_id": call.call_id,
```

`PlannedCall.call_id` is already populated by `query_plan.plan_calls` with the A/B/C strings, so no per-call conditional is needed.

`__main__.py:1170` `--queries` help text updated from `comma-separated query_id filter (Q1..Q6)` to `comma-separated query_id filter (A, B1, B2, B3, C1, C2)`.

### U2 follow-up — third call site `f637e86`

Replace `synth_q.id` with `call.call_id` in the live `completed` row path at `run.py:1371`:

```python
# Before (emitted legacy Q-string into the JSON):
"query_id": synth_q.id,
# After:
"query_id": call.call_id,
```

The cursor bookkeeping at `run.py:1118, 1348, 1363` still uses `synth_q.id` — that path is internal (cursor key per `Query.id`), not JSON output, so it stays.

### U3 — Counter bump + read site (`e1ccc8b`)

`Store.insert_posts_brands_signals` at `store.py:1695–1699`:

```python
self._conn.commit()
# Plan 2026-07-15-003 U3: bump the run-level classification
# counter so the post-fetch path's writes count toward
# `totals.n_classifications_written`. Mirror the inline writer
# at the legacy `insert_posts` site.
self._classifications_written += 1
```

Mirrors the inline writer at `store.py:780` (legacy `insert_posts` path).

`cmd_run` read site at `run.py:1441–1450` — moved out of the per-cycle loop, placed AFTER `_run_post_fetch` returns:

```python
# Before (inside the per-call loop, before post-fetch ran):
# summary["totals"]["n_classifications_written"] += store._classifications_written  # line ~1293
# After (after _run_post_fetch completes):
summary["totals"]["n_classifications_written"] = (
    store._classifications_written
)
summary["totals"]["n_classifications_dropped"] = (
    store._classifications_dropped
)
```

The inline comment at `run.py:1315–1321` documents the rationale: "Do NOT accumulate it here — the per-cycle value is meaningless since post-fetch runs after the loop."

## Why This Works

**U1 root cause:** Migration 030 retired `data/queries/<brand>.yaml` in favor of the `brand_keywords` table (with `is_primary=1` rows). The legacy `load_queries(m, data_dir)` call in `cmd_run` continued to dead-end on the retired files, generating one `missing_queries:<brand>` per enabled brand per run. Reading from `Store.read_primary_brand_keywords()` queries the table that is actually canon now, so the noise disappears. Brands missing from `brand_keywords` (e.g. those still pending q-retirement backfill — `eric`, `mimo`, `nemo_megatron`, `qwen`, `deepseek`, `moonshot_kimi`, `sensechat`, `yi`, `doubao`) surface under a renamed key (`missing_brand_keywords:*`) that operators can pattern-match against the post-migration reality.

**U2 root cause:** Two parallel id systems coexisted. The planner emits `PlannedCall.call_id` (A/B/C strings) which is what `posts.call_id` writes. But the per-run JSON still fed `Query` stubs (from `_planned_call_to_query`) whose `id` field was the v1.6 `Q`-string. Three emission sites read either one. Picking `call.call_id` as the single source of truth aligns the JSON with what `posts.call_id` already records.

**U3 root cause:** `_classifications_written` was an *upsert-attempt* counter, not a *unique-row* counter, and only the inline `insert_posts` writer bumped it. The read site was inside the per-cycle loop, so any post-fetch write happened after the snapshot. Once both writers (`insert_posts` at `store.py:780` and `insert_posts_brands_signals` at `store.py:1699`) increment the same counter, and the read moves to once-after-post-fetch, the snapshot reflects "all classification upserts attempted during this run." The 45-vs-26 delta in the live run is therefore **expected** — not a bug. The counter answers "did the classifier even run?", not "how many new rows landed in the DB?"

## Prevention

**Tests (committed):**

- `tests/test_cmd_run_keywords.py` (new, 3 tests):
  - `test_cmd_run_loads_brand_keywords_from_db` — `Store.read_primary_brand_keywords` is consulted at the top of `cmd_run`; no `missing_queries:*` entries emit; no `missing_brand_keywords` entries when DB has all brands.
  - `test_cmd_run_surfaces_brand_with_no_db_rows` — a brand in `enabled_models` but absent from `brand_keywords` surfaces as `missing_brand_keywords:<brand>`.
  - `test_cmd_run_db_read_failure_surfaces_globally` — a `RuntimeError` from the DB read surfaces as a top-level `missing_brand_keywords` entry, not as 20 per-brand entries.
- `tests/test_cmd_run_query_id.py` (new, 4 tests):
  - `test_account_call_query_id_is_a` — account call → query_id="A".
  - `test_brand_wide_call_query_id_uses_planner_call_id` — B1/B2/B3/C1/C2.
  - `test_no_q_string_in_per_row_query_id` — regression net across all 6 call_ids; no Q-string leaks into any emission path (including the `completed` row path that the U2 v1 fix missed).
  - `test_cli_help_text_uses_new_call_id_strings` — `x-monitor run --help` mentions A/B1/B2/B3/C1/C2.
- `tests/test_cmd_run_classification_counter.py` (new, 3 tests):
  - `test_insert_posts_brands_signals_bumps_counter` — successful upsert increments `_classifications_written` by 1.
  - `test_dropped_classification_does_not_bump_counter` — FK-guard / sentinel-brand / `_dead_letter_enum` paths do NOT increment.
  - `test_counter_read_after_post_fetch_not_per_cycle` — static check that `cmd_run` does not accumulate the counter inside the per-call loop and DOES read it once after `_run_post_fetch`.

**Static guard:** `grep -nE 'Q[1-6]' x_monitor/run.py` should return zero matches in active emission paths. The residual `id="Q5"` in the `Query` stub at `run.py:963–972` is documented as never reaching the JSON (the stub satisfies only `apply_skip_order`'s type signature; v1.7 cost is always under budget so the skip-order machinery is a no-op).

**Integration assertion (U4 v3, live):**

```bash
X_MONITOR_CLASSIFIER_BASE_URL=https://api.deepseek.com/anthropic \
  ANTHROPIC_MODEL=deepseek-v4-pro \
  python3 -m x_monitor run --limit-per-call 20
```

Asserts: `degraded == {}`; every `query_id` matches `^[ABC][123]?$`; `totals.n_classifications_written > 0`. Run JSON + log persisted under `data/runs/dsv4-clean-pipeline-20260715T091026.{json,log}`.

**Meta-lesson:** When a "fix" has multiple call sites sharing a symptom, do not stop at a literal-replace pass. In this PR, U2 had three emission sites for `query_id`; two carried the literal `"Q1"` / `"QX"` and were trivially greppable, but the third carried `synth_q.id` — a stub variable whose `.id` was the legacy Q-string. Static grep `Q[1-6]` returned 1 match (the placeholder stub) and 2 matches (the unfixed emission sites), giving a false-positive "everything migrated" signal. The fix was to audit `synth_X.id` patterns where a stub variable carries the legacy id, not to grep for the literal. The U4 live re-run is what surfaced the gap; unit tests for the third emission site (the `completed` row) are now part of the regression net (session history).

**Follow-up candidates (not in this PR):**

- Docstring the `_classifications_written` semantic as "upsert attempts" (5-min, addresses the 45-vs-26 operator confusion).
- Delete the `queries_per_model` / `apply_skip_order` dead loop (30-min; the v1.7 budget math makes it unreachable).
- Clean `WatchPaths` in `com.fuchitalee.x-monitor.plist` — `x_monitor/data/queries/` and `x_monitor/data/accounts/` are still listed, no longer live paths (no-op, harmless throttle).
- **High-urgency sibling fix (flagged by Related Docs Finder, NOT in this PR):** `x_monitor/__main__.py:84, 177, 190` still call `load_queries(m, paths['data'])` from `cmd_dry_run` / `cmd_queries`. The `data/queries/` directory was deleted in plan 2026-07-11-001 U3, so those three sites will raise `FileNotFoundError` at runtime. Plan 003 U1 fixed `cmd_run` only.

## Cross-references

### Related plans

- `docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md` — parent plan. Retired `data/queries/` and `data/filters/` directories. Plan 003's U1 is the missing tail-end of plan 001's intent (the LAST consumer in `cmd_run` that still read those retired yamls). Same author intent, different unit of work.
- `docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md` — introduced the B1/B2/B3 wide-net call fan-out via `x_query_specs` + `is_primary` on `brand_keywords`. The A/B/C `call_id` strings that plan 003 U2 emits are the canonical labels that plan 002's renderer produces. Plan 003 is a downstream consumer of plan 002's `call_id` contract.
- `docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md` — backfilled the `brand_keywords` table with `is_primary=0` rows. Plan 003 U1's `read_brand_keywords` path consumes exactly this table. Without this backfill, U1's DB read would return 8/20 brands (per `brand-keywords-migration-030-gap` memory) and emit `missing_brand_keywords` entries for the rest.
- `docs/plans/2026-07-13-001-feat-live-a-z-populate-db-plan.md` — established the live-run pattern that plan 003's U4 v3 re-run mirrored. The original 2026-07-15T082550 run referenced in plan 003 was a direct descendant of this smoketest; the misleading JSON output from that run is what plan 003 set out to fix.

### Related memory

- `memory/2026-07-13-q-retirement-status.md` — **now stale (refresh recommended)**. Memory asserts the Q1-Q6 framework is "still wired into live prod." Plan 003's U1+U2+U3 closed the `cmd_run` side of that surface (the operator-visible JSON). The `config.py` Literal/validator and the deeper plumbing may still carry Q-strings, but `cmd_run`'s JSON no longer leaks them. Refresh this memory.
- `memory/brand-keywords-migration-030-gap.md` — references the 8/20 brand gap that plan 2026-07-10-001 closed. After that backfill, plan 003 U1's `read_primary_brand_keywords` reads from a fully populated table.
- `memory/b-call-revival-user-direction.md` — the user-chosen `is_primary` column is what makes plan 003 U1's DB read bounded (`read_primary_brand_keywords` filters to `is_primary=1`). Direct prerequisite.
- `memory/x-monitor-migration-rollout.md` — staging→prod rollout procedure. Plan 003 doesn't add a migration, but the same discipline applies to any future plan that updates the run JSON shape.

### Stale patterns flagged for refresh

- `x-monitoring/x_monitor/__main__.py:84, 177, 190` — three remaining `load_queries(m, paths['data'])` call sites in `cmd_dry_run` and `cmd_queries`. The `data/queries/` directory was deleted in plan 2026-07-11-001 U3; these sites will raise `FileNotFoundError` at runtime. **High urgency, NOT in this PR.**
- `docs/reference/twitterapi-live-queries-by-model.md` — built around the Q1-Q6 yaml framework. Plan 001 deleted `data/queries/` and `data/filters/`; plan 003 retired the runtime reads. Doc should be rewritten to describe the `x_query_specs` + `brand_keywords` + `is_primary` surface.
- `docs/reference/lookup-tables.md` — references `Q1..Q6` and `call_c_specs` (renamed to `x_query_specs` in plan 002 R20). Q-string references made even more stale by plan 003 U2.
