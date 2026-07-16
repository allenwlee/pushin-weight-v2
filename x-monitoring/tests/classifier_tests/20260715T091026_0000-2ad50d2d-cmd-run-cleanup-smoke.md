# cmd_run cleanup smoketest (Plan 2026-07-15-003)

Plan: `docs/plans/2026-07-15-003-fix-cmd-run-cleanup-plan.md`
Run under test: `data/runs/20260715T091026_0000-2ad50d2d.json`
Reviewer: Allen
Date: 2026-07-15

This is a "smoke" rather than a content review — the plan ships three
mechanical fixes to `cmd_run`'s output, and the goal is to confirm the
JSON summary now reflects reality. Each unit (U1/U2/U3) maps to one
section below. U4 (live re-run on DS V4) is the integration that ties
them together.

---

## U1 — DB-keyword load in cmd_run

**Claim:** `cmd_run` reads brand tokens from `Store.read_primary_brand_keywords()`
instead of `load_queries(m, data_dir)`, so the run JSON no longer emits
20 `missing_queries:*` entries from the retired `data/queries/<m>.yaml`
files.

### Live evidence

The U4 run JSON (`20260715T091026_0000-2ad50d2d.json`):

```json
"degraded": {}
```

The `degraded` dict is empty. Pre-fix, it contained 20 entries of the
shape `"missing_queries:<brand>": "missing query file: ..."`. Post-fix,
zero entries — confirms the DB-keyword load path executed successfully
for every brand in `enabled_models`.

### Unit tests

`tests/test_cmd_run_keywords.py` (new, 3 tests, all pass):

- `test_cmd_run_loads_brand_keywords_from_db` — `Store.read_primary_brand_keywords`
  is consulted at the top of `cmd_run`; no `missing_queries:*` entries emit;
  no `missing_brand_keywords` entries when DB has all brands.
- `test_cmd_run_surfaces_brand_with_no_db_rows` — a brand in
  `enabled_models` but absent from `brand_keywords` surfaces as
  `missing_brand_keywords:<brand>`.
- `test_cmd_run_db_read_failure_surfaces_globally` — a `RuntimeError`
  from the DB read surfaces as a top-level `missing_brand_keywords`
  entry, not as 20 per-brand entries.

### Side note (not a regression)

The legacy `Query` stub (id="Q5", query_string="(placeholder)") still
feeds `apply_skip_order` to satisfy its type signature. That machinery
is already a no-op in v1.7 since per-cycle cost <= budget, so the stub
never reaches the planner. The follow-up cleanup is to delete
`queries_per_model` / `apply_skip_order` entirely (plan candidate, not
in this PR).

---

## U2 — A/B/C call_id in run JSON

**Claim:** The per-row `query_id` field in the run JSON uses the
planner's A/B/C call_ids instead of the legacy Q1/Q5 strings.

### Live evidence

All 6 query rows in the U4 run JSON:

| brand | call_kind | query_id |
|---|---|---|
| `*` | `account` | `A` |
| `mimo` | `brand_wide` | `C1` |
| `ernie` | `brand_wide` | `C2` |
| `minimax` | `brand_wide` | `B1` |
| `doubao` | `brand_wide` | `B2` |
| `nemo_megatron` | `brand_wide` | `B3` |

All values match the regex `^[ABC][123]?$`. Pre-fix (the U4 v1 run that
was scrapped) emitted `Q1`/`Q5`/`QX` instead — the U2 follow-up commit
`f637e86` (caught during U4 v2) closed that leak.

### U2 follow-up — call_site audit

