# {{AGENT_ATTRIBUTION}}
# Call-path attribution pipeline update
#
# Companion to docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md
# which landed the schema (migration 004) on 2026-06-19. This plan lands the
# INGEST side: populating post_brands, post_mentions, post_brand_signals on
# every TwitterAPI.io ingest + a one-shot reattribute_all_posts subcommand
# for the 2,008 historical posts.

---

title: Call-path attribution pipeline (post_brands / post_mentions / post_brand_signals population)
type: feat
status: active
date: 2026-06-19
origin: docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md

---

# Call-path attribution pipeline

## Overview

The x-monitor schema migration 004 (companies/brands/accounts/post_brands/post_mentions/post_brand_signals) is live on production as of 2026-06-19 15:30 JST. The ingest path still writes to the v1.7 single-brand model: `attribute_to_brand` returns one brand, `classify_signal` returns one signal string, and `Store.insert_posts` writes the brand/signal into `posts.brand_id` / `posts.signal` (both columns dropped in migration 004). The result: `post_brands`, `post_mentions`, and `post_brand_signals` are empty, the dashboard's treemap renders the "no data" strip, and the v1.8 multi-brand attribution is invisible.

This plan lands the new attribution pipeline. On every TwitterAPI.io ingest:

1. **4-source extraction** (`user_mention`, `hashtag`, `body_keyword`, `search_term`) writes one `post_mentions` row per (post, brand, source) triple.
2. **Brand consolidation** dedups by `(post_id, brand_id)` and writes one `post_brands` row per distinct brand with `weight = 1.0 / N_distinct_brands`.
3. **Per-brand signal classification** rewrites `classify_signal` to return `list[(brand_id, signal)]` and writes one `post_brand_signals` row per (post, brand) pair.

Plus a one-shot `python -m x_monitor reattribute --since <min_created_at>` subcommand that walks the 2,008 historical posts through the same pipeline so the dashboard has real data on first render.

## Problem Frame

Today (post-migration, pre-this-plan):

- The 4 new join tables are empty (verified 2026-06-19 15:30: `post_brands=0`, `post_mentions=0`, `post_brand_signals=0`).
- The dashboard's treemap renders 11 brand tiles all with "no data" because `serialize_grid_card` reads `posts.source_query_id` for signal counts and JOINs `post_brands` for weight — both queries return 0 rows.
- The next pipeline cycle (every 15 min per the LaunchAgent plist) will run `RunPipeline.execute()`, which still calls the v1.7 `attribute_to_brand` returning a single brand_id. Even if we patched `insert_posts` to write to the new tables, the v1.7 attribution only knows about 11 brands (no multi-brand), uses one signal string, and writes nothing to `post_mentions`.

The migration's value proposition — multi-brand attribution, per-brand signal decomposition, 4-source mention tracking — is invisible until this plan lands.

## Requirements Trace

