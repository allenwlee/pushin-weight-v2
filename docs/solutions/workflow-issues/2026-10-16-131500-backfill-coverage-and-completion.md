---
title: Prove X backfill coverage separately from processing completion
date: "2026-10-16"
category: workflow-issues
module: harvest
problem_type: workflow_issue
component: service_object
severity: high
applies_when:
  - "Accepting a historical X backfill as equivalent to scheduled collection"
  - "Explaining low recovered volume or comparing historical days"
  - "Scaling a verified daily batch to a month"
tags: ["backfiller", "collection-coverage", "pagination", "reconciliation", "enrichment", "provenance", "harvester-parity"]
---

# Prove X backfill coverage separately from processing completion

## Context

The August recovery successfully processed its saved posts, but that did not
establish that it collected what normal harvesting would have found. The prior
production campaign eventually verified seven windows containing 13,491 Posts;
the subsequent August 9 investigation still found a collection-scope gap
(session history). The resolved lesson is how to distinguish and verify those
claims. The total missing August 9 population remains unresolved.

The inspected backfill adapter accepts only B1–B3 and C1–C3. Normal collection
also has Call A and RARE_EXTRA paths. Reusing CycleRunner and its Post writer
therefore did not establish equivalent collection scope. Independently, the
enrichment verifier accepts a selected set of saved IDs: it cannot discover
posts the provider never returned or an omitted route never requested.

This is knowledge captured from the October 16 audit of the local
`4e60a2f1` tree and retained execution receipts. It is not a claim that adding
the missing routes has shipped, or that their contribution explains the entire
historical volume difference.

## Guidance

### Keep four acceptance claims separate

| Claim | Required evidence | What it cannot establish alone |
| --- | --- | --- |
| Collection scope matches the selected harvester policy | Enumerate every enabled route, brands, account roles, exclusions, queries, bounds and downstream gates; explain every deliberate difference | The provider returned every eligible historical post |
| Every planned query finished | Exact query and configuration identity, committed page/cursor history and terminal reason for every scope | A page cap, error or unknown outcome is exhaustion; omitted routes are covered |
| Returned data was accounted for | Raw appearances, unique native IDs, overlaps, rejects with reasons, saved/updated IDs and run membership reconcile | Cross-date traffic predicts exact historical recall |
| Saved posts are usable | Canonical translations, classification and applicable extraction records pass persisted-data verification through shared publishers | Acquisition completeness outside the saved cohort |

Report these separately even if a process or CollectionRun reports success.
Set the required claims before execution. A target volume is a diagnostic
benchmark, not a stop condition or a way to waive missing-route evidence.

### Compare the same posts before assigning a cause

Use known historical positives and the exact frozen query to trace each ID:
query eligibility → provider response → matching/filtering → persistence →
campaign membership → canonical enrichment. Compare the scheduled and backfill
callers on identical inputs. Label an untested explanation as a hypothesis.

A defect shared by both callers can lose posts, but it does not by itself
explain their difference. Likewise, an omitted route proves scope drift without
quantifying its contribution. Current list membership cannot reconstruct past
membership. Official-account attribution markers also do not count every
Call A result, because staff candidates use another path.

### Preserve the execution evidence through recovery

Record requested and effective bounds, query/configuration identity, page
counts, cursor changes, terminal reasons, per-stage counts and distinct IDs.
Distinguish publication time from first ingestion time when constructing a
historical baseline. Deduplicate cohorts by stable native identity before
adding totals.

Recovery must retain original inputs, saved replies, physical attempts,
reservations and unknown costs. An already-paid valid reply awaiting publication
is different from an unsent request, an invalid reply and a sent request whose
outcome is unknown. The prior campaign's replay failures showed why a successful
parser test is insufficient: exercise the real publisher with complete and
pending members of the same original packet, then interrupt and resume
(session history). A successful repair does not prove that its source is in
the next deployed image; record exact candidate activation separately.

## Why This Matters

Processing success can hide acquisition loss indefinitely: every saved post
looks healthy, while missing posts never enter the denominator. Conversely,
raw provider counts overstate unique stored posts when routes overlap or
matching rejects irrelevant results. These errors produce false completion
claims and unreliable resource estimates for a month-long run.

