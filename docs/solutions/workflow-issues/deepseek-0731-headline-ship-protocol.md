---
title: "Shipping DeepSeek 0731 headlines stalled on protocol, not code"
date: 2026-09-25
category: workflow-issues
module: pushin-weight-v2
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "Shipping an LLM headline change to production through LFG while Ollija owns exact-SHA staging/production"
  - "A plan gate requires zero-critical on unseen LLM outputs (SC2-style critic on a closed case set)"
  - "An agent is iterating prompt or eval versions until a critic reports zero critical findings"
  - "Updating origin/main (or another tracking ref) with git fetch of a remote branch"
  - "Resuming a ce-handoff whose continuation clause is older than the latest Delivery Exception"
symptoms:
  - "Codex looped about 12 hours on unbounded SC2 zero-critical prompt tuning (V40 through V56)"
  - "Owner handed off to Grok because the LFG session would not stop on a practical bar"
  - "LFG-to-deploy collided with Ollija exact-SHA staging/production"
  - "A tracking-ref freshness problem was diagnosed during delivery; source-only fetch behavior depends on remote mapping"
  - "After ship, Celery --concurrency=3 OOM on Render Starter; durable pin is --concurrency=1 on main"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
related_components:
  - ollija
  - background_job
tags:
  - ollija
  - lfg
  - ce-handoff
  - worktrees
  - git-fetch
  - headlines
  - deepseek-0731
  - sc2
---

# Shipping DeepSeek 0731 headlines stalled on protocol, not code

## Context

The DeepSeek V4 Flash 0731 headline candidate shipped because the owner stopped an unbounded evaluation loop, froze critic V56 on a practical lead-sentence bar, then delivered through headline-only exact-SHA staging and a production fast-forward. The hard part was process.

On 2026-09-24 the owner invoked `$compound-engineering:lfg this plan, ollija to production` against the already-complete plan `docs/plans/2026-09-24-060052-feat-headline-0731-architecture-plan.md` (present on `origin/main`; absent from this checkout; `artifact_readiness: implementation-ready`, `delivery_target: production`, `delivery_selected_by_user: true`). Codex stayed inside the plan's SC2 gate: freeze a 24-case pack, score zero-critical, retune the critic/editor, repeat. Saved-case clears (V45, later 13-case) were followed by a new sealed 24-case live trial. V52 through V55 each produced a new critical. V56 started both remaining gates at once. (session history, Codex 0731 LFG session, 2026-09-24 09:55Z–22:17Z)

The owner asked how many LFG iterations had run. The agent answered with gate status, then continued. About twelve hours after LFG start the owner wrote a `ce-handoff` and restarted in Grok with an explicit instruction: the Codex loop would not reach perfection; treat remaining critic nits as whack-a-mole; pick a practical bar for the app as a whole.

Grok froze V56 after a twelve-case lead-sentence review of saved regressions, wrote that into the plan's Delivery Exceptions, committed, then followed Ollija exact-SHA staging and `git push origin <candidate-sha>:refs/heads/main`. As of 2026-09-25 those production commits (`976e84a` Merge origin/main so V56 can fast-forward production; later `09aaa76` pin Celery to one process) are ancestors of `origin/main`. Neither has a GitHub pull request.

## Current interpretation

The historical staging route and V56 acceptance were owner-selected for this release. They are not universal shipping requirements. See [the three-incident synthesis](2026-09-25-203900-authorized-release-blocked-by-inherited-gates.md) for source-verified qualifications and current fixes. Secondary factual errors remain defects unless the owner explicitly accepts them for that release.

## Guidance

### Verdict: agent and plugin together, plus an unbounded plan gate

This was both. The incident-era Compound Engineering shipping endpoint conflicted with this production plan; earlier-session plan intake and stale handoff instructions added friction. The agent treated LFG plus SC2 as a standing order to keep retuning. The plan's SC2 wording made that loop look mandatory.

**Plugin (CE)**

1. At version 3.28.2, LFG routed earlier-session plans through `ce-plan`; it already reused ready plans written in the same session. The correction is to reuse any explicitly identified, sufficient ready plan after a material drift check, not to remove content verification.
2. LFG's shipping tail succeeds only when remaining work is committed, pushed, and in an **open PR URL**. The "project-defined process may own the handoff" exception still requires that PR URL (Compound Engineering LFG shipping-tail rule in the plugin cache). PushinWeight production for this change is exact-SHA staging, then `git push origin <candidate-sha>:refs/heads/main`. Opening a PR, or blocking because no PR exists, is the wrong ship.
3. LFG has bounded CI repair and blocked states. This semantic qualification loop lacked an effective dataset/iteration/spend boundary; that narrower defect must be fixed at the qualification contract.
4. `ce-handoff` snapshots the continuation clause at write time. The V56 handoff (`/tmp/compound-engineering-501/ce-handoff/pushin-weight-v2-aff2eb3769a9/headline-0731-v56-qualification.md`) recorded the owner's earlier "keep working and iterating until success" plus remaining SC1–SC9 (semantic review plus staging/ops gates). Resume from the **latest owner exception in the plan**, not from that earlier clause.

