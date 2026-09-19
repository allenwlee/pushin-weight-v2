# Hy-MT2-30B-A3B endpoint metadata — 2026-09-17 21:25 JST

This immutable supplement preserves one public OpenRouter endpoint-metadata
response for `tencent/hy-mt2-30b-a3b`. It uses no credentials and makes no
inference request.

The frozen catalog snapshot remains the price authority: `$0.074` per million
input tokens and `$0.295` per million output tokens. Endpoint prices captured
here are metadata only and never raise those request caps.

- `raw/` contains the response bytes.
- `endpoint-metadata.csv` makes the returned route, provider, tag, limits and
  supported parameters easy to inspect.
- `manifest.json` records timing, scope, response status and SHA-256 hashes.
- `capture.py` is the repeatable public-GET procedure.
