BEGIN READ ONLY; SET LOCAL statement_timeout='45s';
WITH author_roles AS (
 SELECT ba.accounts_id,array_agg(DISTINCT ba.role_id::text ORDER BY ba.role_id::text) AS roles
 FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel
 WHERE ba.role_id IN ('official','staff','community') GROUP BY ba.accounts_id
), b AS (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,p.text,p.lang,p.is_reply,
 coalesce(a.roles,ARRAY[]::text[]) AS roles,
 row_number() OVER(ORDER BY md5(p.tweet_id||'bai-contrast-2026-09-29'),p.tweet_id) AS sample_rank
 FROM posts p LEFT JOIN author_roles a ON a.accounts_id=p.author_id
 WHERE p.text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|tronecostar)([^a-z0-9_]|$)'
)
SELECT json_build_object('observed_at',statement_timestamp(),
'population',(SELECT row_to_json(x) FROM (SELECT count(*) AS posts,count(DISTINCT author_id) AS author_ids,count(DISTINCT lower(author_handle)) AS handles,min(created_at) AS first_post,max(created_at) AS last_post,count(*)FILTER(WHERE cardinality(roles)>0) AS known_role_overlap,count(*)FILTER(WHERE is_reply) AS replies FROM b)x),
'language_counts',(SELECT json_agg(x) FROM (SELECT lang,count(*) AS posts FROM b GROUP BY lang ORDER BY posts DESC)x),
'sample',(SELECT json_agg(x ORDER BY sample_rank) FROM (SELECT * FROM b WHERE sample_rank<=24)x));
COMMIT;
