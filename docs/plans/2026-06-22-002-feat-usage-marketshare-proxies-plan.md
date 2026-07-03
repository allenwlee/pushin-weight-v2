---
title: "feat: Usage / market-share proxy collectors + comparison charts (OpenRouter + opencode primary)"
type: feat
status: active
date: 2026-06-22
target_repo: minimax-marketing (code under `x-monitoring/`)
revision:
  - 2026-06-22 — Initial plan. Adds a generic time-series layer (`usage_sources`, `source_brand_keys`, `usage_samples`), collectors for OpenRouter (JSON API) and opencode (HTML scrape), and a new `/usage` dashboard page that overlays usage metrics on the existing X-post time series. Treats the existing `products` table from plan 2026-06-21-001 as the HF input that an aggregator collector rolls up.
---

# Usage / market-share proxy collectors + comparison charts

## Overview

Add a **usage telemetry** layer to x-monitor that pulls per-brand usage signals from public third-party proxies, stores them in a generic time-series table, and renders them in a new dashboard page that **overlays usage metrics on the existing X-post time series** for direct brand-by-brand comparison.

**Primary proxies (deeper coverage):**
1. **OpenRouter** — JSON API at `https://openrouter.ai/api/v1/datasets/rankings-daily`. Top 50 models/day by total tokens, ~12 months of history, Bearer auth, 30 req/min · 500 req/day.
2. **opencode.ai /data** — public leaderboard at `https://opencode.ai/data` plus per-model pages at `https://opencode.ai/data/{brand}/{model}`. Daily token volume, unique users, cost, cache ratio, geo. **HTML scrape** (no public JSON XHR endpoint was discoverable).

