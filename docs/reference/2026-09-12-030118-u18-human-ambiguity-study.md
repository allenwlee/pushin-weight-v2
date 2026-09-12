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

## Owner calibration after the independent-model audit

The owner reviewed the 16 highlighted differences from the Grok audit after
seeing both model-generated judgments. This is prompt-calibration evidence,
not a blinded human review or adjudication, and it cannot populate either
reviewer CSV or satisfy the gate below.

The review established these rules for the next prompt identity:

- `results_evaluations` needs source-visible product performance or quality
  evidence. Generic praise, endorsement, admiration, customer value, and the
  inaccessible contents of a link or media attachment do not qualify.
- Customer-facing price, affordability, electricity-cost, cloud-billing,
  subscription-cost, or usage-expense comments are not `business_finance`.
  That type is limited to the company, business, or investor perspective.
- `testimonial` includes praise, favorable experience, endorsement, and clear
  admiration of an achievement by the target brand. It can coexist with
  `advertising_marketing`, `hands_on_usage`, `results_evaluations`, or
  `opinions_reactions`.
- Every product label is strictly target-brand-specific. In case 16, Corpus is
  the praised company and Qwen is the event host, so the praise is not a Qwen
  testimonial. Separately, praise for a person alone does not transfer to an
  employer or product. When brand attribution independently identifies the
  person's product or work as the current target and the visible source praises
  that work, the praise may support a testimonial for that target.
- When the visible source supports a post type but the tone of unavailable
  media is unclear, omit `testimonial`. The current four-value sentiment
  contract records the absence of visible positive or negative valence as
  `neutral`; `null` remains reserved for context that prevents classification.
- A hackathon with organized participation and a bounded submission, prize,
  or winning track can be both `events` and `opportunities`, including when a
  post refers to it after completion.

The affected audit cases are `H7046A8A0689`, `HCC2BC2A1B6B`,
`H4E3B98376E5`, `H540717FEDF5`, `H87229E54527`, `HAF1D06FBEBA`, and
`HB4FB5810A09` for the results boundary; `H1E48CCEEB2F`, `HE6730DF39A2`,
`H3569508600E`, `H540717FEDF5`, `H42DCD9324F4`, `H92A808A114E`, and
`H7F29D6428BB` for testimonial coverage or target-brand scope; and
`HCCC266D762E` for unavailable-media sentiment. `HF3B55FD811B` remains a
known off-topic harvester edge case and does not motivate a classifier rule.

### Case-specific calibration record

These are owner-visible development constraints. They are retained so a later
candidate can be checked against the intended boundaries, but they are not
human gold and do not enter the blinded reviewer packets.

| # | Case | Owner constraint |
| ---: | --- | --- |
| 1 | `H7046A8A0689` | Exclude `results_evaluations`; the praise may support a testimonial for a separately attributed Meta/Muse target, but it is not a Qwen testimonial. |
| 2 | `HCC2BC2A1B6B` | Exclude `results_evaluations`; include `testimonial` for DeepSeek. |
| 3 | `H4E3B98376E5` | Exclude `results_evaluations`. |
| 4 | `H540717FEDF5` | Exclude `results_evaluations` and `business_finance`; customer cost/value comparisons are outside the investor/company type. |
| 5 | `HF3B55FD811B` | Treat as an off-topic harvester edge case; make no classifier change for it. |
| 6 | `H87229E54527` | Exclude `results_evaluations`; the unavailable YouTube video cannot supply evidence absent from the post. |
| 7 | `HAF1D06FBEBA` | Exclude `results_evaluations`. |
| 8 | `HB4FB5810A09` | Exclude `results_evaluations`; include `opinions_reactions`. |
| 9 | `H1E48CCEEB2F` | Include `testimonial` because the author is clearly impressed by the product experience. |
| 10 | `HE6730DF39A2` | Include `testimonial`. |
| 11 | `H3569508600E` | Include `testimonial`; the visible wording is positive about the target brand. |
| 12 | `H540717FEDF5` | Include `testimonial`. |
| 13 | `H42DCD9324F4` | Include `testimonial` and `advertising_marketing`; they are independent and may coexist. |
| 14 | `H92A808A114E` | Include `testimonial` because the author is impressed by MiniMax's achievement. |
| 15 | `HCCC266D762E` | Omit `testimonial`; visible valence is unclear, so map the owner's “unknown” to `neutral` under the current four-value runtime contract. |
| 16 | `H7F29D6428BB` | Omit Qwen `testimonial`; Corpus praise belongs only to a Corpus target. Classify the Qwen Cloud Hackathon as both `events` and `opportunities`. |

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
