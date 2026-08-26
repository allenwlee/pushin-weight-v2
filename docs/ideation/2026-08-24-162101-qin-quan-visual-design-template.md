---
title: Qin Quan Visual Design Template
date: 2026-08-24
status: preserved-candidate
artifact_type: visual_direction
ce_source: ce-prototype
production_status: not-approved
---

# Qin Quan Visual Design Template

## Purpose

This package preserves a possible future visual direction for PushinWeight. It applies the product's Qin bronze weight (*quan*) inspiration to a restrained, mostly colorless interface without requiring users to understand the historical reference.

This is a design candidate, not a production contract or implementation plan. The current production interface remains the source of truth until the owner explicitly approves an upgrade.

## Storage model

The work intentionally lives in two layers:

1. `.context/compound-engineering/ce-prototype/` retains the gitignored `/ce-prototype` runs, decision capsules, screenshots, and iteration history.
2. `docs/ideation/` retains this tracked overview, while `docs/ideation/mockups/qin-quan/` retains curated standalone HTML snapshots that future work can open without reconstructing the original sessions.

This separation keeps exploratory CE state out of production documentation while preserving a stable, reviewable design candidate in the repository.

## Design principles

### Quiet Chinese memory

- Reference ancient Chinese cast form through proportion, asymmetry, weight, and negative space.
- Avoid decorative “Chineseness”: no imitation calligraphy, seals, inscriptions, corrosion effects, ornamental borders, or arbitrary historical motifs.
- Keep universal interface symbols recognizable before introducing product-specific character.
- Treat the Qin weight as a cadence and massing system, not a silhouette every icon must copy.

### Color belongs to meaning

- The interface defaults to ink, bone, and restrained bronze.
- Icons inherit `currentColor` and remain colorless until hover, selection, or semantic state requires color.
- The multi-series line graph is the deliberate exception because rapid series discrimination is its primary function.
- Chart lines use three simultaneous cues: hue, dash rhythm, and marker shape. Color is never the only identifier.

### Typography

- Simplified Chinese display hierarchy: Songti SC / STSong or an equivalent CJK serif.
- Simplified Chinese interface and explanatory copy: PingFang SC / Hiragino Sans GB or an equivalent CJK sans.
- English display hierarchy: Iowan Old Style or a similarly quiet old-style serif.
- Monospace is reserved for measurements, timestamps, code identifiers, and compact technical metadata.
- Chinese headings use natural spacing and upright forms; they do not inherit Latin negative tracking or italic treatments.

## Core palette

| Role | Color | Value |
|---|---|---|
| Primary ground | Ink | `#100F0D` |
| Raised ground | Warm ink | `#171512` |
| Primary text | Bone | `#EEE8DC` |
| Secondary text | Dim bone | `#B8AFA1` |
| Selection and brand memory | Bronze | `#BD8B50` |
| Positive semantic state | Jade | `#7CC7A6` |
| Moderation / negative semantic state | Cinnabar | `#E16D58` |

## Chart palette

These assignments are a prototype, not a permanent brand-to-color contract. Preserve functional distinction if the tracked model list changes.

| Series | Mineral color | Value | Secondary cue |
|---|---|---|---|
| DeepSeek | Jade | `#7CC7A6` | Solid line, circle marker |
| Qwen | Cinnabar | `#E16D58` | Short dash, square marker |
| MiniMax AI | Azurite | `#73A7D8` | Solid line, triangle marker |
| Zhipu GLM | Violet | `#B78AC8` | Dotted line, circle marker |
| Meta Llama | Turquoise | `#63BDB5` | Dash-dot line, diamond marker |
| Mistral | Orpiment | `#E2BC58` | Solid line, diamond marker |
| Xiaomi MiMo | Coral | `#E79A75` | Medium dash, hexagonal marker |
| 零一万物 | Chalk | `#D8D1C5` | Widely dotted line, small circle |

## Artifact inventory

### Icon system studies

- [English icon study](mockups/qin-quan/2026-08-19-184954-qin-quan-icon-study-en.html) — five Qin-weight master-mark variants, representative interface icons, production-size tests, and contextual feed usage.
- [Simplified Chinese icon study](mockups/qin-quan/2026-08-19-184954-qin-quan-icon-study-zh-cn.html) — the same study with Chinese-first typography, translated visible copy, and translated assistive labels.

The five master-mark variants remain unresolved:

- A — Quiet cast / 静铸
- B — Uneven balance / 不均之衡
- C — Bulbous cast / 丰腹铸形
- D — Rounded crown / 微拱上缘
- E — Tucked sphere / 内收球腹

### Homepage application

- [Simplified Chinese homepage direction](mockups/qin-quan/2026-08-24-162101-qin-quan-homepage-zh-cn.html) — the current homepage anatomy rendered in the Qin Quan direction: window and locale controls, pulse strip, filters, eight-series chart, trend summary, and live feed.

The homepage mockup is interactive: filter menus open, control groups switch state, pulse entries toggle, and chart legend buttons isolate individual series.

## CE provenance

The working histories remain under these gitignored runs:

- `.context/compound-engineering/ce-prototype/2026-08-19-184954-qin-quan-icon-family/`
- `.context/compound-engineering/ce-prototype/2026-08-24-home-qin-palette/`

Each run contains its own `decisions.md`, question directory, rendered screenshots, and source screen. The tracked HTML files above are curated snapshots; continue exploratory iteration in a new `/ce-prototype` run rather than editing the archive in place.

## Future CE workflow

1. Use `/ce-prototype` to explore or compare further visual questions. Keep its run in `.context/compound-engineering/ce-prototype/`.
2. When the owner approves a visual direction, update this document with the settled choice and promote the selected snapshot into this package.
3. Use `/ce-brainstorm` if product requirements or affected surfaces are still unclear.
4. Use `/ce-plan` when the owner wants an implementation-ready upgrade plan. The plan should cite this document and the selected HTML artifact rather than reproducing either.
5. Use `/ce-work` only from an approved implementation-ready plan.

## Status and known gaps

- No production template, stylesheet, route, or database state was changed by these prototypes.
- No owner choice among master-mark variants A–E has been recorded.
- The homepage direction is preserved for possible future use; preservation is not production approval.
- The two original Qin-weight photographs were supplied through a temporary image directory that is now empty. Reacquire and archive provenance-cleared copies before production design work depends on them.
