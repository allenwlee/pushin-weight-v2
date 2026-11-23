# TwitterAPI.io support report: historical search omissions and window-dependent results

Prepared: 2026-10-19. Observations: 2026-10-16 and 2026-10-17. All publication and execution times below are UTC. This report was assembled from saved evidence; it does not describe a new API retest on October 19.

## 1. What we need help investigating

We use TwitterAPI.io for ongoing collection and for a one-time historical backfill of public AI-related posts. Historical advanced search is omitting known matching posts even after we follow the returned cursors until the API reports no next page.

The clearest examples are:

- **Known-positive control:** for July 31, 2026, 12:00–12:15, we have 75 matching own-text posts originally collected on their publication day. A later historical `Latest` search returned 46 distinct raw IDs, including only **34 of those 75**. Five sampled omissions all returned through `/twitter/tweets` and still matched the query in their own text.
- **Same query, different bounds:** the full-day July 30 B1 query returned only **3 IDs published during 12:00–13:00**. Searching that hour separately with the unchanged B1 query returned **84**. Across the full day, 24 hourly B1 searches returned **1,716 distinct IDs**, compared with **1,095** from the full-day B1 search.
- **Subsequent controlled comparison:** on October 17, 5-minute searches improved recovery for two of three sampled dates but still missed **154/273 July, 60/95 August and 42/59 September** known posts whose captured search/lookup payloads confirmed current availability and query eligibility. Both interleaved passes returned identical ID sets for each date and window size.

Please help establish whether our parameters or cursor handling depart from the intended API contract, whether the observed omissions are expected historical-search behavior, and how to enumerate the available matching posts reliably. We have not established a provider-internal cause.

The report is self-contained: exact query text, UTC/Unix bounds, local stopping limits, known missing IDs, per-page results and complete request-parameter appendices follow. API keys, account credentials, database identifiers and internal infrastructure details are omitted.

## 2. Request contract and counting method

The client makes HTTP `GET` requests to `https://api.twitterapi.io` with `X-API-Key` authentication and `Accept: application/json`. It uses our explicitly selected on-demand account credential. Secret values are not included here.

| Purpose | Endpoint | Actual URL query parameters |
| --- | --- | --- |
| Search | `/twitter/tweet/advanced_search` | `query`, `queryType`, `limit=20`, and `cursor` after the first page |
| Direct ID lookup | `/twitter/tweets` | `tweet_ids`, a comma-separated string of native post IDs |
| Timeline control | `/twitter/user/last_tweets` | `userId`, `includeReplies="true"`, and `cursor` |

For search, `since_time` and `until_time` are **inline operators inside `query`**, using Unix seconds. They are not separate URL parameters. Our requested interval convention is start-inclusive/end-exclusive; please confirm that interpretation. No language, geography, reply or retweet filter was added to the minimal control beyond the literal query shown below.

`max_results`, `max_pages`, `max_per_page`, elapsed-time ceilings and request budgets are our local iterator/controller settings. They are not extra parameters sent to advanced search. In particular, `max_per_page=20` produces the actual `limit=20` parameter. We do not know from these observations whether that parameter controls the provider's effective page size; several responses were underfilled.

October 16 matched controls used a 30-second request timeout, zero automatic retries and sequential calls. The October 17 comparison used a 15-second request timeout, zero automatic retries and sequential calls; independent query lanes were interleaved page by page. No intentional pacing sleep was inserted in that comparison. Exact execution times are supplied where retained.

**Counts:** a raw appearance is one returned top-level post slot before our application filtering; a distinct ID deduplicates those appearances. A known-positive recovery counts overlap with a fixed previously collected reference set. Stored application Posts additionally require our normal attribution/eligibility rules. These are different quantities and are labeled separately. Nested quoted/replied-to posts are not counted as extra top-level search results.

## 3. Minimal reproduction: July 31, 12:00–12:15

### Search parameters

Publication interval: `2026-07-31T12:00:00Z` to `2026-07-31T12:15:00Z`.
Epoch bounds: `1785499200` to `1785500100`.

The first request was equivalent to the following. This is an example to reproduce the request; the command was not run while preparing this report.

```bash
curl --get 'https://api.twitterapi.io/twitter/tweet/advanced_search' \
  --header 'X-API-Key: REPLACE_WITH_YOUR_API_KEY' \
  --header 'Accept: application/json' \
  --data-urlencode 'query=(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100' \
  --data-urlencode 'queryType=Latest' \
  --data-urlencode 'limit=20'
```

For each subsequent page, we kept `query`, `queryType` and `limit` unchanged and passed the preceding response's exact `next_cursor` as `cursor`. All four actual request-parameter sets and response hashes are in Appendix C, R01–R04. For a fresh reproduction, use freshly returned cursors; the validity of the archived October tokens has not been retested.

The fixed reference set contains 75 own-text matches for the whole term DeepSeek or 深度求索, excluding `xxyweb3` and quote-only mentions. Posts were created between 12:00:07 and 12:14:59 and first collected between 12:05:35.892055 and 12:37:45.290067 on July 31. It is a known-positive sample, not a census of all X posts.

### Observed pages and alternative searches

All D1–D8 search cases below use the same inline 15-minute epoch bounds, with `limit=20`. Full literal query variants are present in Appendix C. Page-count lists include the terminal empty request.

| Case | Change / endpoint | Mode | Actual page sizes | Distinct raw IDs | Known controls recovered | Local search ceiling |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Original DeepSeek query | Latest | 20, 20, 6, 0 | 46 | 34/75 | 20 pages / 400 results |
| D2 | Direct lookup of five D1 omissions | ID lookup | 5 | 5 | 5/5 requested | One lookup of five IDs |
| D3 | Remove `min_faves:0` only | Latest | 20, 20, 6, 0 | 46 | 34/75; same ID set as D1 | 8 pages / 160 results |
| D4 | Original query + OR of five missing authors | Latest | 0 | 0 | 0/5 | 8 pages / 160 results |
| D5 | Original query + `from:viktorg475` | Latest | 0 | 0 | 0/1 | 2 pages / 40 results |
| D6 | `from:viktorg475` only | Latest | 0 | 0 | 0/1 | 2 pages / 40 results |
| D7 | `from:SahilPanhotra` positive control | Latest | 1, 0 | 1 | 1/1 | 2 pages / 40 results |
| D8 | Original DeepSeek query | Top | 14, 13, 6, 0 | 33 | 27/75 | 6 pages / 120 results |
| D9 | Timeline for Wizarp_zz, replies included | Timeline | 15, 0 | 15 | Target absent | 4 pages; stopped after 2 |

D1 and D3 returned identical raw ID sets. D8 added two IDs outside the D1 set but **zero additional members of the 75 known controls**; the D1/D8 known-control union remained 34. D7 returned known post `2083164520349085898`, showing that this author-only syntax could retrieve at least one positive control.

For every D1/D3–D8 search, the final response had `has_next_page=false` and `next_cursor=null`. None ended because the configured result ceiling was reached. D7 used its second allowed request, but that request itself returned the terminal empty/no-next-page response. D1 did not make a forced extra request after the false flag because there was no remaining cursor.

### Five specific omissions that were available by ID

All five were absent from all D1 pages and returned through a single direct lookup within the same diagnostic run. Each captured lookup payload had a nonempty own-text DeepSeek match, a non-excluded author and `isRetweet=false`. Like counts and reply flags below are from that lookup, not assumed from old database values. Excerpts are deliberately short.

