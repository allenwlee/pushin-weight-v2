# Changelog

All notable changes to x-monitor are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/).

## [1.8.0] - 2026-06-19

### Added

- **Call-path attribution pipeline** — new `x_monitor.attribution` module
  decomposes a single tweet into per-brand mentions across four
  extraction sources (user_mention, hashtag, body_keyword, search_term).
  Replaces the v1.7 first-match-wins single-brand classifier with
  all-matches-wins, so a tweet naming two brands produces one row per
  detected brand in `post_brands` / `post_mentions` / `post_brand_signals`.
- **`post_brands`, `post_mentions`, `post_brand_signals` tables**
  (migration 004) — the runtime source of truth for which brands a
  post mentions and what signal (Q1-Q6) it carries per brand. The
  legacy first-class brand column and signal column on the `posts`
  table are dropped.
- **`x_monitor.reattribute` CLI subcommand** — backfill the new
  v1.8 tables for historical posts. Re-runs the multi-brand pipeline
  over every post in the DB (or every post since `--since YYYY-MM-DD`).
  Run once after upgrading, then never again.
- **LLM-based per-brand signal classification** —
  `x_monitor.attribution.classify_signal(text, brand_ids, ...)` asks
  Claude Haiku to decompose a tweet into a per-brand signal map.
  Hallucinated brand_ids (not in the `brands` table) are dropped.
- **Brand source priority (R2)** — `user_mention` + `hashtag` are
  higher confidence than `body_keyword` + `search_term`. Multi-source
  matches take the max confidence across contributing sources.
- **Per-brand fractional weight** — `compute_post_brands` returns a
  `weight` per (post, brand) row that the Combined chart uses for
  proportional multi-brand counting.
- **`__all__` public API on `x_monitor`, `x_monitor.attribution`,
  `x_monitor.store`** — stable import surface; downstream scripts
  can `from x_monitor import Store, attribute_to_brands, ...`.

### Changed

- **DB column rename on the `posts` table** — the legacy count
  column is renamed to its user-facing name `like_count` (per
  Decision 3, R9). Templates and the serializer return `like_count`
  keys; the migration handles the rename atomically.
- **`x_monitor.intent_classifier` is now a compat shim** — the
  legacy `classify_signal(text)` (single-string) and
  `attribute_to_brand(text, ...)` (single-brand) helpers are kept
  and emit `DeprecationWarning` directing callers to the v1.8
  multi-brand equivalents in `x_monitor.attribution`. A follow-up
  commit deletes the file.
- **`account_post_appearances` PK changed** from
  `(model_name, handle, tweet_id)` to `(author_id, tweet_id)`
  (Decision 4). Synthetic `handle:<handle>` author_ids resolve to
  the canonical account row.
- **Dashboard polarity is computed per-brand** — the treemap's
  polarity score is now `signals[brand]` (praise - criticism) / total,
  read from `post_brand_signals`. Posts without a row for the active
  brand don't count.

### Removed

- The legacy first-class brand column and signal column on the
  `posts` table (replaced by `post_brands` / `post_brand_signals`).
- The legacy `model_name` column on `posts`, `accounts`, and
  `account_post_appearances` (replaced by the `brand_accounts` edges
  and `author_id` synthetic id strategy).
- v1.7 single-brand `attribute_to_brand` first-match-wins logic
  (still importable from `x_monitor.intent_classifier` for legacy
  callers, but emits `DeprecationWarning`).

### Operator notes

- The deploy sequence is: apply migration 004 (already done 2026-06-19),
  land this code, then run `python -m x_monitor reattribute --since
  2026-01-01` on the live DB. Expect 5-10 min for ~2,000 posts.
- After `reattribute`, verify the dashboard renders with real data
  before restarting the LaunchAgent + dashboard.
- See `docs/plans/2026-06-19-004-feat-call-path-attribution-pipeline-plan.md`
  for the full plan and per-unit detail.

## [1.7.0] - 2026-06-17

### Added

- 2-call wide-net ingest (Call A `list:<id>` operator escape hatch +
  Call B paren-grouped brand-wide) replacing the per-account 42-call
  cycle. 84% cost reduction (~ $13-22/mo at 15-min cadence, was
  $91-135/mo).
- LLM translation pass (Claude Haiku 4.5) for `text_en` and
  `text_zh_cn` columns. Adds the locale switcher in the dashboard UI.
- `cookie:`-free TwitterAPI.io migration as the primary data source.

## [1.6.0] - 2026-06-16

### Added

- 15-minute cron cadence (was 30-min).
- Multi-page search result handling (X caps ~22 ORs/query, TwitterAPI.io
  caps 20 tweets/page).
- Topbar staleness indicator (`#last-run-stamp` + `.stale` amber
  class after 1h of no poll).

## [1.5.0] and earlier

- See git history: `git log --oneline -- x-monitoring/`.
