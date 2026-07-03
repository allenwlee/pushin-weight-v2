# MiniMax — HuggingFace Products Report

> **A product is a HuggingFace artifact** (currently a model; future: dataset, space)
> owned by a brand. Every row in this report is one product in the `products` table,
> linked back to its `brand` via `brand_id`, with the `hf_type` column declaring its
> artifact kind. Schema details: `x-monitoring/x_monitor/migrations/005_products.sql`
> (PR #6, `feat/hf-products-crawler`).

## Collection summary

| Field | Value |
|---|---|
| **Brand** | MiniMax (`brand_id = minimax`) |
| **HuggingFace org** | `MiniMaxAI` (seeded as `is_primary=1, confirmed=1` in `brand_hf_orgs`) |
| **Products collected** | 19 |
| **All `hf_type`** | `model` (CHECK constraint: `model` \| `dataset` \| `space`) |
| **Total downloads (30-day)** | 4,094,936 |
| **Total likes** | 8,751 |
| **Created-date range** | 2025-01-12 → 2026-06-02 |
| **Collected** | 2026-06-22 (UTC) via `python -m x_monitor hf-products` (crawler) |
| **Source** | HF Hub REST API — `/api/models?author=MiniMaxAI&full=true` (Link-cursor pagination) + per-model `GET /api/models/{id}` (enrichment) |
| **Full dump** | `minimax-hf-products.json` (28 fields incl. parsed `raw` payload) |

## Schema map (data point → `products` table column)

Every value in the JSON dump and table below is persisted to a specific
column in the `products` table. The full DDL is in
`x-monitoring/x_monitor/migrations/005_products.sql`.

| Data point | DB column | Type | Stable? | Source |
|---|---|---|---|---|
| HF repo id (e.g. `MiniMaxAI/MiniMax-M1`) | `repo_id` | TEXT (PK) | ✅ stable | list+detail |
| Owning brand | `brand_id` | TEXT (FK → `brands.brand_id`, `ON DELETE SET NULL`) | ✅ stable | curated `brand_hf_orgs` |
| HF namespace | `hf_org` | TEXT (`NOT NULL`) | ✅ stable | list+detail |
| **Artifact kind** | **`hf_type`** | **TEXT (`NOT NULL`, `CHECK IN ('model','dataset','space')`, default `'model'`)** | ✅ stable | crawler input |
| Repo display name | `display_name` | TEXT | ✅ stable | detail |
| Authoring user/org (HF `author`) | `author` | TEXT | ✅ stable | list+detail |
| Git revision sha | `sha` | TEXT | 🔄 mutable | list+detail |
| Private flag | `private` | INTEGER (0/1) | 🔄 mutable | list+detail |
| Gated mode | `gated` | TEXT (`auto`/`manual`/`false`/NULL) | 🔄 mutable | detail |
| Disabled flag | `disabled` | INTEGER (0/1) | 🔄 mutable | detail |
| HF task (e.g. `text-generation`) | `pipeline_tag` | TEXT | 🔄 mutable | list |
| ML library (e.g. `transformers`) | `library_name` | TEXT | 🔄 mutable | list |
| **30-day downloads** | `downloads` | INTEGER | 🔄 mutable | list (canonical public metric) |
| All-time downloads | `downloads_all_time` | INTEGER | 🔄 mutable | **not exposed by HF API** (always null) |
| Downloads / day | `download_velocity` | REAL | 🔄 mutable | **not exposed by HF API** (always null) |
| Likes | `likes` | INTEGER | 🔄 mutable | list |
| HF trending score | `trending_score` | REAL | 🔄 mutable | list |
| Papers-with-Code id | `paperswithcode_id` | TEXT | 🔄 mutable | detail |
| Created at (HF) | `created_at` | TEXT (ISO-8601) | ✅ stable | list |
| Last modified (HF) | `last_modified` | TEXT (ISO-8601) | 🔄 mutable | list |
| HF tags | `tags_json` | TEXT (JSON array) | 🔄 mutable | list |
| Repo files (siblings) | `siblings_json` | TEXT (JSON array of `{rfilename[, size]}`) | 🔄 mutable | list |
| Model card (license, language, base_model…) | `card_data_json` | TEXT (JSON object) | 🔄 mutable | **detail only** (lean on list) |
| Model config (architectures, model_type, quantization_config…) | `config_json` | TEXT (JSON object) | 🔄 mutable | **detail only** (lean on list) |
| Dependent Spaces | `spaces_json` | TEXT (JSON array) | 🔄 mutable | **detail only** (lean on list) |
| Full HF payload (verbatim) | `raw_json` | TEXT (JSON object) | 🔄 mutable | detail (lossless archive) |
| First-ingested at | `collected_at` | TEXT (ISO-8601) | ✅ stable | crawler (set on first upsert) |
| Last-refreshed at | `updated_at` | TEXT (ISO-8601) | 🔄 mutable | crawler (set on every upsert) |

**Indexes (migration 005):** `idx_products_brand(brand_id)`,
`idx_products_hf_org(hf_org)`.
**FK:** `brand_id` → `brands.brand_id` `ON DELETE SET NULL` (deleting a brand keeps
the product row but nulls its `brand_id`; `repo_id` rows are never cascaded).
**Brand↔HF-org edge** lives in `brand_hf_orgs(brand_id, hf_org, is_primary, confirmed,
discovered_via, added_at)`, PK `(brand_id, hf_org)`, FK `brand_id` → `brands` `ON DELETE CASCADE`.

## Breakdown

### By `hf_type` (the `products.hf_type` column)

| `hf_type` | Count |
|---|---:|
| `model` | 19 |

> Today's crawler only emits `model` rows. The `dataset` and `space`
> values are reserved by the CHECK constraint for when the crawler is
> extended (Unit 6 of the plan leaves the door open).

### By pipeline tag (`products.pipeline_tag`)

| Task | Products |
|---|---:|
| `text-generation` | 13 |
| `image-text-to-text` | 3 |
| `image-feature-extraction` | 3 |

### By license (`products.card_data_json` → `license`)

| License | Products |
|---|---:|
| `other` | 10 |
| `apache-2.0` | 4 |
| `mit` | 3 |
| `—` | 2 |

### By library (`products.library_name`)

| Library | Products |
|---|---:|
| `transformers` | 17 |
| `—` | 2 |

## All products (sorted by 30-day downloads)

`hf_type` column included. All rows in this report are products; the model
identity is the `repo_id` (PK); the brand is the `brand_id` (FK).

| # | `hf_type` | Product (`repo_id`) | `brand_id` | `hf_org` | Downloads | Likes | Task (`pipeline_tag`) | License | Quant | Siblings | Spaces | Created | Last Modified |
|---:|---|---|---|---:|---:|---:|---|---|---|---:|---:|---|---|
| 1 | `model` | `MiniMaxAI/MiniMax-M2.7` | `minimax` | `MiniMaxAI` | 2,647,045 | 1,217 | text-generation | other | fp8 | 151 | 100 | 2026-04-09 | 2026-04-20 |
| 2 | `model` | `MiniMaxAI/MiniMax-M2.5` | `minimax` | `MiniMaxAI` | 601,754 | 1,497 | text-generation | other | fp8 | 163 | 100 | 2026-02-12 | 2026-03-10 |
| 3 | `model` | `MiniMaxAI/MiniMax-M3-MXFP8` | `minimax` | `MiniMaxAI` | 325,474 | 38 | image-text-to-text | other | mxfp8 | 52 | 0 | 2026-06-02 | 2026-06-15 |
| 4 | `model` | `MiniMaxAI/MiniMax-VL-01` | `minimax` | `MiniMaxAI` | 189,924 | 285 | image-text-to-text | — | — | 445 | 20 | 2025-01-12 | 2025-07-03 |
| 5 | `model` | `MiniMaxAI/MiniMax-M2` | `minimax` | `MiniMaxAI` | 126,248 | 1,500 | text-generation | other | fp8 | 153 | 100 | 2025-10-22 | 2025-12-23 |
| 6 | `model` | `MiniMaxAI/MiniMax-M3` | `minimax` | `MiniMaxAI` | 104,076 | 1,180 | image-text-to-text | other | — | 80 | 13 | 2026-06-02 | 2026-06-22 |
| 7 | `model` | `MiniMaxAI/MiniMax-M1-40k` | `minimax` | `MiniMaxAI` | 56,496 | 185 | text-generation | apache-2.0 | — | 433 | 2 | 2025-06-05 | 2025-07-07 |
| 8 | `model` | `MiniMaxAI/MiniMax-Text-01-hf` | `minimax` | `MiniMaxAI` | 28,981 | 11 | text-generation | other | — | 434 | 0 | 2025-06-03 | 2025-07-09 |
| 9 | `model` | `MiniMaxAI/MiniMax-M2.1` | `minimax` | `MiniMaxAI` | 9,901 | 1,356 | text-generation | other | fp8 | 152 | 100 | 2025-12-20 | 2026-02-13 |
| 10 | `model` | `MiniMaxAI/MiniMax-Text-01` | `minimax` | `MiniMaxAI` | 2,790 | 656 | text-generation | — | — | 435 | 23 | 2025-01-12 | 2025-07-03 |
| 11 | `model` | `MiniMaxAI/MiniMax-M1-80k` | `minimax` | `MiniMaxAI` | 1,188 | 692 | text-generation | apache-2.0 | — | 434 | 42 | 2025-06-13 | 2025-07-07 |
| 12 | `model` | `MiniMaxAI/VTP-Large-f16d64` | `minimax` | `MiniMaxAI` | 327 | 15 | image-feature-extraction | other | — | 9 | 0 | 2025-12-16 | 2025-12-16 |
| 13 | `model` | `MiniMaxAI/SynLogic-7B` | `minimax` | `MiniMaxAI` | 195 | 28 | text-generation | mit | — | 15 | 0 | 2025-06-03 | 2025-06-10 |
| 14 | `model` | `MiniMaxAI/SynLogic-32B` | `minimax` | `MiniMaxAI` | 127 | 17 | text-generation | mit | — | 25 | 0 | 2025-05-30 | 2025-06-10 |
| 15 | `model` | `MiniMaxAI/SynLogic-Mix-3-32B` | `minimax` | `MiniMaxAI` | 113 | 20 | text-generation | mit | — | 25 | 1 | 2025-05-30 | 2025-06-10 |
| 16 | `model` | `MiniMaxAI/MiniMax-M1-80k-hf` | `minimax` | `MiniMaxAI` | 87 | 8 | text-generation | apache-2.0 | — | 433 | 0 | 2025-07-01 | 2025-07-09 |
| 17 | `model` | `MiniMaxAI/MiniMax-M1-40k-hf` | `minimax` | `MiniMaxAI` | 82 | 12 | text-generation | apache-2.0 | — | 433 | 0 | 2025-07-01 | 2025-07-11 |
| 18 | `model` | `MiniMaxAI/VTP-Base-f16d64` | `minimax` | `MiniMaxAI` | 68 | 20 | image-feature-extraction | other | — | 9 | 0 | 2025-12-16 | 2025-12-16 |
| 19 | `model` | `MiniMaxAI/VTP-Small-f16d64` | `minimax` | `MiniMaxAI` | 60 | 14 | image-feature-extraction | other | — | 9 | 0 | 2025-12-16 | 2025-12-16 |

## Notes

- **`products` is the product table.** A model is a product; a dataset or space
  will also be a product when the crawler is extended. The artifact kind is
  never implicit — it's always `products.hf_type`.
- **`hf_type` is enforced by a `CHECK` constraint** (`'model'|'dataset'|'space'`).
  The upsert in `store.upsert_product` writes through that constraint; invalid
  values fail at INSERT, not silently downstream.
- **`downloads` is HuggingFace's 30-day count** (the canonical public metric).
  `downloadsAllTime` and per-day velocity are **not exposed** by the HF API, so
  `downloads_all_time` and `download_velocity` are `NULL` in every row.
- **`card_data` / `config` / `spaces` are detail-only.** The list endpoint
  (`/api/models?author=…&full=true`) returns a lean field set (downloads / likes /
  tags / siblings / pipeline_tag / library_name / sha / timestamps). The license,
  base_model, language, architectures, model_type, and quantization_config come
  from the per-model `GET /api/models/{id}` detail call and are persisted as JSON
  text columns so they survive schema evolution.
- **Method.** The crawler resolves `minimax → MiniMaxAI` from the curated
  `brand_hf_orgs` seed, runs a sanity gate (≥1 model authored by the org),
  lists all models with `full=true`, enriches each via the detail endpoint, and
  upserts into `products`. Re-running refreshes mutable stats and preserves stable
  fields (`repo_id`, `brand_id`, `hf_type`, `created_at`).
- **Feature.** PR #6 (`feat/hf-products-crawler`); plan:
  `docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md`.
