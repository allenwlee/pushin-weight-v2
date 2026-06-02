---
title: Goryeo Banquet 30s Test Loop (Hailuo-2.3 vs Veo 3.1)
type: feat
status: active
date: 2026-06-01
origin: docs/brainstorms/2026-06-01-153140-goryeo-banquet-requirements.md
target_repo: royal-outcasts (on remote fuchitalee host)
---

# Goryeo Banquet 30s Test Loop

## Overview

Build a runnable Python script that generates a 30-second Goryeo Banquet scene on both MiniMax Hailuo-2.3 and Google Veo 3.1, then produces a two-panel composite for visual comparison. The artifact (the two 30s clips and the composite) is the deliverable; the user reviews and decides whether to post, iterate, or pivot.

This is a test loop, not a production pipeline. Distribution (X post, caption, framing) is post-test work and out of scope.

## Problem Frame

User wants a single visual artifact that exercises the long-horizon multimodal generation claim of MiniMax M3.0 (the marketing name for the Hailuo 2.x family) against Google's Veo 3.1, in support of an X launch post for M3.0 on 2026-06-01. The artifact is the test; ship/no-ship is decided from the artifact, not from a rubric score (see user feedback: artifact-as-arbiter).

**Three architectural realities surfaced during research that revise the brainstorm:**

1. **"M3.0" is not an API model name on `api.minimax.io`.** The current model family is `MiniMax-Hailuo-2.3` / `MiniMax-Hailuo-2.3-Fast` (T2V/I2V) and `S2V-01` (subject-reference, for character consistency). The "M3" marketing name has not yet been assigned a model identifier at the API surface as of 2026-06-01. This plan uses Hailuo-2.3 + S2V-01.

2. **30s single-take is not supported on either side at the API level.** Hailuo-2.3 caps at 10s per call (3 stitches for 30s); Veo 3.1 caps at 8s per call (4 stitches for 30s). The brainstorm's "zero seams / single context" framing does not survive contact with the API — both paths produce stitched output, with different seam counts.

3. **MiniMax video output is silent.** Diegetic audio must be generated separately via `mmx speech` and muxed with ffmpeg. Veo 3.1 output includes always-on audio (multi-speaker dialogue via prompt cues).

**Implication:** The original "M3 holds 30s, Gemini caps at 8s" differentiator is structurally not what the API does. The actual comparison is 3-stitch Hailuo-2.3 + muxed TTS audio vs 4-stitch Veo 3.1 with native audio. The artifact will reveal whether the differentiator exists in some other form (character consistency, audio quality, scene coherence, period feel).

## Requirements Trace

- **R1** Generate 30s Goryeo Banquet scene — see Locked Prompt (ideation.md)
- **R2** Use canonical character refs from `research/video/` (Haeyoung, Yuna, Lady Mina)
- **R4** Same scene on both models for head-to-head
- **R5** 1 first attempt + 2 retries per model (3 total attempts) based on output quality
- **R6** Two-panel composite (hstack or top/bottom overlay — implementer picks)
- **R10** New runnable script under `scripts/`, reuses existing patterns, calls `generate_i2v()` programmatically with `model` and `duration` overrides and `timeout=1800`
- **R11** End-to-end runnable script (M3.0 + Gemini + composite)

(Not in plan scope: R3 prompt asymmetry, R7 ≤60s target, R8 caption copy, R9 follow-up posts — all post-test work, deliberately deferred.)

## Scope Boundaries

- **In scope:** the script, the two 30s video files, the two-panel composite
- **Out of scope:** X post, caption copy, distribution, post metrics, follow-up posts, README updates, pipeline integration, refactoring existing scripts
- **Not in plan:** rubric scoring, ship threshold, Primary Source Decoded fallback — all post-test decisions the user makes from the artifact

## Context & Research

### Relevant Code and Patterns

- **`scripts/i2v_gen.py`** — `create_i2v_task()`, `generate_i2v()`, `poll_task()`. Argparse caps `--duration` at {6, 10}; `generate_i2v()` programmatically accepts any int. New script calls `generate_i2v(prompt, image, out, model="MiniMax-Hailuo-2.3", duration=10, timeout=1800)` directly.
- **`scripts/video_gen.py`** — `create_video_task()`, `generate_video()`. Same pattern, no image input.
- **`scripts/add_burned_subs_scene5.py`** — closest existing ffmpeg pattern for concat + audio mux + burned subs.
- **Auth contract:** `os.environ.get("MINIMAX_API_TOKEN", "")` (injected by `nono` at runtime via `~/.zshenv`). New scripts use the same env var name to match the existing pattern.
- **Tech stack:** Python 3.14.5, `requests 2.32.5`, `ffmpeg 8.0.1`, `mmx` CLI at `/opt/homebrew/bin/mmx`. No venv; deps are global. No `google-genai` SDK installed — Veo 3.1 calls go via raw `requests`.

