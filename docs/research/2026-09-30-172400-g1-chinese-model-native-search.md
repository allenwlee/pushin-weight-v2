---
title: G1 Chinese models with native search — APIs, platform access, and Scrolls evidence
checked_at: "2026-09-30T17:24:00+09:00"
session: g1-chinese-faces-20260930
status: documentation-and-code-research-complete-live-coverage-unmeasured
---

# Chinese models with native search

**Subsequent test selection:** the owner selected Baidu through SerpApi and
deferred Xiaohongshu/Yuanbao. The active contract is in the existing G1 plan.
SerpApi's [Baidu results](https://serpapi.com/baidu-organic-results) document
images/video links within web results; coverage must be tested separately from
the official Baidu API described below. Direct Baidu account setup and pricing
are historical findings, no longer dependencies for the selected route. Follow-up
verification found Baidu's current [search-only API](https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5)
at `/v2/ai_search/web_search`, with image/video results in `standard` mode and
no required model. This supplements the older chat endpoint described below.
[Current pricing](https://cloud.baidu.com/doc/qianfan/s/1mh4sv6c4) lists RMB
0.036 per standard call and free quota issued daily. The broader proposed
comparison below is historical and is not an active execution checklist.

Yes: Chinese providers offer built-in search, and some expose platform-specific
content. The strongest evidence for G1 is Xiaohongshu's 点点 through a browser
integration, Tencent Yuanbao's advertised WeChat sources, and ByteDance's
documented platform-content services. Baidu and Qwen also expose image search.
These capabilities do not yet establish how many usable staff photographs we
can collect.

The owner's correction replaces **cross-post with Scrolls** as the repository
to inspect for Chinese-platform trials and failures. This report supports the
existing [G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md).
Both deliverables remain: the initial Call A/database staff union and ongoing
acquisition for user additions and personnel discoveries.

## What is actually available

| Provider or app | Documented access | Relevance to staff photographs |
| --- | --- | --- |
| Xiaohongshu 点点 | OpenCLI asks the app's AI and returns structured note citations through a logged-in browser. | Promising discovery inside Xiaohongshu; a separate note-download command retrieves images. No official public 点点 API was established. |
| Tencent Yuanbao / Hunyuan | Yuanbao advertises WeChat Official Accounts and Channels; Hunyuan's API separately documents native search. | Consumer-app access is promising. API parity with the app's WeChat sources is unproven. |
| ByteDance Doubao / Volcengine | Native search schemas, a standalone image-search API, and a separate agent service with selected Toutiao/Douyin resources. | Strong official options, with different access conditions for each service. |
| Baidu AI Search | Model-backed web/image/video search with structured references. | Direct image URLs and source pages are useful; this is not proof of unrestricted access to closed apps. |
| Alibaba Qwen | Native web search and a `web_search_image` tool. | Another official image-search option; closed-platform coverage was not established. |
| Zhipu GLM | Native search plus a standalone search API with selectable engines. | Useful Chinese-web discovery; using Sogou does not itself prove WeChat access. |

Primary documentation: [OpenCLI Xiaohongshu](https://github.com/jackwener/OpenCLI/blob/main/docs/adapters/browser/xiaohongshu.md),
[Hunyuan](https://cloud.tencent.com/document/product/1729/105701),
[Doubao search](https://docs.volcengine.com/docs/Networkedsearch/Networkedsearch-2?lang=zh),
[Baidu AI Search](https://ai.baidu.com/ai-doc/AppBuilder/wm88pf14e),
[Qwen image search](https://help.aliyun.com/zh/model-studio/web-search-image),
[Zhipu search](https://docs.bigmodel.cn/cn/guide/tools/web-search).

## Xiaohongshu: the closest third-party match to the proposed approach

OpenCLI documents two complementary commands:

```text
opencli xiaohongshu ask "<verified name, organization, and question>" -f json
opencli xiaohongshu download "<signed source-note URL>" --output ./xhs
```

These are examples, not commands executed in this research. They require a
logged-in Chrome session and OpenCLI's Browser Bridge extension. The `ask`
result includes an answer and `sources[]`, with note identifiers, links and
available author/date metadata. Some citations lack an `xsec_token`; their
fallback links may not open successfully. [Adapter documentation](https://github.com/jackwener/OpenCLI/blob/main/docs/adapters/browser/xiaohongshu.md).

Source inspection at commit `24136945847afbfad266c6c46a8cd335377f9112` confirms
that `ask` opens `/ai_chat`, uses the page's conversation store, and requests
response references. It depends on private frontend structures; the code
already contains recovery for changed module identifiers. The separate download
adapter reads note image URLs from page state and downloads the available media.
This is an app integration, not a supported Xiaohongshu developer endpoint.
[Pinned ask implementation](https://github.com/jackwener/OpenCLI/blob/24136945847afbfad266c6c46a8cd335377f9112/clis/xiaohongshu/ask.js),
[pinned download implementation](https://github.com/jackwener/OpenCLI/blob/24136945847afbfad266c6c46a8cd335377f9112/clis/xiaohongshu/download.js).

The practical hypothesis is **ask 点点 → retain cited notes → fetch note images
→ verify the pictured person from source context**. A generated answer alone
does not establish identity or count as an acquired asset.

## Tencent: app access and API access must be assessed separately

Tencent's own [Yuanbao app listing](https://apps.apple.com/cn/app/id6480446430)
advertises WeChat Official Account and Channels sources. Hunyuan's
[ChatCompletions API](https://cloud.tencent.com/document/product/1729/105701)
has native search controls including `EnableEnhancement`,
`ForceSearchEnhancement`, `SearchInfo`, and `Citation`. Its `EnableMultimedia`
feature requires allowlisting and particular search settings. That API page
does not establish the same WeChat corpus as the consumer app.

The official [Yuanbao Search MCP](https://developer.cloud.tencent.com/mcp/server/11764)
exposes `SearchPro` at `https://api.wsa.cloud.tencent.com/Mcp` and points to
Tencent's Web Search API product. Its [FAQ](https://cloud.tencent.com/document/product/1806/121804),
updated September 2, explicitly excludes WeChat Official Account content.
The Yuanbao name is therefore insufficient evidence of consumer-app parity.
This exclusion is evidence about that search service, not proof that every
Tencent interface has identical restrictions.

OpenCLI also has `yuanbao ask`, with internet search enabled by default.
Its current output is `Role`/`Text`, rather than a structured source list.
It converts response HTML to Markdown, so links may survive, but source-link
completeness and image retrieval require a live check.
[Pinned implementation](https://github.com/jackwener/OpenCLI/blob/24136945847afbfad266c6c46a8cd335377f9112/clis/yuanbao/ask.js).

A second crawled GitHub project,
[chenwr727/yuanbao-free-api](https://github.com/chenwr727/yuanbao-free-api),
documents an OpenAI-compatible proxy with search-enabled model aliases and
browser/QR login. Its README explicitly limits use to learning/research and
says not to use it commercially, despite also naming an MIT license. Treat it
as integration evidence, not a selected production dependency. Neither bridge
was installed or exercised here.

## ByteDance: three distinct official surfaces

1. **Model-native tools.** The current Ark Responses schema includes
   `web_search` and `doubao_app`, with AI-search capabilities and search-result
   blocks. It lists source options including Toutiao and Douyin. This proves
   documented interfaces; account/model eligibility and actual source coverage
   remain untested. [Responses schema](https://docs.volcengine.com/docs/ark/list-model-responses-api?lang=en).
2. **Standalone Doubao Search.** The Custom API accepts `SearchType: "image"`
   and returns up to five images per request, with `Image.Url`, dimensions and
   optional landing-page `Url`. Web search supports up to 50 results. The
   API-key route is `POST https://open.feedcoopapi.com/search_api/web_search`;
   an IAM-authenticated route also exists. The image operation requires the web
   search service to be enabled. [API reference](https://docs.volcengine.com/docs/Networkedsearch/Networkedsearch-2?lang=zh).
3. **Networked Q&A Agent.** This separate service explicitly offers selected
   Toutiao articles and Douyin encyclopedia content; Pro adds Toutiao images.
   Douyin video access needs platform authorization, sales coordination, and
   an SDK for playback. It is not unrestricted video export or proof that
   ordinary search credentials unlock everything. [Source catalog](https://docs.volcengine.com/docs/NetworkedQAAgent?lang=zh).

The [Agent Plan integration guide](https://docs.volcengine.com/docs/ark/agent-plan-enterprise-search?lang=zh)
also documents MCP/skill access and a shared 500-request monthly allowance.
It describes paid usage after allowances; no account was opened or service
enabled. The standalone API can be a tool for our existing agent without
requiring a switch of the agent's primary model.

## Baidu and Qwen: explicit image results

Baidu's documented v2 beta AI Search endpoint is
`POST https://qianfan.baidubce.com/v2/ai_search/chat/completions`.
It accepts `resource_type_filter` entries for `web`, `image`, and `video` and
returns references with source URLs. The v2 schema names image metadata
`references[].image`, including URL and dimensions; older examples elsewhere
on the same page use `image_detail`. Its v2 parameter table requires `model`.
Do not implement an assumed model-free request against that version or confuse
the separate site-icon field with a photograph.
[Baidu reference](https://ai.baidu.com/ai-doc/AppBuilder/wm88pf14e).

Qwen exposes [native web search](https://help.aliyun.com/zh/model-studio/web-search)
and a [Responses image-search tool](https://help.aliyun.com/zh/model-studio/web-search-image)
named `web_search_image`. Both belong in a public-web image comparison; neither
document establishes unrestricted WeChat or Xiaohongshu access.

Zhipu's [search documentation](https://docs.bigmodel.cn/cn/guide/tools/web-search)
includes its own search, Sogou and Quark engines. Its Sogou description names
Tencent News, Penguin and Zhihu, not WeChat Official Accounts. Brand affiliation
alone is not evidence of a shared content catalog.

## What Scrolls actually contributes

Repository inspected: `/Users/fuchitalee/development/scrolls-project`, HEAD
`456cf3d048ec1e37376a815bd78b1780068e4bc6`. This was read-only inspection;
no collectors or database operations ran.

| Evidence | Useful lesson for G1 |
| --- | --- |
| [Weibo management command](/Users/fuchitalee/development/scrolls-project/scrolls/management/commands/scrape_weibo.py:25) | Starts a Chinese-locale mobile browser session, obtains the account's post container from a known UID, then retrieves timeline pages. This helps after account discovery; it is not a general person-search solution. |
| [Weibo image parser](/Users/fuchitalee/development/scrolls-project/scrolls/management/commands/scrape_weibo.py:120) | Preserves post text/HTML, source identity and `pics[].large.url` with a fallback URL. Reusable extraction logic for multiple images per post. |
| [May collector assessment](/Users/fuchitalee/development/scrolls-project/docs/2026-05-21-monid-vs-current-scrapers.md:127) | Records local Weibo/Zhihu operation and custom extraction. These are historical claims, not a fresh demonstration of authentication or availability today. |
| [January state-media trials](/Users/fuchitalee/development/scrolls-project/docs/research/2026-01-20-china-state-media-scraping.md:45) | Public feed services and static requests did not work uniformly; the local Qwen model classified already-collected content. Using a Chinese model was not the mechanism that fetched it. |
| [Global Times and deployment failures](/Users/fuchitalee/development/scrolls-project/docs/research/2026-01-23-state-media-scraping-assessment.md:90) | Incorrect article URL/date assumptions caused repeated 404s; missing browser binaries were a deployment-image issue, not a universal Render limitation. |
| [Xinhua historical discovery](/Users/fuchitalee/development/scrolls-project/docs/research/2026-01-24-xinhua-commoncrawl-discovery.md:44) | A root-only archive query missed section directories; correcting the discovery query exposed far more historical URLs. Browser pagination was a separate coverage limit. |

Do not copy the Weibo collector unchanged: failed requests can become empty
lists, and unparsed publication dates fall back to the current time. G1 should
preserve failure/unknown states, not report those as empty coverage or fresh
content. Discovery, page access, image retrieval and identity verification need
separate outcomes.

## Revised proposed test

The earlier [provider report](2026-09-30-165900-g1-mainland-photo-integrations.md)
still supplies Apify/TikHub alternatives and top-gun reuse evidence. Its
Apify-first ordering is superseded by this broader comparison; no provider has
been adopted.

- Compare an official image-search route, preferably Doubao or Baidu, with
  点点 citation-to-note retrieval on the frozen 20-person sample. Qwen is an
  additional official image-search candidate, not an automatic extra batch.
- Evaluate Yuanbao separately for WeChat discovery: establish whether its
  browser output preserves usable article URLs, then retrieve article photos.
  Keep the managed WeChat providers as an alternative. A chat answer with no
  recoverable sources fails this purpose.
- Recheck Scrolls' Weibo approach on a known source account before considering
  reuse for a continuing publisher watchlist.

Freeze queries, result/detail limits and a usage ceiling before the live test.
Use the existing 33-photo baseline for deduplication. Count incremental,
attributed photographs of the correct person, people gaining their first or
second useful photo, source availability, cost, and session maintenance.
Search hits, generated text, site icons, and unrelated post images do not count.
These are proposed future test settings, not completed collection.

Successful routes should feed the same stored work queue for the initial
Call A/database staff union and newly added/discovered staff. Productive
company, laboratory and event publishers can then be monitored for future
photos. No change to either G1 deliverable is proposed.

## Crawl evidence and limitations

Firecrawl CLI 1.11.2 performed eight completed bounded crawls, returning **25
page records**, across five official documentation sites and two GitHub
repositories. Counts include navigation/configuration pages; they are not 25
independent capability proofs. Targeted scrapes and pinned GitHub raw files
filled important gaps in the crawls.

Local evidence directory: `.firecrawl/g1-native-chinese-search-20260930/`
(gitignored). `crawl-inventory.json` records completed jobs and page URLs.

| Crawl output | Returned pages |
| --- | ---: |
| `crawl-baidu.json` | 6 |
| `crawl-hunyuan.json` | 8 |
| `crawl-doubao-search.json` | 2 |
| `crawl-qwen.json` | 2 |
| `crawl-zhipu.json` | 1 |
| `crawl-opencli.json` | 1 |
| `crawl-opencli-platforms.json` | 1 |
| `crawl-yuanbao-free-api.json` | 4 |

Two initial CLI waits encountered a polling-unit mismatch and produced no saved
crawl output; later calls used `--wait --progress`. Rate-limited initiations
were retried after reset. They are excluded from the completed-output count.
The observed account credit balance moved from 1,127 to 1,088, a 39-credit
difference covering this research window, including searches and direct
scrapes; this is not an isolated per-job billing audit.

An additional paid lead, [Wellbyte's 点点 endpoint](https://www.wellbyte.net/en/docs/api/xiaohongshu-other-ask_dots),
appeared in search with a 97-credit/success price and a September sample.
The live Firecrawl scrape instead returned its missing-page screen. This is
unresolved cached-versus-live evidence, so it is not counted as a verified
available API or recommended dependency.

No native model calls, social-platform searches, staff-image downloads, service
signups, browser logins, production writes or integration installations were
performed in this follow-up. Documentation/code capability is established;
live access, accepted-photo yield and ongoing reliability remain unmeasured.
