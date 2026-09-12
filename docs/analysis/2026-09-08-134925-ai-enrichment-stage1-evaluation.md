# Stage 1 deterministic contract evaluation

This evaluation establishes that the frozen Stage 1 parser accepts and
canonicalizes the intended stored shapes and rejects malformed boundaries
without manufacturing a classification. It does not measure semantic label
quality.

## Stored fixture result

The evaluator ran the 18 cases in
`tests/fixtures/classification_stage1_contract_v1.json` against
`parse_stage1_classifications`. The fixture SHA-256 is
`4ea6e4e8d145dad5ca5b8c3a4b62352dfacd222e69f070dd90db9fd8cda29af8`.

| Expected contract outcome | Cases | Matching outcomes |
| --- | ---: | ---: |
| Valid and canonicalized | 6 | 6 |
| Invalid and rejected | 12 | 12 |
| Total | 18 | 18 |

Expected contract outcomes therefore matched 18/18 cases. All 12 invalid
cases returned no parsed result, giving zero invalid-to-fallback coercions.
The six valid cases also matched their complete expected canonical results,
including array de-duplication while preserving first-seen order.

The parser inputs cover all ten post-type keys and all five product-label keys.
They include classified and context-missing outcomes; nullable scalar
judgments; empty and multiple label arrays; exclusive `other`; multiple brands;
and duplicate, missing, extra, and malformed brand results. English, Simplified
Chinese, Japanese, stored-quote, and local-parent tags are fixture metadata;
the parser does not read them or establish source-language semantics. Separate
cycle-envelope coverage in `test_cycle_classifier_model_propagation.py`
exercises stored quote and locally available parent text with provenance.

The verification command used the locked Stage 1 environment and the disposable
PostgreSQL database `pushinweight_stage1_u5`. It completed with 133 passing
tests, including the fixture evaluator, writer boundaries, retired adapter,
diagnostics, and health reader. Required PostgreSQL status was 12 executed,
zero skipped, and zero errors. The post-fetch smoke suite separately completed
44/44 tests. Test logs are retained outside the repository under
`~/.local/state/pushinweight-stage1-u5-tests/`.

## Evidence boundary

The fixture is synthetic and explicitly non-gold. These results prove parser
and publication-boundary behavior only. No heldout cohort was adjudicated, and
type, product-label, sentiment, or nationalism precision/recall remains
unmeasured. Those measurements and numeric semantic floors are required before
any production proposal, but are not evidence required for Stage 1 staging.

Two provider transports were unintentionally reached during an earlier failed
local wiring run because that test patched an obsolete constructor seam while
an inherited `DEEPSEEK_API_KEY` was present. The calls completed at
`2026-09-08T17:06:01.078426Z` for `post_translation_synthesis` and
`2026-09-08T17:06:02.991129Z` for `classification`. Their outputs are excluded
from every result above. The wiring test now patches the active factories and
both transformer functions directly; accepted reruns cleared provider and
Twitter credentials and denied non-loopback transport while retaining local
PostgreSQL access.
