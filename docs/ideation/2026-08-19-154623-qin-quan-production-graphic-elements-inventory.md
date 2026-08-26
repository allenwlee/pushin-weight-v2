---
title: Qin Quan production graphic elements inventory
date: 2026-08-19
status: preserved-ideation
artifact_type: design-research
production_status: historical-snapshot
---

# Production graphic elements inventory

> Historical research for the preserved Qin Quan direction. This is not the
> current production inventory or an implementation authorization.

Last updated: 2026-08-19-15:46:23 JST

## Production boundary

This inventory describes the graphics shipped at production revision
`bfc66fdf1646e17441becf10baa27d2977328d95` on 2026-08-19. The revision came
from the read-only `./bin/ollija status --json` result. The public page was
also inspected at `https://pushinweight-web.onrender.com/` at 15:50 JST.

The inventory includes:

- application-authored emoji, symbol glyphs, icon-like text, charts, markers,
  generated avatars, color swatches, and semantic background treatments;
- the public `/` page;
- the deployed authenticated `/brands/<brand>/` and `/internal/` templates,
  even though an unauthenticated production browser is redirected to
  `/accounts/login/` before those templates render;
- both the server-rendered and client-rendered feed paths.

It does not treat punctuation inside ordinary prose as graphics. It also does
not enumerate emoji contained in posts fetched from X or generated narrative
copy: those values are unbounded content passed through the UI, not graphic
choices authored by this repository. That passthrough is documented
separately below. Ordinary component chrome such as every card border, rounded
button, hover fill, and text color is treated as layout/styling rather than as
a separately inventoried graphic; semantic or icon-like treatments are
included.

Source line numbers in this document refer to the production revision above,
not necessarily the current checkout.

## Summary

The production UI has 35 distinct non-ASCII application-authored visual
glyphs when the structural separators, status ellipsis, and authenticated
legacy variants are included:

```text
🌅 ☀️ 🌆 🌙
😊 😶 🙁 😐
🤚 📊 📢 ❓ 円 📅
🖬 🇨🇳 🇺🇸 🚫
👥 ♥ ↻ 💬
▲ ▼ →
☆ ▾ ⇄ ←
★ ♡ ↺
· — …
```

All of them are Unicode text rendered by the browser's system-font fallback.
There is no bundled emoji font, icon font, or icon library, so their exact
appearance can vary by OS and browser.

There are no production runtime raster or vector image assets. At the audited
production revision:

- the live public DOM contained zero `<img>` elements and zero `<svg>`
  elements;
- the live public DOM contained one Chart.js `<canvas>`;
- the Git tree's PNG files are documentation screenshots or the retired v1
  schema image, not runtime UI assets;
- no current Django template references an image, favicon, SVG, webfont, or
  CSS `url(...)` asset.

## Application-authored glyphs

### Time-of-day indicator

The timezone pill chooses one emoji from the hour in the active timezone. It
shows browser-local time by default and `America/Los_Angeles` after the user
toggles it.

| Glyph | Unicode | Use | Associated code |
| --- | --- | --- | --- |
| 🌅 | `U+1F305` SUNRISE | 05:00 through 07:59 | `if (hour >= 5 && hour < 8) return '🌅';` |
| ☀️ | `U+2600 U+FE0F` SUN + emoji variation selector | 08:00 through 16:59; also the server-rendered initial value | `if (hour >= 8 && hour < 17) return '☀️';` |
| 🌆 | `U+1F306` CITYSCAPE AT DUSK | 17:00 through 19:59 | `if (hour >= 17 && hour < 20) return '🌆';` |
| 🌙 | `U+1F319` CRESCENT MOON | 20:00 through 04:59 | `return '🌙';` |

Sources: `monitor/static/pw-tz.js:49-54` and
`monitor/templates/monitor/home.html:67-74`.

```js
function dayEmoji(hour) {
  if (hour >= 5 && hour < 8) return '🌅';
  if (hour >= 8 && hour < 17) return '☀️';
  if (hour >= 17 && hour < 20) return '🌆';
  return '🌙';
}
```

### Sentiment faces

The right-hand signal column of each public feed row shows one or more faces
for the sentiment classifications attached to that post. The whole signal
column is `aria-hidden`; sentiment is represented visually, while the row
background tint provides a second color cue.

