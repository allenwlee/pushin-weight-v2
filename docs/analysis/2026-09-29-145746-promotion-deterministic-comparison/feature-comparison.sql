BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='60s';
WITH
role_accounts AS (
 SELECT ba.accounts_id,array_agg(DISTINCT ba.role_id::text ORDER BY ba.role_id::text) AS roles
 FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel
 WHERE ba.role_id IN ('official','staff','community') GROUP BY ba.accounts_id
),
source AS (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,p.lang,p.is_reply,p.text,
 coalesce(a.roles,ARRAY[]::text[]) AS roles,
 replace(lower(normalize(coalesce(p.text,''),NFKC)),'’','''') AS body
 FROM posts p LEFT JOIN role_accounts a ON a.accounts_id=p.author_id
 WHERE p.fetched_at<'2026-09-29T05:57:44.654358Z'
),
identified AS (
 SELECT *,body ~ '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)' AS bai,
 body ~ '#tronecostar\M' AS tron
 FROM source
),
cohorted AS (
 SELECT i.*,cohort FROM identified i CROSS JOIN LATERAL unnest(
 roles || CASE WHEN bai THEN ARRAY['bai_explicit'] WHEN tron THEN ARRAY['tron_tag_only'] ELSE ARRAY[]::text[] END ||
 CASE WHEN cardinality(roles)=0 AND NOT bai AND NOT tron THEN ARRAY['other_unlabelled'] ELSE ARRAY[]::text[] END
 ) cohort
),
features AS (
 SELECT *,length(body) AS chars,
 regexp_count(body,'https?://') AS links,
 body ~ '\m(we|our|ours|we''re|we''ve)\M' AS ownership_we,
 body ~ '\m(i|my|i''m|i''ve)\M' AS personal_i,
 body ~ '(^|\n)\s*(hey|hi|hello)[ ,]+(everyone|guys|folks|all|there)\M' AS greeting,
 body ~ '\m(tbh|ngl)\M' AS tbh_ngl,
 body ~ '\mhonestly\M' AS honestly,
 body ~ '\mseriously\M' AS seriously,
 body ~ '\mgame[- ]changer\M' AS game_changer,
 body ~ '\mdid you know\M' AS did_you_know,
 body ~ '(what are you waiting for|you won''t regret|trust me|not gonna lie)' AS reassurance,
 body ~ '(head over|check it out|give it a try|try it now)' AS generic_cta,
 body ~ '(free|discount|[0-9]+% off|credits|quota)' AS incentive,
 body ~ '\m(introducing|announcing|we launched|we released|our latest)\M' AS launch_ownership,
 body ~ '(^|[^a-z0-9_])@justinsuntron([^a-z0-9_]|$)' AS sun_tag,
 md5(trim(regexp_replace(regexp_replace(regexp_replace(body,'https?://[^[:space:]]+',' <url> ','g'),'@[a-z0-9_]+',' <handle> ','g'),'\s+',' ','g'))) AS template_hash
 FROM cohorted
),
scored AS (
 SELECT *,tbh_ngl::int+honestly::int+seriously::int+game_changer::int+did_you_know::int+reassurance::int AS filler_families
 FROM features
),
templates AS (
 SELECT cohort,template_hash,count(*) AS posts,count(DISTINCT coalesce(author_id,'handle:'||lower(author_handle))) AS authors,min(created_at) AS first_at,max(created_at) AS last_at,
 array_agg(tweet_id ORDER BY created_at,tweet_id) AS ids
 FROM scored WHERE cohort<>'other_unlabelled'
 GROUP BY cohort,template_hash HAVING count(*)>=2
),
feature_counts AS (
 SELECT cohort,count(*) AS posts,count(DISTINCT coalesce(author_id,'handle:'||lower(author_handle))) AS authors,
 count(*) FILTER(WHERE lang='en') AS english_posts,
 percentile_disc(0.5) WITHIN GROUP(ORDER BY chars) AS median_chars,
 percentile_disc(0.9) WITHIN GROUP(ORDER BY chars) AS p90_chars,
 count(*)FILTER(WHERE chars>600) AS over_600_chars,
 count(*)FILTER(WHERE chars>1000) AS over_1000_chars,
 count(*)FILTER(WHERE links>0) AS has_link,
 count(*)FILTER(WHERE links>=3) AS three_links,
 count(*)FILTER(WHERE ownership_we) AS ownership_we,
 count(*)FILTER(WHERE personal_i) AS personal_i,
 count(*)FILTER(WHERE greeting) AS greeting,
 count(*)FILTER(WHERE tbh_ngl) AS tbh_ngl,
 count(*)FILTER(WHERE honestly) AS honestly,
 count(*)FILTER(WHERE seriously) AS seriously,
 count(*)FILTER(WHERE game_changer) AS game_changer,
 count(*)FILTER(WHERE did_you_know) AS did_you_know,
 count(*)FILTER(WHERE reassurance) AS reassurance,
 count(*)FILTER(WHERE generic_cta) AS generic_cta,
 count(*)FILTER(WHERE incentive) AS incentive,
 count(*)FILTER(WHERE launch_ownership) AS launch_ownership,
 count(*)FILTER(WHERE sun_tag) AS sun_tag,
 count(*)FILTER(WHERE filler_families>=2 AND links>0) AS filler_2_plus_link,
 count(*)FILTER(WHERE filler_families>=3 AND links>0) AS filler_3_plus_link,
 count(*)FILTER(WHERE filler_families>=2 AND links>0 AND NOT ownership_we) AS filler_2_link_no_we,
 count(*)FILTER(WHERE is_reply) AS replies
 FROM scored GROUP BY cohort
),
collisions AS (
 SELECT cohort,tweet_id,author_id,author_handle,created_at,text,roles,bai,tron,filler_families,ownership_we,
 row_number() OVER(PARTITION BY cohort ORDER BY md5(tweet_id||'collision-review-2026-09-29'),tweet_id) AS sample_rank
 FROM scored WHERE filler_families>=2 AND links>0 AND cohort<>'bai_explicit'
)
SELECT json_build_object(
 'observed_at',statement_timestamp(),
 'fetched_before','2026-09-29T05:57:44.654358Z',
 'cohort_definitions','official/staff from current account links; bai_explicit from NFKC-normalized B.AI/@BAI_AGI/@BAI; tron_tag_only from #TRONEcoStar without explicit BAI; other_unlabelled remainder. Roles may overlap campaign cohorts.',
 'feature_counts',(SELECT json_agg(x ORDER BY cohort) FROM feature_counts x),
 'duplicate_summary',(SELECT json_agg(x ORDER BY cohort) FROM (SELECT cohort,count(*) AS repeated_templates,sum(posts) AS posts_in_repeated_templates,count(*)FILTER(WHERE authors>=3) AS templates_3plus_authors,coalesce(sum(posts)FILTER(WHERE authors>=3),0) AS posts_in_3plus_author_templates FROM templates GROUP BY cohort)x),
 'largest_templates',(SELECT json_agg(x ORDER BY cohort,posts DESC,template_hash) FROM (SELECT *,row_number() OVER(PARTITION BY cohort ORDER BY posts DESC,template_hash) AS rank FROM templates) x WHERE rank<=5),
 'candidate_collisions',(SELECT json_agg(x ORDER BY cohort,sample_rank) FROM collisions x WHERE sample_rank<=12),
 'official_bai_overlap',(SELECT json_agg(x ORDER BY created_at,tweet_id) FROM (SELECT tweet_id,author_handle,created_at,text,roles,bai,tron FROM identified WHERE cardinality(roles)>0 AND (bai OR tron)) x)
);
COMMIT;
