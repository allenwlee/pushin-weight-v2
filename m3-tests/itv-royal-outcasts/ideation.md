---
date: 2026-06-01
topic: m3-x-post-goryeo-banquet
focus: A cool, fun test that we can post on X (in support of MiniMax) that showcases M3.0's multimodal capabilities using Claude Code, optionally benchmarked against a competitor.
attribution: "{{AGENT_ATTRIBUTION}}"
---

# Ideation: M3.0 Goryeo Banquet — X Post Showcase

## Codebase Context

**M3.0 (capability to showcase):** Native multimodality — text + image + video + audio in one model. M3.0 ingests image + video input, can generate any of these modalities, and can operate a desktop. Per the M3 launch blog (2026-06-01), direct competitors positioned against are GPT-5.5, Gemini 3.1 Pro, and Claude Opus 4.7. Of these, **Gemini 3.1 Pro** is the only one with a true "one model, all modalities" marketing claim; **GPT-5.5** is fragmented (Sora + DALL-E + GPT + TTS as separate products); **Claude Opus 4.7** is text+image only.

**goryeo-model** (`~/development/goryeo-model` on remote fuchitalee): A local LLM finetune project for Goryeo dynasty (918–1392 CE) historical content. RAG-style instruction-tuning on Samguk Sagi / Goryeo-sa. Currently scaffolding (no committed weights yet). Has data/, scripts/, research/ dirs.

**royal-outcasts** (`~/development/royal-outcasts` on remote fuchitalee): A real, working AI video production pipeline for a Goryeo-era Korean drama series, already integrated with the M3 ecosystem:
- MiniMax mmx speech → Korean TTS
- MiniMax I2V / T2V → image-to-video, text-to-video
- HeyGen → talking heads with lip sync
- SadTalker fallback, ffmpeg composite
- Cross-posts to WordPress (thehistoryofkorea.com)
- Has canonical character refs (Haeyoung, Yuna, Lady Mina), Fountain screenplay, production bible

**Constraint:** Output must work as an X post — visually striking, shareable, autoplay-friendly. Using Claude Code connected to M3.0 as the harness.

