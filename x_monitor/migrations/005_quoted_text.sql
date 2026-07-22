-- Capture quote-tweet content (2026-06-22).
--
-- TwitterAPI.io returns a quote tweet's referenced post inside a nested
-- `quoted_tweet` object. _normalize_tweet now extracts that object's id
-- (written to `quoted_status_id`, a column that already existed but was
-- always NULL) and its text (this new column). Without this column the
-- quoted body was held in memory and then discarded on write, because the
-- stored `raw` is the flattened normalized fields, not the original item.
--
-- Forward-only: existing posts keep NULL; only newly-fetched quote tweets
-- populate `quoted_text`.

ALTER TABLE posts ADD COLUMN quoted_text TEXT;
