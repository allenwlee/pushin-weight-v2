---
title: Bounded Ollija task recovery without agent resurrection
module: ollija
tags:
  - task-supervision
  - worktrees
  - multi-machine
  - release-safety
problem_type: workflow_issue
date: 2026-08-17
---

# Bounded Ollija task recovery without agent resurrection

## Problem

An agent launched from a laptop terminal should not lose hours of work when the
terminal, SSH connection, VS Code window, or coding process crashes. But an
always-running agent that silently resumes after the owner intentionally stops
it is worse: it can reclaim a dirty worktree, continue an obsolete instruction,
or approach production without fresh authority.

Plain text memory and authorship lines were not deterministic enough. Different
agents did not always append them, simultaneous sessions could overwrite them,
and a document could not prove which process still had authority. Worktrees
also accumulated in inconsistent locations across machines.

## Resolution

Separate durable authority from process survival:

1. One explicit `ollija go` creates a versioned task generation in the
   canonical SQLite ledger on `fuchitalee`.
2. The grant binds a tracked task source and digest, one registered worktree,
   coding driver, endpoint, verification argv, origin attribution, and one
   crash retry.
3. A detached tmux supervisor keeps the child alive across client-terminal
   loss. Each child runs in its own recorded process group.
4. `ollija stop` commits cancellation before signaling that exact process
   group. Cancellation is terminal for the generation and wins late races.
5. A host reboot, lost supervisor, second child crash, or intentional stop
   never auto-resumes. Another explicit `go` creates a new generation.
6. Fresh tasks require a clean worktree. Only the same terminal task may
   explicitly re-arm its preserved dirty recovery diff.
7. The coding agent edits but does not commit or push. Ollija verifies the task
   source and branch identity, runs the declared gates, commits the diff, and
   records the resulting SHA.

All task worktrees live beneath the one canonical hierarchy:

```text
/Users/fuchitalee/development/pushin-weight-v2/.worktrees/<branch>
```

No PushinWeight checkout, task state, receipt, cache, or backup is created on
`allenwlee`; it remains a keyboard/browser endpoint.

## Release-specific lesson

The production endpoint reuses the existing candidate, refresh, staging,
approval, release, and verification services. It does not add a parallel Git
or Render path. Machine-checkable green steps continue automatically; required
owner approvals pause the same task generation.

A production candidate already live but lacking the final receipt is
`live but unsealed`. Recomputed status must go directly to
`verify-production`, never repeat `release`. The release command also validates
the authenticated browser and route/selector prerequisites before it advances
`main`, preventing a deployment that Ollija already knows it cannot seal.

## Failure documentation

Ollija records a bounded incident envelope rather than raw logs or agent prose.
It includes task/generation/attempt, safe phase and code, affected SHA, and
ordered route tokens:

- machine, SSH, shell, tmux, environment, or virtualenv: `infra-shell` first;
- code or tests: `ce-debug`, then `ce-compound`;
- UI assessment: Bridgewright plus `ce-debug` when code is implicated;
- release verification: preserve/recompute Ollija state, then debug and
  compound the tooling fix.

Incident files never contain prompts, provider responses, browser storage,
secrets, private post content, or unbounded process output. Ollija recommends
the external diagnostic skill; it does not launch another persistent agent.

## Regression net

Keep automated coverage for:

- one crash and one retry, with no third attempt;
- cancellation before signal and cancellation winning late success;
- exact process-group termination without broad `pkill` matching;
- missing supervisor becoming `lost` without automatic resurrection;
- clean fresh-task enforcement and same-task dirty recovery;
- source drift, agent-created commits, missing diffs, and failing gates;
- Ollija-owned checkpoint commits;
- live-but-unsealed production resuming verification without release;
- browser prerequisite failure before production mutation;
- agent-neutral Codex/Claude status and automatic attribution.
