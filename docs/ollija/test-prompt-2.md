> **Superseded Ollija workflow — historical record.** This retained writing
> prompt describes the former release controller. For current behavior, read
> the [Ollija plan guide](README.md).

You are an expert technical editor transforming developer notes into a strategic README for intelligent, non-developer decision-makers. Rewrite the input using three distinct filters: Strategic Value (Venture Capitalist lens: core capabilities, problem solved, system leverage), Logical Mechanics (Investigative Journalist lens: plain-English data flow, boundary conditions, explicit failure modes), and Operational Friction (Operations Director lens: required resources, setup effort, configurable knobs). Strictly avoid low-level code syntax, internal implementation details, and patronizing ELI5 metaphors.

Output a scannable document formatted strictly into three sections: 1. System Value & Capability (what it achieves and why it matters), 2. How It Works & Boundaries (step-by-step logic, input/output data flows, edge cases), and 3. Operational Prerequisites & Quickstart (resource requirements, setup steps, key configurations). If technical specifics are missing from the source text, state the operational dependency clearly without guessing. Every sentence must convey functional behavior, system impact, or deployment effort.. save as test-prompt-2

## 1. System Value & Capability

Ollija controls the path from a PushinWeight code change to a reviewed
production release.

It reduces the risk that one developer tests one version, reviews one database,
and deploys a different version.

It binds the candidate code revision, review database, staging deployment,
desktop approval, iPhone approval, production deployment, and final headline
observation to one exact release identity.

It separates experimentation from production by providing local preview,
isolated hosted staging, and customer-facing production as distinct operating
environments.

It protects production data by reading it through a dedicated read-only
database identity and copying only a scrubbed review snapshot into staging.

It converts informal release confidence into receipts that record what was
observed, which deployment was reviewed, and which version reached production.

It gives a single developer a lightweight substitute for several organizational
controls: release management, environment checks, data handling review,
device-specific acceptance review, and production verification.

It does not replace GitHub, Render, Google OAuth, PostgreSQL, or operating-system
access controls.

## 2. How It Works & Boundaries

1. Ollija checks the authoritative repository, host, Git state, Render access,
   database tools, and local staging database before permitting a state-changing
   action.
2. Ollija selects a clean Git commit as the candidate and assigns the candidate
   package version and beta tag.
3. Ollija reads production through a read-only PostgreSQL account and creates a
   database snapshot.
4. Ollija restores the snapshot into a uniquely named local PostgreSQL database,
   applies the candidate’s database migrations, and runs application checks.
5. Ollija removes authentication records, sessions, tokens, queues, and other
   operational state while preserving brands, posts, trend aggregates, and
   published narratives required for review.
6. Ollija validates schema, row counts, database identity, and scrubbed-state
   counts before activating the local snapshot.
7. Ollija copies the validated snapshot to the isolated hosted staging
   PostgreSQL database and verifies the target identity before activation.
8. Ollija deploys the exact candidate commit to the hosted staging web service
   and waits for a live deployment at that commit.
9. Bridgewright assesses the rendered staging surface and records assessment
   evidence without receiving approval authority.
10. The owner separately reviews the exact hosted deployment on desktop and the
    physical iPhone 13, and Ollija records each approval against that deployment.
11. Ollija rechecks candidate identity, refresh receipts, staging identity,
    deployment identity, assessment evidence, and owner approvals before moving
    `main` to production.
12. Render deploys the promoted commit to the configured production services.
13. Ollija confirms that the production services are live at one exact commit,
    that public health and sign-in routes respond, and that the configured
    headline model and provider credential are correct.
14. Ollija opens an authenticated production browser page, confirms that the
    headline element is visible and non-empty, and stores a one-way text hash
    rather than the headline text or browser credentials.
15. Ollija creates and pushes the beta tag only after the production checks pass.

Production-derived data flows from the production database to a scrubbed local
review snapshot, then to isolated hosted staging, and never from staging back to
production.

The candidate commit SHA (a cryptographic identifier for one exact code
revision) flows through each deployment and receipt, and any mismatch stops the
workflow.

The Render deployment ID binds human approvals to one actual cloud deployment,
and a replacement deployment makes the prior approvals stale even when the code
revision is unchanged.

The production feed requires Google authentication, so an anonymous HTTP check
cannot prove that a user sees a headline.

The authenticated browser may remain on the operator’s machine and connect to
Ollija through Chrome DevTools Protocol (CDP, a browser-control interface) over
Tailscale or an SSH tunnel.

Ollija leaves browser cookies and storage on the operator’s machine and stores
only the resulting headline fingerprint.

The remote-browser setup depends on a reachable private CDP endpoint and an
authenticated browser context; the repository does not provision that endpoint.

Ollija stops when the working tree is dirty, the candidate is stale, the
database identity is wrong, a staging target is unexpectedly populated, scrubbed
state remains, a required service is not live, provider configuration is wrong,
an approved deployment has been replaced, or the authenticated headline is
missing or unavailable.

Ollija does not infer success from a green build, edit receipts to bypass a
failure, force-push branches, copy staging data into production, or create a
beta tag before final verification.

## 3. Operational Prerequisites & Quickstart

The authoritative PushinWeight checkout must exist on `fuchitalee`, and project
files, database snapshots, receipts, and release artifacts must remain there.

The operator must have GitHub access, Render access, PostgreSQL command-line
tools, a local PostgreSQL review database, Tailscale access, and Bridgewright.

Render must provide separate production and hosted-staging web services and
databases, and staging must have its own hostname, database credentials, Google
OAuth client, and owner allowlist.

The operator must have a desktop browser and the physical iPhone 13 used for
owner review.

Final production verification additionally requires either a local Playwright
storage-state file or an authenticated remote browser reachable through a
private CDP endpoint.

Run the ordinary workflow in this order:

```text
./bin/ollija status
./bin/ollija start
./bin/ollija refresh-local
./bin/ollija preview
./bin/ollija preview-stop
./bin/ollija refresh-staging
./bin/ollija stage
./bin/ollija assess-ui
./bin/ollija approve desktop
./bin/ollija approve iphone
./bin/ollija release
./bin/ollija verify-production
```

`./bin/ollija status` is the read-only entry point and reports the one next
action permitted by the current state.

`./bin/ollija doctor` checks setup and authority problems without changing
release state.

The project contract configures the authoritative host, repository, staging and
production branches, Render resource identities, database safety policy,
refresh retention, deployment polling, headline selector, unavailable-state
text, DSV4 model requirement, and browser verification mode.

The environment controls determine whether harvesting, headline queueing, and
external provider calls run in staging, and staging review should keep those
provider-backed actions disabled unless a separate test explicitly requires
them.

The staging database refresh policy determines which production-derived records
are preserved and which authentication, session, queue, and environment records
are scrubbed.

The production browser verification mode accepts either
`--browser-storage-state <path>` or
`--browser-cdp-url http://<private-host>:9222`, and the two modes cannot be used
together.

The CDP endpoint must remain private through Tailscale or an SSH tunnel because
it provides control over an authenticated browser.

The first beta release uses package version `0.2.0b1` and tag `v0.2.0-beta.1`,
unless the project contract is intentionally changed before a new candidate is
started.
