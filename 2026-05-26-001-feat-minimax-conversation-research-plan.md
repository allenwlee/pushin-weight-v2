# {{AGENT_ATTRIBUTION}}

---
title: "feat: MiniMax Conversation Intelligence Research Plan"
type: feat
status: active
date: 2026-05-26
deepened: 2026-05-26
---

# MiniMax Conversation Intelligence Research Plan

## Overview

Systematic research program to map the global conversation landscape around MiniMax, using Qwen and DeepSeek as control models. Designed to surface patterns by model variant, language, and use-case keyword — forming the basis for a competitive intelligence briefing.

## Problem Frame

We need a comprehensive, evidence-grounded picture of how MiniMax is discussed across the internet: what people are saying, how it compares to rivals, what use-cases dominate, and how conversation differs by language and model variant. Qwen and DeepSeek serve as analytical controls — same methodology, same time window — enabling direct competitive comparison.

## Research Inventory

### Available Sources (last30days v2.1)

| Source | Status | Notes |
|--------|--------|-------|
| Reddit | **BROKEN** | Search times out at 90s — unusable this cycle |
| X (via xAI/Grok) | Working | 8-20 posts per query, engagement data (likes, RTs) |
| YouTube | Working | 7-17 videos, view+like counts, transcripts N/A |
| Web (Brave Search) | Working | 15-23 results, no engagement data |

### Source Weighting Hierarchy

1. **X** — highest signal (engagement metrics, real-time, global voices)
2. **YouTube** — high signal (view counts, transcript-backed when available)
3. **Web** — lower signal (no engagement data, but covers blogs/news/docs)
4. **Reddit** — excluded until timeout issue is resolved

## Key Technical Decisions

- **Reddit excluded** until the 90s timeout bug is fixed or the search library is updated
- **Control models (Qwen, DeepSeek) run with identical queries** — differences are model-specific, not method-specific
- **Per-query results stored** in `docs/research/minimax-conversation/` for downstream synthesis
- **Stats boxes captured programmatically** per query for quantitative comparison across models
- **Language segmentation** handled via language-specific query variants (see Phase 2)
- **Use-case segmentation** handled via keyword scoping within single model queries (see Phase 2)

## Open Questions

### Deferred to Implementation

- Should we also check whether a different Reddit search library or PRAW credentials fix the timeout?
- Should video transcripts be retried with a different YouTube extraction backend?

## Implementation Units

- [ ] **Unit 1: Source Inventory & Diagnostic Verification**

**Goal:** Confirm current source availability and document API key state

**Requirements:** N/A (setup unit)

**Dependencies:** None

**Files:**
- Modify: `docs/research/minimax-conversation/SOURCE_INVENTORY.md` (create)

**Approach:**
- Run `last30days.py --diagnose` for each of the three model queries
- Record which sources are live vs broken per model
- Confirm Reddit timeout is consistent across all three models (not query-specific)

**Verification:**
- Source inventory doc shows all three models have matching source availability

---

- [ ] **Unit 2: Core Model Conversation Queries (Comparative, English-Dominant)**

**Goal:** Establish baseline conversation volume and sentiment for each of the three models using identical query methodology

**Requirements:** R1, R2 (from below)

**Dependencies:** Unit 1

**Files:**
- Create: `docs/research/minimax-conversation/minimax-core-queries.md`
- Create: `docs/research/minimax-conversation/qwen-core-queries.md`
- Create: `docs/research/minimax-conversation/deepseek-core-queries.md`

**Approach:**
Run three `last30days.py` queries in parallel (or sequential if rate-limited), all using `--quick` mode to fit within 5-min timeouts:

1. `last30days.py "Minimax AI"` --emit=compact
2. `last30days.py "Qwen AI"` --emit=compact
3. `last30days.py "DeepSeek AI"` --emit=compact

Capture: X post count, YouTube video count, web result count, total engagement per platform, top voices (@handles, YouTube channels), dominant themes from each result set.

**Patterns to follow:**
- Store raw output per query in separate files
- Build a comparison table: model vs. conversation volume vs. engagement

**Test scenarios:**
- Each query completes without error
- All three models return X, YouTube, and web data
- Stats boxes are captured verbatim from each output

**Verification:**
- Three query result files exist, each with a filled stats box
- Comparison table shows relative conversation volume across models

---

