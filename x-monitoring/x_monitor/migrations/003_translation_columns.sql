-- {{AGENT_ATTRIBUTION}}
-- x-monitor v1.7 migration 003: per-locale translation columns + signal.
--
-- v1.7 adds server-side LLM translation of kept posts (en + zh-CN), so
-- the dashboard can render idiomatically in either locale without
-- relying on browser-side translation. The translation pass runs
-- AFTER the per-model relevance filter (Unit 4 of the v1.7 plan), so
-- cost scales with the kept set, not the raw API return volume.
--
-- New columns on `posts`:
--   - text_en        TEXT   -- English translation (NULL if source is en
--                                or translation skipped/failed)
--   - text_zh_cn     TEXT   -- Simplified Chinese translation (NULL if
--                                source is zh-CN or translation skipped)
--   - lang_detected  TEXT   -- ISO 639-1 + optional script, e.g. 'zh-Hans',
--                                'en', 'ja'. NULL until translate pass runs.
--   - signal         TEXT   -- post-fetch classify_signal() result; one
--                                of release | community_question |
--                                criticism | commenter_capture | praise |
--                                other. Replaces the per-query Q1-Q6
--                                expected_signal for new posts.
--
-- Forward-only: old posts keep `text` as the source. The dashboard
-- falls back to `text` when `text_<locale>` is NULL and shows a
-- subtle "(English source)" / "(中文原文)" badge.

ALTER TABLE posts ADD COLUMN text_en        TEXT;
ALTER TABLE posts ADD COLUMN text_zh_cn     TEXT;
ALTER TABLE posts ADD COLUMN lang_detected  TEXT;
ALTER TABLE posts ADD COLUMN signal         TEXT;

-- Backfill-friendly partial indexes. The planner skips rowids that
-- already have a translation, so the x-monitor translate backfill
-- stays cheap as the table grows.
CREATE INDEX IF NOT EXISTS idx_posts_text_en_null
    ON posts(tweet_id)
    WHERE text_en IS NULL;
CREATE INDEX IF NOT EXISTS idx_posts_text_zh_cn_null
    ON posts(tweet_id)
    WHERE text_zh_cn IS NULL;
CREATE INDEX IF NOT EXISTS idx_posts_lang_detected
    ON posts(lang_detected);
CREATE INDEX IF NOT EXISTS idx_posts_signal_model
    ON posts(model_id, signal);
