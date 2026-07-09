# Plan 005 U3 dry-run report — exact rows that will land in the DB

**Generated:** 2026-07-09
**Operator action:** review before running steps 2 and 3 of the rollout
**Source plan:** `docs/plans/2026-07-09-001-feat-list-yaml-db-sync-plan.md` U3
**Dryrun DB:** `x-monitoring/data/x_monitoring.db.dryrun-mig033.20260709T075121Z.db` (74M copy of live `x_monitoring.db` with migration 033 applied + seed script run)
**Backup of live DB:** `x-monitoring/data/x_monitoring.db.pre-list-yaml-plan.20260709T070538Z.bak` (74M, sha256 `fa702dbaa30d637e6df78a972b09fae678a5239accebf3be14842727e404a13e`)

## Important finding — read this first

**Migration 033 is a NO-OP against the current live DB.** All 7 brands_companies rows it would insert already exist in the live schema. This is consistent with migration 030/031 having pre-seeded these edges, or with a prior apply of an earlier draft. Either way, the migration is safe to run — `INSERT OR IGNORE` skips existing PKs.

**The seed script creates new state** (10 placeholder accounts + 14 new brands_accounts rows). See breakdown below.

---

## Step 2 — Migration 033 (`033_seed_sibling_brands_companies.sql`)

### What the migration says it does
Insert 7 brands_companies rows for sibling brands split by migration 030:

```sql
INSERT OR IGNORE INTO brands_companies (brand_id, company_id) VALUES
    (doubao,   bytedance),
    (seed,     bytedance),
    (chatglm,  zhipu),
    (sensenova, sensetime),
    (step,     stepfun_inc),
    (kwaiyii,  kuaishou_co),
    (wenxin,   baidu);
```

### What would actually happen on the live DB today

**0 rows inserted. 0 rows modified. No-op.**

Pre-existing state in live DB:

| brand_id | brand | company_id | company |
|---|---|---|---|
| 15 | doubao | 14 | bytedance |
| 23 | chatglm | 11 | zhipu |
| 24 | sensenova | 15 | sensetime |
| 25 | step | 8 | stepfun_inc |
| 26 | kwaiyii | 18 | kuaishou_co |
| 27 | wenxin | 2 | baidu |
| 28 | seed | 14 | bytedance |

All 7 rows already exist. `INSERT OR IGNORE` skips them on PK match.

### Verification after step 2

```bash
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_companies;"
# expected: 23 (was 15 + 7 new = 22, but seed already created 1 via prior apply)
# OR: 22 (if no prior apply happened and migration 033 actually inserts 7)
```

**Pre-flight for operator:** if the count is already 22 or 23 BEFORE running migration 033, the migration is a no-op. If it's 15, migration 033 will add 7 and bring it to 22. Either way is safe.

---

## Step 3 — `scripts/seed_list_handles_to_db.py`

The script accepts a (handle, company, role) table. With no `--input` flag, it uses the operator-confirmed 10 triples from plan 005 U3. It calls TwitterAPI.io `/twitter/user/by/username/<handle>` to fetch the real numeric `author_id`; if that returns 401 (the live state on 2026-07-09 — OAuth2 user-context token dead), it falls back to `author_id = lowercased handle` as a placeholder.

The dryrun below used `--no-api` to match the fallback path. The 10 rows shown here are what would land if you ran the script today without fixing the auth.

### What the seed script would actually add

**10 new accounts rows** (case-preserved as written in the YAML table):

| author_id (placeholder) | handle | display_name | first_seen_at |
|---|---|---|---|
| `bytedanceoss` | `bytedanceoss` | *(blank)* | 2026-07-09 07:51:56 |
| `carolglms` | `carolglms` | *(blank)* | 2026-07-09 07:51:56 |
| `chujiezheng` | `chujiezheng` | *(blank)* | 2026-07-09 07:51:56 |
| `doubaoai` | `doubaoai` | *(blank)* | 2026-07-09 07:51:56 |
| `hailuo_ai` | `hailuo_ai` | *(blank)* | 2026-07-09 07:51:56 |
| `liulicheng10` | `liulicheng10` | *(blank)* | 2026-07-09 07:51:56 |
| `mertunsal2020` | `mertunsal2020` | *(blank)* | 2026-07-09 07:51:56 |
| `stepfunai` | `stepfunai` | *(blank)* | 2026-07-09 07:51:56 |
| `xuanmingzhangai` | `xuanmingzhangai` | *(blank)* | 2026-07-09 07:51:56 |
| `zrdianjiao` | `zrdianjiao` | *(blank)* | 2026-07-09 07:51:56 |

