# Issue: `max_tokens` not threaded into `classify_batch_pragmatics_full` — production batch_size=20 silently truncates responses

**Date opened:** 2026-07-15
**Reporter:** probe work in `scripts/probes/classify_batch_limits/`
**Severity:** high — production batches of 20 posts are being silently truncated mid-JSON, but the per-post fallback masks the truncation as success, so the failure mode is invisible without instrumentation.
**Status:** fix applied locally (max_tokens threaded through); awaiting verification.

## Summary

`x_monitor/attribution.py:classify_batch_pragmatics_full` does not accept or
forward a `max_tokens` parameter. The internal helper `_call_signal_with_retry`
hardcodes `max_tokens=1024` in the SDK call. For batch_size ≥ 10 the model
needs ~3000 tokens to emit valid JSON for all posts in the batch, so the
response gets sliced mid-token, and `AnthropicClaudeClient.messages_create`'s
`_json.loads(raw)` at the bottom of the call path raises
`"Unterminated string starting at: line 1 column 3242-3935"`.

The production code path catches this exception and falls back to per-post
retries (the v1.7 fail-soft contract from plan 2026-07-13-001), so the user
sees "24 posts inserted" without ever knowing that the batched LLM call
silently failed and the per-post fallback rescued the run.

## Evidence

### Probe data
- Plan: `docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md`
- Probe: `x-monitoring/scripts/probes/classify_batch_limits/probe.py`
- Probe tests: `x-monitoring/scripts/probes/classify_batch_limits/test_probe.py` (21/21 pass)
- Live JSON: `x-monitoring/data/runs/probe_<UTC>.json` (multiple runs on 2026-07-15)
- Summary: `docs/debug/2026-07-15-classify-batch-limits-probe-results.md`

### Run 1 (live batch_size sweep)
batch_size=1, 5 succeed in 5-6 s with full JSON responses (1926 chars for N=5).
batch_size=10, 15, 20 all time out at 57-60 s with `"Unterminated string"
at column 3242-3831`. The per-post fallback rescues the response, masking
the failure as success — without the `on_batch_error` wiring in the probe,
this would have read as a green sweep.

### Run 2 (live max_tokens sweep at batch_size=20)
With `max_tokens` NOT threaded through to the SDK (the bug), the probe swept
[256, 512, 1024, 2048, 4096] at batch_size=20 — every value timed out at
identical columns (3242 / 3935). The fact that 4096 timed out at the same
column as 1024 is the proof: the parameter never reaches the SDK, so every
sweep is effectively `max_tokens=1024`. **The whole A3 axis of the probe was
a silent no-op.**

### Math
For N=20 tweets with ~1.5 brands per tweet and ~350 chars per classification
JSON object, the response needs ~3000 tokens of structured output. The
SDK default `max_tokens=1024` caps the response at ~4096 chars, slicing
mid-JSON at exactly the columns we observe.

The input side is fine — total prompt for N=20 is ~20.6 KB / ~5162 tokens
(/4 estimate), well under any reasonable gateway input cap. The
`_PRAGMATICS_FULL_SYSTEM_PROMPT` (13.2 KB / ~3300 tokens) dominates but is
prompt-cacheable in principle.

## Root cause

Three layers of `max_tokens` loss:

1. `x_monitor/attribution.py:_call_signal_with_retry(client, prompt)` —
   hardcodes `max_tokens=1024` at line 926. No parameter accepted.

2. `x_monitor/attribution.py:classify_batch_pragmatics_full(...)` —
   signature (line 1723) does not accept `max_tokens`. Cannot forward
   what it doesn't have.

3. `x_monitor/scripts/probes/classify_batch_limits/probe.py:_fire_one_batch`
   — accepts `max_tokens` but passes it to `classify_batch_pragmatics_full`
   as a keyword arg that the function silently drops (Python doesn't
   error on unknown kwargs to a function that uses `**kwargs`).

The probe was hiding the bug because A3 (`sweep_max_tokens`) iterated
five values but always sent `max_tokens=1024` to the SDK.

## Fix applied (local)

| File | Change |
|---|---|
| `x_monitor/attribution.py` line 916 | `_call_signal_with_retry` accepts `*, max_tokens: int = 1024`, forwards to `messages_create` |
| `x_monitor/attribution.py` line 1723 | `classify_batch_pragmatics_full` accepts `*, max_tokens: int = 1024`, forwards |
| `x_monitor/attribution.py` line 1798 | Passes `max_tokens=max_tokens` through to `_call_signal_with_retry` |
| `scripts/probes/classify_batch_limits/probe.py` ~L180 | `_fire_one_batch` passes `max_tokens=max_tokens` to `classify_batch_pragmatics_full` |
| `scripts/probes/classify_batch_limits/test_probe.py` | New test `test_fire_one_batch_threads_max_tokens_to_classify` pins the threading |

