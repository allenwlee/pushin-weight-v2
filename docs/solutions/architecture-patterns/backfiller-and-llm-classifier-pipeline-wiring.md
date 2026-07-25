---
module: harvest
date: 2026-07-24
problem_type: architecture_pattern
component: service_object
severity: high
applies_when:
  - "Building a batched, resumable date-range processing tool that reuses an existing pipeline"
  - "Wiring an LLM-based classifier into an existing data processing workflow with guardrails"
  - "Designing Django management commands that need to process historical data in chunks"
symptoms:
  - "Need to backfill historical data through an existing pipeline without rewriting it"
  - "LLM classification is slow and expensive — needs rate limiting and cost guardrails"
  - "Multiple build/deploy issues surfaced (missing dependencies, stale i18n config, filesystem assumptions on Render)"
root_cause: incomplete_setup
resolution_type: tooling_addition
related_components:
  - background_job
  - tooling
tags:
  - backfiller
  - llm-classifier
  - harvest-cycle
  - cycle-runner
  - django-management-command
  - data-pipeline
  - render-deploy
---

# Backfiller Tool: Date-Bounded Historical Data Recovery

## Context

The v2 Django harvest cycle (`monitor/cycle.py`) runs on a 15-minute cron via Render's Celery beat scheduler. Each cycle plans a set of API calls, fetches recent tweets, attributes them to brands, and persists results via the Django ORM. This steady-state harvesting works well for ongoing coverage, but it cannot reach backward into the past: the regular cycle does not accept time-range parameters, and there was no mechanism to fill historical gaps without manual scripting.

Two concrete gaps exposed this need:

1. **Deployment downtime gaps.** During the Jul 22-23 Render deployment cutover, the v2 harvest was not running. When it came back online, roughly 1,600+ posts from that window were missing. Running `manage.py run_cycle` would only fetch posts from "now" — it could not backfill the missed interval.

2. **LLM classification relay.** The v2 cycle's `_run_post_fetch` method was stubbed out — posts were persisted without `text_en`, `text_zh_cn`, `PostBrandSignal`, or `PostBrandDiscourse` rows. Without real classification, the v2 stack had no labeled data for downstream analytics.

The solution needed two capabilities: a way to bound harvest calls to arbitrary time windows (the backfiller), and a way to run the full translation + classification pipeline on fetched posts (the LLM classifier wiring). Critically, both had to coexist with the regular 15-minute harvest without blocking it.

## Guidance

### Architecture: The Backfiller as a Thin Orchestration Layer

The backfiller (`monitor/management/commands/backfill.py`) is a Django management command that reuses the entire `CycleRunner` pipeline: plan calls, fetch tweets, attribute to brands, persist via ORM, translate, and classify. It is not a separate code path — it is an orchestration wrapper (~300 lines) that configures the same `CycleRunner` with time-bound parameters and then drives it in batched, resumable fashion.

The pipeline reuse is enabled by two design decisions:

**`plan_calls_for_cycle()` — a shared entry point.** Extracted from `CycleRunner._plan_calls()` to module-level, this function reads `X_MONITOR_LIST_ID`, brand filter, primary keywords, and `x_query_specs` from Django settings. Both `CycleRunner` and the backfill command call it, ensuring consistent call planning regardless of entry point.

**`_backfill_call_ids` — single-call execution mode.** The `CycleRunner.__init__` accepts an optional `_backfill_call_ids` parameter. When set, `CycleRunner.run()` narrows the full call plan to only the matching call IDs. This allows the backfiller to execute one call at a time while still using the standard cycle machinery.

### Time Window Configuration

The backfiller accepts `--since` and `--until` with second-level precision:

```
python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00
```

