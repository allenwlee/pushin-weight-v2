BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='35s';
WITH selected AS MATERIALIZED (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,
 lower(normalize(coalesce(p.text,''),NFKC)) AS body
 FROM posts p WHERE p.fetched_at<'2026-09-29T05:57:44.654358Z'
 AND (p.text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|tronecostar|@bai)([^a-z0-9_]|$)'
 OR p.tweet_id IN ('2076601240524354013','2089412475821195620','2090479074422452290','2104662951785316505'))
), bai AS (
 SELECT * FROM selected
 WHERE body ~ '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)'
), authors AS (
 SELECT author_id,min(author_handle) AS example_post_handle,count(*) AS posts,
 count(*)FILTER(WHERE body ~ '#tronecostar\M' AND body ~ '(^|[^a-z0-9_])@justinsuntron([^a-z0-9_]|$)') AS campaign_posts
 FROM bai GROUP BY author_id
), joined AS (
 SELECT r.*,a.handle AS current_handle,a.followers_count,a.followers_fetched_at,
 CASE WHEN a.author_id IS NULL THEN 'missing_account'
 WHEN a.followers_count IS NULL THEN 'missing_followers'
 WHEN a.followers_count<0 THEN 'invalid_followers' ELSE 'known' END AS availability,
 CASE WHEN a.followers_count IS NULL OR a.followers_count<0 THEN 99
 WHEN a.followers_count<100 THEN 1 WHEN a.followers_count<1000 THEN 2
 WHEN a.followers_count<5000 THEN 3 WHEN a.followers_count<10000 THEN 4
 WHEN a.followers_count<50000 THEN 5 WHEN a.followers_count<100000 THEN 6
 ELSE 7 END AS bucket
 FROM authors r LEFT JOIN accounts a ON a.author_id=r.author_id
), binned AS (
 SELECT bucket,count(*) AS accounts,sum(posts) AS posts,
 count(*)FILTER(WHERE campaign_posts>0) AS campaign_accounts,sum(campaign_posts) AS campaign_posts
 FROM joined GROUP BY bucket
)
SELECT json_build_object(
 'observed_at',statement_timestamp(),'post_fetched_before','2026-09-29T05:57:44.654358Z',
 'cohort','Prior 7,303 identified B.AI-associated post comparison: original raw-marker prefilter plus four saved Unicode-only IDs; not all spam-labelled posts.',
 'totals',(SELECT json_build_object('accounts',count(*),'posts',sum(posts),
 'known_followers',count(*)FILTER(WHERE availability='known'),
 'missing_followers',count(*)FILTER(WHERE availability<>'known'),
 'unknown_author_groups',count(*)FILTER(WHERE author_id IS NULL),
 'zero_followers',count(*)FILTER(WHERE followers_count=0),
 'campaign_accounts',count(*)FILTER(WHERE campaign_posts>0),'campaign_posts',sum(campaign_posts),
 'median_followers',percentile_cont(0.5)WITHIN GROUP(ORDER BY followers_count)FILTER(WHERE availability='known'),
 'p25_followers',percentile_cont(0.25)WITHIN GROUP(ORDER BY followers_count)FILTER(WHERE availability='known'),
 'p75_followers',percentile_cont(0.75)WITHIN GROUP(ORDER BY followers_count)FILTER(WHERE availability='known'),
 'p90_followers',percentile_cont(0.90)WITHIN GROUP(ORDER BY followers_count)FILTER(WHERE availability='known'),
 'mean_followers',avg(followers_count)FILTER(WHERE availability='known'),
 'min_followers',min(followers_count)FILTER(WHERE availability='known'),
 'max_followers',max(followers_count)FILTER(WHERE availability='known'),
 'followers_timestamp_missing',count(*)FILTER(WHERE availability='known' AND followers_fetched_at IS NULL),
 'followers_observed_min',min(followers_fetched_at),'followers_observed_max',max(followers_fetched_at),
 'followers_observed_past7days',count(*)FILTER(WHERE followers_fetched_at>=statement_timestamp()-interval '7 days'),
 'followers_observed_past30days',count(*)FILTER(WHERE followers_fetched_at>=statement_timestamp()-interval '30 days')
 ) FROM joined),
 'bins',(SELECT json_agg(x ORDER BY bucket) FROM binned x),
 'authors',(SELECT json_agg(x ORDER BY followers_count DESC NULLS LAST,author_id) FROM joined x)
); COMMIT;
