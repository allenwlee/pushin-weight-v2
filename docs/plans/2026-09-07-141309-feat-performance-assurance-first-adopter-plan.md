---
title: feat/performance-assurance-first-adopter plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-performance-assurance-first-adopter-2026-09-07-141309
  branch: feat/performance-assurance-first-adopter
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/performance-assurance-first-adopter`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/performance-assurance-first-adopter/docs/plans/2026-09-07-141309-feat-performance-assurance-first-adopter-plan.md`
- Change: `feat-performance-assurance-first-adopter-2026-09-07-141309`
- Branch: `feat/performance-assurance-first-adopter`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/performance-assurance-first-adopter/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/performance-assurance-first-adopter/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the Render deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the Render deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/performance-assurance-first-adopter` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/performance-assurance-first-adopter` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

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

None.

# Goal

Adopt the deterministic browser assurance contract from Bridgewright PR #9 at merged commit `d0a5279ff1dcfab76f285b75a048b6611ee3c2d2` in PushinWeight (merged from the reviewed first-adopter head `611105319bed1aaf563b28e0a61efbe817314f3b`), then deliver the first-adopter proof through staging and production without changing unrelated product behavior. The umbrella contract is the Bridgewright integrated performance assurance plan (`docs/plans/2026-09-07-151016-feat-integrated-performance-assurance-plan.md`) represented by [Bridgewright PR #9](https://github.com/allenwlee/bridgewright/pull/9); this plan is its PushinWeight U5-U8 adoption and delivery slice.

## Product Contract

### U5. Pin the reviewed Bridgewright contract and establish the baseline

- Pin Bridgewright's exact merged commit `d0a5279ff1dcfab76f285b75a048b6611ee3c2d2` (the reviewed feature head was `611105319bed1aaf563b28e0a61efbe817314f3b`), build identity, schema digest, skill digest, and `performance-assurance/v1` profile in the adopter declaration and project manifest. Do not use a moving branch, short SHA, or local package fallback.
- Capture the current `origin/main` desktop and mobile baselines before product edits. Include the existing semantics, accessibility behavior, Taiwan (`TW`) handling, geometry, and the current expensive-state behavior.
- Run the first adopter declaration against the baseline and retain the expected red proof for each intentional missing obligation. The red proof must fail for the missing saved-state migration, missing exact sprite/cache contract, missing served-revision header, and any missing desktop/mobile evidence; it must not be replaced with a synthetic clean result.
- Keep baseline evidence separate from candidate evidence and identify both by their exact Git revisions.

### U6. Drop saved expensive state and preserve the visual/semantic contract

- Migrate only safe user preferences to the v2 shape. Drop previously saved expensive query/pulse payloads during migration, never restore or re-request them from persisted state, and keep future persistence bounded to those safe preferences. Preserve existing semantics, keyboard and screen-reader behavior, Taiwan disclosure/labeling, and all non-target geometry.
- Add the external exact 215-flag sprite from the approved source asset. Preserve the exact symbol inventory, geometry, aspect ratio, and Taiwan symbol. Load it through the production asset path with an immutable cache policy and verify the cache-control/reuse evidence in both desktop and mobile runs.
- Keep target-project data inert and keep the change scoped to the declared product surface. Do not weaken accessibility, locale, or geometry regressions to satisfy performance budgets.

### U7. Bind the deployed candidate and execute the complete assurance matrix

- Emit `X-Bridgewright-Revision` dynamically from the exact PushinWeight candidate revision being measured (the Render deployment commit in hosted environments, with an explicit candidate revision for local proof) on the measured main document and revision-probe responses. Every environment repetition must prove that exact full SHA before and after measurement; do not hard-code the Bridgewright dependency revision into this application header.
- Exercise desktop and mobile profiles against the same candidate with Lighthouse and Web Vitals as separate engine-qualified evidence. Require complete LCP, CLS, and INP observations, bounded state/action/network/cache evidence, and no owned browser or Node survivors.
- Require state/cache correctness and exact candidate identity to block. Keep first-slice Web Vitals thresholds advisory only where the Bridgewright contract declares them advisory; missing metrics, missing revision proof, bad cache proof, or unsafe egress remain invalid.
- Run owner-authenticated target checks on populated staging; staging is not the public full Bridgewright performance run because its authentication boundary cannot be exercised as an unauthenticated external target. Run the complete public Bridgewright performance proof on production. For both environments, verify the remote ref, Render deployment revision, served header, and sealed result identify the unchanged candidate SHA wherever the target check is available.

### U8. Production delivery and handoff

- Stop before promotion on any failed, skipped, missing, unknown, or unavailable required obligation, semantic/accessibility/Taiwan/geometry regression, cache/state mismatch, or candidate-SHA mismatch.
- Promote only the unchanged candidate that passes the local baseline/candidate comparison, staging checks, and production checks. Record the exact candidate SHA, Bridgewright result paths/digests, deployment identities, and migration state.
- Preserve the generated Ollija delivery guide and `Delivery Exceptions: None`. The parent workflow owns commits, pushes, staging/production ref updates, Render verification, and final canonical worktree cleanup; Bridgewright and Ollija remain assessment/guidance only.

## Acceptance and verification

1. `ollija annotate-plan <this exact plan path>` is rerun after this plan enrichment, followed by `ollija annotate-plan <this exact plan path> --check`.
2. The baseline red proof fails for the intentionally absent U6/U7 obligations and is retained before implementation.
3. Focused Django, accessibility, locale, geometry, sprite inventory, immutable-cache, and saved-state-v2 tests pass with no unrelated surface changes.
4. The public Bridgewright CLI validates the declaration and seals clean desktop/mobile results for the exact candidate with separate Lighthouse/Web Vitals LCP/CLS/INP evidence on production.
5. Staging owner-authenticated checks and the production public full run report the exact unchanged candidate SHA and served-revision header; production must also report a clean sealed assurance result before completion.

## Stop conditions

- Stop before product edits if the baseline cannot be captured or the expected red proof is not reproducible.
- Stop before staging if saved-state migration, exact 215-flag sprite/cache evidence, semantics, accessibility, Taiwan behavior, geometry, or desktop/mobile assurance fails.
- Stop before production if staging or any exact-SHA deployment/result/header verification fails. Retain the worktree and report the evidence; do not force-remove or bypass the delivery guide.
