# {{AGENT_ATTRIBUTION}}
---
date: 2026-06-07
topic: chinese-models-curated-query-community-graph
status: draft
supersedes: docs/brainstorms/2026-05-30-x-conversation-intelligence-requirements.md
reuses-from: docs/brainstorms/2026-05-30-x-conversation-intelligence-requirements.md
---

# Chinese Models — Curated Query Library + Community Account Graph

## Problem Frame

DevRel needs a daily, all-languages, signal-first view of the X conversation around the nine v1 Chinese AI models — **MiniMax, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, InclusionAI Ling, InclusionAI Ring, InclusionAI Ming** — built from a curated query library and a living community account graph. The May 30 doc's brand-name-only approach worked for English, but missed non-English coverage and the structural relationships between accounts. This doc is the replacement: it scopes the work tightly to the two highest-leverage survivors from the June 7 ideate (curated query library + community account graph), explicitly **all-languages** by default, and explicitly **not** building the broader profiling/CLI/volume-comparison system the May 30 doc described.

**Who is affected:** MiniMax devrel team (single-user MVP)
**What is changing:** From ad-hoc English-leaning brand-name monitoring to a curated, multi-language, community-aware system
**Why it matters:** Most high-signal conversation about Chinese AI models happens in Chinese (and growing in Japanese/Korean/Spanish). Missing non-English = missing the conversation. No community map = no targeted engagement.

### Reuse from May 30 doc (do not re-invent)

- **Apify actor choice:** `automation-lab/twitter-scraper` (search mode requires cookies `auth_token` + `ct0`)
- **Storage:** SQLite, append-only, dedupe by tweet ID
- **Bot detection heuristic** (May 30 R13): avg >10 faves/post, 0 replies, no bio; institutional accounts exempt
- **Engagement score formula:** likes + (retweets×2) + (quotes×3) + replies
- **Cookie rotation pattern** from `automation-lab/twitter-scraper` usage notes
- **Handle normalization:** strip `@`, lowercase

### Out of scope (explicitly deferred)

- LLM-based author profiling (psychological disposition, narrative role, recurring themes) — May 30 R7–R9
- Benchmark brands (OpenAI, Claude, Gemini) — May 30 R10–R11
- CLI query interface — May 30 R16–R21
- Multi-user access, Slack/email alerts, posting/engaging, Phase 2 platforms (Instagram/YouTube/Reddit)
- Auto-discovery of new handles via cross-references (defer to v1.1)

---

## Requirements

### Target Models (Phase 1)

- **R0.** Cover exactly these 9 models: **MiniMax, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, InclusionAI Ling, InclusionAI Ring, InclusionAI Ming**. Schema must allow adding more (Doubao, ERNIE, StepFun, etc.) as config-only, no code change. v1 ships with 9.

### Curated Query Library (Component A)

