# Political wording retest: Jev and 0731

Date: 2026-10-01 UTC. Status: protocol frozen before inference.
Owner request: “ok let's try that on jev and 0731. use separate subagents using faster model”.

## Plain-English Summary

Repeat the original-text part of the completed multilingual test on both
classifiers. Keep the same 117 posts, all 38 questions, supplied context,
reference labels, output contracts, and thresholds. Change only the three
geo-mode instructions: call the category political, and replace the framework
definition with the wording discussed with the owner. This isolates a small
prompt revision without also shrinking the question set or changing output
formatting. There is no translation arm or additional extraction model.

Two GPT-6 Luna subagents prepare and operate the separate provider arms; the
classifiers remain pinned Jev 1.13 and DeepSeek V4 Flash 0731. The parent owns
the common inputs, acceptance rules, reconciliation, and final comparison.
No application, database, collection, scheduler, deployment, or production
prompt changes are authorized. Existing dirty worktree changes are preserved.

## Exact instruction revision

Keep the common source/brand preamble and existing shared geo exclusions
verbatim. Keep all output field names, criteria, and reference labels unchanged.

- In `geo:reporting`, change `geopolitical mode` to `political mode` and
  `a geopolitical claim` to `a political claim`.
- In `geo:nationalism`, change `geopolitical mode` to `political mode` only.
- In `geo:framework`, replace the old two-sentence question/definition with:

> Does political mode framework apply? Does the post explain or predict relationships between countries, or how governments and political systems shape policy, markets, or national security?

  Immediately after that, add the agreed boundary:

> The post itself must supply the political connection. Ordinary company competition, product comparisons, or technical discussion alone do not qualify.

The new positive-boundary sentences apply to framework, the definition being
revised, not as a new government-policy requirement for nationalism. Reporting
and nationalism retain their definitions apart from the explicit terminology
changes above. The old shared exclusions remain after the revised framework
text. `prompt-diff.json` records old/new full question objects for all three.

## Fixed input, baseline, and scoring

- Filter `../2026-09-30-070427-jev-multilingual-classification/requests.json`
  to the original 117 `raw` requests, preserving their order and every state
  object exactly. Same JA20, ZH-CN19, KO20, EN20, ES19, TR19 cases.
- Reuse the old `references.json` byte-for-byte. The references are the main
  agent's original source judgments, not independent human adjudication.
- Preserve the original 38-question set; the other 35 questions are identical.
  Each arm receives the same revised state/questions. Do not send reference
  labels, old model answers, or review notes to either provider.
- Jev: `jev-1.13.0`, native Noul/Choice API; >=0.50 means binary present;
  Choice selects a maximum-probability option. Reuse existing strict validator.
- 0731: `deepseek-ai/DeepSeek-V4-Flash-0731`, DeepInfra standard tier,
  temperature1, top_p1, seed42, reasoning_effort none, max_tokens4096.
  Reuse the exact prior `B_probabilities` wrapper and validators. Do not add
  JSON mode, schema decoding, formatting repairs, or a labels-only arm.
- Invalid fields count as unsuccessful in the main score and are separately
  reported. Preserve valid sibling answers and all raw failed outputs. Keep
  original sensitivity exclusions as a secondary view, without new exclusions.
- Primary comparison: geo true positives, false positives, false negatives,
  invalid fields, exact three-mode matches per post, and paired errors corrected
  versus correct answers broken relative to each model's old raw results.
  Report all 38 fields as secondary context and separate output failures from
  valid disagreements. Never silently remove old-invalid/new-valid differences.
- Directional success means fewer total unsuccessful geo fields than that
  model's old result; also report positive detection losses so an all-no result
  cannot be presented as a useful solution. No production acceptance is granted.
- This is a post-feedback single rerun on a known cohort, not a fresh blinded
  test, a calibrated confidence study, or proof of a causal effect independent
  of model variability or service changes. No contemporaneous old-prompt arm.

## Execution and safety limits

- Maximum 117 physical inference calls per provider, 234 combined. One call
  at a time per provider; the two different provider arms may overlap.
- Maximum USD0.25 model spend per provider, USD0.50 combined. Reserve a
  conservative amount before each request; account for uncertainty on failure.
  Model spend excludes any Render one-off compute.
- Exactly one pass; no retries, preliminary model probes, prompt tuning,
  replacement cases, or automatic model fallback. A 3600-second wall-clock
  deadline per arm and bounded network timeouts apply.
- Stop on missing credentials, unexpected accounting/model, transport or
  submission uncertainty, HTTP error, exhausted budget/deadline, or changed
  frozen inputs. Invalid classification output is recorded, never retried.
- Freeze common inputs, reference and baseline hashes, and protected files
  before calls. Each agent additionally freezes its runner and reused helper
  hashes in its own directory, after provider-free transport/parser checks.
- Secrets stay in existing untracked local stores/environment or Render-managed
  environment. Never print, log, persist, or move secret values between hosts.
- Jev may use the previously authorized local TypeSafe credential. 0731 may
  use the existing local credential if already available, otherwise the prior
  isolated one-off Render workflow. Verify service identity, suspension, and
  absence of another running/pending job before submission; do not alter the
  service. A busy service is not permission to interfere with another task.
- Save each intent/raw response/accounting record append-only before another
  inference call. Capture partial runs and count untested cases as untested.
- No live X or database queries, no Django imports or application writes, no
  cron runs, pause/resume, deployment, Git mutation, or deletion of artifacts.

## Evidence and provider facts checked 2026-10-01

- [TypeSafe models](https://docs.typesafe.ai/models): `jev-1.13.0`, USD0.042/M
  input tokens, output tokens unbilled; native `/v1/systemone` endpoint.
- [DeepInfra 0731](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731):
  standard USD0.06/M input, USD0.015/M cached input, USD0.18/M output.
- Historical comparators: the two 2026-09-30 multilingual reports and immutable
  receipt/score files remain untouched. Their medians are not promises for this
  run, and cross-provider timing on different hosts is not a controlled benchmark.

## Done

Both arms terminate within their limits; every started request is reconciled
to captured response/error/accounting evidence; raw results and output defects
are reported separately; hashes and unchanged service/app state are checked;
the parent provides the paired old/new geo comparison and limits. Failure to
complete an arm is reported honestly, not repaired by an unapproved second pass.
