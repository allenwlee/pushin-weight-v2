---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
plan_depth: standard
created: 2026-07-27
title: zh_CN feed classification labels + 原文 column translation
type: feat
---

## Goal Capsule

- **Objective:** Under the zh_CN locale, the live dashboard's 分类 column shows localized labels (e.g. `实际使用` instead of `hands_on_usage`, `正面` instead of `positive`) and the 原文 column shows the Chinese translation when present. Under EN, behavior is unchanged.
- **Authority hierarchy:** Plan body is binding. Reuse existing patterns (label resolution, locale-to-column mapping, `_pick_text`); do not introduce new tables or pipelines. Verification runs against the production Render deployment (`https://pushinweight-web.onrender.com`, Postgres `dpg-d9go1njeo5us73cg5u00-a`) — no dev DB exists.
- **Execution profile:** Sequential — U1 (label resolution) and U2 (text column) wire through the same serializer, so changes land together. U3 (Playwright harness against prod) gates the merge.
- **Stop conditions:** Do not edit the backfiller or classifier pipeline. Do not re-seed `posts.text_zh_cn` (already handled by the backfiller — see `2026-07-24-002-feat-backfiller-tool-plan.md`). Do not rename `cn_nationalism` / `us_nationalism` model fields — only the user-visible label text changes. Do not introduce a local dev DB or SSH tunnel; everything runs against prod.
- **Tail ownership:** Local session — the user runs `ce-work` or applies commits directly; the prod deploy via Render auto-deploys on push to `main` and triggers the `build.sh` (which runs `compilemessages`).

## Product Contract

### Summary

Make the 分类 column fully localized under zh_CN: each classification key (`hands_on_usage`, `genuine_hype`, `positive`, `none`, etc.) renders via the existing `*_labels` tables; the per-axis labels `cn:` / `us:` become `zh_cn:` / `en:` to match the underlying field naming; the 原文 column under zh_CN falls back through `posts.text_zh_cn → posts.text → empty`. EN locale is unchanged.

### Problem Frame

The Django port shipped the chrome i18n (filter titles, headers) under plan `2026-07-24-003-feat-django-i18n-zh-cn-plan.md`, but three UI surfaces still leak English under zh_CN:

1. **Classification values** are emitted as raw DB keys (`hands_on_usage`, `genuine_hype`, `positive`). The DB has `post_type_labels` / `discourse_labels` / `sentiment_labels` / `nationalism_labels` tables (one row per `key × lang`) populated by `core/management/commands/seed_i18n_labels.py`, but neither the Django view nor the JS feed row builder consults them.
2. **Per-axis labels `cn:` / `us:`** are misleading even in English — they sound like language codes but the underlying fields (`cn_nationalism`, `us_nationalism`) hold country-nationalism LEVELS, not languages. The plan `2026-07-24-003` translated them to `中:` / `美:`, which lost the field-name meaning. The cn:/us: msgids need to be retitled to `zh_cn:` / `en:` to match the actual field semantics.
3. **The 原文 column** in `_feed_initial.html:34` and `pw-feed.js:231` renders `row.text` (the X source — always the original tweet language). Under zh_CN, users expect to see the Chinese translation; the locale-aware text selection already exists (`_pick_text(post, locale)` returns the right column), but it is not wired into this column.

The repo already contains the right infrastructure: `seed_i18n_labels.py` (zh-cn translations for every taxonomy key), `Brand.display_name_zh_cn` (per-brand zh-CN names already wired into the dashboard), and `_LOCALE_TO_COLUMN` (locale-to-text-column mapping used by `_pick_text`). The plan extends these patterns, not new abstractions.

### Requirements

**Classification labels (zh_CN)**

- R1. Under zh_CN, every value rendered in the 分类 column's `types:`, `discourses:`, `sentiments:` rows is looked up via `post_type_labels` / `discourse_labels` / `sentiment_labels`; on miss, the value falls back to the raw DB key.
- R2. Under zh_CN, every value rendered in the `cn_nationalism` / `us_nationalism` rows is looked up via `nationalism_labels`; on miss, raw key.
- R3. Under EN, the 分类 column shows raw DB keys (no change from current behavior).

**Per-axis label keys**

- R4. The classification row labels in `_feed_initial.html` and `pw-feed.js` are `zh_cn:` and `en:` (not `cn:` / `us:` / `中:` / `美:`). This applies in both zh_CN and EN locales — the labels describe which axis the values are on, not a localized string.

**原文 column (zh_CN)**

- R5. Under zh_CN, the 原文 column shows `posts.text_zh_cn` when present, otherwise falls back to `posts.text`, otherwise empty.
- R6. Under EN, the 原文 column shows `posts.text` (current behavior — no change).
- R7. Under `original` locale, the 原文 column shows `posts.text` (current behavior — no change; source text is by definition the X original).

**Verification**

