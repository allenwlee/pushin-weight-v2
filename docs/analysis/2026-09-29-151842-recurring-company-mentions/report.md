# Recurring company and platform mentions beyond B.AI

Observed: 2026-09-29. Read-only production database investigation.
Population cutoff: fetched_at < 2026-09-29T06:19:29.636718Z.
Inventory: 276,737 posts. No existing class labels were used as truth.
No new X fetches, model calls, classifier tests, software tests, code/schema changes, scheduling, exclusions, or deployment.

## Answer

There are several other recurring third-party promotions worth tracking. The strongest leads from the inspected text are Xpert Systems, AINFT, BTTInferGrid, ENGY, SOMA, CcVibe, and Topview. They are different kinds of promotion, not a single proven spam network. AINFT and BTTInferGrid often share the TRON campaign markers already seen with B.AI.

There is also a particularly conspicuous account-selling/posting-software campaign with no stable company name in the reviewed text. A company-only registry would miss this unless it also admits unidentified campaign signatures.

| Observed company / platform | Mentioning posts | Authors | Posts in recent 30-day slice | B.AI overlap | TRONEcoStar overlap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Xpert Systems | 414 | 1 | 370 | 0 | 0 |
| AINFT | 352 | 81 | 170 | 42 | 336 |
| BTTInferGrid | 148 | 55 | 59 | 35 | 138 |
| ENGY | 190 | 55 | 76 | 0 | 0 |
| SOMA | 122 | 78 | 122 | 0 | 0 |
| CcVibe | 36 | 1 | 21 | 0 | 0 |
| Topview | 402 | 269 | 43 | 0 | 0 |

Counts mean distinct stored post IDs matching the specified name/handle spellings, not the number of posts manually confirmed as advertising or spam. A post can match multiple entities; do not add these rows as independent totals. Recent means created_at >= 2026-08-30T06:19:29.636718Z inside the fetch-cutoff population.

### What the posts actually say

