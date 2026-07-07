---
title: Smoketest --source=latest-n + --query-from-yaml polish
date: 2026-07-07
type: feat
status: ready
---

# Context

The post-fetch smoketest (`scripts/post_fetch_smoketest.py`) currently supports three source modes:
- `latest-cycle` — most recent posts from `data/x_monitoring.db`, filtered to brand-attributed posts
- `fixture` — synthetic JSONL
- `api-query` — live TwitterAPI.io (opt-in)

Two operator-facing changes are in scope:

1. **`--source=latest-n` mode (DB path).** The N most recent posts from the DB, ordered by `fetched_at DESC`, **with no brand filter** — so the operator can see the full raw upstream ingest, including posts with no detected brand attribution. Real posts carry real `author_handle`s in the DB, so the renderer keeps emitting the real `https://x.com/<handle>/status/<id>` URL — no synthetic URL format is needed.

2. **`--query-from-yaml BRAND` polish for `--source=api-query` (live path).** Today, going to live mode means hand-writing an X advanced-search string every time (`--query 'kimi (K2.7 OR K2.6) min_faves:2'`). The polish: a flag that reads `data/queries/<BRAND>.yaml` and forwards the first enabled query (Q1 by default) as the live-fetch argument. The "easy switch to live calls" UX — from DB mode to live mode is one flag, with the same translate+classify pipeline downstream.

**Outcome:** Two new operator ergonomics. SQL moves from inline-in-the-script to a new `Store.read_recent_posts(limit)` method, following the codebase convention of owning all SQL in `Store`. The renderer needs no change.

# Files to modify

| File | Change |
|---|---|
| `x-monitoring/x_monitor/store.py` | New `Store.read_recent_posts(limit)` method (above `recent_posts_unsanctioned_missing` at line 1787). |
| `x-monitoring/scripts/post_fetch_smoketest.py` | Extend `--source` choices; add `--latest` flag; new `--query-from-yaml` + `--query-id` flags in a mutually-exclusive group with `--query`; new `_load_latest_n_posts` and `_resolve_query_from_yaml` helpers; new dispatch branch in `main()` for `latest-n`; pre-validation in `main()`. |
| `x-monitoring/x_monitor/__main__.py` | `cmd_smoketest` (line 983) forwards the new flags; smoketest subparser in `build_parser` (line 1202) gains the new args. |
| `x-monitoring/tests/test_post_fetch_smoketest_latest_n.py` | **New file**, 8 tests mirroring `test_post_fetch_smoketest_latest_cycle.py`. |
| `x-monitoring/tests/test_post_fetch_smoketest_api_source.py` | **9 new tests** for query-from-yaml (yaml resolution, query-id selection, missing brand, no enabled queries, mutual exclusion, missing flag, CLI forwarder). |
| `~/.claude/skills/custom-claude-skills/pushin_weight_smoketest/SKILL.md` | Update frontmatter description, `## Source modes` table, and `## Canonical command` with a `latest-n` example and a `api-query --query-from-yaml kimi` example. |

Plan docs (`docs/plans/2026-07-04-001-…` and `docs/plans/2026-07-02-002-…`) are historical artifacts; no edits.

# Implementation

## 1. `Store.read_recent_posts(limit)` in `x_monitor/store.py`

**Insert above `recent_posts_unsanctioned_missing` (line 1787).** Mirror the row-dict return shape of `get_posts_missing_translations` (line 854).

- **Signature:** `read_recent_posts(self, limit: int = 100) -> list[dict[str, Any]]`
- **SQL:** `SELECT p.tweet_id, p.text, p.lang_detected, p.author_handle, p.fetched_at FROM posts p ORDER BY p.fetched_at DESC LIMIT ?`
- **Return:** list of `dict(r)` rows. No JOIN, no filter, no brand attribution — operator wants raw N.
- **Docstring** notes: "Used by the smoketest's `--source=latest-n` mode. Surfaces the N most recent production posts regardless of brand attribution."

## 2. `_load_latest_n_posts` in `scripts/post_fetch_smoketest.py`

