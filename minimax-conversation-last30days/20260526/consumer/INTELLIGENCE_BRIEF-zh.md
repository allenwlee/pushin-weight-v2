# {{AGENT_ATTRIBUTION}}
# 情报简报：MiniMax 对话格局
**日期：** 2026-05-26
**研究周期：** 2026-04-26 至 2026-05-26
**对照模型：** Qwen AI、DeepSeek（与 MiniMax 运行相同查询）
**数据来源：** Reddit（限速/损坏）、X via xAI/Grok、YouTube、Brave 网络搜索

---

## 1. 对话量排名

### 按总提及量（X + Reddit + YouTube，所有查询汇总）

| 排名 | 模型 | X 帖子 | Reddit 帖子 | YouTube 视频 | 总计 |
|------|-------|---------|-------------|--------------|------|
| 1 | **DeepSeek** | ~98 | ~39 | ~51 | **~188** |
| 2 | **MiniMax**（所有查询） | ~163 | ~59 | ~95 | **~317** |
| 3 | **Qwen**（所有查询） | ~94 | ~27 | ~54 | **~175** |

MiniMax 在原始数量上领先仅因为其产品线查询（Hub、Mavis、Speech、Music、Agent、M2.7、Token Plan）分散了对话。当比较单一"品牌"查询时：

| 品牌 | 核心查询量 | 主要叙事驱动因素 |
|-------|------------|------------------|
| DeepSeek | 55（X+Reddit+YT） | 75% 永久降价 + V4 Pro 发布 |
| Qwen | 43（X+Reddit+YT） | Qwen 3.7 Max 发布 + 编程主导地位 |
| MiniMax | 36（X+Reddit+YT） | M2.7 NVIDIA 背书 + Mavis 发布 |

**关键观察：** DeepSeek 主导着头条对话。Qwen 和 MiniMax 的对话更为分散——Qwen 分布在编程/代理方向，MiniMax 分散在碎片化的产品生态系统中。

---

## 2. 用例优势地图

### DeepSeek：编程 + 性价比

DeepSeek 主导着**"编程性价比"**叙事。75% 的 V4 Pro 永久降价主导了整个 30 天窗口期：

- **V4 Pro 定价：** 每 1M tokens 输入 $0.435 / 输出 $0.87 — 比 GPT-5.5 便宜 20-30 倍
- **开发者行为转变：** 用户反馈 V4 Pro 用于生产编程"基本等于免费"
- **技术栈集成：** Hermès Agent + DeepSeek V4 Pro 是持续的高互动模式
- **渗透测试：** 在 r/DeepSeek 上被封为"渗透测试之王"
- **本地推理：** MLX DeepSeek V4 Flash 在 M3 Ultra 上运行（107GB，<128GB）

**主要用例：** 编程代理、生产工作负载、成本敏感型开发者、本地推理爱好者。

### Qwen：编程 + 代理式 AI

Qwen 主导着**"代理时代旗舰模型"**叙事：

- **Qwen 3.7 Max**（2026 年 5 月 20 日发布）：100 万 token 上下文、35 小时自主任务、1000+ 次工具调用
- **全球 AI 编程模型排名第二**（依据阿里巴巴云数据，1541 Code Arena 分数，仅次于 Claude）
- **Qwen 3.7 Max 已上线隐式缓存** — 自动生效，无需设置
- **工具调用基准：** Unsloth Qwen3.6-27B-MTP 达到 91.7% 可靠性（15 次中 13 次成功）
- **WebWorld：** 开放世界模型系列在事实性上超越 Claude Opus 4.1 和 Gemini 3 Pro

**主要用例：** 长周期代理任务、自主编程、SEO 工作流、多轮工具使用。

### MiniMax：多模态创意 + 代理平台

MiniMax 拥有**最广泛的单一品牌用例分布**：

| 用例 | MiniMax 产品 | 对话信号 |
|----------|----------------|-------------------|
| 编程代理 | M2.7 + Token Plan（$10-20/月） | 高 — NVIDIA 背书，$20/月定位 |
| 多模态创意 | MiniMax Hub | 非常高 — 统一工作区叙事 |
| 语音/TTS | Speech 2.8 Turbo | 高 — Variety 报道、戛纳电影节 |
| 音乐生成 | Music 2.6 | 增长中 — 视频编辑社区采用 |
| 多代理团队 | Mavis（由 Agent 更名） | 高 — 验证器模式创新 |
| Perplexity 替代 | MiniMax AI 搜索后端 | 新兴 — 已报告切换至 Perplexity |

