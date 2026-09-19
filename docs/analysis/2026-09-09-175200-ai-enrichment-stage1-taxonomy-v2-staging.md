# Stage 1 taxonomy v2 staging delivery receipt

The versioned taxonomy follow-up is deployed and verified for its authorized
staging scope. Staging web and the headline worker run exact metadata revision
M_B `a6599bcacc360879cc8037b429fa151613eccbd6`. The staging harvest cron remains
suspended and retains its older code. No production database was read or
changed, and no production deploy occurred during this follow-up.

This receipt covers the five identifier renames, strict taxonomy-v2 writes,
Japanese reference labels, compatible v1/v2 reads, and provenance-aware
historical analysis. It does not claim classifier accuracy or Japanese product
UI parity.

## Scope and release identity

| Release | Product revision | Metadata revision | Staging result |
| --- | --- | --- | --- |
| A: compatible readers | `a1b72acb8a146092d933c49a54e79aca2ce873d7` (P_A) | `a698504e43134064b5d000dbe2f96f78d7aa56f0` (M_A) | Web and worker deployed; compatibility probe passed |
| B: canonical cutover | `6bc9fd952eff558dc9f7c2e26a86b8967230331b` (P_B) | `a6599bcacc360879cc8037b429fa151613eccbd6` (M_B) | Web and worker deployed; taxonomy-v2 probe passed |

P identifies the reviewed product source. M adds only verification, fixture,
reference, and retired-diagnostic changes that do not alter the deployed
runtime product. Bridgewright source revision
`0390f3c42195856a67afcb1d62464052cebf3476` and installed performance package
revision `d0a5279ff1dcfab76f285b75a048b6611ee3c2d2` are tool identities, not product
revisions.

Release B makes these identifier-only changes:

| v1 alias | Canonical v2 key |
| --- | --- |
| `buzz_releases` | `releases_updates` |
| `performance_comparisons` | `results_evaluations` |
| `feedback_questions` | `questions_requests` |
| `event_announcement` | `events_opportunities` |
| `product_request` | `ideas_requests` |

New classification output is strict `stage1-taxonomy-v2` with
`stage1-prompt-v3`. Stored v1 and v2 state remains readable through the shared
crosswalk. Migration 0030 rewrites only eligible Stage 1 membership edges,
preserves each state's original taxonomy version, prompt version, model, and
classification time, and is deliberately irreversible.

The active 10 post types, 5 product labels, 4 sentiments, and 6 nationalism
values each have nonblank English, Simplified Chinese, and Japanese reference
labels. This produces exactly 25 Japanese rows across the four classification
families. Japanese is not exposed as a selectable UI locale in this release.

## Historical evidence retained unchanged

The follow-up did not rerun or rewrite the completed production observations.
Their tracked receipts remain the historical source of truth:

| Receipt | Purpose | SHA-256 |
| --- | --- | --- |
| `docs/analysis/2026-09-08-194415-enrichment-stage0-baseline.md` | Owner-selected 90-minute Stage 0 production baseline | `31647f70ae58048ea57b001b2b22b010d44dd78a2e90fe007387865117fa6e4f` |
| `docs/analysis/2026-09-08-134925-ai-enrichment-stage1-staging.md` | Original taxonomy-v1 Stage 1 staging delivery | `29eb1bf4c8a38870a2a30167f3d0c0aaf2b93859ccd0e4f46d3bdb032ca5ee09` |
| `docs/analysis/2026-09-08-134925-ai-enrichment-stage1-evaluation.md` | Synthetic contract evaluation and semantic limits | `2b645a59f3bb6c93591630f11f7bbb50c3cfee3a6634a999816c6c79d328a384` |

The Stage 0 baseline recorded 42 unique successful application transport
events in its bounded window, along with explicit pending-state and measurement
limits. It remains the before-refactor baseline. No new baseline, latest-20
cohort, production query, harvest, or provider call was made for this taxonomy
follow-up.

## Release A compatibility proof

Release A kept the writer on taxonomy v1/prompt v2 while making readers,
filters, SQL aggregation, health output, and the analysis interface compatible
with v1 and v2 keys.

