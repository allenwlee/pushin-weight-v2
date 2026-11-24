# Smaller classifier catalogs cut input cost, but neither qualified for production

The best candidate was B, which shortens the individual brand entries and keeps the standing set of 182 brands plus batch-specific additions. On identical completed batches it used 76.2% fewer input tokens and produced five more judgments that agreed with the blind review. It also left four fewer post-brand pairs with a usable post type and sentiment. Keep the current production setting. C, which also removes the standing set, lost 33 usable judgments against the current prompt.

## Results on the same 140 posts

These seven batches contained 160 post-brand pairs. All eight requests in each batch returned an answer. An invalid answer counts as a miss. The production publication code ran against an isolated local PostgreSQL fixture. Each version started with the same posts and associations and its transaction was rolled back.

| Version | Usable type and sentiment / 160 | Matches blind review / 160 | Input tokens | Estimated cost per 1,000 usable posts |
|---|---:|---:|---:|---:|
| A · current | 149 | 88 | 1,098,433 | $0.274 |
| D · identical repeat of A | 142 | 87 | 1,098,433 | $0.417 |
| B · short entries, 182-brand minimum | 145 | 93 | 261,633 | $0.141 |
| C · short entries, batch-selected brands | 116 | 75 | 137,839 | $0.100 |

Three reviewers graded source text and supplied context for all 232 pairs before seeing model answers. Each pair had one reviewer. Agreement requires a supported post type and sentiment, or a correctly unresolved judgment. Requiring every assigned type to be supported gave A 72, D 69, B 77 and C 68 matches. This is an automated independent assessment, without human adjudication. The two identical controls show ordinary answer variability, as well as different cache costs.

| Comparison | Usable pairs lost / gained | Change in retention, points (one-sided 95% lower bound) | Blind matches lost / gained | Change in agreement, points (lower bound) |
|---|---:|---:|---:|---:|
| D vs A | 16 / 9 | −4.38 (−13.25) | 14 / 13 | −0.62 (−8.55) |
| B vs A | 13 / 9 | −2.50 (−9.55) | 12 / 17 | +3.12 (−3.85) |
| C vs B | 37 / 8 | −18.12 (−41.88) | 29 / 11 | −11.25 (−29.09) |
| C vs A | 41 / 8 | −20.62 (−43.64) | 29 / 16 | −8.12 (−20.37) |

Bounds use 10,000 paired resamples of whole batches. The plan requires no observed decline and lower bounds above −2 points. Seven independent batches give limited precision. Neither candidate passes. The separate ownership challenge set was outside this experiment.

## What went wrong

In batch 08, C returned an extra field called `note` in decision D11. The current parser requires exact fields on every decision. This single extra key invalidated the content reply for all 20 posts, affecting 24 post-brand pairs. Both provider calls completed. A and B each returned valid classifications for all 20 posts in that batch. This identifies the immediate cause of the loss in this run. It does not establish how often the same formatting error would recur under any prompt.

Source judgments also varied. In post 2125132785639981133, someone tried MiniMax on their PC and could not run it. A retained hands-on usage and negative sentiment. C and the repeated control both returned insufficient context. On post 2125132528902095008, C inferred hands-on usage for MiniMax from a list of art-tool tags. A and B kept a neutral other mention. Blind review supported the latter.

## All 200 posts and spend

The first 200 posts from the frozen November 24 reconstruction contained 232 real post-brand pairs. Ten batches of 20 posts each went through four prompt versions and two roles per version. Of 80 physical requests, 75 returned usage and five received HTTP 429. No requests were retried. Rate-limited batches stay in the full counts below. Removing a batch from the matched comparison required removing it for all four versions.

| Version | Rate-limited requests | Usable pairs / 232 | Context missing | Absent | Usable posts / 200 | Provider estimate on returned receipts |
|---|---:|---:|---:|---:|---:|---:|
| A | 3 | 173 | 2 | 57 | 152 | $0.047412 |
| D | 1 | 185 | 4 | 43 | 170 | $0.075584 |
| B | 1 | 188 | 6 | 38 | 162 | $0.024393 |
| C | 0 | 178 | 10 | 44 | 159 | $0.015088 |

Provider estimates total $0.16248. The conservative pre-dispatch reservation across all 80 calls was $2.341626 against the $2.50 hard cap. The 429 replies carried no spend figure. An invoice reconciliation and a comparable-cache billed-cost verdict remain unavailable.

Reproduction materials are in the plan worktree under `.local/feed-catalog/paid-200-v1/`. The 80 original receipts, three blind rubrics, merged decisions, locally published reader states and `evaluation.txt` are retained. The earlier [local reconstruction](2026-11-24-175831-feed-catalog-local-comparison.md) describes the cohort and regression tests. The experiment changed no production data or settings.
