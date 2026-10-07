# Benchmark staging review and G3 handoff

This candidate adds enforceable source-use decisions, a reviewed predecessor-ranking interpretation, and a cutoff-aware evidence reader. It integrates the actual G1/G2 staging revision f927652 without replacing staging posts or editorial content. The requested endpoint is Render staging only.

## Review scope and evidence

Review covers the benchmark amendments since 0e328c7a and interactions with the actual deployed G1/G2 code. Earlier collector/schema checks remain scoped to their recorded revisions; the combined schema was additionally migrated from a recovered, real staging backup. Reuse, quality and efficiency passes found no worthwhile behavior-preserving rewrite. Policy logic and series calculation are shared. Separate source-specific time rules and frozen contracts are intentional.

Per the owner's AGENTS.md tool mapping, review lenses run sequentially in the parent context. There is no independent reviewer or cross-model corroboration. Correctness, security, migration, performance, API/command contracts, testing and deployment are checked against the changed paths and the plan. No peer-review claim is made.

The corrected-publication check found that an obsolete successor row could start the switch too early. The implementation now resolves candidate dates with the same revision/removal rules used by the chart; a regression test covers the correction. G2's editorial packet and picture lookup now use native X identifiers after the generic Account migration; a real PostgreSQL regression protects that integration.

The PostgreSQL suite passed 217 tests, including 109 required database tests and zero skips/errors. The broader CI-equivalent account/catalog/staff/G2 regression net then passed 339 tests, including 189 required PostgreSQL tests with zero skips/errors. The final predecessor/export/access delta passed another 12 tests. Browser checks exercised DeepSeek and GLM, exact and history views, proxy visibility, raw rank, percentage mode, legend toggles, mobile width and evidence download. The standalone benchmark route is outside the homepage controls described by the existing Bridgewright declaration; declaration validation/prescription passed, but its 5,028 homepage obligations are not claimed as benchmark-browser coverage.

## Data-use decisions

| Actual route/dataset | Storage in this release | Public output / forecasts / trading |
| --- | --- | --- |
| OpenRouter rankings history | Explicit isolated review import of the complete available top-50 population; attribution retained | Require a reviewed per-use grant; none inferred from credentials or the download license |
| Arena official leaderboard dataset, text/overall, no style control | Tracked-brand cohort with publication and evaluated variant retained | Require reviewed public-chart/export/forecast grants and portable attribution |
| HF current repository/account metadata | Repository likes, rolling downloads and account follower states retained separately | Unresolved uses remain blocked |
| cfahlgren1/hub-stats community archive | Selected tracked repositories, immutable archive coordinates and Apache notice retained | Separate dataset decision required; archive rights do not establish rights to every upstream use |
| Surviving HF likes/follows | Reconstruction is labeled and omits removed relationships; never treated as historical observed snapshots | Excluded from operational historical forecasts |
| Existing X posts | Existing staging posts and brand joins are reused; no new post collection/import | Current classifications cannot establish what a past forecast knew; no G3 training/inference/trading clearance |

Review-mode access requires an authenticated staff user plus DEBUG or the staging environment, and an explicit review flag. The whole staging site retains its existing owner allowlist. Public HTML and JSON exports consult frozen use grants plus current restrictions. Collection/import commands require explicit isolated-review invocation where policy is unresolved. All recurring source scheduling remains disabled.

## G3 input contract

Use `core.benchmark_forecast_inputs.forecast_inputs` with a timezone-aware cutoff, bounded mapping IDs and the intended use. Operational mode gates local observation, completed import, mapping review, contract creation/review and taxonomy creation; precise provider/effective timestamps must also precede the cutoff. A native date remains a date, never an invented midnight availability time. Later-imported archives cannot enter an operational replay merely because their effective period is old. Every returned observation/value/run ID, source context, time precision and contract hash must be pinned by the consuming forecast. Multiple eligible revisions are retained explicitly; downstream selection must be reproducible.

`retrospective_research` deliberately allows later evidence and returns `not_past_known_evidence=true`. It cannot validate historical trading performance. Native X post classifications are excluded from this reader. Prediction target, horizon, calibration, abstention, source-to-model rights, external-model egress, market matching, exchange automation and trading permissions remain G3-owned release decisions. This collector does not activate any of them.

## Coverage and interpretation limits

HF archive collection reached 683 of 685 available daily publications. 2025-01-09 and 2025-11-16 contain conflicting duplicate records and remain unresolved gaps. No arbitrary winner is selected. OpenRouter absence outside its top 50 is censored coverage, not zero. HF engagement reconstruction cannot recover removed likes or follows; one protected account endpoint remains inaccessible. Provider cutoff uncertainty stays explicit.

DeepSeek's prior rank uses the literal Arena `deepseek-v4-flash` entry, then `deepseek-v4.1-flash-max` from its first valid evaluation. The publisher's release comparison supports a manually reviewed successor interpretation, not an HF-declared weight derivation. The differently evaluated systems are labeled and the curve breaks at the switch. GLM has no reviewed predecessor entry and shows a gap. Rank percentages are not capability changes.

## Staging safety

The 421,275,363-byte staging dump was restored into `pw_benchmark_staging_rehearsal_20261007` on localhost:55436. All combined migrations passed; all ten inbound account relationships preserved native identities. The restored copy has 290,672 posts, 364,056 brand/post links, 88,741 X accounts and both existing editorial stories. See the checksum and row checks in rehearsal-receipt.json. This is a staging backup, not the production backup required before a later production release.

The staging data bundle re-resolves product and account IDs by exact provider identifiers and validates publisher ownership. Its replay uses the shared writer and records new import availability. It does not replace staging tables, accounts, posts, or G2 artifacts. The migration retains native-ID compatibility columns/triggers; rollback to older runtime code does not require destructive reverse migrations. Keep the backup and recover into a separate database if a restore becomes necessary.
