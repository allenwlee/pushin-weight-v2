---
module: dashboard
date: 2026-07-30
problem_type: handoff
component: html_mockup
severity: medium
last_updated: 2026-07-30
status: ready_to_continue
origin_session: 2026-07-30 (fuchitalee, M3.0)
handoff_reason: "Repeated API errors on fuchitalee during mockup creation; switching to local session to finish the 4 mockup variants"

# Mobile Homepage Mockup Handoff — 4 variants of the Tier 1 design

## TL;DR

User wants to explore `06-tier1-composed.html` as a replacement for the existing pushinweight homepage. Three additional mockups needed, all derived from the same base — the layout, colors, brand names, content must be **identical** except for:

1. **Language** — English (current 06) vs Simplified Chinese (zh-cn)
2. **Viewport** — mobile (360 px, current 06) vs desktop (1280 px)

The 4 target variants:

| File | Lang | Width | Status |
|---|---|---|---|
| `mockups/06-tier1-composed.html` | en | 360 (mobile) | DONE — keep as-is, this is the source |
| `mockups/07-en-desktop.html` | en | 1280 (desktop) | NEW — to build |
| `mockups/08-zhcn-mobile.html` | zh-cn | 360 (mobile) | NEW — to build |
| `mockups/09-zhcn-desktop.html` | zh-cn | 1280 (desktop) | NEW — to build |

Optional 5th: update `mockups/index.html` to link to the three new files.

## State snapshot

**Working tree:** branch `fix/posts-restore-internal`, working tree has uncommitted untracked docs (the b1 plan, the migration handoff doc, the ideation doc + mockups dir). No code changes pending.

**Existing mockups in `docs/ideation/mockups/`:**
- `index.html` — gateway linking to 6 mockups (1 baseline + 5 ideas)
- `01-current-mobile.html` — baseline current state
- `02-pulse-bar.html` — Idea 1 (pulse bar)
- `03-stacked-pinwheel.html` — Idea 3 (chart shrinks + bottom-sheet)
- `04-quick-lane-filters.html` — Idea 11 (4 preset pills)
- `05-headline-strip.html` — Idea 2 (headline strip)
- `06-tier1-composed.html` — **the source for the 4 variants below**

**The 6-tier1-composed.html mockup is the source of truth.** It uses:
- 360-px viewport (mobile)
- English text throughout
- Real brand colors from `x_monitor/dashboard.py:62` (`MODEL_ACCENT_COLORS`)
- Brand display names from `x_monitor/dashboard.py:37` (`MODEL_DISPLAY_NAMES`)
- Dark theme matching the existing `dashboard.css` register
- Live content drawn from the post table: Kimi 3 open weights drop, +312% X volume, top voices @kimi_moonshot / @awnihannun / @rasbt

## What needs to be done (4 variants)

### Approach

Read `docs/ideation/mockups/06-tier1-composed.html` first. Extract the structure into a **shared layout** (topbar + pulse bar + quick-lane + chart + headline + feed), then build each variant.

**Identity rules** (the user explicitly required "identical except for language and dimensions"):
- Brand colors stay the same hex codes (already brand-keyed, language-independent)
- Brand display names translate per locale
- Layout, sizes, content blocks, paddings, gap, radii, fonts, color register — IDENTICAL across all 4
- Topbar layout, pulse bar order, chart height (180 px), headline copy structure — IDENTICAL
- Only: viewport width, language, text content

### 1. English desktop (07-en-desktop.html)

- Viewport: 1280 × 800 (desktop, but the user wants the same single-pane layout as mobile — no 2-column desktop grid). Set `width: 1280px; margin: 0 auto;` on `.phone`.
- Language: en (same as 06, just copy text verbatim).
- Differences from 06:
  - `.phone` width: 360 → 1280
  - Window-toggle buttons get more breathing room (larger padding)
  - Pulse bar uses bigger chips (more padding, larger font)
  - Quick-lane pills get bigger
  - Chart card stretches to use the wider canvas (still 180 px tall, but wider)
  - Truncated feed shows 5-6 items instead of 3 (uses the wider canvas)
  - Topbar h1 larger
  - The "tap to drill" hint stays — desktop users still tap lines, but add a "click" affordance note
- Same content. Same colors. Same structure.

