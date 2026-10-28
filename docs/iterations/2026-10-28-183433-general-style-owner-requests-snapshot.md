---
title: Homepage in General's style — owner requests for production
created_at: "2026-10-22T18:45:45+09:00"
status: owner-requests-recorded
source: prototype session homepage-general-prototype-20261022
prototype: .context/compound-engineering/ce-prototype/2026-10-22-homepage-general/ (git-ignored, fuchitalee)
---

# Homepage in General's style — owner requests for production

## Plain-English Summary

The owner reviewed a working prototype of the public homepage restyled to look like the General page. It ran on live production data, and all the homepage's features kept working. This file records every request the owner made during that review, word for word, plus what each request means as a concrete change. The goal is that whoever applies the design to production can do it without the prototype session.

The direction is settled at this level. Use General's look (white panels, DM Sans and Newsreader fonts, segmented controls, a left icon rail) on a Facebook-gray page with a white masthead. Brand colors come from Artificial Analysis, and brand logos appear in the chart legend. The owner also asked for several filter-dropdown copy and spacing changes. A LinkedIn/bronze variant was explored and dropped.

Nothing here has been applied to production. The prototype changed no template, static file, application code, database or deployment. Open items at the end need a decision or follow-up before production work starts. The main one is that renaming the brand tabs to Others/Giant changes only their labels, not which brands are grouped under each.

## Owner requests (verbatim, in order)

1. Original brief (handoff `2026-10-22-143406-homepage-general-fresh-brief.md`, attributed to the owner): *"a new homepage prototype, designed from first principles using General's full visual styling. Copy as much of General's look and feel as possible while preserving all current homepage features and elements. Open the result in a separate browser tab."* Fresh viewpoint: earlier prototypes, proposals and reviews deliberately not consulted.
2. *"let's add a gray to the background (meaning app-shell), same gray as facebook background. things like gx-panel gx-activity retain same color"*
3. *"yes masthead remains white. also can u open up a new tab in same browser and render same page with the gray of linkedin (it's a diff shade of gray)"*
4. *"for the linkedin gray, change the thin borders around the divs to same color as linkedin. then change the color of all the glyphs to a bronze color (inspired by the qin bronze weight). the active toggles should also be changed to a version of the bronze (can be a lighter shade apropos to the design)"*
5. *"change colors also the brand names class='brand' and class='text-layer-tag' and remove gx-head (from both), also change logo color to bronze as well, also from both, delete pw-icon from the geopolitical pill"*
6. *"ok we're going with the fb version. i actualy only wanted the title from pulse-bar-wrap removed, add back the others. the logo should revert to black. the glyphs in sidebar should be a shade of balc"* followed by *"black"*
7. *"ok we're going to make some changes to assigned colors for each model. take a look at artificialanalysis.ai and see if u can grab both the colors assigned to them in bar charts as well as the logos for each of the brands. they keep it consistent throughout their site. (btw there's still some lingering bronze in places like headline-state, revert those back). I want to adopt those colors from aa wholesale and also the logos, which should display in the chart-legend (but not in the pulsebar. for all dropdown, eg sentiment, a cateogry with no glyph should have an equal space in lieu of a glyph, such that the text 'Unclassified' is left aligned with 'Neutral', eg. In GEopolitical, above 'reporting, framework, nationalism', put Geopolitical Framing as a header. for [cn flag] National Stance, capitalize it and put a 1/2 or full line space above that line, to separate from the Framing line. do the same for [us-flag] line. change "Untracked" to "3rd Party" Brand Promotions in the dropdown pill. Under Brands, instead of Open/Closed, put Others/Giant. for all my comments in this session, save to file as well for when we apply these to production"*
8. *"those four should be based on their own brand identities"* (the four brands Artificial Analysis does not chart)

9. Owner answers to the open items: *"Giant is our nickname for oai, anthro, gemini, spacexsi. 2. no leave as is. 3. i'm comfortable 4. yes this is a problem. one way to solve is to use animation of each line. (a) when user hovers over the brand in chartlegend, the brand dot, logo and name get a glow effect for the duration of the hover. at the same time, any other brands in chartlegend get dimmed; same happens to the line: line glows. (b) we should assign different animations to each line, similar to a christmas light that has different settings: vary the speed, pattern (some burn slowly on then off), some twinkle randomly, some twinkle in rhythm, some flash all bulbs at once. the dots next to the brand name will animate in complete sync with the lines. these variations should be applied differently according to color shade. let's try that and see how that works."*
10. *"remove the current hover over line grahp (where the timewindow shows posts by brand). replace that with, when user hovers over a line, has same glow effect on the line and the chartlegend as when chartlegend is hovered over"*

11. *"keep the glow. drop the christmas light animation, it's too busy and hectic. let's try this: for the glow effect, keep the hover. however, automatically, the glow will cycle through each brand on the graph in perpetuity. the cadence should be in order: deepseek glow 1 sec, then qwen, then minimax, etc."*

12. *"its good but the faded ones are too faint. increase by 2x"*

13. *"let's stop the cycling. on hover, the brand's data labels (number of posts) is revealed as plain numbers in same color as the line"*

14. *"make same hover over effect when hover over the individual line"*
15. *"note that on mobile it would be a single tap"*

16. *"on desktop, hover over glows; clicking will keep glow persisted until user clicks elsewhere"*

17. *"you will see here https://polymarket.com/sports/bkkbl/bkkbl-mob-lg-2026-10-22 look at the last point for both lines, they are flashing on and off with a concentric animation. can u recreate that?"*

18. *"I dont love our glow effect which looks cheap, let's see if we can replace it with this pinging effect on hover. or, based on the polymarket implmenetation, do u see other animations they are using that we can use, or is there a opensource library they are using that we can tap into for different ideas"*

19. *"i like kalshi's implmentation better https://polymarket.com/event/nba-2027-champion . some things we should do: 1`. put the y axis on the right side; 2. in en, time should be 12hr time eg 8:17pm; 24:00 clock stays for zhcn,ja; 3. the right side of lines should end a bit to the right of the new y axis, so that the ends of the line are a bit more viewable (just alittle spacing). let's do 4 smoother lives and lighter dotted gridlines;"* (the link points to a Polymarket page although the message names Kalshi; item 4 refers to technique 4 in the research list below)

20. *"remove points, and beacons should be on all the time"*

