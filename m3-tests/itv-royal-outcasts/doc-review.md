---
date: 2026-06-01
topic: goryeo-banquet-doc-review
attribution: "{{AGENT_ATTRIBUTION}}"
---

# Document Review — Goryeo Banquet Requirements

**Source document:** `docs/brainstorms/2026-06-01-153140-goryeo-banquet-requirements.md`
**Type:** requirements
**Reviewers:** coherence, feasibility, scope-guardian, product-lens
- feasibility — plan touches M3.0 video gen API, royal-outcasts pipeline integration, multi-speaker audio
- product-lens — flagship launch post with strategic positioning
- scope-guardian — 11 requirements + 4 SC + 6 decisions for a single X post
- coherence — caption claims vs scene content vs rubric bar

Applied 4 auto-fixes. 25 findings to consider (21 errors, 4 omissions).

## Auto-fixes Applied

- **R10** — Added explicit guidance: new script must call `generate_i2v()` / `generate_video()` directly with `model='M3.0'` and `duration=30` (bypassing `i2v_gen.py`'s argparse, which caps `--duration` at {6, 10} and defaults `--model` to Hailuo-2.3-Fast) (feasibility)
- **R10** — Added explicit guidance: pass `timeout=1800` to `poll_task()` and the generate call (existing 300s default will fire prematurely on 30s / stitched 4×8s runs) (feasibility)
- **Problem Frame** — Removed unexplained "via MSA" parenthetical; "1M context" stands alone now (coherence)
- **R5** — Moved "3 retries per model" out of the numbered rubric list (was visually rendering as item 4, and rubric actually has 3 items) (coherence)

## P0 — Must Fix (4)

| # | Section | Issue | Reviewer | Confidence |
|---|---------|-------|----------|------------|
| 1 | Dependencies + Outstanding Questions | **30s single-take is unverified and load-bearing.** If M3.0 also stitches 4×8s internally, the central differentiator ("M3 holds 30s, Gemini caps at 8s") disappears. Should be a Precondition with a pass/fail gate before planning, not a deferred question. | feasibility (lead) + scope-guardian + product-lens | 0.95 |
| 2 | Success Criteria (S2/S3) | **4/6 ship threshold is dimension-blind.** A passing score can be 2+2+0 (no multi-voice Korean) — then the locked caption "Three voices" is a demonstrable lie on launch day. Need a per-dimension floor on the differentiator dimension. Also conflates "ship as-is" (4/6) with "wins the comparison" (≥5/6) for a flagship launch. | scope-guardian (lead) + product-lens | 0.88 |
| 3 | Post and Distribution (R8) | **Caption uses AI-engineer jargon.** "1M context era" and "8s cap" are model-card vocabulary; a non-technical scroller reads "M3.0 holds 30 seconds" as a duration claim, not a model capability claim. Single post, no thread — every phrase has to land on first read. | product-lens | 0.88 |
| 4 | Success Criteria (S3) | **S3 conflates capability failure with quality failure.** A score of 2/6 from "M3 has no 30s endpoint" (capability fail) and a score of 3/6 from "audio intelligible but period feel off" (quality fail) demand different responses. Capability failure means re-scope the demo (Primary Source Decoded may have the same gap). Quality failure means iterate or pivot. Same "pivot" branch handles both wrongly. | scope-guardian | 0.93 |

## P1 — Should Fix (10)

| # | Section | Issue | Reviewer | Confidence |
|---|---------|-------|----------|------------|
| 5 | R8 vs R1 vs R5 | **Caption "Three voices" overstates the scene.** R1 specifies only one spoken line (Lady Mina whispers) + one laugh (Yuna). Haeyoung is silent. The rubric treats 2 distinct voices as the ship bar (3 is "aspirational"). The post claims "three voices" but the rubric permits shipping with 2. Body-vs-summary mismatch. | coherence | 0.92 |
| 6 | R1/R2/R5 rubric line 2 | **Multi-speaker audio is a separate TTS step in the current pipeline, not one M3.0 video call.** PRODUCTION_BIBLE.md shows mmx speech → HeyGen → I2V → ffmpeg as the only path. The I2V payload has no `voice` / `audio` / `tts` field. R1 implicitly requires a capability the current pipeline has never exercised and the doc does not verify. | feasibility | 0.90 |
| 7 | R1/R2/R5 rubric line 1 | **I2V payload takes a single `first_frame_image`, not 3 character refs.** Even if M3.0 supports 30s, it can anchor one face; the other 2 are prompt-only and will drift across 30s at medium shot. R5 Q1 will likely score 0–1. | feasibility | 0.88 |
| 8 | R3 vs input shapes | **R3 "no per-model prompt tuning" doesn't bridge input-shape asymmetry.** M3.0 takes `first_frame_image`; Veo 3.1 may not. If Veo doesn't accept refs, the head-to-head is "M3 with refs vs Gemini without refs" — a rigged comparison. R3 governs prompt text, not request shape. | feasibility (lead) + product-lens | 0.85 |
| 9 | R10/R11 | **R10/R11 over-engineer pipeline integration for a one-off X post.** Doc itself says "one generation cycle, one post, done" in scope. Two R-bullets + a "Key Decision" + a deferred question about "minimum new-script footprint" is solving an integration problem the scope doesn't have. Reduce to one R-bullet for a runnable script. | scope-guardian | 0.80 |
| 10 | S3 + Scope Boundaries | **Primary Source Decoded is designed in as a named fallback before the lead is verified.** Naming a specific fallback commits to an artifact that has its own requirements/preconditions. Treat as placeholder, not a committed fallback. | scope-guardian | 0.85 |
| 11 | R10/R11 (new stage) | **mmx speech is a separate Node CLI (`/opt/homebrew/bin/mmx`), not part of the I2V endpoint.** R10/R11 mask a 3-tool orchestration: M3.0 video + mmx speech subprocess + ffmpeg mux. Make the 3 stages explicit in the doc. | feasibility | 0.92 |
| 12 | R5 (rubric) | **Rubric doesn't measure the load-bearing differentiator.** "Zero seams" / "one context" is the headline. Rubric scores (a) character recognizability, (b) distinct voices, (c) period feel — none directly score seamlessness, shot continuity, or voice identity persistence. A 4/6 can be achieved with visible seams and voice drift. | product-lens | 0.82 |
| 13 | Key Decisions | **Competitor framing picks M3's weakest differentiator.** "Citable 8s cap" is a temporary product-spec limitation (one Veo update away from changing). "1M context" is structural. Building the launch narrative around a transient competitor weakness is riskier than around a structural M3 strength. | product-lens | 0.80 |
| 14 | R1, S4 | **Cultural specificity is opaque to the X audience.** Goryeo dynasty + Korean dialogue + 3 named characters from a production bible. Non-Korean-reading scrollers see costumes in 2s; the caption explicitly removes the cultural hook. The audio is "a single short Korean line" most viewers cannot parse. | product-lens | 0.85 |

## P2 — Consider Fixing (9)

| # | Section | Issue | Reviewer | Confidence |
|---|---------|-------|----------|------------|
| 15 | Outstanding Questions + Scope | **Cost is a constraint, not a deferred research question.** 3 retries × 2 models on 30s multimodal gen + multi-speaker Korean could be material. R5 silently constrains itself to whatever budget is hit. | scope-guardian (lead) + product-lens | 0.72 |
| 16 | R9 | **R9 hides a 2nd-artifact decision with a stricter bar than the ship bar.** "No follow-up unless M3 is 5-6/6" is stricter than S2 (4-6/6 ships) — the most likely ship case explicitly disallows follow-up. The "2nd artifact" is also a design commitment the doc doesn't scope. | scope-guardian | 0.75 |
| 17 | R2 (omission) | **Voice samples exist (30+ MP3s in `research/video/audio/`) but the I2V payload has no audio/voice field.** "Voice samples as inputs" is structurally impossible at the video gen step. Realistic architecture: voice samples → mmx speech TTS, muxed with M3.0 video (which gets written-voice-description in prompt). | feasibility | 0.88 |
| 18 | R4 (omission) | **Veo 3.1 character ref image support is unverified.** R4 confirms the 8s cap but not whether Veo accepts ref images. If it doesn't, the rubric is biased against Gemini. | feasibility | 0.70 |
| 19 | R5 retries (omission) | **3 retries × 2 models is also a wall-clock question.** With polling timeout=300, worst case is 6 × 5 min = 30 min. "One generation cycle, one post, done" is in tension with the retry allowance. Add a wall-clock budget. | feasibility | 0.75 |
| 20 | S3 (omission) | **No human-veto gate if both models produce poor output.** Asymmetric downside (bad flagship post is remembered as a bad flagship post, not as "no post"). A rubric score doesn't catch visible failure modes (lip-sync desync at 0:22, character flicker at 0:18). | product-lens | 0.80 |
| 21 | R8 caption | **"Zero seams" presupposes seams are visible.** On X mobile autoplay, side-by-side panels compete for attention; most scrollers won't watch both panels for 16+ seconds. The caption's central claim is invisible to most viewers, and the post lands as a marketing claim, not a visual claim. Label panels or lead with full-screen M3.0. | product-lens | 0.78 |
| 22 | Problem Frame | **Stack matchability is admitted but not addressed in the post.** The Problem Frame itself says "Veo + Imagen + Chirp + lip-sync + ffmpeg" could match this. The X audience will ask. Either name the stack in the caption or address it in a follow-up. | product-lens | 0.82 |
| 23 | R10 (HeyGen) | **"HeyGen integration" in Key Decisions is not in R10.** R10 names only M3.0 + mmx speech. Either update R10 to include HeyGen, or remove HeyGen from the decision. | coherence | 0.72 |

## P3 — Optional (2)

| # | Section | Issue | Reviewer | Confidence |
|---|---------|-------|----------|------------|
| 24 | R9 (omission) | **Single-post format limits the launch narrative.** One side-by-side + one caption asked to carry 6 messages (M3 exists, it does multimodal, 1M context, beats Gemini, cultural setting, fair rubric). X rewards narrow claims. | product-lens | 0.70 |
| 25 | Overall structure | **11 R-bullets + 4 SC + 6 decisions for one X post.** A single post can usually fit on one page. The doc is solving for reusability more than for the post itself. | scope-guardian | 0.68 |

## Coverage

| Persona | Status | Findings | Auto | Present | Residual |
|---------|--------|----------|------|---------|----------|
| coherence | completed | 4 | 2 | 2 | 3 |
| feasibility | completed | 10 | 2 | 8 | 4 |
| scope-guardian | completed | 9 | 0 | 7 | 3 |
| product-lens | completed | 10 | 0 | 8 | 5 |

## Residual Concerns (not promoted)

Notable items the reviewers flagged but didn't promote:
- M3.0 endpoints may live on a different subdomain than `api.minimax.io/v1/video_generation` — neither scripts nor doc capture this (feasibility)
- Veo 3.1 8s cap sourced from M3 launch blog; if Google updates Veo in the same week, the comparison number shifts (product-lens)
- "1M context" is a context-window claim for chat, not necessarily a video-duration claim; category error in R1's premise (feasibility)
- Post-success follow-on plan is undefined (will the team get buried in one-off requests?) (product-lens)
- The 3 character ref images are 3 distinct poses/framings; medium-shot composition may require a single composite reference, not 3 separate refs (feasibility)

## Deferred Questions (for planning)

- Exact M3.0 video gen API request shape (post-precondition gate)
- Whether M3.0 video gen accepts multiple character references in one call
- Whether M3.0 video gen outputs diegetic audio in the same call, or whether TTS-mux is still required
- Whether Veo 3.1 accepts character reference images as input
- Typical wall-clock time for M3.0 30s generation (does it fit poll_task timeout=1800?)
- Per-attempt cost for M3.0 30s and Gemini 4×8s (depends on budget ceiling)
