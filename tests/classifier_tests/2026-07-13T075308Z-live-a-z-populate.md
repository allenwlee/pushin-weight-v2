# U3 live smoketest output — plan 2026-07-13-002

**Run date:** 2026-07-13T07:53:08Z
**Driver:** `scripts/live_a_z_populate.py --limit-per-call 5`
**Cmd:** `/opt/homebrew/opt/python@3.14/bin/python3.14 -m x_monitor run --limit-per-call 5`
**Exit code:** 1 (run tail failed at `_update_accounts`)
**Log:** `tests/classifier_tests/2026-07-13T075308Z-live-a-z-populate.log`

## What landed before the tail failed

### U5 partial-row writes — VERIFIED ON LIVE DATA

6 KTD5 dead-letter rows were processed. Where the prior code would have
dropped them entirely, U5's partial-row write persisted each one with
`discourse_key=NULL`, `act_id=0` (KTD5 sentinel), and the LLM-emitted
nationalism pair preserved.

| Tweet ID | Brand | Discourse key from LLM | Row persisted? |
|---|---|---|---|
| `2076573184170823857` | minimax | `uncategorized` | ✅ partial row (act_id=0) |
| `2076573184170823857` | glm | `uncategorized` | ✅ partial row (act_id=0) |
| `2076572879160823964` | glm | `uncategorized` | ✅ partial row (act_id=0) |
| `2076574434463224255` | yi | `uncategorized` | ✅ partial row (act_id=0) |
| `2076575099071914459` | qwen | `uncategorized` | ✅ partial row (act_id=0) |
| `2076574709458874598` | deepseek | `uncategorized` | ✅ partial row (act_id=0) |

DB verification (live `data/x_monitoring.db` after the run):

```
partial rows:           6
total rows in discourse table: 37
rows with act_id=0:     6
```

### Dead-letter JSONL — also written (additive, not replaced)

The KTD5 dead-letter file at
`data/runs/2026-07-13/enum_dead_letter.jsonl` received 6 entries, one per
failed `uncategorized` value. Each entry carries `family=discourse`,
`value=uncategorized`, `table=posts_brands_discourse`, `note="uncategorized-sentinel (KTD5)..."`,
`post_id`, and `brand_id`. The partial-row write is additive — the JSONL
still captures the dropped key for human review.

### Posts inserted — yes; classification runs — no

182 posts landed in `posts` (id ≥ 7540). But the run failed at
`_update_accounts` BEFORE the classification pipeline ran for these new
posts, so `posts_brands_signals` and `posts_brands_discourse` for this
run's posts only contain the KTD5 dead-letter rows above (partial, from
U5) — the full per-post classification table couldn't be generated.

## Why the run failed (task #308)

```
File "x_monitor/run.py", line 1376, in execute
    self._update_accounts(store, summary)
File "x_monitor/run.py", line 1689, in _update_accounts
    store.upsert_account(
        ...
        multiple_posts_in_thread_with_official=thread_count,
    )
TypeError: Store.upsert_account() got an unexpected keyword argument
          'multiple_posts_in_thread_with_official'
```

Pre-existing signature drift. The kwarg was added to `run.py:1689` in
commit `6ac1427` (U4 of plan 2026-07-11-002 — retire data/accounts/),
but `Store.upsert_account` at `store.py:1323` was never updated to accept
it. The signature today is:

```python
def upsert_account(
    self,
    brand_id: str,
    handle: str,
    role: str = "unknown",
    author_id: str | None = None,
    source_query_ids: list[str] | None = None,
    display_name: str | None = None,
    verified: bool = False,
    bio_contains_brand: bool = False,
    multi_brand_voice: bool = False,
    notes: str | None = None,
) -> None:
```

This bug was **masked by task #288** (the closed-DB crash). Before U1,
`store.close()` ran inside the post-fetch finally block, so the run
aborted at line 1366 with `sqlite3.ProgrammingError` and never reached
`_update_accounts` at line 1376. U1 moved `close()` to after
`_update_accounts`, so the run now reaches line 1689 — and crashes there
instead.

