---
title: feat/docs-reference-curation plan
type: docs
date: 2026-09-25
topic: docs-reference-curation
artifact_contract: ce-unified-plan/v1
execution: docs
ollija:
  change_id: feat-docs-reference-curation-2026-09-25-063038
  branch: feat/docs-reference-curation
  workflow: work
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/docs-reference-curation`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/docs-reference-curation/docs/plans/2026-09-25-063038-feat-docs-reference-curation-plan.md`
- Change: `feat-docs-reference-curation-2026-09-25-063038`
- Branch: `feat/docs-reference-curation`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/docs-reference-curation/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/docs-reference-curation/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
- Delivery target: `on-request`
- Owner selection recorded: `false`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Never promote a staging candidate whose automated checks failed.
- Implementation failures return to the parent implementation workflow for diagnosis, correction, recommit, and restaging.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

- Owner-directed in this conversation: commit the documentation-only changes
  to `main`. This authorizes a Git push only and does not authorize staging or
  production deployment. Keep the change isolated from the unrelated dirty
  root checkout and push only a fast-forward commit.

# Reference Curation and Docs Taxonomy

## Plain-English Summary

Keep `docs/reference/` focused on detailed, current documents people use to
understand PushinWeight and refer agents to. Maintain distinct classifier,
commenter, and translator references; create a consolidated rare-types
reference; and move dated evaluations, investigations, iteration targets,
operator procedures, and design assets to their existing documentation homes.
Add a draft taxonomy that explains how to choose among the existing folders.

The change updates links affected by moves, keeps exact machine-readable
contracts as test fixtures, and makes the reference-document procedure
available as a project skill to Claude, Codex, and agents following
`AGENTS.md`. The taxonomy is a draft for owner review; a docs-router skill is
out of scope until that review is complete. No application behavior changes.
Verification checks destinations, links, fixture paths, and the documentation
diff. Do not run tests for this documentation-only task.

## Product Contract

### Reference layout

- Keep `docs/reference/classifier-prompts.md` at its current path and do not
  edit it; it currently has unrelated uncommitted changes in the root checkout.
- Add `docs/reference/commenter.md` for current generated analyst commentary.
- Keep `docs/reference/translator-output.md` at its current path, keeping
  literal translation distinct from commentary and registry translation.
- Keep `docs/reference/post-content-artifacts.md` as the shared storage,
  lifecycle, and demand reference. Link to it from the focused commenter and
  translator documents.
- Create `docs/reference/rare-types.md` from the current rare-type operator
  guide and read contract. Move the machine-readable contract to
  `tests/fixtures/rare_type_intelligence_read_contract_v1.json` and update its
  test reference.
- Consolidate the Stage 1C evaluation and intelligence-analysis prose in
  `docs/analysis/2026-09-10-203138-stage1c-contracts.md`. Move its read-shape JSON to
  `tests/fixtures/stage1c_intelligence_read_contract_v1.json` and update its
  test reference. Preserve the full detail in the combined document.

### Dated-file routing

- Move these 11 Bridgewright contracts to `docs/iterations/`, preserving their
  filenames: `2026-08-19-132714-v24-bridgewright-target.md`,
  `2026-08-19-174833-production-filter-feed-bridgewright-target.md`,
  `2026-08-24-162449-home-chart-time-axes-bridgewright-target.md`,
  `2026-08-26-141113-home-preferences-ui-regressions-bridgewright-target.md`,
  `2026-08-26-202742-pulse-feed-timezone-polish-bridgewright-target.md`,
  `2026-08-28-134649-cyber-quan-icons-bridgewright-target.md`,
  `2026-08-28-164425-feed-headline-usability-bridgewright-target.md`,
  `2026-08-28-181416-chart-hover-freeze-bridgewright-target.md`,
  `2026-08-31-221955-feed-country-geography-bridgewright-target.md`,
  `2026-09-01-114311-feed-inspection-pagination-bridgewright-target.md`, and
  `2026-09-21-155037-ui-glyphs-footer-filters-locale-chart-bridgewright-target.md`.
- Move `2026-08-25-135300-why-first-headline-validation-and-event-anchors-reference.md`
  to `docs/investigations/`.
- Move `2026-09-08-194415-enrichment-contracts.md`,
  `2026-09-09-112957-classification-analysis-contract.md`,
  `2026-09-09-185300-classification-quality-evaluation.md`, and
  `2026-09-12-030118-u18-human-ambiguity-study.md` to `docs/analysis/`.
  Treat versioned material there as dated evidence, not as a current contract.
- Move `2026-09-10-203138-profile-history-and-affiliation-candidates.md` to
  `docs/operations/`.
- Move `2026-09-21-123711-selected-taxonomy-glyphs.svg` to
  `docs/ideation/assets/`.
- Keep `2026-08-29-162947-country-flag-svg-reference.html` in `reference/` as
  an approved visual lookup asset.
- Leave the modified `2026-09-24-210000-product-x-hf-identity-policy-v1.md`
  and all other unrelated root-checkout changes untouched.

### Reference-document skill and project guidance

- Create `.claude/skills/updating-reference-docs/SKILL.md` as the project
  skill. Expose the same skill at `.agents/skills/updating-reference-docs`
  using the existing symlink convention.
- Rework `docs/reference/updating-reference-docs.md` into a concise
  human-readable guide that points to the skill.
- Add direct skill pointers to root `AGENTS.md` and `CLAUDE.md`; agents using
  `AGENTS.md` (including OpenClaw) can discover the same canonical skill.
- Require comprehensive, detailed current-state snapshots; do not summarize
  away detail or preserve changes as a document history. Use plain English
  for explanations and exact technical language where needed.
- Do not create a docs-router skill until the owner has reviewed
  `docs/docs-taxonomy.md`.

## Implementation and Verification

1. Add the taxonomy draft at `docs/docs-taxonomy.md`, describing the existing
   folder purposes and prohibiting new folders under `docs/` without approval.
2. Create the commenter reference from current synthesis/commentary sources;
   keep the translator reference at its current path and cover current literal
   and registry translation. Preserve their distinction and cross-link shared
   artifact lifecycle details.
3. Create the rare-types reference from current operator instructions and
   current rare-type reader/status contract details. Move the JSON schema to
   the named fixture and update `tests/test_rare_type_readers.py`.
4. Combine the Stage 1C evaluation Markdown and intelligence-analysis Markdown
   into `docs/analysis/2026-09-10-203138-stage1c-contracts.md`. Move the JSON read-shape contract to the
   named fixture and update `tests/test_intelligence_readers.py`.
5. Move the dated documents and asset to the listed existing directories.
6. Update all in-repository paths in plans, tests, `bridgewright.yaml`,
   `README.md`, `AGENTS.md`, and the reference documents as applicable.
7. Create the project skill and pointers; preserve the source/update details
   needed to maintain the seven current runtime references and README.
8. Verify that every moved file has its destination, every changed in-repo
   link resolves, the two tests reference the new fixture paths, and
   `git diff --check` passes. Do not run the tests unless the owner separately
   requests them.
9. Inspect the final changed-file list and commit only this work. Push the
   commit to `main` as a fast-forward; do not stage any files from the root
   checkout.
