# ollija operations

ollija is PushinWeight's repo-specific staging and release coach. Run it only
from the authoritative checkout on `fuchitalee`; `allenwlee` remains a keyboard
and browser client and must not contain a PushinWeight checkout or ollija state.

## The ordinary loop

Ask for the next step with:

```bash
./bin/ollija status
```

Use `./bin/ollija doctor` when status reports a safety or tooling problem. A
mutating command refuses a dirty checkout, detached HEAD, unregistered
worktree, wrong host/repository, unreachable Git authority, or a failed tool
probe. Status and doctor do not write runtime state.

## Local production-derived data

The source credential is a dedicated `ollija_dump` PostgreSQL login. It has
`CONNECT`, schema `USAGE`, and `SELECT` privileges only, has no inherited
roles, and defaults to read-only transactions. Keep its connection string in
the ignored local `.env` as `OLLIJA_PROD_READONLY_DATABASE_URL`; never put it in
the repository, a receipt, command arguments, or a chat transcript.

Refresh with:

```bash
./bin/ollija refresh-local
```

The command follows this order:

1. Verify the configured production resource, database, dedicated role, and
   read-only session.
2. Create a mode-`0600` custom-format dump and verify its SHA-256 before any
   target database is created.
3. Create a uniquely named local database beneath the
   `pushinweight_staging` prefix and add a positive staging/building marker.
4. Restore without owner or ACL replay, run candidate migrations and Django
   checks, and—when persistent-data code changed—exercise the currently live
   `origin/main` code against the migrated shadow.
5. Scrub sessions, Django users and allauth links/tokens/apps, harvest queue
   state, enrichment queue state, list-sync state, and applied environment
   snapshots. Preserve posts, brands, published trend narratives, and their
   aggregate row counts.
6. Validate required schema, zero scrubbed rows, exact preserved row counts,
   and recovery posture. Only then mark the new database active and demote the
   prior active local database to recovery status.
7. Delete the raw dump and write an immutable refresh receipt containing only
   identities, counts, age, migration information, and checksum metadata.

Checksum, restore, migration, scrub, compatibility, or invariant failure never
changes the active local binding. A failed shadow is identity-checked and
dropped; the raw dump is removed in all outcomes. Production is never paused
or written by this workflow.

## Local desktop and iPhone preview

Start the active snapshot with:

```bash
./bin/ollija preview
```

The preview binds Django to `127.0.0.1:8000`, then exposes that loopback server
through private Tailscale Serve HTTPS. It refuses SQLite, production database
identities, a non-active staging marker, an occupied port, the wrong MagicDNS
host, or a pre-existing Tailscale Serve configuration. It removes provider
credentials from the child environment and forces harvest/headline provider
controls off.

The staging access middleware leaves `/accounts/` and static assets reachable,
redirects anonymous product requests to login, and returns 403 for an
authenticated email outside `OLLIJA_STAGING_ALLOWED_EMAILS`. An empty staging
allowlist fails closed. Production behavior is unchanged because the boundary
is inert unless `OLLIJA_STAGING_MODE=True`.

The preview uses `OLLIJA_STAGING_GOOGLE_CLIENT_ID` and
`OLLIJA_STAGING_GOOGLE_CLIENT_SECRET` only. If they are absent, production OAuth
credentials are replaced with empty values rather than inherited.

Stop it with:

```bash
./bin/ollija preview-stop
```

Stop verifies the recorded PID command before signaling it. Tailscale Serve is
reset only when its live configuration still points to the recorded ollija
port; there is no broad `pkill`.

## Local recovery and cleanup

The prior active database remains marked `recovery` for the configured receipt
retention window. Do not manually point Django at a build/recovery database.
If an active snapshot is bad, leave it in place for diagnosis and run a fresh
guarded refresh; activation will retain the prior binding again. Removal of old
logical databases is a separate, fingerprinted maintenance action and must
never use a name glob or unresolved shell variable.

## Credential and environment rules

- Production-derived raw data stays on `fuchitalee` or the isolated hosted
  staging database; it is never copied to `allenwlee`.
- Staging uses its own Django secret, Google OAuth client, database, hostname,
  and normalized owner allowlist.
- Staging does not inherit the production secret group and has no cron, Celery
  worker, Redis, Twitter, DeepSeek, or other provider-backed service.
- A green deploy is not proof of environment identity. ollija verifies the
  live commit, database/resource identity, access boundary, and visible page.
