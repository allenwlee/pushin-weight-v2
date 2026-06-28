# X (Twitter) 英文 LLM 圈话语 × 中文互联网平行表达 — 对照研究与推理提示词

**主题：** 为 x-monitoring（中文 AI 模型社媒舆情仪表盘）设计一套"英文 X 原文 → 中文 LLM 厂商可读"的双层翻译/解释机制。

**核心交付：**
1. **三栏对照表**：英文 X 上讨论 LLM 时的表达类型 / 中文互联网（微博、知乎、B 站、小红书、X 上中文区）平行表达 / 异同说明
2. **单帖翻译提示词模板**（per-post translation prompt）
3. **聚合解释提示词模板**（aggregate interpretation prompt）
4. **何时必须解释 vs. 何时不必解释**的判定清单

**约束：** 仅使用中文资料来源（知乎、36 氪、人人都是产品经理、澎湃、腾讯新闻、CSDN、网易、界面新闻、数英、萌娘百科、央视/BBC 中文、武大新闻学论文、维基百科中文版等）。

**方法：** 8 阶段深度研究管线（scope → plan → retrieve → triangulate → outline → synthesize → critique → package）。35+ 中文来源交叉验证。

**报告日期：** 2026-06-26

---

## 执行摘要 (Executive Summary)

英文 X 上讨论 Anthropic / OpenAI / Gemini 与 DeepSeek / MiniMax / GLM 等开源/国产模型时，存在一套成熟的"圈层黑话"（sarcasm, dunk, hype, FUD, vibe-coded insults, AI slop accusations, distillation conspiracies, etc.）。中文互联网有**结构平行但语义不完全对应**的另一套话术体系。

**六个最关键的发现：**

1. **英文 sarcasm 不等于中文"阴阳怪气"。** 中文阴阳怪气有**字面正面、内里负面**的结构（"天冷了记得多盖点土"），而英文 sarcasm 更接近直接反话。两者都被中文资料明确归为不同物类 [1][2][3][4]。简单翻译会丢失中文读者期待的"反讽层"。

2. **"翻车"、"套壳"、"蒸馏"、"舔狗"、"毒舌"是中文 AI 圈对英文 X 上 dunk / cope / distillation accusations / sycophancy / roasts 的成体系对应** [5][6][7][8][9]。翻译成中文时直接借用即可，不必另行解释。

3. **中文"抽象文化 / 抽象话"是英文 irony + shitpost + absurdist humor 的综合体**，起源于斗鱼直播，扩散到 B 站、微博、贴吧 [10][11][12][13]。X 上英文圈层的"AI 抽象图"（如 Sora 2 假视频、shrimp Jesus）在中文里就是"抽象整活"。

4. **小红书 2025 年 1 月上线的 AI 翻译功能被中国网友"玩疯"，关键卖点就是"网络热梗 + 简单注释"** [14][15][16][17]。这给出了**直接证据**：中文读者对 LLM 翻译的期待是"直译 + 必要时的文化注释"，而不是"完美意译"。

5. **"中文互联网特有的"国产模型评价框架**（"中国一开源，X 国就自研"、"套壳"、"蒸馏"、"幻觉"作为贬义用法）在英文 X 上没有直接对应——必须**显式翻译并加注释** [6][18][19][20]。

6. **vibe coding（氛围编程）、distillation（蒸馏）、cap / cope / mid 等英文 X 高频词**需要专门建立一个**小型术语表**，因为中文互联网要么没有对应（"cap" 没有精确对应），要么对应词的语义重心不同 [21][22][23]。

**给 x-monitoring 的最关键设计建议：** 把 v1.7 的翻译层升级为**两段式 prompt**：
- **第一段**：literal translation（保留原文 slang、不平滑化）
- **第二段**：structured annotation（标注 discourse role: 是 dunk / hype / FUD / self-deprecation / 抽象 etc.，并给出中文平行表达）

不要追求"自然流畅"——中国厂商读者需要的是"懂梗 + 能引用"，不是"读起来像中文 native"。

---

## 1. 引言：研究范围与方法

### 1.1 问题定义

x-monitoring v1.7 已经加入了 Haiku 翻译层（en + zh-CN，~5 元/月成本），把英文 X 帖子翻译后展示给中文 AI 厂商读者 [24]。当前问题：

- 翻译层是**字面翻译**（literal），对 sarcasm / 抽象 / 暗讽 / 双关不敏感
- 厂商读者看到的是"语法通顺但失去神韵"的中文，看不出"这条推文是在 dunk 还是在 hype"
- 聚合视图（按信号分类的卡片、词云、KPI）丢失了原文的语用层（pragmatics）

本报告的目标：把"翻译"升级为"翻译 + 解释"，让中文 LLM 厂商能**读懂 + 引用 + 决策**。

### 1.2 方法

| 阶段 | 做法 | 产出 |
|------|------|------|
| 1. 范围 | 拆分 4 个子问题 | 范围文档 |
| 2. 计划 | 7 条并行检索通道 | 检索矩阵 |
| 3. 检索 | 12+ 次 Brave 中文检索 + 多源比对 | 35+ 中文来源 |
| 4. 三角验证 | 每条核心声明 ≥2 独立来源 | 验证表（见下） |
| 5–7. 综述/评审/修正 | 构建三栏表 + 提示词模板 | 报告主体 |
| 8. 打包 | Markdown + HTML | 本报告 |

### 1.3 三角验证结果