**Insert after `_load_latest_cycle_posts` (line 159).** Structurally identical to the cycle helper except:
- Calls `store.read_recent_posts(limit)` instead of inline SQL.
- Does **not** filter posts with no detected brand attribution.
- Still runs `detect_brand_mentions` so the renderer's `brand_mentions:` block can be populated when brands ARE detected.
- Returns `(posts, 0)` — `posts_with_no_brand_skipped` is always 0 for this mode.

**Signature:** `_load_latest_n_posts(store, limit: int) -> tuple[list[dict], int]`

**Post-dict shape (mirrors lines 144-153):** `tweet_id`, `id`, `text`, `lang_detected`, `author_handle`, `brand_id` (first detected brand or `""`), `brand_ids` (list, possibly empty).

## 3. Argparse changes in `_parse_args`

- **Line 50** — extend `--source` choices to `["latest-cycle", "latest-n", "fixture", "api-query"]`. Update help text.
- **After line 97** — add `--latest`:
  ```
  p.add_argument("--latest", type=int, default=20,
                 help="Cap on posts for --source=latest-n (default: 20). "
                      "Distinct from --limit, which caps --source=latest-cycle "
                      "and --source=api-query.")
  ```
  `--limit` keeps its existing default of 200 and its existing role as the global cap for `latest-cycle` and `api-query`.

## 4. Pre-validation in `main()`

Add a block alongside the existing pre-validation (lines 373-387):

- If `args.source == "latest-n"` and `args.latest <= 0`: print error to stderr, return 2.
- If `args.latest > args.limit`: warn to stderr ("--latest N exceeds --limit; clamping --latest to --limit"), clamp `args.latest = args.limit`.

## 5. Dispatch in `main()`

**Insert before the `db_path` fallback at line 439**, mirroring the `api-query` branch's structure:

```python
if args.source == "latest-n":
    store = Store(db_path, auto_migrate=True)
    try:
        brand_keywords = store.read_brand_keywords()
        compiled_index = compile_keyword_index(brand_keywords)
        posts, posts_with_no_brand_skipped = _load_latest_n_posts(
            store, args.latest,
        )
        brand_registry_rows = store.read_brands()
        return _run_pipeline(
            posts, brand_registry_rows, args,
            posts_with_no_brand_skipped=posts_with_no_brand_skipped,
        )
    finally:
        store.close()
```

`_run_pipeline` needs no change — it already handles empty `brand_ids` (skips classification at line 545-547) and `posts_with_no_brand_skipped == 0` is suppressed by the `if posts_with_no_brand_skipped:` guard at line 611.

The existing `db_path` missing fallback (line 440) still applies for `latest-n` when the DB doesn't exist — operator gets rc=2 with a friendly error.

## 6. Renderer — no change

`_render_sample_posts` (lines 284-293) already reads `post.get("author_handle")` with a `(no handle)` fallback. The "post with no brand attribution" path (lines 319-323) already renders correctly: `post:` block with `types=(none)` and `brand_mentions: (none)`. This is exactly what the operator wants to see.

## 7. `--query-from-yaml BRAND` polish for `--source=api-query`

**Goal:** Let the operator go from DB mode to live mode with one switch, by removing the friction of hand-writing X advanced-search strings.

**Status quo (line 62-65 of `scripts/post_fetch_smoketest.py`):**
```
--source=api-query  --query 'kimi (K2.7 OR K2.6) min_faves:2'  --since 2026-07-01
```
Operator must compose the raw query string every time.

**New UX:**
```
--source=api-query  --query-from-yaml kimi  --since 2026-07-01
```
Reads `data/queries/kimi.yaml`, picks the first enabled query (Q1 by default), and forwards its `query_string` as the live-fetch argument.

### 7a. Argparse change in `_parse_args`

Add a new flag **mutually exclusive with `--query`** (using `argparse.add_mutually_exclusive_group`):

```
group = p.add_mutually_exclusive_group()
group.add_argument("--query", help="...existing docstring...")
group.add_argument(
    "--query-from-yaml", metavar="BRAND",
    help="Load the query string from data/queries/<BRAND>.yaml. "
         "Uses the first enabled query (Q1 by default). "
         "Mutually exclusive with --query."
)
```

