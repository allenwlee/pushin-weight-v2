---
title: Collect Chinese workers — executed research and access processes
created_at: "2026-10-01T14:45:11+09:00"
evidence_window: "2026-09-30 through 2026-10-01 JST"
session: g1-chinese-faces-20260930
status: historical-process-capture-skill-installed
source_revision: 33f20b971b01dbb8d90939f975e5dbbd987a3d86
plan: ../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md
---

# Collect Chinese workers: process record for a future skill

This records how we found people, resolved names and work history, accessed
Chinese and other public sources, collected attributed media, and built the
staff dossier. It includes unsuccessful approaches because repeating those
approaches was a significant source of wasted work and misleading conclusions.
It supplied the evidence and procedures for the now-installed user-level
`collect-chinese-workers` skill at `~/.agents/skills/collect-chinese-workers/SKILL.md`.
The historical execution details below remain a dated record, not a sequence to
replay without reconciling later owner decisions.

**Later owner correction, 2026-10-01:** contributors are not staff without
separate employment evidence. Do not collect contributor-only people unless
specifically requested. The report-author expansion recorded below is retired
from default staff discovery. Its 591 entries remain historical evidence, outside
staff queues, default dossier/print views and coverage denominators. The corrected
dossier has 16 founder/current claims and seven former/dated staff records; four
other profiles have unestablished staff eligibility and are excluded from further
staff enrichment. Existing evidence and all saved images are preserved.

The collection is a local research prototype, not a production staff importer.
The live database was read for existing evidence; no people, account links,
affiliations or assets were inserted. API availability and prices below are
dated observations, not promises that a provider will still work later.

The owner's two eventual outcomes remain: an initial batch covering staff in
Call A **or** the database, expanded with official-site staff from the selected
15 China-based brands; and continuing intake when the user adds a person or
the personnel-change mechanism discovers one. Those production paths are
planned, not demonstrated by this dossier. This record covers public
professional biography and media provenance. It does not provide a procedure
for compiling a facial-identification database without subjects' consent.

## Process map

