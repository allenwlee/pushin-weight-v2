<!-- {{AGENT_ATTRIBUTION}} -->
---
attribution: "{{AGENT_ATTRIBUTION}}"
title: "X Semantic Search: Secondary Prompts and Flow for Sarcasm Re-evaluation and Account Stance"
date: 2026-06-29
description: "Brainstorm for secondary LLM prompts and call flow using x_semantic_search to augment primary post classification (post_type, sentiment) with sarcasm detection and per-account stance/persona summaries. Includes production-ready prompt templates, pseudocode sequences, trigger rules, and caching for selective use in the 15-min multi-brand x-monitor loop. References current taxonomy from attribution.py and research."
tags: [x-monitoring, x-semantic-search, secondary-llm, sarcasm, account-stance, taxonomy, classification-flow, cost-control, brainstorms]
---

# X Semantic Search: Secondary Prompts and Flow for Sarcasm Re-evaluation and Account Stance

### written by Grok 4.3

## Overview

Current primary classification (see `x-monitoring/x_monitor/attribution.py::classify_post` and `build_signal_prompt`) runs post-fetch on individual posts and produces per-brand structured output for:

- `post_type`: buzz_releases | hands_on_usage | performance_comparisons | feedback_questions
- `sentiment`: positive | negative | neutral | mixed

Additional context from research (docs/research/...) includes tone flags (Sarcastic/Ironic) and discourse dimensions. Nationalism / discourse axes (e.g. `constructive_critical_us`, `china_nationalism_neutral`, `pro_domestic`, `critical_of_west`) are referenced in evolving taxonomy discussions for richer persona understanding.

**Problem this addresses**: Primary LLM (often Haiku/MiniMax-M3) on a single post can miss sarcasm, double-entendre, or "vibe-coded" intent common in AI discourse on X (see pragmatics research). It also lacks account-level persona.

**Example scenario**: A post is classified primary as:
- post_type: performance_comparisons (or feedback_questions / evaluative)
- sentiment: mixed or negative
- nationalism: constructive_critical_us (constructively critical of US models), china stance: neutral

Secondary adds value by:
- Detecting if "impressive... for a domestic model" is sarcastic dunk vs genuine.
- Building/refreshing an account stance summary (e.g. "This account frequently posts cost/performance comparisons favoring open Chinese models with skeptical but not hostile tone toward US labs").

This improves signal quality for dashboard, review, and downstream (e.g. brand presence reports) without running expensive context on every post.

## Secondary Prompt Templates

Two self-contained templates, suitable for direct insertion into the LLM classification flow (modeled exactly after `build_signal_prompt` style and output rules). Use same client pattern for consistency.

They expect structured JSON output only (no prose, no fences) for reliable parsing.

### 1. Sarcasm Re-evaluation Prompt

```text
You are an expert analyst of AI industry discourse on X (Twitter), specializing in pragmatic layers: sarcasm, irony, double-entendre, "vibe coding", dunks, and indirect criticism common in LLM discussions.

PRIMARY CLASSIFICATION (from single-post LLM):
- post_type: {post_type}
- sentiment: {sentiment}
- discourse/nationalism axes: {nationalism_axes}  (e.g. constructive_critical_us, china_nationalism_neutral, pro_domestic, critical_of_west, neutral)

CURRENT POST TEXT:
"""
{post_text}
"""
BRAND(S) IN SCOPE: {brand_ids}

RECENT ACCOUNT CONTEXT (from targeted semantic search on this username; most recent first):
"""
{recent_posts_joined}
"""

TASK - Sarcasm & Nuance Re-evaluation:
1. Re-assess the post considering the recent context for the author's typical voice.
2. Detect sarcasm, irony, or double meaning (e.g. "impressive results... if you ignore the 3x cost" or "Claude could never" style dunks, "yikes", exaggerated praise that is actually shade).
3. Reference the taxonomy:
   - post_type values: buzz_releases, hands_on_usage, performance_comparisons, feedback_questions
   - sentiment values: positive, negative, neutral, mixed
   - nationalism / stance axes examples: constructive_critical_us (constructively critical of US/Western AI), china_nationalism_neutral (neutral on China domestic models), pro_china_open_source, skeptical_of_all, etc. Flag if context shifts the primary.
4. Decide if primary labels should be revised for accuracy.
5. Output ONLY valid JSON (no explanations outside it):
{
  "sarcasm_detected": true | false,
  "sarcasm_type": "dunk" | "ironic_praise" | "understatement" | "none" | "other",
  "revised_post_type": "one of the 4 exact post_type values or null if no change",
  "revised_sentiment": "one of positive/negative/neutral/mixed or null",
  "revised_nationalism": "e.g. constructive_critical_us | china_nationalism_neutral | ... or null",
  "explanation": "1-2 sentence rationale citing specific words/phrases from post or context",
  "confidence": 0.0-1.0
}
Rules:
- If no meaningful sarcasm or shift, set sarcasm_detected=false and revisions to null.
- Use exact enum values from taxonomy above.
- Base revisions only on evidence; do not hallucinate.
- Consider Chinese/English differences in pragmatics if context indicates.
```

