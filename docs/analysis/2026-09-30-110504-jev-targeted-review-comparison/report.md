# Jev targeted review: useful geo warnings, no demonstrated promotion fix

Date: 2026-09-30. Status: bounded run ended; comparison partially completed.

## Outcome

Jev rejected some unsupported geopolitical decisions when asked a focused
verification question. Showing 0731's explanation did not improve that result:
it weakened one correct rejection, while moving one valid stance just over the
approval threshold. Neither version is established as a reliable automatic fix.

For promotion, the label-only review was uncertain on all four examples. The
promotion-with-explanation comparison could not be completed: our experimental
explanation request produced invalid promotion explanations. That is a failed
experiment input, not evidence that a correctly implemented explanation approach
cannot work.

Twenty model calls were made: four DeepSeek and sixteen Jev. Combined estimated
model cost was **US$0.00340272**, below the approved 32-call/US$1 ceiling. No
application prompt, application code, database, scheduler, or deployment changed.
No further calls are running or planned under this comparison.

## What was tested

The [frozen contract](contract.md) and [cohort](cohort.json) contain eight
post/brand cases: four geopolitical examples and four promotion examples. Seven
are saved real posts; the explicit dual-promotion example is synthetic. The
cases include the owner's original B.AI/GLM promotion example and
@PreciousBa82157 geo complaint, plus positive and negative controls.

0731 used the original local content-v5 and brand-v5 prompts, **not production's
content-v6**. Each arm made two eight-post requests, one per classification role.
The experimental arm added a short claim and exact source quotation in the same
response. This is an explanation requested from the model, not its internal
reasoning trace. Both arms requested `reasoning_effort: none`; all four receipts
reported zero reasoning tokens.

Jev `jev-1.13.0` received the full saved source/context and targeted questions:
does the offered service belong to this tracked brand, or does the source
actually express the assigned national/political judgment? It did not receive
reference labels or the scoring rubric. The review checked both included and
omitted labels. Scores at least 0.80 approved an assignment, at most 0.20 rejected
it, and intermediate scores abstained. These thresholds were fixed before calls;
the scores are not independently calibrated correctness probabilities.

- **A — original labels, no explanation:** eight cases completed.
- **B — explanation-arm labels, explanation shown:** four geo cases completed;
  all four promotion cases unavailable.
- **C — the exact same labels as B, explanation hidden:** four geo cases
  completed; promotion comparisons were not run without a valid B counterpart.

B versus C isolates showing the explanation. A versus B does not: requesting an
explanation also changed 0731's labels. The [partial-comparison record](partial-comparison.md)
was saved before any Jev call. Cases, reference labels, thresholds, and review
questions were not tuned after results.

## Geopolitical results

These are **18 reviewed fields across four source posts per arm**, not 18
independent posts. US stance on two controls was deliberately unscored.

| Measure | A: original labels | C: new labels, explanation hidden | B: same new labels, explanation shown |
| --- | ---: | ---: | ---: |
| 0731 fields matching the reference before review | 16/18 | 14/18 | 14/18 |
| Incorrect fields Jev rejected | 0/2 | 3/4 | 2/4 |
| Incorrect fields Jev approved | 0 | 0 | 0 |
| Correct fields Jev held as uncertain | 3/16 | 6/14 | 5/14 |
| Correct fields Jev rejected | 0 | 0 | 0 |
| All uncertain fields | 5/18 | 7/18 | 7/18 |

No incorrect field was confidently approved. However, uncertainty also held
valid labels, so that fact alone does not establish a useful automatic filter.
Against all scored fields, 0731's exact per-post match was 2/4 for the baseline
and 1/4 when asked for explanations.

### The most informative matched comparison

G02, post `2100052017993683063`, criticizes Anthropic/OpenAI and favors DeepSeek's
open approach. It does not evaluate China as a nation. Baseline 0731 correctly
returned no geo classification. When asked for an explanation, it instead
assigned nationalism and China `mild_pro`.

Its China explanation was:

> The post expresses mild support for China-associated DeepSeek's approach without broad national evaluation.

This is a useful diagnostic artifact: it exposes the company-to-country leap
while acknowledging the absence of a broad national evaluation. It is not proof
that this explanation caused the original historical production error.

| Review of those same new assignments | Explanation hidden | Explanation shown |
| --- | --- | --- |
| Nationalism | 0.10 — reject | 0.25 — uncertain |
| China `mild_pro` | 0.08 — reject | 0.14 — reject |

Showing the explanation weakened the nationalism rejection. Conversely, on G04,
the valid China `anti` assignment moved from 0.79 (uncertain) to 0.81 (approve).
That small threshold crossing is not a robust improvement demonstrated by one
observation. Both B and C correctly rejected G04's omission of `framework`.

### The original reported geo failure

G01, post `2105081335475757197` by @PreciousBa82157, received no geo modes or
national stances in **both fresh 0731 arms**. Jev approved those correct absences.
The historical nationalism/China-pro/US-anti assignment was not replayed as a
candidate. We therefore have **not shown whether Jev would reject that exact
historical assignment**.

### Parser behavior matters

The unchanged application parser added `nationalism` to baseline G03 because
the raw response supplied China `mild_pro` with only `framework`. Jev reviewed
the application-accepted values. The raw-versus-accepted difference is saved in
[audit.json](audit.json); do not attribute that added mode to raw model output.

