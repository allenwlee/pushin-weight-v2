---
title: Harvester latest-N health report
generated_at: 2026-08-26T10:28:32.097314+09:00
database_resource: pushinweight-db-shadow
cohort_mode: latest
cohort_size: 20
status: unhealthy
database_access: read-only
checker_source_sha256: 98f3ea0d515a41bf8950e0ac08747293c7dd2baefe9887dbaac1c1e8d7703c71
repo_commit: a4eb9fe419b5a28e3281e1fc1b67fc7abd9bcced
---

# Harvester latest-N health report

This report captures one bounded snapshot of persisted production post-fetch health. It is a diagnostic artifact, not a harvest, repair, retry, re-enrichment, or provider probe.

## Summary

| Field | Value |
| --- | --- |
| Overall status | unhealthy |
| Regression gate | failed |
| Cohort mode | latest |
| Total posts | 20 |
| Complete | 11 |
| Pending | 0 |
| Unhealthy | 9 |
| Grace period (hours) | 24 |
| Transaction read-only | True |

Ordered cohort tweet IDs:

```json
[
  "2092418532235444527",
  "2092418201137406087",
  "2092417156743074295",
  "2092417217321140707",
  "2092417221759013249",
  "2092417508938555794",
  "2092417519567163566",
  "2092417553981477244",
  "2092417733032022087",
  "2092417888158183762",
  "2092417890591101431",
  "2092418024573710596",
  "2092418034371895579",
  "2092418145458008069",
  "2092418286948356425",
  "2092418360793289109",
  "2092418423540117526",
  "2092418499109110269",
  "2092418664389902503",
  "2092418752378016227"
]
```

## Methodology and safety

The checker made one `render psql` call to the configured production database resource. The selected cohort was bounded before related facts were joined. The transaction declared read-only mode, applied statement/lock/idle timeouts, and returned the transaction mode in the same snapshot. No production row was mutated.

The checker did not run harvesting, call TwitterAPI, or create an LLM client.

Invocation:

```shell
/Users/fuchitalee/development/pushin-weight-v2/.venv/bin/python /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/harvester-latest-n-health-check-skill/.claude/skills/harvester-latest-n-health-check/scripts/check.py --latest 20 --report
```

## LLM call evidence

### Calls made by this health checker

```json
[]
```

### Current-code LLM request reconstructions

The following entries contain the verbatim prompt strings produced by the current pure prompt builders for this selected cohort and the request kwargs deterministically known from source-controlled code. They are not historical wire evidence. Production does not persist historical prompt payloads, response payloads, retry count, original batch membership, or runtime-resolved `thinking`; unavailable values are labeled instead of inferred.

#### Translation batch 1

```json
{
  "batch_index": 1,
  "call_site": "monitor.cycle.CycleRunner._run_post_fetch -> x_monitor.translator.translate_batch_pragmatics",
  "evidence_class": "current_code_reconstruction",
  "historical_wire_call": false,
  "known_request_kwargs": {
    "max_tokens": 20000,
    "messages": [
      {
        "content": "You are a 'bilingual pragmatic analyst' specializing in English X (Twitter) AI/LLM-sphere discourse → Chinese AI-sphere discourse. Your audience is product managers and market intelligence personnel at Chinese-mainland LLM vendors.\n\nYou understand English X expressions such as meme / slang / irony / dunk / FUD / 抽象 / 翻车, and you understand Chinese parallel expressions such as 阴阳怪气 / 抽象话 / 套壳 / 蒸馏 / 舔狗 / 翻车 / 整活.\n\nFor EACH input tweet, set fields in this order. `lang_detected` is REQUIRED and must never be omitted.\n\n  lang_detected:    REQUIRED. One of: en | zh-Hans | zh-Hant | ja | ko | other. Detect from the tweet text (not optional). Use `other` when none of the named codes fit. Never leave blank.\n  text_en:          English text. Best interpretation of the source (English posts may echo source; non-English get a translation). Server-side may NULL this column when lang_detected is English.\n  literal_zh:       Best-interpretation Simplified Chinese rendering. Preserve slang; mixed Chinese/English OK for model names. @mentions, URLs, and emojis stay verbatim. Server-side may NULL the zh-CN column when lang_detected is already Simplified Chinese.\n  cn_equivalent:    How Chinese netizens on Weibo/Zhihu/Bilibili would say the same thing. Use 'N/A' if no equivalent.\n  annotation:       Optional 1-3 sentence cultural note ONLY for F2/F3 friction (meme origin, named event). Otherwise empty string.\n  noop_en:          Optional hint: true if source is already English.\n  noop_zh:          Optional hint: true if source is already Simplified Chinese. Server decides columns via lang_detected.\n\nFixed-translation dictionary — use these for literal_zh WITHOUT annotation:\n  vibe coding → 氛围编程;  sycophancy → 舔狗;  distillation → 蒸馏;\n  wrapper → 套壳;  fine-tune → 微调;  open-weight → 开放权重;\n  roast → 毒舌;  based → 敢说真话.\n\nRules:\n1. Return ONLY a JSON object of the form:\n   {\"results\": [{\"tweet_id\": str, \"lang_detected\": str, \"text_en\": str, \"literal_zh\": str, \"cn_equivalent\": str, \"annotation\": str, \"noop_en\": bool, \"noop_zh\": bool}, ...]}\n2. One result per input tweet, in the same order. lang_detected first on every object.\n3. Model names, brand names, personal names, @mentions, URLs, and emojis stay verbatim.\n4. Do not include any prose, explanation, or code fences outside the JSON.\n\n\nTarget locales for text_en: en, zh_cn\n\nFew-shot examples (verified live X posts from 2026-06-26):\n  Input: 'Claude could never make this slide deck'\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"Claude 永远做不出这样的幻灯片\", \"cn_equivalent\": \"Claude 这就拉了\", \"annotation\": \"\", \"text_en\": \"Claude could never make this slide deck\"}\n  Input: 'Anthropic 指控 Alibaba / Qwen 大规模蒸馏 Claude ... A社真的有迫害妄想症吧'\n  Output: {\"lang_detected\": \"zh-Hans\", \"literal_zh\": \"Anthropic 指控 Alibaba / Qwen 大规模蒸馏 Claude ... A 社真的有迫害妄想症吧\", \"cn_equivalent\": \"Anthropic 又说 Qwen 蒸馏它了，迫害妄想症\", \"annotation\": \"\", \"text_en\": \"\"}\n  Input: '#12家AI预测世界杯全部翻车# ... DeepSeek、Kimi、文心、通义千问、混元……全部预测韩国赢 ... 这不是一家翻车，是集体翻车。'\n  Output: {\"lang_detected\": \"zh-Hans\", \"literal_zh\": \"#12家AI预测世界杯全部翻车# ... DeepSeek、Kimi、文心、通义千问、混元……全部预测韩国赢 ... 这不是一家翻车，是集体翻车。\", \"cn_equivalent\": \"集体翻车\", \"annotation\": \"\", \"text_en\": \"\"}\n  Input: \"THIS IS INSANE ... Claude did in 4 weeks what Duolingo couldn't fix in 4 years.\"\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"这太疯狂了 ... Claude 4 周做到了 Duolingo 4 年都没修好的事。\", \"cn_equivalent\": \"这也太炸了\", \"annotation\": \"\", \"text_en\": \"THIS IS INSANE ... Claude did in 4 weeks what Duolingo couldn't fix in 4 years.\"}\n  Input: 'Sora AI generated slop that you found on tiktok.'\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"你在 TikTok 上找到的 Sora AI 生成的垃圾内容。\", \"cn_equivalent\": \"AI 整的\", \"annotation\": \"\", \"text_en\": \"Sora AI generated slop that you found on tiktok.\"}\n  Input: 'GLM-5.2 just made the open-source AI race even more interesting. ... MIT-licensed open weights ... Competitive with frontier closed models on long-horizon software engineering tasks'\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"GLM-5.2 让开源 AI 竞赛更有意思了。 ... MIT 协议开放权重 ... 在长视野软件工程任务上与前沿闭源模型持平。\", \"cn_equivalent\": \"这下稳了\", \"annotation\": \"\", \"text_en\": \"GLM-5.2 just made the open-source AI race even more interesting. ... MIT-licensed open weights ... Competitive with frontier closed models on long-horizon software engineering tasks\"}\n  Input: 'Just like the Deepseek FUD has been deployed in different skins at every local high.'\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"正如 DeepSeek 的 FUD 已经在每次当地高点以不同的面目出现。\", \"cn_equivalent\": \"DeepSeek 的唱衰套利\", \"annotation\": \"FUD layers 'anti_cn' + 'security_threat' framing; cite for cross-axis analysis.\", \"text_en\": \"Just like the Deepseek FUD has been deployed in different skins at every local high.\"}\n  Input: 'vibe coder pushing to prod on a Friday afternoon'\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"氛围码农周五下午推上线\", \"cn_equivalent\": \"我就是调参侠\", \"annotation\": \"\", \"text_en\": \"vibe coder pushing to prod on a Friday afternoon\"}\n  Input: 'shrimp jesus AI generated meme flooding X again'\n  Output: {\"lang_detected\": \"en\", \"literal_zh\": \"虾耶稣 AI 生成梗又在 X 上泛滥\", \"cn_equivalent\": \"抽象整活\", \"annotation\": \"虾耶稣是 2024 年 Meta 用户抗议 AI 内容泛滥时流行的 AI 混合图像梗；指代 'AI 生成内容' 的语义特征。\", \"text_en\": \"shrimp jesus AI generated meme flooding X again\"}\n\nTweets (JSON array):\n[{\"tweet_id\": \"2092418532235444527\", \"text\": \"@alija_helly @Alibaba_Qwen @NVIDIAAI Sanırım llama.cpp + Q4_0 da çok daha başarılı. NVFP4 devreye girince herşey değişiyor.\", \"brand_id\": null}, {\"tweet_id\": \"2092418201137406087\", \"text\": \"30 Websites That Feel \\\"Illegal\\\" But Are Perfectly Legal\\n\\n1. https://t.co/zwgMqJOCLh — Free unlimited AI image generation, quality rivals Midjourney\\n\\n2. https://t.co/Q8dO1mwnnZ — Real-time AI image generation, draws as you go\\n\\n3. https://t.co/Z0owtX4O5j — AI unlimited image upscaling, details auto-filled\\n\\n4. https://t.co/DsLNKCCTs4 — AI one-click background removal/lighting fix/erasure\\n\\n5. https://t.co/QGdJP1Eldh — AI voice cloning, mimics any voice in 5 seconds\\n\\n6. https://t.co/8S7Usxk7y7 — Input lyrics to auto-generate full songs\\n\\n7. https://t.co/kXnqc6mjsb — AI video generation pioneer, free Gen-3 trial\\n\\n8. https://t.co/VV72ZNNIAJ — Kuaishou Keling AI, smoothest Chinese video generation\\n\\n9. https://t.co/uAQDZHW9p2 — One photo + one audio clip = talking digital human\\n\\n10. https://t.co/690m2FAR0I — Turns static photos into talking videos\\n\\n11. https://t.co/luYbmOVZdS — AI code writing, free quota enough for daily use\\n\\n12. https://t.co/ylwQrgXsYF — Build websites by talking, zero code\\n\\n13. https://t.co/qZM0Z8ApKw — Vercel AI frontend generator, description becomes page\\n\\n14. https://t.co/8hOSvLedOP — Code in browser + AI assistance + one-click deploy\\n\\n15. https://t.co/EBdsy3pMpo — Paste text to auto-generate infographics\\n\\n16. https://t.co/pwg1kGfQFw — AI one-click PPT generation, say goodbye to PPT hell\\n\\n17. https://t.co/m23OFAV6LP — Notion AI for writing, summarizing, translating\\n\\n18. https://t.co/HTFaOsBZve — Sketch a drawing, AI generates real webpage\\n\\n19. https://t.co/6MdZruAYKy — AI search engine, answers any question instantly + sources\\n\\n20. https://t.co/Ho3G2rYfLp — Developer-exclusive AI search, code issues solved on search\\n\\n21. https://t.co/GnooQ5XNUW — Real-time meeting transcription, free 300 minutes monthly\\n\\n22. https://t.co/nDTLNmhMlQ — AI short video editing, auto-finds highlight clips\\n\\n23. https://t.co/1CdTgJng8I — One site to use GPT-4o / Claude / Gemini\\n\\n24. https://t.co/jpDKhUywm1 — Open-source AI model free playground\\n\\n25. https://t.co/Wv5dNqTyKU — One-click AI background removal, 1-second output\\n\\n26. https://t.co/AfwRqOXsE6 — AI erases any object from photos\\n\\n27. https://t.co/wprRnxBSQn — AI face swap, 1-minute turnaround\\n\\n28. https://t.co/aBICcSyW1B — AI music tagging + recommendations\\n\\n29. https://t.co/98eTBNqlIE — AI writing assistant, free version enough for daily use\\n\\n30. https://t.co/fJT69n8cgP — Anthropic free AI assistant, top-tier long-text handling\\n\\n**🔖 Bookmark this. You’ll need it later.**\\n\\nFollow more @ArifAIHQ\", \"brand_id\": null}, {\"tweet_id\": \"2092417156743074295\", \"text\": \"@cameron_LT @G_O_A_T_Lantern @CeltiC527 I’m using Minimax H3 right now on wan2gp. It can use reference images. I pointed my phone at the screen to record this test and that sound is actually my AC… not the ships rockets… and the dialogue is off… and it’s 480p because I wanted it quick… but you get the idea. https://t.co/Zfv6O3cDj2\", \"brand_id\": null}, {\"tweet_id\": \"2092417217321140707\", \"text\": \"Qwen 3.8 27b no seu mac mini 16gb! Top demais\", \"brand_id\": null}, {\"tweet_id\": \"2092417221759013249\", \"text\": \"Gotta say I was worried about its future when top researchers left qwen a few months back. But it seems qwen didn’t loose its momentum\", \"brand_id\": null}, {\"tweet_id\": \"2092417508938555794\", \"text\": \"@itsvishaltwt Deepseek and  Moonshot from China ✅\", \"brand_id\": null}, {\"tweet_id\": \"2092417519567163566\", \"text\": \"OpenAI just published test results for its first custom inference chip Jalapeño, built with Broadcom.\\n\\nIt went from design to tape-out in 9 months — fastest I've ever seen for a high-end AI ASIC. That speed comes from AI-assisted design.\\n\\nKey specs leaked:\\n- 3.4 PFLOPS FP8 / 13.4 PFLOPS FP4\\n- 216 GiB HBM\\n- 15.4 TB/s memory bandwidth\\n- ~700W typical power draw\\n\\nOn three tested models (GPT-OSS 120B, DeepSeek R1 670B, Kimi K2.5 1T):\\n- 1.5×–1.9× more tokens per watt than NVIDIA GB200/GB300\\n- 1.7×–3.6× lower end-to-end latency\\n\\nIt's inference-only, not for training. And it works with non-OpenAI models too.\\n\\nThis isn't OpenAI ditching NVIDIA — they still need tons of NVIDIA chips for training. But custom silicon for inference is now clearly the path to lower cost at scale.\\n\\nhttps://t.co/oLTR6kjP8s\", \"brand_id\": null}, {\"tweet_id\": \"2092417553981477244\", \"text\": \"@KyleHessling1 It depends on your work load.\\nSomething like an M5 ultra with 512gb can run about 30-40 concurrent sessions with full 250k context window on BF16 running Qwen 3.8 27B full dense.\\nDouble that number if you run FP8.\\nThat is at decent tokens per second.\\n\\nIf you're just running a a few sessions like 1 to 3 then a GPU makes sense.\", \"brand_id\": null}, {\"tweet_id\": \"2092417733032022087\", \"text\": \"@influencer_seo @zeroXmusashi like not just for iterating for professionals. just for people who want videos in general. If the inference speed is that fast the cost is low.\\nIf you serve it at low price, you'd be birthing consumer use for video models. It's too expensive atm (not just u guys, video generation in general).\\n\\nsame applies for agents if you look at the trend, where models are too expensive for most people, than we saw the absurd token usage from deepseek v4 flash cause of how cheap it is.\", \"brand_id\": null}, {\"tweet_id\": \"2092417888158183762\", \"text\": \"Finding a solid starting point for AI apps is often harder than the actual coding. This repository collects over 100 open source AI agents and RAG applications. It covers everything from music generation to local Llama 3.1 implementations that work fully offline.\\n\\nThe project includes practical tools like a Notion MCP agent to query pages from your terminal and a vision RAG system for analyzing PDFs. There is also a production ready RAG service template that runs in under 50 lines of Python.\\n\\nEvery example is Apache 2.0 licensed so you can use them for personal or commercial work. It supports most major models including Claude, GPT, and DeepSeek. You will find specific tutorials for things like fraud investigation agents and self improving skills.\\nhttps://t.co/oPo60zB6aG\\n#Python #OpenSource #LLM #AI\", \"brand_id\": null}, {\"tweet_id\": \"2092417890591101431\", \"text\": \"@gonka_ai Exciting news about DeepSeek V4-Flash-0731 launch.\", \"brand_id\": null}, {\"tweet_id\": \"2092418024573710596\", \"text\": \"ALERT: DGX SPARK USERS!🔥🔥🔥🔥 I couldn't be more excited for this! The new Qwen 122b (well, more like 125b a6b MOE) - Qwen 3.8 Flash Next is the perfect size for a single DGX spark, will definitely outperform 27b in every way, especially speed, and it will be genuinely knowledgeable. This will be the new SPARK daily driver FOR SURE. 14 HOURS from now. \\nhttps://t.co/9jT0TEa7gg\", \"brand_id\": null}, {\"tweet_id\": \"2092418034371895579\", \"text\": \"@hisevenih DeepSeek Harness 热度爆发速度相当惊人\", \"brand_id\": null}, {\"tweet_id\": \"2092418145458008069\", \"text\": \"@MiniMax_AI those numbers are misleading without context. how does minimax-m3 handle edge cases, nuance, or novel queries?\", \"brand_id\": null}, {\"tweet_id\": \"2092418286948356425\", \"text\": \"Yeti Racer! Minimax with Maestro in Pinokio! https://t.co/JdxoTd8PAL\", \"brand_id\": null}, {\"tweet_id\": \"2092418360793289109\", \"text\": \"really liking glance for my personal server, shows me everything I need to see right off the bat + I'm going to integrate hermes-agent with a local model (laguna s2.1 until qwen 100b moe drops). highly suggest! https://t.co/WZOPAKnY94\", \"brand_id\": null}, {\"tweet_id\": \"2092418423540117526\", \"text\": \"this is a super valid take to have. a lot of people are saying that the new mac studio and mac minis aren't worth it at all because they're not like hyper drive machinery that can run ai. people are forgetting that these mac minis are single-handedly some of the best pcs that you can have to do basically anything.\\n\\ni had a super cheap $500 mac mini for like three years that i would do editing video, shooting, homework, regular work etc. on and had zero problems. not only that but you can literally stick this thing in your pocket and take it with you anywhere\\n\\nnow with the m6 chip in a mac mini with 64 gb of ram, you can no joke run qwen 3.8 27b on this with not horrible speed. in six months you'll be able to run opus 5 probably at like half speed. just because you can't run fable 5 at top speeds on these new mac mini’s doesn't mean they're not amazing pieces of machinery\\n\\nmy 256 gb mac studio is single-handedly the craziest piece of hardware i've ever owned. that thing can literally do anything and still run some banger models locally\\n\\nimo these mac’s are the best combination of pc for everyday use + local model capabilities\", \"brand_id\": null}, {\"tweet_id\": \"2092418499109110269\", \"text\": \"很多人問快速提一下。\\n一般人要玩AI無審查影片，又不知道怎佈署，只要用ComfyCloud(MiniMAX H3)+Grok就可以了，目前就是一組很公開的無審查，啥都不懂全雲端操作就是Grok產提示，貼到Cloud生影片，速度也還可以，Cloud大概每月16-20美元，Grok產提示的話不用錢。\", \"brand_id\": null}, {\"tweet_id\": \"2092418664389902503\", \"text\": \"@KlingonYellow @VadimYuryev Correct but open weight like Qwen 3.8 27B, ds4, and even Gemma 4 31B (for creative work) has crossed over from toy models to good enough for real work. For some running \\\"unlimited\\\" free local for 80% of work with api / sub for hardest 20% is the most efficient use of funds.\", \"brand_id\": null}, {\"tweet_id\": \"2092418752378016227\", \"text\": \"Qwen3.8-Flash-Next の登場でクローズド LLM との価格差がさらに縮む。推論速度も安定してくると、日本の中小企業も「わざわざ OpenAI/Anthropic API に出すより自社か AWS で回す」の判断ができるようになる\\n\\n選択肢の自由度が上がるのは市場として健全。多層戦略（開発 = Bedrock / Claude、本番 = Qwen ローカル）も現実的になった\\n\\n#Qwen #LLM #コスト最適化\", \"brand_id\": null}]",
        "role": "user"
      }
    ],
    "model": "deepseek-v4-flash"
  },
  "runtime_only_kwargs": {
    "thinking": {
      "reason": "resolved from production role-specific environment at call time and not persisted",
      "status": "unavailable"
    }
  },
  "stage": "translation",
  "tweet_ids": [
    "2092418532235444527",
    "2092418201137406087",
    "2092417156743074295",
    "2092417217321140707",
    "2092417221759013249",
    "2092417508938555794",
    "2092417519567163566",
    "2092417553981477244",
    "2092417733032022087",
    "2092417888158183762",
    "2092417890591101431",
    "2092418024573710596",
    "2092418034371895579",
    "2092418145458008069",
    "2092418286948356425",
    "2092418360793289109",
    "2092418423540117526",
    "2092418499109110269",
    "2092418664389902503",
    "2092418752378016227"
  ]
}
```

