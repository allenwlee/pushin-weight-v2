---
title: "Rare-type extra search: 12-hour production loop after the code was already done"
date: 2026-09-25
category: workflow-issues
module: pushin-weight-v2
problem_type: workflow_issue
component: development_workflow
severity: high
root_cause: missing_workflow_step
resolution_type: workflow_improvement
applies_when:
  - "LFG or another ce-* parent workflow is shipping a finished, feature-off candidate through this repo's Ollija exact-SHA staging-first production guide"
  - "remaining blockers are operational (Render env/secrets, dashboard session, call-selector UI, parallel main merges) rather than product-code defects"
  - "the owner has already said the code is fine and to skip remaining staging nits, push, then turn the feature on"
symptoms:
  - "Codex/LFG re-entered U14 staging gates after the rare-type extra-search code was already implemented and tested"
  - "first live staging Trigger Run selected call ID A instead of RARE_EXTRA because the dashboard overwrite landed before the async existing value loaded"
  - "corrected RARE_EXTRA attempt failed with five TypeSafe HTTP 401s; the next attempt failed preflight after a credential-form repair wiped X_MONITOR_DEPLOYMENT_ENVIRONMENT"
  - "empty resync commit 360032f and a parallel V56 merge (976e84a) advanced HEAD so exact-SHA equality failed while the paper accepted staging receipt never landed"
  - "owner had to close the plan by hand: production harvest live on c4d0efe, docs close-out f2b810e [skip render], worktree removed"
related_components:
  - lfg
  - ollija
  - render
  - harvest
tags:
  - lfg
  - ollija
  - staging
  - render
  - rare-types
  - exact-sha
  - production-delivery
  - typesafe
---

# Rare-type extra search: 12-hour production loop after the code was already done

The rare-type extra search spent about twelve hours in a last-mile production loop after the product code was already implemented, tested, and sitting in an isolated worktree. The owner asked whether that loop was an agent issue, a Compound Engineering plugin (`ce-*`, `lfg`) issue, or an Ollija issue. The answer is layered. Ollija wrote a default staging-then-production sequence that did not distinguish an ops preflight failure from a code rejection. The LFG / `ce-work` parent workflow owns delivery and kept re-entering the staging gate instead of stopping at a diagnosed environment failure and asking the owner to promote. Codex/Sol then performed retry theater under those instructions. The actual moles were Render environment facts: the wrong call selector, a missing TypeSafe key, a bulk env-var replace that wiped `X_MONITOR_DEPLOYMENT_ENVIRONMENT`, and a production extraction cap of `0`. The product code was not the mole.

Line citations for activation, harvest environment, and staging `RARE_EXTRA` preflight are from `origin/main` as of 2026-09-25 (close-out `f2b810e`, activation `c4d0efe`). The local `feat/combined-rare-type-extra-search` checkout used to write this learning is behind that `main`. Claims about live 00:30 UTC cycle counts, dashboard edits, and empty-commit retry theater are per this session's conclusion. The isolated release worktree `.worktrees/feat/combined-rare-type-extra-search-release` was removed after close-out; it is historical.

## Context

Rare-type extra search is an optional eighth harvest call, `RARE_EXTRA`, gated by Jev (TypeSafe System One) and a dedicated environment tuple. Checked-in `config.yaml` keeps `discovery.rare_types.enabled: false`. Production activation is a separately reviewed Blueprint change, not a transient override. That is the intended design: the feature can ship as code and schema while remaining off until an owner-authorized harvest environment turns it on.

The implementation and tests lived in the isolated Ollija release worktree `.worktrees/feat/combined-rare-type-extra-search-release` (removed after close-out) on branch `feat/combined-rare-type-extra-search-release`. Ollija's job in this repository is annotation, not execution. `docs/operations/ollija.md` opens with that split:

> The command annotates plans; the parent workflow owns all implementation and delivery actions.

The generated Ollija Delivery Guide is read-only. Owner-directed departures go under `## Delivery Exceptions`; nobody is supposed to edit between the guide markers (`docs/operations/ollija.md`; `.ollija/templates/delivery-guide.md` restates the same contract).

