BEGIN READ ONLY; SET LOCAL statement_timeout='45s';
SELECT json_build_object('observed_at',statement_timestamp(),
 'inventory',(SELECT json_build_object('posts',count(*),'first_post',min(created_at),'last_post',max(created_at),'entities_present',count(*)FILTER(WHERE entities IS NOT NULL),'raw_handle_bodies',count(*)FILTER(WHERE text LIKE '%@%')) FROM posts),
 'tables',(SELECT json_agg(table_name) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('posts_brands_mentions','brand_discovery_candidates','brand_discovery_candidate_tokens','untracked_brand_promotion_evidence')),
 'tracked_brands',(SELECT json_agg(nickname ORDER BY nickname) FROM brands WHERE NOT is_sentinel),
 'candidate_names',(SELECT json_agg(x ORDER BY source_posts DESC,id) FROM (SELECT id,observed_name,aliases,candidate_handles,verification_status,jsonb_array_length(source_identities) AS source_posts FROM brand_discovery_candidates ORDER BY source_posts DESC,id LIMIT 100)x),
 'evidence_inventory',(SELECT json_build_object('rows',count(*),'posts',count(DISTINCT source_post_id),'candidates',count(DISTINCT brand_discovery_candidate_id)) FROM untracked_brand_promotion_evidence)
); COMMIT;
