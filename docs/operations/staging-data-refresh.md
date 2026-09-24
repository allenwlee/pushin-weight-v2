# Staging data refresh

Last verified: 2026-09-24.

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

The allowlist below describes the rare-type schema through migration 0055 and
the HF catalog schema from 0045_hf_catalog_observations, joined by migration
0056_merge_hf_catalog_rare_types.
Relations introduced after the production migration boundary at 0027 remain
optional on the source so a staging refresh can accept an older production
snapshot and create those relations during the shadow migration. Refresh
preflight compares the source's complete table inventory with the tracked
policy and fails closed with `source_classified_table_missing:<table>` when a
required relation is absent; the later shadow migration does not bypass that
source check. Any optional relation present on the source must have the
declared grant.

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
-- This database predates PostgreSQL 15's secure public-schema default. The
-- managed application role is a member of the schema-owner role, so it keeps
-- CREATE after this legacy grant is removed. Verify that fact before running.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM staging_refresh_reader;
GRANT USAGE ON SCHEMA public TO staging_refresh_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM staging_refresh_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM staging_refresh_reader;

GRANT SELECT ON
  account_based_in_mappings, account_post_appearances,
  account_profile_snapshots, accounts, audience_topic_concepts,
  audience_topic_labels, audience_topic_schemes, brand_discovery_candidates,
  brand_hashtags, brand_keywords,
  brand_search_terms, brands, brands_accounts, brands_companies, companies,
  companies_accounts, countries, country_codes_region, country_labels,
  discourse_keys, discourse_labels, django_content_type, django_migrations,
  django_site, event_evidence, events, geopolitical_mode_keys,
  geopolitical_mode_labels, hf_orgs, job_discovery_runs,
  job_listing_evidence,
  job_listings, model_release_evidence, model_releases, nationalism_keys,
  nationalism_labels, national_stance_keys,
  national_stance_labels, opportunities, people,
  people_accounts, people_brand_affiliation_evidence,
  people_brand_affiliations, personnel_discovery_runs, post_type_keys,
  post_type_labels, post_synthesis_artifacts, post_synthesis_texts,
  post_translation_artifacts, post_translation_texts, posts, posts_brands,
  posts_brands_audience_topics, posts_brands_classification_judgments,
  posts_brands_classification_states, posts_brands_discourse,
  posts_brands_geopolitical_modes,
  posts_brands_mentions, posts_brands_product_labels, posts_brands_products,
  posts_brands_signals,
  posts_unsanctioned_flags, posts_untracked_brand_promotions,
  product_label_keys, product_label_labels, products,
  rare_type_category_assignments,
  region_labels, regions, role_labels, roles, search_queries, sentiment_keys,
  sentiment_labels, targeted_extraction_attempts, targeted_extraction_states,
  trend_narrative_subjects, trend_narratives, unsanctioned_flag_keys,
  untracked_brand_promotion_evidence, untracked_brand_promotion_keys,
  untracked_brand_promotion_labels
TO staging_refresh_reader;

-- pg_dump takes ACCESS SHARE locks even when table data is excluded. PostgreSQL
-- 18's MAINTAIN privilege permits that lock without permitting row reads.
GRANT MAINTAIN ON
  hf_model_catalog_runs, hf_model_catalog_namespace_runs,
  hf_model_catalog_observations,
  _applied_config_snapshot, account_emailaddress, account_emailconfirmation,
  auth_group, auth_group_permissions, auth_permission, auth_user,
  auth_user_groups, auth_user_user_permissions, brand_trend_narratives,
  brand_trend_narrative_texts, brand_discovery_candidate_token_evidence,
  brand_discovery_candidate_tokens, call_state, django_session,
  harvest_backlog_windows, job_source_states, job_source_sync_runs,
  post_enrichment_states,
  post_synthesis_daily_budgets, post_synthesis_demands,
  post_synthesis_rate_limit_buckets,
  product_verification_proposals, profile_movement_candidates,
  rare_type_decision_attempts, rare_type_decision_processing_cycles,
  rare_type_decisions, rare_type_search_daily_budgets, rare_type_search_hits,
  rare_type_search_runs,
  socialaccount_socialaccount, socialaccount_socialapp,
  socialaccount_socialapp_sites, socialaccount_socialtoken,
  trend_narrative_demands, trend_narrative_provider_calls, trend_narrative_runs,
  trend_narrative_visible_runs, trend_narrative_work_slots,
  twitter_list_memberships, twitter_list_sync_state
