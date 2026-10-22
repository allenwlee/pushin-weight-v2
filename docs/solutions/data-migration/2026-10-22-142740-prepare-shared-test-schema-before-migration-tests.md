---
module: core
date: "2026-10-22"
problem_type: test_failure
component: database
severity: high
symptoms:
  - "The reused local test database recorded migration0131 while twenty expected tables were physically absent"
  - "A retained name trigger still referenced a removed language column"
root_cause: missing_validation
resolution_type: workflow_improvement
tags: ["database", "migration", "test-isolation", "shared-test-database", "schema-verification"]
---

# Prepare the shared test database explicitly before migration tests

## Problem

A persistent test database can have the expected Django migration history while
its tables or function bodies disagree with the candidate. Reusing that database
without checking both layers can invalidate application tests and let a migration
rehearsal alter the schema that another worktree expects.

## Symptoms

The October22 RG2 investigation found twenty missing application tables and a
name-guard function referring to the removed language column, despite an applied
migration0131 record. This was the local fixture database on fuchitalee,
`test_pw_g3_timing_20261019` at `127.0.0.1:55436`, separate from Render staging
`pushinweight_staging` and production `pushinweight_shadow`.

The investigation did not establish which earlier command produced the physical
drift. PostgreSQL statement logging was unavailable. The earlier retained dump
already contained no business rows, so empty test tables did not establish lost
durable data or causation by the separate filesystem cleanup.

## What Didn't Work

`--reuse-db` is reuse, not a guarantee that pytest startup cannot migrate. The installed Django database creation path still calls `migrate` after the keep-database creation step. The
host wrapper now refuses pending or incompatible migration histories, but that
history check does not inspect every physical column or stored function. A clean
`makemigrations --check` likewise compares Django state, not the live catalog.

Adding `replaces` to already published migrations would change the graph for
other environments to solve a local problem. Those attempted local edits were
removed. Creating another complete database or restoring production data was
also outside the selected shared-database procedure.

## Solution

Use the existing host wrapper for exclusive test or maintenance access. Verify
the selected database and absence of other clients; explicitly prepare the
reviewed candidate schema before pytest; then check migration history, all
expected tables and columns, and the affected constraints and function bodies.
Retain the candidate and migration-file identities with that evidence. The
canonical host operating note is
`/Users/fuchitalee/infra/docs/reference/pushinweight-shared-test-database.md`.

The repaired local fixture schema was rebuilt from canonical migrations under
exclusive ownership after saving its dump and inventory. The PostgreSQL instance
and database were retained. This was a repair of disposable test fixtures, not a
routine instruction to reset databases or an authorization to affect other
sessions' data.

Historical upgrade tests now use `migration_rehearsal_schema` in
`tests/conftest.py:49`. It creates a temporary schema inside the designated
database, moves relocatable extensions from public into a separate temporary
extension namespace, and sets a search path containing those two namespaces
only. It asserts that no migration recorder is visible before migrating. Each
migration retains its normal transaction policy, including concurrent indexes.
Cleanup restores the original search path and extension locations, removes only
its temporary schemas, and asserts that public migration history is unchanged.

The same file's locale fixture (`tests/conftest.py:18`) recreates the small
required locale catalog for pytest database tests and Django test classes after
normal transaction-test flushes. Required seed rows belong in fixtures; they
must not depend on a retained business-data snapshot.

Physical parity is enforced by
`tests/test_collection_schema_regression_net.py:51`, which compares every managed
core table's physical columns with the ORM and schema reference. The RG2 upgrade
test in `tests/test_rg2_locale_owner_migrations.py:23` independently exercises the
old schema, compatible cutover, new writes and physical deletion, including the
retained historical view and locale-based guard.

## Why This Works

A temporary schema is isolated only if missing names cannot fall through to the
shared public schema. Otherwise an absent migration recorder can resolve to the
public recorder and silently turn a supposed fresh migration into work against
shared state. Separate extension visibility is needed because index/operator
objects must remain available without making public application tables visible.

The wrapper lock coordinates exclusive use of the whole database, which matters
because moving an extension affects more than one schema. Preserve normal
migration transaction behavior instead of wrapping the entire rehearsal in one
transaction; concurrent index migrations need their own supported boundary.

Django's normal test cleanup may remove business rows. The important persistent
resource is the verified database infrastructure and candidate schema; required
catalog data must be recreated by fixtures. Treat independently owned data
separately if it is discovered.

## Prevention

Before each candidate test run, verify both migration history and the physical
schema. After schema-changing tests, repeat the affected physical checks and
confirm public history and extension placement were restored. After production
delivery, reconcile that receipt with the released candidate before preparing
the next group; do not wait until production to prepare tests or roll a newer
shared schema backward for an old worktree.

Use the temporary-schema fixture for historical migration rehearsals under the
wrapper. Do not use the older additional-database fixture on this shared host.
Do not infer local schema correctness from a staging deployment, or production
correctness from a local test result. Keep all three identities in release
receipts.

Related: [Django migration state can hide a missing PostgreSQL constraint](enforce-physical-correction-actor-nullability.md)
explains the distinct production nullability failure that also required catalog
verification. The current release procedure is recorded in the
[global schema plan](../../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md).
