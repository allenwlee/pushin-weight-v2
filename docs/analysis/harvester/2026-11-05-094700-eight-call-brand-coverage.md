# Applied query coverage: fixed twelve-hour DB replay

**Applied locally, not deployed. Zero provider calls.** Same 8,281-post window: Nov 4 22:00 → Nov 5 10:00 JST. **8,190/8,281 posts match (98.9%)** using keyword calls plus current persisted Call A membership.

The corrected baseline matches 8,182 posts. The applied queries recover **eight additional relevant posts**, with **zero lost matches**. Earlier reports said 8,181; one extra baseline match comes from fixing circled-number normalization (`④Muse`), and is not counted as a query gain.

| Brand | DB posts | Baseline caught | Applied caught | Applied % |
|---|---:|---:|---:|---:|
| DeepSeek | 1,873 | 1,821 | 1,822 | 97.3% |
| Dots | 2 | 2 | 2 | 100.0% |
| ByteDance / Doubao | 84 | 83 | 84 | 100.0% |
| ERNIE | 6 | 6 | 6 | 100.0% |
| EXAONE | 1 | 1 | 1 | 100.0% |
| GLM | 350 | 350 | 350 | 100.0% |
| Hunyuan | 694 | 694 | 694 | 100.0% |
| InclusionAI | 13 | 12 | 12 | 92.3% |
| Kuaishou / Kling | 5 | 5 | 5 | 100.0% |
| Meta / Llama | 3,903 | 3,899 | 3,901 | 99.9% |
| MiMo | 34 | 34 | 34 | 100.0% |
| MiniMax | 429 | 401 | 403 | 93.9% |
| Mistral | 98 | 98 | 98 | 100.0% |
| Kimi | 716 | 713 | 716 | 100.0% |
| NVIDIA | 51 | 51 | 51 | 100.0% |
| Qwen | 928 | 927 | 928 | 100.0% |
| Sakana AI | 0 | 0 | 0 | — |
| SenseTime | 4 | 4 | 4 | 100.0% |
| StepFun | 6 | 6 | 6 | 100.0% |
| Upstage | 23 | 21 | 21 | 91.3% |
| Yi | 9 | 9 | 9 | 100.0% |

## Applied changes and ownership

- Qwen: add 千问.
- ByteDance: add 字节扣子 and Coze. The demonstrated incremental hit uses 字节扣子.
- Kimi: add Moonshot with AI/LLM/model/API/tokens/weights/模型/参数 context; preserve independent existing aliases and handle.
- Meta/Llama: add pretraining to existing Llama context; preserve Meta/Muse context and exclusions.
- DeepSeek: add V4.1F shorthand, covering the stored V4.1F-1017 comparison. Other stored text ties DeepSeek to V4.1 Flash shorthand; this association is dataset-grounded.

All previous query branches remain covered by regression tests. Every brand stays whole, except NVIDIA's existing four named family blocks. The nine-call map below is declared explicitly; runtime never silently repacks it. Call A is unchanged. Maximum complete query size: **511 UTF-8 bytes**, including the active author exclusion and two ten-digit timestamp bounds.

- A: Curated list — curated list; 96 bytes.
- B1: Established AI platforms — llama, sensechat, ernie; 511 bytes.
- C1: NVIDIA models and technical AI stack — nemo_megatron/models, nemo_megatron/software; 489 bytes.
- C2: NVIDIA company and product names — nemo_megatron/company, nemo_megatron/product-names; 319 bytes.
- C3: General-purpose model platforms — minimax, qwen, deepseek, glm, yi; 476 bytes.
- C4: Chinese social-platform model labs — hunyuan, dots; 460 bytes.
- B2: Independent model research labs — mistral, sakana_ai, stepfun; 511 bytes.
- B3: Asian model studios — moonshot_kimi, inclusionai, upstage, kuaishou; 511 bytes.
- B4: Consumer-platform AI portfolios — mimo, doubao, exaone; 501 bytes.

## Eight new query matches

