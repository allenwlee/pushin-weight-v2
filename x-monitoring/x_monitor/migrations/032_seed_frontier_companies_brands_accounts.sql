-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 032: seed frontier model companies, brands, and accounts
-- (OpenAI, Anthropic, Google, xAI).
--
-- Plan: docs/plans/2026-07-08-001-feat-frontier-brands-companies-seed-plan.md
--
-- Background:
-- Frontier vendors are not in our TwitterAPI.io search queries
-- (we only capture Chinese-model posts), but Chinese-model posts
-- frequently *mention* the frontier vendors ("Kimi vs. GPT",
-- "Claude code review", "Gemini 3 release watch"). The brand-
-- attribution layer needs real rows for those names so mentions
-- route to them instead of being silently dropped as "no brand".
--
-- Scope: 4 companies (openai, anthropic, google, xai); 5 brands
-- (gpt, claude, gemini, gemma, grok); 16 accounts (operator-curated
-- real X author_ids for the 16 handles: 2 OpenAI official, 3 OpenAI
-- staff, 2 Anthropic official, 2 Anthropic staff, 2 Google official,
-- 3 Google staff, 1 xAI official, 1 xAI staff).
--
-- Idempotency: every section uses INSERT OR IGNORE. The brand→company
-- join in `brands_companies` and the brand×account cross-product in
-- `brands_accounts` survive re-apply via the PK constraints.
-- Subselect-by-nickname is used for the brand→company join so we
-- do not depend on surrogate ids remaining stable across re-applies.
--
-- hq_country and accent_color are intentionally left NULL (the user
-- prompt did not specify colors; companies can be updated by a
-- follow-up migration mirroring migration 024's accent_color note).
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- Section 1 — companies (4 rows)
-- ===========================================================================

INSERT OR IGNORE INTO companies
    (nickname, display_name, hq_country, created_at,
     display_name_en, display_name_zh_cn)
VALUES
    ('openai',    'OpenAI',    NULL, datetime('now'),
     'OpenAI',    'OpenAI'),
    ('anthropic', 'Anthropic', NULL, datetime('now'),
     'Anthropic', 'Anthropic'),
    ('google',    'Google',    NULL, datetime('now'),
     'Google',    'Google'),
    ('xai',       'xAI',       NULL, datetime('now'),
     'xAI',       'xAI');

-- ===========================================================================
-- Section 2 — brands (5 rows)
-- accent_color intentionally NULL; operator can backfill via a follow-up.
-- ===========================================================================

INSERT OR IGNORE INTO brands
    (nickname, display_name, accent_color, is_sentinel, created_at,
     display_name_en, display_name_zh_cn)
VALUES
    ('gpt',    'GPT',    NULL, 0, datetime('now'),
     'GPT',    'GPT'),
    ('claude', 'Claude', NULL, 0, datetime('now'),
     'Claude', 'Claude'),
    ('gemini', 'Gemini', NULL, 0, datetime('now'),
     'Gemini', 'Gemini'),
    ('gemma',  'Gemma',  NULL, 0, datetime('now'),
     'Gemma',  'Gemma'),
    ('grok',   'Grok',   NULL, 0, datetime('now'),
     'Grok',   'Grok');

-- ===========================================================================
-- Section 3 — brands_companies (5 rows: brand_id × company_id, no duplicates)
-- ===========================================================================

INSERT OR IGNORE INTO brands_companies (brand_id, company_id) VALUES
    ((SELECT id FROM brands    WHERE nickname='gpt'),
     (SELECT id FROM companies WHERE nickname='openai')),
    ((SELECT id FROM brands    WHERE nickname='claude'),
     (SELECT id FROM companies WHERE nickname='anthropic')),
    ((SELECT id FROM brands    WHERE nickname='gemini'),
     (SELECT id FROM companies WHERE nickname='google')),
    ((SELECT id FROM brands    WHERE nickname='gemma'),
     (SELECT id FROM companies WHERE nickname='google')),
    ((SELECT id FROM brands    WHERE nickname='grok'),
     (SELECT id FROM companies WHERE nickname='xai'));

-- ===========================================================================
-- Section 4 — accounts (16 rows; all author_ids are real X/Twitter numeric ids
-- supplied by the operator; verified=NULL is acceptable per schema; bio defaults
-- are NULL).
-- ===========================================================================

INSERT OR IGNORE INTO accounts
    (author_id, handle, display_name, first_seen_at)
VALUES
    -- OpenAI row (col G handles; row covers GPT brand cross-product below)
    ('4398626122',          'OpenAI',         'Main official OpenAI account', datetime('now')),
    ('1633874951508721686', 'OpenAIDevs',     'Official developer/platform updates', datetime('now')),
    ('1605',                'sama',           'Sam Altman',   datetime('now')),
    ('162124540',           'gdb',            'Greg Brockman', datetime('now')),
    ('825088493764407298',  'polynoamial',    'Noam Brown',    datetime('now')),
    -- Anthropic row (col G handles; row covers Claude brand cross-product below)
    ('1353836358901501952', 'AnthropicAI',    'Official Anthropic', datetime('now')),
    ('1943306828697550848', 'claudeai',       'Official Claude',    datetime('now')),
    ('874126509245476864',  'DarioAmodei',    'Dario Amodei',       datetime('now')),
    ('33836629',            'karpathy',       'Andrej Karpathy',    datetime('now')),
    -- Google row (col G handles; row covers Gemini + Gemma brand cross-product below)
    ('1806359170830172162', 'GeminiApp',      'Google Gemini',      datetime('now')),
    ('1908326331609468928', 'googlegemma',    'Official Gemma',     datetime('now')),
    ('1482581556',          'demishassabis',  'Demis Hassabis',     datetime('now')),
    ('14130366',            'sundarpichai',   'Sundar Pichai',      datetime('now')),
    ('284333988',           'OfficialLoganK', 'Logan Kilpatrick',   datetime('now')),
    -- xAI row (col G handles; row covers Grok brand cross-product below)
    ('1720665183188922368', 'grok',           'Official Grok',      datetime('now')),
    ('44196397',            'elonmusk',       'Elon Musk',          datetime('now'));

-- ===========================================================================
-- Section 5 — brands_accounts role=official (9 rows; brand × official-handle
-- cross-product per company row).
--
-- role_id=2 = 'official' (verified via sqlite introspection 2026-07-08).
-- ===========================================================================

INSERT OR IGNORE INTO brands_accounts (brand_id, accounts_id, role_id) VALUES
    -- OpenAI: 1 brand (gpt) × 2 official handles (OpenAI, OpenAIDevs) = 2 rows
    ((SELECT id FROM brands    WHERE nickname='gpt'),
     (SELECT id FROM accounts  WHERE author_id='4398626122'),          2),
    ((SELECT id FROM brands    WHERE nickname='gpt'),
     (SELECT id FROM accounts  WHERE author_id='1633874951508721686'), 2),
    -- Anthropic: 1 brand (claude) × 2 official handles (AnthropicAI, claudeai) = 2 rows
    ((SELECT id FROM brands    WHERE nickname='claude'),
     (SELECT id FROM accounts  WHERE author_id='1353836358901501952'), 2),
    ((SELECT id FROM brands    WHERE nickname='claude'),
     (SELECT id FROM accounts  WHERE author_id='1943306828697550848'), 2),
    -- Google: 2 brands (gemini, gemma) × 2 official handles (GeminiApp, googlegemma) = 4 rows
    ((SELECT id FROM brands    WHERE nickname='gemini'),
     (SELECT id FROM accounts  WHERE author_id='1806359170830172162'), 2),
    ((SELECT id FROM brands    WHERE nickname='gemini'),
     (SELECT id FROM accounts  WHERE author_id='1908326331609468928'), 2),
    ((SELECT id FROM brands    WHERE nickname='gemma'),
     (SELECT id FROM accounts  WHERE author_id='1806359170830172162'), 2),
    ((SELECT id FROM brands    WHERE nickname='gemma'),
     (SELECT id FROM accounts  WHERE author_id='1908326331609468928'), 2),
    -- xAI: 1 brand (grok) × 1 official handle (grok) = 1 row
    ((SELECT id FROM brands    WHERE nickname='grok'),
     (SELECT id FROM accounts  WHERE author_id='1720665183188922368'), 2);

-- ===========================================================================
-- Section 6 — brands_accounts role=staff (12 rows; brand × staff-handle
-- cross-product per company row).
--
-- role_id=3 = 'staff' (verified via sqlite introspection 2026-07-08).
-- ===========================================================================

INSERT OR IGNORE INTO brands_accounts (brand_id, accounts_id, role_id) VALUES
    -- OpenAI: 1 brand (gpt) × 3 staff handles (sama, gdb, polynoamial) = 3 rows
    ((SELECT id FROM brands    WHERE nickname='gpt'),
     (SELECT id FROM accounts  WHERE author_id='1605'),                3),
    ((SELECT id FROM brands    WHERE nickname='gpt'),
     (SELECT id FROM accounts  WHERE author_id='162124540'),          3),
    ((SELECT id FROM brands    WHERE nickname='gpt'),
     (SELECT id FROM accounts  WHERE author_id='825088493764407298'), 3),
    -- Anthropic: 1 brand (claude) × 2 staff handles (DarioAmodei, karpathy) = 2 rows
    ((SELECT id FROM brands    WHERE nickname='claude'),
     (SELECT id FROM accounts  WHERE author_id='874126509245476864'), 3),
    ((SELECT id FROM brands    WHERE nickname='claude'),
     (SELECT id FROM accounts  WHERE author_id='33836629'),            3),
    -- Google: 2 brands (gemini, gemma) × 3 staff handles (demishassabis, sundarpichai, OfficialLoganK) = 6 rows
    ((SELECT id FROM brands    WHERE nickname='gemini'),
     (SELECT id FROM accounts  WHERE author_id='1482581556'),         3),
    ((SELECT id FROM brands    WHERE nickname='gemini'),
     (SELECT id FROM accounts  WHERE author_id='14130366'),           3),
    ((SELECT id FROM brands    WHERE nickname='gemini'),
     (SELECT id FROM accounts  WHERE author_id='284333988'),          3),
    ((SELECT id FROM brands    WHERE nickname='gemma'),
     (SELECT id FROM accounts  WHERE author_id='1482581556'),         3),
    ((SELECT id FROM brands    WHERE nickname='gemma'),
     (SELECT id FROM accounts  WHERE author_id='14130366'),           3),
    ((SELECT id FROM brands    WHERE nickname='gemma'),
     (SELECT id FROM accounts  WHERE author_id='284333988'),          3),
    -- xAI: 1 brand (grok) × 1 staff handle (elonmusk) = 1 row
    ((SELECT id FROM brands    WHERE nickname='grok'),
     (SELECT id FROM accounts  WHERE author_id='44196397'),           3);

-- ===========================================================================
-- End of migration. Section 7 deliberately omitted — `added_at` defaults to
-- NULL on INSERT and we have no per-row timestamp the operator cares about;
-- if NULL was wrong it would be a feature bug, not a schema bug.
-- ===========================================================================

COMMIT;
