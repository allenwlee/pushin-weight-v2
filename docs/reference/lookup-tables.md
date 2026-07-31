# Lookup Tables (v2 Django ORM)

Last updated: 2026-07-31-10:35:47


This document catalogs every lookup/enum table in the v2 Django architecture.
Each table constrains what the classifier (LLM-side) and the dashboard
(display-side) are allowed to emit.

**Source of truth.** `core/models.py` defines the Django models (the schema).
`monitor/management/commands/load_seed.py` seeds brands, companies, and roles.
`core/management/commands/seed_i18n_labels.py` seeds the canonical taxonomy
values with en/zh-cn labels for post types, sentiments, discourse, nationalism,
and roles.

**i18n label pattern.** Every key table has a corresponding `*Label` model
with a composite primary key of `(key, lang)`. Labels are seeded with:

```bash
python manage.py seed_i18n_labels
```

---

## 1. Post types -- `PostTypeKey` + `PostTypeLabel`

**Model:** `core.models.PostTypeKey` (table `post_type_keys`), `core.models.PostTypeLabel` (table `post_type_labels`)

**Referenced by:** `PostBrandSignal.post_type` (FK to `PostTypeKey`)

**Dashboard constant:** `monitor/views.py:_DASHBOARD_POST_TYPE_KEYS`

6 values:

| key | en | zh-cn |
|---|---|---|
| `buzz_releases` | Buzz & Releases | 热点发布 |
| `hands_on_usage` | Hands-On Usage | 实际使用 |
| `performance_comparisons` | Performance Comparisons | 性能对比 |
| `feedback_questions` | Feedback & Questions | 反馈提问 |
| `advertising_marketing` | Advertising & Marketing | 广告营销 |
| `event_announcement` | Event Announcement | 活动公告 |

---

## 2. Sentiments -- `SentimentKey` + `SentimentLabel`

**Model:** `core.models.SentimentKey` (table `sentiment_keys`), `core.models.SentimentLabel` (table `sentiment_labels`)

**Referenced by:** `PostBrandSignal.sentiment` (FK to `SentimentKey`)

4 values:

| key | en | zh-cn |
|---|---|---|
| `positive` | Positive | 正面 |
| `negative` | Negative | 负面 |
| `neutral` | Neutral | 中性 |
| `mixed` | Mixed | 混合 |

---

## 3. Discourse -- `DiscourseKey` + `DiscourseLabel`

**Model:** `core.models.DiscourseKey` (table `discourse_keys`), `core.models.DiscourseLabel` (table `discourse_labels`)

**Referenced by:** `PostBrandDiscourse.discourse` (FK to `DiscourseKey`)

**Dashboard constant:** `monitor/views.py:_DASHBOARD_DISCOURSE_KEYS`

10 values (pragmatic register vocabulary):

| key | en | zh-cn |
|---|---|---|
| `genuine_hype` | Genuine Hype | 真实热度 |
| `sarcasm` | Sarcasm | 讽刺 |
| `dunk_yingyang` | Dunk / Yingyang | 阴阳怪气 |
| `self_deprecation` | Self-Deprecation | 自嘲 |
| `cope` | Cope | 自我安慰 |
| `fud` | FUD | 恐惧不确定怀疑 |
| `distillation_accusation` | Distillation Accusation | 蒸馏指控 |
| `ai_slop_critique` | AI Slop Critique | AI垃圾批评 |
| `absurdist_meme` | Absurdist Meme | 荒诞梗 |
| `advertising-marketing` | Advertising / Marketing | 广告营销 |

`advertising-marketing` is **hyphenated** (unlike `advertising_marketing` in
post types -- underscored). Both were introduced in the same migration (U2a).

---

## 4. Nationalism -- `NationalismKey` + `NationalismLabel`

**Model:** `core.models.NationalismKey` (table `nationalism_keys`), `core.models.NationalismLabel` (table `nationalism_labels`)

**Referenced by:** `PostBrandDiscourse.china_nationalism`, `PostBrandDiscourse.us_nationalism` (both FK to `NationalismKey`)

**Dashboard constant:** `monitor/views.py:_DASHBOARD_NATIONALISM_KEYS`

6 values (shared across both China and US axes):

