---
title: Account User About Enrichment Staging Pilot - Plan
type: feat
date: 2026-08-29
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: session-split-from-feed-country-flags
execution: code
deepened: 2026-08-29
ollija:
  change_id: feat-feed-country-flags-disclosure-2026-08-29-093958
  branch: feat/feed-country-flags-disclosure
  workflow: lfg
  delivery_target: staging
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `./bin/ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-country-flags-disclosure`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-country-flags-disclosure/docs/plans/2026-08-29-093958-feat-feed-country-flags-disclosure-plan.md`
- Change: `feat-feed-country-flags-disclosure-2026-08-29-093958`
- Branch: `feat/feed-country-flags-disclosure`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-country-flags-disclosure/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-country-flags-disclosure/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
- Delivery target: `staging`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the Render deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.

### Failure handling

- Never promote a staging candidate whose automated checks failed.
- Implementation failures return to the parent implementation workflow for diagnosis, correction, recommit, and restaging.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

- This plan supersedes the enrichment portion of the former combined feed-country plan. The flag and headline work is deferred to `docs/plans/2026-08-29-223000-feed-country-flags-disclosure-successor-plan.md` and is not part of this LFG run.
- Apply and verify the Django migration on the isolated staging database before making a paid User About call.
- Run the first paid population only from the staging environment against 100 unique staging `Account` rows with callable handles. Permit at most 110 attempts and at most 1,980 credits. Apply accepted values only to the staging database.
- Owner follow-up on 2026-08-30 authorizes one schema-diagnostic staging call, a parser correction backed by redacted path/type evidence, and one replacement 100-Account staging pilot. Across the original failed call, diagnostic call, and replacement pilot, remain within the original cumulative ceiling of 110 attempts and 1,980 projected credits. Schema diagnostics may contain JSON paths, field names, and JSON types only; they must not contain response values, handles, Account IDs, URLs, credentials, headers, connection strings, or raw payloads. Correct the mirrored external-vendor endpoint reference from the observed schema before the replacement pilot.
- Stop after the staging pilot report. Do not migrate or write production, run a full-account population, schedule User About, or ship feed UI under this delivery target.

# Account User About Enrichment Staging Pilot

## Goal Capsule

- **Objective:** Give the operator verified evidence that X About-this-account data can safely enrich PushinWeight Accounts before any production migration, full population, or feed dependency is authorized.
- **Means:** Add typed Account fields, a model-owned observation gateway, and a bounded User About command; deploy the migration to staging; then populate 100 staging Accounts under hard call, credit, time, and schema-drift limits (KTD10-KTD18).
- **Authority:** The Product Contract governs stored data and write semantics. The official TwitterAPI User About schema and current pricing govern the provider boundary. The Ollija Delivery Guide and Delivery Exceptions govern staging-only delivery.
- **Execution profile:** Build and test with fakes locally. Push one exact candidate to staging. Let `build.sh` apply the migration under the existing cluster lock. Run one explicit staging-only paid pilot and emit aggregate evidence.
- **Stop conditions:** Stop before a provider call if the staging service, database identity, API credential, balance-derived QPS, account sample, or migration state is not verified. Stop during the pilot on unknown response leaves, type drift, returned-ID mismatch, authentication failure, open circuit, 110 attempts, a projected spend above 1,980 credits, or 30 minutes of wall time.
- **Tail ownership:** LFG owns implementation, review, commits, PR creation, exact-SHA staging delivery, the capped staging pilot, and CI observation. The owner retains production migration, full population, and UI authorization.

---

## Product Contract

### Summary

Persist TwitterAPI User About account data in typed `Account` fields without a raw JSON column. Route User About, post-author, list-member, and seed observations through one model-owned validation path. Prove the migration and a 100-account paid population on the isolated staging database, then stop for review.

### Problem Frame

`Account.location` and `Post.author_location` are optional free-form profile text. `Post.place.country_code` is a rare post geotag. Neither represents the About-this-account value selected for country flags.

TwitterAPI exposes `about_profile.account_based_in` through `/twitter/user_about`, one handle per call. The production-sized population is roughly 59,225 calls before retries. The endpoint also returns profile identity, creation, verification, affiliate-label, About, and identity-label values. Storing only country would discard account data already paid for; storing a raw response would weaken queryability and validation.

The Django harvester currently writes Account snapshots directly with `update_or_create`. Missing booleans can be coerced to false, malformed values can replace good values, and `followers_fetched_at` is not advanced by the Django post path. A paid backfill must not amplify those defects.

### Key Decisions

- PD4. **Use About-this-account as the account-country source.** (session-settled: user-approved — chosen over profile location and post geotags: `account_based_in` is the selected X-reported account signal.) Governs R6 and R21.
- PD6. **Deliver and test only on staging.** (session-settled: user-directed — chosen over production delivery: migration, paid calls, and writes must be proven on the isolated staging database first.) Governs R15-R18.
- PD9. **Persist typed fields, not raw JSON.** (session-settled: user-directed — chosen over one raw response column: every account-valued response leaf should be queryable with an appropriate type.) Governs R12 and R19.
- PD10. **Evaluate about 100 calls before a larger run.** (session-settled: user-directed — chosen over immediate population of every Account: actual schema, yield, time, and credit burn must be confirmed first.) Governs R16-R18 and R20.
- PD11. **Allow valid post observations to refresh shared mutable fields.** (session-settled: user-directed — chosen over freezing the User About snapshot or adding history now: post author payloads are generally fresher.) Governs R22 and R24.
- PD12. **Validate at the Django model boundary.** (session-settled: user-directed — chosen over parser-only validation and direct ORM defaults: faulty observations must not clobber good Account values.) Governs R22-R24.

### Requirements

**Typed persistence**

- R6. Derive `Account.country_code` only from an exact supported two-letter code or exact canonical English country name in the approved 197-country source. Preserve the exact provider value separately. Do not infer from free-form profile location, post geotags, cities, regions, or fuzzy matches.
- R12. Give every documented leaf under a successful User About `data` object one typed Account destination in the field map below. Reuse semantically identical existing fields and add only missing columns.
- R19. Add no raw User About JSON column. Flatten nested label objects into typed nullable fields, convert camelCase leaves to snake_case, and keep concise provider terminology.
- R21. Reject the full User About observation on returned-ID mismatch, unknown response leaf, or documented type mismatch. Record the failure without an Account write. An otherwise valid response whose exact `account_based_in` value is unsupported still checkpoints and stores that exact value, but derives no `country_code`.

**Account write ownership and freshness**

- R22. Apply serialized last-valid-write semantics to shared mutable fields. An explicitly present, valid post or list value may replace the current value. A missing or invalid value may not clear, false-coerce, or replace it. `created_at` is fill-once and conflicts are reported.
- R23. Every current Django Account writer must submit source, observation time, field presence, and candidates through one model-owned gateway. Reject identity mismatch for the whole observation. Reject malformed independent fields or coupled label groups without blocking other valid Account fields or the related Post write.
- R24. An accepted explicit post `followers_count` observation updates `followers_fetched_at` in the same transaction even when the count is unchanged. Missing or rejected follower values update neither field.

**Bounded staging pilot**

- R15. Deploy only to the exact-SHA staging lane. Apply the migration to staging and verify its database schema before paid calls. Do not mutate `main`, production services, or the production database.
- R16. Select 100 unique staging Accounts with nonblank handles using a recorded seed. Call `/twitter/user_about` once per selected handle. Permit at most 110 attempts, a projected spend of 1,980 credits under the published profile rate, 30 minutes of wall time, and the lower of 5 QPS or the verified balance-derived provider allowance.
- R17. Apply only accepted responses to their matching staging Account rows. Produce timestamped JSON and Markdown reports with sample definition, response distribution, leaf coverage, country yield, `location_accurate` and `source` distributions, rejections, retries, latency percentiles, wall time, effective QPS, credits, and projected full-run cost and duration.
- R18. Stop after the 100-account staging report. Continuing to a production migration, a larger provider run, or the UI successor requires a later owner decision.
- R20. The command is default-dry-run, explicit-apply, resumable, idempotent for successful empty results, globally rate-limited, bounded by account, attempt, credit, and wall-time budgets, and absent from cron, Celery beat, and `run_cycle`.
- R25. A later production apply requires a current encrypted pre-write Account snapshot, row count, digest, and disposable restore proof. This staging plan documents that gate but does not execute it.
- R26. Read the TwitterAPI credential only from the staging service's managed environment. Fail closed when it is absent or invalid. Never accept it as a command argument or write it, request headers, connection strings, handles, Account IDs, or raw provider payloads to tracked reports or normal logs.

### Acceptance Examples

- AE9. **Capped staging population**
  - **Covers:** R15-R18 and R20.
  - **Given:** The exact candidate migration is applied to staging and 100 unique staging Accounts are selected with a recorded seed.
  - **When:** The operator runs explicit apply and two calls retry.
  - **Then:** The report records 100 selected Accounts, 102 attempts, exact writes and rejections, wall time, and credits without any production write.
- AE10. **Identity or schema drift**
  - **Covers:** R21.
  - **Given:** A response returns another user ID, an undocumented leaf, or a documented field with the wrong type.
  - **When:** The strict parser evaluates it.
  - **Then:** No Account field or fetched timestamp changes and the pilot stops with a redacted reason.
- AE17. **Unsupported country value remains observable**
  - **Covers:** R6 and R21.
  - **Given:** A structurally valid matching response contains an exact `account_based_in` value that is absent from the approved country source.
  - **When:** The strict parser and Account gateway accept the response.
  - **Then:** The exact provider value and fetched timestamp are stored, `country_code` remains unchanged or null, the outcome is counted as unmapped, and the row is not retried merely because normalization failed.
- AE11. **Typed deduplicated persistence**
  - **Covers:** R6, R12, and R19.
  - **Given:** A complete documented response.
  - **When:** The Account observation gateway accepts it.
  - **Then:** Shared fields and every missing typed destination are populated, exact country normalization derives `country_code`, and no Account JSON field exists.
- AE12. **Successful empty lookup is resumable**
  - **Covers:** R20.
  - **Given:** A successful response omits optional About and label values.
  - **When:** The command checkpoints the row and restarts.
  - **Then:** `account_based_in_fetched_at` records completion and default missing-only selection does not charge for it again.
- AE13. **Newer post values can win safely**
  - **Covers:** R22-R23.
  - **Given:** User About populated shared mutable fields and About-only country fields.
  - **When:** A later post explicitly carries a new valid handle, display name, blue-verification value, and affiliate label.
  - **Then:** Shared values change while About-only values and their fetched time remain intact.
- AE14. **Missing post fields do not erase**
  - **Covers:** R22-R23.
  - **Given:** An Account has non-null shared values.
  - **When:** A later author payload omits blue verification or affiliate label.
  - **Then:** Existing values remain unchanged.
- AE15. **Faulty post fields are contained**
  - **Covers:** R22-R23.
  - **Given:** A post carries a malformed handle, negative count, invalid URL, or future creation time alongside one valid display-name update.
  - **When:** The production post-to-Account call chain runs.
  - **Then:** The gateway preserves rejected fields, accepts the display name, records redacted rejection reasons, and still persists the Post.
- AE16. **Follower observation freshness**
  - **Covers:** R23-R24.
  - **Given:** An Account has follower count 1,000 observed at T1.
  - **When:** A post at T2 explicitly supplies 1,000 and a post at T3 omits or malforms the count.
  - **Then:** The count remains 1,000, `followers_fetched_at` advances to T2, and T3 changes neither field.

### Scope Boundaries

**In scope**

- User About protocol, strict parsing, shared pacing, typed Account columns, exact country normalization, and the model-owned observation gateway.
- Current Account writers in post ingestion, list reconciliation, and seed loading.
- A default-dry-run management command and one 100-account staging apply.
- Exact-SHA staging deployment, staging migration verification, aggregate pilot evidence, and a production recovery gate in the runbook.

### Deferred to Follow-Up Work

- Production migration and full Account population.
- Country-flag rendering, localized country names, headline disclosure, Bridgewright UI assurance, and reference-page movement. These belong to `docs/plans/2026-08-29-223000-feed-country-flags-disclosure-successor-plan.md`.
- Account observation history or per-field timestamps beyond `followers_fetched_at` and `account_based_in_fetched_at`.
- Scheduling or recurring refresh of User About.

**Outside this plan**

- Treating `account_based_in` as nationality, citizenship, permanent residence, or a guarantee of physical location.
- Changing the seven-call search plan, live cursors, metrics refresh, headline worker, production scheduler, or retired v1 stack.

### Product Contract Preservation

Changed by explicit owner direction: the former combined plan's UI requirements and units moved to the successor plan. The enrichment requirements, stable R/AE/KTD/U IDs, typed field map, and validation semantics retain their prior meaning. The latest direction replaces the former read-only production pilot with a migration-first, write-enabled staging pilot.

---

## Planning Contract

### Key Technical Decisions

- KTD10. **Flatten every documented User About `data` leaf into a typed Account destination.** (session-settled: user-directed — chosen over raw JSON and redundant account-prefixed names: provider-shaped fields should remain queryable and type-safe.) Reuse semantic matches, snake-case camelCase, and drop structural wrappers. Implements PD9, R12, and R19.
- KTD11. **Extend the hardened TwitterAPI caller instead of creating a parallel client.** Reuse one `aiohttp` session, a bounded connector, Retry-After, jitter, split timeouts, and circuit breaking from `monitor/twitterapi/caller.py`. Add one aggregate pace gate capped by the current balance-derived provider QPS and by the command's lower operator cap. Implements R16 and R20.
- KTD12. **Make Account own observation validation and application.** (session-settled: user-directed — chosen over parser-only validation and direct `update_or_create` defaults: every writer needs the same protection.) A transactional model gateway accepts explicitly present fields, validates the proposed subset and cross-field invariants, locks only the target row during comparison and apply, and returns structured applied, unchanged, and rejected outcomes. Implements PD12 and R22-R24.
- KTD13. **Checkpoint successful responses, including success-empty.** Set `account_based_in_fetched_at` after an accepted provider success even when optional About fields are absent. Leave transport, provider, identity, or schema failures retryable. Implements R20-R21.
- KTD14. **Use a migration-first staging pilot.** (session-settled: user-directed — chosen over testing migration or API writes on production: both must be proven against the isolated staging database.) The candidate deploy applies its migration through `build.sh` before the command can select or update staging Accounts. Implements PD6 and R15-R18.
- KTD15. **Use field presence and serialized last-valid-write ownership.** (session-settled: user-directed — chosen over preserving User About snapshots or adding change history: later valid post values should refresh overlapping mutable facts.) “Latest” means the most recently accepted database commit, not event-time arbitration. `created_at` is fill-once. Implements PD11 and R22.
- KTD16. **Activate the existing follower freshness field.** Update `followers_fetched_at` for each accepted explicit follower observation, including an unchanged count. PostgreSQL does not provide a durable per-column last-write timestamp. Implements R24.
- KTD17. **Keep request envelopes out of Account.** Store `status`, `msg`, HTTP status, attempt, latency, and error reason in the run report or dead letter. They describe a call, not an account. Implements R19-R21.
- KTD18. **Reconcile paid usage with provider evidence.** Before each call, refuse an attempt whose published-rate projection would exceed 1,980 credits. Record application attempts and expected pricing, then reconcile the exact UTC pilot window to the TwitterAPI Recent API Calls ledger when dashboard credentials are available. A missing or inconsistent ledger makes the cost result inconclusive and stops the run after staging writes; it never authorizes expansion. Implements PD10 and R17-R18.
- KTD19. **Generate a backend-only country map from the already approved source.** Build code and canonical English-name normalization from `docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json` without moving the review page, generating the runtime SVG sprite, or changing feed code. This keeps R6 executable while preserving the UI successor boundary.

### Typed Account Column and Writer Map

A successful `data.id` must match `Account.author_id`. Nullable types reflect optional provider objects. URL fields use a 2,048-character limit. `Post` means the tweet author payload in `x_monitor/apify.py` and `monitor/cycle.py`. `List` means `monitor/list_membership.py`.

| TwitterAPI path | Account column | Django type | Valid writers |
| --- | --- | --- | --- |
| `data.id` | `author_id` | existing `TextField(primary_key=True)` | Identity key; About validates only |
| `data.name` | `display_name` | existing `TextField(null=True)` | About, Post, List |
| `data.userName` | `handle` | existing `CharField(64, null=True)` | About, Post, List |
| `data.createdAt` | `created_at` | `DateTimeField(null=True)` | About or Post fills null |
| `data.isVerified` | `verified` | existing `BooleanField` | About or explicit Post; deduplicated shared field |
| `data.isBlueVerified` | `is_blue_verified` | existing `BooleanField(null=True)` | About or explicit Post |
| `data.protected` | `protected` | `BooleanField(null=True)` | About or explicit Post |
| `data.profilePicture` | `profile_picture` | existing `TextField(null=True)` | About or explicit Post; deduplicated shared field |
| `data.verification_info.id` | `verification_info_id` | `CharField(128, null=True)` | About only |
| `data.verification_info.is_identity_verified` | `verification_info_is_identity_verified` | `BooleanField(null=True)` | About only |
| `data.affiliates_highlighted_label.label.badge.url` | `affiliate_label_badge_url` | `URLField(2048, null=True)` | About or explicit Post label |
| `data.affiliates_highlighted_label.label.description` | `affiliate_label_description` | `TextField(null=True)` | About or explicit Post label |
| `data.affiliates_highlighted_label.label.url.url` | `affiliate_label_url` | `URLField(2048, null=True)` | About or explicit Post label |
| `data.affiliates_highlighted_label.label.url.urlType` | `affiliate_label_url_type` | `CharField(128, null=True)` | About or explicit Post label |
| `data.affiliates_highlighted_label.label.userLabelDisplayType` | `affiliate_label_user_label_display_type` | `CharField(128, null=True)` | About or explicit Post label |
| `data.affiliates_highlighted_label.label.userLabelType` | `affiliate_label_user_label_type` | `CharField(128, null=True)` | About or explicit Post label |
| `data.about_profile.account_based_in` | `account_based_in` | `TextField(null=True)` | About only |
| `data.about_profile.location_accurate` | `location_accurate` | `BooleanField(null=True)` | About only |
| `data.about_profile.created_country_accurate` | `created_country_accurate` | `BooleanField(null=True)` | About only |
| `data.about_profile.learn_more_url` | `learn_more_url` | `URLField(2048, null=True)` | About only |
| `data.about_profile.affiliate_username` | `affiliate_username` | `CharField(64, null=True)` | About only |
| `data.about_profile.source` | `source` | `CharField(128, null=True)` | About only |
| `data.about_profile.username_changes.count` | `username_changes_count` | `PositiveIntegerField(null=True)` | About only; strictly parse numeric string |
| `data.about_profile.username_changes.last_changed_at_msec` | `username_changes_last_changed_at_msec` | `PositiveBigIntegerField(null=True)` | About only; strictly parse numeric-string epoch milliseconds |
| `data.identity_profile_labels_highlighted_label.label.badge.url` | `identity_profile_label_badge_url` | `URLField(2048, null=True)` | About only |
| `data.identity_profile_labels_highlighted_label.label.description` | `identity_profile_label_description` | `TextField(null=True)` | About only |
| `data.identity_profile_labels_highlighted_label.label.url.url` | `identity_profile_label_url` | `URLField(2048, null=True)` | About only |
| `data.identity_profile_labels_highlighted_label.label.url.urlType` | `identity_profile_label_url_type` | `CharField(128, null=True)` | About only |
| `data.identity_profile_labels_highlighted_label.label.userLabelDisplayType` | `identity_profile_label_user_label_display_type` | `CharField(128, null=True)` | About only |
| `data.identity_profile_labels_highlighted_label.label.userLabelType` | `identity_profile_label_user_label_type` | `CharField(128, null=True)` | About only |
| Exact supported country derived from About | `country_code` | `CharField(2, null=True, db_index=True)` | Derived with accepted About only |
| Successful About observation time | `account_based_in_fetched_at` | `DateTimeField(null=True)` | About only |

### Account Observation Validation

| Field family | Model rule | Rejection behavior |
| --- | --- | --- |
| Identity | Nonblank immutable `author_id` must match the selected row | Reject the whole observation |
| Handle | Trimmed nonblank string without `@`, whitespace, or controls; fits the field | Preserve the current handle |
| Display/profile text | Correct string type, valid Unicode, control-free, and field-length safe | Preserve the affected field |
| Counts | Integer but not Boolean, nonnegative, and database-range safe | Preserve the affected count |
| Booleans | Exact Boolean when present; no string or integer coercion | Preserve the affected Boolean |
| URLs | Null or absolute HTTP(S) URL within 2,048 characters | Preserve the affected URL or label group |
| `created_at` | Timezone-aware, not before X launch, not beyond observation time plus tolerance, and fill-once | Preserve current value and report conflict |
| Affiliate/identity labels | Validate six related leaves as one group; explicit empty object may clear the group | Preserve the whole current group |
| About provider strings | Correct type, trimmed, control-free, and within pilot-observed limits | Preserve the affected field |
| `country_code` | Uppercase supported two-letter code | Preserve the current code or null; count an exact-but-unsupported About value as unmapped without rejecting the otherwise valid observation |

### High-Level Technical Design

```mermaid
sequenceDiagram
  participant L as LFG
  participant S as Staging deploy
  participant D as Staging PostgreSQL
  participant T as TwitterAPI
  L->>S: Push exact candidate SHA
  S->>D: Apply migration under cluster lock
  L->>D: Verify columns and migration receipt
  L->>S: Invoke explicit 100-account apply
  S->>D: Select seeded staging Accounts
  S->>T: Globally paced User About calls
  T-->>S: Typed responses or failures
  S->>D: Validate and apply accepted observations
  S-->>L: Aggregate report and hard stop
