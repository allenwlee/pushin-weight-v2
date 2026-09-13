# U18 v27 saved-response evidence-reuse replay

- Recorded: 2026-09-13T23:21:00+09:00
- Scope: the 30-row owner-reference DeepSeek Pro reviewer diagnostic only
- Result: parser recovery succeeded; the diagnostic thresholds still failed
- New transport: 0 attempts, 0 tokens, 0 USD

## Failure

The original run consumed seven bounded transport attempts across six logical
review batches. One batch was retried after the parser rejected two otherwise
schema-valid replacement rows. Each row reported three derived changes
(`unsupported_post_type`, `unsupported_product_label`, and `sentiment`) and
two exact source quotes. The prior parser required at least as many evidence
rows as derived change reasons.

That is an unsound invariant. Evidence supports the complete corrected
judgment, while `change_reasons` records which fields differ from the saved
primary classification. One exact quote can support several changed fields.
Both rejected rows supplied non-empty, exact substrings of their own source;
no quote was fabricated, cross-row, or context-mismatched.

The provider prompt was unchanged. The parser and selector advanced from
`stage1-selector-v27-owner-calibrated-review-authoritative-v1` to
`stage1-selector-v27-owner-calibrated-evidence-reuse-v2`. A replacement still
requires at least one exact source- or context-bound quote, and malformed or
missing evidence still fails closed.

## Immutable replay inputs

The replay budget is [2026-09-13-232000-u18-runtime-v27-evidence-reuse-replay-budget.json](2026-09-13-232000-u18-runtime-v27-evidence-reuse-replay-budget.json), SHA-256
`cb78dda9dad7de581a261d6242d63858c5f7ca35af02f1e4880c180250c7b132`.
It pins the original cohort, owner-reference subset, original budget, original
usage record, and the six selected raw responses. The failed first response
and all original responses remain preserved; the replay selects the original
batch's second response without modifying it.

The original usage record remains SHA-256
`08f51d1543aa6c5228277177c2a27de838dffc6f7bf245a8368844824885ca14`.
The new budget has hard caps of zero requests, zero transport attempts, zero
input/output tokens, and `$0`.

Run the replay with:

```bash
.venv/bin/python scripts/u18_runtime_pro_reviewer_pilot.py replay-saved \
  --budget docs/analysis/2026-09-13-232000-u18-runtime-v27-evidence-reuse-replay-budget.json
```

The command only verifies SHA-256-pinned local inputs, reparses saved JSON,
and writes a new ignored local candidate/evaluation pair. It never constructs
the transport client or reads provider credentials.

## Replay result

The six saved responses parsed as 30/30 rows under the corrected invariant.
The ignored local artifacts are:

- Candidate: `.context/u18/u18-v27-evidence-reuse-replay-v1/candidate.json`, SHA-256 `8ae379649c1551b764ccb0fa2d451b0e18af889a6e0dcb8a7d3ee90392474535`
- Evaluation: `.context/u18/u18-v27-evidence-reuse-replay-v1/evaluation.json`, SHA-256 `2f7c8bdeec2e7b6c7ce65ee1a0fe6dcd3dc00cd576bd2595979b8fc402646108`

| Measure | Result | Threshold | Status |
| --- | ---: | ---: | --- |
| Post-type exact set | 19/30 (63.33%) | 70% | Fail |
| Product-label exact set | 23/30 (76.67%) | 85% | Fail |
| Outcome accuracy | 29/30 (96.67%) | 90% | Pass |
| Sentiment accuracy | 20/30 (66.67%) | — | Diagnostic only |

Post-type exact set by language: EN 3/10 (30%), JA 8/10 (80%), ZH-CN 7/10
(70%). Outcome accuracy by language: EN 90%, JA 100%, ZH-CN 100%.

The replay removes a parser-induced invalid-response failure. It does not make
the reviewer pass its preregistered owner-reference diagnostic, does not create
human-grounded accuracy, and does not authorize any further provider work or
release decision.

## Verification

- `git diff --check`
- `jq empty docs/analysis/2026-09-13-232000-u18-runtime-v27-evidence-reuse-replay-budget.json`
- `.venv/bin/pytest -q tests/test_u18_runtime_pro_reviewer_pilot.py tests/test_classify_batch_pragmatics_full.py` — 29 passed
- Focused selector/parser suite — 60 passed; 18 PostgreSQL-dependent tests skipped because `DATABASE_URL` is unset

The new regression sends a replacement with two derived reasons and one exact
quote through the real primary → completeness-review call path. It passes
without invoking a repair transport call.

The replay candidate records the immutable budget's `frozen_at` value rather
than wall-clock execution time. Two consecutive credential-cleared replays
produced the same candidate and evaluation hashes, so the documented command
is reproducible as well as transport-free.
