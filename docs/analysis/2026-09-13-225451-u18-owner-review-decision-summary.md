# U18 owner review: consolidated decisions and next taxonomy work

- Recorded: 2026-09-13T22:54:51+09:00
- Owner-review cohort: 45 cases, 15 each in EN, JA, and ZH-CN
- Case order: frozen `selection-manifest.json` order
- Human-review policy: the owner's review is the only human review for this 45-case development cohort
- Verbatim source: `docs/analysis/2026-09-13-203542-u18-owner-human-review-comments.md`
- Earlier owner calibration: `docs/reference/2026-09-12-030118-u18-human-ambiguity-study.md`
- Review packet: `docs/analysis/2026-09-13-072308-u18-human-review-packet.md`

## Plain-English outcome

The 45-case owner review is complete. It is the sole human judgment for this
development cohort. It replaces the previously planned two-reviewer and
adjudicator exercise for this cohort, and the blank case entries in the
owner's completed review are treated as approval of the proposed row. This
does not create a blinded-human accuracy score or an inter-reviewer agreement
score, because those measurements require independent reviewers.

The current 13-post-type contract can close after the case corrections below
are written into the owner reference and the provider-free validation passes.
The owner also identified three improvements that change the label space:
Audience Topics, `news_reporting`, and claim metadata to replace the misleading
`misinformation` product label. Those belong to a new semantic taxonomy
revision. They should not invalidate or silently alter the completed 45-case
review.

## POV: organize the taxonomy by what each field means

Do not revive `discourse`. It was a rhetoric taxonomy, it is being retired by
the current plan, and its old storage couples discourse with nationalism.
Reusing the name for audience subjects would create misleading historical data
and preserve the coupling we are removing.

Use these independent dimensions instead:

| Dimension | It answers | Examples |
| --- | --- | --- |
| Post type | What kind of post is this? | result/evaluation, event, opinion, news report |
| Product label | What product-feedback signal does it contain? | bug, complaint, testimonial, idea/request |
| Audience topic | What audience-relevant subject does it discuss? | local inference, cost/performance, model distillation |
| Sentiment | What is the author's valence toward this attributed brand? | positive, negative, neutral, mixed |
| National stance | Does the author favor or criticize a country? | China stance, U.S. stance |
| Claim metadata | How is a consequential claim presented and reviewed? | reported allegation, corroborated, inconclusive |
| Source relationship | Who is speaking in relation to this brand? | official, staff, third party |
| Unsanctioned flag | Is the post promotional abuse or another caution signal? | marketing spam, scam, crypto promotion |

This separation lets a neutral news report about a U.S. agency's distillation
allegation be tagged as `news_reporting`, `model_distillation`,
`geopolitics_state`, and `reported_allegation` without calling the reporter
anti-China or declaring the allegation false.

## Audience Topics recommendation

Create a new versioned, many-to-many, per-post-and-brand Audience Topics facet.
The initial `ai_audience_topics/v1` manifest should contain:

| Key | Boundary |
| --- | --- |
| `local_inference` | Running or deploying a model on local, edge, self-hosted, or user-controlled hardware; open weights alone are insufficient. |
| `cost_performance` | Price, compute, memory, energy, or operating cost in relation to speed, quality, or capability. |
| `model_distillation` | Distillation as a method or as an alleged way to reproduce model capability; the topic makes no truth judgment. |
| `evals_benchmarks` | Evaluations, leaderboards, scores, and benchmark methods. |
| `openness_license` | Weight/source access, licensing, commercial-use terms, and openness claims. |
| `agents_tools` | Agent systems, tool use, orchestration, and agent workflows. |
| `api_developer_surface` | APIs, SDKs, integration interfaces, quotas, and developer experience. |
| `geopolitics_state` | Governments, state actors, national security, export controls, industrial policy, or international competition. |

`cost_performance` is clearer than `cost_value`: it names the tradeoff that the
audience wants to study. H3569508600E should receive both `local_inference` and
`cost_performance`. H638DEDC4101 should receive `geopolitics_state` while its
China and U.S. stance values remain `none`.