- [ ] **Unit 3: Language-Agnostic Brand-Name Conversation Measurement**

**Goal:** Measure the actual language distribution of organic conversation around each model by using brand-name-only queries (no language-specific keywords) and classifying results by language post-hoc

**Requirements:** R4

**Dependencies:** Unit 1

**Files:**
- Create: `docs/research/minimax-conversation/language-distribution-minimax.md`
- Create: `docs/research/minimax-conversation/language-distribution-qwen.md`
- Create: `docs/research/minimax-conversation/language-distribution-deepseek.md`

**Approach:**
Run brand-name-only queries — no English or Chinese keywords appended — then classify each result by detected language:

1. `last30days.py "MiniMax"` --emit=compact
2. `last30days.py "Qwen"` --emit=compact
3. `last30days.py "DeepSeek"` --emit=compact

For each result set, manually classify:
- **X posts:** Classify by @handle bio language, tweet language, or account location
- **YouTube:** Classify by channel name, video title language, and description language
- **Web results:** Classify by page language (URL domain can serve as a signal; zh.* = Chinese, .jp = Japanese, en.* or no TLD = English/other)

Build a language distribution table per model:

| Model | X (English / Chinese / Japanese / Other) | YouTube (EN/ZH/JP/Other) | Web (EN/ZH/JP/Other) |
|-------|-----------------------------------------|---------------------------|----------------------|
| MiniMax | | | |
| Qwen | | | |
| DeepSeek | | | |

**Rationale:** This is different from Unit 5 (explicit Chinese/Japanese keyword queries). Here, we measure what language the organic conversation IS, not what surfaces when we search in a specific language. The delta between brand-name-only and keyword-appended queries reveals how much non-English conversation exists that English-keyword searches miss.

**Test scenarios:**
- All three queries return ≥10 results across platforms
- Language classification is possible for ≥80% of results
- At least one model shows >10% non-English content

**Verification:**
- Three language distribution files exist
- Cross-model language comparison table is produced
- Quantified delta between brand-name-only and keyword-appended result counts is noted

---

- [ ] **Unit 4: Chinese vs. Non-Chinese Discourse Comparison**

**Goal:** Compare Chinese-language and non-Chinese discourse on MiniMax across two dimensions: (1) subject matter clustering — what topics dominate each language community — and (2) timing — whether Chinese discussion leads or lags non-Chinese discussion on the same developments

**Requirements:** R4

**Dependencies:** Unit 3 (brand-name language distribution establishes the baseline for segmentation)

**Files:**
- Create: `docs/research/minimax-conversation/chinese-vs-nonchinese-subject-matter.md`
- Create: `docs/research/minimax-conversation/chinese-vs-nonchinese-timing.md`

**Approach:**

**Part A — Subject Matter Segmentation:**
Run the same set of queries for MiniMax and compare what Chinese-language results discuss vs. what English/other-language results discuss:

1. `last30days.py "MiniMax"` --emit=compact
2. `last30days.py "MiniMax M2.7"` --emit=compact
3. `last30days.py "MiniMax Hub"` --emit=compact
4. `last30days.py "MiniMax Speech"` --emit=compact
5. `last30days.py "MiniMax Mavis"` --emit=compact
6. `last30days.py "MiniMax Agent"` --emit=compact

For each query, segment results into:
- **Chinese results:** X posts from Chinese-language @handles or China-located accounts, YouTube channels with Chinese names/titles, web results from .cn domains or zh-* pages
- **Non-Chinese results:** everything else

Classify subject matter per language segment using keyword tagging:
- Coding / agentic
- Video / image generation
- Speech / music
- Pricing / value
- Comparison / benchmarks
- News / releases
- Tutorial / how-to

Build a comparison table per query:

| Query | Chinese Top Subject | Non-Chinese Top Subject | Divergence? |
|-------|---------------------|------------------------|-------------|
| MiniMax | | | |
| MiniMax M2.7 | | | |
| MiniMax Hub | | | |
| MiniMax Speech | | | |
| MiniMax Mavis | | | |
| MiniMax Agent | | | |

**Part B — Timing Analysis:**
For each query, sort results chronologically and check:
- Is there a Chinese post that predates the first non-Chinese post on the same topic?
- On average, do Chinese posts appear before, after, or simultaneously with non-Chinese posts?
- Do Chinese sources report MiniMax releases earlier or later than Western sources?

