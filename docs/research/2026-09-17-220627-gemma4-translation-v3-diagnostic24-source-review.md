# Gemma 4 31B translation v3: diagnostic-24 source review

Gemma v3 used the final structured-line and JSON-object configuration. The run has eight provider transport failures: seven HTTP 429 responses and one 180-second transport failure. The retained HTTP failure evidence cannot attribute the 429s to OpenRouter or its selected provider, so it is not evidence about translation quality or the JSON response shape.

The 24-by-3 review ledger classifies every requested locale. It records 10 coverage errors across 6 source posts: nine null target cells from failed requests, plus the Chinese target for the bilingual Hausa post, which repeats the English paragraph rather than rendering the Hausa half. The 62 delivered, non-coverage outputs did not show a confirmed semantic error in this source-only pass. That observation does not make v3 comparable with v1 because the missing coverage is decisive.

The complete source/context ledger is `.context/model-task-20260917/gemma4-translation-v3-structured-diagnostic24-20260917-215700/source-grounded-review-v2.json`. This diagnostic is not a qualification result. V1 is selected for the matched random-100 regression because it completed cleanly, not because v3 proves a format failure.
