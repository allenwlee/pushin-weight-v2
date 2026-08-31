---
title: Account User About staging pilot and production population
date: 2026-08-29
status: production-authorized
---

# Account User About backfill

This runbook covers the completed 100-Account staging pilot and the
owner-authorized, one-time, missing-only production population. It does not
authorize recurring User About collection, refreshes of completed Accounts, or
feed rendering.

## Safety boundary

- Paid calls use `TWITTERAPI_IO_ON_DEMAND_API_KEY` from the Render-managed
  environment. Never pass or print either TwitterAPI key. The command never
  falls back to the scheduled key or retired unsuffixed key.
- Production apply requires `--target production`,
  `X_MONITOR_DEPLOYMENT_ENVIRONMENT=production`, PostgreSQL database
  `pushinweight_shadow`, migrations `core.0020` through `core.0025`, and a
  fresh recovery receipt. These gates run before credential access or HTTP.
- Production `--refresh` is forbidden. Successful responses, including
  documented unavailable and success-empty responses, checkpoint
  `account_based_in_fetched_at`; restarts select only missing rows.
- One nonblocking PostgreSQL advisory lock permits one snapshot or production
  runner at a time. Accepted observations commit per Account and completed
  chunks survive a job restart.
- The production command caps a run at 100,000 Accounts, 110,000 attempts,
  1,980,000 projected credits, 24 hours, 20 operator QPS, 20 concurrent
  requests, and 1,000 Accounts per chunk. Use the smaller operational limits
  below.
- Reports and progress logs are aggregate-only. They must not contain handles,
  X IDs, database URLs, credentials, request headers, recovery-receipt tokens,
  or raw provider values.
- Unknown schema and returned-ID mismatch quarantine only the affected Account:
  they write and checkpoint nothing, emit aggregate-only reason counts, and do
  not stop admission for other Accounts. Ten consecutive Account quarantines
  indicate systemic drift and stop new admissions. Authentication failure, an
  open circuit, or a hard budget also remains a global stop. Already-reserved
  concurrent requests may finish and checkpoint safely.

TwitterAPI's pricing page showed 18 credits per returned profile and
100,000 credits per USD on 2026-08-31. At that rate, 60,000 one-shot calls
project to 1,080,000 credits, or $10.80, before retries. `/twitter/user_about`
has no published endpoint-specific QPS guarantee; use 5 QPS for this run even
if the provider dashboard shows a higher account ceiling.

## Completed staging evidence

The initial strict-schema run is recorded in
`docs/analysis/2026-08-30-000424-twitterapi-user-about-staging-pilot.md` and its
matching JSON. The corrected replacement pilot is recorded in
`docs/analysis/2026-08-30-065017-twitterapi-user-about-replacement-staging-pilot.md`
and matching JSON.

The same deterministic 100-Account sample finished with 99 checkpoints and
one provider error. Across the original drift call, diagnostic call, and
replacement run, cumulative usage was 104 calls and 1,872 projected credits,
within the 110-call / 1,980-credit ceiling. Exact provider burn remained
inconclusive because the Recent API Calls ledger uses a separate dashboard
session.

The staging command remains capped at 100 Accounts, 110 attempts, 1,980
credits, 30 minutes, 5 QPS, one concurrent request, and chunks of at most 100.
Its apply form is:

```bash
python manage.py backfill_account_based_in \
  --target staging --apply --limit 100 \
  --max-attempts 110 --max-credits 1980 \
  --max-wall-seconds 1800 --max-qps 5 \
  --provider-qps <verified-provider-qps> \
  --concurrency 1 --chunk-size 100 \
  --seed account-based-in-pilot-v1 \
  --json-report /tmp/twitterapi-user-about-staging.json \
  --markdown-report /tmp/twitterapi-user-about-staging.md
```

## Production release preflight

Use the exact candidate SHA throughout staging, `main`, production web, and
production harvest. Run one-off jobs from `pushinweight-harvest`
(`crn-d9gv94o4n6ts739tqaug`) so the database and on-demand credential stay in
their managed environment.

Before paid calls:

1. Verify the deployed Git SHA and successful `build.sh` migration.
2. Verify the service identifies as production and the database identifies as
   `pushinweight_shadow` without printing environment values or the connection
   string.
3. Verify both purpose-specific key names are nonempty without printing them.
4. Verify migrations `0020_account_account_based_in_and_more`,
   `0021_account_user_about_live_schema`,
   `0022_account_verification_reason_timestamp`, and
   `0023_account_user_about_unavailable`, and
   `0024_account_identity_profile_label_long_description`, and
   `0025_account_verification_override_year` are applied.
5. Verify the scheduled harvester's latest completed cycle is healthy. Do not
   pause it for the multi-hour provider run.
6. Run the production selection dry-run and record the aggregate eligible
   count:

```bash
python manage.py backfill_account_based_in \
  --target production --limit 100000 \
  --seed account-based-in-production-v1
```

Create the one-off job with Render CLI v2.22 or later:

```bash
render jobs create crn-d9gv94o4n6ts739tqaug \
  --start-command "<command from this runbook>" --confirm
```

## Recovery snapshot and receipt

First prove that the snapshot command is still a zero-write dry run:

```bash
python manage.py prepare_account_user_about_recovery
```

Then create the production snapshot:

