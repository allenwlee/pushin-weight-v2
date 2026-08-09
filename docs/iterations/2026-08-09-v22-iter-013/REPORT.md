# Iteration 013 (v22) — Element-tree diff: live feed structure diverges from mockup

**Date:** 2026-08-09
**Branch:** feat/v20-homepage-phase-a
**Scope:** Audit-only. User reported the live page "looks completely off" — especially locale buttons and the feed. Per the rewritten § Visual-drift detection (single goal statement, model picks method), iter 13 uses **element-tree diff** — a different method class than iter 5-12's computed-style assertions. This is exactly the re-direction rule firing: the user's complaint shifted from micro-drift to spatial/structural drift.

## Step 0 — Regression Net (pre-edit)

```
Passed: 78
Failed: 0
```

Regression net still green but irrelevant — it inspects HTML structure for presence, not for the right shape. The user's complaint is about shape.

## Step 1 — Method: element-tree diff via Chrome DevTools MCP

`mcp__chrome-devtools__evaluate_script` ran on both mockup (`http://127.0.0.1:8001/06-tier1-composed.v22-master.html`) and live (`http://127.0.0.1:5050/?locale=en`) at the same viewport (1358x844). Captured the first feed row's children + descendants + locale button structure + filter pill structure.

## Step 2 — What failed (concrete element-by-element diff)

### Feed row structure

| Element class | Mockup | Live | Status |
|---|---|---|---|
| `.feed-row-shell` (outer wrapper with tint) | present, 2 children | **MISSING** | DEAD |
| `.feed-main` (left column) | present | **MISSING** | DEAD |
| `.feed-signals` (right column with emoji rows) | present | **MISSING** | DEAD |
| `.feed-row` (row container) | inside `.feed-main` | not rendered | DEAD |
| `.body` (handle + meta + text + engagement) | present | not rendered | DEAD |
| `.head` (handle + meta + ts-abs group) | present | not rendered | DEAD |
| `.handle` (`@kimi_moonshot`) | `SPAN.handle` | `<a class="feed-handle-link">` (different element name) | DIVERGED |
| `.meta` (`· 12m (10:21 本地)`) | `SPAN.meta` + `SPAN.ts-abs` | not rendered | DEAD |
| `.text` (post body) + `.text-layer-tag` (分类 indicator) | `DIV.text` + `SPAN.text-layer-tag` | `DIV.cell-truncated` (different element name) | DIVERGED |
| `.engagement` + `.followers` + `.likes` + `.rts` + `.replies` | `DIV.engagement` with 4 child spans | not rendered | DEAD |
| `.sig-row.sig-sentiment` (😊😐) | present | **MISSING** | DEAD |
| `.sig-row.sig-post-type` (📢🤚) | present | **MISSING** | DEAD |
| `.sig-row.sig-nat` (🗯️: 🇨🇳🇺🇸) | present | **MISSING** | DEAD |
| `.avatar` | inside row | rendered outside row (separate column) | DIVERGED |

### Locale buttons

| Property | Mockup | Live |
|---|---|---|
| Container | combined `window-toggle locale-toggle` (one nav) | separate `locale-toggle` (one nav) + separate `window-toggle` (one nav) |
| Button labels | 英文 / 中文 / 原文 | 中文 / EN / orig |
| Button style | pill-shaped buttons inside single nav | separate buttons inside single nav |

### Mockup's layout shape (per the captured mockup data)

Each feed row is:
```
[.feed-row-shell (tinted background)]
  [.feed-main]                 # LEFT 50%
    [.avatar]
    [.body]
      [.head: handle + meta + ts-abs]
      [.text + .text-layer-tag]
      [.engagement: 👥 ♥ ↻ 💬]
  [.feed-signals]              # RIGHT 50%
    [.sig-row.sig-sentiment:  😊😐]
    [.sig-row.sig-post-type:  📢🤚]
    [.sig-row.sig-nat:         🗯️ 🇨🇳🇺🇸]
```

### Live's actual layout shape

Each "feed row" is rendered as **5 separate flat cells inside `.feed-rows`**:
```
.feed-rows > a.feed-date-link       (timestamp)
.feed-rows > span.pill             (brand chip)
.feed-rows > div.lang-sub          (translation source)
.feed-rows > div.cell-truncated    (post text)
.feed-rows > div.muted-cell        (★ count)
```

No wrapper. No avatar in the row. No handle/meta/text-layer-tag/engagement. No emoji signal rows. No right column.

## Step 3 — Summary

**Method used:** element-tree diff via Chrome DevTools MCP `evaluate_script`. Different method class than iter 5-12 (which used computed-style assertions). Correct choice for the user's complaint class (spatial/structural drift).

**What failed:** the live page's feed DOM structure is fundamentally different from the mockup's. Mockup is a 2-column grid (avatar+body on left, emoji signals on right). Live is a flat list of 5 sibling cells per row with no row wrapper. The emoji-based sentiment / post-type / nationalism signals the user sees in the mockup are **completely absent** from the live page. The locale buttons are also in different containers (combined vs separated) with different labels.

**Learnings:**
- iter 11 noted "structural divergence: live uses flat feed children instead of `.feed-row` wrapper" and dismissed it as "visually inconsequential." That call was wrong. The divergence was consequential — it explains exactly why the feed "looks completely wrong" to the user.
- The 78-assertion regression net never noticed because every assertion was about element presence (`feed-handle`, `feed-engagement`, `avatar`, etc.) — the assertions would have failed if the elements didn't exist at all, but they DO exist (in `_feed_initial.html` template, which iter 5 wired up), just in the wrong shape inside the rendered HTML.
- Element-tree diff catches what computed-style assertions can't: not "is this colored right" but "is the row laid out the way the mockup lays it out."

**Re-direction for iter 14:** the fix is **not CSS**, it's **template + view data**. `_feed_initial.html` needs to be rewritten to render the 2-column `.feed-row-shell` structure with `.feed-main` (avatar + handle + meta + text-layer-tag + engagement) and `.feed-signals` (3 sig-rows). The view function `_post_to_wire` needs to extend its return dict to include `meta_text` (relative age like "12m"), `ts_abs_text` (absolute timestamp like "10:21 本地"), `engagement_pretty` object with separate `followers_pretty`, `likes_pretty`, `rts_pretty`, `replies_pretty`, and signal emoji arrays (sentiment_emoji, post_type_emoji, nat_emoji). This is a multi-file change (template + view + maybe a CSS file for the new 2-column grid) — not one iter's work; possibly iter 14 (template + view data shape) + iter 15 (CSS grid + visual verification).

Scope delivered vs plan promised: narrower — audit-only this iter (no code changes). Iter 14+ will land the actual structural fix. No silent narrowing (the structure-divergence finding is now explicit in the plan, not dismissed as "visually inconsequential").