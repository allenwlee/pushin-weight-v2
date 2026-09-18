# GPT-5.6 Luna OpenRouter endpoint receipt

This immutable receipt captures the public `GET /api/v1/models/openai/gpt-5.6-luna/endpoints` response used to pin the OpenRouter route and supported request fields for the Luna translation and commentary controls.

It makes no inference calls and does not set prices. The separate September 17 [OpenRouter pricing snapshot](../2026-09-17-143812-openrouter-pricing-snapshot/README.md) remains the sole pricing source.

Run `python3 capture.py` only before the first capture in this timestamped directory. The script refuses to overwrite its raw response or manifest.
