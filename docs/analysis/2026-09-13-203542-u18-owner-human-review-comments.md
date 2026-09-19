here are all my comments, you will need to combine with my prior comments in this session and organize: ---
created_at: 2026-09-13T20:35:42.325709+09:00
timezone: Asia/Tokyo
source: sublime
---

general ask: to be super vertically oriented towards our audience, we need idiosyncratic tags including the following: local LLM; distillation claims. also, we need a tag for cost/performance. this was what 'discourse' taxonomy was supposed to be. do we need to revive discourse in order to do this? brainstorm and pov some ideas. these tags will change over time as we adjust to the most relevant topics of our audience.



H0040D161174
china nationalism: mild anti

H0DEC6F537E0
{"outcome": "classified", "post_types": ["questions_requests", "events"], "product_labels": ["ideas_requests"], "sentiment": "neutral", "china_nationalism": "none", "us_nationalism": "none"} <<< thef act that post type picked up question request, but product label did not, is concerning. should check on that. "i have some issues" is ambiguous enough for sentiment to be neutral or null

H1A3B3731E1C


this is actually a very standard 'journalism' post, reporting on something. post type should include research_explanation. sentiment should be neutral, since its stance is more info gathering.

H1E48CCEEB2F

see my thgouhts on a 'use-case' product label. this would be one of those posts.

H2B36BE298C6

this is a tough one. this is reporting on a clearly chinese nationalism stance. but the post itself is just reporting neutrally. so actually v26 is wrong in several ways. nationalism should be neutral; 

i'm wondering why this was detected as misinformation; give me details on how that occurred; my sense is that we need to rename misinformation. Grok's point is that it is more a flag for requiring further review. 

irregardless of whether thse claims were brought by a 3rd party or by the author of the post, in that event, allegations of misdoing, distillation, etc. should be given such a product label. let's brainstorm on better labels; some ideas: 'allegation'; but if allegation is what we are trying to find, then do we need a whole new product label? see if we can surface these particular posts by filtering for opinions/reactions with negative sentiments. if we do indeed relabel it allegation, or 'unproven claim', and reconfigure the prompt as such, roughly how many would we uncover on a % basis going forward?

this begs the question: releases/updates is currently geared towards product or brand specific ones (which it should be). however for general but very significant new releases such as this, how do we classify this? we have 13 posttypes already, to add another one would be really hard. if we do widen the definition of releases/updates to include news items such as this, how would user filter these for just product-specific release/updates?

H3569508600E

this should have a testimonial product label, and sentiment should be positive. 
"MiniMax H3 can generate video locally even with 8GB VRAM + 64GB RAM" <<< the use of 'even' is very telling: this is a positive endorsement of how, even with scant resources, minimax performs. the context is that local LLM is all about pulling intelligence from ever smaller hardware

H42DCD9324F4