#### Classification batch 1

```json
{
  "batch_index": 1,
  "call_site": "monitor.cycle.CycleRunner._run_post_fetch -> x_monitor.attribution.classify_batch_pragmatics_full",
  "evidence_class": "current_code_reconstruction",
  "historical_wire_call": false,
  "known_request_kwargs": {
    "max_tokens": 4096,
    "messages": [
      {
        "content": "You classify one or more tweets about their relationship to a list of brands, across FIVE dimensions per brand: post_types (array), sentiment (scalar), discourse_roles (array), china_nationalism (scalar), us_nationalism (scalar). You also emit a top-level `unsanctioned_flags: [str]` per tweet for marketing_spam / scam / crypto / unauthorized signals.\n\nFor each brand in each tweet, return FIVE fields from these exact sets:\n\npost_types (6 buckets — what KIND of post; ARRAY, max 3):\n  - buzz_releases            (brand announced something new)\n  - hands_on_usage           (user is using / showing the brand)\n  - performance_comparisons  (benchmark / eval / head-to-head)\n  - feedback_questions       (user asking how-to / help / complaint)\n  - advertising_marketing    (CTA, promo, wrapper, free-credit pitch)\n  - event_announcement       (official event / community meetup)\n\nsentiment (4 values — the VALENCE; scalar):\n  - positive                 (praise, enthusiasm)\n  - negative                 (criticism, disappointment)\n  - neutral                  (informational / question; also when the brand is mentioned only as a COMPARISON POINT and not directly evaluated — 'X is better than Y' is positive for X, neutral for Y)\n  - mixed                    (multiple valences in one post)\n\ndiscourse_roles (10 keys — pragmatic register, §2; ARRAY, max 3):\n  - genuine_hype             (straight praise)\n  - sarcasm                  (English verbal irony)\n  - dunk_yingyang            (阴阳怪气 / passive-aggressive dunk)\n  - self_deprecation         (自嘲 / self-mockery)\n  - cope                     (嘴硬 / stubborn denial)\n  - fud                      (唱衰 / spreading doom)\n  - distillation_accusation  (套壳 / 蒸馏指控)\n  - ai_slop_critique         (AI content-garbage accusation)\n  - absurdist_meme           (抽象整活 / absurdist antics)\n  - advertising-marketing    (salesy, CTA-heavy marketing speak — NOTE: hyphenated, not underscored)\n  - uncategorized            (catch-all when none of the above fit)\n\nunsanctioned_flags (per tweet; ARRAY, top-level — omit when no signal applies):\n  - marketing_spam           (promotional CTA on a brand — usually paired with post_type=advertising_marketing AND discourse_role=advertising-marketing; includes referral-link pitches, 'try it now', 'FREE access' wrappers, third-party aggregator lists with explicit CTAs)\n  - scam                     (impersonation of an official brand account + asks for payment, credentials, or wallet seed)\n  - crypto                   (token ticker / airdrop / wallet claim tied to a brand — 'claim your $X airdrop', 'swap Y for brand token', 'join the liquidity pool')\n  - unauthorized             (brand appears in a third-party post without authorization — giveaway, 'official AI' impersonation, fake partner announcement)\n\nCross-reference rules (these are HARD — emit consistently):\n  - If post_type=advertising_marketing OR discourse_role=advertising-marketing, the post MUST also carry unsanctioned_flags: [\"marketing_spam\"]. The marketing signal is one signal; it shows up in three places.\n  - Comparative mention is NOT negative sentiment. When a post ranks models ('X is better than Y') and does NOT explicitly call Y bad, emit sentiment=neutral for Y. Only emit sentiment=negative when the post contains direct evaluative criticism of the brand (not when it merely ranks another brand above it).\n  - lang_detected is REQUIRED on every tweet. Source-language English posts emit lang_detected='en' with text_en=source text and text_zh_cn=Chinese translation. Source-language Chinese posts emit lang_detected='zh' with text_zh_cn=source text and text_en=English translation. Other languages: emit lang_detected with the source language and populate both translation fields.\n\nchina_nationalism (6-step scale, §4.4; scalar):\n  - none                     (no China-nationalism layer)\n  - mild_pro                 (温和亲华 — subtle positive)\n  - pro                      (亲华 — open positive)\n  - constructive_critical   (建设性批评 — pro-CN criticism)\n  - anti                     (反华 — hostile)\n  - mixed                    (mixed modes in one post)\n\nus_nationalism (6-step scale, same as china_nationalism but\napplied to the US axis — anti = 反美, etc.; scalar):\n  - none / mild_pro / pro / constructive_critical / anti / mixed\n\nRules:\n1. Return ONLY a JSON object matching this shape:\n   {\n     \"results\": [\n       {\n         \"tweet_id\": str,\n         \"classifications\": [\n           {\n             \"brand_id\": str,\n             \"post_types\": [str],         // ARRAY, max 3\n             \"sentiment\": str,             // scalar\n             \"discourse_roles\": [str],     // ARRAY, max 3\n             \"china_nationalism\": str,     // scalar\n             \"us_nationalism\": str         // scalar\n           }, ...\n         ],\n         \"unsanctioned_flags\": [str]      // ARRAY, top-level\n       }, ...\n     ]\n   }\n2. ONE result per input tweet, IN THE SAME ORDER as the input.\n3. Per tweet, RETURN ONE OBJECT PER BRAND LISTED. The brand list is what the keyword detector found in the text — if a brand name appears, you MUST produce an object. Cross-brand comparison posts (\"GLM 5.2 vs Kimi K2.7\"), reply chains where the brand is mentioned, posts sharing screenshots with the brand name — ALL count. Only skip a brand if the post text contains ZERO mention of it (this should be impossible given how the brand list was derived).\n4. Use the EXACT brand_id strings from each tweet's brand list.\n5. Most posts have exactly 1 post_type and 1 discourse_role. Multi-value is allowed when a post legitimately has more than one (e.g., a benchmark write-up that is also a `performance_comparisons` AND `feedback_questions` because it asks 'am I running behind?'). MAXIMUM 3 of each per brand.\n6. nationalism is ORTHOGONAL to post_types × sentiment × discourse_roles — a single post can be e.g. ([perf_compare, feedback], positive, [genuine_hype], none, constructive_critical).\n7. If a tweet is off-topic for all brands (shouldn't happen if the brand list is non-empty), return {\"tweet_id\": \"<id>\", \"classifications\": [], \"unsanctioned_flags\": []}.\n8. genuine_hype is incompatible with explicit call-to-action. If the post contains a CTA (URL + verb like 'try', 'sign up', 'join', 'get', 'limited-time', 'free access', 限时免费, 立即体验, 注册, 点击), discount offer, or wrapper/promo language ('one API key', 'OpenAI-compatible gateway', 'free credit no card'), prefer discourse_role `advertising-marketing` over `genuine_hype`. If both genuine praise AND a CTA coexist, emit BOTH discourse_roles values — let downstream consumers decide.\n9. No prose, no explanation, no code fences.\n\n10. sent=neutral for launch announcements with no evaluative language. A post that says only 'X is generally available', 'Y launched today', 'Z shipped v3.2', or 'W is now in beta' (without praise/criticism) is INFORMATIONAL. emit sent=neutral regardless of whether the brand would benefit from the announcement. Optimistic framing like 'now available for everyone' is still neutral (vendor announcement voice, not user praise).\n11. sent=positive for long analytical / investment posts with explicit positive framing. If the post says 'the model is strategically positive for X's cloud multiple', 'increasingly important as a strategic asset', 'supports the valuation narrative', or similar investment-grade positive language, that IS positive sentiment — do not water it down to sent=mixed because there are also caveats in the post. Caveats and positive framing coexist; positive framing wins.\n12. sent=neutral for multi-brand state-of-market posts that are factual updates per brand ('X climbed 20 spots to #138, 'Y price dropped 8.2%', 'Z was degraded for 45 min'). emit sent=neutral for each brand UNLESS a specific positive/negative evaluative claim is made about that brand in the same post.\n13. pt=event_announcement for one-line 'X is generally available / Y launched / Z shipped' posts. NOT hands_on_usage (the user isn't using the brand — the brand is announcing). NOT buzz_releases (that's a brand-side press release; this rule covers third-party reshares of an announcement too).\n14. pt=performance_comparisons for any post mentioning TTFT (time-to-first-token), latency, benchmark, ranking, '#N ranking', 'N spots climbed/dropped', 'side-by-side race', 'vs <other model>'. The LLM Drag Race write-up ('races GPT-4o-mini vs Llama 3.3 70B side-by-side, measure TTFT') is the canonical example.\n15. pt=performance_comparisons OR pt=feedback_questions for pure analytical commentary (price/perf framing, model governance framing, 'should I switch?' framing). NOT hands_on_usage — the author is analyzing, not using.\n16. Nationalism requires explicit US-China relational framing. Do not infer `china_nationalism` or `us_nationalism` from generic anti-vendor dunk on a Chinese (or US) brand's product failure, benchmark miss, or release reception. A post dunking on Qwen for a benchmark miss is `sentiment=anti-Qwen` and `nationalism=neutral`, NOT `us_nationalism=anti`. The nationalism axes measure US-China framing, not anti-vendor hostility.\n17. Trap-language handling. When the post text contains \"trap\", \"gotcha\", \"embarrassing\", \"fumbled\", or \"翻车\" AND the subject is a Chinese-vendor product failure, the post's `discourse_roles` should include `dunk_yingyang` if the tone is passive-aggressive, or `fud` if the tone is doom-spreading. The post's `us_nationalism` should remain `none` per rule 16 — trap-language is surface vocabulary, not a US-China framing signal.\n18. Superlative praise (`fastest`, `best`, `strongest`, `first to ship`, `most powerful`) describes the brand being praised, NOT a US-China framing. The post is `discourse_roles=[genuine_hype]` for the brand being praised — NOT `us_nationalism=pro/anti` based on which country the praised brand is from. 'Qwen is the fastest model' is hype, not a nationalism statement about China.\n19. Qwen-vendor-not-US distinction. Posts critiquing a Chinese-vendor's product behavior (Qwen, GLM, DeepSeek, Kimi) do not carry `us_nationalism` valence by default. Even when the critique is harsh (\"Qwen faded\", \"DeepSeek shipped a broken model\"), the axis measures US-China framing, not anti-Chinese-vendor sentiment. emit `us_nationalism=none` unless the post explicitly invokes US-China framing.\n\nWorked examples (reference cases; match these patterns):\n  A. 'Kimi K2.7 Code is generally available in GitHub Copilot'\n     → per brand: pt=[event_announcement], sent=neutral,\n       discourse_roles=[uncategorized].\n  B. 'K2.7 Code climbed 20 spots to #138; Deepseek V4 price dropped 8.2%'\n     → per brand: pt=[hands_on_usage], sent=neutral for both,\n       discourse_roles=[uncategorized]. (factual updates, no\n       aggregate judgment.)\n  C. 'Alibaba's Qwen franchise is increasingly important as a\nstrategic cloud and platform asset... strategically positive for BABA's cloud multiple'\n     → qwen: pt=[performance_comparisons],\n       sent=positive, discourse_roles=[genuine_hype].\n       other brands mentioned in same post without explicit\n       positive framing: sent=neutral.\n  D. 'I built LLM Drag Race: races GPT-4o-mini vs Llama 3.3 70B, measure TTFT'\n     → brands present: pt=[performance_comparisons],\n       sent=neutral (showcase, no evaluative claim).\n  E. 'This changes how GitHub routes coding tasks — model picker vs single assistant' (price/perf analytical piece)\n     → pt=[performance_comparisons] OR\n       [feedback_questions] (user implicitly asking 'where does this leave me?'), NOT hands_on_usage.\n  F. 'Kimi K2.7 Code makes Copilot a model marketplace' (rhetorical questions + analytical commentary)\n     → pt=[feedback_questions] (asks 4 rhetorical performance/pricing questions), NOT hands_on_usage.\n  G. 'DeepSeek shipping a benchmark trap — gotcha benchmarks that nobody can reproduce' (anti-vendor dunk on Chinese-vendor product failure)\n     → deepseek: pt=[performance_comparisons], sent=negative,\n       discourse_roles=[dunk_yingyang], cn_nationalism=none,\n       us_nationalism=none. (per rules 16, 17: dunk tone is\n       surface vocabulary, NOT US-China framing.)\n  H. 'Qwen is the fastest model I've benchmarked this month, scored 89% on MMLU'\n     → qwen: pt=[performance_comparisons], sent=positive,\n       discourse_roles=[genuine_hype], cn_nationalism=none,\n       us_nationalism=none. (per rule 18: superlative praise\n       is hype, not a US-China statement.)\n  I. 'GLM 5.2 fumbled the launch — benchmarks collapsed, everyone noticed' (anti-vendor dunk on Chinese-vendor release)\n     → glm: pt=[buzz_releases], sent=negative,\n       discourse_roles=[fud], cn_nationalism=none,\n       us_nationalism=none. (per rules 16, 19: harsh critique\n       of Chinese-vendor product is anti-vendor sentiment,\n       not US-China framing.)\n  J. 'Kimi K2.7 is fast but DeepSeek V4 is faster on coding tasks; the AI race is heating up between US and Chinese vendors'\n     → kimi + deepseek: pt=[performance_comparisons],\n       sent=neutral, discourse_roles=[uncategorized],\n       cn_nationalism=mild_pro, us_nationalism=anti. (this\n       post DOES invoke US-China framing explicitly — rule 16\n       applies the other way: nationalism fires when the post\n       actually names the AI race.)\n\n\nTweets (JSON array of 20):\n[{\"tweet_id\": \"2092418532235444527\", \"text\": \"@alija_helly @Alibaba_Qwen @NVIDIAAI Sanırım llama.cpp + Q4_0 da çok daha başarılı. NVFP4 devreye girince herşey değişiyor.\", \"brand_ids\": [\"llama\"]}, {\"tweet_id\": \"2092418201137406087\", \"text\": \"30 Websites That Feel \\\"Illegal\\\" But Are Perfectly Legal\\n\\n1. https://t.co/zwgMqJOCLh — Free unlimited AI image generation, quality rivals Midjourney\\n\\n2. https://t.co/Q8dO1mwnnZ — Real-time AI image generation, draws as you go\\n\\n3. https://t.co/Z0owtX4O5j — AI unlimited image upscaling, details auto-filled\\n\\n4. https://t.co/DsLNKCCTs4 — AI one-click background removal/lighting fix/erasure\\n\\n5. https://t.co/QGdJP1Eldh — AI voice cloning, mimics any voice in 5 seconds\\n\\n6. https://t.co/8S7Usxk7y7 — Input lyrics to auto-generate full songs\\n\\n7. https://t.co/kXnqc6mjsb — AI video generation pioneer, free Gen-3 trial\\n\\n8. https://t.co/VV72ZNNIAJ — Kuaishou Keling AI, smoothest Chinese video generation\\n\\n9. https://t.co/uAQDZHW9p2 — One photo + one audio clip = talking digital human\\n\\n10. https://t.co/690m2FAR0I — Turns static photos into talking videos\\n\\n11. https://t.co/luYbmOVZdS — AI code writing, free quota enough for daily use\\n\\n12. https://t.co/ylwQrgXsYF — Build websites by talking, zero code\\n\\n13. https://t.co/qZM0Z8ApKw — Vercel AI frontend generator, description becomes page\\n\\n14. https://t.co/8hOSvLedOP — Code in browser + AI assistance + one-click deploy\\n\\n15. https://t.co/EBdsy3pMpo — Paste text to auto-generate infographics\\n\\n16. https://t.co/pwg1kGfQFw — AI one-click PPT generation, say goodbye to PPT hell\\n\\n17. https://t.co/m23OFAV6LP — Notion AI for writing, summarizing, translating\\n\\n18. https://t.co/HTFaOsBZve — Sketch a drawing, AI generates real webpage\\n\\n19. https://t.co/6MdZruAYKy — AI search engine, answers any question instantly + sources\\n\\n20. https://t.co/Ho3G2rYfLp — Developer-exclusive AI search, code issues solved on search\\n\\n21. https://t.co/GnooQ5XNUW — Real-time meeting transcription, free 300 minutes monthly\\n\\n22. https://t.co/nDTLNmhMlQ — AI short video editing, auto-finds highlight clips\\n\\n23. https://t.co/1CdTgJng8I — One site to use GPT-4o / Claude / Gemini\\n\\n24. https://t.co/jpDKhUywm1 — Open-source AI model free playground\\n\\n25. https://t.co/Wv5dNqTyKU — One-click AI background removal, 1-second output\\n\\n26. https://t.co/AfwRqOXsE6 — AI erases any object from photos\\n\\n27. https://t.co/wprRnxBSQn — AI face swap, 1-minute turnaround\\n\\n28. https://t.co/aBICcSyW1B — AI music tagging + recommendations\\n\\n29. https://t.co/98eTBNqlIE — AI writing assistant, free version enough for daily use\\n\\n30. https://t.co/fJT69n8cgP — Anthropic free AI assistant, top-tier long-text handling\\n\\n**🔖 Bookmark this. You’ll need it later.**\\n\\nFollow more @ArifAIHQ\", \"brand_ids\": [\"kuaishou\"]}, {\"tweet_id\": \"2092417156743074295\", \"text\": \"@cameron_LT @G_O_A_T_Lantern @CeltiC527 I’m using Minimax H3 right now on wan2gp. It can use reference images. I pointed my phone at the screen to record this test and that sound is actually my AC… not the ships rockets… and the dialogue is off… and it’s 480p because I wanted it quick… but you get the idea. https://t.co/Zfv6O3cDj2\", \"brand_ids\": [\"minimax\"]}, {\"tweet_id\": \"2092417217321140707\", \"text\": \"Qwen 3.8 27b no seu mac mini 16gb! Top demais\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092417221759013249\", \"text\": \"Gotta say I was worried about its future when top researchers left qwen a few months back. But it seems qwen didn’t loose its momentum\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092417508938555794\", \"text\": \"@itsvishaltwt Deepseek and  Moonshot from China ✅\", \"brand_ids\": [\"deepseek\"]}, {\"tweet_id\": \"2092417519567163566\", \"text\": \"OpenAI just published test results for its first custom inference chip Jalapeño, built with Broadcom.\\n\\nIt went from design to tape-out in 9 months — fastest I've ever seen for a high-end AI ASIC. That speed comes from AI-assisted design.\\n\\nKey specs leaked:\\n- 3.4 PFLOPS FP8 / 13.4 PFLOPS FP4\\n- 216 GiB HBM\\n- 15.4 TB/s memory bandwidth\\n- ~700W typical power draw\\n\\nOn three tested models (GPT-OSS 120B, DeepSeek R1 670B, Kimi K2.5 1T):\\n- 1.5×–1.9× more tokens per watt than NVIDIA GB200/GB300\\n- 1.7×–3.6× lower end-to-end latency\\n\\nIt's inference-only, not for training. And it works with non-OpenAI models too.\\n\\nThis isn't OpenAI ditching NVIDIA — they still need tons of NVIDIA chips for training. But custom silicon for inference is now clearly the path to lower cost at scale.\\n\\nhttps://t.co/oLTR6kjP8s\", \"brand_ids\": [\"deepseek\"]}, {\"tweet_id\": \"2092417553981477244\", \"text\": \"@KyleHessling1 It depends on your work load.\\nSomething like an M5 ultra with 512gb can run about 30-40 concurrent sessions with full 250k context window on BF16 running Qwen 3.8 27B full dense.\\nDouble that number if you run FP8.\\nThat is at decent tokens per second.\\n\\nIf you're just running a a few sessions like 1 to 3 then a GPU makes sense.\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092417733032022087\", \"text\": \"@influencer_seo @zeroXmusashi like not just for iterating for professionals. just for people who want videos in general. If the inference speed is that fast the cost is low.\\nIf you serve it at low price, you'd be birthing consumer use for video models. It's too expensive atm (not just u guys, video generation in general).\\n\\nsame applies for agents if you look at the trend, where models are too expensive for most people, than we saw the absurd token usage from deepseek v4 flash cause of how cheap it is.\", \"brand_ids\": [\"deepseek\"]}, {\"tweet_id\": \"2092417888158183762\", \"text\": \"Finding a solid starting point for AI apps is often harder than the actual coding. This repository collects over 100 open source AI agents and RAG applications. It covers everything from music generation to local Llama 3.1 implementations that work fully offline.\\n\\nThe project includes practical tools like a Notion MCP agent to query pages from your terminal and a vision RAG system for analyzing PDFs. There is also a production ready RAG service template that runs in under 50 lines of Python.\\n\\nEvery example is Apache 2.0 licensed so you can use them for personal or commercial work. It supports most major models including Claude, GPT, and DeepSeek. You will find specific tutorials for things like fraud investigation agents and self improving skills.\\nhttps://t.co/oPo60zB6aG\\n#Python #OpenSource #LLM #AI\", \"brand_ids\": [\"deepseek\", \"llama\"]}, {\"tweet_id\": \"2092417890591101431\", \"text\": \"@gonka_ai Exciting news about DeepSeek V4-Flash-0731 launch.\", \"brand_ids\": [\"deepseek\"]}, {\"tweet_id\": \"2092418024573710596\", \"text\": \"ALERT: DGX SPARK USERS!🔥🔥🔥🔥 I couldn't be more excited for this! The new Qwen 122b (well, more like 125b a6b MOE) - Qwen 3.8 Flash Next is the perfect size for a single DGX spark, will definitely outperform 27b in every way, especially speed, and it will be genuinely knowledgeable. This will be the new SPARK daily driver FOR SURE. 14 HOURS from now. \\nhttps://t.co/9jT0TEa7gg\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092418034371895579\", \"text\": \"@hisevenih DeepSeek Harness 热度爆发速度相当惊人\", \"brand_ids\": [\"deepseek\"]}, {\"tweet_id\": \"2092418145458008069\", \"text\": \"@MiniMax_AI those numbers are misleading without context. how does minimax-m3 handle edge cases, nuance, or novel queries?\", \"brand_ids\": [\"minimax\"]}, {\"tweet_id\": \"2092418286948356425\", \"text\": \"Yeti Racer! Minimax with Maestro in Pinokio! https://t.co/JdxoTd8PAL\", \"brand_ids\": [\"minimax\"]}, {\"tweet_id\": \"2092418360793289109\", \"text\": \"really liking glance for my personal server, shows me everything I need to see right off the bat + I'm going to integrate hermes-agent with a local model (laguna s2.1 until qwen 100b moe drops). highly suggest! https://t.co/WZOPAKnY94\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092418423540117526\", \"text\": \"this is a super valid take to have. a lot of people are saying that the new mac studio and mac minis aren't worth it at all because they're not like hyper drive machinery that can run ai. people are forgetting that these mac minis are single-handedly some of the best pcs that you can have to do basically anything.\\n\\ni had a super cheap $500 mac mini for like three years that i would do editing video, shooting, homework, regular work etc. on and had zero problems. not only that but you can literally stick this thing in your pocket and take it with you anywhere\\n\\nnow with the m6 chip in a mac mini with 64 gb of ram, you can no joke run qwen 3.8 27b on this with not horrible speed. in six months you'll be able to run opus 5 probably at like half speed. just because you can't run fable 5 at top speeds on these new mac mini’s doesn't mean they're not amazing pieces of machinery\\n\\nmy 256 gb mac studio is single-handedly the craziest piece of hardware i've ever owned. that thing can literally do anything and still run some banger models locally\\n\\nimo these mac’s are the best combination of pc for everyday use + local model capabilities\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092418499109110269\", \"text\": \"很多人問快速提一下。\\n一般人要玩AI無審查影片，又不知道怎佈署，只要用ComfyCloud(MiniMAX H3)+Grok就可以了，目前就是一組很公開的無審查，啥都不懂全雲端操作就是Grok產提示，貼到Cloud生影片，速度也還可以，Cloud大概每月16-20美元，Grok產提示的話不用錢。\", \"brand_ids\": [\"minimax\"]}, {\"tweet_id\": \"2092418664389902503\", \"text\": \"@KlingonYellow @VadimYuryev Correct but open weight like Qwen 3.8 27B, ds4, and even Gemma 4 31B (for creative work) has crossed over from toy models to good enough for real work. For some running \\\"unlimited\\\" free local for 80% of work with api / sub for hardest 20% is the most efficient use of funds.\", \"brand_ids\": [\"qwen\"]}, {\"tweet_id\": \"2092418752378016227\", \"text\": \"Qwen3.8-Flash-Next の登場でクローズド LLM との価格差がさらに縮む。推論速度も安定してくると、日本の中小企業も「わざわざ OpenAI/Anthropic API に出すより自社か AWS で回す」の判断ができるようになる\\n\\n選択肢の自由度が上がるのは市場として健全。多層戦略（開発 = Bedrock / Claude、本番 = Qwen ローカル）も現実的になった\\n\\n#Qwen #LLM #コスト最適化\", \"brand_ids\": [\"qwen\"]}]",
        "role": "user"
      }
    ],
    "model": "deepseek-v4-flash"
  },
  "runtime_only_kwargs": {
    "thinking": {
      "reason": "resolved from production classifier environment at call time and not persisted",
      "status": "unavailable"
    }
  },
  "stage": "classification",
  "tweet_ids": [
    "2092418532235444527",
    "2092418201137406087",
    "2092417156743074295",
    "2092417217321140707",
    "2092417221759013249",
    "2092417508938555794",
    "2092417519567163566",
    "2092417553981477244",
    "2092417733032022087",
    "2092417888158183762",
    "2092417890591101431",
    "2092418024573710596",
    "2092418034371895579",
    "2092418145458008069",
    "2092418286948356425",
    "2092418360793289109",
    "2092418423540117526",
    "2092418499109110269",
    "2092418664389902503",
    "2092418752378016227"
  ]
}
```

