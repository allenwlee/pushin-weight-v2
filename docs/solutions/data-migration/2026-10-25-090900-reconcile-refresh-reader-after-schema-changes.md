---
title: "Reconcile the real refresh reader after schema changes"
date: "2026-10-25"
category: data-migration
module: staging_refresh
problem_type: workflow_issue
component: database
severity: high
applies_when:
  - "A schema release adds or retires tables or sequences classified by the staging refresh policy"
tags: ["database", "migration", "staging-refresh", "permissions", "release-verification"]
---

# Reconcile the real refresh reader after schema changes

## Context

RG4's production schema and webpage checks passed, and its refresh manifest and
grant runbook described the new objects. The actual production
`staging_refresh_reader` role still lacked SELECT on 59 copied tables and 36
sequences, plus MAINTAIN on two excluded tables. The gap included additions from
earlier refactor groups. A correct manifest alone had not preserved the next
production-to-staging refresh's ability to run.

This was discovered during release verification, before starting another
refresh. At 2026-10-24 23:58 UTC, the missing grants were applied to the existing
role according to the existing policy. No new role, row-write permission,
web credential change, dump or restore was required.

## Guidance

Treat the actual source account's privileges as part of a schema release.
After the target migrations are applied, inspect it using the source credential
configured on the service that runs staging refreshes. An owner connection or
an ORM schema check does not exercise that account's permissions.

Use the existing inspection and policy guard in
`scripts/staging_refresh/database.py` and `scripts/staging_refresh/policy.py`:

```python
inspection = PostgresRuntime._inspect(source_url)
_guard_source_inspection(policy, inspection)
```

Here `source_url` is the existing service-owned source credential, resolved only
in memory, and `policy` is the loaded `config/staging_refresh.yaml`. This is an
inspection, not an instruction to start a refresh. Never print or save the URL.

Reconcile only the differences allowed by that policy and the grant instructions
in `docs/operations/staging-data-refresh.md`. Copied tables need SELECT. Excluded
tables must remain unreadable; their PostgreSQL 18 MAINTAIN privilege permits
the schema locks required by the existing dump workflow. Sequences have their
own SELECT requirements. A blanket grant on every table would expose excluded
source data and would fail the existing policy guard.

Reconnect with the real source credential after the repair. Verify database and
role identity, TLS, default read-only mode, no row/schema-write privileges,
complete object classification, permitted table reads, excluded-table lock
access and sequence reads. Do not report this as dump/restore verification.

RG4's verified result was 221 classified physical tables: 155 readable and 66
with MAINTAIN but no row reads, plus 120 readable sequences. The guard passed
with `has_write_privileges=False`. These are dated observations, not permanent
expected counts for later schemas.

## Why this matters

Migrations create objects; editing a checked-in grant example does not execute
it on an existing role. Webpage checks use a different account and therefore
cannot establish snapshot-reader readiness. Without this release check, the
failure is deferred until the next refresh, when the missing grants can look
like a new refresh defect instead of an incomplete earlier schema release.

## When to apply

Apply this check after each group changes the physical objects covered by the
refresh policy, including deletions and sequence changes. Reuse the established
read-only guard; update actual privileges as well as the manifest and runbook.
It does not authorize a production restore, a new database, or a refresh run.
