# OpenAI and Anthropic collection size report

- Window: 2026-10-27T19:00:00+00:00 to 2026-10-28T01:00:00+00:00 (12:00–18:00 US Pacific on 2026-10-27).
- Test job `dd6a88f2-c98f-4efa-b33b-22af3a5208f2`; figures read from run `8bcc64e9-d291-44f3-9426-09e879c5fe85` (status success, one of 38 runs).
- Every measured figure comes from the test job's database records (R20). Per-day figures are estimates: the window figure divided by the window's share of a day's volume (R21).
- The baseline excludes RARE_EXTRA and the two special-events searches (SPECIALEVENTS1, SPECIALEVENTS2, live from deployed revision e5edf737).

## What this answers

How much more the production harvester would collect, pay and store per day if OpenAI and Anthropic became tracked brands. One 6-hour window ran production's 8 searches and the 10 new searches side by side; the baseline is what production's searches keep for the current brands.

## Headline figures

| Figure | Window (measured) | Per day (estimate) | How the estimate was made |
|---|---|---|---|
| Posts kept, baseline | 3,060 | 14,438 | estimate: window figure ÷ window share 0.2119 (production saved posts on the 8 production searches (posts with no discovery-lane source), 2026-10-27 Pacific) |
| Posts kept, added by OpenAI/Anthropic | 20,984 | 121,643 | estimate: production-search part ÷ production share 0.2119, new-search part ÷ pilot share 0.1724 |
| Posts kept with OpenAI/Anthropic | 24,044 | 136,081 | estimate: sum of the parts (kept-post-weighted mix of the production and pilot shares) |
| Search cost, production searches | $0.69–$1.27 | $3.28–$5.98 | estimate: window ÷ production share 0.2119 |
| Search cost, new searches | $5.60–$7.10 | $32.51–$41.21 | estimate: window ÷ pilot share 0.1724 |
| Classification cost (provider-reported) | $7.9121 | $44.2315 | estimate: each post's allocated cost ÷ the share of the search group that kept it |
| Database growth, production-equivalent tables | 497.2 MB | 2,813.9 MB | estimate: window figure ÷ window share 0.1767 (kept-post-weighted mix of the production and pilot shares) |

## Daily harvester needs with OpenAI and Anthropic added (R22)

| Need | Production now, per day | Added (estimate) | Projected per day | Note |
|---|---|---|---|---|
| Saved posts per day | 15,499 | 121,643 | 137,142 | current from production UTC day 2026-10-28 (96 of 96 runs): saved posts, the 8 searches' credits (low end), one 15-credit refresh per refreshed post, no quote calls; classification is the owner's $4/day reference; database growth from pg_database_size 2026-10-29 01:27:55Z (17,191,130,815) to 21:09:29Z (17,602,459,327), read-only |
| Search credits per day | 321,585 | 3,250,738–4,120,710 | 3,572,323–4,442,295 | added = new searches' window credits ÷ pilot share; production's 15-minute windows pay fewer per-request minimums than 5-minute slices |
| Engagement-refresh credits per day | 233,940 | 1,824,641 | 2,057,126 | projected = projected saved posts per day × 15 credits (one refresh per saved post) |
| Quote-tweet credits per day | 0 | 0 | 0 | scaled from production's current quote-tweet credits per saved post |
| Classification cost per day (USD) | $4.00 | $37.15 | $41.15 | added = provider-reported cost allocated to the added posts ÷ their search group's share |
| Database growth per day (bytes) | 501,297,782 | 2,515,363,868 | 3,016,661,650 | production-equivalent tables only, at the test's bytes per kept post |

## Harvester limits (R23)

Projected posts per day are compared with the per-run limits in config.yaml at the deployed production revision; a run happens every 15 minutes (96 per day).

| Limit | Value | Daily capacity | Projected | Factor | Exceeded? |
|---|---|---|---|---|---|
| `search.max_results` | 2,000 posts per search per run | — | 893 (ANT_1, per run) | 0.45× | no |
| `harvest.enrichment.claim_per_cycle` | 100 posts enriched per run | 9,600 | 137,142 | 14.29× | yes |
| `metrics_refresh.per_cycle_cap` | 200 posts refreshed per run | 19,200 | 137,142 | 7.14× | yes |
| `harvest.run_deadline_seconds` | 780 seconds per run | — | — | — | not measured |

Run time per 15-minute run is not measured by this test: the backfiller runs a different execution shape. A staging trial of run_cycle is needed to measure it.

