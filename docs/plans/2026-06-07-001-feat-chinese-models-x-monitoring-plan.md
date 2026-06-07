# {{AGENT_ATTRIBUTION}}
---
date: 2026-06-07
type: feat
title: Chinese Models X Monitoring — Curated Query Library + Community Graph
status: active
amended: 2026-06-07-213552
amendment: Replaces Unit 7 (static daily digest) with Unit 7 (Flask dashboard) + Unit 8 (per-model drill-down). CLI/LaunchAgent renumbered to Unit 9. Data layer, query library, account graph, and run pipeline are unchanged.
origin: docs/brainstorms/2026-06-07-150000-chinese-models-curated-query-community-graph-requirements.md
---

# Chinese Models X Monitoring — Curated Query Library + Community Graph

## Problem Frame

DevRel needs a daily, all-languages, signal-first view of the X conversation around the nine v1 Chinese AI models (MiniMax, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, InclusionAI Ling, InclusionAI Ring, InclusionAI Ming), built from a curated query library and a living community account graph. The May 30 doc's brand-name-only approach worked for English but missed non-English coverage and the structural relationships between accounts.

This plan implements the replacement system scoped in `docs/brainstorms/2026-06-07-150000-chinese-models-curated-query-community-graph-requirements.md` (R0–R25, SC1–SC7, D1–D6) under a new `x-monitoring/` top-level in the `minimax-marketing` repo. The system is intentionally narrow: daily targeted collection + a small local Flask dashboard with a 9-model grid + community account graph, with LLM-based profiling, benchmark brands, multi-user access, and Phase 2 platforms explicitly out of scope.

**Who is affected:** MiniMax devrel team (single-user MVP).
**What is changing:** From ad-hoc English-leaning brand-name monitoring to a curated, multi-language, community-aware daily system.
**Why it matters:** Most high-signal conversation about Chinese AI models is in Chinese (and growing in Japanese/Korean/Spanish). Missing non-English coverage = missing the conversation. No community map = no targeted engagement.

## Context & Research

### Repo patterns to follow

- **SQLite + append-only dedupe by primary key:** The May 30 doc (R12 of that doc) and `minimax-conversation-last30days/engine/lib/dedupe.py` (already in this repo at `minimax-conversation-last30days/engine/`) use SQLite with `tweet_id` PK and `INSERT OR IGNORE`. Adopt unchanged.
- **YAML config in repo, not database:** Query strings and account metadata are config-ish, hand-edited, PR-reviewable. The same way infra is HCL. Mirrors `last30days` engine's `engine/lib/categories.py` registry pattern.
- **Vanilla CSS + htmx, no JS framework:** The dashboard is server-rendered Flask + htmx. Inline SVG for sparklines and the account graph (no d3/vis.js/cytoscape). The `last30days` engine's `engine/lib/render.py` produces self-contained HTML for a one-off research brief — the dashboard reuses the same "open in a browser" pattern, but with a Flask server and 30s htmx polling for the daily-update use case.
- **UUID-keyed run logs with `LATEST` symlink:** A new pattern for this project (not in `last30days`). Solves LaunchAgent double-launch + manual debug-relaunch clobber of a date-keyed file.
- **Cookie health sentinel in run JSON, not cron stderr:** Cron stderr on fuchitalee is not human-attended. The run JSON is the durable alert surface.

### Institutional learnings (from `docs/solutions/` and prior projects in this repo)

- **`since:YYYY-MM-DD` cursors, not `since_id`:** X advanced search accepts `since:` time-bound, which is robust to new accounts; `since_id` requires a numeric id and misses posts from accounts seen for the first time.
- **Cookie health check needs a probe search, not just a file existence check:** Reading `auth_token` from disk and finding it non-empty is necessary but not sufficient. A 1-tweet probe search with a known-good query (`from:x` against an always-active handle) validates the cookie is not just present but accepted. Failed probe → `degraded:cookies` sentinel, not silent run.
- **Don't store `APIFY_API_TOKEN` in the LaunchAgent plist:** Plist plaintext is world-readable to any process that can read the user's plist dir. Source from `~/.env.secrets` via an env wrapper (plist has `EnvironmentVariables` pointing to the wrapper script path, wrapper sources the env file then execs the binary).
- **MiniMax, Qwen, DeepSeek have prior research reports** at `minimax-conversation-last30days/20260526/consumer/{model}-core-queries-zh.md` (research-output markdown, scored X post listings, zh translations — *not* query strings). These reports inform the R6 query templates by documenting the *kinds* of posts the query library should surface (release announcements, criticism, community questions, code benchmarks). The actual X advanced-search query strings must be hand-written for all 9 models from the R6 templates. The prior research used xAI/Grok via `engine/lib/xai_x.py` (X via xAI) and `xurl_x.py` (X API v2 via `xurl` CLI) — neither is the `automation-lab/twitter-scraper` Apify actor, so the query-string format and operator model differ. The R6 template is the source of truth for query-string syntax.
- **`automation-lab/twitter-scraper` followers mode:** Confirmed available per the May 30 doc and Apify's actor listing, but **not yet verified end-to-end on fuchitalee**. D6 calls for a one-shot smoke test before this plan ships. See Implementation Unit 4.

### External references (locked in by D5, no parallel research)

