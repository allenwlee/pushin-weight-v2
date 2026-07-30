# Feed UI contract

### written by Grok 4.3

**Path:** `docs/reference/feed-ui-contract.md`  
**Repo:** pushin-weight-v2  
**Canonical host copy:** `/Users/fuchitalee/development/pushin-weight-v2/docs/reference/feed-ui-contract.md`  
**Status:** living document — update when wire or dual-path render changes  
**Captured from code:** 2026-07-27 (post plans `2026-07-27-001` / `003` partial land)

---

## Purpose

Single source of truth for the **dashboard feed table** (posts list under home / brand views). Plans are **deltas against this contract**, not competing rewrites of history.

**Why this exists.** Feed rows are rendered **twice** (SSR + client). Labels come from **three** systems (DB, gettext, JS hardcodes). Locale codes collide (`zh_cn` / `zh-cn` / `zh_Hans`). Agents that fix one layer and not the others produce the 25-commit i18n churn documented in `docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md`.

---

## Architecture (non-negotiable)

```
┌──────────────────────────────────────────────────────────┐
│  THIS CONTRACT (wire + locale rules + dual-path pins)    │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  Server: monitor/views.py                                │
│  - _normalize_locale / _LOCALE_TO_COLUMN                 │
│  - _pick_translation → text_translated                   │
│  - _localize_classification_value + label cache          │
│  - _post_to_wire / _serialize_feed_row  (ONE wire shape) │
└────────────────────────────┬─────────────────────────────┘
              ┌──────────────┴──────────────┐
              ▼                             ▼
┌─────────────────────────┐   ┌─────────────────────────────┐
│ SSR                     │   │ CSR                         │
│ _feed_initial.html      │   │ pw-feed.js → renderRowHtml  │
│ DISPLAY ONLY            │   │ DISPLAY ONLY                │
│ No business rules       │   │ No business rules           │
└─────────────────────────┘   └─────────────────────────────┘
```

### Rules for implementers

1. **Business logic only in the view serializer.** Template and JS format wire fields; they do not re-derive locale → column or taxonomy labels.
2. **Dual-path rule.** Any change that affects a cell must update **both** `_feed_initial.html` and `pw-feed.js` in the same commit (or prove one path is unused).
3. **Prefer wire-emitted chrome.** Hardcoded Chinese/English in JS is technical debt. Ideal: `axis_labels` on the wire. Until then, template gettext + JS hardcodes must stay **byte-identical** for the same strings.
4. **Absence pins.** Tests must assert old strings are **gone** (`zh_cn:`, bare `hands_on_usage` under zh_CN when a label exists), not only that new strings appear.
5. **Three test layers** before merge: pure helpers → wire snapshot → Playwright (SSR **and** after client refetch/scroll).

---

## Locales

| Cookie / toggle value | Normalize to | Translation column for 翻译 | 原文 column |
|----------------------|--------------|-----------------------------|-------------|
| (missing) | `zh_cn` (default) | `posts.text_zh_cn` | `posts.text` (source X text) |
| `zh_cn` / `zh-CN` / `zh_hans` | `zh_cn` (casefold match) | `posts.text_zh_cn` | `posts.text` |
| `en` | `en` | `posts.text_en` | `posts.text` |
| `original` | `original` | `posts.text` (source **is** the locale) | `posts.text` |

**Code:** `SUPPORTED_LOCALES`, `_LOCALE_TO_COLUMN`, `_normalize_locale`, `_pick_translation` in `monitor/views.py`.

**Django gettext catalog locale** for chrome (`{% trans %}`) is **`zh_Hans`** (`locale/zh_Hans/LC_MESSAGES/`), not `zh-cn`. Cookie display locale and gettext BCP-47 are different systems — do not collapse them without reading `project/locale_cookie.py` / middleware order.

**Label-table lang codes** for classification values (DB `*_labels.lang`): try in order  
`zh-cn` → `zh_cn` → `zh-hans` under display locale `zh_cn`; `en` under `en` / `original`.

---

## Table columns (left → right)

