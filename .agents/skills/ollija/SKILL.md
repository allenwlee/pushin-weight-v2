---
name: ollija
description: Coach and control the repo-specific PushinWeight task, staging, and beta-release workflow. Use when the owner asks what is next, starts or stops bounded agent work, inspects a task, refreshes review data, approves staging, releases, verifies production, or recovers a failed Ollija transition.
---

# Ollija

Ollija is the PushinWeight workflow plugin. Coding tools such as Compound
Engineering, Codex, and Claude do the implementation; Ollija owns where that
work happens, its durable run boundary, the checkpoint commit, and—only when
the owner requested it—the production-through-staging tail.

## Ask at most three simple questions

Ask only for choices the owner has not already supplied:

1. Should this stop at a verified commit, or continue to production through
   staging?
2. Should Codex or Claude perform the coding work?
3. If the plan does not declare a test command, what bounded check should
   Ollija run, or why is this documentation-only?

Do not ask permission again at every green machine-checkable step. A production
grant continues automatically when checks pass, but it waits for any desktop
or physical-iPhone approval required by the exact candidate. No ordinary
session, status read, shell login, or machine startup grants work authority.

## Enforce host, workspace, and Git placement strictly

- `fuchitalee` is the sole writable authority. `allenwlee` is a keyboard and
  browser endpoint. Never create a checkout, worktree, cache, backup, receipt,
  task source, or runtime artifact on `allenwlee`.
- Every task worktree must be a registered Git worktree beneath
  `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/<branch>`. Do not
  create sibling worktree roots, nested repositories, or ad hoc local copies.
- One task uses one branch and one worktree. Never attach one branch to two
  worktrees, move a live task's directory, or delete a worktree while its task
  is active or has an uncommitted recovery diff.
- A fresh `go` requires a clean worktree. “Dirty” means Git sees uncommitted
  file changes. After a paused, cancelled, lost, or failed generation, only the
  same task may be explicitly re-armed with that preserved dirty diff.
- The coding agent may edit and test, but it must not stage, commit, push,
  deploy, release, create another worktree, or launch another agent. Ollija
  independently runs the declared checks, stages the dedicated task diff, and
  creates the checkpoint commit.
- Never substitute direct Git, Render, PostgreSQL, receipt, or tag mutations
  for the Ollija command surface.

## Begin from observed state

Run this read-only command first:

```bash
./bin/ollija status --json
```

Read `status`, `state`, `next_action`, warnings, evidence, task attribution,
process identity, and SHA identities. Use `./bin/ollija doctor --json` for setup
failures. Status reports state; it never starts, resumes, or extends a task.

## Start, observe, stop, and re-arm bounded work

Arm one tracked plan or task brief with exact argv (argument vector) checks:

```bash
./bin/ollija go \
  --task <stable-task-id> \
  --source docs/plans/<tracked-plan>.md \
  --agent codex \
  --endpoint commit \
  --verify-argv '["pytest","tests/ollija"]'
```

Use `--endpoint production` only when the owner chose production through
staging. Use `--no-test-reason '<bounded reason>'` only for genuinely
documentation-only work. The detached supervisor survives the originating
terminal and records origin host/terminal separately from execution host.

```bash
./bin/ollija task-status <task-id> --json
./bin/ollija stop <task-id> --json
```

`stop` records durable cancellation before signaling the exact process group.
It preserves the worktree and uncommitted files. A child-agent crash gets one
automatic retry; a second crash pauses. A missing supervisor or host reboot
never auto-resumes. Cancelled, paused, failed, or lost work requires a new
explicit `go`; it cannot resurrect from a heartbeat or a new chat session.

Ollija does not hand the task to another release agent. The same Ollija-owned
generation supervises coding, creates the checkpoint, and—when granted—runs
the existing release workflow.

## Map owner language to one transition

| Owner intent | Command |
|---|---|
| “What’s next?” | `./bin/ollija status` |
| “Start bounded work” | `./bin/ollija go --help` |
| “How is task X doing?” | `./bin/ollija task-status X` |
| “Stop task X” | `./bin/ollija stop X` |
| “Check the setup” | `./bin/ollija doctor` |
| “Start this beta/change” | `./bin/ollija start` |
| “Refresh review data” | `./bin/ollija refresh-local` |
| “Show local staging” | `./bin/ollija preview` |
| “Stop local staging” | `./bin/ollija preview-stop` |
| “Refresh hosted staging” | `./bin/ollija refresh-staging` |
| “Stage this” | `./bin/ollija stage` |
| “Assess the UI” | `./bin/ollija assess-ui` |
| “Desktop looks good” | `./bin/ollija approve desktop` |
| “Physical iPhone looks good” | `./bin/ollija approve iphone` |
| “Override broken Bridgewright” | `./bin/ollija override bridgewright --owner <id> --reason '<why>'` |
| “Release the beta” | `./bin/ollija release` |
| “Verify production” | `./bin/ollija verify-production` |

State the external effect before a standalone release mutation. Re-run status
after it and report the one next action.

## Preserve human and deployment authority

- Record desktop or iPhone approval only after the owner explicitly approves
  that exact hosted deployment. A simulator, screenshot, agent inspection, or
  Bridgewright assessment is not physical-iPhone approval.
- Treat Bridgewright as assessment evidence only. It cannot approve, deploy,
  release, or replace owner review. If the adapter itself is defective, an
  explicit candidate-bound owner override records owner, failed assessment,
  and reason without pretending automated evidence passed.
- `release` first verifies that a usable authenticated browser session and all
  production route/selector contracts exist. It must fail before advancing
  `main` if later production verification could not run.
- A candidate already live but not sealed resumes at `verify-production`; it
  must never release the same SHA twice.
- Do not report success until every configured Render service is at the exact
  SHA, the authenticated headline is visible, DSV4 is configured, the beta tag
  exists, and the final receipt is sealed.
- Never print connection URLs, provider keys, OAuth secrets, browser storage,
  prompt bodies, provider responses, or private post content.

## Diagnose and document without becoming a gatekeeper

Ollija preserves the product candidate and task work, records a bounded local
incident, and recommends a diagnostic route. The invoking agent or owner runs
the named skill; Ollija does not launch a second autonomous debugging system.

- SSH, shell, environment, virtualenv, tmux, or multi-machine failures:
  `infra-shell` first, then `ce-compound` after the fix.
- Code or test failures: `ce-debug`, then `ce-compound`.
- UI assessment failures: Bridgewright for evidence, plus `ce-debug` when code
  is implicated, then `ce-compound`.
- Release-verification defects: Ollija state first, then `ce-debug` and
  `ce-compound`.

Read `docs/operations/ollija.md` for task recovery, staging, browser-session,
database-refresh, and release details. Read `docs/deploy/render.md` when live
Render topology or DSV4 configuration is involved.
