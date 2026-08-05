# How to add a tracked brand

### written by Grok 4.3

**Audience.** Operators and agents onboarding ~**1 brand per month**.  
**Related plan.** `docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md` (harvest policy 3/5).  
**4/5 later.** Auto C-packing, admin UI, auto-generated reference doc — not required for this checklist.

---

## Goal

A new brand is:

1. **Stored** (DB: brand, keywords, official handle) for attribution and UI  
2. **Searchable** (harvest policy: explicit search paths) so it is not “enabled but invisible to X search”  
3. **Verified** (`harvest_preview` + coverage invariant) before deploy  

Cadence assumption: ~1 brand/month. Bare + handle labs should take well under an hour after 3/5 ships. Polysemous names take longer only if they need a **co** path and a co-pack edit.

---

## Before you start

| Check | Why |
|---|---|
| Brand nickname (stable id, e.g. `foollm`) | Used in DB + policy + `enabled_models` |
| Display name + company | Dashboard / docs |
| Official X handle(s) | Handle path + attribution |
| Search tokens people actually type | Not only the legal name |
| Name ambiguity? | Stats term, common word, sports, crypto ticker → prefer **co** or **versioned** tokens |

**Failure mode to avoid (GLM-class):** brand in `enabled_models` and attributable in the feed, but **no keyword search path** (only rare `@official` mentions). Policy + coverage invariant exist to stop that.

---

## Checklist (after harvest policy 3/5 is live)

### 1. Database / product identity

- [ ] Create `Brand` row (`nickname`, display fields, accent if required)
- [ ] Add `BrandKeyword` rows used for **attribution** (matching post text → brand)
- [ ] Add official account + `brands_accounts` role `official` for each handle
- [ ] Add nickname to `enabled_models` in `config.yaml` **if** that list remains the enable gate (or rely on policy-only enable if the implementation unifies them — follow shipped code)

### 2. Harvest policy block (search)

Edit `config/harvest_policy.yaml` (path may match shipped layout from the plan). Add **one** brand block:

```yaml
foollm:
  paths:
    - bare          # or versioned_bare, and/or co, and/or handle
    - handle
  tokens:
    - FooLLM
    - Foo-3
  co: []            # fill only if "co" is in paths
  handles:
    - FooLLM_AI     # no @
  not_include: []   # brand-local bans for co path (e.g. Kimi F1 terms)
```

**Multi-path is allowed.** Handle-only or handle+keyword brands also declare `handle_tier: top-presence` (default; joins B2) or `handle_tier: other` (joins B3) to keep each handle spec under the 512-char X advanced-search cap. Examples:

| Intent | `paths` |
|---|---|
| Unique lab name + mentions | `[bare, handle]` |
| Versioned product ids (self-disambiguating) | `[versioned_bare, handle]` with tokens like `GLM-5.2` |
| Ambiguous short name | `[co, handle]` + shared min co terms |
| Keyword + co + mentions | `[versioned_bare, co, handle]` |
| Explicitly no X search (rare) | `paths: []` only with a written reason — coverage rules may require a `none` flag |

### 3. Co pack (3/5 only — if `co` ∈ paths)

3/5 uses **fixed co packs** (C1/C2/C3-style), not an auto-packer.

- [ ] Add `foollm` to the correct pack list next to policy (see plan / `co_packs` in config)
- [ ] If the pack’s rendered query would exceed **512** chars, open a new pack (future C4) or trim tokens — do not ship over cap
- [ ] Put brand-local `not_include` on the brand; expect those terms on the co call that contains this brand

**4/5 todo:** packer assigns C\* automatically; this step goes away.

### 4. Preview

```bash
# Shipped CLI (U4): offline preview + coverage invariant.
python manage.py harvest_preview
# CI mode: exit 1 if any enabled brand lacks a search path.
python manage.py harvest_preview --fail-on-invariant-violation

# Library entrypoint (no Django):
python -c "from x_monitor.harvest_preview import build_preview, render_preview; from pathlib import Path; r = build_preview(config_path=Path('config.yaml')); render_preview(r, open('/tmp/preview.md', 'w'))"
```

Confirm:

- [ ] Brand appears in **coverage map** with expected call ids (e.g. `foollm: [B1, B2]`)
- [ ] Every planned call length **&lt; 512** (note headroom)
- [ ] Query text includes the new tokens / `@handle` as intended

