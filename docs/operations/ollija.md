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

The preview binds Django to `127.0.0.1:8011`, then exposes that loopback server
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

## One-time hosted staging setup

The stable hosted environment is defined by `render-staging.yaml`, linked to
the permanent `staging` branch, and named `pushinweight-staging`. During the
one-time Render Blueprint setup select:

- repository: `allenwlee/pushin-weight-v2`
- branch: `staging`
- Blueprint path: `render-staging.yaml`
- create all resources as new

Before deploying the Blueprint, create one Google OAuth **Web application**
client used only by staging/local review. Configure these authorized origins:

```text
https://pushinweight-staging-web.onrender.com
https://fuchitalee.tail65bd38.ts.net
```

Configure these authorized redirect URIs:

```text
https://pushinweight-staging-web.onrender.com/accounts/google/login/callback/
https://fuchitalee.tail65bd38.ts.net/accounts/google/login/callback/
```

At the Blueprint secret prompts, set `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` from that new client and set
`OLLIJA_STAGING_ALLOWED_EMAILS` to the owner's normalized Google email. Render
generates `DJANGO_SECRET_KEY`. Do not attach `pushinweight-secrets`.

### Hosted staging go/no-go

Go only when all of the following are true:

- `render blueprints validate render-staging.yaml` and `render.yaml` both pass.
- Live inventory contains exactly one staging web and one staging PostgreSQL
  resource, with no staging worker, cron, broker, or production resource ID.
- The deployed branch/SHA exactly matches the frozen candidate on `staging`.
- The staging database marker says `staging/active`; its posts, brands, and
  published trend-narrative counts match the refresh receipt; auth/session,
  queue, and environment-state counts are zero.
- Anonymous product routes redirect to staging login, the allowlisted owner can
  enter, and an authenticated non-owner receives 403.
- Provider controls are all false and the live service has no Twitter,
  DeepSeek, Anthropic, Celery, Redis, or production environment-group keys.

If build or boot fails, leave production untouched, keep the prior staging
database binding, and correct the `staging` candidate. If a hosted restore
fails before first activation, the marker remains `building`; do not bind or
serve that database. Replace/retry the isolated staging target from the last
validated scrubbed snapshot. Never copy staging data back to production.

## Credential and environment rules

- Production-derived raw data stays on `fuchitalee` or the isolated hosted
  staging database; it is never copied to `allenwlee`.
- Staging uses its own Django secret, Google OAuth client, database, hostname,
  and normalized owner allowlist.
- Staging does not inherit the production secret group and has no cron, Celery
  worker, Redis, Twitter, DeepSeek, or other provider-backed service.
- A green deploy is not proof of environment identity. ollija verifies the
  live commit, database/resource identity, access boundary, and visible page.

## Candidate, staging, and approval loop

Finish and commit the intended change, including its beta version, before
freezing it. For the first beta the package/version pair is `0.2.0b1` and
`v0.2.0-beta.1`.

```bash
./bin/ollija start
./bin/ollija refresh-local
./bin/ollija preview
```

Review the private preview, then stop it. Once the hosted staging resource IDs
are recorded in `.ollija/project.yaml` and its ignored connection string is in
`OLLIJA_STAGING_DATABASE_URL`, bootstrap and deploy the same candidate:

```bash
./bin/ollija preview-stop
./bin/ollija refresh-staging
./bin/ollija stage
```

`stage` advances only `staging`, waits for the configured staging web service,
and accepts only the newest Render deployment when it is `live` at the exact
candidate SHA. A newer build, failed build, wrong SHA, replaced deploy, stale
refresh, or mismatched resource identity invalidates the stage.

For a UI-affecting candidate, collect assessment evidence and then perform the
two owner reviews. The iPhone approval means the owner inspected the physical
iPhone 13 in Chrome; a simulator or agent statement cannot substitute for it.

```bash
./bin/ollija assess-ui
./bin/ollija approve desktop
./bin/ollija approve iphone
./bin/ollija status
```

Any commit after `start`, any replacement staging deployment, or any UI-impact
change makes the old evidence stale. Commit the correction and repeat from
`start`; do not edit receipt JSON.

## Exact-SHA production release

Release is deliberately two commands. The first command re-reads Git, Render,
refresh, migration/recovery, Bridgewright, desktop, and iPhone authorities. It
records the currently live production service set, then asks the Git server to
fast-forward `main` to the exact approved SHA. There is no force push or merge
commit.

```bash
./bin/ollija release
```

Before production verification, create an ignored Playwright storage-state
file by opening production in a headed browser and completing Google login:

```bash
.venv/bin/playwright codegen \
  --save-storage=.ollija/state/production-browser.json \
  https://pushinweight-web.onrender.com/feed/
```

Close that browser after the authenticated feed is visible, then either put
this path in the ignored `.env` or pass it once:

```text
OLLIJA_PRODUCTION_BROWSER_STORAGE_STATE=.ollija/state/production-browser.json
```

```bash
./bin/ollija verify-production
# or:
./bin/ollija verify-production \
  --browser-storage-state .ollija/state/production-browser.json
```

Verification waits for `pushinweight-web`, `pushinweight-headlines`, and
`pushinweight-harvest` to be `live` at one exact SHA; checks the public login
route; opens the real authenticated feed; requires a visible, non-empty
`[data-pw-headline-body]` whose text is not the unavailable state; and confirms
the checked-in headline route is DeepSeek `deepseek-v4-pro` with the
worker-scoped credential. It stores only a hash of the rendered headline, not
the text or browser session. Only after every check passes does it create and
push the annotated beta tag and seal the production receipt.

## Failed or interrupted release

- If staging fails, production and `main` are untouched. Fix and commit, then
  freeze and stage a new candidate.
- If `main` advanced but a Render build failed, do not tag and do not call the
  release complete. `ollija verify-production` can be retried after the same
  SHA is healthy; a code correction is a new candidate and needs new staging
  approvals.
- If the candidate is live but the headline/browser check fails, preserve the
  last-known-good receipt and fix forward. Redeploying old code is safe only
  when the refresh receipt proved old-code compatibility with the migrated
  schema.
- If the verification command was interrupted, rerun it. Render and Git are
  re-observed; an exact existing tag is idempotent, while a conflicting tag is
  a hard stop.
- Never copy staging data to production, manually rewrite receipts, force-push
  either branch, or create the beta tag before visible verification.
