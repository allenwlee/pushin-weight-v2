# Frozen matched comparison: 0731 multilingual classification

Date: 2026-09-30 UTC. Owner request: “run same test on 0731”.

## Plain-English Summary

Repeat the completed Jev full-taxonomy diagnostic with 0731, using the exact
same 117 posts, 38 questions, source/context/catalog inputs, fixed reference
answers, and 68 stored-English translation pairs. Jev is not rerun. No
application, database, scheduler, deployment, or production prompt changes.

The model returns labels and probability estimates, not extracted names,
handles, quotations, explanations, or event/job/personnel records. A separate
extractor remains assumed and untested. No corrected promotion target or
reference answer is supplied to 0731.

## Fixed comparison

- Source: `../2026-09-30-070427-jev-multilingual-classification/requests.json`.
  Each 0731 user message contains exactly that request's `state` and `questions`
  objects. JSON serialization is deterministic; semantic input parity is
  asserted per request. Model-specific API envelopes necessarily differ.
- Keep original order: 117 raw and 68 translated requests, 185 calls total.
  Same 20 JA, 19 ZH-CN, 20 KO, 20 EN, 19 ES, 19 TR posts. No new exclusions,
  replacements, source repair, live lookup, or translated-text changes.
- Reuse Jev's 34 binary and four fixed-choice reference fields unchanged:
  7,030 scored outputs, of which 4,446 belong to the original-text arm.
- Use the prior matched 0731 experiment's common system wrapper and
  `B_probabilities` output contract verbatim. Each answer has `label` and a
  complete `probabilities` map. No additional labels-only arm is included.
- Model `deepseek-ai/DeepSeek-V4-Flash-0731`, direct DeepInfra; temperature 1,
  top_p 1, seed 42, reasoning_effort none, standard service tier. These match
  the existing classifier request profile and prior comparison. Raise the
  output ceiling from the earlier five-question test's 1,024 to 4,096 tokens
  before inference because this request has 38 questions. No JSON-mode or
  schema-constrained decoding is added.
- The substantive questions stay unchanged even though the Jev results are
  now known. This tests the same design on another model; it is not a new
  optimized production 0731 prompt or a blinded independent replication.

## Scoring frozen before calls

- Reuse the same >=0.50 binary threshold and maximum-probability Choice rule.
  Probabilities must be finite 0–1 values, complete, sum to 1 within 0.015,
  and agree with the returned label. No repairs or threshold tuning.
- Reuse the prior pure 0731 probability parser and Jev's summary, consistency,
  and predeclared sensitivity functions. Keep valid siblings when an individual
  answer is invalid or absent. Extra answer/root keys are an operational
  defect, not a reason to erase otherwise valid fields. Unparseable JSON,
  duplicate object keys, non-stop completion or wrong provider model makes the
  response invalid. No partial-JSON salvage or Markdown stripping.
- Strict results count invalid fields as incorrect; separately show semantic
  label agreement where a usable label exists but probability format fails.
- Report per-language/family/label/stratum, positive precision/recall/F1,
  complete-post agreement, consistency defects, all disagreements, and paired
  Jev-versus-0731 wins/losses on identical fields. Compare translations only
  within the same 68 paired posts. Preserve the previous three sensitivity
  exclusions and report strict results first.
- 0731's percentages are self-reported estimates, not Jev-native probabilities,
  token log probabilities, or validated calibration. Report them descriptively;
  do not choose a production fallback threshold from this sample.
- The expected answers remain the main agent's pre-Jev source judgments,
  not independently adjudicated human truth. Balanced languages, coverage
  selection, sparse positive categories, one known official author, disputed
  class boundaries, incomplete translations, and one target brand per post
  retain all limitations in the [Jev contract](../2026-09-30-070427-jev-multilingual-classification/contract.md).

## Execution, cost and stopping

- Exactly one isolated Render job using staging-harvest's managed credential,
  service `crn-da7vrdqd0e5s739uvcs0`, smallest cron compute plan `plan-crn-003`.
  Verify the exact service is suspended and has no running/pending one-off job
  immediately before submission. Leave the scheduler suspended. No Django
  imports, database connections, credential extraction, or app writes.
- One request at a time, maximum 185 physical model calls, no retries or model
  fallback, US$0.50 model-cost ceiling, one-hour job deadline. HTTP timeout 45s.
  These guards are ceilings, not targets. Estimate/reserve conservatively before
  each call; use provider returned `estimated_cost` for actual reconciliation.
- Save/hash all payloads, this contract, local runner, remote program, reused
  helpers/reference files and protected app/test files before any model call.
  Provider-free fake-transport checks exercise model/request forwarding and
  response capture; no live probe or preliminary model call.
- Record submission intent before job creation. Uncertain submission stops;
  inspect the existing job, never resubmit speculatively. Remote logs capture
  each start and raw response before the next call. Recover logs without
  rerunning inference; retain raw log pages and decoded events locally.
- Stop submissions on missing credentials, HTTP/transport uncertainty, budget,
  deadline, unexpected model/accounting, or changed frozen inputs. Invalid
  classification answers are retained and do not cause a retry. Unfinished
  cases remain untested, not passes. No tuning/second iteration is authorized.
- Provider spend excludes Render compute. Timing compares 0731 on Render with
  previously observed Jev on the local host, so it is not a controlled network,
  cache, service-load, or production-throughput benchmark.

## Provider facts checked 2026-09-30

- [DeepInfra model/pricing](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731):
  standard input $0.06/M, cached input $0.015/M, output $0.18/M.
- [Chat API](https://docs.deepinfra.com/chat/overview) and
  [reasoning control](https://docs.deepinfra.com/chat/reasoning): explicit
  `reasoning_effort: none` and standard tier when service_tier is omitted.
- [Render one-off jobs](https://render.com/docs/one-off-jobs): a separate
  short-lived instance inherits the base service's build/environment. The
  injected program overrides its harvest start command; it runs no scheduler.