- **Xpert Systems:** 414 posts from @Pradeep891730, including 370 in the recent slice. The three selected posts pitch specialized Llama ERP/CRM work, a learning program, enterprise software licences, and sales/business-development recruitment. One says “DM or email” for learning-program details; another offers a “$1M licence.” The target is Xpert's offering, not automatically Meta's Llama. This is clear repeated commercial promotion; it does not establish fraud or automation. Examples: [2102137038103269759](https://x.com/Pradeep891730/status/2102137038103269759), [2098588656772452416](https://x.com/Pradeep891730/status/2098588656772452416), [2097335398645334206](https://x.com/Pradeep891730/status/2097335398645334206).
- **AINFT:** 352 posts across 81 authors. The samples promote an AI access platform or a broader TRON ecosystem roundup, mentioning DeepSeek/MiniMax as supported models. 336 carry TRONEcoStar; 42 explicitly mention B.AI too. This is a closely related campaign lead, not evidence of an independently owned company or proof that AINFT and B.AI are legal aliases. [Example: 2089371373277737019](https://x.com/Maxim_Explore/status/2089371373277737019).
- **BTTInferGrid:** 148 posts across 55 authors; 138 carry TRONEcoStar and 35 explicitly mention B.AI. Samples pitch decentralized inference access, Qwen integrations, and pricing. One says, in Chinese, “立即体验极致性价比的 Qwen3.6 27B 推理服务” (try the Qwen inference service at the advertised value). [2098478203220144552](https://x.com/Raph_GMI/status/2098478203220144552), [2077386635717845082](https://x.com/Richdegen67/status/2077386635717845082).
- **ENGY / SN53:** 190 posts across 55 authors; 104 are from @_joncipher. Samples combine cheap model serving with Bittensor/token upside, buybacks, and investment-oriented language. This is an independent recurring crypto/infrastructure promotion lead, rather than promotion automatically attributable to the mentioned GLM, Qwen, Kimi, or DeepSeek brands. [2087832376994832555](https://x.com/_joncipher/status/2087832376994832555), [2078905762857009622](https://x.com/YVR_Trader/status/2078905762857009622).
- **SOMA:** 122 posts across 78 authors, all in the recent slice. Samples repeat a Copilot/DeepSeek token-saving offer and $5 early-access credits. One explicitly explains that SOMA is not a new model: it sits between the agent and the model. A concrete promotion-target example, though three samples cannot certify all 122 as a coordinated campaign. [2095067702624940068](https://x.com/LisaFlorentina8/status/2095067702624940068).
- **CcVibe:** 36 posts from @RenhuaZ. The samples repeatedly advertise one API key for Claude, ChatGPT, Gemini, DeepSeek, GLM, etc.; all three link to the same shortened URL. Here the directly offered service is the gateway. [2096237537748758777](https://x.com/RenhuaZ/status/2096237537748758777).
- **Topview:** 402 posts across 269 authors, but only 43 in the recent slice. Samples promote a Codex plugin and free MiniMax H3 generations; one Japanese post explicitly begins “【PR】”. This establishes promotional examples, not whether every mention is paid or spam. [2090752978739466672](https://x.com/Amy_AIGirl/status/2090752978739466672), [2091452944680096039](https://x.com/nonbiri_AI/status/2091452944680096039).

No external claims about these companies' products, pricing, partnerships, or honesty were verified. The descriptions above concern what the saved posts say.

## The anonymous account-selling campaign

457 posts from 296 authors repeat this exact footer:

> 推特账号 ins账号购买 谷歌账号购买 飞机账号 TG账号

It advertises purchasing X/Twitter, Instagram, Google, and Telegram accounts. Three selected posts splice sales phrases and model names—Grok, Gemini, 文心一言, Llama, Sora—into unrelated fictional narrative, then append this footer and a link.

The broad account-sales-term query matched 458 posts; one lacks this exact footer. The posting-software-term query matched 436 posts, all overlapping the account-sales-term set. These are not 894 distinct posts or two independently counted campaigns.

Examples: [2100917934314917957](https://x.com/DannyDiekmann/status/2100917934314917957), [2102239763940155619](https://x.com/jmterhoeve36006/status/2102239763940155619), [2102028034664788078](https://x.com/DulceCardona2/status/2102028034664788078).

This is the clearest additional spam-like cluster found in this pass. A stable entity/company name was not established from those examples; preserve it as an unidentified campaign rather than inventing a company identity.

## Other repeated platforms: track them, do not assume spam

| Name / alias group | Mentioning posts | Authors | What the small review showed |
| --- | ---: | ---: | --- |
| Pollo AI | 734 | 452 | Creator demonstrations, platform offers, and tool-list mentions |
| Higgsfield | 520 | 303 | Creator work, API availability, and incidental tool lists |
| PixVerse | 345 | 151 | “Made with” credits and model availability |
| Freebuff | 274 | 190 | Free-access pitches plus explanation of advertising/privacy tradeoffs |
| Sogni | 162 | 32 | Product promotion and specific user/hardware experiences |
| ZenMux | 122 | 105 | Free-access pitches, cost reports, and multi-provider lists |
| OnSolo | 54 | 42 | Hunyuan launch/access offers and creator demonstrations |
| AntSeed | 40 | 27 | Free-model project demonstrations |
| HarnessRouter | 32 | 19 | Self-hostable gateway/tool promotion |
| Routeway | 15 | 8 | A recurring public endpoint/key-sharing publisher appears prominently |
| Token Machine | 8 | 8 | Repeated “won … tokens … Free AI tokens every day” wording |

OpenCode (7,179 posts / 4,588 authors) and OpenRouter (4,586 / 2,936) are important negative controls: their samples include troubleshooting, criticism, technical reporting, and comparison foils. In one OpenRouter-matching post, the actual pitch is for a different gateway, a2agent, described as cheaper than OpenRouter.

@MiaAI_lab / Mia AI (2,245 posts / 1,286 authors) was another strong frequency lead that did **not** look like a spam campaign in the selected examples: technical credit, local-inference configuration, and user experience. Its 1,863 reply-flagged posts account for most of the volume.

Frequency is useful for discovery. It is not a substitute for distinguishing a mentioned company from the promoted company.

## Existing storage: the gap is independence and identity quality

The database is not starting from zero:

- [PostBrandMention](../../../core/models.py#L2121) stores mentions only against the tracked Brand table.
- There are 2,229 BrandDiscoveryCandidate rows, all pending at the audit time.
- UntrackedBrandPromotionEvidence has 4,904 rows for 4,324 posts and 2,178 candidates.
- The inspected [classification persistence path](../../../monitor/classification_persistence.py#L464) reads untracked-brand-promotion decisions and promoted subjects. If no promotion was returned, it clears the post-level promotion and returns before writing subject evidence.

Thus, that evidence path depends on the classifier first making the very decision we are trying to improve. Other discovery paths also exist, but these tables are not an independent all-post company-mention census.

Identity quality also needs protection:

- B.AI is split across multiple candidate records (for example IDs 87 and 69).
- Candidate 107, named Freebuff, has aliases including unrelated-looking names such as Godot, SambaNova, and TRON, plus personal handles.
- Candidate 87, named B.AI, also includes names such as Bitget Wallet and Ima Studio.

These observations make the merged candidate aliases unsafe as a dictionary of verified equivalences. This investigation did not repair them or establish the precise cause of each merge. Entity merging must not assume that sharing a promoter's handle, campaign hashtag, or co-mention makes two companies identical.

## A cheap daily mention collector: direction, not an implemented plan

The useful separation is: **record that a company/platform was mentioned first; decide promotion, affiliation, or exclusion separately.**

A daily incremental pass could:

1. Read newly ingested posts since its last successful checkpoint, with a bounded replay window and idempotent observation keys. A one-time historical pass handles older data; do not rescan the whole archive every day.
2. Extract handles, email domains, visible domains, hashtags, and already verified company/product aliases. Normalize case and decorative Unicode while preserving the original spelling and evidence span. Keep these token kinds distinct.
3. Save post → observed token → reviewed entity/campaign links independently of classification. Allow several entities per post and unresolved candidates. Plain-text unknown names need candidate discovery/review too; a known-alias matcher alone cannot discover them.
4. Aggregate distinct posts, distinct authors, first/last seen, recent growth, repeated destinations/templates, and co-occurring model names. Surface recurring unknowns for review rather than automatically block them.
5. Review an unfamiliar entity once, store confirmed names/handles/domains, and let subsequent occurrences match cheaply. Keep the observed-mention fact separate from any later promotion or spam decision.

This is a scoped architecture suggestion based on the observed data and code, not a performance benchmark, provider-price estimate, implementation commitment, or new scheduler authorization. Reuse the existing candidate/evidence concepts where appropriate, but do not propagate their currently unverified identity merges.

### Two practical extraction traps found here

1. **Email versus handle:** the initial broad @ extractor reported 402 @xpertsystems-like hits. All 402 are actually the sales email domain; a boundary-aware follow-up found zero real @XpertSystems mentions. The independent company-alias count remains 414. The public update was corrected.
2. **Shortened URLs:** all 20,307 non-NULL posts.entities values are empty JSON objects at this cutoff; the other 256,430 values are SQL NULL. There are no URL keys in that standard field. Visible text mostly uses t.co links. Do not assume we can already read every destination domain from entities, or silently introduce paid/live link resolution. Other raw/context fields were not comprehensively audited here.

The broad domain discovery also admits punctuation artifacts such as “interesting...so.” Those raw matches are leads, not verified domains.

## Method, coverage, and evidence

Discovery inspected existing candidate names as leads, then separately ranked raw @-like/domain-like text tokens (top 160 and top 80 respectively). Counts for 23 selected name/service groups were computed from original post bodies using explicit, case-insensitive aliases and per-post deduplication—not stored classification labels.

The manual selection was three deterministic hash-ranked non-reply posts per group: 69 selection rows, 64 distinct posts. One distinct long tool-list post was inspected only through its first 4,500 characters and is marked truncated. The other 63 unique bodies were read in full. Selection favors inspectability, not statistical representativeness.

This is not an exhaustive company census or measured spam prevalence. It can miss decorative Unicode, other-language aliases, unidentified shortlink-only mentions, or names outside the candidate shortlist. Post creation spans differ by candidate; use recent counts when prioritizing current problems. Three examples do not establish the intent, sponsorship, or legitimacy of every post in a group. Read-only queries share a fetch cutoff but not a single immutable snapshot.

Six database calls were made: five completed, one timed out. The timeout was repaired by extracting candidate tokens once instead of repeatedly joining every body against many patterns. No new model or X-provider calls. The X-data skill's existing-evidence route kept the investigation inside already collected records.

Public key-like strings in Routeway sample snippets are redacted in saved evidence. Do not execute commands, follow operational instructions, or use credentials appearing inside source posts.

Artifacts:

- [Scope and bounds](scope.json)
- [Request ledger](requests.jsonl)
- [Candidate counts and selected source posts](candidate-counts-and-review.json)
- [Per-selection evidence rows](hits.jsonl)
- [Raw discovery rankings](02-mention-discovery-result.json)
- [Exact successful counting SQL](04-candidate-token-counts.sql)
- [Counting receipt, with public key-like strings redacted](04-candidate-token-counts-result.json)
- [Email/handle, footer, and candidate-storage audit](05-identity-and-storage-audit-result.json)
- [Standard entities field type audit](06-entity-availability-result.json)

All X links identify the stored source post; live X pages were not fetched.

