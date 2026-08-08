# Iteration 001 (v22) — Element Audit + Diff vs v22-master

**Date:** 2026-08-08
**Branch:** feat/v20-homepage-phase-a (carrying v22 work)
**Viewport:** 390x844 (mobile, zh_cn/en variants handled by mockup locale toggle)
**Locale:** live = en ; mockup = zh_cn (default)
**Stop remaining:** iter 1 of fresh loop after hard-reset

## Step 1 — Regression Net (per-iteration contract)

`tests/regression_net.py --email allen@quantma.com --password ono`

```
Passed: 34
Failed: 0
```

All 34 structural assertions PASS against live page. Pre-iteration gate satisfied.

## Step 2 — Element Audit (live page 8 vs mockup page 7)

| Mockup region | Live page status | Mockup status | Diff |
|---|---|---|---|
| **Banner (h1 + tz pill + window toggle + locale toggle)** | ✅ present (4 windows, 3 locales, tz pill) | ✅ present | **Match** (chrome) |
| **Trending models region** ("脉冲 / 窗口内热度") | ✅ present; pills render (DeepSeek, Qwen, Zhipu GLM, MiniMax AI, Meta Llama, Mistral, Xiaomi MiMo, ByteDance Doubao) | ✅ present ("趋势 · 24H"); pills + %change arrows (Kimi ▲312%, DeepSeek ▲47%) | **Partial**: pills render but **no %change arrows + no "· 23秒前" timestamp** |
| **Filter groups nav** | ✅ 7 buttons (Brands, Discourse, account.role, lang, Sentiment, Nationalism, unsanctioned) | ✅ 7 buttons (品牌/话语/角色/语言/情绪/民族主义/未授权) | **Match structurally**; locale-default differs (live=en, mockup=zh_cn). Live should default to zh_cn per Goal Capsule ("Defaults: zh_cn, 24h window, local timezone") — **flag** |
| **Chart** | ✅ Canvas "每日各品牌帖子总数" | ✅ Canvas with legend (Kimi/DeepSeek/MiniMax/Qwen/ERNIE) | **Match** (chart renders) |
| **Top voices** (mockup: combined into "正在热议 ..." sentence with @handle + ☆ count) | ⚠️ Region exists, heading "Top voices ☆ by followers" present, **but body is EMPTY** — no @handle cards | ✅ Inline with trending: "@kimi_moonshot (☆ 12), @awnihannun (☆ 8), @rasbt (☆ 6)" | **P0 gap**: Top voices view function NOT YET ADDED. Live renders the heading but no data. From the v20 plan's UI region table: this row was already marked "NOT YET ADDED" for Top Voices — confirmed. |
| **本窗口最新 feed** | ✅ heading + 6+ cards with timestamp, handle, translated-from, text, ★ count, types/discourses/sentiments/nationalism chips, author @handle link, follower count | ✅ heading + 3 cards (more compact) | **Partial**: live has full classification chips; mockup has more compact engagement stats (👥 ♥ ↻ 💬 with counts). Live MISSING: avatar circle initials (K/A/S), engagement numbers (👥 128.4k / ♥ 1.2k / ↻ 340 / 💬 89) |

## P0 blockers (live MUST have these to match v22-master)

1. **Top voices body** — heading "Top voices ☆ by followers" is on the page but the data table that backs it is missing. From `monitor/views.py` (per UI region table): `_multi_top_voices()` is NOT YET ADDED. This is the load-bearing P0 from previous iterations — the data infrastructure was never built.

2. **Trending %change arrows** — v22-master shows each pill with ▲/▼/→ and a percentage. Live page shows pills but no delta. This is a new v22 visual element the live page never had.

3. **Locale default** — live defaults to `en` (query param). Goal Capsule says "Defaults: zh_cn". Either live's `?locale=` param routing or the home view's default needs adjustment.

## P1/P2 polish gaps (NOT blockers, captured for follow-up)

- **Engagement counts on feed cards** (👥 / ♥ / ↻ / 💬) — mockup shows numbers; live page shows only ★ star count.
- **Avatar circles** (initials in colored circle) — mockup has them per card; live doesn't.
- **Filter group labels in zh_cn** when locale=zh_cn — live probably translates them via gettext but mockup uses fixed labels (品牌 etc.). Need to verify the `_DASHBOARD_*` key tuples resolve to zh_cn strings.

## P0 missing UI regions (file gaps for v22 plan's UI region table)

| Mockup region | Status on live |
|---|---|
| Top Voices body | **NOT YET ADDED** (P0 — blocks any PASS verdict) |
| Trending %change deltas | **NOT YET ADDED** |
| Feed engagement counts | **NOT YET ADDED** |
| Feed avatar circles | **NOT YET ADDED** |
| Locale-default behavior (zh_cn not en) | **NOT YET ADDED** |

## Step 6 — Diff verdict

**Live is missing 5 P0 items** that the v22-master mockup requires. Top Voices is the historical blocker (4 iterations of fix-attempts, never landed). The 4 others are new v22 deltas (the previous v20 mockup didn't have %change arrows, engagement counts, avatar circles, or zh_cn default).

## Decision

Per per-iteration contract Step 7: "If diff shows new P0: file gap, add to UI region table above." Filing all 5 gaps. **Per Step 8**: do NOT proceed to scenario captures while P0 audit failures are open.

## Next iter

Iter 002 (v22) — Pick the lowest-cost P0 to fix first. Top Voices is the historical blocker; the new v22 P0s (Trending %, locale default, engagement counts, avatar circles) are template-only changes that should land first to clear the simpler path, then revisit Top Voices with the v22-plan's UI region table gap now explicitly listed.

**Recommendation for iter 002:** Locale default (zh_cn) + Trending %change arrows — both are view-layer / template changes, no DB query needed. Fixes 2 of 5 P0 gaps without introducing a DB migration.