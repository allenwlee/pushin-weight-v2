# Source-only reference review: zh-cn

Stored classifier assignments and Jev results are deliberately absent.

## zh_cn_01 — target qwen — natural
Post: 2101132893225656517 | @ScarletKc | other candidates: qwen
Affiliations: []

3/7

那激活参数呢？

它反映的是处理一个 token 时，实际参与计算的参数规模，和每一步的计算量联系更直接。

在架构相近的情况下，更多激活参数通常意味着这一步要经过更多权重运算，也给模型提供了更大的计算能力。具体能发挥成什么水平，还要看这些权重怎么训练、网络怎么组织。

MoE 的特殊之处就在这里。模型拥有一大批参数，每一步按路由使用其中一部分。

拿 Qwen3-30B-A3B 举例，总参数约 30B，每个 token 激活约 3B。模型能够根据输入，从更大的参数集合中选择当前使用的部分，下一步又可能换一组。

所以拿它和一个 3B Dense 比，光看每步激活的数字，会漏掉背后那一整套可供选择的参数。拿它和一个 30B Dense 比，又会漏掉每一步参与计算的规模差异。

总参数和激活参数要放在一起理解。知识、语言理解和推理，都需要这些权重共同参与，很难分别归给其中某一个数字。

Stored English translation:
3/7 What about activated parameters? They reflect the parameter scale that actually participates in computation when processing a token, and tie more directly to the compute per step. With similar architectures, more activated parameters usually means more weight operations per step and gives the model more compute capacity. How concretely it performs depends on how those weights are trained and how the network is organized. This is where MoE is special. The model has a large pool of parameters, and each step routes through a subset of them. Take Qwen3-30B-A3B as an example: total parameters around 30B, each token activates around 3B. The model can pick, based on input, which subset to use now, and may switch to another set next step. So comparing it to a 3B Dense, just looking at the per-step activation number misses the whole pool of selectable parameters behind it. Comparing it to a 30B Dense misses the per-step compute difference. Total parameters and activated parameters should be understood together. Knowledge, language understanding, and reasoning all need these weights working together; it's hard to attribute them to any single number.

## zh_cn_02 — target minimax — natural
Post: 2098964592680731131 | @wugudehaore | other candidates: minimax
Affiliations: []

#Minimax  上市后最高市值4000亿港币。初始只有5.4%的股票流通。现在有部分股票解禁流通。看跌。图二分享下跌目标。 https://t.co/DgtgEpIZxN

Stored English translation:
#Minimax peaked at HK$400 billion market cap after IPO, with only 5.4% of shares initially circulating. Now some lock-up shares are unlocking. Bearish. Figure 2 shares the downside target. https://t.co/DgtgEpIZxN

## zh_cn_03 — target deepseek — natural
Post: 2095452004709732479 | @vintcessun | other candidates: deepseek, minimax
Affiliations: []

一次跑通只是轨迹；能换智能体、换容器复现，才配叫 skill。

https://t.co/YFIFDV2VO5

reSolve 把指令、资源与入口封装成技能包，再由不共享原轨迹的新智能体复现。看不到隐藏 grader 时，用 surrogate verifier 提供稠密评分和失败描述，再以 beam search 筛选。SkillsBench 86 题上，DeepSeek-V4-Pro 从人工技能的 60.1% 升至 74.9%；但最大贡献来自人工 anchor，弱模型收益也明显更小。

Stored English translation:
Running once is just a trajectory; only reproducibility across agents and containers deserves the name 'skill'. https://t.co/YFIFDV2VO5 reSolve encapsulates instructions, resources, and entry points as a skill pack, then reproduces it with a new agent that does not share the original trajectory. When the hidden grader is unavailable, a surrogate verifier provides dense scoring and failure descriptions, then beam search is used for selection. On SkillsBench's 86 questions, DeepSeek-V4-Pro rose from 60.1% with human skills to 74.9%; but the largest contribution came from human anchors, and weaker models benefited far less.

## zh_cn_04 — target dots — natural
Post: 2101120516278849859 | @realfxw | other candidates: dots
Affiliations: []

单张 GPU 每天狂刷 50 万页！法国 AI 团队最新发布的 LightOnOCR-2-1B 正在改写文档解析的成本法则：一个仅 1B（10 亿）参数的小模型，直接越级击败了体量为其 9 倍的竞争对手，并把海量文档处理成本拉低到每千页不到 1 美分。

传统 OCR 往往依赖脆弱的多阶段工程流水线（版面切分、文字检测、分块识别再到后处理拼接），任何环节出错都会导致阅读顺序错乱。而该模型采用纯端到端设计，输入任意 PDF、扫描件或照片，模型直出规整、顺序正确的结构化文本。

核心亮点：

极致吞吐与超低成本：单张 H100 跑出 5.71 页/秒的速度，单卡单日吞吐量约 49.3 万页，每千页处理成本低于 $0.01。

