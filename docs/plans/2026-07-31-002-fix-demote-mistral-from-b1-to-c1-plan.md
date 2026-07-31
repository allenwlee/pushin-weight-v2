---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
title: "fix: Demote Mistral from B1 wide-net to C1 co-constrained (hybrid funnel)"
created: 2026-07-31
depth: standard
type: fix
---

# fix: Demote Mistral from B1 wide-net to C1 co-constrained

## Summary

Move `mistral` out of the B1 bare wide-net (where its polysemous token collides with weather/common-noun noise) into C1, where it shares the 5-term minimal co allowlist already proven against the same class of ambiguity (`MiMo`/`Kimi`/`Yi`/`Llama`). Net effect: B1 shrinks from 6 to 5 brands; C1 grows from 4 to 5; no new calls, no new shape, no co expansion.

## Problem Frame

The hybrid-funnel plan (`docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md`) shipped B1 as a **bare** wide-net (`co_occurrence: []`, R3) for the six highest-presence global brands. Five of those six (`minimax`, `qwen`, `deepseek`, `stepfun`, `hunyuan`) have distinctive tokens that survive without an AND-filter. **Mistral is the exception**: its primary tokens (`Mistral`, `Mixtral`) collide with the French regional weather term "mistral" and with anything "Mistral AI" in adjacent contexts (security tooling, infrastructure posts), producing high-recall noise on a bare keyword sweep. The co-constrained pattern C1 uses (5-term minimal allowlist + thin co) is the same pattern that already saves `Llama` from "llama the animal" and `Kimi` from "kimi the pronoun" — it should also cover Mistral.

The cost of leaving Mistral in B1: false-positive posts dilute the feed and burn credits on non-AI material. The cost of moving it: a known-good config change with zero new architecture.

## Requirements

- R1. `config.yaml::call_b_groups[0]` (B1) MUST contain exactly `[minimax, qwen, deepseek, stepfun, hunyuan]` after this change — `mistral` MUST NOT be present.
- R2. `config.yaml::x_query_specs[0]` (C1) `brands:` map MUST contain a `mistral` key whose value is the primary tokens currently in `data/brand_keywords.json` for brand_id=`mistral`.
- R3. C1's co-occurrence list MUST remain the 5-term minimal allowlist `[llm, model, api, agentic, huggingface]` — no expansion (Mistral rides the same shared co the other C1 brands use).
- R4. B1's `co_occurrence: []` MUST remain empty.
- R5. The total call count MUST remain 7 (A + B1 + B2 + B3 + C1 + C2 + C3).
- R6. C1's rendered query length MUST remain under the 512-char X advanced-search cap.
- R7. `data/brand_keywords.json` row count for `mistral` MUST remain 4 (2 primary + 2 quoted) — no DB rows change.
- R8. The reference doc `docs/reference/twitterapi-live-queries-by-model.md` MUST be updated so Mistral moves from the B1 per-brand table to the C1 per-brand table; other rows in those tables MUST NOT change.

## Key Technical Decisions

- **KTD1. Use inline `mistral: [Mistral, Mixtral]` in C1's `brands:` map.** *(session-settled: user-directed — chosen over "load from DB via primary_keywords": C1's `_build_query` renderer iterates `spec.brands.items()` only, while B1's wide-net branch iterates `spec.wide_net_brands` against the externally-loaded `primary_keywords` dict. Inline placement is the only renderer path that works without code changes.)*
- **KTD2. Tokens are `[Mistral, Mixtral]` (the two primary rows in `data/brand_keywords.json`).** *(session-settled: user-directed — chosen over including the quoted `"Mistral"`/`"Mixtral"` variants: those quoted variants are the operator-curated non-primary patterns used for fallback matching, not for primary co-search. The existing B1 wide-net also reads only the primary set via `is_primary=True` filtering.)*
- **KTD3. No co expansion on C1.** *(session-settled: user-directed — chosen over adding 1-2 extra terms: Mistral's polysemy ("mistral wind", "Mistral security") overlaps with the same loanword/tech-context set the existing 5-term allowlist already targets. C2's optional `baidu`/`文心` additions are brand-specific disambiguators Mistral does not need.)*
- **KTD4. Regression net pins the Mistral move + 7-call shape only.** *(session-settled: user-directed — chosen over pinning every brand-coverage surface: this is a focused config change; aggressive pinning of the full 7-call layout belongs to `tests/test_hybrid_harvest_regression_net.py` which already pins it via `EXPECTED_CALL_IDS_AFTER_U3` and `EXPECTED_CO_COUNTS_AFTER`.)*

