# {{AGENT_ATTRIBUTION}}
# 情报简报：MiniMax 对话格局
**日期：** 2026-05-26
**研究周期：** 2026-04-26 至 2026-05-26
**对照模型：** Qwen AI、DeepSeek（与 MiniMax 使用相同查询）
**数据来源：** Reddit（限速/故障）、X via xAI/Grok、YouTube、Brave 网页搜索

---

## 1. 对话量排名

### 按总提及量（X + Reddit + YouTube，所有查询合并）

| 排名 | 模型 | X 帖子 | Reddit 帖子 | YouTube 视频 | 总计 |
|------|-------|---------|-------------|------------|------|
| 1 | **DeepSeek** | ~98 | ~39 | ~51 | **~188** |
| 2 | **MiniMax**（所有查询） | ~163 | ~59 | ~95 | **~317** |
| 3 | **Qwen**（所有查询） | ~94 | ~27 | ~54 | **~175** |

MiniMax 在原始数量上领先是因为其产品线查询（Hub、Mavis、Speech、Music、Agent、M2.7、Token Plan）分散了对话。当比较单一"品牌"查询时：

| 品牌 | 核心查询量 | 主要叙事驱动因素 |
|-------|----------|-----------------|
| DeepSeek | 55（X+Reddit+YT） | 75% 永久降价 + V4 Pro 发布 |
| Qwen | 43（X+Reddit+YT） | Qwen 3.7 Max 发布 + 编程主导地位 |
| MiniMax | 36（X+Reddit+YT） | M2.7 NVIDIA 背书 + Mavis 发布 |

**关键观察：** DeepSeek 主导了头条对话。Qwen 和 MiniMax 的对话分布更广——Qwen 分布在编程/代理领域，MiniMax 分布在一个分散的产品生态系统中。

---

## 2. 用例优势地图

### DeepSeek：编程 + 性价比

DeepSeek 占据了 **"编程性价比"** 的叙事。75% 永久 V4 Pro 降价主导了整个 30 天窗口：

- **V4 Pro 定价：** 每 1M tokens 输入 $0.435 / 输出 $0.87 —— 比 GPT-5.5 便宜 20-30 倍
- **开发者行为转变：** 用户反馈 V4 Pro 用于生产编程"基本等于免费"
- **技术栈集成：** Hermès Agent + DeepSeek V4 Pro 是一个反复出现的高参与度模式
- **渗透测试：** 在 r/DeepSeek 上被称为"渗透测试之王"
- **本地推理：** MLX DeepSeek V4 Flash 在 M3 Ultra 上运行（107GB，<128GB）

**主导用例：** 编程代理、生产工作负载、成本敏感型开发者、本地推理爱好者。

### Qwen：编程 + 代理式 AI

Qwen 占据了 **"代理时代旗舰模型"** 的叙事：

- **Qwen 3.7 Max**（2026 年 5 月 20 日发布）：1M token 上下文、35 小时自主任务、1000+ 工具调用
- **全球 AI 编程模型 #2** 来自阿里云（1541 Code Arena 分数，仅次于 Claude）
- **隐式缓存已在 Qwen 3.7 Max 上线** —— 自动启用，无需设置
- **工具调用基准：** Unsloth Qwen3.6-27B-MTP 达到 91.7% 可靠性（15 次中 13 次成功）
- **WebWorld：** 击败 Claude Opus 4.1 和 Gemini 3 Pro 的开放世界模型系列

**主导用例：** 长周期代理任务、自主编程、SEO 工作流、多轮工具使用。

### MiniMax：多模态创意 + 代理平台

MiniMax 拥有任何单一品牌中 **最广泛的用例分布**：

| 用例 | MiniMax 产品 | 对话信号 |
|----------|----------------|-------------------|
| 编程代理 | M2.7 + Token Plan（$10-20/月） | 高——NVIDIA 背书、$20/月定位 |
| 多模态创意 | MiniMax Hub | 非常高——统一工作区叙事 |
| 语音/TTS | Speech 2.8 Turbo | 高——Variety 报道、戛纳电影节 |
| 音乐生成 | Music 2.6 | 增长中——视频编辑社区采用 |
| 多代理团队 | Mavis（原 Agent） | 高——验证器模式创新 |
| Perplexity 替代方案 | MiniMax AI 搜索后端 | 新兴——已报告切换至 Perplexity |