- **R1.** New `x_monitor/attribution.py` module owns the 4 extractors + `compute_post_brands` consolidator + per-brand signal classifier. Existing `x_monitor/intent_classifier.py` becomes a thin compat shim that re-exports from `attribution.py` for any remaining callers, then is deleted in a follow-up commit.
- **R2.** On every ingest, `attribute_to_brand` is replaced by `attribute_to_brands` (plural) returning `list[(brand_id, confidence)]` where confidence is a float in [0, 1] derived from the source priority (`user_mention` + `hashtag` = 1.0; `body_keyword` + `search_term` = 0.7; mixed = max). All detected brands are returned (not first-match-wins).
- **R3.** New `x_monitor/attribution.py::extract_user_mentions(post, brand_accounts, entities) -> list[MentionRow]` reads `entities.user_mentions[].id` (numeric X user id) and resolves to `brand_id` via `brand_accounts`. If the handle isn't in `brand_accounts`, emits a `MentionRow(post_id, brand_id=None, source='user_mention', raw_token=f"@{username}", mentioned_at=post.created_at)` so the raw token is preserved for later backfill.
- **R4.** New `x_monitor/attribution.py::extract_hashtag_mentions(post, brand_hashtags, entities) -> list[MentionRow]` reads `entities.hashtags[].tag` (lowercase, no `#` prefix) and resolves to `brand_id` via `brand_hashtags`. Case-insensitive match. Unknown hashtags produce no row (we don't preserve noise).
- **R5.** New `x_monitor/attribution.py::extract_body_keywords(post, compiled_keyword_index) -> list[MentionRow]` compiles all `brand_keywords` patterns once per cycle into a single compiled-regex index (mirrors v1.7's `_BRAND_RE` pattern). Scans `post.text` once, returns every match with `raw_token=<matched substring>`. Filters out matches with `brand_id = '_unattributed'`.
- **R6.** New `x_monitor/attribution.py::extract_search_term_match(post, search_query, brand_search_terms) -> list[MentionRow]` reads `posts.source_query_id`, joins to `search_queries.query_id` for the `keywords_json` array, and emits one row per matching `(brand_id, term)` pair. Always emits at least one row per post (the search-term source is "why this post entered the pipeline").
- **R7.** New `x_monitor/attribution.py::compute_post_brands(post, all_mentions) -> list[(brand_id, weight)]` takes the union of `brand_id` values across all `all_mentions` rows (filtering NULL), dedups, returns `[(brand_id, 1.0 / N)]` per distinct brand. Empty union returns `[('_unattributed', 1.0)]`.
- **R8.** Updated `x_monitor/translator.py::classify_signal(text, brand_ids) -> dict[brand_id, signal]` returns one signal per brand. The LLM prompt includes the explicit `brand_ids` list and asks for a per-brand decomposition. Output parser validates every returned brand_id against `Store.read_brands()` and drops any hallucinated IDs before returning.
- **R9.** New `x_monitor/store.py::Store.insert_post_brands(post_id, brand_id, weight)` uses `INSERT INTO post_brands(post_id, brand_id, weight) VALUES (?, ?, ?) ON CONFLICT(brand_id, post_id) DO UPDATE SET weight = excluded.weight`. The `weight` column MUST be in the INSERT column list (top-gun HF audit lesson: `ON CONFLICT` only updates INSERT-listed columns).
- **R10.** New `x_monitor/store.py::Store.insert_post_mentions(post_id, brand_id, source, raw_token, mentioned_at)` uses `INSERT INTO post_mentions(post_id, brand_id, source, raw_token, mentioned_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(post_id, brand_id, source) DO UPDATE SET raw_token = excluded.raw_token`. `brand_id` may be NULL (un-attributed mentions); the PK allows NULLs via SQLite's default.
- **R11.** New `x_monitor/store.py::Store.insert_post_brand_signals(post_id, brand_id, signal)` uses `INSERT INTO post_brand_signals(post_id, brand_id, signal) VALUES (?, ?, ?) ON CONFLICT(post_id, brand_id) DO UPDATE SET signal = excluded.signal`. The CHECK constraint `brand_id <> '_unattributed'` (from existing plan Decision 15) is enforced.
- **R12.** New `x_monitor/store.py::Store.read_brands() -> list[BrandRow]` reads all 12 rows from the `brands` table (11 real + `_unattributed` sentinel). Cached at module load for the lifetime of the Store instance.
- **R13.** New `x_monitor/store.py::Store.read_brand_accounts() -> dict[author_id, brand_id]` and `read_brand_hashtags() -> dict[tag, brand_id]` and `read_brand_keywords() -> list[(brand_id, pattern, is_regex)]` and `read_brand_search_terms() -> dict[term, brand_id]` return the runtime detection registry. The new `attribution.py` module loads these once at startup and caches them.
- **R14.** New `x_monitor/__main__.py` subcommand `reattribute` (`python -m x_monitor reattribute [--since <iso>] [--until <iso>] [--batch-size 100]`) walks all posts in the window and runs the new pipeline on each. Idempotent (uses `INSERT OR UPDATE` semantics on `post_brands`).
- **R15.** `x_monitor/run.py::RunPipeline.execute()` updates the per-tweet classification block (currently lines 434-465) to call the new `attribute_to_brands` + `classify_signal(text, brand_ids)` and populate `post["brand_ids"]` (list) + `post["mentions"]` (list of `MentionRow`) + `post["signals"]` (dict[brand_id, signal]) before passing to `Store.insert_posts`.
- **R16.** `x_monitor/store.py::Store.insert_posts(kept_all)` accepts the new fields and writes them in the same transaction as the `posts` insert: posts row → post_brands rows → post_mentions rows → post_brand_signals rows. All within one `Store.transaction()`.
- **R17.** `x_monitor/treemap.py::compute_polarity` SQL uses the JOIN shape from existing plan Decision 18 (no IN subquery), reads `post_brand_signals(brand_id, signal)` + `post_brands(brand_id, post_id)`, applies `WHERE pbs.brand_id != '_unattributed'`.
- **R18.** `x_monitor/dashboard.py::serialize_grid_card` no longer reads `p.source_query_id` for signal counts; JOINs `post_brand_signals` per post inside the polarity window. For multi-brand posts, weight by `post_brands.weight`.
- **R19.** `x_monitor/dashboard.py::attribute_to_brand` (the v1.7 single-brand helper) is kept as a legacy wrapper that returns `attribute_to_brands(...)[0]` for ad-hoc text classification (e.g., drill-down views, headline rendering). The treemap/grid source of truth is the persisted `post_brands` table populated by `compute_post_brands` during ingest.
- **R20.** `x_monitor/intent_classifier.py` becomes a compat shim that re-exports `attribute_to_brands`, `classify_signal` (the per-brand version) from `attribution.py` for any remaining callers. A follow-up commit (not in this plan) deletes the file after all callers migrate.

## Scope Boundaries

- **No new analytics views.** The plan populates the new tables but does NOT add new dashboard pages (e.g., "by company" rollup). That's a follow-on plan.
- **No yaml content changes.** The plan's Unit 0 (11 detection.yaml files) is a separate PR-sized unit, NOT this plan.
- **No YAML directory restructure.** The plan reads from the existing `data/queries/<brand>.yaml`, `data/accounts/<brand>.yaml`, `data/filters/<brand>.yaml` flat layout. Restructuring to `data/brands/<brand>/` is a separate unit (existing plan Unit 3).
- **No detection table backfill.** `brand_hashtags`, `brand_keywords`, `brand_search_terms` are populated by the migration's SQL INSERTs from the existing yaml keywords[] arrays (per existing plan's migration step 4c). The new attribution pipeline reads from these tables; if they're empty, the relevant extractors produce no rows but the pipeline still runs (returning only `user_mention` + `search_term` rows for each post).
- **No translation changes.** `text_en` / `text_zh_cn` / `lang_detected` are populated by the existing translator pipeline (Claude Haiku). The attribution pipeline runs on the original `text` column only; multi-language brand token matching is a future enhancement.
- **No LLM prompt rewrite for brand-aware extraction.** The new `classify_signal(text, brand_ids)` takes brand_ids as input (the upstream extractor pre-narrows the brand set). The LLM prompt includes the brand_ids and asks for per-brand signal.

## Context & Research

### Origin document

The full schema design lives in `docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md` (live as of 2026-06-19). Decisions 6 (4-source extraction), 9 (fractional 1/N weights), 10 (no brand_id on accounts), 13 (raw_token format contract), 14 (ON CONFLICT policy), 15 (_unattributed filter), 18 (compute_polarity SQL JOIN) are the source of truth for this plan. Decisions 1, 3, 4, 5, 7, 8, 11, 12, 16, 17 are informational (already implemented by migration 004).

### Relevant code and patterns

- `x_monitor/store.py:125-260` — `insert_posts` is the central write. Already accepts `brand_id: list | str` and `signal: list[tuple] | list[dict] | str` (the migration-004-aware scaffold was landed pre-shipping). Post-migration behavior is partially live; this plan completes it.
- `x_monitor/store.py:408-434` — `get_all_posts` already JOINs `post_brands` (single-brand filter via legacy `brand_id` param). v1.8 may need a multi-brand variant.
- `x_monitor/store.py:496-629` — `upsert_account` / `get_account` / `get_accounts` / `record_appearance` already use the post-migration shape (`brand_accounts` JOIN). The synthetic `handle:<handle>` author_id (`store.py:523`) is the temporary ID strategy for YAML-seeded accounts.
- `x_monitor/intent_classifier.py:80-225` — `classify_signal` (single string) and `attribute_to_brand` (single string|None). v1.8 needs `attribute_to_brands` (plural) returning all matching brand_ids. The compiled-regex fast-path already supports this — `re.findall` returns every match in iteration order.
- `x_monitor/run.py:434-465` — the per-tweet classification seam. Currently stamps `it["brand_id"] = brand` (single); v1.8 will set `it["brand_ids"] = [b1, b2, ...]` and `it["mentions"] = [(b1, src, raw), ...]` and `it["signals"] = {b1: sig1, b2: sig2}`.
- `x_monitor/run.py:507` — `store.insert_posts(kept_all)` already consumes the v1.8-shaped dicts.
- `x_monitor/translator.py:80-98` — `classify_signal` (single string) — duplicated with `intent_classifier.py:80`. This plan moves the canonical version to `attribution.py` and removes both copies.
- `x_monitor/accounts.py:178-181` — mention extraction loop (already iterates `entities.user_mentions`); v1.8 should emit `post_mentions(source='user_mention')` rows alongside the existing `Edge` writes.
- `x_monitor/apify.py:315-356` — `_normalize_tweet` already returns `raw: item` (the full TwitterAPI.io payload). v1.8 should also surface `entities` parsed as a Python dict (currently stored as JSON only on `posts.entities`).
- `x_monitor/treemap.py` — `compute_polarity` reads post-level signal — needs update to JOIN `post_brand_signals`.

### Existing test patterns

- Fixtures: every test creates a `tempfile.TemporaryDirectory()` with `Path(d)/queries/` and `Path(d)/accounts/` seeded inline (e.g. `test_integration_v17.py:60-98` `_seed_data`). No `conftest.py`.
- Test class style: plain `def test_*` functions, no fixtures with scope>function. `MagicMock` + `monkeypatch` for the API client.
- Store integration tests: always end with `store.close()` in a `finally:` block (`test_store.py:35-46`).
- `attribute_to_brand` tests live in `tests/test_intent_classifier_v17.py` (324 lines, 14+ tests, `V17_BRAND_TOKENS` fixture at line 31). The new `attribute_to_brands` tests extend this file.
- Integration seam test: `test_integration_v17.py:146-182` (`test_v17_pipeline_classifies_call_a_response`) is the closest analog — fake fetcher → `attribute_to_brand` → `insert_posts` → `get_all_posts` round-trip.

### Institutional learnings (must-respect)

1. **Top-gun HF audit lesson** (P0): `INSERT ... ON CONFLICT DO UPDATE` only updates columns in the INSERT's column list. The new `insert_post_brands` / `insert_post_mentions` / `insert_post_brand_signals` must include every column they intend to refresh on conflict in the INSERT column list. Source: `project_top_gun_hf_audit_2026-05-18.md`.
2. **TwitterAPI.io 512-char cap** (P1): X API recent-search has a character-length cap, not operator count. The `search_term` extractor joins `posts.source_query_id` → `search_queries.query_id` → `keywords_json`. Each `search_queries.row` must stay under 512 chars when concatenated as OR groups. Source: `feedback_twitter_x_cap_is_characters_not_operators.md`.
3. **`abort_marker` social handles** (P1): any X handle containing 'abor' / 'Ababor-' in detection yaml is a hallucination marker. Delete without research. The list-add audit must apply this filter.
4. **TwitterAPI.io silent list-fallback** (P2): if `search_queries.query_id` doesn't match a real query, the search returns 20 random Latest tweets (HTTP 200, no error). Add a startup sanity check that asserts ≥1 expected author_handle is in the first response after migration lands. Source: `feedback_twitterapi_unknown_list_silent_fallback.md`.
5. **Compiled-regex detection pattern** (P1): `re.compile("(?:" + "|".join(re.escape(t) for t in tokens) + ")", re.IGNORECASE)` built once per cycle, reused. v1.8's `extract_body_keywords` mirrors this. Source: `project_x_monitoring_2026-06-17.md`.
6. **Worktree hygiene** (P2): new code lands in `~/development/minimax-marketing/worktrees/v18-unit4-call-path/` on branch `feat/v1.8-call-path-attribution`. Symlink `.venv` and `data/x_monitoring.db` from main via `../../../../x-monitoring/...`. Source: `feedback_worktree_hygiene_x_monitoring.md`.

### External References

- X API v2 tweet object — `entities.user_mentions[].id` is numeric, `entities.user_mentions[].username` is mutable handle. Use `id` for FK, `username` only for `raw_token` rendering. https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/tweet
- X API v2 user object — `id` is the immutable numeric user id (the PK X uses internally). `entities.hashtags[].tag` is the hashtag text (no `#` prefix, lowercase).
- SQLite ALTER TABLE DROP COLUMN — supported in 3.35+, project on 3.51.0.

## Key Technical Decisions

- **New module vs. extend intent_classifier.py**: New `x_monitor/attribution.py` module owns the entire pipeline. `intent_classifier.py` becomes a compat shim (R1, R20) and is deleted in a follow-up commit. Rationale: clean separation of per-cycle ingestion logic from per-call intent classification; the new module's surface is much larger (4 extractors + consolidator + classifier + reattribute) and deserves its own home.
- **`classify_signal` is moved to attribution.py, not split**: Both `intent_classifier.py` and `translator.py` have copies. Move the canonical version to `attribution.py::classify_signal(text, brand_ids) -> dict[brand_id, signal]`. `translator.py` becomes translation-only (text_en/text_zh_cn). Rationale: signal classification is per-brand, conceptually part of attribution, not translation.
- **`ON CONFLICT DO UPDATE SET weight = excluded.weight`** (not `DO NOTHING`) for `post_brands` per existing plan Decision 14. Reattribution must overwrite stale weights when the detection registry evolves. Same for `post_mentions.raw_token` and `post_brand_signals.signal`.
- **`brand_id = NULL` in `post_mentions`**: preserved as documented (un-attributed mentions kept with raw_token for later backfill). The PK `(post_id, brand_id, source)` allows NULLs via SQLite's default NULL handling in non-INTEGER-PRIMARY-KEY columns.
- **`reattribute_all_posts` is idempotent**: uses ON CONFLICT DO UPDATE so re-running on the same post updates `weight` / `raw_token` / `signal` to the freshly-computed values. Safe to re-run on the cron or as part of the deploy sequence.
- **No `is_sentinel` filter in compute_post_brands**: the consolidator may legitimately produce `_unattributed` rows. The filter lives at the read side (Decision 15 / Decision 18) in `compute_polarity`'s WHERE clause.
- **Translation runs BEFORE attribution**: the existing translator (`claude-haiku-4-5`) writes `text_en` / `text_zh_cn` / `lang_detected` post-fetch. The new attribution pipeline reads `posts.text` (the original) for `body_keyword` matching. If multi-language brand tokens are needed, that's a future enhancement (the existing detection yaml uses English brand names primarily).

## Open Questions

### Resolved During Planning

- **Where does the per-brand signal classifier live?** `attribution.py`. `intent_classifier.py` and `translator.py` both lose their copies.
- **How do we backfill the 2,008 historical posts?** New `reattribute` subcommand runs the same pipeline; idempotent.
- **What happens if a brand is detected only via `search_term`?** `compute_post_brands` includes it with weight 1.0/N. `post_brand_signals` requires the classifier to return a signal; if the LLM returns `_unattributed` or no signal for that brand, `post_brand_signals` has no row for it (it's filterable at the read side).

### Deferred to Implementation

- **Exact column order in the INSERT statements** — implementation-time detail; the plan specifies the columns and their order in the docstring but the exact SQL is the implementer's call.
- **`MentionRow` dataclass definition** — implementation-time; the plan specifies the fields but the dataclass / NamedTuple / pydantic-model choice is implementation-detail.
- **Compiled-regex pattern for body_keyword** — the existing `_BRAND_RE` pattern handles the single-brand case; the multi-brand `extract_body_keywords` needs to enumerate ALL matches, which `re.finditer` does. The exact regex compile is implementation-time.
- **LLM prompt for per-brand signal classification** — the plan specifies the input (text + brand_ids) and output (dict[brand_id, signal]) but the prompt engineering (e.g., "for each of these brands, what is the post's sentiment toward that brand?") is implementation-time.

## High-Level Technical Design

> *Directional guidance for review, not implementation specification. The implementing agent should treat this as context, not code to reproduce.*

### Data flow on ingest

```
TwitterAPI.io response
       ↓
_normalize_tweet(item) → {id, text, lang, created_at, like_count, author_handle, entities, raw, ...}
       ↓
attribute_to_brands(post, brand_accounts, brand_hashtags, compiled_keyword_index, search_query)
       ↓
4 extractors fan out:
       ├── extract_user_mentions(post)       → [MentionRow, ...]    (source='user_mention')
       ├── extract_hashtag_mentions(post)     → [MentionRow, ...]    (source='hashtag')
       ├── extract_body_keywords(post)         → [MentionRow, ...]    (source='body_keyword')
       └── extract_search_term_match(post)     → [MentionRow, ...]    (source='search_term')
       ↓
compute_post_brands(post, all_mentions)
       ↓
[(brand_id, weight), ...]   weight = 1/N_distinct_brands
       ↓
classify_signal(text, brand_ids)
       ↓
{brand_id: signal, ...}     LLM call returns dict
       ↓
Store.insert_posts(post, brand_ids, mentions, signals)
       ↓
single transaction:
       INSERT INTO posts (...)
       INSERT INTO post_brands(post_id, brand_id, weight) ON CONFLICT DO UPDATE SET weight=excluded.weight
       INSERT INTO post_mentions(post_id, brand_id, source, raw_token, mentioned_at) ON CONFLICT DO UPDATE SET raw_token=excluded.raw_token
       INSERT INTO post_brand_signals(post_id, brand_id, signal) ON CONFLICT DO UPDATE SET signal=excluded.signal
```

### ER reminder (post-migration 004, live)

```
posts (tweet_id PK, no brand column, no signal column)
  ↓ 1:N
post_brands (PK brand_id, post_id, weight REAL)
  ↓
post_mentions (PK post_id, brand_id, source, raw_token, mentioned_at)
  ↓
post_brand_signals (PK post_id, brand_id, signal)
```

```
brands (brand_id PK, display_name, accent_color, is_sentinel)
  ↓ 1:N
  ├── brand_accounts    (PK brand_id, author_id, role)    ← from yaml accounts + staff
  ├── brand_hashtags     (PK brand_id, tag)                  ← from yaml hashtags[]
  ├── brand_keywords     (PK brand_id, pattern, is_regex)   ← from yaml keywords[]
  └── brand_search_terms (PK brand_id, term)                ← from yaml keywords[] (same data, different index)
```

## Implementation Units

### Unit 1: New `x_monitor/attribution.py` module — extractors + consolidator + classifier

**Goal:** Land the new module with all 4 extractors + `compute_post_brands` + `classify_signal(text, brand_ids)`. Module has zero side effects on import; tests can import and exercise in isolation.

**Requirements:** R1, R2, R3, R4, R5, R6, R7, R8

**Dependencies:** Migration 004 (live); `brand_accounts`, `brand_hashtags`, `brand_keywords`, `brand_search_terms` tables exist (migration 004 created them; rows are 0 until Unit 0 lands but the schema supports them).

**Files:**
- Create: `x_monitor/attribution.py`
- Create: `tests/test_attribution.py` (one test file per the existing plan Unit 4 spec)
- Create: `tests/test_extract_user_mentions.py`
- Create: `tests/test_extract_hashtag_mentions.py`
- Create: `tests/test_extract_body_keywords.py`
- Create: `tests/test_extract_search_term_match.py`

**Approach:**
- Define `MentionRow` as a frozen dataclass: `post_id: str, brand_id: str | None, source: Literal['user_mention', 'hashtag', 'body_keyword', 'search_term'], raw_token: str, mentioned_at: str`.
- Define `BRAND_SOURCE_PRIORITY` as a constant dict: `{'user_mention': 1.0, 'hashtag': 0.9, 'body_keyword': 0.7, 'search_term': 0.6}`. Used for confidence scoring (R2).
- `extract_user_mentions(post, brand_accounts: dict[author_id, brand_id], entities: dict) -> list[MentionRow]`: iterate `entities.user_mentions[]`, look up `brand_id` via `brand_accounts[id]`. Emit MentionRow with `brand_id` (or None if not in registry) + `raw_token=f"@{username}"`.
- `extract_hashtag_mentions(post, brand_hashtags: dict[tag, brand_id], entities: dict) -> list[MentionRow]`: iterate `entities.hashtags[]`, lowercase + strip `#`, look up via `brand_hashtags`. Emit with `raw_token=f"#{tag}"`. Skip if not registered (unknown hashtag is noise).
- `extract_body_keywords(post, compiled_keyword_index: list[(brand_id, re.Pattern)]) -> list[MentionRow]`: scan `post.text` once with `re.finditer` over the union pattern, emit one MentionRow per match with `raw_token=<match.group(0)>`. Skip matches where the resolved brand_id is `_unattributed`.
- `extract_search_term_match(post, search_query: list[str], brand_search_terms: dict[term, brand_id]) -> list[MentionRow]`: iterate `search_query` (the post's `source_query_id`'s keywords_json), look up via `brand_search_terms`. Always emit at least one row (with `brand_id=None` if no term matches — preserves the "why this post entered the pipeline" record).
- `compute_post_brands(post, all_mentions: list[MentionRow]) -> list[(str, float)]`: union of non-NULL brand_ids, return `[(brand_id, 1.0 / N)]` per brand. Empty union → `[('_unattributed', 1.0)]`.
- `classify_signal(text: str, brand_ids: list[str], brand_registry: list[BrandRow], anthropic_client: AnthropicClaudeClient | None = None) -> dict[str, str]`: build the prompt with `text` + explicit `brand_ids`, send to Claude Haiku 4.5, parse the response as `dict[brand_id, signal]`. Validate every brand_id against `brand_registry` (drop hallucinations). Return empty dict on LLM failure (logged as `WARN: classify_signal returned no signals for post X`).

**Patterns to follow:**
- `x_monitor/dashboard.py:67-70` — the existing `_BRAND_RE` compiled-regex pattern.
- `x_monitor/intent_classifier.py:106` — `build_compiled_brand_pattern` helper.
- `x_monitor/translator.py:80-98` — the existing Claude Haiku call shape.
- `tests/test_intent_classifier_v17.py` — test style (plain functions, no class fixtures, MagicMock for the LLM).

**Test scenarios:**

- `test_attribution.py`:
  - **Happy path - single brand via author handle**: post by `@MiniMaxAI` (in `brand_accounts` for minimax) → `extract_user_mentions` returns `[(minimax, user_mention, "@MiniMaxAI")]`. `compute_post_brands` returns `[(minimax, 1.0)]`.
  - **Happy path - single brand via hashtag**: post by `random_user` with `#kimi` in entities → `extract_hashtag_mentions` returns `[(moonshot_kimi, hashtag, "#kimi")]`.
  - **Happy path - single brand via body keyword**: post text "I love Qwen 3" → `extract_body_keywords` returns `[(qwen, body_keyword, "Qwen 3")]`.
  - **Happy path - single brand via search term**: post fetched by query with `minimax` keyword → `extract_search_term_match` returns `[(minimax, search_term, "minimax")]`.
  - **Happy path - multi-brand, equal split**: post naming "Qwen 3 vs DeepSeek V3" in text → `extract_body_keywords` returns 2 MentionRows (one per brand), `compute_post_brands` returns `[(qwen, 0.5), (deepseek, 0.5)]`.
  - **Edge case - no brand found**: post by random_user, no entities, no search-term match → `compute_post_brands` returns `[('_unattributed', 1.0)]`.
  - **Edge case - dedup, 3 sources → 1 brand**: post by `@MiniMaxAI` with text "minimax M3.0 is great" → 3 MentionRows from 3 sources, all `brand_id=minimax`; `compute_post_brands` returns `[(minimax, 1.0)]`.
  - **Edge case - case-insensitive hashtag**: post with `#MINIMAX` → resolves to `brand_id=minimax`.
  - **Edge case - case-insensitive body keyword**: post text "I love MINIMAX" → matches pattern.
  - **Edge case - unknown hashtag silently dropped**: post with `#worldcup-2026` → no MentionRow emitted.
  - **Edge case - unknown user_mention with brand_id NULL**: post mentioning `@random_user` not in `brand_accounts` → MentionRow with `brand_id=None`.
  - **Edge case - body_keyword pattern with regex**: pattern `M[0-9]+\.[0-9]+` matches "M3.0" and "M2.7".
  - **Error path - entities NULL**: post with `entities=None` → all extractors return `[]`, `compute_post_brands` returns `[('_unattributed', 1.0)]`.
  - **Error path - entities is string 'null'**: post with `entities="null"` → all extractors return `[]`, no AttributeError.
  - **Integration - raw_token format**: for every extractor, assert `raw_token` matches Decision 13 format (`@` prefix for user_mention, `#` prefix for hashtag, bare for body_keyword, as-is for search_term).
  - **Integration - `classify_signal` validates brand_ids**: LLM returns `[(minimax, praise), (qwen, criticism)]` (real brands) → preserved. LLM returns `[(m3_pro, praise)]` (hallucinated brand) → dropped from output.
- `test_extract_user_mentions.py`: focuses on the user_mention extractor; 8 scenarios (happy, unknown handle, empty entities, malformed username, etc.).
- `test_extract_hashtag_mentions.py`: focuses on the hashtag extractor; 6 scenarios.
- `test_extract_body_keywords.py`: focuses on the body_keyword extractor; 10 scenarios (single match, multi-match, regex capture groups, compiled-regex reuse, etc.).
- `test_extract_search_term_match.py`: focuses on the search_term extractor; 5 scenarios.

**Verification:**
- `pytest tests/test_attribution.py tests/test_extract_*.py -v` passes all tests.
- Module imports cleanly: `python -c "from x_monitor.attribution import extract_user_mentions, compute_post_brands, classify_signal; print('OK')"`.
- No Python deprecation warnings.

---

### Unit 2: New `x_monitor/store.py` write methods + detection table reads

**Goal:** Land `insert_post_brands`, `insert_post_mentions`, `insert_post_brand_signals`, `read_brands`, `read_brand_accounts`, `read_brand_hashtags`, `read_brand_keywords`, `read_brand_search_terms`, plus an `insert_posts` enhancement that writes to all 4 tables in one transaction.

**Requirements:** R9, R10, R11, R12, R13, R16

**Dependencies:** Unit 1 (module + dataclasses); migration 004 (live).

**Files:**
- Modify: `x_monitor/store.py` (insert_posts + 7 new methods)
- Modify: `tests/test_store.py` (extend the existing insert_posts round-trip tests with post_brands/post_mentions/post_brand_signals assertions)
- Modify: `tests/test_store_v17.py` (add post-004 schema verification)

**Approach:**
- `Store.read_brands() -> list[BrandRow]`: SELECT brand_id, display_name, accent_color, is_sentinel FROM brands ORDER BY display_name. Cache in `self._brand_cache`.
- `Store.read_brand_accounts() -> dict[author_id, brand_id]`: SELECT author_id, brand_id FROM brand_accounts. Return as dict.
- `Store.read_brand_hashtags() -> dict[str, brand_id]`: SELECT tag, brand_id FROM brand_hashtags. Lowercase keys.
- `Store.read_brand_keywords() -> list[(brand_id, pattern, is_regex)]`: SELECT brand_id, pattern, is_regex FROM brand_keywords.
- `Store.read_brand_search_terms() -> dict[str, brand_id]`: SELECT term, brand_id FROM brand_search_terms.
- `Store.insert_post_brands(post_id, brand_id, weight)`: ON CONFLICT DO UPDATE per R9. Top-gun ON CONFLICT lesson: every column in the UPDATE SET clause must be in the INSERT column list.
- `Store.insert_post_mentions(post_id, brand_id, source, raw_token, mentioned_at)`: ON CONFLICT DO UPDATE per R10. brand_id nullable.
- `Store.insert_post_brand_signals(post_id, brand_id, signal)`: ON CONFLICT DO UPDATE per R11. `_unattributed` blocked by CHECK constraint (existing migration 004).
- `Store.insert_posts(kept_all)` enhanced: accepts `brand_ids: list[str]`, `mentions: list[MentionRow]`, `signals: dict[str, str]` on each post dict. Wraps in one `Store.transaction()`: posts insert → post_brands → post_mentions → post_brand_signals.

**Patterns to follow:**
- `x_monitor/store.py:138-161` — the existing `insert_posts` transactional pattern.
- `x_monitor/store.py:496-629` — the existing `upsert_account` ON CONFLICT pattern.
- `x_monitor/store.py` — the existing `Store.transaction()` context manager.

**Test scenarios:**

- `test_store.py::test_insert_posts_writes_post_brands`: insert a 2-brand post → `post_brands` has 2 rows with weights summing to 1.0.
- `test_store.py::test_insert_posts_writes_post_mentions`: insert a post with user_mention + hashtag → `post_mentions` has 2 rows with correct `source` + `raw_token`.
- `test_store.py::test_insert_posts_writes_post_brand_signals`: insert a post with 2-brand signals → `post_brand_signals` has 2 rows.
- `test_store.py::test_insert_post_brands_upsert_on_conflict`: insert same (post_id, brand_id) twice with different weight → second INSERT overwrites (weight = latest value).
- `test_store.py::test_insert_post_brand_signals_rejects_unattributed`: insert (post_id, '_unattributed', 'praise') → IntegrityError.
- `test_store.py::test_insert_post_mentions_allows_null_brand_id`: insert (post_id, None, 'user_mention', '@random') → succeeds.
- `test_store.py::test_read_brands_returns_12_rows`: insert 11 + sentinel → SELECT returns 12.
- `test_store.py::test_read_brand_accounts_returns_dict`: insert 5 brand_accounts → SELECT returns 5-entry dict keyed by author_id.
- `test_store_v17.py::test_migration_004_brands_seeded`: assert migration 004 seeded 12 brands incl. `_unattributed` with is_sentinel=1.

**Verification:**
- `pytest tests/test_store.py tests/test_store_v17.py -v` passes.
- `pytest tests/ -q` is green (no regression in 297+ tests).

---

### Unit 3: Update `x_monitor/run.py` per-tweet classification seam

**Goal:** Replace the v1.7 single-brand `attribute_to_brand` call with the new `attribute_to_brands` (plural). Populate `post["brand_ids"]`, `post["mentions"]`, `post["signals"]` on each item before passing to `Store.insert_posts`.

**Requirements:** R15

**Dependencies:** Units 1, 2 (modules + Store methods).

**Files:**
- Modify: `x_monitor/run.py` (the per-tweet classification block, currently lines 434-465)
- Modify: `x_monitor/intent_classifier.py` (compat shim — re-export `attribute_to_brands` and the per-brand `classify_signal` from `attribution.py`)
- Modify: `tests/test_run.py` (extend the existing `test_intent_call_reclassifies_brand_id` with multi-brand assertion)

**Approach:**
- At the start of `RunPipeline.execute()`, load detection tables once: `brand_accounts = store.read_brand_accounts()`, `brand_hashtags = store.read_brand_hashtags()`, `compiled_keyword_index = compile_keyword_index(store.read_brand_keywords())`, `search_query_by_id = {row.query_id: row.keywords_json for row in store.read_search_queries()}`.
- For each intent call's items, replace the v1.7 `attribute_to_brand(text, ...)` call with `attribute_to_brands(post, brand_accounts, brand_hashtags, compiled_keyword_index, search_query_by_id.get(it["source_query_id"], []))`.
- Populate `it["brand_ids"]`, `it["mentions"]`, `it["signals"]` on each item.
- The downstream `filter_and_review` and `Store.insert_posts` consume the new fields.

**Patterns to follow:**
- `x_monitor/run.py:434-465` — the existing classification block (replace in place, don't restructure).
- `x_monitor/run.py:273` — the existing `Store` open + migration pattern.

**Test scenarios:**

- `test_run.py::test_intent_call_classifies_multi_brand`: synthetic fetch returns a 2-brand post → assert `it["brand_ids"] == ["qwen", "deepseek"]`, weights sum to 1.0, `post_mentions` has 2+ rows.
- `test_run.py::test_intent_call_passes_mentions_to_insert_posts`: assert `Store.insert_posts` receives `mentions` field on each post dict.
- `test_run.py::test_intent_call_passes_signals_to_insert_posts`: assert `signals` field populated by `classify_signal`.

**Verification:**
- `pytest tests/test_run.py -v` passes.
- A real pipeline run (one cycle) produces `data/runs/<ts>/summary.json` with `brand_id` keys AND `data/brands/<brand>/` not empty for the brands seen.

---

### Unit 4: Update `x_monitor/dashboard.py` polarity + signal aggregation

**Goal:** `compute_polarity` JOINs `post_brand_signals` per brand (no IN subquery per existing plan Decision 18). `serialize_grid_card` reads `post_brand_signals` (not `posts.source_query_id`).

**Requirements:** R17, R18

**Dependencies:** Units 2, 3 (post_brand_signals populated).

**Files:**
- Modify: `x_monitor/dashboard.py` (compute_polarity call sites, serialize_grid_card signal aggregation)
- Modify: `x_monitor/treemap.py` (compute_polarity SQL JOIN rewrite)
- Modify: `tests/test_dashboard.py` (replace any `posts.signal` assertions with `post_brand_signals` JOIN assertions)

**Approach:**
- `compute_polarity(brand_id, window_days) -> dict[signal, weighted_count]`: SELECT pbs.signal, SUM(pb.weight) FROM post_brand_signals pbs JOIN post_brands pb ON pb.post_id = pbs.post_id AND pb.brand_id = pbs.brand_id JOIN posts p ON p.tweet_id = pbs.post_id WHERE pbs.brand_id = :brand_id AND pbs.brand_id != '_unattributed' AND p.created_at >= :window_start GROUP BY pbs.signal.
- `serialize_grid_card(post, brand_id)`: for each post in the brand's window, JOIN `post_brand_signals` to get the signal. Weight by `post_brands.weight`.

**Patterns to follow:**
- Existing plan Decision 18 (JOIN not IN subquery) — exact SQL shape documented there.
- `x_monitor/dashboard.py:264-386` — the existing `serialize_grid_card` shape.

**Test scenarios:**

- `test_dashboard.py::test_treemap_renders_with_real_data`: after reattribute, assert the treemap's polarity chart shows non-zero values for at least one brand.
- `test_dashboard.py::test_polarity_uses_join_not_subquery`: EXPLAIN QUERY PLAN on compute_polarity → no SCAN, no SORT.
- `test_dashboard.py::test_unattributed_excluded_from_polarity`: `compute_polarity('_unattributed')` returns empty dict.

**Verification:**
- `pytest tests/test_dashboard.py tests/test_treemap.py -v` passes.
- Browser smoke test: dashboard renders 11 brand tiles with non-zero polarity (after reattribute).

---

### Unit 5: `reattribute` subcommand + transactional reattribute_all_posts

**Goal:** New `python -m x_monitor reattribute [--since <iso>] [--until <iso>] [--batch-size 100]` subcommand walks all posts in the window and runs the new attribution pipeline on each. Idempotent.

**Requirements:** R14

**Dependencies:** Units 1, 2, 3.

**Files:**
- Modify: `x_monitor/__main__.py` (add the `reattribute` subcommand)
- Create: `x_monitor/reattribute.py` (the subcommand implementation)
- Modify: `tests/test_reattribute.py` (new tests for the subcommand)

**Approach:**
- `reattribute.py::run_reattribute(args)`: load posts in batches of 100 (configurable), for each batch run the full pipeline (load detection tables ONCE at start, then for each post: extract 4 sources → compute_post_brands → classify_signal → write to post_brands/post_mentions/post_brand_signals via Store methods).
- Log progress: `INFO: reattributed <N>/<total> posts`.
- Idempotent via ON CONFLICT DO UPDATE on all 3 write methods.
- Emit `data/runs/<ts>/reattribute_summary.json` with per-brand counts: `{"minimax": {"posts": 1500, "weight_sum": 1500.0, "signals": {"praise": 200, "criticism": 50, ...}}, ...}`.

**Patterns to follow:**
- `x_monitor/__main__.py` (the existing subcommand shape — argparse subparsers).
- `x_monitor/run.py::RunPipeline.execute()` (the per-post loop pattern).

**Test scenarios:**

- `test_reattribute.py::test_reattribute_populates_post_brands`: with 100 synthetic posts (mix of 1-brand, 2-brand, 3-brand, 0-brand), run reattribute → assert `post_brands` count, weight conservation (sum = 100.0 ± 0.001 epsilon), and per-brand counts.
- `test_reattribute.py::test_reattribute_idempotent`: run twice → no duplicate rows in `post_brands`.
- `test_reattribute.py::test_reattribute_emits_summary`: run on 50 posts → assert `data/runs/<ts>/reattribute_summary.json` exists with correct structure.
- `test_reattribute.py::test_reattribute_handles_zero_brand_posts`: 10 posts with no detected brand → all 10 get `_unattributed` rows.

**Verification:**
- `python -m x_monitor reattribute --since 2026-01-01` on a copy of the live DB completes in <10 min for 2,008 posts.
- `data/runs/<ts>/reattribute_summary.json` has correct per-brand counts.
- `post_brands` row count matches posts count after reattribute.

---

### Unit 6: Compat shim in `x_monitor/intent_classifier.py` + cleanup

**Goal:** Make `intent_classifier.py` a thin compat shim that re-exports `attribute_to_brands` and the per-brand `classify_signal` from `attribution.py` for any remaining callers. A follow-up commit (not in this plan) deletes the file.

**Requirements:** R20

**Dependencies:** Units 1, 3.

**Files:**
- Modify: `x_monitor/intent_classifier.py` (replace implementations with re-exports)
- Modify: `tests/test_intent_classifier_v17.py` (mark legacy tests as expected-to-pass-via-shim)

**Approach:**
- Replace the body of `intent_classifier.py::attribute_to_brand` with: `from x_monitor.attribution import attribute_to_brands; def attribute_to_brand(...): return attribute_to_brands(...)[0] if attribute_to_brands(...) else None`. Add a deprecation comment.
- Replace `classify_signal` with re-export: `from x_monitor.attribution import classify_signal as classify_signal_per_brand`.
- Add a `DeprecationWarning` to legacy callers.

**Patterns to follow:**
- Standard Python deprecation pattern.

**Test scenarios:**

- `test_intent_classifier_v17.py::test_attribute_to_brand_legacy_compat`: existing legacy tests still pass via the shim.
- `test_intent_classifier_v17.py::test_classify_signal_deprecation_warning`: calling the legacy `classify_signal` emits a `DeprecationWarning`.

**Verification:**
- `pytest tests/test_intent_classifier_v17.py -v` passes (legacy tests + new compat tests).
- `python -W default -c "from x_monitor.intent_classifier import classify_signal"` emits a deprecation warning.

---

## System-Wide Impact

- **Interaction graph:** `RunPipeline.execute` is the only producer of the new `post_brands` / `post_mentions` / `post_brand_signals` rows during ingest. `compute_polarity` (treemap), `serialize_grid_card` (grid), `/brand/<id>` (drill-down) are the only consumers. `reattribute` is a backfill entry point that bypasses the live ingest. All entry points converge on `Store.insert_posts` (R16) — one transactional seam.
- **Error propagation:** a failure in `Store.insert_posts` (FK violation, CHECK constraint) rolls back the entire transaction including the `posts` row. The pipeline worker retries on the next cycle. A failure in `classify_signal` (LLM unavailable) emits an empty dict, which the caller treats as "no signals for this post" — `post_brand_signals` has no row for this post, and the read side filters accordingly.
- **State lifecycle risks:** the synthetic `handle:<handle>` author_id strategy (`store.py:523`) for YAML-seeded accounts is unchanged. The new `brand_accounts` table is the runtime source of truth (replaces the YAML `accounts[]` arrays). On migration 004, the table starts empty; the first `account_graph` run seeds it from the YAML. Until then, `extract_user_mentions` returns brand_id=NULL for all mentions.
- **API surface parity:** `attribute_to_brand` (singular) stays as a compat shim (R20). External callers (none today — internal only) see no breaking change. The `posts.brand_id` and `posts.signal` columns are gone; any code reading them will fail with `no such column`. This is by design (the schema change is atomic).
- **Integration coverage:** the closest existing integration test is `test_integration_v17.py:146-182` (`test_v17_pipeline_classifies_call_a_response`). The new plan adds `test_reattribute.py` + extends `test_run.py` with multi-brand round-trips. Together they cover the full chain: fetch → classify → write → read back.
- **Unchanged invariants:** the dashboard's UI (treemap, grid, drill-down, polarity window toggle, view tabs) does not change. The data model behind it is reshaped; the surface is not.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The synthetic `handle:<handle>` author_id strategy collides with a real X user whose id happens to be the string "handle:<handle>". | Very low | Low | The format is namespace-prefixed (`handle:` prefix); X user ids are numeric. Collision impossible by construction. |
| `ON CONFLICT DO UPDATE` silently skips a column because it's not in the INSERT's column list (top-gun HF audit lesson). | Med | High | Document the ON CONFLICT column-update gotcha in the docstring of every write method. Add a unit test that asserts each column IS updatable (insert then update same PK with new value, assert new value reflects). |
| The LLM hallucinates brand_ids that don't exist in the `brands` table. | Med | Med | `classify_signal` validates every brand_id against `Store.read_brands()` and drops hallucinated IDs. Logged as `WARN: dropped <N> hallucinated brand_ids`. |
| Reattribute on 2,008 posts takes >15 min, blocks the next cron cycle. | Low | Med | Default batch_size=100 with progress logging. Tested on a copy of prod DB before live reattribute. If too slow, run as a background process detached from the cron. |
| The new `attribution.py` module is too large (>500 lines) and hard to navigate. | Med | Low | Split per-extractor if it grows: `attribution/extractors.py`, `attribution/consolidator.py`, `attribution/classifier.py`. Package layout decision deferred to implementation. |
| `search_queries.keywords_json` is the wrong source for the search_term extractor (the v1.7 plan said it's the right one, but live data may differ). | Low | Med | The plan specifies reading from `search_queries` per existing plan Decision 8. If live data has posts with `source_query_id` not in `search_queries`, the extractor emits `brand_id=None` rows (preserves raw_token). Reattribute logs the orphan count. |
| Body keyword matching on the original `text` column misses non-English brand names (the dashboard includes Chinese brands). | Med | Low | Out of scope per "no translation changes" boundary. Future enhancement: run `extract_body_keywords` on `text_en` AND `text_zh_cn`. |
| Multi-brand attribution breaks the Combined chart's "posts per brand" count (the chart assumes 1 brand per post). | Med | Med | The Combined chart counts each post toward each brand **proportionally to weight** (per project memory). If `compute_post_brands` returns 1 row with weight=0.5, the Combined chart adds 0.5 to each brand's count. Verify in browser smoke test after reattribute. |
| The 4-source extraction produces duplicate `(post_id, brand_id, source)` rows on re-ingest (the ON CONFLICT clause handles this, but the raw_token may differ). | Med | Low | ON CONFLICT DO UPDATE SET raw_token = excluded.raw_token. The latest write wins. Idempotent. |

## Documentation / Operational Notes

- **Schema doc update:** `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md` describes the pre-migration state. After this plan lands, re-emit as `docs/reference/2026-06-19-HHMMSS-x-monitoring-db-schema-v2.md` documenting the new tables. Mark the old doc as deprecated.
- **Runbook update:** add a "Post-ingest verification" section to `deploy/migration-004-runbook.md` describing: (a) how to verify the new tables are populated after a pipeline run, (b) how to run `reattribute` as part of the deploy sequence, (c) the MON-NN alerts to watch in the first 24h after reattribute.
- **CHANGELOG / commit message style:** follow the project's conventional commit format (`feat(x-monitor): call-path attribution pipeline`). Each unit lands as its own atomic commit.
- **Branch:** `feat/v1.8-call-path-attribution` from `feat/v1.8-company-brand-account-model` (the schema migration branch). After the schema migration is merged to main, this branch rebases. After this plan lands, delete `feat/v1.8-company-brand-account-model` per `feedback_git_clean_gone_branches` convention.
- **Operator launch steps:** the deploy sequence is:
  1. Apply the schema migration (already done 2026-06-19).
  2. Land this plan's code (Units 1-6).
  3. Run `python -m x_monitor reattribute --since 2026-01-01` on the live DB. Expect ~5-10 min for 2,008 posts.
  4. Verify dashboard renders with real data.
  5. Restart LaunchAgent + dashboard.

## Sources & References

- **Origin document:** [docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md](docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md)
- Related code: `x_monitor/store.py`, `x_monitor/intent_classifier.py`, `x_monitor/translator.py`, `x_monitor/run.py`, `x_monitor/dashboard.py`, `x_monitor/treemap.py`, `x_monitor/apify.py`, `x_monitor/__main__.py`
- Related plans: `docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md`, `docs/plans/2026-06-17-002-feat-finviz-treemap-front-page-plan.md`, `docs/plans/2026-06-19-003-feat-combined-chart-page-plan.md`
- Related PRs/issues: PR #3 (v1.7), PR for migration 004 (merged 2026-06-19)
- External docs:
  - X API v2 tweet object: https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/tweet
  - X API v2 user object: https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/user
- Institutional learnings: `project_top_gun_hf_audit_2026-05-18.md` (ON CONFLICT column-update gotcha), `feedback_twitter_x_cap_is_characters_not_operators.md` (512-char cap), `feedback_worktree_hygiene_x_monitoring.md` (worktree layout), `feedback_pkill_matches_all_dashboardapp.md` (kill-by-port), `project_x_monitoring_combined_chart_2026-06-19.md` (proportional weight for multi-brand), `feedback_abor_Ababor- in social-handle tables = model hallucination marker.md` (delete 'abor' handles)
- Existing plan Decisions referenced: 6, 9, 10, 13, 14, 15, 18