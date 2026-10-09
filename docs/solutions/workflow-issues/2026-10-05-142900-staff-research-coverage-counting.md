---
title: "Keep staff-research coverage units separate"
date: "2026-10-05"
category: workflow-issues
module: "G1 staff research"
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "Reporting a company research pass that mixes staff, aliases, held candidates and media"
  - "Reconciling search-entry review with source-page inspection and portrait coverage"
tags: [staff-research, coverage, provenance, serpapi, minimax, research-completion]
---

# Keep staff-research coverage units separate

## Context

The MiniMax research pass ended with 60 displayed records, 3,658 returned search
entries and 47 accepted image files. None of those counts answered “how many
employees did we find?” or “how many people have an attributable portrait?”
The roster included unresolved aliases and employment candidates; most search
entries were triaged from titles/snippets; images included avatars, posters and
variants. The final report reconciled these units separately.

The source ledger's `inspected` disposition was especially easy to overread:
many such entries had only title/snippet review. Its separate inspection-level
field, not the disposition name, established whether source content had been
read. This is a reporting distinction in saved research records, not a claim
that every database or future collector enforces these categories.

## Guidance

Define the unit and population before reporting a total. Preserve these
separations in the existing ledger rather than inventing another database model:

| Quantity | What it establishes |
|---|---|
| Employment-supported people | Unique local identities with employment evidence; current, dated and former claims remain distinguishable |
| Employment holds and alias observations | Research leads, potentially overlapping named people; not extra confirmed staff |
| People qualifying for Chinese-source research | Employment-supported people with documented individual mainland ties; a separate filter from employment status |
| Returned entries | Search-provider results, including repeated URLs and irrelevant hits |
| Inspection level | Title/snippet triage, source body read, documented fallback, access failure or unvisited lead |
| Source attempts and saved responses | Access work and evidence availability; neither guarantees a meaningful page body |
| Accepted file hashes | Distinct saved bytes; a shared poster is one file even when linked to several people |
| Portrait coverage | Eligible people with an attributed individual image meeting the requested standard; not the number of files |

Record a reason for a discarded entry and an actionable outcome for a relevant
lead. A failed page can have a readable equivalent source, but that does not
mean the failed page was inspected. A graduate's planned destination or a copied
post whose original author is unconfirmed remains a hold until the relevant
employment or identity link is supported.

Count image attribution and suitability separately. A labeled multi-person
poster can contain useful evidence without being a standalone portrait.
Avatars do not fill a portrait gap merely because their account is known.
For video, distinguish unique source URLs, downloaded files and specifically
attributed segments. A decoded video is not proof of every frame's subject.

Before closing a run, reconcile the roster, selected research population,
remaining queue, file hashes and report. Carry late discoveries through the
same required work. Keep the shared provider balance separate from run usage,
including failed or unresolved requests that may have consumed allowance.

## Why This Matters

A large result count can hide thin source coverage, and a large file count can
hide missing portraits. Counting the wrong population also sends an agent back
to research unresolved aliases as if they were additional employees. Explicit
units make the remaining work reviewable and avoid misleading cost-per-person
or “complete team” claims.

## When to Apply

- Closing or resuming a company discovery run.
- Building a dossier, team page, import manifest or acquisition progress report.
- Comparing provider costs or estimating the next company's workload.
- Reviewing a saved ledger whose status labels have ambiguous meanings.

## Examples

The saved October 5 MiniMax report reconciles as follows:

- **60 records = 45 employment-supported people + 4 employment holds +
  11 unresolved alias observations.** The 45 have 15 current-role claims,
  17 dated claims and 13 former-staff states.
- **45 people = 21 with documented mainland ties + 5 general-research records +
  19 connection reviews.** The 19 connection reviews are already inside the 45;
  they are distinct from the four employment holds outside it.
- **3,658 entries = 3,610 title/snippet-only triage entries + 48 entries with
  source-body or documented-fallback inspection.** Those 48 are entry records,
  not a claim of 48 unique pages. A separate ledger records 80 source attempts.
- **47 accepted image files include 18 account images**, variants and a poster
  linked to more than one person. The team page embeds 45 staff-associated files
  plus two avatars belonging to employment-review records.
- **12 of the 21 qualifying people have an attributed individual image;
  nine gaps remain.** Five distinct video-source URLs produce six person-level
  references and one saved video file.
- **78 run requests include 75 completed responses and three failed or unresolved
  requests.** The final account snapshot independently showed 922 searches left.

The checkpoint marked the prescribed pass completed within scope, while the
coverage report explicitly left the portrait requirement unmet. That completion
label does not establish a full employee census, a database import, or absence
of further photos online. Reaching 78 requests is not a stopping rule for the
next company.

These are dated run observations, not universal performance estimates. The
MiniMax request mix included company discovery, former staff and searches made
before the person-level connection rule was tightened. Dividing 78 by 21 would
not give a measured cost per qualifying employee.

Audit evidence is private local state under
`/Users/fuchitalee/.local/state/collect-chinese-workers/runs/minimax.io/2026-10-05T020000Z/`:
`coverage-report.md`, `coverage.json`, `people.jsonl`,
`evidence/source-coverage.json`, `evidence/search-result-dispositions.jsonl`
and `team-page/manifest.json`. These paths are operator artifacts, not files
promised to exist in another clone. The reconciled figures above preserve
the reasoning without requiring that private state.

## Related

- [Bind photographs to named source blocks](2026-10-05-142500-staff-photo-named-block-attribution.md)
- [Staff collection process capture](../../analysis/2026-10-01-144511-collect-chinese-workers-process-capture.md)
- [Company discovery and completion rules](/Users/fuchitalee/.agents/skills/collect-chinese-workers/references/company-website-run.md)
- [Measured workload reference](/Users/fuchitalee/.agents/skills/collect-chinese-workers/references/deepseek-calibration.md)
