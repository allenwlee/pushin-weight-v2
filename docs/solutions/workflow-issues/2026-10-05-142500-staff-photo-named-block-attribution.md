---
title: "Bind a staff photograph to its named source block"
date: "2026-10-05"
category: workflow-issues
module: "G1 staff research"
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "Collecting staff photographs from pages containing several biographies or event speakers"
  - "A readable source page or valid downloaded image is being treated as identity evidence"
tags: [staff-research, image-attribution, provenance, chinese-web, minimax]
---

# Bind a staff photograph to its named source block

## Context

The October 5 MiniMax collection found a government page containing multiple
professional biographies. An image immediately before Yun Yeyi's heading was
initially selected for her. Reading the repeated page structure showed that
each section used **heading → biography → image**: that image belonged to the
preceding aerospace professional. The image after Yun's biography was the
correct source candidate, but its bytes could not be loaded.

The saved records were corrected and the unrelated image was excluded from
both dossier presentations. Yun retained attributed event/poster evidence and
an explicit individual-photo gap. A valid download from an authoritative
domain had not been sufficient to establish the depicted person's identity.

## Guidance

Establish three facts separately before accepting an image:

1. **Source association:** the page or account belongs to the expected source
   and the text refers to the intended person.
2. **Image attribution:** a named caption, biography container, speaker label
   or demonstrated repeated layout associates this particular image with that
   person. Inspect neighboring blocks when the boundary is ambiguous.
3. **File availability:** the saved bytes decode and match the recorded file.
   This verifies the download, not the person's identity.

Save the original image URL, source URL and the short caption or layout reason
supporting the association. Do not promote the nearest image, the first search
thumbnail, or an image merely because it appears on a trusted domain. Scraped
text may flatten containers; use saved HTML or the rendered page when needed.

When correcting a mistake, retain its rejected disposition and reason, remove
it from every accepted gallery and coverage calculation, and check the final
rendered artifact. A correct source association with a failed download stays
an unavailable candidate. Do not substitute a neighboring person's image to
fill the gap.

A labeled portrait inside a panel poster can support attribution to that
position. It does not make the whole poster a standalone portrait. An account
avatar can be confirmed as that account's image while its depicted subject
remains unestablished. Keep these distinctions visible without invented
percentage-confidence labels.

## Why This Matters

Source credibility, image placement and file integrity answer different
questions. Combining them into one “verified” flag can turn a technically
successful download into a wrong-person dossier. The failure is especially
easy to repeat when a scraper preserves text and image URLs but loses the
page's grouping. A source-block check catches it without comparing faces.

## When to Apply

- Multi-person award announcements, speaker lists and company biographies.
- Search results whose thumbnails differ from the named article subject.
- Replacing a broken or held image in an existing dossier.
- Reviewing old assets before using them as identity references.

## Examples

The [Xuhui government page](https://www.xuhui.gov.cn/xwzx_zwxx/20260304/570259.html),
as saved on October 5, had this order:

```text
Previous person's biography
Image e330dc58d104528ee2883d70fc779d46.jpg
Heading naming Yun Yeyi / 贠烨祎
Yun's biography
Image 7177d0f364befce4caf66a5b602ddea7.jpg
Next person's heading
```

The final local research records mark the first URL as
`held_wrong_named_section` and the second as `held_download`. These are saved
run dispositions, not database enum additions. The accepted team-page media
payload excludes the incorrectly downloaded file. Source attribution was
corrected; a usable standalone portrait was still missing.

Audit evidence is private local state under
`/Users/fuchitalee/.local/state/collect-chinese-workers/runs/minimax.io/2026-10-05T020000Z/`:
the saved page `.firecrawl/yun-shanghai-bio.json`, the `yun-yeyi` record in
`people.jsonl`, and `team-page/minimax-team.html`. These paths are operator
artifacts, not files promised to exist in another clone. The public source and
the layout above preserve the lesson when that local state is unavailable.

## Related

- [Staff collection process capture](../../analysis/2026-10-01-144511-collect-chinese-workers-process-capture.md)
- [Shared media-verification guidance](/Users/fuchitalee/.agents/skills/collect-chinese-workers/references/dossier-and-verification.md)
- [G1 plan](../../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md)
