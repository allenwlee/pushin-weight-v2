# Product-release primary-document staging result

Official announcement pages are now reusable source evidence in the staging database. The reviewed study has **35 separate product releases: 6 confirmed and 29 provisional**. This continuation confirmed DeepSeek 1017 and MiniMax Music 3.0 while preserving the other 33 current reviews and all prior reviews.

[Open the sortable report](2026-10-30-183147-product-release-primary-documents.html) · [Complete result, formatted JSON](2026-10-30-183147-product-release-primary-documents.json)

| Release | Announcement | Availability evidence |
|---|---|---|
| DeepSeek-V4.1-Flash-1017 | 2026-10-17 (day precision) | Official document states API access; first availability date/time remains unknown. |
| MiniMax Music / 3.0 | 2026-08-13 (day precision) | Not independently established; retained local-access reports remain context. |

The source URL, original capture bytes and checksum are retained through existing collection records. Announcement claims point to those captures. Publisher-control assessments are separately archived, explicitly reviewed by this session, and scoped to the announcing source. Capture time and database import time are separate. No official website Account or new Product was fabricated.

| Case | Observation | Capture time | Import time |
|---|---|---|---|
| PR11 | 1637047 | 2026-10-30T08:13:53.418635+00:00 | 2026-10-30T09:27:53.578005+00:00 |
| PR13 | 1637048 | 2026-10-30T08:13:53.464412+00:00 | 2026-10-30T09:27:53.763541+00:00 |

Database row changes in this bounded run:

| Table | Added rows |
|---|---:|
| `accounts` | 0 |
| `collection_evidence_archives` | 4 |
| `collection_jobs` | 2 |
| `collection_observations` | 2 |
| `collection_requests` | 0 |
| `collection_resource_snapshots` | 2 |
| `collection_runs` | 2 |
| `companies_accounts` | 0 |
| `discussion_window_counts` | 3921 |
| `discussion_window_snapshots` | 372 |
| `event_dossier_claims` | 27 |
| `event_dossier_discussion_windows` | 372 |
| `event_dossier_intake_decisions` | 6 |
| `event_dossier_reviews` | 2 |
| `event_dossier_sources` | 4 |
| `event_dossiers` | 2 |
| `product_release_details` | 2 |
| `products` | 0 |

Temporary intake dossiers, when created, are merged into the existing release identities. Added review/detail rows preserve history; they do not mean more than 35 distinct study releases.

Discussion reuse:

- PR11: 186 windows, 186 new numerical snapshots; immediate repeat added 0.
- PR13: 186 windows, 186 new numerical snapshots; immediate repeat added 0.

The discussion windows use stored staging Posts and classifications. Day-only release anchors use an explicitly labelled midnight convention; they do not establish an announcement hour. Historical coverage is incomplete. The source captures and shared numerical windows are available for later TN evidence selection; this continuation did not run the TN prose generator.

Verification and limits:

- Staging web and jobs are live at `6e0894133a715853f9deaa5dc15664cac6bf80b3`; native pilot `job-dbi659oae00c73bb9ie0` verifies migration 0208 and the absence of the unwanted Company.url column.
- The initial pilot rolled back after exposing a canonical-intake repeat defect. The existing test reproduced it; the fix completes source intake after a merge. Exact repeat in the corrected pilot adds no rows.
- After the fix, 28 document/study/pipeline tests and 32 detector/replay/report tests plus 12 subtests passed. The first group contains 28 required PostgreSQL tests, with no skips/errors. Earlier broader validation passed 116 tests and 12 subtests.
- The shared local test database was returned to its prior schema 0206. No production service, collector schedule or production data was changed.
- MiniMax X-account continuity remains unresolved. Website confirmation does not establish ownership of that X handle. Individual creator verification and broader acquisition/lineage automation remain follow-on work.
- No new model, provider collection or web request was used in this continuation. The two public-page captures came from the preceding session research.
- Broader PR CI is reported separately and is not claimed green. On the exact deployed source revision, the homepage suite reports 387 passed, one failed and 110 passing subtests. The failure is the same shared schema-reference mismatch; six other broad checks were still running at report preparation.

Browser validation passed at 1280 and 390 pixels: all 35 rows present, filtering and sorting work, official document links and dates are visible, no JavaScript errors, and wide content scrolls inside the table. Desktop and narrow-screen screenshots were visually inspected.

Final source-revision CI also reports 34 failures / 383 passes in collector regressions (retired collection fields and a stale profile-label fixture), and 19 failures / 348 passes in official-account tests (fixtures missing verified_type). Their failing test files and all 233 pre-existing model definitions are unchanged from the feature base. These are the same failure groups recorded during the preceding study. They remain red; remaining broad checks are not claimed passing. Broader shared-schema/fixture repair is outside this bounded primary-document continuation.
