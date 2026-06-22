# HF products as brand aliases — design notes

Author: allenwlee
Date: 2026-06-22 (JST)
Status: research/design NOTES — not an implementation plan
Audience: future-self (the x-monitor operator)

## Context

x-monitor v1.7.x replaced per-brand account calls with a 2-call design:

- **Call A** — `(list:<x_monitor_list_id>) min_faves:1`. One list-based fan-in; the operator-maintained `x-monitor-staff` list supplies the official handles.
- **Call B** — paren-grouped brand-wide: `(brand1 OR alias1 OR alias2) (brand2 OR …) ...`. Vendor-level fan-out, one paren group per brand.
- **Call C** — optional per `CallCBrandSpec`. Used when a brand's signal is dominated by a specific co-occurrence context (e.g. MiMo posts that mention Xiaomi but only matter when paired with model-name tokens).

The hard cap is **character length (~512 chars)**, not operator count
(`feedback_twitter_x_cap_is_characters_not_operators.md`). Today `_BRAND_ALIASES` has 17 entries. **Aliases do not add characters to the API call** — they only feed the post-fetch `attribute_to_brand` regex matcher.

The future plan: ingest Hugging Face products as additional brand aliases. The motivation is coverage — vendor-level tokens like `bytedance` miss posts about specific products (Bernini, Ouro, Sa2VA, video-as-prompt). Some products are substrings of existing tokens (e.g. `minimax-m3.0` ⊂ `minimax`, so the vendor call already captures them via substring match on `minimax`). Others are NOT substrings and need explicit tokens in Call B to be reachable at all.

These notes capture the failure modes and architectural options BEFORE we ingest anything, so that when actual HF data arrives the design is already thought through.

## Failure modes

### FM1 — Call B exceeds 512 chars → ValueError aborts the cycle

Call B's `query` string is built by concatenating brand groups (`(A OR B OR C) (D OR E) …`). Each paren group is roughly `<brand>` + ` OR ` × N aliases. With ~11 brands and a few aliases each today the string is **~321 chars**. Adding 20 Bytedance product tokens alone would add ~200 chars (10 chars/token × 20 + OR + spaces) → call hits ~520 and the run.py validator raises.

Example (truncated):

```
(anthropic OR claude) (minimax OR m2 OR m2.7 OR minimax-m2.7 OR …)
```

### FM2 — Co-occurrence group in Call C grows past 512 chars

Call C is structured around a *base brand* + co-occurrence tokens:

```
(bytedance OR ByteDance) (bernini OR ouro OR sa2va OR "video-as-prompt")
```

If we add Call C for every vendor that has product-level aliases, each Call C spec risks the same 512-cap blow-up — and unlike Call B there is no paren-grouping trick that helps, because each token really is independent.

### FM3 — Attribution precision degrades with substring tokens

For substrings (`minimax-m3.0` ⊂ `minimax`), no new search chars are needed; the vendor-level Call B already returns the post. The risk is in the post-fetch `attribute_to_brand` regex: a naive `\bminimax-m3.0\b` matcher will only attribute posts that contain the compound token literally. A bare `\bminimax\b` would attribute everything including the noise. The substring case is the **easy** case — the alias can be added to `_BRAND_ALIASES` with no API cost.

### FM4 — Call B's structure becomes unwieldy with single-brand inflation

If we add 20 Bytedance product tokens as a separate paren group inside Call B:

```
(bytedance OR ByteDance OR bernini OR ouro OR sa2va OR "video-as-prompt" OR …) …
```

…the group is no longer readable as "vendor + a few canonical aliases." It looks like a kitchen sink. Tests that snapshot Call B's char count (e.g. `test_query_plan_v17`) need to be loosened. Future readers will struggle to know which token means what.

### FM5 — Brand-only tokens cause false-positive attribution

