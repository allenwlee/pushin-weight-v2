BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='45s';
SELECT jsonb_build_object(
 'observed_at',statement_timestamp(),
 'brands',(SELECT jsonb_agg(jsonb_build_object(
   'brand_id',b.nickname,'names',jsonb_build_array(b.nickname,b.display_name,b.display_name_en,b.display_name_zh_cn),
   'search_terms',coalesce((SELECT jsonb_agg(s.term ORDER BY s.term) FROM brand_search_terms s WHERE s.brand_id=b.nickname),'[]'),
   'keywords',coalesce((SELECT jsonb_agg(k.pattern ORDER BY k.pattern) FROM brand_keywords k WHERE k.brand_id=b.nickname AND NOT k.is_regex),'[]'),
   'hashtags',coalesce((SELECT jsonb_agg(h.tag ORDER BY h.tag) FROM brand_hashtags h WHERE h.brand_id=b.nickname),'[]'),
   'accounts',coalesce((SELECT jsonb_agg(jsonb_build_object('handle',a.handle,'role',ba.role_id) ORDER BY a.handle,ba.role_id) FROM brands_accounts ba JOIN accounts a ON a.author_id=ba.accounts_id WHERE ba.brand_id=b.nickname AND a.handle IS NOT NULL),'[]'),
   'products',coalesce((SELECT jsonb_agg(jsonb_build_object('name',p.display_name,'repo_id',p.repo_id) ORDER BY p.id) FROM products p WHERE p.brand_id=b.nickname),'[]')
 ) ORDER BY b.nickname) FROM brands b WHERE NOT b.is_sentinel)
);
COMMIT;