TO staging_refresh_reader;

GRANT SELECT ON
  hf_model_catalog_namespace_runs_id_seq, hf_model_catalog_observations_id_seq,
  account_emailaddress_id_seq, account_emailconfirmation_id_seq,
  account_profile_snapshots_id_seq,
  auth_group_id_seq, auth_group_permissions_id_seq, auth_permission_id_seq,
  auth_user_groups_id_seq, auth_user_id_seq, auth_user_user_permissions_id_seq,
  audience_topic_concepts_id_seq, brand_discovery_candidates_id_seq,
  brand_discovery_candidate_token_evidence_id_seq,
  brand_discovery_candidate_tokens_id_seq,
  brand_trend_narratives_id_seq,
  brand_trend_narrative_texts_id_seq,
  django_content_type_id_seq, django_migrations_id_seq, django_site_id_seq,
  event_evidence_id_seq, events_id_seq, harvest_backlog_windows_id_seq,
  job_discovery_runs_id_seq,
  job_listing_evidence_id_seq, job_listings_id_seq,
  job_source_sync_runs_id_seq, model_release_evidence_id_seq,
  model_releases_id_seq, opportunities_id_seq,
  post_synthesis_artifacts_id_seq, post_synthesis_daily_budgets_id_seq,
  post_synthesis_demands_id_seq, post_synthesis_rate_limit_buckets_id_seq,
  post_synthesis_texts_id_seq, post_translation_artifacts_id_seq,
  post_translation_texts_id_seq,
  posts_brands_classification_judgments_id_seq,
  people_brand_affiliation_evidence_id_seq,
  people_brand_affiliations_id_seq, personnel_discovery_runs_id_seq,
  products_id_seq, product_verification_proposals_id_seq,
  profile_movement_candidates_id_seq, rare_type_category_assignments_id_seq,
  rare_type_decision_attempts_id_seq,
  rare_type_decision_processing_cycles_id_seq, rare_type_decisions_id_seq,
  rare_type_search_daily_budgets_id_seq, rare_type_search_hits_id_seq,
  rare_type_search_runs_id_seq, search_queries_id_seq,
  socialaccount_socialaccount_id_seq, socialaccount_socialapp_id_seq,
  socialaccount_socialapp_sites_id_seq, socialaccount_socialtoken_id_seq,
  targeted_extraction_attempts_id_seq, targeted_extraction_states_id_seq,
  trend_narrative_demands_id_seq, trend_narrative_provider_calls_id_seq,
  trend_narrative_runs_id_seq,
  trend_narrative_subjects_id_seq, trend_narrative_versions_id_seq,
  twitter_list_memberships_id_seq, untracked_brand_promotion_evidence_id_seq
