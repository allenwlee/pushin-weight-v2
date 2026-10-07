# Four-source benchmark comparison — verified staging

The combined release-response chart and Arena panel are deployed on Render staging at `e28cbda9fa340db61ca4d86e738c5db08ac73260`. HF, OpenRouter, Arena and OpenCode share the existing measurement tables. Production and recurring collection remain unchanged. This directory publishes verification summaries; raw provider exports, screenshots, authenticated sessions and the recoverable database dump remain private on fuchitalee.

Review [DeepSeek](https://pushinweight-staging-web.onrender.com/benchmarks/1b91bd1b-a07d-47c9-a5ae-0e2089fc581e/deepseek-response/?end=2026-10-06) or [GLM](https://pushinweight-staging-web.onrender.com/benchmarks/1b91bd1b-a07d-47c9-a5ae-0e2089fc581e/glm-response/?end=2026-10-06) using the existing staging owner login. The Usage provider control selects OpenRouter or OpenCode. The chart compares brand posts, exact-product tokens and net change in the HF rolling counter, each normalized against its own mean over the same complete reference week. Zero means that reference average. Arena exposes the exact variant's raw score, confidence bounds, reported battle sample and rank; held values remain distinguishable from real publications.

## Database and import proof

The populated staging backup was restored locally before migration. Migrations `0072`, `0073` and `0074` reconcile main, rename `source_metrics` to `metrics`, and preserve newer official-company native X identifiers alongside generic account links. The renamed definition table retains its PostgreSQL object, constraints, indexes, IDs, sequence and all prior measured values. Account cutover is not reversed; backup/forward repair remains the production rollback approach.

Staging retains 290,672 posts, 364,056 post/brand links, 88,743 accounts and both editorial stories. After the bounded OpenCode import it contains 3,891 collection runs, 1,371,217 observations, 2,057,227 values and 18 metric definitions. Two reviewed exact products each contribute 56 available dates, August 13–October 7: 112 observations and 336 values. The six current-day values have an unknown end and remain partial. Replaying the import creates no duplicate measurements. Existing frozen comparisons reuse their measurements rather than copying the fact corpus.

OpenCode hourly commands preserve daily UTC totals and each endpoint revision; they do not manufacture hourly usage or sum successive snapshots. Approximate users/sessions are not deduplicated people across products or days. All collectors, source switches and reviewed contract scheduling remain disabled. Past operational cutoffs exclude this newly imported history. Unreviewed public charts, forecasts, numeric exports and exchange integration are denied.

## Verification

All four hosted workflows passed on the deployed code: benchmark 284/164 required PostgreSQL tests; company 310/250; editorial 257/138; staff 304/177. Required database skips/errors are zero. Suites overlap and are not summed. [Hosted results](hosted-code-checks.json) link the actual runs.

The live page passed 79 browser commands and 29 assertions on desktop/mobile, both products and both token providers. Controls preserve the reference week, show unavailable data honestly, and retain readable labels and accurate physical pointer selection. Score ticks now remain distinct on the ordinary numeric scale. [Browser summary](browser-summary.json) records scope without publishing source measurements.

Authenticated HTTP responses were independently checked against restored PostgreSQL calculations for all four presets, including raw/daily/smoothed/normalized values, reference dates and raw Arena evidence. Those checks ran at `d3d5f97b` and remain valid because subsequent changes affect only SVG rendering/browser assertions. Legacy comparisons return 200, anonymous HTML/JSON redirect to login, and responses are not cached. [HTTP summary](http-summary.json) retains the original tested revision rather than relabeling it as the final candidate.

Existing OpenRouter coverage remains its reported top-50 cohort. HF rolling-counter differences can be negative and are not new daily downloads. Posts after October 3 remain missing in this staging dataset. DeepSeek Arena data identifies the Max variant and begins September 25. The hourly HF experiment is still running toward its October 9 10:18 JST deadline; its observations do not yet establish an effective cutoff timezone. No post refresh, production migration or new recurring job was performed.

The actual staging web process reported the exact candidate SHA. Render reports LIVE deployments for web, headlines and jobs; worker connected/ready logs were observed, but a direct worker process SHA was not obtained. Original auto-deploy flags, reader settings, suspension states and inactive cron schedules were restored. The owned review session, temporary user and uploaded staging files were removed; existing owner users and allowlist were unchanged. The feature worktree, local preview and private backup are retained for review.

Review ran inline under the project's sequential agent rule. Claude returned a balance error and Grok timed out without a review; neither counts as independent review coverage. No actionable code finding remains. A future production release still requires owner authorization, compatibility with its then-current main revision, a verified live-production backup and one migration runner. Public/forecast/trading permissions and collection activation remain separate decisions.

## Receipts

- [Delivery and scope](delivery-receipt.json)
- [Staging database](stage-database-proof.json)
- [Exact deployment metadata](deployments.json)
- [Restored settings](settings-restored.json)
- [Owned-resource cleanup](review-cleanup.json)
- [Backup](backup-receipt.json) and [rename restore proof](restore-rename-proof.json)
- [Inline code review](code-review.json), [mobile review](mobile-ui-review.json), [Arena axis review](arena-axis-review.json)

The final documentation commit is a descendant of the verified code commit. It is pushed only to the feature branch; staging remains on `e28cbda9fa340db61ca4d86e738c5db08ac73260`. Later CI for that documentation head is recorded by the PR monitoring result. Historical receipts in this directory retain their original revision and verification scope.
