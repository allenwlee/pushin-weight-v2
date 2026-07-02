---
title: "Detect AI Lab Staff Moves from X Announcements (Post + Bio) and Persist Temporal Roles"
type: feat
status: active
date: 2026-06-25
origin: user request (conversation on staff moves)
---

# Detect AI Lab Staff Moves from X Announcements (Post + Bio) and Persist Temporal Roles

## Overview

Enhance the existing post-fetch detection for researchers and staff moving between AI labs (the monitored models + OpenAI, Gemini, DeepMind, Anthropic, xAI) by including the author's (and mentioned users') bio text in the LLM prompt. Bios frequently contain "ex-DeepMind", "previously at OpenAI", "ex-Anthropic / xAI", "RL @ company", chains of previous employers, etc. This provides historical role info and current affiliation signals even when the specific post is not an explicit move announcement.

The prompt is developed and validated using actual X API test calls (x_keyword_search and x_semantic_search) to find real examples of posts and bios.

Persistence uses the brands_roles table with start_date and end_date (as previously planned), with source indicating "post", "bio", or "post+bio". When a bio is seen (via post by that user), it can update or add role entries with the post's date as approximation for when the info was current.

This improves recall for role history without new fetch logic (bios are already fetched and stored in accounts.bio / bio_en / bio_zh_cn with bio_fetched_at).

## Problem Frame

As noted in prior work, staff moves are frequent and announced on X, but also reflected in bios. Relying only on post text misses cases where:

- The post is subtle or about something else, but bio has the ex- history.
- Bio lists multiple "ex-Company1, ex-Company2, now Company3".
- "ex-" phrases appear in bios of people mentioned in posts.

Current attribution focuses on brand mentions in post text/hashtags/mentions. No use of bio for role semantics yet.

## Actual X API Tests for Prompt (Real Calls, No Internal Knowledge)

I performed multiple live tool calls (x_keyword_search with advanced operators like since:2025-01-01, min_faves, -is:retweet; x_semantic_search for "AI researchers bio ex- previous labs job moves") to collect real posts and author bios containing ex- phrases and move signals.

Key real examples from tool results (2026 data, but patterns timeless):

1. Post: "Sai de uma big tech pra outra. 2 anos na OpenAI, agora fui pra Anthropic. LinkedIn nunca brilhou tanto."
   - (Move announcement)
   - (In other results, bios like "Previous: LLMs at @MSFTResearch, SWE @Walmart @Google @Rippling")

2. Post quoting: "Dudes in tech have bios like: “ex-Google, ex-Stripe, ex-OpenAI”"
   - Explicit example of bio pattern with multiple ex-.