### 2. Account Stance Summary Prompt

```text
You are building a running persona/stance profile for an X account that posts about AI/LLM models (Chinese domestic and US labs).

ACCOUNT: @{username}
CURRENT POST (just classified):
"""
{post_text}
"""
PRIMARY LABELS: post_type={post_type}, sentiment={sentiment}, nationalism_axes={nationalism_axes}

RECENT POSTS FROM THIS ACCOUNT (semantic search results; use for pattern detection):
"""
{recent_posts_joined}
"""

TASK - Account Stance Summary:
1. Synthesize the author's typical voice, recurring themes, and stances on:
   - US/Western models (e.g. Claude, GPT, Grok) vs domestic/open Chinese (MiniMax, Qwen, DeepSeek, GLM)
   - Performance, cost, agentic capability, openness, "sovereignty"
   - Nationalism lean: pro-China, neutral/factual, constructively critical of US, both-sides, dismissive of all, etc.
2. Use the taxonomy references for consistency:
   - post_type, sentiment as defined in primary classifier.
   - Nationalism axes: constructive_critical_us, china_nationalism (pro/neutral/anti variants), etc.
3. Note evolution or consistency vs the current post.
4. Output ONLY this exact JSON structure (parseable, no extra text):
{
  "account_stance_summary": "Concise 2-4 sentence persona description. E.g. 'Account @foo frequently shares hands-on evals favoring cost-effective Chinese open models; tone is constructively critical of US labs on transparency and pricing while remaining neutral-to-positive on domestic tech. Avoids hype; often highlights practical agent workflows.'",
  "dominant_nationalism_axis": "e.g. constructive_critical_us | china_nationalism_neutral | pro_domestic_open | skeptical_both | neutral_factual",
  "recurring_themes": ["cost", "agentic", "open_weights", "distillation", "slop"],
  "sarcasm_tendency": "high" | "medium" | "low" | "unknown",
  "confidence": 0.0-1.0,
  "last_updated_context_window": "e.g. last 7-14 days from provided posts"
}
Rules:
- Be factual and cite patterns from provided posts only.
- Keep summary short, actionable for DevRel monitoring.
- If insufficient context, use "insufficient_data" and lower confidence.
- Output must be valid minified or pretty JSON but no ``` fences or prose.
```

Usage note: Feed the primary labels + fetched context into these (substitute the {placeholders} or use f-string / template). Call via the same `AnthropicClaudeClient` (or equivalent) with a suitable model (Haiku for cost or stronger if nuance critical). Parse the returned dict after stripping fences (see attribution.py `_call...` + `messages_create` wrapper).

## Sample Call Sequences

Python-style pseudocode / near-exact (using project patterns from `x_monitor/run.py`, `attribution.py`, and observed `x_semantic_search` tool usage in research). Assume imports and clients initialized upstream in the pipeline.

### (a) Primary Post Classification (current flow)

```python
from x_monitor.attribution import classify_post, BrandRow, AnthropicClaudeClient
from x_monitor.store import Store  # or however brands loaded

# In post-processing after fetch + brand attribution
store = Store(...)
brands: list[BrandRow] = store.read_brands()
client = AnthropicClaudeClient(...)  # or from env / config; supports minimax proxy

post_text = post["text"]
relevant_brand_ids = [...]  # from attribute_to_brands or per-post

primary_classifications: dict[str, tuple[str, str]] = classify_post(
    text=post_text,
    brand_ids=relevant_brand_ids,
    brand_registry=brands,
    anthropic_client=client
)
# e.g. {"minimax": ("performance_comparisons", "mixed")}
# Later: store or enrich post with these (post_type, sentiment)
```

### (b) Targeted x_semantic_search for Account Context

Use usernames filter + from_date for recency (7-30 days typical window for persona; keeps token count low).

```python
# Pseudocode using available x tools (as demonstrated in docs/research pragmatics files)
from datetime import datetime, timedelta
# Assume tool available in context (MCP / direct; research examples use x_semantic_search directly)
# In production wrap in a thin x_monitor/x_client.py or reuse apify if applicable

