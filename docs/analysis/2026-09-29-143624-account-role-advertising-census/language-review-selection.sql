BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='30s';
WITH author_roles AS (
 SELECT ba.accounts_id,array_agg(DISTINCT ba.role_id::text ORDER BY ba.role_id::text) AS roles,
 jsonb_agg(jsonb_build_object('brand',ba.brand_id,'role',ba.role_id) ORDER BY ba.brand_id) AS affiliations
 FROM brands_accounts ba JOIN brands b ON b.nickname=ba.brand_id AND NOT b.is_sentinel
 WHERE ba.role_id IN ('official','staff','community') GROUP BY ba.accounts_id
),
ranked AS (
 SELECT p.tweet_id,p.author_id,p.author_handle,p.created_at,p.text,p.text_en,p.lang,p.is_reply,p.quoted_text,p.quoted_author_handle,p.in_reply_to_id,
 a.roles,a.affiliations,
 row_number() OVER(PARTITION BY p.author_id,coalesce(p.is_reply,false) ORDER BY p.created_at DESC,p.tweet_id) AS recent_rank,
 row_number() OVER(PARTITION BY p.author_id,coalesce(p.is_reply,false) ORDER BY md5(p.tweet_id||'promotion-language-review-2026-09-29'),p.tweet_id) AS stable_rank
 FROM posts p JOIN author_roles a ON a.accounts_id=p.author_id
),
selected AS (
 SELECT r.*,parent.text AS local_parent_text
 FROM ranked r LEFT JOIN posts parent ON parent.tweet_id=r.in_reply_to_id
 WHERE (NOT coalesce(r.is_reply,false) AND (r.recent_rank<=3 OR r.stable_rank=1))
 OR (r.is_reply AND r.recent_rank=1)
)
SELECT json_build_object(
 'observed_at',statement_timestamp(),
 'selection','Per known author: three newest non-replies, one deterministic hash-selected non-reply, newest reply; overlaps deduplicated. No stored classifications queried or filtered.',
 'posts',(SELECT json_agg(s ORDER BY roles,author_handle,created_at DESC,tweet_id) FROM selected s));
COMMIT;
