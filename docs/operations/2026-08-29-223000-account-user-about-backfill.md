---
title: Account User About staging pilot and production gate
date: 2026-08-29
status: staging-pilot-only
---

# Account User About staging pilot

This runbook covers the migration-first, 100-account TwitterAPI User About
pilot. It does not authorize a production migration, a full Account
population, a recurring schedule, or feed rendering.

## Safety boundary

- Run paid apply only on `pushinweight-staging-web` with
  `OLLIJA_STAGING_MODE=True`.
- Read `TWITTERAPI_IO_API_KEY` from the Render-managed environment. Never pass
  the key as an argument or print request headers.
- The apply command refuses more than 100 Accounts, 110 attempts, 1,980
  projected credits, 30 minutes, or 5 operator QPS.
- Supply the current balance-derived provider QPS separately. The effective
  QPS is the lower provider/operator limit.
- Reports are aggregate-only. Do not persist handles, X IDs, database URLs,
  credentials, request headers, or raw provider payloads.

## Staging preflight

1. Verify the deployment reports the candidate SHA and succeeded after
   `build.sh` ran migrations.
2. Verify the active database identifies as the staging database and the
   service has at least 100 eligible Accounts. Do not print connection
   strings.
3. Verify migration `core.0020_account_account_based_in_and_more` is applied.
4. Verify the 22 additive nullable columns and the `country_code` index exist.
5. Run a dry selection and confirm it reports zero calls and zero writes:

```bash
python manage.py backfill_account_based_in --limit 100 \
  --seed account-based-in-pilot-v1
```

If staging lacks 100 eligible Accounts, use the guarded procedure in
`docs/operations/staging-data-refresh.md`. Do not read production handles from
inside the backfill command.

## Staging apply

Use one timestamp for both aggregate reports:

```bash
python manage.py backfill_account_based_in \
  --apply \
  --limit 100 \
  --max-attempts 110 \
  --max-credits 1980 \
  --max-wall-seconds 1800 \
  --max-qps 5 \
  --provider-qps <verified-provider-qps> \
  --seed account-based-in-pilot-v1 \
  --json-report docs/analysis/YYYY-MM-DD-HHMMSS-twitterapi-user-about-staging-pilot.json \
  --markdown-report docs/analysis/YYYY-MM-DD-HHMMSS-twitterapi-user-about-staging-pilot.md
```

The command checkpoints successful responses, including success responses
whose optional About fields are empty. Transport, provider, identity, and
schema failures remain eligible for a later retry. Unknown leaves, documented
type drift, returned-ID mismatch, invalid authentication, an open circuit, or
any hard budget stop the run.

## Evidence and reconciliation

Reconcile the aggregate command receipt to staging SQL for selected,
attempted, accepted, changed, unchanged, success-empty, and remaining counts.
Compare the exact UTC call window against TwitterAPI's Recent API Calls ledger
and record actual credits. The dashboard ledger requires its separate session
token; the X API key is not valid for that endpoint.

If the provider ledger is unavailable or does not reconcile, mark actual cost
inconclusive. A bounded staging result remains useful migration and schema
evidence, but cannot authorize expansion.

## Production gate — not executed by this plan

Before any later production apply:

1. Obtain fresh owner authorization for the production migration and call
   volume.
2. Create an encrypted pre-write Account snapshot with an exact row count and
   digest.
3. Restore that snapshot into a disposable PostgreSQL database and verify the
   row count and digest there.
4. Re-measure eligible Accounts, current pricing, provider QPS, and the
   projected attempt ceiling.
5. Pin the exact reviewed candidate SHA and a rollback decision point.

Application rollback can stop future User About calls while leaving nullable
columns in place. Data recovery uses the verified Account snapshot. Do not
drop columns or overwrite production Accounts as an improvised rollback.
