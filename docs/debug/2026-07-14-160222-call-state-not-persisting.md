# Debug: `call_state` cursor not persisting across runs

**Date:** 2026-07-14 16:02 JST
**Reporter:** Allen Lee
**Investigator:** Claude Code (prior session)
**Status:** CLOSED — root cause was NOT call_state; it was TwitterAPI.io silently dropping the `sinceTime` URL parameter on `advanced_search`. Fix landed in commit a46020f (2026-07-14).

## Symptom

Across ~70 scheduled pipeline runs in the 18 hours before 15:30 JST 2026-07-14
(every 15 min via `com.fuchitalee.x-monitor.scheduled` launchd agent), the
`call_state` table in `data/x_monitoring.db` accumulated only **1 row total**
(`llama / B1 / brand_wide / Q5`, with `last_completed_at = 2026-07-13T03:45:28Z`,
27 hours stale).

For every other call in the production 6-call shape (A/B1/B2/B3/C1/C2), the
cursor read returned `None`, so the runtime issued calls with **no time filter**
(`sinceTime=None`, `since=None`) and TwitterAPI.io returned whatever posts it
had indexed. The 15:17 JST run (`20260714T061730_0000-f2d00e8a`) returned
96 posts with **99% dedup** (95/96 already in DB) — the worst case in the
24-hour window.

After I killed the 15:30 JST run at 0 progress, that run wrote 6 rows into
`call_state` anyway (probably from a near-immediate pre-flight pass before the
kill propagated), so the table now has 7 rows.

## What I've verified

1. **`call_state` table exists.** Schema correct, PK is
   `(brand_id, call_id, call_kind, bucket, query_id)`. 7 rows now present.
2. **Write code path is reachable.** `x_monitor/run.py:1304-1312` calls
   `store.set_last_completed_at(...)` after `store.insert_posts(...)` returns,
   inside the same `for call in plan:` loop. No `break`/`continue`/`return`
   between them.
3. **Write code works in isolation.** From a Python REPL, opening a fresh
   `Store(db_path)` and calling `set_last_completed_at('llama','B1','brand_wide',None,'Q5', now)`
   commits successfully and is visible from a second sqlite3 connection. The
   15:30 JST killed run also wrote 6 rows, so the path is functional.
4. **The `set_last_completed_at` symbol has been in `run.py` since
   `e741b64` (2026-07-02)** — confirmed via `git log -S`. So the code that
   *should* be writing every cycle has been there for 11 days. It was not
   removed by the U3 refactor (`26a768e`, 2026-07-10).
5. **`call.brand_id`, `call.call_id`, `call.call_kind`, `call.bucket`, and
   `synth_q.id` (the Q1/Q5 mapping) are all valid values that exist in the
   call plan.** The planner emits real A/B1/B2/B3/C1/C2 calls; `_planned_call_to_query`
   maps account→Q1 and brand_wide→Q5. So the write key matches the read key.
6. **No `call_state` log lines in `/tmp/x-monitor-pipeline.log` or
   `~/Library/Logs/x-monitor/scheduled-stderr.log` across 70+ runs.** The
   `log.warning("failed to advance call_state cursor ...")` path at
   `run.py:1319` has never fired.
7. **No `logging.basicConfig()` in `__main__.py` or `run.py`.** So warnings
   may be going to stderr, which the scheduled wrapper does redirect to
   `/tmp/x-monitor-pipeline.log` via `2>&1`. But pipeline log only contains
   Anthropic `classify_pragmatics_full` 401 errors and the recent pause
   message — nothing from `x_monitor.run`.

## What I have NOT verified

- Whether **a thrown exception between `store.insert_posts(...)` at line 1273
  and `store.set_last_completed_at(...)` at line 1305 is being swallowed by
  the per-call `try/except` somewhere upstream**, causing control flow to skip
  the cursor write without logging.
- Whether **`store.insert_posts` raises on the `classify_pragmatics_full` 401
  errors** we've been seeing for the entire 18-hour window. If it raises,
  the cursor write at line 1305 never executes (it's outside any try/except
  around insert_posts).
- Whether the **U3 refactor (`26a768e`, 2026-07-10)** inadvertently moved the
  cursor write inside a `try/except` that catches broader exceptions than
  intended, swallowing the failure silently.
- Whether there's an **import-time or module-level side effect** in `Store.__init__`
  that causes `_conn` to be in a state where writes are auto-rolled-back
  (e.g., implicit transaction begin that never commits).
- Whether `store.set_last_completed_at` raises on a UNIQUE constraint
  conflict that the ON CONFLICT clause doesn't catch (unlikely but possible
  if the schema drift changed between migration 025 and now).

## Hypothesis (ranked)

