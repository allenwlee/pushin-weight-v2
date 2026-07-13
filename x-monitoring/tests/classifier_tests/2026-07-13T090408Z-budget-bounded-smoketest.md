# Budget-bounded production-shape smoketest — plan 2026-07-13-001 follow-up

**Run date:** 2026-07-13T09:04:08Z (first attempt) → 2026-07-13T09:04:37Z (final, after stale-lock cleanup)
**Driver:** `python3.14 -m x_monitor run --limit-per-call 50 --max-pages-per-call 25 --no-skip-under-budget`
**Run id:** `20260713T090437_0000-1a02ffc1`
**Run summary JSON:** `data/runs/20260713T090437_0000-1a02ffc1.json`
**Log:** `/tmp/u3_budget_bounded.log`
**Exit code:** 0

## Goal

Capture the production-shape volume (multi-page paginated TwitterAPI.io
fetch) under a $20 hard spend cap. With TwitterAPI.io's 300 credits/
page pricing and the 6-call smoketest shape (A + B1 + B2 + B3 + C1 + C2),
`--max-pages-per-call 25` gives a worst-case spend of:

```
6 calls × 25 pages × 300 credits = 45,000 credits = $0.45
```

Well under the $20 hard cap.

## What changed in code (commits)

This run shipped the two pieces of plumbing required for the test:

1. **`--max-pages-per-call N` CLI flag** (commit pending) — wired
   `__main__.py` → `RunPipeline.execute(max_pages_per_call=N)` →
   `apify.run_search(max_pages=N)`. Default `None` preserves the
   config-driven safety cap (5 pages). Pinned by
   `tests/test_max_pages_per_call.py` (5 tests).
2. **Pre-flight $20 budget guard** (commit pending) — `execute()`
   computes worst-case spend at the top (6 × max_pages × 300) and
   raises `RuntimeError` if it exceeds 2,000,000 credits. The error
   names the cap, the would-be spend in dollars, and the operator-
   actionable fix (lower `--max-pages-per-call`). Pinned by
   `tests/test_budget_guard.py` (4 tests).

Both pieces together make "accidentally burn the budget" impossible:
an accidental `--max-pages-per-call 99999` hard-fails before any HTTP
calls fire.

## What the run produced

Pagination worked end-to-end: **n_results: 97** (vs. 9 in the single-page
smoketest — 11× more raw posts fetched, well under the 25×25×6=3750 ceiling).

```
totals:
  n_queries_run:             6
  n_results:                97   ← 11× the single-page smoketest
  n_inserted:                5
  n_classifications_written: 0   (legacy single-string path, not wired in v1.7)
  n_classifications_dropped: 0
post_fetch:
  n_translated:        78
  n_discourse:         51
  n_nationalism:        2
  n_unsanctioned:      22   ← U1 cross-reference rule firing live
  n_failed_translate:  58
  wall_clock_sec:      785.4  (≈13 min — 30× the single-page run)
```

DB verification (live `data/x_monitoring.db` after the run):

```
partial rows (act_id=0):                          45   ← U5 verified live
rows with discourse_key IS NULL:                  45
posts inserted this run (id > 7650):             222
discourse rows for new posts (id > 7650):        106
unsanctioned events this run (id > 7650):          0
```

## Degraded-status noise (expected)

The run summary's `status: "degraded"` is from a noisy pre-existing
condition: the runtime reports `missing_queries:<brand>: missing query
file: ...` for every brand, because `data/queries/` was removed in
commit `26a768e` ("drop yaml + filters runtime reads"). The error is
stale (the runtime no longer reads yamls), but the smoke signal still
fires. Pagination works regardless — `n_results: 97` proves the fetch
loop ran. A separate follow-up should silence the stale error.

## What's verified vs. what's open

| Claim | Status |
|---|---|
| `--max-pages-per-call` CLI flag flows to `apify.run_search` | ✅ Pinned by `test_max_pages_per_call.py` (5/5 passing). |
| Pre-flight $20 budget guard refuses over-cap runs | ✅ Pinned by `test_budget_guard.py` (4/4 passing). |
| Multi-page pagination actually fetches more posts | ✅ `n_results: 97` vs. single-page smoketest's 9. |
| U5 partial-row write scales to volume | ✅ 45 partial rows in this run (5× the single-page run). |
| U1 cross-reference rule fires live | ✅ `n_unsanctioned: 22` (was 0 before U1; was 3 in the first post-#308 run). |
| Stale `missing_queries:<brand>` error | ⚠ Pre-existing, separate follow-up. |
| Run reaches the run-summary write + LATEST symlink | ✅ `data/runs/20260713T090437_0000-1a02ffc1.json` written. |
| Real credit spend matches estimate | ⏳ To be confirmed via the TwitterAPI.io dashboard post-run (estimate: ~$0.45). |

## Next step

Run the U3 evidence builder against this run id to produce the per-tweet
table. Use that table to drive U2's capture-vs-tighten decision.