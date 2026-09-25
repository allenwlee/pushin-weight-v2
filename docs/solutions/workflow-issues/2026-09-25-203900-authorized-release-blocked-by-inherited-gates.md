---
title: "An authorized UI release was blocked by inherited staging gates"
date: 2026-09-25
category: workflow-issues
module: pushin-weight-v2
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "A verified change has production authorization but a shared staging branch contains an independent release"
  - "An owner changes or removes a delivery requirement during execution"
  - "Combining project instructions, Compound Engineering skills, Ollija guidance, and environment checks into one release"
tags:
  - "ollija"
  - "staging"
  - "production-delivery"
  - "instruction-precedence"
  - "verification"
  - "shared-environments"
  - "compound-engineering"
  - "release-policy"
---

# An authorized UI release was blocked by inherited staging gates

## Context

The feed UI follow-up shipped as [PR #47](https://github.com/allenwlee/pushin-weight-v2/pull/47) after the owner removed Ollija from its plan and then explicitly dropped the staging and remaining release requirements. The code did not need another repair to unblock production. The agent needed to change its delivery route.

The immediate incident is solved: Render recorded the UI candidate live. At capture time, the tooling changes below were proposals. The owner subsequently authorized implementation; the [propagation plan](../../plans/2026-09-25-122924-fix-release-guidance-propagation-plan.md) records the implemented changes, verification, and distribution. This document captures one solved delivery problem and compares its causes with two earlier incidents; it does not claim three controlled experiments or a model-wide failure rate.

Evidence was checked on 2026-09-25 against this conversation, GitHub PR state, Render deployment records, the UI worktree, the standalone Ollija source, installed Compound Engineering 3.28.2, the two supplied incident reports, and a bounded prior-session probe. The root checkout used to write this document is behind production and contains the two supplied reports as untracked files. Application source citations below refer to the released UI tree, not an assumption that this checkout is current. The original feed plan is `docs/plans/2026-09-25-041204-feat-feed-processing-indicator-followup-plan.md`, available in PR #47 and its retained feature worktree.

Source roots: Ollija paths beginning `src/ollija/` are relative to `/Users/fuchitalee/development/ollija` (inspected revision `c3e973c`). Compound Engineering paths beginning `skills/` are relative to `/Users/fuchitalee/.codex/plugins/cache/compound-engineering-plugin/compound-engineering/3.28.2`. They are external source citations, not files missing from PushinWeight.

## Guidance

### 1. What this UI incident establishes on its own

The requested change consolidated pending work into one subdued spinning armillary, localized its hover, hid pending/context-missing classification labels, and retained specific language codes. Focused tests and browser checks passed. The full UI assurance evidence records 4,466 passed obligations against the product-source revision. This is evidence for the covered behavior, not a claim that every possible defect was excluded.

The owner had authorized production. The generated guide nevertheless required the unchanged candidate to extend both `staging` and `main`. At that point `staging` contained [PR #46](https://github.com/allenwlee/pushin-weight-v2/pull/46), the independent translation/commentary reliability change. The UI candidate could extend `main`, but could not extend `staging` without including that other release. GitHub reported PR #47 mergeable.

That was a conflict with the selected delivery policy. It did not establish a code dependency on PR #46 or a general requirement to release PRs in numerical order. Declining to force-push staging was correct. Presenting the occupied branch as the only possible release route was the mistake.

| Event, UTC on 2026-09-25 | Evidence and interpretation |
| --- | --- |
| Product verification completed | The retained assurance evidence has 4,466 results, all `passed`, bound to product source `5383560`. The release also included later documentation and evidence-pin commits. |
| Owner removed Ollija from this plan | The agent removed its metadata and generated guide, but wrote a new manual checklist that still required staging first. The removed policy survived in newly authored prose. |
| 08:48:14 | The agent directly deployed the UI candidate to staging web: `dep-dar3ajfavr4c73fjso70`. This avoided the branch ancestry rule but still used the occupied staging environment. |
| During that deployment | Read-only database checks showed an active staging refresh and a migration lock waiter. The restore advanced through tables. There was no evidence of a stalled restore or a new UI test failure. |
| 09:01:52 | The agent cancelled its own waiting staging deployment. It had consumed **13 minutes 38 seconds** without becoming live. PR #46's refresh was preserved. |
| 09:02:36 | The UI candidate advanced `main`; GitHub recorded PR #47 merged. Render began production deployment `dep-dar3hb0473hc73cp5gcg`. |
| 09:03:57 | Render recorded the production deployment complete on `e327ed7`, about **81 seconds** after it started. This is the verified resolution. |
| 09:05:30 | The subsequent authorized enrichment release `b77474a` became live and included the UI candidate. The earlier UI deployment is now `deactivated`, which does not mean it failed to ship. |

The source of the branch rule is precise: standalone Ollija's `src/ollija/annotate_plan.py:151`, `_delivery_actions()`, constructs a staging block at lines 176–184 and unconditionally includes it for production at lines 188–198. It requires a fast-forward onto the shared staging branch. The local `.ollija/templates/delivery-guide.md:29` inserts those actions, and `AGENTS.md` instructs agents to read/check the resulting guide before mutations. Calling the annotator “guidance only” does not make its imperative output harmless when agents are required to follow it.

Ollija's check itself was quick. The earlier “why is this taking so long?” answer correctly distinguished the running UI gate from the annotator's runtime, but missed the larger question: Ollija supplied the route that later blocked delivery. Runtime latency and policy causation are different explanations.

The second delay had a real environmental cause. `scripts/render_migrate.py:58` waits up to 900 seconds for the cluster lock; `scripts/database_lock.py:168` implements that lock on the cluster's administration database. It was protecting a live database refresh. Removing that protection would have been the wrong fix. Choosing an already-authorized route that did not use the busy staging database resolved this UI release.

#### A check can pass while proving a different thing

The candidate UI gate requires a performance run: `.claude/skills/fix-ui/SKILL.md:56` and `tests/ui_assurance/gate.py:77`. Its checked-in performance declaration points to production: `tests/fixtures/performance_assurance/declaration.json:9`. The wrapper explicitly permits distinct product and performance revisions, with a regression test named `test_candidate_gate_allows_distinct_product_and_performance_revisions` in `tests/test_ui_assurance_gate.py:24`.

In this incident the UI evidence covered the new product source, while Lighthouse/Web Vitals measured the **previous production revision**. The performance result was a valid production baseline. It did not establish candidate performance. The agent disclosed that distinction in the PR, but still spent release time satisfying a mandatory candidate gate with a measurement of old code. The evidence boundary needs to be explicit in both the tool result and the rule deciding whether it blocks shipping.

#### The agent's part in the failure

- It took too long to distinguish a policy conflict from a technical inability to deploy.
- It stopped with an open PR even though the active goal was production.
- After the owner removed Ollija, it recreated staging-first as a manual requirement and continued waiting on an unrelated operation.
- It treated status questions as opportunities to repeat the blocker rather than promptly revising the route within the owner's stated scope.
- It added avoidable command setup work: an unqualified `pytest`, symlink paths rejected by the performance runtime, and Render SSH's interactive-mode requirement. These were secondary delays, not the underlying reason staging was required.

The owner's first production request did not automatically waive every test or staging default. The later explicit removals did change those requirements. The failure was not respecting that change promptly. Once requirements were waived, the truthful completion claim was that Render had deployed the revision; staging behavior and the final live hover checks were not retrospectively proven.

### 2. What the three incidents establish together

The other inputs are [DeepSeek 0731 headline shipping](deepseek-0731-headline-ship-protocol.md) and [rare-type extra-search delivery](rare-type-extra-search-production-delivery-loop.md). Their approximately twelve-hour durations and portions of their operational narratives are attributed to those reports and their session histories, not independently re-timed here. A retained prior Codex session corroborates the rare-type sequence of successful local checks, staging selector/credential failures, and repeated release re-entry. An unrelated HF session was excluded from the synthesis.

| Incident | What became the obstacle | What the agent kept doing | What actually changed the outcome |
| --- | --- | --- | --- |
| Feed UI, PR #47 | Shared staging ancestry, then a database refresh lock | Requiring staging and carrying it into a replacement checklist | Owner removed that route; the tested change deployed directly to production |
| Headline 0731 | Repeated fresh evaluation sets, strict critic findings, conflicting shipping instructions | Retuning and reopening qualification instead of reaching a bounded decision | Owner selected a practical acceptance bar, froze the candidate, and used an explicit deployment route |
| Rare-type extra search | Wrong call selector, provider authorization, missing/wiped environment values, moving release identity | Revisiting staging and changing release commits to address environmental failures | Owner changed the delivery requirements; production configuration and activation were then checked against the actual runtime |

**The common mechanism is accumulation of obligations without reconciliation.** A plan, a skill, a generated guide, a runbook, a handoff, and the agent's own checklist each add conditions. The agent treats their combined set as mandatory even when a newer instruction changes the scope, an environment makes one route unavailable, or evidence already satisfies the relevant check. A tool does not need a background process to control execution: generated instructions are enough.

The pattern also has four separable dimensions that should not be collapsed into “blocked”:

1. **Authority:** what the owner authorized, waived, or revoked for this change.
2. **Product evidence:** which behavior was tested on which source and dependency set.
3. **Environment readiness:** whether a chosen database, credential, service, or staging slot is usable.
4. **Delivery observation:** which revision a service actually deployed and whether the intended feature is active.

An occupied staging branch changes environment/route readiness. It does not revoke production authority. A provider 401 can still prevent a feature from working even when its code tests pass. A merge into `main` is not proof of a completed Render deploy. A candidate's presence in history is not proof that a later commit did not revert it.

There is also a scope distinction between the examples. Headline evaluation and rare-type harvesting involved behavior, cost, activation, and operational risks beyond a glyph change. The shared lesson is to make requirements applicable and bounded—not to declare all staging checks or all semantic failures dispensable. Three related incidents under one project's instructions cannot establish that one model or all of Compound Engineering is incapable of shipping.

### Precise culprits and changes proposed at capture time

The following table preserves the recommendations made during capture. Capture itself changed no shared dotfiles, plugin package, or Ollija code; the subsequent implementation is recorded in the linked propagation plan.

| Priority | Current source and defect | Proposed edit | Regression that proves the improvement |
| --- | --- | --- | --- |
| P0 | Ollija `src/ollija/annotate_plan.py:176–198` hardcodes staging before production and ties staging to branch ancestry | Represent the selected route separately from the destination; render either staged or direct production actions. Within staged delivery, allow branch-based or exact-commit deployment. Keep ordinary production pushes non-forced. | Independent PRs A and B share a base; staging has A; B has production authority and an explicit direct route. Generated actions for B neither require A nor rewrite staging. |
| P0 | Ollija `PlanMetadata` / `parse_plan_metadata()` have destination/selection fields but no plan opt-out or route. `render_annotated_plan()` preserves an exceptions heading without interpreting its policy effect. | Add a plan opt-out checked before required managed metadata. An opted-out plan is left untouched by annotation/check and by discovery hooks. Record owner-selected routes structurally while keeping explanatory prose. | Opt-out leaves a plan byte-identical; no guide is reinserted or parallel stub created. An explicit direct route never renders “only after staging passes.” |
| P0 | Repo `AGENTS.md` “Plans and delivery”, `.ollija/templates/delivery-guide.md:33`, and installed Ollija skill instructions can be read as absolute gates | State that current owner instructions govern this plan's route and scope. A removed requirement cannot return through another checklist, handoff, or automatic annotation. Keep independent safety constraints outside that waiver. | Replay “remove Ollija from this plan”, then “drop staging”: next authorized action is production delivery, with no staging mutation or renewed permission request. |
| P0 | Agent execution recreates waived requirements despite higher-priority instructions | Before resuming, summarize the effective endpoint, route, remaining checks, and latest owner changes in the existing plan. This is a small state summary, not a new gate or approval form. | A later instruction overrides the older checklist; completed checks remain complete unless a relevant input changed. |
| P1 | Compound Engineering 3.28.2 `skills/lfg/references/shipping.md`, steps 9–10, requires an open PR even for a project-defined shipping process; it also says single-PR merge authorization has no pipeline carrier and must be returned to the user | Make the project's authorized endpoint the completion condition and preserve the owner's merge authorization through child workflows. A PR request ends at a PR; a production request ends at the documented deployment observation. Use a maintained project adapter or upstream change, not an edit to the plugin cache. | An authorized single-PR release proceeds through merge and deployment; a completed production release does not open another PR merely to satisfy the tail. |
| P1 | LFG `skills/lfg/references/intake.md:14` routes plans from earlier sessions through `ce-plan`; handoffs can carry obsolete continuation instructions | Reuse an explicitly identified implementation-ready plan after a bounded drift check; reconcile current owner instructions before executing a saved continuation. Preserve the existing plan path. | An existing ready plan is neither duplicated nor rewritten just to obtain a this-run planning receipt; a later waiver survives resume. |
| P1 | Project `fix-ui` skill and `tests/ui_assurance/gate.py` require performance work even when its target is old production | Label baseline and candidate performance separately. Only require candidate measurement when the change's risk justifies it, and require matching code/assets for that claim. Reuse valid evidence for documentation-only changes. | A previous-production performance result cannot be reported as candidate performance; changing only plan prose does not rerun the product suite. |
| P1 | `docs/deploy/render.md:78` retains release-specific same-cycle requirements in a general runbook; the rare-type report identifies a runbook selector fixed to `A` | Give each requirement an applicability condition. Select the planned call kind from the current contract. Separate code deployment, migrations, paid acceptance, and activation. | A UI release is not routed through a paid harvest test; `RARE_EXTRA` acceptance does not inherit the old `A` selector. |
| P1 | `.claude/skills/avoiding-recurring-mistakes/SKILL.md:60` says to end every turn with the literal answer; `.agents/skills/` contains another copy | Narrow M2 to unsolicited scope expansion. An in-task status question does not cancel an already-authorized deployment. Update both maintained copies through their existing synchronization convention. | Answer “what is blocking it?” briefly and continue the authorized task; do not turn each clarification into a fresh release request. |
| P1 | Shared instruction files lack a concise cross-skill rule for retaining valid authorization and retiring waived steps | Add the reusable paragraph below outside generated content in `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`; keep a canonical maintained source. Put application-specific route rules in the repo. | The same replay produces the same scope in both Codex and Claude; installation/sync does not restore old wording. |
| P2 | Canonical `~/infra/utilities/claude-code/allen-speak.md:13` requires proactive web research for professional-practice explanations, copied into host instructions | Narrow it to external, changeable claims and recommendations. Explain a locally evidenced blocker first; browse only to establish a capability that matters to the decision. | “Where did this rule come from?” is answered from the source line without generic release-method research. |

The web-research rule explains a secondary detour in this conversation. Checking Render's exact-commit capability was relevant; presenting the dependency conclusion promptly would have prevented the owner from wondering why deployment had turned into research.

#### Proposed shared instruction paragraph

```text
During an active task, retain the user's existing authorization and apply
their latest scope changes immediately. Removing a tool, route, or check
removes its dependent steps from this task; do not recreate them in another
checklist or ask for the same authorization again. A status question does
not cancel the task. Distinguish a product defect, an environment problem,
and a local workflow default. Continue through the shortest authorized
route, and report exactly what was verified or waived. Local workflow
exceptions do not override platform constraints or authorize unrelated work.
```

This paragraph clarifies existing owner-priority instructions. It does not license unrequested production changes, secret exposure, force pushes, unrelated PR inclusion, or termination of another release's database work.

Replace M2's blanket end-of-turn rule in both maintained project skill copies with:

```text
Stay within the requested task. Do not volunteer unrelated commits, releases,
or production changes. When the user has already authorized delivery, retain
that authorization across status questions and continue the necessary work.
Stop or narrow the task when the user directs it, or when a concrete blocker
requires information or authority the session does not provide.
```

Replace Allen Speak's unconditional research paragraph at its canonical source, then refresh the managed copies, with:

```text
Ground explanations in the evidence relevant to the question. For a local
rule or blocker, identify its exact source and explain its effect first.
Verify external, changeable claims and professional recommendations against
current authoritative sources, and cite those sources. Keep research scoped
to facts that can change the answer or the next authorized action.
```

Existing higher-priority browsing requirements still apply. These wording changes target unnecessary detours and premature stops, not source verification itself.

#### Minimal Ollija design, not another release controller

Schema proposed during capture, subsequently implemented by the linked propagation plan:

```yaml
ollija:
  enabled: true
  change_id: existing-change-id
  branch: existing-feature-branch
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
```

For staged delivery, select `delivery_route: staged` and `staging_transport: branch|commit`. Preserve existing behavior for existing metadata unless the owner has selected a different route. `enabled: false` means this plan is not managed; the annotation command and `.ollija/hooks/post-checkout` must respect that without generating a replacement plan. Validate contradictory choices rather than interpreting “production” alone as a staging waiver.

Implementation belongs in Ollija's `src/ollija/annotate_plan.py`, `src/ollija/config.py`, `src/ollija/cli.py`, and `src/ollija/assets/agent-skills/ollija/SKILL.md`, with rendering/discovery tests. The installed `~/.agents/skills/ollija/SKILL.md` is a generated distribution target; editing only that copy leaves the defect in its source. Refresh the installation after implementation. Ollija should remain an annotator: do not add deployment execution, a persistent supervisor, another approval database, or a scheduler to solve an instruction-selection bug.

The editable exceptions text should explain a structured selection, not silently contradict a generated “must stage” paragraph. A waived check has status `waived`, not `passed`. No-op reannotation must not turn a waiver into a new release commit.

#### Bound the work that can grow without limit

For semantic model qualification, freeze the dataset, rubric, candidate, and spend/iteration limits before the run. A concrete starting policy is one baseline, at most two remediation rounds, and one reserved confirmation set, with a separately chosen monetary cap. This is a proposed policy, not a budget granted by this document. Exhausting the budget produces a decision with the remaining defects; it does not automatically pass the candidate or trigger another fresh search for perfection.

For an environmental failure, retry only after changing or verifying the fact that caused it. A missing credential does not justify a new source commit. A broad paid-call authorization is a spending ceiling, not an obligation to consume every attempt. Repeated identical failures should be escalated as the same diagnosed issue, while work covered by an existing owner decision continues. Runtime credentials, correct selectors, and activation caps remain real functional requirements for any route that uses them.

For shared staging, inspect the actual service and database occupancy before starting a deployment. PR order is not resource ownership. Exact-commit deployment can decouple staging from branch ancestry, but it still consumes that service and database. Render also documents auto-deploy interactions for exact-commit deployments; the CLI/API do not disable auto-deploy automatically. A later branch push can replace the chosen build. [Render deployment documentation](https://render.com/docs/deploys#deploying-a-specific-commit).

### Corrections needed before reusing the two earlier reports as policy

1. **The Git fetch claim is too broad.** The headline report says `git fetch origin refs/heads/main` updates only `FETCH_HEAD`. With the normal `remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*`, Git uses that mapping to update `origin/main` too. A local reproduction with Git 2.50.1 confirmed it; removing the mapping reproduced a stale tracking ref. An explicit destination remains a good deterministic command, but the source-only form is not universally broken. [Git's configured remote-tracking behavior](https://git-scm.com/docs/git-fetch#_configured_remote_tracking_branches).

   ```bash
   git fetch origin refs/heads/main:refs/remotes/origin/main
   git merge-base --is-ancestor origin/main "$CANDIDATE_SHA"
   git push origin "$CANDIDATE_SHA":refs/heads/main
   ```

   The final push is still non-forced and rejects a concurrent incompatible update. These commands illustrate the authorized production step, not permission to execute it during this documentation task.

2. **Ancestry is insufficient as a replacement for deployed identity.** Read the live service revision, establish that it includes the candidate, and inspect subsequent changes affecting the feature when claiming its behavior remains present. A descendant can revert an ancestor. Checking only `origin/main` also misses an older, failed, or still-building Render deployment.

3. **LFG does have bounded and blocked states.** Its current shipping reference limits CI repair rounds and propagates child blockers. The narrower defect is an inappropriate endpoint and weak reconciliation of the particular plan/owner/evidence state—not a universal absence of stop conditions. Its current intake also reuses ready plans from the same session; earlier-session plans still take the planning route. Do not generalize that every existing plan is rejected.

4. **Zero-critical evaluation is not inherently impossible.** Repeatedly changing the candidate and opening fresh samples without a stopping budget is the demonstrated failure. A finite zero-critical acceptance set can be useful. The headline owner's acceptance of specific secondary issues does not make them universally harmless.

5. **Environment failure is not automatically safe to waive.** It changes the diagnosis and the required repair. A production feature needing the same missing key will still fail. Distinguish staging-only inconvenience from a runtime prerequisite shared with production.

6. **“Ollija's sequence is correct” needs a scope.** It is a reasonable selected route for a staged release. It is not an immutable prerequisite after a valid owner exception, and it cannot serialize independent releases through an occupied branch without coordination.

These are refresh recommendations for the supplied reports. Their original narratives have been preserved in this capture.

## Why This Matters

The expensive failure is not merely the number of checks. It is that the workflow keeps optimizing for its own completion protocol after the owner's outcome has changed. More warnings and more checklists can make that worse: their interaction creates a stronger gate than any author intended. The observed response is an owner ordering all checks dropped, which also discards useful safeguards.

A better release workflow has one selected endpoint, an explicit applicable route, reusable evidence with a known scope, and finite investigation budgets. Requirements should state the harm they prevent and the condition that makes them relevant. Changes to authority retire dependent work immediately. This preserves the valuable parts—non-forced Git updates, protected databases, truthful deployment identity, credential discipline—without making an unrelated staging release the prerequisite for every UI change.

## When to Apply

Use this incident when an agent reports that a locally verified, production-authorized change “cannot ship” because of a local workflow default or a shared environment, or when it continues a removed requirement under another name. Diagnose actual product failures separately. A default does not disappear merely because it is inconvenient; the recorded owner instruction or applicable project route must justify the change.

## Examples

**Observed failure:** owner removes Ollija → agent removes generated text → agent writes “manually deploy to staging first” → occupied database blocks the same release again.

**Observed resolution:** owner directs removal of staging/remaining gates → agent cancels its own waiting deployment → preserves unrelated staging work → pushes the authorized candidate without force → reports Render's actual live revision, with unperformed checks left unclaimed.

**Future regression:** run that interaction against the changed dotfiles and Ollija renderer using disposable repositories and a fake deploy adapter. Assert zero staging mutations after the override, zero duplicate authorization questions, no repeated tests for unchanged inputs, and no “deployed” report before a live deployment observation. Also test the inverse: without production authority or a route exception, the system must not invent one.

## Related documentation and maintenance

- [DeepSeek 0731 headline ship protocol](deepseek-0731-headline-ship-protocol.md) — distinct evaluation and shipping incident; fetch/endpoint claims need the qualifications above.
- [Rare-type extra-search production delivery](rare-type-extra-search-production-delivery-loop.md) — distinct environment/activation incident; ancestry and exception language need qualification.
- [Ollija operations](../../operations/ollija.md) — current consumer instructions still describe the default staging route. Proposed route/opt-out implementation must update this and the project instructions together.
- [Ollija gatekeeper issue #15](https://github.com/allenwlee/pushin-weight-v2/issues/15) — earlier recognition of the same architectural tension. Removing execution from Ollija did not remove control embedded in its generated text.
- [Historical Ollija task recovery](2026-08-17-190429-ollija-task-recovery.md) — a superseded supervisor design; do not revive its runtime to fix this issue.

Documentation status: incident and production outcome verified; cross-incident conclusions distinguish source checks from attributed history. Tooling and dotfile implementation now has its own linked propagation record above. The suggested semantic-evaluation monetary cap still requires a task-specific choice. Discoverability is already supplied by `AGENTS.md`'s solutions and vocabulary pointers. No additional mandatory reading gate is needed.
