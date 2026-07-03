---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
title: Post-fetch taxonomy extension, multi-discourse, and v10 bug fixes
type: feat
date: 2026-07-03
status: ready
origin:
  - v10 smoketest output at /tmp/random10_smk_v10.md
  - brainstorm at docs/brainstorms/2026-07-03-140809-brainstorm-adv-mktg-scam-crypto-x-posts.md
  - prior brainstorm at docs/plans/2026-07-03-120000-taxonomy-extension-for-promotional-crypto-posts-plan.md (superseded — see Supersession Note §12)
  - Plan2 at docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md (taxonomy + multi-discourse scaffolding already shipped in migration 026)
supersedes: docs/plans/2026-07-03-120000-taxonomy-extension-for-promotional-crypto-posts-plan.md
deepened: 2026-07-03
---

# Post-fetch taxonomy extension, multi-discourse, and v10 bug fixes

## Goal Capsule

Extend the post-fetch classification pipeline so it cleanly tags two new high-signal post classes (advertising/marketing, event/announcement), surfaces crypto/scam/unauthorized flags as a persistent `posts_unsanctioned_flags` row, allows a single post to carry multiple `discourse_role` tags AND multiple `post_type` tags per brand, and closes four v10 smoketest bugs: the `text_en` echo for `lang_detected=zh_cn` posts, brand detection for Chinese-only posts, `genuine_hype` over-rating of promotional CTAs, and post-8's missing `buzz_release` alongside `performance_comparisons`.

Primary actor: DevRel / marketing triage.
Desired outcome: every post leaves the post-fetch pipeline with N orthogonal labels (`post_types[]`, `sentiment`, `discourse_roles[]`, `china/us_nationalism`) plus an optional `unsanctioned_flags` row, all of which the dashboard can filter on.

Open blockers: none. Builds on shipped U1 (migration 026), shipped U4 (`classify_pragmatics_full`), shipped U7 (smoketest runner), and existing brand-keyword yaml infrastructure.

Product Contract preservation: changed — see Supersession Note §12. The prior brainstorm at `2026-07-03-120000-...-plan.md` proposed only taxonomy extension; this plan widens scope to include multi-discourse + v10 bug fixes + multi-post_type + the unsanctioned-flags table per the user's request. Five 120000-plan keys are intentionally substituted (see §12).

## Problem Frame

v10 of the smoketest (see `/tmp/random10_smk_v10.md`) classified 12/12 random posts and surfaced five issues that the shipped post-fetch pipeline does not handle:

1. **Promotional/CTA posts are mislabeled `genuine_hype`.** Post 4 ("GLM 5.2 vs Kimi k2.7 vs Claude Opus 4.8" — pure Chinese-language benchmark, calls GLM 5.2 the "班级里的尖子生") and Post 5 (a MiniMax M3 review with "limited-time free access [URL]" CTA) both returned `discourse_role=genuine_hype`. The first is genuinely benchmark praise; the second is a paid promotion dressed as hype.
2. **`text_en` echoes Chinese source text.** Post 4's source text is Simplified Chinese but `text_en` was populated with the same Chinese characters (literal copy of source, not a translation). The current noop rule only NULLs `text_en` for `lang_detected=en*` family — it does NOT NULL it when the source is already in the target locale's sibling locale.
3. **Brand detection misses Chinese-only posts that mention multiple brands.** Post 4 (Chinese-only "GLM 5.2 vs Kimi k2.7 vs Claude Opus 4.8") was attributed to `moonshot_kimi` only — GLM and Opus are missing. Investigation in U6a will determine whether the gap is in the brand-keyword seed, the regex compilation, or the smoketest runner's `_load_latest_cycle_posts`.
4. **`post_type` and `discourse_role` are single-label.** Post 3 ("Why there is so much hype around GLM 5.2 as myself being claude user am I running behind") could legitimately be both `performance_comparisons` (mentions a model version being compared) AND `feedback_questions` ("am I running behind"). The current `posts_brands_signals` table has `PRIMARY KEY (post_id, brand_id)` only — there is no schema support for N post_types per (post × brand). This is the critical migration blocker; U1b extends the PK.
5. **No way to mark a post as scam/spam/crypto.** Post 7 ("⚡ Everything is waiting for liquidity trigger. Join in our🦅 Telegram ... $GLM $NUSD") is a crypto scam — the classifier returned `genuine_hype` because `discourse_role` has no scam bucket. The brainstorm at `docs/brainstorms/2026-07-03-140809-...md` recommends a separate `posts_unsanctioned_flags` table for `marketing_spam | scam | crypto | unauthorized` flags.

The brainstorm at `docs/plans/2026-07-03-120000-taxonomy-extension-for-promotional-crypto-posts-plan.md` (requirements-only) covers only the new `post_type` + `discourse` values. This plan widens scope to (a) ship those taxonomy values, (b) add multi-discourse + multi-post_type support, (c) add the `posts_unsanctioned_flags` table, and (d) close the four v10 bugs. The 120000 plan is superseded (see §12).

## Requirements

**R1.** Add two new `post_type_keys` rows: `advertising_marketing`, `event_announcement`. Seed labels in `post_type_labels` for en + zh_cn.

**R2.** Add one new `discourse_keys` row: `advertising-marketing` (hyphenated, see KTD7). Seed labels in `discourse_labels` for en + zh_cn.

**R3.** Add a new `posts_unsanctioned_flags` table (post_id TEXT PRIMARY KEY, flags TEXT NOT NULL JSON, evidence TEXT, decided_at TEXT, FK → posts.tweet_id ON DELETE CASCADE). Index on a generated column `flag_set TEXT GENERATED ALWAYS AS (json_extract(flags, '$')) STORED` (per KTD3). If the host's SQLite version predates 3.31.0, fall back to a normalized junction table (documented in the migration header).

**R4.** Modify `classify_pragmatics_full` to emit per (post × brand) row: `post_types: string[]` (array), `discourse_roles: string[]` (array), `sentiment`, `china_nationalism`, `us_nationalism`. Emit at top level (outside `classifications`): `unsanctioned_flags: string[]`.

