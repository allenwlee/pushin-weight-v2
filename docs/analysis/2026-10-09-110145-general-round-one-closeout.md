---
title: "General round one — closeout and lessons for round two"
created_at: "2026-10-09T11:01:45+09:00"
status: closed
round: 1
closed_by: owner
closeout: completed-scope-with-carry-forward
successor: docs/brainstorms/2026-10-09-110145-general-round-two.md
---

# General round one — closeout and lessons for round two

## Plain-English Summary

The owner closes the initial G1–G5 round and accepts moving unfinished work into
round two. Completed research, local implementation and production delivery keep
their actual outcomes. Unfinished features retain their evidence and receive an
assigned stream in the [round-two register](../brainstorms/2026-10-09-110145-general-round-two.md).

The old records remain available in place. Their open checkboxes and proposed
units describe historical unfinished scope; closing the round does not convert
them into completed features. New progress belongs to round two. Five familiar
session labels can be reused without extending the old execution history.

## Authority and evidence boundary

- Owner: “I'm ok with the unfinished work … kick those to this round, close out
  the initial rounds … clean record of this 2nd round.” The following instruction
  requests `ce-compound` on round one to inform round two.
- Evidence: the authoritative index/charter, canonical G1/G2/G4/G5 plans, G3
  design, saved analysis/verification receipts and relevant implementation.
- Root coordination branch: `docs/general-launch-coordination` at `33f20b97`.
  This older checkout is not the deployed application. Current-main readback in
  the preceding audit was `671e9682`; production conclusions below reuse the
  saved release records, not a new live test.
- Prior paid-trial limits, runtime permissions and release endpoints remain
  attached to their original scopes. This rollover changes documentation.

## Closed round-one outcomes

