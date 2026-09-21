# US vs China Nationalism Taxonomy on English X: Findings from Live Probes

### written by Grok 4.3

**Date:** 2026-06-29; addendum 2026-08-31  
**Context:** Updates to the x-monitor project's nationalist sentiment layer analysis for LLM brand discourse. The 2026-06-29 writeup treated sneakers/EV (Anta, Li-Ning) as the obvious next verticals. The 2026-08-31 addendum revises that: the transferable object is political-issue weather on industrial 出海 (AI, embodied AI, EV, batteries, DJI-class electronics), not consumer 潮/口碑. Sneakers do not pass the X-square test.

---

## Background and Evolution

The original research doc assumed the "nationalist sentiment layer" was primarily a Chinese-internet phenomenon (e.g., 弯道超车, sensitivity to 套壳/蒸馏, "China open-sources then others build their own").

Live X probes (using `x_keyword_search` and `x_semantic_search`, lang:en + lang:zh slices, focused on comparative posts about DeepSeek/Qwen/GLM/Kimi vs Claude/OpenAI/Grok, plus US-models-only runs) revealed:

- The layer is active and measurable on **English X** as well (~35-45% of relevant comparative posts, higher in policy/accusation threads).
- It cuts across the 4 post_type × sentiment matrix.
- ** Crucial asymmetry**: The data shapes for the US and China axes are **not the same**.

This has implications for the monitoring system: more precise filtering, targeting, and interpretation for Chinese LLM vendors (and future expansion to other brands).

---

## US Axis (us_nationalism)

In English X discourse around US models/brands, the "negative" or critical side is frequently **not pure hostility** but inward self-chastisement.

### Observed Patterns
- **constructive_critical_us**: Self-reflective criticism aimed at improvement ("we need to do better"). Common examples:
  - Hypocrisy: "Anthropic scraped the whole web for Claude. Now it's mad..."
  - Policy self-sabotage: "The US government is going to destroy the American AI industry... Meanwhile China ships open weights."
  - Calls for reflection: Memorial Day-style posts questioning if Americans still agree on core principles (democracy, free speech, etc.) that defined exceptionalism.
- **uncritical_us / blind_us**: Does appear, especially in US-models-only discourse (no China comparison):
  - Patriotic: "They are an American company, building in America! And to this Marine that means something."
  - "Grok stands alone in defending American lives... real patriotism."
  - Leadership claims: "America counters with its core strengths... US wins by out-innovating... frontier model leadership (still ahead on benchmarks)."
- **mild_pro**: Subtle positive acknowledgments ("still stronger in product polish," "has advantages in innovation").
- Strong hostile `anti_us` is present but less dominant in LLM-comparative threads than the constructive variety.

This aligns with psychological research on **blind patriotism** (uncritical) vs **constructive patriotism** (critical but attached, aimed at positive change).

When China is in the frame, US-positive signals are often qualified or paired with criticism. Pure blind pro_us emerges more when focusing on US models alone.

---

## China Axis (china_nationalism)

The same buckets do not map symmetrically.

### Observed Patterns (English X + Chinese X slices)
- **pro_cn**: External/competitive admiration for results:
  - "China is no longer quietly catching up... efficiency monster... serious challengers... good enough, improving fast, and in many cases much cheaper."
  - "shipped the playbook for building frontier-ish reasoning... open recipes compound."
  - "turning open-weight AI into a real pressure point for the West."
  - Chinese voices: technical pride ("工程上的创新... 给全世界参考"), successful deployments ("M3 ultra 512gb还是牛逼").
- **anti_cn**: Often geopolitical or systemic:
  - "theft is the only path", "progress only by intellectual theft."
  - Security: "legally obligated to provide root access... CCP can compel...", "sleeper agents", "govt sanctioned subversion."
  - Inherent risk framing rather than "fixable flaws."
- **constructive_critical_cn**: Rare/weak in English X. Criticism is more external/judgmental. Chinese X tends to defend under constraints rather than self-chastise.
- **mixed**: Common — acknowledge progress but flag risks ("efficient but still invasive...").