- Aggregate run `20260909t050825z`: 2,523 passed and 25 deselected; required
  PostgreSQL checks were 621 executed, 0 skipped, 0 errors. Log SHA-256 is
  `e006a022f94de6285a1366436b6bed28c6161ca1f7e31e6a0517e6fd6ddbcd6a`;
  JUnit SHA-256 is
  `d30c27669bb9fdd1d7983f5eab9c9bbf97ac0c0de4eb3c444081b64a578dccac`;
  cleaned ownership receipt SHA-256 is
  `a4e27f0772d603a700e8ddbf4c2b99ef50df3e6e06a425b0331feeef0ec54aa0`.
- Candidate run `20260909t051250z`: 199 pytest cases plus 64 subtests passed;
  required PostgreSQL checks were 72/0/0 and all 3,475 UI obligations passed.
  Log SHA-256 is
  `8892bb2b8283868772f5b36b9c251efa24fc5a4734ee232b92d6ac8d3867da4e`;
  JUnit SHA-256 is
  `50d9e65f7af9a346b26d2833c3adcf6bf8d09f64879c2d8cd570e7f24cd69587`;
  cleaned ownership receipt SHA-256 is
  `4b12c9363cfc10d05a3e38e444a52237ded9ce538f3abf05f095144e78554a1e`.
- Exact-M_A English desktop and Chinese mobile browser proof passed after the
  bounded helper reconciliation. The accepted report SHA-256 is
  `b208c47dd055a5ff8b97fea790324d05ad1db541ae4d393b47ccf95a79aaaceb`.
- Release A web deploy `dep-dagfog6417fc73ffu6d0` became live at
  `2026-09-09T06:28:41.556795Z`; worker deploy
  `dep-dagfog6417fc73ffu6q0` became live at
  `2026-09-09T06:28:28.426217Z`.
- The exact-M_A staging probe passed migration 0029, writer identity,
  three-locale seeds, compatible reads, canonical deduplication, current-null
  precedence, unknown-provenance exclusion, both history policies, health,
  identity, and rollback cleanup. Receipt SHA-256 is
  `78633b71b93154601902130939c8f053b5951758982d3b0e92e5a6f5606352ae`.

## Release B local proof

U9 activated the canonical writer and forward-only edge migration. Its final
review-fix suite passed 208 tests with required PostgreSQL checks 44/0/0. Log
SHA-256 is
`73d1de7b0804050e2201608d097a26c6937a028397b96ba034d82ce307cc4e9b`;
JUnit SHA-256 is
`d7401db69f24f1f982e42691ee80fde13b7831574f11a00ceee9237dfdc11596`.

U10 reconciled current consumers and fixtures to canonical output while
retaining v1 only as compatibility input, stored provenance, or historical
evidence. Its focused suite passed 295 tests plus 52 subtests with required
PostgreSQL checks 168/0/0. Log SHA-256 is
`49a8a6c6f6f9624a455b7f361cabfa1873bd9351b50cf3028d829de72223eeb0`;
JUnit SHA-256 is
`cdaf129c20457aafeb49597b06a144b1ad9c318d740f75f3382f6af4de6a8dd4`.

The first Release B aggregate at M `e6834ca3b737104ad128e1cd5368b0cc5450cbcf`
failed seven tests because historical migration fixtures crossed the new
irreversible 0030 boundary and one label test sent compatibility aliases to the
strict v2 publisher. It passed 2,517 tests, failed 7, and deselected 25; required
PostgreSQL checks still executed 622/0/0. Its cleaned ownership receipt is
SHA-256
`92156a80f47f96db9600ca1608f158fd6c093d7e624b5f5d3fa71740c82dbaaa`.
The fixtures were corrected to preserve their historical target without
reversing 0030, and the active publisher assertion now uses canonical keys.

The corrected evidence at exact M_B is:

- Aggregate run `20260909t081512z`: 2,524 passed and 25 deselected; required
  PostgreSQL checks were 622/0/0. Log SHA-256 is
  `fcecdfec6483cfdca57c09ce0b2556224f4e070fc42cbd34d514f926c2aeddef`;
  JUnit SHA-256 is
  `ab18792ed02882ec6620edda476294d705c8d1ac9cbb12be2b424cd11d84afaa`;
  cleaned ownership receipt SHA-256 is
  `fc5badf8d9cf67a4245ac633eed44b9585ae6c97c25973651b5be779a697c94a`.
