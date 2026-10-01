# Jev political-framing retest arm

The one-pass Jev arm completed all 117 frozen original-text cases using model
`jev-1.13.0`, the revised 38-question object, and the unchanged shared
references. This is a post-feedback rerun on a known cohort, not a fresh
blinded test or a production acceptance result.

## Three revised geo modes

All 351 binary answers were valid. Invalid answers are counted separately and
would count as unsuccessful in recall and exact-match scoring.

| Mode | TP | FP | FN | TN | Invalid | Exact field accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Reporting | 13 | 38 | 0 | 66 | 0 | 79/117 (67.5%) |
| Framework | 4 | 5 | 5 | 103 | 0 | 107/117 (91.5%) |
| Nationalism | 3 | 6 | 2 | 106 | 0 | 109/117 (93.2%) |
| Total binary fields | 20 | 49 | 7 | 275 | 0 | 295/351 (84.0%) |

There were 56 binary-field errors (49 false positives and 7 false negatives).
All three geo modes exactly matched the reference on 66/117 posts. The
reporting mode produced most geo false positives (38); framework had five
false negatives and nationalism had two.

## Full response and accounting

- All 38 fields: 4,021/4,446 correct (90.4%); 0 invalid fields.
- China national stance: 101/117 correct (86.3%); US national stance: 104/117
  correct (88.9%). These are multiclass exact matches, separate from the three
  binary geo-mode counts above.
- Physical calls: 117; retries: 0; transport errors: 0.
- Input tokens: 1,829,854. Estimated input cost: USD0.076853868 at the pinned
  USD0.042/M input rate. This is usage-based estimation, not an invoice.
- Median call latency: 0.316 seconds; complete arm elapsed: 41.3 seconds.
- Pre/post frozen, baseline, and protected-file verification passed.

Raw provider responses and per-call accounting are in `receipts/`; normalized
field scores are in `scores.json`, and incorrect rows are in
`disagreements.json`. The `geo_combined` convenience summary in `scores.json`
includes two multiclass stance fields and must not be used for binary confusion
counts. Use `geo_fields` and `geo_three_mode_exact_match` for the valid geo
summaries.