**Data shape on X**: More polarized "efficiency win" (pro) vs "inherent CCP/theft risk" (anti). Less inward "we (China) need to improve for legitimacy."

---

## Recommended Unified Taxonomy (Updated)

To reflect the asymmetry while keeping the structure practical for classification:

- **china_nationalism**: none / mild_pro / pro / constructive_critical / anti / mixed
- **us_nationalism**: none / mild_pro / pro / constructive_critical / anti / mixed

**zh_cn equivalents** (for prompts, UI, or Chinese vendor output):

- none (无)
- mild_pro (温和亲华 / 温和亲美)
- pro (亲华 / 亲美)
- constructive_critical (建设性批评)
- anti (反华 / 反美)
- mixed (混合)

**Notes on usage**:
- `mild_pro`: Subtle positive valence (e.g., noting quality/achievement without overt cheerleading). Distinct from full `pro`.
- `pro`: Clear positive attachment/celebration (efficiency wins for China; patriotic/leadership claims for US).
- `constructive_critical`: Engaged self-criticism for improvement (very common and distinctive on US side; rarer on China side).
- `anti`: Hostile or essentialist rejection (theft/system risk for China; irredeemable hostility for US).
- Use evidence quotes in prompts for accuracy.
- This is orthogonal to the 4 post_type × sentiment matrix.

**Combined interpretation examples**:
- constructive_critical + neutral: "US restrictions are self-defeating while China ships usable models."
- pro_cn + anti_us: "China's cheap open models expose US protectionism."
- anti_cn + neutral_us: "Chinese models carry sleeper risk regardless of cost."
- anti_cn + anti_us: "Both sides stole, but China does it via state compulsion."

---

## Probe Methodology and Sources

- **Tools**: `x_keyword_search` (advanced operators: lang:, since:, min_faves:, from:, quoted phrases, OR groups) and `x_semantic_search` (for nuanced stance).
- **Dates**: Focused on 2026-05/06 data (since:2026-01-01 or 2026-05-01 in calls).
- **Queries** (examples):
  - US criticism: "hypocrisy of Anthropic...", "US gov destroying American AI industry".
  - China positive: "praising Chinese AI models as efficiency monster / playbook".
  - Hostile: "Chinese models dangerous stolen fraud".
  - US-only (no China terms): positive praise for American AI, patriotism.
  - Chinese voices: lang:zh probes on performance, innovation defenses.
- **Findings validation**: Cross-checked with thread fetches for context. ~20-30 posts per major axis. Not exhaustive random sample but targeted for nationalist/comparative discourse.
- **Key observed posts** (examples):
  - US constructive: https://x.com/chenzeling4/status/2070189787349422534 (Anthropic hypocrisy).
  - US pro/patriotic: Posts praising "American company" pride, "real patriotism" for xAI/Grok, "US wins by out-innovating".
  - China pro: Efficiency/playbook posts (e.g., 20x cheaper narrative).
  - China anti: Sleeper/CCP legal obligation posts.
- **HF cross-check**: web_search confirmed Chinese open models leading downloads/trending, correlating with pro_cn spikes during US restriction talk.

---

## Implications for x-monitor (and Future Verticals)

- **Asymmetry handling**: Do not treat axes identically. US benefits from constructive_critical detection (inward, actionable for DevRel). China pro is often efficiency-focused (opportunity) vs anti (risk).
- **Targeting**: Filter/deprioritize strong anti (both sides). Prioritize none + mild_pro + hands_on/perf_compare.
- **Broader use (2026-06-29, superseded in part)**: For sneakers/EV (Anta, Li-Ning, etc.): pro_cn style = "潮" or efficiency wins; anti = risk/narrative attacks. The 2-axis + post_type works across verticals. **2026-08-31:** taxonomy transfer still holds for EV; sneakers/潮 is the wrong square and the wrong job. See addendum.
- **Prompts**: Add to per-post classifier. Use secondary account-level semantic search for sarcasm/context on flagged items.
- **DB/aggs**: Store as independent fields. Enable cross-tabs and "exclude strong nationalist" filters.
- **Value shift**: From pure mention volume ("走个量") to discourse interpretation. This writeup captures the evolved model.