```

```mermaid
flowchart TB
  A[User About response] --> G[Account observation gateway]
  P[Post author payload] --> G
  L[List member payload] --> G
  E[Seed account payload] --> G
  G --> V{Identity and field validation}
  V -->|accepted subset| C[Typed Account columns]
  V -->|rejected field or group| R[Redacted receipt counters]
  C --> F[followers_fetched_at]
  C --> B[account_based_in_fetched_at]
  C --> K[country_code]
```

### Assumptions

- Staging contains at least 100 unique Accounts with nonblank handles. If not, use the existing guarded staging refresh procedure before the pilot; never read handles directly from production inside the command.
- The public endpoint example checked on 2026-08-29 omitted six leaves present in the value-free live schema probe on 2026-08-30. The corrected field map and `docs/external_vendors/twitterapi_docs/endpoint/get_user_about.md` are the current project reference; strict parsing remains the drift detector.
- TwitterAPI pricing checked on 2026-08-29 is 18 credits per returned profile, with a 15-credit minimum per call and USD 1 per 100,000 credits. The 110-attempt cap therefore budgets at most 1,980 credits under the profile-rate assumption.
- The provider QPS ceiling depends on account balance. The command uses the lower of its explicit operator cap and the verified provider allowance. It never relies on the stale 200-QPS note in repository research.
- `account_based_in` is stored as the provider reports it. This plan does not independently verify how X calculates the value.
- A successful response with absent optional objects is a completed lookup. Transport, HTTP, provider-status, identity, and schema failures are not.

### System-Wide Impact

- **Schema:** `Account` gains 26 typed fields across migrations 0020 and 0021. The four live-only additions are additive and nullable; `isVerified` and `profilePicture` reuse existing shared fields.
- **Country identity:** A generated backend-only code/name map supports R6. It carries no SVG, zh-CN display name, template, CSS, or client rendering.
- **Writers:** Post, list, seed, and User About inputs share one Account write boundary.
- **Freshness:** `followers_fetched_at` becomes active. `account_based_in_fetched_at` records successful About lookup completion. Other fields do not gain timestamps.
- **Harvester:** Existing seven-call search, cursors, post columns, classification, translation, metrics, headlines, cron, and concurrency remain unchanged.
- **Cost:** Only the explicit command performs User About calls. Staging and production share the provider quota, so the command enforces global pacing and fixed budgets.
- **Recovery:** Staging changes can be rebuilt from its snapshot. Production rollback preparation is documented but not executed.

### Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Live schema differs from docs | Strict leaf inventory stops on the first unknown or wrong type before that Account write. |
| Handle now belongs to another account | Require returned ID equality. |
| Missing post booleans become false | Preserve key presence through normalization and validate exact booleans. |
| Malformed post data clobbers good values | Route all current writers through KTD12 and preserve rejected fields. |
| Provider I/O holds database locks | Fetch and parse outside transactions; lock one row only for compare-and-apply. |
| Parallel workers exceed QPS | Use one shared limiter and one bounded session for the command. |
| Retries exceed spend | Enforce attempt, credit, wall-time, and circuit limits before each outbound call. |
| Report leaks account identity | Commit aggregates only; keep handles, IDs, credentials, and raw payloads out of tracked reports. |
| Credential crosses an environment or logging boundary | Read `TWITTERAPI_IO_API_KEY` only from the staging service environment; reject CLI-provided secrets and redact request headers and connection strings. |
| Migration and staging data are out of sync | Verify deployed SHA, Django migration leaf, actual columns, types, and row counts before the pilot. |
| Vendor ledger is unavailable | Mark cost reconciliation inconclusive and stop after the bounded staging result. |

### Sequencing

Implement U5 with fake network evidence. Implement U6 and prove every Account writer call chain. Commit a clean candidate with the deferred UI diff isolated. U7 deploys that exact SHA to staging, verifies the migration, runs the 100-account staging apply, and stops with evidence.

---

## Implementation Units

### U5. Add the User About protocol and bounded command

- **Goal:** Provide one strict, globally paced User About client and a default-dry-run Account population command.
- **Requirements:** R16-R21 and R26; AE9-AE12 and AE17. Implements KTD10-KTD11, KTD13, KTD17-KTD18.
- **Dependencies:** None.
- **Files:**
  - Modify `monitor/twitterapi/caller.py`.
  - Create `monitor/twitterapi/user_about.py`.
  - Create `monitor/management/commands/backfill_account_based_in.py`.
  - Create `tests/test_twitterapi_user_about.py`.
  - Modify `tests/test_twitterapi_caller_shape.py`.
  - Create `tests/test_backfill_account_based_in.py`.
- **Approach:**
  1. Add strict response-envelope and leaf parsing against the field map.
  2. Extend the existing caller with an aggregate pace gate and pre-call budget checks.
  3. Make selection deterministic, missing-first, resumable, default-dry-run, and explicit-apply.
  4. Keep detailed runtime receipts outside the repository. Emit tracked aggregate JSON and Markdown after the pilot.
- **Execution note:** Pin parser, pacing, retry, circuit, and zero-write behavior with fake HTTP and a real ORM call chain before any live request.
- **Patterns to follow:** `monitor/twitterapi/caller.py`, `monitor/management/commands/resolve_lonely_placeholders.py`, and `scripts/harvest_cost/emit.py`.
- **Test scenarios:**
  - A complete documented response produces every mapped candidate and no unknown leaf.
  - Missing optional objects produce present/absent metadata without implicit clears.
  - Covers AE10. Unknown leaf, invalid count or datetime, returned-ID mismatch, or provider error performs no write.
  - Covers AE17. An exact but unsupported country string stores the provider value, checkpoints success, and derives no code.
  - Aggregate request timestamps remain within the selected QPS under concurrent completion.
  - One 429 honors Retry-After; repeated 429/5xx opens the circuit; 401/403 stops immediately.
  - Default invocation performs zero HTTP calls and zero Account writes.
  - Covers AE12. Accepted success-empty checkpoints once; a restart skips it unless refresh is explicit.
  - Account, attempt, projected-credit, 30-minute wall-time, and effective-QPS budgets are checked before the next request and cannot overshoot.
  - The credential is sourced only from `TWITTERAPI_IO_API_KEY`; command arguments, reports, and ordinary logs never expose it or request headers.
- **Verification:** Focused tests prove the command-to-caller boundary, strict schema, budgets, redaction, and no recurring scheduler edge.

### U6. Add typed Account persistence and validated writer ownership

- **Goal:** Add every missing typed destination and make all current Django Account writers use one last-valid-write gateway.
- **Requirements:** R6, R12, R19, R21-R25; AE10-AE16. Implements KTD10, KTD12-KTD16.
- **Dependencies:** U5.
- **Files:**
  - Modify `core/models.py`.
  - Create `core/account_validation.py` only if reusable validators do not fit cleanly in the model module.
  - Create the next migration after `core/migrations/0019_guard_per_brand_narrative_reverse.py`.
  - Modify `monitor/twitterapi/user_about.py`.
  - Modify `x_monitor/apify.py`.
  - Modify `monitor/cycle.py`.
  - Modify `monitor/list_membership.py`.
  - Modify `monitor/management/commands/load_seed.py`.
  - Modify `monitor/harvest_summary.py` only if it is the existing structured rejection owner.
  - Create `monitor/country_codes.py`.
  - Create `scripts/build_country_codes.py`.
  - Create `docs/operations/2026-08-29-223000-account-user-about-backfill.md`.
  - Create `tests/test_account_user_about_model.py`.
  - Create `tests/test_account_field_freshness.py`.
  - Create `tests/test_load_seed_account_observation.py`.
  - Modify `tests/test_list_membership_reconciliation.py`.
  - Modify `tests/test_post_schema_denormalization.py`.
  - Modify `tests/test_backfill_account_based_in.py`.
  - Create `tests/test_country_codes.py`.
- **Approach:**
  1. Add only missing nullable fields from the field map and generate one additive migration from the current leaf.
  2. Add the KTD12 gateway and model validators before changing writer call sites.
  3. Preserve provider-key presence through post normalization. Flatten explicit post affiliate labels into the shared Account label fields while retaining existing typed Post fields.
  4. Route About, post, list, and seed Account mutations through the gateway. Keep provider I/O outside its transaction.
  5. Generate the KTD19 backend-only country map and derive country only from accepted exact About values. Do not move or regenerate visual flag artifacts in this plan.
  6. Record bounded rejection counts and redacted reasons without rolling back a valid Post.
  7. Document the R25 production snapshot and restore gate without executing it.
- **Execution note:** Begin with model and production-caller regression tests. Helper-only validation tests are insufficient.
- **Patterns to follow:** `_normalize_tweet` in `x_monitor/apify.py`, `_upsert_account` in `monitor/cycle.py`, and `_upsert_account` in `monitor/list_membership.py`.
- **Test scenarios:**
  - Covers AE11. A complete About response populates shared and new typed fields with no Account JSON field.
  - Account creation and update use the same validation semantics.
  - `created_at` fills null, accepts equality, and preserves/report conflicts.
  - Covers AE13. Explicit valid post values refresh shared mutable and affiliate-label fields without changing About-only fields.
  - Covers AE14. Missing post/list values preserve current fields.
  - Covers AE15. Malformed independent values are rejected field-by-field while a valid sibling value and the Post persist.
  - A malformed coupled label preserves the whole current label group.
  - Exact supported codes and canonical English names normalize; cities, regions, fuzzy names, `WW`, `HF`, and unsupported values do not. Unsupported exact values still store and checkpoint the accepted About observation.
  - Covers AE16. Accepted equal follower counts advance freshness; omitted or rejected counts do not.
  - List handle collision remains degraded rather than corrupting identity.
  - Seed loading remains idempotent and cannot bypass validation.
  - Migration applies from current main, reverses on a disposable database, and leaves existing Account rows intact.
- **Verification:** Model tests and real post/list/seed/About call-chain tests prove the mapped schema, validation containment, writer ownership, and timestamp rules.

### U7. Deploy, migrate, and populate the 100-account staging pilot

- **Goal:** Prove the exact candidate's migration and paid write path on isolated staging, then stop with decision-grade evidence.
- **Requirements:** R15-R18 and R20; AE9-AE12. Implements KTD14 and KTD18.
- **Dependencies:** U5-U6 and all local verification gates.
- **Files:**
  - Create `docs/analysis/YYYY-MM-DD-HHMMSS-twitterapi-user-about-staging-pilot.json` at pilot runtime.
  - Create `docs/analysis/YYYY-MM-DD-HHMMSS-twitterapi-user-about-staging-pilot.md` at pilot runtime with the same timestamp.
  - Modify `docs/operations/2026-08-29-223000-account-user-about-backfill.md` with verified staging evidence and recovery notes.
- **Approach:**
  1. Isolate the existing flag/disclosure working diff and exclude it from the candidate.
  2. Push the exact candidate to the staging lane and wait for `build.sh` migration success.
  3. Verify staging service identity, candidate SHA, database identity, migration row, actual columns/types, and at least 100 callable Accounts.
  4. Run dry-run selection and confirm zero HTTP and database writes.
  5. Run one explicit apply as `python manage.py backfill_account_based_in --apply --limit 100 --max-attempts 110 --max-credits 1980 --max-wall-seconds 1800 --max-qps 5 --seed <recorded-seed> --json-report <timestamped-path> --markdown-report <timestamped-path>`; the command must lower QPS further when the verified provider allowance requires it.
  6. Compare before/after staging rows, reconcile provider usage, emit aggregate reports, and stop.
- **Execution note:** This is the only live-call unit. Do not run it locally or against production. Do not refresh staging unless its verified Account sample is insufficient and the guarded refresh preflight succeeds.
- **Patterns to follow:** `build.sh`, `scripts/render_migrate.py`, `docs/deploy/render.md`, and `docs/operations/staging-data-refresh.md`.
- **Test scenarios:**
  - Candidate SHA and staging deployment SHA match before the command runs.
  - Migration row and all mapped columns/types exist on staging; production migration state is unchanged.
  - Dry run chooses the same seeded 100 Accounts as apply and performs no calls or writes.
  - Covers AE9. Apply stays within 100 Accounts, 110 attempts, a 1,980-credit projected budget, 30 minutes, and the lower of 5 QPS or the authorized provider QPS.
  - Covers AE10. Drift or identity mismatch stops without changing that Account.
  - Covers AE12. Successful empty and populated responses both checkpoint; transient failures remain eligible.
  - Before/after SQL reconciles selected, attempted, accepted, rejected, changed, unchanged, success-empty, and remaining counts.
  - Reports contain no handle, Account ID, credential, connection string, or raw payload.
- **Verification:** Staging reports the exact SHA and migration, the 100-account receipt reconciles to staging SQL and provider evidence, and production remains unchanged.

---

## Verification Contract

| Gate | Command | Required evidence |
| --- | --- | --- |
| Protocol and command | `pytest tests/test_twitterapi_user_about.py tests/test_twitterapi_caller_shape.py tests/test_backfill_account_based_in.py -q` | Strict schema, pacing, retries, circuit, budgets, redaction, dry-run, apply, and restart pass. |
| Model and writer ownership | `pytest tests/test_account_user_about_model.py tests/test_account_field_freshness.py tests/test_load_seed_account_observation.py tests/test_list_membership_reconciliation.py tests/test_post_schema_denormalization.py tests/test_country_codes.py -q` | Typed fields, exact country normalization, invalid-value containment, and About/post/list/seed call chains pass. |
| Migration | `python manage.py makemigrations --check --dry-run` and `python manage.py migrate --plan` | No model drift; the additive migration follows `0019` and plans cleanly. |
| Harvester regression | `pytest tests/test_cycle_regression_net.py tests/test_cycle_search_caps.py tests/test_cycle_cursor_wiring.py tests/test_cycle_error_counters.py tests/test_list_membership_reconciliation.py tests/test_post_schema_denormalization.py -q` | Seven-call shape, cursors, post persistence, Account isolation, and rejection behavior remain correct. |
| Django | `python manage.py check --deploy` | No new deployment errors; existing environment warnings are named. |
| Ollija | `pytest tests/ollija -q` and `./bin/ollija annotate-plan docs/plans/2026-08-29-093958-feat-feed-country-flags-disclosure-plan.md --check` | Guidance remains unchanged and target remains owner-selected staging. |
| Staging migration | Render build log plus staging SQL | Candidate SHA, migration row, all column names/types, and existing row preservation are verified before calls. |
| Staging pilot | Explicit U7 command and before/after SQL | Exactly 100 selected staging Accounts, at most 110 attempts and 1,980 credits, complete aggregate evidence, and no production write. |

---

## Definition of Done

- U5 is done when fake caller and command tests prove strict response parsing, aggregate pacing, retry/circuit behavior, all four concrete budgets, environment-only credential loading, default dry-run, explicit apply, idempotent success-empty checkpointing, and aggregate-only reports.
- U6 is done when the migration contains every missing typed destination and no raw response field; every current Django Account writer uses the model gateway; invalid observations cannot clobber good data; post ingestion remains successful; and `followers_fetched_at` follows R24.
- U7 is done when the exact candidate deploys to staging, the migration and schema are verified there before calls, the 100-account apply completes or stops safely within all caps, and reports reconcile to staging rows and provider evidence.
- Every behavior change has at least one production-caller-to-ORM regression test. Helper-only coverage is insufficient.
- The candidate diff excludes the deferred flag/disclosure implementation and unrelated working-tree changes.
- Required checks have zero unexpected failures or skips. Pre-existing warnings and unrelated suite failures are named precisely.
- Production branch, service SHA, database schema, and Account data remain unchanged.
- No full population, recurring schedule, UI successor work, raw response payload, credential, handle, or Account ID is committed.
- Abandoned experimental code and temporary pilot data are removed. The staging-only worktree remains registered.

---

## Appendix

### Research Sources

- `core/models.py` — current Account fields and the unused `followers_fetched_at`.
- `x_monitor/apify.py` — post author normalization, including `createdAt` and affiliate labels.
- `monitor/cycle.py` — direct post-driven Account `update_or_create`.
- `monitor/list_membership.py` — list-driven handle and display-name updates.
- `monitor/twitterapi/caller.py` — reusable session, connector, retry, timeout, and circuit patterns.
- `docs/external_vendors/twitterapi_docs/twitterapi_index.md` — local pricing and dashboard-ledger research.
- `docs/deploy/render.md` and `docs/operations/staging-data-refresh.md` — isolated staging and migration behavior.
- [TwitterAPI User About](https://docs.twitterapi.io/api-reference/endpoint/get_user_about) — official query parameter and response schema checked 2026-08-29.
- [TwitterAPI pricing](https://twitterapi.io/pricing) — official credit and USD rates checked 2026-08-29.
- [TwitterAPI QPS limits](https://twitterapi.io/qps-limits) — official balance-derived ceiling checked 2026-08-29.

### Sizing Baseline

| Measure | Current planning value | Use |
| --- | --- | --- |
| Callable production-sized population | about 59,225 | Re-measure before later production authorization |
| 100 successful profiles | 1,800 credits / USD 0.018 | Pilot expectation |
| 110-attempt maximum | 1,980 credits / USD 0.0198 | Hard pilot cap under profile pricing |
| 59,225 successful profiles | 1,066,050 credits / USD 10.6605 | Nominal full run before retries |
| Provider QPS | 3, 6, 10, or 20 by balance | Command uses the verified lower ceiling |