- Candidate run `20260909t082130z`: 199 pytest cases plus 64 subtests passed;
  required PostgreSQL checks were 72/0/0, Node suites were 108/0 and 94/0,
  both declared performance scenarios were clean, and all 3,475 UI obligations
  passed. Log SHA-256 is
  `64ab9b6c8335c4e32e614fc0e722691ba816b3a33b95a7c58c036f6f3c2c9897`;
  JUnit SHA-256 is
  `8e3cd64d1744b7121357688a9931daf90af570122325f146906e8daec06c4d69`;
  cleaned ownership receipt SHA-256 is
  `619c9bb46d9b73b7cebdaded7cd7129f6104e5f6faed124529f1f5ddfb97f9d0`.
- Dedicated headline gate: 235 passed; required PostgreSQL checks were
  210/0/0; the standalone worker-boundary check passed without provider
  transport. Ownership receipt SHA-256 is
  `fb9fb3a96b33044120c45a8a459a7d80542ab61561fa973c3693bd85e3707d45`.
- `pytest -q tests/ollija`: 35 passed. The temporary-directory cleanup warnings
  did not affect test results or the repository.

The classifier prompt exhibit is
`docs/reference/classifier-prompts.md`, SHA-256
`697fd01ed4eb53124780125dd4ea0aad702bf2fd67be893d61018fddbca18d57`.
It contains the exact 6,186-byte runtime system prompt at SHA-256
`ec2f4abf7e3b79a023c170239d1b8f8fa1847d893ba03ce70f0531d588da4e73`
and the EN/ZH-CN/JA label tables.

## Release B browser proof

Browser attempt 1 reached its bounded readiness timeout before the candidate
was ready and performed no browser action. Attempt 2 reached the isolated
preview but failed the helper's direct repository import; its report is
retained at SHA-256
`f1a6afa589b6f138ce1f66f68081ad991b64e7b157c52d376339007b0f496dc3`.
The scoped 75-byte import-path fix has SHA-256
`c71d747d13e3df51e5abce5a160ca009849dfd0c0a39906d7c74f64369662ed9`
and passed independent closure review.

Attempt 3 passed at exact P_B/M_B. Its report SHA-256 is
`33a7e3a17fc43bef955f68f76c6053e7089a701f9bd343d634e527e7462ee313`.
It verified English desktop and Simplified Chinese mobile, all five alias-to-
canonical filters, canonical DOM/feed/icon output, exact M_B homepage revision
headers, absence of Japanese selectors and discourse controls, empty console
and page-error lists, 86 owned responses with no failures, and no external or
websocket attempts. The parent-owned completion marker is SHA-256
`d58259fa2c3600484135bca7acc686553525c5279b63f03a50baf3b693f6d623`.

This proof used a public-only deterministic local preview. It did not create an
OAuth identity or authenticated staging session. API responses do not carry
the homepage-only revision header, so alias equivalence is tied to the exact
preview process and its homepage header rather than an invented API identity.

## Release A-on-B data proof

Run `20260909t083227z` archived exact M_A and M_B, verified each archive's
commit identity, created an owned disposable database, seeded v1 state before
0030, applied actual migration 0030 with Release B, and then used exact Release
A source to read the post-0030 database. Release A read recognized v1 and v2
state, retained its v1/prompt-v2 writer identity, and kept the unversioned
legacy policy separate. Migration 0030 was never reversed and no Git ref or
staging deployment moved backward.

- Proof log SHA-256:
  `548175a600097caad5dc2d98a7cd082383eb880206c504a3f4896cbe38a81db0`.
- Final ownership receipt SHA-256:
  `f4c26496ce528f64006a0cb4b6376a0fb635da40a42b4abb08fc08600a2288c2`.
- M_A archive SHA-256:
  `c731e594c16b33e7be2f53c9826ffb211176942c80f0fbbe6ffba7edc0fbd4a8`.
- M_B archive SHA-256:
  `7117b59cbe5a632022d23def23ca170ab1ef8c7f5ec1fd64ea36280eae7d029d`.

The owned database was dropped after zero sessions were verified. No force or
backend termination was used.

## Exact-M_B staging proof