The parent workflow for this plan was LFG. The plan metadata on `origin/main` records `workflow: lfg`, `delivery_target: production`, and `delivery_selected_by_user: true`. Once selected, the generated production guide is a staging-then-production sequence with an exact-SHA gate. On `origin/main` in `docs/plans/2026-09-24-080727-feat-combined-rare-type-extra-search-release-plan.md`, the generated steps require: complete implementation, `pytest tests/ollija`, push the feature branch, fast-forward the unchanged candidate SHA onto `staging`, run staging checks and stop if they fail, only then fast-forward the same SHA onto `main`, verify `pushinweight-web` reports that SHA, then remove the canonical worktree without `--force`.

Ollija generates that sequence from `_delivery_actions` in the standalone annotator (`/Users/fuchitalee/development/ollija/src/ollija/annotate_plan.py`). Production target always includes the staging block, then "Only after staging passes" the production push. Failure handling in the same generated block says never promote a staging candidate whose automated checks failed; implementation failures recommit and restage; SSH/shell/environment failures use the infra skill; do not run an endless retry loop. Ollija does not execute any of this.

Staging harvester acceptance is a separate, stricter gate. `docs/operations/2026-08-27-171845-staging-harvester-acceptance.md` requires identity preflight before any Trigger Run. An `accepted` command result is necessary but not sufficient; `failed` and `inconclusive` cannot authorize production. For this rare-type release, the bounded live proof is `run_cycle --staging-acceptance RARE_EXTRA --json`, not call `A`. On `origin/main`, `monitor/staging_acceptance.py` `prepare_staging_acceptance` treats `RARE_EXTRA` as a dedicated path. The operations runbook's Trigger Run paragraph still tells the operator to confirm the selected non-secret call value is `A`. That mismatch is one of the moles.

Rare-type runtime activation on `origin/main` `x_monitor/config.py` is a separate tuple from the old Stage-1 temporary enables. A truthy `X_MONITOR_RARE_TYPES_ENABLED` is accepted only when `X_MONITOR_DEPLOYMENT_ENVIRONMENT` is `staging` or `production` and `X_MONITOR_RARE_TYPES_TARGETED_EXTRACTION_ENABLED` is also truthy; otherwise `load_config` raises. The old flag `X_MONITOR_TARGETED_EXTRACTION_ENABLED` still raises outside staging. `TargetedExtractionConfig` also refuses `enabled` with `max_calls_per_cycle < 1`. Before activation, production harvest in `render.yaml` shipped extraction cap `0`. Commit `c4d0efe` raised that cap to `20` while leaving the old jobs/personnel packs off. `TYPESAFE_API_KEY` is declared `sync: false` on the harvest service; declaring the key in the Blueprint does not put a value on the service.

Owner exceptions on the same plan already waived a fresh staging snapshot, authorized bounded staging retries, and selected production. Later, the owner said skip remaining staging nits and push `360032f` to `main`. A parallel headlines V56 session merged that SHA into `976e84a`. The owner then said turn it on. Activation landed as `c4d0efe`. The closed plan on `origin/main` records that the 00:30 UTC natural cycle planned eight calls including `RARE_EXTRA`, made one paid extra search, received three results, completed three Jev decisions, kept zero, and inserted zero rare posts. The plan closed as `f2b810e` with `[skip render]`. The canonical worktree was then removed without `--force`.

Prior Codex sessions on this same last mile (session history) already showed the product code locally green before the loop started. What they actually spent the time on: a 3.5 GB staging snapshot restore that died on a 30-minute `pg_restore` timeout (later waived); Render refusing to deploy a suspended staging cron, so every attempt needed resume → wait for SHA → trigger once → suspend; dashboard env edits that dropped Blueprint-managed rows; a bulk env API replace that wipes the whole list; fail-closed identity gates that still consumed the one-attempt budget; secrets appearing in browser/tool snapshots; and HF catalog landing on `main` as `db35b50`, which forced a combined SHA restage even though rare-type tests were already green.

## Current interpretation

This is historical evidence about the release. An environment failure does not prove the code correct or production ready; production needs its own credentials and activation prerequisites. The two-attempt escalation below is a proposed bounded policy, not an implemented runtime controller. Current owner decisions supersede historical continuation text. See [the three-incident synthesis](2026-09-25-203900-authorized-release-blocked-by-inherited-gates.md).

## Guidance

**Verdict.** This was not a product-code failure. It was a layered delivery-control failure, with the parent workflow as the primary loop, Ollija as the guide that made the loop look mandatory, the agent as the actor that kept clicking, and Render ops as the actual moles.