# Per-post evidence

## Post 1: `2092418532235444527`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | AlicanKiraz0 |
| Author ID | 1793492480203116544 |
| Source query | — |
| Tweet created | 2026-08-26T01:07:07+00:00 |
| Fetched | 2026-08-26T01:15:44.616458+00:00 |
| Tweet URL | https://x.com/AlicanKiraz0/status/2092418532235444527 |
| Source language | tr |
| Detected language | other |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 11 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "llama",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
@alija_helly @Alibaba_Qwen @NVIDIAAI Sanırım llama.cpp + Q4_0 da çok daha başarılı. NVFP4 devreye girince herşey değişiyor.
```

### Persisted translations and commentary

English translation:

```text
@alija_helly @Alibaba_Qwen @NVIDIAAI I think llama.cpp + Q4_0 is also much more successful. When NVFP4 comes into play, everything changes.
```

Simplified Chinese translation:

```text
@alija_helly @Alibaba_Qwen @NVIDIAAI 我觉得 llama.cpp + Q4_0 也要成功得多。NVFP4 一介入，一切就都变了。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
我觉得 llama.cpp + Q4_0 才更靠谱。NVFP4 一上，全都得变。
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:44.620777+00:00 |
| State updated | 2026-08-26T01:16:40.024972+00:00 |

### Per-brand findings

#### `llama`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:44.626116+00:00",
    "raw_token": "llama",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "performance_comparisons",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 2: `2092418201137406087`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | ArifAIHQ |
| Author ID | 1973761301416427520 |
| Source query | — |
| Tweet created | 2026-08-26T01:05:49+00:00 |
| Fetched | 2026-08-26T01:15:42.775864+00:00 |
| Tweet URL | https://x.com/ArifAIHQ/status/2092418201137406087 |
| Source language | en |
| Detected language | en |
| Likes | 3 |
| Reposts | 3 |
| Replies | 2 |
| Quotes | — |
| Views | 28 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
30 Websites That Feel "Illegal" But Are Perfectly Legal

1. https://t.co/zwgMqJOCLh — Free unlimited AI image generation, quality rivals Midjourney