TO staging_refresh_reader;
```

The sequence `SELECT` grants both preserve copied sequence state and permit
`pg_dump`'s sequence locks; sequences do not need `MAINTAIN`. The excluded
tables receive `MAINTAIN` only, so the refresh role can lock their schema but
cannot read their rows.

Policy version 4 marks every relation and sequence introduced after the
production migration boundary at `0027` as optional on the source. This covers
the Stage 1 classification state, people/jobs/events/opportunities, targeted
extraction, headline demand, and split translation/synthesis migrations
`0028`–`0055`, including classification judgment history, event evidence, the
U18A topic/geopolitical/promotion catalogs and assignments, and the rare-type
feature. The rare-type copy set retains `model_releases`,
`model_release_evidence`, `rare_type_category_assignments`, and
`posts_brands_products`; existing `products` and `brand_discovery_candidates`
remain copied. Exact source/candidate counts protect all six domain relations
whenever they exist on the source.

Rare-type search, gate, budget, run, hit, attempt, and processing-cycle rows
belong to one environment and are excluded and scrubbed. The same is true for
pending Product verification proposals and the profile-movement work queue.
`brand_discovery_candidate_tokens` and its evidence table are also excluded:
their evidence points to excluded search hits or profile movements, so copying
either table would retain claims without complete provenance or let cascade
cleanup erase only part of the copied domain graph. Canonical discovery
candidates themselves stay copied.

The official-job sync run and lease tables are excluded and
truncated because their active lease and diagnostic history belong to one
environment; the job listings themselves remain in the copied set. This allows
the staging-first release to refresh from the prior
production schema and then create those empty relations with Django migrations.
The source census omits validation counts only for optional relations that are
absent at that boundary. Candidate and active-database validation still count
the complete post-migration relation set.
The repeatable-read source census calculates the exact idempotent seed effects
for pending migrations `core.0033_stage1c_frontier_organization_brands` and
`core.0049_rare_type_domain_records` from the same exported snapshot used by
the dump. It simulates their ordered `get_or_create` behavior for Brands,
Companies, Company links, and nonempty English display-name counts. Existing,
partially seeded, and fully seeded sources therefore each receive exact
source-dependent expectations; the shared Anthropic seed is counted only once
when both migrations are pending. A conflicting Company owner for an 0049
canonical Brand fails before dump work, matching the migration's own refusal.
Validators still require exact equality; there is no range or broad allowance.
Once those migrations are in production, apply the new grants above before the
next refresh; preflight then requires each present optional relation to have
its declared read or maintenance privilege.

Do not add default privileges. A new production table must fail the exhaustive
preflight until `config/staging_refresh.yaml`, this grant list, and the scrub or
copy decision are reviewed together. Before changing the `PUBLIC` schema ACL,
prove that the managed application login is still a member of the schema-owner
role; afterward, prove the application login retains `CREATE` and
`staging_refresh_reader` does not.

Build the external TLS URL locally without printing it, then set only
`STAGING_REFRESH_SOURCE_DATABASE_URL` on `pushinweight-staging-web` through the
Render Dashboard's Environment page. Its shape is:

```text
postgresql://staging_refresh_reader:<password>@dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com:5432/pushinweight_shadow?sslmode=require
```

Never put the URL in a shell command, ticket, log, receipt, Blueprint, or local
environment file. `render-staging.yaml` declares exactly one `sync: false`
placeholder; `render.yaml` must remain free of it.

## Quiesce the staging work boundary

The staging database and broker are one work-state boundary. A queued envelope
from the old database must never run against the newly activated database.
Before every preflight or refresh:

1. Confirm `pushinweight-staging-harvest` still has the dormant
   `0 0 31 2 *` schedule and no manual Trigger Run is active.
2. Suspend `pushinweight-staging-headlines` in the Render Dashboard and wait
   until the service is fully stopped. Do not merely scale it while a task is
   finishing.
3. Suspend `pushinweight-staging-synthesis` and wait until it is fully stopped.
   The worker holds a PostgreSQL coordination lock for its full lifetime, so
   preflight will refuse an idle worker as well as one processing a demand.
4. From the staging web shell, purge the stage-owned broker. The broker has no
   production consumers or data, so clearing these exact queue-coordination
   keys cannot affect production:

```bash
celery -A project purge --force
python - <<'PY'
import os
import redis

from monitor.trend_narrative_queue import HEADLINE_WATERMARK_KEY

