# DeepSeek V4 Flash 0731 GGUF versus hosted headline models

Date: 2026-09-03  
Scope: PushinWeight v2 headline-generation bakeoff; read-only evidence review.

## Executive decision

Do not replace the production headline provider with Hillary's local GGUF. Keep
the hosted DeepSeek V4 Pro path for production headlines and use the local model
only as a shadow candidate until it clears a materially stricter calibration and
latency gate. The local run completed mechanically, but it failed calibration:
`calibration_pass=false` and `zero_unsupported_publications=false`.

## Setup and identity

The local artifact is `/tmp/2026-09-03-dsv4-flash-0731-headline-evaluation.json`
on fuchitalee. It identifies source `ggml-org/DeepSeek-V4-Flash-0731-GGUF`,
served model `dsv4-flash-0731-mxfp4`, MXFP4 quantization, revision
`f559fd6005309e5f6bd650342ee8711ff189b3b8`, Hillary endpoint
`hillary:127.0.0.1:1235`, and a 65,536-token runtime context. The evaluator
intercepted all requests and served them locally; publication was disabled.

The historical evaluator hard-coded request model `deepseek-v4-pro`, while the
intercepted server was the Flash GGUF. Thus this is a model-quality/runtime
comparison, not proof that the local server accepts the production model ID.
The architecture and prompts were `per_brand_rank_editor_critic_v3`, with
rank/editor/critic stages and eight critic controls.

## Quantitative result

The local run used 17 sequential calls: 37,595 reported input tokens and 16,010
output tokens, with accounted cost $0.113025. The $0.00 local billing field is
not comparable to that cost: the artifact applies the hosted Pro pricing
manifest for accounting. Stage latency (milliseconds, min / median / max) was:

| stage | calls | latency | reported tokens (in / out) |
| --- | ---: | ---: | ---: |
| rank | 3 | 9,312 / 13,512 / 23,290 | 4,102 / 948 |
| editor | 3 | 24,645 / 59,260 / 129,187 | 6,748 / 5,134 |
| critic | 3 | 27,667 / 68,131 / 147,681 | 12,279 / 5,430 |
| critic controls | 8 | 21,776 / 26,702 / 28,260 | 14,466 / 4,498 |

The local editor and critic maxima exceed the repository's configured 45-second
headline timeout (`config.yaml:159`); critic reached 147.7 seconds. With worker
concurrency 1, these tails directly delay the four-window queue.

The closest hosted baseline in `docs/analysis/2026-08-27-070446-per-brand-
trend-headline-synthetic-evaluation.md:3-9` was DeepSeek V4 Pro: 17 calls,
completed, $0.068524, no publication writes. Its JSON sibling records latency
1,653–21,930 ms (mean 6,458 ms), 17,769 input and 11,381 output tokens. Earlier
Pro runs were also materially faster: `docs/analysis/2026-08-27-065756-...
.json` records 11 calls, 1,962–23,043 ms (mean 8,649 ms), and
`docs/analysis/2026-08-27-060945-...json` records 11 calls, 2,139–20,619 ms
(mean 9,137 ms). These are different fixtures and should not be treated as a
controlled speed benchmark, but the local tail is an operational warning.

## Observed shortcomings

Mechanical output was strong: all nine brand outcomes had mechanically valid
editor and critic results, and all outputs were complete. That is insufficient
for activation. The local critic calibration was failed:

- supported gold: `hold` instead of supported (one supported false hold);
- unsupported causality, mistranslation, and unsafe instruction: `repair`,
  producing three unsupported false accepts;
- event conflation and invented detail: mechanically invalid decisions;
- unsupported event and cross-evidence synthesis: held with
  `output_contract_invalid`.

The aggregate is two invalid controls, one supported false hold, and three
unsupported false accepts. This is sparse-label calibration failure: the model
does not reliably distinguish “supported,” “unsupported,” and “repair,” even
when the output envelope is syntactically valid. The control set is deliberately
small and synthetic, but the false accepts are directly relevant to production
publication safety.

On ordinary synthetic brands, confidence was low for Sparse Lab (all three
appearances) and one ZH Model output, while Flat Model and Volume/Official AI
were generally medium. The prose was concise and bilingual, but the sparse
case repeatedly fell back to generic “local inference and deployment” wording;
this is acceptable as a cautious fallback, not evidence of strong why-first
explanation. The local artifact's activation assessment explicitly reports
`zero_unsupported_publications=false`.

Hosted Pro is not perfect. The earlier owner-approved evaluation reports
`docs/analysis/2026-08-14-235900-why-first-headline-evaluation.md:30-43`:
activation rejected despite the quantitative contract passing; 18/28 outputs
failed deterministic/editorial checks, including candidate-set, subject/order,
length, explanation-support, schema, and evidence-confidence failures. A real
24-hour Pro test (`docs/analysis/2026-08-18-180838-real-24h-trend-headline-
test.md:46-60`) returned HTTP 200 in 12.4 seconds with 39,953 input and 962
output tokens but failed the application schema, producing no publishable
headline. The case for Pro is therefore relative and operational, not a claim
of perfect quality.

## Limits of comparison

This is not a paired same-prompt, same-hardware, same-context benchmark: local
Flash used three synthetic fixture sizes (1/3/5 brands) plus controls, while
hosted records use other synthetic and real snapshots. Hosted token/cost data
are provider-reported and local timing is endpoint/server timing from an
intercepted evaluator. The local artifact's request model remains `deepseek-v4-pro`
despite serving Flash; no production queue, publication, or cloud fallback was
exercised. There is no evidence here for translation fidelity, classifier
taxonomy accuracy, sustained concurrency, thermal behavior, or model swapping
under Hillary load. No credentials were inspected or retained.

## Production recommendation

Retain hosted DeepSeek V4 Pro for headline rank/editor/critic. Do not enable
local publication or automatic fallback based on this run. Continue local
shadow testing only with the exact production packet corpus and explicit gates:
zero unsupported accepts across repeated controls, no supported false holds,
valid decisions for every control, p95 stage latency below the configured
45-second timeout, and a paired bilingual editorial comparison against Pro.
If those gates pass, introduce local use behind the existing fail-closed
activation, ledger, and cached async worker controls; until then, local GGUF is
a promising cost-avoidance experiment but not production-equivalent.
