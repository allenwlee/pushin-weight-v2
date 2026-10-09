---
title: "General round two — G1–G5 scope and carry-forward register"
created_at: "2026-10-09T11:01:45+09:00"
status: open-for-planning
round: 2
proposed_version: "0.2.0b2"
predecessor: docs/analysis/2026-10-09-110145-general-round-one-closeout.md
---

# General round two — G1–G5 scope and carry-forward register

## Plain-English Summary

Round two starts with the useful work already completed and the unfinished
requirements accepted by the owner. G1 handles assets, G2 editorial choices and
voices, G3 charts and inherited analysis, G4 sharing and inherited API work, and
G5 the General experience. Keep these five labels for concurrent sessions.

The [round-one closeout](../analysis/2026-10-09-110145-general-round-one-closeout.md)
preserves earlier outcomes. This document is the fresh scope/ownership register;
the [charter](2026-09-30-104924-general-launch-charter.md) still holds detailed
owner requirements. The proposed next beta is `0.2.0b2`, tagged
`v0.2.0-beta.2`; no version has been changed by this record.

## How the rollover works

- Round one is **closed with carry-forward** as an owner decision. Completed
  receipts, research, local code and unresolved checkboxes remain intact.
- Every unmet, non-superseded owner requirement in the prior charter/plans
  transfers to the corresponding round-two stream. The rows below group that
  work; they do not discard an unlisted detail. Prior proposals stay proposals,
  and previously excluded or waived work does not become required again.
- A carry-forward row means **accepted into round-two planning**, not already
  implemented. Implementation sequencing and the bounded beta release scope
  belong to the next stream plans. No new deadline or paid allowance is inferred.
- Use IDs `B2-G1-01` etc. Keep the original requirement/unit IDs as provenance.
  Avoid `G1-R2`: existing requirement IDs and Cloudflare R2 already use that form.
- Existing root index/charter remain the shared entry points. New session claims
  identify **round 2**, G item, bounded files and current plan. New detailed
  execution logs belong in the round-two plan, not appended to the closed plan.
- On selecting an implementation plan, follow Ollija in the intended branch/
  worktree and use its returned path. Reuse existing code/context, preserve dirty
  work, and avoid selecting a closed round-one plan as a fresh execution target.
  This register is coordination, not a parallel implementation plan.

## G1 — Assets and graphicsed

**Starting assets:** delivered staff identity/media foundation and shared R2;
saved DeepSeek/MiniMax research and explicit coverage gaps.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G1-01 | New owner priorities; G1-R04; existing G2 picture editor | Every content item receives image/video. Apply relevant-person picture → source author profile picture → company logo; record why the asset fits. Resolve multiple authors and all-fallbacks-missing cases. | Ready to plan |
| B2-G1-02 | New graphicsed guide; G2-R48 picture modularity | Selection/creation/treatment guidance, reuse/caching, attribution and delivery/export variants. Explicitly hand off G2-owned picture/media files before changes; coordinate with G4 exports and G5 presentation. | Ready to plan |
| B2-G1-03 | Unfinished G1 identity/acquisition scope and saved dossiers | Remaining portraits, names/roles and wrong-company corrections; remaining selected brands and broader Call A/database staff population; ongoing acquisition/worker activation, budget and coverage decisions. Review/import saved research only within its actual evidence and authority. | Carried forward |

**Apply round-one lessons:** named-block image attribution, separate people/file/
portrait counts, and real consumer access to shared media. An author avatar
fallback does not imply the depicted subject has been identity-verified.

## G2 — Editorial decisions and voices

**Starting assets:** delivered English writing, source-grounding/context repair,
shared packet preparation and OriginalContent readers/storage.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G2-01 | Unfinished ja/zh_cn voice scope; new explicit priority | Japanese and Simplified Chinese house voices with source-faithful copy, reviewed examples and bounded evaluation. Use the actual story evidence delivered to the writer. | Ready to plan |
| B2-G2-02 | New chart-editor/chart-setter priority | Rules for deciding when/which chart supports a content item; produce the settings/evidence request that G3 validates and renders. | Ready to plan |
| B2-G2-03 | G2 U15 and explicit exclusions after U16 | Retire obsolete storage/aliases and evaluate any remaining rename/reference work only under a selected scope. Reconcile 24-hour owner rollback decision with seven-day report behavior; preserve native consumers, restore proof and records until cleanup is authorized and justified. | Carried forward |
| B2-G2-04 | G2/G5 published-history dependency | Define durable publication/history retention for permanent content and share links. Coordinate old editions, source lists, media and selection pointers with G4/G5. | Carried forward |
| B2-G2-05 | Remaining G2 quality/coverage decisions | Preserve open live-quality qualification, discovery/unnamed-teaser coverage, image-claim evidence and earlier undecided editorial choices. Reconcile old prototype checkboxes against delivered behavior before choosing work; no repeat of completed experiments. | Carried forward |

**Apply round-one lessons:** [verify evidence delivery before voice evaluation](../solutions/workflow-issues/2026-10-09-110145-editorial-evidence-delivery-before-voice-evaluation.md);
keep anchors, background and actual cited support distinct. Publication and
storage changes preserve saved locale/version and selected-story identity.

## G3 — Chart engine and inherited analysis

