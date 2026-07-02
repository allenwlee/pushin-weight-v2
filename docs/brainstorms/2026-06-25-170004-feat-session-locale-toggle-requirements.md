Created: 2026-06-25


# Session-level locale toggle — URL path prefix + original + backfill

## Overview

Ship a user-facing locale toggle for x-monitor that exposes **3 locales** at the **URL path level** (`/en/`, `/zh-CN/`, `/original/`), persists the choice per session via cookie, and ships the **translation backfill** so toggling actually flips the existing 4,683 posts from raw text to translated text.

Builds on the prior `feat/i18n-locale-columns-rebased` branch (commits `ec70c60`–`2537761`, June 23) which already delivered migrations 006/007/008 (locale columns + enum i18n lookup tables + FK conversion), Store i18n helpers (`_pick_i18n_text`, `_pick_enum_label`), translator extension for brand/signal/role/tier, and dashboard i18n wiring (`_load_signal_labels`, `_load_role_labels`, `_load_brand_display_names`). The current `?locale=` + cookie pattern was decided in R10 of `2026-06-17-001-refactor-two-call-wide-net-translation-plan.md`. This plan **supersedes** that URL decision in favor of path-prefix routing per user direction.

## Problem Frame

The dashboard already has **2/3 of the i18n stack** built:
- Per-row translation columns (`text_en`, `text_zh_cn`) on `posts` + per-registry-row locale columns on `brands`, `accounts`, etc.
- 3 enum label tables (`signal_labels`, `role_labels`, `engagement_tier_labels`) with both `en` and `zh_cn` populated
- A locale resolver (`_resolve_locale`) that reads `?locale=` query > `locale` cookie > default `en`
- A working `EN | 中文` toggle in the topbar that POSTs to `/api/set_locale`

What's missing:
- **URL strategy.** URLs are unprefixed. The same `/grid` URL serves all locales; search engines and share-links can't disambiguate. Decision (R10 from origin plan) was to keep it that way, but the user has now requested path-prefix routing.
- **"Original" as a third locale.** Users want to see the source-language text (e.g. Chinese post → untranslated Chinese), not just en/zh-CN. Today there's no toggle for it; `_pick_text` always prefers `text_<locale>` over `text`.
- **Translation backfill.** 4,683 posts in `posts` have `text_en=NULL, text_zh_cn=NULL` — toggling to 中文 on a Chinese post would show the same raw text (which is fine), but toggling to English on the same post would also show the raw Chinese (broken). The translation pipeline was specced in the origin plan but the existing posts predate the pipeline activation.
- **JS-side strings.** `static/dashboard.js` hardcodes "last updated: never" and "Xs ago". `static/trend-chart.js` hardcodes chart series labels as a fallback. Treemap template hardcodes the polarity legend ("criticism rising", "flat", etc.). None of these are locale-aware.

## Requirements Trace

- **R1.** Three locales are user-selectable: `en`, `zh_cn` (canonical URL spelling), `original`.
- **R2.** URL strategy is **path-prefix routing**: `/en/...`, `/zh-CN/...`, `/original/...`. The unprefixed `/` redirects to a locale-prefixed path based on cookie or `Accept-Language` (default `en`).
- **R3.** Locale selection persists per session via the existing `locale` cookie. Cookie value matches the URL path component (no `?locale=` query needed).
- **R4.** Every UI surface — templates, JS-rendered strings, brand display names, signal/role/tier labels, post text, headlines — renders in the active locale. The `original` locale shows the source `text` column verbatim with a small "(source)" badge.
- **R5.** Translation backfill: an operator-initiated `x-monitor translate --backfill` runs Haiku 4.5 over the existing 4,683 posts and populates `text_en` + `text_zh_cn`. Idempotent: re-running skips posts that already have both translations. Bounded: `--limit N` per batch, `--locale en|zh_cn|both` to scope.
- **R6.** Existing behavior is preserved for users who land on unprefixed URLs: cookie → locale-prefixed redirect. Existing `/api/set_locale` POST is **deprecated** in favor of the path-prefix redirect (kept as a no-op fallback for one release).
- **R7.** The 30s htmx poller propagates locale by preserving the path prefix on every poll endpoint. No cookie-vs-path mismatch.
- **R8.** All existing tests pass; new coverage for the locale-prefix routing, the `original` locale handling, the redirect logic, and the JS string-passing convention.

## Scope Boundaries

