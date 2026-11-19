"""Aggregate common signal pairs cheaply while preserving exact rare cases."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

_GROUPED = import_module("core.migrations.0232_each_facts_grouped_build")
_PREVIOUS = import_module("core.migrations.0233_each_facts_cover_index")
SQL_SHA256 = "44cc964d723f1224afb906288d2bbe92bc7ee209bf98c2d48179f17ee7435960"
# Frozen body accepted after same-snapshot physical parity and a 47% staging
# SELECT improvement at default memory. Current source facts remain authoritative.
OPTIMIZED_SELECT = r"""WITH signal_stats AS (
    SELECT g.post_id, g.brand_id, count(*) AS row_count,
        min(g.brand_id::text COLLATE "C") AS brand_min,
        max(g.brand_id::text COLLATE "C") AS brand_max,
        min(nullif(g.sentiment::text, '') COLLATE "C") AS sentiment_min,
        max(nullif(g.sentiment::text, '') COLLATE "C") AS sentiment_max,
        min(g.post_type_key::text COLLATE "C") AS post_type_min
    FROM posts_brands_signals g GROUP BY g.post_id, g.brand_id
), signal_facts AS (
    SELECT stats.post_id, stats.brand_id,
        CASE WHEN stats.row_count=1 THEN ARRAY[stats.post_type_min]
             ELSE ARRAY(SELECT DISTINCT g.post_type_key::text COLLATE "C"
                        FROM posts_brands_signals g
                        WHERE g.post_id=stats.post_id AND g.brand_id=stats.brand_id
                        ORDER BY 1) END AS post_type_keys,
        CASE WHEN stats.brand_min=stats.brand_max THEN ARRAY[stats.brand_min]
             ELSE ARRAY(SELECT literal.spelling FROM (SELECT g.brand_id::text COLLATE "C" AS spelling,
            CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
                 THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=stats.post_id AND g.brand_id=stats.brand_id
        GROUP BY g.brand_id::text COLLATE "C") literal
                        ORDER BY literal.spelling COLLATE "C") END AS brand_ids,
        CASE WHEN stats.brand_min=stats.brand_max THEN ARRAY[
                  CASE WHEN stats.sentiment_min IS NOT DISTINCT FROM stats.sentiment_max
                       THEN stats.sentiment_min END]
             ELSE ARRAY(SELECT literal.sentiment FROM (SELECT g.brand_id::text COLLATE "C" AS spelling,
            CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
                 THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=stats.post_id AND g.brand_id=stats.brand_id
        GROUP BY g.brand_id::text COLLATE "C") literal
                        ORDER BY literal.spelling COLLATE "C") END AS sentiments
    FROM signal_stats stats
), labels AS (
    SELECT l.post_id, l.brand_id,
        array_agg(DISTINCT l.product_label_key::text COLLATE "C"
                  ORDER BY l.product_label_key::text COLLATE "C") AS keys
    FROM posts_brands_product_labels l GROUP BY l.post_id, l.brand_id
), audience AS (
    SELECT a.post_id, a.brand_id,
        array_agg(DISTINCT (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C"
                  ORDER BY (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C") AS edges
    FROM posts_brands_audience_topics a WHERE a.scheme_key='ai_audience_topics/v1'
    GROUP BY a.post_id, a.brand_id
), geo AS (
    SELECT g.post_id, g.brand_id,
        array_agg(g.taxonomy_version::text
                  ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS versions,
        array_agg(g.geopolitical_mode_key::text
                  ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS keys
    FROM posts_brands_geopolitical_modes g GROUP BY g.post_id, g.brand_id
), promotions AS (
    SELECT u.post_id,
        array_agg(item #>> '{}' ORDER BY (item #>> '{}') COLLATE "C") AS keys
    FROM posts_untracked_brand_promotions u
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(u.promotion_keys)='array'
             THEN u.promotion_keys ELSE '[]'::jsonb END
    ) item
    WHERE jsonb_typeof(item)='string' GROUP BY u.post_id
)
SELECT pb.brand_id, pb.post_id, p.created_at, p.lang_detected, p.lang,
    p.author_account_key, (s.post_id IS NOT NULL) AS state_present,
    s.brand_id::text AS state_brand_id,
    s.contract_version AS state_contract_version,
    s.taxonomy_version AS state_taxonomy_version,
    s.outcome AS state_outcome, s.sentiment::text AS state_sentiment,
    COALESCE(signal_facts.brand_ids, ARRAY[]::text[]) AS legacy_sentiment_brand_ids,
    COALESCE(signal_facts.sentiments, ARRAY[]::text[]) AS legacy_sentiment_values,
    COALESCE(signal_facts.post_type_keys, ARRAY[]::text[]) AS post_type_keys,
    COALESCE(labels.keys, ARRAY[]::text[]) AS product_label_keys,
    COALESCE(audience.edges, ARRAY[]::text[]) AS audience_topic_edges,
    COALESCE(geo.versions, ARRAY[]::text[]) AS geopolitical_mode_versions,
    COALESCE(geo.keys, ARRAY[]::text[]) AS geopolitical_mode_keys,
    COALESCE(promotions.keys, ARRAY[]::text[]) AS promotion_keys
FROM posts_brands pb JOIN (SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE (octet_length(tweet_id) <= 256 AND COALESCE(octet_length(lang_detected),0) <= 256 AND COALESCE(octet_length(lang),0) <= 256) UNION ALL SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE NOT (octet_length(tweet_id) <= 256 AND COALESCE(octet_length(lang_detected),0) <= 256 AND COALESCE(octet_length(lang),0) <= 256)) p ON p.tweet_id=pb.post_id
LEFT JOIN posts_brands_classification_states s
    ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
LEFT JOIN signal_facts ON signal_facts.post_id=pb.post_id AND signal_facts.brand_id=pb.brand_id
LEFT JOIN labels ON labels.post_id=pb.post_id AND labels.brand_id=pb.brand_id
LEFT JOIN audience ON audience.post_id=pb.post_id AND audience.brand_id=pb.brand_id
LEFT JOIN geo ON geo.post_id=pb.post_id AND geo.brand_id=pb.brand_id
LEFT JOIN promotions ON promotions.post_id=pb.post_id
WHERE p.created_at < date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'
"""


def forwards(apps, schema_editor):
    _GROUPED.replace_saved_view(schema_editor, OPTIMIZED_SELECT)


def backwards(apps, schema_editor):
    _GROUPED.replace_saved_view(schema_editor, _PREVIOUS.SPLIT_SELECT)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0233_each_facts_cover_index")]
    operations: ClassVar[list] = [migrations.RunPython(forwards, backwards)]
