# Gemma 4 31B random100 recovery-aware rerun

This isolated rerun used the frozen `gemma4_translation_v1` random100 contract. It changed only transport recovery: two in-flight requests, up to three total attempts for HTTP 429/503, shared provider cooldown, and a 40-minute deadline. The model, DeepInfra-only route, raw-text prompt, token ceilings, source rows and saved-price ceiling stayed frozen.

The run began at `2026-09-17T14:11:44.004983+00:00` and ended at `2026-09-17T14:39:20.959987+00:00`, an artifact-derived wall time of 1,656.955 seconds. It made 286 attempts for 215 frozen translation targets: 186 HTTP 200 responses, 98 HTTP 429 responses, and two non-HTTP transport errors. Forty-one targets failed their first attempt; twelve recovered on a later allowed attempt. Twenty-nine targets remained transport-missing. Five further fields were rejected by the existing caller validation, leaving 34 missing fields across 20 rows.

Returned usage reports 99,331 input tokens, 49,266 completion tokens, zero reasoning tokens, and $0.02482317 actual response-reported cost. The pre-send reservation was $0.59909259 for the three-attempt worst case. This is an observed receipt sum, not a replacement for the frozen saved-price cap.

One new 429 receipt identifies `DeepInfra`, `engine_overloaded`, and `upstream_provider_shared_pool`; it had no Retry-After. That establishes the source for this new response only. Sustained shared-pool overload and the fixed retry ceiling explain the missing coverage; they do not establish a model-quality failure.

The source-only packet is `content-masked-source-review-packet.json` (SHA-256 `d0f794cb973d54de9d62b8acab7c18dc43869d8f30a18eaf4558f26323b2b414`). The source-grounded review covers all 300 fields: 85 native copies, 181 delivered generated fields, and 34 missing/rejected fields. It records 24 source-level error-union posts: 21 with coverage failure, including transport missing fields, and three with observed semantic errors. Clear semantic findings include the Chinese un-translated `ENABLE SO MUCH`, literal French `poulet` slang in all three targets, and the Japanese price relation rendered as model “height” in English and Chinese. The price issue is counted because its surrounding dollar comparison makes the monetary relation explicit; this is not a style-only finding.

The original stopped nine-receipt attempt remains preserved separately and is not mixed into this rerun’s delivery or quality counts.

## Parent reconciliation (supersedes preliminary review count)

Final review is **25 affected source posts**, 21 coverage and four additional semantic, with 44 erroneous fields and 256 passing fields. Parent inspection found leaked `[[PQ2B]]` markers in Chinese and Japanese for post `2100357277253542260`, missed in the preliminary 24-source review. The price-question error also occurs in incumbent EN: an additive, source-grounded amendment counts it equally, changing this comparison's control from nine confirmed plus one uncertain to ten confirmed plus one uncertain. Original review files and predictions are preserved. See `parent-reconciled-review.json` and `incumbent-paired-review-amendment.json` in the run directory, and the [combined result](2026-09-17-235000-gemma-qwen-recovery-rerun-comparison.json). The candidate does not qualify.
