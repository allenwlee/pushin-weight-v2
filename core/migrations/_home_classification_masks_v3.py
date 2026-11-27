"""Frozen rebuildable post-level chart projection for classification filters.

Aligned arrays retain the brand/category pairing, including orphan evidence.
The underlying state, signals, labels and post-brand links remain authoritative.
"""
from core.migrations._home_sentiment_masks_v1 import BUILD_SQL, CUTOFF, SOURCE_SQL, CONTRACT, TAXONOMIES


def _once(source, before, after):
    if source.count(before) != 1:
        raise RuntimeError(f'Unexpected classification projection anchor: {before!r}')
    return source.replace(before, after)


_VALID = f"state.contract_version={CONTRACT} AND state.taxonomy_version IN {TAXONOMIES} AND state.outcome='classified'"
_RECENT = "date_bin('2 hours', transaction_timestamp(), '2000-01-01 00:00:00+00'::timestamptz) - interval '15 minutes'"
_COLUMNS = '''COALESCE(types.brand_ids, ARRAY[]::text[]) AS type_brand_ids,
       COALESCE(types.keys, ARRAY[]::text[]) AS type_keys,
       COALESCE(products.brand_ids, ARRAY[]::text[]) AS product_brand_ids,
       COALESCE(products.keys, ARRAY[]::text[]) AS product_keys,
       COALESCE(no_products.brand_ids, ARRAY[]::text[]) AS no_product_brand_ids'''


def _pair_aggregates(key):
    order = f'edge.brand_id::text COLLATE "C", edge.{key}::text COLLATE "C"'
    return (f'array_agg(edge.brand_id::text ORDER BY {order}) AS brand_ids, '
            f'array_agg(edge.{key}::text ORDER BY {order}) AS keys')


def _pair_source(table, key):
    return f'''SELECT {_pair_aggregates(key)}
    FROM {table} edge JOIN posts_brands_classification_states state
      ON state.post_id=edge.post_id AND state.brand_id=edge.brand_id
    WHERE edge.post_id=p.tweet_id AND {_VALID}'''


def _pair_build(table, key):
    return f'''SELECT edge.post_id, {_pair_aggregates(key)}
    FROM {table} edge JOIN posts_brands_classification_states state
      ON state.post_id=edge.post_id AND state.brand_id=edge.brand_id
    WHERE {_VALID} GROUP BY edge.post_id'''

_NO_PRODUCTS = f'''FROM posts_brands edge JOIN posts_brands_classification_states state
  ON state.post_id=edge.post_id AND state.brand_id=edge.brand_id
WHERE {_VALID} AND NOT EXISTS (SELECT 1 FROM posts_brands_product_labels label
  WHERE label.post_id=edge.post_id AND label.brand_id=edge.brand_id)'''

SOURCE = _once(SOURCE_SQL, 'CREATE VIEW home_post_sentiment_facts_source AS',
               'CREATE VIEW home_post_classification_facts_source AS')
SOURCE = _once(SOURCE, '(x.post_id IS NOT NULL) AS legacy_flag',
               '(x.post_id IS NOT NULL) AS legacy_flag,\n       ' + _COLUMNS)
SOURCE = _once(SOURCE, 'LEFT JOIN posts_untracked_brand_promotions u ON', f'''
CROSS JOIN LATERAL ({_pair_source('posts_brands_signals', 'post_type_key')}) types
CROSS JOIN LATERAL ({_pair_source('posts_brands_product_labels', 'product_label_key')}) products
CROSS JOIN LATERAL (SELECT array_agg(edge.brand_id::text ORDER BY edge.brand_id::text COLLATE "C") AS brand_ids
  {_NO_PRODUCTS} AND edge.post_id=p.tweet_id) no_products
LEFT JOIN posts_untracked_brand_promotions u ON''')

BUILD = _once(BUILD_SQL, 'CREATE MATERIALIZED VIEW home_post_sentiment_facts AS',
              'CREATE MATERIALIZED VIEW home_post_classification_facts AS')
BUILD = _once(BUILD, CUTOFF, _RECENT)
BUILD = _once(BUILD, '\nSELECT pb.post_id,p.created_at,', f''', types AS MATERIALIZED (
    {_pair_build('posts_brands_signals', 'post_type_key')}
), products AS MATERIALIZED (
    {_pair_build('posts_brands_product_labels', 'product_label_key')}
), no_products AS MATERIALIZED (
    SELECT edge.post_id,array_agg(edge.brand_id::text ORDER BY edge.brand_id::text COLLATE "C") AS brand_ids
    {_NO_PRODUCTS} GROUP BY edge.post_id
)
SELECT pb.post_id,p.created_at,''')
BUILD = _once(BUILD, '(x.post_id IS NOT NULL) AS legacy_flag',
              '(x.post_id IS NOT NULL) AS legacy_flag,\n       ' + _COLUMNS)
BUILD = _once(BUILD, 'LEFT JOIN posts_untracked_brand_promotions u ON', '''LEFT JOIN types ON types.post_id=pb.post_id
LEFT JOIN products ON products.post_id=pb.post_id
LEFT JOIN no_products ON no_products.post_id=pb.post_id
LEFT JOIN posts_untracked_brand_promotions u ON''')
