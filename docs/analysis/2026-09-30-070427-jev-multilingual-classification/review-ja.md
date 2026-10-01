# Source-only reference review: ja

Stored classifier assignments and Jev results are deliberately absent.

## ja_01 — target deepseek — natural
Post: 2098963821369217086 | @3K1 | other candidates: deepseek
Affiliations: []

諦めるのはまだ早い。：DeepSeek v4.1 Flashを動かしたくてFP4に対応していないA100を、33tok/sから673 tok/sまで持っていって気がつくと公式APIより速くなっていた話｜shi3z https://t.co/pS9xoTe5mM を思い出した

Stored context:
{"stored_quote": "P100を13枚集めたら200GBくらいになってdeepseek v4 flash 0731 も動くし、30万円くらいで組めた。\nなので諦めるのはまだ早い。 https://t.co/QmgNSxqCbY", "quoted_author": "0x71ff", "local_parent": ""}

Stored English translation:
It's too early to give up: reminded of this piece — wanting to run DeepSeek v4.1 Flash, they took an A100 that doesn't support FP4 from 33 tok/s to 673 tok/s, and before they knew it, it was faster than the official API | shi3z https://t.co/pS9xoTe5mM

## ja_02 — target minimax — natural
Post: 2091712099395461388 | @aidoga_lab | other candidates: minimax
Affiliations: []

世界観️：Midjourney
Movie：Capcut (@capcutapp_jp) → MiniMax H3で生成

#capcutcpp

Stored context:
{"stored_quote": "", "quoted_author": "", "local_parent": "MiniMax H3　「SPECIMEN GRID 2」👇 https://t.co/8L8ISP0OHO"}

Stored English translation:
Worldview: Midjourney. Movie: Capcut (@capcutapp_jp) → generated with MiniMax H3 #capcutcpp

## ja_03 — target deepseek — natural
Post: 2102595739474174316 | @connect24h | other candidates: deepseek, mistral, qwen
Affiliations: []

MAGIシステムか！攻撃側まで合議制とは、絶対、攻撃者にもエヴァ好きがいるだろ！笑えないわ。BleepingComputerが伝えたTalosの解析では、WindowsマルウェアClosedQuorumはGemini、DeepSeek、Qwen、Mistralの4系統のAIによる投票で、侵害後の行動を決める設計。MAGIより合議が１つ多い。Geminiの扱いが気になる。どうプロンプトでだましているんだろう？アカウントBANされても再度申請しているのかも。

ついに「AIが攻撃手順を決める」マルウェアが出てきた。

Windowsマルウェア ClosedQuorum。

面白いのは「AIでマルウェアを書いた」ではない。

侵害後の意思決定そのものをLLMに渡している。

使うのは
Gemini / DeepSeek / Qwen / Mistral。
感染端末を偵察
↓
状況を複数LLMへ投入
↓
各モデルが次の行動を投票
↓
多数決で攻撃を実行

選択肢は、
steal
→ LSASS、ブラウザ認証情報、暗号資産Walletを窃取
inject
→ Shellcode生成、Process Hollowing / Early Bird APC Injection
persist
→ 永続化
move
→ 横展開用。ただし解析されたビルドでは未実装
同票ならDeepSeek → Qwen → Mistral → Geminiの順で最終判断。
つまり、

Recon → Decide → Execute → Exfiltrate

の「Decide」を人間からAIへ移した。
ここが怖い。

攻撃者が24時間コンソールに張り付かなくても、侵害後の状況に応じて攻撃チェーンを進められる。
まだ高度なマルウェアではなく、実戦投入も未確認。
API障害、Rate Limit、不正なLLM出力という弱点もある。

それでもこれは重要な転換点。
AIによる攻撃支援から、AIによる攻撃オーケストレーションへ。

SOC/CSIRTが今後相手にするのは、
「速い攻撃者」ではなく、
 人間を待たずに次の手を選ぶ攻撃基盤かもしれない。
https://t.co/cWp2iCfcEg

