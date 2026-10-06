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
  delivery_route: direct
  delivery_route_selected_by_user: true
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
- Delivery route: `direct`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
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

2026-10-06: owner explicitly replied “deploy” to the direct-production recommendation. Use direct production; preserve G2 staging branch, services, and database. No cron pause or manual harvest run authorized. Existing external-review unavailability and unrelated production health defects remain disclosed.

# Jev request capacity and nonblocking rare-search decisions

## Plain-English Summary

Rare-search hits currently wait behind repeatedly rejected requests because a local 32,000-byte limit is mistaken for model capacity. Remove that cutoff and let pinned Jev enforce its documented 64k total-token and 32k state-plus-longest-question limits. Keep full saved text, make invalid input visibly review-needed, and prioritize fresh results while reserving bounded capacity for older/retry work.

The owner selected LFG through production and a separate worktree. Search wording, editorial selection, G2 work, existing spend limits, concurrency and production cron state remain outside this fix. Completion requires regression evidence, owner-selected direct delivery, exact production revision and natural-cycle database/log proof.

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
6. Read latest-N production health before delivery and preserve same cohort for 30-minute follow-up. Deliver directly to production per owner-selected generated guide, verify exact SHA, inspect natural cycles and Beam/backlog durable progress.
7. Record verified evidence and residuals. Cleanup only guarded canonical worktree at verified candidate SHA, last filesystem action.

## Progress

- 2026-10-06: isolated branch/worktree and diagnosis confirmed; no product edits yet.

- 2026-10-06 08:28 UTC: regression first run was red (5 cases). Fixed full payload admission, terminal input failures, due-aware fresh/backlog scheduling, and immediate CycleRunner drain. 206 tests passed (79 PostgreSQL required cases; zero skips/errors). Full CycleRunner→gate→HTTP regression and next-slot transient retry covered. Existing 20/5 request caps, concurrency2, time60s, and spend limits remain.
- Fresh allocation: normal15 fresh +5 older/retry when both are full; idle shares borrowed. Due retries take precedence within the older share. Therefore not all20 fresh arrivals can be attempted immediately when backlog exists, by design under the unchanged cap.
- Initial latest20 pre-change health: 0 complete /13 pending /7 unhealthy; missing commentary and one missing language predate the fix. Exact IDs retained in /tmp/jev-queue-health-before.json for one follow-up after30min. This is not a passed health gate.
- Staging branch bacbb433 contains unrelated G2 changes and is occupied by its live replay. No staging mutations. Release candidate will be completed before requesting owner route exception.

## Review and release evidence

- ce-debug fixed return: cb609ac1, base d6ed01c3, no unrelated preexisting changes. No issue of record.
- ce-simplify-code: three persona passes; reused retry-delay constant and model enums, selected IDs without loading payloads twice. 27 affected tests passed after simplification.
- ce-code-review: full review run `20261006-173044-4998ffcb`, receipt `/tmp/compound-engineering-501/ce-code-review/20261006-173044-4998ffcb/review.json`. Seven local lenses completed sequentially under the harness thread cap. No independent agreement is claimed across reused persona contexts.
- External review did not pass: Claude returned402 before producing a review; one permitted Grok replacement timed out after600seconds with no usable review. No further attempts. This is a coverage limit, not passed verification.
- One confirmed P2: preserve terminal decision reuse for older duplicate search hits. Two PostgreSQL reproductions confirmed the failure and unchanged funding when directly reused. The same two cases were added to the existing Jev test file and failed before fixing eligibility; terminal decisions are now eligible for the existing no-send reuse path. The original review retains confidence75 as required by its validation contract; this repair follows the owner's explicit fix authority and independently reproduced red tests, not invented reviewer consensus.
- Added the advisory CLAIMED lease/retry-boundary regression: active lease and expired-but-not-due claim do not displace fresh work; exactly15-minute-old expired claim reaches the real gate.
- Optional cap1 policy remains unchanged: when configured below deployed normal20/staging5, the reserved older share can use the sole slot. No deployment uses cap1; changing that policy was outside this release.
- Project lint reports1797 pre-existing findings. Base/current changed-file counts match exactly: cycle40, config3, Jev1, others0. No new changed-line findings; no configured typecheck. Diff whitespace checks pass.
- ce-test-browser mode:pipeline applicability: no changed routes, views, templates, styles, or browser behavior; no browser session/server was needed. Existing ingestion test checks feed inclusion. Browser execution skipped as worker-only scope, not reported passed.
- ce-compound documentation skipped: diagnosis, regression tests, and this plan carry the reusable reasoning.
- Read-only Render08:33UTC: production web+harvest both live d6ed01c3, running; staging web live f9276520(G1R2+G2 integration), autodeployoff; staging harvest suspended on76bf81db. Staging ref bacbb433 is unrelated and cannot be safely advanced from this candidate by fast-forward. No environment setting/service state changed.