## User Decisions (this session)
- **2026-06-01:** Use "multimodal" (text+image+video+audio), not "multi-model" or "multi-agent." M3's differentiator is native multimodality, not orchestration.
- **2026-06-01:** Banquet (#2) is the lead candidate. The "could a stack do this?" skepticism was raised; user chose to proceed with the Banquet anyway. Treat the Banquet as a quality + integration test, not a load-bearing multimodality test.
- **2026-06-01:** Duration iterated 30s → 10s → 5s → 10s → **30s (final).** User reasoning: 30s better showcases M3.0 — long-horizon generation is the M3 differentiator (1M context, sustained character + voice consistency), and the contrast against Gemini's 8s cap is starker when M3 holds 30s in a single shot.
- **2026-06-01:** Competitor for head-to-head: **Gemini 3.1 Pro.** Only competitor with native "one model, all modalities" claim.

## Ranked Ideas

### 1. The Goryeo Banquet, Three Speakers One Take (LEAD)
**Description:** A 30-second scene at a Goryeo dynasty royal banquet. Three characters at a low court table lit by oil lamps: Haeyoung pours tea, Yuna reacts with a laugh, Lady Mina leans in and whispers a single short Korean line. Hold a medium shot the entire time. Diegetic audio only. Same prompt run on M3.0 and Gemini 3.1 Pro / Veo 3.1; compare outputs. Post the M3.0 result with the Veo 8s cap as the reveal.
**Rationale:** At 30s, the test leverages M3.0's strongest claimed differentiator — 1M context with MSA, sustained character + voice consistency over long horizons. Gemini's Veo caps at ~8s per clip, so a 30s single-shot requires 4 stitched clips with seams. M3.0 holds the entire scene in one context, so character identity, voice, costume, and lighting all stay consistent. This plays to M3's "long-horizon" claim, not just "one model, all modalities."
**Downsides:**
- A well-orchestrated Gemini stack (Veo + Imagen + Chirp + lip-sync) could match the output at the cost of 4 handoffs — the Banquet is more of an integration test than a true multimodality test. Framed honestly, the post is about fewer seams, not "M3 can do something Gemini fundamentally can't."
- Multi-speaker Korean TTS quality is a real risk; M3.0 needs to actually deliver three distinct voices in 10s.
- Period-accurate Goryeo aesthetic is unverified for M3.0 vs Gemini — a quick A/B before committing to the post is recommended.
**Confidence:** 70%
**Complexity:** Medium
**Status:** Unexplored — needs A/B test before committing to the X post
**A/B test plan:** See "A/B Test Plan" section below.

### 2. One Sentence from Goryeo-sa, Decoded
**Description:** Take a single vivid Classical Chinese sentence from a real Goryeo-sa passage. Pass it through M3.0 across all four modalities: text (translation), image (period scene), video (animated), audio (Korean narration). Show what each modality adds and loses.
**Rationale:** The cleanest "look at all four modalities in one artifact" showcase. Each step depends on the previous one in a way a stack cannot fake — the model's translation must match its own video, and the audio must be coherent with the visual. A pure cross-modal test.
**Downsides:** Lacks a competitor comparison unless one is bolted on. Less "wow" than the cinematic options.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored — recommended as fallback if Banquet A/B fails

### 3. The 1231 Mongol Invasion Trailer
**Description:** A 60-second period-accurate trailer of the 1231 Mongol sacking of Kaesong — cavalry at dawn, defenders on the walls, a child holding a broken sword. One continuous clip. Compare to Gemini/Veo 3.1's 8-second cap.
**Rationale:** Most cinematic option. The Veo 8s cap is a real, citable architectural constraint. Long-horizon continuity is the cleanest M3.0 win — one context, one model, no stitch seams. Goryeo-model can ground the armor and setting.
**Downsides:** Higher production cost (60s of generated video). Historical accuracy claims must be defensible.
**Confidence:** 70%
**Complexity:** Medium-High
**Status:** Unexplored

### 4. Haeyoung Meets Her Ancestor
**Description:** Haeyoung (fictional royal-outcasts character) "interviews" Queen Janghwa (real Goryeo historical figure). M3.0 generates the conversation — Haeyoung's lines are TTS+video from royal-outcasts' existing pipeline; Queen Janghwa's lines come from court records via goryeo-model. The audience can't tell which lines are which without checking captions.
**Rationale:** The fiction/history blur is genuinely novel. The format (character-as-host, conversation as artifact) is native to social video. Royal-outcasts already has Haeyoung as a load-bearing character.
**Downsides:** Requires voice work for two characters. Risk of the historical lines reading as flat.
**Confidence:** 65%
**Complexity:** High
**Status:** Unexplored

### 5. Sound of a Vanished Court
**Description:** Goryeo court music (jeongak) is mostly lost. M3.0 generates plausible court music from textual descriptions in goryeo-model, then re-scores an existing royal-outcasts scene. Frame as "a sound no one has heard in 600 years."
**Rationale:** Audio is the most underused modality in AI demos. "A sound no one has heard in 600 years" is a strong specific hook. Cultural-loss-then-cultural-recovery is inherently shareable.
**Downsides:** Most speculative. Easier to dismiss as "AI made up a song." Cultural-recovery framing requires a careful tone.
**Confidence:** 60%
**Complexity:** High
**Status:** Unexplored

### 6. The Lost 1962 Goryeo Film
**Description:** In 1962, Korean cinema tried to make a Goryeo epic. The film is lost. Reconstruct it synthetically in the style of 1960s Korean cinema — B&W, 4:3, 24fps — and add a "director's note" voiced via M3.0 audio, generated from the actual production problems of that era.
**Rationale:** Frames a fully synthetic artifact as a lost cultural object. Honors a real cultural absence. The self-aware director's note turns a demo into commentary. Highest production-value ceiling.
**Downsides:** Most work. Style transfer to "1960s Korean cinema" is a niche ask. Could read as gimmicky.
**Confidence:** 55%
**Complexity:** High
**Status:** Unexplored

### 7. (Meta) The Four-Post Thread
**Description:** Lead with #1 or #2 (the strongest single post), then over the next 3 days post #3, #4, and a fourth, each demonstrating a different strength: multi-speaker dialogue, historical accuracy, audio reconstruction, character continuity. The thread is the artifact; the individual posts are assets.
**Rationale:** Each post is a single, complete demo. The series is what makes M3.0's "all modalities in one model" message stick.
**Downsides:** Higher overall effort. The lead post has to carry the most weight.
**Confidence:** 70%
**Complexity:** High (for the series), Low per post
**Status:** Unexplored

---

## A/B Test Plan — Goryeo Banquet at 10s

**Goal:** Verify whether M3.0's Goryeo Banquet output is competitive with Gemini 3.1 Pro before committing to the X post. **Decision deadline:** 1 generation cycle on each (~1 hour wall clock).

**Prerequisites (need confirmed before starting):**
- Gemini 3.1 Pro API access — if not available, pivot to GPT-5.5 with Sora+TTS stack as comparator
- M3.0 video gen endpoint — confirm the API path for text-to-video with character reference images
- Cost ceiling — 3 retries per model

**The prompt (verbatim, use for both models):**
```
A 30-second scene at a Goryeo dynasty (918-1392 CE) royal banquet.
Three characters at a low court table lit by oil lamps:
- Haeyoung (30s woman, yellow silk jeogori) pours tea
- Yuna (16-17 girl, casual yellow chima, long braid) laughs
- Lady Mina (35yr noblewoman, purple silk, jade earrings) leans in
  and whispers a single short Korean line
Hold a medium shot the entire time. Diegetic audio only: pouring
liquid, fabric rustle, low laughter, one whispered phrase. No music.
No subtitles. Period-accurate: wood and paper, oil lamps, no
anachronisms.
```

**Inputs to gather (~15 min):**
- `research/video/2026-04-21_haeyoung_front_facing.png` — Haeyoung ref
- `research/video/yuna_canonical.png` — Yuna ref
- `research/video/2026-04-18_mina_refined_v2.png` — Lady Mina ref
- `research/video/audio/` — any existing voice samples per character
- If voice samples don't exist, fall back to a written voice description in the prompt

**Eval rubric (out of 6, 5 min per output):**
1. All 3 characters appear and stay recognizable from refs across the full 30s (0/1/2) — no face/costume drift mid-shot
2. At least 2 distinct Korean voices audible (0/1/2) — 3 distinct voices in 30s is the realistic bar
3. Period feel plausible — no anachronisms (0/1/2)

**Go / pivot matrix:**
| M3 score | Gemini score | Decision |
|----------|--------------|----------|
| 5-6 | any | Post #1 Banquet as planned |
| 3-4 | lower than M3 | Post #1 with softer framing |
| 3-4 | equal or higher | Pivot to #2 Primary Source Decoded |
| 0-2 | any | Drop visual showcase, post the thread |

**Time/cost:**
- Setup: 15 min
- M3.0: 3 × 30s clips ≈ 30-45 min
- Gemini: 3 × 30s clips ≈ 30-45 min (will be 4 stitched 8s clips per attempt; seams are part of the demo)
- Eval: 15 min
- **Total: ~1.5-2 hours wall clock, before API costs**

---

## Rejection Summary (24 cut from 30)

| # | Idea | Reason Rejected |
|---|------|-----------------|
| V1 | Lady Mina Loading Screen | "Loading screen" framing forced; gimmicky |
| V2 | Same Prompt, Five Senses | Duplicates "Casting Call" with worse composition |
| V3 | The Scroll That Unfurls Itself | Parallax + 4 streams technically demanding; overproduced |
| V4 | Casting Call: Goryeo 1392 | Subsumed by Banquet (same character, stronger framing) |
| V5 | Goryeo Detective: Damaged Page | Duplicates Primary Source Decoded |
| V6 | M3.0 vs The Field — 4-model grid | Subsumed by the 10 specific vs-competitor tasks |
| V7 | The Director's Chair | Needs physical set; too produced for X |
| V8 | The Royal Outcast, Translated | Doesn't exercise M3.0 video gen end-to-end |
| V9 | Citation Theater | Duplicates Primary Source Decoded |
| V10 | The Production Bible, Alive | Too complex for an X post |
| VC1 | Lady Mina One-Prompt Scene | Subsumed by Banquet |
| VC4 | The Painting Speaks | Duplicates "The Celadon, Decoded" worse |
| VC5 | Sword-Clash Sound Test | Niche; hard to verify audio quality on autoplay |
| VC6 | 5-Second Voice Clone | M3.0 doesn't have a documented 5-sec voice clone |
| VC7 | Old Korean Subtitle | Subsumed by Primary Source Decoded |
| VC8 | 10-Angle Lady Mina | Veo drift is real but this is just prompting, not "multimodal" |
| VC9 | The Haeyoung Remix | Depends on existing scene, less generalizable |
| VC10 | Goryeo News Broadcast | Niche; depends on news content supply |
| C1 | Goryeo Wikipedia Gap | Risky if M3.0 actually does Goryeo well; not as strong a showcase |
| C2 | What M3.0 Got Wrong About Goryeo Robes | Dunking on M3 defeats the goal of the X post |
| C6 | The Celadon, Decoded | Duplicates VC4 "Painting Speaks" but better — kept as part of #2's image leg |
| C7 | The Honest Hallucination | Clever but requires per-frame labeling |
| C9 | Five M3.0s Disagree | Academic, less viral |
| C10 | What the AI Refused to Show | Politically risky |

---

## Session Log
- 2026-06-01: Initial ideation — 30 candidates generated across 3 frames (visual showcase, vs-competitor, contrarian), 7 survived including 1 meta. Lead: Goryeo Banquet at 10s with Gemini 3.1 Pro as competitor. A/B test plan written.
- 2026-06-01: Iterated duration 30s → 10s → 5s → 10s → 30s (final). Pivoted away from "could a stack do this?" pushback after user chose to proceed with Banquet anyway. Doc finalized.
- 2026-06-01: Final duration: 30s. Rationale: 30s better showcases M3.0's long-horizon generation (1M context, sustained character + voice consistency) — the contrast against Gemini's 8s cap is starker, and M3's "1M context" claim is the strongest differentiator to lead with. Doc updated; ready for `ce:brainstorm`.
