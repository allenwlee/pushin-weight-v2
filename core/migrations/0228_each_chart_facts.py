"""Rebuildable Each facts; native source rows remain authoritative."""

from typing import ClassVar

from django.db import migrations

SOURCE_TABLES = (
    "posts",
    "posts_brands",
    "posts_brands_classification_states",
    "posts_brands_signals",
    "posts_brands_product_labels",
    "posts_brands_audience_topics",
    "posts_brands_geopolitical_modes",
    "posts_untracked_brand_promotions",
)
COLUMNS = """brand_id, post_id, created_at, lang_detected, lang,
    author_account_key, state_present, state_brand_id, state_contract_version,
    state_taxonomy_version, state_outcome, state_sentiment,
    legacy_sentiment_brand_ids, legacy_sentiment_values, post_type_keys,
    product_label_keys, audience_topic_edges, geopolitical_mode_versions,
    geopolitical_mode_keys, promotion_keys"""
VIEW_SQL = """
SET LOCAL lock_timeout = '2s';
INSERT INTO materialization_state(dataset_key, source_generation)
VALUES ('each.brand_post_facts.v1', 0) ON CONFLICT DO NOTHING;
CREATE VIEW each_brand_post_facts_source AS
SELECT pb.brand_id, pb.post_id, p.created_at, p.lang_detected, p.lang,
    p.author_account_key, (s.post_id IS NOT NULL) AS state_present,
    s.brand_id::text AS state_brand_id,
    s.contract_version AS state_contract_version,
    s.taxonomy_version AS state_taxonomy_version,
    s.outcome AS state_outcome, s.sentiment::text AS state_sentiment,
    COALESCE(legacy.brand_ids, ARRAY[]::text[]) AS legacy_sentiment_brand_ids,
    COALESCE(legacy.sentiments, ARRAY[]::text[]) AS legacy_sentiment_values,
    ARRAY(SELECT DISTINCT g.post_type_key::text COLLATE "C"
          FROM posts_brands_signals g
          WHERE g.post_id=pb.post_id AND g.brand_id=pb.brand_id
          ORDER BY 1) AS post_type_keys,
    ARRAY(SELECT DISTINCT l.product_label_key::text COLLATE "C"
          FROM posts_brands_product_labels l
          WHERE l.post_id=pb.post_id AND l.brand_id=pb.brand_id
          ORDER BY 1) AS product_label_keys,
    ARRAY(SELECT DISTINCT (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C"
          FROM posts_brands_audience_topics a
          WHERE a.post_id=pb.post_id AND a.brand_id=pb.brand_id
          AND a.scheme_key='ai_audience_topics/v1'
          ORDER BY 1) AS audience_topic_edges,
    COALESCE(geo.versions, ARRAY[]::text[]) AS geopolitical_mode_versions,
    COALESCE(geo.keys, ARRAY[]::text[]) AS geopolitical_mode_keys,
    ARRAY(SELECT item #>> '{}' FROM jsonb_array_elements(
          CASE WHEN jsonb_typeof(u.promotion_keys)='array'
               THEN u.promotion_keys ELSE '[]'::jsonb END) item
          WHERE jsonb_typeof(item)='string' ORDER BY (item #>> '{}') COLLATE "C") AS promotion_keys
FROM posts_brands pb JOIN posts p ON p.tweet_id=pb.post_id
LEFT JOIN posts_brands_classification_states s
  ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
LEFT JOIN posts_untracked_brand_promotions u ON u.post_id=pb.post_id
LEFT JOIN LATERAL (
    SELECT array_agg(v.brand_id ORDER BY v.brand_id COLLATE "C") AS brand_ids,
           array_agg(v.sentiment ORDER BY v.brand_id COLLATE "C") AS sentiments
    FROM (
        SELECT g.brand_id::text COLLATE "C" AS brand_id,
            CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
                 THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=pb.post_id AND g.brand_id=pb.brand_id
        GROUP BY g.brand_id::text COLLATE "C"
    ) v
) legacy ON TRUE
LEFT JOIN LATERAL (
    SELECT array_agg(g.taxonomy_version::text ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS versions,
           array_agg(g.geopolitical_mode_key::text ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS keys
    FROM posts_brands_geopolitical_modes g
    WHERE g.post_id=pb.post_id AND g.brand_id=pb.brand_id
) geo ON TRUE;
"""
VIEW_SQL += f"""
CREATE MATERIALIZED VIEW each_brand_post_facts AS
SELECT {COLUMNS} FROM each_brand_post_facts_source
WHERE created_at < date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'
WITH NO DATA;
CREATE UNIQUE INDEX each_brand_post_facts_key ON each_brand_post_facts(brand_id, post_id);
CREATE INDEX each_brand_post_facts_window ON each_brand_post_facts(brand_id, created_at);
"""
TRIGGER_SQL = """
CREATE FUNCTION each_facts_invalidate() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
    changed_since timestamptz;
    post_key text;
    candidate timestamptz;
BEGIN
    IF TG_OP='TRUNCATE' THEN
        changed_since := '0001-01-01 00:00:00+00'::timestamptz;
    ELSIF TG_TABLE_NAME='posts' THEN
        changed_since := least(OLD.created_at,NEW.created_at);
    ELSE
        IF TG_OP <> 'INSERT' THEN
            post_key := OLD.post_id;
            SELECT p.created_at INTO candidate FROM posts p WHERE p.tweet_id=post_key;
            IF NOT FOUND THEN candidate := '0001-01-01 00:00:00+00'::timestamptz; END IF;
            changed_since := candidate;
        END IF;
        IF TG_OP <> 'DELETE' THEN
            post_key := NEW.post_id;
            SELECT p.created_at INTO candidate FROM posts p WHERE p.tweet_id=post_key;
            IF NOT FOUND THEN candidate := '0001-01-01 00:00:00+00'::timestamptz; END IF;
            changed_since := least(changed_since,candidate);
        END IF;
    END IF;
    IF changed_since < date_trunc('day', clock_timestamp(), 'UTC') - interval '1 day' THEN
        UPDATE materialization_state SET source_generation=source_generation+1,
            dirty_since=least(dirty_since,changed_since)
        WHERE dataset_key='each.brand_post_facts.v1';
    END IF;
    RETURN NULL;
END
$fn$;
CREATE FUNCTION each_facts_brand_identity() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    IF EXISTS ((SELECT nickname COLLATE "C" FROM old_rows EXCEPT SELECT nickname COLLATE "C" FROM new_rows)
        UNION ALL (SELECT nickname COLLATE "C" FROM new_rows EXCEPT SELECT nickname COLLATE "C" FROM old_rows)) THEN
        UPDATE materialization_state SET source_generation=source_generation+1,
            dirty_since='0001-01-01 00:00:00+00'::timestamptz
        WHERE dataset_key='each.brand_post_facts.v1';
    END IF;
    RETURN NULL;
END
$fn$;
CREATE TRIGGER each_facts_brand_identity AFTER UPDATE ON brands
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT EXECUTE FUNCTION each_facts_brand_identity();
CREATE TRIGGER each_facts_truncate AFTER TRUNCATE ON brands
FOR EACH STATEMENT EXECUTE FUNCTION each_facts_invalidate();
"""
# Field ownership and actual SQL columns are frozen in this migration.
UPDATE_COLUMNS = {
    "posts": [
        ("tweet_id", True),
        ("created_at", False),
        ("lang_detected", True),
        ("lang", True),
        ("author_account_key", False),
    ],
    "posts_brands": [("post_id", True), ("brand_id", True)],
    "posts_brands_classification_states": [
        (x, True)
        for x in (
            "post_id",
            "brand_id",
            "contract_version",
            "taxonomy_version",
            "outcome",
            "sentiment",
        )
    ],
    "posts_brands_signals": [
        (x, True) for x in ("post_id", "brand_id", "post_type_key", "sentiment")
    ],
    "posts_brands_product_labels": [
        (x, True) for x in ("post_id", "brand_id", "product_label_key")
    ],
    "posts_brands_audience_topics": [
        ("post_id", True),
        ("brand_id", True),
        ("concept_id", False),
        ("scheme_key", True),
        ("scheme_revision", False),
    ],
    "posts_brands_geopolitical_modes": [
        (x, True)
        for x in ("post_id", "brand_id", "geopolitical_mode_key", "taxonomy_version")
    ],
    "posts_untracked_brand_promotions": [("post_id", True), ("promotion_keys", False)],
}
REVERSE_SQL = "SET LOCAL lock_timeout = '2s';\nDROP TRIGGER each_facts_brand_identity ON brands;\nDROP TRIGGER each_facts_truncate ON brands;\n"
for table in SOURCE_TABLES:
    for event in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
        if table == "posts" and event in ("INSERT", "DELETE"):
            continue
        condition = ""
        if event == "UPDATE":
            changes = []
            for column, binary in UPDATE_COLUMNS[table]:
                collate = ' COLLATE "C"' if binary else ""
                changes.append(
                    f"OLD.{column}{collate} IS DISTINCT FROM NEW.{column}{collate}"
                )
            condition = " WHEN (" + " OR ".join(changes) + ")"
        level = "STATEMENT" if event == "TRUNCATE" else "ROW"
        TRIGGER_SQL += f"CREATE TRIGGER each_facts_{event.lower()} AFTER {event} ON {table} FOR EACH {level}{condition} EXECUTE FUNCTION each_facts_invalidate();\n"
        REVERSE_SQL += f"DROP TRIGGER each_facts_{event.lower()} ON {table};\n"
REVERSE_SQL += """
DROP FUNCTION each_facts_brand_identity();
DROP FUNCTION each_facts_invalidate();
DROP MATERIALIZED VIEW each_brand_post_facts;
DROP VIEW each_brand_post_facts_source;
DELETE FROM materialization_state WHERE dataset_key='each.brand_post_facts.v1';
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0227_post_translation_requested")]
    operations: ClassVar[list] = [
        migrations.RunSQL(VIEW_SQL + TRIGGER_SQL, REVERSE_SQL)
    ]