- R8. Playwright drives the production dashboard (`https://pushinweight-web.onrender.com`) under all three locales (zh_cn, en, original) and asserts the rendered 分类 row contents match the expected localized / raw labels.
- R9. Unit tests cover the new label-resolution function (`_localize_classification_value`) for hit, miss, and unknown-key cases — run against prod via `render jobs create pushinweight-web --start-command "python manage.py test tests.test_classification_labels"`.

**Out of scope (explicit)**

- Backfilling `posts.text_zh_cn` for rows where the value is null — handled by the backfiller tool (plan `2026-07-24-002`).
- Adding new taxonomy values or translations to `seed_i18n_labels.py` — the existing seed covers all keys the dashboard currently uses.
- Filter control-panel i18n — shipped by plan `2026-07-24-003`.
- Renaming the model fields `cn_nationalism` / `us_nationalism` — out of scope; we only change the visible label text.
- `lang:` axis localization — uses `lang_detected` codes, not taxonomy labels; covered by the existing lang filter rendering.
- Any local dev DB, SSH tunnel, or fuchitalee `.venv` commands — everything runs against prod.

### Acceptance Examples

- AE1. **zh_CN, post with all three classification axes populated.** Drive Playwright to `https://pushinweight-web.onrender.com/` with `locale=zh_cn` cookie. Assert the rendered row contains `types: 实际使用` (not `hands_on_usage`), `discourses: 真实热度` (not `genuine_hype`), `sentiments: 正面` (not `positive`), `zh_cn: 无` (not `cn: none`), `en: 无` (not `us: none`). Covers R1, R2, R4.
- AE2. **zh_CN, post with `text_zh_cn` populated.** Assert the 原文 column shows the Chinese translation, not the English source. Covers R5.
- AE3. **zh_CN, post with `text_zh_cn` null.** Assert the 原文 column falls back to `posts.text`. Covers R5 (fallback branch).
- AE4. **EN locale.** Assert the 分类 column shows raw DB keys (`hands_on_usage`, etc.), the axis labels are `zh_cn:` / `en:`, and the 原文 column shows the source text. Covers R3, R4, R6.
- AE5. **Original locale.** Assert the 原文 column shows the source text exactly as today. Covers R7.
- AE6. **Missing zh-cn label row.** Assert the classification falls back to the raw DB key (no crash, no empty cell). Covers R1/R2 miss branch.

### Scope Boundaries