| Process | Detail |
| --- | --- |
| Establish scope, budgets and evidence storage | [Run setup](#run-setup-and-safe-replay) |
| Find the full population and reconcile a private X list | [Roster discovery](#roster-discovery-and-private-x-access) |
| Recover useful history behind aliases | [Stored account and post evidence](#stored-account-and-post-evidence) |
| Include people without social accounts | [Company sites and existing people](#company-sites-and-people-without-x-accounts) |
| Resolve names, roles and dates independently | [Identity and job facts](#names-job-titles-and-dates) |
| Search Baidu without confusing pages with images | [Baidu through SerpApi](#baidu-search-through-serpapi) |
| Research closed-platform access and alternatives | [Provider routes](#provider-and-platform-access-investigation) |
| Read pages and obtain correctly attributed media | [Source access](#accessing-source-pages-and-extracting-media) and [media handling](#downloading-reviewing-and-counting-media) |
| Explain exactly what verified means | [Verification dimensions](#source-verification-and-identity-evidence) |
| Extract a large research-team population | [DeepSeek method](#deepseek-team-discovery-and-the-chinese-web-follow-up) |
| Build, serve, check and show the dossier | [Dossier workflow](#dossier-build-and-delivery) |
| Preserve failures, costs and material for a skill | [Failure register](#failure-register), [accounting](#execution-and-cost-accounting), [skill installation](#skill-extraction-and-installation) |

The [machine-readable inventory](2026-10-01-144511-collect-chinese-workers-process-inventory.json)
identifies the scripts, receipts and reports inspected for this record, with
file hashes. It contains no credentials, raw provider payloads or image bytes.

## Run setup and safe replay

Work took place in `/Users/fuchitalee/development/pushin-weight-v2` on fuchitalee.
allenwlee was the browser/display endpoint. All generated project files,
downloads, screenshots and receipts stayed on fuchitalee. The local `.context/`
and `.firecrawl/` directories are ignored by Git; a link to them is not a claim
that another clone contains the evidence.

Each bounded pass froze its roster, intended output, request/download/time
ceilings, concurrency and retry policy before executing. The DeepSeek initial
pass allowed 40 SerpApi searches, 150 Firecrawl credits, 150 download attempts
and 60 minutes. Its later source-audit pass allowed 18 searches, 60 Firecrawl
credits, 35 downloads and 45 minutes. These were ceilings, not quotas. The
documentation task did not require another collection run.

Before changing the dossier, the pass saved `data.json.before`,
`dossiers.js.before`, the HTML baseline and image hashes. Search manifests
were separate from execution receipts. Journaling an attempted request before
sending it prevented a restart from automatically repeating a potentially
billable request.

The SerpApi runner read `SERP_API_KEY`, with `SERPAPI_API_KEY` as a fallback,
from the owner's `/Users/fuchitalee/.env.secrets`. It parsed only matching
assignments using `shlex.split`; it did not source the file as shell code.
It chose a nonempty value, sent it only to the provider, redacted its value
from saved response text, and avoided logging credential-bearing URLs.
Other tested names were `SEARCHAPI_KEY`, `PHYLLO_CLIENT_ID` and
`PHYLLO_API_KEY` (used as Phyllo's client secret). Record variable names and
credential environment, never their values or complete authorization headers.

**The saved scripts are historical entry points, not a ready-made CLI.** Many
contain hardcoded directories, fixed sample counts and imports from an earlier
pass. Some regenerate the gallery from an older baseline. Inspect them before
reuse; do not rerun all scripts in date order against the current dossier.

## Roster discovery and private X access

### Database roster versus current list membership

The first read-only query joined `twitter_list_memberships` to `accounts`,
current `brands_accounts` roles and profile snapshots, with list sync state
and reconciliation timestamps. It used a repeatable-read, read-only transaction
and a local statement timeout. The query is saved as
`.context/g1-chinese-faces-20260930/roster-query.sql`.

That snapshot contained 68 active accounts: 20 tagged staff, 25 tagged official,
and 23 with neither role. The 20-role subset became the original dossier.
This was an incomplete selection, not evidence that the list had only 20
people. A smaller Chinese-source view did not change the underlying population.
Ronny was already in the cached membership but was excluded for lacking a staff
role. No current list reconciliation state existed. Harvester YAML and cached
database membership therefore could not establish the latest private roster.

The owner clarified the inclusion rule: **every current list account except an
official company/product account is a presumed person**, even with an alias,
unknown real name or missing staff role. This is a roster rule, not an identity
verification rule. The broader database-staff union still needs its own audit.

### Official API attempts and browser fallback

The owner selected their authenticated X access and ruled out TwitterAPI.io for
the private list. The executed official-route checks returned:

| Request | Observed outcome |
| --- | --- |
| OAuth 2 user lookup | HTTP 401 |
| OAuth 2 token refresh | HTTP 400 |
| OAuth 1 user lookup against v2 | HTTP 403, `client-not-enrolled` |
| v1.1 list membership | HTTP 403, code 453 |

These receipts did not establish working official API entitlement. No TwitterAPI.io
request followed. The usable route was the owner's already signed-in Chrome
session: open the selected list, confirm its owner/name/member total, then open
its members panel and copy rendered member text while scrolling with overlap.
The clipboard was restored after each capture; no X membership was changed.

Five saved captures contained 20, 20, 33, 39 and 18 member occurrences: 130 raw
occurrences, 77 distinct handles and 53 repeats. The distinct count matched
X's displayed **77 Members**, with coverage through the final visible member.
Classification produced **40 people and 37 company/lab/product accounts**.
This was browser text extraction, not raw API JSON or a guaranteed atomic snapshot.

Browser text supplied display names, handles and bios. It did not supply numeric
account IDs, joining dates, historical post counts or reliable locations.
Existing numeric IDs were retained only where matched to saved evidence.
Unresolved new handles used explicit local keys, not invented numeric IDs.
Carol Lin/licheng name similarities did not justify merging handle-less records.

Evidence and exact membership dispositions:
[private-list reconciliation](2026-09-30-225700-g1-private-list-dossier-reconciliation.md),
`.context/g1-live-list-20260930/{browser-page-01.txt,...,browser-page-05.txt,members-from-browser.json,reconciliation.json,classified-members.json}`.
The private raw captures remain local. Future X work should load the canonical
X resource-router skill and respect the selected account/provider.

## Stored account and post evidence

The first inspection missed useful evidence because `description` and
`author_description` were blank. The populated fields were elsewhere:

| Source | Fields actually useful |
| --- | --- |
| `Account` | `author_id`, `handle`, `display_name`, `profile_bio_text`, `profile_picture`, location and observation dates |
| `Post` author snapshot | `author_name`, `author_handle`, `author_profile_picture`, `author_profile_bio.description`, `author_affiliates_highlighted_label` |
| Nested profile URLs | `author_profile_bio.entities.url.urls[].expanded_url` and URL entities inside the description; `author_entities` alone was often empty |
| `AccountProfileSnapshot` | Dated names, `profile_bio_text`, `profile_image_url`, `profile_data`; return to raw posts when the normalized snapshot omits a link |
| Person link | `people_accounts` resolution/review state plus existing multilingual `people` names |
| Post attachments | `entities`, `extended_entities`, `card`, quoted/reposted status and source text; an attachment is not automatically a photograph of its author |

All 466 posts for the frozen 12-account feasibility sample yielded 37 distinct
author-metadata variants. The query capped variants at 30 and profile snapshots
at 15 per account; the observed variants per account were below the cap.
Stable account ID, not mutable handle, joined the history. Pending PersonAccount
links remained pending.

Useful examples: RyanLee's older bio retained a personal LinkedIn URL that the
current bio had replaced; zR's GitHub linked back to the X account and published
Yuxuan Zhang; Lou's company label and `glm5.com` gave work context but no full
identity. A four-account post-media inspection found 49 media-bearing posts out
of 226; it did not establish 49 portraits.

Queries: `.context/g1-chinese-faces-20260930/stored-author-metadata-query.sql`
and `alias-post-evidence-query.sql`. Interpretation and individual examples:
[stored-metadata audit](2026-09-30-114155-g1-public-source-feasibility.md).
The user's alias question materially improved the collection method: inspect
existing metadata and historical self-links before spending on broad searches.

## Company sites and people without X accounts

`Person` already exists separately from `Account`. A staff member without an X
account can be a person; there is no need for a dummy handle or fabricated
account. The DeepSeek pass inspected an existing 489-Person export and reused
Fuli Luo. It did not establish that all other candidates are absent from the
full Account population, and it did not import them.

The accepted website scope is 15 brands: `minimax`, `qwen`, `deepseek`, `glm`,
`mimo`, `moonshot_kimi`, `inclusionai`, `stepfun`, `ernie`, `hunyuan`, `doubao`,
`yi`, `sensechat`, `kuaishou`, `dots`. The deployed enabled-brand check found
21, despite the earlier assumption of 22; 15 were classified China-based.
The saved MiMo brand mapping also contained an erroneous Meituan edge alongside
Xiaomi. A database edge alone must not redirect staff research to a wrong company.

Existing jobs-crawl instructions were located in
[the official jobs sync runbook](../deploy/render.md#official-ai-lab-jobs-sync),
with code in `core/job_sources/{registry,http,adapters,runner,sync}.py` and
`core/management/commands/sync_job_sources.py`. The registry covers Qwen,
DeepSeek, MiniMax, Zhipu and Kimi. Relevant mechanics are official-host/redirect
validation, bounded responses/timeouts, failure isolation and saved parser
fixtures. **Recruiting parsers collect advertised positions, not employee lists.**
They were inspected, not run as a staff importer or rescheduled.

The official-site staff crawl across all 15 remains planned. The tested DeepSeek
route used official announcements/research credits plus named public profiles.
A future staff crawl should preserve every candidate's source and classify it
as existing person, new candidate, unresolved match or excluded with a reason.
Parent-company employment does not establish a product-team role.

Actual job history uses `people_brand_affiliations` and
`people_brand_affiliation_evidence`, with original title/organization wording,
relationship type, status, dates and precision, source URL/text and review state.
`observed_at` is not a joining date. `person_intelligence().employment_history`
includes employment relationships; founder, advisor and other relationship types
remain in affiliations. Multiple conflicting claims do not automatically become
a reconciled one-row-per-job resume. The selected optional given/family fields,
`sexs` → `sex`, and on-demand translation storage remain unimplemented; see the
[G1 plan](../plans/2026-10-01-092148-feat-g1-staff-identity-library-plan.md)
and [People and job history schema reference](../reference/db-schema.md).

## Names, job titles and dates

The useful identity chain is documentary: a stored self-link, reciprocal
personal-site/X links, a bilingual speaker page with the same speaker ID,
or a named university/company biography with matching work context. A name-only
hit or face resemblance is not such a chain.

Keep independent fields and evidence for:

1. Romanized/English name: published spelling, alias, or explicitly labeled
   romanization; don't imply a pinyin rendering was published by the person.
2. Chinese name: exact characters from a named source, owner-supplied wording
   labeled as such, or unknown. Do not transliterate an alias into invented
   Chinese characters.
3. Chinese job title: exact source wording and status; a translation of an
   English title is marked translated and unverified as Chinese original wording.
4. English job title: exact wording where available, with its own source and
   self-reported/reported/company-confirmed/unknown status.

Store the supporting text, source URL, source language, source publication date
where known, observation date and any competing evidence. Research subjects
such as reinforcement learning are biography context, not automatically titles.
“Verified wording” verifies the quotation; it does not prove the employer
confirmed it or that an old title is current.

Keep full names. Optional family/given components require evidence, particularly
for compound surnames, aliases and inconsistent name order. The owner supplied
李元 for RyanLee and Tao He for Ronny; retain the owner provenance and earlier
aliases. Later source-backed Chinese characters are a separate observation.
阮崇 in an early query was wrong for Chong Ruan; the sourced spelling is 阮翀.
顾煜贤 was established by a Chinese article pairing Yuxian Gu with his exact
personal website, not by guessing a Chinese spelling from “Gu.”

Dates retain source precision: year, month or exact day. A graduation date,
paper date, OpenReview account-creation date, announcement date or scrape time
does not become an employment start date. Personal location text is retained
as self-reported work context; a company headquarters is not a person's location.
Fuli Luo, Huajian Xin, Daya Guo and Chong Ruan retain former-DeepSeek status
where supported; their historical contribution does not make them current staff.

Chinese originals are the source evidence. The owner selected saved English
or Japanese translations generated when needed for display. The dossier records
original/translated wording now; the production translation cache is still planned.

## Baidu search through SerpApi

SerpApi was the chosen third-party route to Baidu results. It does not require
calling Qwen. Direct Baidu account setup was retired from the active task after
the owner selected SerpApi; we did not establish that the owner must have a
Chinese phone number or complete a Baidu signup.

### Query construction and actual parameters

Resolve a sourced Chinese name or published alias first, then add **one useful
identity clue**: company, lab, project or university. An unrestricted common
name can be noisy; too many simultaneous constraints can hide relevant pages.
Record any broader fallback as a new query, not a silent change to the first.
Media words used included 照片, 采访, 演讲, 分享 and a named event.

Examples actually used:

```text
罗福莉 小米
罗福莉 演讲
李子玄 智谱
张昱轩 智谱 分享
陈德里 DeepSeek 照片
陈德里 世界互联网大会 照片
阮翀 元戎启行 照片
"Licheng Liu" StepFun
```

The initial three-person experiment used six first-page requests:

```text
GET https://serpapi.com/search.json
engine=baidu
q=<exact query>
ct=2
device=desktop
rn=10
pn=0
api_key=<injected in memory; never log the complete URL>
```

The later names/media pass used `rn=50`, `pn=0`, `device=desktop` and omitted
`ct`. The DeepSeek clarity runner used `engine=baidu`, `q`, `rn=50`, `pn=0`
and the runtime key; it omitted both `ct` and `device`. Preserve these actual
differences when comparing responses. Fifty is a requested page size, not a
guarantee of 50 results. No later batch paginated automatically.

The main response collection is `organic_results`; images and video references
can occur within it or related structures. These are **Baidu web results**, not
proof of a dedicated Baidu image-search integration. No verified endpoint filter
for “only photos of humans” was established. Query wording helps discovery;
source/content inspection still decides whether a result is useful.

### Search execution and accounting

Actual scripts:

| Entry point | Execution behavior |
| --- | --- |
| `.context/g1-serpapi-baidu-test-20260930/run_searches.py` | Six-request fixture; refuses an existing batch receipt; 90-second timeout; 5 MB response bound; stops on error; zero automatic retries |
| `.context/g1-names-images-20261001/search_baidu.py names` then `... media` | Separate name/media manifests and receipts; skips attempted handles; recognizes the provider's no-results message; stops on other errors |
| `.context/g1-deepseek-test-20261001/search_baidu.py` | Bounded DeepSeek manifest; saved raw result per query and receipt |
| `.context/g1-deepseek-dossier-clarity-20261001/search_baidu.py` | Maximum 18 distinct query IDs; journals before calling; skips every attempted ID, including failed/started; 60-second timeout; no paid retries |

The initial six searches returned 52 organic entries for three people—17, 18
and 17 across each person's two queries—representing 43 distinct URLs. They
yielded five new distinct photographs in seven files. Small accepted-photo
counts do not reveal the total number of search results or prove a common name
has little coverage. The early page-size limit and later source review both
constrained yield; next pages were available.

Billing uses search requests, not accepted photographs. The later account
observation increased from six to 47 used searches after 41 calls; result counts
were 669 name-search entries plus 1,021 media-search entries. Separate provider
scrape credits and downloads from SerpApi search allowance. An empty result is
still a recorded request; do not label it “never searched.” Exact current prices
and cache behavior require checking current provider documentation/account data.

The user limited Baidu collection to the selected Chinese-person scope; that
does not remove other staff from the roster. Do not infer nationality from
appearance, a surname or employer. Keep source-language routing and population
inclusion separate.

## Provider and platform access investigation

These routes have different evidence levels. “Documentation inspected” is not
“credential works”; neither means an attributable staff photograph was retrieved.
The linked reports contain the official source URLs and dated API details.

### Firecrawl discovery, scraping and documentation crawling

The initial Chinese-source collection used public web search plus Firecrawl
search with both web and image leads. The saved command shape was:

```sh
firecrawl search '<query>' --sources 'web,images' --limit 6 --country CN --json -o '<capture.json>'
firecrawl scrape '<source-url>' --format 'markdown,links' -o '<capture.json>'
```

Image-search thumbnails were leads, not final attribution. Selected source
pages were scraped and inspected, including Chinese universities, event pages,
company sites, Baijiahao, Sina, Zhihu, CSDN and public articles. If an image or
caption was missing from extracted Markdown, raw HTML and browser inspection
were used selectively. This was not a claim to logged-in WeChat/Weibo access.

The requested native-model investigation ran eight completed bounded Firecrawl
crawls: Baidu, Hunyuan, Doubao, Qwen, Zhipu, OpenCLI repository/docs, and a
Yuanbao third-party repository. They saved 25 page records. Targeted scrapes
and pinned GitHub raw files filled gaps where GitHub crawls returned only a
repository shell/navigation page. Two initial waits had a polling-unit mismatch;
later CLI calls used `--wait --progress`. Rate-limited starts were accounted
for separately from completed crawls. The account balance moved by 39 credits
over that research window; this was not a per-crawl invoice.

The original command arguments for every crawl are not all preserved as a
replay script. Use the saved job/page inventory and the current Firecrawl skill
when recreating a bounded crawl; do not invent an exact historical command.
Evidence: `.firecrawl/g1-native-chinese-search-20260930/crawl-inventory.json`.

Some official documentation was a dynamic Stoplight site. Browser/network
inspection exposed its table of contents and OpenAPI export URL. Those real
links were fetched; guessed authenticated endpoints were not substituted for
documentation discovery. Structured schemas were checked against marketing
claims, especially search versus known-profile or known-post lookup.

### SearchApi comparison

The same six queries were run once via SearchApi with `engine=baidu`, `num=10`,
`page=1`, `ct=1`; the key was sent in an Authorization header. Its language
parameter semantics differ from SerpApi's; exact upstream equivalence was not
independently established. Account credits moved 100 → 94. Searches completed
in 38.742 seconds versus SerpApi's 68.159 seconds, but were run at different times.

SearchApi returned 44 organic entries / 35 distinct URLs and rediscovered all
five accepted SerpApi photographs' sources. In one inline-image response it
assigned the same original URL to 11 different thumbnails: ten mappings were
wrong. Matching thumbnails to the saved Baidu HTML recovered the correct
mappings. Five additional files were downloaded but held for publisher-level
attribution; zero additional photos were accepted. The owner therefore selected
**SerpApi as more reliable for this tested photo workflow**, not as a universal
uptime conclusion. Evidence: [comparison](2026-09-30-185025-g1-searchapi-serpapi-comparison.md).

### Phyllo / InsightIQ

The screenshots' user-creation and SDK-token flow belonged to Phyllo Connect:
an account owner authorizing their own account. It was not a prerequisite for
public-content endpoints. No Connect user or SDK token was created.

The documentation named RedNote for known-profile analytics and known-post/
profile content lookup, but not in the keyword-content-search platform list.
The live read-only probe used Basic authentication for:

```text
GET /v1/work-platforms?limit=100
```

The current-docs host `api.staging.insightiq.ai` rejected the supplied credentials
with HTTP 401. DNS/unauthenticated checks showed a host distinction. The exact
host in the owner's screenshot, `api.staging.getphyllo.com`, accepted the same
credentials with HTTP 200 and returned 17 platforms, none named RedNote or
Xiaohongshu. This established credential validity on Phyllo staging, not search
access. Do not repeat the wrong-host call, request replacement keys, guess a
platform UUID or create a Connect user to fix missing product access.

The owner is awaiting vendor clarification of the product, endpoint and
`work_platform_id`. No Phyllo media/content retrieval was demonstrated and no
support message was sent by the agent. See [the access probe](2026-09-30-190049-g1-phyllo-xiaohongshu-access.md).

### Parse.bot

Firecrawl inspected the supplied marketplace page and docs; unauthenticated
requests read its public endpoint catalogue and a bounded marketplace search.
The Xiaohongshu wrapper exposed `get_note_detail(note_id, xsec_token)`,
`get_user_profile(user_id)` and `list_feed()`. It had **no keyword search**.
A post ID must keep its paired security token from a valid share link/feed;
a profile lookup does not enumerate all that person's posts or other authors'
photos of them. No Parse key, paid execution, note retrieval, API revision,
fork or subscription was used. Provider health checks did not prove image URL
downloads. See [the endpoint assessment](../research/2026-09-30-192019-g1-parsebot-xiaohongshu.md).

### Routes investigated but not executed for staff media

| Route | What was established in documentation/code | Actual limit in this session |
| --- | --- | --- |
| Xiaohongshu app | Owner found useful examples manually; dossier supplies proposed Chinese search phrases | The agent did not run those in-app searches or download those results |
| OpenCLI + 点点 | Logged-in browser adapter can ask 点点 and return note citations; separate note download capability documented | Third-party integration, not established official public API; deferred before a live test |
| Tencent Yuanbao / Hunyuan | Consumer app advertises WeChat sources; Hunyuan has search docs | App/API corpus parity unproved; Yuanbao test deferred |
| Baidu direct | Official structured web/image/video search documentation, including search-only route | Signup and direct paid calls not completed; SerpApi selected instead |
| Qwen | Official web search and `web_search_image` documentation | No Qwen media call; not required for SerpApi/Baidu |
| Doubao / Volcengine | Native search, standalone image search and separate selected-platform agent services | Documentation only; capabilities must not be combined into one assumed endpoint |
| Zhipu | Native/standalone search with selectable engines | Sogou option does not by itself establish WeChat Official Account access |
| Tencent `openclaw-weixin` | Official bot connector for authorized messages/replies/media | Does not document arbitrary public-article/person search; not installed |
| Tencent Web Search / Yuanqi | Search FAQ and authorized own-account knowledge features inspected | Not proof of searching arbitrary WeChat publishers |
| Apify | Specific WeChat article search/detail and Weibo keyword/detail actors documented | Token presence only; no actor run, account balance test or media yield established; wrappers may share an upstream provider |
| TikHub | OpenAPI routes for WeChat article search/detail, Weibo picture search, Xiaohongshu image-note search/detail | No credential or live content call; documented WeChat photos/image categories could return empty while billing |
| Just One API | Article search and several detail versions documented | A higher version number did not imply full HTML/photos; no live test |
| Newrank | Custom API offering documented | No quote, sample, export guarantee, purchase or outreach |
| MediaCrawler | Logged-in browser collection patterns inspected | Not installed/run; historical licensing restriction must be checked before adoption |
| WeRSS / we-mp-rss | Known-publisher feed monitoring documented | Not demonstrated as person-wide discovery; not installed |
| Wellbyte 点点 | Search result advertised a paid endpoint | Live documentation page was missing; availability unresolved |
| Relevance AI | Integration page considered | No public-photo search endpoint established; interpretation of the owner's phrase was not confirmed |

Details: [mainland integration research](../research/2026-09-30-165900-g1-mainland-photo-integrations.md)
and [native-model research](../research/2026-09-30-172400-g1-chinese-model-native-search.md).
Those reports preserve dated prices. Refresh prices, schemas and live access
before a later provider test; do not recreate the retired three-provider batch
merely because the documentation mentions it.

### What top-gun and Scrolls contributed

Read-only inspection of top-gun's `may2026-version/pipeline/smart_match.py`
at `5ad0dbda9140ffa52ea791a0ec51c975b8c9a97b` supplied patterns for existing
evidence first, bounded enrichment, cost accounting and checkpoint/resume.
Its actor was an X collector, not a working China integration. Its heuristic
scores were not adopted as calibrated identity probabilities.

The owner corrected cross-post to Scrolls. Cross-post had already been inspected
for capability/authentication interfaces; its publishing code was not reused as
a Chinese collection route. The relevant repository is
`/Users/fuchitalee/development/scrolls-project`, inspected at
`456cf3d048ec1e37376a815bd78b1780068e4bc6`.

Scrolls' `scrolls/management/commands/scrape_weibo.py` uses a Chinese-locale
mobile browser, a known Weibo UID and its post container to page an account
timeline. It preserves post HTML/text and `pics[].large.url` with a fallback.
That supports collection after account discovery, not general person search.
No Scrolls collector was executed here. Its historical trials also showed:
incorrect URL/date assumptions caused 404s; missing browser binaries were an
environment issue; a root-only archive query missed section directories; Qwen
classified already-fetched content rather than supplying platform access.
Do not inherit its empty-list-on-failure or current-time-on-date-parse-failure
behavior: preserve access errors and unknown dates.

## Accessing source pages and extracting media

1. Save the exact query and original result response. Deduplicate page URLs
   for fetching while retaining every query/result relation.
2. Prioritize pages with a named bio/speaker block, university feature,
   interview, company announcement or personal profile. A source may contain
   several people; the article's main subject is not enough for every image.
3. Save extracted content and inspect the readable body. A successful HTTP
   response, file creation or CLI exit does not prove the article was accessible.
4. Locate the image in the named section and preserve its adjacent caption/text.
   Follow original image URLs from Markdown/HTML; inspect `src`, lazy-loaded
   attributes and responsive variants where present. An Open Graph image may
   be a logo, banner, stock image or a different speaker.
5. If extraction misses the relevant content, use a bounded direct fetch or
   browser inspection of that same source. Keep that route explicit. Do not
   represent access to a verification screen as access to a WeChat article.
6. Record inaccessible, missing, readable-without-attributable-photo and
   unreviewed outcomes separately. Stop at the selected budget; don't infer
   global absence from the inspected subset.

Later Firecrawl batches used two concurrent scrapes, a 55-second subprocess
timeout and no timeout retry. Earlier rate-limit recovery spaced starts seven
seconds apart and limited concurrency to two after the reset. The old rate-limit
retries are part of historical accounting, not permission for unlimited retries.
Existing captures were reused rather than billed again.

Actual access distinctions:

- Baidu indexed public `mp.weixin.qq.com` pages. Two early university articles
  returned verification screens, yielding zero article images. Later, Xin's
  own website linked a different readable WeChat interview with a named guest
  card. This proves one accessible article, not unrestricted WeChat access.
- LinkedIn was unsupported by the tested Firecrawl route and returned HTTP 999
  through the other reader. The historical URL remained a valid identity lead;
  no login or access-control bypass was attempted.
- Personal pages sometimes returned 404; GitHub identicons, Scholar silhouettes
  and Hugging Face cartoons were not treated as portraits. A page failure did
  not establish that the person has no other images.
- A CCF recording page exposed metadata/preview information but required
  login/membership for its full recording. The full recording was not fetched.
- Deli's Zhejiang page/image returned 404. A named Xinhua interview page was
  readable, but its video was not downloaded.

## Downloading, reviewing and counting media

The scripts downloaded candidate image bytes directly after source discovery,
using timeouts, byte limits and image decoding. Firecrawl extracted the page;
it did not make each downloaded image an independently billed SerpApi result.

The DeepSeek image downloader used a browser-style User-Agent, the source page
as Referer, 25-second timeout, 15 MB cap, four concurrent requests, and Pillow
to fully decode and record dimensions/format. Its 80-pixel minimum was a bounded
candidate filter, not an approved production-quality threshold. Original bytes
were saved with SHA-256 and actual format. No generated headshots were used.

Separate candidate download from acceptance. Inspect images and source context,
then record accepted, alternate copy, contextual-only, rejected or failed:

- Accept a photograph with a named source block/caption and adequate context.
- Keep wider event/group photos whole. Use a named position only when the source
  states it; an unlabeled group does not resolve an individual-photo gap.
- Reject charts, paper screenshots, author lists, title slides, logos, default
  avatars, unrelated stock/robot images and wrong-person event photographs.
- Record framing and dimensions separately from attribution. A named portrait
  embedded in an interview poster is still a poster with an embedded portrait.
- Hash exact duplicate bytes. Group different crops, resolutions or posters
  reusing the same photograph, retaining each file and its own publisher evidence.
  These groups are duplicate-image judgments, not face-based identity matches.

Count **search requests, returned entries, unique page URLs, download attempts,
saved files, distinct photographs and people covered** separately. Seven files
can represent five photographs. A single page may yield several images, all of
which still require attribution. Discovery provider and publisher also differ:
“Found via SerpApi · Baidu” does not replace the university/media source URL.

### X profile images from the database

The owner explicitly wanted all account avatars, including nonhuman ones.
`profile-images.sql` unions `accounts.profile_picture`,
`account_profile_snapshots.profile_image_url` and `posts.author_profile_picture`
for the existing roster, preserving the stored URL, source field and first/last
observed timestamps. Forty accounts matched the export; 33 had stored URLs,
with 36 distinct historical URLs. Seven had none.

`collect_account_images.py` reused validated existing files, tried a
`_400x400` CDN variant before the exact `_normal` stored URL, preserved both
URLs, restricted this route to `pbs.twimg.com`, bounded downloads to 8 MB and
15 seconds, decoded content and named files by hash. It saved 33 available
images; three older URLs were unavailable. These live in `account_images`,
separate from researched photographs. A known account-image URL does not by
itself prove the avatar depicts the account owner or resolve an alias identity.

### Video

The first SerpApi trial returned one directly playable Baike MP4. It was
downloaded and inspected with `ffprobe`: 80.341 seconds, H.264, 852 × 480,
with AAC audio. Frames at 5, 30 and 60 seconds showed commentary, a presenter
and mixed footage. It stayed separate from the portrait gallery; it was not
declared footage of Luo Fuli throughout. Bilibili/CCF links and Deli's Xinhua
interview were discovery leads without corresponding saved videos.

For future replay, keep three distinct statuses: video page found, playable
media downloaded, and the relevant subject explicitly attributed in a segment.
Do not convert a thumbnail or video mention into a successful video download.

## Source verification and identity evidence

The dossier now separates these questions:

| Question | Required evidence / current treatment |
| --- | --- |
| Is this the correct person/account? | Documentary account/profile links and matching professional context; preserve unresolved matches |
| Who published this exact image? | Exact source page and downloaded URL, timestamp, bytes/hash and caption/block |
| Does the source explicitly attribute the photo to this person? | Named biography, caption, speaker block or explicit authored context |
| Is it a clear individual portrait? | Visual content/framing check; separate from source status |
| Is the role current? | Dated role evidence; contributor credit and unstarred report entry are insufficient |
| Is reuse authorized? | Separate evidence; public accessibility/source attribution does not establish a reuse license |

The owner's selected source rule accepts an explicitly attributed photo directly
from a confirmed personal X handle or official company bio. “100% verified
source” is the UI's source category, not a statistical confidence score.
A photo posted on a personal account can still depict someone else; the note
must say why it is attributed to the named person. Keep logos, cartoons,
unattributed groups and unconfirmed person/account links explicit.

The current local revision also includes named personal websites under a
**disclosed working assumption**. The optional question has not received an
owner answer. Consequently, its seven primary-source portraits must not be
reported as seven approved X/company-biography cases. Third-party university,
conference and editorial photos remain attributed with their evidence; they
are not automatically promoted to the owner's primary-source category.

The prototype's classification code uses dataset-specific assumptions, including
GitHub Pages/WordPress host patterns for already-reviewed DeepSeek personal
sites. That is not a safe generic source-ownership verifier. The future skill
must preserve the reviewed ownership evidence rather than classify every page
on those hosts as a personal biography. No face matching, embeddings or
face-identification reference pipeline was implemented in this work.

## DeepSeek team discovery and the Chinese-web follow-up

The owner prioritized founder, researchers, C-suite, then other staff, with
headshots important. The initial pass expanded from an official research report.
**This contributor expansion was rejected by the owner's later scope correction.**
The following is an execution history. It must not be used as a default staff
collection procedure; author parsing/enrichment now requires an explicit
contributor request, or separate staff eligibility for an already selected person.

1. Inspect the company's announcement and its linked report. An earlier arXiv
   author capture contained 319 strings, including the organization name;
   this was a discovery input, not the final staff denominator.
2. Download the official linked V4.1 report, save the PDF/text, and render the
   actual author pages for visual inspection. The selected report's Appendix A
   has both research/engineering and business/compliance categories.
3. `parse_authors.py` slices between `A. Author List` and `B. Evaluation Details`,
   verifies the departed-marker explanation, removes page-number/form-feed
   artifacts, normalizes whitespace and splits the comma-separated names.
4. Give each source entry a category/ordinal credit ID. Preserve source spelling,
   report URL/date, departed marker and duplicate-name count. Never merge the
   five repeated name strings merely because their text matches.
5. Retain **591 entries: 465 research/engineering and 126 business/compliance;
   586 distinct name strings and nine departed markers**. Neither a credit nor
   absence of a departed marker proves current employment.
6. Research attributable individual profiles from personal sites, universities,
   conference biographies, Scholar/OpenReview and named Chinese reporting.
   The saved Hugging Face organization-page extraction contains 37
   avatar/profile-link triples; it is not 37 verified current employees or
   a substitute for the report. No model weights or inference were needed.
7. Link an established individual dossier to a credit conservatively. Leave
   unresolved/repeated names unmerged. Reuse Fuli Luo's existing dossier.
8. The initial UI kept all source entries searchable/printable even when there was no detailed
   dossier or photograph. State which entries have never received person-specific
   research instead of treating them as completed negative searches.

Step 8's contributor register has since been removed from the default staff UI
and PDF. The original archive is preserved; its entries are not a research backlog.

For future Hub discovery/collector changes, use the shared `hugging-face` skill
and its dated project notes; an old command's existence does not prove the
current collector or database path is usable. Here the useful Hub artifacts
were a linked report and public identity leads, not a model catalogue refresh.

### What the second pass corrected

The initial run created 27 detailed DeepSeek profiles with photos for 19.
It searched Baidu 22 times, but **Deli Chen was not among those queries**.
The user's challenge exposed that omission. The follow-up added the two actual
Chinese queries, inspected a QbitAI report that names 陈德里 immediately before
his conference photo, and retained his separate self-published portrait.
The dossier now says the first pass did not search him; it does not claim that
Chinese photos were absent.

Other concrete follow-up outcomes:

- Yuxian Gu: a Chinese article paired 顾煜贤 with his exact personal website.
  Downloaded paper/author screenshots did not become new portraits.
- Runxin Xu and Zizheng Pan: Chinese sources provided alternate copies of
  already-collected photographs; they increased file count, not distinct-photo count.
- Huajian Xin: his website linked a readable WeChat interview whose named guest
  card includes a portrait and former DeepSeek internship. Banner/diagram images
  from the same article were held out.
- Chong Ruan: a corrected 阮翀 query found an explicitly captioned wider event
  photograph. A previous article's photo of DeepRoute CEO Zhou Guang was not
  assigned to Ruan. The wider photo does not become a close headshot.
- Fuli Luo: the named personal homepage supplied its own profile photo.
- PKU lists and group pictures sometimes named researchers without identifying
  individual positions; those did not resolve individual-image gaps. Namesakes,
  including unrelated Tianjin/Nanjing academic profiles, were excluded.

Current result: 27 detailed DeepSeek profiles, photos for 21, close/upper-body
portraits for 13, and seven personal-primary-source portrait cases under the
working assumption above. The one-per-person source criterion is **not met**.
The full report has 569 entries without a linked detailed dossier; most have
not been individually researched. See the [DeepSeek report](2026-10-01-122327-g1-deepseek-team-test.md)
and each profile's actual query/source audit, not just this aggregate.

## Dossier build and delivery

The existing prototype is at
`.context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/01-staff-dossiers/screens/`:

| File/data | Purpose |
| --- | --- |
| `001-staff-dossiers.html` | Layout, responsive/print styles, collection and coverage controls |
| `dossiers.js` | Rendering, filters, image viewer, source notes, printable roster |
| `data.json` | All individual dossiers, researched photos, separate X account images, source evidence, coverage and DeepSeek credits |
| `deepseek-roster.json` | Complete 591-entry source register |
| `deepseek-team.pdf` | Generated 47-page printable dossier |
| `images/` | Local original image files; discovery/source grouping retained |

The successive builders are inventoried, not intended as an automatic replay
chain. The latest `build_clarity.py` reads its saved baseline, adds only reviewed
files and a `presentation` layer, preserves existing people/photo objects, and
recomputes counts. Its important structures are:

```text
presentation.fields.{romanized_name,chinese_name,job_title_zh,job_title_en}
  value, source, status, note, original
presentation.image_checks[local_image_path]
  status, source_verified, individual_portrait, reason, evidence_url, source_kind
presentation.chinese_web
  status, summary, initial_status, attempts[], sources[]
attempts[]
  exact query, provider, timestamp, request outcome, result count, pass name
sources[]
  URL, readable label, inspected outcome
```

These are prototype JSON fields, not new database columns. Search history must
distinguish not searched, searched/no candidate saved, source blocked, partial
review and found attributed photo. “Found nothing” is too vague. Negative search
claims are limited to the exact queries and inspected pages.

All 66 dossiers now have the four field blocks. The original 40-person view,
37 organization exclusions, prior image files and aliases remain. The current
collection has 100 distinct researched photographs in 112 files plus 33 X
account images: **145 files**, not 145 distinct photos. A source label is present
on alternate copies and in the image viewer as well as the gallery.

### Xiaohongshu search phrases

`g1-xiaohongshu-terms-20261001/add_search_terms.py` added a proposed phrase beside
each original name, using established Chinese names/aliases plus an identity
clue. Later DeepSeek profiles follow the same display pattern. Former
affiliations and unresolved aliases are labeled. The text field selects its
complete phrase for native copying. This is query preparation, not evidence
that an app search has run. No unavailable Chinese name is fabricated to make
the phrase look complete.

### Broken-image diagnosis and serving

The original preview helper expired after 30 idle minutes. Its state said
`session_end_reason: idle`; browser/HTTP requests returned connection refused
although all saved photos were intact. Lazy loading made some old on-screen
images survive while later requests failed. The fix was a detached local Python
static server at the existing private-network address, without the idle timer.
The server still depends on the host/process staying up; it is not a deployment
or automatic reboot service.

`g1-broken-images-20261001/serve_dossier.py` serves that screens directory and
returns `Cache-Control: no-store` for HTML, JS and JSON. A versioned JS URL fixed
a second issue: Chrome retained an old script after a normal reload. Full-size
image viewing now uses local saved files, while attribution retains external
publisher links. Of 83 original-image URLs checked in the earlier repair,
82 returned images and one returned 403; its saved local copy remained usable.

### Verification performed

- Compare all preserved records and image hashes with the saved baseline;
  distinguish intended additions from changes to original facts.
- Decode every image and verify dimensions. Load every local image URL in a
  real browser. The latest check passed all 145 and preserved all prior 139 hashes.
- Check all four field blocks, source links, image reasons, Chinese-name/alias
  search, company/role/source filters, photo index, image dialog and original view.
- Inspect desktop and 390-pixel mobile layouts. The mobile controls were made
  non-sticky because they obscured the person's name. No horizontal page overflow.
- The historical print check expanded search details and verified all 591 report
  entries, four labels, image reasons and actual queries in the former 47-page PDF.
  That contributor-register output is superseded: the corrected default PDF has
  27 pages and the 16 eligible founder/current claims, with 19 image resources.
- Check JavaScript syntax with `node --check`; run document whitespace/link
  checks. These are local-prototype checks, not production Django test results.

`agent-browser` was used for browser interaction; local browser evaluation
inspected actual rendered state. One important trap: opening the same path with
a different hash can be same-document navigation and retain old JavaScript.
Use `reload`, then wait for a real profile selector before evaluating it.
For screenshots, wait for layout/scroll completion; smooth scrolling can otherwise
capture the wrong section. A saved verification result applies to its exact
files, not a later mutation.

The following local command forms repeat these checks. Paths/session names
belong to this prototype; a later skill should accept them as inputs. Generating
a PDF writes a local artifact, so select an output path deliberately.

```sh
node --check .context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/01-staff-dossiers/screens/dossiers.js
agent-browser --session g1-deepseek reload
agent-browser --session g1-deepseek wait '#staff-deepseek-deli'
agent-browser --session g1-deepseek set viewport 390 844
agent-browser --session g1-deepseek click '#photo-view'
agent-browser --session g1-deepseek click '#dossier-view'
agent-browser --session g1-deepseek pdf '<chosen-local-output.pdf>'
git diff --check
```

### Showing the result in allenwlee Chrome

Preflight SSH identity, visible apps, Chrome windows/tabs and current URL.
Identify the existing dossier tab by URL; tab IDs are observations, not stable
configuration. Send AppleScript via SSH stdin, validate the expected URL,
set that tab's URL, select it and activate Chrome. Re-read title/URL/active tab
after navigation. The last observed successful delivery was October 1 at
14:37 JST, with Deli's profile selected.

An earlier delivery failed because the laptop was offline; a later tab-target
attempt returned “Target tab not found.” Fresh enumeration and direct AppleScript
tab/window references resolved the latter. Do not infer the tab closed from
that error alone. Chrome's JavaScript-through-Apple-Events setting was disabled;
we did not change it. Detailed DOM/image checks ran locally against the same
served files. Six newly added images were also fetched from allenwlee in memory
and matched their saved hashes. No remote project files were created.

The review URL is `http://100.102.74.50:62387/?collection=deepseek`; it requires
the running fuchitalee server and private-network access. Opening/refreshing a
browser and producing a PDF do not imply a physical printer job or deployment.

## Failure register

| Failure or limitation | Correction retained for the skill |
| --- | --- |
| Cached 68-member list and 20 staff roles treated as the full population | Reconcile the current selected list; retain non-company aliases and database-only scope |
| Blank `description` interpreted as no bio | Inspect `profile_bio_text`, nested post bios, historical expanded URLs and snapshots |
| Avatar/post-attachment gallery substituted for researched person images | Keep account images separate; inspect Chinese publisher pages and captions |
| A GitHub-hosted personal photo treated as the end of Chinese-source research | Record actual Chinese queries or explicitly say not searched |
| Deli omitted from initial Baidu queries | Run the actual missing queries, add the resulting source photo and correct the audit |
| Wrong Chinese spelling in a query | Preserve original query receipt; add sourced correction and a separately counted query |
| Research topic presented as job title | Show exact title wording, separate research biography and label missing/translated titles |
| Paper credit/HF organization membership does not establish current employment | Preserve source membership/contribution separately from dated employment claims |
| Repeated author strings risk collapsing people | Retain category/ordinal source-entry IDs and ambiguous identity matches |
| SearchApi assigned one original to unrelated thumbnails | Preserve raw response, recover mappings from saved HTML and withhold unverified candidates |
| A WeChat result URL or HTTP 200 may expose only a verification screen | Detect verification page versus article body; classify access separately from discovery |
| Phyllo valid credentials rejected on another product host | Match the actual credential environment/host; record successful platform catalogue separately from content support |
| Parse.bot lookup endpoints mistaken for discovery | Require documented keyword search for a discovery test; keep known-post retrieval distinct |
| Provider health/marketing treated as media proof | Check actual operation, identity context, downloaded bytes and receipt; docs-only stays docs-only |
| Rate limits and crawl polling mismatch | Preserve physical attempts; bound concurrency/waits and avoid silent repeated paid work |
| Search pages/files/photographs conflated | Keep each count's unit and denominator; group duplicate versions |
| Mixed-footage MP4 treated as subject video | Keep separate; only source-attributed segments support a subject claim |
| An article about Ruan included a different executive's photograph | Inspect the exact caption/block, including neighboring speakers; keep wrong-person candidates out |
| Preview expiry mistaken for lost photos | Check server reachability, then stored bytes, then upstream URLs |
| Cached JS/same-document navigation hid updates | No-store editable files, version script URL, explicit reload and rendered-state check |
| Remote mutation relied on stale tab selection | Enumerate current tabs, validate URL, mutate the identified tab, verify the resulting active page |
| Prototype count assertions/baseline overwrite reused blindly | Treat historical scripts as samples; parameterize and preserve current data before skill extraction |

## Execution and cost accounting

These are distinct passes with different populations. Do not add accepted-photo
counts across rows without accounting for reuse and alternate versions.

| Pass | Requests / observed credits | Measured output |
| --- | --- | --- |
| Stored-metadata feasibility | 12-account deliberate sample; 466 posts / 37 metadata variants | Six 512–1400 px source portraits plus one 128 px Scholar portrait; not approved production assets |
| Chinese-source correction | 60 search attempts: 24 web queries + 36 Firecrawl attempts including nine rate-limit failures; 45 page attempts; 38 downloads; 133 observed Firecrawl-credit decrease | 33 distinct photographs / 37 gallery files, including 25 Chinese-source photographs; 17/20 people covered |
| Native-provider docs/code research | Eight completed crawls / 25 saved page records; 39 observed Firecrawl-credit decrease across the window | Documentation/code capability findings; no native-model staff-media calls |
| SerpApi three-person sample | Six requests / 52 organic entries / 43 unique URLs; 22 scrape attempts for 17 selected sources | Five new photographs / seven files; one mixed-footage MP4 held separately |
| SearchApi comparison | Six requests / 44 organic entries; six measured credits | Same five source photos rediscovered; five extra files held; zero additional accepted photos |
| Private X reconciliation | Four failed official-route attempts, then five browser text captures; zero TwitterAPI.io calls | 77 unique accounts, 40 people, 37 organization exclusions |
| Expanded names/images pass | 16 name + 25 media searches; 669 + 1,021 page entries; 101 observed Firecrawl credits; 52 downloads | 37 new distinct photos / 39 new files; existing 40-person collection reaches 75 photos / 83 files |
| Broken-preview / X avatars | Database read and direct CDN retrieval; no search-provider calls | 33 account images added; 116 total image files at that point |
| Xiaohongshu phrase preparation | No app/provider searches | Suggested per-person phrases and copy controls |
| Initial DeepSeek pass | 22 SerpApi calls / 1,093 page entries; 104 observed Firecrawl credits; 33 download attempts | 26 new dossiers + reused Fuli; 21 new photographs / 23 files; 591 source credits |
| DeepSeek source-audit follow-up | 18 SerpApi calls / 888 page entries; 19 observed Firecrawl credits; 14 download attempts | Four new distinct photos / six files; final 27 DeepSeek profiles with photos for 21 |
| Process documentation | Read existing scripts/reports/receipts | This capture and inventory; no new paid searches or content access |

Phyllo probes and Parse.bot catalogue inspection are described in their sections;
neither established a measured media-call charge. Firecrawl balance movements
are observed account deltas and may include other work in that window; they are
not per-operation invoices. Do not invent a total dollar cost from these numbers.

## Skill extraction and installation

The installed skill describes ordinary professional-profile and attributed
media research, with roster scope and source evidence explicit. It does not
provide worker surveillance or biometric matching. The installed package is:

```text
collect-chinese-workers/
  SKILL.md                         Inputs, outcome, source routing, limits, evidence rules
  agents/openai.yaml               Automatic invocation enabled
  references/roster-and-identities.md
  references/chinese-source-access.md
  references/dossier-and-verification.md
  references/pushinweight.md        Project-specific tables, paths, entry points
```

Keep the skill entry short and put provider-specific detail behind references.
Parameterize roster/brand selection, provider, credential path, output directory,
per-pass limits and portrait/source policy. Do not bake this owner's 77-member
list, 27-person test, private IP, Chrome IDs or fixed provider quota into a
general skill. Load only relevant provider/project references for a given task.

Candidate helpers already have evidence here: metadata export, bounded search
journaling, source queue, media download/hash ledger,
dossier rendering and integrity/browser verification. Before extraction:

1. Remove hardcoded roster lengths, dates, source URLs, private endpoints and
   imports of sibling historical-run scripts. Keep credentials external.
2. Define explicit input/output contracts. Distinguish raw source entries,
   resolved people, claims, photos, file variants and account avatars.
3. Treat `started` requests after interruption as ambiguous, not automatically
   retryable. The current ID-only skip logic also needs a query/parameter
   fingerprint so an edited query cannot masquerade as the previous request.
4. Validate cached scrape contents; file existence alone does not prove a valid,
   readable or fresh source. The historical scrape helper only checks existence.
5. Preserve reviewed ownership/caption evidence. Replace dataset-specific host
   heuristics with explicit source-classification decisions; don't manufacture
   confidence percentages.
6. Replace manual roster parsing/profile tables only where a deterministic
   extraction can be validated. Keep ambiguous matches and unknown fields visible.
7. Do not turn report author parsing into staff discovery. If contributors are
   explicitly requested, keep parsing format-specific with a source-page check;
   don't apply one report's separators or departed markers to another report.
8. Separate research/output from production persistence. User additions and
   personnel-discovery intake, job-history reconciliation, asset storage and
   schema migration are still planned project work, not existing skill behavior.
9. Validate the extracted helpers with saved fixtures: ambiguous names, former
   staff, accountless people, CAPTCHA/404, zero results, wrong image mappings,
   duplicate variants, missing Chinese title, interrupted request and preservation
   of existing dossiers. No fresh paid batch is needed merely to package the skill.

The installed package contains instructions and four supporting references;
historical executable helpers were not copied into it. The inventory remains a
dated snapshot, including hashes of files later changed by the dossier correction.
Codex, Gemini and OpenClaw discover the canonical personal `.agents/skills` root;
Claude and Cursor have symlinks to it. Home and agent instruction files carry
discovery pointers. Installation receipts,
guidance backups and the contributor correction manifest live under
`.context/g1-chinese-workers-skill-20261001/`. Do not interpret this as an installed
production collector or automatically running intake process.

## Evidence locations and reading order

Read this record for the procedure, then the relevant dated report and exact
receipt/script identified by the companion inventory. Local evidence is required
to audit raw responses; the prose remains useful without copying private captures
or media into a future skill package.

| Location | Evidence retained |
| --- | --- |
| `.context/g1-chinese-faces-20260930/` | Database roster, sample dispositions, stored-author/post evidence and initial source checks |
| `.context/compound-engineering/ce-prototype/2026-09-30-g1-staff-dossiers/` | Original preparation, manifests, current dossier and saved images |
| `.context/g1-chinese-portraits-20260930/` | Chinese-source searches/pages, candidate downloads/review and rebuild |
| `.context/g1-mainland-integrations-20260930/` | Public provider documents, TikHub schema and selected routes |
| `.firecrawl/g1-native-chinese-search-20260930/` | Completed crawl inventory, provider docs and pinned repository evidence |
| `.context/g1-serpapi-baidu-test-20260930/` | Six-query fixture, redacted results, source/media manifests, download/video evidence and gallery checks |
| `.context/g1-searchapi-baidu-test-20260930/` | Same-query comparison, usage observations, saved HTML and recovered image mappings |
| `.context/g1-phyllo-xiaohongshu-test-20260930/` | Redacted host/platform probes, documentation discovery and endpoint extracts; credential-bearing screenshots stay private |
| `.firecrawl/g1-parsebot-*20260930.*` | Marketplace/schema/docs captures; no content-execution evidence |
| `.context/g1-live-list-20260930/` | Official-route failures, private browser captures, classified roster and reconciliation |
| `.context/g1-names-images-20261001/` | Name/media manifests, all query outcomes, candidate/source review, quota and preservation checks |
| `.context/g1-broken-images-20261001/` | Server repair, read-only profile URL export, avatar downloader, local/remote image checks |
| `.context/g1-xiaohongshu-terms-20261001/` | Proposed phrase builder and validation |
| `.context/g1-brand-hq-20261001.json` / `g1-people-columns-20261001.json` | Brand-scope and pre-change people-schema observations |
| `.context/g1-deepseek-test-20261001/` | Source PDF/pages, 591-entry parser, personal facts, initial search/media receipts and verification |
| `.context/g1-deepseek-dossier-clarity-20261001/` | Follow-up queries, 26 source reviews plus Fuli's earlier/new source evidence, approved/held files, field/image audit, 47-page PDF and Chrome delivery proof |

All `.context`/`.firecrawl` paths above are on the authoritative host. No new
provider subscription, installation, account connection, outbound message,
production write, scheduler, commit or push was part of this process-capture task.
