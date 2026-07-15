# classify_batch_limits

Diagnostic probe for the production LLM classifier
`x_monitor.attribution.classify_batch_pragmatics_full`. Sweeps 6 axes that
could be the "limit" of the batched path and reports a one-line verdict
naming the smallest axis value that fails.

Plan: `docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md`

## Axes

| Axis | What varies | Default sweep |
|---|---|---|
| `batch_size` | posts per LLM call | 1, 5, 10, 15, 20, 25, 30, 40, 50 |
| `input_tokens` | prompt length (text repetition) | 2k, 4k, 8k, 16k, 32k, 64k |
| `max_tokens` | response cap passed to `messages.create` | 256, 512, 1024, 2048, 4096 |
| `rpm` | serial request rate | 60, 120, 240 (60 s/row) |
| `cache_state` | prompt-cache write vs read across 3 calls | 3 calls, 30 s gaps |
| `concurrency` | parallel call fan-out | 1, 2, 4, 8, 16 |

## Quickstart

```bash
# Offline — never hits the LLM. Builds every prompt, prints len/estimated tokens.
python -m scripts.probes.classify_batch_limits.probe --dry-run

# Single axis, real calls (requires ANTHROPIC_API_KEY)
python -m scripts.probes.classify_batch_limits.probe --axes=batch_size

# Targeted re-run after a fix lands
python -m scripts.probes.classify_batch_limits.probe --axes=concurrency

# Subset of axes
python -m scripts.probes.classify_batch_limits.probe --axes=batch_size,max_tokens

# Run tests
python -m pytest scripts/probes/classify_batch_limits/test_probe.py -v
```

## Output

Per axis: a fixed-width ASCII table (status, wall-clock, key metric).
At the end: a one-line verdict (e.g. `VERDICT: limit hit:
batch_size=25 -> unterminated`) plus a timestamped JSON file under
`data/runs/probe_<utc>.json` for follow-up diffs.

## Credentials

Set `ANTHROPIC_API_KEY` (sourced from `~/.env.secrets` if you run via
the standard wrapper). The probe routes through the same
`AnthropicClaudeClient` the production pipeline uses, with the same
`ANTHROPIC_BASE_URL` (the MiniMax Alibaba gateway).

## Files

- `probe.py` — the probe itself
- `test_probe.py` — 19 unit tests colocated next to the script
- `__init__.py` — package marker so `python -m ...` resolves
- `README.md` — this file