Stored English translation:
The MAGI system! To have a consensus system even on the attacking side, there are definitely Eva fans among the attackers too! I can't even laugh. According to the Talos analysis reported by BleepingComputer, the Windows malware ClosedQuorum is designed to determine post-compromise actions by voting among four AI lineages: Gemini, DeepSeek, Qwen, and Mistral. It has one more consensus member than MAGI. I'm curious about how Gemini is handled. I wonder how they are deceiving it with prompts? Maybe they are reapplying even after the account is banned.

Finally, malware where "AI decides the attack procedure" has appeared.

Windows malware ClosedQuorum.

The interesting part is not that "malware was written with AI."

It is handing over the post-compromise decision-making itself to LLMs.

What it uses are
Gemini / DeepSeek / Qwen / Mistral.
Reconnaissance of the infected terminal
↓
Input situation into multiple LLMs
↓
Each model votes on the next action
↓
Execute attack by majority vote

The options are:
steal
→ Steal LSASS, browser credentials, cryptocurrency Wallets
inject
→ Shellcode generation, Process Hollowing / Early Bird APC Injection
persist
→ Persistence
move
→ For lateral movement. However, unimplemented in the analyzed build
If there is a tie, the final decision follows the order DeepSeek → Qwen → Mistral → Gemini.
In other words,

Recon → Decide → Execute → Exfiltrate

The "Decide" part has been moved from humans to AI.
This is the scary part.

Even if the attacker isn't glued to the console 24 hours a day, the attack chain can progress according to the post-compromise situation.
It is not yet an advanced malware, and deployment in actual combat is unconfirmed.
There are weaknesses such as API failures, Rate Limits, and invalid LLM outputs.

Still, this is an important turning point.
From AI-assisted attacks to AI-driven attack orchestration.

What SOC/CSIRT will deal with from now on may not be
"fast attackers,"
but an attack infrastructure that chooses the next move without waiting for a human.
https://t.co/cWp2iCfcEg

## ja_04 — target deepseek — natural
Post: 2085522812295643197 | @mt_pb_ai | other candidates: deepseek
Affiliations: []

AIの価格破壊を起こしているDeepSeekに最新モデルが来るか？！

コスパ良く高性能なモデルを使いたい人は注目です。

DeepSeek V4-Proの性能や価格を記した「投資家向け資料とされる画像」がXで注目されています。
ただし、現時点でDeepSeekが公式発表した情報ではありません。

・資料では、V4-Proのコーディング能力はClaudeの旗艦モデルを0.3%下回る水準とされている

・100万Tokenのコンテキストをサポートするとされている

・API価格は海外競合の1/10〜1/100という説明

・投稿中のClaude「Fable 5」と比較した試算

→ 入力は10ドル対0.435ドルで約23分の1、出力は50ドル対0.87ドルで約57分の1。100万入力Tokenと100万出力Tokenを使う例では、60ドル対1.305ドルで約46分の1です。

性能がClaudeの最上位モデルに近く、この価格差が事実なら影響は非常に大きそうです。

一方、資料の真偽、モデル名、ベンチマーク、価格、正式提供時期はいずれも公式発表を待つ必要があります。

Stored context:
{"stored_quote": "‼️Breaking ：疑似DeepSeek V4-Pro正式版能力曝光！！🤯\n\n一份网传的投资人材料显示，DeepSeek V4-Pro性能将跻身全球第一梯队，编程能力仅弱于Claude旗舰模型0.3%，同时支持百万Token上下文，API价格只有海外竞品的1/10至1/100。\n\n如果这里的「Claude旗舰」指Anthropic目前最强的Claude Fable 5，并按照Fable 5各项公开最高成绩回推，V4-Pro可能达到：\n\nTerminal-Bench 2.1：约83.5%\nFable 5为83.8%。\n\nDeepSWE：约69.7%\nFable 5公开测试的pass@1为69.9%。\n\nSWE-bench Pro：约80.1%\nFable 5为80.3%。\n\n价格差距则更加夸张。\n\nClaude Fable 5的API定价为每百万Token输入10美元、输出50美元。\n\n按此计算DeepSeek V4-Pro目前官方价格为输入缓存未命中0.435美元、输出0.87美元。\n\n换算下来：\n输入便宜约23倍\n输出便宜约57倍\n\n假设一次使用100万输入Token和100万输出Token，Fable 5需要60美元，V4-Pro只需要1.305美元，综合便宜约46倍。\n\n甚至缓存命中价格也只有0.003625美元，约为Fable 5的1/276。\n\n所以材料里所谓「海外竞品的1/10至1/100」，至少对比Fable 5并不算吹得特别离谱，甚至还写保守了。\n\n如果这份材料属实，V4-Pro正式版的Coding能力几乎贴着Claude最强模型，价格却只有四五十分之一。\n\n十分期待 @deepseek_ai 尽快发布 V4 Pro GA🔥", "quoted_author": "MaxForAI", "local_parent": ""}

