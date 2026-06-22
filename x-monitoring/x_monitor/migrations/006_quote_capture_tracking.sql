-- Quote-tweet capture tracking + created_at_epoch (2026-06-22).
--
-- last_quote_count_seen / last_quote_fetched_at: per-post state for the
-- reactive (official) and daily (non-official) QT-capture regimes. The
-- reactive trigger compares a freshly-observed quote_count against
-- last_quote_count_seen; last_quote_fetched_at seeds the sinceTime of the
-- next /twitter/tweet/quotes call so successive fetches return only new
-- QTs. Written by Store.update_quote_tracking (a dedicated UPDATE), NOT
-- insert_posts, because posts uses INSERT OR IGNORE and a post is re-seen
-- many times as its quote_count grows.
--
-- created_at_epoch: unix-second epoch parsed from the Twitter-format
-- created_at. Time-window queries (polarity windows, the QT daily-pass
-- recency window) filter on this integer because string-comparing the
-- Twitter-format created_at against ISO bounds sorts incorrectly and
-- silently ignored the polarity time window pre-006. New rows are
-- populated by insert_posts; existing rows are backfilled by
-- scripts/2026-06-22-140225-backfill-created-at-epoch.py (SQLite cannot
-- parse the Twitter format in pure SQL).
--
-- Forward-only: existing posts get DEFAULT 0 / NULL / NULL.

ALTER TABLE posts ADD COLUMN last_quote_count_seen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN last_quote_fetched_at TEXT;
ALTER TABLE posts ADD COLUMN created_at_epoch INTEGER;
