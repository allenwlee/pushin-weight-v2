---
title: U18 R98 Direct Control and Fallback Pilot Results
type: analysis
date: 2026-09-14
status: blocked-no-passing-candidate
---

# U18 R98 Direct Control and Fallback Pilot Results

## Plain-English Summary

Direct DeepSeek was used as the control and completed all 45 post-brand rows, but its classifications did not meet the frozen quality and regression requirements. The four preapproved OpenRouter alternatives also failed before producing a passing 45-row result. No model was selected, so classifier activation and staging or production promotion remain blocked at U18.

The bounded run used 12 logical requests and 14 transport attempts. It generated no reasoning tokens. Direct DeepSeek cost an estimated $0.03512344 from returned token usage and the frozen official peak rates. OpenRouter billed $0.00155216. The combined known or estimated spend was $0.03667560, well below the $0.5629859322 ceiling.

## Candidate outcomes

| Candidate | Outcome | Complete pairs | Logical requests / transports | Conservative ledger spend |
| --- | --- | ---: | ---: | ---: |
| Direct DeepSeek V4 Flash | Complete output; failed semantic gates | 45/45 | 6 / 6 | $0.03512344 |
| Qwen3 30B / StreamLake | Invalid content response | 0/45 | 2 / 2 | $0.00155216070 |
| Mistral Small 3.2 / Parasail BF16 | Transport failed after both allowed attempts | 0/45 | 2 / 4 | $0.00216450000 |
| GPT-5.6 Luna / OpenAI Flex | Catalog blocked: required temperature unsupported | 0/45 | 0 / 0 | $0 |
| Gemini 3.8 Flash / Google AI Studio Flex | HTTP 400 | 0/45 | 2 / 2 | $0.00450937500 |

The conservative ledger includes estimated cost for failed transports, even when OpenRouter did not bill them. The settled OpenRouter key delta matches the Qwen requests; Mistral transport failures and Gemini HTTP 400 responses were not billed.

## DeepSeek control quality

DeepSeek reached 100% row coverage and an 8.793-second complete-result p95. Product labels were its strongest dimension: 0.822 exact-set accuracy and 0.769 micro F1, including 0.857 testimonial F1. Post types reached 0.244 exact-set accuracy and 0.654 micro F1. Sentiment accuracy was 0.622. China and U.S. nationalism accuracy were both 0.156 because the model returned null for most assessable non-nationalistic posts instead of none. Across all axes, no row exactly matched the owner reference.

The failed post-type labels included events (0.000 F1), opportunities (0.333), research explanations (0.526), and results/evaluations (0.476). The overall improvement composite was 0.485 versus the required 0.864. This is a semantic-quality failure under the unchanged frozen gates, rather than a coverage, latency, reasoning-token, or cost failure.

## Decision

No candidate is selected. R97 remains immutable failed evidence, and this R98 result closes the separately frozen control-and-fallback trial. No additional model, repair pass, retry, floor change, classifier activation, or deployment is authorized by this result.

The machine-readable result is docs/analysis/2026-09-14-221023-u18-r98-control-fallback-pilot-results.json. Raw public-X packets and provider responses remain under .context/u18/openrouter-two-role-pilot-r98-control-fallback-v1 and are not committed.