## Immutable production health cohort (before this deployment)

Initial observation completed2026-10-06T08:22:23Z:0complete/13pending/7unhealthy. Exact-ID follow-up after30minutes:14complete/0pending/6unhealthy. Both regression_gate and acceptance_gate remain failed, not waived or passed. Language15/20; English and Chinese commentary19/20 each; non-zh-Hans Chinese translations13/13. All6 remaining rows report translation/classification succeeded despite missing fields. These are pre-existing production findings; this branch has not been deployed.

Ordered IDs: 2107381820945797549, 2107382228242104789, 2107382472312783262, 2107382715058192664, 2107381078885306618, 2107381223051931769, 2107383071255265550, 2107383261756301508, 2107382886920028642, 2107382932671541252, 2107382945400951071, 2107383057271476427, 2107383120588861754, 2107383197994815676, 2107383262167630279, 2107383766733762800, 2107383786329497630, 2107383875647451358, 2107383925521645648, 2107384123610317193

Remaining unhealthy rows:
- 2107382228242104789: missing_lang_detected
- 2107382945400951071: missing_lang_detected
- 2107383262167630279: missing_lang_detected
- 2107383766733762800: missing_lang_detected
- 2107383786329497630: missing_commentary_en, missing_commentary_zh_cn
- 2107383925521645648: missing_lang_detected

## Completion and residuals

Owner selected direct production after reviewing candidate5ed8fd2. Staging remains untouched; production authorization and route are settled. Existing production health failures remain disclosed and unresolved in this bounded Jev task.

Production code and natural-cycle behavior are verified below. Beam reached Jev but remains review-needed under the unchanged gate policy. No cron pause occurred. Final documentation-only revision must be observed live before guarded canonical worktree cleanup; code/test/runtime evidence is reused because executable files are unchanged.

- 2026-10-06 09:03 UTC final validation: 209 tests passed in130.24seconds, including82 required PostgreSQL cases with zero skips/errors. This includes the two red-before-fix shared-terminal-decision regressions and the claim-lease/retry-boundary test. Evidence covers final code after simplification and review fixes.

## Production verification — October 6

