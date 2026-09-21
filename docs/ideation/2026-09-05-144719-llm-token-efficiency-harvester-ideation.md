---
title: LLM Token-Efficiency for Harvester and Headline Experiences
date: 2026-09-05
updated: 2026-09-08
focus: Reduce LLM tokens while preserving useful feed enrichment and fast brand pages
status: ideation
artifact_type: ranked_candidates
output_format: markdown
---

# LLM Token-Efficiency — Ideation

> **Compliance is out of scope.** It must not gate, reshape, rank, or judge
> these features. Evaluate ideas only by product value, UX, architecture,
> latency, reliability, and cost.

## Grounding

The companion report ([`docs/analysis/2026-09-03-llm-token-cost-and-scaling-report.md`](../analysis/2026-09-03-llm-token-cost-and-scaling-report.md)) models a 50-post loop at about 210.4k tokens on the conversation baseline, or about 129.4k using the report's latest-`origin/main` cadence/model assumptions. Enrichment is approximately linear per unique post (about 1,768 total tokens/post), while the headline graph is repeated per due, changed brand-window. The queue envelope serves at most 100 posts per cycle (50 current plus 50 carryover). Headline reads already come from PostgreSQL; they do not call an LLM on page load.

The checked-out branch still contains older headline values (`config.yaml` has
30-minute/hourly/6-hour/daily cadence and v4 editor/critic prompts), so the
latest-main numbers are revision-sensitive estimates, not claims about the
currently deployed service. Current code confirms 20-post translation and
classification batches, separate translator/classifier routes, and
fingerprint/work-slot headline machinery.

## Product model clarified

- **X posts are the raw data.**
- **PushinWeight builds the charts and the buy/sell/neutral ratings with pithy
  reasons.**
- **Posts are supporting evidence available on drill-down.**

PushinWeight must not be verbose or re-enumerate the data points that X already
provides. Its business is figuratively and literally building charts: visual,
succinct explanations of movement, magnitude, anomalies, comparisons,
importance, urgency, and likely action. The primary information hierarchy is:

1. chart or rating;
2. pithy reason explaining the signal;
3. underlying posts on drill-down as evidence.

The audience decision was expanded on 2026-09-07. PushinWeight serves two
audiences through the same chart-first experience:

- **Open-weight labs:** employees need actionable product feedback, bug
  reports, complaints, testimonials, ideas/requests, and misinformation review.
- **AI enthusiasts:** users want the latest product releases and features,
  practical hacks, and developments that move capabilities or usability
  forward. They also want an optional way to reduce emotional material.

Labs remain the enterprise audience, and enthusiasts are an explicit audience
for the app. Neither audience requires a verbose reading digest; email remains
low priority. Given the low volume for the tracked brands, every relevant post
is signal and should remain available even when it creates no product ticket.

The most valuable enrichment answers four questions without forcing the user to
read the feed: why the signal matters, how urgent it is, who should care, and
what action may be warranted. A user bookmark is also a strong intent signal:
someone who deliberately saved a post may benefit from organization,
synthesis, retrieval, and connection to later evidence.

## Feed reading model and page direction — 2026-09-07

**Selected:** AI synthesis (analyst commentary) is the default post-reading
experience. Remove the deterministic per-post summary proposal, including the
summary-to-commentary upgrade interaction. Do not introduce four competing
versions of a post: algorithmic summary, AI synthesis, literal translation,
and original. Original/source text and literal translation belong under
source drill-down, not alongside synthesis as equal primary feed modes.

This removes substitute per-post prose, not deterministic chart aggregation,
counts, ranking arithmetic, or output validation.

**Likely future page direction, not a finalized layout:**

| Surface | First read | Supporting evidence |
| --- | --- | --- |
| Homepage | Trend summary | User clicks to expand the synthesized feed. |
| Brand page | Product summary | User clicks to expand the brand's synthesized feed. |

Opening a page to read its summary must not automatically synthesize every
underlying post. Feed expansion is an explicit demand signal; continued reading
can trigger bounded look-ahead preparation. A summary-only session need not
create post-synthesis work, apart from an explicitly budgeted prewarm policy.
Preparation of the first-read trend/product summary is a separate demand and
freshness decision; this does not defer the primary summary until feed expansion.

The selected slim-section product summary remains a **later to-do, outside the
first plan**. The broader homepage/brand-page redesign is a likely future
direction, not newly authorized implementation scope. Preserve this reading
hierarchy when designing the enrichment boundary; do not make the first
enrichment work depend on shipping the page redesign.

## User summary tiles / slim sections — 2026-09-08

**Selected future UI to-do; outside the first enrichment plan.** Add the
reader-facing counterpart to the product-category summary, using the working
name `summary-user`. Reuse the compact, mobile-first, expandable slim-section
presentation selected in the product-summary tile exercise; do not revive the
larger tile layout that pushed the feed too far down the page.

These are content summaries inside the user-facing tiles/sections, not merely
a new navigation bar and not ten equally prominent top-level tiles. Keep the
lab-facing product summary separate: Bug, Complaint, Testimonial, Ideas &
requests, and Misinformation describe product work, while this surface groups
post types for enthusiast reading.

