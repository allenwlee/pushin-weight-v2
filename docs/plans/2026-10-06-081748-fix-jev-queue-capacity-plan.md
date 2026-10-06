---
title: fix/jev-queue-capacity plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-jev-queue-capacity-2026-10-06-081748
  branch: fix/jev-queue-capacity
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/jev-queue-capacity`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/jev-queue-capacity/docs/plans/2026-10-06-081748-fix-jev-queue-capacity-plan.md`
- Change: `fix-jev-queue-capacity-2026-10-06-081748`
- Branch: `fix/jev-queue-capacity`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/jev-queue-capacity/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/jev-queue-capacity/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/jev-queue-capacity` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/jev-queue-capacity` without `--force`.
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

# Jev request capacity and nonblocking rare-search decisions

## Plain-English Summary

Rare-search hits currently wait behind repeatedly rejected requests because a local 32,000-byte limit is mistaken for model capacity. Remove that cutoff and let pinned Jev enforce its documented 64k total-token and 32k state-plus-longest-question limits. Keep full saved text, make invalid input visibly review-needed, and prioritize fresh results while reserving bounded capacity for older/retry work.

The owner selected LFG through production and a separate worktree. Search wording, editorial selection, G2 work, existing spend limits, concurrency and production cron state remain outside this fix. Completion requires regression evidence, applicable staging verification, exact production revision and natural-cycle database/log proof.

## Diagnosis and scope

- Base: d6ed01c3, clean new branch except this hook-created plan.
- TOUCH: x_monitor/jev_decisions.py; x_monitor/config.py; config.yaml; core/rare_type_search.py; monitor/cycle.py; existing Jev/rare-ingestion/regression tests.
- PRESERVE: A/B/C and rare query terms, all classification questions, $0.02/cycle and $0.50/day, 20 normal / 5 staging decisions, two in-flight calls, 60-second allocation, full source text, G2 files/environment.
- ASK FIRST: cron pause, unrelated paid calls, occupied shared staging replacement.
- Evidence: encode_request_payload rejects >32k bytes before any durable claim. CycleRunner slices 20 oldest hits before gate invocation. Nineteen oversized old rows monopolize selection; Beam hit5713 remains unattempted.
- Competing hypothesis (provider latency) rejected by successful ~0.4–0.5-second calls in production.
- Provider contract rechecked 2026-10-06: https://docs.typesafe.ai/models. No documented local tokenizer; capacity enforcement stays with provider. Spend reservation uses the lesser of conservative byte upper bound and published 64k total maximum, not a byte/token equality claim.

## Execution and regression net

1. Reproduce original failure via real CycleRunner drain and real Jev gate with mocked HTTP; 19 long old requests plus fresh Beam.
2. Remove byte rejection/config, preserve full request. Distinguish definitive provider input rejection from retryable transport/server failure; store review-needed immediately for input rejection.
3. Query eligible decisions before limiting; exclude retries not due/active claims/expired payloads. Allocate fresh work promptly and older/retry work separately under existing total budget.
4. Pin transient failure next-cycle retry and successful fresh admission despite old failures. Pin full >32KB request reaching HTTP, terminal provider rejection, request spending reservation, deadlines/concurrency, unchanged A/B/C.
5. Run focused PostgreSQL suite, simplify/review, required browser applicability check, Ollija checks. Isolated local database test_pw_jev_queue_20261006; no shared G2 test resources.
6. Read latest-N production health before delivery and preserve same cohort for 30-minute follow-up. Deliver through available staging per generated guide, production deploy exact SHA, inspect natural cycles and Beam/backlog durable progress.
7. Record verified evidence and residuals. Cleanup only guarded canonical worktree at verified candidate SHA, last filesystem action.

## Progress

- 2026-10-06: isolated branch/worktree and diagnosis confirmed; no product edits yet.

- 2026-10-06 08:28 UTC: regression first run was red (5 cases). Fixed full payload admission, terminal input failures, due-aware fresh/backlog scheduling, and immediate CycleRunner drain. 206 tests passed (79 PostgreSQL required cases; zero skips/errors). Full CycleRunner→gate→HTTP regression and next-slot transient retry covered. Existing 20/5 request caps, concurrency2, time60s, and spend limits remain.
- Fresh allocation: normal15 fresh +5 older/retry when both are full; idle shares borrowed. Due retries take precedence within the older share. Therefore not all20 fresh arrivals can be attempted immediately when backlog exists, by design under the unchanged cap.
- Initial latest20 pre-change health: 0 complete /13 pending /7 unhealthy; missing commentary and one missing language predate the fix. Exact IDs retained in /tmp/jev-queue-health-before.json for one follow-up after30min. This is not a passed health gate.
- Staging branch bacbb433 contains unrelated G2 changes and is occupied by its live replay. No staging mutations. Release candidate will be completed before requesting owner route exception.
