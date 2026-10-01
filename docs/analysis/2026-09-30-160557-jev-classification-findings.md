---
title: Jev classification, promotion ownership, and geopolitical attribution — closed evaluation
created: 2026-09-30T16:05:57+09:00
updated_at: 2026-10-01T19:39:45+09:00
timezone: Asia/Tokyo
document_type: evidence-consolidation
status: closed-keep-0731-reconsider-future-jev
branch: experiment/post-interpretation
base_revision: 1edbc3adaa19b370498ef0fbb026319fc676d397
---

# Jev classification, promotion ownership, and geopolitical attribution — closed evaluation

**Final owner decision — October 1:** Keep 0731 for classification. Reconsider
Jev if a newer version establishes a worthwhile improvement. The authoritative
root now contains the [agent closeout and latest scorecard](2026-10-01-193945-jev-classification-closeout.md),
including the completed [political-wording retest](2026-10-01-053425-political-framing-retest/report.md),
integration limits, future evaluation conditions, and parked headline ideas.
The earlier pending/next-test language below is historical, not an instruction
to resume inference. The underlying promotion and geo issues remain open.
Existing evidence and local experimental code were preserved; no model switch,
rollback deployment, new test, commit or push accompanied this closeout.

**Update — 2026-09-30 17:33 JST:** The same multilingual test has now run on 0731. Jev leads the strict score (88.6% versus 78.9%), but 0731's invalid/missing outputs and much lower positive-label recall materially affect that comparison. 0731 produces fewer false geopolitical tags, while missing more real ones. See [section 13](#13-matched-0731-multilingual-results--2026-09-30-1733-jst) and the [full comparison](2026-09-30-074728-0731-multilingual-comparison/report.md). No production switch followed.