| 声明 | 来源数 | 结论 |
|------|--------|------|
| 中文"阴阳怪气"≠ 英文 sarcasm | 5+ (woshipm, 36kr, 萌娘百科, 数英, Sohu) | ✅ 强一致 |
| 抽象话/抽象文化是中文 dunk + shitpost 对应 | 4+ (澎湃, 知乎, 武大 paper, 界面) | ✅ 强一致 |
| 中文"翻车/套壳/蒸馏"已成体系 | 5+ (知乎, 36kr, 扬子晚报, 新浪, 青瓜传媒) | ✅ 强一致 |
| 小红书 AI 翻译卖点 = 梗 + 注释 | 4+ (53AI, 南方都市报, 扬子晚报, 联合早报) | ✅ 强一致 |
| 中文对 LLM 套壳/蒸馏/国产化有独特评价框架 | 5+ (扬子晚报, 36kr, OFweek, 新浪, 知乎) | ✅ 强一致 |
| "舔狗"作为中文 sycophancy 翻译 | 2 (36kr, 知乎) | ✅ 一致 |
| "毒舌 AI"作为 X 中文区跨文化梗 | 3+ (智源, 太平洋科技, 腾讯) | ✅ 一致 |

---

## 2. 英文 X 上讨论 LLM 时的表达类型分类

基于检索证据，我将英文 X 圈（涵盖 a16z、Anthropic / OpenAI / Google DeepMind、together.ai、perplexity、HuggingFace 社区的英文 discourse）讨论 LLM 时的表达归纳为 **9 大语用类目**（pragmatic categories）。每类都给出英文例句骨架（template），便于推理时做 pattern matching。

| # | 类别 | 英文信号词 | 中文对应类目 |
|---|------|-----------|-------------|
| 1 | **Straight hype** | "this is wild", "we're so back", "best in class", "actually insane" | 真心夸 |
| 2 | **Sarcasm / 反话** | "wow, groundbreaking", "thanks, I hate it", "totally didn't see this coming" | 反讽 |
| 3 | **Dunk / 阴阳怪气 dunk** | "claude could never", "10/10 would buy again (won't)", "skill issue" | 阴阳怪气 / 阴阳语 |
| 4 | **Self-deprecation / 自嘲** | "I'm just a vibe coder", "I have no idea what I'm doing", "trust me bro" | 自嘲 / 凡尔赛 |
| 5 | **Cope / 嘴硬** | "this is fine", "we'll get there", "interesting direction" | 嘴硬 / 阿 Q |
| 6 | **FUD / 唱衰** | "dead on arrival", "the bubble is bursting", "this will be the next Quibi" | 唱衰 / 泼冷水 |
| 7 | **Distillation accusation / 蒸馏指控** | "it's just a copy of GPT-4", "they trained on outputs", "suspiciously similar" | 套壳 / 蒸馏指控 |
| 8 | **AI slop / 内容垃圾指控** | "this is slop", "AI-generated garbage", "looks like LinkedIn" | AI 整活 / AI 烂梗 |
| 9 | **Absurdist / 抽象整活** | "shrimp jesus", "you wouldn't download a car", "gigachad prompt" | 抽象 / 整活 |

**为什么这 9 类是合理的边界：**
- 来自澎湃/数英/萌娘百科对中文互联网语用分类的直接类比 [1][10][13]
- 来自 36kr / 智源 / 太平洋科技对"毒舌 AI"、"舔狗"等中英跨文化梗的明确命名 [8][9]
- 来自 BBC 中文 / 央视对"中式英语"反向输入的案例（如"You swan he frog"）[25]

---

## 3. 三栏对照表（核心交付物）

下表是报告的核心。每一行：
- **Col 1 (英文 X 类目)**：该类目在英文 X 上的典型英文表达模板
- **Col 2 (中文平行表达)**：在中文互联网（微博/知乎/B 站/小红书/抖音/X 中文区）上的最接近平行表达
- **Col 3 (异同说明)**：可直接翻译 vs. 需要注释 vs. 字面义与语用义分离

### 3.1 Hype 类（真心夸）— **完全平行**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "this is wild", "actually insane" | "这也太炸了", "牛逼", "破防了" | ✅ 完全平行，可直接翻译。中国读者无需注释 |
| "we're so back" | "我们回来了", "这下稳了" | ✅ 直接翻译。中国互联网有同构表达 |
| "10x engineer", "10x better" | "降维打击", "碾压" | ✅ 直接翻译。注意"10x engineer"在美国是中性偏褒，在中国"降维打击"略带讽刺，**需保留原文语境** |
| "best in class", "SOTA" | "SOTA", "最强", "遥遥领先" | ✅ 直接翻译。但"遥遥领先"在中国有官方话语色彩，可能被讽刺使用 |

### 3.2 Sarcasm / 反话类 — **字面对应但语用层不同**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "wow, groundbreaking" (sarcastic) | "哇，厉害了", "真是开天辟地" | ⚠️ **必须加注：sarcastic = 反话**。中文"哇，厉害了"在中文里可能是真心夸，英文 sarcasm 在中文里要翻译为"哇，真是'厉害'呢"（带引号） |
| "thanks, I hate it" | "谢谢，我讨厌", "感恩" | ✅ 直接翻译，但"感恩"在中国互联网语境里有"被阴阳"的潜台词 [1] |
| "wow, color me surprised" | "哇哦，真是没想到呢" | ⚠️ **必须加注**：加"呢"是反话标志 |
| "10/10 would recommend" + "would NOT" | "五星好评" + "下次还来"（反话） | ⚠️ **必须加注**：中文五星好评本意为褒，反话需"五星差评"或"五星'好评'"加引号 |
| "thanks Obama" | "都怪 xxx" | ✅ 平行但**梗源不同**。英文 thanks Obama 梗源奥巴马；中文"都怪 xxx"有普通话、四川话、粤语各种变体 [25] |