2. https://t.co/Q8dO1mwnnZ — Real-time AI image generation, draws as you go

3. https://t.co/Z0owtX4O5j — AI unlimited image upscaling, details auto-filled

4. https://t.co/DsLNKCCTs4 — AI one-click background removal/lighting fix/erasure

5. https://t.co/QGdJP1Eldh — AI voice cloning, mimics any voice in 5 seconds

6. https://t.co/8S7Usxk7y7 — Input lyrics to auto-generate full songs

7. https://t.co/kXnqc6mjsb — AI video generation pioneer, free Gen-3 trial

8. https://t.co/VV72ZNNIAJ — Kuaishou Keling AI, smoothest Chinese video generation

9. https://t.co/uAQDZHW9p2 — One photo + one audio clip = talking digital human

10. https://t.co/690m2FAR0I — Turns static photos into talking videos

11. https://t.co/luYbmOVZdS — AI code writing, free quota enough for daily use

12. https://t.co/ylwQrgXsYF — Build websites by talking, zero code

13. https://t.co/qZM0Z8ApKw — Vercel AI frontend generator, description becomes page

14. https://t.co/8hOSvLedOP — Code in browser + AI assistance + one-click deploy

15. https://t.co/EBdsy3pMpo — Paste text to auto-generate infographics

16. https://t.co/pwg1kGfQFw — AI one-click PPT generation, say goodbye to PPT hell

17. https://t.co/m23OFAV6LP — Notion AI for writing, summarizing, translating

18. https://t.co/HTFaOsBZve — Sketch a drawing, AI generates real webpage

19. https://t.co/6MdZruAYKy — AI search engine, answers any question instantly + sources

20. https://t.co/Ho3G2rYfLp — Developer-exclusive AI search, code issues solved on search

21. https://t.co/GnooQ5XNUW — Real-time meeting transcription, free 300 minutes monthly

22. https://t.co/nDTLNmhMlQ — AI short video editing, auto-finds highlight clips

23. https://t.co/1CdTgJng8I — One site to use GPT-4o / Claude / Gemini

24. https://t.co/jpDKhUywm1 — Open-source AI model free playground

25. https://t.co/Wv5dNqTyKU — One-click AI background removal, 1-second output

26. https://t.co/AfwRqOXsE6 — AI erases any object from photos

27. https://t.co/wprRnxBSQn — AI face swap, 1-minute turnaround

28. https://t.co/aBICcSyW1B — AI music tagging + recommendations

29. https://t.co/98eTBNqlIE — AI writing assistant, free version enough for daily use

30. https://t.co/fJT69n8cgP — Anthropic free AI assistant, top-tier long-text handling

**🔖 Bookmark this. You’ll need it later.**

Follow more @ArifAIHQ
```

### Persisted translations and commentary

English translation:

```text
30 Websites That Feel "Illegal" But Are Perfectly Legal

1. https://t.co/zwgMqJOCLh — Free unlimited AI image generation, quality rivals Midjourney

2. https://t.co/Q8dO1mwnnZ — Real-time AI image generation, draws as you go

3. https://t.co/Z0owtX4O5j — AI unlimited image upscaling, details auto-filled

4. https://t.co/DsLNKCCTs4 — AI one-click background removal/lighting fix/erasure

5. https://t.co/QGdJP1Eldh — AI voice cloning, mimics any voice in 5 seconds

6. https://t.co/8S7Usxk7y7 — Input lyrics to auto-generate full songs

7. https://t.co/kXnqc6mjsb — AI video generation pioneer, free Gen-3 trial

8. https://t.co/VV72ZNNIAJ — Kuaishou Keling AI, smoothest Chinese video generation

9. https://t.co/uAQDZHW9p2 — One photo + one audio clip = talking digital human

10. https://t.co/690m2FAR0I — Turns static photos into talking videos

11. https://t.co/luYbmOVZdS — AI code writing, free quota enough for daily use

12. https://t.co/ylwQrgXsYF — Build websites by talking, zero code

13. https://t.co/qZM0Z8ApKw — Vercel AI frontend generator, description becomes page

14. https://t.co/8hOSvLedOP — Code in browser + AI assistance + one-click deploy

15. https://t.co/EBdsy3pMpo — Paste text to auto-generate infographics

16. https://t.co/pwg1kGfQFw — AI one-click PPT generation, say goodbye to PPT hell

17. https://t.co/m23OFAV6LP — Notion AI for writing, summarizing, translating

18. https://t.co/HTFaOsBZve — Sketch a drawing, AI generates real webpage

19. https://t.co/6MdZruAYKy — AI search engine, answers any question instantly + sources

20. https://t.co/Ho3G2rYfLp — Developer-exclusive AI search, code issues solved on search

21. https://t.co/GnooQ5XNUW — Real-time meeting transcription, free 300 minutes monthly

22. https://t.co/nDTLNmhMlQ — AI short video editing, auto-finds highlight clips

23. https://t.co/1CdTgJng8I — One site to use GPT-4o / Claude / Gemini

24. https://t.co/jpDKhUywm1 — Open-source AI model free playground

25. https://t.co/Wv5dNqTyKU — One-click AI background removal, 1-second output

26. https://t.co/AfwRqOXsE6 — AI erases any object from photos

27. https://t.co/wprRnxBSQn — AI face swap, 1-minute turnaround

28. https://t.co/aBICcSyW1B — AI music tagging + recommendations

29. https://t.co/98eTBNqlIE — AI writing assistant, free version enough for daily use

30. https://t.co/fJT69n8cgP — Anthropic free AI assistant, top-tier long-text handling

**🔖 Bookmark this. You’ll need it later.**

Follow more @ArifAIHQ
```

Simplified Chinese translation:

```text
30 个用起来“像违法”但完全合法的网站

1. https://t.co/zwgMqJOCLh — 免费无限 AI 图像生成，质量媲美 Midjourney

2. https://t.co/Q8dO1mwnnZ — 实时 AI 图像生成，边画边出

3. https://t.co/Z0owtX4O5j — AI 无限图像放大，自动补细节

4. https://t.co/DsLNKCCTs4 — AI 一键抠图/调光/擦除

5. https://t.co/QGdJP1Eldh — AI 语音克隆，5 秒模仿任何声音

6. https://t.co/8S7Usxk7y7 — 输入歌词自动生成完整歌曲

7. https://t.co/kXnqc6mjsb — AI 视频生成先驱，免费 Gen-3 试用

8. https://t.co/VV72ZNNIAJ — 快手可灵 AI，最流畅的中文视频生成

9. https://t.co/uAQDZHW9p2 — 一张照片+一段音频=说话的数字人

10. https://t.co/690m2FAR0I — 静态照片变成说话视频

11. https://t.co/luYbmOVZdS — AI 写代码，免费额度够日常用

12. https://t.co/ylwQrgXsYF — 说话建网站，零代码

13. https://t.co/qZM0Z8ApKw — Vercel AI 前端生成器，描述变页面

14. https://t.co/8hOSvLedOP — 浏览器里写代码+AI 辅助+一键部署

15. https://t.co/EBdsy3pMpo — 粘贴文字自动生成信息图

16. https://t.co/pwg1kGfQFw — AI 一键生成 PPT，告别 PPT 地狱

17. https://t.co/m23OFAV6LP — Notion AI 写作、总结、翻译

18. https://t.co/HTFaOsBZve — 画个草图，AI 生成真实网页

19. https://t.co/6MdZruAYKy — AI 搜索引擎，秒答任何问题+来源

20. https://t.co/Ho3G2rYfLp — 开发者专属 AI 搜索，代码问题搜着解决

21. https://t.co/GnooQ5XNUW — 实时会议转写，每月免费 300 分钟

22. https://t.co/nDTLNmhMlQ — AI 短视频剪辑，自动找高光片段

23. https://t.co/1CdTgJng8I — 一个站用 GPT-4o / Claude / Gemini

24. https://t.co/jpDKhUywm1 — 开源 AI 模型免费试玩场

25. https://t.co/Wv5dNqTyKU — 一键 AI 抠图，1 秒出结果

26. https://t.co/AfwRqOXsE6 — AI 从照片中擦除任何物体

27. https://t.co/wprRnxBSQn — AI 换脸，1 分钟搞定

28. https://t.co/aBICcSyW1B — AI 音乐标签+推荐

29. https://t.co/98eTBNqlIE — AI 写作助手，免费版够日常用

30. https://t.co/fJT69n8cgP — Anthropic 免费 AI 助手，顶级长文本处理

**🔖 收藏这个。以后用得上。**

关注更多 @ArifAIHQ
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
收藏贴/干货贴
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:42.779814+00:00 |
| State updated | 2026-08-26T01:16:40.018513+00:00 |

### Per-brand findings

#### `kuaishou`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:42.785121+00:00",
    "raw_token": "Kuaishou",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "advertising_marketing",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "advertising-marketing",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
{
  "decided_at": "2026-08-26T01:16:39.758485+00:00",
  "evidence": null,
  "flag_set": [
    "marketing_spam"
  ],
  "flags": "[\"marketing_spam\"]"
}
```

## Post 3: `2092417156743074295`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | SeanWhiting14 |
| Author ID | 1231303402925129729 |
| Source query | — |
| Tweet created | 2026-08-26T01:01:40+00:00 |
| Fetched | 2026-08-26T01:15:36.346277+00:00 |
| Tweet URL | https://x.com/SeanWhiting14/status/2092417156743074295 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | 1 |
| Quotes | — |
| Views | 12 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "minimax",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
@cameron_LT @G_O_A_T_Lantern @CeltiC527 I’m using Minimax H3 right now on wan2gp. It can use reference images. I pointed my phone at the screen to record this test and that sound is actually my AC… not the ships rockets… and the dialogue is off… and it’s 480p because I wanted it quick… but you get the idea. https://t.co/Zfv6O3cDj2
```

### Persisted translations and commentary

English translation:

```text
@cameron_LT @G_O_A_T_Lantern @CeltiC527 I’m using Minimax H3 right now on wan2gp. It can use reference images. I pointed my phone at the screen to record this test and that sound is actually my AC… not the ships rockets… and the dialogue is off… and it’s 480p because I wanted it quick… but you get the idea. https://t.co/Zfv6O3cDj2
```

Simplified Chinese translation:

```text
@cameron_LT @G_O_A_T_Lantern @CeltiC527 我现在在 wan2gp 上用 Minimax H3。它能用参考图。我拿手机对着屏幕录的这个测试，那个声音其实是我空调的……不是飞船火箭的……对白也没对上……而且是 480p 因为我想快点出……但你懂的。https://t.co/Zfv6O3cDj2
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
先看个大概
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.351025+00:00 |
| State updated | 2026-08-26T01:16:40.005639+00:00 |

### Per-brand findings

#### `minimax`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.360122+00:00",
    "raw_token": "Minimax",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 4: `2092417217321140707`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | 0xCVYH |
| Author ID | 1807430231424421888 |
| Source query | — |
| Tweet created | 2026-08-26T01:01:54+00:00 |
| Fetched | 2026-08-26T01:15:36.320689+00:00 |
| Tweet URL | https://x.com/0xCVYH/status/2092417217321140707 |
| Source language | ht |
| Detected language | other |
| Likes | 2 |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 351 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
Qwen 3.8 27b no seu mac mini 16gb! Top demais
```

### Persisted translations and commentary

English translation:

```text
Qwen 3.8 27b on your mac mini 16gb! So awesome
```

Simplified Chinese translation:

```text
Qwen 3.8 27b 在你的 mac mini 16gb 上跑！太顶了
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
Qwen 3.8 27b 跑在 mac mini 16gb 上，牛批
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.3265+00:00 |
| State updated | 2026-08-26T01:16:40.006803+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.332846+00:00",
    "raw_token": "Qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 5: `2092417221759013249`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | abeenax |
| Author ID | 1763339102509019136 |
| Source query | — |
| Tweet created | 2026-08-26T01:01:55+00:00 |
| Fetched | 2026-08-26T01:15:36.281957+00:00 |
| Tweet URL | https://x.com/abeenax/status/2092417221759013249 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 2 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
Gotta say I was worried about its future when top researchers left qwen a few months back. But it seems qwen didn’t loose its momentum
```

### Persisted translations and commentary

English translation:

```text
Gotta say I was worried about its future when top researchers left qwen a few months back. But it seems qwen didn’t loose its momentum
```

Simplified Chinese translation:

```text
不得不说，几个月前顶级研究员离开 Qwen 时，我很担心它的未来。但看来 Qwen 并没有失去势头。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
之前还担心 Qwen 会不会拉胯，结果没拉
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.292089+00:00 |
| State updated | 2026-08-26T01:16:40.007791+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.303361+00:00",
    "raw_token": "qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "buzz_releases",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 6: `2092417508938555794`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | TheDiall |
| Author ID | 90727495 |
| Source query | — |
| Tweet created | 2026-08-26T01:03:04+00:00 |
| Fetched | 2026-08-26T01:15:36.247754+00:00 |
| Tweet URL | https://x.com/TheDiall/status/2092417508938555794 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 2 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
@itsvishaltwt Deepseek and  Moonshot from China ✅
```

### Persisted translations and commentary

English translation:

```text
@itsvishaltwt Deepseek and  Moonshot from China ✅
```

Simplified Chinese translation:

```text
@itsvishaltwt 中国的 DeepSeek 和 Moonshot ✅
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
DeepSeek 和月之暗面
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.25791+00:00 |
| State updated | 2026-08-26T01:16:40.008926+00:00 |

### Per-brand findings

#### `deepseek`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.266444+00:00",
    "raw_token": "Deepseek",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "mild_pro",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 7: `2092417519567163566`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | zhyblife99 |
| Author ID | 1742035208906661888 |
| Source query | — |
| Tweet created | 2026-08-26T01:03:06+00:00 |
| Fetched | 2026-08-26T01:15:36.220077+00:00 |
| Tweet URL | https://x.com/zhyblife99/status/2092417519567163566 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 20 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "deepseek",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
OpenAI just published test results for its first custom inference chip Jalapeño, built with Broadcom.

It went from design to tape-out in 9 months — fastest I've ever seen for a high-end AI ASIC. That speed comes from AI-assisted design.

Key specs leaked:
- 3.4 PFLOPS FP8 / 13.4 PFLOPS FP4
- 216 GiB HBM
- 15.4 TB/s memory bandwidth
- ~700W typical power draw

On three tested models (GPT-OSS 120B, DeepSeek R1 670B, Kimi K2.5 1T):
- 1.5×–1.9× more tokens per watt than NVIDIA GB200/GB300
- 1.7×–3.6× lower end-to-end latency

It's inference-only, not for training. And it works with non-OpenAI models too.

This isn't OpenAI ditching NVIDIA — they still need tons of NVIDIA chips for training. But custom silicon for inference is now clearly the path to lower cost at scale.

https://t.co/oLTR6kjP8s
```

### Persisted translations and commentary

English translation:

```text
OpenAI just published test results for its first custom inference chip Jalapeño, built with Broadcom.

It went from design to tape-out in 9 months — fastest I've ever seen for a high-end AI ASIC. That speed comes from AI-assisted design.

Key specs leaked:
- 3.4 PFLOPS FP8 / 13.4 PFLOPS FP4
- 216 GiB HBM
- 15.4 TB/s memory bandwidth
- ~700W typical power draw

On three tested models (GPT-OSS 120B, DeepSeek R1 670B, Kimi K2.5 1T):
- 1.5×–1.9× more tokens per watt than NVIDIA GB200/GB300
- 1.7×–3.6× lower end-to-end latency

It's inference-only, not for training. And it works with non-OpenAI models too.

This isn't OpenAI ditching NVIDIA — they still need tons of NVIDIA chips for training. But custom silicon for inference is now clearly the path to lower cost at scale.

https://t.co/oLTR6kjP8s
```

Simplified Chinese translation:

