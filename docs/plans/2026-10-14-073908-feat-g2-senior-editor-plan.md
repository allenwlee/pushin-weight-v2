---
title: G2 production senior editor review
artifact_contract: ce-unified-plan/v1
artifact_readiness: execution-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-g2-senior-editor-2026-10-14-073908
  branch: feat/g2-senior-editor
  workflow: senior-editor-integration
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-senior-editor`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-senior-editor/docs/plans/2026-10-14-073908-feat-g2-senior-editor-plan.md`
- Change: `feat-g2-senior-editor-2026-10-14-073908`
- Branch: `feat/g2-senior-editor`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-senior-editor/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-senior-editor/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `senior-editor-integration`
- Delivery target: `production`
- Owner selection recorded: `true`
- Delivery route: `staged`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-senior-editor` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-senior-editor` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

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

None.

# Goal

## Plain-English Summary

Every new Chatter and Pulse draft will receive a separate senior editor review
against its original evidence before publication. The review grades nine areas
from A+ to F and explains every section, finding and overall grade in one or two
sentences. Only a publish verdict with no unresolved material defect advances.
Held, failed or revision-needed drafts preserve their original text and review.

Keep the locked writers, voice prompts, existing editions and dollar ceilings.
Use GPT6.1 Sol/high for the separate reviewer, with no research tools or outside
story information. The split beatwriter/copyeditor experiment remains separate.
Verify real request/accounting/publication paths with fake providers, then deploy
the same tested revision through staging to production and inspect active code.

## Authorization and scope

Owner: “first integrate sr-edread to production”; subsequent instruction requires
1–2 sentence explanations for each grade. This selects production delivery before
the previously authorized USD3 OpenAI packet trial. Preserve its saved packet and
all original G2 dirt. Native-reader certification remains unavailable.

This clean current-main worktree is the bounded production successor to the retained
round-two trial plan, not a replacement for its test history. No unrelated collection,
source import, prompt/model promotion, UI change or old-edition regeneration.

## Product Contract

The senior-ed-read skill is the literal review rubric. Code supplies immutable draft,
packet and skill hashes, cutoff, locale, voice, model identity and review timestamp.
The model supplies nine section grades/reasons/findings, overall grade/reason,
publish/revise/hold verdict, required changes, uncertainties and strengths. Findings
must quote actual draft text and refer only to supplied source IDs or explicit gaps.
Unknown/malformed/failed reviews fail closed. No rewrite or retry loop is added.

## Storage decision

Inspected core/models.py, migrations0065/0076/0078/0079, provider persistence,
canonical call import and edition readers. Reuse EditorialCall/OriginalContentCall
request/response JSON for all attempts; EditorialAssessment.outcome for per-draft
reviews including nonpublication; EditorialEdition.evidence for accepted receipts,
already copied to OriginalContent.provenance. Zero tables or fields added/retired.

## Implementation units

- U1: versioned review schema/request/validation from canonical skill, explanations
  for all grades, code-owned identity. Tests: nine sections, grade enum, exact
  excerpts, packet-only sources, publish contradictions, request/tool boundary.
- U2: production route GPT6.1/high, mandatory review between validate_copy and
  publish_edition, bound receipt rechecked inside publication transaction. Reuse
  normal budget/idempotency/fences; increase call allowance6→13 for four added
  reviews, preserving USD5/day and USD2/assessment. Test real transport→ledger→
  mirrored publication, review holds/errors/budget exhaustion/duplicate assessment,
  all three languages and Pulse, current writer request hashes unchanged.
- U3: simplify/review/check; update editorial reference; same-SHA staged delivery,
  runtime activation/negative-gate checks, production service identity/health.

## Verification contract / regression net

Use local PostgreSQL with a task-specific disposable test database and persistent
basetemp on fuchitalee; no SQLite claims. Observe focused missing-review rejection
before implementation, then run editorial/original-content regressions, Ollija and
migration-drift checks, plus hosted G2 workflow. No outside story retrieval. Retain
test and delivery receipts outside the clean release worktree. No paid smoke call
is necessary: live runtime builds/validates exact review requests and rejects a
missing/mismatched approval without writes or network. Existing budget exhaustion
must remain a hold; do not reconcile or raise old production ledgers.

## Definition of Done

Mandatory semantic review, durable grades/explanations, unchanged writer requests,
meaningful tests passing; exact candidate observed on staged then production
web/headlines/harvest with effective review route and unchanged money limits.
Resume saved OpenAI experiment only after this endpoint; retain original G2.
