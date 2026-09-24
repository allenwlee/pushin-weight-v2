# 0731 headline finance-context tuning — cycle 1

Date: 2026-09-24. Worktree: `feat/headline-0731-architecture`.
Canonical plan: [headline architecture](../plans/2026-09-24-060052-feat-headline-0731-architecture-plan.md).
Status: tuning in progress; no deployment or qualification claim.

The headline generator is fixed to direct DeepInfra `deepseek-ai/DeepSeek-V4-Flash-0731`, priority tier, reasoning disabled, two brands per editor/critic request, and concurrency three. No competing generator is called. Historical experiment artifacts remain unchanged.

## Implemented before this cycle

- U7: an explicit provider field allowlist, deduplicated text, typed facts with shared scopes, removal of suppressed comparisons, phrase cleanup, source-level brand relevance, and a smaller ranking packet (`dcc704e`).
- U8: deterministic observed activity/participation facts and conservative historical eligibility. Live collection-regime proof is unavailable, so normalized historical context remains unavailable (`a47aa27`).
- U9: response schema 3 binds each cited fact to its numeric value, unit, and brand/time scope; the critic remains responsible for whether the prose actually follows from that fact (`c60194e`). PostgreSQL regression tests cover the actual snapshot → durable calls → publication → EN/ZH/JA serving path.

## Round 1

The diagnostic input reuses archived failures for Kuaishou/Kling, StepFun, SenseNova, Upstage, and Yi. Nine eligible brand/window cases plus eight critic controls yielded 20 provider calls. This is deliberately reused diagnostic evidence, never a new holdout.

| Measurement | Result |
|---|---:|
| Calls completed and mechanically valid | 20/20 |
| Eligible brand/window decisions | 9/9 |
| Missing locale outcomes | 0 |
| Input / output tokens | 188,100 / 30,814 |
| Provider-billed cost | $0.02412558 |
| Entire run, including controls | 239.9 seconds |
| One-day / seven-day diagnostic window | 82.3 / 70.6 seconds |

All eight controls were repaired, including supported gold. The seven deliberately unsupported controls require independent inspection of their replacement narratives. A repair is neither automatically a failure nor automatically a success. The revised evaluator preserves the replacement and leaves activation closed pending that review.

No format failures occurred, and attribution improved: the VAST funding figures were not assigned to Kuaishou, and unrelated Yi keyword matches were acknowledged. Remaining semantic problems included calling a 12.4% historical promotional flag potentially dominant, assigning combined official/staff post counts to one account, and presenting contradictory openness claims without sufficiently clear attribution. Round 2 adds generic rules for these problems, rather than rules naming particular diagnostic posts.

Artifact: `.context/headline-finance-cycle1/round1/candidate-artifact.json`, SHA-256 `5d12cac87022ebac179c444908b367caacefec4812937fa5655ded9ff5b11a75`.
Diagnostic input SHA-256: `57c979ac986d5c744b3526130f2eabc755025fb760ff290ef7d5e3f468071f97`.

## Packet measurement

On the same 47 archived eligible dossiers, compact JSON decreased from 1,510,032 to 939,801 UTF-8 bytes: **37.76%**. All selected evidence IDs and their order were preserved. This isolates representation changes: it excludes prompt text and new finance facts, and is not a token or latency claim. Full-stage measurements including finance remain due.

## Reserved fresh source corpus

A separate, read-only production subprocess ran the current snapshot builders under PostgreSQL repeatable-read transactions. Previously reviewed selected evidence IDs and exact excerpt hashes were excluded before evidence selection; aggregate facts were unchanged. The source packet is reserved for post-lock validation and has not been used for tuning.

- As of: `2026-09-24T10:44:21+00:00`.
- One day: 35 brands, 21 eligible; build time 52.594 seconds.
- Seven days: 35 brands, 23 eligible; build time 93.491 seconds.
- Source SHA-256: `d78040b64855c55608e493dea5ccb6e25f992cd4d0406cc147d87a37895b3999`.
- Reproduction and private artifacts: `.context/headline-finance-cycle1/` on fuchitalee.

## Verification so far

U7/U8 focused PostgreSQL checks passed 136 tests. U9's broader focused run passed 346 tests and exposed one obsolete oversized-packet fixture; that fixture was enlarged to remain genuinely oversized after compaction, then all 10 affected tests passed. The revised evaluation harness passed 26 focused tests. Changed implementation files pass Ruff and `git diff --check`.

Production remains unchanged. Fresh semantic review, calibration closure, latency/cost qualification, Render memory/queue measurement, staging and exact-SHA production verification remain required.

