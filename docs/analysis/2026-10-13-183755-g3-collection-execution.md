# G3 Collection Implementation Evidence

Work source: [Shared Collection Jobs and Model History](../plans/2026-10-13-062212-feat-g3-collection-jobs-history-plan.md).
Base revision: `db5510ccc94ea326dd5f81e833a9c791e5e84d99`.
Canonical branch/worktree: `feat/g3-collection-jobs-history`, `.worktrees/feat/g3-collection-jobs-history` on fuchitalee.
Owner selected LFG through an open pull request and CI result. No deployment, schedule activation or live historical batch is selected. Existing physical table names remain unchanged. U9 belongs to the X/backfill session; whole-plan completion requires its actual integration evidence.

Execution is native inline: project AGENTS.md maps subagent work to sequential main-thread execution. No external implementation model or worker is invoked. Pre-existing planning/research documents were produced in this task and offered through the selected plan; unrelated root/worktree edits remain excluded.

## U1 — Shared Instructions and Fenced Execution

The shared host environment lacked Pillow. An isolated worktree environment was installed from `uv.lock` with `uv sync --frozen --no-default-groups --extra dev --extra benchmark --python 3.12`; no shared environment was changed. PostgreSQL 17.9 is available locally. Tests use the dedicated `pw_g3_collection_20261013` database and its Django test database, not production or staging.

Characterization: `tests/test_collection_schema_consolidation.py` executed six PostgreSQL tests successfully before implementation. New job/state tests then failed during collection because `core.collection_jobs` and `core.collection_state` did not exist.

Implementation: one `CollectionJob` table, nullable job/token fields and a content lifecycle branch on existing runs; typed claim/checkpoint/finish/rejection/import services. Migration reverse refuses to discard job/content evidence. No existing table is renamed.

Verification command:

```sh
DATABASE_URL=postgresql://localhost/pw_g3_collection_20261013 .venv/bin/pytest tests/test_collection_jobs.py tests/test_collection_state.py tests/test_collection_schema_consolidation.py -q --tb=line --reuse-db --basetemp=/Users/fuchitalee/.cache/pw-g3-collection-pytest
```

Result: nineteen passed; nineteen required PostgreSQL cases executed, none skipped. Covers concurrent claims with two connections, lease reclamation, pause fencing, atomic cursor/evidence rollback, unchanged metric/catalog lifecycle, content continuation and rejection/import receipts. The existing table-census assertion was updated for the explicitly approved shared job table.

The [X interface](2026-10-13-160815-g3-backfill-collection-interface.md) names the implemented functions and local evidence. The X runtime call chain is not modified or claimed verified.

## U2 — Reviewed Provider Identities

Catalog links now use the existing `source_subject_mappings` table with a conditional null contract and a subject-qualified unique key. Metric-purpose links retain their original contract requirement, uniqueness and hash construction. Native GitHub account IDs are admitted explicitly; publisher qualification requires an official brand/company account relation rather than an employee affiliation.

The GitHub review service preserves repository IDs through renames, records aliases and reviewed ownership transfers, and supports a family repository's links to multiple canonical model subjects. A bounded import command is inert until `--apply`; admitted mappings remain available after its input file is deleted. Numeric readers explicitly filter metric-purpose mappings. Migration `0082_collection_catalog_mappings` changes no table names and creates no tables; reverse refuses to discard catalog identity evidence.

Evidence: new identity tests first failed on the absent module; a strengthened employee-account case then failed because the initial ownership check admitted any affiliation. The corrected official-role check passes. Latest focused command combines identity, existing database identity/persistence and OpenCode regressions: forty-two tests passed, with thirty-three required PostgreSQL cases executed and none skipped. Model/migration alignment and whitespace checks pass. No real publisher mapping was imported or provider queried.

## Remaining Work

U3–U8 are pending implementation and their own verification. U9 runtime integration remains owned by the X/backfill session; its current staging JSON pilot proceeds independently. The whole nine-unit plan is incomplete.
