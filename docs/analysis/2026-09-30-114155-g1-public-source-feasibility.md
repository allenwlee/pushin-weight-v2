---
title: G1 public-source feasibility and stored author metadata audit
created_at: "2026-09-30T11:41:55+09:00"
status: bounded-audit-complete
scope: G1 research only
plan: ../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md
---

# G1 public-source feasibility and stored author metadata audit

Public sources provide enough credible starting material to begin G1 without
Weibo or WeChat. This pass does **not** establish comprehensive coverage or a
library approved for illustration reuse. Its strongest finding is that
PushinWeight already holds valuable identity links inside collected posts:
those should drive discovery before broad web searches.

A deliberately selected 12-account sample produced six source-attributed
portraits between 512 and 1,400 pixels square and one 128-pixel Scholar portrait.
Four Chinese spellings were explicitly present in inspected sources. Four
accounts have direct documentary links to an external named profile; several
other matches remain corroborated candidates. These counts describe different
properties and must not be collapsed into a single “verified people” count.

## Population and freshness

Read-only production capture: **2026-09-30 11:29:40 JST**, database service
`dpg-d9koekqjobas73fvjqng-a`, configured list `2067062923525275922`.
Source revision: `33f20b971b01dbb8d90939f975e5dbbd987a3d86`.

| Database observation | Count |
| --- | ---: |
| Active memberships / unique account IDs | 68 / 68 |
| Accounts with a canonical staff role | 20 |
| Accounts with a canonical official role | 25 |
| Accounts with neither role | 23 |
| Staff accounts with a stored profile-image URL | 20 / 20 |
| All active accounts with a stored profile-image URL | 61 / 68 |
| Staff accounts with a profile snapshot | 16 / 20 |

Staff and official groups do not overlap in this capture. Membership selection
matches `resolve_call_a_author_contexts`: configured list plus active membership,
then current `brands_accounts` roles. It does not filter by the mutable
membership `source` field: 65 rows currently say `call_a`, three say
`repair_empty_snapshot`.

This is a **database roster, not a newly reconciled X census**. The list has no
`twitter_list_sync_state` row. Fifty memberships carry a September 2
reconciliation timestamp; 18 have none. The 23 unmapped accounts include
recognizable person and organization display names, and two lack handles.
They cannot be silently excluded from a comprehensive G1 population.

Every frozen row has a local disposition: 12 sample-audited but unapproved,
eight staff not yet audited, 25 official accounts provisionally outside person
acquisition, and 23 requiring role resolution. These are research dispositions,
not writes to canonical database roles.

## Stored posts materially change the discovery method

The owner asked whether alias-based accounts had more metadata in collected
posts. They do. The initial inspection looked at `bio` and `description`
but omitted `Account.profile_bio_text` and the richer post JSON. Blank
`author_description` did not mean an empty profile.

The later read-only query examined all **466 stored posts** for the frozen
12 accounts, represented by **37 distinct author-metadata variants**.
Every sampled account has a populated `profile_bio_text`, while all 12 have a
blank account `description`. Each also has populated nested bios in its stored
post history. Individual variant counts range from one to nine, below the
30-variant query limit. Eight sampled accounts have a provisional PersonAccount
link; all eight are pending, and none has a Chinese name recorded there.

Key fields for the next collector or audit:

- `Account.profile_bio_text` for the current normalized bio.
- `Post.author_profile_bio.description` for the bio observed at collection.
- `Post.author_profile_bio.entities.url.urls[].expanded_url` and nested
  description URLs for profile links. Inspect this JSON as well as
  `author_entities`; the latter was often empty.
- `Post.author_affiliates_highlighted_label` for observed company labels.
- Historical `author_name`, `author_handle`, `author_profile_picture`,
  and observation dates; stable account ID joins the history.
- `AccountProfileSnapshot` for compressed history, plus source posts when a
  snapshot omits a website or other field. The raw post can retain more than
  the normalized snapshot.

| Account | Stored posts | Useful evidence already collected | Result |
| --- | ---: | --- | --- |
| Lou / `louszbd` | 121 | Multiple bio variants, `glm5.com`, and an observed Z.ai affiliation label | Stronger organizational context; full name still unresolved |
| RyanLee / `RyanLeeMiniMax` | 57 | An older explicit `linkedin.com/in/ryanlee-dev` link, a newer MiniMax Hub link, and MiniMax affiliation label | A concrete personal-profile lead that a current-only lookup would miss |
| zR / `zRdianjiao` | 36 | Explicit GitHub profile URL and Z.ai affiliation label | Linked GitHub names **Yuxuan Zhang**, lists Z.ai, and links back to `@zRdianjiao` |
| Chao Qiao / `ChaoQiao42` | 12 | RedNote post-training role and authored project context | Useful context; no personal website in the inspected profile variants |

