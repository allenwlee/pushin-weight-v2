<!-- {{AGENT_ATTRIBUTION}} -->
---
attribution: "Grok"
title: "Ongoing Inductive Refinement for Taxonomy Aspects"
date: 2026-06-24
description: "Actionable sketch for evolving the Aspect dimension of the AI brand post taxonomy inductively from the growing wide-net corpus. Replaces legacy signals, supports DevRel alerts and UI, allows data-driven refinement of the 4 Aspects while capping granularity."
tags: [taxonomy, devrel, inductive, aspects, refinement, x-monitoring, wide-net, sentiment, classification, posts, post_brand_signals]
---

# Ongoing Inductive Refinement for Taxonomy Aspects

### written by Grok 4.3

**Date**: 2026-06-24 (JST)

## Context and Motivation

The current taxonomy (detailed in [2026-06-24-155117-simplified-taxonomy.md](./2026-06-24-155117-simplified-taxonomy.md)) consolidates to:

- **4 Type buckets** (Buzz & Releases / 发布与热度, Hands-on Usage / 实际使用体验, Performance & Comparisons / 性能与对比, Feedback & Questions / 问题与建议)
- **Sentiment** (Positive / Negative / Neutral / Mixed)
- **4 Aspects** (cross-cutting): Agentic & Workflows / 智能体与流程, Coding & Engineering / 编程与开发, Cost/Speed/Value / 性价比与效率, Core Capabilities & Openness / 核心能力与开源

Plus China-specific tags: 中文理解, 国产生态/性价比, 合规与安全, 国产骄傲 (see also [2026-06-24-154045-chinese-user-tailoring.md](./2026-06-24-154045-chinese-user-tailoring.md) and the original detailed lists in [2026-06-24-154408-initial-taxonomy-categories.md](./2026-06-24-154408-initial-taxonomy-categories.md)).

**Collection is shifting to wide net** (brand mentions only via broad queries such as Call B in the two-call design — see plans like 2026-06-17-001-refactor-two-call-wide-net-translation-plan.md) followed by **post-fetch classification**. This replaces the old pre-bucketed intent calls and the legacy 6 signals stored in `post_brand_signals` (and historically `posts.signal`): `release`, `community_question`, `criticism`, `commenter_capture`, `praise`, `other` (defined in migration 008_enum_i18n_lookup_tables.sql and surfaced via the legacy `intent_classifier.py` / current `attribution.py` shims).

**Why inductive refinement for Aspects?** The initial Aspects (and the full detailed lists) were derived from small, targeted samples. With the wide-net approach we will accumulate a much larger corpus over time. Aspects should emerge bottom-up from actual collected data to avoid arbitrariness and user's concern on arbitrary granularity. Fresh sampling already shows natural patterns: heavy agentic/coding mentions, strong cost/value emphasis for Chinese models, openness comparisons, and real-world workflow feedback. The taxonomy must stay useful for DevRel (simple UI filters, actionable alerts) while evolving.

## Inductive Process (Data-Driven Evolution)

1. **Collect wide net**: Brand-token mentions only (no pre-filtered "intent" queries). Persist to `posts` table. Attribute via `posts_brands` / brand detection (author + body keywords etc.).

2. **Post-fetch classification** (run after per-brand filter / relevance):
   - Apply current 4 Type buckets + Sentiment (multi-label where appropriate).
   - **Free-text aspect extraction** via LLM: Prompt example: "List specific dimensions mentioned in this post about the model(s). Be concrete and short: e.g. agent workflows, tool calling issues, pricing / compute cost, coding quality / SWE-bench, long context / memory, inference speed / latency, openness / weights / ecosystem, Chinese language understanding, domestic ecosystem value, compliance / safety, national pride framing, comparisons to closed models, harness/tool use, etc. Return as a comma-separated list or JSON array. Only include dimensions actually referenced."
   - Store the free aspects (new column or side table `post_free_aspects` or JSON in `posts` or linked to `post_brand_signals` evolution).