Add a companion flag for picking a specific query from the yaml (default: first enabled):
```
p.add_argument(
    "--query-id", default=None,
    help="When using --query-from-yaml, select a specific query id "
         "(e.g. Q3) instead of the first enabled. Default: first enabled."
)
```

### 7b. Pre-validation in `main()`

In the existing `--source=api-query` pre-validation block (line 379-383), add:
- If `args.source == "api-query"` and `args.query is None` and `args.query_from_yaml is None`: print error ("--source=api-query requires --query '...' or --query-from-yaml BRAND"), return 2.
- If `args.query_from_yaml` is set, resolve the query string at startup. The yaml loader reads `data/queries/<brand>.yaml` (path relative to project root, same convention as `__main__.py` line 416-417). On missing file or no enabled query, print error and return 2. Set `args.query = <resolved string>` so the existing `_load_api_posts` path is untouched.

### 7c. Helper `_resolve_query_from_yaml`

New module-level helper in `scripts/post_fetch_smoketest.py`:

```
def _resolve_query_from_yaml(brand: str, query_id: str | None) -> str:
    """Load data/queries/<brand>.yaml and return the resolved query string.

    Reads the first enabled query by default; if `query_id` is set (e.g. "Q3"),
    selects that specific query. Raises ValueError on missing file, no enabled
    queries, or missing query_id — the caller maps that to rc=2.
    """
```

The yaml schema (verified in `data/queries/llama.yaml` and others) is:
```yaml
queries:
  - id: Q1
    query_string: '(...) min_faves:5'
    enabled: true
  - id: Q2
    ...
```

