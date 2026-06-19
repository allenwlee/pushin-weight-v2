# {{AGENT_ATTRIBUTION}}
# Migration 004: Company/Brand/Account model — operator deploy + rollback runbook

> **Last verified against:** `feat/v1.8-company-brand-account-model` on `2026-06-19`.
> If the migration SQL, the plan, or the deploy scripts have changed since this date, re-verify all POST-NN queries against a fresh dryrun before running on the live DB.
>
> **Source of truth:**
> - Plan: `~/development/minimax-marketing/docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md`
> - Migration SQL: `x_monitor/migrations/004_company_brand_account_model.sql`
> - Baseline: `~/development/minimax-marketing/x-monitoring/data/x_monitoring.db` (19 MB, 2,008 posts, 0 accounts, 0 apa, `_migrations` MAX(version) = 3)
> - SQLite: 3.51.0 (target: ≥ 3.39 for `ALTER TABLE DROP COLUMN`)

---

## TL;DR

- **What it does:** Replaces the `model_id` + `signal` columns on `posts` with a normalized 4-table model: `companies`, `brands`, `brand_companies`, `brand_accounts`, `company_accounts`, `post_brands`, `post_mentions`, `post_brand_signals`, plus the 3 detection-registry tables (`brand_hashtags`, `brand_keywords`, `brand_search_terms`).
- **Why:** Removes the per-post single-brand assumption; lets a post belong to N brands with weight conservation; moves signal classification from a denormalized column into a per-brand table.
- **Rollback guarantee:** Atomic DB file backup taken immediately before the live migration. A single `cp` restores the pre-migration state in <30 seconds. The migration is one transaction, so a mid-deploy failure leaves the DB unchanged.
- **Downtime:** ~5 minutes (1 min migration + 30 s verification + 1 min reattribute + dashboard restart).
- **Risk:** P0 (live DB mutation). Execute the dryrun first, run the 24 POST-NN queries, then deploy.

---

## Prerequisites (verify BEFORE the deploy)

The operator must confirm each of the following on `fuchitalee` before the live deploy window opens.

- [ ] **PRE-01** — Worktree exists at `~/development/minimax-marketing/worktrees/v18` on branch `feat/v1.8-company-brand-account-model`.
  ```bash
  git -C ~/development/minimax-marketing worktree list | grep v18
  ```
- [ ] **PRE-02** — Migration 004 SQL file exists and is syntactically valid.
  ```bash
  test -f ~/development/minimax-marketing/worktrees/v18/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql
  sqlite3 :memory: < ~/development/minimax-marketing/worktrees/v18/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql && echo "SQL parses"
  ```
- [ ] **PRE-03** — All 11 `data/brands/<brand>/detection.yaml` files exist (Unit 7 done).
  ```bash
  ls ~/development/minimax-marketing/x-monitoring/data/brands/*/detection.yaml | wc -l   # expect 11
  ```
- [ ] **PRE-04** — Disk ≥ 500 MB free on the data volume.
  ```bash
  df -m ~/development/minimax-marketing/x-monitoring/data   # Avail column ≥ 500
  ```
- [ ] **PRE-05** — SQLite ≥ 3.35 (the project is on 3.51.0).
  ```bash
  sqlite3 --version
  ```
- [ ] **PRE-06** — Baseline row counts captured.
  ```bash
  sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db <<'SQL'
  SELECT 'posts', COUNT(*) FROM posts;                      -- expect 2008
  SELECT 'posts_with_signal', COUNT(*) FROM posts WHERE signal IS NOT NULL;     -- expect 0
  SELECT 'posts_with_author_id', COUNT(*) FROM posts WHERE author_id IS NOT NULL; -- expect 0
  SQL
  ```
- [ ] **PRE-07** — 297 tests pass on the feature branch BEFORE the migration PR merges.
  ```bash
  cd ~/development/minimax-marketing/worktrees/v18/x-monitoring
  .venv/bin/python -m pytest tests/ -q
  ```
  The 2 pre-existing `test_headlines` failures are unrelated and expected.
