---
title: Cyber-Quan Visual Design Template and Qin-Quan Archive
date: 2026-08-24
updated: 2026-08-28
status: owner-locked-current-guidance
artifact_type: design_system_contract
ce_source: ce-prototype
production_status: cyber-quan-icons-deployed; usability-extensions-approved
---

# Cyber-Quan Visual Design Template

## Purpose and authority

Cyber-Quan is the current visual direction for the public product. It keeps
the production interface's utilitarian color system, native system typeface,
dense layout, whitespace rhythm, and compact button geometry. Its only
Qin-Quan inheritance is the recognizable SVG family drawn with uneven,
rough, cast-like strokes.

The earlier Qin-Quan full-page direction is archived later in this document.
Its ink-and-bronze palette, serif display type, editorial whitespace, and
decorative layout are **not active product guidance**. Do not use the archived
homepage mockup as a visual implementation target.

The production icon boundary and locked choices are detailed in the
[Cyber-Quan icon production plan](2026-08-26-085543-docs-qin-quan-ideation-plan.md).
Current production templates and styles remain the source of truth when a
measurement or interaction is not specified here.

## Active production system

### Information hierarchy

- Optimize first for a DevRel user scanning the latest important information
  on a phone. Functional priority outranks ornamental composition.
- Use position, size, and semantic color sparingly so the newest, largest, or
  most consequential signal is apparent without opening a detail view.
- Preserve production's compact content order and data density. Do not revive
  the Qin-Quan prototype's large display areas, ornamental panels, or generous
  editorial spacing.
- Keep controls visibly subordinate to the information they change. Retain
  the production button, pill, border, radius, and spacing conventions unless
  an approved interaction contract explicitly changes them.

### Production palette

| Role | Active value | Rule |
| --- | --- | --- |
| Page background | `#0b1220` | Default product ground |
| Card background | `#111827` | Panels and grouped information |
| Raised/control background | `#0f172a` | Compact controls and inset surfaces |
| Border | `#1f2937` | Separation without decorative framing |
| Primary text | `#f3f4f6` | Information and labels |
| Secondary text | `#94a3b8` | Metadata and de-emphasis |
| Selected state | `#3b82f6` | Selected or active state only |
| Positive / rising | `#10b981` | Positive sentiment and upward movement |
| Negative / falling | `#f87171` | Negative sentiment and downward movement |
| Mixed / warning | `#fbbf24` | Mixed sentiment and existing warning semantics |

Blue is reserved for selected or active state. It must not encode follower
reach, account role, sentiment, general importance, or decorative icon
identity. Unselected icons inherit the surrounding text or muted color unless
they carry an approved semantic tone.

The production chart keeps its existing series colors and redundant
discrimination cues. The archived Qin-Quan mineral chart palette below is not
an active series-to-color contract.

### Typography and naming

Use the production native system stack:

```css
-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
"Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif
```

Do not reintroduce the Qin-Quan serif display hierarchy. Measurements,
timestamps, and compact technical metadata may retain their existing
monospaced treatment where production already uses one.

The company name is one locked bilingual unit in every locale:
`走个量Pushin'Weight`. Preserve this order and the apostrophe in `Pushin'`.
Do not write `PushinWeight`, `Pushin Weight`, `Pushin' Weight` by itself, or
reverse the Chinese and English names when representing the company.

The compact masthead is the approved space-saving exception to inline
rendering. It may display mark A followed by `走个量`, then `Pushin'`, then
`Weight`, with `Pushin'` and `Weight` on separate lines. These lines still form
the same locked company unit.

### Layout, spacing, and controls

- Retain the production dark cards, thin borders, 10px card radii, compact
  control padding, pill-shaped filter and timezone controls, and tight panel
  rhythm.
- Retain the production mobile shell spacing and the established desktop
  content relationship. Cyber-Quan does not authorize a page reorder.
- Keep whitespace functional: enough to separate controls and scan groups,
  but never enough to push current information below the fold for appearance.
- Preserve fixed control geometry and one-line rails where production relies
  on them. A new icon must fit the existing control rather than enlarge the
  control around itself.
- Any English and Simplified Chinese mockups must be produced as a paired
  deliverable with the same hierarchy, geometry, state coverage, and icon
  registry.

## Active Cyber-Quan SVG language

### Drawing grammar

- Start from familiar, universal iconography rather than Chinese-script
  knowledge. A user should understand the silhouette before noticing its
  historical character.
- Express Qin-Quan influence through slightly uneven shoulders, off-axis
  balance, blunt rounded terminals, irregular curves, and rough stroke weight.