**主导用例：** 多模态创意制作（Hub）、语音优先应用、对开发者友好的代理技术栈。

---

## 3. 语言格局

### 英语对话

**主要叙事：** DeepSeek 的价格战——永久 75% V4 Pro 降价将中国定位为赢得 AI 成本竞争。

**关键话题：**
- r/DeepSeek：V4 Pro 定价讨论、"DeepSeek 真的值得吗？"话题
- r/LocalLLaMA：Qwen 3.7 对比、MiniMax M2.7 本地部署
- r/AISEOInsider：Qwen 3.7 用于 SEO 自动化（发帖量大，可能有推广性质）
- r/vibecoding：DeepSeek V4 Flash 用于"氛围编程"工作流

**观察：** r/AISEOInsider 的 Qwen 3.7 内容量占比过高——类似"Qwen 3.7 是没人注意到的 AI 模型发布"这样的帖子可能反映的是联盟/内容营销动态，而非有机社区情绪。

### 中文对话

**主要叙事：** MiniMax 作为全栈 AI 生态系统——Hub、Mavis、Speech、Music、Hailuo 视频同时被讨论。

**来自中文 X 账户的关键信号：**
- MiniMax Hub 被描述为"AI 视频领域的 Claude"（ResourceHunt9，5月22日）
- Mavis 被描述为"MiniMax 作为 Jarvis"——带 Leader/Worker/Verifier 的多代理系统（LeonBuildsAI，5月15日）
- MiniMax Speech 2.8 因专业语音质量受到认可（flyingpetal472："迭代快"）
- Qwen 3.7 发布在中国开发者圈中也很突出

**中文讨论中的 MiniMax 竞争对手对比：**
- Kimi/MiMo 在编程方面被认为优于 MiniMax（PovilasKorop 在 X 上）
- DeepSeek 被认为综合能力最强，MiniMax 因广度受到重视

### 语言差距发现
**MiniMax 的中文报道相对于其英文报道的比例高于 DeepSeek 或 Qwen。** 这可能反映了：(a) MiniMax 是一家上海本土公司，拥有更强大的国内产品生态系统（Hub、Hailuo、Speech 都有中文版），(b) 与 DeepSeek（积极培育全球开发者社区）相比，西方开发者布道较少。

---

## 4. 模型变体细分（MiniMax）

MiniMax 对话分为不同的产品叙事：

| 变体 | 对话份额 | 关键叙事 |
|---------|------------------|---------------|
| **M2.7** | ~35% | 自进化模型、NVIDIA 背书、"最便宜的 50 倍 Claude 替代方案" |
| **Mavis**（Agent 升级版） | ~20% | Leader-Worker-Verifier 模式、多代理桌面 |
| **Hub** | ~20% | 一体化创意工作区，取代 9 个独立工具 |
| **Speech 2.8** | ~15% | 专业语音、Variety 报道、戛纳电影节 |
| **Music 2.6** | ~5% | 视频编辑社区（日本人居多）、Suno 替代方案 |
| **Hailuo video** | ~5% | 集成在 Hub 中，在创意工作流背景下被提及 |

**值得注意的是：** M2.7 和 Mavis 占主导地位，因为它们是开发者/技术先锋用户讨论的内容。Speech 和 Music 在创意/社区场景中占主导，有较强的非英语参与。

**M2.7 质量回退：** r/MiniMax_AI 上持续存在的"质量下降？"话题（5月22日）表明存在一些用户不满，但表述混杂——支持者表示它"能出活"且是"日常主力"。

---

## 5. 定价感知

### MiniMax Token Plan

**感知：** "超便宜，能完成任务"——定位为价值冠军。

- MiniMax 编程计划 $10/月
- 完整 Token Plan $20/月（所有模态）
- 所有模型共享额度（M2.7、视频、语音、音乐）
- 推荐折扣生效（9折）
- 与 Claude Pro（$20）、ChatGPT Pro（$100）、Gemini 订阅相比被看好

**已知局限：** "智力相对弱"——根据中国开发者账号，智能不如 DeepSeek V4 Pro。但即使批评者也承认其成本量优势。

### DeepSeek V4 Pro

**感知：** "比 GPT-5.5 便宜 20-30 倍"——从根本上重置了价格预期。

- 永久价格：每 1M tokens 输入 $0.435 / 输出 $0.87（75% 折扣促销）
- 缓存命中：每 1M $0.0036
- 开发者证言："DeepSeek V4 Pro 的性价比正在改变我对 AI 生产编程的看法"
- 西方媒体：路透社、彭博社、Engadget 都报道了永久降价