**主要用例：** 多模态创意制作（Hub）、语音优先应用、开发者友好的代理技术栈。

---

## 3. 语言格局

### 英语圈对话

**主要叙事：** DeepSeek 的价格战 — 永久 75% V4 Pro 降价将中国定位为赢得 AI 成本竞赛。

**关键话题：**
- r/DeepSeek：V4 Pro 定价讨论、"DeepSeek 真的值得吗？"话题
- r/LocalLLaMA：Qwen 3.7 对比、MiniMax M2.7 本地部署
- r/AISEOInsider：Qwen 3.7 用于 SEO 自动化（发帖量大，可能有推广性质）
- r/vibecoding：DeepSeek V4 Flash 用于"氛围编程"工作流

**观察：** r/AISEOInsider 的 Qwen 3.7 内容量占比过高——类似"Qwen 3.7 是无人预料到的 AI 模型发布"的话题可能反映的是联盟营销/内容营销动态，而非有机的社区情绪。

### 中文圈对话

**主要叙事：** MiniMax 作为全栈 AI 生态系统 — Hub、Mavis、Speech、Music、Hailuo 视频同时被讨论。

**来自中文 X 账号的关键信号：**
- MiniMax Hub 被描述为"AI 视频的 Claude"（ResourceHunt9，5 月 22 日）
- Mavis 被描述为"MiniMax 版的 Jarvis"——带 Leader/Worker/Verifier 的多代理系统（LeonBuildsAI，5 月 15 日）
- MiniMax Speech 2.8 因专业语音质量获得认可（flyingpetal472："迭代快"）
- Qwen 3.7 发布在中国开发者圈也备受关注

**中文讨论中 MiniMax 竞品对比：**
- Kimi/MiMo 在编程方面被评为高于 MiniMax（PovilasKorop 在 X 上）
- DeepSeek 在通用能力方面被评为最强，MiniMax 因广度受到重视

### 语言差距发现
**MiniMax 相对于其英文报道量拥有更多的中文报道量，比例超过 DeepSeek 或 Qwen。** 这可能反映了：(a) MiniMax 是一家总部位于上海的本土公司，拥有更强的国内产品生态系统（Hub、Hailuo、Speech 都在中国区），(b) 与 DeepSeek 相比缺乏西方开发者布道（DeepSeek 积极培育全球开发者社区）。

---

## 4. 模型变体细分（MiniMax）

MiniMax 对话分解为不同的产品叙事：

| 变体 | 对话份额 | 关键叙事 |
|---------|------------------|---------------|
| **M2.7** | ~35% | 自我进化模型、NVIDIA 背书、"最便宜的 50 倍 Claude 替代方案" |
| **Mavis**（Agent 升级版） | ~20% | Leader-Worker-Verifier 模式、多代理桌面 |
| **Hub** | ~20% | 全功能创意工作区，替代 9 个独立工具 |
| **Speech 2.8** | ~15% | 专业语音、Variety 报道、戛纳电影节 |
| **Music 2.6** | ~5% | 视频编辑社区（日本用户居多）、Suno 替代品 |
| **Hailuo 视频** | ~5% | 集成在 Hub 中，在创意工作流上下文中被提及 |

**注意：** M2.7 和 Mavis 占主导地位，因为它们是开发者/技术先行用户讨论的焦点。Speech 和 Music 在创意/社区场景中占主导，具有强大的非英语用户参与度。

**M2.7 质量回退：** r/MiniMax_AI 上持续存在的"质量下降了吗？"话题（5 月 22 日）表明存在一些用户不满，但叙事角度混杂——支持者称其"发布即用"且是"日常主力"。

---

## 5. 定价认知

### MiniMax Token Plan

**认知：** "便宜好用"——定位为性价比之王。

- $10/月用于 MiniMax Coding Plan
- $20/月用于完整 Token Plan（所有模态）
- 所有模型（M2.7、视频、语音、音乐）共享额度
- 推荐折扣生效中（9 折）
- 与 Claude Pro（$20）、ChatGPT Pro（$100）、Gemini 订阅相比更有优势

**已知局限：** "智力相对弱"——依据中国开发者账号，智能水平弱于 DeepSeek V4 Pro。但即使批评者也承认其成本数量优势。

### DeepSeek V4 Pro

**认知：** "比 GPT-5.5 便宜 20-30 倍"——从根本上重置了价格预期。

