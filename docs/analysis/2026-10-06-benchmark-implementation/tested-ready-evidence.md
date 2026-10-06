# Benchmark database candidate: execution evidence

Endpoint: tested and ready for owner review, with an isolated persistent database
and browser page. No production writes, migrations, schedules or deployment.
Final review and remote CI are recorded below when completed.

## Retained environment

- Worktree: `.worktrees/feat/benchmark-download-collector` on fuchitalee.
- PostgreSQL 18.6: `postgresql://127.0.0.1:55436/pw_benchmark_ready_20261006`.
  Production was observed on PostgreSQL 18.4; this rehearsal matches its major.
- Task-owned cluster: `.local/benchmark-implementation/pg18-data`; shared PG17 on
  port 5432 was left unchanged. The older empty PG17 database is not this evidence.
- Comparison contract: `6124c282-d93c-4e4d-a3ed-6dbae581b672`; taxonomy:
  `dcacf102-006a-4ed6-97b3-f8e413340f76`.
- Preview: <http://fuchitalee:58326/benchmarks/6124c282-d93c-4e4d-a3ed-6dbae581b672/deepseek/?end=2026-10-06>.
  Substitute `glm` for the second product. Opened and title/URL verified in
  Google Chrome on allenwlee. Artifacts and server remain on fuchitalee.
- The projection contains 74,957 posts, 32,144 X accounts, 120,783 post-brand links,
  2,048 products and relevant catalog/ownership rows. Pages were copied read-only;
  this is a bounded projection, not a transaction-consistent production snapshot.
- Two product-type proposals and two confirmed HF namespace/account links were
  applied locally only. Reviewer explicitly says owner review is needed before
  production. Other crosswalk proposals were not silently accepted.

## Implemented units and proof

| Unit | Behavior and verification |
|---|---|
| U10 | Eight initial tables (DataSource and seven taxonomy tables); reviewed graph, stable subjects, frozen group membership, multi-parent merges, two successor paths, manual exclusions and ownership boundaries. Initial three tests were red before implementation; expanded taxonomy tests cover cycles, wrong repository evidence and path deduplication. |
| U12 | Generalized existing Account and all ten inbound references. Native X compatibility columns/triggers preserve old wire identifiers and SQL conflict targets. Six focused account tests, 110 earlier account/caller checks, populated migration receipt and all-ten-FK rehearsal. Old migration tests now use disposable databases before the irreversible account cutover. |
| U5 | Seven shared metric tables. Nine schema tests cover exact integers, finite floats, state/flow timing, protected definitions and raw SQL constraints. Initial model tests failed before the tables existed. |
| U6 | Reviewed immutable source definitions, crosswalk, catalog snapshot and comparison contract. Seven identity tests plus later comparison validation. Provider categories remain a DataSource column; no source_entity or redundant source-type tables. |
| U7 | Bounded manual collection, atomic observations/values, failed envelopes, independent advisory locks, idempotent batches, lease recovery, exact OR totals and optional fourth-provider fixture. Eleven initial persistence tests plus lock/recovery coverage. |
| U13 | Bounded hashed archive manifests, archive publisher/revision/date, independent import time, direct-source precedence and retained revisions. Hash rejection/replay tests and recorded public HF/OR/Arena fixtures. |
| U8 | Fixed-baseline arithmetic: 10→11→13 produces 0%, 10%, 30%; missing/zero/later baselines remain explicit. Fixed cohorts, distinct brand posts, Arena states, complete-publication removal, top-50 omission versus uncollected day. |
| U11 | Literal-span direct attribution and retained legacy brand evidence. Company rollups count a multi-product post once; company-only mentions never become exact product mentions. |
| U14 | Default-off public aggregate page/API, matching existing home access policy. Real URL/template/JSON tests, late-post refresh without caching, five-series real browser proof, mobile/keyboard/scale/source checks. Initial HTTP tests were red on missing routes. |
| U15 | Validated polling/lag/recheck/budget configuration, separate retrieval/publication freshness, gated due-collection command, no registered scheduler. Operations tests were red before implementation; disabled activation and bounded dispatch are tested. |
| U9 | README, recorded fixtures, tracked-brand coverage, CI paths/PostgreSQL18, migration/caller/view regression, review and handoff. Final review/CI pending below. |

