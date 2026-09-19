# Raised-ceiling translation and commentary repeat

The owner requested a complete repeat to determine whether errors recur. All 96 planned provider attempts finished: three translation requests and 45 commentary requests per model. Previous artifacts remain unchanged. No automatic retries, database writes, runtime changes, or deployment occurred.

## Results

| Task / model | Previous complete | Repeat complete | Previous time | Repeat time | Repeat cost |
|---|---:|---:|---:|---:|---:|
| Translation / 0731 | 45/45 | 45/45 | 794.1 s | 875.5 s | $0.009265 |
| Translation / incumbent | 45/45 | 45/45 | 194.0 s | 188.8 s | $0.056446 |
| Commentary / 0731 | 40/45 | 44/45 | 728.9 s | 532.6 s | $0.005887 |
| Commentary / incumbent | 45/45 | 42/45 | 178.0 s | 174.7 s | $0.037102 |

“Complete” means accepted by the actual caller's structural validation; it does not mean semantically faithful. Incumbent costs are usage estimates at the previous report's documented peak rates. 0731 costs are reported usage; wallet fees are excluded. Total repeat cost was $0.01515132 reported for 0731 and approximately $0.09354844 estimated for the incumbent.

## Did the errors recur?

- **0731 translation omission: yes.** Post `2079629240996155513` again omits two source paragraphs from EN, ZH-CN, and JA. The original English field was instructed to copy source verbatim but also lost them. The parent verified the exact raw response independently. This is a real recurring fidelity failure despite valid JSON and a larger ceiling.
- **0731 Anthropic typo: no.** The previous Chinese `Anhtropic` typo is absent in this run. An English rendering of the Japanese name `ジェイコブ・コクソン` differs from the prior output; its intended Latin spelling is not established by the source. It is not counted as confirmed entity corruption.
- **0731 commentary JSON failure: yes, on a different post.** The previous five failed posts all completed this time. The new failure is `2097550594831470859`, with `openrouter_response_content_invalid` after 604 output tokens, far below 4,000. No HTTP 429 responses occurred in this repeat. The adapter did not retain the invalid raw text, so its exact syntax defect remains undetermined.
- **Incumbent commentary: three new failures.** `2091583113914618174` supplied all required fields plus an unsolicited `commentary_en_note`, rejected by the exact schema. `2097328541016743997` and `2072636451452530811` returned unparseable JSON; the direct adapter substituted its existing `llm_non_json_response` fallback, which the synthesis validator rejected. These were 1,139, 376, and 1,704 output tokens respectively, below 4,000. They are not token-ceiling failures.
- **Incumbent literal format:** the Japanese output for `2096881764480561562` reduced an 87-line source with Chinese and Japanese blocks to 45 lines, removing a repeated source segment. Its main substantive content appears once, but this violates the exact literal-format objective.

The full 0731 agent diagnostic initially incorrectly reported the omission as recovered. A second audit disagreed; the parent inspected the raw JSON and confirmed recurrence. The rejected version is retained, and the corrected diagnostic explicitly withdraws its unsupported comprehensive semantic-pass claim. Reported formatting differences are not automatically counted as semantic omissions. These are unblinded diagnostics, not a population-quality estimate.

## Slow batch

0731 repeated translation timings were 363.554, 478.120, and 33.846 seconds for 20/20/5 posts. The second 20-post batch contains ten Chinese and ten Japanese posts. Five long posts account for 71% of its source characters. It generated 25,202 output tokens, while the equivalent incumbent batch completed in 100.511 seconds. The previous 0731 second batch took 526.390 seconds. Slow service therefore recurred, though this one batch was faster on the repeat. Total 0731 translation time increased from 794.116 to 875.535 seconds.

There is no per-post timing within the batch. Queue delay and generation time were not separately measured. Do not attribute the delay to a specific post or to model reasoning: reasoning was disabled and reported reasoning tokens were zero. The longest call still exceeds the runtime's 300-second enrichment-attempt budget.

## Controlled inputs and limits

The repeat reused `.context/u20/translation-synthesis-prepare-20260916-v4/` with identical row and request hashes, prompts, 20/20/5 grouping, model routes, and sampling parameters. Literal allowances were 32,768 / 32,768 / 8,192; each three-language single-post commentary request allowed 4,000. Literal socket inactivity was 180 seconds for both models; the earlier successful 0731 translation run used 60 seconds. This timeout difference is disclosed rather than calling the run identical in every execution parameter. Commentary stayed at 60 seconds. Each model was serial, while the separate provider routes overlapped. The cap remained $0.50 per model.

The current source-copy output fields contain 29,518 of 99,640 characters (29.62%). This is a character proxy, not a token savings measurement. A proposed source-copy optimization is described in the [request-shape research](../research/2026-09-16-190600-u20-0731-request-shape-research.md); it was not applied to this repeat.

## Artifacts and disposition

- Execution and reports: `.context/u20/translation-synthesis-repeat-20260916-183930/`
- Corrected 0731 diagnostic: `arms/0731/translation/repeat-diagnostic-20260916.json`
- Rejected diagnostic retained: `arms/0731/translation/repeat-diagnostic-20260916-rejected-agent-review.json`
- Incumbent diagnostic: `repeat-incumbent-diagnostic.json`
- Per-call usage, request hashes, raw parsed responses, and failed-ID comparison remain in the execution directory.

The original browser packet continues to show the original test, not this repeat. Existing classifier and staging acceptance gates remain open. Higher limits fixed truncation, but did not establish reliable fidelity, JSON output, or runtime latency.
