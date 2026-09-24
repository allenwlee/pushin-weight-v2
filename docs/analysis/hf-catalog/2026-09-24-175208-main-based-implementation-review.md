# HF catalog main-based implementation review

## Scope and intent

Isolate the HF catalog on `feat/hf-model-product-catalog`, based directly on
`origin/main` at `d5694e7`. Include only manual public model collection, rich
metadata persistence, its additive schema, command, tests, and documentation.
No rare-type commits, verification/review code, schedulers, routes, or harvest
behavior changes belong in this branch.

## Actionable Findings

No unresolved code finding blocks the requested local HF commit. End-to-end
acceptance remains incomplete: Render staging has not run this candidate, and
publisher mappings must be reconciled before claiming every tracked publisher
and all four frontier companies have been covered. This is retained operational
work, not a claim of successful collection.

## Verification

- 260 relevant tests passed on this standalone base; 97 PostgreSQL-required tests
  executed, zero skipped, zero errors. The isolated test database was
  `test_pushinweight_hf_main` on localhost.
- Fresh migration setup and populated 0044 -> 0045 upgrade preserve existing
  Product IDs/repository IDs and raw evidence; 64-bit download values persist.
- Real command -> client -> PostgreSQL -> resume, onboarding -> catalog ->
  onboarding, catalog -> existing classifier catalog, headline Product reference
  -> refresh, and concurrent curated edit -> metadata update were exercised.
- Pagination, caps, private/foreign responses, retries, failed enrichment,
  transactional rollback, scope changes and second-connection lock contention
  have passing coverage. Normal tests use HTTP transports, not live HF calls.
- Django system checks, migration-drift check, scoped handwritten Python lint,
  and whitespace checks passed. Generated migrations retain Django's standard
  class-level lists (RUF012); no unrelated lint cleanup was included.
- Two fixture issues surfaced after isolation and were corrected: frontier
  seed rows can already exist, and headline subjects require both language
  snapshots plus their existing support/identity shape. Assertions were kept.

## Simplification and review coverage

Applied ce-simplify-code and ce-code-review inline as required by the supplied
AGENTS tool mapping. No independent subagent, peer, or external validator ran.
Coverage included correctness, project scope, tests, maintainability, public HTTP
boundaries, migration/data safety, manual-batch resource behavior and recovery.

The isolated implementation uses main's existing stable integer Product ID and
case-insensitive unique repository ID. UUIDs, nullable non-HF identities, curated
Product type, verification proposals, post-release links, and rare-type cycle
integration were excluded. The shared source metadata writer saves only explicit
source columns under a row lock. Main's onboarding already updates only identity
columns; regression coverage confirms it leaves collected metadata intact.

Simplification retained the bounded HTTP client and durable catalog service.
Removed the unused verification-source priority from this standalone writer;
no duplicate compatibility importer was added. No additional behavior-preserving
reuse, quality, or efficiency changes were justified by the final pass.

The migration graph starts at main's 0044 merge, not rare-type migration 0055.
Staging-refresh changes were reconstructed from main and include only the three
HF ledger tables and their two sequences. The policy's migration-graph coverage
tests passed. Products remain copied while run state is excluded and scrubbed.

## Limits and remaining work

The earlier four-request live HF capture and three-Product local import were
performed in the combined checkout. They verify public payloads and historical
collector behavior; they are not standalone staging acceptance. The saved
fixture is reused here, and no new external batch was run during isolation.

A future integration with rare-type work will need an explicit migration-graph
merge and metadata-writer integration review. Neither is included in this
standalone commit. Staging needs the documented bounded import/resume checks;
production deployment and collection still require a separate explicit request.
The repository-wide test suite was not run; testing covers HF, onboarding,
headline lifecycle, staging refresh and Ollija guidance.

## Verdict

Ready for the explicitly requested local HF-only commit. The complete catalog
rollout remains **not complete** until staging and publisher coverage pass.

Local review receipt: `/tmp/compound-engineering-501/ce-code-review/20260924-175208-8feb0d64/report.md`.