- **In scope:** Wire DB label tables into the feed row serializer (Django view + JS builder), rename axis labels, swap 原文 column text-source, add Playwright checks, add unit tests for the resolution function.
- **Deferred for later:** Backfilling `posts.text_zh_cn` for posts where it is null; adding new taxonomy values to `seed_i18n_labels.py`; renaming the model fields.
- **Outside this product's identity:** Changing the EN locale rendering; renaming the filter control-panel tabs (`us_nationalism`, `cn_nationalism` already translate but the tab labels are kept for filter-API parity).

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Resolve classification labels in the Django view, not in JS.** Add a single `_localize_classification_value(family, key, locale)` helper in `monitor/views.py` that looks up `post_type_labels` / `discourse_labels` / `sentiment_labels` / `nationalism_labels` for `(key, locale)`; returns the label or the raw key on miss. The serializer (`_serialize_feed_row` + `_post_to_wire`) emits BOTH the key and the resolved label per value, e.g. `"post_types": [{"key": "hands_on_usage", "label": "实际使用"}]`. The JS builder reads `.label`. This keeps the wire shape explicit and lets future locales (ja, ko, etc.) be added by extending the helper. Alternative: resolve in JS via a separate `/labels/` endpoint — rejected because the data is already server-side; one round-trip per page load vs. one DB lookup per row.
- KTD2. **Reuse `_pick_text` for the 原文 column.** Add a new key in the wire (`text_original` = the locale-aware original-source text) so the JS builder doesn't reimplement locale → column mapping. The view computes `text_original` by running `_pick_text(post, locale)`. Under zh_CN, this returns `text_zh_cn or text`; under EN and `original`, it returns `text`. Alternative: branch in JS on `active_locale` — rejected because it duplicates the existing pattern.
- KTD3. **Use one batched DB query for all classifications, not N+1.** In `_enrich_posts_with_classifications` (or equivalent), prefetch `post_type_labels`, `discourse_labels`, `sentiment_labels`, `nationalism_labels` once per request and build a `{(family, key, lang): label}` dict the view reads from. This avoids 6-12 extra queries per feed batch. Alternative: per-row lookup with `.get_or_none()` — rejected for N+1 cost.
- KTD4. **Axis labels (`zh_cn:` / `en:`) are static strings, not translation keys.** They are field names, not localized strings — they describe which axis the values belong to in either locale. Update `_feed_initial.html` (translatable msgid `cn:` → `zh_cn:`, msgid `us:` → `en:`) and `pw-feed.js` (hardcoded `cn:` → `zh_cn:`, `us:` → `en:`). Under EN, the msgid resolves to `zh_cn:` / `en:`; under zh_CN, it resolves to the same strings (no `msgstr` Chinese translation needed — the msgid IS the localized value). Alternative: translate to `中:` / `美:` under zh_CN — explicitly rejected per user answer (`zh_cn:/en: matches DB field names`).
- KTD5. **Verify against the production Render Postgres DB.** Production URL: `https://pushinweight-web.onrender.com`. Prod DB: `dpg-d9go1njeo5us73cg5u00-a` (database `pushinweight`). Query via `ssh -o NoMosH=1 fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "<SQL>"'`. Playwright runs against the prod URL with a session cookie minted against the prod login. **Note:** prod already has labels under both `lang="zh_cn"` (legacy seed) and `lang="zh-cn"` (current seed) — the lookup helper handles both with `zh-cn` taking precedence (see KTD9). No dev DB exists in this workflow.
- KTD6. **Static lookup map for miss-case fallback in JS.** The JS builder receives labeled values from the wire, but for fields that bypass the wire (e.g. the `unsanctioned` pill rendered server-side in `_feed_initial.html`), the JS doesn't need a fallback map — those fields are already translated via `{% trans %}`. The wire carries the resolved label so the JS only emits what the server sent.
- KTD7. **Test the resolution helper with in-memory fixtures against prod.** Add `tests/test_classification_labels.py` that imports `_localize_classification_value` directly and builds in-memory `PostTypeLabel` / `DiscourseLabel` / etc. rows inside `setUp` (uses the prod DB transaction for the test's lifetime; rolls back automatically). Tests run via `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_classification_labels -v 2"'`. No dev DB exists; the prod test DB is created/destroyed by Django's test runner inside the Render container.
- KTD9. **Helper resolves zh_cn / zh-cn / zh-hans lang-code variants with zh-cn precedence.** Production DB has Chinese labels under both `lang="zh-cn"` (from `seed_i18n_labels.py`) and `lang="zh_cn"` (from a legacy seeding pass). Different keys have different translations between the two (`hands_on_usage` = `实际使用` vs `实际使用体验`; `genuine_hype` = `真实热度` vs `真心夸`). Django's internal `translation.activate` uses `zh-hans`. The helper `_localize_classification_value` must try `zh-cn` first, then `zh_cn`, then `zh-hans` (each falls through to the next on miss), and return the first match. Alternative: collapse to a single lang code via a one-time prod data migration that copies `zh-cn` rows over `zh_cn` — explicitly rejected because it would change visible labels for users who already saw the `zh_cn` translations (e.g. `真心夸` -> `真实热度`). Keep both, prefer the seed source.
- KTD8. **Session-settled:** axis label rename from `cn:` / `us:` to `zh_cn:` / `en:` matches DB field names (session-settled: user-directed — chosen over `zh:` / `en:` (more idiomatic) and `中:` / `美:` (keep current translation): field-name consistency wins for the rename).

### High-Level Technical Design

```
                 ┌──────────────────────────────────────────────┐
                 │   Django view (prod: pushinweight-web)        │
                 │                                               │
GET /feed/  ──▶  │  _serialize_feed_row(post, locale)           │
                 │     │                                         │
                 │     ├─▶ _pick_text(post, locale)             │
                 │     │     → text_translated                   │
                 │     │     → text_original                     │  ← NEW
                 │     │                                         │
                 │     └─▶ _enrich_classifications(post, locale) │  ← NEW
                 │           │                                   │
                 │           ├─▶ prefetch *_labels (1 batched    │
                 │           │   query per family)               │
                 │           │                                   │
                 │           └─▶ _localize_classification_value  │
                 │                 (key, family, locale)          │
                 │                 → [{key, label}, ...]         │
                 │                                               │
                 └──────────────────────────────────────────────┘
                                  │
                                  │  JSON wire (rows[])
                                  ▼
                 ┌──────────────────────────────────────────────┐
                 │       pw-feed.js (client row builder)         │
                 │                                               │
                 │  renderRowHtml(row):                          │
                 │    pts.map(v => v.label)         ← uses .label │
                 │    pts.map(v => v.key)   fallback             │
                 │    text: row.text_original       ← NEW field  │
                 └──────────────────────────────────────────────┘
```

Two wire-shape additions:

1. Each classification value in `classifications[nick]` becomes `{key, label}` instead of a bare string.
2. New top-level field `text_original` on each row.

`_feed_initial.html` (initial render) reads the same `{key, label}` shape from the view's pre-computed row dict — no parallel server-side path.

---

## Implementation Units

### U1. Add `_localize_classification_value` + wire-shape changes in view

**Goal:** The Django view resolves every classification value to its localized label via the existing `*_labels` tables and emits both key and label on the wire.

**Requirements:** R1, R2, R3, R5, R6, R7, R9

**Files:**

- `monitor/views.py`
- `tests/test_classification_labels.py` (create)

**Approach:**

1. Add `_localize_classification_value(family, key, locale)` to `monitor/views.py`. `family ∈ {"post_type", "discourse", "sentiment", "nationalism"}`. Map `family` to the right label model. Lookup order per KTD9: try `lang="zh-cn"` first, then `"zh_cn"`, then `"zh-hans"`, then `"en"`. Return the first label found, or the raw key if all miss.
2. Add `_locale_to_lang_codes(locale)` returning the ordered tuple of lang codes to try: `("zh-cn", "zh_cn", "zh-hans")` for `zh_cn`; `("en",)` for `en`; `("en",)` for `original`.
3. In `_enrich_posts_with_classifications` (or wherever `classifications_by_brand` is built), batched-prefetch all label rows for the keys+langs touched by the current page. Build a `dict[(family, key, lang)] = label` lookup once per request.
4. In `_serialize_feed_row` / `_post_to_wire`: when emitting `classifications[nick]["post_types"]`, `["discourse"]`, `["sentiments"]`, `["cn_nationalism"]`, `["us_nationalism"]`, transform each bare string into `{"key": <str>, "label": <str>}`. When the value is null/empty, emit nothing (current behavior).
5. Add `text_original` field to the wire. Compute via `_pick_text(post, "zh_cn")` under zh_CN locale (returns `text_zh_cn or text`); under EN and `original`, compute via `_pick_text(post, "en")` and `_pick_text(post, "original")` respectively (both return `text`).

**Test scenarios:**

- `test_localize_post_type_zh_cn_hit` — in `setUp`, insert a `PostTypeLabel` row for `("hands_on_usage", "zh-cn", "实际使用")`; assert helper returns `"实际使用"`.
- `test_localize_post_type_zh_cn_falls_back_to_zh_cn` — insert only `("hands_on_usage", "zh_cn", "实际使用体验")`; assert helper returns `"实际使用体验"` (zh_cn takes effect when zh-cn is absent).
- `test_localize_post_type_zh_cn_prefers_zh_cn` — insert both `("hands_on_usage", "zh-cn", "实际使用")` AND `("hands_on_usage", "zh_cn", "实际使用体验")`; assert helper returns `"实际使用"` (zh-cn precedence).
- `test_localize_post_type_zh_cn_miss` — no label rows at all; assert helper returns `"hands_on_usage"` (raw key fallback).
- `test_localize_sentiment_en_hit` — insert `("positive", "en", "Positive")`; assert helper returns `"Positive"`.
- `test_localize_nationalism_zh_cn_hit` — insert `("none", "zh-cn", "无")`; assert helper returns `"无"`.
- `test_localize_unknown_family_raises` — `family="invalid"` raises `ValueError` (defensive — catches typos).
- `test_serialize_feed_row_emits_labeled_values` — build a post with classifications, call `_serialize_feed_row`; assert `classifications[nick]["post_types"][0] == {"key": "hands_on_usage", "label": "实际使用"}`.
- `test_text_original_zh_cn_prefers_translation` — post with `text_zh_cn="中文"` and `text="english"`; under zh_CN locale, assert `text_original == "中文"`.
- `test_text_original_zh_cn_falls_back_to_text` — post with `text_zh_cn=None` and `text="english"`; under zh_CN, assert `text_original == "english"`.
- `test_text_original_en_returns_text` — under EN, assert `text_original == post.text` regardless of `text_zh_cn`.

**Verification:** `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_classification_labels -v 2"'` — all 11 tests pass against prod test DB; the helper works on empty DBs (miss branch); round-trips a full row through the wire shape.

---

### U2. Update Django template + JS feed builder to consume labeled values

**Goal:** Both the initial server-rendered rows (`_feed_initial.html`) and the JS-injected rows (`pw-feed.js`) read `.label` for classification values and `text_original` for the 原文 column. Rename axis labels `cn:` → `zh_cn:` and `us:` → `en:`.

**Requirements:** R1, R2, R3, R4, R5, R6, R7

**Files:**

- `monitor/templates/monitor/_feed_initial.html`
- `monitor/static/pw-feed.js`
- `locale/zh_Hans/LC_MESSAGES/django.po`
- `monitor/static/dashboard.js` (no change expected — verify and update only if axis labels appear)

**Approach:**

1. **Template `_feed_initial.html`:**
   - For each `cls.post_types` / `cls.discourse` / `cls.sentiments` / `cls.cn_nationalism` / `cls.us_nationalism` value, switch from `{{ v }}` to a loop that emits `v.label` (with `v.key` as a fallback or `data-key` attribute for debugging).
   - The classification values now arrive from the view as `{key, label}` objects instead of strings. Update template access accordingly.
   - Replace the `<span class="cls-label">{% trans "cn:" %}</span>` msgid with `{% trans "zh_cn:" %}`. Same for `us:` → `en:`.
   - For the 原文 column (`<div class="cell-truncated">{{ row.text|default:"" }}</div>`), switch to `{{ row.text_original|default:"" }}`.

2. **`pw-feed.js`:**
   - Update `renderRowHtml` to emit `v.label` instead of `v` for `post_types` / `discourse` / `sentiments` / `cn_nationalism` / `us_nationalism`. Bare-string values (legacy / non-shape) get rendered as-is so older rows still display.
   - Hardcode `"zh_cn:"` and `"en:"` for the axis labels (these are field names, not translated strings).
   - Replace `escapeHtml(row.text || "")` in the 原文 column with `escapeHtml(row.text_original || "")`.

3. **`locale/zh_Hans/LC_MESSAGES/django.po`:**
   - The msgids `cn:` and `us:` no longer exist in the templates. Remove them from the `.po` file (or leave stale; `compilemessages` regenerates). Add msgids `zh_cn:` and `en:` with `msgstr` equal to the msgid (no translation needed — the label IS the field name).
   - The `build.sh` in prod already runs `compilemessages`; verify it stays in `build.sh` and ships the new `.mo` file.

4. **`monitor/static/dashboard.js`:** Search for `cn:` / `us:` literals; update if present (current dashboard.js delegates to feed.js so likely no change).

**Test scenarios:**

- `test_feed_initial_renders_localized_label` — render `_feed_initial.html` against a row whose `classifications[nick]["post_types"][0] == {"key": "hands_on_usage", "label": "实际使用"}`; assert rendered HTML contains `实际使用` (not `hands_on_usage`).
- `test_feed_initial_renders_axis_label_zh_cn` — assert rendered HTML contains `zh_cn:` (not `cn:`).
- `test_feed_initial_renders_axis_label_en` — assert rendered HTML contains `en:` (not `us:`).
- `test_feed_initial_renders_text_original` — assert the 原文 cell shows `row.text_original`, not `row.text`.

**Verification:** `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_feed_initial -v 2"'` — passes against prod test DB. After deploy (auto on push to main), manually load `https://pushinweight-web.onrender.com/` under zh_CN locale in a browser; inspect the 分类 column of any rendered row — values are Chinese; inspect the 原文 column — shows Chinese when available; inspect the axis labels — show `zh_cn:` / `en:`.

---

### U3. Playwright verification against production dashboard

**Goal:** Drive Playwright against the production pushin-weight-v2 dashboard under all three locales and assert the rendered 分类 and 原文 columns match the expected localized / raw labels. This is the gate that catches the kind of "looks-right-in-code, wrong-on-page" regressions that produced the 25-commit i18n churn documented in `docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md`.

**Requirements:** R8

**Files:**

- `.harness/verify-dashboard.js` (extend existing harness; new check `feed_zh_cn_classification_labels`)

**Approach:**

1. **Mint a production session cookie.** Write a small helper script once:

   ```python
   # /tmp/mint_prod_session.py
   import os, sys, django
   sys.path.insert(0, os.getcwd())
   os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
   django.setup()
   from django.contrib.auth import get_user_model
   from django.contrib.sessions.backends.db import SessionStore
   User = get_user_model()
   u, _ = User.objects.get_or_create(
       username="playwright_probe",
       defaults={"email": "playwright_probe@localhost", "is_staff": True, "is_superuser": True},
   )
   u.set_unusable_password(); u.save()
   s = SessionStore()
   s["_auth_user_id"] = str(u.pk)
   s["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
   s["_auth_user_hash"] = u.get_session_auth_hash()
   s.create()
   print(s.session_key)
   ```

   Push to prod and run as a one-off job:

   ```bash
   ssh -o NoMosH=1 fuchitalee "cat > /tmp/mint.py" < /tmp/mint_prod_session.py
   ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python /tmp/mint.py"'
   ```

   The second command prints `session_key` on stdout. Capture it as `SESSION_COOKIE=<value>`.

2. **Run Playwright against prod.** From local:
   ```bash
   BASE_URL=https://pushinweight-web.onrender.com \
   SESSION_COOKIE=<value> \
   node /Users/allenwlee/development/minimax-marketing/.harness/verify-dashboard.js \
     --only=feed_zh_cn_classification_labels
   ```

3. **Check implementation in `verify-dashboard.js`.** The new check `feed_zh_cn_classification_labels`:
   - Sets the `locale` cookie to `zh_cn`, reloads.
   - Locates the first feed row (`tr[data-pw-feed-row]`).
   - Asserts the row's textContent contains at least one of `实际使用`, `热点发布`, `性能对比`, `反馈提问`, `广告营销`, `活动公告` for the `types:` line — OR the literal raw key (when no zh-cn label is seeded for that taxonomy key, the miss branch fires and the raw key appears; assert that's an acceptable fallback).
   - Asserts the row's textContent contains `zh_cn:` and `en:` for the axis labels.
   - Sets the `locale` cookie to `en`, reloads, asserts the same row shows raw DB keys (`hands_on_usage`, etc.) and `zh_cn:` / `en:` labels.
   - Sets the `locale` cookie to `original`, reloads, asserts the 原文 column equals the raw `text` field (compare against the first JSON `/feed/` response).