client = redis.Redis.from_url(os.environ["CELERY_BROKER_URL"])
keys = [HEADLINE_WATERMARK_KEY, "unacked", "unacked_index"]
keys.extend(client.scan_iter(match="trend-narratives*"))
deleted = client.delete(*keys) if keys else 0
print({"staging_broker_keys_deleted": deleted})
PY
```

The refresh command independently acquires the synthesis-worker coordination
lock, pings the staging broker, checks that no Celery worker responds, and
requires the `trend-narratives` queue, `unacked`
hash, `unacked_index` sorted set, every additional `trend-narratives*` key, and
latest-envelope watermark to be empty. Missing broker access or an unavailable
worker-state probe is a hard refusal. It checks twice: before dump work and
again immediately before activation. Never bypass this gate.

The command also acquires the same staging harvest-coordination advisory lock
used by `--staging-acceptance`, on the cluster administration database. It
holds that lock across the entire preflight or refresh, including activation,
so a manual harvester cannot start in the gap between the two broker checks.
The administration-database session survives termination and renaming of the
active staging database. `harvest_lock_unavailable` is a hard refusal; never
retry it until the active staging harvest or refresh has ended.

Expected refusal codes are `synthesis_lock_unavailable`,
`staging_headline_worker_active:<node>`,
`staging_headline_queue_not_empty`, and
`staging_headline_envelope_present`. Broker or worker inspection failure is
also a refusal, never permission to proceed.

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

Activation revalidates the candidate under its isolated shadow name, disables
it again, and only then swaps names. It writes the paired active/recovery
receipt comments while the new canonical database still refuses connections;
enabling the canonical database is the final cutover action. This ordering
prevents web health checks or user traffic from racing validation or observing
an unreceipted database.

The dump explicitly includes only the `public` application schema. Operational
recovery schemas such as `account_user_about_backup` and
`account_geography_backup` remain production-only and never enter staging.
Restore uses `--clean --if-exists` against the newly created, non-serving
candidate so the archive replaces PostgreSQL's default empty `public` schema.

Immediately recover the same receipt from database metadata and rerun the
active census:

```bash
./bin/refresh-staging-data verify
```

The refresh is not accepted until `verify` returns the same receipt. Then run
this independent, read-only SQL census against the canonical staging database;
do not substitute estimates from `pg_stat_user_tables`:

```bash
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'accounts' AS relation, count(*) AS rows FROM accounts
UNION ALL SELECT 'brand_discovery_candidates', count(*) FROM brand_discovery_candidates
UNION ALL SELECT 'brands', count(*) FROM brands
UNION ALL SELECT 'brands_companies', count(*) FROM brands_companies
UNION ALL SELECT 'companies', count(*) FROM companies
UNION ALL SELECT 'model_release_evidence', count(*) FROM model_release_evidence
UNION ALL SELECT 'model_releases', count(*) FROM model_releases
UNION ALL SELECT 'posts', count(*) FROM posts
UNION ALL SELECT 'posts_brands', count(*) FROM posts_brands
UNION ALL SELECT 'posts_brands_products', count(*) FROM posts_brands_products
UNION ALL SELECT 'posts_brands_classification_judgments', count(*) FROM posts_brands_classification_judgments
UNION ALL SELECT 'posts_brands_audience_topics', count(*) FROM posts_brands_audience_topics
UNION ALL SELECT 'posts_brands_geopolitical_modes', count(*) FROM posts_brands_geopolitical_modes
UNION ALL SELECT 'posts_untracked_brand_promotions', count(*) FROM posts_untracked_brand_promotions
UNION ALL SELECT 'untracked_brand_promotion_evidence', count(*) FROM untracked_brand_promotion_evidence
UNION ALL SELECT 'event_evidence', count(*) FROM event_evidence
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'rare_type_category_assignments', count(*) FROM rare_type_category_assignments
ORDER BY relation;

SELECT max(created_at) AS latest_post_created_at FROM posts;

