BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='35s';
WITH selected AS MATERIALIZED (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,
 lower(normalize(coalesce(p.text,''),NFKC)) AS body
 FROM posts p WHERE p.fetched_at<'2026-09-29T05:57:44.654358Z'
 AND (p.text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|tronecostar|@bai)([^a-z0-9_]|$)'
 OR p.tweet_id IN ('2076601240524354013','2089412475821195620','2090479074422452290','2104662951785316505'))
), bai AS MATERIALIZED (
 SELECT *,body ~ '#tronecostar\M' AND body ~ '(^|[^a-z0-9_])@justinsuntron([^a-z0-9_]|$)' AS campaign_signature,
 md5(tweet_id||'bai-signal-2026-09-29') AS selection_key
 FROM selected WHERE body ~ '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)'
), main AS MATERIALIZED (
 SELECT *,row_number()OVER(ORDER BY selection_key,tweet_id) AS sample_rank
 FROM bai ORDER BY selection_key,tweet_id LIMIT 40
), exceptions AS MATERIALIZED (
 SELECT *,row_number()OVER(ORDER BY selection_key,tweet_id) AS sample_rank
 FROM bai WHERE NOT campaign_signature AND tweet_id NOT IN(SELECT tweet_id FROM main)
 ORDER BY selection_key,tweet_id LIMIT 10
), chosen AS (
 SELECT 'main' AS sample_group,* FROM main
 UNION ALL SELECT 'exceptions' AS sample_group,* FROM exceptions
), rows AS (
 SELECT c.sample_group,c.sample_rank,c.selection_key,c.tweet_id,c.author_id,c.author_handle,c.created_at,c.campaign_signature,
 p.text,p.text_en,p.lang,p.is_reply,p.is_quote,p.in_reply_to_id,p.quoted_text,p.quoted_author_handle,
 q.text AS stored_quote_post_text,r.text AS stored_reply_parent_text,
 (p.extended_entities IS NOT NULL AND p.extended_entities::text NOT IN ('{}','null')) AS stored_media_metadata_present,
 (p.card IS NOT NULL AND p.card::text NOT IN ('{}','null')) AS stored_card_metadata_present,
 (SELECT json_agg(json_build_object('brand',ba.brand_id,'role',ba.role_id)) FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel WHERE ba.accounts_id=c.author_id AND ba.role_id IN('official','staff','community')) AS known_roles
 FROM chosen c JOIN posts p ON p.tweet_id=c.tweet_id
 LEFT JOIN posts q ON q.tweet_id=p.quoted_status_id
 LEFT JOIN posts r ON r.tweet_id=p.in_reply_to_id
)
SELECT json_build_object('observed_at',statement_timestamp(),
'cohort',(SELECT json_build_object('posts',count(*),'authors',count(DISTINCT author_id),'campaign_signature_posts',count(*)FILTER(WHERE campaign_signature),'first_post',min(created_at),'last_post',max(created_at)) FROM bai),
'rows',(SELECT json_agg(x ORDER BY sample_group DESC,sample_rank) FROM rows x));
COMMIT;

