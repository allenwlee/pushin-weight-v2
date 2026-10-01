---
title: Promotion attribution and untracked-company campaigns — ongoing issues
created: 2026-09-30
updated: 2026-10-01
timezone: Asia/Tokyo
status: open
document_type: ongoing-issue-record
branch: experiment/post-interpretation
---

# Promotion attribution and untracked-company campaigns — ongoing issues

## Summary

We are sometimes assigning advertising/marketing to a tracked model brand when a post is selling another company's service and uses that model as a selling point. B.AI is the main observed example. The unresolved problem is not simply recognizing promotional language: it is distinguishing what is promoted, who is doing the promotion, and whether the post belongs to an unwanted campaign.

Existing database analysis found a recognizable B.AI/TRON campaign and several other recurring promotions. It also found useful B.AI-associated posts, including a compatibility question, official partner acknowledgments, and a project announcement. Neither a B.AI mention nor a high posting frequency is a sufficient spam verdict.

This is the appendable issue record requested by the owner, not an implementation plan or authorization to run tests, spend on providers, change prompts, write application data, activate filters, schedule jobs, or deploy. Add new findings and decisions here; retain linked raw evidence separately.

## Current issue index

| ID | Issue | Status | Decision still needed |
| --- | --- | --- | --- |
| PROMO-001 | Advertising assigned to a mentioned model instead of the offered service | Open — reproduced in historical experiment | How to preserve whole-post reasoning while attaching promotion to the correct offering(s) |
| PROMO-002 | Publisher relationship needed to distinguish promotion categories | Open — evidence gap | Which account/affiliation/sponsor evidence is sufficient, and how unknown relationships are represented |
| PROMO-003 | Untracked-company mentions are not independently inventoried | Open — proposed direction | Scope and review policy for inexpensive recurring mention discovery |
| PROMO-004 | Durable campaign identity and exclusion policy | Open — exploratory evidence | What exactly to exclude, with which exceptions, and at which collection/filtering stage |
| PROMO-005 | Useful information may be lost by blanket B.AI exclusion | Open — bounded text review complete | Which kinds of model/access/ecosystem information to preserve |
| PROMO-006 | Prompt experiment outcome and rollback | Evaluation closed; keep 0731; local rollback remains undeployed | Reconsider a newer Jev only under a new bounded evaluation; original ownership issue remains open |
| GEO-001 | Incorrect geo tags on post 2105081335475757197 | Diagnosed — not fixed | How to prevent country stances being inferred from company criticism/model preference |

Statuses describe investigation progress, not whether a fix is deployed. Issue IDs are stable; do not renumber them when adding entries.

## Owner decisions and current boundaries

- **October 1 closeout:** retain 0731 for classification. The later multilingual
  comparisons and political-wording retest are complete. A newer Jev version
  can reopen the question, but no further testing or integration is authorized
  by this record. Start with the [final decision and evidence index](../analysis/2026-10-01-193945-jev-classification-closeout.md).
  This closes the model evaluation, not PROMO-001 or GEO-001.

