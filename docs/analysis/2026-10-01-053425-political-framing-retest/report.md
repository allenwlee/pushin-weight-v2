# Political wording retest — Jev and 0731

117 identical original-text posts; 38 questions per post; the same frozen reference judgments. Only the three political-mode prompts changed. Both arms ran once with no model retries.

These are agreements with frozen agent-written reference labels, not independently human-verified accuracy. This known-cohort, post-feedback rerun has no simultaneous old-prompt control. The category rename and framework rewrite were tested together, so their separate effects are not measured.

## Primary result: three political modes

| Measure | Jev old | Jev new | 0731 old | 0731 new |
|---|---:|---:|---:|---:|
| Correct fields / total | 212/351 (60.4%) | 295/351 (84.0%) | 288/351 (82.1%) | 307/351 (87.5%) |
| All fields correct per post | 32/117 | 66/117 | 88/117 | 95/117 |
| True positive labels | 24 | 20 | 10 | 10 |
| False positive labels | 136 | 49 | 14 | 8 |
| Missed positive labels (including invalid) | 3 | 7 | 17 | 17 |
| Invalid fields | 0 | 0 | 39 | 25 |
| Valid but wrong fields | 139 | 56 | 24 | 19 |
| Posts with false positives | 84 | 46 | 11 | 7 |
| Positive-label precision | 15.0% | 29.0% | 41.7% | 55.6% |
| Positive-label recall | 88.9% | 74.1% | 37.0% | 37.0% |

False negatives include invalid answers on reference-positive fields. Invalid negative fields are also unsuccessful, so TP/FP/FN/TN alone do not cover every invalid field. There are 27 reference-positive political labels (13 reporting, 9 framework, 5 nationalism).

## Paired changes

| Provider | Previously wrong/invalid, now correct | Previously correct, now wrong/invalid | Net correct change |
|---|---:|---:|---:|
| jev | 90 | 7 | +83 |
| 0731 | 41 | 22 | +19 |

The complete correct/wrong/invalid transition matrices and paired valid-only views are in [comparison.json](comparison.json); valid-only views omit the same fields on both sides and do not predict what a repaired response would have said.

## Political subtype results

Each cell is `true positives / false positives / missed positives / invalid fields`.

| Subtype | Jev old | Jev new | 0731 old | 0731 new |
|---|---:|---:|---:|---:|
| reporting | 13 / 56 / 0 / 0 | 13 / 38 / 0 / 0 | 5 / 1 / 8 / 13 | 4 / 2 / 9 / 8 |
| framework | 8 / 74 / 1 / 0 | 4 / 5 / 5 / 0 | 4 / 10 / 5 / 13 | 5 / 4 / 4 / 9 |
| nationalism | 3 / 6 / 2 / 0 | 3 / 6 / 2 / 0 | 1 / 3 / 4 / 13 | 1 / 2 / 4 / 8 |

## What the Jev change did

Most of Jev's improvement came from the rewritten framework question: false positives fell from 74 to 5, but true positives also fell from 8 to 4. Reporting remained the main source of false tags (38), despite detecting all 13 reference-positive reporting labels. Nationalism's aggregate TP/FP/FN counts were unchanged, although some individual answers changed.