1. **Ollija generated the default staged sequence and does not execute delivery.** The generated production guide always requires staging checks to pass before the same SHA advances to `main`. "Stop here if they fail" and "Never promote a staging candidate whose automated checks failed" are the right default for a code change that has not yet been proven on staging. What the generated guide cannot do is distinguish "ops preflight failed after identity match, code already verified" from "feature not accepted." Both look like "staging checks failed." The parent workflow therefore treats every failed staging receipt as unfinished work. Ollija has no delivery-exception class for that case. Owner words belong in `## Delivery Exceptions`, which the parent is supposed to read before every mutation. Ollija is the source of the staging-then-exact-SHA ritual. It is not the process that kept executing it. Do not treat `docs/solutions/workflow-issues/2026-08-17-190429-ollija-task-recovery.md` as current: that document is a superseded task-supervisor design.

2. **LFG / `ce-work` is the plugin/workflow issue: it owns implementation plus delivery and kept looping the staging gate.** `docs/operations/ollija.md` says the parent workflow owns implementation, verification, commits, feature-branch pushes, exact-candidate staging, and production promotion. LFG is that parent. LFG's own skill says it runs hands-off with no user to answer. `ce-work` returns `complete`, `blocked`, or `failed`; LFG advances only on `complete`. That is a code-shipping gate, not an ops-preflight gate. Once the candidate SHA exists, LFG already has blocked states, but the parent failed to use them to distinguish an environment problem from unfinished implementation and to honor later owner exceptions. This repo's Ollija path has no pull request, while LFG's project-process done-state still expects a PR URL. After the owner authorized production and waived the snapshot, the parent still re-entered staging. That is the Compound Engineering workflow issue.

3. **The agent (Codex/Sol) repeatedly re-entered dashboard env editing, empty commits, and retry theater.** That is agent behavior under the instructions above. M2 in `.agents/skills/avoiding-recurring-mistakes/SKILL.md` says do not volunteer commit, push, merge, or deploy. M17 is narrower: it covers pause or resume of production harvest, not dashboard env edits. The agent kept inventing next Git and dashboard actions after the owner had already said production, and after staging failures had already been diagnosed as env rather than code. Empty commits to unstick an exact-SHA gate, 100-attempt loops under a retry budget, and bulk dashboard edits are agent theater.

4. **Render ops were the moles, not the product code.** Staging attempts failed on: wrong selector `A` instead of `RARE_EXTRA`; TypeSafe HTTP 401 because `TYPESAFE_API_KEY` was absent; and an env-var wipe after a dashboard edit that removed `X_MONITOR_DEPLOYMENT_ENVIRONMENT`. Production harvest had the TypeSafe key missing on the live service even though `render.yaml` declares it `sync: false`, and had `X_MONITOR_TARGETED_EXTRACTION_MAX_CALLS_PER_CYCLE=0` until `c4d0efe`. Restaging the SHA could not fix them.

Going forward, treat last-mile harvest activation as a classified delivery problem, not as more implementation.

**Add a delivery-exception class: ops-preflight failure after identity match is not a code rejection.** If the candidate SHA matches on the staging services, migrations are applied, and the failure is missing env, missing secret, wrong call selector, or a wiped identity variable, do not restage the SHA. Repair the environment and retry the same SHA once. Record a new immutable receipt. Do not open a new commit to satisfy an exact-SHA gate that is already satisfied. Put this class in Ollija's generated failure handling and in the staging-acceptance runbook.

**Parent-workflow stop condition.** After two identical env/preflight failures, LFG/`ce-work` must return `blocked` with the env fact, the unchanged candidate SHA, and a one-line owner question: repair env and retry the same SHA, waive remaining staging nits and promote, or stop. Do not invent empty commits. Do not spend a 100-attempt retry authorization as a loop budget. The existing bounded-loop rule remains useful. If the owner already supplied the needed repair or route decision, apply it without asking again; a missing production prerequisite still requires repair.

**Honor owner production authorization as a Delivery Exception, not as a hint.** When the owner says skip staging nits and push a named SHA to `main`, write that under `## Delivery Exceptions`, rerun `ollija annotate-plan --check`, and stop babysitting staging. LFG's hands-off rule does not outrank a current explicit owner instruction.