越级 SOTA 性能：在 OlmOCR-Bench 基准测试中达到业界领先水准，而体量比同台竞技的竞品小约 9 倍；推理速度相比 Chandra 快 3.3 倍、相比 dots.ocr 快 5 倍、相比 OlmOCR 快 1.7 倍。

复杂版面全兼容：精准处理多栏排版、跨行表格、各类单据与表单，数学公式直接输出规范整洁的 LaTeX 语法。

开箱即用与本地部署：覆盖 11 种语言，原生兼容高吞吐框架 vLLM 与 SGLang，也支持在 Ollama 或 LM Studio 本地轻量运行。

真开源商用：采用宽松的 Apache 2.0 协议，企业二次开发和商业落地全无门槛。

无论是需要清洗海量 PDF 构建 RAG 知识库，还是搭建自动化单据录入管线，这个小钢炮模型都把算力利用率拉到了新高度：https://t.co/RYicLVBm76

Stored English translation:
A single GPU crunches 500,000 pages a day! A French AI team's new LightOnOCR-2-1B is rewriting the cost rules for document parsing: a tiny 1B-parameter model that beats competitors nine times its size and drops mass document processing below one cent per thousand pages. Traditional OCR often relies on brittle multi-stage pipelines (layout segmentation, text detection, chunk recognition, then post-processing stitching), and any broken link scrambles reading order. This model is fully end-to-end: feed it any PDF, scan, or photo and it outputs clean, correctly-ordered structured text. Highlights: extreme throughput and ultra-low cost — 5.71 pages/sec on a single H100, ~493k pages per card per day, under $0.01 per thousand pages. Punching-above-weight SOTA — leading results on OlmOCR-Bench while ~9x smaller than competitors; inference 3.3x faster than Chandra, 5x faster than dots.ocr, 1.7x faster than OlmOCR. Complex layouts fully supported — multi-column text, cross-row tables, documents and forms, math formulas output as clean LaTeX. Ready out of the box and locally deployable — 11 languages, natively compatible with high-throughput vLLM and SGLang, and light local runs on Ollama or LM Studio. Truly open for commercial use — permissive Apache 2.0, no barrier for enterprise secondary development and commercial deployment. Whether cleaning huge PDF corpora for RAG knowledge bases or building automated invoice-entry pipelines, this little powerhouse pushes compute utilization to a new level: [link]

## zh_cn_05 — target minimax — natural
Post: 2096131230765105161 | @HueReasonegfo9 | other candidates: minimax
Affiliations: []

我是小梁我出售最好用的特浓rush一秒上头非常好用各种rush都有原液格兰单瓶固体液体R云九海螺套盒都有来找风风下单
还有艾力达果冻
全国可发
保证最好用的rs
✈️ @rush9817
🐧 3171657054
#rush批发 #伪娘 gay 同性恋 男同 性用品 闻rs 控r 吸rs rs推荐 玩rs rush销售山东省 男大
操0伟哥 夫妻情趣用品 https://t.co/Oy6N3AMSET

Stored English translation:
I am Xiao Liang selling the best strong rush that hits instantly, various types available in raw liquid, granule, single bottles, solid, liquid R, Yunjie, Hailuo combo sets, order from Fengfeng. Also Elida jelly. Nationwide shipping. Guaranteed best rs. ✈️ @rush9817 🐧 3171657054 #rush wholesale #crossdresser gay homosexual male gay sex toys sniff rs control r inhale rs rs recommendation play rs rush sales Shandong province male university. Drug for gay sex, couple's sex toys https://t.co/Oy6N3AMSET

## zh_cn_06 — target minimax — natural
Post: 2085587083029356715 | @ekll01 | other candidates: minimax
Affiliations: []

有不少H3插件不兼容larryvrh/MiniMax-H3-Turbo-Lora · Hugging Face，请注意😂

Stored English translation:
Many H3 plugins are incompatible with larryvrh/MiniMax-H3-Turbo-Lora · Hugging Face, please be aware 😂

## zh_cn_07 — target deepseek — natural
Post: 2094993005170286811 | @YishaoRice | other candidates: deepseek
Affiliations: []

开源小版本更新之后，推理单价为什么又开始往下走

成本曲线才是应用层的硬约束

大模型竞争表面上打参数和榜单，底层约束是单位推理成本。过去两年，开源权重、量化格式、推理框架三条线同时推进，应用团队算账已从「能不能跑」变成「跑一百万 token 要多少钱」。Smol AI 这类聚合源每天跟踪模型发布、压缩技术和 agent 运行时，产业叙事从「谁更强」滑向「谁更便宜、谁能进生产」。对应用层，这条曲线比单次评测更硬：它决定高频调用能不能摊进毛利，也决定试点能不能变成可重复采购。

小版本动到的是工程账单

