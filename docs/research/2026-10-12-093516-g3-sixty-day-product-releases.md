---
date: 2026-10-12
status: working-canonical-research-inventory
analysis_only: true
scope_companies: 12
product_classification: proposed-only
---

# Source-backed release list: twelve companies, past sixty days

This is the working canonical research list for the twelve companies selected by
the owner. It records release milestones for models, agents, harnesses and other
AI products, including community previews and quiet code/weight publication.
It is a research artifact; production has not imported it.

**Window:** 2026-08-13T00:35:16+00:00 through 2026-10-12T00:35:16+00:00. This is a rolling
sixty-day interval, approximately August 13–October 12, 2026. Today is incomplete.
Publisher dates without times retain day precision. The two August 13 entries
overlap the lower-boundary day and remain flagged; no exact launch time is invented.

**Inventory:** 159 dated entries: 53 model milestones and
106 agent/harness/other entries, including software version updates.
8 entries carry dated artifact revisions with historical
public-access time unproved. Pending evidence/ownership decisions remain separate.
The individual dates are source-backed; complete recall of every company release
has not been certified.

[JSON source list](2026-10-12-093516-g3-sixty-day-product-releases.json) · [CSV events](2026-10-12-093516-g3-sixty-day-product-releases.csv) ·
[G3 plan](../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md) ·
[Earlier family draft](../analysis/2026-10-12-091100-g3-tracked-brand-family-register.md)

**Date comparison follow-up, October 12:** [X announcements, first HF records and GitHub creation](2026-10-12-132932-g3-x-hf-github-release-dates.md) verifies these separate clocks for 19 HF repositories. It supplies earlier Qwen 27B preannouncement evidence, distinguishes initial metadata from weight files, and marks shared GitHub repositories. Existing artifact dates remain artifact dates; they must not be read as first public-weight availability. The frozen JSON/CSV and database reconciliation counts remain unchanged.

## What a row means

One row is one dated milestone, such as first named announcement, preview access,
API/region availability, public release-note publication, or a checkpoint/code
revision. One product can have several rows. Sibling model sizes/modes launched
together share a row with explicit variants. Preview and final availability,
anonymous debut and identity reveal, and code and weight delivery retain their
distinct dates.

An API reseller adding an existing model is an access milestone. It does not
reset the original model launch. A package, mirror, tokenizer or quantization
does not automatically create another model generation. A newly developed
fine-tune can be a real product; preserve both its developer and base model.

The JSON preserves a stable product/version group ID and an event ID, source
URL, date precision, evidence status, variants and collection observation where
available. Group IDs are analysis identities; binding to existing Product and
ModelRelease records remains later work.

## Shadow and quiet releases

