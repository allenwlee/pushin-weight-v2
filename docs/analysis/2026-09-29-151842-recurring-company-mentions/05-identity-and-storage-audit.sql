BEGIN READ ONLY; SET LOCAL statement_timeout='35s';
SELECT json_build_object('observed_at',statement_timestamp(),'fetched_before','2026-09-29T06:19:29.636718+00:00',
 'identity_audit',(SELECT json_build_object(
 'xpert_email_posts',count(*)FILTER(WHERE text ~* '[a-z0-9._%+-]+@xpertsystems[.]ai\M'),
 'xpert_real_at_mentions',count(*)FILTER(WHERE text ~* '(^|[^a-z0-9._%+-])@xpertsystems\M'),
 'exact_account_sales_footer',count(*)FILTER(WHERE text LIKE '%推特账号 ins账号购买 谷歌账号购买 飞机账号 TG账号%'),
 'exact_footer_authors',count(DISTINCT author_id)FILTER(WHERE text LIKE '%推特账号 ins账号购买 谷歌账号购买 飞机账号 TG账号%'),
 'account_and_posting_terms_overlap',count(*)FILTER(WHERE text ~* '(推特账号|ins账号购买|谷歌账号购买|twitter account purchase|twitter account sales|buy twitter accounts)' AND text ~* '(推特发帖软件|推特营销软件|X账号管理软件|Twitter营销工具|twitter posting software|twitter marketing tool)')
 ) FROM posts WHERE fetched_at<'2026-09-29T06:19:29.636718+00:00' AND text ~* '(xpert|推特账号|ins账号购买|谷歌账号购买|twitter account)'),
 'candidate_inventory',(SELECT json_build_object('total_rows',count(*),'pending',count(*)FILTER(WHERE verification_status='pending')) FROM brand_discovery_candidates),
 'stored_entity_keys',(SELECT json_agg(x ORDER BY posts DESC) FROM (SELECT k.key,count(*) AS posts FROM posts p CROSS JOIN LATERAL jsonb_object_keys(CASE WHEN jsonb_typeof(p.entities)='object' THEN p.entities ELSE '{}'::jsonb END) k(key) WHERE p.fetched_at<'2026-09-29T06:19:29.636718+00:00' AND p.entities IS NOT NULL GROUP BY k.key)x)
); COMMIT;