Store stable topic concepts separately from localized labels and aliases. A
label-only change keeps the concept key; a material definition change creates
a new scheme revision. Older rows where a topic did not yet exist are
“unavailable,” not false. Historical queries must expose the stored revision
and offer separate `current_definition` and `historical_inclusive` modes. This
follows the same version discipline already locked for the post-type refactor.
The concept/label separation is also consistent with the
[W3C SKOS model](https://www.w3.org/TR/skos-reference/) and
[Contentful's taxonomy model](https://www.contentful.com/developers/docs/references/content-management-api/taxonomy/).

Run Audience Topics as a separate versioned classifier pass at first. Adding
eight more decisions to the fragile primary/reviewer prompt would reopen U18
and obscure whether failures come from the post-type contract or from topics.

## Journalism and releases

Do not widen `releases_updates` to general industry news. That would prevent a
user from cleanly filtering actual product or brand releases.

Add `news_reporting` as a fourteenth post type in the next taxonomy revision:

> Primarily relays a current development, sourced report, announcement, or
> news roundup to inform readers. It may coexist with release, business,
> research, result, or opinion types. A first-party product announcement alone
> is not third-party news reporting.

The resulting filters are explicit:

- Product update: `releases_updates`
- General report: `news_reporting`
- Third-party coverage of a product update: both
- Official product announcement: `releases_updates` plus the official source relationship
- General industry news without a target-brand release: `news_reporting` without `releases_updates`

H1A3B3731E1C, H4E3B98376E5, and HB94D1A5CA63 are positive examples for the
new boundary.

## Replace `misinformation` with claim metadata

H2B36BE298C6 received `misinformation` because the v26 prompt defines that
label broadly as “a potentially misleading claim that may warrant review” and
says that it does not adjudicate the claim false. The saved response contains
no reasoning or evidence trace for the choice, so the broad prompt rule plus
the theft/distillation allegation is the available explanation.

The name is inaccurate for the behavior. Move this concern out of product
labels and model it as:

- `claim_presentation`: `author_assertion`, `reported_allegation`, or `disputed_claim`
- `claim_review_status`: `unreviewed`, `corroborated`, `contradicted`, or `inconclusive`

The classifier may identify how a claim is presented. A separate review must
set truth-oriented status. H2B36BE298C6 should be `model_distillation` +
`geopolitics_state` + `reported_allegation`, with neutral sentiment and no
nationalist stance from the reporter.

Filtering `opinions_reactions` plus negative sentiment is not an adequate
substitute. It misses neutral reports of allegations and includes ordinary
criticism. A historical keyword screen found 357 distillation-related posts
among 185,895 posts (about 0.19%), with roughly 40 tight accusation candidates
(about 0.022% of all posts, or 11% of distillation candidates). These are
screening rates from the frozen corpus, not a forward prevalence forecast. A
bounded shadow pass is required before setting expectations for the new field.

## Nationalism and geopolitical discussion

Keep `geopolitics_state` separate from nationalism. A post can discuss states,
national competition, export controls, or government power without favoring
or attacking either country. This resolves H638DEDC4101 without forcing a
neutral geopolitical argument into a pro/anti bucket.

For the present v3 owner reference, use the closest current values and record
lossy cases:

- H0040D161174: store China `anti`; record that the owner's intended intensity
  is **mild anti**, which the current enum cannot represent.
- H2B36BE298C6: store China and U.S. `none`; the reporter attributes the
  allegation rather than adopting it.
- H638DEDC4101: store China and U.S. `none`; apply `geopolitics_state` later.
- H9C7C731F3C3: keep China `pro`. The full stored post, which was missing from
  the truncated review view, says `这不是“国产替代”的叙事，而是“全球统治”的叙事。`
  (“This is not a narrative of domestic substitution, but of global
  dominance”) and says Chinese domestic models are proving China's true
  position in the global landscape. Those lines provide explicit pro-China
  evidence.

If more countries later become first-class filters, replace the two country
columns with actor/stance rows rather than adding one column per country.

## Product-label decisions

A testimonial is a favorable statement about the **current attributed brand's
product or achievement**: praise, endorsement, a favorable experience, clear
admiration, or clear positive anticipation. It does not require a formal
customer quote. Praise of another company, a person alone, or the author's own
brand does not transfer to the target brand.

This definition explains H4E55D967F4E: “nothing but expectations” is positive
anticipation, so it should be a Qwen testimonial when the Qwen-derived model is
the attributed subject. It also explains why H42DCD9324F4 is not a MiniMax
testimonial (the promotion is for Runway), H7F29D6428BB is not a Qwen
testimonial (the praise is for Corpus), and HB4FB5810A09 is not an external
testimonial (it is the official brand replying to a user).

`questions_requests` and `ideas_requests` remain independent, but the product
label must include a brand-directed request to resolve an issue even when the
author does not propose a solution. H0DEC6F537E0 is therefore both a question/
request post and an idea/request product signal. A purely informational
question with no requested product response remains `questions_requests`
without `ideas_requests`.

Do not add a `use_case` product label. The already accepted derived segment
`product_evidence/v1` surfaces `results_evaluations` rows without
`ideas_requests`; its `observed_use_cases/v1` subset additionally requires
`hands_on_usage`.

## Source relationship and unsanctioned rules

The current main classifier receives post text, brand IDs, and stored context,
but not the source's per-brand official/staff relationship. The rare audit has
`source_role`, which explains inconsistent official-account treatment. Add the
per-brand source relationship to the primary and review envelopes; a global
account role is insufficient because one account can have different
relationships to different brands.

Official/staff context should affect interpretation before labels are stored:

- Do not store an official account's self-praise as a customer testimonial and
  then hide it later. Store the correct label once.
- Do not automatically mark current official lab promotions as
  `marketing_spam`.
- Make the exemption a brand-level policy, such as
  `official_promotion_policy=allowed|review|unsanctioned`, so future tracked
  intermediaries can use a stricter rule without changing the taxonomy.
- Keep `scam`, `crypto`, and `unauthorized` evidence independent; official
  status should not blindly erase them.

Do not flag every advertisement for another product as unsanctioned. Apply
`marketing_spam` when there is a promotional call to action, discount/free
access wrapper, referral pitch, or repeated aggregator promotion. Ordinary
comparisons and mentions remain unflagged. H42DCD9324F4 is a positive example
for third-party `marketing_spam`; H69C877BE195 is a negative example because it
comes from the official Upstage account under the current lab policy.

Keep `crypto` as the unsanctioned flag. `blockchain` is broader and would catch
neutral infrastructure discussion. The UI may display “Crypto/token
promotion.” A future neutral `blockchain` subject belongs in Audience Topics.

The 45-case packet contains four v26 `marketing_spam` flags
(H5024EDC82C6, H69C877BE195, H8FA9071508D, and HDA7D2AEEC6F) and one `crypto`
flag (H5024EDC82C6). It contains no `scam` or `unauthorized` flags.

## Media-dependent and off-topic posts

Use `context_missing` when text and stored quote/parent context are too cryptic
to support a brand-specific judgment. Do not infer facts from an inaccessible
image, video, page, or link.

A reproducible proxy—at most 100 Unicode characters, contains a URL, and has
no stored context—found potentially link/media-dependent posts in 3/45 (6.7%)
of this packet, 10/120 (8.3%) of the development cohort, and 21/500 (4.2%) of
the source cohort. This proxy over- and under-counts true media dependence, but
the observed 4.2% source-cohort rate supports a deferred, measured media
enrichment task rather than expanding the current classifier now.

H70A9986C432 should become `context_missing` under the evidence envelope used
for this study. HE10CACEDD3F passed collection because its text literally
contains the tracked token `Qwen`; it should remain `context_missing`, and the
Ferrari/rally “Qwen clip” collision is a deferred relevance-filter issue.
HF3B55FD811B remains the previously accepted off-topic harvester edge with no
classifier change.

Repeated b.ai/`@BAI_AGI` promotion appears in H5024EDC82C6,
H8FA9071508D, and HDA7D2AEEC6F. Keep the posts as source evidence and exclude
them from normal views through `marketing_spam`. Add source/domain recurrence
metrics before creating a harvester ban; a ban would discard evidence and may
hide new abuse patterns.

## Closed beta and hands-on boundaries

A closed beta is an `opportunity` only when the post offers the audience a
bounded route to apply for, request, or receive access. Merely reporting that a
private beta exists is a release/update. Store explicit dates and precision
when supplied; do not invent a deadline from post, fetch, or first-seen time.
H688781944AC is an opportunity because the author is actively requesting entry.
No solicited/unsolicited request scale is added now.

`hands_on_usage` requires visible evidence that the author actually used,
built with, ran, configured, or tested the product. H74C810FB007 qualifies:
the author evaluates Japanese writing, discusses changing the prompt, and
compares the tested Pro result with Flash. H7B628A24F88 does not qualify merely
for explaining the architecture.

## Consolidated 45-case owner reference

Rows marked “accept” retain the packet's proposed owner-reviewed
classification. “Future” records a new-taxonomy requirement without changing
the current v3 row. The order below is the frozen manifest order.

| # | Case | Current-v3 owner decision | Future/deferred note |
| ---: | --- | --- | --- |
| 1 | `H0040D161174` | Set China nationalism to `anti` as the closest current value. | Add `mild_anti` or redesign country stance; topics `local_inference`, `cost_performance`, `geopolitics_state`. |
| 2 | `H0DEC6F537E0` | Classified; post types `questions_requests`, `events`; product `ideas_requests`; neutral; nationalism none/none. | Clarify brand-directed issue-resolution requests in prompt. |
| 3 | `H1A3B3731E1C` | Post types `events`, `research_explanations`; no product labels; neutral; nationalism none/none. | Add `news_reporting`. |
| 4 | `H1E48CCEEB2F` | Accept. | Surface through `product_evidence/v1` and `observed_use_cases/v1`; topics `local_inference`, `agents_tools`. |
| 5 | `H2B36BE298C6` | Post type `research_explanations`; retain temporary compatibility `misinformation`; neutral; nationalism none/none. | Replace label with `reported_allegation`; topics `model_distillation`, `geopolitics_state`; add `news_reporting`. |
| 6 | `H3569508600E` | Add `testimonial`; set sentiment positive; retain current post types. | Topics `local_inference`, `cost_performance`. |
| 7 | `H42DCD9324F4` | Post type `advertising_marketing`; no product labels; neutral; add `marketing_spam`. | Preserve strict per-brand stance and third-party-ad rule. |
| 8 | `H4E3B98376E5` | Post type `research_explanations`; no product labels; neutral; nationalism none/none. | Add `news_reporting`; retain no `results_evaluations`. |
| 9 | `H4E55D967F4E` | Add `testimonial`; retain `opinions_reactions`, positive, nationalism none/none. | Prompt should include clear favorable anticipation. |
| 10 | `H5024EDC82C6` | Accept, including `marketing_spam` and `crypto`. | Keep `crypto`; optional neutral `blockchain` topic later. |
| 11 | `H540717FEDF5` | Retain prior correction: only `opinions_reactions`; add `testimonial`; positive; no `business_finance` or `results_evaluations`. | Topic `cost_performance`. |
| 12 | `H638DEDC4101` | Keep post types/product/sentiment; set China nationalism to `none`. | Topic `geopolitics_state`; redesign country stance if needed. |
| 13 | `H688781944AC` | Add `opportunities`; retain `questions_requests`, `ideas_requests`, positive, nationalism none/none. | Persist unknown/ambiguous availability rather than inventing a deadline. |
| 14 | `H696CC3BCE4C` | Accept. | None. |
| 15 | `H69C877BE195` | Accept classification; remove `marketing_spam` because source is official under current lab policy. | Pass per-brand source relationship and add brand policy. |
| 16 | `H7046A8A0689` | Retain prior correction: `opinions_reactions`, no product label, positive, nationalism none/none. | Meta/Muse praise does not transfer to Qwen. |
| 17 | `H70A9986C432` | Change to `context_missing`. | Deferred media enrichment. |
| 18 | `H74C810FB007` | Add `hands_on_usage`; retain results/opinion, complaint, mixed, nationalism none/none. | None. |
| 19 | `H7B628A24F88` | Accept. | None. |
| 20 | `H7F29D6428BB` | Retain prior correction: add `opportunities`, remove Qwen `testimonial`, keep remaining fields. | Canonical Event identity rules remain R84. |
| 21 | `H87229E54527` | Accept the prior correction: opinion/testimonial/positive without results. | Linked video cannot supply results evidence. |
| 22 | `H8D074DCC4D3` | Accept `context_missing`. | None. |
| 23 | `H8FA9071508D` | Accept, including `marketing_spam`. | Track repeated b.ai source/domain behavior. |
| 24 | `H92A808A114E` | Add `testimonial`; set sentiment positive; retain current post types. | Topic `cost_performance`. |
| 25 | `H951CA2C2BF9` | Accept. | Topics `cost_performance`, `evals_benchmarks`. |
| 26 | `H9920CC08778` | Accept. | Topic `evals_benchmarks`. |
| 27 | `H9C7C731F3C3` | Accept current row, including positive and China `pro`, based on full stored source. | Packet should show the decisive full-source excerpt. |
| 28 | `HAF1D06FBEBA` | Accept prior correction/current row. | None. |
| 29 | `HAF97A8DDDDE` | Accept. | Candidate for `news_reporting`. |
| 30 | `HB4FB5810A09` | Remove `testimonial`; retain opinion, positive, nationalism none/none. | Pass official relationship; distinguish self-praise from customer evidence. |
| 31 | `HB94D1A5CA63` | Accept. | Add `news_reporting`. |
| 32 | `HC63FABBF5A3` | Accept. | None. |
| 33 | `HC9205DA00E5` | Accept. | Surface through product-evidence/use-case segments. |
| 34 | `HCA162EAEBE0` | Accept current positive sentiment. | None. |
| 35 | `HCC2BC2A1B6B` | Accept v26. | Topic `local_inference`. |
| 36 | `HCCC266D762E` | Retain prior correction: remove testimonial and set neutral; keep current post types. | Do not infer media valence. |
| 37 | `HDA7D2AEEC6F` | Accept `context_missing` and `marketing_spam`. | Fix target attribution/context handling; track b.ai recurrence. |
| 38 | `HE10CACEDD3F` | Accept `context_missing`. | Deferred Qwen-token/relevance collision. |
| 39 | `HE2CCD66B3DE` | Accept. | Topics `local_inference`, `cost_performance`. |
| 40 | `HE6730DF39A2` | Retain question/result/opinion; remove `ideas_requests` and `testimonial`; set negative; nationalism none/none. | The author questions the evaluation's credibility rather than requesting a capability. |
| 41 | `HF3B55FD811B` | Accept the prior no-change/off-topic disposition for this study. | Deferred rare harvester relevance edge. |
| 42 | `HF4987074B1F` | Accept `context_missing`. | Pass staff relationship, but absent parent still prevents classification. |
| 43 | `HF5D74262E64` | Keep release/opinion; remove `complaint`; set neutral; nationalism none/none. | Pricing policy may later receive `cost_performance`. |
| 44 | `HF7C5DFD8079` | Accept. | None. |
| 45 | `HFD61C2DE5BD` | Accept. | Topic `evals_benchmarks`. |

## Closure and execution order

The 45-case human-review exercise is **complete by owner acceptance**. Its
human gate is **waived by owner** for this development cohort. The durable
record must state:

- owner-reviewed and unblinded;
- sole human reference for these 45 cases;
- no independent reviewer or adjudicator answers;
- no measured inter-reviewer agreement;
- no claim of blinded human gold or production accuracy;
- the cohort remains consumed development evidence;
- provider, cost, extraction, staging, rollback, and exact-SHA production gates
  remain separate.

Proceed in this order:

1. **Complete:** write the 45 current-v3 decisions above into the owner
   reference, preserve manifest order, validate all enum and completeness
   invariants, and mark the owner review closed.
2. **Complete:** run the bounded v27 DeepSeek Pro diagnostic against that
   exact owner reference and preserve its responses, usage, and budget.
3. **Complete:** replay the saved responses after correcting the evidence
   cardinality invariant. The provider-free replay parsed 30/30 rows with zero
   new transport, but missed the preregistered post-type and product-label
   agreement floors: 63.33% versus 70% and 76.67% versus 85%. Outcome accuracy
   passed at 96.67%. These are owner-reference agreement measures, not human
   accuracy. See `2026-09-13-232100-u18-v27-evidence-reuse-failure-replay.md`.
4. **Next:** apply the current-v3 prompt corrections exposed by the owner
   reference and failed diagnostic, then evaluate a new immutable candidate.
   No further human review is required for this 45-case cohort.
5. After the current-v3 diagnostic gate passes, implement the separately
   versioned U18A revision: `news_reporting`, Audience Topics, claim metadata,
   and per-brand source relationship in classifier envelopes. Do not
   retroactively score its new fields against this 45-case v3 review.
