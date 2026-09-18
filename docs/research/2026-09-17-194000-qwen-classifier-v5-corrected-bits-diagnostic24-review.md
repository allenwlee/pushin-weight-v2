---
title: Qwen classifier v5 corrected-bits diagnostic-24 review
date: 2026-09-17
type: experiment-review
---

# Qwen classifier v5 corrected-bits diagnostic-24 review

This is the wider diagnostic, not a qualification run. It evaluates the raw
responses against the frozen visible source packet and current taxonomy only.
It does not use historical owner answers as a gold set.

## Frozen run facts

- Contract: `.context/model-task-20260917/qwen-classification-v5-corrected-bits-diagnostic24-exception29/contract.json`, SHA-256 `802173bb4a10104c8ec7c3d063c7ddf9221a983050064d537d28db56c309c572`.
- This is distinct from the unused v4 diagnostic contract. It restored the independent content-axis and brand state-consistency checks *before* replacing the legacy output map. V3 and paid v4 did not receive those checks because their earlier prompt construction discarded appended text.
- Ten sequential Alibaba-only calls completed with `finish_reason=stop`; no retry, fallback, or reasoning tokens. Complete request sizes were 15,521--23,323 bytes, below the frozen 32,000-byte bound. Provider-reported total cost was $0.00178043, against a $0.01082398 reservation.
- Strict delivery is 0/24 usable source pairs. Every content reply violates the fixed bit-vector shape; therefore the official report correctly records 24/24 delivery-incomplete sources. This is a representation failure, not a claim that all 24 semantic decisions are wrong.

## Structural diagnosis

All five content replies were valid JSON with the expected top-level names, but
none met the full local wire contract:

| Content batch | Observed structural defect | Effect |
| --- | --- | --- |
| `H-H0040D161174`--`H-H3569508600E` | 16 post-type bits where 14 were required; six promotion bits where five were required. `promoted_subjects` used `null` for empty promotion lists. | No strict row parsed. The versioned normalizer can convert only the final empty-list synonym; it cannot drop unknown positions. |
| `H-H4E3B98376E5`--`H-H92A808A114E` | 15 post-type bits and five/seven topic bits rather than 14/eight. | No row parsed. |
| `H-HAF1D06FBEBA`--`L-L45-04` | 15 post-type bits; seven/eight topic bits; omitted required post-promotion and subject roots when a batch held eight decision slots. | No row parsed. |
| `L-L45-07`--`L-L45-21` | Seven topic bits instead of eight and nine D decisions; brand role switched from D-slot object to an array carrying invented `brand_id` fields. | Neither role parsed. |
| `L-L45-22`--`L-L45-45` | Correct 14/8 decision widths but six promotion bits where five were required. | No strict row parsed; missing/extra vector position remains unrecoverable. |

The normalizer is deliberately limited to complete empty-collection synonyms:
`promoted_subjects: null` becomes `[]` only when its fully supplied promotion
vector is all zero, and a complete blank nationalism object becomes `null`.
It does not repair bit widths, missing roots, unknown slots, arrays in place of
the D-slot object, or content classifications. Applied source-by-source, it
produced 19 usable brand rows and still zero usable content rows; no source pair
becomes publishable. Strict results remain the acceptance result.

## Per-source raw semantic review

`brand` below describes only the raw brand decision when it was structurally
decodable. `content unavailable` means the response shape prevents a reliable
label interpretation, so no label has been inferred from positional bits.

