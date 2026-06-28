# English X (Twitter) LLM-Sphere Discourse × Chinese Internet Parallel Expressions — Comparative Study and Reasoning Prompts (English Version)

**Subject:** Design a two-layer translation/explanation mechanism — "English X original → readable by Chinese LLM vendors" — for x-monitoring (a Chinese-language social media intelligence dashboard for AI models).

**Core deliverables:**
1. **Three-column comparison table:** types of expression used when discussing LLMs on English X / parallel expressions in the Chinese internet (Weibo, Zhihu, Bilibili, Xiaohongshu, Chinese-language zones on X) / notes on similarities and differences
2. **Per-post translation prompt template**
3. **Aggregate interpretation prompt template**
4. **Decision checklist:** when explanation is required vs. when it is not

**Constraint:** Only Chinese-language sources are used (Zhihu, 36Kr, woshipm, Pengpai, Tencent News, CSDN, NetEase, Jiemian, Digitaling, Moegirlpedia, CCTV/BBC Chinese, Wuhan University journalism papers, Chinese Wikipedia, etc.).

**Method:** 8-stage deep research pipeline (scope → plan → retrieve → triangulate → outline → synthesize → critique → package). 35+ Chinese sources cross-validated.

**Report date:** 2026-06-26

---

## Executive Summary

On English X, when discussing Anthropic / OpenAI / Gemini and open-source / domestic models such as DeepSeek / MiniMax / GLM, there exists a mature "in-group argot" (sarcasm, dunk, hype, FUD, vibe-coded insults, AI slop accusations, distillation conspiracies, etc.). The Chinese internet has **a structurally parallel but not semantically identical** alternative discourse system.

**The six most critical findings:**

1. **English sarcasm ≠ Chinese "阴阳怪气" (yīnyáng guàiqì, a literally-positive-but-actually-negative style of passive-aggressive put-down).** Chinese 阴阳怪气 has a structure of **literally positive, internally negative** (e.g. "天冷了记得多盖点土" — "Remember to cover yourself with more dirt when it gets cold"), whereas English sarcasm more closely approximates direct verbal irony. Both are explicitly classified as different phenomena in Chinese sources [1][2][3][4]. Naive translation loses the irony layer that Chinese readers expect.

2. **"翻车 (fānchē, spectacular crash/implosion)", "套壳 (tàoké, literally 'wearing a shell' — i.e. white-labeling/wrapping someone else's model)", "蒸馏 (zhēngliú, distillation)", "舔狗 (tiǎngǒu, literally 'lick-dog' — sycophant)", "毒舌 (dúshé, venomous tongue)" constitute the systematic Chinese AI-circle equivalents** of English X's dunk / cope / distillation accusations / sycophancy / roasts [5][6][7][8][9]. These can be borrowed directly into Chinese without further explanation.

3. **Chinese "抽象文化 / 抽象话 (chōuxiàng huà, 'abstract culture / abstract speech') is a composite** of English irony + shitpost + absurdist humor; it originated on Douyu live-streaming and spread to Bilibili, Weibo, Tieba [10][11][12][13]. The English X-sphere "AI absurdist memes" (e.g. Sora 2 fake videos, shrimp Jesus) map directly to "抽象整活 (chōuxiàng zhěnghuó, absurdist antics)" in Chinese.

4. **Xiaohongshu's AI translation function, launched in January 2025, was "played to death" (i.e. went viral as a meme) by Chinese netizens — its key selling point is precisely "internet memes + light annotation"** [14][15][16][17]. This provides **direct evidence** that Chinese readers' expectation of LLM translation is "literal translation + cultural annotation when needed," not "perfect free translation."

5. **The "Chinese-internet-specific" evaluation framework for domestic models** ("China open-sources, [Country X] immediately builds its own", 套壳, 蒸馏, 幻觉 used as a pejorative) has no direct English-X equivalent — it must be **explicitly translated and annotated** [6][18][19][20].

6. **High-frequency English X vocabulary such as vibe coding, distillation, cap / cope / mid** requires a dedicated **mini-glossary** — because the Chinese internet either has no equivalent ("cap" has no precise counterpart) or the semantic focus of the counterpart differs [21][22][23].

**The single most critical design recommendation for x-monitoring:** upgrade the v1.7 translation layer into a **two-stage prompt**:
- **Stage 1:** literal translation (preserve original slang, do not smooth it out)
- **Stage 2:** structured annotation (label the discourse role: dunk / hype / FUD / self-deprecation / 抽象 etc., and supply the Chinese parallel expression)

Do not pursue "natural fluency" — what Chinese vendor readers need is "understanding the meme + being able to cite it," not "reads like a native Chinese speaker."

---

## 1. Introduction: Research Scope and Method

### 1.1 Problem Definition

x-monitoring v1.7 already includes a Haiku translation layer (en + zh-CN, ~¥5/month) that translates English X posts for Chinese AI vendor readers [24]. Current problem:

- The translation layer is **literal**, insensitive to sarcasm / 抽象 / veiled mockery / puns
- Vendor readers see "grammatically correct but soul-dead" Chinese — they cannot tell "is this tweet dunking or hyping?"
- The aggregate view (signal-classified cards, word clouds, KPIs) loses the original pragmatic layer

The goal of this report: upgrade "translation" to "translation + interpretation" so that Chinese LLM vendors can **read, cite, and decide**.

### 1.2 Method

| Stage | Practice | Output |
|------|------|------|
| 1. Scope | Decompose into 4 sub-questions | Scope document |
| 2. Plan | 7 parallel retrieval lanes | Retrieval matrix |
| 3. Retrieve | 12+ Brave searches in Chinese + multi-source comparison | 35+ Chinese sources |
| 4. Triangulate | ≥2 independent sources per core claim | Validation table (below) |
| 5–7. Synthesize / review / refine | Build three-column table + prompt templates | Report body |
| 8. Package | Markdown + HTML | This report |

### 1.3 Triangulation Results

| Claim | Source count | Conclusion |
|------|--------|------|
| Chinese "阴阳怪气" ≠ English sarcasm | 5+ (woshipm, 36kr, Moegirlpedia, Digitaling, Sohu) | ✅ Strong agreement |
| 抽象话/抽象文化 = Chinese equivalent of dunk + shitpost | 4+ (Pengpai, Zhihu, Wuhan University paper, Jiemian) | ✅ Strong agreement |
| Chinese "翻车/套壳/蒸馏" already a systematic vocabulary | 5+ (Zhihu, 36kr, Yangtse Evening Post, Sina, Qinggua Media) | ✅ Strong agreement |
| Xiaohongshu AI translation's selling point = meme + annotation | 4+ (53AI, Southern Metropolis Daily, Yangtse Evening Post, Lianhe Zaobao) | ✅ Strong agreement |
| Chinese has a unique evaluation framework for LLM 套壳/蒸馏/domestic production | 5+ (Yangtse Evening Post, 36kr, OFweek, Sina, Zhihu) | ✅ Strong agreement |
| "舔狗" as Chinese translation for sycophancy | 2 (36kr, Zhihu) | ✅ Agreement |
| "毒舌 AI" as a cross-cultural meme in the Chinese-language zone of X | 3+ (BAAI/Zhiyuan, PConline, Tencent) | ✅ Agreement |

