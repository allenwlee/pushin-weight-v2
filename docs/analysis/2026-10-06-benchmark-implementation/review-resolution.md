# Review resolution

Review of candidate 7bc690e9 against 5082ddf7 found four issues. The original
[review receipt](code-review.json) is retained as the pre-fix assessment.

1. Person intelligence now returns the native X author_id in its existing field.
2. Seed loading resolves the generic Account before writing brand/account links.
3. The planned database offline report now consumes build_comparison directly.
   It retains the original four raw-value panels and embeds all five Pulse lines,
   exact values, scope, baselines and evidence. Duplicate panel selections fail.
4. OpenRouter configuration rejects completed_day_lag=0; HF can still use zero.

All four failures were reproduced before their fixes. The first targeted run
passed 14 tests. The expanded CI-equivalent run passed 223 tests in 77.88 seconds,
including 126 required PostgreSQL tests with zero skips/errors. Three warnings
concern the absent optional local collectstatic directory. Focused Ruff, JavaScript
syntax and whitespace checks passed. Added tests preserve large integer strings,
missing points, native author IDs and actual seeded relationships.

The new report adapter and command received a supplemental inline review covering
missing/ambiguous panels, exact values, source scope, exclusive file output and
HTML escaping through the existing renderer; no remaining finding was identified.
The real DeepSeek report passed four-panel, exact-token, scope, English/Chinese,
390px overflow and console checks. Full five-line Pulse browser verification was
repeated on the unchanged serving code/assets and retained database.

Local review and validation ran sequentially in the main agent under AGENTS.md.
Independent model coverage was unavailable: Claude returned HTTP 402 insufficient
balance; the single Grok replacement timed out without usable output. Neither is
claimed as a completed independent review. Both terminal job directories were
removed. Stage timing metadata is partial; it is not used as correctness evidence.

No unapplied actionable finding remains. Full production migration duration is
still a release concern: preserve one migration owner, a controlled writer window,
and the required verified live backup. The isolated restore is not that backup.
The known unchanged legacy homepage-filter test failure remains documented in
[tested-ready evidence](tested-ready-evidence.md), outside this feature's green gate.

Additional compound documentation was skipped: the code, regression tests, plan,
this receipt and existing migration-incident learning carry the durable reasoning.

## CI integration follow-up

On ecec4e43 the benchmark workflow passed. Staff CI passed 299 tests and found
two additional integration gaps: its schema assertion still expected the pre-0066
person/account column, and staging refresh had not classified the fifteen new
tables. Both failures were reproduced locally before changes.

The person/account test retains both uniqueness failures and now checks the UUID
foreign key plus the actual native compatibility column through SQL. The staging
policy copies all fifteen durable taxonomy/measurement tables, records the three
new sequences and allows their absence on older source schemas. Fourteen receive
exact count checks; data_sources can gain X/HF seeds during 0066, so its source
count is not pinned. Candidate account/post columns are explicitly required.
The source-grant runbook matches that policy; no grants or refresh ran.

The affected schema/staging-refresh suite passes **123 tests**, including 13
required PostgreSQL cases with zero skips/errors. Focused lint and whitespace
checks pass. The remaining staff tests passed in the preceding remote run and
will run again on the final candidate. This corrects integration with the new
schema; it removes no assertions, skips or authorization checks.
