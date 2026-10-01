---
title: G1 SerpApi Baidu test — actual photo and video yield
checked_at: "2026-09-30T18:34:47+09:00"
session: g1-chinese-faces-20260930
status: bounded-test-complete-gallery-updated
---

# SerpApi Baidu test

Six successful searches found five new, source-attributed photographs across
the three selected people. Seven image files were added to the existing
20-person dossier page because two photographs have alternate versions.
The target of two distinct photographs per person was met for Luo Fuli only.
This establishes useful incremental yield, not exhaustive coverage or a
completed G1 acquisition system.

| Person | Queries | New distinct photographs | Added files | Sources |
| --- | --- | --- | --- | --- |
| 罗福莉 / Fuli Luo | 罗福莉 小米; 罗福莉 演讲 | 3 | 3 | [Baidu Baike](https://baike.baidu.com/item/%E7%BD%97%E7%A6%8F%E8%8E%89/65258630), [Baijiahao](https://baijiahao.baidu.com/s?id=1851798378643241676&wfr=spider&for=pc), [Tencent Tech article republished on Eastmoney](https://caifuhao.eastmoney.com/news/20251217173145244868550) |
| 李子玄 / Zixuan Li | 李子玄 智谱; 李子玄 智谱 演讲 | 1 | 2 | [GenAICon speaker introduction](https://zhidx.com/p/561784.html), [CSDN speaker introduction](https://csdnnews.blog.csdn.net/article/details/161685476) |
| 张昱轩 / Yuxuan Zhang | 张昱轩 智谱; 张昱轩 智谱 分享 | 1 | 2 | [CCF conference speaker introduction](https://www.ccf.org.cn/Media_list/ccfosc/2025-07-17/846513.shtml), [CSDN conference introduction](https://blog.csdn.net/csdnnews/article/details/151061215) |

Luo's two conference images are distinct frames of the same appearance.
Li's two new files are crops of the same front-facing portrait; the existing
angled portrait remains a separate photograph. Zhang's two new files use the
same portrait in different layouts; the previous event photographs remain.
Identity attribution uses the named source sections and captions. No facial
recognition was used.

## What ran and what it costs

- SerpApi: six physical search requests, six HTTP 200 / `Success` responses,
  zero retries or pagination. Total measured request time: 68.159 seconds.
- Results: 52 organic result entries representing 43 distinct result URLs.
  These are pages and media references, not 52 photographs.
- Source extraction: 17 selected pages, at most five per query. Firecrawl made
  22 scrape attempts: five initially hit its requests-per-minute limit. After
  that window reset, the five were fetched once more with starts spaced seven
  seconds apart and concurrency limited to two. The SerpApi searches were not
  repeated.
- Content inspection: 13 readable articles; one article-body extraction gap;
  two WeChat verification pages; one CCF video page with readable metadata but
  login/membership requirements for the full recording.
- Media: ten candidate image downloads and one video download succeeded.
  Seven image files were kept; a model chart, text screenshot, and explanatory
  diagram were rejected. No search-thumbnail count was presented as photo yield.
- SerpApi uses search allowances, not a per-result or per-photo charge. The
  [documented free plan](https://serpapi.com/pricing) includes 250 searches per
  month. [Cached identical searches](https://serpapi.com/baidu-search-api) are
  free. Six uncached searches consume six searches, regardless of the 52 result
  entries. Account billing/quota deltas were not queried; no subscription or
  credit purchase was made. Firecrawl usage is separate.

The owner supplied `/Users/fuchitalee/.env.secrets`; the runner reads the
nonempty `SERP_API_KEY` value directly without sourcing shell code. Credentials
are supplied only to SerpApi and are not saved in the fixtures or responses.

## WeChat and video findings

Baidu returned two public `mp.weixin.qq.com` university profiles of Zhang
Yuxuan. This is evidence of discovery through Baidu, not native WeChat access.
Both fetches reached verification screens, so this test obtained **zero WeChat
article images**. Do not report successful HTTP/scrape responses as readable
article content.

One 80.341-second MP4 was retrieved from the video URL in Luo Fuli's Baike
search result. `ffprobe` verified H.264 video at 852 × 480 plus AAC audio;
frames at 5, 30, and 60 seconds were inspected. It is commentary with mixed
footage and a presenter, so it is held separately and not accepted as verified
subject footage throughout. It was not inserted into the photo gallery.

Li's search returned a Bilibili talk link; that video was not downloaded.
Zhang's CCF recording page describes a three-minute preview and login/member
access to the complete recording; no CCF video was downloaded. Distinguish
video discovery, playable download, and verified subject footage.

## Existing gallery update and verification

The owner requested that the new photographs be added to the existing HTML
and marked as coming through SerpApi. Each added file now shows **Found via
SerpApi · Baidu**, including alternate-version links and the image dialog.
Original publisher links remain visible. Charts and text screenshots are absent
from the gallery. All prior photographs and dossier facts were preserved.

The gallery now contains 38 distinct photographs in 44 files across 17 of the
20 staff. Its Chinese-source subset has 30 distinct photographs across 15
staff. The three previously missing staff still have no usable photograph.

Real Playwright checks passed for the rendered page: 20 dossiers, 38 photograph
groups, seven SerpApi labels, all displayed images loading, all added primary
and alternate image dialogs, the photo-index switch, and 390px mobile layout
without horizontal overflow. All 44 files match their recorded SHA-256 values;
the original dossier fields and old photo records match the saved baseline.
No browser JavaScript errors occurred in the local verification.

The existing allenwlee Chrome tab was identified by host, window, tab, and URL,
then refreshed in place. A subsequent attempt to inspect its DOM through Apple
Events was unavailable because Chrome disables that capability; no browser
settings were changed. The detailed DOM/image checks above were run locally
with Playwright against the same served files.

Preview observed live at `http://100.102.74.50:62387` on fuchitalee; it is a
local review server, not a deployment or permanent URL.

## Filtering and next decision

The [documented SerpApi Baidu filters](https://serpapi.com/baidu-search-api)
cover query operators, language, time, title/domain restrictions and pagination.
They do not establish a photos-of-humans-only filter. Proposed next improvement:
use portrait/photo/interview query variants and a separate image-content screen
for real photographs with visible people, followed by caption/context matching
to the named staff member. Presence of a person does not verify identity.
This automated screening has not been implemented or run.

The six-search test is complete. Additional searches or broader roster expansion
are not implied by remaining monthly quota. Both full staff-union acquisition
and ongoing user/personnel intake remain open in the G1 plan.

## Evidence files

All detailed artifacts are local and ignored:

- `.context/g1-serpapi-baidu-test-20260930/`: request fixtures, one-shot runner,
  six original JSON responses with any credential occurrence redacted, request
  receipt, source manifest, media candidates/downloads/review notes, summary,
  baseline gallery data, browser receipts and screenshots.
- `.firecrawl/g1-serpapi-source-*-20260930.json`: fetched source content.
- `.context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/01-staff-dossiers/screens/`:
  updated HTML, JavaScript, dossier data, and `images/serpapi-baidu/` assets.

No production database, acquisition worker, scheduler, deployment, commit, or
push was changed by this test.