This requires date stamps on all results (X posts show date, YouTube videos show date, web results have date signal). Build a timing table:

| Topic / Release | First Chinese Result | First Non-Chinese Result | Lead/Lag |
|-----------------|---------------------|------------------------|----------|
| MiniMax M2.7 announcement | | | |
| DeepSeek V4 price cut (cross-model) | | | |

**Rationale:** The key question is whether Chinese discourse on MiniMax is substantively different (topic focus) and faster (timing lead) than Western discourse. This Unit is the core analytical comparison — not variant segmentation.

**Test scenarios:**
- Chinese and non-Chinese result subsets each contain ≥5 items for at least 3 queries
- Subject matter classification produces distinct topic clusters per language segment
- Timing comparison is possible for at least 3 query result sets
- At least one clear timing lead or lag pattern is identified

**Verification:**
- Subject matter comparison table exists with ≥5 rows
- Timing comparison table exists with ≥3 rows
- A written summary of key differences (subject matter and timing) is produced

---

- [ ] **Unit 5: Language Segmentation — Chinese-Language Conversation**

**Goal:** Surface Chinese-language discussion of MiniMax (and control models) which may be absent or diluted in English-only queries

**Requirements:** R4

**Dependencies:** Unit 2

**Files:**
- Create: `docs/research/minimax-conversation/minimax-chinese-queries.md`
- Create: `docs/research/minimax-conversation/qwen-chinese-queries.md`
- Create: `docs/research/minimax-conversation/deepseek-chinese-queries.md`

**Approach:**
Run with explicit Chinese-language query variants. Note: last30days.py does not have a language filter flag — this is handled by query terminology:

1. `last30days.py "MiniMax M2.7"` --emit=compact
2. `last30days.py "小莫AI"` --emit=compact  (if applicable)
3. `last30days.py "Minimax 视频"` --emit=compact  (MiniMax + video)
4. `last30days.py "Qwen 3.7"` --emit=compact
5. `last30days.py "DeepSeek V4"` --emit=compact

Also search for Japanese-language handles/variants:
6. `last30days.py "Minimax M2.7 使い方"` --emit=compact (MiniMax usage in Japanese)
7. `last30days.py "Qwen 使い方"` --emit=compact

**Patterns to follow:**
- Compare result counts and themes between brand-name queries and native-language queries
- Note: web results may be in mixed languages; X posts often bilingual

**Test scenarios:**
- At least one non-English query returns Chinese or Japanese language results
- Language-specific results show different theme emphasis vs. English query

**Verification:**
- Chinese/Japanese query files exist with results from at least X + web sources
- Cross-language comparison notes are produced

---

- [ ] **Unit 6: Use-Case / Keyword Segmentation**

**Goal:** Disaggregate conversation by functional use-case to understand where MiniMax wins, loses, and gaps exist vs. competitors

**Requirements:** R5

**Dependencies:** Unit 2

**Files:**
- Create: `docs/research/minimax-conversation/use-case-coding.md`
- Create: `docs/research/minimax-conversation/use-case-video.md`
- Create: `docs/research/minimax-conversation/use-case-image.md`
- Create: `docs/research/minimax-conversation/use-case-speech-music.md`
- Create: `docs/research/minimax-conversation/use-case-agent.md`

**Approach:**
Run keyword-scoped queries for each model. Compare results across models per use-case:

**Coding:**
- `last30days.py "Minimax coding"` --emit=compact
- `last30days.py "Qwen coding"` --emit=compact
- `last30days.py "DeepSeek coding"` --emit=compact

**Video generation:**
- `last30days.py "Minimax video Sora"` --emit=compact
- `last30days.py "Qwen video"` --emit=compact (no direct DeepSeek video equivalent)

**Image generation:**
- `last30days.py "Minimax image generate"` --emit=compact
- `last30days.py "Qwen image"` --emit=compact

**Speech/Music:**
- `last30days.py "Minimax speech audio"` --emit=compact
- `last30days.py "Minimax music"` --emit=compact

**Agentic/CLI:**
- `last30days.py "MiniMax agent Claude Code"` --emit=compact
- `last30days.py "Qwen agent Claude Code"` --emit=compact
- `last30days.py "DeepSeek Claude Code"` --emit=compact

