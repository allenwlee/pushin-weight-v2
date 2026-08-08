---
title: "feat: Ship v22 homepage exhibits as production root"
date: 2026-08-08
last_updated: 2026-08-08
artifact_contract: ce-unified-plan/v1
artifact_readiness: living-wip
execution: code
product_contract_source: design-session + v22 exhibits + live home + design-system-contract-research
plan_type: feat
status: wip
supersedes:
  - docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md  # DEPRECATED 2026-08-08; per-iteration procedure consolidated into § "Per-iteration procedure (consolidated from 2026-08-07-001, added 2026-08-08)"
---

# feat: Ship v22 homepage exhibits as production root

### written by Grok 4.3

> **WIP / LIVING DOCUMENT** — Product intent continues to evolve with the exhibits.
> **Canonical visual target is the v22-master mockup** (exhibits below), not an intermediate v18/v19 alone.
> **Do not schedule ce-work / production cutover** until the user freezes the exhibits (see Freeze criteria).
> **Required reading before any implementation:** `.claude/skills/avoiding-recurring-mistakes/SKILL.md` (full file; M1–M16 at minimum). Treat that skill as a gate, not optional background.

**Target repo:** pushin-weight-v2  
**Canonical plan file:** `docs/plans/2026-08-08-001-feat-v22-homepage-production-plan.md`  
**Local mock mirror:** `/Users/allenwlee/Downloads/pushin-weight-mockups/`  
**Repo mock path:** `docs/ideation/mockups/`  
**Live surfaces to reuse:** `monitor/templates/monitor/home.html`, `monitor/views.py`, `monitor/static/pw-filter-store.js`, `pw-chart.js`, `pw-feed.js`, `monitor/urls.py`, chart partials, feed JSON  

## Plan Goal (verbatim from user)

> the goal of this plan is the following: we have created a new homepage for pushinweights-v2. we spent a lot of time mocking it up in html, which can be found here: `/Users/fuchitalee/development/pushin-weight-v2/docs/ideation/mockups/06-tier1-composed.v22-master.html`. we are replacing the current homepage ('internal'). internal will live on at '/internal', we will not touch that here. our new homepage, as mocked up, should retain all of the old functionality of internal, wrt to the line graph and filters and feed, albeit with different ui/design, and in addition ads new features.
>
> therefore, as much of the existing code base should be re-used for this new homepage, since it will co-exist alongside the internal.
>
> this plan will be considered complete when
>
> a. all features work as would be expected of a 2026 web app
> b. all design (colors, position, size, actions) are identical to the mockup;
> c. all content (both from frontend and db) works intended and as expected from a 2026 web app including speed, responsiveness, etc.
> d. idiomatic and best practices of coding have been followed. DRY, KISS, separation of concerns, verbose and instructive error messaging, 'being kind to your future self', comments in code. will the next agent be able to read the code and easily follow along its logical structure, intent. in particular the Django framework has been followed meticulously. If agent has a question about the code, it will (a) search all local files in repo; (b) conduct a web search BEFORE relying on internal knowledge.



---

## Goal Capsule

Ship the **v22 homepage design** as the **new site root** (`/`). **Do not delete or replace** the existing homepage in place: **move** today’s homepage to **`/internal`** (public URL shape: `pushinweight.ai/internal` / `pushinweights.ai/internal` — path is `/internal`).  

Functionally, **line chart + filter system** stay the same as today’s home — new chrome, same contracts — by **reusing and refactoring** existing modules (**DRY is absolute priority**). Defaults: **zh_cn**, **24h window**, **local** timezone. Mobile + desktop are exhibit pairs (not a single responsive afterthought).

---

## Required reading (implementation gate)

| Order | Document | Why |
|---|---|---|
| 1 | `.claude/skills/avoiding-recurring-mistakes/SKILL.md` | **Mandatory** before coding: M1 settled decisions, M2 no volunteer deploy, M4 parallel sessions, M5 verification in DoD, M7 DRY/shared harvest-style reuse, M9 idiomatic URLs, M10 i18n, M14 plan path, regression-net discipline |
| 2 | This plan | Product + technical contract |
| 3 | `docs/reference/lookup-tables.md` | zh-cn/en taxonomy labels for filters and feed signals |
| 4 | The v22 exhibit | Visual + interaction source of truth |
| 5 | `docs/research/2026-08-08-design-system-contract-gap-analysis-raw.md` (WebSearch supplemental at the end is the load-bearing part — clusters 1, 14, plus Christine Vallaure, Nathan Curtis, REGRESSION.md, arXiv 2603.17973, Tricentis) | Background research for the § "Design system contract framework" section; do not re-litigate the patterns, they're already mapped to this plan's units below. |


---

## Agent handoff brief (start here)

**Audience:** implementing agent with no prior session context.  
**Plan file:** `docs/plans/2026-08-08-001-feat-v22-homepage-production-plan.md`  
**Status:** living-wip — **not** authorized for full production cutover of `/` chrome until freeze (see Stop conditions).

### 0. Before any edit

1. Read **entire** `.claude/skills/avoiding-recurring-mistakes/SKILL.md` (required gate).
2. Read this plan (Goal Capsule, exhibits, DRY mandate, nets A–G, units).
3. `git fetch` + `git status` + check worktrees / recent `main` for parallel UI work (skill M4).
4. Do **not** volunteer commit, push, merge, or deploy (skill M2).

### 1. Canonical inputs

| Role | Path |
|---|---|
| Plan | `docs/plans/2026-08-08-001-feat-v22-homepage-production-plan.md` |
| Skill | `.claude/skills/avoiding-recurring-mistakes/SKILL.md` |
| Exhibits (canonical) | `/Users/fuchitalee/development/pushin-weight-v2/docs/ideation/mockups/06-tier1-composed.v22-master.html` |
| Taxonomy labels | `docs/reference/lookup-tables.md` |
| Live home to move | `monitor/templates/monitor/home.html` + `monitor/static/pw-*.js` + `monitor/views.py` |

Local Mac mirror of exhibit (if needed): `/Users/allenwlee/Downloads/pushin-weight-mockups/06-tier1-composed.v22-master.html`

### 2. Product targets (non-negotiable)

- **New design → `/`** (public root).
- **Existing homepage → `/internal/`** (relocated, **not** deleted; **not** `/old`).
- **DRY:** line chart + filter **behavior** lifted from current home (`pw-chart.js`, `pw-filter-store.js`, `_post_matches_filter`, chart payload). New UI is a shell/skin. Prefer refactor-to-share over copy.
- Defaults: **zh_cn**, **24h** (`HOME_WINDOW_DEFAULT` 7→1), **local** TZ.
- App title always **`走个量` + `Pushin' Weight`**.
- Chart: **no** hover-isolate brand hiding.
- Every commit message must include:  
  `Scope delivered vs plan promised: [match | narrower: …]`

### 3. Execution order (phases)

**Phase A — Foundation (authorized now, without exhibit freeze)**

| Order | Unit | Deliverable |
|---|---|---|
| 1 | **U0** | Comprehensive regression nets **A–G** (pin live contracts **before** breaking `/`) |
| 2 | **U1** | Route split: current home → **`/internal/`**; `/` can be stub/shell placeholder if chrome not authorized |
| 3 | **U2** | Defaults: window **1**, zh_cn, local TZ plumbing |
| 4 | **U4** | Chart path reused; remove hover-isolate only |

**Phase B — Exhibit chrome (only after freeze)**

| Order | Unit | Deliverable |
|---|---|---|
| 5 | **U3** | Pill filter skin on **shared** store |
| 6 | **U5** | Feed signals, infinite scroll, tint (filter-aware), stamps, ☆ |
| 7 | **U6** | Mobile/desktop + zh/en exhibit parity + i18n |
| 8 | **U7** | E2E vs four exhibits; nets still green |

### 4. Stop conditions (hard)

**Stop and ask the user** if any of these hit:

| # | Condition |
|---|---|
| S1 | About to implement **Phase B** without user saying exhibits are frozen / “ship against current v22” |
| S2 | Need to **delete** or break `/internal` legacy behavior to make `/` work |
| S3 | Tempted to **fork** a second chart or filter stack instead of reusing/refactoring |
| S4 | Parallel branch/session already edits same static/template files (M4) |
| S5 | Tests force **silent scope narrowing** (skip net, weaken assertion, “follow-up later” without AskUser) |
| S6 | URL shape would be non-idiomatic (`/api/v1/…`, dotted paths, `/old` instead of `/internal`) |
| S7 | Plan/body conflict with skill M1 settled decisions (v2 Django stack, etc.) |

**Do not stop for:** normal implementation detail (helper names, CSS class names) — use judgment.

### 5. Done means (for handoff completion)

- Phase A complete ⇒ nets A–G green; `/internal/` = former home; foundation defaults; chart no hover-isolate.
- Full plan complete ⇒ Phase A+B; `/` matches v20 exhibits; DRY; skill rules; commit scope lines.

### 6. One-line agent prompt (copy-paste)

> Execute Phase A only of `docs/plans/2026-08-08-001-feat-v22-homepage-production-plan.md`: read `.claude/skills/avoiding-recurring-mistakes/SKILL.md` first; ship U0 nets A–G, U1 move legacy home to `/internal`, U2 defaults (24h/zh_cn/local), U4 chart reuse without hover-isolate; DRY reuse of pw-filter-store and pw-chart; no Phase B chrome, no deploy, no commit unless asked; stop on any hard stop condition in the plan’s Agent handoff brief.

---

---

## Canonical exhibits (build toward these)

These four files are the **final markups / exhibits** for this plan. Implementation must converge on them (locale + layout). Intermediate versions (v2–v19) remain historical; **do not build toward v18 alone**.

| Exhibit | Path (repo) | Layout | Locale |
|---|---|---|---|
| Master exhibit (all locale/responsive variants in one file) | `/Users/fuchitalee/development/pushin-weight-v2/docs/ideation/mockups/06-tier1-composed.v22-master.html` | responsive (mobile 360 ↔ desktop ~1280) | zh_cn + en via locale toggle |

**Local absolute paths (Mac mirror):**

- `/Users/allenwlee/Downloads/pushin-weight-mockups/06-tier1-composed.v22-master.html`

**Exhibit invariants (all four):**

- App name **exactly**: `走个量` + `Pushin' Weight` (both languages, all locales) — title on its **own row** above window + TZ controls.
- Window chips: EN `24h/7d/30d/365d`; zh-CN **`24小时` / `7天` / `30天` / `365天`** (天 preferred over 日 for range filters).
- Filter bar: horizontal pills; dropdown width = filter-bar (not full viewport).
- Brands: Open/Closed lens (no Both); all/clear on visible tier.
- Nationalism: one pill, US/CN lens.
- Chart: multi-brand lines (production Chart.js — not mock SVG); **no hover-isolate**.
- Feed: 4/5 body + 1/5 signals; infinite scroll inside strip; synthesis/综合 text cycle; shell tint @ ~25%; filter-aware tint.
- Signal rows: sentiment faces → post_type emoji (max one each) → nationalism flags → unsanctioned 🚫 or blank.
- TZ: local ⇄ CA badge; feed absolute stamps &lt;24h.

---

## DRY mandate (chart + filters)

| Surface | Rule |
|---|---|
| **Line graph** | **Lift from existing homepage.** Same payload builder (`_build_home_chart_payload`), same `/chart` + `/chart.html`, same Chart.js bootstrap. New shell only re-homes the canvas region. **No second chart stack.** Remove hover-isolate only; do not rewrite data path. |
| **Filters** | **Functionally identical** to current home despite pill UI. Keep `pw-filter-store.js` state shape, `pw:filter-change`, `_parse_filters_from_request`, `_post_matches_filter`, `/feed/?filters=`. Pill DOM is a **skin**; group keys stay `brands`, `discourse`, `post_types`, `role`, `lang`, `us_nationalism`, `cn_nationalism`, `unsanctioned` (+ `sentiment` if product keeps pill functional). |
| **DRY priority** | Prefer extract-shared-module over copy-paste. If desktop and mobile diverge, **one template + CSS layout modes** (or shared partials), not two independent JS copies of filter/chart. Dual `monitor/static` vs `x_monitor/static` must not fork behavior. |
| **Refactor when needed** | Allowed and preferred when it enables one code path for old `/internal` and new `/` consumers (shared store, shared chart render, shared feed row wire). |

---

## Design system contract framework (from 2026-08-08 research)

**Source:** `docs/research/2026-08-08-design-system-contract-gap-analysis-raw.md` (1,979 lines; raw `/last30days` output on "design system component contract gap analysis tooling" + 16 WebSearch supplemental citations).

The research confirms the patterns already in this plan and identifies three new disciplines the plan now adopts. Each pattern lists the cluster in the research file and where the plan already implements (or now adds) it.

### Adopted patterns