- Keep icons legible at production phone sizes. Avoid seal-script puzzles,
  excessive stylization, ornamental corrosion, and literal weight silhouettes
  repeated across the family.
- SVG paths inherit `currentColor`. Parent state owns presentation; symbol
  geometry does not embed application colors.
- Decorative instances are hidden from assistive technology. Visible text or
  the containing control owns the accessible name and state.

### Locked company and operational choices

| Meaning | Locked Cyber-Quan form | Archived alternatives |
| --- | --- | --- |
| Company mark | Mark A, Quiet Cast / 静铸 (`mark-quiet`) | Marks B-E |
| Hands-on use | Hand actively holding a Qin-era hammer | Chisel, keyboard, wrench, stop-hand |
| California locale | Rough outline of California | `CA` monogram |
| Beijing locale | Rough-stroke `京` character | Plain text glyph |
| Marketing reach | Center emitter separated from right-hand waves by clear negative space | Overlapping emitter/waves |
| Rising / falling | Rough trend form with an explicit up/down arrowhead | Ambiguous direction-only stroke |

The chisel and other alternatives remain useful design history, but they do
not map to production.

### Follower magnitude

Follower reach uses recognizable human forms plus the exact visible count.
The figure count and luminance increase together so magnitude reads at a
glance without using blue.

| Existing bin | Symbol | Color |
| --- | --- | --- |
| `0-1k` | One human form | `#64748b` |
| `1k-10k` | Two human forms | `#8492a6` |
| `10k-50k` | Three human forms | `#cbd5e1` |
| `50k-plus` | Four human forms | `#f8fafc` |

The lowest bin is deliberately obscured gray and the highest approaches
white. The count remains visible and owns the precise meaning; color and
figure count are redundant scan cues, not substitutes for text or an
accessible follower label.

### Sentiment and account roles

Sentiment keeps its established production semantics:

- positive: production green `#10b981`;
- neutral: production slate `#94a3b8`;
- negative: production red `#f87171`;
- mixed: production amber `#fbbf24`.

Account role uses one rough credential-badge outline in three distinct tones:

| Role | Color |
| --- | --- |
| Official | Amber `#fbbf24` |
| Staff | Violet `#c4b5fd` |
| Community | Green `#86efac` |

Place the role badge in its own reserved slot directly under the follower
count. Accounts without one of these roles keep the empty slot so adjacent row
geometry does not jump. If one account has multiple mapped roles, display
`official` before `staff` before `community`; filtering may still evaluate the
complete role set. Follower and role accessible labels remain independent.

### Semantic filter icons

When a filter option represents a signal that already has a Cyber-Quan icon in
the feed, place that same icon before its localized name in the dropdown. This
replaces emoji prefixes; it does not create a second visual vocabulary.

- Sentiment options use the matching sentiment face and its semantic tone.
- Post-type options use the matching operational pictogram.
- Official, staff, and community options use the shared credential badge and
  the role tones above.
- Discourse, nationalism, and unsanctioned-state options use their matching
  Cyber-Quan symbols.
- Brand and language options remain text-only unless the owner approves an
  icon for them. Do not invent one merely to fill the row.
- Stable filter keys, checkbox defaults, labels, dropdown geometry, and filter
  behavior do not change because an icon is present.

## Approved compact interaction conventions

These conventions extend the production information-first system. They do not
authorize a broader layout or palette redesign.

### Feed text

- Clicking feed text cycles its available text layers and expands the row in
  the same action.
- Simplified Chinese cycles synthesis (`综合`), literal (`直译`), then source
  (`原文`). It does not insert English as the third state.
- Mobile clamps to three lines by default and at most nine while expanded.
  Desktop clamps to four lines by default and at most twelve while expanded.
  The expanded row therefore stays within three times its default text height.
- Keep the complete selected text in the document; use visual clamping rather
  than destructive string truncation. Clicking outside collapses the row.

### Headlines

- Secondary headline detail is hidden by default.
- A localized link-style `detail` / `详情` control sits at the end of the title
  and reveals the secondary text in place.
- A localized `hide` / `收起` control follows the secondary text. Clicking the
  secondary text itself also hides it.
- Disclosure state, keyboard operation, focus behavior, `aria-expanded`, and
  `aria-controls` must agree. Refreshed headlines return to the collapsed
  default.

### One-line identity

Keep the feed display name or handle and its immutable metadata on one line.
The identity segment yields first and uses a true ellipsis; timestamps, age,
and status metadata remain visible. Preserve the complete identity in the
link title or equivalent accessible text.

