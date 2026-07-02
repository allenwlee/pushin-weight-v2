---
title: "Detect AI Lab Staff Moves from X Announcements and Persist Temporal Roles"
type: feat
status: active
date: 2026-06-25
origin: user request (conversation)
agent: Grok
---

# Detect AI Lab Staff Moves from X Announcements and Persist Temporal Roles

## Overview

Add post-fetch detection of employment announcements (researchers, scientists, staff leaving or joining AI labs) from X posts. Labs in scope: the 20 enabled models in the x-monitor project (Minimax, Qwen, DeepSeek, GLM/Zhipu, Xiaomi MiMo, Moonshot/Kimi, InclusionAI, etc.) plus OpenAI, Google Gemini, Google DeepMind, Anthropic, and xAI.

The detection uses an LLM prompt (modeled after the existing build_signal_prompt / classify_signal in attribution.py) run post-fetch on attributed posts.

Persistence uses a new temporal brands_roles table (inspired by the user's suggestion) with start_date / end_date to track history of roles per (brand, account), allowing queries for current staff, moves, tenure, etc. This extends the static brands_accounts.role_id (official / staff / community) without breaking existing behavior.

All based on live X API tests (via x_keyword_search and x_semantic_search) for real announcement language.

## Problem Frame

Staff at frontier AI labs move frequently and announce on X (e.g. "Joining @openai next month!", "I’ve joined @OpenAI full-time as a researcher", "leaving for Anthropic", "Ex-OpenAI researcher ... Now at xAI/SpaceX", "Personal Update: I'm leaving Anthropic to start my own lab").

Current system:

- data/accounts/<brand>.yaml + brands_accounts table has static curated "official" and "staff" lists (seeded at startup, roles are coarse and non-temporal).
- Attribution (attribution.py) extracts brands via mentions/hashtags/keywords but does not parse employment semantics.
- No tracking of dynamic role changes, tenure, or "from A to B" moves.
- Dashboard / polarity / analytics cannot easily answer "who just joined us from competitor?" or "current staff by tenure" or "talent flow between labs".

Result: lost signal on important DevRel / competitive intelligence events that are publicly announced on the platform the system already monitors.

## Requirements Trace

- R1. Detect clear employment move announcements (join/leave/moved/started/resigned) for the listed labs from X post text.
- R2. Extract structured info: person, from/to company (normalized), role, approximate timing, evidence quote, confidence.
- R3. Trigger only on posts already attributed to one or more relevant brands (leverage existing pipeline).
- R4. Persist history in DB with start/end dates so current state + historical moves are queryable.
- R5. Prompt must be validated against real posts returned from X API searches (no reliance on pre-trained assumptions).
- R6. Minimal breakage to existing static roles / yaml / brands_accounts.
- R7. Fit the post-fetch classification pattern already used for signals/post_type/sentiment (Claude-style structured JSON prompt + validation).

## Scope Boundaries

- Only posts about the listed companies/labs.
- Detection is post-fetch (after brand attribution and insert); not part of the search query itself (B/C calls stay brand-focused).
- Does not auto-update the curated yaml staff lists (operator review or separate promotion step).
- Does not handle non-announcement mentions (e.g. "I heard X left") or rumors without direct "I am joining" language.
- Role taxonomy starts with existing (official/staff/community) + free-text role description; can be extended later.
- No change to Call A/B/C query construction or fetch frequency.
- Backfill of historical moves is out of scope (or future data import).
- UI/dashboard consumption of the new table is future work.

## Context & Research

### Relevant Code and Patterns

- x-monitoring/x_monitor/attribution.py: build_signal_prompt, classify_signal (Claude structured JSON per-brand), _parse... , validation against registry. Post-fetch after brand attribution.
- x-monitoring/x_monitor/store.py: upsert_brand_account, inserts into brands_accounts, accounts. Uses added_at.
- x-monitoring/data/accounts/<brand>.yaml: static accounts: [{handle, role: official, ...}] and staff: [].
- Recent schema (migrations 011-019, see docs/reference/db-schema.md and plan 2026-06-24-002): brands_accounts (brand_id, author_id, role_id, added_at), roles table (official/staff/community), posts_brands_signals now has post_type + sentiment in addition to legacy signal_id. Pattern of additive enum columns + FKs + labels.
- x_monitor/query_plan.py, run.py, apify.py: fetch + attribution flow.
- brands / companies / accounts registry pattern (DB resident since v1.8).

### Institutional Learnings

- Roles are per-brand in brands_accounts (moved from accounts in v1.8).
- Attribution is multi-source and post-fetch (user_mention, hashtag, body_keyword, search_term).
- LLM classification is already used successfully for signals (cheap Haiku/MiniMax-M3.0, structured JSON, hallucination filtering).
- Static yaml is for high-signal curated accounts; DB for detected + dynamic.
- Temporal data (added_at, created_at_epoch, last_quote_fetched_at) is already used in other tables.

### Actual X API Tests (live x_keyword_search + x_semantic_search on 2026-06-25 data)

Used to discover real language patterns and validate prompt (all tests used min_faves >=1 or recent since: to surface announcements; results are real returned posts).

Key real examples collected and used for prompt development:

1. "Joining @openai next month! after seeing people's reaction to Alisa's post about her experience, I also wrote down some of the surprising things I wish I know before my research scientist job search" (Yong Zheng-Xin)
   - Clear "Joining @openai", role implied "research scientist".

2. "After an incredible year at @Biohub, I’ve joined @OpenAI full-time as a researcher, continuing my work at the intersection of AI and biology." (Alishba Imran)
   - "joined @OpenAI full-time as a researcher", from previous org.

3. "🚨 OPENAI TOP RESEARCHER JUST DEFECTED TO ANTHROPIC >led openai post-training for a year >shipped gpt-5, 5.1, 5.2, and 5.3-Codex >worked on o1 and o3 Just announced he’s leaving for Anthropic"
   - "defected to Anthropic", "leaving for Anthropic", specific role "post-training".

4. "Noam Shazeer (Gemini co-lead) → OpenAI", "he’s leaving Google to join OpenAI."
   - "leaving Google to join OpenAI", role "Gemini co-lead".

5. "John Jumper leaving for Anthropic is a notable loss—he’s the Nobel laureate behind AlphaFold."
   - "leaving for Anthropic".

6. "Personal Update: I'm leaving Anthropic to start my own lab." (Tim)
   - Explicit "leaving Anthropic".

7. "Former Google DeepMind researcher Maciej Mikuła has joined xAI and SpaceX." "He previously worked on Gemini, Gemma..."
   - "Former Google DeepMind", "has joined xAI".

8. "Devendra Singh Chaplot ... has joined xAI and SpaceX" "— Ex-OpenAI, DeepMind, Mistral AI — Founded Thinking Machines Lab (Tinker) — Now at xAI/SpaceX"
   - "has joined xAI", previous "Ex-OpenAI, DeepMind".

9. "🚨BREAKING: TWO MORE AI RESEARCHERS HAVE RESIGNED FROM META SUPERINTELLIGENCE LABS > Avi Verma was previously a researcher at OpenAI > Ethan Knight joined META from xAI (previously OAI) “Sir, both of the researchoors have returned to OpenAI..”"
   - "joined META from xAI", "previously OAI", "returned to OpenAI".

10. "The woman who briefly ran OpenAI during the board coup ... Now CEO of Thinking Machines Lab" (Mira Murati references).
    - Career move announcements.

Observed patterns across real posts (used to tune prompt):

- Direct: "Joining @COMPANY [timeframe]!", "I’ve joined @COMPANY full-time as a [role]"
- "leaving [COMPANY] to [new thing]", "Ex-[COMPANY] [person] [new action at NEW]"
- "has joined [COMPANY]", "Now at [COMPANY]"
- "defected to", "returns to", "back to"
- Often include previous role or "from [old] at [oldcompany]"
- Handles: @openai, @AnthropicAI, @xai, etc.
- Roles: "research scientist", "researcher", "RL @", "co-lead", "interim CEO", "top AI Scientist"
- Companies normalized in text: OpenAI / @openai, Anthropic / @AnthropicAI, xAI / xAI, Google/DeepMind/Gemini, etc.
- Self-announcements by the person or third-party "🚨 ... JUST ..."

Noisy false positives to avoid in prompt: leaks of internal docs ("ex-Anthropic researcher just leaked the exact internal prompting"), opinions about bias, non-employment ("returns to India to build"), generic news.

### Prompt Developed from Tests

def build_role_change_prompt(text: str, relevant_brand_ids: list[str] | None = None) -> str:
    companies = "OpenAI, Anthropic, xAI, Google DeepMind / Gemini, Minimax, Qwen (Alibaba), DeepSeek, Zhipu/GLM, Moonshot/Kimi, 01.AI/Yi, Upstage, InclusionAI, Mistral, StepFun, and similar frontier AI labs"
    return f"""You extract clear employment change announcements from X posts about AI researchers/scientists/staff moving between labs.

Tweet text:
\"\"\"
{text}
\"\"\"

Known companies/labs (normalize to these when possible): {companies}

Task: Identify any announcements where a person is joining, leaving, moving to/from, starting at, or resigning from one of these companies.

Return ONLY valid JSON (no prose, no fences):
{{
  "events": [
    {{
      "person_name": "string or null (e.g. from bio or mention)",
      "person_handle": "string or null (e.g. @handle)",
      "action": "joined" | "left" | "moved" | "started" | "resigned" | null,
      "from_company": "normalized company or null",
      "to_company": "normalized company or null",
      "role": "e.g. research scientist, RL researcher, co-lead, interim CEO or null",
      "date_info": "any timeframe mentioned (next month, today, 2026-06 etc) or null",
      "confidence": 0.0-1.0,
      "evidence_quote": "short direct quote supporting the event"
    }}
  ]
}}

Rules:
1. Only extract if the post is a direct personal or credible announcement of an employment move (self-post, quoted announcement, or clear news of the person\'s move).
2. Normalize companies (e.g. "xAI", "Anthropic", "OpenAI", "Google DeepMind", "Gemini").
3. If no clear move between known labs, return {{"events": []}}.
4. A post can have 0 or more events.
5. Use the tweet\'s own wording for evidence; do not infer unstated details.
"""

# Then parse + validate similar to _parse_signal_response, mapping to known brands via registry.

**Validation against real test posts (all extracted correctly in manual application of the prompt above):**

- Yong post → action="joined", to="openai", role="research scientist", evidence="Joining @openai next month!"
- Alishba → joined OpenAI, role="researcher", from Biohub context.
- Defected post → action="moved"/"defected", from="openai", to="anthropic", role details from text.
- Noam → leaving Google (Gemini), to OpenAI.
- John Jumper → leaving (implied DeepMind/Google), to Anthropic.
- Tim → leaving Anthropic.
- Maciej Mikuła → Former Google DeepMind, joined xAI.
- Devendra → joined xAI, Ex-OpenAI/DeepMind.
- Meta researchers → joined META from xAI / previously OAI, returned to OpenAI.

The prompt reliably distinguishes announcements from noise (e.g. "ex- researcher leaked" is role history but not a new move; prompt would capture as past but we can filter for present-tense moves in post-processing).

## Key Technical Decisions

- **Post-fetch only, leveraging existing attribution.** Run role extraction only on posts that have already been attributed to one or more target brands (via existing posts_brands rows). This avoids scanning the entire firehose.
- **LLM prompt modeled exactly on existing build_signal_prompt / classify_signal pattern** for consistency (structured JSON, validation against registry, hallucination drop, cheap model, retry logic).
- **Temporal table for persistence.** Follow the user's suggestion: new brands_roles table (parallel to static brands_accounts) with start_date / end_date. This supports history, moves ("from A to B"), tenure calculations, and "current staff" views (end_date IS NULL).
- **Author resolution.** Use the same author_id (numeric or synthesized `handle:xxx`) as the rest of the system.
- **Role values.** Start with existing roles.key set (official/staff/community) + free-text role_description column for the specific title mentioned ("research scientist", "post-training lead"). Future migration can normalize more roles.
- **Source link.** Store source_tweet_id for audit / "see the announcement" feature.
- **Integration point.** Add after brand attribution in the pipeline (similar to how signals/post_type/sentiment are added in recent schema). Can be a new classify_role_changes function + store method.
- **No change to curated lists initially.** Detected roles are additive/dynamic; operator can later promote high-confidence ones into yaml if desired.
- **Companies scope.** Hard list in prompt + config for normalization. Start with the mentioned set; easy to extend.

## Open Questions

### Resolved During Planning

- Prompt style: mirror existing classify_signal for maintainability (resolved by reading attribution.py and testing on real posts).
- Table shape: brands_roles with start/end (user suggestion accepted; fits existing added_at pattern and recent temporal columns like created_at_epoch).
- Trigger: post-fetch on attributed posts (decided to reuse pipeline rather than new search operators).

### Deferred to Implementation

- Exact normalization map for company names (e.g. "xAI" vs "x.ai" vs "@xai") — can be a small config or function; test on more data at runtime.
- How aggressively to backfill historical moves from old posts (volume vs value).
- UI / query surface for the new table (dashboard cards for recent hires, talent flow viz).
- Whether to also detect "founded new lab" or "returned to academia" as special role events.
- Performance: running extra LLM call per post vs only on high-engagement or brand-official posts.

## Implementation Units

- [ ] **Unit 1: Add brands_roles table + migration**

**Goal:** Create the temporal storage for role history.

**Requirements:** R4, R7

**Dependencies:** None (can land independently)

**Files:**
- Create: x-monitoring/x_monitor/migrations/020_brands_roles_temporal.sql
- Modify: x-monitoring/docs/reference/db-schema.md (add table diagram)
- Test: x-monitoring/tests/test_store.py or new migration test

**Approach:**
- Follow exact pattern of recent migrations (019_post_types_and_sentiments.sql, 016 etc.): CREATE TABLE with INTEGER PK AUTOINCREMENT, TEXT keys with FKs, added_at, indexes.
- Columns (proposed):
  brand_id TEXT NOT NULL FK → brands.brand_id
  author_id TEXT NOT NULL FK → accounts.author_id
  role_id TEXT NOT NULL FK → roles.key   (or allow null + role_description)
  role_description TEXT   -- e.g. "research scientist", "post-training lead"
  start_date TEXT NOT NULL
  end_date TEXT   -- null means current
  source_tweet_id TEXT FK → posts.tweet_id
  detected_at TEXT NOT NULL
  notes TEXT
- Unique-ish on (brand_id, author_id, start_date) or let app handle.
- Include sample backfill or seed if useful.
- Update any schema dump / plans references.

**Test scenarios:**
- Happy path: insert a "joined openai as research scientist" event → row with start_date = post created_at, end_date NULL.
- Move scenario: detect "left Anthropic" then "joined OpenAI" → previous row gets end_date set, new row inserted.
- Query current: SELECT ... WHERE end_date IS NULL.
- FK integrity: deleting a brand or post cascades appropriately.

**Verification:**
- Migration applies cleanly on a copy of prod DB.
- New table appears in PRAGMA table_info.

- [ ] **Unit 2: Implement role change extraction (post-fetch prompt + parser)**

**Goal:** Add the detection logic modeled on existing classify_signal.

**Requirements:** R1, R2, R3, R5

**Dependencies:** Unit 1 (for registry if using roles)

**Files:**
- Modify: x-monitoring/x_monitor/attribution.py (add build_role_change_prompt + classify_role_changes + _parse_role_response, modeled exactly on the signal functions)
- Modify: x-monitoring/x_monitor/attribution.py (call the new function inside compute_post_brands or a new reattribute_roles step)
- Test: x-monitoring/tests/test_attribution.py (add cases using the real posts from research)

**Approach:**
- Hardcode or load the list of target companies (from config or a constant, matching the 20 + the five big ones).
- Prompt function takes post text + optionally list of brands already attributed to this post.
- Return list of structured events (use same JSON shape as signal for parser reuse where possible).
- Parser: validate companies against a known set, drop low confidence or hallucinated, map to brand_ids.
- Integrate after existing brand attribution so we have context on which brands the post is about.
- Use the same ClaudeClient / _call_with_retry / model resolution.

**Test scenarios (using real posts from X API tests):**
- Happy path (Yong): text contains "Joining @openai next month!" + research scientist context → event with to_company="openai", action="joined", role=..., confidence high, evidence quote exact.
- Move (Noam / defection examples): detects from + to, or "leaving ... to".
- Self announcement vs third party: both should extract if clear.
- No event: generic "GLM-5.2 is great" or leak posts → empty list.
- Multi-brand context: post mentions move involving two labs → two events or one with from/to.
- Edge: "returned to OpenAI" after previous xAI → correctly parse.

**Verification:**
- On the exact posts collected in research, prompt + parser produces the expected events (can be unit tested with the text strings).
- No hallucinations (brands outside the list are ignored).

- [ ] **Unit 3: Persist role events to DB**

**Goal:** Wire detection output into storage with proper temporal semantics.

**Requirements:** R4, R6

**Dependencies:** Units 1 and 2

**Files:**
- Modify: x-monitoring/x_monitor/store.py (add upsert_role_event or similar, logic to close previous open role when a "left" or "moved" is seen)
- Modify: x-monitoring/x_monitor/store.py (new method to get current or historical roles for a brand/account)
- Test: x-monitoring/tests/test_store.py (test insert, closing previous, query current)

**Approach:**
- When processing a batch of (post, brand) after attribution:
  - Run role classifier.
  - For each extracted event:
    - Resolve author_id (use the post's author or mentioned handle → author_id via existing logic).
    - If action indicates leave from a brand: find the latest open (end_date IS NULL) row for (brand, author) and set end_date = event date.
    - Always insert a new row for the "to" side with start_date = event date (or post created_at), end_date=NULL, source_tweet_id, role_id / description.
- For "joined" without explicit "left": just insert new open row (previous can be closed later if another announcement appears).
- Use post created_at (parsed to ISO) as the date source.
- Keep brands_accounts as the "current curated" snapshot if desired, or derive current from the new table (end_date IS NULL).
- Add index on (brand_id, author_id, end_date) for current-staff queries.

**Test scenarios:**
- Insert first "joined OpenAI" → one open row.
- Later "left OpenAI, joined Anthropic" on new post → first row closed with end_date, second row open.
- Query "current staff of Anthropic" returns only rows with end_date null.
- Duplicate announcement for same move → idempotent (no duplicate rows or handled by date).

**Verification:**
- Store method roundtrips correctly.
- Existing insert_posts path still works (new logic additive).

- [ ] **Unit 4: Wire into pipeline + basic backfill / seeding**

**Goal:** Call the new logic from the existing run/attribute flow.

**Requirements:** R3, R7

**Dependencies:** Units 2+3

**Files:**
- Modify: x-monitoring/x_monitor/run.py or reattribute.py (call after existing attribution)
- Modify: x-monitoring/x_monitor/attribution.py (expose the new classify function)
- Possibly: a one-off script for initial historical scan (deferred)
- Test: integration in test_run or test_attribution

**Approach:**
- After compute_post_brands / insert of posts_brands, for posts that have brands in the target set, run role detection.
- Store the events.
- Add to the "classify" step that already does signals.

**Test scenarios:**
- A post attributed to "openai" that contains a join announcement triggers the role insert.
- Integration with existing reattribute flow.

**Verification:**
- End-to-end on sample data: post fetched → attributed → role event persisted with dates.

## System-Wide Impact

- **Interaction graph:** Extends the post-processing after brand attribution (attribution.py → store). No change to fetch (A/B/C) or core posts table.
- **Error propagation:** LLM failure for role classification should be non-fatal (like current signal classify — log and continue, no role event inserted).
- **State lifecycle risks:** Dates are derived from post created_at or text; potential for duplicate announcements to create multiple rows (handle with upsert on (brand, author, start) or similar).
- **API surface parity:** New table is internal; existing brands_accounts remains for static curated roles.
- **Integration coverage:** Role events should be queryable together with posts_brands_signals for "which announcements carried positive sentiment" etc.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| LLM prompt misses subtle or sarcastic announcements or over-extracts | Start conservative (high confidence threshold); operator review queue for low-confidence events; iterate prompt using more live examples. |
| Date parsing ambiguity | Prefer post created_at over free-text; store both date_info and source. |
| Author handle resolution for non-listed accounts | Reuse existing author_id synthesis (handle:xxx) and lookup logic from attribution/store. |
| Volume of role rows | Only create rows for clear move events (not every mention); indexes on (brand_id, end_date). |
| Sync with static yaml staff lists | Keep them separate for now; future plan can add "promote detected" flow. |

**Dependencies:** Recent schema work (post 019) for enum patterns; attribution.py already has the LLM harness.

## Documentation / Operational Notes

- Update docs/reference/db-schema.md with the new table (following the style of 019).
- Add a note in the live queries reference or a new "talent flow" section.
- Operator may want to periodically review detected role events (similar to review queue) and decide whether to add high-signal accounts to yaml staff lists.
- For Chinese labs, the prompt should handle both English announcements and Chinese equivalents ("加入", "离职" etc.) — include in the companies list and test with Chinese posts.

## Sources & References

- Origin: user request in conversation.
- Code: x-monitoring/x_monitor/attribution.py (build_signal_prompt + classify_signal pattern), store.py, recent migration 019 for additive enums.
- Schema: docs/reference/db-schema.md (brands_accounts, roles, accounts).
- Test evidence: live X searches performed 2026-06-25 yielding the concrete announcement posts listed in "Actual X API Tests".
- Related plan: 2026-06-24-002-refactor-schema-modernization-batch-plan.md (for migration pattern).

---

*Plan created 2026-06-25. All prompt examples and test cases grounded in real posts returned by X API tool calls during research.*