- [ ] **PRE-08** — Plan reviewer findings (P0/P1 from the 2026-06-19 review pass) are closed. See the revision history at the top of the plan file.
- [ ] **PRE-09** — `x_monitor/config.py` brand list matches 11 + `_unattributed` = 12 entries.
  ```bash
  grep -E "^\s*'[a-z_0-9]+'," ~/development/minimax-marketing/worktrees/v18/x-monitoring/x_monitor/config.py | wc -l
  ```

---

## Pre-deploy checklist (Go / No-Go)

Run the 9 PRE-NN checks above. **If ANY fails, STOP.** Do not proceed to the dryrun or the live migration until the failure is resolved.

- [ ] PRE-01 worktree exists
- [ ] PRE-02 migration SQL valid
- [ ] PRE-03 11 detection.yaml files
- [ ] PRE-04 ≥ 500 MB free disk
- [ ] PRE-05 sqlite ≥ 3.35
- [ ] PRE-06 baseline captured
- [ ] PRE-07 tests green
- [ ] PRE-08 review findings closed
- [ ] PRE-09 brand count = 12

---

## Dryrun procedure (BLOCKING — must complete before live)

```bash
# 1. Copy the live DB to /tmp
cp ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db /tmp/x_monitoring.dryrun.db
ls -lh /tmp/x_monitoring.dryrun.db   # expect ~19 MB

# 2. Apply migration 004 to the dryrun (expect ≤ 5 s)
sqlite3 /tmp/x_monitoring.dryrun.db < \
  ~/development/minimax-marketing/worktrees/v18/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql

# 3. Run all 24 POST-NN verification queries (see next section) against /tmp/x_monitoring.dryrun.db

# 4. If ANY query fails, STOP. Investigate the migration SQL, fix, restart from PRE-02.

# 5. On success, save the dryrun's sha256 as the live DB's expected post-migration sha256 (sanity)
shasum -a 256 /tmp/x_monitoring.dryrun.db > /tmp/expected-post-004.sha256
```

---

## Deploy procedure (live DB) — 12 steps

```bash
# Step 1: confirm the cron pipeline is not currently running
launchctl list | grep com.fuchitalee.x-monitor.scheduled

# Step 2: stop the cron pipeline
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist

# Step 3: stop the dashboard (kill-by-port, NEVER `pkill -f DashboardApp`
#         per feedback_pkill_matches_all_dashboardapp.md)
lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill

# Step 4: atomic backup
TS=$(date -u +%Y%m%dT%H%M%SZ)
cp ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db \
   ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db.pre-004.${TS}.bak
shasum -a 256 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db \
   > /tmp/pre-004.${TS}.sha256
echo "TS=$TS  backup=$TS.bak"   # record this for the rollback section

# Step 5: backup integrity check (expect `ok`)
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db.pre-004.${TS}.bak \
  'PRAGMA integrity_check;'

# Step 6: apply migration 004 to the live DB (expect ≤ 5 s)
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db < \
  ~/development/minimax-marketing/worktrees/v18/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql

# Step 7: verify the _migrations ledger shows version 4
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db \
  'SELECT version, applied_at FROM _migrations ORDER BY version;'

# Step 8: run all 24 POST-NN verification queries — STOP and rollback if any expectation fails

# Step 9: backfill attribution for the existing 2,008 posts
cd ~/development/minimax-marketing/x-monitoring && \
  .venv/bin/python -m x_monitor reattribute \
    --since $(sqlite3 data/x_monitoring.db 'SELECT MIN(created_at) FROM posts')

# Step 10: restart the cron pipeline
launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist

# Step 11: start the dashboard on :5000
cd ~/development/minimax-marketing/x-monitoring
nohup .venv/bin/python -m x_monitor dashboard --port 5000 \
  > ~/Library/Logs/x-monitor/dashboard.log 2>&1 &

# Step 12: wait 30 s, then check the stderr log for stale-code errors
sleep 30
tail -50 ~/Library/Logs/x-monitor/stderr.log
# must show NO `OperationalError: no such column` or `no such column: model_id`
```

---

## Post-deploy verification queries (run all 24 on the live DB)

Every expectation is for the state **after** migration 004 + `reattribute` has run.

