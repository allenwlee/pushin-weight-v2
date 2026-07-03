---
title: "feat: HuggingFace products crawler (brand → HF-org → models → products)"
type: feat
status: completed
date: 2026-06-21
target_repo: minimax-marketing (code under `x-monitoring/`)
---

# feat: HuggingFace products crawler (brand → HF-org → models → products)

## Overview

Add a company-driven HuggingFace crawler to x-monitor. Given a list of companies (default: all enabled brands), the crawler resolves each to its HuggingFace org(s), lists every model under that org, fetches full per-model detail, and persists each model as a row in a new `products` table. `brands` (1) → (N) `products`.

This is the inverse of the existing top-gun HF discovery crawler (which casts a global net and tier-filters): here the starting set is explicit companies, and the goal is an exhaustive per-brand model catalog.

**Greenfield for HF in x-monitor:** there is currently no `products` table, and the existing `accounts` table holds *X/Twitter* accounts (`author_id` = X user id), not HF accounts. The new work attaches to the v1.8 `brands`/`companies` registry introduced in migration 004.

## Problem Frame

The x-monitor brands (MiniMax, Qwen, DeepSeek, GLM, Hunyuan, …) ship models on HuggingFace, but x-monitor has no record of what each brand actually publishes there. We want a durable, refreshable catalog of each brand's HF models ("products") so downstream analysis can reason about model releases, download/like trajectories, and licensing — alongside the existing X-post signal data. The crawler must be idempotent (safe to re-run as stats drift) and must handle the fact that HF org names rarely equal company names (Alibaba→`Qwen`, Tencent→`TencentARC`/`tencent`, Zhipu→`THUDM`).

## Requirements Trace

- **R1** — Accept a list of companies as input; default to all enabled brands (`config.yaml::enabled_models`), overridable via a `--companies`/`--brand` flag.
- **R2** — Resolve each company to its HF org(s) using a **hybrid** strategy: read a curated `brand_hf_orgs` mapping first; for companies absent from the seed, discover candidates via HF org search and persist them flagged for operator review.
- **R3** — For each resolved HF org, list **all** models via `GET /api/models?author={org}&full=true`, paginating through the Link-header cursor until exhausted.
- **R4** — For each model, fetch full detail (`GET /api/models/{id}`) and persist one `products` row capturing the full ModelInfo field set.
- **R5** — Create a `products` table (`brands` 1:N `products`, FK `brand_id → brands.brand_id`) with explicit scalar columns for stable ModelInfo fields **plus** a `raw_json` payload column so no data is lost and columns can be added later without re-scraping.
- **R6** — Be idempotent and re-runnable: upsert on `products.repo_id`; checkpoint + JSONL audit log + atomic writes (mirrors the top-gun crawler).
- **R7** — Authenticate via `HF_TOKEN` (Bearer), with retry/backoff and graceful handling of 404/403/transient HTTP errors.
- **R8** — Expose a CLI subcommand (`python -m x_monitor hf-products …`) plus an optional periodic runner script.

## Scope Boundaries

- **Models only.** `products` = HF models. A `hf_type` column (default `'model'`) is reserved so datasets/spaces can be added later without a schema change. `hf_type` is `CHECK`-constrained to `('model','dataset','space')` — widen the list if HF ever adds a new repo type. The dataset/space endpoints are documented but not crawled.
- **Collection + persistence only.** No dashboard/UI changes in this plan. Surfacing product counts on the treemap/grid is a separate future plan.
- **Discovery does not auto-confirm.** Runtime-discovered org candidates are written to `brand_hf_orgs` with `confirmed = 0`; an operator promotes them. Curated seed rows ship `confirmed = 1`.
- **No changes to existing attribution tables** (`posts`, `post_brands`, `post_mentions`, `post_brand_signals`, `accounts`, `brand_accounts`). The new tables are additive.
- **Org sanity check, not a correctness oracle.** Every resolved org (curated or discovered) is validated to exist and return ≥1 model before scraping; a wrong org fails loudly rather than silently polluting the catalog (lesson: TwitterAPI.io unknown-list silent fallback).

## Context & Research