**Agent**

1. Codex treated "iterate until success" as zero-critical on every fresh 24-case freeze. After LFG start it advanced V45→V56 in one session. The iteration-count question was answered with sample sizes, not with a stop. (session history)
2. `git fetch origin refs/heads/main` updates `FETCH_HEAD` and can also update `origin/main` through the normal `remote.origin.fetch` mapping. Without that mapping, the tracking ref can stay stale. Use an explicit destination when a subsequent check depends on that ref; do not treat the source-only command as universally broken.
3. Headline work lived in the canonical headline-0731-architecture worktree (removed after exact-SHA production verification; historical path). The root checkout was often `feat/combined-rare-type-extra-search`. Editing headline files in the root checkout mixes two features. Use `git -C` that worktree while it exists.

**Plan gate**

Plan SC2 (same plan on `origin/main`, lines 320–333) asks three independent reviewers to score eight disjoint 0731 narratives each (24 cases) against a frozen source packet, with a mean of at least 4/5 on five dimensions **and zero critical factual failures** in the final reader-visible result. Repeated fresh sets can reveal new failures. A finite zero-critical acceptance set is valid; repeatedly reopening qualification without an iteration/spend limit is the unbounded loop.

The durable bar, written into the 2026-09-25 V56 freeze exception (plan lines 111–118): the **lead** names the right company and the main fact. Secondary lawyer-level errors are a weekly review pile. Do not add another critic prompt version. Incomplete Cycle 19 fresh generation stays unused.

### Follow the selected delivery route and verify deployed identity

The 2026-09-25 headline-only exception (plan lines 94–109) replaces only the guide's **staging-branch** fast-forward. The shared `staging` branch carried unrelated rare-type commits. Leave it untouched. Disable auto-deploy on staging web and headlines, deploy the exact candidate SHA, verify the reported SHA, restore auto-deploy. If exact-SHA cannot be verified, stop before production.

LFG may be the owner's "keep going" command. It is not permission to skip the Delivery Guide, the exceptions, or `ollija annotate-plan <plan> --check` before Git or deploy mutations. Current explicit owner instructions determine the applicable route. Generated defaults cannot reinstate waived steps; an open-PR endpoint cannot terminate an authorized production request.

Ollija's CLI in this repo is `init` and `annotate-plan` (plus `--check`). There is no complete/clear/status/task/approval/release command. Worktree remove is parent `git`. After exact-SHA production verification, the generated guide wants guarded `git worktree remove` of the canonical linked worktree (no `--force`); keep the feature branch.

### Refresh the tracking ref, then compare

```bash
git fetch origin refs/heads/main:refs/remotes/origin/main
git rev-parse origin/main
git merge-base --is-ancestor origin/main "$CANDIDATE_SHA"
```

The explicit refspec removes dependence on the configured mapping. The incident did not establish that every source-only fetch leaves a stale ref.

### Two different "concurrency" knobs. Only one of them is RAM.

`--concurrency` on the Celery **start command** is OS processes: N prefork copies of Django. RAM grows almost linearly. Render Starter is 512 MB. The production candidate `976e84a` shipped `render.yaml` with `--concurrency=3` and the worker OOM-restarted. The later pin `09aaa76` (ancestor of `origin/main` as of 2026-09-25, `[skip render]`, no PR) is `--concurrency=1`. This checkout already has that pin:

```89:91:render.yaml
    startCommand: >-
      celery -A project worker -l INFO -Q trend-narratives --concurrency=1
      --prefetch-multiplier=1 --without-gossip --without-mingle
```

`per_brand_worker_concurrency` is in-process LLM HTTP overlap inside one process. On `origin/main` as of 2026-09-25 it is `3` (`config.yaml`) with `Field(default=1, ge=1, le=3)` in `x_monitor/config.py`. This checkout hard-pins it to `1`. Do not collapse those two numbers. Raising Celery concurrency on Starter to match in-process overlap is the OOM.

## Why This Matters

An unbounded "zero critical on a fresh 24-case freeze" gate consumes days of prompt edits and paid reviewer calls without converging. The product ships when the lead is company-and-fact-correct; remaining secondary nits are operations.