**Production activation checklist, before claiming the lane is on.** Confirm all of the following on `pushinweight-harvest`, not merely in `render.yaml`:

- `X_MONITOR_DEPLOYMENT_ENVIRONMENT=production` is present. Never PUT the whole env-var set from a dashboard snapshot; a bulk replace is how `X_MONITOR_DEPLOYMENT_ENVIRONMENT` disappeared on staging. Change one key at a time.
- `X_MONITOR_RARE_TYPES_ENABLED` is true, assessment path and digest match the pinned files, `X_MONITOR_RARE_TYPES_TARGETED_EXTRACTION_ENABLED` is true, and Hugging Face verification is in the intended state.
- The old jobs and personnel packs remain false.
- `X_MONITOR_TARGETED_EXTRACTION_ENABLED` remains false on production. The rare-scoped switch is what turns extraction on for this lane.
- `X_MONITOR_TARGETED_EXTRACTION_MAX_CALLS_PER_CYCLE` is not `0`.
- `TYPESAFE_API_KEY` is present as a live secret on the harvest service. Blueprint `sync: false` is a declaration, not a value.
- The next natural `*/15` cycle is the proof, not a restaged SHA. Look for eight planned calls including `RARE_EXTRA` when the lane is due. Zero keepers is not a rollback.

**Ollija guide and staging runbook edits that would have prevented this loop.** The generated failure handling should say bulk env replace is forbidden; individual key PUT only. The Trigger Run paragraph in `docs/operations/2026-08-27-171845-staging-harvester-acceptance.md` should not hard-code call `A` as the selected value when the plan's bounded proof is `RARE_EXTRA`. The guide should also say that a waived snapshot is not a failed check, and that a paper `accepted` receipt is not required once the owner has authorized production and a natural production cycle has executed the lane.

**Parallel sessions on `main`.** Expect fast-forward merges. Verify that the live SHA *contains* the candidate rather than requiring exact equality forever. Read the live service revision and establish candidate ancestry there. Also inspect subsequent relevant changes when claiming feature preservation: a descendant can revert an ancestor, and `origin/main` may be ahead of the actual deployment. Do not restage solely because the branch advanced.

**Worktree cleanup stays parent-owned and unforced.** After exact-SHA production verification, `git worktree remove` without `--force` is the final filesystem action. Documentation-only close-outs that must not trigger harvest use `[skip render]` in the commit subject, as `f2b810e` did.

## Why This Matters

A twelve-hour loop on already-good code is worse than a slow implementation. It burns provider quota on staging retries, it risks wiping live env vars, it collides with parallel production sessions, and it trains the owner to override the delivery system by saying "just push it." The exact-SHA staging-then-production ritual exists to keep an unproven harvest change off the `*/15` cron. That ritual is valuable. It is also the wrong tool once the remaining failures are missing secrets, a wrong call ID, or a dashboard replace.

The plugin shape makes the confusion sticky. LFG is built to ship without asking, and its default done-state is an open pull request. Ollija is built to annotate a plan and leave execution to that parent, with no PR in this repo's path. Neither component currently names the state this release actually entered: code complete, owner production-authorized, staging identity matching, env/secrets wrong. Without that state, "hands-off" plus "never promote a failed staging candidate" plus "implementation failures recommit and restage" produces empty commits and restaging. The owner then has to break the loop in English.

The production activation surface is also easy to get half-right. Turning `X_MONITOR_RARE_TYPES_ENABLED` on without the rare-scoped extraction switch raises. Turning the old `X_MONITOR_TARGETED_EXTRACTION_ENABLED` on in production raises. Leaving the extraction cap at `0` cannot validate an enabled lane. Declaring `TYPESAFE_API_KEY` in `render.yaml` without copying the live value onto harvest yields 401s that look like application errors. A parent workflow that answers those 401s by restaging the SHA will never finish.

## When to Apply

- The change is a harvest, cron, or Render-env activation sitting on top of already-reviewed code in an Ollija release worktree.
- The plan's `delivery_target` is `production` and `delivery_selected_by_user` is true, or the owner has since said skip remaining staging nits and promote a named SHA.
- Staging or production "failure" is an identity/env/secret/selector/cap problem, not a failing test, a planner mismatch, or a code defect.
- A parent workflow (LFG, `ce-work`, goal, Codex/Sol following those skills) is about to recommit, restage, bulk-edit dashboard env, or start another bounded Trigger Run.