21. *"flags in feed seem not to be rendering"* (diagnosis: they were loading, but white-field flags such as Japan's vanished into the white feed cards, leaving only a red dot; the live feed is dark, so it never showed)

22. *"the flags are stretched horizontally"*

23. *"and they don't show when i scroll down"*

24. *"values for pw-icon follower-icon should be customized for zhcn and ja; eg, 10k followers = 1万 in ja and zhcn (or whatever's established in this context). also vietnam flag looks stretched horizontally still"*

25. (2026-10-24, about the net-change list) *"make this a durable file, and update it every time we make a change. my next changes: the beacons at current point of each line should be on always, upon load and never stopping. lines need additional differentiation; use different line shapes (dotted, dashed, etc); that will have to be reflected in the legend as well. for the beacons, and the alternate shapes by brand (circle, triangle, square, etc); reflect those shapes in the legend in 7d, 30d, 365d, dates on x axis in each language should be prettified (en: Feb 9 (7d, 30d), or Feb 2026 (365d); ja 3月9日, eg) above 'sig-row sig-sentiment' should be a list of all the brands applied by the post. just put the logos. hover over the logo displays the brand name. 'Language detection, translation and analysis pending. Historical first-attempt translation average: about 5 minutes. Historical first-attempt analysis average: about 15 minutes.' -is too verbose; should be: 'Language, translation and analysis pending (5-15 min. est.)' x axis should end at the latest time of fetch (eg, 9:18PM) and work backwords (eg, prior has should be 8:18pm, etc) capitalize 'local' to "Local" on x axis, and tz-pill capitalize Audience Topic everywhere filter-pill 'Lang' should be 'Language' in en"*
26. (2026-10-26) *"for homepage, change meta llama labels to just 'Meta'"*
27. (2026-10-26) *"Llama is the brand-- we may need to change the brand name itself to something more inclusive. eg Minimax is the brand, and encompasses product families such as m and hailuo"*
28. (2026-10-26) *"also confirm how we are setting the order of the pills and chart legend. it was fixed based on average post volume, but meta is now the clear leader aafter we fixed our harvester, and thus should be number 1 (ahead of deepseek)."* Follow-up after the agent reported the order is a fixed list: *"yes it's basically arbitrary. move meta to the top"*
29. (2026-10-26) *"beacons for ending points on line graphs essentially at zero; probably you're capturing after the last fetch  time; the data point should end just before so that real value is captured"*
37. (2026-10-27) *"change: hover over a line will change it to solid on hover (regardless of line pattern at rest)"*
38. (2026-10-27, versioning) *"the current version is basically an alpha, only shared with select group of people. what would be the user facing version"* Then, after the agent suggested "Private Alpha" in the footer: *"yes but the next version will be launched to the public, but we want to let thme know it's still beta."* Decision: *"we should have 1.0.0b1 (then the build version in parens)"* Correction: *"i dont mean bbuild version, i meant the internal version"*
39. (2026-10-27) *"lock in the new logo design: for text, allcaps on one line with differentweight for weight. for the logo itself, i want to make one incremental change: where the handle connects to the top of the weight, the line should look curved, so that the round handle's shape attaches to the top of the weight and is recognizable as such. show locally at differentsizes;"*
40. (2026-10-27) *"lock in that new logo with rounded handle"*
41. (2026-10-27) *"ok we will be restyling general page in same manner as hompeage. take all the appropriate changes in homepage and apply to general, then show locally"*
42. (2026-10-27) *"ok, let's also do dashboard/each"*
43. (2026-10-27) *"switch colors for undetected/unclassified and other/neutral. reduce outline line to 1 px"* Then: *"and yues capitalize"*

## Resulting production change list

Final state after all corrections. Superseded requests (bronze/LinkedIn, removing every heading, bronze logo) are recorded above but are **not** in this list.

### Layout and chrome (General visual system)
- Use General's tokens from `monitor/static/monitor/general.css` (origin/main): DM Sans body, Newsreader editorial headlines, blue `#4378ff`, ink `#18212d`, muted `#687589`, lines `#e6eaf1`, panel borders `#dce4fc`, 18px panel radius, General breakpoints 1320/1160/960/700px, 1440px max content width.
- Left icon rail as on General: General link, in-page anchors (Trending, Posts by brand, Trend summary, Latest), "P"/Pro current; it expands on desktop and becomes a slide-out drawer at ≤700px. **Rail glyphs in black `#1c1e21`.**
- Masthead: logo, then labelled segmented controls Window (1d/7d/30d/365d), Clock (local ⇄ California), Language (en/中文/日本語). **Masthead is white, full width.** **Logo is black (`#18212d`).**
- **Page background (`.app-shell`) is Facebook gray `#f0f2f5`.** Panels, cards, chips, filter buttons and the rail stay white.
- Trending models bar: a white panel **with no heading** (owner removed only this heading).
- Filters row: labelled "Filters"; pills in General's segmented-button style; dropdowns styled like General's settings drawer.
- Main grid: Trend summary on the left, styled like General's Chatter story (large Newsreader headlines), with a wider **"Posts by brand" chart panel that keeps its heading**. ≤960px stacks chart → summary → feed.
- Feed: a panel **with its icon heading row kept** around the existing "Latest in window" title; posts shown as a responsive grid of white cards.
- No bronze anywhere. Status labels that had turned amber/bronze (`headline-state`, `headline-item-state` stale, California clock label, pending-language tag) use muted gray. Mixed-sentiment and official-role glyphs use amber `#d97706`.

### Brand colors (adopt from Artificial Analysis wholesale)
Applied everywhere a brand color appears: chart lines, chart legend dots and trending-chip dots. Production source: the `colors` map and `pulse.entries[].accent_color` in the homepage chart payload.

| Brand key | Display | Color | Source | Legend logo |
|---|---|---|---|---|
| deepseek | DeepSeek | `#2243e6` | AA | AA `deepseek.svg` |
| qwen | Qwen (Alibaba) | `#ff7018` | AA | AA `alibaba.svg` |
| minimax | MiniMax | `#eb3568` | AA | AA `minimax.svg` |
| glm | Zhipu GLM (Z AI) | `#1c7ff8` | AA | AA `zai.svg` |
| mimo | Xiaomi MiMo | `#ff6900` | AA | AA `xiaomi.svg` |
| moonshot_kimi | Moonshot Kimi | `#047afe` | AA | AA `kimi.jpg` |
| inclusionai | InclusionAI | `#4fb5ff` | AA | AA `inclusionai.jpg` |
| mistral | Mistral | `#f32e02` | AA | AA `mistral.svg` |
| stepfun | StepFun | `#00f5e7` | AA | AA `stepfun.svg` |
| ernie | Baidu ERNIE | `#2436d8` | AA | AA `baidu.svg` |
| hunyuan | Tencent Hunyuan | `#5cb9ff` | AA | AA `tencent.svg` |
| llama | Meta Llama | `#0089f4` | AA | AA `meta.svg` |
| nemo_megatron | NVIDIA NeMo | `#76b900` | AA | AA `nvidia.svg` |
| doubao | ByteDance Doubao | `#3c8bff` | AA (ByteDance Seed) | AA `bytedance.svg` |
| exaone | LG EXAONE | `#df3b8a` | AA (LG AI Research) | AA `lg.png` |
| kuaishou | Kuaishou (KwaiKAT) | `#489034` | AA (KwaiKAT) | AA `kwaikat.svg` |
| upstage | Upstage | `#7c59f5` | AA | AA `upstage.svg` |
| yi | 01.AI Yi | `#001a12` | 01.AI brand (01.ai favicon) | AA `01ai.jpg` |
| sensechat | SenseTime SenseChat | `#e83020` | SenseTime brand (logo red) | SenseTime infinity mark (cropped from sensetime.com logo) |
| sakana_ai | Sakana AI | `#e00000` | Sakana AI brand (logo red) | Sakana fish mark (cropped from sakana.ai logo) |
| dots | rednote dots | `#ff2442` | rednote brand (app icon red) | rednote app icon (xhscdn favicon) |

AA colors were read on 2026-10-22 from artificialanalysis.ai chart series. Each series carries `color` plus a `logo` path under `/img/logos/`, and the pairs are consistent across the home page, `/models`, `/leaderboards/models`, `/models/open-source` and model detail pages. AA charts none of yi, sensechat, sakana_ai or dots; AA does host a 01.AI logo. The local prototype copies are in `.context/.../01-general-skin/screens/logos/`.

### Logos
- Brand logos appear **in the chart legend only** (color dot → 14px logo → name). **Not in the trending bar.**

### Flags (owner item 21)
- On the white General cards, flags get a faint hairline edge (four half-pixel `drop-shadow`s at 22% ink, which follow the painted flag, so non-16:9 flags such as Switzerland get no empty frame). Without it, white-field flags (Japan and others) disappear. Applies to feed account flags and to the flags in the filter dropdowns.

- **Proportions (owner item 22):** the sprite (`country-flags.svg`, R74n pixel flags) draws every flag in a 16:9 grid, wider than most real flags (3:2), so they read as stretched — on the live site too. The prototype narrows the drawing to 3:2 in place (`transform: scaleX(.844)`), keeping the pixel-art style. Production can do the same in CSS, or redraw the sprite at 3:2; square or unusual flags (Switzerland, Nepal) are not individually corrected either way.
- **Live defect — flags missing after scrolling (owner item 23):** rows added by infinite scroll are built in the browser by `pw-feed.js`, whose `countryFlagSpriteUrl()` only accepts the sprite URL if it contains `country-flags.svg`. Production serves the collectstatic-hashed name `/static/country-flags.e1ef2c1d1cff.svg`, so the check fails, the fallback looks for an inline `<symbol>` that isn't on the page, every flag is rejected, and single-country location badges are dropped entirely. Measured on pushinweight.ai 2026-10-23: rows 1–50 (server-rendered) had 21 flags; rows 51–200 had 0, although the `/feed/` JSON carried flags for 20 of the next 50 rows. Production fix: accept the hashed name (e.g. match `/country-flags(\.[0-9a-f]+)?\.svg$/`) and add a regression test for scroll-loaded rows with a hashed static URL. The prototype relay rewrites the hashed name to the unhashed one (also served by WhiteNoise), after which rows 51–250 showed 66 flags.

- **Vietnam still looks stretched (owner item 24):** the 3:2 squeeze cannot fix it: the pixel-art star fills the flag's full height and 10 of 16 columns, so it reads wide and oversized, and the squeeze turns round shapes (Japan's sun) into ovals. Options shown to the owner side by side (`/__proto/flags-compare.html`): A live 16:9 pixel art, B squeezed pixel art (prototype now), C vector flags at 3:2 (country-flag-icons, MIT). **Owner choice pending.**