**Test scenarios:**

- AE1 (zh_CN, all three classification axes populated): render row, assert `types: 实际使用`, `discourses: 真实热度`, `sentiments: 正面`, `zh_cn: 无`, `en: 无`.
- AE2 (zh_CN, post with `text_zh_cn` populated): assert 原文 column shows `posts.text_zh_cn`.
- AE3 (zh_CN, post with `text_zh_cn` null): assert 原文 column falls back to `posts.text`.
- AE4 (EN locale): assert classification values are raw keys, axis labels are `zh_cn:` / `en:`, 原文 column shows source text.
- AE5 (original locale): assert 原文 column shows source text.
- AE6 (missing zh-cn label row): select a key without a seeded label, assert the row falls back to the raw key (no crash).

**Verification:** Run `BASE_URL=https://pushinweight-web.onrender.com SESSION_COOKIE=<value> node /Users/allenwlee/development/minimax-marketing/.harness/verify-dashboard.js --only=feed_zh_cn_classification_labels` — passes all 6 acceptance examples against prod. Then run the full `verify-dashboard.js` — no regressions in the 7 prior checks. Capture a screenshot of the prod zh_CN dashboard for visual review. (Playwright runs locally; only the BASE_URL points at prod.)

---

### U4. Pin all zh_CN catalog translations (regression net for existing chrome i18n)