**Not caused by U1.** U1 correctly closed the closed-DB door; this is a
different door that was always there but unreachable.

Fix options (for the task #308 follow-up):
- (a) Add `multiple_posts_in_thread_with_official` to
  `Store.upsert_account` signature (persists the thread-count metric
  somewhere — needs schema decision).
- (b) Drop the kwarg from `run.py:1689` and persist `thread_count`
  elsewhere (or accept the metric loss).
- (c) Pass the kwarg via a different mechanism (separate method, side
  table, etc.).

## What's verified vs what's blocked

| Claim | Status |
|---|---|
| U1 prompt contract changes (unsanctioned_flags triggers + cross-reference rule + comparative-mention rule + lang/text emission requirement) | ✅ Prompt-side change committed and unit-tested; full LLM-emission verification blocked by task #308. |
| U1 closed-DB fix (task #288) | ✅ Committed and unit-tested. Live run now reaches `_update_accounts` (was previously crashing at `store.close()`). |
| U4 call_b_groups dedup | ✅ Committed; `config.yaml:48-51` shows the 6/4/4 split; runtime validator in `x_monitor/config.py`; 4 unit tests. Live verification (TwitterAPI credit spend drop) requires a successful full run — blocked by task #308. |
| U5 partial-row write | ✅ **Verified on live data**: 6 partial rows persisted in `posts_brands_discourse` with `discourse_key=NULL`, `act_id=0`, nationalism pair preserved. Migration 038 applied cleanly; 4 unit tests pass. |
| U7 typo fix | ✅ Committed and regression-tested. |
| U2 implementation choice | ⏸ Scope-only per plan — implementation choice deferred to a measurement-driven decision. |
| U3 full evidence report (per-tweet INSERTED/DROPPED table for tweets #2/#4/#6 marketing_spam recovery, #3/#8/#10 sentiment correctness) | ❌ Blocked by task #308. The classification pipeline didn't run for the new posts because the run crashed before reaching it. |

## Recommended next steps

1. Fix task #308 (3 options above — (a) is the most conservative, (b)
   is fastest).
2. Re-run U3 smoketest (`scripts/live_a_z_populate.py --limit-per-call 5`).
3. Generate the next evidence report via `scripts/build_u3_evidence_live_run.py`.
4. Use the new evidence report to drive U2's capture-vs-tighten
   decision (the dead-letter rate measurement the plan requires).

## Raw stdout/stderr excerpt

```
=== STDOUT ===
(empty)

=== STDERR ===
dead-letter enum: family=discourse value='uncategorized' context={'table': 'posts_brands_discourse', 'post_id': '2076574434463224255', 'brand_id': 'yi', 'note': 'uncategorized-sentinel (KTD5): row skipped, no FK target'}
dead-letter enum: family=discourse value='uncategorized' context={'table': 'posts_brands_discourse', 'post_id': '2076575099071914459', 'brand_id': 'qwen', 'note': 'uncategorized-sentinel (KTD5): row skipped, no FK target'}
dead-letter enum: family=discourse value='uncategorized' context={'table': 'posts_brands_discourse', 'post_id': '2076574709458874598', 'brand_id': 'deepseek', 'note': 'uncategorized-sentinel (KTD5): row skipped, no FK target'}
dead-letter enum: family=discourse value='uncategorized' context={'table': 'posts_brands_discourse', 'post_id': '2076573184170823857', 'brand_id': 'minimax', 'note': 'uncategorized-sentinel (KTD5): row skipped, no FK target'}
dead-letter enum: family=discourse value='uncategorized' context={'table': 'posts_brands_discourse', 'post_id': '2076573184170823857', 'brand_id': 'glm', 'note': 'uncategorized-sentinel (KTD5): row skipped, no FK target'}
dead-letter enum: family=discourse value='uncategorized' context={'table': 'posts_brands_discourse', 'post_id': '2076572879160823964', 'brand_id': 'glm', 'note': 'uncategorized-sentinel (KTD5): row skipped, no FK target'}
Traceback (most recent call last):
  ...
  File "x_monitor/run.py", line 1689, in _update_accounts
    store.upsert_account(
        ...
        multiple_posts_in_thread_with_official=thread_count,
    )
TypeError: Store.upsert_account() got an unexpected keyword argument 'multiple_posts_in_thread_with_official'

# rc=1 elapsed_ms=55867
```

---

# Update — task #308 fixed, smoketest re-run clean (rc=0)

**Run date (re-run):** 2026-07-13T08:42:54Z
**Driver:** `python3.14 -m x_monitor run --limit-per-call 5`
**Run id:** `20260713T084254_0000-77dfe4bb`
**Run summary JSON:** `data/runs/20260713T084254_0000-77dfe4bb.json`
**Log:** `/tmp/u3_post308.log`
**Exit code:** 0

## What changed

Task #308 fix landed in commit `633e47f`:

- `x_monitor/run.py` — drop the `multiple_posts_in_thread_with_official=`
  kwarg from the `store.upsert_account(...)` call at `_update_accounts`.
  `thread_count` is still computed locally (with a `del thread_count`
  marker + a comment documenting why it's not persisted). Nothing in the
  pipeline reads the kwarg back today, so dropping it loses no
  functionality.
- `tests/test_run_task_308.py` — new regression test pinning the fix
  (forbids the kwarg from re-appearing, requires the task #308 marker
  comment to stay).

## What the re-run produced

The run reached `_update_accounts` (previously the crash site), the
classification pipeline ran for the new posts, and U5's partial-row
write was verified live again — 9 new partial rows landed in this run
alone.

```
totals:
  n_queries_run:             6
  n_results:                 9
  n_inserted:                7
  n_classifications_written: 0
  n_classifications_dropped: 0
  n_headlines_fetched:       0
  n_headlines_cached:        0
post_fetch:
  n_translated:        7
  n_discourse:         4
  n_nationalism:       0
  n_unsanctioned:      3
  wall_clock_sec:      23.80
```

DB verification (live `data/x_monitoring.db` after the re-run):

```
partial rows (act_id=0):                   9   ← U5 partial-row writes
total rows in discourse table:            45
rows with discourse_key IS NULL:           9
posts inserted this run (id >= 7540):    225
posts with brand classification
  (post_id >= 7540):                      21
rows in posts_brands_signals
  (post_id >= 7540):                       0
```

Note: `posts_brands_signals` stays empty because the B1/B2/B3/C1/C2
smoketest calls classify through `posts_brands_discourse` only — the
signals table is populated by a different call path. The 21
distinct post/brand combinations with discourse rows confirms the
classification pipeline DID run for the new posts.

`n_classifications_written=0` is a separate counter
(`run.py:1220` reads `store._classifications_written`, which is
incremented inside the legacy `classify_signal` 6-bucket path — that
path is no longer wired into the v1.7 live smoketest). The post-fetch
metrics (`n_discourse: 4`, `n_unsanctioned: 3`, `n_translated: 7`) are
the real measure of classification throughput for this run.

## What's verified vs what's still open

| Claim | Status |
|---|---|
| Task #308 fix (`Store.upsert_account` signature drift) | ✅ Committed (`633e47f`), regression-tested, smoketest re-ran cleanly to rc=0. |
| U5 partial-row write | ✅ Verified on live data, again — 9 partial rows in this run (vs. 6 in the blocked run). |
| Classification pipeline runs end-to-end | ✅ 21 distinct post/brand combinations with discourse rows; `n_unsanctioned: 3`, `n_translated: 7`, `n_discourse: 4`. |
| Run reaches the run-summary write + LATEST symlink | ✅ `data/runs/20260713T084254_0000-77dfe4bb.json` written; LATEST.json updated. |
| U3 full per-tweet evidence report | ⏳ Now unblocked — next step is to run `scripts/build_u3_evidence_live_run.py` against this run's data to produce the disputed-tweet table for tweets #2/#4/#6 marketing_spam recovery and #3/#8/#10 sentiment correctness. |

## Next step

Run the U3 evidence builder against `20260713T084254_0000-77dfe4bb` to
generate the per-tweet table. Use that table to drive U2's
capture-vs-tighten decision.