## Round 2 and the third correction

Round 2 completed all 20 transports for $0.02215863 billed, with 192,018 input and 29,199 output tokens, in 233.3 seconds including calibration. One editor response incorrectly cited SenseNova evidence in StepFun's section. The ownership validator rejected it, and the critic did not publish that draft as valid. This is a semantic cross-brand error, not something that may be normalized away.

Round 3 retains the two-brand graph but derives the structured response schema from each request: every brand branch permits only its own evidence IDs, fact IDs, and exact measurement tuples. The response remains schema 3; named request profiles are `headline_editor_v4` and `headline_critic_v4`. Templates are copied for every request so source IDs cannot leak between requests. Final mechanical validators and the semantic critic remain mandatory; constrained citations cannot prove that prose is true.

The full wire request, including this dynamic schema, now participates in preflight and reservation estimates. Round 3 reserves 20 calls, 226,348 estimated input tokens and $0.063032; its largest estimated request is 82,016 bytes. Reasoning remains disabled. DeepInfra's [structured-output documentation](https://docs.deepinfra.com/chat/structured-outputs), checked 2026-09-24, documents strict JSON Schema output and also cautions that structural compliance does not establish factual accuracy.

The inference lock records configuration and implementation hashes before transport. Existing output directories cannot be silently overwritten, pricing evidence older than seven days fails active DeepInfra preflight, and alternate generator arms are rejected.

Round 2 artifact SHA-256: `89edf08628346e6dde772d99490add742a29880c28fafdd565e264cf90b45e47`.

## Cycle 1 outcome and cycle 2

Round 3's dynamic citation schema completed 20/20 calls, all mechanically
valid, with nine eligible decisions and no missing locales. Billed cost was
$0.02349810 (190,953 input and 28,755 output tokens); wall time including
controls was 289.8 seconds, with one-/seven-day windows at 86.6/101.0 seconds.
Cycle 1 cost $0.06978231 in total. This closed the observed cross-brand citation
failure, but wording still generalized from selected examples to the whole
collected corpus and strengthened planned funding into completed funding.

Cycle 2 round 1 added explicit nonrandom evidence scope and concise wording
rules. All 20 transports and formats again passed, for $0.02317392 billed
(194,614 input, 27,294 output; 407.7 seconds including controls). Semantic
review still found incorrect scope and tense. Its artifact SHA-256 is
`0f92cb7204e2b9c1c96c6c58fb22ce7b67f6e8c6e620012c16f784ee9b93f4f3`.
A source-check correction matters here: the Seedance revenue statement was
absent from the shortened English excerpt but present in the supplied Chinese
translation. It is not an unsupported claim merely because the excerpt omits
it; relevance, attribution and the funding headline's tense remain separate
issues. Reviewers are instructed to inspect all supplied source text.

Cycle 2 round 2 replaces the accumulated writing instructions with a shorter
source-first contract. The dynamic schema now requests citations and exact
measurements before proposition text, and propositions before the visible
headline. The critic reads the dossier before comparing the draft. This keeps
the same three stages, two-brand batches, response fields, validators, and
0731 route. The wire/profile order and prompt version (`finance-v5-ja`) are
captured in its configuration lock. Thirty-eight focused tests passed before
this paid run. No production behavior has been activated.

## Fresh review reservation and broader checks

The 24-case review manifest was frozen before fresh candidate output, with
four one-day and four seven-day cases for each of three independent reviewers.
Its SHA-256 is `d086a3bf0c7082f071b75f2404d6cbaac8a0511630bb924bbdf035bb83c51e2d`.
Both selected evidence IDs and exact excerpt hashes are disjoint from the old
qualification corpus. Reviewers receive sources and one candidate, without
model/configuration identity; no incumbent output is used. Raw review inputs,
receipts and judgments remain under `.context/headline-finance-validation/`.

A clean full repository run completed with **4,102 passing, 399 failing and 78
skipped tests**. It is not a passing full-suite claim. The same run on unchanged
`main` is being used to distinguish pre-existing failures from regressions;
all focused headline checks reported above passed. An earlier reused database
run encountered missing migration-seeded geography rows; the affected account
tests passed on a new test database, and neither that aborted run nor its
failures are counted as qualification evidence.

The unchanged-main comparison completed at `1a879e8`: 4,045 passed, 407
failed, 78 skipped. Every candidate failed test node also failed there; there
were no new failed nodes. The eight baseline-only failures concern historical
backfill scripts and are not credited as fixes from this work. Full logs and
`baseline-comparison.json` preserve this distinction.

