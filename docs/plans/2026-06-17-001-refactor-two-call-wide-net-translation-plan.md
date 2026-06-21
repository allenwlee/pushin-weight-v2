---
title: x-monitor — 2-call wide-net fetch + post-fetch LLM translation
type: refactor
status: active
date: 2026-06-17
amended: 2026-06-17
amendment: Call A is now `list:`-based (not OR-chain) to bypass the X 512-character query length cap. Brand attribution uses Option 1 (author_handle against `data/accounts/<m>.yaml`). New config field `x_monitor_list_id` is required.
amended-2: 2026-06-17 — length cap, not operator cap. Empirical API probe refuted the "22-OR cap with paren-grouping escape hatch" claim that motivated v1.7. The actual limit is on character length (~512 chars, per docs.x.com), not operator count, and paren-grouping does NOT bypass it. See "Cap probe amendment (2026-06-17)" at end of plan. The 2-call design still works: Call A = 29 chars (real escape hatch via `list:`), Call B at 7 brands = 218 chars (well under 512). v1.6's "safe up to 21 brands" claim is wrong; real ceiling for Call B is ~15-17 brands × 3 tokens each.
origin: docs/reference/2026-06-16-194558-twitterapi-live-queries-by-model.md
---

# x-monitor — 2-call wide-net fetch + post-fetch LLM translation

**Target repo:** `minimax-marketing` (project root: `/Users/fuchitalee/development/minimax-marketing`); subproject `x-monitoring/`.

## Overview

Collapse the v1.6 OR-collapsed pipeline from 14 calls/cycle (7 account + 6 intent) to **2 calls/cycle** by:
1. **Call A** = a single `list:`-operator query that pulls any tweet authored by anyone in a curated public x.com list. The list contains all official + staff handles for all 7 enabled brands. The `list:` query is 29 characters regardless of how many handles are in the list — this is the **genuine escape hatch from the 512-character length cap** (the only viable way to get staff handle coverage in a single call without hitting the cap). **NOTE: this is NOT an "operator count" trick**; it's purely because the numeric list ID is a fixed ~12 chars.
2. **Call B** = one OR-chain (paren-grouped for readability) of all deduped brand tokens from `data/queries/<m>.yaml`. 7 brand groups + `min_faves:0` = 218 characters. ✓ Fits under the 512-char cap. **NOTE: paren-grouping is cosmetic, not functional** — it does not bypass the cap. See "Cap probe amendment (2026-06-17)" at end of plan for the empirical evidence.
3. **All signal classification moves to post-fetch** — `INTENT_BUCKETS` and `_split_brands_to_fit_cap` are deleted. `classify_signal` and `attribute_to_brand` are the only signal/brand paths.

Add an LLM-based post-fetch translation layer that produces `text_en` and `text_zh_cn` columns for every post the per-model filter keeps, so the dashboard can render idiomatically in either locale without relying on browser-side translation.

**Source cost reduction:** 14 → 2 calls/cycle, 210 credit floor → 30 credit floor/cycle (7× lower), plus the new translation cost. The translation cost is bounded by kept posts (post-filter), not raw API returns.

## Problem Frame

The 2026-06-16 live-query inventory (see origin doc) shows 7 account + 6 intent = 14 calls/cycle. The floor alone is 210 credits/cycle (15×15 minimum per call), giving a daily floor of ~20,160 credits (~$3/day, ~$91/month at $0.15/1k). The actual spend during news cycles doubles that. The intent-bucket calls exist only to scope X advanced-search to "brand × intent" intersections; all intent classification can run post-fetch via `classify_signal`.

Two structural problems with the current shape:
- **Call count is dominated by brand × intent intersections**, not by what we need. The per-model account call is already maximally collapsed within its 512-char length budget.
- **X's advanced-search 512-character length cap blocks the OR-chain approach to Call A.** With 1 official + 10 staff × 7 brands, a flat `from:H OR to:H ...` chain is 154+ OR tokens ≈ 1,500+ characters — silent fail. The `list:` operator is the documented bypass: one numeric list ID, ~12 characters, infinite handles.
- **Per-locale display relies on browser translation**, which produces poor CJK↔EN for short, technical, or name-laden posts (the exact content we collect). DevRel users are mixed English / Simplified Chinese; both groups need idiomatic rendering.

The refactor unifies the fetch to 2 calls/cycle using `list:`-based Call A, paren-grouped Call B, and adds a translation pass that's scoped to the kept set (not the raw API returns), so the translation cost scales with signal-quality output, not with API return volume.

## Requirements Trace

- R1. Per-cycle call count is **exactly 2** for the fetch phase, regardless of brand count.
- R2. No `INTENT_BUCKETS` constant in `query_plan.py`; the `call_kind` taxonomy collapses to `account` (Call A, `list:`-based) and `brand_wide` (Call B, paren-grouped OR chain).
- R3. Call A returns tweets authored by anyone in the curated public x.com list `x_monitor_list_id`. Call B returns tweets whose text contains any brand token, regardless of intent.
- R4. The per-model relevance filter (`relevance.py` + `data/filters/<m>.yaml`) still runs after fetch and still drives what lands in `posts`. The translation pass runs **after** the per-model filter so it only translates kept posts.
- R5. Each kept post has `text_en` and `text_zh_cn` columns populated (may be NULL when source already equals target locale or when translation is skipped).
- R6. The dashboard picks the display locale via a query/cookie param and renders `text_<locale>` for top-N posts, brand-tokens colorized, headlines (when present) preferred over both. Brand colorization runs in the rendered locale.
- R7. Schema version bumps: migration 003 adds `text_en`, `text_zh_cn`, `lang_detected` columns + indexes; old Q1–Q6 `source_query_id` values are replaced with the 2-value taxonomy (`ACCT`, `BRAND_WIDE`).
- R8. Daily credit floor for the fetch phase is 30 credits (2 × 15 minimum per call), down from 210.
- R9. Translation cost is bounded by the kept-post count per cycle (≤ a few hundred typical), not by the raw API return volume. Translation rate-limit and failure handling are explicit.
- R10. **Brand attribution uses Option 1:** `author_handle` is matched against `data/accounts/<m>.yaml::accounts + staff` (the existing source of truth). A compiled-regex fast-path handles the wide-net Call B path (one alternation regex over all deduped brand tokens, built once per cycle).

## Scope Boundaries

- **In scope:** `query_plan.py`, `run.py`, `intent_classifier.py` (attribution gets a regex fast-path; call-shape branch is gone), `store.py` (new migration + new methods), `dashboard.py` + templates (locale switching), `data/queries/<m>.yaml` (Q1–Q6 fields are kept on disk for brand-token sourcing; `INTENT_BUCKETS` is removed from the plan output but the query-yaml brand-tokens list is still the source of truth for the wide-net OR-chain), `config.yaml` + `Config` (new required field `x_monitor_list_id`), test fixtures.
- **Out of scope:** Headline translation (the `headline` column stays English-source), browser-side language detection, per-post UI for forcing a specific translation, re-translation of historical posts, multi-locale storage beyond en + zh-CN (Japanese/Korean deferred), x.com mega-list creation/curation tooling (the operator creates the list in the x.com UI; the plan only consumes the list ID).
- **Not changing:** The `data/accounts/<m>.yaml` shape (still `accounts:` + `staff:`), the per-model filter `data/filters/<m>.yaml` shape, the review queue, the LaunchAgent cadence, the per-model `min_faves` knobs (migrate them to a single per-model `min_faves` config — see Decision 7).

## Context & Research

### Relevant Code and Patterns