### Relevant code and patterns (top-gun HF crawler — port the mechanics, invert the discovery)

Sourced from `fuchitalee:top-gun/may2026-version/` (local copy is incomplete). These are the canonical patterns to mirror:

- `pipeline/hf_direct_discover_scraper.py` — `HF_API_BASE = "https://huggingface.co/api"`; `hf_get(path, retries=3)` with exponential backoff, httpx 30s timeout, `404→not_found`, `403→forbidden` (retry-then-bail); checkpoint (`hf_checkpoint.json`), per-entry failure log (`hf_failures.jsonl`), JSONL audit log (`logs/hf_audit_{date}.jsonl`, JST timestamps, event types `repo_found`/`repo_skipped`/`repo_failed`); atomic writes (`*.tmp` → `replace`); dedup against DB before scraping.
- `pipeline/build_hf_discover_queue.py` — discovery via `GET /{type}?sort=&direction=&limit=100&full=true&cursor=` with **Link-header cursor pagination**; tier filtering by downloads/likes; author profile via `GET /users/{author}/socials` + `/overview`.
- `pipeline/migrate_gh_hf_owner_columns.py` — idempotent `ALTER TABLE … ADD COLUMN` guarded by `PRAGMA table_info`; the `hf_*` column naming convention for HF-specific fields.

### Relevant code and patterns (x-monitor target)

- `x-monitoring/x_monitor/store.py` — `Store(db_path, auto_migrate=True)`; WAL mode, `PRAGMA foreign_keys = ON`, `row_factory = Row`; `MIGRATIONS_DIR.glob("*.sql")` forward-only runner tracked in `_migrations(version, applied_at)`; `BrandRow` dataclass; transaction context manager. **The migration loader commits the script and writes the `_migrations` ledger row itself — migration SQL must NOT insert into `_migrations`** (see migration 004 header).
- `x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql` — defines `companies`, `brands`, `brand_companies`, `brand_accounts`, `company_accounts`, plus post-attribution tables. **There is no products/HF-org table here.** `brands` is the FK target: `brand_id PK, display_name, accent_color, is_sentinel, created_at`.
- `x-monitoring/x_monitor/__main__.py` — CLI entry with subcommands (e.g. `reattribute`). New `hf-products` subcommand plugs in here.
- `x-monitoring/config.yaml` — `enabled_models` list (the brand_ids), PR-reviewable; the natural home for any operator-tunable HF settings (though the brand→org mapping lives in DB per Decision D3).

### External References — exhaustive HF endpoint inventory (the pre-plan research deliverable)

Base: `https://huggingface.co/api`. Auth: `Authorization: Bearer $HF_TOKEN`.

**By account (org / user):**

| Endpoint | Purpose |
|---|---|
| `GET /models?author={org}&full=true&limit=100&sort=lastModified&direction=-1&cursor={c}` | **List all models owned by org** (R3). Paginate via `Link: rel="next"` cursor. `full=true` returns complete metadata. |
| `GET /datasets?author={org}&full=true` / `GET /spaces?author={org}&full=true` | Same pattern for datasets/spaces (out of scope; documented for future). |
| `GET /organizations?search={query}` | **Org search** — discovery for unknown companies (R2). |
| `GET /organizations/{org}` | Org profile: fullname, avatarUrl, numMembers. |
| `GET /users/{user}` / `/users/{user}/overview` / `/users/{user}/socials` | User profile, fullname/avatarUrl/numFollowers, twitter/github/linkedin/bluesky. |

**By model:**

| Endpoint | Purpose |
|---|---|
| `GET /models/{repo_id}` | **Full ModelInfo** (R4). The authoritative field source for the `products` columns. |
| `GET /models/{repo_id}?expand=author,cardData,gated,private,downloads,downloadsAllTime,likes,lastModified,sha,siblings,tags,trendingScore,pipelineTag,config,spaces` | Field selection (the canonical `expand` set). |
| `GET /models/{repo_id}?blobs=true` | Adds file sizes into `siblings`. |
| `GET /models/{repo_id}/revision/{rev}` · `/revisions` · `/tree/{rev}` · `/subtree` · `/paths-info` · `/safetensors-metadata` · `/languages` | Revision/tree/metadata endpoints (deferred; not needed for the catalog). |