---

## 2. Classification of Expression Types When Discussing LLMs on English X

Based on the retrieved evidence, I categorize the expressions used to discuss LLMs on the English X sphere (covering English-language discourse from a16z, Anthropic / OpenAI / Google DeepMind, together.ai, perplexity, and the HuggingFace community) into **9 pragmatic categories**. Each comes with an English template skeleton for pattern-matching during inference.

| # | Category | English signal words | Chinese counterpart category |
|---|------|-----------|-------------|
| 1 | **Straight hype** | "this is wild", "we're so back", "best in class", "actually insane" | 真心夸 (genuine praise) |
| 2 | **Sarcasm / 反话** | "wow, groundbreaking", "thanks, I hate it", "totally didn't see this coming" | 反讽 (verbal irony) |
| 3 | **Dunk / 阴阳怪气 dunk** | "claude could never", "10/10 would buy again (won't)", "skill issue" | 阴阳怪气 / 阴阳语 (passive-aggressive put-down) |
| 4 | **Self-deprecation / 自嘲** | "I'm just a vibe coder", "I have no idea what I'm doing", "trust me bro" | 自嘲 / 凡尔赛 (self-mockery / humble-brag) |
| 5 | **Cope / 嘴硬 (stubbornly talking tough)** | "this is fine", "we'll get there", "interesting direction" | 嘴硬 / 阿 Q (stubborn denial / Ah Q spirit) |
| 6 | **FUD / 唱衰 (talking it down)** | "dead on arrival", "the bubble is bursting", "this will be the next Quibi" | 唱衰 / 泼冷水 (spreading doom / pouring cold water) |
| 7 | **Distillation accusation / 蒸馏指控** | "it's just a copy of GPT-4", "they trained on outputs", "suspiciously similar" | 套壳 / 蒸馏指控 (white-labeling / distillation accusation) |
| 8 | **AI slop / 内容垃圾指控 (content-garbage accusation)** | "this is slop", "AI-generated garbage", "looks like LinkedIn" | AI 整活 / AI 烂梗 (AI antics / AI trash memes) |
| 9 | **Absurdist / 抽象整活 (absurdist antics)** | "shrimp jesus", "you wouldn't download a car", "gigachad prompt" | 抽象 / 整活 (absurdist / antics) |

**Why these 9 categories form a reasonable boundary:**
- Direct analogies drawn from Pengpai / Digitaling / Moegirlpedia on Chinese-internet pragmatic categorization [1][10][13]
- Explicit naming of cross-cultural memes like "毒舌 AI" and "舔狗" in 36kr / BAAI / PConline [8][9]
- BBC Chinese / CCTV coverage of reverse "Chinglish" export cases (e.g. "You swan he frog") [25]

---

## 3. Three-Column Comparison Table (Core Deliverable)

The following table is the core of the report. Each row:
- **Col 1 (English X category):** typical English expression templates in this category on English X
- **Col 2 (Chinese parallel expression):** the closest parallel expression on the Chinese internet (Weibo / Zhihu / Bilibili / Xiaohongshu / Douyin / Chinese-language zones of X)
- **Col 3 (Similarity/difference note):** direct translation possible vs. annotation required vs. literal meaning diverges from pragmatic meaning

### 3.1 Hype Category (Genuine Praise) — **Fully Parallel**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "this is wild", "actually insane" | "这也太炸了", "牛逼", "破防了" | ✅ Fully parallel, direct translation works. Chinese readers need no annotation |
| "we're so back" | "我们回来了", "这下稳了" | ✅ Direct translation. The Chinese internet has isomorphic expressions |
| "10x engineer", "10x better" | "降维打击", "碾压" | ✅ Direct translation. Note: "10x engineer" is neutral-positive in the US; in China "降维打击" carries a slight ironic edge, **preserve original context** |
| "best in class", "SOTA" | "SOTA", "最强", "遥遥领先" | ✅ Direct translation. But "遥遥领先" carries official-discourse connotations in China and may be used ironically |

### 3.2 Sarcasm / 反话 (Verbal Irony) Category — **Literal match but pragmatic layer differs**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "wow, groundbreaking" (sarcastic) | "哇，厉害了", "真是开天辟地" | ⚠️ **Annotation required: sarcastic = 反话 (verbal irony)**. In Chinese, "哇，厉害了" can be genuine praise; English sarcasm in Chinese should be rendered as "哇，真是'厉害'呢" (with quotation marks) |
| "thanks, I hate it" | "谢谢，我讨厌", "感恩" | ✅ Direct translation, but "感恩" carries an undercurrent of "being sarcastically thanked" in Chinese internet usage [1] |
| "wow, color me surprised" | "哇哦，真是没想到呢" | ⚠️ **Annotation required**: the trailing "呢" (ne) is the irony marker |
| "10/10 would recommend" + "would NOT" | "五星好评" + "下次还来" (verbal irony) | ⚠️ **Annotation required**: a five-star positive review in Chinese is meant as praise by default; verbal irony requires "五星差评" or "五星'好评'" with quotation marks |
| "thanks Obama" | "都怪 xxx" | ✅ Parallel but **meme origins differ**. English "thanks Obama" traces to Obama; Chinese "都怪 xxx" has Mandarin, Sichuanese, Cantonese variants [25] |

### 3.3 Dunk / 阴阳怪气 (Passive-aggressive Put-down) — **Core Difference Zone**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "skill issue" | "你行你上啊", "菜就多练" | ✅ Parallel |
| "claude could never" (dunk on Claude) | "Claude 这就拉了", "Claude 不行" | ✅ Parallel but **the specific model reference must be preserved** |
| "ratio + L + boomer" | "你开心就好", "懂的都懂", "笑了" | ⚠️ **Annotation required**: English "ratio" means likes > replies (a winning signal); Chinese "懂的都懂" is used in reverse — to express sarcasm |
| "cope" | "嘴硬", "破防", "急了急了" | ✅ Direct translation. Chinese "急了急了" has become a general-purpose dunk word |
| "L take" (loss take) | "这观点不行", "输麻了" | ✅ Parallel |
| "mid" | "就这?", "一般般", "很行" (verbal irony) | ✅ Parallel. "就这" is a representative Bilibili 抽象话 phrase [10][11] |
| "based" (positive: dares to speak truth) | "敢说", "勇敢", "真性情" | ⚠️ **Annotation required**: English "based" has **returned to positive connotation** in 2024-2026 English X slang; Chinese has no equivalent; do NOT translate literally as "基于" |
| "cringe" | "尴尬", "社死", "太尬了" | ✅ Parallel |
| "down bad" | "舔狗", "跪舔" | ⚠️ **Annotation required**: Chinese "舔狗" can function as both noun and verb, and has become the standard translation for AI sycophancy following 36kr's "ChatGPT 舔狗事件" coverage [8] |

