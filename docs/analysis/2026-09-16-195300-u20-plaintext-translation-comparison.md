# Plain-text translation comparison and remaining quality failures

Date: September 16, 2026 JST. Canonical plan: [AI enrichment](../plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md), U20. [Machine-readable exhibit](2026-09-16-195300-u20-plaintext-translation-comparison.json).

## Result

Plain-text requests and source-language copying reduced tokens and cost, and fixed one recurrent omission. They did **not** establish sufficient translation quality for a model switch: 0731 still removed the repeated half of a bilingual post, and both models altered a number in another post. No runtime provider, feature flag, staging deployment, or production setting changed.

## Same 45 posts, different request shape

The corpus contains 15 English, 15 Simplified Chinese, and 15 Japanese sources. Each arm ran serially; the independent provider arms ran at the same time. The new shape copies the source locale exactly and sends one post per target language, yielding 90 calls per arm. There were no automatic retries or database writes. Each arm was capped at $0.50, with conservative preflight bounds of approximately $0.326.

| Model and shape | Structurally complete posts | Calls | Output tokens | Total time | Slowest request | Translation cost |
|---|---:|---:|---:|---:|---:|---:|
| 0731, prior JSON batches | 45/45 | 3 | 46,394 | 14m36s | 478.120s | $0.009265 reported |
| 0731, plain text | 45/45 | 90 | 29,211 | 12m40s | 86.635s | $0.007230 reported |
| Incumbent, prior JSON batches | 45/45 | 3 | 46,806 | 3m09s | 100.511s | $0.056446 estimated |
| Incumbent, plain text | 45/45 | 90 | 30,561 | 3m25s | 13.829s | $0.046534 estimated |

0731 output tokens fell 37.0%, cost fell 22.0%, and time fell 13.2%. Incumbent output tokens fell 34.7% and cost fell 17.6%, while time increased 8.7%. Both new arms used 32,868 input tokens and had zero request errors. All 45 native source fields per arm were byte-exact code copies. These are observed sequential timings, not measured production throughput with three concurrent workers.

At this shape, 0731 translation inference was about 6.44 times cheaper than the incumbent, not the owner's desired tenfold reduction. This deliberately balanced diagnostic sample is not a production-volume or monthly-cost projection. Costs exclude review-agent work and wallet purchase fees. The direct endpoint does not return billed cost; estimates use its reported uncached input and output at $0.30 and $1.20 per million tokens, with cache reads at $0.006 (none in this run). Public pricing receipts are in each result artifact; the [DeepSeek price page](https://api-docs.deepseek.com/quick_start/pricing/) is the source of the direct estimate.

## What improved, and what still failed

Parent inspection verified that post `2079629240996155513` now retains both previously omitted paragraphs in 0731 Chinese and Japanese: the author has seen this pattern before, and middle-level researchers quietly update their profiles after leadership departures. English is now a deterministic source copy.

Post `2096881764480561562` contains Chinese text followed by a Japanese-original section. The incumbent preserved both sections in its new English and Japanese outputs. 0731 still deduplicated them: its English output jumps from “(Japanese original text)” to the footer, and its Japanese output also drops the introductory source URL. A nonempty response is therefore insufficient evidence of completeness.

Post `2095737515894313379` says “10.9 trillion tokens.” In the incumbent Chinese headline it became `109万亿`, a tenfold increase. In the 0731 Japanese body it became `100億`, or 10 billion. Both are confirmed quantity-preservation failures, even though other occurrences in the same output were correct.

For post `2093192147700977838`, 0731 returned the unchanged Japanese post in the English target field. Its pronunciation examples may remain Japanese, but the surrounding prose still needs translation.

## Blinded automated review

Two fresh Terra reviewers assessed 180 non-native translations without model identities: 60 pairs per target locale, randomized behind opaque case IDs. One reviewer handled English and then Japanese; the other handled Chinese. Native identity copies were checked mechanically and excluded from these semantic rates. Inputs, rubric, outputs, hashes and the withheld mapping are retained under the run directory.

