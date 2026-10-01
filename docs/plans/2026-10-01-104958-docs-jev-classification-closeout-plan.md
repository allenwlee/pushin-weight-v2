---
title: Preserve the Jev classification research on main
status: verified-awaiting-git-publication
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-jev-classification-closeout-2026-10-01-104958
  branch: docs/jev-classification-closeout
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Preserve the Jev classification research on main

## Plain-English Summary

Publish the completed research and the decision to keep 0731, so agents can
find and inspect it from an ordinary clone of `main`. Preserve the exact saved
inputs, outputs, scorecards and experimental scripts as historical evidence.
The model, application, prototype, database and deployment are unchanged.

The owner requested **"commit/push to main"** on October 1. Completion is a
verified remote commit, not a Render deployment. Use this isolated
documentation branch based on `origin/main`; preserve every other session's
files and the four modified experiment application/test files. Validate
portable links, JSON, evidence hashes, secret-pattern checks and the exact
commit scope. Do not run tests or paid inference.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/jev-classification-closeout`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/jev-classification-closeout/docs/plans/2026-10-01-104958-docs-jev-classification-closeout-plan.md`
- Change: `docs-jev-classification-closeout-2026-10-01-104958`
- Branch: `docs/jev-classification-closeout`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/jev-classification-closeout/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/jev-classification-closeout/render.yaml`
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

Owner authorization: commit and non-forced push of this documentation/evidence
archive directly to `origin/main`. This is not staging or production delivery;
`delivery_target: on-request` refers to deployment, which remains unrequested.
The generated guide grants no extra authority and does not cancel this explicit
Git endpoint. No pull request, staging cycle, database operation, Render action,
software tests or model calls are required or authorized for this archive.

An archive-only commit message includes `[skip render]`. Keep the isolated
delivery worktree and original dirty experiment worktree; production cleanup
conditions do not apply to a commit-and-push request.

# Goal

The Jev closeout, its discoverability links and evidence are reachable from
`origin/main`, without importing experimental application behavior or unrelated
General-launch changes.

## Product Contract

- Include only `CONCEPTS.md`'s Jev entry, the TypeSafe README pointer, the two
  closeout files, comprehensive findings, ongoing issue record, archived
  experiment plan, this delivery record and the eleven manifest-listed study
  directories. Historical executable material remains evidence, not runtime
  integration; snapshot the out-of-directory experimental scripts/tests and
  existing application diff as inert text inside the original study directory.
- Copy the 2,075 manifest-listed files byte-for-byte. Preserve their original
  hashes and disclose any documentation-only link/whitespace normalization.
- Replace hidden-worktree navigation in the closeout/findings/issue entry points
  with ordinary repository-relative links. The unrelated G5 prototype is a
  historical path reference, not part of this commit.
- Keep the main classifier and all `config.yaml`, `x_monitor/`, `monitor/`,
  `core/`, runtime `scripts/`, `tests/`, UI and deployment files unchanged.
- Secret scan must not print candidate secret values. The repository is public.
  Manually inspect any hit; do not publish real credentials. Recorded source
  posts and provider outputs are analysis evidence, not runtime reference prose.
- Verify every JSON/JSONL file parses, manifest hashes match, critical Markdown
  links resolve, and the staged file list is exactly the intended archive.
  `git diff --check` applies; record existing historical whitespace exceptions
  rather than silently rewriting frozen evidence.
- Recheck `origin/main` before push. If it advances, integrate only that new
  upstream state in this isolated branch; never force-push or reset another
  worktree. Completion requires remote containment of the exact archive commit.

## Baseline and boundaries

- Delivery base: `f4d994f9d30f92e534968c28abcebd910daf4e21`.
- Research base: `1edbc3adaa19b370498ef0fbb026319fc676d397` plus the preserved
  local experiment changes recorded in the closeout manifest.
- Existing tests are waived by the owner's earlier stop instruction. None are
  reported as passing in this documentation delivery. Offline file integrity,
  secret-pattern and link checks do not call models or execute experiment code.
- The old interpretation plan is archived context. This bounded publication
  record does not restart it or create a competing active research plan.

## Local verification

- Exact staged scope: 2,087 files; all under `docs/` except the nine-line Jev
  discovery entry in `CONCEPTS.md`. No runtime paths or unrelated files staged.
- All 2,075 original evidence hashes and four inert snapshot hashes match.
  The four original modified application/test files also retain their hashes.
- All 1,984 original JSON files and 477 JSONL records parse. No experiment
  runner, software test, database query or paid model call was executed.
- The archive/entry-point link scan resolved 467 local Markdown links with no
  missing targets before adding the two historical-plan navigation links;
  those added links point to existing closeout/publication files.
- Common credential-pattern and credential-field scans found no live values.
  The single literal-key match is the `offline-only` test placeholder. These
  are bounded checks, not a claim of exhaustive security certification.
- Edited-document `git diff --cached --check` passes. The full archive check
  exits 2 with 292 historical whitespace notices across 20 files, all inside
  hash-verified source material or the literal patch snapshot. Their bytes are
  intentionally retained; the full archive whitespace check is not a pass.
- The Git endpoint remains unverified until the remote contains the final
  archive commit. Record that observation in the delivery response; do not
  infer it from a local commit or an unrelated deployment.
