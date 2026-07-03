---
title: "Configurable search limits + small backlog"
type: feat
status: parked
date: 2026-07-02
origin: docs/plans/2026-07-02-183000-feat-configurable-search-limits-and-feature-backlog.md
---

# Configurable search limits + small backlog

## Goal Capsule

Surface the three hardcoded search caps that shape every `RunPipeline.execute`
cycle (`max_results`, `max_per_page`, `max_pages`) under a new `search:`
section in `config.yaml`, and address five small follow-on items surfaced during
the 2026-07-02 instrumentation + network-analysis conversation: `since=`
cursor wiring, `llama`/`yi` FK-violation noise, slow-API-day latency
observation, Call C narrow AND-filter review, and an HTTP-spend dashboard
panel.

## Problem Frame

Three search caps are baked into code today and operators cannot tune them
without a code edit:

- `max_results=50` at `x-monitoring/x_monitor/run.py:694`
- `SEARCH_MAX_PER_PAGE = 20` at `x-monitoring/x_monitor/apify.py:31`
- `_walk_search(max_pages=5)` default at `x-monitoring/x_monitor/apify.py:234`

Several similar knobs (`daily_ceiling`, `quote_tweets.official_call_budget`,
`quote_tweets.daily_call_budget`, `quote_tweets.max_pages`) are already exposed
via `config.yaml` and `x-monitoring/x_monitor/config.py:84-103` — search caps
are the inconsistent ones. Surfacing them is a config-exposure refactor with
defaults that match current behavior (no ship-path change). Alongside this
refactor, five small backlog items need attention: a designed-but-unwired
`since=` cursor, recurring FK-violation warnings from `llama`/`yi` brand IDs
that aren't in the `brands` table, unexplained server-side latency variance
needing observation, a Call C spec that returns zero posts due to an
over-strict AND filter, and a low-effort dashboard panel to make the existing
`http_log` spend data visually accessible.

## Requirements

- **R1.** Three search caps (`max_results`, `max_per_page`, `max_pages`) must
  be configurable via `config.yaml` under a new `search:` section, with
  defaults that match today's hardcoded values (50 / 20 / 5). Source:
  source doc "Feature: expose main-loop search caps in `config.yaml`",
  "Current state" + "Proposed config".
- **R2.** A new `SearchConfig` Pydantic model in
  `x-monitoring/x_monitor/config.py` must follow the existing
  `QuoteTweetConfig` pattern (BaseModel + `Field(default=…)` + `ge=1`
  bounds) and be wired into `Config` as a nested field with
  `default_factory`. Source: source doc "Code edits" step 1.
- **R3.** The main-loop search call site at `x-monitoring/x_monitor/run.py:694`
  must read `max_results` and `max_pages` from `self.config.search` instead
  of hardcoded literals. Source: source doc "Code edits" step 3.
- **R4.** `_walk_search` and `run_search` in
  `x-monitoring/x_monitor/apify.py` must accept `max_pages` from the caller
  (keeping the default at 5 for back-compat with tests/non-pipeline callers)
  and `max_per_page` must no longer be a module constant — it should be
  read from the caller's `SearchConfig` at the per-page `min(...)` site.
  Source: source doc "Code edits" step 2.
- **R5.** Omitting the `search:` block in `config.yaml` must produce
  identical behavior to today — confirmed via `phase_timings_sec` parity
  and unit tests for `apify._walk_search` continuing to pass with default
  limits. Source: source doc "Verification" + "Risks".
- **R6.** Per-query cursor resume: `since=` must be wired for the main-loop
  search. A new `call_state` (or `query_last_run`) table tracks
  `(brand_id, call_kind, bucket, query_id, last_completed_at)`. Each cycle
  reads the prior timestamp, computes
  `since = (last_completed_at - small_overlap).date().isoformat()`, and
  passes it to `apify.run_search`. Modeled after the existing
  `last_quote_fetched_at → sinceTime` wiring on the QT-capture side, but
  per-query rather than per-post. Source: source doc backlog item 1 +
  `docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md:36`
  (original `since:` rationale).
