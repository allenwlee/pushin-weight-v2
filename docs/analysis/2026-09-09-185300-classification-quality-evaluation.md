# Classification quality evaluation

Use the offline classification evaluator to compare frozen Stage 1 candidate
output with independently adjudicated heldout labels. The evaluator reads JSON
files only. It does not query a database, call a provider, publish state, or
change a classification.

This evaluation is the R17 preproduction gate for classification semantics.
The synthetic parser fixture and the earlier 599-post analyst material are
calibration evidence only. Neither is fresh heldout gold, and neither can
support an accuracy claim.

## Unit and cohort

One evaluation unit is one `(example_id, brand_id)` pair. A post attributed to
two brands therefore contributes two units because every type, product label,
sentiment, and nationalism judgment is brand-specific.

Freeze the cohort after contract `stage1-v1`, taxonomy
`stage1-taxonomy-v2`, prompt `stage1-prompt-v3`, the model, and the available
context envelope have been fixed. The cohort must not contain prompt-development
examples or rows from the 599-post calibration material. Keep its exact order
and record:

- a stable cohort ID and selection seed;
- selection time, method, source revision, and exclusions;
- the candidate artifact SHA-256 and input/context fingerprints;
- raw and normalized source language;
- whether stored quote and local-parent context were available;
- whether the source post had one or several attributed brands.

Do not rebuild a candidate artifact from `PostBrandClassificationState`. That
table retains only the latest valid state. It cannot recover malformed provider
output or a classification replaced by a later run.

A useful starting sampling plan is 300 post-brand units, at least 30 units in
each required language or context slice, and at least 20 adjudicated positives
for every type and product label. These are planning targets to preregister for
the run, not application constants. If the frozen cohort misses a required
slice or has too few adjudicated positives, report the gap and block the
production recommendation instead of changing the threshold after seeing the
scores.

## Private review packet

Keep source text, context text, raw model output, and reviewer work outside the
repository, for example:

```text
~/.local/state/pushinweight-classification-evaluation/<cohort-id>/
  cohort.json
  candidate.json
  annotations/reviewer-a.json
  annotations/reviewer-b.json
  gold.json
  policy.json
  result.json
```

Only a redacted aggregate result and its artifact hashes belong in a dated
`docs/analysis/` receipt. Do not commit production text or raw context in a
test fixture.

The candidate artifact must identify its cohort, contract, taxonomy, prompt,
model, full source revision, and UTC candidate-generation time. Every candidate
row and gold row must carry the same 64-hex `input_context_fingerprint` for its
exact `(example_id, brand_id)` input envelope. A mismatch is an invalid
candidate coverage failure. Preserve invalid raw output as an invalid row; do
not drop it or manufacture a classification.

The gold artifact must declare `provenance.kind: heldout_gold` and
`provenance.gold: true`, identify the same cohort, list at least two independent
`annotators`, name a separate `adjudicator`, set `blind_to_candidate: true`, and
record its adjudication method, version, and UTC completion time. Synthetic,
analyst-calibration, missing-provenance, and structurally invalid artifacts are
rejected before scoring.

## Blinded annotation

Use two independent annotators. Show each annotator the source text and only
the stored quote or locally persisted parent context recorded in the frozen
packet. Do not show candidate output, fetch new context, or use network search.

Give both annotators the Product Contract and the examples in
`docs/reference/classifier-prompts.md`. Each annotation records:

- `outcome`: `classified` or `context_missing`;
- zero or more canonical product labels;
- one or more canonical post types for `classified`, with `other` exclusive;
- sentiment, or null when an independent judgment is unavailable;
- China and US nationalism, keeping explicit `none` separate from null;
- short evidence references and notes for uncertain boundaries.

A third adjudicator resolves every disagreement without deleting the two
original annotations. Retain exact-set and Jaccard agreement for the two
multi-label families and confusion matrices for outcome and scalar fields.
Weak annotator agreement is an evaluation finding; it must not be hidden by
adjudication.

## Score the frozen artifacts

Run the file-only management command after adjudication:

```bash
python manage.py evaluate_classifications \
  --candidate /absolute/path/to/candidate.json \
  --gold /absolute/path/to/gold.json \
  --policy /absolute/path/to/policy.json \
  --output /absolute/path/to/result.json
```