def fetch_account_context(username: str, days_back: int = 14, limit: int = 8) -> list[dict]:
    since = (datetime.utcnow() - timedelta(days=days_back)).date().isoformat()
    # Query focused on AI/LLM to improve relevance (or broad for persona)
    query = "LLM OR AI OR model OR (MiniMax OR Qwen OR DeepSeek OR Claude OR Grok)"
    results = x_semantic_search(
        query=query,
        usernames=[username],   # filter to this account only
        from_date=since,
        # to_date=... optional
        limit=limit,
        # min_score_threshold optional for quality
    )
    return results  # list of post dicts with text, created_at, etc.

recent_posts = fetch_account_context(post["author_handle"])
context_blob = "\n---\n".join(
    f"[{p.get(\"created_at\",\"\")}]: {p.get(\"text\",\"\")[:500]}" for p in recent_posts
)
```

### (c) Combine + Secondary LLM Call

```python
def run_secondary_sarcasm_and_stance(
    post_text: str,
    primary: dict,  # e.g. from classify_post
    recent_context: str,
    username: str,
    client: AnthropicClaudeClient
) -> dict:
    # Build inputs (example for one brand; loop as needed)
    brand_id = next(iter(primary)) if primary else "unknown"
    pt, sent = primary.get(brand_id, ("hands_on_usage", "neutral"))
    # Assume or derive nationalism from primary or text heuristics for now
    nationalism = "constructive_critical_us, china_nationalism_neutral"  # placeholder; future field

    # 1. Sarcasm re-eval
    sarcasm_prompt = build_sarcasm_re_evaluation_prompt(  # template fn that does the substitutions
        post_text=post_text,
        post_type=pt,
        sentiment=sent,
        nationalism_axes=nationalism,
        brand_ids=[brand_id],
        recent_posts_joined=recent_context
    )
    sarc_resp = client.messages_create(
        model="claude-haiku-4-5",  # or current _SIGNAL_MODEL
        max_tokens=512,
        messages=[{"role": "user", "content": sarcasm_prompt}]
    )
    # Wrapper in real client already does json.loads + fence strip
    sarcasm_result = sarc_resp  # the parsed dict

    # 2. Account stance (can be cached; see below)
    stance_prompt = build_account_stance_prompt(
        username=username,
        post_text=post_text,
        post_type=pt,
        sentiment=sent,
        nationalism_axes=nationalism,
        recent_posts_joined=recent_context
    )
    stance_resp = client.messages_create(...)  # same pattern
    stance_result = stance_resp

    return {
        "sarcasm": sarcasm_result,
        "stance": stance_result,
        # merge revised labels back if desired
    }

# Usage after primary
if should_invoke_secondary(post):
    context = fetch_account_context(...)
    secondary = run_secondary_sarcasm_and_stance(post_text, primary_classifications, context, username, client)
    # e.g. apply revisions: if secondary["sarcasm"]["sarcasm_detected"]: ...
```

(Production tip: extract `build_*_prompt` helpers parallel to `build_signal_prompt`; reuse the messages_create + parse wrapper.)

## Trigger Rules and Caching Strategy

### Trigger Rules (selective invocation)

Invoke secondary **only when value > cost/latency**. Heuristics (implement in post-processing after primary classify, before/after store):

- **Taxonomy / content based**:
  - post_type in {"performance_comparisons", "feedback_questions"} (evaluative/critical prone, high sarcasm risk)
  - sentiment in {"mixed", "negative"} or primary flags nuance
  - Text contains sarcasm cues: "impressive", "yikes", "could never", "interesting", "for a ...", "if you", Chinese 阴阳 indicators if detected, or "翻车" etc.
  - Nationalism keywords or primary future field indicates "constructive_critical_*" or china stance discussion

- **Engagement / priority**:
  - High engagement: like_count >= 20 or quote_count > 0 or retweets (amplifies impact of misread tone)
  - From high-signal accounts (official, staff, verified in accounts graph) or recently active authors

- **Confidence / history**:
  - Low primary confidence (extend classify_post to return conf, or use heuristic: short text, multi-brand, etc.)
  - Account triggered secondary in last N posts (to keep persona fresh)
  - First-seen account in window

- **Sampling / budget**:
  - Global rate limit: e.g. max 30 secondary calls per 15-min cycle across all brands
  - Or per-brand cap
  - Always skip if total LLM spend projected over daily budget

Default: ~5-15% of kept posts hit secondary. Falls back gracefully (use primary only).

Example guard in flow:
```python
if (post_type in EVALUATIVE_TYPES or 
    sentiment == "mixed" or 
    post.get("like_count", 0) > 30 or
    username in recent_secondary_accounts):
    ... invoke