- The original problem remains misapplying tracked-brand advertising to a brand that is merely mentioned. Recognizing the post as promotional does not settle ownership of that promotion.
- A post can directly promote two brands. The proposed one-party-promotion restriction was rejected; do not reinstate it.
- The owner distinguished **untracked promotion** (done by an untracked brand), **advertising/marketing** (done by the brand itself or a co-sponsor), and **opinion/reaction** (done by a civilian). This is the intended conceptual distinction discussed in the session, not a claim that the current classifier already implements it or that publisher relationships are known.
- Identify what is promoted separately from who promotes it. The owner later rejected the compartmentalized/target-only implementation experiment and asked to return to the original prompt. Retain the conceptual distinction without treating that rejected architecture as an approved plan.
- The long advertising/marketing addition was removed locally. The original pre-expansion v5 prompt is the local baseline; historical v6 receipts remain historical. This rollback was not deployed by the analysis work.
- The owner stopped the earlier prompt experiment at 37/40 calls; those unused calls are not permission to resume it. Subsequently, the owner explicitly requested both Jev review approaches on both issues and approved a separate increase of up to 32 additional model calls/US$1. That bounded diagnostic has now ended after 20 calls, with the promotion-explanation comparison unavailable. Unused new allowance is not an instruction for further experiments. This issue record itself grants no testing authority.
- The owner asked to inspect post text rather than rely on existing class labels. The language, campaign, follower, and signal findings below must not be described as classifier-verified spam or advertising counts.
- The original request proposed excluding B.AI at TwitterAPI collection and saving spammers durably. Later findings exposed useful exceptions. Record the request, but do not silently turn it into a blanket mention exclusion or claim an exclusion is active.
- A cheap periodic, possibly daily, pass to discover repeated company mentions is a proposed direction. No daily job, database change, new blocklist, or collection-query edit was made by these analyses.

## PROMO-001 — What is actually being promoted?

