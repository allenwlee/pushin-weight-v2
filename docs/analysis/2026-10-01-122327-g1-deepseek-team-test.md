---
title: DeepSeek public team and portrait collection test
date: 2026-10-01
workstream: G1
session: g1-chinese-faces-20260930
status: source-audited-local-dossier-delivered
---

# DeepSeek team collection test

**Scope correction after this test:** the owner explicitly excludes contributors
from staff collection unless specifically requested. The default dossier now
contains 16 founder/current staff claims supported by separate employment evidence,
with seven former/dated staff records in a history view. Four other saved profiles
have unestablished staff eligibility and are excluded from active staff enrichment.
The 591 report credits remain historical evidence only; they are no longer a staff
collection queue or a visible/printed staff register. All original records and
images are retained. See the selected plan's user-level skill/scope correction.

Before that correction, the revised dossier contained **27 individual profiles**,
photographs for **21 people**, and close or upper-body portraits for **13 people**.
It also included every contributor entry in the selected official report. Those
counts describe the historical run, **not current staff coverage or a complete
employee directory**.

[Open the DeepSeek dossier](http://100.102.74.50:62387/?collection=deepseek).
The original 40-person X-list view remains available through the collection
selector, with every prior profile, source, photograph and account image preserved.

## October 1 follow-up: clearer evidence and Chinese-web searches

Each profile now separates **romanized name, Chinese name, Chinese job title and
English job title**, with a source and status for each. Published titles,
self-reported titles, translations and unknown titles are distinguished. Research
areas no longer appear as verified job titles. Every image, including alternate
copies and stored X account images, has a short explanation of its attribution.

The owner accepts directly published photographs from a confirmed personal X
account or official company biography as fully verified sources. Named personal
website portraits are included under a disclosed working assumption; the optional
preference question has not been answered. Under that assumption, **seven of the
27 profiles have a clear portrait from a verified primary source**; 20 do not.
This label describes source provenance, not a measured probability of identity.
Nonhuman avatars, unattributed groups and wider/back-view photographs do not
count as clear portraits. The user's proposed facial-identification reference
database is outside this work without the subjects' consent; this revision
documents biographical sources and does not implement face matching.

**Deli Chen was not searched on Baidu in the initial test.** The follow-up ran
`陈德里 DeepSeek 照片` and `陈德里 世界互联网大会 照片`, returning 50 page results each.
A [QbitAI conference report](https://baijiahao.baidu.com/s?id=1848832300806649522&wfr=spider&for=pc)
names him immediately before an individual photograph, now saved in his dossier.
It remains a third-party attribution. His
[personal homepage](https://victorchen96.github.io/) independently supplies the
names Deli Chen / 陈德里, the title “Senior Researcher” and a self-published portrait.
The Chinese report calls him 研究员; the dossier preserves that dated wording rather
than presenting a translation of “Senior Researcher” as a sourced Chinese title.
A linked Zhejiang page/image returned 404, while a named Xinhua interview video
was found but not downloaded. Those are recorded separately from a no-results
finding.

The bounded follow-up added **four distinct photographs in six files**: Deli's
conference portrait, Fuli Luo's personal-site portrait, a captioned wider event
photo of Chong Ruan / 阮翀, and Huajian Xin / 辛华剑's named WeChat interview card,
plus Chinese-source copies of existing Runxin Xu and Zizheng Pan photographs.
A Chinese report pairing Yuxian Gu with his exact personal website establishes
**顾煜贤**. All 27 profiles have explicit search-history outcomes; none says a
search found nothing when the search was never performed. Unreviewed result
pages, access failures and unresearched report entries remain visible.

Follow-up usage and checks:

- **18 SerpApi calls / 888 page-result entries**, no pagination or paid retries; these counts are search pages, not photographs.
- **19 observed Firecrawl credits**, balance 822 → 803; 14 download attempts, six accepted files and eight held-out or failed candidates.
- The complete collection has **66 dossiers, 100 distinct researched photographs / 112 photo files, plus 33 X account images**. All 145 files decode and load; all prior 139 image files retain their original hashes.
- Desktop/mobile, four sourced fields, per-image explanations, Chinese-name search, source/portrait filters, image viewing and the original 40-person view pass real-browser checks.
- The replacement **47-page PDF** includes all 591 report names, 32 displayed image resources, field sources, image reasons and Chinese search queries. The roster remains a contributor list, not a complete current employee directory.
- At **14:37 JST**, allenwlee Chrome's active tab `919889990` in window `919889817` was verified at the revised DeepSeek URL, focused on Deli. All six added images returned HTTP 200 with matching hashes when fetched from that laptop. No project files or image copies were written there.

Evidence is saved under `.context/g1-deepseek-dossier-clarity-20261001/`, including
the bounded run contract, search/scrape/download receipts, source reviews,
field/image classifications, integrity checks, browser checks, print checks and
remote Chrome/image verification. No production import, migration, deployment,
face matching or additional Git delivery occurred in this follow-up.

The [complete process record](2026-10-01-144511-collect-chinese-workers-process-capture.md)
documents the executed research/access procedures and their failures for a future
`collect-chinese-workers` skill, with a separate script/evidence inventory.

The sections below preserve the **initial test's counts and observations before
the follow-up**. The current numbers and delivery status above supersede them.

## Initial test: what was collected

| Result | Count / meaning |
| --- | --- |
| Official report entries | 591: 465 research/engineering, 126 business/compliance |
| Distinct name strings | 586; five names occur twice and remain separate entries |
| Explicit departed markers | Nine, preserved from the report |
| Individually researched dossiers | 27: one founder, 25 researchers/engineers including former contributors, one reported CFO |
| New individual dossiers | 26; reused the existing Fuli Luo dossier |
| People with photographs | 19 of the 27 individual dossiers |
| People with close/upper-body portraits | 12 of those 27; includes low-resolution portraits with dimensions shown |
| New saved photographs | 21 distinct photographs, 23 original downloaded files including two alternate versions |
| Complete local collection | 66 individual dossiers, 96 distinct researched photographs / 106 photo files, plus the unchanged 33 X account images |
| Individual profiles linked to report credits | 22 entries; ten have a close/upper-body portrait |
| Report entries without a close portrait | 581; most have not received an individual image search |

The report is linked from DeepSeek's [September 9 release announcement](https://www.deepseek.com/news/deepseek-v4-1-flash/).
[Appendix A, pages 46–47](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/main/DeepSeek_V41_Tech_Report.pdf)
lists the two contributor categories and explicitly explains the departed marker.
Both author pages were rendered and inspected. This is evidence of contribution,
with limited departure information; it is not an HR roster. A missing departure
marker does not independently prove employment on October 1.

The repeated strings are Ke Xu, Ning Wang, Xinyu Yang, Yao Li and Zhixuan Chen.
No people or database records were merged solely because these strings repeat.
All 591 source entries are searchable, printable and downloadable as JSON.
Unresearched entries retain unknown dates, locations, Chinese spellings and photos.

## Portrait results and source quality

Close or upper-body portraits are available for Wenfeng Liang, Deli Chen,
Zhihong Shao, Yiyang Ma, Qihao Zhu, Zizheng Pan, Xingchao Liu, Yuxian Gu,
Yuhan Wu, Peiyi Wang, Wentao Yan and the previously collected Fuli Luo.
This category includes clear upper-body photographs; it does not mean every
image is a studio headshot or has production-quality resolution.

Useful sources included:

- [Fortune China's named Liang Wenfeng profile](https://www.fortunechina.com/detail/people/4040/2025/1/liangwenfeng.htm): 770 × 500 portrait; the publisher's edited background is disclosed. Baidu's smaller version is grouped with it.
- [MIT Technology Review's Zhihong Shao award profile](https://www.innovatorsunder35.com/the-list/zhihong-shao/): named 200 × 200 headshot. The personal site's scenery image was excluded.
- [Peiyi Wang's conference-speaker profile](https://underline.io/speakers/150098-peiyi-wang): named 360 × 360 portrait; university/advisor details match his academic record.
- [Peking University coverage](https://news.pku.edu.cn/mtbdnew/15ac0b3e79244efa88b03a570cbcbcaa.htm): named photographs of Qihao Zhu and Damai Dai. Dai's full-body photograph does not resolve his close-headshot gap.
- Personal academic sites, including [Deli Chen](https://victorchen96.github.io/), [Yiyang Ma](https://realpasu.github.io/), [Zizheng Pan](https://zizhengpan.github.io/) and [Yuhan Wu](https://wuyuhan3z.github.io/).
- [PE Daily's 2025 F40 list](https://www.pedaily.cn/2025F40/): a named historical investor portrait for 严文韬. The separate [September 22 appointment report](https://m.thepaper.cn/newsDetail_forward_34123194) says he joined DeepSeek on September 21; the dossier labels this as a reported appointment rather than a company announcement.

No attributable individual photograph was established for Shengding Hu,
Huazuo Gao, Wangding Zeng, Chenggang Zhao, Yu Wu, Zhenda Xie, Huajian Xin or
Chong Ruan. The other seven close-headshot gaps have wider photographs.
The dossier supplies suggested Xiaohongshu queries for all 27 profiles; those
phrases have not been tested inside the app.

Ten of 33 downloaded candidates were held out: nonhuman avatars, documents,
profile screenshots, an unidentified group and an embedded duplicate. A default
silhouette did not count as a portrait. A group photo did not resolve a person's
position. A photo of DeepRoute CEO Zhou Guang was not assigned to Chong Ruan.
Namesakes at Tianjin University and Nanjing University were excluded. No face
recognition, generated portraits, synthetic X handles or person merges were used.

## Roles, original language and existing identities

The view follows the requested order: founder, researchers, C-suite, other staff.
Other staff appear in the complete business/compliance credit register; the
report does not supply their individual job titles. Liang is listed once under
founder, retaining Fortune's dated CEO title.

Fuli Luo remains Xiaomi MiMo / former DeepSeek. Daya Guo's
[personal timeline](https://guoday.github.io/) ends his DeepSeek role in April 2026.
Huajian Xin's [personal account](https://xinhuajian.wordpress.com/) describes an
earlier DeepSeek internship and later Edinburgh/ByteDance Seed work. Chong Ruan
is explicitly labeled former DeepSeek based on dated reporting. These four
former contributors remain discoverable without being represented as current
DeepSeek employees.

Source language and exact role phrases are retained in the local dossier.
Chinese names come from named sources; Shengding Hu, Yuxian Gu and Peiyi Wang
still lack established Chinese spellings in this test. Joining dates keep their
source precision; graduation dates, account-creation dates and publication dates
are never substituted. Locations are included only where individual profiles
state them. English/Japanese translation storage remains planned work.

A read-only export of 489 existing Person records supported identity checking.
Fuli's existing person and dossier were reused. The other inspected self-linked
X handles did not match that export. A production import must still check the
full Account population and normal identity review; this test inserted nothing.

## Cost, verification and artifacts

- 22 SerpApi Baidu searches, requesting up to 50 results each: **1,093 page-result entries**, not 1,093 photographs. No pagination or automatic paid retries.
- Firecrawl balance changed from 926 to 822: **104 observed credits**, within the 150-credit ceiling. Provider balance movement is not a per-request billing audit.
- 33 bounded image-download attempts; 23 accepted files, ten held-out candidates. Original bytes and attribution are saved locally.
- All original 40 records compare equal after excluding Fuli's new DeepSeek-view metadata. Original list/exclusions, image records and other dataset metadata remain intact.
- All **139** local image files decode with matching dimensions and load successfully in the browser. Browser image viewing, 27-profile default, founder/researcher/C-suite/other filters, duplicate-name search, portrait/gap filters and the original 40-person view pass. Missing X handles generate no false profile links.
- Desktop and 390-pixel mobile layouts were inspected with no horizontal page overflow. A **42-page PDF** contains all 591 credited names and 28 displayed image resources; the complete register is not clipped by its screen scrolling area. Print layout keeps a profile together where it fits on one page. The [printable dossier](http://100.102.74.50:62387/deepseek-team.pdf) is linked from the page.
- No production database, schema, application deployment or scheduler changed.

Evidence is in `.context/g1-deepseek-test-20261001/`: run contract, raw report,
rendered author pages, parsed credits, source facts, search/download receipts,
held-out image review, build/integrity receipts, screenshots and print verification.
Firecrawl responses use `.firecrawl/g1-deepseek-20261001-*.json`.

The dossier remains at
`.context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/01-staff-dossiers/screens/`.

### Browser delivery status

The previous allenwlee Chrome dossier tab was identified as window `919889817`,
tab `919889818`. Before the final refresh, SSH stopped connecting. At
`2026-10-01T12:23:27+09:00`, Tailscale reported the laptop offline, last seen at
`2026-10-01T12:20:00+09:00`. Local browser and print checks passed; the remote
Chrome refresh and remote image-byte check remain pending. The owner was asked
whether the laptop is awake/connected. No network settings or remote files changed.

## Consequence for the ongoing collection plan

Public reports solve much of name discovery; individual sites and named academic,
university and editorial profiles provide some useful portraits. Neither yields
a full set of current-team headshots. Keep report-only entries distinct from
verified employment, make unsearched entries visible, and treat portrait discovery
as a separate queue. Closed-platform access remains potentially useful for the
unresolved people, but this test does not establish that such access would fill
every gap. Original batch coverage and continuing staff intake remain unfinished.
