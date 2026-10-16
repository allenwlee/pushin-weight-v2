# Collection schema: local implementation verification

Verified: 2026-10-12 20:52:34 JST. Branch `feat/collection-schema-consolidation`,
working tree based on `f43b2904393013107598af3904b78d3be36c76b4`.
Endpoint: implementation and isolated local verification. No commit, push,
production migration, provider collection, scheduler change or deployment.

The original-content seven-day retirement waiting period is removed. Its actual
legacy-writer and encrypted-restore dependencies still block destructive retirement;
no original-content table or writable alias was dropped.

The source-neutral schema creates zero permanent tables, retires two HF run/
observation tables and generalizes three existing tables. Numeric IDs, values,
contracts, original source timestamps and saved chart references survive. Catalog
history preserves scopes, continuation, raw payloads, outcomes and Product evidence
pointers, with explicit source/purpose separation. The old numeric table names are
writable views containing numeric-purpose records only. Catalog migration refuses
an active catalog invocation and holds its existing database lock through completion.

All **342 tests passed**, including **150 required PostgreSQL tests** with zero
skips/errors. Seven warnings report the absent local collected-static directory;
public template/JSON regressions passed. Actual PostgreSQL 18.6 dump/restore checks
passed from both pre-consolidation and consolidated source schemas. The final
suite also exercises migration reversal/replay, identity collisions, consumed
sequence positions, legacy numeric writers, catalog resume and saved revisions.

Staging refresh preserves numeric evidence and scrubs catalog work in its private
non-serving candidate. Its real restore exposed the preexisting missing-pg_trgm
dependency; the public-schema dump now explicitly includes that extension. See
[PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html).

Models and migration state agree; Django checks, scoped Ruff, whitespace and Ollija
annotation checks passed. Reference inventory, detailed sections and all physical
column names/types/nullability exactly match 149 models and 1,915 columns. Focused
reference changes retain the other schema sections and old inbound anchors.

Local proof is complete. Production sizing, deployment and reader-grant changes
have not been performed. Deployment must drain old HF callers and reapply the
updated source grants, including revoking old scope MAINTAIN privileges before
refresh preflight. The schema can restore HF history; additional-provider catalog
history cannot be represented by the previous HF-only schema.

The historical final pytest command below used `.local/run.py`. The owned helper
now lives at `.context/collection-schema/run.py`; it silently selects this task's
PostgreSQL18 database. Its environment and disposable fixtures have no production
connection. Native implementation ran without independent review or shipping.