The helper does NOT need a yaml library — a hand-rolled parser that walks lines, finds the `queries:` block, and pulls the active entry is sufficient (matches the codebase's preference for not adding PyYAML as a dep just for this). Pattern: scan top-level `queries:` list entries, find one with `id == query_id` (or first `enabled: true`), extract the `query_string:` value.

### 7d. Update `_load_api_posts` and the smoketest pipeline

**No change** to `_load_api_posts` (lines 184-240) or `_run_pipeline` (lines 467-673). The polish is purely argparse + a yaml loader; once `args.query` is set, the existing flow runs unchanged.

### 7e. CLI forwarder in `x_monitor/__main__.py`

`cmd_smoketest` (lines 983-1029) needs to forward the new flags. After line 1009 (`argv.extend(["--query", args.query])`), add:
```
if getattr(args, "query_from_yaml", None):
    argv.extend(["--query-from-yaml", args.query_from_yaml])
if getattr(args, "query_id", None):
    argv.extend(["--query-id", args.query_id])
```

And update the docstring at line 991-1000 to mention `--query-from-yaml` and `--query-id` alongside `--query`.

Also extend `build_parser` (line 1202+) where the smoketest subparser is defined — add the same `--query-from-yaml` and `--query-id` arguments to keep the top-level `x-monitor smoketest` CLI consistent.

# Tests (`tests/test_post_fetch_smoketest_latest_n.py`)

**New file**, 8 tests. Mirror the structure of `test_post_fetch_smoketest_latest_cycle.py` (FakeClaudeClient, `_seed_db_with_kept_posts` pattern), but seed posts **without** populating `posts_brands` so the deterministic brand-keyword detector can return `[]` for some posts.

| Test | Asserts |
|---|---|
| `test_smoketest_latest_n_end_to_end` | `sm.main(["--source", "latest-n", "--latest", "5"])` against seeded DB with 5 posts → rc=0, "POST-FETCH SMOKETEST REPORT" present. |
| `test_smoketest_latest_n_respects_latest_flag` | Seed 10 posts, `--latest 3`, assert `n_posts=3`. |
| `test_smoketest_latest_n_includes_no_brand_posts` | **The critical test for the user's requirement.** Seed 3 posts: 1 with brand-mentioning text, 2 with neutral text (no brand). Assert all 3 appear; `posts_no_brand_skipped:` is NOT in the output. |
| `test_smoketest_latest_n_renders_url_when_handle_present` | Seed post with `author_handle='adlenesifi'`; assert URL `https://x.com/adlenesifi/status/<id>` appears in the sample-posts section. |
| `test_smoketest_latest_n_renders_no_handle_fallback` | Seed post with `author_handle=NULL`; assert `https://x.com/(no handle)/status/<id>` appears. |
| `test_smoketest_latest_n_empty_db` | Fresh empty DB, `sm.main(["--source", "latest-n"])`, assert rc=0 and "nothing to report" in output. |
| `test_smoketest_latest_n_parser_rejects_zero` | `sm.main(["--source", "latest-n", "--latest", "0"])` → rc=2. |
| `test_smoketest_latest_n_clamps_when_latest_exceeds_limit` | Seed 10 posts, run `--latest 100 --limit 5`, assert rc=0 and `n_posts=5` (cap kicks in). |

# Tests for `--query-from-yaml`

Add to a new section in the existing `test_post_fetch_smoketest_api_source.py` (or a new `test_post_fetch_smoketest_query_yaml.py` if the test file is too long — check first).

| Test | Asserts |
|---|---|
| `test_resolve_query_from_yaml_picks_first_enabled` | Hand-roll a `data/queries/_test_brand.yaml` with two enabled queries; assert the helper returns the Q1 `query_string`. |
| `test_resolve_query_from_yaml_picks_specific_query_id` | Same yaml; pass `query_id='Q2'`; assert the Q2 `query_string` is returned. |
| `test_resolve_query_from_yaml_skips_disabled_queries` | Hand-roll yaml with Q1 disabled and Q2 enabled; assert Q2 is returned. |
| `test_resolve_query_from_yaml_raises_on_missing_brand` | `query_from_yaml='nonexistent_brand'` → ValueError. |
| `test_resolve_query_from_yaml_raises_on_no_enabled_queries` | Hand-roll yaml with all queries disabled → ValueError. |
| `test_smoketest_api_query_uses_yaml_query` | Full `sm.main(["--source", "api-query", "--query-from-yaml", "_test_brand"])` end-to-end; assert the live fetch uses the resolved Q1 string. (Use a fake `TwitterApiClient` monkeypatched to return a known set of posts.) |
| `test_smoketest_api_query_yaml_and_query_are_mutually_exclusive` | `sm.main(["--source", "api-query", "--query", "X", "--query-from-yaml", "Y"])` → rc=2. |
| `test_smoketest_api_query_yaml_without_query_exits_2` | `sm.main(["--source", "api-query"])` (neither flag) → rc=2 with friendly error. |
| `test_cli_forwarder_passes_query_from_yaml` | `x-monitor smoketest --source api-query --query-from-yaml kimi` → assert the underlying `post_fetch_smoketest.main` receives `--query-from-yaml kimi`. |

The `_test_brand` yaml is created via `tmp_path` and uses the project-root-relative path convention. The existing `test_post_fetch_smoketest_api_source.py` already has a fixture pattern for this (the file's `tmp_path` setup at the top).

# Skill doc updates

**File:** `~/.claude/skills/custom-claude-skills/pushin_weight_smoketest/SKILL.md`

- **Line 3 (frontmatter `description`)** — extend the mode list: "switch to `--source=latest-cycle` for a real DB run filtered to brand-attributed posts, `--source=latest-n` for raw N most-recent posts with no brand filter, or `--source=api-query --query-from-yaml BRAND` for live X fetches using a brand's saved query."
- **Lines 43-49 (Source modes table)** — add a row between `latest-cycle` and `api-query`:
  ```
  | `latest-n` | Read the N most recent posts from `data/x_monitoring.db`, ordered by `fetched_at DESC`. **No brand filter** — surfaces raw N including posts with no detected brand attribution. Use `--latest N` to set the cap (default 20). | One LLM call per post, no API fetch |
  ```
- **Canonical command (after line 39)** — add two example blocks: a `latest-n` example with `tee` to `tests/classifier_tests/smoketest_latest_n.txt`, and an `api-query --query-from-yaml kimi` example with `tee` to `tests/classifier_tests/smoketest_live_kimi.txt`. The api-query example is the "easy switch to live calls" path — the operator goes from DB to live with one flag.

# Verification

1. Run the new test file: `cd x-monitoring && python3 -m pytest tests/test_post_fetch_smoketest_latest_n.py tests/test_post_fetch_smoketest_api_source.py -v` — all tests pass (8 new for latest-n, 9 new for query-from-yaml).
2. Run the full smoketest suite to confirm no regressions: `python3 -m pytest tests/test_post_fetch_smoketest* -v` — all existing tests pass.
3. End-to-end manual check against prod DB:
   ```
   cd x-monitoring
   python3 -m scripts.post_fetch_smoketest --source=latest-n --latest=5 | tee /tmp/smoketest_latest_n_smoke.txt
   ```
   Confirm: rc=0, the report includes 5 distinct prod posts, each with a real `https://x.com/<handle>/status/<id>` URL where `author_handle` is populated, and posts with no brand attribution still appear (not skipped).
4. End-to-end manual check on the live-fetch polish (requires `TWITTERAPI_IO_API_KEY` in env):
   ```
   cd x-monitoring
   TWITTERAPI_IO_API_KEY=$KEY \
     python3 -m scripts.post_fetch_smoketest \
       --source=api-query --query-from-yaml kimi --since 2026-07-01 --latest 10 \
     | tee tests/classifier_tests/smoketest_live_kimi.txt
   ```
   Confirm: rc=0, the report shows real `https://x.com/<handle>/status/<id>` URLs, and the query string in the http_log matches the Q1 query from `data/queries/kimi.yaml`.
5. Edge-case manual check:
   - `python3 -m scripts.post_fetch_smoketest --source=latest-n --latest=0` → rc=2, error on stderr.
   - `python3 -m scripts.post_fetch_smoketest --source=latest-n --latest=10000` (with `--limit 200` default) → clamps to 200, warning on stderr.
   - `python3 -m scripts.post_fetch_smoketest --source=api-query --query X --query-from-yaml kimi` → rc=2, mutual-exclusion error.
   - `python3 -m scripts.post_fetch_smoketest --source=api-query` → rc=2, "requires --query or --query-from-yaml".

# Commit strategy

One commit, message:

```
feat(x-monitor): add --source=latest-n + --query-from-yaml to smoketest

- --source=latest-n pulls the N most recent posts from
  data/x_monitoring.db ordered by fetched_at DESC, with no
  brand-attribution filter. Operator asked for raw N for
  production-ingest eyeball checks distinct from the brand-filtered
  latest-cycle mode.
- --query-from-yaml BRAND lets --source=api-query load its query
  string from data/queries/<BRAND>.yaml instead of forcing the
  operator to hand-write an X advanced-search string. The "easy
  switch to live calls" path: from DB to live is one flag, with
  the same translate+classify pipeline downstream.

- x_monitor/store.py: new Store.read_recent_posts(limit) helper
  (SQL moved out of the inline script).
- scripts/post_fetch_smoketest.py:
    * new --latest N flag (default 20), new --source=latest-n
      dispatch, new _load_latest_n_posts helper mirroring
      _load_latest_cycle_posts but skipping the no-brand filter.
    * new --query-from-yaml BRAND + --query-id flags, mutually
      exclusive with --query. New _resolve_query_from_yaml helper
      parses the existing data/queries/<brand>.yaml schema.
- x_monitor/__main__.py: cmd_smoketest forwards the new flags;
  top-level `x-monitor smoketest` subparser gains the new args.
- tests/test_post_fetch_smoketest_latest_n.py: 8 new tests for
  latest-n (end-to-end, --latest flag, no-brand inclusion, URL
  rendering, empty DB, --latest <= 0, --latest > --limit clamp).
- tests/test_post_fetch_smoketest_api_source.py: 9 new tests for
  query-from-yaml (yaml resolution, query-id selection, missing
  brand, no enabled queries, mutual exclusion, missing flag,
  CLI forwarder).
- pushin_weight_smoketest skill: Source modes table + canonical
  command + frontmatter description updated.
```
