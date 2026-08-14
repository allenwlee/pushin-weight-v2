yes add a readme, with plenty of technical details, but written so that a nontechnical user can understand it--shoot for a vp of corp dev,  general counsel, and a financial analyst -- all are supremely logical and able to understand complexity but not the lingo. to quickly grasp things they require a very brief explanation starting from the big picture, the pain point, the project's place in the broader tech stack, the 'why' before delving into details. proper names for tech tools, methods, etc should be very briefly explained in parens (acronyms can be used but should be defined in (parentheses) as well. <<< add this prompt verbatim to the front of the readme for further use. 

# Ollija

Ollija is PushinWeight’s release-control system. It guides one developer through
the path from a code change to a reviewed staging release and, finally, a
production release.

It is named after the Korean expression **올리자** (“let’s put it up” or “the
person who puts it up”). The name reflects its job: make the next safe change
clear, record what was actually reviewed, and prevent an accidental production
change.

The Hangul spelling is **올리자** (*ollija*). It comes from **올리다** (*ollida*,
“to raise,” “upload,” “put online,” or “deploy”) plus **-자** (*-ja*, the
hortative ending meaning “let’s”). Korean software teams commonly use **올리다**
for putting a server, container, build, or feature into service. The name also
contains a deliberate wordplay: **-자** can evoke “the person who does [the
action]” when heard as the agent-like **자** used in Korean compounds, so
**올리자** suggests both “let’s put it up” and “the one who puts it up.”
Strictly speaking, the **-자** in the expression is the grammatical “let’s”
ending; the second meaning is a product-name association, not a claim that the
same Korean suffix has both grammatical functions in this exact word.

## The short version

PushinWeight is a live web product. A single developer is responsible for its
code, data, infrastructure, and releases. Without a disciplined process, a
small change can be made directly against production, tested against the wrong
database, or approved based on a page that is not the page eventually deployed.

Ollija creates a controlled path:

```text
code change
    ↓
candidate commit
    ↓
private/local review data
    ↓
isolated hosted staging
    ↓
desktop + physical iPhone review
    ↓
production deployment
    ↓
automated production verification
    ↓
beta tag and sealed release record
```

The important idea is identity. Ollija ties the code version, staging
deployment, database snapshot, human approvals, production deployment, and
visible headline to one exact Git commit (Git’s immutable code-version
identifier).

## Where Ollija fits in the technology stack

Ollija does not replace PushinWeight or Render. It sits above them as a release
orchestration and evidence layer.

| Layer | Role | Plain-language meaning |
| --- | --- | --- |
| Django | Web application framework | Runs the PushinWeight website and database-backed product logic. |
| PostgreSQL | Production and staging database | Stores brands, posts, trend data, users, and published narratives. |
| Celery | Background-job system | Runs scheduled harvesting and headline-generation work outside the web request. |
| Render | Cloud hosting platform | Builds and runs the web services, workers, scheduled jobs, and managed databases. |
| Git/GitHub | Source-control system | Stores the code history and identifies each candidate exactly. |
| Google OAuth | Sign-in service | Controls who can enter staging and production. OAuth (Open Authorization) lets Google authenticate a user without PushinWeight storing that user’s Google password. |
| Bridgewright | UI assessment tool | Inspects a rendered page and records assessment evidence; it cannot approve or release. |
| Ollija | Release-control layer | Connects all of the above and enforces the release sequence. |

The authoritative checkout is on `fuchitalee`. `allenwlee` is a browser and
keyboard endpoint, not a second source-code repository. Project files,
database snapshots, receipts, and release artifacts remain on `fuchitalee`.

## The problem Ollija solves

There are four related risks:

1. **Environment confusion:** local, staging, and production can look similar
   while pointing at different databases or code versions.
2. **Data risk:** realistic trend analysis needs realistic data, but production
   data must not be casually copied into a development environment or modified
   by a test.
3. **Review risk:** a human may approve one deployment while a later deployment
   is the one actually served.
4. **Release uncertainty:** a successful build does not prove that every
   production service is running the same code or that the headline is visible
   to a real authenticated user.

Ollija addresses these with isolation, exact-identity checks, reversible data
refreshes, explicit approvals, and final production verification.

## The environments

### Production

Production is the customer-facing PushinWeight system on Render. It contains
the live PostgreSQL database and the services that serve the website, harvest
posts, and generate trend narratives.

