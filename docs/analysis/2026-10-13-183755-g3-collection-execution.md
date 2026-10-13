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

## U3 — Bounded GitHub Metadata and Evidence

The public GitHub client uses the existing budget/transport machinery and retained official REST documentation for API version `2026-03-10`. Host/path-checked pagination, independent credential-free request construction, an optional exact project credential, per-invocation request/time/byte limits and pinned small-file reads preserve the public metadata boundary. Rate-limit responses become a durable cooldown rather than an unbounded retry queue.

The collector checkpoints publisher identity, repository pages, releases, tags, commits and pinned tree/file metadata through the fenced shared writer. It retains repository creation, release publication and commit author/committer clocks separately. Family mappings do not multiply source event records. A conditional 304 reuses its matching saved page and continues pagination, retaining original payload provenance. A late response after another claim cannot write evidence or progress.

The CLI inspects without writes or client construction by default. Registration creates a disabled source/paused job; there is no schedule activation. The metadata-file allowlist excludes weights and executable code.

Evidence: metadata-client and catalog tests initially failed on absent modules. Existing transport characterization passed forty-one cases before its shared request/body refactor. Latest combined run passed sixty-five cases, with nineteen required PostgreSQL cases executed and none skipped. Tests exercise page-two recovery, distinct release/commit records, true source clocks, a 304 with retained inventory, rate-limit checkpoint/cooldown, stale-response rejection and command-to-client-to-database behavior. GitHub fixtures are explicitly deterministic examples derived from the documented response schema, not claimed live response captures. No real provider batch or production/staging write was run.

## Remaining Work

Mid-implementation simplification ran the ce-simplify-code reuse, quality and efficiency rubrics sequentially inline, following project AGENTS.md; no independent reviewer was invoked. One quality improvement replaces the ownership helper's nested conditional expression with explicit branches; guards, errors and behavior are preserved. Two low-value reuse/query changes were skipped because they risk weakening trust-boundary checks or changing error behavior. No repository type-check command is configured; scoped Ruff checks pass. A separate strengthened command-chain test failed on a commit SHA being used as a tree SHA; the collector now requests the explicitly recorded native tree SHA, validates the tree response and continues to pin file reads to the commit. Eighteen identity/client/catalog tests then passed, including thirteen PostgreSQL cases. This is a correctness refinement under U3, not a behavior-preserving simplification claim.

## U4 — Frozen Cohort and Native Model Inventories

The database-backed planner validates a twenty-one-brand scope and freezes up to one hundred qualified models per brand after reviewed HF mirror deduplication. It sorts native creation timestamps descending with product UUID ties, chooses the earliest supported first-party HF repository among mirrors, permits qualified API-only OpenRouter or dedicated GitHub dates, and leaves family-repository/Arena/unknown dates unranked. All four providers receive identical immutable model/cohort/ownership pins in paused jobs. Missing types/dates and the limits of the observed public inventory remain explicit.

Native HF creation enumeration reuses the existing public metadata client and product projection inside shared checkpoint transactions. The default lastModified path is unchanged. The official Hugging Face SDK source verified the native createdAt sort translation. OpenRouter's documented model catalog uses offset/limit/model_authors; its IDs, canonical slugs and listing-created clocks are retained independently of ranking model_permaslug. Both inventory paths persist evidence/checkpoints in existing tables. An API-only creation test verifies that no OpenRouter date/name/SHA is written to HF-shaped Product fields.

Evidence: absent cohort/inventory modules and the HF sort argument produced expected red failures. Additional call-chain assertions caught the OpenRouter author-filter parameter mismatch, an inherited fake key/query parameter on an injected HF client, and the missing GitHub User-Agent. The corrected requests use the documented filter, independent public headers/query parameters and a valid application User-Agent. Current official primary sources were inspected; only tests used mock transports, no live model inventory ran.

