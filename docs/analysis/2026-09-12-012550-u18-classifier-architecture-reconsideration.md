# U18 classifier architecture reconsideration

## Decision

Replace the failed v18 three-pass, language-specific selector with one complete
primary classification followed by one candidate-aware completeness review.
The review returns one complete canonical replacement judgment. A fixed
reviewer-authoritative selector publishes that judgment only when both passes
validate. Preserve the primary, review, and selected final judgments as
separate versioned records.

Do not continue batch-size tuning, grouped-label prompting, post-hoc union, or
an additions-only reviewer. Keep the frozen exact-set floors and DeepSeek
provider route unchanged.

## Evidence

The exact v18 runtime candidate scored 76/120 (63.3%) complete post-type sets,
while label-level micro F1 was 0.868. Its 65 label errors were balanced: 32
false positives and 33 false negatives. Of the 44 rows with an incorrect type
set, 14 were missing types only, 11 had unsupported extra types only, 16 had
both kinds of error, and three had the wrong outcome.

| Locale | Exact | Missing only | Extra only | Both | Wrong outcome |
| --- | ---: | ---: | ---: | ---: | ---: |
| EN | 22/40 | 5 | 5 | 7 | 1 |
| JA | 28/40 | 2 | 4 | 5 | 1 |
| ZH-CN | 26/40 | 7 | 2 | 4 | 1 |
| All | 76/120 | 14 | 11 | 16 | 3 |

An additions-only reviewer cannot clear the locked locale gate even under an
unrealistic oracle assumption: correcting every missing-only row without ever
adding a false positive would cap EN at 27/40 (67.5%) and the full cohort at
90/120 (75%). It also cannot repair the three outcome errors. The next reviewer
must be able to remove unsupported types and correct outcome when the source
requires it.

The v19 batch-five probe reached 56.7% exact sets, the v20 singleton probe
reached 40.0%, and the normalized diagnostic output from the malformed v21
grouped-label probe reached 33.3%. Those results reject batching and grouped
boolean decomposition as the next change. They do not justify lowering the
quality floor.

## Fixed next experiment

1. Keep the existing complete primary classifier as the proposal.
2. Give one DeepSeek review pass the source packet, attributed brand, and
   canonical primary judgment.
3. Require the reviewer to return a complete canonical classification,
   `accept|replace`, closed change reasons, and source-bound evidence for every
   changed decision.
4. Use the valid review result in full; never union it with the primary or
   select fields by language or observed score.
5. Persist primary, review, and final records under one revision identity, and
   keep the current classification tables as the selected-final projection.
6. Prove parsing, validation, lineage, atomic publication, retries, and call
   bounds without a provider.
7. Freeze prompt/parser/model/selector identities, the existing 120-row
   consumed-development cohort hash, and the complete request/token/cost stop
   rule before a new DeepSeek call.
8. Continue to the 500-row consumed-development run only if every frozen
   continuation floor passes; neither development run can approve release.

## Reproducibility

- Gold packet SHA-256:
  `1fb32d1b648b7bf393e3c88ba0feb29decca6084b33b30b043d13bc4ba333fd6`
- v18 runtime candidate SHA-256:
  `638682d1c792220ba462784df8a4a6592a8e5e8f7f35344a3a6267ce3a0a9884`
- v18 evaluation report SHA-256:
  `9e3fd3eb678d953fec1a7c38bb9b539391f5d4c7a6af022aea917224af347ec4`
- Source artifacts remain ignored under `.context/u18/`; this report carries
  only aggregate metrics and hashes.