Cycle 2 round 2 completed 20/20 valid calls for $0.02057877 billed, with
175,676 input and 20,667 output tokens. One-/seven-day diagnostic generation
took 64.2/69.7 seconds. It still produced unrelated company news for ambiguous
brand matches, so this is not a qualification pass. Round 3 adds short generic
counterexamples for ambiguous names, future investment and instruction-only
source text. It keeps the source-first schema and disabled reasoning.

The final focused implementation run passed **393 tests**, including **232
PostgreSQL-required checks**, with no skips or errors in that required set.
This covers headline generation/lifecycle, direct DeepInfra, configuration,
Render topology and Ollija. Two existing staticfiles warnings remain. The
source-first v6 wording has not yet received fresh semantic qualification.

Cycle 2 round 3 completed 20/20 mechanically valid calls for $0.02010798,
179,349 input and 20,643 output tokens. Windows took 59.9/72.1 seconds.
The Yi one-day output still described Xiaomi, and the instruction control
reported the adversarial instruction as news rather than discarding it.
Cycle 2 therefore remains `improve_0731`. Cumulative billed tuning cost through
six rounds is **$0.13364298**. The next finite cycle changes the critic contract:
identify the subject and quote source support before evaluating the draft.
This adds a bounded, inspectable source check to the existing critic response;
it does not add calls, hidden reasoning, retries, or another generator.

## Cycle 3 — explicit source check before the critic verdict

The new critic request profile is `headline_critic_v5`, with response schema 4
and prompt `headline-critic-finance-source-audit-v1-ja`. Editor response schema 3
and the two-brand call graph remain unchanged. Before its verdict, the critic
must identify the source's subject, classify target-brand relevance, quote up
to four literal source passages, and list any draft errors. These fields stay
in the audit response, not the reader-facing headline.

The validator rejects invented or cross-brand quote support, approval despite
listed errors, and a publish decision when the critic itself says the target
brand is absent or incidental. Whitespace folding is the only quote matching
normalization. This proves literal source membership and self-consistency,
not semantic entailment; independent review is still required. Six new tests
failed before implementation and passed afterward, including fabricated quote,
wrong-brand ID, absent brand, ignored error and missing support. The combined
focused check passed 38 tests before the first paid cycle-3 run.

The inference lock now also records numerical thresholds and evidence policy
settings, in addition to prompt/profile choices and implementation hashes.
No production or staging route has been changed. Commits `dc0cb44` and
`0d38d05` preserve completed tuning infrastructure and safe status receipts;
cycle-3 changes remain under evaluation.

Cycle 3 round 1 recognized the unrelated Yi and Kuaishou sources and explicitly
identified the SenseNova contradiction. It completed 20 transports for
$0.01989387, but only 17 were mechanically valid: one editor measurement binding
and two literal quote checks failed. Some quote text was translated or had
spacing changed instead of being copied. Those results stay failed; they were
not normalized into successes.

Round 2 replaces model-written quotes with stable source-passage IDs. Code
splits the supplied text into bounded passages without changing any character;
concatenation reconstructs each original field exactly. The critic selects
IDs from its own brand, and the exact text remains in its captured request.
This avoids asking the model to copy or retranslate evidence. The critic still
judges relevance and meaning. Forty-six focused tests passed, including three
real PostgreSQL publication paths and checks that audit fields never appear
in reader-facing output. Editor schema remains 3, critic schema 4; the prompt
is `headline-critic-finance-source-audit-v2-ja`.

## Complete-message compaction measurement

A no-transport reconstruction compared the same archived 47 eligible brand/
window cases and 50 stage requests. Writer and critic evidence IDs and their
order were unchanged; critic draft prose was held fixed. New finance context,
source passages, and current prompts are included. Dynamic response schemas
are reported separately as wire bytes, not silently counted as message text.

| Stage | Calls | Prior message bytes | Current message bytes | Reduction | Current wire bytes | Prior measured input tokens |
|---|---:|---:|---:|---:|---:|---:|
| Rank | 2 | 502,294 | 357,664 | 28.79% | 396,500 | 144,965 |
| Editor | 24 | 1,497,194 | 1,063,514 | 28.97% | 1,437,418 | 408,036 |
| Critic | 24 | 1,649,369 | 1,352,167 | 18.02% | 1,803,036 | 449,635 |