3. **Store free aspects**: Keep raw extracted phrases + normalized forms for aggregation. This augments (does not immediately replace) the fixed 4 Aspects.

4. **Periodic aggregation & clustering** (e.g., weekly cron, or after N=500 posts per brand, or on demand):
   - Use LLM summarizer (Grok for English/global; Qwen/GLM or equivalent for Chinese/domestic text) or simple frequency + embedding clustering.
   - Identify emerging stable clusters (e.g. "long context/memory", "inference efficiency / cost reduction", "domestic ecosystem / 国产生态", "harness / tool calling robustness").
   - Map emerging ones back to the 4 core Aspects or propose splits/adds.

## Refinement Steps

- **Map new dimensions** to the existing 4 Aspects first (prefer consolidation).
- **Split only when volume warrants**: e.g., if Cost/Speed/Value volume is high and complaints cluster separately around "price" vs "latency/TPS", consider splitting into Cost/Value and Speed/Latency as sub-filters (keep top-level to 4-6 max).
- **Update artifacts**:
  - LLM classification prompts (in pipeline / attribution layer or new taxonomy classifier module).
  - UI filters in dashboard (x-monitoring dashboard.py / templates; add pills or facets for new stable aspects).
  - Alert rules (see simplified-taxonomy suggestions): e.g. Feedback+Negative spikes, Agentic+Positive wins, Cost/Value+Negative pricing alerts, China surges in 国产骄傲 or 中文理解.
  - Re-evaluate the 4 Type buckets if corpus patterns demand (rare; they are intentionally coarse).
- **China-specific monitoring**: When Weibo/Zhihu integration lands (future), run the same free-aspect extraction. Watch for new stable terms around 合规与安全 (regulatory/compliance framing) and 国产骄傲 (positive national-competitiveness framing). Domestic platforms often surface price sensitivity and ecosystem loyalty more strongly than X.
- **Versioning**: Keep snapshots of taxonomy in docs/research/ (update this file + simplified-taxonomy.md when changes land). Tag stable aspects with first-seen date and supporting post volume.

## Tools and Implementation Sketch

- **DB**: `x-monitoring/data/x_monitoring.db` — `posts` (text, lang_detected, translations, etc.) + `posts_brands_signals` (or evolved table; currently keyed on legacy signals). Extend with `post_aspects` join or free-aspect JSON column + normalized lookup.
- **LLM batches**: Run over recent kept posts (filter by `fetched_at` or `created_at_epoch`). Use existing translator patterns or new `classify_aspects` function. Support bilingual: prefer Chinese-native model for zh text.
- **Pipeline addition**: 
  - In `run.py` or new `taxonomy.py` module: after filter + attribution, call aspect extractor and persist.
  - Simple script proposal (next step): `scripts/2026-06-24-extract-free-aspects.py` or integrated subcommand `x-monitor classify-aspects --since 7d --brand minimax --model gpt-4o` (or local Chinese model). Logs to stdout + DB. Idempotent on (post_id, brand).
- **Aggregation job**: Weekly script or dashboard button that clusters free aspects (use freq + simple LLM "group these phrases into 5-8 stable dimensions") and outputs diff proposals against current 4 Aspects.
- **Update taxonomy MDs**: After each refinement cycle, edit the research files and note changes + evidence (post counts, example tweets).

Example free-aspect outputs from fresh sampling that can refine labels:
- "harness/tool calling issues" → strengthens or splits Agentic & Workflows
- "compute cost reduction" / "too cheap for the quality" → Cost/Speed/Value (or dedicated value sub-aspect)
- "open weights ecosystem" / "local runnable" → Core Capabilities & Openness
- "agentic maxxing" / multi-step workflows → Agentic (or new "Agent Scale / Reliability")

## Validation