### First-read groups

| User-facing group | Underlying post types | Reader's question |
| --- | --- | --- |
| **Updates** | Releases & Updates; Events & Opportunities; Business & Finance | What is happening with these products and companies? |
| **Learn** | Hands-On Usage; Results and Evaluations; Research & Explanations | What can I try, how does it perform, and how does it work? |
| **Discuss** | Questions & Requests; Opinions & Reactions | What are people asking for and saying? |
| **More** — secondary disclosure | Advertising & Marketing; Other | Let me access the remaining types. |

### Reading and expansion behavior

- Show Updates, Learn, and Discuss as the primary compact summary sections,
  with a secondary More disclosure. The group is the entrance; the individual
  post types remain accessible underneath it.
- Use the selected data window and active brand/filter scope for counts.
  Preserve the concrete type breakdown in the first-read summary rather than
  showing only a vague group total. Illustrative copy, not measured data:
  **Learn: 18 hands-on posts · 7 evaluations · 2 explanations**.
- Reuse the product summary's compact header, period/last-updated treatment,
  and caret expansion pattern. Expanding a group reveals its constituent
  types and counts; selecting a type leads to its supporting synthesized
  posts. This is the user-reading equivalent of product-category drill-down,
  not a new bug/ticket detail page.
- Group totals count distinct posts. Multi-label posts can contribute to more
  than one type, so do not assume child counts sum to a unique group total.
- **All still includes every post.** More changes the prominence of controls,
  not collection, retention, or whether Advertising and Other posts appear in
  the all-posts feed.
- Reuse the presentation pattern, not product-ticket semantics by default.
  A product urgency/priority bar is not automatically a meaningful reader
  metric; no new reader-priority score or personal unread-tracking feature is
  selected by this note.
- Grouping and count aggregation are deterministic mappings over post types:
  no extra classifier dimension, merged type definitions, or LLM call is
  needed for them. This aggregate summary does not reintroduce the rejected
  deterministic per-post summary or replace AI synthesis as the post-reading
  experience.
- Preserve the summary-first / on-demand synthesized-feed direction. Reading
  a group summary alone must not synthesize every supporting post; feed
  drill-down follows the shared demand, cache, and bounded preparation policy.

This addition does not implement tiles, change homepage/brand-page placement,
or make the initial enrichment work depend on the future page redesign.

## Taxonomy decisions — updated 2026-09-08

These decisions supersede the earlier exploratory taxonomy and routing
proposals in this document. They record the product direction; classifier,
schema, and UI implementation have not been changed by this documentation
update.

### Selected direction

- Reuse existing `post_type` keys wherever possible, remapping display names
  for the compatible renames. Apply the selected feedback redistribution and
  Events & Opportunities scope expansion described below; add **Opinions &
  Reactions**, **Research & Explanations**, and the already-planned **Business &
  Finance** (`business_finance`). Keep **Other** as the fallback.
- The Updates / Learn / Discuss / More groups above are a presentation layer,
  not replacements for these individual post types.
- Remove the **discourse** classification dimension. A replacement posture or
  sincerity taxonomy has not been selected.
- Add a separate **product** label group: **Bug, Complaint, Testimonial,
  Ideas & requests, Misinformation**.
- Retain every relevant collected post. Product labels help identify work for a
  lab; posts without a product label still contribute to discovery, charts, and
  trends. Event announcements remain first-class.
- Keep the classifier compact. The earlier broad work-signal/owner/action
  schema, fixed bug-first precedence ladder, and proposed six-category
  enthusiast replacement are not the chosen direction.
- No decision here removes or changes sentiment or other existing dimensions
  beyond discourse.

### Final reader-facing post types and remapping

These September 8 decisions supersede the earlier seven-type display list.
They record intended behavior; existing classifier, schema, and UI have not
been migrated by this documentation update.

| Existing key / status | Final display label | Treatment |
| --- | --- | --- |
| `buzz_releases` | Releases & Updates | Display rename; preserve release/update boundaries. |
| `hands_on_usage` | Hands-On Usage | Retain. |
| `performance_comparisons` | Results and Evaluations | Reuse key/display remap; absorb experience assessments previously in Feedback & Questions. |
| `feedback_questions` | Questions & Requests | Reuse key; remove experience-only/evaluative feedback from this bucket. |
| `advertising_marketing` | Advertising & Marketing | Retain. |
| `event_announcement` | Events & Opportunities | Reuse key; expand beyond organized events to opportunities. |
| New category; key to be finalized in planning | Opinions & Reactions | Views, predictions, anticipation, and reactions not principally another defined type. |
| New category; key to be finalized in planning | Research & Explanations | Technical mechanisms, architecture, research interpretation, and conceptual teaching. |
| `business_finance` — already planned | Business & Finance | Preserve the existing definition below. |
| Fallback; persistence representation not selected here | Other | Residual material; distinguish missing context or pending classification from a confident Other judgment. |

