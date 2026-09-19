# U18 v26 classification quality assessment

## Decision

The v26 exhaustive-verdict reviewer fails the consumed-development
continuation gate. Stop DeepSeek Flash prompt-topology tuning. Do not run the
500-row development assessment, open the sealed release cohort, activate
taxonomy-v3 classification on staging, or promote this classifier to
production.

The required boolean verdict maps made the reviewer contract auditable and
increased product-label exactness by one row, but they did not improve the
main post-type judgment. The selected reviewer output was one exact post-type
set worse than the primary.

## Reproducible result

- Candidate rows: 120/120 valid, with 40 EN, 40 JA, and 40 ZH-CN.
- Source revision: `4f9405b7872edbd1078357198f32b14e2c0b25ae`.
- Candidate SHA-256:
  `b06088b52bef44d9f8ac1bd836c305ad8770ef5f3ba4dc20e29b80b4e109ef2e`.
- Evaluation SHA-256:
  `f2f3f4d2a9dac0ac6bd1b997beeef69bfef154e965163dbcdc355e3870d5e6c7`.
- Evaluation identity:
  `sha256:26d76c248348d95edb7a8f88ccf1733e6950cc7011208e9cd99dc1f897c56318`.
- Budget SHA-256:
  `046a8da78dba6758db38b1ebb278e84297b74050f69cc06a256498638b62a02f`.
- Primary-only diagnostic evaluation SHA-256:
  `cc76e578c2cdd9bd721f21f73bdc45ba2a16185895c7e4bf313fc914aca97ccf`.
- The carried-forward consumed-development reference remains the metadata-only
  v25 compatibility copy described in the v25 assessment. No reference labels
  changed. Its two annotators and adjudicator were model passes, so this result
  measures model agreement rather than human-label accuracy.

The run used 26 successful DeepSeek calls with no errors: six primary calls,
twelve normal review calls, and eight one-packet review repairs. Observed usage
was 64,384 input tokens and 36,174 output tokens, for approximately $0.0761 at
the frozen rates. Conservative transport reservations were 355,127 input and
106,496 output tokens, corresponding to $0.2968; both remained below the
$0.72 hard cap.

## Gate results

| Measure | Required | V26 final | Result |
| --- | ---: | ---: | --- |
| Post-type exact sets, all | 70.0% | 50.8% | Fail |
| Post-type exact sets, EN | 70.0% | 45.0% | Fail |
| Post-type exact sets, JA | 70.0% | 60.0% | Fail |
| Post-type exact sets, ZH-CN | 70.0% | 47.5% | Fail |
| Product-label exact sets, all | 85.0% | 83.3% | Fail |
| Product-label exact sets, EN | 70.0% | 87.5% | Pass |
| Product-label exact sets, JA | 70.0% | 90.0% | Pass |
| Product-label exact sets, ZH-CN | 70.0% | 72.5% | Pass |
| Outcome accuracy, all | 90.0% | 93.3% | Pass |
| `context_missing` precision | 50.0% | 38.5% | Fail |
| `context_missing` recall | 50.0% | 100.0% | Pass |

Every supported post-type F1 remained above 0.55 and every supported
product-label F1 remained at or above 0.50. The cohort still has no positive
gold examples for `other`, `personnel_changes`, or product `bug`, so it remains
development evidence rather than a release gate even if the numeric floors
were to pass.

## Primary versus exhaustive reviewer

The primary produced 62/120 exact post-type sets (51.7%) and 99/120 exact
product-label sets (82.5%). The exhaustive reviewer produced 61/120 post-type
sets (50.8%) and 100/120 product-label sets (83.3%). Outcome accuracy stayed at
93.3%. The reviewer also reduced sentiment accuracy from 75.8% to 75.0%.

Locale post-type results were unchanged in EN and JA. ZH-CN fell from 50.0% in
the primary to 47.5% in the final result. The largest remaining post-type
false-negative counts were `opinions_reactions` (13), `releases_updates` (11),
`research_explanations` (7), and `results_evaluations` (4). Product omissions
were still led by `testimonial` (9) and `complaint` (4).

The explicit 18-label audit did not overcome candidate anchoring or the model's
incomplete overlapping-type judgments. Because v26 was the preregistered final
Flash topology attempt, another Flash prompt, batch, decomposition, merge, or
selector experiment is outside the plan.

## Next architecture decision

The next step is the frozen candidate-blind human ambiguity study described in
`docs/reference/2026-09-12-030118-u18-human-ambiguity-study.md`. It determines
whether the current failures belong to the classifier, the model-generated
reference, or underspecified taxonomy boundaries. No further provider
transport is allowed until that study passes. A pass may authorize a small,
separately budgeted DeepSeek Pro reviewer pilot; a failure requires taxonomy
revision and focused human re-review. Anthropic is not an active provider
choice.