```sql
-- POST-01: confirm new tables exist
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
-- Expected: includes _migrations, account_post_appearances,
-- accounts, brand_accounts, brand_companies, brand_hashtags,
-- brand_keywords, brand_search_terms, brands, companies,
-- company_accounts, post_brand_signals, post_brands,
-- post_mentions, posts, search_queries
```
```sql
-- POST-02: brands seeded to 12 rows
SELECT COUNT(*) FROM brands;   -- Expected: 12
```
```sql
-- POST-03: companies seeded
SELECT COUNT(*) FROM companies;   -- Expected: 10..13
```
```sql
-- POST-04: no posts lost
SELECT COUNT(*) FROM posts;   -- Expected: 2008
```
```sql
-- POST-05: model_id column gone
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='model_id';   -- Expected: 0
```
```sql
-- POST-06: signal column gone
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='signal';   -- Expected: 0
```
```sql
-- POST-07: favorite_count renamed to like_count
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='favorite_count';   -- Expected: 0
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='like_count';       -- Expected: 1
```
```sql
-- POST-08: like_count populated
SELECT COUNT(*) FROM posts WHERE like_count IS NOT NULL;   -- Expected: 2008
```
```sql
-- POST-09: post_brands populated post-reattribute
SELECT COUNT(*) FROM post_brands;   -- Expected: 2008+
```
```sql
-- POST-10: post_brand_signals backfilled
SELECT COUNT(*) FROM post_brand_signals;
-- Expected: ≈ number of posts that had a non-NULL posts.signal pre-migration
-- (likely 0 in current prod — signal was never populated;
-- the per-brand classifier populates this on the next cycle)
```
```sql
-- POST-11: post_mentions populated post-reattribute
SELECT COUNT(*) FROM post_mentions;   -- Expected: 4000+
```
```sql
-- POST-12: translation indexes have new predicates (incl. 'und')
SELECT name, sql FROM sqlite_master WHERE type='index'
AND name LIKE 'idx_posts_text_%';
-- Expected: idx_posts_text_en_backfill and idx_posts_text_zh_cn_backfill
-- with WHERE ... NOT IN (..., 'und')
```
```sql
-- POST-13: new attribution indexes exist
SELECT name FROM sqlite_master WHERE type='index'
AND name LIKE 'idx_post%';
-- Expected: idx_post_brands_brand, idx_post_brands_brand_post,
-- idx_post_mentions_brand_source_recent, idx_post_mentions_post,
-- idx_post_brand_signals_brand_signal, idx_post_brand_signals_post
```
```sql
-- POST-14: post_brands schema correct (no is_primary)
PRAGMA table_info(post_brands);
-- Expected: brand_id, post_id, weight; PK(brand_id, post_id)
```
```sql
-- POST-15: post_mentions schema with 4 source categories
PRAGMA table_info(post_mentions);
-- Expected: post_id, brand_id, source, raw_token, mentioned_at;
-- PK(post_id, brand_id, source)
```
```sql
-- POST-16: accounts recreated with author_id PK + bio columns, role DROPPED
SELECT name FROM pragma_table_info('accounts')
WHERE name IN ('author_id','handle','bio','bio_fetched_at','role');
-- Expected: author_id, handle, bio, bio_fetched_at present; role ABSENT
```
```sql
-- POST-17: detection tables seeded from detection.yaml
SELECT COUNT(*) FROM brand_hashtags;   -- Expected: >0 (~30-100)
SELECT COUNT(*) FROM brand_keywords;   -- Expected: >0 (~50-100)
```
```sql
-- POST-18: brand_search_terms seeded from queries.yaml
SELECT COUNT(*) FROM brand_search_terms;   -- Expected: 30..80
```
```sql
-- POST-19: ledger advanced to 4
SELECT MAX(version) FROM _migrations;   -- Expected: 4
```
```sql
-- POST-20: _unattributed is sentinel
SELECT is_sentinel FROM brands WHERE brand_id='_unattributed';   -- Expected: 1
```
```sql
-- POST-21: lang_detected backfilled for translated posts
SELECT COUNT(*) FROM posts
WHERE (text_en IS NOT NULL AND lang_detected IS NULL)
   OR (text_zh_cn IS NOT NULL AND lang_detected IS NULL);
-- Expected: 0
```
```sql
-- POST-22: degraded_accounts.json exists if any backfill warnings
test -f ~/development/minimax-marketing/x-monitoring/data/runs/$(ls -t ~/development/minimax-marketing/x-monitoring/data/runs/ | head -1)/degraded_accounts.json \
  && cat ~/development/minimax-marketing/x-monitoring/data/runs/$(ls -t ~/development/minimax-marketing/x-monitoring/data/runs/ | head -1)/degraded_accounts.json
-- Expected: file exists; may be empty [] if all posts had author_id
```
```sql
-- POST-23: reattribute produced rows
SELECT COUNT(DISTINCT post_id) FROM post_brands;
-- Expected: 2008 (or close — some posts may have been marked _unattributed and skipped)
```
```sql
-- POST-24: weight conservation
SELECT post_id, SUM(weight) FROM post_brands GROUP BY post_id
HAVING ABS(SUM(weight) - 1.0) > 0.001;
-- Expected: 0 rows (allow 0.001 epsilon for floating-point drift)
```

