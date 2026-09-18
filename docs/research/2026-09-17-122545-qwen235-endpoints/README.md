# Qwen3-235B-A22B-Instruct-2507 endpoint receipt

This immutable receipt preserves the public `GET /api/v1/models/qwen/qwen3-235b-a22b-2507/endpoints` response used to pin the Qwen translation trial route and the request fields advertised by that route.

It made no inference calls and did not use credentials. It does not establish a price: the September 17 [saved OpenRouter pricing snapshot](../2026-09-17-143812-openrouter-pricing-snapshot/README.md) remains the sole source for reservation and provider max-price caps.

The captured GMICloud FP8 endpoint is active (`status: 0`) and advertises `max_tokens`, `temperature`, `response_format`, and `structured_outputs`. It does not advertise `reasoning`; the Instruct-2507 profile therefore omits reasoning controls. The raw response also lists alternative providers, which are evidence only and are not fallback authorization.
