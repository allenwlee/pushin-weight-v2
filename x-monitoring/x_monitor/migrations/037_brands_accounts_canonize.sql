-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 037: canonize `brands_accounts` as the operator
-- source for per-brand official/staff handles (DB-canonical).
--
-- Plan: docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md
-- (Unit U4).
--
-- post_step_touches: brands_accounts,brand_keywords
--
-- Background:
--   Plan 2026-07-11-001 (Scope Boundaries) explicitly kept
--   `data/accounts/*.yaml` as the operator-edit surface for per-brand
--   official/staff handles, with a deferred reconciler to migrate
--   yaml state into `brands_accounts`.
--
--   Plan 2026-07-11-002 (U4) brings that reconciler in-scope. As of
--   2026-07-11 the DB has 115 rows in `brands_accounts` (joined to
--   `accounts` + `roles`), mirroring every yaml-listed handle across
--   the 20 enabled brands. The runtime source of truth is now
--   `brands_accounts WHERE role_id IN (2, 3)` (official + staff); the
--   yaml files are deleted.
--
-- Why this migration exists (no body):
--   The schema already supports the canonization — `brands_accounts`,
--   `accounts`, and `roles` were set up by earlier migrations. This
--   file exists to:
--     (a) bump the migration version so `_applied_config_snapshot`
--         gets a fresh post-step run after the runtime refactor
--         lands, and
--     (b) carry the KTD7 header so the U4 post-step fires the
--         `data/brands_accounts.json` export.
--
-- Idempotency:
--   The SELECT below is a no-op against any DB state; it just
--   produces a deterministic no-op result. Running the migration
--   twice on the same DB is harmless.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- No-op: the schema is unchanged. The canonization is a runtime
-- surface refactor (U4 deletes `data/accounts/*.yaml`, the
-- `x_monitor/accounts.py` module, and `scripts/regenerate_accounts_yaml.py`;
-- updates `RunPipeline._update_accounts` + `list_drift.collect_expected_handles`
-- to read from `brands_accounts WHERE role_id IN (2, 3)`).
SELECT 1;

COMMIT;