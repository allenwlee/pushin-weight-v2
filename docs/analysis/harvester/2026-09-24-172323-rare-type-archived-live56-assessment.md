---
title: Rare-Type Archived Live56 Assessment
date: 2026-09-24
topic: combined-rare-type-extra-search
status: pass
---

# Rare-Type Archived Live56 Assessment

This offline finalization passed the functional, identity, receipt, and budget checks for the pinned rare-type tuple. It used frozen evidence only: no retries or new provider calls were made. There is no numeric precision, recall, yield, overlap, or junk-share release bar.

## Evidence

- Source sample: 56 posts selected deterministically from 1337 unique rows across 192 historical quarter-hour windows. The source search estimate was 22935 credits; selecting and assessing the archived sample spent zero incremental TwitterAPI credits.
- Independent labels: 17 keep, 34 drop, and 5 uncertain. These are blind machine-reviewed source labels, not human gold, and were not externally fact-verified.
- TypeSafe receipts: 112 physical attempts, 110 successful responses, and 2 owner-accepted HTTP errors with unknown usage. The capture is explicitly not represented as complete.
- Cost: successful token receipts estimate $0.009196950; conservative reservation across every attempt is $0.036414462 against the $0.25 ceiling. Neither amount is an invoice.

## Blind-label / Jev outcomes

| Source label | Jev outcome | Cases |
| --- | --- | ---: |
| drop | junk | 21 |
| drop | kept | 2 |
| drop | provider_error_accepted | 2 |
| drop | review_needed | 9 |
| keep | junk | 2 |
| keep | kept | 8 |
| keep | review_needed | 7 |
| uncertain | junk | 3 |
| uncertain | kept | 1 |
| uncertain | review_needed | 1 |

All definite keep labels in this archived live sample are model or harness releases. The sample supplies no live-positive coverage for personnel changes, jobs, events, or opportunities. Source review could use captured article context that was not always present in Jev's public-state serializer.

The two accepted HTTP failures remain errors with unknown usage; they were not retried, relabeled from provider output, or replaced with fabricated responses. The frozen fixture was used while tuning routing, so its functional result is in-sample rather than a prospective quality estimate.

Runtime assessment digest: `03165d5084fb8605e5eaa115f5dd98274bb5e7a0a2bfa334e5200bc8776a726a`.
