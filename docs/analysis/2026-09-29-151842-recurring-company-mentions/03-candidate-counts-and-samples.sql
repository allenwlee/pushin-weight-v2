BEGIN READ ONLY; SET LOCAL statement_timeout='45s';
WITH candidates(name,pattern) AS (VALUES ('Xpert Systems','\m(xpert[ ]?systems|xpertsystems|llama xpert)\M'),('AINFT','\m(ainft|ainftcom)\M'),('BTTInferGrid','\mbttinfergrid\M'),('ENGY','\m(engy|engyai)\M'),('Pollo AI','\m(pollo[ ]?ai|itspolloai|polloaijp)\M'),('Higgsfield','\m(higgsfield|higgsfield_ai)\M'),('Topview','\m(topview|topviewai|topviewaihq)\M'),('PixVerse','\m(pixverse|pixverse_)\M'),('Mia AI','\m(miaai_lab|mia[ ]ai)\M'),('OnSolo','\monsolo\M'),('AntSeed','\mantseed\M'),('SOMA','\m(somasubnet|soma subnet)\M'),('Sogni','\m(sogni|sogni_protocol)\M'),('OpenRouter','\mopenrouter\M'),('OpenCode','\m(opencode|open[ ]code)\M'),('Freebuff','\mfreebuff\M'),('ZenMux','\mzenmux\M'),('Routeway','\mrouteway\M'),('Token Machine','\mtoken machine\M'),('HarnessRouter','\mharnessrouter\M'),('CcVibe','\m(ccvibe|cc-vibe)\M'),('Account-sales pitch','(推特账号.{0,20}(购买|出售)|ins账号购买|谷歌账号购买|twitter account.{0,15}(purchase|sale)|buy.{0,15}twitter account)'),('Posting-software pitch','(推特发帖软件|推特营销软件|X账号管理软件|Twitter营销工具|twitter posting software|twitter marketing tool)')),
source AS MATERIALIZED (
 SELECT tweet_id,author_id,author_handle,created_at,is_reply,lang,text
 FROM posts WHERE fetched_at < '2026-09-29T06:19:29.636718+00:00' AND text ~* '(\m(xpert[ ]?systems|xpertsystems|llama xpert)\M)|(\m(ainft|ainftcom)\M)|(\mbttinfergrid\M)|(\m(engy|engyai)\M)|(\m(pollo[ ]?ai|itspolloai|polloaijp)\M)|(\m(higgsfield|higgsfield_ai)\M)|(\m(topview|topviewai|topviewaihq)\M)|(\m(pixverse|pixverse_)\M)|(\m(miaai_lab|mia[ ]ai)\M)|(\monsolo\M)|(\mantseed\M)|(\m(somasubnet|soma subnet)\M)|(\m(sogni|sogni_protocol)\M)|(\mopenrouter\M)|(\m(opencode|open[ ]code)\M)|(\mfreebuff\M)|(\mzenmux\M)|(\mrouteway\M)|(\mtoken machine\M)|(\mharnessrouter\M)|(\m(ccvibe|cc-vibe)\M)|((推特账号.{0,20}(购买|出售)|ins账号购买|谷歌账号购买|twitter account.{0,15}(purchase|sale)|buy.{0,15}twitter account))|((推特发帖软件|推特营销软件|X账号管理软件|Twitter营销工具|twitter posting software|twitter marketing tool))'
), matched AS MATERIALIZED (
 SELECT c.name,p.*,
 text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)' AS bai,
 text ~* '#tronecostar\M' AS tron,
 md5(trim(regexp_replace(regexp_replace(regexp_replace(lower(text),'https?://[^[:space:]]+',' <url> ','g'),'@[a-z0-9_]+',' <handle> ','g'),'\s+',' ','g'))) AS template
 FROM source p JOIN candidates c ON p.text ~* c.pattern
), counts AS (
 SELECT name,count(*) AS posts,count(DISTINCT author_id) AS authors,
 count(*)FILTER(WHERE NOT coalesce(is_reply,false)) AS nonreply_posts,
 count(*)FILTER(WHERE bai) AS bai_overlap,count(*)FILTER(WHERE tron) AS tron_tag_overlap,
 count(*)FILTER(WHERE created_at>='2026-08-30T06:19:29.636718Z') AS recent_30d_posts,
 count(DISTINCT template) AS normalized_bodies,
 min(created_at) AS first_post,max(created_at) AS last_post FROM matched GROUP BY name
), authors AS (
 SELECT *,row_number() OVER(PARTITION BY name ORDER BY posts DESC,author_id) AS rank FROM (
 SELECT name,author_id,min(author_handle) AS example_handle,count(*) AS posts FROM matched GROUP BY name,author_id)x
), samples AS (
 SELECT *,row_number()OVER(PARTITION BY name ORDER BY md5(tweet_id||'company-mention-review-2026-09-29'),tweet_id) AS rank
 FROM matched WHERE NOT coalesce(is_reply,false)
)
SELECT json_build_object('observed_at',statement_timestamp(),'fetched_before','2026-09-29T06:19:29.636718+00:00',
 'counts',(SELECT json_agg(x ORDER BY posts DESC,name) FROM counts x),
 'top_authors',(SELECT json_agg(x ORDER BY name,rank) FROM authors x WHERE rank<=2),
 'sample_posts',(SELECT json_agg(x ORDER BY name,rank) FROM (
 SELECT name,rank,tweet_id,author_id,author_handle,created_at,lang,bai,tron,left(text,6000) AS text,length(text)>6000 AS text_truncated FROM samples WHERE rank<=3)x)
); COMMIT;
