# Lookup Tables (v2 Django ORM)

Version: v0.2.0-beta.1 (current write taxonomy `stage1-taxonomy-v4`)
Last updated: 2026-09-21 12:39:30 JST



This document catalogs every lookup/enum table in the current v2 Django
architecture. Each table constrains what the classifier and dashboard may
emit; compatibility tables remain readable for older persisted rows.

**Source of truth.** `core/models.py` defines the Django models (the schema).
`monitor/management/commands/load_seed.py` seeds brands, companies, and roles.
`core/management/commands/seed_i18n_labels.py` seeds the canonical taxonomy
values with active en/zh-cn/ja labels for post types, product labels, Audience Topics,
sentiments, geopolitical modes, national stance, and roles. Discourse,
nationalism, and unsanctioned families remain compatibility data.

**i18n label pattern.** The post type, product-label, sentiment, discourse,
nationalism, and role key tables have corresponding `*Label` models with a
composite primary key of `(key, lang)`. `UnsanctionedFlagKey` is the documented
unlabeled exception. Labels are seeded with:

```bash
python manage.py seed_i18n_labels
```

---

## 1. Post types -- `PostTypeKey` + `PostTypeLabel`

**Model:** `core.models.PostTypeKey` (table `post_type_keys`), `core.models.PostTypeLabel` (table `post_type_labels`)

**Referenced by:** `PostBrandSignal.post_type` (FK to `PostTypeKey`)

**Dashboard constant:** `monitor/views.py:_DASHBOARD_POST_TYPE_KEYS`

14 active values:

| key | en | zh-cn | ja |
|---|---|---|---|
| `releases_updates` | Releases & Updates | 发布与更新 | リリース・アップデート |
| `hands_on_usage` | Hands-On Usage | 实际使用 | 使用体験 |
| `results_analysis` | Results Analysis | 结果分析 | 結果分析 |
| `questions_requests` | Questions & Requests | 问题与请求 | 質問・要望 |
| `advertising_marketing` | Advertising & Marketing | 广告营销 | 広告・マーケティング |
| `events` | Events | 活动 | イベント |
| `opportunities` | Opportunities | 机会 | 機会 |
| `job_listings` | Job Listings | 招聘信息 | 求人情報 |
| `personnel_changes` | Personnel Changes | 人事变动 | 人事異動 |
| `opinions_reactions` | Opinions & Reactions | 观点与反应 | 意見・反応 |
| `research_explanations` | Research & Explanations | 研究与解释 | 研究・解説 |
| `business_finance` | Business & Finance | 商业与金融 | ビジネス・金融 |
| `news_reporting` | News Reporting | 新闻报道 | ニュース報道 |
| `other` | Other | 其他 | その他 |

The retained v1 aliases and taxonomy-v2 `events_opportunities` key remain
available for compatible historical reads. Taxonomy-v3 writes and emitted
output use the active keys above; the combined v2 key cannot be retroactively
split into `events` or `opportunities` without reclassification.

### 1.1 Product labels -- `ProductLabelKey` + `ProductLabelLabel`

**Model:** `core.models.ProductLabelKey` and
`core.models.ProductLabelLabel`

**Referenced by:** `PostBrandProductLabel.product_label`

5 active values:

| key | en | zh-cn | ja |
|---|---|---|---|
| `bug` | Bug | 缺陷 | バグ |
| `complaint` | Complaint | 投诉 | 苦情 |
| `testimonial` | Testimonial | 推荐评价 | 推奨の声 |
| `ideas_requests` | Ideas & requests | 想法与请求 | アイデア・要望 |
| `investigate_claim` | Investigate Claim | 待核查主张 | 調査対象の主張 |

The retained `product_request` key is a v1 compatibility alias for
`ideas_requests`; it is not an active output key.

---

## 2. Sentiments -- `SentimentKey` + `SentimentLabel`

**Model:** `core.models.SentimentKey` (table `sentiment_keys`), `core.models.SentimentLabel` (table `sentiment_labels`)

**Referenced by:** `PostBrandSignal.sentiment`,
`PostBrandClassificationState.sentiment` (both FK to `SentimentKey`)

4 values:

| key | en | zh-cn | ja |
|---|---|---|---|
| `positive` | Positive | 正面 | ポジティブ |
| `negative` | Negative | 负面 | ネガティブ |
| `neutral` | Neutral | 中性 | 中立 |
| `mixed` | Mixed | 混合 | 賛否混在 |

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

