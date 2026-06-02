# {{AGENT_ATTRIBUTION}}

---
title: "Conversation Intelligence Research — Plan Template"
type: feat
status: template
template_version: 1.0
derived_from: "20260526/consumer/2026-05-26-001-feat-minimax-conversation-research-plan.md"
---

# Conversation Intelligence Research — Plan Template

A reusable plan for running `last30days.py`-based competitive intelligence research on any subject (one or many entities, any window). Two modes: **breaking-news** (single subject, 1-3 day window, dense launch-day coverage) and **landscape** (1-5 subjects, 30-day window, broad mapping). Pick the mode in the Overview section; the unit list adapts.

## How to Use This Template

1. Copy this file to `{YYYYMMDD}/consumer/RESEARCH_PLAN.md` (one per run)
2. Fill in the **Overview**, **Subjects**, **Window**, and **Mode** fields
3. Pick the unit subset for your mode (see "Mode → Unit Selection" below)
4. Replace `{placeholders}` with concrete query strings and file paths
5. Run units in dependency order — most queries can run in parallel
6. After all producer files exist, run Unit N (Synthesis Brief) in `{YYYYMMDD}/consumer/INTELLIGENCE_BRIEF.md`

---

## Overview

> **Replace this section per-run.** Example for breaking-news: "Map the first 25 hours of conversation around [subject] release, dated YYYY-MM-DD." Example for landscape: "Map the 30-day conversation landscape for [subject] using [control 1, control 2] as controls."

- **Subject(s):** `{primary subject, e.g. "MiniMax M3"}`
- **Control models (optional):** `{e.g. "Qwen 3.7 Max, DeepSeek V4 Pro"}` — omit for single-subject breaking-news runs
- **Window:** `{N days, passed to --days N}` — defaults to 30; use 2 for breaking news (≤48h since launch); use 7 for "first week" reception
- **Mode:** `{breaking-news | landscape}`
- **Run date:** `{YYYYMMDD}`
- **Output root:** `minimax-conversation-last30days/{YYYYMMDD}/`

## Problem Frame

We need an evidence-grounded picture of how the chosen subject(s) are being discussed across the open web in the chosen window. The work splits into two phases:

- **Producer phase** — run `last30days.py` queries, capture raw per-query outputs in `producer/`
- **Consumer phase** — synthesize across queries into a single `INTELLIGENCE_BRIEF.md` in `consumer/`

When control models are included, the same query patterns run for each, enabling apples-to-apples comparison.

---

## Mode → Unit Selection

| Unit | Breaking-news (1 subject, 1-3 days) | Landscape (1-5 subjects, 30 days) |
|---|---|---|
| Unit 1 — Source health check | Required | Required |
| Unit 2 — Core/release queries | Required | Required |
| Unit 3 — Variant breakdown | Skip (subject is one variant) | Required (per-model) |
| Unit 4 — Language segmentation | Skip unless Chinese-source signal is critical | Optional (China-headquartered subjects) |
| Unit 5 — Use-case keyword segmentation | Required (capability split) | Required |
| Unit 6 — Comparison queries | Required (M3 vs N) | Required (X vs Y) |
| Unit 7 — Pricing / value | Optional (only if launch shifts pricing) | Required |
| Unit 8 — Reception / review queries | Required | Optional |
| Unit N — Synthesis Brief | Required | Required |

Mode-specific examples below.

---

## Research Inventory

### Available Sources (`last30days.py` ≥ v3.3)

| Source | Typical status | Notes |
|--------|---------------|-------|
| Web (Brave) | Working | 4-20 results, no engagement data, official-domain anchor for spec/announcement |
| Reddit | Working **iff** `lib/` directory is alongside `last30days.py` — see "Critical Setup" | 4-15 threads, engagement (upvotes, comments) |
| YouTube | Working | 4-15 videos, view/like/comment counts |
| X (via xAI/Grok) | Inconsistent | 0-10 posts when active; treat as best-effort signal |
| Hacker News | Inconsistent | 0-2 hits; often only the official launch post |

### Source Weighting Hierarchy

