---
title: "Populate brand_search_terms DB and seed 6 tables from operator CSV"
type: feat
status: active
date: 2026-06-25
origin: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md (U7, R7)
agent: M3.0
---

# Populate `brand_search_terms` from `data/queries/*.yaml` + seed 6 tables from operator CSV

## Overview

This plan lands two related one-shot operator scripts that close two data gaps in the x-monitor production DB as of 2026-06-25:

1. **The `brand_search_terms` table is empty.** Migration 004 created the table; migration 017 documented the hybrid-by-design contract (yaml = query-side source, DB = attribution-side source). But the table has 0 rows on production, so every post's `extract_search_term_match` falls through to the R6 fallback with `brand_id=None` — search-term provenance is recorded but the brand link is lost. U1 + U2 land a populate script that mirrors the yaml tokens into the DB.

2. **The 6 company/brand/account tables have only 11 v1 brands.** The DB has the 11 original v1 brand rows in `brands` + 11 corresponding `companies` + 11 `brands_companies` edges + 11 `hf_orgs` rows + 1,522 `accounts` (backfilled from historical posts). The 9 newer enabled brands (and the additional 9 in the corrected first-batch CSV) have yaml files and `data/queries/<brand>.yaml` entries but no DB rows. U3 + U4 land a CSV-to-DB seed script that parses `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` (20 rows, 17 columns A-Q) and seeds the 6 tables with operator-curated brand/company/HF/X-account data.

Both scripts are idempotent (INSERT OR IGNORE), dry-run-safe, and re-runnable for follow-up batches. A follow-up plan (deferred) will reverse the populate direction: make `brand_search_terms` canonical and emit yaml from it.

## Problem Frame

Current state on `data/x_monitoring.db` (verified 2026-06-25):

