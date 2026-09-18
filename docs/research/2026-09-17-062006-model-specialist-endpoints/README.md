# OpenRouter specialist endpoint snapshot — 2026-09-17 15:20 JST

This immutable capture records public `GET /api/v1/models/{model}/endpoints` responses for four requested routes. It made no inference requests, used no credentials, and made no paid calls.

| Model route | HTTP | Returned endpoints | Availability finding |
|---|---:|---:|---|
| `tencent/hy-mt2-1.8b` | 200 | 1 | available: Tencent, `tencent/fp8`, fp8 |
| `tencent/hy-mt2-7b` | 200 | 1 | available: Tencent, `tencent/fp8`, fp8 |
| `openai/gpt-oss-120b` | 200 | 24 | available from 24 providers/tags |
| `openai/gpt-5-nano` | 200 | 4 | available from OpenAI Flex/OpenAI and Azure |

- [Endpoint metadata CSV](endpoint-metadata.csv) preserves provider, endpoint tag, quantization, context limits, supported parameters, pricing JSON, and the exact endpoint object for every returned record.
- [Raw endpoint responses](raw/) are the exact response bytes saved before normalization.
- [Capture manifest](manifest.json) records request URLs, UTC timestamps, HTTP metadata, coverage, and SHA-256 checksums.
- [Capture script](capture.py) documents the public GET procedure and bounded concurrency (maximum three requests at once).

The CSV retains raw USD-per-token pricing inside each endpoint's `pricing` JSON. Blank or absent fields remain unknown; a route is considered unavailable only when its actual endpoint response is empty. This snapshot is evidence for route selection and parameter support. Provider availability and prices can change, so the exact endpoint should be rechecked before a paid evaluation. Existing Qwen and Gemini snapshots remain the price authority for those models.

## Parameter highlights

- `tencent/hy-mt2-1.8b`: `temperature`, `stop`, `max_completion_tokens`, `max_tokens`.
- `tencent/hy-mt2-7b`: the same plus `response_format` and `structured_outputs`.
- `openai/gpt-oss-120b`: all records support reasoning controls; most also expose structured outputs, tools, sampling, and log probabilities. Exact per-provider lists are in the CSV.
- `openai/gpt-5-nano`: OpenAI records support structured outputs, tools, seed, and reasoning controls; Azure records use `max_completion_tokens` and expose the same core structured/tool controls. Exact lists are in the CSV.