| Glyph | Unicode | Classification | Associated code |
| --- | --- | --- | --- |
| 😊 | `U+1F60A` SMILING FACE WITH SMILING EYES | `positive` | `positive: '\uD83D\uDE0A'` |
| 😶 | `U+1F636` FACE WITHOUT MOUTH | `neutral` | `neutral: '\uD83D\uDE36'` |
| 🙁 | `U+1F641` SLIGHTLY FROWNING FACE | `negative` | `negative: '\uD83D\uDE41'` |
| 😐 | `U+1F610` NEUTRAL FACE | `mixed` | `mixed: '\uD83D\uDE10'` |

Source: `monitor/static/pw-feed.js:203-208`. Rendering is performed by
`paintSignals()` at lines 237-265 and is applied to both the initial SSR rows
and subsequently fetched rows by `hydrateRows()`.

```js
var SENT_FACE = {
  positive: '\uD83D\uDE0A',
  neutral:  '\uD83D\uDE36',
  negative: '\uD83D\uDE41',
  mixed:    '\uD83D\uDE10'
};

elS.textContent = sents.map(function (key) {
  return SENT_FACE[key] || '';
}).join('');
```

### Post-type symbols

The second row of the public feed signal column shows one or more symbols for
the post-type classifications. `円` is intentionally used as an icon, not as
ordinary Japanese text.

| Glyph | Unicode | Classification | Associated code |
| --- | --- | --- | --- |
| 🤚 | `U+1F91A` RAISED BACK OF HAND | `hands_on_usage` | `hands_on_usage: '\uD83E\uDD1A'` |
| 📊 | `U+1F4CA` BAR CHART | `performance_comparisons` | `performance_comparisons: '\uD83D\uDCCA'` |
| 📢 | `U+1F4E2` PUBLIC ADDRESS LOUDSPEAKER | `buzz_releases` | `buzz_releases: '\uD83D\uDCE2'` |
| ❓ | `U+2753` BLACK QUESTION MARK ORNAMENT | `feedback_questions` | `feedback_questions: '\u2754'` |
| 円 | `U+5186` CJK IDEOGRAPH FOR YEN | `advertising_marketing` | `advertising_marketing: '\u5186'` |
| 📅 | `U+1F4C5` CALENDAR | `event_announcement` | `event_announcement: '\uD83D\uDCC5'` |

Source: `monitor/static/pw-feed.js:209-221`.

```js
var POST_TYPE_EMOJI = {
  hands_on_usage:          '\uD83E\uDD1A',
  performance_comparisons: '\uD83D\uDCCA',
  buzz_releases:           '\uD83D\uDCE2',
  feedback_questions:      '\u2754',
  advertising_marketing:   '\u5186',
  event_announcement:      '\uD83D\uDCC5'
};
```

### Nationalism and unsanctioned markers

The third and fourth signal rows indicate non-`none` nationalism
classifications and the unsanctioned flag.

| Glyph | Unicode | Use | Associated code |
| --- | --- | --- | --- |
| 🖬 | `U+1F5AC` SOFT SHELL FLOPPY DISK | Literal prefix plus `:` before any nationalism flags. This is the actual encoded character, even if a platform font makes it look like a different pictogram. | `'<span class="sig-nat-prefix">\uD83D\uDDAC:</span> '` |
| 🇨🇳 | `U+1F1E8 U+1F1F3` regional indicators C + N | A non-`none` China-nationalism value is present. | `showCn ? '\uD83C\uDDE8\uD83C\uDDF3' : ''` |
| 🇺🇸 | `U+1F1FA U+1F1F8` regional indicators U + S | A non-`none` US-nationalism value is present. | `showUs ? '\uD83C\uDDFA\uD83C\uDDF8' : ''` |
| 🚫 | `U+1F6AB` NO ENTRY SIGN | The post is marked unsanctioned. | `elU.textContent = '\uD83D\uDEAB';` |

Source: `monitor/static/pw-feed.js:237-264`.

```js
var flags = (showCn ? '\uD83C\uDDE8\uD83C\uDDF3' : '') +
            (showUs ? '\uD83C\uDDFA\uD83C\uDDF8' : '');
elN.innerHTML = '<span class="sig-nat-prefix">\uD83D\uDDAC:</span> ' + flags;

if (isUn) elU.textContent = '\uD83D\uDEAB';
```

### Public-feed engagement symbols

These four symbols are injected with CSS pseudo-elements before the numeric
engagement counters on every public feed row.

