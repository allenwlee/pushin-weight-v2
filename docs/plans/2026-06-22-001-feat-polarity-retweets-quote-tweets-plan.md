---
title: "Polarity: Include Retweets and Quote-Tweets"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-22-130104-polarity-include-retweets-quote-tweets-requirements.md
deepened: 2026-06-22
---

# Polarity: Include Retweets and Quote-Tweets

## Overview

Make x-monitor's polarity score reflect amplification, not just original posts. Today each
post contributes **1** to its signal bucket (`treemap.py::POLARITY_SQL` sums `pb.weight`). This
plan adds: (1) a **free retweet fold** — weight each post's signal by `(1 + retweet_count)`;
(2) a **paid quote-tweet capture** — fetch QTs of brand posts and classify each QT's own
commentary as an independent vote, powered by a batched `quote_count` refresh so growth is
actually observable. QT capture runs in two regimes by post source: **adaptive/every-cycle** for
official/staff posts (batched refresh + threshold-gated fetch; velocity is emergent), and a
**daily pass** for non-official posts.

A pre-existing polarity-window bug (see Pre-existing Bug) is fixed as a side effect of the
schema change this plan already needs.

## Problem Frame

Polarity (`compute_polarity_from_db`) is an unweighted count of original posts; a launch post
with 7,000 RTs and 2,700 QTs counts as one data point. RTs add no new opinion (pure
amplification); QTs add the quoter's own reaction. The keyword search cannot surface QTs of a
brand post (X indexes a tweet's own text), so they must be fetched via
`GET /twitter/tweet/quotes`. See origin for the full problem frame and locked decisions.

## Requirements Trace

- **R1/R2.** RT fold: weight each post's signal by `(1 + retweet_count)`; no new fetch.
- **R3.** Capture QTs of brand posts; classify each QT's own commentary.
- **R4.** Two regimes: official/staff adaptive (every-cycle batched refresh, delta ≥ 5);
  non-official daily pass.
- **R5.** Fetch quantity = new-since-last, floored at 15.
- **R6.** Dedup via `sinceTime` + `tweet_id` idempotent insert.
- **R7.** Captured QTs use the **same** attribution/classification as originals (multi-brand →
  multiple `post_brands`/`post_brand_signals` rows, 1/N weighted); signal on commentary only.
- **R8.** 15-tweet per-call floor respected (batched refresh amortizes; threshold-gated fetch
  fills the floor or is skipped).
- **R9.** RTs and QTs participate in the same polarity metric ("each utterance = one vote").

## Scope Boundaries

- Likes and replies are out of scope.
- Pure-retweet content is never fetched; `retweet_count` metadata suffices.
- QT capture is one level deep (original → its QTs); no recursive quotes-of-quotes.
- The original-tweet keyword search (Call A/B) is unchanged.
- No per-utterance vote cap by default (each RT/QT = one vote). No `retweet_weight_cap` knob —
  raw counts ship; revisit only if telemetry shows a problem (see Risks).

## Pre-existing Bug (fixed as a side effect)

`POLARITY_SQL` filters `p.created_at >= ?` (and `< ?`) with an **ISO-8601** bound
(`compute_polarity_from_db` builds `current_start_iso = (now - timedelta(...)).isoformat()`),
but `posts.created_at` is stored in **Twitter format** (`Mon Jun 08 22:25:20 +0000 2026`).
Weekday-leading Twitter strings sort lexicographically after any `2…` ISO bound, so **every row
satisfies the lower bound and none satisfy the prior-window upper bound** → polarity is computed
over *all-time* posts as a single "current" window, not the intended current-vs-prior
rate-of-change. (Verified indirectly: a `created_at >= <ISO>` recency probe matched all 3,854
rows.) The `created_at_epoch` column this plan adds for the daily-pass recency window also lets
`POLARITY_SQL` filter on epoch, restoring correct windowing. Flagged for explicit verification
during implementation.

## Context & Research

### Relevant Code and Patterns

- `x-monitoring/x_monitor/treemap.py` — `POLARITY_SQL` (single SQL source of truth),
  `compute_polarity_signal_breakdown`, `compute_polarity_from_db`. RT fold = one-token change to
  `SUM(pb.weight)`; window fix = filter on `created_at_epoch` instead of `created_at`.
- `x-monitoring/x_monitor/apify.py` — `TwitterApiClient` (`_get`, `_walk_search`, `run_search`,
  `_normalize_tweet`). Two new methods: `get_quote_tweets` and a batched `get_tweets_by_ids`.
- `x-monitoring/x_monitor/run.py` — `RunPipeline.execute` (cycle: search →
  `_attribute_call_items` → filter → `store.insert_posts`); `_attribute_call_items` (the
  commentary+`quoted_text` attribution fold to mirror for QT ingest); `_staff_handles_map`
  (returns `{brand: [official+staff handles]}` — the official/staff tag, D6).
- `x-monitoring/x_monitor/store.py` — `insert_posts` (`INSERT OR IGNORE` on `posts`, fixed
  column list; `post_brands` `ON CONFLICT DO UPDATE`). Tracking + epoch need dedicated writes.
- `x-monitoring/x_monitor/migrations/` — forward-only `.sql`, auto-applied via
  `Store.apply_migrations()`, tracked in `_migrations`; current max is 005.

### Institutional Learnings

- `posts` is `INSERT OR IGNORE` with a **fixed INSERT column list**: re-insert never updates any
  column, and a column added by migration is only populated if `insert_posts` lists+binds it.
  Tracking state and `created_at_epoch` therefore need explicit write paths (UPDATE / insert-list
  extension), not just the migration.
- `post_brands` `ON CONFLICT DO UPDATE` only updates INSERT-listed columns (top-gun gotcha).
- TwitterAPI.io bills a **15-tweet minimum per call** (operator-confirmed). Mitigations:
  batched refresh (`GET /twitter/tweets?tweet_ids=…`) amortizes many posts per call; the fetch
  threshold (5) and daily cadence keep calls few.
- `/twitter/tweet/quotes` `has_next_page` can lie (true with empty pages) — stop on empty page.
- `created_at` is Twitter-format; windowing must use a parsed epoch, not string comparison.

### External References

- `GET /twitter/tweet/quotes` — 20/page, `sinceTime`/`untilTime` (unix s), `includeReplies`,
  cursor; `has_next_page` may lie. https://docs.twitterapi.io/api-reference/endpoint/get_tweet_quote
- `GET /twitter/tweets?tweet_ids=<csv>` — **batched** tweet lookup; returns `quoteCount`/
  `retweetCount` per ID. The affordable quote_count refresh. https://docs.twitterapi.io/api-reference/endpoint/get_tweet_by_ids

## Key Technical Decisions

- **Batched quote_count refresh** via `GET /twitter/tweets?tweet_ids=…` is the core enabler: one
  call refreshes all tracked posts' current `quoteCount`, so growth is observable without the
  search re-surfacing the post (closes the D1a "can't see current quote_count" gap for both
  regimes).
- **Official regime is adaptive/every-cycle**: each 15-min cycle batched-refreshes tracked
  officials; `delta ≥ qt_official_delta` (5) triggers a `sinceTime` QT fetch. Velocity is
  emergent — flooding posts fetch every cycle, quiet ones never — so no separate escalation
  machinery is needed.
- **RT fold is a one-token SQL change**: `SUM(pb.weight)` → `SUM(pb.weight * (1 + p.retweet_count))`.
- **QT tracking lives on `posts`** (`last_quote_count_seen`, `last_quote_fetched_at`) written by a
  dedicated UPDATE, transactional with ingest, because `posts` insert is `INSERT OR IGNORE`.
- **`created_at_epoch` column** (populated on insert + backfilled) serves the daily-pass recency
  window AND fixes the pre-existing polarity-window bug by switching `POLARITY_SQL` to epoch.
- **No `capture_source` column**: `insert_posts` can't populate it (fixed list) and no reader
  needs it; QT identity is derived from the fetch path + run-summary counts.
- **Official/staff tagging reuses `_staff_handles_map`** (D6); QT ingest reuses the original-post
  path (`_attribute_call_items` fold + `classify_signal` + `insert_posts`) so multi-brand 1/N
  weighting is inherited (R7).
- **Daily pass is date-gated inside `execute`** (one schedule), not a second launchd job.

## Open Questions

### Resolved During Planning

- **D1a/D1b (observing quote_count growth):** batched `get_tweets_by_ids` refresh each cycle
  (officials) / daily (non-officials) supplies the current count regardless of search recency or
  INSERT-OR-IGNORE staleness. No periodic single-tweet re-check needed; the batched call is it.
- **D2 (mega-flood cap):** `get_quote_tweets` takes `max_pages` (default ~5 = 100 QTs); first
  sighting of a post already at a large `quote_count` is capped and the rest recovered via
  backward `sinceTime` walks on later cycles (acknowledged: the pre-cap backlog needs an explicit
  catch-up walk, see Unit 2).
- **D3 (viral-domination):** ship **raw** `(1 + retweet_count)`; no cap knob. Document the
  compounding effect (RT-fold × hundreds of QT votes on a launch) as a known volatility; revisit
  only with telemetry.
- **D4 (QT storage):** captured QTs are rows in `posts`; no marker column; identity via the fetch
  path.
- **D5 (classification):** attribution matches commentary + `quoted_text` (parent text attached
  only when `quoted_status_id == parent tweet_id`); signal on commentary only; Haiku translation
  on commentary.

### Deferred to Implementation

- Exact `Store.update_quote_tracking` / epoch-write method names and backfill script shape.
- Final `qt_official_delta`, `max_pages`, and daily budget defaults after a live dry-run measures
  real QT volume and refresh cost.
- Batched-refresh ID-list chunking (cap IDs per `GET /twitter/tweets` call).
- Confirm `/twitter/tweets` returns `quoteCount` reliably for older/protected tweets.

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.*

```
ORIGINAL-TWEET CYCLE (unchanged): search -> _attribute_call_items -> insert_posts
        │
        ├── (official/staff authors) ── every cycle ──┐
        │                                             ▼
        │                              BATCHED REFRESH: get_tweets_by_ids(tracked IDs)
        │                                -> current quoteCount per post
        │                                             │
        │                                             ▼
        │                              delta = fresh_qc − last_quote_count_seen
        │                                             │
        │                              delta >= 5 ──> get_quote_tweets(sinceTime) -> ingest
        │                                             │
        ├── (non-official, daily, date-gated) ───────┤  (same batched refresh + threshold
        │   recent posts, created_at_epoch in window  │   fetch, just daily + recency-scoped)
        │                                             │
        └── (all posts) ──────────────── RT FOLD: POLARITY_SQL
                                         SUM(pb.weight * (1 + p.retweet_count))
                                         AND filter on created_at_epoch (window bug fix)

ingest (shared tail): attach parent text as quoted_text (only if quoted_status_id==parent);
  attribute_to_brands (commentary+quoted); classify_signal on commentary; insert_posts;
  Store.update_quote_tracking (same transaction)
```

## Implementation Units

- [ ] **Unit 1: Schema — QT tracking + `created_at_epoch` (migration 006)**

**Goal:** Add tracking columns for observable `quote_count` growth and a parseable epoch column
for recency windowing (which also fixes the polarity-window bug).

**Requirements:** R4, R5, R6 (infrastructure); enables the Pre-existing Bug fix.

**Dependencies:** None.

**Files:**
- Create: `x-monitoring/x_monitor/migrations/006_quote_capture_tracking.sql`
- Modify: `x-monitoring/x_monitor/store.py` (tracking UPDATE; epoch write/backfill), `x-monitoring/x_monitor/apify.py` (`_normalize_tweet` to emit epoch if not already derived)
- Test: `x-monitoring/tests/test_store.py`

**Approach:**
- `ALTER TABLE posts ADD COLUMN last_quote_count_seen INTEGER DEFAULT 0`,
  `last_quote_fetched_at TEXT`, `created_at_epoch INTEGER`. (No `capture_source`.)
- Add a `Store` method to UPDATE `last_quote_count_seen`/`last_quote_fetched_at` per `tweet_id`,
  run in the **same transaction** as the QT ingest batch (advance tracking only on ingest
  success → idempotent `sinceTime` retry on failure).
- Populate `created_at_epoch` on insert (extend `insert_posts`'s column list + bind) and
  backfill existing rows via a one-time Python script (Twitter-format parse — not pure SQL).
- Switch `POLARITY_SQL` to filter on `created_at_epoch` (Unit 6 detail) once populated.

**Patterns to follow:** `migrations/005_quoted_text.sql`; the migration-list assertion in `test_store.py`.

**Test scenarios:**
- Happy path: migration applies on a fresh DB; `applied_migrations()` → `[1..6]`.
- Edge case: re-running `apply_migrations` is idempotent.
- Integration: tracking UPDATE round-trips and is not clobbered by a later `insert_posts` of the
  same `tweet_id` (INSERT OR IGNORE); `created_at_epoch` is written on insert and survives re-insert.
- Integration: the backfill script converts Twitter-format `created_at` to epoch correctly.

**Verification:** Fresh DB reaches migration 6; columns present; tracking + epoch persist across
re-insert; existing rows backfilled to non-null epoch.

---

- [ ] **Unit 2: apify — `get_quote_tweets()` + batched `get_tweets_by_ids()`**

**Goal:** The two new API calls: paginated QT fetch, and the batched quote_count refresh.

**Requirements:** R3, R4, R5, R6, R8.

**Dependencies:** None (independent of schema).

**Files:**
- Modify: `x-monitoring/x_monitor/apify.py`
- Test: `x-monitoring/tests/test_apify.py`

**Approach:**
- `get_quote_tweets(tweet_id, since_time=None, max_pages=5, include_replies=False)` →
  `GET /twitter/tweet/quotes` with `{tweetId, sinceTime (unix s), includeReplies, cursor}`;
  paginate via `next_cursor`; **stop on empty page OR `has_next_page=false`**; honor `max_pages`;
  normalize via `_normalize_tweet`.
- `get_tweets_by_ids(tweet_ids)` → `GET /twitter/tweets?tweet_ids=<csv>`; chunk long ID lists;
  return `{id: quoteCount/retweetCount/...}`. This is the cheap batched refresh.
- For first-sighting catch-up of a post with a large backlog, a backward `sinceTime` walk helper
  (fetch oldest page first) to recover pre-cap history over successive calls.

**Patterns to follow:** `TwitterApiClient._get` + the cursor loop in `_walk_search`.

**Test scenarios:**
- Happy path: a single-page `/quotes` response yields normalized QTs.
- Edge case: `since_time` serialized as unix seconds; `includeReplies=false`.
- Edge case: `max_pages` cap stops pagination.
- Error path: an empty page stops iteration even when `has_next_page=true` (the documented lie).
- Integration: a mocked multi-page `/quotes` response returns the union and stops at the last page.
- Happy path: `get_tweets_by_ids` returns current `quoteCount` per ID; chunking splits long lists.

**Verification:** QT fetch returns all available QTs up to the cap, honors `since_time`, never
loops on the empty-`has_next_page`-lie; batched refresh returns current counts for many IDs.

---

- [ ] **Unit 3: QT ingest — attribute + classify + store**

**Goal:** Ingest captured QTs through the same attribution/classification path as original posts,
producing correct multi-brand `post_brands`/`post_brand_signals` rows.

**Requirements:** R3, R7.

**Dependencies:** Unit 1, Unit 2.

**Files:**
- Modify: `x-monitoring/x_monitor/run.py` (new ingest helper beside `_attribute_call_items`)
- Test: `x-monitoring/tests/test_quote_tweets.py` (extend)

**Approach:**
- For each QT: set `quoted_text` = the QT's nested `quoted_tweet.text`; **only if that is absent
  AND `quoted_status_id == parent tweet_id`**, fall back to the parent brand post's text (assert
  the invariant; otherwise classify on commentary alone). Build match body `commentary +
  quoted_text`; run `attribute_to_brands`; `classify_signal` on **commentary only**; `insert_posts`
  (writes `post_brands`/`post_brand_signals`, ON CONFLICT DO UPDATE). One signal per QT, applied
  to all N attributed brands at weight 1/N.

**Patterns to follow:** `_attribute_call_items` (`run.py:289`); the `insert_posts` path.

**Test scenarios:**
- Happy path: a single-brand QT → one `post_brands` + one `post_brand_signals` row, signal from commentary.
- Edge case: emoji-only commentary, keyword only in quoted (parent) text → attributes via fold.
- Integration (multi-brand): QT naming 2 brands (commentary+quoted) → 2 `post_brands` + 2
  `post_brand_signals`, weight ½ each; one signal applied to both.
- Edge case: signal from commentary only — QT quoting praise but commentary criticizes → `criticism`.
- Edge case: parent-text fallback fires only when `quoted_status_id == parent`; a QT whose nested
  quote points elsewhere does not get the parent fallback.
- Error path / idempotency: re-ingesting the same QT creates no duplicate rows.

**Verification:** Captured QTs yield correctly weighted multi-brand attribution; signal from
commentary; parent-fallback gated on the id invariant; idempotent.

---

- [ ] **Unit 4: Official/staff adaptive QT capture (every cycle)**

**Goal:** Each cycle, batched-refresh tracked officials' `quote_count`; threshold-gated QT fetch.

**Requirements:** R4, R5, R6, R8.

**Dependencies:** Units 1, 2, 3.

**Files:**
- Modify: `x-monitoring/x_monitor/run.py` (`execute`), `x-monitoring/x_monitor/config.py`
- Test: `x-monitoring/tests/test_run.py`

**Approach:**
- Maintain a tracked-official set (recent official/staff posts with `quote_count > 0` or recently
  fetched). Each cycle: `get_tweets_by_ids(tracked)` → fresh counts; for each, `delta = fresh −
  last_quote_count_seen`; if `delta ≥ config.qt_official_delta` (5): `get_quote_tweets(since_time
  = last_quote_fetched_at)` → ingest (Unit 3) → `update_quote_tracking` (same transaction).
  Velocity is emergent (no separate escalation logic).

**Patterns to follow:** `_staff_handles_map` (`run.py:202`) for official membership.

**Test scenarios:**
- Happy path: an official post with `delta ≥ 5` triggers fetch + ingest + tracking update.
- Edge case: `delta < 5` triggers nothing.
- Edge case: a non-official author is excluded from the tracked set.
- Integration: a batched refresh updates many officials in one call; flooding official hits the
  threshold every cycle (fetch every cycle), quiet official never does.
- Integration: across cycles the second fetch uses `sinceTime` from the first (no dupes); tracking
  advances only on ingest success (a failed ingest retries the same window idempotently).

**Verification:** Officials' ongoing QT growth is observed and captured regardless of search
recency; quiet officials cost only the cheap batched refresh; tracking is transactionally sound.

---

- [ ] **Unit 5: Non-official daily QT pass**

**Goal:** Once per day, batched-refresh recent non-official posts; fetch QTs for growth.

**Requirements:** R4, R5, R6, R8.

**Dependencies:** Units 1, 2, 3.

**Files:**
- Modify: `x-monitoring/x_monitor/run.py` (`execute`, date-gated branch), `x-monitoring/x_monitor/store.py`
  (recency query on `created_at_epoch`), `x-monitoring/x_monitor/config.py`
- Test: `x-monitoring/tests/test_run.py`

**Approach:**
- Date-gate via a `data/` marker (≤ once/day). Select non-official posts with `created_at_epoch`
  within `qt_daily_recency_days` (default 7). Batched-refresh their `quote_count`; for those with
  `delta > 0`, `get_quote_tweets(since_time=last_quote_fetched_at)` → ingest → update tracking.
  Stop at a **call-count** budget (`qt_daily_budget`), not a tweet count.

**Patterns to follow:** the per-model query/loop in `execute`; `Store` query helpers.

**Test scenarios:**
- Happy path: the daily branch refreshes + fetches for recent non-official quote-bearing posts.
- Edge case: a second `execute` the same day skips the daily branch (date gate).
- Edge case: official/staff posts and posts outside the recency window are excluded.
- Edge case: the **call-count** budget stops the pass mid-way and logs the partial run.
- Integration: `sinceTime` prevents duplicate QTs across daily passes; the poll set is non-empty
  because quote_count is refreshed (not read from the stale INSERT-OR-IGNORE row).

**Verification:** Non-official QTs captured over time at ~daily cadence with no per-cycle floor
waste; bounded by recency and a call-count budget.

---

- [ ] **Unit 6: RT fold + window fix in polarity**

**Goal:** Weight each post's contribution by `(1 + retweet_count)` and restore correct time
windowing via `created_at_epoch`.

**Requirements:** R1, R2, R9; fixes the Pre-existing Bug.

**Dependencies:** Unit 1 (`created_at_epoch` populated/backfilled).

**Files:**
- Modify: `x-monitoring/x_monitor/treemap.py` (`POLARITY_SQL`), `x-monitoring/x_monitor/dashboard.py`
  (bind epoch bounds instead of ISO strings, if the bound is built there)
- Test: `x-monitoring/tests/test_treemap.py`

**Approach:**
- `POLARITY_SQL`: `SUM(pb.weight)` → `SUM(pb.weight * (1 + p.retweet_count))`; and change the
  window predicates from `p.created_at >= ?` / `< ?` to `p.created_at_epoch >= ?` / `< ?`
  (integer epoch bounds). Update `compute_polarity_from_db`/`compute_polarity_signal_breakdown`
  to pass epoch bounds.

**Patterns to follow:** the existing `POLARITY_SQL` EXPLAIN/single-source-of-truth tests.

**Test scenarios:**
- Happy path: a post with `retweet_count=N`, weight `w` contributes `w*(1+N)` to its bucket.
- Edge case: `retweet_count=0` contributes `w*1` (backward compatible).
- Edge case: multi-brand per-brand weight preserved.
- Happy path (window fix): with `created_at_epoch` populated, a post older than the window is
  excluded; current vs prior windows split correctly (rate-of-change actually applies).
- Edge case (window fix): a DB with all posts in one window yields the prior-empty guard.
- Integration: `compute_polarity_from_db` over mixed RT counts and timestamps produces
  windowed, RT-amplified rates as intended; note the launch-case compounding (high RT + many QT
  votes) in a test comment.

**Verification:** Polarity reflects RT amplification and is correctly time-windowed; zero-RT
posts unchanged; the pre-existing all-time-window behavior is gone.

## System-Wide Impact

- **Interaction graph:** QT ingest invokes `attribute_to_brands` + `classify_signal` +
  `insert_posts` (same chain as originals) → `post_brands`/`post_brand_signals` → polarity
  (`treemap`) → dashboard. The batched refresh + RT fold/window change touch `POLARITY_SQL`,
  read by the dashboard and the dryrun verification path.
- **Error propagation:** `get_quote_tweets` / `get_tweets_by_ids` failures are logged and skip
  that post/batch; they do not abort the cycle.
- **State lifecycle risks:** tracking columns advance only on successful ingest (same
  transaction) → idempotent `sinceTime` retry. Because `posts` is `INSERT OR IGNORE`, tracking +
  epoch use dedicated writes (Unit 1).
- **API surface parity:** captured QTs use identical attribution/classification as originals
  (R7).
- **Integration coverage:** multi-brand QT attribution; adaptive official capture across cycles;
  daily-pass dedup; RT-fold + window-fix effect on the rate-of-change metric.
- **Unchanged invariants:** the original-tweet search (Call A/B), the polarity formula
  *structure* (rate-of-change), and 1/N multi-brand weighting are preserved. The window fix
  restores intended behavior rather than changing the contract.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `quote_count` growth unobservable via INSERT OR IGNORE / search recency | Batched `get_tweets_by_ids` refresh each cycle (official) / daily (non-official) (Units 2/4/5) |
| `has_next_page` lies / infinite pagination | Stop on empty page + `max_pages` cap (Unit 2) |
| First-sighting backlog cap loses history | Backward `sinceTime` catch-up walk (Unit 2); accept cap otherwise |
| Mega-flood + many QT votes compound polarity volatility (D3) | Ship raw per locked decision; document; revisit with telemetry — no speculative cap |
| 15-tweet floor waste | Batched refresh amortizes; official delta (5) + daily cadence keep calls few (R8) |
| Daily budget mis-sized | Budget in **calls** (Unit 5); tune after dry-run |
| `created_at_epoch` backfill incomplete → broken windowing | Backfill script + assert non-null epoch before switching `POLARITY_SQL` (Unit 1/6) |
| Window fix changes live polarity numbers | Expected (restores intended rate-of-change); note in Operational Notes |

## Documentation / Operational Notes

- New config knobs (all optional w/ defaults): `qt_official_delta`, `qt_daily_recency_days`,
  `qt_daily_budget` (calls), `qt_max_pages`, `qt_refresh_chunk_size`.
- Migration 006 auto-applies on the next cron cycle; the epoch backfill script runs once.
- Daily pass runs inside the existing 15-min launchd job, date-gated (no new schedule).
- Add `n_qt_fetched`, `n_refresh_calls`, and per-regime counts to the run summary for spend
  monitoring.
- **Expect a visible polarity change** when the window fix lands: brands will show actual
  rate-of-change between current/prior windows instead of all-time sentiment rate. Flag to the
  operator before deploy.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-22-130104-polarity-include-retweets-quote-tweets-requirements.md](docs/brainstorms/2026-06-22-130104-polarity-include-retweets-quote-tweets-requirements.md)
- Related code: `x-monitoring/x_monitor/treemap.py` (`POLARITY_SQL`, `compute_polarity_from_db`),
  `x-monitoring/x_monitor/apify.py` (`TwitterApiClient`, `_normalize_tweet`),
  `x-monitoring/x_monitor/run.py` (`execute`, `_attribute_call_items`, `_staff_handles_map`),
  `x-monitoring/x_monitor/store.py` (`insert_posts`)
- External docs: https://docs.twitterapi.io/api-reference/endpoint/get_tweet_quote ,
  https://docs.twitterapi.io/api-reference/endpoint/get_tweet_by_ids