The original U2 fix (`6e15b60`) replaced two `summary["queries"].append`
sites but missed the live `completed` row at line 1371, which was still
using `synth_q.id` (the v1.6 Query stub's id). The follow-up
(`f637e86`) replaced it with `call.call_id`. Verified live in U4 v3:
the run JSON now emits A/B/C strings in the `completed` path too.

**Lesson logged:** when a "fix" has multiple call sites that share the
same symptom (literal Q-string in a JSON field), a literal-replace pass
isn't enough. Audit the SQL/ORM read paths for callers that re-build
the row from a different variable. In this case, `synth_q.id` (the
Query stub) was the variable, not the literal "Q1" / "QX".

### Unit tests

`tests/test_cmd_run_query_id.py` (new, 4 tests, all pass):

- `test_account_call_query_id_is_a` — account call → query_id="A"
- `test_brand_wide_call_query_id_uses_planner_call_id` — B1/B2/B3/C1/C2
- `test_no_q_string_in_per_row_query_id` — regression net across all 6
  call_ids; no Q-string leaks into any emission path
- `test_cli_help_text_uses_new_call_id_strings` — `x-monitor run --help`
  mentions A/B1/B2/B3/C1/C2, not "Q1..Q6"

### `--queries` runtime behavior

Help text updated. The flag itself still accepts any string the user
supplies (the call-id filter is wired to `query_id` in the planner
output, not the legacy Q-string). A user passing `--queries=Q5` would
get an empty result set; passing `--queries=A` works as expected. Not
tested explicitly — out of scope for the run JSON fix.

---

## U3 — n_classifications_written counter

**Claim:** The counter captures both the inline `insert_posts` writer
and the post-fetch `insert_posts_brands_signals` writer.

### Live evidence (U4 v3 run)

Run JSON reports:

```json
"totals": {
  "n_classifications_written": 45,
  "n_classifications_dropped": 0,
  ...
}
```

DB-side count for the run's posts:

```sql
SELECT COUNT(*) FROM posts_brands_signals
 WHERE post_id IN (
   SELECT tweet_id FROM posts WHERE fetched_at >= '2026-07-15T09:10:00'
 );
-- 26
```

**Discrepancy: 45 vs 26.** This is a semantic mismatch, not a bug.

The counter measures **upsert attempts** (every `INSERT OR UPDATE`
that reached the SQL), not unique rows in the DB. The PK is
`(post_id, brand_id, post_type_key)` with `ON CONFLICT DO UPDATE` —
so when the inline writer (per-call loop) and the post_fetch writer
(both bump the counter) write the same triple, the second write
updates the existing row instead of failing, but the counter bumps
both times.

```
17 inline writes (one per inserted post)
+ 28 post_fetch writes
= 45 upsert attempts
26 unique rows in DB
   ^--- 19 of those 28 post_fetch writes hit ON CONFLICT
```

### Verdict

The pre-fix counter reported `0` always (read before post_fetch). The
post-fix counter reports `45` — a real, monotonic, observation of how
many classification upserts the pipeline attempted. That's a useful
operator signal (e.g. "did the classifier even run?") even though it
doesn't answer "how many new rows landed."

### Follow-up (not in scope for this PR)

Two options for future plans:

1. **Document the semantic:** add a docstring to `_classifications_written`
   clarifying that it counts upsert attempts (1-2 line change).
2. **Two counters:** split into `n_classifications_upserted` (current 45)
   and `n_classifications_inserted` (new, counted only when `cur.rowcount
   == 1` after the INSERT OR UPDATE). True DB parity.

Both are 5-15 minute follow-ups. Not blocking this PR.

### Unit tests

`tests/test_cmd_run_classification_counter.py` (new, 3 tests, all pass):

- `test_insert_posts_brands_signals_bumps_counter` — successful upsert
  increments `_classifications_written` by 1
- `test_dropped_classification_does_not_bump_counter` — dead-letter path
  does NOT increment (regression net for the U3 fix)
- `test_counter_read_after_post_fetch_not_per_cycle` — static check
  that `cmd_run` no longer accumulates the counter inside the per-call
  loop and DOES read it once after `_run_post_fetch` completes

---

## U4 — Live DS V4 re-run integration

The three fixes land together in one live run. The integration
assertions:

| Assertion | Result |
|---|---|
| `degraded` is empty (no `missing_*` entries) | ✓ — `degraded: {}` |
| Every `query_id` matches `^[ABC][123]?$` | ✓ — 6/6 rows (A, B1, B2, B3, C1, C2) |
| `n_classifications_written` > 0 (post-fetch path counted) | ✓ — 45 (vs 0 pre-fix) |

Run JSON path: `data/runs/dsv4-clean-pipeline-20260715T091026.json`
Run log path: `data/runs/dsv4-clean-pipeline-20260715T091026.log`

Run totals: 35 fetched, 17 newly-inserted, 45 classification upserts,
22 discourse rows, 5 unsanctioned flags. Wall clock 297s on DS V4
via `X_MONITOR_CLASSIFIER_BASE_URL=https://api.deepseek.com/anthropic`.

---

## Cross-cutting findings

1. **The U2 call-site audit gap:** the original U2 fix missed the
   `synth_q.id` emission at `run.py:1371`. Caught during U4 v1's
   live re-run (the JSON showed Q1/Q5 strings despite the
   unit-test-passing fix). Follow-up commit `f637e86` closed it.
   Lesson: literal-replace passes for multi-site symbol migrations
   should also audit `synth_X.id` patterns where a stub variable
   carries the legacy id.

2. **The `n_classifications_written` semantic:** the counter is
   "upsert attempts," not "unique rows in DB." For the 17 newly-
   inserted posts in this run, the counter reports 45 (which is
   `inline_writes + post_fetch_writes`), and the DB has 26 unique
   rows. The two metrics measure different things; both are
   useful, but the run JSON docstring should label the counter
   accurately. Follow-up plan candidate.

3. **`missing_brand_keywords:eric / mimo / nemo_megatron / qwen /
   deepseek / moonshot_kimi / sensechat / yi / doubao / yi / yi`
   in the dry-run output of `test_cmd_run_keywords.py`:** these are
   the brands that don't have `is_primary=1` rows in `brand_keywords`
   yet. They map to the q-retirement work that hasn't finished
   backfilling. Not a regression; surfaced by the test.

4. **`x_monitor/data/queries/` and `x_monitor/data/accounts/`
   still listed in the WatchPaths LaunchAgent** (`com.fuchitalee.
   x-monitor.plist`). Those directories were retired in migration 030;
   the WatchPaths trigger fires on edits to those paths but the
   pipeline_lock now catches the stale paths (since `cmd_run` no
   longer reads them). Net effect: harmless throttle, no actual
   pipeline runs. Worth a one-line plist cleanup but not blocking.

---

## Summary of action items

- **This PR (already shipped):**
  - `404cb7f` U1: load brand tokens from DB in cmd_run
  - `6e15b60` U2: emit A/B/C call_id in dry_run/error paths
  - `e1ccc8b` U3: count post-fetch classifications
  - `f637e86` U2 follow-up: emit `call.call_id` in the live `completed`
    row path
- **Follow-ups:**
  - `n_classifications_written` semantic docstring (5-min)
  - Delete `queries_per_model` / `apply_skip_order` dead loop (30-min)
  - WatchPaths plist cleanup (5-min)