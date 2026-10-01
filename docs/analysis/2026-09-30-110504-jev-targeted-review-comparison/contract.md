# Jev targeted-review comparison

Status: authorized; cohort frozen before paid calls.
Owner authorization: “let’s test both, on both the geopol and promotion issue”, followed by “budget increase approved” for up to 32 additional model calls and US$1. Prior ledger remains 37/40; this run has a separate approved ceiling. This overrides the earlier testing stop only for this bounded comparison.

## Question

Does a targeted Jev review catch unsupported brand-promotion and geopolitical assignments, and does seeing a short 0731-generated justification help?

## Frozen design

- Eight source-post/brand cases: four geopolitical, four promotion; seven saved real posts and one explicitly synthetic dual-promotion control. Two positive and two negative controls per issue. `cohort.json` owns the source text, provenance, and pre-run expectations. This is an enriched development diagnostic, not a population accuracy estimate or unseen holdout.
- DeepSeek baseline: original content-v5 and brand-v5 prompts currently restored in the analysis worktree, with no taxonomy changes. These are not the production content-v6 prompt. Snapshot the exact prompt bytes and requests before execution.
- DeepSeek justification arm: same inputs, slots, taxonomy, generation settings, role split, and output limit; add only a `decision_basis` map containing a short claim and verbatim source passages for promotion membership and geo/stance fields. This is a requested explanation, not a recovered internal thought trace.
- Four DeepSeek calls: two roles per arm, one eight-post batch. Use the real application's payload builder and existing parser for unchanged decision fields; validate experimental basis separately. This is not a production write path.
- Jev A: baseline labels, targeted review, no basis.
- Jev B: justification-arm labels, targeted review, basis visible.
- Jev C (control): the SAME justification-arm labels, targeted review, basis hidden. B versus C isolates showing the explanation; baseline versus justification-arm 0731 labels measures the separate effect of requesting it.
- Exactly one Jev request per source case per arm: 24 planned requests. Each request checks all applicable fields together against the complete frozen source/context. No other case, reference label, rubric, old model result, or aggregate score enters the request. Candidate judgments and basis are explicitly untrusted claims, not instructions.
- Total: 28 planned physical calls; at most 32 including failures/retries. No additional variants, prompt tuning, or repeated best-of selection.

## Scoring fixed before inference

- Count source posts and reviewed fields separately. Primary error types: approving an incorrect assignment; rejecting a correct assignment; uncertain review; missing/invalid output. Do not collapse uncertainty or failure into `none` or a pass.
- Jev is a verifier: a Noul probability >=0.80 approves a proposed field judgment, <=0.20 rejects it, and the middle abstains. These are predeclared operating thresholds, not established calibrated correctness probabilities for this task. No post-hoc threshold tuning.
- Promotion: evaluate presence/absence of advertising_marketing for the specified tracked brand (four fields). Beneficiary ownership is in scope; inferring missing publisher affiliation is not.
- Geo: verify membership of reporting/framework/nationalism individually and each reviewed country's exact stance (18 fields: five each for G01/G02, four each for G03/G04). US stance in the latter two is deliberately unscored. Also report exact per-post geo output against the reviewed expectations.
- Explanations must use source-visible quotes, short nonempty claims, and exact field/slot coverage. Invalid evidence is reported separately and is not repaired or scored as successful review.
- Preserve both original reported failures explicitly. If a fresh 0731 run does not repeat a historical mistake, say so; it is not evidence that Jev repaired that historic assignment.
- An option is only promising on this cohort if it reduces false approvals without increasing rejection/holding of correct positive controls. No deployment or general-quality conclusion from eight examples.

## Safety, resource limits, and stopping

- Existing dirty application/test files are read-only evidence and remain untouched. All new files stay in this experiment directory. No new branch, commit, PR, deployment, production/database write, cron change, or X call.
- One provider request at a time. Direct DeepInfra 0731 and direct TypeSafe `jev-1.13.0` only; no fallback. DeepInfra calls may run in an isolated staging one-off process to use its existing credentials without exporting secrets. Jev uses the already available local credential.
- Record exact request, model, raw response, timestamps, usage, latency, and prompt/source hashes durably before interpreting results or starting the next call. Never print or persist credentials.
- Hard new-model ceiling US$1; reserve US$0.50 for DeepInfra and US$0.45 for Jev, leaving US$0.05 unallocated. Conservative reservations precede network calls. Retain the reservation when an error lacks billed usage; never count unknown cost as zero. Stop on unknown transport completion, identity drift, malformed usage, or exceeding a reservation.
- No DeepInfra retries. Jev permits at most one retry of an explicit HTTP 429/529, after backoff, only while the four-call global spare and dollar ceiling remain. No retry for timeouts, schema/model mismatch, or other failures.
- Stop after this one frozen comparison, budget exhaustion, an unsafe/unresolved transport state, or user interruption. Unused allowance is not a reason for another experiment.

## Current provider documentation checked 2026-09-30

- [TypeSafe API](https://docs.typesafe.ai/api): typed question map and `noul` answer schema.
- [TypeSafe models](https://docs.typesafe.ai/models): pinned Jev identity and US$0.042/M input-token list price; output free. Report list-price estimates separately from provider-billed dollars.
- [DeepInfra 0731](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731): standard US$0.06/M input and US$0.18/M output. Retain provider reported cost and input/output overhead by arm.

## Constraints and limitations

The two new full-role classifier calls per arm are not a replay of the historical production batch. The G04 source originally appeared under a MiniMax decision slot; this experiment deliberately targets visibly mentioned DeepSeek. Labels are pre-run main-agent reviews or existing development controls, not newly owner-adjudicated gold. No claim of independent model errors, population precision/recall, or stable latency follows from this run.
