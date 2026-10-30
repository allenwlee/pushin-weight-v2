# Primary-document release verification review

Scope: current product-release feature worktree, changes after6257cdf2; existing plan's primary-document continuation. This review was performed inline in the same session, following the owner's sequential/session-only instruction. No independent reviewer or external model ran.

Intent: retained primary documents become reusable collection evidence, with source-checked release claims and explicitly reviewed publisher control. Existing Post evidence and native-account ownership requirements remain usable. No automatic collection, inference, production activation or new feature tables/columns.

Checks covered correctness, source/evidence integrity, strict input validation, migration compatibility, replay, shared readers, report links, and the project schema-first/storage rules. Simplification reused the observation projector and attachment path, avoided duplicated Post reads, and kept publication, original capture and import clocks distinct. No further behavior-preserving simplification was warranted.

Findings corrected before delivery:

- The database's sealed instruction grammar also needs the new operation;0208 mirrors the runtime empty-option grammar. Unknown options are rejected by both boundaries.
- Applied0207 must remain in migration history.0208 removes the unwanted Company.url only if empty; a populated value stops the migration before data loss.
- Document-only input must not call the Post loader with an empty list. Mixed source references require exactly one owner.
- Imported capture time is distinct from first database storage. Replay labels imported evidence explicitly and uses the import clock for first-storage selection.
- Normalize optional capture identity fields before hashing so equivalent invocation shapes do not create another import.
- Website control proof must belong to the announcing observation, name its exact URL and retain the source capture. A general research note alone cannot confirm a release. Native repository observations retain the verified CompanyAccount gate.
- Report source names include documents and X accounts, with their own links.

Validation observed:11existing study tests pass before implementation; new command test fails before implementation;116focused/regression/Ollija tests and12subtests pass (44required PostgreSQL tests;0required skips/errors). After the clock/report changes,31focused tests pass (28required PostgreSQL;0skips/errors). Migration reverse/reapply, empty-column removal and nonempty-column refusal are verified on the permanent shared database under its lock. Model/migration-state check reports no changes. Changed Python files pass Ruff; whitespace check passes. Initial setup errors (script import path and missing synthetic created_at) were corrected before the migration assertions succeeded; they are not passing checks.

Remaining limits: source and publisher assessments are supplied by this session, not unattended truth detection. Saved documents do not prove original historical availability at an exact second. Individual creators, stable-account reconciliation and hosted-access vocabulary remain deferred. This verifies the bounded continuation, not the entire unfinished acquisition/TN plan. Staging result, exact deployed revision and browser report validation remain separate delivery observations.
