BEGIN READ ONLY; SET LOCAL statement_timeout='30s';
SELECT json_build_object('observed_at',statement_timestamp(),'bai_text_posts',count(*) FILTER(WHERE text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|tronecostar)([^a-z0-9_]|$)'),'bai_entity_posts',count(*) FILTER(WHERE entities::text ~* 'b[.]ai|bai_agi'),'token_machine_posts',count(*) FILTER(WHERE text ILIKE '%Token Machine%')) FROM posts;
SELECT json_build_object('id',tweet_id,'text',text,'entities',entities,'author_id',author_id,'author_handle',author_handle,'quoted_text',quoted_text) FROM posts WHERE tweet_id='2104483144233853085';
COMMIT;
