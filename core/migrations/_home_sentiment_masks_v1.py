"""Frozen exact Post-level sentiment projection for the v1 saved dataset.

The data is a rebuildable query projection; the underlying PostBrand, state
and signal tables remain authoritative. Keep this definition immutable once
its migration is released.
"""

CONTRACT = "'stage1-v1'"
TAXONOMIES = "('stage1-taxonomy-v1','stage1-taxonomy-v2','stage1-taxonomy-v3','stage1-taxonomy-v4')"
CUTOFF = "date_trunc('day',transaction_timestamp(),'UTC') - interval '1 day'"

# The live relation is parameterized by its enclosing Post; readers constrain
# that Post by an indexed date range or by a bounded set of dirty primary keys.
SOURCE_SQL = f"""
CREATE VIEW home_post_sentiment_facts_source AS
SELECT p.tweet_id AS post_id,p.created_at,
       COALESCE(pairs.brands, ARRAY[]::text[]) AS brands,
       COALESCE(pairs.unclassified, ARRAY[]::text[]) AS unclassified,
       COALESCE(masks.positive, ARRAY[]::text[]) AS positive,
       COALESCE(masks.negative, ARRAY[]::text[]) AS negative,
       COALESCE(masks.neutral, ARRAY[]::text[]) AS neutral,
       COALESCE(masks.mixed, ARRAY[]::text[]) AS mixed,
       (u.post_id IS NOT NULL) AS promotion_flag,
       (x.post_id IS NOT NULL) AS legacy_flag
FROM posts p
CROSS JOIN LATERAL (
    SELECT count(*) AS pair_count,
           array_agg(b.nickname::text ORDER BY b.nickname::text COLLATE "C") AS brands,
           array_agg(pb.brand_id::text ORDER BY pb.brand_id::text COLLATE "C") FILTER (
               WHERE NOT COALESCE(s.contract_version={CONTRACT}
                   AND s.taxonomy_version IN {TAXONOMIES}
                   AND s.outcome='classified',false)) AS unclassified
    FROM posts_brands pb JOIN brands b ON b.nickname=pb.brand_id
    LEFT JOIN posts_brands_classification_states s
      ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
    WHERE pb.post_id=p.tweet_id
) pairs
CROSS JOIN LATERAL (
    SELECT array_agg(e.brand_id ORDER BY e.brand_id COLLATE "C") FILTER (WHERE e.sentiment='positive') AS positive,
           array_agg(e.brand_id ORDER BY e.brand_id COLLATE "C") FILTER (WHERE e.sentiment='negative') AS negative,
           array_agg(e.brand_id ORDER BY e.brand_id COLLATE "C") FILTER (WHERE e.sentiment='neutral') AS neutral,
           array_agg(e.brand_id ORDER BY e.brand_id COLLATE "C") FILTER (WHERE e.sentiment='mixed') AS mixed
    FROM (
        SELECT s.brand_id::text AS brand_id,s.sentiment::text AS sentiment
        FROM posts_brands_classification_states s
        WHERE s.post_id=p.tweet_id AND s.contract_version={CONTRACT}
          AND s.taxonomy_version IN {TAXONOMIES} AND s.sentiment IS NOT NULL
        UNION ALL
        SELECT g.brand_id::text,min(g.sentiment::text) AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=p.tweet_id AND g.sentiment IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM posts_brands_classification_states s
                          WHERE s.post_id=g.post_id AND s.brand_id=g.brand_id)
        GROUP BY g.post_id,g.brand_id HAVING count(DISTINCT g.sentiment)=1
    ) e
) masks
LEFT JOIN posts_untracked_brand_promotions u ON u.post_id=p.tweet_id
LEFT JOIN posts_unsanctioned_flags x ON x.post_id=p.tweet_id
WHERE pairs.pair_count > 0
"""

# A set-based build avoids the source view's per-Post lookups during a rebuild.
BUILD_SQL = f"""
CREATE MATERIALIZED VIEW home_post_sentiment_facts AS
WITH paired AS MATERIALIZED (
    SELECT pb.post_id,
        array_agg(b.nickname::text ORDER BY b.nickname::text COLLATE "C") AS brands,
        array_agg(pb.brand_id::text ORDER BY pb.brand_id::text COLLATE "C") FILTER (
            WHERE NOT COALESCE(s.contract_version={CONTRACT}
                AND s.taxonomy_version IN {TAXONOMIES}
                AND s.outcome='classified',false)) AS unclassified
    FROM posts_brands pb JOIN brands b ON b.nickname=pb.brand_id
    LEFT JOIN posts_brands_classification_states s
      ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
    GROUP BY pb.post_id
), legacy AS MATERIALIZED (
    SELECT g.post_id,g.brand_id,min(g.sentiment::text) AS sentiment
    FROM posts_brands_signals g
    WHERE g.sentiment IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM posts_brands_classification_states s
        WHERE s.post_id=g.post_id AND s.brand_id=g.brand_id)
    GROUP BY g.post_id,g.brand_id HAVING count(DISTINCT g.sentiment)=1
), evidence AS MATERIALIZED (
    SELECT s.post_id,s.brand_id::text AS brand_id,s.sentiment::text AS sentiment
    FROM posts_brands_classification_states s WHERE s.contract_version={CONTRACT}
      AND s.taxonomy_version IN {TAXONOMIES} AND s.sentiment IS NOT NULL
    UNION ALL SELECT post_id,brand_id::text,sentiment FROM legacy
), masks AS MATERIALIZED (
    SELECT post_id,
        array_agg(brand_id ORDER BY brand_id COLLATE "C") FILTER (WHERE sentiment='positive') AS positive,
        array_agg(brand_id ORDER BY brand_id COLLATE "C") FILTER (WHERE sentiment='negative') AS negative,
        array_agg(brand_id ORDER BY brand_id COLLATE "C") FILTER (WHERE sentiment='neutral') AS neutral,
        array_agg(brand_id ORDER BY brand_id COLLATE "C") FILTER (WHERE sentiment='mixed') AS mixed
    FROM evidence GROUP BY post_id
)
SELECT pb.post_id,p.created_at,
       COALESCE(pb.brands, ARRAY[]::text[]) AS brands,
       COALESCE(pb.unclassified, ARRAY[]::text[]) AS unclassified,
       COALESCE(m.positive, ARRAY[]::text[]) AS positive,
       COALESCE(m.negative, ARRAY[]::text[]) AS negative,
       COALESCE(m.neutral, ARRAY[]::text[]) AS neutral,
       COALESCE(m.mixed, ARRAY[]::text[]) AS mixed,
       (u.post_id IS NOT NULL) AS promotion_flag,
       (x.post_id IS NOT NULL) AS legacy_flag
FROM paired pb JOIN posts p ON p.tweet_id=pb.post_id
LEFT JOIN masks m ON m.post_id=pb.post_id
LEFT JOIN posts_untracked_brand_promotions u ON u.post_id=pb.post_id
LEFT JOIN posts_unsanctioned_flags x ON x.post_id=pb.post_id
WHERE p.created_at < {CUTOFF}
WITH NO DATA;
"""
