# Frozen evaluation contract: Jev multilingual classification

## Plain-English Summary

Jev answers all current categorical classification questions, while a separate
future extractor owns entity names, handles, domains, exact quotations, and
structured job/event/personnel records. No extractor is run or scored here.
Its prospective input boundary is the original post, existing context,
candidate brand, catalog, and known account relationships—not extracted labels
or an oracle explanation of the correct promotion target.

The selected set has 120 real database posts: 12 deterministic natural-sample
posts and 8 category-focused posts for each of six database language buckets.
Before any Jev call, source review excludes three incorrectly labelled language
examples: `zh_cn_12` is Indonesian, `es_11` Portuguese, and `tr_11` an English
interjection plus English quote with no Turkish. The frozen evaluated set is
117 posts: JA 20, ZH-CN 19, KO 20, EN 20, ES 19, TR 19. Exclusions are not passes;
there is no replacement sampling after results arrive.

The second arm adds an existing English translation when available. It does
not erase the original or translate quote/parent context. Missing translations
mean no second call, not a failed raw-language classification. Already bilingual
posts and English quote context remain: this measures the real stored input,
not laboratory isolation of each language. Some stored translations are short
summaries rather than complete translations; do not silently repair them.

## Source and boundaries

- All-date production census: 279,892 posts, observed 2026-09-30 07:06:05 UTC.
  Effective language prefers `lang_detected`, falls back to provider `lang`.
  Next three language buckets after excluding Japanese, all Chinese variants,
  Korean and non-language codes: EN 197,854; ES 4,503; TR 2,226.
- Japanese bucket 21,887; explicit `zh-hans` 14,637; Korean 2,084. Generic `zh`
  has another 11,061 posts but is not assumed Simplified Chinese. Sampling uses
  explicit simplified-language codes. ZH-CN includes mixed-script `zh_cn_14`.
- Sampling eligibility: fetched before the census cutoff, nonempty source,
  source <=12,000 characters, and a stored non-sentinel brand association.
  These restrictions and intentionally balanced languages prevent interpreting
  pooled scores as whole-database prevalence/accuracy.
- Coverage selection uses existing label memberships ONLY to find candidates.
  Old classifications are not sent to Jev or used as reference answers. Some
  sampling hints prove wrong on source inspection; preserve that limitation.
- One deterministic target brand per post, not every candidate brand. Target
  discovery, brand catalog completeness, untracked-company discovery and entity
  extraction quality are outside this test. Ordinary-word collisions remain
  to test brand-association rejection. Current stored account relationships
  are not verified historical employment facts. Only one selected author has
  a known official relationship; this is not comprehensive affiliation testing.
- The fresh catalog snapshot has 49 brands and 1,804 product rows. Each request
  retains every brand, curated alias, known account and hashtag, plus only
  product names/repository IDs whose normalized text already occurs in the
  original post or saved context. Candidate matches are not identity proof.
  Selection does not inspect expected answers or English translations, and the
  catalog is identical between a post's two arms. The full production catalog
  is not sent indiscriminately; this is an explicit compact-input diagnostic,
  not a drop-in test of the unchanged production caller.
- No model switch, app edits, production writes, model-generated translation,
  X calls, 0731 calls, extractor calls, retries, or deployment.

## Reference answers and semantic scope

`reference_rows.json` contains all 120 source-reviewed decisions/notes, including
the three exclusions. Main-agent judgments were written before inference using
source-only review packets. They are **not independent human ground truth**.
The agent has reviewed prior development cases and knows their failure themes.
News/opinion overlap, showcase-versus-promotion, parent/quote inheritance,
corporate-versus-product attribution and stance intensity involve judgment.
Report disagreement, preserve examples, and do not claim that every mismatch
establishes a model error beyond dispute.

Definitions in `questions.py` retain the restored current taxonomy wording.
Advertising keeps its concise original definition rather than reinstating the
rejected long B.AI-specific paragraph. Multiple applicable labels and multiple
promoted parties remain possible. Promotion is a content/provider relationship,
not a new rule that unknown accounts must be civilians or official affiliations
alone establish advertising. No exact promoted-subject names are expected.

