# Translator batch-limits probe

**Location:** `scripts/probes/translator_batch_limits/probe.py`

**Trigger:** 2026-08-06 08:47:02 UTC — translator returned
`translator_batch_failed` after a 11,108-byte response was truncated
mid-JSON at DeepSeek V4 Pro. The translator cap was raised to 65,536
tokens in commit `c09a291` (2026-08-05) after a live probe measured
19,554 output tokens (`stop_reason=end_turn`). Today's truncation
**contradicts** that measurement.

**Purpose:** Rules out the two remaining hypotheses after the OpenAI
shim is ruled out (no provider change in recent commits):

1. **DS V4 has a per-request token limit that varies** (different
   bucket on a different day).
2. **DS V4's `thinking` budget leaks into `max_tokens`** when the
   Anthropic-compatible shim's `thinking={"type": "disabled"}` is
   not honored on every request.

**Axes swept (one knob varies, others fixed):**

- **A1 `max_tokens`:** `[4096, 8192, 16384, 20000, 32768, 65536]`
- **A2 `batch_size`:** `[1, 5, 10, 15, 20, 25, 30]`
- **A3 `input_tokens` (per-tweet chars):** `[200, 500, 1000, 2000, 4000, 8000]`
- **A4 `thinking`:** `[{"type": "disabled"}, None, {"type": "enabled"}]`

**Per-row metrics captured:** `status`, `wall_clock_s`, `stop_reason`,
`input_tokens`, `output_tokens`, `response_chars`, `len_results`,
`parse_error` (if any).

**Verdict line:** Names the smallest axis value that hit
`stop_reason=max_tokens` or an error.

## Usage

```bash
# offline — never hits the LLM
python -m scripts.probes.translator_batch_limits.probe --dry-run

# single axis, real calls
python -m scripts.probes.translator_batch_limits.probe --axes=max_tokens

# targeted re-run after a fix lands
python -m scripts.probes.translator_batch_limits.probe --axes=thinking
```

## Credential detection

The prod env-group `pushinweight-secrets` carries two distinct credentials. The probe auto-detects which one the active base URL needs:

- The MiniMax proxy key (prefix `<the provider's key value>`) — used when the base URL routes through `api.minimax.io/anthropic` (the stale default).
- The DeepSeek direct key (prefix `<the provider's key value>`) — used when the base URL routes through `api.deepseek.com/anthropic` (the cron sets a service-level override `X_MONITOR_TRANSLATOR_BASE_URL` for this).

The probe picks the right credential based on the active base URL. On the dev shell, set the env vars from `~/.env.secrets` directly (see `.env.secrets` for the current values) plus the base URL override. Refer to the existing translator code path in `x_monitor/reattribute.py:466` for the exact resolution rules.


## Related

- `docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md` —
  the classifier-side equivalent probe (sister file).
- `x_monitor/translator.py:657` — `translate_batch_pragmatics` (the
  production call site).
- `x_monitor/translator.py:210` — `_call_with_retry` (the retry path
  the probe mirrors; reuses the production Anthropic SDK client).
- `x_monitor/attribution.py:845` — `_resolve_translator_model` (model
  resolution by env-substring; probe uses this for the resolved name).
- `docs/operations/pause-and-resume-harvest-cron.md` — pause/resume
  procedure for the cron (use this to halt during probe runs).
- `x_monitor/reattribute.py:466` — `build_translator_client_from_env`
  (the client factory; the probe uses the same factory).

## What to do with results

If the verdict is `limit hit: max_tokens=N → stop_reason=max_tokens`
with `N < 20000` (or similar), DS V4 has a per-request cap lower
than the assumed 20k. Lower the prod cap and re-measure.

If the verdict is `no stop_reason hit; all rows ok` for A1+A2+A3, the
11k truncation is **not** a per-request DS V4 limit — look at the
thinking axis (A4) or the Anthropic SDK's response reader (a
buffered read may be truncating the stream at 11k chars).

If A4 `thinking=enabled` succeeds where `thinking=disabled` fails,
DS V4's `thinking=disabled` is not always honored — file a ticket
with DeepSeek or work around in the client.
