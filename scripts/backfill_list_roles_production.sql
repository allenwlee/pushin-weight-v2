BEGIN TRANSACTION READ ONLY;
-- Production's Call A main-list members and every X account-brand role, as one
-- x-backfill-list-roles/v1 document for `python manage.py sync_backfill_list_roles`
-- (plan U7, docs/plans/2026-10-30-015749-fix-backfill-size-test-fixes-20261030-plan.md).
-- Read only. Run on fuchitalee and save the full output unchanged:
--   render psql dpg-d9koekqjobas73fvjqng-a -o json \
--     --command "$(cat scripts/backfill_list_roles_production.sql)" \
--     > ~/.local/share/render-operations/<date>-backfill-list-roles/production-export.json
-- Roles carry the account handle so the sync can add role-only X accounts.
-- Roles of X accounts without an author_id cannot be matched by identity and are left out.
SELECT jsonb_build_object(
    'format', 'x-backfill-list-roles/v1',
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
            'handle', a.handle,
            'brand_id', ba.brand_id,
            'role_id', ba.role_id
        ) ORDER BY a.author_id, ba.brand_id), '[]'::jsonb)
        FROM brands_accounts AS ba
        JOIN accounts AS a ON a.account_key = ba.account_key
        WHERE a.author_id IS NOT NULL AND a.data_source_id = 'x'
    )
)::text AS backfill_list_roles_export;
ROLLBACK;