- 20 yaml files in `data/queries/` covering the 20 enabled models in `config.yaml`.
- 11 non-sentinel brand rows in the `brands` table (deepseek, ernie, glm, hunyuan, inclusionai, minimax, mistral, moonshot_kimi, qwen, stepfun, xiaomi_mimo) — the original 11 v1 brands.
- 0 rows in `brand_search_terms` (U1's gap).
- 9 newer enabled brands (llama, nvidia_nemo, doubao, yi, sensechat, exaone, kuaishou, sakana, upstage) have yaml files but no `brands` row yet (U3's gap).
- 11 `hf_orgs` rows (one per v1 company) — 9 of the 20 enabled brands have no HF row.
- 1,522 `accounts` rows (all backfilled from historical posts — none seeded from the corrected first-batch CSV).

Consequences of the two gaps:

- **U1 gap (empty brand_search_terms):** Every post's `extract_search_term_match` returns one `MentionRow(brand_id=None, source="search_term", raw_token="")` — the search-term source is preserved for backfill (R6) but contributes no brand attribution. Brand detection collapses to user_mention + body_keyword + hashtag paths only. The drift check fires on every cycle: `yaml-only=N db-only=0 mismatched=0` — informational noise, but a clear sign the contract is half-implemented.
- **U3 gap (9 brands missing from DB):** The dashboard's brand selector shows 11 brands; the 9 newer enabled brands (Llama, NVIDIA NeMo, Doubao, Yi, SenseChat, EXAONE, Kuaishou, Sakana, Upstage) are invisible. The CSV has operator-curated display_names, accent-color suggestions, official X handles, staff X handles, and HF namespaces for all 20 brands — but none of it is in the DB.

Goal: two one-shot operator scripts:

1. **U1 (brand_search_terms populate):** read `data/queries/<brand>.yaml`, extract the same tokens that `query_plan._load_brand_tokens_per_model` reads (first paren of Q2/Q3/Q5/Q6, split on ` OR `), and INSERT `(term, brand_id, added_at)` rows into `brand_search_terms` — plus the prerequisite brand-row seeds for the 9 missing brands. After running, the drift check reports `yaml-only=0 db-only=0 mismatched=0` for the 20 enabled brands.

2. **U3 (CSV-to-DB seed):** parse `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` (20 rows, 17 columns A-Q) and seed the 6 tables (`companies`, `brands`, `brands_companies`, `accounts`, `brands_accounts`, `hf_orgs`) with operator-curated data. The 10 v1 brand_ids are reused via the override map; the 10 new brand_ids are slug-derived. After running, the DB has 20 brand rows, ~12 company rows, ~30-50 accounts (X handles), and ~20-30 hf_orgs.

## Requirements Trace

- **R1.** Read `data/queries/<brand>.yaml` for every model in `config.yaml::enabled_models` (20 brands as of 2026-06-25).
- **R2.** Extract the same token set that `query_plan._load_brand_tokens_per_model` (query_plan.py:169-211) produces: first `(...)` group of Q2/Q3/Q5/Q6 query strings, split on ` OR `. Preserve the exact form (case, whitespace, embedded quotes, CJK characters, emoji). Do not lowercase; do not strip quotes; do not collapse whitespace.
- **R3.** `brand_id` for each token row is the yaml's filename basename (e.g. `xiaomi_mimo.yaml` → `xiaomi_mimo`). This matches `config.yaml::enabled_models` and the convention used by `query_plan._load_brand_tokens_per_model`.
- **R4.** For each enabled brand that has a yaml but no row in `brands`, INSERT OR IGNORE a brand row with operator-curated `display_name` and `accent_color`. The 9 missing brands' metadata is hardcoded in the script (table below) — same pattern as `scripts/2026-06-19-180000-seed-detection-tables.py` hardcodes its `brand_yaml` mapping.
- **R5.** INSERT OR IGNORE every `(brand_id, term)` row into `brand_search_terms` with `added_at = now()`. Idempotent: re-running adds 0 rows on second invocation.
- **R6.** Support `--dry-run` (`--dry-run` or `DRY_RUN=1` env): print the planned (brand_id, term) pairs and brand-row creations, make no DB writes, exit 0.
- **R7.** After writes, run the same drift check the live cycle runs (`x_monitor.run._log_brand_search_terms_drift`) and assert zero drift across the 20 enabled brands. Print a summary.
- **R8.** Test coverage in `tests/test_brand_search_terms_populate.py` covering: token extraction (CJK + emoji + quoted), idempotency, brand-row auto-creation, dry-run, drift-zero assertion, and a fresh-DB end-to-end.
- **R9.** A second operator script `scripts/2026-06-25-005-seed-companies-brands-from-csv.py` parses the operator-curated CSV at `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` (the "stripped" corrected first-batch file, 20 data rows covering the 20 enabled brands in `config.yaml`, 17 columns A-Q) and seeds 6 tables: `companies`, `brands`, `brands_companies`, `accounts`, `brands_accounts`, `hf_orgs`. The CSV path is a positional CLI arg so the script is portable across machines. Note: the user's original mention of "col A, K, L, O multi-value" referenced an earlier `allenwlee` file; the actual stripped CSV's multi-value columns are K, L, M, N, O (the in-cell separator is `,` with optional trailing space). The plan uses the actual file's column meanings.
- **R10.** Column mapping (verified against `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv`):

| Col | Header | Type | Maps to |
|-----|--------|------|---------|
| A | `#` | single (rank) | informational only — not seeded |
| B | `brands.display_name` | single | `brands.display_name`; brand_id = slug |
| C | `brands.display_name_en` | single | `brands.display_name_en` (refines B) |
| D | `brands.display_name_zh_cn` | single | `brands.display_name_zh_cn` (refines B) |
| E | `company.display_name` | single | `companies.display_name`; company_id = slug |
| F | `company.display_name_en` | single | `companies.display_name_en` (refines E) |
| G | `company.display_name_zh_cn` | single | `companies.display_name_zh_cn` (refines E) |
| H | `company.hq_country` | single | `companies.hq_country` |
| I | `co_hq_city` | single | not seeded (the schema has no city column; stored in `companies.notes` or follow-up) |
| J | `ai_lab_city` | single | not seeded (same as I) |
| K | `brands_accounts.role_id='official'` | **multi-value** (X URLs, comma-separated) | each URL → `accounts` (handle from URL) + `brands_accounts` (role='official') |
| L | `brands_accounts.role_id='staff'` | **multi-value** (X URLs, comma-separated) | each URL → `accounts` + `brands_accounts` (role='staff') |
| M | `notes` | **multi-value** (free text, often multiple sentences) | **NOT seeded** — column is ignored by the script per operator direction 2026-06-25 |
| N | `github_accounts` | **multi-value** (GitHub org URLs) | not seeded in this unit (no `brands_github_orgs` table yet; deferred) |
| O | `hf_orgs` | **multi-value** (HF URLs, sometimes space-separated) | each URL → `hf_orgs.id` (namespace from URL) |
| P | `hf_followers_num` | single (comma-formatted, e.g. `"38,400"`) | not seeded (informational; hf_orgs has no followers column) |
| Q | `tier` | single | not seeded in this unit (no tier column in `brands`; deferred to follow-up that adds a `brands_tier` column) |

- **R11.** Multi-value cells use a robust split: split on `,` and/or whitespace runs, strip whitespace, filter empty strings. The actual data shows mixed separators: K/L use `, `, O uses spaces (e.g. `https://huggingface.co/bytedance/   https://huggingface.co/bytedance-research/`). URL parsing: HF namespace from `r'huggingface\.co/([^/]+)'`, X handle from `r'(?:x|twitter)\.com/([^/?\s,]+)'`. Trailing `/` is stripped from handles.
- **R12.** Brand slug = `re.sub(r'[^a-z0-9]+', '_', brand_name.lower()).strip('_')` by default, with a hardcoded operator-curated override map at the top of the script. The map covers the 11 existing v1 brand_ids (`minimax`, `qwen`, `deepseek`, `glm`, `xiaomi_mimo`, `moonshot_kimi`, `inclusionai`, `mistral`, `stepfun`, `ernie`, `hunyuan`) so the script reuses the existing ids where the display_name matches, and adds the 9 new brand_ids (`llama`, `nvidia_nemo`, `doubao`, `yi`, `sensechat`, `exaone`, `kuaishou`, `sakana`, `upstage`) for the CSV's rows. Company slug = same regex + override map pattern; uses the 11 existing company_ids from `companies` table.
- **R13.** Per row, in a single `Store.transaction()`: INSERT OR IGNORE `companies` (slug, display_name from E, display_name_en from F, display_name_zh_cn from G, hq_country from H, created_at=now); INSERT OR IGNORE `brands` (slug, display_name from B, display_name_en from C, display_name_zh_cn from D, accent_color='#9ca3af', is_sentinel=0, created_at=now); INSERT OR IGNORE `brands_companies` (brand_slug, company_slug, ownership_pct=1.0); for each HF URL from O: parse namespace, INSERT OR IGNORE `hf_orgs` (id=namespace, company_id=company_slug, confirmed=1, discovered_via='curated', added_at=now); for each X URL from K: parse handle, INSERT OR IGNORE `accounts` (author_id=slug-of-handle, handle=handle, verified=0, bio_contains_brand=0, engagement_tier='low', first_seen_at=now, last_seen_at=now), then INSERT OR IGNORE `brands_accounts` (brand_slug, author_id, role='official', added_at=now); for each X URL from L: same as K but role='staff'. Column M (notes) is read and discarded — it is not written to any table. `companies_accounts` is NOT seeded (out of scope per the user's 6-table list; the schema has the table and the app populates it from `brands_accounts → brands_companies` joins later).
- **R14.** Test coverage in `tests/test_seed_companies_brands_from_csv.py` covering: multi-value split (K with `, `, O with whitespace), URL parsing (HF + X with edge cases like trailing `;`, trailing space), slug generation with override map (10 brand_ids must round-trip to the existing v1 ids), idempotency, dry-run, CJK brand name (`千问` → brand_id `qwen` via override), missing optional column (N=empty github → no error), `--limit N` for partial-run testing, and the case where a K URL is `https://x.com/X;` (trailing semicolon — strip it).

### New brand metadata table (R4)

The 9 brands without a `brands` row. `display_name` and `accent_color` are operator-curated. The accent colors are placeholders — operator should review and adjust in a follow-up.

| brand_id | display_name | accent_color |
|----------|--------------|--------------|
| llama | Meta Llama | #1877f2 |
| nvidia_nemo | NVIDIA NeMo | #76b900 |
| doubao | ByteDance Doubao | #3d5afe |
| yi | 01.AI Yi | #6366f1 |
| sensechat | SenseTime SenseChat | #f97316 |
| exaone | LG EXAONE | #a855f7 |
| kuaishou | Kuaishou KwaiYii | #ef4444 |
| sakana | Sakana AI | #14b8a6 |
| upstage | Upstage Solar | #06b6d4 |

## Scope Boundaries

- **No yaml changes.** The U1 script reads the existing 20 yaml files; the new tokens added in plan 2026-06-25-001 are already there.
- **No schema changes.** No new migration. The tables already exist (`brands`, `companies`, `brands_companies`, `brand_accounts`, `accounts` per migration 004; `hf_orgs` per migration 009; `brands_companies` renamed from `brand_companies` per migration 010). The scripts write data only.
- **No changes to `data/filters/*.yaml`.** The filter layer (must_have_none etc.) is unaffected; it is consulted downstream of attribution.
- **No changes to `query_plan.py` or `attribution.py`.** The contract is already enforced; the scripts just populate the missing data.
- **No changes to `config.yaml` enabled_models or call_b_groups.** The drift check will use the same 20 brands.
- **The reverse script (DB → yaml) is OUT of scope here.** A future plan will make `brand_search_terms` canonical and add a generator that emits yaml files from the table. This plan only does the populate direction.
- **No re-attribute or backfill of existing posts.** The U1 populate script writes the attribution lookup table; the existing reattribute subcommand (U3 of the call-path attribution plan) is what walks historical posts through the new pipeline. The drift check after the populate run will show `db-only=0` for the lookup map, but historical posts still need a separate re-run to materialize `MentionRow`s with non-NULL `brand_id` for the `search_term` source.
- **Display names for the 9 new brands are first-pass.** Operator can adjust via a follow-up backfill (same pattern as the i18n display_name backfill scripts 2026-06-23-001/002).
- **`companies_accounts` is NOT seeded in U3.** Out of scope per the user's 6-table list. The schema has the table; the application populates it from `brands_accounts → brands_companies` joins later.
- **`products` table is NOT seeded in U3.** Column A in the CSV is operator-curated product names, not HF repo_ids. Seeding the `products` table (per migration 009) requires HF API data (downloads, sha, etc.) that the CSV doesn't have. The U3 script reads column A but discards it. A follow-up that maps product names → repo_ids (or runs the HF products crawler) is required.
- **Tier column (CSV Q) is NOT seeded.** `brands` has no tier column; adding one is a follow-up migration.
- **github_accounts (CSV N) is NOT seeded.** No `brands_github_orgs` table exists; adding one is a follow-up migration.

## Context & Research

### Relevant code and patterns

- `x_monitor/query_plan.py:169-211` — `_load_brand_tokens_per_model(enabled_models, queries_dir)`. The exact algorithm the script must mirror: load yaml, iterate Q2/Q3/Q5/Q6, find first `(...)` group, split on ` OR `, dedup while preserving insertion order.
- `x_monitor/query_plan.py:104-115` — explicit comment in plan_calls: "Read from `config.yaml` `call_c_specs:` (not from `data/queries/`)". Call C tokens are NOT in scope here — they live in config.yaml under `call_c_specs[].co_occurrence` and `call_c_specs[].brand_groups`. The populate script is brand-token-only.
- `x_monitor/attribution.py:531-594` — `extract_search_term_match`. Consumes the `{term: brand_id}` map from the DB and looks up each keyword from `search_queries.keywords_json` against it. Casefold fallback for term lookup; quote-preserving exact match is preferred.
- `x_monitor/store.py:1517-1526` — `Store.read_brand_search_terms()`. The DB reader. The populate script writes the inverse; no Store method is needed for the write — direct SQL `INSERT OR IGNORE` is the right tool (matches the seed-detection-tables.py pattern).
- `x_monitor/store.py:155-180` — `Store.transaction()` context manager. Use this for the write batch to keep brand-row inserts and brand_search_terms inserts atomic.
- `x_monitor/run.py:304-313` — `_load_brand_search_terms_from_db(store)`. The contract: DB is the attribution source of truth.
- `x_monitor/run.py:316-347` — `_log_brand_search_terms_drift(yaml_terms, db_terms)`. Reuse it (call directly, not reimplement) for the post-run verification.
- `x_monitor/migrations/017_brand_search_terms_hybrid.sql` — the contract comment. The script's docstring should reference this migration as the contract authority.
- `x_monitor/migrations/004_company_brand_account_model.sql:155-164` — `brand_search_terms` schema. PK is `(brand_id, term)`, so `INSERT OR IGNORE` is naturally idempotent on re-run.
- `x_monitor/migrations/004_company_brand_account_model.sql:140-153` — `brands` schema. `display_name TEXT NOT NULL`, `accent_color TEXT NOT NULL DEFAULT '#9ca3af'`, `is_sentinel INTEGER NOT NULL DEFAULT 0`, `created_at TEXT NOT NULL`. The script's brand-row INSERT must supply display_name and created_at; accent_color and is_sentinel use defaults.
- `scripts/2026-06-19-180000-seed-detection-tables.py` — the canonical "operator script that reads yaml and INSERTs into detection tables" template. Same import style (`sqlite3`, `sys`, `yaml`), same path-discovery style (hardcoded `data/` root), same row-count summary footer, same idempotent `INSERT OR IGNORE` style. Replicate this template.
- `scripts/2026-06-23-005-seed-enum-zh-cn-labels.py` — second template for "operator script that takes `db_path` as positional CLI arg and prints summary". Combine both patterns.

### Token extraction algorithm (mirror of `_load_brand_tokens_per_model`)

The populate script implements the same parsing as `query_plan.py:169-211`. Pseudocode (not implementation — direction for the implementer):

```
for brand_id in enabled_models:
    path = data/queries/<brand_id>.yaml
    yaml = load(path).queries
    seen = set(); tokens = []
    for entry in yaml:
        if entry.id not in {Q2, Q3, Q5, Q6}: continue
        # Inline paren-walker: find first "(...)" group in query_string
        # Split group on " OR ", strip whitespace
        for tok in group.split(" OR "):
            tok = tok.strip()
            if tok and tok not in seen:
                seen.add(tok); tokens.append(tok)
    # For each token: INSERT OR IGNORE (brand_id, term, added_at)
```

Q1 and Q4 are account-based (`from:<handle>`, `to:<handle>`) and contribute no body-keyword tokens to the brand_search_terms map — the paren-walker will simply not find a group on those lines (Q1 for xiaomi_mimo is `from:XiaomiMiMo min_faves:3` with no parens; Q1 for minimax is `from:MiniMaxAI min_faves:5`). The script must not error on those — it just yields no tokens for that Q*.

### Test patterns

- `tests/test_brand_search_terms_hybrid.py` — the existing test file for the migration 017 contract. The new test file (`test_brand_search_terms_populate.py`) is a sibling, not a replacement; the existing file stays as-is.
- All migrate / Store tests follow the `tmp_path` + `Store(db, auto_migrate=True)` + `s.close()` pattern. The new test follows the same pattern.
- Fixture pattern: a `tmp_path/queries/` directory seeded with one or two hand-written yaml files; pass that as `queries_dir` to a pure `_extract_tokens(yaml_text) -> list[str]` function for unit tests. End-to-end tests open a real Store + run the script's logic against a tmp DB.

## Key Technical Decisions

- **Mirror `_load_brand_tokens_per_model` byte-for-byte.** The exact same paren-walker, the exact same `Q2/Q3/Q5/Q6` filter, the exact same `split(" OR ")` and `strip()`. This guarantees that "the tokens `plan_calls` puts in the query string" and "the tokens `extract_search_term_match` looks up" come from the same set. If we ever change the parser in query_plan.py, we must change the populate script in lockstep — that invariant is the plan's load-bearing claim.
- **Auto-create brand rows for the 9 missing brands in the same script.** A two-step populate (brands first, then brand_search_terms) inside one `Store.transaction()`. The 9 metadata entries are hardcoded in the script (R4 table). Alternative considered: a separate "seed new brands" script. Rejected: the populate is the natural moment to discover the gap, and a follow-up failure (FK violation) on the first run is bad UX.
- **Reuse `_log_brand_search_terms_drift` for verification.** The live cycle already uses it; the populate script imports and calls it after writes. The assertion is `0 yaml-only, 0 db-only, 0 mismatched` for the 20 enabled brands. This is the only way to prove the populate is "precise" without re-deriving the comparison.
- **No fuzzing, no normalization, no lowercasing.** The brand_search_terms map stores terms as-is; the casefold fallback in `extract_search_term_match` handles the lowercase edge cases. The script does not pre-lowercase; that would break the exact-match fast path.
- **Operator-runnable, not auto-migrated.** The script is a separate operator action invoked after schema changes. Auto-migration in `Store.__init__` would be wrong: the table exists, but the population is operator-curated (operator may add new yaml tokens that should be reviewed before going live). Pattern matches `scripts/2026-06-19-180000-seed-detection-tables.py` and `scripts/2026-06-23-005-seed-enum-zh-cn-labels.py`.
- **Re-run safe via `INSERT OR IGNORE`.** PK is `(brand_id, term)`, so the second run inserts 0 new rows. Useful when the operator adds new tokens to a yaml and re-runs the script — only the new tokens are inserted, existing rows untouched.
- **CLI surface: `python3 scripts/2026-06-25-004-populate-brand-search-terms.py <db_path> [--dry-run]`.** The positional db_path matches the i18n / enum-labels scripts. The `--dry-run` flag is mandatory for safe first-run on production.
- **Display name and accent color for the 9 new brands are first-pass placeholders.** Operator should review and override with the operator-curated values in a follow-up (script + commit). The accent colors in the R4 table are placeholders; the operator may prefer a different palette.

## Proposed Operator Run

### U1 populate (brand_search_terms from yaml)

```
# Preview first (no writes)
python3 scripts/2026-06-25-004-populate-brand-search-terms.py data/x_monitoring.db --dry-run

# Commit
python3 scripts/2026-06-25-004-populate-brand-search-terms.py data/x_monitoring.db

# Verify
sqlite3 data/x_monitoring.db "SELECT brand_id, COUNT(*) FROM brand_search_terms GROUP BY brand_id ORDER BY 2 DESC;"
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brand_search_terms;"
# expected: 20 brands, total row count = sum of unique tokens across all yaml files (~120-140)
```

### U3 CSV seed (companies, brands, brands_companies, accounts, brands_accounts, hf_orgs)

```
# Preview first 5 rows (no writes)
python3 scripts/2026-06-25-005-seed-companies-brands-from-csv.py \
    data/x_monitoring.db \
    docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv \
    --dry-run --limit 5

# Commit (full run, 20 rows)
python3 scripts/2026-06-25-005-seed-companies-brands-from-csv.py \
    data/x_monitoring.db \
    docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv

# Verify
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands;"           # expect 20 (10 existing + 10 new = all enabled)
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM companies;"        # expect ~12 (parents; some brands share parents)
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_companies;" # expect 20
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM accounts;"         # expect ~30-50 (X handles from K + L)
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_accounts;"  # expect ~30-50
sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM hf_orgs;"          # expect ~20-30 (HF namespaces from O)
# expected: 10 of the 20 brand_ids match existing v1 brand_ids (reused via override map)
```

## Implementation Units

- [ ] **Unit 1: Populate script `scripts/2026-06-25-004-populate-brand-search-terms.py`**

**Goal:** Read `data/queries/<brand>.yaml` for the 20 enabled brands, extract the same tokens as `query_plan._load_brand_tokens_per_model`, ensure brand rows exist for all 20, and INSERT OR IGNORE the tokens into `brand_search_terms`. Reuse the drift check to confirm zero drift on exit.

**Requirements:** R1, R2, R3, R4, R5, R6, R7

**Dependencies:** None (the DB schema and the yaml files are both in their final state as of 2026-06-25).

**Files:**

- Create: `x-monitoring/scripts/2026-06-25-004-populate-brand-search-terms.py`
- Test: `x-monitoring/tests/test_brand_search_terms_populate.py` (see U2)

**Approach:**

- Top-level script: `import sqlite3, sys, yaml`; positional `sys.argv[1]` is the `db_path`; optional `--dry-run` flag (check `sys.argv`).
- Hardcode the `enabled_models` list (or import from `x_monitor.config.ENABLED_MODELS` if accessible; if not, hardcode the 20 brand_ids in declaration order to match `config.yaml`).
- Hardcode the `NEW_BRANDS` dict (9 brand_ids → `(display_name, accent_color)` per R4 table).
- Hardcode the `QUERIES_DIR = Path(__file__).resolve().parents[1] / "data" / "queries"` (or read from `config.yaml::data_root` if the project has one — verify in the implementer's first read).
- Function `_extract_tokens(yaml_text: str) -> list[str]` — pure, no I/O. Mirrors `_load_brand_tokens_per_model` byte-for-byte. Used by the script AND by the test file.
- Function `_ensure_brand_rows(conn, brand_id, display_name=None, accent_color=None) -> bool` — returns True if a new brand row was inserted. Uses `INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, is_sentinel, created_at) VALUES (?, ?, ?, 0, ?)`. If `display_name` is None, look up from `NEW_BRANDS`; if still None, error (the 11 existing brands have rows, so this branch is unreachable in practice — defensive only).
- Main block:
  1. Open `sqlite3.connect(db_path)` with `PRAGMA foreign_keys = ON`.
  2. For each `brand_id` in `enabled_models`:
     - Read `<brand_id>.yaml` from `QUERIES_DIR`. Skip with warning if missing.
     - Compute tokens via `_extract_tokens(yaml_text)`.
     - If `--dry-run`: print the brand_id, the planned brand-row action (insert or skip), the token count, and the first 5 tokens as a sample. Continue.
     - Else: call `_ensure_brand_rows(...)` once; then `INSERT OR IGNORE INTO brand_search_terms(brand_id, term, added_at) VALUES (?, ?, ?)` for each token inside a single `conn.execute()` loop; track `new_terms` count.
  3. After the loop, `conn.commit()`.
  4. Read back: `SELECT brand_id, term FROM brand_search_terms` → build the `db_terms` dict.
  5. Re-derive the `yaml_terms` dict (same as `_build_brand_index` in `run.py:266`, but inlined here to avoid importing the private helper).
  6. Call `_log_brand_search_terms_drift(yaml_terms, db_terms)`. If any drift is reported, exit 1 with a clear "populate incomplete" message; else print a zero-drift summary.
  7. Print the per-brand and total row counts (same style as `seed-detection-tables.py`).
- Imports: `from x_monitor.run import _log_brand_search_terms_drift` (this is the public-by-convention helper, used by the test file already).

**Test scenarios:**

- Happy path: against a `tmp_path` DB, running the script populates 20 brand rows and 100+ `brand_search_terms` rows; drift is zero.
- CJK preservation: `海螺` from `minimax.yaml` is stored as `海螺` (not `海螺`, not `hai-luo`).
- Quoted preservation: `"Llama 3"` from `llama.yaml` is stored as `"Llama 3"` (with quotes), not `Llama 3`.
- Emoji preservation: `🤯` from any brand's Q6 is stored as `🤯`.
- Idempotency: running the script twice against the same DB inserts 0 rows on the second run.
- Dry-run: with `--dry-run`, the script makes zero writes (verify by counting `brand_search_terms` rows before/after).
- Missing brand row: against a fresh DB, the script creates brand rows for all 20 brands (no FK violation).
- Q1/Q4 ignored: for `minimax.yaml` (Q1=`from:MiniMaxAI min_faves:5`, Q4=`to:MiniMaxAI min_faves:5`), no tokens are extracted from Q1/Q4; only the 3 tokens from Q2/Q3/Q5/Q6 (`MiniMax`, `海螺`, `Hailuo` — note Q5 omits `海螺`).
- xiaomi_mimo edge: `xiaomi_mimo.yaml` Q1 is `from:XiaomiMiMo min_faves:3` (no parens) — the paren-walker must not raise.

**Verification:**

- `python3 scripts/2026-06-25-004-populate-brand-search-terms.py data/x_monitoring.db --dry-run` prints the expected (brand_id, term) list and exits 0.
- Without `--dry-run`, the same command populates the DB and exits 0.
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brand_search_terms"` returns a non-zero count.
- `sqlite3 data/x_monitoring.db "SELECT brand_id, COUNT(*) FROM brand_search_terms GROUP BY brand_id ORDER BY 2 DESC"` shows 20 brand rows with 4-10 tokens each.
- Re-running exits 0 and inserts 0 new rows.
- The next live cycle's drift check log shows `yaml-only=0 db-only=0 mismatched=0` for the 20 enabled brands.

- [ ] **Unit 2: Test file `tests/test_brand_search_terms_populate.py`**

**Goal:** Cover the `_extract_tokens` function (unit) and the populate script (integration), including CJK, emoji, quoted, idempotency, dry-run, and drift-zero.

**Requirements:** R8

**Dependencies:** Unit 1

**Files:**

- Create: `x-monitoring/tests/test_brand_search_terms_populate.py`

**Approach:**

- Pure-function tests for `_extract_tokens(yaml_text: str) -> list[str]`:
  - Sample yaml with Q1=`from:handle min_faves:5` → no tokens from Q1
  - Sample yaml with Q2=`(A OR "B C" OR 海螺 OR 🤯) (how OR 教程) min_faves:2` → `[A, "B C", 海螺, 🤯]` in order, no Q1 contamination
  - Sample yaml with nested parens (e.g. an AND-of-OR clause in the secondary) → first paren group is the brand clause
  - Sample yaml missing Q2/Q3/Q5/Q6 → empty list
- Integration test: `populate_from_yamls(tmp_db, queries_dir)` — call the script's logic in-process against a `tmp_path` DB and a `tmp_path/queries/` seeded with 1-2 yaml files.
- Idempotency: call twice, assert second call inserts 0.
- Dry-run: call with `dry_run=True`, assert no writes, assert the printed plan includes the expected rows.
- Drift-zero: after a successful populate, build the yaml-side map and the db-side map, call `_log_brand_search_terms_drift`, assert no warnings captured (use the same `caplog.at_level(logging.WARNING, logger="x_monitor.run")` pattern as `test_brand_search_terms_hybrid.py`).
- Brand-row auto-creation: populate 2 yamls whose brand_ids have no brand row yet; assert the brands table has those rows after the run.

**Test scenarios:** (per Unit 1's "Test scenarios" — implemented here)

**Verification:**

- `pytest x-monitoring/tests/test_brand_search_terms_populate.py -v` — all tests pass.
- The new test file does not regress any existing test (run the full suite in isolation: `pytest x-monitoring/tests/test_brand_search_terms_hybrid.py` still passes).

- [ ] **Unit 3: CSV-to-DB seed script `scripts/2026-06-25-005-seed-companies-brands-from-csv.py`**

**Goal:** Parse the operator-curated CSV at `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` and seed the 6 tables (`companies`, `brands`, `brands_companies`, `accounts`, `brands_accounts`, `hf_orgs`) with INSERT OR IGNORE. Reuses the 11 v1 brand_ids via the override map; adds the 9 new brand_ids for the rows in the CSV. Re-runnable for follow-up batches.

**Requirements:** R9, R10, R11, R12, R13, R14

**Dependencies:** None (independent of U1; the CSV seed can run before or after the brand_search_terms populate)

**Files:**

- Create: `x-monitoring/scripts/2026-06-25-005-seed-companies-brands-from-csv.py`
- Test: `x-monitoring/tests/test_seed_companies_brands_from_csv.py`

**Source data:** `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` — 17 columns A-Q, 20 data rows covering the 20 enabled brands in `config.yaml`. The script takes the CSV path as a positional CLI arg.

**Approach:**

- Top-level script: positional `db_path` and `csv_path` as `sys.argv[1]`, `sys.argv[2]`. Optional `--dry-run`, `--limit N` (process first N rows for testing).
- Hardcoded constants at the top of the script (operator can edit without diving into logic):
  - `COLUMNS` dict: maps field name → 0-based column index. R10 table.
  - `BRAND_SLUG_OVERRIDES` dict: display_name → brand_id (20 entries covering all 20 CSV rows: the 11 v1 brand_ids plus 9 new ones). Examples: `"千问": "qwen"`, `"MiniMax": "minimax"`, `"ERNIE / Wenxin": "ernie"`, `"Mimo": "xiaomi_mimo"`, `"Moonshot / Kimi": "moonshot_kimi"`, `"Llama": "llama"`, `"NeMo / Megatron": "nvidia_nemo"`, `"Doubao / Seed": "doubao"`, `"Yi": "yi"`, `"サカナAI": "sakana"`, `"업스테이지": "upstage"`. The implementer enumerates all 20 entries from the CSV's column B.
  - `COMPANY_SLUG_OVERRIDES` dict: display_name → company_id (12 entries mirroring the 11 existing v1 companies + minimax from migration 009).
  - `ROLE_MAP` dict: K → "official", L → "staff" (configurable if M and N later become role columns).
- Function `slugify(name: str, overrides: dict) -> str` — checks overrides first, falls back to `re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')`.
- Function `split_multivalue(cell: str) -> list[str]` — splits on `,` and/or whitespace runs, strips, filters empty.
- Function `parse_hf_url(url: str) -> str | None` — extracts namespace; returns None if URL malformed.
- Function `parse_x_url(url: str) -> str | None` — extracts handle; strips trailing `;`, `,`, `/`; returns None if URL malformed.
- Function `parse_followers(cell: str) -> int` — strips `,` (e.g., `"38,400"` → `38400`); returns 0 on parse error.
- Main block:
  1. Open `sqlite3.connect(db_path)` with `PRAGMA foreign_keys = ON`.
  2. Read CSV with `csv.reader`. First row is header (validate against the expected 17 columns; error with clear message if mismatched). Skip header.
  3. For each row (or first `--limit N`):
     a. Extract single-value fields (B, C, D, E, F, G, H). Apply slugify to B → brand_id, to E → company_id. Column M (notes) is read and discarded.
     b. Split multi-value K (official X URLs) and L (staff X URLs).
     c. Split multi-value O (HF URLs). Parse each → namespace.
     d. INSERT OR IGNORE `companies` (company_id, display_name=E, display_name_en=F, display_name_zh_cn=G, hq_country=H, created_at=now).
     e. INSERT OR IGNORE `brands` (brand_id, display_name=B, display_name_en=C, display_name_zh_cn=D, accent_color='#9ca3af', is_sentinel=0, created_at=now). Do NOT write `notes` from column M — the column is ignored.
     f. INSERT OR IGNORE `brands_companies` (brand_id, company_id, ownership_pct=1.0).
     g. For each HF URL from O: INSERT OR IGNORE `hf_orgs` (id=namespace, company_id, confirmed=1, discovered_via='curated', added_at=now).
     h. For each X URL from K: parse handle; INSERT OR IGNORE `accounts` (author_id=slug-of-handle, handle=handle, verified=0, bio_contains_brand=0, engagement_tier='low', first_seen_at=now, last_seen_at=now); INSERT OR IGNORE `brands_accounts` (brand_id, author_id, role='official', added_at=now).
     i. For each X URL from L: same as K but role='staff'.
     j. Track new-row counts per table in a `Counter`.
     k. Wrap the row in a `conn.commit()` (one transaction per row is fine for 20 rows; a single batch commit at the end is also acceptable).
  4. After loop: print summary table (per-table new-row counts, total).
- `--dry-run`: print the planned (brand_id, company_id, hf_namespace, x_handle, role) per row, no writes, exit 0.
- Idempotency: all INSERTs are `INSERT OR IGNORE`. Re-running on the same DB inserts 0 new rows (the 11 v1 brand_ids are reused; the 9 new ones are seeded on first run).
- Imports: `import csv, sqlite3, sys, re, argparse` (use `argparse` for cleaner CLI than `sys.argv` parsing).

**Test scenarios:**

- Happy path: a 5-row mini-CSV (in `tmp_path/`) → 5 companies, 5 brands, 5 brands_companies edges, N accounts/brands_accounts, N hf_orgs.
- Multi-value split: K with `, ` separator, O with whitespace separator.
- URL parsing: `https://x.com/MiniMax_AI,` (trailing comma) → handle `MiniMax_AI`. `https://x.com/01AI_Yi;` (trailing semicolon) → handle `01AI_Yi`. `https://huggingface.co/MiniMaxAI/MiniMax-M1` → namespace `MiniMaxAI`.
- Slug override: `千问` → `qwen` (via override); `MiniMax` → `minimax` (via override); `Mimo` → `xiaomi_mimo` (via override); `サカナAI` → `sakana` (via override); `업스테이지` → `upstage` (via override).
- CJK display names: brand_id is still snake_case (override), but display_name preserves CJK (`千问`, `零一万物 Yi`, `腾讯混元`).
- Idempotency: running twice against the same DB inserts 0 new rows on the second run.
- Dry-run: with `--dry-run`, the script makes zero writes (count rows before/after).
- `--limit 3`: processes only 3 rows.
- Trailing junk: a row with K=`https://x.com/A;, https://x.com/B,` (trailing punctuation) parses to `['A', 'B']`, not `['A;', 'B,']`.
- HF URL with extra path: `https://huggingface.co/MiniMaxAI/MiniMax-M1` parses to `MiniMaxAI` (only the namespace), not `MiniMax-M1`.
- Empty optional columns: a row with N=empty (no github) and L=empty (no staff) does not error; only K is processed.

**Verification:**

- `python3 scripts/2026-06-25-005-seed-companies-brands-from-csv.py data/x_monitoring.db docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv --dry-run --limit 5` prints the planned writes and exits 0.
- Without `--dry-run`, the same command populates the DB and exits 0.
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands"` returns 20.
- `sqlite3 data/x_monitoring.db "SELECT brand_id, display_name FROM brands ORDER BY brand_id"` shows the 11 v1 brand_ids reused (`minimax`, `qwen`, `deepseek`, `glm`, `xiaomi_mimo`, `moonshot_kimi`, `inclusionai`, `mistral`, `stepfun`, `ernie`, `hunyuan`) + 9 new (`llama`, `nvidia_nemo`, `doubao`, `yi`, `sensechat`, `exaone`, `kuaishou`, `sakana`, `upstage`) = 20 rows total.
- `sqlite3 data/x_monitoring.db "SELECT brand_id, role, COUNT(*) FROM brands_accounts GROUP BY brand_id, role"` shows non-zero counts for both `official` and `staff` for most brands.
- `sqlite3 data/x_monitoring.db "SELECT id, company_id FROM hf_orgs ORDER BY id"` shows the 11 existing HF namespaces + new ones from O (e.g., `meta-llama`, `mistralai`, `nvidia`, `bytedance`, `bytedance-research`, `moonshotai`, `01-ai`, `inclusionAI`, `SenseTime`, `stepfun-ai`, `XiaomiMiMo`, `LGAI-EXAONE`, `SakanaAI`, `Kuaishou`, `upstage`).
- Re-running exits 0 and inserts 0 new rows.
- The new test file passes in isolation: `pytest x-monitoring/tests/test_seed_companies_brands_from_csv.py -v`.

- [ ] **Unit 4: Test file `tests/test_seed_companies_brands_from_csv.py`**

**Goal:** Cover the pure parsing functions (slugify, split_multivalue, parse_hf_url, parse_x_url, parse_followers) and the seed script's row logic (integration via a mini-CSV in `tmp_path`).

**Requirements:** R14

**Dependencies:** Unit 3

**Files:**

- Create: `x-monitoring/tests/test_seed_companies_brands_from_csv.py`

**Approach:**

- Pure-function tests for `slugify(name, overrides)`:
  - Override hit: `slugify("千问", {"千问": "qwen"})` → `qwen`. Tests must also include all 11 v1 brand_ids (round-trip via override) and 9 new brand_ids (slug-derived for non-CJK, override for CJK/Japanese/Korean).
  - Override miss: `slugify("Some New Brand", {})` → `some_new_brand`.
  - CJK fallback: `slugify("百度", {})` → `baidu` (per the regex lowercasing CJK to its base form, no — actually CJK is not `[a-z0-9]` so this is empty; test for the correct behavior, which is to require an override for pure-CJK names).
  - Hyphen + slash: `slugify("ERNIE / Wenxin", {"ERNIE / Wenxin": "ernie"})` → `ernie`.
- Pure-function tests for `split_multivalue(cell)`:
  - Comma-separated: `"A, B, C"` → `['A', 'B', 'C']`.
  - Whitespace-separated: `"A   B   C"` → `['A', 'B', 'C']`.
  - Mixed: `"A, B C"` → `['A', 'B', 'C']`.
  - Trailing junk: `"A,, B,"` → `['A', 'B']`.
  - Empty: `""` → `[]`.
- Pure-function tests for `parse_hf_url(url)`:
  - Standard: `https://huggingface.co/MiniMaxAI/` → `MiniMaxAI`.
  - With model: `https://huggingface.co/MiniMaxAI/MiniMax-M1` → `MiniMaxAI`.
  - Malformed: `not-a-url` → `None`.
- Pure-function tests for `parse_x_url(url)`:
  - Standard: `https://x.com/MiniMax_AI` → `MiniMax_AI`.
  - With trailing semicolon: `https://x.com/01AI_Yi;` → `01AI_Yi`.
  - With trailing comma: `https://x.com/X,` → `X`.
  - Twitter domain: `https://twitter.com/X` → `X`.
  - Malformed: `not-a-url` → `None`.
- Pure-function tests for `parse_followers(cell)`:
  - `"38,400"` → `38400`.
  - `"100"` → `100`.
  - `""` → `0`.
  - `"abc"` → `0` (defensive).
- Integration test: build a 5-row mini-CSV in `tmp_path/test.csv` (header + 5 rows, mirroring the structure of the real CSV), call `seed_from_csv(tmp_db, csv_path, dry_run=False, limit=None)`, then assert:
  - `SELECT COUNT(*) FROM brands` == 5.
  - `SELECT brand_id, display_name FROM brands WHERE brand_id = 'qwen'` shows the override mapping.
  - `SELECT COUNT(*) FROM brands_accounts WHERE role = 'official'` ≥ 5 (one per row, possibly more if multi-value).
  - `SELECT COUNT(*) FROM brands_accounts WHERE role = 'staff'` ≥ 3 (some rows have staff).
  - `SELECT id, company_id FROM hf_orgs` shows the parsed HF namespaces.
- Idempotency: call `seed_from_csv` twice against the same `tmp_db`; assert row counts unchanged on the second call.
- Dry-run: call with `dry_run=True`; assert no rows added; assert the printed plan includes expected brands.
- `--limit 3`: call with `limit=3`; assert exactly 3 brand rows added.
- The test for the "CJK fallback produces empty slug" should `pytest.raises(ValueError)` if the script is called with a CJK brand that has no override — the script should refuse to write a brand with an empty id, and the test should assert the failure mode.

**Verification:**

- `pytest x-monitoring/tests/test_seed_companies_brands_from_csv.py -v` — all tests pass.
- The new test file does not regress any existing test.

## System-Wide Impact

- **Interaction graph (U1):** populate script → `brands` table (writes) + `brand_search_terms` table (writes) → next live cycle's `_load_brand_search_terms_from_db` (reads) → `extract_search_term_match` (reads) → `MentionRow` (writes). The populate is a one-way boot-strap; the live cycle is unchanged.
- **Interaction graph (U3):** CSV seed script → `companies` + `brands` + `brands_companies` + `accounts` + `brands_accounts` + `hf_orgs` tables (writes) → next live cycle's `Store.read_brands()`, `read_brand_search_terms()`, `read_brand_accounts()` (reads) → dashboard brand selector (reads). All 6 tables are downstream consumers; no cycle-time change.
- **Error propagation (U1):** the script's drift-zero check is the "all writes succeeded" signal. A non-zero drift means either a yaml was unreadable (warning, not exit-1) or a brand row could not be created (FK violation, exit-1).
- **Error propagation (U3):** a header mismatch exits with a clear error before any writes. A row with an empty brand_slug (CJK with no override) raises and aborts the row, but the script continues with the next row. An FK violation on `brands_companies` (missing company) raises and aborts.
- **State lifecycle:** `brand_search_terms` rows persist indefinitely (U1). The 6 company/brand tables persist indefinitely (U3). There is no TTL or refresh job. The operator re-runs the scripts after adding tokens to a yaml or after a new CSV batch; existing rows are preserved.
- **API surface parity:** `extract_search_term_match`'s casefold fallback means a populate with mixed-case terms is correct. The U3 seed reuses existing `read_*` API; no API change.
- **Integration coverage (U1):** the script's drift check re-uses the live cycle's drift check, so any divergence between the populate and the live cycle is impossible by construction.
- **Integration coverage (U3):** the override map covers the 11 v1 brand_ids so the seed is backward-compatible with the 1,522 historical `accounts` rows. The 9 new brand_ids have no historical `posts` rows yet (they were never queried before), so the seed does not collide with existing attribution data.
- **Operator runbook effect:** after both scripts run, the drift check log noise goes away (U1) and the dashboard brand selector shows 20 brands (U3).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Token extraction drifts from `query_plan._load_brand_tokens_per_model` | Both files share the R2 "byte-for-byte" requirement. Test U2 covers the parser independently; a divergence shows up immediately. |
| Operator runs the script before the new tokens from plan 2026-06-25-001 are merged | Plan 2026-06-25-001 is already on main as of 2026-06-25 14:33 (commit 674fa8a). This plan assumes that is true. If not, the script is still safe (it just populates fewer tokens). |
| Display name / accent color for the 9 new brands are wrong | R4 is explicit: "first-pass placeholders." Operator follows up with a small backfill script (same pattern as the i18n display_name backfill) to refine. The populate does not block on this. |
| Future plan makes `brand_search_terms` canonical and reverses the flow | This plan's populate script is forward-compatible: when the canonical direction flips, the script becomes the "yaml-emit" step (using the same `_extract_tokens` style, but reversed). The token set in the DB is the source of truth either way. |
| `config.yaml::enabled_models` order or contents change between when this plan lands and when the operator runs the script | The script reads `enabled_models` from `config.yaml` at runtime (preferred) or hardcodes the 20 brand_ids (fallback). If hardcoded, the script must be re-run after any `enabled_models` change. |
| Historical posts still have `MentionRow(brand_id=None, source="search_term")` after the populate | Expected. The populate only fixes the lookup table; historical posts need a re-run of `x_monitor reattribute` (U3 of the call-path attribution plan) to materialize the brand_id from the now-populated map. Out of scope here. |
| U3 CSV column mapping is wrong (R10) | The implementer MUST validate the column indices against the actual header in `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` before merging. A header mismatch exits with a clear error. The override map is hardcoded at the top of the script and reviewed by the operator on first run. |
| U3 brand_id collisions with existing v1 brand_ids (R12) | The override map covers the 11 v1 brand_ids that match the CSV's display_names (`minimax`, `qwen`, `deepseek`, `glm`, `xiaomi_mimo`, `moonshot_kimi`, `inclusionai`, `mistral`, `stepfun`, `ernie`, `hunyuan`). The 9 new brand_ids are slug-derived; the dry-run prints the planned slugs so the operator can review before committing. The script refuses to insert a brand with an empty slug (raises). |
| U3 column O (hf_orgs) uses whitespace as separator instead of comma (R11) | The `split_multivalue` function handles both `,` and whitespace. The data shows `https://huggingface.co/bytedance/   https://huggingface.co/bytedance-research/` — the script must split on runs of whitespace, not just `,`. |
| U3 trailing punctuation in K/L (e.g. `https://x.com/01AI_Yi;`) | The `parse_x_url` function strips trailing `;`, `,`, `/`. The unit test in U4 covers this edge case. |
| CJK brand names produce empty slugs (e.g. `百度` → `` after regex) | The override map covers all CJK display names in the CSV. The script refuses to insert a brand with an empty slug. |

**Dependencies:** Plan 2026-06-25-001 (Call B/C token widening) must be on main (it is). For U3, the 6 target tables must exist (they do, per migration 004 + 009 + 010).

## Future Work (deferred to a follow-up plan)

When the user is ready to make `brand_search_terms` canonical:

1. **Reverse script** `scripts/<date>-emit-yaml-from-brand-search-terms.py` — read `brand_search_terms`, group by `brand_id`, emit `data/queries/<brand_id>.yaml` in the existing shape (Q1-Q6, brand paren first, then the (how|...) etc. secondaries). The secondaries are NOT in `brand_search_terms`; that data lives in the plan / operator's head. Two options:
   - A. Store the secondaries in a new table (`brand_query_templates`) — bigger change.
   - B. Use the existing yamls as a "secondaries template" and only update the brand paren group — simpler. Recommended.
2. **CI check** — a `make check-yaml-db-coverage` that runs the populate in dry-run mode and fails if drift > 0. Prevents future yaml edits from drifting the DB.
3. **Re-attribute historical posts** — run `x_monitor reattribute` once after the populate (or after the canonical flip) so all 2,008+ historical posts get the search-term brand link materialized.

When the user is ready to expand the U3 CSV seed (additional fields):

4. **Tier column** — `brands.tier` (T1-closed / T2-bigtech / etc.) requires a new column. Defer to a follow-up that adds `brands.tier TEXT` and backfills from CSV column Q.
5. **github_accounts** — `brands_github_orgs` table for column N. Defer to a follow-up that creates the table and backfills.
6. **`products` table seeding** — column A (products) is multi-value model SKUs. Seeding the `products` table (per migration 009) requires repo_id, brand_id, hf_org_id, and other HF API data. The CSV's column A is human-curated product names (not repo_ids), so this would require either: (a) a manual mapping CSV from product name → repo_id, or (b) a separate HF products crawler (the existing `run_hf_products.sh` script). Out of scope for this plan.
7. **`companies_accounts` seeding** — derive from `brands_accounts → brands_companies` joins. The application populates this in the normal account_graph pass; no separate seed needed.

## Documentation / Operational Notes

- The script's docstring must reference migration 017 as the contract authority.
- Operator note: re-run the script whenever a yaml's brand-token list changes (new model variant, new alias, removed alias). The drift-zero exit is the success signal.
- Operator note: the 9 new brand display_names and accent_colors are placeholders — refine with a follow-up backfill.
- Operator note: do not edit `brand_search_terms` rows by hand in production. The script is the only supported write path; manual edits will be re-overwritten on the next run (or, if the term is no longer in the yaml, persist as drift).
- The drift check log noise goes away on the next cycle after the populate runs.

## Sources & References

- **Origin contract:** `x-monitoring/x_monitor/migrations/017_brand_search_terms_hybrid.sql` — the hybrid-by-design documentation.
- **Related code:** `x_monitor/query_plan.py:169-211` (`_load_brand_tokens_per_model`), `x_monitor/attribution.py:531-594` (`extract_search_term_match`), `x_monitor/store.py:1517-1526` (`read_brand_search_terms`), `x_monitor/run.py:316-347` (`_log_brand_search_terms_drift`).
- **Schema:** `x_monitor/migrations/004_company_brand_account_model.sql:40-90` — `companies`, `brands`, `brands_companies`, `brand_accounts`, `accounts`. `x_monitor/migrations/009_products.sql:60-118` — `hf_orgs` and `products`. `x_monitor/migrations/010_rename_mn_tables_to_plural_plural.sql` — `brand_companies` → `brands_companies`.
- **Existing tests:** `x-monitoring/tests/test_brand_search_terms_hybrid.py` — the contract test this plan's test file extends.
- **Script template:** `x-monitoring/scripts/2026-06-19-180000-seed-detection-tables.py` and `x-monitoring/scripts/2026-06-23-005-seed-enum-zh-cn-labels.py` — the operator-script pattern.
- **Prior plan:** `docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md` Unit 7 (R7) — the contract land.
- **Token source plan:** `docs/plans/2026-06-25-001-refactor-b-and-c-calls-for-max-inclusion-plan.md` — the source of the 9 new brands and their expanded tokens.
- **CSV source:** `docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv` — the corrected first-batch 20-brand file, 17 columns A-Q, used as the U3 seed source.

---

*Plan generated 2026-06-25 from a read of the empty `brand_search_terms` table, the 20-yaml data/queries/ directory, and the existing hybrid-by-design contract in migration 017.*
