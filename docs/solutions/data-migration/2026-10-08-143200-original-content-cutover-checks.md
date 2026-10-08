---
module: "OriginalContent storage"
date: "2026-10-08"
problem_type: "logic_error"
component: "database"
severity: "high"
symptoms:
  - "Cutover readiness remained true after deleting the shared featured pointer."
root_cause: "missing_validation"
resolution_type: "code_fix"
tags: ["original-content", "cutover", "reconciliation", "postgres"]
---

# Reconcile featured selection before switching content readers

Copying every story and source does not prove that the new reader selects the
same featured story. During the OriginalContent compatibility implementation,
the readiness check compared saved copy, citations and budget reservations but
did not compare `EditorialHero` with `OriginalContentSelection`.

The regression test imported a real PostgreSQL-backed edition and hero, then
deleted only its shared featured pointer. `readiness()` incorrectly returned
true: switching readers in that state would remove the featured Chatter story.
This was reproduced locally before deployment.

`monitor/original_content_cutover.py` now derives the expected workflow/locale
scope from each selected legacy edition and requires the shared pointer to
reference that exact public edition UUID. Missing pointers, empty pointers and
different selected UUIDs add a reconciliation exception. This check does not
repair or select a replacement during a read-only report.

`tests/test_original_content_cutover.py` includes the missing-pointer regression.
It failed before the fix; the related cutover, backfill and retirement suite
then passed all 12 PostgreSQL-required tests, with no skips or errors.

For later reader migrations, reconcile both saved records and the pointers
that choose visible records. Keep this separate from the migration's ability
to create or copy rows: a successful import and a safe reader switch are
different observations.

The broader staging cutover and destructive retirement are separate work.
This learning records the locally verified guard, not a deployment or restore
claim.
