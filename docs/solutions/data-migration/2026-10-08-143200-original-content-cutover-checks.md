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

## Production history needs a bounded query shape

The compatible production rollout found a second failure before import:
PostgreSQL could not write its temporary cursor file. The history query joined
27,155 headline parents to their complete run snapshots. Django opened a
holdable server cursor outside a transaction, repeating the large snapshot
for every parent and materializing that joined result. Reducing the fetch
batch size did not remove the oversized database result.

`headline_history()` now streams small run fields and processes each run's
parents separately. It loads the saved snapshot only when a citation needs
it and shares that run object for the whole group. The metadata import also
selects only the run fields it updates and retains the shared run object when
locking a parent. Keep the potentially large JSON out of the joined cursor.

The PostgreSQL regression uses a large saved snapshot and several parents.
It proves that dry-run, import and replay avoid a snapshot-bearing join and
read that snapshot once per pass. The actual production history check then
completed without the temporary-disk failure. The failed check had made no
content import or reader switch.

## Recover source identity from the original saved excerpt

Production's complete dry-run also found 1,966 unresolved historical aliases.
The original evidence ID hashes the candidate ID, post ID, occurrence kind
and saved full excerpt. Later writing projection trimmed that excerpt to 160
characters while retaining the evidence ID. Recomputing the ID from the trim
could never identify the original post.

Use the full excerpt retained in the run snapshot for identity recovery.
Keep the selected writing projection as the citation's recorded hash basis.
The lookup remains bounded by the saved creation time and facts cutoff and
requires one exact hash match; it never consults today's mutable source text
to guess an ID. Three production samples resolved uniquely with the saved
1,000/274/896-character excerpts and resolved none with their 160-character
writing trims. A shortened-projection regression failed before the correction.

The complete production dry-run then reported zero discrepancies. The import
preserved 19 Chatter/Pulse editions and 52 calls, mapped all 27,155 existing
headline parents and created 43,568 relational source links. Eight checksums
over original editorial/product fields and five original-headline table
checksums match before and after import, including all 13,005 pre-existing
localized texts. New imported records and metadata are excluded from those
original-field comparisons. Encrypted restore and native-writer retirement
proof remain separate prerequisites for deleting obsolete tables.
