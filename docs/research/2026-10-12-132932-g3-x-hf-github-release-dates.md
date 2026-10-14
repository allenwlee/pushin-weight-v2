---
date: 2026-10-12
analysis_only: true
status: verified-date-comparison-with-explicit-gaps
---

# X announcements, first HF records and GitHub repository creation

The owner selects these three date columns. They describe different events. The table uses UTC calendar dates; JSON/CSV retain exact timestamps and repository identities. It covers 19 official HF repositories representing 17 of the 43 proposed model groups in the saved sixty-day inventory. The other 26 groups are listed below, without invented repository dates. Siblings with separate HF repositories have separate rows. This is a bounded comparison, not a complete company release census.

The release inventory remains August 13–October 12,2026. Earlier X announcements and earlier repository records remain in this table because they belong to an in-window product/milestone. Dates are not clipped to the inventory window.

[CSV](2026-10-12-132932-g3-x-hf-github-release-dates.csv) · [Exact timestamps and coverage JSON](2026-10-12-132932-g3-x-hf-github-release-dates.json) · [Original inventory](2026-10-12-093516-g3-sixty-day-product-releases.md)

## Requested comparison

| Model | Release announcement on X | First HF upload recording | GH repo creation date |
| --- | --- | --- | --- |
| MiniMax Music 3 | [2026-08-13](https://x.com/MiniMax_AI/status/2087934657354678421) | [2026-08-07](https://huggingface.co/MiniMaxAI/MiniMax-Music3/commit/412039c64e9e2db3f77fd5bdbfb78a30bf7246d7) * | [2026-08-11](https://api.github.com/repos/MiniMax-AI/MiniMax-Music3) |
| Qwen3.8-27B | [2026-08-03](https://x.com/Alibaba_Qwen/status/2084100707423289643) | [2026-08-05](https://huggingface.co/Qwen/Qwen3.8-27B/commit/6714f561f4c678235aa4780ba4fb904d99a3cca8) * | [2025-09-11](https://api.github.com/repos/QwenLM/Qwen3.8) † |
| GLM-5.3 | [2026-08-14](https://x.com/Zai_org/status/2088132965922476159) | [2026-08-27](https://huggingface.co/zai-org/GLM-5.3/commit/7cda81930d6e4cef42f48555de830aa32ecdde28) | [2026-02-09](https://api.github.com/repos/zai-org/GLM-5) † |
| GLM-5.3-Flash | [2026-08-26](https://x.com/Zai_org/status/2092616204787626030) | [2026-08-25](https://huggingface.co/zai-org/GLM-5.3-Flash/commit/3c7f1b4d38ec8f6eda3b1ca5536b987443e77a72) * | [2026-02-09](https://api.github.com/repos/zai-org/GLM-5) † |
| Qwen3.8-Flash-Next | [2026-08-26](https://x.com/Alibaba_Qwen/status/2092591393424515114) | [2026-08-26](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/commit/34567a4712bc9766c4449e2e98e4468bfa24d915) | [2026-08-24](https://api.github.com/repos/QwenLM/Qwen3.8-Flash-Next) |
| Tencent Hy4 Preview | [2026-08-28](https://x.com/TencentHunyuan/status/2093222928720761009) | [2026-08-27](https://huggingface.co/tencent/Hy4-preview/commit/7a996c909e3974958a0ef8fde0f1acf797a340d4) * | [2026-08-27](https://api.github.com/repos/Tencent-Hunyuan/Hy4-preview) |
| Ling-3.0-flash-Fin | [2026-08-27](https://x.com/AntLingAGI/status/2093022087069958492) | [2026-09-03](https://huggingface.co/inclusionAI/Ling-3.0-flash-Fin/commit/76ccf8ef58adeb1256f272e1a8188691d06cbf69) * | Unverified |
| LLaDA-Image | [2026-09-04](https://x.com/TheInclusionAI/status/2095696902004293744) | [2026-08-28](https://huggingface.co/inclusionAI/LLaDA-Image/commit/778e4747cb0602989f81c77c7b2c2e08f7daaa94) * | [2026-08-31](https://api.github.com/repos/inclusionAI/LLaDA-Image) † |
| LLaDA-Image-Turbo | [2026-09-04](https://x.com/TheInclusionAI/status/2095696902004293744) | [2026-08-28](https://huggingface.co/inclusionAI/LLaDA-Image-Turbo/commit/d92973b6dd6827138d6f4c2e92e320ec63b96255) * | [2026-08-31](https://api.github.com/repos/inclusionAI/LLaDA-Image) † |
| Ling-3.0-flash-VL | [2026-09-04](https://x.com/AntLingAGI/status/2095935971556782372) | [2026-09-04](https://huggingface.co/inclusionAI/Ling-3.0-flash-VL/commit/967ddce37cbe52cf016ad88fdb5d3d3e10e1a944) * | [2026-07-13](https://api.github.com/repos/inclusionAI/vllm-ling-v3) † |
| LLaDA-UI | Unverified | [2026-09-15](https://huggingface.co/inclusionAI/LLaDA-UI/commit/f9a59c1945fc4de68f4bd667b49001cba4a1d954) | [2026-08-31](https://api.github.com/repos/inclusionAI/LLaDA-UI) |
| Ming-Image-0.1-Design | [2026-09-22](https://x.com/AntLingAGI/status/2102452045374804304) | [2026-09-17](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design/commit/9fa3680951ae3fcc2e4c3eda3e4c974dcee22193) * | [2026-09-17](https://api.github.com/repos/inclusionAI/Ming-Image) † |
| Ming-Image-0.1-Design-Layer | [2026-09-22](https://x.com/AntLingAGI/status/2102452045374804304) | [2026-09-17](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer/commit/4002eb32d518a95231872c3925540757156cfb0b) * | [2026-09-17](https://api.github.com/repos/inclusionAI/Ming-Image) † |
| Qwen-Image-2.1 | [2026-09-20](https://x.com/Alibaba_Qwen/status/2101659302792679789) | [2026-09-14](https://huggingface.co/Qwen/Qwen-Image-2.1/commit/b0231bd097b5a2a1cde49a18de703e069d59173d) * | [2026-09-14](https://api.github.com/repos/QwenLM/Qwen-Image-2.1) † |
| MiMo-V2.6-Pro | [2026-09-21](https://x.com/XiaomiMiMo/status/2102138559952290106) | [2026-09-21](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL/commit/c25d97fc71b84c5e6f54a0118a408a634518132f) * | [2025-04-26](https://api.github.com/repos/XiaomiMiMo/MiMo) † |
| MiMo-V2.6-Flash | [2026-09-21](https://x.com/XiaomiMiMo/status/2102138559952290106) | [2026-09-21](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL/commit/990f1a0367298a1190b23a857d5c2b32b3ded88d) * | [2025-04-26](https://api.github.com/repos/XiaomiMiMo/MiMo) † |
| Qwen-Image-2.1-Turbo | [2026-10-09](https://x.com/Alibaba_Qwen/status/2108549075218120949) | [2026-10-09](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo/commit/960b2c791307726231582cf30bf53e980d62092c) * | [2026-09-14](https://api.github.com/repos/QwenLM/Qwen-Image-2.1) † |
| DeepSeek-V4.1-Flash | [2026-09-10](https://x.com/deepseek_ai/status/2097930608790167907) | [2026-09-10](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/commit/3fb9e068ecccc269ec94182be261cc9e4fa34048) * | [2026-09-10](https://api.github.com/repos/deepseek-ai/deepseek-recipe) † |
| DeepSeek-V4-Pro / 0813 API update | [2026-08-13](https://x.com/deepseek_ai/status/2087864585504305397) | [2026-04-22](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro/commit/244d0147232ffc100062c94d37df5ae47a75cccd) * (family repo) | Unverified |

\* Initial recorded revision contains no recognized weight files. It contains setup/model-card/configuration files. This column deliberately records the earliest repository history, rather than silently replacing it with a later weights upload.

† GitHub repository is shared across model generations/variants, or is supporting runtime/recipe code. Its creation does not date the specific model. Ling VL uses the publisher-linked vLLM runtime; DeepSeek V4.1 uses preprocessing/prompt recipes. DeepSeek Pro’s April HF date is a family-repository record, not a verified August 13 checkpoint upload. Unverified means no qualified mapping/date was established, not proof that none exists.

## How the dates were found

X dates come from original publisher posts stored in production. One read-only, uncapped export selected official author accounts over July 15–October 12: 1,494 posts from 24 registered accounts. No paid X provider call was made. These are verified announcements found in our retained evidence; incomplete historical harvesting means they cannot certify the first announcement anywhere on X. Qwen 27B’s August 3 post explicitly preannounces the model; August 14 is its weights launch.

HF dates come from the repository commit-history API. Pagination was checked; all 19 inspected histories reached the oldest available record. Five complete prior responses were reused, and 14 histories fetched. The file-tree API was queried at each initial revision, reading file names and metadata without downloading weights. Sixteen initial revisions contain only setup/metadata files; GLM 5.3, Qwen Flash Next and LLaDA UI already contain weight files. Current history may have been imported or rewritten: the earliest recorded commit is not a guaranteed server upload time or historical public-access timestamp. The [official commit-history documentation](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api#huggingface_hub.HfApi.list_repo_commits) describes newest-first records. HF [repository visibility](https://huggingface.co/docs/hub/en/repositories-settings) can change separately.

GitHub dates come directly from created_at in the [repository REST API](https://docs.github.com/en/rest/repos/repos#get-a-repository). Twelve publisher-linked repositories were inspected; shared identities were queried once. Mappings come from publisher model cards, their code links and the previously verified Qwen family README. Dependency repositories and DeepSeek’s reused V2 logo URL were rejected as model-repository evidence. Four guessed dedicated model/family URLs returned 404; those are failed checks rather than dates. GitHub Release published_at is a separate field and was not used here.

## Current HF collection, verified separately

Production was inspected read-only at 2026-10-12T04:50:41.66726+00:00. The active HF contract collects downloads (rolling 30 days), downloads_all_time when supplied, model likes and publisher followers. Its exact scope is deepseek-ai/DeepSeek-V4.1-Flash and zai-org/GLM-5.3-Flash, plus the deepseek-ai and zai-org publisher accounts. The HF source is enabled with daily_collection_hour_utc=10, meaning 19:00 JST. Recent successful daily runs are October 9, 10 and 11 at approximately 10:01 UTC, each 4/4 selected identities successful. October 12’s daily slot has not yet arrived at this observation.

The due checker runs hourly, but that does not make HF polling hourly. OpenRouter and Arena are also configured daily; OpenCode is approximately hourly. The modern rich catalog importer is manual and separate. Its latest retained runs are September 24; a partial run is retained explicitly. Current scheduler configuration is not a commit/file-upload watcher or an automatic census of all tracked publishers’ repositories. Announcement-triggered exact-HF-link verification is another scoped path; it does not supply continuous repository history.

Current source code was inspected at origin/main fd467363, including core/hf_metadata_client.py, core/benchmark_metric_operations.py, monitor/management/commands/collect_benchmark_due.py, monitor/management/commands/collect_benchmark_metrics.py and scripts/benchmark_download_collector/sources.py. The retained G3/root checkouts lack some subsequently deployed benchmark code; their older file lists were not used to claim the live collector is absent. HF [download-count methodology](https://huggingface.co/docs/hub/en/models-download-stats) distinguishes counted file requests from unique users; the daily change in a rolling counter is not directly daily new downloads.

## Other saved model groups without a reviewed three-date mapping

These remain in the frozen inventory and database audit. Most represent API/platform/regional milestones or pending future weights. No missing cell implies nonexistence. The comparative table does not silently turn an API launch into a weight release.

| Owner | Product / version | Three-date status |
| --- | --- | --- |
| qwen | Wan Video Prime 3.0 | Not established in this pass |
| deepseek | DeepSeek V4 Flash Vision Exp Vision-Exp | Not established in this pass |
| qwen | Qwen3.8 Flash 3.8 | Not established in this pass |
| qwen | Qwen MT Image 2.0 | Not established in this pass |
| qwen | Qwen Flash Character  | Not established in this pass |
| llama | Muse Spark 1.3 | Not established in this pass |
| qwen | Qwen Drive 1.0 | Not established in this pass |
| qwen | Qwen3.8 Max 0902 | Not established in this pass |
| inclusionai | Ling Flash Sante 3.0 | Not established in this pass |
| stepfun | StepAudio 3 | Not established in this pass |
| qwen | HappyOyster 1.0 | Not established in this pass |
| qwen | Qwen3.8 Omni Flash 3.8 | Not established in this pass |
| qwen | Qwen3.8 LiveTranslate 3.8 | Not established in this pass |
| qwen | Qwen Audio Realtime Plus 3.1 | Not established in this pass |
| stepfun | Step 5 Preview 5 | Not established in this pass |
| hunyuan | Tencent Hy Image 3.5 Preview | Not established in this pass |
| qwen | Qwen3.8 Omni Flash Realtime 3.8 | Not established in this pass |
| mimo | MiMo V2.6 Pro UltraSpeed 2.6 | Not established in this pass |
| nemo_megatron | NV Reason CT  | Not established in this pass |
| qwen | Alibaba Decision Model Preview | Not established in this pass |
| minimax | MiniMax M3.1 Flash Preview 3.1 | Not established in this pass |
| inclusionai | Ling Flash 3.1 | Not established in this pass |
| qwen | Qwen Image Pro 2.1 | Not established in this pass |
| mistral | Mistral Large 4 | Not established in this pass |
| qwen | Qwen3.7 Flash 3.7 | Not established in this pass |
| qwen | Qwen3.8 Max 3.8 | Not established in this pass |

## Scope and retained evidence

Private receipts and original public source responses are retained under .context/g3-announcement-weight-dates-2026-10-12-132932/; previous full HF histories remain under .firecrawl/2026-10-12-093516-g3-sixty-day-product-releases/. One corrected read-only measurement query follows an initial schema-column error; only the corrected committed result supports the collection findings. No production records, collector configuration, code, scheduler or deployment changed. No weights, models or inference were downloaded/run.

Checks reconcile every displayed row to a frozen model-group identity, publisher post timestamp, complete HF history and initial file tree; mapped GitHub created_at values match saved API responses. Model-group coverage sums to 43. CSV/JSON/model identities and all dates agree. These checks qualify the requested date meanings, not historical public visibility or universal release recall.
