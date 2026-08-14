You are an expert technical editor transforming developer notes into a strategic README for intelligent, non-developer decision-makers. Rewrite the input using three distinct filters: Strategic Value (Venture Capitalist lens: core capabilities, problem solved, system leverage), Logical Mechanics (Investigative Journalist lens: plain-English data flow, boundary conditions, explicit failure modes), and Operational Friction (Operations Director lens: required resources, setup effort, configurable knobs). Strictly avoid low-level code syntax, internal implementation details, and patronizing ELI5 metaphors.

# Ollija: Strategic Release Control for PushinWeight

## Executive view

Ollija is the release-control layer for PushinWeight, a live data product that
turns social-post activity into trend analysis and headlines. It governs the
transition from a proposed software change to a reviewed production release.

Its value is not that it builds the product. Its value is that it makes each
release explainable, reviewable, and tied to one identifiable version of the
system. For a single-developer project approaching beta, this provides much of
the risk control normally created through separate engineering, operations,
quality-assurance, and release-management roles.

Ollija addresses a simple business risk: a change can appear correct while the
developer is looking at the wrong code, the wrong data, or a different deployed
version. Ollija creates evidence that those identities match.

## Strategic value

### The problem solved

PushinWeight has several moving parts:

- a customer-facing web application;
- a PostgreSQL database containing posts, brands, and trend narratives;
- scheduled harvesting and background processing;
- external data and language-model providers;
- cloud-hosted production and staging environments;
- authenticated pages that must be checked as a real user would see them.

The operational risk grows with the number of boundaries between those parts.
A green deployment only proves that a build completed. It does not prove that
the web service, background workers, database, credentials, and visible page
all correspond to the intended release.

Ollija makes those boundaries explicit and requires evidence at each one.

### Core capabilities

1. **Version identity** — freezes one exact code revision as a release
   candidate and rejects evidence from other revisions.
2. **Data-safe review** — creates a scrubbed review snapshot from production-
   derived data without allowing the review system to write to production.
3. **Environment separation** — keeps local preview, hosted staging, and
   production distinct in code, database, credentials, and hostname.
4. **Human review capture** — records owner approval for desktop and physical
   iPhone review against the exact staging deployment.
5. **Production proof** — verifies that the production services run one exact
   revision and that an authenticated user can see a non-empty headline.
6. **Release evidence** — stores compact, tamper-evident receipts rather than
   relying on memory, screenshots, or informal status messages.

### System leverage

Ollija concentrates several controls in one workflow instead of requiring a
large organization to coordinate them manually. It does not eliminate human
judgment; it makes the scope of that judgment precise.

The system is especially valuable at the beta stage because the cost of a
production mistake is already meaningful, while the team is too small to
justify a complex enterprise release organization. Ollija is intended to be
lightweight enough for one developer but structured enough to preserve a clear
record of what was reviewed and released.

## Logical mechanics

### The release chain

The operating sequence is:

```text
clean code change
  → candidate version
  → reviewed data snapshot
  → isolated staging deployment
  → desktop and iPhone approval
  → production promotion
  → authenticated production verification
  → beta tag and release receipt
```

Each arrow is a gate. A later gate cannot legitimately substitute for an
earlier one. For example, a successful production page cannot retroactively
prove that the staging database was scrubbed correctly.

### Data flow

1. Ollija reads production through a dedicated read-only database identity.
2. It creates a database snapshot and restores it into a uniquely identified
   local review database.
3. It removes authentication state, sessions, queues, and other operational
   state that should not travel into review.
4. It preserves the trend data needed to evaluate headlines.
5. It copies the validated snapshot to the isolated hosted staging database.
6. The candidate code runs against that staging database.
7. Production remains a source of read-only review data, never a test target.

This is a controlled snapshot process, not real-time replication. The benefit
is predictability: the reviewer knows which data was used and which rows were
preserved or removed.

### Deployment identity

Every candidate is identified by a Git commit SHA (a cryptographic identifier
for one exact code revision). Staging and production deployment records must
report that same SHA.

Ollija also binds evidence to the Render deployment ID (the cloud platform’s
identifier for one running deployment). This distinction matters: redeploying
the same code can still create a new deployment, and a human approval should
not silently transfer to an unreviewed deployment.