### 5. Tests / pins

- [ ] Coverage invariant still green (all enabled brands have a path)
- [ ] Optional thin pin: paths + key tokens for this brand (not a full 300-char query golden)

### 6. Docs

- [ ] Optional one-line note in `docs/reference/twitterapi-live-queries-by-model.md` brand table **or** rely on preview (3/5 does not require full reference regen)
- [ ] **4/5 todo:** reference file generated from preview in CI

### 7. Deploy

- [ ] Commit policy + DB migration/seed as needed
- [ ] Deploy so harvest cron loads new policy
- [ ] After one cycle: confirm new posts can attribute to the brand when matching content exists

---

## Decision tree: bare vs co vs versioned

```text
Is the main public name unique on X when alone?
  yes → paths: [bare, handle]  (or bare only if no official account yet)
  no  → Are there version/product strings that are unique?
          yes → paths: [versioned_bare, handle]  tokens: Foo-3, FooLLM-2, ...
          no  → paths: [co, handle]
                tokens: short name + disambiguators
                co: default min list (llm, model, api, agentic, huggingface)
                    + brand-specific if needed
                not_include: stable hijacks only
```

**Do not** put an ambiguous bare token on B1 without co or versioning.

---

## Worked examples

### A. Unique lab (typical monthly onboard)

```yaml
foollm:
  paths: [bare, handle]
  tokens: [FooLLM, Foo-3]
  co: []
  handles: [FooLLM_AI]
  not_include: []
```

No co-pack edit. Preview should show B1 + handle call.

### B. Polyseme + F1-style hijack (like Kimi)

```yaml
moonshot_kimi:
  paths: [co, handle]
  tokens: [Kimi, Moonshot AI, 月之暗面, MoonshotAI]
  co: [llm, model, api, agentic, huggingface]
  handles: [Kimi_Moonshot]
  not_include: [f1, antonelli, mercedes, hamil, alonso, verstappen, formula 1]
```

Co-pack membership required under 3/5. `not_include` is **brand-local** (not “whatever else shares C1 forever” as the mental model).

### C. Dual path (keyword + co + handle)

```yaml
glm:
  paths: [versioned_bare, co, handle]
  tokens: [ChatGLM, GLM-5, GLM-5.2, GLM-5.3, Zhipuai, 智谱]
  # prefer not listing bare "GLM" unless co path covers it separately
  co: [llm, model, api, agentic, huggingface]
  handles: [Zai_org]
  not_include: []
```

Use when versioned bare alone is not enough and short form still needs AI context.

---

## What you should not do

| Anti-pattern | Why |
|---|---|
| Enable brand only in `enabled_models` / DB | Search may never run (GLM-class gap) |
| Only add `@handle` to a B2 list by hand | Easy to desync; policy is the authoring surface after 3/5 |
| Copy full query strings into five test files | Prefer coverage + thin policy pins |
| Add ambiguous bare token to B1 | Noise; use co or versioned tokens |
| Skip preview | Length cap and coverage are easy to miss |

---

## After 4/5 (todo — not required now)

When 4/5 ships you will:

1. Still add **one policy block** (or use admin form)  
2. **Skip manual co_packs** — packer places the brand  
3. Use richer preview (headroom alerts, pack log)  
4. Regenerate the live-queries reference from preview in CI  

Until then, use this checklist and `harvest_preview` as the source of truth for live call strings.

---

## Related files (after 3/5)

| Path | Role |
|---|---|
| `config/harvest_policy.yaml` | Authoring: paths/tokens/co/handles/not_include |
| `config.yaml` | list id, enabled_models (if still separate), non-harvest settings |
| `x_monitor/harvest_policy.py` | load + `specs_from_policy` |
| `monitor/cycle.py` | `plan_calls_for_cycle` |
| `docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md` | Implementation plan |
| `docs/reference/twitterapi-live-queries-by-model.md` | Auto-generated via `scripts/build_reference_doc.py` (M11: current state only) |
| `scripts/build_harvest_policy.py` | Rebuild policy YAML from live config (offline; HANDLE_TO_BRAND table for B2/B3) |
| `scripts/build_reference_doc.py` | Regenerate the live-queries reference doc from current policy |
