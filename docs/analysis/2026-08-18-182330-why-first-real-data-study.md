# Why-first headline study — real data

This repeats the structure of `2026-08-14-235900-why-first-headline-samples.md`,
but uses real stored posts from a read-only PostgreSQL shadow. No simulated posts
were inserted and no narrative/lifecycle rows were written. The only file write
from this run is this report.

Each window made one bounded DeepSeek provider request. The verbatim excerpts
below are the exact stored evidence strings cited by the model's attempted
claims; they are packet excerpts, not reconstructed or paraphrased posts.

## Window summary

| Window | Exact interval (UTC) | Candidates | Packet bytes | Provider result |
| --- | --- | ---: | ---: | --- |
| Latest available | 2026-08-14 00:00:31 → 2026-08-15 00:00:31 | 6 | 123,411 | REJECTED: `headline_output_event_anchor_required` |
| 2026-08-13 | 2026-08-13 00:00:00 → 2026-08-14 00:00:00 | 6 | 107,076 | REJECTED: `headline_output_schema_invalid` |
| 2026-07-13 | 2026-07-13 00:00:00 → 2026-07-14 00:00:00 | 6 | 93,716 | REJECTED: `headline_output_explanation_support_weak` |

All three windows had sufficient selected/prior coverage and comparison was
allowed. The latest interval is the latest complete 24-hour interval available
in this shadow; the source ends at 2026-08-15 00:00:31Z.

## Latest available window

### Quantitative evidence

| Candidate | Selected | Prior | Volume change | Evidence excerpts |
| --- | ---: | ---: | ---: | ---: |
| DeepSeek | 4,744 | 6,491 | -27% | 12 |
| Qwen | 2,456 | 1,014 | +142% | 48 |
| Zhipu GLM | 1,095 | 293 | +274% | 12 |
| MiniMax AI | 1,428 | 1,292 | +11% | 4 |
| Tencent Hunyuan | 25 | 26 | -4% | 12 |
| Meta Llama | 181 | 134 | +35% | 12 |

### Attempted output — REJECTED

Validator: `headline_output_event_anchor_required`  
Selected candidate: Qwen (`qwen:60-69`)

**Why rejected:** The model used event language (“open-weight release”) but
left the required `event_anchor` field empty, so the claim was not linked to a
specific supported event span in the evidence.

**English**

> Conversation centered on Qwen's open-weight release, with users reporting local downloads, benchmark runs, and comparisons against frontier models, alongside a 142% rise in volume.

**简体中文**

> 讨论集中在 Qwen 的开源权重发布上，用户纷纷报告本地下载、基准测试以及与前沿模型的对比，同时讨论量上升了 142%。

**Observation**

> Posts repeatedly described Qwen 3.8 27B as a locally runnable model competing with closed frontier systems, with independent users sharing download and deployment experiences.

**观察（简体中文）**

> 帖子反复将 Qwen 3.8 27B 描述为可在本地运行、能与闭源前沿系统竞争的模型，多个独立用户分享了下载和部署体验。

### Verbatim cited posts

#### Qwen — `e_af7d2cce668f3142d7bd7519`

~~~text
We promised open weights for Qwen3.8. Now, time to meet them! 🎉 ⚡ Qwen3.8-27B: - A native multimodal dense model. With just 27B parameters, it outperforms Qwen3.7-Plus overall and shines in real-world coding & office workflows. - 262K native context, easily extendable to 1M tokens via YaRN. - Built for builders. Highly efficient, high-quality, and licensed under Apache 2.0. 🚀 The open weights for Qwen3.8-2.4T-A95B (Max-level) have also been released recently. Whether you're shipping lightweight applications with Qwen3.8-27B locally or building agents with Qwen3.8-2.4T-A95B, they're yours now! Download, deploy, and build something we haven't imagined yet. 👀👇 - Hugging Face： https://t.co/4kaAcqYEVj - ModelScope： https://t.co/eRIMZCGkhC
~~~

#### Qwen — `e_3486200b5e11a444e33a9979`

~~~text
Before i update to Qwen 3.8-27B - last benchmark with Qwen 3.6-27B on my 3x1080Ti is 36t/s. #bookmarkforme
~~~

#### Qwen — `e_afe475387de411d740e0ae2b`

~~~text
Je sais pas si on se rend vraiment compte : Qwen 3.8 27B, c’est du niveau d’Opus 4.6 en local, avec +200 t/s sur une 5090 et autour de 40–50 t/s sur un DGX Spark. C’est assez fou. SOTA en code askip ! Je le passe sur le billard pour le bench sur mon EVO X2 : pour l’instant je tourne autour de 20 t/s Et forcément je me dis : wen Qwen 35B MoE ?? Je vais pouvoir en profiter à fond, et on va se régaler en API Un mot : trop fort.
~~~

#### Qwen — `e_bbbcc4bd70b78a253aa6ce6a`

~~~text
🔴 ¡QWEN 3.8 27B LIBERADO! A finales de 2025 modelos como Opus 4.5 le abrió los ojos al mundo en cuanto a las capacidades de lo que la IA agéntica podía hacer, sobre todo en programación. Hoy ya puedes ejecutar un modelo superior directamente en tu portátil, en local 🔥
~~~

## 2026-08-13 window

### Quantitative evidence

| Candidate | Selected | Prior | Volume change | Evidence excerpts |
| --- | ---: | ---: | ---: | ---: |
| DeepSeek | 6,488 | 3,842 | +69% | 4 |
| MiniMax AI | 1,293 | 1,050 | +23% | 12 |
| Mistral | 94 | 103 | -9% | 12 |
| Tencent Hunyuan | 26 | 33 | -21% | 25 |
| Qwen | 1,014 | 1,231 | -18% | 4 |
| Meta Llama | 135 | 141 | -4% | 12 |

### Attempted output — REJECTED

Validator: `headline_output_schema_invalid`  
Selected candidates: DeepSeek (`deepseek:52-58`), MiniMax AI (`minimax:full_window`), Tencent Hunyuan (`hunyuan:full_window`)

**Why rejected:** The returned JSON did not satisfy the generation output
schema. The provider transport succeeded, but the application could not accept
the structure as a valid headline response; this code does not expose a more
specific field-level schema error.

**English**

> DeepSeek conversation centered on the V4-Pro release, with users describing frontier performance, flexible reasoning effort, and dramatically cheaper access for builders, alongside a 69% jump in volume.

**简体中文**

> DeepSeek 的讨论集中在 V4-Pro 发布上，用户描述了前沿性能、灵活推理力度以及对开发者而言大幅降低的使用成本，同时讨论量跃升 69%。

**Observations**

> MiniMax AI chatter focused on hands-on H3 video experiments and an upcoming San Francisco showcase, with volume up 23%.

> Tencent Hunyuan posts centered on local video generation tools and Tencent's AI infrastructure spending, with volume down 21%.

**观察（简体中文）**

> MiniMax AI 的讨论集中在 H3 视频实验和即将举行的旧金山展示活动上，讨论量上升 23%。

> Tencent Hunyuan 的帖子集中在本地视频生成工具和腾讯的 AI 基础设施支出上，讨论量下降 21%。

### Verbatim cited posts

#### DeepSeek — `e_86cdbf33abc66eac85d9b68c`

~~~text
DeepSeek just dropped V4-Pro. Frontier performance, flexible reasoning effort, native OpenAI API support. The part that matters for builders isn't the benchmark. It's that a model this capable just got dramatically cheaper overnight.
~~~

#### DeepSeek — `e_60f42a8910084a94fa60a208`

~~~text
DeepSeek V4 Pro 0813が今日から正式提供っぽい。今気づいた。凄そう。早速使ってみる。
~~~

#### MiniMax AI — `e_bbff7acdbd53f5344910554a`

~~~text
Tomorrow at 5:30pm PT: MiniMax H3 × @magnific at the Magnific SF office. We’ll be showcasing what people are already making with H3, talking about where AI video is heading, and getting hands-on with H3 inside Magnific. Expect a live workflow across cinematic generation, native audio, dialogue, editing + more. Then we’ll open things up for networking and more showcases from the community. Only a couple spots left. Link below. #MiniMaxH3 #AIVideo
~~~

#### MiniMax AI — `e_79fc856bf8fbcf5274ae4b7f`

~~~text
Minimax h3で実験。 尾阿波踊りを踊るという指定からトマトという制約を外してみたが、分かんないな。短足のせいか？。 https://t.co/sU7UZybXGw
~~~

#### Tencent Hunyuan — `e_32f566984b2cf640c604e401`

~~~text
A free repo with 7.9K stars runs a full AI video studio locally on 6GB of VRAM with WAN 2.2, LTX-2, Hunyuan Video and Flux built in. One-click install script, generate in your browser. No uploads, no subscriptions, no watermarks. https://t.co/kYg256CAhG
~~~

#### Tencent Hunyuan — `e_70452cc5cd38586dbbdd0573`

~~~text
Atlas Episode 1 - F**king Casinos It's been 6 months since I made an AI video - and the workflow is VERY different now. Seedance 2.5 is really powerful for animation, and Minimax H3 is leagues beyond it for words. There is a BIG opportunity for sound design tools. I made a breakthrough here, and I'm opensourcing it with hopes someone will make it better! The old adage, spend 4 hours sharpening your axe is very true for AI video workflows now: - Teach your agent about the style your going for, what types of shots are used, timing, camera lenses, etc. - NAIL your references - NAIL your shotlist - Use model-provided best prompting practices The rest is just a director's eye (video experience). Until you come to sound... I tried all of the SOTA models (MMAudio, Hunyuan etc) and they are terrible. So i trained an agent skill on some of the best sound design/scoring advice on the internet, gave it an @ElevenLabs API and @HyperFrames_ and the results were genuinely impressive. About 80% of th
~~~

## 2026-07-13 window

### Quantitative evidence

| Candidate | Selected | Prior | Volume change | Evidence excerpts |
| --- | ---: | ---: | ---: | ---: |
| DeepSeek | 490 | 19 | +2,479% | 4 |
| Baidu ERNIE | 34 | 0 | unavailable (no prior posts) | 28 |
| Zhipu GLM | 484 | 16 | +2,925% | 4 |
| 01.AI Yi | 40 | 0 | unavailable (no prior posts) | 12 |
| MiniMax AI | 140 | 1 | +13,900% | 12 |
| Meta Llama | 462 | 5 | +9,140% | 4 |

### Attempted output — REJECTED

Validator: `headline_output_explanation_support_weak`  
Selected candidate: DeepSeek (`deepseek:full_window`)

**Why rejected:** The model labeled its explanation `recurring_content`, but
the cited rows did not establish the required recurring theme across at least
two independent author groups and source clusters. Separately, the model chose
DeepSeek even though MiniMax and Llama had larger measured increases in this
window; that is a wrong-leader review failure.

**English**

> Conversation around DeepSeek centered on its role in China's broader AI ecosystem and hands-on model comparisons, with users describing it as strong for technical work while a new Singapore model was said to beat it on several benchmarks, alongside a 2479% rise in volume.

**简体中文**

> 围绕 DeepSeek 的讨论集中在其在中国更广泛 AI 生态中的角色以及实际模型对比上，用户称其擅长技术工作，同时有帖子称一款新的新加坡模型在多项基准上超越它，讨论量上升 2479%。

**Observation**

> Posts described DeepSeek as part of an end-to-end Chinese AI economy spanning models, cloud infrastructure, and enterprise adoption, while separate users framed it as a technical, math, and programming specialist.

**观察（简体中文）**

> 帖子将 DeepSeek 描述为覆盖模型、云基础设施和企业采用的中国端到端 AI 经济的一部分，同时另有用户将其定位为技术、数学和编程方面的专长模型。

### Verbatim cited posts

#### DeepSeek — `e_c6a074114c7e68ed5136e36c`

~~~text
China Isn’t Just Building AI. It’s Building the Entire AI Economy. Most discussions about AI focus on who has the best model. China is playing a much bigger game. It’s building an end-to-end AI ecosystem where every layer reinforces the next: 🔹 AI Models – DeepSeek, Qwen, ERNIE, MiniMax, Kimi, Hunyuan and many others compete relentlessly, driving innovation and lowering costs. 🔹 Hyperscale Cloud Infrastructure – Alibaba Cloud, Tencent Cloud, Huawei Cloud, Baidu Cloud and Volcano Engine are investing billions in GPUs, data centres and AI infrastructure to power the next generation of applications. 🔹 Developer Platforms – APIs, orchestration layers and agent frameworks make it easier for businesses to build AI products without starting from scratch. 🔹 Enterprise Adoption – Companies deploy AI into customer service, software development, healthcare, finance, manufacturing and education, creating real business value. 🔹 The Flywheel – More users generate more data. More data improves models
~~~

#### DeepSeek — `e_f791ae40f456a03bbdbea040`

~~~text
Okay, so I am NOT trying to force people to use AI, but apparently a LOT of people are either confused or didn't research what they are protesting. So here is a 40,000 foot view summary of exactly WHAT AI is. What is AI? At its core, Generative AI (GenAI) is fundamentally textual. These systems are large language models (LLMs) trained to understand and generate human-like text. They reason, write, code, summarize, and plan using language as their native medium. Grok (built by xAI): Truth-seeking, technically strong, and helpful with a touch of humor. ChatGPT (OpenAI): Versatile all-rounder, great for creative writing, conversations, and general tasks. DeepSeek: Excels at technical work, math, and programming. Gemini (Google): Strong multimodal capabilities and web-integrated knowledge. Image and Video Generation are not core GenAI functions. They are secondary specialized models (usually diffusion models) that take text output from a GenAI model as input. In practice, the main LLM acts
~~~

## Findings

1. Real content can produce a plausible why. The 2026-08-13 DeepSeek evidence
   directly references the V4-Pro release, and the Qwen evidence combines an
   apparent release announcement with independent local benchmark/use reports.
2. The output contract still rejects all three real-data attempts, but for
   different reasons. This is not a transport problem: all three requests
   returned HTTP 200.
3. The 2026-07-13 run exposes a leader-selection risk. MiniMax (+13,900%) and
   Llama (+9,140%) exceeded DeepSeek (+2,479%), yet the provider selected
   DeepSeek. The validator rejected the explanation, but this should also be
   treated as a wrong-leader test failure.
4. Two candidates on 2026-07-13 have no percentage change because their prior
   window has zero posts. The packet must not invent a percentage for them.
5. The latest window has zero classified rows on both sides for the mix
   families. The historical windows have only one-sided classification coverage
   for some candidates (selected-only or prior-only), so any emitted
   `brand_change_pp` values there are not valid two-sided comparisons. This
   study therefore exercises volume plus raw content, but not a trustworthy
   mix-change path.


## Exact provider packet — latest available window

The following is the canonical JSON packet supplied to the provider for the latest window. The single long line is intentional: it preserves the exact serialized packet bytes.

