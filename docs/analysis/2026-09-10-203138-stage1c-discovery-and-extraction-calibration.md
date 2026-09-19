# Stage 1C provider-free discovery and extraction calibration

Status: implementation/staging evidence only. No TwitterAPI or model provider
was called for this report, and both discovery lanes and targeted extraction
remain disabled in `config.yaml`.

## Job research calibration

The checked-in Grok artifact contains 55 listing records from 18 source posts
and 12 organizations. Forty-seven listings belong to untracked organizations;
one source post expands to 23 roles. The language mix is 45 EN, 7 JA, and 3
ZH-CN records. Source relationships are 44 official, 6 staff, and 5 third
party. All 55 lack a deadline, 42 lack location, and 6 lack an application URL.

These facts drove the one-post-to-many-listing schema, explicit partial fields,
application-route state, organization review queue, and separate source-post,
listing, and organization counters. The artifact is selected search output,
not prevalence data, gold labels, or a recall measurement.

## Discovery query and credit ceiling

Each lane has six queries: organization and role/transition families in EN,
ZH-CN, and JA. Each query has a 60-minute cadence, 24-hour lookback, one-page
and 20-result cap, and a stable query ID. The existing 15-minute `CycleRunner`
owns scheduling and cursors. There is no second cron.

At the configured TwitterAPI rate of 15 credits per returned tweet with a
15-credit call minimum:

| Increment if enabled | Jobs | Personnel | Combined |
| --- | ---: | ---: | ---: |
| Calls per cycle, hard cap | 2 | 2 | 4 |
| Credits per full cycle, hard cap | 600 | 600 | 1,200 |
| Credits per day, hard cap | 1,800 | 1,800 | 3,600 |
| USD per day at 100,000 credits/USD | $0.018 | $0.018 | $0.036 |
| Calls per day if every call is empty | 120 | 120 | 240 |
| Full 20-result calls before daily cap | 6 | 6 | 12 |

The planner reserves the full possible charge for calls planned together and
reduces `max_results` when the remaining daily allowance cannot fund 20
results. The run ledger records actual billing credits, including the minimum
for an empty attempted call. A query rejected by the local length cap records
zero provider calls and zero credits.

The runner rechecks remaining daily capacity immediately before transport, so
another completed call cannot make a previously planned call exceed the daily
ceiling. Discovery calls use the existing durable `CallState` cursor identity;
a new runner instance resumes with the stored cursor and overlap. A truncated
discovery response makes only its one configured bounded search request,
persists returned posts, and transfers the remaining window to the shared
backlog instead of multiplying the lane's result budget.

The query strings remain hypotheses until a separately authorized bounded
provider bakeoff measures actual syntax acceptance, per-language yield, false
positives, and coverage. Empty-call volume is why both the call count and
credit ceiling matter.

## Targeted extraction ceiling

The universal classifier adds no extra call for ordinary negative posts.
Positive events, opportunities, jobs, personnel changes, and ambiguous profile
candidates can trigger their own role-specific call. The hard limit is 20
targeted calls per cycle. Configured maximum output tokens are 2,000 for event,
opportunity, and profile extraction, 3,000 for personnel extraction, and 4,000
for job extraction.

A monetary maximum is intentionally unreported because the configured model's
input/output pricing and the real positive rate have not been measured in this
environment. Before activation, run a bounded real-label sample, record actual
input/output tokens by role, and calculate cost from that provider's then-current
price. Missing pricing remains a production blocker rather than being replaced
with an invented estimate.

## Provider-free verification boundary

Fake-provider tests prove disabled lanes add no existing A/B/C calls, query
planning respects cadence/windows/cursors/caps, untracked posts use normal
persistence, source query IDs survive, one post can create 23 idempotent job
rows, ambiguous profiles route only when present, invalid structured choices
roll back, and attempts store token/latency/error telemetry without source text
or secrets. Repeated observations preserve the earliest and latest organization
candidate timestamps and every source identity. Profile evidence,
self-authored personnel posts, and official announcements naming the person's
X handle converge on one person identity for the same account regardless of
arrival order. Two posts with the same canonical job URL converge on one
listing and retain both evidence rows. These tests do not establish real-world
precision, recall, or cost.