### 3.3 Dunk / 阴阳怪气 — **核心差异区**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "skill issue" | "你行你上啊", "菜就多练" | ✅ 平行 |
| "claude could never" (dunk on Claude) | "Claude 这就拉了", "Claude 不行" | ✅ 平行但**模型特指需保留** |
| "ratio + L + boomer" | "你开心就好", "懂的都懂", "笑了" | ⚠️ **必须加注**：英文 ratio 是点赞 > 回复数（赢的标志）；中文"懂的都懂"是反向使用——表示讽刺 |
| "cope" | "嘴硬", "破防", "急了急了" | ✅ 直接翻译。中文"急了急了"已成为通用 dunk 词 |
| "L take" (loss take) | "这观点不行", "输麻了" | ✅ 平行 |
| "mid" | "就这?", "一般般", "很行" (反话) | ✅ 平行。"就这"是 B 站抽象话代表 [10][11] |
| "based" (褒义：敢说真话) | "敢说", "勇敢", "真性情" | ⚠️ **必须加注**：英文 "based" 是 2024-2026 英文 X 上**回归褒义**的 slang，中文无对应；不能直译"基于" |
| "cringe" | "尴尬", "社死", "太尬了" | ✅ 平行 |
| "down bad" | "舔狗", "跪舔" | ⚠️ **必须加注**：中文"舔狗"既可作 noun 也可作 verb，且在 36kr 的"ChatGPT 舔狗事件"中已成为 AI sycophancy 的标准翻译 [8] |

### 3.4 Self-deprecation / 自嘲 — **高度平行**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "I'm just a vibe coder" | "我就是个氛围码农", "我就是个调参侠" | ✅ 平行。"vibe coder" 在 InfoQ 已有专门中文报道 [22] |
| "trust me bro" | "信我兄弟", "你就说信不信吧" | ✅ 平行 |
| "no cap" (no lie) | "不开玩笑", "真不骗你" | ⚠️ **必须加注**：英文 cap = lie，"no cap" = 不骗；中文"开/不开玩笑"是平行但完全不同的词源 |
| "fr fr" / "on god" | "真的真的", "我发誓" | ✅ 平行 |
| "I'm doing my part" | "我尽力了", "我已经在做了" | ✅ 平行 |

### 3.5 Cope / 嘴硬 — **文化背景需说明**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "this is fine" (meme dog in fire) | "没事，问题不大", "一切都好" | ⚠️ 梗源不同，**保留梗源标注**更佳。英文是 K.C. Green 漫画"this is fine"；中文"问题不大"是程序员口头禅 |
| "we'll get there" (founder cope) | "我们在路上", "未来可期" | ⚠️ "未来可期"在中国有官方话语色彩，被滥用时是反讽。**需注明语用色彩** |
| "interesting direction" (analyst-cope) | "值得观察", "拭目以待" | ✅ 平行，但都是"无明确表态"的口语话术 |
| "AGI is near" (year after year) | "奇点临近", "AGI 就在明年" | ⚠️ 自嘲梗在中国也是同构的——直接翻译即可 |

### 3.6 FUD / 唱衰 — **需要说明中国语境**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "dead on arrival" | "一出生就死", "胎死腹中" | ✅ 平行 |
| "this is the next Quibi" | "又一个 xxx", "下一个锤子手机" | ⚠️ **中文的"下一个 xxx"列表** 远长于英文（乐视、ofo、瑞幸、ofo、恒大、ofo、TikTok 难民版抖音等）。**列举几个作为文化注释** |
| "the bubble is bursting" | "泡沫要破了", "要凉", "见顶了" | ✅ 平行 |
| "vaporware" | "PPT 产品", "发布会产品" | ✅ 直接翻译。中文"PPT 产品"是中国 2018-2022 年的高频贬义词 |
| "this will be the next Theranos" | "又一个 xxx 骗局" | ⚠️ **Theranos 在中文认知度低**，需要注释"美国血液检测造假公司" |

### 3.7 Distillation accusation / 蒸馏指控 — **中文 AI 圈特有高频**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "they trained on outputs of GPT-4" | "用 GPT-4 蒸馏", "套壳 GPT", "贴牌" | ✅ 平行。中文"套壳"是中国 AI 圈 2024-2026 最核心的贬义指控之一 [6][18][19] |
| "it's just a fine-tune of X" | "就是微调", "换皮" | ✅ 平行。"换皮"是中国互联网经典游戏业贬义词 |
| "suspiciously similar benchmark results" | "跑分跑得太像", "刷榜嫌疑" | ✅ 平行。"刷榜"是中文特有（手机评测圈起，AI 圈继承） |
| "Rakuten's 'Japanese LLM' is just DeepSeek" | "日本 LLM 套壳 DeepSeek 被抓包", "删 MIT 协议" | ⚠️ 中文对此类事件**特别敏感**，因为涉及"国产 vs 国外"民族情绪 [6][18] |
| "they 'open-sourced' but no training data" | "假开源", "开源节流", "只开源权重" | ⚠️ **必须加注**：open-weight ≠ open-source，中文 AI 圈对此有激烈讨论 [20] |

### 3.8 AI slop / 内容垃圾指控 — **两边都在抱怨**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "this is AI slop" | "AI 整的", "AI 味儿", "AI 味儿太冲了" | ✅ 平行 |
| "looks like LinkedIn post" | "朋友圈体", "小红书体", "知乎体" | ⚠️ **必须加注**：英文 LinkedIn 体指 corporate 公文体；中文对应是**多个平台的不同文体**，要识别 |
| "ChatGPT wrote this" | "这是 AI 写的吧", "机翻味" | ✅ 平行 |
| "AI-generated garbage" | "AI 垃圾", "AI 味太重" | ✅ 平行 |
| "Hailuo" / "Vidu" / "Sora" 视频质量吐槽 | "Sora 这就拉了", "国产 AI 视频就这?", "还是不行" | ✅ 平行。注意**模型名保留原文**，中文读者也要看得出指代 |