- **R7.** The recurring `insert_posts: dropping posts_brands row for
  brand_id='llama'/'yi' not in brands table` warnings (~30 per cycle) must
  be silenced by either removing `llama`/`yi` from `call_b_groups` in
  `config.yaml` (lines 41-44) or registering them in the `brands` table if
  they are intended scope. Today they sit in B1 but are absent from the DB,
  so body-keyword attribution to them is silently dropped at insert. Source:
  source doc backlog item 2.
- **R8.** Server-side latency variance observed on 2026-07-02 (2:05 run
  with 16 requests vs 21-min run the prior day with one Call B page taking
  240s) must be observed across more cycles with explicit instrumentation
  before any mitigation lands. This is an observation task, not a behavior
  change. Possible mitigations after observation: lower `max_results`
  (now configurable per R1), per-call timeout tuning. Source: source doc
  backlog item 3.
- **R9.** Call C spec at `config.yaml:101-117` (multi-brand spec C1:
  5 brands × 22 co-occurrence terms + `min_faves:0`) returns 0 tweets on
  the current state of X. The AND-filter must be relaxed either by
  dropping the co-occurrence paren (loosening to OR across the union) or
  by rebalancing the co-occurrence term list — chosen shape must surface
  ≥1 relevant post for at least one of the 5 covered brands in a probe
  run. Source: source doc backlog item 4.
- **R10.** A new "API spend this cycle" panel must be added to the
  dashboard, rendering aggregated metrics from the existing
  `summary["http_log"]` (request count, total duration, status code
  breakdown, endpoint breakdown). The panel must read from the same
  per-request log that `scripts/dump_http_log.py` already consumes — no
  new instrumentation. Source: source doc backlog item 5.

## Key Technical Decisions

- **Config exposure uses BaseModel mirroring `QuoteTweetConfig` pattern.**
  Search caps are tightly grouped semantically (all three govern a single
  TwitterAPI.io search call), so a dedicated `SearchConfig(BaseModel)` is
  the right shape — same pattern as `QuoteTweetConfig` already in place
  at `x-monitoring/x_monitor/config.py:84-103`. Bounds use `ge=1` to match
  the rest of the config.
- **Defaults match current behavior; this is a pure refactor.** No ship-path
  behavior change is intended. All test pass-criteria in U1 verify parity
  with the current numbers (50 / 20 / 5).
- **Keep `max_pages=5` default on `_walk_search`/`run_search`.** Tests and
  non-pipeline callers rely on the default; only the pipeline call site
  passes an explicit value. Removing the default would cascade tests.
- **`SEARCH_MAX_PER_PAGE` constant is removed, not kept as a fallback.**
  Reading from `SearchConfig` at the `min(...)` site in `_walk_search`
  keeps the per-page cap consistent with the operator's intent and avoids
  a hidden second source of truth.
- **`since=` cursor state lives in its own table, not in an existing
  table.** The cursor data shape `(brand_id, call_kind, bucket, query_id,
  last_completed_at)` is unique per query and doesn't map cleanly onto
  existing per-brand or per-post tables.
- **Call C AND-vs-OR choice is deferred to probe-run evidence, not chosen
  up-front.** The implementer must run the loosened spec against the live
  X state and pick whichever shape surfaces ≥1 relevant post without
  introducing obvious false positives — both shapes are valid candidates.
- **API-spend panel uses existing `http_log`, no new instrumentation.**
  The data is already persisted per cycle; the panel is a pure rendering
  layer on top of the same source that `scripts/dump_http_log.py`
  consumes.

## Implementation Units

### U1. Configurable search caps in `config.yaml`

**Goal:** Expose `max_results`, `max_per_page`, `max_pages` as a
`search:` block in `config.yaml` with defaults that match today's
hardcoded values (50 / 20 / 5). No ship-path behavior change.

**Requirements:** R1, R2, R3, R4, R5.

**Files:**
- `x-monitoring/x_monitor/config.py` (add `SearchConfig`, wire into `Config`)
- `x-monitoring/x_monitor/apify.py` (remove `SEARCH_MAX_PER_PAGE`,
  thread `max_pages` through `_walk_search`/`run_search`, accept
  `max_per_page` from caller)
- `x-monitoring/x_monitor/run.py` (call site at line 694 reads from
  `self.config.search`)
- `x-monitoring/config.yaml` (add `search:` block)
- `x-monitoring/tests/test_config.py` (new test cases for `SearchConfig`
  defaults + bounds)
