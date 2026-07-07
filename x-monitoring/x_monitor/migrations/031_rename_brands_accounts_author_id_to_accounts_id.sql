-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 031: rename brands_accounts.author_id → accounts_id
--
-- Background:
-- `brands_accounts` was created when the column meant "Twitter author id"
-- (TEXT — the X/Twitter numeric user id). Migrations 018 and 020 converted
-- both `accounts.author_id` (TEXT PK) and `brands_accounts.author_id`
-- (TEXT → INTEGER FK to `accounts.id`), but the column name was kept
-- even though its type and meaning shifted.
--
-- Now the column is an INTEGER FK referencing accounts.id. Naming it
-- `author_id` is misleading — it has nothing to do with the X/Twitter
-- "author_id" anymore; it's a join key into `accounts`. Renaming to
-- `accounts_id` makes the parent-table relationship obvious and lets
-- future migrations index/join without misleading readers.
--
-- This is a single-shot atomic rename that ships with the code rename
-- in the same release. No backward-compatibility shim is provided
-- because:
--   1. The migration runner is idempotent (_migrations ledger), so a
--      re-apply after a partial apply is safe (no-ops).
--   2. SQLite's ALTER TABLE RENAME COLUMN is transactional — it either
--      applies fully or not at all (with the BEGIN/COMMIT wrapper
--      around it for safety against interruption).
--   3. There are no triggers or views that reference the old column
--      name (verified by `sqlite_master` query at design time).
--   4. The single index on brands_accounts is on `role_id`, not on
--      `author_id`, so no index rename is needed.
--   5. SQLite automatically updates the FK constraint definition
--      (PRAGMA foreign_key_list) to refer to the new column name —
--      the FK semantics are unchanged (still CASCADE on accounts.id).
--
-- Release posture: ship the migration file + the source-code
-- reference update in the same atomic release. Do NOT deploy one
-- without the other (inserts will fail).
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

ALTER TABLE brands_accounts RENAME COLUMN author_id TO accounts_id;

COMMIT;