| Stream | Outcome at closure | Canonical prior record | Round-two destination |
| --- | --- | --- | --- |
| G1 | Staff/DeepSeek scaffold and shared R2 production deliveries recorded in PRs #49/#52. Broader identity and asset coverage unfinished. | [G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md) | [G1 assets](../brainstorms/2026-10-09-110145-general-round-two.md#g1--assets-and-graphicsed) |
| G2 | English editorial path, compatible OriginalContent consolidation and physical table names delivered; U9–U14/U16 complete per receipts. | [G2 plan](../plans/2026-09-30-051835-docs-g2-voices-corpus-plan.md) | [G2 editorial](../brainstorms/2026-10-09-110145-general-round-two.md#g2--editorial-decisions-and-voices) |
| G3 | Research/design pass completed; forecasting/market implementation not started under this record. Independent benchmark work is delivered separately. | [G3 design](../brainstorms/2026-10-05-163237-g3-evidence-forecasts-markets.md) | [G3 charts and analysis](../brainstorms/2026-10-09-110145-general-round-two.md#g3--chart-engine-and-inherited-analysis) |
| G4 | Requested API/MCP plan and discovery completed as drafts; no deployed server claimed. | [G4 plan](../plans/2026-10-07-053244-feat-g4-mcp-plan.md), [discovery](../brainstorms/2026-10-06-210526-g4-mcp-offering-and-scaffold.md) | [G4 sharing and access](../brainstorms/2026-10-09-110145-general-round-two.md#g4--sharing-x-and-inherited-api-work) |
| G5 | Selected feed/Post/navigation and published Chatter/Pulse integration completed locally; current work remains uncommitted/unpushed. | [G5 plan](../plans/2026-10-02-060108-feat-g5-general-page-plan.md), [detailed index receipt](../brainstorms/2026-09-30-104924-general-launch-index.md#round-one-workstream-record-closed) | [G5 integration](../brainstorms/2026-10-09-110145-general-round-two.md#g5--general-page-integration-and-release-preparation) |

The separate [official-company plan](../plans/2026-10-06-100039-feat-official-co-account-extraction-plan.md)
was already closed by the owner. Its later operating notes stay with that record;
this round does not reopen the classifier/list release or claim its rate-limited
follow-ups are completed. Independent benchmark work remains independently owned.

## Lessons carried into round two

| Finding from round one | Evidence and limit | Concrete round-two consequence |
| --- | --- | --- |
| Inspect what reaches the consumer before judging the producer. | G2 traced 49 database keyword matches → 2 editor matches → 1 writer input, then verified bounded retrieval and exact attribution. New [compounded learning](../solutions/workflow-issues/2026-10-09-110145-editorial-evidence-delivery-before-voice-evaluation.md). Offline retrieval proof is not a live prose-quality verdict. | B2-G2-01/02 freeze evidence for voice comparisons; B2-G3-01/02 and B2-G5-01 check actual chart/page inputs. |
| A downloaded image, an attributed image and a suitable portrait are different achievements. | G1 corrected a wrong-person image from a multi-biography page and preserved the missing-portrait state. [Existing learning](../solutions/workflow-issues/2026-10-05-142500-staff-photo-named-block-attribution.md). | B2-G1-01/02 retain subject evidence and fallback reason; an avatar can satisfy the author's-image fallback without becoming a verified portrait. |
| Coverage needs explicit counting units. | G1's 60 displayed records included 45 employment-supported people, holds and aliases; file counts differed from portrait coverage. [Existing learning](../solutions/workflow-issues/2026-10-05-142900-staff-research-coverage-counting.md). | B2-G1-03 reports people/assets/gaps separately. G2 source counts use cited support; G3 source observations and revisions retain their own units. |
| Producer-side storage success needs consumer-side read proof. | [R2 release](https://github.com/allenwlee/pushin-weight-v2/pull/52) records both service directions, hash equality and reads after restart; original files retained. | B2-G1-01/02 and B2-G4-01 exercise web/worker/export use of the selected image/video, including reuse and missing-media behavior. |
| Content preservation includes the selected publication, locale and citations. | [Cutover learning](../solutions/data-migration/2026-10-08-143200-original-content-cutover-checks.md) covers a missing featured pointer, oversized history query and citation identity recovered from original excerpts. G5 subsequently verified saved bodies and citation links in six locale/viewport views. | B2-G2-03/04, B2-G4-01 and B2-G5-01/02 preserve edition identity, chosen locale, every cited URL and durable links through feed turnover. |
| Historical charts and forecasts need different time boundaries. | Benchmark/G3 contracts distinguish source dates, observation cutoffs, rolling counters, rank and score. A complete post-release reference week cannot be available to a pre-release forecast. This is an established measurement constraint, not evidence of a deployed forecast engine. | B2-G3-01/02/03 retain units, measurement/as-of dates and snapshot/live choice; forecast qualification remains explicit. |
| A prototype and a public integration have different evidence. | G4's loopback sample is design input; G5's real-reader integration has local browser evidence. Neither proves a deployed public MCP service or General launch. | B2-G4-03 records real access/output contracts; B2-G5-03 preserves local work and records any later selected release separately. |
| Long-lived stream names need bounded rounds and explicit transfers. | The October 9 audit found reviewing, paused, planning and local-complete labels across the five finished passes. The owner selected closure with carry-forward. | Each round-two item in the register has its own ID, source, assigned stream and state; old checkboxes are not ticked merely to close the round. |

## Existing constraints still matter

- G2's current owner-selected rollback reevaluation is **October 9, 16:37:56
  JST**, based on the unchanged October 8 production cutover. Some older receipts
  and the deployed retirement report still refer to seven days. B2-G2-03 owns
  reconciliation before cleanup; the date alone is not a deletion instruction.
- G5 retains the known Japanese geography-seed failure. The recorded affected
  run was 279 passing tests plus that failure, with 49 clean browser obligations;
  it is not an all-green release record.
- G3 statistical target selection, market support/submission decisions and G4
  scenario-write/auth/analytics choices remain unresolved inputs. The new round
  preserves these decisions rather than calling them implemented lessons.
- The earlier [inherited release-gates learning](../solutions/workflow-issues/2026-09-25-203900-authorized-release-blocked-by-inherited-gates.md)
  remains applicable: independent branch ordering is not a product dependency.
  Shared files, migrations and actual service occupancy still need coordination.

## Compounding record

Full `ce-compound` research was executed inline under this repository's Codex
task mapping. One distinct durable learning was added; the existing G1 and
OriginalContent learnings above were reused. A seven-day session probe inspected
33 files and selected two prior G2 histories, corroborating the diagnosis and
repair sequence. No new live test or model-quality claim was made.

The new learning is discoverable through the existing AGENTS.md solutions
pointer and round-two links. Source/claim checks and document validation are
recorded in the completing session log. Runtime work, local previews, private
databases and all other sessions' claims remain in place.
