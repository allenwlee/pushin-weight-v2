# Ollija consumer guide

PushinWeight consumes the standalone Ollija command. Ollija keeps deterministic
delivery guidance inside the branch's shared Markdown plan; it does not
implement, approve, commit, push, deploy, or supervise the change.

The engine and neutral agent skill are owned by the standalone checkout at
`/Users/fuchitalee/development/ollija`. This repository owns only its
project-specific `.ollija/` delivery contract, hook, guide template, and
ignored local state.

## Install or refresh the command

The standalone repository is a private preview, so its supported installation
is an isolated user tool built from the authoritative local checkout:

```bash
uv tool install --force /Users/fuchitalee/development/ollija
command -v ollija
uv tool list --show-paths
ollija --help
```

The executable must resolve outside this repository. The installed
distribution's `direct_url.json` must name the standalone checkout before an
embedded-copy migration or standalone upgrade is accepted.

Run `ollija init` from the primary PushinWeight checkout when the managed
neutral skill under `~/.agents/skills/ollija` needs to be installed or
refreshed. Initialization recognizes the existing version-one delivery
profile, leaves `.ollija/project.yaml` and its delivery template unchanged,
and updates only unmodified managed skill files.

## Select and annotate one plan

Before selecting or creating a plan, run:

```bash
ollija annotate-plan
```

Read the exact `plan_path` from the structured result. Use that file for the
whole change; do not create a parallel plan for the same branch.

After the final plan write or document review, refresh the same file:

```bash
ollija annotate-plan <plan-path>
```

Before any Git or deployment mutation, verify that the generated guide is
current without changing the plan:

```bash
ollija annotate-plan <plan-path> --check
```

The generated block lies between the Ollija delivery-guide markers. Do not edit
it directly. Put owner-directed departures in `## Delivery Exceptions`,
outside those markers.

## Project-owned delivery policy

PushinWeight retains these consumer assets:

- `.ollija/project.yaml` — authoritative host, repository, branches,
  environments, worktree area, test commands, and failure routes;
- `.ollija/templates/delivery-guide.md` — PushinWeight's delivery wording;
- `.ollija/hooks/post-checkout` — the nonblocking linked-worktree
  integration; and
- ignored `.ollija/state/` — local consumer runtime state, when present.

The repository does not carry an Ollija Python package, wrapper, or local
Ollija skill. Both humans and agents call the same installed executable.

## Linked-worktree hook

Enable the tracked hook once per fresh clone from the primary checkout:

```bash
git config core.hooksPath "$(git rev-parse --show-toplevel)/.ollija/hooks"
```

The hook skips primary and detached checkouts. In a named linked worktree, it
invokes `ollija annotate-plan` through `PATH`, passes quoted Git-derived
paths, and never forwards caller stdin. A missing, busy, or failing command
does not block Git; the hook prints an installation or recovery message.

## Delivery choices

Ordinary planning uses `delivery_target: on-request`. LFG and goal ask the
owner once whether to stop after staging or continue through production, then
persist `delivery_selected_by_user: true` and the selected target.

The parent workflow reads the selected target, generated guide, and Delivery
Exceptions before acting. It owns tests, commits, feature-branch pushes,
exact-SHA staging, production promotion, verification, and guarded final
worktree cleanup.

## Change ownership

This directory's [CHANGES.md](CHANGES.md) preserves PushinWeight's historical
Ollija decisions and records the final consumer migration. Future engine,
packaging, initialization, and neutral-skill changes belong in the standalone
repository's changelog. PushinWeight records later entries here only when its
consumer delivery policy changes.
