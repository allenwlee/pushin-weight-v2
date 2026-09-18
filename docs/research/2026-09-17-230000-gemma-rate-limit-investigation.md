# Gemma rate-limit investigation

Diagnosis only. Seven HTTP 429 responses affected **five** posts, not six. The sixth post with a null translation had a successful API response containing untranslated Danish; the validator rejected that output. Total affected posts remains eleven: five with transport failures and six with output defects. Prior broad claims that all six missing-output posts came from rate limits are superseded.

## What the evidence establishes

- The 215-request run received 208 successful API responses and seven HTTP 429 responses. The latter account for seven missing locale fields across five posts; a separate rejected source copy accounts for the eighth missing field and sixth missing-output post.
- All seven rejections cluster near 22:23:01–22:23:11 JST, September 17, within approximately 9.435 seconds by estimated request-start times. Their latencies are 239–736 milliseconds. Accepted requests occur before, during and after this window. The entire run lasted about 715 seconds.
- Timing is reconstructed from retained per-request file modification times minus measured request latency. The recorder overwrote its initial consumed-at field, so these are approximate timings, not exact send timestamps.
- The frozen configuration allowed three simultaneous requests, zero pacing, zero retries, and only `deepinfra/turbo`, with fallbacks disabled. It used a paid model on an account already shown as paid and without a per-key credit cap. That does not establish the account balance or its upstream limits.
- Rejecting each request quickly freed a worker to send another queued request immediately. With no backoff or retry, a transient rejection window therefore affected several posts. This explains how throttling became permanent missing output in this experiment, but not which service imposed the original throttle.

## Leading explanation and competing explanations

Transient serving-route capacity throttling is the best-supported explanation: the short cluster, fast rejection, mixed accepted requests and subsequent recovery fit a temporary capacity window. [DeepInfra documents](https://docs.deepinfra.com/account/rate-limits) that a busy model may return 429 even below the usual concurrency limit. Its published direct-account limit is not proof of the quota available through OpenRouter.

An OpenRouter-side throttle or upstream request/token quota remains possible. A persistent exhausted credit balance or invalid prompt is less consistent with the observed successes surrounding the failures, and these were HTTP 429 rather than credit or request-validation statuses. The raw-text prompt did not use JSON response formatting. No inference supports blaming JSON, long outputs or inadequate model intelligence for these seven rejections.

[OpenRouter documents](https://openrouter.ai/docs/api_reference/limits) that 429 can come from either its platform or an upstream provider; error metadata and rate-limit headers distinguish them. The exact origin cannot be recovered from this run because `x_monitor/openrouter.py:179` reads the error body, then at lines 202–204 raises only `openrouter_http_status_429`. It does not retain the body or headers. `scripts/model_task_experiment.py:191` can consequently save only the generic exception, and `x_monitor/literal_translation.py:527` converts that failed call into a missing target. Provider fallback was explicitly disabled by the experiment contract.

## Corrected sixth-post attribution

Post `2100158906307670018`, frozen request index 56, returned HTTP success with `finish_reason=stop`, but copied the Danish original verbatim instead of translating to Chinese. An offline replay of `_validate_translation` reproduces `untranslated_source_copy` and returns null. The initial review's HTTP-429 explanation for this field was wrong. The total score remains 11/100; the transport-versus-model split is corrected. The original review files remain preserved, with this investigation as an additive attribution amendment.

## Recommended next change

Retain sanitized error code/message, provider metadata, request IDs, `Retry-After` and `X-RateLimit-*` headers on exceptions and in experiment receipts. Add a fake HTTP 429 regression in `tests/test_provider_plaintext.py` that proves these fields survive; the existing test only checks the exception type and generic status string. Do not retain authorization headers or credentials.

For a separately recorded recovery test, honor `Retry-After`, otherwise use bounded exponential backoff with jitter, and pause the shared provider queue during cooldown so other workers do not keep submitting. Allow at most two retries per rejected target within an explicit time/cost cap. Keep the same model, prompt and provider for that test; it isolates delivery recovery from model changes. Re-run only the seven rejected targets initially, retaining first-attempt and recovered coverage separately. Review the new translations before inferring a better quality score. Broader provider fallback can change price/precision and should not be silently introduced.

No runtime code, model configuration, original score or deployment was changed. No additional paid inference was sent. Confidence is high in the request counts, the no-retry consequence and the corrected Danish case; moderate in transient capacity as the explanation; unresolved on which service enforced the limit. Exact historical attribution would require provider-side logs or the original HTTP error metadata, which this harness did not save.

Evidence: [machine-readable request IDs, routing and approximate timing](2026-09-17-230000-gemma-rate-limit-investigation.json).
