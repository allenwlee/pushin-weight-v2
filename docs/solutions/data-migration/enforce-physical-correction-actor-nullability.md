---
module: core
date: "2026-10-21"
problem_type: database_issue
component: database
severity: high
symptoms:
  - "Production PostgreSQL allowed NULL in collection_corrections.actor_id although the Django model declared a required Actor foreign key"
  - "Migration state and current model agreed, but the physical database column remained nullable"
root_cause: missing_validation
resolution_type: migration
tags: ["database", "migration", "nullability", "foreign-key", "schema-verification"]
---

# Django migration state can hide a missing PostgreSQL constraint

## Problem

After the correction-actor identity cutover, Django treated
`CollectionCorrection.actor` as a required foreign key, but production
PostgreSQL still allowed `collection_corrections.actor_id` to be NULL. The
field declaration is non-nullable in the model (`core/models.py:8946-8956`),
and migration `0125_correction_actor_writer_cutover` changed Django's migration
state to a required `ForeignKey` (`core/migrations/0125_correction_actor_writer_cutover.py:105-115`).
Its database operations populated actor references and installed a compatibility
trigger, but did not alter the column's physical nullability (`:118-128`).

Migration `0127_remove_legacy_identity_columns` checked actor-reference matches
and removed `actor_identifier`, but did not make `actor_id` physically required
(`core/migrations/0127_remove_legacy_identity_columns.py:16-21, 73-77`). A
schema review therefore found a gap that Django's model and migration history
did not show.

## Symptoms

The production PostgreSQL catalog reported `collection_corrections.actor_id` as
nullable even though Django's model and current correction writers required a
registered Actor. That left a database-level path for raw SQL or another writer
to create a correction without its required actor.

Production contained zero correction rows at the time of the follow-up. There
were no existing NULL rows to repair, but future rows could still violate the
intended invariant without a database constraint.

## What Didn't Work

The earlier migration used `SeparateDatabaseAndState` to update Django's model
state independently from its physical DDL. Because it altered the state to a
required foreign key without issuing `ALTER COLUMN actor_id SET NOT NULL`,
Django's migration recorder and current model agreed while PostgreSQL remained
permissive.

The later exact-replacement preflight established that existing rows had a
matching Actor before deleting the old label. It did not establish the lasting
physical `NOT NULL` invariant. Similarly, `makemigrations --check --dry-run`
reports whether model definitions differ from Django's migration state; it does
not compare every live PostgreSQL constraint with that state.

## Solution

Migration `0128_require_correction_actor` leaves Django state untouched because
the state already correctly marks `actor` required. Its database operations
first count NULL actor references and raise an explicit error if any exist,
then set a five-second lock timeout and a thirty-second statement timeout, and
execute `ALTER TABLE collection_corrections ALTER COLUMN actor_id SET NOT NULL`
(`core/migrations/0128_require_correction_actor.py:6-16, 19-49`). The migration
fails closed instead of inventing or discarding actor identities.

Query the physical catalog directly before and after the constraint migration:

```sql
SELECT is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'collection_corrections'
  AND column_name = 'actor_id';
```

The expected result changes from `YES` to `NO`. The migration also guards the
precondition explicitly:

```sql
SELECT count(*)
FROM collection_corrections
WHERE actor_id IS NULL;
```

A nonzero result blocks the migration and identifies how many rows need an
approved resolution first.

## Why This Works

PostgreSQL enforces `NOT NULL` for every writer, including raw SQL and bulk
paths that may bypass Django model validation. Keeping `state_operations=[]`
avoids an unnecessary model-state change, while the explicit database operation
repairs the physical schema. The preflight checks data before tightening the
constraint, and bounded timeouts keep the DDL from waiting indefinitely for a
lock or running without a time limit.

The regression tests inspect PostgreSQL catalog state, not only ORM behavior.
The successful path confirms `is_nullable='YES'` before migration0128 and
`'NO'` afterward (`tests/test_shared_identity_column_retirement.py:76-83,
121-130`). A second case deliberately inserts a NULL after migration0127 by
temporarily disabling the table's immutability trigger, then verifies
migration0128 raises and leaves the column nullable (`:133-177`). The plan
records three passing PostgreSQL tests, clean `makemigrations --check --dry-run`
and Django system checks, and staging plus production catalog verification for
candidate `f3876ede88ecb3ab129af2cd4aa5d5d6d915ea3a`
(`docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md:271`).
Production still had zero correction rows; isolated PostgreSQL regression
tests cover both the populated valid case and the injected-NULL failure.

## Prevention

When using `SeparateDatabaseAndState`, review the migration's two sides
separately: what Django believes and what SQL actually changes. For every
intended invariant—especially required columns, foreign keys, uniqueness and
checks—identify the PostgreSQL operation that enforces it and verify the live
catalog. A clean migration-state check is useful, but it is not physical-schema
proof.

For a constraint-tightening migration, add both a fail-closed data preflight
and a PostgreSQL regression that covers the valid transition and a deliberately
invalid row. Assert catalog state before and after, plus after a refused
migration, so a test cannot pass solely because the ORM rejects bad input.
Repeat the read-only catalog query against staging and production after
deployment.
