---
name: ollija
description: Add deterministic, agent-agnostic delivery guidance to a PushinWeight plan. Use before creating or selecting a plan, and again after the plan is complete or reviewed.
---

# Ollija plan annotator

Ollija is a plan guide, not a release controller. Its only public command is:

```bash
./bin/ollija annotate-plan [optional-plan-path]
```

It resolves one shared Markdown plan and writes or refreshes its generated
Ollija Delivery Guide. It does not start agents, create release state, ask for
approvals, move or remove worktrees, commit, push, deploy, or retry in the
background.

## Planning contract

Before selecting or creating a plan, every instruction-aware planning workflow
(Codex, Claude, CE, Superpowers, goal, or another planner) must run:

```bash
./bin/ollija annotate-plan
```

Use the exact `plan_path` returned by that command. Enrich that same file; do
not create a parallel plan. After the final plan write or document review, run:

```bash
./bin/ollija annotate-plan <returned-plan-path>
```

The generated guide is read-only. Put owner-directed departures in the plan's
`## Delivery Exceptions` section, outside the guide markers.

## Delivery intent

- For LFG and goal, ask the owner once, before implementation, whether to stop
  after staging or continue through production. Persist the choice in the
  plan's Ollija metadata as `delivery_target: staging|production` and
  `delivery_selected_by_user: true`, then annotate the same plan.
- For ordinary planning, use `delivery_target: on-request`. Ask nothing and do
  not treat planning as permission to commit, push, stage, or release.
- Never infer production authority from a branch, conversation, or prior run.

## Worktree guidance

The Ollija release worktree area is:

`/Users/fuchitalee/development/pushin-weight-v2/.worktrees`

If annotation says the active worktree is outside that area, make relocation
the first plan action and rerun annotation after the move. This is guidance
only: do not prompt, move, reject, or block the worktree.

## Production worktree cleanup

For a user-selected production target, let the generated guide direct the
parent workflow to clean up only after exact-SHA production verification. The
guide emits an executable removal command only for the resolved canonical
linked worktree.

Before running `git worktree remove`, require that worktree to remain
registered, clean, unlocked, and at the verified candidate SHA. Run from the
authoritative repository root without `--force`, preserve the local and remote
feature branches, and make removal the final filesystem action. Retain every
staging-only, failed, unauthorized, dirty, locked, noncanonical, or
candidate-mismatched worktree. Ollija does not remove the worktree itself; the
parent workflow owns the guarded mutation and reports afterward from the
authoritative root.

## Before Git or deployment mutations

The parent implementation or delivery workflow must read the plan's selected
delivery target, generated guide, and `Delivery Exceptions`. Refresh stale
guidance before Git or deployment mutations:

```bash
./bin/ollija annotate-plan <plan-path> --check
```

Stop and resolve any conflict between the requested work and that plan
guidance. The parent workflow—not Ollija—owns implementation, checks, commits,
staging, promotion, and failure diagnosis. For infrastructure or multi-machine
failures, use the repository's infra/multi-machine skill first.

Do not advertise or use retired status, task, approval, browser-verification,
release, receipt, database-refresh, supervisor, or persistent-runtime commands.
