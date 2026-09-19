# U20 fresh five-post translation-error reproduction

**Snapshot:** September 10, 2026 local evaluation database snapshot  
**Run:** September 17, 2026; current `f8df295` translation prompts, raw v12 / opt-in line v13  
**Scope:** five purposively selected real Japanese posts; three explicit model/tool-versus-character/person cases and two standalone-heading cases. This is a reproduction check, not an accuracy, prevalence, or model-selection claim.

## Result

All ten provider responses returned: five English and five Chinese translations, with zero provider errors. The serial run took **67.118 seconds** and reported **$0.00075378**. Native copies were exact for all five Japanese source fields, and all ten non-native outputs retained the source line count.

One material failure reproduced: **F01 Chinese is a byte-for-byte echo of the whole Japanese source**. The deterministic echo validator accepted that response because its Chinese-target guard rejects unchanged Latin-heavy text without CJK characters, but does not reject an unchanged Japanese source containing CJK characters. This is further evidence for the untranslated-text family of failures.

The two direct heading probes did not reproduce that exact symptom: F04 and F05 translated their standalone headings in both target languages and passed all four frozen checks. The three role cases also did not show model/tool-to-person-or-character role confusion in their usable outputs. F01 Chinese is not a role-translation pass because it did not translate at all. The newer role cases are more explicit than the earlier elliptical MiniMax/Phoebes sentence, so this narrow result neither erases the prior failure nor measures its rate.

The harness now additionally accepts frozen diagnostic cohorts of one to ten posts; its existing 45-post cohort remains supported. No runtime translation code, translation prompt, provider configuration, database row, classifier behavior, or production setting changed for this run. Twelve harness tests passed. No new human review was requested; the U20 quality gate remains open.

## Provenance and limits

- Source contract: [fresh selection JSON](../../.context/u20/five-fresh-selection-20260917/selected.json). It records the read-only database query, prior-45 and two original-failure exclusions, selection rationale, and expected checks before inference.
- Run evidence: `.context/u20/five-fresh-probe-20260917-124000/review-inputs.json`, `mechanical-evidence.json`, `independent-review.json`, and `arms/0731/result.json`.
- The source database was `pushinweight_u18_eval`, queried with `default_transaction_read_only=on` and a 15-second statement timeout. The selected posts are five distinct authors, are verbatim DB rows, and are disjoint from the earlier 45-post contract.
- The independent review is a targeted semantic reading of these ten outputs. It is not human gold, an overall translation score, or an estimate of production quality.

## Primary and independent findings

| Case | Intended diagnostic | Primary/mechanical finding | Independent finding |
| --- | --- | --- | --- |
| F01 | model/tool versus fictional character | EN translated; ZH was a complete Japanese echo, although line and URL checks passed | EN retains the role and causal relation; ZH is not a translation and cannot count as a role pass |
| F02 | model/tool, characters, and a depicted person | both target outputs available; line count preserved | no entity-role confusion observed |
| F03 | models/tools, generated character image, and human approver | both target outputs available; line count and URL counts preserved | no tool/human role reassignment observed |
| F04 | short idiomatic heading plus mixed brands | both headings translated; all four frozen checks passed | heading translated and brand/task mappings stay distinct |
| F05 | report title and numbered headings | both title and subheadings translated; all four frozen checks passed | title and all numbered headings translated; no role confusion observed |

## Full verbatim sources

The exact returned EN/ZH texts are in the machine-readable sibling JSON, including line breaks, URLs, and emojis. The following source blocks are verbatim database text; expected checks are the pre-inference checks from the frozen selection contract.

### F01 — `2097915971260600809` (`@mu_sette`)

```text
MiniMax H3で気に入る絵が出なかったのでLoRA作った（入力に存在しないキャラクターを召喚するテスト） https://t.co/yhgZtVRNNQ
```

Checks: MiniMax H3 and LoRA remain tools/adaptation; キャラクター remains an absent fictional input/target; retain the causal relation. The figurative force of 召喚する has no forced gold.

### F02 — `2097551327261847562` (`@ai_hakase_`)

