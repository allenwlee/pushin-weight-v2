# Benchmark code and schema — verified production release

Production is deployed at `dcbedf22d1cd70b4c0d54822980afda70b4f85c8`. All five active Render services report that revision; the actual web, headlines and synthesis processes agree. PR [#50](https://github.com/allenwlee/pushin-weight-v2/pull/50) merged when main advanced without force. The four hosted checks passed at this revision. The code is unchanged from the verified staging candidate; release commits changed documentation only.

Benchmark collection, review/readers and numeric output remain disabled. No production measurement history was imported. Historical measurements and review charts remain on staging. Public source use, forecasts, numeric exports and trading remain separate decisions. The existing HF timing poll is unchanged.

## Safe starting point for the product-type follow-up

Core migration leaf: `0074_official_company_generic_accounts`.

| Current stored product type | Products |
| --- | ---: |
| NULL / unclassified | 2,407 |
| `llm-model` | 0 |
| `other-ai-model` | 0 |
| `agent-harness` | 0 |

This release does not implement `model-llm`, `model-other`, `agent`, `harness` or `other`. The follow-up should start from the deployed revision and add a new migration after this leaf. Update Django ORM choices and PostgreSQL constraint `ck_product_type` together. Preserve existing taxonomy snapshot contents and frozen comparison contracts; new interpretation needs a new version rather than a rewrite of old evidence. Production has zero `taxonomy_versions` rows; the staging snapshots were not changed by this release.

All original fields of the 2,407 products, 2,407 HF catalog observations and 30 HF organizations match the restored pre-release backup. The fifteen shared tables are present, the definition table is `metrics`, and `accounts.account_key` is the account primary key. All twelve native/generic account-link checks return zero mismatches; no invalid index remains. Production definitions, contracts, observations and values are empty.

## Backup and migration

The live custom-format backup is 1,568,561,424 bytes, SHA-256 `45abf3648acdb1f0d8d3181f76b69dcc2476b640a038f47303990891548d949d`. Capture time is bounded by 03:52:21.781–03:52:27 UTC on October 8; the exact exported-snapshot clock was not forwarded by SSH. The archive was fully restored to a fresh owned PostgreSQL database: 151 tables, zero restore errors and verified critical row counts. All pending migrations then passed a full-data rehearsal with preserved native account/post checksums and expected framework permission additions.

A temporary web build guard acquired the fourteen existing account/HFOrg tables together, executed the unchanged transactional migrations on one connection and committed once. A separate concurrency proof refused a conflicting writer before any schema change. The live lock window was 04:25:56.553–05:04:55.975 UTC, 2,339.422 seconds (about 39 minutes). Requests touching those tables could wait; this release does not claim zero downtime. PostgreSQL documents how [these table locks conflict](https://www.postgresql.org/docs/18/sql-lock.html). The build stayed within [Render's build-command limit](https://render.com/docs/deploys).

The private dump is retained on authoritative fuchitalee, with no automatic deletion. It excludes writes after its captured snapshot. Recovery should restore into a fresh empty PostgreSQL 18 database and verify/configure the recovered deployment separately; do not overwrite live data or destructively reverse mixed-source accounts. The backup receipt records the tested command and retention. Render also describes [its managed recovery options](https://render.com/docs/postgresql-backups); no point-in-time recovery window was inspected or tested here.

## Production verification and limits

The live preservation manifest checks 92,186 original accounts, 304,199 original posts and eleven other native-reference sets; all saved rows and native references survive. Existing story/company/brand counts remain at least their baseline; ongoing writers may add rows. The public homepage loads, protected routes retain login redirects, and the existing custom admin renders its found/queue/history views plus one existing product proposal for an existing staff user. No user or authenticated browser session was created. A fresh Google OAuth browser journey was not tested.

The next natural scheduled harvest ran 05:15:56–05:20:47 UTC on the deployed revision. Its canonical summary hash verifies: 16 inserted posts, 5 updates and zero persistence failures. All twenty reported post IDs are present with matching native/generic X account links. The cycle remains degraded: classifier and list-reconciliation warnings existed before release; one older enrichment item was quarantined, with zero newly failed enrichment. These warnings are not claimed as repaired or fully healthy harvesting. No manual harvest, backfill or paid source probe was run.

The original build command, automatic deployment triggers, schedules and suspension states are restored. Retired beat/worker stay suspended. Temporary production verification uploads and the owned headless browser are removed; private backups, local rehearsal databases, existing previews and the feature worktree remain on fuchitalee for review/recovery. Final evidence is pushed only to the feature branch, without a documentation-only staging or production redeploy.

## Evidence

- [Delivery receipt](delivery-receipt.json), [final production/cleanup check](final-production-check.json), [exact deployments](deployments.json) and [merged PR](merged-pr-proof.json)
- [Product-type handoff](taxonomy-handoff.json) and [live database preservation](production-database-proof.json)
- [Backup receipt](backup-receipt.json), [full restore](restore-proof.json) and [migration rehearsal](rehearsal-migration-proof.json)
- [Transaction guard proof](cutover-guard-proof.json) and [live migration events](migration-events.json)
- [Worker process revisions](worker-runtime-proof.json), [scheduled harvest](harvest-proof.json) and [restored settings](settings-restored.json)
- [Public HTTP](public-http-proof.json), [homepage browser](browser-summary.json), [custom admin reads](admin-read-proof.json) and [hosted checks](hosted-release-checks.json)

Raw provider data, native identity manifests, full logs, credentials, authenticated-session material and the recoverable dump are excluded from these committed receipts.