The four newly missed framework positives are `ja_16` (Europe versus US/China AI capability), `ko_01` (China's computing-resource limitation), `es_12` (Chinese AI price pressure on US firms), and `es_13` (politically triggered insecure code and open-model origin/security risk). These remain misses against the frozen references. Several illustrate a genuine scope question: wording centered on governments or relationships between countries can exclude national-technology and market framing that the old definition intended to include. This run does not relabel them after seeing answers.

A simple remaining error is `en_07`: “@NousResearch when are we getting deepseek flash 4.1?” Jev's framework score fell from 50% to 8%, but its political-reporting score stayed positive (51% to 52%). That shows the framework improvement did not repair reporting's boundary.

## All 38 fields (secondary)

| Measure | Jev old | Jev new | 0731 old | 0731 new |
|---|---:|---:|---:|---:|
| Correct fields / total | 3941/4446 (88.6%) | 4021/4446 (90.4%) | 3507/4446 (78.9%) | 3707/4446 (83.4%) |
| All fields correct per post | 2/117 | 3/117 | 2/117 | 2/117 |
| True positive labels | 419 | 415 | 174 | 199 |
| False positive labels | 308 | 225 | 59 | 61 |
| Missed positive labels (including invalid) | 116 | 120 | 361 | 336 |
| Invalid fields | 0 | 0 | 499 | 307 |
| Valid but wrong fields | 505 | 425 | 440 | 432 |
| Posts with false positives | 102 | 93 | 43 | 37 |
| Positive-label precision | 57.6% | 64.8% | 74.7% | 76.5% |
| Positive-label recall | 78.3% | 77.6% | 32.5% | 37.2% |

In this all-field table, accuracy and exact-post counts cover all 38 questions. TP/FP/FN, precision, and recall cover only the 34 binary questions, excluding the four categorical choices (outcome, sentiment, and two country stances).

## Unchanged questions and other class families

The other 35 questions were not rewritten. Changes in them can reflect different sampled outputs or interactions among questions; this design cannot attribute all differences to the prompt edit.

| Family | Jev old correct | Jev new correct | 0731 old correct | 0731 new correct |
|---|---:|---:|---:|---:|
| china_national_stance | 102/117 (invalid 0) | 101/117 (invalid 0) | 87/117 (invalid 15) | 92/117 (invalid 9) |
| geo | 212/351 (invalid 0) | 295/351 (invalid 0) | 288/351 (invalid 39) | 307/351 (invalid 25) |
| outcome | 104/117 (invalid 0) | 105/117 (invalid 0) | 93/117 (invalid 11) | 98/117 (invalid 7) |
| product | 554/585 (invalid 0) | 554/585 (invalid 0) | 480/585 (invalid 67) | 503/585 (invalid 40) |
| promotion | 540/585 (invalid 0) | 539/585 (invalid 0) | 493/585 (invalid 66) | 522/585 (invalid 40) |
| sentiment | 77/117 (invalid 0) | 78/117 (invalid 0) | 57/117 (invalid 11) | 62/117 (invalid 7) |
| topic | 748/819 (invalid 0) | 747/819 (invalid 0) | 633/819 (invalid 91) | 667/819 (invalid 58) |
| type | 1500/1638 (invalid 0) | 1498/1638 (invalid 0) | 1285/1638 (invalid 185) | 1362/1638 (invalid 112) |
| us_national_stance | 104/117 (invalid 0) | 104/117 (invalid 0) | 91/117 (invalid 14) | 94/117 (invalid 9) |

## Political results by source language

Each cell is correct political fields / total; invalid fields count as unsuccessful.

| Language | Jev old | Jev new | 0731 old | 0731 new |
|---|---:|---:|---:|---:|
| en | 29/60 | 48/60 | 50/60 | 55/60 |
| es | 41/57 | 48/57 | 46/57 | 51/57 |
| ja | 27/60 | 48/60 | 50/60 | 52/60 |
| ko | 47/60 | 56/60 | 50/60 | 52/60 |
| tr | 35/57 | 47/57 | 47/57 | 47/57 |
| zh-cn | 33/57 | 48/57 | 45/57 | 50/57 |

## Predeclared reference sensitivity

Exactly the prior exclusions are retained: `es_14` except promotion, `zh_cn_08` China stance, and `tr_19` political modes/national stances. No new exclusions or reference edits were made.

- jev: political correct fields 208/345 → 290/345.
- 0731: political correct fields 283/345 → 302/345.

## Cost, timing, and audit

- jev: 117 calls, model estimate US$0.076853868, median request 0.316s; 0 retries.
- 0731: 117 calls, model estimate US$0.0716500800000000009, median request 10.765s; 0 retries.

Model estimates are not invoices and exclude Render compute. Jev ran locally and 0731 on Render, so timing is observed end-to-end latency, not a controlled throughput benchmark. Caps were US$0.25 and 117 calls per provider; no probes or format-repair calls.

Frozen common input, reference, historical baseline, and protected application/test hashes were verified before reconciliation. No production prompt, application, database, translation/commentary configuration, scheduler, or deployment was changed for this experiment.

## Evidence

[Frozen contract](contract.md), [exact prompt diff](prompt-diff.json), [shared hashes](frozen.json), [full numerical comparison](comparison.json), [per-post political review](geo-cases.md), [Jev receipts and scores](jev/scores.json), [0731 receipts and scores](0731/scores.json).
