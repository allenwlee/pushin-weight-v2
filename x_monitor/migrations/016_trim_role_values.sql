-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 016: trim role taxonomy to {official, staff, community}.
--
-- Migration 008 seeded 5 roles (official, community, researcher, press,
-- vendor). In practice, only 3 of these are used: official, community,
-- and (the newly-introduced) staff. The legacy values researcher, press,
-- and vendor were never used by any current pipeline and are removed
-- to keep the taxonomy tight.
--
-- What this migration does:
--   1. Adds the new `staff` key to `roles` (it is not in the 008 seeds).
--   2. Backfills any `brands_accounts.role_id` / `companies_accounts.role_id`
--      row that points at a removed value to the closest survivor
--      ('community'). The role_id columns are NOT NULL DEFAULT 'community'
--      (per migration 008), so we remap rather than NULL.
--   3. Deletes the removed `role_labels` rows (3 keys × 2 locales = 6 rows).
--   4. Deletes the removed `roles` rows (3 keys).
--   5. Re-inserts the 6 surviving `role_labels` rows (3 keys × 2 locales)
--      with the canonical labels — official (Official / 官方),
--      staff (Staff / 员工), community (Community / 社区). INSERT OR IGNORE
--      so re-running this script after a successful first run is a no-op.
--
-- After this migration:
--   SELECT key FROM roles       -- {community, official, staff} (3 rows)
--   SELECT COUNT(*) FROM role_labels  -- 6
--
-- Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
-- Unit 6 of 9.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Backfill: remap any role_id pointing at a removed value to 'community'.
--    (Defensive — if no such rows exist, the UPDATE is a no-op.)
-- ---------------------------------------------------------------------------
UPDATE brands_accounts
   SET role_id = 'community'
 WHERE role_id IN ('researcher', 'press', 'vendor');

UPDATE companies_accounts
   SET role_id = 'community'
 WHERE role_id IN ('researcher', 'press', 'vendor');

-- ---------------------------------------------------------------------------
-- 2. Add the new `staff` key. (Idempotent — the legacy 008 seeds did not
--    include `staff`, but a future rerun of 016 on a partially-applied DB
--    must not fail.)
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO roles (key, created_at) VALUES
    ('staff', '2026-06-24T00:00:00+00:00');

-- ---------------------------------------------------------------------------
-- 3. Delete the removed role_labels rows. The FK is ON DELETE CASCADE from
--    roles → role_labels, but doing it explicitly makes the intent
--    self-documenting and is also defensive against a future migration that
--    weakens the cascade.
-- ---------------------------------------------------------------------------
DELETE FROM role_labels WHERE key IN ('researcher', 'press', 'vendor');

-- ---------------------------------------------------------------------------
-- 4. Delete the removed roles rows.
-- ---------------------------------------------------------------------------
DELETE FROM roles WHERE key IN ('researcher', 'press', 'vendor');

-- ---------------------------------------------------------------------------
-- 5. Re-insert the 6 surviving role_labels rows (3 keys × 2 locales).
--    INSERT OR IGNORE so a partial rerun is a no-op.
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO role_labels (key, lang, label) VALUES
    ('official',  'en',    'Official'),
    ('official',  'zh_cn', '官方'),
    ('staff',     'en',    'Staff'),
    ('staff',     'zh_cn', '员工'),
    ('community', 'en',    'Community'),
    ('community', 'zh_cn', '社区');

COMMIT;