## Promotion results

Only A, the original-label review without explanations, completed.

| Case | Reference | 0731 assignment | Jev support for that assignment | Result |
| --- | --- | --- | ---: | --- |
| P01: B.AI guide mentions GLM, `2104483144233853085` | Not a GLM ad | GLM ad | 0.30 | Uncertain |
| P02: Token Machine prizes are Qwen tokens, `2101798119298277764` | Not a Qwen ad | Qwen ad | 0.57 | Uncertain |
| P03: Official Qwen ranking celebration and “Try it now”, `2102569821997346912` | Qwen ad | No Qwen ad | 0.26 | Uncertain |
| P04: Explicit DeepSeek API and Token Machine co-promotion, synthetic | DeepSeek ad | DeepSeek ad | 0.79 | Uncertain |

Baseline 0731 matched 1/4 promotion references. Jev confidently rejected none of
the three errors and approved none of them; it also held the one correct
decision. The B.AI problem recurred, but Jev did not decisively resolve it under
the predeclared thresholds. This checks the beneficiary of promotion, not the
separate problem of proving publisher/staff/sponsor affiliation.

### Why the explanation comparison is unavailable

The experimental content response placed three geopolitical explanations inside
each `advertising_marketing` object instead of supplying its required `claim`
and `evidence`. All eight content-role explanations failed shape validation,
including all four promotion test cases. The experimental instruction mentioned
both role-specific schemas in one shared addendum; that is a plausible setup
weakness, not an established model limitation.

Two content decisions also failed the unchanged application parser:

- P01 supplied `@TRONEcostar` as evidence, but the source contains the hashtag
  `#TRONEcostar`, not that handle.
- P04 combined `crypto` and `general` untracked-promotion categories, although
  `general` must stand alone.

The separate brand-role explanations passed validation. We continued only the
independent geo comparison, omitting the invalid, irrelevant promotion-basis
field from geo B inputs. All other B/C inputs were identical. No explanation,
quote, label, or model response was repaired; there was no replacement call.
Promotion B/C remain four unavailable planned cases each, **not zero errors**.

## Cost and operational evidence

| DeepSeek arm, two calls each | Input tokens | Output tokens | Provider-reported estimated cost |
| --- | ---: | ---: | ---: |
| Original | 9,419 | 1,002 | US$0.00073398 |
| Explanation requested | 9,831 | 3,884 | US$0.00126594 |

The explanation arm emitted 2,882 extra output tokens. It required no separate
explanation call, but it was not free. Serial provider-response time totaled
13.09 seconds for the original pair versus 57.26 seconds for the explanation
pair; these are single-run timings, not stable latency estimates.

Sixteen Jev requests used 33,400 input tokens, giving a US$0.00140280 estimate at
the current [TypeSafe input-token list price](https://docs.typesafe.ai/models).
Median observed Jev request time was 0.255 seconds (range 0.199–0.316). Output
tokens are free at that published price. DeepSeek costs above are the provider's
`estimated_cost`, not an invoice; [DeepInfra's model page](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731)
documents current pricing. Combined model estimate: US$0.00340272. Render compute
charges are not included.

The isolated staging job `job-dau72amk1f9s73akemig` succeeded. Bulk Render log
retrieval timed out; three small log pages recovered every existing response
without rerunning inference. All 20 provider requests succeeded without retries.
Jev answered 64 typed questions; 58 field reviews were scored, with six
deliberately unscored US-stance reviews. These are not 58 independent examples.

The provider-free audit checked frozen cohort/prompt/request hashes, unchanged
application sources and original runner, identical B/C inputs except the valid
geo explanation, raw response scores, call counts, coverage, and accounting.
It passed. Existing unrelated dirty application/test files remain untouched.

## Limits and recommendation

This is a small, enriched development diagnostic with pre-run agent-reviewed
labels and existing development fixtures, not an independent holdout or a
production accuracy estimate. The `mild_pro` versus `pro` reference boundary is
also less clear-cut than the company-versus-country error. One Chinese-language
case and one synthetic promotion cannot establish general performance. The
original reported geo failure did not recur, and the promotion-explanation
comparison is missing.

Do not deploy either approach from this evidence. The strongest observation is
that an independent targeted review can flag some company-to-country mistakes;
feeding it 0731's explanation did not improve the tradeoff here. Explanations
can still be useful for inspection, but should not be treated as authoritative
evidence. The promotion question remains unresolved. No further testing or
prompt revision is implied by this report.

## Evidence files

- [Frozen cohort](cohort.json), [contract](contract.md), [preflight hashes](preflight.json).
- [Exact DeepSeek requests](deepseek-requests.json), [raw responses and completion receipts](deepseek-events/complete.json), [parsed decisions and validation failures](deepseek-parsed.json).
- [Recorded partial-comparison deviation](partial-comparison.md), [planned versus available cases](partial-coverage.json).
- [Exact Jev requests](jev-requests.json); raw per-request responses and accounting in `jev/`.
- [Per-field scores](scores.json), [final coverage and independent accounting audit](audit.json).
- Reproducibility helpers: [frozen runner](run.py), [log recovery](collect_logs_paginated.py), [partial-input preparation](prepare_partial_reviews.py), [provider-free audit](audit_results.py).
