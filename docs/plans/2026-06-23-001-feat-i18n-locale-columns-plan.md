---
title: "feat: i18n — per-locale columns + lookup tables for enum translation"
type: feat
status: active
date: 2026-06-23
target_repo: minimax-marketing (code under `x-monitoring/`)
---

# feat: i18n — per-locale columns + lookup tables for enum translation

## Overview

Add per-locale display columns (en + zh-CN) to the registry tables (`accounts`, `companies`, `brands`, and `products` if/when HF migration 005 lands) plus lookup tables for the four enum columns whose user-facing labels need translation (`post_brand_signals.signal`, `brand_accounts.role`, `company_accounts.role`, `accounts.engagement_tier`). The dashboard already has a session-level locale toggle (`?locale=` query param + cookie + topbar buttons) shipped in v1.7 — this plan extends the existing toggle to drive the new columns without inventing new UX.

The locale toggle must be **fast and seamless** for both zh-CN and en users. The lookup-table shape gives a single `JOIN locale_keys ON (key, locale)` per render, cached in app memory at startup.

## Problem Frame

x-monitor's audience is bilingual: today's dashboard is English-only with implicit assumption that all users read English. Three concrete problems block a zh-CN user:

1. **Card titles are hardcoded** in `x_monitor/dashboard.py:38-50` as `MODEL_DISPLAY_NAMES = {"minimax": "MiniMax AI", ...}` — never read from the DB at all. Even if `brands.display_name` had a zh-CN column today, the dashboard would still render the English constant.
2. **Signal labels are hardcoded** in `x_monitor/static/trend-chart.js:23-31` as `SIGNAL_LABELS = {release: "Q1 release", ...}` — same problem; the JS would need to be regenerated per locale.
3. **Role labels render raw English** in `x_monitor/templates/model_detail.html.j2:83-89` (`{% for role, count in role_counts.items() %}`). No localization layer exists.

Without translation, a zh-CN speaker sees English card titles, English signal labels, and English role labels. The v1.7 translation work shipped `posts.text_en`/`text_zh_cn` for post bodies only — registry rows (which display on every card render, every page load) were not in scope.

## Requirements Trace

- **R1** — Add `display_name_en` + `display_name_zh_cn` columns to `accounts`, `companies`, `brands`. Existing `display_name` becomes the **fallback/source** (no rename; keep for back-compat).
- **R2** — Add `bio_en` + `bio_zh_cn` columns to `accounts`. Source `bio` (TEXT, nullable) stays as fallback.
- **R3** — Add `display_name_en` + `display_name_zh_cn` to `products` (deferred to post-HF-merge; see Sequencing below).
- **R4** — Create lookup tables for enum i18n: `signal_types`, `role_types`, `engagement_tier_types`. Each has columns `(key, locale, label)` with composite PK `(key, locale)`.
- **R5** — Convert existing enum columns from convention-only TEXT to FKs pointing at the lookup tables (preserving current values: `release/community_question/criticism/commenter_capture/praise/other` for signal; `official/community/researcher/press/community` for role; `low/medium/high` for engagement_tier). Apply the FK hot-path guard (intersect-before-INSERT) on every write path.
- **R6** — Reuse the existing translator (Claude Haiku 4.5, batch=20, idempotent UPDATE) to populate the new free-form `_en`/`_zh_cn` columns. Source: existing `display_name` (en seed) and `bio` (source locale, sometimes zh-CN already).
- **R7** — Add dashboard helpers `_pick_i18n_text(row, column_name, locale)` and `_pick_enum_label(enum_family, value, locale)` that mirror the existing `_pick_text(post, locale)` pattern. Reuse the existing `?locale=` query param + `locale` cookie + `POST /api/set_locale` flow (already shipped in v1.7; do not re-implement).
- **R8** — Update `dashboard.py` to read brand display names from DB (via `_pick_i18n_text(brands, "display_name", locale)`) instead of the `MODEL_DISPLAY_NAMES` Python constant. The Python constant is kept as the **seed source** for the backfill (the migration seeds `brands.display_name` from it, the translator fills `_en`/`_zh_cn`).
- **R9** — Forward-only migration: existing rows get DEFAULT NULL on the new columns. The dashboard falls back to the existing `display_name` (en source) when the locale column is NULL — same pattern as v1.7's post-text fallback.
- **R10** — Seed all 6 signals, 5 roles, 3 engagement tiers across both locales (`en`, `zh_cn`) in the migration; one INSERT per (key, locale).
- **R11** — Tests cover: migration is idempotent on re-apply; FK guard drops unknown values to the dead-letter log; `_pick_i18n_text` falls back to source column when `_en`/`_zh_cn` are NULL; `_pick_enum_label` returns en label when zh_cn missing and vice versa; dashboard renders the correct column for `?locale=zh-CN`.

## Scope Boundaries