**Patterns to follow:**
- Per use-case: which model dominates? Which model is absent?
- Capture top voices per use-case

**Test scenarios:**
- Each use-case query returns ≥5 total results across platforms for at least one model
- Cross-model comparison table by use-case is producible

**Verification:**
- All 5 use-case files exist
- Cross-model use-case comparison table is produced

---

- [ ] **Unit 7: Competitive Pricing / Value Conversation**

**Goal:** Surface the pricing discussion — MiniMax Token Plan vs. Qwen pricing vs. DeepSeek's 75% price cut — as a distinct conversation track

**Requirements:** R6

**Dependencies:** Unit 2

**Files:**
- Create: `docs/research/minimax-conversation/pricing-conversation.md`

**Approach:**
Run pricing-specific queries:

1. `last30days.py "Minimax Token Plan pricing"` --emit=compact
2. `last30days.py "DeepSeek price cut V4 Pro"` --emit=compact
3. `last30days.py "Qwen API pricing"` --emit=compact
4. `last30days.py "MiniMax vs DeepSeek cost comparison"` --emit=compact
5. `last30days.py "MiniMax vs Qwen pricing"` --emit=compact

Also run generic "AI model cost comparison" and "best value AI model" to capture organic pricing discussion:

6. `last30days.py "best value AI model 2026"` --emit=compact
7. `last30days.py "cheapest AI API May 2026"` --emit=compact

**Patterns to follow:**
- Pricing conversation volume vs. feature conversation volume
- Which model's pricing is most discussed and in what context (positive/negative/neutral)

**Verification:**
- Pricing conversation results captured
- Sentiment summary (positive/negative/neutral) per model on pricing

---

- [ ] **Unit 8: Synthesized Intelligence Brief**

**Goal:** Produce the final competitive intelligence document summarizing all findings

**Requirements:** R1, R2, R3, R4, R5, R6

**Dependencies:** Units 1-5, 7

**Files:**
- Create: `docs/research/minimax-conversation/INTELLIGENCE_BRIEF.md`

**Approach:**
Compile all query results into a structured brief:

1. **Conversation Volume Ranking** — which model has most X posts, YouTube videos, web coverage in the 30-day window
2. **Use-Case Dominance Map** — which model is most associated with each use-case
3. **Language Landscape** — English vs. Chinese vs. Japanese conversation split per model
4. **Model Variant Breakdown** (MiniMax only) — which variants drive most discussion
5. **Pricing Perception** — how is each model's pricing discussed
6. **Top Voices** — @handles and YouTube channels driving conversation per model
7. **Key Quotes** — verbatim highlights from highest-engagement posts per model
8. **Gaps and Opportunities** — where MiniMax is underdiscussed vs. competitors

**Verification:**
- Brief exists and covers all 8 sections
- Brief is grounded in actual query results (citations by source file)
- Comparative tables are included

## Requirements Trace

- R1. Capture a comprehensive snapshot of MiniMax conversation across X, YouTube, and web
- R2. Enable direct comparison with Qwen and DeepSeek using identical methodology
- R3. Disaggregate MiniMax conversation by model variant
- R4. Surface non-English (Chinese, Japanese) conversation streams
- R5. Segment conversation by use-case: coding, video, image, speech/music, agentic
- R6. Capture pricing/value perception as a distinct conversation track

## System-Wide Impact

- **Documentation produced:** 16+ files in `docs/research/minimax-conversation/`
- **No code changes** — research-only, no blast radius
- **Reddit excluded** until timeout issue resolved — brief should note this gap explicitly

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Reddit permanently broken | Document gap in brief; note comparison is X+YouTube+Web only |
| YouTube transcripts not available | Rely on titles and view counts; note in methodology |
| Rate limiting on repeated queries | Use `--quick` mode; space queries if 429s appear |
| 5-minute bash timeout on long runs | All queries use `--quick` to stay well under 300s global timeout |

## Documentation / Operational Notes

- Create directory `docs/research/minimax-conversation/` before running any queries
- All raw query outputs stored as `.md` files (not just in-memory)
- Final brief links to each source file for traceability
- Reddit timeout issue should be investigated separately (PRAW credentials, library update)

## Sources & References

- **Methodology source:** `last30days.py` skill at `$HOME/.claude/skills/last30days/`
- **Pilot research:** MiniMax / Qwen / DeepSeek raw outputs captured 2026-05-26