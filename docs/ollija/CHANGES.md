# Ollija change ledger

This is Ollija's lightweight, advisory human history of material behavior and
rule changes. It explains why a change was necessary, what changed, how it was
proved, and its delivery impact. It complements Git history and plans; no
Ollija command reads, validates, or enforces this file.

Use this compact template:

```md
## YYYY-MM-DD — Short outcome

Type: Fix, feature, or rule

Problem: What failed or was hard to understand.

New behavior: What Ollija does differently.

Proof: The focused automated or bounded manual check.

Release impact: Application, database, production-data, staging, or approval effects.

Related: Optional issue, plan, or solution link.
```

## 2026-08-18 — Add bounded autonomous task control

Type: Feature

Problem: Agent work could outlive a terminal without a durable owner grant,
shared attribution, crash boundary, or reliable path to Ollija's checkpoint
and release controls.

New behavior: Ollija keeps task generations, attempts, origin and execution
attribution, worktree identity, durable cancellation, one bounded restart,
exact process ownership, verification gates, and checkpoint/release outcomes
in its canonical task registry. A new explicit `go` is required after a
terminal failure or intentional stop.

Proof: `pytest tests/ollija`

Release impact: Workflow control only. The task runner does not change the
PushinWeight application schema or production data by itself.

Related: `docs/plans/2026-08-17-175832-ollija-autonomous-task-control.md`

## 2026-08-18 — Require a change-ledger entry

Type: Fix

Problem: Ollija fixes were spread across commits, plans, runbooks, and solution
documents, so understanding prior behavior required a heavyweight search. A
plain instruction to document fixes would not be deterministic across agents.

New behavior: Ollija refuses its checkpoint commit and candidate freeze when a
material Ollija behavior or rule changes without a changed, well-formed entry
in this ledger. Ordinary PushinWeight product changes are unaffected.

Proof: `pytest tests/ollija/test_change_ledger.py tests/ollija/test_task_checkpoint.py tests/ollija/test_cli.py`

Release impact: This changes only Ollija's task and release controls. It does
not change the PushinWeight application, database schema, production data, or
hosted service topology.

Related: `docs/solutions/workflow-issues/2026-08-17-190429-ollija-task-recovery.md`

## 2026-08-18 — Skip data copies for workflow-only candidates

Type: Fix

Problem: Ollija required every candidate to dump, restore, scrub, and copy
production-derived data even when only Ollija's own controls or documentation
changed. That added cost and introduced irrelevant credential and virtualenv
failure points without improving confidence in the candidate.

New behavior: A candidate composed only of Ollija implementation, Ollija
tests, Ollija rules, or documentation proceeds directly to hosted staging.
Unknown, mixed, or product-facing paths conservatively retain the complete
local and hosted data-refresh sequence.

Proof: `pytest tests/ollija/test_change_ledger.py tests/ollija/test_cli.py tests/ollija/test_release.py`

Release impact: No production or staging database is copied or replaced for a
workflow-only candidate. The exact commit is still deployed to hosted staging,
requires its candidate-specific owner approval, and follows the ordinary
production release and verification path.

Related: `docs/operations/ollija.md`

## 2026-08-18 — Make owner approval the production release gate

Type: Rule

Problem: Release was blocked by an authenticated production browser session even
after the owner had reviewed and approved the exact hosted staging deployment.

New behavior: Exact-SHA staging, required machine checks, and explicit owner
approval authorize promotion to `main`. Browser-based production verification
is no longer a prerequisite; it remains an optional post-release sealing check.

Proof: `pytest tests/ollija/test_release.py`

Release impact: Production promotion no longer requires browser storage or CDP
credentials. Render/Git identity and staging approval gates remain enforced.

Related: `docs/operations/ollija.md`

## 2026-08-18 — Guard release worktree location

Type: Fix

Problem: Agents could create linked worktrees outside the repository's shared
release area, leaving Ollija unable to determine whether the checkout was
eligible for staging and release.

New behavior: Ollija names `.worktrees/` the Ollija release worktree area,
warns at worktree creation, asks whether to move an outside worktree, and
provides a deterministic move command for later adoption. The shared Git hook
and command surface keep the owner decision explicit.

Proof: `pytest tests/ollija` plus interactive and noninteractive worktree-hook
checks.

Release impact: Workflow controls only. This changes no PushinWeight
application schema, production data, or hosted service topology.

Related: `docs/operations/ollija.md`

## 2026-08-19 — Retire the stateful release engine

Type: Rule

Problem: Ollija accumulated approvals, receipts, browser checks, task
supervision, database refreshes, and release state that duplicated parent
workflow responsibilities and made routine work difficult to stop.

New behavior: Ollija has one deterministic `annotate-plan` command. It writes
a delivery guide into one shared plan; the parent workflow owns implementation,
Git, staging, promotion, and diagnosis.

Proof: Focused Ollija tests cover deterministic annotation, hook reuse,
agent-parity guidance, retired-surface hygiene, and isolated staging migration
configuration.

Release impact: No application schema or production data change. Delivery now
uses the plan's selected staging or production target without Ollija gates.

Related: `docs/plans/2026-08-19-105405-feat-ollija-plan-annotator-plan.md`