```text
【Minimax H3 ref2vaのポーズ転写でキャラブリーディングを防ぐ方法】
動画生成AI「Minimax H3」のref2va機能を使っていると、特定キャラのポーズを別のキャラに適用した時に外見が混ざり合っちゃう「ブリーディング」現象が起きて困ること、ありませんか？💦

実はこれ、キャラクターのアイデンティティ信号とポーズのジオメトリ信号が同じ領域で競合しちゃうのが原因なんです！
解決策として以下の4つのアプローチがめちゃくちゃ効果的ですよ〜！✨

1. 深度マップ（Depth Map）の活用
深度情報だけを条件付けにすることで、キャラ同士の融合を完全にストップ！ただ、細かい表情やディテールが少し失われちゃうトレードオフがあるので注意です！

2. 棒人間（スケルトン）によるプロンプト制御
色分けされた棒人間をポーズ参照にして、「この位置にあの人物を配置してね！」ってプロンプトで指示する方法です！外見の混濁を防ぎやすくなりますよ〜。たまに棒人間の色に染まっちゃうエラーも起きますが、再生成でサクッと回避できます！

3. プロンプト・メタデータのチャンク削減
長すぎる定義ブロックやメタデータをあえて省略することで、モデルの自律的な推論をうまく引き出せるんですって！プロンプトをシンプルにするのがコツですね！

4. 外部ツールを使ったマルチステップワークフロー
一度に全部やろうとせず、「Krea2」や「Gemini」などの外部ツールでポーズ付きのキャラクター画像を事前に作成し、それをH3に入力するという方法です！元からポーズが適用された画像を使うので、ブリーディングを根本から完全に防げます！NSFWなコンテンツの処理にも安定して使えるので本当におすすめです！

アイデンティティをしっかり保持しつつ、狙い通りのポーズをバッチリ再現していきましょう！🚀

#MinimaxH3 #動画生成AI
```

Checks: MiniMax H3/ref2va, Krea2, and Gemini remain model/features/tools; the two characters remain distinct fictional characters; 人物 is a depicted person; preserve the stated mechanism and tradeoff.

### F03 — `2096805599313006940` (`@hiroshika5555`)

```text
💰費用（https://t.co/HHVb5DxyB8経由）
・キャラシート&止め絵：GPT Image 2 → 1枚 約2〜14円
・動画15秒：MiniMax H3 Max Turbo（480P）→ 約15円 ※75%オフセール中
・BGM 15秒：Stable Audio 2.5 → 約8円
・BGM合成＆480P→1080p（1944×1080）アップスケール：ffmpeg → 無料
完成テイクだけなら合計 約26円
ボツ案・試行錯誤ぜんぶ込みでも 約105円
🛠️進行はClaude Codeに一任
プロンプト設計→見積もり→生成→フレーム分解して検品→BGM合成まで自動。人間はOK出しだけ
動画生成でキャラの顔が崩れる問題は「始点画像の顔をキャラシートで固定してから動画化」で解決しました
#AIart #AIvideo #生成AI
```

Checks: retain the listed tool/model-to-workflow roles, character imagery versus human approver, each numeric value, and the face-repair causal claim.

### F04 — `2094096917068468232` (`@shioyakidev`)

```text
AIの使い分け 僕はこうしてる
ChatGPT→普段の会話、知らない分野についての質問
Gemini→Antigravityでの開発、中程度のデータの高精度の分析・生成
DeepSeek→大量のデータの分析・生成
Claude→高度な開発

これ以外にいい方法あれば教えてください！
```

Checks: translate the opening heading; retain all four brand/task mappings and Antigravity context; preserve informal first-person register without forced wording.

### F05 — `2096986728385118513` (`@JPAITrend`)

```text
AIモデル・サービス日報｜9/7

① GPT-6 Astra、利用枠の消費を改善
Tibo氏によると、一部の高消費ケースでは、消費量が従来の約1/3〜1/4に。品質は変わらないとのこと。API料金の値下げとは別です。

② Gemini、画像で学ぶ新機能
TestingCatalogによると、Students画面に「Immersive View」が登場。画像の気になる部分をクリックして、詳しく学べる仕組みです。公開範囲や日本での利用可否は未確認。

③ GLM 5.3 Flash、API半額期間の終了に注意
OpenRouterのZai経由では、100万トークンあたり入力$0.075／出力$0.25。
割引期限は日本時間9月10日01:00。提供元によって料金は異なります。
```

Checks: translate the title and numbered headings; keep each named service/context distinct, all numerical claims, and the stated availability/price uncertainty.

## Interpretation

The complete F01 Chinese echo confirms that successful transport, native copying, line preservation, URL preservation, and the existing exact-echo validator do not prove translated prose. It does not establish how frequently the symptom occurs. Conversely, the 4/4 frozen-check result for F04 and F05 is limited to these two clearer heading examples, and the role result is limited to these three explicit cases. The correct operational conclusion is to retain the existing open quality gate and use this run as a narrow, durable reproduction exhibit rather than treating it as a prompt-change or release decision.