GLM-5.3-Flash has two supported milestones: Ox Alpha community testing on
August 20, then the named launch/identity explanation on August 26. The publisher
explicitly identifies the anonymous tests on OpenRouter and OpenCode.
[OpenRouter listing](https://openrouter.ai/stealth/ox-alpha),
[Z.ai launch](https://z.ai/blog/glm-5.3-flash).

Space Bunny Alpha has a platform-confirmed September 23 public test date, but
its company identity remains unresolved in the primary platform evidence. It
is in the pending list rather than the twelve-company counts. Tokenizer
similarity and community theories are leads; they do not establish a canonical
MiniMax mapping. [Platform listing](https://openrouter.ai/stealth/space-bunny-alpha).

For a quiet checkpoint upload, inspect the actual revision contents. This pass
checked historical metadata trees containing 131 Qwen Flash Next weight files,
141 GLM5.3 files, 65 Ling Fin files, 16 Ming Design files and 20 Layer files.
No weights were downloaded. Their commit times establish artifact chronology;
repository creation, current publicity or a README update cannot prove precisely
when historical public access began.

For future prediction replay, keep what was known at the time separate from
what this October 12 review learned. An identity reveal can link past anonymous
testing retrospectively without granting that identity to an earlier forecast.

## Proposed product categories

All type labels below are proposals. Current Product.TYPES at the recorded G3
revision has llm-model, other-ai-model and the combined agent-harness option.
The requested five-way split is later implementation work. Do not write these
analysis labels directly into existing Product.type values.

| Proposed label | Meaning for this review |
| --- | --- |
| model-llm | Language/reasoning models, including language-based multimodal models. |
| model-other | Specialized image, video, speech, translation, planning or decision models. |
| agent | Products that carry out tasks through models and tools, including desktop/coding agents. |
| harness | Reusable execution, training, evaluation, safety or integration infrastructure. |
| other | AI platform/evaluation products that do not fit the preceding categories. |

Clinical VLMs, omnimodal speech models, driving VLMs, plugin suites and bundled
agent platforms need subtype review. A model trained for agent tasks remains a
model; the task-running product and its reusable runtime are separate entities.

## Company coverage

Every company was reviewed through a bounded set of publisher/platform sources.
Counts are events and version updates; they are not counts of new model families.

| Company alias | Company | Dated entries |
| --- | --- | --- |
| ds | [DeepSeek](#deepseek) | 3 |
| mm | [MiniMax](#minimax) | 3 |
| qwen | [Alibaba / Qwen](#qwen) | 69 |
| zai | [Z.ai / Zhipu](#glm) | 12 |
| mistral | [Mistral AI](#mistral) | 20 |
| kimi | [Moonshot AI / Kimi](#moonshot-kimi) | 19 |
| step | [StepFun](#stepfun) | 3 |
| inclusion | [Ant Group / inclusionAI](#inclusionai) | 14 |
| mimo | [Xiaomi / MiMo](#mimo) | 4 |
| hunyuan | [Tencent / Hunyuan](#hunyuan) | 4 |
| nemo | [NVIDIA / NeMo / Nemotron](#nemo-megatron) | 5 |
| llama | [Meta / Llama](#llama) | 3 |

## deepseek

DeepSeek

API changelog reviewed; separate weight-publication dates and quiet pre-release tests may remain.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-13 (boundary day) | DeepSeek V4 Pro 0813 | model-llm | general_availability | [Publisher](https://api-docs.deepseek.com/news/news260813) |
| 2026-08-21 | DeepSeek V4 Flash Vision Exp Vision-Exp | model-llm | api_preview | [Publisher](https://api-docs.deepseek.com/news/news260821) |
| 2026-09-10 | DeepSeek V4.1 Flash | model-llm | api_launch | [Publisher](https://api-docs.deepseek.com/news/news260910) |

Date qualifications:

- **DeepSeek V4 Pro 0813, 2026-08-13 (boundary day):** Publisher day; partial lower-bound day remains uncertain.
- **DeepSeek V4.1 Flash, 2026-09-10:** Current changelog reverses the announced September 14 V4 Pro alias retirement; announcement page still contains the old plan.

## minimax

MiniMax

Music source and retained official M3.1 posts reviewed; earlier picker sightings unverified. Full Code/Design/Hailuo release histories not certified.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-13 (boundary day) | MiniMax Music 3.0 | model-other | weights_launch | [Publisher](https://www.minimax.io/blog/minimax-music-3-0-next-generation-open-weights-production-ready-versatile-music-model) |
| 2026-09-27 05:24:55 UTC | MiniMax M3.1 Flash Preview | model-llm | product_preview | [Stored official post](https://x.com/MiniMaxAgent/status/2104079819881517400) |
| 2026-09-27 17:06:37 UTC | MiniMax M3.1 Flash Preview | model-llm | subscription_availability | [Stored official post](https://x.com/MiniMax_AI/status/2104256406786547800) |

Date qualifications:

- **MiniMax Music 3.0, 2026-08-13 (boundary day):** Publisher day; partial lower-bound day remains uncertain.
- **MiniMax M3.1 Flash Preview, 2026-09-27 05:24:55 UTC:** Available inside MiniMax Code; official post already captured by the collector. This does not establish a public inference API or weight release.
- **MiniMax M3.1 Flash Preview, 2026-09-27 17:06:37 UTC:** Token Plan availability announcement; same model, a second access milestone.

## qwen

Alibaba / Qwen

Research/model lifecycle, image repository and every one of six Qwen Code release pages reviewed. Regional SKUs are separate; general Alibaba product history is not exhaustive.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-14 | Qwen3.8 27B [27B] | model-llm | weights_launch | [Publisher](https://github.com/QwenLM/Qwen3.8#news) |
| 2026-08-17 | Qwen3.8 27B | model-llm | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-08-20 | Wan Video Prime 3.0 | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-08-24 04:10:58 UTC | Qwen CUA Driver v0.20.0 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.0) |
| 2026-08-26 | Qwen3.8 Flash | model-llm | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-08-26 08:17:26 UTC | Qwen3.8 Flash Next | model-llm | weight_revision | [Artifact date](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/commit/34567a4712bc9766c4449e2e98e4468bfa24d915) |
| 2026-08-26 09:37:43 UTC | Qwen Code Desktop v0.2.2 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.2.2) |
| 2026-08-26 11:23:28 UTC | Qwen CUA Driver v0.20.1 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.1) |
| 2026-08-28 | Qwen MT Image 2.0 | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-08-28 15:19:39 UTC | Qwen CUA Driver v0.20.2 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.2) |
| 2026-08-30 | Qwen Flash Character | model-llm | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-01 07:12:34 UTC | Qwen CUA Driver v0.20.3 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.3) |
| 2026-09-02 | E-Commerce Bench | other | open_source_launch | [Publisher](https://qwen.ai/research) |
| 2026-09-02 | Qwen Drive 1.0 [4B] | model-other | open_source_launch | [Publisher](https://qwen.ai/research) |
| 2026-09-02 | Qwen3.8 Max 0902 | model-llm | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-02 14:29:52 UTC | Qwen Live Host v0.2.0 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/live-host-v0.2.0) |
| 2026-09-07 10:27:09 UTC | Qwen CUA Driver v0.20.4 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.4) |
| 2026-09-08 15:21:49 UTC | Qwen Code TypeScript SDK v0.1.9 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.9) |
| 2026-09-08 16:49:20 UTC | Qwen Code TypeScript SDK v0.1.10 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.10) |
| 2026-09-09 11:47:33 UTC | Qwen Code TypeScript SDK v0.1.11 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.11) |
| 2026-09-09 14:12:51 UTC | Qwen CUA Driver v0.20.5 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.5) |
| 2026-09-10 05:53:37 UTC | Qwen Code Desktop v0.3.0-preview.0 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.3.0-preview.0) |
| 2026-09-10 08:04:06 UTC | Qwen Code Desktop v0.3.0 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.3.0) |
| 2026-09-10 15:52:03 UTC | Qwen Code TypeScript SDK v0.1.12 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.12) |
| 2026-09-13 11:15:43 UTC | Qwen CUA Driver v0.20.6 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.6) |
| 2026-09-14 12:11:14 UTC | Qwen CUA Driver v0.20.7 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.7) |
| 2026-09-14 15:55:29 UTC | Qwen CUA Driver v0.20.8 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.8) |
| 2026-09-15 05:37:52 UTC | Qwen CUA Driver v0.20.9 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.9) |
| 2026-09-17 | HappyOyster 1.0 [Acting, Adventure, Directing] | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-17 | Qwen3.8 Omni Flash | model-llm | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-17 04:17:14 UTC | Qwen Code Desktop v0.24.0 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.0) |
| 2026-09-18 | Qwen Live Harness | harness | open_source_launch | [Publisher](https://qwen.ai/blog?id=qwen3.8-omni-flash) |
| 2026-09-18 | Qwen MM Plugins | harness | capability_release | [Publisher](https://qwen.ai/blog?id=qwen3.8-omni-flash) |
| 2026-09-18 | Qwen3.8 LiveTranslate | model-other | named_launch | [Publisher](https://qwen.ai/research) |
| 2026-09-18 | Qwen3.8 Omni Flash | model-llm | named_launch | [Publisher](https://qwen.ai/blog?id=qwen3.8-omni-flash) |
| 2026-09-19 08:40:20 UTC | Qwen Code Desktop v0.24.1 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.1) |
| 2026-09-19 09:05:56 UTC | Qwen Code TypeScript SDK v0.1.13 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.13) |
| 2026-09-20 | Qwen Audio Realtime Plus 3.1 | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-20 | Qwen Image 2.1 | model-other | weights_launch | [Publisher](https://github.com/QwenLM/Qwen-Image-2.1#news) |
| 2026-09-21 | Qwen3.8 Omni Flash Realtime | model-llm | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-21 15:20:34 UTC | Qwen Code TypeScript SDK v0.1.14 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.14) |
| 2026-09-21 16:32:58 UTC | Qwen Code Desktop v0.24.3 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.3) |
| 2026-09-22 15:41:09 UTC | Qwen Code Desktop v0.24.4 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.4) |
| 2026-09-23 09:59:26 UTC | Qwen CUA Driver v0.20.11 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/cua-driver-rs-v0.20.11) |
| 2026-09-24 | Alibaba Decision Model Preview | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-09-24 17:41:47 UTC | Qwen Code Desktop v0.24.5 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.5) |
| 2026-09-24 18:09:07 UTC | Qwen Code TypeScript SDK v0.1.15 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.15) |
| 2026-09-26 00:59:39 UTC | Qwen Code Desktop v0.24.6 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.6) |
| 2026-09-26 01:26:02 UTC | Qwen Code TypeScript SDK v0.1.16 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.16) |
| 2026-09-29 14:47:20 UTC | Qwen Code Desktop v0.24.7 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.24.7) |
| 2026-09-29 15:12:40 UTC | Qwen Code TypeScript SDK v0.1.17 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.17) |
| 2026-10-02 | Qwen Image Pro 2.1 | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-10-03 | Qwen3.8 Flash | model-llm | regional_api_availability | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-10-05 10:23:32 UTC | Qwen Code TypeScript SDK v0.1.18 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.18) |
| 2026-10-05 10:45:59 UTC | Qwen Code Desktop v0.25.0 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.25.0) |
| 2026-10-06 18:45:47 UTC | Qwen Code CLI v0.25.1-preview.0 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.1-preview.0) |
| 2026-10-07 22:01:24 UTC | Qwen Code CLI v0.25.0-nightly.20261007.8003d28042 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.0-nightly.20261007.8003d28042) |
| 2026-10-08 | Qwen3.7 Flash | model-llm | regional_api_availability | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-10-08 | Qwen3.8 Max | model-llm | regional_api_availability | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-10-09 | Qwen Image Turbo 2.1 | model-other | weights_launch | [Publisher](https://github.com/QwenLM/Qwen-Image-2.1#news) |
| 2026-10-09 | Qwen Image Turbo 2.1 | model-other | api_listing | [Platform](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) |
| 2026-10-09 05:35:14 UTC | Qwen Code CLI v0.25.1-preview.1 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.1-preview.1) |
| 2026-10-09 22:09:39 UTC | Qwen Code CLI v0.25.0-nightly.20261009.085a44f336 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.0-nightly.20261009.085a44f336) |
| 2026-10-10 18:14:33 UTC | Qwen Code CLI v0.25.1-preview.2 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.1-preview.2) |
| 2026-10-10 21:59:22 UTC | Qwen Code CLI v0.25.0-nightly.20261010.9763580b84 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.0-nightly.20261010.9763580b84) |
| 2026-10-11 10:20:36 UTC | Qwen Code CLI v0.25.1 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.1) |
| 2026-10-11 11:31:22 UTC | Qwen Code Desktop v0.25.1 | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/desktop-v0.25.1) |
| 2026-10-11 11:42:33 UTC | Qwen Code TypeScript SDK v0.1.19 | harness | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/sdk-typescript-v0.1.19) |
| 2026-10-11 22:01:32 UTC | Qwen Code CLI v0.25.1-nightly.20261011.01d3e6d81a | agent | software_version | [Publisher](https://github.com/QwenLM/qwen-code/releases/tag/v0.25.1-nightly.20261011.01d3e6d81a) |

Date qualifications:

- **Qwen3.8 27B, 2026-08-17:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Wan Video Prime 3.0, 2026-08-20:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen3.8 Flash, 2026-08-26:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen3.8 Flash Next, 2026-08-26 08:17:26 UTC:** The dated initial revision contains 131 weight shards. This is an artifact date, not a proved first-public-access instant.
- **Qwen MT Image 2.0, 2026-08-28:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen Flash Character, 2026-08-30:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **E-Commerce Bench, 2026-09-02:** Evaluation artifact; distinguish a benchmark/environment from a model.
- **Qwen Drive 1.0 [4B], 2026-09-02:** VLM for perception/planning; category is provisional.
- **Qwen3.8 Max 0902, 2026-09-02:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **HappyOyster 1.0 [Acting, Adventure, Directing], 2026-09-17:** Three same-day variants of an existing Alibaba world-model family. Acting is currently an invitational preview; do not assume unrestricted public access. Ownership corroboration: https://www.alibabagroup.com/en-US/about-alibaba
- **Qwen3.8 Omni Flash, 2026-09-17:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen Live Harness, 2026-09-18:** Publisher explicitly says the runtime is open sourced. Earliest code publication could predate this announcement.
- **Qwen MM Plugins, 2026-09-18:** Expanded plugin suite, including Video2Note and Omni Skill Creator; not necessarily the suite's first release.
- **Qwen3.8 LiveTranslate, 2026-09-18:** Specialized live translation; category is provisional.
- **Qwen3.8 Omni Flash, 2026-09-18:** Publisher announcement is marked draft; corroborated by the research index and Model Studio lifecycle entries. API entry is separately dated September 17.
- **Qwen Audio Realtime Plus 3.1, 2026-09-20:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen3.8 Omni Flash Realtime, 2026-09-21:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Alibaba Decision Model Preview, 2026-09-24:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen Image Pro 2.1, 2026-10-02:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen3.8 Flash, 2026-10-03:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen3.7 Flash, 2026-10-08:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen3.8 Max, 2026-10-08:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.
- **Qwen Image Turbo 2.1, 2026-10-09:** 8-step variant; distinguish version variant from separate quantizations.
- **Qwen Image Turbo 2.1, 2026-10-09:** Model Studio lifecycle date for the named API SKU; not necessarily its worldwide announcement or first exposure.

## glm

Z.ai / Zhipu

GLM5.3/Flash and Ox mapping verified; eight ZCode versions dated. AutoClaw version chronology remains open.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-14 | GLM 5.3 | model-llm | api_launch | [Publisher](https://z.ai/blog/glm-5.3) |
| 2026-08-20 | GLM Flash 5.3 [Ox Alpha] | model-llm | anonymous_public_test | [Publisher](https://openrouter.ai/stealth/ox-alpha) |
| 2026-08-26 | GLM Flash 5.3 [Ox Alpha] | model-llm | named_launch_identity_reveal | [Publisher](https://z.ai/blog/glm-5.3-flash) |
| 2026-08-27 17:16:19 UTC | GLM 5.3 | model-llm | weight_revision | [Artifact date](https://huggingface.co/zai-org/GLM-5.3/commit/7cda81930d6e4cef42f48555de830aa32ecdde28) |
| 2026-08-31 | ZCode 3.10.2 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-09-04 | ZCode 3.11.2 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-09-17 | ZCode 3.12.3 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-09-19 | ZCode 3.14.0 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-09-22 | ZCode 3.14.1 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-09-22 | ZCode 3.14.3 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-09-29 | ZCode 3.14.4 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |
| 2026-10-09 | ZCode 3.14.5 | agent | software_version | [Publisher](https://zcode.z.ai/en/changelog) |

Date qualifications:

- **GLM 5.3, 2026-08-14:** Weights were promised for later; retain a separate dated artifact milestone.
- **GLM Flash 5.3 [Ox Alpha], 2026-08-20:** OpenRouter dates Ox Alpha to August 20; Z.ai's August 26 launch post explicitly identifies its anonymous Ox Alpha tests on OpenCode and OpenRouter.
- **GLM Flash 5.3 [Ox Alpha], 2026-08-26:** Official launch also states weights are public; identity evidence connects Ox Alpha to this same model.
- **GLM 5.3, 2026-08-27 17:16:19 UTC:** 141 weight shards in the initial revision; commit title 0828, UTC instant August 27 (August 28 at UTC+8). Visibility history is not proved by commit history.

## mistral

Mistral AI

News, product release notes and Vibe CLI public tags reviewed. Future Large4 weights are not counted.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-18 14:13:33 UTC | Mistral Vibe CLI v2.24.2 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.24.2) |
| 2026-08-20 | Agentic Search | harness | product_launch | [Publisher](https://mistral.ai/news/agentic-search/) |
| 2026-08-20 17:39:00 UTC | Mistral Vibe CLI v2.24.3 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.24.3) |
| 2026-08-26 15:19:50 UTC | Mistral Vibe CLI v2.24.4 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.24.4) |
| 2026-08-27 15:29:03 UTC | Mistral Vibe CLI v2.24.5 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.24.5) |
| 2026-09-04 08:53:52 UTC | Mistral Vibe CLI v2.25.0 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.0) |
| 2026-09-09 13:37:18 UTC | Mistral Vibe CLI v2.25.1 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.1) |
| 2026-09-10 14:42:15 UTC | Mistral Vibe CLI v2.25.2 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.2) |
| 2026-09-11 13:05:47 UTC | Mistral Vibe CLI v2.25.3 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.3) |
| 2026-09-12 18:39:34 UTC | Mistral Vibe CLI v2.25.4 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.4) |
| 2026-09-14 | Vibe unified experience | agent | phased_rollout | [Publisher](https://docs.mistral.ai/resources/release-notes) |
| 2026-09-18 11:09:46 UTC | Mistral Vibe CLI v2.25.5 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.5) |
| 2026-09-22 | Vibe Work [Spreadsheets, Mini App Canvas, Agentic Knowledge Base] | agent | capability_release | [Publisher](https://docs.mistral.ai/resources/release-notes) |
| 2026-09-22 08:21:02 UTC | Mistral Vibe CLI v2.25.7 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.7) |
| 2026-09-23 15:10:39 UTC | Mistral Vibe CLI v2.25.8 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.25.8) |
| 2026-10-01 | Vibe unified experience | agent | enterprise_rollout | [Publisher](https://docs.mistral.ai/resources/release-notes) |
| 2026-10-06 | Mistral Large 4 [le Chonk, ML4] | model-llm | api_public_preview | [Publisher](https://mistral.ai/news/mistral-large-4/) |
| 2026-10-06 10:11:18 UTC | Mistral Vibe CLI v2.26.0 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.26.0) |
| 2026-10-09 | Managed Deployments | other | product_launch | [Publisher](https://docs.mistral.ai/resources/release-notes) |
| 2026-10-09 14:56:56 UTC | Mistral Vibe CLI v2.26.1 | agent | software_version | [Publisher](https://github.com/mistralai/mistral-vibe/releases/tag/v2.26.1) |

Date qualifications:

- **Agentic Search, 2026-08-20:** Retrieval infrastructure/tooling; provisional harness versus other classification.
- **Vibe unified experience, 2026-09-14:** September 22 notes state phased Free/Pro/Teams migration began September 14; enterprise migration begins October 1.
- **Vibe Work [Spreadsheets, Mini App Canvas, Agentic Knowledge Base], 2026-09-22:** Spreadsheet, Mini App Canvas and Agentic Knowledge Base updates are one same-day feature bundle.
- **Vibe unified experience, 2026-10-01:** An access rollout of an existing experience, not another model generation.
- **Mistral Large 4 [le Chonk, ML4], 2026-10-06:** Alias le Chonk / ML4. End-of-October weights are planned, not released in this window.
- **Managed Deployments, 2026-10-09:** Managed worker infrastructure for Workflows; provisional AI platform product.

## moonshot-kimi

Moonshot AI / Kimi

K3 milestones predate this window; Kimi Code public releases reviewed. SDK repository has no published release records; that does not prove no SDK availability.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-13 05:50:17 UTC | Kimi Code 0.36.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.36.0) |
| 2026-08-14 12:53:36 UTC | Kimi Code 0.36.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.36.1) |
| 2026-08-18 11:23:11 UTC | Kimi Code 0.37.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.37.0) |
| 2026-08-18 14:32:13 UTC | Kimi Code 0.37.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.37.1) |
| 2026-08-18 17:40:37 UTC | Kimi Code 0.37.2 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.37.2) |
| 2026-08-20 13:13:44 UTC | Kimi Code 0.38.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.38.0) |
| 2026-08-27 11:36:28 UTC | Kimi Code 0.39.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.39.0) |
| 2026-08-28 10:01:05 UTC | Kimi Code 0.39.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.39.1) |
| 2026-09-02 05:59:00 UTC | Kimi Code 0.40.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.40.0) |
| 2026-09-02 09:20:44 UTC | Kimi Code 0.40.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.40.1) |
| 2026-09-04 11:01:07 UTC | Kimi Code 0.41.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.41.0) |
| 2026-09-09 06:24:42 UTC | Kimi Code 0.42.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.42.0) |
| 2026-09-14 12:03:30 UTC | Kimi Code 0.43.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.43.0) |
| 2026-09-15 06:51:26 UTC | Kimi Code 0.43.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%400.43.1) |
| 2026-09-17 05:22:40 UTC | Kimi Code 2.0.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%402.0.0) |
| 2026-09-18 13:13:46 UTC | Kimi Code 2.0.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%402.0.1) |
| 2026-09-19 12:09:15 UTC | Kimi Code 2.0.2 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%402.0.2) |
| 2026-09-23 12:31:44 UTC | Kimi Code 2.1.0 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%402.1.0) |
| 2026-09-24 07:24:08 UTC | Kimi Code 2.1.1 | agent | software_version | [Publisher](https://github.com/MoonshotAI/kimi-code/releases/tag/%40moonshot-ai/kimi-code%402.1.1) |

## stepfun

StepFun

Step5 official launch/community rollout and dated StepAudio3 publisher listing. October15 weights are future.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-09-15 | StepAudio 3 [Realtime, ASR, TTS, Gen, Music] | model-other | named_launch | [Publisher indexed text](https://www.stepfun.com/news) |
| 2026-09-20 03:15:13 UTC | Step 5 Preview | model-llm | api_product_preview | [Stored official post](https://x.com/StepFun_ai/status/2101510462685003786) |
| 2026-10-08 13:08:33 UTC | Step 5 Preview [OpenRouter, OpenCode, Cline, Nous Portal, Kilo Code] | model-llm | community_platform_rollout | [Stored official post](https://x.com/StepFun_ai/status/2108182763002278158) |

Date qualifications:

- **StepAudio 3 [Realtime, ASR, TTS, Gen, Music], 2026-09-15:** Official Chinese news listing supplies the date and five sibling audio products.
- **Step 5 Preview, 2026-09-20 03:15:13 UTC:** Company's launch post and model page; October 15 weights remain a future promise.
- **Step 5 Preview [OpenRouter, OpenCode, Cline, Nous Portal, Kilo Code], 2026-10-08 13:08:33 UTC:** Company announces OpenRouter access and week-long trials through partner agent products.

## inclusionai

Ant Group / inclusionAI

Ling, LLaDA, Ming and runtime evidence reviewed; artifact dates qualified. Untagged projects and separate Realtime Venus weights may remain.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-25 10:23:59 UTC | AReaL v2.1.0 | harness | software_version | [Publisher](https://github.com/areal-project/AReaL/releases/tag/v2.1.0) |
| 2026-09-03 07:29:00 UTC | Ling Flash Fin 3.0 | model-llm | weight_revision | [Artifact date](https://huggingface.co/inclusionAI/Ling-3.0-flash-Fin/commit/d42845b811a125b6c31822d07ff0a01548ac29e7) |
| 2026-09-04 | LLaDA Image [Base, Turbo] | model-other | weights_and_code_launch | [Publisher](https://github.com/inclusionAI/LLaDA-Image#news) |
| 2026-09-04 | Ling Flash Sante 3.0 | model-llm | platform_availability | [Platform](https://openrouter.ai/inclusionai/ling-3.0-flash-sante) |
| 2026-09-04 | Ling Flash VL 3.0 | model-llm | api_launch | [Publisher](https://developer.ant-ling.com/en/docs/getting-started/changelog/) |
| 2026-09-15 02:19:52 UTC | LLaDA UI | model-llm | code_release_revision | [Artifact date](https://github.com/inclusionAI/LLaDA-UI/commit/b3e84b9613c4f931e34764b7fbec43f547bf293d) |
| 2026-09-17 11:33:24 UTC | Ming Image Design 0.1 | model-other | weight_revision | [Artifact date](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design/commit/ef6562bdd166ee7a823b191286f223f8ee05e0a7) |
| 2026-09-17 11:38:02 UTC | Ming Image Design Layer 0.1 | model-other | weight_revision | [Artifact date](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer/commit/e754ee3a342179de92eb79aece58d2039edb1a4a) |
| 2026-09-17 14:17:17 UTC | Ming Image inference code 0.1 | harness | code_release_revision | [Artifact date](https://github.com/inclusionAI/Ming-Image/commit/ddbae3096a97439cf05a91832726e580566dd6cd) |
| 2026-09-18 13:18:44 UTC | Realtime Venus Harness | harness | code_release_revision | [Artifact date](https://github.com/inclusionAI/Realtime-Venus/commit/f493f5c8b0e14c1ec302f98009c23e6ec4fd0433) |
| 2026-09-21 15:46:01 UTC | Realtime Venus Android demo 0918 | agent | software_beta | [Publisher](https://github.com/inclusionAI/Realtime-Venus/releases/tag/android-beta-0918) |
| 2026-09-30 | Ling Flash 3.1 | model-llm | community_api_trial | [Platform](https://vercel.com/changelog/ling-3-1-flash-is-now-available-on-ai-gateway) |
| 2026-09-30 16:33:22 UTC | Ling Flash 3.1 | model-llm | named_announcement | [Stored official post](https://x.com/AntLingAGI/status/2105335205741596911) |
| 2026-10-02 16:14:26 UTC | Ling Flash 3.1 [OpenRouter] | model-llm | platform_availability | [Stored official post](https://x.com/AntLingAGI/status/2106055214969282968) |

Date qualifications:

- **Ling Flash Fin 3.0, 2026-09-03 07:29:00 UTC:** Dated publisher revision contains 65 weight files. Artifact timestamp, not proved first-public-access instant.
- **LLaDA Image [Base, Turbo], 2026-09-04:** Release note explicitly dates both checkpoints and inference code.
- **Ling Flash Sante 3.0, 2026-09-04:** OpenRouter's own page dates the listing September 4. A third-party snapshot's September 26 free alias is not the same event.
- **Ling Flash VL 3.0, 2026-09-04:** The company's API platform changelog establishes September 4 availability; later platform listings can have later dates.
- **LLaDA UI, 2026-09-15 02:19:52 UTC:** Vision-language GUI model plus execution/evaluation code. This dates the initial code revision, not checkpoint publication; proposed type needs review.
- **Ming Image Design 0.1, 2026-09-17 11:33:24 UTC:** Historical recursive tree contains 16 weight files; commit date is distinct from repository creation and visibility.
- **Ming Image Design Layer 0.1, 2026-09-17 11:38:02 UTC:** Historical recursive tree contains 20 weight files; distinct Layer variant.
- **Ming Image inference code 0.1, 2026-09-17 14:17:17 UTC:** Publisher commit declares initial code release; source revision time is not automatically first-public-access time.
- **Realtime Venus Harness, 2026-09-18 13:18:44 UTC:** Initial release revision contains runtime/demo/frontend code; Ant Venus Team and Tsinghua are credited. Model weights need their own dates.
- **Realtime Venus Android demo 0918, 2026-09-21 15:46:01 UTC:** GitHub publication is September 21, despite 0918 in the tag.
- **Ling Flash 3.1, 2026-09-30:** Vercel's publisher-day date for API availability through Novita; exact timezone not specified.
- **Ling Flash 3.1, 2026-09-30 16:33:22 UTC:** UTC September 30 / October 1 at UTC+8. Weights only planned.
- **Ling Flash 3.1 [OpenRouter], 2026-10-02 16:14:26 UTC:** Company announces OpenRouter availability; UTC October 2 / October 3 at UTC+8.

## mimo

Xiaomi / MiMo

Official September22 model/desktop/RL publication source reviewed. Serving-mode and model-generation identities differ.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-09-22 | MiMo Desktop | agent | general_availability | [Publisher](https://mimo.xiaomi.com/mimo-v2-6) |
| 2026-09-22 | MiMo V2.6 [Pro, Flash] | model-llm | weights_and_api_launch | [Publisher](https://mimo.xiaomi.com/mimo-v2-6) |
| 2026-09-22 | MiMo V2.6 Pro UltraSpeed | model-llm | product_rollout | [Publisher](https://mimo.xiaomi.com/mimo-v2-6) |
| 2026-09-22 | MiMo V2.6 RL code and environments | harness | open_source_launch | [Publisher](https://mimo.xiaomi.com/mimo-v2-6) |

Date qualifications:

- **MiMo Desktop, 2026-09-22:** Publisher says first official release after early access; model and desktop product are separate.
- **MiMo V2.6 [Pro, Flash], 2026-09-22:** Xiaomi's source day differs from third-party September 21 dates; keep the publisher day.
- **MiMo V2.6 Pro UltraSpeed, 2026-09-22:** Serving mode of Pro, not a separately established model generation.
- **MiMo V2.6 RL code and environments, 2026-09-22:** Publisher announces RL code and environments; training harness, not an independently named model.

## hunyuan

Tencent / Hunyuan

Hy4, dated Hy Image3.5 card and Tencent product announcements reviewed. CodeBuddy/WorkBuddy full changelogs not certified.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-28 | Tencent Hy4 Preview [BF16, FP8] | model-llm | weights_and_api_preview | [Publisher](https://www.tencent.com/tencent-releases-and-open-sources-tencent-hy4-preview/) |
| 2026-09-17 | WorkBuddy 5.5.6 | agent | software_capability_release | [Publisher indexed text](https://cloudbase.cloud.tencent.com/en/blog/2026/09/18/workbuddy-cloudbase-case) |
| 2026-09-21 | Tencent Hy Image 3.5 Preview | model-other | named_preview_announcement | [Publisher](https://hunyuan.tencent.com/research/hy-image35-preview) |
| 2026-09-23 | Tencent Cloud DataBuddy | agent | product_launch | [Publisher indexed text](https://www.tencentcloud.com/dynamic/news-details/101532) |

Date qualifications:

- **Tencent Hy4 Preview [BF16, FP8], 2026-08-28:** Available through Tencent products/API and OpenRouter; not Hy3 as some secondary stories label it.
- **WorkBuddy 5.5.6, 2026-09-17:** Tencent's September 18 CloudBase post says yesterday's 5.5.6 release added full-stack app generation; source is primary partner team.
- **Tencent Hy Image 3.5 Preview, 2026-09-21:** Official homepage's dated release card; detail page returns only Loading. API/weights availability not separately verified.
- **Tencent Cloud DataBuddy, 2026-09-23:** Company press release names four built-in data agents; proposed category agent versus other remains reviewable.

## nemo-megatron

NVIDIA / NeMo / Nemotron

NVIDIA model introduction, safety stack and published Guardrails/NAT tags reviewed. Relay and diarization exact dates remain open; no complete all-NVIDIA AI release census.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-26 19:31:04 UTC | NeMo Guardrails v0.24.0 | harness | software_version | [Publisher](https://github.com/NVIDIA-NeMo/Guardrails/releases/tag/v0.24.0) |
| 2026-09-10 22:12:09 UTC | NeMo Agent Toolkit v1.9.0 | harness | software_version | [Publisher](https://github.com/NVIDIA/NeMo-Agent-Toolkit/releases/tag/v1.9.0) |
| 2026-09-16 17:15:59 UTC | NeMo Guardrails v0.24.1 | harness | software_version | [Publisher](https://github.com/NVIDIA-NeMo/Guardrails/releases/tag/v0.24.1) |
| 2026-09-23 | NV Reason CT | model-llm | research_model_introduction | [Publisher](https://developer.nvidia.com/blog/introducing-nv-reason-ct-open-3d-ct-vlm-for-radiologist-chain-of-thought-reasoning/) |
| 2026-09-28 | NVIDIA Open Agent Safety Platform | harness | reference_platform_introduction | [Publisher](https://developer.nvidia.com/blog/nvidia-open-agent-safety-platform-a-reference-for-continuous-in-silicon-agent-monitoring/) |

Date qualifications:

- **NV Reason CT, 2026-09-23:** Medical vision-language research model; primary introduction date, checkpoint first availability not separately established.
- **NVIDIA Open Agent Safety Platform, 2026-09-28:** NVIDIA introduces the combined open safety stack; this does not establish the first release date of its pre-existing OpenShell component.

## llama

Meta / Llama

Meta Muse model/agent/company announcements reviewed. Legacy Llama Stack URL redirects to OGX; its eight releases held for owner verification. No new Llama-branded model launch established within the window.

| Date and precision | Product / version / variants | Proposed kind | Milestone | Evidence |
| --- | --- | --- | --- | --- |
| 2026-09-02 | Muse Spark 1.3 | model-llm | api_product_launch | [Publisher](https://research.meta.ai/blog/introducing-muse-spark-1-3) |
| 2026-09-08 | Muse | agent | public_rollout | [Publisher](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) |
| 2026-09-29 | Muse for Small Business | agent | capability_release | [Publisher](https://about.fb.com/news/2026/09/introducing-muse-small-business/) |

Date qualifications:

- **Muse Spark 1.3, 2026-09-02:** Available on Muse Code and Meta Model API; source promises later open weights.
- **Muse, 2026-09-08:** Article subsequently updated September 30; use original publication day.
- **Muse for Small Business, 2026-09-29:** Article updated October 8; do not move the launch to the update day.

## Pending dates and ownership

These entries are not part of the dated release-event count. They preserve
concrete gaps rather than creating unsupported chart markers.

| Company | Product / version | Reported date | Reason / source |
| --- | --- | --- | --- |
| llama | Meta Enterprise Platform  | 2026-09-28 | Organizational/strategic announcement; availability of a new product is not established. Held outside the release-event count. [Source](https://about.fb.com/news/2026/09/launching-meta-enterprise-platform/) |
| llama | Llama Stack / OGX v1.5.0 | 2026-10-09T01:54:32Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.5.0) |
| llama | Llama Stack / OGX v1.0.4 | 2026-10-08T00:26:32Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.0.4) |
| llama | Llama Stack / OGX v1.4.0 | 2026-09-11T14:08:23Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.4.0) |
| llama | Llama Stack / OGX v1.0.3 | 2026-09-10T19:41:05Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.0.3) |
| llama | Llama Stack / OGX v1.3.1 | 2026-09-01T21:05:47Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.3.1) |
| llama | Llama Stack / OGX v1.2.5 | 2026-08-31T17:00:49Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.2.5) |
| llama | Llama Stack / OGX v1.2.4 | 2026-08-20T13:55:42Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.2.4) |
| llama | Llama Stack / OGX v1.2.3 | 2026-08-17T16:25:34Z | Requested legacy URL redirects to ogx-ai/ogx; current release publisher attribution to Meta is unverified. Held out of Meta release counts. [Source](https://github.com/ogx-ai/ogx/releases/tag/v1.2.3) |
| — | Space Bunny Alpha  | 2026-09-23 | Public anonymous preview date confirmed by OpenRouter; company identity remains unknown. MiniMax/M3.1 attribution is speculation, not a canonical mapping. [Source](https://openrouter.ai/stealth/space-bunny-alpha) |
| minimax | M3.1 Flash Preview early picker sightings  | 2026-09-26 | Secondary report of earlier unannounced access; original dated user evidence not yet verified. Official September 27 milestone is separate. [Source](https://vibecodedthis.com/blog/muse/minimax-m31-flash-preview-coding-model) |
| inclusionai | Realtime Venus Omni / Audio weights  | — | Publisher documents both models and the runtime. Code release is dated; separate checkpoint publication dates were not established in this pass. [Source](https://github.com/inclusionAI/Realtime-Venus) |
| glm | AutoClaw current product versions  | — | October blog recaps mention existing features; article date does not establish the release dates of AutoClaw, Auto Design or cluster mode. [Source](https://autoclaw.z.ai/blog/) |
| nemo_megatron | NeMo Relay  | — | September 30 tutorial dates documentation, not the product first release. Keep actual version/tag dates open. [Source](https://developer.nvidia.com/blog/tracing-agent-harness-behavior-with-nvidia-nemo-relay/) |
| nemo_megatron | Nemotron 3 Diarization  | 2026-09 | NVIDIA names it as the September 2026 release; exact day and original release milestone remain unverified. [Source](https://developer.nvidia.com/blog/?p=104696) |
| hunyuan | CodeBuddy / other WorkBuddy versions  | — | Company documents current access through these products; those mentions do not establish their original release dates. [Source](https://www.tencent.com/tencent-releases-and-open-sources-tencent-hy4-preview/) |

## Announced future availability

The announcement exists, but the promised distribution milestone has not
occurred within the selected window.

| Company | Product | Promised availability | Source |
| --- | --- | --- | --- |
| mistral | Mistral Large4 weights | end of October2026 | [Publisher](https://mistral.ai/news/mistral-large-4/) |
| stepfun | Step5 Preview weights | 2026-10-15 | [Publisher](https://www.stepfun.com/step-5-preview) |
| inclusionai | Ling3.1Flash weights | — | [Publisher](https://x.com/AntLingAGI/status/2105335205741596911) |
| llama | MuseSpark open weights | — | [Publisher](https://research.meta.ai/blog/introducing-muse-spark-1-3) |

## Excluded records

The raw software review found 125 published release objects inside the window.
It retained 80 product-version objects, excluded 36 Qwen test/benchmark/image
assets and one NVIDIA pinned-test-toolchain release, and held eight OGX
releases for company ownership. ZCode contributes eight separate day-dated
software entries. All six Qwen Code API pages were read; pages two through six
added no in-window objects. A single old published_at value was not treated as
proof that subsequent pages could be skipped.

Other reviewed exclusions follow. Hardware, funding, partnerships, research
recaps and general company announcements are not automatically product launches.

| Company | Product / version | Date | Exclusion / source |
| --- | --- | --- | --- |
| qwen | Qwen Code pr-9806-verification-assets | 2026-08-24T17:25:55Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/pr-9806-verification-assets) |
| qwen | Qwen Code gh-attach-assets | 2026-08-24T06:12:11Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/gh-attach-assets) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260821-r1 | 2026-08-21T02:38:07Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260821-r1) |
| qwen | Qwen Code dsw-eas-full-20260821-r1 | 2026-08-21T03:47:18Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260821-r1) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260820-r3 | 2026-08-20T15:49:49Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260820-r3) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260820-r2 | 2026-08-20T15:29:40Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260820-r2) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260820-r1 | 2026-08-20T15:11:31Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260820-r1) |
| qwen | Qwen Code dsw-eas-net-smoke-20260819-r1 | 2026-08-19T02:33:53Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-net-smoke-20260819-r1) |
| qwen | Qwen Code dsw-eas-manual-smoke-20260820-r2 | 2026-08-20T12:23:33Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-manual-smoke-20260820-r2) |
| qwen | Qwen Code dsw-eas-manual-smoke-20260820-r1 | 2026-08-20T11:50:34Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-manual-smoke-20260820-r1) |
| qwen | Qwen Code dsw-eas-full-20260820-r1 | 2026-08-19T17:13:28Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260820-r1) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260817-r4 | 2026-08-17T07:38:36Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260817-r4) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260817-r3 | 2026-08-17T06:58:36Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260817-r3) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260817-r2 | 2026-08-17T06:47:31Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260817-r2) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260817-r1 | 2026-08-17T06:28:57Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260817-r1) |
| qwen | Qwen Code dsw-eas-full-20260817-r3 | 2026-08-17T08:56:00Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260817-r3) |
| qwen | Qwen Code dsw-eas-full-20260817-r2 | 2026-08-17T08:30:54Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260817-r2) |
| qwen | Qwen Code dsw-eas-full-20260817-r1 | 2026-08-17T08:29:46Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260817-r1) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260815-r5 | 2026-08-15T13:20:21Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260815-r5) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260815-r4 | 2026-08-15T13:14:45Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260815-r4) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260815-r3 | 2026-08-15T12:00:04Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260815-r3) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260815-r2 | 2026-08-15T11:56:50Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260815-r2) |
| qwen | Qwen Code dsw-eas-tb-smoke-20260815-r1 | 2026-08-15T07:09:26Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-smoke-20260815-r1) |
| qwen | Qwen Code dsw-eas-full-20260816-r3 | 2026-08-16T02:35:37Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260816-r3) |
| qwen | Qwen Code dsw-eas-full-20260816-r2 | 2026-08-16T02:12:41Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260816-r2) |
| qwen | Qwen Code dsw-eas-full-20260816-r1 | 2026-08-16T01:43:33Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260816-r1) |
| qwen | Qwen Code dsw-eas-full-20260815-r1 | 2026-08-15T13:51:49Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260815-r1) |
| qwen | Qwen Code dsw-eas-tb-e2e-20260814-r6 | 2026-08-14T07:55:47Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-e2e-20260814-r6) |
| qwen | Qwen Code dsw-eas-tb-e2e-20260814-r3 | 2026-08-14T06:00:48Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-e2e-20260814-r3) |
| qwen | Qwen Code dsw-eas-tb-e2e-20260814-r2 | 2026-08-14T05:49:41Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-e2e-20260814-r2) |
| qwen | Qwen Code dsw-eas-tb-e2e-20260814-r1 | 2026-08-14T03:58:24Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-e2e-20260814-r1) |
| qwen | Qwen Code weaken-tool-error-shots | 2026-08-13T05:23:25Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/weaken-tool-error-shots) |
| qwen | Qwen Code dsw-eas-full-20260813-r3 | 2026-08-13T06:49:15Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260813-r3) |
| qwen | Qwen Code dsw-eas-full-20260813-r1 | 2026-08-13T06:35:33Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-full-20260813-r1) |
| qwen | Qwen Code dsw-eas-tb-e2e-20260814-r5 | 2026-08-14T06:42:58Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-e2e-20260814-r5) |
| qwen | Qwen Code dsw-eas-tb-e2e-20260814-r4 | 2026-08-14T06:33:48Z | CI/test/benchmark/screenshot assets; not a product version [Source](https://github.com/QwenLM/qwen-code/releases/tag/dsw-eas-tb-e2e-20260814-r4) |
| nemo_megatron | NemoClaw ci-native-podman-e2e-2026-10-01 | 2026-10-01T08:06:28Z | Pinned CI toolchains; not a NemoClaw product release [Source](https://github.com/NVIDIA/NemoClaw/releases/tag/ci-native-podman-e2e-2026-10-01) |
| qwen | Qwen3.8 Max open weights  | 2026-08-12 | Outside the selected sixty-day date range. [Source](https://github.com/QwenLM/Qwen3.8#news) |
| minimax | MiniMax Speech 2.8  | 2026-01-23 | Existing model appears in current navigation; original publisher date is outside the window. [Source](https://www.minimax.io/news/minimax-speech-28) |
| moonshot_kimi | Kimi K3 named launch / weights  | 2026-07-16 / 2026-07-27 | Both milestones predate the window. Keep Kimi Code software releases separate. [Source](https://github.com/MoonshotAI/kimi-help-center/blob/master/en-US/agent/overview.md) |
| glm | GLM5.2  | 2026-06-16 | Outside the window; third-party products using GLM5.2 are not a new GLM5.2 release. [Source](https://z.ai/blog/glm-5.2) |
| mistral | Shieldstral / Leanstral1.5 / OCR4  | 2026-08-04 / 2026-07-02 / 2026-06-23 | Original dates outside window; latest mentions are not new launches. [Source](https://mistral.ai/news) |
| nemo_megatron | Nemotron3NanoOmni / Nemotron3Ultra / Lightning3.5  | 2026-04-28 / 2026-06-04 / 2026-08-11 | Existing models; later tutorials are not initial model releases. Additional weight variants need their own evidence. [Source](https://blogs.nvidia.com/blog/author/karibriski/) |
| outside_scope | Union Alpha / Pareto  | — | Platform states reveal as Pareto by Unbiased, outside the twelve requested company owners. Community Qwen speculation is not attribution. [Source](https://openrouter.ai/stealth/ox-alpha) |

## Method and receipts

The session used Firecrawl search/scrape at concurrency two, then primary web
reader fallbacks for empty, unavailable or unhelpful page extractions. It
performed 22 search attempts (two throttled) and 48 scrape attempts including
one setup check. Search launches were subsequently paced seven seconds apart.
The observed credit balance moved from 639 to 553: an 86-credit balance delta,
within the planned 96-credit ceiling. This is observed account balance, not an
independent per-request billing reconciliation.

Public metadata checks used 23 GitHub REST reads and 12 HF commit/tree reads,
with two SDK-source reads to verify the Hub endpoints. No SDK was installed,
repository code executed, weights downloaded or inference called.

A broad read-only production quote/announcement query hit its 15-second
statement cap. A narrower indexed official-account query succeeded, examining
the latest 500 stored posts for five source-qualified handles and returning
47 text matches. It supplies six canonical source-post milestones. This capped
lookup is source evidence, not complete official-account recall or a review
of all release-tagged posts. Original fetched_at values remain in the JSON.

Ignored raw receipts and local reconstruction inputs: .firecrawl/2026-10-12-093516-g3-sixty-day-product-releases/.
Source revision: 7c426c3a4d76630b17243ac5b8a3451d77efab74; assembled 2026-10-12T01:05:02+00:00.
Every dated row carries a public source URL and local receipt path in the JSON.
The source ledger hashes each receipt; source pages can change later.

Verification covers exact twelve-company scope, date bounds and precision,
proposed kind vocabulary, unique event IDs, consistent JSON/CSV/Markdown counts,
pending/excluded separation, source receipt existence, local links and whitespace.
It does not establish complete release recall, production import, product
classification accuracy, first-public visibility of artifact revisions, or
new runtime behavior.

## Next product work

Use this same inventory to compare expected milestones against stored source
posts and ModelRelease/Evidence. Keep missing capture, failed extraction,
incorrect product/owner/category, duplicate recaps and unknown dates distinct.
Bind anonymous aliases and staged release dates without rewriting immutable
past evidence or pretending an earlier prediction knew a later identity.

Add the five product categories through the existing Product ownership and
review paths. Separate model, task-running agent and reusable harness; preserve
subtypes and developer versus host identity. Migrations, reclassification and
historical collection repair need their own concrete implementation scope.
