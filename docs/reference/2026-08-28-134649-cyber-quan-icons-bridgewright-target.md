# Cyber-Quan production icon target

Approval status: APPROVED

This contract records the owner-approved icon-only delta for the public `/`
homepage. It supplements, and does not replace, the V24 layout authority or the
production pulse/feed/timezone contract. Production typography, spacing,
buttons, control geometry, content order, non-icon colors, and interactions are
protected. `/internal/` and single-brand pages are not targets.

## Locked source

The tracked bilingual studies originated from these exact approved files:

- English SHA-256: `8c63f9c357cbe576e8ef5fc63b607820dfd0039125aeeacbc7ba668e14106f52`
- zh-CN SHA-256: `cc09e5c98be2cd1a42f81a143071cd63313b80691fd82ea00187e6e1a6ed7eaa`
- CSS SHA-256: `021a3d4bad44bdccc0bf3ae0579a17403c17608565170d1f8b6b26493c622eb1`
- Shared 38-symbol sprite SHA-256: `9a5fd90add8e5d60baf87796054b0211fbb94d9ad92e952fc5133465eb9da658`

The timestamped tracked HTML files only change the relative stylesheet name.
All 38 source symbols retain their approved geometry and `0 0 24 24` view box.

The owner-approved runtime alternates in
`docs/ideation/2026-08-29-161106-cyber-quan-icon-alts.html` (SHA-256
`dae29084a247656169dd3e076f0d616390c4fe6f791c697a38a7f8076ad55d81`)
supersede the earlier runtime
geometry for `icon-rise`, `icon-fall`, `icon-followers-1`,
`icon-followers-3`, `icon-sentiment-neutral`, `icon-hands-on-hammer`, and
`icon-california`. Symbol IDs, `0 0 24 24` view boxes, callers, colors, and
dimensions remain unchanged. Follower bins 2 and 4 retain their earlier
geometry.

## Runtime boundary

The production sprite contains exactly these 33 symbols:

`mark-quiet`, `icon-heart`, `icon-reply`, `icon-repost`, `icon-rise`,
`icon-flat`, `icon-fall`, `icon-followers-1`, `icon-followers-2`,
`icon-followers-3`, `icon-followers-4`, `icon-role-badge`, `icon-sentiment-neutral`,
`icon-sentiment-negative`, `icon-sentiment-mixed`,
`icon-hands-on-hammer`, `icon-compare`, `icon-question`, `icon-marketing`,
`icon-event`, `icon-discourse`, `icon-nationalism`, `icon-unsanctioned`,
`icon-california`, `icon-beijing`, `icon-sentiment`, `icon-announce`,
`icon-star`, `icon-caret`, `icon-sunrise`, `icon-day`, `icon-dusk`, and
`icon-night`.

Mark B variants, the chisel alternate, and the unused moderation study remain
in the dossier only. Unknown runtime keys render no SVG.

The masthead uses mark A (`mark-quiet`) and preserves the compact locked unit:
`走个量`, then `Pushin'`, then `Weight`, with the English words on separate
lines. This is the sole permitted non-substitution geometry adjustment.

Follower magnitude uses one through four people and the existing bins with
colors `#64748b`, `#8492a6`, `#cbd5e1`, and `#f8fafc`. Sentiment retains the
existing positive green, neutral slate, negative red, and mixed amber families.
All other symbols inherit the surrounding production text or muted color.
Nationalism uses the approved rough flag with compact `中` and `美` modifiers.

## Pre-change evidence

The unmodified product surface was captured after merging `origin/main`
`158afd2be2e17e51999655006de7cf08e1e8e282` into branch revision
`c65f26381102c1c28e05d38131ed531c73340bc2`. The deterministic fixture is `seed_v22_metadata_regression_orm()`;
the application and browser clock are fixed at `2026-08-10T12:34:00Z`; the
browser timezone is `Asia/Tokyo`; authentication is anonymous. Candidate
goldens and exact icon masks use the same frozen state.

| Frame | Route / locale | Viewport | SHA-256 |
| --- | --- | --- | --- |
| `prechange-desktop-en.png` | `/?locale=en` | 1440×960 | `e2920fdc769371a7b8832f837711fae34cd9cfe12732d7787d1e12cf3c1ae1c7` |
| `desktop-en.png` | `/?locale=en` | 1440×960 | `18fd93bf131bac991fee112859893a8d4f842a797a678a0a5ec291093448af33` |
| `mask-desktop-en.png` | `/?locale=en` | 1440×960 | `a521be13916fad475ad293278905418a3b7b267d3c5a4537735de9d4438ec15f` |
| `prechange-mobile-zh-cn.png` | `/?locale=zh_cn` | 390×844 | `60ebf13da5cded2df252c1a2e5cfe1fd639fe0e6de1997f8a47085cc49b24719` |
| `mobile-zh-cn.png` | `/?locale=zh_cn` | 390×844 | `373572587b78aaeed49248a159f36e5791219bdaea869bf6218f4398a7c23571` |
| `mask-mobile-zh-cn.png` | `/?locale=zh_cn` | 390×844 | `f45674edba7bbfdfb36e35ca1a38a92732d9538292a054382ddb9fb630835837` |

Baseline element boxes in CSS pixels are recorded below. Candidate masks may
cover only these exact icon-bearing elements plus the masthead name box; they
must not cover whole cards, rows, controls, or frames. The sole raster-only
addition is the selected timezone choice's two-pixel leading edge: Chromium
antialiases that rounded seam differently when its emoji text node becomes SVG,
even though the selected-choice and full timezone boxes remain identical.

| Region | Desktop x/y/w/h | Mobile x/y/w/h |
| --- | --- | --- |
| masthead | 182/12/1076/98 | 12/12/366/98 |
| name | 199/28/830/23 | 29/28/120/23 |
| pulse | 182/118/1076/48 | 12/118/366/44 |
| timezone | 427/66/190/28 | 171/66/190/28 |
| first caret | 261/189/4.453125/9 | 74/185/4.453125/9 |
| first follower | 824/264/38/34 | 29/630/38/34 |
| first engagement | 868/307/282/14 | 73/691/214/14 |
| first signals | 1156/264/83/86 | 293/630/66/86 |
| Top Voices | 199/578/577/38 | 29/504/332/56 |

The final candidate must add candidate goldens for the same deterministic
states. Every changed pixel must remain within measured icon boxes or the name
box, with no horizontal overflow at 1440, 390, or 320 pixels.

## Release gate

Automated mobile emulation is not physical-device approval. Before production,
the exact staged candidate SHA requires explicit owner approval in desktop
Chromium and on a physical iPhone in zh-CN. The owner must recognize follower
magnitude, sentiment, post type, nationalism, timezone, pulse direction,
Top Voices, and the masthead at a glance. Missing approval stops at staging.