**Feedback redistribution is not a display-only rename.** Reports and
assessments of actual experience, outcomes, or specific product problems move
to Results and Evaluations. Questions & Requests covers genuine questions,
requests for help or a product change, and contextual support answers. Generic
views or reactions without a specific outcome/assessment belong in Opinions &
Reactions. Legitimate overlaps remain possible; a post that reports a failure
and asks for help can qualify for both Results and Questions.

**Events & Opportunities is the selected name and expanded scope.** Include
organized occasions plus concrete jobs, grants, bounties, and collaboration
opportunities. The historical event-only estimate of roughly 0.4% is not an
estimate for the expanded category; opportunities still require an audit.
The event repair below still prevents ordinary releases/pricing changes from
being mislabeled as organized events, but its occasion requirement applies to
the events branch, not to all opportunities.

Post types describe content, not whether it is intelligent, true, defensible,
useful, sincere, or urgent. Those are separate grading/measurement questions;
unsupported comparisons remain comparisons. Product labels remain independent:
a reported malfunction can be Results and Evaluations plus Bug/Complaint,
while a help request can be Questions & Requests plus Bug. A workaround can
remain Hands-On Usage plus Bug when it addresses an actual malfunction.

The audits below retain their original names and judgments as historical
evidence. Carry the corrective boundaries forward subject to the selected
feedback split and opportunity expansion above; these notes are not a
production relabeling or backfill authorization.

### Event Announcement classification repair — 2026-09-08

**Selected fix to carry into implementation planning; not implemented here.**
Keep `event_announcement` in the existing taxonomy, but stop treating every
announcement, release, or availability change as an organized event.

#### Evidence: 100-post event-label audit

Read-only production snapshot: **2026-09-08 07:10:50 UTC**. Population:
**2,420 distinct posts** dated August 31 through September 8 in Asia/Tokyo,
with September 8 partial. Sample: **100 posts from 95 accounts**, selected by
ascending `md5(tweet_id || 'event-audit-20260908-v1')`, with tweet ID as the
tie-breaker; a post carrying the event label for multiple brands counts once.

The audit read originals, available translations, stored quotes and available
reply parents; it did not classify AI commentary in place of source text or
inspect every image/external page. These are single-agent judgments about
category fit, not independently validated gold labels or verified event facts.

| Finding | Posts out of 100 |
| --- | ---: |
| Clear upcoming organized-event announcement/invitation | 1 |
| Reporting on an ongoing or completed organized event | 4 |
| Identifiable event connection only through quote/parent context | 2 |
| Ambiguous with available context | 2 |
| No identifiable organized event | 91 |

Thus **7/100 had an identifiable event connection**, a deliberately broader
measure than strict announcement accuracy. The 91 non-events comprised 31
release/update/availability posts, 14 promotions, 13 technical/usage/evaluation
posts, 10 corporate/financial posts, 9 roundups, 8 upcoming-release teasers,
4 reactions/requests, and 2 unrelated incident alerts. These audit groupings
are explanatory counts, not a replacement taxonomy.

Examples with full URLs:

- Clear event: PyTorch Conference, October 20-21 in San Jose, with sessions,
  speakers and registration:
  <https://twitter.com/PyTorch/status/2095935008351367293>.
- Retrospective event reporting: Zhipu's August 31 results briefing:
  <https://twitter.com/ruima/status/2094557531108729163>.
- Parent-dependent event recap: Huawei at LEAP in Riyadh:
  <https://twitter.com/ssict/status/2096897772590866937>;
  parent <https://twitter.com/ssict/status/2096897764248461648>.
- Not an organized event: GLM quantized-model availability:
  <https://twitter.com/HaihaoShen/status/2094653028918018173>.
- Not an organized event: Qwen API price reductions:
  <https://twitter.com/Chinazhidx/status/2094663836578271262>.
- Not an organized event: DeepSeek funding/IPO reporting:
  <https://twitter.com/chrisbcore/status/2094826619680481448>.

#### Prompt conflict to remove

In `x_monitor/attribution.py`, the category definition describes an official
event/community meetup, while rule 13 explicitly routes one-line
"generally available / launched / shipped" posts to `event_announcement`
and says not to use `buzz_releases`. Worked example A repeats the error by
labeling Kimi availability in GitHub Copilot as an event. Both the checked-out
file and the locally available `origin/main` version contained this conflict
during the audit; this is not a per-call production prompt trace.

#### Required correction and verification

- Reserve the event boundary for identifiable organized occasions: conferences,
  meetups, webinars, talks, hackathons, workshops, or actual launch
  presentations. A software release date or pricing start time alone is not
  evidence of an organized event.
- Route model/feature/weights releases, integrations, availability changes and
  pricing updates to `buzz_releases` when that is the substantive content.
  Third-party reporting does not turn a release into an event. Promotional
  pitches may independently qualify as `advertising_marketing`.
- Remove/replace conflicting rule 13 **and** worked example A; reconcile other
  prompt variants and examples with one shared definition. Do not add a
  separate event-only classifier or an extra recurring LLM call for this fix.
- Use available parent/quote context when it actually establishes the event;
  do not infer an event from vague "see you there" replies when that context
  is missing. Planning must explicitly settle whether event recaps remain in
  this bucket and how incidental event references are handled; the audit did
  not approve new subcategories.