## Implementation Units

### U1. Remove `mistral` from B1 wide-net brands

**Goal.** Drop `mistral` from `config.yaml::call_b_groups[0]` and from `config.yaml::x_query_specs[?call_id=B1].wide_net_brands`, plus the doc and notes that reference the count.

**Files.**
- `config.yaml` — B1 entry, `call_b_groups` block, and B1 notes comment
- `docs/reference/twitterapi-live-queries-by-model.md` — B1 per-brand table (remove mistral row) and B1 inline shape example (re-render with 5 brands)

**Approach.**
1. Edit `config.yaml::call_b_groups[0]` from `[minimax, qwen, deepseek, mistral, stepfun, hunyuan]` to `[minimax, qwen, deepseek, stepfun, hunyuan]`.
2. Edit the `wide_net_brands:` field of the B1 spec (`x_query_specs[*].call_id == "B1"`) to match.
3. Update the B1 `notes:` block: change `6 brands:` count to `5 brands:` and drop `mistral` from the listed slugs.
4. In the reference doc, remove the row `#4 mistral` from the B1 per-brand table.
5. Re-render the B1 shape example by removing the `OR (Mistral OR Mixtral)` clause.

**Test scenarios.**
- `config.yaml` parses as valid YAML with the edited `call_b_groups[0]` length 5
- `x_query_specs[*].call_id == "B1"` has `wide_net_brands` length 5
- The rendered B1 query string (re-computed by the existing test fixtures) does NOT contain `Mistral` or `Mixtral`
- The B1 doc table has 5 rows and no row with brand_id `mistral`

**Verification.** `pytest tests/test_query_plan_hybrid_shapes.py tests/test_hybrid_harvest_regression_net.py -k "B1 or wide_net"` green; manual `git diff config.yaml` shows the four edits land together.

### U2. Add `mistral` to C1 brand group

**Goal.** Insert `mistral` into `config.yaml::x_query_specs[0]` (the C1 spec) under `brands:` so it shares the 5-term minimal co allowlist with mimo/moonshot_kimi/yi/llama.

**Files.**
- `config.yaml` — C1 `brands:` dict and C1 `notes:` block
- `docs/reference/twitterapi-live-queries-by-model.md` — C1 per-brand table (add mistral row) and C1 shape example (extend with Mistral/Mixtral OR-group)

**Approach.**
1. Add `mistral: [Mistral, Mixtral]` to the C1 spec's `brands:` dict (alphabetical ordering preferred: between `mimo` and `moonshot_kimi`).
2. Update C1 `notes:` block: change `4 brands` to `5 brands` and note the move in a one-line credit: "Mistral demoted from B1 bare (polysemous); rides the shared 5-term co."
3. In the reference doc, add a new row to the C1 per-brand table with brand_id `mistral`, primary tokens `[Mistral, Mixtral]`, count 2.
4. Update the C1 shape example by adding `OR (Mistral OR Mixtral)` to the primary OR-chain.

**Test scenarios.**
- `config.yaml` parses as valid YAML
- `x_query_specs[*].call_id == "C1"` `brands.mistral == [Mistral, Mixtral]` (order may vary; treat as set comparison)
- The rendered C1 query string contains both `Mistral` and `Mixtral`
- C1 query length is still `< 512` characters (assert `<= 400` to leave headroom)
- The C1 doc table has 5 rows and includes a row with brand_id `mistral`

