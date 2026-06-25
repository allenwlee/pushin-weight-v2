-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 018: INTEGER primary keys for enum tables.
--
-- Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
-- (Unit 8 of 9).
--
-- Scope: convert the PK of the two enum lookup tables (signals, roles)
-- from TEXT (the key string) to INTEGER AUTOINCREMENT. The TEXT `key`
-- column is preserved as UNIQUE NOT NULL so that:
--
--   1. All existing FK references in posts_brands_signals.signal_id,
--      brands_accounts.role_id, companies_accounts.role_id continue to
--      store the key STRING — they do not need to be rewritten to hold
--      an integer id. SQLite FKs are satisfied by UNIQUE columns, not
--      only by PRIMARY KEY columns.
--
--   2. The Store API remains unchanged: insert_posts_brands_signals()
--      and upsert_account() continue to accept string keys. The
--      `_known_signal_keys` / `_known_role_keys` caches continue to
--      return set[str] from `SELECT key FROM signals|roles`.
--
--   3. All read-side consumers (treemap.py, dashboard.py, get_account,
--      etc.) continue to see the key string in the *_id FK column and
--      need zero changes.
--
--   4. The signal_labels / role_labels tables continue to FK to
--      signals.key / roles.key (no change to their schema). They
--      survive the rebuild via a TEMP TABLE backup because the FK from
--      labels → enum table is `ON DELETE CASCADE` — `DROP TABLE signals`
--      would otherwise wipe out signal_labels.
--
-- Why AUTOINCREMENT (not bare INTEGER PRIMARY KEY): AUTOINCREMENT
-- guarantees id stability across deletes — without it, SQLite can reuse
-- a deleted id on the next insert. Enum rows are unlikely to be deleted,
-- but we want the ids to be permanent identifiers.
--
-- Why integer PKs at all: aligns with the post_types/sentiments work
-- (U9 will introduce post_type_keys/sentiment_keys alongside signals
-- and roles; the integer PK is the canonical pattern for new enum
-- tables going forward) and gives us integer-based JOIN performance for
-- future analytical queries.
--
-- A follow-up migration can convert the FK columns (signal_id, role_id)
-- from TEXT-storing-key to INTEGER-storing-id if and when the JOIN
-- performance benefit outweighs the consumer-side rewrite cost. This
-- migration deliberately does NOT make that change — it is out of scope.
--
-- Idempotency: the x-monitor migration runner tracks applied migrations
-- in `_migrations` and skips re-application.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. Rebuild `signals` with INTEGER id PK
-- ===========================================================================

-- Step 1a: TEMP TABLE backup of signal_labels (preserved across DROP TABLE
-- signals via the CASCADE FK from signal_labels → signals). The backup
-- is rebuilt back into signal_labels after the rename.
CREATE TEMP TABLE _signal_labels_backup AS
    SELECT key, lang, label FROM signal_labels;

-- Step 1b: rebuild signals with INTEGER id PK + UNIQUE key.
CREATE TABLE signals_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

INSERT INTO signals_new (key, created_at)
    SELECT key, created_at FROM signals
    ORDER BY key;  -- deterministic id assignment for test stability

DROP TABLE signals;
ALTER TABLE signals_new RENAME TO signals;

-- Step 1c: restore signal_labels from the TEMP backup.
INSERT OR IGNORE INTO signal_labels (key, lang, label)
    SELECT key, lang, label FROM _signal_labels_backup;

DROP TABLE _signal_labels_backup;

-- ===========================================================================
-- 2. Rebuild `roles` with INTEGER id PK
-- ===========================================================================

-- Step 2a: TEMP TABLE backup of role_labels (same CASCADE-FK reason).
CREATE TEMP TABLE _role_labels_backup AS
    SELECT key, lang, label FROM role_labels;

-- Step 2b: rebuild roles with INTEGER id PK + UNIQUE key.
CREATE TABLE roles_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

INSERT INTO roles_new (key, created_at)
    SELECT key, created_at FROM roles
    ORDER BY key;  -- deterministic id assignment for test stability

DROP TABLE roles;
ALTER TABLE roles_new RENAME TO roles;

-- Step 2c: restore role_labels from the TEMP backup.
INSERT OR IGNORE INTO role_labels (key, lang, label)
    SELECT key, lang, label FROM _role_labels_backup;

DROP TABLE _role_labels_backup;

COMMIT;