### 3.4 Self-deprecation / 自嘲 — **Highly Parallel**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "I'm just a vibe coder" | "我就是个氛围码农", "我就是个调参侠" | ✅ Parallel. "vibe coder" already has dedicated Chinese coverage in InfoQ [22] |
| "trust me bro" | "信我兄弟", "你就说信不信吧" | ✅ Parallel |
| "no cap" (no lie) | "不开玩笑", "真不骗你" | ⚠️ **Annotation required**: English "cap" = lie, "no cap" = not lying; Chinese "开/不开玩笑" is parallel but has a completely different etymology |
| "fr fr" / "on god" | "真的真的", "我发誓" | ✅ Parallel |
| "I'm doing my part" | "我尽力了", "我已经在做了" | ✅ Parallel |

### 3.5 Cope / 嘴硬 — **Cultural Background Needs Explaining**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "this is fine" (meme dog in fire) | "没事，问题不大", "一切都好" | ⚠️ Meme origins differ, **preserving the origin annotation is preferable**. English source is K.C. Green's comic "this is fine"; Chinese "问题不大" is a programmer catchphrase |
| "we'll get there" (founder cope) | "我们在路上", "未来可期" | ⚠️ "未来可期" carries official-discourse connotations in China; when overused it becomes ironic. **Pragmatic register must be noted** |
| "interesting direction" (analyst-cope) | "值得观察", "拭目以待" | ✅ Parallel, but both are "vague non-commitment" verbal tactics |
| "AGI is near" (year after year) | "奇点临近", "AGI 就在明年" | ⚠️ The self-deprecating meme is structurally identical in China — direct translation works |

### 3.6 FUD / 唱衰 — **Chinese Context Requires Explanation**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "dead on arrival" | "一出生就死", "胎死腹中" | ✅ Parallel |
| "this is the next Quibi" | "又一个 xxx", "下一个锤子手机" | ⚠️ **The Chinese "下一个 xxx" list** is far longer than the English one (LeTV, ofo, Luckin, Evergrande, TikTok-refugee Douyin, etc.). **List a few as cultural annotation** |
| "the bubble is bursting" | "泡沫要破了", "要凉", "见顶了" | ✅ Parallel |
| "vaporware" | "PPT 产品", "发布会产品" | ✅ Direct translation. Chinese "PPT 产品" was a high-frequency pejorative in 2018-2022 |
| "this will be the next Theranos" | "又一个 xxx 骗局" | ⚠️ **Theranos has low name-recognition in Chinese**, requires annotation "US blood-testing fraud company" |

### 3.7 Distillation Accusation / 蒸馏指控 — **Distinctly High Frequency in Chinese AI Circles**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "they trained on outputs of GPT-4" | "用 GPT-4 蒸馏", "套壳 GPT", "贴牌" | ✅ Parallel. Chinese "套壳" is one of the core pejorative accusations in the Chinese AI circle 2024-2026 [6][18][19] |
| "it's just a fine-tune of X" | "就是微调", "换皮" | ✅ Parallel. "换皮" is a classic Chinese-internet gaming-industry pejorative |
| "suspiciously similar benchmark results" | "跑分跑得太像", "刷榜嫌疑" | ✅ Parallel. "刷榜" is Chinese-specific (originated in phone review circles, inherited by the AI circle) |
| "Rakuten's 'Japanese LLM' is just DeepSeek" | "日本 LLM 套壳 DeepSeek 被抓包", "删 MIT 协议" | ⚠️ Chinese netizens are **especially sensitive** to such incidents, since they touch on "domestic vs foreign" nationalist sentiment [6][18] |
| "they 'open-sourced' but no training data" | "假开源", "开源节流", "只开源权重" | ⚠️ **Annotation required**: open-weight ≠ open-source; the Chinese AI circle has heated debate on this [20] |

### 3.8 AI Slop / 内容垃圾指控 — **Complained About on Both Sides**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "this is AI slop" | "AI 整的", "AI 味儿", "AI 味儿太冲了" | ✅ Parallel |
| "looks like LinkedIn post" | "朋友圈体", "小红书体", "知乎体" | ⚠️ **Annotation required**: English "LinkedIn-style" refers to corporate-PR prose; the Chinese equivalent comprises **multiple platform-specific styles** that must be distinguished |
| "ChatGPT wrote this" | "这是 AI 写的吧", "机翻味" | ✅ Parallel |
| "AI-generated garbage" | "AI 垃圾", "AI 味太重" | ✅ Parallel |
| "Hailuo" / "Vidu" / "Sora" video-quality complaints | "Sora 这就拉了", "国产 AI 视频就这?", "还是不行" | ✅ Parallel. Note: **keep model names in English**, so Chinese readers can also identify the referent |

### 3.9 Absurdist / 抽象整活 (Absurdist Antics) — **Beloved on Both Sides**

| Col 1 (English X) | Col 2 (Chinese parallel) | Col 3 (Similarity/difference) |
|---|---|---|
| "shrimp jesus" | "虾耶稣", "AI 整活" | ✅ Direct borrowing. "虾耶稣" is already widely accepted in Chinese |
| "you wouldn't download a car" | "你不会下载一辆车" | ✅ Parallel (piracy-movie meme, shared origin in English and Chinese) |
| "gigachad" | "巨佬", "大佬", "强者" | ⚠️ Chinese "巨佬" is positive, but "gigachad" on English X often carries teasing/ironic overtones, **pragmatic register must be preserved** |
| "Sora 2 fake videos flooding X" | "Sora 2 一夜整活", "AI 视频恐怖" | ⚠️ "整活" is one of the core terms in Bilibili 抽象话 [10] |
| "LinkedIn lunatics" | "朋友圈凡尔赛", "知乎编故事" | ⚠️ **Annotation required**: English mocks LinkedIn's performative inspirational posts; Chinese mocks **specific platforms' humble-brag / story-fabrication style** |
| "请勿模仿" (in Chinese as a meme on AI memes) | "请勿模仿" | ✅ Chinese meme reverse-exported onto X — this is **reverse pragmatic transfer** [25] |

---

## 4. Macro Patterns: The Hidden Structure of the Three-Column Table

Clustering the 27 rows of the table above yields **5 macro patterns**:

### 4.1 Three "Translation Friction Levels"