**Update — 2026-09-30 16:39 JST:** The larger 117-post full-taxonomy multilingual test is complete and did **not support switching** to Jev. See [section 12](#12-new-results--2026-09-30-1636-jst-full-taxonomy-multilingual-pass-completed) for the results and limitations. The original summary and sections 1–11 below describe the historical 16:05 cutoff and are retained unchanged.

## Plain-English Summary

Jev has done better overall than 0731 on our small, deliberately difficult geopolitical/promotion set. Its direct first-pass result was **21/22 scored decisions across eight posts**. On matching questions, 0731 returned **14/22** with compact labels and **16/22** when also asked for probabilities. This is promising evidence for a larger test, not a measured production accuracy rate or proof that Jev will improve every classification category.

The original failures remain distinct. A model can recognize that a post is promotional but attach that promotion to a model merely mentioned inside another provider's offer. It can also turn criticism of a company into a negative national stance. Asking for an explanation, adding longer instructions, or putting an interpretation step first did not reliably solve these problems in the completed experiments.

Jev supplies decisions over defined options; it does not generate arbitrary company names, quotations, translations, or commentary. The next owner-requested evaluation therefore assumes **another model handles extraction**. Jev's full classification task must be tested in Japanese, Simplified Chinese, Korean, and the next three most frequent languages in the database. That new test is pending at this record's cutoff; no language ranks or results are asserted here.

This file consolidates completed evidence and decisions. It is not an implementation plan, migration approval, instruction to resume old experiments, or claim that any model switch has been deployed. The appendable [ongoing issue record](../issues/2026-09-30-095324-promotion-attribution-and-untracked-company-ongoing-issues.md) retains stable PROMO/GEO issue IDs; its earlier Jev status predates the two newer completed experiments recorded here. Existing reports and receipts remain unchanged.

## 1. The questions we must not collapse into one

| Question | What establishes it | What does not establish it |
| --- | --- | --- |
| Is the post promotional? | Whole-post advocacy, offer, showcase, invitation, or benefit framing | A link, enthusiastic word, or technical specification alone |
| What offering is promoted? | The object of the pitch and its provider, supported by source/context | Every named model, prize, integration, comparison foil, or supported backend |
| Who is promoting it? | Trustworthy, dated author/employer/sponsor relationship evidence | Tone, first-person wording, or absence from our account directory |
| Is it an unwanted campaign? | Reviewed campaign identity/signature, repetition, and exclusion policy | Company mention, follower count, or promotion alone |
| Does it express national meaning? | A national/political claim, framework, or adopted judgment in source/context | Vendor nationality inferred from a company name |
| Does it contain useful information? | Specific source-visible facts, claims, examples, or demonstrated results | Legitimacy of the author or the absence of promotional language |

The owner proposed this conceptual distinction: untracked promotion is done by an untracked brand; advertising/marketing by the brand itself or a co-sponsor; opinion/reaction by a civilian. This is a requested conceptual boundary, **not an already-implemented author-affiliation rule**. An unknown account cannot safely be called civilian, and a partner acknowledgment does not prove sponsorship.

The owner explicitly rejected enforcing one promotion target per post. Genuine co-promotion exists. The useful upstream representation would retain what is promoted, who provides it, and supporting statements, allowing multiple relationships. That principle survives; the earlier specific compartmentalized/target-only implementation was rejected after inspection.

Sources: [ongoing decisions](../issues/2026-09-30-095324-promotion-attribution-and-untracked-company-ongoing-issues.md), [official/staff language review](2026-09-29-143624-account-role-advertising-census/language-findings.md), [deterministic comparison](2026-09-29-145746-promotion-deterministic-comparison/report.md).

## 2. Prompt and interpretation experiments: what changed and what failed

### The long advertising instruction and local rollback

Commit `76bf81dbfda8cd6e4a5a453435c68ebe5e7e9081` replaced the brief advertising definition with instructions to identify the promoted subject and beneficiary; exclude mere mentions, prize/token/spin references, compatibility ingredients, benchmarks, and comparison foils; and permit independently supported tracked/untracked co-promotion. It explicitly named the Token Machine/model-token and B.AI/GLM examples. The addition did not establish a successful ownership fix.

The owner then requested removal of that addition. The experiment worktree restored the complete pre-addition prompt module byte-for-byte and selected content/merge v5 lineage, while preserving compatibility with historical v6 receipts. The restored definition is:

```text
- advertising_marketing: a pitch, call to action, showcase, discount, or promotional launch for this brand. A comparison foil cannot inherit another brand's promotion.
```

This was a **local, undeployed rollback**, not proof that production used v5 content. The later geo production observation actually records content-v6, brand-interpretation-v5, and merge-v6. Historical v6 measurements must not be relabelled as v5 measurements.

The rollback record reports 74 passing software tests and seven PostgreSQL-dependent skips; the combined check was incomplete, not fully green. These are software tests, not 74 semantic model trials. The caller-level prompt and lineage pins passed. Exact history and verification are in the [existing experiment plan](../plans/2026-09-29-014716-experiment-post-interpretation-plan.md), with the literal addition available from `git show 76bf81d -- x_monitor/classifier_0731_prompts.py`.

### Shared upstream interpretation

The [paired experiment](2026-09-29-014716-post-interpretation-experiment/report.md) used 15 fixed posts: seven observed posts, three synthetic ownership controls, and five additional synthetic attribution controls. Both classification arms used the v6 two-role caller; the candidate received a separate model-generated entity/claim/offering/provider interpretation. It was an **additional upstream call**, not just a paragraph moved earlier in the existing prompt.

Two non-verbatim-quote defects blocked ten candidate results under whole-batch admission. A declared six-call follow-up reused the unchanged interpretations while bypassing only quote admission. The strict failures remain failures; the follow-up is diagnostic evidence, not a strict pass.

| Check | Baseline | Strict candidate | Diagnostic candidate |
| --- | ---: | ---: | ---: |
| Valid classifications | 15/15 | 5/15 | 15/15 |
| Tracked-ad decision, ten original cases | 4/10 | 0/10 | 3/10 |
| Complete ownership boundary | 3/10 | 0/10 | 3/10 |
| Untracked-promotion category | 5/10 | 3/10 | 9/10 |
| Direct-ad/co-promotion positive controls | 3/3 | 0/3 | 3/3 |
| Specified broader attribution controls | 4/5 | 2/5 | 5/5 |

The 4/10 versus 3/10 figures mean correct **tracked-brand advertising decisions in ten selected development cases**. They are neither post-wide accuracy nor a database promotion rate. The complete-ownership score additionally checks untracked category and promoted-subject name; its exact name match rejects `B.AI platform` versus `B.AI`, a scoring limitation separate from the advertising mistakes.

Two failure locations were observed:

- Some interpretations correctly identified Token Machine as the provider, but downstream classification still marked Qwen/other prize-model advertising. Better extraction alone was not sufficient in those cases.
- Other interpretations omitted Token Machine, misassigned token-provider roles, or failed to resolve B.AI from a shortened URL plus handle. Valid exact quotations did not guarantee a correct interpretation. No verified shortlink-to-company mapping had been supplied.

The clearest positive change separated GLM praise from a B.AI billing complaint. Exploratory commentary also avoided some unsupported claims of official authorship. But both headline arms changed “is building” into “launches” in one case, and both prose arms sometimes understood ownership correctly when structured labels did not. Literal Japanese probes established no clear ownership improvement and were not independently native-speaker reviewed.

This experiment made 21 calls, estimated model cost US$0.00447816. Extraction plus candidate classification cost about 1.92 times baseline classification and took about 80.5 versus 37.3 serial seconds in this small run. Reuse savings across translation/commentary/headlines were not measured. The cumulative earlier task ledger reached 34/40 calls at that point.

### Target-only follow-up and overriding owner decision

The [target-only experiment](2026-09-29-014716-post-interpretation-experiment/targets-only/report.md) asked for promotion targets without UP/AM/OR or publisher-affiliation classification. It used the same 15 sources, three calls, US$0.00062286, bringing the old task ledger to 37/40. No further calls were implied by the unused three.

- Manual target selection matched 11/12 pre-frozen clear-case expectations; three boundary cases were reported separately.
- Only 4/15 rows obeyed the exact output shape. Eleven added an unrequested field, and two posts had non-verbatim evidence. Combining strict shape with clear-case semantic acceptance gives 3/12, not 11/12.
- It found Token Machine in all six relevant posts without treating prize models as targets, but treated a factual release/hosting report as promotion.
- B.AI/GLM, a comparative recommendation, and praise mixed with another provider's complaint exposed an unresolved advocacy-versus-praise boundary.

The target-only 11/12 is **not comparable** to the prior 4/10 versus 3/10: question, output, rubric, and denominator changed. The owner rejected further pursuit of that compartmentalized version and requested the original prompt. Its report's earlier optimistic conclusion is subordinate to the explicit owner-decision section.

## 3. What the database language studies established

### Official and staff language overlaps with campaign promotion

At `2026-09-29T05:40:11.074531Z`, the known-role inventory had 3,511 posts: 1,833 official-role and 1,678 staff-role, across 52 authors. There were **no community-role account links**. These are recorded relationships, not freshly verified employment or sponsorship.

The language review read 216 full bodies, 122 official-role and 94 staff-role, with available quotes/parents. It selected recent and deterministic-hash examples to cover every author, without selecting on stored classifications. This was qualitative coverage, not a manual census or representative promotion prevalence estimate.

Official accounts promote through launches, benefits, showcases, favorable benchmarks, partner availability, discounts, event invitations, and quoted customer work. Staff often do the same in an informal personal voice. Conversely, support instructions, courtesy replies, criticism of a quoted pitch, and requests for access need not be promotion. “Try,” “we,” emojis, technical detail, and links are not deterministic separators.

Recorded home-brand relationships sometimes looked inconsistent with the post text; they must not make an employee's book, event, or another company's product into promotion of the home brand. The proposed short official/staff-language clarification was discussed but **not applied**. Evidence and source selections: [language findings](2026-09-29-143624-account-role-advertising-census/language-findings.md).

### B.AI: strong campaign signature, not a universal spam test

The [B.AI comparison](2026-09-29-145746-promotion-deterministic-comparison/report.md) identified 7,303 associated posts from 395 author IDs, with fetch cutoff `2026-09-29T05:57:44.654358Z`. It used an ASCII raw-body prefilter plus four recovered decorative-Unicode posts; the attempted universal Unicode scan timed out. It is not exhaustive for every alias, indirect mention, or shortlink-only reference.

The conjunction **explicit B.AI marker + `@justinsuntron` + `#TRONEcoStar`** matched 6,873 posts, 94.1% of that cohort, from 186 authors, and zero official/staff comparison posts. Among non-replies it matched 6,868/7,025, or 97.8%. These are exploratory textual match rates, **not independently labelled spam precision/recall**. The signature is co-occurrence anywhere in the body, not necessarily a footer.

Sixty substantive normalized templates repeated across at least three authors covered 270 B.AI posts. This establishes repeated copy in that subset, not payment, automation, fraud, or lack of information in every remaining post. Requiring substantive text fixed an initial duplicate-rule problem with link-only bodies and short thanks.

Generic filler-language rules failed: two filler families plus a link matched only 3.7% of B.AI posts and collided with unrelated engineering/research posts. A command-line `-ngl` even looked like conversational “not gonna lie.” Neither writing style nor criticism keywords supplied a safe general separator.

Important exceptions include official MiniMax thanks to B.AI for model availability, a protocol-compatibility question, and a DeepGuard ecosystem announcement crediting B.AI for tokens. Some campaign-like posts miss the signature through alternate or misspelled tags. Absence is not proof of legitimacy; presence is not permission to block every post by that author. The short exploratory alias `@BAI` needs identity verification before production use.

An approved registry could save verified entity aliases, exact campaign signatures, supporting posts, exceptions, and the enabled policy. No new registry, daily job, post-fetch filter, or TwitterAPI query exclusion was implemented by these studies. Collection exclusion would avoid initial fetch work; a post-fetch rule would not. Actual provider exclusion syntax and exception behavior were not verified here.

### Followers did not reveal a low-follower shortcut

Stored follower counts, observed `2026-09-29T06:35:59.109217Z`, were available for 386/395 associated accounts. Nine were missing, not zero.

| Followers | Accounts | Associated posts |
| --- | ---: | ---: |
| 0–99 | 16 | 17 |
| 100–999 | 9 | 12 |
| 1,000–4,999 | 50 | 398 |
| 5,000–9,999 | 108 | 1,956 |
| 10,000–49,999 | 179 | 4,345 |
| 50,000–99,999 | 18 | 542 |
| 100,000+ | 6 | 14 |
| Unknown | 9 | 19 |

The known-count median was 10,523.5; the middle 50% was 5,607.5–21,108.5. Accounts with 5,000–49,999 followers supplied 86.3% of posts, while accounts below 1,000 supplied 0.4%. Counts were stored snapshots, not necessarily counts when posted; 101 known counts lacked an observation timestamp. Official/platform accounts occur among high-follower outliers. [Full distribution and narrower signature cohort](2026-09-29-145746-promotion-deterministic-comparison/bai-followers-distribution.md).

### Information content is not the same as spam status

A deterministic 40-post sample from the same B.AI cohort contained: zero posts with primary model tests/substantive primary-project evidence; 11 with model specifications, capability claims, or a compatibility issue; 28 with provider/access/pricing/integration/business-model information; and one generic reaction. The 11 are claims, not fact-checked findings.

A separate ten-post exception-seeking supplement included the DeepGuard project announcement. It must not be pooled into the main denominator. Across the 50 texts no actual measured model test was demonstrated, but there was useful access/ecosystem information. Linked pages/media were not inspected, some parent context was missing, and unique information relative to the rest of the database was not measured. No whole-cohort “X% worthless/spam” result is supported. [Signal review and per-post decisions](2026-09-29-145746-promotion-deterministic-comparison/bai-signal-report.md).

### Other recurring companies and the independent-mention gap

A separate inventory covered 276,737 posts at fetch cutoff `2026-09-29T06:19:29.636718Z`; do not mix this later population into the frozen B.AI denominator.

| Recurring promotion lead | Matching posts | Authors |
| --- | ---: | ---: |
| Xpert Systems | 414 | 1 |
| AINFT | 352 | 81 |
| BTTInferGrid | 148 | 55 |
| ENGY | 190 | 55 |
| SOMA | 122 | 78 |
| CcVibe | 36 | 1 |
| Topview | 402 | 269 |
| Unidentified account-sales footer | 457 | 296 |

These are alias/signature match counts, not reviewed spam counts; rows overlap. AINFT/BTTInferGrid often share TRON campaign markers, which does not establish common legal identity. Only 64 distinct selected posts were read: 63 full bodies and one 4,500-character prefix. OpenCode, OpenRouter, and Mia AI were important frequent-mention counterexamples with useful technical discussion, troubleshooting, and criticism. A company-only registry would miss a campaign without a stable company name.

Storage was not empty, but was not an independent company-mention census:

- `PostBrandMention` points only to tracked brands.
- `BrandDiscoveryCandidate` had 2,229 rows, all pending; `UntrackedBrandPromotionEvidence` had 4,904 rows for 4,324 posts and 2,178 candidates.
- The inspected classification-persistence path returns before writing promoted-subject evidence if no untracked promotion is returned. Discovery evidence in that path depends on the classification it could help improve. Other discovery paths exist.
- B.AI was split across candidates; some candidate alias sets also contained unrelated-looking companies and personal handles. Sharing an author, hashtag, or co-mention does not establish aliases. Those merges were not repaired or explained fully.
- An initial broad `@` extractor reported 402 Xpert-like hits that were actually email domains; a boundary-aware follow-up found zero real `@XpertSystems` mentions.
- All 20,307 non-NULL `posts.entities` values were empty objects, and 256,430 were NULL. Expanded t.co destinations were not present in that standard field; other raw/context fields were not exhaustively audited.

The proposed direction is a cheap bounded incremental mention-observation pass with a checkpoint: preserve spelling/source spans, distinguish handles/domains/emails/names, permit unresolved and multiple entities, aggregate recurrence for review, and save verified aliases once. It remains a proposal, not implemented or benchmarked. [Company findings, storage audit, source counts, and extraction traps](2026-09-29-151842-recurring-company-mentions/report.md).

## 4. Geopolitical diagnosis and historical model evidence

Post [2105081335475757197](https://x.com/PreciousBa82157/status/2105081335475757197) criticizes Anthropic/OpenAI and contrasts GLM; its stored quote also concerns companies and cybersecurity. It does not evaluate China, the US, national groups, or national origin. Expected geo result: no modes, China `none`, US `none`.

The read-only observation at `2026-09-30T00:53:47.495954Z` found brand judgment 124094 already containing `nationalism`, China `pro`, US `anti`; final judgment 124095, current state, and geopolitical edge preserved them. This is a **persisted classification false positive, not a tag invented by the UI**. The confirmed failure boundary is the brand-interpretation output. Company-to-country transfer is the likely explanation, not recovered internal reasoning: the raw batch/rationale was not retained in those records.

The prompt already states that vendor origin, ordinary product praise/criticism, historical analogy, flags, and nationality alone are insufficient. Validators enforce allowed values and stance/mode consistency, not source-grounded national meaning. Stored geo evidence repeats axis/value/fingerprint rather than a supporting passage. An append-only normalization branch cannot explain this sole-mode output from nothing. [Diagnosis, source trace, competing explanations, and saved records](2026-09-30-095520-geo-false-positive-2105081335475757197/report.md).

The historical V4.1 Flash comparison offers context, not a counterfactual answer for this post. On a different September 15 owner-reviewed challenge set, exact geopolitical-mode agreement was 32/42 for V4.1 versus 30/42 for 0731; China stance 37/41 versus 34/41; US stance 37/41 for both. The models used different batch/provider execution shapes, older prompts, and a consumed challenge set. This cannot establish whether V4.1 would make this particular error. [Historical comparison and limits](2026-09-15-200946-u18-v4-0731-five-post-comparison.md).

Software tests using fake responses can establish routing, structural rejection, and persistence behavior. They cannot establish that the model understands company-versus-country meaning. Quote extraction would improve inspectability, but a quotation alone does not prove the attached classification is correct.

## 5. Jev as a targeted second reviewer

The owner separately authorized a bounded review comparison and a 32-call/US$1 ceiling after the earlier prompt-experiment stop. It ended at **20 calls: four 0731 and sixteen Jev**, without automatic retries or app changes. The eight cases contain seven real saved posts and one synthetic co-promotion control.

The same case identities recur in the direct-primary and matched-0731 studies:

| Case | Saved source identity | Decision target | Source language |
| --- | --- | --- | --- |
| G01 | `2105081335475757197`, @PreciousBa82157 | GLM | English |
| G02 | `2100052017993683063`, @sunbh_eth | DeepSeek | English |
| G03 | `2100011791119966665`, @TheWorldCorresp | DeepSeek | English |
| G04 | `2100011731204358249`, @sohfangwei | DeepSeek | Simplified Chinese, with supplied English translation |
| P01 | `2104483144233853085`, @xxyweb3 | GLM | English |
| P02 | `2101798119298277764`, @pogixrp | Qwen | English |
| P03 | `2102569821997346912`, @Alibaba_Qwen | Qwen | English |
| P04 | `u18a-tracked-untracked-co-promotion`, synthetic fixture | DeepSeek | English |

Full verbatim source, supplied translation, saved context, and reference provenance are in the [copied primary cohort](2026-09-30-060237-jev-primary-classifier/cohort.json). The original G04 source had appeared under a MiniMax decision slot; these experiments deliberately target its visibly mentioned DeepSeek. That choice was declared before testing and is not an exact replay of that historical slot.

0731 used the locally restored content-v5/brand-v5 prompts, not production content-v6. It was asked either for ordinary labels or labels plus a short claim and exact source evidence. Such an explanation is generated output, not an internal thought trace; it is not free merely because it arrives in the same call.

The comparison separated:

- A: original labels, Jev review without explanation, eight cases.
- B: explanation-arm labels with explanation shown, four geo cases available.
- C: those **same** B labels with explanation hidden, four geo cases available.

B versus C isolates displaying the explanation. A versus B also changes the upstream labels. Predeclared support thresholds were >=80% approve, <=20% reject, otherwise abstain.

### Original frozen-rubric results

| Measure, 18 geo fields per arm | A | C, explanation hidden | B, explanation shown |
| --- | ---: | ---: | ---: |
| Upstream fields matching original reference | 16/18 | 14/18 | 14/18 |
| Incorrect fields rejected | 0/2 | 3/4 | 2/4 |
| Incorrect fields approved | 0 | 0 | 0 |
| Correct fields held uncertain | 3/16 | 6/14 | 5/14 |
| Correct fields rejected | 0 | 0 | 0 |
| All uncertain fields | 5/18 | 7/18 | 7/18 |

On G02, requesting an explanation changed a correct no-geo result into nationalism/China-mild-pro. The explanation itself invoked “China-associated DeepSeek” while acknowledging no broad national evaluation. Showing it to Jev weakened the nationalism rejection from 10% to 25% support, crossing into abstention. On G04, support for a valid China-anti stance moved from 79% to 81%, a small threshold crossing rather than robust evidence of benefit.

Fresh 0731 correctly returned no geo labels for the original complaint G01 in both arms. Its exact historical wrong assignment was **not** replayed as a Jev candidate. This experiment therefore did not show Jev repairing that exact stored error.

Promotion A was uncertain on all four cases:

| Case | 0731 assignment | Jev support for that assignment | Reference |
| --- | --- | ---: | --- |
| P01 B.AI/GLM | GLM ad | 30% | Not GLM ad |
| P02 Token Machine/Qwen | Qwen ad | 57% | Not Qwen ad |
| P03 official Qwen announcement | No Qwen ad | 26% | Qwen ad |
| P04 synthetic explicit co-promotion | DeepSeek ad | 79% | DeepSeek ad |

These percentages support the **proposed answer**, not always the positive class. In P03, low support for “no Qwen ad” favors advertising. At a later exploratory 50% decision rule, promotion becomes 3/4 correct, with P02 still wrong at 57%; it was never 4/4.

Promotion B/C were unavailable because the explanation response used the wrong structure. Two content decisions also failed the application parser: a nonexistent `@TRONEcostar` quote instead of the source hashtag, and `general` combined with another promotion category. Nothing was repaired or rerun. This is failed experimental input, not proof that every correctly designed explanation approach fails. Missing planned cases are not zero errors.

The parser added nationalism to raw G03's framework + directional China stance; Jev reviewed application-accepted labels. That addition must not be attributed to raw model output. [Complete original review report](2026-09-30-110504-jev-targeted-review-comparison/report.md), [frozen contract](2026-09-30-110504-jev-targeted-review-comparison/contract.md), [partial-comparison deviation](2026-09-30-110504-jev-targeted-review-comparison/partial-comparison.md), [audit](2026-09-30-110504-jev-targeted-review-comparison/audit.json).

### Reporting-reference correction and 50% rescore

After discussion, G03 and G04 reporting expectations changed from absent to present: each attributes geopolitical claims while also advancing an opinion/framework. Reporting, framework, and nationalism can coexist. The correction was frozen before the later Jev-primary run; it did not rewrite the original report or trigger new review calls. These are agent-reviewed reference judgments, not independently adjudicated truth.

Using corrected references for all reused columns, baseline 0731 scored 17/22 (geo 16/18, promotion 1/4), and the saved A review treated as a reversing evaluator at 50% scored 19/22 (geo 16/18, promotion 3/4). Fully correct posts increased from 4/8 to 5/8. That is two more correct fields, about 9.1 percentage points **on this selected set**, not a deployment improvement estimate.

The review still accepted G03 China `mild_pro` at 61% when the strict reference is `pro`, and rejected G04 reporting-present at 33% support when the corrected reference requires it. Merely paying attention to probabilities did not create new reasoning or make all judgments correct. [Corrected comparator scores](2026-09-30-060237-jev-primary-classifier/comparators.json).

## 6. Jev as the primary classifier

The next run asked pinned `jev-1.13.0` directly about the same eight cases, with no 0731 assignments or explanations. Source/context and criteria were frozen. It asked three independent Noul questions for geo modes, two seven-option Choice questions for stances, or one Noul for tracked-brand promotion. Noul used >=50%; Choice used the highest-probability option, not a universal 50% requirement.

| Scored fields, corrected references | Saved 0731 baseline | Saved 0731 + Jev review at 50% | Jev primary |
| --- | ---: | ---: | ---: |
| Geo | 16/18 | 16/18 | 18/18 |
| Promotion | 1/4 | 3/4 | 3/4 |
| Combined | 17/22 | 19/22 | **21/22** |
| Posts with every scored field correct | 4/8 | 5/8 | **7/8** |

The prior 0731 baseline classified additional axes; this table was not an equal-prompt model benchmark. It motivated the matched test below.

| Case | Reporting P(yes) | Framework P(yes) | Nationalism P(yes) | China stance | US stance |
| --- | ---: | ---: | ---: | --- | --- |
| G01 original GLM/company-criticism complaint | 6% | 7% | 4% | none, 99% | none, 100% |
| G02 DeepSeek praise/competitor criticism | 27% | 19% | 10% | none, 100% | none, 100% |
| G03 Chinese-innovation defense | 76% | 92% | 86% | pro, 96% | Invalid; already unscored |
| G04 Chinese-system criticism | 78% | 95% | 94% | anti, 99% | anti, 83%; unscored |

The only scored error was P02, Qwen advertising at 51%. P01 was correctly negative at 25%; P03 positive at 94%; synthetic P04 positive at 76%. No cutoff was changed after that result. G03's `pro`/`mild_pro` intensity was declared subjective before inference; excluding it gives 20/21 overall and 17/17 geo.

### Output validity matters separately

G03's unscored US Choice returned `anti`, despite assigning 31% to anti and 32% to pro. This violated the documented selected-maximum contract. The initial runner stopped after three calls. A saved continuation fixed field-local validation before the remaining five unsubmitted calls: retain invalid output, never repair it, count invalid scored answers as failures, and never resubmit completed cases. Neither the scored denominator nor questions/references changed.

There were 23/24 valid answers, seven wholly valid responses out of eight, and all 22 scored answers valid. The two US stances on G03/G04 had been excluded before both experiments; this was not convenient post-result exclusion. We have not adjudicated them as correct. Production must explicitly handle label/distribution inconsistency rather than silently trusting either.

Eight physical requests, zero retries, US$0.000485814 estimated model cost, median local HTTPS time 0.260 seconds. [Report](2026-09-30-060237-jev-primary-classifier/report.md), [contract](2026-09-30-060237-jev-primary-classifier/contract.md), [exact requests](2026-09-30-060237-jev-primary-classifier/requests.json), [scores](2026-09-30-060237-jev-primary-classifier/scores.json), [continuation](2026-09-30-060237-jev-primary-classifier/continuation.md).

## 7. Matched 0731 questions, with and without probabilities

To test whether Jev's question structure alone explained the result, 0731 received exactly the saved Jev `state` and `questions` objects, without prior answers, explanations, case IDs, or reference labels. Two independent arms differed only in the requested output format:

- A: compact boolean/option labels, no probabilities or explanations.
- B: labels plus complete numeric probability distributions.

Both used direct DeepInfra `deepseek-ai/DeepSeek-V4-Flash-0731`, temperature 1, top_p 1, seed 42, `reasoning_effort: none`, max_tokens 1024. Calls were sequential, alternating arm order by case. Sixteen physical calls, no retries or tuning, all HTTP 200/normal completion; all 48 answers valid, including four deliberately unscored fields. Provider receipts reported zero reasoning tokens, which is not proof that the model performs no internal processing.

| Version | Geo fields | Promotion fields | Combined | Posts fully correct on scored fields |
| --- | ---: | ---: | ---: | ---: |
| 0731 A, labels only | 12/18 | 2/4 | **14/22, 63.6%** | 3/8 |
| 0731 B, probabilities | 12/18 | 4/4 | **16/22, 72.7%** | 5/8 |
| Saved Jev primary | 18/18 | 3/4 | **21/22, 95.5%** | 7/8 |

Only two scored labels differed between A/B: P01 and P02 were wrong positive advertising in A and correct negative in B. B's advertising probabilities were 11%, 10%, 90%, and 60% for P01–P04. Thus B got the promotion case Jev missed. This single paired run cannot separate a causal benefit of requesting probabilities from ordinary generation variation.

The same six geo errors occurred in both 0731 arms:

| Incorrect B judgment | Selected-answer estimate | Reference |
| --- | ---: | --- |
| G02 China pro | 60% | none |
| G02 framework present | 80% | absent |
| G02 nationalism present | 75% | absent |
| G02 US anti | 70% | none |
| G03 reporting absent | 90% | present |
| G04 reporting absent | 90% | present |

0731 can produce valid, self-consistent percentages. These are **model-written estimates**, not validated correctness probabilities or next-token log probabilities. The errors at 60–90% show why a high value is not a guarantee. The sample does not establish a calibration curve, reliable fallback threshold, or general overconfidence rate. Separate A/B arms keep the confidence request from silently changing the primary comparison conditions.

The matched wording did not erase Jev's observed advantage overall. It still does not isolate Jev's training/weights from its decision-processing interface. 0731 generates one joint text response, whereas Jev answers through native typed decisions. The compact 0731 result also differs from the prior full-taxonomy 17/22 baseline; those are different request designs, not interchangeable repeats. [Complete matched report](2026-09-30-063633-0731-matched-primary-comparison/report.md), [contract](2026-09-30-063633-0731-matched-primary-comparison/contract.md), [exact requests](2026-09-30-063633-0731-matched-primary-comparison/requests.json), [scores and accounting](2026-09-30-063633-0731-matched-primary-comparison/scores.json).

## 8. Cost, speed, output structure, and confidence: settled versus unproven

### What the completed runs measured

| Run/arm | Physical calls | Input tokens | Output tokens | Model-cost estimate | Timing observation |
| --- | ---: | ---: | ---: | ---: | --- |
| Original review: 0731 ordinary arm | 2 | 9,419 | 1,002 | US$0.00073398 | 13.09 s summed serial response time |
| Original review: 0731 explanation arm | 2 | 9,831 | 3,884 | US$0.00126594 | 57.26 s summed serial response time |
| Original review: all Jev arms | 16 | 33,400 | See receipts | US$0.00140280 | 0.255 s median local request |
| Jev primary | 8 | 11,567 | 928 | US$0.000485814 | 0.260 s median local request |
| Matched 0731 A | 8 | 9,335 | 188 | US$0.00046722 | 1.440 s median Render request |
| Matched 0731 B | 8 | 9,983 | 891 | US$0.00064416 | 2.062 s median Render request |

The original review total was US$0.00340272; the matched 0731 total was US$0.00111138. The scopes and old 37/40-call ledger are separate; unused allowance never implied another run. DeepInfra costs are returned estimates, not invoices. Jev costs use its verified-at-run-time US$0.042/M input price with output free. Render compute is excluded. DeepInfra's recorded standard prices were US$0.06/M input, US$0.18/M output, and US$0.015/M cached input.

0731 A had 2,816 cached input tokens, B 2,560. Compact A cost slightly **less** than Jev in these observations. The proposed Jev output-token advantage can largely disappear when the alternative only emits tiny answers. B emitted 703 more output tokens than A and needed 648 additional input tokens for format guidance. Explanation output was also demonstrably not free.

Observed Jev times were lower, but Jev ran from the local host and 0731 from Render, with different network, cache, and warm conditions. These are not controlled speed benchmarks. One request's multiple questions are not equivalent to repeated remote calls, and conventional 0731 can also answer multiple questions against one supplied source. Reusing an input prefix may obtain cache savings; it does not prove reuse of a prior semantic decision or remove the need to evaluate a different question.

### What is structurally different

TypeSafe's saved documentation describes Jev as natural-language decision-making over supplied `state` and predefined questions. Native outputs are **Noul** (yes probability), **Choice** (selected option, distribution, and confidence), and **Score** (a configured scale). It is not limited to bare percentages, but it does not generate arbitrary prose, code, or reasoning explanations. Code consumes and combines decisions. Vendor documentation describes questions as independently/parallel evaluated; this is a vendor mechanism claim, not an internal implementation measurement made by our experiments.

For a trivial `ABc` source, both systems can answer “all uppercase?” and “alphabetical order?” in one request. Jev's proposed distinction is specialized decision evaluation instead of generating the answer text; it is **not** reading `ABc` once while 0731 must read it twice. There is no demonstrated universal multiplier from asking ten questions, and extra question text still costs input tokens.

Noul's probability is not degree/intensity of the property. Choice's `confidence` summarizes how concentrated the whole distribution is; it is not interchangeable with the probability of the winning option. A seven-option winner can be selected below 50%. Every reported percentage must identify whether it is P(label present), support for a proposed answer, a selected-option probability, or distribution confidence.

TypeSafe claims training aimed at calibrated decisions. Calibration means frequencies across groups of predictions agree with the stated probabilities; neither that claim nor these eight cases validates calibration for this application's categories/languages. We cannot conclude that native Jev numbers are reliable merely because 0731's are generated text. Nor can we attribute the observed accuracy gap entirely to “better reasoning” or entirely to interface structure.

Saved vendor sources: [System One](../external_vendors/typesafe_ai/concepts/system-one.md), [models/pricing/language support](../external_vendors/typesafe_ai/models.md), [Choice](../external_vendors/typesafe_ai/primitives/choice.md), [Noul](../external_vendors/typesafe_ai/primitives/noul.md), [confidence](../external_vendors/typesafe_ai/confidence.md). These are dated copies; the completed-run contracts record the official URLs checked before inference. No new network call was made to create this consolidation.

## 9. What replacing classification would and would not replace

Repository configuration inspected at the recorded worktree revision and existing local changes:

| Responsibility | Configured route | Consequence of a classification-only Jev switch |
| --- | --- | --- |
| Main post/brand categorical classification | DeepInfra 0731 | Candidate replacement; full taxonomy still needs evaluation |
| Language detection and literal translation | DeepInfra Gemma 4 31B turbo | Separate role; no automatic model change |
| Post commentary/synthesis | DeepInfra Gemma 4 31B turbo | Separate role; no automatic model change |
| Headline generation | DeepInfra 0731 | Separate route; not removed by classifier replacement |
| Open-ended promoted-subject extraction | Currently in the classification content response | Needs code/another model if Jev owns decisions |

Sources: [model configuration](../../config.yaml), [two-role prompt/output contract](../../x_monitor/classifier_0731_prompts.py), [synthesis caller and source context](../../monitor/post_synthesis.py), [synthesis fingerprint](../../monitor/post_artifacts.py), [generative synthesis implementation](../../x_monitor/synthesis.py). Configuration is not fresh verification of every deployed environment override.

The current content role returns outcome, post types, audience topics, post-level untracked-promotion categories, and freeform `promoted_subjects` with name, handle, domain, account_handle, and exact evidence. Brand interpretation supplies product labels, sentiment, geo modes, and China/US stances. The classifier is not only a two-question promotion/geo service.

Jev can decide among supplied candidates, but its native decision contract does not discover arbitrary company-name/evidence strings as freeform output. Another extractor could supply those candidates/evidence; code can normalize and validate known identifiers. Neither a separate extractor nor a trustworthy evidence interface was implemented by these diagnostic runs. The owner's new test explicitly adopts this separation as an assumption, without yet selecting its extraction model.

The current separate synthesis context is original source, stored quote, and local parent text. Its fingerprint does not contain classifier labels. Changing the classifier therefore does not itself change or invalidate that commentary input. Translation still matters if the classifier consumes an English translation. Headlines/filtering/selection can be affected by changed labels even when their generative model remains unchanged. Do not imply “unchanged model” means every downstream product result is unaffected.

There is an existing [Jev rare-types gate](../../x_monitor/jev_decisions.py), separately configured under `discovery.rare_types` with committed `enabled: false`. It asks discovery questions about roles, jobs, events, opportunities, releases, and junk. It is not an installed general-classification second opinion or automatic geo/promotion reversal mechanism. Environment activation must be checked separately before describing live use. It provides existing transport concepts, not proof that a complete classifier switch is merely a model-name edit.

A future integration must map typed outputs to the existing taxonomy, represent none/unknown/unavailable properly, validate cross-field consistency, preserve source/model/prompt provenance, and decide timeout/invalid-response behavior. 0731 fallback is optional, not inherently required after every Jev answer. The examples do not establish that 0731 always fixes Jev's uncertain cases. Existing stored classifications remain until explicitly reprocessed; this discussion did not authorize a database-wide reclassification or deployment.

## 10. Rejected shortcuts and unresolved questions

| Hypothesis or shortcut | What we learned |
| --- | --- |
| A longer advertising definition solves ownership | It did not establish success; owner removed it locally. |
| One post must have only one promoted party | Rejected; explicit co-promotion must remain possible. |
| An upstream interpretation automatically fixes labels | Not in the first run: extraction and label application failed separately. |
| Exact quotations prove a correct interpretation | False in observed cases; quote validity and semantic correctness differ. |
| Official/staff tone identifies affiliation | Wording overlaps with civilian/campaign posts; relationships need evidence. |
| Frequent mentions, B.AI mentions, or low followers identify all spam | Unsupported; useful exceptions, distinct campaigns, and substantial mid-follower volume exist. |
| Existing discovery aliases are verified identities | Unsupported; split entities and unrelated-looking merged aliases were observed. |
| Geo false positive is just a rendering bug | Stored brand judgment already contained the wrong labels. |
| Asking for an explanation exposes the original internal reasoning for free | It generates a new explanation, costs output, may change labels, and may be invalid. |
| Explanation-visible Jev review is necessarily better | Not in the completed geo comparison; promotion comparison unavailable. |
| Jev had four correct promotion reviews at 50% | Correction: three of four; P02 remained wrong at 57%. |
| The original reporting-absence references were definitive | Corrected for G03/G04; preserve both historical and corrected scores. |
| High confidence means safe automatic correctness | Both numerical uncertainty and confident errors occurred; thresholds unvalidated. |
| Jev can replace every generative call | No; extraction, translation, commentary, and headlines need separate handling. |
| Jev necessarily saves model cost against compact 0731 | Not shown; compact 0731 A cost slightly less in these observations. |
| Matching questions proves the cause of Jev's advantage | It removes one wording confound, not training/interface/sampling differences. |

Still unresolved: the full taxonomy's per-category quality; multilingual accuracy; independent calibration and useful fallback thresholds; positive-label recall versus easy negative counts; relationship between native-language and translated inputs; extraction quality/identity resolution and its effect on labels; provider-contract failure rates; and operational cost/latency with the full question set, extraction, retries, and any fallback included.

## 11. Latest owner direction: next full-taxonomy multilingual test

The owner now requests a full Jev classification test, specifically assuming **some other model handles extraction**, in Japanese (`jp` in the request, canonical language code `ja`), Simplified Chinese (`zhcn`, corresponding normalized source-language variants must be inspected), Korean (`ko`), and **the next three most frequent database languages** after those selections.

At this record's cutoff:

- The new full-taxonomy experiment has not run. No language ranking, new cohort, accuracy, or spend result is implied by this file.
- The three additional languages must come from an explicit current database population/counting rule, not guesses or UI-locale counts. Unknown/detected-language statuses and Chinese-script normalization need to be disclosed.
- The next frozen contract must distinguish classification supplied with an extractor's output from judging extraction itself. Human-checked candidate/evidence assistance, if used, must be declared; it cannot masquerade as an end-to-end deployed pipeline.
- Original source/context must remain available, and extraction must not smuggle reference classifications into Jev inputs. Missing affiliations, unresolved identities, absent context, and candidate coverage remain real limitations.
- Full coverage means the supported classification axes, not only promotion and geopolitics. Report field counts, source-post counts, complete-output correctness, per-language/per-category results, invalid/missing outputs, and minority/positive labels separately.
- The original 22 checks are correlated fields from eight repeatedly inspected posts, seven real plus one synthetic. Reusing them can protect known boundaries but cannot supply an unseen multilingual accuracy estimate.
- TypeSafe's documentation says English is its strongest language and other languages, including CJK, are not handled equally well. The previous single Chinese source with supplied English translation did not establish Japanese, Chinese-native, or Korean classification quality.
- Freeze source/cohort/definitions/reference judgments/output mapping/thresholds and an iteration/spend ceiling before inference. Do not tune these after outcomes to improve the headline score. Report uncertain references and failures, not only scored successes.

The main agent owns that separate authorized evaluation and its artifacts. This record does not prescribe a new implementation plan, revive the stopped 37/40-call task, require every future result to be reviewed by 0731, or authorize an application model switch.

## Record verification and boundary

This consolidation used saved reports, contracts, score artifacts, local source/configuration, and the exact Git diff for the advertising addition. It made no new database, X-provider, model, or vendor-network calls. No app/config/test/receipt, existing report, issue record, or other agent's document was modified; no commit, push, deployment, scheduler change, or software test was run.

The repository had four pre-existing modified application/test files at the start of this record: `tests/test_u18_runtime_0731.py`, `tests/test_u18a_v4_classification_persistence.py`, `x_monitor/attribution.py`, and `x_monitor/classifier_0731_prompts.py`. They remained outside this documentation task. The local evidence/document skills guided separation of measured findings from proposals and prevented treating historical prompts, role metadata, or stored classifications as live truth.

The completed document was read back; all 40 local Markdown links resolve. Whitespace checks pass for the tracked diff and this new file. The four protected application/test file hashes match the preceding experiment's frozen manifest.

## 12. New results — 2026-09-30 16:36 JST: full-taxonomy multilingual pass completed

This is a dated continuation of the record, not a change to what was known at the original 16:05 cutoff. Section 11's pending experiment has now completed. The initial eight-case findings remain historical evidence; they are not a sufficient basis for replacing the application classifier in light of this broader result.

### Main result and its meaning

On **117 real posts and 38 categorical fields per post**, the original-text Jev arm agreed with the preregistered reference on **3,941/4,446 fields (88.6%)**, but on **every field for only 2/117 posts**. Across binary positive labels, precision was **57.6%**, recall **78.3%**, and F1 **66.4%**. Precision here means the fraction of positive labels Jev assigned that the reference also assigned; recall is the fraction of reference positives Jev recovered. Numerous correct negative answers inflate field agreement, so 88.6% alone gives an incomplete picture.

These are agreements with the main agent's source-reviewed judgments, written before model calls, **not independent human ground truth or production accuracy**. Some class boundaries remain debatable. The selection balances languages and deliberately seeks category coverage, rather than sampling the whole database in its natural proportions. The wider task, cases, and question set also differ from the earlier 21/22 study; their percentages are not interchangeable measurements of one fixed test.

The completed run did not establish a safe switch. In particular, it showed extensive over-assignment of geopolitical labels and weak precision for tracked-brand advertising—the two original problem areas. No threshold tuning, reference rewriting, model replacement, or database reclassification followed from these scores.

Evidence: [full multilingual report](2026-09-30-070427-jev-multilingual-classification/report.md), [frozen contract](2026-09-30-070427-jev-multilingual-classification/contract.md), [scores and probabilities](2026-09-30-070427-jev-multilingual-classification/scores.json).

### Language selection and per-language results

The read-only all-date census observed **279,892 posts at 2026-09-30 07:06:05 UTC**, preferring `lang_detected` over provider `lang`. After excluding Japanese, all Chinese variants, Korean, and non-language codes, the next three language buckets were **English 197,854; Spanish 4,503; Turkish 2,226**. Japanese had 21,887, explicit Simplified Chinese `zh-hans` 14,637, and Korean 2,084. An additional 11,061 generic `zh` posts were not assumed to be Simplified Chinese.

The initial selection had 120 posts: 12 deterministic natural-sample posts and eight category-focused posts per language. Before inference, source review excluded one Indonesian post stored as Simplified Chinese, one Portuguese post stored as Spanish, and one non-Turkish interjection stored as Turkish. These exclusions are not passes; no replacement sampling occurred after results. Eligibility also required nonempty source of at most 12,000 characters and a stored non-sentinel brand association.

| Language | Posts | Field agreement | Entire post agrees | Positive precision | Positive recall | Positive F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| English | 20 | 664/760, 87.4% | 1/20 | 54.5% | 80.6% | 65.0% |
| Spanish | 19 | 648/722, 89.8% | 0/19 | 59.4% | 80.0% | 68.2% |
| Japanese | 20 | 663/760, 87.2% | 0/20 | 52.7% | 83.0% | 64.5% |
| Korean | 20 | 671/760, 88.3% | 0/20 | 65.5% | 69.8% | 67.6% |
| Turkish | 19 | 657/722, 91.0% | 1/19 | 55.7% | 83.1% | 66.7% |
| Simplified Chinese | 19 | 638/722, 88.4% | 0/19 | 60.2% | 76.3% | 67.3% |

The 69 natural-sample posts reached 89.9% field agreement, 2/69 entire posts, positive precision 58.3%, and recall 75.4%. The 48 coverage-seeking posts reached 86.8%, 0/48 entire posts, precision 56.9%, and recall 81.7%. English did not clearly outperform the other languages on these selected cases; this does not establish equal language capability. Sources and quotes can be mixed-language, and per-language samples are small.

### The two original failure areas did not hold up across the broader sample

“False positive” and “false negative” below mean disagreement with the frozen agent reference, not independently settled truth for every ambiguous case.

| Label | Reference positives | Correct positive assignments | Extra positive assignments | Missed positives | Positive precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Geopolitical reporting | 13 | 13 | 56 | 0 | 18.8% | 100.0% |
| Geopolitical framework | 9 | 8 | 74 | 1 | 9.8% | 88.9% |
| Nationalism | 5 | 3 | 6 | 2 | 33.3% | 60.0% |
| Tracked-brand advertising/marketing | 8 | 6 | 13 | 2 | 31.6% | 75.0% |

Taken together, geopolitical mode fields had **212/351 agreement (60.4%)**, exact geo-family agreement on **32/117 posts**, positive precision **15.0%**, and recall **88.9%**. Jev found many intended positives but applied reporting/framework to many additional posts. This broader overcalling is not consistent with treating the earlier 18/18 geo result as a reliable general capability estimate.

Untracked-promotion labels had 540/585 field agreement (92.3%) but positive precision only 34.6% and recall 62.1%. Specific problems included eight extra spam assignments, alongside one correctly detected reference-positive spam case. There were 11 unauthorized assignments and two scam assignments, with zero reference positives for either category. With no reference-positive scam or unauthorized examples, recall for those categories is **unmeasured**, not perfect; the study cannot certify their detection reliability.

Other notable boundaries: sentiment agreement was 77/117 (65.8%); factual/news reporting recovered 25 of 46 reference positives, missing 21; evals/benchmarks topic recovered 16 of 30, missing 14. Some sparse categories performed well in this set, but two correct job-listing positives do not establish general job-classification reliability. The full per-label table and disagreements remain in the [report](2026-09-30-070427-jev-multilingual-classification/report.md), [disagreement records](2026-09-30-070427-jev-multilingual-classification/disagreements.json), and [per-case results](2026-09-30-070427-jev-multilingual-classification/case-results.md).

### Existing English translations made essentially no aggregate difference

Sixty-eight non-English posts had a distinct stored English translation and received a second call with that translation added. On **exactly those paired posts**, original-text agreement was **2,271/2,584 (87.9%)** and translation-assisted agreement **2,272/2,584 (87.9%)**: one additional matching field in aggregate. Positive F1 changed from **65.3% to 65.8%**.

The per-language direction varied: Korean improved from 467/532 to 474/532 fields, Japanese from 491/570 to 493/570, and Turkish from 346/380 to 347/380; Spanish fell from 364/418 to 360/418 and Simplified Chinese from 603/684 to 598/684. No broad language-routing conclusion follows from these small differences.

The arm added saved translation while retaining original source, quote, and parent text; it did not translate quote/parent context or replace the original. Some saved translations are summaries rather than full literal translations. No new translation was generated or repaired. With one call per arm and no English duplicate-call control, this cannot separate translation effects from ordinary model variability or measure how high-quality fresh translation would perform.

### Syntactic validity did not ensure consistent answers

Every returned field was structurally valid in this run; none had the earlier Choice/maximum-probability defect. Nevertheless, **34/185 responses** had a cross-answer consistency issue or extra output field. The recorded issue counts overlap:

- 31 responses combined missing context with assessed scalar answers.
- 14 combined missing context with target-specific label memberships.
- Eight combined exclusive `general` promotion with specific promotion categories.

Raw answers were never repaired or silently cleared to improve scores. This illustrates a practical consequence of independent questions: valid individual outputs can conflict when composed. A future application adapter still needs explicit rules for outcome, none/unavailable, mutually exclusive values, errors, and retry/pending states.

Selected-answer probability bins were descriptive, not calibrated thresholds: agreement was 179/352 below 60%, 611/859 in the 60–80% bin, 802/858 in the 80–90% bin, and 2,349/2,377 in the 90–100% bin. The highest bin contains many easy negatives as well as 28 disagreements. It does not independently establish a safe fallback policy. Choice's distribution-sharpness `confidence` remains a separate quantity.

Three reference uncertainties were declared before inference: Meta-company versus Llama attribution, China-stance intensity, and a national-origin product generalization. Excluding only those specified fields changes original-text agreement to 3,914/4,407 (88.8%), not a materially different result. Other subjective boundaries remain. Strict results stay primary, and no after-the-fact exclusions were added.

### The extraction assumption was respected, but extraction itself remains untested

Jev returned **categorical decisions and probabilities only**. A separate future extractor would handle arbitrary promoted-company names, handles/domains, exact supporting passages, and detailed job/event/personnel records. This run did not call or score an extractor, measure extraction cost, test execution ordering, or measure extractor/classifier consistency.

The classifier input included one selected candidate brand per post, known account facts, all 49 tracked brands and curated aliases, and source-matched names/repository IDs from a 1,804-product catalog. It contained **no manually corrected promotion target, reference label, or previous model assignment**. Existing labels helped select coverage examples only. Jev still had to interpret who/what the post concerned; delegating freeform extraction output did not eliminate that reasoning task.

Only one selected author had a known official relationship. Consequently this is not an adequate test of official/staff/community distinctions or the owner's prospective affiliation-dependent UP/AM/OR rule. Brand discovery, candidate completeness, historical affiliation correctness, and every-brand-per-post coverage were also outside the measured scope. This was a compact-input classification diagnostic, not the unchanged full production caller or an end-to-end extraction-plus-classification pipeline.

### Completed execution and unchanged application state

- **185 physical Jev calls:** 117 original-text, 68 translation-assisted; sequential, one frozen pass, no retries. Model `jev-1.13.0`.
- **2,900,629 input tokens; 170,416 output tokens.** Estimated model cost **US$0.121826418**, below the US$0.50 ceiling, using the checked US$0.042/M input price with output unbilled. This is not an invoice.
- Median local HTTPS request time **0.333 seconds**, range 0.288–0.623. No matched 0731 full-taxonomy cost/speed run or production load/throughput test occurred.
- Four read-only database invocations, including the preserved first-selection SQL syntax error. No model retry was caused by that pre-inference collection repair.
- Frozen source/question/reference/runner hashes, request/response counts, cost reconciliation, and protected application/test hashes were checked.
- No application edits, model switch, database write, live X retrieval, new translation, extractor call, 0731 call, deployment, or scheduler mutation occurred in this run. Translation/commentary remain separately configured for Gemma; application classification and headlines are unchanged.

Supporting artifacts: [frozen scope](2026-09-30-070427-jev-multilingual-classification/scope.md), [hash manifest](2026-09-30-070427-jev-multilingual-classification/frozen.json), [questions](2026-09-30-070427-jev-multilingual-classification/questions.py), [exact requests](2026-09-30-070427-jev-multilingual-classification/requests.json), [source cohort](2026-09-30-070427-jev-multilingual-classification/cohort.json), [pre-inference reference judgments](2026-09-30-070427-jev-multilingual-classification/reference_rows.json), [raw receipts](2026-09-30-070427-jev-multilingual-classification/receipts/).

This append-only documentation update made no new provider/database calls and changed only this findings file. The main agent retains ownership of example-level interpretation in the linked experiment report. No additional inference or migration is authorized by recording these results.

## 13. Matched 0731 multilingual results — 2026-09-30 17:33 JST

The owner requested “run same test on 0731.” A single completed 185-call pass used the exact prior Jev `state` and `questions` objects, 117 original posts, 68 stored-English pairs, 38 fields, reference answers, 50% binary cutoff, maximum-probability Choice mapping, and original sensitivity rules. Independent JSON checks found zero input/ID mismatches. Jev was not rerun; no new database or X calls occurred.

0731 used `deepseek-ai/DeepSeek-V4-Flash-0731` on direct DeepInfra with the existing classifier profile: temperature 1, top_p 1, seed 42, reasoning_effort none, standard tier. The model-specific wrapper was the earlier matched test's `B_probabilities` contract, requesting compact labels plus full self-reported probability distributions. Output allowance was 4,096 tokens, fixed before inference for the larger question set. There was no labels-only arm, extraction call, revised question wording, JSON-mode decoding, retry, or production prompt change.

| Original-arm metric | Jev | 0731 |
| --- | --- | --- |
| Strict field agreement | 3,941/4,446, 88.6% | 3,507/4,446, 78.9% |
| Entire 38-field post agrees | 2/117 | 2/117 |
| Positive precision | 57.6% | 74.7% |
| Positive recall | 78.3% | 32.5% |
| Positive F1 | 66.4% | 45.3% |
| Invalid/missing fields | 0 | 499 |

Per-language strict agreement, Jev → 0731: Japanese 87.2% → 79.5%; Simplified Chinese 88.4% → 78.3%; Korean 88.3% → 78.4%; English 87.4% → 74.5%; Spanish 89.8% → 80.7%; Turkish 91.0% → 82.1%. These remain small, balanced and coverage-seeking samples, not population accuracy or a reliable ranking of language ability.

### Do not collapse output failures into a pure reasoning verdict

The 939 original-arm 0731 failures comprise **499 invalid/missing outputs and 440 valid disagreements**. Invalid fields affected 23/117 original responses and 9/68 translated responses. Across both arms, eight responses had malformed JSON, six had empty answer maps, and four used string booleans instead of actual JSON booleans; another 18 fields failed probability-format/label-consistency checks. All 185 provider responses were HTTP 200 with normal `stop` completion, so neither truncation nor a transport failure explains these defects.

Per the frozen contract, no JSON was repaired, strings coerced, missing labels invented or failed fields dropped. A supplemental score ignoring only probability defects on already well-typed labels raises original agreement to 3,516/4,446 (79.1%); this is not a general readable-answer recovery. The full probability-output delivery is materially less robust than Jev's native output in this run. That does not establish the deployed 0731 prompt's accuracy or isolate underlying reasoning from the changed interface.

0731 also genuinely assigns fewer positive tags: 233 valid positive memberships, 174 supported, versus Jev's 727 and 419. Of 535 reference positives, 0731 misses 361 versus Jev's 116. Those 361 misses include 292 explicit valid rejections and 69 invalid/missing fields. Thus conservative output is not merely a formatting artifact.

### Original geo and promotion problems

- Geo modes: 0731 records 10 supported tags, 14 unsupported tags and 17 missed positives; Jev records 24, 136 and three. On the plain DeepSeek-release question (`en_07`), 0731 correctly rejects every geo mode and accepts questions/requests. Its reduction in overcalling comes with substantially worse positive recall.
- Tracked-brand advertising: 0731 records zero supported positives, three unsupported positives and eight misses; Jev records six, 13 and two. Seven 0731 misses are explicit `p_yes=0` rejections, one is invalid JSON. Some expected advertising boundaries remain subjective; the strict scores are preserved.
- B.AI provider promotions `zh_cn_14` and `en_15`: 0731 assigns DeepSeek advertising 0% and 20%, correctly below threshold, versus Jev's 76% and 83%. But 0731 also misses `en_15`'s untracked general promotion. It rejects the WorkBuddy offer's untracked general promotion (`en_12`) at 2%, which Jev correctly accepts at 76%. Promotion ownership is therefore not solved by this lower positive rate.
- Self-reported certainty: 0731 gives exactly 100% selected-answer probability to 3,118 valid original-arm decisions; 333 disagree with the reference. These percentages are not safe routing guarantees or interchangeable with native decision probabilities.

### Translation, cost and timing

On the same 68 paired posts, 0731 changes from 2,058/2,584 agreement (79.6%) without English to 2,130/2,584 (82.4%) with English; positive F1 changes 45.7% → 51.7%. Invalid fields also fall 270 → 187 in that paired comparison. The observed improvement mixes output validity, classification differences and run variability; it does not isolate a translation-comprehension effect. Jev's corresponding agreement was 2,271 → 2,272.

0731 used 2,406,620 input tokens, including 1,400,832 reported cached tokens, and 185,238 output tokens. Provider-estimated model spend totals **US$0.1147026**, compared with Jev's **US$0.121826418**. Render compute is excluded. Median observed request time was **9.912 seconds** for 0731 versus **0.333 seconds** for Jev. Different hosts, times, cache state and service load prevent treating this as a controlled speed benchmark. This probability-output test also does not establish cost against a compact labels-only 0731 response.

The isolated Render job `job-dauc1alg1s2s73cbc27g` succeeded from 07:56:26 to 08:28:23 UTC. All 185 starts/responses and costs reconcile; zero retries. Protected application/test and frozen evidence hashes match. The staging scheduler remained suspended; postflight found no active one-off job. A lossless pre-submission compression adjustment changed only transport encoding, not model inputs. No production model/configuration, database, scheduler or deployment was changed.

Evidence: [comparison report](2026-09-30-074728-0731-multilingual-comparison/report.md), [frozen contract](2026-09-30-074728-0731-multilingual-comparison/contract.md), [scores/probabilities](2026-09-30-074728-0731-multilingual-comparison/scores.json), [paired model decisions](2026-09-30-074728-0731-multilingual-comparison/model-pairs.json), [output-defect audit](2026-09-30-074728-0731-multilingual-comparison/output-audit.json), [per-case results](2026-09-30-074728-0731-multilingual-comparison/case-results.md), [postflight](2026-09-30-074728-0731-multilingual-comparison/render-postflight.json).

This matched result favors Jev's delivered score, not an unconditional migration. Jev still overcalls geopolitical modes and misattributes promotions; 0731's same-question probability wrapper misses many positives and has output defects. Extraction quality/cost, native production-prompt quality, independent reference adjudication and safe probability thresholds remain unmeasured. The completed test grants no further inference, model switch or reclassification authority.
