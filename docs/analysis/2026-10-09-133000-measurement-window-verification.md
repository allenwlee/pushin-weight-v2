# Database-enforced measurement windows: verification and deployment handoff

The three-column implementation preserves nullable start/end evidence and adds
a stored generated `window_range`. PostgreSQL creates finite `[start,end)`
ranges only when both endpoints are known. Either unknown means the entire
range is SQL NULL, while any known endpoint remains stored. Supplied infinity,
reversed intervals and empty intervals are rejected. State measurements keep
their existing instant/date fields and a NULL flow range.

Scope: plan R46–R49, U29–U31; based on `671e968290780813bdbbfb9cd0d37bb74f601c6a`.
Migration leaf: `0081_measurement_window_index`, after
`0080_measurement_window` and the existing 0079 leaf. No new tables or changed
provider clocks. Current endpoint is a verified PR; staging and production
have not received these migrations.

## What was verified

The read-only live profile found 354,279 values, 75,292,672 bytes including
indexes, and PostgreSQL 18.4. Its timing shapes included 33,441 complete exact
windows, 114 known-start/unknown-end date-only windows, 131,081 date-only
values with no flow bounds and 189,643 unknown values. This profile did not
write live data or request provider APIs.

The isolated rehearsal used PostgreSQL 18 on fuchitalee, port 55436, database
`pw_benchmark_time_range_20261009`, cloned from retained
`pw_g5_collected_20261009`. It contained 354,237 values. Its source database
was preserved. All source facts, identities and immutable contracts remained
unchanged.

| Proof | Result |
| --- | --- |
| Competing SHARE lock | Refused after 5.110 seconds; neither function nor generated column committed |
| Populated column migration | 1.589 seconds locally |
| Concurrent range index | 0.232 seconds locally; valid and ready |
| Complete range versus scalar bounds | Zero mismatches; finite, nonempty and `[)` throughout |
| Original row checksum | `dc10c6f64f0aa045629689544180f7bf`, identical before, after, reversal and reapplication |
| Populated reversal | 0.296 seconds locally; original columns and values preserved |
| Reapplication | 1.537 seconds locally |
| Table plus indexes | 76,292,096 bytes before; 78,094,336 after |
| Four combined chart responses | Identical before/after/reverse/reapply at a fixed comparison clock |

The four comparisons were DeepSeek/GLM with each of OpenRouter and OpenCode.
Before/reversing the schema, characterization deferred only the newly absent,
unused field from root/related SELECTs. Every existing query, relationship,
stored value and computation remained real. After migration the ordinary
current ORM queried the generated column. The comparison clock was fixed to
avoid interpreting the response's changing `generated_at` as a data change.
Neither provider measurements nor chart arithmetic were mocked.

Fresh-database verification applied the complete migration graph and passed
41 focused tests, including actual persistence for all four providers. The
broader benchmark/measurement regression run passed 198 tests, with 115
PostgreSQL-required tests executed, zero skipped and zero setup errors.
Strengthened OpenCode partial/completed-window persistence then passed its
focused regression. Fourteen interval tests include the shared-window-table
schema guard, exact lower/upper boundaries, fractional-second membership,
unknown/partial endpoints, raw SQL rejection, bulk-update regeneration,
equivalent timezone offsets, 23/25-hour DST days and a temporary future table
using the same database constructor. The first proof-first test failed on
the missing generated field before implementation.

The browser exercised the actual Django Pulse page and JSON over the
populated rehearsal database: DeepSeek and GLM combined charts, three series,
Arena publications/confidence/rank/battles, normalization, smoothing, legend,
raw view, date axis, mobile geometry and export. All 79 recorded browser
commands passed. The task-owned headless session and local server are removed
at handoff; screenshots/logs remain private on fuchitalee. No visible UI change
or third-party login was required.

`makemigrations --check --dry-run` reports no changes; Django system checks and
`git diff --check` pass. Ruff passes all new modules/migrations and affected
tests. `core/models.py` has the same 177 pre-existing lint findings as the
base, with none added by this change; broad legacy lint is not called clean.
No project type-check command is configured.

## Review scope and limits

Plan review checked consistency, feasibility and adverse migration outcomes.
It reconciled the current PR endpoint with historical production grants and
made the rewrite/lock cost explicit. Simplification checked reuse, clarity and
efficiency and retained the existing checks alongside the generated rule.
No additional simplification was needed.

Code review covered correctness, repository rules, testing, migration safety,
reliability, performance and adverse failure paths. All review work ran inline
under the owner's AGENTS.md Task/Subagent/Parallel mapping. No independent
reviewer, cross-model reviewer or separate validation agent ran; that coverage
is unavailable and is not counted as passed. The final scoped diff has no
unresolved actionable finding or settlement conflict. The generated-column
dependency ordering was corrected during implementation: endpoint-comment
AlterField operations precede adding the range, and reversal drops the range
before altering endpoints.

The native database rule lives in immutable `measurement_window_v1`, with a
shared Django generated-field factory and a schema guard for metric tables
using the canonical window endpoint names. Column/function comments expose
the boundary contract to direct SQL readers. Adding a new rule means a new
function version and explicit migration; do not replace an existing function's
semantics under persisted generated values.

## Future deployment and recovery

The measured local times are rehearsal evidence, not production guarantees.
The stored column rewrites `metric_values` under an exclusive table lock.
Migration 0080 admits that lock for at most five seconds and bounds statements
at 120 seconds within its transaction. A busy table causes an atomic failure;
diagnose the conflicting activity and retry after it clears. Other tables,
source schedules and collectors are not paused by this implementation.

Before an authorized production cutover, verify a recoverable live snapshot
with the required recovery scope. The retained October 8 production snapshot
was fully restored but predates subsequently imported/collected metric data;
take and restore a new snapshot if recovery must include that later data.
It may be taken hours before the planned deployment. Use the existing shared
build migration runner to serialize service builds. New application processes
must start after 0080 is applied; old application code can continue using the
retained endpoints on the expanded schema.

Migration 0081 creates the partial GiST index concurrently outside the
transaction. A failed concurrent build can leave its index invalid. Inspect
`pg_index` and the migration ledger before retry; remove only the owned invalid
`idx_value_window_range` with a concurrent drop under the migration guard, then
retry 0081. Do not drop a valid/shared index or use CASCADE.

After cutover, verify leaf 0081, generated-column expression/comments, zero
range/boundary mismatches, valid/ready index, preserved unknown boundaries and
the four source/chart paths. Example diagnostic:

```sql
SELECT count(*) FROM metric_values
WHERE (window_range IS NULL) IS DISTINCT FROM
      (window_start_at IS NULL OR window_end_at IS NULL)
   OR (window_range IS NOT NULL AND
       (lower(window_range) IS DISTINCT FROM window_start_at
        OR upper(window_range) IS DISTINCT FROM window_end_at
        OR NOT lower_inc(window_range) OR upper_inc(window_range)
        OR lower_inf(window_range) OR upper_inf(window_range)));

SELECT indisvalid, indisready FROM pg_index
WHERE indexrelid = 'idx_value_window_range'::regclass;
```

Application rollback can retain this additive schema. If schema reversal is
required, first move application processes to code that does not select the
generated column, then reverse 0081 and 0080 to 0079 under the shared guard.
Reversal removes only the derived column/index/function, preserving original
timestamps and measurement rows. A future table depending on the function
must be handled explicitly; the function drop intentionally refuses CASCADE.
