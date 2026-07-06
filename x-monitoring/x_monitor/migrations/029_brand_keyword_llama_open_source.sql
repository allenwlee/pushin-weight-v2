-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 029: brand-keyword coverage for "Open-source Llama" phrasings.
--
-- Plan: docs/plans/2026-07-06-001-feat-v12-classifier-calibration-plan.md
-- Unit 3 of 5 (U3 — Meta-Llama attribution gap; closes the v11 smoketest's
-- Post 7 miss where "Open-source Llama" / "open-source-llama" / "open-weights
-- Llama" phrasings fell through to the _unattributed sentinel).
--
-- Background:
-- Migration 024 seeded the `llama` brand row in `brands` (nickname='llama',
-- display_name='Meta Llama'). The existing `data/queries/llama.yaml` search
-- queries cover "Llama", "Code Llama", "Meta Llama", "Llama 3/4", "Muse Spark",
-- "Llama 3.1" — but those are FETCH-side tokens, not attribution-side
-- patterns. The attribution layer (`compile_keyword_index` in
-- x_monitor/run.py) joins posts against `brand_keywords` rows, which only
-- had the auto-seeded `enabled_models` entry for 'llama' (literal substring
-- "llama") at the time of the v11 smoketest.
--
-- That meant a post phrased "Open-source Llama 4 just dropped" or
-- "open-source-llama weights are now permissively licensed" failed to
-- attribute: the literal substring "llama" appears in both phrasings, so
-- the auto-seed SHOULD match in theory, but the v11 smoketest transcript
-- at /tmp/smoketest_v11_full.txt (Post 7) shows it didn't in practice
-- against the live keyword index — likely because the case-insensitive
-- auto-seed pattern didn't combine with the multi-word "Open-source" token
-- in the way the attribution regex expected.
--
-- This migration adds explicit regex patterns under the `llama` brand_id
-- that anchor on "Open[- ]source Llama" and "open[- ]weights Llama" so
-- the attribution is robust to the surface vocabulary.
--
-- Schema reference (from sqlite_master on data/monitor.db, 2026-07-06):
--   brand_keywords.brand_id is TEXT FK to brands.nickname (post-migration 023's
--   `brand_id -> nickname` rename; the child column stayed named brand_id
--   per migration 023 lines 32-37, deliberate). No subquery needed —
--   `'llama'` is the FK target value.
--   brand_keywords.added_at is TEXT NOT NULL with no default
--   (migrations/004_company_brand_account_model.sql:150); written explicitly
--   with datetime('now').
--
-- Idempotency: PRIMARY KEY (brand_id, pattern) on brand_keywords
-- (migrations/004:151). INSERT OR IGNORE skips duplicate (brand_id,
-- pattern) pairs on re-application.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- Seed two regex patterns under brand_id='llama'. Both patterns use RE2
-- character classes (no backreferences, no lookaheads) so compile_keyword_index
-- can compile them with re.compile() without a custom engine. The
-- `[- ]` character class covers space or hyphen between tokens, so the
-- same pattern matches "Open-source Llama" (capitalized, spaced) AND
-- "open-source-llama" (lowercase, fully hyphenated). compile_keyword_index
-- compiles with re.IGNORECASE so case differences are normalized.
-- ===========================================================================

INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('llama', 'Open[- ]source[- ]Llama', 1, datetime('now')),
    ('llama', 'open[- ]weights[- ]Llama', 1, datetime('now'));

COMMIT;