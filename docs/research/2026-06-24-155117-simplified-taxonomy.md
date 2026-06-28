<!-- {{AGENT_ATTRIBUTION}} -->
---
attribution: "Grok"
title: "Simplified Classification System for AI Brand Post Taxonomy"
date: 2026-06-24
description: "Final simplified 4-bucket taxonomy for categorizing X (and multi-platform) posts about AI brands (Qwen, GLM, MiniMax, etc.). Includes Type buckets, Sentiment, Aspects as filters, dashboard metrics/alert suggestions, and questions for setup details."
tags: [taxonomy, ai-brands, sentiment-analysis, classification, devrel, weibo, zhihu]
---

# Simplified Classification System for AI Brand Post Taxonomy

**Context**: Initial detailed categories (many Type options + many Aspects) were too granular, especially given smaller English X datasets for Chinese models like Qwen, GLM/Z.ai, MiniMax, DeepSeek, etc. The goal was a simple interface for DevRel staff.

This is the consolidated, actionable version (with bilingual/Chinese tailoring where relevant).

## 1. Post Type — 4 Top-Level Buckets (Main Navigation)

These are the primary filters/tabs in the UI. Every post gets one primary bucket (multi-label allowed for secondary).

1. **Buzz & Releases** (发布与热度)
   - Announcements, model drops, hype, viral shares, third-party amplification, memes about releases.
   - Subgroups: Official release, Third-party hype, Viral/meme.

2. **Hands-on Usage** (实际使用体验)
   - Real demos, agent runs, coding workflows, "I tried X for...", production stories, screenshots/videos.
   - Subgroups: Positive wins, Mixed/qualified, Issues/bugs found.

3. **Performance & Comparisons** (性能与对比)
   - Benchmarks, leaderboards, head-to-head rankings ("better than Claude/Grok"), technical evals.
   - Subgroups: Pure benchmark, Real-world validation, Direct vs competitor.

4. **Feedback & Questions** (问题与建议)
   - Direct questions ("how do I...?"), feature requests, pricing complaints, bug reports, suggestions.
   - Subgroups: How-to/questions, Feature requests, Criticisms/complaints.

**Why 4?** Keeps the main view scannable even with modest volume. Subgroups live inside for drill-down.

## 2. Sentiment (Simple Scale)

- **Positive**
- **Negative**
- **Neutral**
- **Mixed / Nuanced** (very common — "great on agents, weak on knowledge")

**Optional Tone flag** (for advanced view):
- Direct
- Sarcastic / Ironic (阴阳怪气 on Chinese platforms)
- Humorous

**Notes**:
- On English X: sarcasm often dry ("yikes", "impressive...").
- On Weibo/Zhihu: expressed via exaggeration, memes, indirect phrasing, or "阴阳".
- Use Chinese LLM for classification on domestic text.

## 3. Aspects — Cross-Cutting Filters (4 + China-Specific)

Applied as multi-select pills/filters on top of the 4 Type buckets.

1. **Agentic & Workflows** (智能体与流程)
   - Agents, tool calling, multi-step automation, swarms, long-horizon tasks.

2. **Coding & Engineering** (编程与开发)
   - SWE-bench, code gen, debugging, real software engineering tasks.

3. **Cost, Speed & Value** (性价比与效率)
   - Pricing, discounts, TPS/latency, token efficiency, "too good for the price".

4. **Core Capabilities & Openness** (核心能力与开源)
   - Reasoning, context (1M tokens), knowledge, open weights, local runnability, licensing.

**China-Specific Additions** (extra filters or sub-tags):
- 中文理解 (Chinese language understanding)
- 国产生态 / 性价比 (Domestic ecosystem & value)
- 合规与安全 (Compliance/safety — regulations, censorship)
- 国产骄傲 (National pride framing in positive posts)

## Platform Handling (for Chinese Models)

- **X/Twitter**: Global/international perception.
- **Weibo (微博)**: Real-time buzz, viral feedback, quick opinions. Best for Buzz & Feedback buckets.
- **Zhihu (知乎)**: In-depth comparisons, technical deep dives, long usage reports. Best for Performance & Usage.

Run with platform filter. Domestic volume is typically much higher for these brands.

## Suggested Dashboard Metrics & Alert Rules

