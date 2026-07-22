-- {{AGENT_ATTRIBUTION}}
-- x-monitor initial schema (migration 001).
-- Posts are append-only with tweet_id PK. Accounts are derived, regenerated
-- on every run. account_post_appearances is the join table for the per-account
-- graph. There is NO review_queue table — review state lives in
-- data/_review_queue.json (single source of truth, R25).

CREATE TABLE IF NOT EXISTS posts (
    tweet_id            TEXT PRIMARY KEY,
    model_id            TEXT NOT NULL,
    author_handle       TEXT NOT NULL,
    author_id           TEXT,
    text                TEXT,
    lang                TEXT,
    created_at          TEXT,
    fetched_at          TEXT NOT NULL,
    favorite_count      INTEGER DEFAULT 0,
    retweet_count       INTEGER DEFAULT 0,
    reply_count         INTEGER DEFAULT 0,
    quote_count         INTEGER DEFAULT 0,
    in_reply_to_user_id TEXT,
    quoted_status_id    TEXT,
    conversation_id     TEXT,
    entities            TEXT,   -- JSON
    source_query_id     TEXT,
    raw                 TEXT    -- JSON of the full Apify response row
);

CREATE INDEX IF NOT EXISTS idx_posts_model_created
    ON posts(model_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_posts_author
    ON posts(author_handle);

CREATE TABLE IF NOT EXISTS accounts (
    model_id              TEXT NOT NULL,
    handle                TEXT NOT NULL,
    display_name          TEXT,
    role                  TEXT NOT NULL DEFAULT 'unknown',
    verified              INTEGER NOT NULL DEFAULT 0,
    bio_contains_brand    INTEGER NOT NULL DEFAULT 0,
    engagement_tier       TEXT NOT NULL DEFAULT 'low',
    multi_brand_voice     INTEGER NOT NULL DEFAULT 0,
    first_seen_at         TEXT,
    last_seen_at          TEXT,
    source_query_ids      TEXT,   -- JSON list
    notes                 TEXT,
    PRIMARY KEY(model_id, handle)
);

CREATE INDEX IF NOT EXISTS idx_accounts_model
    ON accounts(model_id);

CREATE TABLE IF NOT EXISTS account_post_appearances (
    model_id    TEXT NOT NULL,
    handle      TEXT NOT NULL,
    tweet_id    TEXT NOT NULL,
    role_at_time TEXT,
    PRIMARY KEY(model_id, handle, tweet_id),
    FOREIGN KEY(model_id, handle) REFERENCES accounts(model_id, handle) ON DELETE CASCADE,
    FOREIGN KEY(tweet_id) REFERENCES posts(tweet_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_apa_model
    ON account_post_appearances(model_id, handle);
