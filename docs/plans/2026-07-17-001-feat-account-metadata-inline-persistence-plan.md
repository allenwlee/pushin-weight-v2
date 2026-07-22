---
title: "Persist TwitterAPI.io author metadata inline to accounts table"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
date: 2026-07-17
type: feat
module: "x_monitor.store (upsert_account) + x_monitor.apify (_normalize_tweet)"
---

## Summary

TwitterAPI.io's `/twitter/tweet/advanced_search` and `/twitter/tweets` responses already include a rich `author` object — `followers`, `following`, `verifiedType`, `profilePicture`, `favouritesCount`, `statusesCount`, `mediaCount`, `description`, `profile_bio`, `createdAt`, `location`, `isBlueVerified` — but only `display_name` and `verified` are persisted to `accounts` via `upsert_account`. The rest is dropped.

This plan adds a single migration (`039_accounts_inline_metadata.sql`) extending `accounts` with the inline author metadata, wires `_normalize_tweet` to surface the full set, and routes `upsert_account` to read the new fields. **No new API calls** — the data is already in every tweet response. Per-post capture is out of scope (accounts table is the single source of truth; last fetch wins, idempotent via `ON CONFLICT DO UPDATE`).

## Problem Frame

`x_monitor/run.py` calls `TwitterApiClient.advanced_search` and `tweets(tweet_ids)` to fetch posts. Both endpoints return a nested `author` object on each tweet. The current `_normalize_tweet` (`x_monitor/apify.py:524-584`) extracts `author_followers_count`, `author_verified`, `author_name`, and `author_id`, then `RunPipeline.execute` passes the normalized dict to `Store.upsert_account`. But `upsert_account` (`x_monitor/store.py:1329-1412`) only consumes `handle`, `display_name`, and `verified` from that dict. The follower count, following count, verified type, profile picture, location, and all the engagement counts get dropped at the INSERT OR UPDATE.

Verified live against `data/runs/raw/20260715T091026_0000-2ad50d2d/*_account_acct.json` — every tweet author object in the canonical 09:10 run carries the full field set, including `Hailuo_AI` (the first row) with `followers: 74109`, `following: 575`, `favouritesCount: 12642`, `statusesCount: 5250`, `mediaCount: 282`, `fastFollowersCount: 0`, `isBlueVerified: true`, `verifiedType: "Business"`, `profilePicture: "https://pbs.twimg.com/..."`, `description: ""`, `location: "San Francisco"`, `createdAt: "Tue Sep 03 13:11:12 +0000 2024"`.

The `accounts` table (`x-monitoring/data/x_monitoring.db`) currently has `author_id`, `handle`, `display_name`, `bio`, `bio_fetched_at`, `verified`, `bio_contains_brand`, `first_seen_at`, `last_seen_at`, `source_query_ids`, `notes`, `bio_en`, `bio_zh_cn` — but no engagement, no profile metadata, no fetch timestamp for the inline fields.

## Goal Capsule

A single migration adds 13 columns to `accounts`; `_normalize_tweet` exposes them in the normalized dict; `upsert_account` persists them. The 15-min pipeline cycle will then accumulate engagement metrics on tracked accounts for free, with zero extra credit spend and zero new endpoints. Operators can query `SELECT handle, followers_count, followers_fetched_at FROM accounts ORDER BY followers_fetched_at DESC LIMIT 50` to see who's trending now.

## Requirements

| ID | Statement |
|---|---|
| R1 | Add 13 new columns to `accounts`: `followers_count INTEGER`, `following_count INTEGER`, `favourites_count INTEGER`, `statuses_count INTEGER`, `media_count INTEGER`, `fast_followers_count INTEGER`, `is_blue_verified INTEGER`, `verified_type TEXT`, `profile_picture TEXT`, `location TEXT`, `description TEXT`, `profile_bio_text TEXT`, `followers_fetched_at TEXT` (latter captures last-write timestamp for the engagement+profile bundle). |
| R2 | Extend `_normalize_tweet` to surface all 13 fields from `author` on every tweet response. Defensive defaults: missing/null → 0 / None / "" / False as appropriate per field type. |
| R3 | Extend `upsert_account` to read the new fields from the caller's kwargs and write them via `INSERT OR REPLACE INTO accounts` with `ON CONFLICT(author_id) DO UPDATE`. Existing rows must not be wiped — use `COALESCE(excluded.X, accounts.X)` for non-engagement fields and direct assignment for engagement counters (last fetch wins, the data is fresh). |
| R4 | Schema image regeneration: re-render `docs/reference/images/xmonitor-schema-post-batch.png` from the updated `docs/reference/schema.dot` and co-commit per repo convention. |
| R5 | Reference doc updates: `docs/reference/db-schema.md` (live section) reflects the new columns; `docs/research/2026-06-17-105855-top-100-llm-brands.md` lines 132-133 (`api.fxtwitter.com` / `api.twstalker.com` recipe) can be retired — no longer needed. |
| R6 | Test coverage: (a) migration applies cleanly on a fresh DB; (b) `upsert_account` writes all 13 new fields on a fresh row; (c) `upsert_account` updates engagement counters on conflict but preserves stale `bio_*` columns when excluded values are NULL; (d) `_normalize_tweet` produces all 13 fields for a representative tweet shape. |
| R7 | Idempotency: re-running the same migration is a no-op (use `IF NOT EXISTS` / `ALTER TABLE` guards). |

