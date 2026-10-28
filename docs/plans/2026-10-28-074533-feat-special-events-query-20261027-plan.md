---
title: Complete the special-events, Meta and release-routing deployment
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: existing-g3-plan-and-owner-continuation
execution: code
ollija:
  change_id: feat-special-events-query-20261027-2026-10-28-074533
  branch: feat/special-events-query-20261027
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  staging_transport: branch
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/special-events-query-20261027`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/special-events-query-20261027/docs/plans/2026-10-28-074533-feat-special-events-query-20261027-plan.md`
- Change: `feat-special-events-query-20261027-2026-10-28-074533`
- Branch: `feat/special-events-query-20261027`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/special-events-query-20261027/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/special-events-query-20261027/render.yaml`
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
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/special-events-query-20261027` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/special-events-query-20261027` without `--force`.
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
<!-- END OLLIJA DELIVERY GUIDE --># Complete the special-events, Meta and release-routing deployment

## Plain-English Summary

Finish the already implemented bundle through production activation. Meta becomes the visible name while the internal llama key remains. The two special-events queries share the existing credit allowance; ordinary and special-event releases enter the same release-processing path. The X transport uses the name x_client. Preserve the deployed continuous-enrichment and X-list fixes.

Reuse valid prior tests and recorded paid staging evidence. Correct the staging evaluator against the actual discovery counters and explicit bounded coverage, verify the integrated candidate, review with GPT from this session, deploy, apply the bounded Meta changes and observe normal production collection. No worker/slot/budget increase, Giants onboarding, schema change or production scheduler pause is included.

## Goal Capsule

This is the branch-bound release continuation returned by ollija after the original G3 schema plan was closed by its owner. The selected product decisions and W1–W8/SE/R1/routing scope remain in /Users/fuchitalee/development/pushin-weight-v2/.worktrees/refactor/global-shared-vocabulary-20261021/docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md, sections Special-events split and vocabulary and Coordinated homepage backend and X-client rename. Do not reopen or duplicate the wider G3/G2 scope. Existing execution tracker: todos/2026-10-27-172859-coordinated-se-meta-client-work.md.

## Product Contract

Preserve exact assessed SE1/SE2 wording, independent query windows, shared 28,800 daily credits, provider/model limits, literal translation and separate lazy commentary. Retain llama identity and aliases; register verified meta-models publisher and use existing bounded metadata-only catalog import. Keep unapproved zh/ja copy unchanged. Preserve existing production enrichment/key and list-credential behavior, including the prepared logging follow-up. No new tables/columns or migrations.

## Implementation Units

1. Integrate origin/main and the owned reviewed list-visibility follow-up c8595f4b. Resolve only task-owned conflicts.
2. Correct bounded discovery acceptance using actual inserted IDs/counters and explicit truncated coverage; keep ordinary-search transfer requirements and all caps/identity/output checks. Pin a real caller regression before the fix. Reuse saved paid search and persisted cohort with a read-only candidate evaluation; no additional paid search is required by this continuation.
3. Run affected tests against the shared permanent PostgreSQL wrapper. Reuse c458b9bd browser assurance where source/assets/fixtures are unchanged. Run GPT review through this session; external Claude/Grok routes are retired.
4. Commit/push, stage integrated exact candidate and verify environment/runtime plus persisted proof. Promote non-forced to main, observe all affected services, apply bounded Meta data update/catalog, verify normal SE1/SE2 cycle and page/performance behavior.

## Verification Contract

- Regression net exercises real CycleRunner discovery/post-fetch to the acceptance evaluator with fake transports, including truncation and invalid counters/caps/IDs.
- Preserve failed historical acceptance receipt; corrected evaluation is separate proof, never relabel the old result.
- Shared PostgreSQL tests, scoped lint and internal GPT review; distinguish existing baseline failures and unperformed tests.
- Candidate stage runtime SHA/database identity and normal provider routes; no provider calls in the saved-evidence verification.
- Production exact-SHA service observation, bounded Meta update preview/application/readback, SE1/SE2 natural scheduled run and unchanged shared allowance.
- Public page and one-day desktop/mobile performance evidence on the deployed candidate, following original authenticated-staging measurement limitation.

## Definition of Done

All selected code is on remote main and observed deployed; Meta data/publisher changes are verified; normal scheduled collection proves both enabled query identities; release routing is verified from caller/persisted evidence; remaining limitations are explicit. Only remove a clean registered canonical worktree at the verified revision, preserving untracked evidence and branches.

## Delivery Exceptions

Owner on October28: “u were using a deprecated claude route, use gpt from this session. continue to deployment”. Use native GPT; retire all external-Claude/Grok review dependencies. This continues production authorization and authorizes repairing the failed staging checker; it does not waive correctness or authorize another paid search. Original paid/persisted evidence is reusable for unchanged runtime behavior. No other scope or route waiver.
