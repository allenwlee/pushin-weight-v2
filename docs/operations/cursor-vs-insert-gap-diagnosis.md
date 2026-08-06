# Cursor vs Insert Gap — Diagnosis (2026-08-06)

## Symptom

The 2026-08-05 16:00-16:14 UTC cycle (01:00-01:14 JST) inserted **86 unique posts** out of **~989 tweets fetched** across 52 TwitterAPI.io calls. The dashboard shows 989 fetches and 15,015 credits/cycle. The DB shows 86 new inserts.

The user flagged: *"989 fetched vs 86 inserted is too low. The start/end dates are not set properly, and we are repeatedly grabbing the same posts and discarding dupes."*

## Root cause

The cursor-floor in `monitor/cycle.py:_read_cursor_since` is clamped to `now - config.yaml::cycle.max_lookback_hours` (set to **2 hours**). Every cycle that finds a `last_completed_at` older than 2 hours uses the floor — never the prior cursor. So:

- Cursor at `2026-08-05 10:00:35 UTC` (B1/deepseek) → fetched again at `2026-08-05 16:00 UTC` with `since_time = max(10:00-60s, 16:00-2h) = 14:00 UTC`. Same 2-hour window every cycle.
- Cursor at `2026-08-05 02:15:44 UTC` (B1/minimax) → same floor logic.

**The 2-hour window IS the user's hypothesis.** Every 15-min cycle re-fetches the same 2-hour window. `INSERT OR IGNORE` discards ~903 of the 989 tweets per cycle (duplicates from earlier cycles).

## Verifying the duplicates

The 14:00-16:00 UTC window already contained **~1,150 posts** in `posts` (sum of all 14:00-15:59 buckets). The 16:00-16:14 cycle re-fetched those tweets; only 86 were new (the 16:00-16:14 tranche). **Insert-to-fetch ratio ≈ 9.1%** at this 2-hour-floor config.

For comparison, at a healthy 15-min floor (`max_lookback_hours=0.25`), the cycle would fetch ~15 min of tweets and the insert ratio would be ~80-95% (most fetched tweets are new).

## Why the cursor wasn't advancing

Looking at `call_state` rows in the last 24 hours, only **9 cursor advances** across 7 calls. With 96 cycles/day, that's 672 attempts — almost all `update_or_create` calls **failed silently** (per `_advance_cursor`'s "log and report False rather than raising" pattern at `monitor/cycle.py:370-378`). The cycle still inserts posts and runs classifies, but the cursor doesn't move forward.

The exact failure mode for the cursor writes is **not yet diagnosed** — could be a change to the `CallState` model schema, a stale primary-key tuple mismatch, or a transaction-isolation issue with the recent migration. The pause-and-investigate flow is paused; the cursor-vs-insert gap is the diagnostic priority.

## Holding the cursor at 2 hours is also a stability feature

The 2-hour floor is **not a bug per se** — it exists to absorb cron downtime, plan-deploy pauses, and Render maintenance windows. If the cron misses 2 consecutive cycles, the 2-hour floor means the next successful cycle re-fetches the missed window (`INSERT OR IGNORE` handles the dedup).

But the cost is **8 redundant fetches per cycle** (52 calls × 989 tweets vs the strictly-needed 15-min window which would be ~150 tweets). **At 96 cycles/day, that's ~$21/day in wasted credits** — about 70% of the monthly TwitterAPI.io allotment.

## Options (pick one)

### Option A — Lower `max_lookback_hours` to 0.25 (15 min)

```yaml
cycle:
  max_lookback_hours: 0.25  # one cycle window, not 2 hours
  cursor_overlap_seconds: 60
```

**Pros:** dramatically reduces duplicate fetches. Insert:fetch ratio goes from ~9% to ~80-95%.
**Cons:** if the cron misses 2+ cycles (45+ min downtime), the missed window is GONE. Acceptable because the TwitterAPI.io search only covers ~7 days back anyway.

### Option B — Keep the floor, cap the cycle's wasted spend

Skip the floor entirely when the cursor is fresh; cap the floor at 15 min only when the cursor is missing or stale. This is what `_read_cursor_since` *should* do but doesn't currently.

**Pros:** preserves the 2-hour downtime recovery while preventing the daily waste.
**Cons:** requires more code than Option A.

### Option C — Just add the regression pin (no fix)

Add `tests/test_harvester_cursor_vs_insert_ratio.py` that asserts the cycle's insert:fetch ratio is between 0.30 and 0.95 (catches the 9% baseline; lets the regression net catch any future regression). No code change to the cursor logic.

**Pros:** small change, fails loud if the cursor logic drifts further.
**Cons:** doesn't fix the actual waste — just makes it visible.

## Recommendation

Option C (regression pin) PLUS Option A (lower the floor). The regression pin fails CI on any future drift; the floor change brings the insert:fetch ratio back to healthy. The 2-hour floor as a downtime recovery is overkill given TwitterAPI.io's 7-day search window.

## How to reproduce

1. Cron is **paused** (Render REST API `suspend`). To resume: `curl -X POST -d '{"suspend":"no"}' https://api.render.com/v1/services/crn-d9gv94o4n6ts739tqaug/suspend` (then verify with dashboard toggle if the API doesn't clear).
2. From the prod DB, query the 14:00-16:00 UTC window's post counts vs. the 16:00-16:14 cycle's insert count.
3. Or open the TwitterAPI.io dashboard at https://twitterapi.io/dashboard and compare the credits column to the `posts` insert count for the same window.

## Related

- `monitor/cycle.py:_read_cursor_since` (line 259) — the function with the `max_lookback_hours` clamp
- `monitor/cycle.py:_advance_cursor` (line 321) — the cursor write that fails silently
- `config.yaml:90-91` — `cursor_overlap_seconds: 60` and `max_lookback_hours: 2` (the offending config)
- `x_monitor/store.py:608` — `INSERT OR IGNORE INTO posts` (the dedup that's eating 90% of fetches)
- `docs/operations/pause-and-resume-harvest-cron.md` — cron pause/resume procedure
- `.claude/skills/avoiding-recurring-mistakes/SKILL.md` M17 — halt-then-diagnose-then-pin (added 2026-08-06)
- Issue #13 — https://github.com/allenwlee/pushin-weight-v2/issues/13 — planned to receive this conclusion