Ollija never uses production as a test target. Its production database access
for refreshes is a dedicated read-only PostgreSQL account (a database user that
cannot write data).

### Hosted staging

Hosted staging is an isolated Render web service and an isolated Render
PostgreSQL database. It is intended for review before production. It has its
own Google OAuth client, hostname, database credentials, and owner allowlist.

For the current staging design:

- the web service runs the candidate code;
- the database contains a scrubbed production-derived snapshot;
- users and sessions are removed or replaced with staging-safe state;
- harvesting, Celery (background-job processing), and provider calls are off;
- existing published narratives can be served for review;
- staging never writes back to production.

The staging database is not a continuous replica. Ollija creates a guarded
refresh from production-derived data, validates it, and then copies that
validated snapshot to hosted staging.

### Local preview

Local preview runs Django against an active local PostgreSQL snapshot. Ollija
exposes it through private Tailscale HTTPS (Tailscale is a private network
overlay) so the desktop browser and physical iPhone can review the same local
surface when needed.

## What happens during a normal change

### 1. Start a candidate

```bash
./bin/ollija start
```

Ollija freezes the current clean commit as the candidate. A candidate is the
only version that may proceed through the release workflow. If the code changes
after this point, the previous evidence becomes stale and a new candidate is
required.

### 2. Refresh local review data

```bash
./bin/ollija refresh-local
```

The refresh process:

1. checks that the source is the configured production database and the account
   is read-only;
2. creates a PostgreSQL dump (a database backup file);
3. restores it into a uniquely named local staging database;
4. runs migrations and Django checks;
5. removes users, sessions, tokens, queues, and other operational state;
6. preserves the data needed for trend and headline review;
7. validates expected row counts and required schema;
8. activates the new snapshot only after all checks pass;
9. removes the raw dump and stores a receipt containing identities, counts, and
   checksums rather than secrets or raw data.

The previous active local database is retained as a recovery target for a
limited period. Ollija never uses a database name glob or an unresolved shell
variable for cleanup.

### 3. Review locally, if needed

```bash
./bin/ollija preview
```

This starts the active snapshot on the local preview port and publishes it only
through the private tailnet. Provider credentials are removed from the preview
process, and headline/harvest provider controls are forced off.

Stop it with:

```bash
./bin/ollija preview-stop
```

### 4. Refresh hosted staging

```bash
./bin/ollija refresh-staging
```

This copies the already validated, scrubbed local snapshot to the isolated
hosted staging database. Ollija verifies the target database identity, marker,
resource, and preserved counts before activating it.

### 5. Deploy the exact candidate to staging

```bash
./bin/ollija stage
```

Ollija asks Render to deploy the exact candidate SHA (secure hash identifier),
then waits for the deployment to be live. A deployment built from a different
commit, a replaced deployment, or a failed deployment cannot satisfy this
step.

### 6. Collect assessment and owner approvals

```bash
./bin/ollija assess-ui
./bin/ollija approve desktop
./bin/ollija approve iphone
```

Bridgewright provides assessment evidence only. The owner must separately
inspect the exact hosted deployment on desktop and the physical iPhone 13.
Screenshots, an agent’s inspection, or a simulator cannot substitute for the
physical-device approval.

### 7. Promote the approved candidate

```bash
./bin/ollija release
```

This is the first command that can change production. It rechecks the candidate,
refresh receipts, staging identity, deployment identity, Bridgewright evidence,
and both owner approvals. It then fast-forwards `main` (moves the production
branch forward without rewriting history) to the exact approved commit and
starts the production deployment.

It does not create the beta tag yet. Tagging waits for final production
verification.

### 8. Verify production and seal the release

```bash
./bin/ollija verify-production
```

Verification checks that:

- the configured production services are live;
- all services run the exact candidate SHA;
- public health and sign-in routes respond correctly;
- the authenticated feed visibly contains a non-empty headline;
- the headline is not the unavailable-state text;
- the configured model is DeepSeek `deepseek-v4-pro` (DSV4, the selected
  DeepSeek generation-4 model);
- the headline worker has the provider credential scoped to that worker;
- the annotated beta tag can be created safely.

Only after these checks pass does Ollija create and push the beta tag
`v0.2.0-beta.1` and write the final production receipt.

## Remote authenticated browser verification

The production feed requires Google authentication. A plain HTTP request can
prove that a route exists, but it cannot prove that an authenticated user sees
a headline.

