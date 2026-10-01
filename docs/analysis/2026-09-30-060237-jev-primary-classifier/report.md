# Jev primary classifier: 21/22 scored decisions, one borderline promotion error

Date: 2026-09-30. Status: completed; eight physical calls, no retries.

## Result

Jev classified the saved source material without seeing 0731's assignments or
explanations. Against the expected answers frozen before this run, it got
**21/22 scored fields correct (95.5%)**, and every scored field correct on
**7/8 posts**. The only scored error was Token Machine/Qwen advertising at 51%.

This covers geopolitical modes/national stances and tracked-brand advertising
membership only, not all application classifications. The set has seven real
posts and one synthetic case. It was repeatedly inspected during development;
this is not a holdout or a production accuracy estimate.

The comparison below uses the same corrected reference labels for every column.
Earlier results are reused; no new 0731 calls were made.

| Scored fields | Saved 0731 baseline | Saved 0731 + Jev review at 50% | Jev primary |
| --- | ---: | ---: | ---: |
| Geopolitics | 16/18 | 16/18 | **18/18** |
| Promotion | 1/4 | 3/4 | **3/4** |
| Combined | 17/22 (77.3%) | 19/22 (86.4%) | **21/22 (95.5%)** |
| Posts with every scored field correct | 4/8 | 5/8 | **7/8** |

Jev primary has four more correct fields than the saved 0731 baseline and two
more than the saved reviewer approach. This is not an equal-prompt model
benchmark: the prior 0731 calls covered more fields, and the primary Jev questions
ask for labels directly rather than verifying offered assignments.

## Promotion: all four results

Here the percentage is directly the probability that the target brand's own
offering is being promoted. It is **not** support for a previous model's answer.
The fixed rule is present at >=50%, absent below 50%.

| Case and target | P(target-brand advertising) | Jev decision | Expected | Result |
| --- | ---: | --- | --- | --- |
| P01: B.AI guide mentioning GLM; target GLM | 25% | No | No | Correct |
| P02: Token Machine prizes involving Qwen; target Qwen | 51% | Yes | No | Incorrect |
| P03: official Qwen announcement with "Try it now"; target Qwen | 94% | Yes | Yes | Correct |
| P04: explicit DeepSeek API + Token Machine co-promotion; target DeepSeek; synthetic | 76% | Yes | Yes | Correct |

The one error barely crosses the frozen cutoff, by one percentage point. No
threshold was adjusted after observing it. This does not establish that 0731
would resolve the uncertain case: the saved 0731 baseline also got P02 wrong.

## Geopolitics: all scored probabilities

Mode columns show probability **the mode is present**, not confidence in an
absence. Stance columns show the selected label and its option probability.

| Case | Reporting | Framework | Nationalism | China stance | US stance | Correct scored fields |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| G01: original GLM/Anthropic company-criticism complaint | 6% | 7% | 4% | none, 99% | none, 100% | 5/5 |
| G02: DeepSeek praise and criticism of competitors | 27% | 19% | 10% | none, 100% | none, 100% | 5/5 |
| G03: defense of Chinese innovation against theft accusations | 76% | 92% | 86% | pro, 96% | **Invalid; unscored** | 4/4 |
| G04: criticism of China's political system and AI industry | 78% | 95% | 94% | anti, 99% | anti, 83%; unscored | 4/4 |

G03 and G04 both include reporting in the new references because they attribute
geopolitical positions as well as advancing their own arguments. These two
corrections were recorded before this run; the earlier experiment is unchanged.
The reported 100% values are model outputs, not guarantees of truth.

G03's `pro` versus `mild_pro` boundary was flagged as subjective before inference.
The strict result includes it and Jev chose the expected `pro`. The predeclared
sensitivity result excluding that field is 20/21 combined, with geo 17/17.

US stance on G03 and G04 was excluded before both this run and the preceding
experiment. We have not adjudicated these outputs as correct; neither is
included in the 18/18 geopolitical result.

## Provider-output inconsistency and explicit continuation

G03's US Choice returned `choice=anti`, but its distribution gave anti 31% and
pro 32%. The selected label was not the highest-probability option, contrary to
the [documented Choice contract](https://docs.typesafe.ai/primitives/choice).

The initial validator stopped after three calls. Before sending the remaining
five, [a continuation record](continuation.md) froze a field-local validation
policy: preserve invalid answers as invalid, never repair their labels, count
invalid scored answers as failures, and continue only unsubmitted cases. No
question, reference answer, cutoff, or existing response was changed. No case
was retried. The inconsistency concerned an already-unscored field, so the
scored denominator remained 22, rather than being reduced after seeing results.

There were **23 valid answers out of 24**, across **seven wholly valid responses
out of eight**. All 22 scored answers were valid. There were no detected
directional-stance-without-nationalism inconsistencies among valid answers.

This output-contract defect matters independently of accuracy. A production
consumer must not blindly trust the selected label and the distribution to
agree; this experiment does not implement a production policy for that case.

## Cost, timing, and verification

- Eight requests to pinned `jev-1.13.0`, one per post, sequential, no retries.
- 11,567 reported input tokens; 928 reported output tokens.
- Estimated cost **US$0.000485814**, from returned input usage at the
  [verified list price](https://docs.typesafe.ai/models) of US$0.042 per million
  input tokens, with free output. This is not an invoice.
- Median observed request time **0.260 seconds**, range 0.199–0.288 seconds.
  This includes the local HTTPS request/response but not experiment preparation.
  It is not evidence of a speed advantage over an equivalent compact 0731 call.
- Frozen source/question/reference/runner hashes match. Original experiment
  files and the four pre-existing dirty application/test files are unchanged.
- Every physical start has one saved HTTP 200 response and usage accounting;
  all eight calls are within the eight-call and US$0.02 limits.

No live X calls, new translations, database writes, model fallback, production
configuration changes, app prompt changes, scheduler changes, or deployment
occurred. No further calls are running or planned for this diagnostic.

## Evidence

- [Frozen contract](contract.md), [frozen hashes](frozen.json), [copied cohort and revised references](cohort.json).
- [Exact eight requests](requests.json), [baseline/reviewer comparison](comparators.json).
- [Raw receipts](receipts/), [completion](complete.json), [per-field scores and audit](scores.json).
- [Original runner](run.py), [explicit continuation](continuation.md), [continuation hashes](continuation-frozen.json), [continuation runner](continue_run.py).
