-- {{AGENT_ATTRIBUTION}}
-- x-monitor v1.2 migration 002: article headline columns on posts.
--
-- Adds headline (the article title fetched from the URL) and
-- headline_source (one of: "fetched", "cached", "url_only",
-- "fetch_failed") so the dashboard can render a meaningful preview
-- for URL-only posts without mutating the original `text` column
-- (which is what we want for FTS, full-text fallback, and the
-- per-query 'n_url_only_posts' counter).
--
-- The partial index targets the backfill subcommand: it lets the
-- planner skip the rowids that already have a headline, so the
-- backfill stays cheap even as the table grows.

ALTER TABLE posts ADD COLUMN headline TEXT;
ALTER TABLE posts ADD COLUMN headline_source TEXT;

-- Backfill-friendly index. Posts with no URL-only text don't need
-- to be in the index; the WHERE clause keeps it small.
CREATE INDEX IF NOT EXISTS idx_posts_headline_null_urlonly
    ON posts(tweet_id)
    WHERE headline IS NULL AND text GLOB 'https*';