### Character Refs and Audio

- **Refs (3 canonicals, 1024×1024 PNG):** `research/video/2026-04-21_haeyoung_front_facing.png`, `research/video/yuna_canonical.png`, `research/video/2026-04-18_mina_refined_v2.png`
- **Voice samples (33 MP3s in `research/video/audio/`):** `yuna_os_goodbye.mp3` (~8.9s, contains a laugh and a line) is the closest fit for Yuna's audible moment; `mina_call_v2.mp3` / `mina_meeting.mp3` are usable Lady Mina references. Mux these into the M3.0 path at the prompt-specified timestamps.

### Institutional Learnings

- `AGENTS.md` "Working Rules": do not refactor `i2v_gen.py` / `video_gen.py`; add new files under `scripts/`. Generated media in `research/video/` is gitignored — not committed.
- `PRODUCTION_BIBLE.md` is authoritative for the pipeline; `add_burned_subs_scene5.py` is the ffmpeg template for mux with audio.
- User's saved feedback: "no oversell" and "artifact-as-arbiter." The plan does not include abstract pre-validation gates (no P0 precondition tests, no rubric floor, no caption draft). The artifact is the test.

### External References

- **MiniMax API docs** (context7: `/websites/platform_minimax_io_api-reference`): model enums, payload shapes, `S2V-01` subject_reference spec.
- **Veo 3.1 docs** (context7: `/google-gemini/veo-3-nano-banana-gemini-api-quickstart`, plus `https://ai.google.dev/gemini-api/docs/video`): `veo-3.1-generate-preview`, `:predictLongRunning`, `referenceImages` (up to 3), `aspectRatio`, `durationSeconds`.

## Key Technical Decisions