These are parsed from ISO format (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`), converted to epoch seconds, and threaded through the settings pipeline:

```
backfill._parse_iso()
  → settings.X_MONITOR_CYCLE_SINCE_TIME (epoch int)
  → settings.X_MONITOR_CYCLE_UNTIL_TIME (epoch int)
  → CycleRunner._fetch_tweets() reads from settings
  → TwitterApiClient.run_search(since_time=, until_time=)
  → apify.py injects `since_time:<epoch> until_time:<epoch>` into query strings
```

The `until_time` parameter is a new addition to the pipeline — `apify.py` already supported `since_time` for the regular harvest's sliding window; the backfiller added the matching upper bound so search results stay strictly within the target interval.

### Dynamic Resource Estimation

The backfiller computes `max_results` and `max_pages` from the window size rather than requiring the operator to guess. It uses a 2,350 posts/day baseline (measured from the Jul 21 steady-state harvest) with a 2x safety margin:

```python
def _compute_params(since_epoch, until_epoch, safety_margin):
    gap_hours = max((until_epoch - since_epoch) / 3600.0, 1.0)
    est_total = int(_EST_DAILY_POSTS * (gap_hours / 24))
    est_per_call = max(est_total // _EST_CALLS_PER_CYCLE, 50)

    max_results = int(min(est_per_call * safety_margin, _MAX_RESULTS_CEILING))
    max_results = max(max_results, 100)
    max_pages = min(
        max(int((max_results / _TWEETS_PER_PAGE) * safety_margin) + 1, 5),
        _MAX_PAGES_CEILING,
    )
    return max_results, max_pages, est_total
```

Ceilings (`_MAX_RESULTS_CEILING=1000`, `_MAX_PAGES_CEILING=100`) prevent runaway API consumption on large windows. Operators can override the computed values with `--max-results` and `--max-pages`.

### Batched Execution with Cooperative Scheduling

The backfiller does not attempt to process an entire window in one shot. Instead, it processes `--batch-size` calls per invocation (default: 3), pauses between calls (`--pause` seconds, default: 5), writes progress to a state file, and exits. This is deliberate for coexistence with the regular harvest:

- Each batch creates a fresh `CycleRunner` instance and runs `runner.run()`.
- Between batches, the regular 15-minute harvest cron can grab the pipeline lock or simply interleave its calls.
- The `--pause` flag creates breathing room between calls within a batch.

This is not a producer-consumer queue — it is cooperative yielding: the backfiller does a small chunk of work and releases control back to the system.

### State Files for Resumability

Progress is tracked in `data/backfill/<since_epoch>-<until_epoch>.json`:

```json
{
  "since_epoch": 1753142400,
  "until_epoch": 1753268400,
  "since_label": "2026-07-22T05:00",
  "until_label": "2026-07-23T21:00",
  "gap_hours": 35.0,
  "est_total_posts": 3429,
  "max_results": 1000,
  "max_pages": 100,
  "calls_total": 6,
  "calls_completed_ids": ["call_a_01", "call_a_02"],
  "calls_completed": 2,
  "total_inserted": 823,
  "runs": [],
  "finished": false,
  "calls_remaining": ["call_a_03", "call_a_04", "call_b_01", "call_b_02"]
}
```

On subsequent runs with the same `--since`/`--until`, the backfiller loads the state file, skips completed calls, and picks up where it left off. `--status` prints the current progress; `--reset` discards the state and starts fresh.

**Render limitation:** Render jobs do not share a filesystem. State files persist only within a single job's lifetime. This means a backfill must complete in one Render job invocation — run it with a large enough `--batch-size` (or default to all calls) when executing on Render, and monitor until completion.

### LLM Classifier Wiring

The `_run_post_fetch` method in `CycleRunner` was rewired from a stub to real v1 function calls. The pipeline is:

1. **Build Anthropic client** via `x_monitor.reattribute.build_anthropic_client_from_env()` — reads `DEEPSEEK_API_KEY` and `X_MONITOR_CLASSIFIER_BASE_URL` from environment.

2. **Convert Django `Brand` models to v1 `BrandRow` namedtuples.** The v1 classifier expects `BrandRow(brand_id, display_name, accent_color, is_sentinel)`. The Django `Brand.nickname` field maps to `BrandRow.brand_id`.

3. **Stage 1 — Translate:** `x_monitor.translator.translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)` produces `text_en`, `text_zh_cn`, and `lang_detected` for each post. Results are persisted to the `Post` model's `text_en`, `text_zh_cn`, and `lang_detected` fields via `update_or_create`.

4. **Stage 2 — Classify:** `x_monitor.attribution.classify_batch_pragmatics_full(tweets, brand_registry, client)` produces per-brand `(post_type, sentiment)` decompositions and optional `discourse_role` / `china_nationalism` / `us_nationalism` flags. Results are persisted to `PostBrandSignal` and `PostBrandDiscourse` tables.

**Guardrails** prevent runaway API spend:

- **Pause between batches:** `X_MONITOR_LLM_PAUSE_SECONDS` (default 1s) — inserted after every classification batch boundary.
- **Hard cap:** `_max_llm_calls` (set via `--max-llm-calls` on the backfill command) — classification stops when the counter is reached. Remaining posts are persisted without labels and will be picked up by the next invocation.
- **Batch size:** `X_MONITOR_CLASSIFY_BATCH_SIZE` (default 20) controls how many posts go into each LLM call.
- **Sequential processing:** Classification runs inline within `_run_post_fetch` — no async, no concurrent workers. This is deliberate: the LLM API has rate limits, and concurrent calls would amplify failure modes.

### Build/Deploy Gotchas Encountered

Several environment-specific issues were discovered and fixed during this build:

1. **`LANGUAGE_CODE="zh-cn"` breaks Django startup.** After an i18n revert, the settings file retained `LANGUAGE_CODE="zh-cn"` but no compiled `.mo` file existed. Django's startup checks failed. Fix: revert to `LANGUAGE_CODE="en"` until i18n is re-enabled.

2. **`compilemessages` requires `gettext` on the host.** Render's Python runtime does not include GNU gettext. Running `python manage.py compilemessages` fails. Fix: skip compilemessages in build.sh; either commit pre-compiled `.mo` files or defer i18n.

3. **Render jobs do not share a filesystem.** State files written by one Render job are invisible to another. Backfill jobs must complete within a single invocation.

4. **`plan_calls()` does not accept `limit_per_call` as a keyword argument.** The backfill initially passed `limit_per_call` to the shared `plan_calls()` function, but the function signature only accepts `list_id`, `x_query_specs`, and `primary_keywords`. Fix: pass `max_results`/`max_pages` through Django settings instead, where `CycleRunner._fetch_tweets()` reads them.

## Why This Matters

The alternative to a reusable orchestration layer would have been duplicating the fetch-attribute-persist pipeline inside the management command. That would create three problems:

1. **Divergent behavior.** Two copies of the harvest logic would inevitably drift — a bug fix in `CycleRunner` would not propagate to the backfill command, and vice versa.

2. **Configuration leakage.** The backfill would need its own copies of `plan_calls`, `_fetch_tweets`, `_attribute_items`, and `_persist_items`, each with duplicate parameter plumbing.

3. **Testing surface explosion.** Every change to the pipeline would need to be verified against two entry points with different state management.

By extracting `plan_calls_for_cycle()` to module level and adding the `_backfill_call_ids` single-call mode to `CycleRunner`, the backfiller becomes a pure orchestration concern: it sets up time-bounded settings, drives `CycleRunner` in batches, and manages state files. The pipeline itself remains a single source of truth in `CycleRunner.run()`.

The cooperative batching design (process `--batch-size` calls, write state, exit) is also important. Alternatives considered:

- **Monolithic single-run:** Process the entire window in one invocation. Simple but risky — if the job fails at call 5 of 6, all progress is lost (no state file without explicit checkpointing), and the regular harvest is blocked for the duration.

- **Background queue per call:** Enqueue each call as a Celery task. More resilient but adds infrastructure complexity (Celery routing, task deduplication, result backend) for what is fundamentally a one-off recovery operation.

The cooperative batching approach hits the middle ground: it checkpoints progress so failure is cheap, it yields between batches so the regular harvest is not starved, and it requires no additional infrastructure beyond the Django management command framework.

## When to Apply

**Use the backfiller when:**

- A deployment or outage gap needs filling (e.g., hours or days of missed harvest).
- You need bounded historical data for a specific analysis window.
- A migration or schema change requires re-fetching and re-processing posts from a past interval.
- You are testing LLM classification changes and want to re-classify a known time range.

**Use the regular harvest (`manage.py run_cycle` or the Celery beat scheduler) when:**

- Ongoing, forward-looking coverage is the goal.
- The 15-minute sliding window is sufficient.
- You want automated, hands-off operation.

**Do NOT use the backfiller for:**

- Windows larger than a few days without adjusting `--max-results` and `--max-pages`. The API will truncate results, and you may miss posts even though the backfiller reports completion.
- Replacing the regular harvest. The backfiller is a recovery/analysis tool, not a production scheduler.
- Continuous re-backfilling of the same window. The state file prevents reprocessing completed calls, but posts already persisted via `update_or_create` will be updated in-place — repeated runs won't create duplicates, but they will re-fetch and re-persist the same data, wasting API credits.

## Examples

### Fill a Deployment Gap

```bash
# Plan first (dry-run)
python manage.py backfill \
  --since 2026-07-22T05:00 \
  --until 2026-07-23T21:00 \
  --dry-run

# Execute with moderate batch size and LLM cap
python manage.py backfill \
  --since 2026-07-22T05:00 \
  --until 2026-07-23T21:00 \
  --batch-size 6 \
  --pause 10 \
  --max-llm-calls 50

# Check progress
python manage.py backfill \
  --since 2026-07-22T05:00 \
  --until 2026-07-23T21:00 \
  --status
```

### Targeted Re-Classification of a Known Window

```bash
python manage.py backfill \
  --since 2026-07-22T14:00 \
  --until 2026-07-22T18:00 \
  --max-llm-calls 100
```

### Resume After Failure

If a backfill invocation fails partway through (e.g., Render job timeout), simply re-run the same command:

```bash
# State file at data/backfill/1753142400-1753268400.json tracks progress
python manage.py backfill \
  --since 2026-07-22T05:00 \
  --until 2026-07-23T21:00
```

The backfiller loads the state file, finds `calls_completed_ids: ["call_a_01", "call_a_02"]`, and picks up with `call_a_03`. No manual tracking is required.

### Reset and Start Over

```bash
python manage.py backfill \
  --since 2026-07-22T05:00 \
  --until 2026-07-23T21:00 \
  --reset
```

### Override Computed Parameters

```bash
# Force smaller results window (useful for testing)
python manage.py backfill \
  --since 2026-07-22T05:00 \
  --until 2026-07-23T21:00 \
  --max-results 200 \
  --max-pages 10 \
  --batch-size 2
```