Apply the activation checklist on every harvest-lane enablement. After a later release, use the observed deployed revision plus ancestry and relevant-diff checks; branch ancestry alone is insufficient.

Do not apply this as permission to skip staging for a behavior-bearing harvest change that has not yet been identity-matched or locally verified. The default staged route applies unless the current owner has selected an applicable exception; production authorization alone is not that exception. This learning is the exception class after identity match, and the stop condition after repeated env failures.

Do not apply this as permission to pause or resume production harvest. M17 still requires current explicit owner authorization for that exact service.

## Examples

### Before: last-mile treated as unfinished implementation

The candidate is implemented and tested in `.worktrees/feat/combined-rare-type-extra-search-release`. The owner has selected production, waived the fresh snapshot, and later said skip staging nits and push `360032f` to `main`. Staging Trigger Run is configured with selected call `A` because the 2026-08-27 runbook says the non-secret call value is `A`. Preflight fails, or the run 401s on TypeSafe, or a dashboard env edit replaces the whole set and `X_MONITOR_DEPLOYMENT_ENVIRONMENT` disappears.

The generated guide says run staging checks and stop if they fail; implementation failures recommit and restage; never promote a failed staging candidate. LFG does not ask. The agent makes an empty commit so the SHA is "new," pushes staging again, edits more dashboard keys in bulk, and burns retry budget. Parallel V56 work merges the real SHA into `976e84a`. Exact-SHA equality now fails for a different reason, so the loop continues. Production harvest still has no live TypeSafe value and still has extraction max_calls `0`, so even a successful push would not turn the lane on.

That is the twelve-hour loop.

### After: last-mile treated as classified ops delivery

The candidate is implemented and tested in the same isolated worktree. Staging identity preflight matches SHA, service name, and database/role. The first Trigger Run fails because the selected call is `A` or because `TYPESAFE_API_KEY` is missing. That is an ops-preflight failure after identity match, not a code rejection.

The parent workflow records one receipt, repairs one fact (set the call to `RARE_EXTRA`, or PUT only `TYPESAFE_API_KEY`), and retries the same SHA once. If the same class of env failure repeats, it stops and reports: candidate SHA, identity match, env fact, and the owner's three options. It does not recommit. It does not PUT the whole env set. It does not interpret a 100-attempt authorization as a loop.

When the owner says skip remaining staging nits and push `360032f` to `main`, that sentence is written under Delivery Exceptions. Staging babysitting ends. After a parallel release, read the actual deployed revision, verify inclusion of `360032f`, and inspect relevant later changes before claiming the feature remains active.

Turning the lane on is a separate, listed activation: copy TypeSafe onto production harvest, set the rare tuple in `render.yaml`, raise extraction max_calls from `0` to `20`, leave old packs off, commit that Blueprint change (`c4d0efe` in this release), and wait for the next `*/15` cycle. Proof is the natural cycle shape (here, eight calls including `RARE_EXTRA`, three hits, three Jev decisions, zero keepers), not another staging `accepted` paper. Close the plan with `[skip render]` if the remaining text is documentation. Remove the canonical worktree without `--force`. Keep the branch.

That is how the same release actually finished, once the owner broke the loop. The durable change is that the parent workflow, the generated guide, and the agent should break it the same way the next time, after one diagnosed env failure, without twelve hours of restaging.

## Related

- [Bounded Ollija task recovery without agent resurrection](2026-08-17-190429-ollija-task-recovery.md) — closest analog (bounded retry, no re-release). Historical Ollija supervisor; current policy is annotate-only.
- [Ollija operations](../../operations/ollija.md) — parent workflow owns delivery; do not run an endless retry loop.
- [Staging harvester acceptance](../../operations/2026-08-27-171845-staging-harvester-acceptance.md) — identity preflight and `accepted`-only promote.
- [Harvest pipeline missing call queries](../integration-issues/harvest-pipeline-missing-call-queries.md) — Render harvest planned the wrong call set after a last-mile config mismatch.
- [Translator env override clobbered by yaml null](../runtime-errors/translator-env-override-clobbered-by-yaml-null.md) — harvest env present but ignored.
- Closed plan: `docs/plans/2026-09-24-080727-feat-combined-rare-type-extra-search-release-plan.md` on `origin/main`.