The preferred remote design keeps the authenticated browser on the operator’s
machine and lets Ollija connect through Chrome DevTools Protocol (CDP, a
browser-control interface) over Tailscale or an SSH tunnel:

```bash
./bin/ollija verify-production \
  --browser-cdp-url http://<operator-tailnet-host>:9222
```

Ollija opens a page in the remote browser, checks the headline element, records
only a SHA-256 text fingerprint (a one-way hash), and leaves cookies and browser
storage on the operator’s machine. The CDP endpoint must never be exposed to
the public internet.

The older local-storage mode remains available:

```bash
./bin/ollija verify-production \
  --browser-storage-state .ollija/state/production-browser.json
```

These modes are mutually exclusive. A missing browser session is a verification
failure, not permission to bypass authentication or mark the release complete.

## Receipts and evidence

Ollija stores small JSON receipts under `.ollija/state/receipts/`. A receipt is
an immutable record of an observed fact, such as:

- candidate commit selected;
- local refresh completed;
- hosted refresh completed;
- staging deployment became live;
- Bridgewright assessment passed;
- desktop approval recorded;
- iPhone approval recorded;
- production deployment verified.

Receipts are bound to the candidate SHA and, where relevant, the Render
deployment ID. If a new deployment replaces the reviewed deployment, the old
approval is stale even if the code is identical. This prevents an approval from
silently carrying over to a different live system.

Receipts must never contain database URLs, API keys, OAuth secrets, browser
storage, headline text, or raw production data. The production verification
receipt stores a headline hash rather than the headline itself.

## Safety rules

Ollija refuses mutating commands when:

- the working tree is dirty;
- the checkout is detached or on the wrong host;
- the repository authority is unavailable;
- the candidate, staging, or production SHA is inconsistent;
- a database identity is wrong or a target is not empty when emptiness is
  required;
- a refresh is stale or incomplete;
- an approval or assessment is bound to another deployment;
- required production services are not live at one exact SHA.

These are deliberate stops. Do not edit receipt JSON, force-push Git, copy
staging data into production, or manually create the beta tag to get past one.
Resolve the reported condition and rerun the same idempotent command when the
candidate has not changed.

## The important files

| File | Purpose |
| --- | --- |
| `bin/ollija` | The user-facing command wrapper. |
| `scripts/ollija/` | Python implementation of state, receipts, database guards, Render integration, approvals, and verification. |
| `.ollija/project.yaml` | The project contract: authoritative host, branches, resources, paths, safeguards, and verification settings. |
| `.ollija/state/` | Local runtime state and receipts. It is ignored by Git and must remain on `fuchitalee`. |
| `docs/operations/ollija.md` | Detailed operational runbook and recovery procedures. |
| `docs/operations/ollija-rollout-baseline.md` | Historical baseline and rollout record. |
| `.agents/skills/ollija/SKILL.md` | Instructions for AI agents using Ollija. |
| `.claude/skills/ollija` | Claude Code compatibility link to the canonical skill. |
| `render.yaml` | Production Render Blueprint (infrastructure-as-code configuration). |
| `render-staging.yaml` | Isolated staging Render Blueprint. |

## Common commands

```bash
./bin/ollija status          # Show the current state and exactly one next action
./bin/ollija doctor          # Diagnose setup and authority problems
./bin/ollija start           # Freeze a clean commit as a candidate
./bin/ollija refresh-local   # Build a guarded local review snapshot
./bin/ollija preview         # Start local private preview
./bin/ollija preview-stop    # Stop local private preview
./bin/ollija refresh-staging # Refresh hosted staging data
./bin/ollija stage            # Deploy candidate to hosted staging
./bin/ollija assess-ui       # Record Bridgewright assessment
./bin/ollija approve desktop # Record owner desktop approval
./bin/ollija approve iphone  # Record owner physical-iPhone approval
./bin/ollija release          # Promote approved candidate to production
./bin/ollija verify-production # Verify and seal the production release
```

When uncertain, run `./bin/ollija status`. It is read-only and is the workflow
authority.

## What success looks like

A release is complete only when:

1. the exact approved candidate is live in production;
2. all configured production services are healthy at that SHA;
3. the authenticated production feed visibly displays a headline;
4. DSV4 is configured for headline generation;
5. the beta tag exists; and
6. Ollija has written the final production receipt.

Until all six are true, the honest status is “deployed but not fully verified,”
not “release complete.”

For the detailed runbook, including database recovery and one-time Render setup,
see [`docs/operations/ollija.md`](../operations/ollija.md).
