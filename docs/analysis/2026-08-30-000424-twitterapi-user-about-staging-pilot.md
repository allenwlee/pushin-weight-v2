# TwitterAPI User About staging pilot

The bounded staging pilot stopped safely on the first response because the live
provider payload did not match the strict documented schema. It made one paid
attempt, retried zero times, and changed zero Account rows. No retry, larger
run, production migration, or production write is authorized.

## Deployment and preflight

- Candidate and remote staging SHA: `b17affada9d0f2237e050b589d7b83afe96ebc52`
- Staging web deploy: `dep-da9f69s9v7es73dj5940` (`live`)
- Database and role: `pushinweight_staging` / `pushinweight_staging`
- Migration: `core.0020_account_account_based_in_and_more` applied
- Schema: 22 of 22 typed columns present and nullable; both `country_code`
  indexes present
- Accounts: 57,084 total; 57,082 with callable handles
- Dry run: 100 selected with seed `account-based-in-pilot-v1`; zero HTTP calls
  and zero writes
- Managed credential: present only in the staging harvester environment
- Provider balance before: 8,808,062 recharge credits; published balance tier
  allowed 20 QPS; the operator cap reduced the effective limit to 5 QPS

The web service did not hold `TWITTERAPI_IO_API_KEY`, so the paid command ran as
an exact-SHA Render one-off job derived from the dormant staging harvester. That
kept the credential in Render and used the same isolated staging database. A
preliminary one-off dry-run attempt failed during staging OAuth configuration
validation before Django loaded; it made no provider call and no database write.
Future retry planning must align the durable executor guard and credential
ownership before another paid call.

## Pilot outcome

| Measure | Result |
| --- | ---: |
| Selected Accounts | 100 |
| Attempted Accounts | 1 |
| Accepted | 0 |
| Changed | 0 |
| Not attempted | 99 |
| Attempts / retries | 1 / 0 |
| Projected credits | 18 |
| Projected USD | $0.00018 |
| Network wall time | 1.011 seconds |
| p50 / p95 latency | 1010.433 ms / 1010.433 ms |
| Stop reason | `schema_drift` |

The command logged no handle, X account ID, credential, request header, raw
payload, or connection string. Strict parsing intentionally withheld the
unknown live payload from normal logs. Diagnosing the exact schema difference
therefore requires a separately authorized, redacted capture design; this plan
does not make a second User About call.

## Database reconciliation

Before and after the pilot, staging had zero rows with
`account_based_in_fetched_at`, `account_based_in`, or `country_code`. The
schema-drift response was not checkpointed, and no Account value changed.

The production database remained unchanged: migration 0020 is absent, none of
the 22 columns exists there, and no production write was performed.

## Credit reconciliation

The post-run recharge balance was 8,805,032, a shared-window difference of
3,030 credits. Staging and the live harvester use the same provider account,
and this window crossed normal production activity. The separate Recent API
Calls dashboard session was unavailable, so the pilot's actual burn cannot be
isolated from that balance delta. Published-rate projection is 18 credits;
actual cost remains inconclusive.

## Decision

The guardrails worked: the first unexpected response stopped the run with no
write amplification. The schema assumption is not validated, cost
reconciliation is inconclusive, and expansion is not authorized. Stop here for
owner review.

