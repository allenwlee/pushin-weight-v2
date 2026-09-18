---
title: Qwen classifier v6 singleton named diagnostic-24 review
date: 2026-09-17
type: experiment-review
---

# Qwen classifier v6 singleton named diagnostic-24 review

V6 tests one structural change after v5: each source gets one content call and
one brand-interpretation call, with named canonical arrays in place of
positional vectors. It retains the current U18A taxonomy, independent-axis
check, country state table, Alibaba-only route, no fallback, and no retry. This
review uses frozen visible evidence only; previous owner answers are not a
semantic gold set.

## Delivery and cost

- Contract: `.context/model-task-20260917/qwen-classification-v6-singleton-named-diagnostic24-exception29/contract.json`, SHA-256 `bb84429e70d078dfab3b245f47434eb6093cbac30b3e8630f8af2bbda17e5091`.
- All 48 required calls returned `finish_reason=stop`, selected Alibaba, and reported zero reasoning tokens. There was no transport error, retry, or fallback. The run finished at `2026-09-17T07:43:10.558175+00:00`.
- Actual provider-reported cost: $0.002654116; frozen reservation: $0.04391652. The largest frozen serialized request was 19,003 bytes, below the 32,000-byte Qwen bound.
- Strict delivery: 16/24 publishable source pairs; eight are incomplete (`H-H0040D161174`, `H-H1E48CCEEB2F`, `H-H4E3B98376E5`, `H-HAF1D06FBEBA`, `L-L45-04`, `L-L45-17`, `L-L45-23`, `L-L45-45`). This fails the zero-error smoke and 1% cohort gate.

The singleton named shape is a substantial delivery improvement from v5's
0/24. The remaining repeated wire defect is a bare D-slot mapping in the brand
role: six replies supplied an exact `D01` value but omitted the required
`decisions` object. A versioned replay wraps only an otherwise exact bare D
mapping. It also maps an expected canonical brand ID such as `qwen` to D01
only for a singleton source with a complete, unique expected-brand bijection.
It rejects aliases, unknown IDs, duplicates, incomplete mappings, collisions,
and every multi-source response; it changes no labels. That replay makes
H1E48, HAF1, L45-04, L45-45, H0040, and L45-23 pair-deliverable (22/24).
H4E3 still fails cross-role context consistency and L45-17 still conflicts
because Qwen is marked unavailable despite direct supplied evidence. Strict
delivery remains the result.

## Per-source evidence review

`C` and `B` state strict parser status. Parenthesized labels are the model's
raw named-array decisions when decodable. “Good axis” identifies support from
the visible source, rather than agreement with historical labels.

