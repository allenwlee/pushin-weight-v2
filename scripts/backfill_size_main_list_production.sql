-- Production's current Call A main-list members and every account-brand role (plan U1/U9).
-- Read only: run with `render psql dpg-d9koekqjobas73fvjqng-a -o json --command "<this file>"`.
-- The size test seeds these into xbackfiller so the 8 production searches attribute Call A
-- authors as production does today; switch-off removes them again with the seed's undo receipt.
BEGIN TRANSACTION READ ONLY;
SELECT jsonb_build_object(
    'format', 'oai-anthropic-main-list/v1',
    'database', current_database(),
    'generated_at', now(),
    'list_id', 2067062923525275922,
    'members', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'author_id', a.author_id,
            'handle', a.handle
        ) ORDER BY a.author_id), '[]'::jsonb)
        FROM twitter_list_memberships AS m
        JOIN accounts AS a ON a.account_key = m.account_key
        WHERE m.list_id = 2067062923525275922 AND m.active AND a.author_id IS NOT NULL
    ),
    'roles', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'author_id', a.author_id,
            'brand_id', ba.brand_id,
            'role_id', ba.role_id
        ) ORDER BY a.author_id, ba.brand_id), '[]'::jsonb)
        FROM brands_accounts AS ba
        JOIN accounts AS a ON a.account_key = ba.account_key
        WHERE a.author_id IS NOT NULL AND a.data_source_id = 'x'
    )
)::text AS main_list_export;
ROLLBACK;