- Direct fast-forward production push: `01dbc492f469496128feec0af0acf3a49f919307`, with code unchanged from the209-test candidate. Web deployment `dep-db2c4ibncjis73cfjnug` became live09:43:26UTC; harvest `dep-db2c4ijncjis73cfjpg0` became live09:42:33; headlines `dep-db2c4ibncjis73cfjoe0` became live09:42:57. All reported the exact candidate. No staging mutation, Blueprint application, cron pause, schedule change, or manual harvest.
- Natural09:45 scheduled run: `20261006T094535_0000-854adf4f`; summary hash `267a65861f4ce1b87eed53bd773f9b9fa15861603bb83285fc354bc5dea01791`, emitted09:50:37UTC. Exact candidate SHA reported in the summary. All eight planned calls ran,50 normal inserts plus one rare-kept post; database observation found51 rows in the09:45–10:00 fetched window.
- Eleven fresh hits6120–6130 fetched09:45:46.864631 reached their first Jev send in0.227399–2.562408seconds. Nine older hits that had been blocked by the byte cutoff also completed; provider input usage ranged up to14,796 actual tokens. Twenty attempts settled, zero errors/in-flight calls, $0.005474196 accounted against the unchanged$0.02 slot cap. Prior09:30 slot had one attempt. Decisions:13junk,6review-needed,1kept. No natural retry failure occurred; next-eligible-slot retry proof remains the PostgreSQL regression evidence, not an induced production failure.
- Kept post `2107403489844326715` persisted09:45:52.000217, first visible09:45:52.030374, translation/classification succeeded and classified_at09:50:10.544041. Two affiliation records/evidence attachments were produced. Full same-cycle completion is not instantaneous: this example took about264seconds to classification.
- Overall harvest status remains `degraded`: one classifier batch failure,53 enrichment rows pending (3current/50carryover), one quarantined row. Jev errors were zero. These broader enrichment findings are disclosed, not relabeled healthy or repaired by this branch.
- Read-only09:55 observation: cron remained unsuspended on `*/15 * * * *`, last successful run09:50:42; daily Jev accounting$0.009559242/$0.50, zero outstanding reservations. Saved Beam replay dry-run found hit5713, zero provider calls/writes. The09:45 slot had used20/20 attempts; replay waits for the next real scheduler startup rather than opening the shared60-second deadline early.
- Local raw evidence: `/tmp/jev-natural-0945.json`, `/tmp/jev-natural-0945-outcomes.json`, `/tmp/jev-natural-0945-summary.json`, `/tmp/jev-natural-0945-post-proof.json`. These retain exact IDs/timing and separate model decisions from transport errors.

- Beam recovery environment correction: the10:01:40 committed replay on web selected no hit and made no provider call because web lacks harvest's service-scoped `TYPESAFE_API_KEY`. The initial dry-run did not test that prerequisite; this omission cost an additional slot wait. The10:00 natural harvester independently completed20 attempts at$0.006271272. The cron service does not support SSH, including ephemeral mode; no instance was created. A temporary interactive SSH process on the deployed web revision received the existing harvest Jev and DeepInfra keys through echo-disabled stdin, with no secret output, file, or persistent service environment update. Real Jev, translator, classifier and relevancy/targeted factory preflights succeeded before scheduling the saved-hit replay for actual10:15 command startup. No caps or deadlines were changed.

- Beam replay ran after actual scheduled command startup10:15:36.471, triggered10:15:38.448. Saved hit5713 reached Jev10:15:41.414912 and settled10:15:41.852311: decision5010, attempt5000, one successful request,430ms provider latency,1,936 input/276 output tokens,$0.000081312 accounted. Zero TwitterAPI/Hugging Face requests and zero enrichment calls. The shared10:15 slot settled20 total attempts (replay plus natural work), $0.001875468, no in-flight calls.
- Beam's result is **review_needed**, not a transport failure or unattempted hit. Scores: AI-related0.98, model-release0.75, source-announcement0.75. Existing yes threshold0.80 leaves model-release in the uncertainty band; derived_types is empty. No Post, classification, or visibility was created. The queue/capacity repair is verified; changing this gate decision or guaranteeing Chatter/Pulse inclusion is outside the unchanged editorial scope. Evidence: `/tmp/jev-beam-replay-result.json`, `/tmp/jev-beam-final-proof.json`, `/tmp/jev-beam-decision.json`.
- Remaining backlog at09:50 snapshot:1,159 decision-pending,1,440 review-needed,3,035 junk,496 kept. Further scheduled cycles drain under the unchanged bounds; this release does not claim the whole backlog was processed or all review-needed decisions accepted.
- Final receipt is documentation-only. Reuse209-test/82-PostgreSQL evidence and exact01dbc492 natural-cycle proof; verify final documentation SHA on production web/harvest/headlines, append shared coordination OFF, and remove only the clean registered canonical worktree without force. Preserve feature branches.
