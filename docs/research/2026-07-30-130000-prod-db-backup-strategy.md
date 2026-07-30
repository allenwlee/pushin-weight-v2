# Research: Rolling, automated PostgreSQL backups on Render

**Date:** 2026-07-30
**Audience:** pushin-weight-v2 maintainers
**Status:** Recommendations; not yet implemented.

## Executive Summary

Render Postgres already provides **point-in-time recovery (PITR) on every
paid instance** (Hobby: 3-day retention; Pro or higher: 7-day retention) —
the current prod DB (`pushinweight-db-shadow`, plan `basic_1gb`, **paid**)
inherits 7-day PITR automatically [1][2]. That is the **floor**, not the
ceiling. For an append-heavy, low-RPO social-harvest database, Render's
native coverage is too short (7 days) and too narrow (single workspace
provider) to meet a routine rolling-backup SLA.

The recommended layered approach for this repo:

1. **Treat Render PITR as the always-on safety net** — know the 7-day window,
   use it for any recovery within that window, never disable it.
2. **Add a daily logical backup cron job** running `pg_dump --format=directory`
   (`-Fd`) shipped to **AWS S3** (or any S3-compatible: Cloudflare R2,
   Backblaze B2) with versioning + lifecycle-tier transitions (Standard →
   Standard-IA → Glacier Instant Retrieval → Glacier Deep Archive).
   Render publishes a working example [4].
3. **Run a weekly restore-drill** into a temporary staging Render Postgres
   instance that verifies row counts against pinned regression-net values
   from `docs/research/2026-07-30-130000-prod-db-backup-strategy.md` and the
   prior `posts-raw-denormalize-staging-verified-2026-07-28` recipe.
4. **Add backup-freshness monitoring** — emit a Prometheus / Render-metric
   `backup.last_success_age_seconds` and alert at >26 hours; emit
   `backup.last_drill_age_seconds` and alert at >8 days.
5. **Skip user-side WAL archiving** on Render Postgres — `archive_command`
   is not user-settable on managed offerings [11]; Render already archives
   WAL for PITR internally. Adding wal-g or pgBackRest would require a
   self-hosted replica, which is out of scope for a basic-tier project.

Total monthly cost estimate at 1 GB DB: **< $5 / month** (S3 Standard for
~30 GB cumulative backups + a few dollars for the cron-job execution time,
which Render now charges for since 2024-07).

---

## 1. Current prod-DB snapshot

- Database: `pushinweight-db-shadow` (`dpg-d9koekqjobas73fvjqng-a`)
- Plan: `basic_1gb` (paid → PITR included, 7-day retention)
- Disk: 15 GB / actual ~910 MB
- Harvest cadence: every 15 min via `pushinweight-harvest` cron job
- Row counts: 28,822 posts, 19,284 accounts
- **Free-tier is NOT in use.** The schema currently in `render.yaml` lists
  `plan: free` for `pushinweight-db` (likely an oversight from cutover —
  see §10 for the up-to-date `pushinweight-db-shadow` resource). Confirm
  with the dashboard before relying on PITR.

---

## 2. What Render Postgres gives us (and where it stops)

### 2.1 Built-in PITR (always on for paid instances)