```json
{
  "status": "complete",
  "plan_path": "/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation/docs/plans/2026-10-12-105837-feat-collection-schema-consolidation-plan.md",
  "changed_files": [
    "README.md",
    "config/staging_refresh.yaml",
    "core/benchmark_metric_operations.py",
    "core/benchmark_metric_series.py",
    "core/benchmark_metric_store.py",
    "core/benchmark_opencode.py",
    "core/hf_catalog.py",
    "core/migrations/0080_collection_schema.py",
    "core/models.py",
    "docs/operations/staging-data-refresh.md",
    "docs/plans/2026-10-12-105837-feat-collection-schema-consolidation-plan.md",
    "docs/reference/db-schema.md",
    "docs/reference/hf-model-catalog.md",
    "docs/reference/original-content.md",
    "monitor/management/commands/benchmark_opencode_snapshots.py",
    "monitor/management/commands/collect_benchmark_due.py",
    "monitor/management/commands/import_hf_product_catalog.py",
    "monitor/original_content_cutover.py",
    "scripts/staging_refresh/database.py",
    "scripts/staging_refresh/policy.py",
    "tests/staging_refresh/test_database.py",
    "tests/staging_refresh/test_policy.py",
    "tests/test_benchmark_download_db_models.py",
    "tests/test_benchmark_download_operations.py",
    "tests/test_benchmark_download_persistence.py",
    "tests/test_benchmark_forecast_inputs.py",
    "tests/test_benchmark_opencode.py",
    "tests/test_benchmark_use_policy.py",
    "tests/test_collection_schema_consolidation.py",
    "tests/test_collection_schema_migration.py",
    "tests/test_collection_schema_refresh.py",
    "tests/test_hf_catalog_runner.py",
    "tests/test_import_hf_product_catalog.py",
    "tests/test_original_content_retirement.py",
    "docs/analysis/2026-10-12-205234-collection-schema-local-verification.md"
  ],
  "u_ids_attempted": [
    "U14a",
    "U14b",
    "U14c"
  ],
  "u_ids_completed": [
    "U14a",
    "U14b",
    "U14c"
  ],
  "verification_results": {
    "pytest": {
      "passed": 342,
      "warnings": 7,
      "elapsed_seconds": 139.89,
      "required_postgres_executed": 150,
      "required_postgres_skipped": 0,
      "required_postgres_errors": 0
    },
    "postgresql": "18.6 (owned databases on existing local port 55436)",
    "django": "5.2.18",
    "makemigrations_check": "No changes detected",
    "django_system_check": "0 issues",
    "ruff_changed_implementation_and_new_tests": "passed",
    "reference_inventory_columns_types_nullability": "149 tables / 1915 columns; exact",
    "git_diff_check": "passed",
    "ollija_annotation_check": "unchanged; delivery on-request"
  },
  "verification_evidence": [
    {
      "unit": "U14a",
      "behavior_changed": true,
      "existing_tests_inspected": [
        "tests/test_original_content_retirement.py"
      ],
      "tests_added_or_changed": [
        "tests/test_original_content_retirement.py"
      ],
      "tests_used_unchanged": [],
      "red_observed": "Updated retirement assertion failed because earliest_retirement_at and rollback_window_elapsed were still returned; 1 failed/1 passed before timer removal.",
      "verification": {
        "command": "python3 .local/run.py -m pytest tests/test_benchmark*.py tests/test_hf_catalog*.py tests/test_import_hf_product_catalog.py tests/test_collection_schema*.py tests/test_original_content_retirement.py tests/staging_refresh -q --tb=short --basetemp=/Users/fuchitalee/.cache/pw-collection-schema-pytest --create-db",
        "result": "2 retirement tests passed within final 342-test suite"
      },
      "exception_reason": null
    },
    {
      "unit": "U14b",
      "behavior_changed": true,
      "existing_tests_inspected": [
        "tests/test_hf_catalog_runner.py",
        "tests/test_import_hf_product_catalog.py",
        "tests/test_benchmark_download_db_models.py",
        "tests/test_benchmark_download_operations.py",
        "tests/test_benchmark_download_persistence.py",
        "tests/test_benchmark_metrics_rename.py"
      ],
      "tests_added_or_changed": [
        "tests/test_collection_schema_consolidation.py",
        "tests/test_collection_schema_migration.py",
        "affected import/SQL-reference tests"
      ],
      "tests_used_unchanged": [
        "HF persistence/scope/regression-net",
        "benchmark source/history/series/CLI/export/fixtures/engagement/release-response/predecessor/account tests"
      ],
      "red_observed": "Shared-schema test collection initially failed on absent CollectionRun/CollectionObservation imports. Populated restore then caught a RenameModel reverse-state failure; state-only model renames repaired it.",
      "verification": {
        "command": "python3 .local/run.py -m pytest tests/test_benchmark*.py tests/test_hf_catalog*.py tests/test_import_hf_product_catalog.py tests/test_collection_schema*.py tests/test_original_content_retirement.py tests/staging_refresh -q --tb=short --basetemp=/Users/fuchitalee/.cache/pw-collection-schema-pytest --create-db",
        "result": "Populated forward/reverse/replay, UUID collision, overlapping/sparse observation IDs, consumed sequence gaps, original timestamps, Product JSON pointers, old numeric writers/views, saved-run resolution, active-catalog lock refusal and full collector command/client/writer regressions passed."
      },
      "exception_reason": null
    },
    {
      "unit": "U14c",
      "behavior_changed": true,
      "existing_tests_inspected": [
        "tests/staging_refresh/test_policy.py",
        "tests/staging_refresh/test_database.py"
      ],
      "tests_added_or_changed": [
        "tests/test_collection_schema_refresh.py",
        "tests/staging_refresh/test_database.py",
        "tests/staging_refresh/test_policy.py"
      ],
      "tests_used_unchanged": [
        "remaining tests/staging_refresh suite"
      ],
      "red_observed": "Pre-merge count mapping returned old table keys instead of canonical keys. Real restores subsequently failed because a public-schema dump omitted pg_trgm needed by GIN indexes. Explicit extension selection repaired the actual restore.",
      "verification": {
        "command": "python3 .local/run.py -m pytest tests/test_benchmark*.py tests/test_hf_catalog*.py tests/test_import_hf_product_catalog.py tests/test_collection_schema*.py tests/test_original_content_retirement.py tests/staging_refresh -q --tb=short --basetemp=/Users/fuchitalee/.cache/pw-collection-schema-pytest --create-db",
        "result": "Both real PostgreSQL 18 dump/restore/migrate/scrub/check/validate paths passed for source schemas 0079 and 0080. Numeric data survived; catalog work was absent. Source authorization rejects readable legacy catalog data and mixed physical schemas."
      },
      "exception_reason": "The synthetic restore fixture intentionally has no harvested posts, so only required_nonempty_tables is disabled for that fixture. Schema/view/sequence/FK/count/translation/classification/scrub parity checks and real Django migrate/check remain active."
    }
  ],
  "implementation_engine_binding": null,
  "requested_route": {
    "target": "native",
    "harness": "inline"
  },
  "actual_route": {
    "target": "native",
    "harness": "inline"
  },
  "requested_model": null,
  "actual_model": "unverified (native; no external worker receipt)",
  "requested_effort": null,
  "fallback_reason": null,
  "run_id": null,
  "source_kind": "plan",
  "source_digest": "6a8079fe0b420f28e397edad46f1196d6b7016435c684782257481a465a88ed5",
  "unit_receipts": [
    {
      "unit": "U14a",
      "route": "native inline",
      "model": "unverified",
      "detached_process": null,
      "integration": "implemented in canonical isolated worktree",
      "verification": "passed",
      "canonical_commit": null,
      "cleanup": "temporary migration/restore databases dropped; own PostgreSQL18 test database/worktree retained"
    },
    {
      "unit": "U14b",
      "route": "native inline",
      "model": "unverified",
      "detached_process": null,
      "integration": "implemented in canonical isolated worktree",
      "verification": "passed",
      "canonical_commit": null,
      "cleanup": "temporary migration/restore databases dropped; own PostgreSQL18 test database/worktree retained"
    },
    {
      "unit": "U14c",
      "route": "native inline",
      "model": "unverified",
      "detached_process": null,
      "integration": "implemented in canonical isolated worktree",
      "verification": "passed",
      "canonical_commit": null,
      "cleanup": "temporary migration/restore databases dropped; own PostgreSQL18 test database/worktree retained"
    }
  ],
  "plan_checkpoint": null,
  "blockers": [],
  "recovery_path": "/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation",
  "settled_decision_conflicts": [],
  "behavior_change": true,
  "standalone_shipping_skipped": true
}
```
