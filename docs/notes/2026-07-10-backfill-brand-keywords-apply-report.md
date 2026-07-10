# Plan 2026-07-10-001 apply report — brand_keywords backfill

**Generated:** 2026-07-10
**Plan:** `docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md`
**Live DB:** `data/x_monitoring.db` (74M, currently at migration v34)
**Pre-apply backup:** `data/x_monitoring.db.pre-mig034.20260710T061250Z.bak` (74M)
**Probe CSV (post-apply):** `docs/notes/probe_evidence/2026-07-10T061250Z-filter_yield_post_backfill.csv`

## Steps applied

### Step 1 — Migration 034

**Outcome: applied, 60 rows inserted.**

`x_monitor/migrations/034_backfill_brand_keywords_from_yaml.sql` ran cleanly via `Store.apply_migrations()`. The migration covers 13 brands (the "missing" set per the 2026-07-09 read): doubao, ernie, exaone, hunyuan, kuaishou, mimo, mistral, nemo_megatron, sakana_ai, sensechat, stepfun, upstage, yi. 60 INSERT OR IGNORE rows total.

Live DB went from migration v33 to v34.

### Step 2 — `scripts/backfill_brand_keywords.py`

**Outcome: 57 more rows inserted, 33 skipped (idempotency confirmed).**

```
backfill_brand_keywords — run report

  enabled brands:    20
  (brand, token) pairs parsed: 90
  inserted:          57
  skipped (existed): 33
```

The 33 skipped pairs are the overlap between migration 034's static snapshot and the script's runtime parser output (same parser, same source — they should match). The 57 inserted are tokens that migration 004 already seeded for some brands + the regex patterns from migration 029.

Pre/post row counts:

| Table | Before | After | Delta |
|---|---|---|---|
| `brand_keywords` total rows | 90 | 207 | +117 |
| `brand_keywords` distinct brands | 8 | 21 | +13 |
| `_migrations` version | 33 | 34 | +1 |

Per-brand coverage after backfill:

| brand | rows | brand | rows |
|---|---|---|---|
| deepseek | 14 | inclusionai | 13 |
| doubao | 11 | kuaishou | 5 |
| ernie | 4 | llama | 9 |
| exaone | 5 | mimo | 14 |
| glm | 17 | minimax | 14 |
| hunyuan | 6 | mistral | 4 |
| moonshot_kimi | 17 | nemo_megatron | 6 |
| qwen | 20 | sakana_ai | 7 |
| sensechat | 5 | stepfun | 4 |
| upstage | 12 | xiaomi_mimo | 10 |
| yi | 10 | | |

Every brand in `enabled_models` now has at least its Q2 paren-group tokens in the table.

### Step 3 — Probe rerun

**Outcome: B3 fully recovered (0/50 → 49/50), C2 partially recovered (1/50 → 5/50), B1/B2 also lifted significantly.**

Run: `python3 -m scripts.probe_filter_yield --max-results 50 --output /tmp/filter_yield_post_backfill.csv`

| Spec | Before (2026-07-09) | After (2026-07-10) | Δ kept |
|---|---|---|---|
| A | 2 | 3 | +1 |
| B1 | 12 | 40 | **+28** |
| B2 | 11 | 41 | **+30** |
| B3 | 0 | **49** | **+49** |
| C1 | 19 | 19 | 0 |
| C2 | 1 | **5** | **+4** |

#### B3 — fully recovered

The pre-backfill 0/50 was a probe-methodology bug, not a B3-spec bug (see `2026-07-09-b3-probe-methodology-bug` memory). B3's query is well-formed (310 chars, OR-of-5-brands), returns 50 hits. The 0 kept was the `_kept_after_filter` finding zero matches because `brand_keywords` had zero entries for the 5 B3 brands. After backfill, the index has 5-12 entries per B3 brand, so the kept count is now 49/50.

#### C2 — partially recovered, AND-filter still suspect