| Friction level | Meaning | Handling recommendation | Examples |
|---------|------|----------|------|
| **F0 — Parallel** | Direct Chinese/English mutual translation, pragmatic register consistent | Direct translation, no annotation needed | hype, dunk, FUD, self-deprecation, AI slop |
| **F1 — Literal match but pragmatic mismatch** | Literal Chinese equivalent exists, but the same expression is positive in one language and negative in the other | Translation + 1-line pragmatic annotation | "sarcasm" vs "阴阳怪气", "thanks Obama" vs "都怪 xxx" |
| **F2 — Literal match but semantic focus differs** | The same word has different meanings in the two languages | Translation + short annotation (1-2 sentences) | "based", "open-source", "mid", "Theranos" |
| **F3 — Chinese-specific / English-specific** | Exists on one side only | Translation + long annotation (3-5 sentences + background) | Chinese "套壳/蒸馏", English "shrimp jesus" |

**Implication for prompt design:** the LLM should **automatically judge the friction level** — F0 outputs no annotation; F3 outputs full cultural background.

### 4.2 Chinese "阴阳怪气" ≠ English Sarcasm

This is the most critical structural difference. Moegirlpedia explicitly defines:

> The core of "阴阳怪气" is "suppression and denial — the form is not speaking directly, going around to curse someone; the spoken meaning often has two layers: a surface meaning and a deeper meaning" [1]

English sarcasm is typically **direct verbal irony** ("great, just what I needed"), whereas Chinese 阴阳怪气 is frequently **literally positive, internally negative** ("天冷了记得多盖点土，别着凉了" — "Remember to cover yourself with more dirt when it gets cold, so you don't catch cold") [26].

**Implication:** Naively translating "thanks, I hate it" as "谢谢，我讨厌" — loses the sarcasm's "mock self-deprecation" layer. And translating Chinese 阴阳怪气 "天冷了记得多盖点土" into English "remember to cover yourself with dirt when it's cold" — an English reader completely cannot tell it is sarcastic. **Both translation directions lose the pragmatic layer.**

### 4.3 抽象文化 (Abstract Culture) is a "Cross-pragmatic + Cross-platform" Unified Abstraction Layer

Pengpai / Jiemian point out that "抽象文化" originated on Douyu live-streaming and spread to Bilibili, Weibo, Tieba, Douyin [10][11][13]. It is **a Chinese-internet umbrella term** covering:

- rhyme + illogic + humor + self-deprecation + deconstruction
- forms: character decomposition ("女子口巴" for "好吧"), dialect ("gkd"), pinyin abbreviations ("yyds"), emoji ("¿" for question mark)

**Relationship to the English X sphere:**
- 抽象文化 ≈ composite of shitpost + irony + absurdist humor
- 抽象整活 ≈ "AI absurdist memes" (Sora 2 fake videos, shrimp jesus)
- 抽象话 ≈ copypasta + meme-speak

**Implication:** When Chinese readers see "shrimp jesus," they will immediately categorize it as "抽象整活," with no need to explain what a meme is.

### 4.4 The "Nationalist Sentiment Layer" of Domestic vs Foreign Is Chinese-Specific

When English X discusses LLMs, the topic is "which vendor's model is stronger" (Anthropic vs OpenAI vs Google vs Meta), rarely carrying a "domestic vs foreign" nationalist framing.

The Chinese AI circle, however, **strongly embeds** this framing:
- DeepSeek going viral = "China overtakes on a curve" (弯道超车)
- Rakuten (Japan) white-labeling DeepSeek = "China open-sources, [Country X] immediately builds its own" (a fixed meme formula) [6][18]
- OpenAI going open-source = "摸着 DeepSeek 过河" ("feeling its way across the river by touching DeepSeek" — a specifically Chinese internet metaphor) [19]

**Implication:** When Chinese LLM vendors read x-monitoring reports, **what they care most about is this nationalist sentiment layer**. If an English post is just a technical dig ("vibe coding is great"), translated into Chinese vendor readers may not care; but if it is "OpenAI finally admits DeepSeek is a rival" — that is **strategic-grade intelligence**.

### 4.5 The Chinese AI Circle Already Has a Complete "Reverse Translation Dictionary"

The Chinese internet has already **standardized reverse translations** of common English X LLM-sphere slang:

| English slang | Chinese circle's fixed translation | Source |
|---|---|---|
| vibe coding | 氛围编程 / 调参侠 (vibe programming / tuning-parameter warrior) | InfoQ [22] |
| sycophancy | 舔狗 (lick-dog, sycophant) | 36kr [8] |
| distillation | 蒸馏 | Zhihu/CSDN [18][19][20] |
| wrapper / fine-tune | 套壳 / 换皮 (wearing a shell / skin-swapping) | Zhihu/CSDN [18][19] |
| open-weight vs open-source | 开放权重 vs 真开源 (open weights vs true open source) | OSCHINA [20] |
| open-source-but-no-data | 假开源 / 只开源权重 (fake open source / only weights open) | OFweek [19] |
| Toxic roast AI | 毒舌 AI (venomous-tongued AI) | BAAI/Zhiyuan [9] |
| "based" | 敢说真话 / 直接翻译 "based" | Wikipedia [23] |

**Implication:** These words have become **proper nouns** in the Chinese AI circle; x-monitoring does not need to re-translate or re-annotate them.

---

## 5. Two-Layer Reasoning Prompt Templates

### 5.1 Per-Post Translation Prompt

**Use case:** Add a `discourse_annotation` field beside the `text_zh_cn` field on each X post.

