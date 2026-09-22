---
title: Rare-type query and Jev quality stop
date: 2026-09-22
status: blocked
plan: docs/plans/2026-09-21-081940-feat-combined-rare-type-extra-search-plan.md
query_version: rare-types-v2-2026-09-22
delivery_target: staging
enablement_approved: false
---

# Rare-type query and Jev quality stop

The current candidate must not be enabled or delivered to staging. The live query returned too few useful posts, and the captured Jev decisions reject too many positive examples. These are two independent failures, not a provider availability failure. No search lane, Post ingestion, domain-record creation, or deployment was activated.

## Live query

Two predeclared on-demand requests used the committed query and production-shaped renderer: one first page over 15 minutes, then one first page over seven days. Both ended at `2026-09-22T00:33:28Z`, used `Latest`, capped at 20 results, and had zero retries. No additional pages were purchased.

| Measurement | Result | Required |
| --- | --- | --- |
| 15-minute returned posts | 0 | Insufficient to establish freshness |
| Seven-day first-page raw/normalized posts | 20 / 20; truncated | At least 10 assessable posts |
| Independently read keepers | 5 / 20 = 25% | At least 60% |
| Already stored exact IDs | 1 / 20 = 5% | At most 20% |
| Mill / recruiter posts | 0 / 0 | Neither pattern above 20% of a page |
| Search credits | 315 estimated; invoice usage unknown | 600 reserved; plan ceiling 1,200 |

The five source-level keepers were one personnel announcement and four model-release reports. Jobs, events, and opportunities each had zero keepers. They are reference judgments about source posts, not Jev decisions or saved canonical records:

- Personnel: `2102167270726488207` — @nbaschez joining Notion to work on AI agents.
- Release reports: `2102173737189888212` — @CopyRebeldia; `2102164033814065606` — @reprynttAI; `2102160491472998895` — @tsukitama_ai; `2102158428856529401` — @Ai_hebrew.

Five further posts were ambiguous. Even counting all five as keepers gives only 50%, still below the unchanged 60% floor. Seven-day yield does not prove 15-minute coverage. The first page was truncated; it says nothing about all matching posts.

The exact-ID overlap lookup ran in a production read-only transaction at `2026-09-22T00:37:12.786372Z`; only `2102173737189888212` matched. This is the current 20-post cohort, not the historical `0/241924` measurement. Keeper yield including the empty-page floor was `5/315 = 0.015873` per estimated credit. At the checked tariff, the estimate is USD 0.00315; it is not a confirmed invoice charge.

Full captured public text, labels, query hashes, request bounds, and overlap identity are in [the live trial](2026-09-22-093328-rare-type-live-query-trial.json). No Jev calls were made on these 20 posts after the query failed.

## Jev reference corpus

The exact route `typesafe/jev-1.13-20260917` / `TypeSafe` passed one schema-only smoke, which is excluded from quality scoring. The frozen corpus then contained 56 cases: 28 positive and 28 negative/ambiguous, including at least five examples of each type and English, Chinese, and Japanese personnel cases. Synthetic reference labels remained outside the public state sent to Jev.

Frozen fixture SHA-256: `e7dc35afbdc38b15343789f54df67cf76c403acb3ef98967968b1d09016cd7fa`.

The collector attempted all 56 requests serially with a ten-second request limit and zero retries. Its terminal output was truncated during capture: 37 complete responses were saved, and 19 were lost. This was an evidence-capture error in this run, not a missing-provider-response claim. The collector did not journal each response to disk; future collection must do so before emitting terminal progress. No paid replay was used to hide or fill that gap.

The canonical U7 gate derives 35 `review_needed`, two `junk`, and zero `kept` from the 37 saved responses. Fourteen saved cases are reference positives; none was kept. Since there are only 14 other positive cases, even perfect decisions on all missing positives would give at most `14/28 = 50%` recall, below the required 90%. Exact full-corpus precision and recall are unavailable. Precision is undefined when no cases are kept, not zero.

Within the saved subset only, recall is 0/5 personnel, 0/5 jobs, 0/2 events, and 0/2 model releases. No opportunity-positive response was captured, so that subset's opportunity recall is undefined. All per-type precision values are undefined because no case was kept. These are partial-subset diagnostics, not a complete benchmark.

The implementation currently returns `review_needed` when *any* of its 15 probabilities is between 0.20 and 0.80, before checking definite junk or applicable positive types. Saved responses show intermediate values on unrelated questions, which can suppress otherwise relevant cases. That identifies a correction target; it does not establish that changing this rule alone would pass quality. Questions and routing must be revised and independently re-evaluated without weakening the quality floors.

Reported Jev cost was USD 0.004480350 including the earlier smoke; the upfront reservation including that smoke was USD 0.017458980, below the separate USD 0.25 assessment cap. The final total was captured, but 19 per-response records are missing, so full itemized cost reconciliation is unavailable.

See [schema smoke](2026-09-22-093040-rare-type-jev-schema-smoke.json) and [partial real corpus responses and missing-case list](2026-09-22-094002-rare-type-jev-corpus.json). Neither artifact is a passing assessment or owner approval.

## Local verification

U3 tooling is committed at `b20e1af`. The worker observed `1 passed, 18 failed` before the runtime module existed, then `25 passed` after implementation. Scoped Ruff passed. Parent verification passed all 174 tests in 93.56 seconds, including 80 required PostgreSQL tests with zero skips or errors:

```sh
env DATABASE_URL=postgres://fuchitalee@localhost:5432/pw_rare_feature_20260922 .venv/bin/pytest --reuse-db --basetemp=/Users/fuchitalee/development/pushin-weight-v2/.context/rare-feature-tests/host-u3-final tests/test_rare_type_quality_gate.py tests/test_jev_decisions.py tests/test_rare_type_search_schema.py tests/test_config.py tests/test_discovery_lanes.py tests/test_cycle_regression_net.py tests/test_cycle_tip_sweep.py tests/test_cycle_search_caps.py tests/test_harvest_cursor_lifecycle.py tests/test_rare_type_extra_search_query.py tests/test_trial_rare_type_extra_search.py -q
```

An additional provider-free audit passed the saved evidence through U3: the complete-assessment entry point correctly rejected the 19 missing predictions; scoring only the explicitly selected 37-case subset reproduced the outcomes and recall bound above. Each saved request hash matched canonical U7 request bytes. Saved per-response costs sum to USD 0.002903838; that is not the entire run's reported total.

The [machine-readable stop checkpoint](2026-09-22-095250-rare-type-quality-stop.json) is deliberately not a passing `rare-type-quality-assessment-v1` artifact. It cannot serve as an enablement receipt.

## Resume boundary

Keep the existing checkout, feature branch, frozen failed evidence, and unrelated dirty files. U1/U2/U4/U5/U7 are locally implemented and verified. U3's scorer can test assessment logic, but U3 acceptance has failed. U6 and U8–U14 remain unimplemented; there is no end-to-end source-to-record or staging proof.

Next planning work should tighten employment/release query phrases and revise Jev questions plus type-specific uncertainty handling. Preserve one search, three language families, the broad AI-related organization scope, cost bounds, and all quality floors. Version changed inputs, add newly observed false positives to a separate future reference set, and journal complete responses before another explicitly bounded assessment. A changed prompt tested on the same development cases alone is not independent quality evidence.

Only a passing complete assessment and explicit operator yield acceptance can reopen enablement. Final simplification, review, pull request, CI, browser checks, and exact-SHA staging verification have not run for this unfinished feature.