~~~json
{
  "as_of": "2026-08-15T00:00:31Z",
  "candidates": [
    {
      "brand_key": "deepseek",
      "candidate_id": "deepseek:full_window",
      "coarse_series": {
        "author_counts": [
          573,
          560,
          661,
          605,
          563,
          528,
          297,
          287
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            679,
            666,
            773,
            706,
            637,
            606,
            349,
            328
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                114,
                125,
                152,
                124,
                85,
                91,
                55,
                48
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                565,
                541,
                621,
                582,
                552,
                515,
                294,
                280
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          679,
          666,
          773,
          706,
          637,
          606,
          349,
          328
        ]
      },
      "display_name_en": "DeepSeek",
      "display_name_zh_cn": "DeepSeek",
      "end_at": "2026-08-15T00:00:31Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_98109d427754acdb4f97",
          "discourse_keys": [],
          "evidence_id": "e_c0237fd79c2ef067dda636ae",
          "excerpt": "Anthropic and OpenAI just lost the agent infrastructure war. DeepSeek Harness just dropped as a model-agnostic, open-source alternative to Claude Code. Locked-in ecosystems are a dead end for real engineers. Why would you pay a 'safety' tax to a closed lab when you can run the harness yourself? https://t.co/MuNlGJpsmT #OpenSource #AI #DeepSeek",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_981d696cfffab2a80777",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_02306af04fde3af94a49"
        },
        {
          "author_group_id": "ag_9beee618763c0049fbd1",
          "discourse_keys": [],
          "evidence_id": "e_c92cfea2a3343ae8f45e9bfa",
          "excerpt": "DeepSeek V4 Pro Smoke测试翻车！材料约束仅55.60分，代码执行维度全缺失导致主榜落空😱 API故障还是模型硬伤？单日10题波动正常吗？ https://t.co/dnx3YMm0pB #DeepSeek V4 Pro #Smoke评测 #API故障",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_f06a26910ef370459c6b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_2ec648b44c3c753dde69"
        },
        {
          "author_group_id": "ag_607d49326caf7fddb0d0",
          "discourse_keys": [],
          "evidence_id": "e_88531495790e23029b2d4ee8",
          "excerpt": "@EvanOtero @mehulmpt Gemini 4 at Fable performance while at Deepseek V4 Flash prices https://t.co/cS8kCAtDpI",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_063356dc8f58acf130af",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_051c04ab78d4c3473952"
        },
        {
          "author_group_id": "ag_d0f4eb010ca9e1246bd0",
          "discourse_keys": [],
          "evidence_id": "e_bbe9afaf8ffe857e4fd087e7",
          "excerpt": "Claude - Gemini - Deepseek - Cursor",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a58da1a2ce04dbc69e6b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_bbb6171fc8d4d79ce82d"
        },
        {
          "author_group_id": "ag_a288b8fe8934eb152340",
          "discourse_keys": [],
          "evidence_id": "e_033fda7c1bbce7f587e44dc4",
          "excerpt": "「最近のAI界隈、数ヶ月前までの停滞が嘘みたいに盛り上がっとるな🔥 FableやMiniMax-H3とか、毎日新しいおもちゃが届く感覚！ attic_filmでも、最新AIで作ったアニメ調の素材を実写に合成するテストをしてるんやけど、これがめっちゃオモロいんよ。 クロマキー合成の手間も減って表現の幅がバグレベル",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_6901354c26202ea3458c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_3ab654af0e510efec372"
        },
        {
          "author_group_id": "ag_01f6ff0c8554e6242315",
          "discourse_keys": [],
          "evidence_id": "e_f0b712867d894513a4901ab1",
          "excerpt": "Cronjob Response: ☕ Kopi AI 热点日报 (job_id: 8d38408efbe1) ------------- ☕ Kopi AI 早报 | 2026年08月14日 1. Claude 接管应用日常维护：388 个 PR 的实践 — Boris Cherny 让 Claude 通过 Slack 自动完成崩溃测试、死代码清理等任务，数周内提交近 400 个 PR。 2. Google DeepMind 推出 Gemini 3.7 Flash — 距上代仅三周，主打编程与智能体任务，成为当前最强工作模型之一。 3. MiniMax Music 3.0 发布 — 新一代开源全能音乐模型，可根据概念和歌词一次生成最长五分钟的完整歌曲。 4. Google Sheets 推出 Sheets Canvas — 基于 Gemini，用户用自然语言即可将表格数据转化为交互式仪表盘和迷你应用。 5. Qwen3.8-2.4T-A95B 开源上线 — 阿里开源 2.4T 参数 MoE 模型（95B 激活），主打自主编码与深度研究，硅基流动提供 Day-0 支持。 6. DeepSeek Harness v0.1 开发者预览版发布 — 基于 Cordis 元框架构建的智能体框架，MIT 许可证开源。 7. Cursor 推出 Builds 功能 — 后台持续准备开发环境副本，云智能体启动速度提升最高 3 倍，环境启动快 10 倍。 --- 💡 Powered by Kopi AI Agent | https://t.co/s36sD3I9L9 ☕ 每天一杯 Kopi，AI 热点不错过 To stop or manage this job, send me a new message (e.g. \"stop reminder ☕ Kopi AI 热点日报\").",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_48894ce2b18832761af2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_adfecb32c26c06bfd88a"
        },
        {
          "author_group_id": "ag_2b811e947097e870fc94",
          "discourse_keys": [],
          "evidence_id": "e_19aeb80c5ea98ea24d325a66",
          "excerpt": "@deydercintron @OfficialLoganK @grok @grok compare to DeepSeek",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_993562de7d99a64cea92",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c9f6b8dd9860ab265799"
        },
        {
          "author_group_id": "ag_cea73506936d48a4a7d4",
          "discourse_keys": [],
          "evidence_id": "e_306d5387a11dd9a8efa3cfbc",
          "excerpt": "Al parecer DeepSeek hará un ajuste de precios en sus horas pico. Que según entiendo será de madrugada y de 7pm a 10pm hora del centro de México. Eso quiere decir que trabajaremos en horario de oficina. Además, si manejan obsidian para sus proyectos, es como un súper poder.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_235342fae97567786df3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7133a5ccd98d0aef892e"
        },
        {
          "author_group_id": "ag_1d32eb70bb7cd6f5a2da",
          "discourse_keys": [],
          "evidence_id": "e_2a68d508211d0b5208aeaa8f",
          "excerpt": "@TechMDAI Deepseek has this extra oomph Qwen 3.8 27b seems to be missing. I’m still experimenting with it though.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_82f0162edd919dcb4b61",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_6b28a303b08ee5b6a528"
        },
        {
          "author_group_id": "ag_94bad356e32094219124",
          "discourse_keys": [],
          "evidence_id": "e_e564c7d35a981cdfdd90f089",
          "excerpt": "【8/14 僕が気になったAIニューストピック8個】 ①本日、Gemini 3.7 Flash をリリースします。 https://t.co/GOHUOvm0pX ②本日、DeepSeek-V4-Proをリリースします！ https://t.co/r63ainhwVU ③DeepSeek Harness v0.1 が開発者プレビュー版として利用可能になりました！ https://t.co/1Wjqtx0n0E ④Claude Code デスクトップで使用制限に達しましたか？ 今ならオートコンティニュー チェックボックスがあります。 https://t.co/DpSpAGLLCz ⑤ChatGPT は今や、パソコンのアプリやウェブサイトでのあなたの活動を記憶できるようになりました。 https://t.co/JXvZ4XbA1P ⑥ウルトラファストモードのプレビュー：GPT-5.6 Sol、最大14倍の速度で。 https://t.co/isUUX6h2Nz GPT-5.6 Solのウルトラファストモードが、Cerebrasの技術で駆動され、現在限定プレビューで提供されています。 https://t.co/mkXs9Pqtwr ⑦Sakana Chat が大幅アップグレードされました。 https://t.co/PZCItn2yct ⑧Suno Studio 2.0 が公開されました。 https://t.co/FDEZA8BPy8 「AIに何を演奏させるか」だけでなく「自分でどう演奏するか」を選べる https://t.co/VW8CBu8Iy0",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_d2a691214d5a4b140918",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_6c4dc5d53e7a791d9124"
        },
        {
          "author_group_id": "ag_a350ff322f7abb62a647",
          "discourse_keys": [],
          "evidence_id": "e_80450dc48cf6187be626f960",
          "excerpt": "4/5 And I’m not convinced everyone else is playing with that same clock or bottleneck. @Kimi_Moonshot is already discussing Kimi K4, according to reporting, and apparently wants considerably more NVIDIA Blackwell compute to train something larger than K3. ByteDance is reportedly even deeper in the lunatic end of the pool, pretraining a model that could reach roughly 10 trillion parameters. That one is months away if it works, not next Tuesday, but it tells you how crowded the pipeline behind today’s releases already is. Then there’s @Alibaba_Qwen, DeepSeek and @Zai_org shipping or preparing open weights while the American labs increasingly have cyber evaluations, trusted-access programs and government coordination layered onto their release process. That could make “who shipped fastest?” a pretty misleading scoreboard.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_603328e08cd2b34d9a5f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_76dab0adb94b8ff77f4f"
        },
        {
          "author_group_id": "ag_576bbd104a7200874351",
          "discourse_keys": [],
          "evidence_id": "e_83c46432e0bb23e5e2a15c89",
          "excerpt": "2026년 8월 14일 AI 뉴스 1. 구글, Gemini Flash 가격 절반으로 인하 구글이 Gemini 3.7 Flash의 가격을 기존보다 약 50% 낮췄습니다. AI 성능 경쟁 못지않게 얼마나 싸게 AI를 사용할 수 있느냐가 중요해지면서 빅테크의 가격 경쟁도 본격화되고 있습니다. 2. OpenAI, GPT-5.6을 14배 빠르게 쓰는 요금제 공개 OpenAI가 GPT-5.6 Sol을 일반 방식보다 최대 14배 빠르게 실행하는 ‘Ultrafast’ 서비스를 내놨습니다. 복잡한 업무를 AI에게 맡기는 기업이 늘면서 단순히 똑똑한 모델보다 빠르게 답하고 일을 끝내는 AI의 가치가 커지고 있습니다. 3. DeepSeek, AI가 직접 일하는 ‘에이전트 도구’ 오픈소스로 공개 DeepSeek가 AI 에이전트를 실행하고 관리하는 Harness v0.1을 오픈소스로 공개했습니다. 이제 경쟁이 AI 모델 자체를 만드는 것에서 한 단계 더 나아가, AI가 실제 업무를 수행하게 만드는 실행 시스템으로 확대되고 있습니다. 4. 데이터브릭스, 기업가치 1,900억 달러 돌파 AI·데이터 기업 Databricks가 50억 달러 규모의 투자 유치 과정에서 약 1,900억 달러의 기업가치를 인정받았습니다. 연간 매출 규모도 70억 달러를 넘어, 기업들이 실제 업무에 AI를 도입하면서 관련 소프트웨어 시장도 빠르게 커지고 있습니다. 5. AMD, AI 투자 위해 50억 달러 자금 조달 추진 AMD가 최대 50억 달러 규모의 회사채 발행을 추진하고 있습니다. AI 반도체 경쟁에는 연구개발뿐 아니라 공장·칩·데이터센터 등에 막대한 돈이 필요해지면서 AI 경쟁이 자본력 싸움으로도 번지고 있습니다. 6. 로봇청소기, 이제 목소리와 손짓까지 알아듣는다 로봇 기업 Matic이 음성과 손짓으로 조작할 수 있는 새로운 로봇청소기 인터페이스를 공개했습니다. 앱에서 버튼을 누르는 대신 “여기 청소해”라고 말하거나 손으로 가리키는 방식이 가능해지면서 사람과 로봇의 소통 방식이 더 자연스러워지고 있습니",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_e16542d6cb532e78aac8",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_ba6cb97dba5a7f2bea3f"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 64,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 64,
        "selected_count": 12,
        "story_rank": 2,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "none",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "absurdist_meme",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "advertising-marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "ai_slop_critique",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "cope",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "dunk_yingyang",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "fud",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "genuine_hype",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "sarcasm",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "self_deprecation",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "advertising_marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "buzz_releases",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "feedback_questions",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "hands_on_usage",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "performance_comparisons",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "negative",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "neutral",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "positive",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "none",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 6491,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 4744,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "-26.914189",
          "comparison_state": "available",
          "prior_authors": 4201,
          "prior_count": 6491,
          "selected_authors": 3518,
          "selected_count": 4744
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "discourse": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "sentiment": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "deepseek:full_window",
          "direction": "decrease",
          "display_en": "27%",
          "display_zh_cn": "27%",
          "fact_id": "qf_5d43bfdf698712e3e2314859",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "-26.914189",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "volume",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "post_type",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "discourse",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "sentiment",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "nationalism",
          "rank": 1,
          "stream_position": 1
        }
      ],
      "start_at": "2026-08-14T00:00:31Z"
    },
    {
      "brand_key": "qwen",
      "candidate_id": "qwen:60-69",
      "coarse_series": {
        "author_counts": [
          77,
          86,
          153,
          153,
          198,
          696,
          361,
          292
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            80,
            102,
            172,
            164,
            228,
            930,
            435,
            345
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                12,
                21,
                34,
                22,
                38,
                226,
                78,
                57
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                68,
                81,
                138,
                142,
                190,
                704,
                357,
                288
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          80,
          102,
          172,
          164,
          228,
          930,
          435,
          345
        ]
      },
      "display_name_en": "Qwen",
      "display_name_zh_cn": "Qwen",
      "end_at": "2026-08-14T17:30:31Z",
      "episodes": [
        {
          "baseline_post_count": "16.000000",
          "end_at": "2026-08-14T17:30:31Z",
          "end_bucket_index": 69,
          "episode_id": "qwen:60-69",
          "peak_author_count": 131,
          "peak_post_count": 145,
          "peak_to_baseline": "9.062500",
          "post_count": 839,
          "start_at": "2026-08-14T15:00:31Z",
          "start_bucket_index": 60
        },
        {
          "baseline_post_count": "16.000000",
          "end_at": "2026-08-14T18:00:31Z",
          "end_bucket_index": 71,
          "episode_id": "qwen:71-71",
          "peak_author_count": 46,
          "peak_post_count": 52,
          "peak_to_baseline": "3.250000",
          "post_count": 52,
          "start_at": "2026-08-14T17:45:31Z",
          "start_bucket_index": 71
        }
      ],
      "evidence": [
        {
          "author_group_id": "ag_c94d583651e7d2d6cf00",
          "discourse_keys": [],
          "evidence_id": "e_af7d2cce668f3142d7bd7519",
          "excerpt": "We promised open weights for Qwen3.8. Now, time to meet them! 🎉 ⚡ Qwen3.8-27B: - A native multimodal dense model. With just 27B parameters, it outperforms Qwen3.7-Plus overall and shines in real-world coding & office workflows. - 262K native context, easily extendable to 1M tokens via YaRN. - Built for builders. Highly efficient, high-quality, and licensed under Apache 2.0. 🚀 The open weights for Qwen3.8-2.4T-A95B (Max-level) have also been released recently. Whether you're shipping lightweight applications with Qwen3.8-27B locally or building agents with Qwen3.8-2.4T-A95B, they're yours now! Download, deploy, and build something we haven't imagined yet. 👀👇 - Hugging Face： https://t.co/4kaAcqYEVj - ModelScope： https://t.co/eRIMZCGkhC",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_13fbb3aa89c074682a38",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": true,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_d6fda0c49eda183405ab"
        },
        {
          "author_group_id": "ag_25700276d7969cf24d77",
          "discourse_keys": [],
          "evidence_id": "e_3486200b5e11a444e33a9979",
          "excerpt": "Before i update to Qwen 3.8-27B - last benchmark with Qwen 3.6-27B on my 3x1080Ti is 36t/s. #bookmarkforme",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3887f9d5f4ca22e73051",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a14930db0dff140b9bc7"
        },
        {
          "author_group_id": "ag_bb1732029119435905b1",
          "discourse_keys": [],
          "evidence_id": "e_fdae4bff250793319f3acedf",
          "excerpt": "Qwen 3.8 27B is live! https://t.co/VpA5npb59N",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_36af01aff6f017fcbdfc",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_176b24485e43c6516ee5"
        },
        {
          "author_group_id": "ag_ed832c86fe73971b3bdf",
          "discourse_keys": [],
          "evidence_id": "e_ee93aaae7d6337e722fe91ad",
          "excerpt": "Qwen 3.8 27B is live. Heat up the GPUS!!!! https://t.co/n6mSD8Va4v",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d983a3aab4d78a12ec78",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_176b24485e43c6516ee5"
        },
        {
          "author_group_id": "ag_ca4ee423a4248f7babc7",
          "discourse_keys": [],
          "evidence_id": "e_590bfa59dcb0a4ae0dc99761",
          "excerpt": "qwen 3.8 27B is noice https://t.co/VXJdlAcsve",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_e897b8be9d0e49f74ac2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_176b24485e43c6516ee5"
        },
        {
          "author_group_id": "ag_aad4da45261dc59b93c9",
          "discourse_keys": [],
          "evidence_id": "e_c7b9e43acf0ccd4431311eb1",
          "excerpt": "Qwen 3.8 27b Benchmarks https://t.co/UuY9SC32Cs",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_6af929d7e0177d5a409e",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_fd8ece90ae1afa463e7b"
        },
        {
          "author_group_id": "ag_c94d583651e7d2d6cf00",
          "discourse_keys": [],
          "evidence_id": "e_d9e2bc0d193d31f6b96c8443",
          "excerpt": "Yes, we are back👑, with 206 tok/s on a single RTX 5090! Amazing Day-0 work from the SGLang team. Give it a try~@sgl_project",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3b98148d746c869cb6d0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": true,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_6b53e4a500a6db538145"
        },
        {
          "author_group_id": "ag_ca24ff4cc3a873a15fdf",
          "discourse_keys": [],
          "evidence_id": "e_37d372f07ef05f3b7a17bf2f",
          "excerpt": "Using qwen 3.8-27b 4-bit on a m3 pro 36gb Where do I change this in the desktop app? Can I change it? @UnslothAI https://t.co/qmiXRIFpjS",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_2f35c0b897c874efbb84",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a3dea002b80ca20b2dd1"
        },
        {
          "author_group_id": "ag_3a6efa29ec5bb807e098",
          "discourse_keys": [],
          "evidence_id": "e_373300f68535c6966674d805",
          "excerpt": "qwen",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_67f2d22514622d1be30c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_f79d6de60cb6852b35a5"
        },
        {
          "author_group_id": "ag_0578057e22e9064fc9c5",
          "discourse_keys": [],
          "evidence_id": "e_afe475387de411d740e0ae2b",
          "excerpt": "Je sais pas si on se rend vraiment compte : Qwen 3.8 27B, c’est du niveau d’Opus 4.6 en local, avec +200 t/s sur une 5090 et autour de 40–50 t/s sur un DGX Spark. C’est assez fou. SOTA en code askip ! Je le passe sur le billard pour le bench sur mon EVO X2 : pour l’instant je tourne autour de 20 t/s Et forcément je me dis : wen Qwen 35B MoE ?? Je vais pouvoir en profiter à fond, et on va se régaler en API Un mot : trop fort.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_382cd4c6d1b62d5dced4",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_b375c071aea9f486e307"
        },
        {
          "author_group_id": "ag_4aa33a45b601833780c0",
          "discourse_keys": [],
          "evidence_id": "e_7bf2b00568b0b35889cd8dcd",
          "excerpt": "#Qwen 3.8 27b is finally out: https://t.co/EcQ7dBBVWM https://t.co/aEcdS1qtOW",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_284bcb9f4412c21c0538",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_590ab97273ffffffb67c"
        },
        {
          "author_group_id": "ag_d93179cd0926f675716c",
          "discourse_keys": [],
          "evidence_id": "e_97201f0fa7e4ebd44a565276",
          "excerpt": "Appreciation post for @Alibaba_Qwen Qwen 2.8 27B beating Opus 4.6 in many benchmarks is just amazing!!🤩 We are now running SOTA model at home 🔥 can you believe that? https://t.co/0NUYtkwXsI",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_91567e92e30628b38f60",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_16edea736b9534acbac7"
        },
        {
          "author_group_id": "ag_1f6fb7fb1dfa56b1786c",
          "discourse_keys": [],
          "evidence_id": "e_435967f49e6fbf894c7068bb",
          "excerpt": "Qwen 3.8 27B Finally https://t.co/RYGI0QlK9u",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_c4726b831fd68f4b2603",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_0de5e57c2b5443ec7bfe"
        },
        {
          "author_group_id": "ag_6cdecf0e32afae192037",
          "discourse_keys": [],
          "evidence_id": "e_b554e4910698da6b7022bc0c",
          "excerpt": "@CardilloSamuel And now it’s qwen 3.8 27b Next week it’ll be qwen 4.8 35b moe",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_f32f39434a3d0fcbbd42",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_947eda0ac9f8abc8a9f6"
        },
        {
          "author_group_id": "ag_e322efe0dcce5725cb86",
          "discourse_keys": [],
          "evidence_id": "e_115607a7e67d2c344665ca66",
          "excerpt": "Watited but Launched QWEN 3.8-27B",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ce2dbe01e6ec1b5f5195",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_75fa66874d394f7b2ce8"
        },
        {
          "author_group_id": "ag_ea42ea478a29cecad94b",
          "discourse_keys": [],
          "evidence_id": "e_20905a9396416b3dff3dfee2",
          "excerpt": "qwen on demon time",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_a074f3a74e8ab1031191",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_22546375e6e5045e30a5"
        },
        {
          "author_group_id": "ag_8113dc65d1f62d81dc9c",
          "discourse_keys": [],
          "evidence_id": "e_a48850beb738ef9876669fd9",
          "excerpt": "HF's summer 2026 report in one line: the frontier is Chinese and huge, but most installs are still small and Qwen-shaped. Chinese labs now ship the largest open model almost every month. US labs are mostly converting and optimizing those weights for their own chips. Likes and downloads barely overlap. One repo makes both top-25 lists. People heart the 2T drop. But they still download the 6-year-old MiniLM. Qwen is the base model now: a whopping 151k derivatives. Full family, Apache 2.0, every week another release. That's why the 27B matters more than the 2.4T for most of us. Small models still do most of the work. llama.cpp is the only reason the giant ones show up locally. Also noteworthy: agents are becoming the Hub's real user. The client mix is changing every month. We keep talking about the biggest model. But this report is about who got embedded. 👇",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_bdbbe9440dee2a9f2033",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_98ff8ae226d7a12b793c"
        },
        {
          "author_group_id": "ag_013cf3d030d0f515c135",
          "discourse_keys": [],
          "evidence_id": "e_edad26ba177539b857a945a4",
          "excerpt": "来了 Qwen 3.8 27B 来了 。https://t.co/uS7Rh1KoPw",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_91346e2ef58b11f603c6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_509f3cadd15c5de2e1e6"
        },
        {
          "author_group_id": "ag_337668df23af2ff80541",
          "discourse_keys": [],
          "evidence_id": "e_38a38f02629076a3168debc5",
          "excerpt": "Qwen3.8-27B made a surprisingly large jump over Qwen3.6! This made me curious: how close is a 27B model to the real frontier? ChatGPT collected for me the published results from Qwen, OpenAI, Anthropic, DeepSeek and Google into one comparison table. It is interesting as it shows how much closer the small qwen got to the grown-up models.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_bc086e22fc1f1f24e155",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c294f7d39f17d8ac3f6d"
        },
        {
          "author_group_id": "ag_6d3132b08d0ffc98c820",
          "discourse_keys": [],
          "evidence_id": "e_fe254b5794fb1c7ceba381ab",
          "excerpt": "qwen is out 👀 https://t.co/RCEAHEWkUq",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_81cb7f119cd6b94e75d1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_d8063816745e67064270"
        },
        {
          "author_group_id": "ag_ace0b64eeeb0b419a0f6",
          "discourse_keys": [],
          "evidence_id": "e_a12c011c5fa958ba7870c1f3",
          "excerpt": "@jun_song what does super qwen mean",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_c88a4ec69e83ef1ef48b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_3d65fd6a7bdb73a4287d"
        },
        {
          "author_group_id": "ag_fb5a1c6b9ab36baa6606",
          "discourse_keys": [],
          "evidence_id": "e_d29944cb752c09274b4956a4",
          "excerpt": "Qwen 3.8 27B OUT NOW https://t.co/MUUrfqGTHX https://t.co/ORvaBbn5zz",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_e93be192a2c44bda9da5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_cc88e7e25398050c249d"
        },
        {
          "author_group_id": "ag_27f9ff801cc1b0415e71",
          "discourse_keys": [],
          "evidence_id": "e_b262fcf3103d6df4d10dee96",
          "excerpt": "Hier sieht man den Vergleich grafisch. Fazit: Qwen 3.8 27B ist schneller mit den Tasks fertig und braucht dafür weniger Token. Ja, das MoE Modell 35B A3B ist schneller, aber auch schlechter. https://t.co/BCaXmPZcyn",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3db8cc754aef553fe6fb",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_280c2352c7faf1a70638"
        },
        {
          "author_group_id": "ag_8113dc65d1f62d81dc9c",
          "discourse_keys": [],
          "evidence_id": "e_9d84ef0c1a750d18240b1a7e",
          "excerpt": "Qwen3.8-27B is the drop of the week that actually matters for local AI. It's a compact, deployment-friendly model with native vision-language. Images and video support from day one, not bolted on later. Qwen is calling this the most capable generation in the open family after 3.5 and 3.6. The pitch is: coding, professional work, research, and long-horizon agentic tasks. Better planning. Better use of environment feedback. More reliable end-to-end completion. Plus flexible thinking control for multi-step work. That's the gap most 27B models still lose on. Can’t wait to fire this up on my DGX Spark with Hermes 🔥",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7fe1f86470e02d432c16",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_a91b3ed85f495c6caaf2"
        },
        {
          "author_group_id": "ag_67aafe2e91277c0651c2",
          "discourse_keys": [],
          "evidence_id": "e_f2901b4fae7939345df672cb",
          "excerpt": "@PengQihang87687 Congratulations! Thrilled to see the return of the open-source queen Qwen!",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d8fd4f3eff2ab8e4b4f5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_553db1d4f04e44e77a03"
        },
        {
          "author_group_id": "ag_4461970c9a5da483dcb4",
          "discourse_keys": [],
          "evidence_id": "e_612a89a56f489f850c502b1d",
          "excerpt": "qwen 3.8 27b is out",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_04ce9e5486327e5be45b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_131af1e26a9c3eda9a45"
        },
        {
          "author_group_id": "ag_c26b53c8b7415d75d21f",
          "discourse_keys": [],
          "evidence_id": "e_3fc87f4f05214fab4fda7771",
          "excerpt": "I want to thank Alibaba for releasing such an amazing model Qwen 3.8 27B, and Unsloth for the quants, and also ModelScope (Also Alibaba)/Huggingface for keeping up with the demand! https://t.co/IMCfd89N3L",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ea74c4c27b15c0d944e4",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8aa37257db48e4f7d4c9"
        },
        {
          "author_group_id": "ag_45ab8f6e304487e2352a",
          "discourse_keys": [],
          "evidence_id": "e_c60c9c8d8f0dbc04e9798ff9",
          "excerpt": "qwen 3.8-27B finally out! 55.6 GB 🗣️ https://t.co/M9Yw4Gx2Ho",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_2bb991325061efd1605c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_67fdcb40f0c8b508464a"
        },
        {
          "author_group_id": "ag_fff736e4e72cb9f7915c",
          "discourse_keys": [],
          "evidence_id": "e_c64f746bdf7def6f8eac78d7",
          "excerpt": "Qwen-3.8-27B weights are available! Downloading in progress https://t.co/uA1gsoOLm9",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_be922e48f3f99677bfde",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_541edad37ec70711d346"
        },
        {
          "author_group_id": "ag_813b650d388768314a0f",
          "discourse_keys": [],
          "evidence_id": "e_1bf5200a023d6d8e9bd2fe11",
          "excerpt": "these qwen 3.8 27b scores are crazy high? https://t.co/p8JZDqNSaB",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_b1654310c2192907626a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_4a730c163bce77b274ca"
        },
        {
          "author_group_id": "ag_e6f7ec80f0fa42c0fc3b",
          "discourse_keys": [],
          "evidence_id": "e_de202a7624390458952b08f5",
          "excerpt": "Me downloading Qwen3.8 (31GB) on an ADSL network \"8h remaing\", giving me some real 2000 nostalgia vibe What was I thinking going to the back of beyond on new Qwen release day https://t.co/IsxvIR1rnr",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_4aa525b4f56b1da821b9",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_956244568f7f7a7e432b"
        },
        {
          "author_group_id": "ag_3a20a69326d618a199c8",
          "discourse_keys": [],
          "evidence_id": "e_39c7231f15071bb8ad551080",
          "excerpt": "Qwen 3.7 27B きたーーーーー https://t.co/sCgyyIdKiQ",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_6da369e2c7e110921f3a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_fe2747810b8b31be8d4f"
        },
        {
          "author_group_id": "ag_a317c0022418104c766f",
          "discourse_keys": [],
          "evidence_id": "e_67a55f1a76b23fb158353723",
          "excerpt": "qwen 3.8 27b: thinking mode burned 26k tokens on a simple quiz that takes 14 seconds without it. verbose reasoning is the feature and the tax at once. on local hardware you pay in wall-clock minutes, which makes the waste impossible to ignore.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_60e694f9fb59ec09ff7c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_ca1ae757c8a7e1d401dc"
        },
        {
          "author_group_id": "ag_a01e84441cb155a554cc",
          "discourse_keys": [],
          "evidence_id": "e_2b5fb917bb085c7ac31701a1",
          "excerpt": "Qwen 3.8 27b is here https://t.co/lxXBePVi41 https://t.co/O7mPI6wmsh",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_5325233e5ef0b9cd80a2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_fddb28e7e081b2208732"
        },
        {
          "author_group_id": "ag_21f44a5f4c4a52c718ac",
          "discourse_keys": [],
          "evidence_id": "e_3104ac37081b6303d4ee245d",
          "excerpt": "200+ tok/s for Qwen 3.8 27b 🥲",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_9be59e4225717b65945d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_51f2fd1af6d431e57aac"
        },
        {
          "author_group_id": "ag_844a085b9dc7af646011",
          "discourse_keys": [],
          "evidence_id": "e_27c8a45973dd6ba7cc02fbb0",
          "excerpt": "@HENKOWISH @loktar00 @qwen @QwenDevs bahaha t'as test en mlx ou pas la déjà",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0db90829bba83cbd1d3a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_179c4503f9fac8895e60"
        },
        {
          "author_group_id": "ag_24279b401c5ff5a82985",
          "discourse_keys": [],
          "evidence_id": "e_8422bcf615bf85256726b45c",
          "excerpt": "Qwen 3.8 27B試さなきゃ！",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a3d80901c0b6ac7ecfb7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_94b3b70dc79f84b050e6"
        },
        {
          "author_group_id": "ag_ea74fbdbb56f4ddcb386",
          "discourse_keys": [],
          "evidence_id": "e_7dfc4858f6aee15dc1f6fb74",
          "excerpt": "@0xZKnw @loktar00 @qwen @QwenDevs Mdrr qu’il finisse de me load le html le reste on en reparlera",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_bd9c836b10da0c78efc3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_308f7da59c11ec7bd9d6"
        },
        {
          "author_group_id": "ag_a65cb862d9e490fac81e",
          "discourse_keys": [],
          "evidence_id": "e_862839241682916d50a7496e",
          "excerpt": "Vivimos en un mundo bien distinto al de hace apenas unos meses. Qwen 3.8 justo liberó sus weights y ya puedes correr en una laptop un modelo que lo hemos vistoen comparativas compite con modelos cerrados de primer nivel Hace 6 meses hablar de IA local todavía sonaba a experimentopara raza con mucho tiempo libre. Hoy hablamos de modelos realmente capaces y privados sin tener que pagar cada token and the good news es que es just the beginning Si hoy ya se puede correr esto en la lap, qué podremos hacer en una mac mini en 12 meses? Confienzo que no me he ocupado en entender cómo funciona la IA local pero hoy comienzo Estoy seguro que esto no es un tema de moda, esto viene por todo.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_7c85b83d73c845ef75c0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_7618279d91910457a5fe"
        },
        {
          "author_group_id": "ag_1b5698383a06dd2841d1",
          "discourse_keys": [],
          "evidence_id": "e_7a872eaa3d41f2e198fc2840",
          "excerpt": "Qwen 3.8 27B、Opus4.6 Maxよりも高いパフォーマンス出してて、頭がやばい https://t.co/9olhNxiEol",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_eef5663aefad31fd137c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_65de52bf272fa2d90f78"
        },
        {
          "author_group_id": "ag_939559696b080a9c7640",
          "discourse_keys": [],
          "evidence_id": "e_6f18de926581b62488163ec0",
          "excerpt": "@Yuchenj_UW qwen 3.8 27b🚀",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_65213b567e990a0ae7e3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_3a222df4f4010c88717b"
        },
        {
          "author_group_id": "ag_2c676b1fd709dfda360a",
          "discourse_keys": [],
          "evidence_id": "e_85f8b87aba5c7d1beb7c3929",
          "excerpt": "Finally its here!!!!! Qwen 3.8 27b https://t.co/hdYoHct6V7",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_e1d8e4ee3d4748404e3b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_ca66eb4f5c8b93e1ec56"
        },
        {
          "author_group_id": "ag_b618d14fa1e06a2ba065",
          "discourse_keys": [],
          "evidence_id": "e_89c868e660004e1df31f36a4",
          "excerpt": "QWEN 3.8 27B LETSS GOOO https://t.co/vlp1SHM5os",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_e9d80c568acc4f82ea11",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_58cd1aed2e2577d26176"
        },
        {
          "author_group_id": "ag_171b2582c08b46d2e02e",
          "discourse_keys": [],
          "evidence_id": "e_f8f53acbaad6f5cc02544147",
          "excerpt": "@ViralScroll Guys who fucking cares Qwen 3.8 27B is out!",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_8542b0e6a1a0b4b5de79",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_df7e109c768a258bee42"
        },
        {
          "author_group_id": "ag_b2327478abee76cfd37b",
          "discourse_keys": [],
          "evidence_id": "e_de7e9c2265b8b585de844360",
          "excerpt": "Qwen 3.8 is ~Opus 4.6 level on 27B. Blows Meta's Muse out of the water https://t.co/beRylU89Mu",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_116e904f809970f23d3a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_2cbbb78d19dd42025156"
        },
        {
          "author_group_id": "ag_7fb494eec4fda7696169",
          "discourse_keys": [],
          "evidence_id": "e_1bec6714f022d28e99ca7fb9",
          "excerpt": "@ivanfioravanti My unsloth download crashed and now I’m babysitting qwen file. What to add into LM Studio?",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3d231a8988be5849fa9d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_d98704798bc9c7df9138"
        },
        {
          "author_group_id": "ag_3e2e3a332607f3bc8ccf",
          "discourse_keys": [],
          "evidence_id": "e_f18a6acb501f7f9c8364df62",
          "excerpt": "Qwen 3.8-27B 来た！",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_029aacb7f3c4ae0230eb",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_ef8cd7e3df8486780507"
        },
        {
          "author_group_id": "ag_ff4b3cb6a88f67b3066d",
          "discourse_keys": [],
          "evidence_id": "e_bbbcc4bd70b78a253aa6ce6a",
          "excerpt": "🔴 ¡QWEN 3.8 27B LIBERADO! A finales de 2025 modelos como Opus 4.5 le abrió los ojos al mundo en cuanto a las capacidades de lo que la IA agéntica podía hacer, sobre todo en programación. Hoy ya puedes ejecutar un modelo superior directamente en tu portátil, en local 🔥",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_348122ac9ff389d0cc9d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a1a10c93e278d99567c5"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "lead",
        "available_independent_source_count": 78,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 81,
        "selected_count": 48,
        "story_rank": 1,
        "target_count": 48
      },
      "evidence_support": {
        "distinct_author_group_count": 46,
        "distinct_source_cluster_count": 48,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 2
      },
      "family_facts": {
        "volume": {
          "change_pct": "142.209073",
          "comparison_state": "available",
          "prior_authors": 855,
          "prior_count": 1014,
          "selected_authors": 1698,
          "selected_count": 2456
        }
      },
      "kind": "episode",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "qwen:60-69",
          "direction": "increase",
          "display_en": "142%",
          "display_zh_cn": "142%",
          "fact_id": "qf_9122776307bd31c332fd6305",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "142.209073",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "episode_rank": 1,
          "family": "volume",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-08-14T15:00:31Z"
    },
    {
      "brand_key": "glm",
      "candidate_id": "glm:22-26",
      "coarse_series": {
        "author_counts": [
          25,
          117,
          236,
          157,
          154,
          144,
          78,
          57
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            25,
            141,
            278,
            172,
            174,
            162,
            79,
            64
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                7,
                53,
                104,
                51,
                50,
                37,
                17,
                16
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                18,
                88,
                174,
                121,
                124,
                125,
                62,
                48
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          25,
          141,
          278,
          172,
          174,
          162,
          79,
          64
        ]
      },
      "display_name_en": "Zhipu GLM",
      "display_name_zh_cn": "Zhipu GLM",
      "end_at": "2026-08-14T06:45:31Z",
      "episodes": [
        {
          "baseline_post_count": "9.500000",
          "end_at": "2026-08-14T06:45:31Z",
          "end_bucket_index": 26,
          "episode_id": "glm:22-26",
          "peak_author_count": 43,
          "peak_post_count": 49,
          "peak_to_baseline": "5.157895",
          "post_count": 195,
          "start_at": "2026-08-14T05:30:31Z",
          "start_bucket_index": 22
        }
      ],
      "evidence": [
        {
          "author_group_id": "ag_cee47ba79ea5a1dfbf35",
          "discourse_keys": [],
          "evidence_id": "e_33622bb100d69a32cbcf9104",
          "excerpt": "🧩 DeepSeek × Peking University: Can an Agent Rewrite Its Own Runtime Without Restarting? DeepSeek’s new open-source Harness makes almost everything replaceable: the model adapter, tools, session manager, filesystem, and even the Agent loop itself. That raises a harder question: how can an Agent modify its own runtime without leaving broken dependencies or hidden state behind? Zhihu contributor 段小草 argues that the most important part may not be the Harness itself, but Cordis, the runtime beneath it. 1️⃣ The idea predates the Agent boom Cordis did not begin as an AI project. Its concepts grew out of years of work on Koishi, an open-source chatbot framework with a large plugin ecosystem. Managing thousands of plugins exposed a recurring problem: installing a component is easy, but removing it cleanly is not. The new DeepSeek and Peking University paper, A Programming Paradigm for Spatiotemporal Composability, turns those engineering lessons into a formal programming model. 2️⃣ Why self-ev",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_1d507b7697b2daad338a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": true,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_3010d8c55cc26eda83ac"
        },
        {
          "author_group_id": "ag_7d66b5d725676340c84f",
          "discourse_keys": [],
          "evidence_id": "e_12281b6bcb19f3949599c028",
          "excerpt": "梁圣的 DeepSeek 重磅发布 Harness：https://t.co/ncvX4M6bGJ 最大特色：一切皆插件！ 开发者不需要改源码，只通过配置就能组合AI能力，现在社区插件排名： 1. colleague-skill 同事 Skill https://t.co/dcWqJ0Ue39 将冰冷的离别化为温暖的 Skill。提供飞书/钉钉/Slack 消息、文档、邮件、截图 + 主观描述，生成真正能替该同事工作的 AI Skill，支持数字生命传承。 2. iPolloWork AI 工作台 https://t.co/jmUFSiOUQj 下一代本地优先可视化 AI 工作台。从一个目标产出可继续编辑的代码、文档、演示稿、网站、设计与视频。定位 Codex / Claude Code 的开源平替。 3. OpenBiliClaw 内容发现 Agent https://t.co/630lKzuILX 本地私有、开源的自进化跨平台 AI 内容发现 Agent。先理解用户兴趣，再主动从 B站、小红书、抖音、YouTube、X、知乎、Reddit、微博等平台与开放 Web 寻找内容。支持 DSH 插件。 4. deeptide macOS Coding Agent https://t.co/tSPBY3LWRx Built by DeepSeek, for DeepSeek。Swift 原生 macOS 编程 Agent，深度对接 DeepSeek 模型与 Harness。 5. dsh-web-ui Web UI 增强合集 https://t.co/2WHTJhccKB DSH Web UI 插件与皮肤大合集：任务看板、Git 图谱、右侧面板、远程/移动端 UI、鲸鱼娘宠物、实时 Token 统计、皮肤中心。可单独或一键全家桶安装。 6. mobius 自进化 Agent OS https://t.co/kbRrRDgkzX 第一个自进化开源 Agent OS。连接团队、AI Agents、设备与算力，定位完整的 Agent 操作系统。 7. modlens 视觉插件 https://t.co/GAdtYwrq6b 全网第一个 DeepSeek Harness 视觉插件。给纯文本模型装上“眼睛”：直接粘贴图片即可获得 OCR + 布局 + 语义结构化 JSON 证据，",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_1c2561c03f29e1e0e235",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_946440c795d44bfe66c1"
        },
        {
          "author_group_id": "ag_1a8378bc84ae2cbbe732",
          "discourse_keys": [],
          "evidence_id": "e_61c6c42e453e521df1901ba4",
          "excerpt": "@Q_Beaux @NVIDIAAI GLM 5.3 is here https://t.co/HlXySErFzG",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_f2b4dea0810b674573f2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_9f255b0a782d9bdd794b"
        },
        {
          "author_group_id": "ag_44696843837085697006",
          "discourse_keys": [],
          "evidence_id": "e_649a90b8d9c0fb40f693f381",
          "excerpt": "China is starting to harden, courtesy of Tsinghua. The US is going in on the attack. (\"Criminal entities\" are, for example, labs doing distillation, GPU smugglers… it's easy to trespass the extraterritorial US law). Everything is developing as foretold. Eurosisters, your move? https://t.co/MyGcLnc9j6",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0734d389185a49ba9885",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_1b381f369a0f77c455a9"
        },
        {
          "author_group_id": "ag_8e1671336216254929fb",
          "discourse_keys": [],
          "evidence_id": "e_12988a719d27aec99beda7bb",
          "excerpt": "What a wild week with so many new AI models... Gemini 3.7 Flash Grok 4.6 GLM 5.3 DeepSeek V4 Pro GA Muse Glimmer 30B AI summer is not for the weak!",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d92500af6e18c161028f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_3535d3f07b704c207010"
        },
        {
          "author_group_id": "ag_5d77ac5a9e5a65ecb587",
          "discourse_keys": [],
          "evidence_id": "e_1f3ea4b813740b181cc76423",
          "excerpt": "@ollama @Zai_org GLM 5.3은 코딩용 메인 드라이버로 사용할 수 있을 것 같아서 기대됨.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_6fcd8bb10d495889fb50",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_ce59f8a987a06b2aff64"
        },
        {
          "author_group_id": "ag_b34c5ae9e74c05bea0bb",
          "discourse_keys": [],
          "evidence_id": "e_e0dad67f61ea55fc81929cf9",
          "excerpt": "@MiniMax_AI now it's your turn buddy 🫵🏻",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_ffe93624076e600a98fd",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_bfbedee6dac148afd186"
        },
        {
          "author_group_id": "ag_7cc2076bfb6ed240c3af",
          "discourse_keys": [],
          "evidence_id": "e_f75e0dca08ae2e440a8ea381",
          "excerpt": "🚨 New GLM-5.3 is out ▸ Third place on Terminal bench 🥉 ▸ One million tokens context window ▸ Performance is around Fable 5 and Sol 5.6 level at a fraction of the cost. The @Zai_org team's new model is off to a good start. Let's see if those results get confirmed by user! https://t.co/Npjxt3aIVr",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_92c205c68afe7be047ee",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_84f55659f1e73686f4b6"
        },
        {
          "author_group_id": "ag_9ef8b67a7bbec3f4b83f",
          "discourse_keys": [],
          "evidence_id": "e_8d1f7a473ba3cf9bf88e64b3",
          "excerpt": "@Zai_org Most people will test the new GLM on coding. I’m more curious about the cyber defense claims. Open models getting this good at vulnerability work feels like it changes the game quietly.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_adcac9f427b6e2d35229",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_b064958203b9ced5c5fe"
        },
        {
          "author_group_id": "ag_6a9691129d0d58f9deb5",
          "discourse_keys": [],
          "evidence_id": "e_16616093efd105d3e0dc8723",
          "excerpt": "@Zai_org GLM-5.3: coding/agent post-train + cyber benches; open weights after safety. Vendor evals until independent tickets confirm.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_c397d5c65f311b60302f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c351430609121c7acef7"
        },
        {
          "author_group_id": "ag_62508b1c3697c5ef760a",
          "discourse_keys": [],
          "evidence_id": "e_830f75e68f673b798f648dba",
          "excerpt": "@Zai_org just announced GLM-5.3 🌊 https://t.co/VBbKn9KE4F",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_40f6c6f0c88335f2fce0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_690cd10f72b2f9b178b7"
        },
        {
          "author_group_id": "ag_66b0191778a7f4f848b4",
          "discourse_keys": [],
          "evidence_id": "e_ebafe16aee0804d2df355c96",
          "excerpt": "@opencode Will people use GLM 5.3 more or DeepSeek Pro?",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_20f7e67a66e6a9aed74d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_4ae95a95934dc7dead23"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 46,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 65,
        "selected_count": 12,
        "story_rank": 3,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 1
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "none",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "absurdist_meme",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "advertising-marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "ai_slop_critique",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "cope",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "dunk_yingyang",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "fud",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "genuine_hype",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "sarcasm",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "self_deprecation",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "advertising_marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "buzz_releases",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "feedback_questions",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "hands_on_usage",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "performance_comparisons",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "negative",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "neutral",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "positive",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "none",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 293,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1095,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "273.720137",
          "comparison_state": "available",
          "prior_authors": 265,
          "prior_count": 293,
          "selected_authors": 850,
          "selected_count": 1095
        }
      },
      "kind": "episode",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "discourse": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "sentiment": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "glm:22-26",
          "direction": "increase",
          "display_en": "274%",
          "display_zh_cn": "274%",
          "fact_id": "qf_f27150fc2b06a7edd9e15f06",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "273.720137",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "episode_rank": 1,
          "family": "post_type",
          "rank": 2,
          "stream_position": 2
        },
        {
          "episode_rank": 1,
          "family": "discourse",
          "rank": 2,
          "stream_position": 2
        },
        {
          "episode_rank": 1,
          "family": "sentiment",
          "rank": 2,
          "stream_position": 2
        },
        {
          "episode_rank": 1,
          "family": "nationalism",
          "rank": 2,
          "stream_position": 2
        },
        {
          "episode_rank": 1,
          "family": "volume",
          "rank": 4,
          "stream_position": 4
        }
      ],
      "start_at": "2026-08-14T05:30:31Z"
    },
    {
      "brand_key": "minimax",
      "candidate_id": "minimax:43-43",
      "coarse_series": {
        "author_counts": [
          157,
          156,
          173,
          218,
          188,
          136,
          92,
          83
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            195,
            189,
            201,
            250,
            220,
            167,
            105,
            101
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                46,
                29,
                32,
                52,
                36,
                30,
                15,
                13
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                149,
                160,
                169,
                198,
                184,
                137,
                90,
                88
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          195,
          189,
          201,
          250,
          220,
          167,
          105,
          101
        ]
      },
      "display_name_en": "MiniMax AI",
      "display_name_zh_cn": "MiniMax AI",
      "end_at": "2026-08-14T11:00:31Z",
      "episodes": [
        {
          "baseline_post_count": "14.000000",
          "end_at": "2026-08-14T11:00:31Z",
          "end_bucket_index": 43,
          "episode_id": "minimax:43-43",
          "peak_author_count": 42,
          "peak_post_count": 46,
          "peak_to_baseline": "3.285714",
          "post_count": 46,
          "start_at": "2026-08-14T10:45:31Z",
          "start_bucket_index": 43
        }
      ],
      "evidence": [
        {
          "author_group_id": "ag_08b66cdfaac4ee791a73",
          "discourse_keys": [],
          "evidence_id": "e_867879e79c3001720bb1b379",
          "excerpt": "Finally got my dream setup running on my Macs. Deepseek flash via dwarfstar on a dedicated m3 max, openwebui + hermes for interfacing+multimodal agents, flux for image gen, minimax video music for local video + music.",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_84280d5959a603bb85b2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_ecf12d66473c6a7267dc"
        },
        {
          "author_group_id": "ag_4cfe533d8ac75543f90d",
          "discourse_keys": [],
          "evidence_id": "e_bef2db267adc53fba8bd70f7",
          "excerpt": "Lo más difícil del vídeo con IA ya no es crear una toma espectacular. Es mantener personajes, estilo y narrativa durante toda la secuencia. MiniMax H3 apunta justo a eso, y ahora está al 50% en 2K hasta el 1 de septiembre 🔥",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_8c7b08feab48d770486d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_43f265b191e95c14f6a4"
        },
        {
          "author_group_id": "ag_c72b0ec9cc1ec43b52b8",
          "discourse_keys": [],
          "evidence_id": "e_951706f88f267da50033b53b",
          "excerpt": "In the near future, there will be only one way to prove you are a human. Generated locally with Minimax H3. https://t.co/M9CJcilNl5",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3bb789e0fc6bc7dbf429",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_06c360979b9e893e4d60"
        },
        {
          "author_group_id": "ag_3bfb1a7c56f7d565fd1c",
          "discourse_keys": [],
          "evidence_id": "e_132cd924238fddd7132cbb70",
          "excerpt": "@MarcosBear13660 I used MiniMax H3 running locally in comfyUI.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d1ed40682b934aa3b854",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_4fe1b1ec3b6374432ee6"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "floor",
        "available_independent_source_count": 37,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 46,
        "selected_count": 4,
        "story_rank": 6,
        "target_count": 4
      },
      "evidence_support": {
        "distinct_author_group_count": 4,
        "distinct_source_cluster_count": 4,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "volume": {
          "change_pct": "10.526316",
          "comparison_state": "available",
          "prior_authors": 925,
          "prior_count": 1292,
          "selected_authors": 1017,
          "selected_count": 1428
        }
      },
      "kind": "episode",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "minimax:43-43",
          "direction": "increase",
          "display_en": "11%",
          "display_zh_cn": "11%",
          "fact_id": "qf_4d66a4e132c70f0bd14ce465",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "10.526316",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "episode_rank": 1,
          "family": "volume",
          "rank": 3,
          "stream_position": 3
        }
      ],
      "start_at": "2026-08-14T10:45:31Z"
    },
    {
      "brand_key": "hunyuan",
      "candidate_id": "hunyuan:full_window",
      "coarse_series": {
        "author_counts": [
          2,
          2,
          4,
          5,
          5,
          1,
          4,
          2
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            2,
            2,
            4,
            5,
            5,
            1,
            4,
            2
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                1,
                1,
                1,
                0,
                0,
                1,
                1,
                2
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                1,
                1,
                3,
                5,
                5,
                0,
                3,
                0
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          2,
          2,
          4,
          5,
          5,
          1,
          4,
          2
        ]
      },
      "display_name_en": "Tencent Hunyuan",
      "display_name_zh_cn": "Tencent Hunyuan",
      "end_at": "2026-08-15T00:00:31Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_d88caec99dc3a6a33d14",
          "discourse_keys": [],
          "evidence_id": "e_3dae42ce4a7546639bab074a",
          "excerpt": "一个免费的仓库，拥有近 8K 星标，刚发布了一个完整的 AI 视频研究，完全在你的 PC 上运行。 只需 6GB VRAM 就能运行……即使在老旧 GPU 上！ 内置 Wan 2.2、LTX-2、Hunyuan Video 和 Flux。 零云端上传，零订阅，零水印。 如何用 3 个步骤安装： 克隆仓库 运行一键安装程序 打开浏览器并生成 在整个 2026 年，你找不到比这更好的免费东西了。 趁它还没爆火，赶紧分享！",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_35275aa624566c1de8ec",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_3a7465209101ef79f2e8"
        },
        {
          "author_group_id": "ag_cc4dd48fcb075c15807e",
          "discourse_keys": [],
          "evidence_id": "e_9abe3ba5c9e2fd8a03e45eb0",
          "excerpt": "Pika เปิดตัว Pika Audio 4 โมเดลเสียง AI ชูต้นทุนต่ำกว่าคู่แข่งสูงสุด 20 เท่า Pika เปิดตัว Pika Audio ชุด Foundation Model ด้านเสียง 4 โมเดล ได้แก่ Pika Soundtrack, Pika Music, Pika SFX และ Pika Speech ครอบคลุมการสร้างเสียงประกอบวิดีโอ เพลง ซาวด์เอฟเฟกต์ และเสียงพูด โดยเปิดให้ใช้งานผ่าน Pika API Club จุดขายสำคัญคือด้านต้นทุน โดย Pika ระบุว่า Pika SFX ประหยัดกว่าทางเลือกอื่นสูงสุด 20 เท่า, Pika Music สูงสุด 10 เท่า และ Pika Speech ประหยัดกว่า ElevenLabs v3 ราว 9 เท่า ขณะที่ Pika Soundtrack มีต้นทุนต่ำกว่า Hunyuan Foley ราว 2 เท่า บริษัทระบุว่าต้นทุนที่ลดลงมาจากการพัฒนาเทคนิคด้าน Training และ Inference Efficiency ซึ่งช่วยให้การสร้างเสียงด้วย AI มีราคาถูกลง การเปิดตัวครั้งนี้สะท้อนว่า Pika กำลังขยายจาก AI สำหรับสร้างวิดีโอ ไปสู่แพลตฟอร์ม Generative Media ที่ครอบคลุมทั้งภาพและเสียง พร้อมผลักดันการแข่งขันในตลาด Generative AI จากเรื่องคุณภาพของโมเดล ไปสู่เรื่อง ต้นทุนในการผลิตคอนเทนต์ในระดับอุตสาหกรรม มากขึ้น แหล่งที่มา: https://t.co/2JWj4vRine ข้อมูลเพิ่มเติม: https://t.co/PyTxvMG7Cp",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_636510102ed85b30700d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_b53c0f5f440569cc6c96"
        },
        {
          "author_group_id": "ag_acb9037e65fb234a9100",
          "discourse_keys": [],
          "evidence_id": "e_9373be4a46e6be730a68d2f0",
          "excerpt": "@mintdotgg nice very cool i also run https://t.co/cUA8lNNzna looks like hunyuan was best here idk? rodin?",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a70fa7124db1bd048799",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_89420614f46ba0ccc9aa"
        },
        {
          "author_group_id": "ag_f24785fcb01ee5918734",
          "discourse_keys": [],
          "evidence_id": "e_1c159df371f4ff617ed91951",
          "excerpt": "🚨Tencent Hunyuan senior researcher Xu Can has joined the WeChat WeLM team to work on large model R&amp;D WeChat is also hiring for WeLM inference optimization &amp; Agent roles His move is expected to further strengthen WeLM’s capabilities in training/inference/complex task execution https://t.co/cKL61Bm2LQ",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_1bcdf0feec4729f017f2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_500c403295bab278735d"
        },
        {
          "author_group_id": "ag_44696843837085697006",
          "discourse_keys": [],
          "evidence_id": "e_5eeaa1a366b976600a1f1854",
          "excerpt": "I think they are seriously underrated Their first model was crazy impressive as a piece of research",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_750570ba5bfa6687811b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_10caa03aa36d66ecdfa9"
        },
        {
          "author_group_id": "ag_3c5b7e5db0a7a1823fd1",
          "discourse_keys": [],
          "evidence_id": "e_5ef290626fa74f95cb28253a",
          "excerpt": "The five TBC posts that traveled furthest this week all circled the same hard question: when AI moves from demo to deployment, who gets paid, and who gets squeezed. 1. ByteDance’s Doubao is now charging a separate channel service fee on transactions it routes, roughly 12% for hotel bookings and 18% for some lifestyle services. The policy took effect August 10, and Doubao has clarified it does not accept paid promotion. The revenue is small, daily e-commerce GMV was reportedly around RMB 10 million (~$1.4 million) in the first half of 2026, but the real work is attribution: ByteDance wants to know whether AI generates incremental demand or just reshuffles existing bookings. https://t.co/D1Hah3NFcz 2. Microsoft Copilot reached 30 million paid seats across Office 365’s 450 million commercial base, only 3.3% penetration. That is up from 15 million earlier in the year, fast growth from a low base, but the number is a warning for China’s standalone model companies. Even embedded in the world",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_d229274f09fd173c9df1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_7b07edc3fcf1f30bd05e"
        },
        {
          "author_group_id": "ag_ccc3e98952f2fc9713ce",
          "discourse_keys": [],
          "evidence_id": "e_8f8917955211e9bd33e44409",
          "excerpt": "🔥 Live Free Models Supported: • ⚡ DeepSeek V4 Flash Free (with reasoning) • 🚀 NVIDIA Nemotron 3.5 Lightning (128k) • 🥒 OpenCode Big Pickle • 🌐 Tencent Hunyuan 3 Free • 🛡️ NVIDIA Nemotron 3 Ultra Works with OpenCode2 CLI, Claude Code, Cursor, and Continue.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_546d6e57bde414b83f49",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_475a9c2783e9581cf19d"
        },
        {
          "author_group_id": "ag_4d762a1bcb828b486c89",
          "discourse_keys": [],
          "evidence_id": "e_ebdd6c3f0fa342237d2013ec",
          "excerpt": "AI 3D MODEL SHOWDOWN Tripo P1 vs Meshy V6 vs Hunyuan V3.1 Pro vs Rodin 2.5 You guys loved the first one, so we’re running it back. Same image. Same prompt. One generation each. No cherry-picking. This time, we’re comparing geometry, textures, materials, and overall usability. The goal isn’t to find one “best” model, it’s to find which model is best for what you’re trying to create, or which style fits your project. Exact photo used is in the comments below.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_584f380971d4cbfe35af",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_95a9510d5ea944992ffc"
        },
        {
          "author_group_id": "ag_30c0e0b53b78c10486ba",
          "discourse_keys": [],
          "evidence_id": "e_ae5ef433627dbc0e15f8f169",
          "excerpt": "@catmanyau @metatransformr I tried before with unreal, was a hobby project nothing serious but it works. Now most likely today I'll test it again, will share results when I'm done, I'll open source it as well when I mature it a bit more. It is a xcom like turn based @threejs . I'll connect to my local qwen 3.6(3.8 coming today) nothing serious a 7900XTX and an old RTX3070 on a 10 year old PC later for TTS. My plan is AI commander in the mission controlling enemy soldiers. Also character enemy or mine doesn't matter talks depending on the situation like when I throw a granade and it damages my ally kinda thing so a GM AI. That GM AI will also control the general narrative after mission, one faction trying to build a mage weapon somewhere and creates a mission to grab the head scientist kind. And depending on the mission outcome story progress but AI will decide it. I'll also be adding factions 4 in total including me and 3 others will have AI faction leaders which they autonomously deci",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_2f045102f5dabf0618b0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_91d39a9cc45ac50de372"
        },
        {
          "author_group_id": "ag_01607916fbbfffcb0424",
          "discourse_keys": [],
          "evidence_id": "e_d989716e206231b06e580162",
          "excerpt": "🔥👀PIKA just messed with ai audio scene new 4 models, cheap, fast, uncensored Pika Soundtrack is priced 50% cheaper than Hunyuan Foley, the only model with comparable functionality Pika SFX is priced up to 95% cheaper than competitors (highest being ElevenLabs SFX) full thread",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_754f2e548788a0d4e4a0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_2d97a6f0b94d56ca8c08"
        },
        {
          "author_group_id": "ag_1a6183d01848aedfd75a",
          "discourse_keys": [],
          "evidence_id": "e_c059fb99c4931cae8d335cff",
          "excerpt": "THIS IS F**KING GOLD FOUND A OPEN SOURCE PROJECT FOR ANYONE WITHOUT A MONSTER GPU: WanGP. It's a one stop video—>image—>audio generator that runs Wan 2.1/2.2, LTX 2, Qwen Image, Hunyuan Video, Flux, and more all optimized to run on as little as 6GB of VRAM. Works on older Nvidia cards (RTX 10XX and up), AMD GPUs, and even GTX 10-series hardware most tools have completely given up on. Full web UI, LoRA support, quantized checkpoints (int8, fp8, gguf), a generation queue, and even an MCP server so your AI agents can trigger generations directly. FREE TO USE LOCALLY No subscription, no license fee just clone it and run. Repo below",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_df8ed68bb507ad99b540",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a21049d4d3e755d070e7"
        },
        {
          "author_group_id": "ag_691340f9635b2c9edfeb",
          "discourse_keys": [],
          "evidence_id": "e_1ac9b0e675a6ad602832c936",
          "excerpt": "We’re thrilled to be able offer prices this low, thanks to our team’s innovations in training and inference efficiency. A few highlights: • Pika Soundtrack is 0.617 / seconds and 2x more cost-efficient than Hunyuan Foley, the only model with comparable video-to-audio functionality. • Pika SFX is up to 20x more cost-efficient than alternatives. • Pika Speech is 9x more cost-efficient ElevenLabs v3, 4.5x more cost-efficient than Cartesia and ElevenLabs Turbo, and 2x more cost-efficient than Fish Audio. • Pika Music is up to 10x more cost-efficient than comparable music models.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_e0c4a4892e02fa84e23f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_35886bfcdf5d4c1c4628"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 25,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 25,
        "selected_count": 12,
        "story_rank": 4,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "none",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "absurdist_meme",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "advertising-marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "ai_slop_critique",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "cope",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "dunk_yingyang",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "fud",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "genuine_hype",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "sarcasm",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "self_deprecation",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "advertising_marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "buzz_releases",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "feedback_questions",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "hands_on_usage",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "performance_comparisons",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "negative",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "neutral",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "positive",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "none",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 26,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 25,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "-3.846154",
          "comparison_state": "available",
          "prior_authors": 24,
          "prior_count": 26,
          "selected_authors": 24,
          "selected_count": 25
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "discourse": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "sentiment": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "hunyuan:full_window",
          "direction": "decrease",
          "display_en": "4%",
          "display_zh_cn": "4%",
          "fact_id": "qf_aa44739c4fe2989fd3b15a2e",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "-3.846154",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "post_type",
          "rank": 3,
          "stream_position": 3
        },
        {
          "family": "discourse",
          "rank": 3,
          "stream_position": 3
        },
        {
          "family": "sentiment",
          "rank": 3,
          "stream_position": 3
        },
        {
          "family": "nationalism",
          "rank": 3,
          "stream_position": 3
        }
      ],
      "start_at": "2026-08-14T00:00:31Z"
    },
    {
      "brand_key": "llama",
      "candidate_id": "llama:full_window",
      "coarse_series": {
        "author_counts": [
          12,
          8,
          10,
          11,
          16,
          43,
          29,
          21
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            12,
            8,
            10,
            11,
            17,
            64,
            34,
            25
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                2,
                1,
                1,
                1,
                1,
                25,
                7,
                3
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                10,
                7,
                9,
                10,
                16,
                39,
                27,
                22
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          12,
          8,
          10,
          11,
          17,
          64,
          34,
          25
        ]
      },
      "display_name_en": "Meta Llama",
      "display_name_zh_cn": "Meta Llama",
      "end_at": "2026-08-15T00:00:31Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_97faa911d81c5c0c8f12",
          "discourse_keys": [],
          "evidence_id": "e_59c0f3502a9de653c9429c1b",
          "excerpt": "@25_cycle @draizk @JunkScience it gets better ... I had a choice today ... either install a new 'Claude Code' on a llama-3.1-8b-instruct-abliterated LLM OR van Westen etal (2026) Failure to track a stable AMOC state under rapid climate change OR Sleiman etal (2026) ZEST: Zero-shot embodied skill transfer for athletic robot control OR Tardif etal (20190 Last Millennium Reanalysis with an expanded proxy database and seasonal proxy modeling guess who won ? Supplement of Last Millennium Reanalysis with an expanded proxy database and seasonal proxy modeling as I listen to music from Cathedrals of Thought HT @25_cycle",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3fd97b1f79dee11745ec",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_5f6c7f609cd2d7edabb7"
        },
        {
          "author_group_id": "ag_24350f68a4360fb6c950",
          "discourse_keys": [],
          "evidence_id": "e_2f634f118d1b3d00435653ec",
          "excerpt": "@iamsupersocks Ah et si tu veux un meilleure perf, faut prendre le llama.cpp d'AMD, optimisé pour ROCm. Les nightly build sont ici : https://t.co/rehhNZqwir ... ou alors SGLang (moteur que les les gens qui font Qwen et les boîtes d'IA Chinoises en général apprécient beaucoup).",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_480144ab1bc63e41d6ce",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_af9160de8f2f75676eb2"
        },
        {
          "author_group_id": "ag_bd4db06381ce4130111d",
          "discourse_keys": [],
          "evidence_id": "e_a595d662b122918f3e297846",
          "excerpt": "@QualCompounders Well said. Their play in open source is big too. Their models are excellent for general intelligence as is and Llama 3 70B is one of the best at on prem solutions for smaller compute stacks or cloud based projects. Excited to try out their new Muse Glimmer model too.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_8556b4fc2d8e9191484a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_6c5a301b0541744de512"
        },
        {
          "author_group_id": "ag_f9459c8cad80b3e8b03c",
          "discourse_keys": [],
          "evidence_id": "e_39f93566c1ddeffd34d03688",
          "excerpt": "Llama 3.3 70B can sometimes notice when activation steering pushes it off-task and correct itself even while the steering is still happening. In this paper the researchers continuously pushed the model toward an unrelated concept. in 3.8% of trials, the model noticed something was wrong, said things like “wait, that’s not right”, and tried to return to the original task. they also found 26 SAE latents linked to this correction behavior. when they removed these latents, repeated correction attempts dropped from 7.4% to 5.5%. but here’s the interesting part they notice.. some of this correction may simply come from the model reading its own previous output and realizing it went off track. when researchers gave the off-topic text to an unsteered model, that alone could trigger a correction. still, that didn’t explain everything. the model recovered much better when continuing from its own corrected text than when it was simply given a clean on-topic prefix. so normal context explains part",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_aa7a5eeb800859a7762e",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_43a2f39fd681c8a0f928"
        },
        {
          "author_group_id": "ag_526387eee2f83835b06f",
          "discourse_keys": [],
          "evidence_id": "e_5b748205f38c7502d4296876",
          "excerpt": "NVIDIA published a guide on what your context actually costs in hardware. a 128k context window for one user on Llama 3 70B holds about 40 GB of KV cache. and it scales linearly with every user after. context grows -> KV cache grows -> GPU memory fills -> the model stops loading at all their fix isn't compression. it's giving the GPU access to CPU memory: on a GH200 that's 96 GB of GPU memory plus 480 GB hanging off the CPU, one address space, 900 GB/s, no explicit transfers. which reframes the thing entirely. your conversation history isn't text in a prompt. it's gigabytes occupying silicon, and every re-paste refills them. read the guide for the code, then the article below for what happens when the context stops being re-sent.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_97383573755613b8c5b1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_77180312af2391af3d1e"
        },
        {
          "author_group_id": "ag_3a7b782b0773d148ac1f",
          "discourse_keys": [],
          "evidence_id": "e_edf5377b2e3f90feb427ec6e",
          "excerpt": "#AI bug hunter finds flaws & Faster Llama training on Blackwell - #AI #news (Aug 14, 2026) • Frontier model race accelerates • Open versus closed AI debate • Private inference and watermarking • Agents need oversight and evals • AI math progress gets nuance • Vibe-coding money keeps flowing Also in 🇪🇸 Español https://t.co/1K094BwsuS",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d43499f5e50030f0a4f5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_d676b1bf40d4705ba641"
        },
        {
          "author_group_id": "ag_e0c83f35672bec2b0e88",
          "discourse_keys": [],
          "evidence_id": "e_d7ce7504e0756dde2b67ab4b",
          "excerpt": "@sama Great that Codex already supports local models via Ollama! Plz keep expanding and polishing first-class local/open-source model support in the Codex desktop app so users can fully run agents offline with models like Gemma, Llama, or Qwen without any cloud dependency",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_438c999cc48ce2697cc9",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_f026c03209298e48c710"
        },
        {
          "author_group_id": "ag_4021b5517748f10a0126",
          "discourse_keys": [],
          "evidence_id": "e_e95caafd96ea7537edc8d482",
          "excerpt": "single 3090 users (for 24GB vram), this one is for you Use this updated llama-server command to serve Qwen-3.8-27b ./build/bin/llama-server -m \"/qwen-3.8/Qwen3.8-27B-Q4_K_M.gguf\" -ngl 999 -fa on --jinja -np 1 -t 12 --alias qwen3.8-27b-q4 --spec-default --spec-type draft-mtp --spec-draft-type-k q8_0 --spec-draft-type-v q8_0 --cache-type-k q8_0 --cache-type-v q8_0 --temperature 1.0 --top_p 0.95 --top_k 30 --min_p 0.0 --presence_penalty 0.0 Getting max speed and context with best results now. Also set reasoning to medium.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_dd47a08ac16b2b159f47",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_b0af0f5ddd67c0f54269"
        },
        {
          "author_group_id": "ag_a2168ae1eaeca38df1c1",
          "discourse_keys": [],
          "evidence_id": "e_676e4c7c9b56e48e60afdc77",
          "excerpt": "@BerlinCapitalll Doesn't it seem odd that Bittensor, does not have, nor seem focused on building, its own in-house fully fleshed out Frontier-level LLM? It does not even have something akin to the Chinese models like Deep Seek. It has Llama from 2023. We are sick of fancy white papers, fly-wheels, and hype-trains. F*ck that. We want REAL USERS, REAL REVENUE, REAL UTILITY, OR GO HOME.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a16e0440b742f1e303f7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_dbba37b1e30ba9e9de1a"
        },
        {
          "author_group_id": "ag_20924552ffd21e1108ba",
          "discourse_keys": [],
          "evidence_id": "e_c5854e141ffa632a301dbc1f",
          "excerpt": "Qwen3.8-27B 权重刚落地，llama-benchy 的 Apple Silicon 实测就出来了：比前代稍慢。 《Qwen3.8-27B 在 Apple Silicon 上比前代稍慢》 llama-benchy：llama-bench 式基准，跑在任何 OpenAI 兼容端点上 llama-benchy 输出和 llama-bench 同款统计：不同上下文深度下的 prompt processing（pp）和 token generation（tg）速度，加三个延迟指标。差别在于它面向任何 OpenAI 兼容端点，llama.cpp、vLLM、SGLang、LM Studio 本地服务器都行。作者 eugr 是 vLLM 项目的活跃贡献者，2026 年 1 月翻遍现有工具没找到能用的，就自己写了。 解决什么问题 llama-bench 只属于 llama.cpp，而且直连 C++ 引擎测量，不代表最终用户体验。vLLM 自带的 bench 工具则是三个坑： • 不同上下文长度下的 prefill 速度基本算不出来。vllm bench sweep serve 只对关了 prefix caching 的 vLLM 有效；同一个 prompt 反复跑会命中 llama-server 缓存，得到很低的 TTFT 中位数和虚高的 prefill 速度 • 它的 TTFT 测到的是收到第一个数据块的时间，不是第一个可用 token • 随机 prompt 测不出投机解码/MTP 的真实效果 能测什么 • pp 和 tg 速度，可指定上下文深度；context prefill 和缓存上下文上的后续 prompt 分开测（--enable-prefix-caching） • TTFR（首个数据块）、est_ppt（扣除网络延迟后的 prompt 处理时间）、端到端 TTFT（首个生成 token） • --runs 多轮取 mean±std，用 HuggingFace tokenizer 精确计数，正确处理 MTP 多 token 块 • 默认拿《福尔摩斯探案集》文本做 prompt 语料，投机解码的测量更接近真实 • --concurrency 测并发吞吐，--post-run-cmd 每轮后执行命令（比如清缓存） Qwen3.8-27B 实测 8 月 14 日 Qw",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_00bc424abbb059d64378",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_99220068c1d3caf62a11"
        },
        {
          "author_group_id": "ag_fd2f14ccc10b91c318a4",
          "discourse_keys": [],
          "evidence_id": "e_efa6d09ca05ffe2493f411ac",
          "excerpt": "it's not really claude code if you're routing to deepseek. it's claude code's UI with a different model behind it. still useful though",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_d1df19874182902da157",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_d4c707d4cb359f65c5b8"
        },
        {
          "author_group_id": "ag_852361ae4411a7531329",
          "discourse_keys": [],
          "evidence_id": "e_368ab9fc5d294319325a8c89",
          "excerpt": "@ResonantTrace ps i also have a llama 2 based version and also a mini version for ollama on huggingface as well main python skeleton : https://t.co/0gfOEKZHF6 mini ollama model : https://t.co/0gfOEKZHF6",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_beea5b785220b071e152",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_0e7f6476743133a0eef5"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 64,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 64,
        "selected_count": 12,
        "story_rank": 5,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "advertising_marketing",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 134,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 181,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "buzz_releases",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 134,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 181,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 134,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 181,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "feedback_questions",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 134,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 181,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "hands_on_usage",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 134,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 181,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "performance_comparisons",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 134,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 181,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "35.074627",
          "comparison_state": "available",
          "prior_authors": 120,
          "prior_count": 134,
          "selected_authors": 139,
          "selected_count": 181
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {}
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "llama:full_window",
          "direction": "increase",
          "display_en": "35%",
          "display_zh_cn": "35%",
          "fact_id": "qf_e9aeba400df912515d5a81b9",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "35.074627",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "post_type",
          "rank": 4,
          "stream_position": 4
        }
      ],
      "start_at": "2026-08-14T00:00:31Z"
    }
  ],
  "comparison_allowed": true,
  "comparison_suppressed_reasons": [],
  "coverage": {
    "prior": {
      "earliest_at": "2025-01-15T09:47:50Z",
      "known_backlog_overlap": false,
      "ratio": "1.000000",
      "state": "sufficient"
    },
    "selected": {
      "earliest_at": "2025-01-15T09:47:50Z",
      "known_backlog_overlap": false,
      "ratio": "1.000000",
      "state": "sufficient"
    }
  },
  "evidence_policy": {
    "comparison_ceiling": 12,
    "excerpt_characters": 1000,
    "floor": 4,
    "lead_ceiling": 48,
    "provider_packet_bytes": 131072,
    "reservoir_rank_limit": 32,
    "version": "adaptive-v1"
  },
  "quantitative_fact_schema_version": 1,
  "series_axis": {
    "coarse": {
      "bucket_count": 8,
      "duration_seconds": 10800,
      "ends": [
        "2026-08-14T03:00:31Z",
        "2026-08-14T06:00:31Z",
        "2026-08-14T09:00:31Z",
        "2026-08-14T12:00:31Z",
        "2026-08-14T15:00:31Z",
        "2026-08-14T18:00:31Z",
        "2026-08-14T21:00:31Z",
        "2026-08-15T00:00:31Z"
      ],
      "starts": [
        "2026-08-14T00:00:31Z",
        "2026-08-14T03:00:31Z",
        "2026-08-14T06:00:31Z",
        "2026-08-14T09:00:31Z",
        "2026-08-14T12:00:31Z",
        "2026-08-14T15:00:31Z",
        "2026-08-14T18:00:31Z",
        "2026-08-14T21:00:31Z"
      ]
    }
  },
  "snapshot_schema_version": 1,
  "thresholds": {
    "episode_peak_ratio": "3.0",
    "max_episodes_per_candidate": 3,
    "min_authors": 10,
    "min_posts": 20,
    "minimum_coverage": "0.75"
  },
  "unresolved_backlog_intervals": [],
  "window_days": 1
}
~~~


