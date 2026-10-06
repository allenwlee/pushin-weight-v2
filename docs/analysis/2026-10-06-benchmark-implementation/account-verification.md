# Account migration verification — implementation in progress

The retained development database is `pw_benchmark_ready_20261006` on
`127.0.0.1:55436`, PostgreSQL 18.6, on fuchitalee. Production was observed running
PostgreSQL 18.4. The earlier empty PostgreSQL 17 database on port 5432 is not the
current verification target. No production writes, backup, migration or scheduler
change ran.

Migration 0066 applied to a bounded read-only production projection containing
32,144 real X accounts, 74,957 posts, 120,783 post-brand links, 98 brand-account
links, 625 person-account links and 2,048 products. IDs, native author links,
post-brand links, person-account links and product UUIDs match the exported rows.
All ten reference tables have zero mismatches. The projection includes DeepSeek
and GLM posts from August 26 through October 6; its pages were captured separately,
so it is not a transactionally consistent full database backup. Staff name/media
records are excluded and selected-name pointers are null in this projection.

A separate populated fixture rehearsal exercised all ten inbound FK tables,
including the seven not populated by the real-data projection. Replaying the
migration preserved UUIDs. The executable fixture is
`scripts/benchmark_download_collector/rehearse_accounts.py`; it deliberately
requires the dedicated local database `pw_benchmark_migration_20261006` on port
55436, starting empty. Native SQL conflict targets and source-scoped indexes are
also exercised in `tests/test_account_source_identity.py`.

Verification so far:

- 110 account, person, staff, list, verification, duplicate and freshness tests
  passed on PostgreSQL 18 (no skips).
- Extended profile/onboarding/real-cycle/caller tests initially exposed native-ID
  boundaries. After fixes, the 59-test subset had two stale fixture failures;
  the final affected profile file then passed all 10 tests. The previously green
  targeted-extraction, classification and trend-candidate tests remain applicable.
- 29 geography/account/staff tests passed without skips before the PostgreSQL 18
  rehearsal. Older live-shadow tests tied to July 30 row counts were excluded
  from this gate, not treated as passes.
- Django reports no ungenerated model changes; focused import/error lint and
  `git diff --check` passed.

The migration retains native X columns and compatibility triggers. It fails on
unmapped references, bounds lock acquisition, and backfills references in batches
of 5,000 inside one atomic cutover. Transaction failure rolls the whole migration
back; batches are not externally committed checkpoints. Mixed-source reversal is
explicitly prohibited: disable consumers and forward-repair, or restore the
reviewed backup. Broader feature regression, HF compatibility setup and final
review remain outstanding; this is not a tested-and-ready completion receipt.
