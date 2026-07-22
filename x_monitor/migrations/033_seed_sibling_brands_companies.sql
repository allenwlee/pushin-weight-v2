-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 033: seed the 7 sibling brands_companies rows.
--
-- Plan: docs/plans/2026-07-09-001-feat-list-yaml-db-sync-plan.md (Unit 3)
-- Reconciliation note: docs/notes/2026-07-09-list-yaml-reconciliation.md
--
-- Background:
-- Migration 030 split some Chinese-model brands into a primary brand +
-- a sibling brand (doubao + seed, chatglm + glm, sensenova + sensechat,
-- step + stepfun, kwaiyii + kuaishou, wenxin + ernie) and seeded the
-- primary brand's row in `brands_companies` (e.g. glm → zhipu) but
-- deliberately did not seed the sibling's row (e.g. chatglm → zhipu)
-- because the U3 seed script had not yet been written. Plan 005 U3
-- closes that gap.
--
-- This migration is data-only: 7 INSERT OR IGNORE rows. The 10 list-
-- not-in-DB handles are seeded by a separate one-shot script
-- (`scripts/seed_list_handles_to_db.py`) that performs the TwitterAPI.io
-- author_id lookup and the brand-by-company cross-product. That script
-- is non-migration because it does I/O (HTTP) and may need re-runs as
-- the auth path is fixed — keeping it out of the migration ledger means
-- re-runs don't trigger spurious "_migrations already applied" failures.
--
-- Operator-confirmed 2026-07-09 (reconciliation note Bucket 3c):
--   doubao    → bytedance
--   seed      → bytedance
--   chatglm   → zhipu
--   sensenova → sensetime
--   step      → stepfun_inc
--   kwaiyii   → kuaishou_co
--   wenxin    → baidu
--
-- Idempotency: every INSERT is INSERT OR IGNORE. The
-- brands_companies.(brand_id, company_id) PK enforces uniqueness
-- across re-applies.
--
-- Subselect-by-nickname is used for the brand→company join so we do
-- not depend on surrogate ids remaining stable across re-applies.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

INSERT OR IGNORE INTO brands_companies (brand_id, company_id) VALUES
    ((SELECT id FROM brands    WHERE nickname='doubao'),
     (SELECT id FROM companies WHERE nickname='bytedance')),
    ((SELECT id FROM brands    WHERE nickname='seed'),
     (SELECT id FROM companies WHERE nickname='bytedance')),
    ((SELECT id FROM brands    WHERE nickname='chatglm'),
     (SELECT id FROM companies WHERE nickname='zhipu')),
    ((SELECT id FROM brands    WHERE nickname='sensenova'),
     (SELECT id FROM companies WHERE nickname='sensetime')),
    ((SELECT id FROM brands    WHERE nickname='step'),
     (SELECT id FROM companies WHERE nickname='stepfun_inc')),
    ((SELECT id FROM brands    WHERE nickname='kwaiyii'),
     (SELECT id FROM companies WHERE nickname='kuaishou_co')),
    ((SELECT id FROM brands    WHERE nickname='wenxin'),
     (SELECT id FROM companies WHERE nickname='baidu'));

COMMIT;