**Referenced by:** `PostBrandDiscourse.china_nationalism`,
`PostBrandDiscourse.us_nationalism`,
`PostBrandClassificationState.china_nationalism`, and
`PostBrandClassificationState.us_nationalism` (all FK to `NationalismKey`)

**Dashboard constant:** `monitor/views.py:_DASHBOARD_NATIONALISM_KEYS`

6 values (shared across both China and US axes):

| key | en | zh-cn | ja |
|---|---|---|---|
| `none` | None | 无 | なし |
| `mild_pro` | Mild Pro | 温和支持 | 控えめな支持 |
| `pro` | Pro | 支持 | 支持 |
| `constructive_critical` | Constructive Critical | 建设性批评 | 建設的な批判 |
| `anti` | Anti | 反对 | 反対 |
| `mixed` | Mixed | 混合 | 賛否混在 |

Nationalism is an axis about which side of the US-China divide the post
sympathizes with, NOT about generic anti-vendor hostility.

---

## 5. Audience Topics, geopolitical modes, and current flags

### Audience Topics

Audience Topics use `AudienceTopicScheme`, `AudienceTopicConcept`, and
`AudienceTopicLabel` rather than the older discourse table. The current seven
concept keys are:

`local_inference`, `cost_performance`, `model_distillation`,
`evals_benchmarks`, `openness_license`, `agents_tools`, and
`api_developer_surface`.

### Geopolitical modes and national stance

`GeopoliticalModeKey`/`GeopoliticalModeLabel` currently allow `reporting`,
`framework`, `nationalism`, and the exclusive `none`/`unavailable` sentinels.
`NationalStanceKey`/`NationalStanceLabel` hold the China/US direction values:
`none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, and `mixed`.
Directional national stance is valid only when `nationalism` is selected.

### Untracked Brand Promotions

`UntrackedBrandPromotionKey`/`UntrackedBrandPromotionLabel` use `general`,
`spam`, `scam`, `crypto`, and `unauthorized`. `general` is the exclusive
fallback for a promotion outside the tracked catalog when no narrower key
applies. Historical `UnsanctionedFlagKey` rows remain readable and are not
silently relabeled.

## 6. Roles -- `Role` + `RoleLabel`

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

## 7. Historical unsanctioned flags -- `UnsanctionedFlagKey`

**Model:** `core.models.UnsanctionedFlagKey` (table `unsanctioned_flag_keys`)

**Referenced by:** `PostUnsanctionedFlag.flags` (stored as a JSON array of flag keys in a TEXT column, not via FK)

**No label table.** This is the only key table without a corresponding `*Label` model.

Historical values remain readable, but current writes use the separate
Untracked Brand Promotions family described above. The historical table has
4 known values:

| key | description |
|---|---|
| `marketing_spam` | Historical promotional-content flag |
| `scam` | Obvious fraud / phishing |
| `crypto` | Crypto-shilling, web3 promotion |
| `unauthorized` | Impersonation / brand-misuse |

---

## 8. Brand registry

**Model:** `core.models.Brand` (table `brands`), `core.models.Company` (table `companies`), `core.models.BrandCompany` (table `brands_companies`)

**Seeded by:** `python manage.py load_seed`

**Source of truth:** The `brands` and `companies` DB tables (canonical).
Runtime opt-in is via `KNOWN_MODELS` in `project/settings.py`, which mirrors
`enabled_models` in `config.yaml`.

### 8.1 Enabled brands (21)

The `#` column is the canonical ordering of `enabled_models` in
`config.yaml` (mirrored by `KNOWN_MODELS` in `project/settings.py`).
The brands table itself holds **33 rows** at last review (sibling brands
seeded by migration 033, plus discovery rows for `gemini`/`gemma`/`gpt`/`grok`
and a `test_brand` row) — only the 20 in `enabled_models` are loaded
into the hot path; sibling/discovery rows are visible to admin tooling
but excluded from `model_validator(_validate_models)` in
`x_monitor/config.py`.

