# Staging data refresh

Last verified: 2026-08-27.

This procedure replaces only the isolated `pushinweight_staging` database with
a current production snapshot. It never changes the production database. The
mechanism restores into a shadow database, migrates it, removes private and
operational data, validates it, and only then swaps database names under a
shared cluster lock. The prior staging database remains disabled as the
receipt-named recovery point.

The command is intentionally usable only on `pushinweight-staging-web`
(`srv-d9vb8t49v7es738lf2ng`). Production has neither the enable flag nor the
source secret. Do not copy either setting to another service.

## One-time source reader

Application credentials remain Render-managed. The refresh reader is a
separate least-privileged PostgreSQL login because it must see only the
allowlisted product relations. Open an interactive owner session so the
password never appears in a command argument, shell history, transcript, or
tracked file:

```bash
render psql dpg-d9koekqjobas73fvjqng-a
```

Run the following in `psql`. `\password` prompts twice without echoing the
secret.

```sql
SELECT 'CREATE ROLE staging_refresh_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'staging_refresh_reader')
\gexec

ALTER ROLE staging_refresh_reader
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE staging_refresh_reader SET default_transaction_read_only = on;
\password staging_refresh_reader

REVOKE ALL ON DATABASE pushinweight_shadow FROM staging_refresh_reader;
REVOKE CREATE, TEMPORARY ON DATABASE pushinweight_shadow FROM staging_refresh_reader;
GRANT CONNECT ON DATABASE pushinweight_shadow TO staging_refresh_reader;
GRANT CONNECT ON DATABASE postgres TO staging_refresh_reader;
REVOKE CREATE ON SCHEMA public FROM staging_refresh_reader;
GRANT USAGE ON SCHEMA public TO staging_refresh_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM staging_refresh_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM staging_refresh_reader;

GRANT SELECT ON
  account_post_appearances, accounts, brand_hashtags, brand_keywords,
  brand_search_terms, brands, brands_accounts, brands_companies, companies,
  companies_accounts, discourse_keys, discourse_labels, django_content_type,
  django_migrations, django_site, hf_orgs, nationalism_keys,
  nationalism_labels, post_type_keys, post_type_labels, posts, posts_brands,
  posts_brands_discourse, posts_brands_mentions, posts_brands_signals,
  posts_unsanctioned_flags, products, role_labels, roles, search_queries,
  sentiment_keys, sentiment_labels, trend_narrative_subjects,
  trend_narratives, unsanctioned_flag_keys
TO staging_refresh_reader;

GRANT SELECT ON
  account_emailaddress_id_seq, account_emailconfirmation_id_seq,
  auth_group_id_seq, auth_group_permissions_id_seq, auth_permission_id_seq,
  auth_user_groups_id_seq, auth_user_id_seq, auth_user_user_permissions_id_seq,
  django_content_type_id_seq, django_migrations_id_seq, django_site_id_seq,
  harvest_backlog_windows_id_seq, products_id_seq, search_queries_id_seq,
  socialaccount_socialaccount_id_seq, socialaccount_socialapp_id_seq,
  socialaccount_socialapp_sites_id_seq, socialaccount_socialtoken_id_seq,
  trend_narrative_subjects_id_seq, trend_narrative_versions_id_seq,
  twitter_list_memberships_id_seq
TO staging_refresh_reader;
```

Do not add default privileges. A new production table must fail the exhaustive
preflight until `config/staging_refresh.yaml`, this grant list, and the scrub or
copy decision are reviewed together.

Build the external TLS URL locally without printing it, then set only
`STAGING_REFRESH_SOURCE_DATABASE_URL` on `pushinweight-staging-web` through the
Render Dashboard's Environment page. Its shape is:

```text
postgresql://staging_refresh_reader:<password>@dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com:5432/pushinweight_shadow?sslmode=require
```

Never put the URL in a shell command, ticket, log, receipt, Blueprint, or local
environment file. `render-staging.yaml` declares exactly one `sync: false`
placeholder; `render.yaml` must remain free of it.

## Preflight and refresh

SSH to the staging web service and first prove the service, connection, role,
TLS, PostgreSQL 18, relation policy, free-space, and lock guards:

```bash
render ssh srv-d9vb8t49v7es738lf2ng
./bin/refresh-staging-data preflight
```

A successful preflight emits one secret-free JSON line with
`"status":"authorized"`. Any rejection is a stop condition. In particular,
do not work around an unclassified relation, source privilege, target identity,
tool-version, space, or shared-lock failure.

Run the refresh with the exact policy-derived confirmation:

```bash
./bin/refresh-staging-data refresh \
  --confirm 'REFRESH production/pushinweight_shadow -> staging/pushinweight_staging'
```

Success emits and stores one receipt containing the dump checksum, snapshot
time, source and candidate counts, scrub results, canonical name, recovery
name, and exact rollback confirmation. Copy the JSON receipt to the operation
record, but never create a tracked receipt file. The dump is removed in the
command's guaranteed cleanup path.

Immediately recover the same receipt from database metadata and rerun the
active census:

```bash
./bin/refresh-staging-data verify
```

The refresh is not accepted until `verify` returns the same receipt and an
independent read-only census confirms representative counts and timestamps,
all configured scrub tables at zero, one current narrative per window, and the
staging site identity.

## Rollback

Use only the recovery database named by the active receipt. The command
refuses a guessed, enabled, unmarked, ambiguous, or receipt-mismatched name.

```bash
./bin/refresh-staging-data rollback \
  --recovery pushinweight_staging_recovery_YYYYMMDDtHHMMSSz \
  --confirm 'ROLLBACK staging/pushinweight_staging_recovery_YYYYMMDDtHHMMSSz -> staging/pushinweight_staging'
./bin/refresh-staging-data verify
```

Rollback preserves the displaced database as a newly named, disabled recovery
and writes a new paired receipt. Never drop either side while diagnosing a
partial cutover.

## Pruning

Policy retains the newest marked recovery. Prune only an older exact name from
its own receipt:

```bash
./bin/refresh-staging-data prune \
  --recovery pushinweight_staging_recovery_YYYYMMDDtHHMMSSz \
  --confirm 'PRUNE staging/pushinweight_staging_recovery_YYYYMMDDtHHMMSSz'
```

The command refuses the canonical database, active candidates, retained
recoveries, legacy unmarked databases, and prefix-only impostors. Review legacy
unmarked databases manually; this mechanism intentionally never drops them.

## Interrupted operations

- Before either rename, the canonical staging database is re-enabled and the
  shadow is retained or safely removed by its exact marker.
- After either rename, the state machine attempts to restore the original
  canonical and returns `*_failed_repaired` with one enabled canonical.
- `*_manual_recovery_required` lists the exact canonical, incoming, and
  displaced database states. Stop all lifecycle commands, preserve every
  database, and inspect those names through the production database's
  `postgres` administration database before taking manual action.
- `cluster_lock_unavailable` means a deploy migration or another lifecycle
  command owns the cluster. Retry after that owner finishes; do not bypass the
  lock.
- A stale mechanism-owned dump older than 24 hours is removed by the next
  command initialization. Unrelated files and unmarked databases are ignored.

## Reader rotation and revocation

Rotate with `\password staging_refresh_reader` in an interactive production
owner session. Update the one staging secret through Render without displaying
it, redeploy staging, and require `preflight` to pass. Existing refresh
connections may finish; new connections immediately use the new password.

To revoke the mechanism, remove the one staging environment value, redeploy,
and then run:

```sql
ALTER ROLE staging_refresh_reader NOLOGIN;
```

Do not revoke or rotate the production application credential as part of this
procedure.
