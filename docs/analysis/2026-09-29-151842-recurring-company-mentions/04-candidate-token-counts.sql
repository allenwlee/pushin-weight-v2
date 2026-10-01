BEGIN READ ONLY; SET LOCAL statement_timeout='45s';
WITH aliases(name,alias) AS (VALUES ('Xpert Systems','xpert systems'),('Xpert Systems','xpertsystems'),('Xpert Systems','llama xpert'),('AINFT','ainft'),('AINFT','ainftcom'),('BTTInferGrid','bttinfergrid'),('ENGY','engy'),('ENGY','engyai'),('Pollo AI','pollo ai'),('Pollo AI','polloai'),('Pollo AI','itspolloai'),('Pollo AI','polloaijp'),('Higgsfield','higgsfield'),('Higgsfield','higgsfield_ai'),('Topview','topview'),('Topview','topviewai'),('Topview','topviewaihq'),('PixVerse','pixverse'),('PixVerse','pixverse_'),('Mia AI','miaai_lab'),('Mia AI','mia ai'),('OnSolo','onsolo'),('AntSeed','antseed'),('SOMA','somasubnet'),('SOMA','soma subnet'),('Sogni','sogni'),('Sogni','sogni_protocol'),('OpenRouter','openrouter'),('OpenCode','opencode'),('OpenCode','open code'),('Freebuff','freebuff'),('ZenMux','zenmux'),('Routeway','routeway'),('Token Machine','token machine'),('HarnessRouter','harnessrouter'),('CcVibe','ccvibe'),('CcVibe','cc-vibe'),('Account-sales terms','推特账号'),('Account-sales terms','ins账号购买'),('Account-sales terms','谷歌账号购买'),('Account-sales terms','twitter account purchase'),('Account-sales terms','twitter account sales'),('Account-sales terms','buy twitter accounts'),('Posting-software terms','推特发帖软件'),('Posting-software terms','推特营销软件'),('Posting-software terms','x账号管理软件'),('Posting-software terms','twitter营销工具'),('Posting-software terms','twitter posting software'),('Posting-software terms','twitter marketing tool')),
hits AS MATERIALIZED (
 SELECT DISTINCT p.tweet_id,p.author_id,p.author_handle,p.created_at,p.is_reply,p.lang,p.text,a.name
 FROM posts p CROSS JOIN LATERAL regexp_matches(p.text,'\m(?:twitter account purchase|twitter posting software|twitter marketing tool|twitter account sales|buy twitter accounts|sogni_protocol|xpert systems|higgsfield_ai|token machine|harnessrouter|xpertsystems|bttinfergrid|llama xpert|topviewaihq|soma subnet|itspolloai|higgsfield|somasubnet|openrouter|polloaijp|topviewai|pixverse_|miaai_lab|open code|ainftcom|pollo ai|pixverse|opencode|freebuff|routeway|polloai|topview|antseed|cc-vibe|engyai|mia ai|onsolo|zenmux|ccvibe|ainft|sogni|engy)\M|推特账号|ins账号购买|谷歌账号购买|推特发帖软件|推特营销软件|x账号管理软件|twitter营销工具','gi') m
 JOIN aliases a ON a.alias=lower(m[1])
 WHERE p.fetched_at<'2026-09-29T06:19:29.636718+00:00'
), counts AS (
 SELECT name,count(*) AS posts,count(DISTINCT author_id) AS authors,
 count(*)FILTER(WHERE NOT coalesce(is_reply,false)) AS nonreply_posts,
 count(*)FILTER(WHERE text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)') AS bai_overlap,
 count(*)FILTER(WHERE text ~* '#tronecostar\M') AS tron_tag_overlap,
 count(*)FILTER(WHERE created_at>='2026-08-30T06:19:29.636718Z') AS recent_30d_posts,
 count(DISTINCT text) AS distinct_raw_bodies,
 min(created_at) AS first_post,max(created_at) AS last_post FROM hits GROUP BY name
), authors AS (
 SELECT *,row_number() OVER(PARTITION BY name ORDER BY posts DESC,author_id) AS rank FROM (
 SELECT name,author_id,min(author_handle) AS example_handle,count(*) AS posts FROM hits GROUP BY name,author_id)x
), samples AS (
 SELECT *,row_number()OVER(PARTITION BY name ORDER BY md5(tweet_id||'company-mention-review-2026-09-29'),tweet_id) AS rank
 FROM hits WHERE NOT coalesce(is_reply,false)
)
SELECT json_build_object('observed_at',statement_timestamp(),'fetched_before','2026-09-29T06:19:29.636718+00:00',
 'counts',(SELECT json_agg(x ORDER BY posts DESC,name) FROM counts x),
 'top_authors',(SELECT json_agg(x ORDER BY name,rank) FROM authors x WHERE rank<=2),
 'sample_posts',(SELECT json_agg(x ORDER BY name,rank) FROM (
 SELECT name,rank,tweet_id,author_id,author_handle,created_at,lang,left(text,4500) AS text,length(text)>4500 AS text_truncated FROM samples WHERE rank<=3)x)
); COMMIT;
