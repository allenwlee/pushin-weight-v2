---
title: Shared post interpretation — bounded experiment
status: historical-experiment-closed
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: experiment-post-interpretation-2026-09-29-014716
  branch: experiment/post-interpretation
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Shared post interpretation — bounded experiment

**Archived October 1, 2026:** The research ended with the owner's decision to
keep 0731 for classification. Read the
[final closeout](../analysis/2026-10-01-193945-jev-classification-closeout.md)
before the historical requirements below. Old budgets, next steps and the
generated worktree guide are evidence of the experiment's original scope,
not permission to resume tests, inference, deployment or the rejected design.
The later commit/push request covers documentation and evidence only; its
[publication record](2026-10-01-104958-docs-jev-classification-closeout-plan.md)
is separate from this completed experiment.

## Plain-English Summary

Test whether identifying entities, their roles, attributed claims, and calls to
action before classification improves advertising ownership and other judgments.
Compare the same posts with and without the model-generated interpretation.
Also inspect its usefulness for commentary, literal translation, and a short
source-grounded headline; those three are exploratory probes, not production
pipeline acceptance. The owner explicitly accepts the risk of an incorrect
interpretation and authorized this experiment on 2026-09-29.

Use the existing DeepSeek V4 Flash 0731 route. Save raw responses, compare
matched inputs, count invalid outputs as failures, and report added cost and
latency. This branch contains experiment code and evidence only; the quality
candidate and next-UI draft stay at their existing revisions.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/experiment/post-interpretation`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/experiment/post-interpretation/docs/plans/2026-09-29-014716-experiment-post-interpretation-plan.md`
- Change: `experiment-post-interpretation-2026-09-29-014716`
- Branch: `experiment/post-interpretation`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/experiment/post-interpretation/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/experiment/post-interpretation/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`
- Delivery route: `staged`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

The owner instructed "stop running tests" during the prompt rollback
discussion. Do not run further automated software tests or reopen the skipped
PostgreSQL checks. Historical test receipts remain historical; the waiver is
not a passed check. The later authorization to separate and evaluate promotion
targets permits the bounded model experiment below, not software-test runs,
deployment or publisher-affiliation research.

## Goal

Answer whether a reusable, source-grounded interpretation improves downstream
ownership and attribution enough to justify a larger implementation trial.

## Product Contract

### Frozen experiment contract

- Base revision: `1edbc3adaa19b370498ef0fbb026319fc676d397`.
- Cohort: all ten existing `u18a_label_owner_regressions_v1.json` cases plus
  five visibly synthetic controls: comparison, quoted criticism, unresolved
  pronoun, concrete release, and mixed praise/criticism. These are development
  examples, not a blinded or representative accuracy sample.
- Three fixed batches of five. Each batch uses two existing classifier calls
  for the baseline, one interpretation call, two classifier calls supplied
  with that interpretation, and two matched cross-task probes: 21 calls.
- Retain the same source, model, generation settings, classifier prompts,
  parsers, batch composition, and input order between classifier arms. The
  treatment appends only a derived-interpretation field and a short instruction
  to consult it while retaining source authority. No reference answers or
  taxonomy expectations enter the interpretation prompt.
- Use `classify_batch_pragmatics_full` with captured request/response transport;
  do not clone the classifier. Classification evidence remains experimental,
  even though its embedded lineage names the existing v6 prompt.
- The interpretation records multiple entities/roles, attributed claims,
  calls to action with offering/provider, supporting verbatim source text, and
  uncertainty. Validate evidence quotes and shape before reuse. Invalid
  interpretations are explicit failures; do not silently repair them.
- Each secondary probe emits English commentary, literal Japanese translation,
  and a concise English headline using a shared frozen prompt. It tests reuse,
  not the production commentary model or aggregate headline workflow.

### Budgets and stop rules

- Prior work consumed 13 of 40 authorized calls; this experiment may consume
  at most 27 more, including failures. Planned calls: 21; six reserved for one
  documented follow-up selected after reviewing the paired result.
- Prior reported classifier cost: $0.000918; reserve $0.05 for the earlier
  translator. New experiment hard cap: $5, comfortably inside the $10 total.
- One provider call at a time; no automatic transport retries. Reserve the
  next call using a conservative $20/million input/output-token bound, then
  account reported usage. Unknown cost or transport completion stops paid work.
- Official DeepInfra model page checked 2026-09-29: standard input $0.06/M,
  output $0.18/M. Keep the existing profile and explicit model; do not change
  pricing, service tier, provider, or credentials.
- Execute as one isolated one-off job using the already configured staging
  harvest service credentials. Do not resume its scheduler, deploy code,
  query/write application data, fetch X posts, or change environment settings.
- Stream compressed evidence records into the job logs and collect them into
  this worktree, including raw provider envelopes and request hashes.

### Fixed scoring and decision

- Primary: existing ownership boundary checks (tracked advertising, untracked
  promotion category, promoted subject) for all ten original cases. Report
  validity separately and count invalid results as failed acceptance.
- Secondary: comparison target, quoted-speaker attribution, unresolved identity,
  release ownership, and complaint/praise target on the five new controls.
- Interpretation review: correct role assignments, no unsupported entity or
  claim, accurate quotation ownership, explicit uncertainty where needed.
- Probe review: no ownership transfer, quotation adoption, invented release,
  invented identity, or claim-to-fact conversion in any of the three outputs.
- Advance only if original-case ownership improves, direct-ad/co-promotion
  positives do not regress, and the broader controls show no critical new
  attribution errors. A miss or invalid response is reported, not redefined.
- This is one candidate, one paired run. No open-ended tuning campaign.

### Regression net and deliverables

- Offline transport tests pin the real classifier caller, interpretation
  injection in both roles, original source retention, no reference-answer
  leakage, and quote validation. Budget tests pin pre-call rejection.
- Save cohort, prompt text/hashes, source revision, call ledger, raw provider
  replies, parsed results, per-case scoring, reviewer notes, and final report.
- Finish with the experiment result and recommendation; implementation and
  deployment of a shared interpretation stage remain a later task.

### Observed run and bounded follow-up (2026-09-29)

Initial run completed with 15 calls, $0.00300834 reported cost, and no unknown
usage. Batches 1 and 2 were withheld from candidate classification because
their interpretations contained respectively one paraphrased supporting quote
and two whitespace-normalized quotes. The strict result remains recorded as
failed admission, including the whole-batch consequence. Batch 3 completed both
arms and both probes; its GLM-versus-B.AI complaint attribution improved while
the Token Machine tracked-advertising errors remained.

One six-call diagnostic follow-up reuses the exact unedited interpretations
for batches 1 and 2, bypassing only their quote-admission failure, with original
source still provided. No model prompt, entity, claim, or reference judgment is
edited. This distinguishes extraction/citation reliability from downstream
usefulness under the owner's accepted interpretation risk. It is explicitly
not a pass of the original strict experiment. Two classifier calls and one
candidate probe per batch; reuse their original baselines. Aggregate task calls
will be at most 34/40. Do not spend the remaining six without a new experimental
question or scope. Preserve all previous results and separate follow-up receipts.

### Completed result (2026-09-29)

Both jobs succeeded. Initial 15 plus diagnostic six calls consumed 21 new calls,
$0.00447816 reported model cost, 40,472 input tokens and 13,564 output tokens.
Task total is 34/40 calls; six remain unused. No deployment or application data
write. Eight offline harness tests passed.

The complete diagnostic comparison has 15 valid results in each arm. Original
ownership boundaries remained 3/10; tracked-ad decisions worsened 4/10 to 3/10;
untracked-promotion categories improved 5/10 to 9/10. All three direct-ad and
co-promotion positives stayed correct. Broader fixed controls improved 4/5 to
5/5 by separating GLM praise from B.AI's billing complaint. The strict run's
ten withheld candidates remain failures, not retroactively repaired passes.

Decision: experiment complete; candidate does not meet advancement criteria.
The interpreter sometimes omits the owner, and the classifier also sometimes
ignores a correctly identified provider. Do not infer broad architectural
failure from this small, unreplicated development sample. Do not spend the
remaining calls or deploy from this artifact without a new authorized task.

Full evidence, limitations and next-test recommendation:
`docs/analysis/2026-09-29-014716-post-interpretation-experiment/report.md`.

### Owner-requested prompt rollback (2026-09-29)

After discussing the failed experiment, the owner requested removal of the
long advertising/marketing addition and the relevant prompt sections verbatim.
Scope: restore only the exact advertising definition preceding `76bf81d` in
this active experiment branch; preserve all other prompt wording, the generic
interpretation experiment, frozen source evidence, saved results, and the
separate staged quality candidate. No provider calls, database changes,
commit/push or deployment are part of this local rollback.

The restored prompt is byte-identical to the pre-addition prompt module.
Select the corresponding content/merge v5 lineage rather than mislabelling the
restored wording v6; continue accepting historical v6 receipts. Do not rewrite
historical evaluation manifests or treat their v6 scores as v5 measurements.

Regression net: capture the actual `classify_batch_pragmatics_full` caller's
content prompt and assert the complete restored definition plus absence of
the removed named examples; pin the selected v5 trace and historical v6
compatibility. The two targeted assertions failed before the rollback.
Run selected-route, two-role, contract, persistence and experiment-harness
tests afterward; report any unavailable database verification separately.

Verification: 74 tests passed, seven required PostgreSQL tests skipped because
`DATABASE_URL` is unset; the combined run correctly reports incomplete rather
than green. The new caller-level rollback pin and restored-lineage pin both
pass. `git diff 76bf81d^ -- x_monitor/classifier_0731_prompts.py` is empty,
proving the complete prompt module matches the pre-addition version. No live
health check was used as proof of this undeployed local change.

### Promotion-target-only experiment — authorized 2026-09-29

The owner clarified two separate decisions: first identify every promoted
brand/offering from the post; only afterward use the promoter's relationship
to assign UP/AM/OR. This unit implements/evaluates only the first decision.
The old advertising-label score is not a target-identification score and is
not reused as this unit's reference.

- Preserve the rollback, old prompts/receipts, classifier runtime, UI and all
  application data. Extend the isolated experiment harness only.
- Same fifteen source posts, batch composition, DeepSeek 0731 direct provider
  and generation settings. Three sequential calls; no retries or tuning loop.
  New maximum $1; prior task calls 34/40, resulting maximum 37/40. Existing
  pre-call reservation and unknown-usage stop remain active.
- Model input is only source/context; no prior interpretation, tracked-brand
  list, author identity/affiliation, reference targets or expected labels.
- Output explicit promoted `targets` with offering/evidence/reason, separate
  `other_mentions` with role/evidence, and uncertainty. Multiple targets are
  allowed. Publisher classification is recorded separately as not evaluated;
  no UP/AM/OR outputs are requested or inferred.
- Freeze twelve clear-case expectations and three separately displayed
  judgment boundaries in `target_manifest()` before calling the provider.
  Token Machine references are not automatically model promotion; retain both
  offerings in the co-promotion control. Do not invent targets in neutral,
  quoted-criticism or unresolved-reference controls. B.AI/GLM, personal model
  preference and praise/complaint remain explicitly reviewed boundaries, not
  silently scored against the old author-blind advertising answers.
- Separate target accuracy from exact naming/identity resolution and quote
  fidelity. Short URL to B.AI is not a verified mapping in the supplied source.
  These are assistant-authored development expectations, not owner-labelled
  independent ground truth. Preserve every output for inspection.
- Execute through the existing one-off staging credential route without
  scheduler, service/environment or database changes. Validate only the
  unchanged transport/config/fixture runtime hashes because this experiment
  does not execute the restored classifier prompt.
- No pytest, database verification, new test files, production health checks,
  commit/push or deployment. Manual inspection of model output and durable
  raw request/response receipts completes this experimental unit.

Target-only result: three calls completed for $0.00062286 reported model cost;
task total 37/40. Manual target review matched 11/12 frozen clear-case
expectations; factual release/hosting news was overcalled as promotion. All
six Token Machine targets and both offerings in the co-promotion were retained.
B.AI/GLM, preference and mixed praise/complaint outputs remain separately
reported judgment boundaries, not scored as advertising errors. Exact shape
passed only 4/15 rows (unrequested explanatory fields); two supporting quotes
were not verbatim. No repairs or software tests were run. The second-stage
publisher classification is explicitly not evaluated. This is not a deployment
candidate. Evidence and limitations:
`docs/analysis/2026-09-29-014716-post-interpretation-experiment/targets-only/report.md`.