## Each search (R14)

Fetched counts unique posts the search returned; kept counts posts it saved; a post found by two searches appears in both rows but once in the totals.

| Search | Group | Fetched | Kept | Dropped (by reason) | Pages | Requests | Retries | Credits | Slice outcomes |
|---|---|---|---|---|---|---|---|---|---|
| A | production | 93 | 78 | relevance_drop 10, unmatched_attribution 5 | 116 | 131 | 15 | 2,475–6,975 | complete 72 |
| ANT_1 | new | 14,597 | 11,260 | not_include 42, unmatched_attribution 3,295 | 833 | 988 | 155 | 220,035–266,535 | complete 72 |
| ANT_2 | new | 1,204 | 1,172 | unmatched_attribution 32 | 159 | 180 | 21 | 19,140–25,440 | complete 72 |
| ANT_3 | new | 1,020 | 906 | unmatched_attribution 114 | 152 | 178 | 26 | 16,380–24,180 | complete 72 |
| A_ANT | new | 11 | 8 | relevance_drop 3 | 82 | 91 | 9 | 1,245–3,945 | complete 72 |
| A_OAI | new | 5 | 0 | relevance_drop 5 | 76 | 87 | 11 | 1,155–4,455 | complete 72 |
| B1 | production | 1,544 | 1,283 | unmatched_attribution 261 | 179 | 213 | 34 | 24,240–34,440 | complete 72 |
| B2 | production | 167 | 36 | unmatched_attribution 131 | 135 | 159 | 24 | 3,585–10,785 | complete 72 |
| B3 | production | 86 | 22 | unmatched_attribution 64 | 113 | 139 | 26 | 2,370–10,170 | complete 72 |
| B_ANT | new | 1,322 | 1,322 | none | 169 | 187 | 18 | 20,910–26,310 | complete 72 |
| B_OAI | new | 1,285 | 1,216 | unmatched_attribution 69 | 168 | 188 | 20 | 20,355–26,355 | complete 72 |
| C1 | production | 169 | 128 | not_include 5, unmatched_attribution 36 | 136 | 148 | 12 | 3,615–7,215 | complete 72 |
| C2 | production | 36 | 9 | unmatched_attribution 27 | 102 | 114 | 12 | 1,620–5,220 | complete 72 |
| C3 | production | 85 | 72 | unmatched_attribution 13 | 120 | 136 | 16 | 2,355–7,155 | complete 72 |
| C4 | production | 1,874 | 1,617 | not_include 13, unmatched_attribution 244 | 203 | 255 | 52 | 29,190–44,790 | complete 72 |
| OAI_1 | new | 9,416 | 7,460 | unmatched_attribution 1,956 | 576 | 699 | 123 | 142,320–179,220 | complete 72 |
| OAI_2 | new | 5,960 | 4,493 | not_include 4, unmatched_attribution 1,463 | 407 | 479 | 72 | 90,480–112,080 | complete 72 |
| OAI_3 | new | 1,826 | 1,199 | not_include 103, unmatched_attribution 524 | 197 | 242 | 45 | 28,470–41,970 | complete 72 |
| **All searches** | | 31,801 | 24,044 | | 3,923 | 4,614 | 691 | 629,940–837,240 | |

## Growth (R15)