- **`x_monitor/query_plan.py`** — current source of truth for call shape. `INTENT_BUCKETS` (line 45–69) and `_split_brands_to_fit_cap` (line 138–165) are the two constructs to retire. `plan_calls` (line 205–278) keeps the structure but emits only 2 calls: one `list:`-based account query, one paren-grouped brand-wide query.
- **`x_monitor/intent_classifier.py`** — `classify_signal` and `attribute_to_brand` stay. They are post-fetch and now become the only signal/brand attribution path. `attribute_to_brand` gets a **compiled-regex fast-path**: a single `re.compile(r"\b(?:MiniMax|海螺|Hailuo|Qwen|通义|...)\b", re.IGNORECASE)` over all deduped brand tokens is built once per cycle and used for the wide-net Call B path. The current Python-loop path stays for the author-handle-priority branch. Author-handle attribution is still first-priority.
- **`x_monitor/run.py`** — the `execute()` loop iterates `plan_calls(...)`. The intent-call branch (line ~420–445) collapses; both calls now stamp `source_query_id` differently (`ACCT` for Call A, `BRAND_WIDE` for Call B) and route every result through `attribute_to_brand`. The per-model filter handles brand-specific gating; the post-filter translation pass is the new end-of-cycle step.
- **`x_monitor/accounts.py::load_staff` / `load_accounts`** — the staff-list source for brand attribution. The x.com mega-list is the query-side filter; `data/accounts/<m>.yaml` is the attribution source of truth. They must stay in sync; the new unit test asserts this (the test compares the union of `accounts + staff` across all enabled models to the x.com list — at minimum, every yaml-listed handle should be in the x.com list; handles in x.com but not in the yaml are tolerated as a soft drift warning).
- **`x_monitor/store.py::insert_posts`** — already idempotent. New: 3 new columns on `posts` (`text_en`, `text_zh_cn`, `lang_detected`), 1 new column on summary (`translation_stats`). New helper `bulk_update_translations(rows)` that batch-updates translations for a set of tweet_ids. New `get_posts_missing_translations(locale, limit)` for the backfill subcommand.
- **`x_monitor/dashboard.py::serialize_grid_card`** — adds `display_locale` (from `?locale=` query param or `locale` cookie, defaulting to `en`). New helper `_pick_text(post, locale)` returns `text_<locale>` when present, else `text`. `top3_24h`/`top3_7d` use `_pick_text`. The `brand_colorize` filter continues to work on the chosen locale's text.
- **`x_monitor/templates/grid.html.j2`** — adds a locale switcher in the topbar (en | zh-CN links that set the cookie + refresh). The 30s polling endpoint (`/api/grid.html`) reads the cookie and re-renders. The htmx poll also propagates the locale via a hidden input.
- **`x_monitor/__main__.py`** — new subcommand `x-monitor translate` that re-runs the translation pass over posts that have NULL `text_en` or NULL `text_zh_cn`. The end-of-run translation pass is the default path; the subcommand is the recovery/backfill path.

### Institutional Learnings

- **`x-monitor v1.6 plan (2026-06-07-001)`** — already collapsed calls vs. the original 6×9 = 42-call shape. The 14-call v1.6 was the best X would let us do given the per-call OR cap. v1.7 collapses further using `list:` to bypass the cap for Call A, and paren-grouping for Call B.
- **Top-gun agent attribution (2026-06-08 plan)** — used a 2-pass deterministic-then-ML pattern; the same shape applies here (post-fetch deterministic brand attribution via compiled regex + LLM translation). The LLM is the *post* step, not the gating step.
- **Translation cost vs. browser translation** — never rely on browser translation for short, technical, name-laden content; the failure mode is silent (looks like it works, but loses "MiniMax-M3" and "海螺" subtleties). This is the explicit user-stated reason for the change.
- **TwitterAPI.io 15-credit floor per call** — confirmed in the 2026-06-16 inventory doc; reducing 14 → 2 calls cuts the per-cycle floor 7× even before the per-return surcharge.

### External References

