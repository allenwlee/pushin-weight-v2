# PostHog initial setup verification

The independent analytics foundation works locally and can send labeled browser and server events to US PostHog project 652560. The [traffic and usage dashboard](https://us.posthog.com/project/652560/dashboard/2184992) has production charts and a separate setup table containing two actual test records.

[receipt.json](receipt.json) records the live event identifiers, dashboard queries, file hashes and local checks. The final focused suite passed 28 tests and 13 subtests. It used an isolated PostgreSQL database and the real official browser SDK with intercepted test-suite requests. One additional bounded live verification sent exactly one anonymous pageview and one server setup event. No real user traffic was collected by this work.

The suite verifies stable signed-in IDs, account switches, logout reset, sanitized URLs, opt-in, browser preferences, bots, disabled configuration, a blocked SDK and delivery failure logs. Application source defaults to disabled. Production still needs a selected deployment endpoint and visitor preference control; no commit, push or deployment occurred.

Repository-wide Ruff has 1,854 findings outside the changed Python files, while scoped checks pass. Three unchanged cookie tests that directly call the homepage view fail because their mocked chart response lacks `computed_at`. These are recorded as existing coverage limits, not passed checks. The maintained real homepage route regressions pass with the local test environment configured correctly.

The disposable database was stopped after verification. Runtime scripts, downloaded SDK and database data remain under ignored `.pytest-tmp/`; the one-off live script refuses to run again while its receipt exists. The operating workflow and configuration are in [the analytics guide](../../operations/posthog-analytics.md).