- **Human review sample**: Pull 50-100 recent posts per brand (stratified by Type/Sentiment). Blind-compare fixed Aspects vs. human-labeled free aspects. Measure agreement + actionability.
- **Alert/actionability tracking**: Before/after metrics — do Type+Sentiment+Aspect combos surface more DevRel-relevant items than legacy signals or Type+Sentiment alone? (E.g., count of "Feedback + Negative + Cost" alerts that led to real investigation.)
- **Stability metrics**: Track how often proposed new aspects survive 2-3 aggregation cycles vs. noise.
- **Granularity guard**: Audit for over-fragmentation quarterly. Rule of thumb: max 4-6 total Aspects (core + China). If a dimension appears in <2% of posts, keep as free-text tag only.

## Risks and Mitigations

- **Over-fragmentation / arbitrary granularity**: Primary risk flagged by user. Mitigation: always map-to-existing first; require volume threshold + human confirmation before promoting a free aspect to filter; document rationale in research MDs.
- **Prompt drift / LLM inconsistency**: Fix seed prompts, use temperature=0 where possible, run consistency checks across models.
- **Storage bloat**: Free aspects are small text; aggregate periodically and prune raw per-post after clustering.
- **UI complexity for DevRel**: Keep main nav as the 4 Type buckets. Aspects remain secondary multi-select filters/pills. Alerts can use aspect combos without cluttering primary view.
- **China vs global divergence**: Allow platform-specific aspect emphasis (X may emphasize openness/benchmarks; domestic may emphasize 性价比 and 国产骄傲) via filters rather than forking the taxonomy.

## How This Supports DevRel Goals and the Wide-Net Approach

The simplified 4-bucket + Sentiment + Aspects design was explicitly for "simple interface for DevRel staff" (see simplified-taxonomy.md). Inductive refinement keeps it alive and relevant as volume grows:

- **Actionable alerts** become richer without losing simplicity: "Agentic + Positive" win spikes (good for amplification), "Feedback + Negative + Cost/Value" (pricing or perf pain), "国产骄傲 + Buzz" surges around releases.
- **Comparisons & competitive intel**: Aspects highlight where Chinese models are praised for value/openness vs. where global models lead on agentic reliability.
- **Wide net benefit**: Pre-filtered collection (old 6 signals) risked missing emergent topics. Wide net + post-fetch + free-aspect storage gives discovery power from the full mention corpus while still classifying everything into the stable DevRel-friendly structure. Larger N enables statistical validation of aspects instead of anecdote-driven design.
- **Evolution path**: Legacy signals were coarse and English-leaning. The new system is bilingual-ready, aspect-aware (closer to true ABSA), and data-grounded.

## Next Steps (Actionable)

1. **Prototype free-aspect logging**: Add a minimal extractor to the pipeline (or standalone script) that runs on a sample of recent posts. Store results alongside `post_brand_signals` evolution. Use current taxonomy as base labels + free text.
2. **First aggregation pass**: After ~1 week of wide-net data or 200-300 posts/brand, run clustering and propose any immediate refinements (e.g. split hints for Cost/Speed/Value).
3. **Update prompts & dashboard**: Incorporate stable aspects into classification code and UI (preserve backward compat with legacy signals during transition).
4. **Document outcomes**: Update this file + simplified-taxonomy.md with concrete clusters, volumes, and decisions. Revisit after Weibo/Zhihu pilot.
5. **Validation loop**: Schedule human review of 1-2 aspect proposals per cycle.

This keeps the taxonomy practical and evolvable rather than frozen from small samples.

**Related files** (in docs/research/):
- 2026-06-24-155117-simplified-taxonomy.md (current canonical structure + alerts)
- 2026-06-24-154408-initial-taxonomy-categories.md (original rich lists for reference)
- 2026-06-24-154045-chinese-user-tailoring.md (bilingual + platform notes)
- Also cross-ref: x-monitoring DB schema (docs/reference/db-schema.md), attribution/intent code, wide-net plans.

*Part of ongoing taxonomy work to support DevRel monitoring as collection scales.*