**ModelInfo field set → `products` columns** (from `huggingface_hub.ModelInfo` / `DatasetInfo` dataclass + `expand` enum): scalar fields become typed columns; nested/list/object fields become JSON columns; the full payload is also kept verbatim in `raw_json`.

### Institutional learnings applied

- **TwitterAPI.io unknown-list silent fallback** → every resolved HF org must pass a startup sanity check (org exists + returns ≥1 model whose `author` matches) before scraping. A wrong org must fail loudly, not silently write unrelated models.
- **Parallel-subagent cross-import drift** → if implementation is split across subagents, the `brand_hf_orgs` ↔ `products.brand_id` FK contract and the `Store` write-method signatures must be specified up front (see System-Wide Impact).
- **BSD sed / macOS quirks** → migration is pure SQL (no sed); no cross-host text-munging in this feature.

## Key Technical Decisions

- **D1 — Org resolution is hybrid (curated + discover-and-flag).** A curated `brand_hf_orgs` seed gives accuracy for the ~11 known brands; runtime `GET /organizations?search=` discovers orgs for unknown companies and persists them `confirmed=0` for operator review. *(User-confirmed.)*
- **D2 — Products = models only, with `hf_type` reserved.** Matches "grabs all the models". *(User-confirmed.)*
- **D3 — Brand→org mapping lives in a DB table, not `config.yaml`.** Consistent with migration 004's move of the brand registry into the DB and its M:N edge-table convention (`brand_companies`, `brand_accounts`). A `brand_hf_orgs` M:N table also handles brands with multiple HF orgs.
- **D4 — Wide scalar columns + `raw_json`.** Explicit columns for the stable, queryable ModelInfo scalars (downloads, likes, pipeline_tag, gated, …); the complete payload is preserved in `raw_json` so adding columns later is a migration + backfill-from-`raw_json`, not a re-scrape. Matches top-gun's `raw` column pattern.
- **D5 — Port top-gun's crawler mechanics.** Reuse the proven `hf_get` retry/backoff, checkpoint, JSONL audit, and atomic-write patterns rather than inventing new ones. httpx (already a dependency via top-gun) as the HTTP client.
- **D6 — Org sanity gate.** Every resolved org is probed once (exists + ≥1 model + `author` matches) before listing; failure is a hard stop for that org with an audit event, never silent.
- **D7 — Input defaults to enabled brands.** `--companies`/`--brand` filter to a subset; no arg ⇒ all `enabled_models`. *(Inferred; flag in Open Questions if you want a different default.)*

## Open Questions

### Resolved During Planning
- Org resolution strategy → **hybrid curated + discover-and-flag** (D1, user-confirmed).
- Product scope → **models only** (D2, user-confirmed).
- Where the mapping lives → DB table, not YAML (D3).
- Whether products needs the existing `accounts` table → **no**; `accounts` is X accounts; HF orgs are their own `brand_hf_orgs` edge (D3).

### Deferred to Implementation
- Exact curated org for thin-presence brands (e.g. ERNIE/Baidu, which org to use). The seed ships best-effort defaults; the sanity gate + discover step will surface wrong guesses for operator correction.
- Whether to fetch per-model detail via `GET /models/{id}` separately, or rely on `full=true` list metadata. `full=true` already returns most ModelInfo fields; a separate detail call may be needed only for fields absent from the list response (decision at implementation time after one probe).
- Periodic-refresh cadence (cron/LaunchAgent) — the CLI + optional runner ship now; scheduling is a documented operator step, not coded here.

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.*