---

**Scope delivered (2026-06-29)**: Replaced outdated "Chinese-specific" assumption with probe-backed asymmetry findings, unified taxonomy as specified, zh_cn terms, examples, and implications. Kept Chinese-source core intact. Only EN version.

---

## Addendum 2026-08-31: Next verticals, next language, product shape

### written by Grok 4.6

**Date:** 2026-08-31  
**Context:** Live X probes (`x_keyword_search` Top/Latest + `x_semantic_search`), last-30-days compact scan, and TAM sources (IEA Global EV Outlook 2026, Forbes China 跨国经营30强, SNE Research / CnEVPost H1 2026 cells, Counterpoint/SAG humanoid shipments, DataReportal/Statista X reach, Reuters Institute Korea news). Question: after LLM labs, which Chinese 出海 verticals have Anglo (then non-English) *target audiences on X*, and what product that implies.

This addendum does not change the 6-step nationalism taxonomy. It changes **what the taxonomy is for**.

---

### Product thesis (revises "future verticals")

PushinWeight is not generic overseas 口碑. It measures **whether a Chinese industrial brand is being talked about as a product or as a political object**, and which issue is doing the converting.

The buyer is overseas BD / government affairs / brand risk at a Chinese industrial HQ. The output is not "sentiment 62% negative." It is:

- share of posts that are political-object vs product
- which issue is carrying the week
- US-axis shape: `constructive_critical_us` ("we are going to lose this industry") vs `anti_cn` ("inherent CCP risk")
- whether Japan's 経済安保 register is turning on

Domestic analog: 蜜度 / 新浪舆情通 (political weather). Not 清博声量, not Brandwatch mention volume, not 小红书种草. Punchline for Chinese netizens: 国内看口碑，出海看许可。实体清单的前戏发生在推特上。

---

### Vertical ranking (supersedes sneakers/EV-as-潮)

LLM labs remain vertical 1: Anglo AI conversation is uniquely on X; the buyer conversation and the permission conversation are the same feed. Fold Kling / Hailuo / Wan into the lab set, not a new vertical.

| Priority | Vertical | Why it inherits the taxonomy | Skip / caveat |
|---|---|---|---|
| Keep | LLM / AI labs | Already shipping. Theft vs open weights vs export controls | — |
| Next | Embodied AI / humanoids (Unitree, UBTECH, Agibot, Fourier, Zhiyuan) | Same X neighborhood as labs + Tesla Optimus Twitter. DoD lists, military-civil fusion, GMO-as-Japan-distributor panic | Classifier reuse almost 1:1 |
| Then | Chinese EVs into Tesla Twitter (BYD, NIO, XPeng, Xiaomi Auto, Geely/Zeekr) | Auto chain ~36% of Forbes China 30 overseas-revenue increment. Tesla Twitter is X-native. US passenger door mostly shut; UK/AU/CA/Gulf English + global Tesla Twitter still matter | Not 懂车帝口碑 |
| Then | Batteries as the political twin (CATL, BYD cell) | UFLPA/Xinjiang, FEOC, "Chinese military company" lists, Wall Street underwriting. House Select Committee on CATL is not a cell review | Demand is Europe/NA/ME/AU, not JP/KR buyers |
| Then | DJI-class dual-use electronics | Product audience is YouTube/IG; **Anglo problem is X** (ban, geofencing, FCC, Ukraine diversion) | Keyword collisions: `$DJI` = Dow |
| Optional cash | Crypto exchanges (OKX, Binance, Bitget) | Most X-native of all; different customer | Only if sales motion can be crypto-vendor |
| Weak X | Anker-class portable energy | 96.6% overseas revenue — ideal *customer*, Amazon/Reddit/YouTube primary | Brand-health overlay, not the category |
| **Skip** | **Sneakers (Anta, Li-Ning)** | 2026-06-29 named these. IG/TikTok is the community; X is a press wire (Steph in Way of Wade). `pro_cn` = 潮 is consumer 口碑, not permission | Taxonomy *can* score it; the product should not |
| Skip | SHEIN/Temu, beauty, Labubu, gaming | X is memes. Purchase is TikTok/IG/Discord | Wrong square |

