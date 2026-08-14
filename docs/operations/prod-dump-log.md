# Production DB dump log (pushinweight-db-shadow)

Append-only log of every pg_dump event for the production shadow DB. Entries are never edited; corrections are appended.

Per plan `2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md` U0, every dump must be physically verified: file size, md5 (both ends), and round-trip extractability.

## Connection details

- **DB name**: `pushinweight_shadow`
- **DB id**: `dpg-d9koekqjobas73fvjqng-a`
- **Plan**: `basic_1gb` (Render Postgres)
- **External URL**: `postgresql://pushinweight_shadow:<redacted>@dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com:5432/pushinweight_shadow`
- **Status as of 2026-07-30**: `available`, not suspended, region: oregon

## Storage locations

- `~/.render/cli.yaml` — Render API key (canonical access)
- `~/Downloads/pushinweight-dumps/` — captured dump files on fuchitalee
- This file — event log

## Event log

### 2026-07-30 10:47 UTC (10:47 JST) — Pause-and-dump (start of plan `2026-07-30-002`)

- **Operator**: Claude (per user direction via /goal; auth test passed before dump)
- **Reason**: U0 in combined plan `2026-07-30-002`. Pre-flight safety net before any unit touches production data.
- **Source**: shadow DB external URL (above), direct from fuchitalee.
- **Tool**: `pg_dump --no-owner --no-privileges --format=custom` (custom format, gzip-compressed internally).
- **Capture command**:
  ```
  /opt/homebrew/bin/pg_dump --no-owner --no-privileges --format=custom \
      --file=/Users/fuchitalee/Downloads/pushinweight-dumps/pushinweight-20260730-104308.dump \
      "postgresql://pushinweight_shadow:<redacted>@dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com:5432/pushinweight_shadow"
  ```
- **File**:
  - Path: `/Users/fuchitalee/Downloads/pushinweight-dumps/pushinweight-20260730-104308.dump`
  - Size: **1,986,560 bytes** (1.9 MB compressed; ~10 MB uncompressed when extracted via `pg_restore`)
  - md5: `b239a84573319acf2cbb1b0337f3adab`
- **Schema verification**: `pg_restore --list` returned **366 TOC entries** (130 data-bearing + schema), 30+ public tables (the plan threshold). All four FK-relevant tables present: `posts`, `accounts`, `account_post_appearances`, `brands_accounts`, `companies_accounts`. ✓
- **Round-trip extract verification**: extracted `accounts` + `posts` to `/tmp/partial.sql` via `pg_restore -t accounts -t posts -f /tmp/partial.sql <dump>`. Output: 9,616,347 bytes, 23,187 lines, 1 `COPY public.posts` block, 1 `COPY public.accounts` block. Round-trip confirmed. ✓
- **Row-count snapshot** (live DB at capture time, used for U0 evidence pin):
  | Table | Count |
  |---|---:|
  | posts | 28,822 |
  | accounts | 19,284 |
  | account_post_appearances | 6,803 |
  | brands_accounts | 178 |
  | companies_accounts | 0 |
  | brands | 33 |
  | companies | 30 |
- **TwitterAPI auth check at capture time**: 7/7 sample handles returned integer IDs (sama, DoubaoAI, doubaoai, BytePlusGlobal, bytedanceoss, MiniMax_AI, MiniMaxAgent, hailuo_ai). Auth working at capture time. ✓
- **Verdict**: U0 complete. U1 (BEFORE pins) and U2+ (hybrid funnel ship) can begin.
- **Next event**: Pause confirmation in `pause-and-resume-harvest-cron.md` (suspended via Render REST API at 2026-07-30 10:43 UTC).

## Notes for future sessions

The 1.9 MB compressed size is normal for this sparse shadow DB. The 40 MB number in `project_pushinweight_2026-07-29_recovery_state.md` referred to the **2026-07-28 incident dump** which carried the full v1 SQLite → Django port and a different schema density. Don't compare those sizes.

Custom format (`--format=custom`) is gzip-compressed internally. To inspect raw content, use `pg_restore -t <table> -f <out.sql> <dump>` which writes a plain-SQL file ~5x larger than the dump.