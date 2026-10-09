---
title: "Publish General round-one closeout and round-two coordination"
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: documentation
status: completed
ollija:
  change_id: docs-general-round-two-records-2026-10-09-042111
  branch: docs/general-round-two-records
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Publish General round-one closeout and round-two coordination

## Plain-English Summary

Publish the owner's completed round-one closeout and new round-two register on
a dedicated documentation branch so the next G1–G5 sessions can recover them
from Git. Include the shared charter/index, related closure notes, new learning
and General vocabulary. Preserve current-main release history and unrelated
working changes in the authoritative root and implementation checkouts.

Completion is a verified remote branch containing only the selected documents.
The current request selects commit-and-push; application delivery remains
separate. Validate the changed record links, metadata, historical preservation
and the exact staged file set before publishing.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/general-round-two-records`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/general-round-two-records/docs/plans/2026-10-09-042111-docs-general-round-two-records-plan.md`
- Change: `docs-general-round-two-records-2026-10-09-042111`
- Branch: `docs/general-round-two-records`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/general-round-two-records/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/general-round-two-records/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
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

The owner asks “shouldn't we push these?” after explicitly identifying the
updated coordination documents. That selects commit-and-push for this bounded
documentation change. `delivery_target: on-request` remains because no staging
or production endpoint is selected. The generated guide alone supplies no
authority; this owner request supplies the commit/push authority. No PR, merge,
staging or production release is required to reach the requested endpoint.

**October 9 continuation:** the owner now explicitly requests “merge to main.”
This authorizes merging the published documentation snapshot into `main`,
including a pull request if used for the merge. The application delivery target
remains `on-request`; no staging step or application deployment is selected.
Use `[skip render]` on the documentation merge as required by the repository
README. Completion is observed remote-main inclusion of this branch's candidate
commit. Preserve newer local session handoffs and all other worktrees.

**G3 handoff follow-up:** the owner asks to “push and commit to main when done”
after confirming G3's own-worktree rule. Publish the existing G3 round-two
handoff with that rule and its shared index/charter pointers. Reuse this clean
documentation worktree, advance it to current main, and preserve all other
streams' published and local content. The endpoint is a verified non-forced
push to `main` with `[skip render]`; no application deployment or G3
implementation worktree creation is selected. This continuation uses the same
publication plan and retains `delivery_target: on-request`.

# Goal

The remote `docs/general-round-two-records` branch contains the current
coordination snapshot and all round-one closure records, based on main
`671e968290780813bdbbfb9cd0d37bb74f601c6a`.

## Product Contract

- Publish the authoritative index and charter, round-one closeout, round-two
  register, new evidence-delivery learning and their supporting G3/G4 records.
- Preserve G1's newer main-branch R2 release history while adding closure
  metadata/notes. Publish current canonical G2/G4/G5 records and the superseded
  initial G1 planning record with their explicit closure notes.
- Add only the General vocabulary section to current-main `CONCEPTS.md`;
  preserve existing main entries and exclude unrelated root glossary changes.
- Keep branch-matched Ollija publication guidance valid. Earlier closed-plan
  metadata is historical and does not select this branch's delivery endpoint.
- Normalize portable links in the newly authored current-round records;
  historical references to private evidence/previews remain machine-local.
- Preserve the active independent metric-window owner's shared notes.

## Verification and completion

1. Review named-file changes and confirm no application/configuration edits.
2. Verify closure metadata in all prior records and 17 unique round-two items.
3. Verify links in the new round documents and the learning; run frontmatter
   and claim checks plus scoped whitespace checks. No runtime tests are needed
   for this documentation publication.
4. Run `ollija annotate-plan` and its check before Git mutations. Stage and
   commit only the named publication files, then push the live HEAD.
5. Read the remote branch SHA and compare it with the local commit. Record the
   resulting receipt in the authoritative index/session without claiming a merge
   or deployment. Preserve other worktrees and their uncommitted work.

## Publication receipt — October 9, 2026

- Published commit `7babf0228bf7a885931829a2c94dd0245683a64d` to
  `origin/docs/general-round-two-records`; `git ls-remote` confirmed the same SHA.
- The exact committed scope was 16 Markdown documents. Named-file review,
  whitespace checks, new-document link checks, learning frontmatter/claim checks
  and Ollija annotation checks passed. Runtime tests were not needed or run.
- Preserved main's newer G1 release history and glossary entries, canonical
  implementation worktrees, unrelated root changes and the metric-window owner.
- Completed the authoritative index publication claim and recorded its OFF
  entry. This follow-up receipt records the already verified publication.
- No pull request, merge, staging or production deployment was performed.

## G3 handoff publication — October 9 continuation

Publish only the G3 handoff section and workspace instructions in the existing
round-two register, its charter/index pointers and this continuation record.
G3's future implementation must use its assigned worktree and record the exact
path/branch when created; shared coordination stays in the authoritative root.
The existing G3 historical capture and private evidence references retain their
stated dates and machine-local limits.

Verify that all non-G3 register content is byte-identical to current main,
the new workspace anchor resolves, and the selected diff contains only these
four Markdown files. Run scoped whitespace and annotation checks, commit with
`[skip render]`, push to `main` without force, and confirm the candidate is on
remote main. Record the observed receipt in the authoritative index. Preserve
other sessions' unpublished handoffs and implementation worktrees.
