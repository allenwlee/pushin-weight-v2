# 2026-07-02 — Latency observation log (U4)

Plan: [docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md](../plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md)
Unit 4 of 6 (U4 — Slow-API-day latency observation).

## Background

On 2026-07-02 the main loop ran twice in the same day with dramatically
different total wall-clock durations:

| cycle              | total wall-clock | n_requests | notes                        |
| ------------------ | ---------------- | ---------- | ---------------------------- |
| morning            | 2 min 05 s       | 12         | clean run                    |
| afternoon          | 21 min 32 s      | 18         | 3 timeouts; one 5xx retry    |

The variance was first noted by the operator in the daily notes.
U4 is the **observation unit** — no behavior change yet. We want to
characterize the distribution across a multi-day window before
deciding what (if anything) to fix. The natural followup actions are
listed under "What we'll consider after the window closes."

## What this unit ships

- `scripts/dump_http_log.py --latency-summary` flag. Prints a
  per-endpoint mean / p50 / p95 / p99 / max latency distribution plus
  the overall distribution and top outliers. Opt-in; does not change
  default script behavior.
- Smoke tests for the new flag (empty log, single request,
  all-equal-sizes, mixed latency).
- This observation log.

## What this unit deliberately does NOT ship

- Any `max_results` / `max_pages` / `max_per_page` change. U1 made
  these configurable; U4 is the *observation* step. Acting on the
  observation is a separate unit (or follow-on tuning) once we know
  the shape.
- A per-call timeout knob. TwitterAPI.io's behavior under
  unexpected latency is documented in its own guide; we'd want
  contract terms before adding an aggressive timeout.
- Cache rewrites. The pipeline caches per-cycle in memory; no
  on-disk cache to rewrite.

## Observation window

- **Start:** 2026-07-02 (cycle that surfaced the variance).
- **End target:** 7 cycles / 7 days, whichever is later.
- **Captured per cycle:**
  - total wall-clock (started_at → finished_at)
  - per-page latency from `summary["http_log"]` (via the new
    `--latency-summary` flag)
  - request count and per-endpoint counts
  - any `degraded` / `twitterapi_auth` / `twitterapi_rate_limit`
    sentinels in `summary["degraded"]`
  - whether the cycle hit the `daily_ceiling` skip path

## Cycle-by-cycle captures

Format: one row per cycle. Empty rows are placeholders for future
operators.

| date          | run_id  | total wall-clock | n_req | p95 ms | degraded                   | daily_ceiling hit |
| ------------- | ------- | ---------------- | ----- | ------ | -------------------------- | ----------------- |
| 2026-07-02 a  | (TBD)   | 2 min 05 s       | 12    | (TBD)  | none                       | no                |
| 2026-07-02 b  | (TBD)   | 21 min 32 s      | 18    | (TBD)  | twitterapi_rate_limit (×3) | no                |
| (next 5/6)    |         |                  |       |        |                            |                   |

Procedure to fill a row, after each cycle:

```bash
scripts/dump_http_log.py --latency-summary --no-pretty > cycle.json
scripts/dump_http_log.py --latency-summary
# copy p95 from the "Overall" section into the table
```

## What we'll consider after the window closes

Once 7 cycles are in, summarize:

1. **Distribution shape.** Right-skewed outliers (server-side
   stall) vs broad right shift (genuine load). The first points to
   TwitterAPI.io; the second to our query shape / pagination
   strategy.
2. **Correlation.** Per-page latency vs total wall-clock — if strong,
   the slowdown is server-side. If weak, it's pipeline-side (likely
   filter_and_review or post-fetch attribution).
3. **Sentinels.** Any twitterapi_auth / twitterapi_rate_limit
   activations suggest credential or quota drift independent of
   latency.
4. **Decision triggers:**
   - p95 > 5 s sustained across the window AND no rate-limit
     sentinels → consider lowering `config.search.max_pages` /
     `max_per_page` via U1's knobs. Otherwise leave defaults.
   - Rate-limit sentinels observed → investigate quota and
     `daily_ceiling` separately, not via latency tuning.

The decision will be made in a follow-up unit, not in U4. U4
intentionally captures only the data; acting on it is downstream.