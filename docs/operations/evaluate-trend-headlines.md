# Evaluate per-brand trend headlines

`evaluate_trend_headlines` runs the production all-brand dossier, rank,
five-brand editor batch, critic, transport, and mechanical-validation
contracts without enqueueing work or publishing a headline. It is an explicit,
finite operator tool; tests, scheduled workers, browser requests, and harvest
cycles never invoke it.

## Prepare a finite manifest

Before live transport, verify the configured route's current context and
pricing with the provider or the project's contracted rate card. Record the
source revision and check time. The manifest is a hard cap, not an estimate:

```json
{
  "run_id": "owner-chosen-run-id",
  "reviewer": "operator-or-agent-identity",
  "model": "deepseek-v4-pro",
  "max_calls": 40,
  "input_token_budget": 2000000,
  "output_token_budget": 700000,
  "dollar_budget": "5.00",
  "input_dollars_per_million_tokens": "CURRENT-VERIFIED-RATE",
  "output_dollars_per_million_tokens": "CURRENT-VERIFIED-RATE",
  "pricing_version": "rate-card-name-and-date",
  "pricing_checked_at": "YYYY-MM-DDTHH:MM:SS+00:00",
  "context_window_tokens": 500000,
  "brand_cap": 25,
  "concurrency": 1,
  "max_packet_bytes": 131072
}
```

The command rejects incomplete, non-positive, or over-budget manifests; a
model other than the explicit `deepseek-v4-pro` route; concurrency other than
one; more than 100 brands; a packet over the declared byte limit; or a request
that exceeds the declared context window. It reserves the deterministic
canonical request graph's calls, input estimates, maximum outputs, and cost
before transport. After the rank response determines the live batch order,
the evaluator checks each actual packet and context footprint again before
sending it. Credentials come from the normal DeepSeek environment and never
enter the manifest or artifact.

## Synthetic preflight and execution

Synthetic mode contains closed one-, three-, and five-brand fixtures covering
sparse data, flat volume, unavailable comparison, non-English evidence,
first-party evidence, and high volume. It also sends eight critic controls:
one fully supported narrative plus unsupported event, causality, event
conflation, mistranslation, cross-evidence synthesis, invented-detail, and
unsafe-instruction drafts. The fixed graph is 17 calls:

- three rank calls;
- three editor calls;
- three critic calls;
- eight critic-control calls.

For compatibility with the original operator command, omitting both dataset
selectors means `--synthetic`. Real-data access always requires `--real`.

Inspect the deterministic reservation plan without resolving a credential or
writing an artifact:

```bash
python manage.py evaluate_trend_headlines \
  --dry-run --synthetic \
  --manifest /absolute/path/to/manifest.json
```

After the finite manifest is authorized, execute it sequentially:

```bash
python manage.py evaluate_trend_headlines \
  --execute --synthetic \
  --manifest /absolute/path/to/manifest.json \
  --cancel-file /absolute/path/to/evaluation.cancel \
  --output-dir docs/analysis
```

Creating the cancellation file stops before the next provider call; there are
no automatic retries or repair calls:

```bash
touch /absolute/path/to/evaluation.cancel
```

Activation requires completion, a decision for every eligible brand, all
eight mechanically valid control responses, zero false acceptance across the
seven adversarial controls, and zero false holds of the supported control.

## Real-data evaluation

Real mode builds deterministic, read-only snapshots for the requested fixed
windows. When all brands fit under `brand_cap`, it evaluates all of them. If
the cap is smaller, selection is deterministic and stratified to retain sparse,
flat, unavailable-baseline, non-English, first-party, ordinary, and
high-volume cases. It still does not create queue, lifecycle, visible-run, or
publication rows.

Real mode intentionally does not repeat the synthetic critic controls. Its
artifact therefore records calibration as `not_run` and cannot by itself
claim activation readiness; pair it with a green synthetic control artifact.

```bash
python manage.py evaluate_trend_headlines \
  --dry-run --real \
  --windows 1,7,30,365 \
  --as-of 2026-08-27T00:00:00+00:00 \
  --manifest /absolute/path/to/manifest.json

python manage.py evaluate_trend_headlines \
  --execute --real \
  --windows 1,7,30,365 \
  --as-of 2026-08-27T00:00:00+00:00 \
  --manifest /absolute/path/to/manifest.json \
  --cancel-file /absolute/path/to/evaluation.cancel \
  --output-dir docs/analysis
```

Do not put credentials, connection strings, or private author identifiers in
committed artifacts. Production text may be reviewed only under the
repository's existing data-handling authorization.

## Review the artifacts

Execution writes timestamped JSON and Markdown siblings under the selected
output directory. The JSON is authoritative and includes:

- the manifest and exact preflight estimates;
- every closed snapshot, stage envelope, and provider request;
- every raw provider response and mechanical verdict;
- provider-reported or conservatively estimated token usage, latency, and
  reserved/accounted cost;
- each brand's approve, repair, hold, no-content, or data-quality result;
- bilingual rubric results for why-first relevance, factual support,
  proportionality, translation equivalence, and secondary usefulness;
- critic-control false accepts/holds and the final activation assessment.

The Markdown sibling is the human review surface. Keep invalid and held calls
in the artifact; never average away a critical failure.

## Materiality calibration

Materiality calibration is provider-free and read-only. Each anchor/window
uses a fresh repeatable-read PostgreSQL transaction and emits proposals only
when it has enough samples:

```bash
python manage.py evaluate_trend_headlines \
  --calibrate \
  --as-of 2026-08-14T00:00:00+00:00 \
  --anchor-count 12 \
  --anchor-step-days 7 \
  --minimum-samples 20 \
  --epsilon 0.1 \
  --windows 1,7,30,365 \
  --output-dir docs/analysis
```

The command never writes proposed flat/small/meaningful/sharp bands back to
configuration.

## Safety boundary

- Evaluation never publishes, enqueues, harvests, or mutates narrative state.
- Browser loads and filters never trigger this command or any provider call.
- Provider transport is serial, finite, and cancellation-aware.
- A transport failure is not retried automatically.
- Production activation stops on an incomplete run, an undecided eligible
  brand, a supported-control false hold, an unsupported-control false accept,
  or incomplete budget accounting.