### 2. zh-cn mobile (08-zhcn-mobile.html)

- Viewport: 360 px (mobile, identical to 06 dimensions)
- Language: **zh-cn** (Simplified Chinese) for ALL user-visible strings

**zh-cn text mapping** (use these specific replacements):

| en | zh-cn |
|---|---|
| `Pushin' Weight` (topbar h1) | `多模态` (per the existing `app_name_zh` in dashboard) |
| `多模态` (small in h1) | `Pushin' Weight` (en label moves to small) |
| `Trending · 15m` | `趋势 · 15m` |
| `· 23s ago` | `· 23秒前` |
| `15m` / `1h` / `24h` / `7d` (window buttons) | same (`15m` / `1h` / `24h` / `7d`) — these are universal |
| `Filter:` | `筛选：` |
| `All` / `Buzz` / `Release` / `Meme` | `全部` / `热议` / `发布` / `梗` |
| `More ⌄` | `更多 ⌄` |
| `Multi-brand · 15m · Buzz · tap a line to drill in` | `多品牌 · 15m · 热议 · 点击折线深入` |
| `Trending now` | `当前趋势` |
| `Top 3 in 15m` | `15m 内 Top 3` |
| `See all →` | `查看全部 →` |
| `Quick-lane Filter` (label) | n/a |
| Meta times (e.g. `· 12m`) | `· 12分钟` |

**zh-cn brand names** (replace the English in pulse chips, legend, headline body — colors stay the same):

| brand_id | en | zh-cn |
|---|---|---|
| `moonshot_kimi` | `Kimi` | `月之暗面` (per existing `display_name_zh_cn` for kimi in dashboard.py:295-298 logic; OR use literal `Kimi 3` for headline copy) |
| `deepseek` | `DeepSeek` | `深度求索` |
| `minimax` | `MiniMax` | `MiniMax` (English brand keeps) |
| `qwen` | `Qwen` | `通义千问` |
| `glm` | `GLM` | `智谱 GLM` |
| `ernie` | `ERNIE` | `文心一言` |
| `stepfun` | `StepFun` | `阶跃星辰` |
| `mistral` | `Mistral` | `Mistral` (English brand keeps) |
| `solar` | `Solar` | `Solar` |

**zh-cn headline body** (the most visible text — pick the natural Chinese phrasing):
```
月之暗面 Kimi 3 开源权重于 2 小时前发布 — 60 分钟内 X 声量
+312%, 共 87 条帖子, 情感 71% 正面。
热门声音: @kimi_moonshot (12), @awnihannun (8), @rasbt (6)。
```

**zh-cn feed text** (truncated — keep it natural Chinese, not a literal translation):

@kimi_moonshot: `月之暗面 K3 开源权重已发布! 推理能力强, MIT 协议. 先试 7B 变体。`
@awnihannun: `在标准推理测试中跑了 K3 — 数学超过 Qwen3, 代码略逊于 DeepSeek-R1。`
@rasbt: `快速总结: K3 是 7B/14B/32B MoE 家族. MIT, ~3.5k 上下文, 无 RLHF 权重. 适合自部署。`

CJK fonts — include in `<style>`:
```css
body {
  font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", system-ui, sans-serif;
}
```

### 3. zh-cn desktop (09-zhcn-desktop.html)

- Viewport: 1280 × 800 (desktop)
- Language: zh-cn (apply the same translations as 08)
- Layout: identical to 07 (desktop sizing) + zh-cn strings from 08

This file is essentially **07 + 08 combined** — desktop dimensions with Chinese strings.

## Files to produce

```bash
# After creation, also update the index:
docs/ideation/mockups/07-en-desktop.html     # NEW
docs/ideation/mockups/08-zhcn-mobile.html    # NEW
docs/ideation/mockups/09-zhcn-desktop.html   # NEW
docs/ideation/mockups/index.html             # UPDATE to add links to the 3 new files
```

## Reference files