**R5.** Allow N `post_types` per (post × brand). Migration 027b extends `posts_brands_signals` PK from `(post_id, brand_id)` to `(post_id, brand_id, post_type_key)`. The `sentiment` column moves out of the implicit uniqueness constraint — it becomes a per-(post,brand,post_type) value, which is the correct semantic (each post_type can have its own sentiment, e.g., a perf_comparisons post that's positive overall but its feedback_questions aspect is mixed).

**R6.** Fix the `text_en` echo bug. When `lang_detected` is in the Simplified Chinese family (`zh`, `zh-Hans`, `zh-CN`, `zh_CN_Hans`), set `text_en = None` server-side. The translator's system prompt should also be updated so the LLM does NOT echo the source into the locale column that matches the source.

**R7.** Investigate brand detection for Chinese-only multi-brand posts, then fix the root cause. Investigation first (U6a delivers a written root-cause note), fix second (U6b applies the targeted code or seed change).

**R8.** Update the `genuine_hype` rule in `build_pragmatics_full_prompt`: "**genuine_hype is incompatible with explicit call-to-action.** If the post contains a CTA (URL + verb like 'try', 'sign up', 'join', 'get', 'limited-time', 'free access', 限时免费, 立即体验, 注册, 点击), discount offer, or wrapper/promo language ('one API key', 'OpenAI-compatible gateway', 'free credit no card'), prefer `discourse_role=advertising-marketing` over `genuine_hype`. If both genuine praise AND a CTA coexist, emit BOTH `discourse_roles` values — let downstream consumers decide. The previously-discussed "verified handle" exception is deferred (OQ6) because author verification data is not in the classification prompt input."

**R9.** Post 8 (`Kimi-K2.7-Code lands as the #3 open model in the Code Arena: Frontend, #19 overall`) is a borderline case. The multi-value array prompt change may emit `post_types: ["performance_comparisons", "buzz_releases"]`; the verifier accepts either single or dual value as correct (Post 8 is borderline — the existing single-label classifier chose `performance_comparisons` only).

**R10.** The smoketest runner must render multi-discourse + multi-post_type correctly in the sample output (one line per discourse, one line per post_type, not collapsed to first).

**R11.** Hot-loop budget — measurement gate. Before merge, run `x-monitor smoketest --limit 50 --strict-budget` against a fresh DB; record `t_classify_ms` + `t_translate_ms` in the PR body. The new ceiling is `max(90s, 2× measured)`. The original Plan2 0.6 s/kept-post claim was based on a dev cycle, not the v10 12-post cycle (which was 5.49 s/post). This plan does NOT commit to the 90 s budget as a hard ceiling — it commits to a measurement gate and a re-derived ceiling.

**R12.** Fail-soft contract (carried from Plan2 R9): a single post's classification failure never aborts the cycle. The unsanctioned-flags writer is its own stage with its own fail-soft path.

**R13.** Selective backfill: a `x-monitor backfill unsanctioned-flags` subcommand re-classifies recent posts for the new flags only (not the whole 5,703-post history). Default: last 200 posts. The backfill extracts ONLY `unsanctioned_flags` from the LLM response — it does NOT overwrite `posts_brands_signals` or `posts_brands_discourse` (KTD8 clarification).

**R14.** Security hardening (per security-lens review):
- Parser hard-caps arrays to 6 entries (2× the prompt's stated max-3, defensive ceiling); excess is logged + dropped.
- `Store.upsert_unsanctioned_flags` caps `evidence` length at 1 KB, strips control chars, rejects URLs unless the dashboard renders them as plain text.
- `Store.get_unsanctioned_flags` returns `None` on parse failure (NOT `[]`) so the dashboard can distinguish "no flags row" from "row exists but corrupted" via `flag_get_status()`.

## Key Technical Decisions

**KTD1. Multi-value output uses arrays; `posts_brands_signals` PK rebuild is mandatory.** The LLM prompt emits `post_types: [str]` and `discourse_roles: [str]` per brand row. The parser maps each (brand_id, post_type) tuple to a `posts_brands_signals` row and each (brand_id, discourse_role) tuple to a `posts_brands_discourse` row. Migration 027b extends `posts_brands_signals.PRIMARY KEY` from `(post_id, brand_id)` to `(post_id, brand_id, post_type_key)` — this is a destructive migration (existing rows need to be re-inserted with their primary post_type, and any duplicate (post_id, brand_id, post_type_key) triples will conflict). Implementer MUST verify by reading migration 019 + the existing `posts_brands_signals` data before writing 027b. **Schema is forward-compatible for `posts_brands_discourse`** (composite PK `(post_id, brand_id, discourse_key, act_id)` per migration 026 — no migration needed).

**KTD2. `unsanctioned_flags` is per-post, not per-brand.** A post either has flags or doesn't — they're properties of the post, not the (post × brand) relationship. Single row in `posts_unsanctioned_flags` per post_id (PRIMARY KEY). The classifier prompt emits `unsanctioned_flags: [string]` at the JSON root (outside `classifications`). Parser persists once per post. Note: if a per-brand need surfaces (e.g., "this crypto scam is about GLM only, not Kimi"), the schema can be extended to `posts_unsanctioned_flag_keys(post_id, brand_id, flag_key)` without data loss — deferred.

**KTD3. `posts_unsanctioned_flags` uses JSON TEXT + generated column + index.** `flags` column is `TEXT NOT NULL` storing JSON array. A generated column `flag_set TEXT GENERATED ALWAYS AS (json_extract(flags, '$')) STORED` enables indexable lookups. Index: `CREATE INDEX idx_unsanctioned_flag_set ON posts_unsanctioned_flags(flag_set)`. Requires SQLite 3.31.0+ (March 2020 — current as of 2026). Implementer verifies version in migration apply; if older, falls back to a normalized junction table per the KTD3 fallback path.

**KTD4. `advertising-marketing` discourse tag is orthogonal to `post_type=advertising_marketing`.** A post can be `post_type=performance_comparisons, discourse_role=advertising-marketing` (e.g., a vendor's sponsored benchmark write-up). Conversely, a post can be `post_type=advertising_marketing, discourse_role=genuine_hype` (rare — see R8). The two dimensions stay orthogonal.

**KTD5. CTA+URL detection runs in the prompt, not pre-LLM.** We considered pre-LLM regex matching (URL + verb proximity) as a deterministic first pass to short-circuit `genuine_hype`. Rejected: too brittle (Chinese-language CTAs use different patterns; "限时免费体验" doesn't pair with `try` verb). The LLM classifier handles this with one new prompt rule (R8). The same rule applies in the translator's noop path — Post 5 should NOT echo the promotional Chinese text into `text_en` (already true if R6 fix lands).

**KTD6. Brand detection fix is split into investigate-then-fix.** U6a produces a written investigation report (`docs/investigations/2026-07-03-brand-detection-post4.md`) with: (i) the brand_keywords table contents for GLM/Opus rows, (ii) whether `compile_keyword_index` includes those patterns, (iii) whether `detect_brand_mentions` returns all matches or has a singleton fallback, (iv) whether the smoketest runner's `_load_latest_cycle_posts` collapses to `brand_ids[0]`. U6b applies the fix only after the report identifies the root cause. If the report finds no code bug (just seed-data missing), U6b is a YAML/seed edit, not a code change.

**KTD7. `discourse_role=advertising-marketing` uses a hyphen, not an underscore.** The brainstorm used the hyphenated form and renaming now would orphan downstream references. Document the convention in the migration comment. **Trade-off accepted:** inconsistency with the other 9 keys. Implementer adds a constant lookup `_ADVERTISING_MARKETING_DISC = "advertising-marketing"` in `attribution.py` so future code paths reference the constant instead of the literal.

**KTD8. Backfill extracts ONLY `unsanctioned_flags`, not full reclassification.** Per R13, the backfill CLI makes one LLM call per post via `classify_pragmatics_full` (reusing the existing function for consistency), then discards everything except `unsanctioned_flags` and writes only to `posts_unsanctioned_flags`. Existing `posts_brands_signals` and `posts_brands_discourse` rows are NOT overwritten. Trade-off: wasteful LLM cost on the dropped prongs (acceptable for `--limit 200`); alternative is a dedicated `classify_unsanctioned_flags_only(post)` with a minimal prompt (cheaper, deferred).

**KTD9. Hot-loop math: measurement gate, not asserted ceiling.** The original Plan2 0.6 s/kept-post claim is replaced by R11's measurement gate. The v10 smoketest (`/tmp/random10_smk_v10.md:269-280`) measured 65.9 s for 12 posts = 5.49 s/post (translate+classify combined); extrapolated to 200 posts = 1,098 s. This is the realistic per-post figure. Plan2's batched-call design (20-post batches × 10 calls) achieves much better throughput at scale, but the actual measurement hasn't been taken at 200 posts. R11 commits to the measurement, not the assertion.

## Implementation Units

### U1a. Migration 027a: new post_types + new discourse + unsanctioned_flags table

Mirror migration 026 + 019 for new lookup tables; add the unsanctioned_flags table per KTD3.

**Goal.** Persist the new taxonomy values and the unsanctioned-flags table.
**Files:**
- `x-monitoring/x_monitor/migrations/027a_taxonomy_and_unsanctioned.sql` (new)
- `scripts/build_schema_image.sh` runs after migration lands (project CLAUDE.md mandate)
**Approach.** Single SQL file with: 2 new `INSERT OR IGNORE INTO post_type_keys`, 4 new `post_type_labels` rows (en + zh_cn × 2 keys), 1 new `INSERT OR IGNORE INTO discourse_keys`, 2 new `discourse_labels` rows, and the `CREATE TABLE posts_unsanctioned_flags` with FK + JSON flags column + generated column + index. Header comment documents the SQLite 3.31.0+ requirement and the KTD3 fallback path. Wrap body in `BEGIN;` / `COMMIT;` per migration 026 convention. Do NOT manually insert into `_migrations` — `Store.apply_migrations` handles the ledger.
**Test scenarios:**
- Migration applies cleanly on a DB with migrations 001-026 applied.
- `SELECT key FROM post_type_keys WHERE key IN ('advertising_marketing', 'event_announcement')` returns 2 rows.
- `SELECT key FROM discourse_keys WHERE key = 'advertising-marketing'` returns 1 row (with hyphen).
- `INSERT INTO posts_unsanctioned_flags (post_id, flags) VALUES ('test-tweet', '["scam", "crypto"]')` succeeds; the generated column `flag_set` populates with the extracted JSON.
- `INSERT INTO posts_unsanctioned_flags (post_id, flags) VALUES ('test-tweet', '[]')` succeeds (empty flags = valid).
- `INSERT INTO posts_unsanctioned_flags (post_id, flags) VALUES ('nonexistent', '[]')` fails with FK violation (assumes `PRAGMA foreign_keys = ON`).
- The `idx_unsanctioned_flag_set` index exists and `EXPLAIN QUERY PLAN SELECT * FROM posts_unsanctioned_flags WHERE flag_set = '["scam"]'` reports index use.
**Verification.** `x-monitor migrate status` shows 027a applied; `sqlite3 data/x_monitoring.db ".indexes posts_unsanctioned_flags"` lists the index.

### U1b. Migration 027b: extend posts_brands_signals PK

The critical blocker for multi-post_type support.

**Goal.** Allow N `post_type` values per (post × brand).
**Files:**
- `x-monitoring/x_monitor/migrations/027b_posts_brands_signals_multi_post_type.sql` (new)
**Approach.** SQLite supports PK extension via `ALTER TABLE` only for compatible changes. The current PK is `(post_id, brand_id)` and the change is to extend with `post_type_key`. SQLite requires a table rebuild for this kind of PK change. Pattern:
1. Create new table `posts_brands_signals_new` with `PRIMARY KEY (post_id, brand_id, post_type_key)` and the same columns.
2. `INSERT INTO posts_brands_signals_new SELECT post_id, brand_id, post_type, sentiment, ... FROM posts_brands_signals;` — preserves existing rows.
3. `DROP TABLE posts_brands_signals; ALTER TABLE posts_brands_signals_new RENAME TO posts_brands_signals;`
4. Recreate indexes.
**Pre-condition.** U6a (brand detection investigation) runs first to confirm Post 4's brand_ids list — this determines whether the migration needs to handle the (post_id, brand_id) row that previously only had `moonshot_kimi` (the migration preserves the existing row; downstream U2's parser writes the additional `(moonshot_kimi, glm, post_type)` rows on next cycle).

**Critical safety check (implementer must do):** Before running, count duplicate (post_id, brand_id) pairs in existing data:
```sql
SELECT post_id, brand_id, COUNT(*) c FROM posts_brands_signals GROUP BY post_id, brand_id HAVING c > 1;
```
If non-zero, the migration's INSERT step will fail with UNIQUE constraint on the NEW pk? No — the NEW pk includes post_type_key, so duplicates with DIFFERENT post_types are preserved, duplicates with SAME post_type are rejected. Implementer reports the count and resolves any duplicates before proceeding.

**Test scenarios:**
- Migration applies cleanly on a DB with migrations 001-027a applied.
- `PRAGMA table_info(posts_brands_signals)` shows `post_type_key` is part of PK (NOT NULL, no default).
- `INSERT INTO posts_brands_signals (post_id, brand_id, post_type_key) VALUES ('test-post', 'test-brand', 'performance_comparisons')` then `INSERT ... ('test-post', 'test-brand', 'feedback_questions')` succeeds (2 rows for the same post × brand).
- `INSERT ... ('test-post', 'test-brand', 'performance_comparisons')` again (duplicate) succeeds via `ON CONFLICT DO UPDATE` (idempotent).
- Rollback: `migrations rollback 027b` restores the original `(post_id, brand_id)` PK.
**Verification.** `x-monitor migrate status` shows 027b applied; `sqlite3 data/x_monitoring.db ".schema posts_brands_signals"` shows the new composite PK.

### U2a. Extend _VALID_* enum sets + parse top-level unsanctioned_flags

Two focused changes: enum extension + parser top-level field extraction.

**Goal.** The classifier accepts the new taxonomy values and parses `unsanctioned_flags` at the JSON root.
**Files:**
- `x-monitoring/x_monitor/attribution.py` (lines 997-1010 for enum extensions; lines 1076-1119 for parser reshape)
**Approach.** Two changes:
1. Extend `_VALID_POST_TYPES` (line 1005) with `advertising_marketing`, `event_announcement`. Extend `_VALID_DISCOURSE` (line 997) with `"advertising-marketing"` (hyphen).
2. Modify `_parse_pragmatics_full_response` to also read top-level `unsanctioned_flags: []` and return it alongside the per-brand dict. New return shape: `{"by_brand": dict[str, dict], "unsanctioned_flags": list[str]}`. Update `classify_pragmatics_full` (line 1122) to return the same tuple. The caller (`_run_post_fetch` in `run.py`) extracts `unsanctioned_flags` and calls `Store.upsert_unsanctioned_flags(post_id, flags, evidence)`.
**Test scenarios:**
- An LLM response with `classifications: [...]` and `unsanctioned_flags: ["scam", "crypto"]` parses to `{"by_brand": {...}, "unsanctioned_flags": ["scam", "crypto"]}`.
- An LLM response with no `unsanctioned_flags` key returns `{"unsanctioned_flags": []}` (default empty).
- An LLM response with `unsanctioned_flags: ["unknown_flag"]` filters the unknown value out (KTD2 says valid values are `marketing_spam | scam | crypto | unauthorized`).
**Verification.** `tests/test_classify_pragmatics_full.py` updated with the new return shape.

### U2b. Reshape parser: scalar → array for post_types and discourse_roles

The second half of the parser change — output shape changes from scalar fields to arrays.

**Goal.** Parser accepts `post_types: [str]` and `discourse_roles: [str]` per brand row; emits N `posts_brands_signals` rows + N `posts_brands_discourse` rows per (post × brand).
**Files:**
- `x-monitoring/x_monitor/attribution.py` (lines 1076-1119)
- `x-monitoring/x_monitor/store.py` (new method `bulk_insert_post_brand_signals` mirroring `bulk_insert_post_brand_discourse`)
**Approach.** Three changes:
1. `_parse_pragmatics_full_response` reads `item.get("post_types", [])` (array) and `item.get("discourse_roles", [])` (array). Defaults: `["hands_on_usage"]` for missing/invalid post_types, `["uncategorized"]` for missing/invalid discourse_roles.
2. Each `(brand_id, post_type)` pair becomes one row in `posts_brands_signals`. Each `(brand_id, discourse_role)` pair becomes one row in `posts_brands_discourse` (with `act_id` auto-assigned as the row's index in the array).
3. **Security: hard-cap arrays at 6 entries** (2× the prompt's stated max-3, defensive ceiling). Excess entries are logged and dropped.
4. New `Store.bulk_insert_post_brand_signals(rows: list[dict])` mirrors `bulk_insert_post_brand_discourse` (lines 1566-1729) but writes to `posts_brands_signals` with the new composite PK.

**Test scenarios:**
- An LLM response with `post_types: ["performance_comparisons", "feedback_questions"]` for brand `glm` produces 2 `posts_brands_signals` rows: `(post_id, glm, performance_comparisons)` and `(post_id, glm, feedback_questions)`.
- An LLM response with `discourse_roles: ["genuine_hype", "advertising-marketing"]` produces 2 `posts_brands_discourse` rows: `(post_id, glm, genuine_hype, act_id=1)` and `(post_id, glm, advertising-marketing, act_id=2)`.
- An LLM response with `post_types` containing 100 entries persists 6 rows (security cap) and logs a warning.
- An LLM response with `discourse_roles: ["unknown_tag"]` coerces to `["uncategorized"]`.
**Verification.** `tests/test_classify_pragmatics_full_arrays.py` (new) covers the array reshape + security cap.

### U3a. Prompt rewrite: new taxonomy + array output contract

Replace the prompt's enum lists + the per-brand scalar→array shape change.

**Goal.** LLM is instructed to emit arrays and the new taxonomy values.
**Files:**
- `x-monitoring/x_monitor/attribution.py` (lines 1012-1073 — `build_pragmatics_full_prompt`)
- `x-monitoring/x_monitor/data/few_shot_pragmatics.jsonl` (add 1-2 adv/mktg examples)
**Approach.** Four changes:
1. Change `post_type (4 buckets ...)` block to list 6 keys (4 existing + `advertising_marketing` + `event_announcement`).
2. Change `discourse_role (9 keys ...)` block to list 10 keys (9 existing + `advertising-marketing`).
3. Change `RETURN ONE ROW FOR EVERY BRAND LISTED` rule to: "Return `post_types: [str]` and `discourse_roles: [str]` arrays per row. Most posts have exactly 1 of each. Multi-value is allowed when a post legitimately has more than one (e.g., a benchmark write-up that is also a `performance_comparisons` AND `feedback_questions`). Maximum 3 of each per brand."
4. Add few-shot examples (1-2) covering `advertising-marketing` discourse + `advertising_marketing` post_type. Pulled from the brainstorm's literal X examples (lines 23-49 of the brainstorm doc).

**Test scenarios:**
- `build_pragmatics_full_prompt("text", ["glm"])` output contains the strings `"advertising_marketing"`, `"event_announcement"`, `"advertising-marketing"`, and the phrase "Maximum 3 of each per brand".
- Few-shot JSONL file contains at least 1 example with `discourse_role: "advertising-marketing"`.
**Verification.** `tests/test_classify_pragmatics_full_prompt.py` asserts the prompt string contains the new keys.

### U3b. Prompt rewrite: CTA rule + unsanctioned-flags top-level field

Add the CTA-precludes-genuine_hype rule and the unsanctioned_flags top-level instruction.

**Goal.** LLM knows the CTA rule and the unsanctioned-flags output shape.
**Files:**
- `x-monitoring/x_monitor/attribution.py` (lines 1012-1073)
**Approach.** Two changes:
1. Add to the Rules block: "**7. genuine_hype is incompatible with explicit call-to-action.** If the post contains a CTA (URL + verb like 'try', 'sign up', 'join', 'get', 'limited-time', 'free access', 限时免费, 立即体验, 注册, 点击), discount offer, or wrapper/promo language ('one API key', 'OpenAI-compatible gateway', 'free credit no card'), prefer `discourse_role=advertising-marketing` over `genuine_hype`. If both genuine praise AND a CTA coexist, emit BOTH `discourse_roles` values — let downstream consumers decide."
2. Add at JSON root level: "Also emit `unsanctioned_flags: [str]` at the JSON root (outside `classifications`). Allowed values: `marketing_spam | scam | crypto | unauthorized`. Empty array if none apply. Use this for promotional/crypto/scam/unauthorized brand use that the post_type and discourse_role taxonomies don't fully capture."

**Test scenarios:**
- The prompt contains the substring "genuine_hype is incompatible with explicit call-to-action".
- The prompt contains the phrase "unsanctioned_flags: [str]" and the list "marketing_spam | scam | crypto | unauthorized".
**Verification.** `tests/test_classify_pragmatics_full_prompt.py` extended.

### U4. Store methods: upsert_unsanctioned_flags + bulk_insert_post_brand_signals

Two new Store methods (one for unsanctioned flags, one for the new signals insert path).

**Goal.** Persist unsanctioned flags + multi-post_type signals idempotently.
**Files:**
- `x-monitoring/x_monitor/store.py` (~80 lines total)
**Approach.** Two methods:
1. **`Store.upsert_unsanctioned_flags(post_id, flags, evidence=None)`:** SQL `INSERT ... ON CONFLICT(post_id) DO UPDATE SET flags=excluded.flags, evidence=excluded.evidence, decided_at=excluded.decided_at`. JSON-serialize flags. **Security (R14):** cap `evidence` length at 1 KB; strip `\x00` and C0 controls except `\t\n\r`; reject if evidence contains `http(s)://` (URLs in evidence are an XSS / open-redirect risk on dashboard rendering). Companion `Store.get_unsanctioned_flags(post_id)` returns `list[str] | None` — `None` for missing row, `[]` only if the row exists but flags is empty array. Companion `Store.flag_get_status(post_id) -> 'missing'|'ok'|'corrupt'` — returns 'corrupt' if `flags` column fails JSON parse (so dashboard can distinguish from missing).
2. **`Store.bulk_insert_post_brand_signals(rows)`:** mirrors `bulk_insert_post_brand_discourse` (store.py lines 1566-1729). SQL uses `ON CONFLICT(post_id, brand_id, post_type_key) DO UPDATE SET sentiment=excluded.sentiment`. Validates each row's `post_type_key` against `_known_post_type_keys()` and `brand_id` against the registry.

**Test scenarios:**
- Insert new post_id: row created with current timestamp; `flag_get_status` returns 'ok'.
- Re-insert same post_id with different flags: row updated; `get_unsanctioned_flags` returns new flags.
- `upsert_unsanctioned_flags(pid, flags, evidence='x' * 2000)` raises `ValueError` (length cap).
- `upsert_unsanctioned_flags(pid, flags, evidence='see https://evil.com')` raises `ValueError` (URL rejection).
- `bulk_insert_post_brand_signals` with N rows of mixed post_types writes N rows; second call with same PKs is idempotent.
**Verification.** `tests/test_store_unsanctioned_flags.py` + `tests/test_store_post_brand_signals_arrays.py` (new).

### U5. Fix text_en echo bug + translator prompt update

Two changes: symmetric noop rule + system prompt update.

**Goal.** Posts with `lang_detected=zh_cn` (or `zh-Hans` family) do NOT echo Chinese characters into `text_en`.
**Files:**
- `x-monitoring/x_monitor/translator.py` (lines 631-638 for noop rule; lines 351-415 for system prompt)
**Approach.** Two changes:
1. **Server-side noop rule (lines 631-638):** Add symmetric noop — when `_is_simplified_chinese_family(lang)` is True, set `text_en = None` in addition to the existing `text_zh_cn = None`. The existing logic at line 638 already NULLs `text_zh_cn`; we add the line `text_en = None if is_already_zh else judged.get("text_en")` symmetric to the English noop.
2. **System prompt (lines 351-415):** Update `_PRAGMATICS_SYSTEM_PROMPT` to add: "When the source tweet is already in English, set `text_en` to null. When the source tweet is already in Simplified Chinese, set `text_zh_cn` to null. Never echo the source into the locale column that matches the source."

**Test scenarios:**
- A post with `lang_detected="zh_cn"` and `text="GLM 5.2 真棒"` and LLM-responded `text_en="GLM 5.2 真棒"` (echo) gets `text_en=None` after the noop rule fires.
- A post with `lang_detected="en"` and `text="GLM 5.2 is great"` still gets `text_en=None` and `text_zh_cn="GLM 5.2 真棒"` (existing behavior preserved).
- A post with `lang_detected="ja"` (Japanese, neither family) keeps both `text_en` and `text_zh_cn` populated.
- A post with `lang_detected="zh-Hant"` (Traditional Chinese) keeps both populated (does NOT match Simplified Chinese family).
**Verification.** `tests/test_translator_pragmatics.py` extended with the symmetric noop tests.

### U6a. Investigate brand detection root cause for Post 4

Read-only investigation; produces a written report.

**Goal.** Identify the root cause of Post 4's single-brand attribution (only `moonshot_kimi` instead of `[glm, moonshot_kimi, opus/claude]`).
**Files:**
- `docs/investigations/2026-07-03-brand-detection-post4.md` (new)
**Approach.** Three diagnostic steps + concrete SQL commands:
1. **Seed check:** `sqlite3 data/x_monitoring.db "SELECT brand_id, pattern, is_regex FROM brand_keywords WHERE pattern LIKE '%glm%' OR pattern LIKE '%GLM%' OR pattern LIKE '%opus%' OR pattern LIKE '%Opus%' OR pattern LIKE '%claude%' OR pattern LIKE '%Claude%' OR pattern LIKE '%moonshot%';"` — verify the GLM and Opus patterns exist.
2. **Compile check:** Read `compile_keyword_index` output for the GLM brand — run `python -c "from x_monitor.attribution import compile_keyword_index; from x_monitor.store import Store; store = Store('data/x_monitoring.db'); idx = compile_keyword_index(store.read_brand_keywords()); print([b for b in idx[1].values()])"` and verify `glm` and `claude` (or equivalent Opus brand) are in the token-to-brand map.
3. **Detection check:** Run `python -c "from x_monitor.attribution import compile_keyword_index, detect_brand_mentions; ...; print(detect_brand_mentions(post4_text, idx))"` with Post 4's text and verify it returns `[glm, moonshot_kimi, claude]` (or equivalent).
4. **Runner check:** Read `_load_latest_cycle_posts` in `scripts/post_fetch_smoketest.py` line 118 — verify it does NOT collapse to `brand_ids[0]`.
The investigation report documents which step surfaces the bug (and which doesn't).

**Test scenarios:**
- Each diagnostic step produces a concrete result captured in the investigation report.
- Report concludes with one of: (a) code bug found at step 2/3/4, (b) seed-data missing for step 1, (c) no bug found (then Post 4 is a transient misclassification).
**Verification.** The investigation report is committed to `docs/investigations/`. U6b is blocked on this report.

### U6b. Fix brand detection for multi-brand Chinese-only posts

Apply the fix only after U6a's root-cause report.

**Goal.** Post 4 returns `brand_ids = ["glm", "moonshot_kimi", "claude"]` (or equivalent).
**Files:** Determined by U6a's root cause. Likely candidates:
- `x-monitoring/x_monitor/attribution.py` (lines 376-504 — `compile_keyword_index` or `detect_brand_mentions`)
- `x-monitoring/data/filters/glm.yaml` (if seed missing)
- `x-monitoring/scripts/post_fetch_smoketest.py` (if singleton fallback)
**Approach.** Targeted fix based on U6a findings. Most likely fix per the repo-research-analyst's report: extend `compile_keyword_index` with CJK-aware normalization OR add brand_patterns to the yaml tables. Includes a negative-match test (a post with 0 brand tokens returns `[]`, not the false-positive set).

**Test scenarios:**
- A Chinese-only post "GLM 5.2 vs Kimi k2.7" with brand registry containing glm + moonshot_kimi returns `brand_ids = ["glm", "moonshot_kimi"]`.
- A post with "Claude Opus 4.8" returns `brand_ids = ["claude"]`.
- A post with zero brand-mentioning tokens returns `brand_ids = []` (not false positives).
**Verification.** Re-run v11 smoketest on Post 4; verify brand row count.

### U7. Update smoketest runner for multi-discourse + unsanctioned flags output

Update `_render_sample_posts` and the report counters.

**Goal.** Smoketest output shows N lines per brand (one per post_type, one per discourse) and reports `n_unsanctioned`.
**Files:**
- `x-monitoring/scripts/post_fetch_smoketest.py` (lines 145-177 for sample renderer; lines 303-345 for counters)
**Approach.** Three changes:
1. **Sample renderer:** Render N lines per brand where N = max(len(post_types), len(discourse_roles), 1). Use `itertools.zip_longest` for clarity.
2. **Counters:** Add `n_unsanctioned` (count of posts with non-empty unsanctioned flags) and `n_multi_discourse` (count of (post × brand) rows where discourse_roles has > 1 entry).
3. **Output section:** Add `=== UNSANCTIONED FLAGS ===` listing the flagged post_ids and their flags.

**Test scenarios:**
- A 5-post fixture where 1 post has `unsanctioned_flags=["scam", "crypto"]` and 1 has `discourse_roles=["genuine_hype", "advertising-marketing"]`: smoketest output shows `n_unsanctioned=1` and `n_multi_discourse=1`.
**Verification.** Re-run v11 smoketest against the same 12 random posts; verify Post 4 gets correct brands, Post 5 gets `advertising-marketing`, Post 7 gets `unsanctioned_flags` reported.

### U8a. Wire unsanctioned-flags stage into _run_post_fetch

The pipeline integration half of U8.

**Goal.** Every cycle persists unsanctioned flags for new posts.
**Files:**
- `x-monitoring/x_monitor/run.py` (the `_run_post_fetch` helper added in Plan2 U5)
**Approach.** After `classify_pragmatics_full` returns, iterate the per-post `unsanctioned_flags` and call `Store.upsert_unsanctioned_flags(post_id, flags, evidence)`. Failures are caught and logged; cycle continues. Add `n_unsanctioned` AND `phase_timings_sec["unsanctioned"]` to the cycle summary (per VC#8 fix from coherence review).

**Test scenarios:**
- A cycle with 50 kept posts, 5 of which the LLM flags with `["marketing_spam"]` and 2 with `["scam", "crypto"]`: cycle completes in < measurement-gate ceiling; 7 rows are in `posts_unsanctioned_flags` after the cycle; cycle summary reports `n_unsanctioned=7` AND `phase_timings_sec["unsanctioned"]` has a timing record.
**Verification.** Run a full cycle against the live DB; verify both the count and the timing record.

### U8b. New backfill CLI: x-monitor backfill unsanctioned-flags

The CLI half of U8.

**Goal.** Selective backfill of recent posts for `unsanctioned_flags` only.
**Files:**
- `x-monitoring/x_monitor/__main__.py` (new `cmd_backfill_unsanctioned_flags` + parser entry)
- `x-monitoring/x_monitor/store.py` (new `Store.recent_posts_unsanctioned_missing(limit) -> list[dict]` helper)
**Approach.** `cmd_backfill_unsanctioned_flags(args, paths)`:
- Flags: `--limit 200` (default), `--dry-run`, `--yes` (required when `--limit > 500`, per F9 security finding — prevents accidental reclassification of large history).
- Internals: `Store.recent_posts_unsanctioned_missing(args.limit)` → for each post, call `classify_pragmatics_full(post, ...)` → extract `unsanctioned_flags` from response → `Store.upsert_unsanctioned_flags(post_id, flags, evidence)`. Discard everything else from the LLM response (per KTD8).
- Rate limit: 200ms sleep between LLM calls (per F9).

**Test scenarios:**
- `x-monitor backfill unsanctioned-flags --limit 200 --dry-run` reports the post_ids that would be classified without writing.
- `x-monitor backfill unsanctioned-flags --limit 500` requires `--yes` flag (else errors with usage hint).
- `x-monitor backfill unsanctioned-flags --limit 50` writes 50 rows in < measurement-gate ceiling.
**Verification.** Backfill on the live DB; verify rows written match the LLM output.

## High-Level Technical Design

### Per-post data flow (extended from Plan2 §6.2)

```
kept_tweet
   │
   ├──> classify_pragmatics_full (one call per 20-post batch)
   │      │
   │      ├──> posts_brands_signals  (NEW: N rows per brand, one per post_type)
   │      ├──> posts_brands_discourse (NEW: N rows per brand, one per discourse_role)
   │      ├──> posts_unsanctioned_flags (NEW: 0 or 1 row per post with flags)
   │      └──> phase_timings_sec["classify"] += elapsed
   │
   ├──> translate_batch_pragmatics (one call per 20-post batch)
   │      │
   │      ├──> posts.text_en         (NEW: NULL'd when lang_detected is in zh_cn family)
   │      ├──> posts.text_zh_cn
   │      ├──> posts.lang_detected
   │      └──> phase_timings_sec["translate"] += elapsed
   │
   ├──> [unsanctioned flags write, per post]
   │      └──> phase_timings_sec["unsanctioned"] += elapsed
   │
   └──> [failures: rows marked translation_failed, classification errors logged]
```

### LLM output contract (extended from Plan2 §5.1)

```json
{
  "classifications": [
    {
      "brand_id": "glm",
      "post_types": ["performance_comparisons", "feedback_questions"],
      "sentiment": "neutral",
      "discourse_roles": ["self_deprecation"],
      "china_nationalism": "mild_pro",
      "us_nationalism": "none"
    }
  ],
  "unsanctioned_flags": []
}
```

For Post 7 (crypto scam):

```json
{
  "classifications": [
    {"brand_id": "glm", "post_types": ["advertising_marketing"], "sentiment": "positive",
     "discourse_roles": ["advertising-marketing"], "china_nationalism": "none", "us_nationalism": "none"}
  ],
  "unsanctioned_flags": ["marketing_spam", "crypto", "unauthorized"]
}
```

### Storage shape (new tables)

```
posts_unsanctioned_flags (
  post_id     TEXT PRIMARY KEY,
  flags       TEXT NOT NULL,                              -- JSON array e.g. '["scam","crypto"]'
  flag_set    TEXT GENERATED ALWAYS AS (json_extract(flags, '$')) STORED,  -- indexable lookup
  evidence    TEXT,                                       -- sanitized, max 1 KB, no URLs
  decided_at  TEXT NOT NULL,                              -- ISO timestamp
  FOREIGN KEY (post_id) REFERENCES posts(tweet_id) ON DELETE CASCADE
)
CREATE INDEX idx_unsanctioned_flag_set ON posts_unsanctioned_flags(flag_set);

posts_brands_signals (NEW PK from migration 027b):
  post_id            TEXT NOT NULL,
  brand_id           TEXT NOT NULL,
  post_type_key      TEXT NOT NULL,  -- NEW: now part of PK
  sentiment          TEXT,
  PRIMARY KEY (post_id, brand_id, post_type_key),
  FOREIGN KEY (post_type_key) REFERENCES post_type_keys(key),
  ...
)
```

## Verification Contract

The plan is "done" when each of these is true:

1. **Migration 027a applies cleanly** (`x-monitor migrate status` shows 027a applied; new tables and lookup rows present).
2. **Migration 027b applies cleanly** (`x-monitor migrate status` shows 027b applied; `posts_brands_signals` PK is `(post_id, brand_id, post_type_key)`).
3. **Multi-value outputs round-trip.** A fixture with "GLM 5.2 vs Kimi K2.7, am I running behind?" returns `post_types: ["performance_comparisons", "feedback_questions"]` and persists 2 `posts_brands_signals` rows for the GLM brand (requires U1b + U2b + U3a).
4. **CTA rule fires.** A fixture with "GLM 5.2 is amazing — try it free at https://example.com" returns `discourse_roles: ["advertising-marketing"]`, NOT `["genuine_hype"]` (requires U3b + U2b).
5. **`unsanctioned_flags` persist.** A Post-7-style crypto scam post gets `unsanctioned_flags: ["marketing_spam", "crypto", "unauthorized"]` and a `posts_unsanctioned_flags` row is written (requires U2a + U3b + U4 + U8a).
6. **`text_en` echo bug fixed.** A post with `lang_detected="zh_cn"` and LLM-responded `text_en="GLM 5.2 真棒"` (echo) gets `text_en=None` after the noop rule (requires U5).
7. **Brand detection fixed.** Post 4 in v11 smoketest returns `brand_ids = ["glm", "moonshot_kimi"]` or `["glm", "moonshot_kimi", "claude"]` (requires U6a + U6b).
8. **Smoketest v11 output** shows: Post 5 with `discourse=advertising-marketing`, Post 7 with `unsanctioned_flags: ["marketing_spam", "crypto"]` listed in the new section, Post 8 with at least `performance_comparisons` (dual with `buzz_releases` accepted but not required).
9. **Measurement gate passes.** Run `x-monitor smoketest --limit 50 --strict-budget` against a fresh DB; record `t_classify_ms` + `t_translate_ms` + `t_total_ms` in the PR body. New ceiling is `max(90s, 2× measured)` (requires U7 + the smoketest runner).
10. **`phase_timings_sec["unsanctioned"]` recorded.** Cycle summary includes the unsanctioned-flags timing (requires U8a).
11. **Backfill CLI works.** `x-monitor backfill unsanctioned-flags --limit 50` writes 50 rows; `--limit > 500` requires `--yes` flag (requires U8b).
12. **All existing Plan2 tests pass.** Plan2's 78+ test surface continues to pass after fixture updates for `post_types` array shape and `_parse_pragmatics_full_response` return shape.

## Definition of Done

- [ ] U1a migration `027a_taxonomy_and_unsanctioned.sql` applies cleanly; rollback restores pre-migration schema.
- [ ] U1b migration `027b_posts_brands_signals_multi_post_type.sql` applies cleanly; pre-flight duplicate check ran; rollback restores pre-migration schema.
- [ ] U2a `_VALID_*` enums extended; `_parse_pragmatics_full_response` returns `{"by_brand": ..., "unsanctioned_flags": ...}`.
- [ ] U2b parser reshaped to arrays; `bulk_insert_post_brand_signals` implemented; security cap at 6 enforced.
- [ ] U3a prompt builder updated for new taxonomy + array instructions; few-shot examples augmented.
- [ ] U3b prompt builder updated for CTA rule + unsanctioned-flags top-level field.
- [ ] U4 `Store.upsert_unsanctioned_flags` + `Store.get_unsanctioned_flags` + `Store.flag_get_status` + `Store.bulk_insert_post_brand_signals` implemented + tested with security caps.
- [ ] U5 `text_en` echo bug fixed; symmetric noop for Simplified Chinese family; system prompt updated.
- [ ] U6a investigation report written; root cause identified.
- [ ] U6b brand detection fix applied + tested; negative-match test (0 brand tokens → `[]`) passes.
- [ ] U7 smoketest runner renders multi-discourse + unsanctioned flags section.
- [ ] U8a `_run_post_fetch` writes unsanctioned flags; cycle summary includes `n_unsanctioned` AND `phase_timings_sec["unsanctioned"]`.
- [ ] U8b `x-monitor backfill unsanctioned-flags` CLI shipped; `--yes` flag required for `--limit > 500`.
- [ ] Smoketest v11 against the same 12 random posts shows Post 4, 5, 7, 8 corrected.
- [ ] Measurement gate run; `t_classify_ms` + `t_translate_ms` + `t_total_ms` recorded in PR body.
- [ ] All existing Plan2 tests pass after fixture updates.
- [ ] `docs/post_fetch_architecture.md` updated for the new dimension.
- [ ] Schema image regenerated via `scripts/build_schema_image.sh` if `.dot` changes.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| U1b migration fails on existing data with duplicate (post_id, brand_id) pairs | Low | High | U1b mandates pre-flight duplicate check; resolution procedure in U1b approach. |
| LLM emits empty arrays more often (over-cautious) | Medium | Medium | Prompt explicitly says "Most posts have exactly 1" + max-3 ceiling; parser falls back to `["hands_on_usage"]` / `["uncategorized"]` if arrays are empty. |
| CTA rule over-triggers — LLM treats "official docs link" as a CTA | Medium | Medium | R8 explicit dual-tag rule; few-shot example demonstrates the dual-tag case. **Verified-handle exception deferred to OQ6** (out of scope for v1). |
| LLM prompt-injection echo into `evidence` | Low | Medium | U4 sanitization (1 KB cap, control char strip, URL rejection); evidence stored as TEXT not rendered HTML. |
| `posts_unsanctioned_flags` JSON-as-TEXT requires SQLite 3.31.0+ | Low | Low | U1a migration header verifies version; KTD3 fallback to junction table documented. |
| U6a investigation reveals no code bug (transient misclassification) | Low | Low | U6b becomes a no-op with a written explanation; Post 4 in v11 may still be single-brand. |
| Hot-loop budget breach | High | Medium | R11 measurement gate replaces asserted ceiling; actual measurement commits before merge. |
| Array security cap (6) truncates legitimate multi-value posts | Low | Low | Max-3 in prompt + 2× defensive ceiling = 6; legitimate multi-value posts are rare. |
| Backfill CLI accidentally reclassifies large history | Low | Medium | `--yes` flag required for `--limit > 500`; 200ms rate limit; default `--limit 200`. |
| Schema-image regen needed for new migration | Low | Low | U1a includes running `scripts/build_schema_image.sh --check` post-merge; follow the project CLAUDE.md mandate. |

## Open Questions

**OQ6. Should the CTA exception handle "verified handle" or "brand's own official URL"?** Per feasibility F3, neither is implementable without adding author verification data + a `brands.official_url` column to the classification prompt input. Defer to v2. Implementation path: extend `classify_pragmatics_full` signature with `author_verified: bool` + `brand_official_urls: dict[str, str]` and update the prompt to check these. Recommended for a follow-up plan.

**OQ7. Should the unsanctioned-flags table be per-post or per-brand?** Per KTD2 we ship per-post. If a per-brand need surfaces (e.g., "this crypto scam is about GLM only, not Kimi"), the schema can extend to `posts_unsanctioned_flag_keys(post_id, brand_id, flag_key)` without data loss — defer until needed.

**OQ8. Should the backfill use a dedicated `classify_unsanctioned_flags_only(post)` minimal prompt instead of full `classify_pragmatics_full`?** Per KTD8, full call (discarding prongs) ships in v1 for consistency. A dedicated minimal prompt saves LLM cost. Defer to v2.

## Scope Boundaries

### In Scope

- U1a migration for 2 new post_types + 1 new discourse + `posts_unsanctioned_flags` table.
- U1b migration to extend `posts_brands_signals` PK.
- U2a enum extension + top-level unsanctioned_flags parsing.
- U2b parser reshape for multi-value outputs + security cap.
- U3a prompt rewrite for new taxonomy + array instructions.
- U3b prompt rewrite for CTA rule + unsanctioned-flags prompt block.
- U4 Store methods for unsanctioned flags + multi-post_type signals.
- U5 `text_en` echo bug fix (symmetric noop + system prompt).
- U6a brand detection investigation.
- U6b brand detection fix (root-cause-driven).
- U7 smoketest runner updates for multi-discourse + unsanctioned flags output.
- U8a unsanctioned-flags pipeline integration + `phase_timings_sec` recording.
- U8b unsanctioned-flags backfill CLI.

### Deferred to Follow-Up Work

- Full-history backfill of the 5,703 existing posts through the new prompt (R13 covers selective backfill only).
- Verified-handle CTA exception (OQ6).
- Per-brand unsanctioned flags (OQ7).
- Minimal-prompt backfill for cost savings (OQ8).
- Per-axis `discourse_labels` split (Plan2 KTD4).
- `posts_brands_discourse.annotation` column (Plan2 OQ4).
- Register field for translation audience framing (Plan2 OQ5 — translator's voice-picker).
- 套壳 / 蒸馏 slur detection for the brand filter (orthogonal).

### Outside this product's identity

- Hard-dropping scam/crypto posts at ingestion time. They remain valuable signal for brand protection; the dashboard gets a filter.
- Numerical sentiment scoring (stays 4-value ordinal).
- Non-X platform classifiers (Weibo, Zhihu).
- Automatic takedown / account reporting based on `unsanctioned_flags`. Brand-protection triage is human-reviewed; auto-action is out of scope.
- LLM provider changes / cost optimization for the wider prompt (R11 measurement gate observes cost; provider changes deferred).
- Multi-platform discourse vocabulary (a `discourse_labels_zh_tw` or similar).
- Dashboard UI changes for filtering by `unsanctioned_flags`. The dashboard consumes the new tables directly via existing Store methods; UI refresh is downstream of this plan.

## Supersession Note

The plan at `docs/plans/2026-07-03-120000-taxonomy-extension-for-promotional-crypto-posts-plan.md` (requirements-only, brainstorm-sourced) is **superseded** by this plan. The 120000 plan covers only the taxonomy extension (R1-R2 in this plan); this plan widens scope to include multi-discourse (R4), multi-post_type (R5), the unsanctioned flags table (R3), and the v10 bug fixes (R6-R9). All product decisions from the 120000 plan (the underlying intent of covering promo + crypto) are preserved here, but **five named keys are intentionally substituted** with different names per the brainstorm + user scoping decisions:

| 120000 brainstorm key | This plan's substitution | Why |
|---|---|---|
| `promotional_spam` (post_type) | `advertising_marketing` (post_type) | The brainstorm at `docs/brainstorms/2026-07-03-140809-...md:104-105` uses the broader "catch-all for any advertising and marketing with call to action" framing, which fits the post_type better than the narrower `promotional_spam`. |
| `crypto_scam` (post_type) | `unsanctioned_flags[crypto]` + `unsanctioned_flags[scam]` (top-level flags) | Crypto is a property of the post's *relationship* to the brand, not a post category — the dashboard filter wants `crypto=TRUE` as a boolean, not a post_type bucket. |
| `promotional` (discourse_role) | `advertising-marketing` (discourse_role) | The brainstorm uses the hyphenated form (and explicitly says "To go along with the new post_type `advertising_marketing`"). |
| `brand_jacking` (discourse_role) | `unsanctioned_flags[unauthorized]` (top-level flag) | Same as above — brand-jacking is a relationship property, not a discourse register. |
| `scam_hijack` (discourse_role) | `unsanctioned_flags[scam]` (top-level flag) | Same. |

The 120000 file remains in `docs/plans/` as a brainstorm record but is no longer canonical for execution. Discovery should route to this plan (2026-07-03-003).

## References

- v10 smoketest output: `/tmp/random10_smk_v10.md` (12 random posts classified; 5 issues surfaced).
- Brainstorm: `docs/brainstorms/2026-07-03-140809-brainstorm-adv-mktg-scam-crypto-x-posts.md` (research via X API on 2026-07-03).
- Prior brainstorm (superseded): `docs/plans/2026-07-03-120000-taxonomy-extension-for-promotional-crypto-posts-plan.md`.
- Plan2: `docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md` — provides the schema (migration 026), the classifier (`classify_pragmatics_full`), the translator (`translate_batch_pragmatics`), and the smoketest runner (`scripts/post_fetch_smoketest.py`).
- Migration 026 (shipped): `x-monitoring/x_monitor/migrations/026_pragmatics_axes.sql` — pattern to mirror for new lookup tables.
- Migration 019 (shipped): `x-monitoring/x_monitor/migrations/019_post_types_and_sentiments.sql` — pattern reference for `post_type_keys` + `post_type_labels`.
- `x-monitoring/x_monitor/attribution.py` — `build_pragmatics_full_prompt` (rewrite in U3), `_parse_pragmatics_full_response` (reshape in U2), `_VALID_*` enums (extend in U2a), `classify_pragmatics_full` (return shape change in U2a), `compile_keyword_index` + `detect_brand_mentions` (investigate in U6a).
- `x-monitoring/x_monitor/translator.py:631-638` — current noop rule to make symmetric in U5.
- `x-monitoring/x_monitor/store.py` — `_known_post_type_keys` + `_known_discourse_keys` caches (extend in U1a via INSERT), `bulk_insert_post_brand_discourse` (mirror for signals in U2b), new `bulk_insert_post_brand_signals` + `upsert_unsanctioned_flags` in U4.
- `x-monitoring/scripts/post_fetch_smoketest.py` — sample renderer to update in U7; `_load_latest_cycle_posts` to investigate in U6a.
- `x-monitoring/data/filters/glm.yaml` — brand_keywords seed to verify in U6a.
- `docs/post_fetch_architecture.md` — architecture doc to update for the new dimension.