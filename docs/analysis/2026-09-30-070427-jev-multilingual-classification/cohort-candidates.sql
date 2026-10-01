BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='45s';
WITH language_posts AS MATERIALIZED (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,p.fetched_at,p.text,
        p.lang,p.lang_detected,p.text_en,p.quoted_text,p.quoted_author_handle,
        p.in_reply_to_id,p.is_reply,p.is_quote,
        CASE WHEN coalesce(nullif(lower(p.lang_detected),''),lower(p.lang)) IN ('zh-hans','zh-cn','zh_cn') THEN 'zh-cn'
             ELSE coalesce(nullif(lower(p.lang_detected),''),lower(p.lang)) END AS language
 FROM posts p
 WHERE p.fetched_at < '2026-09-30T07:06:05Z'
   AND nullif(btrim(p.text),'') IS NOT NULL
   AND length(p.text)<=12000
   AND coalesce(nullif(lower(p.lang_detected),''),lower(p.lang)) IN ('ja','zh-hans','zh-cn','zh_cn','ko','en','es','tr')
   AND EXISTS (SELECT 1 FROM posts_brands pb JOIN brands b ON b.nickname=pb.brand_id WHERE pb.post_id=p.tweet_id AND NOT b.is_sentinel)
),
natural_ranked AS (
 SELECT tweet_id,language,row_number() OVER(PARTITION BY language ORDER BY md5(tweet_id||'jev-multilingual-v1-20260930'),tweet_id) AS rank
 FROM language_posts
),
natural AS (SELECT * FROM natural_ranked WHERE rank<=12),
edges AS MATERIALIZED (
 SELECT l.tweet_id,l.language,s.brand_id,'type:'||s.post_type_key AS label
 FROM language_posts l JOIN posts_brands_signals s ON s.post_id=l.tweet_id
 JOIN posts_brands_classification_states c ON c.post_id=s.post_id AND c.brand_id=s.brand_id AND c.taxonomy_version='stage1-taxonomy-v4'
 UNION ALL
 SELECT l.tweet_id,l.language,s.brand_id,'product:'||s.product_label_key
 FROM language_posts l JOIN posts_brands_product_labels s ON s.post_id=l.tweet_id
 UNION ALL
 SELECT l.tweet_id,l.language,s.brand_id,'geo:'||s.geopolitical_mode_key
 FROM language_posts l JOIN posts_brands_geopolitical_modes s ON s.post_id=l.tweet_id
 WHERE s.geopolitical_mode_key NOT IN ('none','unavailable')
 UNION ALL
 SELECT l.tweet_id,l.language,s.brand_id,'topic:'||c.key
 FROM language_posts l JOIN posts_brands_audience_topics s ON s.post_id=l.tweet_id JOIN audience_topic_concepts c ON c.id=s.concept_id
 WHERE c.key NOT IN ('none','unavailable')
 UNION ALL
 SELECT l.tweet_id,l.language,NULL,'promotion:'||k.value
 FROM language_posts l JOIN posts_untracked_brand_promotions s ON s.post_id=l.tweet_id
 CROSS JOIN LATERAL jsonb_array_elements_text(s.promotion_keys) k(value)
 WHERE k.value<>'none'
),
edge_ranked AS (
 SELECT e.*,row_number() OVER(PARTITION BY language,label ORDER BY md5(tweet_id||'jev-coverage-v1-20260930'),tweet_id,brand_id) AS rank
 FROM edges e WHERE NOT EXISTS (SELECT 1 FROM natural n WHERE n.tweet_id=e.tweet_id)
),
selected AS (
 SELECT tweet_id FROM natural UNION SELECT tweet_id FROM edge_ranked WHERE rank=1
),
rows AS (
 SELECT p.*,
   (SELECT n.rank FROM natural n WHERE n.tweet_id=p.tweet_id) AS natural_rank,
   coalesce((SELECT jsonb_agg(DISTINCT jsonb_build_object('brand_id',e.brand_id,'label',e.label)) FROM edges e WHERE e.tweet_id=p.tweet_id),'[]') AS sampling_labels_not_gold,
   coalesce((SELECT jsonb_agg(pb.brand_id ORDER BY pb.brand_id) FROM posts_brands pb JOIN brands b ON b.nickname=pb.brand_id WHERE pb.post_id=p.tweet_id AND NOT b.is_sentinel),'[]') AS brand_ids,
   coalesce((SELECT jsonb_agg(jsonb_build_object('brand_id',ba.brand_id,'role',ba.role_id,'reviewed',true) ORDER BY ba.brand_id,ba.role_id) FROM brands_accounts ba WHERE ba.accounts_id=p.author_id),'[]') AS author_affiliations,
   (SELECT parent.text FROM posts parent WHERE parent.tweet_id=p.in_reply_to_id) AS local_parent_text,
   (SELECT tt.text FROM post_translation_artifacts ta JOIN post_translation_texts tt ON tt.artifact_id=ta.id WHERE ta.post_id=p.tweet_id AND ta.is_current AND ta.state='succeeded' AND tt.locale='en' LIMIT 1) AS normalized_english,
   (SELECT jsonb_build_object('model',ta.model,'prompt_version',ta.prompt_version,'source_language',ta.source_language,'fingerprint',ta.source_content_fingerprint) FROM post_translation_artifacts ta WHERE ta.post_id=p.tweet_id AND ta.is_current AND ta.state='succeeded' LIMIT 1) AS translation_provenance
 FROM language_posts p JOIN selected s USING(tweet_id)
)
SELECT jsonb_build_object(
 'observed_at',statement_timestamp(), 'fetched_before','2026-09-30T07:06:05Z',
 'selection','12 hash-ranked natural posts per language plus one hash-ranked candidate per observed classification label/language. Stored labels are sampling hints only, never gold or Jev input.',
 'eligible_counts',(SELECT jsonb_agg(x) FROM (SELECT language,count(*) AS posts FROM language_posts GROUP BY language ORDER BY language) x),
 'tracked_brands',(SELECT jsonb_agg(jsonb_build_object('brand_id',b.nickname,'display_name',b.display_name) ORDER BY b.nickname) FROM brands b WHERE NOT b.is_sentinel),
 'posts',(SELECT jsonb_agg(r ORDER BY language,natural_rank NULLS LAST,tweet_id) FROM rows r)
);
COMMIT;
