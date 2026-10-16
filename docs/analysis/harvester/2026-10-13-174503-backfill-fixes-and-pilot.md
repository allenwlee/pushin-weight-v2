# Backfill fixes and the August 9 staging test

The backfiller fixes pass offline verification. The required live test has
**not succeeded**: both attempts recovered zero new posts. The second found
one matching post already in staging. A different approved 15-minute sample
is needed to exercise recovery, translation and classification.

The [same task plan](../../plans/2026-10-12-105615-docs-august-harvest-audit-20261012-plan.md)
contains the approved G3 persistence boundary and next-sample manifests.

## Implemented behavior

Historical runs require fixed UTC bounds and finite limits. The command divides
long intervals into call/time-slice units, resumes committed provider cursors,
and replaces checkpoints atomically on fuchitalee. A changed query, configuration,
scope or limit cannot inherit completion. Failed persistence keeps the prior
cursor. Anomalous pages stop automatic retries; their cause must be inspected
before an explicit retry.

One invocation budget counts physical HTTP requests and model requests across
all runners and retries. The writer lease covers active units and is released
before pauses. Admission preserves upcoming scheduled slots and their startup
grace. Inline enrichment selects a frozen new-post cohort; pending work remains
durable and visible. Enrichment-only resumption purchases no search again, and
a zero model allowance defers before claiming work.

Scheduled collection retains its existing queries, credential purpose and
cursor/backlog behavior. Manual recovery uses ON_DEMAND only. Explicit historical
queries are available for one brand and B/C call; command bounds own their dates.
Call A requires a frozen historical account manifest before execution.

G3 approved host JSON for this pilot and owns the future shared persistence API.
No shared model, migration, CollectionJob or standalone backfill table changed.
No scheduler, production deployment or month campaign was started.

## Verification

Final source: `2cf43ef3`; base: `db5510cc`.

- 252 tests pass; 107 PostgreSQL-required tests executed, zero skips/errors.
- Tests cover actual command/runner/API transport/ORM wiring, repeated cursors,
  partial fetch/storage failures, concurrent budgets, scoped claims and writer
  release to a competing connection. Scheduled regression tests also pass.
- Focused Ruff lint and Django system checks pass. Existing project-wide lint
  debt is recorded separately. No configured project typecheck exists.
- Code review included an independent Grok-family read, requesting `grok-4.7`
  at `xhigh`; exact serving model/effort are unverified. Supported failure and
  persistence findings were addressed. The first Claude route returned an
  insufficient-balance error and produced no review.
- No browser routes changed.

## Live test

Fixed sample: **August 9, 2026, 00:00–00:15 UTC /09:00–09:15 JST**, Qwen/B1.
Runtime: fuchitalee against verified `pushinweight_staging`, role
`pushinweight_staging`, PostgreSQL18.4, migration0080. Checkpoints remain on
fuchitalee. The staging harvest cron stays suspended; schedules and credentials
were not changed.

Both attempts used one unit, at most five primary pages/100 returned primary
results, ten HTTP requests, sixty model calls, a300-second deadline, and a
frozen cohort of at most five newly inserted posts.

| Observation | Original query | Verified historical names |
| --- | --- | --- |
| Source | `fd8d0b79` | `0c967468` |
| Primary requests | 1 | 2 |
| Primary returned posts | 0 | 1 |
| Newly inserted posts | 0 | 0 |
| Existing posts updated | 0 | 1 |
| Model calls | 0 | 0 |
| Elapsed | 3.150s | 9.813s |
| Peak process memory | 103.22MiB | 103.67MiB |
| Cursor/backlog digest change | None | None |
| Required recovery test | Failed | Failed |

The historical-name query adds `"Qwen3.8"` to the existing Qwen/Qwen3/通义千问
population; it keeps the same dates, brand, call and limits. Its two pages drain
the provider response and deduplicate one previously stored post. No new cohort
exists, so translation/classification transport, tokens, cost and parallel
resource use remain unmeasured. These timings and memory values describe an
empty/duplicate workload and cannot support a24-hour or month forecast.

Seven bounded provider-only diagnostics explain the result: exact Qwen3.8
searches and ID lookup return the known post in the fixed interval, while the
original query returns none. A `Top` query with epoch bounds returns October
posts; those results were not stored and that approach was not adopted. Ten
TwitterAPI requests total were made across the two pilots and diagnostics, all
with the on-demand purpose. Query bounds follow the provider's current
[advanced-search documentation](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search).
Search results do not establish a complete historical X census.

The original failed receipts/checkpoints remain intact. Current source adds
only a zero-model-budget deferral after the second pilot; its behavior is
covered by PostgreSQL tests. No successful candidate enrichment claim is made.

## Remaining acceptance work

Two replacement manifests have been prepared with read-only staging dry runs:
August1 08:00–08:15UTC inside the first audited gap, or August9 00:15–00:30UTC
adjacent to the original sample. Both retain Qwen/B1 and the finite caps, and
explicitly include historical Qwen3.6/Qwen3.8 names. They require owner selection
because they change the fixed sample. Neither has run.

Success still requires a real newly inserted scoped post, a drained provider
receipt, complete persisted translation and canonical classification for the
frozen recovered cohort, and unchanged live cursor/backlog state. Local tests,
this report and a draft pull request do not fulfill that condition.