| key | en | zh-cn |
|---|---|---|
| `none` | None | 无 |
| `mild_pro` | Mild Pro | 温和支持 |
| `pro` | Pro | 支持 |
| `constructive_critical` | Constructive Critical | 建设性批评 |
| `anti` | Anti | 反对 |
| `mixed` | Mixed | 混合 |

Nationalism is an axis about which side of the US-China divide the post
sympathizes with, NOT about generic anti-vendor hostility.

---

## 5. Roles -- `Role` + `RoleLabel`

**Model:** `core.models.Role` (table `roles`), `core.models.RoleLabel` (table `role_labels`)

**Referenced by:** `BrandAccount.role`, `CompanyAccount.role` (both FK to `Role`)

**Dashboard constant:** `monitor/views.py:_DASHBOARD_ROLE_FILTER_KEYS`

3 values:

| key | en | zh-cn |
|---|---|---|
| `official` | Official | 官方 |
| `staff` | Staff | 员工 |
| `community` | Community | 社区 |

The dashboard filter panel exposes a fourth runtime option (`other`) for
accounts with no role or an unrecognized role, but `other` is not a persisted
Role row -- it is computed at query time.

---

## 6. Unsanctioned flags -- `UnsanctionedFlagKey`

**Model:** `core.models.UnsanctionedFlagKey` (table `unsanctioned_flag_keys`)

**Referenced by:** `PostUnsanctionedFlag.flags` (stored as a JSON array of flag keys in a TEXT column, not via FK)

**No label table.** This is the only key table without a corresponding `*Label` model.

4 known values:

| key | description |
|---|---|
| `marketing_spam` | Promotional content with no informational value |
| `scam` | Obvious fraud / phishing |
| `crypto` | Crypto-shilling, web3 promotion |
| `unauthorized` | Impersonation / brand-misuse |

---

## 7. Brand registry

**Model:** `core.models.Brand` (table `brands`), `core.models.Company` (table `companies`), `core.models.BrandCompany` (table `brands_companies`)

**Seeded by:** `python manage.py load_seed`

**Source of truth:** The `brands` and `companies` DB tables (canonical).
Runtime opt-in is via `KNOWN_MODELS` in `project/settings.py`, which mirrors
`enabled_models` in `config.yaml`.

### 7.1 Enabled brands (20)

| # | nickname | display name | parent company | HQ | accent color |
|---:|---|---|---|---|
| 1 | `minimax` | MiniMax | MiniMax | CN | `#3b82f6` |
| 2 | `qwen` | Qwen | Alibaba Group | CN | `#f97316` |
| 3 | `deepseek` | DeepSeek | DeepSeek | CN | `#10b981` |
| 4 | `glm` | GLM / ChatGLM | Zhipu AI | CN | `#a855f7` |
| 5 | `mimo` | MiMo | Meituan | CN | `#eab308` |
| 6 | `moonshot_kimi` | Moonshot AI / Kimi | Moonshot AI | CN | `#ec4899` |
| 7 | `inclusionai` | InclusionAI | InclusionAI Co. | CN | `#06b6d4` |
| 8 | `mistral` | Mistral | Mistral AI | FR | `#facc15` |
| 9 | `stepfun` | StepFun | StepFun | CN | `#22c55e` |
| 10 | `ernie` | ERNIE | Baidu Inc. | CN | `#0ea5e9` |
| 11 | `hunyuan` | Hunyuan | Tencent | CN | `#ec4899` |
| 12 | `llama` | Llama | Meta Platforms Inc. | US | `#14b8a6` |
| 13 | `nemo_megatron` | NeMo / Megatron | NVIDIA | US | `#84cc16` |
| 14 | `doubao` | Doubao | ByteDance | CN | `#f43f5e` |
| 15 | `yi` | Yi | 01.AI | CN | `#8b5cf6` |
| 16 | `sensechat` | SenseChat | SenseTime | CN | `#d946ef` |
| 17 | `exaone` | EXAONE | LG AI Research | KR | `#0d9488` |
| 18 | `kuaishou` | Kling / Kuaishou | Kuaishou Technology | CN | `#fb923c` |
| 19 | `sakana_ai` | Sakana AI | Sakana | JP | `#6366f1` |
| 20 | `upstage` | Upstage | Upstage Inc. | KR | `#dc2626` |

