# U18 human ambiguity study

This study determines whether people who understand each source language can
apply taxonomy v3 consistently. It also creates the first human-reviewed
reference labels for the classifier work.

The existing U18 reference was candidate-blind, but it was produced by two
DeepSeek Flash reviews followed by a DeepSeek Pro audit. Scores against that
reference measure model agreement. They are useful development evidence, but
they are not human-grounded accuracy measurements.

## Study shape

The study contains 45 cases: 15 English, 15 Japanese, and 15 Simplified
Chinese. Each language has three deterministic five-case groups:

- stable disagreements where at least three of four preserved model runs agree
  with one another but disagree with the model-generated reference;
- conflicts where the preserved model runs disagree with one another; and
- controls where all four model runs and the reference agree.

The groups diagnose difficult boundaries; they do not measure natural
prevalence or rare-label recall. Selection uses exact `outcome` plus the full
post-type set. A private manifest records the source identities, selection
groups, input hashes, and artifact hashes.

Reviewer CSV files contain only an opaque case ID, source language, target
brand, source text, and stored quote/parent context. They omit source IDs,
selection groups, old labels, candidate labels, model names, source roles,
source hints, and discovery hints.

## Human roles

Two people independently label every case. Each reviewer must be fluent enough
in the case's source language to judge ordinary product language, tone, and
national framing. A reviewer slot may be split among EN, JA, and ZH-CN
specialists, but both slots must cover every case independently and the people
within a language must be distinct.

A third person resolves only the disagreements after both independent files
are locked. The adjudicator sees the source, stored context, and both human
answers. The adjudicator does not see any model answer. Reviewer and
adjudicator references are retained in the private result; the tracked report
records the method without publishing names.

## Answer columns

Use a vertical bar (`|`) between multiple values in the two list columns. Leave
the list cell empty for an empty list.

| Column | Allowed value |
| --- | --- |
| `outcome` | `classified` or `context_missing` |
| `post_types_pipe` | Zero or more canonical post-type keys |
| `product_labels_pipe` | Zero or more canonical product-label keys |
| `sentiment` | `positive`, `negative`, `neutral`, `mixed`, or empty when unknown |
| `china_nationalism` | `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed`, or empty when unknown |
| `us_nationalism` | The same values as `china_nationalism` |
| `job_discovery_relevant` | `true` or `false` |
| `personnel_discovery_relevant` | `true` or `false` |
| `confidence_1_to_5` | Integer from 1 through 5 |
| `taxonomy_issue` | `true` or `false` |
| `taxonomy_issue_code` | One code from the list below when `taxonomy_issue` is true |
| `ambiguity_notes` | Required when `taxonomy_issue` is true; otherwise optional |

Canonical post types are `releases_updates`, `hands_on_usage`,
`results_evaluations`, `questions_requests`, `advertising_marketing`, `events`,
`opportunities`, `job_listings`, `personnel_changes`, `opinions_reactions`,
`research_explanations`, `business_finance`, and `other`.

Canonical product labels are `bug`, `complaint`, `testimonial`,
`ideas_requests`, and `misinformation`.

Taxonomy issue codes are `release_vs_marketing`, `usage_vs_evaluation`,
`result_vs_opinion`, `research_vs_other`, `event_vs_opportunity`,
`job_vs_opportunity`, `personnel_vs_biography`, `context_missing`,
`brand_attribution`, `product_label`, `sentiment`, `nationalism`, and `other`.

## Labeling rules

Use the frozen taxonomy-v3 definitions in
[`classifier-prompts.md`](classifier-prompts.md). Apply every supported post
type and product label independently. `other` is exclusive.

Use `classified` when the supplied source or context says something
attributable to the target brand. A classified answer requires at least one
post type, a sentiment, and `none` or a substantive value on both nationalism
axes. Use `context_missing` only when the supplied material cannot support a
brand-specific classification; it requires empty post-type and product-label
lists.

An event requires attendance at a scheduled physical or live-online session.
An opportunity requires a bounded chance to take an action for a concrete
benefit. A job listing requires a concrete role and an actionable application
route. A personnel change requires a named person and a joining, leaving,
appointment, or explicit before-and-after employment transition. Past items
still receive their subject type.

Mark `taxonomy_issue=true` when the frozen definitions do not provide a stable
answer, even after choosing the best available classification. Use the closest
issue code and explain the unresolved boundary briefly. Do not research the
post, follow links, inspect media, or add missing conversation context.

## Commands

Build the private packets without network or database access:

```bash
.venv/bin/python -m scripts.u18_human_ambiguity_study build
```

This writes ignored files under
`.context/u18/human-ambiguity-study-v1/`. Give `reviewer-a.csv` and
`reviewer-b.csv` to the two independent reviewer slots. Keep
`selection-manifest.json` private from all reviewers.

After both reviewer files are complete, validate them and create the
disagreement-only packet:

```bash
.venv/bin/python -m scripts.u18_human_ambiguity_study prepare-adjudication
```

After a distinct human completes `adjudicator.csv`, validate and finalize the
human reference. Copy `human-attestation.template.json` to
`human-attestation.json` and complete every per-language reviewer and
adjudicator assignment. Each assignment records language proficiency,
independent work, absence of model assistance or model-answer exposure, and a
completion time. The two reviewer references and adjudicator reference must be
three distinct people within each language.

```bash
.venv/bin/python -m scripts.u18_human_ambiguity_study finalize
```

## Decision rule

The taxonomy reliability gate passes only when the two independent human
reviews match on exact `outcome` plus the full post-type set for at least 80%
of all 45 cases and at least 70% of each language's 15 cases. It also requires
that no taxonomy issue code recur in three or more distinct cases.

If the gate fails, revise the taxonomy wording or examples and run a focused
human re-review before any more provider evaluation. If it passes, compare the
adjudicated human answers with the preserved model runs and preregister one
small DeepSeek Pro reviewer pilot against this human reference. The 45 cases
remain consumed development evidence; a later release claim still requires a
new zero-overlap, human-reviewed cohort with adequate label support.

On a failed gate, the finalizer writes a non-gold
`human-adjudicated-diagnostic.json` and removes any stale `human-gold.json`.
Only a passing gate creates `human-gold.json`.
