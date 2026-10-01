BEGIN READ ONLY; SET LOCAL statement_timeout='30s';
SELECT json_build_object('observed_at',statement_timestamp(),'posts',json_agg(row_to_json(x))) FROM (
 SELECT tweet_id,author_handle,text,
 lower(normalize(text,NFKC)) ~ '#tronecostar\M' AS normalized_tron,
 lower(normalize(text,NFKC)) ~ '(^|[^a-z0-9_])@justinsuntron([^a-z0-9_]|$)' AS normalized_sun
 FROM posts WHERE fetched_at<'2026-09-29T05:57:44.654358Z'
 AND text ~ 'https?://' AND text ~* '(tbh|ngl|honestly|seriously|game[- ]changer|did you know|what are you waiting for|you won.t regret|trust me|not gonna lie)'
 AND NOT (text ~* '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|tronecostar|@bai)([^a-z0-9_]|$)')
 AND lower(normalize(text,NFKC)) ~ '(^|[^a-z0-9_])(@?bai_agi|b[.]ai|@bai)([^a-z0-9_]|$)'
)x; COMMIT;