| Source | C / B | Good axis and source-specific issue |
| --- | --- | --- |
| `H-H0040D161174` | invalid (`qwen` key) / valid | B framework/neutral is plausible from China API data concerns and U.S. comparison. C visibly selects openness/cost but loses the required D slot; it also omits local/self-hosted operation. Local advice does not itself establish investor finance. |
| `H-H0DEC6F537E0` | valid / valid | `questions_requests`, positive sentiment, none product/geopolitics are supported by acceptance gratitude and request to discuss issues. This is a delivered semantic good. |
| `H-H1E48CCEEB2F` | valid / bare D root | C hands-on use, opinion, local inference, and agents/tools are supported by the two-session local DeepSeek experiment. B testimonial/positive/non-geopolitical is supported; only the outer `decisions` wrapper is missing. |
| `H-H2B36BE298C6` | valid / valid | C news reporting and distillation are supported. B investigate-claim is plausible for attribution, but negative sentiment and China-anti/U.S.-pro nationalism transfer a reported allegation into the author's stance. |
| `H-H3569508600E` | valid / valid | C hands-on use, measured performance/result, local operation, and cost/performance are supported. B `ideas_requests` is unsupported: the source gives recommendations rather than asking MiniMax for an idea. |
| `H-H4E3B98376E5` | valid / bare D root | The stored quote explicitly discusses the DeepSeek R1 paper and its Aha moment. C opinion is therefore plausible; B unavailable/unknown is wrong after replay. The terse authored text leaves the exact target sentiment uncertain. |
| `H-H7046A8A0689` | valid / valid | C opinion is supported. The unsupported “better than Qwen 3.6” is not `results_analysis`; it praises an external model relative to Qwen, so B negative sentiment is defensible. |
| `H-H74C810FB007` | valid / valid | C opinion plus B complaint/negative are supported by the stated disappointment with DeepSeek V4 Pro. |
| `H-H8FA9071508D` | valid / valid | Hunyuan is absent from the visible text, so C context-missing and B unavailable/unknown are correct. The post-level general promotion of the named zero-credit provider is source-supported and independent of target-brand relevance. |
| `H-H92A808A114E` | valid / valid | B MiniMax testimonial/positive/non-geopolitical is supported by the stated 9-second/15-second H3 capability. C captures opinion but may omit this capability as independent experience/result evidence. The later digital-human/motion limitation is generic and must not be transferred to MiniMax. |
| `H-HAF1D06FBEBA` | valid / bare D root | C opinion is supported. B bug/neutral is a defensible reading of the faulty discount, but the bare D root prevents strict delivery; replay makes only the wire envelope publishable. |
| `H-HFD61C2DE5BD` | valid / valid | C opinion is supported. MiniMax is called a capable high-volume executor, so B neutral undercalls favorable sentiment; the claim remains opinion rather than automatically `results_analysis`. |
| `L-L45-01` | valid / valid | DeepSeek reporting/business/personnel and neutral state are supported. The output wrongly classifies Doubao, GLM, and MiniMax as opinions/assessed neutral when they appear only as investment examples; those must be context-missing/unavailable. |
| `L-L45-02` | valid / valid | B bug/negative is supported by the CVE and fix. C `results_analysis`/`evals_benchmarks` is unsupported; it misses the news, technical sandbox explanation, and agent/tool context. |
| `L-L45-04` | valid / bare D root | C personnel change is supported; business finance is not clearly established by the visible hiring account. B neutral/non-geopolitical is defensible but lacks only the `decisions` envelope. |
| `L-L45-07` | valid / valid | Official Sakana hiring supports C job listing and B neutral/non-geopolitical. `opportunities` may also need independent assessment; no contrary raw label is invented. |
| `L-L45-09` | valid / valid | C hands-on usage and experience/result are supported by the MiniMax H3 workflow and fine-motion limitation. B should reflect a product-experience complaint and mixed sentiment rather than bug/neutral. |
| `L-L45-13` | valid / valid | C job listing is supported. The DeepSeek-infrastructure opinion can plausibly be business finance, but B framework is unsupported because the post does not adopt a geopolitical frame. |
| `L-L45-17` | valid / valid | The source specifically attributes allegations to Alibaba/Qwen, Moonshot/Kimi, and DeepSeek. C news reporting and carefully attributed B investigate-claim/negative readings are relevant for each. Qwen's unavailable result contradicts that direct supplied evidence; no nationalism should be inferred solely from the allegations. |
| `L-L45-21` | valid / valid | C opinion is supported. B framework/nationalism is supported for the explicit China/U.S. argument, but identical China-pro/U.S.-anti sentiment for Kimi, DeepSeek, and GLM oversimplifies praise of capability, warning of Chinese ideology, and concern over U.S. stagnation. |
| `L-L45-22` | valid / valid | The owner has accepted the positive DeepSeek benchmark/comparison boundary. The raw positive testimonial is therefore not marked as an unsupported transfer. The release/event/API axes still require target-specific scope rather than automatic inheritance from the unnamed competing model. |
| `L-L45-23` | invalid (`qwen` key) / bare D root | The Qwen Cloud hackathon is visibly an event/opportunity with agent-project context. Both roles violate the fixed D slot; no replay maps the prohibited brand-name key to D01. |
| `L-L45-30` | valid / valid | Qwen is visibly associated with overseas-news hiring. C news reporting is plausible but must independently consider job-listing content; B reporting/neutral has no stated country stance and is structurally valid. |
| `L-L45-45` | valid / bare D root | C hands-on usage, result, cost/performance, and agents/tools are source-supported. B testimonial/positive/non-geopolitical is also supportable; replay restores only its omitted outer root. |