- Keep brand relevance separate from event identity: a real conference can
  still have an incorrect brand match. The PyTorch sample was tagged `yi`
  despite the visible match being a speaker name; the Abuja climate workshop
  was tagged `upstage` without evident AI-brand relevance. Record these as
  separate attribution concerns, not proof the content is not an event.
- Verification must cover actual event invitations, launch presentations,
  ordinary releases/GA/integrations/pricing, promotions, recaps, and
  missing-context replies. Pin the canonical prompt used by the production
  classifier call chain, and evaluate a fresh held-out sample after changes.
  Prompt-string tests alone do not establish improved model accuracy.
- Do not optimize toward a desired unclassified percentage. Most false event
  labels fit another content type; usefulness and reader benefit remain
  separate grading questions. Historical relabeling/backfill requires its
  own bounded scope and authorization.

This documentation update does not change classifier code, stored labels,
harvesting, product labels, sentiment, nationalism, or production services.

### Audit fixes for the other five post types — 2026-09-08

**Selected fixes to carry into implementation planning; not implemented here.**
Keep the existing `business_finance` key and **Business & Finance** display
label and definition unchanged. This audit adds evidence and corrective
requirements; it does not add, rename, or duplicate a category.

#### Evidence: five-type source-content audit

Read-only production snapshots: **2026-09-08 07:28:06–07:30:01 UTC**.
The publication-date window was August 31 through September 8 in Asia/Tokyo,
with September 8 partial. We sampled **100 distinct posts per stored type**
(500 total), regardless of brand count; the independent samples happened not
to overlap. Selection order was `md5(tweet_id || post_type_key ||
'five-types-audit-20260908-v1')`, with tweet ID as the tie-breaker. Populations
were Buzz & Releases 2,024, Hands-On Usage 9,087, Performance Comparisons
7,043, Feedback & Questions 4,998, and Advertising & Marketing 2,642.

Judgments were single-agent semantic reviews of originals, available
translations, parents, quotes, and link-card metadata. We did not independently
inspect every media or external page, and did not verify truth. These are not
gold labels or whole-database accuracy estimates; usefulness/evidence quality
and brand attribution are separate questions. Legitimate multiple types remain
allowed.

| Stored type | Clear fit | Mismatch | Uncertain |
| --- | ---: | ---: | ---: |
| Buzz & Releases | 48 | 47 | 5 |
| Hands-On Usage | 82 | 12 | 6 |
| Performance Comparisons | 76 | 23 | 1 |
| Feedback & Questions | 61 | 34 | 5 |
| Advertising & Marketing | 90 | 4 | 6 |

#### Required corrective boundaries

