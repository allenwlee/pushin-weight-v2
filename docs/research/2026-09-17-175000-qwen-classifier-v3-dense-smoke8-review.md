---
title: Qwen classifier v3 dense smoke-8 review
date: 2026-09-17
type: experiment-review
---

# Qwen classifier v3 dense smoke-8 review

V3 tested a substantive response-shape change, not a longer version of v2:
each classification axis was a complete boolean map and the local adapter
would only unfold validated flags into the existing taxonomy arrays. It never
adds `nationalism` or changes a country stance. The experiment fails its
delivery gate, but the raw rows show why.

## Transport and accounting

All four Alibaba-only calls finished with `stop`, no fallback or retry. Each
used the saved 2,048-token reasoning setting and reported exactly 2,048
reasoning tokens. Latencies were 35.2–50.2 seconds; this is much slower than
v2's 4.4–7.0 seconds. Reported cost was $0.00211992 against the $0.00496206
reservation. The raw artifact is
`.context/model-task-20260917/qwen-classification-v3-dense-smoke8/attempt-1.consumed.json`.

All eight sources are delivery errors because every raw response fails the
same local dense adapter rules. This is not a join or slot-mapping bug:

| Call | Raw failure | Adapter behavior |
| --- | --- | --- |
| First content batch | D02–D05 have every Audience Topic flag false despite `classified`; D01 also has no `cost_performance` even though v2 found it. | Rejects the batch because a current-topic result must contain an explicit topic or `none`; it does not silently introduce `none`. |
| First brand batch | D03 says `nationalism=false` while `china_national_stance="anti"`. | Rejects the batch; directional stances require an explicit nationalism flag. |
| Second content batch | Every classified decision has all Audience Topic flags false. | Rejects the batch for the same missing-sentinel state. |
| Second brand batch | It returns `P01_D01_deepseek`-style decision keys instead of the frozen D01–D05 keys, and assigns `unknown` country stances with `none` geopolitical mode for D01/D02. | Rejects before semantic projection because fixed slots are not preserved; the country states would also be invalid. |

The raw content nevertheless confirms that expanded axes can change choices:
it finds Qwen openness and the Meetup question, and it adds DeepSeek CFO
`news_reporting`. It also produces obvious semantic errors: the distillation
allegation becomes `business_finance`, the DeepSeek security CVE becomes
`other`, and the MiniMax hands-on post gets `agents_tools` despite no agent
evidence. The dense map therefore did not provide a quality win that would
justify moving beyond smoke.

## V4 direction

The diagnosis is representation inflation, not an adapter defect. Full named
maps consumed 2,848–4,321 output tokens and encouraged omitted sentinels and
invented slot identifiers. V4 should retain per-axis exhaustive selection but
use fixed-order bit vectors: one compact `0`/`1` string per axis, with a
length pinned to the published enum order. The adapter can verify every bit,
the `none`/`unavailable` invariants, and the original D/P slots before
projecting to taxonomy arrays. This keeps the two existing roles and avoids a
third repair call. It must still reject an invalid vector rather than treating
the compact representation as permission to manufacture a semantic answer.
