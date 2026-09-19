# Gemini Commentary v3 — fresh100 source-grounded review

**Candidate:** `gemini_flex_commentary_v3`  
**Cohort:** frozen fresh100, 100 posts and 300 locale outputs  
**Scope:** every source post, supplied context entry, and `en` / `zh-cn` / `ja` output was read in bounded review chunks.

The complete per-source evidence is [`source-grounded-review-v1.json`](../../.context/model-task-20260917/gemini-commentary-v3-r113-fresh100-20260917-190000/source-grounded-review-v1.json), SHA-256 `c6340aff71d44a5f0918b0bbe6ad60f843691e1588340f6144c6560de9b929e9`. It is tied to the source-only packet SHA-256 `39333b81e0578cae6619f7ef77708161c044956df2263967a48fb6b2a97de825` and live-report SHA-256 `86f7f8e9ab7aab686e2838c5c3654d9e34e926525f99cb07b92924f1bf7752da`.

The candidate has **four confirmed erroneous source posts**: three material and one minor. All four affect the three locale outputs because they are the same explanation carried across locales.

| Post | Severity | Source-grounded finding |
| --- | --- | --- |
| `2100212362594705773` | Material | Transfers a separate local-parent speaker's four-model test to the source author. |
| `2100287941796933993` | Minor | Changes control of Hermes over SSH/Tailscale into controlling hardware. |
| `2100320116432830498` | Material | Transfers the quoted organisation's release announcement and "our first MoE" claim to a source author who posted only an emoji reaction. |
| `2100365704046289317` | Material | Recasts shipping a bug after switching models as a successful shipment and positive evidence. |

The other 96 posts have no confirmed source-bound semantic, attribution, uncertainty, numeric, locale, or coverage error. Context was allowed to explain thread relationships where it did not transfer context-speaker authorship or intent. Structural delivery was complete (100/100 requests; zero transport and structural failures; zero retries/fallbacks), but this was not used to infer semantic quality.

Receipt cost was `$0.03094585`. Provider `output_tokens` are reported here as **completion tokens including reasoning**: 63101 prompt + 138954 completion = 202055 total, with 117762 reasoning tokens already included in completion. Aggregate call latency was 544481 ms. This is diagnostic evidence only; it does not establish incumbent parity, qualification, or a production decision.