**Verification.** `pytest tests/test_query_plan_hybrid_shapes.py tests/test_hybrid_harvest_regression_net.py -k "C1 or mistral"` green; visual diff of the shape example matches the new 5-brand group.

### U3. Pin Mistral move + 7-call shape (regression net)

**Goal.** Add a focused regression test that pins (a) `mistral` is in C1's brand group and NOT in B1's `wide_net_brands`, and (b) the 7-call shape survives (B1 still 5 brands, C1 still 5 brands, B2/B3 unchanged).

**Files.**
- `tests/test_mistral_call_placement.py` (new) — focused regression net

**Approach.**
1. New test module with three test functions:
   - `test_mistral_in_c1_brand_group`: load `config.yaml`, find the spec with `call_id == "C1"`, assert `"mistral" in c1_spec.brands` and `set(c1_spec.brands["mistral"]) == {"Mistral", "Mixtral"}`.
   - `test_mistral_not_in_b1_wide_net`: load `config.yaml`, find the B1 spec, assert `"mistral" not in b1_spec.wide_net_brands` and `len(b1_spec.wide_net_brands) == 5`.
   - `test_seven_call_shape_invariant`: assert `EXPECTED_CALL_IDS_AFTER_U3 == {"A", "B1", "B2", "B3", "C1", "C2", "C3"}` (the value already defined in `tests/test_hybrid_harvest_regression_net.py`; re-import or duplicate as needed).