### Follower counts in Chinese and Japanese (owner item 24)
- zh_hans and ja count followers the way X, Weibo and Xiaohongshu do: below 10,000 the exact number with a thousands comma (`4,407`); from 10,000 in 万 with one decimal (`2.9万`, `12.3万`, `999.9万`); from 100 million in 亿 (zh) / 億 (ja) (`1.2亿` / `1.2億`). Values are truncated, never rounded up, as X does (29,701 → `2.9万`). English keeps the current `29.7k`. Applies to the count beside the follower icon, its hover/inspection label (`2.9万 X 关注者` / `2.9万 X フォロワー`) and screen-reader label.
- Production: format server-side from `followers_count` per locale (the `followers_pretty` / `followers_label` fields and the server-rendered row), not in the browser — server-rendered rows carry only the English abbreviation (`4.41k`), from which exact Chinese/Japanese values cannot be recovered. The prototype relay rewrites `/feed/` JSON and, for the first page, looks up exact counts from the feed API (100 rows) by tweet ID.

### Filter dropdowns
- **All dropdowns:** an option without a glyph keeps an empty glyph-sized space (16px), so its text lines up with options that have one. Example: Sentiment's "Unclassified" aligns with "Neutral". Verified across every filter group: zero misaligned columns.
- **Geopolitical:** add the header **"Geopolitical Framing"** above Reporting / Framework / Nationalism. The two national-stance lines read **"National Stance"** (capitalized), each with roughly a line of space (14px) above it to separate it from the section before. The owner also removed the pill's globe help icon (`pw-icon` inside `.filter-help-trigger`).
- **Rename:** "Untracked Brand Promotions" → **"3rd Party Brand Promotions"** (pill title and dropdown label).
- **Brands tabs:** "Open / Closed" → **"Others / Giant"**.
- The prototype's translations for the new labels were chosen by the agent and need owner or translator review: zh 地缘政治框架 / 第三方品牌推广 / 其他 / 巨头; ja 地政学的フレーミング / サードパーティのブランドプロモーション / その他 / 大手.

