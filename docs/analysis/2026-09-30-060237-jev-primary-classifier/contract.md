# Jev as primary classifier: frozen diagnostic contract

Date: 2026-09-30 (UTC). Scope: one bounded experiment, not a production change.

## Plain-English Summary

Ask Jev to classify the same eight saved post/brand cases independently, without
0731's assignments or explanations. Measure tracked-brand advertising membership
and geopolitical modes/national stances, not the entire application taxonomy.
No live X retrieval, new translations, 0731 calls, database writes, scheduler
changes, application edits, or deployment are included.

This reuses a small, repeatedly inspected development set, not an independent
holdout. Seven cases are real saved posts; one dual-promotion case is synthetic.
The expected answers are agent-reviewed judgments, not independently established
truth. Accuracy and confidence calibration across production are not established.

## Authorization and limits

Owner request: "let's do another test. this time, make jev the primary classifier.
and see what it's accuracy is."

- Model: `jev-1.13.0`, direct `https://api.typesafe.ai/v1/systemone`.
- Eight physical requests maximum: one per case; sequential; no retries.
- US$0.02 model-spend ceiling. Stop on transport uncertainty, HTTP failure,
  malformed response, insufficient credential, changed frozen inputs, or budget.
- Reuse the local `TYPESAFE_API_KEY`; never print or save its value.
- Use append-only start/response/accounting receipts. Never resubmit a case.
- The existing dirty application/test files are outside this task and preserved.

## Evidence and expected answers, fixed before inference

Source: `../2026-09-30-110504-jev-targeted-review-comparison/cohort.json`.
Reuse source text, supplied translations, context, public account handle,
affiliations, and target brand exactly. Do not send case IDs, post IDs, expected
answers, scoring rubrics, previous predictions, or prior explanations to Jev.

Retain every prior expected answer except these two explicit corrections,
discussed before this run:

- G03: include `reporting` alongside `framework` and `nationalism`; the post
  attributes geopolitical claims/proposals before advancing its own argument.
- G04: include `reporting` alongside `framework` and `nationalism`; the post
  attributes Trump's geopolitical position before advancing its own argument.

These corrections are the main agent's consistent application of coexisting
modes, not a claim that the owner independently adjudicated every label.
Keep G03 China `pro` as the strict expected stance. Separately report a
predeclared sensitivity result excluding that one disputed intensity field.
US stances in G03/G04 remain unscored, as in the prior experiment.

## Questions and scoring

- Promotion: one direct Noul question per case asking whether the supplied
  source promotes the tracked brand's own offering. Retain the earlier
  provider/beneficiary distinction and allow explicit dual promotion.
- Geo: three independent Noul questions for reporting/framework/nationalism,
  plus one seven-option Choice question for each country's exact stance.
- Preserve the prior definitions and explicitly state that geo modes can
  coexist, as the original 0731 prompt already does. Add no case-specific hints.
- Noul: probability >= 0.50 means the label is present, otherwise absent.
- Choice: select the highest-probability option; preserve the provider's
  selected option on a tie. A multi-option choice need not exceed 50%.
- Record raw probabilities, Choice distribution/confidence, and any internal
  inconsistency. Do not repair answers or force stance/mode consistency.
- Score 18 geo fields and four promotion fields (22 total); also count posts
  where every scored field is correct. The 24 returned answers include the two
  intentionally unscored US stances. Missing/invalid answers are not passes.
- Compare with saved baseline 0731 and the saved label-only Jev reviews at 50%,
  rescoring both against these same corrected references. Do not call 0731.
- Do not tune thresholds/questions/answers after seeing results. End after
  this run, regardless of accuracy. Preserve the old experiment unmodified.

## Verification and reporting

Before inference, freeze source/request/contract/runner/comparator hashes and
check that model requests contain only the allowed evidence. Validate both
Noul and Choice parsing with provider-free fixtures. Afterward verify complete
receipts, hashes, eight-or-fewer physical starts, cost accounting, and unchanged
application/test files. Report all incorrect predictions and their percentages.

Latency and cost are observations for this run, not an equal-workload comparison
with 0731: the previous 0731 calls covered more classification fields. This test
also differs from reviewing supplied assignments; it does not isolate only a
model change or establish that a particular internal mechanism caused results.

## Provider contract checked before inference

Official documentation checked 2026-09-30:

- [Noul request/response](https://docs.typesafe.ai/primitives/noul).
- [Choice request/response](https://docs.typesafe.ai/primitives/choice): `criteria`
  supplies options; response includes `choice`, `probabilities`, and `confidence`.
- [Model and pricing](https://docs.typesafe.ai/models): pinned `jev-1.13.0`,
  US$0.042 per million input tokens; output tokens free. Cost is a list-price
  estimate from returned usage, not a provider invoice.