## Implementation boundary

- Production color, typography, spacing, control, content-order, and behavior
  remain protected unless this document names a narrow exception.
- New SVGs must use the shared allowlisted sprite and semantic mapping. Unknown
  runtime keys render no SVG rather than accepting data-derived fragment IDs.
- Server-rendered and asynchronously refreshed rows must select the same icon,
  tone, order, label, and geometry.
- Every icon must resolve to nonzero geometry at desktop and narrow phone
  widths without horizontal overflow.
- Keep current locale, timezone, filter, chart, headline, feed, and
  accessibility behavior while changing presentation.
- Treat `monitor/static/home-v20.css` and
  `monitor/templates/monitor/home.html` as current production references, not
  the archived Qin-Quan homepage HTML.

## Archived Qin-Quan exploration — historical record only

The following material explains the source exploration. It is deliberately
preserved so future work can understand what was tested and rejected. Nothing
in this section overrides the active Cyber-Quan rules above.

### Archived full-page principles

The Qin-Quan candidate explored ancient Chinese cast form through proportion,
asymmetry, weight, and negative space. It avoided imitation calligraphy,
inscriptions, corrosion effects, ornamental borders, and arbitrary historical
motifs. This produced an attractive editorial treatment, but the owner and
user feedback found production more readable and usable for a utilitarian
mobile dashboard.

The candidate proposed Songti SC / STSong for Chinese display hierarchy,
PingFang SC / Hiragino Sans GB for Chinese interface copy, and Iowan Old Style
for English display hierarchy. Those display-font proposals are shelved.

### Archived Qin-Quan palette

| Prototype role | Archived value |
| --- | --- |
| Primary ground / Ink | `#100F0D` |
| Raised ground / Warm ink | `#171512` |
| Primary text / Bone | `#EEE8DC` |
| Secondary text / Dim bone | `#B8AFA1` |
| Selection and brand memory / Bronze | `#BD8B50` |
| Positive / Jade | `#7CC7A6` |
| Negative / Cinnabar | `#E16D58` |

The archived chart study assigned Jade `#7CC7A6`, Cinnabar `#E16D58`,
Azurite `#73A7D8`, Violet `#B78AC8`, Turquoise `#63BDB5`, Orpiment
`#E2BC58`, Coral `#E79A75`, and Chalk `#D8D1C5` to model series with
different dash rhythms and marker shapes. These are prototype records, not
current brand-to-color assignments.

### Preserved artifacts

- [English original icon study](../ideation/mockups/qin-quan/2026-08-19-184954-qin-quan-icon-study-en.html)
- [Simplified Chinese original icon study](../ideation/mockups/qin-quan/2026-08-19-184954-qin-quan-icon-study-zh-cn.html)
- [Archived Qin-Quan homepage direction](../ideation/mockups/qin-quan/2026-08-24-162101-qin-quan-homepage-zh-cn.html)
- `.context/compound-engineering/ce-prototype/2026-08-28-cyber-quan-svg-study-production/`
  retains the paired production-restyle, rejected small-seal expansion, final
  rough SVG family, decisions, and browser evidence.
- `.context/compound-engineering/ce-prototype/2026-08-28-cyber-quan-mobile-utility/`
  retains the earlier mobile-at-a-glance experiment. Its blue follower
  treatment and proposed mobile page reorder were superseded and are not
  active guidance.

### Rejected and superseded directions

- Small-seal characters for operational signals were rejected because meaning
  depended too heavily on knowledge of Chinese script and the result was too
  stylized.
- The full Qin-Quan palette, display type, editorial spacing, and layout were
  shelved in favor of the production system.
- Follower blue was replaced by the locked gray-to-white magnitude ramp.
- Mark A replaced the unresolved A-E mark study.
- The Qin hammer replaced the chisel, keyboard, wrench, and stop-hand studies
  for hands-on use.
- The California outline and rough `京` replaced the `CA` monogram and plain
  text glyph.

## Continuing the design system

1. Begin with the active production system and this Cyber-Quan contract.
2. For a new icon, make the universal silhouette intuitive first, then apply
   the rough uneven-stroke grammar. Produce English and Simplified Chinese
   examples together.
3. Keep exploration in a new CE prototype run; never overwrite the preserved
   Qin-Quan or Cyber-Quan evidence.
4. Record an owner choice here before promoting a new palette, typeface,
   layout, color meaning, company-name variant, or icon into production.
5. Implement only through an approved plan with regression coverage for the
   existing desktop, narrow-phone, bilingual, keyboard, and asynchronous
   rendering paths.