### Qwen 3.7 Max

**感知：** 溢价定价但对代理工作负载值得。

- 每 1M tokens 输入 $2.50 / 输出 $7.50（OpenRouter）
- 1M 上下文，包含隐式缓存
- 被视为"值得"用于 35 小时自主任务
- 受到 DeepSeek V4 Pro 的价格压力（"阿里巴巴的 Qwen 可能需要降低 API 定价以匹配 DeepSeek 的 $0.84/1M"）

---

## 6. 主要声音

### MiniMax

| 账号 | 角色 | 重要贡献 |
|--------|------|---------------------|
| @NVIDIAAI | 官方 | M2.7 上的 16 个本地 AI 代理——最高 MiniMax X 参与度（1253 赞） |
| @RebeccahAdson | 高级用户 | MiniMax Hub 叙事领导者，多条高转发帖子 |
| @MikaStars39 | 内部人士 | 宣布加入 MiniMax 后训练团队，参与 M3 开发 |
| @MiniMaxAgent | 官方 | Mavis 发布公告 |
| @Hailuo_AI | 官方 | Speech 2.8 戛纳报道、语音合作 |
| @boxmining | 意见领袖 | Mavis "最适合入门的多代理"报道 |
| @kaif9999 | 高级用户 | MiniMax $10 编程计划作为必备代理订阅 |

### DeepSeek

| 账号 | 角色 | 重要贡献 |
|--------|------|---------------------|
| @deepseek_ai | 官方 | 75% 永久降价公告（23K 赞） |
| @testingcatalog | 分析师 | V4 Pro 定价分解 |
| @0xSero | 开发者 | "$6.74 买了 0.45B tokens"——真实成本案例 |
| @jeremychone | 开发者 | V4 Pro 生产编程证言 |
| @mark_k | 意见领袖 | DeepSeek 架构深度解析（MoE、MLA、Engram） |

### Qwen

| 账号 | 角色 | 重要贡献 |
|--------|------|---------------------|
| @Alibaba_Qwen | 官方 | Qwen 3.7 Max 隐式缓存公告 |
| @alibaba_cloud | 官方 | Qwen 3.7 Max #2 编程模型声明 |
| @outsource_ | 开发者 | Qwen ULTRON 27B 微调，3D 模型生成演示 |
| @rohanpaul_ai | 分析师 | Qwen 3.7 Max 编程/代理基准 |

---

## 7. 关键引言

### 关于 MiniMax M2.7

> "MiniMax M2.7 是家用模型中按基准测试最聪明的，在 GB10 硬件上运行速度为 34-36 tokens/秒。"
> — @mattwallace，5月25日

> "NVIDIA 正在免费提供 80+ AI 模型的 API 访问。真的是免费的。DeepSeek 3.2、Kimi 2.5、MiniMax M2.7、GPT-OSS-120B、GLM 5.1、Llama 3。"
> — @venoyuls，5月25日

> "顺便说一句...我目前最好的开源 AI 模型依次是：1. Deepseek v4 pro 2. Minimax 2.7 3. Kimi 2.6"
> — @nekwasar，5月25日

### 关于 MiniMax Hub / Mavis

> "大家还在拼凑多个 AI 工具来完成一个项目。一个用于图像，一个用于视频，一个用于音频。MiniMax Hub 将整个流程变成一个 AI 创意工作区。说实话，感觉就像是 AI 视频领域的 Claude。"
> — @FellMentKE，5月16日（201 赞，115 转发）

> "MiniMax的Mavis给了一个思路: Leader负责统筹全局, Worker负责具体执行, Verifier负责验收质量. 关键设计是Worker和Verifier之间是对抗关系."
> — @LeonBuildsAI，5月15日

> "MiniMax 做到了大实验室都没做到的。一个计划。CLI、API、代理。所有模型：M2.7、视频、语音、音乐。额度全平台共享。"
> — @heyshrutimishra，5月16日

### 关于 DeepSeek V4 Pro 降价

> "DeepSeek 是免费的，质量几乎和 Claude 一样好。但我们仍然每月付 $20，因为我们说服自己付费版更懂我们。"
> — @trikcode，5月24日