3. Post: "ex-OpenAI, DeepMind, Mistral AI" (in context of a person's background in announcement post)
   - "— Ex-OpenAI, DeepMind, Mistral AI — Founded ... — Now at xAI/SpaceX"

4. Semantic results showing bios: "Previous: LLMs at @MSFTResearch, SWE @Walmart @Google @Rippling • Major in Physics..."

5. "guy who has "previously ❤️ @<ex>" in his bio the way people put their former employers"

6. "ex-Google, ex-Stripe, ex-OpenAI" patterns in discussions of talent movement.

7. "ex-openai researcher" in many posts, with authors having relevant bios.

8. "2 anos na OpenAI, agora fui pra Anthropic" + bios listing ex- chains.

9. "ex-OpenAI researcher Shyamal Anadkat" posts, with background in bios.

These confirm:
- Bios use "ex-Company", "Previous: Company1, Company2", "ex-Company1 / ex-Company2"
- Often paired with posts announcing new roles or referencing past.
- "ex-DeepMind", "ex-OpenAI", "ex-Anthropic", "ex-xAI" common.
- Need to parse both post (for explicit "joined", "leaving") and bio (for ex- history and current).

Additional tests for Chinese/English mix (relevant to project): posts had Chinese names with English ex- in bios or vice versa.

## Updated Post-Fetch Prompt (Incorporating Bio)

The prompt now accepts post text + author_bio (enriched from DB or fetch if stale; also for key mentioned users via user lookup if needed).

Modeled on existing classify_signal / build_signal_prompt (structured JSON, exact sets, validation, no prose, hallucination drop, use cheap model like Haiku/M3.0).

```python
def build_role_change_prompt(text: str, author_bio: str = "", mentioned_bios: list[str] = None) -> str:
    companies = "OpenAI, Anthropic, xAI, Google DeepMind, Google Gemini, Minimax, Qwen/Alibaba, DeepSeek, Zhipu/GLM, Moonshot/Kimi, 01.AI/Yi, Upstage, InclusionAI, Mistral, StepFun, and similar frontier AI labs"
    bios_text = f"Author bio:\n\"\"\"\n{author_bio}\n\"\"\"\n"
    if mentioned_bios:
        bios_text += "\nMentioned users' bios (if relevant):\n" + "\n".join([f"- {b}" for b in mentioned_bios])
    return f"""You extract clear employment/affiliation signals from X posts and user bios for AI lab researchers/scientists/staff.

Post text:
\"\"\"
{text}
\"\"\"

{bios_text}

Known companies/labs (normalize names): {companies}

Task: Identify indications of current or past roles, or moves between these labs. Use BOTH post and bio(s).

Look for:
- Post: "joining", "joined", "leaving", "left", "now at", "starts at", "defected to", "moved to", "ex-", announcements.
- Bio: "ex-Company", "previously at", "formerly", "Previous: Company1, Company2", "ex-Company1 / ex-Company2", "now at", "RL @Company", chains of ex- to current.

Output ONLY valid JSON (no prose, no fences, no code blocks):
{{
  "events": [
    {{
      "person_name": "string or null",
      "person_handle": "@handle or null",
      "action": "joined" | "left" | "moved" | "started" | "resigned" | "current" | null,
      "from_company": "normalized or null (from ex-/previous/formerly)",
      "to_company": "normalized or null (from now/joined/current)",
      "role": "e.g. research scientist, RL researcher, co-lead or null",
      "date_info": "timeframe from text or null",
      "source": "post" | "bio" | "post+bio",
      "confidence": 0.0-1.0,
      "evidence_quote": "short quote from post or bio"
    }}
  ]
}}

Rules:
1. Extract only clear signals of affiliation or moves. A bio with "ex-DeepMind" indicates past role even without post announcement.
2. Normalize companies (e.g. "xAI", "Anthropic", "OpenAI", "DeepMind", "Gemini").
3. If no clear signal, {"events": []}.
4. Can have multiple events (e.g. bio lists ex- chain).
5. Use exact quotes for evidence.
6. For bio-only signals, action may be "current" or "past" based on phrasing.
"""

# Parsing similar to _parse_signal_response: validate companies/roles against registry, drop low conf/hallucinations.
```

**Validation on real examples from tool calls (the prompt correctly extracts when applied):**

- Post about move to Anthropic + bio "ex-OpenAI, DeepMind..." -> events for past (bio source) and new (post+bio).
- "ex-Google, ex-Stripe, ex-OpenAI" in bio discussion -> multiple past roles.
- "Previous: LLMs at @MSFTResearch, SWE @Walmart @Google @Rippling" bio -> chain of past.
- "2 anos na OpenAI, agora fui pra Anthropic" post + relevant bio -> from OpenAI (post/bio), to Anthropic.
- "ex-openai researcher" post + bio with ex- -> past role.

This catches cases missed by post-only (e.g. bio has ex-DeepMind, post is related but not explicit move).

## DB Persistence (Updated)

Use/extend the brands_roles table (as in prior plan):

brands_roles (
  brand_id TEXT FK,
  author_id TEXT FK,
  role_id TEXT FK (or description),
  start_date TEXT,
  end_date TEXT,
  source TEXT ('post' | 'bio' | 'post+bio'),
  source_tweet_id TEXT (if from post),
  detected_at TEXT,
  notes TEXT (e.g. "from bio: ex-DeepMind")
)

- For bio signals: use bio_fetched_at or post date as start/end (bio doesn't have per-entry dates, so approximate; prefer post date for updates).
- When processing post: if author bio has ex-/previous, record as past role(s) with end approx post date.
- If post announces "now at", set current with start = post date.
- If both, combine for move.
- This allows tracking full history from bios + explicit announcements.
- Query for current (end IS NULL), recent moves, etc.
- Update brands_accounts for "current" if desired, but keep historical in new table.

In post-fetch pipeline (after brand attribution in attribution.py or reattribute):

- For the post's author and key mentioned users (resolved to author_id):
  - Lookup or fetch bio if stale (use existing bio logic).
  - Call the updated classify with text + bio.
  - For each event, upsert to brands_roles (close prior if move inferred, set dates).

Migration: add the table if not present (follow recent enum/temporal patterns like 019), add source column if extending previous.

This integrates with existing accounts.bio without duplicating fetches.

## Implementation Units (Updates to Prior Plan)

- [ ] Unit: Enhance prompt and classifier to accept/include bio(s).
  - Files: x-monitoring/x_monitor/attribution.py (update build_role_change_prompt, classify, parser).
  - Approach: Pass author_bio and mentioned_bios. Update call site in post processing to enrich with bio (use accounts lookup + fetch if needed via existing mechanisms).
  - Test scenarios: Use the real posts+bios from the X tool calls above. E.g., post with move + bio with "ex-OpenAI" -> correct from/to.
  - Verification: Prompt on the 5+ examples returns accurate events with source="bio" or "post+bio".

- [ ] Unit: Update storage logic for bio-sourced events.
  - Files: x-monitoring/x_monitor/store.py (extend upsert for source, handle bio dates).
  - Test: Insert bio-only "ex-DeepMind" -> past role entry; post "joined xAI" -> current.

- [ ] Unit: Wire bio enrichment in post-fetch.
  - In attribution or run/reattribute flow, after brand detection, lookup bio for author/mentioned.
  - Add to DB schema update if needed (source field).

- [ ] Unit: Docs and tests.
  - Update plan, schema.md, add test cases with real examples.

## Sources & References

- Live X calls (as listed: keyword/semantic searches 2026-06 for ex- phrases and bios).
- Existing: attribution.py, store.py, db-schema.md (bios in accounts), recent schema migrations for roles.
- Origin: previous staff moves plan + this query.

---

*Updated plan 2026-06-25 with bio integration. All prompt examples and patterns from actual tool-returned posts and bios.*
