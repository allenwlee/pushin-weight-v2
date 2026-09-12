# Stage 1C staging delivery receipt

Stage 1C is deployed and verified for its authorized staging scope. The
staging web service and headline worker run exact metadata revision M
`2d4e50f5b6a9d185190d2cf8919ad2b8664f9ae0`, which pins reviewed product
source P `84377b43d5938a07fbc6e95b1b7a4cf2212ceba1`. The staging harvest cron
remains suspended on its older revision. Production `main` remains unchanged
at `af272b6fe0b43be3276429792508749b9ddc8194`.

This receipt covers the thirteen-type taxonomy-v3/prompt-v4 contract, the
additive people, affiliation, job, event, opportunity, discovery-ledger, and
targeted-extraction schema, three-locale reference labels, provider-free
profile/discovery/extraction behavior, internal read contracts, and staging
database compatibility. It does not claim real classifier, discovery, or
extraction accuracy.

## Release identity

| Identity | Revision | Meaning |
| --- | --- | --- |
| P | `84377b43d5938a07fbc6e95b1b7a4cf2212ceba1` | Reviewed product source: taxonomy, schema, services, migrations, tests, and reference contracts |
| M | `2d4e50f5b6a9d185190d2cf8919ad2b8664f9ae0` | P plus the two exact-P UI-assurance pins; the revision deployed to staging |

The feature branch and remote `staging` ref both resolved to exact M before
verification. The later receipt-only commit is not a deployed product
revision.

## What is active on staging

- New classification output uses exactly thirteen post types under
  `stage1-taxonomy-v3` and `stage1-prompt-v4`.
- `events` requires attendance; `opportunities` requires a time-bounded action
  in exchange for a benefit. Past or closed items remain classifiable and are
  filtered by source facts plus a caller-supplied `as_of` time.
- `job_listings` and `personnel_changes` are distinct post types. Taxonomy-v2
  `events_opportunities` rows remain a separate historical population.
- Migrations 0031 through 0036 add normalized people, person-account,
  profile-snapshot, affiliation/evidence, organization-candidate,
  job/evidence, discovery-run, event, opportunity, and extraction-state
  storage without rewriting existing posts, accounts, or classification
  provenance.
- English, Simplified Chinese, and Japanese reference labels exist for every
  active post type. Japanese remains reference data rather than a selectable
  product locale in this release.
- The optional global job-discovery lane, personnel-discovery lane, and all
  targeted extractors remain disabled. The staging deployment did not run a
  harvest or provider acceptance call.

## Local candidate evidence

All local runs used disposable PostgreSQL and blank provider credentials.

- Full tracked provider-denied projection: 2,610 passed, 25 deselected, with
  required PostgreSQL execution `677/0/0` for executed/skipped/errors. Log
  SHA-256:
  `cbf384ed2e688050f90fd9a42b4225d38d2987070fc466455f08b48c616eed5f`;
  JUnit SHA-256:
  `73abdcfe9abd71437514fb1341c8f85c49b7e92e01a02654f208522460563560`.
- Exact P/M candidate gate: 199 pytest cases plus 64 subtests passed with
  required PostgreSQL `72/0/0`; Node suites passed `108/0` and `94/0`; all
  3,598 Bridgewright obligations passed with zero failed, skipped, errored,
  missing, or unknown obligations.
- Both deterministic performance scenarios (`homepage-desktop` and
  `homepage-mobile`) returned clean with zero findings. Performance attempt
  `c484a20f25549a4f30cf1943` used installed Bridgewright package commit
  `d0a5279ff1dcfab76f285b75a048b6611ee3c2d2` and declaration digest
  `d8d6715b2f3547292a46dfbaac63c4f205ea4343e143843218278c67d1ed291e`.
- Candidate log SHA-256:
  `a409dfd6a98c5d0b657f51f1dccd914fbea54c98be65094f9c72bd05fffc683e`;
  JUnit SHA-256:
  `87df3e64ac6f2154804b098e2fa75a6538c9672184039a66633762465994b4ca`.
- Fresh, upgrade-from-0030, and empty reverse migration proofs all passed.
  The reverse proof removed only the empty Stage 1C tables.
- `makemigrations --check --dry-run`, `git diff --check`, scoped Ruff, and
  Django deployment checks passed. Django reported only the expected local
  security-setting warnings.
- `pytest -q tests/ollija` passed 35 tests. The two assurance-pin contract
  files passed 8 focused tests.
- Local browser proof exercised the English and Chinese roots, all thirteen
  labels, the Job Listings and Personnel Changes filters, `/feed/`,
  `/chart.html`, and locale switching with no console error.

## Exact-SHA staging evidence

The remote `staging` ref advanced by fast-forward from
`a6599bcacc360879cc8037b429fa151613eccbd6` to exact M.

| Service | Render ID | Deploy | Revision | Result |
| --- | --- | --- | --- | --- |
| `pushinweight-staging-web` | `srv-d9vb8t49v7es738lf2ng` | `dep-dahbm03bc2fs73fn650g` | M | Live at `2026-09-10T14:14:50Z` |
| `pushinweight-staging-headlines` | `srv-da7vrdqd0e5s739uvcsg` | `dep-dahbm03bc2fs73fn65d0` | M | Live at `2026-09-10T14:14:38Z` |
| `pushinweight-staging-harvest` | `crn-da7vrdqd0e5s739uvcs0` | no new deploy | older `bdcfb638d66faf99723a42bd49adc243df3f891e` | Suspended; manual-only command retained |

The staging root returned the expected `302` OAuth redirect and the login page
returned `200`. A provider-denied SSH probe on the web service verified:

- exact deployed SHA, service, environment, PostgreSQL host, database, and
  database user;
- database connectivity and applied migrations 0031–0036;
- all thirteen new Stage 1C model tables;
- taxonomy v3, prompt v4, and exactly thirteen active post types;
- 39 nonblank active post-type labels across `en`, `zh-cn`, and `ja`;
- distinct Anthropic and Google DeepMind organization-facing brand rows; and
- disabled job discovery, personnel discovery, and targeted extraction.

All thirteen new intelligence tables contained zero rows at verification
time, which is expected because no backfill, discovery, harvest, or extractor
was activated. The probe was read-only and blanked provider credentials.

## Boundaries that remain

Production promotion is not authorized. Before any production proposal, U12A
must preserve the taxonomy-v2 real-label baseline and the preregistered
taxonomy-v3, job/personnel discovery, role extraction, and affiliation
extraction assessments must meet their support and quality floors. Activating
either discovery lane, any targeted extractor, public MCP/API access, or a
profile backfill also requires its separately documented authorization and
cost/quality gate.

