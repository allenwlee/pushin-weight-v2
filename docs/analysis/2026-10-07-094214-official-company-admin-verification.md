# Official-company admin console verification

The owner identified the existing product-review inbox as the admin page and
requested `/admin` plus official-account detail. This follow-up preserves owner/
staff authorization, product decisions, CSRF checks and old proposal forms.

## Local evidence

- Real Chromium baseline: `/product-review/?locale=en` rendered the review inbox;
  the new `/admin` regression failed with HTTP404 before the implementation.
- Discovery CI-equivalent command: 212 passed, including179 required PostgreSQL
  tests, zero skips/errors. Includes new registration -> list sync -> admin data
  path, bounded pagination/query count and already-open legacy approval form.
- Staff/staging CI-equivalent command: 302 passed, including176 required
  PostgreSQL tests, zero skips/errors. Ollija checks:36 passed.
- Chromium: populated and empty real routes; EN/zh_hans/JA; owner login; account
  evidence expansion; script text escaped; mobile page without document overflow;
  product approval persisted through the real form. Before/after PNGs retained
  locally under `.pytest-tmp/admin-*.png` (deterministic test data).
- Nullable migration0069 applied forward, reversed to0068, and applied forward
  on isolated PostgreSQL17.9 database `pw_official_co_20261006`. Model/migration
  consistency check passed. Changed standalone Python files pass Ruff.
- Homepage control/filter/chart/feed behavior is unchanged. The homepage
  Bridgewright stateful profile does not cover this separate owner console.

## Production baseline and outstanding endpoint

Read-only Render PostgreSQL inspection before this follow-up found0 discovery
states,0 attempts,0 registrations,0 list intents and0 scans. Production web and
harvest are live at14970271 with discovery/registration/list flags off. Encrypted
credential provisioning, live renewal and owner/private-list preflight already
passed. The earlier manual Reflection add is separate evidence, not an extractor
add. This receipt does not claim initial scan activation or verified collection.

The console counts acknowledged additions separately from membership readback
and pre-existing membership. Request/acknowledgement timestamps are nullable;
historical confirmation without an add receipt does not establish an addition.

The parent retains the authorized whole-database scan, normal scheduled-cycle
progress and subsequently collected, correctly attributed post as the remaining
production endpoint. No staging mutation or production pause occurred.

## Follow-up before deployment

A fresh hosted run exposed the missing Playwright Python package before tests
started. Discovery CI now installs the same Playwright requirement already
present in the local development dependency group. The official table also
excludes ordinary queued scan states; accepted accounts and list-history rows
remain visible even while the whole-population backlog grows. A regression uses
60 newer pending authors to verify that found companies and existing list history
remain on the first page while global pending counts remain accurate.
