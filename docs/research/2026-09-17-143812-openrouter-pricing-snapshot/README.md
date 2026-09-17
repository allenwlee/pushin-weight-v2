# OpenRouter price snapshot — 2026-09-17 14:38:12 JST

This snapshot preserves the prices OpenRouter returned when we checked, so model comparisons can cite saved evidence rather than recall. It helps select inexpensive candidates for classification, translation and commentary; it does not score their intelligence or quality.

- [All 444 catalog models, CSV](models.csv): readable USD per million input/output/cache tokens, exact model IDs, modalities and supported parameters.
- [Candidate provider and tier prices, CSV](candidate-endpoints.csv): 68 endpoints for the nine queried candidates; 80 rows including price-tier overrides.
- [Raw catalog](raw/models.json): exact response bytes from `GET https://openrouter.ai/api/v1/models`.
- [Capture manifest](manifest.json): URLs, per-request UTC timestamps, HTTP status, available server cache headers, coverage, and SHA-256 checksums.
- [Capture script](capture.py): repeatable capture into a NEW timestamped directory. Run `python3 capture.py /absolute/path/to/docs/research`. Existing snapshots are never overwritten. Uses public metadata requests; no API key or inference calls.

## Rules for price answers

1. Cite this snapshot's capture date and the exact model ID. For a test recommendation, identify the endpoint/provider, service tier, and applicable input-length tier from the endpoint table.
2. Read both input and output prices. Forecast using each task's measured token mix; include cache, reasoning, retries and successful-result coverage when known. Do not use the arithmetic average of model input prices.
3. Blank means unknown or not applicable. Zero must be explicitly present in the API response. A model without an active endpoint has no executable quote in this snapshot.
4. Catalog prices do not guarantee that a selected provider costs the same. A base endpoint row may be superseded by its threshold rows; inspect original pricing JSON for conditions beyond the named columns. Service tiers such as Flex are separate endpoint tags.
5. Raw prompt/completion rates are USD PER TOKEN; CSV columns multiply by exactly 1,000,000 using decimal arithmetic. Other fields (images, requests, searches, storage etc.) retain original API units and are not blindly scaled.
6. Funding fees and taxes are separate; direct-provider prices are separate. An OpenRouter DeepSeek listing is not the price for our direct DeepSeek account.
7. This is a dated observation, not a permanent guarantee. Recheck the exact endpoint before any paid evaluation. No paid availability check was performed.

## Candidate scope

- `deepseek/deepseek-v4-flash-0731`: HTTP 200, 29 endpoints, catalog present=True.
- `deepseek/deepseek-v4.1-flash`: HTTP 200, 19 endpoints, catalog present=True.
- `qwen/qwen3.7-flash`: HTTP 200, 1 endpoints, catalog present=True.
- `google/gemini-2.5-flash-lite`: HTTP 200, 5 endpoints, catalog present=True.
- `qwen/qwen-2.5-7b-instruct`: HTTP 200, 1 endpoints, catalog present=True.
- `qwen/qwen-2.5-72b-instruct`: HTTP 200, 2 endpoints, catalog present=True.
- `meta-llama/llama-3.3-70b-instruct`: HTTP 200, 11 endpoints, catalog present=True.
- `qwen/qwen2.5-32b-instruct`: HTTP 200, 0 endpoints, catalog present=False.
- `deepseek/deepseek-r1-distill-llama-8b`: HTTP 200, 0 endpoints, catalog present=False.

Only candidate endpoints were expanded. The complete default catalog is captured, but specialized output catalogs (for example transcription) and provider details for other models require additional queries. The public metadata fetches occurred over a short interval, not one atomic vendor-wide snapshot.