LFG's incident-era default shape (planning intake, open PR, babysit CI) is a GitHub-PR product. PushinWeight's production path is exact-SHA staging then a fast-forward of `main`. Following LFG literally either blocks a finished plan or opens a PR that is not the release. Following LFG's "through production" vibe without the Delivery Exceptions skips the SHA identity check that keeps rare-type and headline from contaminating each other.

`ce-handoff` is a snapshot. Resuming it after the owner has changed the stop condition restarts the loop the owner just killed.

An actually stale `origin/main` makes a production ancestry comparison unreliable; verify its freshness rather than infer it from fetch syntax alone. Committing on the wrong worktree mixes two features in one SHA.

## When to Apply

- Any headline 0731 / V56 / critic-prompt change, bakeoff, or "one more cycle until SC2 is clean."
- Any LFG / ce-work / ce-plan run against an already-complete Ollija plan (`artifact_readiness: implementation-ready`, `delivery_target: production`).
- Any staging or production deploy of headlines: exact SHA, do not push `staging`, verify reported SHA, then `git push origin <sha>:refs/heads/main`.
- Any session that resumes from `ce-handoff` while a later Delivery Exception has changed the stop condition.
- Any `git fetch origin refs/heads/<branch>` used to decide merge-base, fast-forward, or "what is production."
- Any edit of `render.yaml` `startCommand` or live Render start command for `pushinweight-headlines`.
- Root checkout on a different feature than the worktree that owns the change.

## Examples

### Wrong: treat SC2 as an until-success loop

Codex kept freezing a new 24-case pack, scoring zero-critical, retuning critic/editor text, and repeating. The V56 `ce-handoff` still said iterate until success. That is the loop the owner stopped by restarting in Grok.

### Right: freeze V56 on a lead-sentence bar

Twelve saved V56 regression leads: right company, main fact. Commit the freeze (`0ad93c2` `fix(headlines): freeze 0731 V56 source-owned secondary claims`, ancestor of `origin/main` as of 2026-09-25). Do not add critic v57. Secondary inverted-legal / tool-role nits go to a weekly pile. Incomplete Cycle 19 fresh generation stays unused.

### Wrong: LFG shipping tail as the production path

Stop at an open PR although the request is production, or rewrite an earlier-session ready plan solely to obtain a current-run planning receipt.

### Right: Ollija exact-SHA, then production ref push

1. Work in the canonical headline worktree (or `git -C` it) while it exists.
2. `ollija annotate-plan docs/plans/2026-09-24-060052-feat-headline-0731-architecture-plan.md --check`.
3. Merge refreshed `origin/main` (rare-type already production) so the candidate can fast-forward.
4. Staging: do not push `staging`. Deploy exact candidate SHA to staging web + headlines. Verify reported SHA.
5. Production: `git push origin <candidate-sha>:refs/heads/main`. Verify `pushinweight-web` / `pushinweight-headlines` report that SHA.
6. Then `git worktree remove` the canonical worktree without `--force`. Keep the feature branch.

No PRs for the production candidate or the later RAM pin.

### Mapping-dependent: source-only fetch

```bash
git fetch origin refs/heads/main
git merge-base --is-ancestor origin/main HEAD   # verify remote.origin.fetch maps main before relying on origin/main
```

### Right: update the tracking ref, then compare

```bash
git fetch origin refs/heads/main:refs/remotes/origin/main
git rev-parse origin/main
git merge-base --is-ancestor origin/main "$CANDIDATE_SHA"
```

## Related

- [Bounded Ollija task recovery without agent resurrection](2026-08-17-190429-ollija-task-recovery.md) — historical supervisor recovery; body still describes Ollija-owned commits. Current protocol is plan-only `annotate-plan` plus parent LFG/exact-SHA delivery. Moderate overlap; refresh candidate.
- [Why mockup-06 dropdowns took 8 versions](2026-08-05-115349-mockup-06-dropdown-agent-failure-postmortem.md) — analogous agent loop that stays green on the wrong oracle until a human stops it.
- [Cached bilingual trend narratives](../architecture-patterns/2026-08-12-205000-cached-bilingual-trend-narratives.md) — headline worker architecture already specified concurrency/prefetch=1; this learning adds the Starter OOM when Blueprint/`startCommand` drift to 3.
- GitHub issue [#15](https://github.com/allenwlee/pushin-weight-v2/issues/15) / PR [#17](https://github.com/allenwlee/pushin-weight-v2/pull/17) — Ollija as gatekeeper vs resumable guide; PR 17 made Ollija plan-only. Headline-0731 shipping still had to re-learn that against leftover supervisor docs and LFG's PR tail.