**Optional proxies (lower priority, same generic schema):**
- Hugging Face — derived by aggregating the existing `products` table from plan 2026-06-21-001 (sum `downloads`/`likes` per `brand_id`).
- Ollama library — per-model "Downloads" aggregate (HTML scrape; only "Downloads" is exposed, not per-tag pull counts).
- npm + PyPI SDK downloads — public JSON APIs at `api.npmjs.org` and `pypistats.org`.
- GitHub stars — `api.github.com/repos/{owner}/{repo}` (no clone/traffic).
- ModelScope — `api.modelscope.cn` (probe pending from fuchitalee; the model registry is the natural Chinese proxy and complements OpenRouter's Western bias).

**What this plan delivers:**
- Migration 007: `usage_sources`, `source_brand_keys`, `usage_samples`.
- Collector modules under `x_monitor/usage/` (one per source), with a thin orchestrator + CLI subcommand.
- New `/usage` dashboard route + topbar 4th tab; multi-line chart per source, with an overlay toggle to compare against the X-post time series from the same brands.
- A **bias report** as a companion doc (`docs/research/2026-06-22-161413-usage-proxies-bias-report.md`) — OpenRouter + opencode bias analyses are an explicit user deliverable.

## Problem Frame

Today the dashboard tracks what *people say* about AI brands on X. It does not track what *people use*. The market-share story (which brand is gaining, which is fading) is inferred from conversation volume, not actual consumption.

The user wants to:
1. **Expose the endpoints** of OpenRouter rankings + opencode telemetry, and identify any additional credible proxies.
2. **Collect this data** daily.
3. **Compare** the consumption signal with the existing X-post signal — same brands, same time axis, side-by-side.
4. **Produce charts** analogous to the existing `combined` page (multi-brand line chart) but with a second axis for usage.
5. **Report the biases** of OpenRouter and opencode user bases (an explicit deliverable: "what biases for each of these two sites have in terms of user bases").

Without this layer, "growth" claims on the dashboard are pure conversation-velocity proxies — meaningful but blind to actual model usage.

## Requirements Trace

- **R1.** Daily (or weekly) collection of per-brand usage metrics from OpenRouter + opencode; idempotent re-runs.
- **R2.** A generic time-series store so adding a new proxy is a new collector module, not a new table.
- **R3.** Every collected metric must be attributable to a `brand_id` in the existing `brands` table.
- **R4.** A new dashboard route `/usage` that renders per-source time series (one line per brand per source) with a toggle to overlay the X-post daily totals.
- **R5.** A bias report covering at minimum OpenRouter + opencode; the report must be specific (over/under-represents, demographic skew, technical vs non-technical).
- **R6.** Citation requirements respected: the OpenRouter API requires "Source: OpenRouter (openrouter.ai/rankings), as of {as_of}." when republished. The dashboard must render this footer when OpenRouter data is shown.
- **R7.** HF (via `products` aggregation) integrates without duplicating plan 2026-06-21-001; the existing `products` table remains the catalog, the new collector is a thin read-side rollup.
- **R8.** All collector failures must be isolated: a bad response from one source must not abort other sources or the X-monitor pipeline.
- **R9.** Rate limits respected: OpenRouter caps 30 req/min · 500 req/day. The collector must budget its calls (1 request per run covers a 30-day window via `start_date`/`end_date`).
- **R10.** Backfill: on first run, fetch the maximum available window (OpenRouter: 2025-01-01 to present; opencode: earliest date visible on the per-model page) so the chart has historical context from day one.

## Scope Boundaries

- **In scope:** OpenRouter + opencode as Tier-1 collectors; HF (via existing `products`), Ollama, npm, PyPI, GitHub stars, ModelScope as Tier-2 collectors; `/usage` dashboard page; bias report.
- **Out of scope:** Reddit, GitHub Discussions, Discord, Slack, search-trend-based proxies (Google Trends scraping is fragile, deferred); per-user profiling; per-prompt/response analysis; any "anomaly detection" on usage (just collect + display).
- **Out of scope:** Rewriting the existing X-post pipeline. The X-post data lives in `posts`/`post_brand_signals` and is consumed read-only by the new `/usage` page when the overlay is toggled on.
- **Out of scope:** Promoting opencode as a primary, fully-trusted ranking source. opencode's bias profile is narrower than OpenRouter's (see Bias Report §3). It is valuable as a *secondary* signal — particularly for Chinese OSS models where it gives one of the few public views — but not as a stand-alone ranking.

## Context & Research

### Endpoint inventory (the "expose the endpoints" deliverable)

| Source | Endpoint | Method | Auth | Rate limit | Update freq | Data shape (relevant fields) | Verdict |
|---|---|---|---|---|---|---|---|
| **OpenRouter** | `https://openrouter.ai/api/v1/datasets/rankings-daily?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | GET | `Authorization: Bearer <OPENROUTER_API_KEY>` | 30 req/min, 500 req/day/key | Daily, top-50 per day from 2025-01-01 onward | `{data: [{date, model_permaslug, total_tokens (string)}, …], meta: {as_of, start_date, end_date, version: "v1"}}`. Top 50 + an `"other"` aggregate. **Caveat: tokenizers differ across providers — "a token" is not directly comparable across rows.** | **PRIMARY.** Stable, official, top-50 with daily granularity. |
| **opencode.ai** | `https://opencode.ai/data` (leaderboard) | GET (HTML) | None | None published (be polite) | Page updated daily (visible "Page Updated: Jun 22, 05:50 AM UTC"). Range filters: 1D / 1W / 2W / 1M / 2M. Audience filters: All Users / Zen / Go. | HTML with embedded daily token totals (cumulative), leaderboard (rank, model, brand, tokens, WoW %), unique users, market share, geo, session/token cost, cache ratio. | **PRIMARY** for the per-model page scrape; leaderboard HTML is brittle but the per-model pages are stable. |
| **opencode.ai (per model)** | `https://opencode.ai/data/{brand}/{model-slug}` | GET (HTML) | None | None published | Daily | Sections: Overview (tokens, unique users, sessions, share, momentum), Usage (daily token series), Users (daily unique-user series), Efficiency (cost/cache), Geo, Peers. | **PRIMARY** for collector; scrape daily token series and aggregate to brand. |
| **Hugging Face** | `https://huggingface.co/api/models?author={org}&limit=100` (cursor-paginated) | GET | Optional `Bearer $HF_TOKEN` (raises rate limits) | Anonymous ~100 req/h, authed much higher | Stats fields (`downloads`, `likes`, `trendingScore`) reflect real-time server counters. | `[{id, downloads, likes, trendingScore, createdAt, pipeline_tag, library_name, tags, private}, …]`. **NOTE: `downloads` here is an all-time count, not 30-day.** The `products` table from plan 2026-06-21-001 already persists this; we read from there. | **SECONDARY** (read from `products`, not a new fetch). |
| **Ollama library** | `https://ollama.com/library/{model}` | GET (HTML) | None | None published | Daily | Hero "X.XM Downloads" aggregate + per-tag table (size, context, modality). **No per-tag pull counts** — only the aggregate per model page. | **SECONDARY** (HTML scrape, lower signal density). |
| **npm** | `https://api.npmjs.org/downloads/point/last-week/{pkg}` | GET | None | None published | Live | `{downloads: int, start: "YYYY-MM-DD", end: "YYYY-MM-DD", package: string}`. Also `last-day`, `last-month`, `last-year`, `date-range:start:end`. | **SECONDARY** (cleanest non-OAuth proxy). |
| **PyPI** | `https://pypistats.org/api/packages/{pkg}/recent` | GET | None | None published | Live | `{data: {last_day, last_week, last_month: int}, package, type: "recent_downloads"}`. | **SECONDARY** (clean). |
| **GitHub** | `https://api.github.com/repos/{owner}/{repo}` | GET | Optional `Bearer $GH_TOKEN` (raises 60→5000 req/h) | 60 req/h anon, 5000/h authed | Live | `{stargazers_count, forks_count, open_issues_count, pushed_at, …}`. **GitHub does NOT expose clone or traffic counts via API long-term.** | **SECONDARY** (stars only; weak usage signal). |
| **ModelScope** | `https://api.modelscope.cn/api/v1/models?author={author}&page=1&page_size=50` (probe pending from fuchitalee — probe returned ECONNREFUSED from this Mac, expected) | GET | `Authorization: Bearer $MODELSCOPE_TOKEN` if private | Unknown | Unknown | TBD — confirm during implementation. | **SECONDARY** but **high priority** because ModelScope is Qwen's home turf; OpenRouter's weak on Chinese-domestic OSS. |
| **Google Trends** | trends.google.com | (scrape) | None | None published | Daily | Trending search interest by region. | **DEFERRED.** Fragile scraping, no public API. |
| **Artificial Analysis** | artificialanalysis.ai | (probe) | None | Unknown | Unknown | Benchmarks + price-perf. **No public usage volume** — only popularity/leaderboard. | **DEFERRED.** Benchmarks, not usage. |

### Bias report (the "report on what biases" deliverable)

The bias report lives at `docs/research/2026-06-22-161413-usage-proxies-bias-report.md`. It covers, for OpenRouter and opencode specifically (and a brief note per Tier-2 source), the following structure per source:

- **Who uses it** (user-base description: developer vs consumer; hobbyist vs enterprise; geographic concentration; technical level).
- **What it over-represents** (specific AI brands/models whose usage is inflated relative to the global market).
- **What it under-represents** (specific brands/models whose usage is hidden — the long tail, self-hosted users, app/IDE users, Chinese-domestic-only models).
- **Implication for the comparison chart** (how to caveat the visual).

Key bias findings (full prose in the bias report):

- **OpenRouter:** aggregator-of-aggregators with a Western/API-first user base. Heavily over-represents Anthropic + OpenAI in `programming` category, and any model with free credits. Per the State of AI 2025 report, US 47%, Germany 8%, China 6% of token volume; reasoning models >50% of token share; programming category is second-largest after roleplay. **Under-represents** Chinese-domestic-only models (Kimi-K2.7, DeepSeek V4 family, Qwen, GLM, MiMo) that mostly run on ModelScope / direct provider endpoints; **under-represents** self-hosted models (Ollama, vLLM, llama.cpp); **over-represents** routing through aggregator (a "request" on OpenRouter is not the same as a "user" anywhere — a developer routing across 5 providers counts 5x).

- **opencode.ai:** terminal/CLI coding agent user base — predominantly Western indie developers and power users. The `data` page covers the **subset who opted into Zen or Go** (the curated + low-cost tiers) plus an "All Users" filter that presumably aggregates opt-in telemetry. **Over-represents** open-weight Chinese models that ship on Hugging Face and run cheaply on OpenRouter/DeepSeek-direct (deepseek-v4-flash is #1 with 48% of observed 2M volume per the per-model page). **Under-represents** consumer-facing AI products (ChatGPT, Claude.ai, Gemini app) entirely — opencode users are by definition API-style consumers. **Heavily concentrated in coding workloads** — coding agent benchmark is the lead use case. **Telemetry is opt-in**, so the user base is a self-selected cohort. **No mobile, no enterprise IDE, no consumer app.**

- **Hugging Face:** researchers + ML practitioners; over-represents open-weights; under-represents proprietary API users.
- **Ollama:** hobbyists + local-run; over-represents "runs on a laptop"; under-represents enterprise/production.
- **npm/PyPI:** developer ecosystem skew; reflects SDK install count, not production API usage.
- **GitHub stars:** pure popularity; weak usage signal; vanity-prone.

The bias report also includes a **reconciliation table** showing how the X-post signal compares to each usage signal — both feed into the same brand_id, and a divergence (e.g. "X post volume up 200% but OpenRouter share flat") is the kind of insight the `/usage` page is designed to surface.

### Relevant code and patterns (x-monitor target)

- `x-monitoring/x_monitor/store.py::Store.apply_migrations` — forward-only migration runner over `MIGRATIONS_DIR.glob("*.sql")` tracked in `_migrations(version, applied_at)`. Auto-applies on `Store(...)` open when `auto_migrate=True`. New migration is `x_monitor/migrations/007_usage_telemetry.sql`. **Do not insert into `_migrations` from the SQL.**
- `x-monitoring/x_monitor/store.py::Store.upsert_account` and the post-004 upsert pattern (`INSERT … ON CONFLICT(…) DO UPDATE`) — the new `usage_samples` writer follows the same idempotent shape.
- `x-monitoring/x_monitor/store.py::Store.read_brands` returns the 12 brand rows (incl. `_unattributed` sentinel). The new collector uses this to enumerate which brand_ids to write for.
- `x-monitoring/x_monitor/templates/grid.html.j2` / `treemap.html.j2` / `combined.html.j2` topbar pattern — add a 4th `<a class="view-tab">` for `/usage`. `is-active` set by the same `request_endpoint` context.
- `x-monitoring/x_monitor/static/trend-chart.js` and `combined-chart.js` — defensive destroy-before-create pattern (`var prior = Chart.getChart(canvas); if (prior) prior.destroy();`) MUST be copied into the new usage-chart module verbatim.
- `x-monitoring/x_monitor/dashboard.py::serialize_combined_chart` (line ~310+; per the combined-chart plan §Unit 1) — the data-assembly pattern to mirror: build `brand_day_metric_counts` nested dict, materialize `series[brand] = list[float]` per metric.
- `x-monitoring/x_monitor/dashboard.py::MODEL_DISPLAY_NAMES` and `MODEL_ACCENT_COLORS` (lines 38, 53) — read but not modified. The new usage chart uses the same brand_id → display_name / accent_color mappings.
- `x-monitoring/x_monitor/__main__.py` subcommand registration pattern (lines 738+) — add a new `usage-collect` parser.
- `x-monitoring/x_monitor/config.py` — add an optional `usage:` section in `config.yaml` for source enable/disable + per-source budget (or keep the registry in the DB; **open question, see below**).

### Existing plan references

- **`docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md`** (status: completed; code in worktree `worktrees/hf-products/`, branch `feat/hf-products-crawler`): the `products` table + `brand_hf_orgs` table + `hf_client.py` + `hf_products.py`. **This plan's HF collector does NOT duplicate that work** — it reads the `products` table and writes brand-aggregated rows to `usage_samples`. Migration 007 follows migration 006 (`006_quote_capture_tracking.sql`) on the timeline; the HF plan's claimed migration 005 was preempted by the quote-capture work and will land as 007 in the merged branch.
- **`docs/plans/2026-06-19-003-feat-combined-chart-page-plan.md`** (status: completed): the multi-brand line-chart pattern. The new `/usage` page extends this with a per-source filter, an X-post overlay toggle, and a citation footer.
- **`docs/plans/2026-06-17-002-feat-finviz-treemap-front-page-plan.md`**: precedent for an additive topbar tab without disturbing existing routes.
- **`docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md`**: the 11 enabled brands that the collectors enumerate.

### External references

- OpenRouter `rankings-daily` API spec: `https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily`. Verbatim response shape and rate limits captured in the Endpoint Inventory table above. **Citation requirement**: "Source: OpenRouter (openrouter.ai/rankings), as of {as_of}." — render in the dashboard footer when OpenRouter data is visible.
- OpenRouter State of AI 2025 (`https://openrouter.ai/state-of-ai`): one-time PDF, 100T+ token study. The brand-level "Top OSS Model Authors by trillions of tokens" table is the single best public benchmark for which Chinese OSS labs are actually big in OpenRouter (DeepSeek 14.37T, Qwen 5.59T, MiniMax 1.26T, Z-AI 1.18T, MoonshotAI 0.92T). Use this as a calibration reference, not as a recurring data source.
- opencode.ai: the only public data source is the HTML at `/data` and `/data/{brand}/{model}`. No XHR endpoint was discoverable via WebFetch; client-side fetch from a JS bundle. **Plan assumes HTML scrape**; if the implementation later finds the XHR endpoint, swap the parser with no DB impact.
- Hugging Face: `https://huggingface.co/docs/hub/en/api` and `https://huggingface.co/docs/hub/en/models-download-stats`. The `downloads` field is an all-time count (server-side filtered by `countDownloads` rules per library — e.g. GGUF counts every file download, transformers only counts `config.json`).
- Ollama: `https://docs.ollama.com/api/tags` is the **local** API (lists installed models); the public library is HTML only at `https://ollama.com/library/{model}`. There is a third-party API mirror at `https://github.com/frefrik/ollama-models-api` but it is not authoritative.
- npm: `https://api.npmjs.org/` — no auth, no rate limit, public.
- PyPI: `https://pypistats.org/api/packages/{pkg}/recent` — no auth, no rate limit, public. (The `pypistats.org` website is third-party, but the `/api/...` path is a community standard.)
- GitHub: `https://docs.github.com/en/rest/repos/repos#get-a-repository` — anonymous 60 req/h, authed 5000 req/h.

## Key Technical Decisions

- **D1. One generic time-series table, `usage_samples`, not per-source tables.** Avoids a migration per new source; the schema is `source × brand_id × metric × window × sampled_at` with the value and a `raw_json` payload snippet. Mirrors how `post_brand_signals` is a generic fact table for X-post signals.
- **D2. Per-source brand identification via `source_brand_keys`.** Different sources name the same brand differently: OpenRouter uses `deepseek/deepseek-chat`; opencode uses `deepseek/deepseek-v4-flash`; npm uses `@anthropic-ai/sdk`; HF uses `Qwen`. A single `(source, brand_id, key)` mapping table handles all of them. Curated seed with `confirmed=1`; discover-and-flag for unknowns (mirroring plan 2026-06-21-001's hybrid org-resolution pattern). The HF `brand_hf_orgs` table from the existing plan is treated as a special case (or generalized into `source_brand_keys` with `source='huggingface'`); **defer to implementation**.
- **D3. OpenRouter collector uses a single request per run.** The `start_date`/`end_date` query covers a 30-day window in one call. Rate budget: 30 runs/mo ≈ 1 req/day → 30 req/mo → 0.06% of the 500 req/day limit, plenty of headroom for retries.
- **D4. opencode collector scrapes the per-model page, not the leaderboard.** Per-model pages are stable URLs (`/data/{brand}/{model}`), content-rich, and structurally identical across models. The leaderboard is brittle and time-windowed; skip it.
- **D5. HF collector reads from the existing `products` table; no new HTTP calls.** The HF plan's `products` table is the source of truth; the new collector is a single SQL `SELECT brand_id, SUM(downloads), SUM(likes) FROM products GROUP BY brand_id` and writes one `usage_samples` row per (brand, metric). This is the cleanest integration with the existing work.
- **D6. Tier-2 sources are gated by `usage_sources.enabled`.** Default-enabled: OpenRouter, opencode, HF. Default-disabled: Ollama, npm, PyPI, GitHub, ModelScope (operator opts in via the `usage_sources` table; the CLI's `--all` flag enables all).
- **D7. `/usage` page is a NEW 4th topbar tab, additive.** Pattern mirrors the combined-chart and treemap precedents. The 4 routes (existing `/`, `/grid`, `/combined`, new `/usage`) and the topbar nav in all templates are updated together. No changes to existing routes.
- **D8. X-post overlay is a toggle, not a separate view.** The chart defaults to showing the chosen usage metric; an "Overlay X posts" checkbox adds a second line per brand on a secondary y-axis (right side). Single Chart.js chart with a `yAxisID: 'y_posts'` for the posts line and `yAxisID: 'y_tokens'` for the usage line. Mirrors the existing `--bar-*` token aesthetic.
- **D9. Citation footer is conditional.** The `/usage` page renders "Source: OpenRouter (openrouter.ai/rankings), as of {meta.as_of}" only when OpenRouter is one of the visible sources. Same conditional footer for opencode ("Source: opencode.ai/data") and HF.
- **D10. Bias report is a first-class artifact, not a comment.** Lives at `docs/research/2026-06-22-161413-usage-proxies-bias-report.md`, committed to the repo, linked from the `/usage` page header so operators read it once before drawing conclusions.
- **D11. Idempotent collectors, append-only store.** Every collector run writes one row per (source, brand, metric, window, sampled_at). Re-running the same day overwrites only the latest row (the upsert key includes `sampled_at`); historical days are immutable. No cleanup job needed.
- **D12. The `usage_samples.value` is REAL, not INT.** Tokens can be in trillions; we need full double precision. `unit` is stored alongside (`'tokens'`, `'count'`, `'pct'`, `'usd'`).

## Open Questions

### Resolved During Planning

- Which proxies are Tier-1 vs Tier-2? **Tier-1: OpenRouter + opencode; Tier-2: HF (via products), Ollama, npm, PyPI, GitHub, ModelScope.** Operator enables Tier-2 via `usage_sources.enabled`.
- How is the brand key for each source populated? **Curated seed in `source_brand_keys` at migration time; discover-and-flag for unknowns at runtime.** The seed is small (~50 rows) and the mapping is stable.
- Where does the per-source config live (enable/disable, budgets)? **`usage_sources` table.** Optional `usage:` section in `config.yaml` for the per-source CLI defaults (default 30-day window, default brands to enumerate).
- How is the `/usage` page triggered? **Same htmx poll as the other dashboard pages**, reusing `config.dashboard.poll_seconds`.

### Deferred to Implementation

- Whether to fold the existing `brand_hf_orgs` table into `source_brand_keys` (`source='huggingface'`) or leave it alone. **Leave alone for now** — the HF plan's tests and Store methods reference `brand_hf_orgs` directly; generalizing is a separate refactor.
- Exact `unit` taxonomy for the `usage_samples.unit` column. **Use the set `{tokens, count, pct, usd}` for now; widen if a source needs a new unit.**
- How to handle the OpenRouter "token-comparability caveat" in the chart UI. **Render a "?" tooltip on the usage line that explains the per-provider tokenizer difference** when the user hovers. Not a top-level disclaimer (too noisy).
- Whether to add a `/usage/api` JSON endpoint for external consumers. **Add it** (mirrors `/api/combined.json`), so the bias report can be cross-referenced from outside the dashboard.
- Exact ModelScope API shape — needs a probe from fuchitalee. **Open question surfaced by research; not blocking.**
- Whether `usage_samples` should retain `raw_json` for ALL rows or only a sample. **Retain for first run per (source, brand, day); cap the JSONL audit at last 30 rows per source to avoid bloat.**
- Period for the `/usage` time axis default. **90 days** (gives the chart historical context while staying focused on the most recent quarter).

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.*

```
                            +----------------------------+
   +------------------+     |  external proxy endpoints  |
   | CLI:             |     |  - openrouter rankings     |
   | x_monitor        |     |  - opencode.ai/data        |
   |   usage-collect  |     |  - HF products (read-side) |
   +--------+---------+     |  - ollama library          |
            |               |  - npm / pypi APIs         |
            v               |  - GitHub stars            |
   +------------------+     |  - modelscope (TBD)        |
   | x_monitor/usage/ |     +-----------+----------------+
   |  orchestrator    |                 |
   |  openrouter.py   | <---------------+
   |  opencode.py     |  (httpx GET / BS4 parse)
   |  huggingface.py  |
   |  ollama.py       |                 |
   |  npm.py          |                 |
   |  pypi.py         |                 |
   |  github.py       |                 |
   +--------+---------+                 |
            |                           |
            v                           v
   +------------------+      +----------------------+
   | Store            |      | source_brand_keys    |
   |  .write_usage_   |      |  + brands table      |
   |   sample(...)    | ---> |  (resolved at write) |
   +--------+---------+      +----------------------+
            |
            v
   +------------------+      +------------------+
   | usage_samples    |      | /usage dashboard |
   | (time-series)    | <--> |  - per-source    |
   +------------------+      |  - overlay X     |
                             |  - bias footer   |
                             +------------------+
```

The four data flow stages map to implementation units: **schema** (Unit 1) → **collectors** (Unit 2, parallelizable per source) → **orchestrator + CLI** (Unit 3) → **dashboard** (Unit 4, depends on Unit 1 + Unit 3 writing data).

## Implementation Units

- [ ] **Unit 1: Migration 007 — `usage_sources` + `source_brand_keys` + `usage_samples`**

**Goal:** Introduce the three new tables and seed the `usage_sources` registry + curated `source_brand_keys` for Tier-1 sources.

**Requirements:** R2, R3, D1, D2, D6

**Dependencies:** Migration 006 (provides `brands` and `_unattributed` sentinel).

**Files:**
- Create: `x-monitoring/x_monitor/migrations/007_usage_telemetry.sql`
- Test: `x-monitoring/tests/test_migration_007_usage_telemetry.py`

**Approach:**
- `BEGIN; … COMMIT;`. Do **not** insert into `_migrations`. `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` for re-apply safety.
- `usage_sources(source TEXT PRIMARY KEY, display_name TEXT NOT NULL, kind TEXT NOT NULL, endpoint_url TEXT, citation_note TEXT, enabled INTEGER NOT NULL DEFAULT 1, last_collected_at TEXT, added_at TEXT NOT NULL)`. `kind` ∈ `{json_api, html_scrape, db_read}`.
- `source_brand_keys(source TEXT NOT NULL, brand_id TEXT NOT NULL, key TEXT NOT NULL, key_kind TEXT NOT NULL DEFAULT 'slug', confirmed INTEGER NOT NULL DEFAULT 1, discovered_via TEXT, added_at TEXT NOT NULL, PRIMARY KEY(source, brand_id, key), FOREIGN KEY(brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE)`. Index `(source, brand_id)`.
- `usage_samples(source TEXT NOT NULL, brand_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL, window TEXT, sampled_at TEXT NOT NULL, raw_json TEXT, PRIMARY KEY(source, brand_id, metric, window, sampled_at), FOREIGN KEY(brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE)`. Index `(source, sampled_at DESC)`, `(brand_id, sampled_at DESC)`. `unit` ∈ `{tokens, count, pct, usd}`.
- Seed `usage_sources` with the 8 sources (5 enabled by default: openrouter, opencode, huggingface; 3 disabled by default: ollama, npm, pypi, github, modelscope — operator flips `enabled`).
- Seed `source_brand_keys` with the curated mapping. **Approximate size: 50-80 rows.** Examples:
  - `('openrouter', 'deepseek', 'deepseek/deepseek-chat', 'slug', 1)`
  - `('openrouter', 'qwen', 'qwen/qwen-2.5-72b-instruct', 'slug', 1)`
  - `('openrouter', 'minimax', 'minimax/minimax-m2', 'slug', 1)`
  - `('opencode', 'deepseek', 'deepseek/deepseek-v4-flash', 'slug', 1)`
  - `('opencode', 'minimax', 'minimax/minimax-m3', 'slug', 1)`
  - `('huggingface', 'deepseek', 'deepseek-ai', 'org', 1)`
  - `('npm', 'anthropic', '@anthropic-ai/sdk', 'package', 1)`
  - `('pypi', 'openai', 'openai', 'package', 1)`

  Operator adds missing rows via SQL after first run (or `upsert_source_brand_key` helper).

**Patterns to follow:** migration 004 + 006 (transactional, seeded, FK conventions, `_migrations` loader).

**Test scenarios:**
- Happy path: apply 007 on a fresh DB with 001-006 applied → all 3 tables exist with expected columns; curated seed rows present; `_migrations` records version 7.
- Edge case: `usage_samples.brand_id` FK rejects a brand_id not in `brands` (insert fails under `PRAGMA foreign_keys=ON`); `ON DELETE CASCADE` clears `usage_samples` rows when a brand is deleted.
- Edge case: re-running 007 is a no-op — no duplicate seed rows, no error.
- Integration: `Store(...)` with `auto_migrate=True` brings a brand-new DB up through 007 and `read_brands()` still returns the 12 seeded brands.

**Verification:** A fresh `x_monitoring.db` reaches schema version 7 with all three tables queryable and the seed present; existing 001-006 tables and data untouched.

---

- [ ] **Unit 2: Per-source collector modules under `x_monitor/usage/`**

**Goal:** A collector per source, each with: `collect(*, brands, days) -> list[UsageSample]`. Pure function, no side effects, no I/O at import time. Used by the orchestrator in Unit 3.

**Requirements:** R1, R8, R9, R10, D3, D4, D5, D11

**Dependencies:** Unit 1.

**Files:**
- Create: `x-monitoring/x_monitor/usage/__init__.py`
- Create: `x-monitoring/x_monitor/usage/openrouter.py`
- Create: `x-monitoring/x_monitor/usage/opencode.py`
- Create: `x-monitoring/x_monitor/usage/huggingface.py`
- Create: `x-monitoring/x_monitor/usage/ollama.py` (Tier-2)
- Create: `x-monitoring/x_monitor/usage/npm.py` (Tier-2)
- Create: `x-monitoring/x_monitor/usage/pypi.py` (Tier-2)
- Create: `x-monitoring/x_monitor/usage/github.py` (Tier-2)
- Create: `x-monitoring/x_monitor/usage/types.py` (dataclasses: `UsageSample`, `CollectorResult`)
- Test: `x-monitoring/tests/test_usage_openrouter.py`
- Test: `x-monitoring/tests/test_usage_opencode.py`
- Test: `x-monitoring/tests/test_usage_huggingface.py`

**Approach:**

- `types.py`:
  ```python
  @dataclass(frozen=True)
  class UsageSample:
      source: str
      brand_id: str
      metric: str
      value: float
      unit: str
      window: str  # "1d", "7d", "30d", "all_time", etc., or None
      sampled_at: str  # ISO 8601
      raw_json: dict | None = None
  ```

- `openrouter.py`:
  - `OPENROUTER_BASE = "https://openrouter.ai"`, `openrouter_token()` reads env.
  - `fetch_rankings_daily(*, start_date, end_date, retries=3)` — single `GET /api/v1/datasets/rankings-daily?start_date=…&end_date=…`, exponential backoff, 30s timeout, 429 → retry-with-backoff.
  - `collect(*, brands, days=30)` — fetches the window, joins rows to `source_brand_keys` on `model_permaslug`, returns one `UsageSample(source='openrouter', brand_id=…, metric='tokens', value=total_tokens, unit='tokens', window='1d', sampled_at=date)` per (date, brand) row. Brands not in the join are dropped (they're in the `other` aggregate — accept that loss or surface a warning).
  - Backfill: on first run, default `days=365` (capped at OpenRouter's 2025-01-01 floor).

- `opencode.py`:
  - `fetch_model_page(brand, model_slug) -> tuple[BeautifulSoup, str]` — `GET https://opencode.ai/data/{brand}/{model}` with 30s timeout, 1-2s polite sleep between requests.
  - `parse_overview(soup) -> dict` — extract "Tokens: 42T", "Unique Users: 567K", "Sessions: 5,912,523", "Token Share: 48%", "Momentum: +22,385%" from the Overview section.
  - `parse_daily_tokens(soup) -> list[tuple[date, int]]` — extract the "Daily Token Volume" series as a list of (date, tokens) pairs.
  - `collect(*, brands, days=30)` — for each brand, find all model pages from `source_brand_keys`; for each (brand, model) pair, parse the daily-tokens series; aggregate per brand per day (sum across models of the same brand).
  - The 18-model leaderboard URL set can be hardcoded in `source_brand_keys` for v1; runtime discovery of new models is deferred.

- `huggingface.py`:
  - No HTTP. `collect(*, brands, days=None)` — `SELECT brand_id, SUM(downloads), SUM(likes) FROM products GROUP BY brand_id` (with optional date filter on `updated_at`). Returns one `UsageSample(metric='downloads_all_time', value=…, unit='count', window='all_time', sampled_at=now)` per brand.
  - Reads from the existing `products` table populated by plan 2026-06-21-001.

- `ollama.py`, `npm.py`, `pypi.py`, `github.py`:
  - Each follows the same `collect(*, brands, days) -> list[UsageSample]` shape.
  - Ollama: scrape `https://ollama.com/library/{model}` for "X.XM Downloads" aggregate. No per-tag pull counts.
  - npm: `https://api.npmjs.org/downloads/point/last-week/{pkg}` for each brand's primary SDK package.
  - PyPI: `https://pypistats.org/api/packages/{pkg}/recent` for each brand's primary PyPI package.
  - GitHub: `https://api.github.com/repos/{owner}/{repo}` for each brand's primary model repo; record `stargazers_count` as `metric='stars'`.

- Shared HTTP client: `x_monitor/usage/_http.py` with `get_json(url, *, headers=None, retries=3, base_backoff=0.5, max_timeout=30)` using httpx. Mirror the `hf_client.hf_get` shape from plan 2026-06-21-001.

- All collectors must handle: network errors (log + skip), 4xx (log + skip), 429 (retry-with-backoff, fail if persistent), JSON parse errors (log + skip), and missing brand keys (drop the row, do not write `_unattributed`).

**Execution note:** Test-first for the HTTP and parse contracts using `respx` / `httpx.MockTransport` (or static HTML fixtures for `opencode.py` — save snapshots of 2-3 real model pages to `tests/fixtures/opencode/`). Network must not be hit in unit tests.

**Patterns to follow:** `x_monitor/apify.py` (existing X-post HTTP client) for the retry/backoff shape; `x_monitor/hf_client.py` (from worktree `worktrees/hf-products/`) for the function signatures.

**Test scenarios (per collector):**
- Happy path: mocked response → expected `UsageSample` list, brand mapping correct, units/windows correct.
- Happy path: re-running with the same `sampled_at` produces the same list (idempotent).
- Edge case: a model slug in the response that has no `source_brand_keys` row is dropped (not written as `_unattributed`).
- Edge case: empty response (0 models) → empty list, no error.
- Error path: HTTP 500 → retried then surfaced as a `CollectorResult` error (not a crash).
- Error path: HTTP 429 → exponential backoff, eventual success or fail-with-error after N attempts.
- Error path: malformed JSON → `CollectorResult(error="parse_failed")`, no crash.
- Integration: `collect()` output round-trips through `Store.write_usage_sample(...)` and re-queries back identically.

**Verification:** Each collector has unit tests; the orchestrator (Unit 3) smoke-tests all of them with a 1-day window on a fresh DB.

---

- [ ] **Unit 3: Orchestrator + CLI subcommand + periodic runner**

**Goal:** A single entry point that runs all enabled collectors, writes results to the DB, and is callable from the command line + a scheduled script.

**Requirements:** R1, R8, R11, D6

**Dependencies:** Unit 1, Unit 2.

**Files:**
- Create: `x-monitoring/x_monitor/usage/orchestrator.py`
- Modify: `x-monitoring/x_monitor/store.py` (add `read_usage_sources`, `read_source_brand_keys`, `write_usage_sample`, `read_usage_samples`)
- Modify: `x-monitoring/x_monitor/__main__.py` (add `usage-collect` subcommand)
- Create: `x-monitoring/scripts/run_usage_collect.sh` (periodic runner)
- Test: `x-monitoring/tests/test_usage_orchestrator.py`
- Test: `x-monitoring/tests/test_usage_cli.py`

**Approach:**
- `orchestrator.py::collect_all(*, sources=None, brands=None, days=30, dry_run=False) -> dict[str, CollectorResult]`:
  - Reads `usage_sources WHERE enabled=1` (or the `sources` filter list).
  - Reads `source_brand_keys` for the enabled sources.
  - For each source, calls the corresponding `x_monitor/usage/{source}.collect(...)` with per-source isolation (try/except → `CollectorResult(error=str(e))`).
  - Aggregates results, writes via `Store.write_usage_sample(...)` (upsert on the PK).
  - Updates `usage_sources.last_collected_at`.
  - Returns a `dict[source -> CollectorResult]` for logging / CLI summary.
- `Store.write_usage_sample(sample)` — `INSERT INTO usage_samples(...) ON CONFLICT(source, brand_id, metric, window, sampled_at) DO UPDATE SET value=excluded.value, unit=excluded.unit, raw_json=excluded.raw_json`.
- `Store.read_usage_samples(*, source=None, brand_id=None, since=None, until=None) -> list[UsageSample]` — for the dashboard.
- CLI: `python -m x_monitor usage-collect [--source openrouter] [--brands deepseek,qwen] [--days 30] [--dry-run] [--all]` (the `--all` flag enables Tier-2 sources for one run only without flipping `usage_sources.enabled` permanently).
- `scripts/run_usage_collect.sh` mirrors the existing `scripts/run_hf_products.sh` and `scripts/run_x_monitor_*.sh` patterns: source `~/.env.secrets` (for `OPENROUTER_API_KEY`), PID guard, log to `logs/`, exit non-zero on collector errors.
- Periodic scheduling (LaunchAgent / cron at 1h cadence) is a documented operator step, not coded here. The X-monitor `run` script already has the LaunchAgent pattern to mirror.

**Patterns to follow:** `x_monitor/run.py::RunPipeline.execute` (the X-post pipeline) for the per-stage try/except isolation; top-gun `run_hf_collector.sh` for the secrets-sourcing + logging pattern.

**Test scenarios:**
- Happy path: `collect_all(sources=['openrouter', 'opencode'], days=1)` with mocked collectors writes 2 × N samples to `usage_samples` (N = number of brands per source).
- Happy path: `--dry-run` resolves sources and brand keys but writes nothing.
- Edge case: one source raises → its result is `{error: ...}`, the other source still completes; the run returns a dict with one error and one success.
- Edge case: re-running the same day → upsert overwrites, no duplicate rows.
- Integration: `read_usage_samples(source='openrouter', since='2026-06-15')` returns the expected time range.
- Error path: missing `OPENROUTER_API_KEY` env var → `CollectorResult(error="missing_openrouter_token")`, other sources still run.
- CLI: `python -m x_monitor usage-collect --help` lists flags; `--dry-run --source openrouter` resolves + gates + reports without writing.

**Verification:** `python -m x_monitor usage-collect --source openrouter --days 7 --dry-run` reports the brand match rate and a per-source sample count. A real run against the live OpenRouter + opencode APIs (operator-confirmed) populates `usage_samples` for the 12 brands.

---

- [ ] **Unit 4: `/usage` dashboard route + chart module + bias-report link + citation footer**

**Goal:** A new 4th topbar tab at `/usage` that renders per-source usage time series with an X-post overlay toggle, the bias-report link, and conditional citation footers.

**Requirements:** R4, R5, R6, D7, D8, D9, D10

**Dependencies:** Unit 1, Unit 3 (data must exist to render).

**Files:**
- Create: `x-monitoring/x_monitor/templates/usage.html.j2`
- Create: `x-monitoring/x_monitor/templates/_usage_chart.html.j2`
- Create: `x-monitoring/x_monitor/static/usage-chart.js`
- Create: `x-monitoring/x_monitor/static/usage-chart.css`
- Modify: `x-monitoring/x_monitor/dashboard.py` (add `serialize_usage_chart`, `_build_usage_payload`, `_usage_sources_for_citation`, the 3 routes, the topbar context)
- Modify: `x-monitoring/x_monitor/templates/grid.html.j2` (add 4th topbar tab)
- Modify: `x-monitoring/x_monitor/templates/treemap.html.j2` (same)
- Modify: `x-monitoring/x_monitor/templates/combined.html.j2` (same)
- Create: `x-monitoring/docs/research/2026-06-22-161413-usage-proxies-bias-report.md`
- Test: `x-monitoring/tests/test_usage_dashboard.py`

**Approach:**

- `serialize_usage_chart(brands, samples, posts_by_brand, *, source, window_days, now)`:
  - For the chosen source, build `brand_day_tokens[brand][iso_date] = float` from `usage_samples`.
  - For the X-post overlay, build `brand_day_posts[brand][iso_date] = int` from `posts` (sum of all 6 signals per day, same as the combined-chart's per-brand total line).
  - Return `{days, series_tokens: {brand: [float]}, series_posts: {brand: [int]}, latest_as_of: str}`.
  - `latest_as_of` is the most recent `sampled_at` across the visible samples (used in the citation footer).
- `_build_usage_payload(db_path, source, window_days, *, include_posts_overlay)`:
  - Opens `Store`, fetches `usage_samples` filtered by source + window, fetches `posts` for the X-post overlay, calls `serialize_usage_chart`, returns the payload + the source's citation note.
- 3 routes (initial / htmx partial / JSON):
  - `GET /usage?source=openrouter&days=90` — render `usage.html.j2`.
  - `GET /api/usage.html?source=…&days=…&overlay=1` — htmx partial, renders `_usage_chart.html.j2`.
  - `GET /api/usage.json?source=…&days=…` — JSON for external consumers.
- 1 source-picker route:
  - `GET /api/usage_source/<source>` — sets a `usage_source` cookie and redirects to `/usage`. Same pattern as the combined-chart's `combined_window` cookie.
- 1 overlay-toggle route (or just a `?overlay=1` query param — decide at implementation time):
  - Either a cookie or a query param. Defer to implementation; recommend cookie (mirrors existing `polarity_window`, `combined_window`).
- Topbar nav becomes 4 tabs in all 4 templates (treemap, combined, grid, usage). `is-active` set by the existing `request_endpoint` context.
- `static/usage-chart.js` — Chart.js v4 multi-axis chart:
  - Y-axis left (`y_tokens`): the per-brand usage line for the chosen source. Stroke = `MODEL_ACCENT_COLORS[brand]`. Hidden by default if no data.
  - Y-axis right (`y_posts`): the per-brand X-post totals. Lighter stroke, dashed. Hidden when overlay is off.
  - Defensive destroy-before-create (copy from `trend-chart.js`).
- Bias-report link: in the topbar header, a small "Bias & methodology" link to `https://github.com/.../docs/research/2026-06-22-161413-usage-proxies-bias-report.md` (or the static-served path). The link is always visible.
- Citation footer: conditional render at the bottom of the chart canvas. If `source == 'openrouter'`, render `"Source: OpenRouter (openrouter.ai/rankings), as of {meta.as_of}."`. Same for opencode + HF.

**Patterns to follow:** `x_monitor/dashboard.py::serialize_combined_chart` (per the combined-chart plan §Unit 1) for the data-assembly shape; the 3-route triplet pattern (initial / htmx partial / JSON); the `trend-chart.js` defensive-destroy pattern; `MODEL_DISPLAY_NAMES` / `MODEL_ACCENT_COLORS` for brand colors.

**Test scenarios:**
- Happy path: `GET /usage?source=openrouter` returns 200, HTML contains the 4th topbar tab, the chart canvas, and the OpenRouter citation footer.
- Happy path: `GET /api/usage.json?source=openrouter&days=30` returns 200, JSON has `{days, series_tokens, series_posts, latest_as_of, citation}`.
- Happy path: `GET /api/usage_source/opencode` sets `usage_source=opencode` cookie and 302s to `/usage`.
- Edge case: source with no samples → empty `series_tokens`, no crash, chart still renders with the empty-state message.
- Edge case: `_unattributed` brand is NOT rendered (filter at serialization).
- Integration: the 4 templates' topbar has exactly 4 `<a class="view-tab">` entries (verified via the `_view_tab` helper used by the other plans).
- Citation: `latest_as_of` is the actual most-recent `sampled_at` in `usage_samples`, not a wall-clock default.

**Verification:** `pytest tests/test_usage_dashboard.py -q` passes; `curl /api/usage.json?source=openrouter | jq '.citation'` returns the OpenRouter citation string. Browser smoke test: load `/usage`, see the chart, toggle the overlay, switch sources.

---

- [ ] **Unit 5: Bias report + operator runbook + config + exports**

**Goal:** Ship the bias report as a first-class artifact, document the operator runbook, and wire the new surfaces into the package exports + CHANGELOG.

**Requirements:** R5, R10 (operability)

**Dependencies:** Units 1-4.

**Files:**
- Create: `x-monitoring/docs/research/2026-06-22-161413-usage-proxies-bias-report.md`
- Modify: `x-monitoring/x_monitor/__init__.py` (export the orchestrator and per-source collectors in `__all__`, lazy if heavy)
- Modify: `x-monitoring/x_monitor/config.py` (validate the optional `usage:` section in `config.yaml` — `default_window_days`, `default_sources`, `tier2_auto_enable`)
- Modify: `x-monitoring/config.yaml` (add an `usage:` section with sensible defaults)
- Modify: `x-monitoring/README.md` (add a "Usage telemetry" section under the architecture overview)
- Modify: `x-monitoring/x_monitor/CHANGELOG.md` (v2.0 entry: usage telemetry layer)
- Modify: `x-monitoring/scripts/run_usage_collect.sh` (LaunchAgent-friendly version with PID guard + log rotation; optional)

**Approach:**

- `docs/research/2026-06-22-161413-usage-proxies-bias-report.md` is structured:
  1. **Executive summary** (1 paragraph: "OpenRouter and opencode are both strong signals but for different audiences; HF + Ollama are weak-but-correlated; npm + PyPI are the noisiest").
  2. **Per-source analysis** (OpenRouter, opencode, HF, Ollama, npm, PyPI, GitHub stars) with: user base, what it over-represents, what it under-represents, implication for the comparison chart.
  3. **Reconciliation table** — for each brand, the X-post daily total vs. the OpenRouter + opencode + HF usage signal, with a "story" column ("rising on X but flat on OpenRouter — hype-driven?").
  4. **Methodology notes** — token-comparability caveat for OpenRouter, opt-in nature of opencode telemetry, snapshot vs. time-series distinction.
  5. **References** — link the OpenRouter State of AI 2025 PDF, the opencode `/data` page, the HF download-stats docs.
- `usage:` section in `config.yaml`:
  ```yaml
  usage:
    default_window_days: 90
    default_sources: [openrouter, opencode, huggingface]
    tier2_auto_enable: false
    openrouter:
      max_calls_per_run: 1
    opencode:
      polite_sleep_seconds: 1.5
  ```
- Operator runbook (in README):
  1. Ensure migration 007 auto-applies on next `Store` open.
  2. `export OPENROUTER_API_KEY=…` (free, sign up at openrouter.ai).
  3. `python -m x_monitor usage-collect --source openrouter --days 30 --dry-run` to preview.
  4. Enable Tier-2 sources in the `usage_sources` table if desired.
  5. `python -m x_monitor usage-collect --all` (or via LaunchAgent).
  6. `curl localhost:5000/usage` to view the chart.
- Periodic scheduling: document the LaunchAgent pattern (the existing `x-monitor` LaunchAgent watches `data/queries/`; add `data/usage/` to the watch list and add a `Run usage-collect` post-run hook, OR a separate LaunchAgent with a 1h interval — implementation-time decision).

**Test scenarios:**
- Test expectation: none — this unit is exports / config / docs. Covered by Units 1-4's tests + import-smoke (`from x_monitor.usage import collect_all`).

**Verification:** `python -c "import x_monitor; print('collect_all' in x_monitor.__all__)"` is True; the bias report renders in the dashboard topbar link; the README has a "Usage telemetry" section.

## System-Wide Impact

- **Interaction graph:** The new collector pipeline is **isolated** from the X-post pipeline. Reads `brands` + (for HF) `products`; writes only `usage_sources`, `source_brand_keys`, `usage_samples`. The dashboard's new `/usage` route reads `usage_samples` + (for the overlay) the existing `posts` table. No interaction with the X-post attribution path.
- **Error propagation:** Per-source isolation — a failing source (OpenRouter 429, opencode scrape timeout, Ollama 5xx) is logged via a `CollectorResult` and the run continues. The X-post pipeline is NOT affected.
- **State lifecycle risks:** (a) Re-runs are idempotent — guaranteed by the PK upsert. (b) Backfill populates historical data without overwriting; only the most recent `sampled_at` is updated. (c) `brand_id` FK with `ON DELETE CASCADE` means deleting a brand clears its `usage_samples` rows. (d) `source_brand_keys` is curated at migration time and augmented at runtime; the `_unattributed` brand is **never** written to `usage_samples` (filter at the collector level).
- **API surface parity:** The `Store` gains `read_usage_sources`, `read_source_brand_keys`, `write_usage_sample`, `read_usage_samples`. These are additive. The 3 new dashboard routes (`/usage`, `/api/usage.html`, `/api/usage.json`) and the 1 source-picker route (`/api/usage_source/<source>`) mirror the existing 3-route triplet pattern.
- **Integration coverage:** Cross-layer integration tests must cover: collector → Store write → dashboard read (full round-trip with mocked network), and source picker cookie → route → chart (cookie-driven source filter).
- **Unchanged invariants:**
  - `brands`, `companies`, `post_*`, `accounts`, `brand_accounts`, `products`, `brand_hf_orgs` are all untouched.
  - The X-post pipeline (`x_monitor/run.py::RunPipeline.execute`) and the existing dashboard routes (`/`, `/grid`, `/combined`, `/treemap`) are untouched.
  - The 3 existing topbar tabs are preserved (only a 4th is added).
  - The `MODEL_DISPLAY_NAMES` and `MODEL_ACCENT_COLORS` mappings are read but not modified.
  - The existing LaunchAgent pattern is preserved (a new one may be added for the usage collector, not replacing the existing).

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| OpenRouter rate limit (30/min, 500/day) is consumed by a runaway backfill | Cap `days` at 365 per call; only 1 call per run; surface `429` in `CollectorResult` and abort that source. |
| opencode HTML page structure changes (silent breakage) | Pin a parser-version field in `usage_sources`; re-run a quick "schema check" before parsing; fall back to a `CollectorResult(error="schema_changed")` and alert. |
| Token-comparability across providers (OpenRouter caveat) | Documented in the bias report; tooltip on the chart explains "tokens not directly comparable across providers" on hover. |
| Per-source brand keys go stale as models are added/renamed | Curated seed at migration time; runtime discover-and-flag surfaces new keys for operator review (mirroring plan 2026-06-21-001's `brand_hf_orgs` hybrid). |
| Opt-in opencode telemetry is a self-selected cohort | Bias report §3 calls this out; the chart legend shows the sample size (e.g. "opencode 1D unique users: 92K"). |
| Ollama aggregate "Downloads" is the only field, no per-tag pull counts | Documented in bias report; collector writes a single sample per (model, day) with the aggregate and `metric='downloads_aggregate'`. |
| npm/PyPI downloads include dev/CI noise | The bias report notes this; the chart labels these as "SDK downloads" not "API usage". |
| GitHub stars are a popularity proxy, not a usage signal | The bias report grades GitHub as Tier-2 + weak; operator can disable per-source via `usage_sources.enabled`. |
| ModelScope API probe pending from fuchitalee (ECONNREFUSED from this Mac) | Surface in the plan as an open question; the collector file exists but is gated on a successful probe. Do not block the rest of the plan on it. |
| Cross-import drift if Unit 2 collectors are parallelized | Spec the `UsageSample` dataclass + `Store.write_usage_sample` signature up front (this plan); reconciliation pass if parallelized. |
| Dashboard rerender with empty `usage_samples` looks broken | Empty-state copy in the chart ("No usage data yet — run `python -m x_monitor usage-collect` to populate"). |

## Documentation / Operational Notes

- **Operator run sequence (first time):**
  1. Migration 007 auto-applies on next `Store` open.
  2. `export OPENROUTER_API_KEY=…` (free, get at openrouter.ai → Settings → Keys).
  3. `python -m x_monitor usage-collect --source openrouter --days 30 --dry-run` to preview the brand match rate.
  4. Inspect the `source_brand_keys` table for any missing mappings; add via SQL.
  5. `python -m x_monitor usage-collect --source openrouter,opencode,huggingface` (no flag = default 30-day window).
  6. Verify with `sqlite3 data/x_monitoring.db "SELECT source, COUNT(*) FROM usage_samples GROUP BY source"`.
  7. Open `http://localhost:5000/usage` in the browser.

- **Adding a new brand's mapping for an existing source:** `INSERT INTO source_brand_keys(source, brand_id, key, key_kind, confirmed, added_at) VALUES(...)`.

- **Adding a new source (Tier-3):** create `x_monitor/usage/{name}.py` with the `collect(*, brands, days)` signature; INSERT into `usage_sources`; seed `source_brand_keys`; restart the dashboard.

- **Refresh cadence:** daily. OpenRouter and opencode both update once per day; running more often is wasteful. A 1h LaunchAgent interval is fine (each run is idempotent).

- **Updating solutions docs:** if a non-obvious bug surfaces (OpenRouter 429 retry pattern, opencode HTML schema change, Ollama aggregate scrape), add a `docs/solutions/2026-MM-DD-...md` entry per existing convention.

- **Citation footer:** when the OpenRouter source is visible on `/usage`, the footer MUST read "Source: OpenRouter (openrouter.ai/rankings), as of {meta.as_of}." (with the `as_of` from the most recent `usage_samples.sampled_at`). This is the OpenRouter's terms of use.

## Sources & References

- **Origin:** user request (this session) — expose OpenRouter rankings + opencode endpoints, additional proxies, bias report, comparison chart.
- **Related code:** `x_monitor/store.py`, `x_monitor/dashboard.py`, `x_monitor/apify.py`, `x_monitor/__main__.py`, `x_monitor/templates/`, `x_monitor/static/trend-chart.js`, `x_monitor/static/combined-chart.js`, `x_monitor/hf_client.py` (worktree `worktrees/hf-products/`), `x_monitor/hf_products.py` (same worktree).
- **Related plans:**
  - [docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md](docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md) — `products` table + HF brand-org mapping.
  - [docs/plans/2026-06-19-003-feat-combined-chart-page-plan.md](docs/plans/2026-06-19-003-feat-combined-chart-page-plan.md) — multi-brand line-chart pattern.
  - [docs/plans/2026-06-17-002-feat-finviz-treemap-front-page-plan.md](docs/plans/2026-06-17-002-feat-finviz-treemap-front-page-plan.md) — additive topbar tab precedent.
  - [docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md](docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md) — the 11 enabled brands.
- **External API docs:**
  - OpenRouter: https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily
  - OpenRouter State of AI 2025: https://openrouter.ai/state-of-ai (PDF; calibration only, not recurring)
  - opencode: https://opencode.ai/data and https://opencode.ai/data/{brand}/{model}
  - Hugging Face: https://huggingface.co/docs/hub/en/api and https://huggingface.co/docs/hub/en/models-download-stats
  - Ollama: https://docs.ollama.com/api/tags (local); https://ollama.com/library/{model} (public scrape target)
  - npm: https://api.npmjs.org/
  - PyPI: https://pypistats.org/api/packages/{pkg}/recent
  - GitHub: https://docs.github.com/en/rest/repos/repos#get-a-repository
  - ModelScope: https://api.modelscope.cn/api/v1/models (probe pending)
- **Applied learnings:**
  - Plan 2026-06-21-001 §"Institutional Learnings Applied" — org sanity gate, hybrid curated+discover.
  - Plan 2026-06-19-003 §"Institutional Learnings" — defensive destroy-before-create for Chart.js.
  - Memory: per-collector `CollectorResult` isolation prevents one bad source from breaking the run; per-source cookies match the existing dashboard cookie pattern.
  - Memory: fuchitalee is the canonical remote; migrations, code, and the DB live there. All file paths in this plan are repo-relative (`x-monitoring/...`).