```
 companies input  (default: config.yaml enabled_models; --companies override)
        │
        ▼
 resolve_hf_orgs(brand_id)
        ├── read brand_hf_orgs WHERE confirmed=1   ──► use these orgs          ┐
        └── none?  GET /organizations?search={company_name}                     │
                    heuristic pick (name similarity / model-author match)        │
                    └─► upsert brand_hf_orgs (confirmed=0, discovered_via=…)    │
                        flag for operator review (not scraped this run)          │
                                                                                  ▼
 for each resolved, confirmed hf_org:
        sanity_gate(org)  ── GET /models?author={org}&limit=1 ──► assert ≥1 model, author matches
              │ pass                                                  fail ──► audit event, skip org
              ▼
        paginate GET /models?author={org}&full=true&limit=100  (Link rel="next" cursor)
              │
              ▼
        for each model ──► (GET /models/{id} if needed) ──► Store.upsert_product(row)
                                                              │
                                                              ▼
                                                        products table
                                       (brand_id FK · scalars · *_json · raw_json · updated_at)
```

The three stages map 1:1 to implementation units: **resolve** (Unit 3), **enumerate+gate** and **enrich+persist** (Unit 4), wired by the **client** (Unit 2) over the **schema** (Unit 1) and driven by the **CLI** (Unit 5).

## Implementation Units

- [ ] **Unit 1: Migration 005 — `products` + `brand_hf_orgs` schema**

**Goal:** Introduce the two new tables and seed the curated org mapping. Auto-applied by `Store.apply_migrations()`.

**Requirements:** R5, R2 (storage), R6 (idempotent)

**Dependencies:** Migration 004 (provides `brands`).

**Files:**
- Create: `x-monitoring/x_monitor/migrations/005_products.sql`
- Test: `x-monitoring/tests/test_migration_005_products.py`

**Approach:**
- `BEGIN; … COMMIT;`. Do **not** insert into `_migrations` (the loader does that). Use `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` so re-apply is a no-op.
- `brand_hf_orgs(brand_id, hf_org, is_primary, confirmed, discovered_via, added_at)`, PK `(brand_id, hf_org)`, FK `brand_id → brands(brand_id) ON DELETE CASCADE`. `confirmed` INTEGER (1 curated/confirmed, 0 discovered candidate). Index `(brand_id)`.
- `products(repo_id PK, brand_id, hf_org, hf_type DEFAULT 'model' CHECK (hf_type IN ('model','dataset','space')), display_name, author, sha, private, gated, disabled, pipeline_tag, library_name, downloads, downloads_all_time, download_velocity, likes, trending_score, paperswithcode_id, created_at, last_modified, tags_json, siblings_json, card_data_json, config_json, spaces_json, raw_json, collected_at, updated_at)`, FK `brand_id → brands(brand_id) ON DELETE SET NULL`. Indexes `(brand_id)`, `(hf_org)`.
- Seed `brand_hf_orgs` with curated defaults (all `confirmed=1`, `is_primary=1`). These are **operator-verifiable** defaults to be confirmed by the Unit-3 sanity gate on first run:

  | brand_id | hf_org (default, verify) |
  |---|---|
  | minimax | `MiniMaxAI` |
  | qwen | `Qwen` |
  | deepseek | `deepseek-ai` |
  | glm | `THUDM` |
  | xiaomi_mimo | `XiaomiMiMo` |
  | moonshot_kimi | `moonshotai` |
  | inclusionai | `inclusionAI` |
  | mistral | `mistralai` |
  | stepfun | `stepfun-ai` |
  | ernie | `baidu` *(thin presence — likely flags for review)* |
  | hunyuan | `tencent` |

**Patterns to follow:** migration 004 (transactional, seeded, FK conventions); `migrate_gh_hf_owner_columns.py` (idempotent column adds — though here we use CREATE TABLE).

**Test scenarios:**
- Happy path: apply 005 on a fresh DB with 001–004 applied → both tables exist with the expected columns; curated seed rows present for all 11 brands; `_migrations` records version 5.
- Edge case: `products.brand_id` FK rejects a brand_id not in `brands` (insert fails under `PRAGMA foreign_keys=ON`); `ON DELETE SET NULL` clears `brand_id` when a brand is deleted.
- Edge case: re-running the migration (second `apply_migrations`) is a no-op — no duplicate seed rows, no error.
- Integration: `Store(...)` with `auto_migrate=True` brings a brand-new DB up through 005 and `read_brands()` still returns the 12 seeded brands.