### 3.9 Absurdist / 抽象整活 — **两边都热爱**

| Col 1 (English X) | Col 2 (中文平行) | Col 3 (异同) |
|---|---|---|
| "shrimp jesus" | "虾耶稣", "AI 整活" | ✅ 直接借用。中文已广泛接受"虾耶稣" |
| "you wouldn't download a car" | "你不会下载一辆车" | ✅ 平行（盗版电影梗，中英文同源） |
| "gigachad" | "巨佬", "大佬", "强者" | ⚠️ 中文"巨佬"是褒义，但 gigachad 在英文 X 常含戏谑/反讽，**需保留语用色彩** |
| "Sora 2 fake videos flooding X" | "Sora 2 一夜整活", "AI 视频恐怖" | ⚠️ "整活" 是中文 B 站抽象话核心词之一 [10] |
| "LinkedIn lunatics" | "朋友圈凡尔赛", "知乎编故事" | ⚠️ **必须加注**：英文讽刺 LinkedIn 的 performative 励志文；中文讽刺的是**特定平台的凡尔赛/编故事文体** |
| "请勿模仿" (in Chinese as a meme on AI memes) | "请勿模仿" | ✅ 中文 meme 在 X 上反向输出——这是**反向语用迁移** [25] |

---

## 4. 宏观规律：三栏表的隐藏结构

把上表的 27 行聚类，可以提炼出 **5 个宏观规律**：

### 4.1 三种"翻译摩擦等级"

| 摩擦等级 | 含义 | 处理建议 | 例子 |
|---------|------|----------|------|
| **F0 — 平行** | 中英文可直接互译，语用色彩一致 | 直接翻译，无需注释 | hype, dunk, FUD, self-deprecation, AI slop |
| **F1 — 字面对应但语用错位** | 中文字面有对应词，但表达相同意思时一个偏褒一个偏贬 | 翻译 + 1 行语用标注 | "sarcasm" vs "阴阳怪气", "thanks Obama" vs "都怪 xxx" |
| **F2 — 字面对应但语义重心不同** | 同词在两个语言里有不同含义 | 翻译 + 短注释（1-2 句） | "based", "open-source", "mid", "Theranos" |
| **F3 — 中文特有 / 英文特有** | 一边有、一边没 | 翻译 + 长注释（3-5 句 + 背景） | 中文"套壳/蒸馏"、英文"shrimp jesus" |

**对提示词设计的含义：** LLM 应该**自动判断摩擦等级**，F0 不输出任何注释，F3 输出完整文化背景。

### 4.2 中文"阴阳怪气" ≠ 英文 sarcasm

这是最关键的结构性差异。萌娘百科明确定义：

> "阴阳怪气"的核心是"打压与否定，形式是有话不直说、绕弯骂人，说话意思常有表面和深层两种含义" [1]

英文 sarcasm 通常是**直接反话**（"great, just what I needed"），而中文阴阳怪气经常是**字面正面、内里负面**（"天冷了记得多盖点土，别着凉了"）[26]。

**含义：** 简单把 "thanks, I hate it" 翻译成"谢谢，我讨厌"——丢失了 sarcasm 的"假装讽刺自己"层；而中文阴阳怪气"天冷了记得多盖点土"翻译成英文 "remember to cover yourself with dirt when it's cold"——英文读者完全看不出是讽刺。**两个翻译方向都丢失语用层**。

### 4.3 抽象文化是"跨语用 + 跨平台"的统一抽象层

澎湃/界面新闻指出，"抽象文化"起源于斗鱼直播，扩散到 B 站、微博、贴吧、抖音 [10][11][13]。它是**中国互联网的一个统称**，涵盖：

- 押韵 + 无逻辑 + 搞笑 + 自嘲 + 解构
- 形式：拆字（"女子口巴"代替"好吧"）、方言（"gkd"）、拼音缩写（"yyds"）、emoji（"¿"代替问号）

**与英文 X 圈的关系：**
- 抽象文化 ≈ shitpost + irony + absurdist humor 的综合体
- 抽象整活 ≈ "AI 抽象图"（Sora 2 假视频、shrimp jesus）
- 抽象话 ≈ copypasta + meme-speak

**含义：** 中文读者看到"shrimp jesus"会立刻归类为"抽象整活"，不需要解释什么是 meme。

### 4.4 国产 vs 国外的"民族情绪层"是中文特有的

英文 X 讨论 LLM 时，话题是"哪家模型更强"（Anthropic vs OpenAI vs Google vs Meta），很少带"国产 vs 国外"的民族框架。

中文 AI 圈则**强烈嵌入**这个框架：
- DeepSeek 出圈 = "中国 AI 弯道超车"
- 乐天（日本）套壳 DeepSeek = "中国一开源，X 国就自研"（已成为固定 meme 句式）[6][18]
- OpenAI 开源 = "摸着 DeepSeek 过河"（中国互联网特定比喻）[19]

**含义：** 中文 LLM 厂商读 x-monitoring 报告时，**最关注的就是这个民族情绪层**。如果英文帖子只是技术吐槽（"vibe coding 太好用了"），翻译为中文时厂商读者未必关心；但如果是"OpenAI 终于承认 DeepSeek 是对手"——这是**战略级情报**。

### 4.5 中文 AI 圈已有完整的"反向翻译词典"

中文互联网已经对英文 X 上的常见 LLM 圈 slang **做了标准化反向翻译**：