**Country breakdown:** 14 CN, 2 US, 2 KR, 1 FR, 1 JP.

Company mappings are sourced from `BRAND_TO_COMPANY` in
`monitor/management/commands/load_seed.py`. Display names are from
`BRAND_DISPLAY` in the same file. Accent colors are from
`MODEL_ACCENT_COLORS` in `monitor/views.py`.

### 7.2 Sentinel brand

| nickname | display name | `is_sentinel` |
|---|---|---|
| `_unattributed` | Unattributed | `True` |

Every post falls into `_unattributed` until attribution runs. This brand is
excluded from the dashboard brand list and chart aggregation.

### 7.3 Brand-account links

The runtime source of truth for per-brand account handles is the
`brands_accounts` junction table (model `BrandAccount`), joined to `Account`
and `Role`. Edit handles via `load_seed` or a Django migration -- there are
no flat files to update.

---

## i18n label pattern

Each key table (PostTypeKey, SentimentKey, DiscourseKey, NationalismKey, Role)
has a corresponding `*Label` model. The label table uses a composite primary
key of `(key, lang)` via `django.db.models.CompositePrimaryKey`.

Supported locales: `en`, `zh-cn`.

Example Django ORM usage:

```python
# Get the English label for a post type key

Last updated: 2026-07-31-10:35:47
label = PostTypeLabel.objects.get(post_type_id="buzz_releases", lang="en")
print(label.label)  # "Buzz & Releases"

# Get all labels for a discourse key
for lbl in DiscourseKey.objects.get(key="genuine_hype").labels.all():
    print(f"{lbl.lang}: {lbl.label}")
# en: Genuine Hype
# zh-cn: 真实热度
```

Seeding is idempotent -- re-running `seed_i18n_labels` after the first run
produces no net new rows (all inserts use `get_or_create`).

---

## Adding a new taxonomy value (v2 workflow)

1. **Add the key** to the relevant list in `core/management/commands/seed_i18n_labels.py`
   (e.g. `_POST_TYPES`, `_DISCOURSE`).
2. **Add en and zh-cn labels** to the matching label dict (e.g.
   `POST_TYPE_LABELS`, `DISCOURSE_LABELS`).
3. **Add to the dashboard constant** in `monitor/views.py` if the value should
   appear in the filter control panel (e.g. `_DASHBOARD_DISCOURSE_KEYS`).
4. **Update the classifier prompt legend** so the LLM knows the new value exists.
5. **Run `python manage.py seed_i18n_labels`** to insert the new key and labels.
6. **Update this document** with the new row.

Steps 1-3 and 6 should land in a single commit so they do not drift.

---

Last reviewed: 2026-07-31

**Substantive corrections this review:** none. Verified against `core/models.py` (Brand has `nickname` TEXT PK, no synthetic `id`), `core/management/commands/seed_i18n_labels.py` (all 6 post types, 4 sentiments, 10 discourse, 6 nationalism, 3 roles match), `config.yaml::enabled_models` (20 brands, identical order to §7.1), `monitor/management/commands/load_seed.py` (`BRAND_DISPLAY`, `BRAND_TO_COMPANY` match §7.1 columns 3 and 4), `monitor/views.py::MODEL_ACCENT_COLORS` (match §7.1 column 6), and `config.yaml::call_b_groups` (3 groups as documented). Country breakdown (14 CN / 2 US / 2 KR / 1 FR / 1 JP) reconciles.

**Flagged — could not verify:** the `_VALID_POST_TYPES` frozenset in `x_monitor/attribution.py` was truncated by the grep header (`_VALID_POST_TYPES = {` on line 1102, body not captured). Doc's 6-value list matches the seed list in `seed_i18n_labels.py` so the frozenset is very likely consistent, but the literal set membership was not directly confirmed. The `data/queries/` directory referenced by the 2026-07-13 call-B plan and the `call_b_groups` config comment does not exist on disk (`No such file or directory`) — the per-brand → call-group coverage matrix asserted in the plan is not enforceable in the current repo state and is not represented in this doc.

**Drift noticed but not fixed:** two `Last updated:` lines under H1 (line 3 `2026-07-24-11:36:23` and line 5 `2026-07-24`) — only the second is the canonical date; the first is a leftover timestamp. Per scope, main session owns these lines.
