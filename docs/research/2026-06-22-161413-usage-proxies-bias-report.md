---
title: "Bias & methodology report: usage / market-share proxy data sources"
date: 2026-06-22
authors: research synthesis for x-monitor v2.0 usage-telemetry plan
companion_plan: docs/plans/2026-06-22-002-feat-usage-marketshare-proxies-plan.md
status: active
---

# Bias & methodology report: usage / market-share proxy data sources

## 1. Executive summary

The dashboard's existing X-post signal measures *conversation volume* — how often each brand is *talked about*. The new usage layer measures *consumption* — how often each brand is *actually called*. Both signals are valuable, both have biases, and they diverge in informative ways.

**Headline biases of the two primary proxies:**

- **OpenRouter** — Western/API-first user base (US 47%, DE 8%, CN 6% of token volume per OpenRouter's own State of AI 2025 report). Aggregator-of-aggregators, so a single developer routing across five providers counts five times. Heavily over-represents Anthropic + OpenAI in programming; under-represents self-hosted (Ollama / vLLM / llama.cpp) and Chinese-domestic-only models that mostly run on direct-provider endpoints or ModelScope. **Strength:** the most canonical public token-volume ranking in the world. **Weakness:** a "token" on OpenRouter is not a "token" on any specific provider — tokenizers differ.

- **opencode.ai /data** — terminal/CLI coding-agent user base, opt-in self-selected cohort. Heavily concentrated in coding workloads (its lead use case). Captures the subset of users who opted into Zen or Go (the curated + low-cost tiers). **Over-represents** open-weight Chinese models that ship cheaply (deepseek-v4-flash alone accounts for 48% of observed 2M volume). **Under-represents** consumer AI entirely — ChatGPT, Claude.ai, the Gemini app — by definition, because opencode users are API-style consumers. **Strength:** the only public source that publishes daily *unique-user* counts at the per-model level. **Weakness:** opt-in telemetry is not representative of all coding-agent users.

**How to use this report:** every line on the new `/usage` dashboard must be read with its proxy's bias in mind. The dashboard does not declare a single "market share" — it shows what each proxy says, side-by-side, so the divergence itself is the insight.

## 2. Per-source analysis

### 2.1 OpenRouter (`openrouter.ai`)

**Endpoint:** `https://openrouter.ai/api/v1/datasets/rankings-daily?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- **Auth:** Bearer (same key as inference — free tier sufficient)
- **Rate limit:** 30 req/min, 500 req/day
- **History:** from 2025-01-01
- **Coverage:** top 50 models per day by total tokens + an `other` aggregate

**Who uses OpenRouter:**
- Western API-first developers; mostly paid-tier users with credit-card billing.
- The OpenRouter State of AI 2025 report (100T+ token study) shows continental token share: NA 47.22%, Asia 28.61%, Europe 21.32%, SA 1.21%, Oceania 1.18%, Africa 0.46%.
- Top countries: US 47.17%, SG 9.21%, DE 7.51%, CN 6.01%, KR 2.88%, NL 2.65%, UK 2.52%, CA 1.90%, JP 1.77%, IN 1.62%.
- Billing location ≠ user location, so the geographic signal is somewhat approximate.
- Language mix: English 82.87%, Simplified Chinese 4.95%, Russian 2.47%, Spanish 1.43%, Thai 1.03%.

**What it over-represents:**
- **Anthropic + OpenAI in programming** — Anthropic's programming share is >60%, OpenAI's grew from ~2% (July 2025) to ~8%. These two brands dominate the `programming` category because their models are the default choices for Claude Code / OpenAI Codex / Cursor.
- **Any model with free credits** — many Chinese labs and small startups run free-tier promotions on OpenRouter to acquire users; their token share during the promotion window is inflated.
- **Reasoning models (>50% of token share)** — reasoning models consume orders of magnitude more tokens per request, so a few reasoning-heavy customers dominate the totals.
- **Roleplay (~52% of OSS tokens)** — the OSS model's biggest use case on OpenRouter is roleplay (chatbot personas), not coding.

**What it under-represents:**
- **Chinese-domestic-only models** — Kimi K2.7, DeepSeek V4 family, Qwen 3.7, GLM 5.x, MiMo — most of their direct-provider volume goes through ModelScope, Aliyun, DeepSeek's own endpoint, or domestic aggregators. OpenRouter sees only the slice of their volume that international users route through OpenRouter.
- **Self-hosted models** — Ollama, vLLM, llama.cpp, LM Studio users are invisible.
- **Enterprise IDE users** — GitHub Copilot, Cursor, Continue, Cline in their default IDE configurations typically use the IDE's own gateway (e.g. Copilot's Microsoft-hosted endpoint), not OpenRouter.
- **Mobile / consumer apps** — ChatGPT, Claude.ai, Gemini app traffic is invisible.
- **Anything outside the top 50** — the `other` aggregate is a single row, not a per-model breakdown. Any model with < ~1% token share is invisible at the brand level.

**OpenRouter's own brand-level data (State of AI 2025, top OSS authors by trillions of tokens, Nov 2024–Nov 2025):**

| Brand | Tokens (T) |
|---|---|
| DeepSeek | 14.37 |
| Qwen | 5.59 |
| Meta LLaMA | 3.96 |
| Mistral AI | 2.92 |
| OpenAI | 1.65 |
| MiniMax | 1.26 |
| Z-AI (GLM) | 1.18 |
| TNGTech | 1.13 |
| MoonshotAI | 0.92 |
| Google | 0.82 |

These are the same brand_ids in the x-monitor `brands` table (`deepseek`, `qwen`, `mistral`, `openai` not in scope, `minimax`, `glm`, `moonshot_kimi`, `meta` not in scope). **This table is the single best public benchmark for cross-brand usage on OpenRouter — use it as calibration when reading the chart.**

**Token-comparability caveat (from OpenRouter's own docs):**
> "Totals use each upstream provider's own tokenizer, so a token in one row is not directly comparable to a token in another row from a different provider."

Implication: a Qwen token ≠ a Claude token in raw count. Trend lines are still meaningful (a brand growing on OpenRouter is genuinely growing); cross-brand absolute comparisons are not.

**Citation requirement (from OpenRouter's API terms):**
> When republishing, must cite: `"Source: OpenRouter (openrouter.ai/rankings), as of {as_of}."`

The dashboard renders this footer conditionally when OpenRouter is the visible source.

---

### 2.2 opencode.ai (`opencode.ai/data`)

**Endpoints:** `https://opencode.ai/data` (leaderboard, time-window filter: 1D/1W/2W/1M/2M; audience filter: All Users / Zen / Go) and `https://opencode.ai/data/{brand}/{model}` (per-model detail page).
- **Auth:** none
- **Rate limit:** not published (be polite, 1-2s between requests)
- **History:** earliest date visible on per-model pages is APR 28 (~2 months)
- **Coverage:** 18 models across 6 brands: DeepSeek, MiniMax, Zhipu, Xiaomi/MiMo, Moonshot/Kimi, Qwen

**Who uses opencode:**
- Terminal/CLI AI coding agent users — predominantly Western indie developers, hobbyists, and power users. Per the homepage, "7.5M monthly developers" and "160K GitHub stars" (a corporate marketing aggregate, not per-model).
- Opt-in telemetry. The Zen and Go filters isolate paid users; the All Users filter is the broader opt-in cohort.
- Heavy concentration in coding workloads — opencode is a coding agent, so the entire dataset is by definition coding-agent traffic.

**What it over-represents:**
- **Open-weight Chinese models** — DeepSeek V4 Flash (7.4T tokens, #1) and the broader DeepSeek family; MiniMax M3 (#3, 1.8T, +26% WoW); Qwen 3.7 Plus; GLM 5.2 (new); Kimi K2.7 Code. These models are over-represented on opencode because they are cheap to call via OpenRouter / direct-provider routes and run well in coding-agent workflows.
- **Low-cost models on the Go tier** — the pricing-tiers image on the `/go` page shows models with very different request-allotment ceilings (880 requests for "Big Pickle and free models" → 30,100 for MiniMax M3). The Go tier is explicitly "low cost coding models for everyone", so cheap models get more volume per subscriber.
- **Cacheable models** — the cache ratio metric shows 95%+ cache hit rates for the top models. A model with high cacheability serves more effective requests per minute of compute, so it's disproportionately present on a budget tier.

**What it under-represents:**
- **Consumer AI entirely** — ChatGPT, Claude.ai, Gemini app, Copilot Chat, Perplexity — opencode is a coding agent, so consumer AI users are not in the dataset at all.
- **Enterprise IDE users** — Cursor, Continue, Cline, GitHub Copilot in IDEs — opencode is a CLI/TUI, so IDE users are absent unless they also use opencode.
- **Non-English-language markets** — the data page is in English; opencode's primary distribution is GitHub + English-language docs.
- **Reasoning-heavy workloads** — opencode is a coding agent; the roleplay and chat workloads that drive OpenRouter's category mix are invisible here.
- **Closed/proprietary enterprise APIs** — Azure OpenAI, AWS Bedrock, Vertex AI direct customers who use opencode but pay their cloud provider directly do not appear unless they explicitly route through opencode's accounting.

**Why opencode's bias is narrower than OpenRouter's:**
OpenRouter is an API aggregator that proxies to anyone; opencode is a coding agent with a small, self-selected, English-speaking CLI user base. The two sources agree on the broad strokes (Chinese OSS models are big in 2026) but diverge on the long tail (OpenRouter sees the entire API market; opencode sees only CLI coding-agent users).

**Telemetry is opt-in.** A user who installs opencode and disables telemetry is invisible. The actual user base is larger than the dataset suggests; the bias is towards users comfortable sharing usage data with the opencode team.

**The "7.5M monthly developers" claim is an aggregate marketing number.** It is NOT a per-model signal. Don't use it as a benchmark — it's only useful as a sanity check that the order of magnitude is correct.

**Why this proxy still matters:**
For the x-monitor's specific question — which Chinese AI labs are gaining coding-agent mindshare — opencode is the **single best public source**. It's the only one that publishes daily unique-user counts at the per-model level. The bias is real but the signal is unique.

---

### 2.3 Hugging Face (read-side aggregation of `products` table)

**Endpoint:** `https://huggingface.co/api/models?author={org}&limit=100` (paginated by Link-cursor). Read-side: `SELECT brand_id, SUM(downloads), SUM(likes) FROM products GROUP BY brand_id`.
- **Auth:** optional `Bearer $HF_TOKEN` (raises rate limits)
- **Coverage:** the entire HF Hub catalog per brand

**Who uses Hugging Face:**
- ML researchers, open-source developers, fine-tuners, AI engineers prototyping locally.
- Heavily skewed toward open-weights and toward research workflows.
- The HF `downloads` field counts HTTP requests to specific files (`config.json`, weight files per library) — not users, not inference calls. A developer who clones the whole repo counts more than a developer who just downloads `config.json`.

**What it over-represents:**
- **Open-weight models** — proprietary models (Anthropic, OpenAI closed-weight, Google Gemini) are absent or undercounted.
- **Research-flavored benchmarks** — academic users drive spikes via paper releases.
- **Libraries with stricter `countDownloads` rules** — GGUF models are double-counted (every file counts); transformers models only count `config.json`. Cross-library comparisons are unfair.
- **Initial-release spikes** — `trendingScore` (which the HF plan uses) spikes hard on day-of-release then decays.

**What it under-represents:**
- **Proprietary API users** — Claude Sonnet, GPT-5, Gemini Pro are all on HF as "gated" repos with download-restricted weights; their `downloads` field is essentially a waitlist count.
- **Production inference** — HF downloads are a one-time fetch; production inference happens on closed endpoints.
- **Chinese-domestic users** — most Chinese OSS labs also publish on ModelScope; HF downloads undercount their true reach.
- **Anything not on HF** — Copilot-direct, ChatGPT, Claude.ai are entirely absent.

**Implication:** HF `downloads` is a *catalog signal* — it tells you "this model is published and reachable" not "this model is in production". Trend lines are still meaningful (a model's downloads grow when production deployments grow), but absolute counts are not comparable to API-call counts.

---

### 2.4 Ollama library (`ollama.com/library/{model}`)

**Endpoint:** `https://ollama.com/library/{model}` (HTML scrape).
- **Auth:** none
- **Coverage:** per-model aggregate "X.XM Downloads" + per-tag table (size, context, modality). **No per-tag pull counts** — only the model-level aggregate.

**Who uses Ollama:**
- Local-run hobbyists, indie devs, students, AI-curious tinkerers. Strong "runs on a laptop" bias.
- Heavily Mac/Linux; less Windows (WSL works but is not the default).
- Mostly users who do NOT have access to OpenAI/Anthropic API keys (or who prefer local inference for privacy reasons).

**What it over-represents:**
- **Small open-weight models** — Llama 3.1 8B, Qwen 2.5 7B, Phi-4, Gemma 3 — models that fit on consumer GPUs.
- **Privacy-conscious Western users** — Ollama is the default choice for users who refuse to send prompts to a cloud API.
- **Coding-agent local inference** — some users run local coding agents via Ollama-served models.

**What it under-represents:**
- **Production deployments** — Ollama is a developer tool, not a serving platform. Production runs on vLLM, TGI, Triton.
- **Enterprise** — Ollama users are overwhelmingly individuals, not corporate IT.
- **Chinese users** — Ollama's distribution is GitHub + English docs; Chinese users lean toward ModelScope for direct-provider + domestic hosting.
- **Closed/proprietary models** — Ollama only serves open-weight GGUF models.

**Implication:** Ollama is a *hobbyist signal*. Use it to identify which small open-weight models are gaining enthusiast mindshare. Don't use it for production usage estimates.

---

### 2.5 npm SDK downloads (`api.npmjs.org`)

**Endpoint:** `https://api.npmjs.org/downloads/point/last-week/{pkg}` (also `last-day`, `last-month`, `last-year`, `date-range:start:end`).
- **Auth:** none
- **Coverage:** each brand's primary SDK package (`@anthropic-ai/sdk`, `openai`, `@google/genai`, `@mistralai/mistralai`, etc.)

**Who runs `npm install`:**
- JavaScript / TypeScript developers.
- **Counts every install** — including dev environments, CI pipelines, monorepo deduplication that re-fetches, and unused `package.json` entries.

**What it over-represents:**
- **Dev/CI noise** — a CI matrix with 50 builds counts 50 downloads per run.
- **AI-curious developers who never send a real request** — they install the SDK and never call it.
- **Frontend developers** — JS is a frontend-heavy ecosystem, so usage skews toward web-app + Vercel/Next.js developers.

**What it under-represents:**
- **Backend Python developers** — the largest AI dev segment, who use the PyPI SDK instead.
- **Mobile developers** — iOS / Android.
- **Serverless production** — many production deployments are bundled and don't re-fetch on every cold start.

**Implication:** npm downloads measure *ecosystem presence*, not API usage. A 10× growth in `@anthropic-ai/sdk` downloads means 10× more JS developers have the SDK in their project tree — it does NOT mean 10× more API calls. Pair with PyPI downloads for a more complete picture.

---

### 2.6 PyPI SDK downloads (`pypistats.org/api/packages/{pkg}/recent`)

**Endpoint:** `https://pypistats.org/api/packages/{pkg}/recent`.
- **Auth:** none
- **Coverage:** `openai`, `anthropic`, `google-generativeai`, `mistralai`, etc.

**Who runs `pip install`:**
- Backend Python developers, ML researchers, data scientists, Jupyter notebook users.
- **Counts every install** — including dev environments, Jupyter kernel rebuilds, and Docker layer caching.

**What it over-represents:**
- **Notebook users** — Jupyter auto-installs are over-counted.
- **Dev / CI noise** — same as npm.
- **ML research workflows** — heavy Python+PyTorch ecosystem.

**What it under-represents:**
- **Production runtime usage** — a `pip install` in a production Dockerfile counts once per image build, not per request.
- **Frontend / mobile / non-Python backends.**

**Implication:** Same as npm — ecosystem presence, not API usage. PyPI is the better proxy of the two for AI SDK adoption (Python is the dominant AI dev language), but it still doesn't measure API calls.

---

### 2.7 GitHub stars (`api.github.com/repos/{owner}/{repo}`)

**Endpoint:** `https://api.github.com/repos/{owner}/{repo}`.
- **Auth:** optional Bearer (raises 60→5000 req/h)
- **Coverage:** `stargazers_count`, `forks_count`, `pushed_at`. **GitHub does NOT expose clone or traffic counts via the public API long-term.**

**What it measures:**
- Developer attention / vanity / curiosity. Stars are bookmarked repos, not used repos.

**What it over-represents:**
- **New releases** — every major release gets a star spike from release-watching bots and newsletters.
- **Hype-driven stars** — a viral tweet about a model produces 10K stars in 24 hours.
- **People who star to follow a project** — not the same as people who deploy it.

**What it under-represents:**
- **Production usage** — most production deployments never touch the repo after `git clone`.
- **Enterprise usage** — many enterprise users fork to internal-only mirrors, not the public repo.

**Implication:** GitHub stars are a **popularity signal, not a usage signal**. Tier-2 + weak. Disable by default; only enable if comparing release-announcement traction to actual deployment.

---

### 2.8 ModelScope (probe pending from fuchitalee)

**Endpoint:** `https://api.modelscope.cn/api/v1/models?author={author}&page=1&page_size=50` (probe returned ECONNREFUSED from this Mac; expected from the dev environment, must be probed from fuchitalee).
- **Auth:** optional Bearer for private repos
- **Coverage:** the entire ModelScope catalog

**Why this matters:**
ModelScope is Alibaba's Hugging Face equivalent and is the **home turf for Qwen, Tongyi, and other Alibaba-family models**. For Chinese OSS models, ModelScope downloads are likely a much larger signal than HF downloads. Until probed, treat as a Tier-2 source with **higher priority than HF** for the `qwen` brand specifically.

**Predicted bias profile (subject to confirmation):**
- Over-represents Chinese-domestic users (the default Chinese OSS hub).
- Under-represents international users (who go to HF or Hugging Face mirrors).
- Strong complement to OpenRouter's under-representation of Chinese-domestic models.

---

### 2.9 Sources deferred (out of scope)

- **Google Trends** — search interest as a proxy; no public API, fragile scraping, frequently CAPTCHA-gated. Defer.
- **Artificial Analysis** — benchmarks + price-performance leaderboard; **no public usage volume**. Benchmarks ≠ usage. Defer unless they publish a usage metric.
- **Reddit / Discord / Slack** — community discussion volume; mirrors the X-post signal already collected. Defer.
- **GitHub Copilot / Cursor / Cline telemetry** — proprietary; not published. Defer.

## 3. Reconciliation table — X-post signal vs. usage signal

This is the kind of comparison the new `/usage` dashboard is designed to surface. Hypothetical example:

| Brand | X-post daily total | OpenRouter tokens (7d avg) | opencode tokens (7d avg) | HF downloads growth | Story |
|---|---|---|---|---|---|
| DeepSeek | High, declining | High, stable | #1, very high | Growing | Usage plateauing while X chatter continues — narrative catching up to usage. |
| MiniMax | High, growing | Moderate, growing | High, +26% WoW | Growing | Three signals agree — broad-based growth. |
| Qwen | High, stable | Moderate | Moderate, declining | Very high | HF traction strong (Qwen is everywhere on HF); OpenRouter less so; opencode dipping slightly. |
| GLM | Moderate, growing | Moderate, growing | New entry at #4 | Growing | Cross-signal acceleration — multiple confirmation. |
| Kimi | Low, stable | Low | Moderate, +89% WoW | Growing | Coding-agent-specific surge (Kimi K2.7 Code release). |
| Xiaomi MiMo | Very low | N/A | Moderate | N/A | New entrant; coding-agent niche traction only. |

**Why this table matters:** the X-post signal is a *narrative* proxy. When the X-post signal diverges from the usage signal — "X chatter up 200% but OpenRouter flat" or "X chatter flat but opencode usage up 50%" — that's the insight. The dashboard surfaces these divergences visually; this report teaches operators how to read them.

## 4. Methodology notes

### 4.1 Token-comparability (OpenRouter)

A "token" on OpenRouter is whatever the upstream provider's tokenizer returns. Anthropic's tokenizer and DeepSeek's tokenizer produce different token counts for the same input string. **Trend lines** are comparable (a brand growing on OpenRouter is genuinely growing); **absolute values across brands** are not.

The dashboard renders a tooltip on hover that explains: "Tokens are provider-tokenized; absolute values across brands are not directly comparable."

### 4.2 Snapshot vs. time-series

`products.downloads` in the `products` table is a snapshot (latest value, upserted each run). `usage_samples` is a time-series (one row per sample date, append-only). The HF collector reads the snapshot from `products` and writes a derived time-series row to `usage_samples` — the source of truth is the products table, the chart data is the time-series.

### 4.3 Sample size disclosure

Every line on the `/usage` chart that uses opencode data should show the unique-user count for the visible window (e.g. "opencode 1D unique users: 92K"). Small samples are noisier; the chart shouldn't hide that.

### 4.4 Window selection

Default window: **90 days.** OpenRouter has 1 year of history but most brands' usage 90+ days back is dominated by models that have since been deprecated. 90 days keeps the chart focused on current generation. Operators can override via the dashboard's window toggle.

### 4.5 Collector isolation

A failure in one collector (OpenRouter 429, opencode scrape timeout, HF db read error) is **isolated** — the other collectors still complete, and the dashboard still renders the data it has. Empty-state copy ("No data yet — run `python -m x_monitor usage-collect`") appears for sources with zero rows.

### 4.6 First-run backfill

On first run, the collector pulls the maximum available window:
- OpenRouter: 365 days (capped at 2025-01-01 floor).
- opencode: as far back as the per-model page shows (~APR 28, ~2 months).
- HF: cumulative downloads from `products.updated_at`.

This gives the chart historical context from day one.

## 5. References

### Primary sources
- OpenRouter rankings API: https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily
- OpenRouter State of AI 2025 report: https://openrouter.ai/state-of-ai
- OpenRouter `/data` product page: https://openrouter.ai/data
- opencode leaderboard: https://opencode.ai/data
- opencode per-model page example: https://opencode.ai/data/deepseek/deepseek-v4-flash
- Hugging Face Hub API: https://huggingface.co/docs/hub/en/api
- Hugging Face download stats methodology: https://huggingface.co/docs/hub/en/models-download-stats
- Ollama library: https://ollama.com/library
- npm downloads API: https://api.npmjs.org/
- PyPI stats API: https://pypistats.org/api/
- GitHub REST API: https://docs.github.com/en/rest/repos/repos#get-a-repository

### Companion artifacts
- Companion plan: `docs/plans/2026-06-22-002-feat-usage-marketshare-proxies-plan.md`
- Existing HF products plan: `docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md`
- Existing combined-chart plan: `docs/plans/2026-06-19-003-feat-combined-chart-page-plan.md`
- Prior related research: `docs/research/2026-06-17-105855-top-100-llm-brands.md`

### Acknowledgements
- Bias categorizations adapted from OpenRouter's own State of AI 2025 report (continental/country/language breakdowns) and from standard criticism of self-reported telemetry (opt-in bias, dev/CI noise).
- The "opencode's data page is the only public source with daily per-model unique-user counts" claim is based on the present research sweep (June 2026); verify before relying on it long-term.