this is advertising about a product called Runway. therefore sentiment and product label towards each brand should be neutral and none. it's the same point we had before: enforce sentiment and product label stance strictly towards the brand in question.
this should also get an unsanctioned flag, as this is advertising about a 3rd party product (we don't know for sure if they are affiliated with the brands, but we can add this flag as a caution--the user will know whether this was sanctioned or not)

H4E3B98376E5

this is also a news type, posting info from 3rd party with neutral stance like H1A3B3731E1C


H4E55D967F4E
why isn't this testimonial? give me a brief definition of how we are classifying a testimonial

H5024EDC82C6
should we relabel from crypto to blockchain? which is more accurate and more neutral (is crypto a bit negative)

H540717FEDF5
should be testimonial. this is not business/finance (see our prior discussion in session)

H638DEDC4101
another tough one that makes me rethink our taxonomy. posts like this are neither ostensibly pro/anti either cn or us. instead, they are making a broader geopolitical point. let's brainstorm on a better nationalism taxonomy that more accurately classifies this one. we definitely want to tag these kinds of posts with a 'geopolitical', or better yet, a 'state-level' classification, to show that user is mentioning a brand, but is making a point that widens the scope to include state actors. this is an insightful point that is not necessarily colored by bias either way--instead making a logical claim and putting forward an argument based on that.

H688781944AC
correctly classified as 'opportunities' by v25, however we need to make sure the time gating is properly ambiguous, as a 'closed beta' should not be surfaced as an impending event with a deadline. such closed betas asre not offered publicly, therefore it's debatable whether this is an opportunity or not. i think we can't capture every edge case such as this, so we can address this by having sufficiently vague time gates. note: whether we need a 'solicited' vs unsolicited type scale for requests (for the product people). i'd say no for now

H696CC3BCE4C
correct

H69C877BE195
this is NOT marketing spam, because it is written by an official account. for now, our official accounts (which are comprised of the ai labs) do NOT spam. however, in the future, when we widen the lens of the brands we track, we may in fact have brands (not ai labs, but intermediarly ai companies) that do spam. what is the easiest way we can clear current brands from any unsanctioned flags, but  allow for this rule to be differnetly applied in future?

H7046A8A0689
see my comments before; this is about meta model



H70A9986C432

it seems even the grok run didn't read the media, which is critical to interpreting this post. i used grok on the x post itself and here's the result:

The X post uses two anime-style chibi images of a blue-haired maid character celebrating Zhipu AI's GLM model price hikes ("GLM涨价") while dominating a defeated black-haired rival, with captions like "Finally got fooled" and "Price-hike big model, kneel before me!"
Text reads "依旧跑赢没奖励，跑输被斩杀" (Still, winning the race brings no reward; losing gets you beheaded), sarcastically critiquing the brutal Chinese LLM market where strong performance yields little gain but underperformance leads to elimination.
Hashtagged #DeepSeek, it references the intense 2026 AI pricing shifts—including DeepSeek's major August API hikes with peak/off-peak rates and prior price wars—amid broader industry moves by GLM and others toward value-based pricing.

The poster is complaining, in a jokey way, that competing in China’s AI-model market is a lose-lose game.They mean: even if your model “wins” (performs well or gains users), you still don’t get a real prize—prices stay squeezed or you have to raise them and look greedy. If you lose the race, you’re finished. The cute pictures mock GLM’s price hike and treat it like the winner stepping on a rival, while the #DeepSeek tag points at DeepSeek as part of the same messy price-war-then-price-hike cycle.


this post, without the media, is too short and cryptic to classify. how often do we see posts like these (where we can't interpret due to not accessing the media?) if it is rare, we can just pass on this for now and make this a to-do.

H74C810FB007
mostly correct. why not hands-on? presumably this author used it.


H7B628A24F88

this was correct not to apply hands-on, because technically, user did not have to actually use the product to pontificate on the underlying architecture


H7F29D6428BB

covered this last time



H87229E54527
covered this before



H8D074DCC4D3
context missing is correct; there is no parent to this post; either user misposted (rather than replying) or just posted this. 

H8FA9071508D
b.ai is spamming a lot via multiple accounts

H92A808A114E

sentiment should be positive. pointing out that 15 seconds of content can be generated in 9 seconds is a compliment. product label should be testimonial

H951CA2C2BF9


H9920CC08778


H9C7C731F3C3

sentiment should be positive; i do not see pro china nationalism here (at least in truncated message; this account has been suspended so i cannot see the entire message on x). give me the explicit pro china text that you have

HAF1D06FBEBA

HAF97A8DDDDE

HB4FB5810A09

this is from the official account, therefore it doesn't need a product label (should we add product labels to official account's posts, and then filter out later?)

HB94D1A5CA63
another canddiate for the news type post/tag

HC63FABBF5A3

HC9205DA00E5

should any post detected as advertising that is NOT for the brand itself, be tagged as unsanctioned?

HCA162EAEBE0
sentiment: positiv

HCC2BC2A1B6B
v26 correct

HCCC266D762E
covered by me before in session

HDA7D2AEEC6F
b.ai spam again - wondering if worth banning posts like this--but actually the post will already have been captured. probably not a ton of spam right now but this will increase once we add the frontier models to our list of brands being tracked. worth a small brainstorm--if there are enough posts like these


HE10CACEDD3F
how did this pass harvester? seems very rare and not worth worrying about

HE2CCD66B3DE

HE6730DF39A2
my interpretation is that sentiment is negative. user is expressing surprise that a model that lacks some fundamental capabilities got such a good score--therefore questioning credibility of those tests

HF3B55FD811B
covered before


HF4987074B1F

note this is from a staff account; note that without that context grok cannot properly classify, underlining the point that we probably should use our knowledge of official/staff accounts for our classifier


HF5D74262E64
i don't think this is clearly a complaint, product category should be none; grok's analysis is right

HF7C5DFD8079
correct



























. <<< save this entire prompt verbatim as an artifact and attach as exhibit to our plan ultimately. for now, evaluate all the questions and my comments, and organize into a summary to file. note that my personal eval of all 45 questions will be the only human review that we do, and so once these comments are addressed, show that the tests are closed and we can proceed.

---

## Prevalence analysis added 2026-09-14

Everything above this divider remains the owner's original message byte for
byte. Its SHA-256 before this appendix was added was
`bb1dca6b9f4d2b931ef93e9d79946ca41c2cbc8efacd2618ac12b8c550cd49ab`.
This appendix answers the prevalence questions in that review and includes the
later question about geopolitical framework versus nationalistic stance.
Machine-readable results are preserved in
`docs/analysis/2026-09-14-075314-u18-owner-edge-prevalence.json`.

### Evidence boundary

The primary source is the frozen production dump at
`/Users/fuchitalee/Downloads/pushinweight-dumps/pushinweight-prod-20260910-165134.dump`,
SHA-256
`618f31498b94a42e54940c4e5bf90d7bb09a122b72f1406181b4e029f9b25e06`.
It contains 211,245 posts through 2026-09-10 16:45 JST, including 210,587
distinct brand-attributed posts and 252,579 post-brand pairs. Rates below use
distinct brand-attributed posts unless the text says “pairs.”

Historical classifier labels are model output rather than human truth. The
lexical queries are high-recall screens with false positives and false
negatives. Their counts are useful prevalence bounds, but they are not
precision, recall, or a forecast of future traffic. The 45-row owner reference
and 30-row v27 run are consumed development evidence and measure agreement
with this review rather than production accuracy.

An earlier exploratory unsanctioned/role check used the retired 20,322-post
SQLite extract covering April–May 2026. The newer September PostgreSQL dump
supersedes that extract for every rate in this appendix; the two populations
must not be compared directly.

### Decisions at a glance

- **Add `news_reporting`:** a conservative screen found 3,556 general-news
  candidates without a product release, or 1.69% of branded posts, which is large
  enough and serves a distinct user filter.
- **Shadow-test one Geopolitical family in place of the separate Nationalism
  and geopolitical-topic split:** even the narrow framework screen found 1,913
  candidates, or 0.91%, and 68% had no stored national stance; the broad screen
  found 5.07% and 80% had no stance, but these lexical screens do not establish
  classification precision.
- **Add `model_distillation` plus claim-presentation metadata:** likely
  distillation-allegation traffic is approximately 0.22% to 0.46%; it is rare
  but strategically valuable, and a negative-opinion filter misses most of it.
- **Do not add a broad `allegation` product label:** generic allegation terms
  appeared in 5.16% of branded posts and the sample was too noisy.
- **Add role-aware and repeated-promoter handling:** `@BAI_AGI` occurred in
  4,116 posts, or 1.95%, and more than half were not already marked marketing
  spam; 11.88% of official-account posts were also marked marketing spam.
- **Keep media enrichment deferred:** short media/link posts form a 3.18% to
  4.38% upper-bound queue, while a small exploratory review found only one
  clearly dependent case in 100; keep using `context_missing` and measure a
  dedicated media lane before paying to enrich all media.
- **Keep the closed-beta boundary inside `opportunities`:** limited-access
  language appeared in 0.31% of posts, but an explicit audience action route
  appeared in only 0.08%; this does not justify another label.
- **Treat HE10-style “Qwen clip” traffic as spam/relevance:** the screen found
  372 hits across 12 normalized templates from eight accounts in four days, so
  it is a concentrated keyword-collision burst rather than a taxonomy concept.
- **Keep questions separate from product requests:** 57% of question rows in
  the 120-row v26 cohort and 50% in the owner reference correctly had no
  `ideas_requests` label.
- **Tune testimonial, result/evaluation, and request prompts:** the owner added
  four testimonials and removed six across 45 rows; this is a prompt-quality
  issue rather than evidence for more labels.

### Questions versus product ideas or requests

The 120-row v26 cohort has seven `questions_requests` rows. Four of the seven
(57.1%) have no `ideas_requests` label. Text review found those four to be
informational or rhetorical questions: how long something would run, whether
Qwen raised Mac mini prices, which domestic agent might outperform another,
and a question to builders about product discovery. They do not ask the
attributed brand to change or fix its product.

The completed 45-row owner reference has four question/request rows. Two
(50%) intentionally have no product idea/request. H0DEC6F537E0 is one of the
other two: asking to discuss issues after a meetup registration is a
brand-directed request for resolution, so it should receive both fields.

**Decision:** preserve independent fields. Clarify that a product-directed
request to fix or resolve an issue qualifies as `ideas_requests`, even when the
author offers no proposed solution. Do not automatically copy every
`questions_requests` post into `ideas_requests`.

### Distillation and allegations

The historical `distillation_accusation` label appears on 467 posts (0.22%) and
687 post-brand pairs (0.27%). A broad multilingual distillation term screen
finds 2,255 posts (1.07%). Requiring both a distillation term and accusation
language narrows the queue to 961 posts (0.46%). The samples include real
allegations and reporting, along with false positives such as ordinary model
compression, technical tutorials, and unrelated uses of “distilled.”

Only 209 of those 961 tight-screen posts had historical negative sentiment.
Filtering for negative opinion would therefore surface 21.75% and miss 78.25%
of that candidate queue, including neutral reports of third-party allegations.
A generic multilingual allegation screen found 10,856 posts (5.16%) and was
far too broad to serve as a product label.

**Decision:** use `model_distillation` as an audience topic and store how a
consequential claim is presented, including `reported_allegation`. Do not use
negative sentiment as the retrieval mechanism and do not create a generic
`allegation` product label. Run the versioned shadow classifier before treating
0.22% to 0.46% as anything more than the likely review-queue range.

### News reporting versus product releases

A multilingual third-party news-marker screen found 4,299 posts (2.04%). Of
those, 3,556 (1.69%) had no historical release label and 743 (0.35%) overlapped
one. Separately, 13,298 posts (6.31%) had the historical product-release proxy,
and 12,555 (5.96%) had no third-party news marker.

**Decision:** add `news_reporting` as the fourteenth post type and keep
`releases_updates` product- and brand-specific. The two may coexist when a
third party reports a product release. Widening `releases_updates` would mix a
roughly 1.69% general-news population into the 5.96% release-only population
and make the product-release filter less useful.

### Geopolitical framework versus nationalistic stance

The old classifier stored a non-`none` China or U.S. stance on 6,468 posts
(3.07%). A broad actor-plus-framework screen found 10,683 posts (5.07%); 8,543
of them, or 80.0%, had no stored national stance. A narrower screen requiring
both China and U.S. references plus framework language found 1,913 posts
(0.91%); 1,308, or 68.4%, had no stored stance. The lexical screens are noisy,
but both show that state-level analysis without a nationalistic stance is a
regular category rather than a one-off distinction.

**Provisional design for the shadow pass:** call the whole dimension
**Geopolitical** and remove `geopolitics_state` from Audience Topics. Within
Geopolitical, allow the multi-label modes `reporting`, `framework`, and
`nationalistic_stance`; an empty set means the post is not geopolitical. Keep
country-specific direction only when the author actually takes a nationalistic
stance, using renamed China and U.S. national-stance values for the current
scope.

The prompt boundary should stay concrete:

- `reporting`: attributes a geopolitical claim or stance to someone else
  without adopting it;
- `framework`: explains or predicts how states, policy, markets, security, or
  national systems interact, including “China's AI strategy is more effective”
  when the claim is only about instrumental effectiveness;
- `nationalistic_stance`: assigns broader moral, civic, cultural, or systemic
  superiority or inferiority to a state or national group, such as “the U.S.
  will win AI because capitalism makes America inherently superior.”

The modes may coexist when the text does both. This avoids the ambiguous label
“neutral geopolitical stance.” A framework can be neutral in authorial
sentiment while still making a strong comparative claim. The 0.91% narrow and
5.07% broad candidate rates justify testing this small mode set. Activate it
only if a bounded shadow comparison shows that the model separates the three
modes reliably without an unacceptable token, latency, or error increase.

### Media-dependent posts

The dump contains media metadata for 57,055 branded posts (27.1%), but media
presence alone does not mean the text is unclassifiable. A structural upper
bound found 6,691 posts (3.18%) with media, at most 100 visible characters after
removing URLs, and no stored quote or locally stored reply parent. Replacing
“has media” with “has a URL” produces 9,228 posts (4.38%). An agent-assessed
exploratory sample of 100 cases found one apparent media/link-dependent case;
that 1% observation is directional, not a human prevalence or accuracy
estimate.

**Decision:** keep `context_missing` for unsupported cases such as
H70A9986C432. Add a measured media-enrichment trial later, scoped to the short
no-context queue. Do not increase classifier context cost for all 27.1% of
posts that happen to have media.

### Repeated b.ai promotion and third-party advertising

The literal `@BAI_AGI` appears in 4,116 branded posts (1.95%) from 341 authors.
Only 1,988 (48.3%) already have a legacy `marketing_spam` flag. This is large
enough for explicit recurrence and promotional-evidence handling.

Historical `advertising_marketing` appears on 15,090 third-party post-brand
pairs. Of those, 10,761 (71.3%) also have `marketing_spam`; 4,329 (28.7%) do
not. The unflagged group includes ordinary comparisons, reporting, and generic
recommendations, so advertising cannot automatically imply unsanctioned spam.
The legacy unsanctioned flag is post-level while advertising and account roles
are per brand, so this overlap also cannot identify which brand caused the
flag on a multi-brand post.

**Decision:** retain these posts as abuse evidence and default-hide qualifying
ones. Apply `marketing_spam` when third-party advertising has a call to action,
referral, free-access/discount wrapper, repeated template/source behavior, or
similar promotional evidence. Persist the new decision per post and brand,
with the legacy post-level flag kept as compatibility data. Add a deterministic
b.ai recurrence rule, but do not ban the posts at harvest time.

### Official and staff promotions

Among 1,204 distinct posts from accounts with an official relationship to the
attributed brand, 143 (11.88%) carry legacy `marketing_spam`. Among 1,001 staff
posts, 66 (6.59%) do. Pair-level rates are similar: 169/1,408 official pairs
(12.00%) and 75/1,197 staff pairs (6.27%). Samples include ordinary official
calls to action, releases, events, and jobs, so the owner-identified false flag
is systematic enough to fix.

**Decision:** pass the reviewed account-brand relationship into classification
and use a brand-level `official_promotion_policy` with `allowed`, `review`, or
`unsanctioned`. Set current AI-lab brands to `allowed`; future intermediary
brands can choose another policy. Official status should prevent the automatic
marketing-spam inference, but it should not erase independently supported
`scam`, `crypto`, or `unauthorized` evidence. Classify official self-praise
correctly at write time rather than storing a customer testimonial and hiding
it later.

### HE10 and the “Qwen clip” collision

The HE10-oriented Qwen-clip screen found 372 hits (0.18%) from eight accounts
between August 22 and August 25, peaking at 117 posts in one day. Removing clip
numbers and URLs reduces the set to 12 normalized templates, and the ten most
common templates cover 343 posts (92.2%). Only five (1.34%) have a legacy
marketing-spam flag, while 101 (27.2%) received at least one historical
classification signal.

**Decision:** this is not a taxonomy edge. It is a concentrated keyword
collision and spam burst. Add the normalized template/account recurrence to
relevance and unsanctioned diagnostics, retain the source rows, and prevent
them from appearing in normal views. The burst is too material to call a
one-off but too semantically narrow to justify a post type.

### Closed beta, waitlist, invite-only, and early access

Across multilingual limited-access terms, 643 posts (0.31%) mention a closed
or private beta, invite-only access, a waitlist, or early access. Only 166
(0.08% of all branded posts) also contain an obvious action route. Restricting
the screen to closed/private beta finds 303 posts (0.14%), including 75 (0.04%)
with an action route.

**Decision:** keep the narrow rule already proposed. A limited-access post is
an `opportunity` only when it offers the audience a way to apply, request,
register, try, or receive access. Store dates only when supplied and leave an
unknown deadline unknown. The actionable population is too small to warrant a
new label or a solicited/unsolicited scale.

### Prompt-quality edges that do not need taxonomy changes

In the 45-row owner reference, the owner added four `testimonial` labels and
removed six, added and removed one `hands_on_usage` label, removed two
`results_evaluations` labels, and both added and removed one `ideas_requests`
label. In the separate 30-row v27 owner-conformity diagnostic, label F1 was
0.67 for testimonial, 0.67 for results/evaluation, 0.50 for idea/request, and
0.92 for hands-on usage.

**Decision:** tighten the testimonial, target-brand, result/evaluation,
customer-cost versus investor/business, and product-request examples in the
existing prompt. Keep the current hands-on field and boundary. These observed
errors justify prompt calibration, not new post types or product labels.
