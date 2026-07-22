---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
plan_depth: lightweight
created: 2026-07-22
---

## Product Contract

### Summary

Add a `lang_detected` filter group to the control panel — 13 checkboxes (11 individual languages at ≥20 posts, "undetected" for null, "other" for the tail), ordered by post frequency. Follows the existing filter group pattern end-to-end.

### Problem Frame

The control panel has no way to filter by the language of a post (`lang_detected`). A user examining English-only discourse or non-English coverage has no mechanism to narrow the chart or feed. The `lang_detected` field is already denormalized onto every post by the existing denormalization pipeline — it just isn't exposed in any filter.

### Requirements

- **R1:** 11 individual language checkboxes for languages with ≥20 posts (en, zh-hans, ja, es, tr, fr, pt, ko, id, ar, pl), ordered by descending frequency.
- **R2:** One "undetected" checkbox for posts where `lang_detected` is null.
- **R3:** One "other" checkbox for the remaining 21 languages below the 20-post cutoff.
- **R4:** All checkboxes checked by default (`__all__` sentinel).
- **R5:** "Undetected" uses asymmetric semantics: null-`lang_detected` posts pass only when "undetected" is explicitly checked (mirrors the role "other" bucket). Without this, checking only "en" would pass ~19K posts (3.7K en + 15.6K null), defeating the filter.
- **R6:** The filter narrows both the home chart and the feed.

### Scope Boundaries

**In scope:** constant definition, `_post_matches_filter` predicate branch, template section, route template-kwarg wiring, unit tests, one playwright verification check.

**Deferred to Follow-Up Work:** None.

---

## Planning Contract

### Key Technical Decisions

- **Mirror role's asymmetric "other" semantics for null.** The other axes (discourse, post_types, nationalism) treat null as "no opinion" — they pass any non-empty filter. `lang_detected` cannot do this because 15,613 of 19,908 posts have null lang_detected; "no opinion" would make individual language filtering useless. Null posts become their own "undetected" bucket, like role's synthetic "other" bucket.
- **Cutoff at ≥20 posts, not statistical.** pl at 20 posts is the last double-digit count; zh-hant at 12 is a natural drop. The breakpoint is a planning-time decision (not deferred) because it determines the constant definition and template shape.
- **Follow the existing filter group pattern exactly** — constant tuple, `_post_matches_filter` branch, template `for` loop with `data-pw-filter-group="lang"`, route kwargs. No new abstractions.

---

## Implementation Units

### U1. Add `_DASHBOARD_LANG_FILTER_KEYS` constant

**Goal:** Define the canonical set of language filter checkboxes.

**Requirements:** R1, R2, R3

**Dependencies:** None

**Files:**
- `x_monitor/dashboard.py` — add constant

**Approach:** Add after the existing `_DASHBOARD_ROLE_FILTER_KEYS` block (line ~232). The tuple carries 13 keys in display order: `en`, `zh-hans`, `ja`, `es`, `tr`, `fr`, `pt`, `ko`, `id`, `ar`, `pl`, `undetected`, `other`. Comment documents the ≥20 cutoff and the asymmetric semantics for "undetected".

**Patterns to follow:** `_DASHBOARD_ROLE_FILTER_KEYS` definition (lines 226-232).

**Test scenarios:**
- Constant has 13 entries.
- "undetected" and "other" are present.
- Keys are in descending-frequency order.

**Verification:** Import the constant in the test; assert length and membership.

---

### U2. Add `lang` branch to `_post_matches_filter`

**Goal:** `lang_detected` filter checkboxes actually narrow posts.

**Requirements:** R4, R5, R6

**Dependencies:** U1

**Files:**
- `x_monitor/dashboard.py` — modify `_post_matches_filter`
- `x_monitor/static/pw-filter-store.js` — add `lang` to `defaultFilters()` return dict and the collapse-processing array (line ~98)
- `x_monitor/_home_routes.py` — add `'lang'` to the per-param parsing tuple (line ~72, the query-string fallback path)
- `tests/test_home_chart.py` — add lang filter tests

**Approach:** Add a branch after the existing nationalism loop. Mirror the role branch's asymmetric structure:

```python
# lang_detected filter (asymmetric: null posts treated as "undetected" bucket)
lang = filters.get("lang")
if lang is not None and lang != "__all__":
    if not lang:
        return False
    post_lang = post.get("lang_detected")
    if post_lang is None:
        if "undetected" not in lang:
            return False
    elif post_lang in _DASHBOARD_LANG_FILTER_KEYS:
        if post_lang not in lang:
            # Check the "other" bucket as a fallback.
            if "other" not in lang:
                return False
    else:
        # Unknown language (below cutoff): passes only when "other" is active.
        if "other" not in lang:
            return False
```

