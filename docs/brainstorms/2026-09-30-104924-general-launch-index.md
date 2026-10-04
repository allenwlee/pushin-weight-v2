---
title: General Launch Index
created_at: "2026-09-30T10:49:24+09:00"
status: active-coordination
---

# General Launch Index

Start here for work on the general-page launch. Read the
[General Launch Charter](2026-09-30-104924-general-launch-charter.md), then follow
the task plan for the G item you are working on. The charter defines the work;
this index records who is doing it, what happens next, and the human-readable
session log. Neither document is an implementation plan.

## Shared location

The authoritative coordination files live on **fuchitalee**, at:

```text
/Users/fuchitalee/development/pushin-weight-v2/docs/brainstorms/2026-09-30-104924-general-launch-index.md
/Users/fuchitalee/development/pushin-weight-v2/docs/brainstorms/2026-09-30-104924-general-launch-charter.md
```

Sessions in linked worktrees must consult and update these shared files, rather
than maintaining divergent worktree copies. Task code and detailed task plans
remain in their assigned worktrees. Record the actual plan/worktree location
when adding a plan link. These new files need an authorized commit/push before
they can be assumed present in other clones or branch snapshots.

## Workstream status

| G item | Outcome | Task plan | Active sessions and owned scope | Status | Next step / blocker |
| --- | --- | --- | --- | --- | --- |
| G1 | Verified researcher identities and images | [G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md), [PR #49](https://github.com/allenwlee/pushin-weight-v2/pull/49), `feat/g1-staff-identity-library` | None; production scaffold/pilot release complete. | Implementing | Scaffold and saved DeepSeek pilot are live at `f176e614`: 24 people, 35 stored images, repeat-import and restart checks passed. Review 11 current portrait gaps, pending roles and legacy wrong-company claims; establish shared worker storage and paid-search limits before broader collection. General G1 acquisition and launch readiness remain unfinished; separate harvester-health warnings are recorded in the plan. |
| G2 | English, Chinese, and Japanese editorial voice | Not created | None recorded | Not started | Research reference voices and prepare a bounded comparison packet. |
| G3 | Topic history behind each general-page headline | Not created | None recorded | Not started | Turn the existing longitudinal research into one concrete reader experience. |
| G4 | Controlled public API and MCP | Not created | None recorded | Not started | Define permitted outputs, check relevant terms, and resolve source-link versus anonymity wording. |

These statuses refer to the four launch workstreams, not earlier related
research or the existing visual prototype. No working session has been assigned
or inferred from merely creating this index.

Suggested statuses: **Not started**, **Investigating**, **Planning**,
**Implementing**, **Reviewing**, **Paused**, **Blocked**, and **Ready**.
**Ready** requires linked completion evidence against the task plan and charter;
it does not mean deployed. Keep the concrete delivery observation in the task
plan: local, pushed, staging, or verified production, as applicable.

## How sessions use this index

1. **Start or resume:** read the current charter, this table, and the relevant
   task plan. Check existing active claims and actual branch/worktree state.
   Choose a recognizable session identifier and keep it unchanged for that
   session; use the platform thread/session ID when available, otherwise a
   descriptive unique label. Record the G item, bounded subtask, branch/worktree,
   and files owned. Append an **ON** log entry and update the active-session cell
   before starting the task.
2. **Work:** keep detailed progress, evidence, and commands in the task plan.
   Update this index when status, ownership, blockers, or dependencies change.
   Multiple sessions may work on the same G item only with explicitly disjoint
   subtasks/file ownership or an agreed handoff. Keep every active session
   visible; one session must not overwrite another's claim.
3. **Pause, switch tasks, or finish:** record results and the exact next step in
   the task plan. Append an **OFF** entry with the reason and a one-line summary
   of work performed. Remove only your active claim and set the appropriate
   workstream status. Switching G items requires OFF for the old scope and ON
   for the new scope. A task can remain unfinished when its session logs off.
4. **Recover an abrupt stop:** a crashed or closed session may leave no OFF
   entry. Do not invent one on its behalf or assume an old timestamp proves it
   stopped. Check for live work and preserve its edits. When taking over is
   justified, append **RECOVER** explaining the evidence, update ownership, and
   append your own ON entry.
5. **Change shared requirements:** reconcile with current owner instructions,
   update the charter in place, identify affected G items/task plans, and append
   a **DECISION** entry with the source of authority. Agent proposals stay
   labeled proposals until resolved. No additional approval is needed merely
   to record an instruction already given by the owner.

Sessions perform these updates as part of their work. There is no automatic
session detector or background index updater. A later session can resume from
the recorded next step without requiring the previous session to remain alive.

## Concurrent edit discipline

Before writing this shared index or charter, reread the current file and make a
small targeted change. Do not regenerate it from an earlier copy. Preserve all
other rows and log entries. Serialize overlapping coordination edits when
another session is editing the same area; resolve conflicts against the latest
file rather than replacing it wholesale. The active-session table coordinates
people and agents; it is not a technical lock.

For each workstream's implementation plan, follow `AGENTS.md`: read the installed
Ollija skill, run `ollija annotate-plan` before selecting/creating the plan, and
use the exact returned path. Link that plan here. Keep each capability's detailed
work in its plan rather than creating a second progress ledger in this index.

## Log

Append one row when logging **ON** or **OFF** a G item. Use the actual event time
in ISO 8601 format with the offset, normally JST (`+09:00`), e.g.
`2026-09-30T10:49:24+09:00`. Keep the summary to one line: the bounded work
started, or what was accomplished and where the next session should continue.
Do not backdate events or convert an OFF entry into a claim that the task is
complete. Log a later correction as a new row rather than rewriting an earlier
session's account.

**ON/OFF** are the normal session events. **UPDATE**, **RECOVER**, and **DECISION**
record material progress, takeovers, and shared decisions respectively. For
coordination across all four items, use `G1–G4 (coordination)`; this does not
introduce a fifth launch workstream.

| Datetime (with timezone) | Event | G item | Session | One-line work summary |
| --- | --- | --- | --- | --- |
| 2026-09-30T10:49:24+09:00 | ON | G1–G4 (coordination) | general-launch-setup-20260930 | Started the owner-authorized charter, shared index, session logging rules, and AGENTS.md discovery pointer in the authoritative root; no capability implementation started. |
| 2026-09-30T10:52:50+09:00 | OFF | G1–G4 (coordination) | general-launch-setup-20260930 | Completed both coordination documents and the AGENTS.md pointer; reviewed content and verified local links/whitespace; next sessions can claim G1–G4 and establish their task plans; files are not committed or pushed. |

## Related context

- [General Launch Charter](2026-09-30-104924-general-launch-charter.md): requirements and open decisions.
- [Longitudinal research](../research/2026-09-28-111844-agentic-ai-media-advantages.md): existing research, including the general/product/dashboard distinction.
- [First-screen prototype capsule](../../.context/compound-engineering/ce-prototype/2026-09-29-general-homepage/decisions.md): local preview, references, limitations, and unaccepted design questions.
- [First-screen prototype HTML](../../.context/compound-engineering/ce-prototype/2026-09-29-general-homepage/01-above-the-fold/screens/index.html): local artifact; do not infer a running server from its existence.
- [Meta Muse collection proposal](../handoffs/2026-09-28-183339-meta-muse-harvest-proposal.md): adjacent prior research; not an extra authorized G item.
- [Docs taxonomy](../docs-taxonomy.md): routing guidance for research, plans, evidence, and handoffs.

| 2026-10-04T08:37:52+09:00 | ON | G1 | g1-chinese-faces-20260930 | Owner requests “lfg to deployment” after the production-rollout summary. Continue the existing G1 plan through staging rehearsal, backup, coordinated production code/schema release, matching/import of the 24-person DeepSeek pilot and stored assets, and live verification. Paid search remains disabled; preserve other workstreams and existing suspended services. |
| 2026-10-04T11:11:18+09:00 | OFF | G1 | g1-chinese-faces-20260930 | Deployed scaffold and saved DeepSeek pilot at `f176e614` through production-sized staging, verified backups, migrations, 24 people (21 new/three matched), 35 persistent images and duplicate-free replay. Restored all service states/schedules; normal harvest inserted 20 verified rows but retained degraded-health warnings. Paid photo search remains off; 11 current portrait gaps remain. Dossier with assets copied to allenwlee Downloads/agents. |
