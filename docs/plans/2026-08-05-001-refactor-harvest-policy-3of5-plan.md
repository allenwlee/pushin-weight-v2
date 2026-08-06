---
title: "Harvest policy 3/5 — per-brand search paths (4/5 deferred) - Plan"
type: refactor
date: 2026-08-05
amended: 2026-08-05
amendment_note: "Aligned with .claude/skills/avoiding-recurring-mistakes (M1/M4/M5/M7/M8/M11/M14): pre-exec git hygiene, DoD verification queries, DRY reuse of query_plan, preview no external API, reference docs current-state only"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
origin_session: 2026-08-04 GLM under-capture investigation + harvest flexibility discussion
related:
  - docs/reference/twitterapi-live-queries-by-model.md
  - docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
  - docs/how-to/add-tracked-brand.md
  - .claude/skills/avoiding-recurring-mistakes/SKILL.md
---

# Harvest policy 3/5 — per-brand search paths (4/5 deferred) - Plan

### written by Grok 4.3

## Goal Capsule

**Objective.** Make weekly call tweaks and monthly brand onboarding (~1 brand/month) cheap and safe by introducing a **per-brand harvest policy** as the single authoring surface for search paths, deriving today's A/B1/B2/B3/C\* query strings from that policy, adding **preview + coverage invariants**, and **thin regression pins**. Ship **3/5 only** in this plan; record **4/5** (auto-packer, admin UI, generated reference) as deferred follow-up so succession is intentional.

**Authority.** Session-settled: hybrid funnel stays (bare / co / handle); multi-`paths` per brand allowed; brand-local `not_include`; 4/5 after 3/5; GLM under-capture root cause was handle-only placement without keyword path (policy must prevent silent under-coverage).

**Stop when.** Policy file (or equivalent) is the only place humans edit harvest modes/tokens/co/handles for search; `plan_calls` derives specs from policy; `harvest_preview` (or manage command) prints brand→call map + lengths; every `enabled_models` brand has an explicit search path or explicit `paths: []` / `none`; pins assert policy outcomes not full C1 mega-strings; how-to guide for new brands lands; 4/5 listed under Deferred without implementation units in this plan.

**Out of band.** 4/5 auto-packer / admin UI / auto-regenerated reference (todo); hybrid funnel product rules rewrite; translator/classifier changes; GLM-specific product decision (which paths GLM gets) except as migration seed matching current or an explicit improvement called out in U5.

---

## Product Contract

### Summary

Replace call-centric authoring (`x_query_specs` as the human source of truth with three different shapes) with **brand-centric harvest policy**. The planner **derives** the existing six call shapes so runtime stays familiar. Operators onboarding ~1 brand/month add **one policy block** + DB brand/handle rows, run preview, ship — without editing three handle lists and hoping C still fits under 512.

### Problem Frame

1. Search membership is split: C tokens inlined in YAML, B1 brand ids in `wide_net_brands` + DB `is_primary`, B2/B3 **hardcoded handle strings**.
2. `enabled_models` ≠ search coverage (GLM: enabled + attributable, effectively handle-only).
3. Customization (dual path, Kimi `not_include`) is possible but brittle; call-level `not_include` bleeds to all brands on that call.
4. Monthly brand adds and weekly tweaks pay multi-surface tax + doc/pin churn.

### Requirements

#### Policy model (3/5)

