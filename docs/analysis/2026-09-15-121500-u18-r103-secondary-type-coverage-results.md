# R103: broad secondary post-type coverage over one primary call

R103 tested the proposed near-full secondary pass without repeating primary
classification. It sent the 41 rows that R101's primary call marked
`classified` to one focused DeepSeek specialist in three 20/20/1 batches. The
specialist independently evaluated four commonly missed overlapping types
(`results_evaluations`, `research_explanations`, `hands_on_usage`, and
`opinions_reactions`) and the four rare types. It could only add a label backed
by an exact quote; it could not change outcome, sentiment, product labels,
nationalism, unsanctioned flags, or remove primary labels.

## Result

The test completed operationally: all three calls returned valid row-oriented
JSON, all 41 rows received eight explicit decisions, and no production code,
rows, or runtime configuration changed. The actual marginal cost was
$0.01830 under the conservative rate model ($0.00718 at the current off-peak
estimate), compared with a frozen ceiling of $0.05830.

The architecture fails its quality test. It recovered five reference labels,
but added seven labels the completed owner reference does not support. It must
not become a routine production call.

| Measure | Result |
|---|---:|
| Eligible primary-classified rows | 41 / 45 |
| Specialist calls | 3 |
| Correct added labels | 5 |
| Unsupported added labels | 7 |
| Post-type exact-set accuracy | 44.4% → 44.4% |
| Production changed | No |

The five useful additions were two `events` labels (H0DEC6F537E0 and
H1A3B3731E1C), two `results_evaluations` labels (H3569508600E and
HF3B55FD811B), and one `opportunities` label (H688781944AC).

The seven unsupported additions were an `opinions_reactions` and an
`opportunities` label on H5024EDC82C6; `results_evaluations` on H7046A8A0689,
H92A808A114E, H9C7C731F3C3, and HB4FB5810A09; and `opportunities` on
HB94D1A5CA63. This confirms that merely narrowing the response fields does
not solve the model's boundary errors for results/evaluations and promotions.

R102 is retained as a failed, non-merged transport record. Its first paid call
returned a type-grouped response instead of the required row-oriented schema;
no decisions were accepted. R103 added an explicit output shape and raw-response
receipt before validation, then ran as a separate frozen experiment.

## Evidence

- [Frozen R103 contract](2026-09-15-121500-u18-r103-secondary-type-coverage-contract.json)
- [Machine-readable R103 result](2026-09-15-121500-u18-r103-secondary-type-coverage-results.json)
- Private R103 requests/responses: `.context/u18/secondary-type-coverage-pilot-r103-v1/` (ignored)
- R101 primary source: [R101 result](2026-09-15-111545-u18-r101-single-primary-conditional-results.md)
