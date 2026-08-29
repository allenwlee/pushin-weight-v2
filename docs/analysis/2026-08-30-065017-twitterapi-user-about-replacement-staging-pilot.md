# TwitterAPI User About replacement staging pilot

The guarded 100-Account staging pilot completed. It checkpointed 99 Accounts;
one provider-error Account remains eligible for a later retry. The run stayed
inside the owner-approved cumulative cap, and production remained unmigrated
and unwritten.

## Outcome

| Measure | Result |
| --- | ---: |
| Unique sampled Accounts | 100 |
| Checkpointed Accounts | 99 |
| Provider errors | 1 |
| Nonempty `account_based_in` | 97 (97%) |
| Normalized `country_code` | 84 (84%) |
| Country mapping among nonempty `account_based_in` | 86.6% |
| Unavailable profiles | 1 |
| Verification-reason timestamps | 62 |
| Cumulative User About calls | 104 / 110 |
| Cumulative projected credits | 1,872 / 1,980 |
| Cumulative projected USD | $0.01872 |
| Retries | 0 |

The cumulative count includes the original one-call schema stop, one
schema-only diagnostic call, and the replacement pilot. The replacement pilot
itself made 102 calls for 100 unique Accounts because two Accounts were retried
after strict schema drift was corrected. Those corrections added the live
verification-reason timestamp and unavailable-profile variant to typed schema;
the final 89-Account segment completed with no schema drift.

## Schema and database reconciliation

- Pilot-executed code and staging SHA:
  `c4197fbd22def1a5934bf9a824f02093128a29d3`
- Database and role: `pushinweight_staging` / `pushinweight_staging`
- Migrations 0020 through 0023: applied
- User About columns: 29 typed nullable additions; no raw JSON column
- Staging Accounts: 57,084 total; 57,082 callable
- Before: zero User About checkpoints
- After: 99 checkpoints, 97 nonempty based-in values, 84 country codes, one
  unavailable profile, and 62 verification-reason timestamps

The unavailable success variant contains no profile ID. It can update only
`unavailable`, `unavailable_reason`, and the fetch checkpoint, and only while
the selected Account still owns the requested handle. Normal profile responses
retain the strict returned-ID match. The corrected live endpoint reference is
[`get_user_about.md`](../external_vendors/twitterapi_docs/endpoint/get_user_about.md).

## Time and scale projection

The replacement segments spent 82.998 seconds in provider calls and averaged
1.229 calls/second. Including the two fail-closed schema corrections and exact-
SHA staging deploys, the replacement pilot elapsed 20 minutes 45 seconds.

At the configured 5-QPS cap, 57,082 calls project to 3.17 hours. The current
sequential implementation's observed rate projects to about 12.9 hours. The
published-rate projection is 1,027,476 credits, or $10.27476, before retries.
This is evidence for a later production decision, not authorization to run it.

## Credit reconciliation

The application projection is 1,872 credits across all 104 authorized calls.
Exact provider burn remains inconclusive: TwitterAPI's Recent API Calls ledger
requires a separate dashboard session token, while the managed API key cannot
query it and the visible provider balance is shared with production activity.
No larger run should use the shared balance delta as proof of exact cost.

## Production boundary and decision

A read-only production check found `pushinweight_shadow` with none of migrations
0020–0023 and none of the sampled User About columns. This workflow performed
no production write. The staging pilot and backfiller are complete; production
migration and the full Account population remain owner-gated.