Original example: [@xxyweb3, 2104483144233853085](https://x.com/xxyweb3/status/2104483144233853085). The stored body promotes a platform's guide and access/deployment service while describing GLM as a standout feature. It was the owner's example of advertising being incorrectly attached to Zhipu/GLM.

The database comparison identifies **selling access through a provider versus announcing/advocating the model itself** as the useful distinction. That is not an exclusive rule: genuine partner co-promotion exists, and a service pitch can advocate both offerings. A model name, technical specification, favorable statement, or discount word alone does not resolve the relationship.

The first upstream-interpretation experiment did not fix this boundary. In the ten original advertising cases, the baseline was correct on 4/10 tracked-ad decisions and the diagnostic candidate on 3/10. Those are fixed development cases, not production accuracy. Some extracted interpretations correctly named the third-party provider, but downstream classification still assigned tracked-brand ads. Other interpretations omitted or misidentified the provider.

Evidence: [promotion comparison](../analysis/2026-09-29-145746-promotion-deterministic-comparison/report.md), [paired experiment](../analysis/2026-09-29-014716-post-interpretation-experiment/report.md).

Open questions:

- Where is the boundary between advocating a model and using its capabilities as reasons to buy/use someone else's service?
- How should useful factual claims, praise, and provider promotion coexist without making every mentioned brand an advertiser?
- How should unresolved short URLs or handles remain unresolved rather than produce invented company relationships?

## PROMO-002 — Who is promoting it?

Promotional content alone cannot reliably distinguish official/staff/sponsor activity from an unaffiliated person's recommendation. The saved language study read 216 full stored posts across all 52 authors with official/staff links. Both legitimate brand accounts and B.AI promoters use technical detail, enthusiasm, invitations, benefits, and discounts. Staff also write in a personal voice. Conversely, an official account's courtesy reply, support instruction, or criticism is not automatically advertising.

The full recorded-role inventory was 3,511 posts: 1,833 official-role and 1,678 staff-role. There were no community-role links. These are inventory counts, not manually confirmed promotion counts. The 216-post selection favored recent non-replies and author coverage; it cannot establish a prevalence rate for the entire inventory.

Recorded account roles may also be stale or wrong. The study contains concrete relationship warnings. A home-brand link must not override the post's actual subject, and an unknown account must not be labelled civilian simply because it lacks a known staff link. A partner acknowledgment does not prove paid sponsorship.

Evidence: [official/staff promotional-language findings](../analysis/2026-09-29-143624-account-role-advertising-census/language-findings.md).

Open decision: define trustworthy, dated publisher-to-brand relationship evidence and an explicit unknown state before relying on that relationship to select UP/AM/OR.

## PROMO-003 — Independent recurring company mentions

The owner proposed a cheap periodic pass over stored posts to find repeated company mentions, rather than tracking posting accounts alone. The storage audit found existing candidate/evidence concepts, but not an independent all-post untracked-company mention inventory:

- `PostBrandMention` links only to tracked `Brand` records.
- At the audit, `BrandDiscoveryCandidate` had 2,229 rows, all pending; `UntrackedBrandPromotionEvidence` had 4,904 rows for 4,324 posts and 2,178 candidates.
- The inspected classification-persistence path returns before writing promoted-subject evidence when no untracked promotion was classified. This makes that evidence dependent on the decision it could otherwise help improve. Other discovery paths exist; this is not a claim that all candidate discovery uses that one path.
- Candidate identity is not yet safe to reuse unquestioningly. B.AI is split across records; candidate alias sets also include unrelated-looking co-mentioned companies and personal handles. Shared promoters, hashtags, or co-mentions are not evidence that companies are aliases.

The proposed direction is to record **a mention as an observation**, with its spelling and evidence, independently of promotion/spam decisions. Allow multiple entities and unresolved candidates. Aggregate repeated mentions for review, then save verified names/handles/domains or campaign signatures for inexpensive future matches. A bounded incremental pass with a checkpoint was suggested, not implemented or benchmarked.

Extraction constraints already observed: email domains can be mistaken for @handles; shortened links conceal destination identity; all 20,307 non-NULL `posts.entities` values were empty objects in the audited population, while 256,430 were NULL. Other raw/context fields were not comprehensively audited. Do not assume expanded link destinations are available or introduce live resolution without scope.

Evidence: [recurring-company investigation and storage audit](../analysis/2026-09-29-151842-recurring-company-mentions/report.md).

## PROMO-004 — Known campaigns, other candidates, and durable policy

### B.AI cohort and useful deterministic evidence

The saved comparison identified **7,303 B.AI-associated posts from 395 author IDs**, fetched before `2026-09-29T05:57:44.654358Z`. Selection used explicit B.AI body markers with a raw-text prefilter plus four recovered Unicode-only posts. This does not exhaust all Unicode spellings, indirect references, or shortened-link-only mentions. Association is not a spam label.

Within that cohort, **6,873 posts (94.1%) from 186 authors** contain the joint signature: an explicit B.AI marker, `@justinsuntron`, and `#TRONEcoStar`. No official/staff comparison post matched all three. These are exploratory match rates, not independently measured spam-detection accuracy. Signature absence also does not establish legitimacy; variants, typos, and replies exist.

Sixty substantive normalized text templates recur across at least three authors, covering 270 B.AI posts. This is direct evidence of repeated copy in that subset, not proof that the remaining posts provide unique information or that every repeated announcement is dishonest.

A proposed registry would distinguish confirmed entity aliases, exact campaign signatures, evidence posts, reviewed exceptions, and an enabled policy. Do not automatically block all associated authors or equate a campaign match with verified payment, automation, or fraud. The short exploratory alias `@BAI` needs identity verification before use as a canonical production alias.

Collection-layer exclusion and post-fetch filtering are different: the latter cannot avoid the initial fetch. The analyses did not verify provider exclusion syntax or change either layer.

### Other recurring promotion leads

The separate inventory of 276,737 stored posts used a later cutoff, `2026-09-29T06:19:29.636718Z`. Its counts must not be mixed into the frozen B.AI denominator.

| Candidate | Matching posts | Authors | Why it merits review |
| --- | ---: | ---: | --- |
| Xpert Systems | 414 | 1 | Repeated enterprise software, training, and recruitment offers |
| AINFT | 352 | 81 | Access/platform promotion; 336 posts share the TRONEcoStar tag |
| BTTInferGrid | 148 | 55 | Inference-service promotion; 138 share that tag |
| ENGY | 190 | 55 | Model-serving and token/investment-oriented promotion |
| SOMA | 122 | 78 | Repeated token-saving and early-access-credit offers |
| CcVibe | 36 | 1 | Repeated multi-model API-gateway pitch |
| Topview | 402 | 269 | Plugin/free-generation promotional examples, including disclosed PR |
| Unidentified account-selling campaign | 457 | 296 | Exact repeated account-sales footer; no company identity established |

These are alias/signature match counts, not individually confirmed spam counts. Rows can overlap. The company study reviewed 64 distinct selected posts (63 complete bodies and one 4,500-character prefix), not every matched post. It also found frequent platforms such as OpenCode and OpenRouter with useful troubleshooting, criticism, and technical discussion: frequency is a discovery cue, not a verdict.

Evidence: [B.AI comparison](../analysis/2026-09-29-145746-promotion-deterministic-comparison/report.md), [other-company report](../analysis/2026-09-29-151842-recurring-company-mentions/report.md).

### Follower counts do not supply an easy shortcut

Stored follower counts were known for 386 of the 395 B.AI-associated authors, with a median of 10,523.5. The 287 accounts with 5,000–49,999 followers contributed 6,301 posts (86.3%); the 25 below 1,000 contributed only 29 (0.4%). A low-follower threshold would miss most observed volume.

These were current stored counts at `2026-09-29T06:35:59.109217Z`, not live X checks or counts at posting time. Nine were missing and 101 known counts lacked an observation timestamp. High-follower outliers include official/platform accounts. Followers do not prove authenticity or spam.

Evidence: [complete follower distribution and freshness limits](../analysis/2026-09-29-145746-promotion-deterministic-comparison/bai-followers-distribution.md).

## PROMO-005 — How much useful information would exclusion remove?

The text-signal review used 40 deterministic hash-selected posts from the 7,303-post cohort, independent of stored class labels, author roles, and follower counts. Each post was assigned the highest information tier present:

| Information in the main sample | Posts |
| --- | ---: |
| Substantive primary model/project evidence | 0/40 |
| Specific model specifications, capability claims, or compatibility issue | 11/40 |
| Provider access, prices, usage, integration, or business-model information | 28/40 |
| Generic reaction without concrete additional information | 1/40 |

None of the 40 stored texts demonstrated a model test or measured model result. That is narrower than saying they contain no signal: prices, availability, integration instructions, or a compatibility question may be useful. The specific model claims were not fact-checked.

Ten additional posts without the exact joint campaign signature were reviewed separately to look for exceptions; do not add them to the main denominator. One announced DeepGuard, a security-plugin project for DeepSeek Harness, and credited B.AI for tokens. The post's authorship/product were not independently verified, but it illustrates why a mention-only exclusion can lose ecosystem information. The earlier comparison also found official MiniMax acknowledgments of B.AI availability.

Limits: text-only manual review; media and linked pages were not inspected; some replies lacked local parents. No unique-information rate was measured against the rest of the database, and no whole-cohort spam/signal percentage was established. A repeated provider announcement can contain facts without adding a new fact each time.

Evidence: [signal findings, selected source posts, and per-post decisions](../analysis/2026-09-29-145746-promotion-deterministic-comparison/bai-signal-report.md).

## PROMO-006 — Experiment and prompt state

The long advertising/marketing expansion did not solve the ownership problem. A separate upstream interpretation experiment then failed its original-case improvement requirement. A later target-only experiment was reviewed under a different question and rubric; its 11/12 manual clear-case target score is not comparable to the earlier 4/10 versus 3/10 advertising score. It also had output-shape and exact-quote defects and was never a deployment-ready candidate.

The owner rejected further pursuit of that compartmentalized approach and requested the original prompt. The local prompt module was restored to the exact pre-expansion text; selected content/merge lineage is v5 while historical v6 receipts remain accepted. These facts concern the experiment worktree, not proof of the currently deployed prompt. Preserve the separate staged quality candidate and other sessions' changes.

The saved experiment report contains historical suggestions for another diagnostic. Those suggestions are **not active instructions**. The earlier stop ended that experiment at 37/40 calls, and the official-language review's small candidate clarification was explicitly not applied. A subsequent owner-authorized Jev comparison used a separate 32-call/US$1 ceiling and ended after 20 calls; its narrower scope did not revive those historical suggestions or authorize application changes. See the dated update below.

Evidence: [paired historical result](../analysis/2026-09-29-014716-post-interpretation-experiment/report.md), [target-only result and overriding owner decision](../analysis/2026-09-29-014716-post-interpretation-experiment/targets-only/report.md), [existing experiment plan and rollback record](../plans/2026-09-29-014716-experiment-post-interpretation-plan.md).

## GEO-001 — Company criticism incorrectly became national stances

Source: [@PreciousBa82157, 2105081335475757197](https://x.com/PreciousBa82157/status/2105081335475757197).

Owner report on 2026-09-30: this post should not have received geo tags. The main agent's read-only production observation at `2026-09-30T00:53:47.495954Z` found:

- The stored post criticizes Anthropic/OpenAI over hacking and monopoly, contrasting GLM-5.3. Its saved quote from `@attrc` asks why Anthropic advertised switching to GLM for cybersecurity. Neither text mentions nations/national groups or makes national origin the basis of its evaluation.
- The only stored brand is `glm`. Brand-interpretation judgment `124094`, from `stage1-brand-interpretation-0731-v5` using `deepseek-ai/DeepSeek-V4-Flash-0731`, already contains `geopolitical_modes: [nationalism]`, China `pro`, and US `anti`. Final judgment `124095`, current state, and the geopolitical edge repeat those values. Classification time was `2026-09-29T23:49:39Z`.
- This is a persisted classifier false positive, **not a tag invented by the UI**. The prompt expressly says vendor origin and ordinary product criticism are insufficient. The examined validators check allowed values and consistency, not whether the source expresses national meaning; persistence copies the resulting geo values.
- A code branch that can add `nationalism` to other non-empty modes does not explain this sole-mode output: it preserves existing non-`none` modes, and the earlier model judgment already supplies `[nationalism]`.

Likely interpretation error, not a retained model rationale: criticism of US companies became hostility toward the US, while preference for GLM became support for China. The source does not support that move. The expected correction for this example is `geopolitical_modes: [none]`, China `none`, US `none`; that is the manual diagnostic expectation, **not an applied database correction**. Other classification axes are outside this diagnosis.

Evidence: [main-agent investigation and saved database evidence](../analysis/2026-09-30-095520-geo-false-positive-2105081335475757197/report.md). No prompt/code/database change, model call, or test was made. A shared root cause with the promotion issues has not been established.

## Append-only update log

### 2026-09-30 — Initial consolidation

- Added the stable issue index, current owner decisions, historical experiment state, and linked database findings.
- Kept post counts, author counts, sample judgments, and classifier outputs distinct. Preserved incomplete-coverage and role/follower freshness limits.
- Recorded the new geo report, then incorporated the main agent's read-only diagnosis under GEO-001 with confirmed facts separated from the inferred model mistake.
- Documentation-only work: no application code, database, prompt, provider, scheduler, or deployment changes; no tests or model calls.

### 2026-09-30 — GEO-001 diagnosis received

- Evidence supplied by the main agent: production observation `2026-09-30T00:53:47.495954Z`, stored brand judgment `124094`, final judgment `124095`, and source/persistence trace linked above.
- Updated GEO-001 from investigating to diagnosed, not fixed. The erroneous national labels originate in the brand model output and survive validation/persistence; the particular reasoning error is inferred because no rationale was retained.
- No correction was applied. Discussion of a remedy remains separate from authorization to change behavior or historical records.

### 2026-09-30 11:27 JST — Bounded Jev review comparison ended, partially completed

- Issue IDs: PROMO-001, PROMO-006, GEO-001.
- Owner direction: “let's test both, on both the geopol and promotion issue”; then “budget increase approved” for up to 32 additional model calls and US$1. This reopened only that bounded diagnostic, not the rejected upstream-interpretation architecture or production changes.
- Frozen cohort: eight post/brand cases, seven saved real posts and one synthetic dual-promotion control; four cases per issue. Original local content-v5/brand-v5 baseline versus the same prompts requesting a short checkable explanation. Jev reviewed original labels without explanations, and matched new geo labels with explanations shown versus hidden. Reference labels and thresholds were fixed before calls.
- Promotion: original 0731 labels matched 1/4 references; label-only Jev review was uncertain on all four, including the B.AI/GLM and Token Machine/Qwen mistakes. No demonstrated promotion fix. The explanation comparison was unavailable: the experimental content response returned the wrong explanation structure, and two content decisions also failed the existing parser. No response was repaired or retried.
- Geo: showing the explanation rejected 2/4 incorrect fields versus 3/4 when it was hidden, while holding 5/14 correct fields versus 6/14. No wrong field was confidently approved in either condition. On a company-comparison example, requesting explanations introduced nationalism/China-mild-pro assignments, and showing the resulting explanation weakened Jev's nationalism rejection. This small result does not establish a production-ready filter or a general explanation effect.
- Original geo complaint: fresh 0731 returned correct absences in both arms for post `2105081335475757197`. Its historical incorrect candidate was not replayed to Jev; the exact original failure remains untested as a verifier input.
- Counts/cost: 4 DeepSeek plus 16 Jev calls, no retries; 64 Jev question answers, 58 scored field reviews, not independent posts. Combined estimated model cost US$0.00340272 (DeepInfra-reported estimate plus Jev list-price estimate; excludes Render compute). The earlier 37/40 ledger remains separate.
- Evidence: [complete diagnostic report](../analysis/2026-09-30-110504-jev-targeted-review-comparison/report.md), [frozen contract](../analysis/2026-09-30-110504-jev-targeted-review-comparison/contract.md), [pre-Jev partial-comparison record](../analysis/2026-09-30-110504-jev-targeted-review-comparison/partial-comparison.md), [audit with unavailable cases retained](../analysis/2026-09-30-110504-jev-targeted-review-comparison/audit.json).
- Actions: isolated staging inference job and local Jev calls only; no X requests, production/database writes, application prompt/code edits, scheduler changes, or deployment. Frozen application-source hashes remained unchanged. No further calls are running or planned under this comparison. Promotion ownership and reliable geo correction remain open.

### 2026-10-01 — Classifier evaluation closed without switching

- Owner decision: keep 0731 for classification; remain open to improved future
  Jev versions. Preserve the research for discovery by later agents.
- The root [closeout](../analysis/2026-10-01-193945-jev-classification-closeout.md)
  supersedes earlier pending-experiment directions. It links the final
  117-post/38-field comparison, its limitations, proposed retesting conditions,
  and an inventory of saved evidence. Historical study results remain intact.
- Promotion attribution and unsupported national tagging are still open;
  choosing the incumbent is not a fix. Reading-level and other asynchronous
  headline ideas are proposals, not new product requirements.
- Documentation and offline score/hash checks only. No provider/database calls,
  application changes, new tests, production edits, commits or pushes.

### Template for the next update

Copy this block below the existing updates. Update the issue index/current summary if status changes; retain prior entries and mark superseded conclusions explicitly.

```markdown
### YYYY-MM-DD HH:MM JST — Short update title

- Issue ID(s): PROMO-NNN / GEO-NNN (reuse existing IDs where applicable).
- Owner request or decision: exact scope; distinguish a proposal from approval.
- Observation time / population: UTC cutoff or retrieval time, counting unit, sample size.
- Evidence: source post IDs and local artifact links; identify stored vs live evidence.
- Finding: observed facts, then interpretation; no inferred affiliation or spam verdict without support.
- Limits / contrary examples: missing context, coverage, identity, freshness, or review limits.
- Status / open decision: what changed and what remains unresolved.
- Actions actually taken: include read-only work; distinguish any separately authorized mutation.
```