## Exact provider packet — 2026-08-13 window

The following is the canonical JSON packet supplied to the provider for the 2026-08-13 window. The single long line is intentional: it preserves the exact serialized packet bytes.

~~~json
{
  "as_of": "2026-08-14T00:00:00Z",
  "candidates": [
    {
      "brand_key": "deepseek",
      "candidate_id": "deepseek:52-58",
      "coarse_series": {
        "author_counts": [
          470,
          444,
          325,
          633,
          1378,
          984,
          558,
          360
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            571,
            510,
            369,
            771,
            1895,
            1276,
            678,
            418
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                101,
                86,
                57,
                162,
                561,
                289,
                136,
                74
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                470,
                424,
                312,
                609,
                1334,
                987,
                542,
                344
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          571,
          510,
          369,
          771,
          1895,
          1276,
          678,
          418
        ]
      },
      "display_name_en": "DeepSeek",
      "display_name_zh_cn": "DeepSeek",
      "end_at": "2026-08-13T14:45:00Z",
      "episodes": [
        {
          "baseline_post_count": "51.500000",
          "end_at": "2026-08-13T14:45:00Z",
          "end_bucket_index": 58,
          "episode_id": "deepseek:52-58",
          "peak_author_count": 205,
          "peak_post_count": 241,
          "peak_to_baseline": "4.679612",
          "post_count": 1265,
          "start_at": "2026-08-13T13:00:00Z",
          "start_bucket_index": 52
        }
      ],
      "evidence": [
        {
          "author_group_id": "ag_e34c73a86546b5d8dda8",
          "discourse_keys": [],
          "evidence_id": "e_86cdbf33abc66eac85d9b68c",
          "excerpt": "DeepSeek just dropped V4-Pro. Frontier performance, flexible reasoning effort, native OpenAI API support. The part that matters for builders isn't the benchmark. It's that a model this capable just got dramatically cheaper overnight.",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_b3756754725730820dde",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8c6c35a1ac49e3adb4f6"
        },
        {
          "author_group_id": "ag_762c0b33242eaf918f5a",
          "discourse_keys": [],
          "evidence_id": "e_60f42a8910084a94fa60a208",
          "excerpt": "DeepSeek V4 Pro 0813が今日から正式提供っぽい。今気づいた。凄そう。早速使ってみる。",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_77b6fce4e33068af5997",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_70284112b079de05f8da"
        },
        {
          "author_group_id": "ag_778a0992723cfb9458ff",
          "discourse_keys": [],
          "evidence_id": "e_99fe43ae3fd9c27e029633a0",
          "excerpt": "@deepseek https://t.co/FmtXKxOEYY",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_8ed39a5b9974a12f3fae",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a207267b21778ca2eb41"
        },
        {
          "author_group_id": "ag_083a7ebd25d4652eac82",
          "discourse_keys": [],
          "evidence_id": "e_f6d47bcfdb8f4280a75e8378",
          "excerpt": "@NFT_Chen @deepseek https://t.co/60EMz6msHD",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_2b1778da11d099ac31e1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_a207267b21778ca2eb41"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "floor",
        "available_independent_source_count": 64,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 64,
        "selected_count": 4,
        "story_rank": 4,
        "target_count": 4
      },
      "evidence_support": {
        "distinct_author_group_count": 4,
        "distinct_source_cluster_count": 4,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "volume": {
          "change_pct": "68.870380",
          "comparison_state": "available",
          "prior_authors": 2754,
          "prior_count": 3842,
          "selected_authors": 4198,
          "selected_count": 6488
        }
      },
      "kind": "episode",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "deepseek:52-58",
          "direction": "increase",
          "display_en": "69%",
          "display_zh_cn": "69%",
          "fact_id": "qf_59b0606149da6a087806b0a6",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "68.870380",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "episode_rank": 1,
          "family": "volume",
          "rank": 1,
          "stream_position": 1
        }
      ],
      "start_at": "2026-08-13T13:00:00Z"
    },
    {
      "brand_key": "minimax",
      "candidate_id": "minimax:full_window",
      "coarse_series": {
        "author_counts": [
          100,
          84,
          85,
          147,
          178,
          204,
          152,
          145
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            113,
            99,
            92,
            171,
            200,
            269,
            175,
            174
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                14,
                14,
                9,
                28,
                25,
                83,
                42,
                41
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                99,
                85,
                83,
                143,
                175,
                186,
                133,
                133
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          113,
          99,
          92,
          171,
          200,
          269,
          175,
          174
        ]
      },
      "display_name_en": "MiniMax AI",
      "display_name_zh_cn": "MiniMax AI",
      "end_at": "2026-08-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_ee6bd77a97837267662b",
          "discourse_keys": [],
          "evidence_id": "e_bbff7acdbd53f5344910554a",
          "excerpt": "Tomorrow at 5:30pm PT: MiniMax H3 × @magnific at the Magnific SF office. We’ll be showcasing what people are already making with H3, talking about where AI video is heading, and getting hands-on with H3 inside Magnific. Expect a live workflow across cinematic generation, native audio, dialogue, editing + more. Then we’ll open things up for networking and more showcases from the community. Only a couple spots left. Link below. #MiniMaxH3 #AIVideo",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_2cafc5b4f2edb448492e",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": true,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a36cf3f1698b9295596a"
        },
        {
          "author_group_id": "ag_260c55040b8bad314e85",
          "discourse_keys": [],
          "evidence_id": "e_79fc856bf8fbcf5274ae4b7f",
          "excerpt": "Minimax h3で実験。 尾阿波踊りを踊るという指定からトマトという制約を外してみたが、分かんないな。短足のせいか？。 https://t.co/sU7UZybXGw",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_c46fff7718759397dc7c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_23b1d9c74f1960f6c757"
        },
        {
          "author_group_id": "ag_8cbf7f67bfc96185e555",
          "discourse_keys": [],
          "evidence_id": "e_458a77fbfc4bb9c1ad89e601",
          "excerpt": "A short H3 example can clarify what to test next. This video gives you a concrete result to inspect. Atlas Cloud provides a direct MiniMax H3 route for production testing. https://t.co/TTg8IXi89C https://t.co/5UllPhsdVx",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_46a3df6b73b44c9db2ba",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_43e86fdce45913ca6229"
        },
        {
          "author_group_id": "ag_9b3ba5202e9b7654e7a5",
          "discourse_keys": [],
          "evidence_id": "e_9e118b900d9e3d9a8ab16dbf",
          "excerpt": "A short H3 example can clarify what to test next. This video gives you a concrete result to inspect. Atlas Cloud provides a direct MiniMax H3 route for production testing. https://t.co/cv8jsYkDWO https://t.co/iZ1t0YxK8S",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_33908ce3c30a9adc5dba",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_43e86fdce45913ca6229"
        },
        {
          "author_group_id": "ag_bba2df4276ae3f62d628",
          "discourse_keys": [],
          "evidence_id": "e_fde06405076300fad4395594",
          "excerpt": "Same prompt. Different models. Different results. We put the exact same prompt through Seedance 2.0, Seedance 2.5, and MiniMax H3. Which one is your pick? 👀 https://t.co/GKJASTEmex",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_4682394528b504d5b08d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c8ea6c3554569ec62044"
        },
        {
          "author_group_id": "ag_742448fc385c45b251b6",
          "discourse_keys": [],
          "evidence_id": "e_ccbd31ad6ed7b3cd6718acaf",
          "excerpt": "Who said you also wanted a SOTA open-weights music model 👀",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_82e2159072f42cc02baa",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": true,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_9beb48ad2bc8f8d3b3d2"
        },
        {
          "author_group_id": "ag_3629a61e2b178f9adb94",
          "discourse_keys": [],
          "evidence_id": "e_dca90142dfc3f4ce6f9a58ea",
          "excerpt": "Links: EZlaunch for Minimax H3 (Configured for 3090 or 4090), added heretic as option (proceed with caution...it will literally render anything: https://t.co/fngkutVLE8 Dual DGX Sparks SuperDeepSeek v4 Flash Abliterated: https://t.co/t8dtQp10TF",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a17d040f26bb64e93226",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_787cf83e873d0131c102"
        },
        {
          "author_group_id": "ag_b89db5eec5ca9fcff0b2",
          "discourse_keys": [],
          "evidence_id": "e_c831604b8835f4e0a3ba6dbd",
          "excerpt": "ATELIER LABの実験映像。 制作中のゲーム『潮の約束 ZERO』を、MiniMax H3で映像化してみました。 映像も音もH3。短い生成動画をつないで約30秒のPVにしています。 無印M4 Mac mini（24GB）のローカル環境で、ここまで作れるんですね。 #MiniMaxH3 #生成AI #ゲーム制作 https://t.co/07Nza1X8Ro",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_f6830c261107893d25c1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_da281459a41e7e5d736d"
        },
        {
          "author_group_id": "ag_3d8c3a0680aef31da6c0",
          "discourse_keys": [],
          "evidence_id": "e_8e783a054594c8e04161414f",
          "excerpt": "ليمتس ال AI كلها خلصت ف كنت بشوف بلان صغيرة كدا امشي حالي بيها ل بكرا ف لقيت OpenCode عاملين بلان كدا ب10$ دولار واول شهر ب 5$ فيها كل الموديلز الصينةQwen, Kimi, GLM, Minimax, DeepSeek, و كمان Grok 4.5, GPT 5.6. اشترك من هنا وخد 5$ كريدتس وانا زيهم🙈 https://t.co/sXz0UxlEM8",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d0b837976af8325fe922",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_900c497e99e1b69ceae0"
        },
        {
          "author_group_id": "ag_4cdc9e3390f17fe446f3",
          "discourse_keys": [],
          "evidence_id": "e_6c7db4b02b2a5ef686f41297",
          "excerpt": "@notjazii I’ve switched my model to minimax ..",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ed9994dd5936e8db276d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_52362b18dc2baa15037b"
        },
        {
          "author_group_id": "ag_e3202369c1381e4220d4",
          "discourse_keys": [],
          "evidence_id": "e_bcd249aa7d3ed96aa5ee90ae",
          "excerpt": "Wizstar 发布 Seedance 2.5 和 MiniMax H3，AI 视频生成能力再升级。对广告投放来说，这意味着素材生产的效率门槛又降了一层。 • 视频广告的 A/B 测试可以更大胆——用 AI 快速生成多版本，跑量后再集中预算给胜出素材。 • 注意官方称新模型支持更长的上下文和更细腻的动作，适合做产品演示或剧情向短视频。 • 建议今天就去试一下：拿一条现有跑量素材，让 AI 重做 3 个变体，对比点击率变化，别等到同行先跑通。",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_906234902c76259b7514",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a6b150409d67a99b8055"
        },
        {
          "author_group_id": "ag_0fb6bd84ce2fcab131cd",
          "discourse_keys": [],
          "evidence_id": "e_d29df7c5606f505307f1133b",
          "excerpt": "■MiniMax Audio https://t.co/Wa8S3IeHgM",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_60a030e99afa28063f97",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_465a3cece52eaf18cc9c"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 80,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 83,
        "selected_count": 12,
        "story_rank": 3,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 2
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "-0.044098",
              "market_relative_change_pp": "0.044098",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.571429",
              "key": "mild_pro",
              "market_change_pp": "-0.602675",
              "market_relative_change_pp": "0.031247",
              "prior_basis_count": 1050,
              "prior_count": 6,
              "prior_prevalence": "0.005714",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-37.428571",
              "key": "none",
              "market_change_pp": "-21.343525",
              "market_relative_change_pp": "-16.085047",
              "prior_basis_count": 1050,
              "prior_count": 393,
              "prior_prevalence": "0.374286",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.095238",
              "key": "pro",
              "market_change_pp": "-0.543878",
              "market_relative_change_pp": "0.448640",
              "prior_basis_count": 1050,
              "prior_count": 1,
              "prior_prevalence": "0.000952",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.380952",
          "prior_covered_count": 400,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "-1.428571",
              "key": "absurdist_meme",
              "market_change_pp": "-0.764369",
              "market_relative_change_pp": "-0.664203",
              "prior_basis_count": 1050,
              "prior_count": 15,
              "prior_prevalence": "0.014286",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-8.666667",
              "key": "advertising-marketing",
              "market_change_pp": "-4.145230",
              "market_relative_change_pp": "-4.521437",
              "prior_basis_count": 1050,
              "prior_count": 91,
              "prior_prevalence": "0.086667",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.095238",
              "key": "ai_slop_critique",
              "market_change_pp": "-0.014699",
              "market_relative_change_pp": "-0.080539",
              "prior_basis_count": 1050,
              "prior_count": 1,
              "prior_prevalence": "0.000952",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.285714",
              "key": "cope",
              "market_change_pp": "-0.352786",
              "market_relative_change_pp": "0.067071",
              "prior_basis_count": 1050,
              "prior_count": 3,
              "prior_prevalence": "0.002857",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "-0.102896",
              "market_relative_change_pp": "0.102896",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.666667",
              "key": "dunk_yingyang",
              "market_change_pp": "-0.485080",
              "market_relative_change_pp": "-0.181587",
              "prior_basis_count": 1050,
              "prior_count": 7,
              "prior_prevalence": "0.006667",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.952381",
              "key": "fud",
              "market_change_pp": "-1.249449",
              "market_relative_change_pp": "0.297068",
              "prior_basis_count": 1050,
              "prior_count": 10,
              "prior_prevalence": "0.009524",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-24.190476",
              "key": "genuine_hype",
              "market_change_pp": "-14.523005",
              "market_relative_change_pp": "-9.667472",
              "prior_basis_count": 1050,
              "prior_count": 254,
              "prior_prevalence": "0.241905",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.095238",
              "key": "sarcasm",
              "market_change_pp": "-0.352786",
              "market_relative_change_pp": "0.257547",
              "prior_basis_count": 1050,
              "prior_count": 1,
              "prior_prevalence": "0.000952",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-1.809524",
              "key": "self_deprecation",
              "market_change_pp": "-0.617375",
              "market_relative_change_pp": "-1.192149",
              "prior_basis_count": 1050,
              "prior_count": 19,
              "prior_prevalence": "0.018095",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.380952",
          "prior_covered_count": 400,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "-6.761905",
              "key": "advertising_marketing",
              "market_change_pp": "-3.439659",
              "market_relative_change_pp": "-3.322246",
              "prior_basis_count": 1050,
              "prior_count": 71,
              "prior_prevalence": "0.067619",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-3.333333",
              "key": "buzz_releases",
              "market_change_pp": "-2.807585",
              "market_relative_change_pp": "-0.525748",
              "prior_basis_count": 1050,
              "prior_count": 35,
              "prior_prevalence": "0.033333",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-1.904762",
              "key": "event_announcement",
              "market_change_pp": "-1.616934",
              "market_relative_change_pp": "-0.287828",
              "prior_basis_count": 1050,
              "prior_count": 20,
              "prior_prevalence": "0.019048",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-7.619048",
              "key": "feedback_questions",
              "market_change_pp": "-6.820520",
              "market_relative_change_pp": "-0.798527",
              "prior_basis_count": 1050,
              "prior_count": 80,
              "prior_prevalence": "0.076190",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-31.714286",
              "key": "hands_on_usage",
              "market_change_pp": "-14.567103",
              "market_relative_change_pp": "-17.147183",
              "prior_basis_count": 1050,
              "prior_count": 333,
              "prior_prevalence": "0.317143",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-9.428571",
              "key": "performance_comparisons",
              "market_change_pp": "-10.789358",
              "market_relative_change_pp": "1.360786",
              "prior_basis_count": 1050,
              "prior_count": 99,
              "prior_prevalence": "0.094286",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.600952",
          "prior_covered_count": 631,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "-0.190476",
              "key": "anti",
              "market_change_pp": "-0.426283",
              "market_relative_change_pp": "0.235806",
              "prior_basis_count": 1050,
              "prior_count": 2,
              "prior_prevalence": "0.001905",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "-0.058798",
              "market_relative_change_pp": "0.058798",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "-0.058798",
              "market_relative_change_pp": "0.058798",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1050,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-37.809524",
              "key": "none",
              "market_change_pp": "-21.960900",
              "market_relative_change_pp": "-15.848624",
              "prior_basis_count": 1050,
              "prior_count": 397,
              "prior_prevalence": "0.378095",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-0.095238",
              "key": "pro",
              "market_change_pp": "-0.044098",
              "market_relative_change_pp": "-0.051140",
              "prior_basis_count": 1050,
              "prior_count": 1,
              "prior_prevalence": "0.000952",
              "selected_basis_count": 1293,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.380952",
          "prior_covered_count": 400,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "23.142857",
          "comparison_state": "available",
          "prior_authors": 780,
          "prior_count": 1050,
          "selected_authors": 926,
          "selected_count": 1293
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "mild_pro": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "none": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "pro": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "discourse": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "absurdist_meme": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "advertising-marketing": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "ai_slop_critique": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "cope": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "dunk_yingyang": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "fud": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "genuine_hype": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "sarcasm": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "self_deprecation": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising_marketing": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "buzz_releases": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "event_announcement": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "feedback_questions": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "hands_on_usage": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "performance_comparisons": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "anti": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "none": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "pro": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "minimax:full_window",
          "direction": "increase",
          "display_en": "23%",
          "display_zh_cn": "23%",
          "fact_id": "qf_3a07aa2486e9105d311aba1e",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "23.142857",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "post_type",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "discourse",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "nationalism",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "volume",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-08-13T00:00:00Z"
    },
    {
      "brand_key": "mistral",
      "candidate_id": "mistral:full_window",
      "coarse_series": {
        "author_counts": [
          5,
          7,
          9,
          12,
          20,
          13,
          12,
          12
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            6,
            8,
            10,
            13,
            20,
            13,
            12,
            12
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                1,
                2,
                4,
                5,
                2,
                1,
                5
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                6,
                7,
                8,
                9,
                15,
                11,
                11,
                7
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          6,
          8,
          10,
          13,
          20,
          13,
          12,
          12
        ]
      },
      "display_name_en": "Mistral",
      "display_name_zh_cn": "Mistral",
      "end_at": "2026-08-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_2231e8e3ce08fb4d5eb1",
          "discourse_keys": [],
          "evidence_id": "e_9a3a059a2306b151ea84de8a",
          "excerpt": "Cierre IA: agente en tu GPU, bots con PC propio y Gemini a mil millones 𝗠𝘂𝘀𝗲 𝗚𝗹𝗶𝗺𝗺𝗲𝗿: 𝟥𝟢𝗕 𝗼𝗽𝗲𝗻 𝗽𝗮𝗿𝗮 𝗮𝗴𝗲𝗻𝘁𝗲𝘀 𝗹𝗼𝗰𝗮𝗹𝗲𝘀 Meta Superintelligence Labs suelta Muse Glimmer (30B, Apache 2.0): pensado para agentes always-on en Mac/PC con una sola GPU de consumo. Destilación desde un teacher más grande + cuantización ~4-bit (<20 GB) y drafter DFlash. En las evals de Meta (vs Gemma4-31B y Qwen3.6-27B): MCP-Atlas 75,5 / DeepSearch QA 74,6 / SWE-Bench Verified 76,0; Qwen sigue delante en OSWorld y Terminal-Bench. Pesos en Hugging Face; llama.cpp/MLX/ExecuTorch en camino. Fuente(s): https://t.co/IXcUtI3Xrx https://t.co/b2gyBxRA3D 𝗚𝗿𝗼𝗸 𝗕𝗼𝘁: 𝗰𝗼𝗺𝗽𝗮ñ𝗲𝗿𝗼𝘀 𝗰𝗼𝗻 𝘀𝘂 𝗽𝗿𝗼𝗽𝗶𝗮 𝗺á𝗾𝘂𝗶𝗻𝗮 SpaceXAI abre beta de Grok Bot: agentes 24/7 con computador propio en la nube, login a apps reales (incluso sin API limpia), mensajería tipo colega y varios bots en paralelo. Disponible para SuperGrok Heavy, Cursor Ultra y Cursor Teams Premium (desktop/iOS); enterprise en waitlist. Fuente(s): https://t.co/yCyV4aHpRQ 𝗚𝗲𝗺𝗶𝗻𝗶 𝗔𝗽𝗽: 𝟣.𝟢𝟢",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_50548b8a9845cc4241e1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_893695764988d2e6bbfb"
        },
        {
          "author_group_id": "ag_216516657bdbf33ec1eb",
          "discourse_keys": [],
          "evidence_id": "e_334705d852c2905af74d7a3a",
          "excerpt": "@PastaMaxxer @arthurmensch GLM 5.2 is a good start but, even on 'just' serving the latest Chinese models (Qwen, K3 and DS being the priority ones), Mistral needs to be far more ambitious. There's a huge opportunity regarding full throttle, EU-based endpoints. Inference onboarding should be far nimbler too!",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_54957d0bcb3b13fcc819",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_6260abb02ff3c441f480"
        },
        {
          "author_group_id": "ag_9e4e166c105d7f9cb761",
          "discourse_keys": [],
          "evidence_id": "e_17df24134a931b101a88a0da",
          "excerpt": "@PernotLeplay @MistralAI Mistral runs on US Chips with US Software",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d98a5aaf39ba9a3ae8e4",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8ab75766a5dde789550b"
        },
        {
          "author_group_id": "ag_0b46357c2af5382ded04",
          "discourse_keys": [],
          "evidence_id": "e_3571870b5bd5a5b3e79d4e94",
          "excerpt": "@PernotLeplay @MistralAI Mistral is trash",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_10a22c37c1832af282d8",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8ab75766a5dde789550b"
        },
        {
          "author_group_id": "ag_1013cfbc408968e358d0",
          "discourse_keys": [],
          "evidence_id": "e_b994bb446056bf5a5a256a03",
          "excerpt": "6 FREE AI APIs worth bookmarking in 2026: 1. Groq — Llama 3.3 70B https://t.co/G9f2ph9aIB 2. Google AI Studio — Gemini https://t.co/AxErAH5jOO 3. Mistral AI — Mistral models https://t.co/fErzpNaWah 4. Pollinations AI — Text, image, audio & video https://t.co/TGmVJ9tpqP 5. OpenRouter — Free AI models through one API https://t.co/T7PTLGEXo1 6. Hugging Face — Open models & inference https://t.co/77x3zK9dxZ Bookmark this. You’ll thank yourself when you build your next AI project.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_5703dad6ac7c370b90b5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_bf44fbca98f8b13a4a22"
        },
        {
          "author_group_id": "ag_43db790a7eb557783df0",
          "discourse_keys": [],
          "evidence_id": "e_8dc460fffb92b1851e657cdc",
          "excerpt": "6 FREE AI APIs worth bookmarking in 2026: 1. Groq — Llama 3.3 70B https://t.co/0fKqMUS5m4 2. Google AI Studio — Gemini https://t.co/QlF6xgutW0 3. Mistral AI — Mistral models https://t.co/lWzJxpZSei 4. Pollinations AI — Text, image, audio & video https://t.co/uLwTbaBcB9 5. OpenRouter — Free AI models through one API https://t.co/hp5LjpwWbK 6. Hugging Face — Open models & inference https://t.co/uz7Aiu8etr Bookmark this. You’ll thank yourself when you build your next AI project.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_39dbdd9cdf8bc6fc35d7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_bf44fbca98f8b13a4a22"
        },
        {
          "author_group_id": "ag_3bd0d4b99c14cfc89cd4",
          "discourse_keys": [],
          "evidence_id": "e_8573326c8a6f418a720256eb",
          "excerpt": "@sahill_og Qwen Kimi Mistral Deepseek you mean mostly only US models that start with C ...",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_40c2ba04a34da86aa775",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_df325f38330b2e39c757"
        },
        {
          "author_group_id": "ag_59de96ef916b57a0736f",
          "discourse_keys": [],
          "evidence_id": "e_9729521165fbb6f2d929b1b5",
          "excerpt": "How to Create Your Own AI When people say \"create your own artificial intelligence (AI) model\", they rarely mean training one from scratch. That takes millions of dollars and industrial hardware. It almost always means running an existing open-source model on your own computer and shaping it until it feels like yours. You need very little theory. Model size (7B, 13B, 70B): B means billions of parameters, roughly brain size. Bigger is smarter but slower. For most laptops, 3B to 14B is the sweet spot. Quantization (Q4, Q8): compression that lets big models run on normal hardware. Q4 is the standard; it shrinks a 7B model from about 14 gigabytes (GB) to 5GB with minor quality loss. Your computer's memory (RAM) decides everything: 8GB → 3B models (Llama 3.2 3B) 16GB → 7B–13B (Mistral 7B, Qwen 8B) 32GB → up to ~30B (Qwen 14B) 64GB+ → 70B models Two free tools, both on Mac, Windows and Linux: LM Studio, if you never want to see a terminal. Browse models, click download, chat. Nothing you typ",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_b88640e170c644010dd5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c47960dd443fb246bda3"
        },
        {
          "author_group_id": "ag_a983528951dc86006228",
          "discourse_keys": [],
          "evidence_id": "e_5f9f8a970d92ab992b59e5c3",
          "excerpt": "Mistral has the best OCR model. We are currently using mistral model for an internal tool we are building for an interior design studio",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_5dfb8d4f9ac2d93c7cc0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_6e2829f1413d4a0e2392"
        },
        {
          "author_group_id": "ag_35a0e16db61806737784",
          "discourse_keys": [],
          "evidence_id": "e_48d7af5cb40608e5ddf6161a",
          "excerpt": "Je l'ai déjà dit dans un autre tweet : arrêtez de vendre des « agents IA » qui tournent sur n8n ou Hermes chez votre client. Dans l'autre tweet je parlais d'un point vu valorisation de votre entreprise ( prendre le statut d'éditeur de logiciel plutot que rester un Freelance), mais là je parle d'un point de vu crédibilité et négociation chez un gros client . Votre solution doit tourner sur un serveur dédié. Le client y accède par une application web ou par API branchée sur son workflow. Et vous vendez ça comme un éditeur : licence + frais d'installation + maintenance annuelle. Et changez de vocabulaire : tu ne vends pas des agents IA, tu vends du logiciel, des applications. Ton métier et ton statut, c'est éditeur de logiciel. Commercialement, oui, ce sont des applications qui automatisent des tâches avec de l'IA. Mais un grand compte n'achète pas un « agent IA », il achète un logiciel, avec une licence, un contrat, un éditeur en face. Positionne-toi comme ça. Il y a 8 mois j'étais un vi",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_5f6babe7f6ba1dd3a25b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8d5a3e0f499d7784dfa1"
        },
        {
          "author_group_id": "ag_ea1e231de93e0d25cc0e",
          "discourse_keys": [],
          "evidence_id": "e_f1e68d15a78f3324e7a605a6",
          "excerpt": "@sahill_og Mistral, Gemini, Deepseek, llama to name a few more starting with “c”",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7504a8766516d9b255b3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_9a9c172f8ef873278351"
        },
        {
          "author_group_id": "ag_9b36c91e1b4089433eee",
          "discourse_keys": [],
          "evidence_id": "e_2bb5f51456b6f6e0c9e6c104",
          "excerpt": "10 FREE GITHUB REPOS THAT REPLACE $30,000 A YEAR IN PAID TOOLS 1,8M stars between them and every one costs you nothing 1. awesome, 495k stars the master list of every other list, whatever you need is already in here https://t.co/df7JJQddRo 2. public-apis, 456k stars 1,400 free APIs across 50 categories, weather, finance, images, games, all documented https://t.co/PqEFBgfUgw 3. scrapling, 73.6k stars undetectable web scraping with Cloudflare bypass baked in, kills the $300 a month scraping API https://t.co/xSIV0WMbFZ 4. free-for-dev, 132k stars hundreds of services with permanent free tiers, no trial, no card https://t.co/E9Io07xIw1 5. ollama, 178k stars run Llama, Mistral or DeepSeek locally with one command, zero API bill https://t.co/lAWfIjmAPX 6. langflow, 153k stars drag and drop builder for AI agents and RAG pipelines, ship it as an API or MCP server https://t.co/5dsxiGvT2a 7. awesome-mcp-servers, 92k stars thousands of MCP servers wiring your agent to browsers, databases and ever",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a7c0e1ac6ae453e3fcf5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_e4d8189566158dca50bf"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 60,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 64,
        "selected_count": 12,
        "story_rank": 2,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "-1.941748",
              "key": "absurdist_meme",
              "market_change_pp": "-0.764369",
              "market_relative_change_pp": "-1.177379",
              "prior_basis_count": 103,
              "prior_count": 2,
              "prior_prevalence": "0.019417",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-3.883495",
              "key": "advertising-marketing",
              "market_change_pp": "-4.145230",
              "market_relative_change_pp": "0.261735",
              "prior_basis_count": 103,
              "prior_count": 4,
              "prior_prevalence": "0.038835",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "ai_slop_critique",
              "market_change_pp": "-0.014699",
              "market_relative_change_pp": "0.014699",
              "prior_basis_count": 103,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "cope",
              "market_change_pp": "-0.352786",
              "market_relative_change_pp": "0.352786",
              "prior_basis_count": 103,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "-0.102896",
              "market_relative_change_pp": "0.102896",
              "prior_basis_count": 103,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-1.941748",
              "key": "dunk_yingyang",
              "market_change_pp": "-0.485080",
              "market_relative_change_pp": "-1.456667",
              "prior_basis_count": 103,
              "prior_count": 2,
              "prior_prevalence": "0.019417",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-3.883495",
              "key": "fud",
              "market_change_pp": "-1.249449",
              "market_relative_change_pp": "-2.634046",
              "prior_basis_count": 103,
              "prior_count": 4,
              "prior_prevalence": "0.038835",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-19.417476",
              "key": "genuine_hype",
              "market_change_pp": "-14.523005",
              "market_relative_change_pp": "-4.894471",
              "prior_basis_count": 103,
              "prior_count": 20,
              "prior_prevalence": "0.194175",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "sarcasm",
              "market_change_pp": "-0.352786",
              "market_relative_change_pp": "0.352786",
              "prior_basis_count": 103,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "self_deprecation",
              "market_change_pp": "-0.617375",
              "market_relative_change_pp": "0.617375",
              "prior_basis_count": 103,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.310680",
          "prior_covered_count": 32,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "-1.941748",
              "key": "mixed",
              "market_change_pp": "-1.572836",
              "market_relative_change_pp": "-0.368912",
              "prior_basis_count": 103,
              "prior_count": 2,
              "prior_prevalence": "0.019417",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-4.854369",
              "key": "negative",
              "market_change_pp": "-2.719389",
              "market_relative_change_pp": "-2.134980",
              "prior_basis_count": 103,
              "prior_count": 5,
              "prior_prevalence": "0.048544",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-33.980583",
              "key": "neutral",
              "market_change_pp": "-18.256651",
              "market_relative_change_pp": "-15.723931",
              "prior_basis_count": 103,
              "prior_count": 35,
              "prior_prevalence": "0.339806",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-21.359223",
              "key": "positive",
              "market_change_pp": "-17.168896",
              "market_relative_change_pp": "-4.190327",
              "prior_basis_count": 103,
              "prior_count": 22,
              "prior_prevalence": "0.213592",
              "selected_basis_count": 94,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.621359",
          "prior_covered_count": 64,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "-8.737864",
          "comparison_state": "available",
          "prior_authors": 94,
          "prior_count": 103,
          "selected_authors": 86,
          "selected_count": 94
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "discourse": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "absurdist_meme": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "advertising-marketing": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "dunk_yingyang": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "fud": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "genuine_hype": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "sentiment": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "mixed": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "negative": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "neutral": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "positive": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "mistral:full_window",
          "direction": "decrease",
          "display_en": "9%",
          "display_zh_cn": "9%",
          "fact_id": "qf_45edd8c1065297f12c2bb1bd",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "-8.737864",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "sentiment",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "discourse",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-08-13T00:00:00Z"
    },
    {
      "brand_key": "hunyuan",
      "candidate_id": "hunyuan:full_window",
      "coarse_series": {
        "author_counts": [
          6,
          1,
          3,
          5,
          5,
          3,
          1,
          2
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            6,
            1,
            3,
            5,
            5,
            3,
            1,
            2
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                3,
                0,
                0,
                0,
                1
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                6,
                1,
                3,
                2,
                5,
                3,
                1,
                1
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          6,
          1,
          3,
          5,
          5,
          3,
          1,
          2
        ]
      },
      "display_name_en": "Tencent Hunyuan",
      "display_name_zh_cn": "Tencent Hunyuan",
      "end_at": "2026-08-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_3407e593531f149877c3",
          "discourse_keys": [],
          "evidence_id": "e_32f566984b2cf640c604e401",
          "excerpt": "A free repo with 7.9K stars runs a full AI video studio locally on 6GB of VRAM with WAN 2.2, LTX-2, Hunyuan Video and Flux built in. One-click install script, generate in your browser. No uploads, no subscriptions, no watermarks. https://t.co/kYg256CAhG",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d4dab61b136fd39d5603",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_69f2f6c70ea122f09eee"
        },
        {
          "author_group_id": "ag_f4b54199128a19c1b51b",
          "discourse_keys": [],
          "evidence_id": "e_70452cc5cd38586dbbdd0573",
          "excerpt": "Atlas Episode 1 - F**king Casinos It's been 6 months since I made an AI video - and the workflow is VERY different now. Seedance 2.5 is really powerful for animation, and Minimax H3 is leagues beyond it for words. There is a BIG opportunity for sound design tools. I made a breakthrough here, and I'm opensourcing it with hopes someone will make it better! The old adage, spend 4 hours sharpening your axe is very true for AI video workflows now: - Teach your agent about the style your going for, what types of shots are used, timing, camera lenses, etc. - NAIL your references - NAIL your shotlist - Use model-provided best prompting practices The rest is just a director's eye (video experience). Until you come to sound... I tried all of the SOTA models (MMAudio, Hunyuan etc) and they are terrible. So i trained an agent skill on some of the best sound design/scoring advice on the internet, gave it an @ElevenLabs API and @HyperFrames_ and the results were genuinely impressive. About 80% of th",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7d265239206a910d7e4c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_566f4e7f979f5232d8d1"
        },
        {
          "author_group_id": "ag_1169b015029c58a3a52a",
          "discourse_keys": [],
          "evidence_id": "e_da8ac3172c2f7ac6a92d0573",
          "excerpt": "A best Local Video generation model in consumer GPU’ This Open-source tool runs a full AI video studio locally on 6GB of VRAM with WAN 2.2, LTX-2, Hunyuan Video and Flux built in. One-click install script, generate in your browser. No uploads, no subscriptions, no watermarks. https://t.co/AGyJ585m2t",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_2d57aad5c3f437806c2f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_69f2f6c70ea122f09eee"
        },
        {
          "author_group_id": "ag_2c4602537465d2fa9341",
          "discourse_keys": [],
          "evidence_id": "e_c7269e9387c3a3ae79e78cb9",
          "excerpt": "Tencent WorkBuddy is the easiest-to-use productivity AI agent I've tried. WorkBuddy is already China's #1 productivity AI agent on PC by daily active users (Tencent's Q1 earnings). Now global — free to try, set up in minutes, no cloud config. Also, Hunyuan (HY) 3.0 is an LLM from Tencent, and now it's free for users worldwide through August 31, 2026 (PT). Give it one real task off today's list. That's the moment it clicks. ⬇️ Try it yourself: https://t.co/vqU3oc7nR3 @TencentAI_News",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a21483cd7b60cde23c68",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8fe162254f093a33889c"
        },
        {
          "author_group_id": "ag_85f5e8034d1fcff0ca63",
          "discourse_keys": [],
          "evidence_id": "e_de27f1af6350463bcb8f9572",
          "excerpt": "Tencent WorkBuddy is the easiest-to-use productivity AI agent I've tried. WorkBuddy is already China's #1 productivity AI agent on PC by daily active users (Tencent's Q1 earnings). Now global — free to try, set up in minutes, no cloud config. Also, Hunyuan (HY) 3.0 is an LLM from Tencent, and now it's free for users worldwide through August 31, 2026 (PT). Give it one real task off today's list. That's the moment it clicks.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_39c62995f4c8ff5b6bd6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_8fe162254f093a33889c"
        },
        {
          "author_group_id": "ag_a32623d819c9c509ed41",
          "discourse_keys": [],
          "evidence_id": "e_d17fa2abae9556942f41aea3",
          "excerpt": "@Weixin_WeChat Training on users' mass chat history without announcements, would WeLM perform better than hunyuan from Tencent?",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_50c8dfeb290fe9b6ab6f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_8dd3e0cd42eae7853194"
        },
        {
          "author_group_id": "ag_66e116db2b2cc5f955bd",
          "discourse_keys": [],
          "evidence_id": "e_3b3543b7850623d691284e1a",
          "excerpt": "Tencent reported H1 2026 revenue of $56.1 billion, up 10%, and gross profit of $32.1 billion, up 12%. But free cash flow turned negative at -$1.9 billion, largely because of AI infrastructure spending for Hunyuan, WorkBuddy and cloud customers. Excluding prepayments for computing capacity, FCF would have been $5.3 billion. President Martin Lau said Tencent is trying to build a large, profitable, cash-generating AI-native business: use computing resources first for models and applications, then rent out excess capacity through Tencent Cloud. In a worst-case scenario, he said, Tencent could still recover its infrastructure costs through cloud leasing.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_223639508e9dc35e2ae8",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_cea5a389dea682e0ed50"
        },
        {
          "author_group_id": "ag_9b82ffde5651c09f4a0d",
          "discourse_keys": [],
          "evidence_id": "e_529b2be6a86521a3f658f84d",
          "excerpt": "🚨 ¡LA LOCURA MÁS GRANDE DEL AÑO! 🔥 Cancelé mi suscripción a Higgsfield en el acto. Un repo GRATIS con casi 8K estrellas acaba de soltar un estudio completo de vídeo con IA que corre 100% en tu PC. Funciona con solo 6GB de VRAM… ¡hasta en GPUs viejas! Incluye Wan 2.2, LTX-2, Hunyuan Video y Flux integrados. Cero subidas a la nube, cero suscripciones, cero marcas de agua. Cómo lo montas en 3 pasos: Clonas el repo Ejecutas el instalador de un solo clic Abres el navegador y generas No vas a encontrar nada GRATUITO mejor que esto en todo 2026. ¡Comparte ya antes de que explote!",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_6d5188ec443d64d469c6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_e800a1a6e5e49e4f8862"
        },
        {
          "author_group_id": "ag_25f8bc1eb58e3dc755b9",
          "discourse_keys": [],
          "evidence_id": "e_3cb3a814eca03de21f64f2df",
          "excerpt": "YAY! Fixed the key Metal limitations in the Trellis 2 Mac port (local Image > 3D on apple silicon). Big thanks to GPT-5.6 Sol (@OpenAIDevs) for helping isolate the core issue and write the conclusive fix. Spent a week with Opus 5 trying to get proper quality out of a local pipeline. But I got hung up on quality and ended up deep down the rabbit hole and fixed several CUDA > Metal translation problems that were holding back the existing ports (started from shivampkumar’s repo, which in turn was based on Pedro Augusto's work). It's in a super awesome space now!! To celebrate finally getting back to building Worklings, I’m taking requests; send me an image and I’ll return a GLB. Great way to test the pipeline. Anyone else currently fighting Trellis 2 or other Image > 3D models on Apple Silicon? I'll be happy to share notes. What’s the biggest issue you’re still hitting? I plan to now test the Hunyuan 3D model next... anyone worked with this?",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_800e040ae298f2695572",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_07f0ed81967b6821dc24"
        },
        {
          "author_group_id": "ag_a72d27e5a9e1ac11855b",
          "discourse_keys": [],
          "evidence_id": "e_cbd41e3b106ff4172a394eb6",
          "excerpt": "@RoundtableSpace 6gb running wan2.2, hunyuan AND flux together is wild, my old 3060 finally has a reason to wake up",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_4a21ab37dc1d9513ec98",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a6d30d0b5ed897a3e89b"
        },
        {
          "author_group_id": "ag_ae644e470898008c865c",
          "discourse_keys": [],
          "evidence_id": "e_e3ddc94cadeb8f2be62a4b8b",
          "excerpt": "🚨 Tencent descarta ganancias inmediatas de USD $53.000 millones en IA 🚨 El gigante chino rechazó alquilar su infraestructura de GPU con un margen del 30% para enfocarse en modelos propios como Hunyuan-4. El presidente afirma que esta estrategia brindará mayores retornos a largo plazo. A pesar de obtener ingresos de USD $30.300 millones, la incertidumbre del mercado ha afectado sus acciones. La compañía se posiciona para liderar en el sector de IA en China.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a0cba833bcb3fd0d7420",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_efeca0451e7d0da47525"
        },
        {
          "author_group_id": "ag_9c1649004b0fd886f6aa",
          "discourse_keys": [],
          "evidence_id": "e_646cb538581f067686643b7f",
          "excerpt": "@WescheNex1q @NVIDIAAI @Alibaba_Qwen @QwenDevs I dont know why this is a think.... why would you use this for this purpose and not hunyuan or somrhting, 2d to 3d",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_93846f0db78a28025b84",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7b1b8ebd5563264f2772"
        },
        {
          "author_group_id": "ag_4d762a1bcb828b486c89",
          "discourse_keys": [],
          "evidence_id": "e_7479504d1711cb87731b50ad",
          "excerpt": "There are way too many AI 3D models claiming to be the best. So we’re testing them head-to-head. Tripo P1 vs Meshy V6 vs Hunyuan V3.1 Pro vs Rodin 2.5 Same image. Same prompt. No cherry-picking, only 1 generation. This week’s test: a shiny metal helmet. reflections, materials, geometry, and texture accuracy. Next up: characters, objects, environments, and more. By the end, we want one answer: Which AI 3D model should you actually use for your next game, website, or project?",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_4a13b33ec75bd512e76c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_83ac1017fd5a2344c13b"
        },
        {
          "author_group_id": "ag_22adc83a31b4a97c06cc",
          "discourse_keys": [],
          "evidence_id": "e_78108648cb5a2aa0492fa1f2",
          "excerpt": "Tencent’s Q2 results show Hunyuan AI scaling fast, with Hy3 reaching full release and WorkBuddy topping 20M PC visits in June. For cross-border sellers, Tencent AI could increasingly power customer service, product Q&A, listing creation and ad copy across WeChat and enterprise tools.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_088ab547b9f0b1a05358",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_d7af1fa6b1870c85ae38"
        },
        {
          "author_group_id": "ag_3cbf9c600d4222210277",
          "discourse_keys": [],
          "evidence_id": "e_233d2f7b74084f206b79b968",
          "excerpt": "1/ Image generation is live on the AntSeed network 🖼️ 37 models already being served by independent providers: FLUX 2, Nano Banana, Seedream, Qwen-Image, Grok Imagine, Ideogram, Recraft, Hunyuan, SD3.5 & more. Paid per image in USDC. No API key. No subscription. From $0.005/image.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0b0468b6476b4f4fe063",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_4dfa85c6cd5c6f98676b"
        },
        {
          "author_group_id": "ag_bd3dc7f5098ba3cb7ee0",
          "discourse_keys": [],
          "evidence_id": "e_f45209dac7601771e9fa9b26",
          "excerpt": "Shares of #Tencent fall on #AI cost concerns as the tech giant has to spend heavily to catch up with rivals like $BABA and $BIDU. Tencent posted a 176% y/y jump in capital expenditures in Q2 and swung into a negative cash flow of RMB13.8 billion. Still, revenues rose 11% on strong ad sales and gaming, and the company remains profitable while pushing forward with its Hunyuan models, #WorkBuddy and other AI products. #MarketInsights",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0bc3c3fc700907756cfc",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_61c056c58c5464f7ab6a"
        },
        {
          "author_group_id": "ag_2d7c4602a470b60c983c",
          "discourse_keys": [],
          "evidence_id": "e_40bd368ee3c3777ae4a5c864",
          "excerpt": "@goodhunt Here's a concise summary in English from Hunyuan: The August 13 release of DeepSeek V4 Pro sparked mostly negative reactions, driven by three key issues: 1. Silent rollout and suspected rollback: The model was quietly updated via API documentation changes with no announcement; within hours, banners and changelogs disappeared, backend fingerprints shifted, and user tests showed performance dropping back to Flash/Preview levels — fueling speculation that the wrong model version had been deployed. 2. Benchmark-to-real-world gap: Official scores (TerminalBench 2.1: 87.9) were strong, but third-party evaluations (Artificial Analysis: 53 intelligence index) and hands-on tests — e.g., long-context coding tasks failing early or producing worse results than Flash — created sharp disappointment. 3. Pricing anxiety without performance justification: A \"major price hike soon\" warning combined with underwhelming real-world gains made developers question whether Pro was worth 3× the cost o",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_92570d0f7ae1c23845e6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_5c925cabc6951cc8378a"
        },
        {
          "author_group_id": "ag_f574246e039146cfb507",
          "discourse_keys": [],
          "evidence_id": "e_b3a31d783611ed92ea95f241",
          "excerpt": "텐센트 2분기, AI 투자 확대와 클라우드 성장 가속 텐센트 클라우드 매출 성장률이 1분기 10% 후반에서 2분기 20% 초반으로 가속했고, 2분기 운영 CapEx는 518억 위안으로 전년 동기 대비 190% 늘었다는 내용은 공식 공시 원문 미확인 상태다. 핵심 내용 - WorkBuddy가 상호작용 기준 중국 1위를 기록했고 Hunyuan 3의 일평균 토큰 사용량이 프리뷰 대비 4배 증가했다는 내용은 공식 공시 원문 미확인 상태다.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_93ef9ea1004d3ecf7491",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_cbe6b9dc047a1dce609a"
        },
        {
          "author_group_id": "ag_37cdb80f3c9fd610664f",
          "discourse_keys": [],
          "evidence_id": "e_9272f72509f082bcc6c627de",
          "excerpt": "🎨 AI ART & VISUALS ROUNDUP — August 13, 2026 1️⃣ NANO BANANA PRO: THE NEW ARCHITECT'S HYBRID WORKFLOW A fresh three-tool workflow is circulating among architects and 3D designers: ideate with Midjourney, refine prompts through ChatGPT, then finish renders in Nano Banana Pro. This triangle approach combines the creative speed of AI ideation with the precision of dedicated rendering software, letting architects iterate on concepts faster than ever before. The workflow has been gaining traction on YouTube and design communities as teams look to streamline their visualization pipelines. 🔹 @ArchiGenAi 2️⃣ LTX 2.5 GETS AMD STRIX PATCHES — NEAR INSTANT VIDEO GENERATION An open-source community patch for LTX 2.5 has been released specifically for AMD Strix Halo hardware, dramatically cutting video generation times. On an R9700 AI Pro processor, a five-second clip now generates in just 0.85 seconds after the initial model load. This patch opens up real-time AI video iteration on AMD consumer ha",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_9371e54acf26c9dc2198",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7055a0c141e90bc00b99"
        },
        {
          "author_group_id": "ag_eb1a2027f3bfbb2eff95",
          "discourse_keys": [],
          "evidence_id": "e_bc32130dd7d100f7ab491fb2",
          "excerpt": "Haciendo también pruebas en #Blender con generación de malla usando #HunYuan y generación de texturas con #ComfyUI https://t.co/AeaZYgeJmD",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_35b1eb705f41548718a0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_0f023f8104b199cbe3dc"
        },
        {
          "author_group_id": "ag_3634141f7cdccde2e951",
          "discourse_keys": [],
          "evidence_id": "e_e96154d8d76007896aba14f5",
          "excerpt": "Tencent $53bn hardware splurge for AI models not rentals Tencent AI Ecosystem visualized for reference here https://t.co/YGie7jPjZB Tencent spent $53 billion on hardware for AI workloads. It could recover costs immediately by renting infrastructure. The company prioritizes building its own AI models over renting compute. Tencent released a 295-billion-parameter model Hunyuan-3 in July. Q2 revenue reached $30.3 billion a 11% increase. Net profit rose nine percent to $10.3 billion. WeChat monthly active users grew to 1.349 billion. Tencent plans to sell tokens for AI services like WorkBuddy.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ab5b2cb50febcde256d6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_9a47283ef5e1acdd216d"
        },
        {
          "author_group_id": "ag_25f8bc1eb58e3dc755b9",
          "discourse_keys": [],
          "evidence_id": "e_6913c7c465093e94b7e288c4",
          "excerpt": "Anyone else here working with local Image > 3D models on Apple Silicon? Looking for someone who can do some faithful reproductions on Metal - if you're working in AI, AI to 3D, etc... please please hit me up. SF3D is good - but it's the poor man's Image > 3D pipeline. I'm currently working with Trellis and want to get this to a nice production ready stage, help needed. Hunyuan next... Here's a quick update of my progress so far. First: Metal needs more love. There's lots of people working on getting stuff to work on Metal, but a drop in the ocean compared to the CUDA dudes! Currently trying to get Trellis 2 on Metal to match the Microsoft Demo on @huggingface. It does some stuff well, but there's other stuff it just doesn't. Here's 2 examples; Left is the model generated on upstream demo - uses cuda and some monster hardware. Right is my humble m5 with 32 gigs of unified memory. 1. Fox - I managed to get a closed mesh - but quality wasn't so great. It's got a lot more detail than the o",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_b3bf19dc5860f51f27e7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_97b32495ace7ca3f7c2e"
        },
        {
          "author_group_id": "ag_d4e5803f156a3705e6e4",
          "discourse_keys": [],
          "evidence_id": "e_56ccdba7c382b5210e416f72",
          "excerpt": "you can use deepseek v4 pro, kimi k3 and glm 5.2 for free on a cloud coding agent till year end 😳 a platform called cnb cool runs a cloud agent called codebuddy npc it codes for you, you just describe the task in an issue and its free till december 31 2026 what you get for free: - 11 frontier models to pick from - deepseek v4 pro, deepseek v4 flash, kimi k3, glm 5.2, hunyuan 3 - kimi k2.7, kimi k2.6, glm 5.1, glm 5.0 turbo, minimax m3, minimax m2.7 - full autonomous dev loop: requirements to pr - creates branch, implements code, submits pr on its own - auto fixes build failures and merge conflicts - no credit card, no setup, no clone full setup guide (free): step 1: go to https://t.co/0kFEAYJTEb > create an account, make a repo step 2: open the issues page > create an issue and describe your task step 3: mention the npc > type @npc/CodeBuddy in the issue > add the model you want after it step 4: let it work > npc gets context, codes, pushes, submits pr > you review and merge already si",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_a73a80c8aa17713c3b22",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_9dd208deccc7ebd2100b"
        },
        {
          "author_group_id": "ag_ef2b76eac533f21e6497",
          "discourse_keys": [],
          "evidence_id": "e_2859fd06ee26abf3d5a0b762",
          "excerpt": "$60/M IS EXPENSIVE. $0/M IS CHEAP. LOCAL IS NEITHER. Your price-war graph ends at zero. But zero still means \"on their server, under their rules, with their watermark\". The next line on that graph doesn't slope down. It leaves the axis. 7.9K stars. 6GB VRAM. Wan 2.2, ltx-2, hunyuan, flux. All running in a browser tab, no login, no invoice. Six months from now, the creators who saw this post will be shipping. The ones who scrolled past will be renewing subscriptions. The exit door is already open.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_12a3902e1838ee2cd82f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_dc5010d15e76c1863b99"
        },
        {
          "author_group_id": "ag_66e116db2b2cc5f955bd",
          "discourse_keys": [],
          "evidence_id": "e_326ca8c81b24e0dd37b045b3",
          "excerpt": "Tencent CSO James Mitchell said China’s token prices are low, but production costs are even lower, pushing WorkBuddy’s paid-user gross margins close to Tencent Cloud levels. WorkBuddy now sees over 21 million monthly visits, giving it the scale to build a Codex-like ecosystem; Codex currently has more than 15 million users. Tencent’s AI spending priorities are clear: larger Hunyuan models first, WorkBuddy compute second, and cloud capacity third. Management says most current AI spending is one-off.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_acc60d5225adb1d00b94",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_35fd23056419e5d68f86"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "lead",
        "available_independent_source_count": 25,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 26,
        "selected_count": 25,
        "story_rank": 1,
        "target_count": 25
      },
      "evidence_support": {
        "distinct_author_group_count": 23,
        "distinct_source_cluster_count": 25,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "-0.044098",
              "market_relative_change_pp": "0.044098",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-6.060606",
              "key": "mild_pro",
              "market_change_pp": "-0.602675",
              "market_relative_change_pp": "-5.457931",
              "prior_basis_count": 33,
              "prior_count": 2,
              "prior_prevalence": "0.060606",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-27.272727",
              "key": "none",
              "market_change_pp": "-21.343525",
              "market_relative_change_pp": "-5.929202",
              "prior_basis_count": 33,
              "prior_count": 9,
              "prior_prevalence": "0.272727",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "-0.543878",
              "market_relative_change_pp": "0.543878",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.333333",
          "prior_covered_count": 11,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "-12.121212",
              "key": "advertising_marketing",
              "market_change_pp": "-3.439659",
              "market_relative_change_pp": "-8.681553",
              "prior_basis_count": 33,
              "prior_count": 4,
              "prior_prevalence": "0.121212",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-30.303030",
              "key": "buzz_releases",
              "market_change_pp": "-2.807585",
              "market_relative_change_pp": "-27.495445",
              "prior_basis_count": 33,
              "prior_count": 10,
              "prior_prevalence": "0.303030",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "-1.616934",
              "market_relative_change_pp": "1.616934",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "feedback_questions",
              "market_change_pp": "-6.820520",
              "market_relative_change_pp": "6.820520",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-9.090909",
              "key": "hands_on_usage",
              "market_change_pp": "-14.567103",
              "market_relative_change_pp": "5.476194",
              "prior_basis_count": 33,
              "prior_count": 3,
              "prior_prevalence": "0.090909",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-6.060606",
              "key": "performance_comparisons",
              "market_change_pp": "-10.789358",
              "market_relative_change_pp": "4.728752",
              "prior_basis_count": 33,
              "prior_count": 2,
              "prior_prevalence": "0.060606",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.575758",
          "prior_covered_count": 19,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "-3.030303",
              "key": "mixed",
              "market_change_pp": "-1.572836",
              "market_relative_change_pp": "-1.457468",
              "prior_basis_count": 33,
              "prior_count": 1,
              "prior_prevalence": "0.030303",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "negative",
              "market_change_pp": "-2.719389",
              "market_relative_change_pp": "2.719389",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-33.333333",
              "key": "neutral",
              "market_change_pp": "-18.256651",
              "market_relative_change_pp": "-15.076682",
              "prior_basis_count": 33,
              "prior_count": 11,
              "prior_prevalence": "0.333333",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-21.212121",
              "key": "positive",
              "market_change_pp": "-17.168896",
              "market_relative_change_pp": "-4.043225",
              "prior_basis_count": 33,
              "prior_count": 7,
              "prior_prevalence": "0.212121",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.575758",
          "prior_covered_count": 19,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "-0.426283",
              "market_relative_change_pp": "0.426283",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "-0.058798",
              "market_relative_change_pp": "0.058798",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "-0.058798",
              "market_relative_change_pp": "0.058798",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-33.333333",
              "key": "none",
              "market_change_pp": "-21.960900",
              "market_relative_change_pp": "-11.372434",
              "prior_basis_count": 33,
              "prior_count": 11,
              "prior_prevalence": "0.333333",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "-0.044098",
              "market_relative_change_pp": "0.044098",
              "prior_basis_count": 33,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 26,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.333333",
          "prior_covered_count": 11,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "-21.212121",
          "comparison_state": "available",
          "prior_authors": 31,
          "prior_count": 33,
          "selected_authors": 24,
          "selected_count": 26
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "mild_pro": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "none": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising_marketing": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "buzz_releases": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "hands_on_usage": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "performance_comparisons": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "sentiment": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "mixed": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "neutral": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "positive": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "none": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "hunyuan:full_window",
          "direction": "decrease",
          "display_en": "21%",
          "display_zh_cn": "21%",
          "fact_id": "qf_aa44739c4fe2989fd3b15a2e",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "-21.212121",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "post_type",
          "rank": 2,
          "stream_position": 2
        },
        {
          "family": "sentiment",
          "rank": 2,
          "stream_position": 2
        },
        {
          "family": "nationalism",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-08-13T00:00:00Z"
    },
    {
      "brand_key": "qwen",
      "candidate_id": "qwen:full_window",
      "coarse_series": {
        "author_counts": [
          103,
          90,
          94,
          159,
          143,
          143,
          118,
          80
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            117,
            93,
            99,
            171,
            159,
            153,
            133,
            89
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                15,
                20,
                13,
                27,
                21,
                21,
                15,
                14
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                102,
                73,
                86,
                144,
                138,
                132,
                118,
                75
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          117,
          93,
          99,
          171,
          159,
          153,
          133,
          89
        ]
      },
      "display_name_en": "Qwen",
      "display_name_zh_cn": "Qwen",
      "end_at": "2026-08-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_fb4134c071d51639324a",
          "discourse_keys": [],
          "evidence_id": "e_5554301696631d14076f55bb",
          "excerpt": "这轮 Qwen、DeepSeek、Kimi 旗舰开源模型给我最大的启发，不只是参数量继续增长，而是： Open-weight ≠ easy to self-host。 过去企业所谓的 self-host，基本是： 买一台 Dell/HPE/Supermicro 8卡 OEM AI server → 下载权重 → vLLM/SGLang → 挂一个内部 API。 但现在，部分满血或 FP8 frontier model 已经跨过单个 8-GPU NVLink domain 的显存边界；另一些即使勉强装得下，也几乎不给 KV cache、长上下文、并发和 HA 留空间。 真正的生产部署开始需要： 16/32张GPU、多节点高速网络、TP/PP/EP、prefill-decode separation、KV/state routing、调度、监控和故障恢复。 Self-host 的最小单位，正在从 single-node OEM AI server 变成 multi-node AI factory。 这并不意味着 OEM AI server 没有市场。FP4、Flash、蒸馏版、企业领域模型、RAG 和 Agent 仍然适合单节点部署。但想运行满血 frontier open model，企业买的已经不是一台服务器，而是一套 rack-scale infrastructure。 这也解释了为什么 open-source 不一定会削弱 NBIS、CRWV 等 Neocloud，反而可能强化它们： 模型权重被民主化了，但 frontier infrastructure 没有被民主化。 NBIS 和 CRWV 最新财报验证了几个趋势： 需求已经从训练扩散到 post-training、managed inference、open models 和 enterprise； 旧一代 GPU 仍可以承接 FP4、推理、RAG、Agent 和 batch workloads； GPU 的“技术前沿寿命”可能只有1–2年，但“经济产生现金流的寿命”可以达到5年以上； 真正稀缺的不是单张GPU，而是已经通电、联网、可调度、可交付的 AI cluster。 所以 NVIDIA 的 moat 也不应只理解为 CUDA，而是： GPU + NVLink/NVSwitch + Networking",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_92eb1656320f056a9139",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_b3906fa4c8fdcecd59f1"
        },
        {
          "author_group_id": "ag_216516657bdbf33ec1eb",
          "discourse_keys": [],
          "evidence_id": "e_20f986ff6f6ead09561466a7",
          "excerpt": "@PastaMaxxer @arthurmensch GLM 5.2 is a good start but, even on 'just' serving the latest Chinese models (Qwen, K3 and DS being the priority ones), Mistral needs to be far more ambitious. There's a huge opportunity regarding full throttle, EU-based endpoints. Inference onboarding should be far nimbler too!",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_54957d0bcb3b13fcc819",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_4f636647ffa39cf5f222"
        },
        {
          "author_group_id": "ag_08dfc6abbf22f7246ae2",
          "discourse_keys": [],
          "evidence_id": "e_c49f13c2d6132bcc4713b112",
          "excerpt": "Qwen 3.6の無検閲Fable Fusion👁️👁️",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_384400ed9ee8f1a8840d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7aee4b6ab8dda9ddf456"
        },
        {
          "author_group_id": "ag_f2977d5deac99ce731c8",
          "discourse_keys": [],
          "evidence_id": "e_2c74e81b0b97cde7339073c7",
          "excerpt": "@juanmacias Es una locura, a mi me pasa lo mismo con Claude .En si ahora uso Qwen 3.8 Max o 3.7 por ahorro/Gpt Sol high para tema de backend/Infra",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7ffd5421a380dbabfd6c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_468252c8111dd52a2004"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "floor",
        "available_independent_source_count": 63,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 64,
        "selected_count": 4,
        "story_rank": 6,
        "target_count": 4
      },
      "evidence_support": {
        "distinct_author_group_count": 4,
        "distinct_source_cluster_count": 4,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "volume": {
          "change_pct": "-17.627945",
          "comparison_state": "available",
          "prior_authors": 984,
          "prior_count": 1231,
          "selected_authors": 855,
          "selected_count": 1014
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "qwen:full_window",
          "direction": "decrease",
          "display_en": "18%",
          "display_zh_cn": "18%",
          "fact_id": "qf_a033b9665a3d26e73ff2b188",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "-17.627945",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "volume",
          "rank": 3,
          "stream_position": 3
        }
      ],
      "start_at": "2026-08-13T00:00:00Z"
    },
    {
      "brand_key": "llama",
      "candidate_id": "llama:full_window",
      "coarse_series": {
        "author_counts": [
          15,
          10,
          13,
          17,
          21,
          23,
          17,
          10
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            15,
            11,
            13,
            18,
            25,
            26,
            17,
            10
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                3,
                2,
                1,
                2,
                8,
                3,
                0,
                1
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                12,
                9,
                12,
                16,
                17,
                23,
                17,
                9
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          15,
          11,
          13,
          18,
          25,
          26,
          17,
          10
        ]
      },
      "display_name_en": "Meta Llama",
      "display_name_zh_cn": "Meta Llama",
      "end_at": "2026-08-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_c576d1ab0f617c3d7dde",
          "discourse_keys": [],
          "evidence_id": "e_c80211fabe3abd317a5db63c",
          "excerpt": "Fui puxar o fio de um paper do NBER que saiu em julho e pouca gente comentou: \"AI Premium\", de Borri (Luiss), Tsyvinski (Yale) e Liu (Rochester). O dataset é absurdo. 380 trilhões de tokens de consumo real de AI via OpenRouter — plataforma que roteia requests pra GPT, Claude, Gemini, Llama, DeepSeek e mais de 400 modelos. São ~2% do consumo global mensal. Dados de jan/2024 a abr/2026, nível usuário-modelo-dia. Milhões de contas. Com isso eles construíram um fator de AI — parecido com o que Fama-French fez pra value/size — e mediram o prêmio que empresas expostas a AI ganham na bolsa. O número central: 64,1 bps por semana. Long-short value-weighted. Sobrevive a Fama-French 5 fatores + momentum (56 bps, t=2,41). Sobrevive a controle por Google Trends de AI (69,6 bps). Sobrevive quando tira semanas de lançamento de modelos (39,5 bps). O prêmio é real, não é hype. Mas aí vem o detalhe que muda tudo: o prêmio só existe no uso intensivo. • Closed-source (GPT, Claude): 53 bps/semana • Open-we",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7141794786344f9a2617",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_dabfe1a8827883db7f2f"
        },
        {
          "author_group_id": "ag_814aa2172de7f4e10f8b",
          "discourse_keys": [],
          "evidence_id": "e_cfd5ce0f226d1f1be5f649c6",
          "excerpt": "高性能LLM導入でコストや専用ハードがネックになっている課題へ Llama 3.3はテキスト特化の最適化で70BながらGPT‑4相当の精度を実現。MMUL86%（GPT‑4:86.4%）、HumanEval88.4%、MATH77%。128Kコンテキスト・低ビット量子化で一般ワークステーション運用も可能。 自社PoCの候補に入れる価値はあるだろうか。https://t.co/OxXC5MKVJB",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d14462fb1093654501af",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_80da10b0764f1769e9c0"
        },
        {
          "author_group_id": "ag_2231e8e3ce08fb4d5eb1",
          "discourse_keys": [],
          "evidence_id": "e_990ff6049726a0da7667901d",
          "excerpt": "Cierre IA: agente en tu GPU, bots con PC propio y Gemini a mil millones 𝗠𝘂𝘀𝗲 𝗚𝗹𝗶𝗺𝗺𝗲𝗿: 𝟥𝟢𝗕 𝗼𝗽𝗲𝗻 𝗽𝗮𝗿𝗮 𝗮𝗴𝗲𝗻𝘁𝗲𝘀 𝗹𝗼𝗰𝗮𝗹𝗲𝘀 Meta Superintelligence Labs suelta Muse Glimmer (30B, Apache 2.0): pensado para agentes always-on en Mac/PC con una sola GPU de consumo. Destilación desde un teacher más grande + cuantización ~4-bit (<20 GB) y drafter DFlash. En las evals de Meta (vs Gemma4-31B y Qwen3.6-27B): MCP-Atlas 75,5 / DeepSearch QA 74,6 / SWE-Bench Verified 76,0; Qwen sigue delante en OSWorld y Terminal-Bench. Pesos en Hugging Face; llama.cpp/MLX/ExecuTorch en camino. Fuente(s): https://t.co/IXcUtI3Xrx https://t.co/b2gyBxRA3D 𝗚𝗿𝗼𝗸 𝗕𝗼𝘁: 𝗰𝗼𝗺𝗽𝗮ñ𝗲𝗿𝗼𝘀 𝗰𝗼𝗻 𝘀𝘂 𝗽𝗿𝗼𝗽𝗶𝗮 𝗺á𝗾𝘂𝗶𝗻𝗮 SpaceXAI abre beta de Grok Bot: agentes 24/7 con computador propio en la nube, login a apps reales (incluso sin API limpia), mensajería tipo colega y varios bots en paralelo. Disponible para SuperGrok Heavy, Cursor Ultra y Cursor Teams Premium (desktop/iOS); enterprise en waitlist. Fuente(s): https://t.co/yCyV4aHpRQ 𝗚𝗲𝗺𝗶𝗻𝗶 𝗔𝗽𝗽: 𝟣.𝟢𝟢",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_50548b8a9845cc4241e1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_65b223763af4a188b96f"
        },
        {
          "author_group_id": "ag_59de96ef916b57a0736f",
          "discourse_keys": [],
          "evidence_id": "e_5ed805d14fcda1d7820d35a1",
          "excerpt": "How to Create Your Own AI When people say \"create your own artificial intelligence (AI) model\", they rarely mean training one from scratch. That takes millions of dollars and industrial hardware. It almost always means running an existing open-source model on your own computer and shaping it until it feels like yours. You need very little theory. Model size (7B, 13B, 70B): B means billions of parameters, roughly brain size. Bigger is smarter but slower. For most laptops, 3B to 14B is the sweet spot. Quantization (Q4, Q8): compression that lets big models run on normal hardware. Q4 is the standard; it shrinks a 7B model from about 14 gigabytes (GB) to 5GB with minor quality loss. Your computer's memory (RAM) decides everything: 8GB → 3B models (Llama 3.2 3B) 16GB → 7B–13B (Mistral 7B, Qwen 8B) 32GB → up to ~30B (Qwen 14B) 64GB+ → 70B models Two free tools, both on Mac, Windows and Linux: LM Studio, if you never want to see a terminal. Browse models, click download, chat. Nothing you typ",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_b88640e170c644010dd5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_13763ab6261a245639ee"
        },
        {
          "author_group_id": "ag_6cb484f0a00c3322df17",
          "discourse_keys": [],
          "evidence_id": "e_6146303ce3b27e19f6ce6781",
          "excerpt": "Which of the following is developed by xAI? A. Claude B. GPT-4o C. Gemini D. Grok E. Llama F. Qwen G. Phi-3",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_f3798f2658a6eebd216d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_b84df7c2149beb407417"
        },
        {
          "author_group_id": "ag_9b36c91e1b4089433eee",
          "discourse_keys": [],
          "evidence_id": "e_f49078023175d9b291a37d8a",
          "excerpt": "10 FREE GITHUB REPOS THAT REPLACE $30,000 A YEAR IN PAID TOOLS 1,8M stars between them and every one costs you nothing 1. awesome, 495k stars the master list of every other list, whatever you need is already in here https://t.co/df7JJQddRo 2. public-apis, 456k stars 1,400 free APIs across 50 categories, weather, finance, images, games, all documented https://t.co/PqEFBgfUgw 3. scrapling, 73.6k stars undetectable web scraping with Cloudflare bypass baked in, kills the $300 a month scraping API https://t.co/xSIV0WMbFZ 4. free-for-dev, 132k stars hundreds of services with permanent free tiers, no trial, no card https://t.co/E9Io07xIw1 5. ollama, 178k stars run Llama, Mistral or DeepSeek locally with one command, zero API bill https://t.co/lAWfIjmAPX 6. langflow, 153k stars drag and drop builder for AI agents and RAG pipelines, ship it as an API or MCP server https://t.co/5dsxiGvT2a 7. awesome-mcp-servers, 92k stars thousands of MCP servers wiring your agent to browsers, databases and ever",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a7c0e1ac6ae453e3fcf5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_e05a09d6031e90d95056"
        },
        {
          "author_group_id": "ag_c703b58290ffa689bec2",
          "discourse_keys": [],
          "evidence_id": "e_fd3cdf66603f8bd0f32c0fe5",
          "excerpt": "🤖 AI DAILY BRIEF — 13 AGUSTUS 2026 TODAY'S VIBE: Dalam 48 jam terakhir, open-source AI nggak pernah semenarik ini. Alibaba release weights model terbesar mereka seumur hidup, Meta balik ke open source setelah 16 bulan absen, DeepSeek diam-diam drop model 57x lebih murah dari Claude, dan Grok 4.6 finally landed. Di sisi lain, NVIDIA lagi bermain di level beda — mengubah GPU jadi \"investable asset class\" $500B. Oh iya, Bernie Sanders juga kirim ultimatum ke Sam Altman, Dario, dan Zuck. Lumayan ramai. --- 1. NVIDIA + WALL STREET: $500B COMPUTE FINANCING PLATFORM Jensen Huang announce kemitraan dengan Apollo, BlackRock, Blackstone, Brookfield, Goldman Sachs, dan KKR untuk mobilisasi lebih dari $500 miliar dolar buat AI infrastructure. \"In AI, compute is revenue\" — GPU kini mau dibiayai seperti jalan tol atau pembangkit listrik. Ini bisa drastis ubah siapa yang bisa bangun AI factory. Untuk lab kecil dan negara berkembang, ini potentially life-changing access ke compute. https://t.co/YSgugH",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_cc64fd55fd7806707de7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_83cf84f6a605742a3575"
        },
        {
          "author_group_id": "ag_58b4d5d64a6003b77096",
          "discourse_keys": [],
          "evidence_id": "e_193177b70af743ac07276d40",
          "excerpt": "DEEPSEEK ACABA DE LANZAR SU RIVAL OPEN SOURCE DE CLAUDE CODE se llama DeepSeek Harness no es otro modelo para chatear es un agente que puede trabajar directamente sobre proyectos de codigo, usar herramientas y ejecutar tareas completas como los agentes de programacion que estan explotando este año y llega justo cuando Claude Code, Codex y Cursor estan peleando por convertirse en el lugar donde programamos todo la diferencia es bastante importante DeepSeek lo esta llevando al open source la guerra ya no es por tener el modelo mas inteligente es por quien termina controlando al agente que escribe tu codigo",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_159d74f5d9553ee305fb",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_3dc5dcbd48eba7240dc5"
        },
        {
          "author_group_id": "ag_bdd759515d06ae5a86a2",
          "discourse_keys": [],
          "evidence_id": "e_65126ea758d51f5d0eb71068",
          "excerpt": "✅ Foundation-Sec-8B-Reasoning initial round deployed (pre-bios modification) Engine: llama.cpp (Vulkan backend) — not vLLM. vLLM needs CUDA/ROCm, which AMD APUs can't do; llama.cpp offloads matmuls to the Radeon iGPU over unified memory (RADV, Vulkan 1.4.318). Quant: official fdtn-ai Q4_K_M GGUF (4.58 GiB) — the right fit for 64k on this box. Q8_0 (7.95 GiB) was too fat. 64k context: native Llama 3.1 capability, no rope scaling. KV cache quantized (Q8_0 K / Q4_0 V) to keep memory sane. Decode speed ~8 tok/s prefill ~67 tok/s (iGPU offload, all 33 layers) context_length: 65536 Verified end-to-end: a real hermes -p sec-mini session answered T1566.001 Things worth knowing The \"16GB\" is really 12GB — the BIOS UMA frame buffer carves out ~4GiB for the iGPU. Not required to change for this config (fits with ~5.8GB headroom), but lowering it later would let us jump to higher Kv cache quantization, longer context, maybe even Q8 for the model. Initial results within expected range. Now some mor",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0a7d66dc7f20b4a29374",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "quote"
          },
          "theme_cluster_id": "th_5af49158696952d775ae"
        },
        {
          "author_group_id": "ag_ed561c61808b9f5100f6",
          "discourse_keys": [],
          "evidence_id": "e_8ee87d019ad604dfdb5f646e",
          "excerpt": "A 30B agent just dropped onto a single consumer GPU. Muse Glimmer is Apache 2.0 open-weights from Meta, distilled from Muse Spark for always-on local agents, function calling, coding, and LLM-as-a-judge. Full precision needs over 55 GB. About 4-bit quantization puts the language model under 20 GB, with a K-Quant-17GB build plus DFlash drafter measured on M4-Max, M5-Max, and RTX-5090. 1. Cloud vs local. Cloud still wins on frontier depth. Local wins when the agent needs your files, calendar, and screenshots with no API hop. 2. Agent-first training. The page names DeepSearch QA, MCP-Atlas, tau-Bench, and SWE-Bench, plus failure recovery and a perception encoder. No scores. Size-class peers are Gemma 4 31B and Qwen 3.6 27B. 3. License is the unlock. Apache 2.0 lets you fine-tune, ship, and keep the loop on-device. llama.cpp, MLX, and ExecuTorch are still landing. Decision rule: if the job needs personal context and must stay on the machine, run Glimmer locally. If you still need undistill",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_07c86255b1886b655b7e",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a5e0d05988048ce24440"
        },
        {
          "author_group_id": "ag_f3372a89c728df94c027",
          "discourse_keys": [],
          "evidence_id": "e_65e23d2fed8bb7617a2d4137",
          "excerpt": "@Kimi_Moonshot Expert importance scores came free: llama.cpp's imatrix (originally by ikawrakow) already records per-expert counts and activation energy.Routing is highly skewed. In layer 40: coldest expert 52 calls, hottest 57,948—1,114×. That's why pruning is cheap.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_b9c0e6f839eb211e59b1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_aa5562267f539e4f07a4"
        },
        {
          "author_group_id": "ag_8052099132e7826e292f",
          "discourse_keys": [],
          "evidence_id": "e_13fc2784de33b471fdad4a33",
          "excerpt": "Which open source AI model is your daily driver? - DeepSeek V4 - Qwen 3.5 - Kimi K2.6 - GLM 5 - Llama 4 - Mistral Large - Other",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_22fa2606569ac6a75431",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_302f588c2ec7733b0075"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 63,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 64,
        "selected_count": 12,
        "story_rank": 5,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "-4.964539",
              "key": "advertising_marketing",
              "market_change_pp": "-3.439659",
              "market_relative_change_pp": "-1.524880",
              "prior_basis_count": 141,
              "prior_count": 7,
              "prior_prevalence": "0.049645",
              "selected_basis_count": 135,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-6.382979",
              "key": "buzz_releases",
              "market_change_pp": "-2.807585",
              "market_relative_change_pp": "-3.575394",
              "prior_basis_count": 141,
              "prior_count": 9,
              "prior_prevalence": "0.063830",
              "selected_basis_count": 135,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-1.418440",
              "key": "event_announcement",
              "market_change_pp": "-1.616934",
              "market_relative_change_pp": "0.198494",
              "prior_basis_count": 141,
              "prior_count": 2,
              "prior_prevalence": "0.014184",
              "selected_basis_count": 135,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-8.510638",
              "key": "feedback_questions",
              "market_change_pp": "-6.820520",
              "market_relative_change_pp": "-1.690118",
              "prior_basis_count": 141,
              "prior_count": 12,
              "prior_prevalence": "0.085106",
              "selected_basis_count": 135,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-9.929078",
              "key": "hands_on_usage",
              "market_change_pp": "-14.567103",
              "market_relative_change_pp": "4.638025",
              "prior_basis_count": 141,
              "prior_count": 14,
              "prior_prevalence": "0.099291",
              "selected_basis_count": 135,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "-21.276596",
              "key": "performance_comparisons",
              "market_change_pp": "-10.789358",
              "market_relative_change_pp": "-10.487238",
              "prior_basis_count": 141,
              "prior_count": 30,
              "prior_prevalence": "0.212766",
              "selected_basis_count": 135,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.510638",
          "prior_covered_count": 72,
          "selected_coverage_ratio": "0.000000",
          "selected_covered_count": 0
        },
        "volume": {
          "change_pct": "-4.255319",
          "comparison_state": "available",
          "prior_authors": 121,
          "prior_count": 141,
          "selected_authors": 121,
          "selected_count": 135
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "post_type": {
          "coverage_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising_marketing": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "buzz_releases": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "event_announcement": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "feedback_questions": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "hands_on_usage": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "performance_comparisons": {
              "counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "llama:full_window",
          "direction": "decrease",
          "display_en": "4%",
          "display_zh_cn": "4%",
          "fact_id": "qf_e9aeba400df912515d5a81b9",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "-4.255319",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "post_type",
          "rank": 3,
          "stream_position": 3
        }
      ],
      "start_at": "2026-08-13T00:00:00Z"
    }
  ],
  "comparison_allowed": true,
  "comparison_suppressed_reasons": [],
  "coverage": {
    "prior": {
      "earliest_at": "2025-01-15T09:47:50Z",
      "known_backlog_overlap": false,
      "ratio": "1.000000",
      "state": "sufficient"
    },
    "selected": {
      "earliest_at": "2025-01-15T09:47:50Z",
      "known_backlog_overlap": false,
      "ratio": "1.000000",
      "state": "sufficient"
    }
  },
  "evidence_policy": {
    "comparison_ceiling": 12,
    "excerpt_characters": 1000,
    "floor": 4,
    "lead_ceiling": 48,
    "provider_packet_bytes": 131072,
    "reservoir_rank_limit": 32,
    "version": "adaptive-v1"
  },
  "quantitative_fact_schema_version": 1,
  "series_axis": {
    "coarse": {
      "bucket_count": 8,
      "duration_seconds": 10800,
      "ends": [
        "2026-08-13T03:00:00Z",
        "2026-08-13T06:00:00Z",
        "2026-08-13T09:00:00Z",
        "2026-08-13T12:00:00Z",
        "2026-08-13T15:00:00Z",
        "2026-08-13T18:00:00Z",
        "2026-08-13T21:00:00Z",
        "2026-08-14T00:00:00Z"
      ],
      "starts": [
        "2026-08-13T00:00:00Z",
        "2026-08-13T03:00:00Z",
        "2026-08-13T06:00:00Z",
        "2026-08-13T09:00:00Z",
        "2026-08-13T12:00:00Z",
        "2026-08-13T15:00:00Z",
        "2026-08-13T18:00:00Z",
        "2026-08-13T21:00:00Z"
      ]
    }
  },
  "snapshot_schema_version": 1,
  "thresholds": {
    "episode_peak_ratio": "3.0",
    "max_episodes_per_candidate": 3,
    "min_authors": 10,
    "min_posts": 20,
    "minimum_coverage": "0.75"
  },
  "unresolved_backlog_intervals": [],
  "window_days": 1
}
~~~