- **Use `MiniMax-Hailuo-2.3` (and `S2V-01` for character refs) as the M3.0 path.** "M3.0" is not in the API enum. Hailuo-2.3 is the current production model.
- **Stitch 3×10s calls on the M3.0 path using first-frame chaining on Hailuo-2.3 I2V.** After each clip returns, extract the last frame (ffmpeg) and pass it as `first_frame_image` to the next call's I2V payload. This minimizes visual drift between stitches. The M3.0 path produces 3 separate mp4s concatenated into one 30s clip.
- **For Veo 3.1, prompt each 8s clip with a "previously: ..." cue describing the last frame of the prior clip.** No native memory between calls; continuity comes from the prompt and the 3 reference images passed to every call.
- **Audio: M3.0 path is silent video + separately-generated `mmx speech` TTS for Lady Mina's Korean whisper (use `Korean_CalmLady` voice per PRODUCTION_BIBLE.md), plus a pre-recorded Yuna laugh sample from `research/video/audio/yuna_os_goodbye.mp3`. Mux both at the prompt-specified timestamps. Veo 3.1 has always-on audio; do not add separate TTS.**
- **Two-panel composite via ffmpeg `hstack` (horizontal side-by-side, half-width each) or `overlay` (M3.0 on top half, Veo on bottom half of a 1920×1080 frame).** Implementer picks based on what reads best in the artifact. No burned-in captions (per R6; can add later if useful for the user's review).
- **Timeout: 1800s on M3.0 `poll_task()` calls (the existing 300s default fires prematurely on 10s generations). For Veo 3.1, use a 600s polling timeout on the operation URL — Veo 3.1's predictLongRunning typically completes in <5 min for 8s clips, so 600s is sufficient and gives a hard upper bound.**
- **S2V-01 probe in Unit 1 — fall back to Hailuo-2.3 I2V with a composite first frame if multi-subject subject_reference does not work in one call.** The plan does not pre-commit to S2V-01; runtime decides.
- **Output dir:** `out/` at the repo root. Implementer must verify `out/` is in `.gitignore` (if not, add it) — generated mp4s and mp3s are large and must not be committed.

## Open Questions

### Resolved During Planning

- Q: Which model name to use for "M3.0"? → A: `MiniMax-Hailuo-2.3` (and `S2V-01` for character refs). "M3.0" is not in the API enum.
- Q: Is 30s single-take possible? → A: No. Max 10s on Hailuo-2.3, max 8s on Veo 3.1. Both require stitching.
- Q: Does MiniMax output diegetic audio? → A: No. Use `mmx speech` + ffmpeg.
- Q: Are voice clones supported via `mmx`? → A: No. System voices only.
- Q: Is `GEMINI_API_KEY` on fuchitalee? → A: No (only in `~/.openclaw/.env` locally on user's machine, not on fuchitalee). Unit 1 surfaces this; user must provision before Unit 3 can run.

### Deferred to Implementation

- Whether `S2V-01` `subject_reference` actually preserves character identity across 3 subjects in one call. Probe at runtime; fall back to I2V with a composite first frame.
- Exact prompt phrasing for Veo 3.1 audio cues (Korean dialogue, period-accurate soundscape).
- Whether the two-panel composite needs burned-in time markers for the user's review.
- Whether `last_frame_image` chaining on M3.0 produces natural continuity or visible drift. Test at runtime; the artifact is the answer.
- Whether the 3 stitched Hailuo-2.3 clips total exactly 30s or come in slightly under (often 9.5s per call rather than 10s). ffmpeg concat handles the mismatch.

## High-Level Technical Design

> *Directional guidance for review, not implementation specification. The implementing agent should treat this as context, not code to reproduce.*

```
[Locked Prompt + 3 character refs (Haeyoung, Yuna, Lady Mina)]
                          |
                          v
            +-------------+-------------+
            |                           |
            v                           v
   +-------------------+      +-------------------+
   | M3.0 path         |      | Veo 3.1 path      |
   | (Hailuo-2.3 /     |      | (veo-3.1-generate-|
   |  S2V-01)          |      |  preview)         |
   |                   |      |                   |
   | 3 stitched 10s    |      | 4 stitched 8s     |
   | calls; first-     |      | calls; prompt-cue |
   | frame chaining on |      | chaining          |
   | Hailuo-2.3 I2V    |      |                   |
   +---------+---------+      +---------+---------+
             |                          |
             v                          v
    +-----------------+        +-----------------+
    | mmx speech TTS  |        | (audio baked in) |
    | for Lady Mina + |        |                 |
    | Yuna laugh      |        |                 |
    | sample -> ffmpeg|        |                 |
    | mux at prompts  |        |                 |
    +--------+--------+        +--------+--------+
             |                          |
             v                          v
       m3_30s.mp4                 veo_30s.mp4
             |                          |
             +-------------+------------+
                          |
                          v
                ffmpeg hstack/overlay
                  (2 panels, synced)
                          |
                          v
                  two_panel.mp4
                          |
                          v
                    user reviews
```

## Implementation Units

- [ ] **Unit 1: API surface probe**

**Goal:** Confirm that both MiniMax Hailuo-2.3 and Veo 3.1 are reachable with the request shapes research surfaced, and that the necessary API keys are available on fuchitalee.

**Requirements:** R10, R11 (the script needs the right request shape before any generation)

**Dependencies:** None

**Files:**
- Create: `scripts/probe_m3_endpoint.py`
- Create: `scripts/probe_veo_endpoint.py`

**Approach:**
- Probe M3.0/Hailuo-2.3: 5s generation with one character ref (Haeyoung only). Validate (a) `task_id` returned, (b) polling reaches `Success` in <10 min with `timeout=1800`, (c) `download_url` returns playable mp4.
- Probe M3.0/S2V-01: short generation with all 3 subject_refs in one call. Validate that 3-subject subject_reference is accepted (return shape, no error). If rejected, document the failure mode in stderr and the plan will fall back to I2V with a composite first frame.
- Probe Veo 3.1: 8s generation, no ref images, English prompt with a `says: "..."` dialogue cue. Validate (a) operation name returned, (b) polling reaches `done: true` in <15 min, (c) `video.uri` returns playable mp4, (d) audio is present in the downloaded mp4.
- If `GEMINI_API_KEY` is not set on fuchitalee, surface this immediately as a blocker for Unit 3.

**Patterns to follow:**
- `create_i2v_task` / `poll_task` from `scripts/i2v_gen.py` for the M3.0 probe
- Raw `requests.post()` to `:predictLongRunning` for the Veo probe

**Test scenarios:**
- Happy path: M3.0 probe returns Success and playable mp4 within 10 min; S2V-01 probe accepts 3 subject_refs; Veo probe returns `done: true` and playable mp4 with audio within 15 min.
- Error path: M3.0 returns 401/403 → check `MINIMAX_API_TOKEN` is loaded; M3.0 returns 400 → log full request/response payload; Veo returns 403 → confirm `GEMINI_API_KEY` is set on fuchitalee (this is the most likely failure mode).
- Edge case: S2V-01 rejects 3 subjects → log, fall back decision recorded for Unit 2.

**Verification:** Both probe scripts run end-to-end. Output paths logged to stdout. Failure modes are documented in stderr with the full HTTP response, not swallowed.

- [ ] **Unit 2: M3.0 path (3-stitch + TTS + ffmpeg mux)**

**Goal:** Produce a single 30s mp4 of the Goryeo Banquet scene from the M3.0 side, with the whisper + laugh audio muxed in.

**Requirements:** R1, R2, R10, R11

**Dependencies:** Unit 1 (M3.0 endpoint confirmed, S2V-01-vs-I2V decision recorded)

**Files:**
- Create: `scripts/m3_banquet_30s.py`
- Output: `out/m3_30s.mp4` (and intermediate `out/m3_clip_{1,2,3}.mp4`, `out/m3_whisper.mp3`)

**Approach:**
- Call `generate_i2v()` from `scripts/i2v_gen.py` programmatically three times (10s each, `model="MiniMax-Hailuo-2.3"`, `timeout=1800`).
- Use the S2V-01 path if Unit 1 confirmed 3-subject subject_reference works; otherwise fall back to I2V with the first call's `first_frame_image` set to a composite (Haeyoung + Yuna + Lady Mina) — but at runtime, the simpler path is to just use the first character ref and let the others be prompt-described. Document the chosen path in a header comment.
- For calls 2 and 3, extract the last frame of the previous call's mp4 (ffmpeg `-sseof -0.1 -vframes 1`) and pass that PNG as `first_frame_image` to the next I2V call. This minimizes visual drift between stitches without depending on a separate `last_frame_image` field.
- Generate Lady Mina's whisper via subprocess: `mmx speech synthesize --text "<the locked Korean line>" --voice Korean_CalmLady --out out/m3_whisper.mp3`. Hard-code the locked Korean line in the script (or read it from a sibling file in the `m3-test/` dir).
- Mux: ffmpeg concat the 3 video clips → `out/m3_video_concat.mp4`. Then ffmpeg overlay whisper + pre-recorded Yuna laugh (from `research/video/audio/yuna_os_goodbye.mp3`) at the prompt-specified timestamps (Yuna laugh at ~5s, Lady Mina whisper at ~22s).
- Final output: `out/m3_30s.mp4`.

**Patterns to follow:**
- `generate_i2v` from `scripts/i2v_gen.py` (called programmatically, not via subprocess to the CLI)
- `mmx speech synthesize` (via subprocess)
- `ffmpeg -f concat -safe 0 -i concat_list.txt -c copy out.mp4` (the pattern in `add_burned_subs_scene5.py`)

**Test scenarios:**
- Happy path: script produces `out/m3_30s.mp4` of 28-32s, has visible characters + audio at the right timestamps.
- Error path: M3.0 call 2 or 3 fails → log the failure, return the partial concat (calls 1+2 or 1) for review, do not crash the script.
- Error path: `mmx speech` fails (returns 0-byte output, Korean voice not loaded) → log, continue with silent video.
- Error path: ffmpeg concat fails (resolution mismatch between clips) → log the ffmpeg stderr, return the longest single clip.
- Edge case: 3-stitch total runtime is <30s because Hailuo-2.3 pads to 9.5s instead of 10s → ffmpeg concat handles the mismatch; do not pad artificially.

**Verification:** Script runs end-to-end. Output file is 28-32s, plays in QuickTime / VLC, has all 3 character refs visible at some point, has at least one Korean voice audible (or the absence is documented in stderr).

- [ ] **Unit 3: Veo 3.1 path (4-stitch with reference images + native audio)**

**Goal:** Produce a single 30s mp4 of the Goryeo Banquet scene from the Veo 3.1 side, with native always-on audio.

**Requirements:** R1, R2, R4, R11

**Dependencies:** Unit 1 (Veo endpoint confirmed), `GEMINI_API_KEY` available on fuchitalee

**Files:**
- Create: `scripts/veo_banquet_30s.py`
- Output: `out/veo_30s.mp4` (and intermediate `out/veo_clip_{1,2,3,4}.mp4`)

**Approach:**
- Call Veo 3.1 four times (8s each) via raw `requests.post()` to `:predictLongRunning`. Model: `veo-3.1-generate-preview`. Each call: 3 `referenceImages` (Haeyoung, Yuna, Lady Mina as base64-encoded JPEG), `aspectRatio=16:9`, `durationSeconds=8`.
- For calls 2-4, prefix the prompt with a "previously: ..." cue describing the last frame of the prior clip to encourage continuity. No native memory between calls.
- Poll the operation URL with 5s interval, 600s timeout per call.
- Download the resulting mp4 from `response.generateVideoResponse.generatedSamples[0].video.uri` (with the `x-goog-api-key` header for auth).
- ffmpeg concat the 4 clips → `out/veo_30s.mp4`.

**Patterns to follow:**
- Veo 3.1 official quickstart (context7) for the request shape and polling loop
- ffmpeg concat pattern from Unit 2

**Test scenarios:**
- Happy path: 4×8s clips concatenate cleanly, total runtime 30-32s, audio is present in at least one clip, all 3 character refs visible at some point.
- Error path: Veo call 1 succeeds but call 2 fails → log, return partial concat (call 1).
- Error path: Veo audio contains no Korean (returns English audio despite Korean prompt) → log the language detected (or just note the absence), do not retry. The artifact is the test.
- Edge case: Veo rejects 3 `referenceImages` (max is 2 or 1) → fall back to 1 hero ref + describe the others in prompt; document the choice in stderr.

**Verification:** Script runs end-to-end. Output file is 30-32s, plays in QuickTime / VLC, has all 3 character refs visible at some point, has audible audio.

- [ ] **Unit 4: Two-panel composite**

**Goal:** Produce a single ≤60s mp4 with the M3.0 and Veo 3.1 clips playing simultaneously, laid out for direct visual comparison.

**Requirements:** R6

**Dependencies:** Units 2 and 3 (both `out/m3_30s.mp4` and `out/veo_30s.mp4` exist)

**Files:**
- Create: `scripts/composite_two_panel.py`
- Output: `out/two_panel.mp4`

**Approach:**
- ffmpeg `hstack` (horizontal side-by-side, half-width each) or `overlay` (M3.0 on top half, Veo on bottom half of a 1920×1080 frame) to put both clips in a single frame. Implementer picks based on what reads best in the artifact.
- Both panels play simultaneously, synced to start at t=0. Use the shorter of the two runtimes for the composite (do not pad).
- No burned-in captions, no labels, no audio mixing by default (each panel plays its own audio; ffmpeg `-filter_complex amix` for mixed output is optional and configurable via flag).
- If M3.0 has audio but Veo doesn't (or vice versa) → composite plays whichever audio is present; do not error.

**Patterns to follow:**
- `add_burned_subs_scene5.py` for the ffmpeg command pattern
- ffmpeg `hstack` / `overlay` / `amix` filters

**Test scenarios:**
- Happy path: composite plays both panels simultaneously, total runtime ≤ max(M3, Veo) + 1s, no audio crackling.
- Error path: one of the input files is missing → log the gap, exit cleanly (do not crash).
- Edge case: M3.0 has audio but Veo doesn't (or vice versa) → composite plays whichever audio is present; do not error.
- Edge case: composite is requested before either Unit 2 or 3 has run → log a clear "run m3_banquet_30s.py and veo_banquet_30s.py first" message.

**Verification:** Composite runs end-to-end. Output file plays in QuickTime / VLC, both panels visible at all times, no desync. The user can then watch and decide.

## System-Wide Impact

- **Interaction graph:** No callbacks, middleware, or shared state. The scripts write files to `out/`. No DB writes, no API writes outside the generation calls.
- **Error propagation:** Failures in any unit are logged to stderr with the failure mode and partial output. Scripts do not crash on a single unit's failure — they return the partial result for review.
- **State lifecycle risks:** Generated mp4s and mp3s are written to `out/`, which is gitignored. They will accumulate across runs. The plan does not include a cleanup step; the user can `rm out/*.mp4 out/*.mp3` manually after review.
- **API surface parity:** No existing scripts are modified. The new scripts call existing `generate_i2v()` and `generate_video()` programmatically (the API contract of those functions is preserved).
- **Integration coverage:** The plan is an integration test by design (it calls external APIs and produces real artifacts). Unit tests are not appropriate; the artifact is the test.
- **Unchanged invariants:** `scripts/i2v_gen.py` and `scripts/video_gen.py` are not modified. `AGENTS.md` "Working Rules" are honored (no refactoring of existing gen scripts). Generated media is not committed.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `GEMINI_API_KEY` is not on fuchitalee | High | High | Unit 1 surfaces this immediately. User must add to `~/.openclaw/.env` and re-trigger `nono` before Unit 3 can run. Alternative: run the Veo leg on the user's local machine and `scp` the output to fuchitalee. |
| S2V-01 `subject_reference` rejects 3 subjects | Med | Med | Probe in Unit 1; fall back to Hailuo-2.3 I2V with a single hero ref + prompt-described others. |
| Veo 3.1 audio returns English despite Korean prompt | Med | Med | Accept the artifact; do not retry. Multi-speaker Korean is unverified. Document in stderr. |
| `last_frame_image` chaining on M3.0 produces visible drift | Med | Med | The artifact is the test. If drift is unacceptable, the next iteration (post-test) can re-stitch with explicit scene-bible cues. |
| Both paths produce visibly poor output | Med | Med | This is the user's decision point. The artifact is the test, not a precondition. User picks iterate vs pivot from watching. |
| Cost exceeds expected budget on retries | Low | Med | Wall-clock budget: 60 min total. Cap retries at 2 per model after the first attempt. |
| Veo 3.1 max `referenceImages` is 2 (not 3) | Med | Med | Probe in Unit 1; fall back to 1 hero ref + prompt-described others. |
| `mmx speech` returns 0-byte output (Korean system voice not loaded) | Low | Low | Accept silent video; log the failure. The visual artifact is still reviewable. |
| 3-stitch M3.0 total runtime <30s | High | Low | ffmpeg concat handles the mismatch; do not pad. The 30s claim was an input target, not a hard output requirement. |
| ffmpeg concat fails (resolution mismatch between stitched clips) | Med | Med | Log ffmpeg stderr; return the longest single clip. The user can still review individual clips. |

## Documentation / Operational Notes

- After the artifact is reviewed, this plan and the requirements doc should be updated to reflect what the API actually does (3-stitch Hailuo-2.3 + TTS mux vs 4-stitch Veo with native audio, no "M3.0" API model name).
- The `out/` directory is gitignored; generated mp4s/mp3s are not committed.
- If the user decides to post, the X post / caption / framing is a separate workstream that draws on the artifact, not on this plan. Per user feedback: distribution is post-test work.
- The first 15-20 minutes of execution should be the Unit 1 probe — confirm endpoints and keys before any generation script is written. Failures here are signal, not errors to bury.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-01-153140-goryeo-banquet-requirements.md](../brainstorms/2026-06-01-153140-goryeo-banquet-requirements.md) (also at `fuchitalee:/Users/fuchitalee/development/royal-outcasts/m3-test/requirements.md`)
- **Ideation doc:** [docs/ideation/2026-06-01-150556-m3-x-post-goryeo-banquet-ideation.md](../ideation/2026-06-01-150556-m3-x-post-goryeo-banquet-ideation.md) (contains the locked 30s prompt)
- **Doc review:** [docs/brainstorms/2026-06-01-162046-goryeo-banquet-doc-review.md](../brainstorms/2026-06-01-162046-goryeo-banquet-doc-review.md)
- **Repo patterns:** `fuchitalee:/Users/fuchitalee/development/royal-outcasts/scripts/i2v_gen.py`, `scripts/video_gen.py`, `scripts/add_burned_subs_scene5.py`
- **Character refs:** `fuchitalee:/Users/fuchitalee/development/royal-outcasts/research/video/{2026-04-21_haeyoung_front_facing.png,yuna_canonical.png,2026-04-18_mina_refined_v2.png}`
- **Voice samples:** `fuchitalee:/Users/fuchitalee/development/royal-outcasts/research/video/audio/`
- **API docs:** context7 `/websites/platform_minimax_io_api-reference`, `/google-gemini/veo-3-nano-banana-gemini-api-quickstart`, `https://ai.google.dev/gemini-api/docs/video`
- **User feedback:** "no oversell" (`feedback_no_oversell.md`), "artifact-as-arbiter" (`feedback_artifact_arbiter.md`), "M3 multimodal terminology" (`feedback_m3_multimodal_terminology.md`)