```bash
python manage.py prepare_account_user_about_recovery \
  --apply --confirm-database pushinweight_shadow
```

The guarded command acquires the same advisory lock as the backfill, starts a
repeatable-read transaction, copies the complete `accounts` relation into the
private `account_user_about_backup` schema, and computes a deterministic row
count and SHA-256 digest. It copies that snapshot into a disposable temporary
relation and requires the restored count and digest to match before commit.

Capture the emitted `recovery_receipt` token in the operator's secure session;
do not paste it into tracked files or normal chat. The receipt is valid for 24
hours and binds the database, creation cutoff, snapshot relation, count,
digest, storage policy, and restore proof. The production runner records only
its digest and relation in aggregate output.

## Production 100-Account smoke

Use the fresh receipt with the explicit diversity-stratified smoke strategy:

```bash
python manage.py backfill_account_based_in \
  --target production --apply --limit 100 \
  --max-attempts 110 --max-credits 1980 \
  --max-wall-seconds 1800 --max-qps 5 --provider-qps 5 \
  --concurrency 5 --chunk-size 100 \
  --selection-strategy diversity_stratified \
  --seed account-based-in-production-smoke-v1 \
  --recovery-receipt '<secure-receipt>' \
  --json-report /tmp/twitterapi-user-about-production-smoke.json \
  --markdown-report /tmp/twitterapi-user-about-production-smoke.md
```

The smoke balances actual or snowflake-derived X-account age, observed
follower-size buckets, and public profile-location proxies for the US, EU,
Japan, other, and unknown. Profile location is used only to diversify the
test; it never populates or validates `country_code`.

Stop before the full run if the smoke has any authentication, rate-limit,
circuit, or hard-budget stop; an unexplained schema or identity quarantine;
unexpected rejected-field pattern; receipt mismatch; or harvester regression.
Reconcile the 100-row aggregate receipt with PostgreSQL counts and, when
available, the provider's exact UTC-window Recent API Calls ledger.

## Full missing-only production run

Run the dry selection again after the smoke. Let `N` be its reported eligible
count. Set `A = ceil(N * 1.10)` and `C = A * 18`; record all three numbers in
the release evidence. The command refuses a limit or budget outside its hard
caps.

```bash
python manage.py backfill_account_based_in \
  --target production --apply --limit <N> \
  --max-attempts <A> --max-credits <C> \
  --max-wall-seconds 21600 --max-qps 5 --provider-qps 5 \
  --concurrency 5 --chunk-size 500 \
  --require-complete \
  --seed account-based-in-production-v1 \
  --recovery-receipt '<same-secure-receipt>' \
  --json-report /tmp/twitterapi-user-about-production-full.json \
  --markdown-report /tmp/twitterapi-user-about-production-full.md
```

At 5 request starts per second, 60,000 attempts have a lower-bound runtime of
3 hours 20 minutes. The six-hour wall budget allows normal response latency,
bounded retries, and checkpoint overhead without authorizing more calls or
credits.

If a job exits unexpectedly, do not use `--refresh`. Re-run the dry selection,
recalculate `N`, `A`, and `C`, and resume with the same receipt while it is
fresh. Completed rows are absent from the next selection. If the receipt has
expired, create and restore-prove a new snapshot before resuming.

## Reconciliation and completion

Record aggregate counts before the smoke, after the smoke, after the full run,
and after any residual retry:

```sql
SELECT
  count(*) FILTER (WHERE handle IS NOT NULL AND handle <> '') AS callable,
  count(*) FILTER (
    WHERE handle IS NOT NULL AND handle <> ''
      AND account_based_in_fetched_at IS NULL
  ) AS remaining,
  count(*) FILTER (WHERE account_based_in_fetched_at IS NOT NULL) AS checkpointed,
  count(*) FILTER (WHERE account_based_in IS NOT NULL AND account_based_in <> '')
    AS based_in_nonempty,
  count(*) FILTER (WHERE country_code IS NOT NULL) AS country_mapped
FROM accounts;
```

The run is complete when every Account present at the recovery cutoff with a
nonblank handle is either checkpointed or documented as a quarantined or
non-callable provider outcome; no retryable Account remains; all admitted
attempts and projected credits are within the recorded budgets; reports
contain no sensitive values; and a fresh scheduled harvest cycle succeeds
under the scheduled key.

Generic provider errors remain uncheckpointed by design. Retry only that
missing residue under a fresh bounded budget. Do not convert errors into false
success checkpoints just to reach zero.

## Stop and recovery

The normal rollback is to stop launching jobs. Additive nullable columns can
remain in place and missing-only work can resume safely.

If accepted values are proven corrupt, stop the backfill, pause the harvest
cron using `docs/operations/pause-and-resume-harvest-cron.md`, and preserve the
failed job evidence. Recovery must use the exact receipt-named snapshot in one
reviewed transaction, joining on `author_id` and restoring only the fields
authorized to the User About writer plus the shared profile fields that the
failed run actually changed. Compare the post-restore count and digest to the
receipt, then resume and verify the harvester. Do not swap the CTAS table into
place, drop migrations, truncate `accounts`, or improvise a broad overwrite.

Retain the recovery relation until final reconciliation and at least one
healthy scheduled harvest. Drop only the exact receipt-named table in a later,
explicit cleanup; never drop the backup schema recursively.