Stored English translation:
Is the latest model coming to DeepSeek, which is causing price disruption in AI?! This is noteworthy for those wanting high-performance models at good cost-performance. An image claimed to be investor materials showing DeepSeek V4-Pro's performance and pricing is drawing attention on X. However, this is not official DeepSeek information. The materials state V4-Pro's coding ability is 0.3% below Claude's flagship model. It is said to support 1M token context. API pricing is described as 1/10 to 1/100 of overseas competitors. A calculation comparing it with Claude 'Fable 5': Input is $10 vs $0.435, about 1/23; Output is $50 vs $0.87, about 1/57. For 1M input and 1M output tokens, it's $60 vs $1.305, about 1/46. If performance is close to Claude's top model and this price gap is real, the impact would be very large. However, authenticity, model name, benchmarks, pricing, and official launch timing all await official confirmation.

## ja_05 — target minimax — natural
Post: 2089442141751902272 | @luche_whitewing | other candidates: minimax
Affiliations: []

早朝の美少女🏝️
朝の光が、水面に小さな道を描く。
玲奈は迷いをそっと置いて、
透きとおる青の中へ——。
思いきって踏み出した先には、
昨日まで知らなかった景色が
待っているのかもしれません。
CapCut @capcutapp_jp
MiniMax H3を使って制作しています。
#capcutcpp #MiniMaxH3 
忙しい一日の途中で、 少しだけ心を休めていってください。🪽

Stored context:
{"stored_quote": "波が昨日の足跡を消して、\n朝が新しい物語を描きはじめる——。\n玲奈が見つけた小さな貝殻は、\n海から届いた今日最初の贈りもの。\n潮風に髪とパレオを遊ばせ、\n水平線へ静かに深呼吸。\n立ち止まることは、\n前へ進むための優しい準備なのかもしれません。\n朝の海を歩く25秒の小さな物語。\n波音とともに、心ほどけるひとときをどうぞ\n今日も穏やかな一日になりますように。\nCapCut　@capcutapp_jp のSeedance2.5で生成・制作しました。@capcutapp #capcutcp", "quoted_author": "luche_whitewing", "local_parent": ""}

## ja_06 — target minimax — natural
Post: 2089299406583726236 | @sidodtv | other candidates: minimax
Affiliations: []

MiniMax-H3による犬と猫のボクシングアニメ

動きが速いブレがきれいに出ませんね https://t.co/56kaRdlydl

## ja_07 — target minimax — natural
Post: 2090270568532828380 | @kik0ai1jikake | other candidates: minimax
Affiliations: []

MiniMax H3とSeedance2の
モーショングラフィックを比較してみた

どちらもCapcutで生成 コストは
左 MiniMax H3 10秒 768p『 210 』
右 Seedance2 480p『 110 』720pだと『 240 』
確かにH3の方が最終的にコスパ良くなる印象

プロンプトはリプ欄

生成結果はH3の方が前評判通りスッキリ
とまとまっている感じはしますが

seedanceも悪くないので
適材適所な感じかなと

色々選択肢が広がるのは良いですね
試していこうと思いました

@capcutapp_jp #capcut #capcutcpp

## ja_08 — target minimax — natural
Post: 2090439924332032347 | @javawock7618 | other candidates: minimax
Affiliations: []

MiniMax-H3 FaceRefineワークフローを更新しました。

使用モデルをRef2VAに変更し、顔参照で修正精度が少し上がりました。
レンジモードを追加しました。0フレームから指定フレームまでの範囲だけを修正し、残りを結合して出力します。前半の引き画角で顔が潰れているときに使えると思います。

