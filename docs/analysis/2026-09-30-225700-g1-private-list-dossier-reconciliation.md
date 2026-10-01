---
title: G1 private X list — current membership and expanded dossier
captured_at: "2026-09-30T22:47:03+09:00"
session: g1-chinese-faces-20260930
status: roster-and-prototype-updated-searches-held
---

# G1 private X list — current membership and expanded dossier

The owner's current private list has **77 accounts: 40 people and 37 company,
lab, or product accounts**. The existing dossier now includes all 40 people,
adding 20 to the earlier staff-role-selected sample. All 38 photographs in
44 gallery files are preserved. Seventeen people have collected photos;
23 still have a photo gap. No new photo or video search ran.

## Retrieval and completeness

- Source: the signed-in Chrome session on allenwlee, opening
  [the list](https://x.com/i/lists/2067062923525275922) and its members panel.
- The rendered overview identifies `_openweight-off-staff`, owner `@allenwlee`,
  and **77 Members**. Captures completed at 22:47 JST on September 30.
- Copied the rendered member text while scrolling the panel. Five captures
  contain 20, 20, 33, 39, and 18 member occurrences: 130 occurrences,
  77 distinct handles, 53 repeated occurrences. Overlap spans each section;
  the final section ends at Stefania Druga. The unique count equals X's
  displayed total. These are browser text captures, **not raw API responses**.
- Used no TwitterAPI.io calls. Four official X API attempts preceded the browser
  route: OAuth 2 user lookup returned 401; refresh returned 400; OAuth 1 user
  lookup on v2 returned 403 `client-not-enrolled`; v1.1 list membership returned
  403/code 453. No secret values were saved in evidence or changed.
- All task files remain on fuchitalee. The browser clipboard was restored after
  each capture. No X account/list changes, production writes, or deployment.

The browser member panel supplied handles, display names, and biographies.
It did not supply numeric account IDs, locations, employment dates, or historical
post counts. Existing IDs were retained where the current handle matched the
saved database record. `CarolGLMs`, `liulicheng10`, `echojuliett`, and
`ShunyuYao12` use explicit handle-based local dossier keys and leave numeric IDs
unknown. The first two resemble the saved handle-less Carol Lin/licheng records,
but name similarity alone was not used to merge IDs. This is not the complete
Call A/database-staff union audit required for the eventual G1 implementation.

## Inclusion and corrections

The owner directs that every account except official company accounts be treated
as a person. Missing database staff roles and unresolved full names no longer
exclude a list member. Company and role fields for new dossiers use explicit
current biographies; missing details remain unknown. Inclusion is not a claim
that every name, affiliation, or nationality has been independently verified.

The 20 additions are:

| Person / displayed alias | X handle |
| --- | --- |
| John Kim | `PremiumGoblin` |
| Leanna Ren | `RenLeanna` |
| Tao He / RonnyHe | `Ronny_MiniMax` |
| Olive Song | `olive_jy_song` |
| Kyle Wong | `ewveggies` |
| Carol Lin | `CarolGLMs` |
| Randy | `Randyxian` |
| Yifan Zhang | `yifanzhang_` |
| licheng | `liulicheng10` |
| Jason Wei | `_jasonwei` |
| Miao Xiong | `miao_xiong_cs` |
| Shunyu Yao | `ShunyuYao12` |
| Kaylee George | `krgeorge` |
| Ming-Yu Liu | `liu_mingyu` |
| Junyang Lin | `JustinLin610` |
| Aidan Gomez | `aidangomez` |
| Ivan Zhang | `1vnzh` |
| Lucy Park | `echojuliett` |
| Sung Kim | `hunkims` |
| Mark Zuckerberg | `finkd` |

Applied the owner's names **李元** for `RyanLeeMiniMax` and **Tao He** for
`Ronny_MiniMax`, retaining the observed aliases and explicit owner provenance.
No Chinese spelling was inferred for Tao He.

The excluded accounts are visible in an expandable section of the gallery and
in the per-account classification ledger. Two noteworthy dispositions:

- `naiveailab` is linked by [NaiveAI's own research site](https://naive.ai/en/research/).
- `StepFunAI` currently describes an Imperium Group corporate asset-acquisition
  account. It is excluded as a company account, not attributed to StepFun staff.
  The separate `StepFun_ai` account remains the StepFun company/product entry.

## Baidu preparation and verification

The local queue records all 40 people: three completed SerpApi sample subjects,
eight prepared name-plus-identity-clue queries on hold, and 29 entries requiring
Chinese-only scope/identity review before any query is scheduled. This is not
a nationality classification; a face, surname, or employer alone is insufficient.
Non-Chinese people should use other sources. Preserve the owner limit of one
request per remaining eligible person, `rn=50`, `pn=0`, with no pagination.
The asset-search hold remains active; **zero new Baidu calls** were made.

Browser checks against the actual preview passed: 40 dossiers, 37 exclusions,
38 photograph groups, all 44 image files decoded, 23 missing-photo states,
Ronny/Tao He and 李元 searches, company/coverage filters, view switching, and
image open/close. There were zero browser errors and no horizontal overflow at
1440 px or 390 px. Screenshots were visually inspected, including Tao He's name
and role on screen at mobile width. Original photo records and all 65 files in
the image directory remain byte-identical; 44 of those files are gallery assets.

Artifacts:

- [Existing dossier HTML](../../.context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/01-staff-dossiers/screens/001-staff-dossiers.html)
- [Updated data](../../.context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/01-staff-dossiers/screens/data.json)
- [All member classifications](../../.context/g1-live-list-20260930/classified-members.json)
- [Baidu preparation queue](../../.context/g1-live-list-20260930/baidu-queue.json)
- [Reconciliation receipt](../../.context/g1-live-list-20260930/reconciliation.json)
- [Browser verification](../../.context/g1-live-list-20260930/browser-verification.json)

Raw browser captures, failed API receipts, the pre-edit gallery, preserved-file
hashes, update script, and screenshots are under `.context/g1-live-list-20260930/`.
The live preview is temporary at `http://100.102.74.50:62387`; the original
allenwlee Chrome dossier tab was refreshed to Tao He's card. Prototype files
and captured evidence remain local and ignored by Git.
