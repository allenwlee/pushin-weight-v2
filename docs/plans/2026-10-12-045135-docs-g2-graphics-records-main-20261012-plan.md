---
title: Publish G2 editorial and graphics records to main
artifact_contract: ce-unified-plan/v1
artifact_readiness: execution-ready
product_contract_source: owner push-to-main request, October 12
execution: documentation
status: complete
git_publication_target: main
git_publication_selected_by_user: true
ollija:
  change_id: docs-g2-graphics-records-main-20261012-2026-10-12-045135
  branch: docs/g2-graphics-records-main-20261012
  workflow: documentation-publication
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Publish G2 editorial and graphics records to main

## Plain-English Summary

Make the current editorial choices, graphics-editor ownership and both image
variants available through remote main. Publish the authoritative coordination
snapshot and linked public G2 records/assets while preserving original worktrees,
private evidence and other sessions' latest coordination. No application changes
or deployment are part of this request.

Use this isolated checkout based on fd467363. Check file scope, links, asset
hashes, whitespace and secrets, then make a named-file commit with [skip render]
and non-forced push to main. Reconcile any concurrent main update and verify the
final remote commit/tree. Reuse existing unchanged review-page/asset browser
evidence rather than rerunning application tests.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g2-graphics-records-main-20261012`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g2-graphics-records-main-20261012/docs/plans/2026-10-12-045135-docs-g2-graphics-records-main-20261012-plan.md`
- Change: `docs-g2-graphics-records-main-20261012-2026-10-12-045135`
- Branch: `docs/g2-graphics-records-main-20261012`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g2-graphics-records-main-20261012/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g2-graphics-records-main-20261012/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `documentation-publication`
- Delivery target: `on-request`
- Owner selection recorded: `false`
- Delivery route: `staged`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

Owner explicitly requests push to main. This authorizes a Git documentation/assets
commit and verified non-forced main push without a PR. Application deployment
remains on-request; no staging/production service action is selected. Preserve
the original G2 worktree; this branch is only the publication transport. The
guide's unselected-application wording does not cancel the owner's Git request.

# Goal

Remote main contains the selected current coordination, exact model choices,
graphics-editor responsibility, public review/illustration artifacts and source
task plan, with working repository-relative G2 links and no private evidence.

## Product Contract

TOUCH: three authoritative charter/index/register documents, the existing G2
round-two plan, this publication plan and its linked public G2 analysis folders.
PRESERVE: root/G2 dirty files, application/configuration/runtime, private .local
evidence and source photos, other sessions' ownership and published log entries.

Verification: inspect latest-main diff and explicit staged file list; check
documentation links, JSON/embedded review data and raster/video assets; reject
secret values/private provider reasoning; git diff --check; verify remote main
equals the pushed candidate and compare published file hashes. Missing
machine-local evidence pointers remain explicitly machine-local.

## Progress

- Isolated publication checkout created from latest remote main fd467363;
  original worktrees preserved. Worktree hook generated this exact plan; enriched
  it as Git-only publication scope, separately from the source editorial plan.
- Three remote-only historical G1/G4/G5 session-log entries found and reconciled
  into the shared index. Published G4 draft discovery retained. Latest local
  G1–G5 coordination is the source snapshot, not their application code.
- Publication package:90named paths,31valid raster assets,21valid JSON files,
  three valid embedded review payloads, zero secret findings and zero new missing
  links.48older transport/other-stream references remain explicit machine-local
  pointers; the combined HTML contains complete current drafts/prompts. The old
  native-English standalone page and verbatim packet stay in their original
  archive; current English drafts are in the combined review. Provider workspace
  identifiers are redacted in published copies; original local evidence retained.
  Staged whitespace check passes; original G2 review/config hashes unchanged.

- Main content publication verified atb52881fcfd6cad263caef061d32d7ced4b19820d, 2026-10-12T14:07:38+09:00; [receipt](../analysis/2026-10-12-112151-g2-graphics-editor/publication-to-main.md). Original worktrees and private evidence preserved. Git-only endpoint achieved; documentation closeout commit follows.