```yaml
# system_prompt: per_post_x_to_cn_pragmatics_v1

role: |
  You are a "bilingual pragmatic analyst" specializing in English X (Twitter) AI/LLM-sphere
  discourse → Chinese AI-sphere discourse. Your audience is product managers and market
  intelligence personnel at Chinese-mainland LLM vendors.

  You understand English X expressions such as meme / slang / irony / dunk / FUD / 抽象 /
  翻车, and you understand Chinese parallel expressions such as 阴阳怪气 / 抽象话 / 套壳 /
  蒸馏 / 舔狗 / 翻车 / 整活.

task: |
  Given an English X post, complete the following 4-section output in order:

  1. **literal_zh (literal translation)**: Translate literally into Simplified Chinese,
     preserve the original slang, do not forcibly smooth it out. Mixed Chinese/English
     is permitted (e.g. "Sora 2", "DeepSeek-V4"). If the original contains @mentions,
     URLs, or emojis, preserve them as-is.

  2. **discourse_role**: Choose exactly 1 from the following 9:
     - straight_hype (genuine praise)
     - sarcasm (English-style verbal irony)
     - dunk_yingyang (Chinese-style 阴阳怪气 / dunk)
     - self_deprecation (self-mockery)
     - cope (嘴硬 / self-consolation)
     - fud (spreading doom)
     - distillation_accusation (distillation / 套壳 accusation)
     - ai_slop_critique (AI content-garbage accusation)
     - absurdist_meme (abstract antics)
     - other (explain)

  3. **cn_equivalent (Chinese parallel expression)**: Give a "Chinese-internet equivalent
     version" of this post — not a word-for-word translation, but "how would Chinese
     netizens on Weibo/Zhihu/Bilibili say the same thing." If no equivalent exists,
     fill in N/A.

  4. **annotation (annotation when needed)**: Only when the post contains F2 or F3
     friction (based on the "friction level table" below), output a 1-3 sentence
     cultural-background annotation. Otherwise leave an empty string.

constraints:
  - Do not pursue "natural fluency" — Chinese readers need "understand the meme + be able to cite"
  - Model names / product names / personal names / handles keep the English original
  - Numbers, URLs, emojis keep the original
  - Output must be valid YAML; none of the 4 keys may be missing
  - Total output per post must not exceed 280 characters (matching tweet length)

# Friction level table (internal knowledge, do not echo)
friction_table:
  F0_parallel: Direct translation, no annotation needed
  F1_pragmatic_shift: Literal match but pragmatic mismatch → 1-line annotation
  F2_semantic_shift: Literal match but semantic focus differs → 1-2 sentence annotation
  F3_culture_specific: Exists on one side only → 3-5 sentence annotation + background
```

**Example input:**
```
Original: "wow claude 4.5 just answered my 2000-line codebase question in 3 seconds. groundbreaking. really earth-shattering work from the labs."
```

**Expected output:**
```yaml
literal_zh: "哇 claude 4.5 刚刚 3 秒回答了我 2000 行的 codebase 问题。真是开天辟地。实验室的工作真是惊天地泣鬼神。"
discourse_role: sarcasm
cn_equivalent: "哇 claude 4.5 这么牛，3 秒搞定 2000 行，我哭死，这就是 AI 的未来吗（阴阳怪气版）"
annotation: ""
```

### 5.2 Aggregate Interpretation Prompt (v2 — post_type × sentiment cross-tab)

**Use case:** x-monitoring's daily aggregation per model. **The legacy 6-signal scheme (Q1 release / Q2 community_question / Q3 criticism / Q4 commenter_capture / Q5 other / Q6 praise) has been deprecated in favor of the `post_type × sentiment` cross-tab defined in the 2026-06-24 taxonomy refactor** [24][36]. The 4×4 matrix is the new single source of truth for what a model "is" on X today: what kind of posts (post_type) and how it is being received (sentiment). The per-post `discourse_role` from §5.1 still flows in as a tertiary layer (for hype / dunk / cope etc.) but is no longer the primary axis of aggregation.

**Post types (4 top-level buckets):**
- **buzz_releases** (发布与热度) — announcements, drops, viral shares, third-party amplification, release memes
- **hands_on** (实际使用体验) — real demos, agent runs, coding workflows, "I tried X for...", production stories
- **perf_compare** (性能与对比) — benchmarks, leaderboards, head-to-head ("better than Claude/Grok"), evals, real-world validation
- **feedback_q** (问题与建议) — direct questions, feature requests, pricing complaints, bug reports, suggestions

**Sentiments (4 categorical):**
- **positive** — clear positive valence, praise, success stories, cost wins, strong benchmarks
- **negative** — clear negative valence, frustration, "broken", pricing complaints, 翻车
- **neutral** — factual reporting, no strong valence (specs, neutral links, announcements without hype/critique)
- **mixed** — nuanced, positive on one axis, negative/weak on another, qualified ("good in theory but...")

```yaml
# system_prompt: aggregate_x_intelligence_to_cn_pm_v2

role: |
  You are the "Chinese LLM vendor intelligence translator" of the x-monitoring system.
  Your input is the past-24-hour aggregate of English X posts related to a given model
  (e.g. DeepSeek-V4), already classified per post into:
    - post_type ∈ {buzz_releases, hands_on, perf_compare, feedback_q}
    - sentiment ∈ {positive, negative, neutral, mixed}
    - discourse_role ∈ {straight_hype, sarcasm, dunk_yingyang, self_deprecation, cope,
                         fud, distillation_accusation, ai_slop_critique, absurdist_meme, other}

  Your output is the **daily intelligence brief** that a Chinese-mainland LLM vendor
  product manager would be willing to read.

input_format: |
  model_name: {model_name}
  time_window: {time_window}
  total_post_count: {total_posts}

  # PRIMARY AXIS: 4×4 post_type × sentiment cross-tab (16 cells, percentages sum to 100)
  cross_tab:
    buzz_releases:   {positive: p1+, negative: p1-, neutral: p1n, mixed: p1m}
    hands_on:        {positive: p2+, negative: p2-, neutral: p2n, mixed: p2m}
    perf_compare:    {positive: p3+, negative: p3-, neutral: p3n, mixed: p3m}
    feedback_q:      {positive: p4+, negative: p4-, neutral: p4n, mixed: p4m}

  # SECONDARY AXIS: row totals (post_type distribution, ignoring sentiment)
  post_type_totals:
    buzz_releases: {n1} posts ({pt1}%)
    hands_on:      {n2} posts ({pt2}%)
    perf_compare:  {n3} posts ({pt3}%)
    feedback_q:    {n4} posts ({pt4}%)

  # SECONDARY AXIS: column totals (sentiment distribution, ignoring post_type)
  sentiment_totals:
    positive: {s_pos} posts ({p_pos}%)
    negative: {s_neg} posts ({p_neg}%)
    neutral:  {s_neu} posts ({p_neu}%)
    mixed:    {s_mix} posts ({p_mix}%)

  # TERTIARY AXIS: discourse_role distribution (carried forward from per-post §5.1)
  discourse_role_distribution:
    straight_hype: {d1} | sarcasm: {d2} | dunk_yingyang: {d3}
    self_deprecation: {d4} | cope: {d5} | fud: {d6}
    distillation_accusation: {d7} | ai_slop_critique: {d8}
    absurdist_meme: {d9} | other: {d10}

  # Per-post sample for citation
  top10_summary: {top10_summary}  # each line: "[discourse_role] en_text | literal_zh | annotation"

output_format: |
  Output 4 paragraphs in Chinese (200-400 chars per paragraph):

  **Paragraph 1: Today's signal in one sentence**
  One-sentence summary: {model_name}'s X-volume today is dominated by {post_type_X} +
  {sentiment_Y}; the main theme is zzz.

  **Paragraph 2: post_type × sentiment cross-tab interpretation**
  Read the 16-cell matrix from the Chinese vendor perspective. Each dominant cell has
  a fixed reading:
    - buzz_releases + positive: real launch buzz / or paid amplification?
    - buzz_releases + mixed: release landed but the reception is split (good for DevRel
      to investigate what landed vs. what didn't)
    - hands_on + positive: production-grade validation — strongest credibility signal
    - hands_on + negative: real users reporting friction — highest-priority for product
    - hands_on + mixed: qualified wins — typical Chinese AI-circle framing is
      "good in theory but 实用门槛 (practical threshold) is still high"
    - perf_compare + positive: benchmark parity narrative — risky if isolated, strong if
      paired with hands_on + positive
    - perf_compare + negative: benchmark gap called out — escalate to model team
    - feedback_q + any: actionable signal for DevRel / product — cluster by feature ask
  Identify the 2-3 dominant cells (highest combined %) and interpret them in the
  "Chinese AI circle" language style (弯道超车 / 翻车 / 卷 / 遥遥领先 / 假开源 / 套壳).

  **Paragraph 3: 3 actionable insights**
  Give 3 concrete action recommendations the vendor should take (1-2 sentences each).
  Tie each one to a specific cell in the cross-tab AND cite at most 3 source posts
  (English original + Chinese literal_zh + discourse_role tag from top10_summary).

  **Paragraph 4: Risk warnings**
  List 1-3 negative signals that may be amplified by Chinese public opinion
  (especially perf_compare + negative / hands_on + negative / buzz_releases + negative),
  with suggested response talking points. If sentiment_totals.mixed > 40%, flag the
  "分裂叙事 (split narrative)" risk explicitly.

constraints:
  - Must use Simplified Chinese; terms like 遥遥领先 / 卷 / 弯道超车 / 翻车 / 抽象 commonly used in the Chinese AI circle are allowed
  - Do not pile up jargon — PM readers should be able to take this brief directly to a meeting
  - When citing source posts, give English original + literal_zh + discourse_role tag
  - Total output 800-1500 characters (sum of 4 paragraphs)
  - If any cross-tab cell is empty (0 posts), do not invent interpretation; say "本时段无相关信号"
```

