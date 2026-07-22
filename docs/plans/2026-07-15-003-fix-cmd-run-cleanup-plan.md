---
title: Retire remaining Q-string references in run.py
type: fix
date: 2026-07-15
updated: 2026-07-22
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

## Goal Capsule

Replace the last hardcoded `"Q1"`/`"Q5"` strings in `_planned_call_to_query` and synthetic `Query(id="Q5")` objects with the planner's A/B/C call_ids. The run JSON `query_id` field already emits A/B/C correctly — the remaining Q-strings live only in the `call_state` cursor keys and the skip-order Query stubs.

## What's Already Done

- **Run JSON `query_id`** — already emits `call.call_id` (A/B1/B2/B3/C1/C2) at lines 1162 and 1268.
- **`missing_queries:*` → `missing_brand_keywords:*`** — already renamed at lines 1029-1033.
- **`n_classifications_written` counter** — already reads `store._classifications_written` after `_run_post_fetch` (line 1521), and `insert_posts_brands_signals` bumps it (store.py:1782).
- **`degraded_skip_order`** — config.yaml already uses A/B/C strings.

## What's Left

Two sites still emit Q-strings:

### Site 1: `_planned_call_to_query` (run.py:191-210)

Returns `"Q1"` for account calls and `"Q5"` for brand_wide calls. The caller uses `synth_q.id` as:
- The `query_id` portion of the `call_state` cursor composite key `(brand_id, call_id, call_kind, bucket, query_id)`
- The `q.id` in `apply_skip_order` when matching against `degraded_skip_order`

**Fix:** Change `_planned_call_to_query` to return `call.call_id`. The `call_state` cursor key becomes `(brand_id, call_id, call_kind, bucket, call_id)` — the `query_id` column now carries the same value as `call_id`. Existing cursor rows with `query_id="Q5"` become orphans; the next cycle will create new rows with the corrected key and start with a fresh cursor (no data loss — just a one-time wider initial fetch window).

### Site 2: Synthetic `Query(id="Q5")` objects (run.py:834, 851, 1039)

These are used in the skip-order / budget-gating path where a synthetic Query is needed but no PlannedCall exists yet. Currently hardcoded to `"Q5"`.

**Fix:** The three sites are:
- Line 834: `Query(id="Q5")` in the error path — change to `"B3"` (first in skip order)
- Line 851: `Query(id="Q5")` in the model-filter path — same
- Line 1039: `Query(id="Q5")` in the keyword-missing path — same

## Implementation Units

### U1. Replace Q-strings in `_planned_call_to_query`

**Files:** `x-monitoring/x_monitor/run.py`

**Change:**
```python
def _planned_call_to_query(call):
    if call.call_kind == "account":
        qid, min_faves = call.call_id, MIN_FAVES_FOR_LIST_CALL
    else:
        qid, min_faves = call.call_id, 0
    return Query(id=qid, ...)
```

**Impact:** `call_state` cursor rows with `query_id="Q5"` stop matching. On next cycle, each call creates a fresh cursor row with `query_id=<call_id>` and starts from a null cursor (wider initial fetch window, dedup handles duplicates). No migration needed — old rows are simply never read again.

**Verification:** `grep -n 'Q1\|Q5' x_monitor/run.py` returns zero matches in the `_planned_call_to_query` function. A dry-run plan shows `synth_q.id` matching `call.call_id`.

### U2. Replace synthetic `Query(id="Q5")` stubs

**Files:** `x-monitoring/x_monitor/run.py`

**Change:** Replace the three `id="Q5"` literals at lines 834, 851, 1039 with `id="B3"` (the first entry in `degraded_skip_order`, which is the most-expendable call under budget pressure).

**Verification:** Zero `Q5` matches in `x_monitor/run.py`.

## Verification Contract

| Gate | Command | Pass criterion |
|---|---|---|
| Static grep | `grep -nE '"Q[1-6]"' x_monitor/run.py` | Zero matches |
| Dry-run plan | `python3 -c "from x_monitor.query_plan import plan_calls; ..."` | All `PlannedCall.call_id` values are A/B1/B2/B3/C1/C2 |
| Unit tests | `python3 -m pytest tests/test_run.py -q` | Pass |