**Goal:** Add a unit test that snapshots every msgid → msgstr pair in `locale/zh_Hans/LC_MESSAGES/django.po` and asserts each translation still resolves to its pinned value. This catches accidental shifts to the OTHER translations (feed headers, filter titles, empty states, topbar labels, axis labels after rename) when U1/U2 land. The 5 strings U1/U2 intentionally change (`cn:`, `us:`, `types:`, `discourses:`, `sentiments:`) get their pinned values updated in lockstep with U1/U2 — so the test encodes the BEFORE and AFTER for those, and FORBIDS drift on the rest.

**Requirements:** (defense-in-depth; not gated by an R-ID — supports R8 by ensuring Playwright sees stable chrome)

**Files:**

- `tests/test_i18n_catalog_pinned.py` (create)

**Approach:**

1. The test file imports `django.utils.translation` and the Django message catalog at module load. It uses `gettext` (the runtime-translated string function) so we exercise the same path the templates use.
2. Test cases (one per translation, or one parametrized test iterating a dict):
   - **Header test (`test_headers_pin`)**: assert `gettext("Filters") == "筛选"`, `gettext("Brands") == "品牌"`, `gettext("Discourse") == "话语"`, `gettext("post_type") == "文章类型"`, `gettext("account.role") == "账户角色"`, `gettext("lang") == "语言"`, `gettext("us_nationalism") == "美国民族主义"`, `gettext("cn_nationalism") == "中国民族主义"`, `gettext("unsanctioned") == "未批准"`, `gettext("show only flagged posts") == "仅显示标记帖子"`, `gettext("only") == "仅"`, `gettext("all") == "全部"`.
   - **Feed column test (`test_feed_columns_pin`)**: assert `gettext("datetime") == "日期时间"`, `gettext("brand") == "品牌"`, `gettext("translated") == "翻译"`, `gettext("original") == "原文"`, `gettext("classifications") == "分类"`, `gettext("handle") == "账号"`, `gettext("translated from:") == "翻译自:"`.
   - **Topbar + state test (`test_topbar_pin`)**: assert `gettext("window:") == "窗口:"`, `gettext("lang:") == "语言:"`, `gettext("24h window") == "24小时窗口"`, `gettext("loading more…") == "加载更多…"`, `gettext("end of feed") == "信息流结束"`, `gettext("no posts in window") == "窗口内无帖子"`, `gettext("← multi-brand") == "← 多品牌"`, `gettext("(locked)") == "（已锁定）"`, `gettext("Daily total posts per brand") == "每日各品牌帖子总数"`, `gettext("Single-brand stacked-area chart") == "单品牌堆叠面积图"`, `gettext("Spend panel — stubbed for U7.") == "消费面板 — U7待实现"`.
   - **Classification row labels — intentionally changed in U1/U2** (`test_classification_labels_pin`): pin the AFTER values that U1/U2 will produce:
     - `gettext("zh_cn:") == "zh_cn:"` (NEW msgid — no translation needed, msgid IS the value)
     - `gettext("en:") == "en:"` (NEW msgid — same)
     - `gettext("types:") == "类型:"` (UNCHANGED translation — `msgstr` stays `"类型:"`)
     - `gettext("discourses:") == "话语:"` (UNCHANGED translation)
     - `gettext("sentiments:") == "情感:"` (UNCHANGED translation)
     - These ARE the only 5 strings U1/U2 modify; U1 only changes the cn:/us: msgids (renames), not the msgstrs for types:/discourses:/sentiments:. The pin encodes the contract: types:/discourses:/sentiments: translations must NOT change to "实际使用" etc. (those belong in DB label rows, not the .po file).