- `x-monitoring/tests/test_apify_walk.py` (new test cases confirming
  `_walk_search` honors caller-supplied `max_pages` and `max_per_page`)

**Approach:**
- Add `SearchConfig` Pydantic BaseModel mirroring the `QuoteTweetConfig`
  pattern (`Field(default=…, ge=1)` for each of the three caps).
- Wire it as `search: SearchConfig = Field(default_factory=SearchConfig)`
  on the root `Config`.
- Remove the module constant `SEARCH_MAX_PER_PAGE` from `apify.py` and
  remove its import in `_walk_search`; replace the `min(...)` site with
  a caller-supplied value (passed in via the same wiring that already
  threads `max_pages`).
- Change `_walk_search(query, max_results, *, max_pages=5)` signature so
  `max_pages` is required from the caller (or keep the default 5 for
  back-compat — implementer's call, but document the choice).
- Change `run_search` to accept and pass through `max_pages` (and
  `max_per_page` if not already threaded).
- At `run.py:694`, replace the `max_results=50` literal with
  `s = self.config.search; apify.run_search(call.query_string,
  max_results=s.max_results, max_pages=s.max_pages, max_per_page=s.max_per_page)`.
- Add a `search:` block to `config.yaml` with `max_results: 50`,
  `max_per_page: 20`, `max_pages: 5`. Block is optional; omitting yields
  defaults.

**Test scenarios:**
- *Happy path — defaults:* Build `Config` from a YAML file with no
  `search:` block; assert `config.search.max_results == 50`,
  `config.search.max_per_page == 20`, `config.search.max_pages == 5`.
- *Happy path — explicit override:* Build `Config` from YAML with
  `search.max_results: 25`; assert the field reads 25 and other fields
  fall back to defaults.
- *Edge case — partial override:* YAML has only `search.max_pages: 3`;
  assert `max_results` and `max_per_page` are still 50 and 20.
- *Error paths — bounds violations:* YAML has `search.max_results: 0`
  (or any non-positive integer on any of the three caps); assert the
  Pydantic validator raises with a message naming the violating field.
- *Edge case — missing config.yaml entirely:* Loading must succeed
  with all three defaults (verifies `default_factory` wiring).
- *Integration — `_walk_search` honors `max_pages=2`:* Stub the HTTP
  client to return `has_next_page: true` indefinitely; call
  `_walk_search(query, max_results=200, max_pages=2)`; assert exactly 2
  HTTP calls were made and the result length is capped at
  `2 * max_per_page` regardless of the cursor claiming more pages.
- *Integration — `_walk_search` honors `max_per_page=5`:* Stub the HTTP
  client to echo `limit` back into the response payload; call
  `_walk_search(query, max_results=20, max_per_page=5, max_pages=10)`;
  assert every per-page request URL contained `limit=5`.
- *Integration — pipeline call site reads from config:* In a fake
  pipeline run, set `config.search.max_results=25` and `max_pages=3`;
  assert the call site in `run.py` invokes `apify.run_search` with
  exactly those values (capture via mock).
- *Integration — parity with current behavior when block omitted:* Run
  a full cycle with no `search:` entry; compare `phase_timings_sec`
  against a baseline run captured before the change; assert no drift.

### U2. Wire `since=` cursor for main-loop search

**Goal:** Persist `last_completed_at` per query and pass
`since = (last_completed_at - small_overlap).date().isoformat()` into
`apify.run_search` on the next cycle, eliminating redundant re-fetches
of TwitterAPI.io's "Latest" window.

**Requirements:** R6.

**Files:**
- `x-monitoring/x_monitor/migrations/004_call_state.sql` (new
  migration: `call_state` or `query_last_run` table)
- `x-monitoring/x_monitor/store.py` (add
  `get_last_completed_at(brand_id, call_kind, bucket, query_id)` and
  `set_last_completed_at(...)` helpers)
- `x-monitoring/x_monitor/run.py` (read prior timestamp at the start
  of each call, pass `since=` into `apify.run_search`, write
  `last_completed_at` after a successful cycle)
- `x-monitoring/x_monitor/apify.py` (verify `run_search` continues to
  accept `since=` and injects it as the `since:` operator — already
  exists per source doc, just ensure wiring at call site)
- `x-monitoring/tests/test_store.py` (new test cases for the
  upsert/select round-trip)
- `x-monitoring/tests/test_run_since.py` (new test cases confirming
  the call site threads `since=` correctly)

**Approach:**
- Add a migration that creates a table keyed by
  `(brand_id, call_kind, bucket, query_id)` with `last_completed_at`
  (timestamp with timezone). Index on the composite key.
- Add `Store.get_last_completed_at(...)` returning the timestamp or
  `None` if the row doesn't exist.
- Add `Store.set_last_completed_at(...)` performing an upsert
  (INSERT … ON CONFLICT … DO UPDATE).
- In `run.py`, before each `apify.run_search` call, read the prior
  timestamp. If present, compute
  `since_dt = last_completed_at - small_overlap` (e.g. 1 hour to absorb
  near-boundary posts) and pass `since=since_dt.date().isoformat()`.
- After a successful cycle (results fetched, no exception), write
  `last_completed_at = utc_now()` for the same key.
- If `since` is `None` (first-ever cycle for a query), no `since=`
  operator is injected — the existing `run_search` already handles
  this branch (`if since and "since:" not in query`).
- Document the `small_overlap` choice in a code comment with the
  reason (boundary post inclusion).

**Test scenarios:**
- *Happy path — first cycle (no prior state):* Call the pipeline with
  no row in `call_state` for a query; assert no `since=` parameter is
  passed to `apify.run_search` (verify via captured call args).
- *Happy path — second cycle (cursor present):* Pre-seed
  `call_state` with `last_completed_at = 2026-07-01T10:00:00Z`;
  run the pipeline; assert `apify.run_search` was called with
  `since="2026-07-01"` (after subtracting the small overlap).
- *Happy path — overlap subtracts correctly:* Pre-seed with
  `last_completed_at = 2026-07-01T01:30:00Z` and small_overlap=1h;
  assert `since` is `"2026-06-30"` (date is the date of
  `last_completed_at - 1h`, not of `last_completed_at` itself).
- *Edge case — explicit `since:` in query string:* Pre-seed with a
  prior timestamp; pipeline uses a query that already contains
  `since:2026-06-30`; assert the cursor-supplied `since=` is NOT
  injected (matches existing `run_search` guard).
- *Edge case — exception during cycle:* Force `apify.run_search` to
  raise mid-call; assert `last_completed_at` is NOT updated (only
  successful cycles advance the cursor).
- *Dedup behavior — same post on both cycles:* Verify that the
  `tweet_id` dedup logic in the insert path (existing) still drops
  re-fetched posts after the cursor is wired. Simulate by writing the
  same tweet to the DB, then re-running with a `since=` cursor that
  would re-include it; assert only one `posts` row exists.
- *Edge of `since` expiration:* TwitterAPI.io's `since:` accepts
  dates within a bounded historical window (verify exact bound in
  unit test against the real API in dry-run); assert the code
  clamps `since` to that bound if the stored `last_completed_at` is
  older. (If no bound applies, this test is omitted and the rationale
  is documented.)
- *Integration — full cycle after backfill:* Backfill a row with
  `last_completed_at = now`; run a full cycle; assert one
  `call_state` row exists per query executed and `last_completed_at`
  advances to ~now.

### U3. Resolve `llama` / `yi` FK-violation noise

**Goal:** Silence the recurring
`insert_posts: dropping posts_brands row for brand_id='llama'/'yi' not
in brands table` warnings by choosing one of two fix shapes and
documenting the choice.

**Requirements:** R7.

**Files:**
- `x-monitoring/config.yaml` (remove `llama` / `yi` from
  `call_b_groups` lines 41-44, OR)
- `x-monitoring/scripts/seed_brands_llama_yi.sql` (new one-shot script
  to register the brands if they're intended scope, OR)
- `x-monitoring/x_monitor/store.py` (no change expected; warnings are
  emitted from the insert path)
- `x-monitoring/tests/test_call_b_groups.py` (new test asserting
  either `llama`/`yi` are absent from `call_b_groups` OR they are
  present in the `brands` table, never the inconsistent state)

**Approach:**
- Inspect current intent: check `data/filters/llama.yaml`,
  `data/filters/yi.yaml` (if they exist), any docs in `docs/plans/`
  referencing these brands, and the `enabled_models` list at the top
  of `config.yaml`. If `llama`/`yi` appear in `enabled_models` or are
  documented as in-scope, fix shape = register them in the `brands`
  table via a one-shot SQL migration or seed script. If they are
  accidental leftovers from a stale `call_b_groups`, fix shape =
  remove them.
- Document the chosen shape (and the rejected alternative) in the
  PR description so future readers know which direction was taken.
- Whichever shape is chosen, verify the warnings stop by running a
  full cycle and grepping the run JSON for
  `dropping posts_brands row for brand_id`.

**Test scenarios:**
- *Happy path — chosen fix removes the warning:* Run a full cycle
  with the chosen fix in place; assert the warning count for
  `llama` and `yi` in the run JSON is 0.
- *Regression test — pre-fix state would warn:* Programmatically
  simulate the pre-fix state (e.g. re-add `llama` to `call_b_groups`
  while keeping the `brands` table as-is, run a single insert, then
  revert); assert the warning DOES appear. This locks in the test's
  ability to catch the regression class.
- *Happy path — chosen fix doesn't break other B1 brands:* Run a
  full cycle; assert no new warnings appear for brands that are
  correctly registered (e.g. `qwen`, `deepseek`, `mistral`).
- *Edge case — `enabled_models` consistency:* If `llama`/`yi` are
  removed from `call_b_groups`, assert they are also absent from
  `enabled_models` (or document an explicit reason for the
  divergence).
- *Error path — chosen fix is the wrong one (smoke test):* Briefly
  verify that selecting "add to brands" when they should have been
  removed does NOT silently lose data: confirm that posts with
  body-keyword matches for `llama`/`yi` are still routed
  appropriately.

### U4. Slow-API-day latency: observation task

**Goal:** Capture enough data across multiple cycles to confirm whether
the 2:05 vs 21-min variance observed on 2026-07-02 is server-side or
pipeline-side, and to characterize the distribution. **No behavior
change in this unit.**

**Requirements:** R8.

**Files:**
- `x-monitoring/x_monitor/run.py` (no code change; surface any
  per-call latency already captured in `summary["http_log"]` for
  follow-up analysis)
- `x-monitoring/scripts/dump_http_log.py` (extend, if needed, to
  summarize per-call latency distribution — mean, p50, p95, p99,
  outliers; only if not already present)
- `docs/notes/2026-07-02-latency-observation.md` (new observation
  log capturing runs and findings; lives outside `plans/` since it's
  not a feature plan)

**Approach:**
- Define an observation window (e.g. 7 cycles / 7 days).
- For each cycle, capture: total wall-clock, per-page latency from
  `summary["http_log"]`, request count, any
  `degraded`/`twitterapi_auth`/`twitterapi_rate_limit` sentinels.
- After the window, summarize: distribution of total run time,
  distribution of per-page latency, correlation between per-page
  latency and total run time, count of cycles that hit the
  `daily_ceiling` skip path.
- Only after the observation window closes, decide whether to act:
  lower `max_results` (now configurable per R1), introduce
  per-call timeout tuning, or leave alone.
- If `dump_http_log.py` doesn't already summarize the latency
  distribution in a useful form, add a `--latency-summary` flag that
  prints it. This is the only code change allowed in this unit, and
  it is opt-in (no behavior change to the pipeline).

**Test scenarios:**
- *Test expectation: none — this is observability, no behavior change
  yet.* Document the no-tests posture explicitly in the unit and
  re-evaluate after the observation window closes.
- *Smoke test — `--latency-summary` flag works:* Run
  `scripts/dump_http_log.py --latency-summary` against an existing
  run JSON with mixed-latency entries; assert it prints a
  distribution table and does not crash on edge cases (empty log,
  single request, all requests with same duration).
- *Smoke test — observation log captures the right shape:* Assert
  the observation log has one entry per cycle run during the window
  and each entry contains total wall-clock, p95 per-page latency, and
  request count.

### U5. Review Call C narrow AND-filter

**Goal:** Loosen the multi-brand Call C spec at `config.yaml:101-117`
so that it returns ≥1 relevant post per cycle instead of 0, by either
removing the co-occurrence paren (loosening the AND to OR across the
full union) or rebalancing the co-occurrence term list.

**Requirements:** R9.

**Files:**
- `x-monitoring/config.yaml` (lines 101-117 — the C1 spec)
- `x-monitoring/scripts/probe_call_c_spec.py` (new helper that
  performs a one-shot probe of a candidate spec against the live
  TwitterAPI.io and reports count + sample tweets; lives in
  `scripts/` to mirror the existing helper pattern)
- `x-monitoring/tests/test_call_c_specs.py` (new test cases that load
  the spec from config and assert it is well-formed, plus a probe
  harness test marked as live-skip-if-no-credentials)

**Approach:**
- Capture the current 0-tweet state as the baseline (run the probe
  against today's config, save the count + sample).
- Draft two candidate spec shapes: (a) drop the co-occurrence paren,
  so the entire brand-token union becomes a single OR group; (b)
  trim the co-occurrence list to a smaller, higher-signal subset.
- Run the probe against each candidate on the live API. Record counts
  and inspect the first 5 returned posts of each for relevance
  (body-keyword match to one of the 5 covered brands).
- Pick the candidate that (1) returns ≥1 post and (2) has the higher
  relevance ratio. If both qualify equally, prefer shape (b) since it
  preserves the AND filter's intent.
- Update `config.yaml` with the chosen shape; preserve the existing
  `notes:` block but append a date stamp + chosen-shape note.
- The `notes:` block format follows the existing convention of
  appending date-stamped changelog entries.

**Test scenarios:**
- *Happy path — chosen spec returns >0 posts:* Run the probe against
  the chosen spec; assert `n_results >= 1` and at least one of the
  first 5 results has a body-keyword match for one of the 5 brands
  (`xiaomi_mimo`, `moonshot_kimi`, `yi`, `upstage`, `llama`).
- *Edge case — both candidates pass; chosen one is documented:*
  The probe-run output must be preserved (commit alongside the
  config change) so future readers can see why one shape was picked.
- *Tradeoff documentation — AND vs OR tradeoff:* A test or doc
  assertion records the AND-vs-OR tradeoff in plain language (the
  AND-filter was originally chosen for signal density; loosening
  trades signal density for recall).
- *Edge case — min_faves unchanged:* `min_faves: 0` must remain in
  the spec regardless of the chosen shape (don't accidentally
  tighten it back up).
- *Regression — other Call C specs unaffected:* If there are
  multiple specs in `call_c_specs`, assert only the C1 spec was
  touched (others are byte-identical to their pre-change state).
- *Smoke — config loads:* After the change, load `config.yaml` via
  the existing config loader; assert no parse errors.

### U6. Surface API spend via `http_log` in the dashboard

**Goal:** Add a low-effort "API spend this cycle" panel to the
dashboard that renders aggregated metrics from the existing
`summary["http_log"]` field of the latest run JSON. No new
instrumentation.

**Requirements:** R10.

**Files:**
- `x-monitoring/x_monitor/dashboard.py` (add a new route that serves
  the panel fragment for htmx polling — or extend an existing
  endpoint to include the spend block)
- `x-monitoring/x_monitor/templates/api_spend_panel.html.j2` (new
  Jinja2 partial template for the panel)
- `x-monitoring/x_monitor/templates/_grid_cards.html.j2` (or
  equivalent — insert the new partial into the existing dashboard
  layout)
- `x-monitoring/x_monitor/templates/combined.html.j2` (insert the
  partial into the combined dashboard view)
- `x-monitoring/tests/test_dashboard_spend.py` (new test cases that
  hit the new route with a fixture run JSON and assert the rendered
  HTML contains the expected spend metrics)

**Approach:**
- Sketch the panel content from `scripts/dump_http_log.py`'s output
  shape: total request count, total duration, status code breakdown
  (e.g. 200 / 4xx / 5xx counts), endpoint breakdown (path → count +
  mean duration), and per-cycle cost estimate if credits-per-request
  data is in the log.
- Decide on the route: either extend the existing
  `latest_run`/`grid_cards` endpoint to include the spend block in
  its response, or add a dedicated `/api_spend` route that
  htmx-polled pages consume via `hx-get`. The implementer picks the
  smaller-blast-radius option.
- Render the panel as a Jinja2 partial that takes the aggregated
  metrics dict as input. Follow the existing dashboard styling
  conventions (vanilla CSS + htmx, inline SVG where needed).
- Insert the partial into the relevant layout templates. Skip
  detailed page if it doesn't make sense; insert into `combined` and
  `grid` at minimum.
- Aggregation logic should live in a small helper (e.g.
  `summarize_http_log(log: list[dict]) -> dict`) so the same
  aggregation can be reused by tests and by `dump_http_log.py` if
  desired.

**Test scenarios:**
- *Happy path — panel renders with sample log:* Hit the new route
  with a fixture run JSON containing a representative `http_log`
  (mixed paths, mixed statuses, mixed durations); assert the
  rendered HTML contains (a) total request count, (b) total
  duration, (c) at least one entry per distinct path in the fixture.
- *Happy path — empty log doesn't crash:* Fixture with empty
  `http_log`; assert the panel renders with zeros (no division by
  zero in mean calculations).
- *Edge case — single-request log:* Fixture with one entry; assert
  mean = that entry's duration (no off-by-one in aggregation).
- *Error path — missing `http_log` key:* Fixture with no
  `http_log` field; assert the panel renders a "no API calls this
  cycle" placeholder, not a 500.
- *Integration — htmx polling works:* Confirm the existing 30s
  poll cadence on the dashboard updates the panel without a full
  page reload (verify the `hx-get` attribute on the panel's
  container).
- *Integration — existing dashboard routes unaffected:* Hit the
  existing `/`, `/grid`, `/combined`, `/model/<id>` routes with a
  fixture; assert responses still include their existing content
  blocks (no accidental template breakage).
- *Regression — `dump_http_log.py` parity:* Confirm
  `scripts/dump_http_log.py` and the new dashboard helper produce
  consistent totals for the same fixture log (the aggregation
  logic should not diverge between the two paths).

## Verification Contract

- **U1:** Defaults match today's behavior (`max_results=50`,
  `max_per_page=20`, `max_pages=5`); overrides in `config.yaml`
  change the relevant cap; unit tests pass; `phase_timings_sec` shows
  no drift on a no-config-block cycle; `scripts/dump_http_log.py`
  confirms the per-page `limit` field honors the new `max_per_page`.
- **U2:** A second cycle for any given query passes
  `since=<yesterday's date>` (with small overlap subtracted) into
  `apify.run_search`; `call_state` table advances
  `last_completed_at` only on success; the existing tweet-id dedup
  path still drops re-fetched posts.
- **U3:** The recurring FK-violation warnings stop. If
  `llama`/`yi` are removed from `call_b_groups`, no warning for them
  appears. If they are added to the `brands` table, the insert path
  succeeds for posts that body-keyword match them.
- **U4:** An observation log captures N cycles; latency distribution
  summary is produced; no behavior change is made in this unit.
- **U5:** The chosen Call C spec returns ≥1 post in a probe run; at
  least one of the first 5 results is relevant to a covered brand;
  the tradeoff is documented in the `notes:` block.
- **U6:** A new "API spend this cycle" panel renders on the dashboard
  using only the existing `http_log` data; the panel updates via the
  existing 30s htmx poll; aggregation matches
  `scripts/dump_http_log.py` for the same input.

## Definition of Done

- [ ] U1: `SearchConfig` model lands in `x-monitoring/x_monitor/config.py`
      with the documented defaults and `ge=1` bounds; `_walk_search` and
      `run_search` accept `max_pages` and `max_per_page` from the caller;
      `SEARCH_MAX_PER_PAGE` is removed; `run.py:694` reads from
      `self.config.search`; `config.yaml` has a `search:` block with
      defaults; tests pass.
- [ ] U2: Migration creating `call_state` (or `query_last_run`) lands;
      `Store` has `get_last_completed_at` / `set_last_completed_at`;
      `run.py` reads prior timestamp, computes `since=`, threads it
      through, and writes the new timestamp on success; tests pass.
- [ ] U3: Either `llama`/`yi` are removed from `call_b_groups` or they
      are registered in the `brands` table; chosen fix is documented; the
      warnings stop; regression test exists.
- [ ] U4: Observation window runs for the configured N cycles;
      `docs/notes/2026-07-02-latency-observation.md` is populated with
      distribution data; any helper added to `dump_http_log.py` has a
      smoke test.
- [ ] U5: Chosen Call C spec shape lands in `config.yaml:101-117`;
      probe-run evidence is committed alongside; `notes:` block is
      updated with the chosen shape and date.
- [ ] U6: New dashboard route (or extended route) serves the spend
      panel; partial template is inserted into the relevant layout
      files; aggregation helper lives in a reusable location; tests
      pass; `dump_http_log.py` parity confirmed.
- [ ] All units: regression suite green; no new warnings emitted on a
      clean cycle; dashboard renders without 500s.

## Risks & Mitigations

- **R1 risk:** Reducing `max_results` cuts pages walked and may lose
  coverage for high-volume brands on burst days.
  *Mitigation:* Document the tradeoff in the dashboard's operational
  notes; preserve the 5-page safety cap so a runaway config can't
  drain credits; prefer reducing `max_pages` over `max_results` when
  tuning for cost.
- **R1 risk:** Increasing `max_pages` beyond 5 risks runaway pagination
  draining the credit budget.
  *Mitigation:* Keep the default at 5; document the credit ceiling
  math in the config comment (5 pages × 20 tweets = 100 tweets =
  ~$0.015 per search at TwitterAPI.io pricing).
- **R2 risk:** Cursor resume adds new failure modes (TwitterAPI.io's
  `since:` window bound, server-side gap if `last_completed_at` is
  older than the bound).
  *Mitigation:* Clamp `since` to the API-allowed maximum if the
  stored timestamp is older; fall back to a windowed fetch in that
  case; surface a sentinel in `summary["degraded"]` so operators can
  see when the cursor was clamped.
- **R2 risk:** A failed cycle leaving `last_completed_at` un-updated
  causes the next cycle to re-fetch a wide window — costly.
  *Mitigation:* Only update on success (covered in U2 test scenarios);
  log explicitly when a cycle fails so the wide re-fetch is visible.
- **R3 risk:** Choosing the wrong fix shape (removing vs registering)
  silently changes brand coverage.
  *Mitigation:* Document the intent evidence (presence in
  `enabled_models`, mentions in `docs/plans/`, filter YAMLs); smoke
  test confirms the chosen shape doesn't introduce a new warning for
  any brand.
- **U4 risk:** Acting on a single observation (2:05 vs 21 min) is
  overfitting.
  *Mitigation:* This unit is observation-only; mitigation decisions
  are deferred until the window closes.
- **U5 risk:** Loosening the AND filter to OR introduces false
  positives that were previously excluded.
  *Mitigation:* Probe the first 5 results of the chosen shape for
  relevance ratio before committing; preserve the second candidate
  in the commit history so rollback is one revert away; document the
  AND-vs-OR tradeoff in the spec's `notes:` block.
- **U6 risk:** Dashboard route proliferation makes the polling load
  worse.
  *Mitigation:* Prefer extending an existing endpoint over adding a
  new one; reuse the existing 30s htmx poll cadence; if a new route
  is necessary, document its refresh interval in the route
  registration.

## Scope Boundaries

### In Scope

- Configurable search caps (`max_results`, `max_per_page`,
  `max_pages`) via a new `search:` section in `config.yaml`
  (U1).
- `since=` cursor wiring for the main-loop search, persisted in a
  new `call_state` table (U2).
- Resolving `llama` / `yi` FK-violation warnings via removal from
  `call_b_groups` or registration in the `brands` table (U3).
- Observation-only capture of slow-API-day latency across multiple
  cycles, with no behavior change (U4).
- Review and relaxation of the Call C spec's narrow AND-filter
  (U5).
- Dashboard panel rendering the existing `http_log` data as "API
  spend this cycle" (U6).

### Deferred to Follow-Up Work

- All follow-up mitigations that U4's observation window may
  suggest (per-call timeout tuning, lowering `max_results` beyond
  the default, etc.) — deferred until the window closes.
- Threshold-based alerting when total per-day API spend exceeds an
  absolute number — mentioned in the source doc as a longer-term
  follow-up to U6; out of scope here.