开源社区某模型小版本更新后，推理单价下行。这类更新通常不抢头条，却会改写真实账单——量化是否更友好、默认推理栈是否更省显存、社区是否同步放出 GGUF/FP8 等可直接部署的权重。

Smol AI 首页近期集中讨论 Ornith 等新开源权重族、多种量化格式，以及 agent 评测与成本效率工具链，与「版本迭代 → 推理更便宜」同向。没有单独一篇 Smol 稿给出「某模型小版本 → 精确降价百分之几」时，长文只能写方向，不能自行填数字。

闭源溢价与开源降本仍在拉开

DailyBrief 语料库中，DW 中文曾报道中国 AI 竞赛升级：研究机构指出 DeepSeek 最新模型的运行成本较 Anthropic Claude Fable 5 低逾百倍。把它与开源推理成本下行放在同一帧，更像结构性现象——闭源旗舰维持高溢价，开源与半开源用工程优化把账单往下拽。阿里巴巴同期发布更大规模模型，也在强化「规模 + 效率」双叙事。

Hugging Face 博客侧同期有 Nunchaku 4-bit 扩散推理、OlmoEarth 地理推理等条目。降本不只发生在文本 LLM，多模态与垂直场景同样在吃量化与专用推理栈的红利。应用团队面对的不是单一模型变便宜，而是整条开源与半开源供给带在压低单位成本；闭源仍可靠效果与合规卖溢价，但价差已成为采购对照表里的一列。

ToB：高频调用先受益，采购卡在三个闸门

单位推理成本下修，最先受益的不是 Demo，而是客服质检、文档抽取、代码辅助、短视频脚本与素材流水线。语料里 MoneyPrinterTurbo 一类项目把「大模型写脚本 + 自动成片」产品化，是把推理成本摊进单次视频生产的毛利模型；Kimi K3 等长上下文模型被写进工作流，是在赌一次调用覆盖更多步骤、减少人工接力。

ToB 落地卡在三个闸门：效果是否稳定、合规是否可审计、单次任务成本是否低于人工替代。小版本若只带来几个百分点的成本下降，可能改不了采购决策；若叠加量化、批处理、专用 runtime（语料中 TrueFoundry 开源 TrueForge 强调 token 与成本优化），会把「试点 → 小规模上线」的窗口往前推。采购节奏更像在等成本曲线拐点，而不是等下一次榜单翻盘。

Stored English translation:
After the open-source minor version update, why is the inference unit price starting to drop again? The cost curve is the hard constraint for the application layer.

## zh_cn_08 — target deepseek — natural
Post: 2086763159180959889 | @LShanrenM | other candidates: deepseek
Affiliations: []

@LuBtc888 我无数次说过:投资是有门槛的

投资是需要能力
投资是需要人才
投资是需要眼光的

中国能有几个沈南鹏 ?

看到国资投资什么 deepseek ,

投资什么

这个AI

那个AI ,烦!

结论就是:一地鸡毛

私人资本都需专业的投资人,国资有能力找到专业的投资人吗? 
你能给人家分配资本吗?

分配任务差不多

## zh_cn_09 — target deepseek — natural
Post: 2094358567365300351 | @yabarich | other candidates: deepseek, glm, mimo
Affiliations: []

🚀 从 210 万到 220 万+：AI 采用正在加速

新增超过 10 万注册用户，代表 https://t.co/9E4zMljHkp 再次完成一项重要增长。

目前平台用户数量已经突破 220 万。全球开发者正在寻找能够同时提供先进模型、可靠 API 与高成本效率的 AI 基础设施，而 https://t.co/9E4zMljHkp 正在将这些能力集中于同一平台。

🤖 多模型访问

用户可以探索 DeepSeek-V4-Flash、Hy3、MiMo-V2.5、GLM-5.3-Flash、Qwen3.8-Flash 等集成模型，而无需被限制在单一技术路径中。

⚡ 高并发基础设施

工业级 API 面向 Agent 应用与生产工作负载，提供低延迟、高吞吐的执行能力。

💳 加密原生成本效率

原生支付方式与可扩展计算调度，为开发者管理模型使用量及部署成本提供更加灵活的路径。

AI 采用的下一阶段，不会只取决于模型是否更强，还需要能够让模型变得容易访问、稳定可靠并具有经济可行性的基础设施。

每一位新增用户，都可能为网络带来一次新实验、一个新应用、一名新 Agent 或一种新想法。

220 万用户是一项里程碑，而更值得期待的是他们接下来会创造什么。

👉 立即开始探索：
https://t.co/Miu0HbV0UT

@BAI_AGI @justinsuntron #TRONEcoStar

