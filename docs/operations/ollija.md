# Ollija operations

This is PushinWeight's operating guide for the standalone Ollija command. The
command annotates plans; the parent workflow owns all implementation and
delivery actions.

## Install or refresh standalone Ollija

On the authoritative host, install the private-preview checkout as an isolated
user command:

```bash
uv tool install --force /Users/fuchitalee/development/ollija
command -v ollija
uv tool list --show-paths
ollija --help
```

The executable must resolve outside PushinWeight. Confirm the installed
distribution's `direct_url.json` names
`/Users/fuchitalee/development/ollija`.

Run `ollija init` from the primary checkout only when the managed neutral
skill under `~/.agents/skills/ollija` needs installation or refresh. The
command preserves PushinWeight's existing delivery profile and templates.

## Start or resume planning

From the active worktree, run:

```bash
ollija annotate-plan
```

Read the returned `plan_path`. Use that exact path for the whole change,
including CE, goal, Superpowers, Codex, or Claude planning. Enrich the stub in
place, then rerun annotation after the final plan write or review:

```bash
ollija annotate-plan <plan-path>
```

The generated Ollija Delivery Guide is read-only. Add an owner-directed change
under `## Delivery Exceptions`; do not edit between its markers.

## Enable the tracked worktree hook

Once per fresh clone, configure Git from the primary checkout:

```bash
git config core.hooksPath "$(git rev-parse --show-toplevel)/.ollija/hooks"
```

Thereafter a named linked worktree starts or refreshes its shared plan stub.
The hook invokes the installed command through `PATH`, passes the linked
worktree and authoritative root as quoted data, and never blocks Git when
annotation is unavailable, busy, or fails. Primary and detached checkouts do
nothing.

## Set delivery authority once

Ordinary plans remain `delivery_target: on-request` and require a later
explicit delivery request. LFG and goal use the owner’s existing endpoint selection; ask only when it is genuinely absent.
Commit-and-push alone does not select staging or production.
They persist `delivery_target: staging|production` and
`delivery_selected_by_user: true` in the plan, then annotate it. No later
Ollija authorization or browser code exists.

## Deliver from the plan

Before a Git or deployment mutation, the parent workflow reads the selected
target, guide, and Delivery Exceptions, then confirms freshness:

```bash
ollija annotate-plan <plan-path> --check
```

The parent workflow owns implementation, verification, commits,
feature-branch pushes, exact-candidate staging, and production promotion. A
production guide defaults to staged delivery. An explicit owner-selected direct route
reaches production without staging; exact-commit staging does not move the shared branch.
A staging guide stops after its applicable checks. The deployed service revision is the
completion evidence; ancestry alone cannot establish preserved behavior or deployment.

Worktrees intended for delivery belong under
`<authoritative-repo>/.worktrees/<branch>`. Outside worktrees receive
relocation guidance only; annotation never moves or blocks them.

After exact-SHA production verification, follow the generated guide's guarded
`git worktree remove` step as the final filesystem action. Never use
`--force`; retain staging-only, failed, unauthorized, dirty, locked,
noncanonical, or candidate-mismatched worktrees.

## Correct errors

When a guide has a wrong path, environment fact, or instruction, correct the
tracked consumer source in `.ollija/project.yaml`, the delivery template, or
`AGENTS.md`, then rerun annotation. Engine or packaging defects belong in
the standalone Ollija repository.

For shell, SSH, environment, or multi-machine failures, use the repository's
infra/multi-machine skill first. For a material PushinWeight delivery-policy
change, add a concise advisory entry to `docs/ollija/CHANGES.md`.

## Persist routes and opt-outs

Use `--delivery-route direct --delivery-route-selected-by-user` with owner-selected production.
For staging without a branch update, use `--delivery-route staged
--delivery-route-selected-by-user --staging-transport commit`. These are arguments to
`ollija annotate-plan <plan-path>`. Existing plans retain branch-based staged delivery.

An opted-out plan retains only `ollija: {enabled: false, branch: <branch>}`; remove its old
guide. Discovery, normal annotation and `--check` return disabled without rewriting the file
or creating a replacement. Current owner exceptions supersede local defaults, including a
saved continuation. Record them in the existing plan, not another approval ledger.

When installing a tested Ollija branch before it lands on main, install from its authoritative
fuchitalee worktree with `uv tool install --force <ollija-worktree>`, record the source commit,
and run `ollija init` to refresh the managed skill. Do not overwrite unrelated local skill
edits if initialization reports a conflict. Once landed, refresh from the canonical checkout.
