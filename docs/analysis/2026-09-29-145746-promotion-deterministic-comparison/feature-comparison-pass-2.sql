BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='60s';
WITH role_accounts AS (
 SELECT ba.accounts_id,array_agg(DISTINCT ba.role_id::text ORDER BY ba.role_id::text) AS roles
 FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel
 WHERE ba.role_id IN ('official','staff','community') GROUP BY ba.accounts_id
), source AS MATERIALIZED (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,p.lang,p.is_reply,p.text,
 coalesce(a.roles,ARRAY[]::text[]) AS roles,
 replace(lower(normalize(coalesce(p.text,''),NFKC)),'’','''') AS body
 FROM posts p LEFT JOIN role_accounts a ON a.accounts_id=p.author_id
 WHERE p.fetched_at<'2026-09-29T05:57:44.654358Z'
 AND (a.accounts_id IS NOT NULL
 OR p.text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|tronecostar|@bai)([^a-z0-9_]|$)'
 OR (p.text ~ 'https?://' AND p.text ~* '(tbh|ngl|honestly|seriously|game[- ]changer|did you know|what are you waiting for|you won.t regret|trust me|not gonna lie)'))
), identified AS MATERIALIZED (
 SELECT *,body ~ '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)' AS bai,
 body ~ '#tronecostar\M' AS tron,
 body ~ '(^|[^a-z0-9_])@justinsuntron([^a-z0-9_]|$)' AS sun,
 (body ~ '\m(tbh|ngl)\M')::int+(body ~ '\mhonestly\M')::int+(body ~ '\mseriously\M')::int+
 (body ~ '\mgame[- ]changer\M')::int+(body ~ '\mdid you know\M')::int+
 (body ~ '(what are you waiting for|you won''t regret|trust me|not gonna lie)')::int AS filler,
 trim(regexp_replace(regexp_replace(regexp_replace(body,'https?://[^[:space:]]+',' <url> ','g'),'@[a-z0-9_]+',' <handle> ','g'),'\s+',' ','g')) AS template
 FROM source
), cohorted AS MATERIALIZED (
 SELECT i.*,cohort FROM identified i CROSS JOIN LATERAL unnest(roles ||
 CASE WHEN bai THEN ARRAY['bai_explicit'] WHEN tron THEN ARRAY['tron_tag_only'] ELSE ARRAY[]::text[] END) cohort
), slices AS (
 SELECT c.*,slice FROM cohorted c CROSS JOIN LATERAL unnest(
 ARRAY['all'] ||
 CASE WHEN NOT coalesce(is_reply,false) THEN ARRAY['nonreply'] ELSE ARRAY[]::text[] END ||
 CASE WHEN NOT coalesce(is_reply,false) AND created_at>='2026-08-30T05:57:44.654358Z' THEN ARRAY['recent_nonreply'] ELSE ARRAY[]::text[] END ||
 CASE WHEN NOT coalesce(is_reply,false) AND lang='en' THEN ARRAY['english_nonreply'] ELSE ARRAY[]::text[] END) slice
), counts AS (
 SELECT cohort,slice,count(*) AS posts,count(DISTINCT author_id) AS authors,
 percentile_disc(0.5) WITHIN GROUP(ORDER BY length(body)) AS median_chars,
 count(*)FILTER(WHERE length(body)>1000) AS over1000,
 count(*)FILTER(WHERE filler>=2 AND body ~ 'https?://') AS fillers2link,
 count(*)FILTER(WHERE bai AND tron) AS bai_tron,
 count(*)FILTER(WHERE bai AND sun) AS bai_sun,
 count(*)FILTER(WHERE bai AND tron AND sun) AS bai_tron_sun,
 count(*)FILTER(WHERE tron AND sun) AS tron_sun,
 count(*)FILTER(WHERE body ~ '(free|discount|[0-9]+% off|credits|quota)') AS incentive,
 count(*)FILTER(WHERE body ~ '\m(we|our|ours|we''re|we''ve)\M') AS we,
 count(*)FILTER(WHERE body ~ '(available on|free on|access.{0,60} on |available via|now on |integrat.{0,60}with)') AS hosted_access_language
 FROM slices GROUP BY cohort,slice
), substantive_templates AS (
 SELECT cohort,md5(template) AS hash,count(*) AS posts,count(DISTINCT author_id) AS authors,
 min(tweet_id) AS example_id,min(template) AS normalized_text
 FROM cohorted WHERE length(regexp_replace(template,'<(url|handle)>','','g'))>=120
 GROUP BY cohort,template HAVING count(DISTINCT author_id)>=3
), review AS (
 SELECT *,row_number() OVER(PARTITION BY review_group ORDER BY md5(tweet_id||'pass2-review-2026-09-29'),tweet_id) AS rank
 FROM (
 SELECT i.*, review_group FROM identified i CROSS JOIN LATERAL unnest(
 CASE WHEN cardinality(roles)=0 AND NOT bai AND NOT tron AND filler>=2 AND body ~ 'https?://' THEN ARRAY['outside_filler_collisions'] ELSE ARRAY[]::text[] END ||
 CASE WHEN bai AND NOT (tron AND sun) THEN ARRAY['bai_without_full_footer'] ELSE ARRAY[]::text[] END ||
 CASE WHEN bai AND body ~ '(\m(spam|scam|shill)\M|paid.{0,15}(post|promot)|刷屏|骗子|垃圾营销)' THEN ARRAY['bai_criticism_terms'] ELSE ARRAY[]::text[] END ||
 CASE WHEN cardinality(roles)>0 AND sun THEN ARRAY['official_staff_sun'] ELSE ARRAY[]::text[] END
 ) review_group
 ) x
)
SELECT json_build_object(
 'observed_at',statement_timestamp(),'fetched_before','2026-09-29T05:57:44.654358Z',
 'counts',(SELECT json_agg(x ORDER BY cohort,slice) FROM counts x),
 'outside_control',(SELECT json_build_object('ascii_prefilter_candidates',count(*),'two_filler_link_posts',count(*)FILTER(WHERE filler>=2),'two_filler_link_authors',count(DISTINCT author_id)FILTER(WHERE filler>=2)) FROM identified WHERE cardinality(roles)=0 AND NOT bai AND NOT tron),
 'substantive_reuse',(SELECT json_agg(x ORDER BY cohort) FROM (SELECT cohort,count(*) AS template_groups,sum(posts) AS posts FROM substantive_templates GROUP BY cohort)x),
 'substantive_examples',(SELECT json_agg(x ORDER BY cohort,posts DESC,hash) FROM (SELECT *,row_number() OVER(PARTITION BY cohort ORDER BY posts DESC,hash) AS rank FROM substantive_templates)x WHERE rank<=2),
 'review_group_counts',(SELECT json_agg(x) FROM (SELECT review_group,count(*) AS posts FROM review GROUP BY review_group)x),
 'review_posts',(SELECT json_agg(x ORDER BY review_group,rank) FROM (SELECT review_group,rank,tweet_id,author_handle,created_at,lang,is_reply,roles,bai,tron,sun,filler,text FROM review WHERE rank<=8)x),
 'top_bai_authors',(SELECT json_agg(x ORDER BY posts DESC,author_id) FROM (SELECT author_id,min(author_handle) AS example_handle,count(*) AS posts,count(*)FILTER(WHERE tron AND sun) AS full_footer_posts FROM identified WHERE bai GROUP BY author_id ORDER BY posts DESC,author_id LIMIT 12)x)
); COMMIT;
