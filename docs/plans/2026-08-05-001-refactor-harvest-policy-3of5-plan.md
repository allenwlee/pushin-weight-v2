---
title: "Harvest policy 3/5 — per-brand search paths (4/5 deferred) - Plan"
type: refactor
date: 2026-08-05
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
origin_session: 2026-08-04 GLM under-capture investigation + harvest flexibility discussion
related:
  - docs/reference/twitterapi-live-queries-by-model.md
  - docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
  - docs/how-to/add-tracked-brand.md
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
- R15. Update or mark stale sections of `docs/reference/twitterapi-live-queries-by-model.md` so brand→call map matches policy (full auto-regen is 4/5).

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

- **KTD4.** Derive `XQuerySpec` then reuse `_build_query` / `plan_calls` renderer. Avoid rewriting the fetch pipeline.

- **KTD5.** 3/5 fixed/hand co packs OK; 4/5 auto-pack deferred. Schema must not encode "brand forever on C1" as a permanent field — packs are planner-internal.

- **KTD6.** Ship how-to guide in-repo as part of this plan (user-requested), not only plan prose.

- **KTD7.** 4/5 is **todo only** in Scope Boundaries — no implementation units for packer/UI/regen in this plan.

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

### U1. Pin harvest surface regression net (BEFORE)

**Goal.** Capture current brand→call / string properties so migration cannot silently regress unrelated brands.

**Requirements.** R13 (BEFORE pins)

**Dependencies.** None

**Files.**
- `tests/test_harvest_policy_regression_net.py` (new) or extend `tests/test_hybrid_harvest_regression_net.py`

**Approach.**
1. Pin BEFORE: which brands appear on which call_ids from live config (or planner output).
2. Pin co allowlist `{llm, model, api, agentic, huggingface}` and C2 extras.
3. Pin "glm currently has handle path via Zai_org; no C brand dict entry" as BEFORE comment — AFTER may intentionally improve.

**Test scenarios.**
- Covers AE: pins load against current planner before policy cutover.
- AFTER notes: intentional path changes for migrated brands documented in pin comments.

**Verification.** pytest green on current main before U3 lands.

---

### U2. Harvest policy schema + loader

**Goal.** Define policy structure and load it from `config/harvest_policy.yaml` (or agreed path).

**Requirements.** R1–R5, R2 multi-paths

**Dependencies.** U1

**Files.**
- `config/harvest_policy.yaml` (new)
- `x_monitor/harvest_policy.py` (new) — load + validate
- `tests/test_harvest_policy_load.py` (new)

**Approach.**
1. Schema fields: paths, tokens, co, handles, not_include (optional notes).
2. Validation: unknown path names fail; empty tokens with bare/co path fail; handle path requires ≥1 handle.
3. Do not yet wire planner (U3).

**Test scenarios.**
- Happy: load fixture with multi-path brand.
- Edge: empty paths allowed only when explicitly none.
- Error: co path with empty co list fails or warns per chosen rule (prefer fail).
- Error: unknown path key rejected.

**Verification.** unit tests green; sample file documents 2–3 brands including multi-path and not_include.

---

### U3. Derive XQuerySpec from policy + wire plan_calls

**Goal.** `plan_calls_for_cycle` uses `specs_from_policy` instead of hand-authored heterogeneous specs as source of truth.

**Requirements.** R6–R9, R12

**Dependencies.** U2

**Files.**
- `x_monitor/harvest_policy.py` (`specs_from_policy`)
- `x_monitor/query_plan.py` (only if adapter needed)
- `monitor/cycle.py` (`plan_calls_for_cycle` / `_resolve_x_query_specs`)
- `tests/test_specs_from_policy.py` (new)
- `config.yaml` — stop authoring live brands/handles lists as source (remove or generate-only)

**Approach.**
1. Partition brands by paths → bare list, co list, handle lists (pure vs other if still desired — can keep B2/B3 split via policy flag `handle_tier: pure|other` or two handle packs).
2. Fixed co packs (3/5): table or YAML section `co_packs: [[...],[...],...]` owned next to policy.
3. Union `not_include` onto co specs for brands in each pack.
4. Wire cycle to load policy → specs → existing `plan_calls`.

**Patterns to follow.** Existing `XQuerySpec`, `_build_query` handle-only / empty-co omit paren behavior.

**Test scenarios.**
- Happy: bare brand tokens appear in B1-shaped string without co paren.
- Happy: co brand appears with secondary co group.
- Happy: multi-path brand appears on bare/co and handle calls.
- Edge: all strings &lt; 512.
- Integration: `plan_calls_for_cycle` returns 7 calls with expected call_ids.

**Verification.** unit + cycle plan smoke.

---

### U4. harvest_preview + coverage invariant

**Goal.** Operator and CI can see brand→call map and fail on under-coverage.

**Requirements.** R10, R11, R16