Stored English translation:
🚀 From 2.1 million to 2.2 million+: AI adoption is accelerating. Adding over 100K registered users represents another significant growth milestone for https://t.co/9E4zMljHkp. The platform's user count has now surpassed 2.2 million. Global developers are seeking AI infrastructure that simultaneously offers advanced models, reliable APIs, and high cost efficiency, and https://t.co/9E4zMljHkp is concentrating these capabilities on one platform. 🤖 Multi-model access. Users can explore integrated models like DeepSeek-V4-Flash, Hy3, MiMo-V2.5, GLM-5.3-Flash, Qwen3.8-Flash without being locked into a single technical path. ⚡ High-concurrency infrastructure. Industrial-grade APIs target Agent applications and production workloads with low latency and high throughput. 💳 Crypto-native cost efficiency. Native payment methods and scalable compute scheduling provide developers with a more flexible path to manage model usage and deployment costs. The next phase of AI adoption won't depend solely on stronger models, but also on infrastructure that makes models accessible, reliable, and economically viable. Every new user could bring the network a new experiment, a new application, a new Agent, or a new idea. 2.2 million users is a milestone, but what's more exciting is what they will create next. 👉 Start exploring now: https://t.co/Miu0HbV0UT @BAI_AGI @justinsuntron #TRONEcoStar

## zh_cn_10 — target minimax — natural
Post: 2104885840367538431 | @zuz84093219 | other candidates: minimax
Affiliations: []

@NFT_Chen MiniMax Code更新在即咯

Stored English translation:
@NFT_Chen MiniMax Code update is coming soon

## zh_cn_11 — target doubao — natural
Post: 2100457097158885603 | @cy_xiaozhu | other candidates: doubao
Affiliations: []

@criscxuan deepseek写文本也一般，最好用的竟然是豆包😂

Stored English translation:
@criscxuan DeepSeek isn't great at writing text either — turns out Doubao is the most usable 😂

## zh_cn_12 — target qwen — natural
Post: 2083807062325416243 | @maulana_drip_id | other candidates: qwen
Affiliations: []

@affanzbasalamah qwen setelah banyak eksodus penelitinya jadi kurang ya, kemarin banyak yang berhenti.

Stored context:
{"stored_quote": "", "quoted_author": "", "local_parent": "Mantap. \n\nTapi hari-hari pakai DeepSeek flash ama Kimi. Ama Sonnet dan Opus. https://t.co/SAD4NmKbuJ"}

Stored English translation:
Qwen has become worse after the mass exodus of its researchers, many quit recently.

## zh_cn_13 — target mimo — coverage
Post: 2104479508019745100 | @0xLogicrw | other candidates: mimo
Affiliations: []

小米 MiMo 团队复盘了 MiMo-V2.6 上线后的工具调用重复问题。模型有时会反复调用相同或高度相似的工具，持续消耗上下文，但任务没有进展。在 OpenCode 中，Flash 和 Pro 出现重复工具调用的回复占比一度分别达到 1.02% 和 0.54%。

问题出在强化学习的奖励设计。训练主要奖励「最后有没有把任务做对」，却没有充分惩罚过程中的低效行为。原来的规则只有单轮工具调用超过 32 次才会处罚，32 次以下的重复调用完全不扣分。随着 RL 规模扩大，这种坏习惯反而被不断强化。小米回放训练 checkpoint 后发现，Flash 中单轮调用超过 10 次的异常样本比例从 step 0 的 11.1% 增至 step 20 的 24.6%。

最直接的办法是把惩罚阈值从 32 次降到 8 次，再重跑约 20 个 MixRL step，但预计要花 231 万美元。小米最终只训练了一个专门纠正重复调用的 RL teacher，跑 12 个 step、约 7000 个样本，再通过 MOPD 把这项能力合回 Pro 和 Flash。整轮修复约花 9 万美元，只有完整重训方案的约 4%，其他主要 benchmark 基本保持不变。

修复后的 MiMo-V2.6-Pro-MOPD 和 Flash-MOPD 权重已经开放，API 也已经切到新版，调用名称不变。小米还会重置 MiMo Desktop 用户当前周期的剩余额度。

Stored context:
{"stored_quote": "🛠️ MiMo-V2.6 update: tool-call repetition, diagnosed & fixed.\nAfter the MiMo-V2.6 series models launched, we noticed them sometimes repeating identical or highly similar tool calls — burning context and stalling tasks, especially in MiMo Desktop, MiMo Code and OpenCode.\nRoot cause\nA \"reward blind spot\" in scaling RL: when rewards only track final-answer correctness, inefficient behaviors along the way go unnoticed — and get amplified as training scales. Concretely, our flooding penalty only kicked in at >32 tool calls per turn, so anything below that threshold went completely unpunished.\nThe fix\nWe trained a light-weight repetition-specialized RL teacher — just 12 steps, ~7k examples — and merged it into the main model via MOPD, at roughly 4% of the cost of a full mixRL retrain. Repetition dropped sharply across harnesses and context lengths, while benchmarks held steady.\n\n📦 Updated models, open-sourced (MOPD suffix): https://t.co/u81xJigdkn\n📝 Full postmortem: https://t.co/SfFokWC0iD\n\nHuge thanks to our community for the patience and feedback 🙏 Updated models go live on our API platform Sep 25, 06:00 (UTC+8), names unchanged. And for MiMo Desktop users: everyone's remaining quota in the current window will be reset.", "quoted_author": "XiaomiMiMoDevs", "local_parent": ""}

