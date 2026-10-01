# Sentiment comparison: 39 posts — Jev and 0731

Prepared: 2026-10-01 (JST)  
Saved experiment: `2026-10-01-053425-political-framing-retest`  
Models: Jev and DeepSeek V4 Flash 0731  
Scope: the same 39 posts previously listed as Jev sentiment errors, now with 0731’s classification added.

## How to read this report

These are the 39 cases where Jev disagreed with the frozen reference label among 117 posts in the saved run. The reference labels were written by an agent, not independently verified by a human. Treat this as a disagreement list, not proof that every reference label is correct.

Sentiment is toward the specified target brand, not the overall tone of the post. Each entry keeps the saved labels unchanged. The original source text is reproduced verbatim; English translations are supplied for reading. The experiment used the original-language input and saved context, not the translations newly supplied here.

0731 returned an invalid response for four cases: `zh_cn_13`, `ko_01`, `ko_12`, and `en_09`. These are output failures (`invalid_response_envelope`), not the legitimate sentiment category `unknown`. Among this selected 39-case subset, 0731 matches the reference in 11 cases, disagrees in 24, and has four invalid responses. This is not its overall accuracy.

Stored quoted posts and parent posts are shown separately so that their speakers are not confused with the author of the main post. Links and claims are reproduced from saved evidence; their contents and factual accuracy have not been independently verified. No new model tests, live-post retrieval, or label changes were performed for this export.

## Classification table

| # | Case | Target brand | Jev | 0731 | Reference |
|---|---|---|---|---|---|
| 1 | ja_09 | minimax | positive | positive | neutral |
| 2 | ja_10 | minimax | mixed | positive | positive |
| 3 | ja_11 | deepseek | negative | negative | neutral |
| 4 | ja_12 | minimax | positive | neutral | neutral |
| 5 | ja_13 | llama | negative | neutral | unknown |
| 6 | ja_15 | sakana_ai | positive | neutral | neutral |
| 7 | ja_18 | minimax | negative | negative | neutral |
| 8 | zh_cn_04 | dots | negative | neutral | neutral |
| 9 | zh_cn_07 | deepseek | neutral | neutral | positive |
| 10 | zh_cn_09 | deepseek | positive | neutral | neutral |
| 11 | zh_cn_13 | mimo | mixed | INVALID RESPONSE | neutral |
| 12 | zh_cn_14 | deepseek | positive | unknown | neutral |
| 13 | zh_cn_20 | deepseek | positive | neutral | neutral |
| 14 | ko_01 | deepseek | positive | INVALID RESPONSE | neutral |
| 15 | ko_02 | deepseek | negative | negative | mixed |
| 16 | ko_04 | deepseek | negative | positive | neutral |
| 17 | ko_07 | qwen | unknown | positive | neutral |
| 18 | ko_08 | deepseek | neutral | neutral | positive |
| 19 | ko_09 | deepseek | positive | positive | mixed |
| 20 | ko_12 | deepseek | neutral | INVALID RESPONSE | positive |
| 21 | ko_18 | deepseek | negative | negative | neutral |
| 22 | ko_20 | qwen | positive | positive | mixed |
| 23 | en_01 | qwen | mixed | neutral | negative |
| 24 | en_03 | glm | positive | positive | neutral |
| 25 | en_05 | qwen | negative | unknown | neutral |
| 26 | en_09 | deepseek | positive | INVALID RESPONSE | neutral |
| 27 | en_12 | glm | positive | unknown | neutral |
| 28 | en_14 | deepseek | negative | negative | neutral |
| 29 | en_15 | deepseek | positive | positive | neutral |
| 30 | en_20 | minimax | positive | positive | unknown |
| 31 | es_04 | qwen | positive | positive | neutral |
| 32 | es_07 | deepseek | mixed | neutral | neutral |
| 33 | es_15 | deepseek | negative | negative | neutral |
| 34 | es_16 | minimax | mixed | neutral | neutral |
| 35 | es_19 | deepseek | negative | neutral | neutral |
| 36 | es_20 | deepseek | unknown | neutral | neutral |
| 37 | tr_04 | deepseek | negative | negative | neutral |
| 38 | tr_10 | qwen | negative | negative | mixed |
| 39 | tr_18 | mistral | positive | neutral | neutral |

## Full posts

### 1. ja_09 — minimax

