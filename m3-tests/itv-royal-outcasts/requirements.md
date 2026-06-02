---
date: 2026-06-01
topic: goryeo-banquet-x-post
attribution: "{{AGENT_ATTRIBUTION}}"
---

# Goryeo Banquet — X Post Showcase for M3.0

## Problem Frame

MiniMax launched M3.0 on 2026-06-01 with native multimodality (text + image + video + audio) and 1M context. The launch positioned M3.0 against GPT-5.5, Gemini 3.1 Pro, and Claude Opus 4.7. The X timeline is the channel where the "first contact" with most developers and creators happens — and where MiniMax wants M3.0 to land as a credible "one model, all modalities" alternative to a stack of separate tools.

**Who is affected:** MiniMax's product marketing positioning; the AI/creator X audience's mental model of which model wins on long-horizon multimodal generation.

**What is changing:** Today, a 30s single-take multimodal scene with multiple characters, voices, and historical-period accuracy requires a stack of tools (Veo + Imagen + Chirp + lip-sync + ffmpeg). M3.0 claims to do this in one model. This X post is the artifact that proves or disproves that claim.

**Why it matters:** If the post lands, M3.0's "one model, 1M context" narrative is concrete. If it doesn't, the launch risks being a marketing claim without a memory of evidence — and the X audience files M3 alongside every other "we also do video" announcement.

## Requirements

### Demo Content
- **R1.** Generate a 30-second single-take video of a Goryeo dynasty (918–1392 CE) royal banquet scene at royal-outcasts' canonical visual standard. Three characters at a low court table lit by oil lamps: Haeyoung pours tea, Yuna reacts with a laugh, Lady Mina leans in and whispers a single short Korean line. Medium shot held for the full 30 seconds. Diegetic audio only — no music, no subtitles. Period-accurate: wood and paper architecture, oil lamps, no anachronisms.
- **R2.** Use the canonical character reference images from `research/video/` (Haeyoung, Yuna, Lady Mina) and any existing voice samples from `research/video/audio/` as inputs. Fall back to a written voice description in the prompt if samples don't exist.
- **R3.** Use the locked prompt (from ideation doc) verbatim across both M3.0 and Gemini 3.1 Pro runs. No per-model prompt tuning.

### Comparison Setup
- **R4.** Generate the same 30-second scene on **Gemini 3.1 Pro / Veo 3.1** as a head-to-head. Veo 3.1 caps at ~8s per clip, so the Gemini output will be 4 stitched 8s clips. The seams are part of the demo.
- **R5.** Score both outputs on the locked 6-point rubric (3 questions × 0/1/2):
  1. All 3 characters appear and stay recognizable from refs across the full duration (0/1/2)
  2. At least 2 distinct Korean voices audible (0/1/2) — 3 distinct voices is aspirational
  3. Period feel plausible — no anachronisms (0/1/2)

  Each model may be retried up to 3 times for the rubric eval.

### Composite Artifact
- **R6.** Produce a single side-by-side video: M3.0 above, stitched Gemini below (or vice versa — to be determined during production for the strongest visual). Both clips play simultaneously. No captions burned in (caption is the X post copy).
- **R7.** Format the side-by-side to autoplay cleanly on X's mobile player. Target ≤60s total runtime for both panels.

### Post and Distribution
- **R8.** Post on X with the locked caption: *"M3.0 holds 30 seconds. Three faces, three voices, one context, zero seams. Gemini 3.1 Pro: 8s per clip. The 1M-context era just made the 8s cap look dated."*
- **R9.** Single post, not threaded. No follow-up reply unless the M3 score is 5-6/6 and a 2nd artifact warrants it.