The [GitHub profile for Yuxuan Zhang](https://github.com/zRzRzRzRzRzRzR)
also supplies a LinkedIn link. His Chinese spelling was not established; the
romanized name is not a basis for inventing characters.

The 226 stored posts belonging to these four accounts were also exported for
post-level link/media inspection. Forty-nine contain nonempty media metadata.
Those are **not 49 portraits**: attribution, quoted/reposted material, and
actual image contents need inspection before any count of personal photos.
A bounded text-cue scan was not an exhaustive identity analysis.

Ryan's explicit LinkedIn URL remains a valid stored lead even though Firecrawl
reported the site unsupported and the web reader returned HTTP 999. No login,
account change, or access-control bypass was attempted.

## Frozen sample and observed assets

Sample frozen at **2026-09-30 11:30:38 JST**, before its web research. It covers
seven company/team groupings represented by nine brand keys, including
abbreviated names. It is a deliberate feasibility sample from the 20 staff
records, not a statistical sample, nationality classification, or replacement
for the complete roster.

“Source-attributed” means the named personal, institutional, or event page
presents the image as its portrait. Visual inspection checked framing and
portrait versus icon. It did not establish camera origin, independently verify
likeness, or approve reuse.

| Roster account | Name evidence | Chinese spelling explicitly observed | Inspected image result |
| --- | --- | --- | --- |
| `_LuoFuli` | Fuli Luo on Scholar; exact account link remains to confirm | 罗福莉 | Scholar portrait, **128×128**; larger source needed |
| `ChaoQiao42` | Chao Qiao and RedNote role in stored metadata | Not established | Stored X avatar, **48×48** |
| `ChujieZheng` | Personal homepage and stored profile link point to each other | 郑楚杰 | Homepage portrait, **862×862** |
| `CunxiangWang` | OpenReview name, Tsinghua affiliation and advisor corroborate stored bio | Not established | Linked homepage returns 404; tested GitHub image is an identicon, not a portrait |
| `EileenTal` | Ailing Teng and StepFun role match event profile; bilingual pages share speaker ID 1290 | 滕爱龄 | SuperAI portrait, **526×526** |
| `lindahua` | Dahua Lin and CUHK/SenseTime context match institutional and personal pages | Not established | Personal-site portrait, **512×512** |
| `louszbd` | Lou; affiliation and website history supported | Not established | Stored X avatar, **48×48**; full-name match unresolved |
| `RyanLeeMiniMax` | RyanLee; historical personal LinkedIn link supported | Not established | Stored X avatar, **48×48**; linked page inaccessible through tested readers |
| `xiong_hui_chen` | Personal homepage links the X account; stored bio links homepage; Scholar links same homepage | 陈雄辉 | Homepage portrait, **1281×1281** |
| `xuanmingzhangai` | Stored profile links the current lab page; OpenReview corroborates | Not established | Lab-page portrait, **1400×1400** |
| `ZixuanLi_` | Zixuan Li and Z.ai leadership role match event profile | Not established | SuperAI portrait, **526×526** |
| `zRdianjiao` | Reciprocal GitHub/X links support Yuxuan Zhang | Not established | Stored X avatar, **48×48**; larger attributed portrait still needed |

The four direct account/profile links are Chujie Zheng, Xiong-Hui Chen,
Xuanming Zhang, and Yuxuan Zhang. The other rows retain their weaker evidence
status. All 12 retain **reuse eligibility not established** and **not persisted
as approved G1 records**. A database “verified” or paid badge is not substituted
for these checks.

The current Xuanming profile describes a different current organization from
the stored Qwen association. Preserve both with their observation dates; this
audit does not overwrite employment records.

The six larger images and the four Chinese spellings demonstrate accessible
assets and name evidence. They do not establish enough angles per person,
likeness performance in generated illustrations, full coverage, or launch
readiness. Cunxiang's failed homepage does not prove that other photos are
unavailable. No final image-quality threshold has been approved.

## Primary source map

| Source | What was inspected |
| --- | --- |
| [Chujie Zheng](https://chujiezheng.github.io/) | Name, Chinese spelling, X link and portrait |
| [Xiong-Hui Chen](https://xionghuichen.github.io/) and [his Scholar profile](https://scholar.google.com/citations?user=H5pguCYAAAAJ&hl=en) | Reciprocal account link, portrait and explicit Chinese spelling |
| [Xuanming Zhang](https://worldeology.com/faculty/zhangxm) and [OpenReview](https://openreview.net/profile?id=~Xuanming_Zhang3) | Lab portrait and corroborating profile; historical account link came from stored posts |
| [Dahua Lin's personal site](http://dahua.site/) and [CUHK](https://research.cuhk.edu.hk/en/persons/dahua-lin/) | Portrait and institutional link to the personal site |
| [SuperAI speaker page](https://www.superai.com/speakers) | Named Ailing Teng and Zixuan Li portraits; event date is not used as identity evidence |
| [Ailing Teng, English](https://ml-summit.org/speaker/1290?lang=en&uid=c1048) and [Chinese](https://ml-summit.org/speaker/1290?uid=c1048) | Same speaker ID explicitly supplies 滕爱龄 |
| [Fuli Luo, Scholar](https://scholar.google.com/citations?user=1s79Z5cAAAAJ&hl=zh-CN) | Explicit 罗福莉 spelling and small portrait |
| [Cunxiang Wang, OpenReview](https://openreview.net/profile?id=~Cunxiang_Wang1) and [GitHub](https://github.com/wangcunxiang) | Research identity context; dead homepage and nonportrait GitHub image |
| [Yuxuan Zhang, GitHub](https://github.com/zRzRzRzRzRzRzR) | Public name, Z.ai and reciprocal X link |

No Weibo or WeChat request was required for these results. This is evidence
that they are unnecessary for this starting sample, not a claim that their
content is universally inaccessible or that every remaining person has an
open-web alternative.

## Proposed next work

1. Expand the **stored-metadata audit first** to the remaining staff and
   unmapped active accounts. Reconcile role and roster freshness separately
   from identity verification. Do not silently narrow G1 to the 20 labeled
   staff when known people remain among unmapped entries.
2. Use stable account IDs to build a dated set of all observed names, bios,
   expanded website links, affiliation labels, image URLs, and source post IDs.
   Follow explicit personal links before broad search; older links may be more
   useful than the current profile.
3. Propose an initial acceptance rule of one clear, attributed portrait per
   person for illustration experiments, preferably at least 512 pixels on the
   shorter edge. This is a proposal, not an owner-approved quantity or quality
   threshold. Test additional angles only if the illustration workflow needs
   them.
4. Keep an explicit unresolved queue for Chinese spelling, exact account
   linkage, missing images, and reuse decisions. Use conference pages,
   institutional profiles and public interviews to fill specific gaps; add
   closed-platform work only where the evidence requires it.
5. Design database provenance and image storage after these criteria settle.
   Preserve source URL, observed time, image hash/dimensions, identity decision,
   reviewer, and separate reuse decision. Demonstrate an approved illustration
   example before calling G1 complete.

## Evidence and execution accounting

Local evidence lives under
[`.context/g1-chinese-faces-20260930/`](../../.context/g1-chinese-faces-20260930/);
fetched pages live under ignored `.firecrawl/g1-*`. These are local artifacts on
the authoritative host; a later clone will not contain them automatically.

- `roster-query.sql`, `roster-raw.txt`, `roster.json`,
  `roster-summary.json`, and `roster-dispositions.json`.
- `sample.json` records the unchanged frozen account set;
  `sample-audit.json` records separate evidence statuses.
- `stored-author-metadata-query.sql` and its raw/parsed results preserve dated
  profile variants and pending person links.
- `alias-post-evidence-query.sql` and its raw/parsed results contain the
  226-post inspection set.
- `image-*.json` records URLs, HTTP status, dimensions, byte sizes and SHA-256;
  `images/` retains original downloads. Two AVIF images were decoded to PNG
  only for viewer compatibility; source bytes remain intact.
- `web-search-batch-*.txt` are exact rendered tool transcripts, not raw
  search-provider JSON. Firecrawl results preserve their JSON separately.

The frozen budget was used: **24 search attempts** (12 Firecrawl attempts,
including two rate-limit failures, and 12 queries in three web tool batches);
**30 targeted page/image attempts** (16 Firecrawl source-page attempts,
one failed web-reader attempt, 12 direct image requests, and one setup scrape).
Firecrawl source-page attempts include the unsupported LinkedIn request.
The GitHub Pages 404 is retained as a failed content result despite a successful
CLI exit. No retries or searches beyond that bound were made.

Firecrawl's account balance went from 1,306 to 1,270: an observed **36-credit
decrease**, below the 100-credit ceiling. This is an account-level delta, not an
isolated invoice if another session shared the account. There were no new
TwitterAPI or Grok calls, model calls, image-generation calls, database writes,
publishing actions, commits, pushes, or deployments. Three PostgreSQL queries
used explicit read-only transactions and statement timeouts.

Initial search request timing was not individually logged. Saved results and
the tool transcript support their status and count; do not treat a reconstructed
request manifest as raw timing evidence. Future collection should write each
request record before dispatch.

## Relation to G1 completion

G1-R01–R02: this pass supplies a dated database population, local dispositions,
and sampled documentary evidence; comprehensive identity/photo collection is
unfinished. G1-R03: storage and persistence are not implemented.
G1-R04: reuse decisions and an illustration demonstration remain open.
