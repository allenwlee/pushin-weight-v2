# Shared account migration verification

Source: feat/g3-account-extensions; initial base443d13f3, publishing base is the separately deployed PR59 revision948f05ad. Verification is local PostgreSQL17.9 with an isolated task database and temporary migration/shadow databases. Production account migration is not selected or performed.

## Result and storage census

The change keeps shared UUID account identity, moves33 X-specific current fields to the34-column x_account_details one-to-one extension, and retires hf_orgs. The existing companies_accounts gains nullable ownership_confirmed; Product.publisher_account points to generic Account. All150 concrete application tables/1931 physical columns are documented with exact inventory/column equality. This change adds1 table/retires1; PR59 independently added collection_jobs.

Pending HF namespaces remain explicitly false, independently unreviewed company-account links remain NULL, and source account creation dates remain unknown unless observed. Namespace discovery evidence preserves original namespace, discovery label, added_at and prior nullable account link for reverse migration. Existing linked identities and independent provider_metadata survive. Per-source product mappings, metric records and profile snapshots are unchanged.

## Executed evidence

- Characterization before implementation:27 tests passed;10 required PostgreSQL tests executed,0 skips/errors. The root virtualenv lacked Pillow; the already prepared collection environment was reused read-only.
- Proof-first X extension tests failed on missing XAccountDetail; publisher tests failed on missing helper module before code existed.
- Initial X implementation verification:81 tests passed;47 required PostgreSQL tests,0 skips/errors, including populated forward/reverse preservation and non-X evidence refusal.
- Full regression pass:563 passed/10 failed out of573. Causes were shared lookup-role fixture duplication, now-explicit organization kind, current models queried against historical schema, a moved badge-query field, and socket-only snapshot URL assumptions. Each was repaired without weakening behavioral assertions.
- Correction pass:55 passed with2 snapshot-policy mismatches. Updating the existing copied-table policy resolved both restore cases; subsequent151passed/1runbook-policy failure resolved by updating the actual existing grants/runbook.
- Final migration/X/HF/policy verification:93 passed;36 required PostgreSQL tests,0 skips/errors. Covers all33 field values, original snapshot equality, linked and pending HF ownership/product/UUID/date preservation, nullable prior-link roundtrip, atomic conflict refusal, split-write rollback, deferred parent fields, SQL parent deletion/cascading details and source membership guards.
- Final snapshot/plan-guidance verification:38 passed;2 required PostgreSQL tests,0 skips/errors. Both current-source and legacy collection-source dump/restore proofs preserve numeric history and classify the new physical account schema.
- Django system check, makemigrations --check --dry-run, scoped Ruff import/undefined-name checks, skill validator and whitespace checks pass.

The broad pass's initially failed cases are covered by successful correction/final checks. No earlier failed run is reported as green. CI on the published revision provides the integrated candidate check. There were no live provider requests, collection activation or production account writes.

## Review and material deployment limits

Native main-agent sequential reuse/quality/efficiency and correctness/data-migration/standards review followed the project task mapping. No independent-agent or cross-model review is claimed. The review confirmed source-qualified uniqueness, nullable review semantics, historical models/database alias use, exact field movement, atomic accepted-subset writes and positive source guards. Simplification writes first-time detail values in one insert and subsequent supplied fields in one update; immutable migrations intentionally retain their own schema logic.

Review fixes: route split saves through their actual database alias; preserve pending detail values while loading deferred parent fields; restore the old nullable HF account pointer; preserve SQL deletion lifecycle. The populated proof caught Django's deferred FK DDL ordering: migration0083 installs the cascading FK and source guards before copying rows and removes the deferred default FK statement. Forward and reverse proofs execute against actual populated PostgreSQL schemas.

Account production rollout requires a separately authorized coordinated code/schema cutover: old readers/writers cannot continue after their physical columns/table are removed. Preserve all old data in a pre-cutover backup, quiesce affected old processes under that rollout's authority, apply migrations and start/verify the same candidate on each affected service. Do not use Render's ordinary automatic predeploy migration while old account binaries remain active. No calendar rollover window or dual-write grace period is invented. Reverse refuses ambiguous/unknown ownership, changed namespace identity or non-HF product publishers the old schema cannot represent; do not force it.

The new staging-refresh policy intentionally requires source migration0084 and the x_account_details SELECT grant. A pre0084 source fails closed; do not use this candidate to refresh from the currently older production account schema. Rollout planning must order source migration/grants before that refresh. No source grant was applied by this task.

Browser scope mapping: no template, view, route, asset or frontend interaction changed. Standalone browser acceptance has no affected visual route to execute; this is not a browser-pass claim. Existing product-review and account/profile call-chain regressions were executed. All public forecast/chart/YouTube/GitHub source activation work remains separate.

## Frozen HF scope correction

A linked HF account can have a different equivalent namespace capitalization and independent discovery metadata. The populated preservation fixture reproduced an incorrect frozen-scope change (linkedlab versus LinkedLab). Publisher presentation/evidence helpers now retain original HFOrg namespace/discovery values while the source-qualified normalized identity still matches; independent account metadata survives. Changed identities use their current provider identifier rather than an obsolete alias. Reserved provenance-key collisions refuse migration atomically instead of overwriting existing metadata.

The strengthened HF migration/catalog/cohort-identity suite passed41 tests/35 required PostgreSQL tests with0 skips/errors; the additional provenance-collision test passed1 required PostgreSQL test. These checks cover the correction after the initial candidate's four CI checks passed; the corrected published revision receives its own CI run.

## Separate PR59 production delivery

Delegate verified PR59 merged and all six active production services at948f05ad0c42837ecfe4082539bf34dcea9d7a88; migrations0081/0082 and shared API present. All2,057,227 staging and369,169 preexisting production numeric rows unchanged. No collector activation; legacy services remain suspended. Existing collection plan and backfill interface hold full live receipts. This does not establish production account-migration readiness.