| Target | 0731 fidelity flags | Incumbent fidelity flags | 0731 readability passes | Incumbent readability passes |
|---|---:|---:|---:|---:|
| English | 6/30 | 2/30 | 29/30 | 30/30 |
| Simplified Chinese | 2/30 | 3/30 | 30/30 | 28/30 |
| Japanese | 5/30 | 5/30 | 29/30 | 26/30 |

These are preliminary automated judgments, **not human gold or an accuracy estimate**. Parent review caught overstatements: the source itself contains the awkward “ready people never launch” maxim, Japanese does not specify researcher plurality, and katakana-only names do not establish a unique English spelling. Numeric token differences can also reflect ordinary localization. The report retains the original review rather than silently rewriting its scores. The independently verified omissions and changed quantities alone are enough to keep the existing U20 invariant gate open.

## Implementation, checks, and next step

Runtime checkpoint `e2a439e` adds raw-text adapters, deterministic native copying, isolated target-language failures, exact literal persistence, and retained usage on failed artifacts. It also saves the already-tested opt-in 0731 classifier dependencies sharing those files. Harness checkpoint `c6f6c55` preserves the bounded evaluation machinery and prior JSON comparison harnesses.

The runtime regression run passed 174 tests, including 24 required PostgreSQL checks with no skips. The failure-accounting follow-up passed all 14 artifact-lifecycle checks, and 19 evaluation-harness tests passed. The new review page passed the required tabbed builder and real Chromium checks: 45 tabs, one visible post, three locale outputs, independent pane scrolling, no horizontal overflow and no browser errors. It displays the newly measured translations alongside explicitly labelled, unchanged commentary from the previous experiment.

Because omissions persisted, the previously deferred paragraph guard is now being tested as an **opt-in** protocol. It adds short source-collision-free paragraph markers inside the same single-post/single-language call. Code requires every marker in order and reassembles the original separators; missing, duplicated or reordered sections fail instead of being silently published. This does not add one call per paragraph, and it cannot by itself prove correct numbers or meaning. A separately frozen four-call 0731 probe covers the two known omission posts before any full-cohort rerun or runtime activation.

## Evidence locations

- Frozen plain-text experiment: `.context/u20/plaintext-translation-20260916-192900/`.
- Each arm's `result.json` includes raw usage, requests, timings, result rows and source-copy checks; raw response files are retained separately.
- `comparison-summary.json`, `audit.json`, `blinded-review-summary.json`, and `blind-review-manifest.json` preserve measured and reviewed evidence.
- Review: `.context/u20/plaintext-translation-20260916-192900/review/plaintext-translation-review.html`.
- Earlier comparison: [raised-ceiling repeat](2026-09-16-190600-u20-raised-ceiling-repeat.md).

The selected classifier architecture and its separate quality gates are unchanged. Translation and commentary quality gates remain open; no new owner review is required by this experiment.

## Targeted paragraph proof completed

The separate `paragraph-translation-probe-20260916-195500` execution returned
4/4 accepted responses and 2/2 complete posts in 75.424 seconds, with no retries.
It used 5,251 input and 4,848 output tokens and cost $0.00118770 reported.
The conservative reserved bound was $0.03304664; the incumbent arm was not run.
Parent inspection confirmed all 24 paragraphs of the first post and all 44
paragraphs of the bilingual post. The previously dropped Japanese-original
section and introductory URL are present in both relevant translations.

The bilingual Japanese output retains 87 source lines; its English output
has 130 lines because the model inserted extra blank lines around blocks.
Code restores source separators but preserves the returned block content,
so marker completeness must not be described as exact line-count preservation.
The four-call success does not overwrite the original 45-post result or close
the number, entity, target-language, readability or runtime-capacity gates.

The opt-in guard and targeted harness passed 53 focused tests, including
14 required PostgreSQL tests with no skips. Default plaintext and classifier
behavior remain unchanged. The next full evaluation should follow semantic
constraint fixes; do not spend another 90 calls merely to repeat known
number/target-language failures.
