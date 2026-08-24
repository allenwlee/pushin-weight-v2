# Real 24-hour why-first headline test

Date: 2026-08-18 18:08 JST  
Window: 2026-08-14 00:01Z through 2026-08-15 00:01Z  
Source: local read-only PostgreSQL shadow containing the latest available real snapshot (as of 2026-08-15)

## Packet check

- Coverage: sufficient for both selected and prior windows
- Comparison: allowed
- Candidates: 6
- Evidence excerpts: 92 total (48 / 4 / 12 / 4 / 12 / 12)
- Provider packet: 125,576 bytes of the 131,072-byte limit

## Quantitative evidence

Every candidate had a volume comparison. The source snapshot had no classified
post-type, discourse, or sentiment rows, so those mix families supplied no
non-zero percentage-point evidence in this run.

| Candidate | Selected posts | Prior posts | Volume change |
| --- | ---: | ---: | ---: |
| DeepSeek | 4,743 | 6,490 | -27% |
| Qwen | 2,456 | 1,013 | +142% |
| Zhipu GLM | 1,095 | 293 | +274% |
| MiniMax AI | 1,428 | 1,293 | +10% |
| Tencent Hunyuan | 25 | 26 | -4% |
| Meta Llama | 181 | 134 | +35% |

## Content cues available to explain the movement

The excerpts were real post text and did contain usable cause signals, even
though the structured mix fields were empty:

- Qwen: an official-looking Qwen3.8 open-weights release and download/build invitation.
- MiniMax: hands-on local setup combining MiniMax video/music with other local tools.
- Tencent Hunyuan: a free local AI-video repository featuring Hunyuan Video.
- DeepSeek: comparisons involving DeepSeek V4 Flash pricing and competing models.
- Zhipu GLM: discussion placing GLM 5.3 among a cluster of newly released models.
- Meta Llama: mostly broad LLM/research references; the brand-specific cause is weak.

These are evidence cues, not confirmed causal claims. The headline should say
what the posts indicate, not assert an external release unless an official
source is present.

## Provider run

One bounded DeepSeek request was made against this packet. The API returned
HTTP 200 in 12.4 seconds (39,953 input tokens; 962 output tokens), but the
generated JSON failed the application output-schema validator with
`headline_output_schema_invalid`. Therefore this run produced no publishable
headline and no observations/claims to review.

## Conclusion

The packet can now carry real content-based “why” signals, and every candidate
has quantitative volume color. However, this snapshot cannot test the intended
discourse/sentiment percentage claims because its classification coverage is
zero. The immediate test failure is at provider-output validation, before
headline review; a follow-up should capture and diagnose the rejected JSON,
then rerun once the schema issue is fixed.