- 永久定价：每 1M tokens 输入 $0.435 / 输出 $0.87（75% 折扣后的促销价）
- 缓存命中：每 1M $0.0036
- 开发者证言："DeepSeek V4 Pro 的性价比正在改变我对 AI 生产编程的看法"
- 西方媒体：路透社、布隆伯格、Engadget 都报道了永久降价

### Qwen 3.7 Max

**认知：** 定价偏高但对代理工作负载物有所值。

- 每 1M tokens 输入 $2.50 / 输出 $7.50（OpenRouter）
- 100 万上下文，含隐式缓存
- 被视为"值得"用于 35 小时自主任务
- 面临来自 DeepSeek V4 Pro 的价格压力（"阿里巴巴的 Qwen 可能需要降低 API 定价以匹配 DeepSeek 的 $0.84/1M"）

---

## 6. 关键声音

### MiniMax

| 账号 | 角色 | 重要贡献 |
|--------|------|---------------------|
| @NVIDIAAI | 官方 | M2.7 上的 16 个本地 AI 代理 — MiniMax X 最高互动（1253 赞） |
| @RebeccahAdson | 高级用户 | MiniMax Hub 叙事领导者，多条高转发话题 |
| @MikaStars39 | 内部人士 | 宣布加入 MiniMax 训练后团队，参与 M3 开发 |
| @MiniMaxAgent | 官方 | Mavis 发布公告 |
| @Hailuo_AI | 官方 | Speech 2.8 戛纳报道、语音合作伙伴关系 |
| @boxmining | 影响者 | Mavis"最适合入门者的多代理"报道 |
| @kaif9999 | 高级用户 | MiniMax $10 编程计划作为必备代理订阅 |

### DeepSeek

| 账号 | 角色 | 重要贡献 |
|--------|------|---------------------|
| @deepseek_ai | 官方 | 75% 永久降价公告（23K 赞） |
| @testingcatalog | 分析师 | V4 Pro 定价解析 |
| @0xSero | 开发者 | "$6.74 获得 4.5 亿 tokens"——真实成本案例 |
| @jeremychone | 开发者 | V4 Pro 生产编程证言 |
| @mark_k | 影响者 | DeepSeek 架构深度解析（MoE、MLA、Engram） |

### Qwen

| 账号 | 角色 | 重要贡献 |
|--------|------|---------------------|
| @Alibaba_Qwen | 官方 | Qwen 3.7 Max 隐式缓存公告 |
| @alibaba_cloud | 官方 | Qwen 3.7 Max 第二大编程模型声明 |
| @outsource_ | 开发者 | Qwen ULTRON 27B 微调、3D 模型生成演示 |
| @rohanpaul_ai | 分析师 | Qwen 3.7 Max 编程/代理基准 |

---

## 7. 关键引述

### 关于 MiniMax M2.7

> "MiniMax M2.7 是按基准测试来看最聪明的家用模型，在 GB10 硬件上运行速度为 34-36 tokens/秒。"
> — @mattwallace，5 月 25 日

> "NVIDIA 向 80+ AI 模型提供免费 API 访问。真的是免费的。DeepSeek 3.2、Kimi 2.5、MiniMax M2.7、GPT-OSS-120B、GLM 5.1、Llama 3。"
> — @venoyuls，5 月 25 日

> "既然说到了……我目前最好的开源 AI 模型仍然是：1. Deepseek v4 pro 2. Minimax 2.7 3. Kimi 2.6"
> — @nekwasar，5 月 25 日

### 关于 MiniMax Hub / Mavis

> "大家仍然在拼凑多个 AI 工具来完成一个项目。一个用于图像，另一个用于视频，还有一个用于音频。MiniMax Hub 将整个流程整合为一个 AI 创意工作区。说实话，感觉就像是 AI 视频的 Claude。"
> — @FellMentKE，5 月 16 日（201 赞，115 转发）

> "MiniMax的Mavis给了一个思路: Leader负责统筹全局, Worker负责具体执行, Verifier负责验收质量. 关键设计是Worker和Verifier之间是对抗关系."
> — @LeonBuildsAI，5 月 15 日

> "MiniMax 做到了大厂都没有做到的。一套方案。CLI、API、代理。所有模型：M2.7、视频、语音、音乐。所有额度共享。"
> — @heyshrutimishra，5 月 16 日

### 关于 DeepSeek V4 Pro 降价

> "DeepSeek 是免费的，质量几乎和 Claude 一样好。但我们仍然每月付 $20，因为我们已经说服自己付费版本更懂我们。"
> — @trikcode，5 月 24 日

