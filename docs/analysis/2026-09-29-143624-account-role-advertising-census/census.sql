BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '45s';
WITH
observation AS (SELECT statement_timestamp() AS observed_at),
signal_sets AS (
 SELECT post_id,brand_id,array_agg(DISTINCT post_type_key::text ORDER BY post_type_key::text) AS type_keys,
 bool_or(post_type_key='advertising_marketing') AS is_ad,
 bool_or(post_type_key IN ('buzz_releases','hands_on_usage','performance_comparisons','feedback_questions','advertising_marketing','event_announcement')) AS has_legacy
 FROM posts_brands_signals GROUP BY post_id,brand_id
),
pairs AS (
 SELECT pb.post_id,pb.brand_id,p.author_id,p.author_handle,p.created_at,ba.role_id,
 s.contract_version,s.taxonomy_version,s.prompt_version,s.model,s.outcome,s.classified_at,
 coalesce(sig.is_ad,false) AS is_ad,coalesce(sig.type_keys,ARRAY[]::text[]) AS type_keys,
 CASE WHEN s.post_id IS NOT NULL THEN
  CASE WHEN s.contract_version='stage1-v1' AND s.taxonomy_version IN ('stage1-taxonomy-v1','stage1-taxonomy-v2','stage1-taxonomy-v3','stage1-taxonomy-v4') AND s.outcome='classified' THEN 'exact_classified'
       WHEN s.contract_version='stage1-v1' AND s.taxonomy_version IN ('stage1-taxonomy-v1','stage1-taxonomy-v2','stage1-taxonomy-v3','stage1-taxonomy-v4') AND s.outcome='context_missing' THEN 'exact_context_missing'
       ELSE 'unrecognized_state' END
  WHEN sig.has_legacy THEN 'legacy_approximate'
  ELSE 'unversioned_other_or_untyped' END AS era
 FROM posts_brands pb JOIN posts p ON p.tweet_id=pb.post_id
 JOIN brands b ON b.nickname=pb.brand_id AND NOT b.is_sentinel
 LEFT JOIN brands_accounts ba ON ba.accounts_id=p.author_id AND ba.brand_id=pb.brand_id
 LEFT JOIN posts_brands_classification_states s ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
 LEFT JOIN signal_sets sig ON sig.post_id=pb.post_id AND sig.brand_id=pb.brand_id
),
known_pairs AS (SELECT * FROM pairs WHERE role_id IN ('official','staff','community')),
rollup_pairs AS (
 SELECT role_id AS role_group,k.* FROM known_pairs k
 UNION ALL SELECT 'all_known_roles' AS role_group,k.* FROM known_pairs k
),
role_counts AS (SELECT role_group,count(DISTINCT post_id) AS posts,
count(DISTINCT author_id) AS authors,
count(DISTINCT post_id) FILTER(WHERE is_ad) AS stored_ad_posts,
count(*) AS post_brand_pairs,
count(*) FILTER(WHERE is_ad) AS stored_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified') AS exact_classified_posts,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_posts,
count(*) FILTER(WHERE era='exact_classified') AS exact_classified_pairs,
count(*) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_context_missing') AS context_missing_posts,
count(*) FILTER(WHERE era='exact_context_missing') AS context_missing_pairs,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate') AS legacy_posts,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_posts,
count(*) FILTER(WHERE era='legacy_approximate') AS legacy_pairs,
count(*) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_pairs,
count(*) FILTER(WHERE era='unversioned_other_or_untyped') AS unversioned_other_or_untyped_pairs,
count(*) FILTER(WHERE era='unrecognized_state') AS unrecognized_state_pairs FROM rollup_pairs GROUP BY role_group),
recent_counts AS (SELECT role_group,count(DISTINCT post_id) AS posts,
count(DISTINCT author_id) AS authors,
count(DISTINCT post_id) FILTER(WHERE is_ad) AS stored_ad_posts,
count(*) AS post_brand_pairs,
count(*) FILTER(WHERE is_ad) AS stored_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified') AS exact_classified_posts,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_posts,
count(*) FILTER(WHERE era='exact_classified') AS exact_classified_pairs,
count(*) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_context_missing') AS context_missing_posts,
count(*) FILTER(WHERE era='exact_context_missing') AS context_missing_pairs,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate') AS legacy_posts,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_posts,
count(*) FILTER(WHERE era='legacy_approximate') AS legacy_pairs,
count(*) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_pairs,
count(*) FILTER(WHERE era='unversioned_other_or_untyped') AS unversioned_other_or_untyped_pairs,
count(*) FILTER(WHERE era='unrecognized_state') AS unrecognized_state_pairs FROM rollup_pairs,observation WHERE created_at>=observed_at-interval '30 days' AND created_at<observed_at GROUP BY role_group),
brand_counts AS (SELECT role_id,brand_id,count(DISTINCT post_id) AS posts,
count(DISTINCT author_id) AS authors,
count(DISTINCT post_id) FILTER(WHERE is_ad) AS stored_ad_posts,
count(*) AS post_brand_pairs,
count(*) FILTER(WHERE is_ad) AS stored_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified') AS exact_classified_posts,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_posts,
count(*) FILTER(WHERE era='exact_classified') AS exact_classified_pairs,
count(*) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_context_missing') AS context_missing_posts,
count(*) FILTER(WHERE era='exact_context_missing') AS context_missing_pairs,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate') AS legacy_posts,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_posts,
count(*) FILTER(WHERE era='legacy_approximate') AS legacy_pairs,
count(*) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_pairs,
count(*) FILTER(WHERE era='unversioned_other_or_untyped') AS unversioned_other_or_untyped_pairs,
count(*) FILTER(WHERE era='unrecognized_state') AS unrecognized_state_pairs FROM known_pairs GROUP BY role_id,brand_id),
author_counts AS (SELECT role_id,author_id,min(author_handle) AS author_handle,count(DISTINCT post_id) AS posts,

count(DISTINCT post_id) FILTER(WHERE is_ad) AS stored_ad_posts,
count(*) AS post_brand_pairs,
count(*) FILTER(WHERE is_ad) AS stored_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified') AS exact_classified_posts,
count(DISTINCT post_id) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_posts,
count(*) FILTER(WHERE era='exact_classified') AS exact_classified_pairs,
count(*) FILTER(WHERE era='exact_classified' AND is_ad) AS exact_ad_pairs,
count(DISTINCT post_id) FILTER(WHERE era='exact_context_missing') AS context_missing_posts,
count(*) FILTER(WHERE era='exact_context_missing') AS context_missing_pairs,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate') AS legacy_posts,
count(DISTINCT post_id) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_posts,
count(*) FILTER(WHERE era='legacy_approximate') AS legacy_pairs,
count(*) FILTER(WHERE era='legacy_approximate' AND is_ad) AS legacy_ad_pairs,
count(*) FILTER(WHERE era='unversioned_other_or_untyped') AS unversioned_other_or_untyped_pairs,
count(*) FILTER(WHERE era='unrecognized_state') AS unrecognized_state_pairs FROM known_pairs GROUP BY role_id,author_id),
role_inventory AS (
 SELECT ba.role_id,count(*) AS account_brand_links,count(DISTINCT ba.accounts_id) AS accounts
 FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel GROUP BY ba.role_id
),
all_author_posts AS (
 SELECT DISTINCT ba.role_id,p.tweet_id,p.author_id
 FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel JOIN posts p ON p.author_id=ba.accounts_id
 WHERE ba.role_id IN ('official','staff','community')
),
all_author_counts AS (
 SELECT role_id,count(*) AS posts,count(DISTINCT author_id) AS authors,
 count(*) FILTER(WHERE EXISTS(SELECT 1 FROM pairs x WHERE x.post_id=a.tweet_id AND x.is_ad)) AS ad_for_any_non_sentinel_brand
 FROM all_author_posts a GROUP BY role_id
),
type_counts AS (
 SELECT role_id,era,type_key,count(DISTINCT post_id) AS posts,count(*) AS memberships
 FROM known_pairs CROSS JOIN LATERAL unnest(type_keys) type_key GROUP BY role_id,era,type_key
),
provenance AS (
 SELECT role_id,era,contract_version,taxonomy_version,prompt_version,model,count(*) AS pairs,
 count(DISTINCT post_id) AS posts,count(*) FILTER(WHERE is_ad) AS ad_pairs,
 count(DISTINCT post_id) FILTER(WHERE is_ad) AS ad_posts,min(classified_at) AS first_classified,max(classified_at) AS last_classified
 FROM known_pairs GROUP BY role_id,era,contract_version,taxonomy_version,prompt_version,model
),
samples AS (
 SELECT k.*,p.text,p.text_en,row_number() OVER(PARTITION BY role_id,is_ad ORDER BY k.created_at DESC,k.post_id) AS sample_rank
 FROM known_pairs k JOIN posts p ON p.tweet_id=k.post_id WHERE era='exact_classified'
),
post_rollup AS (
 SELECT post_id,bool_or(role_id IN ('official','staff','community')) AS has_known_role,bool_or(is_ad) AS any_ad,
 bool_or(role_id='official') AS official,bool_or(role_id='staff') AS staff,bool_or(role_id='community') AS community
 FROM pairs GROUP BY post_id
)
SELECT json_build_object(
 'schema','account-role-advertising-census/v1',
 'observed_at',(SELECT observed_at FROM observation),
 'database',current_database(),
 'scope','all persisted posts; no date cutoff; non-sentinel brands; same-brand role and advertising matches; distinct post counts',
 'query_source_revision','97ffe7f',
 'population',(SELECT row_to_json(x) FROM (SELECT count(*) AS database_posts,min(created_at) AS earliest_post,max(created_at) AS latest_post,count(*) FILTER(WHERE created_at IS NULL) AS missing_dates FROM posts) x),
 'post_rollup',(SELECT row_to_json(x) FROM (SELECT count(*) AS non_sentinel_brand_posts,count(*) FILTER(WHERE any_ad) AS any_ad_posts,count(*) FILTER(WHERE has_known_role) AS known_role_posts,count(*) FILTER(WHERE has_known_role AND any_ad) AS known_role_any_brand_ad_posts,count(*) FILTER(WHERE official AND staff) AS official_staff_overlap_posts,count(*) FILTER(WHERE NOT coalesce(has_known_role,false)) AS no_known_role_posts FROM post_rollup) x),
 'role_inventory',(SELECT json_agg(x ORDER BY role_id) FROM role_inventory x),
 'all_posts_by_known_authors',(SELECT json_agg(x ORDER BY role_id) FROM all_author_counts x),
 'by_role',(SELECT json_agg(x ORDER BY role_group) FROM role_counts x),
 'last_30_days_by_role',(SELECT json_agg(x ORDER BY role_group) FROM recent_counts x),
 'by_brand',(SELECT json_agg(x ORDER BY role_id,brand_id) FROM brand_counts x),
 'by_author',(SELECT json_agg(x ORDER BY role_id,stored_ad_posts DESC,author_handle) FROM author_counts x),
 'stored_types',(SELECT json_agg(x ORDER BY role_id,era,posts DESC,type_key) FROM type_counts x),
 'provenance',(SELECT json_agg(x ORDER BY role_id,era,prompt_version) FROM provenance x),
 'recent_examples',(SELECT json_agg(x ORDER BY role_id,is_ad DESC,created_at DESC,post_id) FROM (SELECT role_id,post_id,brand_id,author_handle,created_at,is_ad,type_keys,prompt_version,text,text_en FROM samples WHERE sample_rank<=3 ORDER BY role_id,is_ad DESC,sample_rank) x)
);
COMMIT;