| Glyph | Unicode | Use | Associated code |
| --- | --- | --- | --- |
| 👥 | `U+1F465` BUSTS IN SILHOUETTE | Author follower count | `.followers::before { content: "👥 "; }` |
| ♥ | `U+2665` BLACK HEART SUIT | Like count, colored red | `.likes::before { content: "♥ "; color: #f87171; }` |
| ↻ | `U+21BB` CLOCKWISE OPEN CIRCLE ARROW | Retweet count, colored green | `.rts::before { content: "↻ "; color: var(--up); }` |
| 💬 | `U+1F4AC` SPEECH BALLOON | Reply count | `.replies::before { content: "💬 "; }` |

Source: `monitor/static/home-v20.css:669-680`.

### Trend, score, navigation, and control glyphs

| Glyph | Unicode | Surface and use | Associated code |
| --- | --- | --- | --- |
| ▲ | `U+25B2` BLACK UP-POINTING TRIANGLE | Prefixes an upward pulse-chip percentage on `/`. | `.pulse-chip .delta.up::before { content: "▲ "; }` |
| ▼ | `U+25BC` BLACK DOWN-POINTING TRIANGLE | Prefixes a downward pulse-chip percentage on `/`. | `.pulse-chip .delta.down::before { content: "▼ "; }` |
| → | `U+2192` RIGHTWARDS ARROW | Prefixes a flat pulse-chip percentage on `/`. | `.pulse-chip .delta.flat::before { content: "→ "; }` |
| ☆ | `U+2606` WHITE STAR | Labels the follower-derived Top voices score in the headline strip and each voice chip. | `'(☆ ' + entry.voice_star + ')'` |
| ▾ | `U+25BE` BLACK DOWN-POINTING SMALL TRIANGLE | Dropdown caret on each of the seven filter pills; rotates 180 degrees while open. | `<span class="carat" aria-hidden="true">▾</span>` |
| ⇄ | `U+21C4` RIGHTWARDS ARROW OVER LEFTWARDS ARROW | Indicates that the timezone pill toggles local and California time. | `setHTML(pair, active === 'ca' ? '⇄ ' + localLabel() : '⇄ ' + CA_ICON_HTML)` |
| ← | `U+2190` LEFTWARDS ARROW | Back-to-multi-brand link on the authenticated single-brand page. | `{% trans "← multi-brand" %}` |

Sources:

- `monitor/static/home-v20.css:221-229`
- `monitor/templates/monitor/home.html:107-226,274-283`
- `monitor/static/pw-chart.js:286-313`
- `monitor/static/pw-tz.js:85-102`
- `monitor/templates/monitor/brand_home.html:27-31`

### Authenticated legacy-feed variants

The deployed `/brands/<brand>/` and `/internal/` templates use the legacy feed
partial after authentication. Two engagement concepts use different glyphs
there than on the public page, and a black star is also displayed under the
translated text.

| Glyph | Unicode | Use | Associated code |
| --- | --- | --- | --- |
| ★ | `U+2605` BLACK STAR | Extra like count below the translated-text cell. | `&#9733; {{ row.like_count }}` |
| 👥 | `U+1F465` BUSTS IN SILHOUETTE | Follower count, same glyph as public feed. | `&#128101;` |
| ♡ | `U+2661` WHITE HEART SUIT | Like count; outline variant instead of public feed's `♥`. | `&#9825;` |
| ↺ | `U+21BA` ANTICLOCKWISE OPEN CIRCLE ARROW | Retweet count; opposite direction from public feed's `↻`. | `&#8634;` |
| 💬 | `U+1F4AC` SPEECH BALLOON | Reply count, same glyph as public feed. | `&#128172;` |

Source: `monitor/templates/monitor/_feed_initial_legacy.html:26-34,95-100`.

### Structural markers

These are symbolic UI markers rather than emoji, but they are included for
completeness because the templates use them visually.

| Glyph | Unicode | Use | Associated code |
| --- | --- | --- | --- |
| · | `U+00B7` MIDDLE DOT | Separates counts, metadata, time/window labels, and the `Trending · 24h heat` heading. | Example: `· {{ row.meta_text }}` |
| — | `U+2014` EM DASH | Empty-brand placeholder in the authenticated legacy feed and prose separator in the spend stub. | `<span class="pill muted">—</span>` |
| … | `U+2026` HORIZONTAL ELLIPSIS | Indicates an in-progress loading state in the public and authenticated feeds. | `{% trans "loading more…" %}` |

Primary sources:
`monitor/templates/monitor/home.html`,
`monitor/templates/monitor/_feed_initial_v22.html`,
`monitor/templates/monitor/_feed_initial_legacy.html`,
`monitor/templates/monitor/brand_home.html`, and
`monitor/templates/monitor/home_internal.html`.