Thirty-eight independently answered fields per call:

- 14 post-type membership questions, including the exclusive `other` residual;
- 7 audience-topic membership questions;
- 5 product-label membership questions;
- 3 geopolitical-mode membership questions;
- 5 post-level untracked-promotion membership questions;
- outcome, sentiment, China stance and US stance as fixed-choice questions.

For categorical output compatibility, empty assessed product/topic/geo/promotion
memberships mean `none`. A `context_missing` outcome maps empty audience/geo
memberships to `unavailable`. No factual correction, quote generation or model
retry is performed. Raw independent answers remain the primary scored results;
report inconsistent memberships separately rather than silently clearing them.

## Scoring and stopping rules, fixed before inference

- Model `jev-1.13.0`, direct TypeSafe endpoint, sequential calls, no retries.
- One `raw` call per eligible case; one `translated` call per non-English case
  with a distinct existing translation. Alternate arm order by case index.
- Noul >=0.50 means present; Choice must select a maximum-probability option.
  A seven-option winner need not exceed 50%. Keep full distributions and the
  separate vendor confidence value; do not confuse those numbers.
- Invalid/missing fields count as incorrect and as operational defects. Keep
  valid sibling answers. No response/label repair or extra calls. HTTP/transport
  uncertainty stops submissions; unfinished cases remain explicitly untested.
- At most 240 physical calls, US$0.50 model-spend ceiling. Append start/raw
  response/accounting receipts before advancing. Save counts and conservative
  pre-call reservations; actual estimates use returned input tokens × $0.042/M.
- One pass, no tuning. Fixed references, prompts, cohort and runner are hashed
  before first inference, together with protected application/test files.
- Primary reports: per-language and per-family field agreement, exact complete
  post agreement, natural versus coverage results, binary positive precision /
  recall / F1, and per-label positive support. A missing positive label has
  unmeasured recall, never 100%. Sparse positives cannot establish reliability.
- Translation effect is computed ONLY on paired posts, by language. Do not
  compare an all-raw score to a translated-only subset as if cohorts matched.
- Report all semantic disagreements, malformed fields and consistency failures.
  Consistency checks include other-plus-specific type, classified without a
  type, missing context with target-specific memberships, general-plus-specific
  promotion, and directional national stance without nationalism.
- Confidence bins are descriptive development-set results, not calibrated
  production guarantees. No fallback threshold is selected from these scores.
- Predeclared sensitivity: omit all brand-specific fields for `es_14` (whether
  Meta enterprise news belongs to Meta Llama); omit China stance for `zh_cn_08`
  (anti versus constructive criticism); omit geo/national-stance fields for
  `tr_19` (national-origin product generalization boundary). Keep strict results
  as primary. No new exclusions after viewing outputs.
- This diagnostic has no production-go gate. Missing support, disagreement,
  model-output defects and single-reviewer uncertainty remain work to resolve
  before any migration decision. A complete run is not an approved switch.

## Provider facts checked 2026-09-30

[Models and pricing](https://docs.typesafe.ai/models),
[Choice](https://docs.typesafe.ai/primitives/choice), and
[Noul](https://docs.typesafe.ai/primitives/noul): $0.042/M input tokens, output
free; 64k request and 32k state-plus-longest-question limits; English strongest,
other languages including CJK require testing. Model is pinned, not an alias.

## Collection incidents

First cohort SQL attempt failed because `natural` is a SQL keyword. Its SQL and
error receipt remain intact; `cohort-candidates-v2.sql` renamed that local CTE.
The second attempt succeeded. A local parsing check also found that Python's
`splitlines()` splits literal Unicode separators within valid JSON; parsing
was corrected to PostgreSQL's LF record separator before selecting the cohort.
Four database invocations total (census, failed selection, successful selection,
catalog snapshot),
all read-only; these are not model retries.
