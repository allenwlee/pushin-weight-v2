# Matched questions: Jev 21/22; 0731 labels 14/22; 0731 with probabilities 16/22

Date: 2026-09-30 UTC. Completed: 16 new 0731 calls; zero retries or Jev calls.

## Outcome

On the same eight cases, with identical source state, question wording, criteria,
and corrected reference answers, the saved Jev primary run remains ahead of
both new 0731 versions overall. The probability-reporting 0731 version gets all
four promotion cases right, including the case Jev missed, but repeats the
geopolitical errors made by the labels-only version.

| Version | Geo fields | Promotion fields | Combined | Posts with every scored field correct |
| --- | ---: | ---: | ---: | ---: |
| 0731 compact labels only, A | 12/18 | 2/4 | **14/22 (63.6%)** | 3/8 |
| 0731 labels + probability estimates, B | 12/18 | 4/4 | **16/22 (72.7%)** | 5/8 |
| Jev primary, saved previous run | 18/18 | 3/4 | **21/22 (95.5%)** | 7/8 |

This is a small, repeatedly inspected development set, not production accuracy
or an independent holdout. There are 22 correlated field checks across eight
posts, not 22 independent posts. Seven posts are real; one is synthetic. Two US
stance fields per version are intentionally unscored, as fixed before all runs.

The Jev comparison retains its earlier output defect: one already-unscored US
Choice label disagreed with the highest returned probability. All 48 answers
from the two new 0731 arms are valid, including their four unscored answers;
all 16 responses ended normally, with zero provider-reported reasoning tokens.

## What was matched, and what was not

Every 0731 user message is exactly the saved Jev `state` and `questions` objects,
serialized as JSON. Both 0731 arms share that identical user message and the
same sampling settings, model, maximum output, and common system instructions.
Only the system's output-format request differs. No prior labels, explanations,
scores, or reference answers were provided to 0731.

- Model: `deepseek-ai/DeepSeek-V4-Flash-0731`, direct DeepInfra.
- Temperature 1, top_p 1, seed 42, reasoning_effort none, max_tokens 1024.
- One request per case per arm, alternating arm order by case, sequential.
- A returns only boolean/option labels, with no explanations or probabilities.
- B returns those labels plus numeric probability distributions.
- Nothing was tuned after seeing the results; no answer was repaired.

Thus, different substantive question wording does not explain the whole observed
gap on this set. However, this still does not isolate Jev's internal architecture
from its training/weights. 0731 generates a joint text response; Jev uses its
native decision interface. A single paired run also cannot distinguish the
causal effect of confidence elicitation from ordinary generation variation.

## Did asking for probabilities change the decisions?

There were **two differences among the 22 scored decisions**, both promotion
improvements in B. No scored geopolitical label changed.

| Case | A: labels only | B: with probabilities | Reference |
| --- | --- | --- | --- |
| P01: B.AI guide mentioning GLM | GLM advertising | Not GLM advertising, 89% | Not GLM advertising |
| P02: Token Machine prizes involving Qwen | Qwen advertising | Not Qwen advertising, 90% | Not Qwen advertising |

The percentages above are B's confidence in its selected **negative** answer,
not the probability that advertising is present. The direct advertising
probabilities across all promotion cases are:

| Case | Jev P(advertising) | 0731 B P(advertising) | Expected |
| --- | ---: | ---: | --- |
| P01 B.AI / GLM | 25% | 11% | No |
| P02 Token Machine / Qwen | 51% | 10% | No |
| P03 official Qwen announcement | 94% | 90% | Yes |
| P04 explicit DeepSeek co-promotion, synthetic | 76% | 60% | Yes |

The answers-only arm remains the primary comparison. Recording B as a separate
arm prevents silently treating a confidence-request change as if it were the
same request. The two observed changes do not prove that asking for confidence
will generally improve decisions.

## Are 0731's percentages reliable?

They are valid, internally consistent **self-reported estimates**, not evidence
of calibration. Here are every one of B's six scored mistakes:

