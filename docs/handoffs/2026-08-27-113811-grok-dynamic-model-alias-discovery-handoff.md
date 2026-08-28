# Research dynamic discovery of unknown model names using X data

## Problem

PushinWeight monitors conversations about approximately 20 AI brands. Collection currently depends substantially on known brand names, model names, aliases, and official or staff accounts.

This fails when a company launches or previews a model under an entirely new name that could not have been configured beforehand.

Recent example:

- The anonymous model **Ox Alpha** appeared around August 20, 2026.
- Z.ai/Zhipu officially revealed on August 26, 2026, that Ox Alpha was **GLM-5.3-Flash**.
- Before that announcement, many users discussed "Ox Alpha" without saying GLM, Zhipu, Z.ai, or `@Zai_org`.
- We want Zhipu's trend headline to identify Ox Alpha as the reason its conversation is notable.

Official reveal: https://x.com/Zai_org/status/2092616204787626030

## What our database shows

As of August 27, 2026:

- 1,129 stored posts contained "Ox Alpha."
- 603 were attributed to GLM/Zhipu.
- 517 used "Ox Alpha" without GLM, Zhipu, Z.ai, or `@Zai_org`.
- Only 17 of those 517 alias-only posts were attributed to GLM.
- Before the official reveal, 939 Ox Alpha posts had been stored.
- Of those, 430 were attributed to GLM, mostly because they also mentioned or speculated about GLM/Zhipu.
- Approximately 500 pre-reveal alias-only posts were stored but not connected to GLM.
- We cannot measure from our database how many additional Ox Alpha posts were never collected.

Our latest one-day GLM headline packet contained four Ox Alpha excerpts out of twelve evidence excerpts, but it omitted Z.ai's authoritative announcement. The generation was subsequently rejected by existing validation.

## Research request

Use direct X API access to reconstruct the Ox Alpha conversation from its first appearance through the official reveal and determine how PushinWeight could discover unknown names automatically.

Please do not merely endorse the proposed approach below. Challenge it and recommend a simpler or stronger design if one exists.

### 1. Quantify the collection gap

Search all accessible X posts containing variations such as:

- `Ox Alpha`
- `OxAlpha`
- `ox-alpha`
- Relevant OpenRouter or OpenCode model slugs
- Other spelling or language variants discovered during research

Separate:

- Original posts, replies, quotes, and reposts
- Unique authors
- Exact and near-duplicate clusters
- Posts containing known Zhipu signals: GLM, GLM-5.3, Zhipu, Z.ai, or `@Zai_org`
- Posts containing only the unknown Ox Alpha name
- Posts collected before versus after the August 26 official reveal
- Languages and translated variants

Estimate the percentage of the real Ox Alpha conversation that a known-term GLM query would have missed.

### 2. Reconstruct the discovery timeline

Build a timeline showing when evidence connecting Ox Alpha to Zhipu first became available.

Distinguish:

- Pure speculation
- Repeated community consensus
- Technical fingerprinting
- Posts from known Zhipu staff
- Official-account statements
- Quotes or replies involving official or staff accounts
- Final authoritative confirmation

Avoid using knowledge from the August 26 reveal to describe what was knowable on earlier dates.

### 3. Identify early discovery signals

Determine which signals could have detected Ox Alpha as a notable emerging model name before its ownership was known, including:

- Sudden phrase-frequency bursts
- Repetition across independent authors
- Co-mentions with known AI models
- Common URLs, domains, model slugs, or platforms
- Reply or quote relationships with known accounts
- Overlap with Zhipu staff or community networks
- Semantic similarity to existing GLM conversation
- Technical claims, tokenizer fingerprints, or model behavior
- LLM-based entity and alias discovery

Explain which signals are strong enough to collect more posts and which are strong enough to attribute the alias to Zhipu.

## Architecture question

Brainstorm a lightweight, cost-conscious system that can:

1. Notice a previously unknown model or product name.
2. Begin temporarily collecting it without waiting for manual configuration.
3. Avoid flooding the database with unrelated viral phrases.
4. Associate it with a tracked brand when sufficient evidence appears.
5. Distinguish speculative from confirmed associations.
6. Reattribute already-stored posts after confirmation.
7. Run a bounded historical recovery query for posts missed before confirmation.
8. Provide the headline LLM with aggregate phrase counts, a timeline, and authoritative evidence.
9. Expire temporary aliases that prove irrelevant.
10. Work within a 15-minute harvest cycle and controlled X API budget.

Possible—but not predetermined—components include:

- A global emerging-phrase detector
- Temporary discovery queries with TTLs
- Confidence-scored alias records
- Trusted official or staff confirmation
- LLM review of candidate alias relationships
- A bounded recovery search after confirmation
- Corpus-wide phrase aggregation plus sampled evidence

## Requested output

Please return:

1. Quantitative findings from X.
2. The Ox Alpha discovery timeline.
3. What our current query strategy would have collected or missed.
4. Three viable architectures, including the simplest one.
5. Cost, latency, false-positive, and API-credit tradeoffs.
6. Recommended confidence states and promotion rules.
7. A recommended production design.
8. Example database records and lifecycle for `Ox Alpha -> GLM-5.3-Flash -> GLM/Zhipu`.
9. How the resulting information should appear in a trend-narrative packet.
10. Failure cases and tests using other surprise model launches.

The ultimate product requirement is: **when an unknown name suddenly dominates discussion around a tracked company, the resulting brand headline should explain it—even though that name did not exist in our configuration before the event.**