Total message reduction is **23.99%**, meeting the diagnostic 20% target.
This is a byte result, not a token-saving claim: no new tokens were bought for
this reconstruction. The schema adds wire overhead; actual qualified tokens
and costs still require the fresh paid run. Reproduction:
`PYTHONPATH=. .venv/bin/python .context/headline-finance-cycle3/measure_packet_bytes.py`
(using the shared root `.venv` when the linked worktree has no local one).

### Cycle 3 final round and bounded cycle 4

Cycle 3 round 2 completed 20/20 mechanically valid calls for $0.01981809
(provider receipts), 189,316 input and 20,279 output tokens. It still assigned
one investor's RMB 1.4 billion to two investors, and withheld useful staff
content. Round 3 added numerical ownership checks, deterministic critic
sampling, and corrected the synthetic control's missing brand identity and
percent unit. Those fixture corrections do not retroactively pass earlier
rounds. Round 3 completed 20 transports, 19 mechanically valid responses,
191,297 input / 23,595 output tokens, billed $0.01741842. Window generation
wall times were 64.063 seconds (1d) and 63.840 seconds (7d), excluding SQL.
The supported control was approved and all seven unsupported controls repaired;
independent semantic review of repairs remains required.

The funding correction succeeded. The remaining invalid response classified
its replacement as incidental but attempted to publish it. That whole batch
was safely withheld, including an otherwise usable second brand. The critic
also still repeated an open-source assertion despite a conflicting official
reply. Artifact SHA-256:
`620ccef63cc6f804c34c29c2034e652c03fd05933f36600a8df453335f54739e`.

Cycle 4 is a new, explicit maximum-three-round correction cycle, keeping 0731,
three stages, two-brand batches and three concurrent workers. Its first round
clarifies that source relevance assesses the best supported replacement, not
only the faulty draft. Reviewed staff AI-work discussion can be attributed to
the staff account without inventing a person's identity or corporate title.
The source audit now records up to three disagreements using exact passage IDs
from both sides. This is a source-reading aid, not deterministic fact checking.
The frozen unseen corpus and review assignments remain unused and unchanged.

Cycle 4 round 1 completed 20/20 mechanically valid calls: 194,064 input /
24,402 output tokens, provider-billed $0.01757430, generation wall times
77.630 seconds (1d) / 86.997 seconds (7d). Artifact SHA-256:
`56049ab5c42640dcbb7fdcc5cc478cd3b6414ad7c339708e147386b6f6ac656f`.
It corrected staff attribution and the conflicting open-source assertions,
while preserving the planned financial amounts. Manual inspection found a
synthetic repair still overgeneralizing "conversation centered on" from two
examples, incomplete Japanese clauses inherited from the supported-control
fixture, and a literal Japanese rendering of "AI theater" in the Yi example.
Round 2 corrects the fixture in all three languages and adds brief instructions
for measured topic prevalence, equivalent factual clauses and idiomatic meaning.
The earlier fixture errors are explicitly harness defects, not new model errors;
the critic's failure to repair them remains recorded.

The broader current test run executed 232 required PostgreSQL checks with no
skips/errors: 465 passed, two failed. Both failures are the existing X-article
routing failures in `tests/test_headlines.py`, also present in the separately
run unchanged-main baseline. The round-2 focused regression run passed 41 tests.
The standalone readiness reporter additionally has 13 passing gate tests for
critical errors, missing/duplicate reviews, false holds, route/format failures,
actual billing, latency, memory and missing operational evidence. It cannot
emit `ready_0731` before every success criterion has supporting evidence.

### Owner-selected final-output measurement policy

After ten completed diagnostic rounds (200 transports; $0.20834766 billed), the
owner requested a pause and approved judging final output by severity. Cycle 4
round 2 was stopped at 2026-09-24 12:19:58 UTC with 18 completed-call receipts
logged and no final artifact; an accepted in-flight request may still be billed.
It is an interrupted run, neither a pass nor a failure. Its call entitlements
are not replayed. On resume, the generator remained at writer finance-v7 and
critic source-audit-v5, and the fresh source set entered first validation.

`final-output-severity-v2` keeps material factual failures as release blockers
and the five mean-quality thresholds at 4/5. Minor wording, harmless omissions
and mild qualitative scope issues are deductions. An existing critic's repair
of an invalid editor draft is measured as recovered, while raw failures remain
visible. Invalid final responses remain blockers. Fixture defects are separate
inconclusive controls and require fixture correction, not automatic generator
retuning. Sixteen readiness-policy tests pass. The old rubric and manifest were
archived before the new rubric was frozen; the 24 case assignments are unchanged.
New rubric SHA-256:
`b3e1304baba85be313f12b976625d51bbf0d9eb3a01ae31203dcd69508024be6`.