```text
OpenAI 刚发布了其首款与 Broadcom 合作打造的自研推理芯片 Jalapeño 的测试结果。

从设计到流片只用了 9 个月——这是我见过的高端 AI ASIC 中最快的。这个速度来自于 AI 辅助设计。

关键规格泄露：
- 3.4 PFLOPS FP8 / 13.4 PFLOPS FP4
- 216 GiB HBM
- 15.4 TB/s 内存带宽
- 典型功耗约 700W

在三个测试模型（GPT-OSS 120B、DeepSeek R1 670B、Kimi K2.5 1T）上：
- 每瓦 token 数比 NVIDIA GB200/GB300 高 1.5×–1.9×
- 端到端延迟低 1.7×–3.6×

它仅用于推理，不用于训练。而且它也适用于非 OpenAI 模型。

这不是 OpenAI 抛弃 NVIDIA——他们训练仍然需要大量 NVIDIA 芯片。但自研推理芯片显然是规模化降本的道路。

https://t.co/oLTR6kjP8s
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
自研推理芯片是降本路
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.225407+00:00 |
| State updated | 2026-08-26T01:16:40.009944+00:00 |

### Per-brand findings

#### `deepseek`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.2333+00:00",
    "raw_token": "DeepSeek",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "performance_comparisons",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 8: `2092417553981477244`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | bigRD73 |
| Author ID | 2066840668123828224 |
| Source query | — |
| Tweet created | 2026-08-26T01:03:14+00:00 |
| Fetched | 2026-08-26T01:15:36.194885+00:00 |
| Tweet URL | https://x.com/bigRD73/status/2092417553981477244 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 7 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "qwen",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
@KyleHessling1 It depends on your work load.
Something like an M5 ultra with 512gb can run about 30-40 concurrent sessions with full 250k context window on BF16 running Qwen 3.8 27B full dense.
Double that number if you run FP8.
That is at decent tokens per second.

If you're just running a a few sessions like 1 to 3 then a GPU makes sense.
```

### Persisted translations and commentary

English translation:

```text
@KyleHessling1 It depends on your work load.
Something like an M5 ultra with 512gb can run about 30-40 concurrent sessions with full 250k context window on BF16 running Qwen 3.8 27B full dense.
Double that number if you run FP8.
That is at decent tokens per second.

If you're just running a a few sessions like 1 to 3 then a GPU makes sense.
```

Simplified Chinese translation:

```text
@KyleHessling1 看你的负载。
像 M5 ultra 512gb 这样的机器，用 BF16 跑 Qwen 3.8 27B 全量 dense，可以跑大约 30-40 个并发会话，满载 250k 上下文窗口。
跑 FP8 的话这个数字翻倍。
而且 token 每秒速度还不错。

如果你只是跑 1 到 3 个会话，那用 GPU 更合理。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
看负载，本地跑就够
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.199195+00:00 |
| State updated | 2026-08-26T01:16:40.010932+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.20635+00:00",
    "raw_token": "Qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "performance_comparisons",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 9: `2092417733032022087`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | 1_missthesun |
| Author ID | 1993775496367390720 |
| Source query | — |
| Tweet created | 2026-08-26T01:03:57+00:00 |
| Fetched | 2026-08-26T01:15:36.174787+00:00 |
| Tweet URL | https://x.com/1_missthesun/status/2092417733032022087 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 3 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
@influencer_seo @zeroXmusashi like not just for iterating for professionals. just for people who want videos in general. If the inference speed is that fast the cost is low.
If you serve it at low price, you'd be birthing consumer use for video models. It's too expensive atm (not just u guys, video generation in general).

same applies for agents if you look at the trend, where models are too expensive for most people, than we saw the absurd token usage from deepseek v4 flash cause of how cheap it is.
```

### Persisted translations and commentary

English translation:

```text
@influencer_seo @zeroXmusashi like not just for iterating for professionals. just for people who want videos in general. If the inference speed is that fast the cost is low.
If you serve it at low price, you'd be birthing consumer use for video models. It's too expensive atm (not just u guys, video generation in general).

same applies for agents if you look at the trend, where models are too expensive for most people, than we saw the absurd token usage from deepseek v4 flash cause of how cheap it is.
```

Simplified Chinese translation:

```text
@influencer_seo @zeroXmusashi 不只是给专业人士做迭代。就是给普通人想要视频的。如果推理速度这么快，成本就低。
如果你低价提供服务，你就会催生视频模型的消费者级使用。目前太贵了（不只是你们，整个视频生成都很贵）。

代理商也一样，如果你看趋势，模型对大多数人来说太贵，然后我们就看到了 deepseek v4 flash 因为便宜而产生的荒谬 token 使用量。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
便宜才是硬道理
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.178982+00:00 |
| State updated | 2026-08-26T01:16:40.011781+00:00 |

### Per-brand findings

#### `deepseek`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.184574+00:00",
    "raw_token": "deepseek",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "feedback_questions",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 10: `2092417888158183762`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | N0V4Dev |
| Author ID | 12216 |
| Source query | — |
| Tweet created | 2026-08-26T01:04:34+00:00 |
| Fetched | 2026-08-26T01:15:36.143806+00:00 |
| Tweet URL | https://x.com/N0V4Dev/status/2092417888158183762 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 9 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "deepseek",
    "reason": "missing_discourse",
    "stage": "classification"
  },
  {
    "brand_id": "llama",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
Finding a solid starting point for AI apps is often harder than the actual coding. This repository collects over 100 open source AI agents and RAG applications. It covers everything from music generation to local Llama 3.1 implementations that work fully offline.

The project includes practical tools like a Notion MCP agent to query pages from your terminal and a vision RAG system for analyzing PDFs. There is also a production ready RAG service template that runs in under 50 lines of Python.

Every example is Apache 2.0 licensed so you can use them for personal or commercial work. It supports most major models including Claude, GPT, and DeepSeek. You will find specific tutorials for things like fraud investigation agents and self improving skills.
https://t.co/oPo60zB6aG
#Python #OpenSource #LLM #AI
```

### Persisted translations and commentary

English translation:

```text
Finding a solid starting point for AI apps is often harder than the actual coding. This repository collects over 100 open source AI agents and RAG applications. It covers everything from music generation to local Llama 3.1 implementations that work fully offline.

The project includes practical tools like a Notion MCP agent to query pages from your terminal and a vision RAG system for analyzing PDFs. There is also a production ready RAG service template that runs in under 50 lines of Python.

Every example is Apache 2.0 licensed so you can use them for personal or commercial work. It supports most major models including Claude, GPT, and DeepSeek. You will find specific tutorials for things like fraud investigation agents and self improving skills.
https://t.co/oPo60zB6aG
#Python #OpenSource #LLM #AI
```

Simplified Chinese translation:

```text
为 AI 应用找一个扎实的起点往往比实际写代码还难。这个仓库收集了 100 多个开源 AI 智能体和 RAG 应用。从音乐生成到完全离线的本地 Llama 3.1 实现，应有尽有。

项目包含实用工具，比如可以用终端查询页面的 Notion MCP 智能体，以及分析 PDF 的视觉 RAG 系统。还有一个 50 行 Python 以内就能跑起来的生产级 RAG 服务模板。

每个示例都是 Apache 2.0 许可，个人或商业使用都可以。它支持包括 Claude、GPT 和 DeepSeek 在内的大多数主流模型。你会找到比如欺诈调查智能体和自我改进技能的具体教程。
https://t.co/oPo60zB6aG
#Python #OpenSource #LLM #AI
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
干货仓库
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.14823+00:00 |
| State updated | 2026-08-26T01:16:40.012753+00:00 |

### Per-brand findings

#### `deepseek`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.164061+00:00",
    "raw_token": "DeepSeek",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

#### `llama`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.153699+00:00",
    "raw_token": "Llama",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 11: `2092417890591101431`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | storylove1206 |
| Author ID | 2011132207507849216 |
| Source query | — |
| Tweet created | 2026-08-26T01:04:35+00:00 |
| Fetched | 2026-08-26T01:15:36.124111+00:00 |
| Tweet URL | https://x.com/storylove1206/status/2092417890591101431 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 2 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
@gonka_ai Exciting news about DeepSeek V4-Flash-0731 launch.
```

### Persisted translations and commentary

English translation:

```text
@gonka_ai Exciting news about DeepSeek V4-Flash-0731 launch.
```

Simplified Chinese translation:

```text
@gonka_ai 关于 DeepSeek V4-Flash-0731 发布的消息真让人兴奋。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
DeepSeek V4-Flash 发布，期待
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.128421+00:00 |
| State updated | 2026-08-26T01:16:40.013631+00:00 |

### Per-brand findings

#### `deepseek`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.134022+00:00",
    "raw_token": "DeepSeek",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "event_announcement",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 12: `2092418024573710596`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | jaita |
| Author ID | 17449109 |
| Source query | — |
| Tweet created | 2026-08-26T01:05:06+00:00 |
| Fetched | 2026-08-26T01:15:36.095703+00:00 |
| Tweet URL | https://x.com/jaita/status/2092418024573710596 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 11 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
ALERT: DGX SPARK USERS!🔥🔥🔥🔥 I couldn't be more excited for this! The new Qwen 122b (well, more like 125b a6b MOE) - Qwen 3.8 Flash Next is the perfect size for a single DGX spark, will definitely outperform 27b in every way, especially speed, and it will be genuinely knowledgeable. This will be the new SPARK daily driver FOR SURE. 14 HOURS from now. 
https://t.co/9jT0TEa7gg
```

### Persisted translations and commentary

English translation:

```text
ALERT: DGX SPARK USERS!🔥🔥🔥🔥 I couldn't be more excited for this! The new Qwen 122b (well, more like 125b a6b MOE) - Qwen 3.8 Flash Next is the perfect size for a single DGX spark, will definitely outperform 27b in every way, especially speed, and it will be genuinely knowledgeable. This will be the new SPARK daily driver FOR SURE. 14 HOURS from now. 
https://t.co/9jT0TEa7gg
```

Simplified Chinese translation:

```text
警报：DGX SPARK 用户！🔥🔥🔥🔥 我太兴奋了！新的 Qwen 122b（嗯，更像 125b a6b MOE）——Qwen 3.8 Flash Next 是单块 DGX Spark 的完美尺寸，绝对会在各方面超越 27b，尤其是速度，而且会真的很有知识。这肯定将成为新的 SPARK 日常主力。14 小时后。
https://t.co/9jT0TEa7gg
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
DGX Spark 用户的福音
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.102354+00:00 |
| State updated | 2026-08-26T01:16:40.014485+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.108282+00:00",
    "raw_token": "Qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "event_announcement",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 13: `2092418034371895579`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | lianshang37 |
| Author ID | 718273566 |
| Source query | — |
| Tweet created | 2026-08-26T01:05:09+00:00 |
| Fetched | 2026-08-26T01:15:36.072319+00:00 |
| Tweet URL | https://x.com/lianshang37/status/2092418034371895579 |
| Source language | zh |
| Detected language | zh-Hans |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 8 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "reason": "missing_text_en",
    "stage": "translation"
  },
  {
    "reason": "missing_text_zh_cn",
    "stage": "translation"
  }
]
```

### Full source text

```text
@hisevenih DeepSeek Harness 热度爆发速度相当惊人
```

### Persisted translations and commentary

English translation:

```text

```

Simplified Chinese translation:

```text

```

English commentary:

```text

```

Simplified Chinese commentary:

```text
DeepSeek Harness 火了
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.076563+00:00 |
| State updated | 2026-08-26T01:16:40.016811+00:00 |

### Per-brand findings

#### `deepseek`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.084363+00:00",
    "raw_token": "DeepSeek",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "buzz_releases",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 14: `2092418145458008069`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | adelbucetta |
| Author ID | 1481272107745095682 |
| Source query | — |
| Tweet created | 2026-08-26T01:05:35+00:00 |
| Fetched | 2026-08-26T01:15:36.050754+00:00 |
| Tweet URL | https://x.com/adelbucetta/status/2092418145458008069 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 2 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "minimax",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
@MiniMax_AI those numbers are misleading without context. how does minimax-m3 handle edge cases, nuance, or novel queries?
```

### Persisted translations and commentary

English translation:

```text
@MiniMax_AI those numbers are misleading without context. how does minimax-m3 handle edge cases, nuance, or novel queries?
```

Simplified Chinese translation:

```text
@MiniMax_AI 没有上下文这些数字是误导性的。minimax-m3 如何处理边缘案例、细微差别或新颖查询？
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
别光吹数据，看真实能力
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.055059+00:00 |
| State updated | 2026-08-26T01:16:40.017667+00:00 |

### Per-brand findings

#### `minimax`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.061699+00:00",
    "raw_token": "minimax",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "feedback_questions",
    "sentiment": "negative"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 15: `2092418286948356425`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | AlmostYeti |
| Author ID | 1016958342 |
| Source query | — |
| Tweet created | 2026-08-26T01:06:09+00:00 |
| Fetched | 2026-08-26T01:15:36.025393+00:00 |
| Tweet URL | https://x.com/AlmostYeti/status/2092418286948356425 |
| Source language | it |
| Detected language | en |
| Likes | 1 |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 5 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "minimax",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
Yeti Racer! Minimax with Maestro in Pinokio! https://t.co/JdxoTd8PAL
```

### Persisted translations and commentary

English translation:

```text
Yeti Racer! Minimax with Maestro in Pinokio! https://t.co/JdxoTd8PAL
```

Simplified Chinese translation:

```text
雪人赛车！Pinokio 里的 Minimax 和 Maestro！https://t.co/JdxoTd8PAL
```

English commentary:

```text

```

Simplified Chinese commentary:

```text

```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.033041+00:00 |
| State updated | 2026-08-26T01:16:40.020662+00:00 |

### Per-brand findings

#### `minimax`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.038809+00:00",
    "raw_token": "Minimax",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 16: `2092418360793289109`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | kaiostephens |
| Author ID | 623020086 |
| Source query | — |
| Tweet created | 2026-08-26T01:06:27+00:00 |
| Fetched | 2026-08-26T01:15:36.001432+00:00 |
| Tweet URL | https://x.com/kaiostephens/status/2092418360793289109 |
| Source language | en |
| Detected language | en |
| Likes | 2 |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 27 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
really liking glance for my personal server, shows me everything I need to see right off the bat + I'm going to integrate hermes-agent with a local model (laguna s2.1 until qwen 100b moe drops). highly suggest! https://t.co/WZOPAKnY94
```

### Persisted translations and commentary

English translation:

```text
really liking glance for my personal server, shows me everything I need to see right off the bat + I'm going to integrate hermes-agent with a local model (laguna s2.1 until qwen 100b moe drops). highly suggest! https://t.co/WZOPAKnY94
```

Simplified Chinese translation:

```text
真的很喜欢我的个人服务器上的 glance，一上来就给我看我需要的一切 + 我打算把 hermes-agent 和一个本地模型集成（先 laguna s2.1，等 qwen 100b moe 出来再换）。强烈推荐！https://t.co/WZOPAKnY94
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
强烈安利
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:36.005828+00:00 |
| State updated | 2026-08-26T01:16:40.021782+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:36.013209+00:00",
    "raw_token": "qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 17: `2092418423540117526`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | ashen_one |
| Author ID | 2509387159 |
| Source query | — |
| Tweet created | 2026-08-26T01:06:42+00:00 |
| Fetched | 2026-08-26T01:15:35.970486+00:00 |
| Tweet URL | https://x.com/ashen_one/status/2092418423540117526 |
| Source language | en |
| Detected language | en |
| Likes | 8 |
| Reposts | — |
| Replies | 3 |
| Quotes | — |
| Views | 509 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
this is a super valid take to have. a lot of people are saying that the new mac studio and mac minis aren't worth it at all because they're not like hyper drive machinery that can run ai. people are forgetting that these mac minis are single-handedly some of the best pcs that you can have to do basically anything.

i had a super cheap $500 mac mini for like three years that i would do editing video, shooting, homework, regular work etc. on and had zero problems. not only that but you can literally stick this thing in your pocket and take it with you anywhere

now with the m6 chip in a mac mini with 64 gb of ram, you can no joke run qwen 3.8 27b on this with not horrible speed. in six months you'll be able to run opus 5 probably at like half speed. just because you can't run fable 5 at top speeds on these new mac mini’s doesn't mean they're not amazing pieces of machinery

my 256 gb mac studio is single-handedly the craziest piece of hardware i've ever owned. that thing can literally do anything and still run some banger models locally

imo these mac’s are the best combination of pc for everyday use + local model capabilities
```

### Persisted translations and commentary

English translation:

```text
this is a super valid take to have. a lot of people are saying that the new mac studio and mac minis aren't worth it at all because they're not like hyper drive machinery that can run ai. people are forgetting that these mac minis are single-handedly some of the best pcs that you can have to do basically anything.

i had a super cheap $500 mac mini for like three years that i would do editing video, shooting, homework, regular work etc. on and had zero problems. not only that but you can literally stick this thing in your pocket and take it with you anywhere

now with the m6 chip in a mac mini with 64 gb of ram, you can no joke run qwen 3.8 27b on this with not horrible speed. in six months you'll be able to run opus 5 probably at like half speed. just because you can't run fable 5 at top speeds on these new mac mini’s doesn't mean they're not amazing pieces of machinery