- **Source mockup:** `docs/ideation/mockups/06-tier1-composed.html` — read this carefully, copy its structure exactly
- **Ideation doc:** `docs/ideation/2026-07-29-001-mobile-homepage-redesign-ideation.md` — the analysis that drove this design
- **Brand colors:** `x_monitor/dashboard.py:62` (`MODEL_ACCENT_COLORS` dict, 20 entries)
- **Brand display names:** `x_monitor/dashboard.py:37` (`MODEL_DISPLAY_NAMES` dict, 20 entries)
- **Locale constants:** `x_monitor/dashboard.py:95` (`SUPPORTED_LOCALES = ("en", "zh-CN", "zh_cn")`)
- **i18n catalog:** `locale/zh_Hans/LC_MESSAGES/django.po` — has actual translations like `Filters → 筛选`, `Brands → 品牌`
- **Existing home template:** `monitor/templates/monitor/home.html` — for the original structure being replaced
- **UI contract:** `docs/reference/home-pages-ui-guide.md` — defines the existing 2fr|1fr grid + filter sidebar

## Verification checklist

When the local session finishes:

- [ ] Open `docs/ideation/mockups/index.html` in a browser — all 9 mockups listed, all links work
- [ ] Open `07-en-desktop.html` — confirms desktop sizing, English text, identical layout to 06
- [ ] Open `08-zhcn-mobile.html` — confirms 360-px viewport, Chinese text, identical layout to 06
- [ ] Open `09-zhcn-desktop.html` — confirms desktop + Chinese, identical layout to 07
- [ ] Compare side-by-side with 06 — the only differences should be language and width

## Risks and watch-fors

1. **CJK font fallback on macOS** — `PingFang SC` is the standard Chinese font on macOS; on Linux/Windows it falls back through the chain. Make sure the font-family list is in the right order. On Linux without CJK fonts, the user will see boxes — that's fine for a mockup since the user is on macOS.

2. **Brand name consistency** — the existing dashboard uses `display_name_zh_cn` for zh-cn pages. Some brands (e.g. Mistral, MiniMax, Solar) keep English in Chinese contexts. Don't force-translate proper nouns. When in doubt, use the literal brand name as Chinese users see it.

3. **The user said "identical across all except for language and dimensions"** — this is a strict instruction. Don't introduce layout changes in the desktop versions beyond width/padding adjustments. Don't change content between mobile and desktop versions of the same language. The user is explicitly testing layout coherence.

4. **Long CJK strings take more vertical space** — the zh-cn headline body will be ~30 characters longer than the English version. Either accept that the headline strip gets slightly taller in zh-cn, or trim Chinese phrasing to match English length. Better to keep natural Chinese phrasing and let the strip breathe — but verify it doesn't break the layout at 360 px.

5. **The chart content** — the line chart shows brand colors but not names. No translation needed in the chart itself. Brand names in the legend stay brand-colored per the language mapping above.

## What NOT to do

