# Integrated staging refresh and browser verification

**Environment:** staging  
**Candidate:** `cb715ce205b2e5417d981981971a7cb9c14d0334`  
**Refresh completed:** `2026-09-11T15:46:14.676490+00:00`  
**Decision:** staging data, migration, worker-isolation, and disabled-lane checks pass; production remains blocked by U18 classification quality.

## Plain-English Summary

Staging now uses a fresh, scrubbed copy of production data instead of its stale
database. The refresh copied product data, ran the additive Stage 1 migrations,
removed login, scheduler, provider, and queue state, verified the result, and
kept the displaced staging database as a disabled recovery point. Production
data was read through the dedicated read-only refresh account and was not
changed.

The refreshed site renders its chart and feed in English, Simplified Chinese,
and Japanese. The 13 post-type labels render in all three languages, and the
seven owner-selected Column A glyphs use the exact locked symbol IDs at 15 by
15 CSS pixels on desktop and mobile. Headline serving is live on the same
candidate while provider calls, demand shaping, and critic routing remain off.
The synthesis worker and staging harvester remain suspended.

Historical posts remain deliberately separate from the new taxonomy. They are
visible when all post types are selected, but narrowing the post-type control
returns no rows until current, versioned classifications exist. Staging has no
such rows because classification activation remains blocked by the U18 quality
gate. This avoids silently assigning old records to new meanings.

## Guarded refresh receipt

The guarded refresh completed and `./bin/refresh-staging-data verify` recovered
the same database-stored receipt.

| Field | Value |
| --- | --- |
| Source | `production/pushinweight_shadow` |
| Target | `staging/pushinweight_staging` |
| Snapshot time | `2026-09-11T15:21:42.081758+00:00` |
| Dump bytes | `287025794` |
| Dump SHA-256 | `4d9dc1d74fb2dfb555534b65438870aef5563bdbb211e0f19c715fc0de6f8cbc` |
| Recovery database | `pushinweight_staging_recovery_20260911t154614z` |
| Rollback confirmation | `ROLLBACK staging/pushinweight_staging_recovery_20260911t154614z -> staging/pushinweight_staging` |

Product counts matched the receipt after applying only the declared forward
migration deltas:

| Relation | Source | Staging | Declared delta |
| --- | ---: | ---: | ---: |
| `accounts` | 70,329 | 70,329 | 0 |
| `brands` | 34 | 36 | +2 from migration 0033 |
| `brands_companies` | 35 | 37 | +2 from migration 0033 |
| `companies` | 31 | 31 | 0 |
| `posts` | 217,402 | 217,402 | 0 |
| `posts_brands` | 261,233 | 261,233 | 0 |
| `products` | 1 | 1 | 0 |

The latest copied post timestamp was `2026-09-11 15:15:16+00`. Migration 0033
also added exactly two `brands.display_name_en` values; all other translation
counts matched the source.

## Independent database census

The independent read-only census confirmed:

- the migration graph reaches `core.0039_affiliation_candidate_and_integrity_guards`;
- all 23 Stage 1 tables exist;
- the new observation and classification tables are empty as expected, while `product_label_keys=6` and `product_label_labels=17` contain seed data;
- copied historical classification relations contain `posts_brands_discourse=95,664`, `posts_brands_mentions=261,080`, `posts_brands_signals=166,823`, and `posts_unsanctioned_flags=11,040` rows;
- `posts_brands_classification_states=0` and `posts_brands_product_labels=0`, preserving the current-versus-historical boundary;
- all 29 scrubbed authentication, scheduler, queue, budget, and provider-state tables contain zero rows;
- no current narrative window is duplicated and no foreign key is unvalidated;
- `django_site` is `pushinweight-staging-web.onrender.com` / `Pushin Weight Staging`;
- the receipt-named recovery database has `datallowconn=false`, and every older recovery database found is also disabled;
- no refresh dump remains under `/tmp` or the repository's `.staging-refresh` directory.

The production reader account needed one least-privilege correction before the
refresh: `SELECT` was granted on the six geography relations added in migration
0026. The account still cannot write, and no production row changed.