1. **`store.insert_posts` raises on the LLM 401s**, so cursor write at line
   1305 never runs. The exception is caught somewhere upstream (probably in
   `__main__.py`'s per-run handler) which logs it to a different stream than
   I've checked. Fix: wrap the cursor write in `try/finally` so it always
   fires on a successful *fetch*, even when post-fetch classification fails.
2. **An exception in `_attribute_call_items` (line 1202) or
   `filter_and_review` (line 1238)** propagates out of the `for call in plan:`
   loop, killing the cycle before any cursor write. The cycle would show
   `status=aborted` in the JSON summary, but the JSONs from the 18-hour
   window all show `status=degraded` (not aborted) with `n_inserted > 0` —
   so this hypothesis is contradicted by the JSON evidence. Lower confidence.
3. **The writes ARE happening but to a different DB file** (e.g., a staging
   DB that got rotated, or a path resolved relative to the wrong CWD).
   Test: check `Store.__init__`'s `db_path` argument and verify it matches
   `data/x_monitoring.db` for the scheduled runs.
4. **Migration drift** — a migration between 025 and now silently dropped the
   table or changed the PK. Already partially checked: `SELECT MAX(version)
   FROM _migrations` = 38, table exists with 7 rows, so this is unlikely.

## Reproduction recipe

The scheduled wrapper at `/Users/fuchitalee/development/minimax-marketing/x-monitoring/deploy/run-pipeline-with-notify.sh`
is now kill-switched via `/tmp/x-monitor-paused`. To reproduce:

1. `rm /tmp/x-monitor-paused`
2. `cd /Users/fuchitalee/development/minimax-marketing/x-monitoring`
3. `source ~/.env.secrets`
4. `.venv/bin/python -m x_monitor run --no-skip-under-budget > /tmp/repro.log 2>&1`
5. After completion, `sqlite3 data/x_monitoring.db "SELECT brand_id, call_id, last_completed_at FROM call_state ORDER BY updated_at DESC;"`

Expected: at least 6 new rows (A, B1-B3 for each unique brand in the cycle,
C1, C2 for each unique brand). Actual (prior to today): only 1 row from
27 hours ago.

## Anchor for the next investigator

`x_monitor/run.py:1304-1312` — the cursor write call site. The `try` block
at line 1304 has a `try/except Exception` that catches and logs at line
1313-1325, but the cursor write **runs unconditionally on the success path
of insert_posts**, not in a `finally` clause. If insert_posts raises
mid-cycle (e.g., due to the LLM 401s we've been observing), the cursor write
is skipped entirely.

The cheapest fix is to move `set_last_completed_at` into a `try/finally`
that wraps `insert_posts` — or to write the cursor *before* insert_posts
(eagerly, after the fetch succeeds but before classification). The eager
write is safer because it guarantees the cursor advances even when
classification fails, which is the correct behavior (we DID fetch through
this moment, even if no posts got inserted).

---

## Resolution (2026-07-14, post-investigation)

**Root cause was NOT in `call_state`, `run.py`, or `store.py`** — those
all behaved correctly. The cursor was being written on every cycle; it
just wasn't *honored* by TwitterAPI.io.

### What was actually wrong

Commit `37c5f08` (the "sub-day cursor precision via sinceTime query param"
fix from the cursor-precision investigation) moved `sinceTime` from one
location TwitterAPI.io ignores to another:

| Form | TwitterAPI.io behavior |
|---|---|
| `since:<YYYY-MM-DD>` inline operator | Honored — but date-only precision (resets to midnight UTC) |
| `sinceTime=<epoch>` URL parameter | **Silently dropped** — TwitterAPI.io advanced_search ignores unknown URL params |
| `since_time:<epoch>` inline operator | Honored — sub-day precision |

So every cycle was correctly emitting the cursor at the right epoch value,
TwitterAPI.io was correctly dropping it, and the API was returning the
entire recent X firehose — which then deduped at the DB level to ~5-15%
actual insertions.

### Direct API verification

| Test | n_results | posts older than cursor (1h ago) |
|---|---|---|
| `sinceTime` URL param (37c5f08 code) | 20 | **10** ← ignored |
| `since_time:` inline operator (docs form) | 11 | **0** ← honored |
| no filter (control) | 20 | **10** (identical to URL-param form) |

### Fix applied (commit a46020f)

`x_monitor/apify.py`:
- `run_search` injects ` since_time:<int(since_time)>` into the query
  string when `since_time` is provided (idempotent — leaves existing
  `since_time:` operator alone).
- `_walk_search` no longer writes `params["sinceTime"]` at all.

`tests/test_cursor_since_time.py`:
- Rewritten (9 tests) to pin the new behavior — inline operator MUST be
  in the query string, URL params dict MUST NOT carry `sinceTime` on
  advanced_search.

Post-fix live verification: 12 results returned, **0 older than cursor**.

### Counter-example: `get_quote_tweets` is fine

The `/twitter/tweet/quotes` endpoint officially documents `sinceTime` as
a URL parameter and honors it. Only `advanced_search` silently drops
unknown URL params. Do not "fix" `get_quote_tweets` to use inline
operators — it's working correctly as-is.

### Going forward

The pipeline is currently paused (kill switch at `/tmp/x-monitor-paused`).
When the operator is ready to resume:

```bash
rm /tmp/x-monitor-paused
launchctl load /Users/fuchitalee/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist
launchctl load /Users/fuchitalee/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
```

Expected first-cycle behavior: n_inserted should be much closer to n_results
(no more 85-99% dedup), and `call_state.last_completed_at` will advance
on every cycle (no more 27-hour staleness).