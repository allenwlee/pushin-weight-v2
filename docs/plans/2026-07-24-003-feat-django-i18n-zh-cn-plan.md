---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
plan_depth: standard
created: 2026-07-24
---

# feat: Django i18n — zh_CN default locale with full UI translation

## Goal Capsule

Wrap every hardcoded English string in the Django monitor templates with `{% trans %}` / `{% blocktrans %}`, create the `zh_CN` `.po` file, change the default locale from `en` to `zh_cn`, and keep the existing three-mode locale toggle (`zh_cn` / `en` / `original`) working. After this plan, the dashboard renders in Chinese by default; switching to `en` restores the current English UI; `original` shows English UI chrome with source-language text in the translated column.

## Problem Frame

The Django i18n infrastructure (`LocaleMiddleware`, `USE_I18N`, `LOCALE_PATHS`, `LANGUAGES`) is wired but unused. The `locale/` directory is empty — no `.po` files exist. Every UI string in the templates is hardcoded in English. The existing locale cookie mechanism only affects the text-column selection in `_pick_text()` and display-name resolution in `_feed_initial.html`; the chrome (headers, labels, filter titles, buttons) is always English. The original `2026-07-06-003` plan specified zh_CN as the default, but the implementation never delivered full i18n.

## Requirements

- **R1.** Default locale is `zh_cn`. On first visit (no cookie), the dashboard renders in Chinese.
- **R2.** All UI chrome strings (filter group titles, feed column headers, sort buttons, labels, placeholder text, empty states) use Django `{% trans %}` and appear in Chinese when `zh_cn` is active.
- **R3.** The EN locale is the existing hardcoded strings extracted via `makemessages` — no visual change from today when English is selected.
- **R4.** The "original" locale mode uses English for all UI chrome. Only the translated text column differs (shows `posts.text` directly instead of `text_en` or `text_zh_cn`).
- **R5.** Locale persists via the existing `locale` cookie (no change to the cookie mechanism).
- **R6.** Django `makemessages` / `compilemessages` workflow: `.po` files live in `locale/zh_CN/LC_MESSAGES/django.po`, compiled to `.mo` at build time.
- **R7.** The locale toggle (zh_cn / EN / orig) in the topbar continues to work and now affects `{% trans %}` resolution via `translation.activate()`.

## Key Technical Decisions

- **Use `translation.activate()` in `set_locale`, not a custom request processor.** The `LocaleMiddleware` sets the language from the session/cookie if `LANGUAGE_SESSION_KEY` is used, but our existing cookie is named `locale`, not `django_language`. Rather than rename the cookie (which would be a user-visible reset), call `translation.activate(locale)` in the `set_locale` view so `{% trans %}` tags resolve correctly. This keeps the existing cookie key and JS wire intact.
- **Keep the three-mode `active_locale` system.** Django's built-in i18n doesn't have an "original" concept. Continue passing `active_locale` to templates for the text-column and display-name branching. The new `translation.activate()` call runs alongside — they serve different purposes: Django's activated language controls `{% trans %}`, `active_locale` controls text-column selection.
- **`makemessages` extracts from templates, not just Python.** Django's `django-admin makemessages -l zh_CN` scans `.html` templates for `{% trans %}` and `{% blocktrans %}` tags. Run it after wrapping all strings, then hand-translate the resulting `.po` file.
- **`_pretty_followers` suffix stays in English.** k/m suffixes are English conventions; switching to 万 (wàn) would require i18n-aware formatting. Deferred to follow-up — Twitter/X itself uses k/m across all locales, so English suffixes are consistent with the platform the data comes from.

## Implementation Units

### U1. Wrap all template strings with `{% trans %}` and `{% blocktrans %}`

**Goal:** Every hardcoded English string in the Django templates becomes a translatable string.

**Requirements:** R2, R3

**Dependencies:** None

**Files:**
- `monitor/templates/monitor/home.html`
- `monitor/templates/monitor/brand_home.html`
- `monitor/templates/monitor/_feed_initial.html`
- `monitor/templates/monitor/_home_chart.html`
- `monitor/templates/monitor/_brand_chart.html`