| Native post ID / public link | Author | Created UTC | Likes | Reply | Own-text excerpt |
| --- | --- | --- | --- | --- | --- |
| [2083160778341843345](https://x.com/viktorg475/status/2083160778341843345) | viktorg475 | 2026-07-31 12:00:07 | 1 | false | When you getting the new DeepSeek flash release? |
| [2083160925813543079](https://x.com/Web3Aible/status/2083160925813543079) | Web3Aible | 2026-07-31 12:00:42 | 0 | false | DeepSeek V4-Flash + DeepSeek Responses endpoint + OpenCode harness |
| [2083161065735532639](https://x.com/jhsmith409/status/2083161065735532639) | jhsmith409 | 2026-07-31 12:01:15 | 0 | false | DeepSeek-V4-Flash is natively MXFP4. |
| [2083161164914327965](https://x.com/Wizarp_zz/status/2083161164914327965) | Wizarp_zz | 2026-07-31 12:01:39 | 0 | false | DeepSeek-V4-Flash 这波更像是冲着 Agent 工作流来的 |
| [2083161198011265296](https://x.com/voidfreud/status/2083161198011265296) | voidfreud | 2026-07-31 12:01:47 | 1 | true | DeepSeek will normalize Fable-level intelligence at barely above free. |

The exact direct-lookup parameter was:

```json
{
  "tweet_ids": "2083160778341843345,2083160925813543079,2083161065735532639,2083161164914327965,2083161198011265296"
}
```

Replaying all 75 stored reference texts and these five lookup payloads through the same matcher used by normal collection and backfill accepted them in both paths. These five search omissions therefore occur before our attribution or database insertion step.

### Diagnostic execution windows

These are application-run intervals rather than per-request HTTP timestamps, except for the timeline timestamps explicitly recorded below.

| Cases | Execution interval on 2026-10-16 UTC |
| --- | --- |
| D1–D2 | 19:19:02.468648–19:19:06.219670 |
| D3–D4 | 19:25:50.079178–19:25:54.947328 |
| D5–D8 | 19:32:21.108384–19:32:29.241832 |
| D9 first request issued | 19:41:35.007233 |
| D9 continuation issued | 19:43:52.299023 |

### Timeline control and our parser issue

D9 called `/twitter/user/last_tweets` with `userId="809230456340156416"`, `includeReplies="true"` and an initially empty cursor. No date bound or limit parameter was sent to that endpoint. The target was `2083161164914327965` by Wizarp_zz.

The first response placed 15 posts under `data.tweets`, with top-level `has_next_page=true` and a top-level `next_cursor`. Our initial diagnostic parser incorrectly expected top-level `tweets` and failed after preserving the exact body. We corrected the read of that saved response, reused it without re-requesting page one, and sent its actual cursor for page two. That response had `data.tweets=[]`, `has_next_page=false`, but a nonempty `next_cursor`. We stopped on the empty/false response. There were two physical requests in total.

The 15 returned posts spanned 2016–2026; the known July 31 target was absent. We do not treat this bounded timeline test as proof of a complete lifetime enumeration. Please clarify the intended timeline history scope and handling of an empty response with a false continuation flag and a nonempty cursor.

## 4. Original July 30 backfill and window experiments

The original publication interval was the full UTC day: `2026-07-30T00:00:00Z` to `2026-07-31T00:00:00Z`, epochs `1785369600`–`1785456000`. We used eight frozen query groups, named A, B1, B2, B3, C1, C2, C3 and RARE_EXTRA. Those are our local group names, not provider endpoints. Every search used `queryType=Latest`, `limit=20`, inline epoch bounds and cursor continuation. All eight exact queries and the six isolated B1 variants are in Appendix A.

We then tested shorter bounds and simpler queries without widening the search terms. All seven collection experiments below ultimately ended with complete/provider-drained query scopes; temporary checkpoint/page/request/time limits were resumed until that point. Earlier checkpoint labels such as `page_cap` do not mean we permanently stopped after that page. The controller normally saved one 20-result page per checkpoint and continued its cursor on the next step.

| Case | Scenario | Physical search requests | Raw appearances | Distinct raw IDs in that scenario |
| --- | --- | --- | --- | --- |
| J1 | Eight full-day queries | 192 | 3585 | 3171 |
| J2 | B1, 12:00–13:00 only | 6 | 84 | 84 |
| J3 | Six B/C queries × 24 one-hour windows | 415 | 3655 | 3137 |
| J4 | Six separate B1 branches, 12:00–13:00 | 14 | 87 | 84 |
| J5 | B1, four 15-minute windows, 12:00–13:00 | 10 | 84 | 84 |
| J6 | Same full-day A query, corrected application roles | 15 | 269 | 269 |
| J7 | Six separate B1 branches, full day | 99 | 1813 | 1715 |

Across these overlapping experiments there were **751 search requests, 9,577 raw appearances and 3,619 distinct raw IDs**. These totals must not be interpreted as 751 full pages of different posts. Partial/empty pages, overlapping windows/routes and repeated comparisons account for the difference.

For B1 specifically, the original full-day enumeration took 56 pages and returned 1,095 distinct IDs. The 24-hourly-window enumeration took 121 pages and returned 1,716 distinct IDs, including all 1,095 original IDs plus 621 additional IDs. Within the noon hour, the full-day result set contained 3 IDs by their native publication timestamps, while J2 returned 84. The four 15-minute J5 windows and the six isolated-branch J4 searches also returned the same 84-ID union for that hour.

The original full-day page/request counts by route were A15 / B1 56 / B2 53 / B3 8 / C1 29 / C2 6 / C3 10 / RARE_EXTRA15. Every route reached an API end marker. J7's six full-day branch searches returned 1,715 distinct IDs; this is a separately measured set and is not asserted to be identical to the 1,716-ID hourly B1 set.

Our original controller had per-attempt ceilings of 200 requests, 300 seconds, 32 MiB and 100,000 items, with a campaign-wide 5,000-request ceiling. The hourly reconciliation used 200 requests/600 seconds per attempt and was resumed across attempts. These were local execution budgets, not URL parameters; final provider-drain observations, rather than budget exhaustion, determined the final states summarized here.

### Application issues separated from API recall

The database eventually held 2,086 distinct accepted July 30 Posts from these experiments: 1,552 original +35 from J2 +312 further from J3 +187 from J6. Other passes added no new stored Posts. We do not expect every raw search object to become an application Post: brand attribution, excluded-term checks, staff relevance and rare-type review apply.

J6 corrected our own list-author role attribution: the unchanged A query returned the same 269 raw IDs in 15 requests, while accepted records increased from 64 to 251. That 187-record gain is an application fix, not evidence of improved provider recall. A separate cached-import counter/transaction bug affected 18 otherwise qualified lookup records; it is also independent of the advanced-search omission controls.

The initial approximately 4,000-post daily expectation was a planning estimate, not a verified list of July 30 IDs. We are not asking support to explain a numerical target shortfall alone. The concrete support issues are the known matching IDs missing before filtering, and the different raw result sets under wider versus narrower time bounds.

## 5. Follow-up: controlled 5-minute, 10-minute and 1-hour searches

This later experiment ran on October 17 from `03:45:35.699831Z` to `03:50:16.779302Z` (281.08 seconds). It used the unchanged DeepSeek branch from section 3, `queryType=Latest`, `limit=20`, and the same hour of day on three publication dates.

| Publication date | UTC hour | Start epoch | End epoch |
| --- | --- | --- | --- |
| 2026-07-31 | 2026-07-31T12:00:00Z–13:00:00Z | 1785499200 | 1785502800 |
| 2026-08-31 | 2026-08-31T12:00:00Z–13:00:00Z | 1788177600 | 1788181200 |
| 2026-09-30 | 2026-09-30T12:00:00Z–13:00:00Z | 1790769600 | 1790773200 |

For each date and each of two passes, we issued twelve adjacent 5-minute queries, six adjacent 10-minute queries and one 60-minute query. For a resolution of `m` minutes, query `i` was precisely the base DeepSeek branch plus `since_time:(hour_start + 60*m*i)` and `until_time:(hour_start + 60*m*(i+1))`, with `i=0..(60/m-1)`. Each exact logical query had its own cursor chain.

We interleaved the 18 date/resolution/pass lanes in a frozen order, issuing one physical page per active lane per round. Within a lane, we finished each slice before moving chronologically to its next slice. The complete order and every actual HTTP parameter set, time, status, response size and hash are included in Appendix D.

Local limits were 100 pages per exact query, 400 physical calls overall, 380 search calls, 1,200 elapsed seconds, zero automatic retries and a USD 1.20 estimated-spend ceiling. The remaining call reservation supported availability lookups in batches of at most 50 IDs. No limit was reached: **114/114 logical queries ended as provider-exhausted**, with **254 search calls +7 lookup calls =261 physical calls**, all recorded HTTP 200, zero errors/retries and no unresolved charges. There were no application Post writes or model calls in this diagnostic.

The fixed control populations comprised own-text matching posts first collected on their publication day: July31 287, August31 97 and September30 60. After search, we looked up all 346 known IDs missed by any method/pass. Search or lookup payloads confirmed 273/95/59 respectively were still available and matched the same text/author/time/nonnegative-likes conditions. Fourteen July, two August and one September control were not returned or unavailable by lookup; those are excluded from the available-matching denominator. No deletion or suspension cause is assumed.

### Results per pass

Both passes returned exactly the same ID set for every date/resolution cell, so the following rows apply to each pass independently. Distinct raw search IDs include results outside our fixed known-positive population.

| Date | Window minutes | Calls per pass | Distinct raw IDs | Stored controls recovered | Available matching controls recovered |
| --- | --- | --- | --- | --- | --- |
| 2026-07-31 | 5 | 25 | 183 | 119/287 | 119/273 |
| 2026-07-31 | 10 | 18 | 182 | 118/287 | 118/273 |
| 2026-07-31 | 60 | 5 | 80 | 55/287 | 55/273 |
| 2026-08-31 | 5 | 24 | 45 | 35/97 | 35/95 |
| 2026-08-31 | 10 | 12 | 45 | 35/97 | 35/95 |
| 2026-08-31 | 60 | 4 | 45 | 35/97 | 35/95 |
| 2026-09-30 | 5 | 24 | 55 | 17/60 | 17/59 |
| 2026-09-30 | 10 | 12 | 55 | 17/60 | 17/59 |
| 2026-09-30 | 60 | 3 | 21 | 9/60 | 9/59 |

Five-minute and ten-minute windows returned many more IDs than a one-hour query in July and September; August was unchanged. Narrowing still did not restore all known available matching posts. July 10-minute search also missed one known control returned by the hour search, so a narrower-window union was not always a strict superset.

The original 75-post, 15-minute reference set is a subset of the July hourly control population. Within that original subset, this follow-up recovered 34/75 using 5-minute queries, and 33/75 using 10-minute or 60-minute queries; 71/75 were currently available and matching. These are different bounds and a different execution date from the October 16 D1 search, so they are not an exact replay of D1.

Across all resolutions and both passes, 1,422 identified raw search appearances collapsed to 283 distinct IDs. There were no within-cell duplicate extras, missing IDs or invalid/out-of-window timestamps in search responses. Lookup responses contained five blank-ID/unknown-time slots, which were preserved and excluded from identified-post counts. We did not count lookup results as search recovery.

These are three different date cohorts with different volumes and account states. They do not demonstrate a causal effect of post age. Exact repeat stability in this experiment is an observation, not proof of caching or a guarantee about future requests.

## 6. Questions for TwitterAPI.io

1. Are the literal `since_time` / `until_time` epoch operators, `queryType=Latest` and the `limit=20` parameter correct for complete historical enumeration? What are the exact endpoint-boundary semantics?
2. Why do the five linked posts return by ID but disappear from the fully paginated matching search? Are there search-specific visibility/indexing/retention conditions that would explain these IDs?
3. Is `has_next_page=false` with a null cursor a definitive endpoint for the query, even when matching ID-lookup-accessible posts remain? Is there another supported historical-search enumeration mode or required parameter?
4. Why does a full-day query omit IDs returned by the identical query restricted to an hour, and why do 5-/10-minute slices still omit available known positives? Is any documented sampling, ranking, result ceiling, query-length limit or server-side time-window rule relevant?
5. Does `min_faves:0` have any special search semantics? Removing it produced an identical set in our minimal test. Are replies, reposts, edited posts or other post classes treated differently by search versus ID lookup?
6. Do the five-author OR and single-author query forms in Appendix C need different syntax? In particular, `from:viktorg475` alone returned no result for a known post in the exact interval, while the positive `from:SahilPanhotra` control succeeded.
7. For `/twitter/user/last_tweets`, what historical depth should we expect, and which continuation signal should govern an empty `data.tweets` response with `has_next_page=false` but a nonempty `next_cursor`?
8. Which additional diagnostic fields would help your investigation? We retained response bodies and SHA-256 hashes for the controlled tests, but not provider response-header request IDs for October 16. We can supply selected saved evidence through the existing support conversation without repeating the full collection.

## 7. Evidence boundaries

The October 16 minimal controls have 20 saved exact response bodies totaling 660,306 bytes, verified against their saved hashes. Appendix C reconstructs R01–R18 search/lookup parameters from frozen instructions, actual client code and the preceding captured cursor; it is not a packet capture. Per-request timestamps, HTTP status values and response-header request IDs were not retained for those 18 requests. Timeline request arguments/times were recorded directly.

The October 17 comparison has a directly recorded 261-request ledger and exact response bodies totaling 8,290,306 bytes; every body/hash was rechecked when assembling this report. Its request IDs are our local ledger labels, not provider-issued identifiers. It records per-request issue/completion times and HTTP status; authentication and response headers were not archived.

The broader July 30 collection preserves frozen query/window definitions and page-level ID/count/exclusion receipts, but not all 751 raw HTTP response bodies or full network traces. Consequently we provide its exact scenario parameters and aggregate results, while using the controlled captures for detailed reproduction. Appendix request tables contain response metadata and native IDs rather than copying full post bodies.

No paid API call, new collection, production import, application change or deployment was performed to prepare this report.

## Appendix A. Exact July 30 scenario queries and bounds

All queries below are literal frozen base queries. For each request, append ` since_time:<start_epoch> until_time:<end_epoch>` to the base query, send `queryType=Latest` and `limit=20`, omit cursor on the first page, and then forward the previous response's exact cursor. Query text, spacing, quotes and parentheses have not been rewritten.

### A

```text
(list:2067062923525275922) min_faves:0 -from:xxyweb3
```

### B1

```text
((DeepSeek OR 深度求索) OR (dots3-note OR dots studio OR "dots 3 note" OR "dots-3-note" OR "dots.3-note" OR "dots3 note" OR "dots-studio" OR dots.ocr OR dots.tts OR dots.llm1 OR dots.vlm OR dots.mocr OR dots3 OR dots4) OR (Hunyuan OR 混元 OR 腾讯混元 OR Hy3 OR Hy4 OR Hy5 OR Hy4-preview OR Hy5-preview) OR (Hailuo OR MiniMax OR 海螺) OR (Qwen OR Qwen3 OR 通义千问) OR (StepFun OR 阶跃星辰)) min_faves:0 -from:xxyweb3
```

### C1

```text
((Llama OR Llama 3 OR Llama 4 OR Meta Llama OR Code Llama) OR (MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Mistral OR Mixtral) OR (Kimi OR Moonshot AI OR 月之暗面 OR 暗面 OR MoonshotAI) OR (Yi OR 01.AI OR 零一万物 OR Yi LLM OR Yi-VL OR Yi-Coder)) (llm OR model OR api OR agentic OR huggingface) min_faves:0 -from:xxyweb3
```

### C2

```text
((ERNIE OR 文心一言) OR (Upstage OR Solar Pro OR Solar LLM OR 업스테이지)) (llm OR model OR api OR agentic OR huggingface OR baidu OR 文心) min_faves:0 -from:xxyweb3
```

### C3

```text
(((Doubao OR ByteDance) OR (Kuaishou OR KwaiYii) OR (SenseChat OR SenseTime) OR (glm OR ChatGLM OR Zhipu OR 智谱 OR Z.ai OR GLM-4 OR GLM-5 OR GLM-6)) (llm OR model OR api OR agentic OR huggingface) OR ("Ox Alpha" OR OxAlpha OR ox-alpha)) min_faves:0 -from:xxyweb3
```

### B2

```text
(@MiniMaxAgent OR @MiniMax_AI OR @hailuo_ai OR @Ali_TongyiLab OR @Alibaba_Qwen OR @deepseek_ai OR @AntLingAGI OR @TheInclusionAI OR @ZhihuFrontier OR @robbyant_brain OR @MistralAI OR @StepFun_ai OR @stepfunai OR @TencentHunyuan OR @NVIDIAAI OR @NVIDIAAIDev OR @LG_AI_Research OR @SakanaAILabs) min_faves:0 -from:xxyweb3
```

### B3

```text
(@XiaomiMiMo OR @XiaomiMiMoDevs OR @Kimi_Moonshot OR @ErnieforDevs OR @PaddlePaddle OR @AIatMeta OR @BytePlusGlobal OR @bytedanceoss OR @doubaoai OR @01AI_Yi OR @Kling_ai OR @SenseTime_AI OR @upstageai) min_faves:0 -from:xxyweb3
```

### RARE_EXTRA

```text
(("I've joined" OR "I joined" OR "I left" OR "我加入" OR "我离开" OR 出任 OR 换帅 OR に入社 OR を退職) (AI OR LLM OR OpenAI OR Anthropic) OR ("I've joined @deepseek_ai") OR ("we're hiring" OR "currently hiring" OR 招聘 OR 募集中) (engineer OR researcher) OR ("we'll be at" OR 登壇) ("AI conference" OR summit) OR ("applications open" OR "apply by" OR 申请) (hackathon OR fellowship) (AI OR LLM) OR (introducing OR 开源 OR 发布) (model OR weights OR Preview) OR ("step 5 preview")) min_faves:0
```

### Isolated B1 branch queries used by J4 and J7

Branch 1:

```text
(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3
```

Branch 2:

```text
(dots3-note OR dots studio OR "dots 3 note" OR "dots-3-note" OR "dots.3-note" OR "dots3 note" OR "dots-studio" OR dots.ocr OR dots.tts OR dots.llm1 OR dots.vlm OR dots.mocr OR dots3 OR dots4) min_faves:0 -from:xxyweb3
```

Branch 3:

```text
(Hunyuan OR 混元 OR 腾讯混元 OR Hy3 OR Hy4 OR Hy5 OR Hy4-preview OR Hy5-preview) min_faves:0 -from:xxyweb3
```

Branch 4:

```text
(Hailuo OR MiniMax OR 海螺) min_faves:0 -from:xxyweb3
```

Branch 5:

```text
(Qwen OR Qwen3 OR 通义千问) min_faves:0 -from:xxyweb3
```

Branch 6:

```text
(StepFun OR 阶跃星辰) min_faves:0 -from:xxyweb3
```

### Complete window construction for J1–J7

| Cases | Queries | Start/end epochs |
| --- | --- | --- |
| J1 | All eight base queries | 1785369600 → 1785456000 |
| J2 | B1 only | 1785412800 → 1785416400 |
| J3 | B1, B2, B3, C1, C2, C3 | For each h=0..23: 1785369600+3600*h → 1785369600+3600*(h+1) |
| J4 | Each of six isolated B1 branches | 1785412800 → 1785416400 |
| J5 | B1 only, four adjacent windows | 1785412800→1785413700; 1785413700→1785414600; 1785414600→1785415500; 1785415500→1785416400 |
| J6 | A only, same API query; application-role fix | 1785369600 → 1785456000 |
| J7 | Each of six isolated B1 branches | 1785369600 → 1785456000 |

## Appendix B. Complete original 75-ID reference population

The population is partitioned below by the October 16 D1 historical-search outcome. All IDs are decimal strings. The SHA-256 of the lexicographically sorted 75 IDs joined with newline characters and no trailing newline is `aaf0edb1426352f76553a9f3dd5daba2b47eb02c920a79c7dde195cc55b13461`.

### 34 known IDs found in D1

```json
[
  "2083160786109636633",
  "2083160816069808571",
  "2083160982533136757",
  "2083161152603750851",
  "2083161299828277414",
  "2083161506087305480",
  "2083161527897510145",
  "2083161888083624388",
  "2083161954009460789",
  "2083162209556025471",
  "2083162235682296082",
  "2083162254686486697",
  "2083162331060605315",
  "2083162394113487223",
  "2083162451088949315",
  "2083162453072834770",
  "2083162593313640806",
  "2083162610363719907",
  "2083162657931301354",
  "2083162892782715211",
  "2083162905118220506",
  "2083162965910413762",
  "2083162983530697109",
  "2083162986621927859",
  "2083163158298886455",
  "2083163378886066305",
  "2083163475795390873",
  "2083163554249920796",
  "2083164066516754812",
  "2083164225162064148",
  "2083164318636314817",
  "2083164337926226351",
  "2083164478925926628",
  "2083164520349085898"
]
```

### 41 known IDs missing from D1

```json
[
  "2083160778341843345",
  "2083160925813543079",
  "2083161065735532639",
  "2083161164914327965",
  "2083161198011265296",
  "2083161292878004305",
  "2083161383521132709",
  "2083161535656886351",
  "2083161577289880004",
  "2083161618385637796",
  "2083161737046511704",
  "2083161902427811841",
  "2083162172159672786",
  "2083162215889117631",
  "2083162309099225167",
  "2083162327470293440",
  "2083162444042469623",
  "2083162624464724230",
  "2083162686528028749",
  "2083162849484968420",
  "2083162878530523531",
  "2083162937150079488",
  "2083162968762577152",
  "2083163005890523298",
  "2083163167971008766",
  "2083163382924873901",
  "2083163472381333599",
  "2083163549057032546",
  "2083163590027104523",
  "2083163723099767138",
  "2083163749699977538",
  "2083163840964071568",
  "2083163892780572672",
  "2083163894240166129",
  "2083163917740626264",
  "2083163983335600161",
  "2083164143130210730",
  "2083164168480247842",
  "2083164216542838897",
  "2083164266853470259",
  "2083164375758577760"
]
```

## Appendix C. All 20 October 16 controlled request parameter sets

Each JSON record supplies the endpoint, complete decoded URL query parameters, captured top-level result IDs/count, continuation fields and response SHA-256/bytes. Cursors are untruncated. The API key is omitted from every record. R01–R18 time evidence is only the enclosing application-run interval, not a claimed individual request timestamp. No provider response-body text is reproduced.

### R01 — D1

```json
{
  "request": "R01",
  "case": "D1",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:19:02.468648+00:00",
    "end_utc": "2026-10-16T19:19:06.21967+00:00"
  },
  "response": {
    "raw_count": 20,
    "returned_ids": [
      "2083164520349085898",
      "2083164478925926628",
      "2083164469111263411",
      "2083164342036639873",
      "2083164337926226351",
      "2083164318636314817",
      "2083164228559716811",
      "2083164225162064148",
      "2083164066516754812",
      "2083163554249920796",
      "2083163475795390873",
      "2083163378886066305",
      "2083163278042440086",
      "2083163193611059406",
      "2083163158298886455",
      "2083162986621927859",
      "2083162983530697109",
      "2083162965910413762",
      "2083162905118220506",
      "2083162892782715211"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OGdKZbBSwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGaSMAAnEAoABh1MZpIv_9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9HZ0NOZWcyaHpvNHd3dUY1Q3pIT2pocmpCVzRjSWM2T0xUWVpZeEZCem80dTZYMnJDQkhPamlKT2ZhTVprYzZPR3pBdGVCc3h6bzRqY3NHMUVjSE9qaDJ2dVdBVGNjNk9HeVNwY1JsUnpvNFowcGxzRkxIT2poNHpSYkFNNGM2T0xwSlJZUXdSem80ZmJjMjZHVwAA",
    "sha256": "b9078f8b225698fe61de38f669658de7756cf00e645f994f6f6eb4fce5ff10ff",
    "bytes": 93202
  }
}
```

### R02 — D1

```json
{
  "request": "R02",
  "case": "D1",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OGdKZbBSwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGaSMAAnEAoABh1MZpIv_9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9HZ0NOZWcyaHpvNHd3dUY1Q3pIT2pocmpCVzRjSWM2T0xUWVpZeEZCem80dTZYMnJDQkhPamlKT2ZhTVprYzZPR3pBdGVCc3h6bzRqY3NHMUVjSE9qaDJ2dVdBVGNjNk9HeVNwY1JsUnpvNFowcGxzRkxIT2poNHpSYkFNNGM2T0xwSlJZUXdSem80ZmJjMjZHVwAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:19:02.468648+00:00",
    "end_utc": "2026-10-16T19:19:06.21967+00:00"
  },
  "response": {
    "raw_count": 20,
    "returned_ids": [
      "2083162657931301354",
      "2083162610363719907",
      "2083162593313640806",
      "2083162453072834770",
      "2083162451088949315",
      "2083162394113487223",
      "2083162336060469404",
      "2083162331060605315",
      "2083162254686486697",
      "2083162235682296082",
      "2083162209556025471",
      "2083162103947678186",
      "2083161954009460789",
      "2083161888083624388",
      "2083161780227080452",
      "2083161527897510145",
      "2083161506087305480",
      "2083161299828277414",
      "2083161274536677565",
      "2083161152603750851"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OAH_tcBwwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTGaSMAAnEAoABh1MZpIv_7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T0JmWUJkUkFSem80ZzVYbTBDQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk9NTUxoZVFzeHpvNEZwTUdnRUlIT2pnc3p6YlFjUWM2T0ViaWx0d25Cem80dE5obGpFVUhPamlKT2ZhTVprYzZPRUVLMW9SRWh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9FMlVwYkFReHpvNGJKS2x4R1ZIT2poQ0pnWEFLa2M2T0dkS1piQlN4em80ZmJjMjZHV0hPamhWMi9YVVdZYzZPTVlIQnF3eWh6bzRBZisxd0hESE9qaXJuR1c0WHdjNk9DYUlCc0JCQnpvNHUyaTJzR3ZIT2pob0FqWG9Ob2M2T0ZtZTFxUjZoem80Q1JpbTlDOUhPamc1WDliVWVvYzZPRXBEcFl4ZHh6bzRhNHdWdUhDSE9qaTdwZmFzSUVjNk9FYVlGZVJneHpvNGJNQzE0R3pIT2ppTnl3YlVSd2M2T0RDbGxld05Sem80VnRvR3VEakhPamk2U1VXRU1FYzZPSGpORnNBemc9PQAA",
    "sha256": "1b45419d3441d25f27bd2e7541db070f8f3dcbdbce4e9349786c7b2658c93f59",
    "bytes": 85042
  }
}
```

### R03 — D1

```json
{
  "request": "R03",
  "case": "D1",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OAH_tcBwwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTGaSMAAnEAoABh1MZpIv_7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T0JmWUJkUkFSem80ZzVYbTBDQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk9NTUxoZVFzeHpvNEZwTUdnRUlIT2pnc3p6YlFjUWM2T0ViaWx0d25Cem80dE5obGpFVUhPamlKT2ZhTVprYzZPRUVLMW9SRWh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9FMlVwYkFReHpvNGJKS2x4R1ZIT2poQ0pnWEFLa2M2T0dkS1piQlN4em80ZmJjMjZHV0hPamhWMi9YVVdZYzZPTVlIQnF3eWh6bzRBZisxd0hESE9qaXJuR1c0WHdjNk9DYUlCc0JCQnpvNHUyaTJzR3ZIT2pob0FqWG9Ob2M2T0ZtZTFxUjZoem80Q1JpbTlDOUhPamc1WDliVWVvYzZPRXBEcFl4ZHh6bzRhNHdWdUhDSE9qaTdwZmFzSUVjNk9FYVlGZVJneHpvNGJNQzE0R3pIT2ppTnl3YlVSd2M2T0RDbGxld05Sem80VnRvR3VEakhPamk2U1VXRU1FYzZPSGpORnNBemc9PQAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:19:02.468648+00:00",
    "end_utc": "2026-10-16T19:19:06.21967+00:00"
  },
  "response": {
    "raw_count": 6,
    "returned_ids": [
      "2083160982533136757",
      "2083160968893206580",
      "2083160951956660582",
      "2083160853701071140",
      "2083160816069808571",
      "2083160786109636633"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTGaSMAAnEAoABh1MZpIv_4rQCwAHAAACCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDNGM2T0lPVjV0QWdSem80RjlnRjFFQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2pnV2t3YUFRZ2M2T0N6UE50QnhCem80UnVLVzNDY0hPamkwMkdXTVJRYzZPSWs1OW94bVJ6bzM3S3FGcUFaSE9qaEJDdGFFUkljNk9FMnlOWncwaHpvNGRyN2xnRTNIT2poTmxLV3dFTWM2T0d5U3BjUmxSem80ZmJjMjZHV0hPamhuU21Xd1VzYzZPRUltQmNBcVJ6bzRWZHYxMUZtSE9qZndtYmFFU1FjNk4rNW85cVJ1eHpvNHhnY0dyREtIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPamk3YUxhd2E4YzZPR2dDTmVnMmh6bzRXWjdXcEhxSE9qZzVYOWJVZW9jNk9Ba1lwdlF2UnpvNGE0d1Z1SENIT2poS1E2V01YY2M2T0x1bDlxd2dSem8zK0JsMTJGMUhPamhHbUJYa1lNYzZPSTNMQnRSSEJ6bzRiTUMxNEd6SE9qZ3dwWlhzRFVjNk4vZE9OYVFOQnpvNFZ0b0d1RGpIT2ppNlNVV0VNRWM2T0hqTkZzQXpnPT0AAA",
    "sha256": "b7b72bf71dff2934b16b9f2dc86e6ef4aac184f9b2b8da9d9bafc4244301cfff",
    "bytes": 26174
  }
}
```

### R04 — D1

```json
{
  "request": "R04",
  "case": "D1",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTGaSMAAnEAoABh1MZpIv_4rQCwAHAAACCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDNGM2T0lPVjV0QWdSem80RjlnRjFFQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2pnV2t3YUFRZ2M2T0N6UE50QnhCem80UnVLVzNDY0hPamkwMkdXTVJRYzZPSWs1OW94bVJ6bzM3S3FGcUFaSE9qaEJDdGFFUkljNk9FMnlOWncwaHpvNGRyN2xnRTNIT2poTmxLV3dFTWM2T0d5U3BjUmxSem80ZmJjMjZHV0hPamhuU21Xd1VzYzZPRUltQmNBcVJ6bzRWZHYxMUZtSE9qZndtYmFFU1FjNk4rNW85cVJ1eHpvNHhnY0dyREtIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPamk3YUxhd2E4YzZPR2dDTmVnMmh6bzRXWjdXcEhxSE9qZzVYOWJVZW9jNk9Ba1lwdlF2UnpvNGE0d1Z1SENIT2poS1E2V01YY2M2T0x1bDlxd2dSem8zK0JsMTJGMUhPamhHbUJYa1lNYzZPSTNMQnRSSEJ6bzRiTUMxNEd6SE9qZ3dwWlhzRFVjNk4vZE9OYVFOQnpvNFZ0b0d1RGpIT2ppNlNVV0VNRWM2T0hqTkZzQXpnPT0AAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:19:02.468648+00:00",
    "end_utc": "2026-10-16T19:19:06.21967+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R05 — D2

```json
{
  "request": "R05",
  "case": "D2",
  "method": "GET",
  "endpoint": "/twitter/tweets",
  "arguments": {
    "tweet_ids": "2083160778341843345,2083160925813543079,2083161065735532639,2083161164914327965,2083161198011265296"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:19:02.468648+00:00",
    "end_utc": "2026-10-16T19:19:06.21967+00:00"
  },
  "response": {
    "raw_count": 5,
    "returned_ids": [
      "2083160778341843345",
      "2083160925813543079",
      "2083161065735532639",
      "2083161164914327965",
      "2083161198011265296"
    ],
    "sha256": "5229ec3c7da3e2ae56e1eaa83928b922e9a396a39d01a6026b1753235fdae60f",
    "bytes": 19112
  }
}
```

### R06 — D3

```json
{
  "request": "R06",
  "case": "D3",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:25:50.079178+00:00",
    "end_utc": "2026-10-16T19:25:54.947328+00:00"
  },
  "response": {
    "raw_count": 20,
    "returned_ids": [
      "2083164520349085898",
      "2083164478925926628",
      "2083164469111263411",
      "2083164342036639873",
      "2083164337926226351",
      "2083164318636314817",
      "2083164228559716811",
      "2083164225162064148",
      "2083164066516754812",
      "2083163554249920796",
      "2083163475795390873",
      "2083163378886066305",
      "2083163278042440086",
      "2083163193611059406",
      "2083163158298886455",
      "2083162986621927859",
      "2083162983530697109",
      "2083162965910413762",
      "2083162905118220506",
      "2083162892782715211"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OGdKZbBSwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGggP0AnEAoABh1MaCA_P9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9HZ0NOZWcyaHpvNHd3dUY1Q3pIT2pocmpCVzRjSWM2T0xUWVpZeEZCem80dTZYMnJDQkhPamlKT2ZhTVprYzZPR3pBdGVCc3h6bzRqY3NHMUVjSE9qaDJ2dVdBVGNjNk9HeVNwY1JsUnpvNFowcGxzRkxIT2poNHpSYkFNNGM2T0xwSlJZUXdSem80ZmJjMjZHVwAA",
    "sha256": "905c75a9d7ed5e63d18500ef7589894d6ad3d23cfb594d4dda4bd06747fea009",
    "bytes": 93202
  }
}
```

### R07 — D3

```json
{
  "request": "R07",
  "case": "D3",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OGdKZbBSwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGggP0AnEAoABh1MaCA_P9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9HZ0NOZWcyaHpvNHd3dUY1Q3pIT2pocmpCVzRjSWM2T0xUWVpZeEZCem80dTZYMnJDQkhPamlKT2ZhTVprYzZPR3pBdGVCc3h6bzRqY3NHMUVjSE9qaDJ2dVdBVGNjNk9HeVNwY1JsUnpvNFowcGxzRkxIT2poNHpSYkFNNGM2T0xwSlJZUXdSem80ZmJjMjZHVwAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:25:50.079178+00:00",
    "end_utc": "2026-10-16T19:25:54.947328+00:00"
  },
  "response": {
    "raw_count": 20,
    "returned_ids": [
      "2083162657931301354",
      "2083162610363719907",
      "2083162593313640806",
      "2083162453072834770",
      "2083162451088949315",
      "2083162394113487223",
      "2083162336060469404",
      "2083162331060605315",
      "2083162254686486697",
      "2083162235682296082",
      "2083162209556025471",
      "2083162103947678186",
      "2083161954009460789",
      "2083161888083624388",
      "2083161780227080452",
      "2083161527897510145",
      "2083161506087305480",
      "2083161299828277414",
      "2083161274536677565",
      "2083161152603750851"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OAH_tcBwwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTGggP0AnEAoABh1MaCA_P7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T0JmWUJkUkFSem80ZzVYbTBDQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk9NTUxoZVFzeHpvNEZwTUdnRUlIT2pnc3p6YlFjUWM2T0ViaWx0d25Cem80dE5obGpFVUhPamlKT2ZhTVprYzZPRUVLMW9SRWh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9FMlVwYkFReHpvNGJKS2x4R1ZIT2poQ0pnWEFLa2M2T0dkS1piQlN4em80ZmJjMjZHV0hPamhWMi9YVVdZYzZPTVlIQnF3eWh6bzRBZisxd0hESE9qaXJuR1c0WHdjNk9DYUlCc0JCQnpvNHUyaTJzR3ZIT2pob0FqWG9Ob2M2T0ZtZTFxUjZoem80Q1JpbTlDOUhPamc1WDliVWVvYzZPRXBEcFl4ZHh6bzRhNHdWdUhDSE9qaTdwZmFzSUVjNk9FYVlGZVJneHpvNGJNQzE0R3pIT2ppTnl3YlVSd2M2T0RDbGxld05Sem80VnRvR3VEakhPamk2U1VXRU1FYzZPSGpORnNBemc9PQAA",
    "sha256": "19e67f8a1bc458328dc525a6df6b357d3659e4f521ff3b809481fb5842de9242",
    "bytes": 85034
  }
}
```

### R08 — D3

```json
{
  "request": "R08",
  "case": "D3",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OAH_tcBwwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTGggP0AnEAoABh1MaCA_P7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T0JmWUJkUkFSem80ZzVYbTBDQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk9NTUxoZVFzeHpvNEZwTUdnRUlIT2pnc3p6YlFjUWM2T0ViaWx0d25Cem80dE5obGpFVUhPamlKT2ZhTVprYzZPRUVLMW9SRWh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9FMlVwYkFReHpvNGJKS2x4R1ZIT2poQ0pnWEFLa2M2T0dkS1piQlN4em80ZmJjMjZHV0hPamhWMi9YVVdZYzZPTVlIQnF3eWh6bzRBZisxd0hESE9qaXJuR1c0WHdjNk9DYUlCc0JCQnpvNHUyaTJzR3ZIT2pob0FqWG9Ob2M2T0ZtZTFxUjZoem80Q1JpbTlDOUhPamc1WDliVWVvYzZPRXBEcFl4ZHh6bzRhNHdWdUhDSE9qaTdwZmFzSUVjNk9FYVlGZVJneHpvNGJNQzE0R3pIT2ppTnl3YlVSd2M2T0RDbGxld05Sem80VnRvR3VEakhPamk2U1VXRU1FYzZPSGpORnNBemc9PQAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:25:50.079178+00:00",
    "end_utc": "2026-10-16T19:25:54.947328+00:00"
  },
  "response": {
    "raw_count": 6,
    "returned_ids": [
      "2083160982533136757",
      "2083160968893206580",
      "2083160951956660582",
      "2083160853701071140",
      "2083160816069808571",
      "2083160786109636633"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTGggP0AnEAoABh1MaCA_P4rQCwAHAAACCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDNGM2T0lPVjV0QWdSem80RjlnRjFFQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2pnV2t3YUFRZ2M2T0N6UE50QnhCem80UnVLVzNDY0hPamkwMkdXTVJRYzZPSWs1OW94bVJ6bzM3S3FGcUFaSE9qaEJDdGFFUkljNk9FMnlOWncwaHpvNGRyN2xnRTNIT2poTmxLV3dFTWM2T0d5U3BjUmxSem80ZmJjMjZHV0hPamhuU21Xd1VzYzZPRUltQmNBcVJ6bzRWZHYxMUZtSE9qZndtYmFFU1FjNk4rNW85cVJ1eHpvNHhnY0dyREtIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPamk3YUxhd2E4YzZPR2dDTmVnMmh6bzRXWjdXcEhxSE9qZzVYOWJVZW9jNk9Ba1lwdlF2UnpvNGE0d1Z1SENIT2poS1E2V01YY2M2T0x1bDlxd2dSem8zK0JsMTJGMUhPamhHbUJYa1lNYzZPSTNMQnRSSEJ6bzRiTUMxNEd6SE9qZ3dwWlhzRFVjNk4vZE9OYVFOQnpvNFZ0b0d1RGpIT2ppNlNVV0VNRWM2T0hqTkZzQXpnPT0AAA",
    "sha256": "374b8c1bac84f0263f2d55ac83eba734f60234f455fd037e2cae5d3a2e8d050a",
    "bytes": 26174
  }
}
```

### R09 — D3

```json
{
  "request": "R09",
  "case": "D3",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTGggP0AnEAoABh1MaCA_P4rQCwAHAAACCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDNGM2T0lPVjV0QWdSem80RjlnRjFFQkhPampEbmNYY09RYzZPRCtGaHJRZnh6bzR0UXNHa0hMSE9qZ0trWWJBS1ljNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2pnV2t3YUFRZ2M2T0N6UE50QnhCem80UnVLVzNDY0hPamkwMkdXTVJRYzZPSWs1OW94bVJ6bzM3S3FGcUFaSE9qaEJDdGFFUkljNk9FMnlOWncwaHpvNGRyN2xnRTNIT2poTmxLV3dFTWM2T0d5U3BjUmxSem80ZmJjMjZHV0hPamhuU21Xd1VzYzZPRUltQmNBcVJ6bzRWZHYxMUZtSE9qZndtYmFFU1FjNk4rNW85cVJ1eHpvNHhnY0dyREtIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPamk3YUxhd2E4YzZPR2dDTmVnMmh6bzRXWjdXcEhxSE9qZzVYOWJVZW9jNk9Ba1lwdlF2UnpvNGE0d1Z1SENIT2poS1E2V01YY2M2T0x1bDlxd2dSem8zK0JsMTJGMUhPamhHbUJYa1lNYzZPSTNMQnRSSEJ6bzRiTUMxNEd6SE9qZ3dwWlhzRFVjNk4vZE9OYVFOQnpvNFZ0b0d1RGpIT2ppNlNVV0VNRWM2T0hqTkZzQXpnPT0AAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:25:50.079178+00:00",
    "end_utc": "2026-10-16T19:25:54.947328+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R10 — D4

```json
{
  "request": "R10",
  "case": "D4",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 (from:Web3Aible OR from:Wizarp_zz OR from:jhsmith409 OR from:viktorg475 OR from:voidfreud) since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:25:50.079178+00:00",
    "end_utc": "2026-10-16T19:25:54.947328+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R11 — D5

```json
{
  "request": "R11",
  "case": "D5",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 from:viktorg475 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R12 — D6

```json
{
  "request": "R12",
  "case": "D6",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "from:viktorg475 since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R13 — D7

```json
{
  "request": "R13",
  "case": "D7",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "from:SahilPanhotra since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 1,
    "returned_ids": [
      "2083164520349085898"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OMYHBqwygAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGmfqQAnEAoABh1MaZ-o_9jwCwAHAAAAKEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBRWM2T01ZSEJxd3lnPT0AAA",
    "sha256": "4da1b89edc2965a4da472c95ac6f88d090934727fb2279148db8eb7f0aca1d2f",
    "bytes": 7113
  }
}
```

### R14 — D7

```json
{
  "request": "R14",
  "case": "D7",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "from:SahilPanhotra since_time:1785499200 until_time:1785500100",
    "queryType": "Latest",
    "limit": 20,
    "cursor": "DAADDAABCgABHOjjGBwasMoKAAIc6OMYHBqwygAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGmfqQAnEAoABh1MaZ-o_9jwCwAHAAAAKEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBRWM2T01ZSEJxd3lnPT0AAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R15 — D8

```json
{
  "request": "R15",
  "case": "D8",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Top",
    "limit": 20
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 14,
    "returned_ids": [
      "2083163475795390873",
      "2083163158298886455",
      "2083161954009460789",
      "2083160982533136757",
      "2083161888083624388",
      "2083161274536677565",
      "2083162331060605315",
      "2083162453072834770",
      "2083160968893206580",
      "2083164520349085898",
      "2083162209556025471",
      "2083162394113487223",
      "2083164225162064148",
      "2083162235682296082"
    ],
    "has_next_page": true,
    "next_cursor": "DAACCgACHUxpoYdAJxAKAAMdTGmhhz_Y8AgABAAAAAILAAUAAAFQRW1QQzZ3QUFBZlEvZ0dKTjB2R3AvQUFBQUIwYzZKbzlLcFl3dnh6bzRQNFdHdEIvSE9pM1Q1UWFRUjhjNk4vWlIxZGhaaHpvNEtxMWw1QS9IT2pnc3p6YlFjUWM2T0JhVEJvQkNCem80dE5obGpFVUhPamhscXFYc09RYzZPSWs1OW94bVJ6bzRRUXJXaEVTSE9qZ2lYWFc4RWdjNk9IYSs1WUJOeHpvNFRiSTFuRFNIT2pnc2dNVzhkNGM2Tit5cWhhZ0dSem8zeWNIbGpCRUhPamhwMzRYQWdBYzZPQkw5aGNnSnh6bzR4Z2NHckRLSE9qU2dDSVhnT1VjNk4xZjU5YXd4UnpvNENSaW05QzlIT2poS1E2V01YY2M2Ti9nWmRkaGRSem80UnBnVjVHREhPamhjemJhNEhRYzZPRENsbGV3TlJ6bzM5MDQxcEEwCAAGAAAAAAgABwAAAAAMAAgKAAEc6N_dONaQNAAAAA",
    "sha256": "098d263ffc8861653bf6ad4ff35250109afc693d217e4e1c123f984706ad61b3",
    "bytes": 85795
  }
}
```

### R16 — D8

```json
{
  "request": "R16",
  "case": "D8",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Top",
    "limit": 20,
    "cursor": "DAACCgACHUxpoYdAJxAKAAMdTGmhhz_Y8AgABAAAAAILAAUAAAFQRW1QQzZ3QUFBZlEvZ0dKTjB2R3AvQUFBQUIwYzZKbzlLcFl3dnh6bzRQNFdHdEIvSE9pM1Q1UWFRUjhjNk4vWlIxZGhaaHpvNEtxMWw1QS9IT2pnc3p6YlFjUWM2T0JhVEJvQkNCem80dE5obGpFVUhPamhscXFYc09RYzZPSWs1OW94bVJ6bzRRUXJXaEVTSE9qZ2lYWFc4RWdjNk9IYSs1WUJOeHpvNFRiSTFuRFNIT2pnc2dNVzhkNGM2Tit5cWhhZ0dSem8zeWNIbGpCRUhPamhwMzRYQWdBYzZPQkw5aGNnSnh6bzR4Z2NHckRLSE9qU2dDSVhnT1VjNk4xZjU5YXd4UnpvNENSaW05QzlIT2poS1E2V01YY2M2Ti9nWmRkaGRSem80UnBnVjVHREhPamhjemJhNEhRYzZPRENsbGV3TlJ6bzM5MDQxcEEwCAAGAAAAAAgABwAAAAAMAAgKAAEc6N_dONaQNAAAAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 13,
    "returned_ids": [
      "2083163378886066305",
      "2083164066516754812",
      "2083164478925926628",
      "2083164342036639873",
      "2083161527897510145",
      "2083162965910413762",
      "2083161299828277414",
      "2083163139521077622",
      "2083164318636314817",
      "2083162451088949315",
      "2083162922981744757",
      "2083163554249920796",
      "2083164337926226351"
    ],
    "has_next_page": true,
    "next_cursor": "DAACCgACHUxpoYdAJxAKAAMdTGmhhz-x4AgABAAAAAILAAUAAAJ8RW1QQzZ3QUFBZlEvZ0dKTjB2R3AvQUFBQURrYzZKbzlLcFl3dnh6bzRnNVhtMENCSE9qakRuY1hjT1FjNkxkUGxCcEJIeHpvMzlsSFYyRm1IT2pnV2t3YUFRZ2M2T0NxdFplUVB4em80aVRuMmpHWkhPamdpWFhXOEVnYzZPRTJVcGJBUXh6b3plNUgyekZaSE9qaHAzNFhBZ0FjNk4reXFoYWdHUnpvNFZkdjExRm1IT2pocERHWFlIVWM2T0JMOWhjZ0p4em80cTV4bHVGOEhPamdtaUFiQVFRYzZOMWY1OWF3eFJ6bzMrQnZWMkVhSE9qZzVYOWJVZW9jNkxkQjZWWmgwaHpvNFNrT2xqRjNIT2poY3piYTRIUWM2T0hXbkZkaGRoem80Q255bDRGakhPamdYMkFYVVFFYzZPRCtGaHJRZnh6bzRIQUdsb0FQSE9qZ0trWWJBS1ljNk9MVFlaWXhGQnpvNExNODIwSEVIT2pobHFxWHNPUWM2T0VFSzFvUkVoem80ZHI3bGdFM0hPamhOc2pXY05JYzZPQ3lBeGJ4M2h6bzN5Y0hsakJFSE9qZndtYmFFU1FjNk4rNW85cVJ1eHpvNHhnY0dyREtIT2pTZ0NJWGdPVWM2STlQYlZzd1loem80dTJpMnNHdkhPaVVxVjdiMGZrYzZPQWtZcHZRdlJ6bzBuQngxckVVSE9qZncyZGFNRUljNk9HdU1GYmh3aHpvNHU2WDJyQ0JIT2pmNEdYWFlYVWM2T0VhWUZlUmd4em80amNzRzFFY0hPamd3cFpYc0RVYzZNL1lycHJoY0J6bzR1a2xGaERCSE9qZjNUaldrRFE9CAAGAAAAAAgABwAAAAEMAAgKAAEc6OAqRhsApgAAAA",
    "sha256": "286ca988b7a19fd25268580eae9545cd93a0ff9e08181a182564775a3b197461",
    "bytes": 66840
  }
}
```

### R17 — D8

```json
{
  "request": "R17",
  "case": "D8",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Top",
    "limit": 20,
    "cursor": "DAACCgACHUxpoYdAJxAKAAMdTGmhhz-x4AgABAAAAAILAAUAAAJ8RW1QQzZ3QUFBZlEvZ0dKTjB2R3AvQUFBQURrYzZKbzlLcFl3dnh6bzRnNVhtMENCSE9qakRuY1hjT1FjNkxkUGxCcEJIeHpvMzlsSFYyRm1IT2pnV2t3YUFRZ2M2T0NxdFplUVB4em80aVRuMmpHWkhPamdpWFhXOEVnYzZPRTJVcGJBUXh6b3plNUgyekZaSE9qaHAzNFhBZ0FjNk4reXFoYWdHUnpvNFZkdjExRm1IT2pocERHWFlIVWM2T0JMOWhjZ0p4em80cTV4bHVGOEhPamdtaUFiQVFRYzZOMWY1OWF3eFJ6bzMrQnZWMkVhSE9qZzVYOWJVZW9jNkxkQjZWWmgwaHpvNFNrT2xqRjNIT2poY3piYTRIUWM2T0hXbkZkaGRoem80Q255bDRGakhPamdYMkFYVVFFYzZPRCtGaHJRZnh6bzRIQUdsb0FQSE9qZ0trWWJBS1ljNk9MVFlaWXhGQnpvNExNODIwSEVIT2pobHFxWHNPUWM2T0VFSzFvUkVoem80ZHI3bGdFM0hPamhOc2pXY05JYzZPQ3lBeGJ4M2h6bzN5Y0hsakJFSE9qZndtYmFFU1FjNk4rNW85cVJ1eHpvNHhnY0dyREtIT2pTZ0NJWGdPVWM2STlQYlZzd1loem80dTJpMnNHdkhPaVVxVjdiMGZrYzZPQWtZcHZRdlJ6bzBuQngxckVVSE9qZncyZGFNRUljNk9HdU1GYmh3aHpvNHU2WDJyQ0JIT2pmNEdYWFlYVWM2T0VhWUZlUmd4em80amNzRzFFY0hPamd3cFpYc0RVYzZNL1lycHJoY0J6bzR1a2xGaERCSE9qZjNUaldrRFE9CAAGAAAAAAgABwAAAAEMAAgKAAEc6OAqRhsApgAAAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 6,
    "returned_ids": [
      "2083162657931301354",
      "2083161152603750851",
      "2083162986621927859",
      "2083162254686486697",
      "2083163193611059406",
      "2083162983530697109"
    ],
    "has_next_page": true,
    "next_cursor": "DAACCgACHUxpoYdAJxAKAAMdTGmhhz-K0AgABAAAAAILAAUAAAMwRW1QQzZ3QUFBZlEvZ0dKTjB2R3AvQUFBQUVvYzZKbzlLcFl3dnh6bzRnNVhtMENCSE9qakRuY1hjT1FjNklZaTFacXd3aHpvdDArVUdrRWZIT2pmMlVkWFlXWWM2T0JhVEJvQkNCem80S3ExbDVBL0hPamlKT2ZhTVprYzZPR3lTcGNSbFJ6bzRmYmMyNkdXSE9qZ2lYWFc4RWdjNk9HZEtaYkJTeHpvNFRaU2xzQkRIT2pON2tmYk1Wa2M2T0VJbUJjQXFSem80YWQrRndJQUhPamZzcW9Xb0JrYzZPRlhiOWRSWmh6bzRhUXhsMkIxSE9qZ1MvWVhJQ2NjNk5lNkZCdkFIaHpvNEFmKzF3SERIT2ppcm5HVzRYd2M2T0NhSUJzQkJCem80YUFJMTZEYUhPamRYK2ZXc01VYzZHd3ZSRnNRWFJ6bzMrQnZWMkVhSE9qZzVYOWJVZW9jNkxkQjZWWmgwaHpvNFNrT2xqRjNIT2poY3piYTRIUWM2T0hXbkZkaGRoem80VnRvR3VEakhPamdLZktYZ1dNYzZPQmZZQmRSQVJ6bzRQNFdHdEIvSE9qZ2NBYVdnQThjNk9BcVJoc0FwaHpvNFJ1S1czQ2NIT2ppMDJHV01SUWM2T0N6UE50QnhCem80WmFxbDdEa0hPamhCQ3RhRVJJYzZPSGErNVlCTnh6bzRUYkkxbkRTSE9qZ3NnTVc4ZDRjNk44bkI1WXdSQnpvMzhKbTJoRWtIT2pmdWFQYWtic2M2T01ZSEJxd3loem8wb0FpRjREbEhPaVBUMjFiTUdJYzZPTHRvdHJCcnh6b2xLbGUyOUg1SE9qaFpudGFrZW9jNk9Ba1lwdlF2UnpvMG5CeDFyRVVIT2pmdzJkYU1FSWM2T0NWMjl0d0Noem9wV1FOV3RHY0hPamhyakJXNGNJYzZPTHVsOXF3Z1J6bzMrQmwxMkYxSE9qaEdtQlhrWU1jNk9HekF0ZUJzeHpvNGpjc0cxRWNIT2pmcW9PYlFPSWM2T0RDbGxld05Sem80ZU0wV3dET0hPalAySzZhNFhBYzZPTHBKUllRd1J6bzM5MDQxcEEwCAAGAAAAAAgABwAAAAIMAAgKAAEc6OAqRhsApgAAAA",
    "sha256": "f1e8e0a8798ee323bbfdd70c9f669904ebfe060e3827d8b3e58e57958829f691",
    "bytes": 29438
  }
}
```

### R18 — D8

```json
{
  "request": "R18",
  "case": "D8",
  "method": "GET",
  "endpoint": "/twitter/tweet/advanced_search",
  "arguments": {
    "query": "(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100",
    "queryType": "Top",
    "limit": 20,
    "cursor": "DAACCgACHUxpoYdAJxAKAAMdTGmhhz-K0AgABAAAAAILAAUAAAMwRW1QQzZ3QUFBZlEvZ0dKTjB2R3AvQUFBQUVvYzZKbzlLcFl3dnh6bzRnNVhtMENCSE9qakRuY1hjT1FjNklZaTFacXd3aHpvdDArVUdrRWZIT2pmMlVkWFlXWWM2T0JhVEJvQkNCem80S3ExbDVBL0hPamlKT2ZhTVprYzZPR3lTcGNSbFJ6bzRmYmMyNkdXSE9qZ2lYWFc4RWdjNk9HZEtaYkJTeHpvNFRaU2xzQkRIT2pON2tmYk1Wa2M2T0VJbUJjQXFSem80YWQrRndJQUhPamZzcW9Xb0JrYzZPRlhiOWRSWmh6bzRhUXhsMkIxSE9qZ1MvWVhJQ2NjNk5lNkZCdkFIaHpvNEFmKzF3SERIT2ppcm5HVzRYd2M2T0NhSUJzQkJCem80YUFJMTZEYUhPamRYK2ZXc01VYzZHd3ZSRnNRWFJ6bzMrQnZWMkVhSE9qZzVYOWJVZW9jNkxkQjZWWmgwaHpvNFNrT2xqRjNIT2poY3piYTRIUWM2T0hXbkZkaGRoem80VnRvR3VEakhPamdLZktYZ1dNYzZPQmZZQmRSQVJ6bzRQNFdHdEIvSE9qZ2NBYVdnQThjNk9BcVJoc0FwaHpvNFJ1S1czQ2NIT2ppMDJHV01SUWM2T0N6UE50QnhCem80WmFxbDdEa0hPamhCQ3RhRVJJYzZPSGErNVlCTnh6bzRUYkkxbkRTSE9qZ3NnTVc4ZDRjNk44bkI1WXdSQnpvMzhKbTJoRWtIT2pmdWFQYWtic2M2T01ZSEJxd3loem8wb0FpRjREbEhPaVBUMjFiTUdJYzZPTHRvdHJCcnh6b2xLbGUyOUg1SE9qaFpudGFrZW9jNk9Ba1lwdlF2UnpvMG5CeDFyRVVIT2pmdzJkYU1FSWM2T0NWMjl0d0Noem9wV1FOV3RHY0hPamhyakJXNGNJYzZPTHVsOXF3Z1J6bzMrQmwxMkYxSE9qaEdtQlhrWU1jNk9HekF0ZUJzeHpvNGpjc0cxRWNIT2pmcW9PYlFPSWM2T0RDbGxld05Sem80ZU0wV3dET0hPalAySzZhNFhBYzZPTHBKUllRd1J6bzM5MDQxcEEwCAAGAAAAAAgABwAAAAIMAAgKAAEc6OAqRhsApgAAAA"
  },
  "time_evidence": {
    "kind": "application_run_interval_only",
    "start_utc": "2026-10-16T19:32:21.108384+00:00",
    "end_utc": "2026-10-16T19:32:29.241832+00:00"
  },
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": null,
    "sha256": "c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785",
    "bytes": 54
  }
}
```

### R19 — D9

```json
{
  "request": "R19",
  "case": "D9",
  "method": "GET",
  "endpoint": "/twitter/user/last_tweets",
  "arguments": {
    "cursor": "",
    "userId": "809230456340156416",
    "includeReplies": "true"
  },
  "issued_at_utc": "2026-10-16T19:41:35.007233+00:00",
  "response": {
    "raw_count": 15,
    "returned_ids": [
      "2110989380601229659",
      "2110989247499137380",
      "2110436014456188984",
      "2109992704008712208",
      "2109948258395009332",
      "2108753937339723900",
      "2108397174820352480",
      "2108391945890627619",
      "2108386274830934446",
      "2061617544692367704",
      "2060655363083714772",
      "1960716417268928661",
      "1152960385881972739",
      "919017900484128769",
      "810804095846072320"
    ],
    "has_next_page": true,
    "next_cursor": "DAADDAABCgABHUu9qDtbsVsKAAILQI4Hg1ZAAAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGu7F0AnEAoABh1Ma7sXP9jwCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGNtT3NpaVJ2QTFBekJBZWxNbFBBQkhVZ0t3eFFXc1RRZFM3MkpQZHJ4WkIxSnhsK2kyakE0R3pYZE1YU1hVSlVkUW40bGNKdGhyaDFEeklpSjF6QjhIVXU5cUR0YnNWc2RRb2dQU3BxeDRBdEFqZ2VEVmtBQUhVS0RUZFliQUNNZFNETXZZUnJ3RUJBQUkxekFsNkFESEp4V08rWWFBVmc9AAA",
    "sha256": "35eb9112f010e41bda3bedce2647ea6147adb2ec24f229fd8ccafc14cb77e02f",
    "bytes": 42321
  }
}
```

### R20 — D9

```json
{
  "request": "R20",
  "case": "D9",
  "method": "GET",
  "endpoint": "/twitter/user/last_tweets",
  "arguments": {
    "cursor": "DAADDAABCgABHUu9qDtbsVsKAAILQI4Hg1ZAAAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTGu7F0AnEAoABh1Ma7sXP9jwCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGNtT3NpaVJ2QTFBekJBZWxNbFBBQkhVZ0t3eFFXc1RRZFM3MkpQZHJ4WkIxSnhsK2kyakE0R3pYZE1YU1hVSlVkUW40bGNKdGhyaDFEeklpSjF6QjhIVXU5cUR0YnNWc2RRb2dQU3BxeDRBdEFqZ2VEVmtBQUhVS0RUZFliQUNNZFNETXZZUnJ3RUJBQUkxekFsNkFESEp4V08rWWFBVmc9AAA",
    "userId": "809230456340156416",
    "includeReplies": "true"
  },
  "issued_at_utc": "2026-10-16T19:43:52.299023+00:00",
  "response": {
    "raw_count": 0,
    "returned_ids": [],
    "has_next_page": false,
    "next_cursor": "DAADDAABCgABHUu9qDtbsVsKAAILQI4Hg1ZAAAAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTGu7F0AnEAoABh1Ma7sXP7HgCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGNtT3NpaVJ2QTFBekJBZWxNbFBBQkhVbkdYNkxhTURnZFM3MkpQZHJ4WkIxSUNzTVVGckUwSFVKK0pYQ2JZYTRiTmQweGRKZFFsUjFEeklpSjF6QjhIVXU5cUR0YnNWc2RRb2dQU3BxeDRCMUNnMDNXR3dBakMwQ09CNE5XUUFBZFNETXZZUnJ3RUJBQUkxekFsNkFESEp4V08rWWFBVmc9AAA",
    "sha256": "6e0b9888024a31a179d537612aef1d0c73bb35d8824b7429fabc987e3cb6a4af",
    "bytes": 481
  }
}
```

## Appendix D. Complete October 17 comparison request ledger

The following JSON Lines block contains all 261 physical requests in execution order, with complete decoded parameters, actual issue/completion timestamps, HTTP status and captured response metadata. Cursors and lookup ID lists are untruncated. `request_id` and `query_id` are local evidence labels. Each request used GET against `https://api.twitterapi.io` and the authentication/header contract in section 2. Original raw response bodies remain separately retained; this appendix includes their hashes and counts, not their full contents.

The frozen interleaving order was:

```json
[
  "2026-07-31-5m-p1",
  "2026-07-31-10m-p1",
  "2026-07-31-60m-p1",
  "2026-07-31-10m-p2",
  "2026-07-31-60m-p2",
  "2026-07-31-5m-p2",
  "2026-08-31-10m-p1",
  "2026-08-31-60m-p1",
  "2026-08-31-5m-p1",
  "2026-08-31-60m-p2",
  "2026-08-31-5m-p2",
  "2026-08-31-10m-p2",
  "2026-09-30-60m-p1",
  "2026-09-30-5m-p1",
  "2026-09-30-10m-p1",
  "2026-09-30-5m-p2",
  "2026-09-30-10m-p2",
  "2026-09-30-60m-p2"
]
```

```jsonl
{"request_id":"request-0001","query_id":"2026-07-31-5m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:35.702486+00:00","completed_at_utc":"2026-10-17T03:45:36.826390+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499500","queryType":"Latest","limit":20},"raw_count":14,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjgwpZXsDUKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqDD8AnEAoABh1M2oMPv9jwCwAHAAAAsEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBNGM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzRBZisxd0hESE9qZ21pQWJBUVFjNk9BcVJoc0FwaHpvMzlsSFYyRm1IT2pnSkdLYjBMMGM2T0JhVEJvQkNCem80TE04MjBIRUhPamY0R1hYWVhVYzZPRENsbGV3TlJ6bzM3S3FGcUFaAAA"},"http_status":200,"sha256":"794d3e0a44c8814e0160441b38b2833e7dbcc704f61042f63100ac1ba8642895","response_bytes":54008}
{"request_id":"request-0002","query_id":"2026-07-31-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:36.827382+00:00","completed_at_utc":"2026-10-17T03:45:38.956103+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6OCzPNtBxAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqE2cAnEAoABh1M2oTZv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRMTTgyMEhFSE9qaEc0cGJjSndjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pnd3BaWHNEVWM2T0VhWUZlUmd4em80UVFyV2hFU0hPamhzd0xYZ2JNYzZPRTJVcGJBUXh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9HeVNwY1JsUnpvNFZ0b0d1RGpIT2poblNtV3dVc2M2T0ZYYjlkUlpoem80ZU0wV3dETwAA"},"http_status":200,"sha256":"fa17bc0e40d494cb7c699d4638c31d438d93ff4cac1bb74efc1021da3cb4d28b","response_bytes":89199}
{"request_id":"request-0003","query_id":"2026-07-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:38.956423+00:00","completed_at_utc":"2026-10-17T03:45:40.500158+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OVeP9ZwBAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqGasAnEAoABh1M2oZqv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPam8yVWVXNFgwYzZPbFkvOXJ4Y3h6bzY0ZGFsc0RsSE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNk9DYzI5Q3dIT2pvV1FPWHdFNGM2T2pyMkJ1eEdCem82ampabGxIaEhPanFyYTFXNElJYzZPVmVQOVp3QkJ6bzZPT2ltOUdjSE9qci9RamE0SjhjNk9aY2pSY2dqeHpvNlNCTGx2RTBIT2p0UE9yYVlLc2M2T3VLTVpyQVRoem81cEI2V2lGVQAA"},"http_status":200,"sha256":"edb90926a8fac8ab7b8ab9cb897645f2f7d4a39bfe162534d5a22d4c1bf9cc44","response_bytes":126824}
{"request_id":"request-0004","query_id":"2026-07-31-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:40.500882+00:00","completed_at_utc":"2026-10-17T03:45:42.090520+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6OCzPNtBxAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqH7cAnEAoABh1M2oftv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRMTTgyMEhFSE9qaEc0cGJjSndjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pnd3BaWHNEVWM2T0VhWUZlUmd4em80UVFyV2hFU0hPamhzd0xYZ2JNYzZPRTJVcGJBUXh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9HeVNwY1JsUnpvNFZ0b0d1RGpIT2poblNtV3dVc2M2T0ZYYjlkUlpoem80ZU0wV3dETwAA"},"http_status":200,"sha256":"6dbb03c7af988db9748d3594c5ec1d944d10c56dc42e101ce92f994a2736c6f1","response_bytes":89199}
{"request_id":"request-0005","query_id":"2026-07-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:42.091391+00:00","completed_at_utc":"2026-10-17T03:45:43.431499+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OVeP9ZwBAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqJTMAnEAoABh1M2olMv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPam8yVWVXNFgwYzZPbFkvOXJ4Y3h6bzY0ZGFsc0RsSE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNk9DYzI5Q3dIT2pvV1FPWHdFNGM2T2pyMkJ1eEdCem82ampabGxIaEhPanFyYTFXNElJYzZPVmVQOVp3QkJ6bzZPT2ltOUdjSE9qci9RamE0SjhjNk9aY2pSY2dqeHpvNlNCTGx2RTBIT2p0UE9yYVlLc2M2T3VLTVpyQVRoem81cEI2V2lGVQAA"},"http_status":200,"sha256":"e853f3bc7451b756e797fd47951989c26d904b867b606613473ea83bdf8b0c05","response_bytes":126824}
{"request_id":"request-0006","query_id":"2026-07-31-5m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:43.432240+00:00","completed_at_utc":"2026-10-17T03:45:44.979582+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499500","queryType":"Latest","limit":20},"raw_count":14,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjgwpZXsDUKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqKzEAnEAoABh1M2orMP9jwCwAHAAAAsEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBNGM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzRBZisxd0hESE9qZ21pQWJBUVFjNk9BcVJoc0FwaHpvMzlsSFYyRm1IT2pnSkdLYjBMMGM2T0JhVEJvQkNCem80TE04MjBIRUhPamY0R1hYWVhVYzZPRENsbGV3TlJ6bzM3S3FGcUFaAAA"},"http_status":200,"sha256":"da15ccce2287635ab28c585afd80c1f16475e77c117002356036e6ed3bc6242a","response_bytes":54008}
{"request_id":"request-0007","query_id":"2026-08-31-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:44.980823+00:00","completed_at_utc":"2026-10-17T03:45:46.377187+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788178200","queryType":"Latest","limit":20},"raw_count":11,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqMOwAnEAoABh1M2ow6_9jwCwAHAAAAkEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBc2RFTXBJb3B1aFFSMFF5WkQxV3pBbEhSREtUd2Jid09RZEVNbWo0eGVCZ3gwUXlXZXhXakdLSFJESkhzZ1hNVElkRU1wejhac3g3QjBReVZvdWx6QWFIUkRKWFgyWGdDc2RFTW5DWEZhUkZ4MFF5UXVsRjNGRgAA"},"http_status":200,"sha256":"018688e5a956348aefba671e86fe4742951264ac1da3cde901418e386deaa74a","response_bytes":62657}
{"request_id":"request-0008","query_id":"2026-08-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:46.378193+00:00","completed_at_utc":"2026-10-17T03:45:48.319207+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEM-_E1dg5QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqN3sAnEAoABh1M2o3ev9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWRFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOVGpLWmVoUFIwUTBrVWUxeUJESFJEVE8vcVdJWThkRU5UdlJGZGhQQjBRMVp5WEdnRDlIUkRSOUljWGdic2RFTkd0alplQjJSMFEwKytYVjJBZEhSRFRiR25iTVBrZEVORWV6VllnNFIwUTBwaTgxckhGSFJEV1ljRVdJZEFkRU5CcUhwYUF0aDBRMGxjejJ6R1ZIUkRTUkNOYVlPQWRFTS8zVEJaUnVSMFF6NzhUVjJEbAAA"},"http_status":200,"sha256":"9b2c119d769f9621ab13c502e3d2e6b9f05692ea83776bcd5cb7f1da67132901","response_bytes":102085}
{"request_id":"request-0009","query_id":"2026-08-31-5m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:48.319873+00:00","completed_at_utc":"2026-10-17T03:45:49.609302+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788177900","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDJwlxWkRcKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqPe0AnEAoABh1M2o97P9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTW1ROVZzd0pSMFF5YVBqRjRHREhSREpaN0ZhTVlvZEVNa2V5QmN4TWgwUXlWb3VsekFhSFJESlhYMlhnQ3NkRU1uQ1hGYVJGeDBReVF1bEYzRkYAAA"},"http_status":200,"sha256":"ea9ab5a0a0d70bdad2d9db71a81934dc12ee4adfa64a062a27ccf8ec75bb7ac0","response_bytes":49836}
{"request_id":"request-0010","query_id":"2026-08-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:49.610410+00:00","completed_at_utc":"2026-10-17T03:45:50.919984+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEM-_E1dg5QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqQroAnEAoABh1M2pCuf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWRFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOVGpLWmVoUFIwUTBrVWUxeUJESFJEVE8vcVdJWThkRU5UdlJGZGhQQjBRMVp5WEdnRDlIUkRSOUljWGdic2RFTkd0alplQjJSMFEwKytYVjJBZEhSRFRiR25iTVBrZEVORWV6VllnNFIwUTBwaTgxckhGSFJEV1ljRVdJZEFkRU5CcUhwYUF0aDBRMGxjejJ6R1ZIUkRTUkNOYVlPQWRFTS8zVEJaUnVSMFF6NzhUVjJEbAAA"},"http_status":200,"sha256":"8c66ac22cc4d947073a9b0d87ca33d6f7cbf28191aa8cab2874ee5ff32913a36","response_bytes":102125}
{"request_id":"request-0011","query_id":"2026-08-31-5m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:50.921020+00:00","completed_at_utc":"2026-10-17T03:45:51.913324+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788177900","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDJwlxWkRcKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqRuQAnEAoABh1M2pG4_9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTW1ROVZzd0pSMFF5YVBqRjRHREhSREpaN0ZhTVlvZEVNa2V5QmN4TWgwUXlWb3VsekFhSFJESlhYMlhnQ3NkRU1uQ1hGYVJGeDBReVF1bEYzRkYAAA"},"http_status":200,"sha256":"3580efec8ca8d66739c75fd92a316e06e29402cf5b3344f3fba3d290d64489b3","response_bytes":49836}
{"request_id":"request-0012","query_id":"2026-08-31-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:51.917133+00:00","completed_at_utc":"2026-10-17T03:45:53.492320+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788178200","queryType":"Latest","limit":20},"raw_count":11,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqTDAAnEAoABh1M2pML_9jwCwAHAAAAkEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBc2RFTXBJb3B1aFFSMFF5WkQxV3pBbEhSREtUd2Jid09RZEVNbWo0eGVCZ3gwUXlXZXhXakdLSFJESkhzZ1hNVElkRU1wejhac3g3QjBReVZvdWx6QWFIUkRKWFgyWGdDc2RFTW5DWEZhUkZ4MFF5UXVsRjNGRgAA"},"http_status":200,"sha256":"642e16e055767b373d29f2d1705dd5fc2ee0922b432ce8416e28f71924e35fd0","response_bytes":62647}
{"request_id":"request-0013","query_id":"2026-09-30-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:53.493203+00:00","completed_at_utc":"2026-10-17T03:45:54.874521+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790773200","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2jXN5ZweAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqUdEAnEAoABh1M2pR0P9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjI4VW9CcFJteDAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROM0lITk51QXNCMDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkbzF6ZVdjSGdkTjJsWVgxWVF6eDAzYWhJSldvRkZIVGQwT1lBYmNlb2ROM0wwSkZjQlVoMDNkaWtEbXVIcgAA"},"http_status":200,"sha256":"758ffeac706ec0a673108492b3004716840ec4864194fce415b6225e5ef46d80","response_bytes":101372}
{"request_id":"request-0014","query_id":"2026-09-30-5m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:54.875412+00:00","completed_at_utc":"2026-10-17T03:45:55.705145+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790769900","queryType":"Latest","limit":20},"raw_count":6,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdpw6lbcU8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqVrsAnEAoABh1M2pWuv9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMmxIb3hhZ01SMDNhTmMzbG5CNEhUZHBXRjlXRU04ZE4ybkRxVnR4VHgwM2FQanNHaUY4SFRkb3JRMFc4TFE9AAA"},"http_status":200,"sha256":"3b0b0b0d63c2b734d69fd6249a8c36aee97f1aaa29e4ac968b7c15447f777764","response_bytes":33440}
{"request_id":"request-0015","query_id":"2026-09-30-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:55.706201+00:00","completed_at_utc":"2026-10-17T03:45:57.262255+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790770200","queryType":"Latest","limit":20},"raw_count":15,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqWuMAnEAoABh1M2pa4v9jwCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYVVlakZxQXhIVGRvMXplV2NIZ2ROMmxZWDFZUXp4MDNhY09wVzNGUEhUZG9yUTBXOExRZE4yajQ3Qm9oZkIwM2FoSUpXb0ZGSFRkcVZHV2JNYW89AAA"},"http_status":200,"sha256":"5a2cadd9a86591a4d277d3ab2f5fabb2110b4b4bd7bb623bef543c72ca42411e","response_bytes":62351}
{"request_id":"request-0016","query_id":"2026-09-30-5m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:57.263155+00:00","completed_at_utc":"2026-10-17T03:45:58.402284+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790769900","queryType":"Latest","limit":20},"raw_count":6,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdpw6lbcU8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqYOMAnEAoABh1M2pg4v9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMmxIb3hhZ01SMDNhTmMzbG5CNEhUZHBXRjlXRU04ZE4ybkRxVnR4VHgwM2FQanNHaUY4SFRkb3JRMFc4TFE9AAA"},"http_status":200,"sha256":"7c6514a4c81da4e60aabf541941446c959cf90870c7b52fe55765d70a589184f","response_bytes":33412}
{"request_id":"request-0017","query_id":"2026-09-30-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:58.404334+00:00","completed_at_utc":"2026-10-17T03:45:59.846984+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790770200","queryType":"Latest","limit":20},"raw_count":15,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqZVgAnEAoABh1M2plV_9jwCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYVVlakZxQXhIVGRvMXplV2NIZ2ROMmxZWDFZUXp4MDNhY09wVzNGUEhUZG9yUTBXOExRZE4yajQ3Qm9oZkIwM2FoSUpXb0ZGSFRkcVZHV2JNYW89AAA"},"http_status":200,"sha256":"2158ee1bbd2ec3c6fb6b03932644271c7bd7af1985d7e1df70cec0c6df2c4612","response_bytes":62351}
{"request_id":"request-0018","query_id":"2026-09-30-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:45:59.847847+00:00","completed_at_utc":"2026-10-17T03:46:01.537245+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790773200","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2jXN5ZweAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqawMAnEAoABh1M2prAv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjI4VW9CcFJteDAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROM0lITk51QXNCMDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkbzF6ZVdjSGdkTjJsWVgxWVF6eDAzYWhJSldvRkZIVGQwT1lBYmNlb2ROM0wwSkZjQlVoMDNkaWtEbXVIcgAA"},"http_status":200,"sha256":"3ca7843e88aa8ed8fe00a9cab51decaf75b0bcf24cde54a9b9c212d465912608","response_bytes":101352}
{"request_id":"request-0019","query_id":"2026-07-31-5m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:01.538808+00:00","completed_at_utc":"2026-10-17T03:46:02.014032+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjgwpZXsDUKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqDD8AnEAoABh1M2oMPv9jwCwAHAAAAsEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBNGM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzRBZisxd0hESE9qZ21pQWJBUVFjNk9BcVJoc0FwaHpvMzlsSFYyRm1IT2pnSkdLYjBMMGM2T0JhVEJvQkNCem80TE04MjBIRUhPamY0R1hYWVhVYzZPRENsbGV3TlJ6bzM3S3FGcUFaAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0020","query_id":"2026-07-31-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:02.016940+00:00","completed_at_utc":"2026-10-17T03:46:02.777578+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6OCzPNtBxAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqE2cAnEAoABh1M2oTZv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRMTTgyMEhFSE9qaEc0cGJjSndjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pnd3BaWHNEVWM2T0VhWUZlUmd4em80UVFyV2hFU0hPamhzd0xYZ2JNYzZPRTJVcGJBUXh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9HeVNwY1JsUnpvNFZ0b0d1RGpIT2poblNtV3dVc2M2T0ZYYjlkUlpoem80ZU0wV3dETwAA"},"raw_count":12,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqE2cAnEAoABh1M2oTZv7HgCwAHAAABcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDQWM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamcvaFlhMEg4YzZPQXFSaHNBcGh6bzM5bEhWMkZtSE9qZ3N6emJRY1FjNk9FYmlsdHduQnpvNEZwTUdnRUlIT2poQkN0YUVSSWM2T0UyVXBiQVF4em80ZHI3bGdFM0hPamhOc2pXY05JYzZPR3lTcGNSbFJ6bzRaMHBsc0ZMSE9qZnNxb1dvQmtjNk9GWGI5ZFJaaHpvMzhKbTJoRWtIT2pmdWFQYWtic2M2T0FIL3RjQnd4em80Sm9nR3dFRUhPamhvQWpYb05vYzZPRm1lMXFSNmh6bzRPVi9XMUhxSE9qZ0pHS2IwTDBjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pmNEdYWFlYVWM2T0VhWUZlUmd4em80Yk1DMTRHekhPamd3cFpYc0RVYzZPRmJhQnJnNHh6bzRlTTBXd0RPAAA"},"http_status":200,"sha256":"15e0e52ca0c340a54a729a622c6bd7f6525d0f28648961d804b4dd9b7aeccbb0","response_bytes":48044}
{"request_id":"request-0021","query_id":"2026-07-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:02.778466+00:00","completed_at_utc":"2026-10-17T03:46:04.313200+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OVeP9ZwBAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqGasAnEAoABh1M2oZqv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPam8yVWVXNFgwYzZPbFkvOXJ4Y3h6bzY0ZGFsc0RsSE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNk9DYzI5Q3dIT2pvV1FPWHdFNGM2T2pyMkJ1eEdCem82ampabGxIaEhPanFyYTFXNElJYzZPVmVQOVp3QkJ6bzZPT2ltOUdjSE9qci9RamE0SjhjNk9aY2pSY2dqeHpvNlNCTGx2RTBIT2p0UE9yYVlLc2M2T3VLTVpyQVRoem81cEI2V2lGVQAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OLpJRYQwQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqGasAnEAoABh1M2oZqv7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T1ZNUWRaeHZCem83S056bG9IVkhPampEbmNYY09RYzZPU2EyWmVBYWh6bzZWai8ydkZ6SE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNDU0ZW1wRnFIT2pqREM0WGtMTWM2T1FrM05heDR4em82cTJ0VnVDQ0hPamxYai9XY0FRYzZPdjlDTnJnbnh6bzVVSVlGbURBSE9qbVhJMFhJSThjNk8wODZ0cGdxeHpvNjRveG1zQk9IT2prbDliYWNhWWM2T09pc1JkeGh4em83TFcyMXZIQkhPampHQndhc01vYzZPalpSNWJoZlJ6bzQ0MFRGbkNJSE9qcmgxcVd3T1VjNk9qZ25OdlFzQnpvNkZrRGw4Qk9IT2preXVYWE1POGM2T09aSzVxeGh4em82T3ZZRzdFWUhPanFPTm1XVWVFYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qbFNUelhFS1VjNk9qam9wdlJuQnpvNDFSa1YwRk5IT2pwSUV1VzhUUWM2T0xwSlJZUXdSem80N3dGbXBFNUhPam1rSHBhSVZRYzZPU2hZMXB3eFE9PQAA"},"http_status":200,"sha256":"88ebfdff798ac1b4b21713fdcf456d87f323e70e118bb8a8c6f6b85c0d490650","response_bytes":115343}
{"request_id":"request-0022","query_id":"2026-07-31-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:04.313974+00:00","completed_at_utc":"2026-10-17T03:46:05.927478+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6OCzPNtBxAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqH7cAnEAoABh1M2oftv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRMTTgyMEhFSE9qaEc0cGJjSndjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pnd3BaWHNEVWM2T0VhWUZlUmd4em80UVFyV2hFU0hPamhzd0xYZ2JNYzZPRTJVcGJBUXh6bzRkcjdsZ0UzSE9qaE5zaldjTkljNk9HeVNwY1JsUnpvNFZ0b0d1RGpIT2poblNtV3dVc2M2T0ZYYjlkUlpoem80ZU0wV3dETwAA"},"raw_count":12,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqH7cAnEAoABh1M2oftv7HgCwAHAAABcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDQWM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamcvaFlhMEg4YzZPQXFSaHNBcGh6bzM5bEhWMkZtSE9qZ3N6emJRY1FjNk9FYmlsdHduQnpvNEZwTUdnRUlIT2poQkN0YUVSSWM2T0UyVXBiQVF4em80ZHI3bGdFM0hPamhOc2pXY05JYzZPR3lTcGNSbFJ6bzRaMHBsc0ZMSE9qZnNxb1dvQmtjNk9GWGI5ZFJaaHpvMzhKbTJoRWtIT2pmdWFQYWtic2M2T0FIL3RjQnd4em80Sm9nR3dFRUhPamhvQWpYb05vYzZPRm1lMXFSNmh6bzRPVi9XMUhxSE9qZ0pHS2IwTDBjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pmNEdYWFlYVWM2T0VhWUZlUmd4em80Yk1DMTRHekhPamd3cFpYc0RVYzZPRmJhQnJnNHh6bzRlTTBXd0RPAAA"},"http_status":200,"sha256":"fd35414dd0221d68dc9b24c609167f5bfe175aab3bb50b8156773e7dd6334424","response_bytes":48044}
{"request_id":"request-0023","query_id":"2026-07-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:05.928180+00:00","completed_at_utc":"2026-10-17T03:46:07.298016+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OVeP9ZwBAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqJTMAnEAoABh1M2olMv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPam8yVWVXNFgwYzZPbFkvOXJ4Y3h6bzY0ZGFsc0RsSE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNk9DYzI5Q3dIT2pvV1FPWHdFNGM2T2pyMkJ1eEdCem82ampabGxIaEhPanFyYTFXNElJYzZPVmVQOVp3QkJ6bzZPT2ltOUdjSE9qci9RamE0SjhjNk9aY2pSY2dqeHpvNlNCTGx2RTBIT2p0UE9yYVlLc2M2T3VLTVpyQVRoem81cEI2V2lGVQAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OLpJRYQwQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqJTMAnEAoABh1M2olMv7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T1ZNUWRaeHZCem83S056bG9IVkhPampEbmNYY09RYzZPU2EyWmVBYWh6bzZWai8ydkZ6SE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNDU0ZW1wRnFIT2pqREM0WGtMTWM2T1FrM05heDR4em82cTJ0VnVDQ0hPamxYai9XY0FRYzZPdjlDTnJnbnh6bzVVSVlGbURBSE9qbVhJMFhJSThjNk8wODZ0cGdxeHpvNjRveG1zQk9IT2prbDliYWNhWWM2T09pc1JkeGh4em83TFcyMXZIQkhPampHQndhc01vYzZPalpSNWJoZlJ6bzQ0MFRGbkNJSE9qcmgxcVd3T1VjNk9qZ25OdlFzQnpvNkZrRGw4Qk9IT2preXVYWE1POGM2T09aSzVxeGh4em82T3ZZRzdFWUhPanFPTm1XVWVFYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qbFNUelhFS1VjNk9qam9wdlJuQnpvNDFSa1YwRk5IT2pwSUV1VzhUUWM2T0xwSlJZUXdSem80N3dGbXBFNUhPam1rSHBhSVZRYzZPU2hZMXB3eFE9PQAA"},"http_status":200,"sha256":"a6b8dee14b5392c625e681a9654007abf7edf7da8986e2cd783d516b605f3bc9","response_bytes":115343}
{"request_id":"request-0024","query_id":"2026-07-31-5m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:07.298988+00:00","completed_at_utc":"2026-10-17T03:46:07.693089+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjgwpZXsDUKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqKzEAnEAoABh1M2orMP9jwCwAHAAAAsEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBNGM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzRBZisxd0hESE9qZ21pQWJBUVFjNk9BcVJoc0FwaHpvMzlsSFYyRm1IT2pnSkdLYjBMMGM2T0JhVEJvQkNCem80TE04MjBIRUhPamY0R1hYWVhVYzZPRENsbGV3TlJ6bzM3S3FGcUFaAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0025","query_id":"2026-08-31-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:07.695542+00:00","completed_at_utc":"2026-10-17T03:46:08.304929+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788178200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqMOwAnEAoABh1M2ow6_9jwCwAHAAAAkEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBc2RFTXBJb3B1aFFSMFF5WkQxV3pBbEhSREtUd2Jid09RZEVNbWo0eGVCZ3gwUXlXZXhXakdLSFJESkhzZ1hNVElkRU1wejhac3g3QjBReVZvdWx6QWFIUkRKWFgyWGdDc2RFTW5DWEZhUkZ4MFF5UXVsRjNGRgAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0026","query_id":"2026-08-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:08.306173+00:00","completed_at_utc":"2026-10-17T03:46:10.160435+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEM-_E1dg5QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqN3sAnEAoABh1M2o3ev9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWRFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOVGpLWmVoUFIwUTBrVWUxeUJESFJEVE8vcVdJWThkRU5UdlJGZGhQQjBRMVp5WEdnRDlIUkRSOUljWGdic2RFTkd0alplQjJSMFEwKytYVjJBZEhSRFRiR25iTVBrZEVORWV6VllnNFIwUTBwaTgxckhGSFJEV1ljRVdJZEFkRU5CcUhwYUF0aDBRMGxjejJ6R1ZIUkRTUkNOYVlPQWRFTS8zVEJaUnVSMFF6NzhUVjJEbAAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMmQ9VswJQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqN3sAnEAoABh1M2o3ev7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2RFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJES1R3YmJ3T1FkRU5UaktaZWhQUjBReWFQakY0R0RIUkRTUlI3WElFTWRFTlR2UkZkaFBCMFF5Nm5DVnFIK0hSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUTAyeHAyekQ1SFJETW1ldFdnYThkRU5FZXpWWWc0UjBRMHBpODFySEZIUkRXWWNFV0lkQWRFTkJxSHBhQXRoMFF5M3JQV3ZHV0hSRE5YUGpXd1VrZEVNKy9FMWRnNVIwUXp3eEUyc0dNSFJEUDQ1VmE4YklkRU11YXN0YlJNUjBReW5QeG16SHNIUkRUTy9xV0lZOGRFTldjbHhvQS9SMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVOUHZsMWRnSFIwUXozYUFWdUUvSFJESndseFdrUmNkRU16eDFwcmhmQjBRekRvNm1xQk5IUkRTVnpQYk1aVWRFTkpFSTFwZzRCMFF6L2RNRmxHNUhSRE4rTE5hOEpRZEVNbVE5VnN3SlE9PQAA"},"http_status":200,"sha256":"b94bc63f77e884b393f19730fa2b23fd5f90588f9e2e2209514b0a2a7b646b6f","response_bytes":105770}
{"request_id":"request-0027","query_id":"2026-08-31-5m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:10.161411+00:00","completed_at_utc":"2026-10-17T03:46:10.787485+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788177900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDJwlxWkRcKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqPe0AnEAoABh1M2o97P9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTW1ROVZzd0pSMFF5YVBqRjRHREhSREpaN0ZhTVlvZEVNa2V5QmN4TWgwUXlWb3VsekFhSFJESlhYMlhnQ3NkRU1uQ1hGYVJGeDBReVF1bEYzRkYAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0028","query_id":"2026-08-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:10.790465+00:00","completed_at_utc":"2026-10-17T03:46:12.090887+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEM-_E1dg5QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqQroAnEAoABh1M2pCuf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWRFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOVGpLWmVoUFIwUTBrVWUxeUJESFJEVE8vcVdJWThkRU5UdlJGZGhQQjBRMVp5WEdnRDlIUkRSOUljWGdic2RFTkd0alplQjJSMFEwKytYVjJBZEhSRFRiR25iTVBrZEVORWV6VllnNFIwUTBwaTgxckhGSFJEV1ljRVdJZEFkRU5CcUhwYUF0aDBRMGxjejJ6R1ZIUkRTUkNOYVlPQWRFTS8zVEJaUnVSMFF6NzhUVjJEbAAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMmQ9VswJQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqQroAnEAoABh1M2pCuf7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2RFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJES1R3YmJ3T1FkRU5UaktaZWhQUjBReWFQakY0R0RIUkRTUlI3WElFTWRFTlR2UkZkaFBCMFF5Nm5DVnFIK0hSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUTAyeHAyekQ1SFJETW1ldFdnYThkRU5FZXpWWWc0UjBRMHBpODFySEZIUkRXWWNFV0lkQWRFTkJxSHBhQXRoMFF5M3JQV3ZHV0hSRE5YUGpXd1VrZEVNKy9FMWRnNVIwUXp3eEUyc0dNSFJEUDQ1VmE4YklkRU11YXN0YlJNUjBReW5QeG16SHNIUkRUTy9xV0lZOGRFTldjbHhvQS9SMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVOUHZsMWRnSFIwUXozYUFWdUUvSFJESndseFdrUmNkRU16eDFwcmhmQjBRekRvNm1xQk5IUkRTVnpQYk1aVWRFTkpFSTFwZzRCMFF6L2RNRmxHNUhSRE4rTE5hOEpRZEVNbVE5VnN3SlE9PQAA"},"http_status":200,"sha256":"f878ed8f10da857ddd324305b1158b0df26538f85f24be968e703b0988ad30f3","response_bytes":105788}
{"request_id":"request-0029","query_id":"2026-08-31-5m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:12.091475+00:00","completed_at_utc":"2026-10-17T03:46:12.436219+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788177900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDJwlxWkRcKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqRuQAnEAoABh1M2pG4_9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTW1ROVZzd0pSMFF5YVBqRjRHREhSREpaN0ZhTVlvZEVNa2V5QmN4TWgwUXlWb3VsekFhSFJESlhYMlhnQ3NkRU1uQ1hGYVJGeDBReVF1bEYzRkYAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0030","query_id":"2026-08-31-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:12.438957+00:00","completed_at_utc":"2026-10-17T03:46:12.874440+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788178200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqTDAAnEAoABh1M2pML_9jwCwAHAAAAkEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBc2RFTXBJb3B1aFFSMFF5WkQxV3pBbEhSREtUd2Jid09RZEVNbWo0eGVCZ3gwUXlXZXhXakdLSFJESkhzZ1hNVElkRU1wejhac3g3QjBReVZvdWx6QWFIUkRKWFgyWGdDc2RFTW5DWEZhUkZ4MFF5UXVsRjNGRgAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0031","query_id":"2026-09-30-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:12.876155+00:00","completed_at_utc":"2026-10-17T03:46:13.498015+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2jXN5ZweAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqUdEAnEAoABh1M2pR0P9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjI4VW9CcFJteDAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROM0lITk51QXNCMDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkbzF6ZVdjSGdkTjJsWVgxWVF6eDAzYWhJSldvRkZIVGQwT1lBYmNlb2ROM0wwSkZjQlVoMDNkaWtEbXVIcgAA"},"raw_count":1,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqUdEAnEAoABh1M2pR0P7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjNJSE5OdUFzQjAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROMjhVb0JwUm14MDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkcFdGOVdFTThkTjJqWE41WndlQjAzYUswTkZ2QzBIVGQwT1lBYmNlb2ROMm9TQ1ZxQlJSMDNjdlFrVndGU0hUZDJLUU9hNGVzPQAA"},"http_status":200,"sha256":"23b59419172e35f21e90a59349f908e945a1498271d9e6bd430e3bb02c0f5a5a","response_bytes":4657}
{"request_id":"request-0032","query_id":"2026-09-30-5m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:13.499656+00:00","completed_at_utc":"2026-10-17T03:46:14.451164+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790769900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdpw6lbcU8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqVrsAnEAoABh1M2pWuv9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMmxIb3hhZ01SMDNhTmMzbG5CNEhUZHBXRjlXRU04ZE4ybkRxVnR4VHgwM2FQanNHaUY4SFRkb3JRMFc4TFE9AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0033","query_id":"2026-09-30-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:14.452807+00:00","completed_at_utc":"2026-10-17T03:46:15.058293+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790770200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqWuMAnEAoABh1M2pa4v9jwCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYVVlakZxQXhIVGRvMXplV2NIZ2ROMmxZWDFZUXp4MDNhY09wVzNGUEhUZG9yUTBXOExRZE4yajQ3Qm9oZkIwM2FoSUpXb0ZGSFRkcVZHV2JNYW89AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0034","query_id":"2026-09-30-5m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:15.059221+00:00","completed_at_utc":"2026-10-17T03:46:15.734902+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790769900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdpw6lbcU8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqYOMAnEAoABh1M2pg4v9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMmxIb3hhZ01SMDNhTmMzbG5CNEhUZHBXRjlXRU04ZE4ybkRxVnR4VHgwM2FQanNHaUY4SFRkb3JRMFc4TFE9AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0035","query_id":"2026-09-30-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:15.736512+00:00","completed_at_utc":"2026-10-17T03:46:16.435925+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790770200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqZVgAnEAoABh1M2plV_9jwCwAHAAAAvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBOGROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYVVlakZxQXhIVGRvMXplV2NIZ2ROMmxZWDFZUXp4MDNhY09wVzNGUEhUZG9yUTBXOExRZE4yajQ3Qm9oZkIwM2FoSUpXb0ZGSFRkcVZHV2JNYW89AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0036","query_id":"2026-09-30-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:16.437758+00:00","completed_at_utc":"2026-10-17T03:46:17.291969+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2jXN5ZweAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqawMAnEAoABh1M2prAv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjI4VW9CcFJteDAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROM0lITk51QXNCMDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkbzF6ZVdjSGdkTjJsWVgxWVF6eDAzYWhJSldvRkZIVGQwT1lBYmNlb2ROM0wwSkZjQlVoMDNkaWtEbXVIcgAA"},"raw_count":1,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqawMAnEAoABh1M2prAv7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjNJSE5OdUFzQjAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROMjhVb0JwUm14MDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkcFdGOVdFTThkTjJqWE41WndlQjAzYUswTkZ2QzBIVGQwT1lBYmNlb2ROMm9TQ1ZxQlJSMDNjdlFrVndGU0hUZDJLUU9hNGVzPQAA"},"http_status":200,"sha256":"46a27b2783bb6deaa4b0c41b799837248f26efc079f19326d3780ecd2bd80ca5","response_bytes":4647}
{"request_id":"request-0037","query_id":"2026-07-31-5m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:17.294409+00:00","completed_at_utc":"2026-10-17T03:46:18.501406+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499500 until_time:1785499800","queryType":"Latest","limit":20},"raw_count":19,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6ODlf1tR6gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqruQAnEAoABh1M2qu4_9jwCwAHAAAA6EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCTWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRSdUtXM0NjSE9qaEtRNldNWGNjNk9HdU1GYmh3aHpvNFFRcldoRVNIT2poR21CWGtZTWM2T0VJbUJjQXFSem80Yk1DMTRHekhPamhObEtXd0VNYzZPSGErNVlCTnh6bzRUYkkxbkRTSE9qaHNrcVhFWlVjNk9GYmFCcmc0eHpvNFowcGxzRkxIT2poVjIvWFVXWWM2T0hqTkZzQXpnPT0AAA"},"http_status":200,"sha256":"e4433bc82836ce190ee1623bb1417dbd9f717c22a695e08b2ccda7ffac8dfcd6","response_bytes":87316}
{"request_id":"request-0038","query_id":"2026-07-31-10m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:18.502113+00:00","completed_at_utc":"2026-10-17T03:46:19.394442+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqE2cAnEAoABh1M2oTZv7HgCwAHAAABcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDQWM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamcvaFlhMEg4YzZPQXFSaHNBcGh6bzM5bEhWMkZtSE9qZ3N6emJRY1FjNk9FYmlsdHduQnpvNEZwTUdnRUlIT2poQkN0YUVSSWM2T0UyVXBiQVF4em80ZHI3bGdFM0hPamhOc2pXY05JYzZPR3lTcGNSbFJ6bzRaMHBsc0ZMSE9qZnNxb1dvQmtjNk9GWGI5ZFJaaHpvMzhKbTJoRWtIT2pmdWFQYWtic2M2T0FIL3RjQnd4em80Sm9nR3dFRUhPamhvQWpYb05vYzZPRm1lMXFSNmh6bzRPVi9XMUhxSE9qZ0pHS2IwTDBjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pmNEdYWFlYVWM2T0VhWUZlUmd4em80Yk1DMTRHekhPamd3cFpYc0RVYzZPRmJhQnJnNHh6bzRlTTBXd0RPAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0039","query_id":"2026-07-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:19.396905+00:00","completed_at_utc":"2026-10-17T03:46:21.090388+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OLpJRYQwQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqGasAnEAoABh1M2oZqv7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T1ZNUWRaeHZCem83S056bG9IVkhPampEbmNYY09RYzZPU2EyWmVBYWh6bzZWai8ydkZ6SE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNDU0ZW1wRnFIT2pqREM0WGtMTWM2T1FrM05heDR4em82cTJ0VnVDQ0hPamxYai9XY0FRYzZPdjlDTnJnbnh6bzVVSVlGbURBSE9qbVhJMFhJSThjNk8wODZ0cGdxeHpvNjRveG1zQk9IT2prbDliYWNhWWM2T09pc1JkeGh4em83TFcyMXZIQkhPampHQndhc01vYzZPalpSNWJoZlJ6bzQ0MFRGbkNJSE9qcmgxcVd3T1VjNk9qZ25OdlFzQnpvNkZrRGw4Qk9IT2preXVYWE1POGM2T09aSzVxeGh4em82T3ZZRzdFWUhPanFPTm1XVWVFYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qbFNUelhFS1VjNk9qam9wdlJuQnpvNDFSa1YwRk5IT2pwSUV1VzhUUWM2T0xwSlJZUXdSem80N3dGbXBFNUhPam1rSHBhSVZRYzZPU2hZMXB3eFE9PQAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OEpDpYxdwAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqGasAnEAoABh1M2oZqv4rQCwAHAAACnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFEd2M2T0lPVjV0QWdSem81VXhCMW5HOEhPampEbmNYY09RYzZPeXNXUnBSY1J6bzZWai8ydkZ6SE9qaTFDd2FRY3NjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2ppSk9mYU1aa2M2T0UyVXBiQVF4em82LzBJMnVDZkhPamhWMi9YVVdZYzZPVkNHQlpnd0J6bzRiSktseEdWSE9qbVhJMFhJSThjNk91S01ackFUaHpvNUpmVzJuR21IT2poblNtV3dVc2M2T09pc1JkeGh4em80ZmJjMjZHV0hPanN0YmJXOGNFYzZPT05FeFp3aUJ6bzRxNXhsdUY4SE9qbzRKemIwTEFjNk9HZ0NOZWcyaHpvNU1ybDF6RHZIT2pqbVN1YXNZY2M2T280MlpaUjRSem80U2tPbGpGM0hPampWR1JYUVUwYzZPa2dTNWJ4TkJ6bzRWdG9HdURqSE9qa29XTmFjTVVjNk95amM1YUIxUnpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem82cTJ0VnVDQ0hPamxYai9XY0FRYzZPTFRZWll4RkJ6bzRUYkkxbkRTSE9qaDJ2dVdBVGNjNk8wODZ0cGdxeHpvNk5sSGx1RjlIT2pqR0J3YXNNb2M2T3VIV3BiQTVSem82RmtEbDhCT0hPamhabnRha2VvYzZPanIyQnV4R0J6bzRhNHdWdUhDSE9qanNDaFhFUXdjNk9MdWw5cXdnUnpvNVVrODF4Q2xIT2pvNDZLYjBad2M2T0d6QXRlQnN4em80amNzRzFFY0hPamp2QVdha1RrYzZPTHBKUllRd1J6bzVwQjZXaUZVSE9qaDR6UmJBTTQ9AAA"},"http_status":200,"sha256":"846a96f1fae513ff9d6f372ab8dd516badc8f60a16f6b280cbf42b0662eb6d04","response_bytes":94891}
{"request_id":"request-0040","query_id":"2026-07-31-10m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:21.091133+00:00","completed_at_utc":"2026-10-17T03:46:21.918232+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785499800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqH7cAnEAoABh1M2oftv7HgCwAHAAABcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDQWM2Ti9kT05hUU5Cem80RjlnRjFFQkhPamcvaFlhMEg4YzZPQXFSaHNBcGh6bzM5bEhWMkZtSE9qZ3N6emJRY1FjNk9FYmlsdHduQnpvNEZwTUdnRUlIT2poQkN0YUVSSWM2T0UyVXBiQVF4em80ZHI3bGdFM0hPamhOc2pXY05JYzZPR3lTcGNSbFJ6bzRaMHBsc0ZMSE9qZnNxb1dvQmtjNk9GWGI5ZFJaaHpvMzhKbTJoRWtIT2pmdWFQYWtic2M2T0FIL3RjQnd4em80Sm9nR3dFRUhPamhvQWpYb05vYzZPRm1lMXFSNmh6bzRPVi9XMUhxSE9qZ0pHS2IwTDBjNk9FcERwWXhkeHpvNGE0d1Z1SENIT2pmNEdYWFlYVWM2T0VhWUZlUmd4em80Yk1DMTRHekhPamd3cFpYc0RVYzZPRmJhQnJnNHh6bzRlTTBXd0RPAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0041","query_id":"2026-07-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:21.920244+00:00","completed_at_utc":"2026-10-17T03:46:23.652436+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OLpJRYQwQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqJTMAnEAoABh1M2olMv7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2M2T1ZNUWRaeHZCem83S056bG9IVkhPampEbmNYY09RYzZPU2EyWmVBYWh6bzZWai8ydkZ6SE9qc3JGa2FVWEVjNk96cE5wcFIxeHpvNDU0ZW1wRnFIT2pqREM0WGtMTWM2T1FrM05heDR4em82cTJ0VnVDQ0hPamxYai9XY0FRYzZPdjlDTnJnbnh6bzVVSVlGbURBSE9qbVhJMFhJSThjNk8wODZ0cGdxeHpvNjRveG1zQk9IT2prbDliYWNhWWM2T09pc1JkeGh4em83TFcyMXZIQkhPampHQndhc01vYzZPalpSNWJoZlJ6bzQ0MFRGbkNJSE9qcmgxcVd3T1VjNk9qZ25OdlFzQnpvNkZrRGw4Qk9IT2preXVYWE1POGM2T09aSzVxeGh4em82T3ZZRzdFWUhPanFPTm1XVWVFYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qbFNUelhFS1VjNk9qam9wdlJuQnpvNDFSa1YwRk5IT2pwSUV1VzhUUWM2T0xwSlJZUXdSem80N3dGbXBFNUhPam1rSHBhSVZRYzZPU2hZMXB3eFE9PQAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OEpDpYxdwAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqJTMAnEAoABh1M2olMv4rQCwAHAAACnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFEd2M2T0lPVjV0QWdSem81VXhCMW5HOEhPampEbmNYY09RYzZPeXNXUnBSY1J6bzZWai8ydkZ6SE9qaTFDd2FRY3NjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2ppSk9mYU1aa2M2T0UyVXBiQVF4em82LzBJMnVDZkhPamhWMi9YVVdZYzZPVkNHQlpnd0J6bzRiSktseEdWSE9qbVhJMFhJSThjNk91S01ackFUaHpvNUpmVzJuR21IT2poblNtV3dVc2M2T09pc1JkeGh4em80ZmJjMjZHV0hPanN0YmJXOGNFYzZPT05FeFp3aUJ6bzRxNXhsdUY4SE9qbzRKemIwTEFjNk9HZ0NOZWcyaHpvNU1ybDF6RHZIT2pqbVN1YXNZY2M2T280MlpaUjRSem80U2tPbGpGM0hPampWR1JYUVUwYzZPa2dTNWJ4TkJ6bzRWdG9HdURqSE9qa29XTmFjTVVjNk95amM1YUIxUnpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem82cTJ0VnVDQ0hPamxYai9XY0FRYzZPTFRZWll4RkJ6bzRUYkkxbkRTSE9qaDJ2dVdBVGNjNk8wODZ0cGdxeHpvNk5sSGx1RjlIT2pqR0J3YXNNb2M2T3VIV3BiQTVSem82RmtEbDhCT0hPamhabnRha2VvYzZPanIyQnV4R0J6bzRhNHdWdUhDSE9qanNDaFhFUXdjNk9MdWw5cXdnUnpvNVVrODF4Q2xIT2pvNDZLYjBad2M2T0d6QXRlQnN4em80amNzRzFFY0hPamp2QVdha1RrYzZPTHBKUllRd1J6bzVwQjZXaUZVSE9qaDR6UmJBTTQ9AAA"},"http_status":200,"sha256":"146800f555eedd047e50a2bdfe238fc2b1bee81434ebda09e78a5a70fa2f2cee","response_bytes":94891}
{"request_id":"request-0042","query_id":"2026-07-31-5m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:23.653076+00:00","completed_at_utc":"2026-10-17T03:46:25.256666+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499500 until_time:1785499800","queryType":"Latest","limit":20},"raw_count":19,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6ODlf1tR6gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqyG4AnEAoABh1M2rIbf9jwCwAHAAAA6EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCTWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRSdUtXM0NjSE9qaEtRNldNWGNjNk9HdU1GYmh3aHpvNFFRcldoRVNIT2poR21CWGtZTWM2T0VJbUJjQXFSem80Yk1DMTRHekhPamhObEtXd0VNYzZPSGErNVlCTnh6bzRUYkkxbkRTSE9qaHNrcVhFWlVjNk9GYmFCcmc0eHpvNFowcGxzRkxIT2poVjIvWFVXWWM2T0hqTkZzQXpnPT0AAA"},"http_status":200,"sha256":"3f590c06694cb008ccf9b851dca8cd3b48f3f593747dcb7ca88d7e6415559d6f","response_bytes":87308}
{"request_id":"request-0043","query_id":"2026-08-31-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:25.258037+00:00","completed_at_utc":"2026-10-17T03:46:26.081439+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178800","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqzXYAnEAoABh1M2rNdf9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTXlpakZkeHhCMFF5NXF5MXRFeEhSRExxY0pXb2Y0ZEVNeVo2MWFCcngwUXpQSFdtdUY4SFJETGVzOWE4WllkRU0xYytOYkJTUjBRekRvNm1xQk4AAA"},"http_status":200,"sha256":"6e347deea53978137eec8a0217714e79ecf1a39777d1b10ab7f547b561ae60c8","response_bytes":38255}
{"request_id":"request-0044","query_id":"2026-08-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:26.084785+00:00","completed_at_utc":"2026-10-17T03:46:27.039294+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMmQ9VswJQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqN3sAnEAoABh1M2o3ev7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2RFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJES1R3YmJ3T1FkRU5UaktaZWhQUjBReWFQakY0R0RIUkRTUlI3WElFTWRFTlR2UkZkaFBCMFF5Nm5DVnFIK0hSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUTAyeHAyekQ1SFJETW1ldFdnYThkRU5FZXpWWWc0UjBRMHBpODFySEZIUkRXWWNFV0lkQWRFTkJxSHBhQXRoMFF5M3JQV3ZHV0hSRE5YUGpXd1VrZEVNKy9FMWRnNVIwUXp3eEUyc0dNSFJEUDQ1VmE4YklkRU11YXN0YlJNUjBReW5QeG16SHNIUkRUTy9xV0lZOGRFTldjbHhvQS9SMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVOUHZsMWRnSFIwUXozYUFWdUUvSFJESndseFdrUmNkRU16eDFwcmhmQjBRekRvNm1xQk5IUkRTVnpQYk1aVWRFTkpFSTFwZzRCMFF6L2RNRmxHNUhSRE4rTE5hOEpRZEVNbVE5VnN3SlE9PQAA"},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqN3sAnEAoABh1M2o3ev4rQCwAHAAAB_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDMGRFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJESkhzZ1hNVElkRU1sYUxwY3dHaDBReWs4RzI4RGtIUkRVNHltWG9UMGRFTW1qNHhlQmd4MFF5V2V4V2pHS0hSRFNSUjdYSUVNZEVOVHZSRmRoUEIwUXk2bkNWcUgrSFJEUFNORVdvU0FkRU0yeWtWdEE1eDBRMDJ4cDJ6RDVIUkRSSHMxV0lPRWRFTXlaNjFhQnJ4MFEwcGk4MXJIRkhSRFdZY0VXSWRBZEVOQnFIcGFBdGgwUXkzclBXdkdXSFJETlhQald3VWtkRU0rL0UxZGc1UjBRend4RTJzR01IUkRQNDVWYThiSWRFTXVhc3RiUk1SMFEwZlNIRjRHN0hSRFZuSmNhQVAwZEVOTTcrcFloangwUXluUHhtekhzSFJEVDc1ZFhZQjBkRU5HdGpaZUIyUjBRejNhQVZ1RS9IUkRKQzZVWGNVVWRFTWxkZlplQUt4MFF6Zml6V3ZDVUhSRE04ZGFhNFh3ZEVNLzNUQlpSdVIwUTBsY3oyekdWSFJEU1JDTmFZT0FkRU1uQ1hGYVJGeDBRekRvNm1xQk5IUkRKa1BWYk1DVT0AAA"},"http_status":200,"sha256":"12db938377b6fca6e6364cf2034125260ce37de6461430e9f5a81a31f059850c","response_bytes":29115}
{"request_id":"request-0045","query_id":"2026-08-31-5m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:27.040646+00:00","completed_at_utc":"2026-10-17T03:46:27.758530+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177900 until_time:1788178200","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMpIopuhQQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq1M0AnEAoABh1M2rUzP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTXBJb3B1aFFSMFF5azhHMjhEa0hSREtjL0diTWV3PQAA"},"http_status":200,"sha256":"eba760665cbe81f5469be057d89f84846c991e964c133a1333c3abb3c92a9b67","response_bytes":13017}
{"request_id":"request-0046","query_id":"2026-08-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:27.759768+00:00","completed_at_utc":"2026-10-17T03:46:28.434115+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMmQ9VswJQAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqQroAnEAoABh1M2pCuf7HgCwAHAAAByEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDZ2RFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJES1R3YmJ3T1FkRU5UaktaZWhQUjBReWFQakY0R0RIUkRTUlI3WElFTWRFTlR2UkZkaFBCMFF5Nm5DVnFIK0hSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUTAyeHAyekQ1SFJETW1ldFdnYThkRU5FZXpWWWc0UjBRMHBpODFySEZIUkRXWWNFV0lkQWRFTkJxSHBhQXRoMFF5M3JQV3ZHV0hSRE5YUGpXd1VrZEVNKy9FMWRnNVIwUXp3eEUyc0dNSFJEUDQ1VmE4YklkRU11YXN0YlJNUjBReW5QeG16SHNIUkRUTy9xV0lZOGRFTldjbHhvQS9SMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVOUHZsMWRnSFIwUXozYUFWdUUvSFJESndseFdrUmNkRU16eDFwcmhmQjBRekRvNm1xQk5IUkRTVnpQYk1aVWRFTkpFSTFwZzRCMFF6L2RNRmxHNUhSRE4rTE5hOEpRZEVNbVE5VnN3SlE9PQAA"},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqQroAnEAoABh1M2pCuf4rQCwAHAAAB_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDMGRFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJESkhzZ1hNVElkRU1sYUxwY3dHaDBReWs4RzI4RGtIUkRVNHltWG9UMGRFTW1qNHhlQmd4MFF5V2V4V2pHS0hSRFNSUjdYSUVNZEVOVHZSRmRoUEIwUXk2bkNWcUgrSFJEUFNORVdvU0FkRU0yeWtWdEE1eDBRMDJ4cDJ6RDVIUkRSSHMxV0lPRWRFTXlaNjFhQnJ4MFEwcGk4MXJIRkhSRFdZY0VXSWRBZEVOQnFIcGFBdGgwUXkzclBXdkdXSFJETlhQald3VWtkRU0rL0UxZGc1UjBRend4RTJzR01IUkRQNDVWYThiSWRFTXVhc3RiUk1SMFEwZlNIRjRHN0hSRFZuSmNhQVAwZEVOTTcrcFloangwUXluUHhtekhzSFJEVDc1ZFhZQjBkRU5HdGpaZUIyUjBRejNhQVZ1RS9IUkRKQzZVWGNVVWRFTWxkZlplQUt4MFF6Zml6V3ZDVUhSRE04ZGFhNFh3ZEVNLzNUQlpSdVIwUTBsY3oyekdWSFJEU1JDTmFZT0FkRU1uQ1hGYVJGeDBRekRvNm1xQk5IUkRKa1BWYk1DVT0AAA"},"http_status":200,"sha256":"15615203ec22d00d8a23ed33ffd2e95562afcc79121ab2117e2aa024d1dea76d","response_bytes":29115}
{"request_id":"request-0047","query_id":"2026-08-31-5m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:28.435696+00:00","completed_at_utc":"2026-10-17T03:46:29.268728+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177900 until_time:1788178200","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMpIopuhQQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq2lIAnEAoABh1M2raUf9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTXBJb3B1aFFSMFF5azhHMjhEa0hSREtjL0diTWV3PQAA"},"http_status":200,"sha256":"7549043fea33d8041d24fcfba47e571c2b134cb00974195e5b47a4a4a88a76c9","response_bytes":13017}
{"request_id":"request-0048","query_id":"2026-08-31-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:29.270366+00:00","completed_at_utc":"2026-10-17T03:46:29.985157+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178800","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq3LAAnEAoABh1M2rcr_9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTXlpakZkeHhCMFF5NXF5MXRFeEhSRExxY0pXb2Y0ZEVNeVo2MWFCcngwUXpQSFdtdUY4SFJETGVzOWE4WllkRU0xYytOYkJTUjBRekRvNm1xQk4AAA"},"http_status":200,"sha256":"f605629519a32bee58116be651db334743cf9cffc7d70d649561e6278f8ad31e","response_bytes":38255}
{"request_id":"request-0049","query_id":"2026-09-30-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:29.986609+00:00","completed_at_utc":"2026-10-17T03:46:30.869960+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqUdEAnEAoABh1M2pR0P7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjNJSE5OdUFzQjAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROMjhVb0JwUm14MDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkcFdGOVdFTThkTjJqWE41WndlQjAzYUswTkZ2QzBIVGQwT1lBYmNlb2ROMm9TQ1ZxQlJSMDNjdlFrVndGU0hUZDJLUU9hNGVzPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0050","query_id":"2026-09-30-5m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:30.872449+00:00","completed_at_utc":"2026-10-17T03:46:31.775688+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769900 until_time:1790770200","queryType":"Latest","limit":20},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2oFmhbwIQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq47kAnEAoABh1M2rjuP9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYWhJSldvRkZIVGRxVkdXYk1hbz0AAA"},"http_status":200,"sha256":"1ba197049d3521e820491a1fe7389c5dc9baaa62b4b09c0d55ac1c3d11504367","response_bytes":29135}
{"request_id":"request-0051","query_id":"2026-09-30-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:31.776742+00:00","completed_at_utc":"2026-10-17T03:46:32.913054+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770800","queryType":"Latest","limit":20},"raw_count":6,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq58oAnEAoABh1M2rnyf9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMnZWZTlkQjZ4MDNiTnJhbTlFdEhUZHJYVjJhMElFZE4yeU4yMXV3NngwM2JPeEtHeEZUSFRkc3hsTVh3TzA9AAA"},"http_status":200,"sha256":"25926ea0f8c85a6f721479a5b0949dd52ee0d3753f2beed8925344931555d2d1","response_bytes":21639}
{"request_id":"request-0052","query_id":"2026-09-30-5m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:32.914361+00:00","completed_at_utc":"2026-10-17T03:46:33.438167+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769900 until_time:1790770200","queryType":"Latest","limit":20},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2oFmhbwIQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq6uoAnEAoABh1M2rq6f9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYWhJSldvRkZIVGRxVkdXYk1hbz0AAA"},"http_status":200,"sha256":"be4a42b027971c679cb6af087fb49afca21b763b64533cf15a9fe3d84ed10931","response_bytes":29135}
{"request_id":"request-0053","query_id":"2026-09-30-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:33.439409+00:00","completed_at_utc":"2026-10-17T03:46:34.567073+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770800","queryType":"Latest","limit":20},"raw_count":6,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq7hUAnEAoABh1M2ruFP9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMnZWZTlkQjZ4MDNiTnJhbTlFdEhUZHJYVjJhMElFZE4yeU4yMXV3NngwM2JPeEtHeEZUSFRkc3hsTVh3TzA9AAA"},"http_status":200,"sha256":"7d1506413e425eff99f7c4e687cc9e89b0c60d09e898c3e51b04d12f7af6c3a6","response_bytes":21639}
{"request_id":"request-0054","query_id":"2026-09-30-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:34.569688+00:00","completed_at_utc":"2026-10-17T03:46:34.923183+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769600 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2KQOa4esKAAIdN2itDRbwtAAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNqawMAnEAoABh1M2prAv7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWROMjh0NnhlaE1oMDNhb1RzMmdEaEhUZHFEazJXd0M0ZE4zRTRYVmNnT3gwM2NiZVZtNUhLSFRkdzlCcVhjVFVkTjNJSE5OdUFzQjAzY2EvUDJzQ0dIVGR3d3dmYkFSa2ROMjhVb0JwUm14MDNjT3JtVnlIQkhUZHNqZHRic09zZE4ybEhveGFnTVIwM2I5SzhtaUduSFRkcFdGOVdFTThkTjJqWE41WndlQjAzYUswTkZ2QzBIVGQwT1lBYmNlb2ROMm9TQ1ZxQlJSMDNjdlFrVndGU0hUZDJLUU9hNGVzPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0055","query_id":"2026-07-31-5m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:34.925547+00:00","completed_at_utc":"2026-10-17T03:46:35.942464+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499500 until_time:1785499800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6ODlf1tR6gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqruQAnEAoABh1M2qu4_9jwCwAHAAAA6EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCTWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRSdUtXM0NjSE9qaEtRNldNWGNjNk9HdU1GYmh3aHpvNFFRcldoRVNIT2poR21CWGtZTWM2T0VJbUJjQXFSem80Yk1DMTRHekhPamhObEtXd0VNYzZPSGErNVlCTnh6bzRUYkkxbkRTSE9qaHNrcVhFWlVjNk9GYmFCcmc0eHpvNFowcGxzRkxIT2poVjIvWFVXWWM2T0hqTkZzQXpnPT0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0056","query_id":"2026-07-31-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:35.943391+00:00","completed_at_utc":"2026-10-17T03:46:37.802527+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500400","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMOdxdw5AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq-WsAnEAoABh1M2r5av9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTVlIQnF3eWh6bzR5WERHdEVjSE9qampSTVdjSWdjNk9Rd0psY1EzaHpvNDU0ZW1wRnFIT2pqS0dHWElBOGM2T09aSzVxeGh4em81Q1RjMXJIakhPampleXlXd1pJYzZPT3dLRmNSREJ6bzQxUmtWMEZOSE9qano0blhBUkljNk9QV1VGYlI2eHpvNHc1M0YzRGtIT2pqUHNUVzBWSWM2T09pc1JkeGh4em80N3dGbXBFNQAA"},"http_status":200,"sha256":"91c04e305b5aa15f864946ad805123e908efdbb1f838d3bcb6fbaa8330ae3dd5","response_bytes":72783}
{"request_id":"request-0057","query_id":"2026-07-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:37.803928+00:00","completed_at_utc":"2026-10-17T03:46:39.690660+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OEpDpYxdwAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqGasAnEAoABh1M2oZqv4rQCwAHAAACnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFEd2M2T0lPVjV0QWdSem81VXhCMW5HOEhPampEbmNYY09RYzZPeXNXUnBSY1J6bzZWai8ydkZ6SE9qaTFDd2FRY3NjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2ppSk9mYU1aa2M2T0UyVXBiQVF4em82LzBJMnVDZkhPamhWMi9YVVdZYzZPVkNHQlpnd0J6bzRiSktseEdWSE9qbVhJMFhJSThjNk91S01ackFUaHpvNUpmVzJuR21IT2poblNtV3dVc2M2T09pc1JkeGh4em80ZmJjMjZHV0hPanN0YmJXOGNFYzZPT05FeFp3aUJ6bzRxNXhsdUY4SE9qbzRKemIwTEFjNk9HZ0NOZWcyaHpvNU1ybDF6RHZIT2pqbVN1YXNZY2M2T280MlpaUjRSem80U2tPbGpGM0hPampWR1JYUVUwYzZPa2dTNWJ4TkJ6bzRWdG9HdURqSE9qa29XTmFjTVVjNk95amM1YUIxUnpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem82cTJ0VnVDQ0hPamxYai9XY0FRYzZPTFRZWll4RkJ6bzRUYkkxbkRTSE9qaDJ2dVdBVGNjNk8wODZ0cGdxeHpvNk5sSGx1RjlIT2pqR0J3YXNNb2M2T3VIV3BiQTVSem82RmtEbDhCT0hPamhabnRha2VvYzZPanIyQnV4R0J6bzRhNHdWdUhDSE9qanNDaFhFUXdjNk9MdWw5cXdnUnpvNVVrODF4Q2xIT2pvNDZLYjBad2M2T0d6QXRlQnN4em80amNzRzFFY0hPamp2QVdha1RrYzZPTHBKUllRd1J6bzVwQjZXaUZVSE9qaDR6UmJBTTQ9AAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAMKAAUdTNqGasAnEAoABh1M2oZqv2PACwAHAAADcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFGQWM2T01PZHhkdzVCem81VXhCMW5HOEhPamlEbGViUUlFYzZPbFkvOXJ4Y3h6bzdLeFpHbEZ4SE9qaTFDd2FRY3NjNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2prSk56V3NlTWM2Tit5cWhhZ0dSem80RnBNR2dFSUhPamhDSmdYQUtrYzZPSWs1OW94bVJ6bzRmYmMyNkdXSE9qci9RamE0SjhjNk91S01ackFUaHpvNVVJWUZtREFIT2ptWEkwWElJOGM2T0UyVXBiQVF4em80YkpLbHhHVkhPamtsOWJhY2FZYzZPR2RLWmJCU3h6bzQ2S3hGM0dISE9qaFYyL1hVV1ljNk95MXR0Ynh3UnpvNDQwVEZuQ0lIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPam80SnpiMExBYzZPR2dDTmVnMmh6bzVNcmwxekR2SE9qZzVYOWJVZW9jNk9PWks1cXhoeHpvNmpqWmxsSGhIT2poS1E2V01YY2M2T05VWkZkQlRSem82U0JMbHZFMEhPamhXMmdhNE9NYzZPU2hZMXB3eFJ6bzRGOWdGMUVCSE9qc28zT1dnZFVjNk9EK0ZoclFmeHpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem80Q3BHR3dDbUhPamdzenpiUWNRYzZPcXRyVmJnZ2h6bzVWNC8xbkFFSE9qaEc0cGJjSndjNk9MVFlaWXhGQnpvNFFRcldoRVNIT2poTnNqV2NOSWM2T0hhKzVZQk54em83VHpxMm1DckhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzZObEhsdUY5SE9qakdCd2FzTW9jNk91SFdwYkE1UnpvNkZrRGw4Qk9IT2poWm50YWtlb2M2T0FrWXB2UXZSem82T3ZZRzdFWUhPamY0R1hYWVhVYzZPampvcHZSbkJ6bzVVazgxeENsSE9qaHJqQlc0Y0ljNk9MdWw5cXdnUnpvNDdBb1Z4RU1IT2poR21CWGtZTWM2T0kzTEJ0UkhCem80Yk1DMTRHekhPamd3cFpYc0RVYzZOL2RPTmFRTkJ6bzRlTTBXd0RPSE9qbWtIcGFJVlFjNk9McEpSWVF3UnpvNDd3Rm1wRTUAAA"},"http_status":200,"sha256":"ab7d80488068f69d9e8c113b5bc3e0112bdc7900acb7d96e4edd67075b03567b","response_bytes":83304}
{"request_id":"request-0058","query_id":"2026-07-31-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:39.692251+00:00","completed_at_utc":"2026-10-17T03:46:40.804061+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500400","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMOdxdw5AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrBeYAnEAoABh1M2sF5f9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTVlIQnF3eWh6bzR5WERHdEVjSE9qampSTVdjSWdjNk9Rd0psY1EzaHpvNDU0ZW1wRnFIT2pqS0dHWElBOGM2T09aSzVxeGh4em81Q1RjMXJIakhPampleXlXd1pJYzZPT3dLRmNSREJ6bzQxUmtWMEZOSE9qano0blhBUkljNk9QV1VGYlI2eHpvNHc1M0YzRGtIT2pqUHNUVzBWSWM2T09pc1JkeGh4em80N3dGbXBFNQAA"},"http_status":200,"sha256":"400dea7c29bd38b6b64728e0f387d6a6918753df2e31914c9f53562eeefdc817","response_bytes":72783}
{"request_id":"request-0059","query_id":"2026-07-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:40.805760+00:00","completed_at_utc":"2026-10-17T03:46:42.379528+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6OEpDpYxdwAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqJTMAnEAoABh1M2olMv4rQCwAHAAACnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFEd2M2T0lPVjV0QWdSem81VXhCMW5HOEhPampEbmNYY09RYzZPeXNXUnBSY1J6bzZWai8ydkZ6SE9qaTFDd2FRY3NjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2ppSk9mYU1aa2M2T0UyVXBiQVF4em82LzBJMnVDZkhPamhWMi9YVVdZYzZPVkNHQlpnd0J6bzRiSktseEdWSE9qbVhJMFhJSThjNk91S01ackFUaHpvNUpmVzJuR21IT2poblNtV3dVc2M2T09pc1JkeGh4em80ZmJjMjZHV0hPanN0YmJXOGNFYzZPT05FeFp3aUJ6bzRxNXhsdUY4SE9qbzRKemIwTEFjNk9HZ0NOZWcyaHpvNU1ybDF6RHZIT2pqbVN1YXNZY2M2T280MlpaUjRSem80U2tPbGpGM0hPampWR1JYUVUwYzZPa2dTNWJ4TkJ6bzRWdG9HdURqSE9qa29XTmFjTVVjNk95amM1YUIxUnpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem82cTJ0VnVDQ0hPamxYai9XY0FRYzZPTFRZWll4RkJ6bzRUYkkxbkRTSE9qaDJ2dVdBVGNjNk8wODZ0cGdxeHpvNk5sSGx1RjlIT2pqR0J3YXNNb2M2T3VIV3BiQTVSem82RmtEbDhCT0hPamhabnRha2VvYzZPanIyQnV4R0J6bzRhNHdWdUhDSE9qanNDaFhFUXdjNk9MdWw5cXdnUnpvNVVrODF4Q2xIT2pvNDZLYjBad2M2T0d6QXRlQnN4em80amNzRzFFY0hPamp2QVdha1RrYzZPTHBKUllRd1J6bzVwQjZXaUZVSE9qaDR6UmJBTTQ9AAA"},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAMKAAUdTNqJTMAnEAoABh1M2olMv2PACwAHAAADcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFGQWM2T01PZHhkdzVCem81VXhCMW5HOEhPamlEbGViUUlFYzZPbFkvOXJ4Y3h6bzdLeFpHbEZ4SE9qaTFDd2FRY3NjNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2prSk56V3NlTWM2Tit5cWhhZ0dSem80RnBNR2dFSUhPamhDSmdYQUtrYzZPSWs1OW94bVJ6bzRmYmMyNkdXSE9qci9RamE0SjhjNk91S01ackFUaHpvNVVJWUZtREFIT2ptWEkwWElJOGM2T0UyVXBiQVF4em80YkpLbHhHVkhPamtsOWJhY2FZYzZPR2RLWmJCU3h6bzQ2S3hGM0dISE9qaFYyL1hVV1ljNk95MXR0Ynh3UnpvNDQwVEZuQ0lIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPam80SnpiMExBYzZPR2dDTmVnMmh6bzVNcmwxekR2SE9qZzVYOWJVZW9jNk9PWks1cXhoeHpvNmpqWmxsSGhIT2poS1E2V01YY2M2T05VWkZkQlRSem82U0JMbHZFMEhPamhXMmdhNE9NYzZPU2hZMXB3eFJ6bzRGOWdGMUVCSE9qc28zT1dnZFVjNk9EK0ZoclFmeHpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem80Q3BHR3dDbUhPamdzenpiUWNRYzZPcXRyVmJnZ2h6bzVWNC8xbkFFSE9qaEc0cGJjSndjNk9MVFlaWXhGQnpvNFFRcldoRVNIT2poTnNqV2NOSWM2T0hhKzVZQk54em83VHpxMm1DckhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzZObEhsdUY5SE9qakdCd2FzTW9jNk91SFdwYkE1UnpvNkZrRGw4Qk9IT2poWm50YWtlb2M2T0FrWXB2UXZSem82T3ZZRzdFWUhPamY0R1hYWVhVYzZPampvcHZSbkJ6bzVVazgxeENsSE9qaHJqQlc0Y0ljNk9MdWw5cXdnUnpvNDdBb1Z4RU1IT2poR21CWGtZTWM2T0kzTEJ0UkhCem80Yk1DMTRHekhPamd3cFpYc0RVYzZOL2RPTmFRTkJ6bzRlTTBXd0RPSE9qbWtIcGFJVlFjNk9McEpSWVF3UnpvNDd3Rm1wRTUAAA"},"http_status":200,"sha256":"6eae19c4b04cbac5cec4baebf08d86ff900192e05078fc351642dabc520d7722","response_bytes":83304}
{"request_id":"request-0060","query_id":"2026-07-31-5m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:42.380889+00:00","completed_at_utc":"2026-10-17T03:46:43.084166+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499500 until_time:1785499800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjh4zRbAM4KAAIc6ODlf1tR6gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqyG4AnEAoABh1M2rIbf9jwCwAHAAAA6EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCTWM2T0QrRmhyUWZ4em80YUFJMTZEYUhPamhabnRha2VvYzZPRGxmMXRSNmh6bzRSdUtXM0NjSE9qaEtRNldNWGNjNk9HdU1GYmh3aHpvNFFRcldoRVNIT2poR21CWGtZTWM2T0VJbUJjQXFSem80Yk1DMTRHekhPamhObEtXd0VNYzZPSGErNVlCTnh6bzRUYkkxbkRTSE9qaHNrcVhFWlVjNk9GYmFCcmc0eHpvNFowcGxzRkxIT2poVjIvWFVXWWM2T0hqTkZzQXpnPT0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0061","query_id":"2026-08-31-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:43.086739+00:00","completed_at_utc":"2026-10-17T03:46:43.672319+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNqzXYAnEAoABh1M2rNdf9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTXlpakZkeHhCMFF5NXF5MXRFeEhSRExxY0pXb2Y0ZEVNeVo2MWFCcngwUXpQSFdtdUY4SFJETGVzOWE4WllkRU0xYytOYkJTUjBRekRvNm1xQk4AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0062","query_id":"2026-08-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:43.674212+00:00","completed_at_utc":"2026-10-17T03:46:44.540019+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqN3sAnEAoABh1M2o3ev4rQCwAHAAAB_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDMGRFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJESkhzZ1hNVElkRU1sYUxwY3dHaDBReWs4RzI4RGtIUkRVNHltWG9UMGRFTW1qNHhlQmd4MFF5V2V4V2pHS0hSRFNSUjdYSUVNZEVOVHZSRmRoUEIwUXk2bkNWcUgrSFJEUFNORVdvU0FkRU0yeWtWdEE1eDBRMDJ4cDJ6RDVIUkRSSHMxV0lPRWRFTXlaNjFhQnJ4MFEwcGk4MXJIRkhSRFdZY0VXSWRBZEVOQnFIcGFBdGgwUXkzclBXdkdXSFJETlhQald3VWtkRU0rL0UxZGc1UjBRend4RTJzR01IUkRQNDVWYThiSWRFTXVhc3RiUk1SMFEwZlNIRjRHN0hSRFZuSmNhQVAwZEVOTTcrcFloangwUXluUHhtekhzSFJEVDc1ZFhZQjBkRU5HdGpaZUIyUjBRejNhQVZ1RS9IUkRKQzZVWGNVVWRFTWxkZlplQUt4MFF6Zml6V3ZDVUhSRE04ZGFhNFh3ZEVNLzNUQlpSdVIwUTBsY3oyekdWSFJEU1JDTmFZT0FkRU1uQ1hGYVJGeDBRekRvNm1xQk5IUkRKa1BWYk1DVT0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0063","query_id":"2026-08-31-5m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:44.541984+00:00","completed_at_utc":"2026-10-17T03:46:45.023544+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177900 until_time:1788178200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMpIopuhQQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq1M0AnEAoABh1M2rUzP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTXBJb3B1aFFSMFF5azhHMjhEa0hSREtjL0diTWV3PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0064","query_id":"2026-08-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:45.025560+00:00","completed_at_utc":"2026-10-17T03:46:45.439495+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdEMkLpRdxRQAIAAIAAAACCAADAAAAAAgABAAAAAIKAAUdTNqQroAnEAoABh1M2pCuf4rQCwAHAAAB_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDMGRFTXlpakZkeHhCMFF5a2lpbTZGQkhSRFJ0UXNiTU1FZEVOQXRmMXJRd0IwUXpqYm8yb0QySFJESkhzZ1hNVElkRU1sYUxwY3dHaDBReWs4RzI4RGtIUkRVNHltWG9UMGRFTW1qNHhlQmd4MFF5V2V4V2pHS0hSRFNSUjdYSUVNZEVOVHZSRmRoUEIwUXk2bkNWcUgrSFJEUFNORVdvU0FkRU0yeWtWdEE1eDBRMDJ4cDJ6RDVIUkRSSHMxV0lPRWRFTXlaNjFhQnJ4MFEwcGk4MXJIRkhSRFdZY0VXSWRBZEVOQnFIcGFBdGgwUXkzclBXdkdXSFJETlhQald3VWtkRU0rL0UxZGc1UjBRend4RTJzR01IUkRQNDVWYThiSWRFTXVhc3RiUk1SMFEwZlNIRjRHN0hSRFZuSmNhQVAwZEVOTTcrcFloangwUXluUHhtekhzSFJEVDc1ZFhZQjBkRU5HdGpaZUIyUjBRejNhQVZ1RS9IUkRKQzZVWGNVVWRFTWxkZlplQUt4MFF6Zml6V3ZDVUhSRE04ZGFhNFh3ZEVNLzNUQlpSdVIwUTBsY3oyekdWSFJEU1JDTmFZT0FkRU1uQ1hGYVJGeDBRekRvNm1xQk5IUkRKa1BWYk1DVT0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0065","query_id":"2026-08-31-5m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:45.441824+00:00","completed_at_utc":"2026-10-17T03:46:45.903818+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788177900 until_time:1788178200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDKc_GbMewKAAIdEMpIopuhQQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq2lIAnEAoABh1M2raUf9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTXBJb3B1aFFSMFF5azhHMjhEa0hSREtjL0diTWV3PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0066","query_id":"2026-08-31-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:45.904635+00:00","completed_at_utc":"2026-10-17T03:46:46.253277+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq3LAAnEAoABh1M2rcr_9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTXlpakZkeHhCMFF5NXF5MXRFeEhSRExxY0pXb2Y0ZEVNeVo2MWFCcngwUXpQSFdtdUY4SFJETGVzOWE4WllkRU0xYytOYkJTUjBRekRvNm1xQk4AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0067","query_id":"2026-09-30-5m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:46.254217+00:00","completed_at_utc":"2026-10-17T03:46:47.078738+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769900 until_time:1790770200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2oFmhbwIQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq47kAnEAoABh1M2rjuP9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYWhJSldvRkZIVGRxVkdXYk1hbz0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0068","query_id":"2026-09-30-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:47.080936+00:00","completed_at_utc":"2026-10-17T03:46:48.004853+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq58oAnEAoABh1M2rnyf9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMnZWZTlkQjZ4MDNiTnJhbTlFdEhUZHJYVjJhMElFZE4yeU4yMXV3NngwM2JPeEtHeEZUSFRkc3hsTVh3TzA9AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0069","query_id":"2026-09-30-5m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:48.006904+00:00","completed_at_utc":"2026-10-17T03:46:48.389960+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790769900 until_time:1790770200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdqmxwWYa8KAAIdN2oFmhbwIQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq6uoAnEAoABh1M2rq6f9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROMnBRcjVzaHNSMDNhZ1dhRnZBaEhUZHFoT3phQU9FZE4yb09UWmJBTGgwM2Fwc2NGbUd2SFRkcVAxYldzZjRkTjJxWFBCWkJFUjAzYWhJSldvRkZIVGRxVkdXYk1hbz0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0070","query_id":"2026-09-30-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:48.392135+00:00","completed_at_utc":"2026-10-17T03:46:48.875507+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq7hUAnEAoABh1M2ruFP9jwCwAHAAAAXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBWWROMnZWZTlkQjZ4MDNiTnJhbTlFdEhUZHJYVjJhMElFZE4yeU4yMXV3NngwM2JPeEtHeEZUSFRkc3hsTVh3TzA9AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0071","query_id":"2026-07-31-5m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:48.877450+00:00","completed_at_utc":"2026-10-17T03:46:50.397803+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500100","queryType":"Latest","limit":20},"raw_count":13,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjjGBwasMoKAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrKr4AnEAoABh1M2sqvf9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9NTUxoZVFzeHpvNHROaGxqRVVIT2ppN3BmYXNJRWM2T0lrNTlveG1Sem80amNzRzFFY0hPamk2U1VXRU1FYzZPSDIzTnVobGc9PQAA"},"http_status":200,"sha256":"c472ca91f0b86537aa85f747ac9d5d43349a2e663e906268a34ff090df450a96","response_bytes":62249}
{"request_id":"request-0072","query_id":"2026-07-31-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:50.401040+00:00","completed_at_utc":"2026-10-17T03:46:51.760842+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMOdxdw5AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNq-WsAnEAoABh1M2r5av9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTVlIQnF3eWh6bzR5WERHdEVjSE9qampSTVdjSWdjNk9Rd0psY1EzaHpvNDU0ZW1wRnFIT2pqS0dHWElBOGM2T09aSzVxeGh4em81Q1RjMXJIakhPampleXlXd1pJYzZPT3dLRmNSREJ6bzQxUmtWMEZOSE9qano0blhBUkljNk9QV1VGYlI2eHpvNHc1M0YzRGtIT2pqUHNUVzBWSWM2T09pc1JkeGh4em80N3dGbXBFNQAA"},"raw_count":11,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNq-WsAnEAoABh1M2r5av7HgCwAHAAABaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCOGM2T1FxR1piaFp4em80OVpObTBDSkhPampEbmNYY09RYzZPTFVMQnBCeXh6bzQ1NGVtcEZxSE9qaktHR1hJQThjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2pqZXl5V3daSWM2T0xUWVpZeEZCem80aVRuMmpHWkhPampvckVYY1ljYzZPSDIzTnVobGh6bzR5VlRWZ0RJSE9qakdCd2FzTW9jNk9NbHd4clJIQnpvNDQwVEZuQ0lIT2prTUNaWEVONGM2T0t1Y1piaGZCem80dTJpMnNHdkhPamptU3Vhc1ljYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qalZHUlhRVTBjNk9QUGlkY0JFaHpvNGpjc0cxRWNIT2pqMWxCVzBlc2M2T0lPVjV0QWdSem80ejdFMXRGU0hPamk2U1VXRU1FYzZPTzhCWnFST1E9PQAA"},"http_status":200,"sha256":"aae2e54351f85f6a7decb346d922a0f343ea49e216267482c9740fa86f859f23","response_bytes":53212}
{"request_id":"request-0073","query_id":"2026-07-31-60m-p1-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:51.763018+00:00","completed_at_utc":"2026-10-17T03:46:52.585128+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAMKAAUdTNqGasAnEAoABh1M2oZqv2PACwAHAAADcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFGQWM2T01PZHhkdzVCem81VXhCMW5HOEhPamlEbGViUUlFYzZPbFkvOXJ4Y3h6bzdLeFpHbEZ4SE9qaTFDd2FRY3NjNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2prSk56V3NlTWM2Tit5cWhhZ0dSem80RnBNR2dFSUhPamhDSmdYQUtrYzZPSWs1OW94bVJ6bzRmYmMyNkdXSE9qci9RamE0SjhjNk91S01ackFUaHpvNVVJWUZtREFIT2ptWEkwWElJOGM2T0UyVXBiQVF4em80YkpLbHhHVkhPamtsOWJhY2FZYzZPR2RLWmJCU3h6bzQ2S3hGM0dISE9qaFYyL1hVV1ljNk95MXR0Ynh3UnpvNDQwVEZuQ0lIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPam80SnpiMExBYzZPR2dDTmVnMmh6bzVNcmwxekR2SE9qZzVYOWJVZW9jNk9PWks1cXhoeHpvNmpqWmxsSGhIT2poS1E2V01YY2M2T05VWkZkQlRSem82U0JMbHZFMEhPamhXMmdhNE9NYzZPU2hZMXB3eFJ6bzRGOWdGMUVCSE9qc28zT1dnZFVjNk9EK0ZoclFmeHpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem80Q3BHR3dDbUhPamdzenpiUWNRYzZPcXRyVmJnZ2h6bzVWNC8xbkFFSE9qaEc0cGJjSndjNk9MVFlaWXhGQnpvNFFRcldoRVNIT2poTnNqV2NOSWM2T0hhKzVZQk54em83VHpxMm1DckhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzZObEhsdUY5SE9qakdCd2FzTW9jNk91SFdwYkE1UnpvNkZrRGw4Qk9IT2poWm50YWtlb2M2T0FrWXB2UXZSem82T3ZZRzdFWUhPamY0R1hYWVhVYzZPampvcHZSbkJ6bzVVazgxeENsSE9qaHJqQlc0Y0ljNk9MdWw5cXdnUnpvNDdBb1Z4RU1IT2poR21CWGtZTWM2T0kzTEJ0UkhCem80Yk1DMTRHekhPamd3cFpYc0RVYzZOL2RPTmFRTkJ6bzRlTTBXd0RPSE9qbWtIcGFJVlFjNk9McEpSWVF3UnpvNDd3Rm1wRTUAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0074","query_id":"2026-07-31-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:52.587195+00:00","completed_at_utc":"2026-10-17T03:46:54.057285+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMOdxdw5AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrBeYAnEAoABh1M2sF5f9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTVlIQnF3eWh6bzR5WERHdEVjSE9qampSTVdjSWdjNk9Rd0psY1EzaHpvNDU0ZW1wRnFIT2pqS0dHWElBOGM2T09aSzVxeGh4em81Q1RjMXJIakhPampleXlXd1pJYzZPT3dLRmNSREJ6bzQxUmtWMEZOSE9qano0blhBUkljNk9QV1VGYlI2eHpvNHc1M0YzRGtIT2pqUHNUVzBWSWM2T09pc1JkeGh4em80N3dGbXBFNQAA"},"raw_count":11,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNrBeYAnEAoABh1M2sF5f7HgCwAHAAABaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCOGM2T1FxR1piaFp4em80OVpObTBDSkhPampEbmNYY09RYzZPTFVMQnBCeXh6bzQ1NGVtcEZxSE9qaktHR1hJQThjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2pqZXl5V3daSWM2T0xUWVpZeEZCem80aVRuMmpHWkhPampvckVYY1ljYzZPSDIzTnVobGh6bzR5VlRWZ0RJSE9qakdCd2FzTW9jNk9NbHd4clJIQnpvNDQwVEZuQ0lIT2prTUNaWEVONGM2T0t1Y1piaGZCem80dTJpMnNHdkhPamptU3Vhc1ljYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qalZHUlhRVTBjNk9QUGlkY0JFaHpvNGpjc0cxRWNIT2pqMWxCVzBlc2M2T0lPVjV0QWdSem80ejdFMXRGU0hPamk2U1VXRU1FYzZPTzhCWnFST1E9PQAA"},"http_status":200,"sha256":"e9b4b9e1a4b24aad0fdd2924156bae567eb751f5fff1daff4d48ea02ccd01502","response_bytes":53200}
{"request_id":"request-0075","query_id":"2026-07-31-60m-p2-w00","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:54.058651+00:00","completed_at_utc":"2026-10-17T03:46:54.709154+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtPOraYKsKAAIc6N-yqhagGQAIAAIAAAACCAADAAAAAAgABAAAAAMKAAUdTNqJTMAnEAoABh1M2olMv2PACwAHAAADcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFGQWM2T01PZHhkdzVCem81VXhCMW5HOEhPamlEbGViUUlFYzZPbFkvOXJ4Y3h6bzdLeFpHbEZ4SE9qaTFDd2FRY3NjNk4vWlIxZGhaaHpvNHd3dUY1Q3pIT2prSk56V3NlTWM2Tit5cWhhZ0dSem80RnBNR2dFSUhPamhDSmdYQUtrYzZPSWs1OW94bVJ6bzRmYmMyNkdXSE9qci9RamE0SjhjNk91S01ackFUaHpvNVVJWUZtREFIT2ptWEkwWElJOGM2T0UyVXBiQVF4em80YkpLbHhHVkhPamtsOWJhY2FZYzZPR2RLWmJCU3h6bzQ2S3hGM0dISE9qaFYyL1hVV1ljNk95MXR0Ynh3UnpvNDQwVEZuQ0lIT2pnQi83WEFjTWM2T0t1Y1piaGZCem80Sm9nR3dFRUhPam80SnpiMExBYzZPR2dDTmVnMmh6bzVNcmwxekR2SE9qZzVYOWJVZW9jNk9PWks1cXhoeHpvNmpqWmxsSGhIT2poS1E2V01YY2M2T05VWkZkQlRSem82U0JMbHZFMEhPamhXMmdhNE9NYzZPU2hZMXB3eFJ6bzRGOWdGMUVCSE9qc28zT1dnZFVjNk9EK0ZoclFmeHpvNUpyWmw0QnFIT2pzNlRhYVVkY2M2T09lSHBxUmFoem80Q3BHR3dDbUhPamdzenpiUWNRYzZPcXRyVmJnZ2h6bzVWNC8xbkFFSE9qaEc0cGJjSndjNk9MVFlaWXhGQnpvNFFRcldoRVNIT2poTnNqV2NOSWM2T0hhKzVZQk54em83VHpxMm1DckhPamZ3bWJhRVNRYzZOKzVvOXFSdXh6bzZObEhsdUY5SE9qakdCd2FzTW9jNk91SFdwYkE1UnpvNkZrRGw4Qk9IT2poWm50YWtlb2M2T0FrWXB2UXZSem82T3ZZRzdFWUhPamY0R1hYWVhVYzZPampvcHZSbkJ6bzVVazgxeENsSE9qaHJqQlc0Y0ljNk9MdWw5cXdnUnpvNDdBb1Z4RU1IT2poR21CWGtZTWM2T0kzTEJ0UkhCem80Yk1DMTRHekhPamd3cFpYc0RVYzZOL2RPTmFRTkJ6bzRlTTBXd0RPSE9qbWtIcGFJVlFjNk9McEpSWVF3UnpvNDd3Rm1wRTUAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0076","query_id":"2026-07-31-5m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:54.712180+00:00","completed_at_utc":"2026-10-17T03:46:56.267762+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500100","queryType":"Latest","limit":20},"raw_count":13,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjjGBwasMoKAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrQaUAnEAoABh1M2tBpP9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9NTUxoZVFzeHpvNHROaGxqRVVIT2ppN3BmYXNJRWM2T0lrNTlveG1Sem80amNzRzFFY0hPamk2U1VXRU1FYzZPSDIzTnVobGc9PQAA"},"http_status":200,"sha256":"65089c891e9ada953ab94abf2cdba8836ede6fa6f7cbcd5905716331c4171793","response_bytes":62249}
{"request_id":"request-0077","query_id":"2026-08-31-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:56.268402+00:00","completed_at_utc":"2026-10-17T03:46:57.453379+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179400","queryType":"Latest","limit":20},"raw_count":7,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrRxMAnEAoABh1M2tHEv9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTTQyNk5xQTloMFF6d3hFMnNHTUhSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUXozYUFWdUUvSFJETitMTmE4SlFkRU0rL0UxZGc1UT09AAA"},"http_status":200,"sha256":"98377a1d59f87397b0d7969854077c2eb403240678601e4eaff650e18112888b","response_bytes":42766}
{"request_id":"request-0078","query_id":"2026-08-31-5m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:57.455428+00:00","completed_at_utc":"2026-10-17T03:46:58.615715+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178500","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDMOjqaoE0KAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrTEoAnEAoABh1M2tMSf9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXVhc3RiUk1SMFF5Nm5DVnFIK0hSRExlczlhOFpZZEVNdzZPcHFnVFE9PQAA"},"http_status":200,"sha256":"a51ba35d97e7f483dbc1f7afd006ee10b53d68fb276cf55276d0a6688d75b115","response_bytes":16664}
{"request_id":"request-0079","query_id":"2026-08-31-5m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:58.617733+00:00","completed_at_utc":"2026-10-17T03:46:59.686905+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178500","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDMOjqaoE0KAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrUHUAnEAoABh1M2tQdP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXVhc3RiUk1SMFF5Nm5DVnFIK0hSRExlczlhOFpZZEVNdzZPcHFnVFE9PQAA"},"http_status":200,"sha256":"a6e8c8d4cff0667d55015e9edd6bf043414e5c55e7676f96c590057dd61594f1","response_bytes":16664}
{"request_id":"request-0080","query_id":"2026-08-31-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:46:59.688482+00:00","completed_at_utc":"2026-10-17T03:47:01.020013+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179400","queryType":"Latest","limit":20},"raw_count":7,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrVFIAnEAoABh1M2tUUf9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTTQyNk5xQTloMFF6d3hFMnNHTUhSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUXozYUFWdUUvSFJETitMTmE4SlFkRU0rL0UxZGc1UT09AAA"},"http_status":200,"sha256":"dc2dd7438ce638614c37fe983b42081764a2d1391c450c066c728bc261d13929","response_bytes":42756}
{"request_id":"request-0081","query_id":"2026-09-30-5m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:01.021155+00:00","completed_at_utc":"2026-10-17T03:47:02.238681+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770500","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdr1XvXQesKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrWwsAnEAoABh1M2tbCv9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROMnZWZTlkQjZ4MDNhMTFkbXRDQgAA"},"http_status":200,"sha256":"56c08a684b879b65cf03f958a9955021b1d5c8dc7260d4c37cd5f8bf30b80e20","response_bytes":11018}
{"request_id":"request-0082","query_id":"2026-09-30-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:02.240539+00:00","completed_at_utc":"2026-10-17T03:47:02.991140+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771400","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrXbEAnEAoABh1M2tdsP9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROMjh0NnhlaE1oMDNickdjV3NBVUhUZHQ5RGJhZ0dnZE4yOFVvQnBSbXgwM2JuZFRsbkV5SFRkdG1uWWIwS29kTjI3eDFGdUEvQjAzYmtDZG13R3QAAA"},"http_status":200,"sha256":"b15ac4b3588d66b5fcf27034a992a0b1db582eeb87ffbbfd6c0f7cdde4df82d2","response_bytes":22506}
{"request_id":"request-0083","query_id":"2026-09-30-5m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:02.992518+00:00","completed_at_utc":"2026-10-17T03:47:04.122761+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770500","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdr1XvXQesKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrYnkAnEAoABh1M2tieP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROMnZWZTlkQjZ4MDNhMTFkbXRDQgAA"},"http_status":200,"sha256":"4fb2b5bfd20ef0f2de55fff187caa66909b87d436d5f66d86da315b3d39af8d2","response_bytes":11018}
{"request_id":"request-0084","query_id":"2026-09-30-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:04.124586+00:00","completed_at_utc":"2026-10-17T03:47:05.023113+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771400","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrZZQAnEAoABh1M2tlk_9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROMjh0NnhlaE1oMDNickdjV3NBVUhUZHQ5RGJhZ0dnZE4yOFVvQnBSbXgwM2JuZFRsbkV5SFRkdG1uWWIwS29kTjI3eDFGdUEvQjAzYmtDZG13R3QAAA"},"http_status":200,"sha256":"ff6bd88244a7aa08fbb55eaf8536aad729794f5c12f02557579fcd25f79108df","response_bytes":22506}
{"request_id":"request-0085","query_id":"2026-07-31-5m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:05.024652+00:00","completed_at_utc":"2026-10-17T03:47:05.569871+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500100","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjjGBwasMoKAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrKr4AnEAoABh1M2sqvf9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9NTUxoZVFzeHpvNHROaGxqRVVIT2ppN3BmYXNJRWM2T0lrNTlveG1Sem80amNzRzFFY0hPamk2U1VXRU1FYzZPSDIzTnVobGc9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0086","query_id":"2026-07-31-10m-p1-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:05.572029+00:00","completed_at_utc":"2026-10-17T03:47:06.505385+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNq-WsAnEAoABh1M2r5av7HgCwAHAAABaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCOGM2T1FxR1piaFp4em80OVpObTBDSkhPampEbmNYY09RYzZPTFVMQnBCeXh6bzQ1NGVtcEZxSE9qaktHR1hJQThjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2pqZXl5V3daSWM2T0xUWVpZeEZCem80aVRuMmpHWkhPampvckVYY1ljYzZPSDIzTnVobGh6bzR5VlRWZ0RJSE9qakdCd2FzTW9jNk9NbHd4clJIQnpvNDQwVEZuQ0lIT2prTUNaWEVONGM2T0t1Y1piaGZCem80dTJpMnNHdkhPamptU3Vhc1ljYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qalZHUlhRVTBjNk9QUGlkY0JFaHpvNGpjc0cxRWNIT2pqMWxCVzBlc2M2T0lPVjV0QWdSem80ejdFMXRGU0hPamk2U1VXRU1FYzZPTzhCWnFST1E9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0087","query_id":"2026-07-31-10m-p2-w01","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:06.506853+00:00","completed_at_utc":"2026-10-17T03:47:06.876804+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNrBeYAnEAoABh1M2sF5f7HgCwAHAAABaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCOGM2T1FxR1piaFp4em80OVpObTBDSkhPampEbmNYY09RYzZPTFVMQnBCeXh6bzQ1NGVtcEZxSE9qaktHR1hJQThjNk9NTUxoZVFzeHpvNUNUYzFySGpIT2pqZXl5V3daSWM2T0xUWVpZeEZCem80aVRuMmpHWkhPampvckVYY1ljYzZPSDIzTnVobGh6bzR5VlRWZ0RJSE9qakdCd2FzTW9jNk9NbHd4clJIQnpvNDQwVEZuQ0lIT2prTUNaWEVONGM2T0t1Y1piaGZCem80dTJpMnNHdkhPamptU3Vhc1ljYzZPTHVsOXF3Z1J6bzQ3QW9WeEVNSE9qalZHUlhRVTBjNk9QUGlkY0JFaHpvNGpjc0cxRWNIT2pqMWxCVzBlc2M2T0lPVjV0QWdSem80ejdFMXRGU0hPamk2U1VXRU1FYzZPTzhCWnFST1E9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0088","query_id":"2026-07-31-5m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:06.877808+00:00","completed_at_utc":"2026-10-17T03:47:07.558181+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499800 until_time:1785500100","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjjGBwasMoKAAIc6OH23NuhlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrQaUAnEAoABh1M2tBpP9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T0lPVjV0QWdSem80dzUzRjNEa0hPampHQndhc01vYzZPS3VjWmJoZkJ6bzR0UXNHa0hMSE9qaTdhTGF3YThjNk9NTUxoZVFzeHpvNHROaGxqRVVIT2ppN3BmYXNJRWM2T0lrNTlveG1Sem80amNzRzFFY0hPamk2U1VXRU1FYzZPSDIzTnVobGc9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0089","query_id":"2026-08-31-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:07.560563+00:00","completed_at_utc":"2026-10-17T03:47:08.051940+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrRxMAnEAoABh1M2tHEv9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTTQyNk5xQTloMFF6d3hFMnNHTUhSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUXozYUFWdUUvSFJETitMTmE4SlFkRU0rL0UxZGc1UT09AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0090","query_id":"2026-08-31-5m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:08.053799+00:00","completed_at_utc":"2026-10-17T03:47:08.977723+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDMOjqaoE0KAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrTEoAnEAoABh1M2tMSf9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXVhc3RiUk1SMFF5Nm5DVnFIK0hSRExlczlhOFpZZEVNdzZPcHFnVFE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0091","query_id":"2026-08-31-5m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:08.981130+00:00","completed_at_utc":"2026-10-17T03:47:09.360439+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178200 until_time:1788178500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDMOjqaoE0KAAIdEMt6z1rxlgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrUHUAnEAoABh1M2tQdP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXVhc3RiUk1SMFF5Nm5DVnFIK0hSRExlczlhOFpZZEVNdzZPcHFnVFE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0092","query_id":"2026-08-31-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:09.362754+00:00","completed_at_utc":"2026-10-17T03:47:10.127895+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrVFIAnEAoABh1M2tUUf9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTTQyNk5xQTloMFF6d3hFMnNHTUhSRFBTTkVXb1NBZEVNMnlrVnRBNXgwUXozYUFWdUUvSFJETitMTmE4SlFkRU0rL0UxZGc1UT09AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0093","query_id":"2026-09-30-5m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:10.130172+00:00","completed_at_utc":"2026-10-17T03:47:11.072925+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdr1XvXQesKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrWwsAnEAoABh1M2tbCv9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROMnZWZTlkQjZ4MDNhMTFkbXRDQgAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0094","query_id":"2026-09-30-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:11.074845+00:00","completed_at_utc":"2026-10-17T03:47:11.973174+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrXbEAnEAoABh1M2tdsP9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROMjh0NnhlaE1oMDNickdjV3NBVUhUZHQ5RGJhZ0dnZE4yOFVvQnBSbXgwM2JuZFRsbkV5SFRkdG1uWWIwS29kTjI3eDFGdUEvQjAzYmtDZG13R3QAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0095","query_id":"2026-09-30-5m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:11.975289+00:00","completed_at_utc":"2026-10-17T03:47:12.335799+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770200 until_time:1790770500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdr1XvXQesKAAIdN2tdXZrQgQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrYnkAnEAoABh1M2tieP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROMnZWZTlkQjZ4MDNhMTFkbXRDQgAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0096","query_id":"2026-09-30-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:12.337789+00:00","completed_at_utc":"2026-10-17T03:47:12.722886+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrZZQAnEAoABh1M2tlk_9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROMjh0NnhlaE1oMDNickdjV3NBVUhUZHQ5RGJhZ0dnZE4yOFVvQnBSbXgwM2JuZFRsbkV5SFRkdG1uWWIwS29kTjI3eDFGdUEvQjAzYmtDZG13R3QAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0097","query_id":"2026-07-31-5m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:12.724890+00:00","completed_at_utc":"2026-10-17T03:47:13.942744+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500100 until_time:1785500400","queryType":"Latest","limit":20},"raw_count":18,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMlU1YAyAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrh14AnEAoABh1M2uHXf9jwCwAHAAAA3EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCSWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTWx3eHJSSEJ6bzQ0MFRGbkNJSE9qa01DWlhFTjRjNk9PZUhwcVJhaHpvNHloaGx5QVBIT2pqbVN1YXNZY2M2T1FrM05heDR4em80M3NzbHNHU0hPampzQ2hYRVF3YzZPTlVaRmRCVFJ6bzQ4K0oxd0VTSE9qajFsQlcwZXNjNk9NK3hOYlJVaHpvNDZLeEYzR0hIT2pqdkFXYWtUaz0AAA"},"http_status":200,"sha256":"ec854ad6a2baa35f0eea1a64908d791ca4390ea96c67c770de882b7ba48da2fb","response_bytes":63452}
{"request_id":"request-0098","query_id":"2026-07-31-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:13.944013+00:00","completed_at_utc":"2026-10-17T03:47:15.810041+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785501000","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSX1tpxpgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrjO4AnEAoABh1M2uM7f9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPU2EyWmVBYWh6bzVXYklWcUc5SE9qbDhRYmJRTm9jNk9aM0hWcGgrQnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVVSVlGbURBSE9qbVhJMFhJSThjNk9TWDF0cHhwaHpvNUtGalduREZIT2prL3BUYXNPb2M2T1VhYXhiUTdCem81UFI4MjNCYgAA"},"http_status":200,"sha256":"5b3f6506900aac1eb85941d1ed5ebc6528c28777d50930eac85020e148f1ca8d","response_bytes":134305}
{"request_id":"request-0099","query_id":"2026-07-31-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:15.810993+00:00","completed_at_utc":"2026-10-17T03:47:17.194969+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785501000","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSX1tpxpgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrk6oAnEAoABh1M2uTqf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPU2EyWmVBYWh6bzVXYklWcUc5SE9qbDhRYmJRTm9jNk9aM0hWcGgrQnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVVSVlGbURBSE9qbVhJMFhJSThjNk9TWDF0cHhwaHpvNUtGalduREZIT2prL3BUYXNPb2M2T1VhYXhiUTdCem81UFI4MjNCYgAA"},"http_status":200,"sha256":"d3c5256aba0ce3e234099d555431a9afc25b909fc381cfa1b13485decedca4ee","response_bytes":134305}
{"request_id":"request-0100","query_id":"2026-07-31-5m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:17.195960+00:00","completed_at_utc":"2026-10-17T03:47:18.178634+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500100 until_time:1785500400","queryType":"Latest","limit":20},"raw_count":18,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMlU1YAyAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrmAIAnEAoABh1M2uYAf9jwCwAHAAAA3EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCSWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTWx3eHJSSEJ6bzQ0MFRGbkNJSE9qa01DWlhFTjRjNk9PZUhwcVJhaHpvNHloaGx5QVBIT2pqbVN1YXNZY2M2T1FrM05heDR4em80M3NzbHNHU0hPampzQ2hYRVF3YzZPTlVaRmRCVFJ6bzQ4K0oxd0VTSE9qajFsQlcwZXNjNk9NK3hOYlJVaHpvNDZLeEYzR0hIT2pqdkFXYWtUaz0AAA"},"http_status":200,"sha256":"fa87f50bf9c5c5f43ca892c3e4a0b30f4ca899e95d254660e847861eccb337be","response_bytes":63452}
{"request_id":"request-0101","query_id":"2026-08-31-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:18.179422+00:00","completed_at_utc":"2026-10-17T03:47:19.033439+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788180000","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrnH4AnEAoABh1M2ucff9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOSDBoeGVCdXgwUTBhMk5sNEhaSFJEUkhzMVdJT0VkRU5CcUhwYUF0aDBRei9kTUZsRzUAAA"},"http_status":200,"sha256":"38229a628b3bd91e20662c748d95c32d65e9fef1298b92b363f798c8b6c676bd","response_bytes":39765}
{"request_id":"request-0102","query_id":"2026-08-31-5m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:19.035092+00:00","completed_at_utc":"2026-10-17T03:47:19.866803+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178500 until_time:1788178800","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMyZ61aBrwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrn6UAnEAoABh1M2ufpP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXlpakZkeHhCMFF6Sm5yVm9HdkhSRE04ZGFhNFh3ZEVNMWMrTmJCU1E9PQAA"},"http_status":200,"sha256":"991f6fe470d25d5f746a89246050c6df965b7e08ef7e1c3958d746f70d7798d6","response_bytes":21791}
{"request_id":"request-0103","query_id":"2026-08-31-5m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:19.868915+00:00","completed_at_utc":"2026-10-17T03:47:21.037291+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178500 until_time:1788178800","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMyZ61aBrwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNro-MAnEAoABh1M2uj4v9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXlpakZkeHhCMFF6Sm5yVm9HdkhSRE04ZGFhNFh3ZEVNMWMrTmJCU1E9PQAA"},"http_status":200,"sha256":"2d032774bff38e6265c6bb98ccc1249e3d5afcb2eb82049ba4ec97ca6496e442","response_bytes":21791}
{"request_id":"request-0104","query_id":"2026-08-31-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:21.038827+00:00","completed_at_utc":"2026-10-17T03:47:22.156199+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788180000","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrqA8AnEAoABh1M2uoDv9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOSDBoeGVCdXgwUTBhMk5sNEhaSFJEUkhzMVdJT0VkRU5CcUhwYUF0aDBRei9kTUZsRzUAAA"},"http_status":200,"sha256":"e96eb4e1feeb057ae5aca2501cb83c21d685662a97b8818e797ebd8c1f3d8972","response_bytes":39735}
{"request_id":"request-0105","query_id":"2026-09-30-5m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:22.157961+00:00","completed_at_utc":"2026-10-17T03:47:23.291597+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770500 until_time:1790770800","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2yN21uw6wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrrUUAnEAoABh1M2utRP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMnphMnB2UkxSMDNiSTNiVzdEckhUZHM3RW9iRVZNZE4yekdVeGZBN1E9PQAA"},"http_status":200,"sha256":"6b604d05d705b14fb214aa327320520d8ebec7ff1c466389d76c7dee0c33067a","response_bytes":10816}
{"request_id":"request-0106","query_id":"2026-09-30-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:23.293454+00:00","completed_at_utc":"2026-10-17T03:47:24.594142+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790772000","queryType":"Latest","limit":20},"raw_count":13,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrsSYAnEAoABh1M2uxJf9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGROMitRZTVwQXJCMDNiODhHbXNHckhUZHhPRjFYSURzZE4zRzNsWnVSeWgwM2NQUWFsM0UxSFRkeHI4L2F3SVlkTjNEREI5c0JHUjAzY1ZKVzJsRXZIVGR3NnVaWEljRWROMi8zV0JvaHdCMDNiOUs4bWlHbkhUZHh1WnliZ0pnZE4zRU9RVnJSVVE9PQAA"},"http_status":200,"sha256":"b17868e29bec4dc759b18b8f13dc47dc71c9989c291779559f9bed723e1e53d3","response_bytes":59806}
{"request_id":"request-0107","query_id":"2026-09-30-5m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:24.595659+00:00","completed_at_utc":"2026-10-17T03:47:25.758957+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770500 until_time:1790770800","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2yN21uw6wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrtukAnEAoABh1M2u26P9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMnphMnB2UkxSMDNiSTNiVzdEckhUZHM3RW9iRVZNZE4yekdVeGZBN1E9PQAA"},"http_status":200,"sha256":"78b551ea50962a13f8c9353d20167af92fe1c1d2926b3f22ac0c96a130f05cc1","response_bytes":10816}
{"request_id":"request-0108","query_id":"2026-09-30-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:25.760880+00:00","completed_at_utc":"2026-10-17T03:47:27.341263+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790772000","queryType":"Latest","limit":20},"raw_count":13,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrutMAnEAoABh1M2u60v9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGROMitRZTVwQXJCMDNiODhHbXNHckhUZHhPRjFYSURzZE4zRzNsWnVSeWgwM2NQUWFsM0UxSFRkeHI4L2F3SVlkTjNEREI5c0JHUjAzY1ZKVzJsRXZIVGR3NnVaWEljRWROMi8zV0JvaHdCMDNiOUs4bWlHbkhUZHh1WnliZ0pnZE4zRU9RVnJSVVE9PQAA"},"http_status":200,"sha256":"562fd9a792b1da49ea696975822f90e7cac9fd6687155ad5b1e2e776bb46ad94","response_bytes":59786}
{"request_id":"request-0109","query_id":"2026-07-31-5m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:27.342425+00:00","completed_at_utc":"2026-10-17T03:47:27.864232+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500100 until_time:1785500400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMlU1YAyAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrh14AnEAoABh1M2uHXf9jwCwAHAAAA3EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCSWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTWx3eHJSSEJ6bzQ0MFRGbkNJSE9qa01DWlhFTjRjNk9PZUhwcVJhaHpvNHloaGx5QVBIT2pqbVN1YXNZY2M2T1FrM05heDR4em80M3NzbHNHU0hPampzQ2hYRVF3YzZPTlVaRmRCVFJ6bzQ4K0oxd0VTSE9qajFsQlcwZXNjNk9NK3hOYlJVaHpvNDZLeEYzR0hIT2pqdkFXYWtUaz0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0110","query_id":"2026-07-31-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:27.868473+00:00","completed_at_utc":"2026-10-17T03:47:28.442564+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785501000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSX1tpxpgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrjO4AnEAoABh1M2uM7f9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPU2EyWmVBYWh6bzVXYklWcUc5SE9qbDhRYmJRTm9jNk9aM0hWcGgrQnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVVSVlGbURBSE9qbVhJMFhJSThjNk9TWDF0cHhwaHpvNUtGalduREZIT2prL3BUYXNPb2M2T1VhYXhiUTdCem81UFI4MjNCYgAA"},"raw_count":1,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNrjO4AnEAoABh1M2uM7f7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPWjNIVnBoK0J6bzVKclpsNEJxSE9qbDhRYmJRTm9jNk9WbXlGYWh2UnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVJbGdHcENiSE9qbFFoZ1dZTUFjNk9aY2pSY2dqeHpvNVBSODIzQmJIT2prbDliYWNhWWM2T1QrbE5xdzZoem81UnByRnREc0hPamtvV05hY01VPQAA"},"http_status":200,"sha256":"4ba2a6563737c6cd01fa1d63f9a8452587b1ad3f0bda7c5a55d39dcc49c69348","response_bytes":9394}
{"request_id":"request-0111","query_id":"2026-07-31-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:28.445075+00:00","completed_at_utc":"2026-10-17T03:47:28.910003+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785501000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSX1tpxpgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrk6oAnEAoABh1M2uTqf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPU2EyWmVBYWh6bzVXYklWcUc5SE9qbDhRYmJRTm9jNk9aM0hWcGgrQnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVVSVlGbURBSE9qbVhJMFhJSThjNk9TWDF0cHhwaHpvNUtGalduREZIT2prL3BUYXNPb2M2T1VhYXhiUTdCem81UFI4MjNCYgAA"},"raw_count":1,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNrk6oAnEAoABh1M2uTqf7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPWjNIVnBoK0J6bzVKclpsNEJxSE9qbDhRYmJRTm9jNk9WbXlGYWh2UnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVJbGdHcENiSE9qbFFoZ1dZTUFjNk9aY2pSY2dqeHpvNVBSODIzQmJIT2prbDliYWNhWWM2T1QrbE5xdzZoem81UnByRnREc0hPamtvV05hY01VPQAA"},"http_status":200,"sha256":"a555b7e6f54698ecc46898e000dcba4f2cef49afc371b2f77229717a249b67fe","response_bytes":9394}
{"request_id":"request-0112","query_id":"2026-07-31-5m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:28.910694+00:00","completed_at_utc":"2026-10-17T03:47:29.275635+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500100 until_time:1785500400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjkMCZXEN4KAAIc6OMlU1YAyAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrmAIAnEAoABh1M2uYAf9jwCwAHAAAA3EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCSWM2T1FxR1piaFp4em80OVpObTBDSkhPampKVk5XQU1nYzZPTWx3eHJSSEJ6bzQ0MFRGbkNJSE9qa01DWlhFTjRjNk9PZUhwcVJhaHpvNHloaGx5QVBIT2pqbVN1YXNZY2M2T1FrM05heDR4em80M3NzbHNHU0hPampzQ2hYRVF3YzZPTlVaRmRCVFJ6bzQ4K0oxd0VTSE9qajFsQlcwZXNjNk9NK3hOYlJVaHpvNDZLeEYzR0hIT2pqdkFXYWtUaz0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0113","query_id":"2026-08-31-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:29.278092+00:00","completed_at_utc":"2026-10-17T03:47:29.779967+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788180000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrnH4AnEAoABh1M2ucff9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOSDBoeGVCdXgwUTBhMk5sNEhaSFJEUkhzMVdJT0VkRU5CcUhwYUF0aDBRei9kTUZsRzUAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0114","query_id":"2026-08-31-5m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:29.782481+00:00","completed_at_utc":"2026-10-17T03:47:30.316682+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178500 until_time:1788178800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMyZ61aBrwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrn6UAnEAoABh1M2ufpP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXlpakZkeHhCMFF6Sm5yVm9HdkhSRE04ZGFhNFh3ZEVNMWMrTmJCU1E9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0115","query_id":"2026-08-31-5m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:30.319620+00:00","completed_at_utc":"2026-10-17T03:47:31.008907+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178500 until_time:1788178800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDNXPjWwUkKAAIdEMyZ61aBrwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNro-MAnEAoABh1M2uj4v9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTXlpakZkeHhCMFF6Sm5yVm9HdkhSRE04ZGFhNFh3ZEVNMWMrTmJCU1E9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0116","query_id":"2026-08-31-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:31.011340+00:00","completed_at_utc":"2026-10-17T03:47:31.395008+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788180000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrqA8AnEAoABh1M2uoDv9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2RFTkcxQ3hzd3dSMFEwQzEvV3REQUhSRFA0NVZhOGJJZEVOSDBoeGVCdXgwUTBhMk5sNEhaSFJEUkhzMVdJT0VkRU5CcUhwYUF0aDBRei9kTUZsRzUAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0117","query_id":"2026-09-30-5m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:31.397542+00:00","completed_at_utc":"2026-10-17T03:47:32.247302+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770500 until_time:1790770800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2yN21uw6wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrrUUAnEAoABh1M2utRP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMnphMnB2UkxSMDNiSTNiVzdEckhUZHM3RW9iRVZNZE4yekdVeGZBN1E9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0118","query_id":"2026-09-30-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:32.249788+00:00","completed_at_utc":"2026-10-17T03:47:32.962491+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790772000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrsSYAnEAoABh1M2uxJf9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGROMitRZTVwQXJCMDNiODhHbXNHckhUZHhPRjFYSURzZE4zRzNsWnVSeWgwM2NQUWFsM0UxSFRkeHI4L2F3SVlkTjNEREI5c0JHUjAzY1ZKVzJsRXZIVGR3NnVaWEljRWROMi8zV0JvaHdCMDNiOUs4bWlHbkhUZHh1WnliZ0pnZE4zRU9RVnJSVVE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0119","query_id":"2026-09-30-5m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:32.964408+00:00","completed_at_utc":"2026-10-17T03:47:33.426913+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770500 until_time:1790770800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTds7EobEVMKAAIdN2yN21uw6wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrtukAnEAoABh1M2u26P9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMnphMnB2UkxSMDNiSTNiVzdEckhUZHM3RW9iRVZNZE4yekdVeGZBN1E9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0120","query_id":"2026-09-30-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:33.429133+00:00","completed_at_utc":"2026-10-17T03:47:33.786991+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790772000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNrutMAnEAoABh1M2u60v9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGROMitRZTVwQXJCMDNiODhHbXNHckhUZHhPRjFYSURzZE4zRzNsWnVSeWgwM2NQUWFsM0UxSFRkeHI4L2F3SVlkTjNEREI5c0JHUjAzY1ZKVzJsRXZIVGR3NnVaWEljRWROMi8zV0JvaHdCMDNiOUs4bWlHbkhUZHh1WnliZ0pnZE4zRU9RVnJSVVE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0121","query_id":"2026-07-31-5m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:33.789134+00:00","completed_at_utc":"2026-10-17T03:47:35.369375+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785500700","queryType":"Latest","limit":20},"raw_count":12,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjlXj_WcAQKAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr2lwAnEAoABh1M2vaW_9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T1ZNUWRaeHZCem81SnJabDRCcUhPamt5dVhYTU84YzZPVmVQOVp3QkJ6bzVVazgxeENsSE9qa2lXQWFrSnNjNk9WQ0dCWmd3QnpvNUpmVzJuR21IT2prb1dOYWNNVWM2T1QrbE5xdzZoem81UnByRnREc0hPams5SHpiY0ZzPQAA"},"http_status":200,"sha256":"77bc3216a78c39e43d011f06b8d93bcbdf938c1a6997b7113049dcf25ab7dcf9","response_bytes":95313}
{"request_id":"request-0122","query_id":"2026-07-31-10m-p1-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:35.370848+00:00","completed_at_utc":"2026-10-17T03:47:36.240624+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785501000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNrjO4AnEAoABh1M2uM7f7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPWjNIVnBoK0J6bzVKclpsNEJxSE9qbDhRYmJRTm9jNk9WbXlGYWh2UnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVJbGdHcENiSE9qbFFoZ1dZTUFjNk9aY2pSY2dqeHpvNVBSODIzQmJIT2prbDliYWNhWWM2T1QrbE5xdzZoem81UnByRnREc0hPamtvV05hY01VPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0123","query_id":"2026-07-31-10m-p2-w02","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:36.243044+00:00","completed_at_utc":"2026-10-17T03:47:36.942206+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785501000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNrk6oAnEAoABh1M2uTqf7HgCwAHAAAA_EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCVWM2T1owNU5zQXB4em81VXhCMW5HOEhPam1NVUNiZ09jYzZPWjNIVnBoK0J6bzVKclpsNEJxSE9qbDhRYmJRTm9jNk9WbXlGYWh2UnpvNU1ybDF6RHZIT2pscXgxYmtRRWM2T2FGVmxhd2poem81VjQvMW5BRUhPamxTVHpYRUtVYzZPWXpYcHFCV3h6bzVJbGdHcENiSE9qbFFoZ1dZTUFjNk9aY2pSY2dqeHpvNVBSODIzQmJIT2prbDliYWNhWWM2T1QrbE5xdzZoem81UnByRnREc0hPamtvV05hY01VPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0124","query_id":"2026-07-31-5m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:36.944843+00:00","completed_at_utc":"2026-10-17T03:47:37.975095+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785500700","queryType":"Latest","limit":20},"raw_count":12,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjlXj_WcAQKAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr5WMAnEAoABh1M2vlYv9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T1ZNUWRaeHZCem81SnJabDRCcUhPamt5dVhYTU84YzZPVmVQOVp3QkJ6bzVVazgxeENsSE9qa2lXQWFrSnNjNk9WQ0dCWmd3QnpvNUpmVzJuR21IT2prb1dOYWNNVWM2T1QrbE5xdzZoem81UnByRnREc0hPams5SHpiY0ZzPQAA"},"http_status":200,"sha256":"86cc65d8f12311e8291db3873fe28e92f0ab486331c249ca29da89d3308e20b8","response_bytes":95313}
{"request_id":"request-0125","query_id":"2026-08-31-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:37.975986+00:00","completed_at_utc":"2026-10-17T03:47:38.869044+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180600","queryType":"Latest","limit":20},"raw_count":7,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr6XMAnEAoABh1M2vpcv9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFQ3NWRYWUIwZEVOTnNhZHN3K1IwUTBwaTgxckhGSFJEU1Z6UGJNWlVkRU5KRUkxcGc0QT09AAA"},"http_status":200,"sha256":"47df636f957018f39159290fd41da593b6719459af91ac30a34152a5f0e6111b","response_bytes":29163}
{"request_id":"request-0126","query_id":"2026-08-31-5m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:38.871397+00:00","completed_at_utc":"2026-10-17T03:47:39.970967+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179100","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDONujagPYKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr7a8AnEAoABh1M2vtrv9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTTQyNk5xQTloMFF6YktSVzBEbkhSRE4rTE5hOEpRPQAA"},"http_status":200,"sha256":"be1abd5b0a977c15d15fe233dbdb4564c0d17213ca2fa2650fb8be1d53be1986","response_bytes":22731}
{"request_id":"request-0127","query_id":"2026-08-31-5m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:39.973798+00:00","completed_at_utc":"2026-10-17T03:47:40.745391+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179100","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDONujagPYKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr8TkAnEAoABh1M2vxOP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTTQyNk5xQTloMFF6YktSVzBEbkhSRE4rTE5hOEpRPQAA"},"http_status":200,"sha256":"804ae807fbf74684c4c10a38acd9b94966d4a27132328edfeb196fbc29060671","response_bytes":22731}
{"request_id":"request-0128","query_id":"2026-08-31-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:40.747221+00:00","completed_at_utc":"2026-10-17T03:47:41.387743+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180600","queryType":"Latest","limit":20},"raw_count":7,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr9B4AnEAoABh1M2v0Hf9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFQ3NWRYWUIwZEVOTnNhZHN3K1IwUTBwaTgxckhGSFJEU1Z6UGJNWlVkRU5KRUkxcGc0QT09AAA"},"http_status":200,"sha256":"23fb4894bbe7acd44e1e69de7a84c46a1d65480461c1adc8a3f4c187822415da","response_bytes":29163}
{"request_id":"request-0129","query_id":"2026-09-30-5m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:41.389711+00:00","completed_at_utc":"2026-10-17T03:47:42.553472+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771100","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTduQJ2bAa0KAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr-IsAnEAoABh1M2v4iv9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROMjVBblpzQnJSMDNiZlEyMm9Cb0hUZHRtblliMEtvPQAA"},"http_status":200,"sha256":"3fe0de7bae46bcbf34bfd801c9da4f3fab8fc27146604c2d9d442b0b026c3724","response_bytes":9871}
{"request_id":"request-0130","query_id":"2026-09-30-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:42.555518+00:00","completed_at_utc":"2026-10-17T03:47:43.325324+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772600","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr-0AAnEAoABh1M2v7P_9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM0prZnh1aEdCMDNjZ2MwMjRDd0hUZHkrV1hhc0U0ZE4zUHE2cHJRWlIwM2N2UWtWd0ZTAAA"},"http_status":200,"sha256":"20a80cd9128cabdb20c0a4da6309b3f3bfa9dbd28e15148e8cfa38bf2df1f2e5","response_bytes":28445}
{"request_id":"request-0131","query_id":"2026-09-30-5m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:43.327293+00:00","completed_at_utc":"2026-10-17T03:47:44.137013+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771100","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTduQJ2bAa0KAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr_sUAnEAoABh1M2v-xP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROMjVBblpzQnJSMDNiZlEyMm9Cb0hUZHRtblliMEtvPQAA"},"http_status":200,"sha256":"bf8628dc8ee6baad18747c9cb965683c86a7c08b8f926d56f5d2ff0823dd47ca","response_bytes":9871}
{"request_id":"request-0132","query_id":"2026-09-30-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:44.139134+00:00","completed_at_utc":"2026-10-17T03:47:45.157987+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772600","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsAeUAnEAoABh1M2wB5P9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM0prZnh1aEdCMDNjZ2MwMjRDd0hUZHkrV1hhc0U0ZE4zUHE2cHJRWlIwM2N2UWtWd0ZTAAA"},"http_status":200,"sha256":"c4b0a4ce5231e4ba57f4e538fe17699ab1e08c50195c5c0469178174f7dcb0a6","response_bytes":28445}
{"request_id":"request-0133","query_id":"2026-07-31-5m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:45.159734+00:00","completed_at_utc":"2026-10-17T03:47:45.749666+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785500700","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjlXj_WcAQKAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr2lwAnEAoABh1M2vaW_9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T1ZNUWRaeHZCem81SnJabDRCcUhPamt5dVhYTU84YzZPVmVQOVp3QkJ6bzVVazgxeENsSE9qa2lXQWFrSnNjNk9WQ0dCWmd3QnpvNUpmVzJuR21IT2prb1dOYWNNVWM2T1QrbE5xdzZoem81UnByRnREc0hPams5SHpiY0ZzPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0134","query_id":"2026-07-31-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:45.753868+00:00","completed_at_utc":"2026-10-17T03:47:47.265853+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501600","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OdEF5sRigAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsCWYAnEAoABh1M2wJZf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qblI3RWJjTjhjNk9lQitSYnhQeHpvNkpFeFcwSC9IT2puU2hUYTRXb2M2T2haQTVmQVRoem82RzVnRnhBNkhPam9tVFlXSVB3YzZPZXluTmNnN2h6bzU0UGMxbEVISE9qblJCZWJFWW9jNk9mQXlkdEIzeHpvNkNHZm0yQy9IT2pvYVM2YkVjVWM2T2RQQWhyQml4em81MjZxVjFFbwAA"},"http_status":200,"sha256":"553835036fbae5a014016798785d07747c31ab9e97533fc1e3fec58968550645","response_bytes":95458}
{"request_id":"request-0135","query_id":"2026-07-31-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:47.267291+00:00","completed_at_utc":"2026-10-17T03:47:48.832456+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501600","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OdEF5sRigAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsDqIAnEAoABh1M2wOof9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qblI3RWJjTjhjNk9lQitSYnhQeHpvNkpFeFcwSC9IT2puU2hUYTRXb2M2T2haQTVmQVRoem82RzVnRnhBNkhPam9tVFlXSVB3YzZPZXluTmNnN2h6bzU0UGMxbEVISE9qblJCZWJFWW9jNk9mQXlkdEIzeHpvNkNHZm0yQy9IT2pvYVM2YkVjVWM2T2RQQWhyQml4em81MjZxVjFFbwAA"},"http_status":200,"sha256":"67886bb2d1ece316184cd43b513751c68ffd8b62054e2bdb0e4eaa7ab4edc24f","response_bytes":95448}
{"request_id":"request-0136","query_id":"2026-07-31-5m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:48.833934+00:00","completed_at_utc":"2026-10-17T03:47:49.169284+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500400 until_time:1785500700","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjlXj_WcAQKAAIc6OSJYBqQmwAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr5WMAnEAoABh1M2vlYv9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T1ZNUWRaeHZCem81SnJabDRCcUhPamt5dVhYTU84YzZPVmVQOVp3QkJ6bzVVazgxeENsSE9qa2lXQWFrSnNjNk9WQ0dCWmd3QnpvNUpmVzJuR21IT2prb1dOYWNNVWM2T1QrbE5xdzZoem81UnByRnREc0hPams5SHpiY0ZzPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0137","query_id":"2026-08-31-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:49.172242+00:00","completed_at_utc":"2026-10-17T03:47:49.874151+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr6XMAnEAoABh1M2vpcv9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFQ3NWRYWUIwZEVOTnNhZHN3K1IwUTBwaTgxckhGSFJEU1Z6UGJNWlVkRU5KRUkxcGc0QT09AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0138","query_id":"2026-08-31-5m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:49.876116+00:00","completed_at_utc":"2026-10-17T03:47:51.441562+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179100","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDONujagPYKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr7a8AnEAoABh1M2vtrv9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTTQyNk5xQTloMFF6YktSVzBEbkhSRE4rTE5hOEpRPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0139","query_id":"2026-08-31-5m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:51.444079+00:00","completed_at_utc":"2026-10-17T03:47:52.131801+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788178800 until_time:1788179100","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDONujagPYKAAIdEM2ykVtA5wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr8TkAnEAoABh1M2vxOP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWRFTTQyNk5xQTloMFF6YktSVzBEbkhSRE4rTE5hOEpRPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0140","query_id":"2026-08-31-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:52.135227+00:00","completed_at_utc":"2026-10-17T03:47:52.830570+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr9B4AnEAoABh1M2v0Hf9jwCwAHAAAAaEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBY2RFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFQ3NWRYWUIwZEVOTnNhZHN3K1IwUTBwaTgxckhGSFJEU1Z6UGJNWlVkRU5KRUkxcGc0QT09AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0141","query_id":"2026-09-30-5m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:52.833349+00:00","completed_at_utc":"2026-10-17T03:47:53.590649+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771100","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTduQJ2bAa0KAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr-IsAnEAoABh1M2v4iv9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROMjVBblpzQnJSMDNiZlEyMm9Cb0hUZHRtblliMEtvPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0142","query_id":"2026-09-30-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:53.591501+00:00","completed_at_utc":"2026-10-17T03:47:54.127184+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr-0AAnEAoABh1M2v7P_9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM0prZnh1aEdCMDNjZ2MwMjRDd0hUZHkrV1hhc0U0ZE4zUHE2cHJRWlIwM2N2UWtWd0ZTAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0143","query_id":"2026-09-30-5m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:54.129644+00:00","completed_at_utc":"2026-10-17T03:47:54.590287+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790770800 until_time:1790771100","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTduQJ2bAa0KAAIdN22adhvQqgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNr_sUAnEAoABh1M2v-xP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROMjVBblpzQnJSMDNiZlEyMm9Cb0hUZHRtblliMEtvPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0144","query_id":"2026-09-30-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:54.592659+00:00","completed_at_utc":"2026-10-17T03:47:55.282721+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsAeUAnEAoABh1M2wB5P9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM0prZnh1aEdCMDNjZ2MwMjRDd0hUZHkrV1hhc0U0ZE4zUHE2cHJRWlIwM2N2UWtWd0ZTAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0145","query_id":"2026-07-31-5m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:55.287006+00:00","completed_at_utc":"2026-10-17T03:47:56.875917+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500700 until_time:1785501000","queryType":"Latest","limit":20},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OVmyFahvQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsLo0AnEAoABh1M2wujP9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2M2T1owNU5zQXB4em81akZBbTREbkhPamxac2hXb2IwYzZPWHhCdHRBMmh6bzVuY2RXbUg0SE9qbHF4MWJrUUVjNk9hRlZsYXdqaHpvNWpOZW1vRmJIT2ptWEkwWElJOD0AAA"},"http_status":200,"sha256":"0dd94d790398526ee88602b712a49fe1f1598375191379eae561c3b37a967902","response_bytes":48104}
{"request_id":"request-0146","query_id":"2026-07-31-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:56.877785+00:00","completed_at_utc":"2026-10-17T03:47:58.478741+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OdEF5sRigAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsCWYAnEAoABh1M2wJZf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qblI3RWJjTjhjNk9lQitSYnhQeHpvNkpFeFcwSC9IT2puU2hUYTRXb2M2T2haQTVmQVRoem82RzVnRnhBNkhPam9tVFlXSVB3YzZPZXluTmNnN2h6bzU0UGMxbEVISE9qblJCZWJFWW9jNk9mQXlkdEIzeHpvNkNHZm0yQy9IT2pvYVM2YkVjVWM2T2RQQWhyQml4em81MjZxVjFFbwAA"},"raw_count":10,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNsCWYAnEAoABh1M2wJZf7HgCwAHAAABXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCNGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPYUg3Rm94Wmh6bzU0SDVGdkUvSE9qblNoVGE0V29jNk9hMUd4dGg0aHpvNkc1Z0Z4QTZIT2ptdEdsWHNDSWM2T2laTmhZZy9Cem81dnlaMnBDb0hPam5zcHpYSU80YzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qbndNbmJRZDhjNk9ocExwc1J4UnpvNXpMT1ZnQ1dIT2ptalJwV1VJVWM2T2hHQnhvUXRCem82S2JOVjhFR0hPam5JbDhiY1l3YzZPZEhzUnR3M3h6bzZKRXhXMEgvSE9qb1dRT1h3RTRjNk9ienBCZFJlUnpvNTBRWG14R0tIT2pvSVorYllMOGM2T2FRZWxvaFZCem81MDhDR3NHTEhPam5icXBYVVNnPQAA"},"http_status":200,"sha256":"86b5e725cf4e469e4f53e6b21df07312c06e68c08bef41e9cbb4124cfb2e1219","response_bytes":48195}
{"request_id":"request-0147","query_id":"2026-07-31-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:58.479652+00:00","completed_at_utc":"2026-10-17T03:47:59.355313+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OdEF5sRigAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsDqIAnEAoABh1M2wOof9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qblI3RWJjTjhjNk9lQitSYnhQeHpvNkpFeFcwSC9IT2puU2hUYTRXb2M2T2haQTVmQVRoem82RzVnRnhBNkhPam9tVFlXSVB3YzZPZXluTmNnN2h6bzU0UGMxbEVISE9qblJCZWJFWW9jNk9mQXlkdEIzeHpvNkNHZm0yQy9IT2pvYVM2YkVjVWM2T2RQQWhyQml4em81MjZxVjFFbwAA"},"raw_count":10,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNsDqIAnEAoABh1M2wOof7HgCwAHAAABXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCNGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPYUg3Rm94Wmh6bzU0SDVGdkUvSE9qblNoVGE0V29jNk9hMUd4dGg0aHpvNkc1Z0Z4QTZIT2ptdEdsWHNDSWM2T2laTmhZZy9Cem81dnlaMnBDb0hPam5zcHpYSU80YzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qbndNbmJRZDhjNk9ocExwc1J4UnpvNXpMT1ZnQ1dIT2ptalJwV1VJVWM2T2hHQnhvUXRCem82S2JOVjhFR0hPam5JbDhiY1l3YzZPZEhzUnR3M3h6bzZKRXhXMEgvSE9qb1dRT1h3RTRjNk9ienBCZFJlUnpvNTBRWG14R0tIT2pvSVorYllMOGM2T2FRZWxvaFZCem81MDhDR3NHTEhPam5icXBYVVNnPQAA"},"http_status":200,"sha256":"ce549ccfdbe5da7e7e486a1a99c66356c1fb9635519eb9e3a4f45bbd2266ed20","response_bytes":48195}
{"request_id":"request-0148","query_id":"2026-07-31-5m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:47:59.357173+00:00","completed_at_utc":"2026-10-17T03:48:01.005586+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500700 until_time:1785501000","queryType":"Latest","limit":20},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OVmyFahvQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsPpAAnEAoABh1M2w-j_9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2M2T1owNU5zQXB4em81akZBbTREbkhPamxac2hXb2IwYzZPWHhCdHRBMmh6bzVuY2RXbUg0SE9qbHF4MWJrUUVjNk9hRlZsYXdqaHpvNWpOZW1vRmJIT2ptWEkwWElJOD0AAA"},"http_status":200,"sha256":"6bc15cd79067834af522fc4925ef897b92d8367d43629ce78b4ac2f3f2b1f485","response_bytes":48104}
{"request_id":"request-0149","query_id":"2026-08-31-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:01.007383+00:00","completed_at_utc":"2026-10-17T03:48:01.790535+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788181200","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsQ0sAnEAoABh1M2xDSv9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTlRqS1plaFBSMFExTzlFVjJFOEhSRFZuSmNhQVAwZEVOWmh3UlloMEE9PQAA"},"http_status":200,"sha256":"90c81d886fafb53e41203860451996ff2a9af1e15033c1c00f1a4b3fb210a641","response_bytes":24156}
{"request_id":"request-0150","query_id":"2026-08-31-5m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:01.792952+00:00","completed_at_utc":"2026-10-17T03:48:02.696059+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179100 until_time:1788179400","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM8MRNrBjAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsRuwAnEAoABh1M2xG6_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTThNUk5yQmpCMFF6MGpSRnFFZ0hSRFBkb0JXNFQ4ZEVNKy9FMWRnNVE9PQAA"},"http_status":200,"sha256":"93549f506c7ab7c05304d691bd713ec2508103e1b991f5d5010409ccdae71a56","response_bytes":20230}
{"request_id":"request-0151","query_id":"2026-08-31-5m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:02.698441+00:00","completed_at_utc":"2026-10-17T03:48:03.507829+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179100 until_time:1788179400","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM8MRNrBjAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsSgwAnEAoABh1M2xKC_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTThNUk5yQmpCMFF6MGpSRnFFZ0hSRFBkb0JXNFQ4ZEVNKy9FMWRnNVE9PQAA"},"http_status":200,"sha256":"2dfdc67fe921ffc113847ec1af5de07bf5510a4e2079460049affb44cc4895fb","response_bytes":20230}
{"request_id":"request-0152","query_id":"2026-08-31-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:03.509652+00:00","completed_at_utc":"2026-10-17T03:48:04.306023+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788181200","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsTR4AnEAoABh1M2xNHf9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTlRqS1plaFBSMFExTzlFVjJFOEhSRFZuSmNhQVAwZEVOWmh3UlloMEE9PQAA"},"http_status":200,"sha256":"4819ff631b9d52032dda2d8ba576332e761c9b34f3a195ac446e845ee9fbcc11","response_bytes":24156}
{"request_id":"request-0153","query_id":"2026-09-30-5m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:04.307877+00:00","completed_at_utc":"2026-10-17T03:48:05.413864+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771100 until_time:1790771400","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN253U5ZxMgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsUdUAnEAoABh1M2xR1P9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROMjh0NnhlaE1oMDNickdjV3NBVUhUZHZGS0FhVVpzZE4yNTNVNVp4TWgwM2J2SFVXNEQ4AAA"},"http_status":200,"sha256":"33107540c2dd2ee9b146978a37c7116da2f49fb6542dcddd5ec9dda42c34b206","response_bytes":12830}
{"request_id":"request-0154","query_id":"2026-09-30-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:05.415976+00:00","completed_at_utc":"2026-10-17T03:48:06.748536+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790773200","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsVisAnEAoABh1M2xWKv9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROM1pQS05aUXBCMDNkQ1NvMjVEaEhUZDFreThhVWVBZE4zUmZTdGFoZ0IwM2RVUnhHOUNsSFRkMWJUNFdvUk1kTjNRNWdCdHg2aDAzZGlrRG11SHIAAA"},"http_status":200,"sha256":"bbc2fcfa08db80038f0697844d7265b0df940d379335bc76e4ce3c7ddc7c4129","response_bytes":27369}
{"request_id":"request-0155","query_id":"2026-09-30-5m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:06.753079+00:00","completed_at_utc":"2026-10-17T03:48:07.320852+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771100 until_time:1790771400","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN253U5ZxMgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsWboAnEAoABh1M2xZuf9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROMjh0NnhlaE1oMDNickdjV3NBVUhUZHZGS0FhVVpzZE4yNTNVNVp4TWgwM2J2SFVXNEQ4AAA"},"http_status":200,"sha256":"bfa4f7b7983d254b9e465ef9b9dd84f3b335c2c9aa9fba95579223dbf0453626","response_bytes":12830}
{"request_id":"request-0156","query_id":"2026-09-30-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:07.326487+00:00","completed_at_utc":"2026-10-17T03:48:08.224674+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790773200","queryType":"Latest","limit":20},"raw_count":8,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsW_EAnEAoABh1M2xb8P9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROM1pQS05aUXBCMDNkQ1NvMjVEaEhUZDFreThhVWVBZE4zUmZTdGFoZ0IwM2RVUnhHOUNsSFRkMWJUNFdvUk1kTjNRNWdCdHg2aDAzZGlrRG11SHIAAA"},"http_status":200,"sha256":"42577bcb622fa9647c81dc203c25aca068c4c67ef628fb848d952ebac1451e6c","response_bytes":27369}
{"request_id":"request-0157","query_id":"2026-07-31-5m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:08.225858+00:00","completed_at_utc":"2026-10-17T03:48:09.118548+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500700 until_time:1785501000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OVmyFahvQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsLo0AnEAoABh1M2wujP9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2M2T1owNU5zQXB4em81akZBbTREbkhPamxac2hXb2IwYzZPWHhCdHRBMmh6bzVuY2RXbUg0SE9qbHF4MWJrUUVjNk9hRlZsYXdqaHpvNWpOZW1vRmJIT2ptWEkwWElJOD0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0158","query_id":"2026-07-31-10m-p1-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:09.120770+00:00","completed_at_utc":"2026-10-17T03:48:09.971799+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNsCWYAnEAoABh1M2wJZf7HgCwAHAAABXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCNGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPYUg3Rm94Wmh6bzU0SDVGdkUvSE9qblNoVGE0V29jNk9hMUd4dGg0aHpvNkc1Z0Z4QTZIT2ptdEdsWHNDSWM2T2laTmhZZy9Cem81dnlaMnBDb0hPam5zcHpYSU80YzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qbndNbmJRZDhjNk9ocExwc1J4UnpvNXpMT1ZnQ1dIT2ptalJwV1VJVWM2T2hHQnhvUXRCem82S2JOVjhFR0hPam5JbDhiY1l3YzZPZEhzUnR3M3h6bzZKRXhXMEgvSE9qb1dRT1h3RTRjNk9ienBCZFJlUnpvNTBRWG14R0tIT2pvSVorYllMOGM2T2FRZWxvaFZCem81MDhDR3NHTEhPam5icXBYVVNnPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0159","query_id":"2026-07-31-10m-p2-w03","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:09.973318+00:00","completed_at_utc":"2026-10-17T03:48:10.517447+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNsDqIAnEAoABh1M2wOof7HgCwAHAAABXEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCNGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPYUg3Rm94Wmh6bzU0SDVGdkUvSE9qblNoVGE0V29jNk9hMUd4dGg0aHpvNkc1Z0Z4QTZIT2ptdEdsWHNDSWM2T2laTmhZZy9Cem81dnlaMnBDb0hPam5zcHpYSU80YzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qbndNbmJRZDhjNk9ocExwc1J4UnpvNXpMT1ZnQ1dIT2ptalJwV1VJVWM2T2hHQnhvUXRCem82S2JOVjhFR0hPam5JbDhiY1l3YzZPZEhzUnR3M3h6bzZKRXhXMEgvSE9qb1dRT1h3RTRjNk9ienBCZFJlUnpvNTBRWG14R0tIT2pvSVorYllMOGM2T2FRZWxvaFZCem81MDhDR3NHTEhPam5icXBYVVNnPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0160","query_id":"2026-07-31-5m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:10.520002+00:00","completed_at_utc":"2026-10-17T03:48:11.197766+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785500700 until_time:1785501000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjmhVZWsI4KAAIc6OVmyFahvQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsPpAAnEAoABh1M2w-j_9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2M2T1owNU5zQXB4em81akZBbTREbkhPamxac2hXb2IwYzZPWHhCdHRBMmh6bzVuY2RXbUg0SE9qbHF4MWJrUUVjNk9hRlZsYXdqaHpvNWpOZW1vRmJIT2ptWEkwWElJOD0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0161","query_id":"2026-08-31-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:11.199961+00:00","completed_at_utc":"2026-10-17T03:48:11.640990+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsQ0sAnEAoABh1M2xDSv9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTlRqS1plaFBSMFExTzlFVjJFOEhSRFZuSmNhQVAwZEVOWmh3UlloMEE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0162","query_id":"2026-08-31-5m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:11.643546+00:00","completed_at_utc":"2026-10-17T03:48:12.153113+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179100 until_time:1788179400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM8MRNrBjAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsRuwAnEAoABh1M2xG6_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTThNUk5yQmpCMFF6MGpSRnFFZ0hSRFBkb0JXNFQ4ZEVNKy9FMWRnNVE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0163","query_id":"2026-08-31-5m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:12.156790+00:00","completed_at_utc":"2026-10-17T03:48:12.939042+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179100 until_time:1788179400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDPvxNXYOUKAAIdEM8MRNrBjAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsSgwAnEAoABh1M2xKC_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTThNUk5yQmpCMFF6MGpSRnFFZ0hSRFBkb0JXNFQ4ZEVNKy9FMWRnNVE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0164","query_id":"2026-08-31-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:12.941593+00:00","completed_at_utc":"2026-10-17T03:48:13.279767+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsTR4AnEAoABh1M2xNHf9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTlRqS1plaFBSMFExTzlFVjJFOEhSRFZuSmNhQVAwZEVOWmh3UlloMEE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0165","query_id":"2026-09-30-5m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:13.282088+00:00","completed_at_utc":"2026-10-17T03:48:13.776682+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771100 until_time:1790771400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN253U5ZxMgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsUdUAnEAoABh1M2xR1P9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROMjh0NnhlaE1oMDNickdjV3NBVUhUZHZGS0FhVVpzZE4yNTNVNVp4TWgwM2J2SFVXNEQ4AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0166","query_id":"2026-09-30-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:13.779253+00:00","completed_at_utc":"2026-10-17T03:48:14.513434+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsVisAnEAoABh1M2xWKv9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROM1pQS05aUXBCMDNkQ1NvMjVEaEhUZDFreThhVWVBZE4zUmZTdGFoZ0IwM2RVUnhHOUNsSFRkMWJUNFdvUk1kTjNRNWdCdHg2aDAzZGlrRG11SHIAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0167","query_id":"2026-09-30-5m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:14.515997+00:00","completed_at_utc":"2026-10-17T03:48:14.920172+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771100 until_time:1790771400","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdvLesXoTIKAAIdN253U5ZxMgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsWboAnEAoABh1M2xZuf9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROMjh0NnhlaE1oMDNickdjV3NBVUhUZHZGS0FhVVpzZE4yNTNVNVp4TWgwM2J2SFVXNEQ4AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0168","query_id":"2026-09-30-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:14.922580+00:00","completed_at_utc":"2026-10-17T03:48:15.686159+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsW_EAnEAoABh1M2xb8P9jwCwAHAAAAcEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBZ2ROM1pQS05aUXBCMDNkQ1NvMjVEaEhUZDFreThhVWVBZE4zUmZTdGFoZ0IwM2RVUnhHOUNsSFRkMWJUNFdvUk1kTjNRNWdCdHg2aDAzZGlrRG11SHIAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0169","query_id":"2026-07-31-5m-p1-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:15.688555+00:00","completed_at_utc":"2026-10-17T03:48:17.263456+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501300","queryType":"Latest","limit":20},"raw_count":17,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjng9zWUQcKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsfg8AnEAoABh1M2x-Dv9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T2R1cWxkUktCem81ekxPVmdDV0hPam1oK3hhTVdZYzZPYU5HbFpRaFJ6bzUwZXhHM0RmSE9qbmdma1c4VDhjNk9jaVh4dHhqQnpvNTBvVTJ1RnFIT2ptdFJzYlllSWM2T2J6cEJkUmVSem81dnlaMnBDb0hPam10R2xYc0NJYzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qblJCZWJFWW9jNk9hUWVsb2hWQnpvNTA4Q0dzR0wAAA"},"http_status":200,"sha256":"7b8875b9f94d9f8cd7cf1546f7eb7833968d64a993e6ce9c64523a3b02e606fa","response_bytes":66116}
{"request_id":"request-0170","query_id":"2026-07-31-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:17.265053+00:00","completed_at_utc":"2026-10-17T03:48:18.924828+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785502200","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OmW5pZA9wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNshHEAnEAoABh1M2yEcP9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPbXYrZHB4WkJ6bzZydmFsakNFSE9qcUFmVldjUThjNk9yY0hKY3c2eHpvNlpibWxrRDNIT2pxdmpuYllQa2M2T3FqU1plUVdoem82dVF3MThBbEhPanErc0xib1dVYzZPbzQyWlpSNFJ6bzZxMnRWdUNDSE9qcDlaYVhVRk1jNk9wVmRCY0FIaHpvNnMza1ZnQlFIT2pxVjJPWDBGSWM2T3J5YTlmUUd4em82c1htVnlFbAAA"},"http_status":200,"sha256":"d07aa0fcfa77196531d3c026d6ed7eb2697ed9d7b8e9d7b645d4abd7b5a336d2","response_bytes":91904}
{"request_id":"request-0171","query_id":"2026-07-31-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:18.925220+00:00","completed_at_utc":"2026-10-17T03:48:20.438264+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785502200","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OmW5pZA9wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsilwAnEAoABh1M2yKW_9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPbXYrZHB4WkJ6bzZydmFsakNFSE9qcUFmVldjUThjNk9yY0hKY3c2eHpvNlpibWxrRDNIT2pxdmpuYllQa2M2T3FqU1plUVdoem82dVF3MThBbEhPanErc0xib1dVYzZPbzQyWlpSNFJ6bzZxMnRWdUNDSE9qcDlaYVhVRk1jNk9wVmRCY0FIaHpvNnMza1ZnQlFIT2pxVjJPWDBGSWM2T3J5YTlmUUd4em82c1htVnlFbAAA"},"http_status":200,"sha256":"75d57ba406356f2a0ac726112f39e6f116f777f38d15252ac8115a2425a34ef7","response_bytes":91904}
{"request_id":"request-0172","query_id":"2026-07-31-5m-p2-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:20.439334+00:00","completed_at_utc":"2026-10-17T03:48:21.897362+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501300","queryType":"Latest","limit":20},"raw_count":17,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjng9zWUQcKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNskAIAnEAoABh1M2yQAf9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T2R1cWxkUktCem81ekxPVmdDV0hPam1oK3hhTVdZYzZPYU5HbFpRaFJ6bzUwZXhHM0RmSE9qbmdma1c4VDhjNk9jaVh4dHhqQnpvNTBvVTJ1RnFIT2ptdFJzYlllSWM2T2J6cEJkUmVSem81dnlaMnBDb0hPam10R2xYc0NJYzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qblJCZWJFWW9jNk9hUWVsb2hWQnpvNTA4Q0dzR0wAAA"},"http_status":200,"sha256":"9060e884dfad7d063736ff080349a5b6750cbdb58d9348924950297d9bf76eff","response_bytes":66116}
{"request_id":"request-0173","query_id":"2026-08-31-5m-p1-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:21.899905+00:00","completed_at_utc":"2026-10-17T03:48:22.526205+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788179700","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDQah6WgLYKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNslRAAnEAoABh1M2yVD_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkF0ZjFyUXdCMFF6K09WV3ZHeUhSRFFhaDZXZ0xZZEVNLzNUQlpSdVE9PQAA"},"http_status":200,"sha256":"bdb4e00a4e1b96d68d1fcd370d420d8dcf0e602d4b77e8f27a243637e02b6b04","response_bytes":13133}
{"request_id":"request-0174","query_id":"2026-08-31-5m-p2-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:22.528745+00:00","completed_at_utc":"2026-10-17T03:48:23.112158+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788179700","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDQah6WgLYKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsl2MAnEAoABh1M2yXYv9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkF0ZjFyUXdCMFF6K09WV3ZHeUhSRFFhaDZXZ0xZZEVNLzNUQlpSdVE9PQAA"},"http_status":200,"sha256":"b3253207ecb4b7227c137beb4f1b43cc01c835d60dbf3814f3d608b5c9327f1b","response_bytes":13133}
{"request_id":"request-0175","query_id":"2026-09-30-5m-p1-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:23.114242+00:00","completed_at_utc":"2026-10-17T03:48:24.063195+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790771700","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdv91gaIcAKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsmlQAnEAoABh1M2yaU_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMitRZTVwQXJCMDNiODhHbXNHckhUZHY5MWdhSWNBZE4yL1N2Sm9ocHc9PQAA"},"http_status":200,"sha256":"c4eb83cb62f9eb2e44e7c64189b1812bae28c947662b87caf8dd2a63396f148f","response_bytes":16507}
{"request_id":"request-0176","query_id":"2026-09-30-5m-p2-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:24.065429+00:00","completed_at_utc":"2026-10-17T03:48:24.742438+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790771700","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdv91gaIcAKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsnQEAnEAoABh1M2ydAP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMitRZTVwQXJCMDNiODhHbXNHckhUZHY5MWdhSWNBZE4yL1N2Sm9ocHc9PQAA"},"http_status":200,"sha256":"f153fbf3620bc52f909f82259be93793102fb71f24470e8a945009563694161f","response_bytes":16507}
{"request_id":"request-0177","query_id":"2026-07-31-5m-p1-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:24.744544+00:00","completed_at_utc":"2026-10-17T03:48:25.326140+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501300","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjng9zWUQcKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsfg8AnEAoABh1M2x-Dv9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T2R1cWxkUktCem81ekxPVmdDV0hPam1oK3hhTVdZYzZPYU5HbFpRaFJ6bzUwZXhHM0RmSE9qbmdma1c4VDhjNk9jaVh4dHhqQnpvNTBvVTJ1RnFIT2ptdFJzYlllSWM2T2J6cEJkUmVSem81dnlaMnBDb0hPam10R2xYc0NJYzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qblJCZWJFWW9jNk9hUWVsb2hWQnpvNTA4Q0dzR0wAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0178","query_id":"2026-07-31-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:25.328988+00:00","completed_at_utc":"2026-10-17T03:48:26.760412+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785502200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OmW5pZA9wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNshHEAnEAoABh1M2yEcP9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPbXYrZHB4WkJ6bzZydmFsakNFSE9qcUFmVldjUThjNk9yY0hKY3c2eHpvNlpibWxrRDNIT2pxdmpuYllQa2M2T3FqU1plUVdoem82dVF3MThBbEhPanErc0xib1dVYzZPbzQyWlpSNFJ6bzZxMnRWdUNDSE9qcDlaYVhVRk1jNk9wVmRCY0FIaHpvNnMza1ZnQlFIT2pxVjJPWDBGSWM2T3J5YTlmUUd4em82c1htVnlFbAAA"},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNshHEAnEAoABh1M2yEcP7HgCwAHAAABUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCMGM2T3NNNEJzaEh4em82VmovMnZGekhPanFBZlZXY1E4YzZPcmNISmN3Nnh6bzZOYUJtaEVlSE9qcW8wbVhrRm9jNk9ya01OZkFKUnpvNnEydFZ1Q0NIT2pwOVphWFVGTWM2T3J5YTlmUUd4em82c1htVnlFbEhPanA5dGZXUUpVYzZPalpSNWJoZlJ6bzZ1VjAyN0JuSE9qcHIvbmFjV1FjNk9xNzJwWXdoQnpvNk9DYzI5Q3dIT2pwbHVhV1FQY2M2T3ErT2R0ZytSem82ampabGxIaEhPanErc0xib1dVYzZPanIyQnV4R0J6bzZsVjBGd0FlSE9qbzQ2S2IwWndjNk9yTjVGWUFVQnpvNlRZSjI3Q0FIT2pwSUV1VzhUUWM2T3BYWTVmUVVoem82Ujd5bWpHNgAA"},"http_status":200,"sha256":"545c0f80d9da6c46fda0fd86ae08658e364bd0ef40c88f6319cc3cd7b0dc2b33","response_bytes":52946}
{"request_id":"request-0179","query_id":"2026-07-31-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:26.762179+00:00","completed_at_utc":"2026-10-17T03:48:28.193390+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785502200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OmW5pZA9wAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsilwAnEAoABh1M2yKW_9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPbXYrZHB4WkJ6bzZydmFsakNFSE9qcUFmVldjUThjNk9yY0hKY3c2eHpvNlpibWxrRDNIT2pxdmpuYllQa2M2T3FqU1plUVdoem82dVF3MThBbEhPanErc0xib1dVYzZPbzQyWlpSNFJ6bzZxMnRWdUNDSE9qcDlaYVhVRk1jNk9wVmRCY0FIaHpvNnMza1ZnQlFIT2pxVjJPWDBGSWM2T3J5YTlmUUd4em82c1htVnlFbAAA"},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNsilwAnEAoABh1M2yKW_7HgCwAHAAABUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCMGM2T3NNNEJzaEh4em82VmovMnZGekhPanFBZlZXY1E4YzZPcmNISmN3Nnh6bzZOYUJtaEVlSE9qcW8wbVhrRm9jNk9ya01OZkFKUnpvNnEydFZ1Q0NIT2pwOVphWFVGTWM2T3J5YTlmUUd4em82c1htVnlFbEhPanA5dGZXUUpVYzZPalpSNWJoZlJ6bzZ1VjAyN0JuSE9qcHIvbmFjV1FjNk9xNzJwWXdoQnpvNk9DYzI5Q3dIT2pwbHVhV1FQY2M2T3ErT2R0ZytSem82ampabGxIaEhPanErc0xib1dVYzZPanIyQnV4R0J6bzZsVjBGd0FlSE9qbzQ2S2IwWndjNk9yTjVGWUFVQnpvNlRZSjI3Q0FIT2pwSUV1VzhUUWM2T3BYWTVmUVVoem82Ujd5bWpHNgAA"},"http_status":200,"sha256":"cd84e8a1983024741f81a86eabd95cd29d12a704c8abd68289a15dcaad143b74","response_bytes":52946}
{"request_id":"request-0180","query_id":"2026-07-31-5m-p2-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:28.195367+00:00","completed_at_utc":"2026-10-17T03:48:28.667277+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501000 until_time:1785501300","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjng9zWUQcKAAIc6OaH7FoxZgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNskAIAnEAoABh1M2yQAf9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T2R1cWxkUktCem81ekxPVmdDV0hPam1oK3hhTVdZYzZPYU5HbFpRaFJ6bzUwZXhHM0RmSE9qbmdma1c4VDhjNk9jaVh4dHhqQnpvNTBvVTJ1RnFIT2ptdFJzYlllSWM2T2J6cEJkUmVSem81dnlaMnBDb0hPam10R2xYc0NJYzZPZUQzTlpSQnh6bzV2NEpGNUVQSE9qblJCZWJFWW9jNk9hUWVsb2hWQnpvNTA4Q0dzR0wAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0181","query_id":"2026-08-31-5m-p1-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:28.670890+00:00","completed_at_utc":"2026-10-17T03:48:29.260580+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788179700","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDQah6WgLYKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNslRAAnEAoABh1M2yVD_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkF0ZjFyUXdCMFF6K09WV3ZHeUhSRFFhaDZXZ0xZZEVNLzNUQlpSdVE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0182","query_id":"2026-08-31-5m-p2-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:29.262322+00:00","completed_at_utc":"2026-10-17T03:48:29.714263+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179400 until_time:1788179700","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDQah6WgLYKAAIdEM_jlVrxsgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsl2MAnEAoABh1M2yXYv9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkF0ZjFyUXdCMFF6K09WV3ZHeUhSRFFhaDZXZ0xZZEVNLzNUQlpSdVE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0183","query_id":"2026-09-30-5m-p1-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:29.716209+00:00","completed_at_utc":"2026-10-17T03:48:30.240676+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790771700","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdv91gaIcAKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsmlQAnEAoABh1M2yaU_9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMitRZTVwQXJCMDNiODhHbXNHckhUZHY5MWdhSWNBZE4yL1N2Sm9ocHc9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0184","query_id":"2026-09-30-5m-p2-w06","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:30.243503+00:00","completed_at_utc":"2026-10-17T03:48:30.600533+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771400 until_time:1790771700","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdv91gaIcAKAAIdN2-Qe5pArAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsnQEAnEAoABh1M2ydAP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWROMitRZTVwQXJCMDNiODhHbXNHckhUZHY5MWdhSWNBZE4yL1N2Sm9ocHc9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0185","query_id":"2026-07-31-5m-p1-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:30.604365+00:00","completed_at_utc":"2026-10-17T03:48:32.217591+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501300 until_time:1785501600","queryType":"Latest","limit":20},"raw_count":13,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OeynNcg7gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsuDcAnEAoABh1M2y4Nv9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qb2tURmJRZjhjNk9oWkE1ZkFUaHpvNkc1Z0Z4QTZIT2pvbVRZV0lQd2M2T2V5bk5jZzdoem81OERKMjBIZkhPam9JWitiWUw4YzZPaHBMcHNSeFE9PQAA"},"http_status":200,"sha256":"7829df0cc53d6e9218d04b6f4874dbe0a94f108526226f204b514e7887cd18b6","response_bytes":77245}
{"request_id":"request-0186","query_id":"2026-07-31-10m-p1-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:32.219382+00:00","completed_at_utc":"2026-10-17T03:48:33.131834+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785502200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNshHEAnEAoABh1M2yEcP7HgCwAHAAABUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCMGM2T3NNNEJzaEh4em82VmovMnZGekhPanFBZlZXY1E4YzZPcmNISmN3Nnh6bzZOYUJtaEVlSE9qcW8wbVhrRm9jNk9ya01OZkFKUnpvNnEydFZ1Q0NIT2pwOVphWFVGTWM2T3J5YTlmUUd4em82c1htVnlFbEhPanA5dGZXUUpVYzZPalpSNWJoZlJ6bzZ1VjAyN0JuSE9qcHIvbmFjV1FjNk9xNzJwWXdoQnpvNk9DYzI5Q3dIT2pwbHVhV1FQY2M2T3ErT2R0ZytSem82ampabGxIaEhPanErc0xib1dVYzZPanIyQnV4R0J6bzZsVjBGd0FlSE9qbzQ2S2IwWndjNk9yTjVGWUFVQnpvNlRZSjI3Q0FIT2pwSUV1VzhUUWM2T3BYWTVmUVVoem82Ujd5bWpHNgAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0187","query_id":"2026-07-31-10m-p2-w04","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:33.139122+00:00","completed_at_utc":"2026-10-17T03:48:34.008767+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785502200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNsilwAnEAoABh1M2yKW_7HgCwAHAAABUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCMGM2T3NNNEJzaEh4em82VmovMnZGekhPanFBZlZXY1E4YzZPcmNISmN3Nnh6bzZOYUJtaEVlSE9qcW8wbVhrRm9jNk9ya01OZkFKUnpvNnEydFZ1Q0NIT2pwOVphWFVGTWM2T3J5YTlmUUd4em82c1htVnlFbEhPanA5dGZXUUpVYzZPalpSNWJoZlJ6bzZ1VjAyN0JuSE9qcHIvbmFjV1FjNk9xNzJwWXdoQnpvNk9DYzI5Q3dIT2pwbHVhV1FQY2M2T3ErT2R0ZytSem82ampabGxIaEhPanErc0xib1dVYzZPanIyQnV4R0J6bzZsVjBGd0FlSE9qbzQ2S2IwWndjNk9yTjVGWUFVQnpvNlRZSjI3Q0FIT2pwSUV1VzhUUWM2T3BYWTVmUVVoem82Ujd5bWpHNgAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0188","query_id":"2026-07-31-5m-p2-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:34.011762+00:00","completed_at_utc":"2026-10-17T03:48:35.000734+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501300 until_time:1785501600","queryType":"Latest","limit":20},"raw_count":13,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OeynNcg7gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsxBsAnEAoABh1M2zEGv9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qb2tURmJRZjhjNk9oWkE1ZkFUaHpvNkc1Z0Z4QTZIT2pvbVRZV0lQd2M2T2V5bk5jZzdoem81OERKMjBIZkhPam9JWitiWUw4YzZPaHBMcHNSeFE9PQAA"},"http_status":200,"sha256":"b2148f7d3ff9b913893944e7f6b8c129293fab8e2db611d5f485a8b33941361c","response_bytes":77255}
{"request_id":"request-0189","query_id":"2026-08-31-5m-p1-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:35.002328+00:00","completed_at_utc":"2026-10-17T03:48:36.153690+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179700 until_time:1788180000","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdENEezVYg4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsyZUAnEAoABh1M2zJlP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkcxQ3hzd3dSMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVORWV6VllnNFE9PQAA"},"http_status":200,"sha256":"d06200358f23c8b49464b68add4de7fdff71d2fc8f0566caa3f0863d5f618a30","response_bytes":26832}
{"request_id":"request-0190","query_id":"2026-08-31-5m-p2-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:36.156162+00:00","completed_at_utc":"2026-10-17T03:48:36.815479+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179700 until_time:1788180000","queryType":"Latest","limit":20},"raw_count":4,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdENEezVYg4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNszEoAnEAoABh1M2zMSf9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkcxQ3hzd3dSMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVORWV6VllnNFE9PQAA"},"http_status":200,"sha256":"96f26114de6beea65e3bda34da65d341f573faa8cc510398a7d20cf487464539","response_bytes":26832}
{"request_id":"request-0191","query_id":"2026-09-30-5m-p1-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:36.817735+00:00","completed_at_utc":"2026-10-17T03:48:38.114673+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771700 until_time:1790772000","queryType":"Latest","limit":20},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN3DDB9sBGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs0KEAnEAoABh1M2zQoP9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROM0U0WFZjZ094MDNjYmVWbTVIS0hUZHc5QnFYY1RVZE4zR3Z6OXJBaGgwM2NNTUgyd0VaSFRkeFVsYmFVUzhkTjNEcTVsY2h3UjAzY2JtY200Q1lIVGR4RGtGYTBWRT0AAA"},"http_status":200,"sha256":"0f478991d5ce0bbe6fcf621e9b3ecfd26ba6529088d788d865f5e54f33b5d042","response_bytes":43477}
{"request_id":"request-0192","query_id":"2026-09-30-5m-p2-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:38.117774+00:00","completed_at_utc":"2026-10-17T03:48:39.495899+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771700 until_time:1790772000","queryType":"Latest","limit":20},"raw_count":9,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN3DDB9sBGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs1RIAnEAoABh1M2zVEf9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROM0U0WFZjZ094MDNjYmVWbTVIS0hUZHc5QnFYY1RVZE4zR3Z6OXJBaGgwM2NNTUgyd0VaSFRkeFVsYmFVUzhkTjNEcTVsY2h3UjAzY2JtY200Q1lIVGR4RGtGYTBWRT0AAA"},"http_status":200,"sha256":"46c5477dc2151d35df4f7b6250e42915290b63cec3738fbffb4af17354e3d835","response_bytes":43477}
{"request_id":"request-0193","query_id":"2026-07-31-5m-p1-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:39.497199+00:00","completed_at_utc":"2026-10-17T03:48:40.358047+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501300 until_time:1785501600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OeynNcg7gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsuDcAnEAoABh1M2y4Nv9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qb2tURmJRZjhjNk9oWkE1ZkFUaHpvNkc1Z0Z4QTZIT2pvbVRZV0lQd2M2T2V5bk5jZzdoem81OERKMjBIZkhPam9JWitiWUw4YzZPaHBMcHNSeFE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0194","query_id":"2026-07-31-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:40.361146+00:00","completed_at_utc":"2026-10-17T03:48:41.792418+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs3oMAnEAoABh1M2zegv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"http_status":200,"sha256":"6463dd37452ba2106c9aeb090da118dbb29351b56396e8996146b52bfb4af987","response_bytes":82635}
{"request_id":"request-0195","query_id":"2026-07-31-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:41.793923+00:00","completed_at_utc":"2026-10-17T03:48:42.867166+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs4v0AnEAoABh1M2zi_P9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"http_status":200,"sha256":"5a69357e6328ce1e1688bda30e1d7c931f0672aeeed6c9b8dd2b744d9b1f7db5","response_bytes":82635}
{"request_id":"request-0196","query_id":"2026-07-31-5m-p2-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:42.868175+00:00","completed_at_utc":"2026-10-17T03:48:43.346382+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501300 until_time:1785501600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjops1XwQYKAAIc6OeynNcg7gAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsxBsAnEAoABh1M2zEGv9jwCwAHAAAAqEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBMGM2T2lGMUZzUWp4em82QlJobXpISUhPam51NVRYQUZzYzZPaEdCeG9RdEJ6bzZLYk5WOEVHSE9qb2tURmJRZjhjNk9oWkE1ZkFUaHpvNkc1Z0Z4QTZIT2pvbVRZV0lQd2M2T2V5bk5jZzdoem81OERKMjBIZkhPam9JWitiWUw4YzZPaHBMcHNSeFE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0197","query_id":"2026-08-31-5m-p1-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:43.348755+00:00","completed_at_utc":"2026-10-17T03:48:44.163910+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179700 until_time:1788180000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdENEezVYg4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNsyZUAnEAoABh1M2zJlP9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkcxQ3hzd3dSMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVORWV6VllnNFE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0198","query_id":"2026-08-31-5m-p2-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:44.165985+00:00","completed_at_utc":"2026-10-17T03:48:44.621465+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788179700 until_time:1788180000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDR9IcXgbsKAAIdENEezVYg4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNszEoAnEAoABh1M2zMSf9jwCwAHAAAASEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBUWRFTkcxQ3hzd3dSMFEwZlNIRjRHN0hSRFJyWTJYZ2RrZEVORWV6VllnNFE9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0199","query_id":"2026-09-30-5m-p1-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:44.624893+00:00","completed_at_utc":"2026-10-17T03:48:45.124121+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771700 until_time:1790772000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN3DDB9sBGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs0KEAnEAoABh1M2zQoP9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROM0U0WFZjZ094MDNjYmVWbTVIS0hUZHc5QnFYY1RVZE4zR3Z6OXJBaGgwM2NNTUgyd0VaSFRkeFVsYmFVUzhkTjNEcTVsY2h3UjAzY2JtY200Q1lIVGR4RGtGYTBWRT0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0200","query_id":"2026-09-30-5m-p2-w07","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:45.126958+00:00","completed_at_utc":"2026-10-17T03:48:45.528802+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790771700 until_time:1790772000","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdxuZybgJgKAAIdN3DDB9sBGQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs1RIAnEAoABh1M2zVEf9jwCwAHAAAAfEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBa2ROM0U0WFZjZ094MDNjYmVWbTVIS0hUZHc5QnFYY1RVZE4zR3Z6OXJBaGgwM2NNTUgyd0VaSFRkeFVsYmFVUzhkTjNEcTVsY2h3UjAzY2JtY200Q1lIVGR4RGtGYTBWRT0AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0201","query_id":"2026-07-31-5m-p1-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:45.531625+00:00","completed_at_utc":"2026-10-17T03:48:47.096136+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785501900","queryType":"Latest","limit":20},"raw_count":12,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjp9ZaXUFMKAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs8oMAnEAoABh1M2zygv9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T2paUjViaGZSem82YS81Mm5Ga0hPanBXUC9hOFhNYzZPbVc1cFpBOXh6bzZPQ2MyOUN3SE9qbzFvR2FFUjRjNk9qcjJCdXhHQnpvNmZXV2wxQlRIT2pvNDZLYjBad2M2T2tnUzVieE5Cem82VFlKMjdDQUhPanBIdkthTWJvPQAA"},"http_status":200,"sha256":"f3015006ac51c63ae70b537b4c47936184ca3cba503a6de1f721d3653f3b5fd3","response_bytes":63512}
{"request_id":"request-0202","query_id":"2026-07-31-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:47.097921+00:00","completed_at_utc":"2026-10-17T03:48:48.286310+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs3oMAnEAoABh1M2zegv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"raw_count":19,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNs3oMAnEAoABh1M2zegv7HgCwAHAAABvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDY2M2T3lqYzVhQjFSem82NThIVzRDUEhPanNTTVZhY2VZYzZPMG54ZFpoL2h6bzdLeFpHbEZ4SE9qczZUYWFVZGNjNk9zaU9KZGhGaHpvN05wYzFzRGFIT2pzUmk3WG9Fb2M2T3g4bUpvQi94em82NG94bXNCT0hPanJtWVJYSUNVYzZPdjlDTnJnbnh6bzdFcHNXZ0hiSE9qcytMMFh3ZTRjNk93ekV4YUFpeHpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem82NW94VmlGTUhPanNEcGNYa0FjYzZPeTF0dGJ4d1J6bzY4MVdXMEV6SE9qc0l0Zlc0TVFjNk93V1pGdFFZUnpvN1BBN21yRmRIT2p0SGFtYUliVWM2T3p6dmh0d1BSem82NGRhbHNEbEhPanJNc2lXQWNVYzZPczBvbFl3eHh6bzY2TmpsNUFxSE9qc3JybVdNUTRjNk8wZDlKcmhXUnpvNi8yemxtQ2lIT2p0Uy9WWElYZ2M2T3hQSkJkUmhCem83RWxZbXVFQ0hPanJ5ZUNhMFkwPQAA"},"http_status":200,"sha256":"58b8bdca9a0316e0dd89a7b636a780dec273463428d0ad0fa2c574c265e012a6","response_bytes":94243}
{"request_id":"request-0203","query_id":"2026-07-31-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:48.287553+00:00","completed_at_utc":"2026-10-17T03:48:49.714629+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs4v0AnEAoABh1M2zi_P9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"raw_count":19,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNs4v0AnEAoABh1M2zi_P7HgCwAHAAABvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDY2M2T3lqYzVhQjFSem82NThIVzRDUEhPanNTTVZhY2VZYzZPMG54ZFpoL2h6bzdLeFpHbEZ4SE9qczZUYWFVZGNjNk9zaU9KZGhGaHpvN05wYzFzRGFIT2pzUmk3WG9Fb2M2T3g4bUpvQi94em82NG94bXNCT0hPanJtWVJYSUNVYzZPdjlDTnJnbnh6bzdFcHNXZ0hiSE9qcytMMFh3ZTRjNk93ekV4YUFpeHpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem82NW94VmlGTUhPanNEcGNYa0FjYzZPeTF0dGJ4d1J6bzY4MVdXMEV6SE9qc0l0Zlc0TVFjNk93V1pGdFFZUnpvN1BBN21yRmRIT2p0SGFtYUliVWM2T3p6dmh0d1BSem82NGRhbHNEbEhPanJNc2lXQWNVYzZPczBvbFl3eHh6bzY2TmpsNUFxSE9qc3JybVdNUTRjNk8wZDlKcmhXUnpvNi8yemxtQ2lIT2p0Uy9WWElYZ2M2T3hQSkJkUmhCem83RWxZbXVFQ0hPanJ5ZUNhMFkwPQAA"},"http_status":200,"sha256":"be7d6bc9caa3f7b9a2af2c1a962288487b78730d3f8835b5d58530b8f1db595f","response_bytes":94243}
{"request_id":"request-0204","query_id":"2026-07-31-5m-p2-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:49.716367+00:00","completed_at_utc":"2026-10-17T03:48:51.223819+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785501900","queryType":"Latest","limit":20},"raw_count":12,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjp9ZaXUFMKAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtAmsAnEAoABh1M20Cav9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T2paUjViaGZSem82YS81Mm5Ga0hPanBXUC9hOFhNYzZPbVc1cFpBOXh6bzZPQ2MyOUN3SE9qbzFvR2FFUjRjNk9qcjJCdXhHQnpvNmZXV2wxQlRIT2pvNDZLYjBad2M2T2tnUzVieE5Cem82VFlKMjdDQUhPanBIdkthTWJvPQAA"},"http_status":200,"sha256":"34624a8b4083ffeb4c61de0039450d740bab1c864a0feba0688806b9e57111b0","response_bytes":63512}
{"request_id":"request-0205","query_id":"2026-08-31-5m-p1-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:51.226106+00:00","completed_at_utc":"2026-10-17T03:48:52.547856+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180300","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDTO_qWIY8KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtCJEAnEAoABh1M20IkP9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWRFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFNtTHpXc2NVZEVOSlhNOXN4bFIwUTBrUWpXbURnAAA"},"http_status":200,"sha256":"1909fb1f7e78ac040b82e8cc94a14694269a6452b90027cba5d3e2f254f1f8b5","response_bytes":18165}
{"request_id":"request-0206","query_id":"2026-08-31-5m-p2-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:52.550104+00:00","completed_at_utc":"2026-10-17T03:48:53.556574+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180300","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDTO_qWIY8KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtDTAAnEAoABh1M20NL_9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWRFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFNtTHpXc2NVZEVOSlhNOXN4bFIwUTBrUWpXbURnAAA"},"http_status":200,"sha256":"3fb3784f48d39e50e72a888ac894c68b8201561a1628109f3bb8e3d1ea2c1b07","response_bytes":18165}
{"request_id":"request-0207","query_id":"2026-09-30-5m-p1-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:53.559057+00:00","completed_at_utc":"2026-10-17T03:48:54.360601+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772300","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdyZH8boRgKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtESMAnEAoABh1M20RIv9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROM0prZnh1aEdCMDNjZ2MwMjRDdwAA"},"http_status":200,"sha256":"27dafeb5e6c6f49b900eb40ec47fe52fe9b660e56f07ba7961df200a5037addd","response_bytes":10534}
{"request_id":"request-0208","query_id":"2026-09-30-5m-p2-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:54.363415+00:00","completed_at_utc":"2026-10-17T03:48:54.886314+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772300","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdyZH8boRgKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtE4EAnEAoABh1M20TgP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROM0prZnh1aEdCMDNjZ2MwMjRDdwAA"},"http_status":200,"sha256":"6ef1d997c199c60a93f0273d6dad2d29d01cf087c649ecd044931fbe3a0e6c6f","response_bytes":10534}
{"request_id":"request-0209","query_id":"2026-07-31-5m-p1-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:54.888374+00:00","completed_at_utc":"2026-10-17T03:48:55.407741+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785501900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjp9ZaXUFMKAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNs8oMAnEAoABh1M2zygv9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T2paUjViaGZSem82YS81Mm5Ga0hPanBXUC9hOFhNYzZPbVc1cFpBOXh6bzZPQ2MyOUN3SE9qbzFvR2FFUjRjNk9qcjJCdXhHQnpvNmZXV2wxQlRIT2pvNDZLYjBad2M2T2tnUzVieE5Cem82VFlKMjdDQUhPanBIdkthTWJvPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0210","query_id":"2026-07-31-10m-p1-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:55.410905+00:00","completed_at_utc":"2026-10-17T03:48:55.935380+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNs3oMAnEAoABh1M2zegv7HgCwAHAAABvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDY2M2T3lqYzVhQjFSem82NThIVzRDUEhPanNTTVZhY2VZYzZPMG54ZFpoL2h6bzdLeFpHbEZ4SE9qczZUYWFVZGNjNk9zaU9KZGhGaHpvN05wYzFzRGFIT2pzUmk3WG9Fb2M2T3g4bUpvQi94em82NG94bXNCT0hPanJtWVJYSUNVYzZPdjlDTnJnbnh6bzdFcHNXZ0hiSE9qcytMMFh3ZTRjNk93ekV4YUFpeHpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem82NW94VmlGTUhPanNEcGNYa0FjYzZPeTF0dGJ4d1J6bzY4MVdXMEV6SE9qc0l0Zlc0TVFjNk93V1pGdFFZUnpvN1BBN21yRmRIT2p0SGFtYUliVWM2T3p6dmh0d1BSem82NGRhbHNEbEhPanJNc2lXQWNVYzZPczBvbFl3eHh6bzY2TmpsNUFxSE9qc3JybVdNUTRjNk8wZDlKcmhXUnpvNi8yemxtQ2lIT2p0Uy9WWElYZ2M2T3hQSkJkUmhCem83RWxZbXVFQ0hPanJ5ZUNhMFkwPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0211","query_id":"2026-07-31-10m-p2-w05","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:55.937455+00:00","completed_at_utc":"2026-10-17T03:48:56.635829+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNs4v0AnEAoABh1M2zi_P7HgCwAHAAABvEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFDY2M2T3lqYzVhQjFSem82NThIVzRDUEhPanNTTVZhY2VZYzZPMG54ZFpoL2h6bzdLeFpHbEZ4SE9qczZUYWFVZGNjNk9zaU9KZGhGaHpvN05wYzFzRGFIT2pzUmk3WG9Fb2M2T3g4bUpvQi94em82NG94bXNCT0hPanJtWVJYSUNVYzZPdjlDTnJnbnh6bzdFcHNXZ0hiSE9qcytMMFh3ZTRjNk93ekV4YUFpeHpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem82NW94VmlGTUhPanNEcGNYa0FjYzZPeTF0dGJ4d1J6bzY4MVdXMEV6SE9qc0l0Zlc0TVFjNk93V1pGdFFZUnpvN1BBN21yRmRIT2p0SGFtYUliVWM2T3p6dmh0d1BSem82NGRhbHNEbEhPanJNc2lXQWNVYzZPczBvbFl3eHh6bzY2TmpsNUFxSE9qc3JybVdNUTRjNk8wZDlKcmhXUnpvNi8yemxtQ2lIT2p0Uy9WWElYZ2M2T3hQSkJkUmhCem83RWxZbXVFQ0hPanJ5ZUNhMFkwPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0212","query_id":"2026-07-31-5m-p2-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:56.638288+00:00","completed_at_utc":"2026-10-17T03:48:57.375760+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501600 until_time:1785501900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjp9ZaXUFMKAAIc6OjWgZoRHgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtAmsAnEAoABh1M20Cav9jwCwAHAAAAnEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBd2M2T2paUjViaGZSem82YS81Mm5Ga0hPanBXUC9hOFhNYzZPbVc1cFpBOXh6bzZPQ2MyOUN3SE9qbzFvR2FFUjRjNk9qcjJCdXhHQnpvNmZXV2wxQlRIT2pvNDZLYjBad2M2T2tnUzVieE5Cem82VFlKMjdDQUhPanBIdkthTWJvPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0213","query_id":"2026-08-31-5m-p1-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:57.378798+00:00","completed_at_utc":"2026-10-17T03:48:58.026207+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180300","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDTO_qWIY8KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtCJEAnEAoABh1M20IkP9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWRFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFNtTHpXc2NVZEVOSlhNOXN4bFIwUTBrUWpXbURnAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0214","query_id":"2026-08-31-5m-p2-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:58.028661+00:00","completed_at_utc":"2026-10-17T03:48:58.710882+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180000 until_time:1788180300","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDTO_qWIY8KAAIdENJEI1pg4AAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtDTAAnEAoABh1M20NL_9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWRFTkpGSHRjZ1F4MFEwenY2bGlHUEhSRFNtTHpXc2NVZEVOSlhNOXN4bFIwUTBrUWpXbURnAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0215","query_id":"2026-09-30-5m-p1-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:58.714180+00:00","completed_at_utc":"2026-10-17T03:48:59.185589+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772300","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdyZH8boRgKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtESMAnEAoABh1M20RIv9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROM0prZnh1aEdCMDNjZ2MwMjRDdwAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0216","query_id":"2026-09-30-5m-p2-w08","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:59.188786+00:00","completed_at_utc":"2026-10-17T03:48:59.600941+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772000 until_time:1790772300","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdyZH8boRgKAAIdN3IHNNuAsAAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtE4EAnEAoABh1M20TgP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWROM0prZnh1aEdCMDNjZ2MwMjRDdwAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0217","query_id":"2026-07-31-5m-p1-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:48:59.604603+00:00","completed_at_utc":"2026-10-17T03:49:01.364376+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501900 until_time:1785502200","queryType":"Latest","limit":20},"raw_count":17,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6On219ZAlQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtKlAAnEAoABh1M20qT_9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPcTcycFl3aEJ6bzZnSDFWbkVQSE9qcTNCeVhNT3NjNk9xK09kdGcrUnpvNnFOSmw1QmFIT2pxNUREWHdDVWM2T3I2d3R1aFpSem82ampabGxIaEhPanFyYTFXNElJYzZPcFZkQmNBSGh6bzZzM2tWZ0JRSE9qcVYyT1gwRkljNk9yeWE5ZlFHeHpvNnNYbVZ5RWwAAA"},"http_status":200,"sha256":"a5f1717faa1bd91f58c15a3e5a83cc0593e2514e170276bc30e728a1e4d426cf","response_bytes":81056}
{"request_id":"request-0218","query_id":"2026-07-31-5m-p2-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:01.367943+00:00","completed_at_utc":"2026-10-17T03:49:02.365429+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501900 until_time:1785502200","queryType":"Latest","limit":20},"raw_count":17,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6On219ZAlQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtLwYAnEAoABh1M20vBf9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPcTcycFl3aEJ6bzZnSDFWbkVQSE9qcTNCeVhNT3NjNk9xK09kdGcrUnpvNnFOSmw1QmFIT2pxNUREWHdDVWM2T3I2d3R1aFpSem82ampabGxIaEhPanFyYTFXNElJYzZPcFZkQmNBSGh6bzZzM2tWZ0JRSE9qcVYyT1gwRkljNk9yeWE5ZlFHeHpvNnNYbVZ5RWwAAA"},"http_status":200,"sha256":"9b4190b4cfab064cd0619cd10b5c346a3c66d5c2ccaaf4e211b1f5a187d3d002","response_bytes":81058}
{"request_id":"request-0219","query_id":"2026-08-31-5m-p1-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:02.367227+00:00","completed_at_utc":"2026-10-17T03:49:03.008653+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180300 until_time:1788180600","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENNsadsw-QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtMxYAnEAoABh1M20zFf9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlB2bDFkZ0hSMFEwMnhwMnpENQAA"},"http_status":200,"sha256":"c8fa2be486543b83040623d7abcde499475e96425cdf12e9274a47cae883aa34","response_bytes":11188}
{"request_id":"request-0220","query_id":"2026-08-31-5m-p2-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:03.011605+00:00","completed_at_utc":"2026-10-17T03:49:03.633333+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180300 until_time:1788180600","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENNsadsw-QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtNbMAnEAoABh1M201sv9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlB2bDFkZ0hSMFEwMnhwMnpENQAA"},"http_status":200,"sha256":"b68d05328bb17aa40c9b84f7430300ab168dd55b4c66eb50cec1498dece38c29","response_bytes":11188}
{"request_id":"request-0221","query_id":"2026-09-30-5m-p1-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:03.635839+00:00","completed_at_utc":"2026-10-17T03:49:04.846739+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772300 until_time:1790772600","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3L0JFcBUgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtOSUAnEAoABh1M205JP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM0w1WmRxd1RoMDNjK3JxbXRCbEhUZHk5Q1JYQVZJPQAA"},"http_status":200,"sha256":"8bd1aa4c0226c157cf7883d00acdd2b757ff0b04bd0a8c7867407314ba7c905f","response_bytes":18106}
{"request_id":"request-0222","query_id":"2026-09-30-5m-p2-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:04.848994+00:00","completed_at_utc":"2026-10-17T03:49:05.621225+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772300 until_time:1790772600","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3L0JFcBUgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtPMQAnEAoABh1M208w_9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM0w1WmRxd1RoMDNjK3JxbXRCbEhUZHk5Q1JYQVZJPQAA"},"http_status":200,"sha256":"79213012d45ea3f815cb7903e8b1c1229912592e1716cc64a7bd75b0488ba69f","response_bytes":18106}
{"request_id":"request-0223","query_id":"2026-07-31-5m-p1-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:05.624862+00:00","completed_at_utc":"2026-10-17T03:49:06.108027+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501900 until_time:1785502200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6On219ZAlQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtKlAAnEAoABh1M20qT_9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPcTcycFl3aEJ6bzZnSDFWbkVQSE9qcTNCeVhNT3NjNk9xK09kdGcrUnpvNnFOSmw1QmFIT2pxNUREWHdDVWM2T3I2d3R1aFpSem82ampabGxIaEhPanFyYTFXNElJYzZPcFZkQmNBSGh6bzZzM2tWZ0JRSE9qcVYyT1gwRkljNk9yeWE5ZlFHeHpvNnNYbVZ5RWwAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0224","query_id":"2026-07-31-5m-p2-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:06.111633+00:00","completed_at_utc":"2026-10-17T03:49:06.466720+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785501900 until_time:1785502200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjrDOAbIR8KAAIc6On219ZAlQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtLwYAnEAoABh1M20vBf9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T24yMTlaQWxSem82d3pnR3lFZkhPanE1WFRic0djYzZPcTcycFl3aEJ6bzZnSDFWbkVQSE9qcTNCeVhNT3NjNk9xK09kdGcrUnpvNnFOSmw1QmFIT2pxNUREWHdDVWM2T3I2d3R1aFpSem82ampabGxIaEhPanFyYTFXNElJYzZPcFZkQmNBSGh6bzZzM2tWZ0JRSE9qcVYyT1gwRkljNk9yeWE5ZlFHeHpvNnNYbVZ5RWwAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0225","query_id":"2026-08-31-5m-p1-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:06.470020+00:00","completed_at_utc":"2026-10-17T03:49:06.941014+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180300 until_time:1788180600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENNsadsw-QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtMxYAnEAoABh1M20zFf9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlB2bDFkZ0hSMFEwMnhwMnpENQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0226","query_id":"2026-08-31-5m-p2-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:06.944146+00:00","completed_at_utc":"2026-10-17T03:49:07.309370+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180300 until_time:1788180600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDT75dXYB0KAAIdENNsadsw-QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtNbMAnEAoABh1M201sv9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlB2bDFkZ0hSMFEwMnhwMnpENQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0227","query_id":"2026-09-30-5m-p1-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:07.312424+00:00","completed_at_utc":"2026-10-17T03:49:08.301680+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772300 until_time:1790772600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3L0JFcBUgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtOSUAnEAoABh1M205JP9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM0w1WmRxd1RoMDNjK3JxbXRCbEhUZHk5Q1JYQVZJPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0228","query_id":"2026-09-30-5m-p2-w09","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:08.303455+00:00","completed_at_utc":"2026-10-17T03:49:08.644596+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772300 until_time:1790772600","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTdz6uqa0GUKAAIdN3L0JFcBUgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtPMQAnEAoABh1M208w_9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM0w1WmRxd1RoMDNjK3JxbXRCbEhUZHk5Q1JYQVZJPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0229","query_id":"2026-07-31-5m-p1-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:08.647167+00:00","completed_at_utc":"2026-10-17T03:49:09.810021+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502500","queryType":"Latest","limit":20},"raw_count":17,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjsMxMWgIsKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtTBQAnEAoABh1M21ME_9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T3VmQjF1QWp4em82ODFXVzBFekhPanNGbVJiVUdFYzZPd2kxOWJneEJ6bzY0ZGFsc0RsSE9qck1zaVdBY1VjNk9zMG9sWXd4eHpvNjZOamw1QXFIT2pySWppWFlSWWM2T3VaaEZjZ0pSem82LzJ6bG1DaUhPanIvUWphNEo4YzZPd3pFeGFBaXh6bzY0b3htc0JPSE9qcm1qRldJVXdjNk93T2x4ZVFCeHpvNjhuZ210R04AAA"},"http_status":200,"sha256":"4c7a094113aac4cdb4360b58f136838dadc81d3bbf620fdab87fd7001582c17a","response_bytes":80611}
{"request_id":"request-0230","query_id":"2026-07-31-5m-p2-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:09.811860+00:00","completed_at_utc":"2026-10-17T03:49:11.378860+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502500","queryType":"Latest","limit":20},"raw_count":17,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjsMxMWgIsKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtUV0AnEAoABh1M21RXP9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T3VmQjF1QWp4em82ODFXVzBFekhPanNGbVJiVUdFYzZPd2kxOWJneEJ6bzY0ZGFsc0RsSE9qck1zaVdBY1VjNk9zMG9sWXd4eHpvNjZOamw1QXFIT2pySWppWFlSWWM2T3VaaEZjZ0pSem82LzJ6bG1DaUhPanIvUWphNEo4YzZPd3pFeGFBaXh6bzY0b3htc0JPSE9qcm1qRldJVXdjNk93T2x4ZVFCeHpvNjhuZ210R04AAA"},"http_status":200,"sha256":"a8fb76ce71899096c8e6e30059dafd5c8021d16de06d5659200c81c4f6776620","response_bytes":80611}
{"request_id":"request-0231","query_id":"2026-08-31-5m-p1-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:11.380680+00:00","completed_at_utc":"2026-10-17T03:49:12.424461+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788180900","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDU70RXYTwKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtV3oAnEAoABh1M21Xef9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlRqS1plaFBSMFExTzlFVjJFOAAA"},"http_status":200,"sha256":"f6aeaf00ef60a00cfa05e52c4149c1427a9c19064ecf8eb1e350c1dd385f0e2f","response_bytes":7720}
{"request_id":"request-0232","query_id":"2026-08-31-5m-p2-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:12.427760+00:00","completed_at_utc":"2026-10-17T03:49:13.361084+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788180900","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDU70RXYTwKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtWz0AnEAoABh1M21bPP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlRqS1plaFBSMFExTzlFVjJFOAAA"},"http_status":200,"sha256":"1062082c9510b9c21db7d0351fa8ab9a3ad88d45294adfd1c373f0423bb3612d","response_bytes":7720}
{"request_id":"request-0233","query_id":"2026-09-30-5m-p1-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:13.363652+00:00","completed_at_utc":"2026-10-17T03:49:14.148255+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790772900","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd0X0rWoYAKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtXfIAnEAoABh1M21d8f9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM1FrcU51UTRSMDNkRjlLMXFHQUhUZDBPWUFiY2VvPQAA"},"http_status":200,"sha256":"8257fd76a2529c0fb6fbb4d8564e826307b2eed4a44a836faa83923f9dc6e830","response_bytes":16719}
{"request_id":"request-0234","query_id":"2026-09-30-5m-p2-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:14.151848+00:00","completed_at_utc":"2026-10-17T03:49:15.332702+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790772900","queryType":"Latest","limit":20},"raw_count":3,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd0X0rWoYAKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtYiQAnEAoABh1M21iI_9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM1FrcU51UTRSMDNkRjlLMXFHQUhUZDBPWUFiY2VvPQAA"},"http_status":200,"sha256":"9c04e9c8c95b56d96616f4865cf0bb61fd685799bc2b9ae5b638cb99b70458a7","response_bytes":16719}
{"request_id":"request-0235","query_id":"2026-07-31-5m-p1-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:15.337296+00:00","completed_at_utc":"2026-10-17T03:49:15.854710+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjsMxMWgIsKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtTBQAnEAoABh1M21ME_9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T3VmQjF1QWp4em82ODFXVzBFekhPanNGbVJiVUdFYzZPd2kxOWJneEJ6bzY0ZGFsc0RsSE9qck1zaVdBY1VjNk9zMG9sWXd4eHpvNjZOamw1QXFIT2pySWppWFlSWWM2T3VaaEZjZ0pSem82LzJ6bG1DaUhPanIvUWphNEo4YzZPd3pFeGFBaXh6bzY0b3htc0JPSE9qcm1qRldJVXdjNk93T2x4ZVFCeHpvNjhuZ210R04AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0236","query_id":"2026-07-31-5m-p2-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:15.857764+00:00","completed_at_utc":"2026-10-17T03:49:16.553247+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502200 until_time:1785502500","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjsMxMWgIsKAAIc6OsiOJdhFgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtUV0AnEAoABh1M21RXP9jwCwAHAAAA0EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCRWM2T3VmQjF1QWp4em82ODFXVzBFekhPanNGbVJiVUdFYzZPd2kxOWJneEJ6bzY0ZGFsc0RsSE9qck1zaVdBY1VjNk9zMG9sWXd4eHpvNjZOamw1QXFIT2pySWppWFlSWWM2T3VaaEZjZ0pSem82LzJ6bG1DaUhPanIvUWphNEo4YzZPd3pFeGFBaXh6bzY0b3htc0JPSE9qcm1qRldJVXdjNk93T2x4ZVFCeHpvNjhuZ210R04AAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0237","query_id":"2026-08-31-5m-p1-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:16.556133+00:00","completed_at_utc":"2026-10-17T03:49:17.426818+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788180900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDU70RXYTwKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtV3oAnEAoABh1M21Xef9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlRqS1plaFBSMFExTzlFVjJFOAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0238","query_id":"2026-08-31-5m-p2-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:17.430358+00:00","completed_at_utc":"2026-10-17T03:49:17.807335+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180600 until_time:1788180900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDU70RXYTwKAAIdENTjKZehPQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtWz0AnEAoABh1M21bPP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTlRqS1plaFBSMFExTzlFVjJFOAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0239","query_id":"2026-09-30-5m-p1-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:17.810853+00:00","completed_at_utc":"2026-10-17T03:49:18.760550+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790772900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd0X0rWoYAKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtXfIAnEAoABh1M21d8f9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM1FrcU51UTRSMDNkRjlLMXFHQUhUZDBPWUFiY2VvPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0240","query_id":"2026-09-30-5m-p2-w10","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:18.762679+00:00","completed_at_utc":"2026-10-17T03:49:19.521849+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772600 until_time:1790772900","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd0X0rWoYAKAAIdN3QkqNuQ4QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtYiQAnEAoABh1M21iI_9jwCwAHAAAAPEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBTWROM1FrcU51UTRSMDNkRjlLMXFHQUhUZDBPWUFiY2VvPQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0241","query_id":"2026-07-31-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:19.523848+00:00","completed_at_utc":"2026-10-17T03:49:20.810231+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502500 until_time:1785502800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtdwYAnEAoABh1M213Bf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"http_status":200,"sha256":"e386a7dd306a4e266ee61a7873c637ec179e835b8d13b6c7d4ffd6d8b7b0a41e","response_bytes":82635}
{"request_id":"request-0242","query_id":"2026-07-31-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:20.811940+00:00","completed_at_utc":"2026-10-17T03:49:21.819720+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502500 until_time:1785502800","queryType":"Latest","limit":20},"raw_count":20,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNteysAnEAoABh1M217Kv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"http_status":200,"sha256":"bb1cad1b7a34edb3e252f7a140c0d30f4931a553d501e29dd844fb0a91461b29","response_bytes":82635}
{"request_id":"request-0243","query_id":"2026-08-31-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:21.821896+00:00","completed_at_utc":"2026-10-17T03:49:22.908035+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180900 until_time:1788181200","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENWclxoA_QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtf8EAnEAoABh1M21_wP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTldjbHhvQS9SMFExbUhCRmlIUQAA"},"http_status":200,"sha256":"8095ffdba0a16f3a2a65038023b4736f3f9f7fa777892d58051b60677d0e2565","response_bytes":16616}
{"request_id":"request-0244","query_id":"2026-08-31-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:22.911659+00:00","completed_at_utc":"2026-10-17T03:49:23.603145+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180900 until_time:1788181200","queryType":"Latest","limit":20},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENWclxoA_QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtgwYAnEAoABh1M22DBf9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTldjbHhvQS9SMFExbUhCRmlIUQAA"},"http_status":200,"sha256":"b98b2d70e7945764f2d1acce5f4d5aa84d546f84b2e98646e83da687ac8fb921","response_bytes":16626}
{"request_id":"request-0245","query_id":"2026-09-30-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:23.605144+00:00","completed_at_utc":"2026-10-17T03:49:25.062379+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772900 until_time:1790773200","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3VEcRvQpQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtiPMAnEAoABh1M22I8v9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM1pQS05aUXBCMDNkWk12R2xIZ0hUZDFSSEViMEtVZE4zVnRQaGFoRXgwM2Rpa0RtdUhyAAA"},"http_status":200,"sha256":"b23368237f839724e12b80c1a395224558147c12072e0c64c5be052f9f5c8749","response_bytes":10845}
{"request_id":"request-0246","query_id":"2026-09-30-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:25.064230+00:00","completed_at_utc":"2026-10-17T03:49:25.918297+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772900 until_time:1790773200","queryType":"Latest","limit":20},"raw_count":5,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3VEcRvQpQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtjE0AnEAoABh1M22MTP9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM1pQS05aUXBCMDNkWk12R2xIZ0hUZDFSSEViMEtVZE4zVnRQaGFoRXgwM2Rpa0RtdUhyAAA"},"http_status":200,"sha256":"2dd97db151dc5bfe8d35b819f2883fa5b4a7c9ee0370fb882e87dea3bd1ad97b","response_bytes":10845}
{"request_id":"request-0247","query_id":"2026-07-31-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:25.919809+00:00","completed_at_utc":"2026-10-17T03:49:26.536757+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502500 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtdwYAnEAoABh1M213Bf9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxGLtegSgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNtdwYAnEAoABh1M213Bf7HgCwAHAAABCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCWWM2T3kxdHRieHdSem83S056bG9IVkhPanM4NzRiY0QwYzZPMG54ZFpoL2h6bzdQQTdtckZkSE9qdEhhbWFJYlVjNk95c1dScFJjUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3hHTHRlZ1Noem83SzY1bGpFT0hPanRIZlNhNFZrYzZPeDhtSm9CL3h6bzdLS01HMkdsSE9qdFMvVlhJWGdjNk96NHZSZkI3aHpvN1R6cTJtQ3JIT2p0Q3RvWGNDSWM2T3hQSkJkUmhCem83RXBzV2dIYkhPanNTVmlhNFFJYzZPeEl4VnB4NWc9PQAA"},"http_status":200,"sha256":"fcf979fdb747387525acc4b28b664904983683aa4d29b08f0fd84cee42bad96e","response_bytes":13828}
{"request_id":"request-0248","query_id":"2026-07-31-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:26.538742+00:00","completed_at_utc":"2026-10-17T03:49:27.028514+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502500 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxJWJrhAgAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNteysAnEAoABh1M217Kv9jwCwAHAAAA8EVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCUWM2T3kxdHRieHdSem83S056bG9IVkhPanNyRmthVVhFYzZPendPNXF4WFJ6bzdSMnBtaUcxSE9qdEo4WFdZZjRjNk96enZodHdQUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3l1dVpZeERoem83UjMwbXVGWkhPanNmSmlhQWY4YzZPeEtiRm9CMnh6bzdQaTlGOEh1SE9qdFMvVlhJWGdjNk94UEpCZFJoQnpvN1FyYUYzQWlIT2p0UE9yYVlLc2M2T3lpakJ0aHBSem83RWxZbXVFQwAA"},"raw_count":2,"continuation":{"has_next_page":true,"next_cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxGLtegSgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNteysAnEAoABh1M217Kv7HgCwAHAAABCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCWWM2T3kxdHRieHdSem83S056bG9IVkhPanM4NzRiY0QwYzZPMG54ZFpoL2h6bzdQQTdtckZkSE9qdEhhbWFJYlVjNk95c1dScFJjUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3hHTHRlZ1Noem83SzY1bGpFT0hPanRIZlNhNFZrYzZPeDhtSm9CL3h6bzdLS01HMkdsSE9qdFMvVlhJWGdjNk96NHZSZkI3aHpvN1R6cTJtQ3JIT2p0Q3RvWGNDSWM2T3hQSkJkUmhCem83RXBzV2dIYkhPanNTVmlhNFFJYzZPeEl4VnB4NWc9PQAA"},"http_status":200,"sha256":"0d72e92a944c9e1862acceb4d4202cee24abed5c650c68e82dc47e93851ba065","response_bytes":13828}
{"request_id":"request-0249","query_id":"2026-08-31-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:27.030862+00:00","completed_at_utc":"2026-10-17T03:49:27.465645+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180900 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENWclxoA_QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtf8EAnEAoABh1M21_wP9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTldjbHhvQS9SMFExbUhCRmlIUQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0250","query_id":"2026-08-31-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:27.469888+00:00","completed_at_utc":"2026-10-17T03:49:27.912551+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1788180900 until_time:1788181200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHRDWYcEWIdAKAAIdENWclxoA_QAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtgwYAnEAoABh1M22DBf9jwCwAHAAAAMEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBSWRFTldjbHhvQS9SMFExbUhCRmlIUQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0251","query_id":"2026-09-30-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:27.915273+00:00","completed_at_utc":"2026-10-17T03:49:28.960243+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772900 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3VEcRvQpQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtiPMAnEAoABh1M22I8v9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM1pQS05aUXBCMDNkWk12R2xIZ0hUZDFSSEViMEtVZE4zVnRQaGFoRXgwM2Rpa0RtdUhyAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0252","query_id":"2026-09-30-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:28.963340+00:00","completed_at_utc":"2026-10-17T03:49:29.686856+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1790772900 until_time:1790773200","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHTd2TyjWUKQKAAIdN3VEcRvQpQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUdTNtjE0AnEAoABh1M22MTP9jwCwAHAAAAUEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFBVWROM1pQS05aUXBCMDNkWk12R2xIZ0hUZDFSSEViMEtVZE4zVnRQaGFoRXgwM2Rpa0RtdUhyAAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0253","query_id":"2026-07-31-5m-p1-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:29.689771+00:00","completed_at_utc":"2026-10-17T03:49:30.533509+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502500 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxGLtegSgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNtdwYAnEAoABh1M213Bf7HgCwAHAAABCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCWWM2T3kxdHRieHdSem83S056bG9IVkhPanM4NzRiY0QwYzZPMG54ZFpoL2h6bzdQQTdtckZkSE9qdEhhbWFJYlVjNk95c1dScFJjUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3hHTHRlZ1Noem83SzY1bGpFT0hPanRIZlNhNFZrYzZPeDhtSm9CL3h6bzdLS01HMkdsSE9qdFMvVlhJWGdjNk96NHZSZkI3aHpvN1R6cTJtQ3JIT2p0Q3RvWGNDSWM2T3hQSkJkUmhCem83RXBzV2dIYkhPanNTVmlhNFFJYzZPeEl4VnB4NWc9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0254","query_id":"2026-07-31-5m-p2-w11","kind":"search","tool_or_endpoint":"/twitter/tweet/advanced_search","issued_at_utc":"2026-10-17T03:49:30.536990+00:00","completed_at_utc":"2026-10-17T03:49:31.300699+00:00","arguments":{"query":"(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785502500 until_time:1785502800","queryType":"Latest","limit":20,"cursor":"DAADDAABCgABHOjtS_VXIXgKAAIc6OxGLtegSgAIAAIAAAACCAADAAAAAAgABAAAAAEKAAUdTNteysAnEAoABh1M217Kv7HgCwAHAAABCEVtUEM2d0FBQWZRL2dHSk4wdkdwL0FBQUFCWWM2T3kxdHRieHdSem83S056bG9IVkhPanM4NzRiY0QwYzZPMG54ZFpoL2h6bzdQQTdtckZkSE9qdEhhbWFJYlVjNk95c1dScFJjUnpvN09rMm1sSFhIT2pzMmx6V3dOb2M2T3hHTHRlZ1Noem83SzY1bGpFT0hPanRIZlNhNFZrYzZPeDhtSm9CL3h6bzdLS01HMkdsSE9qdFMvVlhJWGdjNk96NHZSZkI3aHpvN1R6cTJtQ3JIT2p0Q3RvWGNDSWM2T3hQSkJkUmhCem83RXBzV2dIYkhPanNTVmlhNFFJYzZPeEl4VnB4NWc9PQAA"},"raw_count":0,"continuation":{"has_next_page":false,"next_cursor":null},"http_status":200,"sha256":"c211e5c2da1ddac542e156973a29cef0984ee2d85b1fc71a01f194fc212a5785","response_bytes":54}
{"request_id":"request-0255","query_id":"availability-000","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:49:31.313248+00:00","completed_at_utc":"2026-10-17T03:49:38.499657+00:00","arguments":{"tweet_ids":"2083160778341843345,2083160925813543079,2083161065735532639,2083161164914327965,2083161198011265296,2083161292878004305,2083161383521132709,2083161535656886351,2083161577289880004,2083161618385637796,2083161737046511704,2083161902427811841,2083162172159672786,2083162215889117631,2083162254686486697,2083162309099225167,2083162327470293440,2083162444042469623,2083162624464724230,2083162686528028749,2083162849484968420,2083162878530523531,2083162937150079488,2083162968762577152,2083163005890523298,2083163167971008766,2083163382924873901,2083163472381333599,2083163549057032546,2083163590027104523,2083163723099767138,2083163749699977538,2083163840964071568,2083163892780572672,2083163894240166129,2083163917740626264,2083163983335600161,2083164143130210730,2083164168480247842,2083164216542838897,2083164266853470259,2083164337926226351,2083164375758577760,2083164577110294728,2083164578985464092,2083164590234345487,2083164643779121586,2083164681313681826,2083164686388744530,2083164701836640557"},"raw_count":48,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"ac7a5bdb4c685a25a363a99e77adacc808566422d3ad0b891b8375280b7dcae8","response_bytes":171859}
{"request_id":"request-0256","query_id":"availability-001","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:49:38.500389+00:00","completed_at_utc":"2026-10-17T03:49:45.128671+00:00","arguments":{"tweet_ids":"2083164752684208622,2083164823274037347,2083164945827414418,2083165015503216844,2083165046637482420,2083165092141469826,2083165134932054527,2083165211268120999,2083165262258528605,2083165264968044602,2083165308169158930,2083165330696761722,2083165337223381129,2083165337269228011,2083165413295407144,2083165416042492263,2083165489706983497,2083165589112025589,2083165679315026018,2083165686163964376,2083165697127932263,2083165716161699914,2083165723111657694,2083165808793104838,2083166106332860571,2083166164742713789,2083166394170905054,2083166560969978091,2083166566376763483,2083166729287422188,2083166929712185660,2083167057269399997,2083167107064459428,2083167164287377917,2083167259522949479,2083167350753562881,2083167451550986667,2083167503992209720,2083167511034400824,2083167620967145750,2083167651023765722,2083167717440290903,2083167744065740886,2083167746657841415,2083167766459174950,2083167788563304593,2083167934567039072,2083167935963758939,2083168015512662358,2083168036404781526"},"raw_count":48,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"e54f9ac98199c25af23061ad0c065fab606991c2a1793146d12c41222b07442b","response_bytes":215822}
{"request_id":"request-0257","query_id":"availability-002","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:49:45.129862+00:00","completed_at_utc":"2026-10-17T03:49:49.960025+00:00","arguments":{"tweet_ids":"2083168070470881484,2083168082684760430,2083168166096560192,2083168201781997652,2083168205296603311,2083168210170589359,2083168217389007015,2083168226083836336,2083168226926813688,2083168238381461520,2083168288012415118,2083168299119161702,2083168306371133567,2083168321365495941,2083168380123824287,2083168485296009559,2083168493177102818,2083168512047247713,2083168520637174085,2083168619329183889,2083168631933001852,2083168691751928190,2083168745074184684,2083168761763287417,2083168800246239400,2083168806407475471,2083168836485022009,2083168854549885034,2083168940449034630,2083168970081710334,2083169033054978198,2083169035064332678,2083169107298685322,2083169116995600441,2083169122758914271,2083169133022339434,2083169142878978090,2083169154182594955,2083169188214972669,2083169224768332195,2083169284906205340,2083169317676372243,2083169373074682175,2083169381190619399,2083169382461550910,2083169391202435416,2083169394570784875,2083169429907783806,2083169467949883871,2083169581980393710"},"raw_count":47,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"bbf2e7567d9ce359df296bd00ddc9d6ba670346b24733c68ebc05c777c19e65f","response_bytes":161639}
{"request_id":"request-0258","query_id":"availability-003","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:49:49.961119+00:00","completed_at_utc":"2026-10-17T03:49:55.484571+00:00","arguments":{"tweet_ids":"2083169620500873307,2083169744728031354,2083169770715889767,2083169873489015112,2083169996461740518,2083170001893405128,2083170058768179391,2083170077470253068,2083170097191895154,2083170154591219820,2083170253262168505,2083170366109979077,2083170385437282468,2083170388415025210,2083170489149886607,2083170546267890092,2083170572393914620,2083170630766149894,2083170719643369770,2083170735128781269,2083170739268784152,2083170804255379534,2083170831891591412,2083170835653857566,2083170924631670920,2083170961583427923,2083171090608578596,2083171127715832258,2083171214743281898,2083171236012548509,2083171277326496064,2083171325724840168,2083171351473316219,2083171410579517512,2083171414786425334,2083171478804287823,2083171525834752419,2083171661981827319,2083171769679245668,2083171841581965498,2083171876633801139,2083171946955682129,2083171973174280354,2083172068661612627,2083172072671359273,2083172074051223701,2083172121790804239,2083172275600400696,2083172488712802386,2083172920205914244"},"raw_count":50,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"358a458a2e2dd4d87f76df55c08811ae3b7f867b1caa2bfc5204119411826abd","response_bytes":226000}
{"request_id":"request-0259","query_id":"availability-004","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:49:55.485639+00:00","completed_at_utc":"2026-10-17T03:50:00.570839+00:00","arguments":{"tweet_ids":"2083173425103737053,2083173512554938623,2083173655509664188,2083173674996166764,2083173734756827298,2083173914641928234,2083174349629231353,2083174381673717815,2083174624951693798,2083174632048427483,2083174847539184127,2083175010538316197,2083175062840946958,2083175107791577304,2083175240876818571,2083175250263458010,2083175330013982823,2083175344195154269,2083175380727349742,2083175458523279394,2083175476109926620,2083175500919312531,2083175507344990702,2083175539314139573,2083175540572479833,2083175582737523198,2083175686018134503,2083175745459753226,2083175754163245279,2083175766766858285,2083175791719014487,2083175792159433150,2083175807002767696,2094394777340891391,2094394929548280221,2094394965476696254,2094394990390583787,2094395024075084024,2094395202551078927,2094395424694259835,2094395774897426542,2094396021690560928,2094396137188852137,2094396157808316580,2094396412486193503,2094396515124924646,2094396667009364362,2094396890435740040,2094396904931013106,2094397017531519465"},"raw_count":48,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"79019275e8ff3dc11daf82e3548388b909003a2f19b21b56ae1dfd83fb5f205b","response_bytes":243887}
{"request_id":"request-0260","query_id":"availability-005","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:50:00.571842+00:00","completed_at_utc":"2026-10-17T03:50:12.036711+00:00","arguments":{"tweet_ids":"2094397320708104410,2094397663898742855,2094397993738752324,2094398044254966151,2094398143844511946,2094398303739969797,2094399203489276143,2094399316874105283,2094399368304673223,2094399566770524228,2094399912829989203,2094400634879709656,2094400913922253278,2094401130545500441,2094402043540877768,2094402151569080363,2094402333274677442,2094402549323317309,2094402830321000646,2094402948390600911,2094402999733100912,2094403030913523760,2094404116026097751,2094404141938356571,2094404282875326744,2094404300755628106,2094404409446838469,2094404492611420621,2094404947592740983,2094405490117636471,2094405513077457395,2094405751804678573,2094406641307283964,2094407118589682051,2094407264643727679,2094407404158890090,2094407628994802098,2094407635974119633,2094407700985663949,2094407742555304132,2094408047166902500,2094408599141310803,2094409219629789223,2094409554805289472,2094409800540921873,2105266675687870736,2105267966732357709,2105268145761951773,2105269501109649716,2105269693002969447"},"raw_count":48,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"267dd6f6feb1729d6c5b1430740deb0f8aba4b27cede5dbad4a805250a503069","response_bytes":218044}
{"request_id":"request-0261","query_id":"availability-006","kind":"lookup","tool_or_endpoint":"/twitter/tweets","issued_at_utc":"2026-10-17T03:50:12.037806+00:00","completed_at_utc":"2026-10-17T03:50:16.774561+00:00","arguments":{"tweet_ids":"2105269881642037666,2105269915468906987,2105270165826863400,2105270207178788987,2105270291714703457,2105271692482253121,2105273611200422277,2105273896006226248,2105274007855481047,2105274285778715051,2105276442795970823,2105276878500335989,2105276927032598552,2105277002601382286,2105277126773809432,2105277216095600651,2105277261054362011,2105277310051987738,2105277484216533364,2105277746415075456,2105277761908523147,2105278108698112358,2105278353657962927,2105278426919702640,2105278499288502514,2105278552086356016,2105278634738995695,2105278667945619577,2105278803832406245,2105278918261645820,2105279029427233009,2105279051619602657,2105279303445291392,2105279311486091437,2105279475277517157,2105279722615976150,2105279918187913623,2105280070562840794,2105280095850316151,2105280287634870437,2105280311873384581,2105280462872551699,2105280518585737574,2105280550516990373,2105280648411779147,2105281433178624164"},"raw_count":45,"continuation":{"has_next_page":null,"next_cursor":null},"http_status":200,"sha256":"63b1cbeb76bcc43f9faf32bbb298a07ddba0a24477814d7d3b7c7bb9bb46c964","response_bytes":184531}
```

## Appendix E. Available matching controls still missed by 5-minute search

For each publication date below, the listed IDs were in the fixed stored control population, had captured current search/lookup evidence of availability and matching eligibility, and were absent from the corresponding full-hour union of 5-minute searches in both passes. These lists exclude controls not returned or unavailable by lookup. The full October 17 lookup parameters are in Appendix D.

### 2026-07-31 — 154 missing of 273 available matching controls

```json
[
  "2083160778341843345",
  "2083160925813543079",
  "2083161065735532639",
  "2083161164914327965",
  "2083161198011265296",
  "2083161292878004305",
  "2083161383521132709",
  "2083161535656886351",
  "2083161577289880004",
  "2083161618385637796",
  "2083161737046511704",
  "2083161902427811841",
  "2083162172159672786",
  "2083162215889117631",
  "2083162309099225167",
  "2083162327470293440",
  "2083162624464724230",
  "2083162686528028749",
  "2083162849484968420",
  "2083162878530523531",
  "2083162937150079488",
  "2083162968762577152",
  "2083163005890523298",
  "2083163549057032546",
  "2083163590027104523",
  "2083163723099767138",
  "2083163749699977538",
  "2083163840964071568",
  "2083163892780572672",
  "2083163894240166129",
  "2083163917740626264",
  "2083163983335600161",
  "2083164143130210730",
  "2083164168480247842",
  "2083164216542838897",
  "2083164266853470259",
  "2083164375758577760",
  "2083164643779121586",
  "2083164681313681826",
  "2083164701836640557",
  "2083164752684208622",
  "2083164823274037347",
  "2083165015503216844",
  "2083165046637482420",
  "2083165092141469826",
  "2083165134932054527",
  "2083165211268120999",
  "2083165262258528605",
  "2083165264968044602",
  "2083165330696761722",
  "2083165413295407144",
  "2083165416042492263",
  "2083165489706983497",
  "2083165589112025589",
  "2083165679315026018",
  "2083165686163964376",
  "2083165716161699914",
  "2083165808793104838",
  "2083166164742713789",
  "2083166394170905054",
  "2083166560969978091",
  "2083166929712185660",
  "2083167107064459428",
  "2083167164287377917",
  "2083167259522949479",
  "2083167451550986667",
  "2083167503992209720",
  "2083167620967145750",
  "2083167717440290903",
  "2083167744065740886",
  "2083167746657841415",
  "2083167766459174950",
  "2083167788563304593",
  "2083168015512662358",
  "2083168036404781526",
  "2083168070470881484",
  "2083168082684760430",
  "2083168166096560192",
  "2083168201781997652",
  "2083168210170589359",
  "2083168226083836336",
  "2083168238381461520",
  "2083168380123824287",
  "2083168485296009559",
  "2083168512047247713",
  "2083168520637174085",
  "2083168619329183889",
  "2083168631933001852",
  "2083168691751928190",
  "2083168745074184684",
  "2083168836485022009",
  "2083168854549885034",
  "2083168940449034630",
  "2083168970081710334",
  "2083169035064332678",
  "2083169116995600441",
  "2083169142878978090",
  "2083169188214972669",
  "2083169284906205340",
  "2083169317676372243",
  "2083169382461550910",
  "2083169391202435416",
  "2083169394570784875",
  "2083169467949883871",
  "2083169744728031354",
  "2083169770715889767",
  "2083169873489015112",
  "2083169996461740518",
  "2083170077470253068",
  "2083170097191895154",
  "2083170154591219820",
  "2083170253262168505",
  "2083170385437282468",
  "2083170546267890092",
  "2083170719643369770",
  "2083170735128781269",
  "2083170739268784152",
  "2083170804255379534",
  "2083170831891591412",
  "2083170961583427923",
  "2083171090608578596",
  "2083171127715832258",
  "2083171214743281898",
  "2083171236012548509",
  "2083171277326496064",
  "2083171325724840168",
  "2083171351473316219",
  "2083171410579517512",
  "2083171414786425334",
  "2083171525834752419",
  "2083171841581965498",
  "2083171876633801139",
  "2083171946955682129",
  "2083171973174280354",
  "2083172072671359273",
  "2083172275600400696",
  "2083173425103737053",
  "2083173512554938623",
  "2083173655509664188",
  "2083173734756827298",
  "2083174349629231353",
  "2083174381673717815",
  "2083175107791577304",
  "2083175240876818571",
  "2083175330013982823",
  "2083175476109926620",
  "2083175500919312531",
  "2083175507344990702",
  "2083175745459753226",
  "2083175754163245279",
  "2083175766766858285",
  "2083175791719014487",
  "2083175792159433150",
  "2083175807002767696"
]
```

### 2026-08-31 — 60 missing of 95 available matching controls

```json
[
  "2094394777340891391",
  "2094394929548280221",
  "2094394965476696254",
  "2094394990390583787",
  "2094395024075084024",
  "2094395202551078927",
  "2094395424694259835",
  "2094395774897426542",
  "2094396021690560928",
  "2094396137188852137",
  "2094396157808316580",
  "2094396412486193503",
  "2094396515124924646",
  "2094396667009364362",
  "2094396890435740040",
  "2094396904931013106",
  "2094397017531519465",
  "2094397320708104410",
  "2094397663898742855",
  "2094397993738752324",
  "2094398044254966151",
  "2094398143844511946",
  "2094398303739969797",
  "2094399203489276143",
  "2094399316874105283",
  "2094399368304673223",
  "2094399566770524228",
  "2094399912829989203",
  "2094400634879709656",
  "2094400913922253278",
  "2094401130545500441",
  "2094402043540877768",
  "2094402151569080363",
  "2094402333274677442",
  "2094402549323317309",
  "2094402830321000646",
  "2094402948390600911",
  "2094402999733100912",
  "2094403030913523760",
  "2094404116026097751",
  "2094404141938356571",
  "2094404282875326744",
  "2094404300755628106",
  "2094404409446838469",
  "2094404492611420621",
  "2094404947592740983",
  "2094405490117636471",
  "2094405513077457395",
  "2094406641307283964",
  "2094407118589682051",
  "2094407264643727679",
  "2094407628994802098",
  "2094407635974119633",
  "2094407700985663949",
  "2094407742555304132",
  "2094408047166902500",
  "2094408599141310803",
  "2094409219629789223",
  "2094409554805289472",
  "2094409800540921873"
]
```

### 2026-09-30 — 42 missing of 59 available matching controls

```json
[
  "2105266675687870736",
  "2105267966732357709",
  "2105268145761951773",
  "2105269501109649716",
  "2105269693002969447",
  "2105269881642037666",
  "2105270165826863400",
  "2105270207178788987",
  "2105270291714703457",
  "2105271692482253121",
  "2105273611200422277",
  "2105273896006226248",
  "2105276442795970823",
  "2105276878500335989",
  "2105276927032598552",
  "2105277002601382286",
  "2105277216095600651",
  "2105277261054362011",
  "2105277310051987738",
  "2105277484216533364",
  "2105277746415075456",
  "2105277761908523147",
  "2105278108698112358",
  "2105278353657962927",
  "2105278426919702640",
  "2105278499288502514",
  "2105278552086356016",
  "2105278634738995695",
  "2105278667945619577",
  "2105278803832406245",
  "2105278918261645820",
  "2105279029427233009",
  "2105279311486091437",
  "2105279475277517157",
  "2105279722615976150",
  "2105279918187913623",
  "2105280070562840794",
  "2105280095850316151",
  "2105280311873384581",
  "2105280518585737574",
  "2105280550516990373",
  "2105280648411779147"
]
```
