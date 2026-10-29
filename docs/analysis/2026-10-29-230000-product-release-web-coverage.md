# Product-release web inventory and database coverage

This is a 142-nomination coverage checklist, not a count of 142 distinct or confirmed releases. It retains the earlier 56 nominations and adds 86 provider, lab and research nominations. Family variants, previews, regional access and separate milestones can overlap. The frozen 30-case test cohort was not changed by this additional research.

The primary-source review spans DeepSeek, MiniMax, Z.ai, Qwen/Alibaba, Mistral, Kimi, StepFun, Meta, OpenAI, Anthropic, Google, NVIDIA, Cohere, xAI, Upstage, IBM, Ai2, LG, SenseTime, inclusionAI, Sakana, Kuaishou and the unfamiliar publishers in the study. Links and source-stated dates are retained per row. This is a bounded broad cross-check, not proof that every worldwide release was found.

[Full CSV](2026-10-29-230000-product-release-web-coverage.csv) · [Source-linked JSON](2026-10-29-230000-product-release-web-coverage.json)

The raw-text search read 438,494 source-database Posts and 265,340 staged Posts in August1 00:00JST–October29 19:00JST. It found a normalized alias occurrence for **139/142** nominations in the source and **122/142** in staging. A match may concern a comparator, rumor, older model or similarly prefixed version; this is presence evidence, not release recall or confirmation.

## Corrections to the original check

The first pass dropped five-character aliases such as GLM53 and Bolmo. A supplemental query corrected that search bug. Another pass used exact provider orderings: `wan3.0-video-prime` and `qwen-audio-3.1-realtime-plus`. Punctuation normalization alone cannot repair reordered model names. HappyOyster was also checked without requiring a version suffix. These changes repair this research process; the routine source-first detector has no product-name search gate.

[Alibaba's lifecycle page](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) also lists Qwen Flash Character in January and as a later global rollout in August. That does not establish a new August model. The same caution applies to regional deployments, speed tiers and provider listings elsewhere. Research must retain the provider's actual ID, region, access channel and date meaning instead of manufacturing a search term from display-name components.

## Source alias nonmatches

- B012: Qwen Flash Character / None — searched Qwen-Flash-Character, qwen-flash-character. [Primary listing](https://www.alibabacloud.com/help/en/model-studio/newly-released-models).
- B036: Alibaba Decision Model / Preview — searched Alibaba Decision Model, decision-model-preview. [Primary listing](https://www.alibabacloud.com/help/en/model-studio/newly-released-models).
- W084: Qwen Audio 3.0 Realtime Flash — searched qwen-audio-3.0-realtime-flash. [Primary listing](https://www.alibabacloud.com/help/en/model-studio/newly-released-models).

These are unresolved name-coverage gaps. They do not prove that the database lacks every related post or that the harvester failed. Confirm the original announcement and search broader identifiers before selecting a collector repair. No new collection query, provider request or harvester schedule was activated for these gaps.

## Additional staging-only gaps

- Voxtral Mini Transcribe 3: 8 source-database alias matches, zero in staging.
- Voxtral Mini Transcribe Realtime 3: 9 source-database alias matches, zero in staging.
- Voxtral Small Transcribe 3: 24 source-database alias matches, zero in staging.
- Gemini 3.5 Live: 2 source-database alias matches, zero in staging.
- Gemini API CLI: 16 source-database alias matches, zero in staging.
- Nemotron 3.5 Transcribe: 83 source-database alias matches, zero in staging.
- Granary v2: 9 source-database alias matches, zero in staging.
- Embed 5: 1 source-database alias matches, zero in staging.
- North 2: 2 source-database alias matches, zero in staging.
- Rerank 5: 3 source-database alias matches, zero in staging.
- OlmoEarth 1.3: 4 source-database alias matches, zero in staging.
- Qwen Audio 3.1 Realtime Flash: 9 source-database alias matches, zero in staging.
- SenseNova 6.8 Code2Video: 12 source-database alias matches, zero in staging.
- Ling-3.1-flash-1019: 59 source-database alias matches, zero in staging.
- Ming-3.0-tts-0.5B: 9 source-database alias matches, zero in staging.
- Sakana Aquarium: 4 source-database alias matches, zero in staging.
- Sakana API Platform: 1 source-database alias matches, zero in staging.

The study uses the finite staging fixture. These differences must not be interpreted as audience inactivity.

## Collection consequences

Known catalogue membership is no longer an admission gate, and the supported loaders consume saved labels/commentary and retained non-X release documents. Further targeted acquisition of cards/provenance and publisher-account verification belongs to PR-U4. Missing release-bearing content in metadata observations is reported explicitly. No unproven fix is claimed for a name nonmatch. The separate rare-query handoff and URL/entity collection work retain their existing owners.