Bytedance is a household name (TikTok's parent). A bare `\bbytedance\b` post-fetch regex will attribute every ByteDance-the-company discussion to our "AI vendor" brand, polluting the signal mix. The MiMo precedent already showed this — `moonshot` as a token matched Moonshot crypto exchange spam; we dropped it from `_BRAND_ALIASES` and replaced with `月之暗面`/`暗面` per `project_xmonitor_quote_tweets_2026-06-22.md`.

## Mitigations (in order of preference)

### Option A — Post-fetch alias map (unlimited, zero API cost)

A separate file (e.g. `data/aliases/bytedance.yaml`) mapping brand → list of product-name regexes. The `attribute_to_brand` post-fetch step consults this map *after* the vendor-level token match. No API chars added. No cap to worry about. This is where **most product names should live**.

### Option B — Promote high-collision vendors to their own Call C

For vendors where product-name mentions are the dominant signal (not vendor-name mentions), use a dedicated Call C:

```
Call C bytedance: (bernini OR ouro OR sa2va OR "video-as-prompt") (research OR paper OR model OR release)
```

…each as its own API call, with its own 512-char budget. Keeps Call B clean and readable.

### Option C — Split Call B into B1 + B2 + …

If even the brand-grouped paren call hits the cap, split into multiple calls. Last resort — each extra call adds cost + a duplicate-result risk (same post can match both B1 and B2; attribution becomes union-or-dedupe).

### Option D — Don't add (accept lower recall for low-signal brands)

For low-signal brands whose product mentions are rare, do nothing. Recall drops for those products; everything else unchanged.

## Recommended architecture

1. **Vendor-level token in Call B** — small, cheap, covers the common case. Keep current size discipline (≤ 400 chars to leave headroom).
2. **Optional Call C** for vendors with collision problems (Bytedance is the canonical example — house-hold-name, multiple product lines).
3. **Post-fetch alias map** (`data/aliases/<vendor>.yaml`) for the long tail of product names. Lookup is regex-based and free at API-call time.
4. **Post-fetch soft-drop rules** in the relevance filter, analogous to the F1 list for Kimi. A product-name mention in a non-research context (e.g. "Bernini the pasta sauce") should not count as a brand mention. Use case-by-case stopwords.

## Operator decision (2026-06-22)

**Limit brand aliases manually for now. Do NOT auto-ingest HF products.**

Reasons:

- We don't have actual HF product data to ingest yet. The Bytedance/Bernini examples are illustrative, not real.
- Call B today is 321/512 chars (191 chars of headroom). Plenty of room before we hit the cap.
- No vendor yet has the Bytedance-style collision problem in our monitored set.
- The post-fetch alias map is the right shape, but adding it without data means adding empty config + dead code.

**Revisit when:**

- We have actual HF product data (CSV or API) to ingest.
- Call B starts approaching 512 chars (warn at ~400).
- A new vendor with collision problems (Bytedance-class) is added to the monitored set.
- We see recall gaps in production — a known product's posts not showing up in the dashboard.

## Open questions

1. **How will we detect "Call B is getting tight"?** Add a runtime warning at ~400 chars (`logger.warning(...)` in `run.py:query builder`), surfaced via `data/runs/LATEST.*.json` so the dashboard staleness indicator could grow a "Call B at 78% of cap" badge?
2. **How will we represent the alias map?** Options: (a) new file under `data/aliases/`, (b) section in `config.yaml`, (c) HF-derived CSV refreshed by a separate script. Need to pick before any ingestion happens.
3. **Multi-token product names.** `video-as-prompt` needs to match as a single token, not the word `video` alone. Should the alias map store raw regexes or normalized compound tokens with implicit word boundaries? Default to raw regexes for explicit control.
4. **Cross-language aliases.** Same problem as `月之暗面` for Moonshot. HF products have Chinese names too (Bernini → 伯尔尼尼?). Manual curation vs auto-translate via Haiku pass?
5. **Versioning.** `minimax-m2.7` vs `minimax-m3.0` — should the alias map have a `latest` pointer, or always require explicit versions?

## Cross-references

- `project_xmonitor_quote_tweets_2026-06-22.md` — v1.7 + Call C work, moonshot/MiMo disambig examples
- `feedback_xmonitor_fk_hot_path_2026-06-20.md` — prior attribution work; the `attribute_to_brand` regex matcher lives here
- `feedback_xmonitor_cron_v17_list_gate.md` — v1.7 gate at `run.py:376-384`; the call builder we extend lives in the same file
- `feedback_twitter_x_cap_is_characters_not_operators.md` — confirms the 512-char cap mechanism (FM1, FM2)
- `feedback_twitterapi_unknown_list_silent_fallback.md` — silent-failure precedent; the alias map must have a startup sanity check analogous to the list-drift detection
- Recent commits:
  - `90e6c51` — Units 5-6 (polarity RT-fold + day-1 moonshot disambig)
  - `d66eb71` — Call C MiMo

## Estimated cost / impact

- **Steady state at 11 brands + ~3-5 Call C specs:** ~$0.50-1/mo (adds ≤5 new API calls per 15-min cycle; existing v1.7 cost baseline is ~$13-22/mo).
- **One-time HF ingestion:** design TBD. CSV import script + alias-map file generation, run once. Cost negligible.
- **No regressions expected.** The post-fetch alias map is purely additive — existing vendor tokens stay, new product tokens get attributed when the post-fetch step sees them. The MiMo fix (dropping `moonshot`, adding `月之暗面`) showed the pattern: additive on the brand side, subtractive on the noise side.
- **Risk if done wrong:** FM5-style false positives (over-attribution) would corrupt the polarity numbers. Mitigation: ship the alias map behind a feature flag, dry-run against 2008 historical posts, compare dashboards before/after.