Omit `--policy` only for an exploratory score. Without a preregistered policy,
the result must remain `unassessed` and cannot recommend production.

The report keeps coverage separate from semantics:

- missing and invalid candidate rows are coverage failures and never enter a
  semantic denominator;
- outcome reports a `classified`/`context_missing` confusion matrix;
- types and products report per-label TP, FP, FN, precision, recall, F1,
  exact-set accuracy, Jaccard, and micro/macro summaries;
- products report empty-set accuracy and empty/non-empty confusion;
- sentiment and both nationalism axes report accuracy and confusion matrices;
- nationalism reports explicit `none` versus null-unknown errors;
- language and exact context-provenance slices show their own denominators;
- the support table separately counts multiple-type, empty-product, and
  multiple-product gold cases;
- every excluded low-support label or missing required slice is named.

An undefined precision, recall, F1, or accuracy has JSON value `null`. The only
special arithmetic case is Jaccard for two empty sets, which is `1.0`.

Scores describe this frozen cohort. If selection oversamples candidate-predicted
rare labels, do not present its unweighted overall score as population
prevalence or population accuracy. Compare candidate and incumbent outputs on
the same cohort when a comparable incumbent artifact exists.

## Preregister the decision policy

Keep product thresholds in `policy.json`, not application code. Policy schema
version 1 requires:

- a positive `min_support`, applied to every type, product label, required
  scalar value, and the multiple-type/empty-product/multiple-product cases;
- a positive `min_slice_support`, applied to EN, ZH-CN, JA and every required
  context slice;
- `required_contexts` containing at least `none`, `stored_quote`, and
  `local_parent`, with `stored_quote+local_parent` available as an additional
  exact slice;
- numeric `floors` from 0 through 1 for every required R17 metric path.

Required floors cover overall exact-set and micro F1 results, every type and
product-label F1, product empty-set accuracy, all four scalar accuracies,
outcome recall for `classified` and `context_missing`, recall for every
sentiment, and `none` and `unknown` recall on both nationalism axes. Additional
floors may target emitted paths under `all`, `by_language`, or `by_context`.
The evaluator rejects missing required floors and unknown policy fields, so a
partial policy cannot produce `pass`.

Generate a policy skeleton from the exact evaluator revision, then replace
every null before running it:

```bash
python - <<'PY' > /absolute/path/to/policy.json
import json
from core.classification_evaluation import REQUIRED_FLOOR_PATHS

print(json.dumps({
    "policy_version": 1,
    "min_support": 20,
    "min_slice_support": 30,
    "required_contexts": ["none", "stored_quote", "local_parent"],
    "floors": {path: None for path in sorted(REQUIRED_FLOOR_PATHS)},
}, indent=2, sort_keys=True))
PY
```

Record thresholds before candidate output is revealed to annotators. If the
run also compares an incumbent or uses confidence bounds, retain that method
and result beside the policy; evaluator schema v1 reports absolute candidate
floors and does not calculate a paired incumbent delta.

At minimum, production remains blocked when:

- candidate coverage is incomplete;
- any required label or EN, ZH-CN, or JA slice is under-supported;
- any structural invalidity is treated as a published judgment;
- a missing value is converted to `neutral`, `none`, `other`, or another
  fabricated default;
- a required type, product, sentiment, nationalism, or context-missing metric
  misses its preregistered floor;
- cohort, candidate, gold, prompt, taxonomy, model, or source identity cannot
  be reproduced.

A policy-bearing result also blocks when the evaluator runs from a dirty
worktree or cannot identify its exact Git revision. Exploratory runs without a
policy remain `unassessed`; missing slices still appear as warnings and support
counts.

R17 is complete only when the fresh cohort, original blinded annotations,
adjudicated gold, preregistered policy, deterministic result, disagreements,
and support table are retained together. Building or testing the evaluator
alone does not complete R17 and does not authorize production.

## Synthetic arithmetic fixture

The tracked fixture under `tests/fixtures/` exists only to prove metric
arithmetic, deterministic ordering, identity changes, strict provenance, and
safe failure behavior. It must declare `kind: synthetic` and `gold: false`.
Tests may derive an in-memory heldout-shaped document from it to exercise the
scorer, but no generated output may be cited as semantic-quality evidence.