---

## Rollback procedure (10 steps, ~5 minutes)

Use this procedure if **any** of the POST-NN queries fails, or any of the P0/P1 rollback triggers fires during the 24h monitoring window. The `TS` value is the timestamp recorded in deploy step 4.

```bash
# 1. Stop the cron pipeline
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist

# 2. Stop the dashboard
lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill

# 3. Restore the DB from the atomic backup taken in deploy step 4
cp ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db.pre-004.${TS}.bak \
   ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db

# 4. Verify the restored DB integrity
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db 'PRAGMA integrity_check;'
# expect: ok

# 5. Verify the ledger rolled back
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db 'SELECT MAX(version) FROM _migrations;'
# expect: 3

# 6. Code rollback (revert the migration PR, or check out the pre-migration SHA)
cd ~/development/minimax-marketing
git checkout main
git revert <migration-004-merge-commit>
# (or: git checkout <pre-migration-sha>)

# 7. Restart the cron pipeline
launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist

# 8. Start the dashboard back up (deploy step 11)
cd ~/development/minimax-marketing/x-monitoring
nohup .venv/bin/python -m x_monitor dashboard --port 5000 \
  > ~/Library/Logs/x-monitor/dashboard.log 2>&1 &

# 9. Smoke test
curl -s -o /dev/null -w 'HTTP %{http_code}\n' --max-time 5 http://127.0.0.1:5000/
# expect: HTTP 200

# 10. Total rollback time: ~5 minutes
```

After rollback, file a postmortem noting which POST-NN query or MON-NN alert triggered the rollback, attach the backup file path, and keep the `.pre-004.${TS}.bak` file on disk until the issue is root-caused.

---

## Monitoring (first 24h post-deploy)

Check these 10 metrics during the first 24 hours. Each has a concrete threshold that triggers investigation (P1) or immediate rollback (P0).

| ID | Metric | Threshold | Action |
|---|---|---|---|
| MON-01 | `stderr.log` shows `no such column` / `OperationalError` | any occurrence | **ROLLBACK** (pipeline on stale code) |
| MON-02 | `post_brands` row count after 1h | < 100 | investigate Unit 4 / reattribute |
| MON-03 | `post_mentions` row count after 1h | < 500 | 4-source extraction broken |
| MON-04 | `GET /` and `GET /grid` HTTP code | non-200 | investigate |
| MON-05 | `GET /brand/<id>` HTTP code for all 11 brands | any non-200 | investigate |
| MON-06 | `SUM(weight) GROUP BY brand_id` | all zeros after 4h | investigate weight computation |
| MON-07 | `launchctl list \| grep com.fuchitalee.x-monitor.scheduled` | process missing | restart pipeline |
| MON-08 | `posts` row count growth | zero growth in 24h with cron active | investigate pipeline |
| MON-09 | `post_brand_signals` distribution by signal | all zeros after 4h | per-brand classifier not running |
| MON-10 | DB file size | > 25 MB within 24h | investigate unexpected growth |

Quick checks:

