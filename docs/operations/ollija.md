# Ollija operations

This is the current operating guide for Ollija. The only Ollija command is
`./bin/ollija annotate-plan`; all implementation and delivery actions remain
with the parent workflow selected by the owner.

## Start or resume planning

From the active worktree, run:

```bash
./bin/ollija annotate-plan
```

Read the returned `plan_path`. Use that exact path for the whole change,
including any CE, goal, Superpowers, Codex, or Claude planning work. Enrich the
stub in place, then rerun annotation after the final plan write or review.

```bash
./bin/ollija annotate-plan <plan-path>
```

The generated Ollija Delivery Guide is read-only. Add an owner-directed change
under `## Delivery Exceptions`; do not edit between its markers.

## Set delivery authority once

Ordinary plans remain `delivery_target: on-request` and require a later
explicit delivery request. LFG and goal ask the owner once before
implementation whether to stop at staging or continue through production. They
persist `delivery_target: staging|production` and
`delivery_selected_by_user: true` in the plan, then annotate it. No later
Ollija authorization or browser code exists.

## Deliver from the plan

Before a Git or deployment mutation, the parent workflow reads the selected
target, guide, and Delivery Exceptions, then confirms freshness:

```bash
./bin/ollija annotate-plan <plan-path> --check
```

The parent workflow owns implementation, verification, commits, feature-branch
pushes, exact-candidate staging, and any production promotion. A production
guide requires the unchanged candidate SHA to pass staging before that same SHA
is advanced to `main`. A staging guide stops after staging checks.

Worktrees intended for delivery belong under
`<authoritative-repo>/.worktrees/<branch>`. Outside worktrees receive
relocation guidance only; annotation never moves or blocks them.

## Correct errors

When the guide has a wrong path, environment fact, or instruction, correct the
tracked source (`.ollija/project.yaml`, the delivery template, or tracked agent
instructions) and rerun annotation. For shell, SSH, environment, or
multi-machine failures, use the repository's infra/multi-machine skill first.
For material Ollija behavior changes, add a concise advisory entry to
`docs/ollija/CHANGES.md`.