## ja_09 — target minimax — natural
Post: 2087298764583415883 | @__su888 | other candidates: minimax
Affiliations: []

antirezによるMiniMax-H3のApple Siliconネイティブ推論実装。int8 MLPとQKV量子化で50層19遷移の512x512 denoiseを36.30秒から19.18秒へ短縮し、ピークテンソルも36.4→25.9GiBに削減 / antirez/h3.c: MiniMax H3 inference engine for Mac computers
https://t.co/1SGffbmLJr

Stored English translation:
antirez's MiniMax-H3 Apple Silicon native inference implementation. With int8 MLP and QKV quantization, 50-layer 19-iteration 512x512 denoise shortened from 36.30s to 19.18s, peak tensor also reduced from 36.4→25.9GiB / antirez/h3.c: MiniMax H3 inference engine for Mac computers
https://t.co/1SGffbmLJr

## ja_10 — target minimax — natural
Post: 2087557406473744443 | @To_Vten_ozi | other candidates: minimax
Affiliations: []

Minimax H3は0.4～0.6などサイズ小さく生成して、SeedVR2でアップスケールするのが良さそう。
アップスケールの方が時間かかったけどね😆 https://t.co/FoHPjl1upn

## ja_11 — target deepseek — natural
Post: 2097846114489962944 | @amano76_SEO | other candidates: deepseek, minimax, moonshot_kimi, stepfun
Affiliations: []

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

Stored English translation:
[Latest AI news | 2026.09.10] Three highlights from generative AI news announced and reported in the US. (1) OpenAI announced 'AI solved an unsolved math problem' — ~10,000 AI agents ran simultaneously and produced a solution to the Navier–Stokes millennium prize problem, using an unreleased internal model claimed to outperform GPT-6 Astra; solution reached in ~88 hours, plus 17 more hours for Lean formalization and verification by GPT-6 Astra. Caveat: OpenAI's own claim; not yet certified by the math community or the Clay Mathematics Institute. (2) Meta launches personal AI agent 'Muse' in the US — browses, sends email, fills forms, books travel, buys products, negotiates prices, continues after app closes; approval required for critical actions; iOS/Android/Web in US and via WhatsApp. Meta claims dedicated virtual environment and monitor agent for safety, and no chat data to ad systems—Meta's own claim. (3) US government warns of 'large-scale model distillation' by Chinese AI firms — NSA, CISA, FBI joint advisory naming DeepSeek, Alibaba, Moonshot AI, MiniMax, StepFun, and Zhipu AI for obtaining large volumes of outputs from Claude, GPT, Gemini, Grok etc. Distillation itself is a standard technique; the US government objects to alleged evasion of TOS/regional limits/detection using multiple APIs and proxy services. This is a US government agency finding; China denies it as 'groundless accusations.' The takeaway: generative AI is moving from answering questions to doing research, operating external services, and performing real work—and verifying AI results, granting agent permissions, and protecting model IP are now more important than ever. #生成AI #AIニュース #OpenAI #MetaAI #AIエージェント

## ja_12 — target minimax — natural
Post: 2086784629701521832 | @toMion818 | other candidates: minimax
Affiliations: []

🚀【 新MV公開 】🚀

toMion - Space For Both Of Us
(Official Music Video)

ミニアルバム表題曲のMVをYouTubeにアップしました！

映像はGoogle Colabを使って、今話題の動画生成AI「MiniMax-H3」で制作しています🎥✨

#toMion #MiniMaxH3 #動画生成AI #AIMV #AIアニメ
https://t.co/uObLxv33oE

Stored English translation:
🚀【 New MV Release 】🚀

toMion - Space For Both Of Us
(Official Music Video)

Uploaded the MV for the mini-album title track to YouTube!

The video was made using Google Colab and the trending video generation AI "MiniMax-H3" 🎥✨

#toMion #MiniMaxH3 #VideoGenerationAI #AIMV #AIAnime
https://t.co/uObLxv33oE

## ja_13 — target llama — coverage
Post: 2103244089747554662 | @ai_hakase_ | other candidates: llama
Affiliations: []