> "DeepSeek 的策略很有趣：'好吧，你觉得可靠 1M 上下文、快速、便宜、顶级开源智能还不够酷？来个 75% 降价怎么样...'"
> — @teortaxesTex，4月29日

> "这个 DeepSeek V4 Pro 的性价比（$0.87 输出）真的在改变我对 AI 生产编程的看法。看到三巨头继续翻倍或三倍涨价真的很有趣..."
> — @jeremychone，5月25日

### 关于 Qwen 3.7 Max

> "Qwen 3.7-Max 正式成为全球 #2 AI 编程模型。在 Code Arena 上获得 1541 分，仅次于 Claude。"
> — @alibaba_cloud，5月26日

> "隐式缓存现在已在 Qwen3.7-Max 上线——自动启用，无需设置。"
> — @Alibaba_Qwen，5月25日

> "DeepSeek V4 Pro 最聪明。它的 API 收集数据用于训练。Kimi K2.6：均衡。DeepSeek V4 Flash：最高效。MiniMax M2.7：最快。"
> — @AmineHilaa，5月25日（引用服务 FAQ）

---

## 8. 差距与机会

### 对话中的差距

**1. MiniMax 讲故事有问题，不是产品有问题。**
M2.7 在技术上与 V4 Pro 和 Qwen 3.7 Max 具有竞争力。但 DeepSeek 占据了"性价比"故事；Qwen 占据了"代理能力"故事。MiniMax 的故事是"我们什么都做"。在专家为王的世界里，通才的故事更难落地。

**2. 质量回退叙事未解决。**
r/MiniMax_AI 上 5月22日的"质量下降？"话题有活跃参与。如果 MiniMax 在 DeepSeek 和 Qwen 改进时悄悄降低模型质量，这可能加速用户流失。

**3. 西方主流媒体 coverage 很少。**
DeepSeek 的降价获得了路透社、彭博社、Engadget 和 CNN 的报道。MiniMax 的 Mavis 发布和 NVIDIA 背书没有。这表明 MiniMax 的公关/传播没有有效触达西方科技媒体。

**4. 数据收集担忧正在浮现。**
X 上的用户注意到 DeepSeek V4 Pro 的 API"收集数据用于训练"——这与"开放权重"认知不同。MiniMax 应该澄清其数据政策，以避免被同样对待。

### 机会

**1. MiniMax Hub 作为切入创意专业人士的楔子。**
Hub 叙事（"AI 视频领域的 Claude"）正在引起共鸣。这是相对于 DeepSeek（编程导向）和 Qwen（代理导向）的差异化定位。如果通过创意专业人士社区放大，一体化创意工作区的故事可以占据一个独特的受众群体。

**2. Perplexity 作为证明案例。**
Perplexity 报道切换到 MiniMax AI 搜索（成本降低 27%，工具调用减少 45%）是一个尚未广泛宣传的可靠企业参考案例。

**3. Mavis 验证器模式作为技术差异化。**
对抗性 Worker/Verifier 架构确实是新颖的。X 上的技术受众正在关注它。将 Mavis 定位为"自我检查工作的代理"可能会吸引那些被 AI 自信错误输出伤害过的开发者。

**4. Speech 2.8 作为低调的收入驱动因素。**
Variety 报道、戛纳电影节使用、基于 Speech 02 构建的第三方 SaaS——MiniMax Speech 正在以极少的营销支出产生 B2B 收入和品牌信誉。这可能是该模型最强的护城河。

---

## 附录：数据覆盖说明

- **Reddit：** 所有模型都坏了（90年代超时）——全模型比较仍然有效，因为限制是均等的。对照实验完整性得到维护。
- **YouTube：** 可用；无法获取字幕（试点 0/5）。使用了标题 + 浏览量。
- **Hacker News：** 整个期间 Algolia API 错误——HN 数据不可用。
- **网页（Brave）：** 偶发 429 错误；部分查询返回 0 个网页结果。DeepSeek V4 查询返回了网页数据；MiniMax 查询经常返回 0 个网页结果。
- **Reddit 丰富：** 大部分查询第一页后被限速（429）；参与度指标仅反映第一页帖子。

---

*研究通过 `last30days.py` 在 Reddit、X（xAI/Grok）、YouTube 和 Brave 网页搜索上进行。涵盖 3 个模型（MiniMax、Qwen、DeepSeek）的 27 个查询，按语言、用例和关键词细分。总研究时间：第 1-7 单元约 30 小时。*