## Real data and limits

DeepSeek: exact HF `deepseek-ai/DeepSeek-V4.1-Flash`, OR
`deepseek/deepseek-v4.1-flash-20260910`, Arena `deepseek-v4.1-flash-max` (Max is
explicitly labeled). Launch September 10 is the owner-supplied announcement date.
Brand-wide posts are intentionally broader than those three product measurements.

GLM: HF `zai-org/GLM-5.3-Flash`, OR `z-ai/glm-5.3-flash-20260826`, Arena
`glm-5.3-flash`; launch August 26. Its HF line currently has only the October 6
observation; the later baseline and earlier gap are disclosed.

Real writes in the isolated database include 26 DeepSeek HF archive dates,
11 official Arena product/publication rows (three DeepSeek, eight GLM), direct
current counters for both HF repositories, and OR daily rows for August 26–October 5.
The current OR day is unavailable. DeepSeek Arena begins September 25. Historical
community HF windows keep unknown cutoff/timezone rather than invented midnight.
Original and richer-provenance reimports remain separate evidence; replaying each
manifest is a no-op. Recorded public samples are committed under
`tests/fixtures/benchmark_download_collector/`; private post bodies are not.

[Tracked-brand coverage](tracked-brand-coverage.md) separates the actual 21 enabled
brands, 11 represented in the probed OR top 50 and ten absent. Only the two reviewed
local comparisons are configured; absence never means zero.

## Verification boundaries

- Focused earlier integration: 202 passed, no skips/errors. Later expanded run:
  355 passed, eight subtests passed, one unchanged legacy homepage-filter failure.
  New lock-test harness fix and final focused rerun are recorded below.
- The legacy failure is `test_home_chart_filters_narrow_counts`: expected 1, got 2.
  Both the test and `x_monitor/dashboard.py` have identical Git blobs at base
  `5082ddf7` and candidate (test `accb0760`, implementation `caf3cc8c`). The same
  isolated pure test fails; this feature did not change that filtering contract.
- An overbroad `test_migration_0*.py` run also selected retired v1 SQLite migration
  tests: 72 such failures are outside the live Django/PostgreSQL migration gate.
  Three relevant Django failures exposed historical fixture setup/native-ID
  assertions, were repaired, and passed in the 355-pass expanded run. Unrelated
  retired tests are not reported as passed and were not rewritten.
- Local dump restore and forward migration passed with the full projection counts
  and zero mismatched post authors: [restore receipt](local-restore-receipt.json).
  This is not the required future live production backup.
- Django system check and model/migration drift check pass. Owned Python lint and
  JavaScript syntax checks pass. No typecheck command is configured for these files.
- Browser receipt/screenshots live in `.local/benchmark-implementation/browser/`;
  the owned `verify_pulse_browser` module repeats the real-page checks.
- Homepage Bridgewright declaration validation/prescription passed (5,028 declared
  obligations). The standalone comparison route has no controls in that homepage
  declaration; its dedicated browser checks are the applicable UI proof. No
  homepage candidate/performance assessment is claimed for these new controls.
  Existing home/view regression runs cover the unchanged maintained surfaces.
- Logs/projection/dumps are retained under `.local/benchmark-implementation/`, with
  copied private data excluded from Git. No source credentials appear in receipts.

## Read the database

```sh
export DATABASE_URL=postgresql://127.0.0.1:55436/pw_benchmark_ready_20261006
.venv/bin/python manage.py benchmark_series \
  --contract 6124c282-d93c-4e4d-a3ed-6dbae581b672 --preset deepseek --end-date 2026-10-06
.venv/bin/python manage.py benchmark_collection_health \
  --contract 6124c282-d93c-4e4d-a3ed-6dbae581b672
```

Feature/runtime flags default off. Owner visual approval, production crosswalk
acceptance, a verified live backup and release/activation remain future decisions.