```

### Caching Strategy

**Account stance summaries** (the expensive persona one):

- TTL: 45-90 minutes (balances freshness for active accounts vs cost; 30 min min for very active)
- Key: f"{username}:{date_window}"  e.g. "user123:2026-06-29" or finer "user123:2026-06-29-14" (for sub-day)
- Storage options (simple, no new deps):
  - In-memory: stance_cache: dict[str, tuple[dict, float]] in RunPipeline or a StanceCache class (like HeadlinesCache)
  - File-backed: data/cache/account_stance/{username}.json with {"summary": {...}, "ts": iso, "window": "..."}
  - On hit: if now - ts < TTL and window overlaps current, reuse
  - Write after successful secondary stance call
  - Invalidate: on explicit (operator cmd) or if account posts volume high (count > X in window)
- Sarcasm re-eval: **per-post, no cache** (or very short 5-min if same post reprocessed)

Benefits in 15-min multi-brand flow:
- Repeated mentions of same account in one poll cycle hit cache.
- Across cycles, persona stable for non-viral accounts.
- Simple dict + file write keeps it lightweight; can later promote to store table if needed.

Example stub:
```python
STANCE_TTL_MIN = 60
def get_cached_stance(username: str) -> dict | None:
    ...
    if time.time() - entry_ts < STANCE_TTL_MIN * 60:
        return cached
```

## Practical Integration Notes for 15-min Multi-Brand Flow

- Location: After `classify_post` (and relevance/attribute) in `filter_and_review` or post-keep step in run.py / pipeline. Before or after `store.insert_posts`.
- Cost/latency control: secondary only on trigger + cache hits + budget caps. Primary remains always-on (cheap Haiku).
- Model choice: reuse `_resolve_signal_model()` or force cheaper for secondary when possible.
- Error handling: secondary failure must never drop the post; log warn + fall back to primary labels.
- DB / schema impact: initially store secondary results as JSON blob in new `post_secondary` column or side table (or enrich metadata). Later migrate if stable. Account stance can live in memory + periodic flush to accounts table.
- Observability: log % posts hitting secondary, cache hit rate, avg tokens for secondary, sarcasm flip rate.
- Testing: add to tests/test_*.py using FakeClaudeClient; seed example posts with known sarcasm.
- Rollout: feature flag in config.yaml e.g. `secondary_sarcasm_enabled: true`, `secondary_max_per_cycle: 20`

This keeps the core 15-min loop (wide-net fetch -> filter -> attribute -> primary classify -> store) fast while layering depth selectively where sarcasm + persona add signal (e.g. critical US/China stances that are actually ironic).

## Open Questions and Next Steps

- Exact nationalism/discourse_role taxonomy values and where they live today (primary classify extension? separate role_labels?); need to align secondary prompts once finalized.
- Should revised labels from sarcasm flow back into primary post_type/sentiment columns or be additive flags only?
- Implement `x_semantic_search` wrapper in x_monitor (or reuse existing X client)? Research uses direct; prod needs rate limiting, error handling, auth.
- Cache implementation: in-mem only first, or file? Persistence across restarts?
- Cost modeling: secondary ~2-3x primary tokens (context); estimate per-15min impact on MiniMax/Anthropic bill.
- Add confidence output from primary? Enables better triggers.
- Follow-up plan file? User to decide if promote to `docs/plans/`.
- Validation: run live on a few accounts with known sarcastic style (use x tools to sample), compare primary vs secondary+context labels.

Next: prototype the two build_ functions + trigger predicate in a branch off main; test with fake client + real x_semantic_search samples from research notes.

---

**References for implementation** (do not modify):
- Primary flow: x-monitoring/x_monitor/attribution.py (build_signal_prompt, classify_post, AnthropicClaudeClient)
- Pipeline: x-monitoring/x_monitor/run.py (classify_post calls, filter_and_review)
- Taxonomy research: docs/research/2026-06-24-*-taxonomy*.md + pragmatics prompt files
- Tool usage examples: x_keyword_search + x_semantic_search calls in recent research mds

Scope delivered vs plan promised: match