**Core Metrics** (track over time, per brand/model, split by platform):
- Volume per Type bucket (absolute + % of total)
- Sentiment distribution (e.g., % Positive in Usage bucket)
- Aspect co-occurrence (e.g., "Agentic + Cost + Positive" spikes)
- Engagement-weighted sentiment (likes/views on positive vs negative posts)
- Competitor deltas (e.g., our "Performance + Positive" vs Claude's)

**Trend Metrics**:
- 7d/30d change in bucket volume
- "Mixed" rate (high mixed = nuanced but potentially actionable feedback)
- Sarcastic/Ironic volume (often hidden negative)

**Alert Rules** (examples for DevRel):
- Spike alert: >2x normal volume in "Feedback & Questions + Negative" for any brand in last 24h
- Win alert: Sudden increase in "Performance & Comparisons + Positive + Coding" mentions
- Risk alert: Rising "Cost, Speed & Value + Negative" (pricing complaints)
- Competitive alert: "Agentic + Positive" for a competitor exceeds threshold
- China-specific: Surge in "国产骄傲" or domestic ecosystem praise around a release

**Implementation Tips**:
- Use simple counts first, then add engagement weighting.
- Time-series charts per bucket + sentiment heatmaps.
- Export for Slack/Email alerts.
- Separate views: Global (X) vs Domestic (Weibo+Zhihu).

## Next Steps / Questions to Refine

To make this even more tailored:

What’s your current setup for collecting/annotating these posts (volume, tools, manual vs automated)?

- Volume: ~how many posts per week per brand?
- Tools: X API, Firehose, third-party (Brandwatch, etc.), custom scrapers? Same for Weibo/Zhihu?
- Annotation: Pure LLM classifier? Human review loop? Hybrid?
- Any existing dashboards or pain points?

This info will help refine buckets, prompts, and alert thresholds further.

---

**Related files in this directory**:
- 2026-06-24-154408-initial-taxonomy-categories.md (original detailed lists)
- 2026-06-24-154045-chinese-user-tailoring.md (bilingual/Chinese staff adaptations)

**Attribution note**: All agent-generated docs in this project include the "written by Grok X.Y" subheader (see global ~/.grok/AGENTS.md).

---

*Generated as part of ongoing taxonomy refinement for AI brand monitoring.*
## Fresh Sampling Methodology Update (2026-06-24)

**Update from wide-net sampling run**: See new sibling document 2026-06-24-160500-fresh-sampling-methodology.md for full methodology, exact X search queries (brand-only wide net using x_keyword_search + x_semantic_search), model coverage from yamls (minimax/qwen/deepseek/glm/xiaomi_mimo/moonshot_kimi + doubao/ernie/hunyuan/yi/sensechat/etc.), ~40+ post yield, Kimi disambiguation challenges (F1 bleed despite -antonelli/F1 filters), and 8 classified examples applying this taxonomy.

Key validation points from fresh data:
- The 4 Post Type buckets (Buzz & Releases / 发布与热度, Hands-on Usage / 实际使用体验, Performance & Comparisons / 性能与对比, Feedback & Questions / 问题与建议) + Sentiment (Positive/Negative/Neutral/Mixed + optional Sarcastic/Ironic) + Aspects (Agentic & Workflows, Coding & Engineering, Cost/Speed/Value 性价比, Core Capabilities & Openness + China tags like 中文理解, 国产骄傲) effectively classify real unfiltered posts.
- Examples (abridged):
  - GLM-5.2 Cline/VSCode tool spills (Hands-on Usage, Mixed, Agentic + Coding)
  - GLM-5.2 benchmarks + agent potential (Performance & Comparisons, Positive/Mixed, Agentic + Coding)
  - Cost 100x drops + MiniMax M3 cuts + GLM-5.2 1M context (Buzz/Performance, Positive, Cost/Value + Openness)
  - DeepSeek cheap at WeCom billion-user scale (Hands-on/Performance, Positive, Cost)
  - OSS rankings (GLM 5.2 #1, MiniMax #2, Kimi #3) (Performance & Comparisons, Positive/Mixed, Openness + Coding)
  - Doubao charging + Tesla China (Feedback & Questions, Mixed, Cost + 国产生态)
  - Chinese labs strategic paths comparison (Performance, Positive, multi-aspect)
- Challenges noted: volume skew, bilingual noise, need for yaml filters + review queue. Supports recurring wide-net sampling for unbiased bucket/sentiment distributions.

This appends practical grounding data to the taxonomy without altering core definitions.

