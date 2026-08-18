# ollija operations

ollija is PushinWeight's repo-specific task and release controller. It lets a
coding agent do bounded implementation work, then owns the verified checkpoint
and the optional production-through-staging path. Run it only on `fuchitalee`;
`allenwlee` remains a keyboard/browser client and must not contain a
PushinWeight checkout, worktree, task ledger, receipt, or Ollija artifact.

## The ordinary loop

Ask for the next step with:

```bash
./bin/ollija status
```

Use `./bin/ollija doctor` when status reports a safety or tooling problem. A
mutating command refuses a dirty checkout, detached HEAD, unregistered
worktree, wrong host/repository, unreachable Git authority, or a failed tool
probe. Status and doctor do not write runtime state.

## Bounded agent work

Ollija does not replace Codex, Claude, or Compound Engineering. It gives one
coding agent a narrow assignment and records the run independently of the chat
or terminal that initiated it. Before `go`, settle three facts: the desired
endpoint (`commit` or `production`), the coding driver (`codex` or `claude`),
and the exact test argv (argument vector) or a bounded documentation-only
reason.

The branch must already be attached as a registered Git worktree at exactly:

```text
/Users/fuchitalee/development/pushin-weight-v2/.worktrees/<branch>
```

Create it through the repository's worktree workflow. Do not create a second
worktree root, a nested repository, or a client-local copy. Start a fresh task
from that clean worktree:

```bash
./bin/ollija go \
  --task <stable-task-id> \
  --source docs/plans/<tracked-plan>.md \
  --agent codex \
  --endpoint commit \
  --verify-argv '["pytest","tests/ollija"]'
```

`--endpoint production` authorizes the same generation to continue from its
verified commit through the existing staging and release services. Machine
checks continue automatically. Candidate-bound desktop and physical-iPhone
approvals still pause the run when the product contract requires them.

The coding agent may edit and test only. It must leave an uncommitted diff and
must not stage, commit, push, deploy, create another worktree, or launch another
agent. Ollija re-runs the declared checks, stages the task worktree's complete
diff, creates the commit, and confirms the tree is clean. An agent-created
commit, changed plan, missing diff, or failing gate pauses instead of being
trusted.

### Observe, stop, and recover

The detached tmux supervisor (a terminal session that remains on the host)
survives loss of SSH, VS Code, or the initiating terminal. Inspect it from any
later session routed to `fuchitalee`:

```bash
./bin/ollija task-status <task-id> --json
./bin/ollija stop <task-id> --json
```

`stop` writes durable cancellation before it signals the recorded process
group. It does not delete the worktree or uncommitted files. One unexpected
child-agent crash gets one retry. A second crash, missing supervisor, or host
reboot does not restart automatically; a new explicit `go` is required.

A fresh task must be clean. The one exception is recovery: the same paused,
cancelled, failed, or lost task may be explicitly re-armed with its preserved
dirty diff. Here “dirty” means Git sees changes that have not been committed.
Another task cannot claim that diff.

Task generations and attempt attribution are stored in the shared SQLite
ledger at `.ollija/state/tasks.sqlite3` under the canonical checkout. This
records coding driver, origin host/terminal, execution host, process identity,
heartbeat, endpoint, restart use, and outcome without requiring agents to add
authorship lines to documents.

### Lightweight Ollija change record

Every material change to Ollija's behavior or operating rules must update
`docs/ollija/CHANGES.md`. Each entry is deliberately shorter than a plan or a
solution article and states the problem, new behavior, proof, and release
impact. Ollija checks this before it creates a task checkpoint commit and again
before it freezes a release candidate. Product changes outside Ollija do not
need an entry. Agent and machine attribution comes from the task ledger, not
handwritten document metadata.

### Failure routes

Ollija writes only bounded incident facts under `.ollija/state/incidents/`—no
prompt body, provider response, browser session, secret, private post content,
or raw task output. It recommends, but does not autonomously launch, the
diagnostic workflow:

- environment, SSH, shell, tmux, virtualenv, or multi-machine problem:
  `infra-shell` first, then `ce-compound` after the fix;
- code or test defect: `ce-debug`, then `ce-compound`;
- UI assessment defect: Bridgewright plus `ce-debug` when code is implicated,
  then `ce-compound`;
- release verification defect: recompute Ollija status, then use `ce-debug`
  and `ce-compound`.

## Local production-derived data

This section applies when the candidate changes PushinWeight product behavior,
database behavior, or any path Ollija cannot safely classify. A candidate made
only of Ollija implementation, tests, rules, or documentation skips both data
refresh commands and proceeds directly to hosted staging. The classifier is
conservative: one unknown or product-facing path restores the full sequence.

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

If Bridgewright itself is defective, the owner may record a narrow exception:

```bash
./bin/ollija override bridgewright \
  --owner <owner-id> \
  --reason '<what failed and why the exception is justified>'
```

The immutable receipt remains visibly different from clean automated evidence
and is bound to the exact candidate and staging deployment. It does not replace
desktop or physical-iPhone approval.

## Exact-SHA production release

The owner approval on the exact hosted staging deployment is the production
release gate. Ollija re-reads Git, Render, refresh, migration/recovery,
Bridgewright, desktop, and iPhone authorities, records the currently live
production service set, and asks the Git server to fast-forward `main` to the
exact approved SHA. There is no force push or merge commit, and no authenticated
production browser session is required.

```bash
./bin/ollija release
```

This promotes the approved candidate. Production browser verification and beta
tag sealing are optional afterward:

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

For remote verification, keep the authenticated browser on the operator's
machine and expose its Chrome DevTools Protocol endpoint only over the private
tailnet. Ollija connects to that browser, records a hash of the visible
headline, and leaves the browser, cookies, and storage on the operator's
machine:

```bash
./bin/ollija verify-production \
  --browser-cdp-url http://<operator-tailnet-host>:9222
```

The storage-state and CDP options are mutually exclusive. The CDP endpoint
must not be exposed publicly; use Tailscale or an SSH tunnel.

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
- If the exact candidate is already live but lacks a sealed production
  receipt, status returns `releasing` and the next action is
  `ollija verify-production`. Never invoke `release` again for that SHA.
- If the candidate is live but the headline/browser check fails, preserve the
  last-known-good receipt and fix forward. Redeploying old code is safe only
  when the refresh receipt proved old-code compatibility with the migrated
  schema.
- If the verification command was interrupted, rerun it. Render and Git are
  re-observed; an exact existing tag is idempotent, while a conflicting tag is
  a hard stop.
- Never copy staging data to production, manually rewrite receipts, force-push
  either branch, or create the beta tag before visible verification.