## Programmatic and CSS-drawn graphics

### California monogram badge

`CA` is rendered as a small amber-gradient badge in the timezone pill and in
California-mode feed timestamps. It is icon-like text, not an image or SVG.

```js
var CA_ICON_HTML =
  '<span class="tz-ca-icon" title="California" aria-label="California">CA</span>';
```

```css
.tz-ca-icon {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: linear-gradient(145deg, #f59e0b 0%, #b45309 100%);
  color: #111827;
}
```

Sources: `monitor/static/pw-tz.js:8-10` and
`monitor/static/home-v20.css:682-725`.

### Multi-brand line chart and point markers

The public home chart is a Chart.js canvas. Each brand is drawn as a
two-pixel line in its accent color. Five-minute data also has 1.5-pixel point
markers and a curve tension of `0.3`; coarser data has no point markers.
Chart.js draws the axes, grid, and hover tooltip inside the same canvas.

```html
<canvas class="home-chart"
        aria-label="{% trans "Daily total posts per brand" %}"
        data-home='{{ payload }}'></canvas>
```

```js
datasets.push({
  label: brand + ' (total)',
  data: totalData,
  type: 'line',
  borderColor: stroke,
  backgroundColor: stroke,
  borderWidth: 2,
  pointRadius: granularity === 'minute' ? 1.5 : 0,
  tension: granularity === 'minute' ? 0.3 : 0,
  fill: false
});
```

Sources: `monitor/templates/monitor/_home_chart.html:1-5` and
`monitor/static/pw-chart.js:89-179`. Chart.js 4.4.0 is loaded from the unpkg
CDN by `monitor/templates/monitor/home.html:10-15`.

### Chart legend color dots

The public chart's HTML legend is separate from the canvas. One six-pixel
round dot is generated for each brand series, using the same color as its
line. The live audit saw 32 dots; the count is data-dependent.

```js
legend.innerHTML = Object.keys(payload.series).map(function (brand) {
  return '<span><i style="background:' +
    escapeHtml((payload.colors || {})[brand] || '#9ca3af') +
    '"></i>' + escapeHtml(BRAND_NAMES[brand] || brand) + '</span>';
}).join('');
```

```css
.legend i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}
```

Sources: `monitor/static/pw-chart.js:195-208` and
`monitor/static/home-v20.css:419-430`.

### Authenticated single-brand stacked-area chart

The `/brands/<brand>/` page renders a second Chart.js canvas after login. The
active classification tab is visualized as stacked colored areas with
transparent borders; inactive tab datasets are hidden.

```html
<canvas class="home-brand-chart"
        aria-label="{% trans "Single-brand stacked-area chart" %}"
        data-brand-chart='{{ payload|safe }}'></canvas>
```

```js
datasets.push({
  label: tab + ': ' + cat,
  data: brandData,
  type: 'line',
  borderColor: 'transparent',
  backgroundColor: colorForCategory(tab, cat),
  borderWidth: 0,
  pointRadius: granularity === 'minute' ? 1.5 : 0,
  fill: datasets.length === 0 ? 'origin' : '-1',
  hidden: tab !== activeTab
});
```

Sources: `monitor/templates/monitor/_brand_chart.html:1-4` and
`monitor/static/pw-brand-chart.js:21-102`.

### Generated initial avatars

Feed rows do not load X profile images. They use a round, colored text avatar:
one or two alphanumeric characters from the handle over a stable HSL color
derived from that handle. An unknown/empty handle uses `?` on 50% gray. The
live public audit saw 49 avatars in the loaded feed; the count varies with
the result set.

```python
def _avatar_initials(handle: str) -> str:
    h = (handle or "").lstrip("@").strip()
    if not h:
        return "?"
    chars = [c for c in h if c.isalnum()]
    if not chars:
        return "?"
    if len(chars) == 1:
        return chars[0].upper()
    return (chars[0] + chars[1]).upper()

def _avatar_color(handle: str) -> str:
    h = (handle or "").lstrip("@").strip().lower()
    if not h:
        return "hsl(0, 0%, 50%)"
    n = 5381
    for ch in h:
        n = ((n << 5) + n) + ord(ch)
        n &= 0xFFFFFFFF
    return f"hsl({n % 360}, 55%, 45%)"
```

```html
<span class="avatar" style="background: {{ row.avatar_color }}"
      aria-hidden="true">{{ row.avatar_initials }}</span>
```

```css
.feed-row .avatar {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: white;
}
```