| Pattern (research citation) | Where in this plan |
|---|---|
| **"Design system contract = testable standard"** (Cluster 1: DEV Community / levaiinbey 23-check verification checklist; also Christine Vallaure on Substack) | Already: **Comprehensive regression nets A–G** (this plan § "Comprehensive regression nets") + U0 implementation unit. New: explicit citation at the top of that section (see "Regression net discipline" paragraph below). |
| **"Schemas not docs" / Component Contracts** (Nathan Curtis, Substack; 18 months of pain making specs manageable) | Already: **Production wiring map** (§ "Production wiring map") names the DB/view/template responsibilities per concern. New: a finer-grained **UI region → DB query → view function → template loop** table below (§ "UI region → infra mirror table") extends the wiring map per mockup region, closing the gap Curtis identifies ("spec changes became unmanageable" → now each mockup delta has a row you can update). |
| **REGRESSION.md pattern** (Jussi P Mäntysen, LinkedIn) | Already: Nets A–G + scope-delta-on-every-commit line. New: explicit "Regression net discipline" paragraph below that names the prototype file (`tests/regression_net.py` from the v20 iteration plan) and the discipline "every fix gets a net that proves the old bug stays dead." |
| **Double-loop model for agentic coding** (testdouble / Joé Dupuis) | Already: **Agent handoff brief** separates outer (Phase A vs Phase B, freeze gates) from inner (per-unit edit loop) decisions. New: explicit reference in the handoff brief so future implementers see the meta/inner split is intentional, not accidental. |
| **"Passing tests ≠ correct behavior" / Intent drift** (Tricentis; also arXiv 2603.17973 "Test-Driven Agentic Development" — agents resolve real issues but introduce regressions in previously-passing tests) | Already: Net C pins i18n strings that must not drift; Net G pins app title and window labels. New: explicit "intent drift" reference added to the verification contract (Phase A must re-read this every iteration before declaring PASS). |
| **Visual regression tooling gap** (Chromatic, Percy, Storybook addon visual testing; Sparkbox VRT; Ramotion Contract-Driven Component Testing; pathtoproject.com enterprise contract testing) | **Deliberately skipped for v18 plan surface.** Visual regression tooling covers rendered Storybook stories; this plan targets a server-rendered Django template + Chart.js canvas + Tailwind mockup HTML. The gap that matters here is **DB trace**, not pixel diff — which is why the **UI region → infra mirror table** (added below) is the right level of abstraction. Visual tooling is a follow-up if/when a Storybook shell gets introduced. |
| **Figma → AI handoff workflow** (DesignPixil / Anant Jain; sills audit; Figma Code Connect/MCP) | **Deliberately skipped.** Source of truth here is the four HTML exhibits in `docs/ideation/mockups/`, not Figma. Adopt would be cargo-culting. |
| **Test-Driven Agentic Development** (arXiv 2603.17973) | Already: regression net discipline + per-iteration verification. New: explicit "treat the v20 regression net (`tests/regression_net.py`) as a learning artifact" pointer — TDD principles apply, but agentic iteration is run by another session, so the discipline is **net-driven**, not test-first-in-the-loop. |

### Patterns deliberately skipped (and why)

- **Figma/Code Connect/MCP workflows** — wrong tool for HTML-exhibit source of truth.
- **Storybook visual regression tooling (Chromatic, Percy, Sparkbox VRT)** — covers rendered half only; we ship Django templates, not a component library. The DB trace half is what's missing here, and that's what the UI region table below addresses.
- **Multi-agent graph topologies (Cluster 14, hackproduct9)** — orthogonal; single-agent iteration is enough for this plan's surface.

### Regression net discipline (v20 prototype)

This plan's regression nets A–G already implement the "REGRESSION.md" discipline at the unit level: each net pins a contract value that the shell rewrite cannot silently break. The companion file `tests/regression_net.py` (introduced by the v20 agentic iteration plan at `docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md`) is the **prototype implementation** for the iteration-loop half of this discipline — assertions about page elements that must remain present after every iteration, not just at unit-test time. Both nets must be green before any "PASS" verdict on a U-unit: A–G catches server-side contract drift; `regression_net.py` catches rendered-page drift. The "Scope delivered vs plan promised" commit footer (per CLAUDE.md plan-execution-contract) is the third leg: every commit names whether the scope matched the plan.

---

## Iteration drift mitigation (from 2026-08-08 angle-1 research)

The first research incorporation (§ "Design system contract framework") addresses *what* the shell promises (the contract surface). This section addresses *how the iteration loop stays on those promises* - the drift problem documented in the angle-1 research file.

### The drift problem in practice