SELECT 'account_emailaddress' AS relation, count(*) AS rows FROM account_emailaddress
UNION ALL SELECT 'account_emailconfirmation', count(*) FROM account_emailconfirmation
UNION ALL SELECT 'auth_group', count(*) FROM auth_group
UNION ALL SELECT 'auth_group_permissions', count(*) FROM auth_group_permissions
UNION ALL SELECT 'auth_permission', count(*) FROM auth_permission
UNION ALL SELECT 'auth_user', count(*) FROM auth_user
UNION ALL SELECT 'auth_user_groups', count(*) FROM auth_user_groups
UNION ALL SELECT 'auth_user_user_permissions', count(*) FROM auth_user_user_permissions
UNION ALL SELECT 'brand_trend_narratives', count(*) FROM brand_trend_narratives
UNION ALL SELECT 'brand_trend_narrative_texts', count(*) FROM brand_trend_narrative_texts
UNION ALL SELECT 'brand_discovery_candidate_token_evidence', count(*) FROM brand_discovery_candidate_token_evidence
UNION ALL SELECT 'brand_discovery_candidate_tokens', count(*) FROM brand_discovery_candidate_tokens
UNION ALL SELECT 'hf_model_catalog_runs', count(*) FROM hf_model_catalog_runs
UNION ALL SELECT 'hf_model_catalog_namespace_runs', count(*) FROM hf_model_catalog_namespace_runs
UNION ALL SELECT 'hf_model_catalog_observations', count(*) FROM hf_model_catalog_observations
UNION ALL SELECT 'call_state', count(*) FROM call_state
UNION ALL SELECT 'django_session', count(*) FROM django_session
UNION ALL SELECT 'harvest_backlog_windows', count(*) FROM harvest_backlog_windows
UNION ALL SELECT 'post_enrichment_states', count(*) FROM post_enrichment_states
UNION ALL SELECT 'post_synthesis_daily_budgets', count(*) FROM post_synthesis_daily_budgets
UNION ALL SELECT 'post_synthesis_demands', count(*) FROM post_synthesis_demands
UNION ALL SELECT 'post_synthesis_rate_limit_buckets', count(*) FROM post_synthesis_rate_limit_buckets
UNION ALL SELECT 'product_verification_proposals', count(*) FROM product_verification_proposals
UNION ALL SELECT 'profile_movement_candidates', count(*) FROM profile_movement_candidates
UNION ALL SELECT 'rare_type_decision_attempts', count(*) FROM rare_type_decision_attempts
UNION ALL SELECT 'rare_type_decision_processing_cycles', count(*) FROM rare_type_decision_processing_cycles
UNION ALL SELECT 'rare_type_decisions', count(*) FROM rare_type_decisions
UNION ALL SELECT 'rare_type_search_daily_budgets', count(*) FROM rare_type_search_daily_budgets
UNION ALL SELECT 'rare_type_search_hits', count(*) FROM rare_type_search_hits
UNION ALL SELECT 'rare_type_search_runs', count(*) FROM rare_type_search_runs
UNION ALL SELECT 'socialaccount_socialaccount', count(*) FROM socialaccount_socialaccount
UNION ALL SELECT 'socialaccount_socialapp', count(*) FROM socialaccount_socialapp
UNION ALL SELECT 'socialaccount_socialapp_sites', count(*) FROM socialaccount_socialapp_sites
UNION ALL SELECT 'socialaccount_socialtoken', count(*) FROM socialaccount_socialtoken
UNION ALL SELECT 'trend_narrative_demands', count(*) FROM trend_narrative_demands
UNION ALL SELECT 'trend_narrative_provider_calls', count(*) FROM trend_narrative_provider_calls
UNION ALL SELECT 'trend_narrative_runs', count(*) FROM trend_narrative_runs
UNION ALL SELECT 'trend_narrative_visible_runs', count(*) FROM trend_narrative_visible_runs
UNION ALL SELECT 'trend_narrative_work_slots', count(*) FROM trend_narrative_work_slots
UNION ALL SELECT 'twitter_list_memberships', count(*) FROM twitter_list_memberships
UNION ALL SELECT 'twitter_list_sync_state', count(*) FROM twitter_list_sync_state
UNION ALL SELECT '_applied_config_snapshot', count(*) FROM _applied_config_snapshot
ORDER BY relation;

SELECT window_days, count(*) AS current_rows
FROM trend_narratives
WHERE is_current
GROUP BY window_days
HAVING count(*) > 1;

SELECT conname
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname = 'public' AND c.contype = 'f' AND NOT c.convalidated;

SELECT domain, name FROM django_site WHERE id = 1;
SQL

python - <<'PY'
import os

import psycopg

from scripts.database_lock import admin_connection_parameters

parameters = admin_connection_parameters(os.environ["DATABASE_URL"])
with psycopg.connect(**parameters) as connection, connection.cursor() as cursor:
    cursor.execute(
        "SELECT datname, datallowconn FROM pg_database "
        "WHERE datname LIKE 'pushinweight_staging_recovery_%' ORDER BY datname"
    )
    for row in cursor:
        print(*row)
PY

find /tmp "$PWD/.staging-refresh" -maxdepth 1 -type f \
  -name 'staging-refresh-*.dump' -print 2>/dev/null
```

Record the exact counts and latest timestamp next to the receipt. The census
must include the copied classification-judgment and event-evidence tables
introduced through migration 0043, the rare-type domain relations through
0055, and the HF catalog relations in 0045_hf_catalog_observations. Every
scrub count listed above must be zero; both
invariant queries must return no rows; the site must be
`pushinweight-staging-web.onrender.com` / `Pushin Weight Staging`; the
receipt-named recovery must have `datallowconn = f`; and the dump search must
be empty. Compare product counts and the latest timestamp to the receipt, not
to an earlier observation of production.

Only after `verify` and the independent zero-state census both pass may the
staging headline worker be resumed. Resume the synthesis worker only after its
provider-call flag and lane budget have passed the staged activation gate.
The staging harvester remains dormant; each later acceptance run is a separate
intentional Render Trigger Run.

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

HF catalog refresh policy: Products (including rich metadata) are copied. The
three `hf_model_catalog_*` ledger tables are excluded, optional on older sources,
and scrubbed on staging. Copied metadata references retain their original run
UUID and do not imply the original observations exist in staging.