## Scope Boundaries

**In scope:**
- 1 SQL migration adding 13 columns
- 1 edit to `_normalize_tweet` (extend return dict)
- 1 edit to `upsert_account` (extend INSERT, extend ON CONFLICT clause)
- Regenerate schema image + commit `.dot` and `.png` together
- Update `db-schema.md`
- New test file or extend existing

**Out of scope:**
- Per-post follower capture on `posts.author_followers_count` — accounts table is the single source of truth, last fetch wins (per user direction).
- New TwitterAPI.io endpoint — `/twitter/user/info` already returns these fields inline in tweet responses.
- New CLI command — these are populated automatically on every run.
- Daily refresh cadence — the 15-min cycle already keeps `followers_fetched_at` current (the per-tweet upsert updates the timestamp).
- `bio_fetched_at` migration — out of scope; the existing bio path is unchanged.
- `accounts.id` integer FK refactor (migration 031 already retired `author_id` → `accounts_id`; this plan doesn't touch that surface).
- Re-pulling historical data — the plan only persists forward from when it ships.

## Key Technical Decisions

**KTD1: Migration 039 vs amending the latest existing migration.** New file `039_accounts_inline_metadata.sql`. Reason: migrations are immutable once applied (per repo convention); live DB is at v38 and the new columns land as v39.

**KTD2: Engagement columns nullable + zero default, profile columns nullable + empty string default.** Reason: pre-existing `accounts` rows (1,522 v1.7-cycle rows per `docs/research/2026-06-25-130000-seed-report.md` line 208) will not have these populated until the next pipeline cycle re-fetches their author. Letting the columns be nullable avoids a backfill step. `COALESCE(excluded.X, accounts.X)` on the ON CONFLICT path lets pre-existing stale rows keep their old values for non-engagement fields until a fresh write arrives.

**KTD3: `verified` and `is_blue_verified` are separate columns.** TwitterAPI.io returns both `isVerified` (legacy checkmark) and `isBlueVerified` (X Premium / paid checkmark) in the author object. The existing `accounts.verified` column carries `isBlueVerified OR isVerified` per the normalizer at `apify.py:579-581`. New `is_blue_verified` column stores `isBlueVerified` specifically so operators can distinguish paid verification from legacy checkmark status. The existing `verified` column continues to carry the union (backward-compatible with `x-monitor relevance audit-handles` which checks `verified == True`).

**KTD4: `verified_type TEXT`, no enum constraint.** The API returns values like `"Business"`, `"Government"`, `""` (none). String column is simpler than an enum + lookup table for a field that rarely matters operationally.

**KTD5: `profile_bio_text TEXT`, separate from existing `accounts.bio`.** The existing `bio` column is populated by a separate `bio_fetched_at` workflow (operator-initiated per `audit-handles`); it carries the canonical English-translated bio. `profile_bio_text` is the raw `author.profile_bio.description` field from inline tweet responses — lower fidelity but free. Operators who want the rich bio continue to use the existing `bio` path.

**KTD6: `description TEXT` separate from `profile_bio_text`.** TwitterAPI.io returns `description` (top-level, often empty) and `profile_bio.description` (nested, rich). Both can be null. Storing both gives operators choice.

**KTD7: `followers_fetched_at TEXT` covers the engagement+profile bundle as a whole.** Single timestamp per row update. Sufficient for the operator question "is this fresh?" — finer-grained per-field timestamps would inflate column count without operator value.

**KTD8: `_normalize_tweet` adds new keys, store ignores unknowns.** The current normalizer already drops unknown keys at the store layer (per the existing pattern). Adding the new fields to the normalizer return dict is additive; callers that don't read them get nothing. No risk of breaking existing pipelines.

**KTD9: Test isolation via `Store(auto_migrate=False)`.** Same pattern as `test_cmd_main_siblings.py` — bypass migration 034's canonical brand-keyword seed. For this plan's tests, the migration is the migration under test, so the test must run with `auto_migrate=True` and then explicitly invoke `store.apply_migrations()` to apply 039 (or use a synthetic schema).

## Implementation Units

### U1. Migration: add 13 columns to `accounts`

**Goal:** Forward-only SQL migration adding the engagement + profile metadata columns to `accounts`.

**Files:**
- Create: `x-monitoring/x_monitor/migrations/039_accounts_inline_metadata.sql`
- Modify: `docs/reference/schema.dot` (add columns to the `accounts` table node)
- Regenerate: `docs/reference/images/xmonitor-schema-post-batch.png` via `scripts/build_schema_image.sh`
- Modify: `docs/reference/db-schema.md` (live section, lines 47-66 area — reflect the new columns)

**Approach:** SQL only. Each column is `ALTER TABLE accounts ADD COLUMN <name> <type>` guarded by `IF NOT EXISTS` (SQLite supports `ADD COLUMN` without `IF NOT EXISTS` natively; wrap each in a check via `PRAGMA table_info` if needed, or use the idempotency-via-pragma pattern from prior migrations). The KTD7 `expected_artifacts:` header per repo convention. Bump `_migrations` to v39 with the artifact digest.

**Test scenarios:**
- Migration applies cleanly on a fresh DB (no prior tables): `python -c "from x_monitor.store import Store; Store('fresh.db', auto_migrate=True)"` succeeds, `PRAGMA table_info(accounts)` shows all 13 new columns.
- Migration is idempotent: applying twice is a no-op (no `duplicate column` error).
- Pre-existing DB at v38 upgrades to v39 without data loss: existing `accounts` rows survive the migration; new columns are NULL.

**Verification:** `sqlite3 data/x_monitoring.db "SELECT version FROM _migrations ORDER BY version DESC LIMIT 1"` reports 39. `sqlite3 data/x_monitoring.db ".schema accounts"` lists all 13 new columns.

**Dependencies:** none (first unit).

### U2. `_normalize_tweet` extension

**Goal:** Surface all 13 inline author metadata fields in the normalized tweet dict so `upsert_account` can consume them.

**Files:**
- Modify: `x-monitoring/x_monitor/apify.py` (the `_normalize_tweet` return dict at lines 546-584)
- Modify: `x-monitoring/x_monitor/store.py` (`upsert_account` signature at lines 1329-1412; INSERT and ON CONFLICT clauses)

**Approach:** Add 13 new keys to the return dict with defensive defaults (0 / None / "" / False per type). Extend `upsert_account` to accept the new fields as kwargs, extend the INSERT column list and VALUES list, extend the ON CONFLICT DO UPDATE clause with `COALESCE(excluded.X, accounts.X)` for non-engagement fields and direct assignment for engagement counters. `is_blue_verified` is the boolean-or of the API field; convert via `int(bool(...))` for the INTEGER column.

**Test scenarios:**
- `_normalize_tweet` produces all 13 fields for a representative tweet (synthetic input matching the live `Hailuo_AI` shape). Each field has the right type and value.
- `_normalize_tweet` produces safe defaults for an empty/missing `author` dict — all engagement fields → 0, all string fields → "" / None.
- `upsert_account` writes all 13 new fields on a fresh row (`ON CONFLICT` doesn't fire).
- `upsert_account` updates engagement counters on conflict (`is_blue_verified`, `followers_count`, etc. take the new value).
- `upsert_account` preserves stale `bio_*` columns when excluded values are NULL (the COALESCE pattern).
- `upsert_account` idempotent re-fetch updates `followers_fetched_at` even when engagement values are unchanged.

**Verification:** A live dry-run + a live DB query showing the new columns populated for a recent fetch.

**Dependencies:** U1 (column existence required for store writes).

**Patterns to follow:** `x-monitoring/tests/test_cmd_main_siblings.py` — `Store(auto_migrate=False)` for isolation; create `accounts` table schema manually in the test fixture, then exercise `upsert_account` directly.

### U3. Reference doc updates + smoketest

**Goal:** Update reference docs to reflect the new columns and retire the superseded external-recipe reference.

**Files:**
- Modify: `docs/reference/db-schema.md` (live section — extend the `accounts` column table)
- Modify: `docs/research/2026-06-17-105855-top-100-llm-brands.md` (lines 132-133: mark the `api.fxtwitter.com` / `api.twstalker.com` recipe as superseded — pipeline now provides follower counts inline)
- Modify: `x-monitoring/tests/classifier_tests/` — add a smoketest doc mirroring the convention from `20260715T091026_0000-2ad50d2d-cmd-run-cleanup-smoke.md` (named `20260717T<HHMMSS>_0000-<runhash>-account-metadata-persistence-smoke.md`)

**Approach:** Doc-only edits. Update the `db-schema.md` accounts column table with the 13 new columns and a one-line note that they're populated inline from tweet responses. Add a "superseded by inline persistence" cross-reference at the top of the 2026-06-17 research note. After running the live integration assertion (U2's live verification), persist the smoketest doc to `tests/classifier_tests/`.

**Test scenarios:**
- (No code tests — doc verification is human-readable; verify by reading the diff.)

**Verification:** `git diff --stat docs/reference/ docs/research/` shows only the intended files. Live smoke run produces a populated accounts row.

**Dependencies:** U2 (need the live integration to write the smoketest doc against).

## Risks & Dependencies

**Risk 1: Migration 039 fails on the live DB.** Pre-existing DBs at v38 may have a different `accounts` schema than the test fixtures (e.g., if a partial migration was applied and rolled back). Mitigation: use `PRAGMA table_info(accounts)` guards per column before `ALTER TABLE ADD COLUMN`, matching the pattern from migrations 031 and 037.

**Risk 2: `ON CONFLICT DO UPDATE` semantics on engagement counters may overwrite stale data with `NULL`.** If a tweet response has `followers = null` (rare but possible — see `isAutomated` accounts), the new write would null the existing count. Mitigation: use `COALESCE(excluded.followers_count, accounts.followers_count)` for the engagement counters too, OR convert nulls to 0 in `_normalize_tweet` before the write. KTD2 picks the latter — `_normalize_tweet` defaults to 0 for missing engagement fields.

**Risk 3: `accounts.id` INTEGER PK is the FK target for `brands_accounts.accounts_id`.** The 13 new columns are nullable TEXT/INTEGER, not PK-related. No impact on the FK relationship. Verified by reading `x-monitoring/x_monitor/store.py:1387-1400`.

**Risk 4: Performance — `upsert_account` is called per-tweet.** Each write is a single-row `INSERT OR REPLACE` + an `INSERT INTO brands_accounts` — adding 13 columns is constant overhead per row. At ~17-35 inserted posts per cycle (per the 09:10 smoketest), this is negligible. No new index needed.

## System-Wide Impact

- **Dashboard (`x_monitor/dashboard.py`):** no change required. Dashboard already queries `accounts`; new columns are additive.
- **Run summary JSON (`x_monitor/run.py`):** no change. The summary reflects per-call results, not per-account metadata.
- **Launchd agents:** no change. The 15-min cycle automatically accumulates the new data; no new cadence required.
- **Manual kill switch (`/tmp/x-monitor-paused`):** unchanged.

## Documentation Plan

- `docs/reference/db-schema.md` — live section update (U3)
- `docs/research/2026-06-17-105855-top-100-llm-brands.md` — supersede marker (U3)
- `x-monitoring/tests/classifier_tests/20260717T<runhash>-account-metadata-persistence-smoke.md` — new smoketest (U3)

## Future Considerations

- **Per-post follower capture:** if operators want follower-count-over-time analysis, a `posts.author_followers_count` column would enable it. Out of scope per user direction; revisit if the engagement-trend question becomes operational.
- **Backfill of historical accounts:** 1,522 pre-existing `accounts` rows have NULL for the new columns until the next time those authors appear in a tweet fetch. Could be backfilled via a one-shot script that iterates `SELECT DISTINCT author_id FROM posts` and re-fetches. Out of scope; the pipeline does this naturally over time.
- **Refresh cadence:** the 15-min cycle already keeps `followers_fetched_at` current. If operator needs finer-grained follower tracking (e.g., minute-by-minute), that requires a dedicated scheduler — out of scope.

## Open Questions

None — the user has confirmed scope (maximum coverage, accounts-only path).

## Deferred to Follow-Up Work

- Re-pull historical `accounts` rows (backfill via `SELECT DISTINCT author_id FROM posts` + re-fetch). Naturally resolves over time as the pipeline encounters each author.
- Add `posts.author_followers_count` for per-post historical capture (would enable follower-over-time charts).
- Retire the v1.6 `apply_skip_order` / `queries_per_model` dead loop and the `config.py:48` `VALID_QUERY_IDS` Literal/validator — already noted in `memory/2026-07-13-q-retirement-status.md`.
