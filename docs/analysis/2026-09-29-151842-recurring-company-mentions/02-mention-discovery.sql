BEGIN READ ONLY; SET LOCAL statement_timeout='45s';
WITH source AS MATERIALIZED (
 SELECT tweet_id,author_id,author_handle,is_reply,text
 FROM posts WHERE fetched_at < '2026-09-29T06:19:29.636718+00:00'
), tokens AS (
 SELECT DISTINCT p.tweet_id,p.author_id,p.author_handle,p.is_reply,
 CASE WHEN left(m[1],1)='@' THEN 'handle' ELSE 'domain' END AS kind,
 lower(m[1]) AS token
 FROM source p CROSS JOIN LATERAL regexp_matches(p.text,
 '@[A-Za-z0-9_]+|[A-Za-z0-9][A-Za-z0-9.-]*[.](?:ai|com|io|app|dev|xyz|net|org|co|so)(?![A-Za-z0-9_])','g') m
), counted AS (
 SELECT kind,token,count(*) AS posts,count(DISTINCT author_id) AS authors,
 count(*)FILTER(WHERE NOT coalesce(is_reply,false)) AS nonreply_posts,
 count(*)FILTER(WHERE token='@'||lower(author_handle)) AS self_mentions
 FROM tokens WHERE token NOT IN ('t.co','x.com','twitter.com','www.twitter.com')
 GROUP BY kind,token
), ranked AS (
 SELECT *,row_number()OVER(PARTITION BY kind ORDER BY nonreply_posts DESC,posts DESC,token) AS rank FROM counted
)
SELECT json_build_object('observed_at',statement_timestamp(),'fetched_before','2026-09-29T06:19:29.636718+00:00',
 'rankings',(SELECT json_agg(x ORDER BY kind,rank) FROM ranked x WHERE (kind='handle' AND rank<=160) OR (kind='domain' AND rank<=80)),
 'known_brand_handles',(SELECT json_agg(x) FROM (SELECT lower(a.handle) AS handle,array_agg(DISTINCT ba.brand_id ORDER BY ba.brand_id) AS brands FROM accounts a JOIN brands_accounts ba ON ba.accounts_id=a.author_id JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel GROUP BY lower(a.handle))x)
); COMMIT;