**Issue set that moves overseas sales** (stable, small):

| Vertical | Issues |
|---|---|
| AI / labs | theft vs open weights, export controls, "CCP can compel," dual-use |
| Embodied AI | same + DoD entity lists, military-civil fusion, weapons-on-dogs, JP 経済安保 |
| EV | tariffs, subsidy discrimination, safety-as-nationalism, "market invasion" |
| Batteries | UFLPA / Xinjiang, FEOC, military-company lists, Wall Street underwriting |
| DJI-class | bans, backdoors, FCC/geofencing, dual-use |

Live English X (late Aug 2026) that matches this layer, not product reviews:

- Unitree "Superman" ~1.2M views; Optimus clips ~950k; Grok: ~97% of H1 2026 humanoid shipments from Chinese firms; crypto pre-IPO ~$38B vs ~$9B banker case.
- BYD: Tesla Twitter sales tables; "if this were Tesla there would be thousands of comments"; Bloomberg "prove it overseas."
- CATL: House Select Committee investigation ~149k views.
- DJI: MTG geofencing/White House clip ~1.1M; flood-rescue FC200 ~1.1M.
- Japan: Sankei RACCO kei-EV ~639k views; Diet member Inose Naoki on Suzuki kei EV using BYD-related cells ("parasitic"); GMO × Unitree 経済安保 threads 40k–128k; Sumitomo Heavy humanoid-actuator clip ~858k.

---

### Next language after Anglo: Japanese, not Korean

TAM-first (Chinese 出海 *into that country*) does **not** pick JA or KO. Europe does (IEA 2025: Europe 3.77M NEVs, Germany 850k; Korea >200k; Japan ~100k / <3% of car sales). CATL overseas cell/ESS demand is Europe, North America, Middle East, Australia. Embodied-AI 2026 TAM: Europe $1.41B > Japan $0.27B > Korea $0.13B.