| # | Header (conceptual) | Wire fields | SSR | CSR (`data-pw-*` / structure) |
|---|---------------------|-------------|-----|-------------------------------|
| 1 | Date | `tweet_id`, `created_at`, `created_at_iso` | link to x.com/status | same |
| 2 | Brands | `brands[]` with `display_name_zh_cn` / `display_name_en` | locale branch | prefers `display_name_zh_cn` then en |
| 3 | 翻译 (translation) | `text_translated`, `is_translated`, `lang_detected`, `like_count` | `[data-pw-cell-translated]` | same |
| 4 | 原文 (source / original) | `text_original`, also `text` (alias of original) | `[data-pw-cell-translated]` (shared class) | same |
| 5 | 分类 (classifications) | `classifications[nickname]`, `brand_nicknames`, `unsanctioned` | `.cls-block` / `.cls-label` / `.pill[data-key]` | same |
| 6 | Account | `account.handle`, `followers_pretty`, `role` / `role_label` | handle link | same |

---

## Text columns contract

### 翻译 (`text_translated`)

| Case | Wire value | Display |
|------|------------|---------|
| Locale column has non-empty text | that string | string |
| Locale column empty / null | JSON `null` | literal **`NULL`** (ASCII, not translated) |
| Never | fall back to source `text` under zh_CN/en for “looks full” | **forbidden** (plan 003) |

**Helpers:** `_pick_translation(post, locale) → (str|None, is_translated: bool)`.

**Render:**

- Template: `{% if row.text_translated %}…{% else %}NULL{% endif %}`
- JS: `row.text_translated || 'NULL'`

### 原文 (`text_original`)

| Locale | Value |
|--------|--------|
| All (current code) | **`post.text`** (X source language as stored) |

Note: plan 001 intended locale-aware “original” under zh_CN via `_pick_text` → `text_zh_cn or text`. **Current code does not do that** — both wire fields `text` and `text_original` are source `post.text`. Future plans that change 原文 must update this table and both renderers; do not assume 001 is live.

---

## Classification contract

### Wire shape (per brand nickname)

```json
"classifications": {
  "<brand_nickname>": {
    "post_types":  [ {"key": "hands_on_usage", "label": "实际使用"}, ... ],
    "discourse":   [ {"key": "genuine_hype", "label": "..."}, ... ],
    "sentiments":  [ {"key": "...", "label": "..."}, ... ],
    "cn_nationalism": {"key": "none", "label": "无"} | null,
    "us_nationalism": {"key": "...", "label": "..."} | null,
    "role_label": "..."
  }
}
```

- **`key`:** stable DB taxonomy id (filters, debug, `data-key`).
- **`label`:** localized display string; **on miss = key** (never empty pill if key exists).
- Family map: `post_type` / `discourse` / `sentiment` / `nationalism` → `*_labels` tables.

### Axis chrome labels (nationalism rows)

| Axis field | Canonical display string (SSR + CSR) | Forbidden legacy |
|------------|--------------------------------------|------------------|
| `cn_nationalism` | `中国民族主义:` | `cn:`, `中:`, `zh_cn:` |
| `us_nationalism` | `美国民族主义:` | `us:`, `美:`, `en:` |

SSR uses `{% trans "中国民族主义:" %}` / `{% trans "美国民族主义:" %}`.  
CSR currently **hardcodes** the same Chinese strings in `pw-feed.js` (debt — keep in sync until wire-emitted `axis_labels`).

### Row chrome labels (types / discourses / sentiments)

| Axis | Display (gettext / hardcoded) |
|------|-------------------------------|
| post_types | `types:` |
| discourse | `discourses:` |
| sentiments | `sentiments:` |

Under zh_CN, gettext may translate these in `.po`; JS currently hardcodes English **`types:` / `discourses:` / `sentiments:`** — known dual-path inconsistency; fix by emitting chrome from wire or gettext-export JSON, not by editing only one path.

### Locale behavior for values

| Display locale | Classification **values** |
|----------------|---------------------------|
| `zh_cn` | Labels from DB (`zh-cn` / `zh_cn` / `zh-hans`) |
| `en` | Typically raw keys or en labels if seeded |
| `original` | Same as en label path for taxonomy |

---

## Inventory matrix (must stay complete)