```bash
# MON-01: tail the stderr log
tail -100 ~/Library/Logs/x-monitor/stderr.log | grep -E "no such column|OperationalError" || echo "clean"

# MON-02 / MON-03: attribution row counts
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db \
  "SELECT 'post_brands', COUNT(*) FROM post_brands;
   SELECT 'post_mentions', COUNT(*) FROM post_mentions;"

# MON-04 / MON-05: dashboard reachability
curl -s -o /dev/null -w 'HTTP %{http_code}\n' --max-time 5 http://127.0.0.1:5000/
for brand in minimax qwen deepseek kimi doubao yi glm wenxin hunyuan; do
  curl -s -o /dev/null -w "HTTP %{http_code}  /brand/$brand\n" --max-time 5 "http://127.0.0.1:5000/brand/$brand"
done

# MON-06: weight conservation
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db \
  "SELECT brand_id, ROUND(SUM(weight), 3) FROM post_brands GROUP BY brand_id ORDER BY 2 DESC LIMIT 5;"

# MON-07: launchd process
launchctl list | grep com.fuchitalee.x-monitor.scheduled

# MON-08: posts growth
sqlite3 ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db \
  "SELECT DATE(fetched_at), COUNT(*) FROM posts GROUP BY 1 ORDER BY 1 DESC LIMIT 7;"

# MON-10: DB file size
ls -lh ~/development/minimax-marketing/x-monitoring/data/x_monitoring.db
```

---

## Failure indicators + rollback triggers

### P0 — rollback immediately

- `stderr.log` shows `no such column: model_id`, `no such column: signal`, or `no such column: favorite_count` → **pipeline on stale code, ROLLBACK**
- `pragma_table_info('posts')` shows `model_id` or `signal` while `_migrations MAX(version) = 4` → **partially applied migration, ROLLBACK**
- Dashboard returns 500 on `/brand/<id>` routes → **ROLLBACK**
- `PRAGMA integrity_check` returns anything other than `ok` → **corruption, ROLLBACK IMMEDIATELY from backup**

### P1 — investigate, rollback if not resolved in 30 min

- `post_brands` empty after 1h of pipeline runs → Unit 4 / `reattribute` not running
- `pytest tests/` fails after deploy → code/schema mismatch

### P2 — investigate, non-blocking

- `post_brand_signals` empty after 4h → per-brand classifier not running; treemap shows "no data"

---

## Operator notes

- **Plan:** `~/development/minimax-marketing/docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md`
- **Migration SQL:** `~/development/minimax-marketing/worktrees/v18/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql`
- **Live DB:** `~/development/minimax-marketing/x-monitoring/data/x_monitoring.db`
- **Live DB backup (post-deploy):** `~/development/minimax-marketing/x-monitoring/data/x_monitoring.db.pre-004.${TS}.bak`
- **Dryrun DB (pre-deploy, can be deleted after success):** `/tmp/x_monitoring.dryrun.db`
- **LaunchAgent plist (cron, on fuchitalee):** `~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist`
- **LaunchAgent plist (WatchPaths, on fuchitalee):** `~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist`
- **Pipeline logs:** `~/Library/Logs/x-monitor/scheduled-{stdout,stderr}.log`
- **Dashboard log:** `~/Library/Logs/x-monitor/dashboard.log`
- **Run JSONs:** `~/development/minimax-marketing/x-monitoring/data/runs/<run_id>.json`
- **Run summary:** `~/development/minimax-marketing/x-monitoring/data/runs/LATEST.json`

### On-call reference

- The plan file contains a 24h window: confirm that the deploy window is during the operator's working hours (not Friday evening or weekend).
- The dashboard is on `0.0.0.0:5000` Tailscale — operators on the tailnet can verify in a browser at `http://fuchitalee:5000/`.
- If the live migration aborts mid-transaction, `_migrations` will NOT have row 4. A re-run is a no-op (the migration uses `IF NOT EXISTS` guards). Investigate the partial state, then re-run after the fix.
- The atomic backup in deploy step 4 is the single point of recovery. Verify it BEFORE applying the migration (step 5 integrity check). If the backup fails integrity, STOP and re-derive the backup before continuing.
