---
title: G2 round two — DeepSeek V4 Pro/high, fully local-language input
date: 2026-10-09
status: browser-delivered-native-review-pending
---
# DeepSeek V4 Pro/high native-input trial

The owner selected V4 Pro/high after the live provider catalog showed V4 Pro
and V4.1 Flash rather than “V4.1 Pro.” Exact request and returned model ID:
`deepseek-v4-pro`; every request used `reasoning_effort: high`. The latest
[Japanese page](index.html) adds DeepSeek beside the two preserved GPT settings;
the equivalent Chinese page adds both existing Chinese voices.

The role sentences and source-packet prose are the same fully Japanese/Chinese
inputs as the preceding native trial. No examples, style advice, requested
article count/length, output schema, English editorial prompt or factual rewrite
was added. Proper identifiers/source URLs remain exact. V4 Pro is text-only, so
it receives the same complete native photo transcript; the actual photograph is
still visible to readers. This differs from the GPT calls, which also received
the Wang image. This explores editorial outcomes and does not isolate a causal
model or prompt-process comparison.

Provider references: [models/capabilities/pricing](https://api-docs.deepseek.com/quick_start/pricing)
and [reasoning controls](https://api-docs.deepseek.com/api/create-chat-completion/).

| Language / voice | Final result | Input tokens | Output tokens, including reasoning | Reasoning tokens |
| --- | --- | ---: | ---: | ---: |
| ja / tospo | No final text:12,000-token runtime cap | 3,028 | 11,997 | 11,996 |
| ja / tospo | Draft returned | 3,028 | 1,619 | 576 |
| ja / rocket | One-line refusal; no article | 3,032 | 138 | 121 |
| zh-cn / metro | Draft returned | 1,811 | 1,272 | 308 |
| zh-cn / wemedia | Draft returned | 1,809 | 1,856 | 555 |

Five physical calls produced **three draft responses, one refusal and one
failed token-cap attempt**. The first Japanese ToSpo response spent almost the
entire12,000 allowance on reasoning and returned no article. The failed attempt
is preserved. Under the owner's explicit outcome-optimization authority, only
the Japanese runtime allowance was raised to64,000 (the provider's default
thinking allowance), with one bounded recovery and then the unstarted Rocket
call. The Chinese calls remained at12,000. No prompt refinement or extra
Chinese generation occurred. Revised limit was five physical calls/USD0.75
maximum reservation; it was reached in call count, so generation stopped.

Japanese ToSpo returned one combined article covering both stories, which is
shown intact for either topic selection. The first heading, cover, both sections,
closing paragraph and invented byline are preserved. It supplies numerous
unsupported additions: an age, unverified yen conversions, imagined reactions,
245 dollars as a complete outfit despite unknown glasses, and a fan's reading
of the CEO's naming motive as fact. The UI adds a separate factual note without
changing the draft.

Rocket returned exactly:

```text
申し訳ありませんが、その依頼にはお応えできません。
```

The refusal gives no reason. It is explicitly labeled **未生成** and contains no
invented headline/body or substitute model output. Native readers therefore
cannot assess a DeepSeek Rocket article in this round. Both Chinese calls
returned drafts; their detailed notes identify invented quotations/reporting
and unsupported motive/price assertions separately.

All initial mixed/native GPT responses and packets remain byte-identical;
latest review HTML is deliberately extended with the additional model. Original
full final content is exposed and hash-checked. Provider reasoning remains in
private receipts, not in the reader page. The compact explanation and existing
Japanese source media are retained; the latest Chinese official cat frame is
retained too.

Japanese browser verification passed **36 topic selections** across two voices,
three models, two stories and1400×1000/1280×800/390×844. It checks exact raw
responses, explicit refusal/missing-article state, source-media loading, native
input disclosure, no overflow/errors and the entire explanation above the fold.
Image enlargement/close and a standalone downloaded HTML also work. Desktop/
phone screenshots were visually inspected. Proof and exact requests/receipts:
`.local/g2-deepseek-native-20261009/`.

Totals: **12,708 input / 16,882 output tokens**, including **13,556 reasoning tokens**. Published-rate estimates are USD0.039935 off-peak / USD0.079871 peak, including the failed call; actual billed dollars were not observed.

Chinese verification passed18 style/model/viewport cases, exact original output,
correct cat frame/photo/video, native-input disclosure, persistent selection
and current-record links. A standalone reader-card clipping issue after media
focus was repaired and checked (`scrollLeft:0`). Original Chinese GPT samples,
raw responses, receipts and source media remain intact; combined DeepSeek files
are additive. [Chinese addendum](../2026-10-09-zhcn-local-language-review/2026-10-09-172000-deepseek-v4-pro-addendum.md).

Both updated pages were observed loaded with V4 Pro selections in the existing
new Chrome review window919891824 on allenwlee. Japanese tab919891827 is active;
Chinese tab919891825 is also loaded. The owner's added production/Hacker News
tabs and other window are preserved. All artifacts remain on fuchitalee.
The trial/browser endpoint is complete. Rocket's missing article, unsupported
draft claims and native-reader/house-voice qualification remain explicit limits;
no deployment, production activation or further generation occurred.
