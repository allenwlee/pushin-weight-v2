BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='45s';
WITH counts AS (
 SELECT coalesce(nullif(lower(lang_detected),''),nullif(lower(lang),''),'unknown') AS effective_language,
        lang_detected,lang,count(*) AS posts,
        count(*) FILTER (WHERE nullif(btrim(text),'') IS NOT NULL) AS with_text,
        count(*) FILTER (WHERE nullif(btrim(text_en),'') IS NOT NULL) AS with_legacy_english
 FROM posts GROUP BY 1,2,3
)
SELECT jsonb_build_object(
 'observed_at',statement_timestamp(),
 'database',current_database(),
 'total_posts',(SELECT sum(posts) FROM counts),
 'created_min',(SELECT min(created_at) FROM posts),
 'created_max',(SELECT max(created_at) FROM posts),
 'groups',(SELECT jsonb_agg(c ORDER BY posts DESC,effective_language,lang_detected,lang) FROM counts c)
);
COMMIT;