- **In scope:** translation columns on registry tables, lookup tables for enum i18n, dashboard helpers, translator extension for new free-form columns.
- **Out of scope:**
  - **Plural_plural N-to-N table renames** (`brand_accounts` → `brands_accounts`, etc.) — **deferred** to a separate plan per the chronology decision. The convention is already the de-facto standard for new M:N tables (no existing tables violate it); a bulk rename would require touching every FK edge and the dashboard.
  - **text-PK → integer-PK rewrites** — **deferred**. `accounts.author_id` is a deliberate v1.8 choice (immutable opaque X user id; survives re-rolls that integer surrogates don't). `brands.brand_id`/`companies.company_id` are likewise deliberate. A PK rewrite breaks 7+ FK edges and triggers ON DELETE CASCADE rewrites; cost > benefit without a concrete query that needs integer arithmetic.
  - **Japanese / Korean / other locales** — v1.7 explicitly deferred these; this plan stays en + zh-CN.
  - **Headline translation** — `headline` column stays en-source (per v1.7 R6).
  - **Handle/mention translation** — handles are `@`-identifiers, canonical, not translated.
  - **Translator prompt changes for compound locales** — out of scope; v1.7's Haiku prompt handles en↔zh-CN bidirectionally.

## Context & Research

### Relevant Code and Patterns

- `x-monitoring/x_monitor/translator.py` (262 lines) — the existing translation infrastructure. `translate_batch(tweets, target_locales, client, *, brand_names=None, dry_run=False)` is the public API. Batch size 20; exponential backoff; idempotent UPDATE. Extend with `translate_registry_rows(table, column, target_locales, client, ...)` that mirrors the same shape but for `display_name` / `bio` instead of `text`.
- `x-monitoring/x_monitor/store.py`:
  - `_apply_migration` runs `executescript(sql)` then writes `_migrations` (migration loader auto-applies; SQL must NOT touch `_migrations`).
  - `bulk_update_translations` (`store.py:515`) and `get_posts_missing_translations` (`store.py:565`) — pattern to mirror for `bulk_update_translations_<col>` and `get_<table>_missing_translations_<col>`.
  - `_known_brand_ids()` (`store.py` per memory `feedback_xmonitor_fk_hot_path_2026-06-20`) — the FK-guard pattern; mirror as `_known_signal_values()`, `_known_role_values()`, `_known_engagement_tier_values()`.
- `x-monitoring/x_monitor/dashboard.py`:
  - `SUPPORTED_LOCALES = ("en", "zh-CN", "zh_cn")` at line 76.
  - `_LOCALE_TO_COLUMN = {"en": "en", "zh-CN": "zh_cn", "zh_cn": "zh_cn"}` at line 79.
  - `normalize_locale(locale)` at line 88.
  - `_pick_text(post, locale)` at line 111 — canonical pattern; mirror as `_pick_i18n_text(row, col, locale)`.
  - `serialize_grid_card(..., display_locale="en", ...)` at line 317 — already accepts `display_locale`; thread it into more render paths.
  - `_resolve_locale()` priority `?locale=` > cookie > `"en"` at line 602.
  - `MODEL_DISPLAY_NAMES` Python dict at line 38-50 — to be replaced by DB-backed reads via `_pick_i18n_text(brands, "display_name", locale)`.
  - `POST /api/set_locale` route at line 881 — already exists; no new endpoint needed.
- `x-monitoring/x_monitor/migrations/003_translation_columns.sql` — the direct precedent. Forward-only, no backfill in SQL, partial indexes with `WHERE <col>_en IS NULL` for backfill driver.
- `x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql` — `BEGIN`/`COMMIT` wrapper, idempotent `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE`, FK with `ON DELETE CASCADE`/`SET NULL`. The only CHECK constraint in the whole schema is `post_brand_signals CHECK (brand_id <> '_unattributed')` (line 131); no enum CHECK constraints exist today.
- `x-monitoring/x_monitor/templates/grid.html.j2` line 5 `<html lang="{{ active_locale.split('-')[0] }}">` and lines 42-50 (topbar locale switcher) — already correct; no template changes for the toggle.
- `x-monitoring/x_monitor/templates/_model_card.html.j2` — renders `p.display_text | brand_colorize` with class `source-fallback` when `p.is_translated == false`; mirror the badge for `display_name`.
- `x-monitoring/x_monitor/static/trend-chart.js` lines 13-31 — `SIGNAL_KEYS` / `SIGNAL_LABELS` hardcoded; need to inject locale-aware labels via the rendered HTML (server emits `data-signal-labels` JSON attribute per locale).

### Institutional Learnings

- `feedback_xmonitor_fk_hot_path_2026-06-20.md` — **the critical pattern**: every lookup-table FK must intersect writes against the registry before INSERT. LLM-hallucinated values crashed sqlite3 with `IntegrityError: FOREIGN KEY constraint failed`. Apply the same intersect-before-INSERT pattern in:
  - `Store.insert_post_brand_signals` (signal FK)
  - `Store.insert_brand_account` / `Store.insert_company_account` (role FK)
  - `Store.insert_account` / `Store.update_account_engagement_tier` (engagement_tier FK)
- `project_xmonitor_v18_unit2_rename_2026-06-19.md` — the rename playbook (if any future rename is needed): `perl -pi -e` for cross-host, synthetic PK mapping for derived entities, `Store.apply_migrations` self-applies. Not invoked here; included as the reference pattern for the **deferred** plural_plural + integer-PK plans.
- `feedback_worktree_hygiene_x_monitoring.md` — develop in `<repo>/worktrees/<name>/` with `.venv` + `data/x_monitoring.db` symlinked. Apply for the implementation of this plan.

### External References

- SQLite table rebuild pattern for CHECK → FK conversion: SQLite does not support `ALTER TABLE … DROP CONSTRAINT`. The conversion requires `CREATE TABLE _new(...); INSERT INTO _new SELECT ... FROM posts; DROP TABLE posts; ALTER TABLE _new RENAME TO posts;` inside one transaction. This is documented at https://www.sqlite.org/lang_altertable.html ("Making Other Kinds Of Table Schema Changes").
- Anthropic Claude Haiku 4.5: ~$0.005 per 1K translation rows (per v1.7 plan Unit 4 cost estimate). For ~30 brand/company/account rows × 2 locales = 60 LLM calls (well under $0.01).

## Key Technical Decisions

- **D1** — Use **lookup tables** (`signal_types`, `role_types`, `engagement_tier_types`) for enum i18n, not JSON sidecars. Rationale: user explicitly chose this option for fast/seamless locale switching (one JOIN per render, cacheable at startup). Lookup tables also get us a FK-validated schema for free, which is the same correctness story as `brands`/`companies`.
- **D2** — Use `<col>_en` / `<col>_zh_cn` column pairs on each table that needs free-form translation, not a sidecar table. Rationale: matches v1.7's `posts.text_en`/`text_zh_cn` precedent (per origin: 2026-06-17 plan Decision 5). One source column stays (the existing `display_name` / `bio`); locale columns default to NULL until the translator backfills them.
- **D3** — **Sequencing constraint:** the i18n migration MUST be numbered `006_*.sql`, not `005`. The HF products crawler migration `005_products.sql` lives on branch `feat/hf-products-crawler` (unmerged). Renumbering would conflict when that branch merges.
- **D4** — **FK-guard pattern** (per `feedback_xmonitor_fk_hot_path_2026-06-20.md`): every write to a lookup-table FK column must intersect against `_known_signal_values()` / `_known_role_values()` / `_known_engagement_tier_values()` (cached at app startup, invalidated on `Store._apply_migration`). Unknown values go to a dead-letter log (`data/runs/<ts>/enum_dead_letter.jsonl`); they do NOT raise `IntegrityError`.
- **D5** — **Conversion shape**: `signal_types`, `role_types`, `engagement_tier_types` each get `(key, locale, label)` columns with PK `(key, locale)`. Seed both locales in the migration. The existing TEXT column on `post_brand_signals` / `brand_accounts` / `company_accounts` / `accounts` is dropped + replaced by an FK column referencing the new table (SQLite table-rebuild pattern).
- **D6** — **Display name fallback chain** (in `_pick_i18n_text`):
  1. If `<col>_<locale>` exists and is non-NULL → return it.
  2. Else if `<col>_<en>` exists and is non-NULL → return it.
  3. Else return the source `<col>` column (current value).
  4. Mark `is_translated = False` for cases (2) and (3) so the dashboard renders the "source fallback" badge.
- **D7** — **Translator extension**: a single new function `translate_registry_rows(table, column, target_locales, client, *, batch_size=20)` in `x_monitor/translator.py`. It reads rows where `<col>_<locale>` IS NULL, builds the same Haiku prompt shape (with locale-aware rules + brand-name verbatim), writes back via `bulk_update_translations_<col>`. CLI: `x-monitor translate-registry <table> <column> [--locale en|zh-CN|both] [--limit N] [--dry-run]`.
- **D8** — **Translation cost is negligible**: ~30 brands + ~10 companies + ~50 accounts × 2 locales = ~180 LLM calls at Haiku 4.5 rates ≈ $0.005 total. No budget cap needed; backfill runs once.
- **D9** — **JS signal labels**: instead of shipping a per-locale `trend-chart.js`, the server emits the localized `SIGNAL_LABELS` dict as a `data-signal-labels` JSON attribute on the chart container; the JS reads it from there. One JS bundle, per-locale labels.
- **D10** — **Defer (chronology decision)**: plural_plural renames + integer-PK rewrites ship as separate plans after this one. Their blast radius is much larger (every FK edge in the schema) and combining would triple the review cost.

## Open Questions

### Resolved During Planning

- **Q1: Chronology of i18n vs side-notes** → i18n first; renames + PK rewrites deferred (D10). User-confirmed.
- **Q2: Enum translation shape** → lookup tables. User-confirmed (for fast/seamless locale switching).
- **Q3: products table scope** → defer until `feat/hf-products-crawler` merges to main. R3 is conditional on that merge happening first.

### Deferred to Implementation

- **Q4: Exact zh-CN translations for the 6 signals / 5 roles / 3 engagement tiers** — these are dictionary / domain decisions, not architectural. The migration seeds English labels; zh-CN seed labels are operator-curated in a follow-up script that writes to the lookup tables. Implementation may stage these as a JSON file in `x-monitoring/data/translations/` for operator review.
- **Q5: How to handle the case where `bio` is already in zh-CN** — v1.7's translator has a `noop_<locale>` flag (skip translation when source already matches target). Reuse the same flag for `bio` — if the LLM detects `lang_detected == "zh-CN"`, set `bio_zh_cn = bio`, leave `bio_en` for a future translator pass.
- **Q6: Backfill ordering** — backfill `display_name_en` for all brands first (smallest set, highest visibility), then `companies.display_name_en`, then `accounts.display_name_en` (largest set, lowest priority), then `bio_en/zh_cn`. The operator may run these in any order via the CLI; default runs in priority order.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Data model after migration

```
brands (existing TEXT PK, 12 columns)
  + display_name_en   TEXT     -- NEW (NULL until translator backfills)
  + display_name_zh_cn TEXT    -- NEW (NULL until translator backfills)
  + bio               -- (brands has no bio column; N/A here)

companies (existing TEXT PK, 4 columns)
  + display_name_en   TEXT
  + display_name_zh_cn TEXT

accounts (existing TEXT PK author_id, 14 columns)
  + bio_en            TEXT     -- source bio stays for fallback
  + bio_zh_cn         TEXT
  -- display_name_en/_zh_cn are NOT added on accounts (handles are the
  --   identifier; the @handle shows in the UI, not a translated name)

products (after HF 005 merges)
  + display_name_en   TEXT
  + display_name_zh_cn TEXT

signal_types (NEW)
  (key TEXT, locale TEXT, label TEXT, PRIMARY KEY (key, locale))
  -- 6 keys × 2 locales = 12 rows

role_types (NEW)
  (key TEXT, locale TEXT, label TEXT, PRIMARY KEY (key, locale))
  -- 5 keys × 2 locales = 10 rows

engagement_tier_types (NEW)
  (key TEXT, locale TEXT, label TEXT, PRIMARY KEY (key, locale))
  -- 3 keys × 2 locales = 6 rows
```

### FK conversion shape (post_brand_signals.signal as the example)

Pre-004:
```sql
post_brand_signals(
    post_id   TEXT NOT NULL,
    brand_id  TEXT NOT NULL,
    signal    TEXT NOT NULL,   -- convention-only
    PRIMARY KEY (post_id, brand_id),
    CHECK (brand_id <> '_unattributed')
)
```

Post-migration-006:
```sql
post_brand_signals(
    post_id   TEXT NOT NULL,
    brand_id  TEXT NOT NULL,
    signal    TEXT NOT NULL,
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (signal, 'zh-CN') REFERENCES signal_types(key, locale),  -- NOT how FKs work
    -- SQLite FKs can't reference composite (key, locale); instead:
    FOREIGN KEY (signal) REFERENCES signal_types_en(key),  -- WRONG shape
)
```

The honest shape: SQLite FKs cannot target a subset of a composite PK. Two viable shapes:

**Option A (recommended)**: keep `signal_types` as `(key, locale, label)` for display; add a sibling `signal_keys(key PRIMARY KEY, ...)` for FK integrity. The lookup table for FKs is `signal_keys`; the lookup table for labels is `signal_types`. They share the `key` column.

**Option B**: keep all enum validation in CHECK constraints (no FK); add `signal_types` as a pure display lookup.

Going with **Option A**: separate the integrity concern (which keys exist?) from the display concern (what's the label for key K in locale L?). This is a small additional table per enum family but matches the v1.8 pattern of `brands` being the canonical registry.

Revised shape:

```
signal_keys(key TEXT PRIMARY KEY, created_at TEXT)
  -- 6 rows: release, community_question, criticism, commenter_capture, praise, other
signal_labels(key TEXT, locale TEXT, label TEXT, PRIMARY KEY (key, locale),
              FOREIGN KEY (key) REFERENCES signal_keys(key) ON DELETE CASCADE)
  -- 12 rows = 6 keys × 2 locales

post_brand_signals.signal REFERENCES signal_keys(key)   -- FK for integrity
-- Dashboard reads signal_labels(key=post.signal, locale=?) for display
```

Same shape for `role_keys` / `role_labels` and `engagement_tier_keys` / `engagement_tier_labels`.

### Render flow (post-migration)

```
HTTP request → DashboardApp._resolve_locale()
              ↓
              locale in {"en", "zh-CN", "zh_cn"}
              ↓
              _build_cards(db_path) -- threads locale into every helper
              ↓
              for each brand card:
                display_name = _pick_i18n_text(brand_row, "display_name", locale)
                signal_breakdown[i].label = _pick_enum_label("signal", key, locale)
              ↓
              for each role bar:
                role_label = _pick_enum_label("role", role_key, locale)
              ↓
              template renders {{ display_name }} | brand_colorize
              chart container gets data-signal-labels='{"release":"发布",...}'
```

## Implementation Units

- [ ] **Unit 1: Migration 006 — locale columns on registry tables**

**Goal:** Add `display_name_en`/`_zh_cn` to `brands`, `companies`, and `bio_en`/`_zh_cn` to `accounts`. Plus partial indexes for the backfill driver.

**Requirements:** R1, R2, R9

**Dependencies:** HF migration 005 must be merged first (so the migration number is unambiguous and we can plan the products column in a follow-up without colliding). For this unit, defer products entirely — R3 ships as Unit 7.

**Files:**
- Create: `x-monitoring/x_monitor/migrations/006_i18n_locale_columns.sql`
- Test: `x-monitoring/tests/test_migration_006_i18n_locale_columns.py`

**Approach:**
- `BEGIN; … COMMIT;` wrapper.
- `ALTER TABLE brands ADD COLUMN display_name_en TEXT; ALTER TABLE brands ADD COLUMN display_name_zh_cn TEXT;` (and equivalents for `companies`, `accounts.bio`).
- Partial indexes for the backfill driver: `CREATE INDEX IF NOT EXISTS idx_brands_display_name_en_backfill ON brands(brand_id) WHERE display_name_en IS NULL;` (and equivalents for the zh_cn indexes + the bio pair).
- Idempotent on re-apply (`ADD COLUMN` in SQLite raises if column exists, so guard with `PRAGMA table_info(brands)` check at the top of the migration script — or use the existing `migrate_gh_hf_owner_columns.py` pattern of guarded ALTER).

**Test scenarios:**
- Happy path: apply 006 on a DB with 001-005 applied → columns exist, partial indexes exist, existing rows have NULL for the new columns.
- Edge case: re-running 006 is a no-op (guarded ALTER).
- Integration: `Store(...)` with `auto_migrate=True` brings a brand-new DB through 006, `_resolve_locale()` still works.

**Verification:** Migration applies cleanly on a copy of the live DB; `PRAGMA table_info(brands)` shows the new columns; `PRAGMA index_list(brands)` shows the backfill partial indexes.

- [ ] **Unit 2: Migration 007 — enum lookup tables + FK conversion**

**Goal:** Create the three enum-key tables (`signal_keys`, `role_keys`, `engagement_tier_keys`) + their label tables (`signal_labels`, `role_labels`, `engagement_tier_labels`), seed with all keys × both locales, then convert the four TEXT enum columns to FKs (SQLite table-rebuild pattern).

**Requirements:** R4, R5, R10

**Dependencies:** Unit 1. Must be a separate migration file (separate `BEGIN;`/`COMMIT;`) because SQLite table rebuilds can't share a transaction with `ALTER TABLE` on a different table cleanly.

**Files:**
- Create: `x-monitoring/x_monitor/migrations/007_enum_i18n_lookup_tables.sql`
- Modify: `x-monitoring/x_monitor/store.py` (new `_known_signal_keys()`, `_known_role_keys()`, `_known_engagement_tier_keys()` cached loaders)
- Test: `x-monitoring/tests/test_migration_007_enum_i18n.py`

**Approach:**
- `BEGIN; … COMMIT;` wrapper.
- `CREATE TABLE IF NOT EXISTS signal_keys(key TEXT PRIMARY KEY, created_at TEXT NOT NULL); INSERT OR IGNORE INTO signal_keys(key, created_at) VALUES ('release', ...), ('community_question', ...), ('criticism', ...), ('commenter_capture', ...), ('praise', ...), ('other', ...);`
- `CREATE TABLE IF NOT EXISTS signal_labels(key TEXT NOT NULL, locale TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY (key, locale), FOREIGN KEY (key) REFERENCES signal_keys(key) ON DELETE CASCADE);`
- `INSERT OR IGNORE INTO signal_labels(key, locale, label) VALUES ('release', 'en', 'Release'), ('release', 'zh_cn', '发布'), …`
- Same for `role_keys` (5 rows: official, community, researcher, press, vendor) + `role_labels` (10 rows), and `engagement_tier_keys` (3 rows: low, medium, high) + `engagement_tier_labels` (6 rows).
- **FK conversion via table rebuild**:
  - `CREATE TABLE post_brand_signals_new(post_id TEXT NOT NULL, brand_id TEXT NOT NULL, signal TEXT NOT NULL, PRIMARY KEY (post_id, brand_id), FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE SET NULL, FOREIGN KEY (signal) REFERENCES signal_keys(key) ON DELETE RESTRICT, CHECK (brand_id <> '_unattributed'));`
  - `INSERT INTO post_brand_signals_new SELECT post_id, brand_id, signal FROM post_brand_signals;`
  - `DROP TABLE post_brand_signals; ALTER TABLE post_brand_signals_new RENAME TO post_brand_signals;`
  - Re-create all `idx_post_brand_signals_*` indexes on the new table.
  - Same shape for `brand_accounts.role`, `company_accounts.role`, `accounts.engagement_tier`.
- **CHECK constraint preservation**: the `post_brand_signals CHECK (brand_id <> '_unattributed')` must survive the rebuild (P0 review fix from migration 004 history).

**Test scenarios:**
- Happy path: apply 007 → 3 key tables + 3 label tables exist; 6/5/3 keys seeded; 12/10/6 labels seeded; `post_brand_signals.signal` is now FK; existing rows preserved.
- Edge case: re-running 007 is a no-op.
- Error path: trying to INSERT an unknown signal value into `post_brand_signals` raises `IntegrityError` (we test the FK works) — BUT the application-level `_known_signal_keys()` intersect-before-INSERT prevents this from happening in normal flow.
- Integration: insert a valid post_brand_signals row via `Store`; verify the row is queryable and the FK lookup works.

**Verification:** Migration applies on a DB with 001-006 applied; `PRAGMA foreign_key_list(post_brand_signals)` shows the new signal_keys FK; all FK-protected inserts via the application succeed without integrity errors.

- [ ] **Unit 3: Store — `_pick_i18n_text` + `_pick_enum_label` helpers + FK-guard caches**

**Goal:** Add the dashboard helpers and the FK-guard cache loaders. Wire the FK-guard into the four insert paths that write to the now-FK-protected columns.

**Requirements:** R5 (guard pattern), R7 (helpers)

**Dependencies:** Unit 2.

**Files:**
- Modify: `x-monitoring/x_monitor/store.py` (add `_pick_i18n_text`, `_pick_enum_label` static/instance methods; add `_known_signal_keys`, `_known_role_keys`, `_known_engagement_tier_keys` cached loaders; update `insert_post_brand_signals`, `insert_brand_account`, `insert_company_account`, `insert_account`, `update_account_engagement_tier` to intersect-before-INSERT)
- Test: `x-monitoring/tests/test_store_i18n_helpers.py`

**Approach:**
- `_known_*` loaders: cache `set[str]` of valid keys, populated on first call after `Store.__init__`. Invalidated in `_apply_migration` after a migration runs (since new keys may have been added).
- `_pick_i18n_text(row, column, locale) -> (str, bool)`: mirror `_pick_text` shape from `dashboard.py:111`. Fallback chain per D6.
- `_pick_enum_label(enum_family, value, locale) -> (str, bool)`: family is `"signal"` / `"role"` / `"engagement_tier"`. Looks up `signal_labels(key=value, locale=locale)`; falls back to `signal_labels(key=value, locale='en')`; falls back to the raw `value` (canonical English key).
- Insert-site guard pattern (per `feedback_xmonitor_fk_hot_path_2026-06-20.md`): every write checks the value is in the cached `_known_*` set; unknown values log to `data/runs/<ts>/enum_dead_letter.jsonl` and skip the INSERT for that one row (not the whole batch).

**Test scenarios:**
- Happy path: `_pick_i18n_text(brand_row, "display_name", "zh_cn")` returns the zh_cn column when populated.
- Edge case: `_pick_i18n_text` falls back to en when zh_cn is NULL.
- Edge case: `_pick_i18n_text` falls back to source `display_name` when both locale columns are NULL.
- Edge case: `_pick_enum_label("signal", "release", "zh_cn")` returns "发布" when seeded.
- Error path: unknown enum value at insert site goes to dead-letter log, does NOT raise IntegrityError.
- Integration: bulk insert 1000 post_brand_signals rows with 0.1% unknown signal values → 990 succeed, 10 go to dead-letter log.

**Verification:** Tests pass; the FK-guard is wired into all four insert paths (verified via grep).

- [ ] **Unit 4: Translator extension — `translate_registry_rows`**

**Goal:** Extend `x_monitor/translator.py` with a function that translates the new free-form columns (`display_name`, `bio`) using the existing Haiku 4.5 client + prompt shape.

**Requirements:** R6, R7, R8

**Dependencies:** Unit 1 (the columns must exist).

**Files:**
- Modify: `x-monitoring/x_monitor/translator.py` (add `translate_registry_rows(table, column, target_locales, client, *, batch_size=20, dry_run=False)`)
- Modify: `x-monitoring/x_monitor/store.py` (add `bulk_update_registry_translations(table, column, rows)` + `get_registry_missing_translations(table, column, locale, limit)`)
- Modify: `x-monitoring/x_monitor/cli.py` (add `translate-registry` subcommand)
- Test: `x-monitoring/tests/test_translator_registry.py`

**Approach:**
- Mirror the existing `translate_batch` shape: batch size 20, exponential backoff, idempotent UPDATE, dry-run mode.
- Prompt rules 1-6 reused from v1.7; new rule 7: "for proper nouns (company names, brand names, model names), preserve the canonical form — translate the descriptor but not the name itself" (e.g., "MiniMax AI's Haiku 4.5" → Chinese keeps "MiniMax AI" verbatim).
- Locale list: `target_locales = ["en", "zh_cn"]` by default; CLI accepts `--locale en|zh-CN|both`.
- Dead-letter handling: if LLM returns invalid JSON, log + skip the row; do not abort the batch.

**Test scenarios:**
- Happy path: 30 brand rows translated in 2 batches (batch size 20 → 20 + 10).
- Edge case: empty input list is a no-op.
- Edge case: row with `display_name = "MiniMax AI"` (already English) → `noop_en = True`, no LLM call for the en locale.
- Error path: 5xx retry exhausts → row marked `translation_failed = True`, batch continues.
- Integration: end-to-end with `FakeClaudeClient` returns a valid response dict for both batches.

**Verification:** `python -m x_monitor translate-registry brands display_name --locale both --dry-run` prints the rows that would be translated without writing; without `--dry-run`, the rows are updated in the DB.

- [ ] **Unit 5: Dashboard wiring — `_resolve_locale` → every render path**

**Goal:** Replace `MODEL_DISPLAY_NAMES` Python dict with DB-backed reads via `_pick_i18n_text`. Wire `_pick_enum_label` into the role-bars section of the brand detail page and the chart container's signal labels.

**Requirements:** R7, R8

**Dependencies:** Unit 3 (helpers exist).

**Files:**
- Modify: `x-monitoring/x_monitor/dashboard.py` (replace `MODEL_DISPLAY_NAMES` reads with `Store._pick_i18n_text(brands, "display_name", locale)`; thread locale into `serialize_grid_card` for the role-bar section)
- Modify: `x-monitoring/x_monitor/static/trend-chart.js` (read `data-signal-labels` from chart container; fall back to `SIGNAL_LABELS` if attribute missing)
- Modify: `x-monitoring/x_monitor/templates/_model_card.html.j2` (add `data-signal-labels='…'` attribute on chart container)
- Modify: `x-monitoring/x_monitor/templates/model_detail.html.j2` (use `_pick_enum_label("role", role_key, locale)` for role-bar labels)
- Test: `x-monitoring/tests/test_dashboard_i18n.py`

**Approach:**
- `MODEL_DISPLAY_NAMES` becomes the **fallback chain's terminal step** if the DB has no `display_name` at all (shouldn't happen post-Unit 4 backfill, but defensive).
- The dashboard's `_build_cards` already threads `display_locale` into `serialize_grid_card`. Extend it to also look up brand display names from the DB (one query: `SELECT brand_id, display_name, display_name_en, display_name_zh_cn FROM brands`) and pass a `display_name_<locale>` per brand.
- Server emits a single `data-signal-labels` attribute per chart container: `JSON.stringify({release: "发布", community_question: "社区问题", ...})`. JS reads it once at chart init.

**Test scenarios:**
- Happy path: dashboard renders Chinese locale (`?locale=zh-CN`) → card titles in Chinese, signal labels in Chinese, role bars in Chinese.
- Happy path: dashboard renders English locale → falls back to source `display_name` (which is English seed).
- Edge case: locale cookie set to "zh-CN" but column is NULL → falls back to English source, renders "source fallback" badge.
- Integration: full dashboard render with `?locale=zh-CN` returns Chinese strings; with `?locale=en` (default) returns English strings; with `?locale=fr` falls back to English with a warning log.

**Verification:** Manual visual check on `/`, `/grid`, `/brand/<id>` for both locales; `pytest tests/test_dashboard_i18n.py -q` passes.

- [ ] **Unit 6: Backfill driver + operator scripts**

**Goal:** Provide operator scripts that backfill the new locale columns using the translator. Document the order of operations in the deploy runbook.

**Requirements:** R6, R8

**Dependencies:** Unit 4 (translator extension), Unit 5 (dashboard reads locale columns).

**Files:**
- Create: `x-monitoring/scripts/2026-06-23-001-backfill-display-name-en.py`
- Create: `x-monitoring/scripts/2026-06-23-002-backfill-display-name-zh-cn.py`
- Create: `x-monitoring/scripts/2026-06-23-003-backfill-bio-en.py`
- Create: `x-monitoring/scripts/2026-06-23-004-backfill-bio-zh-cn.py`
- Create: `x-monitoring/scripts/2026-06-23-005-seed-enum-zh-cn-labels.py` (operator-curated Chinese labels for the 6 signals, 5 roles, 3 tiers)

**Approach:**
- Each backfill script is a thin wrapper around `x_monitor.translator.translate_registry_rows`. Idempotent (only translates rows where the target column is NULL). Safe to re-run.
- Order: run `seed-enum-zh-cn-labels.py` first (operator decides Chinese names for each enum value, e.g., "release" → "发布"); then run the four backfill scripts.
- Each script logs: how many rows were translated, how many were no-op (source already in target locale), how many failed (translation_failed).

**Test scenarios:**
- Happy path: 12 brands translated end-to-end with a `FakeClaudeClient`; `brands.display_name_en` populated for all 12.
- Edge case: re-run is a no-op (all columns already populated).
- Error path: LLM returns invalid JSON for one batch → that batch's rows are logged as failed, subsequent batches still run.

**Verification:** Run the four scripts on a copy of the live DB; all target columns populated; no failures in the log.

- [ ] **Unit 7: products.display_name_en/_zh_cn (conditional)**

**Goal:** Add the same locale columns to `products` (if/when HF migration 005 merges to main). Skipped if 005 has not merged by the time this plan executes.

**Requirements:** R3

**Dependencies:** HF 005 merged (status currently: on branch `feat/hf-products-crawler`, unmerged).

**Files:**
- Create: `x-monitoring/x_monitor/migrations/008_products_locale_columns.sql`
- Test: `x-monitoring/tests/test_migration_008_products_locale.py`

**Approach:**
- Same shape as Unit 1 but on `products`.
- This is a **separate migration file** (008) so it can ship independently when 005 merges. If 005 has not merged by the time Units 1-6 ship, this unit is deferred to a follow-up PR.

**Test scenarios:**
- Happy path: apply 008 on a DB with 001-007 applied → `products.display_name_en` and `display_name_zh_cn` exist, partial indexes exist, existing rows have NULL.

**Verification:** Migration applies cleanly after 005 + 007.

## System-Wide Impact

- **Interaction graph:** The dashboard locale toggle already calls `_resolve_locale()` on every request. Unit 5 extends its consumers (card render, signal labels, role bars) but does not introduce a new entry point. The translator extension adds a new CLI subcommand (`translate-registry`) but does not change the existing cron path.
- **Error propagation:** LLM translation failures go to per-row `translation_failed = True` (not aborting the batch, mirroring v1.7's behavior). FK-guard failures (unknown enum values) go to a dead-letter log file; the batch continues. Both failures are visible via the existing `data/runs/<ts>/` directory structure.
- **State lifecycle risks:** Partial migration failure mid-transaction (between `CREATE TABLE signal_keys` and the table-rebuild of `post_brand_signals`) leaves the DB in an inconsistent state. Mitigation: the `BEGIN; … COMMIT;` wrapper is per-migration-file, not per-step. If a migration fails, the loader rolls back the transaction. Operators run migrations one-at-a-time and check `SELECT * FROM _migrations` between steps.
- **API surface parity:** No new HTTP endpoints. The existing `POST /api/set_locale` is reused. The new `x-monitor translate-registry` CLI is an additive subcommand.
- **Integration coverage:** Unit 5's dashboard integration test exercises the full HTTP round-trip with both locales; Unit 4's translator integration test exercises the LLM round-trip with `FakeClaudeClient`. Both are required.
- **Unchanged invariants:** `posts.text` (source) is unchanged; the v1.7 fallback chain for `posts.text` is unchanged. `MODEL_DISPLAY_NAMES` Python dict is retained as the terminal fallback (defensive; never reached post-backfill). `_resolve_locale()` priority order is unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| HF migration 005 collision if `feat/hf-products-crawler` merges with a different migration number | Use `006` for this i18n migration (per D3); Unit 7 ships as `008` to leave room for any HF follow-up migration |
| SQLite table rebuild for FK conversion (Unit 2) drops existing rows on failure | `BEGIN; … COMMIT;` wraps the entire rebuild; loader rolls back on failure; dry-run on `/tmp/x_monitoring.dryrun.db` before live deploy (per migration 004 operator prerequisites) |
| LLM hallucinated enum values crash `post_brand_signals` INSERT (per `feedback_xmonitor_fk_hot_path_2026-06-20.md`) | Intersect-before-INSERT in all four write paths; dead-letter log for unknown values (Unit 3) |
| `MODEL_DISPLAY_NAMES` Python dict used by tests / external scripts | Retain the dict as fallback (D8); deprecation note in the module docstring; remove in a follow-up after one release cycle |
| Backfill LLM call cost surprises | $0.005 estimated total for ~180 rows; documented in D8; no budget cap needed; dry-run mode lets operator preview |
| Operator forgets to seed zh-CN enum labels before backfill | Unit 6 order of operations: `seed-enum-zh-cn-labels.py` runs FIRST; the backfill scripts assume labels exist; deploy runbook calls this out explicitly |
| Race condition: translator backfills row while dashboard reads it | Existing `Store` uses SQLite WAL mode; readers see last-committed state; backfill UPDATEs are atomic per row; no special handling needed |
| Tests assume `dashboards.py` reads `MODEL_DISPLAY_NAMES` | Unit 5 changes this; tests that depend on the Python dict must be updated to assert on the DB-seeded values instead |

## Documentation / Operational Notes

- **Deploy runbook (operator actions, in order):**
  1. Stop pipeline worker (`launchctl unload com.fuchitalee.x-monitor`).
  2. Stop dashboard (`lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs kill`).
  3. Atomic backup of `data/x_monitoring.db` with sha256.
  4. Apply migration 006 on the live DB (auto-applies on first request after restart, OR manually via `Store.apply_migrations()`).
  5. Restart dashboard, verify `/` renders with English (default locale).
  6. Apply migration 007 on the live DB (table rebuild — verify on dryrun first).
  7. Restart dashboard, verify role-bars + chart labels still render (no change yet — labels are still English until Unit 5 ships).
  8. Ship Unit 5 (dashboard reads from DB). Verify `/` renders.
  9. Run `seed-enum-zh-cn-labels.py` (operator-curated Chinese names).
  10. Run the four backfill scripts (display_name_en, display_name_zh_cn, bio_en, bio_zh_cn) in dry-run first, then live.
  11. Switch dashboard cookie to `zh-CN`, verify Chinese strings render.
  12. Restart pipeline worker.
- **Memory updates:** add a `project_xmonitor_i18n_locale_2026-06-23.md` after shipping, capturing: which migration number was used, the FK-guard locations (for future FK-added columns), the operator-curated zh-CN enum labels (so they survive rebuilds), the `translate-registry` CLI usage.
- **Cost tracking:** log translator LLM calls in `data/runs/<ts>/translator_costs.json` (mirroring v1.7's pattern). The ~$0.005 estimate is per-deploy, not per-cycle.

## Sources & References

- **Origin prompt:** user request 2026-06-23 — "we need to add new columns for zh_cn versions in following tables: accounts (bio_zh_cn, bio_en); companies (change display_name to display_name, add display_name_en, display_name_zh_cn); brands (display_name_en, display_name_zh_cn), products (display_name_zh_cn, display_name_en)".
- **Related plan:** `docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md` — direct precedent for v1.7's `text_en`/`text_zh_cn` shape.
- **Related plan:** `docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md` — migration 004 (company/brand/account model; this plan's foundation).
- **Related plan:** `docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md` — unmerged branch with migration 005 (products table); sequencing constraint.
- **Memory:** `feedback_xmonitor_fk_hot_path_2026-06-20.md` — FK-guard pattern (intersect-before-INSERT for lookup-table FKs).
- **Memory:** `project_xmonitor_v18_unit2_rename_2026-06-19.md` — rename playbook (reference pattern for the deferred plural_plural + integer-PK plans).
- **Code:** `x-monitoring/x_monitor/translator.py` — translation infrastructure.
- **Code:** `x-monitoring/x_monitor/store.py` — store API + migration loader.
- **Code:** `x-monitoring/x_monitor/dashboard.py` — dashboard locale helpers + MODEL_DISPLAY_NAMES dict.
- **Code:** `x-monitoring/x_monitor/migrations/003_translation_columns.sql` — direct precedent for additive migration with partial indexes.
- **Code:** `x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql` — migration conventions (BEGIN/COMMIT, idempotency, FK patterns).
- **Reference:** `docs/reference/db-schema.md` — current table inventory + column shapes.