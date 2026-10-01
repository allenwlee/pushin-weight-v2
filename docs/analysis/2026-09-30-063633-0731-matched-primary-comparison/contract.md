# 0731 matched primary classification: answers versus confidence estimates

Date: 2026-09-30 UTC. Status: frozen before inference.

## Plain-English Summary

Give 0731 the exact saved source state, question instructions, and answer-option
definitions used by the Jev primary-classifier experiment. Compare compact
answers alone with compact answers plus self-reported probability distributions.
The answers-only version is the main accuracy comparison with Jev. The second
version checks whether eliciting confidence changes decisions or adds cost.

No application prompt, database, scheduler, deployment, or production setting
will change. Reuse eight saved cases (seven real posts and one synthetic control),
the revised reference answers, and the already completed Jev results. This is a
small development diagnostic, not an independent holdout or calibration study.

## Authorization and limits

Owner request: "do that test for 0731. can we also get probabilities from 0731?
is that reliable? will that corrupt the study?"

- Two independent eight-request arms, 16 physical model calls total maximum.
- Pinned model `deepseek-ai/DeepSeek-V4-Flash-0731`, direct DeepInfra.
- Model spend capped at US$0.05; no retries or model/provider fallback.
- Existing 0731 request profile: temperature 1, top_p 1, seed 42,
  reasoning_effort none; max_tokens 1024 in both arms. No explanations requested.
- One request per case per arm, alternating arm order by case, sequential.
- One isolated Render job using staging-harvest's managed DeepInfra credential.
  The suspended scheduler remains suspended; the job only performs these HTTPS
  requests and emits evidence. No Django imports or database connections.
- Model cost excludes Render job compute. Do not expose or retrieve the key.
- Stop on uncertain transport, HTTP error, missing credential, changed frozen
  artifacts, deadline, or exhausted budget. An invalid model answer is retained,
  scored as invalid, and does not trigger a retry or prevent the other cases.
- Record start before submission; an ambiguous submission is never resubmitted.

## Fixed evidence and comparison design

Use `../2026-09-30-060237-jev-primary-classifier/requests.json` for the exact
source state and questions, and that directory's cohort for expected answers.
For every new request, the user message is exactly the previous `state` and
`questions` objects, serialized as JSON. No prior answer, reference label, score,
explanation, case ID, or test outcome is supplied to either model arm.

Both arms have the same common system instructions and identical user content.
Only the system's output contract differs:

- A_labels: `answers` maps question IDs to boolean labels for Noul questions or
  option-name strings for Choice questions. No percentages or explanations.
- B_probabilities: each answer has `label` and `probabilities`. Boolean questions
  have true/false probabilities; Choice questions have all seven stance-option
  probabilities. Values run 0–1 and sum to 1. The label must agree with the
  distribution (binary >=0.50 is true; Choice label is a maximum).

This uses the same substantive question wording, but adapts the output request
to a text-generation API. It does not reproduce Jev's internal parallel question
processing. The sampling profile is held fixed between 0731 arms, but a single
paired run cannot separate a causal confidence-prompt effect from generation
variation. Previously saved Jev requests ran on the local host, while 0731 runs
on Render, so end-to-end timings have different network paths and warm/cache
conditions and are observational, not a controlled speed benchmark.

## Frozen scoring

- Exactly 22 scored fields per arm: 18 geo and four tracked-brand promotion.
- G03/G04 reporting=true in both arms, as fixed before the Jev primary run.
- G03 China pro remains the strict reference; separately report the predeclared
  sensitivity result excluding that one disputed stance-intensity field.
- US stance in G03/G04 remains unscored; record the answers and any defects.
- Strict accuracy requires a valid, consistent answer and the expected label.
  Invalid scored fields remain in the denominator and count as failures.
- Also report semantic-label accuracy independently of confidence formatting,
  all invalid answers, and posts where every scored field is correct.
- Compare paired A/B labels, recording improvements, regressions, and unchanged
  errors. Do not adjust questions, thresholds, reference labels, or output limits
  after seeing the responses. No further iterations are included.
- Percentages are elicited numeric estimates, not token log probabilities or
  demonstrated frequencies of correctness. Inspect confidence on mistakes;
  do not infer calibration from this eight-case set or fit a threshold on it.
- The existing Jev 21/22 comparison has one invalid, already-unscored US Choice
  answer; retain that limitation, and do not rerun Jev.

## Evidence and verification

Freeze all 16 payloads, source hashes, local runner and remote program before
submission. Provider-free fixtures verify label, probability, and inconsistency
parsing. Retain raw responses, usage, finish reasons, request durations, and
provider cost estimates. Recover job output with bounded small log pages, never
by repeating inference. Verify no more than 16 starts, matching successful
responses/accounting, exact input parity, and unchanged existing app/test files.

## References checked before inference

- [DeepInfra 0731 model and prices](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731):
  standard input US$0.06/M, output US$0.18/M, cached input US$0.015/M.
- [DeepInfra Chat Completions](https://docs.deepinfra.com/chat/overview).
- [Tian et al., Just Ask for Calibration](https://arxiv.org/abs/2305.14975):
  verbalized confidence was useful on other models/tasks; this is not evidence
  that 0731's estimates are calibrated for these classifications.