**Verification:** A fresh `x_monitoring.db` reaches schema version 5 with both tables queryable and the seed present; existing 001–004 tables and data untouched.

---

- [ ] **Unit 2: HF API client module**

**Goal:** A thin, testable HTTP layer over the HF REST API — token auth, retry/backoff, cursor pagination, org search, model list/detail.

**Requirements:** R3, R4, R7

**Dependencies:** Unit 1 (no code dep, but informs return shapes).

**Files:**
- Create: `x-monitoring/x_monitor/hf_client.py`
- Test: `x-monitoring/tests/test_hf_client.py`

**Approach:**
- `hf_token()` reads `HF_TOKEN` from env (sourced from `~/.env.secrets` by the runner, per top-gun). `hf_headers()` → `{"Accept": "application/json", "Authorization": f"Bearer {token}"}` when present.
- `hf_get(path, params=None, retries=3)` — port top-gun's: httpx 30s timeout, exponential backoff, `404→(None,"not_found")`, `403→` retry-then-`"forbidden"`, non-200 transient → retry, else `http_{code}`.
- `list_models_by_org(org, *, full=True, limit=100)` — paginates `GET /models?author={org}&…` by parsing the `Link: rel="next"` `cursor=` (port the regex/unquote from `build_hf_discover_queue.py`). Yields model dicts until exhausted or `--max` cap. Honors a polite inter-page sleep.
- `get_model(repo_id, *, expand=None, blobs=False)` — `GET /models/{repo_id}` (with `expand`/`blobs` as needed).
- `search_organizations(query)` — `GET /organizations?search={query}`; returns candidate orgs for discovery (R2).
- No I/O at import time; all network behind functions.

**Execution note:** Test-first for the HTTP contract using an httpx `MockTransport` (or `respx`) — do not hit the network in unit tests.

**Patterns to follow:** top-gun `hf_direct_discover_scraper.hf_get` + `build_hf_discover_queue.discover_models` cursor logic.

**Test scenarios:**
- Happy path: `list_models_by_org("deepseek-ai")` with a mocked 2-page response returns models from both pages, in order, following the cursor.
- Edge case: empty org (0 models) returns `[]` without error.
- Edge case: a page with no `Link: rel="next"` stops pagination (no infinite loop).
- Error path: `hf_get` retries on HTTP 500/429 then succeeds; exhausts retries on persistent 500 and returns an error sentinel.
- Error path: `404` returns `(None, "not_found")` immediately (no retry).
- Happy path: auth header present when `HF_TOKEN` set; absent (anonymous) when unset, request still sent.

**Verification:** All client functions are unit-testable offline via mocked transport; the cursor/retry/auth behaviors are asserted, not assumed.

---

- [ ] **Unit 3: Brand→HF-org resolver (hybrid curated + discover-and-flag) + Store write methods**

**Goal:** Given a company/brand, return confirmed HF orgs (from seed) or discover candidates and persist them flagged for review.

**Requirements:** R1, R2, R6

**Dependencies:** Unit 1 (tables), Unit 2 (`search_organizations`, `list_models_by_org` for the sanity gate).

**Files:**
- Create: `x-monitoring/x_monitor/hf_products.py` (resolver + orchestrator entrypoints)
- Modify: `x-monitoring/x_monitor/store.py` (add `read_brand_hf_orgs`, `upsert_brand_hf_org`)
- Test: `x-monitoring/tests/test_hf_products.py`

**Approach:**
- `read_brand_hf_orgs(brand_id, *, confirmed_only=True)` — returns list of `{hf_org, is_primary, confirmed}`.
- `resolve_hf_orgs(brand)`: if confirmed orgs exist → return them; else `search_organizations(company_display_name)` → heuristic-rank candidates (name/token similarity, or a probe that the candidate actually publishes models) → `upsert_brand_hf_org(..., confirmed=0, discovered_via="search:{q}")` for the top candidate(s). Discovered candidates are **not** returned for scraping this run; they surface in a report for operator promotion.
- `sanity_gate(org)` (also used by Unit 4): `GET /models?author={org}&limit=1` → assert ≥1 model **and** `model["author"] == org` (or org is the namespace). On failure → audit event `org_invalid`, return False. Guards against silent wrong-org pollution (D6).
- Input handling: resolve the `--companies`/`--brand` args to brand_ids; default to `enabled_models`. Unknown company names log and skip.