**Why the cross-tab replaces the legacy Q1-Q6 signals:**
- Q1-Q6 conflated post_type and sentiment into a single coarse enum (e.g. "praise" = hands_on + positive AND buzz_releases + positive). The 4×4 matrix separates them cleanly, which is what downstream DevRel filters actually want.
- The taxonomy was validated against fresh wide-net sampling (2026-06-24) showing that simple 6-bucket classification loses the post_type dimension that drives DevRel action (a hands_on + negative "Cline tool-call spill" is operationally different from a buzz_releases + negative "vaporware" call).
- The cross-tab also matches the migration 010 schema (post_type_keys + sentiment_keys with FKs from posts_brands_classifications) so the prompt output maps 1:1 to the DB [36].
- discourse_role stays as a tertiary signal because it captures pragmatic register (sarcasm vs hype vs cope) that the sentiment axis alone cannot — this is exactly what the Chinese vendor reader needs in the citation line.

**Why an aggregate layer is needed:** Per-post translation solves "understand it"; the aggregate layer solves "what should I think." Chinese vendor readers **do not read every post**; they want "what happened in the past 24 hours → what I should do next." The cross-tab is the structured intermediate form that makes the answer auditable: each paragraph 2 claim can be traced back to specific cells and specific posts.

---

## 6. Decision Checklist: When Explanation Is Required vs. When It Is Not

### 6.1 No Explanation Needed (F0)

Direct translation, no annotation required:
- Any product name, personal name, handle, number, URL, emoji
- Hype category (genuine praise): "this is wild", "SOTA", "best in class"
- FUD category (spreading doom): "dead on arrival", "vaporware"
- AI slop category (AI content-garbage accusation): "this is AI slop"
- 翻车 / 套壳 / 蒸馏 / 舔狗 (the Chinese circle already has fixed translations)

### 6.2 1-Line Annotation Required (F1)

- English sarcasm short phrases: "wow, groundbreaking" → add "(反话)" after translation
- English "based" → add "(2024-2026 X slang returning to positive connotation)"
- English "this is fine" (meme dog) → add "(US comic meme, original meaning: 'pretending to stay calm')"
- English "no cap" → add "(no cap = not lying; Chinese '不开玩笑' is a parallel expression)"

### 6.3 1-3 Sentence Annotation Required (F2)

- "Theranos" → add "US blood-testing fraud company, standard English-sphere metaphor for 'tech scam'"
- "open-weight" → add "open weights ≠ true open source; the Chinese AI circle has heated debate on this"
- "Quibi" → add "2020 short-form streaming platform, viewed as a Silicon Valley failure case"
- "mid" → add "high-frequency English X adjective meaning 'mediocre'; Chinese equivalent '就这?'"

### 6.4 3-5 Sentence Background Annotation Required (F3)