## Exact per-source call record

The frozen raw envelopes contain provider creation times and complete usage.
The runner also persists individual wall-clock duration (`ms`). `in/out/r` are
input, output, and reasoning tokens; each row gives content then brand.

| Source | Content `in/out/r; $; ms` | Brand `in/out/r; $; ms` |
| --- | --- | --- |
| H-H0040D161174 | 3131/126/0; .00011031; 2658 | 2856/89/0; .00009725; 2094 |
| H-H0DEC6F537E0 | 2637/111/0; .00009354; 2460 | 2362/89/0; .00008243; 1766 |
| H-H1E48CCEEB2F | 2845/128/0; .00004055; 2192 | 2570/79/0; .00003515; 1788 |
| H-H2B36BE298C6 | 2726/113/0; .00003503; 2269 | 2451/103/0; .00008692; 1968 |
| H-H3569508600E | 2801/126/0; .00003897; 2369 | 2526/90/0; .00003526; 1951 |
| H-H4E3B98376E5 | 2767/113/0; .00003626; 2858 | 2492/80/0; .00003294; 1422 |
| H-H7046A8A0689 | 2648/113/0; .00003269; 2389 | 2373/89/0; .00003054; 1839 |
| H-H74C810FB007 | 2659/113/0; .00003302; 2680 | 2384/90/0; .00003100; 2238 |
| H-H8FA9071508D | 3228/209/0; .00012401; 3098 | 2953/90/0; .00004807; 1983 |
| H-H92A808A114E | 3256/113/0; .00005093; 2077 | 2981/89/0; .00004878; 1736 |
| H-HAF1D06FBEBA | 2686/113/0; .00003383; 2961 | 2411/79/0; .00003038; 1559 |
| H-HFD61C2DE5BD | 2869/113/0; .00010076; 2427 | 2594/89/0; .00003717; 1725 |
| L-L45-01 | 2897/284/0; .00006239; 3761 | 2622/317/0; .00006765; 3582 |
| L-L45-02 | 2721/115/0; .00003514; 2644 | 2446/89/0; .00003273; 1873 |
| L-L45-04 | 2767/119/0; .00009848; 3005 | 2492/79/0; .00003281; 2099 |
| L-L45-07 | 2783/112/0; .00003661; 2406 | 2508/89/0; .00003459; 2058 |
| L-L45-09 | 2743/118/0; .00003619; 1939 | 2468/89/0; .00003339; 2057 |
| L-L45-13 | 2882/119/0; .00004049; 2892 | 2607/89/0; .00003756; 1577 |
| L-L45-17 | 4271/213/0; .00015582; 3371 | 3996/258/0; .00010120; 3391 |
| L-L45-21 | 2751/219/0; .00004956; 3916 | 2476/259/0; .00005573; 3129 |
| L-L45-22 | 2705/128/0; .00009779; 2916 | 2430/89/0; .00003225; 2077 |
| L-L45-23 | 2783/116/0; .00003713; 2154 | 2508/79/0; .00003329; 1706 |
| L-L45-30 | 2753/111/0; .00009702; 2225 | 2478/90/0; .00003382; 1613 |
| L-L45-45 | 3036/125/0; .00004589; 1999 | 2761/79/0; .00004088; 1795 |

The named singleton shape is the last authorized Qwen classifier configuration
(six distinct profiles). It demonstrates that delivery improved, but semantic
errors on current axes remain material, so it cannot qualify the model.