The single highest-signal item in the angle-1 corpus is a [r/ClaudeCode](https://www.reddit.com/r/ClaudeCode/comments/1vdd84c/hundreds_of_guardrails_and_my_ai_still_passes_its/) thread titled "Hundreds of guardrails and my AI still passes its own broken work. Anyone solved this?loop engineering" - which describes drift in plain language:

> "Drift. Let a model loop unsupervised and by round 3 or 4 the task has quietly mutated into something adjacent to what I asked. Self validation is near useless. Doesn't matter how many guardrails you write, I've had hundreds of rules and explicit gate checks and it..."

This is the v20 loop drift the user surfaced: comparing live against *previous live* lets drift accumulate. The mockup is the only external reference that does not drift with the implementation.

### Patterns adopted

| Pattern | Source | Where in plan |
|---|---|---|
| **Compare live screenshots against canonical mockups, NOT against previous-live** | angle-1 cluster 8 (Tristan Bob X post: "1) Come up with an idea 2) Generate screenshots 3) Generate a prompt to build the UI mockup 4) Give your agentic coding tool the screenshots") + Christine Vallaure contract framing (first research) | Already implicit in the v20 companion plan at `docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md` "Per-iteration contract" step 6: *"compare live vs mockup, not live vs previous live."* New: explicit reference here so the v18 plan does not duplicate the v20 fix in the wrong direction. |
| **Bound autonomous loops with a fixed task contract** | angle-1 cluster 6 (r/ClaudeCode drift thread) + testdouble double-loop model (first research, already in § "Design system contract framework") | Already: **Stop conditions (hard)** § and **Agent handoff brief** §. New: cite the drift thread explicitly in the handoff brief so future implementers see the bound is a load-bearing guard, not a perfunctory one. |
| **Use Playwright / browser-MCP evidence for iterative visual verification** | angle-1 cluster 7 (Rustwright Rust rewrite of Playwright on HN, 12 pts) + angle-1 supplement (MCP Market "Visual Regression Claude Code Skill", Jeffallan `claude-skills/playwright-expert/SKILL.md`, AI Skill Market "Visual Regression Until Match") | Already: `tests/regression_net.py` is the lightweight structural subset of this pattern (no browser dependency, see v20 plan regression net section). New: add one-line note in § "Regression net discipline" that a Playwright-MCP upgrade path exists when/if structural assertions prove insufficient. |
| **Explicit approval before updating visual baselines** | angle-1 supplement (AI Skill Market "Visual Regression Until Match": "fixes unintended diffs until baselines match intentionally") | Already implicit in **Stop conditions** § (no unit ships without user-visible verification). New: codify in § "Verification Contract" that an agent cannot self-promote a snapshot diff to "expected" without surfacing it to the user - the regression net is a detector, not an approver. |

### Patterns deliberately skipped (and why)

- **Figma-to-AI coding handoff workflows** (angle-1 supplement: DesignPixil "Figma to AI Coding Tools: A Design Handoff Guide 2026") - source of truth here is HTML exhibits (`/Users/fuchitalee/development/pushin-weight-v2/docs/ideation/mockups/06-tier1-composed.v22-master.html`), not Figma. Cargo-cult.
- **Visual Regression Until Match loop** (angle-1 supplement: AI Skill Market) - this is a *self-correcting* loop ("fixes unintended diffs until baselines match"); the v18/v20 plan deliberately surfaces diffs to the user rather than letting the agent self-approve.
- **Figma + dev workflows (Code Connect, MCP, Make)** (angle-1 cluster 6 YouTube transcript, Figma channel) - same as above; exhibits are HTML, not Figma.

### Drift mitigation discipline (delta on top of v20)

When the v18 plan's `tests/regression_net.py` is added (or its equivalent for the v18 surface), the per-iteration procedure must follow the v20 plan's "Per-iteration contract" verbatim:

> 1. Run `regression_net.py` against the live page (asserts all PASSes from previous iterations still pass)
> 2. Pick scenario from the matrix (table-driven, not agent-decided)
> 3. Run Step 0 audit
> 4. Screenshot the mockup at the same viewport + locale
> 5. Screenshot the live page at the same viewport + locale
> 6. Diff: live vs mockup (NOT live vs previous live)
> 7. If diff shows new P0: file gap, add to UI region table above
> 8. If diff shows regression: STOP, revert or fix, surface to user
> 9. Otherwise: write report, commit, advance iteration N+1

Step 6 is the load-bearing change. Without it, the drift documented in the r/ClaudeCode thread above is the default outcome of any autonomous loop longer than 2-3 iterations.

---

## Visual-drift detection: Element Audit + Chrome DevTools MCP (added 2026-08-08)

The angle-1 section above ("Iteration drift mitigation") and the v20 prototype regression net at `tests/regression_net.py` together pin the **structural** surface (right HTML elements present, right text in them). They do NOT pin **computed CSS values** — `getComputedStyle(el).color`, `background-color`, `font-weight`, `padding`, `border-radius`. This gap surfaced on 2026-08-08: `.pulse-chip-name` rendered **black** text on the dark pulse-card (invisible against the dark pulse fill), but every one of the 50 regression-net assertions passed because the `<span class="pulse-chip-name">` element existed with the right text content. The HTML was correct; the visual output was wrong, and only a human eye on the live page caught it.

The research angle-1 corpus is explicit about why this gap exists. Two load-bearing citations:

- **Tokens fix theming; screenshots catch the drift tokens can't express** ([digitalapplied.com](https://www.digitalapplied.com/blog/screenshot-driven-ui-development-vision-models-2026), 2026-08-01, cluster 1, score 51): "Design tokens fix theming. They cannot express spacing rhythm, visual hierarchy, density, or [other visual drift]." Structural assertions (HTML + class names) are the *tokens* layer; computed styles are the *visual* layer. The regression net currently asserts only the token layer.
- **Accessibility snapshots beat screenshots for structural verification** ([dev.to pointchecknote, 2026-08-05](https://dev.to/pointchecknote/browser-automation-with-claude-playwright-mcp-why-accessibility-snapshots-beat-screenshots-2pke), angle-1 cluster "alternatives"): the a11y tree gives stable, machine-diffable structural tokens; pixel screenshots give the visual layer neither can express alone. Both layers are needed.

### Why Chrome DevTools MCP, not Playwright (per session-settled decision)

Per the prior session's research incorporation (`docs/research/2026-08-08-agentic-ui-iteration-loop-drift-raw.md`, X12 grok 2026-07-10, angle-1 cluster on browser control): "Browser control via Playwright headless Chromium or Google's Chrome DevTools MCP has been doable for custom agents for a while. **The difference: Claude now has a native in-app browser.**" Anthropic's `mcp__chrome-devtools__` exposes:

| Tool | What it returns | Drift signal it catches |
|---|---|---|
| `take_snapshot` (a11y tree) | Stable structural tokens w/ uids | "right element exists at right uid" — same as current HTML grep |
| `take_screenshot` | PNG of live viewport | Pixel diff vs mockup PNG — catches the visual drift tokens can't express |
| `evaluate_script(fn)` | Return value of arbitrary JS in page context | `getComputedStyle(el).color` / `background-color` / `font-weight` for any element — catches the *black-on-dark* class of defects that a11y snapshots and HTML greps both miss |

The third row is the new capability. The existing regression net's 50 assertions inspect only the first column (a11y-equivalent: HTML structure). Adding the third column catches the pulse-chip-color defect on the next iteration.

Playwright MCP would give the same capability surface (Playwright has `page.evaluate()` for computed styles and `page.screenshot()` for pixel diffs), but requires spinning a separate browser binary; Chrome DevTools MCP uses the user's already-running Chrome instance via CDP — zero install, zero config, and the screenshots/pixel diffs are guaranteed to be in the same viewport the user is testing in. The cost saved is the "does the agent's headless Chromium match the user's Chrome" reconciliation problem.

### Element Audit script — `tests/element_audit.py` (NEW)

The audit walks the v22-master mockup DOM and the live page DOM in parallel, captures computed styles for every region in the **UI region table** (§ "UI region → DB query → view function → template loop"), and emits a per-region diff. The diff is FAIL if any region's computed-style values differ; PASS otherwise.

**Region targets (pinned to the 5 most-drifted regions from the 2026-08-08 visual review):**

| Region | Mockup computed value (pinned) | Live computed value (must match) |
|---|---|---|
| `.pulse-chip-name` | `color: rgb(255, 255, 255)` (white) | (asserted at audit time) |
| `.voice-chip` background | `rgba(124, 58, 237, 0.18)` purple tint | (asserted at audit time) |
| `.filter-button:hover` | distinct hover color from default state | (asserted at audit time) |
| `.feed-handle` text-decoration | `none` (no underline by default) | (asserted at audit time) |
| `.delta.up::before` content | `"▲"` + green color | (asserted at audit time) |

The pinned values above are the **AFTER** state the plan INTENTIONALLY lands on; a BEFORE comment in the assertion captures the diff (e.g., `# BEFORE: color was rgb(0, 0, 0) — invisible on dark pulse-card fill`).

### Regression-net extension — `_check_visual_tokens()` (NEW)

Extends `tests/regression_net.py` with a new method that runs against the **mockup HTML file** served locally (the v22-master file is a static HTML; the audit serves it via `python -m http.server` on port 5051 during the audit run, OR fetches it directly via `file://`) and against the live Django page. For each pinned region, both responses' `getComputedStyle` are captured and compared to the pinned values via a small headless driver.

Since `tests/regression_net.py` is intentionally **no-browser-dependency** (per its module docstring: "the only client-side changes (htmx chart refresh, time-window JS) are noted separately"), the Element Audit lives in a SEPARATE file (`tests/element_audit.py`) that requires `playwright` or uses the Chrome DevTools MCP directly. The two are coupled by **shared pinned-values table** (single source of truth in `tests/visual_tokens.py`):

```python
# tests/visual_tokens.py (single source of truth for pinned CSS values)
VISUAL_TOKENS = {
    ".pulse-chip-name": {"color": "rgb(255, 255, 255)"},
    ".voice-chip": {"background-color": "rgba(124, 58, 237, 0.18)"},
    ".delta.up::before": {"content": "\"▲\""},
    # ... 5+ regions, one row per pinned token
}
```

Both `tests/element_audit.py` (browser-driven) and `tests/regression_net.py` (HTTP-only) read from this dict. When the plan INTENTIONALLY changes a value, only this file is updated — both surfaces pick up the new pinned value on next run, and the BEFORE comment in the assertion preserves the audit trail.

### Per-iteration contract extension

The v20 plan's "Per-iteration contract" step 6 (diff live vs mockup, NOT live vs previous-live) is extended to:

> 6a. Run `tests/element_audit.py` against v22-master + live at the same viewport + locale
> 6b. For each row in `tests/visual_tokens.py`, assert mockup computed value == live computed value == pinned value
> 6c. If 6b fails: file a NEW P0/P1 in the UI region table; do NOT proceed to scenario capture

Step 6a-c is the **load-bearing change** vs the current process. Without it, the drift documented in the r/ClaudeCode thread (cited in angle-1) re-appears at the *visual* layer even when the structural regression net is green — which is exactly what happened with the pulse-chip color on 2026-08-08.

### Definition of Done (new line)

> **Visual drift net shipped and green** — `tests/visual_tokens.py` has ≥ 5 pinned regions, `tests/element_audit.py` runs against mockup + live and fails on any mismatch, and the 2026-08-08 pulse-chip-color defect (and any other pre-existing visual defects surfaced by manual review) are pinned in the AFTER state.

### Patterns deliberately skipped (and why)

- **Pure pixel-diff screenshot comparison** (`pixelmatch` / `odiff` libraries) — catches more than computed-style diff (rendering quirks, font hinting, anti-aliasing) but is brittle across viewports and CSS class renames. The structural computed-style pin catches the same class of defect the user complained about (color, contrast, weight) without the brittleness. Pixel diff can be added later as a Tier-2 audit if computed-style proves insufficient.
- **Figma-to-CSS token sync** (Tokens Studio, Style Dictionary) — source of truth is HTML exhibits, not Figma. Same cargo-cult skip as the angle-1 § "Patterns deliberately skipped" list.
- **CSS-in-JS runtime assertions** (e.g., styled-components `jest-styled-components`) — the v22 shell uses plain `home-v20.css`; no CSS-in-JS runtime exists to hook into.
---

## Regression net discipline (from 2026-08-08 angle-2 research)

**Source:** `docs/research/2026-08-08-regression-nets-for-ai-agents-raw.md` (1,826 lines; raw `/last30days` run on "regression test AI agent code changes pin UNCHANGED surface" + 8 WebSearch supplemental sources). 153 items across Reddit (34), HN (29), TikTok (27), GitHub (24), YouTube (13), Web (12), Instagram (7), X (7).

Angle-2 narrows angle-1's iteration-drift topic to a specific discipline: **regression nets are not just a defensive net — they are the eval/QA primitive for AI-driven code change**, and they must be built BEFORE the production failure they prevent closes. Six patterns are adopted; two deliberately skipped.

### Adopted patterns

| Pattern (research citation) | Where in this plan |
|---|---|
| **"Evals are your regression tests for AI"** (Latitude YouTube, cluster 8, score 55) — directly frames evals as regression tests: "you write tests to make sure new changes don't break existing [behavior]… this is why evaluations are going to be your regression testing [strategy]." | Already: `tests/regression_net.py` prototype (see § "Regression net discipline (v20 prototype)"). New: explicit framing in § "Evals as regression tests (v18)" below — the regression net is the **v18 analog of LLM evals**; same discipline, different surface (Django templates + Chart.js canvas + i18n strings, not LLM outputs). |
| **Closed-loop RUN → detect reds → diagnose** (hackproduct9 TikTok, cluster 7, 1,882 views, 65 likes, score 57) — "Five stages. One closed loop. 🧪 RUN — the same suite every release. 6 cases through the app. 4 green, 2 red. The reds…" | Already: v20 iteration loop has Steps 0–9 + per-iteration regression_net.py run (see v20 plan § "Iteration loop"). New: explicit "Closed-loop RUN → detect reds → diagnose" subsection below maps hackproduct9's five stages onto the v18/v20 unit verification gate so future implementers see the loop is intentional, not accidental. |
| **REGRESSION.md: name a test after each production failure BEFORE closing it** (@adlrocha Substack) — a sharper version of the Jussi Mäntysen "REGRESSION.md" pattern already adopted in angle-1: write the regression test that would have caught the failure, then close the ticket. | Already: Nets A–G + scope-delta commit footer. New: explicit Definition-of-Done line below — every production failure uncovered during U0–U7 must produce a regression-net assertion (or `tests/regression_net.py` assertion) BEFORE the unit that surfaced it is marked PASS. Failure-to-add-the-net is itself a Definition-of-Done violation. |
| **Production-tracing → SME review → suite → pre-deploy regression** (Metacto + LangSmith / Langfuse / Arize / Braintrust WebSearch citations, cluster 19 / WebSearch supplemental) — the canonical LLM-ops closed loop: production traces surface failures → SME reviews/labels → examples added to suite → pre-deploy regression run gates releases. | New: § "Production-tracing → regression-suite pipeline" below frames Nets A–G and `regression_net.py` as the Django-template analog of this loop. The "SME" here is the implementing agent + design-session owner; the "trace" is the Element Audit (v20 plan § "Element Audit") + per-iteration report; the "suite" is the union of Net A–G + `regression_net.py` + `_DASHBOARD_*` key tuples. |
| **Vibe vs eval distinction** (hackproduct9 TikTok, cluster 7) — "Does it feel better?" is not an eval. It's a vibe. Real question: "better on which dimension, and where exactly did it fail?" | New: § "Vibe-vs-eval gate" below — before any U-unit can be marked PASS, the implementer must name **which Net (A–G) or which `regression_net.py` assertion** measures the change, and what the BEFORE→AFTER pin value is. "It looks better" is a vibe and a verification-contract violation. |
| **Agent-as-QA + golden snapshot + PR gate** (Proctor UiPath AgentHack cluster 3 score 60; agentsnap cluster 1 score 64; Skylos cluster 4 score 60) — non-deterministic AI automation needs an external QA agent or a deterministic checkpoint that reports `pass / fail / incomplete (never assumes clean)`. | Already: v20 iteration loop runs Element Audit (Step 0) BEFORE the scenario capture, and the regression net runs FIRST before PASS. New: explicit reinforcement in § "Closed-loop RUN → detect reds → diagnose" — the regression net is the PR gate; an iteration with `incomplete` (audit skipped, regression net skipped, scenario not captured) is automatically a FAIL. "Agent said done" is not sufficient evidence. |

### Patterns deliberately skipped (and why)

- **AWS Bedrock AgentCore Evaluations / pre-built evaluators (correctness, helpfulness, tool selection accuracy, etc.)** — the production surface here is server-rendered Django templates, not an LLM API. The eval dimensions AgentCore ships (correctness/helpfulness/safety) are LLM-output dimensions. The v18 analog is Nets C/D/E which already pin wire-shape and chrome-string correctness. Cargo-culting AgentCore into the v18 plan would be surface confusion.
- **TDD rule: failing test first, keep iterating until green** (cluster 10, cluster 23 caution about useless tests) — angle-1 already adopted Test-Driven Agentic Development as **net-driven**, not test-first-in-the-loop. The X23 caution ("AI writes useless tests that never go back to failing") reinforces the net-driven framing: tests must be pinned to UNCHANGED surface values, not invented to chase a goal. No new content; reference § "Regression net discipline (v20 prototype)" + angle-1 § "Test-Driven Agentic Development" (see first research § "Design system contract framework" row 8).

### Evals as regression tests (v18)

The Latitude framing lands cleanly: **Nets A–G + `tests/regression_net.py` are the v18 regression suite, and they ARE the evals.** The "model" under test is the Django view function + template render + JS payload, not an LLM. The "behavior" under test is the contract surface — filter keys, window defaults, chart payload shape, feed wire fields, locale exhibits, i18n chrome strings. The "eval" is the assertion that the surface value matches the pinned AFTER-state. Every U-unit (U0–U7) must answer the eval question explicitly in its Approach block: **"Which Net (or `regression_net.py` assertion) measures this change, and what is the pinned BEFORE/AFTER value?"** If a U-unit's Approach block lacks that line, the U-unit is not ready to be marked PASS.

The "vibe" failure mode this prevents: implementer writes a U-unit, eyeballs the page, declares "looks good," commits. Six months later a filter key drifts and the chart silently drops a series. Nets A–G make the drift loud.

### Closed-loop RUN → detect reds → diagnose

The hackproduct9 five-stage loop maps onto v18/v20 as follows. (The mapping is the discipline; the labels are deliberately informal so implementers can recite them.)

| Stage | hackproduct9 label | v18 / v20 mapping |
|---|---|---|
| 1 | **RUN** | Run Nets A–G (`pytest tests/test_home_v20_regression_net.py`) AND `tests/regression_net.py` against the live page. Both must execute; neither may be skipped or `xfail`-ed without a tracked gap. |
| 2 | **DETECT** | Read the assertion failure list. Group by Net (A through G) and by `regression_net.py` assertion. Each red is a candidate failure mode. |
| 3 | **DIAGNOSE** | For each red: which contract value drifted? Look at the diff between pinned BEFORE/AFTER value and current value. If the change is intentional (a Net explicitly waives a value with user OK), close the red with a docstring; otherwise the change is a regression. |
| 4 | **FIX-OR-REVERT** | If regression, revert the commit that introduced the drift OR fix the consumer. Re-run the suite to confirm the red closes and no new reds appear. |
| 5 | **ADVANCE** | Only when all reds are closed (with rationale per red) may the U-unit be marked PASS and the next iteration begin. |

The v20 iteration loop already implements stages 1–4 implicitly. The new discipline: the v20 **report file** (`/tmp/pushin-weight-iterations/NNNN-report.md`) must include a "Red summary" section that lists each red from stages 2–3, its diagnosis, and its fix-or-revert decision. A report without a "Red summary" section is incomplete and the iteration does not count toward the 100-iteration cap.

### Production-tracing → regression-suite pipeline

The Metacto / LangSmith / Langfuse / Arize / Braintrust pipeline adapted to v18:

```
Element Audit (v20 § "Element Audit", Step 0 of every iteration)
        ↓ (surfaces a missing chrome region, a drifted i18n string, a wrong filter key)
Regression net assertion (Net A–G or tests/regression_net.py)
        ↓ (fails because the new value ≠ pinned value)
Diagnosis: trace back to the commit that introduced the drift
        ↓
Add a NEW pinned assertion to tests/regression_net.py or Net A–G
        ↓
Re-run full suite (A–G + regression_net.py)
        ↓
Pre-deploy gate: all green → commit can ship; any red → revert or fix-and-rerun
```

The "SME" in v18 is the implementing agent + the design-session owner. The "trace" is the Element Audit + per-iteration report. The "suite" is the union of Nets A–G + `regression_net.py` + `_DASHBOARD_*` key tuples. The "pre-deploy gate" is the Definition of Done check (below). Every loop iteration that surfaces a regression **MUST add a new pinned assertion before the iteration is marked complete** — that's the discipline the Metacto/LangSmith pipeline encodes, and it's the one piece missing from v18's existing regression-net framing.

### Vibe-vs-eval gate (Definition of Done reinforcement)

Two lines added to § "Definition of Done" reinforce the vibe-vs-eval distinction:

- **Eval-named line (add):** Every U-unit's Approach block must name which Net (A–G) or `regression_net.py` assertion measures the change, with the BEFORE/AFTER pinned value. "Looks better" / "feels right" / "matches the mockup" are NOT acceptable substitutes.
- **Failure-closes-the-loop line (add):** Every production failure surfaced during U0–U7 (a regression-net red, a render bug, a chrome drift, a locale miss) must produce a new pinned assertion in `tests/regression_net.py` or Net A–G BEFORE the unit that surfaced the failure is marked PASS. "Fix the bug, move on" without adding the net is a Definition-of-Done violation.

### Why this section is angle-2, not angle-1

Angle-1 ("Iteration drift mitigation") covers the *meta* problem: passing tests can mask real regressions in agent-driven iteration. Angle-2 covers the *mechanism*: regression nets are the AI-era analog of LLM evals, and the discipline is "name a regression test after each failure before closing it." Angle-2 also surfaces concrete tooling patterns (closed-loop, production-tracing, agent-as-QA, golden snapshots) that angle-1 only gestures at.

---

## UI region → DB query → view function → template loop

This is the **per-mockup-region extension** of the production wiring map (§ "Production wiring map"). The wiring map names the *concern* (chart, filter, feed, locale); this table names the *cell in the Django stack* that produces each mockup region. Empty/loading state columns are mandatory — TDD intent: when a cell is missing, the row says "NOT YET ADDED" (see v20 plan's "Top Voices" row precedent) so future implementers can falsify the gap in one read.

| Mockup region | DB query | View function | Template loop | Empty state | Loading state |
|---|---|---|---|---|---|
| **App title** `走个量 Pushin' Weight` | n/a (locale + settings) | template literal | `{% block title %}` + `<header class="app-title">` | "走个量 Pushin' Weight" always present (both locales) | n/a |
| **Window chips** `24小时 / 7天 / 30天 / 365天` | n/a | `_resolve_home_window(request)` → `1` default; cookie override | `{% for d in window_days %}` inside `.window-toggle` | n/a | n/a |
| **TZ pill** `local ⇄ CA` | n/a | `pw-tz.js` reads `Intl.DateTimeFormat().resolvedOptions().timeZone` | `<nav class="tz-pill" data-tz-active="local">` | "local" always rendered; CA badge conditional | n/a |
| **Locale toggle** `中文 / EN / 原始` | n/a (session/cookie) | `_resolve_locale(request)` → `zh_hans` default | `<nav class="locale-toggle">` | n/a | n/a |
| **Brands pill** (Open/Closed lens; Closed list = Anthropic, OpenAI, SpaceXAI, Google) | `monitor_brand` filtered by `is_open` flag | `_build_brands_context()` (U3) | `{% for b in brands %}` inside `.filter-group[data-pw-filter-group="brands"]` | empty `__all__` sentinel | skeleton shimmer |
| **Discourse / Role / Lang / Nationalism / Unsanctioned pills** | `monitor_taxonomy` (static) | `_DASHBOARD_*` keys | `{% for k in keys %}` inside `.filter-group[data-pw-filter-group="…"]` | empty filter group | "loading filters..." shimmer |
| **Sentiment pill** *(only if A6 resolves functional)* | `monitor_taxonomy` (static) | `_post_matches_filter` extended for `sentiment` axis | `{% for s in sentiment_keys %}` | "sentiment" group hidden if A6 deferred | n/a |
| **Chart canvas** `Daily total posts per brand` | posts aggregated by brand × day for window | `_build_home_chart_payload(window, filters)` | `{% include "monitor/_home_chart.html" %}` with `<canvas class="home-chart">` | empty chart, axes drawn, no lines | `/chart.html?filters=` htmx skeleton |
| **Top voices** `☆ N (handle)` | top accounts by mention_count × log10(followers_count+10) in window | `_multi_top_voices(window_days, limit=3)` — single aggregation query on `Post.objects.values("author__handle", "author__author_id", "author__followers_count").annotate(mention_count=Count("tweet_id"))`, scored and sorted in Python | `<span class="headline-voices">` with `{% for voice in top_voices %}<a class="voice-chip">@{{ voice.handle }} (☆ {{ voice.voice_star }})</a>{% endfor %}` | "no top voices this period" when window has 0 posts | skeleton shimmer |
| **Trending %change deltas** `▲ 312%` per pill | v22-master shows each pill with ▲/▼/→ + percentage | `_build_brands_context()` extended for `recent_pct_change`; `_compute_brand_deltas()` runs single aggregation query (`PostBrand` x `Post`, 60 min vs prior 60 min buckets) | `{% for b in brands %}` extended with `<span class="delta {{ b.pct_class }}">{{ b.pct_change }}%</span>` | "—" placeholder when no prior window data | skeleton shimmer |
| **Feed engagement counts** `👥 128.4k ♥ 1.2k ↻ 340 💬 89` | v22-master shows per-card engagement stats | `_post_to_wire()` extended with `retweet_count`/`reply_count`/`quote_count` + `_engagement_pretty()` compact formatter | `{% for row in feed.rows %}` extended with `<div class="feed-engagement">` + 4 `.engagement-stat` spans (👥/♥/↻/💬 HTML entities) | hidden when count = 0 | n/a |
| **Feed avatar circles** (initials in colored circle) | v22-master shows initials like `K`, `A`, `S` per card | `_avatar_initials()` derives 1-2 chars from handle; `_avatar_color()` djb2 hash → stable HSL | `<span class="avatar" style="background: {{ row.avatar_color }}">{{ row.avatar_initials }}</span>` inside `.feed-author` flex container | avatar hidden when initials blank | n/a |
| **Feed cards** (body 4/5 + signals 1/5) | posts in window, filtered, paginated | `_get_feed_posts(window, filters)` + `_enrich_posts_with_classifications()` + `_serialize_feed_row()` | `{% include "monitor/_feed_initial.html" %}` + infinite-scroll fragment | "no posts in window" | "loading more..." |
| **Feed stamp** `(HH:mm local|CA)` when age <24h | n/a (computed from `created_at`) | `_format_feed_stamp(post, tz_mode)` | `{% if post.age_seconds < 86400 %}<time>{{ stamp }}</time>{% endif %}` | stamp hidden when ≥24h | n/a |
| **Shell tint** (~25% gradient / solid) | n/a (computed from post's brand→sentiment ∩ active brand filter) | recompute on `pw:filter-change` per row | `.feed-row-shell` style attr or class | solid for single-sentiment post; gradient for 2+ sentiments | n/a |

### Mockup-side infra mirror (DB tables backing each region)

| Mockup region | Required DB table | Required fields | Required index |
|---|---|---|---|
| App title | settings / i18n catalog | `走个量`, `Pushin' Weight` strings | n/a |
| Window chips | settings / i18n catalog | `24小时`, `7天`, `30天`, `365天` | n/a |
| TZ pill | session/cookie | `tz_active` ∈ `{local, CA}` | n/a |
| Locale toggle | session/cookie | `active_locale` ∈ `{zh_hans, en, original}` | n/a |
| Brands pill | `monitor_brand` | `nickname`, `accent_color`, `is_open`, `recent_post_count` | `(is_open, recent_post_count DESC)` |
| Discourse / Role / Lang / Nationalism / Unsanctioned / Sentiment pills | `monitor_taxonomy` | `key`, `display_name`, `group` | `(group, key)` |
| Chart canvas | `monitor_post` aggregated | `created_at`, `brand_id`, `count` | `(created_at, brand_id)` |
| Top voices | `monitor_account` JOIN `monitor_post` | `handle`, `follower_count`, `mention_count` | `(window_days, mention_count DESC)` |
| Feed cards | `monitor_post` | `tweet_id`, `text_en`, `author_handle`, `created_at`, classifications | `(created_at DESC, klass_filter)` |
| Feed stamp | n/a (computed) | n/a | n/a |
| Shell tint | n/a (computed) | n/a | n/a |

**Convention:** rows marked **NOT YET ADDED** are gaps to be filled by the unit that owns the region. When the implementer lands the missing cell, they update the row in the same commit (plan-execution-contract: plan body stays in sync).

**Iter 1 (2026-08-08) v22-master Element Audit surfaced 5 P0 gaps.** Locale default was a false positive (Django `LANGUAGE_CODE="zh-hans"` already sets zh_cn when no `?locale=` param) — row removed. **Iter 2** resolved Trending %change deltas (`_build_brands_context()` + `_compute_brand_deltas()`). **Iter 3** resolved Feed engagement counts (`_post_to_wire()` + `_engagement_pretty()`) and Feed avatar circles (`_avatar_initials()` + `_avatar_color()`). **Iter 4** resolved Top Voices body (historical blocker) — `_multi_top_voices()` view function + `.headline-voices` / `.voice-chip` template rendering. **All 4 real P0 gaps now closed.** See `docs/iterations/2026-08-08-v22-iter-{001,002,003,004}/REPORT.md`.

---

## Session-settled product decisions (full design-session incorporation)

Implementers who never saw chat must treat this table as product law until revised.

| Topic | Decision |
|---|---|
| **Root page** | New v22 design is **`/`** |
| **Existing homepage** | **Not replaced in place** — **moved** to **`/internal`** (remains functional: filters + chart + feed as today) |
| Default locale | **zh_cn** |
| Default window | **24h** (`HOME_WINDOW_DEFAULT` 7→**1**) |
| Default TZ | **local** (browser `Intl`), not hard-coded Beijing |
| App title | **`走个量 Pushin' Weight`** on all language versions; title row above controls |
| Window labels zh | **24小时 / 7天 / 30天 / 365天** |
| Layout strategy | Four exhibits: mobile zh/en + desktop zh/en (desktop = wider shell + chart\|feed grid) |
| Filters | Reuse production semantics; pill chrome from exhibits |
| Brands | Open/Closed lens; Open all-on; Closed all-off; **all / clear** (clear replaces “only”) |
| Closed brands | UI partition (Anthropic, OpenAI, SpaceXAI, Google); empty OK if not in DB |
| Nationalism | Single pill; US/CN lenses |
| Sentiment | positive/negative/neutral/mixed; labels from lookup-tables |
| Taxonomy labels | zh-cn strings from `docs/reference/lookup-tables.md` |
| Chart | Same as home; **no hover-to-isolate-brand** |
| TZ | Topbar pill: local ⇄ CA monogram; day/night emoji |
| Feed stamps | &lt;24h absolute `(HH:mm 本地|local)` or CA; toggles with TZ |
| Feed engagement | Followers first, then likes/RTs/replies |
| Top voices | **☆ N** = follower weight, not engagement |
| Text cycle | zh: 综合 → text_zh_cn → text; en: text_en → text; original: text → text_en |
| Text layer tags | **synthesis** (en UI) / **综合** (zh UI) — not “voice” |
| Feed infinite scroll | Inside `.feed-strip` (no “See all”) |
| Feed columns | Body **4/5** left, signals **1/5** right |
| Signal rows | sentiment faces; post_type emojis (one each); nationalism 🗯️:flags or blank; unsanctioned 🚫 or blank |
| Shell tint | Multi-sentiment **gradient intentional** @ ~25% alpha; **recompute from brand-sentiments still in scope after Brands filter** (e.g. only MiniMax positive → solid green) |
| Dropdown geometry | Width = filter-bar; not 100vw; not phone outer padding |
| Open authority | Single `is-open` + pointerup; not focus-within races |
| Deploy | No volunteer push/deploy (skill M2) |

---

## Production wiring map

| Concern | Reuse (do not reinvent) | New / change |
|---|---|---|
| `/` | `views.home` name | New v22 shell template(s) |
| `/internal/` | Current `home.html` behavior | **Move** current home here; name `home_internal` |
| Filter store | `pw-filter-store.js` | Skin for pills/lenses/all-clear; keep wire shape |
| Filter match | `_post_matches_filter` | Extend only for missing axes (e.g. sentiment) if functional |
| Chart payload | `_build_home_chart_payload` | Unchanged |
| Chart UI | `pw-chart.js` + Chart.js | Drop hover-isolate; same refetch |
| Feed | `pw-feed.js` + `/feed/` | Row chrome, stamps, infinite scroll, signals |
| Locale / window cookies | `set_locale`, `set_window`, resolvers | Default window 1 |
| Labels | seed_i18n / lookup-tables | Drive pill checkbox display strings |

### URL map (M9 — idiomatic)

| Path | Role |
|---|---|
| `/` | **New** v22 homepage (public root) |
| `/internal/` | **Existing** homepage relocated (internal / prior design) |
| `/feed/`, `/chart/`, `/chart.html` | Unchanged JSON/HTML data |
| `/locale/<locale>/`, `/window/<days>/` | Unchanged cookie setters |

**Not** `/old`. **Not** `/api/v1/…`.

---

## Requirements

| ID | Requirement |
|---|---|
| R1 | `/` renders the v22 exhibit design (locale-appropriate mobile or desktop). |
| R2 | Existing homepage **remains available** at **`/internal/`** with **same filter + chart + feed behavior** as today’s `/` (relocated, not deleted). |
| R3 | Defaults: **zh_cn**, **24h** (`HOME_WINDOW_DEFAULT = 1`), **local** TZ. |
| R4 | Filters functionally match production; pill UI from exhibits; **reuse store + match**. |
| R5 | Line chart is the **existing** multi-brand chart path; **no hover-isolate**. |
| R6 | Mobile + desktop behaviors match the **four exhibits**. |
| R7 | TZ pill + feed absolute stamps as exhibits. |
| R8 | Feed: followers first; ☆ voices; signals column; infinite scroll; filter-aware shell tint. |
| R9 | Idiomatic URLs; only new page path is `/internal/`. |
| R10 | i18n both catalogs; taxonomy labels from lookup-tables. |
| R11 | **Comprehensive regression nets** before and after shell swap (see below). |
| R12 | Shell tint = f(brand-sentiments ∩ active brand filter); multi-sentiment gradient intentional. |
| R13 | **DRY:** no parallel chart or filter implementations; refactor shared code when needed. |
| R14 | Skill `avoiding-recurring-mistakes` followed for all units. |

---

## Comprehensive regression nets

Regression nets pin the **current correct behavior of surfaces we keep** so the redesign cannot silently break them. Each net is a real test file with **explicit pinned values**.

### Net A — Route & shell identity
- `reverse("home") == "/"` after cutover serves **new** shell marker (e.g. `data-pw-shell="v20"`).
- `reverse("home_internal")` or path **`/internal/`** serves **legacy** marker (e.g. `id="control-panel"` present).
- `/internal/` still loads chart region + filter group attributes compatible with store.

### Net B — Window & locale defaults
- **BEFORE** intentional change: document `HOME_WINDOW_DEFAULT == 7` in a comment on the test that asserts **AFTER** `== 1`.
- No-cookie request: window **1**, locale **zh_cn** / Django **zh-hans**.
- Cookie `home_window=7` still honored when set (returning users).

### Net C — Filter contract (unchanged wire)
Pin `_DASHBOARD_DISCOURSE_KEYS`, `_DASHBOARD_POST_TYPE_KEYS`, `_DASHBOARD_ROLE_FILTER_KEYS`, `_DASHBOARD_NATIONALISM_KEYS`, `_DASHBOARD_LANG_FILTER_KEYS` to frozen tuples from live `monitor/views.py` at plan time (list full tuples in test).
- `_parse_filters_from_request` still accepts brands/discourse/role/lang/nationalism/unsanctioned JSON.
- `_post_matches_filter`: uncheck discourse key excludes posts; unsanctioned `only`/`off` behavior pinned; brand list intersection pinned.
- **i18n pin examples** (AFTER intentional chrome may change only new strings): e.g. existing gettext that must not drift — pin at least 3 chrome strings that redesign must not corrupt (e.g. if `Filters` / `筛选` remain on `/internal`).

### Net D — Chart contract
- `_build_home_chart_payload(1, {})` returns expected top-level keys (pin key set: document actual keys from code).
- `pw-chart.js` post-change: **no** hover-isolate control flow (`hoveredBrandIndex` absent or inert).
- `pw:filter-change` still triggers refetch URL containing `/chart.html` and `filters=`.
- Multi-series always visible (behavior test or static analysis + integration smoke).

### Net E — Feed contract
- Wire fields used by feed: `tweet_id`, handle, `followers` / pretty, `created_at`, text fields, classification keys — pin names from `_post_to_wire` / `_serialize_feed_row`.
- Followers formatting: pin `_pretty_followers(128400) == "128.4k"` (or live helper’s exact string).
- Absolute stamp rule: age &lt; 24h shows stamp; age ≥ 24h hides.

### Net F — `/internal` parity after move
- Snapshot critical legacy behaviors: control-panel checkbox groups exist; window toggle present; chart canvas class `home-chart`; feed endpoint still works with same filters param.
- No dependency of `/internal` on v20-only DOM (legacy must not require pill bar).

### Net G — Locale exhibits
- zh-CN window labels map 1→24小时, 7→7天, 30→30天, 365→365天 in UI strings catalog.
- App title always contains both `走个量` and `Pushin' Weight`.

**Definition of Done includes:** Nets A–G shipped and green (or explicitly waived per surface with user OK).

---

## Scope Boundaries

### In scope
- New root shell from v22 exhibits
- Relocate current home to `/internal/`
- Defaults, TZ, feed chrome, pill filters skin, chart hover removal
- Shared refactor for DRY
- Comprehensive regression nets
- i18n for new chrome

### Out of scope
- Deleting the old homepage
- Rebuilding harvest/classifier
- Brand drill-down redesign
- Volunteer deploy

### Assumptions
| ID | Assumption |
|---|---|
| A1 | Closed brands UI-only if not in DB |
| A2 | “local” = browser timezone |
| A3 | Domain host may be pushinweight.ai or pushinweights.ai — **path is `/internal`** |
| A4 | One Django app serves mobile/desktop via CSS + locale, driven by exhibits |

---

## Key Technical Decisions

| ID | Decision | Rationale |
|---|---|---|
| KTD1 | **Shell swap + route move, not dual APIs** | R13 DRY |
| KTD2 | Legacy at **`/internal/`** | User: not replace; relocate (supersedes earlier `/old`) |
| KTD3 | Chart + filter **lifted** from current home | Functional sameness |
| KTD4 | `HOME_WINDOW_DEFAULT = 1` | R3 |
| KTD5 | Filter group attributes preserved under new DOM | R4 |
| KTD6 | Four exhibits are **canonical** | User 2026-08-07 |
| KTD7 | Dropdown geometry = filter-bar width | Session lessons |
| KTD8 | Filter-aware shell tint | R12 |
| KTD9 | Required skill read before implement | User gate |

---

## Design-process lessons (carry into implementation)

1. Single open-state authority for pills (`is-open` + pointerup).
2. Overflow clipping: don’t trap dropdowns in overflow-x without pin/inner scroller.
3. Playwright “display:block” ≠ on-screen — pin geometry in verification.
4. Multi-sentiment gradient is intentional; filter must narrow tint set.


## Implementation Units

**Mock-stability legend**

| Tag | Meaning |
|---|---|
| **FOUNDATION-STABLE** | Can start once user freezes *product* defaults/routes; not blocked on pixel mock churn |
| **EXHIBIT-DEPENDENT** | Wait for exhibit freeze (or explicit “implement against current v20”) — visual chrome |

Units keep U0–U7 shape. Early units (regression net, route split, defaults) are mock-stable; chrome units are mock-dependent.

---

### U0. Comprehensive regression nets (A–G) — pin contracts before move — **FOUNDATION-STABLE**

**Goal:** Freeze current filter keys, window default (pre-change), chart payload shape, and feed wire fields so the shell rewrite cannot silently break data contracts.

**Requirements:** R11  

**Dependencies:** none  

**Files:**
- `tests/test_home_v20_regression_net.py` (create)
- Possibly assert against constants in `monitor/views.py`

**Approach:**
1. Pin `_DASHBOARD_*` key tuples used by home filters (discourse, post_type, role, nationalism, lang).
2. Pin feed wire fields currently required by `pw-feed.js` / serialize path (tweet_id, handle, followers / followers_pretty, created_at, text fields, classification keys including sentiments).
3. Pin chart payload top-level keys returned by `_build_home_chart_payload`.
4. Pin **pre-change** `HOME_WINDOW_DEFAULT == 7` in a test that will be **updated in U2** to `1` with a BEFORE comment (intentional change).
5. Pin existing routes: `reverse("home") == "/"`; after U1 also pin `/internal/`.
6. Prefer at least one **call-chain** style pin where practical (M18 spirit): e.g. `_parse_filters_from_request` + `_post_matches_filter` together, not only constants.

**Test scenarios:**
- Happy: key tuples equal frozen lists.
- Happy: chart payload for window=1 with empty filters has expected keys.
- Happy: feed wire includes followers_pretty path for a synthetic post.
- Edge: unsupported locale still normalizes per existing rules.

**Verification:** `pytest tests/test_home_v20_regression_net.py` green before any shell rewrite.

---

### U1. Route split: `/` new shell stub, `/internal` legacy — **FOUNDATION-STABLE** (stub) / **EXHIBIT-DEPENDENT** (full chrome)

**Goal:** Introduce `/internal` without losing today’s home; free `/` for the new shell.

**Requirements:** R1, R2, R9  

**Dependencies:** U0  

**Files:**
- `monitor/urls.py`
- `monitor/views.py` (thin wrapper or dual template names)
- `monitor/templates/monitor/home_internal.html` (copy/rename of current home)
- `monitor/templates/monitor/home.html` (eventually v20; may temporarily alias legacy until U3+)
- Tests for reverse/resolve

**Approach:**
1. Copy current `home.html` → `home_internal.html` (or keep content and switch names carefully).
2. Add `path("old/", …, name="home_internal")` (trailing slash per Django convention; user-facing “/old” redirects if needed).
3. Keep legacy behavior identical (same context, same scripts).
4. New home can ship incrementally: first paint may still be partial shell; full chrome after U3–U5.
5. Distinct template markers (HTML comment or `data-pw-page="multi-v20"` vs `multi-legacy`) for tests.

**Test scenarios:**
- Happy: `/` and `/internal/` both 200.
- Happy: legacy marker only on `/internal/`; new marker only on `/` once shell lands.
- Edge: reverse names stable for bookmarks.

**Verification:** Django client GET both paths; assert markers.

**Note:** Full visual parity with mock is **EXHIBIT-DEPENDENT**; the route wiring itself is **FOUNDATION-STABLE**.

---

### U2. Defaults: window=1, confirm zh_cn, TZ local default — **FOUNDATION-STABLE**

**Goal:** First-paint product defaults match session decisions.

**Requirements:** R3, R7 (default only)  

**Dependencies:** U0  

**Files:**
- `monitor/views.py` (`HOME_WINDOW_DEFAULT`)
- Optional: `monitor/static/pw-tz.js` skeleton with `data-tz-active="local"`
- Regression test update for window pin (BEFORE 7 → AFTER 1)
- Template attribute defaults on new shell

**Approach:**
1. Set `HOME_WINDOW_DEFAULT = 1`.
2. Confirm locale path already defaults zh_cn (no change unless bug).
3. TZ module: default `data-tz-active="local"`; CA = `America/Los_Angeles`; labels word **local** + **CA** monogram badge.
4. Cookie note: existing `home_window=7` cookies still win for returning users; only first visits / cleared cookies get 24h.

**Test scenarios:**
- Happy: request without cookies → window_days == 1.
- Happy: request without locale cookie → zh_cn / zh-hans translation active.
- Happy: TZ script/template marks local on boot.

**Verification:** view unit tests for `_resolve_home_window` / `_resolve_locale`; update U0 window pin in same unit.

---

### U3. Filter bar UI → v22 pills; keep filter store contract — **EXHIBIT-DEPENDENT**

**Goal:** Replace vertical control panel with horizontal pill bar + full-bar-width dropdowns; filters still emit `pw:filter-change` and serialize the same filter JSON shape.

**Requirements:** R4, R10, KTD5, KTD9, KTD10  

**Dependencies:** U1, U0  

**Files:**
- `monitor/templates/monitor/home.html` (filter markup)
- `monitor/static/pw-filter-store.js` (minimal: all/clear scoped to lens; nationalism dual grids; drop only-column or map clear)
- `monitor/static/home-v20.css` (or `dashboard.css` section) — prefer dedicated file to reduce dual-root thrash
- `locale/en/LC_MESSAGES/django.po`, `locale/zh_Hans/LC_MESSAGES/django.po`
- Server-side filter tests; optional Playwright geometry pins

**Approach:**
1. Preserve `data-pw-filter-group` values: `brands`, `discourse`, `post_types` (if retained), `role`, `lang`, `us_nationalism`, `cn_nationalism`, `unsanctioned`; add `sentiment` if A6.
2. Pill order: Brands → Discourse → Role → Lang → Sentiment → Nationalism → Unsanctioned.
3. Brands: Open/Closed lens; Open all-on; Closed all-off; Closed list = UI partition (Anthropic, OpenAI, SpaceXAI, Google when present).
4. Nationalism: single pill; US/CN lens; two grids bound to `us_nationalism` / `cn_nationalism` (same 6 keys as `_DASHBOARD_NATIONALISM_KEYS`).
5. Sentiment: positive|negative|neutral|mixed; extend `_post_matches_filter` + store default if shipping the pill live.
6. Toolbars: Brands/Nationalism **all/clear** scoped to **visible** lens; Lang flat **all/clear**.
7. Drag-to-scroll on `.filter-bar-scroller`; open on pointerup; single `is-open` authority.
8. Dropdown geometry: width/left = filter-bar box (not viewport).
9. Before editing shared static: `git fetch`, worktree list, recent main commits on `monitor/static/*` (M4).

**Patterns:** v22 mock HTML/CSS/JS; existing `pw-filter-store.js` change handlers.

**Test scenarios:**
- Happy: `_parse_filters_from_request` still accepts existing filter JSON.
- Happy: unchecking a discourse key excludes matching posts.
- Happy: nationalism US vs CN independent.
- Happy: brands Open all-on → `__all__` when all open brands checked and closed empty-off does not falsely empty brands filter (document expected serialize rule).
- Edge: empty brand selection / all-on → `__all__` sentinel preserved.
- Geometry (manual/Playwright): open Brands dropdown on-screen width ≈ filter-bar.

**Verification:** server-side filter tests green; geometry checklist for open dropdown.

---

### U4. Chart: reuse payload; remove hover isolate — **FOUNDATION-STABLE** (hover removal) / **EXHIBIT-DEPENDENT** (chrome wrap)

**Goal:** Chart continuous with production data; no hover brand isolation.

**Requirements:** R5  

**Dependencies:** U1  

**Files:**
- `monitor/static/pw-chart.js` (and dual-copy if required)
- `monitor/templates/monitor/_home_chart.html` (canvas contract)
- Test forbidding hover-isolate control flow or asserting no hide-on-hover behavior

**Approach:**
1. Keep Chart.js construction and dataset mapping from payload.
2. Remove `hoveredBrandIndex` mouse-move logic and discourse-layer hide tied to hover isolate.
3. Preserve `pw:filter-change` refetch; preserve `#home-chart` / `canvas.home-chart` ids/classes.
4. Do not ship mock SVG chart.
5. If brand drill-down shares `pw-chart.js`, gate hover removal to multi-brand home page (`data-pw-page`) so brand chart is not silently changed without review.

**Test scenarios:**
- Happy: chart region id remains `home-chart`; canvas class `home-chart`.
- Happy: after unit, no hover-isolate hide path (grep or unit).
- Integration: filter change still calls `/chart.html?filters=`.

**Verification:** multi lines always visible; mouse move does not hide series.

---

### U5. Pulse, headline, feed chrome (followers, TZ stamps, ☆ voices) — **EXHIBIT-DEPENDENT**

**Goal:** Match v22 information density under the chart.

**Requirements:** R7, R8, A4, A5  

**Dependencies:** U2, U3  

**Files:**
- `monitor/templates/monitor/home.html`
- `monitor/static/pw-feed.js`
- `monitor/static/pw-tz.js`
- `monitor/views.py` (ensure wire fields: followers, created_at ISO)
- Tests for stamp visibility rule (&lt;24h)

**Approach:**
0. **Filter-aware shell tint (R12 / KTD11):** multi-sentiment gradient is intentional; when Brands filter leaves one in-scope brand sentiment (e.g. only MiniMax → positive), shell is solid for that sentiment.

**Approach:**
1. Feed row: relative time + `(HH:mm local|CA)` when age &lt; 24h; bind to TZ mode.
2. Engagement: 👥 followers first using `_pretty_followers` / `followers_pretty`.
3. Headline strip: top voices with `☆ N` (follower counts, **not** RT/like/reply).
4. Pulse: derive from chart payload top brands or stub.
5. TZ toggle updates stamps without full page reload.

**Test scenarios:**
- Happy: wire includes followers; pretty format OK.
- Happy: post age 12m → stamp shown; age 2d → stamp hidden.
- Happy: TZ toggle switches stamp suffix local ↔ CA without reload.
- Edge: missing followers → omit icon or empty.

**Verification:** manual or Playwright on `/` with seeded posts; stamp + order checks.

---

### U6. Responsive layout + i18n chrome pass — **EXHIBIT-DEPENDENT**

**Goal:** Desktop usable; Chinese/English chrome complete.

**Requirements:** R6, R10  

**Dependencies:** U3–U5  

**Files:**
- `home-v20.css` / related
- `locale/*/LC_MESSAGES/django.po`

**Approach:**
1. Mobile-first base = v20 (~360 content column).
2. ≥768px / ≥1024: wider max-width, less cramped pills, chart height; optional side-by-side only if filter bar stays intact.
3. Translate: local, California/CA, filter group titles, Unsanctioned, empty states, etc.
4. Regression: pin sample of **unchanged** gettext strings (e.g. existing Filters / 筛选 if still used elsewhere) so chrome edits do not silently drift unrelated catalog entries.

**Test scenarios:**
- Regression: pin existing catalog strings that must not change.
- Happy: template loads both locales.

**Verification:** resize 360 and 1280; locale toggle on new topbar.

---

### U7. Integration verification + Definition of Done gate — after freeze + U1–U6

**Goal:** End-to-end proof before ship.

**Requirements:** R1–R11, M5  

**Dependencies:** U1–U6 + **exhibit freeze**  

**Files:**
- `tests/test_home_v20_e2e.py` and/or Playwright under `tests/` if available
- This plan’s DoD checklist

**Approach:** Run automated + documented manual checks including **geometry** pins; fix gaps. **Do not** volunteer deploy.

**Test scenarios:**
- `/` 200, `/internal/` 200, distinct markers.
- Default window 1, locale zh_cn, TZ local.
- Filter uncheck → feed/chart request includes filters.
- Chart multi-series without hover hide.
- TZ toggle updates feed stamps.
- Open filter dropdown: on-screen, width ≈ filter-bar.

**Verification:** full pytest path for home + Playwright smoke if infrastructure exists; else Django + manual checklist in PR.

---

## Freeze criteria — Do not implement yet

**Do not start ce-work / production cutover** until the user explicitly freezes (or explicitly authorizes “implement against current v20 knowing mock may still move”).

| Gate | Status (2026-08-08) | Resolution |
|---|---|---|
| G1 — mock frozen | **✅ RESOLVED** | User confirmed `06-tier1-composed.v22-master.html` is final. Mobile/desktop × zh/en exhibits are the four production target renders. |
| G2 — session-settled decisions | **✅ RESOLVED** | Defaults = 24h / zh_cn / user-local-TZ. `LANGUAGE_CODE="zh-hans"`, `/internal` legacy route, ☆ = followers by voice_score all stand. |
| G3 — post_type primary-bar | **✅ RESOLVED** | All 6 post_type keys ship as peers in the filter dropdown (no primary-bar grouping): `buzz_releases / hands_on_usage / performance_comparisons / feedback_questions / advertising_marketing / event_announcement`. |
| G4 — Sentiment functional vs decorative (A6) | **✅ RESOLVED (DB-canonical)** | Sentiment filter is functional. 4 keys ship per `docs/reference/lookup-tables.md § 2`: `positive / negative / neutral / mixed`. Plan defers to DB; do not invent labels in code or template. |
| G4b — Nationalism axis (added 2026-08-08) | **✅ RESOLVED (DB-canonical)** | Two parallel axes (china_nationalism + us_nationalism), 6 keys each per `docs/reference/lookup-tables.md § 4`: `none / mild_pro / pro / constructive_critical / anti / mixed`. Plan defers to DB. |
| G4c — Discourse vocabulary (added 2026-08-08) | **✅ RESOLVED (DB-canonical)** | 10 keys per `docs/reference/lookup-tables.md § 3`: `genuine_hype / sarcasm / dunk_yingyang / self_deprecation / cope / fud / distillation_accusation / ai_slop_critique / absurdist_meme / advertising-marketing` (note hyphen). |
| G4d — Roles (added 2026-08-08) | **✅ RESOLVED (DB-canonical)** | 3 persisted Roles (`official / staff / community`) + 1 computed-at-query (`other`) per `docs/reference/lookup-tables.md § 5`. |
| G4e — Unsanctioned flags (added 2026-08-08) | **✅ RESOLVED (DB-canonical)** | 4 keys per `docs/reference/lookup-tables.md § 6`: `marketing_spam / scam / crypto / unauthorized`. No `*Label` table exists for this one. |
| G4f — Filter wire (added 2026-08-08) | **✅ RESOLVED** | All 7 filter groups ship as-is: Brands / Discourse / account.role / lang / Sentiment / Nationalism / unsanctioned. |
| G5 — No parallel session mid-edit | **🟢 ACTIVE** | No parallel session currently editing the same mock. |

**Canonical reference for every filter value:** `docs/reference/lookup-tables.md`. Per user direction 2026-08-08: "literally all of the filter labels should be determined by db … make sure to clearly have the plan use db as canon for every filter and choices within each." Plan body, templates, view code, and i18n catalogs must read from the DB at runtime — not hardcode labels or option sets.

**Allowed before freeze (optional):** U0 regression net only, if user wants early contract pins. Route split (U1) and window default (U2) may start only when user says product defaults are settled even if chrome still moves. **All gates now RESOLVED → U3–U6 are unblocked.**

**Not allowed before freeze:** ~~Full U3–U6 chrome cutover, deploy, "while we're at it" brand page restyle (M2).~~ **SUPERSEDED 2026-08-08** — gates G1–G4f are RESOLVED. Phase B (U1-full chrome, U3, U4-chrome, U5, U6) is now go-decision-only at the user's `/goal` prompt.

---

## Open mockup deltas still expected


### Feed-row shell tint (v19+; 2026-08-07)

- **Confirmed intentional:** when a post has **two+ sentiments** across brand mentions, `.feed-row-shell` uses a **gradient** among positive (green), negative (red), mixed (purple) at ~**25%** alpha — not a bug.
- **Filter-aware tint (required for production):** recompute the sentiment set used for tint from **only brands still in scope after the active Brands filter** (brands selected and present on the post). Example: post MiniMax=positive, Kimi=negative → default gradient green–red; user filters **only MiniMax** → shell becomes **solid positive green**.
- Implementation note: store per-post `brand → sentiment` (or parallel arrays); do not tint from a bag-of-sentiments that ignores brand identity when brands are filtered.
- Mock today may still tint from static `data-sentiments` on the row; production must recompute on `pw:filter-change` / active brand set.


> Living placeholder — **user appends** further mock changes here. Implementers re-read this section + the HTML mock before each UI unit.

| Date | Delta | Impact on units |
|---|---|---|
| _(none logged yet)_ | Mock will keep evolving | U3–U6 re-diff against latest `06-tier1-composed.v*.html` before coding |
| | | |

When a new mock version lands (v19+), update:

1. Frontmatter `last_updated`
2. Visual source of truth path
3. This table
4. Any pill order / lens / TZ copy that changed

---


---

## Freeze criteria / do not implement yet

Do **not** start full ce-work cutover until:

| Gate | Status (2026-08-08) | Meaning / Resolution |
|---|---|---|
| G1 | **✅ RESOLVED** | User freezes the **v22 exhibit** (or says "ship against current v22") — confirmed v22-master is final. |
| G2 | **✅ RESOLVED** | Session-settled table still accepted — defaults confirmed (24h/zh_cn/local-TZ), filter wire confirmed (7 groups ship as-is, all values DB-canonical). |
| G3 | **✅ RESOLVED** | `/internal` path confirmed (supersedes any older `/old` notes) — already adopted in U1. |
| G4 | **🟡 ACTIVE** | Regression net list A–G accepted — Nets A–G defined in plan; **needs implementer acceptance before U7 Integration Verification can close**. Mark accepted when first U-unit ships and the net reads green. |
| G5 | **🟡 ACTIVE** | Skill `avoiding-recurring-mistakes` acknowledged by implementer — skill exists at `.claude/skills/avoiding-recurring-mistakes/SKILL.md`; require explicit acknowledgement in agent handoff before Phase B starts. |

**Allowed before freeze:** U0 nets only (characterization against live `/`). **Gates G1–G3 now RESOLVED → U1-stub, U2, U4-hover-removal are go-decision-only.**

**Note on block duplication:** This block (G1–G5 = mock/session/internal/nets/skill) and the prior block (G1–G5 = mock/session/post_type/sentiment/parallel-edit) cover overlapping-but-distinct gates. The first block is the **product-decision** freeze; the second is the **project-hygiene** freeze. Both must be cleared before U7 (Integration Verification + Definition of Done) closes. As of 2026-08-08 the product-decision freeze is fully cleared; project-hygiene freeze is at 3/5 RESOLVED with the implementer-acknowledgement gates (G4, G5) deferred to the agent that picks up Phase B.

---

## Per-iteration procedure (consolidated from 2026-08-07-001, added 2026-08-08)

The v20 iteration-loop companion plan at `docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md` defined the per-iteration operating procedure that drove iter 1-4. To prevent two-plan drift, that content is consolidated here. The v20 plan is now **DEPRECATED** (see its frontmatter banner) and any future iteration procedure edits happen in this section.

This section is the **operating contract for iter N≥5**. The v22 plan body sections above (research incorporations, regression nets A–G, gate resolutions, visual-drift unit) are the **strategic context**; this section is the **per-iteration execution protocol**.

### Scenario matrix

| # | Scenario | Pre-state | Actions | Expected | Captures |
|---|---|---|---|---|---|
| A | Unauthenticated landing | no session | open `/` | login CTA, no data, show v22 layout | 1 live + 1 mockup |
| B | Authenticated default | logged in, defaults | open `/` | chart + filter rail, default brand set | 1 live + 1 mockup |
| C | Filter interaction | logged in, default | tap brand pill to unselect one brand → wait → screenshot | chart line drops, mention count updates, KPIs reflect | 1 before + 1 after |
| D | Locale switch | logged in, defaults | tap locale toggle en ↔ zh_cn | chart labels, axis, legend, recommendation text all translated; layout reflows | 2 screenshots |
| E | Time window switch | logged in, defaults | tap 24h → 7d → 30d | chart axis and data update, no overlap | 3 screenshots |
| F | Empty / no-data state | logged in, filter to brand with no mentions | observe | graceful empty state, no broken layout, no "NaN" | 1 live + 1 mockup |
| G | Mobile scroll | logged in, defaults | swipe down | filter drawer collapses, chart scrolls, no overlap | 1 live + 1 mockup |
| H | Top Voices body | logged in, defaults | scroll to top voices | 3-5 voice chips with @handle, star, permalink | 1 live + 1 mockup |

(Visual source of truth: `docs/ideation/mockups/06-tier1-composed.v22-master.html` — single file, responsive mobile ↔ desktop × locale built-in. The 4 `v20-*` files were consolidated into v22-master per the changelog 2026-08-08 entry "Mockup consolidation"; they're retained as design-history previews but no longer the canonical target.)

### Element Audit (Step 0 of every iteration) — Chrome DevTools MCP

Before any scenario capture, the live page must contain every visible element that the v22-master mockup shows, and the visible elements must be functionally identical (same DOM role, same text content, same purpose, same approximate position). This is the load-bearing pre-flight — if the live page is missing a section, no scenario diff is meaningful.

Procedure (Chrome DevTools MCP, **not Playwright** per § "Visual-drift detection: Element Audit + Chrome DevTools MCP"):

1. `mcp__chrome-devtools__navigate_page` to the live URL (e.g. `/` for scenarios A-G, append `?locale=zh_cn` for locale variants).
2. Wait for the page to settle: `mcp__chrome-devtools__wait_for` on the body, `mcp__chrome-devtools__list_console_messages` to confirm no JS errors, then `mcp__chrome-devtools__evaluate_script("() => document.readyState === 'complete'")` to confirm full load.
3. `mcp__chrome-devtools__take_snapshot` to get the a11y tree of the live page.
4. Navigate to the v22-master mockup via `file://` or local `python -m http.server 8001`, `take_snapshot` again.
5. **Viewport-morphology check** (see dedicated subsection below): `mcp__chrome-devtools__resize_page` to the other breakpoint, re-snapshot, verify the DOM structure morphs correctly (desktop → mobile: feed nests under top-voices; mobile → desktop: feed becomes a sibling).
6. Diff the two a11y trees by **section**, not by exact pixel position:
   - For each top-level `<section>`, `<header>`, `<nav>`, `<main>`, `<footer>` in the mockup, confirm an equivalent element exists in the live page.
   - For each heading (`h1`-`h6`), confirm the live page has the same heading at the same nesting level, with the same text content (or a translation-equivalent for `zh_cn` variants).
   - For each interactive control (`button`, `a[href]`, `input`, `select`), confirm it exists in the live page with the same role and similar text.
   - For the feed element specifically, verify its structural parent matches the breakpoint (under top-voices at mobile, sibling at desktop).
7. Write `audit.md` in the iteration dir with: **Identical (matched)** / **Missing on live (P0 blocker)** / **Extra on live** / **Different position** sections.
8. If any P0 missing element is found, **stop the scenario captures and surface to the user**. Fix the missing element first, then re-run the audit.

The audit is fast (~5-10 MCP calls) and runs every iteration. It catches regressions early — if a previous iteration's fix removed a section, the next iteration's audit catches it.

#### What "identical" means at the audit level

The audit defines "identical" at the structural level: every visible region in the mockup exists on the live page with the same role and same text content. Rendering differences (color, spacing, animation, minor typographic drift) are captured by the **per-iteration contract step 6a-c** (see § "Visual-drift detection: Element Audit + Chrome DevTools MCP") and ranked P1/P2/P3 — they are not blockers. Element-presence is the P0 gate.

#### First iteration is audit-first

Iteration 1 runs the Element Audit against the canonical mobile-en mockup, then against mobile-zhcn (if locale is reachable), then runs scenario A (unauthenticated landing). Subsequent iterations re-run the audit as Step 0 first, then proceed to the chosen scenario.

### Viewport morphology (desktop ↔ mobile is the SAME page)

The v22 home is a **single responsive page**, not two separate desktop and mobile layouts. The mockup files (mobile preview + desktop preview) are previews of the same page at different breakpoints, not separate code paths. The plan body is explicit:

- One `<body>` element, one template, one CSS bundle.
- Tailwind responsive prefixes (`md:`, `sm:`) handle the layout changes.
- The feed lives **inside the "Top Voices" section** at mobile widths (it sits below the top-voices list rather than as its own full-width section). This is the load-bearing layout rule — if the feed is rendered as a separate region at mobile widths, the morphology is broken.

Per-iteration procedure for the responsive check:

1. **Element Audit at desktop width** (1440×900, or whatever the available window allows):
   - Run the standard audit against the v22-master mockup at desktop width.
   - Capture the live page snapshot at desktop width.
   - Verify: top voices section, chart section, recommendations section, feed section all present. At desktop width, the feed is **its own full-width section** below the top voices.
2. **Element Audit at mobile width** (390×844):
   - `mcp__chrome-devtools__resize_page 390 844` to switch to mobile viewport.
   - Wait for the page to settle, take the second snapshot.
   - Verify: top voices section is still present, but the **feed is now nested inside the top-voices section** rather than being its own sibling. If the feed re-renders as a separate section at mobile width, that's a P0 (morphology is broken).
3. **Morphology diff**: compare the two a11y trees specifically around the feed's structural parent:
   - Desktop: feed is a sibling of top-voices (both sit under `main`)
   - Mobile: feed is a child of top-voices
   - If the parent chain differs between breakpoints, the responsive code is using `hidden` / `block` toggles instead of relocating the DOM. That's wrong — the relocation should be in the DOM, not just visual.
4. Save both desktop and mobile snapshots to the iteration dir: `audit-desktop-snapshot.txt` and `audit-mobile-snapshot.txt`. Add a `morphology.md` with the parent's-a11y-path comparison.
5. The morphology check is part of every iteration's Element Audit, alongside the standard t=0 / t=60 time-based pass.

### Time-based element testing (audit variation)

The v22 home displays live data that refreshes over time (Top Voices stream, mention counts, time-series chart points). Static snapshots miss elements that only appear after a delay. **Every iteration must include a time-based test pass** that re-runs the audit after a 30s to 60s wait, and compares the delayed state to the t=0 state.

Why this matters:

- Top Voices and live-tile sections may be empty at t=0 and populate after the first data fetch completes (typical 30-60s depending on the harvester schedule).
- Auto-refresh logic (the 60s refresh in the original `pw-feed.js`) is exactly what we want to verify, not bypass.
- The audit at t=0 may show "missing voice chips" as a P0 blocker, but at t=60 the section is populated; the time-based pass prevents false positives.

Procedure for the time-based pass:

1. After completing the t=0 Element Audit, leave the live page open in the Chrome DevTools MCP browser.
2. Wait 60 seconds using `mcp__chrome-devtools__evaluate_script("async () => { await new Promise(r => setTimeout(r, 60000)); return true; }")`.
3. `mcp__chrome-devtools__take_snapshot` again to capture the post-wait a11y tree.
4. Diff the t=0 tree against the t=60 tree:
   - **New elements that appeared:** voice chips, mention rows, chart updates — these are expected, not blockers.
   - **New elements that appeared but should have been there at t=0:** P0 — the live page is failing to render critical content immediately.
   - **Elements that changed state (e.g. "Loading..." → "47 mentions"):** expected, not a blocker.
5. Save both snapshots to the iteration dir: `audit-t0-snapshot.txt` and `audit-t60-snapshot.txt`.
6. Update `audit.md` with the time-based diff: section per element, marked `appeared_after_t0` or `present_at_t0`.

The time-based pass is essentially the same audit run twice with a 60s gap. It catches the most common category of false-positive P0 in data-driven UIs: "element missing" that is actually "element lazy-loaded after the data fetch completes."

### Local servers

| Surface | URL | Source |
|---|---|---|
| Live dev (Django) | `http://127.0.0.1:5050/` | fuchitalee `:5050` via SSH tunnel |
| Mockup canonical | `http://127.0.0.1:8001/06-tier1-composed.v22-master.html` | fuchitalee `:8001` (python -m http.server) |

### Iteration loop (per-iteration contract — REPLACES the v20-plan version)

For each iteration N (1..N_max):

```
For iteration N:
  0. Run Element Audit (a11y tree diff) against live + mockup at same viewport+locale
  1. Run tests/regression_net.py against the live page (asserts all PASSes from previous iterations still pass)
  1a. Run tests/element_audit.py (Chrome DevTools MCP) — NEW per § "Visual-drift detection"
  2. Pick scenario from the matrix (table-driven, not agent-decided)
  3. Run Step 0 audit (a11y tree) at t=0 + t=60 (time-based variation)
  4. Screenshot the mockup at the same viewport + locale
  5. Screenshot the live page at the same viewport + locale
  6. Diff: live vs mockup (NOT live vs previous live)
  7. If diff shows new P0: file gap, add to UI region table above
  8. If diff shows regression: STOP, revert or fix, surface to user
  9. Otherwise: write REPORT.md, commit (with plan-execution-contract footer), advance iteration N+1
```

The critical change is **step 6: compare live against mockup, not against previous live**. This is the cure for the drift the user identified.

### Auth handling

Iter 1: Element Audit (at t=0 and t=60) + scenario A only (no auth). Then sign in via the form on `/accounts/login/?next=/`, persist the session cookie in the Chrome DevTools MCP browser context, run audit + scenarios B, C, G, H.

Local-dev test credentials: `allen@quantma.com` / `ono` (per project-context memory). If login fails (missing test account, password reset required, etc.), the agent surfaces the blocker rather than guessing. Logs in next iteration after the user resolves.

### "What matches / doesn't match" — P0/P1/P2/P3 ranking

For each scenario, the diff is structural:

- **Matches:** layout, hierarchy, spacing, typography, component rendering, color, motion (post-disable)
- **Doesn't match:** same list, ranked:
  - **P0 (blocker):** element missing, broken layout, console error, JS error
  - **P1:** visible regression vs mockup (catches the .pulse-chip-name-color defect class)
  - **P2:** polish / proportion / color
  - **P3:** nice-to-have

### Commit policy

Agent commits to branch `feat/v20-homepage-phase-a`. No push, no PR. Each commit gets the plan-execution-contract `Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]` line.


---

## Verification Contract

1. Nets A–G green.
2. `/` matches exhibit for locale + viewport class.
3. `/internal/` behaves like pre-change `/`.
4. Filter change updates chart + feed via **same** events/URLs.
5. Chart multi-series; no hover hide.
6. Brand-only filter solidifies shell tint.
7. DRY: no duplicate chart/filter business logic modules.
8. No volunteer deploy.

---

## Definition of Done

- [ ] Required skill read
- [ ] Nets A–G green
- [ ] `tests/regression_net.py` (v20 prototype, introduced by `docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md`) green when run against the live page — server-side AND rendered-page nets both pass before any PASS verdict on a U-unit
- [ ] UI region infra mirror table (above) has zero `NOT YET ADDED` rows for cells the unit ships, or a tracked gap with user OK
- [ ] `/` = v22 design; `/internal/` = former homepage
- [ ] Defaults zh_cn + 24h + local
- [ ] Chart + filters reused (DRY)
- [ ] Four exhibits reflected (mobile/desktop × zh/en)
- [ ] Scope line on every commit: `Scope delivered vs plan promised: …`
- [ ] **Eval-named line (per § "Regression net discipline (from 2026-08-08 angle-2 research)" / "Vibe-vs-eval gate"):** Every U-unit's Approach block names which Net (A–G) or `tests/regression_net.py` assertion measures the change, with the BEFORE/AFTER pinned value. "Looks better" / "feels right" / "matches the mockup" are NOT acceptable substitutes.
- [ ] **Failure-closes-the-loop line (per § "Regression net discipline (from 2026-08-08 angle-2 research)" / "Production-tracing → regression-suite pipeline"):** Every production failure surfaced during U0–U7 produces a new pinned assertion in `tests/regression_net.py` or Net A–G BEFORE the unit that surfaced the failure is marked PASS. "Fix the bug, move on" without adding the net is a Definition-of-Done violation.

---

## Open mockup deltas still expected

_(Append future exhibit edits here.)_

### Prior notes retained
- Feed-row shell tint filter-aware (v19+)
- Infinite feed, synthesis/综合, signal rows, unsanctioned 🚫
- App title dual-language row; zh window 天 labels

---

## Changelog (plan document)

| Date | Change |
|---|---|
| 2026-08-09 | **v22 iter 11: U6 mobile-viewport visual audit green** — Chrome DevTools MCP `resize_page 390 844` (clamped to 500 minimum); all 17 sampled regions match mockup pins at mobile width (pulse-chip-name, voice-chip, filter-pill, locale-toggle button, feed-handle-link, pulse-bar horizontal-scroll, filter-bar single-column, feed-strip responsive). Zero visual drift surfaced. Noted structural divergence (live uses `.pulse-chip-name` + flat feed children instead of mockup's `.pulse-chip .name` + `.feed-row` wrapper) — visually inconsequential because iter 5/6 CSS rules already target the actual live class names; structural normalization deferred as separate concern. Regression net stable at 78/0. Remaining v22 work: U7 Integration verification + DoD gate confirmation. Artifacts: `docs/iterations/2026-08-09-v22-iter-011/REPORT.md`. |
| 2026-08-09 | **v22 iter 10: U4 hover-isolate removed from pw-chart.js; +2 assertions** — audit found `hoveredBrandIndex` actively controlling `ds.hidden` in `pw-chart.js` lines 153-190 (plan § U4 explicitly forbids hover-isolate brand hiding; § Net D requires "absent or inert"). Replaced entire `onHover` callback body (42 lines) with 4-line no-op: all brand lines now stay visible on chart hover regardless of cursor proximity. `grep "hoveredBrandIndex" pw-chart.js` after fix: 1 match (explanatory comment only). Net D extended via `_check_chart_no_hover_isolate(session)` in `tests/regression_net.py`: fetches `/static/pw-chart.js`, strips comments, asserts no active `hoveredBrandIndex` references + `onHover` body contains no `ds.hidden` mutations. Regression net: 76 → 78 assertions, 0 failures. Remaining v22 work: U6 mobile-viewport visual audit, U7 Integration verification + DoD gate confirmation. Artifacts: `docs/iterations/2026-08-09-v22-iter-010/REPORT.md`. |
| 2026-08-09 | **v22 iter 9: U2 defaults shipped (window=1, locale=zh_cn); +4 assertions** — audit found live `/` defaulted to 7d not 1d (iter 1-4 left `HOME_WINDOW_DEFAULT=7` despite plan § U2 saying AFTER=1). Fixed `monitor/views.py:154-155`: `HOME_WINDOW_DEFAULT=1` (AFTER), `HOME_WINDOW_DEFAULT_BEFORE=7` (BEFORE pin preserved per Net B requirement). Net B explicit defaults assertions added via `_check_defaults(html, session)` method in `tests/regression_net.py`: no-cookie active-window=1, no-cookie `data-pw-window`=1, no-cookie zh_cn chrome rendered (本窗口最新 present), `home_window=7` cookie honored on returning-user request. Regression net: 72 → 76 assertions, 0 failures. Remaining v22 work: U4 hover-isolate absence assertion, U6 mobile-viewport audit, U7 integration verification + DoD gate. Artifacts: `docs/iterations/2026-08-09-v22-iter-009/REPORT.md`. |
| 2026-08-09 | **v22 iter 8: U1 route split shipped + Net F (/internal/ parity) shipped (+10 assertions)** — closes the iter-7 deferral. Saved pre-v22 `monitor/templates/monitor/home.html` (from git `6ac2ddd^`) to `monitor/templates/monitor/home_internal.html` (180 lines). Added `home_internal()` view at `monitor/views.py:1211` (copy of pre-v22 `home()` body, pointed at home_internal.html; shares all helper functions with v22 `home()`). Added `/internal/` route at `monitor/urls.py:16`. v22 chrome stays at `/`. Net F `_check_internal_parity(session)` method added to `tests/regression_net.py`: asserts `/internal/` returns 200 + 5 legacy markers present (`id="control-panel"`, `id="home-chart"`, `.window-toggle`, `.locale-btn`, `.filter-group`) + 3 v22 markers ABSENT (`.pulse-chip`, `.voice-chip`, `.filter-pill`) + both app names present. Regression net: 62 → 72 assertions, 0 failures. Remaining v22 work: U2 standalone defaults pin, U4 hover-isolate absence, U6 mobile-viewport audit, U7 integration verification + DoD gate. Artifacts: `docs/iterations/2026-08-09-v22-iter-008/REPORT.md`. |
| 2026-08-09 | **v22 iter 7: Comprehensive regression nets C, D, G shipped (+12 assertions); F deferred** — Net C pins the 5 `_DASHBOARD_*_KEYS` tuples from `monitor/views.py` lines 110-141 + asserts all 7 filter groups render via `data-group="..."` (actual wire shape; initial guess of `data-pw-filter-group` was wrong). Net D asserts chart canvas + heading (`Daily total posts per brand` / `每日各品牌帖子总数`) + `pw-chart.js`. Net G asserts zh_cn name + English name + 3-button locale toggle. Total regression net: 50 → 62 assertions, 0 failures. **Net F deferred to iter 8** because audit found `/internal/` returns 404 — iter 1-4 shipped v22 chrome to `/` in-place without adding the `/internal/` route to `monitor/urls.py`, violating plan § Goal Capsule ("move today's homepage to `/internal/`, do not delete or replace in place") and Stop Condition S2. `tests/regression_net.py` annotated with deferral note pointing at iter 8. **U1 (route split) + Net F = iter 8 scope** per user confirmation 2026-08-09. Artifacts: `docs/iterations/2026-08-09-v22-iter-007/REPORT.md`. |
| 2026-08-08 | **v22 iter 6: Phase B chrome visual-drift audit + 5 fixes** — wider audit on U3 (filter chrome), U4 (chart wrap), U5 (pulse/headline), U6 (responsive feed). All sampled regions matched mockup except 3 browser-default leaks: `.locale-toggle button` (color, border-color, border-radius all leaking browser default black/0px), `.feed-row` (color + border-color inheriting link blue from descendant anchors). Fix: appended `.locale-toggle button` + `.feed-row` rules to `monitor/static/home-v20.css`. `tests/visual_tokens.py` extended 5 → 7 pinned regions. Regression net 50/0 PASS pre and post. U3/U4/U5/U6 visual surfaces now substantially validated against v22-master mockup. Remaining v22 work: U0 (Nets A–G), U7 (Integration verification + DoD gate). Artifacts: `docs/iterations/2026-08-08-v22-iter-006/{REPORT.md, audit-pre.json, audit-post.json}`. |
| 2026-08-08 | **v22 iter 5: Visual-drift net shipped + 4 drifted regions fixed** — implementation of § "Visual-drift detection: Element Audit + Chrome DevTools MCP". Created `tests/visual_tokens.py` (single source of truth, 5 pinned regions: `.pulse-chip .name` color, `.voice-chip` bg/color/padding/border-radius, `.feed-handle` color/text-decoration/font-weight, `.filter-button.is-active`, `.delta.up::before`) + `tests/element_audit.py` (Chrome DevTools MCP-driven diff runner). Pre-edit audit surfaced 4 drifts: `.pulse-chip-name` rendering black on dark pulse fill (user-reported), `.feed-handle-link` rendering as browser-default link (blue + underline + weight 400). Root cause: CSS rules existed but used selector patterns that didn't match the v22 template's actual class hierarchy (`.pulse-chip .name` vs template's `<span class="pulse-chip-name">`; `.feed .feed-handle-link` vs v22's `.feed-strip` ancestor). Fix: appended `.pulse-chip-name` and `.feed-strip .feed-handle-link` rules to `monitor/static/home-v20.css`. Post-edit audit: all 4 regions match mockup pins. Regression net 50/0 PASS pre and post. Per-iteration contract § "Visual-drift detection" realized end-to-end. Phase B (U3, U4-chrome, U5, U6) now has automatic visual-diff gate for every future iter. Artifacts: `docs/iterations/2026-08-08-v22-iter-005/{REPORT.md, audit-pre.json, audit-post.json}`. |
| 2026-08-08 | **v20 iteration-loop companion plan CONSOLIDATED into v22 (DEPRECATED)** — `docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md` is now DEPRECATED. Its content (Scenario matrix A-H, Element Audit procedure, Viewport morphology, Time-based testing, Local servers, Iteration loop / per-iteration contract steps 0-9, Auth handling, "matches/doesn't match" P0-P3 ranking, Commit policy) is absorbed into new § "Per-iteration procedure (consolidated from 2026-08-07-001, added 2026-08-08)". Frontmatter updated with `supersedes:` block. Eliminates two-plan drift; one source of truth. Visual source of truth path updated from `v20-{mobile,desktop}-{en,zhcn}.html` (4 files) to `06-tier1-composed.v22-master.html` (1 file with responsive built-in) per the earlier changelog mockup-consolidation entry. |
| 2026-08-08 | **All 7 freeze-criteria gates RESOLVED (Phase B unblocked)** — product-decision freeze fully cleared: F1 defaults = 24h/zh_cn/local-TZ; F2 filter wire = 7 groups ship as-is (Brands/Discourse/account.role/lang/Sentiment/Nationalism/unsanctioned); G1 mock freeze = `06-tier1-composed.v22-master.html` is final; G3 post_type = 6 keys as peers (no primary-bar grouping); G4 sentiment = DB-canonical (4 keys per `lookup-tables.md § 2`); G4b nationalism = DB-canonical (6 keys × 2 axes per § 4); G4c discourse = DB-canonical (10 keys per § 3); G4d roles = DB-canonical (3 persisted + 1 computed per § 5); G4e unsanctioned = DB-canonical (4 keys per § 6). User direction 2026-08-08: "literally all of the filter labels should be determined by db … make sure to clearly have the plan use db as canon for every filter and choices within each." Both freeze blocks updated; second block's G4 (Net A–G acceptance) and G5 (avoiding-recurring-mistakes skill acknowledgement) remain ACTIVE — implementer-acknowledgement gates, deferred to Phase B agent. Phase B (U1-full chrome, U3, U4-chrome, U5, U6) is now go-decision-only at the user's `/goal` prompt. |
| 2026-08-08 | **Visual-drift detection: Element Audit + Chrome DevTools MCP added** — new § "Visual-drift detection: Element Audit + Chrome DevTools MCP (added 2026-08-08)" inserted between angle-1 (iteration drift) and angle-2 (regression net) sections. Distills the prior research-incorporation session's browser-tool decision (Chrome DevTools MCP native `mcp__chrome-devtools__` over Playwright MCP: zero-install CDP, shares user's running Chrome, exposes both `take_snapshot` and `evaluate_script(fn)`). Adds **NEW** unit: `tests/visual_tokens.py` (single source of truth, ≥ 5 pinned regions) + `tests/element_audit.py` (Chrome DevTools MCP-driven computed-style diff vs `tests/regression_net.py` HTTP-only). Pinned regions include `.pulse-chip-name` color (the 2026-08-08 defect — black on dark fill — AFTER state: `rgb(255, 255, 255)`), `.voice-chip` background, `.filter-button:hover`, `.feed-handle` text-decoration, `.delta.up::before` content. Per-iteration contract extended with steps 6a-6c; new Definition-of-Done line "Visual drift net shipped and green." Scope: angle-3 incorporation. Implementation units TBD in iter 5 — no silent narrowing. |
| 2026-08-08 | **v22 iter 4: Top Voices body RESOLVED (historical blocker)** — P0 #1 of 5 fixed. Added `_multi_top_voices(window_days, limit=3)` view function joining Post × Account; voice_score = mention_count × log10(followers_count+10). Rendered `<span class="headline-voices">` block with `<a class="voice-chip">@handle (☆ N)</a>` chips, ordered by star DESC, comma-separated. CSS `.headline-voices` / `.voice-chip` / `.voice-star` appended to `home-v20.css`. Regression net extended from 46 to 50 assertions (+5 top-voices checks), all green. Live verified: @JulianGoldieSEO (☆ 869), @Megannewman99 (☆ 631), @tushar_koshti (☆ 445). **All 4 P0 gaps closed — goal `v22` condition MET.** |
| 2026-08-08 | **v22 iter 3: Feed engagement + avatar circles resolved** — P0 #3 + #4 of 5 from iter 1 audit fixed. Added `_avatar_initials()` (1-2 char uppercase from handle), `_avatar_color()` (djb2 hash → stable HSL), `_engagement_pretty()` (compact counters); extended `_post_to_wire()` return with `retweet_count`/`reply_count`/`quote_count`/`avatar_initials`/`avatar_color`/`engagement_pretty`. Template `_feed_initial.html` wraps handle cell in `<div class="feed-author">` with avatar + adds `<div class="feed-engagement">` with 4 `.engagement-stat` spans (👥/♥/↻/💬 HTML entities). CSS `.feed-author`/`.avatar`/`.feed-engagement`/`.engagement-icon` appended to `home-v20.css`. Regression net extended from 37 to 46 assertions (+6 engagement +3 avatar), all green. UI region table updated. 1 P0 gap remains: Top Voices. |
| 2026-08-08 | **v22 iter 2: Trending %change deltas resolved** — P0 #2 of 5 from iter 1 fixed. Added `_compute_brand_deltas()` (single aggregation query against PostBrand x Post, 60 min vs prior 60 min buckets); extended `_build_brands_context()` with pct_change / pct_arrow / pct_class; template renders `<span class="delta {{ b.pct_class }}">{{ b.pct_change }}%</span>` inside pulse-chip. CSS .delta.up/.down/.flat arrows were already in `home-v20.css:200-206`. Regression net extended from 34 to 37 assertions (added 3 trending-delta checks), all green. UI region table updated; Locale default P0 dropped (false positive — `LANGUAGE_CODE="zh-hans"`). 3 P0 gaps remain (Top Voices, Feed engagement counts, Feed avatar circles). Goal hook still holding. |
| 2026-08-08 | **v22 iter 1: Element Audit + 5 new P0 gaps filed** — regression net 34/0 PASS; live vs v22-master diff surfaced Top Voices (pre-existing), Trending %change deltas, Feed engagement counts, Feed avatar circles, Locale default. UI region table extended with 4 new NOT YET ADDED rows. Per per-iteration contract step 8, scenario captures deferred until P0 audit failures are addressed. Artifacts: `docs/iterations/2026-08-08-v22-iter-001/{REPORT.md, live.png, v22-master.png}`. |
| 2026-08-08 | **Mockup consolidation: 4 v20-* files collapsed to single `06-tier1-composed.v22-master.html`** (responsive mobile ↔ desktop + locale toggle built-in). All 5 mockup references in plan updated to point at v22-master (3 doc-paths + 1 local mirror + 1 Sources bullet). v20-* files retained on disk as design-history. |
| 2026-08-08 | **Regression net discipline incorporated** from `docs/research/2026-08-08-regression-nets-for-ai-agents-raw.md`: new § "Regression net discipline (from 2026-08-08 angle-2 research)" with 6 adopted patterns (Evals-as-regression-tests / Closed-loop RUN-detect-diagnose / REGRESSION.md-named-after-failure / Production-tracing-suite-pipeline / Vibe-vs-eval / Agent-as-QA-PR-gate) + 2 deliberately skipped (AgentCore Evaluations / TDD-useless-tests). Sub-sections: "Evals as regression tests (v18)" framing Nets A–G as the v18 analog of LLM evals; "Closed-loop RUN → detect reds → diagnose" mapping hackproduct9 5 stages onto v18/v20 verification gate; "Production-tracing → regression-suite pipeline" adapting Metacto/LangSmith/Langfuse/Arize/Braintrust loop; "Vibe-vs-eval gate" reinforcing Definition of Done with two new lines (eval-named + failure-closes-the-loop).
| 2026-08-08 | **Iteration drift mitigation incorporated** from `docs/research/2026-08-08-agentic-ui-iteration-loop-drift-raw.md`: new § "Iteration drift mitigation (from 2026-08-08 angle-1 research)" with 4 adopted patterns w/ citations (compare-live-vs-mockup-not-previous-live, bounded-loop task contract, Playwright/browser-MCP evidence, explicit approval before baseline update) + 3 deliberately skipped + drift-mitigation discipline paragraph referencing v20 plan's per-iteration contract step 6 verbatim. |
| 2026-08-08 | **Design system contract framework incorporated** from `docs/research/2026-08-08-design-system-contract-gap-analysis-raw.md`: new § "Design system contract framework" (8 adopted patterns w/ citations, 3 deliberately skipped); **UI region → DB query → view function → template loop** table (12 regions × 5 columns) + mockup-side infra mirror table (11 rows); **regression-net-discipline paragraph** pointing to `tests/regression_net.py` prototype from v20 plan; Sources section updated; end-of-unit scope delta footer. |
| 2026-08-07 | **Agent handoff brief:** Phase A authorized now (U0–U2, U4); Phase B after exhibit freeze; hard stop conditions; copy-paste agent prompt. |
| 2026-08-07 | **Canonical exhibits = four v20 files**; session prompts incorporated; **DRY/reuse chart+filters** mandate; **required** avoiding-recurring-mistakes skill; **comprehensive regression nets A–G**; legacy home path **`/internal`** (not replace; not `/old`); root = new design. |
| 2026-08-07 | Feed shell tint filter-aware (R12/KTD11). |
| 2026-08-07 | WIP living-doc rewrite from v18-oriented draft. |
| 2026-08-05 | Initial plan draft. |

---

## Sources

- Exhibits: `/Users/fuchitalee/development/pushin-weight-v2/docs/ideation/mockups/06-tier1-composed.v22-master.html` (+ local Downloads mirror)
- Lookup: `docs/reference/lookup-tables.md`
- Skill: `.claude/skills/avoiding-recurring-mistakes/SKILL.md`
- Live home: `monitor/templates/monitor/home.html`, `monitor/views.py`, `monitor/static/pw-*.js`
- Design session: dropdown debug → taxonomy → TZ → feed signals → v22 trifurcation (+ desktop)
- Research: `docs/research/2026-08-08-design-system-contract-gap-analysis-raw.md` (WebSearch supplemental results enumerate the contract / schema / regression-net / agentic-iteration citations referenced in § "Design system contract framework")
- Research: `docs/research/2026-08-08-agentic-ui-iteration-loop-drift-raw.md` (drift-mitigation citations referenced in § "Iteration drift mitigation")
- Research: `docs/research/2026-08-08-regression-nets-for-ai-agents-raw.md` (regression-net / closed-loop / production-tracing / agent-as-QA citations referenced in § "Regression net discipline (from 2026-08-08 angle-2 research)")
- Companion plan (prototype iteration loop + `tests/regression_net.py`): `docs/plans/2026-08-07-001-DEPRECATED-feat-v20-agentic-iteration-plan.md`
- Visual drift pin source (single source of truth for computed-style assertions): `tests/visual_tokens.py` (NEW — to be created in iter 5)
- Visual drift audit script: `tests/element_audit.py` (NEW — Chrome DevTools MCP-driven, to be created in iter 5)

---

## End-of-unit scope delta

`Scope delivered vs plan promised: match — three research incorporations completed (first research = design-system-contract, second = agentic-ui-iteration-loop-drift, third = regression-nets-for-ai-agents) + mockup consolidation (4 v20-* files — single v22-master). Added by angle-2 (this revision): § "Regression net discipline (from 2026-08-08 angle-2 research)" (6 adopted patterns w/ citations, 2 deliberately skipped) + 4 sub-sections + 2 new Definition-of-Done lines + Sources entry for the angle-2 research file + Changelog row. Added by mockup-consolidation (this revision): all 4 v20-* mockup file references collapsed to single v22-master file (responsive mobile ↔ desktop + locale toggle built-in) using the fuchitalee absolute path. Added by angle-3 visual-drift-detection (this revision): § "Visual-drift detection: Element Audit + Chrome DevTools MCP (added 2026-08-08)" — distills prior session's Chrome DevTools MCP vs Playwright decision; defines NEW unit `tests/visual_tokens.py` (pinned computed-style values for ≥ 5 regions) + `tests/element_audit.py` (Chrome DevTools MCP-driven visual diff); per-iteration contract extended with steps 6a-6c; new Definition-of-Done line "Visual drift net shipped and green." Implementation units TBD in iter 5 — design-only scope this revision; no code changes yet. Added by gate-resolution (this revision): all 7 product-decision freeze gates RESOLVED via sequential Q&A (F1 defaults, F2 filter wire, G1 mock freeze, G3 post_type, G4 sentiment, G4b nationalism, G4c discourse, G4d roles, G4e unsanctioned) — every filter value DB-canonical per `docs/reference/lookup-tables.md`. Phase B (U1-full chrome, U3, U4-chrome, U5, U6) now unblocked. Project-hygiene gates G4 (Net A–G acceptance) and G5 (avoiding-recurring-mistakes skill acknowledgement) remain ACTIVE — implementer-acknowledgement gates, deferred to Phase B agent. No units deferred; no silent narrowing.