Sources: `monitor/views.py:458-481,687-704`,
`monitor/templates/monitor/_feed_initial_v22.html:23-25`,
`monitor/static/pw-feed.js:169-186`, and
`monitor/static/home-v20.css:625-635`.

### Filter-status dots

Every public filter pill begins with a six-pixel round marker. It is an empty
muted ring when the checkboxes match their defaults and a solid blue dot when
at least one checkbox differs. The live page had seven, one for each filter
group.

```html
<span class="status-dot is-default" aria-hidden="true"></span>
```

```js
var changed = false;
boxes.forEach(function (box) {
  if (box.checked !== box.defaultChecked) changed = true;
});
dot.classList.toggle('is-changed', changed);
dot.classList.toggle('is-default', !changed);
```

```css
.filter-pill .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.filter-pill .status-dot.is-default {
  background: transparent;
  border: 1px solid var(--muted);
}
.filter-pill .status-dot.is-changed {
  background: var(--accent);
  border: 1px solid var(--accent);
}
```

Sources: `monitor/templates/monitor/home.html:107-226`,
`monitor/static/pw-filter-pills.js:111-125`, and
`monitor/static/home-v20.css:277-296`.

### Pulse-chip accent rails

Every model in the Trending/Pulse bar is a rounded chip with a three-pixel
left rail in the model's data-provided accent color. This provides a visual
brand key before the up/down/flat glyph.

```html
<button class="pulse-chip"
        style="--chip-color:{{ entry.accent_color }}">
```

```css
.pulse-chip {
  border: 1px solid var(--border);
  border-left: 3px solid var(--chip-color, var(--accent));
  border-radius: 6px;
}
```

Sources: `monitor/templates/monitor/home.html:83-96`,
`monitor/static/pw-chart.js:210-245`, and
`monitor/static/home-v20.css:191-229`.

### Headline gradient card and animated pulse dot

The Trend summary is a purple gradient card. Its kicker begins with a glowing
seven-pixel pink dot whose opacity pulses every two seconds. The dot is
decorative and `aria-hidden`.

```html
<section class="headline-strip" role="region" ...>
  <div class="kicker">
    <span class="pulse" aria-hidden="true"></span>
```

```css
.headline-strip {
  background: linear-gradient(135deg, #1e1b4b 0%, #4c1d95 100%);
  border: 1px solid #7c3aed;
}
.headline-strip .pulse {
  width: 7px;
  height: 7px;
  background: var(--kimi);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--kimi);
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

Sources: `monitor/templates/monitor/home.html:250-289` and
`monitor/static/home-v20.css:432-497`.

### Feed sentiment tints and multi-sentiment gradients

The public feed adds a translucent row background based on sentiment. Single
sentiments use a flat green, red, or purple tint. Combined classifications use
two- or three-stop horizontal gradients. Neutral has no tint.

```python
if has_p and has_n and has_m:
    return "tint-pos-neg-mixed"
if has_p and has_n:
    return "tint-pos-neg"
if has_p and has_m:
    return "tint-pos-mixed"
if has_n and has_m:
    return "tint-neg-mixed"
if has_p:
    return "tint-positive"
if has_n:
    return "tint-negative"
if has_m:
    return "tint-mixed"
