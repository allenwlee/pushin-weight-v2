# Official/staff promotion versus the B.AI campaign

Date: 2026-09-29. Source: existing production PostgreSQL records, read-only.
Post-population cutoff: `fetched_at < 2026-09-29T05:57:44.654358Z`.
Owner direction: compare actual text; ignore stored class labels; hold the prompt retry.

## Finding

There is a useful deterministic distinction for this known campaign: a repeated combination of B.AI identity, Justin Sun's handle, and the TRON campaign hashtag. It separates the bulk B.AI campaign from the recorded official/staff posts far better than promotional vocabulary does.

This does **not** establish a universal language rule separating legitimate advertising, untracked-brand promotion, and civilian opinion. Official accounts and B.AI promoters both use launches, technical specifications, benefits, discounts, enthusiasm, and invitations to try products. Campaign membership, promotional intent, promotion target, and author/sponsor relationship remain different questions.

No prompt or application changes, model/provider calls, software tests, database writes, scheduling changes, or deployment were performed for this comparison. The X-data routing skill directed this work to existing evidence; the failed database requests were not replaced with paid fetches or model tests.

## Population and completeness

- All 3,511 stored posts by accounts currently recorded as official/staff for non-sentinel brands: 1,833 official posts across 28 authors, and 1,678 staff posts across 24 authors. No community-role links exist.
- 7,303 identified B.AI-associated posts across 395 author IDs in the reported comparison. Association means a bounded body match for B.AI, BAI_AGI, or @BAI after Unicode normalization, not a reviewed spam label.
- 708 additional posts have the TRONEcoStar hashtag without an explicit normalized B.AI marker. Keep these separate: some concern BTTInferGrid or wider TRON topics.
- Two B.AI-associated posts also belong to the official cohort. The groups are not disjoint.
- Initial discovery found 8,010 raw-body matches for B.AI/BAI_AGI/TRONEcostar. Reconciliation: 7,299 explicit B.AI matches + 708 hashtag-only matches + 3 plain TRONEcostar-word matches without the hashtag = 8,010. The outside-control scan then found four additional fancy-Unicode B.AI posts, producing 7,303 explicit matches.
- A global Unicode-normalized selection exceeded the 60-second database limit. Consequently, this is a full inventory of the stated ASCII-prefilter population plus those four recovered posts, **not an exhaustive census of every Unicode spelling or every indirect reference to B.AI**.
- The official/staff inventory includes support, replies, personal observations, and other non-promotional material. Roles are current database metadata, not independently verified current employment or sponsorship.
- Read-only transactions shared the fetch cutoff but not one immutable database snapshot; text and account relationships could change between reads.

Full-population feature counts were calculated in SQL. Human reading consisted of the earlier 216 official/staff selections across all 52 authors, 24 deterministic campaign selections, and the saved collision/exception selections here—not a claim that every one of the thousands of posts was manually labeled.

## Measured differences

| Measured pattern | B.AI-associated: 7,303 | Official: 1,833 | Staff: 1,678 |
| --- | ---: | ---: | ---: |
| Three-part campaign signature | 6873 (94.1%) | 0 (0.0%) | 0 (0.0%) |
| At least two filler families + link | 273 (3.7%) | 0 (0.0%) | 0 (0.0%) |
| More than 1,000 normalized characters | 4834 (66.2%) | 168 (9.2%) | 26 (1.5%) |
| Free / discounts / credits / quota wording | 4441 (60.8%) | 129 (7.0%) | 38 (2.3%) |
| We / our wording | 489 (6.7%) | 464 (25.3%) | 264 (15.7%) |
| Hosted-access phrase family | 1427 (19.5%) | 46 (2.5%) | 8 (0.5%) |

The three-part signature means all three occur somewhere in the normalized body:

1. An explicit B.AI marker.
2. `@justinsuntron`.
3. `#TRONEcoStar`.

The calculation checks co-occurrence, not position at the end of the post. The reviewed examples frequently use them as a footer.

The six filler families were fixed before results: TBH/NGL; honestly; seriously; game-changer; did-you-know; and reassurance such as trust-me/you-won't-regret/what-are-you-waiting-for/not-gonna-lie. A hit requires at least two different families plus a URL. Repeating TBH does not count as two.

The incentive and hosted-access patterns are deliberately broad exploratory measurements. Incentives include substring matches for free, discount, percentage-off, credits, and quota; they can match non-sales uses. Hosted-access patterns include available-on, free-on, now-on, available-via, and bounded access/integration phrases. These are not semantic labels.

First-pass additional measurements, on 7,299 rather than 7,303 B.AI posts:

- At least three URL occurrences: 4,770 B.AI; 99 official; 7 staff.
- Median normalized body length: 1,347 B.AI; 163 official; 52 staff.
- URL occurrences are not distinct links or calls to action. B.AI frequently appears as repeated shortened URLs in the stored body.

### Check that short replies are not driving the result

Among posts not flagged as replies (NULL reply flags are included):

- B.AI: signature in 6,868 / 7,025 = 97.8%.
- Official/staff: signature in 0 / 1,696.
- For the recent slice, creation time >= 2026-08-30T05:57:44.654358Z within the same fetch cutoff: 4,069 / 4,157 B.AI = 97.9%; 0 / 877 official/staff.
- For English non-replies: 5,508 / 5,612 B.AI = 98.1%; zero in both known-role groups.

These are cohort match rates, **not spam-detection accuracy, precision, or recall**. The cohorts were not independently labeled for spam, and this was exploratory analysis, not a held-out evaluation.

## The important counterexamples

### A B.AI mention can be an official partner acknowledgment

MiniMax's official account posted:

> Thanks to the @BAI_AGI team for making M3 available from day one.

[Stored source: 2067913044752044159](https://x.com/MiniMax_AI/status/2067913044752044159).

A second official reply addresses @BAI_AGI and thanks people trying M3 ([2067913825941151997](https://x.com/MiniMax_AI/status/2067913825941151997)). Neither has the three-part campaign signature. Another official reply thanks @justinsuntron without B.AI or the campaign hashtag.

Therefore, neither B.AI alone nor Justin Sun alone safely establishes spam. An official acknowledgment also does not prove a paid sponsorship arrangement.

### Filler words catch unrelated technical and personal discussion

The outside-cohort scan found 19 posts from 17 authors satisfying the two-filler-plus-link rule, among 4,852 raw-prefilter candidates. That denominator is a candidate pool, not all other database posts.

Examples:

- [Qwen local voice benchmark, 2098208251242242121](https://x.com/Oluwaphilemon1/status/2098208251242242121): “seriously” plus the command-line option `-ngl` triggers the rule. The latter is not conversational “not gonna lie.”
- [Researcher's conference reflection, 2098154466520269147](https://x.com/dahou_yasser/status/2098154466520269147): TBH and seriously appear in a self-deprecating discussion of their model being overtaken.
- [Engineering/recruiting post, 2103292627080908934](https://x.com/GeoffreyHuntley/status/2103292627080908934): honestly and not-gonna-lie appear in a specific description of engineering work and hiring.
- Other collisions include direct MiniMax recommendations and an explicitly disclosed referral promotion. Their account relationships are not established by this scan.

Meanwhile, the rule misses 96.3% of the identified B.AI population. It is neither a useful general separator nor a sufficient spam-removal rule.

One selected unrelated post was a pasted coding conversation containing incidental account credentials. Its body is omitted from saved pass-two receipts and derived exports; numeric results are preserved. Those receipts are explicitly marked redacted/reconstructed, not untouched raw output. No incidental credentials are reproduced in this report.

### Criticism keywords do not repair the problem

Only one B.AI-associated post matched the narrow criticism-term probe. Reading it shows a promotional pitch that mentions potential misuse/spam as a caveat. This is not proof there are no critical B.AI posts: the probe is narrow, language-dependent, and body-only. A “spam/scam present” exception would itself be unreliable.

### Not all B.AI promotion carries the same tags

430 identified B.AI posts lack the full three-part signature. The reviewed selection includes replies, a #JUST variant, a misspelled #TrunEcoster, a TRONGlobalFriends variant, and a long B.AI/MiMo explanation without Justin Sun's handle. The rule knowingly leaves such posts unresolved.

The four Unicode-only recoveries also lack the full signature. They include thread fragments. Missing tags must not mean legitimate, and membership must not automatically spread from one post to every post by its author.

## Repeated text is a second useful, narrower signal

After normalizing Unicode/case/whitespace and replacing URLs and @handles with placeholders:

- 60 substantive templates occur across at least three distinct author IDs in the B.AI cohort, covering 270 posts.
- None meet that condition in the official or staff cohorts.
- Nine additional templates cover 39 hashtag-only TRON posts.

“Substantive” requires at least 120 characters after removing the URL/handle placeholders. This follow-up was necessary because the first pass incorrectly made link-only bodies and short thanks look like substantial cross-account reuse.

The largest B.AI example is an approximately 800-character English free-model pitch, reused in nine posts across five authors. Another is a Chinese version appearing seven times across five authors. Hashtags, model names, numbers, and remaining wording are preserved in the template comparison.

This gives direct evidence of copied campaign copy across accounts, but covers only 3.7% of the identified B.AI posts. Legitimate syndicated announcements could also be repeated; duplication alone does not establish payment, automation, or dishonesty.

## The language nugget about promotion targets

The clearest conceptual distinction is **selling access through a provider versus announcing the model itself**.

A recovered B.AI thread explicitly asks, in fancy Unicode, why use B.AI instead of connecting directly, then says:

> With a single API you can access multiple frontier models without managing separate accounts or integrations.

[Stored source: 2076601240524354013](https://x.com/Kelechiweb/status/2076601240524354013).

That is an unusually clear statement of the provider/model relationship: different model brands are reasons to use the provider's service.

In the original [GLM guide post, 2104483144233853085](https://x.com/xxyweb3/status/2104483144233853085), the offered object is the platform's guide and access/deployment service; GLM is described as a standout feature. That interpretation is supported by the complete body and campaign tags, not merely by the presence of a discount word.

However, “available on” language also occurs in 54 official/staff posts, and genuine co-promotion exists—for example, [Upstage's “Try Cline. Try Solar Pro 4.”](https://x.com/upstageai/status/2099153360863813683). A provider can promote its service and a model at the same time. We should not reinstate a one-party-promotion constraint.

Code can reliably recognize known identifiers and explicit textual patterns. It cannot infer all target relationships or paid sponsorship from those patterns alone.

## What I would encode, and what I would leave to interpretation

For this specific problem, the candidate is a **known-campaign match**, with evidence recorded:

```text
explicit B.AI marker
AND exact Justin Sun handle
AND exact TRONEcoStar hashtag
→ known B.AI/TRON campaign match
```

That is a proposed policy input, not a silently implemented spam or classification verdict. The exploratory cohort includes @BAI; that short alias must be identity-verified before treating it as a canonical production alias. The original problematic post has the unambiguous @BAI_AGI handle.

A durable registry should store the entity/campaign, confirmed handles/domains, exact signature, supporting post IDs, reviewed exceptions, and enabled policy. Do not block all 395 associated authors merely because they appear in this comparison. Match reasons should distinguish a campaign match from an author block.

There are three separate decisions:

1. **Known unwanted campaign:** an approved campaign registry can deterministically identify and exclude it.
2. **What is promoted:** provider/model relationships still require whole-post interpretation outside explicit known cases; multiple targets remain allowed.
3. **Who is promoting it:** official/staff/sponsor/civilian attribution requires trustworthy account/relationship evidence, not writing style.

This can remove the known B.AI source of bad tracked-brand assignments without claiming to solve every future untracked promotion. It should not silently convert all mentions of Zhipu/Qwen into, or out of, tracked-brand advertising.

If filtering is later requested at the TwitterAPI search layer, its actual query capabilities and exception behavior must be checked separately. A post-fetch rule alone does not avoid fetch charges. No query syntax, account blocklist, or live filter was changed here.

## Execution record and reproducibility

Two exploratory feature definitions were used. The first all-database feature query exceeded 60 seconds; narrowing it to the comparison cohorts succeeded. Pass two added the predeclared collision/recency checks and a substantive-text restriction for duplicates. A selection repair intended to include all Unicode spellings also exceeded 60 seconds; it was not repeatedly retried. A small reconciliation read identified the four extra posts already returned by the control selection.

All work stayed read-only. Zero new model calls; zero X-provider calls. Existing prompt experimentation remains on hold.

The [request ledger](requests.jsonl) records seven database invocations: five completed and two timed out. It is reconstructed from saved SQL and receipts; unavailable issue timestamps are explicitly null.

Evidence:

- [Reported counts and review selections](feature-comparison-final.json)
- [Pass-one SQL](feature-comparison-scoped.sql) and [unmodified Render output](feature-comparison-scoped-render-result.json)
- [Pass-two SQL](feature-comparison-pass-2.sql) and [receipt with sensitive unrelated body omitted](feature-comparison-pass-2-render-result.json)
- [Four-post cohort reconciliation](cohort-reconciliation-render-result.json)
- [Initial campaign sample](bai-sample.json)
- [Earlier 216-post official/staff language review](../2026-09-29-143624-account-role-advertising-census/language-findings.md)
- [Pre-analysis comparison contract](comparison-contract.json)

Linked X pages were not fetched; quoted evidence comes from the stored database bodies. Missing media, expanded link destinations, quote context, thread context, untracked brand mentions, and historical affiliation accuracy remain limitations. The original problematic post has NULL entities and no stored quoted text; we did not infer or fetch the destinations of its shortened URLs.