**Execution note:** Resolver behavior is testable by injecting a fake client (dependency-inject the HF calls) so tests don't hit the network.

**Patterns to follow:** top-gun `_hf_author_cache` (cache author/org lookups per run); `Store` transaction context for writes.

**Test scenarios:**
- Happy path: a brand with a confirmed seed row returns exactly those orgs without any search call (no network).
- Happy path: a brand with **no** confirmed row triggers `search_organizations`, and the top candidate is upserted `confirmed=0` with `discovered_via` set; it is NOT returned for scraping.
- Edge case: re-resolving an already-discovered candidate does not duplicate the `brand_hf_orgs` row (PK upsert).
- Edge case: `sanity_gate` returns False for an org that returns 0 models or whose models have a different `author`; True otherwise.
- Integration: resolver + Store write — a discovered candidate round-trips through the DB and is readable via `read_brand_hf_orgs(confirmed_only=False)`.

**Verification:** For the 11 seeded brands, resolution makes zero search calls and returns the curated orgs; for an unknown company, a flagged candidate lands in `brand_hf_orgs` without being scraped.

---

- [ ] **Unit 4: Products collector + persistence (`Store.upsert_product`)**

**Goal:** For each confirmed org, enumerate all models and upsert product rows.

**Requirements:** R3, R4, R5, R6

**Dependencies:** Unit 1, Unit 2, Unit 3.

**Files:**
- Modify: `x-monitoring/x_monitor/store.py` (add `upsert_product`, `read_products`)
- Modify: `x-monitoring/x_monitor/hf_products.py` (add `collect_products_for_org`, `collect_all`)
- Test: `x-monitoring/tests/test_hf_products.py` (extend)