| Cell / chrome | Wire field | View helper | Template | JS |
|---------------|------------|-------------|----------|-----|
| Date link | `tweet_id`, `created_at*` | `_post_to_wire` | `.feed-date-link` | same |
| Brand pills | `brands[]` | wire + `MODEL_DISPLAY_NAMES` | locale branch | prefers zh_cn name |
| 翻译 body | `text_translated` | `_pick_translation` | `[data-pw-cell-translated]` first in col | same selector |
| 翻译 NULL | `null` | — | literal NULL | `\|\| 'NULL'` |
| 原文 | `text_original` / `text` | currently `post.text` | second text cell | `text_original \|\| text` |
| types values | `classifications.*.post_types[]` | `_labelize` / `_localize_*` | `.pill[data-key]` | `.pill[data-key]` |
| discourse values | `…discourse[]` | same | same | same |
| sentiment values | `…sentiments[]` | same | same | same |
| cn nationalism | `…cn_nationalism` | same | `{% trans "中国民族主义:" %}` | hardcoded Chinese |
| us nationalism | `…us_nationalism` | same | `{% trans "美国民族主义:" %}` | hardcoded Chinese |
| Unsanctioned | `unsanctioned` | enrich | pill | pill |
| Handle | `account.handle` | enrich / author | `.feed-handle-link` | same |

---

## Change procedure (every UI PR)

1. **Read this contract** + open both render files and `views.py`.
2. **Update the contract first** if product rules change (locale matrix, NULL, axis names).
3. **Implement serializer / helpers** and L1 pure tests.
4. **L2 wire snapshot** for three locales (fixture post with full classifications + null translation).
5. **Sync both renderers** in one commit; `rg` for string literals that must match.
6. **L3 harness:** `.harness/verify-dashboard.js` (or successor) — assert SSR and post-refetch; assert **absence** of forbidden legacy strings.
7. Commit message includes:  
   `Scope delivered vs plan/contract: match | narrower: …`  
   and lists dual-path files.

### Forbidden agent patterns

- Edit only `pw-feed.js` or only `_feed_initial.html` for the same cell.
- “Fix” locale by renaming directories without middleware / cookie mapping.
- Fall back `text_translated` → `text` under zh_CN/en to hide empty translations.
- Re-introduce axis labels `zh_cn:` / `en:` / `cn:` / `us:` without updating this contract + harness.
- Run only unit tests and skip dual-path visual contract for feed PRs.

---

## Related plans (historical; do not re-execute blindly)

| Plan | Relationship to this contract |
|------|--------------------------------|
| `docs/plans/2026-07-27-001-feat-zh-cn-classification-labels-plan.md` | Introduced `{key,label}` wire; **axis labels `zh_cn:`/`en:` superseded** by 003 |
| `docs/plans/2026-07-27-003-fix-zh-cn-axis-rename-and-translation-null-fallback-plan.md` | Axis Chinese names + translation NULL; **partially live** — verify dual path before re-touching |
| `docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md` | Why dual path + gettext + middleware ordering bite |

New work should be a **delta section** at the bottom of this file or a short plan that says “amends feed-ui-contract § X”.

---

## Known debts (as of capture)

1. Nationalism axis strings hardcoded in JS vs `{% trans %}` in template.
2. `types:` / `discourses:` / `sentiments:` may differ between gettext SSR and English JS hardcodes under zh_CN.
3. Brand pills: template branches on `active_locale == 'zh_cn'`; JS always prefers `display_name_zh_cn` first (locale-insensitive).
4. `text_original` does not use zh_CN translation (001 intended); product may want that later — update contract first.
5. Two serializers (`_post_to_wire` and `_serialize_feed_row`) — keep behavior in lockstep or merge.

---

## Verification commands

```bash
# L1/L2 (local or job)
.venv/bin/pytest tests/test_classification_labels.py tests/test_translation_null_fallback.py tests/test_i18n_catalog_pinned.py -q

# Dual-path string audit
rg -n "中国民族主义|美国民族主义|zh_cn:|text_translated|text_original|cls-label" \
  monitor/templates/monitor/_feed_initial.html monitor/static/pw-feed.js monitor/views.py

# L3 harness (needs session cookie)
node .harness/verify-dashboard.js --only=feed_zh_cn_classification_labels
```

---

## Amendment log

| Date | Change |
|------|--------|
| 2026-07-27 | Initial capture from live views / template / pw-feed.js; methodology for agent-safe UI work |
