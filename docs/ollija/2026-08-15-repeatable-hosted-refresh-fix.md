---
title: Repeatable Hosted Staging Refresh
date: 2026-08-15
type: solution
component: ollija
---

# Repeatable hosted staging refresh

## Problem

`ollija refresh-staging` worked only when the hosted database was empty. After
the first successful bootstrap, every later candidate stopped because the same
database was already marked active and contained tables.

## Cause

The lifecycle correctly required a fresh hosted snapshot for each candidate,
but the hosted database implementation exposed only its one-time bootstrap
path. Unit tests covered those rules separately and did not exercise their
incompatibility.

## Fix

An active staging database now selects a repeat-refresh plan. Ollija creates a
uniquely named logical shadow database in the same Render Postgres instance,
restores and validates the scrubbed snapshot there, and then swaps database
names in one PostgreSQL transaction. Render keeps using the canonical
`pushinweight_staging` connection, while the previous database is disabled and
retained under an explicit recovery name. A failed pre-cutover attempt removes
only the shadow created by that attempt.

Regression coverage keeps first-time bootstrap behavior, proves that an active
healthy target selects replacement rather than rejection, and rejects targets
with an unsafe marker or incomplete schema.

## Operational result

Operators continue to run the same command:

```bash
./bin/ollija refresh-staging
```

No manual clearing, database deletion, connection-string change, or receipt
editing is required between candidates.