X-first (this product's constraint) picks Japan:

| Country | X users (2025 ad reach) | Rank | Adult / internet penetration |
|---|---|---|---|
| US (already Anglo) | ~100–105M | 1 | — |
| **Japan** | **71–74.5M** | **2** | **~64% of 18+** (DataReportal: 71.2M, 57.9% of population) |
| Germany | 17.4M | 7–8 | ~16% of internet users |
| Brazil | ~16–17M | ~8–9 | high Chinese EV *sales*, weaker political-X |
| **Korea** | **~10.8M** | **14** | Naver/Kakao/YouTube own the square |

Japan EV TAM for Chinese brands is a rounding error (BYD ~7,400 cars in Japan 2023–end-2025; RACCO target 10k orders in 2026). Japan still wins the listening product because X *is* the Japanese public square, and the RACCO / Unitree / 経済安保 argument is already the nationalism taxonomy with a third axis (industrial pride / 経済安保).

Korea: BYD is actually selling more units than in Japan (China outsold Japan in Korea's import ranking, Apr 2026). Still skip `lang:ko` on X. Korea's town square is a stack, not X:

| Layer | What it is | Analog |
|---|---|---|
| **YouTube** | Closest national square. Reuters Institute 2025: 50% of Koreans regularly get news on YouTube (global avg 30%). ~44 h/month. Martial-law week was decided here | Anglo X news |
| **Naver News comments** | Mass thermometer (KAIST: 110M comments / 20 years) | The replies |
| **커뮤니티 basket** | No Reddit-scale unifier. DC Inside ~3M DAU; Money Today 2026 scraped 19 boards (TheQoo, Instiz, DC, FMKorea, Ilbe, Bobaedream…) | Fight clubs |
| **Bobaedream** | Korean car board | Tesla Twitter for *product* EV talk |
| **Blind / Clien** | Workplace + tech | Battery competitor intel |
| KakaoTalk | 49.1M, 95% of population | Private utility, not public |
| X | ~10.4M, campus use skews female | Side room |

If a CATL/BYD client pulls Korea, harvest YouTube + Bobaedream + Naver comments. That is a different product.

Unconstrained by JA/KO: German is the TAM language after English (CATL Hungary, BYD EU). German X is usable, not Japan-grade. Portuguese/Spanish only if EV clients pull toward Brazil/Mexico sales. Listening-product order: English → Japanese → German. Not Korean.

---

### Chinese-netizen analogs (how to pitch)

Do not say "X 就是海外微博." That trains them to expect 热搜和粉丝.

| Their world | What it is | PushinWeight analog |
|---|---|---|
| 蜜度 / 新浪舆情通 | Weibo+政务：稳不稳 | Same *job* (政治天气), different square and issues |
| 人民网 / 新华舆情 | 涉政风险 | Closest: 许可风险，不是差评 |
| 清博 / 识微 / 新榜 | 声量、正负面 | Brandwatch cousins. Not this |
| 慧科 / 沃观 | 海外新闻抓取 | See the article; do not score the issue |
| 微博热搜 | 国内舆论主场 | Naive X analog. Half right |
| 知乎科技区 | 长帖撕模型 | AI Twitter, slow |
| 雪球 | 散户+产业资本 | Tesla Twitter / FinTwit |
| 汽车之家 / 懂车帝 | 车主口碑 | EV product talk. Not this |
| 观察者网评论区 | 民族叙事 | Domestic mirror of `pro_cn` / `anti_cn` |

Scars they already have: 华为实体清单, 大疆禁售, 新疆棉花, 光伏双反, 欧盟电动车反补贴, TikTok 法案, DeepSeek「抄袭」叙事.

Netizen line: 出海企业买到的海外舆情是差评和声量。真要命的是产品何时变成「中国威胁」。那个转换发生在 X 上，蜜度看不见，Brandwatch 读不懂建设性批美 vs 本质反华。

Buyer line: 你们已有蜜度看国内、Brandwatch 看海外声量。缺第三张图：议题热度 × 政治对象化率 × 美/中民族主义形态。只做关税、清单、劳工、国安四个开关；只做 X（加日本推特）；只做 EV / 电池 / 消费电子 / AI.

What not to analogize: 小红书/抖音 (货盘), 识微覆盖面 (they sell sources, we sell interpretation), 「海外版微博热搜」 (budgets land in marketing, then Brandwatch wins), 正负面百分比 (蜜度报表).

---

### Probe methodology (2026-08-31)

- **Tools:** `x_keyword_search` (lang:en / lang:ja / lang:ko / lang:de; Top then Latest), `x_semantic_search`, last30days compact, web_search for TAM and platform reach.
- **Noise learned:** Latest-mode is unusable for BYD/DJI/Anker (dealers, `$DJI` = Dow, people named Anker/DJI). Use Top + constrained co-tokens.
- **TAM sources:** IEA Global EV Outlook 2026; Forbes China 跨国经营30强 (2026-08-28); China Daily on Anker 96.6% overseas; SNE Research via CnEVPost H1 2026; Counterpoint/SAG humanoid H1 2026; HiQual 2026 country TAM; DataReportal Digital 2026 JP/KR; Statista/WPR X users; Reuters Institute Digital News Report Korea 2025; Korea Herald on DC Inside.
- **Does not claim:** exhaustive volume counts (X tools return samples, not totals); Korea product-EV TAM is "zero" (it is not; the X square is).

---

**Scope delivered (2026-08-31):** Recorded the vertical/market/pitch findings that grew out of the 2026-06-29 "sneakers/EV" aside. Taxonomy unchanged. Sneakers dropped. Product named as industrial political-issue weather. Next language after Anglo = Japanese. Korea square documented so `lang:ko` on X is not re-litigated without new evidence.

(End of addendum.)