The useful correction is an evidence chain from planned scope to persisted
outputs. It supports diagnosis without assuming that broad search, pagination,
list coverage or a particular shared filter caused an unmeasured shortfall.

## When to Apply

- Before declaring a day or campaign complete or scaling its resource estimate.
- When a recovered day has lower volume despite finished scopes or healthy enrichment.
- When promoting staging data to production or resuming previously paid work.

## Examples

### August 9 cohort totals

The verified staging cohort contained 1,660 distinct Posts. Production already
held 782; 730 appeared in both. Copying the 930 missing Posts produced
**782 + 1,660 − 730 = 1,712**, not 2,442. Verification of those 1,660 source
Posts and the live union established their storage quality, not full-day recall.

### One page per invocation did not mean one page per campaign

The original broad-window receipts contain these counts, including the final
empty page in each walk:

| Route | Pages | Nonempty pages | Raw appearances |
| --- | ---: | ---: | ---: |
| B1 | 66 | 65 | 1,293 |
| B2 | 11 | 10 | 190 |
| B3 | 3 | 2 | 36 |
| C1 | 12 | 11 | 205 |
| C2 | 4 | 3 | 51 |
| C3 | 4 | 3 | 57 |
| Total | 100 | 94 | 1,832 |

B1 covered 07:15–24:00 UTC; the other five covered 07:00–24:00. Earlier
coverage used 15-minute slices, so this was a mixed execution strategy rather
than six identical 24-hour queries. All six broad walks recorded drained
terminal responses. Their 1,832 raw appearances are not 1,832 unique Posts.

The database adapter also limits a physical step to one page, then saves its
cursor and loops. Reading that setting as a campaign-wide 20-post limit would
misdiagnose the problem. A separate later 49.5-hour width probe retrieved 168
pages / 3,360 appearances and stopped at its page cap. Its control hour drained
after six pages / 82 appearances. That probe cannot establish wide-query
exhaustion or full equivalence. Do not merge the two investigations' outcomes.

### Differences that were proved, and explanations that were not

- The adapter's six-route allowlist omits A and RARE_EXTRA. Contribution to the
  full shortfall was not measured. October 15 logs showed 663 Call A inserts
  platform-wide; 24 official-account mention rows in a four-brand subset were
  not a valid upper bound on that subset's total Call A contribution.
- Mixed-script word boundaries and GLM context requirements caused demonstrated
  exclusions, but were shared by the compared callers. Same-population replay
  accepted all 930 staging-only and 730 overlapping Posts, 2,089 of 2,094 older
  missed Posts, and all 855 re-found references. These findings cannot explain
  most of the differential loss by downstream matching alone.
- Two known posts were available by ID lookup but absent from tested searches.
  This proves a lookup/search discrepancy for those cases, not its backend cause.
- A roughly 4,000-post July 30 expectation is a planning benchmark. Counts from
  another date, counts inflated by later backfills, or reaching that number
  cannot certify complete historical recovery.

## Related

- [Investigation receipts and July 30 continuation plan](../../plans/2026-10-16-075314-ops-aug09-staging-promotion-20261016-plan.md): dated queries, corrections and retained evidence locations.
- [Backfill collection adapter](../../../monitor/backfill_collection.py): `CALL_IDS`, `validate_scope`, request loop and committed checkpoints.
- [Shared runner](../../../monitor/cycle.py): `plan_calls_for_cycle`, scheduled author exclusions, Call A role handling and rare-type search.
- [Persisted enrichment verification](../../../monitor/backfill_enrichment.py): `completion_facts` and `verify_cohort`.
- [Historical pipeline-wiring learning](../architecture-patterns/backfiller-and-llm-classifier-pipeline-wiring.md): useful origin of shared orchestration; its July scheduler, JSON-state and inference instructions need a scoped refresh before operational use.

Private source receipts remain on fuchitalee under
`~/.local/share/render-operations/2026-10-16-aug09-staging-promotion/` and
`~/.local/share/render-operations/2026-10-15-production-backfill-readiness/`.
Raw provider payloads, credentials and personal post data are not reproduced here.
