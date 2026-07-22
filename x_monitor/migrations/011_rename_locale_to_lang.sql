-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 011: rename `locale` columns to `lang` on the i18n
-- label tables.
--
-- The `*_labels` tables (signal_labels, role_labels, engagement_tier_labels)
-- were created in migration 008 with a `locale` column on the composite
-- PRIMARY KEY (key, locale). The rest of the i18n stack has converged on
-- `lang` as the column name (matches the existing `lang` parameter used by
-- the translator pipeline and the `lang_detected` column on `posts`). This
-- migration unifies the column name across the schema.
--
-- Renames (columns):
--   signal_labels.locale          → signal_labels.lang
--   role_labels.locale            → role_labels.lang
--   engagement_tier_labels.locale → engagement_tier_labels.lang
--                                    (table is dropped in migration 012,
--                                     but the column is renamed here first
--                                     for consistency; U2 will then drop
--                                     the entire table)
--
-- Renames (indexes): none. No index is defined on the `locale` column
-- itself — the only indexed lookups on these tables use the composite PK
-- (key, locale), which follows the column rename automatically. The
-- per-locale partial indexes added in migration 007 (e.g.
-- idx_brands_display_name_en_backfill) target `*_en` and `*_zh_cn` columns
-- on the registry tables (brands, companies, accounts), not the labels
-- tables, and are not affected.
--
-- Backward compatibility: the x-monitor migration runner tracks applied
-- migrations in `_migrations` and skips re-application. This script does
-- not need IF EXISTS guards on the renames — the runner enforces "run
-- once per fresh DB".
--
-- Code impact: x_monitor/store.py::_pick_enum_label and
-- tests/test_migration_008_enum_i18n.py update their column references
-- to match. The display-locale parameter on the dashboard (e.g. ?locale=zh-CN
-- on /grid) is a separate concept — a user-facing cookie/query value, not
-- a DB column — and is intentionally NOT renamed.
--
-- Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
-- Unit 1 of 9.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ---------------------------------------------------------------------------
-- Column renames (`locale` → `lang` on each i18n label table)
-- ---------------------------------------------------------------------------
ALTER TABLE signal_labels          RENAME COLUMN locale TO lang;
ALTER TABLE role_labels            RENAME COLUMN locale TO lang;
ALTER TABLE engagement_tier_labels RENAME COLUMN locale TO lang;

COMMIT;