**Starting assets:** deployed independent benchmark/usage collection and charts,
G3 evidence/forecast research and the GLM/DeepSeek comparison example.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G3-01 | New chart-engine priority | Generalize the release/source chart with reusable data/configuration/calculation/rendering and suitable existing homepage interactions. Define metric units, baselines, series, windows and annotations. | Ready to plan |
| B2-G3-02 | New share-settings priority; G4/G5 handoff | Validated saved chart state, locale and data-as-of identity; explicit frozen snapshot versus live-updating behavior. Supply the same state to editor, browser and share/export consumers. | Ready to plan |
| B2-G3-03 | Unimplemented G3 design, G3-R12 and later statistical/market requirements | Historical analysis, qualified forecast target/baselines/uncertainty, reader scenario questions, prediction record and market-candidate/support workflow. Reassess the old benchmark dependency using delivered evidence; retain unresolved statistical/threshold/submission/notification choices. | Carried forward; decisions remain |

**Apply round-one lessons:** rolling downloads, exact-model usage, raw score and
rank keep their separate meanings. A post-release comparison baseline cannot
leak into a pre-release forecast. Chart implementation and forecast qualification
have separate completion evidence; this rollover does not claim the old hold
was a completed forecast implementation.

## G4 — Sharing, X and inherited API work

**Starting assets:** API/MCP discovery/draft, public-output restrictions and
October 9 X research in the shared index.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G4-01 | New sharing priority | Permanent content/chart URLs, chosen locale and settings, share previews and image/video export. Preserve the chosen edition and distinguish snapshot/live chart links. | Ready to plan |
| B2-G4-02 | Owner's X sharing/login option | Compare link sharing and native media posting; check actual API access/cost/permissions and explicit user share action. Compare mandatory X login with optional X connection; mandatory login remains an option. | Ready to plan; login choice open |
| B2-G4-03 | Unimplemented G4 API/MCP draft | Retain saved-output API/MCP, auth/disclosure, possible private scenario writes, analytics and integration work. Current public content/identity restrictions still apply. The sample server is a prototype; final MCP integration follows actual upstream capability availability. | Carried forward; decisions remain |

**Apply round-one lessons:** exact saved outputs and permissions must survive
every consumer path. Browser JSON and a loopback mock server do not establish a
public API contract. Native posting permission and login remain separate.

## G5 — General-page integration and release preparation

**Starting assets:** accepted General design, real lower feeds, permanent Post
pages/navigation, locally verified published Chatter/Pulse integration and saved
browser evidence. Preserve `.worktrees/feat/g5-general-page` and its dirty code.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G5-01 | New chart/asset/voice/sharing priorities; current local General work | Integrate G1/G2/G3/G4 components incrementally into the accepted layout and detail pages; verify desktop/mobile, all supported locales and Human/Agent geometry. | Ready to plan |
| B2-G5-02 | Unfinished G5 release/readiness scope | Resolve the recorded Japanese geography-seed failure, durable published-history/link behavior with G2, actual candidate assurance/performance and remaining General navigation/source-display decisions. Reuse valid earlier evidence. | Carried forward |
| B2-G5-03 | Existing local-only endpoint; future launch | Preserve and reconcile local work onto the eventual chosen candidate. Record any later commit/push/deployment endpoint explicitly. Default landing/domain routing, including the recorded pushinweight.si purchase, remains a selected-scope decision. | Carried forward; delivery unselected |

**Apply round-one lessons:** check database → shared reader → page → recipient
with real saved content; keep prototype, local browser and production receipts
separate. Closing round one is not permission to remove its dirty worktree.

## Shared agreements for parallel work

Agree these interfaces before overlapping code edits. G1/G2/G3/G4 own their
outputs; G5 owns page integration. A shared module has one editing owner at a
time, with an explicit handoff when ownership changes.

| Agreement | Required meaning | Lead / consumers |
| --- | --- | --- |
| Content reference | Post or OriginalContent, stable identity, saved revision/edition and locale | G2 + G5 / all |
| Asset selection | Selected image/video, source/subject evidence, fallback reason, reusable variants | G1 / G2, G4, G5 |
| Chart request/state | Source metrics/series, units, window, baseline/transform, annotations, locale, cutoff/as-of and snapshot/live choice | G2 editorial intent + G3 validation / G4, G5 |
| Share view | Exact content reference, chart state, chosen language and asset variant; recipient locale must not silently replace shared language | G4 / G3, G5 |

Start with one GLM5.3 content item carried through all applicable components,
then a second configuration proving chart reuse. Exercise both a third-party
Post and OriginalContent. No global “finish G1 before G2” ordering is introduced;
only concrete interface, shared-file, migration or runtime conflicts constrain
concurrent work.

## Round-two completion records

Each bounded plan records delivered behavior, evidence scope, actual endpoint,
remaining items and their destination. Relevant regression checks cover changed
existing behavior; earlier checks are reused while their assumptions still hold.
When a subtask finishes, close it without reopening round one. When the owner
closes round two, produce the same explicit outcome/transfer record for any
unfinished scope.

No implementation plan or active implementation owner is created by this
register. Use the authoritative [index](2026-09-30-104924-general-launch-index.md)
for current claims and ON/OFF entries. The retained branches/worktrees are source
material, not an instruction to reset, delete or deploy them.