**Approach:**
- Add `{% load i18n %}` at the top of each template (after `{% load static %}` where present).
- Wrap every hardcoded English string: filter group titles (`Filters`, `Brands`, `Discourse`, `post_type`, `account.role`, `lang`, `us_nationalism`, `cn_nationalism`, `unsanctioned`), feed column headers (`datetime`, `brand`, `translated`, `original`, `classifications`, `handle`), topbar labels (`window:`, `lang:`, `24h window`, `{{ home_window_days }}d window`), filter labels (`only`, `all`, `show only flagged posts`), empty states (`no posts in window`, `loading more…`, `end of feed`), classification labels (`types:`, `discourses:`, `sentiments:`, `cn:`, `us:`, `unsanctioned`, `translated from:`), chart canvas `aria-label` attributes (`Daily total posts per brand`, `Single-brand stacked-area chart`, `Area chart category`), and brand_home-only strings (`← multi-brand`, `(locked)`).
- Use `{% blocktrans %}` for strings with interpolation (e.g., `{% blocktrans %}translated from: [{{ row.lang_detected }}]{% endblocktrans %}`).

**Patterns to follow:** Django docs: `{% trans "string" %}` for literals, `{% blocktrans %}...{{ var }}...{% endblocktrans %}` for interpolated strings.