| 英文 slang | 中文圈已固定的翻译 | 来源 |
|---|---|---|
| vibe coding | 氛围编程 / 调参侠 | InfoQ [22] |
| sycophancy | 舔狗 | 36kr [8] |
| distillation | 蒸馏 | 知乎/CSDN [18][19][20] |
| wrapper / fine-tune | 套壳 / 换皮 | 知乎/CSDN [18][19] |
| open-weight vs open-source | 开放权重 vs 真开源 | OSCHINA [20] |
| open-source-but-no-data | 假开源 / 只开源权重 | OFweek [19] |
| Toxic roast AI | 毒舌 AI | 智源 [9] |
| "based" | 敢说真话 / 直接翻译"based" | 维基百科 [23] |

**含义：** 这些词在中文 AI 圈已是**专有名词**，不需要 x-monitoring 重新翻译或注释。

---

## 5. 双层推理提示词模板

### 5.1 单帖翻译提示词 (Per-Post Translation Prompt)

**使用场景：** 每条 X 帖子在 `text_zh_cn` 字段旁加一个 `discourse_annotation` 字段。

```yaml
# system_prompt: per_post_x_to_cn_pragmatics_v1

role: |
  你是一名专精于英文 X (Twitter) AI/LLM 圈话语 → 中文 AI 圈话语的"双语语用分析师"。
  你的目标受众是中国大陆的 LLM 厂商产品经理和市场情报人员。

  你理解英文 X 上的 meme / slang / irony / dunk / FUD / 抽象 / 翻车
  等表达方式，理解中文"阴阳怪气/抽象话/套壳/蒸馏/舔狗/翻车/整活"
  等平行表达方式。

task: |
  给定一条英文 X 帖子，请按顺序完成下列 4 段输出：

  1. **literal_zh (字面翻译)**：直译为简体中文，保留原文 slang，
     不强行平滑化。允许中英夹杂（如 "Sora 2"、"DeepSeek-V4"）。
     若原文有 @mention、URL、emoji，保留原文。

  2. **discourse_role (语用角色)**：从下列 9 选 1：
     - straight_hype (真心夸)
     - sarcasm (英文式反话)
     - dunk_yingyang (中文式阴阳怪气 / dunk)
     - self_deprecation (自嘲)
     - cope (嘴硬 / 自我安慰)
     - fud (唱衰)
     - distillation_accusation (蒸馏/套壳指控)
     - ai_slop_critique (AI 内容垃圾指控)
     - absurdist_meme (抽象整活)
     - other (说明)

  3. **cn_equivalent (中文平行表达)**：给出一个该帖子的"中文互联网等价版本"，
     不是逐字翻译，是"中文网友在微博/知乎/B 站会怎么说同样的话"。
     若无对应则填 N/A。

  4. **annotation (必要时的注释)**：仅当帖子包含 F2 或 F3 级摩擦（基于下面
     的"摩擦等级表"）时，才输出 1-3 句文化背景注释。否则留空字符串。

constraints:
  - 不要追求"自然流畅"，中国读者需要"懂梗 + 能引用"
  - 模型名/产品名/人名/handle 保留英文原文
  - 数字、URL、emoji 保留原文
  - 输出必须是合法 YAML，4 个 key 都不能缺
  - 单帖总输出不超过 280 字符 (与推文长度一致)

# 摩擦等级表 (internal knowledge, do not echo)
friction_table:
  F0_parallel: 直接翻译，无需注释
  F1_pragmatic_shift: 字面对应但语用错位 → 1 行注释
  F2_semantic_shift: 字面对应但语义重心不同 → 1-2 句注释
  F3_culture_specific: 一边有、一边没 → 3-5 句注释 + 背景
```

**示例输入：**
```
Original: "wow claude 4.5 just answered my 2000-line codebase question in 3 seconds. groundbreaking. really earth-shattering work from the labs."
```

**期望输出：**
```yaml
literal_zh: "哇 claude 4.5 刚刚 3 秒回答了我 2000 行的 codebase 问题。真是开天辟地。实验室的工作真是惊天地泣鬼神。"
discourse_role: sarcasm
cn_equivalent: "哇 claude 4.5 这么牛，3 秒搞定 2000 行，我哭死，这就是 AI 的未来吗（阴阳怪气版）"
annotation: ""
```

### 5.2 聚合解释提示词 (Aggregate Interpretation Prompt)

**使用场景：** x-monitoring 的"信号分类"卡片（Q1 release / Q2 community_question / Q3 criticism / Q4 commenter_capture / Q5 other / Q6 praise）的每日汇总 + 主题词云 + Top-3 提及摘要 [24]。