C2 went from 1/50 to 5/50. ERNIE gained 4 brand_keywords rows (`ERNIE`, `文心一言`), so the 1 → 5 lift comes from those. The remaining 5/50 is still low for a spec with 21 co-occurrence terms.

Possible remaining cause: the C2 AND-filter is too narrow even with full keyword coverage. The probe samples that didn't attribute to ERNIE may have been matching the co-occurrence terms but not containing `ERNIE` or `文心一言` literally — i.e., generic AI/LLM chatter passing the AND-filter without being about Baidu ERNIE specifically.

If C2 is meant to be a primary signal source for ERNIE, the next iteration should:
1. Tighten the AND-filter with disambiguators like `"百度"` and `Wenxin` (without space, to match `文心` more loosely).
2. OR add an explicit `attribute_to_brands` regex test for ERNIE to catch `ERNIE` / `文心` mentions.

This is now a separate follow-up tracked in `2026-07-09-c2-yield-probe-failure` memory.

#### B1/B2 — significant recovery

B1 (12 → 40) and B2 (11 → 41) saw similar lifts because their brand tokens were also missing for several brands (`doubao`, `mistral`, `stepfun`, `ernie`, `hunyuan`, `mimo`, `sensechat`, `yi` were all in the missing set). The probe's `_kept_after_filter` was silently dropping mentions of these brands even when the post text contained their tokens.

#### A/C1 — minimal change

A (list-based) and C1 (5 polysemous brands, both groups already had keyword coverage) saw small or no change. C1 unchanged at 19/50 confirms that the existing keyword coverage for the 5 C1 brands was already working.

### Step 4 — Tests

| Test file | Result |
|---|---|
| `tests/test_backfill_brand_keywords.py` | 8/8 passed |
| `tests/test_brand_search_terms_populate.py` | unchanged (pre-existing 1 failure unrelated to this plan) |
| `tests/test_call_c_specs.py` | unchanged (pre-existing 1 skipped, live-gated) |
| `tests/test_probe_filter_yield.py` | unchanged (pre-existing 2 failures unrelated to this plan) |

The pre-existing test failures (3 total) are unchanged — this plan does not touch the code paths those tests exercise.

## Summary of plan 2026-07-10-001 status

### Complete ✅

- [x] U1: `parse_brand_tokens` extracted from `_load_brand_tokens_per_model` in `x_monitor/query_plan.py`
- [x] U1: `_parse_first_paren_group` helper exposed for reuse
- [x] U1: `x_monitor/run.py` updated to import the renamed public function
- [x] U2: Migration 034 written + applied
- [x] U2: `scripts/backfill_brand_keywords.py` written + run on live DB
- [x] U2: 13 brands backfilled (90 → 207 rows; 8 → 21 brands covered)
- [x] U3: 8 hermetic tests pass
- [x] Apply: probe rerun shows B3 fully recovered (49/50), C2 partially recovered (5/50)

### Open (not blocking plan "done") ⚠️

- **C2 spec AND-filter** still yields 5/50 — separate follow-up tracked in `2026-07-09-c2-yield-probe-failure` memory. After this backfill, the AND-filter itself is the remaining gap.
- **Pre-existing test failures** in `test_brand_search_terms_populate.py` (1) and `test_probe_filter_yield.py` (2) — unrelated to this plan, not addressed.

### Plan DoD check

- [x] `parse_brand_tokens` extracted and is the public import path
- [x] Migration 034 applied (live DB at v34)
- [x] Backfill script run on live DB
- [x] All 20 enabled brands have ≥1 row in `brand_keywords`
- [x] Probe rerun shows expected kept-count recovery
- [x] 8/8 backfill tests pass
- [x] Apply report written
- [x] Probe evidence CSV committed

The `brand_keywords` table is now canonical for all 20 enabled brands plus the legacy `xiaomi_mimo` brand from before migration 030's rename. The probe's `_kept_after_filter` returns nonzero for posts mentioning any of those brands. Production `attribute_to_brands` (if it shares the same index) gets the same coverage.