1. **Web** — highest reliability, captures official sources, blogs, and press
2. **YouTube** — high signal, captures hands-on reviews and creator opinion
3. **Reddit** — high signal when working, captures community sentiment and pricing/UX complaints
4. **X** — high signal when active, but availability fluctuates
5. **Hacker News** — sparse, useful only for official-announcement post engagement

### Critical Setup

`last30days.py` requires its sibling `lib/` directory to be present at runtime. If you copy `last30days.py` into a new directory (such as `engine/`) without also copying `lib/`, every Reddit query will fail silently with `ModuleNotFoundError: No module named 'lib'`. This was the root cause of "broken Reddit" in the 20260526 cycle.

When setting up a fresh execution environment:

```bash
# Copy both, not just one
scp source-path/last30days.py target-path/
scp -r source-path/lib/ target-path/
```

## Key Technical Decisions

- **Window selection:** breaking-news uses `--days 2`, landscape uses default `--days 30`. Match window to the noise floor — too wide dilutes launch signal with pre-launch chatter; too narrow misses delayed reactions.
- **Per-query results stored** in `producer/{slug}.md` for downstream synthesis (don't pipe stdout — write files)
- **Comparison queries** (e.g. `m3-vs-claude`) use the harness's two-entity mode automatically when the query string contains "X vs Y"
- **Single-subject mode** is the default; comparison mode is opted into via query string only

## Open Questions Per Run

### Resolve Before Running

- Which entity is the subject vs. which are controls?
- Window length: how far back is signal still relevant for this question?
- Which use-case queries matter for this subject (coding? video? speech?) — omit queries that will return zero results

### Deferred to Implementation

- If X returns zero results, is that signal (X has no conversation yet) or method failure (auth/rate limit)?
- If Reddit returns lower volume than expected, is it `lib/` missing, ScrapeCreators key absent, or genuine low activity?
- Should video transcripts be retried with a different backend? (Currently transcripts are not retrieved; only titles + counts.)

---

## Implementation Units

### Unit 1: Source Health Check

**Goal:** Confirm source availability before running the full query battery

**Requirements:** Always required

**Dependencies:** None

**Files:**
- Create: `{YYYYMMDD}/producer/_SOURCE_HEALTH.md` (or note in driver-script output)

**Approach:**

```bash
# One canonical query to verify each source returns ≥1 hit
python3 engine/last30days.py "{subject}" --emit=compact --days {N} --quick > /tmp/health.md
# Inspect: how many sources are active? Web/Reddit/YouTube/X?
```

If Reddit returns zero across multiple queries, verify:
1. `lib/` directory is colocated with `last30days.py`
2. `SCRAPECREATORS_API_KEY` is set (optional; keyless path is the fallback)

**Verification:**
- Health check shows ≥2 sources active for the chosen subject + window
- If <2 sources active, surface in brief's "Source Coverage" section before continuing

---

### Unit 2: Core / Release Queries

**Goal:** Establish baseline conversation volume and surface the central narrative

**Dependencies:** Unit 1

**Files:**
- Create: `{YYYYMMDD}/producer/{subject-slug}-core.md`
- Breaking-news: also `{subject-slug}-release.md`
- Landscape: also `{control-slug}-core.md` per control model

**Approach:**

```bash
# Breaking-news mode (single subject):
python3 engine/last30days.py "{subject}" --days 2 --quick --emit=compact > producer/{subject}-core.md
python3 engine/last30days.py "{subject} release" --days 2 --quick --emit=compact > producer/{subject}-release.md

# Landscape mode (subject + controls):
python3 engine/last30days.py "{subject}" --days 30 --emit=compact > producer/{subject}-core.md
python3 engine/last30days.py "{control1}" --days 30 --emit=compact > producer/{control1}-core.md
python3 engine/last30days.py "{control2}" --days 30 --emit=compact > producer/{control2}-core.md
```

**Verification:**
- Each `_core.md` file has ≥1 evidence cluster
- For landscape mode, all controls have matched query structure

---

### Unit 3: Variant / Sub-Product Breakdown

**Goal:** Disaggregate conversation by product variant (only meaningful for subjects with multiple shipped products in the window)

**Dependencies:** Unit 2

**Files:**
- Create: `{YYYYMMDD}/producer/{subject}-{variant}.md` per variant

**Approach:**

Breaking-news: usually skipped — a launch is itself one variant. Run only if the launched subject ships in multiple SKUs simultaneously.

Landscape example for MiniMax:

```bash
python3 engine/last30days.py "{subject} {variant}" --emit=compact > producer/{subject}-{variant}.md
# Example variants: M2.7, Mavis, Hub, Speech, Music, Hailuo
```

**Verification:**
- One file per variant the subject actually ships
- File counts ≥1 evidence cluster, or is documented in the brief as "no organic discussion"

---

### Unit 4: Language Segmentation (Optional)

**Goal:** Surface non-English conversation (Chinese, Japanese, Korean) which English keyword queries miss

**When to include:** subject is headquartered in a non-English market, or has documented strong non-English creator communities

**Dependencies:** Unit 2

**Files:**
- Create: `{YYYYMMDD}/producer/{subject}-{lang}.md` per language

**Approach:**

```bash
# Chinese-language query variants
python3 engine/last30days.py "{subject in native script, e.g. 小莫AI}" --emit=compact > producer/{subject}-zh.md

# Japanese usage queries
python3 engine/last30days.py "{subject} 使い方" --emit=compact > producer/{subject}-ja.md
```

**Verification:**
- Non-English query returns ≥1 result distinct from English query results
- Brief includes a language-distribution section

---

### Unit 5: Use-Case Keyword Segmentation

**Goal:** Disaggregate conversation by functional capability

**Dependencies:** Unit 2

**Files:**
- Create: `{YYYYMMDD}/producer/{subject}-{usecase}.md` per use-case

**Use-case selection guide (pick from this menu based on subject):**

| Use-case slug | When to include |
|---|---|
| `coding` | Subject is a coding-capable LLM |
| `multimodal` | Subject has multimodal claims |
| `image` | Subject generates or understands images |
| `video` | Subject generates or understands video |
| `speech` | Subject does TTS or speech understanding |
| `music` | Subject does music generation |
| `agent` | Subject is positioned for agentic / tool-use workloads |
| `benchmark` | Subject has published benchmark scores worth verifying |

**Approach:**

```bash
python3 engine/last30days.py "{subject} {usecase}" --emit=compact > producer/{subject}-{usecase}.md
```

**Verification:**
- One file per use-case the subject actually claims
- Brief surfaces a use-case dominance map

---

### Unit 6: Comparison Queries

**Goal:** Direct head-to-head comparison vs. each rival

**Dependencies:** Unit 2

**Files:**
- Create: `{YYYYMMDD}/producer/{subject}-vs-{rival}.md` per rival

**Approach:**

```bash
python3 engine/last30days.py "{subject} vs {rival}" --emit=compact > producer/{subject}-vs-{rival}.md
# The harness auto-detects two-entity comparison mode from "X vs Y" syntax
```

Pick rivals that matter for the subject's positioning (e.g., for MiniMax M3: Claude, DeepSeek, Qwen — not Llama, which is in a different tier).

**Verification:**
- File contains a `## Resolved Entities` block confirming both entities matched
- Evidence is split into `## {subject}` and `## {rival}` subsections

---

### Unit 7: Pricing / Value Conversation

**Goal:** Capture pricing perception as a distinct conversation track

**Dependencies:** Unit 2

**Files:**
- Create: `{YYYYMMDD}/producer/{subject}-pricing.md`

**Approach:**

```bash
python3 engine/last30days.py "{subject} pricing"     --emit=compact > producer/{subject}-pricing.md
# Optional: cross-cutting queries that don't name the subject
python3 engine/last30days.py "best value AI model {YYYY}" --emit=compact > producer/value-context.md
```

**Verification:**
- Pricing file captures both vendor-claimed pricing and community sentiment about pricing
- Brief notes whether pricing is being discussed positively, neutrally, or as a concern

---

### Unit 8: Reception / Review Queries (Breaking-News Mode)

**Goal:** Capture independent reviewer reaction in the first days post-launch — this is where contrary evidence lives

**Dependencies:** Unit 2

**Files:**
- Create: `{YYYYMMDD}/producer/{subject}-review.md`

**Approach:**

```bash
python3 engine/last30days.py "{subject} review" --days 2 --emit=compact > producer/{subject}-review.md
```

The most-engaged contrary review (look for critical YouTube titles like "...does NOT live up to claims", "broke X", "buyer beware") deserves direct quoting in the brief. **Do not bury it.** Critical reviews with strong engagement are the highest-signal evidence in a launch window.

**Verification:**
- Review file captures both promotional and critical voices
- Brief surfaces at least one independent reviewer by name, with engagement metrics

---

### Unit N: Synthesis — Intelligence Brief

**Goal:** Produce a single, citable intelligence document at `{YYYYMMDD}/consumer/INTELLIGENCE_BRIEF.md`

**Dependencies:** All preceding units

**Files:**
- Create: `{YYYYMMDD}/consumer/INTELLIGENCE_BRIEF.md`

**Approach:**

A good brief has 6-9 sections. The exact structure depends on mode:

**Breaking-news brief structure (~150-200 lines):**
1. Headline — what shipped, the dominant narrative, the most useful critical voice
2. Release mechanics — date, source, initial reach, friction signals
3. Verified technical specs — only triangulated facts, vendor-source-anchored
4. Reception patterns — top reviewers, engagement, tone split
5. Critical signals — things that don't match the narrative (this is the no-oversell section)
6. Source coverage notes — which sources active, which sparse
7. Delta vs. prior research — what changed since last cycle
8. Things to watch — concrete next 7-14 day signals
9. Appendix — query inventory

**Landscape brief structure (~400-500 lines):**
1. Conversation volume ranking — by source and combined
2. Use-case dominance map — who owns which capability narrative
3. Language landscape — English vs. native-market coverage
4. Variant breakdown (subject only) — internal conversation share
5. Pricing perception — sentiment and absolute pricing snapshots
6. Top voices — handles, channels, repeat-mention authors
7. Key quotes — verbatim highlights from highest-engagement posts
8. Gaps and opportunities — where the subject is underdiscussed
9. Appendix — data coverage notes, methodology

**Verification:**
- Every claim in the brief cites a specific producer file (or specifies vendor-claimed-but-uncross-referenced)
- The most engaged critical voice is surfaced, not buried
- "No oversell" check: read the brief as the subject's competitor; does any sentence overstate vendor claims?
- Source coverage section explicitly lists which sources had data and which were thin

---

## Requirements Trace

This template's requirements are:

- **R1.** Reusable across subjects (single-entity and comparative)
- **R2.** Reusable across windows (breaking-news, week-in-review, landscape)
- **R3.** Resilient to source-health variation (one source down ≠ run fails)
- **R4.** Output structure is consistent across runs (producer/ and consumer/, slugged filenames)
- **R5.** Brief surfaces contrary evidence, not just vendor claims
- **R6.** Critical setup (lib/ requirement) is documented inline so a fresh setup doesn't silently fail

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `last30days.py` `lib/` directory missing from execution dir | Setup checklist + Unit 1 health check |
| Single source dominates evidence (e.g., only YouTube has hits) | Brief surfaces source-skew in the coverage section |
| Vendor benchmarks are not independently verified in window | Brief separates "vendor-claimed" from "independently reproduced" |
| Promotional reviewer dominates engagement, drowning critical reviews | Unit 8 (reception) explicitly hunts for critical voices |
| Window choice biases conclusions (too narrow / too wide) | Window selection documented in brief's "Research Period" |

## Operational Notes

- All raw query outputs go to `producer/` as `.md` files — never inline-only
- All synthesis goes to `consumer/INTELLIGENCE_BRIEF.md` — one per run
- Per-run driver scripts (e.g. `run_{YYYYMMDD}_{subject}_{event}.py`) live in `engine/` and orchestrate the unit run order
- Translations of the brief (e.g. -zh, -ja) live in `consumer/` alongside the English original
- Do not commit large generated outputs (>100MB) — the brief is small, but raw web-page snapshots are not currently captured

## Sources & References

- **Engine:** `last30days.py` skill, vendored at `engine/last30days.py` + `engine/lib/`
- **Reference run (landscape, 30-day, 3-model):** `20260526/`
- **Reference run (breaking-news, 2-day, single-subject):** `20260602/`
- **Skill upstream:** `$HOME/.claude/plugins/cache/last30days-skill/last30days/`