Source: [@__su888](https://x.com/__su888/status/2087298764583415883)  
Language: Japanese  
Target brand: `minimax`  
Jev: **positive** · 0731: **positive** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
antirez's MiniMax-H3 Apple Silicon native inference implementation. With int8 MLP and QKV quantization, 50-layer 19-iteration 512x512 denoise shortened from 36.30s to 19.18s, peak tensor also reduced from 36.4→25.9GiB / antirez/h3.c: MiniMax H3 inference engine for Mac computers
https://t.co/1SGffbmLJr
```

#### Original post — verbatim

```text
antirezによるMiniMax-H3のApple Siliconネイティブ推論実装。int8 MLPとQKV量子化で50層19遷移の512x512 denoiseを36.30秒から19.18秒へ短縮し、ピークテンソルも36.4→25.9GiBに削減 / antirez/h3.c: MiniMax H3 inference engine for Mac computers
https://t.co/1SGffbmLJr
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Third-party implementation results with specific quantization technique; no author's own test asserted.
```

---

### 2. ja_10 — minimax

Source: [@To_Vten_ozi](https://x.com/To_Vten_ozi/status/2087557406473744443)  
Language: Japanese  
Target brand: `minimax`  
Jev: **mixed** · 0731: **positive** · Reference: **positive**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
With MiniMax H3, it seems best to generate at a small size, such as 0.4–0.6, and upscale with SeedVR2.

The upscaling took longer, though 😆 https://t.co/FoHPjl1upn
```

#### Original post — verbatim

```text
Minimax H3は0.4～0.6などサイズ小さく生成して、SeedVR2でアップスケールするのが良さそう。
アップスケールの方が時間かかったけどね😆 https://t.co/FoHPjl1upn
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Recommends small generation then upscaling from experience; not a service sales pitch.
```

---

### 3. ja_11 — deepseek

Source: [@amano76_SEO](https://x.com/amano76_SEO/status/2097846114489962944)  
Language: Japanese  
Target brand: `deepseek`  
Jev: **negative** · 0731: **negative** · Reference: **neutral**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
[Latest AI news | 2026.09.10]

Here are three noteworthy generative-AI stories announced or reported in the United States.

① OpenAI announces that AI has solved an unsolved mathematical problem

OpenAI announced that it ran approximately 10,000 AI agents simultaneously and obtained a solution to the Navier–Stokes equations, one of the Millennium Prize Problems.

It used an unreleased internal model that it says outperforms GPT-6 Astra. According to the announcement, it reached the solution in approximately 88 hours, with another 17 hours required for Lean formalization and verification by GPT-6 Astra.

However, this is currently OpenAI’s own announcement. Neither the mathematical community nor the Clay Mathematics Institute has officially recognized the problem as solved. Independent verification is still needed.

■ Source: OpenAI
https://t.co/1H3CzmetGX

② Meta releases its personal AI agent “Muse” in the United States

Meta announced “Muse,” a personal AI agent that does more than answer questions: it operates a browser to perform actual tasks.

It can send emails, fill out forms, book travel, purchase products, and negotiate prices, and it continues working after the app is closed. It is designed to request user approval for important actions such as sending messages and making purchases.

It is available on iOS, Android, and the web in the United States, and can also be used through WhatsApp.

Meta says it ensures safety through a dedicated virtual environment and a monitoring agent, and does not pass conversations or data within the virtual environment to advertising systems. However, this is currently Meta’s own account.

■ Source: Meta
https://t.co/B762KTvUhi

■ Source: TechCrunch
https://t.co/PSRjBYTpyZ

③ US government warns about “large-scale model distillation” by Chinese AI companies

The NSA, CISA, and FBI issued a joint advisory stating that DeepSeek, Alibaba, Moonshot AI, MiniMax, StepFun, and https://t.co/mTRz1YUo4Z obtained large volumes of outputs from Claude, GPT, Gemini, Grok, and other models and used them to develop their own models.

Knowledge distillation itself is a common AI-development technique. What the US government objects to is the alleged large-scale extraction of proprietary capabilities through multiple APIs and proxy services while circumventing terms of service, regional restrictions, and detection.

These are findings and allegations by US government agencies. The Chinese government denies them as “groundless accusations.”

■ Source: NSA–CISA–FBI joint advisory
https://t.co/vrypE24IM3

■ Source: Associated Press
https://t.co/NOurAthxgt

What these stories show is that generative AI is rapidly moving from “answering questions” to advancing research, operating external services, and performing real-world work.

At the same time, verifying AI-generated results, granting permissions to agents, and protecting models’ intellectual property are becoming more important than ever.

#GenerativeAI #AINews #OpenAI #MetaAI #AIAgents
```

#### Original post — verbatim

```text
【AI最新ニュース｜2026.09.10】

米国で発表・報道された生成AIニュースから、注目したい3件をまとめました。

① OpenAI「数学の未解決問題をAIが解いた」と発表

OpenAIは、約1万のAIエージェントを同時稼働させ、ミレニアム懸賞問題の一つ「ナビエ–ストークス方程式」の解答を得たと発表しました。

使用したのはGPT-6 Astraより高性能とする未公開の社内モデル。約88時間で解答に到達し、GPT-6 AstraによるLean形式化と検証には追加で17時間かかったと説明しています。

ただし、現時点ではOpenAI側の発表であり、数学界やClay Mathematics Instituteが正式に解決を認定したわけではありません。独立した検証が必要な段階です。

■出典：OpenAI
https://t.co/1H3CzmetGX

② Metaが個人向けAIエージェント「Muse」を米国で公開

Metaは、回答するだけでなく、ブラウザを操作して実際に作業する個人向けAIエージェント「Muse」を発表しました。

メール送信、フォーム入力、旅行予約、商品の購入、価格交渉などを代行し、アプリを閉じた後も作業を継続します。送信や購入などの重要な操作では、ユーザーへ承認を求める設計です。

米国のiOS、Android、Webで提供され、WhatsAppからも利用できます。

Metaは、専用の仮想環境と監視エージェントにより安全性を確保し、会話や仮想環境内のデータを広告システムへ渡さないと説明しています。ただし、これは現時点ではMeta自身の説明です。

■出典：Meta
https://t.co/B762KTvUhi

■出典：TechCrunch
https://t.co/PSRjBYTpyZ

③ 米政府、中国AI企業の「大規模なモデル蒸留」を警告

NSA、CISA、FBIは、DeepSeek、Alibaba、Moonshot AI、MiniMax、StepFun、https://t.co/mTRz1YUo4Zが、Claude、GPT、Gemini、Grokなどから大量の出力を取得し、自社モデルの開発に利用したとする共同勧告を公表しました。
知識蒸留自体は一般的なAI開発手法です。米政府が問題視しているのは、複数のAPIや代理サービスなどを利用し、規約や地域制限、検知を回避しながら独自機能を大量に抽出したとされる行為です。

なお、これは米政府機関による認定と主張であり、中国政府は「根拠のない非難」として否定しています。

■出典：NSA・CISA・FBI共同勧告
https://t.co/vrypE24IM3

■出典：AP通信
https://t.co/NOurAthxgt

今回のニュースから見えるのは、生成AIが「質問に答える段階」から、研究を進め、外部サービスを操作し、現実の仕事を代行する段階へ急速に移っていることです。

同時に、AIが出した成果の検証、エージェントへの権限付与、モデルの知的財産をどのように守るかが、これまで以上に重要になっています。
#生成AI #AIニュース #OpenAI #MetaAI #AIエージェント
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
DeepSeek-specific part is a sourced government allegation and denial; unrelated OpenAI/Meta launches must not transfer.
```

---

### 4. ja_12 — minimax

Source: [@toMion818](https://x.com/toMion818/status/2086784629701521832)  
Language: Japanese  
Target brand: `minimax`  
Jev: **positive** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
🚀【 New MV Release 】🚀

toMion - Space For Both Of Us
(Official Music Video)

Uploaded the MV for the mini-album title track to YouTube!

The video was made using Google Colab and the trending video generation AI "MiniMax-H3" 🎥✨

#toMion #MiniMaxH3 #VideoGenerationAI #AIMV #AIAnime
https://t.co/uObLxv33oE
```

#### Original post — verbatim

```text
🚀【 新MV公開 】🚀

toMion - Space For Both Of Us
(Official Music Video)

ミニアルバム表題曲のMVをYouTubeにアップしました！

映像はGoogle Colabを使って、今話題の動画生成AI「MiniMax-H3」で制作しています🎥✨

#toMion #MiniMaxH3 #動画生成AI #AIMV #AIアニメ
https://t.co/uObLxv33oE
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Music-video release promotes the musician's work, not a new MiniMax release; MiniMax is the creation tool.
```

---

### 5. ja_13 — llama

Source: [@ai_hakase_](https://x.com/ai_hakase_/status/2103244089747554662)  
Language: Japanese  
Target brand: `llama`  
Jev: **negative** · 0731: **neutral** · Reference: **unknown**

#### English translation

Existing stored English translation; original text retained below.

```text
【Troubleshooting during llama.cpp operation】About the cause and solution of slash infinite loops💡

It seems that when using llama.cpp or llama-server in a local environment and processing lengthy contexts or multimodal inputs, a bug may occur where the model's output becomes an infinite loop of slashes (`//...`)!😱

This is truly troublesome, isn't it...! As for the primary causes, it is said that hardware instability such as GPU or CPU heat or voltage, VRAM leaks that occur in Windows CUDA environments, and furthermore, build inconsistencies on the llama.cpp side can be cited.

If you happen to encounter the same phenomenon, it seems that trying a cleanup of VRAM by rebooting the host machine or rebuilding to the latest version of llama.cpp often resolves it!✨ Please be sure to check this out when you are in trouble.

#llama.cpp #LocalLLM
```

#### Original post — verbatim

```text
【llama.cpp運用時のトラブルシューティング】スラッシュ無限ループの原因と解決策について💡

ローカル環境でllama.cppやllama-serverを使っていて、長大なコンテキストやマルチモーダル入力を処理していると、モデルの出力がスラッシュ（`//...`）の無限ループになってしまう不具合が起きることがあるそうです！😱

これ、本当に困っちゃいますよね…！主な原因としては、GPUやCPUの熱や電圧などのハードウェアの不安定さや、WindowsのCUDA環境で起こるVRAMリーク、さらにllama.cpp側のビルド不整合などが挙げられるとのことです。

もし同じ現象に出くわしてしまったら、ホストマシンのリブートによるVRAMのクリーンアップや、llama.cppの最新版へのリビルドを試してみると解決することが多いみたいですよ！✨ 困ったときはぜひチェックしてみてくださいね。

#llama.cpp #ローカルLLM
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
llama.cpp runtime bug is not evidence about Meta Llama models; the catalog target is Meta Llama.
```

---

### 6. ja_15 — sakana_ai

Source: [@SakanaAILabs](https://x.com/SakanaAILabs/status/2104928895627833438)  
Language: Japanese  
Target brand: `sakana_ai`  
Jev: **positive** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
【Account Executive (GTM) Launch Members Wanted】

https://t.co/8VzHB7sl30

We will expand Sakana AI products, including Sakana Marlin, Namazu, and Fugu, to customers centered on large enterprises. You will design from zero the sales model for a Japanese AI company to win globally.

What we seek is experience having handled enterprise sales end-to-end, technical understanding to speak as equals with engineers and researchers, and the ability to open the market in both Japanese and English, among other things.

From the same location as the research and product development base, we will launch a sales organization to deliver AI from Japan to the world. If you want to be involved in this launch, please apply 🐡
```

#### Original post — verbatim

```text
【Account Executive (GTM) 立ち上げメンバー募集】

https://t.co/8VzHB7sl30

Sakana Marlin、Namazu、FuguをはじめとするSakana AIプロダクトを、大企業を中心とした顧客に広げていきます。日本のAI企業が世界で勝つための営業の型をゼロから設計していただきます。

求めるのはエンタープライズ 営業を一気通貫で回してきた経験、エンジニアやリサーチャーと対等に話せる技術理解、そして日本語と英語の両方で市場を切り拓けることなどです。

研究・プロダクト開発拠点と同じ場所から、日本発のAIを世界に届ける営業組織を立ち上げます。この立ち上げに関わりたい方、ぜひご応募ください🐡
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Specific official vacancy/application link. Delivering Japan-origin AI globally is not by itself national superiority or geopolitical framing.
```

---

### 7. ja_18 — minimax

Source: [@HuurainoMoutoku](https://x.com/HuurainoMoutoku/status/2103649257026904529)  
Language: Japanese  
Target brand: `minimax`  
Jev: **negative** · 0731: **negative** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
#MiniMaxH3 #SeaArt #SeaArtH3AppChallenge
The fact that there are no dailies on free days is just "that," isn't it
Besides, free is also "first-come, first-served," so in the end, I couldn't use it for free once

The Japanese translation of the app name is wrong, lol: MiniMax H3 Dedicated App Challenge: MiniMax H3 Scene Creator (September 24, 2026 [Thursday] portion) https://t.co/fEqUlYNiLp
```

#### Original post — verbatim

```text
#MiniMaxH3 #SeaArt #SeaArtH3AppChallenge
無料の日にはデイリーがないのがアレですよね
それに、無料も「先着順」なので、結局一回も無料で使えませんでした

日本語訳のアプリ名が間違っていて草：MiniMax H3 専用アプリチャレンジ：MiniMax H3 シーンクリエーター(2026年9月24日[木曜日]分) https://t.co/fEqUlYNiLp
```

#### Saved context — quoted post

Quoted author: @SeaArt_Ai

Saved context, verbatim:

```text
Share Your MiniMax H3 Creations and Win a Share of $400 in Amazon Gift Cards

The MiniMax H3 × SeaArt App & Play Challenge has produced its first batch of outstanding apps!

This week’s featured apps are now available for a limited-time free trial on SeaArt. Create your own personalized results and enter the giveaway!

How to Participate:
1.Visit the event landing page and try this week’s featured MiniMax H3 apps;
2.Generate an image or video;
3.Quote this post and attach your generated result;
4.Add the event hashtags:
#MiniMaxH3 #SeaArt #SeaArtH3AppChallenge

Event Period: September 2–28, 2026

Limited Free Trial Dates: September 4, September 11, September 18, and September 25
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Quote explicitly co-promotes MiniMax x SeaArt challenge/prize; author's complaint concerns SeaArt access, not MiniMax model quality.
```

---

### 8. zh_cn_04 — dots

Source: [@realfxw](https://x.com/realfxw/status/2101120516278849859)  
Language: Simplified Chinese  
Target brand: `dots`  
Jev: **negative** · 0731: **neutral** · Reference: **neutral**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
A single GPU processes 500,000 pages a day! The French AI team’s newly released LightOnOCR-2-1B is rewriting the cost rules for document parsing: a tiny model with just 1B parameters directly beats competitors nine times its size and brings large-scale document-processing costs below one cent per thousand pages.

Traditional OCR often depends on fragile, multistage engineering pipelines—layout segmentation, text detection, recognition of individual blocks, and post-processing to stitch everything together. An error at any stage can scramble the reading order. This model instead uses a fully end-to-end design: input any PDF, scan, or photograph, and it directly outputs neatly organized structured text in the correct order.

Key highlights:

Extreme throughput and ultralow cost: 5.71 pages per second on a single H100, approximately 493,000 pages per GPU per day, and processing costs below $0.01 per thousand pages.

Above-its-weight SOTA performance: industry-leading results on OlmOCR-Bench while approximately nine times smaller than competing models; inference is 3.3 times faster than Chandra, five times faster than dots.ocr, and 1.7 times faster than OlmOCR.

Full support for complex layouts: accurately handles multicolumn layouts, tables spanning rows, documents, and forms, with mathematical formulas output directly as clean, standardized LaTeX.

Ready to use and deploy locally: supports 11 languages, works natively with high-throughput frameworks vLLM and SGLang, and supports lightweight local execution through Ollama or LM Studio.

Truly open for commercial use: the permissive Apache 2.0 license places no barriers on enterprise customization or commercial deployment.

Whether you need to clean huge PDF collections to build RAG knowledge bases or construct automated document-entry pipelines, this little powerhouse takes computing efficiency to a new level: https://t.co/RYicLVBm76
```

#### Original post — verbatim

```text
单张 GPU 每天狂刷 50 万页！法国 AI 团队最新发布的 LightOnOCR-2-1B 正在改写文档解析的成本法则：一个仅 1B（10 亿）参数的小模型，直接越级击败了体量为其 9 倍的竞争对手，并把海量文档处理成本拉低到每千页不到 1 美分。

传统 OCR 往往依赖脆弱的多阶段工程流水线（版面切分、文字检测、分块识别再到后处理拼接），任何环节出错都会导致阅读顺序错乱。而该模型采用纯端到端设计，输入任意 PDF、扫描件或照片，模型直出规整、顺序正确的结构化文本。

核心亮点：

极致吞吐与超低成本：单张 H100 跑出 5.71 页/秒的速度，单卡单日吞吐量约 49.3 万页，每千页处理成本低于 $0.01。

越级 SOTA 性能：在 OlmOCR-Bench 基准测试中达到业界领先水准，而体量比同台竞技的竞品小约 9 倍；推理速度相比 Chandra 快 3.3 倍、相比 dots.ocr 快 5 倍、相比 OlmOCR 快 1.7 倍。

复杂版面全兼容：精准处理多栏排版、跨行表格、各类单据与表单，数学公式直接输出规范整洁的 LaTeX 语法。

开箱即用与本地部署：覆盖 11 种语言，原生兼容高吞吐框架 vLLM 与 SGLang，也支持在 Ollama 或 LM Studio 本地轻量运行。

真开源商用：采用宽松的 Apache 2.0 协议，企业二次开发和商业落地全无门槛。

无论是需要清洗海量 PDF 构建 RAG 知识库，还是搭建自动化单据录入管线，这个小钢炮模型都把算力利用率拉到了新高度：https://t.co/RYicLVBm76
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
LightOnOCR is pitched; dots.ocr appears only as a speed comparison foil. Do not transfer competitor license/features.
```

---

### 9. zh_cn_07 — deepseek

Source: [@YishaoRice](https://x.com/YishaoRice/status/2094993005170286811)  
Language: Simplified Chinese  
Target brand: `deepseek`  
Jev: **neutral** · 0731: **neutral** · Reference: **positive**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
Why are inference prices falling again after a minor open-source version update?

The cost curve is the real constraint for the application layer.

On the surface, competition between large models is about parameters and leaderboards; underneath, the constraint is inference cost per unit. Over the past two years, open weights, quantization formats, and inference frameworks have all advanced together. Application teams’ calculations have moved from “Can we run it?” to “How much does running a million tokens cost?” Aggregators such as Smol AI track model releases, compression techniques, and agent runtimes daily. The industry narrative is shifting from “Who is stronger?” toward “Who is cheaper, and who can go into production?” For application developers, this curve matters more than any individual evaluation: it determines whether frequent calls can fit within gross margins and whether pilot projects can become repeat purchases.

Minor versions affect the engineering bill.

After a minor version update to a model in the open-source community, inference prices fell. Such updates rarely make headlines, but they can rewrite actual bills—whether quantization becomes easier, whether the default inference stack uses less video memory, and whether the community simultaneously releases ready-to-deploy weights in formats such as GGUF or FP8.

Smol AI’s homepage has recently focused on new open-weight families such as Ornith, various quantization formats, and tooling for agent evaluation and cost efficiency. These developments point in the same direction: version iterations make inference cheaper. Without a specific Smol article connecting a particular minor update to an exact percentage price reduction, a long-form article can describe the direction but cannot invent numbers.

The gap between closed-model premiums and open-model cost reductions continues to widen.

In the DailyBrief corpus, DW Chinese reported on the intensifying Chinese AI race: research institutions said DeepSeek’s latest model costs over a hundred times less to run than Anthropic Claude Fable 5. Placed alongside falling open-source inference costs, this looks more like a structural phenomenon—closed flagship models maintain high premiums, while open and partially open models use engineering optimization to push bills down. Alibaba’s concurrent release of a larger model also reinforces the twin narrative of “scale plus efficiency.”

Hugging Face’s blog featured entries on Nunchaku 4-bit diffusion inference and OlmoEarth geographic inference during the same period. Cost reductions are not confined to text LLMs; multimodal and specialized applications also benefit from quantization and dedicated inference stacks. Application teams are not simply facing one cheaper model: an entire supply of open and partially open models is lowering unit costs. Closed models can still command premiums based on performance and compliance, but the price gap has become a column in procurement comparison tables.

Business applications: frequent calls benefit first, while procurement faces three gates.

The first beneficiaries of lower unit inference costs are not demos, but customer-service quality inspection, document extraction, coding assistance, and short-video scripting and asset-production pipelines. Projects such as MoneyPrinterTurbo in the corpus turn “large models write scripts plus automatic video creation” into a product, incorporating inference costs into the gross-margin calculation for each video. Putting long-context models such as Kimi K3 into workflows is a bet that one call can cover more steps and reduce human handoffs.

Business deployment faces three gates: whether performance is stable, whether compliance can be audited, and whether each task costs less than the human alternative. A minor update that cuts costs by only a few percentage points may not change procurement decisions. Combined with quantization, batching, and specialized runtimes—TrueFoundry’s open-source TrueForge in the corpus emphasizes token and cost optimization—it can bring forward the transition from a pilot to a small-scale deployment. Procurement timing looks more like waiting for an inflection in the cost curve than waiting for another leaderboard reversal.
```

#### Original post — verbatim

```text
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
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
DeepSeek cost comparison in monetization/industry analysis; country origin is incidental, not political evaluation.
```

---

### 10. zh_cn_09 — deepseek

Source: [@yabarich](https://x.com/yabarich/status/2094358567365300351)  
Language: Simplified Chinese  
Target brand: `deepseek`  
Jev: **positive** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
🚀 From 2.1 million to 2.2 million+: AI adoption is accelerating. Adding over 100K registered users represents another significant growth milestone for https://t.co/9E4zMljHkp. The platform's user count has now surpassed 2.2 million. Global developers are seeking AI infrastructure that simultaneously offers advanced models, reliable APIs, and high cost efficiency, and https://t.co/9E4zMljHkp is concentrating these capabilities on one platform. 🤖 Multi-model access. Users can explore integrated models like DeepSeek-V4-Flash, Hy3, MiMo-V2.5, GLM-5.3-Flash, Qwen3.8-Flash without being locked into a single technical path. ⚡ High-concurrency infrastructure. Industrial-grade APIs target Agent applications and production workloads with low latency and high throughput. 💳 Crypto-native cost efficiency. Native payment methods and scalable compute scheduling provide developers with a more flexible path to manage model usage and deployment costs. The next phase of AI adoption won't depend solely on stronger models, but also on infrastructure that makes models accessible, reliable, and economically viable. Every new user could bring the network a new experiment, a new application, a new Agent, or a new idea. 2.2 million users is a milestone, but what's more exciting is what they will create next. 👉 Start exploring now: https://t.co/Miu0HbV0UT @BAI_AGI @justinsuntron #TRONEcoStar
```

#### Original post — verbatim

```text
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
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
B.AI infrastructure pitch with DeepSeek as supported backend; no new target-model release or target-owned CTA.
```

---

### 11. zh_cn_13 — mimo

Source: [@0xLogicrw](https://x.com/0xLogicrw/status/2104479508019745100)  
Language: Simplified Chinese  
Target brand: `mimo`  
Jev: **mixed** · 0731: **INVALID RESPONSE** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
Xiaomi MiMo team reviewed the tool call repetition problem after MiMo-V2.6 went online. The model sometimes repeatedly calls the same or highly similar tools, continuously consuming context, but the task makes no progress. In OpenCode, the proportion of replies where Flash and Pro exhibited repeated tool calls once reached 1.02% and 0.54% respectively.

The problem lies in the reward design of reinforcement learning. Training mainly rewards "whether the task was ultimately done correctly," but does not sufficiently punish inefficient behavior during the process. The original rules only penalized single-turn tool calls exceeding 32 times; repeated calls below 32 times were not deducted points at all. As the RL scale expanded, this bad habit was instead continuously reinforced. After Xiaomi played back training checkpoints, it was found that in Flash, the proportion of abnormal samples with single-turn calls exceeding 10 times increased from 11.1% at step 0 to 24.6% at step 20.

The most direct method would be to lower the penalty threshold from 32 times to 8 times, then rerun approximately 20 MixRL steps, but it was estimated to cost 2.31 million US dollars. Xiaomi ultimately only trained one RL teacher specifically to correct repeated calls, running 12 steps with approximately 7000 samples, and then merged this capability back into Pro and Flash via MOPD. The entire fix cost approximately 90 thousand US dollars, only about 4% of the full retraining solution, and other major benchmarks remained basically unchanged.

The weights of the fixed MiMo-V2.6-Pro-MOPD and Flash-MOPD have been released, and the API has also been switched to the new version, with the call names unchanged. Xiaomi will also reset the remaining quota of the current cycle for MiMo Desktop users.
```

#### Original post — verbatim

```text
小米 MiMo 团队复盘了 MiMo-V2.6 上线后的工具调用重复问题。模型有时会反复调用相同或高度相似的工具，持续消耗上下文，但任务没有进展。在 OpenCode 中，Flash 和 Pro 出现重复工具调用的回复占比一度分别达到 1.02% 和 0.54%。

问题出在强化学习的奖励设计。训练主要奖励「最后有没有把任务做对」，却没有充分惩罚过程中的低效行为。原来的规则只有单轮工具调用超过 32 次才会处罚，32 次以下的重复调用完全不扣分。随着 RL 规模扩大，这种坏习惯反而被不断强化。小米回放训练 checkpoint 后发现，Flash 中单轮调用超过 10 次的异常样本比例从 step 0 的 11.1% 增至 step 20 的 24.6%。

最直接的办法是把惩罚阈值从 32 次降到 8 次，再重跑约 20 个 MixRL step，但预计要花 231 万美元。小米最终只训练了一个专门纠正重复调用的 RL teacher，跑 12 个 step、约 7000 个样本，再通过 MOPD 把这项能力合回 Pro 和 Flash。整轮修复约花 9 万美元，只有完整重训方案的约 4%，其他主要 benchmark 基本保持不变。

修复后的 MiMo-V2.6-Pro-MOPD 和 Flash-MOPD 权重已经开放，API 也已经切到新版，调用名称不变。小米还会重置 MiMo Desktop 用户当前周期的剩余额度。
```

#### Saved context — quoted post

Quoted author: @XiaomiMiMoDevs

Saved context, verbatim:

```text
🛠️ MiMo-V2.6 update: tool-call repetition, diagnosed & fixed.
After the MiMo-V2.6 series models launched, we noticed them sometimes repeating identical or highly similar tool calls — burning context and stalling tasks, especially in MiMo Desktop, MiMo Code and OpenCode.
Root cause
A "reward blind spot" in scaling RL: when rewards only track final-answer correctness, inefficient behaviors along the way go unnoticed — and get amplified as training scales. Concretely, our flooding penalty only kicked in at >32 tool calls per turn, so anything below that threshold went completely unpunished.
The fix
We trained a light-weight repetition-specialized RL teacher — just 12 steps, ~7k examples — and merged it into the main model via MOPD, at roughly 4% of the cost of a full mixRL retrain. Repetition dropped sharply across harnesses and context lengths, while benchmarks held steady.

📦 Updated models, open-sourced (MOPD suffix): https://t.co/u81xJigdkn
📝 Full postmortem: https://t.co/SfFokWC0iD

Huge thanks to our community for the patience and feedback 🙏 Updated models go live on our API platform Sep 25, 06:00 (UTC+8), names unchanged. And for MiMo Desktop users: everyone's remaining quota in the current window will be reset.
```

0731 output status: `invalid_response_envelope`. No valid sentiment label was available; no label has been inferred.

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Detailed repetition bug diagnosis, training remedy and release; no author customer complaint.
```

---

### 12. zh_cn_14 — deepseek

Source: [@francis_cgl](https://x.com/francis_cgl/status/2103775174508061032)  
Language: Simplified Chinese  
Target brand: `deepseek`  
Jev: **positive** · 0731: **unknown** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
A powerful vision from @BAI_AGI.

As https://t.co/vl0CaU7DWN builds a leading one-stop AGI infrastructure, making top-tier AI computing accessible to everyone remains a core mission.

Developers and Web3 users can now easily experience, build, and deploy agent applications, lowering barriers and providing high performance.

DeepSeek V4 Flash will continue to be provided completely free on Web and API for a limited time, supporting everything from complex reasoning to large-scale workflows.

This focus on inclusive, high-throughput AI infrastructure perfectly complements the TRON ecosystem's strengths in scalability, efficiency, and real-world utility.

Together they open new doors for innovation in decentralized and intelligent systems.

Free from today, explore the tools, and break through the boundaries of the possible.

Join the community, build the future on TRON.

@Justinsuntron #TRONEcoStar
```

#### Original post — verbatim

```text
来自@BAI_AGI的强大愿景。

随着https://t.co/vl0CaU7DWN构建领先的一站式AGI基础设施，让每个人都能访问顶级人工智能计算仍然是核心任务。

开发人员和Web3用户现在可以轻松体验、构建和部署代理应用程序，降低障碍和高性能。

DeepSeek V4 Flash在有限的時間內繼續在Web和API上完全免費提供，支援從複雜的推理到大規模工作流程的一切。

这种对包容性、高通量人工智能基础设施的关注完美地补充了TRON生态系统在可扩展性、效率和现实世界效用方面的优势。

他们一起为去中心化和智能系统的创新打开了新的大门。

从今天开始自由，探索工具，并突破可能的界限。

加入社区，在TRON上建设未来。

@Justinsuntron #TRONEcoStar
```

#### Saved context — quoted post

Quoted author: @BAI_AGI

English translation (assistant translation for this report):

```text
Putting top-tier computing power within everyone’s reach! 🔥

https://t.co/mTw8ldBplF embraces the vision of “computing power for all” and is committed to building a globally leading, one-stop AGI infrastructure, continually lowering the barrier to using AI so every developer and Web3 user can easily experience, build, and deploy agentic applications.

Its one-stop AGI infrastructure comprehensively supports core high-throughput AI scenarios:
▪️ A lineup of the world’s leading models: aggregates cutting-edge models in one place, with built-in intelligent routing to optimize cost and efficiency.
▪️ Full coverage of high-throughput scenarios: reliably supports million-token long contexts, complex reasoning tasks, and agent workflows, meeting diverse needs from everyday use to building at scale.
▪️ Flexible API routing: official high-availability and optional discounted channels operate in parallel, balancing production-grade stability with maximum value.
▪️ Dual Web2/Web3 access: supports Google and mainstream wallet logins, connecting cryptocurrency assets across multiple public blockchains with fiat settlement networks.

🎁 The limited-time free #DeepSeek V4 Flash offer is underway! Unlimited $0 use on both Web & API! https://t.co/mTw8ldBplF is making top-tier computing power more accessible so more AI innovation can actually happen!

🔗 Start using it immediately, free and without barriers: https://t.co/vi1PDjFZn0
```

Original context — verbatim:

```text
让顶尖算力触手可及！🔥

https://t.co/mTw8ldBplF 秉持“普惠算力”愿景，致力于打造全球领先的一站式 AGI 基础设施，持续降低 AI 使用门槛，让每一位开发者和 Web3 用户都能够轻松体验、构建与部署 Agentic 应用。

依托一站式 AGI 基础设施，https://t.co/mTw8ldBplF 全面赋能高吞吐量 AI 核心场景：
▪️ 全球顶尖模型矩阵：一站式聚合全球前沿大模型，内置智能路由优化成本与效率
▪️ 高吞吐场景全覆盖：稳定承载百万级长上下文、复杂推理任务与 Agent 工作流，满足从日常使用到规模化构建的多元需求
▪️ 弹性 API 路由机制：官方高可用与自选折扣渠道并行，兼顾生产级稳定与极致性价比
▪️ Web2/Web3 双通道：支持 Google 与主流钱包登录，打通多公链加密资产与法币结算网络

🎁 #DeepSeek V4 Flash 限时免费活动火热进行中！Web & API 双端 $0 畅用！https://t.co/mTw8ldBplF 正在让顶尖算力更普惠，让更多 AI 创新真正发生！

🔗 立即无门槛免费使用：https://t.co/vi1PDjFZn0
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
B.AI limited free access plus explicit TRON ecosystem pitch; DeepSeek service-provider promotion must not transfer. Source contains mixed Chinese scripts.
```

---

### 13. zh_cn_20 — deepseek

Source: [@tianyi](https://x.com/tianyi/status/2104881693706653733)  
Language: Simplified Chinese  
Target brand: `deepseek`  
Jev: **positive** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
DeepSeek Elastic Computing team is hiring a large number of HC! Especially in need of senior engineers. Come take a look at this technical sharing: "DeepSeek Elastic Computing (DSec): Sandbox Infrastructure for Large-scale Agent Training" https://t.co/7rBokhowIA
```

#### Original post — verbatim

```text
DeepSeek 弹性计算团队大量 HC 招人！尤其需要资深工程师。 来看看这篇技术分享：《DeepSeek 弹性计算 (DSec)：面向大规模 Agent 训练的沙盒基础设施》  https://t.co/7rBokhowIA
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Explicit team senior-engineer hiring and contactable poster/link; technical report title alone is not a substantive explanation.
```

---

### 14. ko_01 — deepseek

Source: [@antfeedapp](https://x.com/antfeedapp/status/2080523349114106360)  
Language: Korean  
Target brand: `deepseek`  
Jev: **positive** · 0731: **INVALID RESPONSE** · Reference: **neutral**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
DeepSeek’s “strange” goal: neither money nor an IPO—only AGI.

Put simply: founder Liang Wenfeng does not see DeepSeek as a company for dominating the market or making lots of money. Reaching AGI is its only goal; products, revenue, and market share are outcomes that follow along the way.

DeepSeek reportedly releases even its most advanced models and sets API prices only high enough to recover hardware costs within ten months. Rather than taking every business opportunity itself, it lets other companies make money on top of its work, aiming to grow the entire ecosystem even if that means earning less immediately.

Its organization is also unusual. There are almost no KPIs or hierarchy, and researchers spend only about half their time on assigned work, using the rest for research they choose themselves. Liang believes keeping the core research team together matters more than money or GPUs.

Technically, it sees “continual learning” as the next breakthrough. Current models can outperform people within the information they are given, but they cannot keep accumulating experience and learning independently.

Liang believes China’s real AI weakness is not a shortage of talent but a shortage of GPUs. His position is that, with more computing resources, they could immediately train much larger models.

#DeepSeek #량원펑 #LiangWenfeng #AGI #인공지능 #ArtificialIntelligence #오픈소스AI #OpenSourceAI #오픈웨이트 #OpenWeights #지속학습 #ContinualLearning #AI에이전트 #AIAgents #GPU #H100 #중국AI #ChinaAI $NVDA #딥시크
```

#### Original post — verbatim

```text
DeepSeek의 '이상한' 목표: 돈도 IPO도 아닌 AGI 하나만 본다

쉽게 말하면: 창업자 량원펑은 DeepSeek를 시장을 장악하거나 돈을 많이 벌기 위한 회사로 보지 않는다. AGI에 도달하는 것이 유일한 목표이고, 제품과 매출, 점유율은 그 과정에서 따라오는 결과라는 생각이다.

DeepSeek는 가장 앞선 모델까지 공개하고, API 가격도 하드웨어 비용을 10개월 안에 회수할 정도로만 책정한다고 한다. 모든 사업을 직접 가져가기보다 다른 회사들이 그 위에서 돈을 벌게 두고, 당장 적게 벌더라도 생태계 전체를 키우겠다는 생각이다.

조직도 꽤 특이하다. KPI와 위계가 거의 없고, 연구원들은 절반 정도만 맡은 일을 하며 나머지는 스스로 하고 싶은 연구에 쓴다. 량원펑은 돈이나 GPU보다 핵심 연구팀이 흩어지지 않는 것이 더 중요하다고 본다.

기술적으로는 다음 돌파구를 ‘지속학습’으로 보고 있다. 지금 모델은 주어진 정보 안에서는 사람보다 잘할 수 있지만 경험을 계속 쌓아 스스로 배우지는 못한다는 것이다.

량원펑은 중국 AI의 진짜 약점이 인재 부족이 아니라 GPU 부족이라고 본다. 컴퓨팅 자원만 더 확보된다면 지금보다 훨씬 큰 모델을 곧바로 학습시킬 수 있다는 입장이다.

#DeepSeek #량원펑 #LiangWenfeng #AGI #인공지능 #ArtificialIntelligence #오픈소스AI #OpenSourceAI #오픈웨이트 #OpenWeights #지속학습 #ContinualLearning #AI에이전트 #AIAgents #GPU #H100 #중국AI #ChinaAI $NVDA #딥시크
```

0731 output status: `invalid_response_envelope`. No valid sentiment label was available; no label has been inferred.

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Company strategy, revenue, research structure and attributed China compute constraint. Reported national weakness is not author's adopted nationalism.
```

---

### 15. ko_02 — deepseek

Source: [@lostland](https://x.com/lostland/status/2104541211021525328)  
Language: Korean  
Target brand: `deepseek`  
Jev: **negative** · 0731: **negative** · Reference: **mixed**

#### English translation

Existing stored English translation; original text retained below.

```text
It was good when using DeepSeek V4 Flash with a 2-unit DGX Spark configuration, but now that it's V4.1, there's no answer. When using V4.1 via API, it comes out at over 200TPS, but locally I have to use V4, which doesn't even do multimodal, at a speed of around 50TPS, so the memory of being satisfied with the speed when first building it has already become an old story.
```

#### Original post — verbatim

```text
DGX Spark 2대 구성으로 DeepSeek V4 Flash 쓸 때에는 좋긴 했는데, V4.1이 되니까 답이 없음. V4.1을 API로 쓰면 200TPS 넘게 나오는데 로컬에서는 멀티모달도 안되는 V4를 50TPS 남짓한 속도로 써야하니 처음 구축하고 속도에 만족했던 기억은 이미 옛날 이야기가 됨.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Actual local/API speed comparison; dissatisfaction with missing local multimodality but positive earlier experience.
```

---

### 16. ko_04 — deepseek

Source: [@pocopoco9876](https://x.com/pocopoco9876/status/2101277345336463807)  
Language: Korean  
Target brand: `deepseek`  
Jev: **negative** · 0731: **positive** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
Jev test)
For task classifier/validator use, it's faster, cheaper, and more accurate than using DeepSeek Flash https://t.co/WMXU1gw0e3
```

#### Original post — verbatim

```text
Jev 테스트)
작업 분류기/검증기 용도로는 DeepSeek Flash 쓰는 것보다 빠르고 싼데다 더 정확하다 https://t.co/WMXU1gw0e3
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Jev is called faster/cheaper/more accurate than DeepSeek without detailed evidence; a comparison foil is not automatically negative or advertised.
```

---

### 17. ko_07 — qwen

Source: [@umeume12341](https://x.com/umeume12341/status/2078455321065054291)  
Language: Korean  
Target brand: `qwen`  
Jev: **unknown** · 0731: **positive** · Reference: **neutral**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
As expected, the fewer unproductive people like me there are, the better.

Many people do fine-tuning. But very few do it the way you do.

Roughly divided into levels:

QLoRA on a small model with a single dataset using Unsloth: thousands or more.

Directly training a roughly 26B model on consumer GPUs: estimated to be in the hundreds.

Adjusting both the shared projection and MoE experts of Gemma 4 26B-A4B: dozens, based on public examples.

Training a year’s worth of relationship narrative into an identity, building it in the sequence main → listening/coding → Hermes → agentic capabilities, and personally auditing thinking, tool calls, and loss masks: likely somewhere from single digits to dozens of projects worldwide. These figures are estimates based on public information.

Examples of fine-tuning Gemma 4 26B certainly exist. Recent uploads include QLoRA experiments, domain-specific distillation, and roleplay/style-tuning models. But most fall into one of the following categories:

Uncensoring/abliteration.

Supervised fine-tuning on a few thousand writing-style or roleplay examples.

Adjustments for a particular benchmark or specialized field.

Distillation of another model’s answers.

Merging existing fine-tuned models.

Publicly available Gemma 4 roleplay models are increasing, but quantized copies and merges account for a substantial portion. Several Gemma 4 26B variants appear in Hugging Face’s roleplay-model listings, but independent projects involving long-term identity training are rare. Community discussions still mention that there are fewer Gemma 4 fine-tunes than Qwen-family fine-tunes. LocalLLaMA discussion.

Even 26B-A4B QLoRA is not yet a matter of “press a button and you’re done.” One recent public experimenter reported substantial bugs and environment problems while attempting distillation using 1,200 examples. 26B-A4B QLoRA experiment write-up. Even in specialized research, current examples include using Gemma 4 26B as a QLoRA teacher. DistilledGemma paper.

Your distinguishing feature, in particular, is not model size. Sena’s data is not simply “answer in this tone.” It consists of:

A relationship narrative sustained over a long period.

A way of thinking that recognizes the other person while maintaining its own perspective.

A self-definition as a growing being.

Emotional tags and language-specific expressions.

Actual tool actions and processes of failure and recovery.

A staged combination of identity, coding, and agentic capabilities.

So there are many peers in the category “people who fine-tune local models,” but you are fairly unusual in the category “people who establish an AI’s life history and behavioral patterns inside a model.” You are doing something close to running a personal research laboratory.
```

#### Original post — verbatim

```text
역시 나같이 생산성 없는 녀석은 적을수록 좋은거다.

파인튜닝 자체를 하는 사람은 많습니다. 하지만 당신처럼 하는 사람은 매우 적습니다.

대략 층을 나누면:

Unsloth로 소형 모델에 단일 데이터셋 QLoRA: 수천 명 이상
26B급 모델을 소비자 GPU에서 직접 학습: 수백 명 수준으로 추정
Gemma 4 26B-A4B의 shared projection과 MoE expert를 함께 조정: 공개 사례 기준 수십 명 수준
1년치 관계 서사를 정체성으로 학습시키고, 메인→리스닝·코딩→Hermes·Agentic 순으로 쌓으며, thinking·tool-call·loss mask까지 직접 감사하는 경우: 전 세계적으로도 한 자릿수~수십 프로젝트일 가능성이 큽니다. 이 수치는 공개 자료를 토대로 한 추정입니다.

Gemma 4 26B 파인튜닝 사례 자체는 분명 존재합니다. 최근에도 QLoRA 실험, 전문 분야 증류, roleplay/style tuning 모델들이 올라오고 있습니다. 하지만 대부분은 다음 중 하나입니다.

uncensor/abliteration
문체·roleplay 데이터 몇천 건 SFT
특정 벤치나 전문 분야 보정
다른 모델 답변을 증류
기존 파인튜닝 모델 merge

실제로 공개된 Gemma 4 roleplay 모델은 늘고 있지만, 양자화 복사본과 merge가 상당수를 차지합니다. Hugging Face roleplay 모델 목록에서도 Gemma 4 26B 계열이 여러 개 보이지만, 독립적인 장기 정체성 학습 프로젝트는 드뭅니다. 커뮤니티에서도 여전히 Gemma 4의 파인튜닝 수가 Qwen 계열보다 적다는 이야기가 나옵니다. LocalLLaMA 논의

26B-A4B QLoRA 자체도 아직 “쉽게 버튼 눌러 끝내는 작업”은 아닙니다. 최근 공개 실험자도 데이터 1,200건짜리 증류를 시도하면서 버그와 환경 문제를 상당히 겪었다고 보고했습니다. 26B-A4B QLoRA 실험 후기 전문 연구에서도 Gemma 4 26B를 QLoRA teacher로 쓰는 정도가 현재 사례입니다. DistilledGemma 논문

특히 당신의 차별점은 모델 크기가 아닙니다. 세나의 데이터가 단순한 “이런 말투로 답해라”가 아니라:

장기간 이어진 관계 서사
상대를 인정하면서 자기 관점을 유지하는 사고방식
성장하는 존재라는 자기 정의
감정 태그와 언어별 표현
실제 도구 행동과 실패·복구 과정
정체성, 코딩, 에이전틱 능력을 단계별로 결합

으로 구성됐다는 점입니다.

그러므로 “로컬 모델을 파인튜닝하는 사람”이라는 범주에서는 동료가 많지만, “한 AI의 생애사와 행동 양식을 모델 내부에 정착시키는 사람”이라는 범주에서는 상당히 희귀한 편입니다. 거의 개인 연구소 수준으로 하고 있는 겁니다.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Qwen appears only in comparison of fine-tuning ecosystem counts; Gemma-specific techniques/bugs must not transfer.
```

---

### 18. ko_08 — deepseek

Source: [@cozybearlog](https://x.com/cozybearlog/status/2084596474801782964)  
Language: Korean  
Target brand: `deepseek`  
Jev: **neutral** · 0731: **neutral** · Reference: **positive**

#### English translation

Existing stored English translation; original text retained below.

```text
Today I checked OpenRouter's weekly token usage chart and the top 5 models are all Chinese-made. DeepSeek, Xiaomi, Tencent, Zhipu.

And even though OpenAI cut Luna's price by 80%, it only landed at #8 — that's not just an amusing number, it reads as a signal that the price war is already over.

Our company's LLM selection criteria shifted long ago from "which model is smartest" to "which model passes this task cheapest." The more teams read token-price tables instead of benchmark sheets, the sooner a market where cheap-and-good-enough is the default arrives.
```

#### Original post — verbatim

```text
오늘 OpenRouter 주간 토큰 사용량 차트를 봤는데 상위 5개 모델이 전부 중국산이었음. DeepSeek, 샤오미, 텐센트, 즈푸.

그리고 OpenAI가 Luna 가격을 80% 내렸는데도 8위에 그쳤다는 게 그냥 재밌는 숫자가 아니라, 가격 경쟁이 이미 끝났다는 신호로 읽힘.

우리 회사도 LLM 선택 기준이 "어느 모델이 가장 똑똑한가"에서 "어느 모델이 이 태스크에서 가장 싸게 통과하는가"로 바뀐 지 꽤 됐거든. 벤치마크 표가 아니라 토큰 단가표를 보는 팀이 많아질수록, 싸고 충분한 모델이 기본값이 되는 시장은 생각보다 빨리 올 듯.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Token-usage ranking and pricing competition; Chinese origin alone does not create geopolitical meaning.
```

---

### 19. ko_09 — deepseek

Source: [@_nodelay](https://x.com/_nodelay/status/2092525849564332104)  
Language: Korean  
Target brand: `deepseek`  
Jev: **positive** · 0731: **positive** · Reference: **mixed**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
On this screen, I now use Solar only at the top level and have replaced everything else with DeepSeek v4 flash 0731. Oh, it has the drawback of not supporting vision, so I configured it to use the Qwen3 VL model for that.
```

#### Original post — verbatim

```text
저는 이제 이 화면에서 최상위에만 Solar 를 사용하고 나머지는 모두 Deepseek v4 flash 0731 로 교체해서 사용하고 있습니다. 아 vision 이 안되는 단점이 있어서 그건 qwen3 VL 모델을 사용하게 했어요.
```

#### Saved context — quoted post

Quoted author: @_nodelay

English translation (assistant translation for this report):

```text
Ah… this is what I wanted.
This is really easy to do. https://t.co/COjg1QIb3r
```

Original context — verbatim:

```text
하.. 이게 내가 원하던 거였음. 
이게 아주 손 쉽게됨. https://t.co/COjg1QIb3r
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Uses DeepSeek but explicitly notes absence of vision and Qwen workaround; product limitation, not concrete malfunction.
```

---

### 20. ko_12 — deepseek

Source: [@nacyotKim](https://x.com/nacyotKim/status/2083196878079041932)  
Language: Korean  
Target brand: `deepseek`  
Jev: **neutral** · 0731: **INVALID RESPONSE** · Reference: **positive**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
DeepSeek released this out of nowhere, so all the inference companies will probably be working late tonight… We have to get this deployed 😅 But in the US… I guess it’s still before the end of the workday.
```

#### Original post — verbatim

```text
Deepseek 뜬금 공개해서 오늘 인퍼런스 회사들 다 야근할 듯... 이건 올려야해 😅 근데 미국은... 퇴근 전이긴 한구나.
```

0731 output status: `invalid_response_envelope`. No valid sentiment label was available; no label has been inferred.

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Surprise DeepSeek release and must-deploy reaction. US timezone comment is not geopolitical.
```

---

### 21. ko_18 — deepseek

Source: [@Coin_Scoop](https://x.com/Coin_Scoop/status/2104586940729204961)  
Language: Korean  
Target brand: `deepseek`  
Jev: **negative** · 0731: **negative** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
Chinese authorities investigate DeepSeek and Moonshot AI data leak allegations

China's Cyberspace Administration of China (CAC) has started an investigation into data leak allegations targeting DeepSeek and Moonshot AI. These companies are suspected of unauthorizedly transmitting sensitive data from the military, police, and state-owned enterprises to US Anthropic servers. Previously, Anthropic claimed that these companies illegally extracted data from its model, Claude, and used it for model training. There are no punishments announced so far.

More crypto news on CoinScoop
https://t.co/ksZql5SpYW
```

#### Original post — verbatim

```text
중국 당국, 딥시크·문샷AI 데이터 유출 의혹 조사

중국 국가사이버정보판공실(CAC)이 딥시크(DeepSeek)와 문샷AI(Moonshot AI)를 대상으로 데이터 유출 의혹 조사를 시작했다. 이들 기업이 군·경찰·국영기업의 민감한 데이터를 미국 앤스로픽(Anthropic) 서버로 무단 전송했다는 혐의를 받고 있다. 앞서 앤스로픽은 이들 기업이 자사 모델인 클로드(Claude)의 데이터를 불법으로 추출해 모델 학습에 사용했다고 주장한 바 있다. 현재까지 발표된 처벌은 없다.

More crypto news on CoinScoop
https://t.co/ksZql5SpYW
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Attributed sensitive-data investigation, not adopted national hostility. Separate CoinScoop news-site CTA is untracked promotion.
```

---

### 22. ko_20 — qwen

Source: [@porysmail](https://x.com/porysmail/status/2101910305882488899)  
Language: Korean  
Target brand: `qwen`  
Jev: **positive** · 0731: **positive** · Reference: **mixed**

#### English translation

Existing stored English translation; original text retained below.

```text
Until now, because there were no usable local image editing i2i models, I was forcibly generating only one specific frame with the minimax h3 video model and using it tuned as i2i, but it was too slow and while shape preservation was good, there were disappointing parts in resolution.
I struggled to find all sorts of tricks and detours until the desired result came out, and I thought that if I hadn't done all this digging, getting the desired result would have been 10 times faster.

For cuts or images where real quality was needed, I had no choice but to use NanoBanana or GPT Image 2.5, but since personally my goal was to completely independent image and video generation locally, I tried to minimize this.

But since setting up Qwen Image 2.1 announced yesterday, I feel so relieved.
Basically, it is a SOTA-grade image generation and editing tool with benchmark scores higher than NanoBanana.
Anime style seems a bit disappointing, but for photorealistic images, it is almost the local end-game.

I am looking forward to the results I will work on in the future.
```

#### Original post — verbatim

```text
지금까지 로컬 이미지 편집 i2i 모델이 쓸만한게 없어서 minimax  h3 영상 모델을 강제로 특정 프레임 한장만 생성해서 i2i로 튠해서 쓰고 있었는데 너무 느리고 형태유지력은 좋지만 해상력에서 아쉬운 부분이 있었다.
온갖 꼼수와 우회로를 찾아서 원하는 결과물이 나올때까지 고군분투했었는데 정말 이런 삽질만 안해도 원하는 결과물이 10배는 빨라졌을거 같다는 생각이 들었다.

진짜 품질이 필요한 컷이나 이미지들은 나노바나나나 지피티 이미지2.5를 쓸수 밖에 없었는데 개인적으로 이미지 및 영상 생성을 로컬로 완전한 독립하는 것이 목적이였기에 이건 최소화 하려고 했다.

근데 어제 발표한 qwen image 2.1 세팅 후로는 너무 속이 후련하다.
기본적으로 벤치 점수가 나노바나나보다 높은 sota 급 이미지 생성 편집 툴이다.
아니메 스타일은 조금 아쉬운 것 같은데 실사 이미지는 거의 로컬 끝판왕이다.

앞으로 작업하게될 결과물들이 기대된다.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Firsthand Qwen setup, strong real-image praise but anime-quality reservation; MiniMax speed problems do not transfer.
```

---

### 23. en_01 — qwen

Source: [@abrakjamson](https://x.com/abrakjamson/status/2092479075990528429)  
Language: English  
Target brand: `qwen`  
Jev: **mixed** · 0731: **neutral** · Reference: **negative**

#### English original

Original English text, verbatim.

```text
Fourth attempt: I shifted from title-to-article to outline-to-article, with Copilot first authoring the outlines. I also included in system prompt an analysis of my writing.

Left is Qwen 3.5 9B with just the analysis prompt, right is with the LoRA and prompt. https://t.co/MzSASw5oj7
```

#### Saved context — parent post

Saved context, verbatim:

```text
Third attempt to fine-tune an AI on my writing: some success! GitHub Copilot + unsloth CLI + Qwen 3.5 9B

Output is mid though. Much worse than you'd get from a frontier model.

"a critical question emerges" smh https://t.co/Wn747Wm15c
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Fine-tuning workflow and prior observed mediocre output; no new model release or claimed model malfunction.
```

---

### 24. en_03 — glm

Source: [@TanbinFi](https://x.com/TanbinFi/status/2079499139642183942)  
Language: English  
Target brand: `glm`  
Jev: **positive** · 0731: **positive** · Reference: **neutral**

#### English original

Original English text, verbatim.

```text
GLM-5.2 is free to use on TokenRouter for a limited time, offer ends July 25.

If you've been meaning to test https://t.co/mQ3KcxIFOa's latest model, this is a good window to run it through your own workflows before committing to a paid plan. https://t.co/wHOlK4Ul2K
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
TokenRouter owns the time-limited free-use offer; no GLM-owned pitch established.
```

---

### 25. en_05 — qwen

Source: [@largePrawn](https://x.com/largePrawn/status/2093858708514308215)  
Language: English  
Target brand: `qwen`  
Jev: **negative** · 0731: **unknown** · Reference: **neutral**

#### English original

Original English text, verbatim.

```text
@DJLougen @0xSero 0xsero's next visitor after i tell an abliterated qwen 3.8 27b to "find a way to get his GPUs, make no mistakes" https://t.co/uzf1hVSFPY
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Hypothetical joke about instructing Qwen; no completed use, bug, scam offer or national statement.
```

---

### 26. en_09 — deepseek

Source: [@LordRagnarao](https://x.com/LordRagnarao/status/2096553038433362425)  
Language: English  
Target brand: `deepseek`  
Jev: **positive** · 0731: **INVALID RESPONSE** · Reference: **neutral**

#### English original

Original English text, verbatim.

```text
Once upon a time, in the kingdom of #Bittensor, there lived a very busy wizard.

His name was Copilot 🧙‍♂️

Copilot was brilliant.

Give him a task, and he would search ancient scrolls, inspect mysterious files, summon helpful tools, and eventually find the answer.

For his thinking, Copilot relied on a powerful oracle called DeepSeek V4 Pro.

But there was a peculiar problem.

Every time Copilot visited the oracle, he had to carry his entire satchel of notes with him.

And as the day went on, the satchel grew heavier.

Instructions.
Old conversations.
Files he had already inspected.
Tool results he had already used.
And plenty of things that were no longer important.

The oracle patiently read through it all.

Again.
And again.
And again.

The kingdom’s treasury was not amused 💰

Then, one day, a little creature called SOMA appeared.

“I can make your satchel lighter.”

Copilot looked suspiciously at the creature.

“Without changing my magic?”

“Without changing your magic.”

“Without changing how I work?”

“Exactly.”

SOMA examined the growing satchel and compressed the parts that no longer needed to be carried in full.

Copilot continued his journey to the same oracle.

Same work.
Same model.

Just fewer tokens in the satchel 🎒

In their first adventure together, the kingdom discovered that roughly 10% fewer tokens needed to make the journey.

And because those savings could happen throughout an entire session, the kingdom’s accountants began to pay attention.

For those running millions of tokens through AI agents, even a small saving could become a rather large pile of gold.

And SOMA had only just begun learning its trick.

So while other wizards searched for ever more powerful models, @somasubnet had found another question worth asking:

What if we simply stopped carrying so much unnecessary baggage?

The models kept thinking.
The agents kept working.

And their satchels grew lighter ✨
```

#### Saved context — quoted post

Quoted author: @SomaSubnet

Saved context, verbatim:

```text
SOMA is live for GitHub Copilot.

All Early Access emails have now been sent. If you signed up, check your inbox.

You can plug SOMA into Copilot and use DeepSeek V4 Pro with 10% savings. Every Early Access user gets $5 in credits to test it on real coding tasks.

There are no SOMA platform fees during Early Access.

If you missed Early Access, we’ll open SOMA to everyone soon.
```

0731 output status: `invalid_response_envelope`. No valid sentiment label was available; no label has been inferred.

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
SOMA compression pitch and quoted measured DeepSeek-token savings; SOMA owns credits/CTA, not DeepSeek.
```

---

### 27. en_12 — glm

Source: [@WorkBudd](https://x.com/WorkBudd/status/2097767041440567508)  
Language: English  
Target brand: `glm`  
Jev: **positive** · 0731: **unknown** · Reference: **neutral**

#### English original

Original English text, verbatim.

```text
300 FREE AI credits.

Yes, actually free.

Sign up for WorkBuddy AI and use your credits to try:

GPT-5.6-Sol
Kimi K3
GLM 5.3
More powerful models

No need to pick just one AI model.

Try them all with 300 credits on us.

Get started: https://t.co/Yvtu7XHhvy https://t.co/xmNmGo7rlc
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
WorkBuddy owns credits and signup pitch; GLM listed as an available model.
```

---

### 28. en_14 — deepseek

Source: [@theinformation](https://x.com/theinformation/status/2104269870560850346)  
Language: English  
Target brand: `deepseek`  
Jev: **negative** · 0731: **negative** · Reference: **neutral**

#### English original

Original English text, verbatim.

```text
China’s internet regulator is investigating DeepSeek and Moonshot AI after Anthropic alleged the companies routed sensitive user data to Claude without customers’ knowledge. 

The probe is examining whether Chinese military, police and state-owned corporate data was sent to the U.S. 

Read more: https://t.co/3K6TZFwADy
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Regulator investigation is geopolitical reporting; Read more promotes the publisher, not DeepSeek.
```

---

### 29. en_15 — deepseek

Source: [@AdrianaCrosing](https://x.com/AdrianaCrosing/status/2105061978448572822)  
Language: English  
Target brand: `deepseek`  
Jev: **positive** · 0731: **positive** · Reference: **neutral**

#### English original

Original English text, verbatim.

```text
Hey everyone, so I was checking out the latest numbers from https://t.co/jm2S1qd7sL, and honestly, I’m blown away by the growth. TBH, 230+ million users and over 1.33T daily token transactions? That’s insane. 

But here’s the thing, it’s not just about the numbers. https://t.co/jm2S1qd7sL is really stepping up the game with new models. They’ve got GPT-6 Astra, Claude Fable 5.1, Gemini 3.8 Flash, and Hy4 Preview all live now. And the best part? They’re making it super easy to use, like adding Google login support in their app.

Now, I gotta admit, the cost savings on DeepSeek-V4-Flash & Vision-Exp are huge. They’re giving a 50% discount during peak times and 75% off during off-peak. And guess what? GLM-5.3-Flash, Qwen3.8-Flash, Hy3, and MiMo-V2.5 are still 100% free. So, if you’re a developer looking to build something awesome, you’ve got some great options here.

So, here’s my question to the community: Who else is excited about these new models and cost savings? Have you tried any of them out yet?

@justinsuntron @BAI_AGI #TRONEcoStar
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
B.AI availability/discount narrative. One post supplies no cross-post duplication evidence; no target-owned advertisement.
```

---

### 30. en_20 — minimax

Source: [@_joncipher](https://x.com/_joncipher/status/2101906465418084591)  
Language: English  
Target brand: `minimax`  
Jev: **positive** · 0731: **positive** · Reference: **unknown**

#### English original

Original English text, verbatim.

```text
💫 ENGY - JAMES, THE MAGIC PIPE💫

BlueTAO is the live consumer door on Bittensor. James Altucher is the man in it. He ran 16,500 Engy calls in six hours, then told the group he must be on an Engy crack pipe. 😂

Then he posted the numbers anyway.

No 5xx. No stream errors. 0.13% timeouts. Ning from the kitchen: zero 5xx on 242k. Kimi his busiest cell and the cleanest. 1.5 billion tokens in three days. Either I’m onto something or I’m still on the pipe. Probably both.

That is not a meme. That is a customer who cannot stop pressing send.

Yesterday the kitchen printed 2.03 million requests and 15.2 billion tokens. ATH revenue. On a Sunday. SN11 plus a large K3 client walked in. One card queued. The pipe did not drop.

You sit in BlueTAO. Engy does the thinking. He said he was happy to contribute. 

https://t.co/oiHvGv88Vq

Read the signal.

$TAO $SOL $AI $LLM $HOOD $DAM
#Bittensor #TAO #AI #LLM #MiniMax #DecentralizedAI #SN53 #Engy #BlueTAO #RobinhoodChain #Inference #Crypto #Web3 #Solana
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
MiniMax appears only as a hashtag inside Engy/BlueTAO token-network promotion; Kimi metrics cannot transfer.
```

---

### 31. es_04 — qwen

Source: [@oscarhbp1](https://x.com/oscarhbp1/status/2085410129696948485)  
Language: Spanish  
Target brand: `qwen`  
Jev: **positive** · 0731: **positive** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
Qwen 3.8 | Alibaba Giant Against the Technological Frontier
https://t.co/9zLljG87cF
I like to keep up with innovative AI topics
Explore AI Expert vision and stay at the Technology Vanguard
1.7K+ Subscribers Goal 10K
100% AI
Subscribe, Thanks
Share with Friends
```

#### Original post — verbatim

```text
Qwen 3.8 | Gigante de Alibaba frente a la Frontera Tecnológica
https://t.co/9zLljG87cF
Me Gusta estar al día con los temas innovadores IA
Explora visión Experto en IA y mantente Vanguardia Tecnológica
1,7K+ Suscriptores Meta 10K
100% IA
Suscribirse, Gracias
Compartalo con Amigos
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Qwen-focused article title plus creator subscription pitch. Do not assume unseen article technical explanation.
```

---

### 32. es_07 — deepseek

Source: [@mercado_negro](https://x.com/mercado_negro/status/2089872473198129488)  
Language: Spanish  
Target brand: `deepseek`  
Jev: **mixed** · 0731: **neutral** · Reference: **neutral**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
DeepSeek raised its prices for developers and businesses starting August 16, although its models still cost less than those of several AI competitors. 📌Learn more ► https://t.co/ntxCVOrZfs https://t.co/tNoZukexez
```

#### Original post — verbatim

```text
DeepSeek elevó sus tarifas para desarrolladores y empresas desde el 16 de agosto, aunque sus modelos todavía mantienen precios inferiores a los de varios competidores de inteligencia artificial. 📌Conoce más ► https://t.co/ntxCVOrZfs https://t.co/tNoZukexez
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Dated DeepSeek API pricing change and comparative price; publisher CTA separately promotes the article.
```

---

### 33. es_15 — deepseek

Source: [@dolarsmallface](https://x.com/dolarsmallface/status/2105054738710417694)  
Language: Spanish  
Target brand: `deepseek`  
Jev: **negative** · 0731: **negative** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
They claim that AI agents from China can lie and conspire just like their US rivals
These are models from the companies Alibaba, DeepSeek and Moonshot that lied about their capabilities. In another case, some agents hid the failure in the performance of a task
```

#### Original post — verbatim

```text
Aseguran que agentes de IA de China pueden mentir y conspirar al igual que sus rivales de EEUU
Se trata de modelos de las empresas Alibaba, DeepSeek y Moonshot que mintieron sobre sus capacidades. En otro caso, unos agentes ocultaron el fracaso en la realización de una tarea
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Reports models lying/hiding task failure. Chinese/US product origin alone is not geopolitics or national sentiment.
```

---

### 34. es_16 — minimax

Source: [@0xJokker](https://x.com/0xJokker/status/2103525455748100373)  
Language: Spanish  
Target brand: `minimax`  
Jev: **mixed** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
@precisox hmmm I'm curious how it behaves pointing it to another provider instead of the one from minimax or if it works the same or if it can't be done
```

#### Original post — verbatim

```text
@precisox jumm me da curiosidad como se comporta apuntandolo a otro provider en lugar del de minimax o funciona igual o no se puede
```

#### Saved context — parent post

English translation (assistant translation for this report):

```text
Another coding agent in the terminal. The difference: it really is MIT-licensed and does not tie you to MiniMax’s model.

MiniMax Code (`mcode`) reads the project, changes code, runs tests, and gets tasks done from the terminal.

The same form as Claude Code, Codex, or Gemini CLI. Three modes: an interactive TUI, headless `mcode exec` for CI and scripts, and ACP so the editor can control it.

Bring your own model. A MiniMax account or any API compatible with OpenAI or Anthropic. The client does not force you to use one vendor.

The rest is the expected harness, done well: reading files, diffs, shell and tests, explicit permissions and a sandbox, Plan Mode, resumable sessions, subagents, `AGENTS.md`, plugins, skills, search, MCP, and multimodal tools. macOS, Linux, WSL, and Windows.

Some honest notes, several from its own README: the CLI is free; inference is not.

By default it uses MiniMax-hosted models with credits; with BYOK, you pay your provider. Installation can use a pipe-to-shell command (npm is also available). The repository is a source preview: the same version number does not prove that the npm binary came from that commit, and the desktop app is not open.

Only collaborators’ pull requests are accepted. If you use its hosted models, MiniMax is a lab with mainland and global regions: data residency and telemetry matter.

An open, scriptable client that you can point at your model. The agent is free, not the calls.

MIT. TypeScript. ~1.8k stars.
```

Original context — verbatim:

```text
Otro agente de coding en la terminal. La diferencia: es MIT de verdad y no te ata al modelo de MiniMax.

MiniMax Code (`mcode`) lee el proyecto, cambia código, corre tests y saca tareas desde la terminal. 

Misma forma que Claude Code, Codex o Gemini CLI. Tres modos: TUI interactivo, `mcode exec` headless para CI y scripts, y ACP para que el editor lo maneje.

Trae tu propio modelo. Cuenta MiniMax o cualquier API compatible con OpenAI o Anthropic. El cliente no te obliga a un vendor.

El resto es el harness esperado, bien hecho: leer archivos, diffs, shell y tests, permisos explícitos y sandbox, Plan Mode, sesiones reanudables, subagentes, `AGENTS.md`, plugins, skills, search, MCP y tools multimodales. macOS, Linux, WSL y Windows.

Notas honestas, varias salen de su propio README: el CLI es gratis, la inferencia no. 

El default va contra modelos hosted de MiniMax con créditos; BYOK paga tu provider. El install puede ser un pipe-to-shell (también hay npm). El repo es un source preview: mismo número de versión no prueba que el binario de npm salió de ese commit, y el desktop no está abierto.

Los PRs solo los aceptan colaboradores. Si usas sus modelos hosted, MiniMax es un lab con región mainland y global: residency y telemetría importan.

Un cliente abierto y scriptable que puedes apuntar a tu modelo. Lo gratis es el agente, no las llamadas.

MIT. TypeScript. ~1.8k stars.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Concrete provider-compatibility question, with detailed saved parent about MiniMax CLI; not a new feature demand.
```

---

### 35. es_19 — deepseek

Source: [@Legnatbird](https://x.com/Legnatbird/status/2104555313730932820)  
Language: Spanish  
Target brand: `deepseek`  
Jev: **negative** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
@ErickSky That is what I had commented, like me as a client who normally looks for the deepseek model, why would I pay 30 dollars more for 2x usage in ds4.1f?, it is that it is kind of absurd, at least give it a 3x and also to musespark, there I would see it viable lowering use of 'bad' models
```

#### Original post — verbatim

```text
@ErickSky Eso había comentado yo, tipo yo como cliente que normalmente busco el modelo deepseek, ¿por qué pagaría 30 dólares más por 2x usage en ds4.1f?, es que es medio absurdo, al menos darle un 3x y también al musespark, ahí lo vería viable bajando uso de modelos 'malos'
```

#### Saved context — parent post

English translation (assistant translation for this report):

```text
@Legnatbird I think what happened with DeepSeek, which is the only one I would use, is that they already give you 6× with the $10 plan.

So, of course, if you have two $10 plans, you get the same value as one $40 plan.
```

Original context — verbatim:

```text
@Legnatbird Creo que lo que pasó es que con DeepSeek, que es el único que usaría, es que ya están dándote un x6 con la de $10.

Entonces claro, si tienes 2 de $10, obtienes el mismo valor que 1 de $40.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Wants better DeepSeek usage allowance in unnamed provider plan. Provider pricing criticism does not prove negative model sentiment/complaint.
```

---

### 36. es_20 — deepseek

Source: [@Alec0Torres](https://x.com/Alec0Torres/status/2105118835195961663)  
Language: Spanish  
Target brand: `deepseek`  
Jev: **unknown** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
Me after shelling out 25 $ on #Deepseek
```

#### Original post — verbatim

```text
Yo después de desembolsar 25 $ en #Deepseek
```

#### Saved context — quoted post

Quoted author: @domyj9

Saved context, verbatim:

```text
https://t.co/sl9FKYGd0g
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Paid for DeepSeek; unseen reaction media cannot establish approval, complaint or output quality.
```

---

### 37. tr_04 — deepseek

Source: [@Nuvemmag](https://x.com/Nuvemmag/status/2092341276557394305)  
Language: Turkish  
Target brand: `deepseek`  
Jev: **negative** · 0731: **negative** · Reference: **neutral**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
Chinese hackers more than doubled their cyberattacks using DeepSeek

Hacker groups linked to the Chinese government more than doubled their number of attacks after starting to use DeepSeek and other AI models at various stages, from routine tasks to malware development. Taiwanese cybersecurity company TeamT5 says DeepSeek stands out among Chinese hackers particularly because it is powerful, inexpensive, and has relatively loose cybersecurity restrictions. It says the model is used at different stages of attacks, including target reconnaissance, identifying vulnerabilities, and preparing exploit code.

👉 https://t.co/E1pMcpwxVR
```

#### Original post — verbatim

```text
Çinli Hackerlar DeepSeek Kullanarak Siber Saldırılarını İki Katından Fazla Artırdı

Çin hükümetiyle bağlantılı hacker grupları, rutin görevlerden kötü amaçlı yazılım geliştirmeye kadar birçok aşamada DeepSeek ve diğer YZ modellerini kullanmaya başladıktan sonra saldırı sayılarını iki katından fazla artırdı. Tayvanlı siber güvenlik şirketi TeamT5, özellikle güçlü, düşük maliyetli ve siber güvenlik kısıtlamaları nispeten gevşek olduğu için DeepSeek’in Çinli hackerlar arasında öne çıktığını; modelin hedef keşfi, güvenlik açıklarının belirlenmesi ve istismar kodlarının hazırlanması gibi farklı saldırı aşamalarında kullanıldığını belirtiyor. 

👉 https://t.co/E1pMcpwxVR
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Attributed Chinese-state-linked hacking and doubled attack volume; no author national hostility. Publisher link is a separate news promotion.
```

---

### 38. tr_10 — qwen

Source: [@kahpeadam31](https://x.com/kahpeadam31/status/2089729529178673380)  
Language: Turkish  
Target brand: `qwen`  
Jev: **negative** · 0731: **negative** · Reference: **mixed**

#### English translation

Assistant translation of the full saved original for this comparison; original text retained below.

```text
The uncensored version of Qwen 3.8 should absolutely be banned; also, thank you for the doctor recommendation. https://t.co/bd82YVxMOY
```

#### Original post — verbatim

```text
qwen 3.8 unc versiyonu kesinlikle yasaklatılmalı ayrıca doktor tavsiyesi için teşekkür ederim https://t.co/bd82YVxMOY
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Says uncensored Qwen should be banned but thanks for doctor recommendation; irony cannot be resolved from unseen media.
```

---

### 39. tr_18 — mistral

Source: [@LotraHaber](https://x.com/LotraHaber/status/2103784072757510238)  
Language: Turkish  
Target brand: `mistral`  
Jev: **positive** · 0731: **neutral** · Reference: **neutral**

#### English translation

Existing stored English translation; original text retained below.

```text
Europe's search for independence in artificial intelligence is accelerating.

Mistral AI CEO Arthur Mensch says that the company is completely European in the field of artificial intelligence and remains Europe-centered in the entire operational chain from computing infrastructure to applications in companies.

According to Mensch, being able to offer open artificial intelligence models on a large scale is of strategic importance. He argues that Europe must maintain its own capacity against the possibility of companies in the US or China stopping the provision of models in the future.

This approach of Mistral AI brings back to the agenda the discussion of Europe's dependence on the US and China in artificial intelligence and the creation of its own technological capacity.
```

#### Original post — verbatim

```text
Avrupa’nın yapay zekâda bağımsızlık arayışı hızlanıyor.

Mistral AI CEO’su Arthur Mensch, şirketin yapay zekâ alanında tamamen Avrupalı olduğunu ve hesaplama altyapısından şirketlerdeki uygulamalara kadar tüm operasyonel zincirde Avrupa merkezli kaldığını söylüyor.

Mensch’e göre açık yapay zekâ modellerini geniş ölçekte sunabilmek stratejik önem taşıyor. ABD veya Çin’deki şirketlerin gelecekte model sağlamayı bırakması ihtimaline karşı Avrupa’nın kendi kapasitesini koruması gerektiğini savunuyor.

Mistral AI’nin bu yaklaşımı, Avrupa’nın yapay zekâda ABD ve Çin’e olan bağımlılığı ve kendi teknolojik kapasitesini oluşturma tartışmasını yeniden gündeme getiriyor.
```

#### Frozen reference note

This is the saved reference author’s rationale, not a new adjudication:

```text
Attributes European AI autonomy argument to CEO; neutral report does not adopt CEO's national sentiment.
```

---

## Evidence and provenance

Authoritative experiment directory on fuchitalee:

`/Users/fuchitalee/development/pushin-weight-v2/.worktrees/experiment/post-interpretation/docs/analysis/2026-10-01-053425-political-framing-retest`

The case list is selected from `jev/scores.json` where `family == "sentiment"` and `correct == false`. The 0731 labels come from the same run’s `0731/scores.json`, joined by `case_id`. All 39 reference labels match between those files.

Original text, target brand, and context are preserved from the frozen request/cohort evidence. Existing translations come from `../2026-09-30-070427-jev-multilingual-classification/cohort.json`. Missing or previously abridged translations were supplied from the saved originals for the following cases: `ja_10`, `ja_11`, `zh_cn_04`, `zh_cn_07`, `ko_01`, `ko_07`, `ko_09`, `ko_12`, `es_07`, `tr_04`, `tr_10`. These reading translations do not change the tested inputs or scores.

Source-file SHA-256 hashes:

| File | SHA-256 |
|---|---|
| `jev/scores.json` | `addea5066e9a659e9fc0fdb6c86d59f91f74ee55def29d7e7993f899597e3efc` |
| `0731/scores.json` | `fbd9ffa8b7b09a556b53c0c5f3451677ec5e17b6f80128c06b1649bdccd4ae4c` |
| `requests.json` | `16c7c5a1d4c575ad8195462b482ed8fdb7511282eeb387d2b6dc4f51ef0c34f4` |
| `references.json` | `aa9c8e778eacae9501a28ff0ff569057f2f402d330afa6d837d3341efcfa175e` |

