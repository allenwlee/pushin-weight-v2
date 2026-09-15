# Conditional third classifier call: frozen trial

The owner requested this experiment on September 15. It tests whether a focused
third call recovers jobs, personnel changes, events, and opportunities that the
two-role DeepSeek run omitted. R98's saved answers are fixed; only the new call
is purchased. The sole owner-reviewed 45-case reference stays local and is used
for scoring, not sent to the provider. This is consumed calibration evidence.

The [contract](../analysis/2026-09-15-103348-u18-r100-conditional-rare-type-contract.json)
freezes the source hashes, prompt, screen, schedule, merge, scoring, and caps.
The [shared plan](../plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md)
records authorization in Exception 19 and requirement R100. The trial code is
[u18_conditional_rare_type_pilot.py](../../scripts/u18_conditional_rare_type_pilot.py).

The source/context screen recognizes broad English, Japanese, and Chinese cues;
it also accepts prior question, advertising, or rare-type labels. It selects
23/45 rows: 10 English, 5 Japanese, and 8 Simplified Chinese. Original batch
boundaries produce 12/8/3 specialist inputs, three additional calls alongside
the six saved base calls. The gate deliberately favors recall; its selected
fraction is not a production prevalence estimate. Already context-missing base
rows are not repaired. Skipped positives count as screen misses.

The specialist makes four explicit independent Boolean decisions per row. Each
positive must cite a short verbatim source/context substring. Existing labels
remain, supported missing rare labels are added, and exclusive `other` is
removed when necessary. No other axis changes. An invalid response preserves
that original batch, counts as failure, and stops the run without retries.
Negative specialist judgments cannot remove an erroneous base label.

The direct route remains `https://api.deepseek.com/anthropic/v1/messages`, with
`model=deepseek-v4-flash`, temperature zero, thinking disabled, 6,000 output
tokens per call, concurrency one, and 90-second timeout. There are at most
three transports, 65,259 conservative input tokens, and 18,000 output tokens.
The reserved ceiling is **$0.05247396** at the older conservative $0.44/$1.32
input/output rates; the runner refuses an envelope above $0.15. Cache-read
tokens are included in the conservative cost. Unknown usage reserves the full
request allowance. An exclusive run marker prevents accidental repeated spend.

[DeepSeek's pricing page](https://api-docs.deepseek.com/quick_start/pricing/),
checked September 15, says the legacy Flash name is now served by
**DeepSeek-V4.1-Flash**. Current peak prices per million tokens are $0.30 input,
$0.006 cache read, and $1.20 output; off-peak prices are half. Peak times are
01:00–04:00 and 06:00–10:00 UTC on weekdays. The report estimates current-price
cost from observed tokens/time and separately shows the conservative ceiling;
neither is an independently verified invoice. This provider alias change means
the experiment cannot isolate the effect of the architecture from a possible
model-version effect. It still measures the practical incremental change to
the fixed baseline answers.

Diagnostic success requires at least one recovered rare label, no incorrect
additions, complete valid specialist responses, and respected caps. All existing
full-quality gates are scored separately and are required for activation. Jobs
have only one reference positive, events three, opportunities five, and
personnel changes zero. The trial cannot establish population accuracy or
personnel recall. No further human review is required.

Before inference, 82 focused tests passed: 17 specialist routing/parser/caller
regressions, 29 existing two-role pilot tests, and 36 Ollija checks. This trial
changes no runtime configuration, harvester, database state, or deployment.

Commands, from the canonical feature worktree:

```sh
.venv/bin/python -m scripts.u18_conditional_rare_type_pilot prepare \
  --contract docs/analysis/2026-09-15-103348-u18-r100-conditional-rare-type-contract.json
.venv/bin/python -m scripts.u18_conditional_rare_type_pilot run \
  --contract docs/analysis/2026-09-15-103348-u18-r100-conditional-rare-type-contract.json
```

`prepare` already ran and refuses to overwrite the contract. The API key is
loaded only for `run` from the existing local secret store; it is never put in
an artifact. Raw inputs/outputs stay in ignored
`.context/u18/conditional-rare-type-pilot-r100-v1/`. R98's original timing/cost
comes from its retained `adaptive-result.json`, since a previous provider-free
replay reset timing and spend in its candidate file without changing labels.
