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

Review-mode access requires an explicit review flag and either an authenticated owner on the existing staging email allowlist, or a staff user in local DEBUG mode. The live staging check found no existing owner account; using the existing owner allowlist lets the first Google sign-in review charts without granting staff/admin privileges. The whole staging site retains its existing owner allowlist. Public HTML and JSON exports consult frozen use grants plus current restrictions. Collection/import commands require explicit isolated-review invocation where policy is unresolved. All recurring source scheduling remains disabled.

## G3 input contract

Use `core.benchmark_forecast_inputs.forecast_inputs` with a timezone-aware cutoff, bounded mapping IDs and the intended use. Operational mode gates local observation, completed import, mapping review, contract creation/review and taxonomy creation; precise provider/effective timestamps must also precede the cutoff. A native date remains a date, never an invented midnight availability time. Later-imported archives cannot enter an operational replay merely because their effective period is old. Every returned observation/value/run ID, source context, time precision and contract hash must be pinned by the consuming forecast. Multiple eligible revisions are retained explicitly; downstream selection must be reproducible.

`retrospective_research` deliberately allows later evidence and returns `not_past_known_evidence=true`. It cannot validate historical trading performance. Native X post classifications are excluded from this reader. Prediction target, horizon, calibration, abstention, source-to-model rights, external-model egress, market matching, exchange automation and trading permissions remain G3-owned release decisions. This collector does not activate any of them.

## Coverage and interpretation limits

HF archive collection reached 683 of 685 available daily publications. 2025-01-09 and 2025-11-16 contain conflicting duplicate records and remain unresolved gaps. No arbitrary winner is selected. OpenRouter absence outside its top 50 is censored coverage, not zero. HF engagement reconstruction cannot recover removed likes or follows; one protected account endpoint remains inaccessible. Provider cutoff uncertainty stays explicit.

DeepSeek's prior rank uses the literal Arena `deepseek-v4-flash` entry, then `deepseek-v4.1-flash-max` from its first valid evaluation. The publisher's release comparison supports a manually reviewed successor interpretation, not an HF-declared weight derivation. The differently evaluated systems are labeled and the curve breaks at the switch. GLM has no reviewed predecessor entry and shows a gap. Rank percentages are not capability changes.

## Staging safety

The 421,275,363-byte staging dump was restored into `pw_benchmark_staging_rehearsal_20261007` on localhost:55436. All combined migrations passed; all ten inbound account relationships preserved native identities. The restored copy has 290,672 posts, 364,056 brand/post links, 88,741 X accounts and both existing editorial stories. See the checksum and row checks in rehearsal-receipt.json. This is a staging backup, not the production backup required before a later production release.

The staging data bundle re-resolves product and account IDs by exact provider identifiers and validates publisher ownership. Its replay uses the shared writer and records new import availability. It does not replace staging tables, accounts, posts, or G2 artifacts. The migration retains native-ID compatibility columns/triggers; rollback to older runtime code does not require destructive reverse migrations. Keep the backup and recover into a separate database if a restore becomes necessary.


## Staging deployment observations

The final code candidate is `1375d1c0efaa053d5d3d9cf1ca652e580ddcd330`. Render staging web, headline worker and jobs service report that revision. The synthesis worker and harvest cron remain suspended; both cron schedules remain `0 0 31 2 *`. Web and headline automatic deployment settings are restored to `no`. No production deployment was performed by this task.

The jobs build acquired the shared migration lock first and applied the account/measurement migration set through `0069_merge_20261007_0550` in about 26 minutes. The first web build exhausted its 900-second lock wait; its failure did not roll back or invalidate the jobs migration. The final web deployment ran after the lock was released. A future production release must select one migration runner, account for the observed duration and then deploy dependent services. Do not rely on several simultaneous builds waiting within 900 seconds.

Actual staging preservation checks found zero native-ID mismatches across all ten inbound Account relationships, with 290,672 posts, 88,741 X accounts and both editorial stories retained. The private editorial archive and API returned HTTP 200 using a disposable staff fixture; the fixture's role was restored immediately. Benchmark owner review separately passed with a nonstaff fixture on the existing staging email allowlist. Anonymous HTML and JSON requests redirect to sign-in.

Render's SSH shell and the running web process expose different session-signing keys. The verification fixture uses the running process's existing key in memory; neither key is changed or recorded. A normal owner Google sign-in uses the web process. This finding concerns constructing sessions from SSH, not a passed Google OAuth journey.

The historical replay retains deterministic run keys and uses the shared validated writer. It was paused at a completed-run boundary using its own source lock, then resumed in 50-run database transactions to reduce disk synchronization waits. Already completed runs are reused. This changes the temporary replay procedure, not provider parsing or application collection behavior.

The existing staging post snapshot is conservatively usable through October 3. October 4–6 remain unavailable in these comparisons. Provider history is imported separately; it does not refresh X posts. Release-history views are verified through October 6 with post gaps after October 3. Frozen exact-model views retain their stricter coverage rule: they are verified through October 3 and reject an explicit October 6 request with HTTP 400. The initial verification script requested October 6 for all presets; it was corrected to check both valid ranges and the preserved rejection, without changing application behavior.

A future production request must also reconcile newer `main` migrations and inbound Account relationships before PR #50 can be merged. Current staging integration does not establish production merge readiness or public/forecast/trading permission. The live-production backup requirement remains open; the backup taken here is staging-only.


## Verified staging result

All 3,890 retained source runs are imported: 3,868 HF, 14 Arena and 8 OpenRouter. They contain 1,371,105 observations and 2,056,891 metric values. The completed staging database is 4,613,412,543 bytes. The batched replay took 3,103.7 seconds, after the initial unbatched portion; production import planning should use this observed staging cost rather than the much faster local rehearsal.

All 1,152 checked provider datapoints across four comparisons match the retained-source reference, including raw values, baselines and percentages. Valid JSON requests took 3.6–8.0 seconds in the final check and returned private/no-store cache headers. Exact-view out-of-coverage requests return 400. The live browser completed 38 checks covering desktop/mobile layout, controls, raw rank, predecessor labels, the September 25 switch, GLM's explicit predecessor gap and evidence download. One early browser navigation returned a gateway error; a later intermediate range probe returned an unexpected status that was not captured. The complete final checks passed; no application exception was observed for those navigation events.

The disposable nonstaff review account, its three sessions and the staging upload directory were removed. No real owner account or credentials were changed. The existing hourly HF timing poll remains active on fuchitalee and retains its October 9 automatic stop.

See [deployment receipt](deployment-receipt.json), [live database receipt](staging-verification.json), [exact HTTP value comparison](live-http-values.json), [live browser evidence](live-history-browser.json) and [staging preservation checks](staging-preservation.json). The deployed code revision remains `1375d1c0`; a later documentation-only receipt commit does not require another deployment.