Before deployment, exact Release A web and worker runtimes were stable, and
four worker samples showed zero queued, active, reserved, scheduled,
unacknowledged, or namespaced work. The parent detached only the idle old
consumer. After M_B deployed, the replacement worker had a new exact-M_B node,
the one owned queue was reattached, and four more samples remained idle.

| Worker guard step | Receipt SHA-256 |
| --- | --- |
| Observe exact M_A node and idle boundary | `c8f76e088d67cff9e82b2bb7eae68e33185ff57881dff9a332e0b2d2f18a0dfa` |
| Cancel only the old node's `trend-narratives` consumer | `2d8e70a41358e2cbdefd216e64727a14230377df69ce5edaaffaeef40aeb9564` |
| Verify replacement exact-M_B node and queue | `67fef7910ba2727dad31318bfda722ad0a40013076c3f178bc5c69d40f23459d` |

The server-enforced fast-forward moved `refs/heads/staging` from exact M_A to
exact M_B. Web deploy `dep-daghng8ae00c73bs4qbg` became live at
`2026-09-09T08:42:54.582269Z`; worker deploy
`dep-daghng8ae00c73bs4qo0` became live at
`2026-09-09T08:42:51.515765Z`.

The Phase B staging probe ran from `2026-09-09T08:44:54.502107Z` through
`2026-09-09T08:45:00.668398Z`. It verified exact service, environment,
database, user, host, revision, and health plus:

- migration 0030 and taxonomy-v2/prompt-v3 writer identity;
- three preexisting v1 states observed with unchanged count;
- exactly 25 Japanese taxonomy reference rows;
- compatible v1/v2 reads and canonical aggregate deduplication;
- current-null precedence and unknown-provenance exclusion;
- separate `current_definition` and `historical_inclusive` analysis output;
- transaction-local fixture rollback and cleanup;
- blank provider credentials and a denied queue endpoint.

The probe receipt SHA-256 is
`35caf70e2a5b5f22d2da4d0de0d6c71db43be4630a61f04f513d161812ade802`.
The three-state observation is a count-preservation check for this staging
database, not a claim that every historical production record was inspected.

A final live-state snapshot verified remote staging and feature refs,
exact-M_B web and worker deployments, no nonterminal staging deploys, the
login-wall redirect, the suspended cron, and unchanged production `main`. Its
SHA-256 is
`6bad883efd6c5d54cef690e2851a97658fa29ec300681c87af5f848543de540f`.

## Staging cron and production boundary

Staging cron `crn-da7vrdqd0e5s739uvcs0` remains suspended with dormant schedule
`0 0 31 2 *`. It has no job or log after suspension and retains old live code
`bdcfb638d66faf99723a42bd49adc243df3f891e`; it did not deploy or run with
Release A or B. The original suspension receipt is SHA-256
`609b2df1bcadb34c9b47cbab8e37a6051832e8f788c16db45ea1e6ef7cd6e572`;
the later suspension verification is SHA-256
`cc15b50fe9e7cb45f255a84bc09dc60a4bc209508f580feda3851f466122c0c4`.

Production `main` remained
`af272b6fe0b43be3276429792508749b9ddc8194`. This follow-up made no production
deployment or database read, started no harvest or headline job, and invoked no
provider. The canonical staging worktree is retained as required for a
staging-only delivery.

## Future analysis and remaining gate

The shared analysis interface requires an explicit half-open UTC range over
`Post.created_at` and one of two policies:

- `current_definition` reports recognized versioned Stage 1 state with
  canonical v2 keys and separates stored v1 from v2 provenance;
- `historical_inclusive` adds unversioned legacy rows only in a separately
  labeled `legacy_unversioned_approximate` section.

Approximate legacy rows never enter exact Stage 1 denominators. Unknown state
versions are excluded and warned about, null post timestamps are excluded and
counted, and legacy product-label availability is reported as unavailable
rather than zero. The latest-state table records the classification visible at
query time; it does not reconstruct arbitrary past states. Physical Django
model and table names remain stable, while taxonomy and prompt versions carry
the semantic era.

No fresh heldout cohort was adjudicated. Type, product-label, sentiment, and
nationalism accuracy in English, Simplified Chinese, and Japanese remains
unmeasured. R17's heldout semantic assessment and numeric floors remain a
preproduction gate and block any production recommendation until separately
completed and explicitly authorized.