- **R1.** Maintain a versioned query library at `data/queries/<model_id>.yaml`. Each file lists 3–5 queries for that model.
- **R2.** Each query has: `id`, `description`, `query_string`, `expected_signal` (one of: `release` / `pricing` / `api_change` / `criticism` / `community_question` / `benchmark` / `partnership`), `priority` (`p0` / `p1` / `p2`), `enabled` (bool), `last_run_at`, `last_post_id_seen` (for incremental collection).
- **R3.** Query strings use X advanced operators (`from:`, `to:`, `min_faves:`, `min_retweets:`, `since:`, `until:`, `lang:`, `-filter:replies`, `OR`, parentheses). Each query targets one of the signal types above.
- **R4.** **All-languages by default.** No `lang:` filter on queries unless intentionally added. Trust X's language detection. Capture `lang` field on every collected post for downstream filtering.
- **R5.** For models with non-English brand names, include transliteration variants in the query where recall matters. Per R6/R4, all-languages is the default — variants supplement, never replace, the brand-name term. Current variants:
  - MiniMax → MiniMax / 海螺 AI / Hailuo
  - Qwen → Qwen / 通义千问 / 通义 / Tongyi
  - DeepSeek → DeepSeek / 深度求索
  - GLM → GLM / 智谱 / Zhipu
  - Xiaomi MiMo → MiMo / Xiaomi MiMo / 小米 MiMo
  - Moonshot Kimi → Kimi / Moonshot Kimi / Kimi K2 / 月之暗面
  - InclusionAI Ling → Ling / BaiLing / 百灵 / 灵 / InclusionAI / 入选
  - InclusionAI Ring → Ring / 沉思 / InclusionAI Ring / InclusionAI / 入选
  - InclusionAI Ming → Ming / 明 / InclusionAI Ming / InclusionAI / 入选

  **Note on the InclusionAI family:** Ling/Ring/Ming all live under the "BaiLing foundation model" umbrella and share the "InclusionAI (入选)" open-source release identity. Variants above are tuned per-series but share the "InclusionAI" parent term to catch umbrella-branded posts (e.g. releases framed as "InclusionAI announces..." that don't name a specific series).
- **R6.** Each model has at minimum these query slots (filled with model-specific terms). Engagement floors: Q1 uses `min_faves:5` (release signals are inherently low-volume, lift the floor), Q2 uses `min_faves:2` (community questions need low floor to surface), Q3 uses `min_faves:1` (criticism posts are often low-engagement in absolute terms, especially non-English), Q4 uses `min_faves:5` (commenters worth tracking have some gravity), Q5 picks its own based on the model:
  - **Q1 (release):** official handle releasing — `from:<official> (release OR 发布 OR リリース OR 출시) min_faves:5`
  - **Q2 (community question):** users asking — `<brand> (how to OR how do I OR 怎么 OR 使い方 OR 사용법) min_faves:2`
  - **Q3 (criticism):** pushback — `<brand> (bad OR broken OR disappointed OR 失望 OR ゴミ OR 별로) min_faves:1`
  - **Q4 (commenter capture):** replies to official — `to:<official> min_faves:5`
  - **Q5 (model-conditional):** free slot for a model-specific high-signal query (e.g. pricing for DeepSeek, coding eval for Qwen, video for MiniMax)
- **R7.** Incremental collection: each query tracks `last_post_id_seen`. Daily run fetches only posts newer than the last seen ID (using `since_id` or `since:` time bound) plus a 24h overlap window for safety.
- **R8.** Query library is a checked-in artifact in the repo. Changes to a query are diffable, reviewable, and rollback-able.

### Community Account Graph (Component B)

- **R9.** Maintain a community account graph at `data/accounts/<model_id>.yaml` (or SQLite, decision deferred to plan). One graph per model.
- **R10.** Graph nodes are X accounts. Each node has: `handle`, `display_name`, `role` (one of: `official` / `employee` / `developer` / `researcher` / `journalist` / `critic` / `hater` / `opportunist` / `unknown`), `engagement_tier` (`high` / `medium` / `low` / `unknown`), `first_seen_at`, `last_seen_at`, `source_query_ids` (which queries surfaced this account), `notes` (free text).
- **R11.** Graph edges capture relationships. Each edge is derived from a specific tweet object field to avoid regex-on-text false edges:
  - `follows` (A → B): A follows B — derived from `automation-lab/twitter-scraper` followers/following mode output
  - `replied_to` (A → B): A replied to B — derived from tweet field `in_reply_to_user_id` / `in_reply_to_status_id`
  - `quoted` (A → B): A quoted B — derived from tweet field `quoted_status_id` / `quoted_user_id`
  - `mentioned` (A → B): A mentioned B — derived from tweet field `entities.user_mentions[].id`
  - `co_appears_in_thread` (A ↔ B): A and B both commented in same thread — derived from shared `conversation_id`
- **R12.** **Spine of the graph is three sources** (chosen as primary):
  1. **Official handles** (seeded manually per model)
  2. **Followers of official handles** (scraped via `automation-lab/twitter-scraper` profile-followers mode — **one-time bootstrap only**, not part of the daily cron; results committed to `data/accounts/<model_id>.yaml` and re-used). The daily cron does NOT hit the followers endpoint (per R16 + cookie dependency in R19).
  3. **Commenters on official posts** (collected via `to:<official>` queries from R6 Q4)
- **R13.** Reply-chain clustering: when a post has ≥3 commenters who also comment on ≥2 other posts by the same official, flag the cluster. This surfaces collaborator and critic networks around the model.
- **R14.** Account role tagging is initially `unknown`. Upgrade to a specific role only when evidence accumulates (e.g. `verified_handle`, `bio_contains_<model>`, `multiple_posts_in_thread_with_official`, `criticized_in_<model>_release_thread`). No LLM in v1; rules-based only. Manual review queue for ambiguous accounts.
- **R15.** Cross-model authors: if the same handle appears in graphs for multiple models, surface as a `multi_brand_voice` tag. Useful for spotting journalists, comparators, and bridges.

### Collection Mechanics

- **R16.** Daily cron on fuchitalee runs the query library for all 9 models, hits Apify, ingests results into SQLite. Checkpoint-resume: each query run logs `started_at`, `finished_at`, `posts_collected`, `error`; on failure, resume from last successful query. **Atomicity:** Apify raw results are persisted to `data/runs/raw/<run_id>/<query_id>.json` BEFORE any DB insert; `finished_at` is stamped only after raw JSON is on disk. Resume re-reads the raw JSON and re-attempts inserts (idempotent on `tweet_id` primary key) — this prevents Apify re-charge on a partial DB failure.
- **R17.** Apify budget guardrail: at the start of each run, check estimated cost against remaining credit (~$5/mo free tier ≈ 1,600 tweets). If projected cost > remaining, skip queries in this order: **Q5 first (model-conditional, broadest recall), then Q3 (criticism), then Q2 (community question), then Q4 (commenter capture), then Q1 (release, highest signal-per-tweet, last to drop).** Log the degraded run and which slots were skipped.
- **R18.** All collected posts persist with: tweet_id, author_handle, text, created_at, lang, like_count, retweet_count, reply_count, quote_count, source_query_id, model_id, ingested_at.
- **R19.** Cookie health check at the start of each run: if `auth_token`/`ct0` is missing or expired, mark run as `degraded:cookies` and write a sentinel line to the run JSON (`degraded:cookies: true` field at top level). The run JSON is the durable alert surface; cron stderr on fuchitalee is not relied on because it is not human-attended. **Query-rot detection** (in-scope, was Q4): a query that returns 0 results for 3 consecutive daily runs flips its YAML `enabled` to false and emits a `degraded:query_rot: <query_id>` sentinel in the run JSON. A new query or fix to the broken query re-enables it via PR.

### Reliability Primitives

- **R20.** All collection runs write a UUID-keyed run log at `data/runs/<run_id>.json` (per-query status, per-model totals, total cost estimate, total errors, duration, sentinels, query_rot events). `data/runs/LATEST.json` is a symlink to the most recent completed/aborted run; `data/runs/LATEST.running.json` is a symlink to the currently executing run. UUID keying survives double-launch (LaunchAgent re-fires, manual re-run during debugging) and partial-harvest scenarios that would clobber a date-keyed file. The two `LATEST*.json` symlinks are the durable alert surface — cron stderr is not relied on.
- **R25.** **Review queue** at `data/_review_queue.json` (single JSON, deduped by `tweet_id`, items carry `status: open|resolved|dismissed`, `reason: low_engagement|off_topic|suspicious_actor|ambiguous_role`, `model_id`, `tweet_id`, `discovered_at`, `notes`). Surfaced when the digest collection rules mark a post as "needs human eyes" — e.g. accounts that hit bot-detection thresholds, low-engagement posts that match release signals, ambiguous role tags. Backed by an `x-monitor review` CLI: `--list`, `--resolve <tweet_id>`, `--dismiss <tweet_id>`, `--add <tweet_id> --reason <r>`. Status changes write to the same JSON, append-or-update by `tweet_id`.
- **R21.** Schema migrations tracked in `migrations/` (SQLite pattern from May 30 doc, deferred detail to plan).
- **R22.** Dry-run mode (`--dry-run`): show what queries would run and projected cost without hitting Apify. Used before first live run and after any query library change. **Dry-run also validates query syntax** against X's advanced-search operator grammar (balanced parens, known operators, no stray colons) and fails loudly on invalid queries so a broken YAML doesn't pass cron and waste an Apify slot.
- **R23.** **Daily digest (consumes R18's collected posts).** Once per cron run, after all queries finish, generate a static HTML page at `data/digest/<YYYY-MM-DD>.html`. The page is the human-facing surface for SC1's "5–10 high-signal posts per model." It must be:
  - **Sorted by model**, then by a per-model signal score (R22 dry-run + engagement formula combined with `expected_signal` weighting: `release`/`criticism` weighted higher than `community_question`)
  - **Top 5–10 per model** displayed in full text + author + timestamp + engagement count + a "view on X" deep link
  - **Truncated long posts** to first 280 chars with a "show more" toggle
  - **Self-contained HTML** (inline CSS, no external resources) — opens in a browser locally; no server, no Notion, no Slack
  - **One section per degraded state** if any: `degraded:cookies`, `degraded:query_rot: <query_id>`, `queries skipped: Q5/Q3/...` so the operator can see at a glance what didn't run
  - **No JS frameworks** — vanilla HTML the user can grep, version, and view in `git diff` if needed
- **R24.** **Per-query result cap and daily cost ceiling.** Each query is capped at `max_results: 50` (overridable per-query in the YAML, but never above 100). At the start of each run, estimate total cost assuming every enabled query returns its cap; if estimate > daily ceiling (default: 53 tweets/day = ~1,600/mo, matches the Apify free tier), run the R17 skip order. **Per-query `max_results` and daily ceiling are both in the YAML** so the budget policy is reviewable in PR. v1 ships at 53/day (free tier); raise to 333/day (paid, ~6× headroom) when real workload justifies the $8/mo spend.

### Success Criteria

- **SC1.** Daily digest (per R23) surfaces 5–10 high-signal posts per model that warrant action (release, controversy, key voice), at `data/digest/<YYYY-MM-DD>.html` (self-contained static HTML, openable locally). Time-to-insight ≤ 5 min/day.
- **SC2.** All 9 models have an account graph with ≥1 official handle, ≥10 follower accounts, and ≥10 commenter accounts within 14 days of first run.
- **SC3.** Non-English posts make up ≥30% of daily collected posts (a sanity floor — if EN-only is the result, the query library is biased).
- **SC4.** Daily collection runs unattended for 7 consecutive days without manual intervention. Cookie rotation is the only acceptable manual touchpoint.
- **SC5.** Adding a new model (e.g. Kimi) is a config-only change: drop a new `data/queries/<model_id>.yaml` and `data/accounts/<model_id>.yaml`, no code change.
- **SC6.** The query library is reviewable in PR form: any change to a query is a single YAML diff with reviewer-visible `expected_signal` and `priority`. **CI cost gate:** a PR that changes a query string runs a 1-shot dry-run (per R22) and posts `result_count_estimate` and `cost_estimate` as a PR comment; if the new cost exceeds the model's daily budget ceiling, the PR is blocked from merge.
- **SC7.** Budget: stays within the $5/mo Apify free tier. If budget pressure emerges, R17 degradation kicks in automatically before any human is paged.

---

## Scope Boundaries

### In scope (v1)
- 9 models, curated query library per model, community account graph per model
- All-languages collection with transliteration variants where it helps recall
- Apify-based daily collection with checkpoint-resume
- Cookie health checks, budget guardrails, daily run logs
- Role tagging by rules (no LLM in v1)
- Reply-chain clustering

### Out of scope (deferred to v1.1+)
- LLM-based profiling (psychological disposition, narrative role, themes)
- Benchmark brands (OpenAI, Claude, Gemini) comparison
- CLI query interface (May 30 R16–R21)
- Slack/email alerts (single-user stderr is enough for now)
- Posting or engaging
- Phase 2 platforms (Instagram, YouTube, Reddit)
- Auto-discovery of handles via cross-references across models
- Historical backfill on first run
- Multi-user access

---

## Key Decisions

- **All-languages by default, no `lang:` filter.** Capture `lang` field for downstream analysis. Transliteration variants added per model where recall matters.
- **3–5 queries per model, not 1, not 10.** Matches the ideate doc's prioritized survivor #1. 1 is too narrow to catch the signal types in R6; 10+ burns budget without clear marginal value.
- **Graph spine = official + followers + commenters.** The third source (commenters via `to:` queries) is what makes the graph community-aware rather than just a fan list.
- **No LLM in v1.** Rules-based role tagging and reply-chain clustering. LLM is heavy, slow, and unnecessary at this scale. v1.1 can add it once we know what the rules miss.
- **Query library is YAML in repo.** Not a database, not a UI. Diffable, reviewable, rollback-able. The same reason infra is HCL not a config UI.
- **SQLite for posts, YAML for queries and accounts.** Different access patterns: posts are write-heavy append-only, queries/accounts are read-mostly config. Don't unify for unification's sake.
- **May 30 doc is reused, not re-derived.** Apify actor, cookie pattern, bot heuristic, engagement formula, handle normalization, SQLite-as-MVP — all carried forward. No re-decision.

---

## Dependencies / Assumptions

- **D1.** Apify API token (`APIFY_API_TOKEN`) is available and funded. Free tier = ~1,600 tweets/mo = ~$5 credit.
- **D2.** X cookies (`auth_token`, `ct0`) are available. Will rot; rotation is the only manual operation.
- **D3.** Server is fuchitalee. Cron access available. Disk adequate for SQLite growth (~MB scale, not GB).
- **D4.** Official handles per model are known or discoverable via 5 min of manual research. Seeded manually in v1.
- **D5.** v1 uses Apify (`automation-lab/twitter-scraper`) as the sole X data source — no fallback paths, no parallel pipeline, no X API v2 budget in v1. If X changes terms / Apify actor breaks / Apify token is revoked, that is a re-architecture event, not a v1 bug. The Apify-only constraint is the answer to ToS risk: X/Apify is the established third-party aggregator path; the system stays inside that single dependency.
- **D6.** `automation-lab/twitter-scraper` exposes a `followers` (or equivalent profile-followers) mode that returns usable data for the 9 official handles. **Verify with one test run before /ce:plan finalizes.** If unavailable, R12 spine degrades to "official + commenters" only and SC2's "≥10 follower accounts within 14 days" drops to a stretch goal.

---

## Open Questions

- **Q1.** For each of the 9 models, what is the canonical official X handle? Need these before queries can be written. (Some models have multiple official accounts, e.g. org vs product vs research. InclusionAI in particular may have separate handles for Ling / Ring / Ming / InclusionAI org — confirm which is canonical per series.)
- **Q2.** RESOLVED. New top-level `x-monitoring/` directory under the repo root. All data, queries, accounts, runs, digests, and code live under `x-monitoring/`.
- **Q3.** Reply-chain clustering threshold (R13): what counts as a "cluster"? Proposal: ≥3 commenters who appear on ≥2 of the same official's posts. Adjustable post-launch.
- **Q4.** RESOLVED. Query-rot detection is in-scope (see R19 update): 3 consecutive zero-result days auto-disable the query and emit a run-JSON sentinel. Re-enable requires a PR.
- **Q5.** Role tagging rules (R14) need a starter taxonomy. v1 ships with the 9 roles in R10, but actual upgrade conditions (e.g. "bio_contains_<brand>") need to be enumerated. Defer to plan.
- **Q6.** RESOLVED. Daily digest = static self-contained HTML at `x-monitoring/data/digest/<YYYY-MM-DD>.html` (R23). No server, no Notion, no Slack. Open in browser locally.

---

## Next Steps

-> `/ce:plan` for structured implementation planning (in progress; resolving R20/R24 to UUID + 53/day, adding R25 review queue, resolving Q2/Q6)