return "tint-neutral"
```

```css
.feed-row-shell.tint-positive { background: rgba(16, 185, 129, 0.25); }
.feed-row-shell.tint-negative { background: rgba(248, 113, 113, 0.25); }
.feed-row-shell.tint-mixed    { background: rgba(168, 85, 247, 0.25); }
.feed-row-shell.tint-neutral  { background: transparent; }
.feed-row-shell.tint-pos-neg {
  background: linear-gradient(90deg,
    rgba(16,185,129,0.25) 0%, rgba(248,113,113,0.25) 100%);
}
.feed-row-shell.tint-pos-mixed {
  background: linear-gradient(90deg,
    rgba(16,185,129,0.25) 0%, rgba(168,85,247,0.25) 100%);
}
.feed-row-shell.tint-neg-mixed {
  background: linear-gradient(90deg,
    rgba(248,113,113,0.25) 0%, rgba(168,85,247,0.25) 100%);
}
.feed-row-shell.tint-pos-neg-mixed {
  background: linear-gradient(90deg,
    rgba(16,185,129,0.25) 0%,
    rgba(168,85,247,0.25) 50%,
    rgba(248,113,113,0.25) 100%);
}
```

Sources: `monitor/views.py:615-635` and
`monitor/static/home-v20.css:551-585`.

### Authenticated brand swatches

The `/internal/` filter panel shows an eight-pixel rounded-square swatch for
each brand. The single-brand page shows one locked swatch. The color comes
from `brand.accent_color` with the normal server-side fallback.

```html
<span class="swatch" style="background: {{ brand.accent_color }};"></span>
```

```css
.control-row .swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: var(--muted);
}
```

Sources: `monitor/templates/monitor/home_internal.html:64-74`,
`monitor/templates/monitor/brand_home.html:70-79`, and
`monitor/static/dashboard.css:412-430`.

### Browser-native markers and controls

Two small graphic families are delegated to the browser instead of custom
assets:

- default list bullets for the Trend summary observations, from
  `<ul class="headline-observations"><li>...</li></ul>` in
  `monitor/templates/monitor/home.html:268-272`;
- native checkbox boxes/checkmarks in the public filter dropdowns and the
  authenticated filter panels. The CSS changes layout and cursor only; it does
  not replace the native checkbox drawing.

Because these are platform-native controls, their exact pixels vary by
browser and OS.

## Dynamic content that can contain arbitrary emoji

Posts from X may contain any Unicode emoji or symbol. The live audit did show
such post-authored emoji, but they are not stable repo inventory items. The
server-rendered path outputs the selected text field as content:

```django
{{ row.text_translated|default:row.text_original|default:row.text|default:'NULL' }}
```

The client-rendered path escapes the fetched value and preserves its Unicode:

```js
escapeHtml((row.text_translated || row.text_en || row.text || '')
  .toString().slice(0, 600))
```

Sources: `monitor/templates/monitor/_feed_initial_v22.html:42-49` and
`monitor/static/pw-feed.js:130-137,178-180`.

The generated Trend summary and observations are similarly inserted as text
with `textContent` in `monitor/static/pw-chart.js:252-284`. Their punctuation
or emoji, if any, comes from the current narrative data rather than a fixed
graphic mapping.

## Shipped files deliberately excluded from the production inventory

| File or family | Why excluded |
| --- | --- |
| `docs/iterations/**/*.png`, `docs/screenshots/*.png` | Documentation and comparison screenshots only; no runtime template references them. |
| `docs/reference/images/xmonitor-schema-post-batch.png` | Explicitly retired v1 schema image. |
| `x_monitor/templates/**` and `x_monitor/static/**` | Retired Flask/v1 presentation layer; production serves the Django `monitor` app. |
| `monitor/static/combined-chart.js` | Shipped static file but no current Django template loads a `canvas.combined-chart` or this script. |
| `monitor/static/trend-chart.js` | Shipped static file but no current Django template loads a `canvas.trend-chart` or this script. |
| Treemap, sparkline, and badge rules retained in `monitor/static/dashboard.css` | No current production Django template emits their required DOM. |
| Emoji found in tests, docs, comments, logs, or management-command output | Not a production UI graphic. |

## Verification notes

The live browser check established the following at the audit instant:

| Check | Result |
| --- | --- |
| Public page title | `走个量 Pushin' Weight` |
| Public `<img>` count | `0` |
| Public `<svg>` count | `0` |
| Public `<canvas>` count | `1` |
| Generated `.avatar` count | `49` |
| Non-empty signal-row count | `98` |
| Filter `.status-dot` count | `7` |
| Chart `.legend i` count | `32` |
| First live signal pair | `😊` and `🤚` |
| Timezone widget at 15:50 JST | `☀️ 15:50 本地 ⇄ CA` |
| `/brands/deepseek/` unauthenticated | Redirected to `/accounts/login/?next=/brands/deepseek/` |
| `/internal/` unauthenticated | Redirected to `/accounts/login/?next=/internal/` |
| Login page image/SVG/canvas counts | `0 / 0 / 0` |

Counts tied to feed rows, brands, or current time are observations, not fixed
contracts. The code mappings and asset-absence findings are the durable parts
of this inventory.

## Maintenance rule

Update this inventory whenever a production UI change adds, removes, or
repurposes:

- a Unicode glyph or CSS `content` string;
- an image, SVG, icon/font dependency, favicon, or CSS image URL;
- a canvas/SVG visualization;
- a generated marker such as an avatar, legend dot, status dot, swatch, or
  semantic tint.

Verify the deployed production revision first, then reconcile the public page,
the authenticated templates, and both SSR/CSR feed renderers. Do not infer
production graphics from mockups, screenshots, retired `x_monitor` templates,
or shipped-but-unreferenced static files.