## Service and control state

| Service | State | Deployed revision |
| --- | --- | --- |
| `pushinweight-staging-web` | live, not suspended | `cb715ce205b2e5417d981981971a7cb9c14d0334` |
| `pushinweight-staging-headlines` | live, not suspended | `cb715ce205b2e5417d981981971a7cb9c14d0334` |
| `pushinweight-staging-synthesis` | suspended | `7a58daefb4ac22fb71364f5d84e457d1a8c39877` |
| `pushinweight-staging-harvest` | suspended | `bdcfb638d66faf99723a42bd49adc243df3f891e` |

The headline worker connected only to its `trend-narratives` queue and reached
Celery ready state. Its runtime controls were inspected without displaying
credentials:

- `X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED=False`
- `X_MONITOR_HEADLINE_DEMAND_SHAPING_ENABLED=False`
- `X_MONITOR_HEADLINE_CRITIC_RISK_ROUTING_ENABLED=False`
- `X_MONITOR_HEADLINE_ACTIVATION_STATE=owner_override`
- `X_MONITOR_HEADLINE_CONTROL_REVISION=staging-v24-integrated-ja-demand-20260911`

Production web, harvest, and headline services were independently checked and
remain active.

## Browser verification

Anonymous requests returned the expected `302` login redirect, and the login
page returned `200`. For owner-only testing, an ephemeral staging user and
database session were created, used only for this browser run, and deleted at
the end. The scrub verifier intentionally failed with
`active_scrub_incomplete` while that session existed and passed again after
cleanup, proving the guard detects temporary authentication state.

Authenticated checks against the deployed staging URL showed:

- the seven-day chart and feed render in English, Simplified Chinese, and Japanese with no browser console or page errors;
- desktop renders 50 feed rows and a nonzero `580.64 × 240` chart canvas;
- Japanese exposes all 13 translated post-type labels;
- the seven locked symbols are `#a-opportunity`, `#a-jobs`, `#a-personnel`, `#a-opinions`, `#a-research`, `#a-finance`, and `#a-other`;
- all seven symbol definitions use `viewBox="0 0 24 24"` and `currentColor`, and every rendered filter glyph measures exactly `15 × 15` CSS pixels;
- at `390 × 844`, the post-type panel stays within the viewport, all 13 labels and glyphs render, the feed contains 50 rows, and the chart canvas is `336 × 180`;
- at `320 × 700`, the page has no horizontal document overflow and the chart canvas is `266 × 180`;
- changing a post-type checkbox issued successful `200` chart and feed requests with the canonical 13-type filter payload.

The browser run also exercised the bounded demand writer: visible and
lookahead rows created 8 synthesis-demand rows and 32 rate-limit buckets while
the suspended worker and disabled provider flag prevented synthesis calls.
Those staging-only operational rows, 348 Django permission rows present after
the deploy/authentication exercise, the test session, and the test user were
removed after observation. The final scrub census and receipt verifier then
returned to the required zero state.

Evidence screenshots:

- `docs/screenshots/2026-09-12-staging-integrated/ja-post-types-desktop.png`
- `docs/screenshots/2026-09-12-staging-integrated/ja-post-types-mobile-390x844.png`

## Refresh defects corrected during the run

The first guarded attempts failed closed and exposed six defects in the refresh
mechanism. The final candidate fixes them with migration-aware optional source
relations, migration-aware count and translation deltas, source census support
for pre-Stage-1 databases, a `public`-schema-only dump, replacement of the
candidate's default empty schema during restore, and the complete independent
census. The operations runbook now uses the tested administration-connection
helper for recovery checks; passing `-d postgres` after a PostgreSQL URL had
discarded the URL and attempted a local socket connection.

## Remaining release gate

This evidence does not convert U18 into a pass. The exact DeepSeek runtime
probe remains at 63.3% post-type exact-set accuracy, and the consumed unseen
cohort remains at 58.43%, below the frozen quality floors. Paid classification,
discovery, targeted extraction, and synthesis stay disabled, and the candidate
must not be promoted to production until the classification-quality decision
is resolved and the remaining U23 lane checks pass.
