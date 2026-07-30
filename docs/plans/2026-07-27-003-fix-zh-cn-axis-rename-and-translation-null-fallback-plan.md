---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
plan_depth: standard
created: 2026-07-27
title: zh_CN axis label rename (中国民族主义 / 美国民族主义) + 翻译 column NULL-without-fallback
type: fix
---

## Goal Capsule

- **Objective:** Two related fixes to the zh_CN dashboard surface:
  1. Rename the two nationalism axis labels in the 分类 column from the current field-name strings (`zh_cn:` / `en:`) to the Chinese axis names (`中国民族主义:` / `美国民族主义:`), matching the chrome filter panel labels that already exist as `us_nationalism` → `美国民族主义` / `cn_nationalism` → `中国民族主义` in the catalog.
  2. Make the 翻译 column render the literal string `NULL` (under all locales) when no translated text exists for the post — no fallback to the source `text`. Currently `_pick_text` falls back to `text` when `text_en` / `text_zh_cn` is empty, which makes missing translations visually indistinguishable from real ones and hides data-correctness gaps (the 215 legacy zh-hans posts that have `text_zh_cn IS NULL` look fine on the dashboard even though they're broken).
- **Authority hierarchy:** Plan body is binding. Reuse existing label resolution / locale-to-column mapping / template rendering patterns; do not introduce new tables, pipelines, or display libraries. Verification runs against the production Render deployment (`https://pushinweight-web.onrender.com`, Postgres `dpg-d9go1njeo5us73cg5u00-a`).
- **Execution profile:** Sequential — U1 (axis rename template/JS/po) and U2 (translation NULL fallback) wire through different surfaces but both are required before U3 (Playwright) can verify them, and U4 (regression net) covers both. U3 is the gate that catches silent drift on either.
- **Stop conditions:** Do not introduce a local dev DB, SSH tunnel, or `.venv/bin/python` workflow. Do not modify `core/management/commands/seed_i18n_labels.py` — the existing translations are reused as-is. Do not change `_pick_text` callers outside the wire shape. Do not introduce a "NULL" localization key — `NULL` is a programmer-grade signal intentionally, not a translated string. Do not add a CLI flag, env var, or settings switch for either behavior — both are unconditional.
- **Tail ownership:** Local session — the user runs `ce-work` or applies commits directly; the prod deploy via Render auto-deploys on push to `main` and triggers `build.sh` (which runs `compilemessages`).

## Product Contract

### Summary

Rename the two nationalism axis labels in the 分类 column to Chinese axis names that match the existing chrome i18n catalog entries (`中国民族主义` / `美国民族主义`), and change the 翻译 column to render literal `NULL` when no translated text exists for a post (under all locales — zh_CN, en, original). EN locale classification values stay as raw DB keys; the 原文 column stays as the source `text` for all locales (existing behavior unchanged from U1 of plan `2026-07-27-001`).

### Problem Frame

Plan `2026-07-27-001-feat-zh-cn-classification-labels-plan.md` shipped axis labels `zh_cn:` / `en:` for the 分类 column under both locales. User feedback 2026-07-27: those labels are confusing because (a) they look like language codes (the field is *country nationalism level*, not language), and (b) the chrome filter panel already uses the Chinese axis names `中国民族主义:` / `美国民族主义:` — so the 分类 column and the filter panel disagree on what to call the same axis. The plan's KTD4 noted "field-name consistency wins for the rename," but user verification reveals the axis labels should be the Chinese axis names instead.

Separately, the 翻译 column under zh_CN locale currently falls back to the source `text` when `text_zh_cn IS NULL`. For posts that *are* in Chinese (`lang_detected = zh-hans`), `_pick_text` returns `text` (which is Chinese) — fine. But for posts that *aren't* translated yet (the 215 legacy posts in prod from before fix `02e1f6c`, plus any future post that lands before the LLM classifies it), the 翻译 column shows the English source text — making missing translations look identical to real ones and hiding the data gap. The user wants the literal string `NULL` instead, so the dashboard makes the gap visible at a glance.

The repo already has the right infrastructure for both fixes: `seed_i18n_labels.py` already populates `中国民族主义` / `美国民族主义` for `cn_nationalism` / `us_nationalism` keys (visible in the chrome filter panel), and the JS feed builder + template already handle arbitrary label values per classification value. The fix just re-points the axis labels and removes the fallback in `_pick_text`.

### Requirements

**Axis label rename (zh_CN + EN locales)**

- R1. Under zh_CN, the 分类 column shows `中国民族主义:` (was `zh_cn:`) and `美国民族主义:` (was `en:`) as the axis labels for the two nationalism rows.
- R2. Under EN, the same labels — `中国民族主义:` / `美国民族主义:` — appear (axis names are field-name identifiers, not localized strings; per KTD8 of plan `2026-07-27-001`, the rename is field-name consistency, not translation).
- R3. The chrome filter panel labels (already `中国民族主义` / `美国民族主义` for the `cn_nationalism` / `us_nationalism` filter keys) match the 分类 column axis labels after this change.

**翻译 column NULL-without-fallback**

- R4. Under zh_CN, when `posts.text_zh_cn IS NULL`, the 翻译 column renders the literal string `NULL` (no fallback to `posts.text`).
- R5. Under EN, when `posts.text_en IS NULL`, the 翻译 column renders the literal string `NULL` (no fallback to `posts.text`).
- R6. Under `original`, when `posts.text IS NULL`, the 翻译 column renders the literal string `NULL` (the source IS the original; if source is empty, NULL).
- R7. When the locale-appropriate translation IS populated, the 翻译 column renders it as today (no behavior change for the hit branch).
- R8. The wire field `text_translated` is `null` (Python/JSON null, not the string `"NULL"`) when no translation exists; the rendering layer converts the JSON null into the display string `NULL`.

**Verification**

- R9. Playwright drives the production dashboard under zh_CN, en, and original locales and asserts:
  - 分类 column shows `中国民族主义:` / `美国民族主义:` as the axis labels in BOTH zh_CN and EN locales.
  - 分类 column does NOT show `zh_cn:` / `en:` anywhere.
  - For posts where `text_zh_cn` (under zh_CN) / `text_en` (under en) / `text` (under original) is NULL, the 翻译 column renders the literal `NULL`.
  - For posts where the translation is populated, the 翻译 column renders the translation as today.
- R10. Unit tests cover the new `_pick_translation` helper for hit + miss + null-source cases — run against prod via `render jobs create pushinweight-web --start-command "python manage.py test tests.test_translation_null_fallback"`.

**Out of scope (explicit)**

- Renaming the model fields `cn_nationalism` / `us_nationalism` — out of scope; only the visible label text changes.
- Renaming the filter control-panel tab keys (`us_nationalism` / `cn_nationalism`) — these are filter-API identifiers and stay as-is per the parallel naming convention in plan `2026-07-24-003`.
- Backfilling `posts.text_zh_cn` / `posts.text_en` for legacy rows — handled by the fix in commit `02e1f6c` going forward; retroactive cleanup is out of scope.
- Translating the word "NULL" itself — `NULL` is a programmer-grade signal intentionally; do not add `{% trans "NULL" %}`.
- A CLI flag, env var, or settings switch for either behavior — both changes are unconditional.

### Acceptance Examples

- AE1. **zh_CN, post with all four classification values populated and `text_zh_cn` populated.** Render row, assert axis labels are `中国民族主义:` / `美国民族主义:` (NOT `zh_cn:` / `en:`), assert 翻译 column shows the Chinese translation. Covers R1, R7.
- AE2. **zh_CN, post with `text_zh_cn IS NULL`.** Assert 翻译 column renders the literal string `NULL` (NOT the English source text). Covers R4, R8.
- AE3. **zh_CN, post with `text IS NULL` AND `text_zh_cn IS NULL`.** Assert 翻译 column renders `NULL` (no crash, no fallback to empty string). Covers R4 edge case.
- AE4. **EN locale, post with `text_en IS NULL`.** Assert 翻译 column renders `NULL` (NOT the English source text — the source IS English so the temptation is to fall back, but the rule is unconditional). Covers R5, R8.
- AE5. **Original locale, post with `text IS NULL`.** Assert 翻译 column renders `NULL`. Covers R6.
- AE6. **zh_CN locale, axis label disambiguation.** Render row, assert NO occurrence of `zh_cn:` or `en:` anywhere in the 分类 column. Covers R1, R2.
- AE7. **Filter panel axis labels match 分类 column axis labels.** Open the dashboard under zh_CN, assert filter panel shows `中国民族主义` / `美国民族主义` (existing chrome i18n) and the 分类 column shows the same labels (no `zh_cn:` / `en:`). Covers R3.

### Scope Boundaries

- **In scope:** Axis label rename in `_feed_initial.html`, `pw-feed.js`, `locale/zh_Hans/LC_MESSAGES/django.po`, plus regression-net updates. `_pick_text` rewrite to drop the fallback. Render layer (template + JS) emits literal `NULL` when `text_translated` is JSON null. New unit tests + Playwright check.
- **Deferred for later:** Retroactive `text_zh_cn` backfill for the 215 legacy prod posts (fix `02e1f6c` only handles future ingestion; legacy rows will keep showing `NULL` until the LLM classifier pipeline re-processes them).
- **Outside this product's identity:** Translating the literal `NULL` string — programmer-grade signal stays as-is.

## Planning Contract

### Key Technical Decisions

- KTD1. **Axis labels are field-name identifiers, not localized strings** — per KTD8 of plan `2026-07-27-001`, the rename is about consistency between the 分类 column and the chrome filter panel. The axis labels are the same under both zh_CN and EN: `中国民族主义:` and `美国民族主义:`. Update the .po file so under zh_CN, msgid `zh_cn:` → msgid `中国民族主义:` (msgstr `中国民族主义:`), and msgid `en:` → msgid `美国民族主义:` (msgstr `美国民族主义:`). The msgid IS the displayed value under both locales, same pattern as the previous `zh_cn:` rename. Alternative: drop the trailing colon from the msgid and add a separate CSS class — rejected because the trailing colon is consistent with `类型:` / `话语:` / `情感:` already in the catalog.
- KTD2. **`_pick_text` keeps returning `None` for missing translations (current behavior) but stops falling back to source `text`.** Rename to `_pick_translation(post, locale) -> str | None` for clarity, return `None` when no locale-appropriate column has data. The wire field `text_translated` already accepts `None` (verified by inspecting `_post_to_wire` and `_serialize_feed_row`). The render layer converts `None` → literal `NULL`. Alternative: keep `_pick_text` and have it return `("NULL", False)` — rejected because the wire shape should carry semantic None, not a sentinel string; sentinel-in-wire makes the JS / template branch on a string that conflicts with the column's natural null state.
- KTD3. **NULL rendering happens in the template and JS builder, not in the wire shape.** The wire carries `text_translated: None` (Python None → JSON null). The template emits `{% if row.text_translated %}{{ row.text_translated }}{% else %}NULL{% endif %}` and the JS builder emits `escapeHtml(row.text_translated || "NULL")` (the `||` falls through on `null`/`undefined`/empty string). Alternative: emit `"NULL"` directly in the view — rejected because it conflates the data state with the display concern; a future i18n'd "untranslated" string would require touching the view again.
- KTD4. **Under `original` locale, `_pick_translation` returns the source `text` only if it's populated** (current `_pick_text` behavior under `__source__` column → returns `text` if present, None if not). So under `original`, the 翻译 column shows the source text when present (R7 hit branch) and `NULL` when source is empty (R6 miss branch). This is consistent with the "no fallback" rule — under `original`, the source IS the locale-appropriate translation, so there's no separate fallback to suppress.
- KTD5. **Axis label rename is single-touch per file: one identifier swap in the template, one in the JS builder, one .po entry per msgid.** Per KTD4, the msgid IS the displayed value, so the rename is a clean replace with no translation table updates. No string-table migration; no second-language support work; no risk of msgid/msgstr drift. Alternative: add a separate msgstr under zh_CN like `中国民族主义:` — explicitly rejected per KTD1 (axis labels are field-name identifiers, not localized).
- KTD6. **Regression net covers both fixes via one updated test class.** Update `tests/test_i18n_catalog_pinned.py` `CLASSIFICATION_LABELS_PIN` so the pinned msgstrs are `中国民族主义:` and `美国民族主义:` (was `zh_cn:` and `en:`). Add a new test class `TestTranslationNullFallback` to `tests/test_classification_labels.py` (or new file `tests/test_translation_null_fallback.py`) that pins `_pick_translation` behavior across hit/miss/null-source cases. Both pin tests run against prod via the same render jobs pattern.
- KTD7. **Existing Playwright check extends with new assertions.** The U3 check from plan `2026-07-27-001` (`feed_zh_cn_classification_labels`) currently asserts `zh_cn:` / `en:` are present. After this plan, those assertions invert: assert `zh_cn:` / `en:` are ABSENT and `中国民族主义:` / `美国民族主义:` are PRESENT. Add new AE2 / AE4 / AE5 assertions for the NULL rendering by hitting a known-missing translation (any of the 215 legacy prod posts, e.g. tweet_id `2081578563816554708` which has `lang_detected='zh-hans'` AND `text_zh_cn IS NULL`).
- KTD8. **No localization for "NULL".** KTD3's render-layer branch emits the literal English `NULL` regardless of locale. Alternative: localize as `未翻译` (zh) / `Untranslated` (en) — rejected because (a) the user asked for the literal string, (b) localizing creates a regression net for two more strings we don't otherwise need, and (c) "NULL" is the same in both languages for technical users, who are the audience for this column anyway (the dashboard is a debugging tool, not a customer-facing product).
- KTD9. **Test naming follows plan `2026-07-27-001`'s pattern.** New file `tests/test_translation_null_fallback.py` with 8-10 scenarios mirroring `tests/test_classification_labels.py`'s structure: pure-function tests for `_pick_translation` (hit / miss / null-source / all-locales), serializer tests for `text_translated IS None` wire shape, template-render test (using Django test client + `_feed_initial.html` snapshot). Regression net test in `tests/test_i18n_catalog_pinned.py` updated in place.

### High-Level Technical Design

```
                 ┌──────────────────────────────────────────────┐
                 │   Django view (prod: pushinweight-web)        │
                 │                                               │
GET /feed/  ──▶  │  _serialize_feed_row(post, locale)           │
                 │     │                                         │
                 │     ├─▶ _pick_translation(post, locale)       │
                 │     │     → text_translated: str | None        │  ← CHANGED
                 │     │       (no fallback to post.text)        │
                 │     │                                         │
                 │     └─▶ classification shape (unchanged from  │
                 │           plan 2026-07-27-001)                 │
                 └──────────────────────────────────────────────┘
                                  │
                                  │  JSON wire: text_translated may be null
                                  ▼
                 ┌──────────────────────────────────────────────┐
                 │       pw-feed.js / _feed_initial.html         │
                 │                                               │
                 │  render translation cell:                     │
                 │    {% if row.text_translated %}              │
                 │      {{ row.text_translated }}                │
                 │    {% else %}                                 │
                 │      NULL                                     │
                 │    {% endif %}                                │
                 │                                               │
                 │  render axis labels:                          │
                 │    {% trans "中国民族主义:" %}                │  ← RENAMED
                 │    {% trans "美国民族主义:" %}                │  ← RENAMED
                 └──────────────────────────────────────────────┘
```

Three wire-shape changes:

1. `text_translated` field semantics: now `str | None` where `None` means "no translation" (no longer falls back to `text`). The wire shape is backward-compatible for callers that branch on null vs string.
2. Axis label msgids in `django.po`: `zh_cn:` → `中国民族主义:`, `en:` → `美国民族主义:`. The msgstr equals the msgid under zh_CN (per KTD1, axis labels are field-name identifiers).
3. Template + JS render: `{% if row.text_translated %}` and `row.text_translated || "NULL"` convert the null wire into the literal display string.

## Implementation Units

### U1. Rename axis labels in template, JS, and .po file

**Goal:** Replace `zh_cn:` / `en:` with `中国民族主义:` / `美国民族主义:` everywhere the axis label appears. Update the regression net so a future revert fails loudly.

**Requirements:** R1, R2, R3

**Files:**

- `monitor/templates/monitor/_feed_initial.html`
- `monitor/static/pw-feed.js`
- `locale/zh_Hans/LC_MESSAGES/django.po`
- `locale/zh_Hans/LC_MESSAGES/django.mo` (re-compiled from `.po`)
- `tests/test_i18n_catalog_pinned.py` (update `CLASSIFICATION_LABELS_PIN`)
- `.harness/verify-dashboard.js` (update U3 check assertions)

**Approach:**

1. **`_feed_initial.html`:** change `{% trans "zh_cn:" %}` → `{% trans "中国民族主义:" %}` and `{% trans "en:" %}` → `{% trans "美国民族主义:" %}`. No other changes — the `cls.cn_nationalism.label` / `cls.us_nationalism.label` rendering already works for the new axis-name strings.
2. **`pw-feed.js`:** in `renderRowHtml`, change the two hardcoded axis-label strings:
   - `'<span class="cls-label">zh_cn:</span>'` → `'<span class="cls-label">中国民族主义:</span>'`
   - `'<span class="cls-label">en:</span>'` → `'<span class="cls-label">美国民族主义:</span>'`
   No other changes — the `cnKey` / `usKey` / `cnLabel` / `usLabel` variable assignments and the `data-key` attribute rendering stay as-is.
3. **`django.po`:** replace the msgid block:
   ```
   msgid "zh_cn:"
   msgstr "zh_cn:"
   
   msgid "en:"
   msgstr "en:"
   ```
   with:
   ```
   msgid "中国民族主义:"
   msgstr "中国民族主义:"
   
   msgid "美国民族主义:"
   msgstr "美国民族主义:"
   ```
   Run `compilemessages` so `django.mo` is regenerated. The build.sh on prod already runs `compilemessages` on every deploy, but local compile catches the change before push.
4. **`test_i18n_catalog_pinned.py`:** update `CLASSIFICATION_LABELS_PIN`:
   ```python
   CLASSIFICATION_LABELS_PIN: dict[str, str] = {
       "中国民族主义:": "中国民族主义:",
       "美国民族主义:": "美国民族主义:",
       "types:": "类型:",
       "discourses:": "话语:",
       "sentiments:": "情感:",
   }
   ```
   The individual `test_zh_cn_axis_label_msgid_is_msgstr` and `test_en_axis_label_msgid_is_msgstr` test methods become `test_zh_cn_axis_label_msgid_is_msgstr` (renamed or split) for the new axis labels. No other test in this file changes.
5. **`verify-dashboard.js`:** update the U3 check `feed_zh_cn_classification_labels`:
   - Change the axis-label matchers from `zh_cn:` / `en:` to `中国民族主义:` / `美国民族主义:`.
   - Add new assertions: `enAxis.cnOldSeen` / `enAxis.usOldSeen` becomes "old `zh_cn:` / `en:` axis labels NOT present under EN locale" (inverting the current logic).

**Test scenarios:**

- `test_classification_labels_pin` (updated): `gettext("中国民族主义:") == "中国民族主义:"` AND `gettext("美国民族主义:") == "美国民族主义:"` AND `gettext("zh_cn:")` raises LookupError or returns the untranslated msgid (NOT the catalog value) — pins both the new labels AND the removal of the old ones.
- `test_zh_cn_axis_label_msgid_is_msgstr` (renamed): `gettext("中国民族主义:") == "中国民族主义:"`.
- `test_en_axis_label_msgid_is_msgstr` (renamed): `gettext("美国民族主义:") == "美国民族主义:"`.
- `test_old_zh_cn_axis_label_removed` (new): `gettext("zh_cn:") != "zh_cn:"` — old label is gone from the catalog (returns the English source because there's no zh_CN translation).
- `test_old_en_axis_label_removed` (new): `gettext("en:") != "en:"` — same for the other old label.

**Verification:** `ssh fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_i18n_catalog_pinned -v 2"'` — all pin tests pass against prod test DB. If anyone reverts the .po rename, the pin test fails with `Expected: 'zh_cn:' / Got: '中国民族主义:'`.

---

### U2. Remove `_pick_text` fallback + render literal NULL for missing translations

**Goal:** `_pick_translation(post, locale) -> str | None` returns `None` (no fallback to source) when no locale-appropriate column has data. Template + JS render the literal `NULL` when `text_translated IS None`.

**Requirements:** R4, R5, R6, R7, R8

**Files:**

- `monitor/views.py` (rename `_pick_text` → `_pick_translation`, drop the fallback)
- `monitor/templates/monitor/_feed_initial.html` (add `{% if %}` branch around `row.text_translated`)
- `monitor/static/pw-feed.js` (change `row.text_translated || ''` to `row.text_translated || 'NULL'` in the 翻译 cell)
- `tests/test_translation_null_fallback.py` (new)

**Approach:**

1. **`monitor/views.py`:**
   - Rename `_pick_text` → `_pick_translation` (keep the docstring but rewrite the contract: "Returns the locale-appropriate translation, or `None` if not available.")
   - Drop the final `if translated:` → `return translated, True` branch's "fallback to text" tail. New return: when the locale-appropriate column is empty, return `(None, False)`. Under `original` locale (`column == "__source__"`), return `(None, False)` if `text` is None/empty (no fallback there either — the source IS the locale-appropriate translation under `original`).
   - Update the two callers in `_post_to_wire` (line ~428) and `_serialize_feed_row` (line ~1169) to use `_pick_translation` instead of `_pick_text`. The wire field name `text_translated` stays the same; only the value semantics change (now `str | None` instead of `str`).
   - Update `is_translated` semantics: still `True` when a real translation was found, `False` otherwise (no behavior change for the boolean).
2. **`_feed_initial.html`:**
   - Find the 翻译 cell: `<div class="cell-truncated" data-pw-cell-truncated>{{ row.text_translated|default:'' }}</div>`.
   - Replace with:
     ```jinja
     <div class="cell-truncated" data-pw-cell-truncated>
       {% if row.text_translated %}{{ row.text_translated }}{% else %}NULL{% endif %}
     </div>
     ```
   - No change to the `原文` cell — that stays as `row.text_original` from plan `2026-07-27-001`.
3. **`pw-feed.js`:**
   - Find the 翻译 cell render line: `'<div class="cell-truncated" data-pw-cell-truncated>' + escapeHtml(row.text_translated || '') + '</div>'`.
   - Replace with: `'<div class="cell-truncated" data-pw-cell-truncated>' + escapeHtml(row.text_translated || 'NULL') + '</div>'`.
   - No change to the `原文` cell.
4. **`tests/test_translation_null_fallback.py` (new):**
   - Test scenarios (see below).

**Test scenarios:**

- `test_pick_translation_zh_cn_hit` — post with `text_zh_cn="中文"`, under zh_CN locale, helper returns `"中文"` (NOT None).
- `test_pick_translation_zh_cn_miss_returns_none` — post with `text_zh_cn=None` AND `text="english"`, under zh_CN locale, helper returns `None` (NOT `"english"` — this is the key behavior change).
- `test_pick_translation_en_hit` — post with `text_en="English"`, under en locale, returns `"English"`.
- `test_pick_translation_en_miss_returns_none` — post with `text_en=None` AND `text="english"`, under en locale, returns `None` (NOT `"english"` — even though the source IS English; the rule is unconditional per KTD8).
- `test_pick_translation_original_hit` — post with `text="source"`, under original locale, returns `"source"`.
- `test_pick_translation_original_miss_returns_none` — post with `text=None` AND `text_en=None` AND `text_zh_cn=None`, under original locale, returns `None`.
- `test_pick_translation_empty_string_returns_none` — post with `text_zh_cn=""` (empty string, not None), under zh_CN locale, returns `None` (empty string is treated as missing).
- `test_serialize_feed_row_emits_null_text_translated` — full row through `_serialize_feed_row(post, "zh_cn")` with `text_zh_cn=None` AND `text="english"`; assert `wire["text_translated"] is None` (not "english").
- `test_serialize_feed_row_emits_string_text_translated` — full row through `_serialize_feed_row(post, "zh_cn")` with `text_zh_cn="中文"`; assert `wire["text_translated"] == "中文"`.

**Verification:** `ssh fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_translation_null_fallback -v 2"'` — all 9 scenarios pass against prod test DB. The miss-branch tests are the load-bearing ones — they prove the fallback is gone.

---

### U3. Extend Playwright check to cover axis rename + NULL rendering

**Goal:** The U3 check from plan `2026-07-27-001` (`feed_zh_cn_classification_labels`) now asserts the new axis labels appear, the old ones are absent, and the 翻译 column renders `NULL` for missing translations. Covers AE1-AE7.

**Requirements:** R9, R10 (the unit-test half is in U1 / U2)

**Files:**

- `.harness/verify-dashboard.js` (extend existing `feed_zh_cn_classification_labels` check)

**Approach:**

1. **Update the existing axis-label assertions** in `feed_zh_cn_classification_labels`:
   - Old: `zhcnSeen` / `enSeen` flags check for the strings `zh_cn:` / `en:`.
   - New: check for `中国民族主义:` / `美国民族主义:` presence, and add `oldZhcnSeen` / `oldEnSeen` flags that assert the OLD strings are NOT present anywhere in the rendered DOM.
2. **Add NULL-rendering assertions** for the 翻译 cell:
   - Fetch the `/feed/` JSON payload (via page.evaluate or direct fetch).
   - Pick a row where `text_translated` is null (or `text_zh_cn` is null under zh_CN locale).
   - Find the row in the rendered DOM.
   - Assert the 翻译 cell's textContent is exactly the string `"NULL"`.
   - Repeat under EN locale (using a row where `text_en` is null) and original locale (using a row where `text` is null).
3. **Add a known-missing-translation probe** for AE2 / AE4 / AE5:
   - The legacy prod post `tweet_id="2081578563816554708"` (verified 2026-07-27 to have `lang_detected='zh-hans'` AND `text_zh_cn IS NULL`) is a deterministic target. The check filters the feed rows by tweet_id and asserts the 翻译 cell renders `NULL`.

**Test scenarios:**

- `feed_zh_cn_classification_labels` (extended):
  - AE1: axis labels `中国民族主义:` / `美国民族主义:` present in zh_CN locale rows.
  - AE6 (inversion): `zh_cn:` / `en:` NOT present anywhere.
  - AE2: 翻译 cell renders `NULL` for `tweet_id=2081578563816554708` under zh_CN locale.
  - AE4: 翻译 cell renders `NULL` for the same row under EN locale (because `text_en` is also null for posts that haven't been through the LLM).
  - AE5: 翻译 cell renders `NULL` for the same row under original locale (because `text` itself is not null for that post, but the assertion needs a row with null `text` — pick another legacy post if needed; or assert "if `text_translated` is JSON null, DOM shows `NULL`" generally).

**Verification:** `SESSION_COOKIE=<value> BASE_URL=https://pushinweight-web.onrender.com node .harness/verify-dashboard.js --only=feed_zh_cn_classification_labels` — passes all 7 acceptance examples against prod. Capture a screenshot of the prod zh_CN dashboard for visual review (the 翻译 column should show `NULL` for posts without `text_zh_cn`).

---

### U4. Update regression net tests (axis labels + NULL fallback)

**Goal:** Pin the AFTER state for both fixes in `tests/test_i18n_catalog_pinned.py` (axis labels) and add a new `tests/test_translation_null_fallback.py` (NULL fallback). The two together form the regression net per `feedback_regression_net_in_every_plan.md` — fails loudly if either fix is silently reverted.

**Requirements:** R10 (unit-test half), defense-in-depth

**Files:**

- `tests/test_i18n_catalog_pinned.py` (update `CLASSIFICATION_LABELS_PIN` + per-axis-label test methods)
- `tests/test_translation_null_fallback.py` (new — 9 scenarios per U2)

**Approach:**

1. **`tests/test_i18n_catalog_pinned.py`:** update the pin dict (per U1 step 4) and the per-method test names + assertions (per U1 test scenarios). No changes to the `TestHeadersPin` / `TestFeedColumnsPin` / `TestTopbarPin` / `TestLocaleActivation` / `TestNoMsgidSilentlyLost` classes.
2. **`tests/test_translation_null_fallback.py`:** create per U2. Each scenario is a parametrized or named method that imports `_pick_translation` from `monitor.views` and runs in-process against in-memory post fixtures (no DB needed for the pure-function tests; the serializer tests need `@pytest.mark.django_db`).
3. **The `_feed_initial.html` template render check** lives in a third file or in `test_translation_null_fallback.py` as a Django test-client integration test. Use `client.force_login(user)` + `client.get("/feed/")` + `assertContains(response, "NULL")` + `assertNotContains(response, "row.text_translated")` to verify the template branch.

**Test scenarios:**

- The 4 axis-label update tests (U1).
- The 9 `_pick_translation` + serializer tests (U2).
- 1 template-render integration test: `client.get("/feed/?locale=zh_cn")` against a fixture row with `text_zh_cn=None`; assert response body contains `NULL` at the position where the 翻译 cell renders.
- 1 template-render integration test: `client.get("/feed/?locale=en")` against a fixture row with `text_en=None` AND `text="english"`; assert response body contains `NULL` (NOT `english`).

**Verification:** `ssh fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_i18n_catalog_pinned tests.test_translation_null_fallback -v 2"'` — all pin tests pass against prod test DB. Total ~30 scenarios across the two files. If anyone silently drops the `_pick_text` → `_pick_translation` rename, or reverts the NULL render, the tests fail with a clear diff.

## Verification Contract

All verification runs against the production Render deployment.

- **Prod DB label confirmation:** `ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT lang, label FROM core_china_nationalism_labels WHERE lang='\''zh-cn'\'' LIMIT 5;"'` — confirms the existing chrome labels still exist (no change to `seed_i18n_labels.py`).
- **Unit tests** (prod test DB):
  - `render jobs create pushinweight-web --start-command "python manage.py test tests.test_translation_null_fallback -v 2"` — U2's 9 scenarios pass.
  - `render jobs create pushinweight-web --start-command "python manage.py test tests.test_i18n_catalog_pinned -v 2"` — U1 + U4's pin tests pass.
  - `render jobs create pushinweight-web --start-command "python manage.py test tests.test_classification_labels -v 2"` — U1's pin from plan `2026-07-27-001` still passes (no regression).
- **i18n catalog:** `render jobs create pushinweight-web --start-command "python manage.py compilemessages && python manage.py check --deploy"` — no i18n errors after the msgid rename.
- **Playwright gate** (production):
  - `SESSION_COOKIE=<value> BASE_URL=https://pushinweight-web.onrender.com node .harness/verify-dashboard.js --only=feed_zh_cn_classification_labels` — U3's extended check passes all 7 acceptance examples against prod.
  - Full suite: `SESSION_COOKIE=<value> BASE_URL=https://pushinweight-web.onrender.com node verify-dashboard.js` — no regressions in any prior checks (window1Minute, langFilter, etc.).
- **Mint prod session cookie:** use the playwright_probe user's `last_name` (set by an inline `python -c` Render job per the U3 pattern in plan `2026-07-27-001`). Session_key is retrievable from `auth_user.last_name` column on prod via `render psql`.
- **Manual smoke:** open `https://pushinweight-web.onrender.com/` with `locale=zh_cn` cookie set in the browser. Inspect the 分类 column of any rendered row — axis labels show `中国民族主义:` / `美国民族主义:` (NOT `zh_cn:` / `en:`). Inspect the 翻译 column for any post with `text_zh_cn IS NULL` (e.g. legacy post `2081578563816554708`) — renders `NULL` (NOT the English source). Inspect the filter panel — `中国民族主义` / `美国民族主义` labels (existing chrome i18n, no change).

## Definition of Done

- U1 complete: axis labels `中国民族主义:` / `美国民族主义:` ship in `_feed_initial.html`, `pw-feed.js`, and `locale/zh_Hans/LC_MESSAGES/django.po`. `compilemessages` succeeds. All 4 pin tests pass against prod test DB.
- U2 complete: `_pick_translation` (renamed from `_pick_text`) returns `None` (no fallback) when no translation exists. Template + JS render literal `NULL` when `text_translated IS None`. All 9 scenarios in `tests/test_translation_null_fallback.py` pass against prod test DB.
- U3 complete: U3 Playwright check `feed_zh_cn_classification_labels` extended with axis-label-inversion + NULL-rendering assertions. All 7 acceptance examples (AE1-AE7) pass against `https://pushinweight-web.onrender.com`. Full `verify-dashboard.js` suite regression-clean.
- U4 complete: `tests/test_i18n_catalog_pinned.py` axis-label pins updated (4 tests). `tests/test_translation_null_fallback.py` ships with 9 + 2 = 11 scenarios. All tests pass against prod test DB. Total scenario count across both fix-related files: ~30.
- Commit messages include the line `Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]` per global CLAUDE.md rule 4.
- No new dependencies added.
- No edits to `core/management/commands/seed_i18n_labels.py` (the existing translation strings for `cn_nationalism` / `us_nationalism` are reused).
- No edits to the backfiller, classifier pipeline, or fix `02e1f6c`'s `monitor/cycle.py` lang-detected invariant.
- No local dev DB, SSH tunnel, or `.venv/bin/python` commands introduced anywhere in the plan.
- Both fixes ship as a coordinated commit pair so U3 can verify the production dashboard renders both correctly together.

## Sources & Research

- `docs/plans/2026-07-27-001-feat-zh-cn-classification-labels-plan.md` — the prior zh_CN plan that introduced the `zh_cn:` / `en:` axis labels. KTD4 / KTD8 in that plan called out the rename as field-name consistency; this plan reverses that choice per user feedback.
- `monitor/views.py` — `_pick_text` (line 196), `_post_to_wire` (line 335), `_serialize_feed_row` (line 1010). The wire shape change in U2 is a one-line behavior flip per function.
- `monitor/templates/monitor/_feed_initial.html` — line 34 (原文 cell, unchanged from plan `2026-07-27-001`), line 22 (翻译 cell, the target of the `{% if %}` branch in U2).
- `monitor/static/pw-feed.js` — line 225 (翻译 cell render, the target of the `|| "NULL"` change in U2).
- `locale/zh_Hans/LC_MESSAGES/django.po` — lines 34-39 (axis-label msgid block, the target of U1's msgid rename).
- `core/management/commands/seed_i18n_labels.py` — existing chrome i18n labels `中国民族主义` / `美国民族主义` for `cn_nationalism` / `us_nationalism` filter keys. The axis labels in the 分类 column now match these existing labels (no new translations needed).
- `tests/test_i18n_catalog_pinned.py` — `CLASSIFICATION_LABELS_PIN` dict (lines ~52-60), `TestClassificationLabelsPin` class — the target of U1's pin update.
- `tests/test_classification_labels.py` — `_apply_invariant` test pattern + `_serialize_feed_row` test pattern, the model for U2's new `tests/test_translation_null_fallback.py`.
- `.harness/verify-dashboard.js` — `feed_zh_cn_classification_labels` check (lines 31-150), the target of U3's axis-label-inversion + NULL-rendering assertions.
- `feedback_regression_net_in_every_plan.md` — the user-stated rule that plans modifying an existing surface must include a regression-net unit; U1 + U4 together satisfy it for this plan.
- Prod DB state (verified 2026-07-27):
  - 215 posts with `lang_detected != 'zh'` AND `text_zh_cn IS NULL` (205 zh-hans + 4 en + 6 other).
  - `tweet_id="2081578563816554708"` is one of the 205 zh-hans posts with `text_zh_cn IS NULL` — deterministic target for U3's NULL-rendering assertion.
  - Chrome filter panel labels (`中国民族主义` / `美国民族主义`) already exist in `core_nationalism_labels` table under `lang='zh-cn'` (from `seed_i18n_labels.py`).
- `reference_pushinweight_prod_db_via_render_cli.md` — query pattern + service IDs for prod verification.