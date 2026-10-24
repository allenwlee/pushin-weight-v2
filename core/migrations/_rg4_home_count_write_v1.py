"""Do not capture full Post rows for geography-only updates.

The homepage generation is a version, not a row or statement count. Rare Post
identity/date corrections advance it per changed row; relationship bulk writes
retain their existing statement-level invalidation. No transition row sets are
built for Post updates, including large source-copy batches.
"""

SQL = """
CREATE OR REPLACE FUNCTION home_counts_post_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE changed_since timestamptz;
BEGIN
    changed_since := least(OLD.created_at, NEW.created_at);
    IF changed_since IS NOT NULL THEN
        UPDATE materialization_state SET source_generation = source_generation + 1,
            dirty_since = least(dirty_since, changed_since)
            WHERE dataset_key = 'home.brand_time_counts.v1';
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER home_counts_update ON posts;
CREATE TRIGGER home_counts_update AFTER UPDATE ON posts FOR EACH ROW
WHEN (OLD.tweet_id IS DISTINCT FROM NEW.tweet_id OR OLD.created_at IS DISTINCT FROM NEW.created_at)
EXECUTE FUNCTION home_counts_post_update();
"""


def install(apps, schema_editor):
    schema_editor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    schema_editor.execute(SQL)