- **Apify actor:** `automation-lab/twitter-scraper` — search mode requires cookies `auth_token` + `ct0`; profile-followers mode requires cookies.
- **X advanced-search operators:** `from:`, `to:`, `min_faves:`, `min_retweets:`, `since:`, `until:`, `lang:`, `-filter:replies`, `OR`, parentheses. `--dry-run` validates against this grammar.
- **Paid tier budget (v1 default):** ~10,000 tweets/mo ≈ 333 tweets/day. Matches the R24 daily ceiling. (The free tier is ~1,600/mo ≈ 53/day, which fits R17's skip-order behavior but doesn't leave room for SC1's 5–10 × 9 daily target without rotation; v1 ships on paid.)

## Key Technical Decisions

| # | Decision | Rationale | Rejected alternatives |
|---|----------|-----------|----------------------|
| 1 | **Single Python package** `x_monitor` (one `__main__.py` with subcommands), not a multi-package repo | KISS. `x-monitor run`, `x-monitor review`, `x-monitor dry-run`, `x-monitor accounts bootstrap-followers`, `x-monitor migrate`, `x-monitor setup cookies` all in one entry point. Reviewer can grep one file. | Separate binaries per command (more deploy surface, no shared model imports). |
| 2 | **YAML for accounts and queries, SQLite for posts** | Queries/accounts are read-mostly config edited in PR. Posts are write-heavy append-only. Different access patterns. Unifying them forces one of them to be a second-class citizen. | SQLite for everything (YAML diffs become SQL diffs — unreviewable). YAML for everything (concurrent writes to append-only log = corruption). |
| 3 | **Edges derived on-demand from posts, not stored** | `in_reply_to_user_id`, `quoted_status_id`, `entities.user_mentions[].id`, `conversation_id` are all already on every tweet. Deriving at read time keeps the graph always-current with no migration risk. | Persisted `edges` table (must be kept in sync with posts, double-write risk, migration burden for new edge types). |
| 4 | **UUID-keyed run logs with `LATEST.json` + `LATEST.running.json` symlinks** | Survives double-launch (LaunchAgent re-fires, manual re-runs) and partial-harvest scenarios. `LATEST.json` answers "what happened today" without scanning. `LATEST.running.json` enables resume across restarts. | Date-keyed `data/runs/<YYYY-MM-DD>.json` (silently clobbered on second run of the day). |
| 5 | **Daily ceiling = 333 (Apify paid tier, ~$10/mo), configurable in YAML** | 333/day gives 6× headroom over the 2,250-tweet upper bound (9 × 5 × 50), so R17's skip order rarely fires and SC1's "5–10 high-signal posts × 9 models" target is met without rotation. Operator accepts the $10/mo spend upfront; v1 ships on the paid tier, not the free tier. | 53/day free tier (math doesn't fit SC1 — skip-order would drop 4 of 5 query types on day 1). |
| 6 | **Cookies at `~/.config/x-monitor/cookies.json` (mode 600)** | Rotation is the only manual op; needs to be one `cp` from a working browser, not a keychain prompt or plist edit. | Plist `EnvironmentVariables` (cookie is too long, ugly in plist). macOS keychain (interactive prompt on every run; breaks non-GUI). |
| 7 | **`x-monitor review` as a subcommand of the same CLI** | Reviewing is a daily action that happens right after reading the digest. Same binary, same args convention, no second `pip install`. | Separate `x-monitor-review` binary (no shared imports, no shared config loading). |
| 8 | **LaunchAgent on fuchitalee with `WatchPaths` for `data/queries/` + `fcntl.flock` on `data/runs/LOCK`** | WatchPaths makes a query-library PR a re-run trigger. `fcntl.flock` on `data/runs/LOCK` serializes any double-fire (PR merge mid-run, manual `launchctl kickstart` while cron is running) — second invocation exits 0 with `degraded:already_running: true` in its run JSON. | OpenClaw cron (gateway-side wedge we already worked around in `project_jc_openclaw_*`). raw cron (no env wrapper, no logs). WatchPaths without the lock (overlap risk on PR-merge mid-run). |
| 9 | **Reply-chain cluster threshold = ≥3 commenters × ≥2 posts** (Q3) | Matches the threshold in R13. Adjustable via `config.yaml::clustering.{min_commenters,min_posts}` — no code change. | Hard-coded (can't tune post-launch). Per-model thresholds (YAGNI for v1). |
| 10 | **No LLM in v1** | Rules-based role tagging covers 80% of cases at 0 cost and <1s per post. LLM is heavy, slow, and unnecessary at v1 scale. v1.1 can add it once we know what rules miss. | LLM-based profiling (per May 30 R7–R9, explicitly deferred). |
| 11 | **Flask + htmx + vanilla CSS for the dashboard, no JS framework** | Dashboard is a single internal page; a JS framework (React/Vue) adds build-step + bundle + state management for what is fundamentally a 9-card grid + drill-down. Flask serves the routes; htmx gives partial HTML updates for the 30s polling without writing fetch/JSON parsing; vanilla CSS keeps the bundle at <20KB. The drill-down page is a Jinja2 template; the per-model card is also Jinja2, rendered server-side on each poll. | React/Vue/SPA (build step, hydration cost, framework churn — all YAGNI for a 9-card grid). |

## Scope Boundaries

### In scope (v1)

- 9 models, curated query library per model, community account graph per model.
- All-languages collection with transliteration variants where it helps recall.
- Apify-based daily collection with checkpoint-resume.
- Cookie health checks, budget guardrails, UUID-keyed run logs.
- Role tagging by rules (no LLM in v1).
- Reply-chain clustering.
- **Local Flask dashboard** with a 9-model grid (one card per model, time-series sparkline + signal breakdown + top-3 posts) and a per-model drill-down page. 30s polling, no auth. Manually started (`x-monitor dashboard start`) — not always-on.
- Single JSON review queue with CLI.
- LaunchAgent deployment on fuchitalee (data run only; dashboard is on-demand).

### Out of scope (deferred to v1.1+, carried from origin doc)

- LLM-based profiling (psychological disposition, narrative role, themes).
- Benchmark brands (OpenAI, Claude, Gemini) comparison.
- CLI query interface (May 30 R16–R21) — out of scope, replaced by curated YAML.
- Slack/email alerts (single-user stderr + run JSON is enough for now).
- Posting or engaging.
- Phase 2 platforms (Instagram, YouTube, Reddit).
- Auto-discovery of handles via cross-references across models.
- Historical backfill on first run (defer to v1.1 with `--backfill` flag).
- Multi-user access.

## Implementation Units

### Unit 1 — Scaffold + config layer

**Files:**
- `x-monitoring/README.md` — quickstart, daily ops, troubleshooting.
- `x-monitoring/pyproject.toml` — deps: `requests`, `pyyaml`, `python-dateutil`, `pydantic>=2`, `jinja2>=3`.
- `x-monitoring/.gitignore` — `data/runs/raw/`, `data/runs/<run_id>.json`, `data/runs/LATEST*.json`, `data/runs/LOCK`, `data/x_monitoring.db`, `data/dashboard.pid`, `data/dashboard.log`, `__pycache__/`, `*.egg-info/`.
- `x-monitoring/config.yaml` — `enabled_models: [minimax, qwen, deepseek, glm, xiaomi_mimo, moonshot_kimi, inclusionai_ling, inclusionai_ring, inclusionai_ming]`, `daily_ceiling: 333`, `apify_actor: automation-lab/twitter-scraper`, `clustering: {min_commenters: 3, min_posts: 2}`, `query_rot_streak_threshold: 3` (per-model override: `query_rot_streak_threshold_per_model: {xiaomi_mimo: 5, inclusionai_ling: 5, inclusionai_ring: 5, inclusionai_ming: 5}` for known low-volume models), `review_reasons: [low_engagement, off_topic, suspicious_actor, ambiguous_role]`, `degraded_skip_order: [Q5, Q3, Q2, Q4, Q1]`.
- `x-monitoring/x_monitor/__init__.py`
- `x-monitoring/x_monitor/config.py` — `load_config(path: Path) -> Config` (Pydantic).

**Approach:** Pure scaffolding, no business logic. Config schema is the single source of truth for the model registry, daily budget, skip order, and review reasons. Pydantic validates at load; reject unknown model_id, `daily_ceiling: 0`, `enabled_models: []`.

**Test scenarios:**
- `tests/test_config.py`
  - Rejects unknown `model_id` in `enabled_models`.
  - Rejects `daily_ceiling: 0` and negative values.
  - Rejects `enabled_models: []` (operator must opt in, no silent empty runs).
  - Loads with all 9 model_ids from the registry, asserts all are present.

**Verification:** `python -c "from x_monitor.config import load_config; c = load_config(Path('config.yaml')); assert len(c.enabled_models) == 9"` exits 0.

### Unit 2 — Query library (R1–R8)

**Files:**
- `x-monitoring/x_monitor/queries.py` — Pydantic `Query` model; `load_queries(model_id: str, root: Path) -> list[Query]`; `validate_query_syntax(q: Query) -> list[str]` (balanced parens, known operators, no stray colons, no `lang:` filter unless intentionally added per R4).
- `x-monitoring/x_monitor/__main__.py` — register `x-monitor dry-run` here.
- `x-monitoring/data/queries/minimax.yaml`
- `x-monitoring/data/queries/qwen.yaml`
- `x-monitoring/data/queries/deepseek.yaml`
- `x-monitoring/data/queries/glm.yaml`
- `x-monitoring/data/queries/xiaomi_mimo.yaml`
- `x-monitoring/data/queries/moonshot_kimi.yaml`
- `x-monitoring/data/queries/inclusionai_ling.yaml`
- `x-monitoring/data/queries/inclusionai_ring.yaml`
- `x-monitoring/data/queries/inclusionai_ming.yaml`
- `x-monitoring/tests/test_queries.py`

**Approach:** 9 YAML files, one per model. Each file has Q1 (release, from:<official> with min_faves:5), Q2 (community question, brand-term with how-to operators and min_faves:2), Q3 (criticism, brand-term with negative operators and min_faves:1), Q4 (commenter capture, to:<official> with min_faves:5), Q5 (model-conditional). Per-model variants from R5; per-model `min_faves` floors from R6. For MiniMax, Qwen, DeepSeek, port the working query strings from `minimax-conversation-last30days/20260526/consumer/` (Q1–Q3 already exercised there) into the new YAML shape. For the other 6, hand-write from the R6 templates and the R5 transliteration table.

**Test scenarios:**
- `tests/test_queries.py`
  - Loads all 9 YAMLs and asserts each has exactly 5 queries (Q1–Q5).
  - Rejects YAML missing `query_string` or `expected_signal`.
  - Rejects `expected_signal: foo` (not in the enum).
  - Rejects query strings containing `lang:` unless `lang:` is in a model-specific allowlist (R4's all-languages default).
  - `validate_query_syntax` catches: `(foo OR bar` (unbalanced), `from:@handle` (stray colon after operator arg), `min_faves:notanumber` (bad value).
  - Each query has a non-empty `query_string` after R5 transliteration substitution.

**Verification:** `python -m x_monitor dry-run` exits 0 with a per-model, per-query list and the total estimated cost (assuming each query returns its `max_results` cap).

### Unit 3 — Account graph (R9–R15)

**Files:**
- `x-monitoring/x_monitor/accounts.py` — `load_accounts(model_id: str, root: Path) -> list[Account]`; `derive_edges(posts: list[Post], model_id: str) -> list[Edge]` (4 types from R11's source fields, NOT regex-on-text); `find_clusters(edges: list[Edge], posts: list[Post], min_commenters: int, min_posts: int) -> list[Cluster]`.
- `x-monitoring/data/accounts/<model_id>.yaml` × 9 — seed with `official` handle from the canonical list (Q1, to be resolved in this unit; one-time manual research ~5 min, deferred to execution).
- `x-monitoring/tests/test_accounts.py`

**Approach:** YAML for graph nodes, edges derived on-demand. The R11 source-field derivation is the critical correctness contract — it must not be replaced with text-based regex. The seed YAML for each model has 1 `official` node; follower and commenter nodes are populated by ingesting posts (Q4 queries) and running the dedupe/role-tag pipeline.

**Test scenarios:**
- `tests/test_accounts.py`
  - `derive_edges` produces `replied_to` from `in_reply_to_user_id` (not from text).
  - `derive_edges` produces `quoted` from `quoted_status_id` (not from text).
  - `derive_edges` produces `mentioned` from `entities.user_mentions[].id` (not from `@handle` regex).
  - `derive_edges` produces `co_appears_in_thread` from shared `conversation_id`.
  - A tweet with no `in_reply_to_user_id` does NOT produce a `replied_to` edge (even if its text starts with `@user`).
  - `find_clusters` flags a cluster of 3 commenters appearing on 2 of the same official's posts.
  - `find_clusters` does NOT flag a single commenter appearing on 2 posts.
  - Role tagging: account with `bio_contains_<brand>` upgrades to `developer` (or whichever role the YAML maps it to).
  - Cross-model authors: same handle in two model graphs surfaces as `multi_brand_voice` in the digest.

**Verification:** Run unit tests + manual review of the 9 seeded YAML files for `official` handle correctness.

### Unit 4 — Apify client + cookie health (R16, R19, D5, D6)

**Files:**
- `x-monitoring/x_monitor/apify.py` — `class ApifyClient` with `run_search(query, max_results, since)`, `run_followers(handle)`, `probe_cookie()` (1-tweet search against a known-active handle to validate cookies are accepted, not just present).
- `x-monitoring/x_monitor/cookies.py` — `load_cookies(path: Path) -> dict` reads `~/.config/x-monitor/cookies.json` (mode 600); raises `CookieMissingError` if file missing or `auth_token` empty.
- `x-monitoring/tests/test_apify.py`

**Approach:** Thin wrapper around the `automation-lab/twitter-scraper` HTTP API. The probe search is the R19 health check — necessary because a non-empty cookies file is not sufficient (cookies can be accepted-on-file-but-rejected-by-X). The `run_followers` mode is gated on D6 — Unit 4 includes a `bootstrap-followers` entry point whose first invocation is the D6 verification; failure prints a clear warning and the system degrades to R12's "official + commenters" spine per the requirement.

**Test scenarios:**
- `tests/test_apify.py`
  - `load_cookies` raises `CookieMissingError` when file absent.
  - `load_cookies` raises `CookieMissingError` when `auth_token` is empty string.
  - `ApifyClient.run_search` raises `ApifyAuthError` on HTTP 401.
  - `ApifyClient.run_search` raises `ApifyRateLimitError` on HTTP 429 (caller should retry with backoff).
  - `probe_cookie` returns `True` on 200 with ≥1 result, `False` on 401 or 200 with 0 results.
  - `run_followers` returns a list of `{handle, display_name, follower_count}` objects.
  - **D6 manual verification (pre-merge):** `x-monitor accounts bootstrap-followers --model minimax --handle MiniMaxAI` (or canonical handle) succeeds and writes the follower list to `data/accounts/minimax.yaml`. If it fails, mark D6 as failed and degrade SC2's "≥10 follower accounts within 14 days" to a stretch goal.

**Verification:** Manual smoke test on fuchitalee. Pre-merge: at least one successful `run_search` end-to-end against a real model handle (e.g. `from:MiniMaxAI` returning ≥1 tweet). D6 verification: at least one successful `run_followers` call.

### Unit 5 — Storage layer (R18, R21)

**Files:**
- `x-monitoring/x_monitor/store.py` — `class Store` with `insert_posts(posts)`, `get_posts_for_digest(model_id, since)`, `get_all_posts(model_id)`, `get_account(model_id, handle)`, `upsert_account(model_id, handle, role, engagement_tier, source_query_ids)`. (The review queue lives entirely in `data/_review_queue.json` and is served by `x_monitor/review.py` — there is no SQLite `review_queue` table to keep in sync.)
- `x-monitoring/x_monitor/migrations/001_initial.sql` — tables: `posts`, `accounts`, `account_post_appearances`. (No `review_queue` table — review state lives in `data/_review_queue.json` per R25.)
- `x-monitoring/x_monitor/__main__.py` — register `x-monitor migrate` here.
- `x-monitoring/tests/test_store.py`

**Approach:** SQLite at `x-monitoring/data/x_monitoring.db`. Schema is append-only with `tweet_id` PK on `posts` (idempotent insert). `accounts` and `account_post_appearances` are derived, regenerated on every run. `review_queue` is a small in-process table (the on-disk JSON `data/_review_queue.json` is the durable alert surface; the SQLite table is for digest queries). Migrations numbered, applied forward-only with a `_migrations` table tracking applied versions. `INSERT OR IGNORE` for posts (no exceptions on duplicate).

**Test scenarios:**
- `tests/test_store.py`
  - Insert 100 posts, then re-insert the same 100 — row count remains 100 (idempotency).
  - Insert 100 posts, then 50 new ones — row count is 150, no exceptions.
  - `upsert_account` updates `last_seen_at` and `engagement_tier` on second call.
  - Migrations apply forward-only; re-running on a fresh DB is a no-op.
  - `get_posts_for_digest` returns posts ordered by `created_at` desc within the 24h window.
  - Foreign-key constraint: cannot insert `account_post_appearances` row referencing a non-existent `model_id`. (Review queue is JSON-only; tested in `test_cli.py`.)

**Verification:** `python -m x_monitor migrate` is idempotent. Manual: insert a test post, query it back, assert all fields preserved including `entities` (JSON column).

### Unit 6 — Run pipeline (R16, R17, R19, R20, R22, R25)

**Files:**
- `x-monitoring/x_monitor/run.py` — `class RunPipeline` with `estimate_cost(queries)`, `apply_skip_order(queries, budget)`, `execute()`, `resume(run_id)`. Acquires an exclusive `fcntl.flock` on `x-monitoring/data/runs/LOCK` at the start of `execute()`; if the lock is held, exits 0 with `degraded:already_running: true` in the run JSON (covers WatchPaths double-fire + manual `launchctl kickstart` while cron is running).
- `x-monitoring/x_monitor/cookie_check.py` — wraps the `probe_cookie` call from Unit 4; emits `degraded:cookies` sentinel.
- `x-monitoring/x_monitor/query_rot.py` — track 0-result streaks; flip `enabled: false` after 3 consecutive (or per-model override from `config.yaml::query_rot_streak_threshold`); emit `degraded:query_rot` sentinel.
- `x-monitoring/x_monitor/review.py` — single review-queue module exposing `class ReviewQueue` with `list()`, `add()`, `resolve()`, `dismiss()`, and `append_rule_match()`. The pipeline calls `append_rule_match()` during harvest, the CLI subcommands call `list/add/resolve/dismiss`. All write to `data/_review_queue.json` (single source of truth; no SQLite `review_queue` table).
- `x-monitoring/x_monitor/__main__.py` — register `x-monitor run` here.
- `x-monitoring/tests/test_run.py`

**Approach:** The pipeline is the heart of the system. Per R16's atomicity requirement, raw Apify responses are persisted to `data/runs/raw/<run_id>/<query_id>.json` BEFORE any DB insert. `finished_at` is stamped only after raw JSON is on disk. Resume re-reads raw JSON and re-attempts inserts (idempotent on `tweet_id`) — this prevents Apify re-charge on a partial DB failure. The UUID-keyed run log and `LATEST.json` / `LATEST.running.json` symlinks (R20) are managed at the start and end of every run. The R17 skip order is `Q5, Q3, Q2, Q4, Q1` (Q1 last because release signals are highest-signal-per-tweet). Query-rot detection is a separate module that reads the previous 3 days' run logs and flips `enabled: false` if zero results. Review queue rules: posts from accounts hitting bot-detection thresholds, low-engagement posts matching release signal, ambiguous role tags.

**Test scenarios:**
- `tests/test_run.py`
  - `estimate_cost` reads the actual 9 `data/queries/*.yaml` files at test time (does not hardcode `max_results=50`), asserts the computed cost is within the 333/day ceiling by default. Catches config drift if a YAML sets `max_results: 200` (9 × 5 × 200 = 9,000 = 27× over budget, would force skip-order).
  - `apply_skip_order` drops Q5 first, then Q3, Q2, Q4, leaves Q1.
  - Pipeline writes `data/runs/raw/<run_id>/<query_id>.json` BEFORE inserting into SQLite (mock Apify, assert file exists at the right time).
  - Pipeline aborts cleanly when budget ceiling is hit mid-run (Q1 partially run, Q4+ skipped).
  - Pipeline acquires `fcntl.flock` on `data/runs/LOCK`; a second concurrent invocation exits 0 and writes `degraded:already_running: true` to its run JSON (mock the lock to simulate a held lock and assert behavior).
  - Resume re-reads `data/runs/raw/<run_id>/` and re-attempts insert — no Apify call (mock asserts Apify was NOT called twice for the same query_id).
  - Run JSON contains `degraded:cookies: true` when `probe_cookie` returns False; cron is unaffected.
  - Run JSON contains `degraded:query_rot: <query_id>` when a query hits 3 consecutive zero-result days (or per-model threshold from `config.yaml`).
  - `data/runs/LATEST.json` symlink points to the most recent completed/aborted run.
  - `data/runs/LATEST.running.json` symlink points to the in-flight run during execution; replaced by `LATEST.json` on completion.
  - `x-monitor review --add <tweet_id> --reason suspicious_actor` appends to `data/_review_queue.json`.
  - `x-monitor review --resolve <tweet_id>` updates `status: resolved` in the same JSON.

**Verification:** End-to-end dry run on fuchitalee: `python -m x_monitor run --dry-run` produces a valid run JSON, all 9 YAMLs validate, total estimated cost is printed, no Apify calls. Then a live test run with 1 model and 1 query to confirm the full path.

### Unit 7 — Dashboard (grid view)

**Files:**
- `x-monitoring/x_monitor/dashboard.py` — `class DashboardApp` wrapping a Flask app. Routes: `GET /` (grid view), `GET /api/grid.json` (JSON for htmx polling), `GET /model/<model_id>` (drill-down, served by Unit 8). Helpers: `serialize_grid_card(model_id) -> dict` (returns `{model_id, display_name, sparkline_svg, signal_breakdown, top3_posts, account_counts, degraded_sentinels, last_run_at}`), `build_sparkline(posts_by_day, days=14) -> str` (returns inline SVG, no external lib).
- `x-monitoring/x_monitor/__main__.py` — register `x-monitor dashboard start|stop|status` here. `start` backgrounds the Flask process and writes `data/dashboard.pid`; `stop` reads the pid and `SIGTERM`s; `status` reports pid + last 50 lines of `data/dashboard.log`.
- `x-monitoring/x_monitor/templates/grid.html.j2` — Jinja2 template, htmx-driven. Each model card is a `<div class="model-card" data-model-id="...">`; the card body has a sparkline (inline SVG), a small bar chart for signal-type breakdown, and the top-3 posts as text. htmx triggers `GET /api/grid.json` every 30s and swaps the grid container (`hx-trigger="every 30s" hx-get="/api/grid.json" hx-swap="outerHTML"`). No JS framework, no build step.
- `x-monitoring/x_monitor/templates/_model_card.html.j2` — partial template rendered for each card (also used by the JSON path that returns a card fragment for htmx swap).
- `x-monitoring/x_monitor/static/dashboard.css` — vanilla CSS (~150 lines, no preprocessor). CSS variables for the 9 model accent colors. Grid layout: `grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))` so 9 cards wrap responsively.
- `x-monitoring/pyproject.toml` — add `flask>=3`, `htmx` (loaded from a CDN via `<script src="...">` in the template, single line; no build step).
- `x-monitoring/tests/test_dashboard.py`

**Approach:** Server-rendered Flask app, htmx for the 30s polling. No JS framework. Each per-model card is a self-contained module — adding a 10th model = dropping a 10th YAML query file + 10th account YAML, no dashboard code change (the grid iterates over `config.yaml::enabled_models`). The sparkline is an inline SVG built server-side from `posts_by_day` (no external charting lib). The signal breakdown is a horizontal bar chart, also inline SVG. The top-3 posts are plain text with engagement counts and "view on X" deep links. Degraded-state sentinels render as a colored badge on the card (red = cookies, yellow = query_rot, gray = already_running). Dashboard is **manually started**, not always-on — `x-monitor dashboard start` backgrounds the Flask process, `x-monitor dashboard stop` kills it. The 30s polling means the operator can keep the tab open and glance at it; if the server isn't running, the operator runs `start` once per session.

**Test scenarios:**
- `tests/test_dashboard.py`
  - `GET /` returns 200 with the 9 model cards in the grid (one per `config.yaml::enabled_models`).
  - `GET /api/grid.json` returns JSON with a `cards` key, one entry per model, each with `model_id`, `sparkline_svg`, `signal_breakdown`, `top3_posts`, `account_counts`, `degraded_sentinels`, `last_run_at`.
  - `serialize_grid_card` returns a card with a non-empty `sparkline_svg` containing `<svg` and `</svg>` and no external `<image href="http...">`.
  - `build_sparkline` produces a deterministic SVG given a fixed `posts_by_day` input (no jitter, no random).
  - Card for a model with no posts in the window renders a "no posts" empty state, not an error.
  - Degraded sentinel `degraded:cookies: true` renders as a red badge on the affected card.
  - `x-monitor dashboard start` backgrounds the process and writes `data/dashboard.pid`; `x-monitor dashboard stop` SIGTERMs and removes the pid file; `x-monitor dashboard status` reports "running" with a valid pid.
  - Dashboard template contains `<script src="https://unpkg.com/htmx.org@1.9">` (or similar) exactly once — no other `<script>` tags.
  - Dashboard CSS has no `@import` and no external `url()` references.
  - Adding a 10th model to `config.yaml::enabled_models` results in a 10th card on the grid with no code change (smoke test with a test config).

**Verification:** `x-monitor dashboard start`, then open `http://127.0.0.1:5000/` in a browser, confirm the 9 cards render, the sparklines draw, the polling indicator (htmx's `htmx:trigger` event visible in dev tools) fires every 30s. Then click a model card → drill-down page loads. Then `x-monitor dashboard stop` → process gone, port 5000 free.

### Unit 8 — Dashboard (per-model drill-down)

**Files:**
- `x-monitoring/x_monitor/dashboard.py` — add route `GET /model/<model_id>` and `GET /api/model/<model_id>.json`. Renders the full per-model digest: all top posts by `score_post` (no 5–10 cap, but truncated at 280 chars via `<details><summary>`), the account graph (force-directed node-link SVG, server-rendered, no d3), reply-chain clusters flagged as a sidebar list, role-tag distribution as a small bar chart, query-rot / cookie sentinels as a banner at the top.
- `x-monitoring/x_monitor/account_graph.py` — `class AccountGraph` with `build_force_directed(accounts, edges, width=800, height=600) -> str` (returns inline SVG; layout is a simple Fruchterman-Reingold-style force iteration done in Python, ~50 lines, no external graph layout lib). Center node = official handle. Edges colored by edge type. Click handler: htmx `GET /account/<handle>` (not implemented in v1, just renders the node — defer the per-account drill to v1.1).
- `x-monitoring/x_monitor/templates/model_detail.html.j2` — Jinja2 template, extends `grid.html.j2`'s layout. Top: model name + last-run-at + degraded-state banner. Middle: tabbed view (Posts / Graph / Clusters / Roles), default Posts tab. Bottom: review-queue actions for posts matching the review rules.
- `x-monitoring/x_monitor/templates/_model_posts.html.j2` — partial for the Posts tab (used by htmx `GET /api/model/<model_id>/posts` for the 30s refresh of just the posts panel).
- `x-monitoring/x_monitor/templates/_model_graph.html.j2` — partial for the Graph tab.
- `x-monitoring/tests/test_dashboard.py` (extend with drill-down tests)

**Approach:** The drill-down is the same dashboard, just one model at a time. Server-rendered, htmx-refreshable. The force-directed graph is the most novel piece — it's a Python implementation of Fruchterman-Reingold (or a simple deterministic radial layout with the official handle at the center and commenters radiating out by engagement tier). No external graph viz lib (d3, vis.js, cytoscape) because they all want JS execution. The graph is a static SVG that re-renders on each tab switch. The Posts tab is a chronological list of the day's top posts; the Clusters tab shows reply-chain clusters as a list (each cluster = "5 commenters who appeared on 3 of <model>'s posts"). The Roles tab shows the role-tag distribution as a horizontal bar chart.

**Test scenarios:**
- `tests/test_dashboard.py` (drill-down additions)
  - `GET /model/<model_id>` returns 200 for a known model, 404 for an unknown model.
  - Drill-down page has 4 tabs (Posts / Graph / Clusters / Roles); default active tab is Posts.
  - Top posts list has all posts for the model in the last 24h, sorted by `score_post` desc.
  - Posts > 280 chars wrap in `<details><summary>show more</summary>...</details>`; full text is in the details block.
  - `build_force_directed` produces an SVG with one `<circle>` per account node and one `<line>` per edge.
  - Graph layout is deterministic: same input → same SVG output (no random init).
  - Official handle is the center-most node (smallest distance to layout center).
  - Reply-chain cluster threshold (≥3 commenters × ≥2 posts) is enforced — a 2-commenter cluster is not shown.
  - Role distribution: 5 `developer` + 3 `critic` + 2 `unknown` → bar chart with 3 segments in those proportions.
  - `degraded:cookies: true` on the run JSON → drill-down shows a red banner at the top.
  - Drill-down htmx refresh on the Posts tab swaps only the posts panel (assert response is a fragment, not a full HTML page).

**Verification:** Click a model card on the grid → drill-down loads in <500ms. Switch tabs → tab content swaps. Force a `degraded:cookies` sentinel in `data/runs/LATEST.json` and confirm the red banner appears within 30s on the next poll. Force a query-rot on Q3 and confirm the affected model card on the grid shows a yellow badge.

### Unit 9 — CLI + LaunchAgent deployment

**Files:**
- `x-monitoring/x_monitor/__main__.py` — arg parser: `x-monitor run`, `x-monitor run --dry-run`, `x-monitor dashboard start|stop|status`, `x-monitor review --list|--resolve|--dismiss|--add`, `x-monitor migrate`, `x-monitor accounts bootstrap-followers`, `x-monitor queries list-disabled`, `x-monitor setup cookies`.
- `x-monitoring/setup/setup_cookies.py` — interactive wizard for `~/.config/x-monitor/cookies.json`. (Re-invoked as `x-monitor setup cookies` from the CLI; not a separate top-level command.)
- `x-monitoring/deploy/com.fuchitalee.x-monitor.plist` — LaunchAgent with `WatchPaths: [.../x-monitoring/data/queries/]`, `ProgramArguments: [/bin/zsh, -c, 'source ~/.env.secrets && exec python -m x_monitor run']`, `StandardOutPath: ~/Library/Logs/x-monitor/stdout.log`, `StandardErrorPath: ~/Library/Logs/x-monitor/stderr.log`.
- `x-monitoring/deploy/install.sh` — `cp com.fuchitalee.x-monitor.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist`.
- `x-monitoring/deploy/README.md` — install / uninstall / view logs / trigger manual run.
- `x-monitoring/tests/test_cli.py`

**Approach:** One CLI entry point. Subcommands as argparse subparsers. The plist does NOT contain `APIFY_API_TOKEN` (per institutional learnings) — it sources `~/.env.secrets` via a shell wrapper. `WatchPaths` on `data/queries/` means a PR merge that changes a query triggers a re-run. `StandardOutPath` to `~/Library/Logs/x-monitor/` so cron stderr is greppable post-hoc even though it's not the durable alert surface.

**Test scenarios:**
- `tests/test_cli.py`
  - `python -m x_monitor --help` lists all subcommands (including `dashboard` and its `start|stop|status`).
  - `python -m x_monitor run --dry-run` exits 0 and produces a run JSON.
  - `python -m x_monitor review --list` prints the open queue.
  - `python -m x_monitor review --add <tweet_id> --reason suspicious_actor` appends to `data/_review_queue.json`.
  - `python -m x_monitor review --resolve <tweet_id>` updates status (assert file content changes).
  - `python -m x_monitor migrate` is idempotent.
  - `x-monitor accounts bootstrap-followers` is registered (D6 verification path).
  - Plist file parses (use `plutil -lint`).
  - Plist has `WatchPaths` containing `data/queries/`.
  - Plist does NOT contain literal `APIFY_API_TOKEN=...` anywhere in the file.

**Verification:** Install the LaunchAgent on fuchitalee, trigger a manual run via `launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor`, confirm `data/runs/<run_id>.json` appears. Then `x-monitor dashboard start` and open `http://127.0.0.1:5000/` in a browser; confirm the 9 cards render and the polling fires every 30s. Unattended run for 7 consecutive days (SC4).

## File Layout (Repo-Relative)

```
minimax-marketing/
├── x-monitoring/
│   ├── README.md
│   ├── pyproject.toml
│   ├── .gitignore
│   ├── config.yaml
│   ├── setup/
│   │   └── setup_cookies.py
│   ├── deploy/
│   │   ├── com.fuchitalee.x-monitor.plist
│   │   ├── install.sh
│   │   └── README.md
│   ├── x_monitor/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── config.py
│   │   ├── queries.py
│   │   ├── accounts.py
│   │   ├── apify.py
│   │   ├── cookies.py
│   │   ├── store.py
│   │   ├── run.py
│   │   ├── dashboard.py
│   │   ├── account_graph.py
│   │   ├── scoring.py
│   │   ├── review.py
│   │   ├── cookie_check.py
│   │   ├── query_rot.py
│   │   ├── templates/
│   │   │   ├── grid.html.j2
│   │   │   ├── _model_card.html.j2
│   │   │   ├── model_detail.html.j2
│   │   │   ├── _model_posts.html.j2
│   │   │   └── _model_graph.html.j2
│   │   ├── static/
│   │   │   └── dashboard.css
│   │   └── migrations/
│   │       └── 001_initial.sql
│   ├── data/
│   │   ├── queries/<model_id>.yaml  ×9
│   │   ├── accounts/<model_id>.yaml ×9
│   │   ├── runs/
│   │   │   ├── raw/<run_id>/<query_id>.json
│   │   │   ├── <run_id>.json
│   │   │   ├── LATEST.json           (symlink, not in git)
│   │   │   ├── LATEST.running.json   (symlink, not in git)
│   │   │   └── LOCK                  (fcntl.flock file, not in git)
│   │   ├── _review_queue.json
│   │   ├── dashboard.pid             (when dashboard is running, not in git)
│   │   ├── dashboard.log             (Flask access + error log, not in git)
│   │   └── x_monitoring.db           (gitignored)
│   └── tests/
│       ├── __init__.py
│       ├── test_config.py
│       ├── test_queries.py
│       ├── test_accounts.py
│       ├── test_apify.py
│       ├── test_store.py
│       ├── test_run.py
│       ├── test_dashboard.py
│       └── test_cli.py
└── docs/
    ├── ideate/
    │   └── 2026-06-07-120000-chinese-models-x-dashboard-ideation.md
    ├── brainstorms/
    │   ├── 2026-05-30-x-conversation-intelligence-requirements.md
    │   └── 2026-06-07-150000-chinese-models-curated-query-community-graph-requirements.md
    └── plans/
        └── 2026-06-07-001-feat-chinese-models-x-monitoring-plan.md   ← this file
```

## Sequencing

| Order | Unit | Depends on | Parallelizable with |
|-------|------|------------|---------------------|
| 1 | Scaffold + config | (none) | (none) |
| 2 | Query library | Unit 1 | Unit 4 |
| 3 | Account graph | Unit 1, Unit 4 (for tests with real data) | Unit 5 |
| 4 | Apify client + cookie health | Unit 1 | Unit 2 |
| 5 | Storage layer | Unit 1 | Unit 3 |
| 6 | Run pipeline | Units 2, 4, 5 | (none — depends on all prior) |
| 7 | Dashboard (grid view) | Units 5, 6 | Unit 8 |
| 8 | Dashboard (drill-down) | Units 3, 5, 6, 7 | (none — final UI unit) |
| 9 | CLI + LaunchAgent | All prior | (none) |

Units 2 and 4 are parallelizable after Unit 1. Unit 3 needs Unit 4 for realistic test fixtures but the unit itself can be developed against mocked data. Unit 7 and Unit 8 can be built in parallel after Unit 6; Unit 8 needs Unit 3 only for the account graph view. Unit 9's LaunchAgent install is the final step after the dashboard ships a working grid + drill-down.

## System-Wide Impact

### Affected interfaces

- **New CLI surface:** `x-monitor` subcommands. No existing CLI in the repo is affected.
- **New file conventions under `x-monitoring/`:** YAML for queries/accounts, JSON for runs, Flask + Jinja2 + htmx for the dashboard, SQLite for posts. None of these overlap with `minimax-conversation-last30days/` (which has its own conventions under `engine/`).
- **New LaunchAgent:** `com.fuchitalee.x-monitor`. No existing LaunchAgent is affected. (Verify: `ls ~/Library/LaunchAgents/ | grep -i monitor` should be empty before install.)
- **New env wrapper:** The plist sources `~/.env.secrets`. The `APIFY_API_TOKEN` and cookie-related env vars are read at runtime, not inlined. No impact on existing LaunchAgents.

### Failure propagation

- **Cookie rot:** `probe_cookie` returns False → `degraded:cookies` sentinel in run JSON → dashboard renders a red badge on every model card and a banner at the top of the drill-down page → operator sees it on opening the dashboard. Cron keeps running (does NOT abort). This is the desired degradation: keep collecting what we can, surface the problem.
- **Budget exhausted mid-run:** R17 skip order drops Q5 first. If still over budget after Q5, drop Q3, then Q2, then Q4, then Q1. The run completes with whatever it could collect. Digest surfaces the skipped queries in a degraded-state section.
- **Apify 5xx mid-run:** Pipeline catches the exception, marks the query as `error` in the run JSON, continues to the next query. Resume re-reads raw JSON for any query that completed but failed DB insert. Aborts the run if ≥3 consecutive 5xx (likely Apify outage, not transient).
- **SQLite corruption:** Migration integrity check on startup; if corrupt, log loudly and abort (do NOT proceed with a partial DB; the run JSON is still written).
- **LaunchAgent not running:** Operator opens dashboard, sees empty cards (no posts from today's run) and a banner explaining the last run didn't happen. Investigate via `launchctl list | grep x-monitor` and `tail ~/Library/Logs/x-monitor/`.

### State lifecycle

- **Run lifecycle:** `running` → `completed` | `degraded` | `aborted`. `LATEST.running.json` is the in-flight symlink; replaced by `LATEST.json` on terminal state.
- **Query lifecycle:** `enabled: true` → 3 consecutive zero-result days → `enabled: false` + `degraded:query_rot` sentinel → operator PR re-enables.
- **Account lifecycle:** Newly-seen handle → `role: unknown` → evidence accumulates (verified_handle, bio_contains, multiple_posts_in_thread) → role upgrade → `multi_brand_voice` tag if same handle appears in another model's graph.
- **Review queue lifecycle:** tweet discovered → `status: open` → operator `--resolve` or `--dismiss` → `status: resolved` or `status: dismissed`. Never auto-pruned; manual cleanup at the end of each quarter.

### Data integrity

- Posts table: `tweet_id` PK, append-only. `INSERT OR IGNORE` for idempotency. No updates.
- Accounts table: derived, regenerated on every run. `upsert` semantics on `(model_id, handle)`.
- Run JSON files: appendable within a run, immutable after `finished_at` stamp.
- `_review_queue.json`: append-or-update by `tweet_id`. The single source of truth — the digest reads it for the "needs review" section, the pipeline writes to it via `review.py::ReviewQueue.append_rule_match()`, and the CLI reads/writes via the same module. Use file lock (`fcntl.flock`) to prevent concurrent writes from the pipeline and a manual CLI invocation.
- Symlinks (`LATEST.json`, `LATEST.running.json`): atomically replaced via `os.replace` on a temp symlink → rename.
- `LOCK` file: created and `fcntl.flock`-ed at run start, released at run end. Held lock → second invocation exits 0 with `degraded:already_running: true` in its run JSON.

## Success Criteria Trace

| SC | Where it's satisfied | Test file |
|----|----------------------|-----------|
| SC1 — 5–10 high-signal posts per model on the dashboard grid, ≤5 min/day | Unit 7 (dashboard), Unit 8 (drill-down), Unit 6 (pipeline) | `tests/test_dashboard.py` |
| SC2 — 9 models with ≥1 official, ≥10 follower, ≥10 commenter accounts within 14 days | Unit 4 (bootstrap-followers), Unit 3 (graph), D6 verification | `tests/test_accounts.py` |
| SC3 — Non-English ≥30% of daily posts | Unit 2 (queries — no `lang:` filter), Unit 5 (storage captures `lang`) | `tests/test_queries.py` (no lang filter assertion) |
| SC4 — Unattended 7 consecutive days | Unit 9 (LaunchAgent), Unit 6 (cookie sentinel + query_rot are non-fatal) | Manual: 7-day soak test post-deploy |
| SC5 — Adding a model is config-only | Unit 1 (config.yaml), Unit 2 (queries YAML), Unit 3 (accounts YAML) | `tests/test_config.py` |
| SC6 — Query library PR-reviewable, CI cost gate | Unit 2 (YAML diffs are greppable), Unit 6 (`--dry-run` is callable from CI) | `tests/test_run.py` |
| SC7 — Stays within the $10/mo Apify paid tier (333 tweets/day) | Unit 6 (R17 skip order), Unit 1 (`daily_ceiling: 333` in config) | `tests/test_run.py` (skip order) |

## Risks & Dependencies

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `automation-lab/twitter-scraper` breaks or is removed | Medium | D5 declares this a re-architecture event, not a v1 bug. Backup path is manual browser screenshots, but that's not automated. Mitigation: monitor the Apify actor's status, have a runbook for actor migration. |
| Cookie rot is more frequent than expected (X tightening) | High | R19's sentinel surfaces it. The probe search is the canary. Mitigation: document the rotation procedure in `x-monitoring/README.md` and `deploy/README.md`. |
| 53/day is too tight for 9 models × 5 queries | Resolved | v1 ships at 333/day (paid tier, ~$10/mo). Math fits SC1's 5–10 × 9 target without skip-order on most days. If budget pressure emerges, the R17 skip order is the safety valve. |
| Query-rot detection false-positives (legitimate low-volume days) | Medium | The threshold is 3 consecutive zero-result days. For genuinely low-volume models (MiMo, Ling/Ring/Ming), a 4-5 day threshold may be needed. Mitigation: per-model override in `config.yaml::query_rot_streak_threshold`. |
| 9 official handles have multiple candidates (Q1 unresolved) | High | Q1 is the operator's responsibility: 5 min of manual research. Plan defers to execution. R12 spine is robust to a single canonical handle per model. |
| LaunchAgent vs OpenClaw cron: gateway wedge we already hit | Low (resolved) | Per `project_jc_openclaw_m27_ab_test_2026-06-04`, the wedge was gateway-side. LaunchAgent bypasses the gateway entirely. |
| Plist is on fuchitalee, OpenClaw is on jc | n/a | Out of scope. This system runs on fuchitalee, not jc. |
| R6 engagement floors may need per-model tuning post-launch | Medium | `min_faves` per query is already in the YAML (R2). Tuning is a query YAML diff, no code change. |
| Reply-chain cluster threshold is too aggressive or too lax | Medium | Per Decision 9, `clustering.{min_commenters, min_posts}` are in `config.yaml`. Tune via PR. |
| Bot-detection heuristic (May 30 R13) is a single rule and may have false positives | Medium | Items surface in the review queue (R25), not auto-blocked. Operator resolves via `x-monitor review`. |
| Dashboard server crash (Flask process dies mid-session) | Medium | `x-monitor dashboard status` shows "not running" with the last 50 lines of `data/dashboard.log` for diagnosis. The server is stateless (all state lives in SQLite + JSON), so `x-monitor dashboard start` is a clean restart. No data loss. |
| Port 5000 conflict on fuchitalee (another Flask app) | Low | `config.yaml::dashboard_port` is configurable (default 5000). If `start` fails with `Address already in use`, the error message tells the operator how to change the port. |
| htmx CDN unreachable on first dashboard load | Low | The dashboard does not function without htmx (no polling). Mitigation: vendor htmx locally at `x-monitoring/x_monitor/static/htmx.min.js` if the operator's network blocks the CDN; default loads from `unpkg.com`. |
| Force-directed graph layout is server-rendered, no client-side interaction | Low (intentional) | The graph is a static SVG. Clicking a node goes to the model detail page (not a per-node drilldown) — per-node drilldown is v1.1. For a single internal operator, this is sufficient. |

## Open Questions (deferred to execution)

- **Q1 (carried from origin doc):** For each of the 9 models, what is the canonical official X handle? Some have multiple candidates (org vs product vs research; InclusionAI has separate handles for Ling/Ring/Ming/parent). **Resolution path:** 5–15 min per model (InclusionAI alone may have 4+ candidates: org, Ling, Ring, Ming, parent), so 1–2 hours total. Book a calendar block **before Unit 3 starts** and land the 9 `data/accounts/<model_id>.yaml` files as a single reviewable PR. The plan defers to execution because it's an external fact, but the SC2 14-day graph-coverage criterion depends on it being correct on day 1 — wrong handle = wrong query results = an entire model's digest is noise.
- **Q5 (carried from origin doc):** Role-tagging rules need a starter taxonomy. v1 ships with the 9 roles in R10, but the actual upgrade conditions (e.g. `bio_contains_<brand>`, `verified_handle`, `multiple_posts_in_thread_with_official`) need to be enumerated. **Resolution path:** in `x_monitor/accounts.py::role_tag()`, hard-code a starter rule set per the May 30 bot-detection heuristic (avg >10 faves/post, 0 replies, no bio → `suspicious_actor`; bio_contains brand → `developer`; verified_handle matching model name → `employee`; ≥2 posts in same thread as official → `community`). Tune post-launch via the review queue's ambiguous_role entries.

## Documentation

- **`x-monitoring/README.md`:** Quickstart (clone, install, set cookies, dry-run, live run, dashboard start), daily ops (open dashboard URL, review queue, rotate cookies, dashboard stop), troubleshooting (cookie rot, Apify 5xx, budget exhaustion, query rot, dashboard port conflict).
- **`x-monitoring/deploy/README.md`:** Install / uninstall LaunchAgent, view logs, trigger manual run, list loaded agents.
- **Origin requirements doc:** `docs/brainstorms/2026-06-07-150000-chinese-models-curated-query-community-graph-requirements.md` — the source of truth for R0–R25, SC1–SC7, D1–D6.
- **Plan doc:** `docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md` — this file.
- **Inline docstrings:** All public functions in `x_monitor/` get a one-line docstring. No external API doc generator (Sphinx, etc.) — this is a single-user MVP, grep-ability > render-ability.

## Operational Notes

### Daily (operator, ≤5 min)

1. `x-monitor dashboard start` (if not already running). Open `http://127.0.0.1:5000/` in browser.
2. Glance at the 9-card grid — sparklines show post volume trends, signal-breakdown bars show release / criticism / community-question proportions, top-3 posts on each card show today's signal.
3. Click a model card → drill-down loads. Switch tabs (Posts / Graph / Clusters / Roles) as needed.
4. `x-monitor review --list` for the open queue; `--resolve` or `--dismiss` items. (Or use the in-dashboard review-queue actions on the drill-down.)
5. `x-monitor dashboard stop` when done (the server is on-demand, not always-on).

### Weekly (operator, ~10 min)

1. `tail ~/Library/Logs/x-monitor/stdout.log` for the past 7 days.
2. Verify the budget hasn't been blown (Apify dashboard).
3. Check the review queue for stale `open` items; resolve or dismiss.
4. Re-evaluate `daily_ceiling` and `query_rot_streak_threshold` if needed.
5. If the dashboard has been running for days, `x-monitor dashboard stop && x-monitor dashboard start` to flush any stale state.

### Manual operations

- **Cookie rotation:** Copy `auth_token` + `ct0` from a working browser's dev tools (Application → Cookies → x.com) into `~/.config/x-monitor/cookies.json`. Re-run `x-monitor setup cookies` for validation.
- **Add a model:** Drop new `data/queries/<model_id>.yaml` and `data/accounts/<model_id>.yaml`, add model_id to `config.yaml::enabled_models`. PR review. Merge → LaunchAgent re-runs via `WatchPaths`. The dashboard picks up the new model on the next poll (no code change).
- **Disable a query:** Set `enabled: false` in the relevant YAML. PR review. Merge.
- **Port conflict (dashboard):** If `x-monitor dashboard start` fails with `Address already in use`, find the process with `lsof -nP -iTCP:5000 -sTCP:LISTEN` and either kill it or change the port in `config.yaml::dashboard_port`.

### Monitoring

- **Run JSON files (`data/runs/<run_id>.json`):** the durable alert surface. `LATEST.json` is the most recent.
- **LaunchAgent logs:** `~/Library/Logs/x-monitor/stdout.log` and `stderr.log`. Greppable post-hoc.
- **Apify dashboard:** credits remaining, run history, error rate.

### Rollout

1. Units 1–8 complete, tests green.
2. Unit 9 plist installs on fuchitalee.
3. First live run triggered via `launchctl kickstart`.
4. `x-monitor dashboard start`; operator opens `http://127.0.0.1:5000/`, validates grid + drill-down end-to-end.
5. 7-day soak test (SC4) — daily runs unattended; operator opens the dashboard daily to glance at the 9 cards.
6. Mark plan `status: complete` and move to v1.1 backlog (LLM profiling, benchmark brands, auto-discovery, per-account drilldown from the graph node click).

## Verification

- **Unit tests:** `cd x-monitoring && python -m pytest tests/` — all 8 unit-test files pass.
- **End-to-end dry run:** `python -m x_monitor run --dry-run` — exits 0, produces valid run JSON, no Apify calls, total estimated cost is within the 333/day ceiling for the loaded YAML set.
- **End-to-end live run (1 model, 1 query):** `python -m x_monitor run --models minimax --queries Q1` — exits 0, posts in SQLite, dashboard picks up the new post on the next 30s poll.
- **LaunchAgent install:** `bash deploy/install.sh` — plist loads, `launchctl list | grep x-monitor` shows the agent.
- **Manual run trigger:** `launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor` — run JSON appears within budget ceiling.
- **Dashboard smoke test:** `x-monitor dashboard start && curl -s http://127.0.0.1:5000/ | grep -c 'model-card'` returns 9 (one card per enabled model). `x-monitor dashboard stop` then `lsof -nP -iTCP:5000 -sTCP:LISTEN` shows no listener.
- **Dashboard drill-down smoke test:** `curl -s http://127.0.0.1:5000/model/minimax | grep -c 'tab'` returns 4 (Posts / Graph / Clusters / Roles tabs).
- **D6 verification (pre-merge blocker):** `x-monitor accounts bootstrap-followers --model minimax` succeeds and writes follower list.

## Next Steps

-> Document review (Phase 5) with 5 personas: coherence, feasibility, scope-guardian, product-lens, adversarial. Route present-findings to user for judgment; auto-fixes applied silently.
