# Gemini Flex classifier v1 — smoke eight review

## Frozen run

`gemini_flex_classifier_v1` sent four requests: two five-post-or-smaller
batches and the required `content` / `brand_interpretation` roles. It pinned
`google/gemini-2.5-flash-lite` to `google-ai-studio/flex`, requested Flex tier,
disabled provider fallbacks and reasoning, and used strict JSON Schema.

All four replies attested Google AI Studio, model `google/gemini-2.5-flash-lite`,
and `service_tier: flex`. No response was retried, repaired, or sent to a
different provider. The contract, raw envelopes, parsed results, usage, and
consumed marker are in
`.context/model-task-20260917/gemini-flex-classification-v1-smoke8/`.

| Measure | Result |
|---|---:|
| Provider calls | 4 / 4 |
| Strict parser calls | 4 / 4 |
| Complete strict source pairs | 7 / 8 |
| Source-level structural inconsistency | 1 / 8 |
| Reported input / cache-read / output tokens | 12,984 / 758 / 2,090 |
| Reported provider cost | $0.00103309 |
| Total sequential latency | 8,564 ms |

The acceptance rule is incumbent parity under the current independent rubric,
not the retired fixed one-percent error gate. This smoke result cannot be
declared equal to or better than the direct DeepSeek V4.1 baseline because it
has a confirmed content/brand inconsistency and only eight sources have been
reviewed here.

## Confirmed failure-linked findings

| Source post | Exact supplied evidence and context | v1 output | Finding |
|---|---|---|---|
| `L-L45-02` | Source text: “DeepSeek Harness denied file writes and left loopback alone. Its own control API listens there, so the agent could curl itself to danger-full-access. CVE-2026-82533, 9.4. Fixed in 0.1.2-alpha.1.” Supplied context contains only author `NewsOfLinux`, empty quote/reply, and the explicit unavailable-media note. | Content: `classified`, `hands_on_usage`, `research_explanations`, `agents_tools`. Brand: `bug`, negative, but geopolitical `unavailable` and sentiment/country unknown. | The direct DeepSeek Harness behavior, CVE, and fixed version are visible evidence, so the brand role's unavailable state conflicts with the content role's classified state. This is a strict cross-role delivery failure, not a parser failure. |
| `L-L45-01` | Source text says “next station DeepSeek CFO” and “DeepSeek 未回应”; its separately named public investment cases are ByteDance, MiniMax, and Zhipu. Supplied context contains only author `JimiLonbo`, empty quote/reply, and the unavailable-media note. | Content gives `personnel_changes` and `business_finance` to DeepSeek, Doubao, GLM, and MiniMax. | The visible CFO transition is specifically DeepSeek. Extending `personnel_changes` to the other target brands transfers a role change across brands, contrary to the supplied evidence and taxonomy rule. |
| `L-L45-21` | Source text warns that Chinese AI could put “自国の思想を含めたAIを世界に無料で展開し、いつしかその思想は世界の常識となる.” Supplied context contains only author `pipix1121`, empty quote/reply, and the unavailable-media note. | All three targets receive China `pro`, U.S. `anti`, and positive sentiment. | The China `pro` result reverses the stated warning. The source context does not add another speaker or omitted-media evidence that could justify the reversal. |

Other model-versus-incumbent differences remain unscored pending the full
same-cohort rubric review. For example, `H-H0DEC6F537E0` correctly restores
`questions_requests`, while its brand `unknown` reading needs the rubric rather
than an automatic incumbent match.

## v2 adjustment

The next frozen configuration isolates every source into its own two-role batch
and retains the same Flex route and strict schema. It adds a brand-bound check
against cross-brand transfer and a direct-evidence availability check: visible
product vulnerabilities, versions, behavior, complaints, releases, or
comparisons cannot be marked unavailable. This changes batch shape and the
two failure-linked checks only; it does not add a third role, retry, fallback,
or reasoning budget.
