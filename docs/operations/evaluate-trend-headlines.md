# Evaluate why-first trend headlines

This command evaluates synthetic conversation stories through the production
provider-packet, request, and output-validation contracts. It is an explicit
operator tool: scheduled tasks and ordinary tests never invoke it.

It cannot publish a headline, enqueue a worker, run harvesting, or write
historical facts. Synthetic execution writes only its requested report files.
Calibration reads stored posts in bounded PostgreSQL read-only transactions and
does not change `config.yaml`.

## Prepare a finite manifest

Before authorizing transport, recheck the current `deepseek-v4-pro` context
limit and input/output token prices in DeepSeek's official
[pricing documentation](https://api-docs.deepseek.com/quick_start/pricing) and
[token-usage guidance](https://api-docs.deepseek.com/quick_start/token_usage).
Put the checked values and timestamp in a local manifest; do not commit
credentials or treat an old example price as current.

```json
{
  "run_id": "owner-chosen-run-id",
  "model": "deepseek-v4-pro",
  "max_calls": 28,
  "input_token_budget": 20000000,
  "dollar_budget": "OWNER-SET-FINITE-LIMIT",
  "input_dollars_per_million_tokens": "CURRENT-OFFICIAL-PRICE",
  "output_dollars_per_million_tokens": "CURRENT-OFFICIAL-PRICE",
  "pricing_checked_at": "YYYY-MM-DDTHH:MM:SSZ",
  "context_window_tokens": "CURRENT-OFFICIAL-LIMIT",
  "concurrency": 1,
  "max_output_tokens": 1600,
  "max_packet_bytes": 131072
}
```

The command rejects missing or non-positive call, input-token, and dollar
budgets; a model other than the explicit `deepseek-v4-pro` route; concurrency
other than one; or a changed output cap. UTF-8 request bytes are used as a
conservative upper bound for input tokens. Before every transport it reserves
that input estimate plus the maximum output-token cost. Provider-reported usage
then becomes the accounted usage for the next boundary check.

## Preflight without transport

```bash
python manage.py evaluate_trend_headlines \
  --dry-run \
  --manifest /absolute/path/to/local-manifest.json
```

Inspect the exact model, call count, fixed concurrency, evidence budgets,
packet bytes, conservative input-token estimates, total reserved cost, and
whether the plan fits the declared call cap. Dry-run does not resolve an API
credential or create an artifact.

The deterministic corpus contains sixteen pairwise-covering scenarios across
quantity, rate, mix, content, evidence strength, shape, data quality, and
candidate competition. Two sentinels repeat at 4, 12, 24, and 48 excerpts with
a fixed 1,000-character cap. A separate density sweep holds 24 excerpts fixed
while varying the character cap, so count and text density are not confounded.

## Execute only after owner authorization

No live execution is implied by a successful preflight. After the owner
explicitly authorizes that exact manifest:

```bash
python manage.py evaluate_trend_headlines \
  --execute \
  --manifest /absolute/path/to/local-manifest.json \
  --cancel-file /absolute/path/to/evaluation.cancel \
  --output-dir docs/analysis
```

To cancel cleanly, create the declared cancellation file. The current call is
allowed to finish; the runner checks the file before the next call and stops
without starting another transport.

```bash
touch /absolute/path/to/evaluation.cancel
```

Execution is sequential. A provider response is captured before contract
validation, so malformed or rejected bilingual output remains visible in the
report. A provider request failure consumes one call attempt but never triggers
an automatic retry or repair call.

## Review the artifacts

The output directory receives timestamped siblings:

```text
docs/analysis/
  YYYY-MM-DD-HHMMSS-why-first-headline-evaluation.json
  YYYY-MM-DD-HHMMSS-why-first-headline-evaluation.md
```

The JSON file is authoritative. It records the manifest and preflight, stop
reason, every scenario dimension, evidence and excerpt budgets, packet bytes,
estimated input tokens, reserved and accounted cost, provider token usage,
latency, raw output, extracted English and Chinese bodies, validator verdict,
and all nine editorial-rubric fields. Rubric entries begin as
`not_applicable` with a pending-review note; a human reviewer must change every
applicable field to `pass` or `fail` and explain the decision. Never discard an
invalid call or average away a critical failure.

The Markdown sibling is a short decision surface. The reviewed U6 report must
also record the quality plateau, rejected budgets, materiality decision, and
owner verdict before any production policy is frozen.

## Propose materiality bands read-only

Historical calibration is separate from provider execution:

```bash
python manage.py evaluate_trend_headlines \
  --calibrate \
  --as-of 2026-08-14T00:00:00Z \
  --anchor-count 12 \
  --anchor-step-days 7 \
  --minimum-samples 20 \
  --epsilon 0.1 \
  --windows 1,7,30,365 \
  --output-dir docs/analysis
```

At most 64 anchors are accepted. Each window/anchor reconstruction owns a fresh
repeatable-read, read-only PostgreSQL transaction. The report includes usable
sample and anchor counts, anchor coverage, absolute-change median and robust
upper quantiles, explicit near-zero epsilon, and proposed flat/small/meaningful/
sharp boundaries. Under-sampled groups have status `insufficient_samples` and
no proposal. The command never writes fixed bands back to configuration; that
requires the separate reviewed U6 change.

## Safety boundary

- Use only synthetic post text for provider evaluation; do not substitute raw
  production posts into the live report.
- Keep the manifest and cancellation path local. API credentials come from the
  configured DeepSeek environment variables and are never written to artifacts.
- Do not run `--execute` from pytest, a scheduled worker, harvest cron, or a
  release command.
- Stop policy freeze on any unsupported why or number, wrong leader, omitted
  supported why, quiet-window exaggeration, divergent locale judgment,
  under-sampled calibration group, or incomplete budget accounting.