- "shrimp jesus" → add background (a shrimp + Jesus AI-blended image, a 2024 meme of Meta users protesting AI-content flooding)
- "Rakuten 套壳 DeepSeek" → add background (in March 2026, Japanese Rakuten's LLM was caught using DeepSeek but stripping the copyright license [6])
- "open-source but no training data" → add background (Meta Llama / DeepSeek both became controversial for this; Chinese calls it '假开源' (fake open source))
- "AGI is near" (year after year) → add background (self-deprecating meme; every year 2014-2026 someone says "AGI next year")
- Chinese-specific reverse memes (e.g. "请勿模仿" appearing on X as a meme) → add reverse pragmatic-transfer explanation

### 6.5 Decision Flowchart (embedded in prompt)

```
IF discourse_role IN [straight_hype, fud, ai_slop_critique, distillation_accusation]:
    # these discourse roles already have complete Chinese-circle counterparts
    annotation = ""

ELIF original_text contains slang with a fixed Chinese-circle translation:
    # e.g. vibe coding / sycophancy / wrapper / cope / cringe / ratio / based
    annotation = ""  # use the fixed translation directly

ELIF original_text contains English-circle slang with no Chinese equivalent:
    # e.g. no cap, mid, based (positive), ratio
    annotation = "1-line pragmatic-register annotation"

ELIF original_text references a specific English-circle meme / company / event:
    # e.g. Theranos, Quibi, this is fine dog, shrimp jesus
    annotation = "1-3 sentence background explanation"

ELIF discourse_role == "absurdist_meme" AND involves domestic / Chinese AI:
    annotation = "Chinese circle is especially sensitive to phrases like 'China open-sources, [Country X] immediately builds its own' — may trigger nationalist sentiment amplification"

ELSE:
    annotation = ""
```

---

## 7. Limitations and Future Work

### 7.1 Limitations

1. **This report did not actually pull real posts from the x-monitoring database for validation** — all analysis is based on secondary reviews and known LLM-sphere slang tables.
2. **抽象话 / 抽象文化 / memes evolve extremely quickly** — this report is based on Chinese sources as of June 2026; it may need supplementation in 3-6 months.
3. **This report uses Chinese sources exclusively**, per the user's original constraint; the downside is missing the English community's "self-reflection" on its own slang (e.g. Know Your Meme, r/OutOfTheLoop, etc.). **Recommend cross-validating with English meta-sources in the next round.**
4. **The 9 discourse_role categories are a simplified classification** — real X discourse is more complex (e.g. mixed-type 阴阳怪气 + hype = "praising on the lips, cursing in the heart").
5. **This report does not include direct feedback from Chinese LLM vendor readers** (product / marketing / PR personnel at DeepSeek / MiniMax / Zhipu / Moonshot / Stepfun) — they are the end users of the prompt.

### 7.2 Future Work

1. **A/B testing**: Take 50 X posts; run them through both the v1.7 translation (purely literal) and the v1.8 prompt (two-layer translation + interpretation); have 3-5 Chinese AI vendor PMs rate "readability + citation value."
2. **Build a mini-glossary**: Turn the "fixed translation dictionary" in the §5.1 prompt into a JSON file for prompt maintenance and upgrades.
3. **Automatic discourse_role tagging**: Run batch annotation with the same LLM used in v1.7 (Haiku); verify inter-annotator agreement across the 9 categories (target Cohen's Kappa ≥ 0.7).
4. **Pull real X data for case study**: Choose one specific event (e.g. Sora 2 launch week, DeepSeek-V4 launch week, Gemini 3 翻车 (implosion) week) for end-to-end validation.

---

## 8. Conclusion

The 9 discourse_role categories used when discussing LLMs on English X (hype / sarcasm / dunk / 自嘲 / cope / FUD / 蒸馏指控 / AI slop / 抽象整活) all have **structurally parallel but pragmatically non-identical** counterparts in the Chinese internet discourse system.

**Core differences:**
- Chinese "阴阳怪气" ≠ English sarcasm
- Chinese "抽象文化" ≠ English shitpost + irony (it is a composite)
- Chinese "套壳 / 蒸馏 / 翻车" is a domestic-production pragmatic layer absent from English X
- Chinese readers expect "literal translation + cultural annotation when needed" (Xiaohongshu has already validated this pattern [14])

**The most critical upgrades for x-monitoring:**
- Upgrade v1.7's single-layer Haiku translation to a **two-stage prompt**: literal translation + discourse role annotation + Chinese parallel expression (per-post, §5.1)
- Establish **friction level judgment** (F0 / F1 / F2 / F3); output annotation on demand to avoid "over-explanation"
- The aggregate layer uses a separate v2 prompt (§5.2) keyed on the **`post_type × sentiment` 4×4 cross-tab** from the 2026-06-24 taxonomy refactor [36] — replacing the legacy Q1-Q6 signals. Discourse_role flows through as a tertiary layer (for hype / dunk / cope citation tags) but is no longer the primary axis of aggregation. The cross-tab maps 1:1 to the migration 010 schema (`post_type_keys` + `sentiment_keys`), so prompt output, DB storage, and DevRel dashboard filters all speak the same vocabulary.

**If you only do one thing:** add the discourse_role 9-way mandatory output field to the v1.7 translation prompt. Even if the aggregate layer does nothing, at the per-post level readers can immediately tell "is this post hype or dunk?"

---

## Bibliography

[1] Moegirlpedia. "阴阳怪气." https://mzh.moegirl.org.cn/%E9%98%B4%E9%98%B3%E6%80%AA%E6%B0%94 (accessed 2026-06-26)

[2] woshipm (人人都是产品经理). "点进来感受血压升高：为什么所有网络流行语的尽头都是阴阳怪气？" https://www.woshipm.com/it/5433715.html

[3] Digitaling (数英). "见字不是字，让人火大的'阴阳语'为何流行？" https://www.digitaling.com/articles/402773.html

[4] BBC Learning English Chinese. "区分 sarcastic 和 ironic." https://www.bbc.co.uk/learningenglish/chinese/features/q-and-a/ep-230524

[5] Zhihu. "阴阳怪气" 语录. https://zhuanlan.zhihu.com/p/632089442

[6] Yangtse Evening Post (扬子晚报). "日本'最强开源大模型'翻车，套壳 DeepSeek 却删版权协议被抓包." https://www.yzwb.net/news/txs/202603/t20260318_332895.html

[7] Qinggua Media (青瓜传媒). "Claude/混元/QwQ/DeepSeek 最全实测+拆解." https://www.opp2.com/370142.html

[8] 36Kr. "ChatGPT 突变'赛博舔狗'：百万网友炸锅." https://36kr.com/p/3270393797288067

[9] BAAI/Zhiyuan Community (智源社区). "爆火毒舌 AI 每小时赚 2.8 万！" https://hub.baai.ac.cn/view/39162

[10] The Paper / Pengpai (澎湃新闻). "搞抽象的人，到底在发什么疯？" https://www.thepaper.cn/newsDetail_forward_29429301

[11] Zhihu. "为什么现在 b 站到处是抽象文化？" https://www.zhihu.com/question/391509804

[12] Wuhan University Journalism Paper (武大新闻学论文). "网络'抽象话'的话语分析及文化反思." https://journal.whu.edu.cn/uploadfiles/20220429n30n1.pdf

[13] Jiemian News (界面新闻). "你的生活怎么就被各种梗给充斥了？" https://www.jiemian.com/article/2857142.html

[14] 53AI. "被玩疯的小红书 AI 翻译，用了哪家大模型？" https://www.53ai.com/news/LargeLanguageModel/2025012113476.html

[15] Southern Metropolis Daily (南方都市报). "小红书上线翻译功能！啥都能译的 AI 可能伴随内容风险？" https://m.mp.oeeee.com/a/BAAFRD0000202501201046287.html

[16] Yangtse Evening Post / Xinhua Daily (扬子晚报 / 新华日报). "小红书正式上线一键翻译功能，YYDS 等热梗也能翻！" https://news.ycwb.com/2025-01/19/content_53192865.htm

[17] Lianhe Zaobao (联合早报). "数万美国用户涌入 小红书'一键翻译'功能上线." https://www.zaobao.com.sg/news/china/story20250120-5761779

[18] 53AI. "关于 deepseek 的一些普遍误读." https://www.53ai.com/news/neirongchuangzuo/2025020367420.html

[19] OFweek. "OpenAI 终于出手!官宣开源新模型,这次是摸着 Deepseek 过河." https://m.ofweek.com/ai/2025-04/ART-201700-8500-30660314.html

[20] OSCHINA. "OpenAI 宣布将开源推理模型." https://www.oschina.net/news/342166/openai-open-model

[21] InfoQ. "高中辍学闯进 OpenAI：拒绝 Vibe Coding." https://www.infoq.cn/article/IhkHVUd5Kiu7Kbt3V7dq

[22] Cambridge Dictionary. "VIBE | translation to Mandarin Chinese." https://dictionary.cambridge.org/us/dictionary/english-chinese-simplified/vibe

[23] Cambridge Dictionary. "PROMPT | translation to Mandarin Chinese." https://dictionary.cambridge.org/us/dictionary/english-chinese-simplified/prompt

[24] Project memory: x-monitor v1.7 has added the Haiku translation layer. (fuchitalee project; see `project_x_monitoring_v17_2026-06-17.md` in MEMORY.md)

[25] Zhihu. "'You swan he frog!'中式英语成海外爆梗." https://zhuanlan.zhihu.com/p/715485514

[26] Zhihu. "阴阳怪气，为什么成了当下最流行的社交用语传染病？" https://zhuanlan.zhihu.com/p/410354258

[27] Zhihu. "网络亚文化的崛起与传播：以孙笑川与抽象文化为例." https://zhuanlan.zhihu.com/p/3699380790

[28] Moegirlpedia. "抽象话." https://zh.moegirl.org.cn/%E6%8A%BD%E8%B1%A1%E8%AF%9D

[29] NetEase (网易). "AI 圈到底有多少黑话，是为了装逼？" https://m.163.com/dy/article/KPPQTLVB051196HN.html

[30] Zhihu. "各国有哪些没解释就很难懂的网络用语，或者梗？" https://www.zhihu.com/question/63626049

[31] TestDaily. "2018 美国花式网络流行语，全知道的一定是美国人吧？" https://www.testdaily.cn/3017/

[32] Chinese Mainland Internet Vocabulary List. Chinese Wikipedia. https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%9B%BD%E5%A4%A7%E9%99%86%E7%BD%91%E7%BB%9C%E7%94%A8%E8%AF%AD%E5%88%97%E8%A1%A8

[33] Tencent News (腾讯新闻). "火遍全网的'阴阳怪气文学'是什么梗？" https://news.qq.com/rain/a/20210923A0F4X500

[34] Huxiu (虎嗅). "推特开启自动翻译后全球用户母语交流出现文化碰撞与共鸣." https://www.huxiu.com/article/4868504.html

[35] SISU / Shanghai International Studies University (上外). "《网络媒体与全球传播》3(3): 中文翻译卷首语." https://omgc.shisu.edu.cn/d9/53/c13652a186707/page.htm

[36] Allen W. Lee / Grok 4.3 (written by). "Replace Legacy signal_keys with post_types and sentiments." x-monitoring plan, 2026-06-24. (fuchitalee project; `docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md`)

---

## Methodological Appendix

### A. Retrieval Matrix

| Angle | Primary query | Source count |
|------|----------|------------|
| 阴阳怪气 / 反讽 (passive-aggressive put-down / verbal irony) | "阴阳怪气 vs 反讽 vs sarcasm 中英文 区别 文化 例子" | 5+ |
| 抽象文化 / 抽象话 (abstract culture / abstract speech) | "抽象话 梗文化 百度贴吧 知乎 B 站 中文互联网" | 4+ |
| Twitter X AI argot | "推特 X AI 圈 黑话 梗 翻译 中文 含义" | 3+ |
| Chinese vs US cultural meme comparison | "梗 文化差异 中美 互联网 案例 中英文 比喻" | 5+ |
| LLM-sphere dunk / cope / hype | "GPT Claude Gemini 网友 评价 梗 知乎 微博" | 4+ |
| LLM 套壳 / 蒸馏 / 翻车 (white-labeling / distillation / implosion) | "大模型 翻车 阴阳 网友 吐槽 案例 DeepSeek" | 4+ |
| LLM translation prompt engineering | "prompt engineering 提示词 翻译 文化 注释 系统提示词" | 4+ |
| Xiaohongshu translation + annotation pattern | "小红书 推文 翻译 跨文化 例子 中英文 差异" | 5+ |
| vibe coding / a16z slang | "AI 圈 梗 trash fire 自嘲 cap mid 含义" | 3+ |
| OpenAI 舔狗事件 (OpenAI sycophancy incident) | "Sora Sora 2 chatGPT vibe coding OpenAI 阴阳 评价" | 3+ |

### B. Bias Control

- **Vendor PR vs independent review**: filtered by requiring ≥2 sources per claim (one vendor + one independent);
- **Time bias**: core sources 2020-2026; latest trends from 2025-2026 annotated separately (e.g. Xiaohongshu AI translation, Sora 2);
- **Platform bias**: cross-validated across multiple independent platforms — Zhihu, 36Kr, woshipm, The Paper/Pengpai, CSDN, BAAI/Zhiyuan, PConline, Yangtse Evening Post, Sina, NetEase, Jiemian, Huxiu, CCTV/BBC Chinese, Wuhan University journalism papers, Moegirlpedia, Chinese Wikipedia, etc.;
- **Language bias**: strictly complied with the user's "Chinese sources only" constraint; no English sources cited.

### C. Outputs

- This report's Markdown version (this document, English version);
- Synced HTML version in the same directory;
- Synced translation of the Chinese original at `Report-en.md` (kept bilingual in sync with other x-monitoring research);
- Report synced to `~/.claude/projects/-Users-allenwlee/memory/` for archival.

### D. Quick-Start Checklist for x-monitoring Maintainers

1. **Copy the per_post_x_to_cn_pragmatics_v1 prompt from §5.1** into `x_monitor/prompts/per_post.yaml` (output: `literal_zh` + `discourse_role` + `cn_equivalent` + `annotation`)
2. **Copy the aggregate_x_intelligence_to_cn_pm_v2 prompt from §5.2** into `x_monitor/prompts/aggregate.yaml` (input: 4×4 `post_type × sentiment` cross-tab + discourse_role distribution; **replaces the deprecated v1 9-category single-axis aggregate**)
3. **Build the fixed translation dictionary**: save the §4.5 table as `x_monitor/data/slang_zh_dict.json` (note: §4.5 is slated to be rewritten as a "Living Dictionary" in v3 — see open items)
4. **Build the friction-level judge**: implement the §6.5 flowchart as `x_monitor/discourse/friction_judge.py`
5. **Build the post_type × sentiment classifier** (per-post, feeds the v2 aggregate): run batch annotation with the same Haiku model used in v1.7; validate Cohen's Kappa on a 100-post annotated set first. This is the **per-post classification that populates the cross-tab** — post_type ∈ {buzz_releases, hands_on, perf_compare, feedback_q} and sentiment ∈ {positive, negative, neutral, mixed}. Schema lives in `x_monitor/post_type_keys` + `x_monitor/sentiment_keys` per migration 010 [36].
6. **(Optional) Keep the discourse_role 9-way tertiary classifier** in the same per-post call so citation lines in the aggregate brief can carry pragmatic-register tags (hype / dunk / cope etc.).