Latest combined cohort/native-inventory/HF-client/HF-catalog/GitHub-client/legacy-source run: ninety-two passed, twenty-one required PostgreSQL cases executed, none skipped. It covers company-wide caps across two namespaces, mirrors before caps, earliest creation, deterministic ties, all twenty-one reports, frozen per-source equality, family-date rejection, Google exclusion and actual adapter-to-DB paths. Source registration and all campaign jobs remain inactive by default.

## U5 — Bounded History and Sparse Archive Admission

HF commit/tree metadata and GitHub release/tag/commit/tree/file evidence traverse public clients and fenced database checkpoints. HF history is pinned to a recorded head revision; GitHub trees use recorded tree identities. Neither path downloads model weights. Reviewed immutable HF archive coordinates reuse range acquisition, store selected JSON and range hashes before import, and retain separate publisher/revision/snapshot/retrieval clocks. Optional numeric admission requires a real reviewed contract and its selected products. Single-snapshot chunks preserve sparse dates, explicit zero and missing fields; no daily interpolation occurs.

OpenRouter/Arena publication windows are acquired through shared database jobs and projected onto reviewed provider identifiers. Repeated model jobs reuse the same window evidence. OpenRouter's pre-2025 interval and absent top-50 rows remain gaps; `other` is never assigned to a missing model. Arena requires a frozen supported text configuration. Coverage evaluations remain qualified, not assertions of complete public history.

Evidence: eighteen history/acquisition/import tests passed, including eleven required PostgreSQL tests, none skipped. Native HF resume and GitHub pinned-tree call chains use mock transports. A real parquet range fixture traverses archive acquisition through numeric writing; zero persists, absent all-time remains absent under a reviewed v2 contract, and replay uses DB evidence without another request. Older required-field contracts remain unchanged. No real historical batch ran.

## U6 — Shared Dispatch and Explicit Scheduling Handover

Due dispatch uses UTC slots, attempt cooldowns and shared finite request/time/byte ceilings. Numeric work retains priority. Paused registration alone preserves legacy benchmark dispatch; explicit `take_metric_authority` records the job pointer in existing DataSource metadata. Afterwards the legacy entrypoint routes through that authority, including when paused, so it cannot silently fall back. External Render-cron X jobs never enter shared due dispatch. Content claims still require explicit caller authorization and do not depend on the unrelated metric-source enabled flag.

The benchmark command's job-aware path fetches outside database transactions and writes numeric observations/values under the shared claim fence. Successful writing and job pointers finish atomically; existing unregistered writer behavior and metric hashes remain valid.

Evidence: forty-six scheduler/budget/state/legacy-persistence/operations tests passed, forty-two required PostgreSQL cases executed, none skipped. They exercise the actual shared command-to-benchmark-command-to-source-to-writer chain, legacy scheduling handover, UTC daily slots, cooldowns, aggregate request exhaustion and external X driver exclusion. A subsequent stale-response test explicitly pauses a job inside the transport callback and verifies that no values survive the rejected fence.

## U7 — Read-Only Collection Reports

Shared service/CLI reports distinguish attempt and success clocks, expired claims,
empty success, unknown usage and pending scoped work. Cohort jobs without an
optional JSON role remain visible. Reports retain date precision and bounded
evidence references, redact credential fields and omit lease tokens.

Evidence: three PostgreSQL report tests exercise actual CLI/service parity,
separate health clocks, missing usage, scope location and legacy JSON redaction.

## U8 — Schema, Copy and Compatibility Verification

The copy policy classifies collection_jobs as copied/optional-source state. Its
scrubber pauses all copied jobs, clears runtime intent and catalog/content
attempt pointers before deleting excluded runs/scopes/observations, and retains
numeric references. Actual PostgreSQL dump/restore/migrate/scrub tests pass from
both older and current sources. Current readers in the older migration test now
run after the forward migrations; historical models and writable compatibility
aliases still verify the original merge/restore behavior.