3. Each test calls `translation.activate("zh-hans")` in `setUp` (and resets in `tearDown` via `translation.deactivate_all()`) so the test is locale-deterministic regardless of the host's default.
4. Pin the catalog as a Python dict literal in the test file (not parsed from the .po at test time). This is the freeze — if someone adds a new msgid/msgstr pair, the test file gets a new entry; if someone edits a msgstr, the test fails loudly.
5. Run against prod via `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_i18n_catalog_pinned -v 2"'`.

**Test scenarios:**

- `test_headers_pin` — all 12 header strings resolve to pinned Chinese.
- `test_feed_columns_pin` — all 7 feed column headers resolve to pinned Chinese.
- `test_topbar_pin` — all 11 topbar/state strings resolve to pinned Chinese.
- `test_classification_labels_pin` — `zh_cn:` / `en:` msgids resolve to themselves (no Chinese msgstr), `types:` / `discourses:` / `sentiments:` resolve to existing `类型:` / `话语:` / `情感:` translations (UNCHANGED).
- `test_untranslated_msgid_returns_english` — assert `gettext("definitely_not_a_msgid") == "definitely_not_a_msgid"` to confirm the test infrastructure is wired correctly (proves the activated locale is `zh-hans` and not English-default).
- `test_no_msgid_silently_lost` — iterate every msgid in the catalog dict; assert each is non-empty in both source and target. Catches accidental deletion of a msgstr.

