# Gemini commentary v3 regression145 independent source review

Reviewed 2026-09-17 directly from the two source-only packets before consulting earlier commentary assessments. All 145 supplied source/context records and all 435 locale outputs received an explicit status. Both packets report zero transport and structural errors.

The old45 cohort has five confirmed erroneous sources: three material and two minor, for **[5,5]**. The material cases say Nvidia acquired Poolside when the source only says Nvidia made a $6 billion check and hired people; assign the quoted lyric-tool workflow and its unsupported causality to the reply author; and reverse the Japanese `こいつ` reference after Qwen3-Coder-Next matches DeepSeek. The minor cases attach a stored-quote campaign to the reply author and reverse the stored quote's speed direction in Chinese. The record preserves the initial seven-source independent result and its later parent source/context adjudication in `review_amendment`.

The initial random100 independent record found six confirmed sources—four material and two minor—and four source-only ambiguities, **[6,10]**. It is retained at `review-gemini-v3-commentary-random100-independent.json`, but its four uncertainty entries were independently rechecked against the frozen packet and saved live report.

The parent amendment confirms that all four packet output dictionaries exactly match the saved live result. It changes two former uncertainties to material errors: `2100239765429801078` invents a denial of paid promotion where spam source text only supports account/software promotion, and `2100346971144036571` invents a Qwen release from a tokenizer-based identity guess. The earlier latter record quoted a different Mistral post. The remaining `pi` and Italian-pronoun records stay unresolved. The six original confirmed records do not overlap the two additions. Random100 is therefore **eight confirmed sources** (six material, two minor), two unresolved sources, **[8,10]**, with zero coverage failures. Locale totals are 272 good, 18 material, four minor, and six unresolved fields.

Across both cohorts the amended direct-review interval is **[13,15]**: 13 confirmed candidate sources and two unresolved sources. The incumbent results remain separate: random100 has nine confirmed (five semantic and four coverage) plus one unresolved source, while old45 has three coverage failures. Old45's 5-versus-3 result fails that regression cohort; this report does not make a qualification decision. Detailed exact spans and per-locale statuses are retained in `review-gemini-v3-commentary-old45-independent.json`, `review-gemini-v3-commentary-random100-independent.json`, and [the parent amendment](../../.context/model-task-20260917/review-gemini-v3-commentary-random100-parent-uncertainty-amendment.json).

## Later paired-control amendment — Gemini commentary v4 no-reasoning random100

This report preserves the original v3 regression145 review history above. The
new owner-authorized v4 control is a separate, identity-free random100 run
with the same source/context, source-bound prompt, schema, model, route,
concurrency, timeout and output cap as v3; only the reasoning request changes
from enabled (2,048 tokens) to disabled. Parent reconciliation of two new
full source-only reviews records **21 confirmed affected sources**—13 material
semantic, seven minor semantic, and one incomplete-content source—and four
uncertain sources, **[21,25]**. Across 300 locale fields: 229 good, 37
material, 19 minor, three incomplete, and 12 uncertain. The incomplete
three-field source `2100404047882727911` ended with `stop` after 83 completion
tokens, rather than reaching the 8,192-token cap; valid JSON delivery does not
make it a semantic success.

For the like-for-like paired comparison, a versioned review of the existing
reasoning-enabled v3 output now records **10 confirmed +3 uncertain, [10,13]**,
superseding the earlier 8+2 random100 assessment while retaining its raw
outputs and prior review. All ten confirmed sources are shared with v4; v4 has
11 confirmed-only sources and v3 has none. The unresolved capacity case
`2100281384351015367` remains unresolved because its wording can denote either
comparative evidence or workload causation. The disabled run's actual Gemini
receipt is $0.0069008 versus v3's $0.0299522 (76.96% lower), with 1.481s versus
5.199s median request latency and 50.731s versus about 176s artifact wall
time. It also reports eight rather than 114,584 reasoning tokens. Those cost
and latency gains do not compensate for the higher reviewed error count. The
paired experiment is closed without a quality pass, qualification decision, or
runtime activation.

The controlling records are [the reconciled v4 review](../../.context/model-task-20260917/gemini-commentary-v4-no-reasoning-r113-random100-20260917-220100/parent-reconciled-review.json), [the paired comparison](../../.context/model-task-20260917/gemini-commentary-v4-no-reasoning-r113-random100-20260917-220100/parent-paired-comparison.json), and the retained versioned [v3 paired-control review](../../.context/model-task-20260917/gemini-commentary-v3-r113-random100-20260917-184300/parent-paired-control-review.json).