Schema census confirms exactly one added table, no retirements/renames, and a
complete reference inventory of 150 application tables/1,935 physical columns.
Both evidence-preserving reverse guards execute. Django checks and migration
drift checks pass. The shared runtime/API reference and X handover describe actual
implemented behavior, including explicit caller authority for content claims.

Final refinements keep physical HF bytes cumulative, preserve the legacy source
advisory lock before paid dispatch, roll back failed scheduling handovers, charge
shared publication requests once, select source-dated file revisions before the
frozen cutoff and preserve completed UTC day selection across cutoff offsets.
Reviewed OpenRouter publications also traverse numeric admission; `other` does
not become selected-model usage. Real HF public visibility is not inferred from
Git commit dates.

Combined verification: **394 passed; 165 required PostgreSQL cases executed,
zero skipped**, using the isolated local database, PostgreSQL 17 dump tools and
mock provider transports. The focused command covers shared jobs/state/identity/
schema/migration/copy/scheduling/budgets/reports, GH, HF, cohorts/history and legacy
benchmark/OpenCode/backfill/staging-refresh regression paths. Two initial command
attempts used nonexistent test filenames and ran zero tests; they are not evidence.
The corrected command passed. No live provider batch, schedule activation,
staging/production database write or deployment occurred.

## Remaining Integration

G3-owned U1–U8 are locally implemented and verified. U9 runtime integration remains
owned by the X/backfill session; its current staging JSON pilot proceeds independently.
The whole nine-unit plan remains incomplete until that owner supplies actual
scheduled/manual/backfill adapter evidence. G3's selected delivery endpoint is an
open pull request with CI decided, not deployment or a real historical batch.

## Final Review and Follow-up

The final simplify/review passes used the project-required sequential inline route;
no independent reviewer or peer-model request ran. The configured Claude CLI route
uses a different provider credential, so it was not invoked or changed. The durable
[review receipt](2026-10-13-225202-g3-collection-review-followup.json) records eight
source-validated findings and their bounded corrections.

New regression counterexamples failed for GitHub alias ordering, history and catalog
resumes after public visibility changed, draft release retention, a Google company
alias, and malformed HF pagination. They now pass. Repository aliases retain a
separate latest reviewed name; public eligibility is rechecked before continuation;
unpublished releases are removed from observation/page evidence while still counting
against response budgets. Cohort exclusion follows company relations. HF history
rejects an unparseable advertised next page. Historical orchestration is separated
into native evidence, archive admission, publication acquisition and cohort validation
modules while keeping its public imports.

The collector workflow now runs the new shared collection/provider/history regressions
on PostgreSQL. Its expanded lint command passes. No repository type-check command is
configured. Repository-wide Ruff is not green because of existing findings; five new
mutable-class annotations were corrected without changing migration operations.
Browser testing is not applicable: this diff changes no route, view, template, browser
interaction, script or style. Additional compounding documentation was skipped because
the reasoning is already carried by code, tests, plan and the runtime reference.

The expanded local regression net passed **398 tests, including 168 required PostgreSQL
cases and no skips**, in 141.27 seconds. After the last related GitHub catalog fixes,
the targeted native/provider/history suite passed **72 tests, including 34 PostgreSQL
cases and no skips**, in 5.45 seconds. Existing migration/restore verification remains
valid because those operations were not changed by the final catalog refinements.

One initial workflow reproduction omitted DATABASE_URL; the runner correctly rejected
it as incomplete (179 required PostgreSQL tests skipped). It is not passing evidence.
The corrected run explicitly uses the task's isolated local PostgreSQL database.

The exact configured CI test selections both pass locally after all final code
changes: the existing collector group passed **301 tests, including 179 required
PostgreSQL cases**, in 84.57 seconds; the new shared collection group passed
**94 tests, including 84 required PostgreSQL cases**, in 82.47 seconds. Neither
skipped a required database test. The expanded CI lint command passes too.