- **Buzz & Releases:** Require a substantive concrete release, feature,
  weights, integration, availability, or pricing change. Bare excitement,
  personal anticipation, and procurement/funding stories do not qualify.
  Specific reported or rumored releases may count without endorsing their
  truth; an author's personal wish or prediction alone does not. Third-party
  reporting is valid. Corporate/financial material routes to the already
  planned **Business & Finance** category where apt; do not create another
  category. Examples: fundraising reported as a release
  (<https://twitter.com/JamesTakesOnAI/status/2097213942632493560>) and bare
  excitement (<https://twitter.com/Hawthorn_thinks/status/2096598326988959796>).
- **Hands-On Usage:** Require actual use, a demo or artifact, observed
  experience, or a concrete workflow/setup/tutorial. Future intent, bare
  recommendation, and praise/news roundups are insufficient; missing context
  is uncertain. Shared chatbot outputs can legitimately count regardless of
  low usefulness. Example of future intent:
  <https://twitter.com/Devon8zzh/status/2097141625474646096>.
- **Performance Comparisons:** Require a substantive model/product/harness
  evaluation, benchmark, ranking, or comparison; unsupported subjective
  rankings still count as comparisons, with grade quality separately. Do not
  route stock returns, usage popularity, architecture history, or a post that
  merely mentions a benchmark, ranking, latency, or model name. Examples:
  stock returns (<https://twitter.com/StockTicker24/status/2094305535852233123>)
  and usage popularity
  (<https://twitter.com/SentedgeAI/status/2094832746208051510>).
- **Feedback & Questions:** Require an actual product-related question,
  request, complaint/experience, or targeted support answer/correction. Do not
  count rhetorical article headings, industry commentary, standalone tutorials,
  or unrelated questions asked *to* a chatbot. Examples: a question-shaped
  tutorial (<https://twitter.com/woshipm/status/2097210758723481813>) and a
  chatbot mathematical question
  (<https://twitter.com/sirxterminator/status/2095949745994829917>).
- **Advertising & Marketing:** Require observable promotion, acquisition
  pitch, CTA, credits, discount, services, or product showcase. Do not infer
  marketing solely from free/open-source/resource links. Useful genuine
  promotional posts still qualify; borderline review-versus-promotion remains
  uncertain. Example of a standalone tutorial mislabel:
  <https://twitter.com/CryptooGG_/status/2096991485728350350>.

Keep brand-match correctness separate from type correctness: four explicit
unrelated product ads were wrongly matched to MiniMax but were correctly typed
as ads, and sports player Ernie Clement was matched to ERNIE in a mislabeled
betting-picks post. Do not broaden this work into brand-filter implementation.

#### Prompt reconciliation and verification

The checked-out `x_monitor/attribution.py` shows the likely source of the
observed errors (repository evidence, not a per-call deployed prompt trace):
rule 14 routes any mention of TTFT/latency/benchmark/ranking to comparisons;
rule 15 routes analytical governance and similar material into comparisons or
feedback. Worked example B maps ranking/price updates to hands-on, C maps
Alibaba corporate valuation to comparisons, E invents implicit questions for
analytical posts, and F maps rhetorical questions to feedback. Reconcile the
base definitions, rules, and examples—including the existing event repair's
rule 13/example A—in one shared canonical definition across prompt variants.

Do not add extra per-type LLM calls. Regression requirements are positive,
negative, and context-missing boundary fixtures; verification of the actual
production classifier call-chain prompt/config wiring; and a held-out fresh
post sample after prompt edits. Prompt-string tests alone are insufficient.
Do not optimize toward a target unclassified percentage. Historical
relabeling/backfill requires separate scoped approval. Preserve existing
sentiment, nationalism, and product labels, and grade usefulness/defensibility
separately from type and brand attribution.

### Product labels and the request/idea decision

| Product label | Intended meaning |
| --- | --- |
| Bug | A reported concrete malfunction, failure, or regression. |
| Complaint | Dissatisfaction with the product or experience. |
| Testimonial | Praise or endorsement of the product; a concrete positive experience provides stronger evidence. |
| Ideas & requests | A desired capability, improvement, unmet need, or proposed product idea. |
| Misinformation | A potentially false or misleading claim about the brand or product that warrants review; confirmation requires evidence. |

Keep product requests and product ideas together under **Ideas & requests**
(proposed key: `product_request`). They overlap too much to justify another
classifier distinction now:

- Request: "Please add batch inference — I am processing 10,000 documents."
- Idea: "Batch inference could be useful for overnight document processing."

Both express possible product improvements. The request supplies more evidence
of an immediate need, but wording alone does not determine importance. A useful
unsolicited idea can outrank an explicit request. Later priority evaluation
should consider the stated problem, expected benefit, urgency, and corroborating
demand; it does not need to reconstruct a request-versus-idea label.

Working behavior to validate during planning: allow an empty product-label set
when none applies, and multiple labels when each is supported. A bug report may
also contain a feature request. Sarcasm or disagreement alone does not establish
misinformation, and an investment thesis is not a product testimonial.

### Business & Finance definition and reference post

Reference post, full URL:
<https://x.com/zhaoge168/status/2096767995133702183>

The post is a premarket briefing connecting news to potential stock
beneficiaries. Its AI-related items include reports about DeepSeek infrastructure
spending and AI labs' commercial distribution plans. These are descriptions of
what the post reports, not independent verification of its underlying claims.
The category must cover suppliers, partners, and parent companies as well as a
lab's own business or shares.

Use **Business & Finance** when the substantive point concerns a company's
business, financial position, or investment prospects:

- stock analysis, valuations, earnings, and investment theses;
- funding, IPOs, acquisitions, and corporate ownership;
- revenue, monetization, and commercial strategy;
- financial implications for suppliers, partners, and parent companies.

Boundary examples:

- "Cheaper inference makes my coding workflow affordable" stays in the existing
  usage/comparison categories.
- "Cheaper inference could compress the company's margins" belongs in
  **Business & Finance**.

The current classifier prompt already discusses investment commentary but has
no dedicated post type for it. This addition fills that gap. Bullishness about
a stock should not automatically become praise of the model or a Testimonial.

### Emotion, sincerity, and priority: requirement retained, design open

Enthusiasts want an optional way to reduce emotional material, while labs need
to recognize posts worth attention even when their wording is sarcastic,
hostile, or insincere. Literal sincerity is therefore not a sufficient measure:

- a sarcastic post can contain a concrete, important bug report;
- an upset account with substantial reach can create a significant reputation
  signal regardless of whether direct engagement would be useful;
- a detailed report from a small account can have substantial product value.

Attention priority and whether/how to respond are different judgments. Reach
and engagement may inform attention, but neither proves sincerity, factual
accuracy, or product value.

The proposed distinction between substantive information, information mixed
with reaction, and reaction alone remains an option to evaluate. It has not
been adopted as a new classifier output, and the discarded posture taxonomy
must not be treated as settled. The future measurement criteria and evaluation
examples still need definition; missing reply context must be represented as
uncertainty.

For enthusiasts, "what moves the ball forward" remains a discovery/ranking
objective across post types: new capabilities, practical techniques, lower
cost or hardware requirements, better reliability, wider access, or evidence
that changes understanding. It is not an additional post type in this decision.

## Competitive product notes

### Vibe Coding Trends

- Full URL: <https://vibecodingtrends.com/>
- Positive: its singular focus on vibe coding demonstrates the value of a
  tightly defined vertical.
- Reject: users should not have to read themes and paragraphs to determine why
  a theme matters. Brand-mention counts and movement should be visual.
- Reject: too many categories and too much prose make the experience feel like
  another verbose feed.
- Lesson: preserve the narrow market focus, but replace thematic enumeration
  with chart-like signals, ratings, and pithy explanations.

### HerculeRadar

- Full URL:
  <https://www.reddit.com/r/indiehackers/comments/1w5d1ah/i_built_an_aipowered_social_listening_tool_for/>
- Strongest benchmark; rated 10/10 for ideas worth adapting.
- It makes a post actionable by explaining why it matters, how urgent it is,
  and what the user should do about it.
- Adapt its importance, urgency, recipient, and action framing into
  PushinWeight's signal and evidence views.

#### Dossiers PushinWeight should address

1. **Dossier No. 01 - Customer support:** Answer the people who never opened a
   ticket.
2. **Dossier No. 02 - Product feedback:** Your roadmap is already being written
   in public.
3. **Dossier No. 03 - Testimonials:** People are praising you. You just have not
   seen it.
4. **Dossier No. 04 - Social selling:** Be in the thread where someone asks for
   a recommendation.
5. **Dossier No. 05 - Competitor monitoring:** Know what your competitors'
   users complain about.
6. **Dossier No. 06 - PR monitoring:** Watch a launch land in real time.
7. **Dossier No. 07 - Reputation management:** Correct the false claim while it
   is still small.
8. **Dossier No. 08 - Agencies:** Every client, one inbox, no tab juggling.
9. **Dossier No. 09 - Brand monitoring:** Know what your name means to people
   who never contact you.
10. **Dossier No. 10 - Launches:** Read the room while the room is still
    talking.

“Open the file” maps cleanly to PushinWeight's information hierarchy: the chart
or rating exposes the signal, a pithy reason explains it, and opening the signal
reveals the supporting posts and suggested response.

These dossiers should become underlying jobs-to-be-done and routing signals,
not ten new top-level feed categories. A single post may support several
workflows. The following broader metadata proposal was exploratory and is
superseded as a classifier-output requirement by the 2026-09-07 decisions above.
It remains context for possible future experiences, not a mandate to ask the
classifier for all of these fields:

- affected brand and competitor;
- signal type and business use case;
- importance and urgency;
- responsible team or role;
- recommended next action;
- confidence and supporting evidence.

The selected post-type and product labels can support dashboard views, saved
evidence, and brand-page charts. Further routing or priority metadata remains
future design work; avoid duplicating enrichment or forcing every user to
navigate an oversized taxonomy. Related dossiers should
share primitives: PR monitoring and launches share launch-reaction signals;
brand and reputation monitoring share claim and perception signals; customer
support and product feedback share issue and request signals.

### FeedRecap

- Full URL: <https://www.feedrecap.com/>
- Reject: it largely regurgitates X in another format and adds too little
  analytical value.
- Lesson: summarization alone is not intelligence; PushinWeight must expose
  change, significance, and action.

### VibeUsers

- Full URL: <https://vibeusers.io/>
- The product is shut down and is not a live benchmark.

### Digest

- Full URL: <https://usedigest.com/>
- Reject for the core product: users do not need another email digest.

### Readless

- Full URL: <https://www.readless.app/>
- Reject for the core product: it is another email-oriented reading product.

### Tweetsmash

- Full URL: <https://www.tweetsmash.com/>
- Positive: a bookmark is explicit evidence that the user considers a post
  important.
- Idea to retain: let users organize and summarize bookmarked evidence instead
  of sending undifferentiated summaries of every followed account.
- Potential PushinWeight adaptation: saved posts become a personal evidence
  workspace connected to brands, chart events, ratings, and later developments.

### ListenToX

- Full URL: <https://listentox.com/>
- Interesting delivery experiment, but outside PushinWeight's current
  enterprise-dashboard wheelhouse.

### Catch Up Feed

- Full URL: <https://catchupfeed.io/>
- Bookmark this product for design ideas.
- Like HerculeRadar, it explains why a post is important and implies what action
  should follow, although its action framing is less direct.
- Adapt the concise significance treatment while making urgency and action more
  explicit.

### PulseDigest

- Full URL: <https://maazsiddiqui.com/aiAutomation/pulse-digest>
- Reject for the core product: it is another email digest aimed at personal
  consumption.
- Product distinction: email summaries serve consumers reading X for personal
  benefit; dashboards serve employees using X to perform work.

### Twigest

- Full URL: <https://twigest.com/>
- The public page appeared to have missing HTML/CSS, and the registered
  experience remained empty.
- It provides no useful live benchmark in its observed state.

## Competitive synthesis

The useful benchmark set is intentionally small:

1. **HerculeRadar** for importance, urgency, and recommended action.
2. **Catch Up Feed** for concise explanations of why evidence matters.
3. **Tweetsmash** for treating deliberate bookmarks as high-intent evidence.
4. **Vibe Coding Trends** only for the benefit of narrow vertical focus.

The rejected cluster shares the wrong product model: resurface many posts or
send a reading digest. PushinWeight should instead convert social activity into
visual explanatory intelligence. Its closest metaphor is a market terminal,
where posts are measurements, charts expose the signal, ratings summarize the
implication, and drill-down evidence lets the user verify the conclusion.

## Candidate ideas and critique

### 1. Demand-driven AI synthesis; keep universal translation

**Selected direction:** save tokens by changing when synthesis is generated,
not by replacing the desired reading experience with templated prose.
Lazy-loading cards alone is insufficient: the current feed is paginated but
selects completed enrichment, and the translator generates translations and
commentary together. The change must defer provider work itself.

#### Shared enrichment boundary and locale parity

- Retain collection and compact classification across all relevant posts so
  charts, counts, and filters do not depend on whether someone opened the feed.
  Synthesis-pending posts must remain discoverable, not silently disappear.
- Keep eager literal translations where needed under the existing policy.
  EN, ZH-CN, and JA have equal support; JA must not become a secondary,
  later-on-request exception to ZH-CN.
- For a post selected for synthesis, prepare and persist the required localized
  synthesis for EN, ZH-CN, and JA under the same policy. The selective-work unit
  is the post, not a viewer or a locale toggle.
- Refactor batch and one-off async enrichment around shared preparation,
  prompt-building, validation, retry, and persistence components. Harvester
  batches and synthesis-only jobs reuse these modules; a synthesis-only request
  must not redo completed literal translations or classifications.
- Keep model routing independent by role: synthesis/judgment can use a different
  model from literal translation or compact classification. This is separation
  of responsibilities, not a selection of particular providers.

#### Demand and preparation policy

1. **Keep only a small ready reserve.** Consider bounded first-screen prewarming
   for the default feed and recently active or pinned brand feeds, with one
   shared budget. Do not prepare every brand/filter combination after each
   harvest. With the likely summary-first layout, prewarming should depend on
   expected feed-opening demand, not page visits alone.
2. **On feed expansion, reuse or request the first slice.** Return persisted
   synthesis immediately when available. Coalesce missing work with existing
   in-flight jobs; explicit cold demand outranks speculative preparation.
3. **Prepare ahead while the user reads.** Request a bounded next slice before
   its cards enter the viewport. Tune look-ahead and small-batch size using
   measured queue time, p95 synthesis completion time, and reading/scroll speed.
   Do not wait for each card to become visible before starting its LLM call.
4. **Stop obsolete speculation.** Pause look-ahead when the feed is collapsed
   or the tab is hidden, debounce rapid filter changes, and discard queued work
   that no remaining requester needs before dispatch. Already-started calls
   may still incur cost; track that waste.
5. **Handle cold misses honestly.** A cold filter or fast jump may require a
   loading state for the requested slice. Preserve matching cached content
   where appropriate, stable ordering, and an explicit pending state; do not
   substitute algorithmic commentary or falsely present an incomplete feed as
   complete. Instant access everywhere cannot be promised without more prewarm.

Persist and share synthesis by post/content-context version, synthesis
prompt/model version, and required locale outputs. Neither user identity nor
brand/filter navigation should multiply identical work. A new harvest,
engagement-only update, or another viewer does not invalidate unchanged
synthesis; meaningful source/context changes can.

Any background synthesis for headline evidence or other non-feed consumers
must be an explicit, budgeted demand source, not a hidden eager-all path.

#### Fifteen-minute collection versus asynchronous reading

The 15-minute interval governs collection, not synthesis expiration or worker
dispatch. Workers may respond between harvests. Illustrative chronology,
not a latency benchmark:

- **10:00:** Harvest arrives; retain/classify the posts and optionally prepare
  the small budgeted ready reserve.
- **10:04:** A reads the summary, expands MiniMax's feed, receives cached
  synthesis, and requests missing first-slice/look-ahead work as needed.
- **10:09:** B expands the same feed and reuses A's completed work; an unfinished
  request joins the same job rather than starting another.
- **10:15:** New collection does not clear old post synthesis. Only new or
  meaningfully changed content creates new eligible work.

#### Economics and open measurements

Savings depend on the fraction of distinct posts synthesized across **all**
viewers, including prefetches nobody eventually reads. Caching already exists;
the new saving is avoiding generation for never-demanded posts, not caching
the same eager work again.

For example, 100 collected posts, 10 prewarmed posts, and 20 additional distinct
posts requested by readers means 30 synthesized posts: approximately **70%
fewer per-post synthesis jobs**, not 70% off the overall LLM bill. Eager
classification and translation, localized outputs, fixed prompt overhead,
repairs, and retries still cost tokens. If users collectively reach all 100
posts, lazy generation largely defers expenditure instead of avoiding it.

**Why it survives:** the default remains the AI explanation users want,
summary-only visits can be inexpensive, and staggered readers share the same
prepared evidence.

**Risks / measurements:** small-batch synthesis latency is not yet established;
do not infer it from the old 20-post combined translator or headline probes.
Measure feed-expansion rate, distinct-post synthesis rate, prefetch usefulness,
cache hits, queue time, time to first readable slice, p50/p95 completion time,
cold-filter waits, retries, and total tokens per role and locale. Low traffic
and diverse filters can produce cold misses; broad readership can erase the
selective-generation saving. These measurements set the prewarm budget, not
an assumed instant response.

### 2. Cascade classification from compact labels to specialist axes

Run compact common labels for all processed posts. The 2026-09-07 direction
keeps post types, adds the product group, and removes discourse. A cascade to
specialist evaluations remains a candidate for ambiguous or triggered posts,
with schema validation and a bounded fallback; its outputs are not yet
selected. Do not restore the removed discourse dimension through a legacy
full-classifier fallback. Reuse classifications for unchanged post content and
attribution.

**Why it survives:** Classification is retained for all posts in the current
model and becomes a larger share after headline savings. A cascade offers a
clear latency/cost lever without hiding posts from the feed.

**Risks:** Missed specialist labels can damage filters and charts. Frozen-cohort
evaluation must establish recall and UX parity before rollout; per-post
fallbacks and retries must be counted.

### 3. Material-change headline generation with durable per-brand reads

Key generation by `brand + window + facts fingerprint + prompt/model version`.
Generate only when a hot or explicitly watched brand-window is materially
changed; serve the last-good narrative immediately while one refresh runs.
Keep per-brand visible state and work slots separate from the demand policy.
Use deterministic DB captions for chart tabs rather than one narrative per tab.

**Why it survives:** It matches the existing persisted headline architecture,
removes page-view and unchanged-window duplication, and improves perceived
latency through stale-while-revalidate. For dedicated brand pages, use
`seed -> prewarm active brands -> stale-while-revalidate -> cold refresh`.

**Risks:** Fingerprint thresholds can suppress meaningful updates; cold brands
may look stale. Track changed-window rate, hot/pinned/subscribed demand,
last-good age, refresh queue age, and cache-hit latency.

### 4. Conditional critic and single strong final writer

Let one validated writer produce a candidate. Invoke the semantic critic only
for risk signals such as causal/event/quotation claims, low evidence coverage,
or disagreement; audit a random safe sample. Validate IDs, numbers, evidence
references, and schema in application code before publication.

**Why it survives:** Critic calls are a major headline cost component and the
report shows local critic calibration failures, so unconditional repetition is
both expensive and not a quality guarantee.

**Risks:** Risk heuristics can miss subtle errors; an under-called critic can
reduce trust. Freeze representative cohorts and compare unsupported-publication
rate, false holds, latency, retries, and total tokens.

### 5. Demand-shaped hot list and on-demand headline queue

Persist `hot_until`, request counters, and explicit reasons (operator pin,
follow, launch watch) in PostgreSQL. Use Redis only for short-lived dedupe
locks. A first requester reserves one job; subsequent requests read the same
persisted result. Prewarm active brands and give cold brands a bounded priority
refresh.

**Why it survives:** It makes the cost unit one changed active brand-window,
not one user or chart tab, and keeps brand-page navigation useful.

**Risks:** Popularity feedback can starve long-tail brands; request spikes can
create queue contention. Set TTLs, fairness limits, and stale-age budgets;
observe queue wait and per-brand freshness.

### 6. Swap translation/classification/headline models immediately

Route roles to cheaper or free candidates based on catalog prices alone.

**Reject for now:** The report's prices are point-in-time snapshots, several
routes lack schema enforcement or output capacity, free endpoints have shared
limits, and Hillary's local Flash passed transport but failed headline quality
and capacity calibration. Model swaps remain useful as frozen-cohort
experiments after call-shape changes, not as the first product decision.

## Recommended sequence

1. Instrument every provider call across translator, classifier, and headline
   roles with actual input/output/cached/reasoning tokens, latency, retries,
   fallback, schema outcome, and worker identity; keep reserved maxima separate.
2. Measure feed-expansion demand, distinct-post synthesis, prefetch usefulness,
   headline fingerprint changes, hot demand, cache reuse, critic escalation,
   backlog age, and user-visible freshness.
3. Trial the shared async synthesis boundary, bounded prewarm/look-ahead, and
   durable cache/hot-list on frozen cohorts. Measure the EN/ZH-CN/JA small-batch
   path and cold first-slice waits before setting budgets. Keep deterministic
   chart captions and critic escalation separate from post-synthesis UX;
   there is no deterministic per-post summary fallback.
4. Re-evaluate cheaper routes only with quality, fallback, rate-limit, and
   latency evidence. Do not expand headline brand caps until budget and queue
   capacity are explicit.

## Success measures

Product value: useful feed coverage, narrative evidence quality, and brand-page
freshness. UX: time to the first-read page summary, time from feed expansion to
readable synthesis, cold-slice waits, stale age, cache-hit latency, and
navigation readiness. Architecture/reliability: queue age, duplicate jobs,
schema-valid publication, retry/fallback rate, and restart behavior. Cost:
actual tokens and dollars per collected post, per distinct synthesized post,
and per changed brand-window, with p50/p95 by role and locale—not reserved
budgets or page views. Track summary-only sessions, feed-expansion rate, and
unused prefetches separately so apparent cache improvements do not hide wasted
generation.