## Exact provider packet — 2026-07-13 window

The following is the canonical JSON packet supplied to the provider for the 2026-07-13 window. The single long line is intentional: it preserves the exact serialized packet bytes.

~~~json
{
  "as_of": "2026-07-14T00:00:00Z",
  "candidates": [
    {
      "brand_key": "deepseek",
      "candidate_id": "deepseek:full_window",
      "coarse_series": {
        "author_counts": [
          35,
          61,
          55,
          51,
          62,
          72,
          73,
          37
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            37,
            63,
            58,
            60,
            73,
            81,
            79,
            39
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                37,
                63,
                58,
                60,
                73,
                81,
                79,
                39
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          37,
          63,
          58,
          60,
          73,
          81,
          79,
          39
        ]
      },
      "display_name_en": "DeepSeek",
      "display_name_zh_cn": "DeepSeek",
      "end_at": "2026-07-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_be11b69ca04f1c7b3845",
          "discourse_keys": [],
          "evidence_id": "e_c6a074114c7e68ed5136e36c",
          "excerpt": "China Isn’t Just Building AI. It’s Building the Entire AI Economy. Most discussions about AI focus on who has the best model. China is playing a much bigger game. It’s building an end-to-end AI ecosystem where every layer reinforces the next: 🔹 AI Models – DeepSeek, Qwen, ERNIE, MiniMax, Kimi, Hunyuan and many others compete relentlessly, driving innovation and lowering costs. 🔹 Hyperscale Cloud Infrastructure – Alibaba Cloud, Tencent Cloud, Huawei Cloud, Baidu Cloud and Volcano Engine are investing billions in GPUs, data centres and AI infrastructure to power the next generation of applications. 🔹 Developer Platforms – APIs, orchestration layers and agent frameworks make it easier for businesses to build AI products without starting from scratch. 🔹 Enterprise Adoption – Companies deploy AI into customer service, software development, healthcare, finance, manufacturing and education, creating real business value. 🔹 The Flywheel – More users generate more data. More data improves models",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_995e6b5b4e965ffb74cf",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_af85a773c5f8f5285913"
        },
        {
          "author_group_id": "ag_a85eadece708eca03c00",
          "discourse_keys": [],
          "evidence_id": "e_f791ae40f456a03bbdbea040",
          "excerpt": "Okay, so I am NOT trying to force people to use AI, but apparently a LOT of people are either confused or didn't research what they are protesting. So here is a 40,000 foot view summary of exactly WHAT AI is. What is AI? At its core, Generative AI (GenAI) is fundamentally textual. These systems are large language models (LLMs) trained to understand and generate human-like text. They reason, write, code, summarize, and plan using language as their native medium. Grok (built by xAI): Truth-seeking, technically strong, and helpful with a touch of humor. ChatGPT (OpenAI): Versatile all-rounder, great for creative writing, conversations, and general tasks. DeepSeek: Excels at technical work, math, and programming. Gemini (Google): Strong multimodal capabilities and web-integrated knowledge. Image and Video Generation are not core GenAI functions. They are secondary specialized models (usually diffusion models) that take text output from a GenAI model as input. In practice, the main LLM acts",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_617ccaab7817a4a373cd",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_e150d7bf209a600f7e64"
        },
        {
          "author_group_id": "ag_4624781b36b12d43b350",
          "discourse_keys": [
            "genuine_hype"
          ],
          "evidence_id": "e_e686a5e015b814593c670fdf",
          "excerpt": "[update] - So, I trained qwen3-1.7b using SFT for 40 steps on 600 samples of synthetic data which I had created using deepseek v4 flash, which consisted of 600 unique puzzles and basically the data was in a similar format like the wordle sft data by @PrimeIntellect . - The base model was writing super verbose reasoning traces and it would exhaust 1024 tokens before even making the actual move. After SFT, it is writing much more concise reasoning traces and a good thing is that it is able to even solve quite a bit of the simple puzzles, thouhg it's struggling in the medium/hard ones(which is where rl will hopefully come into play). - Also one more promising thing imo is that during the eval the SFT checkpoint model attempted a total of 5639 moves and out of this only 36 moves were illegal. From this I'm inferring that by seeing the SFT data it might have gotten a bit of idea about what are the possible legal moves for a given puzzle state. - Now, it's time to play around with rl trainin",
          "post_type_keys": [
            "performance_comparisons"
          ],
          "roles": [
            "dominant_discourse_representative",
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_18c49a7f78c0111c797d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_06a23fc359dc20cb6929"
        },
        {
          "author_group_id": "ag_7af0ea9bb410ddf7484b",
          "discourse_keys": [],
          "evidence_id": "e_e9dab13669382580c3d6ccc5",
          "excerpt": "🚨 NEW MODEL ALERT Singapore just dropped a model that's putting up frontier-level numbers. Agnes 2.5 Pro: • 82.7 on SWE-bench Verified • 78.7 multilingual • Strong gains on SWE Atlas • Beating GLM 5.2 and DeepSeek V4 Pro on multiple cuts • Free API available today The biggest takeaway isn't the benchmark here. It's the country. NOW frontier is no longer just a US vs China story.",
          "post_type_keys": [
            "performance_comparisons"
          ],
          "roles": [
            "contrasting_reaction",
            "supporting_context"
          ],
          "sentiment_keys": [
            "negative"
          ],
          "source_cluster_id": "sc_text_96823d448064c677bc7a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a0a0a157342c6278d82d"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "floor",
        "available_independent_source_count": 94,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 96,
        "selected_count": 4,
        "story_rank": 4,
        "target_count": 4
      },
      "evidence_support": {
        "distinct_author_group_count": 4,
        "distinct_source_cluster_count": 4,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "volume": {
          "change_pct": "2478.947368",
          "comparison_state": "available",
          "prior_authors": 19,
          "prior_count": 19,
          "selected_authors": 415,
          "selected_count": 490
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "deepseek:full_window",
          "direction": "increase",
          "display_en": "2479%",
          "display_zh_cn": "2479%",
          "fact_id": "qf_5d43bfdf698712e3e2314859",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "2478.947368",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "volume",
          "rank": 1,
          "stream_position": 1
        }
      ],
      "start_at": "2026-07-13T00:00:00Z"
    },
    {
      "brand_key": "ernie",
      "candidate_id": "ernie:full_window",
      "coarse_series": {
        "author_counts": [
          13,
          9,
          1,
          1,
          1,
          0,
          0,
          0
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            16,
            9,
            7,
            1,
            1,
            0,
            0,
            0
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                16,
                9,
                7,
                1,
                1,
                0,
                0,
                0
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          16,
          9,
          7,
          1,
          1,
          0,
          0,
          0
        ]
      },
      "display_name_en": "Baidu ERNIE",
      "display_name_zh_cn": "Baidu ERNIE",
      "end_at": "2026-07-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_be11b69ca04f1c7b3845",
          "discourse_keys": [],
          "evidence_id": "e_7d9f5f1e52e7554024ca4754",
          "excerpt": "China Isn’t Just Building AI. It’s Building the Entire AI Economy. Most discussions about AI focus on who has the best model. China is playing a much bigger game. It’s building an end-to-end AI ecosystem where every layer reinforces the next: 🔹 AI Models – DeepSeek, Qwen, ERNIE, MiniMax, Kimi, Hunyuan and many others compete relentlessly, driving innovation and lowering costs. 🔹 Hyperscale Cloud Infrastructure – Alibaba Cloud, Tencent Cloud, Huawei Cloud, Baidu Cloud and Volcano Engine are investing billions in GPUs, data centres and AI infrastructure to power the next generation of applications. 🔹 Developer Platforms – APIs, orchestration layers and agent frameworks make it easier for businesses to build AI products without starting from scratch. 🔹 Enterprise Adoption – Companies deploy AI into customer service, software development, healthcare, finance, manufacturing and education, creating real business value. 🔹 The Flywheel – More users generate more data. More data improves models",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_995e6b5b4e965ffb74cf",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_660a6085b598137d0385"
        },
        {
          "author_group_id": "ag_d7173d7fa8047d7232be",
          "discourse_keys": [],
          "evidence_id": "e_0b58eda1edc095b4361f1963",
          "excerpt": "Τα περισσότερα μεγάλα κινεζικά AI labs (DeepSeek, Qwen, GLM, Kimi, MiniMax, Hunyuan, ERNIE) έχουν πλέον διαθέσει σημαντικά μοντέλα ως open weights, συχνά με άδειες MIT ή Apache 2.0. Αντίθετα, τα δυτικά GPT-5, Claude, Gemini παραμένουν closed. https://t.co/iOomhrjblq",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3ecc99e0383b5612ef11",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_68c2559f732d1be89829"
        },
        {
          "author_group_id": "ag_d29796c468f2478dbc5a",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_881c9481df8fab562887abb5",
          "excerpt": "@77Q66 @OptimusVibee You have a huge influence. Please tell more people about the strengths of this project. On BSC, $BIBI became a leading AI agent. On Robinhood Chain, I believe $ERNIE can become the equivalent. It's still early, and more people should know about its potential.",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "dominant_discourse_representative",
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_e26023618fdb205dfc92",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_2b667e709b354b080b01"
        },
        {
          "author_group_id": "ag_374f01ab3ff56b2ca992",
          "discourse_keys": [],
          "evidence_id": "e_e609071f089c3e1f248ab4d4",
          "excerpt": "Here’s a clean, copyable list of major Chinese AI models (LLMs and notable systems): • Qwen (Alibaba) – Qwen2, Qwen2.5, Qwen-Max • DeepSeek – DeepSeek-V2, DeepSeek-V3, DeepSeek-R1 • ERNIE (Baidu) – ERNIE 4.0, ERNIE-Speed • GLM (Zhipu AI) – GLM-4, GLM-4V, ChatGLM • Yi (https://t.co/4TEdd86hyN) – Yi-1.5, Yi-Large • Doubao (ByteDance) – Doubao-Pro, Doubao-1.5-Pro • Kimi (Moonshot AI) • Hunyuan (Tencent) – Hunyuan-Pro • Aquila (BAAI) • InternLM (Shanghai AI Lab) • TeleChat (China Telecom) • Spark (iFlyTek) • Baichuan (Baichuan Intelligence) – Baichuan2, Baichuan3 • SenseChat (SenseTime) • Yang (Alibaba, older series)",
          "post_type_keys": [
            "buzz_releases"
          ],
          "roles": [
            "contrasting_reaction",
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_e7911bd0d6071d4cad98",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_b378263fd89f82732452"
        },
        {
          "author_group_id": "ag_7bff0d78ba16b4b21718",
          "discourse_keys": [],
          "evidence_id": "e_ec149a442c490f2839e83575",
          "excerpt": "Cashed us out again 😭🔥🤑🍀 ✅ Sam Antonacci HR ✅ Jake McCarthy HR ✅ Ernie Clement HR Need a win? ➡️ Click the Link in my Comment box for the rest 💯 Secured winning slates… #MLB #fanduel #GamblingX @Playbook https://t.co/r5wWT0Daw5",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_399c330b0e4bec440f94",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7a305995549b2c98eb7d"
        },
        {
          "author_group_id": "ag_35e61a5ac5f06505f7d2",
          "discourse_keys": [],
          "evidence_id": "e_4b785d6f5385015010a5401b",
          "excerpt": "Cashed us out again 😭🔥🤑🍀 ✅ Sam Antonacci HR ✅ Jake McCarthy HR ✅ Ernie Clement HR ➡️ Need a win? ➡️ Click The Link Below To Get Daily Secured Guaranteed Winning Picks ⬇️⬇️💯 https://t.co/coS0BxXlSa #MLB #fanduel #GamblingX @Playbook https://t.co/3vesD3U3fd",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ee59eed5eadca5cb2743",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7a305995549b2c98eb7d"
        },
        {
          "author_group_id": "ag_1e4d27be19f4b80c9c2d",
          "discourse_keys": [],
          "evidence_id": "e_50b113e5b5c038306b39095e",
          "excerpt": "@BarrySchust Ernie Banks",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_3f7a0491fdb7d2d3ac35",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_e71a5ad04246ce50c67b"
        },
        {
          "author_group_id": "ag_e91c718677e7207883ad",
          "discourse_keys": [],
          "evidence_id": "e_bb5247961cdf17dacc1e5c02",
          "excerpt": "@BarrySchust Mr. Cubs, Ernie Banks",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_6cbfc98fe362253c25a4",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_e71a5ad04246ce50c67b"
        },
        {
          "author_group_id": "ag_92ee28d9e87af5965638",
          "discourse_keys": [],
          "evidence_id": "e_0b5dd986ee293916f8a3ce7f",
          "excerpt": "@TalkinBaseball_ F- World Series to last place and the star player hitting 6 homers in 92 games, the only positive has been the Free Agent signings, Ernie and Varland being the only ones performing. Consistently. Nothing short of an embarrassment",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_8d4b8a005ed046ea7072",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_d3c3a1ad60a371fc73bc"
        },
        {
          "author_group_id": "ag_d54b0af62dbbf4d484de",
          "discourse_keys": [],
          "evidence_id": "e_37ca788e2d8bbfb4ddece092",
          "excerpt": "#NEWS Lithium Africa to Strengthen Board of Directors with Nomination of John Kanellitsas and Ernie Ortiz Dr. Thomas Benson, Chief Executive Officer, commented: “John and Ernie are two of the most respected leaders in the lithium sector, and I am thrilled to welcome them as we build Lithium Africa into a world-class exploration and consolidation platform. John has been a mentor to me since my time at Lithium Americas and Lithium Argentina, where he helped guide both companies through periods of exploration, development, and extraordinary growth. Ernie has spent his career at the center of critical minerals capital markets, and his track record in structuring and financing lithium assets around the world is exactly the expertise that will help us deliver value for our shareholders, our host countries, and the communities where we operate.” 🔗Full news release: https://t.co/qXZM3ApLgM 🇨🇦 TSX-V: #LAF | 🇩🇪 FSE: #6MQ | 🇺🇸 OTCQB: #LTAFF $LAF #GanfengLithium #Lithium #CriticalMinerals #Explora",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7d84aced14c807d325a3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_e25c209184c26731b6ed"
        },
        {
          "author_group_id": "ag_d29796c468f2478dbc5a",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_2d769d244b0a0d258599db15",
          "excerpt": "@verah_tee @OptimusVibee @grok You have a huge influence. Please tell more people about the strengths of this project. On BSC, $BIBI became a leading AI agent. On Robinhood Chain, I believe $ERNIE can become the equivalent. It's still early, and more people should know about its potential.",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_cc5f5edce6b074573e72",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_2b667e709b354b080b01"
        },
        {
          "author_group_id": "ag_1a9c376cb170271322ce",
          "discourse_keys": [],
          "evidence_id": "e_c2da9886bb19c25986428198",
          "excerpt": "@Juice_Is_Loose1 @Mets2026 He’s 18th all time in WAR for SS and he’s 32. He’ll almost certainly be top 10 by the time he retires ahead of guys like Ozzie Smith, Robin Yount, and Ernie Banks",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_2a51c5124604a82bd1ba",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_31729f973eaed694eb58"
        },
        {
          "author_group_id": "ag_4e549d0c65392de97f56",
          "discourse_keys": [],
          "evidence_id": "e_84015caa4e9d40bcec093125",
          "excerpt": "Actual Outcome: Blue Jays 4, Padres 5 (Final) HR: Ernie Clement, Nathan Lukes",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_76781b60d394850a73d5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a754ba4b3a329a5d1b51"
        },
        {
          "author_group_id": "ag_3e158318e37dcf71c69c",
          "discourse_keys": [],
          "evidence_id": "e_307f7181b5d839f437cf26f0",
          "excerpt": "@q1043ootb @jcontheair @itspetergabriel @U2 @Dogstarband_CEO @TheOfficialA7X @GoodCharlotte @UBSArena appreciative Thank You and respect for You..Jonathan excellent Jonathan excellent sunday night show and always rockin best tunes ever created rockin on Q104.3 for please many many more years!! appreciatively.. Thank You from ernie caplanson",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_170c5e9131fdb85c3088",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_9374c5c9a25356686d25"
        },
        {
          "author_group_id": "ag_b1cc47af1fab425ad70c",
          "discourse_keys": [],
          "evidence_id": "e_ad9ab3ce95f68f5dd8c01132",
          "excerpt": "Life is pretty simple for me. I play, nap, eat (slowly but surely) and I love treats. Oh and I love pets &amp; cuddles too! -Ernie Day 12 #NationalSimplicityDay #PostAFavPic4VioletJul26 https://t.co/mY52Kmj6Wl",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a5e26ce8095a867ac745",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_53757987971e1ab2e422"
        },
        {
          "author_group_id": "ag_e3f9df8659d983b16522",
          "discourse_keys": [],
          "evidence_id": "e_16dc68ece6fb8b12fe5e33d5",
          "excerpt": "@MitchBannon E is for Ernie. Can't play D.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_70726585bbb49cc64c6f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_297cc8aa1517bda24706"
        },
        {
          "author_group_id": "ag_e23f57eee179d5f69141",
          "discourse_keys": [],
          "evidence_id": "e_8438d25d8d06260a95a6cdba",
          "excerpt": "Negatives from the 2026 First Half for the Jays - We’re in last place - Vladdy is washed - Gausman is old - Varsho is bald - George Springer is old and bald - Bieber got replaced by Justin - Kirk is a pumpkin - Barger has died 15 times - Jeff Hoffman - Ernie forgot how to play D",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_374bfab2a276eeb5e318",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_a41a4326194616a75a5d"
        },
        {
          "author_group_id": "ag_537661d1409b96002bc7",
          "discourse_keys": [],
          "evidence_id": "e_01782ab223c628987c76113e",
          "excerpt": "🔥 Y LOS SIN TECHO: • SiliconFlow → 10 modelos gratis • https://t.co/HvwKQ5m1Ti / Zhipu → GLM-4-Flash • Kilo Code → 7 rotativos • OpenCode Zen → 6 coding • Tencent → Hunyuan Lite • Baidu → ERNIE Speed/Lite Tope de rate, no de tokens. Úsalo sin miedo.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_c6914e35d9ca34e9c837",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7f4744fa863e36e16942"
        },
        {
          "author_group_id": "ag_e23f57eee179d5f69141",
          "discourse_keys": [],
          "evidence_id": "e_d92be8819511955f5a5e3c90",
          "excerpt": "- Ernie lowkey can’t play defence - remember when we thought we’d start the season like 7-2 and then we went like 4-5 lmaooooooooooo - The entire AL is a joke this year should’ve been a breeze and we’re still beyond terrible - Seriously why is our offence so bad",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0af6085eb2b4f881fea7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_2a71fe031da70d8806ee"
        },
        {
          "author_group_id": "ag_aab293be5ea73e876fcc",
          "discourse_keys": [],
          "evidence_id": "e_3c24e1a804504ebf5633ad4f",
          "excerpt": "Doubles 1. Otto Lopez (MIA) - 26 2. Rafael Devers (SF) - 25 3. Matt Olson (ATL) - 24 T-4. Alec Burleson (STL), Ernie Clement (TOR), Freddie Freeman (LAD), Nico Hoerner (CHC), Troy Johnston (COL), Josh Jung (TEX), Brice Turang (MIL), James Wood (WAS) - 23 https://t.co/ZWbqEmVHa7",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_8afea04d1ffaf1b94b17",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_10234303c2046d685b7a"
        },
        {
          "author_group_id": "ag_11fcb634afd3c7333816",
          "discourse_keys": [],
          "evidence_id": "e_b4702baaa3f1374e6790b970",
          "excerpt": "@raiderslove1234 @MarkAbr61812810 Hey Ernie. Good evening.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_9a3c86749bc35eeedd4d",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_12a5421ed3b079e136d6"
        },
        {
          "author_group_id": "ag_a5dd8a06c4edcb643e5a",
          "discourse_keys": [],
          "evidence_id": "e_150d09b81b66afa942e20e87",
          "excerpt": "Ernie Tedeschi proposed drafting plans for a land-value tax and a credit-invoice VAT, pointing to alternative fiscal tools. The idea was framed through fantasy-government roles, but reflects a broader policy focus shaped by his macro analysis.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_7b75f2d62e0a59840ba5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_0bb7b4fda9abdb05bd4e"
        },
        {
          "author_group_id": "ag_7bb2d29c077c124d4a43",
          "discourse_keys": [],
          "evidence_id": "e_3f8a22e4ee1c8186f7d6f9ee",
          "excerpt": "This is one of the most disgusting statements that I have heard from the Liar. Australia is our country, we don't need any welcome, in particular a welcome to country made up by Ernie Dingo! #Auspol2026",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ac5ec2d3433007502764",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_f2bb012aada2d0c53bb8"
        },
        {
          "author_group_id": "ag_e98de79edc29d17a82f6",
          "discourse_keys": [],
          "evidence_id": "e_9027d269b685f52f55aad5a5",
          "excerpt": "@WonderWilbur That's very simple but pawfect Ernie 😍",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_a9b92601c603f681efe5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_957632563b2eaefb8eba"
        },
        {
          "author_group_id": "ag_2e0bb4f0d935b11a6f3f",
          "discourse_keys": [],
          "evidence_id": "e_2dea8eb79fbe60de87e8b136",
          "excerpt": "@ErnestJugend @53gaDr3amca5t Ernie Im not the one who thinks declarations of war are inconsequential &amp; that war is vibes",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_accfa34e25c64da5c7a2",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c30c13a41dc51d9bc760"
        },
        {
          "author_group_id": "ag_35e61a5ac5f06505f7d2",
          "discourse_keys": [],
          "evidence_id": "e_6966369f9ae9ac56b057c881",
          "excerpt": "💣 BANG! 3-Leg HR 💰🔥 ✅ Sam Antonacci HR (+750) ✅ Jake McCarthy HR (+1060) ✅ Ernie Clement HR (+800) +88640 ODDS 🚀 ➡️ Need a win? ➡️ Click The Link Below To Get Daily Secured Guaranteed Winning Picks ⬇️⬇️💯 https://t.co/coS0BxXlSa #MLB #fanduel #GamblingX @Playbook https://t.co/2h0IK9B1Te",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_5b540a1a7c2a83f58dba",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_63f152784079c3858fc7"
        },
        {
          "author_group_id": "ag_d29796c468f2478dbc5a",
          "discourse_keys": [],
          "evidence_id": "e_c289cf4f164834d55c9af06a",
          "excerpt": "@meligamble You have a huge influence. Please tell more people about the strengths of this project. On BSC, $BIBI became a leading AI agent. On Robinhood Chain, I believe $ERNIE can become the equivalent. It's still early, and more people should know about its potential.",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_86c217d51a570c769eb6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_2b667e709b354b080b01"
        },
        {
          "author_group_id": "ag_d29796c468f2478dbc5a",
          "discourse_keys": [],
          "evidence_id": "e_26f5b989626a9eb7ee734238",
          "excerpt": "🚀 $ERNIE looks undervalued. Like $BIBI on BNB Chain, $ERNIE could become a key AI community token on Robinhood Chain. ✅ ~$40K Market Cap ✅ DEX Paid ✅ No obvious scam wallets I'm accumulating here. DYOR. $ERNIE #RobinhoodChain #Crypto https://t.co/zL6xHDvpsV",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_0a6009ebf3900d046e52",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7a2a22d41dc542e80775"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "lead",
        "available_independent_source_count": 28,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 34,
        "selected_count": 28,
        "story_rank": 1,
        "target_count": 28
      },
      "evidence_support": {
        "distinct_author_group_count": 23,
        "distinct_source_cluster_count": 28,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.186047",
              "market_relative_change_pp": "-0.186047",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "20.588235",
              "key": "none",
              "market_change_pp": "6.372093",
              "market_relative_change_pp": "14.216142",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 7,
              "selected_prevalence": "0.205882"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.186047",
              "market_relative_change_pp": "-0.186047",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.205882",
          "selected_covered_count": 7
        },
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "absurdist_meme",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "20.588235",
              "key": "advertising-marketing",
              "market_change_pp": "2.744186",
              "market_relative_change_pp": "17.844049",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 7,
              "selected_prevalence": "0.205882"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "ai_slop_critique",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "cope",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "dunk_yingyang",
              "market_change_pp": "0.465116",
              "market_relative_change_pp": "-0.465116",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "fud",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "genuine_hype",
              "market_change_pp": "3.441860",
              "market_relative_change_pp": "-3.441860",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "sarcasm",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "self_deprecation",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.205882",
          "selected_covered_count": 7
        },
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "20.588235",
              "key": "advertising_marketing",
              "market_change_pp": "2.279070",
              "market_relative_change_pp": "18.309166",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 7,
              "selected_prevalence": "0.205882"
            },
            {
              "brand_change_pp": "2.941176",
              "key": "buzz_releases",
              "market_change_pp": "2.372093",
              "market_relative_change_pp": "0.569083",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 1,
              "selected_prevalence": "0.029412"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "0.232558",
              "market_relative_change_pp": "-0.232558",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "feedback_questions",
              "market_change_pp": "1.255814",
              "market_relative_change_pp": "-1.255814",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "hands_on_usage",
              "market_change_pp": "2.651163",
              "market_relative_change_pp": "-2.651163",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "performance_comparisons",
              "market_change_pp": "3.162791",
              "market_relative_change_pp": "-3.162791",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.235294",
          "selected_covered_count": 8
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.232558",
              "market_relative_change_pp": "-0.232558",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "negative",
              "market_change_pp": "1.255814",
              "market_relative_change_pp": "-1.255814",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "5.882353",
              "key": "neutral",
              "market_change_pp": "5.534884",
              "market_relative_change_pp": "0.347469",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 2,
              "selected_prevalence": "0.058824"
            },
            {
              "brand_change_pp": "17.647059",
              "key": "positive",
              "market_change_pp": "4.790698",
              "market_relative_change_pp": "12.856361",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 6,
              "selected_prevalence": "0.176471"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.235294",
          "selected_covered_count": 8
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.093023",
              "market_relative_change_pp": "-0.093023",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "20.588235",
              "key": "none",
              "market_change_pp": "6.697674",
              "market_relative_change_pp": "13.890561",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 7,
              "selected_prevalence": "0.205882"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 34,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.205882",
          "selected_covered_count": 7
        },
        "volume": {
          "change_pct": null,
          "comparison_state": "new_or_low_base",
          "prior_authors": 0,
          "prior_count": 0,
          "selected_authors": 23,
          "selected_count": 34
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            0,
            7,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            100,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "none": {
              "counts": [
                0,
                0,
                7,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "1.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "discourse": {
          "coverage_counts": [
            0,
            0,
            7,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            100,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising-marketing": {
              "counts": [
                0,
                0,
                7,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "1.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "post_type": {
          "coverage_counts": [
            0,
            1,
            7,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            11,
            100,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising_marketing": {
              "counts": [
                0,
                0,
                7,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "1.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "buzz_releases": {
              "counts": [
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.111111",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "sentiment": {
          "coverage_counts": [
            0,
            1,
            7,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            11,
            100,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "neutral": {
              "counts": [
                0,
                1,
                1,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.111111",
                "0.142857",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "positive": {
              "counts": [
                0,
                0,
                6,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "0.857143",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            0,
            7,
            0,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            0,
            100,
            0,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "none": {
              "counts": [
                0,
                0,
                7,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.000000",
                "1.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [],
      "signals": [
        {
          "family": "post_type",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "discourse",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "sentiment",
          "rank": 1,
          "stream_position": 1
        },
        {
          "family": "nationalism",
          "rank": 1,
          "stream_position": 1
        }
      ],
      "start_at": "2026-07-13T00:00:00Z"
    },
    {
      "brand_key": "glm",
      "candidate_id": "glm:full_window",
      "coarse_series": {
        "author_counts": [
          34,
          52,
          45,
          58,
          60,
          72,
          61,
          46
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            35,
            58,
            49,
            65,
            66,
            82,
            66,
            63
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                35,
                58,
                49,
                65,
                66,
                82,
                66,
                63
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          35,
          58,
          49,
          65,
          66,
          82,
          66,
          63
        ]
      },
      "display_name_en": "Zhipu GLM",
      "display_name_zh_cn": "Zhipu GLM",
      "end_at": "2026-07-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_7f71ef8ab0728322952a",
          "discourse_keys": [],
          "evidence_id": "e_65430edea2a129207de224b0",
          "excerpt": "I handed @ChatGPTapp -5.6 Sol (High) a 2015 theoretical physics paper by @AnthropicAI cofoudner Sam McClandish and a hostile spec: existing Next.js repo, strict TypeScript, Tailwind v4, @Cloudflare edge, no WebGL, no React Three Fiber. It shipped an interactive kinematic-space explainer. Zero-shot. What that run reveals 🧵 https://t.co/HncdM3agvG The paradox: @claudeai Fable 5 leads SWE-Bench Pro 80.3% to Sol’s 64.6% — a 15-point rout. Yet Sol built the whole artifact effortlessly. SWE-Bench grades forensic remediation of legacy code. This graded zero-to-one construction. Different sports, one scoreboard. Where Sol actually dominates: 88.8% on Terminal-Bench 2.1 (91.9% in Ultra mode), 53.6 on Agents’ Last Exam. And frugality — 15,954 output tokens per SWE-Bench task vs 67,020 for Claude Opus 4.8. It plans succinctly and executes. No expensive internal monologue. The Pareto math of “high”: stepping down from xhigh costs 2 points of DeepSWE pass rate (71%→69%) and returns 26% of cost and ",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_6e1fe34d9309eba622f7",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_53744eb244802e797656"
        },
        {
          "author_group_id": "ag_abb6b9a7d84604d664fa",
          "discourse_keys": [],
          "evidence_id": "e_793d6dc271dd7c155ffe6a4a",
          "excerpt": "这个月项目团队把 Cursor Team 账号全部停用了。 看了下账单，差不多花了 9 万美元。接下来准备全部切到 API Key 模式，每个人分配固定额度，成本终于能控住一点。 我也特意申请了智谱 GLM-5.2 来试，实际体验下来，感觉并没有海外开发者吹得那么神。每天还要抢购额度，这点我确实有点不能理解…… 另外，Harness 这个方向倒是值得好好研究一下。",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_768d05c8c333ab918122",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_0d8dc22309821ac36036"
        },
        {
          "author_group_id": "ag_2298054b32cda33317ed",
          "discourse_keys": [
            "genuine_hype"
          ],
          "evidence_id": "e_e8715061e2368bc0ce420965",
          "excerpt": "@thetruetelmo @GavMcCracken You've heard correctly, Z GLM 5.2 is Opus 4.8 / GPT-5.5 tier opensource. Once it can be hosted on Mac Studio tier consumer hardware, then I will be moving most of my token spend for slow async work to it, and cut my coding plan down significantly.",
          "post_type_keys": [
            "performance_comparisons"
          ],
          "roles": [
            "dominant_discourse_representative",
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_571245c58f8d1ff5b07c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_82763f917551d9dd2988"
        },
        {
          "author_group_id": "ag_7af0ea9bb410ddf7484b",
          "discourse_keys": [],
          "evidence_id": "e_da2d12de20856ae4b10dba47",
          "excerpt": "🚨 NEW MODEL ALERT Singapore just dropped a model that's putting up frontier-level numbers. Agnes 2.5 Pro: • 82.7 on SWE-bench Verified • 78.7 multilingual • Strong gains on SWE Atlas • Beating GLM 5.2 and DeepSeek V4 Pro on multiple cuts • Free API available today The biggest takeaway isn't the benchmark here. It's the country. NOW frontier is no longer just a US vs China story.",
          "post_type_keys": [
            "performance_comparisons"
          ],
          "roles": [
            "contrasting_reaction",
            "supporting_context"
          ],
          "sentiment_keys": [
            "negative"
          ],
          "source_cluster_id": "sc_text_96823d448064c677bc7a",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_137509f277f2af641de6"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "floor",
        "available_independent_source_count": 123,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 127,
        "selected_count": 4,
        "story_rank": 5,
        "target_count": 4
      },
      "evidence_support": {
        "distinct_author_group_count": 4,
        "distinct_source_cluster_count": 4,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "volume": {
          "change_pct": "2925.000000",
          "comparison_state": "available",
          "prior_authors": 16,
          "prior_count": 16,
          "selected_authors": 388,
          "selected_count": 484
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "glm:full_window",
          "direction": "increase",
          "display_en": "2925%",
          "display_zh_cn": "2925%",
          "fact_id": "qf_85dd698bfb0fcc8bc05ac883",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "2925.000000",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "volume",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-07-13T00:00:00Z"
    },
    {
      "brand_key": "yi",
      "candidate_id": "yi:full_window",
      "coarse_series": {
        "author_counts": [
          13,
          12,
          2,
          6,
          3,
          3,
          0,
          1
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            13,
            12,
            2,
            6,
            3,
            3,
            0,
            1
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                13,
                12,
                2,
                6,
                3,
                3,
                0,
                1
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          13,
          12,
          2,
          6,
          3,
          3,
          0,
          1
        ]
      },
      "display_name_en": "01.AI Yi",
      "display_name_zh_cn": "零一万物",
      "end_at": "2026-07-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_d36ed59af6b14f30e0c1",
          "discourse_keys": [],
          "evidence_id": "e_d92cf3d7c050ad8e0c8733a9",
          "excerpt": "Just in: Morning News Mei Yi Weekend Escalation! Strait passage is a mystery; Samsung Longren Chip Factory is put into production ahead of schedule, SK Hynix CEO: storage is still in short supply in 2030; Zhaoyi Innovation Hong Kong Stock is unblocked today. Summary: The conflict between the United States and Iran escalated over the weekend! Strait passage is a mystery; Samsung Yongin chip factory is put into production ahead of schedule, SK Hynix CEO: Storage will still be in short supply in 2030; GigaDevice Hong Kong stocks are the cornerstone of the ban today. European and American stock markets: The S&P 500 rose 0.42% to 7575.39 points, with a cumulative gain of 1.23% for the week; the Dow closed up 0.29%, at 52637.01 points, with a cumulative decline of 0.50% for the week; the Nasdaq closed up 0.29%, at 26281.607 points, with a cumulative gain of 1.74% for the week. The European STOXX 600 Index rose 0.04% to 641.10 points, falling 1.79% for the whole week. A shares: The Shanghai C",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_ddbf8a21a601e5f35090",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_1976a67aee7b4ba19afd"
        },
        {
          "author_group_id": "ag_c2ecd1b0ec90660a33b9",
          "discourse_keys": [],
          "evidence_id": "e_d323db767a595039bfb078a1",
          "excerpt": "I love playing PG Master Yi, I have been a player of the deck since before the game's original release. I am proud to have gotten the deck to its dominant BDIF status, being most-played and 60% WR at high-tier events. It is time to put it aside for now, time to play Shen. 🥲🥲",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_fc8f259e22a8d108a678",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_9fb40e3a15c661dfa0a3"
        },
        {
          "author_group_id": "ag_bfaae93d4e9f12880627",
          "discourse_keys": [
            "genuine_hype"
          ],
          "evidence_id": "e_648d076cadd90edfacce3e3f",
          "excerpt": "🥺🥺 I think I'm melting cuz of him. When Xiao Yi chants 'eeny, meeny, miny, moe', it's so adorable 😙 https://t.co/d1EcaPcqp2",
          "post_type_keys": [
            "hands_on_usage"
          ],
          "roles": [
            "dominant_discourse_representative",
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_b8164f2e9c16e6870202",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_9cb98c914964290d5572"
        },
        {
          "author_group_id": "ag_eb9f043bc77c267f7308",
          "discourse_keys": [
            "dunk_yingyang"
          ],
          "evidence_id": "e_c9b18bf02c376b8645b06f75",
          "excerpt": "❗️🇨🇳 Mega-embassy judicial review hearings tomorrow and Wednesday. Here's what to expect: 1⃣ It would be fairly normal to lose at this stage (administrative court), and then to appeal. A case of this significance naturally points towards to the higher courts. However: 2⃣ The case for the claimants (Royal Mint Court Residents Association @StopTheEmbassy) is strong, and the judge, Lady Justice Lieven, has a reputation for robustly defending the rule of law. 3⃣ Everything is arguable in the law, and nobody should be over-confident in litigation. We don't know which way this is going to go, but we are hopeful. 4⃣ We also don't know when to expect the judgment. Could be a while. The judiciary recess may delay it. 5⃣ The grounds have been set out in some detail in the press, but our ground 1, which addresses enforceability, is a real problem for the government. See the 📸 below, which is a transcription of the letter Boris Johnson sent to Wang Yi in 2018, which, by the way, the UK government ",
          "post_type_keys": [
            "buzz_releases"
          ],
          "roles": [
            "contrasting_reaction",
            "supporting_context"
          ],
          "sentiment_keys": [
            "negative"
          ],
          "source_cluster_id": "sc_text_cd5171284c427ac1922c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_b9d2a5e8e0d9e660195c"
        },
        {
          "author_group_id": "ag_0232cebbc199ecbd1dd3",
          "discourse_keys": [],
          "evidence_id": "e_1765591584cc8e9da08e82c5",
          "excerpt": "Massage in riyadh jeddah buraydah al khaj 🏒🛶 https://t.co/vxOEfz5YXU jubail khobar hofuf dammam khamis abha medina tabuk massage at home riyadh,jeddah 🐛🧁 yi https://t.co/g0hgqfr5UK",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_dd60852e3602a1fe73b3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_864aaf74fdce67a21cfb"
        },
        {
          "author_group_id": "ag_41f49c7a3e598341cfa2",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_94652fdaf981cc1e3f3349f9",
          "excerpt": "Massage in riyadh jeddah buraydah al khaj 🪕🧉 https://t.co/hFlJH0aHwp jubail khobar hofuf dammam khamis abha medina tabuk massage at home riyadh,jeddah 🏏🥩 yI https://t.co/BVQU1PjiJv",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_b797f8015e3e2d5d058f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_864aaf74fdce67a21cfb"
        },
        {
          "author_group_id": "ag_d46dc0006cfc87f7e48d",
          "discourse_keys": [],
          "evidence_id": "e_21209f9f7f21c1ac4add38bf",
          "excerpt": "Massage in riyadh jeddah buraydah al khaj 🪗🛰️ https://t.co/JkJivVly4U jubail khobar hofuf dammam khamis abha medina tabuk massage at home riyadh,jeddah 🦉🍸 yi https://t.co/q808Hv4mqm",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_95d2e89afd0ad311f989",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_864aaf74fdce67a21cfb"
        },
        {
          "author_group_id": "ag_7328d2920d1e866abbae",
          "discourse_keys": [],
          "evidence_id": "e_1d198b82159bb2af297b37ae",
          "excerpt": "yes it is fractal. the whole model of the astronomical system given by Plato in a process of reverse engineering \"what the artificer had done\" shows it is a fractalising system. The topology of the way light gyrates on the surface on the planet, shows the formative image of the analemma - moebius function twist 180 degrees, as a projection of the orbtial path, due to the planets tilted axis. It is this that informs the structure of ALL COSMOLOGICAL MODELS from plato to ptolemy influenced by Vitruvius who gives the primary model used in Ptolemies Analemma, to Copernicus, Bruno and Moebius Klein and Sophus lie....... all employed the one and same model that has informed both the ultrastructural project of crystallopgraphy and harmonic studies in em. The model of the analemma, is based on the noontime points of the longest and shortest days of the year. This is a two circle/sphere model that informs the paths of the ecliptic. from the ruling of this structure, all platonic shapes and form",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_d6d9da79af4d66fdfaa6",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_785569b3f5dd1f2ef70b"
        },
        {
          "author_group_id": "ag_8e818c599676648e42c4",
          "discourse_keys": [],
          "evidence_id": "e_9e818b0f6de37c18b2027adf",
          "excerpt": "Huggingface #1 Paper of the Week: 2026-07-05..2026-07-11 The Mirage of Optimizing Training Policies: Monotonic Inference Policies as the Real Objective for LLM Reinforcement Learning Authors: Jing Liang, Hongyao Tang, Yi Ma, Yancheng He, Weixun Wang, Xiaoyang Li, Ju Huang, Wenbo Su, Jinyi Liu, Yan Zheng, Jianye Hao, Bo Zheng",
          "post_type_keys": [
            "buzz_releases"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_688fff7963b4c8790012",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c507944ed5743b92b622"
        },
        {
          "author_group_id": "ag_374f01ab3ff56b2ca992",
          "discourse_keys": [],
          "evidence_id": "e_14a2494a78424a9e02323da5",
          "excerpt": "Here’s a clean, copyable list of major Chinese AI models (LLMs and notable systems): • Qwen (Alibaba) – Qwen2, Qwen2.5, Qwen-Max • DeepSeek – DeepSeek-V2, DeepSeek-V3, DeepSeek-R1 • ERNIE (Baidu) – ERNIE 4.0, ERNIE-Speed • GLM (Zhipu AI) – GLM-4, GLM-4V, ChatGLM • Yi (https://t.co/4TEdd86hyN) – Yi-1.5, Yi-Large • Doubao (ByteDance) – Doubao-Pro, Doubao-1.5-Pro • Kimi (Moonshot AI) • Hunyuan (Tencent) – Hunyuan-Pro • Aquila (BAAI) • InternLM (Shanghai AI Lab) • TeleChat (China Telecom) • Spark (iFlyTek) • Baichuan (Baichuan Intelligence) – Baichuan2, Baichuan3 • SenseChat (SenseTime) • Yang (Alibaba, older series)",
          "post_type_keys": [
            "buzz_releases"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_e7911bd0d6071d4cad98",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_4c1290f40fc42a5e33aa"
        },
        {
          "author_group_id": "ag_644abc46c2953858eafe",
          "discourse_keys": [],
          "evidence_id": "e_3afbbd23a3763c5e0e05e2cb",
          "excerpt": "Güne Başlarken Bilinmesi Gerekenler Güney Kore'nin KOSPI endeksi düşüşünü %7'ye genişletti; SK Hynix ise %12'den fazla geriledi. Zincirüstü analist Ai Yi, X platformunda SK Hynix hissesinin %9,6'dan fazla düştüğünü ve \"ABD hisselerinde uzun ve kısa pozisyonlardan $5.293 milyonu aşan kâr elde eden akıllı para\"nın kârlarını geri vermeye başladığını duyurdu. CZ, popüler $Meme coin'leri BSC'de bir yakım adresine gönderdi\" konusundaki topluluğun hararetli tartışmasına yanıt olarak, \"O kadar da derin değil. O cüzdana uzun zamandır bakmıyordum ve açtığımda çok fazla token (on binlerce) olduğunu gördüm ve yazılımın gösterimi biraz dostça değildi. Token Pocket Baş İşletme Müdürü Michael, Robinhood kurucusu Vlad Tenev’in mnemonic ifadesinin canlı yayın sırasında sızdırıldığını twitlemiştir. Adresin kontrolü ele geçirildikten sonra saldırganlar bu adresi ve ilişkili adresleri kullanarak büyük miktarda $Meme token 1 satın almış, binlerce yatırımcıyı çekmiş ve token’ın piyasa değerini kısa bir süre",
          "post_type_keys": [
            "feedback_questions",
            "hands_on_usage"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_5affffcee781e0d155dc",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_713ce6f231a249098176"
        },
        {
          "author_group_id": "ag_afe473561bacd77fe49a",
          "discourse_keys": [
            "genuine_hype"
          ],
          "evidence_id": "e_8ecf0768ddc257d741848076",
          "excerpt": "In the 'My Bias, My Boss' script-reading video, Yuna read her lines from the ep. 2 script book, so yayyy!!! Looks like we’ll get to meet Yoon Cho-Yi in the very first week of the drama’s release ✨ #YUNA #MyBiasMyBoss #최애의사원 https://t.co/uzBQ4BZg5q",
          "post_type_keys": [
            "hands_on_usage"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_db1ca3fadacd4f5b9ba5",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_be7626c53d696549cb39"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 40,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 40,
        "selected_count": 12,
        "story_rank": 2,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "post_type": {
          "labels": [
            {
              "brand_change_pp": "2.500000",
              "key": "advertising_marketing",
              "market_change_pp": "2.279070",
              "market_relative_change_pp": "0.220930",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 1,
              "selected_prevalence": "0.025000"
            },
            {
              "brand_change_pp": "10.000000",
              "key": "buzz_releases",
              "market_change_pp": "2.372093",
              "market_relative_change_pp": "7.627907",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 4,
              "selected_prevalence": "0.100000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "event_announcement",
              "market_change_pp": "0.232558",
              "market_relative_change_pp": "-0.232558",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "5.000000",
              "key": "feedback_questions",
              "market_change_pp": "1.255814",
              "market_relative_change_pp": "3.744186",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 2,
              "selected_prevalence": "0.050000"
            },
            {
              "brand_change_pp": "12.500000",
              "key": "hands_on_usage",
              "market_change_pp": "2.651163",
              "market_relative_change_pp": "9.848837",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 5,
              "selected_prevalence": "0.125000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "performance_comparisons",
              "market_change_pp": "3.162791",
              "market_relative_change_pp": "-3.162791",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.275000",
          "selected_covered_count": 11
        },
        "sentiment": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.232558",
              "market_relative_change_pp": "-0.232558",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "5.000000",
              "key": "negative",
              "market_change_pp": "1.255814",
              "market_relative_change_pp": "3.744186",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 2,
              "selected_prevalence": "0.050000"
            },
            {
              "brand_change_pp": "17.500000",
              "key": "neutral",
              "market_change_pp": "5.534884",
              "market_relative_change_pp": "11.965116",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 7,
              "selected_prevalence": "0.175000"
            },
            {
              "brand_change_pp": "5.000000",
              "key": "positive",
              "market_change_pp": "4.790698",
              "market_relative_change_pp": "0.209302",
              "prior_basis_count": 0,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 40,
              "selected_count": 2,
              "selected_prevalence": "0.050000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.275000",
          "selected_covered_count": 11
        },
        "volume": {
          "change_pct": null,
          "comparison_state": "new_or_low_base",
          "prior_authors": 0,
          "prior_count": 0,
          "selected_authors": 40,
          "selected_count": 40
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "post_type": {
          "coverage_counts": [
            3,
            3,
            1,
            4,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            23,
            25,
            50,
            67,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising_marketing": {
              "counts": [
                1,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.076923",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "buzz_releases": {
              "counts": [
                0,
                1,
                0,
                3,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.083333",
                "0.000000",
                "0.500000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "feedback_questions": {
              "counts": [
                1,
                0,
                1,
                0,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.076923",
                "0.000000",
                "0.500000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "hands_on_usage": {
              "counts": [
                1,
                2,
                1,
                1,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.076923",
                "0.166667",
                "0.500000",
                "0.166667",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "sentiment": {
          "coverage_counts": [
            3,
            3,
            1,
            4,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            23,
            25,
            50,
            67,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "negative": {
              "counts": [
                1,
                0,
                0,
                1,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.076923",
                "0.000000",
                "0.000000",
                "0.166667",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "neutral": {
              "counts": [
                2,
                2,
                1,
                2,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.153846",
                "0.166667",
                "0.500000",
                "0.333333",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "positive": {
              "counts": [
                0,
                1,
                0,
                1,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.083333",
                "0.000000",
                "0.166667",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [],
      "signals": [
        {
          "family": "post_type",
          "rank": 2,
          "stream_position": 2
        },
        {
          "family": "sentiment",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-07-13T00:00:00Z"
    },
    {
      "brand_key": "minimax",
      "candidate_id": "minimax:full_window",
      "coarse_series": {
        "author_counts": [
          8,
          20,
          15,
          15,
          18,
          17,
          21,
          5
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            8,
            22,
            16,
            19,
            21,
            24,
            24,
            6
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                8,
                22,
                16,
                19,
                21,
                24,
                24,
                6
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          8,
          22,
          16,
          19,
          21,
          24,
          24,
          6
        ]
      },
      "display_name_en": "MiniMax AI",
      "display_name_zh_cn": "MiniMax AI",
      "end_at": "2026-07-14T00:00:00Z",
      "episodes": [],
      "evidence": [
        {
          "author_group_id": "ag_be11b69ca04f1c7b3845",
          "discourse_keys": [],
          "evidence_id": "e_6d53e5249c7bbfb870d3bb54",
          "excerpt": "China Isn’t Just Building AI. It’s Building the Entire AI Economy. Most discussions about AI focus on who has the best model. China is playing a much bigger game. It’s building an end-to-end AI ecosystem where every layer reinforces the next: 🔹 AI Models – DeepSeek, Qwen, ERNIE, MiniMax, Kimi, Hunyuan and many others compete relentlessly, driving innovation and lowering costs. 🔹 Hyperscale Cloud Infrastructure – Alibaba Cloud, Tencent Cloud, Huawei Cloud, Baidu Cloud and Volcano Engine are investing billions in GPUs, data centres and AI infrastructure to power the next generation of applications. 🔹 Developer Platforms – APIs, orchestration layers and agent frameworks make it easier for businesses to build AI products without starting from scratch. 🔹 Enterprise Adoption – Companies deploy AI into customer service, software development, healthcare, finance, manufacturing and education, creating real business value. 🔹 The Flywheel – More users generate more data. More data improves models",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_995e6b5b4e965ffb74cf",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_899148c944640c9408e6"
        },
        {
          "author_group_id": "ag_ab6066a48fbb637a0f5d",
          "discourse_keys": [],
          "evidence_id": "e_cbb5d065971938468a24d26d",
          "excerpt": "为什么只用一个 AI？ 真正的效率，是让全球顶级模型为你所用。 https://t.co/feB1uBLwsI 汇聚全球领先 AI 生态，一站式接入顶尖大模型。 无论是代码开发、复杂推理、内容创作，还是 AI Agent 构建，都能根据不同场景自由切换最合适的模型。 全球顶级模型矩阵 GPT 系列（12 款） ✨ Claude 系列（9 款） Gemini 系列（3 款） 国产领先模型 • DeepSeek • GLM • Kimi • MiniMax •Qwen 从轻量级 Mini / Flash 到旗舰级 Pro / Opus，覆盖速度、性能与成本的不同需求，让每一次调用都更加高效。 在 https://t.co/feB1uBLwsI，模型不再是限制。 而是释放创造力、提升生产力、驱动 AI Agent 协作的核心动力。 未来属于会使用 AI 的人。 而未来的 AI，不止一个模型。 立即体验：https://t.co/n3sL38g6uW 个平台，汇聚全球智能。 @BAI_AGI @justinsuntron #TRONEcoStar",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_b0aeb2d3be9daec16cd0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_f9769c4bbaa4827701b4"
        },
        {
          "author_group_id": "ag_1b161bd9c782646f74f7",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_3297f02014e1fe5fafd54658",
          "excerpt": "10/ https://t.co/78WJXEDEeP doesn't just support Claude models. Through the same unified infrastructure, developers can access models from OpenAI, Google, DeepSeek, MiniMax, Moonshot, Zhipu AI, and more. One API. Multiple frontier AI models. That's the flexibility https://t.co/78WJXEDEeP brings to developers. Whether you choose settings.json or Environment Variables, the goal is the same: A faster, more flexible way to connect Claude Code to https://t.co/78WJXEDEeP's unified AI infrastructure. Once configured, you're free to build, experiment, and switch between leading AI models with minimal friction. Happy building! #LLM #AgenticAI",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "dominant_discourse_representative",
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_f97d4eaffc043443f46b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_c30fbd4f1c08bdec6e08"
        },
        {
          "author_group_id": "ag_44c7be77172ff8fce13b",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_078c4bac7d0b103f3b90024d",
          "excerpt": "Do not choose an AI model based only on benchmarks. Test it with your own prompts, data, and application workflow. Different models can perform differently across coding, writing, reasoning, summarization, translation, extraction, and automation tasks. OpenFrog makes model comparison easier by providing access to popular Chinese AI models through one relay gateway: DeepSeek V4 for development and reasoning tasks. GLM 5 for general AI applications. Kimi K2 for long-context and agent workflows. MiniMax M2.7 for efficient application development. Qwen 3.7 Max for a broad range of language tasks. With OpenFrog, developers get: • One API key • One unified relay endpoint • Stable access to supported models • Clear account usage and balance • Pricing up to 50% lower than official rates on selected models Register now and receive $1 in free testing credit automatically: https://t.co/moiOPqfJhd Need help getting started? Join us: Discord: https://t.co/1LcV7fIBLX Telegram: https://t.co/bHUtExIWN",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "contrasting_reaction",
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_fa81bb3790f1980598e1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_13fa627bebe0289222fe"
        },
        {
          "author_group_id": "ag_162c94dc908785069868",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_df8ae374b76c43daf9085424",
          "excerpt": "✅ Top AI LLM Models for Every Task Ask Gemini 3.1 Pro FREE now 👉 https://t.co/HhCHOdKkxU → Writing &amp; Research: Grok 4.3, GLM 5.1,GPT-5.5, Claude 4.6, Gemini 3.1 Pro, Perplexity → Social Content: Grok 4, GPT o3, DeepSeek → Academic / STEM: Claude Opus 4.7, MiniMax M2.7 https://t.co/ujqhAG9m0E",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_c2da85f077e58be0c43c",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_077f87d54ebd35abd242"
        },
        {
          "author_group_id": "ag_faaea62d1115e2e67c62",
          "discourse_keys": [],
          "evidence_id": "e_c234d18b6e22db9348109f9f",
          "excerpt": "✅ Top AI LLM Models for Every Task Ask Gemini 3.1 Pro FREE now 👉 https://t.co/EMeQhwzqyB → Writing &amp; Research: Grok 4.3, GLM 5.1,GPT-5.5, Claude 4.6, Gemini 3.1 Pro, Perplexity → Social Content: Grok 4, GPT o3, DeepSeek → Academic / STEM: Claude Opus 4.7, MiniMax M2.7 https://t.co/TdoZmtfn8o",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_dfa11b7eb0d1326c68ba",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_077f87d54ebd35abd242"
        },
        {
          "author_group_id": "ag_4a34cea61b3f3dbf474e",
          "discourse_keys": [],
          "evidence_id": "e_cacb5dfc443c67653ec97c07",
          "excerpt": "MiniMax seeks $2.05B to build China's largest Al model https://t.co/LOjnjGuD9Y",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_65b973cc4bb1bf6a7518",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_7969c03068a572d8dae8"
        },
        {
          "author_group_id": "ag_3b05ebcc4f7edbf5b49e",
          "discourse_keys": [],
          "evidence_id": "e_88449da19b7f58f074f72c61",
          "excerpt": "Since we are all still talking about 5.6 - I'm fairly happy with the models (Luna, Terra, Sol) - I'm also happy with the many many options that people love to complain about - I'm a $20 Plus user, $20 Gemini User, $6 Twitter user, $0 GLM user (kindness of friend) They built it for my workflow Use 5.6 Medium in ChatGPT projects ↓ Use my Markdown Converter tool, which lets me bundle my elixir app as one txt file ↓ Upload the txt file and AGENTS md file to the project ↓ Ask the model for a detailed plan ↓ Take that detailed plan to any of my models depending on my mood ↓ Right now it's Luna Low as my executor I have other executor models -- I also use 3.5 Flash in Antigravity, -- Zai in OpenCode, -- I used Grok but the GitHub thing spooked me, -- When Meta comes I'll add it to my rotation, -- I have DeepSeek v4 as a backup -- I also have some Kimi credits from the World Cup -- If I ever wanted I can throw $10 to OpenCode Go and get more models I'm not building a compiler or something low ",
          "post_type_keys": [
            "hands_on_usage"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_b1754a3ec54a8034d6b0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_e64b27914d4261cc20d0"
        },
        {
          "author_group_id": "ag_19ae3d82d85eb6a18b6d",
          "discourse_keys": [],
          "evidence_id": "e_79e25ec1291a1a291455e24c",
          "excerpt": "@_jasonwei Performed well on my Debate Benchmark https://t.co/flB9L3RJxh",
          "post_type_keys": [],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_root_abd2ff8bf535aecb99cf",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_236e3963c2f68e7cc3fc"
        },
        {
          "author_group_id": "ag_2fa3d681f6a367d5dd22",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_4d443fe8894678fb69156168",
          "excerpt": "Can you tell? Is this a real vlog or AI? Just open MiniMax Hub choose the Promo Video Skill and upload your product image Agent auto-generates lifelike UGC ads It also generates multiple regional and language versions With quality and speed like this No seller should miss this https://t.co/I8UhI1Z9gs",
          "post_type_keys": [
            "advertising_marketing"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_92f483e52fe1902f0c2f",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_5269e1967e49c5d7f630"
        },
        {
          "author_group_id": "ag_d4e00491a51937c83d65",
          "discourse_keys": [
            "advertising-marketing"
          ],
          "evidence_id": "e_8ea800b864a82a4c3a5fcd7b",
          "excerpt": "𝗚𝗿𝗲𝗮𝘁 𝗘𝗰𝗼𝘀𝘆𝘀𝘁𝗲𝗺𝘀 𝗔𝗿𝗲𝗻’𝘁 𝗕𝘂𝗶𝗹𝘁 𝗜𝗻 𝗔 𝗗𝗮𝘆—𝗧𝗵𝗲𝘆’𝗿𝗲 𝗕𝘂𝗶𝗹𝘁 𝗘𝘃𝗲𝗿𝘆 𝗪𝗲𝗲𝗸. Innovation never stands still. Each milestone, integration, and ecosystem upgrade brings Web3 one step closer to a smarter, more connected future. The latest TRON Eco Weekly Recap highlights another week of meaningful progress—and @AINFTcom continues to play a key role in that momentum. 𝗔 𝘄𝗲𝗲𝗸 𝗼𝗳 𝗴𝗿𝗼𝘄𝘁𝗵 • 🤖 Expanded AI model support with GPT-5.5-Instant, DeepSeek-V3.2, MiniMax-M2.7, and GLM-5.1 across Web Chat and API. • 💳 Added more convenient payment options with WeChat Pay and Alipay top-ups. • 🌐 Continued strengthening AI accessibility for developers, creators, and businesses. • 🚀 Contributed to the rapid evolution of AI infrastructure across the TRON ecosystem. 𝗧𝗼𝗴𝗲𝘁𝗵𝗲𝗿, 𝘄𝗲’𝗿𝗲 𝗯𝘂𝗶𝗹𝗱𝗶𝗻𝗴 𝗺𝗼𝗿𝗲 𝘁𝗵𝗮𝗻 𝘁𝗲𝗰𝗵𝗻𝗼𝗹𝗼𝗴𝘆. From AI infrastructure and seamless payments to decentralized innovation, every advancement across the TRON ecosystem strengthens the foundation for the next generation of Web3. AINFT is proud to contribute to thi",
          "post_type_keys": [
            "buzz_releases"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "neutral"
          ],
          "source_cluster_id": "sc_text_9e6e1c58bb72613467b3",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_5a9f37fcaaba0ca732e5"
        },
        {
          "author_group_id": "ag_d62511e357cad88afe46",
          "discourse_keys": [
            "genuine_hype"
          ],
          "evidence_id": "e_4afa360c27d7bcfb551e2a1a",
          "excerpt": "MiniMax-M3 has been the most creative model I've used, compared to Claude, GPT, GLM and DeepSeek. Whenever I'm asking design questions, MiniMax gives me the best solutions.",
          "post_type_keys": [
            "hands_on_usage"
          ],
          "roles": [
            "supporting_context"
          ],
          "sentiment_keys": [
            "positive"
          ],
          "source_cluster_id": "sc_text_e8b8c9e05bc690fcb9e0",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_33e376e02664f816b34f"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "comparison",
        "available_independent_source_count": 70,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 77,
        "selected_count": 12,
        "story_rank": 3,
        "target_count": 12
      },
      "evidence_support": {
        "distinct_author_group_count": 12,
        "distinct_source_cluster_count": 12,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "china_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.186047",
              "market_relative_change_pp": "-0.186047",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "12.142857",
              "key": "none",
              "market_change_pp": "6.372093",
              "market_relative_change_pp": "5.770764",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 17,
              "selected_prevalence": "0.121429"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.186047",
              "market_relative_change_pp": "-0.186047",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.121429",
          "selected_covered_count": 17
        },
        "discourse": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "absurdist_meme",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "9.285714",
              "key": "advertising-marketing",
              "market_change_pp": "2.744186",
              "market_relative_change_pp": "6.541528",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 13,
              "selected_prevalence": "0.092857"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "ai_slop_critique",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "cope",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "distillation_accusation",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "dunk_yingyang",
              "market_change_pp": "0.465116",
              "market_relative_change_pp": "-0.465116",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "fud",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "2.857143",
              "key": "genuine_hype",
              "market_change_pp": "3.441860",
              "market_relative_change_pp": "-0.584718",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 4,
              "selected_prevalence": "0.028571"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "sarcasm",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "self_deprecation",
              "market_change_pp": "0.046512",
              "market_relative_change_pp": "-0.046512",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.121429",
          "selected_covered_count": 17
        },
        "us_nationalism": {
          "labels": [
            {
              "brand_change_pp": "0.000000",
              "key": "anti",
              "market_change_pp": "0.093023",
              "market_relative_change_pp": "-0.093023",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "constructive_critical",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mild_pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "mixed",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            },
            {
              "brand_change_pp": "12.142857",
              "key": "none",
              "market_change_pp": "6.697674",
              "market_relative_change_pp": "5.445183",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 17,
              "selected_prevalence": "0.121429"
            },
            {
              "brand_change_pp": "0.000000",
              "key": "pro",
              "market_change_pp": "0.000000",
              "market_relative_change_pp": "0.000000",
              "prior_basis_count": 1,
              "prior_count": 0,
              "prior_prevalence": "0.000000",
              "selected_basis_count": 140,
              "selected_count": 0,
              "selected_prevalence": "0.000000"
            }
          ],
          "prior_coverage_ratio": "0.000000",
          "prior_covered_count": 0,
          "selected_coverage_ratio": "0.121429",
          "selected_covered_count": 17
        },
        "volume": {
          "change_pct": "13900.000000",
          "comparison_state": "available",
          "prior_authors": 1,
          "prior_count": 1,
          "selected_authors": 110,
          "selected_count": 140
        }
      },
      "kind": "full_window",
      "metadata_trajectories": {
        "china_nationalism": {
          "coverage_counts": [
            0,
            6,
            1,
            10,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            27,
            6,
            53,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "none": {
              "counts": [
                0,
                6,
                1,
                10,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.272727",
                "0.062500",
                "0.526316",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "discourse": {
          "coverage_counts": [
            0,
            6,
            1,
            10,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            27,
            6,
            53,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "advertising-marketing": {
              "counts": [
                0,
                5,
                1,
                7,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.227273",
                "0.062500",
                "0.368421",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            },
            "genuine_hype": {
              "counts": [
                0,
                1,
                0,
                3,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.045455",
                "0.000000",
                "0.157895",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        },
        "us_nationalism": {
          "coverage_counts": [
            0,
            6,
            1,
            10,
            0,
            0,
            0,
            0
          ],
          "coverage_percent": [
            0,
            27,
            6,
            53,
            0,
            0,
            0,
            0
          ],
          "labels": {
            "none": {
              "counts": [
                0,
                6,
                1,
                10,
                0,
                0,
                0,
                0
              ],
              "prevalence": [
                "0.000000",
                "0.272727",
                "0.062500",
                "0.526316",
                "0.000000",
                "0.000000",
                "0.000000",
                "0.000000"
              ]
            }
          }
        }
      },
      "quantitative_facts": [
        {
          "candidate_id": "minimax:full_window",
          "direction": "increase",
          "display_en": "13900%",
          "display_zh_cn": "13900%",
          "fact_id": "qf_3a07aa2486e9105d311aba1e",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "13900.000000",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "family": "discourse",
          "rank": 2,
          "stream_position": 2
        },
        {
          "family": "nationalism",
          "rank": 2,
          "stream_position": 2
        }
      ],
      "start_at": "2026-07-13T00:00:00Z"
    },
    {
      "brand_key": "llama",
      "candidate_id": "llama:7-14",
      "coarse_series": {
        "author_counts": [
          215,
          113,
          10,
          16,
          28,
          24,
          20,
          19
        ],
        "engagement": {
          "concentrations": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "coverage_ratios": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000",
            "0.000000"
          ],
          "eligible_counts": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
          ],
          "intensities": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "interactions": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "likes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "missing_counts": [
            217,
            118,
            11,
            17,
            31,
            27,
            21,
            20
          ],
          "post_kinds": {
            "quote": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "repost": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ]
            },
            "source_post": {
              "eligible_counts": [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
              ],
              "interactions": [
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null
              ],
              "missing_counts": [
                217,
                118,
                11,
                17,
                31,
                27,
                21,
                20
              ]
            }
          },
          "quotes": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "replies": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ],
          "reposts": [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null
          ]
        },
        "post_counts": [
          217,
          118,
          11,
          17,
          31,
          27,
          21,
          20
        ]
      },
      "display_name_en": "Meta Llama",
      "display_name_zh_cn": "Meta Llama",
      "end_at": "2026-07-13T03:45:00Z",
      "episodes": [
        {
          "baseline_post_count": "2.000000",
          "end_at": "2026-07-13T03:45:00Z",
          "end_bucket_index": 14,
          "episode_id": "llama:7-14",
          "peak_author_count": 58,
          "peak_post_count": 58,
          "peak_to_baseline": "29.000000",
          "post_count": 315,
          "start_at": "2026-07-13T01:45:00Z",
          "start_bucket_index": 7
        }
      ],
      "evidence": [
        {
          "author_group_id": "ag_c7e564c157603164882a",
          "discourse_keys": [],
          "evidence_id": "e_c5c8f05781ff53930954c1a1",
          "excerpt": "El problema se llama Gambler’s Ruin y ha sido súper estudiado. NUNCA le vas a ganar al casino si apuestas indefinidamente, aunque la probabilidad de ganar sea 50/50, porque tu capital es limitado y sensible a fluctuaciones.",
          "post_type_keys": [],
          "roles": [
            "official_or_catalyst",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_285ae73742e4a995722b",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_fdca218352b03e36491a"
        },
        {
          "author_group_id": "ag_e557681c2c9c678c6806",
          "discourse_keys": [],
          "evidence_id": "e_788842df991885e804b20fad",
          "excerpt": "@robertomtzTV Ahora ya también eres experto pero en fútbol? Jajajaja No le llaman en el tercer gol de Argentina porque lo revisa el var y no ven necesario llamar al árbitro para que la vea. El var llama cuando ve algo raro y que el árbitro debería revisarlo. Para de mamar hijo",
          "post_type_keys": [],
          "roles": [
            "top_engaged_original",
            "supporting_context"
          ],
          "sentiment_keys": [],
          "source_cluster_id": "sc_text_f65a8b98e91a5ce164de",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_75ee5feb37facc73643f"
        },
        {
          "author_group_id": "ag_380edfa482f66299f389",
          "discourse_keys": [
            "dunk_yingyang"
          ],
          "evidence_id": "e_496f3ab39856c0a54b20c7c0",
          "excerpt": "ESO SE LLAMA ENVIDIA ACA EN ARGENTINA Y EN CUALQUIER PARTE DEL MUNDO.",
          "post_type_keys": [
            "hands_on_usage"
          ],
          "roles": [
            "dominant_discourse_representative",
            "supporting_context"
          ],
          "sentiment_keys": [
            "negative"
          ],
          "source_cluster_id": "sc_text_e342362149c03e5183cc",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_1265eed808d7bdee9098"
        },
        {
          "author_group_id": "ag_9ff64b0af72043dd66e3",
          "discourse_keys": [],
          "evidence_id": "e_c71e59bc4ce3726291be94ca",
          "excerpt": "#ServicioSocial SE BUSCA 🚨🚨 🚨 GATO PERDIDO – NUEVO LOURDES Se busca a Mocca, desaparecido posiblemente desde el jueves. Tiene 3 años, es café con blanco, con una mancha blanca en la espalda, y responde a su nombre. ⚠️ Tiene leucemia felina (FeLV), por lo que necesita regresar a casa lo antes posible. Si lo has visto o tienes información, por favor llama al: 📞 7163-9490 o 7146-8434 🙏 ¡Ayúdanos compartiendo! Cada publicación puede hacer la diferencia. ❤️",
          "post_type_keys": [
            "buzz_releases"
          ],
          "roles": [
            "contrasting_reaction",
            "supporting_context"
          ],
          "sentiment_keys": [
            "negative"
          ],
          "source_cluster_id": "sc_text_422c91705ed85a68bca1",
          "source_flags": {
            "metrics_observed": false,
            "occurrence_source": "original_post",
            "official": false,
            "post_kind": "source_post"
          },
          "theme_cluster_id": "th_6b19b12b3a35b980025b"
        }
      ],
      "evidence_allocation": {
        "allocation_class": "floor",
        "available_independent_source_count": 69,
        "packet_trimmed_count": 0,
        "policy_version": "adaptive-v1",
        "protected_floor_count": 4,
        "reservoir_count": 69,
        "selected_count": 4,
        "story_rank": 6,
        "target_count": 4
      },
      "evidence_support": {
        "distinct_author_group_count": 4,
        "distinct_source_cluster_count": 4,
        "event_claim_may_be_supported": true,
        "evidence_only_entity_may_be_supported": true,
        "official_source_count": 0
      },
      "family_facts": {
        "volume": {
          "change_pct": "9140.000000",
          "comparison_state": "available",
          "prior_authors": 5,
          "prior_count": 5,
          "selected_authors": 439,
          "selected_count": 462
        }
      },
      "kind": "episode",
      "metadata_trajectories": {},
      "quantitative_facts": [
        {
          "candidate_id": "llama:7-14",
          "direction": "increase",
          "display_en": "9140%",
          "display_zh_cn": "9140%",
          "fact_id": "qf_aec346a24ffe824f9b1b6142",
          "family": "volume",
          "label_key": "",
          "metric": "change_pct",
          "rounding": "nearest_tenth_below_one_else_whole",
          "source_value": "9140.000000",
          "unit": "percent"
        }
      ],
      "signals": [
        {
          "episode_rank": 1,
          "family": "volume",
          "rank": 3,
          "stream_position": 3
        }
      ],
      "start_at": "2026-07-13T01:45:00Z"
    }
  ],
  "comparison_allowed": true,
  "comparison_suppressed_reasons": [],
  "coverage": {
    "prior": {
      "earliest_at": "2025-01-15T09:47:50Z",
      "known_backlog_overlap": false,
      "ratio": "1.000000",
      "state": "sufficient"
    },
    "selected": {
      "earliest_at": "2025-01-15T09:47:50Z",
      "known_backlog_overlap": false,
      "ratio": "1.000000",
      "state": "sufficient"
    }
  },
  "evidence_policy": {
    "comparison_ceiling": 12,
    "excerpt_characters": 1000,
    "floor": 4,
    "lead_ceiling": 48,
    "provider_packet_bytes": 131072,
    "reservoir_rank_limit": 32,
    "version": "adaptive-v1"
  },
  "quantitative_fact_schema_version": 1,
  "series_axis": {
    "coarse": {
      "bucket_count": 8,
      "duration_seconds": 10800,
      "ends": [
        "2026-07-13T03:00:00Z",
        "2026-07-13T06:00:00Z",
        "2026-07-13T09:00:00Z",
        "2026-07-13T12:00:00Z",
        "2026-07-13T15:00:00Z",
        "2026-07-13T18:00:00Z",
        "2026-07-13T21:00:00Z",
        "2026-07-14T00:00:00Z"
      ],
      "starts": [
        "2026-07-13T00:00:00Z",
        "2026-07-13T03:00:00Z",
        "2026-07-13T06:00:00Z",
        "2026-07-13T09:00:00Z",
        "2026-07-13T12:00:00Z",
        "2026-07-13T15:00:00Z",
        "2026-07-13T18:00:00Z",
        "2026-07-13T21:00:00Z"
      ]
    }
  },
  "snapshot_schema_version": 1,
  "thresholds": {
    "episode_peak_ratio": "3.0",
    "max_episodes_per_candidate": 3,
    "min_authors": 10,
    "min_posts": 20,
    "minimum_coverage": "0.75"
  },
  "unresolved_backlog_intervals": [],
  "window_days": 1
}
~~~
