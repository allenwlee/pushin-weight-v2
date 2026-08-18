# Ollija change ledger

This is Ollija's lightweight, durable record of material behavior and rule
changes. It explains why the change was necessary, what is different now, how
the change was proved, and whether releasing it affects the application,
databases, or production data. It complements Git history; it does not replace
a plan or a longer `docs/solutions/` article when either is genuinely useful.

Ollija requires a new entry whenever a task changes its implementation,
operator rules, skill instructions, or release runbook. Correcting this ledger
alone does not require a second entry. Do not add handwritten authorship: the
Ollija task ledger records the coding agent, originating terminal, execution
host, task generation, and checkpoint commit.

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