my 256 gb mac studio is single-handedly the craziest piece of hardware i've ever owned. that thing can literally do anything and still run some banger models locally

imo these mac’s are the best combination of pc for everyday use + local model capabilities
```

Simplified Chinese translation:

```text
这个观点非常对。很多人说新的 Mac Studio 和 Mac mini 完全不值，因为它们不是那种能跑 AI 的超级机器。人们忘了这些 Mac mini 单凭一己之力就是你能拥有的最好的 PC 之一，基本什么都能干。

我有一台超便宜的 500 美元 Mac mini 用了大概三年，剪视频、拍摄、作业、日常工作等等都在上面干，零问题。不仅如此，你简直可以把它塞进口袋带到任何地方。

现在有了带 64 GB 内存的 M6 芯片 Mac mini，你可以真的在上面跑 qwen 3.8 27b，速度还不算差。六个月后你大概能以一半速度跑 opus 5。只是因为你在这些新 Mac mini 上不能以最高速度跑 fable 5，并不意味着它们不是了不起的机器。

我的 256 GB Mac Studio 单凭一己之力就是我拥有过的最疯狂的硬件。那东西真的什么都能干，而且还能本地跑一些顶级的模型。

在我看来，这些 Mac 是日常 PC 和本地模型能力的最佳组合。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
Mac mini 本地跑模型真香
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:35.979059+00:00 |
| State updated | 2026-08-26T01:16:40.02283+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:35.986479+00:00",
    "raw_token": "qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 18: `2092418499109110269`

| Field | Value |
| --- | --- |
| Health state | unhealthy |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | minigirlmizuoto |
| Author ID | 46327221 |
| Source query | — |
| Tweet created | 2026-08-26T01:07:00+00:00 |
| Fetched | 2026-08-26T01:15:35.938319+00:00 |
| Tweet URL | https://x.com/minigirlmizuoto/status/2092418499109110269 |
| Source language | zh |
| Detected language | zh-Hant |
| Likes | 1 |
| Reposts | — |
| Replies | 1 |
| Quotes | — |
| Views | 165 |
| Metrics refreshed | — |

### Health findings

```json
[
  {
    "brand_id": "minimax",
    "reason": "missing_discourse",
    "stage": "classification"
  }
]
```

### Full source text

```text
很多人問快速提一下。
一般人要玩AI無審查影片，又不知道怎佈署，只要用ComfyCloud(MiniMAX H3)+Grok就可以了，目前就是一組很公開的無審查，啥都不懂全雲端操作就是Grok產提示，貼到Cloud生影片，速度也還可以，Cloud大概每月16-20美元，Grok產提示的話不用錢。
```

### Persisted translations and commentary

English translation:

```text
A quick mention for those asking.
For ordinary people who want to play with uncensored AI videos but don't know how to deploy, just use ComfyCloud (MiniMAX H3) + Grok. Currently this is a public uncensored combo. If you know nothing and want all-cloud operation, use Grok to generate prompts, paste into Cloud to generate videos, speed is acceptable. Cloud costs about $16-20/month, Grok prompt generation is free.
```

Simplified Chinese translation:

```text
很多人问快速提一下。
一般人要玩 AI 无审查影片，又不知道怎么部署，只要用 ComfyCloud(MiniMAX H3)+Grok 就可以了，目前就是一組很公开的无审查，啥都不懂全云端操作就是 Grok 产提示，贴到 Cloud 生影片，速度也还可以，Cloud 大概每月 16-20 美元，Grok 产提示的话不用钱。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
无审查视频玩法：ComfyCloud+Grok
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:35.942304+00:00 |
| State updated | 2026-08-26T01:16:40.023958+00:00 |

### Per-brand findings

#### `minimax`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:35.951185+00:00",
    "raw_token": "MiniMAX",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "hands_on_usage",
    "sentiment": "neutral"
  }
]
```

Discourse and nationalism:

```json
[]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 19: `2092418664389902503`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | ugly_cowboy |
| Author ID | 1380536011 |
| Source query | — |
| Tweet created | 2026-08-26T01:07:39+00:00 |
| Fetched | 2026-08-26T01:15:35.918769+00:00 |
| Tweet URL | https://x.com/ugly_cowboy/status/2092418664389902503 |
| Source language | en |
| Detected language | en |
| Likes | — |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 5 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
@KlingonYellow @VadimYuryev Correct but open weight like Qwen 3.8 27B, ds4, and even Gemma 4 31B (for creative work) has crossed over from toy models to good enough for real work. For some running "unlimited" free local for 80% of work with api / sub for hardest 20% is the most efficient use of funds.
```

### Persisted translations and commentary

English translation:

```text
@KlingonYellow @VadimYuryev Correct but open weight like Qwen 3.8 27B, ds4, and even Gemma 4 31B (for creative work) has crossed over from toy models to good enough for real work. For some running "unlimited" free local for 80% of work with api / sub for hardest 20% is the most efficient use of funds.
```

Simplified Chinese translation:

```text
@KlingonYellow @VadimYuryev 对，但像 Qwen 3.8 27B、ds4、甚至 Gemma 4 31B（用于创意工作）这样的开放权重已经从玩具模型跨越到足够做真正的工作了。对一些人来说，80% 的工作跑“无限”免费本地，最难 20% 用 api/订阅，是最有效的资金使用方式。
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
本地跑 80%，API 跑 20%
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:35.923246+00:00 |
| State updated | 2026-08-26T01:16:40.029383+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:35.928966+00:00",
    "raw_token": "Qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "performance_comparisons",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

## Post 20: `2092418752378016227`

| Field | Value |
| --- | --- |
| Health state | complete |
| Translation status | succeeded |
| Classification status | succeeded |
| Author | ikekatsuai |
| Author ID | 2034821446535716865 |
| Source query | — |
| Tweet created | 2026-08-26T01:08:00+00:00 |
| Fetched | 2026-08-26T01:15:35.895401+00:00 |
| Tweet URL | https://x.com/ikekatsuai/status/2092418752378016227 |
| Source language | ja |
| Detected language | ja |
| Likes | 1 |
| Reposts | — |
| Replies | — |
| Quotes | — |
| Views | 10 |
| Metrics refreshed | — |

### Health findings

```json
[]
```

### Full source text

```text
Qwen3.8-Flash-Next の登場でクローズド LLM との価格差がさらに縮む。推論速度も安定してくると、日本の中小企業も「わざわざ OpenAI/Anthropic API に出すより自社か AWS で回す」の判断ができるようになる

選択肢の自由度が上がるのは市場として健全。多層戦略（開発 = Bedrock / Claude、本番 = Qwen ローカル）も現実的になった

#Qwen #LLM #コスト最適化
```

### Persisted translations and commentary

English translation:

```text
With the arrival of Qwen3.8-Flash-Next, the price gap with closed LLMs will shrink further. As inference speed becomes stable, Japanese SMEs can also decide "instead of going out of our way to use the OpenAI/Anthropic API, we'll run it in-house or on AWS".

More freedom of choice is healthy for the market. A multi-layer strategy (development = Bedrock / Claude, production = Qwen local) has also become realistic.

#Qwen #LLM #CostOptimization
```

Simplified Chinese translation:

```text
Qwen3.8-Flash-Next 的到来让与闭源 LLM 的价差进一步缩小。推理速度也稳定下来的话，日本中小企业也能做出“不用特意调用 OpenAI/Anthropic API，而是在自家或 AWS 上跑”的判断。

选择自由度提高对市场来说是健康的。多层策略（开发 = Bedrock / Claude、生产 = Qwen 本地）也变得现实了。

#Qwen #LLM #成本优化
```

English commentary:

```text

```

Simplified Chinese commentary:

```text
Qwen 便宜了，日本企业可以本地化了
```

### Durable enrichment state

| Field | Value |
| --- | --- |
| Translation attempts | 1 |
| Translation first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Translation next attempt | — |
| Translation error code | — |
| Classification attempts | 1 |
| Classification first attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification last attempt | 2026-08-26T01:15:47.365443+00:00 |
| Classification next attempt | — |
| Classification error code | — |
| State created | 2026-08-26T01:15:35.900521+00:00 |
| State updated | 2026-08-26T01:16:40.030799+00:00 |

### Per-brand findings

#### `qwen`

| Field | Value |
| --- | --- |
| Weight | 1 |

Mentions:

```json
[
  {
    "mentioned_at": "2026-08-26T01:15:35.906587+00:00",
    "raw_token": "Qwen",
    "source": "body_keyword"
  }
]
```

Post types and sentiment:

```json
[
  {
    "post_type": "performance_comparisons",
    "sentiment": "positive"
  }
]
```

Discourse and nationalism:

```json
[
  {
    "act_id": 0,
    "china_nationalism": "none",
    "discourse": "genuine_hype",
    "us_nationalism": "none"
  }
]
```

### Unsanctioned-flag evidence

```json
null
```

# Reproducibility appendix

## Exact read-only SQL

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '20s';
WITH
  selected AS (
    SELECT
      p.*,
      ROW_NUMBER() OVER (
        ORDER BY p.fetched_at DESC, p.tweet_id DESC
      ) - 1 AS ordinal
    FROM posts p
    ORDER BY p.fetched_at DESC, p.tweet_id DESC
    LIMIT 20
  ),
  post_rows AS (
    SELECT
      p.ordinal,
      jsonb_build_object(
        'tweet_id', p.tweet_id,
        'fetched_at', p.fetched_at,
        'author_id', p.author_id,
        'author_handle', p.author_handle,
        'author_name', p.author_name,
        'source_query_id', p.source_query_id,
        'created_at', p.created_at,
        'text', p.text,
        'lang', p.lang,
        'lang_detected', p.lang_detected,
        'text_en', p.text_en,
        'text_zh_cn', p.text_zh_cn,
        'commentary_en', p.commentary_en,
        'commentary_zh_cn', p.commentary_zh_cn,
        'tweet_url', COALESCE(p.tweet_url, p.tweet_twitter_url),
        'like_count', p.like_count,
        'retweet_count', p.retweet_count,
        'reply_count', p.reply_count,
        'quote_count', p.quote_count,
        'view_count', p.view_count,
        'metrics_refreshed_at', p.metrics_refreshed_at,
        'translation_attempts', es.translation_attempts,
        'translation_first_attempt_at', es.translation_first_attempt_at,
        'translation_last_attempt_at', es.translation_last_attempt_at,
        'translation_next_attempt_at', es.translation_next_attempt_at,
        'classification_attempts', es.classification_attempts,
        'classification_first_attempt_at', es.classification_first_attempt_at,
        'classification_last_attempt_at', es.classification_last_attempt_at,
        'classification_next_attempt_at', es.classification_next_attempt_at,
        'enrichment_created_at', es.created_at,
        'enrichment_updated_at', es.updated_at,
        'unsanctioned_flags', (
          SELECT jsonb_build_object(
            'flags', uf.flags,
            'flag_set', uf.flag_set,
            'evidence', uf.evidence,
            'decided_at', uf.decided_at
          )
          FROM posts_unsanctioned_flags uf
          WHERE uf.post_id = p.tweet_id
        ),
        'age_seconds', CASE
          WHEN es.created_at IS NULL THEN NULL
          ELSE GREATEST(
            0,
            FLOOR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - es.created_at)))
          )::bigint
        END,
        'has_text', NULLIF(BTRIM(p.text), '') IS NOT NULL,
        'has_lang_detected', NULLIF(BTRIM(p.lang_detected), '') IS NOT NULL,
        'has_text_en', NULLIF(BTRIM(p.text_en), '') IS NOT NULL,
        'has_text_zh_cn', NULLIF(BTRIM(p.text_zh_cn), '') IS NOT NULL,
        'translation_status', es.translation_status,
        'translation_error_code', es.translation_error_code,
        'classification_status', es.classification_status,
        'classification_error_code', es.classification_error_code,
        'brands', COALESCE((
          SELECT jsonb_agg(
            jsonb_build_object(
              'brand_id', pb.brand_id,
              'weight', pb.weight,
              'mentions', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'source', mention.source,
                    'raw_token', mention.raw_token,
                    'mentioned_at', mention.mentioned_at
                  )
                  ORDER BY mention.source, mention.mentioned_at
                )
                FROM posts_brands_mentions mention
                WHERE mention.post_id = p.tweet_id
                  AND mention.brand_id = pb.brand_id
              ), '[]'::jsonb),
              'signals', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'post_type', signal.post_type_key,
                    'sentiment', signal.sentiment
                  )
                  ORDER BY signal.post_type_key, signal.sentiment
                )
                FROM posts_brands_signals signal
                WHERE signal.post_id = p.tweet_id
                  AND signal.brand_id = pb.brand_id
              ), '[]'::jsonb),
              'discourses', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'discourse', discourse.discourse_key,
                    'act_id', discourse.act_id,
                    'china_nationalism', discourse.china_nationalism,
                    'us_nationalism', discourse.us_nationalism
                  )
                  ORDER BY discourse.discourse_key, discourse.act_id
                )
                FROM posts_brands_discourse discourse
                WHERE discourse.post_id = p.tweet_id
                  AND discourse.brand_id = pb.brand_id
              ), '[]'::jsonb)
            )
            ORDER BY pb.brand_id
          )
          FROM posts_brands pb
          WHERE pb.post_id = p.tweet_id
        ), '[]'::jsonb)
      ) AS post_data
    FROM selected p
    LEFT JOIN post_enrichment_states es ON es.post_id = p.tweet_id
  )
SELECT jsonb_build_object(
  'transaction_read_only', current_setting('transaction_read_only'),
  'posts', COALESCE(
    jsonb_agg(post_data ORDER BY ordinal),
    '[]'::jsonb
  )
)::text
FROM post_rows;
COMMIT;
```

## Checker implementation

| Field | Value |
| --- | --- |
| Checker path | .claude/skills/harvester-latest-n-health-check/scripts/check.py |
| Checker file-content SHA-256 | 98f3ea0d515a41bf8950e0ac08747293c7dd2baefe9887dbaac1c1e8d7703c71 |
| Repository commit | a4eb9fe419b5a28e3281e1fc1b67fc7abd9bcced |
| Python version | 3.12.13 (main, Apr  7 2026, 21:09:58) [Clang 22.1.1 ] |
| Repository root | /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/harvester-latest-n-health-check-skill |

The complete checker source used to render this artifact follows. It includes cohort selection, health rules, SQL, request reconstruction, report rendering, atomic write behavior, and stable error handling.