**Approach:**
- `collect_products_for_org(brand_id, org, *, max=None)`: `sanity_gate(org)` → `list_models_by_org(org, full=True)` → for each model, (optionally `get_model(id)` if a needed field is absent from the list payload) → `Store.upsert_product(row)`.
- Map ModelInfo → `products` columns: scalars direct; `tags`/`siblings`/`cardData`/`config`/`spaces` → JSON columns; full payload → `raw_json`. `repo_id` = model `id` (`org/name`).
- `upsert_product(row)`: `INSERT … ON CONFLICT(repo_id) DO UPDATE SET` the mutable stats (`downloads`, `downloads_all_time`, `download_velocity`, `likes`, `trending_score`, `last_modified`, `*_json`, `raw_json`, `updated_at`); keep `brand_id`/`collected_at` stable. Idempotent re-run.
- `collect_all(companies=None, *, dry_run=False, max=None)`: resolve → gate → collect, with per-org try/except isolation (one bad org doesn't abort the run), running tallies, and JSONL audit events (`org_start`/`org_invalid`/`product_upserted`/`org_done`).
- Checkpoint + atomic semantics for the audit log (port top-gun pattern; lighter-weight is fine — the DB upsert is the source of truth, the checkpoint is for resume-on-crash).

**Execution note:** Persistence logic test-first; the HTTP fan-out is injected via the fake client from Unit 3.

**Patterns to follow:** top-gun `collect_model` (field extraction + audit) and `Store` upsert style already used for `post_brands` (`ON CONFLICT … DO UPDATE`).

**Test scenarios:**
- Happy path: `collect_products_for_org` for a mocked org returning 3 models upserts 3 `products` rows with correct scalar + JSON columns and `raw_json` equal to the full payload.
- Happy path: re-running the same org updates mutable stats (downloads/likes/updated_at change) and does not duplicate rows (count unchanged).
- Edge case: a model whose `author` differs from the org is skipped (sanity gate at list level) and logged.
- Error path: one org raises (e.g. 403) → it is recorded as a failure and skipped; other orgs in `collect_all` still complete.
- Integration: `collect_all(companies=["deepseek"])` with a fake client writes products for the `deepseek` brand only; `read_products(brand_id="deepseek")` returns them ordered by `downloads DESC`.

**Verification:** After `collect_all()` against the real API (smoke, operator-run), `SELECT brand_id, COUNT(*) FROM products GROUP BY brand_id` shows a non-zero count per confirmed brand, and a second run changes only `updated_at`/stats — no new rows.

---

- [ ] **Unit 5: CLI subcommand + optional runner**

**Goal:** Drive the crawler from the command line; provide an operator runner that loads `HF_TOKEN`.

**Requirements:** R1, R8

**Dependencies:** Unit 4.

**Files:**
- Modify: `x-monitoring/x_monitor/__main__.py` (register `hf-products` subcommand)
- Create: `x-monitoring/scripts/run_hf_products.sh` (optional periodic runner)
- Test: `x-monitoring/tests/test_hf_cli.py`

**Approach:**
- Subcommand `hf-products` with flags: `--companies a,b,c` / `--brand <id>` (subset; default all enabled), `--discover` (run discovery for unknowns even if no scrape), `--dry-run` (resolve+gate only, no writes), `--max N` (cap models per org), `--limit-orgs N`.
- Prints a per-brand/per-org report: orgs used, models upserted, discovered candidates awaiting confirmation.
- `run_hf_products.sh` mirrors top-gun's `run_hf_collector.sh`: `source ~/.env.secrets`, single-pass (or simple retry loop), PID guard, log to `logs/`. Periodic scheduling (LaunchAgent/cron) is documented but not wired here.

**Patterns to follow:** `__main__.py` existing subcommand registration; top-gun `run_hf_collector.sh` (secrets sourcing, PID guard, logging).

**Test scenarios:**
- Happy path: `python -m x_monitor hf-products --brand deepseek --dry-run` resolves+gates and prints the report without writing products.
- Happy path: `--companies minimax,qwen` scopes the run to those two brands only.
- Edge case: unknown company in `--companies` is logged and skipped; exit status remains success.
- Edge case: missing `HF_TOKEN` runs anonymously (public models still collected) and logs a notice; gated/private repos are simply absent.

**Verification:** `python -m x_monitor hf-products --help` lists the subcommand and flags; a `--dry-run` against a real brand prints resolved orgs and gated results with zero DB writes.

---

- [ ] **Unit 6: Package exports, config note, docs**

**Goal:** Wire the new public surface into the package and document operator steps.

**Requirements:** R8 (operability)

**Dependencies:** Units 1–5.

**Files:**
- Modify: `x-monitoring/x_monitor/__init__.py` (export `collect_products`, `resolve_hf_orgs`, etc. in `__all__`, lazy if heavy)
- Modify: `x-monitoring/x_monitor/config.py` (load/validate an optional `hf:` section if any tunables are added; otherwise just document `HF_TOKEN` env)
- Modify: `x-monitoring/README.md` / `CHANGELOG.md` (v1.9 section: products crawler, operator runbook, how to promote discovered orgs)

**Approach:**
- Keep `HF_TOKEN` as an env var (no secret in `config.yaml`); document that the runner sources `~/.env.secrets`.
- Document the promote-a-discovered-org flow: `UPDATE brand_hf_orgs SET confirmed=1 WHERE brand_id=? AND hf_org=?` (or a tiny CLI helper) after an operator verifies the candidate.
- Note the migration is forward-only and auto-applied; no manual `_migrations` insert.

**Test scenarios:**
- Test expectation: none — this unit is exports/config/docs. (Covered by Units 1–5's tests + import-smoke that `from x_monitor import collect_products` works.)

**Verification:** `python -c "import x_monitor; print('collect_products' in x_monitor.__all__)"` is True; README documents the run sequence and org-promotion step.

## System-Wide Impact

- **Interaction graph:** New, isolated pipeline. Reads `brands` (and optionally `companies` for display names); writes only `products` and `brand_hf_orgs`. No interaction with the X-post ingestion/attribution path or the dashboard. Future dashboard integration would *read* `products` (additive).
- **Error propagation:** Per-org isolation — a failing org (403/404/network) is logged via audit event and skipped; it never aborts the whole run and never writes partial/garbage rows (DB upsert is all-or-nothing per row).
- **State lifecycle risks:** (a) Re-runs must be idempotent — guaranteed by `repo_id` PK upsert (no duplicate products). (b) Discovered-but-unconfirmed orgs must not be silently scraped — enforced by `resolve_hf_orgs` returning only `confirmed=1` for collection. (c) `brand_id` FK with `ON DELETE SET NULL` means deleting a brand nulls its products rather than orphaning/cascading.
- **API surface parity:** The `Store` gains `read_brand_hf_orgs` / `upsert_brand_hf_org` / `upsert_product` / `read_products`. These are additive; existing `Store` methods are unchanged.
- **Integration coverage:** Unit tests must cover resolver↔store and collector↔store round-trips (cross-layer), since mocks alone won't prove the `brand_hf_orgs.brand_id` → `products.brand_id` FK contract holds end-to-end.
- **Unchanged invariants:** `brands`, `companies`, `post_*`, `accounts`, `brand_accounts` tables and all existing dashboard/attribution behavior are untouched.

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| Curated org guesses wrong (e.g. ERNIE/Baidu, Zhipu↔THUDM) → scraping the wrong org's models | Sanity gate (D6) asserts org exists + ≥1 model + `author` match; wrong org fails loudly; seed values flagged operator-verifiable. |
| Silent wrong-org pollution (cf. TwitterAPI.io list-id bug) | `sanity_gate` returns False on 0-model / author-mismatch; audited as `org_invalid`; never writes silently. |
| HF rate limiting / 403 on anonymous access | `HF_TOKEN` Bearer auth (raises limits); retry/backoff ported from top-gun; per-org isolation. |
| `full=true` list omits a field the catalog wants | `raw_json` preserves the full payload; add column + backfill from `raw_json` later without re-scraping (D4). |
| Migration applied on a DB mid-pipeline-run | Document the operator stop-pipeline + backup prerequisite (as migration 004 does); forward-only + idempotent so re-runs are safe. |
| `HF_TOKEN` absent in non-interactive contexts | Anonymous mode still collects public models; runner sources `~/.env.secrets`; missing token is logged, not fatal. |
| Cross-import drift if split across subagents | Spec the `Store` write-method signatures + `brand_hf_orgs`/`products` FK contract up front (this plan); reconciliation pass if parallelized. |

## Documentation / Operational Notes

- **Operator run sequence:** (1) ensure migration 005 auto-applies on next `Store` open; (2) `export HF_TOKEN=…` (or rely on runner sourcing `~/.env.secrets`); (3) `python -m x_monitor hf-products --dry-run` to review resolved orgs; (4) promote any discovered candidates (`confirmed=1`); (5) `python -m x_monitor hf-products`; (6) verify `SELECT brand_id, COUNT(*) FROM products GROUP BY brand_id`.
- **Refresh:** re-run periodically (stats drift). Cadence via LaunchAgent/cron is a documented operator step, not coded here.
- **Adding a brand's HF org:** insert into `brand_hf_orgs` (or let discovery flag it), then promote to `confirmed=1`.

## Sources & References

- **Origin:** user request (this session) — company-driven HF crawler → `products` table under `brands`.
- **Crawler pattern (port):** `fuchitalee:top-gun/may2026-version/pipeline/hf_direct_discover_scraper.py`, `build_hf_discover_queue.py`, `migrate_gh_hf_owner_columns.py`, `run_hf_collector.sh`.
- **Target schema/conventions:** `x-monitoring/x_monitor/store.py`, `x_monitor/migrations/004_company_brand_account_model.sql`, `x_monitor/__main__.py`, `config.yaml`.
- **HF API docs:** context7 `/huggingface/hub-docs` and `/huggingface/huggingface_hub` (ModelInfo/DatasetInfo dataclass field set, `expand` enum, `/models?author=` + Link-cursor pagination, `/organizations?search=`).
- **Applied learnings:** TwitterAPI.io silent-fallback sanity-gate pattern; parallel-subagent cross-import-contract guidance.