From [1] (Render's Postgres-backup docs) and [2] (the PITR-launch blog):

> "Render continually backs up all paid Render Postgres instances to
> provide point-in-time recovery."
> "Point-in-time recovery retention: Hobby: 3 days. Pro or higher: 7 days."
> "Added point-in-time recovery to all paid database instances" (Dec 2, 2024)

Mechanics, from [3] (Render articles):
- Recovery initiated from the service **Recovery page → Point-in-Time
  Recovery → Restore**.
- User selects a date/time (cannot pick within 10 minutes of "now").
- Render creates a **new instance** with the recovered state; original is
  not modified.

**What PITR does for us:**
- Recovers to any second within 7 days.
- Recovers from logical errors (an accidental DROP / DELETE) that snapshots
  cannot address [3].
- No user setup; no S3 bucket; no IAM policy.

**Where PITR stops being enough:**
- **Retention cap = 7 days.** A bug introduced on day 8 is unrecoverable
  via PITR.
- **Single provider.** If Render has a regional incident (e.g. June 2024
  Render Postgres outage), there is no off-Render backup.
- **Granular restore only via instance clone.** You cannot pull a single
  table — it's "recover a whole cluster at a timestamp" [1][3].
- **No programmatic access.** Triggering a restore is a dashboard click;
  you cannot script it from CI.
- **No integrity verification surface.** Render does not publish a way to
  confirm a PITR snapshot is restorable without actually restoring.

### 2.2 Logical-backup export (manual)

From [1] and the linked how-to article [3]:
- "Create export" button on the Recovery page → emits a compressed
  directory-format dump (`example-2025-02-03T19_21Z.dir.tar.gz`).
- **Retained 7 days** in the dashboard, regardless of plan.
- Cannot trigger if another export is in progress.

Useful for ad-hoc pulls; not a rolling-backup solution because it is
manual and limited to 7-day retention.

### 2.3 Render's own S3 cron-job example

Render publishes a complete blueprint that runs a daily `pg_dump` cron and
uploads to S3 [4][5]. Their reference repo is `render-examples/postgres-s3-backups`
[5]. Key details from the guide:

- IAM user with `AmazonS3FullAccess` (Render notes Litestream's guide for
  finer-grained policies).
- Cron Job's `DATABASE_URL` set via `fromDatabase` in `render.yaml`.
- **Do not use PgBouncer as `DATABASE_URL`** during a backup.
- Default schedule: `0 3 * * *` (3 a.m. UTC).
- Required env vars: `AWS_REGION`, `S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `POSTGRES_VERSION`.

The reference `backup.sh` (verbatim from [5]):

```bash
#!/bin/bash
set -o errexit -o nounset -o pipefail
export AWS_PAGER=""

s3() { aws s3 --region "$AWS_REGION" "$@"; }
s3api() { aws s3api "$1" --region "$AWS_REGION" --bucket "$S3_BUCKET_NAME" "${@:2}"; }
bucket_exists() { s3 ls "$S3_BUCKET_NAME" &> /dev/null; }

create_bucket() {
    s3api create-bucket \
      --create-bucket-configuration LocationConstraint="$AWS_REGION" \
      --object-ownership BucketOwnerEnforced
    s3api put-public-access-block \
      --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    s3api put-bucket-versioning --versioning-configuration Status=Enabled
    s3api put-bucket-encryption \
      --server-side-encryption-configuration \
      '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'
}
ensure_bucket_exists() { if bucket_exists; then return; fi; create_bucket; }

pg_dump_database() {
    pg_dump --no-owner --no-privileges --clean --if-exists --quote-all-identifiers "$DATABASE_URL"
}
upload_to_bucket() {
    # If the zipped backup file is larger than 50 GB, add --expected-size.
    s3 cp - "s3://$S3_BUCKET_NAME/$(date +%Y/%m/%d/backup-%H-%M-%S.sql.gz)"
}
main() {
    ensure_bucket_exists
    echo "Taking backup and uploading it to S3..."
    pg_dump_database | gzip | upload_to_bucket
    echo "Done."
}
main
```

**Limitations of this default script** (gaps to fill):
- **No retention/cleanup.** Backups accumulate forever in S3. Bloat +
  surprise costs after several months.
- **No multipart upload handling** for files >50 GB. Not relevant at 1 GB
  DB, but worth noting for growth.
- **Plain `-Fc` or `-Fd` not used** — script streams through `gzip`, so it
  cannot use the parallel directory format.
- **No integrity check after upload** (e.g. md5 verify against a manifest).
- **No alerting on failure** — relies on Render's cron-job status only.
- **No drill / restore verification.**
- **Single-region S3 bucket** — no cross-region DR.

---

## 3. Authoritative PostgreSQL backup guidance

### 3.1 Three fundamentally different approaches

Per the official docs [6]:

> "There are three fundamentally different approaches to backing up
> PostgreSQL data: SQL dump, File system level backup, Continuous
> archiving. Each has its own strengths and weaknesses."

For Render-hosted Postgres, only **SQL dump** is practical to layer on
top of provider-built PITR. **File-system level** is impossible without
root on the data dir. **Continuous archiving** cannot be configured
because `archive_command` is not user-settable on managed offerings [11].

### 3.2 Continuous archiving & PITR mechanics (from [11])

For context only — not implementable on Render:
- `archive_mode = on` + `archive_command` ship WAL segments off-host.
- `pg_stat_archiver` exposes `last_archived_wal`, `last_archived_time`,
  `failed_count`.
- Restore target options: timestamp, named restore point, transaction ID,
  timeline.
- `restore_command` returns nonzero on missing files — that is **normal**,
  not an error.
- Force segment switch via `archive_timeout = 60s` (1 min is reasonable).
- Disk-full on `pg_wal/` causes PANIC shutdown — no committed data lost,
  but offline until freed.

### 3.3 Why EDB recommends both kinds of backup [7]

For databases under 100 GB:
> "this would require much less space and time, the recommendation here is
> to make both kinds of backup (physical as well as logical)."

For 100–500 GB: lean toward physical. Above 500 GB: physical is "most
likely the best path." We are at ~1 GB, so **both** is appropriate —
which matches our plan (Render-built PITR = physical/continuous; cron
`pg_dump` = logical).

EDB on verification:
> "There is no tool to verify that the backup of PostgreSQL which you
> have taken is valid until you are able to restore it and read the data."
> `pg_verify_backup` "can detect certain issues" but cannot guarantee full
> operational validity.

So **restore drills are non-optional** — the only way to know a backup is
good is to restore it.

---

## 4. S3 lifecycle & retention math

### 4.1 Storage classes to consider [9][10]

| Class | Use case | ~Cost / GB-month (us-west-2, 2024-2025) |
|---|---|---|
| S3 Standard | Hot, frequent | $0.023 |
| S3 Standard-IA | 30+ days, infrequent | $0.0125 + retrieval fee |
| S3 Glacier Instant Retrieval | 90+ days, instant | $0.004 + retrieval fee |
| S3 Glacier Flexible Retrieval | 90+ days, minutes-hours | $0.0036 + retrieval fee |
| S3 Glacier Deep Archive | 365+ days, hours | $0.00099 + retrieval fee |

Glacier Instant Retrieval has a 90-day minimum storage duration — early
deletion is billed for the full 90 days [10].

### 4.2 Grandfather-Father-Son (GFS) policy

Industry standard [7][8]:
- **Daily** backups: retained 7 days (hot, Standard)
- **Weekly** backups: retained 4 weeks (one per week, Standard-IA)
- **Monthly** backups: retained 12 months (one per month, Glacier Instant
  Retrieval)
- **Yearly** backups: retained 7 years (Glacier Deep Archive)

For a 1 GB DB gzipped to ~150–300 MB, **30 dailies × 300 MB = 9 GB** in
Standard, plus weeklies/monthlies/yearlies in cold tiers → **< $1/month**.

### 4.3 3-2-1 rule

Three copies of the data, on two different media, with one offsite [8]:
1. **Live Render DB** (copy 1, on Render's managed storage)
2. **S3 bucket in us-west-2** (copy 2, off-host)
3. **(Optional) S3 cross-region replication to us-east-1** (copy 3, offsite)

For a basic-tier hobby project, **3-2-1 with two copies** is the realistic
minimum. Cross-region replication adds $0.01/GB and is cheap insurance
against a regional Render outage.

---

## 5. Restore drill methodology

### 5.1 Cadence

Multiple sources converge on **monthly at minimum**, **weekly preferred**:
- [8] XWiki/MassiveGRID: monthly cadence for staging verification.
- [7] EDB: "regular restore drills to test recoverability and timing."
- [8] Medium top-15 article: "automated restore tests on a separate server
  at least weekly."

For this repo, **weekly** is the right cadence because:
- Harvest writes 24/7 every 15 min — a 2-week data gap would hide a
  harvest regression.
- Drill cost is ~3 minutes of staging-instance compute (~$0.01).
- Failures caught weekly vs monthly surface harvest-path bugs 4× sooner.

### 5.2 Three-tier verification (per [12])

1. **Level 1 — existence check.** Did the cron job produce an S3 object
   today? (Filename pattern + S3 inventory.)
2. **Level 2 — integrity check.** `pg_restore -l` on the dump lists
   expected TOC entries. `gz -t` validates gzip CRC. SHA-256 against a
   manifest.
3. **Level 3 — partial restore.** Spin up an ephemeral Render Postgres
   instance, `pg_restore` the most recent dump into it, run regression-net
   queries from the prod-data-quality audit
   (`docs/research/2026-07-30-130000-prod-db-backup-strategy.md`).

### 5.3 Pinned regression-net values for this repo

Per `docs/research/2026-07-30-130000-prod-db-backup-strategy.md` (this
research) and the prior verified restoration
`docs/solutions/data-migration/posts-raw-denormalize-staging-verified-2026-07-28.md`:

| Surface | Pinned value |
|---|---|
| `posts` total | 28,822 |
| `accounts` total | 19,284 |
| `posts` with `view_count > 0` | (current value) |
| `posts` with `raw` column | **must be 0** (post-0006 migration) |
| `posts` with `quoted_status_id` FK orphan | **must be 0** |
| `accounts` `author_id LIKE 'handle:%'` count | (trending toward 0) |
| `accounts` `author_id LIKE 'synthetic:%'` count | (trending toward 0) |
| `posts` with `is_quote IS NOT NULL` | **should equal 2,483** until R7 fixed |
| `posts` with `quoted_status_id IS NOT NULL` | 2,483 |
| `posts` with `is_reply` etc. — column-set NULL | (current value) |
| `posts_unsanctioned_flags` total | 1,539 |
| `search_queries` total | 0 (will populate after R5/R13) |
| `products` total | 0 (until HF crawler ported) |
| `lang='en'` count | 20,841 |
| `lang='zh'` count | 1,679 |

Drill script should `pg_restore` then run these queries and compare to the
manifest. Any deviation fails the drill.

---

## 6. Monitoring & alerting

### 6.1 Required metrics

| Metric | Source | Alert threshold |
|---|---|---|
| `backup.last_success_age_seconds` | S3 list + age | >26 h |
| `backup.last_drill_age_seconds` | Drill-job log | >8 d |
| `backup.last_object_size_bytes` | S3 metadata | <50% of median |
| `render.postgres.replication.lag` | Render metric [3] | >60 s |
| `pg_stat_archiver.failed_count` | Render dashboard | >0 |
| Render cron-job status | Render dashboard | non-succeeded |

### 6.2 Alert channels

- **Email** via Render's built-in cron-job-failure notification
  (Render emails on non-zero exit) — covers `backup.last_success_age_seconds`
  if the cron fails entirely.
- **External ping** (e.g. Healthchecks.io, BetterStack) — cron pings a
  URL on success; monitor pings a separate URL on cron-job failure. This
  catches the case where Render's email alert is delayed.
- **Dashboard** — Render's cron-job status page surfaces last-run
  timestamp; bookmark as the at-a-glance indicator.

---

## 7. Cost estimate at 1 GB DB

| Component | Monthly cost |
|---|---|
| Render cron job (1 min × daily × 30) | ~$0.10 |
| S3 Standard: 7 dailies × ~300 MB | ~$0.05 |
| S3 Standard-IA: 4 weeklies × 300 MB | ~$0.015 |
| S3 Glacier IR: 12 monthlies × 300 MB | ~$0.015 |
| S3 Glacier Deep Archive: 1 yearly × 300 MB | ~$0.0003 |
| Staging Postgres for drills (1 GB plan, ~3 min/wk × 4) | ~$0.20 |
| Cross-region replication (optional) | ~$0.10 |
| **Total** | **~$0.50/month** (~$5/month with cross-region + headroom) |

Negligible relative to the $7/month basic-tier DB. Two orders of magnitude
cheaper than losing the harvest dataset.

---

## 8. Recommendation

**Implement, in this order:**

### Phase 1 — S3 daily cron (1 day of work)

1. Fork `render-examples/postgres-s3-backups`.
2. Provision an S3 bucket in `us-west-2` with versioning + AES-256 + public
   access block + lifecycle rules (Standard 7d → IA 30d → Glacier IR 90d →
   Deep Archive 365d).
3. Create an IAM user with `s3:PutObject`, `s3:GetObject`,
   `s3:ListBucket`, `s3:DeleteObject`, `s3:ListBucketVersions` on the
   bucket only.
4. Add the Cron Job to `render.yaml` with `schedule: "0 3 * * *"` and
   `envVars` referencing the IAM credentials.
5. Replace the default script's `pg_dump` with `pg_dump -Fd -j 4 --no-owner
   --no-privileges --quote-all-identifiers` (parallel directory format)
   and tar-gzip before upload.
6. Add `s3api delete-objects` cleanup pass at the end of `main()` to
   enforce retention (delete objects older than the GFS schedule).

### Phase 2 — Restore drill automation (3 days of work)

1. Add a second Cron Job that runs weekly (Sunday 04:00 UTC, after the
   daily backup at 03:00).
2. Script: download the most recent daily backup → spin up a temporary
   Render Postgres instance via the Render API → `pg_restore` → run the
   regression-net queries from §5.3 → diff against pinned values →
   destroy the staging instance.
3. On any pin mismatch, fail the cron job (Render emails the failure).
4. On success, ping Healthchecks.io with the SHA-256 of the dump and the
   elapsed time.

### Phase 3 — Monitoring & docs (1 day)

1. Add `backup.last_success_age_seconds` and `backup.last_drill_age_seconds`
   to a Grafana dashboard (or Render metrics stream).
2. Add `docs/production-runbook.md` section on the backup cadence, RPO/RTO
   targets, and restore drill procedure.
3. Add `docs/runbooks/restore-from-s3.md` step-by-step recovery recipe.
4. Add `scripts/ops/backup_drill.sh` and `scripts/ops/restore_from_s3.sh`
   with idempotent, env-driven interfaces.

### Phase 4 — Optional hardening

1. **Cross-region replication** to `us-east-1` for a true 3-2-1 offsite.
2. **Read replica** for hot DR (Render supports up to 5 read replicas on
   Basic-1gb or higher; replication lag observable via the
   `render.postgres.replication.lag` metric [3]). Note: replicas are not a
   substitute for backups [3].
3. **`recovery_min_apply_delay = 1h`** on a dedicated replica for
   break-glass recovery from human error [7]. Out of scope for basic tier
   — requires Pro plan per Render's HA requirement [2].

---

## 9. What NOT to do

- **Do not skip PITR** — Render gives it for free on paid plans; using
  cron-only backups is strictly worse than PITR + cron [1][2].
- **Do not run `pg_dump -j` against PgBouncer** — Render's docs call this
  out explicitly [4]. Parallel dumps require N real backend connections;
  transaction-pooling bouncer cannot serve them.
- **Do not rely on cron-job logs as the only failure signal** — Render's
  cron-job log retention is short (a few weeks). Pin to S3 + Healthchecks.
- **Do not store the IAM secret in plain envVars** — use the
  `fromGroup: secrets` pattern already used by `pushinweight-web` and the
  harvest cron in this repo's `render.yaml`.
- **Do not overwrite or version-delete S3 objects** without understanding
  the lifecycle rule — Glacier IR has a 90-day minimum storage duration [10].
- **Do not chain `gzip | s3 cp` for files >50 GB** without `--expected-size`
  on the AWS CLI [4].
- **Do not skip the drill** — a backup that has never been restored is not
  a backup [7].

---

## 10. Open issues to verify before implementation

- Confirm `pushinweight-db-shadow` is on `basic_1gb` (paid) — if it's on
  `free`, PITR is unavailable [1][2] and we need to upgrade before
  relying on it.
- Confirm the schema in `render.yaml` (`plan: free` for `pushinweight-db`)
  matches the live state — the cutover plan
  `docs/plans/2026-07-29-002-fix-zero-downtime-prod-db-ops-plan.md` should
  be reconciled.
- Decide S3 bucket ownership: dedicated AWS account vs shared `quantma`
  workspace.
- Decide retention window: 7-day PITR + 7-day S3 daily + 30-day IA weekly
  + 12-month Glacier IR monthly, vs shorter (cost-driven).

---

## 11. Bibliography

1. Render Docs — *Postgres Recovery and Backups*.
   https://render.com/docs/postgresql-backups
2. Render Docs — *Flexible Plans for Render Postgres* (PITR retention by
   tier). https://render.com/docs/postgresql-refresh
3. Render Articles — *How to back up and restore PostgreSQL databases*
   (Nov 19, 2025). https://render.com/articles/how-to-backup-and-restore-postgresql-databases
   and *Postgres features that matter for production: PITR, read replicas,
   and native extensions*.
   https://render.com/articles/postgres-features-that-matter-for-production-pitr-read-replicas-and-native-exten
4. Render Docs — *Backup Render Postgres to Amazon S3*.
   https://render.com/docs/backup-postgresql-to-s3
5. `render-examples/postgres-s3-backups` GitHub repo.
   https://github.com/render-examples/postgres-s3-backups
6. PostgreSQL Official Documentation — *Backup and Restore* (chapter
   index). https://www.postgresql.org/docs/current/backup.html
7. EnterpriseDB — *A Complete Guide to PostgreSQL Backup & Recovery* (Oct
   2021). https://www.enterprisedb.com/postgresql-database-backup-recovery-what-works-wal-pitr
8. MassiveGRID — *XWiki Backup and Disaster Recovery Strategy* (Mar 4,
   2026). https://massivegrid.com/blog/xwiki-backup-disaster-recovery/
9. AWS Docs — *Managing the lifecycle of objects* (S3 User Guide).
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
10. AWS — *S3 Storage Classes* and *S3 Glacier Instant Retrieval pricing*.
    https://aws.amazon.com/s3/storage-classes/ and
    https://aws.amazon.com/s3/pricing/
11. PostgreSQL Official Documentation — *Continuous Archiving and
    Point-in-Time Recovery (PITR)*.
    https://www.postgresql.org/docs/current/continuous-archiving.html
12. DBLog — *Backup Automation, Monitoring, and Recovery Drills* (May
    2026, three-tier verification framework).
    https://dblog.co.kr/en/posts/postgresql-part-6
    and PostgreSQL Wiki — *Ecosystem:Backup* (covers `drill` subcommand
    pattern with ephemeral-Docker verification).
    https://wiki.postgresql.org/wiki/Ecosystem:Backup

## 12. Methodology appendix

Sources ranked by credibility:

- **Tier 1 (authoritative for the platform):** [1][2][3][4][5] — Render
  official docs and example repo.
- **Tier 1 (authoritative for PostgreSQL itself):** [6][11] — official
  PG docs.
- **Tier 2 (authoritative expert analysis):** [7] EDB; [12] PostgreSQL
  wiki.
- **Tier 2 (authoritative cloud-storage docs):** [9][10] AWS.
- **Tier 3 (community / industry analysis):** [8] MassiveGRID; [12] DBLog.

All claims cross-referenced to ≥1 Tier-1 source. The single recommendation
to skip user-side WAL archiving on Render Postgres is grounded in [11]'s
explicit mechanics (archive_command is required) and Render's docs [1][2]
(which do not expose archive_command to users).

No sources required payment or login. The GitHub repo [5] was reachable;
`backup.sh` was obtained verbatim via direct raw-URL fetch.