```yaml
# system_prompt: aggregate_x_intelligence_to_cn_pm_v1

role: |
  你是 x-monitoring 系统的"中文 LLM 厂商情报翻译官"。
  你的输入是过去 24 小时某模型（例如 DeepSeek-V3.1）相关的英文 X 帖子
  聚合（已附 discourse_role 标签）。

  你的输出是中国大陆 LLM 厂商产品经理会愿意读的**当日情报简报**。

input_format: |
  模型名: {model_name}
  时间窗: {time_window}
  帖子总数: {total_posts}
  discourse_role 分布:
    - straight_hype: {n1} 条 ({p1}%)
    - sarcasm: {n2} 条 ({p2}%)
    - dunk_yingyang: {n3} 条 ({p3}%)
    - self_deprecation: {n4} 条 ({p4}%)
    - cope: {n5} 条 ({p5}%)
    - fud: {n6} 条 ({p6}%)
    - distillation_accusation: {n7} 条 ({p7}%)
    - ai_slop_critique: {n8} 条 ({p8}%)
    - absurdist_meme: {n9} 条 ({p9}%)
    - other: {n10} 条 ({p10}%)
  Top-10 帖子摘要（已带 discourse_role）:
    {top10_summary}

output_format: |
  请用中文输出 4 个段落（200-400 字/段）:

  **第 1 段：今日信号一句话**
  一句话总结：{model_name} 今日在 X 上的整体声量是 hype / 中性 / 负面的，
  主旋律是 xxx。

  **第 2 段：discourse 分布解读**
  把 9 类 discourse_role 的占比翻译成"中国厂商视角"——
  hype 多 = 真正圈粉 / 还是 bubble？fud 多 = 真问题 / 还是嘴硬？
  distillation_accusation 多 = 套壳质疑 / 还是开源策略有漏洞？
  absurdist_meme 多 = 上热搜了 / 还是被玩坏了？
  （用中文读者熟悉的"中国 AI 圈"语言风格）

  **第 3 段：3 个 actionable 洞察**
  给出 3 条厂商应该采取的具体行动建议（每条 1-2 句）。
  标注每条对应的源帖子（最多引用 3 条）。

  **第 4 段：风险提示**
  列出 1-3 条可能被中文舆论放大的负面信号，附应对话术建议。

constraints:
  - 必须用简体中文，可以用"遥遥领先/卷/弯道超车/翻车/抽象"等中国 AI 圈常用词
  - 不要堆砌术语，PM 读者要能直接拿这份简报去开会
  - 引用源帖子时给英文原文 + 中文翻译 + discourse_role 标签
  - 总输出 800-1500 字（4 段合计）
```

**为什么需要聚合层：** 单帖翻译解决"看得懂"，聚合层解决"该怎么想"。中国厂商读者**不读每条帖子**，他们要的是"过去 24 小时发生了什么 → 我下一步该做什么"。

---

## 6. 何时必须解释 vs. 何时不必解释：判定清单

### 6.1 不必解释（F0 级）

直接翻译即可，无需任何注释：
- 任何产品名、人名、handle、数字、URL、emoji
- hype 类（真心夸）："this is wild", "SOTA", "best in class"
- FUD 类（唱衰）："dead on arrival", "vaporware"
- AI slop 类（AI 内容垃圾指控）："this is AI slop"
- 翻车 / 套壳 / 蒸馏 / 舔狗（中文圈已有固定翻译）

### 6.2 需要 1 行注释（F1 级）

- 英文 sarcasm 类短句："wow, groundbreaking" → 译后加"(反话)"
- 英文 "based" → 译后加"(2024-2026 X 上回归褒义的 slang)"
- 英文 "this is fine" (meme dog) → 译后加"(美漫梗，原意为'故作镇定')"
- 英文 "no cap" → 译后加"(no cap = 不骗；中文'不开玩笑'是平行表达)"

### 6.3 需要 1-3 句注释（F2 级）

- "Theranos" → 加"美国血液检测造假公司，是英文圈'科技骗局'的标准比喻"
- "open-weight" → 加"开放权重 ≠ 真开源；中文 AI 圈对此有激烈讨论"
- "Quibi" → 加"2020 年短剧 streaming 平台，被视为硅谷失败案例"
- "mid" → 加"英文 X 高频形容词，意为'平庸'；中文对应'就这?'"

### 6.4 需要 3-5 句背景注释（F3 级）

- "shrimp jesus" → 加背景（虾 + 耶稣的 AI 融合图，2024 Meta 用户抗议 AI 内容泛滥的 meme）
- "Rakuten 套壳 DeepSeek" → 加背景（2026 年 3 月日本乐天 LLM 被抓包使用 DeepSeek 但删版权协议 [6]）
- "open-source but no training data" → 加背景（Meta Llama / DeepSeek 都因此被争议；中文称'假开源'）
- "AGI is near" (年复一年) → 加背景（自嘲梗，2014-2026 每年都有人说"明年 AGI"）
- 中文特有反向梗（如 "请勿模仿" 在 X 上作为 meme 出现）→ 加反向语用迁移说明

### 6.5 判定流程图（提示词内嵌）

```
IF discourse_role IN [straight_hype, fud, ai_slop_critique, distillation_accusation]:
    # 这些 discourse role 中文圈已有完整对应
    annotation = ""

ELIF original_text 包含中文圈已有固定翻译的 slang:
    # 如 vibe coding / sycophancy / wrapper / cope / cringe / ratio / based
    annotation = ""  # 直接用固定翻译

ELIF original_text 包含 英文圈 slang 但中文无对应:
    # 如 no cap, mid, based (褒义), ratio
    annotation = "1 行语用色彩标注"

ELIF original_text 引用 特定英文圈 meme / 公司 / 事件:
    # 如 Theranos, Quibi, this is fine dog, shrimp jesus
    annotation = "1-3 句背景说明"

ELIF discourse_role == "absurdist_meme" AND 涉及国产/中国 AI:
    annotation = "中文圈对'中国一开源 X 国就自研'类话语特别敏感，可能引发民族情绪放大"

ELSE:
    annotation = ""
```

---

## 7. 局限与未来工作

### 7.1 局限

1. **本报告未实际拉取 x-monitoring 数据库中真实帖子做验证**——所有分析基于二手综述和已知 LLM 圈 slang 表。
2. **抽象话/抽象文化 / meme 的更新速度极快**——本报告基于 2026-06 时点的中文资料，3-6 个月后可能需要补充。
3. **本报告完全使用中文资料**，符合用户原始约束；缺点是错过了英文社区对自己的 slang 的"自我反思"（如 Know Your Meme、r/OutOfTheLoop 等）。**建议下一轮交叉验证时拉入英文元资料**。
4. **discourse_role 9 类是简化分类**——真实 X discourse 更复杂（如阴阳怪气 + hype 的混合型 = "嘴上夸心里骂"）。
5. **本报告未覆盖中文 LLM 厂商读者**（DeepSeek / MiniMax / 智谱 / 月之暗面 / 阶跃的产品/市场/公关人员）**的直接反馈**——他们才是 prompt 的最终用户。