Stored English translation:
Xiaomi MiMo team reviewed the tool call repetition problem after MiMo-V2.6 went online. The model sometimes repeatedly calls the same or highly similar tools, continuously consuming context, but the task makes no progress. In OpenCode, the proportion of replies where Flash and Pro exhibited repeated tool calls once reached 1.02% and 0.54% respectively.

The problem lies in the reward design of reinforcement learning. Training mainly rewards "whether the task was ultimately done correctly," but does not sufficiently punish inefficient behavior during the process. The original rules only penalized single-turn tool calls exceeding 32 times; repeated calls below 32 times were not deducted points at all. As the RL scale expanded, this bad habit was instead continuously reinforced. After Xiaomi played back training checkpoints, it was found that in Flash, the proportion of abnormal samples with single-turn calls exceeding 10 times increased from 11.1% at step 0 to 24.6% at step 20.

The most direct method would be to lower the penalty threshold from 32 times to 8 times, then rerun approximately 20 MixRL steps, but it was estimated to cost 2.31 million US dollars. Xiaomi ultimately only trained one RL teacher specifically to correct repeated calls, running 12 steps with approximately 7000 samples, and then merged this capability back into Pro and Flash via MOPD. The entire fix cost approximately 90 thousand US dollars, only about 4% of the full retraining solution, and other major benchmarks remained basically unchanged.

The weights of the fixed MiMo-V2.6-Pro-MOPD and Flash-MOPD have been released, and the API has also been switched to the new version, with the call names unchanged. Xiaomi will also reset the remaining quota of the current cycle for MiMo Desktop users.

## zh_cn_14 — target deepseek — coverage
Post: 2103775174508061032 | @francis_cgl | other candidates: deepseek, minimax
Affiliations: []

来自@BAI_AGI的强大愿景。

随着https://t.co/vl0CaU7DWN构建领先的一站式AGI基础设施，让每个人都能访问顶级人工智能计算仍然是核心任务。

开发人员和Web3用户现在可以轻松体验、构建和部署代理应用程序，降低障碍和高性能。

DeepSeek V4 Flash在有限的時間內繼續在Web和API上完全免費提供，支援從複雜的推理到大規模工作流程的一切。

这种对包容性、高通量人工智能基础设施的关注完美地补充了TRON生态系统在可扩展性、效率和现实世界效用方面的优势。

他们一起为去中心化和智能系统的创新打开了新的大门。

从今天开始自由，探索工具，并突破可能的界限。

加入社区，在TRON上建设未来。

@Justinsuntron #TRONEcoStar

Stored context:
{"stored_quote": "让顶尖算力触手可及！🔥\n\nhttps://t.co/mTw8ldBplF 秉持“普惠算力”愿景，致力于打造全球领先的一站式 AGI 基础设施，持续降低 AI 使用门槛，让每一位开发者和 Web3 用户都能够轻松体验、构建与部署 Agentic 应用。\n\n依托一站式 AGI 基础设施，https://t.co/mTw8ldBplF 全面赋能高吞吐量 AI 核心场景：\n▪️ 全球顶尖模型矩阵：一站式聚合全球前沿大模型，内置智能路由优化成本与效率\n▪️ 高吞吐场景全覆盖：稳定承载百万级长上下文、复杂推理任务与 Agent 工作流，满足从日常使用到规模化构建的多元需求\n▪️ 弹性 API 路由机制：官方高可用与自选折扣渠道并行，兼顾生产级稳定与极致性价比\n▪️ Web2/Web3 双通道：支持 Google 与主流钱包登录，打通多公链加密资产与法币结算网络\n\n🎁 #DeepSeek V4 Flash 限时免费活动火热进行中！Web & API 双端 $0 畅用！https://t.co/mTw8ldBplF 正在让顶尖算力更普惠，让更多 AI 创新真正发生！\n\n🔗 立即无门槛免费使用：https://t.co/vi1PDjFZn0", "quoted_author": "BAI_AGI", "local_parent": ""}

Stored English translation:
A powerful vision from @BAI_AGI.

As https://t.co/vl0CaU7DWN builds a leading one-stop AGI infrastructure, making top-tier AI computing accessible to everyone remains a core mission.

Developers and Web3 users can now easily experience, build, and deploy agent applications, lowering barriers and providing high performance.

DeepSeek V4 Flash will continue to be provided completely free on Web and API for a limited time, supporting everything from complex reasoning to large-scale workflows.