Signature change is backward-compatible: defaults to 1024, so any caller
that does not pass `max_tokens` gets the old behavior.

Tests: 21/21 pass.

## What still needs investigation

### 1. Should `classify_batch_pragmatics_full`'s DEFAULT be raised?

Currently the fix preserves `max_tokens=1024` as the default, which means
the production call site at `x_monitor/run.py` (or wherever
`classify_batch_pragmatics_full` is called in the v1.7 pipeline) keeps
the old behavior unless explicitly bumped.

**Question:** should the default be raised to 4096 (the value we
estimated is safe for batch_size=20), forcing the fix everywhere with
zero caller changes? Or should the default stay at 1024 to preserve
behavior for callers that pass `tweets=[]` for some reason and only
override at the v1.7 call site?

**Recommendation:** raise default to 4096. Reasoning:
- Single-post paths need ~250-400 tokens, well under 4096.
- Batch path needs ~3000 tokens at batch_size=20.
- 4096 covers all current use cases with 30% headroom.
- Cost difference is negligible (output is cheaper than input).
- Defaulting low means a future caller who forgets to pass max_tokens
  reintroduces the bug.

### 2. Should we hard-cap `max_tokens` based on batch_size?

The probe's A1 axis shows the failure ceiling at batch_size=10 today.
With `max_tokens=4096` actually applied, the ceiling may move to
batch_size=30 or 50. **The probe needs to be re-run with the fix to
find the new ceiling.** If it lands at, say, batch_size=40, we should
consider:

- Computing `max_tokens` dynamically from `len(tweets)` (e.g. `200 *
  len(tweets)` or `min(4096, 200 * len(tweets))`).
- Capping `batch_size` to a value where the response comfortably fits
  in the chosen `max_tokens` ceiling.

### 3. Was the per-post fallback masking OTHER bugs?

The fail-soft contract from plan 2026-07-13-001 was designed to prevent
a single bad post from poisoning a batch. But the same contract silently
swallows batch-level failures (response truncation, gateway 4xx/5xx,
malformed JSON). The probe's `on_batch_error` wiring is one way to
expose this; another is a metric/counter on `classify_batch_pragmatics_full`
that increments per batch failure so operators see the masking rate
without needing the probe.

**Question:** should `_run_post_fetch` (or wherever the v1.7 pipeline
calls into the batch classifier) log a WARNING every time the batch
fails and per-post fallback runs, with a counter that ops can alert on?

### 4. Are the other `_call_signal_with_retry` callers affected?

Two other call sites use the same helper:
- `classify_post` (line 972) — single-post, response ~250-400 tokens, 1024 is fine.
- The signal-extraction path (line 1590) — also single-post or short,
  1024 is fine.

Neither needs `max_tokens` > 1024 today, but they should accept the
parameter for symmetry with the batch path. (Low priority — current
behavior is correct.)

### 5. Probe follow-ups

- Re-run the `max_tokens` sweep with the fix to confirm batch_size=20
  succeeds at `max_tokens=2048` or `max_tokens=4096`.
- Re-run the `batch_size` sweep with `max_tokens=4096` to find the
  NEW ceiling (was 10, may now be 30-50).
- Run `concurrency` and `rpm` axes against the new ceiling to make sure
  we don't regress there.

## Files to inspect

- `x-monitoring/x_monitor/attribution.py` — the bug + the fix
- `x-monitoring/scripts/probes/classify_batch_limits/probe.py` — A3 axis
  was a silent no-op pre-fix; verify post-fix
- `x-monitoring/scripts/probes/classify_batch_limits/test_probe.py` —
  new regression test pins the threading
- `x-monitoring/x_monitor/run.py` — the v1.7 call site that calls
  `classify_batch_pragmatics_full`; needs to pass `max_tokens=4096`
  (or the default needs to be raised — see question 1)
- `docs/debug/2026-07-15-classify-batch-limits-probe-results.md` —
  probe results summary, will need updating post-re-run

## Suggested next steps for the investigating agent

1. **Verify the fix.** Run the probe's `max_tokens` axis at batch_size=20
   post-fix. Expected: 4096 succeeds, 2048 may succeed, 1024 and below
   time out at column 3242-3935. Confirms the parameter is now live.
2. **Find the v1.7 call site.** `grep -rn "classify_batch_pragmatics_full"
   x_monitor/` will surface it. Verify it doesn't pass `max_tokens` (so
   the default will apply) and decide whether to raise the default to
   4096 or pass it explicitly.
3. **Re-run batch_size sweep.** With `max_tokens=4096`, expect the
   ceiling to move up. Document the new ceiling.
4. **Decide on masking observability.** Add a counter or warning to
   `classify_batch_pragmatics_full` for batch-fail → per-post-fallback
   transitions so the silent masking rate is visible without a probe.
5. **Update the probe-results doc.** Re-run, record the new ceiling,
   note that A3 was previously a no-op.