- [2118088333087879494](https://x.com/i/status/2118088333087879494) — stored labels: moonshot_kimi; @testingcatalog Model card numbers: 2.8T total params, 104B active per token, 896 experts with 16 picked per token, 1M context. The weights are ~1.56 
- [2118065745951109156](https://x.com/i/status/2118065745951109156) — stored labels: moonshot_kimi; 能力账（均为 Moonshot 自报，对比 Claude Opus 5.5）： Terminal-Bench 4.0：65.7% vs 66.4% SWE-Marathon：51.7% vs 46.3% HLE-Diamond：39.4% vs 60.9%  API 每百万 token $2 输入 
- [2118044670588514575](https://x.com/i/status/2118044670588514575) — stored labels: llama; Cohere: embedding random init &gt;&gt;&gt; synthetic pretraining on non-language processes like NCA. Hutter is wrong! Even with continued admixture of
- [2118044349581967748](https://x.com/i/status/2118044349581967748) — stored labels: llama; Cohere: embedding random init &gt;&gt;&gt; synthetic pretraining on non-language processes like NCA. Hutter is wrong! The reasonable ablation here wou
- [2118029506745127284](https://x.com/i/status/2118029506745127284) — stored labels: moonshot_kimi; At launch it sat #4 on Artificial Analysis (55), and AA projected it would become the top open-weight model on its index once weights shipped.  Not MI
- [2118026809984090238](https://x.com/i/status/2118026809984090238) — stored labels: minimax, qwen; 苹果国行AI牵手千问落地 刚看到苹果在中国推 Apple Intelligence 的消息，第一反应是这一天终于来了，但合作方是阿里千问而不是自研模型落地，这个信号比功能本身更值得琢磨。开发者 Beta 已经能测，正式版要等 12 月随系统更新推送，节奏上算是稳扎稳打。 首批功能清单拉出来看，实时翻
- [2118026642358735295](https://x.com/i/status/2118026642358735295) — stored labels: deepseek; I approve of AA and other evals that show V4.1F-1017 losing to Haiku or Luna. That's fair. On those evals. However, it is a vastly superior model. Hai
- [2117992594064167007](https://x.com/i/status/2117992594064167007) — stored labels: doubao, minimax; 字节扣子企业版分阶段停售、下线。  官方公告：企业标准版、旗舰版本月底起停新售；火山引擎旧版套餐年底全面下线，未用完自动退回账户；新版企业套餐最晚用到后年年底。对话、工作流等资源怎么导出，写的是「后续公告」。  腾讯元器本月上旬停服，存量智能体不可用，另给导出过渡期和云上替代方案。  大厂智能体平台

## Remaining misses and scope

Ninety-one unique posts remain unmatched. Apparent stored label errors dominate tracked-brand misses: DeepSeek has 42 TRON promotions among its 51 misses; MiniMax has 21 among its 26. Two Meta misses refer to Launch Llama and a paper named Meta², not clear Meta/Llama model references. Upstage's two misses concern the solar system/solar stocks; InclusionAI's one concerns generic inclusion. Other saved content and unavailable thread/article/image context are not grounds for inventing aliases. Existing labels were not changed and no adjusted “100% relevance” denominator is claimed.

Twenty-three fully unattributed posts remain unmatched. The prior two relevant unassigned NVIDIA posts remain caught. The earlier 626 candidate missing-brand associations are a separate, unvalidated candidate audit from the prior query version; they were not imported as labels.

Call A uses current persisted membership, not historical reconstruction: 213 active rows, 210 usable handles. A separate read-only DB identity check found no window posts for the three members without handles. Keyword evaluation uses stored text, quotes, explicit mentions and observed expanded URL paths. X indexing, pagination, image text, article contents and unseen thread context are not simulated. This measures the fixed DB cohort, not all relevant posts on X.

## Verification and receipts

**496 checks pass: 364 local/pure and 132 database/backfill checks; 91 require PostgreSQL, with zero skips/errors.** Covers preserved branches, new positive/negative aliases, ungated handles, contexts, byte limits at transport, whole-brand ownership, scheduled/backfill persistence, saved historical recipes and cursor/dedup behavior. Shared permanent test DB only; no schema migration, reset or restore. Four hash-verified migration-discovery overlays were removed after testing.

Full offline output, per-post matched call IDs, all missed IDs and input hashes: `applied-final/replay/results.json`. Corrected baseline: `applied-final/baseline-corrected/results.json`. Exact gained IDs and zero-loss comparison: `applied-final/comparison.json`. The root is `/Users/fuchitalee/development/pushin-weight-v2/data/runs/2026-11-05-102849-locked-12h-portfolio-audit`.

A prior read-only production enrichment cohort remains an unrelated, previously observed unhealthy finding: 20/20 missing commentary; candidate undeployed. Its original receipts are retained in `data/runs/2026-11-05-091322-harvest-eight-call-coverage/production-health-{initial,final}.json`; no new provider/enrichment run or production repair was performed.

## Exact applied queries

### A

```text
(list:2067062923525275922) min_faves:0 -from:xxyweb3
```

### B1

```text
("Muse Image" OR "Muse Video" OR "Muse Voice" OR Llama (llm OR model OR api OR agentic OR huggingface OR pretraining) OR (Meta OR Muse) (AI OR model OR models OR agent OR agents OR code OR Wonder OR Spark OR Glimmer OR research OR release OR 模型 OR 智能体 OR トークン) OR @AIatMeta OR SenseChat OR SenseTime OR SenseNova OR 商汤 OR 日日新 OR @SenseTime_AI OR ERNIE OR 文心一言 OR 文心 OR PaddleOCR OR @ErnieforDevs OR @PaddlePaddle) -from:xxyweb3
```

### C1

```text
(NeMo OR Megatron OR Nemotron OR Alpamayo OR BioNeMo OR NemoClaw OR GR00T OR TensorRT OR TRT-LLM OR Parakeet OR Canary OR Audio2Face OR DLSS OR NV-Embed OR NV-CLIP OR NemoGuard OR NVLM OR CUDA OR cuDNN OR CUTLASS OR NCCL OR RAPIDS OR cuML OR cuDF OR cuVS OR DeepStream OR Holoscan OR Omniverse OR PhysicsNeMo OR Earth-2 OR CorrDiff OR FourCastNet OR MONAI OR Auto-Ontology OR AI-Q OR Garak OR cuOpt OR cuGraph OR Jetson OR JetPack) -from:xxyweb3
```

### C2

```text
(NVIDIA OR 英伟达 OR 輝達 OR 英偉達 OR エヌビディア OR @NVIDIAAI OR @NVIDIAAIDev OR Cosmos OR Isaac OR NIM OR Riva OR Dynamo OR Triton OR Eagle OR TAO OR Morpheus OR Merlin OR Maxine OR Modulus OR Clara OR Ising OR ACE OR Tokkio OR Edify OR DRIVE) -from:xxyweb3
```

### C3

```text
(Hailuo OR MiniMax OR 海螺 (AI OR 模型 OR H3 OR 歌曲) OR @MiniMaxAgent OR @MiniMax_AI OR @hailuo_ai OR Qwen OR Qwen3 OR 通义千问 OR 千问 OR @Ali_TongyiLab OR @Alibaba_Qwen OR DeepSeek OR 深度求索 OR V4.1F OR @deepseek_ai OR OxAlpha OR ox-alpha OR (glm OR ChatGLM OR Zhipu OR 智谱 OR Z.ai) (llm OR model OR api OR agentic OR huggingface) OR Yi OR 01.AI OR 零一万物 OR 万智 OR Wanzhi OR @01AI_Yi) -from:xxyweb3
```

### C4

```text
(Hunyuan OR Hunyuan4 OR 腾讯混元 OR Hunyuan3D OR HunyuanVideo OR HunyuanImage OR Hy-MT2 OR Hy-Memory OR HY-World OR 混元3 OR 混元4 OR 混元5 OR Hy3 OR Hy4 OR Hy5 OR 混元 (AI OR 模型 OR 3D OR 腾讯) OR @TencentHunyuan OR dots studio OR "dots 3 note" OR "dots.3-note" OR dots.ocr OR dots.tts OR dots.llm1 OR dots.vlm OR dots.mocr OR DotsOCR OR "dots OCR" OR dots3 OR dots4 OR @dotsstudioai) -from:xxyweb3
```

### B2

```text
(Mistral OR Mixtral OR Codestral OR Devstral OR Voxtral OR Magistral OR Ministral OR Pixtral OR Mathstral OR Leanstral OR LIDstral OR Timestral OR @MistralAI OR Sakana OR SakanaAI OR SakanaAILabs OR サカナAI OR Namazu OR ShinkaEvolve OR "AI Scientist" OR "Darwin Gödel Machine" OR @SakanaAILabs OR StepFun OR 阶跃星辰 OR Step-5 OR Step5 OR Step-3.5-Flash OR "Step 3.7 Flash" OR StepAudio OR Step-Audio OR Step-Video OR @StepFun_ai OR @stepfunai) -from:xxyweb3
```

### B3

```text
(Kimi OR 月之暗面 OR 暗面 OR MoonshotAI OR K2 OR K3 OR Kimi3 OR Moonshot (AI OR LLM OR model OR API OR tokens OR weights OR 模型 OR 参数) OR @Kimi_Moonshot OR InclusionAI OR Ling OR Ring OR Ming OR @AntLingAGI OR @TheInclusionAI OR @ZhihuFrontier OR @robbyant_brain OR Upstage OR Solar Pro OR Solar LLM OR 업스테이지 OR "Solar Open" OR "Solar Mini" OR @upstageai OR Kuaishou OR KwaiYii OR Kling OR 可灵 OR 可靈 OR 快手 OR @Kling_ai) -from:xxyweb3
```

### B4

```text
(MiMo OR (Xiaomi OR 小米) (AI OR LLM OR model OR models OR agent OR agents OR 模型 OR 大模型 OR 人工智能 OR 智能体) OR @XiaomiMiMo OR @XiaomiMiMoDevs OR Doubao OR ByteDance OR 豆包 OR 字节跳动 OR Seedance OR Seedream OR Seed2.1 OR SeedRealtime OR "Seed Audio" OR SeedAudio OR "Seed Diffusion" OR SeedDiffusion OR 字节扣子 OR Coze OR @BytePlusGlobal OR @bytedanceoss OR @doubaoai OR EXAONE OR "LG AI" OR @LG_AI_Research) -from:xxyweb3
```


## Existing brand counts versus total potential matches

Same fixed twelve-hour DB cohort, applied final queries including Call A. “Extra” means stored posts lacking this particular brand label, not newly fetched posts outside the database. Extras are raw candidates and include false positives. “Potential total” sums caught existing brand rows plus disjoint extra candidates; it is not a validated relevance count. Entirely absent-from-DB posts cannot be measured by this offline test.

| Brand | Already tagged in DB | Existing caught | Extra candidates | Potential total |
|---|---:|---:|---:|---:|
| DeepSeek | 1873 | 1822 | 23 | 1845 |
| Dots | 2 | 2 | 3 | 5 |
| ByteDance / Doubao | 84 | 84 | 26 | 110 |
| ERNIE | 6 | 6 | 2 | 8 |
| EXAONE | 1 | 1 | 0 | 1 |
| GLM | 350 | 350 | 5 | 355 |
| Hunyuan | 694 | 694 | 12 | 706 |
| InclusionAI | 13 | 12 | 0 | 12 |
| Kuaishou / Kling | 5 | 5 | 19 | 24 |
| Meta / Llama | 3903 | 3901 | 5 | 3906 |
| MiMo | 34 | 34 | 2 | 36 |
| MiniMax | 429 | 403 | 3 | 406 |
| Mistral | 98 | 98 | 13 | 111 |
| Kimi | 716 | 716 | 22 | 738 |
| NVIDIA | 51 | 51 | 410 | 461 |
| Qwen | 928 | 928 | 15 | 943 |
| Sakana AI | 0 | 0 | 4 | 4 |
| SenseTime | 4 | 4 | 0 | 4 |
| StepFun | 6 | 6 | 61 | 67 |
| Upstage | 23 | 21 | 0 | 21 |
| Yi | 9 | 9 | 1 | 10 |

Extra candidates:626brand/post pairs on579unique stored posts; two were fully unassigned NVIDIA posts. Brand totals overlap. All raw candidate IDs and source text are in applied-final/new-label-audit/results.json. Joined table is recorded in applied-final/brand-comparison.{json,csv}. No provider calls or DB writes.


## Extra candidates as percentage of existing DB brand count

Formula: additional candidates / existing DB-tagged posts ×100. These are potential increases, not reviewed relevance rates. Zero baselines have no defined percentage.

| Brand | Extra candidates | Extra / DB tagged |
|---|---:|---:|
| DeepSeek | 23 | 1.2% |
| Dots | 3 | 150.0% |
| ByteDance / Doubao | 26 | 31.0% |
| ERNIE | 2 | 33.3% |
| EXAONE | 0 | 0.0% |
| GLM | 5 | 1.4% |
| Hunyuan | 12 | 1.7% |
| InclusionAI | 0 | 0.0% |
| Kuaishou / Kling | 19 | 380.0% |
| Meta / Llama | 5 | 0.1% |
| MiMo | 2 | 5.9% |
| MiniMax | 3 | 0.7% |
| Mistral | 13 | 13.3% |
| Kimi | 22 | 3.1% |
| NVIDIA | 410 | 803.9% |
| Qwen | 15 | 1.6% |
| Sakana AI | 4 | N/A (zero baseline) |
| SenseTime | 0 | 0.0% |
| StepFun | 61 | 1016.7% |
| Upstage | 0 | 0.0% |
| Yi | 1 | 11.1% |
