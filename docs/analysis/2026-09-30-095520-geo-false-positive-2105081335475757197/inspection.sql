BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='20s';
SELECT json_build_object('observed_at',statement_timestamp(),
'post',(SELECT row_to_json(x) FROM (SELECT tweet_id,author_id,author_handle,text,text_en,lang,lang_detected,created_at,fetched_at,is_reply,is_quote,in_reply_to_id,quoted_status_id,quoted_text,quoted_author_handle FROM posts WHERE tweet_id='2105081335475757197') x),
'states',(SELECT json_agg(x) FROM posts_brands_classification_states x WHERE post_id='2105081335475757197'),
'geo_modes',(SELECT json_agg(x) FROM posts_brands_geopolitical_modes x WHERE post_id='2105081335475757197'),
'signals',(SELECT json_agg(x) FROM posts_brands_signals x WHERE post_id='2105081335475757197'),
'judgments',(SELECT json_agg(x ORDER BY created_at,id) FROM posts_brands_classification_judgments x WHERE post_id='2105081335475757197'));
COMMIT;