| Case | Incorrect selected answer | Estimated probability of that answer | Expected |
| --- | --- | ---: | --- |
| G02 DeepSeek praise / competitor criticism | China pro | 60% | none |
| G02 | geopolitical framework present | 80% | absent |
| G02 | nationalism present | 75% | absent |
| G02 | US anti | 70% | none |
| G03 Chinese-innovation defense | reporting absent | 90% | present |
| G04 Chinese-system criticism | reporting absent | 90% | present |

G02 demonstrates the original company-to-country attribution problem despite
explicit instructions against it. G03/G04 use our revised, pre-frozen judgment
that attributed reporting can coexist with adopted opinion. Those reference
answers remain human/agent judgments, not externally adjudicated truth.

Both 0731 versions selected G03 China `pro` correctly. Excluding that predeclared
disputed intensity field yields A 13/21 and B 15/21; it does not remove their
geopolitical disagreements.

A high percentage is therefore not a safe correctness guarantee. This small
sample cannot establish a calibration curve, a reliable routing threshold, or a
general overconfidence rate. Prior research has found useful verbalized
confidence on other models/tasks, but does not validate these 0731 percentages
for this application: [Tian et al., Just Ask for Calibration](https://arxiv.org/abs/2305.14975).

## Cost and timing

| Eight-request version | Input tokens | Cached input tokens | Output tokens | Estimated model cost | Median request time |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0731 A, labels only | 9,335 | 2,816 | 188 | US$0.00046722 | 1.440 s |
| 0731 B, probabilities | 9,983 | 2,560 | 891 | US$0.00064416 | 2.062 s |
| Jev primary, previous run | 11,567 | not reported here | 928 | US$0.000485814 | 0.260 s |

The compact 0731 arm really is small: 188 output tokens total across eight calls.
Its observed estimated model cost was slightly below Jev's in these runs;
there is no demonstrated Jev token-billing advantage over compact 0731 here.
B emitted 703 more output tokens than A and also needed longer format guidance.

DeepInfra costs are its returned `estimated_cost` values, including the observed
cached-input usage, not invoices. Its current
[standard prices](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731) are
US$0.06/M input, US$0.18/M output, and US$0.015/M cached input. Jev's estimate uses
its [input-token price](https://docs.typesafe.ai/models), with free output.

0731 timings were measured inside a Render job; Jev timings were measured on
the local host. They include HTTPS request/response, but not job startup or
experiment preparation. Different network paths, caches, and warm conditions
mean these are observed timings, not a controlled speed benchmark. No claim is
made about which internal mechanism causes the observed difference.

## Execution and checks

- Job `job-dauavd1srm7s73bhf01g` succeeded, 06:44:04–06:45:03 UTC.
- Sixteen provider starts and sixteen HTTP 200 responses, all normal completion.
- Combined provider-reported model estimate **US$0.00111138**, below US$0.05.
  Render job compute is additional and not included in that model-only estimate.
- Small-page log recovery retrieved all 34 evidence events without inference
  retries. Seven log pages were sufficient.
- Frozen input/question/cohort/runner hashes match. A/B user messages and sampler
  settings match for all eight pairs. Prior Jev files and existing dirty app/test
  files are unchanged. Both semantic-label and strict-validity scores agree.
- The staging-harvest scheduler remained suspended after the job. No production
  or application state, prompts, configuration, databases, or deployment changed.
- The experiment is complete. No further calls are running or planned.

## Evidence

- [Frozen contract](contract.md), [exact requests](requests.json), [cohort](cohort.json), [hashes](frozen.json).
- [Raw response events](events/), [completion](events/complete.json), [job receipt](job.json).
- [Scores, probabilities, changes, usage, and audit](scores.json).
- [Local runner](run.py), [isolated remote program](remote.py), [recovered logs](log-pages/).
- [Previous Jev primary report](../2026-09-30-060237-jev-primary-classifier/report.md).
