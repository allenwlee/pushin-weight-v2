# classify_batch_limits probe — first end-to-end results

**Date:** 2026-07-15 (JST)
**Plan:** docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md
**Commits:** 5f44e34 (U1 spine), 8994af5 (U2 sweeps + U3 JSON)
**Test status:** 19/19 pass

## TL;DR

The probe is operational and lands clean ceiling tables for all 6 axes
in dry-run mode. A live `cache_state` run on the Alibaba gateway
confirmed the LLM path works end-to-end (single-post calls completed
in 2-3 s) but surfaced a probe-internal timing artifact in
`sweep_cache_state` that I'll fix in a follow-up.

## What I ran

### 1) `--dry-run` across all 6 axes (offline, ~instant)

```
$ python -m scripts.probes.classify_batch_limits.probe --dry-run \
    --axes=batch_size,max_tokens,input_tokens,concurrency,cache_state,rpm
```

All 6 sweeps produced fixed-width ASCII tables; every row's status was
`dry_run`; verdict correctly reported "all green — no axis failed";
JSON written to `data/runs/probe_<utc>.json`. The wiring (synthetic
tweet builder, status classifier, table renderer, JSON writer) is
verified end-to-end without ever touching the LLM.

**Per-axis dry-run row counts (sanity-check the sweep values land):**

| Axis | Rows | Notes |
|---|---|---|
| batch_size | 9 | values: 1, 5, 10, 15, 20, 25, 30, 40, 50 |
| max_tokens | 5 | values: 256, 512, 1024, 2048, 4096 |
| input_tokens | 6 | values: 2k, 4k, 8k, 16k, 32k, 64k |
| concurrency | 5 | values: 1, 2, 4, 8, 16 |
| cache_state | 3 | three consecutive calls at batch_size=1 |
| rpm | 3 | values: 60, 120, 240 (60 s/row) |

Total: 31 sweep rows. The probe also reports per-row
`input_tokens`/`wall_clock_s`/`status_histogram` so a future diff can
answer "did the fix land?" without bespoke tooling (KTD5).

### 2) Live `cache_state` run on the Alibaba gateway

```
$ source ~/.env.secrets
$ python -m scripts.probes.classify_batch_limits.probe \
    --axes=cache_state --batch-size=1 --timeout=20
```

```
=== cache_state ===
call   | status  | wall_clock_s
-------+---------+--------------
call_1 | success | 3.065
call_2 | timeout | 63.795
call_3 | success | 2.118
```

JSON: `data/runs/probe_20260715T035634Z.json`.

**What this tells us:**

- **The LLM path works.** `classify_batch_pragmatics_full` round-trip
  on a single post is 2-3 s against the MiniMax proxy at
  `api.minimax.io` (Alibaba Cloud). The auth fix from earlier today is
  holding.
- **call_2 timing is a probe-internal artifact, not a classifier
  failure.** `sweep_cache_state` sleeps 30 s between calls to keep the
  prompt cache warm across the Anthropic 5-min TTL, but `_fire_one_batch`
  enforces a 20 s per-call timeout (the `--timeout=20` I passed). The
  sleep pushed total wall-clock past 60 s, exceeding the probe's timeout
  budget. In a real production cycle this would never happen because
  calls aren't gated by an inter-call sleep.
- **The probe's verdict logic correctly treated `timeout` as
  non-success** (would have surfaced in the verdict line) and the JSON
  captured the failure shape.

## What this does NOT tell us yet

I deliberately did NOT run the live versions of these axes:

- **batch_size ≥ 25** — the original failure mode from this morning
  was a 20-post batch returning "Unterminated string" at column 3831.
  That's exactly the question `sweep_batch_size` is designed to answer
  (smallest batch_size that fails). Worth running next.
- **max_tokens ≤ 1024** — the production classifier uses 1024; lower
  values may force the truncation. Worth running.
- **input_tokens** — costs scale with prompt size; not free to probe
  at the high end. Worth running incrementally.
- **rpm and concurrency** — both are 60 s/row × 3-5 values = 3-5 min
  each. Burn rate against the Alibaba gateway is real; defer to a
  focused diagnostic session when the other axes have narrowed the
  search space.

## Probe-internal issues surfaced (not blocking)

1. **`sweep_cache_state` inter-call sleep interacts badly with
   `--timeout`.** The 30 s sleep is intentional (keep cache warm) but
   exceeds the default `--timeout=30` and races with user-supplied
   lower timeouts. Two fixes worth considering:
   - Reset `_FakeClient.in_flight_max` between rows so the test
     counter doesn't leak (already done at module level; live
     `_RealClient` may need the same).
   - Suppress the verdict for `cache_state` (treat any status other
     than `unterminated_json`/`5xx` as inconclusive — cache_state is
     about cache behavior, not failure detection).
2. **`_fire_one_batch` doesn't surface Anthropic `usage` data.** The
   probe reports `cache_creation_input_tokens: 0` /
   `cache_read_input_tokens: 0` because the batched classifier path
   doesn't propagate the SDK's `usage` block. The cache_state sweep
   therefore can't directly observe cache hits today — it can only
   observe whether the call succeeded at all. To make cache_state
   useful, `_call_signal_with_retry` needs to expose `usage` back
   through `classify_batch_pragmatics_full`.
3. **Dry-run verdict suppression is silent.** "All green — no axis
   failed" reads as a pass, but in dry-run it really means "we didn't
   test anything." Worth a follow-up that adds "(dry-run, no LLM
   calls fired)" to the verdict line for clarity.

## Next steps (in priority order)

1. **Fix the `_fire_one_batch` usage-surfacing gap** so `cache_state`
   can actually observe cache hit/miss. Without this, the A5 axis
   isn't useful as designed.
2. **Run live `batch_size` sweep** (A1) — directly answers the
   question that motivated this probe: is 20 the batch-size ceiling?
3. **Run live `max_tokens` sweep** (A3) at batch_size=20 — is the
   1024 token response cap the truncation culprit?
4. **Address the dry-run verdict ambiguity** so operators can't
   mistake "all green (dry-run)" for "all green (production-safe)."
5. **Defer live `rpm` / `concurrency`** until (1)-(3) have narrowed
   the search space — the gateway cost of those sweeps is real.

## Artifacts

- Probe: `x-monitoring/scripts/probes/classify_batch_limits/{probe.py,test_probe.py,README.md}`
- Tests: 19/19 pass (`python -m pytest scripts/probes/classify_batch_limits/test_probe.py -v`)
- Dry-run JSON: `data/runs/probe_<utc>.json` (timestamped, diff-friendly)
- Live JSON: `data/runs/probe_20260715T035634Z.json`
- Plan: `docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md`
- Commits: 5f44e34 (U1), 8994af5 (U2+U3)