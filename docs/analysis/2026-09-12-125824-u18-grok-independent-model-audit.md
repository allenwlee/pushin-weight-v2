# U18 Grok independent model audit

## Decision

The Grok 4.6 audit is valid independent model evidence, but it does not replace
the human ambiguity study or authorize another provider run. Grok disagrees too
widely with both the model-generated reference and every preserved classifier
candidate to serve as an adjudicator.

The result strengthens the case that exact-set failures combine model behavior
with unresolved taxonomy and brand-attribution boundaries. Taxonomy-v3 staging
activation, the 500-row development run, and the unopened release cohort remain
blocked.

## Artifact and validation

- Private artifact:
  `.context/u18/human-ambiguity-study-v1/grok-independent-audit.json`.
- SHA-256:
  `0618cf78e44773ae5c58dda9ec35cbc262f37443f06bfec36fa5acf536a0ead0`.
- Declared model: Grok 4.6 (xAI).
- Declared method: candidate-blind, no internet, and restricted to the frozen
  study note, prompt reference, and reviewer-A source packet.
- Rows: 45 unique expected case IDs, with 15 EN, 15 JA, and 15 ZH-CN.
- Closed-schema validation: passed with zero errors.
- Output shape, allowed labels, booleans, confidence range, classified and
  `context_missing` invariants, and exclusive `other` behavior all passed.
- Provider usage and cost are unknown because the owner ran this audit in an
  external Grok build session rather than the repository's budgeted transport.

## Agreement with the model-generated reference

| Measure | Agreement |
| --- | ---: |
| Exact outcome plus post-type set | 31.1% |
| Exact product-label set | 68.9% |
| Sentiment | 64.4% |
| Both nationalism axes | 86.7% |
| Complete classification object | 11.1% |
| Post-type micro precision | 71.7% |
| Post-type micro recall | 74.7% |
| Post-type micro F1 | 73.2% |
| Product-label micro precision | 73.3% |
| Product-label micro recall | 47.8% |
| Product-label micro F1 | 57.9% |

Exact outcome plus post-type agreement was 33.3% for EN, 33.3% for JA, and
26.7% for ZH-CN. Outcome alone agreed on 42/45 cases: Grok matched 40
`classified` and two `context_missing` rows, while changing three reference
`classified` rows to `context_missing`.

The low exact-set score is not total semantic collapse. Grok and the reference
shared 71 positive post-type decisions, with 28 Grok-only additions and 24
reference-only decisions. The largest Grok additions were
`results_evaluations` (8), `advertising_marketing` (5), and
`opinions_reactions` (5). The largest omissions were
`research_explanations` (7), `results_evaluations` (5), and
`releases_updates` (4). Product-label recall was chiefly reduced by eight
missing `testimonial` decisions.

## Diagnostic groups

| Frozen group | Exact outcome plus post-type agreement with reference |
| --- | ---: |
| Agreement controls | 40.0% |
| Model-run conflicts | 40.0% |
| Stable model-versus-reference disagreements | 13.3% |

The 15 agreement controls were cases where all four preserved classifier runs
and the model-generated reference had agreed before Grok saw them. Grok matched
only six exactly. In the 15 stable model-versus-reference disagreements, Grok
matched the prior model consensus three times, the model-generated reference
twice, and neither ten times. Grok therefore adds a distinct interpretation; it
does not resolve which prior answer is correct.

No preserved candidate clearly aligned with Grok. Exact outcome plus post-type
agreement was 24.4% for the v18 primary and 31.1% for the v18 secondary, v25
primary, and v26 final. The audit cannot justify selecting one of those
candidates as ground truth.

## Reported ambiguity

Grok marked 14/45 cases with taxonomy issues: six EN, three JA, and five ZH-CN.
The issues appeared in six model-run conflicts, four agreement controls, and
four stable model-versus-reference disagreements.

The issue codes were six `brand_attribution`, two `nationalism`, and one each
for `result_vs_opinion`, `context_missing`, `job_vs_opportunity`, `sentiment`,
`product_label`, and `event_vs_opportunity`. Four issues occurred even in the
agreement-control group. Confidence was 3 for 16 cases, 4 for 23, and 5 for
six; Grok assigned no confidence below 3.

These issue counts are model observations rather than human findings and do not
enter the human reliability gate. They are useful pointers for the later human
adjudication and any taxonomy/example revision.

## Next step

Keep this artifact hidden from the independent human reviewers. Qualified
humans review the already frozen candidate-blind CSVs, and a distinct human
sees only human disagreements during adjudication. If that is unavailable, the
project may explicitly choose to proceed using model-agreement evidence, but it
must not describe the resulting classifier as human-validated or as measured
against ground truth.