This focus on inclusive, high-throughput AI infrastructure perfectly complements the TRON ecosystem's strengths in scalability, efficiency, and real-world utility.

Together they open new doors for innovation in decentralized and intelligent systems.

Free from today, explore the tools, and break through the boundaries of the possible.

Join the community, build the future on TRON.

@Justinsuntron #TRONEcoStar

## zh_cn_15 — target qwen — coverage
Post: 2101868706532094095 | @Alan_jupiters | other candidates: minimax, qwen
Affiliations: []

想在普通家用电脑上跑起 27B 参数量的大模型，现在有了更平价的方案。

Reddit 网友分享了在 RTX 3060（12GB）加 5060 Ti（16GB）的双卡组合下，流畅运行 Qwen 27B 模型的实测经验。这说明通过合理的显存拆分和优化工具，不必购买昂贵的专业卡，也能获得不错的本地 AI 推理体验。

1. 核心工具是 exllamav3 引擎。它专门针对 NVIDIA GPU 进行了极致优化，配合 tabbyAPI 框架，能让模型在显存容量受限时依然维持极高的生成速度。

2. 速度表现亮眼。在该博主的配置下，平均推理速度达到了每秒 50 个 token，这已经足以满足实时对话需求。关键在于使用了 MTP 技术（多头预测），能有效弥补显存带宽不足导致的性能瓶颈。

3. 硬件组合策略。该方案展示了如何利用闲置显卡通过 PCIe 插槽组合显存。只要总显存能覆盖模型权重，通过开源工具的分布式处理，就能实现“平民级”的本地大模型部署。

Takeaway：
本地运行大模型不再是极客的专利，通过 exllamav3 引擎和多卡显存叠加，普通家用显卡也能跑起中等规模的高性能模型，显著降低了隐私敏感类 AI 应用的部署门槛。

#人工智能 #本地AI #大模型 #RTX3060 #科技干货

https://t.co/ZPfF8FwYZr

Stored English translation:
Want to run a large model with 27B parameters on an ordinary home computer, there is now a more affordable solution.

A Reddit user shared real-test experience of smoothly running the Qwen 27B model under a dual-card combination of RTX 3060 (12GB) plus 5060 Ti (16GB). This shows that through reasonable VRAM splitting and optimization tools, without buying expensive professional cards, one can still obtain a good local AI inference experience.

1. The core tool is the exllamav3 engine. It is specifically and extremely optimized for NVIDIA GPUs, and combined with the tabbyAPI framework, it allows the model to maintain extremely high generation speeds even when VRAM capacity is limited.

2. Speed performance is eye-catching. Under this blogger's configuration, the average inference speed reached 50 tokens per second, which is already enough to meet real-time conversation needs. The key lies in the use of MTP technology (Multi-Token Prediction), which can effectively compensate for performance bottlenecks caused by insufficient VRAM bandwidth.

3. Hardware combination strategy. This solution demonstrates how to utilize idle graphics cards to combine VRAM through PCIe slots. As long as the total VRAM can cover the model weights, through the distributed processing of open-source tools, a "civilian-level" local large model deployment can be achieved.

Takeaway:
Running large models locally is no longer the patent of geeks; through the exllamav3 engine and multi-card VRAM stacking, ordinary home graphics cards can also run medium-scale high-performance models, significantly lowering the deployment threshold for privacy-sensitive AI applications.

#ArtificialIntelligence #LocalAI #LargeModel #RTX3060 #TechDryGoods

https://t.co/ZPfF8FwYZr

## zh_cn_16 — target deepseek — coverage
Post: 2103002792021594377 | @KhanAIBuilds | other candidates: deepseek, moonshot_kimi
Affiliations: []

说个翻转，别急着站队。

9 月 10 号 Anthropic 发了第四份威胁情报，指控七家中国实验室用假号把用户请求悄悄转到 Claude，拿输出当自家模型答案——它管这叫 illicit distillation。公开数字里，Moonshot 大约两千三百万次交换、五千三百八十个假号；DeepSeek 更密，七月十四天里超过一千两百一十万次。

美方读这份报告，看的是「模型被偷」。

十二天后，Decrypt 和 The Next Web 引 The Information：中国网信办 CAC 先是把七家都叫过去，随后把调查收窄到 DeepSeek 和 Moonshot，人已经上门问过。关心的点不是 Claude 丢不丢能力，是公安、军工、政企类敏感数据有没有跟着路由层落到美服。探针还开着，没定罚，两家也没公开回应。

同一套「品牌路由层」行为，在两边的罪名刚好对调——一边告窃智，一边查出境。

我不太想在这讨论峰会谁赢谁输。可检验的东西更硬：有没有正式处罚或整改公告；产品端有没有可核对的路由切断、日志留存、跨境评估，而不只是「我们配合调查」。

卧槽这事其实挺直白——你把用户请求偷偷转给别人的模型，美方盯的是模型，中方盯的是数据。下次再刷到蒸馏大战，先问一句：你说的风险，是模型侧，还是数据侧？