**Dependencies.** U3

**Files.**
- `x_monitor/harvest_preview.py` or `core/management/commands/harvest_preview.py`
- `tests/test_harvest_coverage_invariant.py` (new)

**Approach.**
1. Preview prints call_id, len, headroom, query (optional truncate), coverage map.
2. Invariant test: foreach enabled brand, coverage non-empty unless explicit none.
3. Optional: warn if co brand missing from all co_packs.

**Test scenarios.**
- Covers AE1: enabled brand with empty paths fails invariant.
- Happy: full policy of 20 brands passes.
- Edge: explicit `paths: []` allowed only with flag/reason field if required by schema.

**Verification.** command runs locally; invariant in pytest.

---

### U5. Migrate all 20 brands + cutover

**Goal.** Seed `harvest_policy.yaml` from current live behavior (or intentional small fixes), delete dual authoring.

**Requirements.** R8, R9, R15; notes R16–R18

**Dependencies.** U3, U4

**Files.**
- `config/harvest_policy.yaml` (full 20 brands)
- `config.yaml` (strip obsolete x_query_specs brand/handle authoring)
- `docs/reference/twitterapi-live-queries-by-model.md` (brand→call map sync; mark generated strings as preview-sourced where needed)
- U1 AFTER pins

**Approach.**
1. Map each enabled brand from current config/docs into paths/tokens/handles/co/not_include.
2. Preserve Kimi/C1 F1 not_include on moonshot_kimi.
3. GLM: migrate current handle path; **recommend** adding versioned_bare or co path in same PR only if product agrees — otherwise pin handle-only as explicit and file follow-up issue (do not leave accidental). Prefer making GLM keyword path intentional in this unit if session consensus holds under-capture is a bug.
4. Update AFTER regression pins.

**Test scenarios.**
- All 20 brands in policy.
- Coverage invariant green.
- Lengths &lt; 512 for all calls.
- Snapshot of brand→call map stable except documented intentional deltas.

**Verification.** preview matches expectations; pytest green.

**Execution note:** Prefer characterization of current planner output before flipping the wire.

---

### U6. How-to guide for adding tracked brands

**Goal.** Operators and agents can onboard ~1 brand/month without rediscovering the funnel.

**Requirements.** R14, R16–R18

**Dependencies.** U5 (or draft in parallel after U2 schema frozen; finalize after U5)

**Files.**
- `docs/how-to/add-tracked-brand.md` (new) — **also delivered as part of this planning request; keep in sync with shipped behavior at U6**

**Approach.**
1. Checklist: DB brand + keywords + official handle → policy block → co pack if needed → preview → deploy → optional dashboard.
2. Decision tree: bare vs co vs versioned tokens.
3. Examples: bare lab; polyseme with not_include; dual path.
4. Point to 4/5 deferred improvements (auto-pack).

**Test expectation:** none — documentation unit; verify links and commands match U4/U5 names.

**Verification.** guide reviewed against `harvest_preview` real flags; linked from reference or CONCEPTS if present.

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

- pytest: policy load, specs_from_policy, coverage invariant, thin regression AFTER, length &lt; 512
- `harvest_preview` shows 7 calls + brand map for all enabled brands
- Manual: flip one token in policy → preview changes that call only
- How-to steps match shipped commands

## Definition of Done

- [ ] U1 BEFORE/AFTER regression net green
- [ ] Policy file authoring live for all enabled brands
- [ ] Planner derives specs; dual hand-authored handle/brand lists removed as source of truth
- [ ] harvest_preview + coverage invariant green
- [ ] How-to `docs/how-to/add-tracked-brand.md` accurate
- [ ] Reference brand→call map consistent with policy
- [ ] 4/5 only in Deferred (no packer/UI units shipped as "done")
- [ ] Scope delivered vs plan documented in commits

---

## System-Wide Impact

- Harvest config authoring becomes brand-centric; fewer silent gaps when adding brands monthly.
- Attribution/DB keyword paths may still exist for non-search uses — document boundary.
- Cron deploy still ships policy with code until 4/5 hot-reload.

## Documentation / Operational Notes

- Primary operator doc after ship: `docs/how-to/add-tracked-brand.md`
- Live string inspection: `harvest_preview` over hand-maintained reference strings
- When adding co brands under 3/5: edit `co_packs` in the same PR as the policy block

## Sources & Research

- Session: GLM under-capture (cohort 11 vs deepseek 101); live config C brands exclude glm; B2 handle-only
- Session: 3/5 then 4/5 succession; multi-paths + brand-local not_include required
- Code: `config.yaml` `x_query_specs`, `x_monitor/query_plan.py`, `monitor/cycle.py` `_load_primary_keywords` / `plan_calls_for_cycle`
- Docs: `docs/reference/twitterapi-live-queries-by-model.md`, hybrid funnel plans 2026-07-28/30