### User-visible verification

The feed requires Google authentication. A public HTTP check can prove that the
website responds, but it cannot prove that an authenticated user sees a
headline.

Ollija therefore supports an authenticated browser probe. The browser can be
local to the operator or remain on another authorized machine through Chrome
DevTools Protocol (CDP, a browser-control connection) over a private network.
Ollija checks the headline element and stores only a one-way text fingerprint,
not the headline text, cookies, or browser storage.

### Boundary conditions and failure modes

Ollija stops rather than guessing when it detects any of the following:

- the working copy contains uncommitted changes;
- the candidate does not match the staged or production revision;
- a staging or production deployment was replaced after review;
- a database target has the wrong identity or unexpected existing data;
- scrubbed authentication or queue state remains in the review database;
- a required service is not live;
- provider configuration does not match the intended model or credential scope;
- the authenticated headline is missing, empty, or still shows the unavailable
  state;
- a required desktop or physical-device approval is missing.

These conditions are designed to produce a diagnostic next step. They are not
failures to be bypassed by editing receipts, force-pushing a branch, or creating
a release tag manually.

## Operational friction

### Required resources

- one authoritative PushinWeight checkout on `fuchitalee`;
- Git and a reachable GitHub remote;
- Render access for the production and isolated staging resources;
- PostgreSQL command-line tools for guarded snapshot operations;
- a local PostgreSQL instance or equivalent review database;
- Tailscale for private local preview access;
- Google OAuth credentials dedicated to staging;
- Bridgewright for UI assessment;
- a desktop browser and the physical iPhone 13 used for owner review;
- an authenticated browser session or private CDP endpoint for final production
  verification.

`allenwlee` is used as a browser and keyboard endpoint, not as a second source
checkout. Repository files, database snapshots, and Ollija receipts remain on
the authoritative machine.

### Setup effort

The one-time setup is the expensive part. It includes registering the Render
staging Blueprint (an infrastructure definition), creating the staging
database and web service, configuring a separate Google OAuth client, recording
resource identities, and establishing the local database credentials.

After setup, the normal loop is intentionally command-driven:

```text
start → refresh-local → refresh-staging → stage
→ assess → approve desktop → approve iPhone
→ release → verify production
```

The operator should normally begin with `./bin/ollija status`. Ollija reports
one recommended next action rather than presenting a menu of potentially
unsafe alternatives.

### Main configurable knobs

- **Staging access:** the allowlisted Google email addresses.
- **Review data:** which production-derived entities are preserved and which
  operational tables are scrubbed.
- **Provider controls:** whether headline generation, harvesting, and external
  provider calls are enabled in a given environment.
- **Deployment timing:** Render’s build, health-check, and polling intervals.
- **Headline verification:** the production path, selector, unavailable-state
  text, and browser connection mode.
- **Release version:** the package version and beta tag format.
- **Receipt retention:** how long prior local recovery state is retained.

These settings are project-contract inputs. They should be changed in a reviewed
code change, not as an informal workaround in a live environment.

## Governance and accountability

Ollija is not a security boundary by itself and does not replace access control
provided by GitHub, Render, Google, PostgreSQL, or the operating system. It is a
process-control layer that makes unsafe transitions difficult and observable.

The owner remains accountable for the two human approvals. Bridgewright can
assess a page but cannot approve it. An automated test can report that a route
responds but cannot claim that a human reviewed the physical iPhone.

The release record distinguishes three facts that are often conflated:

1. code was promoted to production;
2. production services became healthy;
3. an authenticated user visibly received the intended feature.

Only the combination of all three, plus the beta tag and receipt, constitutes a
fully verified release.

## Decision summary

Ollija is appropriate when the product has meaningful production data, a real
user base or beta cohort, and one developer who needs dependable separation
between experimentation and release. It provides a compact control system with
low recurring operating cost.

Its principal trade-off is intentional friction: a release takes longer than a
direct deployment because the system requires fresh data identity, deployment
identity, human review, and production proof. That friction is the product. It
converts an informal “it looked fine” decision into a bounded, auditable claim:
this exact version was reviewed in this environment, then confirmed live in
production.