**Verification:** `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py test tests.test_i18n_catalog_pinned -v 2"'` — all 6 tests pass against prod test DB. If anyone changes `msgstr "筛选"` to `"筛选2"` without updating the test, the test fails with a clear diff (`Expected: '筛选2' / Got: '筛选'`).


## Verification Contract

All verification runs against the production Render deployment. No dev DB exists.

- **Prod DB label confirmation** (production is the truth): `ssh -o NoMosH=1 fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT '\''post_type'\'' family, COUNT(*) FROM post_type_labels WHERE lang='\''zh-cn'\'' GROUP BY lang UNION ALL SELECT '\''discourse'\'' family, COUNT(*) FROM discourse_labels WHERE lang='\''zh-cn'\'' GROUP BY lang UNION ALL SELECT '\''sentiment'\'' family, COUNT(*) FROM sentiment_labels WHERE lang='\''zh-cn'\'' GROUP BY lang UNION ALL SELECT '\''nationalism'\'' family, COUNT(*) FROM nationalism_labels WHERE lang='\''zh-cn'\'' GROUP BY lang UNION ALL SELECT '\''role'\'' family, COUNT(*) FROM role_labels WHERE lang='\''zh-cn'\'' GROUP BY lang"'` — expected: post_type=6, discourse=10, sentiment=4, nationalism=6, role=3 (each under `zh-cn` lang). Prod currently has all of these (confirmed 2026-07-27). If any family is missing `zh-cn` rows, run `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py seed_i18n_labels"'` to insert them.
- **Unit tests** (prod test DB): `ssh -o NoMosH=1 fuchitalee "render jobs create pushinweight-web --start-command "python manage.py test tests.test_classification_labels -v 2""` — U1's tests pass (11 scenarios covering hit/miss/zh_cn-vs-zh-cn precedence/unknown-key).
- **i18n catalog pin tests** (prod test DB): `ssh -o NoMosH=1 fuchitalee "render jobs create pushinweight-web --start-command 'python manage.py test tests.test_i18n_catalog_pinned -v 2'"` — U4's tests pass (6 tests covering ~35 pinned translations). This is the regression net: fails if any existing msgstr shifts without an explicit test update, AND pins the AFTER state for the 5 strings U1/U2 intentionally change.
- **i18n catalog**: The `build.sh` runs `compilemessages` on every deploy to prod. Verify via `ssh -o NoMosH=1 fuchitalee 'render jobs create pushinweight-web --start-command "python manage.py compilemessages && python manage.py check --deploy"'` — no i18n errors.
- **Mint prod session cookie**: see U3 step 1. Use the printed session key as `SESSION_COOKIE=<value>` when running Playwright.
- **Playwright gate** (production): `BASE_URL=https://pushinweight-web.onrender.com SESSION_COOKIE=<value> node /Users/allenwlee/development/minimax-marketing/.harness/verify-dashboard.js --only=feed_zh_cn_classification_labels` — passes all 6 acceptance examples against prod. Full suite: `BASE_URL=https://pushinweight-web.onrender.com SESSION_COOKIE=<value> node verify-dashboard.js` — no regressions in the 7 prior checks.
- **Manual smoke**: open `https://pushinweight-web.onrender.com/` with `locale=zh_cn` cookie set in the browser, click into a brand, confirm 分类 column shows Chinese values (e.g. `实际使用`, `真实热度`, `正面`), 原文 column shows Chinese text when `text_zh_cn` is populated (the backfiller has populated 4,795 of 27,161 posts), axis labels are `zh_cn:` / `en:`.