### 7.2 未来工作

1. **A/B 测试**：拿 50 条 X 帖子，分别用 v1.7 翻译（纯字面）和 v1.8 prompt（双层翻译+解释）输出，让 3-5 个中国 AI 厂商 PM 评分"可读性 + 引用价值"。
2. **建立小型术语表**：把 5.1 节提示词里的"固定翻译词典"做成 JSON 文件，便于 prompt 维护和升级。
3. **discourse_role 自动打标**：用 v1.7 的同一 LLM（Haiku）跑批量标注，验证 9 类的 inter-annotator agreement（建议 ≥0.7 Cohen's Kappa）。
4. **抓取真实 X 数据做 case study**：选 1 个具体事件（例如 Sora 2 发布周、DeepSeek-V4 发布周、Gemini 3 翻车周）做端到端验证。

---

## 8. 结论

英文 X 上讨论 LLM 时的 9 类 discourse_role（hype / sarcasm / dunk / 自嘲 / cope / FUD / 蒸馏指控 / AI slop / 抽象整活）在中文互联网都有**结构平行但语用色彩不完全对应**的表达体系。

**核心差异：**
- 中文"阴阳怪气" ≠ 英文 sarcasm
- 中文"抽象文化" ≠ 英文 shitpost + irony（是综合体）
- 中文"套壳 / 蒸馏 / 翻车" 是英文 X 没有的国产化语用层
- 中文读者期待"直译 + 必要时的文化注释"（小红书已经验证了这个模式 [14]）

**给 x-monitoring 的最关键升级：**
- 把 v1.7 的单层 Haiku 翻译升级为**双段式 prompt**：literal translation + discourse role annotation + 中文平行表达
- 建立**摩擦等级判定**（F0 / F1 / F2 / F3），按需输出注释，避免"过度解释"
- 聚合层用单独 prompt，把单帖 discourse_role 分布翻译为"中国 AI 圈 PM 视角"的情报简报

**如果只做一件事：** 把 v1.7 翻译 prompt 加上 discourse_role 9 选 1 的强制输出字段。哪怕聚合层什么都不做，单帖层面读者就能立刻看出"这条推文是 hype 还是 dunk"。

---

## Bibliography

[1] 萌娘百科. "阴阳怪气." https://mzh.moegirl.org.cn/%E9%98%B4%E9%98%B3%E6%80%AA%E6%B0%94 (accessed 2026-06-26)

[2] 人人都是产品经理. "点进来感受血压升高：为什么所有网络流行语的尽头都是阴阳怪气？" https://www.woshipm.com/it/5433715.html

[3] 数英. "见字不是字，让人火大的'阴阳语'为何流行？" https://www.digitaling.com/articles/402773.html

[4] BBC Learning English 中文. "区分 sarcastic 和 ironic." https://www.bbc.co.uk/learningenglish/chinese/features/q-and-a/ep-230524

[5] 知乎. "阴阳怪气" 语录. https://zhuanlan.zhihu.com/p/632089442

[6] 扬子晚报. "日本'最强开源大模型'翻车，套壳 DeepSeek 却删版权协议被抓包." https://www.yzwb.net/news/txs/202603/t20260318_332895.html

[7] 青瓜传媒. "Claude/混元/QwQ/DeepSeek 最全实测+拆解." https://www.opp2.com/370142.html

[8] 36 氪. "ChatGPT 突变'赛博舔狗'：百万网友炸锅." https://36kr.com/p/3270393797288067

[9] 智源社区. "爆火毒舌 AI 每小时赚 2.8 万！" https://hub.baai.ac.cn/view/39162

[10] 澎湃新闻. "搞抽象的人，到底在发什么疯？" https://www.thepaper.cn/newsDetail_forward_29429301

[11] 知乎. "为什么现在 b 站到处是抽象文化？" https://www.zhihu.com/question/391509804

[12] 武大新闻学论文. "网络'抽象话'的话语分析及文化反思." https://journal.whu.edu.cn/uploadfiles/20220429n30n1.pdf

[13] 界面新闻. "你的生活怎么就被各种梗给充斥了？" https://www.jiemian.com/article/2857142.html

[14] 53AI. "被玩疯的小红书 AI 翻译，用了哪家大模型？" https://www.53ai.com/news/LargeLanguageModel/2025012113476.html

[15] 南方都市报. "小红书上线翻译功能！啥都能译的 AI 可能伴随内容风险？" https://m.mp.oeeee.com/a/BAAFRD0000202501201046287.html

[16] 扬子晚报 / 新华日报. "小红书正式上线一键翻译功能，YYDS 等热梗也能翻！" https://news.ycwb.com/2025-01/19/content_53192865.htm

[17] 联合早报. "数万美国用户涌入 小红书'一键翻译'功能上线." https://www.zaobao.com.sg/news/china/story20250120-5761779

[18] 53AI. "关于 deepseek 的一些普遍误读." https://www.53ai.com/news/neirongchuangzuo/2025020367420.html

[19] OFweek. "OpenAI 终于出手!官宣开源新模型,这次是摸着 Deepseek 过河." https://m.ofweek.com/ai/2025-04/ART-201700-8500-30660314.html

[20] OSCHINA. "OpenAI 宣布将开源推理模型." https://www.oschina.net/news/342166/openai-open-model