### Pipeline Integration
- **R10.** Add new script(s) under `~/development/royal-outcasts/scripts/` that call the MiniMax M3.0 video gen API and the mmx speech CLI (or M3.0 audio endpoint if available). Reuse existing character ref paths and the production bible. Do not modify existing generation scripts unless required. The new script must call `generate_i2v()` / `generate_video()` programmatically with explicit `model='M3.0'` and `duration=30` (bypassing `i2v_gen.py`'s argparse, which caps `--duration` at {6, 10} and defaults `--model` to Hailuo-2.3-Fast), and pass `timeout=1800` to both `poll_task()` and the underlying generate call (the existing 300s default will fire prematurely on 30s / stitched 4×8s runs).
- **R11.** The new script should be runnable end-to-end: take the prompt + character refs, call M3.0 and Gemini 3.1 Pro, return both outputs. Composite is a separate `ffmpeg` step.

## Success Criteria
- **S1.** Side-by-side video produced and posted on X with the locked caption.
- **S2.** M3.0 score is **≥ 4/6** on the rubric → ship as-is.
- **S3.** M3.0 score is **< 4/6** → do not ship; pivot to Primary Source Decoded (the #2 fallback from the ideation doc) as the lead artifact.
- **S4.** The post reads as authentic to a non-technical viewer. The seam contrast between M3.0 and Gemini is visible without explanation.

## Scope Boundaries
- **Not in scope:** Threaded follow-up posts, paid promotion, marketing site copy updates, README updates, the 6 other survivors from the ideation doc.
- **Not in scope:** Production-grade ffmpeg polish (color grading, audio mixing, transitions) beyond what makes the side-by-side readable. The X player is forgiving; ship when it's clear, not when it's perfect.
- **Not in scope:** Re-running the A/B after publication. One generation cycle, one post, done.

## Key Decisions
- **30 seconds, not shorter.** User reasoning: 30s better showcases M3.0's long-horizon generation claim (1M context, sustained character + voice consistency). The contrast against Gemini's 8s cap is starker at 30s than at 10s or 5s. Iterated 30 → 10 → 5 → 10 → 30; final.
- **Side-by-side, not M3-only or 4-up grid.** The seams between Gemini's 4 stitched 8s clips are the story. M3-only wouldn't show the contrast; 4-up grid is hard to read in autoplay.
- **Pragmatic 4/6 threshold.** M3 artifact stands on its own; Gemini is just there for context. Ship at 4/6 even if Gemini is also decent.
- **Extend royal-outcasts pipeline, not standalone.** Reuses existing character refs, production bible, and HeyGen integration. Aligns the demo with the production project rather than making it a one-off.
- **Caption Option B (direct, product-led).** Leads with the win ("30 seconds, three faces"), names the competitor, lands the takeaway ("1M-context era just made the 8s cap look dated"). No cultural hook in the caption — the artifact carries the cultural weight; the caption is the product claim.
- **Competitor is Gemini 3.1 Pro, not GPT-5.5 or Claude.** Only competitor with a true "one model, all modalities" marketing claim. Direct comparison; citable 8s cap.

## Dependencies / Assumptions
- **Confirmed:** Gemini 3.1 Pro API access (user has key).
- **Confirmed:** Veo 3.1 8s per clip cap (per M3 launch blog, 2026-06-01).
- **Confirmed:** Royal-outcasts canonical character refs exist at `research/video/2026-04-21_haeyoung_front_facing.png`, `research/video/yuna_canonical.png`, `research/video/2026-04-18_mina_refined_v2.png` (read from PRODUCTION_BIBLE.md on fuchitalee).
- **Unverified:** M3.0 video gen supports 30s single-take output (likely per blog's "1M context" claim, but the actual API surface is unconfirmed).
- **Unverified:** M3.0 supports multi-speaker Korean audio in a single generated clip (the blog lists native multimodality but doesn't show a multi-speaker demo).
- **Unverified:** MiniMax I2V / mmx speech in royal-outcasts are M3.0 endpoints, or a different version (e.g., M2.7). The PRODUCTION_BIBLE.md references "MiniMax I2V" and "MiniMax mmx speech" without version.

## Outstanding Questions

### Resolve Before Planning
*(none — all blocking questions resolved this session)*

### Deferred to Planning
- **[Affects R1, R11][Needs research]** What is the exact M3.0 video gen API endpoint, request shape, and parameters for a 30s single-take video with character reference image inputs? Confirm during planning by reading the MiniMax API docs via context7.
- **[Affects R1][Needs research]** Can M3.0 output a 30s single-take video in one API call, or does it need 4 stitched 8s calls (in which case M3 has the same stitching problem as Gemini)? Verify before designing the script.
- **[Affects R1][Technical]** How is multi-speaker Korean audio handled — is it generated by M3.0 in one pass, or is the script expected to use MiniMax mmx speech as a separate step and mux with the M3.0 video? Plan should verify by reading the M3.0 audio capabilities.
- **[Affects R4][Technical]** What is the exact Gemini 3.1 Pro video gen request shape for an 8s clip with character reference inputs? Same API-surfaces question.
- **[Affects R10][Technical]** What's the minimum new-script footprint in royal-outcasts? One new file under `scripts/`, or extend `i2v_gen.py` and `video_gen.py`? Plan should pick the smallest change that supports the demo.
- **[Affects S4][Needs research]** Approximate cost per M3.0 30s attempt and per Gemini 4×8s attempt. Confirms whether 3 retries per model is realistic within budget.

## Next Steps
→ `/ce:plan` for structured implementation planning. The deferred questions above should be answered in the first 15-20 minutes of planning via MiniMax API docs and a quick test call.
