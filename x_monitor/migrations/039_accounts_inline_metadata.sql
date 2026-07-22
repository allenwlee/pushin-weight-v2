-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 039: add 13 inline author metadata columns to accounts.
-- These fields are already present in every TwitterAPI.io tweet response's
-- `author` object; the pipeline just wasn't persisting them. No new API calls.
--
-- Plan: docs/plans/2026-07-17-001-feat-account-metadata-inline-persistence-plan.md
--
-- post_step_touches: accounts
--
-- Columns added (all nullable; pre-existing rows stay NULL until next fetch):
--   Engagement counters  (INTEGER): followers_count, following_count,
--     favourites_count, statuses_count, media_count, fast_followers_count
--   Profile metadata     (TEXT): verified_type, profile_picture, location,
--     description, profile_bio_text
--   Verification detail  (INTEGER): is_blue_verified
--   Freshness tracker    (TEXT): followers_fetched_at
--
-- KTD7: this file's first non-comment line after header is
--   `-- post_step_touches: accounts`
--   so the U4 runner fires the JSON export after apply.

BEGIN;

ALTER TABLE accounts ADD COLUMN followers_count INTEGER;
ALTER TABLE accounts ADD COLUMN following_count INTEGER;
ALTER TABLE accounts ADD COLUMN favourites_count INTEGER;
ALTER TABLE accounts ADD COLUMN statuses_count INTEGER;
ALTER TABLE accounts ADD COLUMN media_count INTEGER;
ALTER TABLE accounts ADD COLUMN fast_followers_count INTEGER;

ALTER TABLE accounts ADD COLUMN is_blue_verified INTEGER;
ALTER TABLE accounts ADD COLUMN verified_type TEXT;
ALTER TABLE accounts ADD COLUMN profile_picture TEXT;
ALTER TABLE accounts ADD COLUMN location TEXT;
ALTER TABLE accounts ADD COLUMN description TEXT;
ALTER TABLE accounts ADD COLUMN profile_bio_text TEXT;

ALTER TABLE accounts ADD COLUMN followers_fetched_at TEXT;

COMMIT;
