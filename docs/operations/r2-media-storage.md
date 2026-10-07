# Shared media storage on Cloudflare R2

PushinWeight keeps staff source images and generated editorial media in private
R2 storage so Render's web service and background workers can read the same
files. PostgreSQL retains object names, hashes, attribution and review state;
file bytes live in R2. The application checks permission before issuing a
download link valid for at most five minutes.

The storage code is opt-in. With no backend configuration, existing filesystem
storage continues to work. Installing this code does not create buckets, copy
files or enable staff collection or editorial generation.

## Configuration and ownership

G1 owns the adapter, shared settings, credentials and migration. G2 consumes the
two existing Django storage aliases and owns its editorial view/picture policy.
Use `core.media_storage.PrivateR2Storage` for both remote aliases. It extends
the [standard Django S3 adapter](https://django-storages.readthedocs.io/en/latest/backends/s3_compatible/cloudflare-r2.html)
with explicit R2 credentials, HTTPS, signed links and private/no-store responses.
It rejects missing credentials and does not fall back to another app's AWS key.

Configure these secret values through Render's service environment, not Git:

- `R2_ACCOUNT_ID`: Cloudflare account ID.
- `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`: the R2 S3 credentials for this
  environment. Give runtime credentials object read/write access only to that
  environment's bucket. Provisioning credentials are a separate operator concern.

Use a different private bucket for staging and production. Within each bucket,
`staff/` stores originals and `editorial/` stores derivatives. Both private buckets
below were created on October 6, 2026. Deployment observations and G2 handoff
details are recorded in the existing G1 plan and [PR #52](https://github.com/allenwlee/pushin-weight-v2/pull/52).

| Environment | Bucket | Staff options | Editorial options |
| --- | --- | --- | --- |
| Staging | `pushinweight-media-staging` | `{"bucket_name":"pushinweight-media-staging","location":"staff"}` | `{"bucket_name":"pushinweight-media-staging","location":"editorial"}` |
| Production | `pushinweight-media-production` | `{"bucket_name":"pushinweight-media-production","location":"staff"}` | `{"bucket_name":"pushinweight-media-production","location":"editorial"}` |

The operator's `/Users/fuchitalee/.env.secrets` keeps the deployment pairs under
distinct names so configuring staging does not accidentally use production's
credential. Create each token with **Object Read & Write**, restricted to the
one corresponding bucket:

| Operator secret-store variable | Render variable | Services |
| --- | --- | --- |
| `R2_STAGING_ACCESS_KEY_ID` | `R2_ACCESS_KEY_ID` | Staging web and headline worker |
| `R2_STAGING_SECRET_ACCESS_KEY` | `R2_SECRET_ACCESS_KEY` | Staging web and headline worker |
| `R2_PRODUCTION_ACCESS_KEY_ID` | `R2_ACCESS_KEY_ID` | Production web and headline worker |
| `R2_PRODUCTION_SECRET_ACCESS_KEY` | `R2_SECRET_ACCESS_KEY` | Production web and headline worker |

`R2_ACCOUNT_ID` is shared. The original administrative setup pair stays in the
operator secret store. Both deployment pairs passed own-bucket GETs and
cross-bucket denial checks on October 6 and are installed on the corresponding
Render web and headline worker services. Repeat those checks when rotating or
replacing credentials.

Set `STAFF_MEDIA_STORAGE_BACKEND` and `EDITORIAL_MEDIA_STORAGE_BACKEND` to
`core.media_storage.PrivateR2Storage`; put the corresponding JSON above in
`STAFF_MEDIA_STORAGE_OPTIONS` and `EDITORIAL_MEDIA_STORAGE_OPTIONS`. Explicit
options replace the filesystem defaults. `*_MEDIA_ROOT` is a local path and is
not a bucket prefix. The adapter computes the R2 endpoint from `R2_ACCOUNT_ID`.

The aliases use the same environment-specific credentials on web and the
headline/editorial worker. A future staff collection worker needs staff access
when that worker is separately activated. Do not give unrelated services a key.
The Render Blueprint does not provision these operator-managed values or assert
readiness. Configure the exact services through Render without applying an
unrelated Blueprint or changing other agents' runtime controls.

Only set `STAFF_MEDIA_DURABLE=true` and `EDITORIAL_MEDIA_DURABLE=true` after
verification establishes shared access. Those flags describe storage readiness;
they do not authorize or enable paid collection or media generation.

## Copy existing staff files before changing serving configuration

Run source-copy commands in the existing web service, where the persistent disk
is mounted. Render one-off jobs cannot see that disk. Set the new R2 credentials
on the intended services first, while keeping their active filesystem backend.
Use process-local backend overrides for the copy command so website requests
continue reading the original disk throughout the copy.

For staging, with credentials already available to the command process:

```sh
STAFF_MEDIA_STORAGE_BACKEND=core.media_storage.PrivateR2Storage \
STAFF_MEDIA_STORAGE_OPTIONS='{"bucket_name":"pushinweight-media-staging","location":"staff"}' \
python manage.py migrate_staff_media --source-root /var/data/staff-media
```

This previews the transfer: it verifies existing destination objects and source
bytes for missing destinations, and reports planned copies without writing.
Run the same command with `--apply` to copy missing objects. A failed run emits
JSON errors and exits unsuccessfully. Rerunning verifies completed copies and
continues the missing ones. It never updates database rows or deletes source
files; a differing destination object is an error, not an overwrite instruction.
R2 copies use a conditional write (`If-None-Match: *`), so an object created by
another process after the initial check is also preserved and verified. Only
the R2 adapter and a filesystem backend with overwriting disabled support copy
mode; other configured backends fail explicitly when a copy is needed.

The destination preserves each database-relative `storage_name` under the chosen
prefix. Files not referenced by `staff_media_objects`, such as exported HTML
dossiers, are outside this command's inventory and remain on the existing disk.
The report includes the ordered inventory hash, object count, copied/verified
counts and verified byte count. Preserve it with the deployment record.

Repeat the inventory/copy immediately before cutover to include any new objects.
If collection can write during the transition, coordinate a bounded pause of
only that writer. An in-flight migration error blocks cutover. Then configure
the web and worker storage backends/options and deploy the reviewed revision.
Production uses the same procedure with the production bucket and credentials.

## Verify the actual deployed services

The staff destination can be verified without local source files:

```sh
python manage.py migrate_staff_media --verify-only
```

Require no errors, a verified count equal to the inventory, matching expected
bytes/hashes, and an inventory hash matching the final copy receipt. An empty
inventory is not proof that the existing staff library was migrated.

Prove shared access independently of database records. In the web service:

```sh
python manage.py check_media_storage --storage staff_media --write
```

The JSON receipt contains a probe ID, SHA-256, writer service/revision and backend.
In the actual worker service, use the returned values:

```sh
python manage.py check_media_storage --storage staff_media \
  --probe-id RETURNED_UUID --expected-sha256 RETURNED_SHA256
```

Repeat worker-to-web and for `editorial_media`. Require the expected
`core.media_storage.PrivateR2Storage` backend and distinct writer/reader service
identities, with the intended revision recorded. The small proof objects remain
under `_storage-probes/` within each namespace; this command does not delete them.
Local filesystem tests validate command behavior but do not establish R2 access.

Repeat destination verification and cross-service reads after a redeployment.
Test G2's authorized source-image and saved-video delivery, denied access,
disabled pictures, expired URLs and video range/playback using saved media. No
paid provider call is necessary for storage verification. G2 readiness requires
its deployed integration too; a successful backend probe alone is insufficient.

## Download links and disablement

The G2 asset route retains its authorization, current verification, edition and
picture-policy checks before redirecting to `storage.url(name, expire=300)`.
Keep the redirect response private/no-store. Do not store this temporary URL in
`generated_storage_name` or any permanent object-reference field.

The adapter requests private/no-store object responses and caps URLs at five
minutes. Disabling pictures prevents new links from being issued. An existing
link can remain usable until its expiry; this is not immediate revocation of a
previously issued link. Media already downloaded cannot be recalled. The G2
tests and operating description must preserve this distinction.

## October 6 verification and G2 continuation

The deployed adapter passed actual web-to-worker and worker-to-web checks for
both aliases in both environments. Each bucket contains all 35 existing staff
objects, totaling 20,060,954 bytes, with unchanged database-relative keys and
matching hashes. The ordered inventory hash is
`5d87e585ab518346379658826772adbc84a36d75ba7c9fc351276553679f6c8e`.

G2's integration revision is
`f92765206fdbbbe9aa2006ef29154fdf0e1d079f` on
`test/g1-r2-g2-20261006`. It combines published G2 `bacbb433` with the G1 adapter.
Its deployed asset view passed source-image and saved-video redirects/downloads,
ranges, anonymous denial, disabled pictures and revoked-verification checks.
The temporary database fixtures were rolled back; synthetic Chrome video
playback passed separately. Production has the G1 code only. No paid provider
calls were needed for any storage check.

The rollout restores that G2 integration to staging after separately proving
the G1 production candidate. The tracked `staging` branch remains at G2's
published revision, and automatic deployment is off for both staging services.
Before G2 resumes deployment, inspect live service revisions, reconcile its
branch with main, and preserve the existing `staff_media` / `editorial_media`
aliases and credential settings. Keep the local G2 route-limit correction;
this storage change does not include it. Re-enable automatic deployment only
when the tracked branch contains the intended combined code.

The latest deployment identities, effective durability flags and restart
read-back results are recorded in [PR #52](https://github.com/allenwlee/pushin-weight-v2/pull/52)
and the authoritative launch index. Local evidence is archived on fuchitalee at
`/Users/fuchitalee/development/pushin-weight-v2/.context/g1-r2-release-20261006/`.
Storage readiness resolves G1's shared-file dependency. G2's role review,
generation policy, spending limits and public activation remain its own gates.

## Rollback and retained files

Record each service's original backend/options/root and durability flags before
cutover. Keep all original disk files. On missing/corrupt objects, access-policy
regressions or repeated R2 failures, stop media activation and restore the
recorded filesystem settings on the web service. Mark shared storage unavailable
until it is verified again; a worker cannot use the web service's private disk.

If new assets were written to R2 after cutover, inventory and copy those files
back with hash verification before claiming a complete filesystem rollback.
Original disk copies cover the pre-cutover inventory only. Do not delete buckets,
new R2 objects or Render disks during rollback. Retention cleanup needs its own
review after a successful observation period.

Official references checked October 5, 2026: [R2 credentials](https://developers.cloudflare.com/r2/api/tokens/),
[R2 Python access and signed URLs](https://developers.cloudflare.com/r2/examples/aws/boto3/),
[R2 conditional writes](https://developers.cloudflare.com/r2/api/s3/api/),
[Render disk access limitations](https://render.com/docs/disks#disk-limitations-and-considerations).