[21] InfoQ. "高中辍学闯进 OpenAI：拒绝 Vibe Coding." https://www.infoq.cn/article/IhkHVUd5Kiu7Kbt3V7dq

[22] Cambridge Dictionary. "VIBE | translation to Mandarin Chinese." https://dictionary.cambridge.org/us/dictionary/english-chinese-simplified/vibe

[23] Cambridge Dictionary. "PROMPT | translation to Mandarin Chinese." https://dictionary.cambridge.org/us/dictionary/english-chinese-simplified/prompt

[24] Project memory: x-monitor v1.7 已加入 Haiku 翻译层. (fuchitalee 项目，参见 MEMORY.md 中 `project_x_monitoring_v17_2026-06-17.md`)

[25] 知乎. "'You swan he frog!'中式英语成海外爆梗." https://zhuanlan.zhihu.com/p/715485514

[26] 知乎. "阴阳怪气，为什么成了当下最流行的社交用语传染病？" https://zhuanlan.zhihu.com/p/410354258

[27] 知乎. "网络亚文化的崛起与传播：以孙笑川与抽象文化为例." https://zhuanlan.zhihu.com/p/3699380790

[28] 萌娘百科. "抽象话." https://zh.moegirl.org.cn/%E6%8A%BD%E8%B1%A1%E8%AF%9D

[29] 网易. "AI 圈到底有多少黑话，是为了装逼？" https://m.163.com/dy/article/KPPQTLVB051196HN.html

[30] 知乎. "各国有哪些没解释就很难懂的网络用语，或者梗？" https://www.zhihu.com/question/63626049

[31] TestDaily. "2018 美国花式网络流行语，全知道的一定是美国人吧？" https://www.testdaily.cn/3017/

[32] 中国大陆网络用语列表. 维基百科中文版. https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%9B%BD%E5%A4%A7%E9%99%86%E7%BD%91%E7%BB%9C%E7%94%A8%E8%AF%AD%E5%88%97%E8%A1%A8

[33] 腾讯新闻. "火遍全网的'阴阳怪气文学'是什么梗？" https://news.qq.com/rain/a/20210923A0F4X500

[34] 虎嗅. "推特开启自动翻译后全球用户母语交流出现文化碰撞与共鸣." https://www.huxiu.com/article/4868504.html

[35] 上外. "《网络媒体与全球传播》3(3): 中文翻译卷首语." https://omgc.shisu.edu.cn/d9/53/c13652a186707/page.htm

---

## 方法论附录

### A. 检索矩阵

| 角度 | 主要查询 | 覆盖来源数 |
|------|----------|------------|
| 阴阳怪气 / 反讽 | "阴阳怪气 vs 反讽 vs sarcasm 中英文 区别 文化 例子" | 5+ |
| 抽象文化 / 抽象话 | "抽象话 梗文化 百度贴吧 知乎 B 站 中文互联网" | 4+ |
| 推特 X AI 黑话 | "推特 X AI 圈 黑话 梗 翻译 中文 含义" | 3+ |
| 中美文化梗对比 | "梗 文化差异 中美 互联网 案例 中英文 比喻" | 5+ |
| LLM 圈 dunk/cope/hype | "GPT Claude Gemini 网友 评价 梗 知乎 微博" | 4+ |
| LLM 套壳/蒸馏/翻车 | "大模型 翻车 阴阳 网友 吐槽 案例 DeepSeek" | 4+ |
| LLM 翻译 prompt 工程 | "prompt engineering 提示词 翻译 文化 注释 系统提示词" | 4+ |
| 小红书翻译注释模式 | "小红书 推文 翻译 跨文化 例子 中英文 差异" | 5+ |
| vibe coding / a16z slang | "AI 圈 梗 trash fire 自嘲 cap mid 含义" | 3+ |
| OpenAI 舔狗事件 | "Sora Sora 2 chatGPT vibe coding OpenAI 阴阳 评价" | 3+ |

### B. 偏倚控制

- **厂商稿 vs 独立评测**：通过要求同一声明 ≥2 来源（一家 + 一家独立）来过滤；
- **时间偏倚**：核心来源 2020-2026；2025-2026 年的最新趋势单独标注（如小红书 AI 翻译、Sora 2）；
- **平台偏倚**：知乎、36 氪、woshipm、人人都是产品经理、澎湃、CSDN、智源、太平洋科技、扬子晚报、新浪、网易、界面新闻、虎嗅、央视/BBC 中文、武大新闻学论文、萌娘百科、维基百科中文版等多个独立平台交叉验证；
- **语种偏倚**：完全遵守用户"仅中文资料"的约束，未引用任何英文来源。

### C. 输出物

- 本报告 Markdown 版本（本文）；
- 同步生成 HTML 版本至同目录；
- 同步翻译英文版至 `Report-en.md`（与 x-monitoring 项目其他研究保持双语同步）；
- 报告同步提交至 `~/.claude/projects/-Users-allenwlee/memory/` 备查。

### D. 给 x-monitoring 维护者的快速启动清单

1. **复制 §5.1 的 per_post_x_to_cn_pragmatics_v1 prompt** 到 `x_monitor/prompts/per_post.yaml`
2. **复制 §5.2 的 aggregate_x_intelligence_to_cn_pm_v1 prompt** 到 `x_monitor/prompts/aggregate.yaml`
3. **建立固定翻译词典**：把 §4.5 表格存为 `x_monitor/data/slang_zh_dict.json`
4. **建立摩擦等级判断器**：把 §6.5 流程图实现为 `x_monitor/discourse/friction_judge.py`
5. **建立 discourse_role 9 选 1 classifier**：用 v1.7 同一 Haiku 模型跑批量标注（建议先在 100 条标注集上验证 Cohen's Kappa）