## Definition of Done

- U1 complete: `_localize_classification_value` implemented (with KTD9 lang-code precedence), wire shape emits `{key, label}`, `text_original` added, all 11 tests pass against prod test DB.
- U2 complete: template + JS builder consume `.label` and `text_original`, axis labels renamed to `zh_cn:` / `en:`, prod `compilemessages` succeeds.
- U3 complete: Playwright check `feed_zh_cn_classification_labels` exists, all 6 acceptance examples pass against `https://pushinweight-web.onrender.com`, full `verify-dashboard.js` regression-clean.
- U4 complete: `tests/test_i18n_catalog_pinned.py` ships with 6 tests covering ~35 pinned msgid/msgstr pairs across headers, feed columns, topbar/state, and the 5 classification-label strings. All tests pass against prod test DB.
- Commit messages include the line `Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]` per global CLAUDE.md rule 4.
- No new dependencies added.
- No edits to `core/management/commands/seed_i18n_labels.py` (the existing translation strings are used as-is).
- No edits to the backfiller or classifier pipeline.
- No local dev DB, SSH tunnel, or `.venv/bin/python` commands introduced anywhere in the plan.
- The 25-commit i18n churn failure mode (see `docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md`) is NOT repeated: every change is gated by Playwright against prod, not by code reasoning.

## Prod DB State (verified 2026-07-27)

- Postgres service: `dpg-d9go1njeo5us73cg5u00-a` (database `pushinweight`)
- Web service: `pushinweight-web` (URL `https://pushinweight-web.onrender.com`, dashboard via `https://pushinweight-web.onrender.com/accounts/login/`)
- `posts` total: 27,161 rows
- `posts` with `text_zh_cn IS NOT NULL`: 4,795 rows (17.7%)
- `post_type_labels`: 6 rows × 3 lang codes (`en`, `zh_cn`, `zh-cn`)
- `discourse_labels`: 10 rows × 3 lang codes
- `sentiment_labels`: 4 rows × 3 lang codes
- `nationalism_labels`: 6 rows × 3 lang codes
- `role_labels`: 3 rows × 3 lang codes
- Translation divergence between `zh_cn` (legacy) and `zh-cn` (seed): confirmed on `hands_on_usage` (`实际使用` vs `实际使用体验`) and `genuine_hype` (`真实热度` vs `真心夸`); identical on `positive` and `none`.
- Render CLI auth file: `~/.render/cli.yaml` on fuchitalee (workspace `tea-d5o7n0mr433s73fubbmg`). All prod DB queries route through `ssh -o NoMosH=1 fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "..."'`.

## Sources & Research

- `core/models.py` — `PostTypeLabel`, `DiscourseLabel`, `SentimentLabel`, `NationalismLabel`, `RoleLabel` schemas (CompositePrimaryKey on `(<fk>, lang)`).
- `core/management/commands/seed_i18n_labels.py` — the existing translation table (zh-cn labels for every taxonomy key). `_LOCALES = ["en", "zh-cn"]`.
- `monitor/views.py:_pick_text` (lines 192-202) — existing locale-to-column mapping. Reuse this pattern for `text_original`.
- `monitor/views.py:_LOCALE_TO_COLUMN` (lines 88-93) — `zh_cn → text_zh_cn`, `en → text_en`, `original → text`.
- `monitor/views.py:_serialize_feed_row` (line 1010) — current wire shape, emits bare-string classification values.
- `monitor/templates/monitor/_feed_initial.html` — current rendering (line 34: `row.text`; lines 63-69: `cn:` / `us:` axis labels).
- `monitor/static/pw-feed.js` — client-side row builder (line 197-201: `cn:` / `us:` axis labels; line 231: `row.text`).
- `docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md` — failure mode to avoid: 25 commits of churn because code-only reasoning replaced Playwright verification.
- `feedback_playwright_first_for_ui.md` — Playwright is the first tool, not the last, for UI fixes.
- `docs/plans/2026-07-24-003-feat-django-i18n-zh-cn-plan.md` — the chrome i18n plan this builds on (filter titles, headers, labels).
- `docs/plans/2026-07-24-002-feat-backfiller-tool-plan.md` — handles `text_zh_cn` population; we do not re-seed here.
- `docs/plans/2026-07-22-001-feat-lang-detected-filter-plan.md` — the lang filter axis (uses `lang_detected` codes, not taxonomy labels; out of scope here).
- `reference_pushinweight_prod_db_via_render_cli.md` — query pattern + service IDs for prod verification.
