---
module: harvest
date: 2026-11-21
problem_type: integration_issue
component: background_job
severity: high
symptoms:
  - Fresh posts have missing sentiment while the classifier reports successful publications.
  - Targeted extraction records report budget failures with zero input and output tokens.
root_cause: logic_error
resolution_type: code_fix
tags: [enrichment, classification, budgeting, translation, dashboard]
---

# Verify enrichment from each post through to the reader

A continuous worker can reserve its entire batch allowance, complete both classifier calls for every post and still starve everything that follows. In production, one hundred classifier pairs reserved room for six calls apiece. When each pair used two calls, four unused slots remained charged against the same batch. At 06:32 JST on November 21, all 1,596 targeted-extraction records since midnight were local budget refusals. The corresponding November 17 period had 813 successes out of 878 recorded attempts.

A **paid launch window** reserves an operator-authorized spending allowance in the database. The **continuous worker** holds short-lived capacity for calls and possible retries. Returning a continuous reservation when both roles settle releases capacity for the next role. Keep the durable launch ledger conservative. Pin the transition from a saturated classifier batch into a real follow-on extraction and a reader-requested translation. Count a refused dispatch as deferred. A transport failure after dispatch consumes a slot.

For sentiment, select posts by collection time, freeze their IDs and track each brand assignment. Read first dispatch, the first saved usable sentiment and post type, the current selected judgment, and the dashboard bucket. Count genuine missing-context decisions separately. During this incident, most overnight posts reached a provider quickly even while Meta's visible sentiment coverage remained poor. A second classifier pass on the same post can increment a worker counter without increasing coverage. A chart based on publication time can also display a post before it has been in the processing queue for a full measurement window.

Translation on demand changed both the classifier input and the language reader. Use pre-change evidence from November 16–17. November 18 included a provider outage and November 19 already used on-demand translation. Replay original-language text with the optional English text removed, including catalog names touching Chinese, Japanese and Korean characters, and near-matches such as `MiMoé`. Source language tags may be wrong. Preserve them as evidence, keep Chinese with unspecified script distinct from Simplified Chinese, and measure requested translation completeness only for real work. Existing failed or incomplete artifacts and attempts still merit inspection.

An older two-target translation packet can contain the same inherited source-script assumption twice. On explicit reader demand, check the script from the source and reuse an existing target only when its exact request, saved source and response still match. Keep the original provider charge on the paid record. A region-only upstream language tag supports Chinese on the chart and supplies no script result.

The repeatable checks live in `tests/test_enrichment_worker.py`, `tests/test_classified_product_releases.py`, `tests/test_compressed_classifier.py` and `tests/test_harvester_latest_n_health_check.py`. The November 21 repair section of the feed-enrichment plan records the baseline and live verification criteria.
