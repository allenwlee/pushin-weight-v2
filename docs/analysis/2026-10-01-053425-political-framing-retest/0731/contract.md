# 0731 arm: political-framing prompt retest

This directory contains the isolated DeepSeek V4 Flash 0731 arm for the shared
2026-10-01 political-framing retest. The shared parent directory owns the
frozen cases, revised questions, reference labels, common protocol, and shared
hashes. This arm changes only the model endpoint and uses the agreed political
question wording supplied in those shared inputs.

## Frozen model request

- Model: `deepseek-ai/DeepSeek-V4-Flash-0731`, direct DeepInfra chat API.
- Wrapper: the earlier matched comparison's `B_probabilities` system text,
  byte for byte.
- Profile: temperature 1, top_p 1, seed 42, reasoning_effort `none`,
  `max_tokens` 4096, standard service tier (omitted provider field).
- Input: exactly 117 original-text cases, all 38 revised questions, and the
  complete per-case state from the shared frozen input. No translation arm,
  JSON-mode change, output-format change, repair, or retry.
- The serialized DeepInfra user message contains exactly `state` and
  `questions`; a digest is recorded for every request and compared to the
  shared input digest.

## Bounds and transport

- At most 117 physical provider calls, sequentially, with 45-second HTTP
  timeouts and a 3,600-second overall worker deadline.
- Provider spend is capped at US$0.25. Before each call, reserve the full
  4,096-token output ceiling and a conservative two input tokens per body
  byte. Stop before starting if the next reservation exceeds the remaining
  cap. Reconcile actual spend from returned usage.
- Use the existing suspended staging-harvest cron only as the base service
  for one isolated Render one-off job on `plan-crn-003`. Confirm the exact
  service remains suspended and every existing one-off is terminal before
  job creation. Do not change service state or configuration.
- The job reads `DEEPINFRA_API_KEY` only from its inherited Render runtime
  environment; it emits only whether the credential is present. No Django,
  database, Twitter/X, app writes, or scheduler execution is in this runner.
- Record the submission intent before creating the job. If submission status
  is uncertain, inspect that job and never submit again. The worker appends
  start, raw finished, and accounting events to logs before moving on. It
  explicitly records unavailable accounting for malformed or empty HTTP
  bodies. Recover those logs; never rerun inference to fill gaps.

## Validation and reporting

- Reuse the prior pure probability parser and freeze its source digest.
- A valid answer has a boolean yes/no label or a listed Choice label,
  complete finite probabilities in `[0,1]`, sum within 0.015 of one, and a
  label consistent with the probabilities. Invalid outputs remain visible and
  count incorrect; usable labels with invalid probabilities are separately
  reported as semantic-label agreement.
- Preserve valid sibling answers when another field is missing or invalid.
  Malformed JSON, duplicate keys, wrong model, or non-stop completion makes
  the response invalid. Extra keys are recorded as response defects. No
  partial-JSON salvage, Markdown stripping, or retries.
- Verify the shared and local frozen hashes before and after the run. Report
  exact scored counts, invalid outputs, disagreements, per-language/family/
  stratum results, model cost, and timing. The result is a diagnostic model
  comparison, not a production prompt or calibration recommendation.
