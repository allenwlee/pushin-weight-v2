# Stage 0 enrichment baseline

The owner-selected 90-minute production observation is complete. This passive
record supports continuing Stage 1 toward staging: it found no evidence that
Stage 0 telemetry introduced a material regression. Four translation rows
remained retryable at the final cycle, so it does not establish universal
enrichment completeness. It contains no spend or semantic-accuracy estimate.

## Production observation: 13:51–15:21 UTC, September 8

Stage 0 was promoted in [PR 40](https://github.com/allenwlee/pushin-weight-v2/pull/40)
at `af272b6fe0b43be3276429792508749b9ddc8194`. Production web, harvest cron and
headline worker reported that exact commit; web health and an isolated
provider-free direct-HTTP probe passed before observation. Six terminal natural
harvest summaries in this window also reported that commit. The window was not
mixed with another candidate.

Bounded log collection filtered provider `event_id` records in six 15-minute
partitions, excluded the synthetic `provider-free` run, and deduplicated event
IDs. It found **42 unique application transport events, all successful**, with
zero duplicate IDs or saturated log partitions. These are transport successes,
not proof that every response satisfied downstream enrichment requirements.

| Role / stage | Calls | Reported input tokens | Reported output tokens | Cache-read tokens | Latency range, seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Classification | 13 | 47,538 | 31,509 | 41,600 | 5.152–14.962 |
| Translation and synthesis | 17 | 49,335 | 118,423 | 30,080 | 2.862–116.359 |
| Headline rank | 1 | 85,401 | 1,879 | 0 | 11.152 |
| Headline editor | 5 | 152,823 | 18,211 | 3,584 | 17.436–27.011 |
| Headline critic | 5 | 173,320 | 18,463 | 2,560 | 15.462–21.385 |
| Relevancy | 1 | 92 | 2 | 256 | 0.648 |

Input, output and cache fields were available for all events. Reported
cache-creation usage was zero. Provider total and reasoning usage were unknown
for all 42 events; they are not derived or treated as zero. Cache fields can
overlap other counters and must not be added to input/output usage. Ranges are
observed minima/maxima, with the sample size shown; no percentiles are inferred.

Attempt kinds were 39 initial, two repair and one single-post relevancy call.
The reported configured model was `deepseek-v4-flash` on 41 events and
`claude-haiku-4-5` on one relevancy event; all provider-host classes were
`deepseek`. These fields describe application configuration and routing.

Headline stages accounted for 411,544 of 508,509 reported input tokens (about
81%). Translation/synthesis accounted for 118,423 of 188,487 output tokens
(about 63%). These proportions identify useful later efficiency targets; they
are not invoice cost proportions. The headline ledger independently contained
11 unique request identities with matching 411,544 input / 38,553 output sums
and recorded latency on all rows. Ledger and log counts are corroboration,
never additive. The ledger uses request creation time while telemetry uses
completion time, so agreement in this window does not establish equivalent
boundary semantics in every window.

| Natural cycle, UTC | Inserted posts | Claimed | Succeeded | Pending | Failed |
| --- | ---: | ---: | ---: | ---: | ---: |
| 14:00 | 31 | 48 | 48 | 0 | 0 |
| 14:15 | 47 | 29 | 29 | 0 | 0 |
| 14:30 | 36 | 54 | 54 | 0 | 0 |
| 14:45 | 29 | 29 | 29 | 0 | 0 |
| 15:00 | 38 | 38 | 37 | 1 | 0 |
| 15:15 | 80 | 41 | 37 | 4 | 0 |

Cycle claim counts include carryover and need not equal inserted counts. Do not
sum these as a distinct-post completion cohort. All six cycles reported zero
translator/classifier batch failures, unavailable clients, invalid classifier
flags and quarantined enrichment rows. They retained pre-existing
`list_membership_reconciliation` degradation; 14:00 and 15:15 also reported
`call_a_author_roles` degradation. Their overall status was `degraded`, not
fully healthy.

A bounded read-only aggregate at 15:24:15 UTC inspected the 41 states last
attempted in 15:15–15:21. All 41 classifications had succeeded. Translation
had succeeded on 37 rows (including one after two attempts), while four rows
had first-attempt `translation_incomplete` and remained pending. This is a
post-window database snapshot, not a reconstructed snapshot at 15:21. Pending
enrichment was also observed before Stage 0, as recorded below. There is no
evidence here attributing that existing failure mode to passive telemetry.

No manual harvest, model call, scheduler pause, backfill or production write was
used to fill this baseline. The separate immutable latest-20, 30-minute
production health observation remains a Stage 1 pre-staging gate.

## Evidence receipts

The canonical Stage 1 worktree retains metadata-only receipts under
`.context/stage0-baseline/`, including collection scripts, production deploy
verification, the earlier health snapshot, and a SHA-256 manifest. Key hashes:

- Final provider receipt: `b6e791e949ec3ad33ca6200a79bfcd14c85c03560fb2d2ae52dcca4e2e97e384`.
- Final cycle summaries: `07b8ca059e69fee788ff398bf9cc6c3084c2dc88acc2bc7e5649b50165a01436`.
- Pending-state aggregate: `bdf9f2f473609e7dff16bb216dc749e955c681427bb97d27b91e30f93aad3731`.

The initial cycle-summary extraction used incorrect nested keys for inserted
and error counters; those fields were corrected from the canonical summary
schema. The pending-state aggregate initially encountered unparseable psql
table rendering and was read once more with unaligned, tuples-only output.
Neither correction changed the observation window or production data.

## Pre-implementation reference

The captured command was:

```text
render logs -r crn-d9gv94o4n6ts739tqaug --tail 120 --output text
```

Capture time: `2026-09-08T20:06:37+0900`.

- Deploy SHA reported by the logs: `b184276cc6ec4e7d1a9eba83357e824848dc8f94`.
- Run `20260908T103029_0000-508c7fc6` at `10:30:29Z`: 28 claimed, 28 succeeded, 82.853 seconds post-fetch.
- Run `20260908T100053_0000-c1ed2294` at `10:00:53Z`: 42 claimed, 40 succeeded, 2 pending, 108.909 seconds post-fetch.

A separate read-only `git ls-remote` receipt resolved both remote `main` and
remote `staging` to `b184276cc6ec4e7d1a9eba83357e824848dc8f94`. This is separate
from the production log receipt. At that pre-implementation checkpoint, the
headline ledger already persisted basic input/output/latency fields. Aggregate
usage by role and extended headline usage remained unmeasured. Cost,
percentiles, worker liveness and usage totals were unreported rather than zero
or estimated.

Those measurements predated Stage 0 telemetry and are retained as historical
context. Stage 0 preserved taxonomy, runtime behavior, schema, scheduling,
prompts, retries, model configuration and outputs. Its staging and production
verification subsequently completed as recorded above.