| # | nickname | display name (live) | parent company | HQ | accent color (live) |
|---:|---|---|---|---|---|
| 1 | `minimax` | MiniMax AI | MiniMax | CN | `#3b82f6` |
| 2 | `qwen` | Qwen | Alibaba Group | CN | `#f97316` |
| 3 | `deepseek` | DeepSeek | DeepSeek | CN | `#10b981` |
| 4 | `glm` | Zhipu GLM | Zhipu AI | CN | `#a855f7` |
| 5 | `mimo` | Xiaomi MiMo | Meituan | CN | `#eab308` |
| 6 | `moonshot_kimi` | Moonshot Kimi | Moonshot AI | CN | `#ec4899` |
| 7 | `inclusionai` | InclusionAI | InclusionAI Co. | CN | `#06b6d4` |
| 8 | `mistral` | Mistral | Mistral AI | FR | `#facc15` |
| 9 | `stepfun` | StepFun | StepFun | CN | `#22c55e` |
| 10 | `ernie` | Baidu ERNIE | Baidu Inc. | CN | `#0ea5e9` |
| 11 | `hunyuan` | Tencent Hunyuan | Tencent | CN | `#ec4899` |
| 12 | `llama` | Meta Llama | Meta Platforms Inc. | US | `#1877f2` |
| 13 | `nemo_megatron` | NVIDIA NeMo | NVIDIA | US | `#76b900` |
| 14 | `doubao` | ByteDance Doubao | ByteDance | CN | `#000000` |
| 15 | `yi` | 01.AI Yi | 01.AI | CN | `#7c3aed` |
| 16 | `sensechat` | SenseTime SenseChat | SenseTime | CN | `#ff6b00` |
| 17 | `exaone` | LG EXAONE | LG AI Research | KR | `#a50034` |
| 18 | `kuaishou` | Kuaishou KwaiYii | Kuaishou Technology | CN | `#ff4906` |
| 19 | `sakana_ai` | Sakana AI | Sakana | JP | `#1e40af` |
| 20 | `upstage` | Upstage Solar | Upstage Inc. | KR | `#22c55e` |
| 21 | `dots` | Dots | Dots | CN | configured |

**Country breakdown:** 14 CN, 2 US, 2 KR, 1 FR, 1 JP.

**Source-of-truth note.** Column 3 (display name) and column 6 (accent
color) reflect the live `brands` table (`brands.display_name` and
`brands.accent_color` columns). The seeder
(`monitor/management/commands/load_seed.py::BRAND_DISPLAY`) and the
dashboard view (`monitor/views.py::MODEL_ACCENT_COLORS` and
`MODEL_DISPLAY_NAMES`) are *fallbacks*: the dashboard render path
does `brand_obj.display_name or MODEL_DISPLAY_NAMES.get(...)`, so the
DB row wins. The 20 rows above mirror the live `brands` table as of
2026-08-05. Parent-company mappings are from `BRAND_TO_COMPANY` in
`load_seed.py` and HQ countries are derived from `Company.hq_country`
via `brands_companies`.

### 8.2 Sentinel brand

| nickname | display name | `is_sentinel` |
|---|---|---|
| `_unattributed` | Unattributed | `True` |

Every post falls into `_unattributed` until attribution runs. This brand is
excluded from the dashboard brand list and chart aggregation.

### 8.3 Brand-account links

The runtime source of truth for per-brand account handles is the
`brands_accounts` junction table (model `BrandAccount`), joined to `Account`
and `Role`. Edit handles via `load_seed` or a Django migration -- there are
no flat files to update.

---

## i18n label pattern

Post type, product-label, sentiment, discourse, nationalism, and role key
tables have corresponding `*Label` models. `UnsanctionedFlagKey` is the
unlabeled exception described in §6. Each label table uses a composite primary
key of `(key, lang)` via `django.db.models.CompositePrimaryKey`. Active post
type, product label, sentiment, and nationalism rows have `en`, `zh-cn`, and
`ja`; retained discourse and role rows have `en` and `zh-cn`.

Example Django ORM usage:

```python
# Get the Japanese label for a post type key

label = PostTypeLabel.objects.get(post_type_id="releases_updates", lang="ja")
print(label.label)  # "リリース・アップデート"

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
2. **Add every active locale label** to the matching label dict (e.g.
   `POST_TYPE_LABELS`, `DISCOURSE_LABELS`).
3. **Add to the dashboard constant** in `monitor/views.py` if the value should
   appear in the filter control panel (e.g. `_DASHBOARD_DISCOURSE_KEYS`).
4. **Update the classifier prompt legend** so the LLM knows the new value exists.
5. **Run `python manage.py seed_i18n_labels`** to insert the new key and labels.
6. **Update this document** with the new row.

Steps 1-3 and 6 should land in a single commit so they do not drift.

---


Last reviewed: 2026-09-21 12:39:30 JST — Detailed lookup snapshot reconciled with core/models.py, seed commands, v4 contract, 21 enabled brands, and the en/zh-cn/ja label set. Historical compatibility families remain readable but are not current-write vocabulary.