【llama.cpp運用時のトラブルシューティング】スラッシュ無限ループの原因と解決策について💡

ローカル環境でllama.cppやllama-serverを使っていて、長大なコンテキストやマルチモーダル入力を処理していると、モデルの出力がスラッシュ（`//...`）の無限ループになってしまう不具合が起きることがあるそうです！😱

これ、本当に困っちゃいますよね…！主な原因としては、GPUやCPUの熱や電圧などのハードウェアの不安定さや、WindowsのCUDA環境で起こるVRAMリーク、さらにllama.cpp側のビルド不整合などが挙げられるとのことです。

もし同じ現象に出くわしてしまったら、ホストマシンのリブートによるVRAMのクリーンアップや、llama.cppの最新版へのリビルドを試してみると解決することが多いみたいですよ！✨ 困ったときはぜひチェックしてみてくださいね。

#llama.cpp #ローカルLLM

Stored English translation:
【Troubleshooting during llama.cpp operation】About the cause and solution of slash infinite loops💡

It seems that when using llama.cpp or llama-server in a local environment and processing lengthy contexts or multimodal inputs, a bug may occur where the model's output becomes an infinite loop of slashes (`//...`)!😱

This is truly troublesome, isn't it...! As for the primary causes, it is said that hardware instability such as GPU or CPU heat or voltage, VRAM leaks that occur in Windows CUDA environments, and furthermore, build inconsistencies on the llama.cpp side can be cited.

If you happen to encounter the same phenomenon, it seems that trying a cleanup of VRAM by rebooting the host machine or rebuilding to the latest version of llama.cpp often resolves it!✨ Please be sure to check this out when you are in trouble.

#llama.cpp #LocalLLM

## ja_14 — target minimax — coverage
Post: 2102422720931844486 | @KimiAI_Studio | other candidates: minimax, moonshot_kimi
Affiliations: []

【速報】
Kimi K3を爆速化させる実行基盤「MiniMax Code CLI」、MITで完全OSS化！！

https://t.co/36TIyEhQWP

モデル単体ではなく外側の「実行枠（ハーネス）」こそが真の資産！ツール呼び出しや権限チェックの全経路を透明化した高効率コーディングエージェントが話題に

・Kimi K3との連携で30タスク中23件成功（合格率76.7%／完了中央値4分33秒）を記録 
・思考からコード差分出力までのレイテンシが短く、消費トークンを大幅に抑える軽量設計 
・自社モデルだけでなくOpenAIやAnthropic互換APIにも対応！MITライセンスで即セルフホスト可能

最新モデルが数週間単位で目まぐるしく入れ替わる時代だからこそ、「モデル自体は差し替え可能な借り物として扱い、権限管理やファイル操作を司るハーネス側を資産として手元に持つ」という視点はめちゃくちゃ本質的。
内部ロジックがブラックボックスなクローズドツールに依存せず、ツール呼び出しや差分生成の経路が読めるOSSハーネスを選ぶのは、長期的な開発環境の安全性・投資対効果の面でも極めて堅実な選択です。

Stored English translation:
[Breaking News]
"MiniMax Code CLI," the execution framework that makes Kimi K3 lightning fast, is now fully OSS under MIT!!

https://t.co/36TIyEhQWP

Not the model alone, but the outer "execution framework (harness)" is the true asset! A high-efficiency coding agent that has made all paths for tool calling and permission checks transparent is becoming a hot topic.

・Recorded 23 successes out of 30 tasks (pass rate 76.7% / median completion 4 min 33 sec) in coordination with Kimi K3
・Lightweight design with short latency from thinking to code diff output, significantly suppressing token consumption
・Supports not only in-house models but also OpenAI and Anthropic compatible APIs! Immediate self-hosting possible with MIT license

Precisely because we are in an era where the latest models are replaced dizzyingly on a scale of weeks, the perspective of "treating the model itself as a replaceable borrowed item and keeping the harness side that governs permission management and file operations as an asset on hand" is incredibly essential.
Choosing an OSS harness where the paths for tool calling and diff generation can be read, rather than depending on closed tools whose internal logic is a black box, is an extremely solid choice in terms of long-term development environment safety and return on investment.