**Why display_name is blank:** the operator has not collected actual display_name data from x.com for any of these 10 handles. The placeholder `author_id = lowercased handle` path used by `seed_list_handles_to_db.py --no-api` does NOT call TwitterAPI.io's `/2/users/by/username/<handle>` endpoint, so the real `name` field from x.com is unavailable. Inserting `display_name = handle` would fabricate a value from the handle string — which is wrong (handles are not display names; e.g. `@hailuo_ai` might display as "Hailuo AI" on x.com, not literally `hailuo_ai`). The script (`x-monitoring/scripts/seed_list_handles_to_db.py` line 237) now inserts `display_name = ''` and operator can backfill via a follow-up UPDATE once the TwitterAPI.io auth path is restored.

**Caveat — `DoubaoAI` already exists.** The live DB has an `accounts` row with `author_id='1856750484977324034'` and `handle='DoubaoAI'`. The plan uses handle `doubaoai` (all lowercase) for the new row. These are different author_ids (real numeric vs placeholder), so both rows will coexist. This means the brand yaml will surface both:

- `DoubaoAI` → doubao (official) [real, pre-existing]
- `doubaoai` → doubao (official) [placeholder, new]

The regen script will pick the first enabled_models match per handle — both end up in `doubao.yaml`. Operator should consolidate by deleting the placeholder row once the auth path is fixed, OR by editing the seed table to use `DoubaoAI` (capitalized) as the handle so it merges with the existing row.

**14 new brands_accounts rows** (cross-product of handle × company-owned brands):

| handle | brand | role | source |
|---|---|---|---|
| `DoubaoAI` | doubao | official | **pre-existing** (real author_id `1856750484977324034`) |
| `DoubaoAI` | seed | official | **pre-existing** |
| `bytedanceoss` | doubao | official | new |
| `bytedanceoss` | seed | official | new |
| `carolglms` | chatglm | staff | new |
| `carolglms` | glm | staff | new |
| `chujiezheng` | qwen | staff | new |
| `doubaoai` | doubao | official | new (placeholder; real `DoubaoAI` also has this row) |
| `doubaoai` | seed | official | new (placeholder; real `DoubaoAI` also has this row) |
| `hailuo_ai` | minimax | official | new |
| `liulicheng10` | step | staff | new |
| `liulicheng10` | stepfun | staff | new |
| `mertunsal2020` | mistral | staff | new |
| `stepfunai` | step | official | new |
| `stepfunai` | stepfun | official | new |
| `xuanmingzhangai` | qwen | staff | new |
| `zrdianjiao` | chatglm | staff | new |
| `zrdianjiao` | glm | staff | new |

That's 18 rows total when including the 2 pre-existing `DoubaoAI` rows. The plan's verification query (`brands_accounts for 10 new handles ≥ 10`) returns 18, matching.

### Duplication note — `doubaoai` vs `DoubaoAI`

The lowercase `doubaoai` placeholder and the pre-existing `DoubaoAI` (real author_id `1856750484977324034`) both have `brands_accounts` rows for `doubao` and `seed`. After step 3, `doubao.yaml` will list both handles as the official ByteDance Doubao account. **The regen script (step 4) will surface this duplication.** Operator has two options:

- **Option A:** Delete the placeholder row after step 3:
  ```sql
  DELETE FROM brands_accounts WHERE accounts_id = (
    SELECT id FROM accounts WHERE author_id = 'doubaoai'
  );
  DELETE FROM accounts WHERE author_id = 'doubaoai';
  ```
  Then re-run the regen. `DoubaoAI` is the canonical row.

- **Option B:** Edit the seed script's DEFAULT_SEED to use `handle="DoubaoAI"` (capitalized) for that triple. Re-running the seed script will insert with author_id=`doubaoai` again (since the placeholder path fires), but a follow-up migration could UPDATE the placeholder to the real numeric id once auth is fixed.

For now, plan 005 ships the placeholder approach (matches migration 032's pattern); operator cleanup is a future-step task.

---

## Summary — what to expect after both steps

| Table | Before | After step 2 | After step 3 |
|---|---|---|---|
| `brands_companies` | 15 | 22 or 23 (no-op if rows pre-exist) | 22 or 23 |
| `accounts` | 1587 | 1587 (no-op) | 1597 (+10) |
| `brands_accounts` | 83 | 83 (no-op) | 99 (+16) |

**Rollback target:** the `.pre-list-yaml-plan.20260709T070538Z.bak` backup is the source of truth for reverting. If anything looks wrong after steps 2+3, restore from that backup and the DB returns to pre-step-2 state.

**Suggested operator review order:**

1. Read this file end-to-end.
2. Sanity-check the 10 placeholder accounts and the 16 new brands_accounts rows above.
3. Decide on the `DoubaoAI` vs `doubaoai` duplication handling (Option A or B).
4. If green, run step 2 (migration 033) and step 3 (seed script) per the rollout procedure in the plan.
5. Run step 4 (regen script) and the U5 parity test to confirm the yaml↔DB drift closes.

**Cleanup:** the dryrun DB at `data/x_monitoring.db.dryrun-mig033.20260709T075121Z.db` is gitignored (matches the `.bak` pattern in the repo's `.gitignore`) and can be deleted when review is complete.