Stored English translation:
Let me tell you about a reversal, don't be quick to take sides.

On September 10, Anthropic released its fourth threat intelligence report, accusing seven Chinese laboratories of using fake accounts to quietly redirect user requests to Claude, taking the output as their own models' answers—it calls this illicit distillation. In the public figures, Moonshot had about twenty-three million exchanges, five thousand three hundred and eighty fake accounts; DeepSeek was denser, with over twelve million one hundred thousand times in fourteen days in July.

The US side reading this report sees "models being stolen."

Twelve days later, Decrypt and The Next Web cited The Information: China's cyberspace administration CAC first called all seven in, then narrowed the investigation to DeepSeek and Moonshot, people have already visited in person to ask. The point of concern is not whether Claude is losing capability, but whether sensitive data of public security, military industry, and government-enterprise types followed the routing layer to US servers. The probes are still open, no penalties have been set, and the two companies have not publicly responded.

The same set of "brand routing layer" behavior, the charges on both sides are exactly swapped—one side sues for theft of intelligence, the other investigates outbound transfer.

I don't really want to discuss who won or lost the summit here. But the things that can be verified are harder: whether there are formal penalties or rectification announcements; whether there are verifiable routing cuts, log retention, and cross-border assessments on the product side, rather than just "we are cooperating with the investigation."

Holy shit this matter is actually quite straightforward—you secretly redirect user requests to someone else's model, the US side is staring at the model, the Chinese side is staring at the data. Next time you brush past the distillation war, ask one question first: the risk you are talking about, is it on the model side, or the data side?

## zh_cn_17 — target ernie — coverage
Post: 2102965016924418336 | @daityn_rucker | other candidates: ernie
Affiliations: []

小暑炎热，空调坏了。两人索性去图书馆推特发帖软件出售Gemini文心一言避暑，并肩看书推特发帖软件互关互赞热评热搜影子封禁深圳，Twitter发帖软件开源模型机器人股票偶尔低声交流。
🔥推特账号 ins账号购买 谷歌账号购买 飞机账号 TG账号
https://t.co/rrTKDlsfDB

Stored English translation:
Slight Heat is scorching, the air conditioner is broken. Two people simply went to the library Twitter posting software selling Gemini Wenxin Yiyan to escape the heat, reading books side by side Twitter posting software mutual follow mutual like hot comments hot search shadow ban Shenzhen, Twitter posting software open source model robot stocks occasionally communicating in low voices.
🔥Twitter account ins account purchase Google account purchase plane account TG account
https://t.co/rrTKDlsfDB

## zh_cn_18 — target qwen — coverage
Post: 2102237798824902873 | @NFT_Chen | other candidates: minimax, qwen
Affiliations: []

🔥重磅！2026云栖大会开幕，Qwen新掌门刘大一恒首次官宣 Qwen4全家桶，RSI自我进化已初步跑通！未来将发布 5-10T 量级模型！

刘大恒一讲话要点拆解：
1️⃣ Qwen4系列 Coming Soon Qwen4-Max｜Qwen4-Flash & Qwen4-Plus｜Qwen4-27B 开源侧先有27B，闭源侧Max/Plus/Flash分层继续。

2️⃣ RSI自我进化系统已落地
 从真实内测日志 + 用户反馈里自动找能力缺口 → 自动构造训练数据 → 先在小模型上多轮验证 → 再喂给Max。
 一个多月完成 33轮数据迭代，30天把千问3.8 Max的AA智能指数从40拉到45，冲到国内第一。

3️⃣ 芯模协同飞轮 千问完整接入工业级EDA，连续跑60+小时、调用数万次工具，在保性能前提下把芯片面积缩减 42%。
 形成「模型设计芯片 → 更强芯片反哺模型」的正向循环。

4️⃣ 更远的野心 未来Qwen会训5-10T 量级模型。趋势很明确：自我迭代 + 芯模协同，扎进真实产业生产。

可以期待一下Qwen4正式发布。有27B开源先吃上，Max再冲天花板！

#Qwen4 #通义千问 #云栖大会 #RSI #刘大一恒 #阿里云 #大模型 #阿里巴巴

Stored context:
{"stored_quote": "🔥最新！阿里AI大模型 Qwen 换帅：预训练出身的刘大一恒正式出任一号位！\n\n云栖大会嘉宾名单上，他排在蔡崇信、吴泳铭之后，位列第三。\n\n细节要点：\n🔹川大本硕博，2020华为天才少年第一档，2021加入达摩院，Qwen早期核心 \n\n🔹主导Qwen1至3.5全系列，参与300+模型开源，引用3.6万+，NeurIPS25最佳论文通讯作者\n\n🔹3月林俊旸、郁博文离职，惠彬原1月赴Meta；刘从预训练扩管后训练和Coding\n\n🔹6月Token Foundry成立、吴泳铭亲管；9月刘正式扶正\n\n🔹HF下载约20.45亿次，近谷歌5倍、Meta 9倍，开源第一\n\n#阿里 #Qwen #刘大一恒 #云栖大会 #开源大模型 #千问通义", "quoted_author": "NFT_Chen", "local_parent": ""}

