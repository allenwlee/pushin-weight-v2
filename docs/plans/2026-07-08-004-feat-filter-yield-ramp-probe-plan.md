---
title: Per-call filter-yield ramp probe
date: 2026-07-08
type: feat
status: ready
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# Context

The post-fetch pipeline runs 5 advanced_search calls per 15-min cycle: Call A (list fan-in), Call B1/B2/B3 (the `call_b_groups` brand-wide splits), and Call C1 (the multi-brand co-occurrence spec). Each call has its own `query_string` and its own filter shape, but **we have no measured numbers for how many posts each one returns at the operator-set `max_results=50` cap, nor what the diminishing-returns curve looks like as we ramp the cap.**

This is a measurement gap. The pipeline's `daily_ceiling: 333` budget is set conservatively against a 9×5×50=2,250 theoretical upper bound from SC1 — but the actual yield per call is unknown. Without it, we can't tell whether:

- 50 is the right cap (we're already saturating the API), or we're leaving 4× recall on the table.
- B1/B2/B3 are balanced or skewed (B2 may be much louder than B3, suggesting the group split is wrong).
- Call C is over- or under-filtered at its current 23-term OR list.
- The TwitterAPI.io 512-char query cap is the binding constraint or just one of several.

**Outcome:** A new `scripts/probe_filter_yield.py` script that fires each of the 5 calls at max_results ∈ {50, 100, 150, 200} and reports per-call `n_results` + per-call kept-set size after the post-fetch keyword-detector regex. The output is a single CSV/JSON table that makes the yield-vs-cap curve visible per call. This becomes the canonical measurement artifact for any future `max_results` / `call_b_groups` / `call_c_specs` tuning PR.

The probe is **read-only** — it does not touch `data/`, does not write to the DB, and does not run the full pipeline. It mirrors the existing `scripts/probe_call_c_spec.py` pattern but extends to all 5 calls.

# Files to modify

| Path | Change |
|---|---|
| `x-monitoring/scripts/probe_filter_yield.py` | **NEW.** One-shot CLI: reads `config.yaml`, calls `plan_calls(...)`, then per call fires the live API at each `max_results` level, writes a CSV report. |
| `x-monitoring/tests/test_probe_filter_yield.py` | **NEW.** Mocks the live API; verifies the call set, the ramp sequence, the CSV output shape, and the dry-run path. |
| `docs/reference/api-rate-budget.md` (or similar) | **NEW.** Captures the probe output as the canonical reference for budget-vs-yield decisions. (Defer to a follow-up PR after the first probe run produces data.) |

# Implementation

## U1. The probe script (`scripts/probe_filter_yield.py`)

### U1a. CLI surface

```
scripts/probe_filter_yield.py [--max-results 50,100,150,200]
                               [--hard-max 1000]
                               [--dry-run]
                               [--output /tmp/filter_yield.csv]
                               [--budget-cap 1.50]
```

- `--max-results`: comma-separated ramp levels. Default `50,100,150,200`.
- **`--hard-max`: the absolute ceiling, applied per call.** Default **1000**. Any ramp level above this is **silently clamped** to `--hard-max` before being sent to the API. The justification:
  - TwitterAPI.io's per-call ceiling is 1,000 tweets for `advanced_search` (100/page × 10 pages). Anything above 1,000 returns no additional data — the API truncates or errors.
  - This defends against the "millions of posts" case the operator named: if someone removes the `max_results` param, omits the `--max-results` flag, or types `--max-results 1000000`, the script will internally clamp to 1,000 and log a warning ("clamped 1000000 → 1000 (hard-max)").
  - 1,000 is high enough that no realistic ramp test ever hits it (the existing default ramp tops out at 200), so the cap is invisible during normal use.
- `--dry-run`: skip live API calls; emit the planned calls with their `query_length` and the expected cost ceiling (sum of `max_results` levels × call count × $0.15/1k).
- `--output`: write path for the CSV report. Default `/tmp/filter_yield_<UTC-timestamp>.csv`.
- `--budget-cap`: refuse to run if the projected total cost (`sum(min(max_results_level, hard_max)) × n_calls × $0.15/1k`) exceeds this dollar figure. Default **$1.50**. The hard-max is the primary defense; the budget-cap is the secondary defense that catches bad combinations of ramp levels (e.g., `--max-results 500,1000,2000,5000`).
- Requires `TWITTERAPI_IO_KEY` (or `TWITTER_API_KEY`) in env. Without it, exits 2 with a clear message — same fail-soft shape as `probe_call_c_spec.py`.

### U1b. Call discovery

Reuse `x_monitor.query_plan.plan_calls` directly:

```
from x_monitor.config import load_config
from x_monitor.query_plan import plan_calls

cfg = load_config(Path("x-monitoring") / "config.yaml")
calls = plan_calls(
    data_dir=Path("x-monitoring") / "data",
    enabled_models=cfg.enabled_models,
    x_monitor_list_id=cfg.x_monitor_list_id,
    call_c_specs=cfg.call_c_specs,
    call_b_groups=cfg.call_b_groups,
)
```

Each `PlannedCall` already carries `call_id` (`A`, `B1`, `B2`, `B3`, `C1`), `query_string`, `query_length`. No new config needed.

### U1c. Live API firing

For each call × each ramp level, fire one `advanced_search` request with `max_results=<level>`. Per-call result:

- `n_results`: total tweets returned (TwitterAPI's `n_results` field in the response — already used by `probe_call_c_spec.py`).
- `n_kept_after_filter`: kept-set size after `x_monitor.attribution.detect_brand_mentions` runs the keyword-detector regex on each returned tweet's text. This is what the production pipeline would actually persist.
- `wall_clock_ms`: HTTP round-trip time.
- `cost_estimate_usd`: `n_results × $0.00015` (TwitterAPI.io's $0.15/1k published rate; cents not worth computing exactly).
- `sample_tweet_ids`: first 3 tweet IDs (for spot-checking relevance).

### U1d. Aggregation

The output CSV has one row per `(call_id, max_results)` combination:

| call_id | max_results | n_results | n_kept_after_filter | wall_clock_ms | cost_estimate_usd | t_newest | t_oldest | n_within_15min | sample_tweet_ids |
|---|---|---|---|---|---|---|---|---|---|
| A   | 50  | … | … | … | … | … | … | … | … |
| A   | 100 | … | … | … | … | … | … | … | … |
| A   | 150 | … | … | … | … | … | … | … | … |
| A   | 200 | … | … | … | … | … | … | … | … |
| B1  | 50  | … | … | … | … | … | … | … | … |
| B1  | 100 | … | … | … | … | … | … | … | … |
| …   | …   | … | … | … | … | … |
| C1  | 200 | … | … | … | … | … |

Per-call summary printed to stdout:

```
=== Per-call yield (max_results=200) ===
A   : 187/200  kept=164  cost=$0.028
B1  : 198/200  kept=121  cost=$0.030
B2  : 200/200  kept=89   cost=$0.030
B3  : 145/200  kept=34   cost=$0.022
C1  : 23/200   kept=18   cost=$0.003
```

### U1e. The "filters" the user is asking about

The user wrote "see how many posts all our filters will catch within a 15 min period." Concretely, that's three filter stages:

| Filter stage | What it does | Where to count |
|---|---|---|
| **API-side filter** | TwitterAPI.io applies `min_faves`, `lang:`, etc. before returning results | `n_results` from the API response |
| **Post-fetch keyword detector** | `x_monitor.attribution.detect_brand_mentions` regex matches brand tokens; non-matches are dropped before persistence | `n_kept_after_filter` in the probe output |
| **Unattributed-brand catch-all** | Posts with no monitored-brand attribution are bucketed into `_unattributed_all` (per the v13 plan's 2.1) | Optional `--with-unattributed` flag (deferred; out of scope for the first run) |

The first probe run reports stages 1 and 2 only. Stage 3 belongs to the v13 plan's taxonomy work and ships when that ships.

### U1e.1. Timestamps and "did we hit the cap?" detection

**Sort order is `Latest` (reverse-chronological) by default** — TwitterAPI.io's `queryType` parameter accepts only `"Latest"` or `"Top"` (default: `"Latest"`). This means when we hit the 1,000-tweet cap, we have the **newest 1,000** of whatever the API has, and the older tweets are invisible.

For each call × ramp level, the probe records three additional fields:

- `t_newest`: `created_at` of the first tweet in the response (the most recent).
- `t_oldest`: `created_at` of the last tweet in the response (the oldest, given reverse-chronological order).
- `n_within_15min`: count of returned tweets where `t_newest − created_at ≤ 15 min`.

**How to read these:**

| Pattern | Meaning | Action |
|---|---|---|
| `n_within_15min < max_results` AND `n_within_15min < n_results` | We hit the cap. There are more tweets in the 15-min window than the API returned. | The probe extrapolates: see U1e.2. |
| `n_within_15min == n_results` | We caught the whole 15-min window. No extrapolation needed. | The ramp max is sufficient. |
| `n_within_15min < n_results` AND `n_within_15min < max_results` | The 15-min window is sparse; the cap is unhit. | We're well-saturated; no extrapolation needed. |

The `n_within_15min` field is the single most important diagnostic in the output. A row where it's equal to `max_results` is **saturated** — bumping the cap further would yield more, but each additional 1000 costs $0.15.

### U1e.2. Linear-density extrapolation

When we hit the cap (`n_within_15min < n_results`), the probe computes a **linear extrapolation** of total volume in the 15-min window:

```
density = n_within_15min / (t_newest - oldest_t_within_15min)  # tweets per minute
extrapolated_total = density * 15  # tweets in the 15-min window
```

Where `oldest_t_within_15min` is the timestamp of the oldest returned tweet still inside the 15-min window.

**Caveats (must be in the operator's reading of the output):**

- **Linearity assumption.** Twitter activity is bursty, not linear. A burst in the last 5 minutes followed by silence would underestimate the prior 10 minutes. A sustained ramp would overestimate. The linear extrapolation is a **first-order estimate**, not a measurement.
- **Only the front of the stream is observed.** With `Latest` order, we get the newest 1,000. If the API has 5,000 in 15 min, the oldest 4,000 are invisible. The linear extrapolation uses the timestamps of the 1,000 we have, which biases toward the recent burst shape.
- **`Top` sort would invalidate this.** If someone changes `queryType` to `"Top"`, the order is by relevance, not time, and the extrapolation is meaningless. The probe hardcodes `queryType=Latest` to make the timestamp analysis valid.

The probe emits a fourth field for extrapolated cases:

- `extrapolated_n_in_15min`: the linear-extrapolation estimate. `null` if not extrapolating.
- `extrapolation_confidence`: `"high"` (saturation not hit), `"medium"` (extrapolation within 2× the observed density), `"low"` (extrapolation > 2× observed density — bursty regime, treat with skepticism).

This makes the CSV self-describing: any row with `extrapolation_confidence != "high"` is flagged for operator review.

### U1f. Hard-max clamping behavior

Two layers of defense, applied in this order:

1. **Per-level clamp**: each value in `--max-results` is clamped to `min(value, --hard-max)` before being sent to the API. If the clamp fires, log a warning to stderr: `probe_filter_yield: ramp level 5000 → 1000 (hard-max)`. This is the primary defense against the "millions of posts" case.

2. **Total budget cap**: after clamping, sum all clamped levels × n_calls × $0.15/1k. If this exceeds `--budget-cap`, exit 3 with a clear error message citing the projected cost. Default budget-cap is $1.50, which accommodates the default ramp (50, 100, 150, 200) at any number of calls up to 12 — well above our 5-call reality.

**Worst-case spend** (everything ramped to 1000, 5 calls, 4 ramp levels): 5 × (50 + 100 + 150 + 1000) × $0.15/1k = **$0.975 per probe run**, below the $1.50 budget-cap.

The hard-max is intentionally separate from the budget-cap because they catch different mistakes:
- Hard-max catches "someone typed a million" or "max_results param got removed."
- Budget-cap catches "someone added too many ramp levels or too many calls."

### U1g. Failure modes

- **API 429**: the probe retries up to 2× (matching `_call_signal_with_retry`'s pattern but with shorter backoff for a probe — 500ms, 1s). On final 429, the row's `n_results` is `null` and `cost_estimate_usd` is `null`. The script continues to the next call.
- **API 5xx**: same retry policy.
- **Network timeout**: 30s per request. Mark `n_results=null`.
- **Bad JSON**: log to stderr, mark `n_results=null`, continue.

Total run should not exceed ~3 min even at the worst-case 5 calls × 4 ramp levels × ~3 s/call (HTTP back-to-back). Well inside the 15-min cadence window the user named.

## U2. Tests (`tests/test_probe_filter_yield.py`)

| Test | Asserts |
|---|---|
| `test_probe_dry_run_lists_all_calls` | With `--dry-run` and a fake `config.yaml`, the script emits rows for `A`, `B1`, `B2`, `B3`, `C1` (5 calls) × 4 ramp levels = 20 rows. No HTTP calls. |
| `test_probe_ramp_levels_default_to_50_100_150_200` | Default `--max-results` parses to `[50, 100, 150, 200]`. |
| `test_probe_budget_cap_blocks_run` | `--budget-cap 0.01 --max-results 200,200,200,200` rejects with exit 3 (and a stderr line citing the projected cost). |
| `test_probe_hard_max_clamps_huge_ramp_level` | `--max-results 50,100,150,5000 --hard-max 1000` runs at clamped levels (50, 100, 150, 1000) and emits a stderr warning "clamped 5000 → 1000 (hard-max)". |
| `test_probe_hard_max_default_is_1000` | Default `--hard-max` is 1000. |
| `test_probe_hard_max_worst_case_cost_under_budget` | With 5 calls × 4 ramp levels all at `--hard-max 1000`, projected cost is ≤ $1.50 (the default budget-cap). |
| `test_probe_handles_missing_api_key` | No `TWITTERAPI_IO_KEY` env → exit 2 with a clear "no API key in env" message. |
| `test_probe_records_api_429_as_null` | Inject a 429 mock for one call; assert that row's `n_results` and `cost_estimate_usd` are `null` and the script continues to subsequent calls. |
| `test_probe_csv_schema_is_stable` | Output CSV header is exactly `call_id,max_results,n_results,n_kept_after_filter,wall_clock_ms,cost_estimate_usd,t_newest,t_oldest,n_within_15min,extrapolated_n_in_15min,extrapolation_confidence,sample_tweet_ids`. (Stable schema is the contract for downstream analysis.) |
| `test_probe_calls_plan_calls_with_config_groups` | Mock `plan_calls` and assert it's called with the config's `call_b_groups` and `call_c_specs` (not the legacy defaults). |
| `test_probe_records_t_newest_and_t_oldest` | When the API returns N tweets with timestamps, the row's `t_newest` is the max and `t_oldest` is the min (i.e., the response's natural order, which the probe records as-is). |
| `test_probe_n_within_15min_counts_correctly` | Given a response where 60 of 100 tweets fall in the last 15 minutes, the row's `n_within_15min == 60`. |
| `test_probe_extrapolation_fires_when_capped` | When `n_within_15min < n_results < max_results`, the row's `extrapolated_n_in_15min` is a finite number > `n_results` and `extrapolation_confidence` is `"medium"` or `"low"`. |
| `test_probe_extrapolation_skipped_when_not_capped` | When `n_within_15min == n_results`, the row's `extrapolated_n_in_15min` is `null` and `extrapolation_confidence` is `"high"`. |
| `test_probe_sends_query_type_latest` | The probe passes `queryType=Latest` to every API call, regardless of config. (Hardcoded to make the timestamp analysis valid.) |
| `test_probe_extrapolation_handles_no_timestamps` | If the API response is missing `created_at` for all tweets, the row's timestamp fields are `null`, `n_within_15min=0`, `extrapolated_n_in_15min=null`. |

The tests use a fake `config.yaml` fixture (4 brands, 2 B groups, 1 C spec) and a `FakeTwitterApiClient` that returns canned responses per call_id × max_results. No live network in CI.

## U3. Verification

### U3a. Unit

```bash
cd x-monitoring
python3 -m pytest tests/test_probe_filter_yield.py -v
```

All 7 tests pass.

### U3b. Dry-run against the real `config.yaml`

```bash
cd x-monitoring
python3 -m scripts.probe_filter_yield --dry-run
```

Confirms the script reads the live `config.yaml` correctly and emits rows for the actual 5 calls (A, B1, B2, B3, C1) at all 4 ramp levels. No HTTP.

### U3c. Live probe (operator-runs-by-hand)

```bash
cd x-monitoring
TWITTERAPI_IO_KEY=<redacted> \
  python3 -m scripts.probe_filter_yield \
    --max-results 50,100,150,200 \
    --output /tmp/filter_yield_$(date -u +%Y%m%dT%H%M%SZ).csv
```

Expected runtime: ~3 minutes. Expected total cost: **~$0.10–0.30** (5 calls × 4 levels × average ~50–200 results × $0.15/1k). The hard-max=1000 is the safety belt; the typical probe never approaches it.

### U3d. Output review

The operator pastes the CSV into the triaging doc (`x-monitoring/tests/classifier_tests/`) and reviews:

- **Saturation**: any call where `n_results == max_results` at the 200 level is being capped. If B1 saturates at 200 but B3 returns 50, B1's group needs to be split (or its brand list trimmed).
- **Filter hit-rate**: `(n_kept_after_filter / n_results)` per call. Calls under 30% are too permissive; calls over 90% are filtering too aggressively (might be missing recall).
- **Diminishing returns**: compare `n_kept_after_filter` at 50 vs 100 vs 200 per call. If a call doubles from 50→100 but only adds 10% from 100→200, the operator-set cap is fine; if the curve is still steep at 200, raise the cap.

### U3e. Decision artifact

After the first probe run, commit the resulting CSV to `x-monitoring/data/filter_yield_baseline.csv` (gitignored if it contains API keys — but `n_results` and `n_kept_after_filter` are not sensitive). This becomes the baseline that future tuning PRs diff against.

# Commit strategy

One commit:

```
feat(x-monitor): per-call filter-yield ramp probe

Adds scripts/probe_filter_yield.py — a one-shot CLI that fires each
of the 5 advanced_search calls (A, B1, B2, B3, C1) at max_results
levels {50, 100, 150, 200} and reports n_results, kept-set size
after the keyword-detector filter, wall-clock, and cost. The
output is a single CSV the operator can paste into the triaging
doc and use to decide whether the current cap (50) is leaving
recall on the table, or whether the call_b_groups split is
balanced.

- scripts/probe_filter_yield.py: reads config.yaml, calls
  plan_calls() to discover the call set, then per call × per
  ramp level fires one advanced_search request, aggregates to
  CSV. Includes a --dry-run mode that emits the planned call
  set without HTTP, and a --budget-cap safety belt.
- tests/test_probe_filter_yield.py: 7 tests covering dry-run,
  default ramp parsing, budget-cap rejection, missing-API-key
  handling, 429-as-null behavior, CSV schema stability, and
  plan_calls argument forwarding.
```

# Open Questions

1. **Should we run this in CI as a nightly characterization job?** Useful for detecting call-saturation drift over time, but it costs money (~$0.10/run × 365 = ~$36/year) and would need a TWITTERAPI_IO_KEY secret in CI. Defer; flag as a follow-up if the baseline CSV shows interesting variance week-over-week.

2. **Should the probe also run the LLM classification stage?** No — the user asked about "filters", which in our pipeline means the pre-persistence filters (API + keyword-detector), not the post-persistence LLM stage. If the operator wants to measure classifier yield vs. raw tweet volume, that's a separate probe and a separate plan.

3. **Does the existing `probe_call_c_spec.py` stay or get folded into the new probe?** Recommend keeping it as-is — it's the single-call tool operators reach for when iterating on a Call C spec. The new probe is the all-calls tool. Two scripts, two purposes.

4. **What is the right cap for `_kept_after_filter`?** Not answerable from this probe — that's an output of the post-fetch keyword-detector which is exercised here. If the numbers come back alarming (e.g., Call A keeps 100% of results, suggesting the keyword detector is a no-op), that's a separate bug to investigate.