- R1. Introduce a per-brand harvest policy as the **authoritative authoring** surface for harvest search (file under `config/` preferred; structure stable for later DB/admin).
- R2. Each brand policy includes at least: `paths` (set: `bare` | `versioned_bare` | `co` | `handle` | empty/none), `tokens` (or split bare/co tokens if needed), `co` (list; used when `co` ∈ paths), `handles` (list without `@`), `not_include` (brand-local).
- R3. Multi-path brands are first-class (`paths: [versioned_bare, handle]` or `[co, handle]`, etc.). Exclusive single-mode enum is **forbidden**.
- R4. Brand-local `not_include` applies only to co-calls that include that brand (no silent bleed to unrelated brands on the same C call unless those brands share the call by packing — prefer packing so Kimi-only bans stay on Kimi's co chunk when feasible; document residual if union is required for shared C chunk in 3/5).
- R5. Call A (list) remains outside brand policy (list id config unchanged).

#### Planner derivation

- R6. Planner builds `XQuerySpec` list for B1/B2/B3/C\* from policy; existing `_build_query` / `plan_calls` remain the renderer (adapter OK).
- R7. 3/5 may use **fixed or hand-maintained co packs** (mirror current C1/C2/C3) when packing; document that 4/5 replaces this with auto-pack. Adding a **co** brand may require editing the pack list in 3/5 — acceptable; must be one place and called out in how-to.
- R8. B1 bare brands come from policy `paths` containing bare/versioned_bare; tokens from policy (optionally still cross-check DB `is_primary` during migration — pick one source for search tokens post-U5 and document it).
- R9. Handle calls derive from policy `handles` (or DB official handles keyed by brand if policy says `handles: from_db` — implementer chooses one; default: policy lists handles for 3/5 clarity).

#### Preview + invariants

- R10. `harvest_preview` (management command or `python -m` entry) prints: each planned call id, length, headroom to 512, brand→call coverage map.
- R11. Invariant: every nickname in `enabled_models` has ≥1 of {bare/co keyword path, handle path} **or** explicit `paths: []` / `mode: none` with documented reason. Fail CI/tests when violated.
- R12. All planned query strings remain &lt; 512 chars.

#### Pins + docs

- R13. Regression nets pin **policy outcomes** (mode/paths, token membership, coverage, co allowlist, length) — not full multi-hundred-char C1 strings as the primary pin.
- R14. How-to guide for adding tracked brands ships with this plan (`docs/how-to/add-tracked-brand.md`).
- R15. Update `docs/reference/twitterapi-live-queries-by-model.md` to **current state only** after cutover (brand→call map + live shapes from preview). **No** "previously…", dual-history remnants, or obsolete call-centric authoring prose — git is the archive (M11). Full auto-regen of that file is 4/5.

#### Execution hygiene (from avoiding-recurring-mistakes)

- R19. **Pre-exec gate (M4):** Before coding or merging this plan, `git fetch`, note `main` tip + open `feat/*`/`fix/*` that touch `monitor/cycle.py`, `x_monitor/query_plan.py`, `config.yaml`, or `docs/reference/`; surface uncommitted work and parallel branches to the user — do not silently merge.
- R20. **DRY (M7):** Do **not** invent a second query builder or parallel "policy renderer" that duplicates `_build_query` / `plan_calls`. New code is load + partition + `XQuerySpec` construction; render stays in `x_monitor/query_plan.py`.
- R21. **No external tax on preview (M8):** `harvest_preview` is **offline** — loads policy + derives strings only. It must not call TwitterAPI.io, LLM, Apify, or prod DB writes. (Live harvest rate limits/concurrency are unchanged by this plan; do not expand fetch concurrency here.)
- R22. **Canonical stack (M1):** v2 Django + Render only; do not write harvest policy loaders that target retired v1 SQLite/`data/x_monitoring.db`. Schema/config changes stay in repo files + existing Django patterns.
- R23. **Plan path (M14):** This plan lives at `docs/plans/YYYY-MM-DD-NNN-…-plan.md` only.

#### Future brands (~1/month) — notes for implementers / operators

- R16. Steady-state onboard after this plan: (1) DB Brand + keywords + official account, (2) one policy block, (3) if `co` ∈ paths, add brand id to co pack list if not auto-included, (4) `harvest_preview`, (5) thin pin or coverage already covered by invariant, (6) deploy.
- R17. Default template for new brands: prefer `paths: [bare, handle]` or versioned tokens when name is unique; use `co` only when ambiguous (like bare GLM / Kimi / Llama).
- R18. Do not require full reference-doc rewrite for each brand in 3/5; how-to points at preview as source of truth for live strings.

### Acceptance Examples

- AE1. `harvest_preview` shows `glm` with an explicit coverage list (whatever paths policy assigns post-migration); never "enabled but empty coverage" without `paths: []`.
- AE2. Changing only policy tokens for a brand changes the derived call string after preview reload (no silent dual source).
- AE3. Kimi (or equivalent) `not_include` F1 terms remain effective on its co path; pure deepseek bare path does not require those terms.
- AE4. New brand fixture with `paths: [bare, handle]` appears on B1 and a handle call; coverage invariant green.
- AE5. All planned strings &lt; 512.

### Scope Boundaries

**In:** harvest policy schema + loader; derive specs; wire cycle planner; preview command; coverage invariant tests; migrate 20 brands; thin pins; how-to guide; reference map consistency pass.

**Out / Deferred to Follow-Up Work (4/5 todo — not units in this plan):**

- Auto-packer that splits C\* by length without fixed chunks
- Admin UI / dashboard to edit policy
- CI auto-regeneration of full `twitterapi-live-queries-by-model.md`
- Hot-reload policy without deploy
- Replacing attribution keyword tables (posts_brands still uses BrandKeyword as today unless already unified)

**Outside this product's identity:** Changing TwitterAPI client; changing C-only LLM relevancy product rules.

### Success Criteria

- Operators edit one policy surface for search paths
- Preview + invariant catch GLM-class gaps
- Monthly brand add documented and &lt;1h for bare+handle case
- 4/5 clearly deferred with stable policy schema that 4 can extend

---

## Planning Contract

### Key Technical Decisions

- **KTD1.** Per-brand harvest policy is the authoring source of truth for search paths. `(session-settled: user-directed — chosen over keeping call-centric x_query_specs as human source: multi-surface edits caused silent under-capture and high tweak cost)`

- **KTD2.** `paths` is a **set** (multi-path brands). `(session-settled: user-directed — preserves GLM on B+C and handle+keyword; exclusive mode rejected)`

- **KTD3.** Brand-local `not_include`. `(session-settled: user-directed — Kimi F1 bans must not be only call-level bleed)`

- **KTD4.** Derive `XQuerySpec` then reuse `_build_query` / `plan_calls` renderer. Avoid rewriting the fetch pipeline. **(M7 DRY — session-settled + skill)**

- **KTD5.** 3/5 fixed/hand co packs OK; 4/5 auto-pack deferred. Schema must not encode "brand forever on C1" as a permanent field — packs are planner-internal.

- **KTD6.** Ship how-to guide in-repo as part of this plan (user-requested), not only plan prose.

- **KTD7.** 4/5 is **todo only** in Scope Boundaries — no implementation units for packer/UI/regen in this plan.

- **KTD8.** Reference doc edits describe **current** harvest policy + derived calls only (M11). No remnant dual-authoring narrative.

- **KTD9.** Verification is part of each unit's DoD, not a post-ship afterthought (M5). Concrete checks listed under Verification Contract.

### High-Level Technical Design

```text
                    ┌─────────────────────────────┐
                    │  harvest_policy (per brand) │
                    │  paths, tokens, co, handles  │
                    │  not_include                │
                    └─────────────┬───────────────┘
                                  │ load
                                  ▼
                    ┌─────────────────────────────┐
                    │  specs_from_policy()        │
                    │  → XQuerySpec[A,B1,B2,B3,C*]│
                    │  (3/5: fixed co packs)      │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │  plan_calls / _build_query  │  (existing)
                    │  PlannedCall.query_string   │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
        harvest_preview     cycle fetch          tests/invariants
        brand→call map      (unchanged)          coverage + thin pins
```

**4/5 later:** replace fixed packs with `pack_co_brands(max_len)`; add admin write → same policy; generate reference from plan.

### Alternatives Considered

| Approach | Why not default for 3/5 |
|---|---|
| Keep call-centric YAML only | Continues silent under-capture + multi-list edits |
| Jump to 4/5 (packer + UI) in one PR | Larger blast radius; 3/5 unblocks monthly onboard sooner |
| DB-only policy without file | Harder review/diff for 3/5; file preferred first |
| Exclusive single `mode` enum | Loses dual-path customization |

### Risks

| Risk | Mitigation |
|---|---|
| Dual-write during migration (policy + old x_query_specs) | U5 cutover: planner reads policy only; old specs become derived or deleted |
| Co pack hand-edit forgotten on new co brand | How-to + preview length; optional warning if co brand not in any pack |
| not_include bleed when brands share a C pack | Prefer pack Kimi alone or document union; 4/5 can refine |
| Token source DB vs policy conflict | Pick policy as search token source after migration; DB remains for attribution |

### Assumptions

- Current 7-call layout (A + B1 + B2 + B3 + C1 + C2 + C3) remains the runtime target for 3/5.
- ~1 new brand/month; most can be bare+handle.
- Render deploy still required for config/policy changes (hot-reload is 4/5-adjacent, out of scope).

---

## Implementation Units

### U0. Pre-exec hygiene (M4)

**Goal.** Avoid colliding with parallel harvest/config work before any code lands.

**Requirements.** R19

**Dependencies.** None

**Files.** none (ops gate)

**Approach.**
1. `git fetch`; log `origin/main` tip; list branches touching `monitor/cycle.py`, `x_monitor/query_plan.py`, `config.yaml`, `docs/reference/twitterapi-live-queries-by-model.md`.
2. `git status` / `git worktree list` — surface dirty trees and other worktrees.
3. If parallel work exists on the same surfaces, **stop and ask the user** before branching or editing.

**Test expectation:** none — process gate.

**Verification.** Written note in the PR/commit body or execution log: "no conflicting open work" or "user approved proceed despite …".

---

### U1. Pin harvest surface regression net (BEFORE)

**Goal.** Capture current brand→call / string properties so migration cannot silently regress unrelated brands.

**Requirements.** R13 (BEFORE pins)

**Dependencies.** U0

**Files.**
- `tests/test_harvest_policy_regression_net.py` (new) or extend `tests/test_hybrid_harvest_regression_net.py`

**Approach.**
1. Pin BEFORE: which brands appear on which call_ids from live config (or planner output).
2. Pin co allowlist `{llm, model, api, agentic, huggingface}` and C2 extras.
3. Pin "glm currently has handle path via Zai_org; no C brand dict entry" as BEFORE comment — AFTER may intentionally improve.

**Test scenarios.**
- Covers AE: pins load against current planner before policy cutover.
- AFTER notes: intentional path changes for migrated brands documented in pin comments.

**Verification (M5).**
- `pytest` on the pin file green on current `main` **before** U3 wire flip.
- Record pin file path + count of pinned brand→call entries in the unit PR note.

---

### U2. Harvest policy schema + loader

**Goal.** Define policy structure and load it from `config/harvest_policy.yaml` (or agreed path).

**Requirements.** R1–R5, R2 multi-paths, R22

**Dependencies.** U1

**Files.**
- `config/harvest_policy.yaml` (new)
- `x_monitor/harvest_policy.py` (new) — load + validate
- `tests/test_harvest_policy_load.py` (new)

**Approach.**
1. Schema fields: paths, tokens, co, handles, not_include (optional notes).
2. Validation: unknown path names fail; empty tokens with bare/co path fail; handle path requires ≥1 handle.
3. Do not yet wire planner (U3). No v1 SQLite paths.

**Test scenarios.**
- Happy: load fixture with multi-path brand.
- Edge: empty paths allowed only when explicitly none.
- Error: co path with empty co list fails or warns per chosen rule (prefer fail).
- Error: unknown path key rejected.

**Verification (M5).**
- `pytest tests/test_harvest_policy_load.py` green.
- Loader rejects a deliberately broken fixture (assert one negative case).

---

### U3. Derive XQuerySpec from policy + wire plan_calls

**Goal.** `plan_calls_for_cycle` uses `specs_from_policy` instead of hand-authored heterogeneous specs as source of truth.

**Requirements.** R6–R9, R12, R20 (DRY)

**Dependencies.** U2

**Files.**
- `x_monitor/harvest_policy.py` (`specs_from_policy`)
- `x_monitor/query_plan.py` (only if adapter needed — prefer zero fork of render logic)
- `monitor/cycle.py` (`plan_calls_for_cycle` / `_resolve_x_query_specs`)
- `tests/test_specs_from_policy.py` (new)
- `config.yaml` — stop authoring live brands/handles lists as source (remove or generate-only)

**Approach.**
1. Partition brands by paths → bare list, co list, handle lists (pure vs other if still desired — can keep B2/B3 split via policy flag `handle_tier: pure|other` or two handle packs).
2. Fixed co packs (3/5): table or YAML section `co_packs: [[...],[...],...]` owned next to policy.
3. Union `not_include` onto co specs for brands in each pack.
4. Wire cycle to load policy → specs → **existing** `plan_calls` / `_build_query` only (M7).

**Patterns to follow.** Existing `XQuerySpec`, `_build_query` handle-only / empty-co omit paren behavior.

**Test scenarios.**
- Happy: bare brand tokens appear in B1-shaped string without co paren.
- Happy: co brand appears with secondary co group.
- Happy: multi-path brand appears on bare/co and handle calls.
- Edge: all strings &lt; 512.
- Integration: `plan_calls_for_cycle` returns 7 calls with expected call_ids.
- DRY: no new module reimplements paren/OR/co join (grep/code review gate).

**Verification (M5).**
- `pytest tests/test_specs_from_policy.py` green.
- `plan_calls_for_cycle` (or dry-run entry already in repo) returns 7 call_ids; each `len(query_string) < 512`.
- Diff review: no second renderer path.

---

### U4. harvest_preview + coverage invariant

**Goal.** Operator and CI can see brand→call map and fail on under-coverage.

**Requirements.** R10, R11, R16, R21 (no external API)

**Dependencies.** U3

**Files.**
- `x_monitor/harvest_preview.py` or `core/management/commands/harvest_preview.py`
- `tests/test_harvest_coverage_invariant.py` (new)

**Approach.**
1. Preview prints call_id, len, headroom, query (optional truncate), coverage map.
2. Invariant test: foreach enabled brand, coverage non-empty unless explicit none.
3. Optional: warn if co brand missing from all co_packs.
4. **Must not** network to TwitterAPI/LLM/Render (M8). Pure local derive.

**Test scenarios.**
- Covers AE1: enabled brand with empty paths fails invariant.
- Happy: full policy of 20 brands passes.
- Edge: explicit `paths: []` allowed only with flag/reason field if required by schema.
- Guard: unit test or review confirms preview has no HTTP client imports for fetch/LLM.

**Verification (M5).**
- Preview command exits 0 offline; prints coverage for every enabled brand.
- `pytest tests/test_harvest_coverage_invariant.py` green.
- Intentionally drop one brand's paths in a temp fixture → invariant fails.

---

### U5. Migrate all 20 brands + cutover

**Goal.** Seed `harvest_policy.yaml` from current live behavior (or intentional small fixes), delete dual authoring.

**Requirements.** R8, R9, R15 (M11 current-only), R16–R18

**Dependencies.** U3, U4

**Files.**
- `config/harvest_policy.yaml` (full 20 brands)
- `config.yaml` (strip obsolete x_query_specs brand/handle authoring)
- `docs/reference/twitterapi-live-queries-by-model.md` (**rewrite current state only** — M11)
- U1 AFTER pins

**Approach.**
1. Map each enabled brand from current config into paths/tokens/handles/co/not_include.
2. Preserve Kimi F1 not_include on moonshot_kimi.
3. GLM: migrate handle path; **prefer intentional keyword path** (versioned_bare and/or co) if product still treats under-capture as bug — else explicit handle-only + tracked follow-up. Never accidental silence.
4. Update AFTER regression pins.
5. Reference doc: replace call-centric authoring description with policy → derived calls **as of cutover**. Delete obsolete dual-list prose; one line max if v1 ever mentioned.

**Test scenarios.**
- All 20 brands in policy.
- Coverage invariant green.
- Lengths &lt; 512 for all calls.
- Snapshot of brand→call map stable except documented intentional deltas.

**Verification (M5).**
- `harvest_preview` brand map matches policy for all 20 nicknames.
- `pytest` full harvest-policy + hybrid nets green.
- Reference doc: grepping for "legacy wide-net B2" / dual-authoring remnants returns no false "current" claims (spot-check).
- After deploy (when user asks to deploy — not volunteered): one harvest cycle can still plan 7 calls (log or dry-run on Render) — **only if user requests deploy verification**.

**Execution note:** Characterization of current planner output before flipping the wire. Do not volunteer commit/push/deploy (M2).

---

### U6. How-to guide for adding tracked brands

**Goal.** Operators and agents can onboard ~1 brand/month without rediscovering the funnel.

**Requirements.** R14, R16–R18

**Dependencies.** U5 (or draft in parallel after U2 schema frozen; finalize after U5)

**Files.**
- `docs/how-to/add-tracked-brand.md` — already drafted with plan; **finalize** command names against U4 ship

**Approach.**
1. Checklist: DB brand + keywords + official handle → policy block → co pack if needed → preview → deploy → optional dashboard.
2. Decision tree: bare vs co vs versioned tokens.
3. Examples: bare lab; polyseme with not_include; dual path.
4. Point to 4/5 deferred improvements (auto-pack).
5. Explicit "do not only enable without policy paths" (GLM-class).

**Test expectation:** none — documentation unit; verify links and commands match U4/U5 names.

**Verification (M5).**
- How-to commands match the real entrypoint from U4 (copy-paste dry-run).
- Link from reference or README/CONCEPTS only if those files already list how-tos — do not invent new chrome.

---

## Deferred to Follow-Up Work (4/5 todo)

Track as future plan (do **not** implement here):

| Item | Why later |
|---|---|
| Auto `pack_co_brands(max_len)` | Removes monthly hand C-split tax |
| Admin UI to edit policy | Non-YAML operators |
| Generate `twitterapi-live-queries-by-model.md` from preview | Stops doc drift |
| Rich preview report (JSON/HTML, pack_log, headroom alerts) | Ops polish |
| Hot-reload policy without full deploy | Optional ops |

**Succession rule:** 3/5 schema is the API 4/5 writes; do not invent a second policy model in 4/5.

---

## Verification Contract

**Automated**
- pytest: policy load, specs_from_policy, coverage invariant, thin regression BEFORE/AFTER, length &lt; 512
- Coverage invariant fails if any enabled brand lacks paths without explicit none

**Operator (local / staging — no prod write required for this plan)**
- `harvest_preview` (exact command from U4) prints 7 calls + brand→call map for all enabled brands
- Manual: flip one token in policy → preview changes that call only; flip back
- How-to steps match shipped commands

**Prod (only when user requests deploy verification — M2/M5)**
- Via Render CLI / logs: harvest cycle still plans 7 calls after policy deploy (no TwitterAPI probe required for config-only change)
- Do **not** use ad-hoc direct psql to prod host for routine checks; prefer existing Render CLI patterns in repo memory

**Not in scope to verify**
- LLM concurrency / classifier model (unchanged; M8/M12 do not add new LLM paths here)
- i18n catalog (no user-facing chrome strings in this plan)

## Definition of Done

- [ ] U0 pre-exec hygiene recorded
- [ ] U1 BEFORE/AFTER regression net green
- [ ] Policy file authoring live for all enabled brands
- [ ] Planner derives specs via existing `_build_query`/`plan_calls` (no parallel renderer)
- [ ] Dual hand-authored handle/brand lists removed as search source of truth
- [ ] `harvest_preview` offline + coverage invariant green
- [ ] How-to `docs/how-to/add-tracked-brand.md` accurate vs shipped CLI
- [ ] Reference doc = **current** brand→call / shapes only (M11)
- [ ] 4/5 only in Deferred (no packer/UI units shipped as "done")
- [ ] Scope delivered vs plan documented in commits (plan-execution contract)
- [ ] No volunteer commit/push/deploy unless user asked (M2)

---

## System-Wide Impact

- Harvest config authoring becomes brand-centric; fewer silent gaps when adding brands monthly.
- Attribution/DB keyword paths may still exist for non-search uses — document boundary.
- Cron deploy still ships policy with code until 4/5 hot-reload.
- No new external API surface or URL endpoints (M9 N/A).

## Documentation / Operational Notes

- Primary operator doc after ship: `docs/how-to/add-tracked-brand.md`
- Live string inspection: `harvest_preview` is source of truth; reference doc is current snapshot only
- When adding co brands under 3/5: edit `co_packs` in the same PR as the policy block
- Skill: re-read `.claude/skills/avoiding-recurring-mistakes/SKILL.md` at start of `ce-work` on this plan

## Sources & Research

- Session: GLM under-capture (cohort 11 vs deepseek 101); live config C brands exclude glm; B2 handle-only
- Session: 3/5 then 4/5 succession; multi-paths + brand-local not_include required
- Code: `config.yaml` `x_query_specs`, `x_monitor/query_plan.py`, `monitor/cycle.py` `_load_primary_keywords` / `plan_calls_for_cycle`
- Docs: `docs/reference/twitterapi-live-queries-by-model.md`, hybrid funnel plans 2026-07-28/30
- Skill: `.claude/skills/avoiding-recurring-mistakes/SKILL.md` (M1, M2, M4, M5, M7, M8, M11, M14)