### Chart interaction and brand glow
- **No hover tooltip** on the posts-by-brand chart.
- **Hover focus (ping, not glow):** hovering a legend entry or a line focuses that brand. Its line pings at its latest data point, its legend dot pings in the same phase and its name turns bold. The other lines and legend entries dim (owner-tuned: lines 24% opacity, legend entries 56%). The earlier glow (canvas shadow, text-shadow, logo drop-shadow) was replaced because the owner found it cheap-looking. Keyboard focus on a legend entry does the same. Clicking a point on the 1-day chart still narrows the feed to that 5-minute slot; only the tooltip is gone.
- **Line hover = legend hover:** hovering anywhere along a drawn line (within 8px of any segment, not only at data points) gives the identical effect: the line glows, its legend entry glows, the rest dim and that brand's post counts appear. Where lines lie exactly on top of each other, the first brand in legend order wins.
- **Desktop — click to pin:** hover glows while pointing; clicking a line or legend entry pins that brand's glow and counts so they stay after the pointer leaves. Hovering another brand previews it, and moving away returns to the pinned brand. Clicking a different line or entry moves the pin; clicking anywhere else (blank chart area, another panel, the page) releases it. On the 1-day chart a click on a line also keeps the existing feed narrowing to that 5-minute slot.
- **Mobile — single tap:** on touch screens a tap does what hover does. Tap a line (16px reach) or a legend entry to glow it and show its counts; tap it again or tap elsewhere to clear. Touch never triggers the hover path, so a tap does not flash on and off.
- **Chart sizing defect found (also on the live site):** `home-v20.css` forces the chart canvas height (`220px !important`) while Chart.js sizes the chart from its parent, which also contains the legend, so the drawing is squeezed vertically and pointer positions are off by ~20%. The prototype gives the canvas its own fixed-height box (300px desktop / 240px ≤960px / 200px ≤700px) before Chart.js measures it. Production should give the canvas a dedicated container rather than forcing the canvas height.
- **Hover data labels:** while a brand is hovered, its post count is drawn above each point as a plain number in the line's color, with a thin white edge for legibility. Where neighbouring labels would collide (the 1-day view has 288 points), the later one is skipped; the 7-day and longer views show every point.
- **Live end-point ping (after Polymarket):** each line's point in the **latest time slot** gets a solid 4px dot in the line color plus a copy that expands from 1× to 4× while fading from ~60% opacity to 0 then rests (all lines in phase). Exact source parameters from Polymarket's bundle (2026-10-22), a Motion `motion.circle`: `initial {opacity: .6, scale: 1}`, `animate {opacity: 0, scale: 4}`, tween `duration 2.25`, `ease "easeOut"`, `delay .7`, `repeat Infinity`, `repeatDelay 1` (3.25 s cycle). A line with no data in the latest slot gets no ping, so a ping always means "now". While a brand is focused the others keep pinging, dimmed (item 20). Viewers who prefer reduced motion see only the still dot. The prototype redraws the chart at ~30 fps for this; about 1.6 ms per redraw was measured.
- **No automatic glow cycle** (tried, then stopped by the owner).
- **Dropped:** the Christmas-light per-line animation (owner: "too busy and hectic").