| Source | Raw/replayed observation | Visible-evidence review |
| --- | --- | --- |
| `H-H0040D161174` | content unavailable; Qwen `ideas_requests`, neutral, `framework`. | The open-weight/self-hosted choice and China/API data concern can support a framework reading; `ideas_requests` is at best uncertain because the author gives operational advice rather than asking Qwen for an idea. Content needs independently assessed local operation, cost, and openness axes; do not infer investor finance from local advice. |
| `H-H0DEC6F537E0` | content unavailable; Qwen none/positive/non-geopolitical. | Brand gratitude supports positive sentiment and no geopolitical state. Content should separately assess the explicit request to discuss issues. |
| `H-H1E48CCEEB2F` | content unavailable; DeepSeek none/positive/non-geopolitical. | Firsthand local use and a positive collaboration observation support positive brand sentiment; whether the product label should remain none needs the content decision, which is unavailable. |
| `H-H2B36BE298C6` | content unavailable; DeepSeek `investigate_claim`, negative, reporting+framework+nationalism, China anti/U.S. pro. | `investigate_claim` and reporting are supported for attributed theft allegations. The author does not adopt the national stance, so the directional nationalism state is unsupported. |
| `H-H3569508600E` | content unavailable; MiniMax none/neutral/non-geopolitical. | Neutral non-geopolitical brand state is defensible. The source contains concrete local-generation capability, limits, and measured performance that content must assess independently. |
| `H-H4E3B98376E5` | content unavailable; DeepSeek none/neutral/non-geopolitical. | The stored quote explicitly discusses the DeepSeek R1 paper and its Aha moment. That supplies target evidence; no unavailable conclusion should be inferred. The terse authored text leaves the precise post-type/sentiment reading uncertain. |
| `H-H7046A8A0689` | content unavailable; Qwen testimonial/negative/non-geopolitical. | The unsupported “better than Qwen 3.6” statement is an opinion, not `results_analysis`. It praises an external model relative to Qwen, so negative Qwen sentiment is defensible rather than an error. |
| `H-H74C810FB007` | content unavailable; DeepSeek complaint/negative/non-geopolitical. | The author describes disappointment with DeepSeek V4 Pro; complaint and negative sentiment are supported. |
| `H-H8FA9071508D` | content unavailable; Hunyuan none/neutral/non-geopolitical. | The visible post discusses GLM and other named models, not Hunyuan. This should be context-missing/unavailable. |
| `H-H92A808A114E` | content unavailable; MiniMax testimonial/positive/non-geopolitical. | The source attributes a 9-second generation of 15 seconds of video to MiniMax H3, supporting a favorable reading. Later digital-human/motion concerns are generic AI discussion and must not be transferred to MiniMax without a direct link. |
| `H-HAF1D06FBEBA` | content unavailable; GLM none/positive/non-geopolitical. | The author says they obtained a faulty-discount GLM plan and can use the series almost without limit. Positive sentiment is defensible; a product-label judgment remains separate. |
| `H-HFD61C2DE5BD` | content unavailable; MiniMax none/neutral/non-geopolitical. | “Perfectly capable as a high-volume executor” is a favorable evaluation, so neutral likely undercalls sentiment. It is still not automatic `results_analysis` without substantiated results evidence. |
| `L-L45-01` | content unavailable; DeepSeek none/neutral; Doubao unknown; GLM/MiniMax neutral; all non-geopolitical. | DeepSeek’s reported CFO/IPO account can be neutral. Doubao, GLM, and MiniMax occur only as investment examples, so their decisions should be context-missing/unavailable rather than assessed non-geopolitical labels. |
| `L-L45-02` | content unavailable; DeepSeek bug+investigate_claim/negative/non-geopolitical. | The concrete CVE and fix support bug and negative sentiment. `investigate_claim` needs caution: the post supplies a specific report rather than merely asking to investigate. |
| `L-L45-04` | content unavailable; Ernie none/neutral/non-geopolitical. | The factual hiring and leadership account supports neutral brand state. Its personnel-change content is unavailable because the bit output failed. |
| `L-L45-07` | both roles structurally invalid. | The official Sakana hiring post visibly supports job-listing/opportunity content. No usable brand semantics were emitted. |
| `L-L45-09` | both roles structurally invalid. | The author’s MiniMax H3 workflow and fine-motion limitation visibly support hands-on usage and mixed experience; no usable brand semantics were emitted. |
| `L-L45-13` | both roles structurally invalid. | The DeepSeek civil-engineer posting visibly supports hiring/job content. No usable brand semantics were emitted. |
| `L-L45-17` | both roles structurally invalid. | The supplied text specifically names Alibaba/Qwen, Moonshot/Kimi, and DeepSeek in attributed allegations. `news_reporting` and careful `investigate_claim` assessment are therefore relevant for each; the report must preserve attribution rather than treat them as generic Chinese-lab transfers. |
| `L-L45-21` | both roles structurally invalid. | The author makes an adopted China/U.S. geopolitical argument involving Kimi, DeepSeek, and GLM. A future output must assess nationalism/framework separately for each named brand and avoid mechanically uniform directional stance. |
| `L-L45-22` | content unavailable; DeepSeek testimonial/positive/non-geopolitical. | The owner has accepted positive DeepSeek benchmark/comparison relevance for this boundary. The raw positive decision is therefore not marked erroneous here; content scope remains separately unavailable. |
| `L-L45-23` | content unavailable; Qwen testimonial/neutral/non-geopolitical. | Qwen Cloud’s hackathon and project gallery are visibly favorable event/marketing evidence. Neutral sentiment likely undercalls the brand reading. |
| `L-L45-30` | content unavailable; Qwen none/unknown/non-geopolitical. | Qwen is visibly associated with overseas-model-news hiring in a humorous comparison. Unknown sentiment may be defensible, but the content side must decide whether this is a job listing rather than invent labels. |
| `L-L45-45` | content unavailable; DeepSeek testimonial/positive/non-geopolitical. | The author reports hands-on DeepSeek use and earnings, while describing limits and manual validation. Positive testimony is plausible; full content remains unavailable. |

## V6 adjustment, prepared but not sent

The corrected bit prompt did restore semantic checks, but Qwen still treats
vector lengths and slot representation as unstable. V6 therefore keeps the
same Alibaba route, current full taxonomy, independent-axis checks, and
country state table while replacing only the wire shape: each source is its
own two-role batch and returns readable named canonical label arrays. It has
no positional vectors, no redundant `none` bit, no brand IDs in output, no
fallback, and no retry. Its frozen contract is
`.context/model-task-20260917/qwen-classification-v6-singleton-named-diagnostic24-exception29/contract.json`
(SHA-256 `bb84429e70d078dfab3b245f47434eb6093cbac30b3e8630f8af2bbda17e5091`):
24 singleton batches, 48 calls, $0.04391652 reserved, largest request 19,003
bytes. It remains unspent pending portfolio-lock coordination.