- **In scope:** x-monitor dashboard routes only (Flask app at `/`); JS strings in `static/dashboard.js` + `static/trend-chart.js`; Jinja templates (`grid.html.j2`, `treemap.html.j2`, `model_detail.html.j2`, `_model_card.html.j2`, `_grid_cards.html.j2`, `_treemap_svg.html.j2`); the `SUPPORTED_LOCALES` set and `_pick_text` / `_pick_i18n_text` helpers; the `/api/set_locale` endpoint (deprecate then remove); translation backfill CLI.
- **Out of scope:** New locales beyond `en` + `zh_cn` (Japanese / Korean are deferred, same as the origin plan's R14). Per-post UI for forcing a specific translation. Re-translation of historical posts that already have a translation (the backfill skips them). Multi-locale storage beyond two columns per text field. x-monitoring landing pages outside the dashboard. Marketing-site copy (the `minimax-marketing` repo has no marketing-site templates — Flask-rendered dashboard is the entire surface).
- **Branch policy:** This plan lands on top of `feat/i18n-locale-columns-rebased`. After merge, all i18n work (schema + helpers + URL routing + toggle UI + backfill) lives on a single branch. The rebased branch's migration 007 will be renumbered to 009 at rebase time to match main's current migration count (1–6).

## Context & Research

### Prior work on `feat/i18n-locale-columns-rebased`

This branch (6 commits, ~3,500 insertions) is already in place on `worktrees/i18n-locale-columns/`. **Schema and store-layer work is done** — do not redo.

- `ec70c60` — migration 006: i18n locale columns on registry tables (`display_name_en`, `display_name_zh_cn`, etc.)
- `d4d0c07` — migration 007 (renumbered 008 at rebase): enum i18n lookup tables + FK conversion for `signal`/`role`/`engagement_tier` columns
- `6aecbc7` — Unit 3: Store i18n helpers (`_pick_i18n_text`, `_pick_enum_label`, FK guards)
- `69d792d` — Unit 4: translator extension + `translate-registry` CLI subcommand
- `c89b99c` — Unit 5: dashboard i18n wiring (`_load_signal_labels`, `_load_role_labels`, `_load_brand_display_names`, `_load_bio`)
- `2537761` — 5 backfill scripts (display_name, bio, enum labels) for both `en` and `zh_cn`

What's **not** on that branch and what this plan adds:
- URL path-prefix routing (current uses `?locale=` + cookie)
- 3-way toggle UI (current has 2 buttons)
- `original` as a third locale option
- JS-side string localization
- Backfill of post-text translations (the prior plan covers registry-row backfills but **not** post-text translations)

### Relevant code and patterns

- `x-monitoring/x_monitor/dashboard.py::SUPPORTED_LOCALES` (line 75) — currently `("en", "zh-CN", "zh_cn")`. Add `"original"` (alias `"src"`).
- `x-monitoring/x_monitor/dashboard.py::_LOCALE_TO_COLUMN` (line 79) — maps locale → DB column suffix. `original` has no column suffix (returns source).
- `x-monitoring/x_monitor/dashboard.py::_resolve_locale` (line 712) — reads query > cookie. Path-prefix routing supersedes the query branch; cookie still wins for unprefixed-URL fallback.
- `x-monitoring/x_monitor/dashboard.py::api_set_locale` (line 1004) — POSTs to set the cookie. Becomes a deprecated no-op or redirect helper.
- `x-monitoring/x_monitor/dashboard.py::_pick_text` (line 111) — `(text, is_translated)` for a post in a given locale. For `original`, returns `(post["text"], False)` without checking translations.
- `x-monitoring/x_monitor/dashboard.py::_load_signal_labels` (line 189), `_load_role_labels` (line 205), `_load_brand_display_names` (line 155), `_load_bio` (rebranded from `_load_signal_labels`) — all keyed by locale. Need a locale="original" branch that returns the source value (no translation).
- `x-monitoring/x_monitor/translator.py::translate_batch` — already exists; the registry-translation extension on the rebased branch adds brand/signal/role/tier handling. The post-text translation is the existing flow.
- `x-monitoring/x_monitor/__main__.py::cmd_translate` — already exists (added on rebased branch). Needs a `--backfill` mode that runs over all posts where `text_en IS NULL OR text_zh_cn IS NULL`.
- `x-monitoring/x_monitor/templates/grid.html.j2::.locale-switcher` (line 32) — current 2-button form posting to `/api/set_locale`. Replace with 3-link set: `EN | 中文 | Original`, each pointing to `/<locale>/` (the current path is the active locale; the link switches to a different locale at the same logical route).
- `x-monitoring/x_monitor/static/dashboard.js` — hardcoded English strings ("last updated: never", "Xs ago").
- `x-monitoring/x_monitor/static/trend-chart.js` — hardcoded English chart labels ("Q1 release", etc.); already supports `data-signal-labels` JSON override from server; needs fallback-key labels as a per-locale lookup.

### Institutional learnings

- The prior plan `2026-06-17-001-refactor-two-call-wide-net-translation-plan.md` R10 decided to use `?locale=` + cookie. **This plan supersedes that decision** in favor of path-prefix per user direction (2026-06-25). The cookie continues to exist as the persistence mechanism for the unprefixed-URL fallback; the query parameter is dropped.
- Per memory `feedback_parallel_subagents_ximports.md`, when dispatching parallel subagents for tightly-coupled work, pre-budget a reconciliation subagent. The four units below share three cross-import contracts: `SUPPORTED_LOCALES` (extended), `_pick_text` (new branch), and `templates/_model_card.html.j2` (data-signal-labels JSON shape).
- Per memory `feedback_no_oversell.md`, the test must actually exercise the differentiator. The `original` locale test must verify that `_pick_text` returns the raw `text` column, not a translation — that's the entire user-facing claim.
- Per memory `feedback_artifact_arbiter.md`, the artifact (the dashboard rendering) is the final arbiter. A live screenshot of all three locales side-by-side is the post-deploy verification, not a unit test.

### External references

- Flask blueprint per-locale pattern: idiomatic Flask 2.x + 3.x. Each locale is its own `Blueprint` with `url_prefix`; the unprefixed root uses `flask.redirect` based on cookie/Accept-Language. No external dependency.
- htmx hx-get with path-prefix: the existing `/api/grid.html` and `/api/treemap.html` htmx pollers work as-is when the page URL carries the locale prefix — htmx resolves relative URLs against the current page URL. We must NOT use absolute paths in `hx-get`. The locale-aware API endpoints (`/en/api/grid.html`, `/zh-CN/api/grid.html`) are auto-generated by Flask blueprint registration.
- Next.js / Nuxt i18n routing convention: `/[locale]/path` is the dominant 2026 idiom for prefix-routed multilingual sites (Next.js docs: `i18n.routing` config). We're not using Next.js, but the URL convention matches the user's stated expectation and industry trend.

## Key Technical Decisions

- **Path-prefix routing via Flask blueprints, not a single-prefix decorator.** Three blueprints (`bp_en`, `bp_zh_cn`, `bp_original`) each with `url_prefix="/<locale>"`. The unprefixed routes (`/`, `/grid`, `/api/grid.html`, `/api/treemap.html`, `/api/treemap.json`, `/api/polarity_window/<int:days>`, `/api/set_locale`, model-detail `/brand/<id>`) get **the same set of blueprints** so all paths are reachable under any locale. This is more boilerplate than a decorator but it makes the URL space explicit and grep-able, and it eliminates a class of bugs where some routes accidentally fall through to the unprefixed handler.
- **Locale prefix is `zh-CN` not `zh_cn`.** URLs use the canonical BCP-47 spelling; the internal column suffix stays `zh_cn` for SQL ergonomics. The `SUPPORTED_LOCALES` tuple already carries both spellings (`"zh-CN"` as canonical, `"zh_cn"` as DB suffix).
- **`original` is a true third locale, not a fallback.** Stored as a string in `SUPPORTED_LOCALES`. `_pick_text` branches: if locale == "original", return `(post["text"], False)` immediately, never read `text_en` / `text_zh_cn`. `_pick_i18n_text` (registry rows) similarly: if locale == "original", return `(row[column], False)`.
- **Cookie wins for unprefixed-URL fallback.** When a request hits `/` without a locale prefix, the dashboard reads the `locale` cookie (existing behavior); if absent, falls back to `Accept-Language` header matching `en` or `zh-CN`; if no match, defaults to `en`. The cookie is set whenever a user clicks a locale link in the toggle (the link is a `302` redirect to `/<cookie-locale>/<same-path>`). The `/api/set_locale` endpoint becomes a deprecated no-op redirect helper (kept for one release to avoid breaking existing dashboard.js polling on legacy paths).
- **HTMX locale propagation by path.** The htmx `hx-get` attribute resolves relative URLs against the current page URL. When the page is `/en/grid`, `hx-get="/api/grid.html"` resolves to `/api/grid.html` (NOT `/en/api/grid.html`). **Fix**: change hx-get to use locale-aware paths via Jinja: `hx-get="{{ request.path.rsplit('/', 2)[0] }}/api/grid.html"`. Cleaner alternative: use absolute server-relative paths and register the API blueprint at root for ALL locales (the `?locale=` cookie still drives resolution). Decision: keep API endpoints at root for backward-compat with the existing JS polling; only the page-rendering routes get the locale prefix.
- **JS-side locale strings via `data-*` attributes on `<body>`.** Each page sets `<body data-locale="en">` (or `zh-CN` / `original`) and JS reads `document.body.dataset.locale` to look up strings from a per-page `<script type="application/json" id="locale-strings">{...}</script>` block populated by Jinja. Avoids a separate JS-locale dictionary file; strings stay co-located with the template that uses them.
- **Translation backfill uses Haiku 4.5.** Same model and same per-batch (20 tweets) shape as the existing translator pipeline. Bounded by `--limit N` and `--locale en|zh_cn|both` flags. Idempotent: skips posts with both columns already populated. Logs progress; resumable across runs (no state).
- **`/api/set_locale` is deprecated, not deleted.** Old clients hitting the endpoint get a `301` redirect to the canonical `/<locale>/` path with the same route (if the request has a Referer) or `/` (if not). One-release deprecation window; remove in the next plan.

## Open Questions

### Resolved during planning

- URL strategy → path prefix (user, 2026-06-25).
- Toggle set → `en` + `zh_cn` + `original` (user, 2026-06-25).
- Backfill scope → included (user, 2026-06-25).
- Plan scope → full repo (x-monitoring dashboard) (user, 2026-06-25).

### Deferred to implementation

- **Cookie `SameSite` setting for path-prefixed URLs.** The existing cookie uses `samesite="Lax"`. Path-prefix routing doesn't change the cookie scope (`path="/"` covers everything). Decision deferred: keep `Lax` unless a cross-origin embed case appears.
- **Migration renumbering at rebase time.** The rebased branch has migration 007 (will be renumbered to 009 at rebase to match main's current 1–6). The implementer should renumber the migration files AND update the test imports. Cross-check the existing `_migrations` ledger at rebase to avoid duplicate-version errors.
- **`HEAD` redirect behavior for canonical URLs.** When `/en/grid` is requested but the user lands on `/grid` (cookie says `en`), should the redirect be a 302 (temporary) or 301 (permanent)? SEO-wise 301 is correct; session-wise 302 is safer for the cookie-driven fall-through. Default to 302; revisit if SEO matters.
- **Backfill ordering for the 4,683 posts.** Should the backfill translate all `en` first, then `zh_cn`, or interleave? Per-batch cost is ~$0.005 per locale (Haiku); 4,683 × $0.005 × 2 = ~$47 for both locales. Wall-clock at ~3s/batch × 4,683 / 20 = ~700 batches × 3s = ~35 minutes for both locales if serial. Implementation should batch per locale but interleave across locales; can run async.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### URL space (before vs after)

```
BEFORE (current):                     AFTER (this plan):
─────────────────                     ─────────────────
/                                     / → 302 to /<locale>/ (cookie/Accept-Language)
/grid                                  /en/
/brand/<id>                            /en/grid
/api/grid.html                         /en/brand/<id>
/api/treemap.html                      /en/api/grid.html      ← only if API is locale-prefixed
/api/treemap.json                       /en/api/treemap.html     (decision: keep at root for JS compat)
/api/polarity_window/<int>             /zh-CN/
/api/set_locale (POST)                 /zh-CN/grid
                                       /zh-CN/brand/<id>
                                       /original/
                                       /original/grid
                                       /original/brand/<id>
```

The API endpoints (`/api/*`) stay at root for JS polling compatibility; only page-rendering routes get the prefix. htmx `hx-get` resolves relative URLs against the current page URL, so `hx-get="/api/grid.html"` on `/en/grid` resolves to `/api/grid.html` correctly.

### Request flow (locale resolution)

```
incoming request to /zh-CN/grid
  ↓
Flask routes /zh-CN/ → bp_zh_cn blueprint (url_prefix="/zh-CN")
  ↓
blueprint's grid() handler
  ↓
resolve_locale_from_path() → "zh-CN" (from url_prefix, highest priority)
  ↓
if no path prefix (e.g. /grid):
  resolve_locale_from_request() → cookie → Accept-Language → "en" default
  ↓
redirect 302 to /<resolved_locale>/grid if path-prefixed URL was missing
  ↓
render_template("grid.html.j2", active_locale=resolved)
```

The path-prefix takes precedence over the cookie when both are present (a user who clicks a `/fr/` link but has a cookie saying `en` lands on `fr`; the cookie updates on the next click of the locale toggle). The cookie is the persistence layer for users who type the unprefixed URL.

### Translation backfill CLI shape

```
$ x-monitor translate --backfill [--locale en|zh_cn|both] [--limit N] [--batch-size 20]

# Pseudocode shape:
def cmd_translate_backfill(args):
    locale = args.locale  # "en" | "zh_cn" | "both"
    limit = args.limit or float("inf")
    batch_size = args.batch_size or 20
    client = get_claude_client()
    store = open_store()
    pending = store.posts_missing_translation(locale=locale, limit=limit)
    while pending:
        batch = pending[:batch_size]
        rows = translate_batch(batch, target_locales=[locale], client=client)
        store.bulk_update_translations(rows)
        pending = pending[batch_size:]
        log(f"translated {n}/{total}")
```

## Implementation Units

- [ ] **Unit 1: Path-prefix routing + locale redirect**

**Goal:** Every page-rendering route is reachable under `/en/`, `/zh-CN/`, `/original/`. Unprefixed `/`, `/grid`, `/brand/<id>` redirect to the locale-prefixed path based on cookie → Accept-Language → default.

**Requirements:** R2, R3, R6, R7

**Dependencies:** None (first unit; rebased branch's i18n helpers are already in place)

**Files:**
- Modify: `x-monitoring/x_monitor/dashboard.py` — register three locale blueprints (`bp_en`, `bp_zh_cn`, `bp_original`) with `url_prefix="/<locale>"`, each registering the page-rendering routes (`/`, `/grid`, `/brand/<id>`)
- Modify: `x-monitoring/x_monitor/dashboard.py::api_set_locale` — change from "set cookie + return JSON" to "302 redirect to /<locale>/<same-path>"
- Modify: `x-monitoring/x_monitor/dashboard.py::_resolve_locale` — add `resolve_locale_from_path()` that reads the blueprint URL prefix; priority is path > cookie > Accept-Language > default
- Modify: `x-monitoring/x_monitor/templates/grid.html.j2`, `treemap.html.j2`, `model_detail.html.j2` — change `<html lang="en">` to `<html lang="{{ active_locale }}">` (already partially done on rebased branch)
- Test: `x-monitoring/tests/test_dashboard_locale_routing.py`

**Approach:**
- Each blueprint is a thin shim around a shared `_render_grid()`, `_render_treemap()`, `_render_model_detail()` helper. This avoids 3× duplication of route handlers. Helpers take a `locale: str` arg and a `path_prefix: str` arg (for the locale-toggle links to use as the base).
- The redirect at `/` (unprefixed) reads cookie; if absent, parses `Accept-Language` for `en` or `zh-CN`; defaults to `en`.
- API endpoints (`/api/grid.html`, `/api/treemap.html`, `/api/treemap.json`, `/api/polarity_window/<int:days>`) stay at root for JS polling compatibility. Their locale is resolved from cookie (existing `_resolve_locale`).
- The `original` blueprint's pages render the same data as `en`/`zh-CN` but with `_pick_text(post, "original")` returning the raw `text` column. Templates show a small "(source)" badge next to each post text.

**Execution note:** Start with a characterization test of the existing `/`, `/grid`, `/brand/<id>` routes — confirm they currently serve English regardless of cookie (since the cookie was only honored by the JS path) — then extend.

**Patterns to follow:**
- `x-monitoring/x_monitor/dashboard.py::_register_routes` (line 859) — existing route registration; new blueprints mirror its structure
- `x-monitoring/x_monitor/dashboard.py::api_set_locale` (line 1004) — existing POST handler that sets the cookie; the new version redirects instead

**Test scenarios:**
- Happy path: GET `/en/grid` returns 200, body has `active_locale="en"` in Jinja context.
- Happy path: GET `/zh-CN/grid` returns 200, body has `active_locale="zh-CN"`.
- Happy path: GET `/original/grid` returns 200, body has `active_locale="original"`.
- Edge case: GET `/grid` (no prefix) with no cookie → 302 to `/en/grid`.
- Edge case: GET `/grid` with `locale=zh-CN` cookie → 302 to `/zh-CN/grid`.
- Edge case: GET `/grid` with `Accept-Language: zh-CN` (no cookie) → 302 to `/zh-CN/grid`.
- Edge case: GET `/grid` with `Accept-Language: ja-JP` (unsupported) → 302 to `/en/grid`.
- Error path: GET `/fr/grid` (unsupported locale prefix) → 404 (or 302 to `/en/grid`; decision deferred to implementation).

**Verification:** All existing dashboard tests still pass; new tests cover all 4 supported locale-prefix routes and the 4 redirect scenarios above. Manually curl `/grid` with `Accept-Language: zh-CN` from a terminal → expect 302 to `/zh-CN/grid`.

- [ ] **Unit 2: 3-way toggle UI + `original` locale handling**

**Goal:** The topbar locale switcher shows three buttons (EN | 中文 | Original). Clicking each navigates to the locale-prefixed URL. The `original` locale causes every text-rendering helper to return source values without translation.

**Requirements:** R1, R4

**Dependencies:** Unit 1 (path-prefix routing must exist so the toggle can link to the correct prefix)

**Files:**
- Modify: `x-monitoring/x_monitor/dashboard.py::SUPPORTED_LOCALES` — add `"original"` (canonical) and `"src"` (alias)
- Modify: `x-monitoring/x_monitor/dashboard.py::_LOCALE_TO_COLUMN` — `original` → `None` (no column)
- Modify: `x-monitoring/x_monitor/dashboard.py::_pick_text` (line 111) — branch: if locale == "original", return `(post["text"], False)` immediately
- Modify: `x-monitoring/x_monitor/dashboard.py::_load_brand_display_names` (line 155), `_load_signal_labels` (line 189), `_load_role_labels` (line 205) — add `locale == "original"` early-return that returns the source (English) value
- Modify: `x-monitoring/x_monitor/templates/grid.html.j2::.locale-switcher` (line 32) — replace 2-button form with 3-anchor set: each anchor is `href="/<locale>/<current-path>"` with `class="locale-link {% if active_locale == '<locale>' %}active{% endif %}"`
- Modify: `x-monitoring/x_monitor/templates/treemap.html.j2`, `model_detail.html.j2` — add the same 3-anchor switcher (currently absent in the rebased branch)
- Test: `x-monitoring/tests/test_dashboard_locale_routing.py` (extend) + `x-monitoring/tests/test_dashboard_i18n.py` (extend)

**Approach:**
- The 3-anchor switcher is the same `class="locale-link"` markup as the current 2-button form, just with anchors instead of buttons (because the action is GET navigation, not POST). The "active" class drives the visual highlight.
- The `_pick_text` change is a single if-statement at the top: `if locale == "original": return post.get("text"), False`. The `False` flag tells the template to show the "(source)" badge.
- For `_load_*_labels` helpers, the `original` branch returns the English value (since the seed data is English-keyed; the values in the keys table are the canonical English strings). Tests verify that.
- The `data-signal-labels` JSON attribute (already wired on rebased branch) keeps working: when `active_locale == "original"`, the JSON carries the English labels, and `trend-chart.js` falls back to its hardcoded English labels when the JSON is empty.

**Patterns to follow:**
- The rebased branch's `_load_signal_labels` (line 189) — copy its locale-resolution shape, add the `original` branch
- The current grid.html.j2 locale-switcher form (line 32) — copy the markup, swap buttons for anchors, add the third option

**Test scenarios:**
- Happy path: `_pick_text(post, "original")` returns `(post["text"], False)` regardless of `post["text_en"]` / `post["text_zh_cn"]` values.
- Happy path: template renders 3 anchors (EN, 中文, Original) in the locale switcher.
- Happy path: GET `/original/grid` returns a page where every post text matches the source `text` column.
- Edge case: A post with `text="海螺 AI 发布"` (Chinese source, no translation) renders as "海螺 AI 发布" in all three locales (original shows it verbatim; en + zh-CN show it too because translations are NULL and the fallback is source).
- Edge case: A post with `text="海螺 AI 发布"`, `text_en="Hailuo AI released"`, `text_zh_cn=NULL` renders as "海螺 AI 发布" in `original` + `zh-CN`, and "Hailuo AI released" in `en`.
- Error path: locale "src" (alias) resolves to "original" via the case-insensitive normalization already in `normalize_locale`.

**Verification:** The toggle visibly switches between three states (English, Chinese, original) in the live dashboard. Post text in `original` mode is byte-identical to the `text` column in the DB (verified by a checksum test).

- [ ] **Unit 3: JS-side string localization + JS string-passing convention**

**Goal:** Every user-visible string in JS (`dashboard.js`, `trend-chart.js`) and in Jinja templates (treemap polarity legend, "window:" label, etc.) renders in the active locale. Strings are passed via `data-*` attributes on `<body>` or `<script type="application/json">` blocks.

**Requirements:** R4

**Dependencies:** Unit 2 (locale resolution must work end-to-end first)

**Files:**
- Modify: `x-monitoring/x_monitor/templates/grid.html.j2` — add `<body data-locale="{{ active_locale }}">` and `<script type="application/json" id="locale-strings">{...}</script>` block populated by Jinja with all dashboard.js strings in the active locale
- Modify: `x-monitoring/x_monitor/templates/treemap.html.j2` — same: `<body data-locale="...">` + locale-strings JSON
- Modify: `x-monitoring/x_monitor/templates/model_detail.html.j2` — same
- Modify: `x-monitoring/x_monitor/static/dashboard.js` — read `document.body.dataset.locale` and the `#locale-strings` JSON; replace hardcoded English with `localeStrings[key] || key`
- Modify: `x-monitoring/x_monitor/static/trend-chart.js` — same pattern for the chart tooltip label fallback
- Modify: `x-monitoring/x_monitor/templates/treemap.html.j2` — replace hardcoded "criticism rising", "flat", "praise rising", "went dark", "no data" with locale-aware Jinja variables
- Test: `x-monitoring/tests/test_dashboard_locale_routing.py` (extend) + new `x-monitoring/tests/test_locale_strings.py`

**Approach:**
- Each template emits a `<script type="application/json" id="locale-strings">` block right before `</body>`. The JSON has keys for every JS-rendered string in the active locale. The block is `display:none` (script tags aren't rendered), JS parses it on DOMContentLoaded.
- New helper `x_monitor/locale_strings.py` provides `get_locale_strings(locale: str) -> dict[str, str]` that loads the strings from a per-locale YAML file in `x_monitor/locale_strings/<locale>.yaml`. The YAML files are committed to the repo. Three files: `en.yaml`, `zh_cn.yaml`, `original.yaml` (which is identical to `en.yaml`).
- Each template calls `get_locale_strings(active_locale)` and passes the dict to Jinja, which `tojson`s it into the script block.
- For template-side strings (treemap polarity legend), Jinja variables replace the hardcoded English. The polarity legend strings are 5 short phrases — they're declared in `locale_strings.py` (or in a sibling module if they grow) and rendered via `{{ _('criticism_rising') }}`-style Jinja globals.

**Patterns to follow:**
- The rebased branch's `data-signal-labels` JSON attribute pattern (line 7 of `_model_card.html.j2`) — same idea, applied to all JS strings
- Flask's `gettext` / `flask-babel` is the canonical pattern for template-side i18n; we're not introducing that dependency in this plan (the YAML approach is simpler and the strings are small), but the convention of `_('key')` Jinja globals is reused

**Test scenarios:**
- Happy path: `get_locale_strings("en")["last_updated_never"] == "last updated: never"`.
- Happy path: `get_locale_strings("zh_cn")["last_updated_never"] == "最后更新：从未"` (or similar).
- Happy path: `get_locale_strings("original")` matches `en` (since `original` is source-language display).
- Edge case: A locale-strings key missing from a YAML file → log a warning, fall back to English. Never crash.
- Integration: GET `/zh-CN/grid` returns HTML whose `<script id="locale-strings">` JSON contains Chinese values; a JS-side test (via Selenium or a simple HTML parse) verifies the dashboard.js reads the Chinese values.

**Verification:** Manual: open `/zh-CN/grid`, inspect the page source, confirm the `locale-strings` JSON contains Chinese values for "last updated" and "polling every". Manual: open `/zh-CN/grid` in a browser, confirm the "last updated: never" placeholder reads as Chinese in the JS-set DOM (i.e. JS successfully read the locale-strings JSON).

- [ ] **Unit 4: Translation backfill CLI + activation**

**Goal:** An operator-initiated `x-monitor translate --backfill` runs Haiku 4.5 over the existing 4,683 posts that lack translations, populating `text_en` and `text_zh_cn`. After backfill, toggling to `zh-CN` or `en` on a historical post shows the translated text.

**Requirements:** R5

**Dependencies:** Unit 2 (the `original` locale handling changes `_pick_text`'s signature/fallback chain slightly; backfill output should be compatible with the new contract)

**Files:**
- Modify: `x-monitoring/x_monitor/__main__.py::cmd_translate` — add `--backfill` mode flag (vs the existing `--dry-run` / `--limit N` flags)
- Modify: `x-monitoring/x_monitor/store.py` — add `posts_missing_translation(locale: str, limit: int | None) -> list[PostRow]` helper that filters `posts` by `text_<locale> IS NULL`
- Modify: `x-monitoring/x_monitor/store.py` — add `bulk_update_translations(rows: list[dict])` that batch-updates `text_en` / `text_zh_cn` for a list of `tweet_id`s
- Modify: `x-monitoring/x_monitor/translator.py::translate_batch` — extend the existing function to handle the post-text case (it already does; confirm the `noop_*` flags handle the source-equals-target case correctly)
- Test: `x-monitoring/tests/test_translator_backfill.py`

**Approach:**
- The backfill runs in batches of 20 posts (matching the existing translator pipeline's `_TRANSLATION_BATCH_SIZE`). Each batch is one Haiku call. Logs progress: `[backfill] translated 20/4683 (en=20, zh_cn=20)`.
- Idempotent: posts where both `text_en` and `text_zh_cn` are non-NULL are skipped. Posts where only one is populated are translated for the missing locale.
- Bound flags: `--limit N` caps the total posts processed; `--locale en|zh_cn|both` scopes which locales to fill. Default: `--locale both`.
- The CLI is operator-only (`x-monitor translate --backfill`); it is NOT part of the daily harvest loop. The daily harvest continues to translate new posts inline (already specced in the origin plan).
- After backfill, the DB shows a non-zero count of translated posts; toggling to `zh-CN` shows the Chinese translation for English posts (and vice versa). Original Chinese posts still show Chinese in all three locales (the `noop_zh_cn` flag means translation was skipped).

**Patterns to follow:**
- `x-monitoring/x_monitor/translator.py::translate_batch` (existing) — reuse for the per-batch Haiku call
- `x-monitoring/x_monitor/translator.py::_call_with_retry` — reuse for retry logic
- `x-monitoring/x_monitor/store.py::bulk_update_translations` — already exists on the rebased branch (per R10 of origin plan); verify signature

**Test scenarios:**
- Happy path: `posts_missing_translation("en", limit=10)` returns the first 10 posts where `text_en IS NULL`.
- Happy path: `bulk_update_translations(rows)` updates the rows and subsequent reads show the new values.
- Happy path: `cmd_translate --backfill --limit 20 --locale en` translates 20 posts; the next `posts_missing_translation("en", limit=20)` returns posts 21+ (the first 20 are now populated).
- Edge case: `--backfill --locale both` on a DB with 0 translations translates all 4,683 posts (slow; logged batch-by-batch).
- Edge case: A post where `text="M3.0 is the latest"` and source language is `en` → `text_en="M3.0 is the latest"` (noop) and `text_zh_cn="M3.0 是最新版本"` (translated). Verify both via DB query.
- Error path: Haiku API call fails for a batch → batch is retried per `_call_with_retry`; if all retries fail, the batch is logged and skipped; backfill continues with the next batch.

**Verification:** Run `x-monitor translate --backfill --limit 100` against the production DB; verify that 100 posts now have `text_en` or `text_zh_cn` populated. Manually toggle to `zh-CN` on a few of those posts in the live dashboard; confirm the rendered text matches the `text_zh_cn` column value.

## System-Wide Impact

- **Interaction graph:** The locale toggle (topbar 3-anchor) is the entry point for all i18n flows. Clicking EN → navigates to `/en/<same-path>` → blueprint handler resolves `active_locale="en"` → every Jinja template + JS reads `active_locale` or `data-locale` → renders accordingly. The htmx poller preserves locale because the page URL carries the prefix.
- **Error propagation:** A missing translation falls back to source text + `(source)` badge in the template. A missing locale-strings key falls back to English + log warning (never crashes). An unsupported locale prefix (e.g. `/fr/grid`) returns 404 (or 302 to `/en/grid` — implementation decision).
- **State lifecycle risks:** The `locale` cookie is set when the user clicks a toggle anchor. Subsequent clicks update the cookie. Cookie `Max-Age` is 1 year (existing). The cookie survives across server restarts (it's in the browser). The backfill CLI is operator-initiated and resumable; partial runs don't leave inconsistent state because the upsert is per-row.
- **API surface parity:** The `/api/grid.html` and `/api/treemap.html` endpoints stay at root (locale-agnostic); the cookie drives locale resolution. The `/api/set_locale` POST endpoint is deprecated in favor of GET navigation; old clients get a 302 redirect. External consumers (if any) of the JSON API (`/api/treemap.json`) are unaffected by URL-prefix changes.
- **Integration coverage:** The htmx + cookie + path-prefix interaction is the most fragile integration point. Specifically: when the page URL is `/en/grid` and htmx polls `/api/grid.html`, the cookie still wins for locale resolution (since the API is at root). This works correctly because the cookie is set by the page-rendering handler before the JS poll fires.
- **Unchanged invariants:** `posts.text` is never modified (always the source). The translator's idempotency contract (noop for source-equals-target) is preserved. The 30s polling interval is preserved. The existing `?locale=` query param is dropped (was a workaround for the missing path-prefix).

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migration renumbering at rebase breaks rebased branch | Med | Med | Renumber both the migration file AND test imports; cross-check `_migrations` ledger in the rebase; run `pytest tests/test_migration_*.py` after rebasing |
| htmx polling breaks under path-prefix routing | Med | High | Unit 1 tests explicitly cover `hx-get` resolution; integration test simulates the live polling cycle |
| Backfill cost overruns the $47 estimate (Haiku pricing) | Low | Low | Bounded by `--limit`; log cost per batch; idempotent so re-running doesn't double-charge |
| `original` locale breaks some downstream consumer | Low | Med | `_pick_text` returns `(text, False)` for `original`; downstream consumers that check `is_translated` already handle `False` |
| Cookie `path` mismatch (cookie set at `/`, accessed at `/en/`) | Low | Low | Cookies default to `path="/"`; the explicit `set_cookie(..., path="/")` is preserved |
| Path-prefix breaks external links to `/grid` | Med | Med | The 302 redirect at unprefixed paths catches external links; the cookie persists the locale; SEO impact is "one redirect per first click" |
| Locales added later (Japanese/Korean) require schema work | Low | Low | Out of scope per the origin plan's R14. When added, only `locale_strings/<locale>.yaml` + `SUPPORTED_LOCALES` + migration 010 (more locale columns) are needed |

## Documentation / Operational Notes

- **Schema doc update:** `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md` already documents the i18n tables from the rebased branch. No new schema changes in this plan (no new tables or columns). The doc's "ER overview" section may need a small update to note that `original` is a third locale option (not a column).
- **Reference doc:** `docs/reference/x-monitor-locale-architecture.md` (new, ~200 lines) — explain the path-prefix routing, the locale resolution priority, the cookie persistence, the JS string-passing convention. This is a new doc, lives in `docs/reference/`.
- **Plan update:** Mark this plan `status: completed` once the four units ship.
- **Operator runbook:** Document the backfill CLI in `x-monitoring/docs/runbook.md` (or a new file) — what flags to use, expected duration, how to monitor progress.
- **Post-deploy monitoring:** Track `text_en IS NULL` and `text_zh_cn IS NULL` counts over time. Both should drop to near-zero for active brands after backfill. The `translation_stats` table (existing on rebased branch) tracks per-cycle translation counts.

## Sources & References

- **Origin document:** [docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md](2026-06-17-001-refactor-two-call-wide-net-translation-plan.md) — prior plan; R10's URL decision is superseded by this plan
- **Prior i18n branch:** `feat/i18n-locale-columns-rebased` — commits `ec70c60`, `d4d0c07`, `6aecbc7`, `69d792d`, `c89b99c`, `2537761`
- **Related code:**
  - `x-monitoring/x_monitor/dashboard.py` — locale resolution, route registration, i18n wiring
  - `x-monitoring/x_monitor/templates/grid.html.j2`, `treemap.html.j2`, `model_detail.html.j2` — topbar switcher + JS-loaded strings
  - `x-monitoring/x_monitor/static/dashboard.js`, `trend-chart.js` — JS-side hardcoded strings
  - `x-monitoring/x_monitor/store.py` — `_pick_i18n_text`, `_pick_enum_label`, FK helpers
  - `x-monitoring/x_monitor/translator.py` — `translate_batch`, `_call_with_retry`
  - `x-monitoring/x_monitor/__main__.py::cmd_translate` — translation CLI entry point
- **Related plans:**
  - [2026-06-18-195234-refactor-company-brand-account-model-plan.md](2026-06-18-195234-refactor-company-brand-account-model-plan.md) — brand/company split that underlies `_load_brand_display_names`
  - [2026-06-17-002-feat-finviz-treemap-front-page-plan.md](2026-06-17-002-feat-finviz-treemap-front-page-plan.md) — treemap front page that this plan extends with locale strings
- **External references:**
  - [Flask blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) — idiomatic per-prefix routing
  - [Next.js i18n routing](https://nextjs.org/docs/app/building-your-application/routing/internationalization) — `/[locale]/path` convention reference (not used directly, but URL pattern matches)
  - [htmx hx-get reference](https://htmx.org/attributes/hx-get/) — relative-URL resolution semantics