- **X advanced search `list:` operator** — `list:listID` pulls tweets from a public list, with the query string staying tiny (numeric ID is ~12 chars) regardless of list size. This is the **only viable escape hatch from the 512-character length cap** for staff-handle coverage. Quoted from the 2026 cheatsheet: *"`list:listID` — Tweets from a public list. Example: `list:108534289`"*. TwitterAPI.io's advanced-search "operator vocabulary matches the one powering twitter.com's search box," so `list:` works in TwitterAPI.io queries. Sources: [TweetFinder 2026 cheatsheet](https://www.tweetfinder.io/blog/twitter-search-operators-cheatsheet), [ExportData cheatsheet](https://www.exportdata.io/blog/advanced-twitter-search-operators/).
- **X 512-character length cap with silent-fail behavior** — confirmed via direct API probe 2026-06-17 (boundary 509 → 520 chars). Per [docs.x.com](https://docs.x.com/x-api/posts/search/integrate/operators), this is the documented limit for self-serve recent search. Over-cap queries return HTTP 200 with `tweets: []` (no error code, no `msg`, no 4xx). **The "22-OR operator cap" claim from community sources (TweetFinder, getxapi, ExportData, Unfollr, igorbrigadir) is empirically false** in the sense that motivated v1.6 / v1.7's design — it's an artifact of the character cap hitting queries of average token length. The getxapi.com claim that "(a OR b OR c) counts as one expression rather than three separate operators" is **also false** in the sense that motivated the v1.7 design: paren grouping does not bypass the cap. The 7-brand paren-grouped Call B fits under the cap (218 chars) **because 218 < 512**, not because "8 operators < 22 operators."
- **Claude Haiku 4.5** for translation — best cost/latency for short CJK↔EN technical text. Pricing ~$1/MTok input, $5/MTok output. A typical 200-char tweet ≈ 200 tokens, so 1,000 kept posts ≈ $0.005 per locale — trivial. Decision: use Haiku unless operator asks for Opus. Source: fuchitalee gateway already has `ANTHROPIC_API_KEY` in `~/.env.secrets` (referenced in `gh_auth_secrets_hosts` institutional memory).
- **TwitterAPI.io `lang:` operator** — not used. The user explicitly wants translation handled server-side; a `lang:en` or `lang:zh` filter would shrink the returned set but lose cross-language context. We let Call B return everything and translate post-fetch.

## Key Technical Decisions

1. **Two-call shape using `list:` and paren-grouping.**
   - **Call A** = `(list:x_monitor_list_id) min_faves:1`. The list is a single public x.com list curated by the operator to contain all official + staff handles across all 7 enabled brands. `list:` counts as 1 operator; the whole Call A is 2 operators.
   - **Call B** = `((BrandTok1a OR BrandTok1b) OR (BrandTok2a) OR ...) min_faves:0`. 7 brand groups + `min_faves:` = **218 characters** at the current 7-brand token set. Fits well under the 512-char length cap. (Paren grouping is kept for readability; an ungrouped `a OR b OR c OR d...` form would be ~28 chars shorter but harder to read.)
   - **Why not a flat OR-chain for Call A?** Because the OR-chain math: 1 official + 10 staff × 7 brands = 77 handles × 2 (`from:` + `to:`) + 153 ORs = ~307 operators. **Silent fail.** The OR-chain was the v1.6 design; `list:` is the v1.7 escape.
   - **Why not a paren-grouped union for Call A?** `(from:H1 OR to:H1) (from:H2 OR to:H2) ...` is **AND** in X advanced search (intersection, not union). Wrong shape.
2. **Post-fetch is the only signal/brand attribution.** `attribute_to_brand` is the only path from "tweet text/author" to `model_id`. For both calls, author-handle match is first-priority (cheap; `account + staff` lookup in O(brand_count × handle_count) — at 7 × 11 = 77 handles, sub-microsecond). Text-contains is the wide-net fallback (Call B always hits this; Call A may hit it for non-staff replies). `classify_signal` is the only path to signal. The `_qid_to_signal` and `expected_signal` machinery in `run.py` and `query_plan.py` is replaced with a single `signal` column on `posts` (set post-fetch) and a single `source_query_id` per call (`ACCT` or `BRAND_WIDE`).
3. **Compiled-regex fast-path for wide-net brand attribution.** Today `attribute_to_brand` runs a Python loop over `brand_tokens` per tweet. With Call B returning ~50–200 tweets and 21 deduped brand tokens across 7 brands, that's ~4,200 iterations/cycle. A single `re.compile(r"(?:\bMiniMax\b|\b海螺\b|...)", re.IGNORECASE)` built once per cycle does the same work in 200 regex matches. Sub-millisecond. The fast-path is used only when no author-handle match fires (i.e., for Call B tweets that aren't from staff).
4. **Translation runs after the per-model filter.** The fetch → per-model relevance filter → translate sequence means we never translate dropped posts. This bounds translation cost to the kept set, not the raw API returns. The filter's "kept" status is the only signal needed; we do not translate soft-dropped review-queue entries (operator can resolve and re-run translate).
5. **Translation columns on `posts`, not a sidecar table.** `text_en TEXT`, `text_zh_cn TEXT`, `lang_detected TEXT` (ISO 639-1 + optional script, e.g., `zh-Hans`, `en`, `ja`). The dashboard's `_pick_text(post, locale)` reads the right column. NULL when the source already matches the target locale (the translation is a no-op) or when translation failed/skipped.
6. **Translation is LLM-driven via Claude Haiku.** Source language is detected by the LLM (prompt includes "If the text is already in {target_locale}, return it unchanged and set `noop: true`"). Output is structured JSON per tweet: `{tweet_id, lang_detected, text_en, text_zh_cn, noop_en, noop_zh}`. Batched at 20 tweets per request to amortize round-trips. Failures are non-fatal: a missing translation renders the source `text` with a "translation pending" badge, and `x-monitor translate` retries.
7. **x.com mega-list is curated manually, on a documented cadence.** The operator creates the list in the x.com UI (one-time). When `data/accounts/<m>.yaml::staff` gains a new handle, the operator adds it to the x.com list. The unit test for the list↔yaml sync (Unit 1's "Integration" scenario) runs on every dry-run and writes a `degraded:list_drift: [...]` entry to the run JSON if the union of `accounts + staff` doesn't match the x.com list membership we got back from Call A's first response. **This is a soft check, not a hard fail** — we don't have a way to enumerate x.com list members from the API, so the test compares the *known yaml set* to the *observed authors in the first Call A response*: if a yaml-listed handle is absent from the response for N consecutive cycles, raise a soft warning.
8. **Per-model `min_faves` migrates from per-query to per-model.** Today each of Q1–Q6 has its own `min_faves`. The new shape has one Call A (`min_faves:1`) and one Call B (`min_faves:0`); per-model `min_faves` lives in `data/filters/<m>.yaml` (a new top-level field) and the relevance filter applies it before insert.
9. **Skip-order config becomes a no-op.** `config.yaml::degraded_skip_order` and `Config.degraded_skip_order` lose their meaning with 2 calls. Decision: keep the field and validation in `Config` (don't break the schema) but `apply_skip_order` becomes a trivial "if 2 calls > budget, raise" guard.
10. **Dashboard locale switch is a topbar toggle.** `?locale=en|zh-CN` query param + a `locale` cookie. Default to `en` when unset. The 30s htmx poll preserves the locale via the cookie (the route reads the cookie on every poll). Brand colorization runs in the rendered locale. URL-only posts use the translated `headline` (English by default) for both locales; a follow-up can translate `headline` to zh-CN but is out of scope.
11. **Migration is forward-only, no backfill of translations.** New columns default to NULL. Old posts in the table keep `text` as the source; the dashboard falls back to `text` when `text_<locale>` is NULL and shows a subtle "(English source)" / "(中文原文)" badge so users know what they're seeing. A `x-monitor translate` backfill subcommand exists but is operator-initiated, not part of the cycle.

## Open Questions

### Resolved During Planning

- **Q: Can a single `list:`-operator query really replace the entire OR-chain Call A?**
  Resolution: Yes, per the 2026 cheatsheet. `list:listID` is 1 operator, pulls all tweets from a public list. The trade-off is that the list is public (X requires public lists for search); if the operator doesn't want staff membership to be visible, this is a privacy decision.
- **Q: Should Call B include a `lang:` filter to reduce return volume?**
  Resolution: No. The user explicitly asked for server-side translation; filtering by `lang:` would defeat the cross-language coverage that motivates the change. The translation cost is bounded by the kept set, not the raw return.
- **Q: Where does brand attribution live — `data/accounts/<m>.yaml` (Option 1) or `data/filters/<m>.yaml::canonical_handles` (Option 3)?**
  Resolution: Option 1. `data/accounts/<m>.yaml::accounts + staff` is the source of truth. Per-handle metadata (role, bio, engagement_tier) lives there; `attribute_to_brand` already reads it. Option 3 (using `filters::canonical_handles`) would conflate two concerns (relevance filter bypass + brand attribution) and create a 2-yaml drift risk.
- **Q: Should the new shape be a v2 of the plan doc, or an update to v1.6?**
  Resolution: New plan, since the call-shape and signal/brand-attribution pipeline change is a structural refactor (not a forward amendment). This is a `refactor` type plan.

### Deferred to Implementation

- **Q: How do we detect `accounts/<m>.yaml::staff` ↔ x.com list drift?**
  Defer to Unit 1's "list drift" integration test. Approach: on every dry-run, the first Call A response is sampled (e.g., 1 page of 20 tweets) and the set of `author_handle`s is compared to the union of `accounts + staff` across enabled models. If a yaml-listed handle is absent from the first response for 3 consecutive dry-runs, write a `degraded:list_drift: ["expected: alice_dev", ...]` entry to the run JSON. Hard fail is not appropriate (the x.com API doesn't expose list membership; we can't directly enumerate it).
- **Q: How long is the LLM-translation latency budget per cycle?**
  200 kept posts × 1 locale batch × 1 LLM call ≈ 1–3s at Haiku latency. We add a `translation_seconds` field to the run JSON and a soft deadline of 30s for the whole translation pass; if the deadline trips, the run completes with whatever was translated and the rest is backfilled.
- **Q: Should `x-monitor translate` be a separate subcommand or part of `cmd_run`?**
  Both. `cmd_run` translates at the end of each cycle (default). `x-monitor translate [--locale en|zh-CN|both] [--limit N]` is the recovery/backfill subcommand.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Data flow (single cycle)

```
                   ┌────────────────────────────────────────┐
                   │  plan_calls(data_dir, models,          │
                   │             x_monitor_list_id)         │
                   │  -> [CallA(ACCT, list:),               │
                   │     CallB(BRAND_WIDE, paren-groups)]   │
                   └────────────────────────────────────────┘
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
   Call A:  (list:1234567890)               Call B: ((BrandTok1a OR BrandTok1b)
             min_faves:1                              OR (BrandTok2a)
                                                     OR ...)
              ▲                                       ▲
              │ list: counts as 1                     │ 7 paren groups = 7
              │ operator regardless                    │ operators (X grouping
              │ of how many handles                    │ rule)
              ▼                                       ▼
   ┌────────────────────────┐              ┌────────────────────────┐
   │ n_tweets_from          │              │ n_tweets_from          │
   │ twitterapi.io          │              │ twitterapi.io          │
   │ (any author in list)   │              │ (any brand token match)│
   └────────────┬───────────┘              └────────────┬───────────┘
                │                                         │
                ▼                                         ▼
   attribute_to_brand:                      attribute_to_brand:
     1. author_handle match                   1. author_handle match
        against data/accounts/<m>.yaml           (rare — only staff
        .accounts + .staff                       who happen to mention
        (O(brand × handle_count))                a brand)
     2. (fallback) compiled regex            2. (almost always)
        alternation over deduped                compiled regex match
        brand tokens                            on the tweet text
                │                                         │
                └─────────────────┬───────────────────────┘
                                  ▼
                  classify_signal(text)  ->  posts.signal
                                  │
                                  ▼
                  per-model filter (relevance.py)
                  drop / keep / soft-drop -> review queue
                                  │
                                  ▼ (kept only)
                  LLM translate (Claude Haiku)
                  text -> {text_en, text_zh_cn, lang_detected}
                                  │
                                  ▼
                  store.insert_posts(kept_with_translations)
```

### Column additions to `posts`

```
ALTER TABLE posts ADD COLUMN text_en        TEXT;
ALTER TABLE posts ADD COLUMN text_zh_cn     TEXT;
ALTER TABLE posts ADD COLUMN lang_detected  TEXT;
-- source_query_id is repurposed to the 2-value taxonomy
-- ("ACCT" | "BRAND_WIDE"); a new "signal" column is added
-- to record the post-fetch classify_signal() result.
```

### `plan_calls` shape

> *Directional — the implementing agent will translate this into actual Python and verify the operator-cap math against the live API.*

```
def plan_calls(data_dir, enabled_models, *, x_monitor_list_id, operator_cap=22) -> list[PlannedCall]:
    handles = collect_all_official_and_staff_handles(data_dir, enabled_models)
    brand_tokens = collect_deduped_brand_tokens(data_dir, enabled_models)

    # Call A: one list: operator, 1+1=2 total operators
    a_query = f"(list:{x_monitor_list_id}) min_faves:1"
    assert_under_operator_cap(a_query)  # always passes; 2 < 22

    # Call B: 7 paren groups + 1 min_faves = 8 total operators
    b_query = compose_brand_wide_query(brand_tokens, enabled_models)
    assert_under_operator_cap(b_query)

    return [
        PlannedCall(call_kind="account",     model_id="*", bucket=None,
                    query_string=a_query, expected_signal="any",
                    n_operators=count_x_operators(a_query)),
        PlannedCall(call_kind="brand_wide",  model_id="*", bucket=None,
                    query_string=b_query, expected_signal="any",
                    n_operators=count_x_operators(b_query)),
    ]

def compose_brand_wide_query(brand_tokens, enabled_models) -> str:
    """Build the paren-grouped brand-wide query.

    One paren group per brand; each group is the brand's deduped token
    list joined with OR. Per X's grouping rule, each paren group counts
    as 1 operator regardless of how many tokens are inside.
    """
    groups = []
    for m in enabled_models:
        toks = brand_tokens.get(m, [])
        if not toks:
            continue
        groups.append("(" + " OR ".join(toks) + ")")
    return "(" + " OR ".join(groups) + ") min_faves:0"
```

### `attribute_to_brand` with compiled-regex fast-path

> *Directional — the implementing agent translates this into actual Python; the regex is built once per cycle, not per tweet.*

```
# Built once per cycle in RunPipeline.execute
_BRAND_REGEX = re.compile(
    r"(?:" + "|".join(re.escape(t) for t in deduped_brand_tokens) + r")",
    re.IGNORECASE,
)

def attribute_to_brand(text, author_handle, brand_tokens, staff_handles,
                      *, brand_regex=None) -> str | None:
    # 1. Author-handle priority (always first; O(brand × handle_count))
    h = (author_handle or "").casefold()
    for brand, handles in (staff_handles or {}).items():
        for hh in handles:
            if h and h == hh.casefold():
                return brand

    # 2. Text-contains, fast-path. If brand_regex is provided, use it.
    #    Otherwise fall back to the v1.6 dict-iteration path.
    if brand_regex is not None:
        m = brand_regex.search(text or "")
        if m is None:
            return None
        matched = m.group(0)
        # Look up which brand owns this token (the v1.6 dict-iteration
        # path's "first match in iteration order" semantic, but only over
        # the matched token instead of every token).
        return _brand_for_token(matched, brand_tokens)

    # v1.6 fallback (dict-iteration; same as today)
    t = (text or "").casefold()
    for brand, tokens in (brand_tokens or {}).items():
        for tok in tokens:
            ...
```

## Implementation Units

- [ ] **Unit 1: Collapse `query_plan.py` to 2 calls + retire `INTENT_BUCKETS` + add list-drift detection**

**Goal:** `plan_calls()` returns a 2-element list of `PlannedCall`; the intent-bucket constants and split logic are gone; the new `x_monitor_list_id` config field powers Call A.

**Requirements:** R1, R2, R3, R7 (source_query_id taxonomy), R8

**Dependencies:** None

**Files:**
- Modify: `x-monitoring/x_monitor/query_plan.py`
- Modify: `x-monitoring/x_monitor/config.py` — add `x_monitor_list_id: int` (required, validated to be a positive integer)
- Modify: `x-monitoring/config.yaml` — add `x_monitor_list_id: <numeric id>` (operator sets this after creating the x.com list)
- Modify: `x-monitoring/x_monitor/run.py` — pass `x_monitor_list_id` from config into `plan_calls(...)`; add list-drift detection (sample first Call A response, compare `author_handle`s to the union of `accounts + staff`)
- Modify: `x-monitoring/tests/test_run.py` (replace the v1.6 OR-collapse fixtures with the 2-call shape)
- Create: `x-monitoring/data/x_monitor_list.yaml` (optional) — a local mirror of the list membership for the drift test; if absent, the drift test runs in "best effort" mode (only checks yaml → response, not list → yaml)

**Approach:**
- Delete `INTENT_BUCKETS` constant and `_bucket_to_signal`.
- Delete `_split_brands_to_fit_cap` and `_compose_intent_query` (intent-call composition is gone).
- Keep `_extract_brand_tokens` and `_load_brand_tokens_per_model` — they are now the source of Call B's per-brand paren groups.
- Add `collect_all_official_and_staff_handles(data_dir, enabled_models) -> list[str]` (used by the list-drift test, not by the query shape).
- Add `compose_brand_wide_query(brand_tokens, enabled_models) -> str` that emits one paren group per brand (see High-Level Technical Design).
- Rewrite `plan_calls` to take `x_monitor_list_id: int` as a required arg and return `[CallA, CallB]`. The new `PlannedCall` no longer has a per-call `model_id` (the model is per-tweet, decided post-fetch); keep `model_id` as a string with value `"*"` for both calls.
- `PlannedCall.call_kind` Literal narrows to `("account", "brand_wide")`.
- List-drift detection: in `RunPipeline.execute`, after the first Call A response, build a set of `author_handle`s from the response, compare to the union of `accounts + staff` across enabled models, and write any yaml-listed handles missing from the response into `summary["degraded"]["list_drift"]` as a list. **Soft warning, not a hard fail** — the x.com list membership isn't visible from the API, so the only signal is "do my expected authors actually appear in the results."

**Execution note:** Add characterization coverage for `plan_calls` before changing the call shape — confirm the new shape matches a manual operator-cap math check (Call A = 2, Call B = 7+1 = 8).

**Technical design:** See High-Level Technical Design `plan_calls` shape above.

**Patterns to follow:** The existing v1.6 `plan_calls` structure (lines 205–278) is the template; we collapse, not invent.

**Test scenarios:**
- Happy path: `plan_calls(data, enabled_models, x_monitor_list_id=123)` returns exactly 2 calls; Call A = `(list:123) min_faves:1`, Call B has 7 paren groups.
- Happy path: Call A's `n_operators == 2`; Call B's `n_operators == 8` (7 groups + min_faves).
- Edge case: An `enabled_models` list with one brand whose `data/queries/<m>.yaml` is missing → that brand contributes 0 paren groups; Call B emits with the remaining brands' groups.
- Error path: `plan_calls(data, enabled_models)` without `x_monitor_list_id` raises `TypeError` (required arg).
- Error path: `plan_calls(data, enabled_models, x_monitor_list_id="abc")` raises `ValidationError` (must be int).
- Integration: A dry-run with a stub TwitterApiClient that returns no tweets from Call A (e.g., empty response) writes `degraded:list_drift: ["<every yaml-listed handle>"]` to the run JSON — the soft warning fires because the response is empty.
- Integration: A dry-run where Call A returns a `from:alice_dev` tweet (a yaml-listed staff) and `from:bob_random` (not in yaml) → no drift warning; `bob_random` is treated as a Call B result and goes through text-contains attribution.

**Verification:** `python -c "from x_monitor.query_plan import plan_calls; print(plan_calls(Path('data'), ['minimax','qwen','deepseek','glm','xiaomi_mimo','moonshot_kimi','inclusionai'], x_monitor_list_id=1234567890))"` prints exactly 2 entries; the first has `call_kind='account'` and `query_string='(list:1234567890) min_faves:1'`; the second has `call_kind='brand_wide'` and 7 paren groups. Run the full test suite — all 287+ tests pass, with updates to the v1.6 fixtures.

- [ ] **Unit 2: Update `run.py` to consume the 2-call shape + add compiled-regex fast-path to `attribute_to_brand`**

**Goal:** The per-cycle loop in `RunPipeline.execute` iterates the 2 calls; the intent-call branch is gone; both calls now route results through `attribute_to_brand` and `classify_signal`; the wide-net path uses a compiled regex built once per cycle.

**Requirements:** R2, R3, R4, R7, R10

**Dependencies:** Unit 1 (the new `plan_calls` shape)

**Files:**
- Modify: `x-monitoring/x_monitor/run.py`
- Modify: `x-monitoring/x_monitor/intent_classifier.py` — add the `brand_regex` fast-path arg to `attribute_to_brand`
- Modify: `x-monitoring/tests/test_run.py`
- Modify: `x-monitoring/tests/test_intent_classifier.py` (if it exists) or add new tests in `test_run.py`

**Approach:**
- Delete the intent-call branch (the section that runs `attribute_to_brand` only for `call.call_kind == "intent"`). For both calls, run `attribute_to_brand` on every returned tweet.
- Build a single compiled regex once per cycle: `re.compile("(?:" + "|".join(re.escape(t) for t in deduped_brand_tokens) + ")", re.IGNORECASE)`. Pass it as `brand_regex=` to `attribute_to_brand`. The author-handle priority branch runs first (cheap), and the regex is the fallback (one match per tweet max).
- Drop `_signal_to_qid` and the `source_query_id` mapping. `source_query_id` on each inserted post becomes the 2-value taxonomy: `ACCT` for Call A, `BRAND_WIDE` for Call B. Signal is recorded as a new `signal TEXT` column populated by `classify_signal`. (The new `signal` column is added in Unit 3; Unit 2's code can write to it as soon as Unit 3 is merged, but for backward-compatibility, Unit 2 also continues writing `source_query_id` as before.)
- Apply per-model `min_faves` from the new `data/filters/<m>.yaml::min_faves` field *after* the per-call `min_faves:0|1` baseline. Call A keeps `min_faves:1`; Call B uses `min_faves:0`; the per-model filter is the gating step.
- The `_planned_call_to_query` helper is updated: `call_kind == "account"` → `Query(id="Q1", ...)`; `call_kind == "brand_wide"` → `Query(id="Q5", ...)`. The dashboard's `_QID_TO_SIGNAL` mapping adds `ACCT → "release"`, `BRAND_WIDE → "other"`, and keeps the old `Q1..Q6` mappings for backward-compat with old posts.

**Execution note:** Integration test: run a fake cycle with a mock TwitterApiClient that returns 10 tweets across both calls, assert that all 10 get a `model_id` and `signal` set, and the `posts` table receives 10 rows with `source_query_id` in `{"ACCT", "BRAND_WIDE"}`.

**Patterns to follow:** The existing per-call loop in `execute()` is the template; collapse the 2 calls into the same loop body.

**Test scenarios:**
- Happy path: 10 tweets from Call A all have a `model_id` (author handle matches a staff list) and a `signal` (from `classify_signal`).
- Happy path: 10 tweets from Call B all have a `model_id` (regex fast-path matches a brand token) and a `signal`.
- Happy path: 200 tweets from Call B → exactly 1 compiled regex built at cycle start; the regex is reused for all 200.
- Edge case: A tweet from Call B whose text matches no brand token is dropped (existing `_unattributed` behavior).
- Edge case: A tweet whose text matches multiple brand tokens (e.g., "minimax and kimi" — author not staff) is attributed to the first match in `brand_tokens` iteration order.
- Error path: TwitterApiAuthError on Call A short-circuits the cycle (existing behavior); TwitterApiRateLimitError on Call B is logged and the run continues (existing behavior).
- Integration: After a 2-call cycle, `posts.source_query_id` distribution shows both `ACCT` and `BRAND_WIDE` (when both calls return tweets), or one of them (when one returns 0).

**Verification:** `python -m x_monitor dry-run` prints 2 entries in the run JSON's `queries` list (was 14). All v1.6 + new test_run.py tests pass.

- [ ] **Unit 3: Add `text_en` / `text_zh_cn` / `lang_detected` columns + migration 003**

**Goal:** Schema bumps to support per-locale rendering.

**Requirements:** R5, R7

**Dependencies:** None (can land before or in parallel with Units 1–2)

**Files:**
- Create: `x-monitoring/x_monitor/migrations/003_translation_columns.sql`
- Modify: `x-monitoring/x_monitor/store.py` — add `text_en`, `text_zh_cn`, `lang_detected`, and `signal` to `insert_posts` INSERT column list; add `bulk_update_translations(rows) -> int`; add `get_posts_missing_translations(locale, limit) -> list[dict]`.
- Modify: `x-monitoring/tests/test_store.py` — add migration-003 tests + bulk_update_translations tests.

**Approach:**
- Migration 003 SQL:
  ```
  ALTER TABLE posts ADD COLUMN text_en        TEXT;
  ALTER TABLE posts ADD COLUMN text_zh_cn     TEXT;
  ALTER TABLE posts ADD COLUMN lang_detected  TEXT;
  ALTER TABLE posts ADD COLUMN signal         TEXT;  -- new: post-fetch classify_signal() result
  CREATE INDEX IF NOT EXISTS idx_posts_lang_detected ON posts(lang_detected);
  CREATE INDEX IF NOT EXISTS idx_posts_text_en_null ON posts(tweet_id) WHERE text_en IS NULL;
  CREATE INDEX IF NOT EXISTS idx_posts_text_zh_null ON posts(tweet_id) WHERE text_zh_cn IS NULL;
  CREATE INDEX IF NOT EXISTS idx_posts_signal_model ON posts(model_id, signal);
  ```
- `insert_posts` is updated to accept the 4 new fields and pass them to the INSERT. Existing call sites that don't provide them get NULL.
- `bulk_update_translations(rows)` runs a single transaction with `UPDATE posts SET text_en=?, text_zh_cn=?, lang_detected=? WHERE tweet_id=?` for each row; returns the count of rows updated.
- `get_posts_missing_translations(locale, limit)` returns posts where `text_<locale>` IS NULL, ordered by `created_at DESC LIMIT N`. Backs the `x-monitor translate` backfill subcommand.

**Execution note:** The migration is forward-only and trivial; add a test that confirms the new columns are present after migration and that bulk_update_translations is idempotent.

**Patterns to follow:** The existing migration 002 (headline columns) is the template — same ALTER + partial-index pattern.

**Test scenarios:**
- Happy path: migration 003 applies cleanly on a fresh DB and on a DB that already has 001 + 002 applied.
- Happy path: `insert_posts` accepts a post with `text_en`/`text_zh_cn`/`lang_detected`/`signal` and stores all 4.
- Happy path: `bulk_update_translations` updates 5 rows in one transaction; idempotent re-run is a no-op.
- Edge case: `bulk_update_translations` with an empty list is a no-op (returns 0).
- Edge case: `bulk_update_translations` with a `tweet_id` that doesn't exist is silently skipped.
- Edge case: `get_posts_missing_translations("en", 100)` returns only posts with `text_en IS NULL`, ordered newest-first.
- Error path: A `bulk_update_translations` with a malformed row (missing `tweet_id`) raises KeyError before the transaction starts.

**Verification:** `python -m x_monitor migrate` shows `applied: [3]`. The test suite passes including the new migration test.

- [ ] **Unit 4: Add LLM translation pass to the run pipeline + CLI subcommand**

**Goal:** End-of-cycle translation of kept posts; `x-monitor translate` subcommand for backfill.

**Requirements:** R4, R5, R9

**Dependencies:** Unit 2 (the new run loop), Unit 3 (the new columns)

**Files:**
- Create: `x-monitoring/x_monitor/translator.py` — the Claude Haiku client, prompt templates, batching, error handling.
- Modify: `x-monitoring/x_monitor/run.py` — at the end of `execute()`, after all kept posts are inserted, call `translate_kept_posts(kept_all, ...)` and `bulk_update_translations`.
- Modify: `x-monitoring/x_monitor/__main__.py` — add `cmd_translate(args, paths)` and the argparse wiring.
- Modify: `x-monitoring/tests/test_run.py` — add end-of-cycle translation tests (with a fake LLM client).
- Create: `x-monitoring/tests/test_translator.py` — unit tests for the translator module (prompt structure, batching, error handling, noop detection).

**Approach:**
- `translator.py::translate_batch(tweets: list[dict], target_locales: list[str], client: ClaudeClient) -> list[dict]`:
  - Sends a single prompt with up to 20 tweets at a time; structured output `{results: [{tweet_id, text_en, text_zh_cn, lang_detected, noop_en, noop_zh}]}`.
  - Prompt template instructs the LLM to preserve URLs, @mentions, and brand/model names verbatim; translate everything else idiomatically; set `noop_<locale>: true` when the source already matches the target locale.
  - Retries on 429/5xx with exponential backoff (3 attempts); on final failure, returns the input unchanged and marks `text_<locale>` as NULL.
  - Has a `dry_run` mode that logs the prompt and a stub response without calling the LLM.
- The end-of-cycle call in `execute()` happens after `n_inserted` is computed, so the run JSON includes a `translation_stats` field (`n_translated`, `n_noop_en`, `n_noop_zh`, `n_failed`, `seconds`).
- The `x-monitor translate` subcommand:
  ```
  x-monitor translate [--locale en|zh-CN|both] [--limit 500] [--dry-run]
  ```
  Defaults: `--locale both`, `--limit 500`.

**Execution note:** Test the translator with a fake ClaudeClient that returns canned responses; do not hit the real API in unit tests.

**Patterns to follow:** The existing `RunPipeline.execute` shape (acquire lock, write summary, iterate calls, write summary) is the template. The translation pass slots in after the loop.

**Test scenarios:**
- Happy path: 20 kept posts → 1 LLM batch call → 20 rows in `posts` with `text_en`, `text_zh_cn`, `lang_detected` populated.
- Happy path: A Chinese-only tweet → `text_en` is the English translation, `text_zh_cn` equals the source (`noop_zh: true`).
- Happy path: An English-only tweet → `text_en` equals the source (`noop_en: true`), `text_zh_cn` is the Chinese translation.
- Edge case: An emoji-only tweet ("🤯") → both locales equal the source (both noop), `lang_detected` is the LLM's best guess.
- Edge case: A URL-only post is translated by the LLM (the URL is preserved; "no translation needed" is the LLM's call).
- Error path: LLM call returns 500 → retry; second 500 → retry; third 500 → mark as failed, log warning, continue.
- Error path: LLM call returns a malformed response → log warning, mark that tweet as failed, continue.
- Integration: `x-monitor translate --dry-run` prints the prompt and stub response without writing to the DB.
- Integration: After a run, `n_translated` in the run JSON equals the count of `bulk_update_translations` updates.

**Verification:** A real run with the gateway `ANTHROPIC_API_KEY` exports `text_en`/`text_zh_cn` for kept posts; `x-monitor translate --limit 100` on a backfill of 100 NULL-translation posts completes in <30s.

- [ ] **Unit 5: Dashboard locale switcher + per-locale rendering**

**Goal:** The dashboard renders in `en` or `zh-CN` based on a query/cookie; the locale toggle is visible in the topbar.

**Requirements:** R6

**Dependencies:** Unit 3 (the new columns exist)

**Files:**
- Modify: `x-monitoring/x_monitor/dashboard.py` — add `display_locale` arg to `serialize_grid_card`; add `_pick_text(post, locale)` helper; add `/api/set_locale` route that sets the cookie.
- Modify: `x-monitoring/x_monitor/templates/grid.html.j2` — add the locale switcher in the topbar (en | zh-CN links).
- Modify: `x-monitoring/x_monitor/templates/_model_card.html.j2` — top-3 post text rendering uses the chosen locale.
- Modify: `x-monitoring/x_monitor/static/dashboard.css` — locale switcher styling.
- Modify: `x-monitoring/x_monitor/static/dashboard.js` — handle the locale-toggle click.
- Modify: `x-monitoring/tests/test_dashboard.py` — add locale rendering tests.

**Approach:**
- `display_locale` is a new param to `serialize_grid_card`; the route reads it from `request.cookies.get("locale", "en")` and falls back to `"en"`.
- `_pick_text(post, locale) -> tuple[str, bool]` returns `(text, is_translated)`. The bool is False when the dashboard is showing the source `text` because the translation is NULL.
- The topbar adds: `<a href="?locale=en">EN</a> | <a href="?locale=zh-CN">中文</a>`. Alternatively, a small `<form method="POST" action="/api/set_locale">` for cookie-setting.
- The `_model_card.html.j2` template uses `p.display_text | brand_colorize` where `display_text` is `_pick_text`'s output.

**Execution note:** Add a unit test that confirms `_pick_text` falls back correctly when translations are NULL, and that `brand_colorize` works on both English and Chinese text.

**Patterns to follow:** The existing `serialize_grid_card` + `top3_posts` shape is the template; we add a parameter and a helper, not a new endpoint shape.

**Test scenarios:**
- Happy path: `serialize_grid_card(model_id, posts, display_locale="zh-CN")` returns `top3_7d[0].display_text` from `text_zh_cn`.
- Happy path: `serialize_grid_card(model_id, posts, display_locale="en")` returns `display_text` from `text_en`.
- Happy path: `serialize_grid_card(model_id, posts, display_locale="zh-CN")` with a post whose `text_zh_cn` is NULL falls back to `text` and sets `is_translated=False`.
- Edge case: A post with no `text`, no `text_en`, no `text_zh_cn` → `display_text` is empty string.
- Edge case: `display_locale="ja"` (unsupported) → defaults to `"en"` with a warning log.
- Integration: GET `/` with cookie `locale=zh-CN` renders the Chinese-locale template.
- Integration: POST `/api/set_locale` with `locale=zh-CN` sets the cookie and returns 200.

**Verification:** Open `http://localhost:5000/` in a browser; the topbar shows `EN | 中文`; clicking 中文 reloads with Chinese text; the toggle persists across the 30s htmx poll.

- [ ] **Unit 6: Retain `data/queries/<m>.yaml` as the brand-tokens source of truth; deprecate per-query fields**

**Goal:** The queries YAMLs stop driving the call shape (Unit 1 already did this) but stay in the repo as the canonical brand-token list, with the unused Q1–Q6 fields removed or marked vestigial.

**Requirements:** R1, R2

**Dependencies:** Unit 1 (queries are no longer shaped as Q1–Q6 calls)

**Files:**
- Modify: `x-monitoring/data/queries/<m>.yaml` (7 files) — restructure from `queries: [{id, query_string, ...}]` to `brand_tokens: [...]`.
- Modify: `x-monitoring/x_monitor/query_plan.py::_load_brand_tokens_per_model` — read the new shape.

**Approach:**
- The new YAML shape:
  ```
  brand_tokens:
    - MiniMax
    - 海螺
    - Hailuo
  ```
- A migration helper script (run once, checked in at `x-monitoring/data/queries/_migrate_to_brand_tokens.py`) reads the old `queries: []` list, extracts brand tokens from the Q2/Q3/Q5/Q6 paren groups (the existing `_extract_brand_tokens` helper does this), dedupes, and writes the new shape. Idempotent: re-running on a new-shape file is a no-op.

**Execution note:** Run the migration helper against the live `data/queries/` dir on fuchitalee; commit the result.

**Patterns to follow:** The existing 002 migration (headline columns) is the template for forward-only schema changes.

**Test scenarios:**
- Happy path: Each `data/queries/<m>.yaml` parses with the new shape (`brand_tokens: [...]` at the top level).
- Happy path: `_load_brand_tokens_per_model(data, ['minimax', 'qwen', ...])` returns the same brand-token list as the v1.6 version.
- Edge case: A `data/queries/<m>.yaml` with the old shape (no `brand_tokens` key) falls back to scanning `queries: []` for backward compat (logged as a deprecation warning).
- Error path: A `data/queries/<m>.yaml` with both old and new shapes → `brand_tokens` wins; the old `queries:` list is ignored.

**Verification:** `python -c "from x_monitor.query_plan import _load_brand_tokens_per_model; from pathlib import Path; print(_load_brand_tokens_per_model(['minimax','qwen','deepseek','glm','xiaomi_mimo','moonshot_kimi','inclusionai'], Path('data/queries')))"` prints the same 7 brand-token lists that the 2026-06-16 inventory doc shows in its "Per-model brand tokens" table.

- [ ] **Unit 7: Update `config.yaml` and `Config` schema for the new shape**

**Goal:** Add the required `x_monitor_list_id` field; `degraded_skip_order` stays (no schema break) but is a no-op; per-model `min_faves` moves to a documented location.

**Requirements:** R7, R8, R10

**Dependencies:** None (can land in parallel with any other unit)

**Files:**
- Modify: `x-monitoring/config.yaml` — add `x_monitor_list_id: <numeric id>`; keep `degraded_skip_order` (vestigial) with a comment.
- Modify: `x-monitoring/x_monitor/config.py` — add `x_monitor_list_id: int` (required, validated).
- Modify: `x-monitoring/data/filters/<m>.yaml` — add `min_faves: N` to the `RelevanceConfig` schema.
- Modify: `x-monitoring/tests/test_config.py` — add tests for the new fields.

**Approach:**
- `x_monitor_list_id` is required, must be a positive int. The 2026-06-16 launch step is: operator creates the x.com list, copies its numeric ID from the URL, sets `x_monitor_list_id` in `config.yaml`, restarts the LaunchAgent. The plan doc's "Operational Notes" section spells this out.
- `degraded_skip_order` is kept in `Config` (validation passes) but `apply_skip_order` is updated to be a no-op for the 2-call shape.
- The per-model `min_faves` lives in `data/filters/<m>.yaml::min_faves` (a new top-level field on `RelevanceConfig`).

**Execution note:** No test-first requirement here; this is a config + filter refactor with no behavioral change at default values.

**Patterns to follow:** The existing `Config` field-with-default pattern (`query_rot_streak_threshold`, `clustering`, etc.) is the template.

**Test scenarios:**
- Happy path: A config without `x_monitor_list_id` fails validation (required field).
- Happy path: A config with `x_monitor_list_id: "abc"` fails validation (must be int).
- Happy path: A `data/filters/<m>.yaml` without `min_faves` validates; `RelevanceConfig.min_faves` defaults to 0.
- Edge case: A post with `favorite_count=0` and `min_faves=2` is hard-dropped with `reason="hard_drop_min_faves"`.
- Error path: A config with `min_faves_per_model={"unknown_brand": 5}` fails validation.

**Verification:** A round-trip config load and apply run shows the existing 287+ tests pass plus the new config tests.

## System-Wide Impact

- **Interaction graph:** The translation pass is a new step at the end of `RunPipeline.execute`, after the per-call loop. The compiled-regex build is at the top of `execute()` (once per cycle). The list-drift detection is a one-pass operation after Call A's first response. No new middleware; no new background thread; the LaunchAgent cadence is unchanged.
- **Error propagation:** LLM translation failures are non-fatal: a missing translation falls back to source `text` in the dashboard, and the `x-monitor translate` subcommand is the recovery. TwitterApi errors on either call are handled the same as v1.6. List-drift is a soft warning, not a hard fail (the x.com API doesn't expose list membership). The new shape removes the operator-cap-overflow failure mode for both calls: Call A is 2 operators; Call B is 8.
- **State lifecycle risks:** The migration 003 is forward-only and additive. The `source_query_id` values change from `Q1..Q6` to `ACCT | BRAND_WIDE`; old posts keep their old `source_query_id` values, but the dashboard's `_QID_TO_SIGNAL` mapping adds entries for the new values and leaves the old ones returning `None` (so old signal_breakdown counts are zeroed for old posts — acceptable, since we're not rewriting history).
- **API surface parity:** Two CLI subcommands are added (`x-monitor translate`); one config field is added (`x_monitor_list_id`); no existing subcommand or config field is removed.
- **Integration coverage:** The 2-call integration test (Unit 2) is the only way to prove the fetch → classify → insert → translate pipeline works end-to-end. The dashboard locale rendering test (Unit 5) is the only way to prove the front-end respects the toggle. The list-drift test (Unit 1) is the only way to catch yaml ↔ x.com list drift.
- **Unchanged invariants:** The per-model `RelevanceConfig` shape and the `_review_queue.json` shape are unchanged. The `data/accounts/<m>.yaml` shape is unchanged. The LaunchAgent plist and the `~/.env.secrets` env wrapper are unchanged. The TwitterAPI.io client (`apify.py`) is unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| The x.com list is public; staff membership is visible to anyone who knows the list ID | Documented trade-off. The list ID is a number, not a name — to find it, someone would need to either guess the ID or pull it from a config leak. The list is on x.com, which is already a public platform; staff accounts are public. Net: low additional exposure. If the operator objects, fall back to per-brand lists (7 calls instead of 2; loses 3.5× cost reduction but the trade-off is on privacy, not on cost). |
| x.com list curation drift — yaml gains a staff but the x.com list doesn't | Unit 1's list-drift detection compares the first Call A response's `author_handle`s to the yaml union; if a yaml-listed handle is absent for 3 consecutive dry-runs, write `degraded:list_drift` to the run JSON. Soft warning, not hard fail. |
| x.com deletes the list or changes the list ID behind our back | The first Call A response that returns 0 tweets when the list is configured is the signal; a 0-tweet response is already handled (existing behavior: write a `error` entry to the run JSON, mark the run as `degraded`). Operator investigates. |
| LLM translation introduces cost and latency that doesn't fit the 15-min LaunchAgent cadence | The translation pass is bounded by kept-post count (~hundreds), not raw returns; Haiku latency is <2s per batch. The run JSON includes `translation_seconds`; if the deadline (30s) trips, the run completes with whatever was translated and the rest is backfilled. |
| `text_zh_cn` is a Simplified Chinese translation that doesn't read idiomatically for the user's audience | The user explicitly asked for Simplified Chinese; the dashboard's `display_locale` defaults to `en` so the Chinese toggle is opt-in. Operators can flip the default by editing one line. |
| Migration 003 is applied to a DB that already has rows with NULL `text_en`/`text_zh_cn`; the dashboard renders source `text` for those rows, which may be in a different language | The dashboard shows a subtle "(English source)" / "(中文原文)" badge when displaying fallback text. Operators can backfill with `x-monitor translate`. |
| The LLM's `lang_detected` disagrees with TwitterAPI.io's `lang` field (the source `posts.lang` column) | Keep both: `posts.lang` is the API's claim; `posts.lang_detected` is the LLM's. The translation pass uses `lang_detected`; the dashboard surfaces both in the detail view. |
| The compiled-regex fast-path in `attribute_to_brand` produces a regex that doesn't match a token the v1.6 dict-iteration path would have matched | Test: build the regex from the same deduped brand tokens; for each token, assert the regex matches at least one synthetic text containing the token. Test on a corpus of held-out brand mentions. |

## Documentation / Operational Notes

- **`docs/reference/2026-06-16-194558-twitterapi-live-queries-by-model.md`** — superseded. Replace with a v1.7 reference doc that shows the 2-call shape, the paren-grouped Call B, the curated x.com list, and the per-locale storage.
- **Launch steps (one-time, in order):**
  1. Operator creates a public x.com list named (e.g.) `x-monitor-staff` containing all 7 brands' official + staff handles.
  2. Operator copies the list's numeric ID from the x.com URL (the `list:1234567890` portion).
  3. Operator sets `x_monitor_list_id: 1234567890` in `x-monitoring/config.yaml`.
  4. Operator restarts the LaunchAgent (`launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.scheduled`).
  5. First dry-run (`python -m x_monitor dry-run`) should show 2 calls and a non-empty Call A response with author handles from the curated list.
- **Ongoing operational task:** When `data/accounts/<m>.yaml::staff` gains a new handle, the operator adds it to the x.com list. The list-drift detection will surface any drift as a soft warning after 3 cycles.
- **LaunchAgent `com.fuchitalee.x-monitor.scheduled`** — unchanged. The 15-min cadence and the `~/.env.secrets` env wrapper work for both TwitterAPI.io and the Anthropic API key.
- **Operator runbook** — add a section on `x-monitor translate` and the x.com list curation cadence.
- **Dashboard user-facing copy** — the locale switcher says `EN | 中文`.

## Sources & References

- **Origin document:** [docs/reference/2026-06-16-194558-twitterapi-live-queries-by-model.md](../reference/2026-06-16-194558-twitterapi-live-queries-by-model.md)
- **Prior plan:** [docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md](2026-06-07-001-feat-chinese-models-x-monitoring-plan.md)
- **Code references:**
  - `x-monitoring/x_monitor/query_plan.py:45-69` (INTENT_BUCKETS — to delete)
  - `x-monitoring/x_monitor/query_plan.py:138-165` (_split_brands_to_fit_cap — to delete)
  - `x-monitoring/x_monitor/query_plan.py:205-278` (plan_calls — to collapse)
  - `x-monitoring/x_monitor/run.py:420-445` (intent-call branch — to collapse)
  - `x-monitoring/x_monitor/intent_classifier.py:80-150` (attribute_to_brand — to add compiled-regex fast-path)
  - `x-monitoring/x_monitor/migrations/001_initial.sql` (template for 003)
  - `x-monitoring/x_monitor/migrations/002_headline_columns.sql` (template for 003)
  - `x-monitoring/x_monitor/dashboard.py:134-220` (serialize_grid_card — to add display_locale)
  - `x-monitoring/x_monitor/templates/grid.html.j2` (topbar — to add locale switcher)
- **External docs:**
  - X advanced search `list:` operator: [TweetFinder 2026 cheatsheet](https://www.tweetfinder.io/blog/twitter-search-operators-cheatsheet), [ExportData cheatsheet](https://www.exportdata.io/blog/advanced-twitter-search-operators/) — **getxapi 2026 reference removed 2026-06-17** (see amendment below; the "paren grouping = 1 operator" claim is empirically false)
  - X API v2 character-length limits: [docs.x.com](https://docs.x.com/x-api/posts/search/integrate/operators) (512 chars for self-serve recent search)
  - Claude Haiku 4.5 pricing: https://docs.anthropic.com/en/docs/about-claude/pricing
- **Institutional memory:** `~/.claude/projects/-Users-allenwlee/memory/project_x_monitoring_2026-06-16.md` (v1.6 commit history + 287-test baseline)

---

## Cap probe amendment (2026-06-17)

**Trigger:** User pushback — *"Skeptical of `Each per-brand paren group counts as 1 operator under X's grouping rule` (verified via the getxapi 2026 reference: `"(a OR b OR c) counts as one expression rather than three separate operators"`). The deduped brand tokens come from `data/queries/<m>.yaml`; if there is a grouping rule, then conceivably we can have unlimited OR operators. Check official docs and get definitive answer."*

**Investigation:** Direct API probe against `https://api.twitterapi.io/twitter/tweet/advanced_search` with `TWITTERAPI_IO_API_KEY` from `~/.env.secrets` on fuchitalee. Probe scripts at `/tmp/test_paren{3,4,6,7,8}.py` on fuchitalee. Fruit-name tokens (verified to return 20 real tweets at the 22-token baseline) used to control for "no results" vs "cap hit."

**Result:** The cap is on **character length**, not operator count. TwitterAPI.io enforces the official X API v2 self-serve recent-search limit of **~512 characters** (per [docs.x.com](https://docs.x.com/x-api/posts/search/integrate/operators), which specifies only character-length limits and no operator count). Boundary: 49 ungrouped ORs (509 chars) returns 20 tweets; 50 ungrouped ORs (520 chars) returns 0 tweets. Over-cap queries return HTTP 200 with `tweets: []` (no error code, no `msg`, no 4xx) — the "silent fail" the user originally asked us to investigate.

**Paren grouping is NOT an escape hatch.** Test data:

| inner ORs | paren groups | length | tweets |
|---|---|---|---|
| 30 | 1 | 560 | 0 (fails) |
| 30 | 3 | 564 | 0 (fails) |
| 30 | 5 | 568 | 0 (fails) |
| 30 | 10 | 578 | 0 (fails) |
| 30 | 15 | 588 | 0 (fails) |

All five 30-OR variants fail at the same character-count cliff. The `(` and `)` brackets **add** characters without helping. The getxapi.com claim that "(a OR b OR c) counts as one expression rather than three separate operators" is **empirically false** in the sense that motivated v1.6 and v1.7's design. The 22-23 operator number in the igorbrigadir README and the getxapi / ExportData / Unfollr cheatsheets is an **artifact** of the character cap hitting a query of average token length (22 single-word tokens joined by ` OR ` lands near 512 chars). It's not an operator count.

### Impact on v1.7 design

| v1.7 design aspect | Status after probe |
|---|---|
| Call A = `(list:<x_monitor_list_id>) min_faves:1` (29 chars) | **Still works.** `list:` is a real escape hatch because the numeric list ID is ~12 chars regardless of how many handles are in the list. **This is the only viable way to get staff handle coverage in a single call.** |
| Call B = paren-grouped OR chain over 7 brand token groups (218 chars) | **Still works**, but **because 218 < 512**, not because "8 operators < 22 operators." |
| `assert_under_operator_cap()` from v1.6 | **Rename to `assert_under_length_cap(query_string, max_len=512)`** in v1.7. Counts `len(query_string)`, not operator tokens. |
| `_split_brands_to_fit_cap` recursion in v1.6 | **Still delete** in v1.7 — the new 2-call design doesn't need splitting at 7 brands. But if v1.8 scales beyond ~15-17 brands, the splitting logic returns as `_split_brand_wide_query_for_length_cap()`. |
| v1.6 plan's "safe up to 21 brands" claim for Call B | **Wrong.** Empirically: ~15-17 brands with 3 tokens each (~500 chars). Beyond that, must split. Document this as a v1.8 trigger. |
| Paren-grouped Call B shape | **Keep for readability** (per-brand attribution boundaries visible in the query string), even though it adds ~28 chars vs an ungrouped `a OR b OR c OR d...` form. Both shapes fit at 7 brands. |

### Implementation unit delta (vs the original 7 units)

The probe results do **not** add or remove any of the 7 implementation units — they only change the **rationale** in:
- **Unit 1 (rewrite `plan_calls`):** change the docstring from "under X's 22-OR cap" to "under the 512-char length cap"; rename the validation function from `assert_under_operator_cap` to `assert_under_length_cap`; remove the operator-counting helper `count_x_operators` and replace with `query_string_length(s)`.
- **Unit 2 (rewrite `attribute_to_brand` with compiled regex):** no change — this unit was never tied to the operator-cap claim.
- **Unit 3 (translation pass):** no change.
- **Unit 4 (schema migration 003):** no change.
- **Units 5-7 (operator UI, dashboard, tests):** no change.

The `_split_brands_to_fit_cap` helper that was scheduled for deletion in v1.7 stays deleted. A **new helper `assert_under_length_cap(query_string, max_len=512)`** replaces `assert_under_operator_cap` in `x_monitor/queries.py:171` (one-line rename + change of body from `count_x_operators(s) <= 22` to `len(s) <= 512`).

### What the user got right

The pushback was correct: **if there were a true operator-counting grouping rule, the cap would be effectively unlimited, which is implausible for any production system.** The actual cap being on character length is the only design that scales sanely. The `list:` operator remains the genuine escape hatch for the staff handle coverage, and the paren-grouped Call B is kept as a readability convention — but the v1.6 plan's claim that this combination "bypasses the operator cap" was wrong. It works because both query strings are short, not because paren grouping does anything special.

### What to do if `assert_under_length_cap` fires in v1.7

The 7-brand Call B is 218 chars, leaving 294 chars of headroom. Likely failure modes for v1.7:
- Operator adds a 4th brand token to `data/queries/<m>.yaml::brand_tokens` for an existing brand → +10-30 chars per brand. The 7 brands × 3 tokens design has ~9x headroom for token expansion before hitting 500 chars.
- Operator enables a 8th brand → adds a new paren group (~20-50 chars). Still well under 512.

A real failure (>= 512 chars) would require either adding many new brands or substantially expanding brand tokens. In either case, the right response is **to split Call B into multiple `brand_wide` calls** (e.g., Call B1 = brands 1-7, Call B2 = brands 8-14). The `plan_calls` function should grow a `_split_brand_wide_for_length_cap(brand_tokens, max_len=480)` helper that returns 1+ calls, each fitting under the cap with a 32-char safety margin. **This is v1.8 work, not v1.7.**