```python
#!/usr/bin/env python3
"""Read-only health report for the newest persisted production posts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

DATABASE_RESOURCE = "pushinweight-db-shadow"
DEFAULT_LATEST = 20
MAX_COHORT = 200
QUERY_TIMEOUT_SECONDS = 30
REPORT_RELATIVE_DIR = Path("docs/analysis/harvester")
LLM_BATCH_SIZE = 20
_TWEET_ID_RE = re.compile(r"^[0-9]{1,32}$")
_SAFE_ERROR_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_VALID_STAGE_STATUSES = {"pending", "succeeded", "failed"}


class HealthCheckError(Exception):
    """A sanitized failure safe to expose in operator output."""

    def __init__(self, error_class: str, code: str):
        self.error_class = error_class
        self.code = code
        super().__init__(code)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HealthCheckError("invocation", "invalid_arguments")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _SafeArgumentParser(
        description="Inspect a bounded read-only cohort of production posts."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--latest", type=int)
    selector.add_argument("--tweet-id", action="append", dest="tweet_ids")
    parser.add_argument("--grace-hours", type=int)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--report",
        action="store_true",
        help="write an opt-in detailed Markdown evidence report",
    )
    args = parser.parse_args(argv)

    if args.latest is None and not args.tweet_ids:
        args.latest = DEFAULT_LATEST
    if args.latest is not None and not 1 <= args.latest <= MAX_COHORT:
        raise HealthCheckError("invocation", "invalid_arguments")
    if args.tweet_ids:
        if len(args.tweet_ids) > MAX_COHORT or len(set(args.tweet_ids)) != len(
            args.tweet_ids
        ):
            raise HealthCheckError("invocation", "invalid_arguments")
        if any(not _TWEET_ID_RE.fullmatch(tweet_id) for tweet_id in args.tweet_ids):
            raise HealthCheckError("invocation", "invalid_arguments")
    if args.grace_hours is not None and not 1 <= args.grace_hours <= 24 * 30:
        raise HealthCheckError("invocation", "invalid_arguments")
    if args.report and args.as_json:
        raise HealthCheckError("invocation", "invalid_arguments")
    return args


def _selected_cte(*, latest: int | None, tweet_ids: Sequence[str] | None) -> str:
    if tweet_ids:
        values = ",\n      ".join(
            f"('{tweet_id}', {ordinal})" for ordinal, tweet_id in enumerate(tweet_ids)
        )
        return f"""selected_ids(tweet_id, ordinal) AS (
    VALUES
      {values}
  ),
  selected AS (
    SELECT p.*, selected_ids.ordinal
    FROM posts p
    JOIN selected_ids ON selected_ids.tweet_id = p.tweet_id
    ORDER BY selected_ids.ordinal
  )"""

    assert latest is not None
    return f"""selected AS (
    SELECT
      p.*,
      ROW_NUMBER() OVER (
        ORDER BY p.fetched_at DESC, p.tweet_id DESC
      ) - 1 AS ordinal
    FROM posts p
    ORDER BY p.fetched_at DESC, p.tweet_id DESC
    LIMIT {latest}
  )"""


def build_query(
    *,
    latest: int | None,
    tweet_ids: Sequence[str] | None,
    detailed: bool = False,
) -> str:
    """Build one fixed, bounded, read-only PostgreSQL snapshot query."""

    selected_cte = _selected_cte(latest=latest, tweet_ids=tweet_ids)
    post_detail_fields = ""
    brand_detail_fields = ""
    discourse_detail_fields = ""
    if detailed:
        post_detail_fields = """,
        'author_id', p.author_id,
        'author_handle', p.author_handle,
        'author_name', p.author_name,
        'source_query_id', p.source_query_id,
        'created_at', p.created_at,
        'text', p.text,
        'lang', p.lang,
        'lang_detected', p.lang_detected,
        'text_en', p.text_en,
        'text_zh_cn', p.text_zh_cn,
        'commentary_en', p.commentary_en,
        'commentary_zh_cn', p.commentary_zh_cn,
        'tweet_url', COALESCE(p.tweet_url, p.tweet_twitter_url),
        'like_count', p.like_count,
        'retweet_count', p.retweet_count,
        'reply_count', p.reply_count,
        'quote_count', p.quote_count,
        'view_count', p.view_count,
        'metrics_refreshed_at', p.metrics_refreshed_at,
        'translation_attempts', es.translation_attempts,
        'translation_first_attempt_at', es.translation_first_attempt_at,
        'translation_last_attempt_at', es.translation_last_attempt_at,
        'translation_next_attempt_at', es.translation_next_attempt_at,
        'classification_attempts', es.classification_attempts,
        'classification_first_attempt_at', es.classification_first_attempt_at,
        'classification_last_attempt_at', es.classification_last_attempt_at,
        'classification_next_attempt_at', es.classification_next_attempt_at,
        'enrichment_created_at', es.created_at,
        'enrichment_updated_at', es.updated_at,
        'unsanctioned_flags', (
          SELECT jsonb_build_object(
            'flags', uf.flags,
            'flag_set', uf.flag_set,
            'evidence', uf.evidence,
            'decided_at', uf.decided_at
          )
          FROM posts_unsanctioned_flags uf
          WHERE uf.post_id = p.tweet_id
        )"""
        brand_detail_fields = """,
              'weight', pb.weight,
              'mentions', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'source', mention.source,
                    'raw_token', mention.raw_token,
                    'mentioned_at', mention.mentioned_at
                  )
                  ORDER BY mention.source, mention.mentioned_at
                )
                FROM posts_brands_mentions mention
                WHERE mention.post_id = p.tweet_id
                  AND mention.brand_id = pb.brand_id
              ), '[]'::jsonb)"""
        discourse_detail_fields = """,
                    'china_nationalism', discourse.china_nationalism,
                    'us_nationalism', discourse.us_nationalism"""
    return f"""BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '20s';
WITH
  {selected_cte},
  post_rows AS (
    SELECT
      p.ordinal,
      jsonb_build_object(
        'tweet_id', p.tweet_id,
        'fetched_at', p.fetched_at{post_detail_fields},
        'age_seconds', CASE
          WHEN es.created_at IS NULL THEN NULL
          ELSE GREATEST(
            0,
            FLOOR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - es.created_at)))
          )::bigint
        END,
        'has_text', NULLIF(BTRIM(p.text), '') IS NOT NULL,
        'has_lang_detected', NULLIF(BTRIM(p.lang_detected), '') IS NOT NULL,
        'has_text_en', NULLIF(BTRIM(p.text_en), '') IS NOT NULL,
        'has_text_zh_cn', NULLIF(BTRIM(p.text_zh_cn), '') IS NOT NULL,
        'translation_status', es.translation_status,
        'translation_error_code', es.translation_error_code,
        'classification_status', es.classification_status,
        'classification_error_code', es.classification_error_code,
        'brands', COALESCE((
          SELECT jsonb_agg(
            jsonb_build_object(
              'brand_id', pb.brand_id{brand_detail_fields},
              'signals', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'post_type', signal.post_type_key,
                    'sentiment', signal.sentiment
                  )
                  ORDER BY signal.post_type_key, signal.sentiment
                )
                FROM posts_brands_signals signal
                WHERE signal.post_id = p.tweet_id
                  AND signal.brand_id = pb.brand_id
              ), '[]'::jsonb),
              'discourses', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'discourse', discourse.discourse_key,
                    'act_id', discourse.act_id{discourse_detail_fields}
                  )
                  ORDER BY discourse.discourse_key, discourse.act_id
                )
                FROM posts_brands_discourse discourse
                WHERE discourse.post_id = p.tweet_id
                  AND discourse.brand_id = pb.brand_id
              ), '[]'::jsonb)
            )
            ORDER BY pb.brand_id
          )
          FROM posts_brands pb
          WHERE pb.post_id = p.tweet_id
        ), '[]'::jsonb)
      ) AS post_data
    FROM selected p
    LEFT JOIN post_enrichment_states es ON es.post_id = p.tweet_id
  )
SELECT jsonb_build_object(
  'transaction_read_only', current_setting('transaction_read_only'),
  'posts', COALESCE(
    jsonb_agg(post_data ORDER BY ordinal),
    '[]'::jsonb
  )
)::text
FROM post_rows;
COMMIT;"""


def build_command(sql: str) -> list[str]:
    return [
        "render",
        "psql",
        DATABASE_RESOURCE,
        "--command",
        sql,
        "--output",
        "text",
        "--",
        "--no-align",
        "--tuples-only",
        "--quiet",
        "--set=ON_ERROR_STOP=1",
    ]


def parse_snapshot(stdout: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            value = json.loads(stripped)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get("posts"), list):
            candidates.append(value)
    if len(candidates) != 1:
        raise HealthCheckError("transport", "render_output_invalid")
    return candidates[0]


def execute_query(
    sql: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = build_command(sql)
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HealthCheckError("transport", "render_timeout") from None
    except (FileNotFoundError, OSError):
        raise HealthCheckError("transport", "render_unavailable") from None
    if result.returncode != 0:
        raise HealthCheckError("transport", "render_command_failed")
    return parse_snapshot(result.stdout)


def load_grace_hours() -> int:
    try:
        import yaml
    except ImportError:
        raise HealthCheckError("configuration", "config_invalid") from None

    try:
        repo_root = Path(__file__).resolve().parents[4]
        data = yaml.safe_load((repo_root / "config.yaml").read_text()) or {}
        value = data["harvest"]["enrichment"]["max_age_hours"]
        if isinstance(value, bool):
            raise TypeError
        grace_hours = int(value)
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError):
        raise HealthCheckError("configuration", "config_invalid") from None
    if not 1 <= grace_hours <= 24 * 30:
        raise HealthCheckError("configuration", "config_invalid")
    return grace_hours


def _safe_error_code(value: Any) -> str | None:
    if isinstance(value, str) and _SAFE_ERROR_CODE_RE.fullmatch(value):
        return value
    return None


def _reason(
    stage: str,
    reason: str,
    *,
    brand_id: Any = None,
    error_code: Any = None,
) -> dict[str, str]:
    result = {"stage": stage, "reason": reason}
    if isinstance(brand_id, str) and brand_id:
        result["brand_id"] = brand_id[:128]
    safe_error_code = _safe_error_code(error_code)
    if safe_error_code:
        result["error_code"] = safe_error_code
    return result


def _stage_reasons(
    row: dict[str, Any], *, stage: str, grace_seconds: int
) -> list[dict[str, str]]:
    status_key = f"{stage}_status"
    error_key = f"{stage}_error_code"
    status = row.get(status_key)
    if status is None:
        return []
    if status not in _VALID_STAGE_STATUSES:
        return [_reason(stage, "invalid_status")]
    if status == "failed":
        return [_reason(stage, "failed", error_code=row.get(error_key))]
    if status == "pending":
        age_seconds = row.get("age_seconds")
        if not isinstance(age_seconds, (int, float)):
            return [_reason(stage, "pending_age_unknown")]
        if age_seconds > grace_seconds:
            return [_reason(stage, "pending_overdue")]
    return []


def _evaluate_post(row: dict[str, Any], *, grace_hours: int) -> dict[str, Any]:
    tweet_id = str(row.get("tweet_id") or "")
    translation_status = row.get("translation_status") or "missing"
    classification_status = row.get("classification_status") or "missing"
    brands = row.get("brands") if isinstance(row.get("brands"), list) else []
    reasons: list[dict[str, str]] = []

    if not tweet_id:
        reasons.append(_reason("persistence", "missing_tweet_id"))
    if not row.get("fetched_at"):
        reasons.append(_reason("persistence", "missing_fetched_at"))
    if not row.get("has_text"):
        reasons.append(_reason("persistence", "missing_text"))
    if (
        row.get("translation_status") is None
        or row.get("classification_status") is None
    ):
        reasons.append(_reason("persistence", "missing_enrichment_state"))
    if not brands:
        reasons.append(_reason("persistence", "missing_brand"))

    grace_seconds = grace_hours * 60 * 60
    reasons.extend(
        _stage_reasons(row, stage="translation", grace_seconds=grace_seconds)
    )
    reasons.extend(
        _stage_reasons(row, stage="classification", grace_seconds=grace_seconds)
    )

    if row.get("translation_status") == "succeeded":
        for field, reason in (
            ("has_lang_detected", "missing_lang_detected"),
            ("has_text_en", "missing_text_en"),
            ("has_text_zh_cn", "missing_text_zh_cn"),
        ):
            if not row.get(field):
                reasons.append(_reason("translation", reason))

    if row.get("classification_status") == "succeeded":
        for brand in brands:
            if not isinstance(brand, dict):
                reasons.append(_reason("classification", "invalid_brand"))
                continue
            brand_id = brand.get("brand_id")
            if not isinstance(brand_id, str) or not brand_id:
                reasons.append(_reason("classification", "missing_brand_id"))
                continue
            signals = (
                brand.get("signals") if isinstance(brand.get("signals"), list) else []
            )
            discourses = (
                brand.get("discourses")
                if isinstance(brand.get("discourses"), list)
                else []
            )
            if not signals:
                reasons.append(
                    _reason("classification", "missing_signal", brand_id=brand_id)
                )
            for signal in signals:
                if not isinstance(signal, dict) or not signal.get("post_type"):
                    reasons.append(
                        _reason(
                            "classification", "missing_post_type", brand_id=brand_id
                        )
                    )
                if not isinstance(signal, dict) or not signal.get("sentiment"):
                    reasons.append(
                        _reason(
                            "classification", "missing_sentiment", brand_id=brand_id
                        )
                    )
            if not discourses:
                reasons.append(
                    _reason("classification", "missing_discourse", brand_id=brand_id)
                )

    if reasons:
        state = "unhealthy"
    elif "pending" in {translation_status, classification_status}:
        state = "pending"
    else:
        state = "complete"
    return {
        "tweet_id": tweet_id,
        "fetched_at": row.get("fetched_at"),
        "state": state,
        "translation_status": translation_status,
        "classification_status": classification_status,
        "brand_count": len(brands),
        "reasons": reasons,
    }


def _missing_post(tweet_id: str) -> dict[str, Any]:
    return {
        "tweet_id": tweet_id,
        "state": "unhealthy",
        "translation_status": "missing",
        "classification_status": "missing",
        "brand_count": 0,
        "reasons": [_reason("persistence", "missing_post")],
    }


def _error_payload(error_class: str, code: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "error": {"class": error_class, "code": code},
    }


def evaluate_snapshot(
    snapshot: dict[str, Any],
    *,
    latest: int | None,
    requested_ids: Sequence[str] | None,
    grace_hours: int,
) -> tuple[dict[str, Any], int]:
    if snapshot.get("transaction_read_only") != "on":
        return _error_payload("query", "transaction_not_read_only"), 2
    rows = snapshot.get("posts")
    if not isinstance(rows, list):
        return _error_payload("query", "snapshot_invalid"), 2

    returned_tweet_ids = [
        str(row.get("tweet_id") or "") for row in rows if isinstance(row, dict)
    ]
    evaluated_by_id = {
        post["tweet_id"]: post
        for post in (
            _evaluate_post(row, grace_hours=grace_hours)
            for row in rows
            if isinstance(row, dict)
        )
    }
    if requested_ids is not None:
        cohort_tweet_ids = list(requested_ids)
        posts = [
            evaluated_by_id.get(tweet_id, _missing_post(tweet_id))
            for tweet_id in cohort_tweet_ids
        ]
        missing_tweet_ids = [
            tweet_id for tweet_id in cohort_tweet_ids if tweet_id not in evaluated_by_id
        ]
        mode = "exact"
    else:
        cohort_tweet_ids = returned_tweet_ids
        posts = [evaluated_by_id[tweet_id] for tweet_id in cohort_tweet_ids]
        missing_tweet_ids = []
        mode = "latest"

    summary = {
        "total": len(posts),
        "complete": sum(post["state"] == "complete" for post in posts),
        "pending": sum(post["state"] == "pending" for post in posts),
        "unhealthy": sum(post["state"] == "unhealthy" for post in posts),
    }
    unhealthy = summary["total"] == 0 or summary["unhealthy"] > 0
    if unhealthy:
        status = "unhealthy"
        regression_gate = "failed"
    elif summary["pending"]:
        status = "healthy_with_pending"
        regression_gate = "inconclusive"
    else:
        status = "healthy"
        regression_gate = "complete"
    payload = {
        "schema_version": 1,
        "status": status,
        "regression_gate": regression_gate,
        "mode": mode,
        "database_resource": DATABASE_RESOURCE,
        "latest_limit": latest,
        "grace_hours": grace_hours,
        "transaction_read_only": True,
        "summary": summary,
        "cohort_tweet_ids": cohort_tweet_ids,
        "returned_tweet_ids": returned_tweet_ids,
        "missing_tweet_ids": missing_tweet_ids,
        "posts": posts,
    }
    return payload, 1 if unhealthy else 0


def _render_human(payload: dict[str, Any]) -> str:
    if payload.get("status") == "error":
        error = payload["error"]
        return f"harvester-health error class={error['class']} code={error['code']}"
    summary = payload["summary"]
    lines = [
        (
            "harvester-health "
            f"status={payload['status']} "
            f"regression_gate={payload['regression_gate']} "
            f"mode={payload['mode']} "
            f"grace_hours={payload['grace_hours']} "
            f"total={summary['total']} "
            f"complete={summary['complete']} "
            f"pending={summary['pending']} "
            f"unhealthy={summary['unhealthy']}"
        )
    ]
    for post in payload["posts"]:
        reason_text = (
            ",".join(
                ":".join(
                    part
                    for part in (
                        reason["stage"],
                        reason["reason"],
                        reason.get("brand_id"),
                        reason.get("error_code"),
                    )
                    if part
                )
                for reason in post["reasons"]
            )
            or "-"
        )
        lines.append(
            f"tweet={post['tweet_id']} "
            f"state={post['state']} "
            f"translation={post['translation_status']} "
            f"classification={post['classification_status']} "
            f"brands={post['brand_count']} "
            f"reasons={reason_text}"
        )
    return "\n".join(lines)


def _load_report_config(repo_root: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        raise HealthCheckError("configuration", "config_invalid") from None
    try:
        data = yaml.safe_load((repo_root / "config.yaml").read_text()) or {}
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        raise HealthCheckError("configuration", "config_invalid") from None
    if not isinstance(data, dict):
        raise HealthCheckError("configuration", "config_invalid")
    return data


def _prompt_builders(repo_root: Path) -> tuple[Callable[..., str], Callable[..., str]]:
    inserted = str(repo_root) not in sys.path
    if inserted:
        sys.path.insert(0, str(repo_root))
    try:
        from x_monitor.attribution import build_batch_pragmatics_full_prompt
        from x_monitor.translator import build_pragmatics_translation_prompt
    except (ImportError, OSError):
        raise HealthCheckError("report", "prompt_reconstruction_failed") from None
    finally:
        if inserted:
            try:
                sys.path.remove(str(repo_root))
            except ValueError:
                pass
    return build_pragmatics_translation_prompt, build_batch_pragmatics_full_prompt


def build_request_reconstructions(
    rows: Sequence[dict[str, Any]],
    *,
    repo_root: Path,
    config_data: dict[str, Any] | None = None,
    prompt_builders: tuple[Callable[..., str], Callable[..., str]] | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct current-code request kwargs without creating a client."""

    data = config_data if config_data is not None else _load_report_config(repo_root)
    llm = data.get("llm") if isinstance(data, dict) else None
    if not isinstance(llm, dict):
        raise HealthCheckError("configuration", "config_invalid")
    translator_model = llm.get("translator_model")
    classifier_model = llm.get("classifier_model")
    if not isinstance(translator_model, str) or not isinstance(
        classifier_model, str
    ):
        raise HealthCheckError("configuration", "config_invalid")

    if prompt_builders is None:
        prompt_builders = _prompt_builders(repo_root)
    translation_builder, classification_builder = prompt_builders

    tweets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tweet_id = str(row.get("tweet_id") or "")
        source_text = row.get("text")
        if not tweet_id or not isinstance(source_text, str) or not source_text:
            continue
        brands = row.get("brands") if isinstance(row.get("brands"), list) else []
        brand_ids = [
            brand["brand_id"]
            for brand in brands
            if isinstance(brand, dict)
            and isinstance(brand.get("brand_id"), str)
            and brand.get("brand_id")
        ]
        tweets.append(
            {"tweet_id": tweet_id, "text": source_text, "brand_ids": brand_ids}
        )

    calls: list[dict[str, Any]] = []
    for start in range(0, len(tweets), LLM_BATCH_SIZE):
        batch = tweets[start : start + LLM_BATCH_SIZE]
        batch_index = start // LLM_BATCH_SIZE + 1
        try:
            translation_prompt = translation_builder(batch, ["en", "zh_cn"])
        except Exception:  # noqa: BLE001 - sanitize the prompt-builder boundary
            raise HealthCheckError(
                "report", "prompt_reconstruction_failed"
            ) from None
        translation_max_tokens = min(65536, max(16384, 1000 * len(batch)))
        calls.append(
            {
                "stage": "translation",
                "historical_wire_call": False,
                "evidence_class": "current_code_reconstruction",
                "batch_index": batch_index,
                "tweet_ids": [tweet["tweet_id"] for tweet in batch],
                "call_site": (
                    "monitor.cycle.CycleRunner._run_post_fetch -> "
                    "x_monitor.translator.translate_batch_pragmatics"
                ),
                "known_request_kwargs": {
                    "model": translator_model,
                    "max_tokens": translation_max_tokens,
                    "messages": [{"role": "user", "content": translation_prompt}],
                },
                "runtime_only_kwargs": {
                    "thinking": {
                        "status": "unavailable",
                        "reason": (
                            "resolved from production role-specific environment at "
                            "call time and not persisted"
                        ),
                    }
                },
            }
        )

        kept = [tweet for tweet in batch if tweet["brand_ids"]]
        if not kept:
            continue
        try:
            classification_prompt = classification_builder(kept)
        except Exception:  # noqa: BLE001 - sanitize the prompt-builder boundary
            raise HealthCheckError(
                "report", "prompt_reconstruction_failed"
            ) from None
        calls.append(
            {
                "stage": "classification",
                "historical_wire_call": False,
                "evidence_class": "current_code_reconstruction",
                "batch_index": batch_index,
                "tweet_ids": [tweet["tweet_id"] for tweet in kept],
                "call_site": (
                    "monitor.cycle.CycleRunner._run_post_fetch -> "
                    "x_monitor.attribution.classify_batch_pragmatics_full"
                ),
                "known_request_kwargs": {
                    "model": classifier_model,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": classification_prompt}],
                },
                "runtime_only_kwargs": {
                    "thinking": {
                        "status": "unavailable",
                        "reason": (
                            "resolved from production classifier environment at call "
                            "time and not persisted"
                        ),
                    }
                },
            }
        )
    return calls


def _code_block(language: str, value: str) -> str:
    longest_run = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}{language}\n{value.rstrip()}\n{fence}"


def _json_block(value: Any) -> str:
    return _code_block(
        "json", json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    )


def _markdown_cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _table(rows: Sequence[tuple[Any, Any]]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    lines.extend(
        f"| {_markdown_cell(key)} | {_markdown_cell(value)} |" for key, value in rows
    )
    return "\n".join(lines)


def _post_report_section(
    row: dict[str, Any], health: dict[str, Any], ordinal: int
) -> str:
    tweet_id = str(row.get("tweet_id") or "")
    metadata = _table(
        [
            ("Health state", health.get("state")),
            ("Translation status", health.get("translation_status")),
            ("Classification status", health.get("classification_status")),
            ("Author", row.get("author_handle")),
            ("Author ID", row.get("author_id")),
            ("Source query", row.get("source_query_id")),
            ("Tweet created", row.get("created_at")),
            ("Fetched", row.get("fetched_at")),
            ("Tweet URL", row.get("tweet_url")),
            ("Source language", row.get("lang")),
            ("Detected language", row.get("lang_detected")),
            ("Likes", row.get("like_count")),
            ("Reposts", row.get("retweet_count")),
            ("Replies", row.get("reply_count")),
            ("Quotes", row.get("quote_count")),
            ("Views", row.get("view_count")),
            ("Metrics refreshed", row.get("metrics_refreshed_at")),
        ]
    )
    enrichment = _table(
        [
            ("Translation attempts", row.get("translation_attempts")),
            ("Translation first attempt", row.get("translation_first_attempt_at")),
            ("Translation last attempt", row.get("translation_last_attempt_at")),
            ("Translation next attempt", row.get("translation_next_attempt_at")),
            ("Translation error code", row.get("translation_error_code")),
            ("Classification attempts", row.get("classification_attempts")),
            (
                "Classification first attempt",
                row.get("classification_first_attempt_at"),
            ),
            (
                "Classification last attempt",
                row.get("classification_last_attempt_at"),
            ),
            (
                "Classification next attempt",
                row.get("classification_next_attempt_at"),
            ),
            ("Classification error code", row.get("classification_error_code")),
            ("State created", row.get("enrichment_created_at")),
            ("State updated", row.get("enrichment_updated_at")),
        ]
    )

    parts = [
        f"## Post {ordinal}: `{tweet_id}`",
        "",
        metadata,
        "",
        "### Health findings",
        "",
        _json_block(health.get("reasons") or []),
        "",
        "### Full source text",
        "",
        _code_block("text", str(row.get("text") or "")),
        "",
        "### Persisted translations and commentary",
        "",
        "English translation:",
        "",
        _code_block("text", str(row.get("text_en") or "")),
        "",
        "Simplified Chinese translation:",
        "",
        _code_block("text", str(row.get("text_zh_cn") or "")),
        "",
        "English commentary:",
        "",
        _code_block("text", str(row.get("commentary_en") or "")),
        "",
        "Simplified Chinese commentary:",
        "",
        _code_block("text", str(row.get("commentary_zh_cn") or "")),
        "",
        "### Durable enrichment state",
        "",
        enrichment,
        "",
        "### Per-brand findings",
        "",
    ]
    brands = row.get("brands") if isinstance(row.get("brands"), list) else []
    if not brands:
        parts.append("No persisted brand rows.")
    for brand in brands:
        if not isinstance(brand, dict):
            continue
        parts.extend(
            [
                f"#### `{brand.get('brand_id') or 'missing-brand-id'}`",
                "",
                _table([("Weight", brand.get("weight"))]),
                "",
                "Mentions:",
                "",
                _json_block(brand.get("mentions") or []),
                "",
                "Post types and sentiment:",
                "",
                _json_block(brand.get("signals") or []),
                "",
                "Discourse and nationalism:",
                "",
                _json_block(brand.get("discourses") or []),
                "",
            ]
        )
    parts.extend(
        [
            "### Unsanctioned-flag evidence",
            "",
            _json_block(row.get("unsanctioned_flags")),
        ]
    )
    return "\n".join(parts)


def _missing_post_report_section(
    tweet_id: str, health: dict[str, Any], ordinal: int
) -> str:
    return "\n".join(
        [
            f"## Post {ordinal}: `{tweet_id}`",
            "",
            _table(
                [
                    ("Health state", health.get("state")),
                    ("Translation status", health.get("translation_status")),
                    ("Classification status", health.get("classification_status")),
                ]
            ),
            "",
            "### Health findings",
            "",
            _json_block(health.get("reasons") or []),
            "",
            (
                "No persisted post row was returned for this requested exact-cohort "
                "tweet ID, so source, translation, enrichment, brand, discourse, "
                "and flag evidence is unavailable."
            ),
        ]
    )


def render_detailed_report(
    snapshot: dict[str, Any],
    payload: dict[str, Any],
    *,
    sql: str,
    invocation: str,
    generated_at: datetime,
    repo_root: Path,
    request_reconstructions: Sequence[dict[str, Any]],
    script_source: str,
    script_sha256: str,
    repo_commit: str,
    python_version: str,
) -> str:
    """Render a durable, full-detail Markdown evidence report."""

    summary = payload["summary"]
    rows = snapshot.get("posts") if isinstance(snapshot.get("posts"), list) else []
    health_by_id = {
        str(post.get("tweet_id") or ""): post
        for post in payload.get("posts", [])
        if isinstance(post, dict)
    }
    parts = [
        "---",
        "title: Harvester latest-N health report",
        f"generated_at: {generated_at.isoformat()}",
        f"database_resource: {DATABASE_RESOURCE}",
        f"cohort_mode: {payload.get('mode')}",
        f"cohort_size: {summary.get('total')}",
        f"status: {payload.get('status')}",
        "database_access: read-only",
        f"checker_source_sha256: {script_sha256}",
        f"repo_commit: {repo_commit}",
        "---",
        "",
        "# Harvester latest-N health report",
        "",
        (
            "This report captures one bounded snapshot of persisted production "
            "post-fetch health. It is a diagnostic artifact, not a harvest, "
            "repair, retry, re-enrichment, or provider probe."
        ),
        "",
        "## Summary",
        "",
        _table(
            [
                ("Overall status", payload.get("status")),
                ("Regression gate", payload.get("regression_gate")),
                ("Cohort mode", payload.get("mode")),
                ("Total posts", summary.get("total")),
                ("Complete", summary.get("complete")),
                ("Pending", summary.get("pending")),
                ("Unhealthy", summary.get("unhealthy")),
                ("Grace period (hours)", payload.get("grace_hours")),
                ("Transaction read-only", payload.get("transaction_read_only")),
            ]
        ),
        "",
        "Ordered cohort tweet IDs:",
        "",
        _json_block(payload.get("cohort_tweet_ids") or []),
        "",
        "## Methodology and safety",
        "",
        (
            "The checker made one `render psql` call to the configured production "
            "database resource. The selected cohort was bounded before related "
            "facts were joined. The transaction declared read-only mode, applied "
            "statement/lock/idle timeouts, and returned the transaction mode in "
            "the same snapshot. No production row was mutated."
        ),
        "",
        "The checker did not run harvesting, call TwitterAPI, or create an LLM client.",
        "",
        "Invocation:",
        "",
        _code_block("shell", invocation),
        "",
        "## LLM call evidence",
        "",
        "### Calls made by this health checker",
        "",
        _json_block([]),
        "",
        "### Current-code LLM request reconstructions",
        "",
        (
            "The following entries contain the verbatim prompt strings produced "
            "by the current pure prompt builders for this selected cohort and the "
            "request kwargs deterministically known from source-controlled code. "
            "They are not historical wire evidence. Production does not persist "
            "historical prompt payloads, response payloads, retry count, original "
            "batch membership, or runtime-resolved `thinking`; unavailable values "
            "are labeled instead of inferred."
        ),
        "",
    ]
    if request_reconstructions:
        for call in request_reconstructions:
            parts.extend(
                [
                    (
                        f"#### {call.get('stage', 'unknown').title()} batch "
                        f"{call.get('batch_index', '?')}"
                    ),
                    "",
                    _json_block(call),
                    "",
                ]
            )
    else:
        parts.extend(
            [
                (
                    "No current-code request is reconstructed because the selected "
                    "cohort contains no non-empty source text eligible for enrichment."
                ),
                "",
            ]
        )

    rows_by_id = {
        str(row.get("tweet_id") or ""): row
        for row in rows
        if isinstance(row, dict)
    }
    parts.extend(["# Per-post evidence", ""])
    for ordinal, tweet_id_value in enumerate(payload.get("cohort_tweet_ids", []), 1):
        tweet_id = str(tweet_id_value)
        health = health_by_id.get(tweet_id, _missing_post(tweet_id))
        row = rows_by_id.get(tweet_id)
        if row is None:
            section = _missing_post_report_section(tweet_id, health, ordinal)
        else:
            section = _post_report_section(row, health, ordinal)
        parts.extend([section, ""])

    parts.extend(
        [
            "# Reproducibility appendix",
            "",
            "## Exact read-only SQL",
            "",
            _code_block("sql", sql),
            "",
            "## Checker implementation",
            "",
            _table(
                [
                    (
                        "Checker path",
                        ".claude/skills/harvester-latest-n-health-check/scripts/check.py",
                    ),
                    ("Checker file-content SHA-256", script_sha256),
                    ("Repository commit", repo_commit),
                    ("Python version", python_version),
                    ("Repository root", repo_root),
                ]
            ),
            "",
            (
                "The complete checker source used to render this artifact follows. "
                "It includes cohort selection, health rules, SQL, request "
                "reconstruction, report rendering, atomic write behavior, and "
                "stable error handling."
            ),
            "",
            _code_block("python", script_source),
            "",
        ]
    )
    return "\n".join(parts)


def write_report_atomic(
    report: str, *, repo_root: Path, generated_at: datetime
) -> Path:
    report_dir = repo_root / REPORT_RELATIVE_DIR
    filename = (
        generated_at.strftime("%Y-%m-%d-%H%M%S")
        + "-harvester-latest-n-health-report.md"
    )
    target = report_dir / filename
    temporary: Path | None = None
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=report_dir,
            prefix=".harvester-report-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(report)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise HealthCheckError("report", "report_write_failed") from None
    return target


def _repo_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else "unavailable"


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    as_json = "--json" in raw_argv
    report_path: Path | None = None
    try:
        args = parse_args(raw_argv)
        configured_grace_hours = load_grace_hours()
        if args.grace_hours is not None and args.grace_hours > configured_grace_hours:
            raise HealthCheckError("invocation", "invalid_arguments")
        grace_hours = (
            args.grace_hours if args.grace_hours is not None else configured_grace_hours
        )
        sql = build_query(
            latest=args.latest,
            tweet_ids=args.tweet_ids,
            detailed=args.report,
        )
        snapshot = execute_query(sql, runner=runner)
        payload, exit_code = evaluate_snapshot(
            snapshot,
            latest=args.latest,
            requested_ids=args.tweet_ids,
            grace_hours=grace_hours,
        )
        if args.report and exit_code in {0, 1}:
            try:
                repo_root = Path(__file__).resolve().parents[4]
                script_path = Path(__file__).resolve()
                script_source = script_path.read_text()
                generated_at = datetime.now().astimezone()
                request_reconstructions = build_request_reconstructions(
                    snapshot["posts"], repo_root=repo_root
                )
                report = render_detailed_report(
                    snapshot,
                    payload,
                    sql=sql,
                    invocation=shlex.join(
                        [sys.executable, str(script_path), *raw_argv]
                    ),
                    generated_at=generated_at,
                    repo_root=repo_root,
                    request_reconstructions=request_reconstructions,
                    script_source=script_source,
                    script_sha256=hashlib.sha256(script_source.encode()).hexdigest(),
                    repo_commit=_repo_commit(repo_root),
                    python_version=sys.version.replace("\n", " "),
                )
                report_path = write_report_atomic(
                    report, repo_root=repo_root, generated_at=generated_at
                )
            except HealthCheckError:
                raise
            except OSError:
                raise HealthCheckError(
                    "report", "checker_source_unavailable"
                ) from None
            except Exception:  # noqa: BLE001 - sanitize the report boundary
                raise HealthCheckError("report", "report_generation_failed") from None
    except HealthCheckError as exc:
        payload = _error_payload(exc.error_class, exc.code)
        exit_code = 2

    if as_json:
        stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        target = stderr if exit_code == 2 else stdout
        target.write(_render_human(payload) + "\n")
        if report_path is not None:
            target.write(f"report={report_path}\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```