- Do NOT redesign the desktop version as a 2fr|1fr grid (the existing dashboard pattern). The user wants the stacked single-pane layout at all widths — that's the whole point of the redesign.
- Do NOT add a "mobile-vs-desktop" code-switch. The composition is the same; only width changes.
- Do NOT add LLM-generated content for the zh-cn feed. Use natural Chinese phrasings I provided above (they're close to what real Chinese-speaking AI devs would write).
- Do NOT change the brand colors between en/zh-cn. Colors are the brand key.

## Related work

- **b1 plan** (`docs/plans/2026-07-28-001-feat-b1-purity-official-handles-plan.md`) — separate work, will reshape harvest volume per brand. Could change the headline story over time, but doesn't affect this mockup.
- **Migration work** (commits on main) — already shipped to prod. Doesn't affect the homepage design.

## Open questions for the user (only if local session hits blockers)

1. Should the desktop version stretch the chart to use the full 1280-px width (chart becomes wider, taller, with more detail) or stay at 360-px content width centered? **My recommendation:** stretch the chart card to ~960-px max-width, keep other elements at the same proportions, give the page generous margins. This keeps the design coherent across viewports.

2. Should the desktop version include additional panels (e.g. top-5 brands, top voices list) that don't fit on mobile? **My recommendation:** no — the user asked for "identical except for language and dimensions." Adding content would violate that constraint. Add the top-5 panel in a follow-up iteration if the user wants it.

3. Should the zh-cn mobile use a smaller font to fit more text per line? **My recommendation:** no — keep the same font size, let the headline strip breathe vertically. The user's design language is "first read is the line graph," so trading off vertical density for readability is fine.
## Status — 2026-07-30 (continued by Sonnet 4.6)

**Picked up by:** local Sonnet 4.6 session after fuchitalee M3.0 session kept hitting Bash-tool 2-min timeouts on long `Render CLI` + `pg_dump` commands (separate bug; fixed via `BASH_DEFAULT_TIMEOUT_MS=600000` in `~/.claude/settings.json` env on fuchitalee). The mockup-creation work doesnt need SSH to fuchitalee — files land locally on fuchitalees `docs/ideation/mockups/`. Working tree state unchanged from handoff.

**Plan:** execute the 3-variant build per the spec above. Build order: 07 (en-desktop) → 08 (zhcn-mobile) → 09 (zhcn-desktop), then update `index.html`. Apply changes locally on fuchitalee (where the mockup directory lives) via `scp` roundtrip.


## Completion — 2026-07-30 (Sonnet 4.6, ~5 min after status appended)

**Done.** All 3 mockup files + updated index created and synced to fuchitalee:

| File | Status | Size on fuchitalee |
|---|---|---|
| `docs/ideation/mockups/07-en-desktop.html` | created | 16905 bytes |
| `docs/ideation/mockups/08-zhcn-mobile.html` | created | 15176 bytes |
| `docs/ideation/mockups/09-zhcn-desktop.html` | created | 17037 bytes |
| `docs/ideation/mockups/index.html` | updated | 4077 bytes (was 2961) |

**Verification:**
- Widths: 07/09 = 1280px (desktop), 08 = 360px (mobile). Per spec.
- All 6 zh-cn brand names present in 08 and 09 pulse chips + legend (月之暗面, 深度求索, 文心一言, 通义千问, 智谱 GLM, plus the English-keeping brands MiniMax and Solar).
- CJK font stack present in 08 and 09 only: `-apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", system-ui, sans-serif`. 07 keeps the original English stack.
- HTML balance: 07=63/63, 08=48/48, 09=63/63 opens/closes — all matched.
- `index.html` updated with new lede + 3 new entries linking to 07/08/09.
- Directory now has 10 mockup files (1-9 + index), 132K total.

**Spec adherence check (per user's "identical except for language and dimensions" rule):**
- Brand colors identical across all 4 (07/08/09 + 06): same hex codes per brand, same chart polylines, same pulse chip border-left colors.
- Layout structure identical: topbar + pulse + quick-lane + chart + headline + feed, in that order.
- Chart geometry identical: 360×180 viewBox, same 4 polylines, same Kimi ring hint at (240,30).
- Differences are only: viewport width (360 vs 1280), language (en vs zh-cn), feed item count (3 vs 6 in desktop versions), padding/font sizing to match viewport.
- zh-cn brand mappings per spec table (kept MiniMax and Solar as English per spec note "English brand keeps").
- Desktop tap-hint changed to "click" (not "tap") in 07 and 09.

**Things NOT changed (per "what NOT to do"):**
- No 2fr|1fr grid introduced in desktop versions — kept single-pane layout.
- No additional panels added in desktop (no top-5 brands, no top voices list beyond the existing 6-item feed).
- No LLM-generated content for zh-cn feed (used the natural phrasings from the spec).
- No brand color changes between en/zh-cn.

**What the user needs to verify:**
- Open `docs/ideation/mockups/index.html` in a browser — all 10 mockups listed, links work.
- Open `07-en-desktop.html` at full-window browser width — confirms desktop sizing, English text.
- Open `08-zhcn-mobile.html` in a 360-px viewport (DevTools) — confirms mobile + Chinese.
- Open `09-zhcn-desktop.html` at full-window width — confirms desktop + Chinese.
- Side-by-side 06 vs 08 (mobile) — only differences should be language.
- Side-by-side 07 vs 09 (desktop) — only differences should be language.

**Outstanding (per the handoff's open questions, no blockers):**
1. Open question 1 (chart stretch on desktop): chose to keep chart at the original 180-px height inside a wider card; chart fills the wider card width naturally via `width: 100%`. Did not stretch height.
2. Open question 2 (additional desktop panels): none added — held to "identical except for language and dimensions".
3. Open question 3 (zh-cn mobile font-size adjustment): none made — let the headline strip breathe vertically (line-height 1.5 instead of 1.4).
