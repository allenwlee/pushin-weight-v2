# U18 v25 classification quality assessment

## Decision

The v25 candidate fails the consumed-development continuation gate. Do not
run the 500-row assessment, activate taxonomy-v3 classification on staging, or
promote this classifier to production.

The reviewer-authoritative pass did not improve the primary classifier's
complete-set accuracy. The next bounded experiment keeps the same primary and
reviewer-authoritative topology, but requires the reviewer to make an explicit
yes/no judgment for every post type and product label before returning its
complete classification. Those verdicts are validation evidence only; code
will not turn them into labels or merge them with the primary.

## Reproducible result

- Candidate rows: 120/120 valid, with 40 EN, 40 JA, and 40 ZH-CN.
- Candidate SHA-256:
  `2d41e1ec66107a59377e8267dff585fe26a90c8ac633a99268416a7491332a18`.
- Evaluation SHA-256:
  `5458c80d0142d2c5c3059d9b730aaffc0c5984bd0b285ce97403e81c5e156ebb`.
- Carried-forward development gold SHA-256:
  `ac6690ad5455db6ea607b4339ded63f2eb8885d57323aaf17864950c682e1a6f`.
- Paid-response manifest SHA-256:
  `7243e1bbae9a012e33b53c00a0c8bdc2c0ba7151ae28cd050b39e2929b559850`.
- V25 replay transport: 18 cache hits, zero provider calls, zero tokens, and
  zero dollars.
- The source v23 transport used 26 successful DeepSeek calls, 130,406 observed
  input tokens, and 24,725 observed output tokens, with no transport errors.

The gold file carries the same 120 human-development judgments used by the
v18 probe. Its metadata was advanced from the old prompt identifier to the
current canonical taxonomy-v3 identifier so the evaluator could read the
zero-transport replay. No gold labels changed. This makes the result suitable
for development diagnosis, not fresh blind release evidence.

## Gate results

| Measure | Required | V25 final | Result |
| --- | ---: | ---: | --- |
| Post-type exact sets, all | 70.0% | 52.5% | Fail |
| Post-type exact sets, EN | 70.0% | 52.5% | Fail |
| Post-type exact sets, JA | 70.0% | 62.5% | Fail |
| Post-type exact sets, ZH-CN | 70.0% | 42.5% | Fail |
| Product-label exact sets, all | 85.0% | 82.5% | Fail |
| Product-label exact sets, EN | 70.0% | 85.0% | Pass |
| Product-label exact sets, JA | 70.0% | 90.0% | Pass |
| Product-label exact sets, ZH-CN | 70.0% | 72.5% | Pass |
| Outcome accuracy, all | 90.0% | 95.8% | Pass |
| `context_missing` precision | 50.0% | 50.0% | Pass |
| `context_missing` recall | 50.0% | 100.0% | Pass |

Every supported post-type F1 cleared 0.55 and every supported product-label F1
cleared 0.50. The cohort has no positive gold examples for `other`,
`personnel_changes`, or product `bug`, so those three release floors remain
unsupported. The evaluator reports that support block before its numeric floor
checks; manual reconstruction found six numeric failures in the formal policy,
including overall and every-locale post-type exactness.

## What the reviewer changed

The primary reached 64/120 post-type exact sets (53.3%), while the selected
review result reached 63/120 (52.5%). Product-label exactness remained 99/120
(82.5%). Of 120 rows, the reviewer accepted 111 and replaced nine; seven of
those rows also required redundant metadata normalization.

At complete-set level, reviewer changes improved one post-type row and
regressed two. They produced no product-label exact-set improvement. English
was unchanged; ZH-CN post-type exactness fell from 45.0% to 42.5%. The final
candidate still had the largest post-type false-negative counts in
`opinions_reactions` (12), `releases_updates` (12),
`research_explanations` (9), and `results_evaluations` (6). Product-label
omissions were led by `testimonial` (9) and `complaint` (4).

This is reviewer anchoring: the second pass usually accepted the proposal and
did not independently reconstruct the overlapping label set. Parser
normalization solved malformed redundant metadata, but it could not improve
semantic judgment.

## Next bounded experiment

The v26 reviewer will return exhaustive boolean verdict maps for all thirteen
post types and all five product labels, as well as its complete canonical
classification. It must decide those verdicts from source and stored context
before comparing the primary. The parser will require exact key coverage,
boolean values, and agreement between the verdict maps and the complete
classification. Any mismatch receives the existing one-packet repair and then
fails closed.

The reviewer remains the sole final classification authority. The verdict
maps do not union, inject, or select labels, and the existing source-bound
evidence and derived-change rules remain in force. This is the last bounded
DeepSeek Flash prompt-topology test justified by the present evidence. If it
misses the unchanged 120-row continuation floors, further Flash prompt tuning
stops; the next architecture decision must test a stronger configured model or
revisit the taxonomy/gate with fresh human evidence.

The 500-row consumed-development assessment remains forbidden unless v26 first
passes every 120-row continuation floor. Any later release decision still
requires a fresh, candidate-blind, zero-overlap cohort with positive support
for `other`, `personnel_changes`, and `bug`.