2. Use `yaml.safe_load` over `config.yaml` to read the file directly (mirror the pattern in `tests/test_hybrid_harvest_regression_net.py`).
3. Add a docstring noting the change and the BEFORE state (Mistral was in B1's wide_net_brands before this plan).

**Test scenarios.**
- All three tests fail when the BEFORE state is restored (Mistral back in B1, missing from C1) — verified by temporarily reverting U1+U2 in a local check
- All three tests pass against the AFTER state (this plan's target)
- The test file's assertion message names the offending call_id and brand_id so a failure points at the right surface

**Verification.** `pytest tests/test_mistral_call_placement.py -v` green; tests are independent of `manage.py` (no `django_db` marker needed since they read `config.yaml` directly).

### U4. Reference doc "Where to look next" + per-call index update

**Goal.** Update the reference doc's per-call brand tables and the at-a-glance table so the new B1 (5 brands) and C1 (5 brands) shapes match the live config.

**Files.**
- `docs/reference/twitterapi-live-queries-by-model.md` — at-a-glance table and any cross-reference that mentions 6 brands in B1 or 4 brands in C1

**Approach.**
1. If the at-a-glance table near the top of the doc lists per-call brand counts, update B1's count from 6 to 5 and C1's count from 4 to 5.
2. Update the C1 section heading (currently `C1 -- mimo + kimi + yi + llama with 5-term co-occurrence`) to reflect 5 brands: `C1 -- mimo + kimi + yi + llama + mistral with 5-term co-occurrence`.
3. Add a `Last reviewed: 2026-07-31` footer line listing the move.

**Test scenarios.**
- Visual diff confirms the doc strings match the new shape
- The doc's per-brand table for B1 has 5 rows, for C1 has 5 rows

**Verification.** `grep -c "^|.*mistral" docs/reference/twitterapi-live-queries-by-model.md` returns 1 (only in C1 table); `grep -c "Mistral" docs/reference/twitterapi-live-queries-by-model.md` is non-zero (still documented) and consistent with C1's shape example.

## Patterns to Follow

- The C1 brand-group pattern (alphabetical keys, double-quoted multiword tokens, primary-token-only lists) — see existing C1 `brands:` entries for `mimo`, `moonshot_kimi`, `yi`, `llama` in `config.yaml`.
- The B1 `wide_net_brands` pattern (no quotes, comma-separated, no trailing comma) — same convention used in `call_b_groups` and the B1 spec.
- The regression-net test pattern (`yaml.safe_load(REPO_ROOT / "config.yaml")` + module-level pinned values) — see `tests/test_hybrid_harvest_regression_net.py::_load_config()`.
- The "shape (live, from `_build_query`)" doc convention — every shape example in `docs/reference/twitterapi-live-queries-by-model.md` quotes the rendered query string from a real fixture; the new shape must too.

## Out of Scope

- Changing the C1 co-occurrence list (stays at 5 terms).
- Re-running the brand-keyword purity migration (R15/R16 from plan 2026-07-30-002 already demoted bare `Mistral` to `Mistral AI` + `Mixtral` in the DB — `data/brand_keywords.json` already reflects this).
- Updating the `minimax` row in the B1 doc table that incorrectly lists `m2.5` as a primary token (this is pre-existing doc drift, not introduced by this change).
- Changing `enabled_models` in `config.yaml` (mistral stays in the list — only its call placement changes).
- Touching `core/models.py`, migrations, `x_monitor/query_plan.py`, `monitor/cycle.py`, or `x_monitor/attribution.py`.

## Deferred to Follow-Up Work

- If the live harvest shows post-move that Mistral posts in C1 are undercounted vs. the pre-move B1 totals, add a not_include list or expand C1's co allowlist (deferred until post-deploy measurement justifies it).
- Generalizing the `spec.brands` renderer to optionally read from `primary_keywords` (would let all C-path specs share a single primary-tokens loader instead of inline lists) — orthogonal to this change.

## Risks & Mitigations

- **Risk:** C1's rendered query grows past the 512-char cap when Mistral is added. **Mitigation:** U2's test scenario asserts `length <= 400` (current C1 is 264; adding 2 tokens + parens is ~22 chars; new length ~286 — well under cap). The existing `assert_under_length_cap` in `x_monitor/queries.py` enforces the hard 512 limit at runtime.
- **Risk:** The bare-B1 wide-net, now missing Mistral, undercounts Mistral posts that previously appeared in B1. **Mitigation:** C1 is expected to capture them — its 5-term co matches what the v1 era's full-22 co matched for Mistral (per plan 2026-07-30-002's R11). Verify post-deploy via `x_monitor.relevancy` keep rates on the C1 source.
- **Risk:** The doc's existing stale row (`minimax` claims `m2.5` as primary) gets caught up in this change. **Mitigation:** U4 explicitly scopes to the at-a-glance table and B1/C1 tables only; `minimax`'s `m2.5` row stays untouched. The doc drift surfaces in the next doc-review pass.

## Verification Contract

- `pytest tests/test_mistral_call_placement.py -v` green
- `pytest tests/test_query_plan_hybrid_shapes.py tests/test_hybrid_harvest_regression_net.py -v` green (no existing tests broken)
- `python -c "import yaml; d=yaml.safe_load(open('config.yaml')); print(d['call_b_groups']); print([s['call_id'] for s in d['x_query_specs']])"` shows `[minimax, qwen, deepseek, stepfun, hunyuan]` and `['C1', 'C2', 'C3']`
- Visual diff of `config.yaml` shows exactly: B1 `wide_net_brands` 5 slugs; C1 `brands.mistral == [Mistral, Mixtral]`; B1 notes "5 brands"; C1 notes "5 brands"
- Visual diff of `docs/reference/twitterapi-live-queries-by-model.md` shows: B1 per-brand table 5 rows; C1 per-brand table 5 rows; C1 heading mentions 5 brands; B1 shape example no longer mentions Mistral/Mixtral; C1 shape example mentions Mistral/Mixtral

## Definition of Done

- [ ] U1 lands: B1 has 5 brands, mistral removed
- [ ] U2 lands: C1 has 5 brands, mistral added with `[Mistral, Mixtral]` tokens
- [ ] U3 lands: `tests/test_mistral_call_placement.py` ships green
- [ ] U4 lands: reference doc per-call tables and shape examples reflect the move
- [ ] Verification Contract gates all green
- [ ] One commit on `main` (or feature branch) with `Scope delivered vs plan promised: match` footer
- [ ] No out-of-scope files modified (verified via `git diff --stat` showing only `config.yaml`, `docs/reference/twitterapi-live-queries-by-model.md`, `tests/test_mistral_call_placement.py`)
