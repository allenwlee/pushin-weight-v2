---
date: 2026-05-30
topic: x-conversation-intelligence
---
# X Conversation Intelligence — Daily Monitoring System

## Problem Frame

MiniMax devrel needs a systematic, daily picture of the X conversation around AI models — who is talking, what they are saying, who actually shapes the narrative, and what the psychological disposition of key voices is toward MiniMax and its competitors. The existing research (last30days.py) is manual and one-shot; this system automates continuous collection and LLM-powered profiling.

**Who is affected:** MiniMax developer relations team  
**What is changing:** From ad-hoc research to automated daily intelligence  
**Why it matters:** Devrel cannot engage effectively without knowing who the real influencers are, where conversation is happening, and how sentiment is shifting

---

## Requirements

### Data Collection

- **R1.** Collect posts daily from X via Apify `automation-lab/twitter-scraper` actor
- **R2.** Run brand-name search queries per target (see target tiers below)
- **R3.** Collect all available metadata per post: author handle, text, timestamp, likes, retakes, reply count, quote count, language (if detectable), media URLs
- **R4.** Store raw posts in SQLite database — append-only, dedupe by tweet ID
- **R5.** Track language distribution per brand per day to identify resource allocation signals
- **R6.** Run collection daily via cron or manual trigger; log collection run (timestamp, query, post count, errors)

### Target Tiers

**Detailed targets — queries: `"MiniMax"`, `"DeepSeek"`, `"Qwen"`, `"GLM"`, `"Zhipu AI"`, `"Kimi"`, `"Moonshot AI"`**
- **R7.** For each unique author who posts about a detailed target, run LLM profiling to generate:
  - Influence tier: `thought_leader` / `active_participant` / `occasional_mentioner`
  - Narrative role: `primary_shaper` / `amplifier` / `independent_voice` / `isolated`
  - Recurring themes (top 3–5 topics this author discusses re: AI)
  - Psychological disposition toward the brand: `advocate` / `neutral` / `skeptic` / `critic` / `opportunist`
  - Credibility signal: `consistent_expertise` / `generalist` / `unknown`
  - Behavioral summary: posting frequency pattern, engagement style
  - Network position: primary community/camp this author belongs to (if identifiable)
- **R8.** Profile is recomputed when author is re-encountered (incremental update, not full rebuild unless 50+ new posts have been collected since last profile)
- **R9.** Top 50–100 authors by engagement volume receive deep profiling; remaining authors receive medium profiling (influence tier + psychological disposition + credibility signal only — omitting narrative role, recurring themes, behavioral summary, and network position)

**Benchmark targets — queries: `"OpenAI"`, `"Claude AI"`, `"Gemini AI"`**
- **R10.** Track aggregate volume per benchmark brand: daily post count, unique author count
- **R11.** Identify top 10 influencers per benchmark brand by engagement score (likes + retakes×2 + quotes×3 + replies), store handle and engagement score — no LLM profiling

### Author Deduplication

- **R12.** Normalize handles (strip @, lowercase) for deduplication
- **R13.** Detect likely bot accounts via: (a) avg >10 faves per post, (b) 0 replies across posts, (c) no bio text; exclude institutional accounts (verified handles, known official brand/model accounts) from bot scoring regardless of ratio; flag remaining matches for review but do not exclude automatically
- **R14.** Track cross-brand authors: if the same handle appears across multiple brands, note the dual-interest author in their profile

### Engagement Scoring

- **R15.** Author influence score = likes + (retakes × 2) + (quotes × 3) + replies, summed across all collected posts. Used for: R9 top-author selection, R11 benchmark ranking, R19 trends comparison, R20 CLI sorting

### CLI Query Interface

- **R16.** `cli.py authors --brand <brand> [--tier deep|medium|benchmark]` — list authors sorted by influence score
- **R17.** `cli.py authors --handle <handle>` — show full author profile including psychological summary
- **R18.** `cli.py summary --brand <brand>` — show aggregate stats: total posts (all time / 7d / 30d), unique authors, top influencers, language breakdown
- **R19.** `cli.py volume --brand <brand> [--period 7d|30d]` — show daily post volume over time
- **R20.** `cli.py trends --brand <brand>` — show which authors are rising or falling in engagement vs. prior 30-day period
- **R21.** All output in structured text format suitable for piping or copying into reports

---

## Success Criteria

- SC1. Daily collection runs unattended and captures all posts matching brand queries for that day
- SC2. Author universe grows daily as new authors are encountered; first encounter triggers profiling
- SC3. Devrel can query "who are the top 10 voices talking about MiniMax right now" and get names, influence tier, disposition, and psychological summary
- SC4. Devrel can compare conversation volume across all detailed and benchmark brands for any rolling window
- SC5. Language breakdown is visible per brand per day, enabling resource allocation decisions
- SC6. Profiles survive tool restarts (stored in SQLite, not memory)

---

## Scope Boundaries

- **Out of scope:** Posting to X, engaging with authors, automated alerts or Slack notifications
- **Out of scope:** YouTube, Reddit, web (X only for MVP)
- **Out of scope:** Multi-user access control (single-user MVP)
- **Not doing:** Explicit bot filtering/removal beyond flagging; manual review is a future step

---

## Key Decisions

- **SQLite for MVP**: Simple, zero-operations, portable. Schema designed to be compatible with PostgreSQL migration for multi-user Phase 2
- **MiniMax LLM for profiling**: Cheaper than Claude; fits the internal tooling stack. Swap-in point for Claude when budget allows
- **Apify actor as sole collector**: fxtwitter doesn't support search; X free API doesn't support search; Apify is the practical daily-driver option at ~$0.003/tweet
- **Brand-name queries only**: Avoids query complexity; organic conversation surfaces naturally under brand names
- **Single-user MVP**: No auth, no multi-tenancy. Multi-user expansion is a Phase 2 item

---

## Dependencies / Assumptions

- **D1.** Apify API token (`openclaw-APIFY_API_TOKEN`) is available and has budget headroom (~1,600 tweets/month free tier, ~$5/mo credit)
- **D2.** LLM API key (MiniMax) is available for profiling calls
- **D3.** X cookies (`auth_token`, `ct0`) available for Apify search mode (required for full search syntax)
- **D4.** Server is fuchitalee; cron access available; disk space adequate for SQLite growth
- **D5.** Kimi = Moonshot AI (same entity, queried under both names); GLM = Zhipu AI (same entity, queried under both names)

---

## Outstanding Questions

### Resolve Before Planning
*(All Q1–Q3 resolved)*

### Deferred to Phase 2

- **[Q4]** How should multi-user access be implemented?
- **[Q5]** Should the system emit any notifications (Slack/email)?
- **[Q6]** Should we backfill historical posts on first run?

---

## Next Steps

-> `/ce:plan` for structured implementation planning

EOF'