## ja_15 — target sakana_ai — coverage
Post: 2104928895627833438 | @SakanaAILabs | other candidates: sakana_ai
Affiliations: [{"role": "official", "brand_id": "sakana_ai", "reviewed": true}]

【Account Executive (GTM) 立ち上げメンバー募集】

https://t.co/8VzHB7sl30

Sakana Marlin、Namazu、FuguをはじめとするSakana AIプロダクトを、大企業を中心とした顧客に広げていきます。日本のAI企業が世界で勝つための営業の型をゼロから設計していただきます。

求めるのはエンタープライズ 営業を一気通貫で回してきた経験、エンジニアやリサーチャーと対等に話せる技術理解、そして日本語と英語の両方で市場を切り拓けることなどです。

研究・プロダクト開発拠点と同じ場所から、日本発のAIを世界に届ける営業組織を立ち上げます。この立ち上げに関わりたい方、ぜひご応募ください🐡

Stored English translation:
【Account Executive (GTM) Launch Members Wanted】

https://t.co/8VzHB7sl30

We will expand Sakana AI products, including Sakana Marlin, Namazu, and Fugu, to customers centered on large enterprises. You will design from zero the sales model for a Japanese AI company to win globally.

What we seek is experience having handled enterprise sales end-to-end, technical understanding to speak as equals with engineers and researchers, and the ability to open the market in both Japanese and English, among other things.

From the same location as the research and product development base, we will launch a sales organization to deliver AI from Japan to the world. If you want to be involved in this launch, please apply 🐡

## ja_16 — target mistral — coverage
Post: 2105142699661652363 | @iwashi86 | other candidates: mistral
Affiliations: []

“両国とも、ビッグテックを輩出できてはいないし、フロンティアラボも存在しない（厳密に言えばMistral社はある、とはいえフロンティアラボとは言えないだろう）。”

Mixtral が出た時点では、MoEのオープンモデルの先駆けだった記憶だけど、Mistral社その後はそこまでfeatureされなくなってしまった。（LLMのスクラッチ開発は減速している情報も以前見た気がする）

米国・中国が抜けているので、欧州側の活動として個人的には結構応援している

https://t.co/1eIjvKLpNH

Stored English translation:
“Neither country has been able to produce Big Tech, and frontier labs also do not exist (strictly speaking Mistral exists, although it probably cannot be called a frontier lab).”

At the time Mixtral came out, I remember it being a pioneer in MoE open models, but since then Mistral has not become featured to that extent. (I feel like I saw information before that scratch development of LLMs is slowing down)

Since the US and China are ahead, as an activity on the European side, I am personally supporting them quite a bit

https://t.co/1eIjvKLpNH

## ja_17 — target qwen — coverage
Post: 2104489492614942827 | @HAI_h_jp | other candidates: glm, qwen
Affiliations: []

GLM・Qwen・Krea を定額で使える「HAI Go Uncensored」をリリースしました

月額 ¥89,800（税込）の HAI Go Uncensored をご紹介します。GLM・Qwen・Krea の Uncensored モデルが定額対象で、画像は請求期間ごとに50枚分を含みます。利用枠と既存プランからの切替条件をご案内します。 https://t.co/riSS4QBn9U

Stored English translation:
We have released "HAI Go Uncensored" where you can use GLM, Qwen, and Krea for a fixed price

Introducing HAI Go Uncensored at ¥89,800 per month (tax included). Uncensored models of GLM, Qwen, and Krea are subject to the fixed price, and images include 50 copies per billing period. We provide information on the usage quota and switching conditions from existing plans. https://t.co/riSS4QBn9U

## ja_18 — target minimax — coverage
Post: 2103649257026904529 | @HuurainoMoutoku | other candidates: minimax
Affiliations: []

#MiniMaxH3 #SeaArt #SeaArtH3AppChallenge
無料の日にはデイリーがないのがアレですよね
それに、無料も「先着順」なので、結局一回も無料で使えませんでした

日本語訳のアプリ名が間違っていて草：MiniMax H3 専用アプリチャレンジ：MiniMax H3 シーンクリエーター(2026年9月24日[木曜日]分) https://t.co/fEqUlYNiLp