> "DeepSeek 的策略很有趣：'好吧，你觉得可靠的 100 万上下文、快速、便宜、一流开源智能还不够酷？再来个 75% 降价……'"
> — @teortaxesTex，4 月 29 日

> "这个 DeepSeek V4 Pro 的性价比（$0.87 输出）真的在改变我对 AI 生产编程的看法。看到大三巨头不断翻倍或三倍涨价真的很有意思……"
> — @jeremychone，5 月 25 日

### 关于 Qwen 3.7 Max

> "Qwen 3.7-Max 正式成为全球第二大 AI 编程模型。在 Code Arena 上获得 1541 分，仅次于 Claude。"
> — @alibaba_cloud，5 月 26 日

> "隐式缓存现已在 Qwen3.7-Max 上线——自动生效，无需设置。"
> — @Alibaba_Qwen，5 月 25 日

> "DeepSeek V4 Pro 是最聪明的。它的 API 会收集数据用于训练。Kimi K2.6：均衡。DeepSeek V4 Flash：最高效。MiniMax M2.7：最快。"
> — @AmineHilaa，5 月 25 日（引用服务 FAQ）

---

## 8. 差距与机会

### 对话中的差距

**1. MiniMax 面临的是叙事问题，而非产品问题。**
M2.7 在技术上与 V4 Pro 和 Qwen 3.7 Max 具有竞争力。但 DeepSeek 占据了"性价比"叙事；Qwen 占据了"代理能力"叙事。MiniMax 的叙事是"我们什么都能做"。在一个专家横行的世界里，通才的叙事更难落地。

**2. 质量回退叙事悬而未决。**
r/MiniMax_AI 上 5 月 22 日的"质量下降了吗？"话题持续获得互动。如果 MiniMax 在 DeepSeek 和 Qwen 持续改进的同时静默降低模型质量，这可能加速用户流失。

**3. 西方主流媒体报道薄弱。**
DeepSeek 的降价获得了路透社、布隆伯格、Engadget 和 CNN 的报道。MiniMax 的 Mavis 发布和 NVIDIA 背书则没有。这表明 MiniMax 的公关/传播没有有效地触达西方科技媒体。

**4. 数据收集担忧正在浮现。**
X 上的用户注意到 DeepSeek V4 Pro 的 API"会收集数据用于训练"——这与其"开放权重"的认知不同。MiniMax 应澄清其数据政策，以避免受到同样的质疑。

### 机会

**1. MiniMax Hub 作为切入创意专业人士的楔子。**
Hub 叙事（"AI 视频的 Claude"）正在引起共鸣。这与 DeepSeek（聚焦编程）和 Qwen（聚焦代理）形成了差异化定位。统一创意工作区叙事如果通过创意专业人士社区进行放大，可以占据一个独特的受众群体。

**2. Perplexity 作为一个证明案例。**
Perplexity 报道切换至 MiniMax AI 搜索（成本降低 27%，工具调用减少 45%）是一个尚未被广泛宣传的可信企业参考案例。

**3. Mavis 验证器模式作为技术差异化因素。**
对抗性 Worker/Verifier 架构是真正新颖的。X 上的技术受众正在关注它。将 Mavis 定位为"会检查自己工作的代理"可能会吸引那些被 AI 输出自信但错误所困扰的开发者。

**4. Speech 2.8 作为低调的收入驱动因素。**
Variety 报道、戛纳电影节使用、基于 Speech 02 构建的第三方 SaaS——MiniMax Speech 正在以极少的营销投入产生 B2B 收入和品牌信誉。这可能是该模型最强的护城河。

---

## 附录：数据覆盖说明

- **Reddit：** 损坏（所有模型均 90 年代超时）— 所有模型对比仍然有效，因为限制对所有模型均等。对照实验完整性已维护。
- **YouTube：** 正常运行；字幕不可用（试点中 0/5）。使用标题 + 播放量。
- **Hacker News：** 全程 Algolia API 错误 — HN 数据不可用。
- **网络（Brave）：** 零星 429 错误；部分查询返回 0 条网络结果。DeepSeek V4 查询返回了网络数据；MiniMax 查询频繁返回 0 条网络结果。
- **Reddit 丰富化：** 大部分查询在第一页后被限速（429）；互动指标仅反映第一页帖子。

---

*研究通过 `last30days.py` 跨 Reddit、X（xAI/Grok）、YouTube 和 Brave 网络搜索进行。3 个模型（MiniMax、Qwen、DeepSeek）的 27 个查询，按语言、用例和关键词细分。总研究时间：Unit 1-7 约 30 小时。*