**Patterns to follow:** Role predicate branch (lines ~1118-1132).

**Test scenarios:**
- `test_filter_lang_en_only_passes_en_post` — en in active set, post with lang_detected="en" passes.
- `test_filter_lang_en_only_blocks_ja_post` — only en active, post with lang_detected="ja" blocked.
- `test_filter_lang_null_blocked_when_undetected_off` — null lang_detected blocked when "undetected" unchecked.
- `test_filter_lang_null_passes_when_undetected_on` — null lang_detected passes when "undetected" checked.
- `test_filter_lang_tail_language_passes_via_other` — post with lang_detected="th" (below cutoff) passes when "other" checked.
- `test_filter_lang_tail_language_blocked_when_other_off` — blocked when "other" unchecked.
- `test_filter_lang_all_default_passes_everything` — `__all__` sentinel passes all posts.
- `test_filter_lang_empty_list_blocks_all` — `[]` blocks everything.

**Verification:** Run `pytest tests/test_home_chart.py -v -k lang`. All 8 tests pass.

---

### U3. Add lang filter section to template

**Goal:** Render 13 language checkboxes in the control panel.

**Requirements:** R1, R2, R3, R4

**Dependencies:** U1, U2

**Files:**
- `x_monitor/dashboard.py` — add `_DASHBOARD_LANG_DISPLAY_NAMES` dict
- `x_monitor/templates/home.html.j2` — add control group
- `x_monitor/templates/brand_home.html.j2` — same control group
- `x_monitor/_home_routes.py` — pass `lang_keys` and `lang_display_names` template kwargs (×2 route handlers)

**Approach:** Add a new `<div class="control-group">` block after the `account.role` group. Loop over `lang_keys` with `data-pw-filter-group="lang"`. Unlike the existing pattern (which renders raw keys as-is), lang codes need display names: define a `_DASHBOARD_LANG_DISPLAY_NAMES` dict in `dashboard.py` mapping each code to a human-readable label (`zh-hans` → `简体中文`, `ja` → `日本語`, `es` → `Español`, `tr` → `Türkçe`, `fr` → `Français`, `pt` → `Português`, `ko` → `한국어`, `id` → `Bahasa Indonesia`, `ar` → `العربية`, `pl` → `Polski`, `en` → `English`, `undetected` → `undetected`, `other` → `other`). Pass this dict to the template and reference it in the label. All checkboxes `checked` by default.

Add `lang_keys=_DASHBOARD_LANG_FILTER_KEYS` to the two `render_template` calls in `_home_routes.py` (the multi-brand chart route and the single-brand chart route — lines ~398-403 and ~473-478).

**Patterns to follow:** Discourse or role control group in `home.html.j2` (lines ~72-82).

**Test scenarios:**
- All 13 checkboxes render with `data-pw-filter-group="lang"`.
- All checkboxes are checked by default.
- Human-readable labels for the 11 individual languages.

**Verification:** `grep -c 'data-pw-filter-group="lang"'` on both `home.html.j2` and `brand_home.html.j2` returns 13 each; all checkboxes have the `checked` attribute.

---

### U4. Add playwright verification check

**Goal:** End-to-end browser verification that the lang filter narrows the chart.

**Requirements:** R6

**Dependencies:** U3

**Files:**
- `.harness/verify-dashboard.js` — add `langFilter` check; update `filterSnapshot` key list to include `'lang'`

**Approach:** Add a new check function `langFilter`. Set up: uncheck all lang checkboxes except "en". Verify the chart payload has fewer total posts than the default-all. Then re-check "ja" and verify total increases.

**Test scenarios:**
- 13 lang checkboxes exist, all checked by default.
- Unchecking all except "en" drops total post count.
- Adding "ja" back increases the count.

**Verification:** Run `BASE_URL=... node verify-dashboard.js --only=langFilter`.

---

## Verification Contract

1. `pytest tests/test_home_chart.py -v -k lang` — 8 new tests pass.
2. `pytest tests/ --basetemp=$HOME/pytest-basetemp-lang -k "not test_relevance and not test_brand_search_terms_hybrid and not test_yaml_db_parity"` — existing tests not regressed.
3. `BASE_URL=http://127.0.0.1:5050/ node verify-dashboard.js` — 8/8 checks pass (7 existing + langFilter).

## Definition of Done

- [ ] 13 language checkboxes appear in the control panel.
- [ ] Checking/unchecking individual languages narrows the chart and feed correctly.
- [ ] Null-`lang_detected` posts are filtered by the "undetected" checkbox (asymmetric).
- [ ] Below-cutoff languages are filtered by the "other" checkbox.
- [ ] All 8 predicate tests pass.
- [ ] Playwright suite passes with no regressions.