**Execution note:** Run `makemessages -l zh_CN` after wrapping all strings, then verify the extracted `.po` file contains every string listed above. The pre-wrap `makemessages` run is not useful as a baseline (it only extracts strings already inside `{% trans %}` tags, which currently don't exist).

**Test scenarios:**
- `test_zh_cn_renders_chinese_labels` — GET `/` with `locale=zh_cn` cookie; assert filter titles, headers, and labels are in Chinese.
- `test_en_renders_english_labels` — GET `/` with `locale=en` cookie; assert filter titles, headers, and labels are in English (matches current behavior).
- `test_original_renders_english_chrome` — GET `/` with `locale=original` cookie; assert filter titles and headers are in English, but the translated column behavior differs.
- `test_default_no_cookie_renders_zh_cn` — GET `/` with no cookie; assert default is zh_cn (R1).

**Verification:** Load the multi-brand and single-brand pages in zh_cn, en, and original modes. Confirm every visible UI string (except data content) matches the expected locale.

---

### U2. Create `zh_CN` .po file with translations

**Goal:** Produce the `locale/zh_CN/LC_MESSAGES/django.po` file with Chinese translations for every `{% trans %}` string.

**Requirements:** R1, R2, R3, R6

**Dependencies:** U1

**Files:**
- `locale/zh_CN/LC_MESSAGES/django.po` (create)
- `.gitignore` (add `*.mo` or `locale/**/*.mo`)

**Approach:**
1. Ensure the `locale/` directory exists.
2. Run `python manage.py makemessages -l zh_CN` to extract all `{% trans %}` and `{% blocktrans %}` strings from templates and Python files.
3. Hand-translate each `msgid` → `msgstr`. The translation map:

| English (msgid) | Chinese (msgstr) |
|---|---|
| Filters | 筛选 |
| Brands | 品牌 |
| only | 仅 |
| all | 全部 |
| Discourse | 话语 |
| post_type | 文章类型 |
| account.role | 账户角色 |
| lang | 语言 |
| us_nationalism | 美国民族主义 |
| cn_nationalism | 中国民族主义 |
| unsanctioned | 未批准 |
| show only flagged posts | 仅显示标记帖子 |
| datetime | 日期时间 |
| brand | 品牌 |
| translated | 翻译 |
| original | 原文 |
| classifications | 分类 |
| handle | 账号 |
| window: | 窗口: |
| lang: | 语言: |
| 24h window | 24小时窗口 |
| loading more… | 加载更多… |
| end of feed | 信息流结束 |
| no posts in window | 窗口内无帖子 |
| types: | 类型: |
| discourses: | 话语: |
| sentiments: | 情感: |
| cn: | 中: |
| us: | 美: |
| translated from: | 翻译自: |
| Daily total posts per brand | 每日各品牌帖子总数 |
| Single-brand stacked-area chart | 单品牌堆叠面积图 |
| Area chart category | 面积图类别 |
| @unknown | @未知 |
| ← multi-brand | ← 多品牌 |
| (locked) | （已锁定） |

4. Use `{% blocktrans %}` for the window-duration pattern: `{% blocktrans %}{{ home_window_days }}d window{% endblocktrans %}` → `{{ home_window_days }}天窗口`.
5. Compile: `python manage.py compilemessages`.

**Patterns to follow:** Django's standard i18n workflow.

**Test scenarios:**
- `test_po_file_has_all_keys` — parse the `.po` file, assert each key in the translation table above has a non-empty `msgstr`.
- `test_makemessages_deterministic` — run `makemessages -l zh_CN` twice; assert no new strings appear in the second run (all `{% trans %}` strings are captured on first pass).
- `test_compilemessages_runs` — run `compilemessages`; assert `.mo` file is created and non-empty.

**Verification:** `python manage.py compilemessages && python manage.py check` — no errors.

---

### U3. Change default locale to `zh_cn` and wire `translation.activate()`

**Goal:** New visitors see zh_CN; the locale toggle properly activates Django's translation engine.

**Requirements:** R1, R5, R7

**Dependencies:** U1, U2

**Files:**
- `project/settings.py`
- `monitor/views.py`

**Approach:**
1. In `settings.py`, change `LANGUAGE_CODE = "zh-cn"` (not `"zh_cn"` — Django uses BCP 47 with hyphen, not underscore).
2. In `monitor/views.py`, update `_resolve_locale()`: change the final fallback from `return "en"` to `return "zh_cn"`.
3. In `monitor/views.py`, update `_normalize_locale()`: change `if not locale: return "en"` to `if not locale: return "zh_cn"` so both default-locale sites agree.
4. In `monitor/views.py`, keep `"zh-CN"` in `SUPPORTED_LOCALES` for backward compatibility with existing cookies. Order as `("zh_cn", "zh-CN", "en", "original")` — the underscore form comes first so the normalizing loop matches it first, and the hyphen form catches legacy cookies and Accept-Language headers.
5. In `monitor/views.py`, update `set_locale()`: call `translation.activate(django_code)` where `django_code` maps `"zh_cn"` → `"zh-cn"`, `"zh-CN"` → `"zh-cn"`, `"en"` → `"en"`, `"original"` → `"en"` (R4 requires English chrome for original mode). Store the same Django BCP 47 code in `request.session[translation.LANGUAGE_SESSION_KEY]` so `LocaleMiddleware` persists it across requests.

**Execution note:** This is the narrowest unit — one config line, four view changes. No template changes.

**Test scenarios:**
- `test_default_language_is_zh_cn` — assert `django.conf.settings.LANGUAGE_CODE == "zh-cn"`.
- `test_resolve_locale_defaults_to_zh_cn` — call `_resolve_locale(request)` with no cookie; assert returns `"zh_cn"`.
- `test_normalize_locale_fallback_to_zh_cn` — call `_normalize_locale(None)` and `_normalize_locale("")`; assert both return `"zh_cn"`.
- `test_set_locale_zh_cn_activates_translation` — POST to `/locale/zh_cn/`; assert `translation.get_language()` is `"zh-cn"` and the response sets the `locale` cookie.
- `test_set_locale_zh_CN_legacy_cookie` — POST to `/locale/zh-CN/`; assert `translation.get_language()` is `"zh-cn"` (legacy cookie migration).
- `test_set_locale_en` — POST to `/locale/en/`; assert `translation.get_language()` is `"en"`.
- `test_set_locale_original_activates_en` — POST to `/locale/original/`; assert `translation.get_language()` is `"en"` (R4: English chrome).
- `test_languages_setting` — assert `("zh-cn", "简体中文")` entry exists in `LANGUAGES`.

**Verification:** Start server, clear cookies, visit `/`. Verify topbar, filter titles, and feed headers are in Chinese. Click `EN` — verify they switch to English. Click `orig` — verify chrome is English.

---

### U4. Build-time `.mo` compilation for Render

**Goal:** The production Docker/Render build compiles `.po` → `.mo` so `{% trans %}` works without runtime compilation.

**Requirements:** R6

**Dependencies:** U2

**Files:**
- `build.sh` (modify)

**Approach:** Add `python manage.py compilemessages` to `build.sh` **before** `python manage.py collectstatic` (standard Django deployment order). Verify that the Render build environment includes GNU `gettext` (`msgfmt`); if not, add `apt-get install -y gettext` (or the equivalent for the base image) before `compilemessages`. Also add `*.mo` or `locale/**/*.mo` to `.gitignore` — `.po` files are committed; `.mo` files are build artifacts.

**Patterns to follow:** Standard Django deployment practice.

**Test scenarios:**
- `test_compilemessages_produces_mo` — run `python manage.py compilemessages`; assert `locale/zh_CN/LC_MESSAGES/django.mo` exists.
- `test_build_sh_includes_compilemessages` — grep `build.sh` for `compilemessages`.
- `test_gitignore_excludes_mo` — grep `.gitignore` for `.mo` or `locale/**/*.mo`.

**Verification:** After deploying to Render, visit the live site. Verify zh_CN translations render correctly.

---

## Verification Contract

1. `python manage.py check` — no i18n warnings or errors.
2. `python manage.py makemessages -l zh_CN` — extracts all `{% trans %}` strings with zero `obsolete` entries (all template strings are wrapped).
3. Manual smoke: visit `/` with no cookie → Chinese UI. Switch to EN → English UI. Switch to orig → English UI, source-language text column.
4. Existing tests pass — `pytest tests/ -k "not test_golden"` — no regressions from template changes.

## Definition of Done

- [ ] All UI strings are wrapped with `{% trans %}` / `{% blocktrans %}` across all 5 templates.
- [ ] `locale/zh_CN/LC_MESSAGES/django.po` exists with translations for every string in the translation table.
- [ ] `locale/zh_CN/LC_MESSAGES/django.mo` is compiled and `.gitignore` excludes `.mo` files.
- [ ] `LANGUAGE_CODE = "zh-cn"` and `_resolve_locale()` / `_normalize_locale()` default to `"zh_cn"`.
- [ ] `_normalize_locale()` accepts both `zh_cn` and `zh-CN` (legacy backward compat) and maps `"original"` to Django's `"en"` for `translation.activate()`.
- [ ] Render build compiles `.mo` at deploy time with the `gettext` dependency verified.
- [ ] No regressions in existing test suite.
- [ ] Locale toggle (zh_cn / EN / orig) continues to work for both chrome and text-column selection.

## Scope Boundaries

### In scope
- Django monitor app templates (5 files: home, brand_home, _feed_initial, _home_chart, _brand_chart).
- Settings and views for default locale and `translation.activate()`.
- `zh_CN` locale only. `en` is implicit (fallback via `msgid`).
- Backward-compatible handling of legacy `zh-CN` (hyphen) cookies.

### Deferred to Follow-Up Work
- Translating DB content (brand display names, post sentiments) — those are data, not UI.
- The Flask `x_monitor/` app — it has its own template system. Port it to Django first.
- JavaScript strings (e.g., chart tooltip text from `pw-chart.js`).
- Chart tab labels (`post_type`, `discourse`, etc.) — these are server-sent dynamic keys.
- `_pretty_followers` locale-aware formatting (万/亿 for Chinese).
- The `_spend.html` placeholder text (throwaway stub — will be replaced when spend feature ships).

### Outside this product's identity
- Adding `ja`, `ko`, or other locale files. The infrastructure supports it but it's not planned here.
- Switching from cookie-based locale to Django's built-in session/cookie (the existing mechanism works and changing it adds no user value).