- Baseline-equivalent kept: 3,060 (kept by a production search with a tag from the current brands).
- Added kept posts: 20,984 (×6.86 of baseline); all kept with the new brands: 24,044 (×7.86).
- Net-new fetched: 27,901 posts the production searches never returned (×7.15 of the baseline's 3,900 fetched).
- Kept by a production search with no brand tag (should be 0): 0.

| How the added post was found | Posts | Ratio to baseline |
|---|---|---|
| Production search, kept only because of an OpenAI/Anthropic tag | 56 | 0.02 |
| Fetched only by the new searches | 20,922 | 6.84 |
| Fetched by a production search but kept only by a new search | 6 | 0.00 |

| Brand set of the added posts | Posts | Ratio to baseline |
|---|---|---|
| anthropic | 9,514 | 3.11 |
| anthropic+existing brand | 157 | 0.05 |
| anthropic+openai | 2,173 | 0.71 |
| anthropic+openai+existing brand | 97 | 0.03 |
| existing brand | 45 | 0.01 |
| openai | 8,918 | 2.91 |
| openai+existing brand | 80 | 0.03 |

## Search requests and credits (R16)

Each request with a returned body costs max(15, 15 × posts returned) credits. A request with no returned body (unknown outcome, transport error or lost body) counts as 0–300 credits, and an error response with a body (such as HTTP 520) as 0–15. 100,000 credits = $1.

| Group | Requests | Billed | No body | Error with body | Retries | Credits | USD |
|---|---|---|---|---|---|---|---|
| production | 1,295 | 1,104 | 191 | 0 | 191 | 69,450–126,750 | $0.69–$1.27 |
| new | 3,319 | 2,819 | 500 | 0 | 500 | 560,490–710,490 | $5.60–$7.10 |
| all | 4,614 | 3,923 | 691 | 0 | 691 | 629,940–837,240 | $6.30–$8.37 |

Requests used: 4,614 of the 7,000 limit (R10).

## Model cost (R17)

Reserved is what admission held back; provider-reported is what DeepInfra reported for finished requests; settled counts finished requests at reported cost and the rest at their reservation (R11).

| Stage | Requests | Member posts | Reserved | Provider-reported | Settled | Cost unknown |
|---|---|---|---|---|---|---|
| classification | 2,651 | 52,870 | $46.3753 | $4.2429 | $4.2429 | 0 |
| classification (post_targeted_extraction) | 933 | 933 | $0.5782 | $0.0580 | $0.0586 | 1 |
| translation (post_literal_language_detection) | 433 | 433 | $0.0664 | $0.0056 | $0.0056 | 0 |
| translation (post_literal_translation) | 55,840 | 55,840 | $37.8438 | $3.6056 | $3.6484 | 53 |
| **All** | 59,857 | | $84.8637 | $7.9121 | $7.9555 | |

Each request's cost is split evenly across its member posts, then summed by how the post was found:

| Posts | Count | Provider-reported | Settled |
|---|---|---|---|
| Kept on a production search with a tag from the current brands | 3,060 | $1.5008 | $1.5084 |
| Fetched only by the new searches | 20,922 | $6.3599 | $6.3936 |
| Fetched by a production search but kept only by a new search | 6 | $0.0197 | $0.0219 |
| Production search, kept only because of an OpenAI/Anthropic tag | 56 | $0.0316 | $0.0316 |

Collection-time staff relevance checks, reported separately from enrichment: checks 28, provider-reported $0.0006, responses {'returned': 28}.

## Database growth (R18)

- Backfill bookkeeping tables (collection_*, provider_batches, original_content_calls): 575.8 MB.
- Tables production would also grow: 497.2 MB.

| Table | Kind | Growth |
|---|---|---|
| original_content_calls | bookkeeping | 407.5 MB |
| posts | production_equivalent | 147.1 MB |
| posts_brands_classification_judgments | production_equivalent | 107.6 MB |
| collection_scope_runs | bookkeeping | 107.6 MB |
| account_profile_snapshots | production_equivalent | 52.1 MB |
| post_translation_texts | production_equivalent | 48.7 MB |
| post_translation_artifacts | production_equivalent | 36.4 MB |
| collection_observations | bookkeeping | 31.3 MB |
| posts_brands_classification_states | production_equivalent | 18.6 MB |
| collection_requests | bookkeeping | 15.3 MB |
| accounts | production_equivalent | 14.4 MB |
| posts_brands_signals | production_equivalent | 13.9 MB |
| post_enrichment_states | production_equivalent | 13.5 MB |
| collection_runs | bookkeeping | 10.6 MB |
| posts_brands_mentions | production_equivalent | 9.2 MB |
| posts_brands | production_equivalent | 8.0 MB |
| post_translation_chunks | production_equivalent | 7.6 MB |
| posts_brands_audience_topics | production_equivalent | 5.5 MB |
| x_account_details | production_equivalent | 3.2 MB |
| posts_brands_product_labels | production_equivalent | 2.3 MB |
| provider_batches | bookkeeping | 1.6 MB |
| untracked_brand_promotion_evidence | production_equivalent | 1.6 MB |
| collection_scope_request_uses | bookkeeping | 1.1 MB |
| people_brand_affiliation_evidence | production_equivalent | 1.1 MB |
| brand_discovery_candidates | production_equivalent | 1.0 MB |
| posts_untracked_brand_promotions | production_equivalent | 0.8 MB |
| people_brand_affiliations | production_equivalent | 0.7 MB |
| targeted_extraction_attempts | production_equivalent | 0.6 MB |
| collection_job_targets | bookkeeping | 0.6 MB |
| targeted_extraction_states | production_equivalent | 0.5 MB |
| posts_brands_geopolitical_modes | production_equivalent | 0.5 MB |
| people_accounts | production_equivalent | 0.3 MB |
| people_names | production_equivalent | 0.3 MB |
| people_name_evidence | production_equivalent | 0.3 MB |
| job_listings | production_equivalent | 0.2 MB |
| person_name_selections | production_equivalent | 0.2 MB |
| job_listing_evidence | production_equivalent | 0.1 MB |
| opportunities | production_equivalent | 0.1 MB |
| events | production_equivalent | 0.1 MB |
| staff_collection_work | production_equivalent | 0.1 MB |
| event_evidence | production_equivalent | 0.1 MB |
| people | production_equivalent | 0.1 MB |
| collection_jobs | bookkeeping | 0.1 MB |
| job_listing_locations | production_equivalent | 0.1 MB |
| people_media | production_equivalent | 0.1 MB |
| job_employment_type_assignments | production_equivalent | 0.1 MB |
| job_function_assignments | production_equivalent | 0.1 MB |
| job_seniority_assignments | production_equivalent | 0.1 MB |
| job_workplace_type_assignments | production_equivalent | 0.1 MB |
| collection_attempts | bookkeeping | 0.0 MB |
| search_queries | production_equivalent | 0.0 MB |

## Comparison with the pilot and production (R19)

**The baseline excludes RARE_EXTRA and the two special-events searches (SPECIALEVENTS1, SPECIALEVENTS2, live from deployed revision e5edf737).** Those searches have their own shared budget, so their search volume does not change with the new brands. Their posts that mention OpenAI or Anthropic would gain tracked tags; that added classification is not measured here.

- Production saved 3,223 posts in this window from its 8 searches; the test's production searches kept 3,116 (ratio 0.97).
- Left out of the production count: RARE_EXTRA 9, SPECIALEVENTS1 0, SPECIALEVENTS2 0.

| Window figure | Pilot estimate | Measured |
|---|---|---|
| Requests, production | 1,100 | 1,295 |
| Search cost, production | $0.73 | $0.69–$1.27 |
| Requests, new | 2,300 | 3,319 |
| Search cost, new | $3.97 | $5.60–$7.10 |
| Requests, total | 3,400 | 4,614 |
| Search cost, total | $4.70 | $6.30–$8.37 |
| Fetched, production | 4,100 | 3,900 |
| Fetched, new | 21,000 | 28,717 |
| Fetched, net_new | 20,200 | 27,901 |
| Fetched, total | 24,000 | 31,801 |
| Kept, production | 2,800 | 3,116 |
| Kept, new | 13,000 | 21,654 |
| Kept, total | 16,000 | 24,044 |

Pilot window estimates: plan Sizing Assumptions (pilot's three in-window slices, 2026-10-25 Pacific).

| Per-day figure | Pilot estimate | This test (estimate) |
|---|---|---|
| Baseline fetched | 23,300 | 18,401 |
| Net-new fetched | 114,500 | 161,821 |
| Added kept posts | 73,000 | 121,643 |
| Baseline search cost | $4.02 | $3.28–$5.98 |
| New searches' search cost | $22.86 | $32.51–$41.21 |

Pilot per-day estimates: docs/analysis/2026-10-27-221500-oai-anthropic-volume-pilot.md (2026-10-26 JST).

## Shares used for per-day estimates (R21)

- Production searches: 0.2119 — 3,223 of 15,207 saved posts (production saved posts on the 8 production searches (posts with no discovery-lane source), 2026-10-27 Pacific).
- New searches: 0.1724 (pilot slices: summaries.json sha256 7567078461d3, in-window slices [2, 3, 4] of [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]).
- Mixed figures: 0.1767 (kept-post-weighted mix of the production and pilot shares).

## Spend check (R24)

Settled spend: $7.96 (provider-reported $7.91, reserved $84.86, model requests 59,857)
Classified posts: 24,042
Provider-reported cost per classified post: $0.000329
R24 trigger: not met
Volume above doubling: settled spend passed $2 at or below $0.0008 per post. The run continues; the report shows it.

## Reconciliation and sources (R20)

- Kept posts from scope records: 24,044; posts with collection observations: 24,044; kept but not observed: 0; observed but not kept: 0.
- Classified posts that were not kept (should be 0, R13): 0.
- Historical search may omit posts the live harvest would see; figures are provider_filtered_not_exhaustive, as for the July backfill.

Inputs (sha256):

- xbackfiller: `5bb600a74f2ac2c0182ff4d568d7d84889b06fa90e509fbbc7dc62d0f9b3c0aa`
- production: `8e3ce38f4c918665b5a8262c4bd3341cfe9aedd240aaa102e87ed48a02b7685b`
- frozen_queries: `3d2c9c17114bd3de7a7070c60e35ad14eb54236fbf2efd048f657e804c994dec`
- limits_config: `ff02748de8e55f513a738b79288bd1a2c782a2b1c49eca70cb98d431ce49880c`
- pilot_share: `a1bff893257bd60056e33c11c7393ee8d908d4b0c6bac680e8e36ad9135e2b00`
- size_before: `9904b213bd6a77bf4e39f8e4be7d900e7928af6d2a55aba4d32aef41568764eb`
- production_daily: `8dd7103ee70bddee7cfdcef1a3459969309c122939f1acd21f074abc817155f3`
- xbackfiller_sql: `27068cc3a73fcca1378fc36f5cc742fbc94a3e8cca69865be1ba3a1cbb56ab6e`
- production_sql: `704fe17dfb895f3b7e01643dcffe75da2dbc086699d2819110074d1c6466ff50`

## Run notes (written after generation)

These notes were added by hand after `scripts/backfill_size_report.py` generated the sections above. The JSON file holds only the generated figures.

- **Enrichment did not reach zero deferred posts. The owner accepted this on 2026-10-30.**
  - 23,980 of 24,044 kept posts are fully classified and translated.
  - 64 posts (0.27%) were never classified, because their model replies failed canonical validation three times, which is each post's `max_attempts` limit. 7 of the 64 also lack a translation.
  - 60 classified posts did not finish targeted extraction.
  - One targeted-extraction request has an unknown outcome after a transport failure.
  - The final enrichment receipt deferred 123 posts (122 `model_attempt_allowance_exhausted`, 1 `provider_outcome_unknown`). Its status is `failed`, so `verify_window` did not return verified.
  - A re-run could not retry them, because `deferred_enrichment_work` keeps each post's attempt count across regrouped packets.
  - The spend check's "Classified posts: 24,042" counts posts with a completed classification request, including replies that later failed validation.
- **Classification retries are part of the cost.**
  - 1,636 of 2,651 classification requests had at least one member fail canonical validation, and those members were retried in new packets.
  - The 24,044 posts filled 52,870 classification slots, about 2.2 per post.
  - The provider-reported cost above includes those retries. Production's scheduled classifier keeps no per-call rows, so its failure rate cannot be compared here.
  - Both use the same 20-post packet (`_CLASSIFY_BASE_BATCH_SIZE`), so per-post cost carries over otherwise.
  - Translation is $3.61 of the window's $7.91.
- **The low end of the search-credit range is the production-shaped figure.**
  - 691 of the 4,614 requests were paid re-fetches. Each response arrived as one of the 38 runs ended, so its page did not commit and the next run fetched it again (`lost_responses` in `monitor/backfill_staging.py`).
  - Production's 15-minute cycle has no such boundary.
- **Shares (R21).** Production's harvest was on hold for part of 2026-10-27. That overstates the production window share (0.2119) by about 8%, so per-day estimates may be up to about 8% low.
- **Current classification cost.** "$4.00 per day" is the owner's reference figure. The DeepInfra account as a whole, across every workload, was billed about $18.54 per day around 2026-10-28.
- **Current database growth.** The 501,297,782 bytes per day comes from two read-only `pg_database_size` readings of production, 19.7 hours apart (2026-10-29 01:27:55Z and 21:09:29Z).
  - On 2026-10-29 the production database had a 30 GB disk with storage autoscaling off.
  - At the projected growth of about 3.0 GB per day, its free space would last about four days.
- **Not measured.**
  - Run time inside the 15-minute harvest run with the 10 new searches; a staging trial of `run_cycle` is needed.
  - Disk use beyond `pg_database_size`, such as WAL.
- **Lab-list searches.**
  - A_OAI kept 0 posts and A_ANT kept 8. In the test window the lists' accounts wrote little that named their own brand, and staff posts went through the relevance check.
  - The seeded copy of the OpenAI list has no @sama or @ChatGPTapp; private-list member lookups return nothing, so the X list itself could not be checked.
- **Owner decision on scope.** Replies stay in scope ("a reply about a brand is definitely signal we want to keep"), so `-filter:replies` is not an option for reducing volume.
