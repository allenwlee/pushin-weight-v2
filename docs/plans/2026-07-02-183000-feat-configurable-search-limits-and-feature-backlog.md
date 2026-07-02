---
title: "Configurable search limits + open-feature backlog"
type: feat
status: parked
date: 2026-07-02
origin: 2026-07-02 conversation (cap analysis + http_log instrumentation)
---

# Configurable search limits + open-feature backlog

### Feature: expose main-loop search caps in `config.yaml`

The three caps below shape every search call in `RunPipeline.execute`. They
are hardcoded today; the goal of this feature is to surface them in
`config.yaml` so operators can dial them without a code edit. Defaults
match current behavior — this is purely a config-exposure refactor, not a
behavior change on the ship path.

## Current state

| Cap | Where | Configurable? |
|---|---|---|
| `max_results=50` (search ceiling) | `run.py:694` hardcoded in call site | No |
| `SEARCH_MAX_PER_PAGE = 20` | `apify.py:31` module constant | No |
| `_walk_search(max_pages=5)` | `apify.py:234` default | No (search always uses default; QT capture reads `QuoteTweetConfig.max_pages`) |

For comparison, knobs that **are** already wired in config:

| Knob | Where | Default |
|---|---|---|
| `daily_ceiling` (per-day call ceiling, `apply_skip_order`) | `config.yaml:49` | `333` |
| `quote_tweets.official_call_budget` | `config.py:97` | `20` |
| `quote_tweets.daily_call_budget` | `config.py:102` | `50` |
| `quote_tweets.max_pages` (QT capture only) | `config.py:95` | `5` |

## Proposed config

```yaml
# x-monitor config.yaml — new section, defaults match current behavior
search:
  max_results: 50       # tweets per logical call (hardcoded in run.py:694)
  max_per_page: 20      # TwitterAPI.io per-page cap (apify.py:31)
  max_pages: 5          # pagination depth safety cap (apify.py:234)
```

## Code edits

1. **`x_monitor/config.py`** — add a `SearchConfig` Pydantic model
   following the `QuoteTweetConfig` pattern (BaseModel + `Field(default=…)`):

   ```python
   class SearchConfig(BaseModel):
       max_results: int = Field(default=50, ge=1)
       max_per_page: int = Field(default=20, ge=1)
       max_pages: int = Field(default=5, ge=1)
   ```

   Wire it into `Config` as a nested field:

   ```python
   search: SearchConfig = Field(default_factory=SearchConfig)
   ```

2. **`x_monitor/apify.py`**
   - Remove the module constant `SEARCH_MAX_PER_PAGE`, or accept it via
     `TwitterApiClient.__init__` (`max_per_page: int = 20`).
   - Change `_walk_search(query, max_results, *, max_pages=5)` so
     `max_pages` can be passed from the caller. Leave the default at `5`
     for back-compat in tests/non-pipeline callers.

3. **`x_monitor/run.py:694`** — replace
   `apify.run_search(call.query_string, max_results=50)` with:

   ```python
   s = self.config.search
   items = apify.run_search(
       call.query_string,
       max_results=s.max_results,
       max_pages=s.max_pages,
   )
   ```

   And inside `_walk_search`'s per-page calculation, use
   `min(s.max_per_page, …)` instead of `SEARCH_MAX_PER_PAGE`.

4. **`config.yaml`** — add the `search:` block shown above (optional;
   omitting it yields default behavior).

## Verification

- Run a cycle with no `search:` entry — `phase_timings_sec` should be
  unchanged from baseline (defaults match current values).
- Override `search.max_results: 25` and re-run — observe fewer pages
  walked per call (e.g. 2 pages × 20 = 40 instead of 3).
- Confirm `scripts/dump_http_log.py` shows the per-page `limit` field
  capped at the new `max_per_page`.
- Unit tests for `apify._walk_search` continue to pass with default
  limits.

## Risks

- Reducing `max_results` cuts pages from 3 to 2 and may lose coverage
  for high-volume brands on burst days. Operational note in the
  dashboard.
- Increasing `max_pages` beyond 5 risks runaway pagination draining
  credits; the 5 default is a sane cap.

---

### Open-feature backlog (catalog)

These items were surfaced during the 2026-07-02 instrumentation +
network-analysis conversation. Parked here as feature-request fodder —
not necessarily worked on immediately.

#### 1. Wire `since=` for the main-loop search

**Status:** designed but unimplemented. The `since` parameter exists
on `apify.run_search(...)` and the original 2026-06-07 plan declared
`since:YYYY-MM-DD` cursors the chosen strategy, but no caller passes
one today. Every cycle re-fetches TwitterAPI.io's "Latest" window
deduping by `tweet_id`.

**Shape:** a new `call_state` (or `query_last_run`) table:
`(brand_id, call_kind, bucket, query_id, last_completed_at)`; each
cycle reads the prior timestamp, computes
`since = (last_completed_at - small_overlap).date().isoformat()`,
passes it to `run_search`. Wired like `last_quote_fetched_at` →
`sinceTime` on the QT capture side, but per-query rather than
per-post.

**Why deferred:** cursor-resume adds failure modes (expiry) and the
current dedup-by-id is reliable; cost is bounded by `daily_ceiling`.

#### 2. Resolve `llama` / `yi` FK-violation noise

**Symptom:** every cycle emits ~30
`insert_posts: dropping posts_brands row for brand_id='llama' not in
brands table` warnings (similar for `yi`). They are in `call_b_groups`
(config.yaml:41-44) but not registered in the `brands` table.

**Fix shape:** either remove `llama`/`yi` from the B-groups or add
them to `brands` if they're intended scope. Currently they're in B1
but absent from the DB, so all body-keyword attribution to them is
silently dropped at insert.

#### 3. Slow-API-day latency: 2 min vs 21 min

**Observed:** on 2026-07-02 the same code path produced a 2:05 run
(16 req, fast TwitterAPI.io) and a 21-min run the day before (one
Call B page took 240s). Variance is server-side, not pipeline-side.
Possible mitigations: lower `max_results` (now configurable per item
1), per-call timeout tuning, observe more cycles before acting.

#### 4. Review Call C's narrow AND-filter

**Observed:** the multi-brand Call C spec (5 brands × 22
co-occurrence terms + `min_faves:0`) returned **0 tweets** in the
09:21 UTC run because the AND filter ruled out everything currently
on X. Either loosen the AND (drop the co-occurrence paren) or
rebalance the co-occurrence term list (config.yaml:101-117).

#### 5. Surface API spend via `http_log` in the dashboard

**Observed:** every cycle now persists `summary["http_log"]` (full
per-request log, see also `scripts/dump_http_log.py`).
Operators can already see per-request counts and durations after the
fact. A low-effort follow-up is to render a "API spend this cycle"
panel on the dashboard using the same data; a longer follow-up is
to alert when total per-day spend exceeds an absolute threshold.

---

### References

- `x_monitor/run.py:694` — main-loop search call site
- `x_monitor/apify.py:31, 234, 275-298` — `SEARCH_MAX_PER_PAGE`,
  `_walk_search` default, `run_search` signature + `since` handling
- `x_monitor/config.py:84-103` — `QuoteTweetConfig` pattern to mirror
  for `SearchConfig`
- `config.yaml:49` — `daily_ceiling` (existing analogous knob)
- `config.yaml:101-117` — `call_c_specs` (item 4 above)
- `docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md:36`
  — original `since:` design rationale
- `scripts/dump_http_log.py` — companion tool from the same session