Stored context:
{"stored_quote": "Share Your MiniMax H3 Creations and Win a Share of $400 in Amazon Gift Cards\n\nThe MiniMax H3 × SeaArt App & Play Challenge has produced its first batch of outstanding apps!\n\nThis week’s featured apps are now available for a limited-time free trial on SeaArt. Create your own personalized results and enter the giveaway!\n\nHow to Participate:\n1.Visit the event landing page and try this week’s featured MiniMax H3 apps;\n2.Generate an image or video;\n3.Quote this post and attach your generated result;\n4.Add the event hashtags:\n#MiniMaxH3 #SeaArt #SeaArtH3AppChallenge\n\nEvent Period: September 2–28, 2026\n\nLimited Free Trial Dates: September 4, September 11, September 18, and September 25", "quoted_author": "SeaArt_Ai", "local_parent": ""}

Stored English translation:
#MiniMaxH3 #SeaArt #SeaArtH3AppChallenge
The fact that there are no dailies on free days is just "that," isn't it
Besides, free is also "first-come, first-served," so in the end, I couldn't use it for free once

The Japanese translation of the app name is wrong, lol: MiniMax H3 Dedicated App Challenge: MiniMax H3 Scene Creator (September 24, 2026 [Thursday] portion) https://t.co/fEqUlYNiLp

## ja_19 — target moonshot_kimi — coverage
Post: 2102626239794356686 | @xRINGx | other candidates: moonshot_kimi
Affiliations: []

毎度、他国の技術使わないと、中国だけでは何も確立できないという話。
コピーや買収、蒸留、窃取、盗用などの常套手段。

この問題のGrokのまとめ↓

『中国AIのMoonshot(Kimi)とDeepSeekが、AnthropicのClaudeを無断で使っていた件。

中国ではClaudeが使えないため、シンガポールや日本の偽アカウントを数千個作成。ユーザーの質問を黙ってClaudeに転送し、返ってきた回答を自社の回答として提示。推論プロセスまで抽出して自社モデルの学習に使っていた。 

5〜7月だけでMoonshotが2300万回以上、DeepSeekも7月の14日間で1200万回以上。ユーザーはKimiやDeepSeekを使っていると思っていたが、実際はAnthropicのサーバーにデータが流れていた。

Anthropic側は「Claudeの技術そのものを盗んだ」のではなく、出力を大量に集めて自社モデルを強化する「蒸留」だと主張。中国側は公式に認めていない』

Stored context:
{"stored_quote": "中国当局、KimiやDeepSeekを調査　\n米AIに機密情報転送 - 日本経済新聞 https://t.co/Ypajc2IMUl", "quoted_author": "xRINGx", "local_parent": ""}

Stored English translation:
Every time, the story is that without using other countries' technology, China alone cannot establish anything.
Common tactics such as copying, acquisitions, distillation, theft, and plagiarism.

Grok's summary of this issue ↓

"The matter where China AI's Moonshot (Kimi) and DeepSeek were using Anthropic's Claude without permission.

Since Claude cannot be used in China, they created thousands of fake accounts in Singapore and Japan. They silently forwarded users' questions to Claude and presented the returned answers as their own answers. They were even extracting the reasoning process and using it for the training of their own models.

Between May and July alone, Moonshot did it over 23 million times, and DeepSeek also did it over 12 million times in the 14 days of July. Users thought they were using Kimi or DeepSeek, but in reality, data was flowing to Anthropic's servers.

The Anthropic side claims that they did not 'steal the Claude technology itself,' but that it was 'distillation,' collecting outputs in large quantities to strengthen their own models. The Chinese side has not officially admitted it."

## ja_20 — target deepseek — coverage
Post: 2102656351302541457 | @mikoto2000 | other candidates: deepseek
Affiliations: []

DGX Spark x2 と DeepSeek V4 Flash Vision Exp って、何並列まで良い感じで行けるって話でしたっけ？

Stored English translation:
Regarding DGX Spark x2 and DeepSeek V4 Flash Vision Exp, up to how many parallels was it said they could go with a good feel?
