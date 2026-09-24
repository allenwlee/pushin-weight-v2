# Rare-type extra-search query widening (2026-09-23)

Plan: `docs/plans/2026-09-23-070740-feat-rare-type-query-widening-research-plan.md`  
Provider: TwitterAPI.io `advanced_search` Latest, ON_DEMAND, `max_pages=1`, `max_retries=0`.  
Grok `x_keyword_search` used only for vocabulary, not hourly rates.  
No harvest enablement. No Post inserts. No secrets in this file.

Windows (completed UTC, both 15 minutes):

- W1: 2026-09-22 21:30–21:45
- W2: 2026-09-22 21:45–22:00

Two windows = 0.5 hour. Raw posts/hour = (W1+W2 count) / 0.5. Full pages are **censored lower bounds**.

## Candidates (harvest shape, outer parens, `min_faves:0`)

**A** — current `rare-types-v2-2026-09-22` (planner 420, rendered 464)

```text
(("I've joined" OR "I joined" OR "I left" OR "我加入了" OR "我离开了" OR "に入社" OR "を退職") (AI OR LLM OR "machine learning" OR OpenAI OR Anthropic) OR ("I've joined @deepseek_ai") OR ("we're hiring" ("research scientist" OR "ML engineer")) OR (("we'll be at" OR "tickets are live") ("AI conference" OR "AI summit")) OR (("apply by" OR "applications close") (hackathon OR fellowship) (AI OR LLM)) OR ("step 5 preview")) min_faves:0
```

**B** — broader action wording, AI context kept on personnel (planner 443, rendered 487)

```text
(("I've joined" OR "I joined" OR "I left" OR appointed OR 出任 OR 正式加入 OR 换帅 OR に入社 OR を退職) (AI OR LLM OR OpenAI OR Anthropic OR DeepSeek OR Qwen) OR ("we're hiring" OR hiring OR 招聘 OR 募集中) (engineer OR researcher OR intern) OR (speaking OR panel OR "we'll be at" OR 登壇) (AI OR LLM OR conference OR summit) OR ("applications open" OR apply OR 申请) (hackathon OR fellowship) OR (released OR introducing OR 开源 OR 发布) (model OR weights)) min_faves:0
```

**C** — B plus dropped AI co-occurrence on join/leave (planner 386, rendered 430)

```text
(("I've joined" OR "I joined" OR "I left" OR appointed OR 出任 OR 正式加入 OR 换帅 OR に入社 OR を退職) OR ("we're hiring" OR hiring OR 招聘 OR 募集中) (engineer OR researcher) OR (speaking OR panel OR "we'll be at" OR 登壇) (conference OR summit OR DevDay) OR ("applications open" OR apply OR 申请) (hackathon OR fellowship) OR (released OR introducing OR 开源 OR 发布) (model OR weights OR Preview)) min_faves:0
```

## TwitterAPI.io matched windows

| Cand | Window | Raw | Truncated | Credit est. | Relevant (text) | Uncertain | Junk |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| A | W1 | 2 | yes | 30 | 2 Step-5 Preview mentions | 0 | 0 |
| A | W2 | 1 | yes | 15 | 0 | 1 robotics reply | 0 |
| B | W1 | 20 | **full page** | 300 | ~5 (Claude Opus 5.5 intro, GPT-6 Sol/Luna release, FDE hiring, 开源 agent note, OpenAI agents panel) | ~4 | rest |
| B | W2 | 0 | no | 15 | 0 | 0 | 0 |
| C | W1 | 20 | **full page** | 300 | ~2 (Opus intro, WeatherNext) | 0 | ~18 “I left”/appointed personal |
| C | W2 | 20 | **full page** | 300 | ~0 | 1 退職 | rest personal/bot “I left” |

Credit estimate this batch: **960**. Cap was 6 pages.

Raw posts/hour (this half-hour only):

| Cand | Raw/hour | Notes |
| --- | ---: | --- |
| A | 6 | Sparse; both windows had leftover `has_more` with 1–2 hits (treat as weak truncation, not a mill page) |
| B | 40 | Burst: 20 then 0. W1 censored at 20. Hits 20–50 band but page-saturated |
| C | 80 | Theoretical one-page ceiling. Almost all junk |

Do not treat these as a 24-hour rate.

## Grok X search (vocabulary only)

- LithosAI “we're currently hiring for 4 engineering roles” / Machine Learning Engineer: **A misses** (needs exact `"we're hiring"` AND `"ML engineer"`). **B would match** `hiring` + `engineer`.
- DeepSeek CFO 正式加入 / 出任: Grok Latest found those ZH reports. **A misses** first-person-only 我加入了. **B includes 正式加入/出任**.
- Qwen 换帅: in B.
- `(speaking OR panel) Mistral` was noisy (Grok replies), not a clean event net.
- 开源 + MiMo/Qwen: found MiMo-V2.6-Pro / Qwen open-source chatter.

## Known-positive recovery vs burial

B recovers hiring-without-exact-phrase and ZH appointment wording, and finds real model-release posts. In W1 it also **fills the page** with `speaking`/`panel`/`released`/`apply` generic hits, so a rare first-person join in the same 15 minutes may never appear (20-result cap).

C’s 50–80/hour is duplicate “I left my ex / I left work” volume, not relevant discoveries.

## Recommendation

- **Do not enable extra search on `run_cycle`.**
- **Do not adopt C.**
- **Keep A as the sparse baseline** (~6 raw/hour here, high share of Step-5 mentions).
- **B is the useful research direction** for 20–50 raw/hour, but next string should keep AI/org context on join/leave **and** drop unquoted `speaking`, `panel`, `apply`, `released` (too generic). Re-test one tightened B' on new matched windows before changing production query code.
- Full-feature plan’s **$0.06/day** search cap cannot hold 20/hour (480 posts/day × 15 credits ≈ $0.072/day) or 50/hour ($0.18/day). Flag a budget-policy revision; do not silent-edit that plan in this research.

## Spend

Six ON_DEMAND pages. Estimated 960 credits (~$0.01). Invoice not captured.

Machine-local JSON: `/tmp/pw-widen/{A,B,C}-W{1,2}.json` (may vanish).
