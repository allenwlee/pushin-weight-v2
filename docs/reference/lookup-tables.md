# Lookup tables and taxonomy

Version: v0.2.0-beta.1 (current write taxonomy `stage1-taxonomy-v4`)
Last updated: 2026-09-21 12:39:30 JST

The Django lookup tables constrain values that the classifier can write and
the dashboard can display. `core/models.py` defines the schema;
`core/management/commands/load_seed.py` owns brands, companies, and roles;
`core/management/commands/seed_i18n_labels.py` owns the canonical taxonomy
and its English, Simplified Chinese, and Japanese labels.

## Current classifier values

| Family | Current keys |
| --- | --- |
| Post types | `releases_updates`, `hands_on_usage`, `results_analysis`, `questions_requests`, `advertising_marketing`, `events`, `opportunities`, `job_listings`, `personnel_changes`, `opinions_reactions`, `research_explanations`, `business_finance`, `news_reporting`, `other` |
| Product labels | `bug`, `complaint`, `testimonial`, `ideas_requests`, `investigate_claim` |
| Audience Topics | `local_inference`, `cost_performance`, `model_distillation`, `evals_benchmarks`, `openness_license`, `agents_tools`, `api_developer_surface` |
| Geopolitical modes | `reporting`, `framework`, `nationalism` |
| Sentiment | `positive`, `negative`, `neutral`, `mixed` |
| China/US national stance | `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed` |
| Untracked Brand Promotions | `general`, `spam`, `scam`, `crypto`, `unauthorized` |

The transport-only values `unknown` and `unavailable` are used when evidence
is insufficient and are not ordinary label rows. `none` is exclusive within
each applicable multi-value family. `general` is exclusive when an untracked
promotion has no narrower signal; one promotional call to action is not spam
without repetition or substantial duplication.

## Database lookup models

- `PostTypeKey` / `PostTypeLabel`
- `ProductLabelKey` / `ProductLabelLabel`
- `AudienceTopicScheme` / `AudienceTopicConcept` / `AudienceTopicLabel`
- `SentimentKey` / `SentimentLabel`
- `GeopoliticalModeKey` / `GeopoliticalModeLabel`
- `NationalStanceKey` / `NationalStanceLabel`
- `NationalismKey` / `NationalismLabel` (historical compatibility family)
- `Role` / `RoleLabel`
- `UntrackedBrandPromotionKey` (post-level JSON key vocabulary)

Label tables use a composite primary key `(key, lang)`. Supported display
languages are `en`, `zh-cn`, and `ja`; source-language and historical values
remain readable where the compatibility contract requires them. Current
Audience Topics are enabled in the UI under activation revision
`u18a-owner-all-audience-topics-20260921-v1`.

## Brand and account registries

The seeded tracked catalog contains 21 enabled model/tool entries, including
the current `dots` entry. The `_unattributed` sentinel is used for discovery
of promotions outside the tracked catalog and is not a real brand. Brand
accounts and reviewed people/brand affiliations are separate relationships;
an account relationship is evidence about authorship, not by itself a content
classification.

## Compatibility and persistence

`core/classification_contract.py` accepts stage1 taxonomy v1, v2, v3, and v4
for reading. Current writes use v4 names. In particular, historical
`results_evaluations` maps to the current `results_analysis` concept without
rewriting the historical row, and historical `unsanctioned` data remains
readable separately from current `untracked_brand_promotions`.

## Adding a value

Add the key and labels in the Django seed command, create/verify the migration
when the model changes, update the classifier contract and prompt, and run
the focused taxonomy/parser tests. Never edit the retired `schema.dot`, its
PNG, or the legacy SQLite schema as a substitute for Django models and
migrations.

Last reviewed: 2026-09-21 12:39:30 JST — Reconciled lookup families, current
v4 keys, three display locales, 21 enabled tracked entries, and the current
Untracked Brand Promotions vocabulary against `core/models.py`, seed commands,
and classifier contract. Historical compatibility is described as read-only
vocabulary, not as a current write rule.
