# Collection schema and original-content wait: release review

Reviewed: 2026-10-13T07:27:42.415412+09:00. Base `f43b2904393013107598af3904b78d3be36c76b4`.
Scope: the isolated `feat/collection-schema-consolidation` working tree, including
its new migration, fixtures, tests and delivery plan. The repository requires
sequential work in this thread; no independent or external review is claimed.

The change merges catalog bookkeeping into existing collection storage while
preserving numerical history. The second change removes the seven-day clock
from original-content retirement; actual legacy-writer and restore requirements
remain. Original-content tables and compatibility views are retained.

Correctness, schema/data migration, deployment concurrency, old/new callers,
source permission boundaries, test behavior and scoped maintainability were
reviewed. The migration uses one transaction, catalog-idle guard, explicit
model/table renames, purpose-specific lifecycle checks and ID/pointer mappings.
Numeric old-name callers retain writable, numeric-only views. Numeric history,
known unknown source times, source-use controls and curated Product data remain
separate from mutable catalog enrichment. Scopes retain ownership and cursor
history. Real dump/restore tests cover both 0079 and 0080 source schemas; catalog
work is scrubbed before candidate activation and numeric evidence is retained.

Requirements R1–R9 and units U14a–c have implementation/verification evidence.
Two findings were applied. A P1 deployment dependency appeared in the actual Render
benchmark launcher: its out-of-repository command still imports MetricCollectionRun.
Python aliases preserve that import without additional tables or a schedule change.
The captured-launcher regression failed before the fix and passed afterward.
A test-portability finding was also applied: auxiliary test connections now receive
the configured Django database password. Import-order diagnostics introduced by
model renaming were fixed. No actionable code finding remains. Existing model
lint debt is unchanged (177 diagnostics before and after).

Production preflight observed 196 numeric runs, 122,870 numeric observations,
366,185 values, 20 catalog runs, 47 scopes and 2,407 catalog observations.
Catalog statuses are 15 complete, four partial and one interrupted; no active
catalog lock was observed. Full normalized evidence/ID/table fingerprints are
captured privately and must agree after each authorized migration.

The existing 342-test proof is retained. Delivery/migration checks passed 42
checks, with six required PostgreSQL tests and zero skips/errors. The focused credential follow-up passed four migration/restore tests, with four
required PostgreSQL checks and zero skips/errors. Models/migration checks,
system checks, reference census and whitespace checks pass. This is a completed
code review receipt; live deployment gates remain separate.

Verdict: ready for staging once pre-migration capture completes. No original-
content retirement, collection schedule, provider activation, other worktree,
new permanent table or new job registry belongs to this release.

```json
{
  "status": "complete",
  "scope": "current isolated working tree against origin/main; includes untracked migration/tests",
  "base": "f43b2904393013107598af3904b78d3be36c76b4",
  "branch": "feat/collection-schema-consolidation",
  "artifact_path": "/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation/docs/analysis/2026-10-13-072742-collection-schema-release-review.md",
  "review_mode": "sequential main-thread review required by AGENTS.md",
  "independent_peer": "not run; no external-model/subagent execution",
  "lenses": [
    "correctness",
    "project standards",
    "data migration and integrity",
    "testing",
    "performance of bounded transformations",
    "staging permission boundaries",
    "maintainability",
    "adversarial failure cases"
  ],
  "requirements_verified": [
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "R6",
    "R7",
    "R8",
    "R9"
  ],
  "actionable_findings": [],
  "applied_findings": [
    {
      "severity": "P2",
      "file": "tests/test_collection_schema_migration.py / tests/test_collection_schema_refresh.py",
      "finding": "Additional psycopg connections omitted the configured database password, which fails against password-authenticated test databases.",
      "fix": "Pass the existing Django database password to those test-only connections; do not print/store it."
    },
    {
      "severity": "P1",
      "file": "core/models.py / live Render pushinweight-benchmark launcher",
      "finding": "The service-scoped hourly launcher imports MetricCollectionRun outside the repository. Removing that symbol would break scheduled collection after deployment.",
      "fix": "Keep MetricCollectionRun and MetricObservation as import aliases for the canonical classes. Replay the vetted live launcher against real test storage; no schedule or service command change."
    }
  ],
  "verification": {
    "existing_implementation_suite": "342 passed, 150 required PG tests, zero skips/errors",
    "delivery_and_migration_suite": "42 passed, six required PG tests; current credentials change rechecked in the focused follow-up",
    "lint": "changed Python files pass; core/models.py retains the same 177 baseline diagnostics",
    "models_migrations": "makemigrations --check reports no changes",
    "system_checks": "0 issues",
    "reference": "149 application tables / 1915 columns, exact names/types/nullability",
    "whitespace": "passed",
    "credential_followup": "4 migration/restore checks passed, four required PostgreSQL tests and zero skips/errors",
    "live_launcher": "Captured launcher regression failed on the missing import before aliases, then passed in a 38-test collector suite with 38 required PG checks and zero skips/errors."
  },
  "coverage_limits": [
    "Review was performed in this thread; no independent reviewer/model claimed.",
    "Production/staging migration and actual preservation fingerprints are deployment gates, not claimed by this code-review receipt.",
    "Reverse migration represents HF catalog history only; other-source catalogs require retaining the forward schema."
  ],
  "verdict": "ready for staged deployment once pre-migration baseline capture and active-catalog checks succeed"
}
```