### Axis, clock and line style (owner item 19)
- **Y axis on the right** of the posts-by-brand chart, with no axis line (Chart.js `scales.y.position: 'right'`, `border.display: false`). The 1-day chart's "local"/"CA" row labels, which sat left of the plot where the axis was, move under the right-hand axis.
- **Little gap before the axis:** every line ends 16px (the ping's full radius) left of the right-hand axis, so the latest point and its ping are clear of the axis labels. The prototype shrinks the horizontal scale's drawing range after layout; production can do the same in `pw-chart.js` or with right-side chart padding inside the axis.
- **12-hour clock in English, 24-hour in Chinese and Japanese:** English shows lowercase, no-space times — masthead clock `5:36am`, feed stamps `(5:31am local)`, 1-day axis `8am … 12pm … 8pm` (every 2 hours as before), chart click popover and feed hover title. zh_cn and ja keep `05:36` / `20:00`. Note: the live chart popover formats Japanese with the English (`en-US`) locale and so showed 12-hour times; the prototype forces 24-hour there. Production should set the hour cycle per page locale wherever times are formatted (`pw-tz.js` uses `en-GB` + `h23` for every locale today; `pw-chart.js` tick callback builds `H:00`; `pw-feed.js` hover title uses `timeStyle: 'short'`).
- **Smoother lines:** monotone curves on every view (`cubicInterpolationMode: 'monotone'`), which smooths without overshooting below zero or above a peak. The live site draws straight segments for 7 days and longer, and a looser 0.3 tension on 1 day.
- **Lighter dotted gridlines:** horizontal gridlines are 1px dots with 3px gaps (`border.dash: [1, 3]`) in `#dfe4ec`, replacing solid `#eef1f7` lines.
- **No point markers (owner item 20):** lines are drawn without the small per-point dots (`pointRadius: 0`, also on hover). Clicking the 1-day chart still narrows the feed to a 5-minute slot, because the invisible click target (`pointHitRadius: 8`) is kept.
- **Beacons always on (owner item 20):** every line's latest-slot ping keeps pulsing at all times. While a brand is focused, the other brands' beacons keep pulsing at the same dimmed 24% as their lines (previously they stopped and showed a still dot). The focused brand pings at its own latest data point, as before.

### Owner item 25 (2026-10-24): beacons, patterns, axes, post brands, copy
The net change list for production is kept as a durable file and updated after every change: `docs/brainstorms/2026-10-24-210641-homepage-general-net-changes.html`.
- **Beacons from load, never stopping:** the redraw loop starts as soon as the shell runs, not at window load, and Polymarket's 1 s rest is dropped (2.25 s continuous cycle). Every line has a beacon at its current point, the latest time slot. On 1 day the homepage maps 0 posts to a gap (`pw-chart.js` `value === 0 ? NaN`), so a line whose latest 5 minutes were empty had no beacon. The beacon now sits at 0 on the right edge. Verified: 21/21 brands have a beacon in en, zh_cn and ja.
- **Line patterns and beacon shapes per brand:** four patterns (solid; dashed `[7,4]`; dotted `[0,4]` with round caps; dash-dot `[9,3.5,0,3.5]`) by six shapes (circle, square, triangle, diamond, star, cross). They are assigned per brand in a fixed table (the prototype's `BRAND_STYLE`), so rank changes don't move them. Similar blues (DeepSeek, Kimi, GLM, Doubao, Llama, Hunyuan, ERNIE, InclusionAI) get different pairs, and no pair repeats. A new brand gets a stable fallback from a hash of its key. The legend dot becomes an SVG swatch (a line in the pattern ending in the shape), and the focused brand's legend shape pings in the beacon's rhythm. 1-day line width rises from 1.33 to 1.75 px so patterns show. The live "today is partial" dashed last segment (7/30/365 days) stays only for solid-pattern brands, because on patterned lines it would read as a pattern change. Note: on solid lines it can still be confused with a dashed brand, which needs an owner call.
- **1-day axis anchored at the fetch:** the last tick is the payload's `fetched_at` (equal to the last bucket's start + 5 minutes), and ticks step back whole hours. The step is 1 hour when each hour has 42 px or more, otherwise 2, 3, 4 or 6. At 1440 px desktop the plot is about 840 px wide, so the step is 2 hours ("10:03pm, 8:03pm, …"). The owner's example was hourly, and hourly fits on wider screens. Buckets are drawn at their end time. Production: replace `fixedHourlyTicks` (clock hours) with fetch-anchored ticks.
- **Date axis (7/30/365 days):** `Intl.DateTimeFormat` with `timeZone: 'UTC'` on the `YYYY-MM-DD` labels. en-US `{month: 'short', day: 'numeric'}` gives "Oct 18". zh-CN and ja-JP use `month: 'long'`, which gives "10月18日". 365 days uses `{year, month}`, giving "Dec 2025" and "2025年12月", with ticks on every other month start counted back from the latest. 7 days ticks every day and 30 days every 5 days, back from the latest day.
- **"Local":** the 1-day row label and the clock pill read "Local". The feed stamps "(9:30pm local)" were not named and are unchanged.
- **Brands on each post:** a logo row (`.gx-post-brands`) goes before `.sig-row.sig-sentiment`, using the legend's logos. Hovering or tapping a logo uses the homepage's `pw-inspection-trigger` popup to show the brand name. Server-rendered rows carry no brand list, so the relay adds `data-gx-brands` from `/feed/` `brand_nicknames`. Rows loaded later get it from the `/feed/` responses. Verified: 50/50 rows on load and 350/350 after scrolling. Production: render it from `brand_nicknames` in both the template and `pw-feed.js`.
- **Shorter pending message:** the owner's English wording, plus agent-chosen zh/ja equivalents and a matching retry variant (needs review). It comes from the server in three places (homepage HTML, `/feed/` JSON, and the `/api/v2/post-synthesis-demands/` status responses), so production should change the message source once.
- **"Audience Topic":** the per-brand inspection text ("DeepSeek Audience topic: …") becomes "Audience Topic". The pill already read "Audience Topics".
- **"Language":** the English "Lang" filter pill (`pill_lang`) reads "Language".

### Owner item 26 (2026-10-26): "Meta" label
- "Meta Llama" becomes "Meta" wherever it is a brand label, in en, zh and ja: the brand records' `display_name`, `display_name_en` and `display_name_zh_cn` (homepage data and `/feed/` JSON), the brand filter, the trending chip, popups and status labels ("Meta 分类状态："), and the post logo popup. In production, change the brand's display names in the brand data, not the templates. Post text that mentions Llama is unchanged.
- The chart legend read `llama`, not "Meta Llama": `pw-chart.js` keeps its own short `BRAND_NAMES` list and falls back to the brand code for every brand missing from it (most of them: `glm`, `mimo`, `stepfun`…). The prototype renames only the Meta entry. A production fix should take legend names from the payload's display names, as the trending bar does (net-change list item 46).
- **Owner item 27, collection side done in production (2026-10-25, separate Codex harvester session; report `docs/analysis/harvester/2026-10-25-204500-u10-production-delivery.md`):** production `f4536c2f` added a dedicated C4 search for Llama plus contextual Meta/Muse, and added `meta`, `muse`, `muse code`, `muse glimmer`, `muse image`, `muse video`, `muse voice` and `muse wonder` as keywords of the existing `llama` brand. The internal code stays `llama`, as recommended below. Remaining for this list: the visible name, still "Meta Llama" in production, becomes "Meta" (item 26). Older posts are not relabeled. Whether the other product-named brands also become maker-level is still open. The original note follows.
- **Owner item 27 (original note):** the brand should be the maker, not one product line: "Meta", covering Llama and Meta's other model families, the way `minimax` already covers MiniMax and Hailuo (tokens `MiniMax`, `Hailuo`, `海螺`; handles `MiniMax_AI`, `MiniMaxAgent`, `hailuo_ai`). Today `config/harvest_policy.yaml` collects `llama` only on Llama tokens (`Llama`, `Llama 3`, `Llama 4`, `Meta Llama`, `Code Llama`) together with AI context words, plus the `AIatMeta` handle. A bare "Meta" token would be very noisy (the company, the metaverse, "meta" as a word). Pending owner decisions: (1) which Meta families and handles to add; (2) whether other product-named brands follow (Kimi → Moonshot, GLM → Zhipu, ERNIE → Baidu, Hunyuan → Tencent, Doubao → ByteDance, NeMo → NVIDIA). Recommended: keep the internal code `llama` (posts, colors and filters key on it) and change only the display names plus collection terms. Widening collection is a harvester change (`.claude/skills/change-harvester/SKILL.md`) with a TwitterAPI credit cost; it is outside this prototype.

### Owner item 28 (2026-10-26): Meta first in the brand order
- **How the live order works:** one fixed list, `_HOME_CHART_BRAND_PRIORITY` in `monitor/views.py` (DeepSeek, Qwen, MiniMax, GLM, MiMo, Kimi, … with `llama` 12th), drives the trending chips, chart series, chart legend and brand filter. It was set in commit `de453dab` (2026-09-02, "restore chart-ordered brand pills", requirement R18), which kept an older chart order. It is not computed from volume and does not change with the data. Brands missing from the list follow alphabetically.
- **Volumes seen on 2026-10-26 (chart data, all brands selected):** last 24 hours: Meta 3,829 vs DeepSeek 3,807 posts (Meta up from 190 the day before). 7, 30 and 365 days: DeepSeek still leads by a wide margin (7 days: DeepSeek 25,416, Meta 4,319). Meta leads only the most recent day, after the harvester fix.
- **Change:** `llama` (Meta) moves to the top of the list; every other brand keeps its place. Production: move `"llama"` to the front of `_HOME_CHART_BRAND_PRIORITY` and update the order pinned by `tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_live_brand_pills_follow_chart_order_and_remain_accessible` (R18 text says "beginning DeepSeek, Qwen, MiniMax"). The prototype reorders in the relay (`BRAND_ORDER_FIRST`).
- Not done: ordering by volume. The order stays fixed, so a brand keeps its position, color and pattern from day to day.

### Owner item 29 (2026-10-26): 1-day lines end at the last harvested bucket
- **Cause:** the 1-day payload's 288 five-minute buckets run up to the moment the chart is computed (`fetched_at` = `computed_at` = request time, not the harvest time). The harvest runs every 15 minutes, so the newest buckets are not searched yet: on 2026-10-26 at 02:37 UTC the last bucket was 0 for every brand and the one before was partial (all brands 28 vs about 60 normally). Beacons sat on those values. The owner's reading was right. Item 25's "x axis ends at the latest fetch" used this request time; it now uses the harvest cutoff.
- **Change:** buckets that end after the data cutoff are dropped from the 1-day series, so lines, beacons and the axis's last tick end on the last fully searched bucket (example: harvest cutoff 02:30:50, last bucket 02:23–02:28, Meta 27 and DeepSeek 10 instead of 0). 7/30/365-day views are unchanged; their last day stays partial and dashed.
- **Production:** the chart payload has no harvest time. Add the last completed harvest's search end time to the payload (from the cycle record) and end the 1-day buckets at the last bucket that closes before it. The prototype relay approximates the cutoff with the newest stored post's `created_at` (from `/feed/?limit=1`, cached 30 s) and trims `days` and `series` (`trim_unharvested`), which can end a few minutes earlier than the true harvest time.
- Still at zero: brands that genuinely had no posts in the last searched bucket (about 13 of 21 smaller brands). Their beacons sit on the zero line next to the last axis label.

### Owner item 30 (2026-10-26): line-traced decagon logo
- **Owner (verbatim):** "take the 1 pixel and render both prototype pages with it. also p;ut it in the favicon for the page"
- **Source:** the owner's generated wireframe `docs/ideation/assets/2026-10-26-213300-generated-decagon-wireframe.png`, reduced to its main lines (outline, handle inside and out, top, base and the four edges between the visible front faces of the ten-sided body). Trace, SVG files and size study: `.context/compound-engineering/ce-prototype/2026-10-26-decagon-line-logo/`, `docs/ideation/mockups/qin-quan/2026-10-26-213922-decagon-line-logo-sizes.html`.
- **Change:** the masthead logo and the rail's General icon (the shared `#mark-quiet` symbol) draw the line logo with 1 px lines at every size; the browser-tab icon is the same drawing with its line weight fixed at 1 px at 16 px (light gray in a dark browser theme). `?mark=current` restores the previous mark for the tab.
- **Small sizes:** clean from 32 px; at 24 px the handle opening is a few pixels; at 16 px the six vertical lines merge. A simplified 16/24 px drawing is an open choice.

### Owner item 31 (2026-10-27): Latin-only italic wordmark
- **Owner (verbatim):** "Let's keep the 1px for now, and let's play with the type. Let's remove the chinese lettering, and just put Pushin'Weight in sansserif, italics to the right of the logo"
- **Change:** the masthead lockup is the 1 px line logo followed by one line of text, `Pushin’Weight` (typographic apostrophe, no space, as written), in DM Sans italic 600 at 19 px (17 px on the General page below 700 px). 走个量 is removed from the masthead in every page language. DM Sans italic is loaded from Google Fonts; the pages previously loaded only the upright style.
- **Where:** homepage relay `general-shell.js` (`lineLogo()`) and `general-skin.css`; General logo prototype `2026-10-26-decagon-line-logo/01-general/screens/review/logo-preview.{js,css}` (Line mode only). `?mark=current` on either page restores the previous logo and 走个量 lettering.
- **Not changed:** the browser-tab title still reads "走个量 · Pushin' Weight".

### Owner item 32 (2026-10-27): no apostrophe, two-tone wordmark
- **Owner (verbatim):** "the apostrophe doesn't look good. try it with Pushinweight and PushinWeight and use a different color and use heavier weight for 'Weight'"
- **Change (supersedes item 31's spelling and single weight):** no apostrophe. "Pushin" is DM Sans italic 500 in ink (`#18212d`); "Weight"/"weight" is DM Sans italic 800 in the General blue (`--blue`, `#4378ff`). Size unchanged (19 px; 17 px on the General page below 700 px). The italic font load now covers weights 100–1000.
- **Compare:** a "Text" switch at the bottom right picks Pushinweight or PushinWeight (default PushinWeight). The address remembers it as `?wm=lower` or `?wm=camel`. On the General page the switch shows only in Line mode.

### Owner item 33 (2026-10-27): wordmark all black
- **Owner (verbatim):** "change to all black, keep the line weight"
- **Change (supersedes item 32's blue):** "Weight"/"weight" uses the same ink as "Pushin" and the logo (`--ink`, `#18212d`). The weight contrast stays (Pushin 500, Weight 800), and the logo keeps its 1 px lines.

### Owner item 34 (2026-10-27): small all-caps option and tab titles
- **Owner (verbatim):** "try also small allcaps" and "change on the tabs as well"
- **Change:** the Text switch gains a third choice, CAPS (`?wm=caps`): PUSHINWEIGHT in uppercase at 15 px (14 px on the General page below 700 px) with 0.06em letter spacing, still italic, ink, Pushin 500 and Weight 800. The browser-tab title now follows the switch (PushinWeight, Pushinweight or PUSHINWEIGHT) instead of "走个量 · Pushin' Weight"; Current mode (`?mark=current`, or the General page's Current/Bronze buttons) restores the original title.

### Owner item 35 (2026-10-27): tighter WEIGHT in all caps
- **Owner (verbatim):** "can you keep the tracking between pushin same, but reduce tracking in weight" and "for the all caps"
- **Change:** in the CAPS choice only, PUSHIN keeps 0.06em letter spacing (including the gap before WEIGHT); WEIGHT drops to the font's normal spacing (0). The mixed-case spellings are unchanged.

### Owner item 36 (2026-10-27): stacked, justified all caps
- **Owner (verbatim):** "now put weight on the line below pushin. keep spacing at zero. manipulate tracking for both words so that they are justified"
- **Reading:** applies to the CAPS choice (owner item 35 scope). "Spacing at zero" read as WEIGHT's letter spacing staying 0, with the lines set solid (line height = font size, no added leading).
- **Change (replaces the one-line CAPS):** PUSHIN over WEIGHT, 15 px (14 px on the General page below 700 px), line height 1. At zero tracking WEIGHT's ink is wider (58.75 vs 52.13 px at 15 px), so PUSHIN gets 0.0888em tracking (trailing space cancelled) plus a 0.0775em left nudge, measured from rendered ink. Rendered check: both edges align within 0.17 px at 15 and 14 px; the two-line block is 30 px tall beside the 29 px logo.

### Owner item 37 (2026-10-27): focused line turns solid
- While a brand is focused (hover on its line or legend entry, a pinned click/tap, or keyboard focus), its line draws solid end to end on every window, including the 7/30/365-day partial last segment. It returns to its resting pattern when focus clears. Other lines keep their patterns and the 24% dimming; the legend swatch keeps the resting pattern so it still identifies the brand.
- Implementation note: Chart.js caches per-segment styles on the line element (`_segments`), so a redraw alone does not change the dash. The prototype sets the line's `borderDash` to `[]` for the focused brand in `beforeDatasetDraw`, makes the segment `borderDash` callback return `[]` for it, and clears `_segments` when the focus state flips. A production version can do the same in its chart plugin, or call `chart.update('none')` on focus change.

### Owner item 38 (2026-10-27): public launch labelled Beta (pending choice)
- Today: package `0.2.0b1` (`pyproject.toml:8`), git tag `v0.2.0-beta.1`, footer "Made with ❤️ in Yokohama. v0.2.0b1." (pinned by `tests/test_home_v22_browser.py:984`). In practice an invite-only alpha.
- Owner intent: the next release is public but tells users it is still beta.
- Agent recommendation: a "Beta" badge beside the masthead logo, footer "Beta · v1.0.0-beta.1", technical version `1.0.0b1` (PEP 440; ranks after `0.2.0b1`), then `1.0.0b2`… / optional `1.0.0rc1` / `1.0.0`, when the badge is removed. Alternative `0.3.0b1`. **Owner decision (2026-10-27, corrected): public version `1.0.0b1`, followed by the internal version in parentheses.** Footer example: "Made with ❤️ in Yokohama. v1.0.0b1 (0.3.0)." The two are separate numbers. The public version is a product label set by the owner (beta for the public launch, `1.0.0` when the badge comes off). The internal version stays the package version in `pyproject.toml` and the git tags, continuing its own sequence from `0.2.0b1`; its next value is the owner's choice (`0.3.0` is the example). Production: add a separate public-version setting beside `settings.APP_VERSION` (`core/context_processors.py`) and show both in `monitor/templates/monitor/_site_footer.html`; update README line 3 and the footer test at `tests/test_home_v22_browser.py:984`. Not the build or commit code (the earlier `RENDER_GIT_COMMIT` reading was wrong). Badge wording ("Beta") not yet confirmed.

### Owner item 39 (2026-10-27): logo locked in
- Numbering note: items 30–36 above were recorded by the separate logo session (tmux "design"); this session's 2026-10-27 items were renumbered from 30/31 to 37/38 to remove the clash. Items 30–36 have sections but no verbatim entries in the list above.
- **Wordmark (final):** PUSHINWEIGHT on one line, DM Sans italic capitals 15px, all ink. PUSHIN weight 500 with 0.06em letter spacing; WEIGHT weight 800, spacing 0. No apostrophe, no 走个量. Browser-tab title "PUSHINWEIGHT". The comparison options (Pushinweight, PushinWeight, the two-line stack of item 36) and the Text switch are removed from both prototypes; `?wm=` no longer has any effect.
- **Mark (one change):** where each handle leg meets the top of the weight, the straight seam (`M223 318 L340 318`, `M554 318 L662 318` in the traced path) is replaced by the front half of an ellipse 14 units deep (`A58.5 14 …`, `A54 14 …`), so the round handle reads as attached to the top. The inner side of each leg flows into the curve without a corner. Nothing else in the trace changed (the pixel steps on the handle curves remain).
- Applied to: homepage shell (`general-shell.js` `LINE_LOGO`, `screens/logo-line-favicon.svg`), the General logo prototype (`2026-10-26-decagon-line-logo/01-general/screens/review/`), and the source assets (`2026-10-26-decagon-line-logo/assets/`); `trace/logo_assets.py` applies the curve when rerun.
- Size study: `docs/ideation/mockups/qin-quan/2026-10-27-102536-logo-lockup-sizes.html` (before/after at 16–256 px, tab icon, lockup at 1–4×, 8× pixel zooms, prototype mastheads). At 16–29 px the curve is about one pixel deep and reads mainly as softer leg corners; it is clear from about 48 px up.

### Owner item 40 (2026-10-27): rounded-handle logo is final
- The line mark with the curved seams (item 39) is the only logo. Comparison switches are retired in both prototypes: the homepage ignores `?mark=current` and the remembered `gxmark` choice; the General prototype drops the Current/Bronze/Line buttons and `?mark=`, always showing the line mark and line tab icon. Verified with `?mark=current` and a stored old choice: masthead, rail General icon, tab icon and wordmark all show the final logo (homepage; General in en, ja, zh-cn); 0 page errors.
- Consistency fix: the homepage drawer label "Pushin’ Weight" now reads "PUSHINWEIGHT".
- Production: replace the `mark-quiet` symbol, the browser-tab icon and the masthead lettering with the final assets (`.context/compound-engineering/ce-prototype/2026-10-26-decagon-line-logo/assets/logo-line.svg`, `logo-line-favicon.svg`) and the wordmark rules in item 39.

### Owner item 41 (2026-10-27): General restyled like the homepage
Prototype: the live General page through the same relay, `http://100.102.74.50:8786/general/?lang=en` (also `zh-cn`, `ja`). New files in `01-general-skin/screens/`: `general-page-skin.css`, `general-page-shell.js`, and `gx-brand.js` (the locked logo and brand-logo map, now shared with the homepage shell). Relay: `skin_general()` and a `/general/` route; analytics stripped; text rewrites as on the homepage.

**Applied** (homepage change-list items in brackets):
- Page background `#f0f2f5` behind white panels, cards and rail; masthead white across the full width [2, 4]. Human view only; the dark Agent view keeps its own palette.
- Locked logo: line mark with curved seams in the masthead and the rail's General icon, line tab icon, PUSHINWEIGHT wordmark (italic caps on one line, PUSHIN 500 / WEIGHT 800), 走个量 and "Pushin'<br>Weight" removed, tab title and drawer label PUSHINWEIGHT [4].
- "Meta Llama" shown as "Meta": the "#Meta Llama" pills (38 on load) and refreshed feed items [11].
- Brand logos in brand pills for the 21 tracked brands (78 of 89 pills on load; other organizations such as Tsinghua University keep text only), also after refresh/"more" [13, 40].
- Shorter pending copy and "Audience Topic" rewrites run on General too [38, 39]; none of those strings appear on General today.

**Not applicable today:** General has no brand chart yet (Pulse charts read "not available yet"), so chart items [14, 21–35] carry over when the Pulse chart ships; it has no trending bar, filter dropdowns, flags, follower counts or footer [5–8, 15–20, 36–37, 41–43].

**Needs owner decision:** General's masthead "Weights: Open | Closed". The homepage renamed its brand tabs Open/Closed to Others/Giant [18]; on General the same words describe open vs closed model weights, so the rename was not applied.

Verified (Playwright, 2026-10-27): en, zh-cn and ja at 1440, 1100 and 390 px; gray page, white header/panels, wordmark visible and old lettering hidden, curved-seam mark, line tab icon, title, 78/78 tracked-brand pill logos with 0 broken images, 0 "Meta Llama", no horizontal overflow; logos persist after a panel refresh; Agent view unchanged apart from the wordmark; homepage regression check (logo, 21 legend logos, post logos) passes; 0 page errors and 0 HTTP errors.

### Owner item 42 (2026-10-27): /dashboard/each restyled like the homepage
`/dashboard/each` is built from the homepage (same stylesheet, trending chips, trend summary and feed) with its own per-brand chart (`pw-each-chart.js`): tabs for Sentiment, Post Type, Language, Role, Audience Topics, Geopolitical, Product and 3rd Party Brand Promotions, a % / count switch, and stacked category areas. Prototype: `http://100.102.74.50:8786/dashboard/each`.

**Applied:** the whole homepage skin and shell (gray page, white panels, rail, masthead with the locked logo and labelled controls, Meta-first chips, brand colors, Meta label, post brand logos, 12-hour English times, zh/ja follower counts, flags, shorter pending copy, Audience Topic); the chart in the same white panel with its tabs as General-style pills and a light chart area; tabs "Lang" → "Language" (en) and "Untracked Brand Promotions" → "3rd Party Brand Promotions" (zh 第三方品牌推广, ja サードパーティのブランドプロモーション); the chart's shared styling (right-hand value axis, dotted grid, monotone curves, no point markers, 300/240/200 px box) and localized time axis (1 day ends at the last fully harvested bucket and steps back whole hours; 7/30/365 days "Oct 27" / "10月27日" / "Oct 2026").
**Not applied (homepage brand-chart only):** per-brand line patterns, beacon shapes, beacons, focus/pinning, hover-to-solid and legend swatches. This chart's lines are categories of one brand, so those do not apply; its hover tooltip (category counts) stays.

Production notes:
- `pw-each-chart.js` formats its own x labels (`toLocaleTimeString` / `MM-DD`); production should build the axis from the payload's `days`, like the homepage, with the newest tick kept. Chart.js's tick thinning (its `maxTicksLimit: 8`) otherwise drops the newest tick.
- The 1-day payload (`/dashboard/each/chart/`) has the same empty, not-yet-harvested final buckets as the homepage (owner item 29); in % mode they show as gaps. Same fix: end at the last fully harvested bucket.
- Relay-only fix (not a production defect): the relay forced the Referer of every POST to the site root, so the language buttons on any page other than the homepage returned to the homepage. The relay now forwards the real referring page.

**Owner item 43 (resolves the open color/label question):** on every tab the "no data" categories (Unclassified, Undetected) and the catch-all categories (Neutral, Other, No assigned topic, No product signal) swap colors: no-data becomes light gray `#cbd5e1` and catch-all becomes black `#000000` (Role has only Other, now black). The stacked-area outlines are 1 px (were 1.4). English labels start with a capital ("Undetected", "Other"). Production: change the category colors and English labels where the each-chart entries are defined, and `borderWidth: 1` in `pw-each-chart.js`. Prototype: relay `restyle_each_entries`, shell `borderWidth = 1`. Verified en and zh_cn on all six affected tabs, 0 errors.

Verified (Playwright, 2026-10-27): en, zh_cn and ja; 1/7/30/365 days; all eight tabs; count mode; switching brand (chart, summary and feed follow; 50/50 post logos); 1440, 1100 and 390 px with no horizontal overflow; first-load post logos 48/50; homepage regression (21 lines, 15 patterned, 21 swatches, 50 post logos) unchanged; 0 page errors and 0 HTTP errors.

### Polymarket chart techniques and libraries (research for later choices)
Observed on the referenced Polymarket market page on 2026-10-22 (rendered DOM plus its JavaScript bundles):
- **Libraries:** Motion (formerly Framer Motion; MIT) for the ping and enter/exit animations (`motion.circle`, `AnimatePresence`, `useAnimate`); visx (Airbnb's React chart primitives; MIT) for axes, lines, areas and tooltips; d3-shape `curveMonotoneX` for smooth lines; react-spring; Tailwind `animate-ping`/`animate-pulse` for live badges; TradingView lightweight-charts (Apache-2.0) is also present in their bundle. Our homepage is plain JavaScript plus Chart.js, not React, so visx, `AnimatePresence` and react-spring do not drop in. Motion also ships a framework-free `animate()` that could be used, and Chart.js covers curves and line styles natively.
- **Techniques worth trying here:**
  1. *Line draw-in:* each line has a hidden copy with `pathLength=1` and an animated `stroke-dasharray` (0 1 → 1 1), so lines trace themselves left to right on load. On focus a thicker (2.75px) copy can trace over the line.
  2. *Hover crosshair dots:* at the hovered time, every line shows a 4px dot with a faint 2px ring (`stroke-opacity .1`), plus a date header and per-line values.
  3. *Direct end labels:* the line name and current value are printed at the line's end in its colour, with a background-coloured text outline (`-webkit-text-stroke` + `paint-order: stroke`) so they read over other lines, instead of a separate legend.
  4. *Smooth monotone curves* (Chart.js `cubicInterpolationMode: 'monotone'`) and dotted gridlines (`1,3`, 50% opacity). **Adopted (item 19).**
  5. *Entrance:* 0.15 s chart fade-in; a "live" radio-wave icon (two arcs pulsing 1.4 s, second arc delayed 200 ms).

## Open items before production
- **Giant (owner answer):** "Giant" = OpenAI, Anthropic, Google Gemini and SpaceXAI. None of these are among the 21 brands tracked today, so the Giant tab stays empty until they are added to collection, brand records and classification. Production needs that brand onboarding, then the tier assignment (Others = the current 21).
  - **Owner update (2026-10-27):** *"we will be separating 'giants' from the rest; the question remains whether meta is kept in 'rest' or sent to 'giants'; this will depend on how much the giants (oai, anthro) eclipse meta's post volume or not."* Meta's group is undecided until a volume comparison (OpenAI and Anthropic against Meta, on data collected after the 2026-10-25 Meta fix). Note: the homepage's default chart/feed selection is the non-Giant group (`monitor/views.py` `initial_filters` = `open_brands`), so a Giant Meta would leave the default view unless that changes. Handoff: `docs/handoffs/2026-10-27-152400-homepage-backend-prerequisites-handoff.md` (W2, W9).
- **Geopolitical help (owner answer: leave as is):** the globe icon stays deleted; the empty help trigger and its hidden explanation remain as they are.
- **Logos (owner answer: comfortable using them):** production may use these brand marks; choose the hosting source when implementing.
- **Similar colors (owner answer: a real problem):** addressed by hover/tap/pin focus with the ping (the automatic cycle was stopped by the owner).
- **Phone width:** chart x-axis labels crowd together; that comes from the existing chart code, unchanged.
- **Production implementation note:** the prototype achieved this with a relay plus a CSS/JS overlay. Production should change the real sources instead: `monitor/templates/monitor/home.html`, `home-v20.css`, the brand color source behind the chart payload `colors`/`pulse` accent colors, `pw-chart.js` (axis colors for a light surface, legend logos), `pw-locale-toggle.js` (i18n strings for the renamed labels), and the filter partials. Follow `.claude/skills/fix-ui/SKILL.md` regression and locale rules (including `zh_hans`).