Stored English translation:
🔥Heavyweight! 2026 Apsara Conference opens, Qwen's new leader Liu Dayiheng first officially announces Qwen4 family bucket, RSI self-evolution has already preliminarily run through! Will release 5-10T magnitude models in the future!

Breakdown of Liu Dahengyi's speech key points:
1️⃣ Qwen4 series Coming Soon
Qwen4-Max｜Qwen4-Flash & Qwen4-Plus｜Qwen4-27B
Open source side has 27B first, closed source side Max/Plus/Flash layering continues.

2️⃣ RSI self-evolution system has landed
Automatically find capability gaps from real internal test logs + user feedback → automatically construct training data → first verify over multiple rounds on small models → then feed to Max.
Completed 33 rounds of data iteration in over a month, in 30 days pulled Qwen 3.8 Max's AA intelligence index from 40 to 45, rushing to domestic first.

3️⃣ Chip-model collaboration flywheel
Qwen fully integrated into industrial-grade EDA, running continuously for 60+ hours, calling tools tens of thousands of times, reducing chip area by 42% while maintaining performance.
Forming a "model designs chip → stronger chip feeds back to model" positive cycle.

4️⃣ Farther ambition
In the future Qwen will train 5-10T magnitude models. The trend is very clear: self-iteration + chip-model collaboration, diving into real industrial production.

Can look forward to Qwen4's official release. Have 27B open source to eat first, and Max rushes the ceiling!

#Qwen4 #TongyiQianwen #ApsaraConference #RSI #LiuDayiheng #Aliyun #LargeModel #Alibaba

## zh_cn_19 — target mimo — coverage
Post: 2105141166572454356 | @Sigma_ccc | other candidates: deepseek, mimo
Affiliations: []

31岁登顶小米最高职级：
罗福莉@_LuoFuli 的开挂履历。。

· 出身农村普通家庭，北师大计算机本科，北大计算语言学硕士
· 毕业进阿里达摩院，做多语言预训练模型VECO和AliceMind
· 2022年加入幻方，成为DeepSeek研究员，深度参与DeepSeek-V2研发，也部分参与过R1
· 2024年底，雷军认为小米大模型起步太晚，亲自下场挖人，外界传薪酬"千万级"
· 2025年11月12日，她在朋友圈官宣加入Xiaomi MiMo
· 加入小米仅10个月，31岁晋升22级——小米职级体系天花板
· 带队成绩：MiMo-V2.6-Pro拿下AA指数46分，开源权重模型第一；两轮训练烧掉347万美元，她说难度超过DeepSeek R1

从达摩院到DeepSeek再到小米，每一步都踩在风口上。。。

Stored English translation:
31 years old reaching Xiaomi's highest job level:
Luo Fuli @_LuoFuli 's cheat-code resume...

· Born into an ordinary rural family, Beijing Normal University Computer Science undergraduate, Peking University Computational Linguistics master
· After graduation entered Alibaba DAMO Academy, worked on multilingual pre-training models VECO and AliceMind
· Joined High-Flyer in 2022, became a DeepSeek researcher, deeply participated in DeepSeek-V2 R&D, and also partially participated in R1
· At the end of 2024, Lei Jun believed Xiaomi's large model started too late, personally stepped in to poach people, external rumors claim compensation is "ten-million level"
· November 12, 2025, she officially announced joining Xiaomi MiMo on Moments
· Joined Xiaomi for only 10 months, promoted to level 22 at 31 years old——the ceiling of Xiaomi's job level system
· Team leading achievements: MiMo-V2.6-Pro took the AA Index with 46 points, first among open-weight models; two rounds of training burned 3.47 million US dollars, she said the difficulty exceeds DeepSeek R1

From DAMO Academy to DeepSeek and then to Xiaomi, every step has been taken right on the wind vent...

## zh_cn_20 — target deepseek — coverage
Post: 2104881693706653733 | @tianyi | other candidates: deepseek
Affiliations: []

DeepSeek 弹性计算团队大量 HC 招人！尤其需要资深工程师。 来看看这篇技术分享：《DeepSeek 弹性计算 (DSec)：面向大规模 Agent 训练的沙盒基础设施》  https://t.co/7rBokhowIA

Stored English translation:
DeepSeek Elastic Computing team is hiring a large number of HC! Especially in need of senior engineers. Come take a look at this technical sharing: "DeepSeek Elastic Computing (DSec): Sandbox Infrastructure for Large-scale Agent Training" https://t.co/7rBokhowIA
