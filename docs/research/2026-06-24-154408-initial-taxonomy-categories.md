<!-- {{AGENT_ATTRIBUTION}} -->
---
attribution: "Grok"
title: "Initial Detailed Taxonomy: Categories 1 (Type), 2 (Sentiment), and 3 (Aspect)"
date: 2026-06-24
description: "Full details of the original, unsimplified taxonomy lists for post categorization before consolidation into 3-4 buckets. Includes the initial long lists for Type/Intent (Cat 1), Sentiment/Valence (Cat 2), and Aspect/Dimension (Cat 3) proposed for AI brand monitoring on X."
tags: [taxonomy, categorization, initial-proposal, type, sentiment, aspect, x-posts, ai-brands]
---

# Initial Detailed Taxonomy: Categories 1 (Type), 2 (Sentiment), and 3 (Aspect)

**Note**: This document preserves the *initial* (pre-simplification) detailed lists from the taxonomy design phase. These were later consolidated for DevRel usability (especially for Chinese staff and smaller datasets on Chinese models).

The original request was for two scales:
- (1) Type
- (2) Sentiment

A third scale was added during design:
- (3) Aspect

These detailed lists were data-driven from actual X posts about brands like Qwen, GLM/Z.ai, MiniMax, DeepSeek, Anthropic, xAI, etc.

---

## Category 1: Post Type / Communicative Intent (Original Detailed List)

This was the primary scale for the "what kind of post is this?" dimension. The initial proposal included a rich set of categories (with allowance for multi-label in practice).

**Initial detailed categories (before reduction to 4 buckets):**

- **Announcement / Release** — Sharing or reacting to official model drops, updates, papers, HF releases, pricing changes.
- **Sharing & Amplification** — Reposting news, demos, third-party sharing of releases or positive content.
- **Technical Discussion / Analysis** — Deep dives into architecture, training techniques, post-training, ablations, etc.
- **Benchmark / Evaluation** — Posts focused on scores, leaderboards, specific evals (SWE-bench, MMLU, Terminal-Bench), or "benchmark vs real world" critiques.
- **User Experience Report** — First-hand accounts of using the model in workflows (coding agents, long context, agents, local running, production). Includes demos/screenshots/videos.
- **Troubleshooting / Bug Report** — Reports of failures, hallucinations in specific domains, regressions, "nerfed", limitations.
- **Question / Inquiry / Help-seeking** — How do I...? What's the best for X? Clarification on claims, troubleshooting.
- **Suggestion / Feature Request** — Explicit "They should add...", wishlist for next version.
- **Comparison / Head-to-Head** — Explicit "A vs B vs C" for a use case or overall ranking.
- **Speculation / Hype / Rumor** — "Probably distilled", "marketing hype", unverified claims, future predictions.
- **Humor / Meme / Cultural** — Memes, jokes, shitposts about the brand/model.
- **News / Media Link Amplification** — Linking external coverage or articles.
- **Meta / Community** — Posts about the brand's community, meta discussions.

**Rationale (from initial design)**: These were derived from patterns in real posts (rankings, "I tried it", launch reactions, "benchmarks lie", pricing talks, etc.). Too granular for small datasets, hence later grouped.

---

## Category 2: Sentiment / Valence + Tone (Original Detailed List)

Initial proposal moved beyond simple positive/negative.

**Detailed sentiment options:**

- **Strongly Positive** (hype, "game changer", "beats X", "revolutionary")
- **Mildly Positive** / Satisfied (works well for my use case)
- **Neutral / Factual** (mostly reporting specs, numbers, or neutral descriptions)
- **Mildly Negative** / Disappointed
- **Strongly Negative** (slop, useless, broken, "scam")
- **Mixed / Nuanced / Qualified** (best in class for Z, weak for W — noted as very common and valuable)
- **Sarcastic / Ironic** (flag separately — very common on tech Twitter; often carries negative or skeptical undertone, e.g. "impressive", "yikes", "shocking")

**Additional notes from initial proposal**:
- Sentiment should ideally be aspect-specific (e.g., "Positive on coding speed, Negative on cost transparency").
- Sarcasm detection is crucial on X for AI discourse.
- Emotional flavor tags (optional): excited, disappointed, skeptical, impressed, frustrated, bullish.

---

## Category 3: Aspect / Dimension (Original Detailed List)

This was the third scale added for actionability. "Aspect-based sentiment analysis (ABSA)" was recommended as far more useful than overall sentiment.

**Initial detailed aspects** (what the post is actually evaluating):

- **Reasoning / Intelligence** — General "smartness", problem-solving quality.
- **Coding / Agentic / Tool Use** — Software engineering performance, tool calling, multi-step agents, workflows.
- **Speed / Latency / Throughput** — Response time, tokens per second, efficiency.
- **Cost / Value for Money / Economics** — Pricing, discounts, token costs, overall ROI.
- **Context / Long-context Handling** — Ability to handle long inputs, 1M context claims, coherence over length.
- **Multimodal / Vision / Video** — Image, video, audio understanding/generation.
- **Openness / Licensing / Weights / Reproducibility** — Open weights, MIT/Apache license, local runnability, transparency.
- **Practical Usability / UX / Integration** — Ease of use, API quality, ecosystem (HF, local tools), developer experience.
- **Safety / Alignment / Censorship** — Behavior on sensitive topics, refusals, "Chinese model censorship".
- **Availability / Reliability** — Downtime, rate limits, consistency of service.
- **World Knowledge / Factual Accuracy** — Hallucinations, up-to-date knowledge, STEM depth.
- **Frontier Parity / "Chinese models catching up"** — Direct comparisons to Opus/Claude/GPT class, "open source catching closed".

**Rationale**: Recurring themes from sampled posts (e.g., "beats on agents but weak on knowledge", "dramatically cheaper", "1M context finally matches", "distilled?", "open weights").

These were later grouped into 4 facets for simplicity.

---

## Context and Evolution

- **Original user request**: 2 scales only (Type + Sentiment), with examples like release/informational/question and positive/negative.
- **Expansion**: Added Aspect (Cat 3) because binary sentiment + coarse type was not actionable for brands (e.g., "how is our work being received?").
- **Later simplification**: Due to (a) smaller datasets for Chinese models on X, and (b) need for simple DevRel interface → reduced to 4 Type buckets + simple Sentiment + 4 Aspect facets (with Chinese tailoring in a companion doc).
- This file preserves the *initial rich lists* for reference, audit, or future refinement.

**Related file in this directory**:
- 2026-06-24-154045-chinese-user-tailoring.md (the consolidated + localized version)

**Data sources for initial lists**: Sampled high-engagement X posts via semantic/keyword search on topics like "Qwen release", "GLM benchmark", "MiniMax vs Claude", user experiences, pricing discussions, etc. (2026 timeframe).
