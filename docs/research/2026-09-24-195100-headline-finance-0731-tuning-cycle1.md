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

### First fresh validation under the approved severity policy

The frozen 44 eligible brand/window cases completed 56 calls including eight
controls. Generation took 300.873 seconds for 1d and 312.192 seconds for 7d,
excluding the earlier read-only snapshot queries. Actual provider billing was
$0.08330256, with 699,606 input and 89,342 output tokens. Artifact SHA-256:
`d5bb69c76a2432c8464026d81f862d599e6bac1df297f1652b3b63a40c251d49`.
Three independent reviewers assessed their preassigned eight cases each;
review billing was $0.3959723, separate from generation cost. A missing local
`dotenv` dependency stopped the review runner before any HTTP request. Reusing
the existing literal environment loader fixed that launcher defect; prompts,
assignments and generated outputs did not change, and the code hashes were
recorded before and after the fix.

| Dimension | Mean / 5 |
|---|---:|
| Factual support | 4.208 |
| Proportionality | 4.417 |
| Why-first relevance | 4.000 |
| Secondary usefulness | 4.125 |
| Translation equivalence | 4.500 |

All eight repaired/control outputs passed independent source review, and all
five averages meet the target. The remaining substantive claim failures are
InclusionAI's “#1 among open-weight models” losing its comparison class, and a
Kimi narrative attaching an editorial's accusation/motive to the wrong action
and named target. These remain failures under the revised policy. Minor
wording, lead ordering and literal-but-understandable translations remain
deductions; they do not trigger new tuning.

Three critic responses failed the local audit-consistency checks, withholding
six brand results. These were contradictions between diagnostic annotations
and the verdict: incidental relevance with approval, or an error list with
approval. Some list entries actually said the draft was correct. The source
review found useful withheld material, so the availability gate still fails.
Cycle 5 is a maximum-three-round targeted correction: preserve comparison
classes and exact actor/action attribution; omit optional/style comments from
the material-error list; express the existing verdict-consistency rules in
the provider JSON schema. The local safety validator is retained unchanged.
[DeepInfra's structured-output documentation](https://docs.deepinfra.com/chat/structured-outputs)
supports strict schemas; this specific composition is additionally checked
against JSON Schema locally and in the bounded live run.

The first readiness report also treated absent reasoning-token telemetry as
positive evidence of a route failure. Twenty receipts omit that field; they
do not report positive reasoning usage. The transport already requires a
reasoning-disabled request and rejects reported positive usage. The corrected
report preserves unreported counts separately, rather than rewriting them as
observed zeros. The initial report remains intact, with a separately named
receipt-clarified result. Nineteen readiness tests and the focused 61-test run
pass (including three required PostgreSQL checks). No live route changed.

### Subsequent unseen validation and focused corrections

Cycle 5 used a new source freeze (`67045c0bd3bb6a97bad035360229613cd0842c07873e447dd96663a5714ee3a9`)
and 24 locked review assignments. All five rubric means exceeded 4/5, but
SC2 failed on three material cases: an invented named InclusionAI event (Q05),
unverified shared authorship between StepFun posts (Q09), and assigning a
group video-model ranking to Kling individually (Q21). SC3 passed. Generation
billed $0.03422916 for 1d and $0.04256235 for 7d, excluding controls. The
decision remains `improve_0731`; operational and deployment criteria were not
claimed.

Cycle 6 froze different selected post IDs and exact excerpts before querying
the read-only production snapshot. Its source SHA-256 was
`9b54189ba6df6135186eb9611b139faf0630133ad534bbc2d8bf196e4b229277`.
The 24 independent reviews found five material failures: Q26 mistranslated
Chinese `1折` (pay 10%, or 90% off) as 10% off; Q27 withheld an ERNIE
corpus-quality account-sale headline; Q30 removed a MiMo training-completion
hedge; Q32 withheld a supported Nemotron result; and Q41 attached a 4.3x
measurement too broadly. The secondary-usefulness mean was 3.708/5 and nine
final mechanical responses were unresolved. SC2 and SC3 failed. Generation
billed $0.03123684 for 1d and $0.03687480 for 7d, excluding controls. The
failed raw receipts and independent reviews remain in
`.context/headline-finance-cycle6/validation/`.

The ensuing correction narrowed the final writer to source spans and
deterministic discount glosses. It keeps unknown authors and measurement
owners separate, and it refuses a hold when a direct brand mention supports a
scoped report. The saved five cycle-6 failures replayed at 5/5 mechanically
valid and 0 independent critical failures in v22. The five earlier source
regressions also replayed at 5/5 mechanically valid, but independent review
found a new unverified shared-author statement in the StepFun case. The v23
and v24 combined ten-case replays exposed the same source-identity inference;
their mechanical invalidity is recorded, not counted as a pass. A narrowly
scoped, three-locale normalization now removes only observed unverified
shared-author wording while retaining each post's own claim. Any unrecognized
identity wording remains mechanically invalid. The next official combined
replay and fresh blind validation are still required before release.

An additional read-only production keyword check showed InclusionAI's `Ring`
and `Ming` keywords are both non-primary. A saved source post about Vocci,
Pebble Index 01 Ring, and Stream Ring had been marked as an explicit
InclusionAI mention solely because of `Ring`. The snapshot now excludes
non-primary ASCII keywords of at most four characters from its brand alias
evidence. For already-frozen packets, the final writer downgrades those short
non-identity matches to uncertain and removes them from editor hints. This
changes headline source attribution, not the underlying historical post-brand
rows or harvesting rules. The two-case v27 probe narrated the actual
InclusionAI mention rather than the unrelated ring article.

The complete v27 regression replay was 10/10 mechanically valid, but manual
inspection found a subtler unproven connection: the StepFun secondary said a
different post belonged to “the same test.” Because this fails the material
source-attribution requirement, the partly running v27 fresh generation was
terminated without a final artifact; its accepted provider receipts remain
in `.context/headline-finance-cycle7/validation/generation-v27-console.log`.
The next source-link correction covers that exact three-locale wording and
retains the two separate post claims. The v29 targeted StepFun output was
mechanically valid and omitted the unsupported connection. The full v29
regression and fresh validation were superseded by the source-only revisions
below; their partial receipts remain archived.

### Source-only writer revisions v31–v34

The v29 writer's ten saved outputs were reparsed through the v31 source-link
normalizer and independently reviewed as a **diagnostic**, not a release pass:
ten cases, no critical failures, and every factual-support score at least
4/5. The official v31 provider replay was 10/10 mechanically valid, but blind
review found two material failures. Q26's Japanese `1割（価格の10%）の割引` means
10% off instead of paying 10%; Q27 said a single post reported the 49-of-58
corpus count. The fresh v31 run was stopped after 26 accepted calls and
$0.04821273 billed, before a final artifact. Its partial receipts remain in
`.context/headline-finance-cycle7/validation/generation-v31-console.log`.

The next correction made corpus counts dataset-owned, supplied a literal
Chinese discount gloss, and added rejection checks. The v32 replay was stopped
after eight calls because Q26's final secondary omitted a separately sourced
addendum present in its source check, producing a mechanical mismatch. This
was an acceptable narrower final line, so the check now drops only an exact
independent-post addendum; it still preserves caveats. The writer also used a
second ambiguous Japanese discount construction, which the correction now
handles. Its eight provider calls billed $0.00788265.

The v33 replay was 10/10 mechanically valid. Blind review nevertheless found
two material issues: Q26's normalized Japanese line said “original price,”
although the source layered 1折 on an official price adjustment; Q27's
secondary claimed none of all 58 collected posts contained substantive ERNIE
news, while only six nonrandom examples were supplied. A diagnostic reparse of
those two saved outputs with the subsequent narrow correction received 5/5
factual/translation scores for Q26 and 4/5 for Q27, with no critical finding;
this does not qualify the new configuration. The v31, partial v32, and v33
regression generation costs were $0.00678006, $0.00788265, and $0.00657;
their v31/v33 blind review costs were $0.2488145 and $0.2347095, and the
two-case diagnostic review cost $0.0592635. Review spend is separate from
headline generation spend.

The v34 writer preserved the adjusted-price basis when the source stated one
and deleted only the exact unsupported all-post negative clause from a bounded
sample narrative. Its replay was stopped after eight valid calls ($0.00804051)
because Q26 used a spaced Japanese `1 割（価格の10%）の割引` variant that the prior
literal guard missed. A spacing-tolerant guard now detects and normalizes that
same price-meaning error; unrecognized forms still fail closed. The saved v34
raw response reparsed through this correction with the adjusted-price basis
intact.

The official v35 ten-case replay was 10/10 mechanically valid, with no hold.
Independent blind review found zero critical failures and every factual-
support score at least 4/5. Q26's why-first relevance remained 2/5 because
it led with a third-party platform milestone, a deduction to monitor on the
fresh set. Generation billed $0.007038 and the independent review billed
$0.2424995. This closes the saved-regression gate but does not establish fresh
quality or operational readiness.

A new, disjoint read-only production source freeze for fresh validation was
sealed at SHA-256
`b08740c4dc1213ed7dd7aac2c63ff5b4ace87f05be23797fe70c9463b607f94a`;
24 case/reviewer assignments were sealed before any v35 candidate output. The
locked v35 fresh generation is underway in
`.context/headline-finance-cycle8/validation/generation-v35`.

### Cycle 8 fresh result and source-isolation diagnostic

The v35 fresh generation finished all 46 planned calls with no provider
transport error. It produced 35 eligible terminal narratives, cost
$0.07262127 in provider-billed generation, and took 762 seconds. Three
independent reviewers found five material failures among the 24 assigned
cases: Meta Muse content treated as Meta Llama news; PrismML Bonsai metrics
attributed to Qwen; facts from one MiniMax post attached to another; an
official StepFun greeting expanded into unsupported thanks; and a supported
StepFun launch held after an invalid final-writer batch. Four final decisions
were held by two mechanically invalid critic batches. The five rubric means
still exceeded 4/5, illustrating why mean scores cannot override the zero-
material-error gate. SC2 and SC3 failed. The frozen output and preliminary
gate report remain in `.context/headline-finance-cycle8/validation/`.

The shared cause was claim ownership across a six-to-eight-post writer packet.
The v36 diagnostic introduced a deterministic lead post per brand and a
validator requiring visible citations to that post, while still exposing all
selected posts to the writer. Five of six targeted outputs were mechanically
valid. The Llama output still imported a result from a second visible post
and cited the lead post, demonstrating that instruction plus citation checks
alone did not isolate its claims. V36 is diagnostic only. V37 presents only
the selected lead post to the final writer, retains the full packet locally
for audit, and records the omitted-source count. This trades cross-post
synthesis and contradiction awareness for a source-bound headline; both
quality and usefulness must be reviewed before it can qualify.

The first v37 single-source probe repaired the Llama case with two claims
supported by its chosen post. Separate Qwen, MiniMax, StepFun-launch, and
Doubao probes were mechanically valid and avoided the earlier cross-post
attributions. A no-lead StepFun greeting call timed out after 300 seconds
without a provider receipt, so the five-case job stopped after two completed
calls. V38 keeps one visible greeting as hold context when there is no lead;
its two-case Llama/greeting probe returned valid decisions in 15.8 and 5.8
seconds. V38 also uses brand-focused citations from the existing editor call
as *salience hints*, with identity and early-subject checks before selecting
the single lead source. The editor's prose and judgments remain untrusted.
The v38 ten-case saved-regression replay is pending. None of these probes is
a fresh qualification or release pass.

The official v38 ten-case saved-regression replay finished 10/10 mechanically
valid. Independent Sol review found no critical failure and factual-support
scores of at least 4/5 in every case; review cost was $0.233237. One
InclusionAI marketing-ideas case scored 3/5 for why-first and 2/5 for
secondary usefulness, so the single-source strategy still needs the fresh
24-case aggregate test. The reviewer accepted the other saved source-scope
cases, including Kimi allegation ownership, Kling group ranking, the Chinese
discount case (which selected a different supported Go-match claim), the
ERNIE spam sample, Nemotron's trading result, and the Ming-Image metric.

### Cycle 9 fresh result and v39 correction

Cycle 9 sealed a new read-only production source at SHA-256
`ffe8273324a6794a3ce88559d3886435045b9f3869b984a3092f85a46a89b68c`.
The 24 disjoint reviewer assignments and eight controls were fixed before
generation. V38 completed 46/46 provider calls, 35 eligible terminal outcomes,
and no transport failures. Provider-billed generation was $0.05857470 and
total wall time was 714.855 seconds. The 1-day and 7-day windows took 270.272
and 264.312 seconds, respectively. Five raw calls were mechanically invalid;
one editor draft was recovered by the critic, while two paired editor/critic
batches remained invalid and held four brand/window outcomes. All eight
corrupted-draft controls received mechanically valid final decisions and three
independent reviewers found no unsupported control claim surviving repair.

The five review means were 4.625 factual, 4.792 proportionality, 4.583
why-first, 4.500 secondary usefulness, and 4.792 translation equivalence.
One of 24 cases was critical: the InclusionAI 7-day output held despite
selected posts explicitly discussing Ling-3.0-flash-VL's reported release and
visual-agent use. The source snapshot's alias matcher did not recognize the
curated official `@AntLingAGI` account when mentioned by a third party, so
the lead picker found no brand-owned source. The other reviewed holds were
accepted; in particular, Sakana AI had only four brief opinion/joke posts.
Its 90s joke nevertheless became a synthetic 1990s event in the writer, and
the validator correctly rejected it. Because its paired batch was rejected,
the unrelated Yi hold was collateral. This is not a reason to relax factual
validation. Cycle 9 failed SC2 and SC3; the preliminary report is
`.context/headline-finance-cycle9/validation/qualification-v38-preliminary.json`.

V39 makes two source-selection corrections. The snapshot now admits a curated
official account's `@handle` as an attribution alias only when that handle
contains a tracked brand or product term; a general parent-company account
cannot identify a subbrand. A public dossier containing only brief
`opinions_reactions` posts cannot supply a lead headline, so such a batch must
hold without promoting a reply or blocking its paired brand. Frozen Cycle 9
source is reused only for diagnostic replay with a clearly marked simulated
official-handle overlay. The next qualification requires a newly frozen,
disjoint source and a new manifest.

The v39 diagnostic replay completed 46 calls for $0.05530446. It restored the
supported InclusionAI 7-day headline, but Sakana AI still generated a headline
from the 90s joke: the provider-facing projector had moved post types into
`taxonomy.post_types.values`, while the new lead rule read `post_type_keys`
from the private snapshot. One critic batch remained invalid and withheld its
paired outcome. V40 reads the actual projected taxonomy field. A four-brand,
two-window probe confirmed Sakana has no lead and the 7-day paired Upstage
story remains available. Its 1-day writer still tried to narrate a no-lead
example, so deterministic no-lead decisions now normalize to a hold before
content validation. Revalidating that raw response produced two clean holds
without an extra provider call. The raw and normalized decisions remain
separately inspectable; this correction supplies no model-written headline.

The official v40 ten-case saved-regression replay was 10/10 mechanically
valid. Independent Sol review found zero critical errors and factual support
at least 4/5 in every case; it billed $0.2425745. The reviewer retained
minor qualifications for the unnamed InclusionAI event and the interim
Nemotron trading position, neither material. This closes the saved-regression
gate for v40 only. The full fresh and operational gates remain open.

### Cycle 10: fresh V40 qualification failed on two source facts

The source was frozen read-only from production at
`.context/headline-finance-cycle10/fresh-unseen-source.json` (SHA-256
`76631cf01fe419d73f5d1c98fb339e375557c6dc0b800e860aca1867277c63c4`).
Reviewer assignments and eight controls were sealed before generation.
Forty-six 0731 calls produced 34 eligible final brand results for $0.05786667
in provider-billed model usage; final critic batches were mechanically valid.
The 24 independent reviews averaged 4.54 factual support, 4.38
proportionality, 4.42 first-item relevance, 4.25 secondary usefulness, and
4.62 translation equivalence. R1 found two material failures (Q122 and Q127),
while R2 and R3 found none. Thus SC2 failed even though the rubric means and
SC3 passed. The full receipts and reviews are in
`.context/headline-finance-cycle10/validation/`.

Q122 held an InclusionAI post that explicitly reports Ant Group's release of
`Ming-Image-0.1-Design`. The source match used only a generic, deliberately
excluded short `Ming` keyword. The existing Product catalog links the exact
model name to InclusionAI; that exact name now enters the snapshot alias set
only when it appears in the bounded source reservoir. A Cycle 10 diagnostic
lead-selection replay selects the previously held post, without broadening
the `Ming` rule.

Q127 said `48% off` in English and Japanese for a source that says `48折`,
which means paying 48% of the applicable price (52% off). The old resolver
recognized one-digit 折 amounts only. V41 resolves one- and two-digit notation,
passes the deterministic gloss to the final writer, and repairs only the
literal pay-percent-as-discount inversion in source-linked output. Replaying
the actual Cycle 10 critic response now yields `52% off` and `52%オフ` with
matching source-check text. This is diagnostic, not a fresh qualification.
Ten saved regressions and an independent source review are next, followed by
a new disjoint source freeze and sealed 24-case V41 review.

V41's ten saved regression cases completed with 10/10 mechanically valid
final outputs. The independent Sol reviewer found zero critical failures,
scored every case at least 4/5 for factual support, and billed $0.2364545;
the complete source, output, and score receipts are under
`.context/headline-finance-cycle11/regressions-v41-all*`. A separate
two-call diagnostic on the old Q122 packet, with the exact catalog product
alias present, produced a valid source-linked InclusionAI headline rather
than a hold. Neither diagnostic counts as fresh qualification.

Cycle 11 then froze a new disjoint, read-only production source at
`.context/headline-finance-cycle11/fresh-unseen-source.json` (SHA-256
`01c4d2ebc43a19553212249d750605f2b14ec64116a6a467bc68c2b48c9276b3`).
It contains 13 eligible 1-day and 16 eligible 7-day brand dossiers. A new
24-case, three-reviewer assignment and the eight controls were sealed before
generation at `.context/headline-finance-cycle11/validation/manifest.json`.
The preflight plans 40 calls, 561,124 input tokens, and $0.136360 reserved
cost; these were ceilings, not actual usage or a quality result. Fresh
generation began after the assignment seal.

### Cycle 11: V41 source identity and old-event date failures

The sealed V41 generation completed all 40 planned calls and all 29 eligible
brand outcomes in 756.977 seconds, with zero mechanically invalid final
responses and zero missing locale fields. Provider-billed calls totaled
$0.05293098, including the eight critic controls; generation alone cost
$0.02496600 for 1-day and $0.02485008 for 7-day. The one-day and seven-day
generation windows took 294.311 and 265.507 seconds respectively. A read-only
production count found 571 one-day and 85 seven-day run rows in the preceding
30 days; these are observed creations across statuses, not a future demand
guarantee. The preliminary qualifier passed SC1, SC3, SC4, and SC5 but not
SC2 or the unmeasured staging operational criteria. Artifact and qualifier:
`.context/headline-finance-cycle11/validation/generation-v41/` and
`.context/headline-finance-cycle11/validation/qualification-v41-preliminary.json`.

Three blind reviewers assessed 24 disjoint cases. Their combined means were
4.50 factual support, 4.75 proportionality, 4.33 first-item relevance, 4.42
secondary usefulness, and 4.79 translation equivalence. R1 found Q151
critical: a Reliance post about battery and solar wafers had only the lowercase
ordinary word `solar`; `Solar` was an Upstage secondary product keyword and
also the unguarded final word of `Upstage Solar`, so the final headline moved
Reliance's LLM/database/investment claims to Upstage. R3 found Q166 critical:
a recent Llama post explicitly said `Date: Nov 10, 2024` for its hackathon
win, but the headline omitted the old event date and read as current news.
R2 found no critical issue. The frozen source, raw output, and each separate
review are retained under `.context/headline-finance-cycle11/validation/`.

V42 removes bare nonprimary ASCII product words as standalone source identity,
uses only complete display names in lead selection, and retains labeled old
event dates across all three visible locales. The actual Q166 raw critic
response revalidated under this guard now includes `Nov 10, 2024` in English
and `2024年11月10日` in Chinese and Japanese, with the claim text aligned. A
local production-chain regression also shows the Q151 `solar wafers` source
has no Upstage lead while an explicit `Solar Pro 3` release remains eligible.
These are diagnostic replays; V42 still requires a new disjoint freeze and
sealed review assignment. During V42 preparation, the saved Moonshot Kimi
regression failed because `Kimi` is both the display-name suffix and a token
of canonical key `moonshot_kimi`. The V42 replay and freeze were stopped;
their partial files are not a qualification. V43 admits such a suffix only
when present in the canonical brand key, while continuing to reject generic
`Solar` for `upstage`. The affected focused suite passed 113 tests. V43 gets
new artifacts and an independent fresh review.

V43's source freeze had 14 eligible one-day and 17 eligible seven-day brands,
with zero selected evidence ID or exact-text overlap against Cycle 11. The
review assignments were sealed before generation. Its ten saved regressions
were 10/10 mechanically valid, but separate Sol review found Q32 critical:
the Chinese headline described a +5.55% return as a one-day gain, whereas the
source's one-day qualifier described an 11-place ranking climb. The full V43
run was stopped after partial rank/editor calls. It is not a qualification.
V44 adds a metric/time-period ownership check to the source-ledger prompt and
first probes Q32 directly, then replays and reviews all ten saved cases before
another fresh, disjoint trial.

The one-case V44 Q32 probe was semantically correct, but the full ten-case
V44 replay again put `单日`/`1日に` on the +5.55% return, despite its own
number ledger assigning one day to the 11-place ranking change. Prompt-only
guidance did not reliably solve this failure class. A source- and
ledger-conditioned V45 normalizer removes the misplaced daily modifier from
Chinese/Japanese visible claims without changing the figures. Revalidating
the V44 raw response under this code produces period-unspecified +5.55%
return text and a ranking rise, consistent with the source. The regression
test also proves a truly daily return is not changed. V44's prepared fresh
source has not been generated or reviewed and is excluded from release
qualification; V45 needs its own saved-case pass and blind fresh review.
Its source and sealed manifest can be reused byte-for-byte because no V44
generation or review consumed them, and the V45 change occurs after source
selection. Source SHA-256:
`2285a16e82661d4bbcce532b2b55e9e38b95a0ace85253d68867b39eec44e4ea`.
V45's ten saved cases passed all mechanical checks and independent Sol review:
zero critical failures, no holds, and a minimum factual-support score of 4/5.
An independent Q32 diagnostic using the V44 raw response after V45
normalization scored factual support 5/5, translation equivalence 4/5, and no
critical error. These are prerequisite checks; the sealed 24-case fresh run
must still pass before staging.

V45 completed 36/36 calls and 26/26 eligible outcomes on sealed source
`2285a16e82661d4bbcce532b2b55e9e38b95a0ace85253d68867b39eec44e4ea`.
All finals were mechanically valid, all visible locales were present, and
provider-billed generation cost was $0.04903794. Snapshot plus generation
was 283.834 seconds for one day and 320.54 seconds for seven days. Three
independent reviewers found four critical instances across three failure
classes: R1 Q218/Q223 false-held the same supported Nemotron 3 Diarization
post; R3 Q239 lost the force of a Chinese insult in Japanese; R3 Q240 used
Chinese `代币` for app/model usage Tokens. R2 found no critical error. The
preliminary readiness report at
`.context/headline-finance-cycle15/validation/qualification-v45-preliminary.json`
passes SC1/3/4/5 but fails SC2; staging operations remain unmeasured.
V46 limits corrections to versioned secondary product identity, faithful
abusive-language paraphrase, and AI-service Token terminology before another
saved-case and fresh-source trial.

V46 expanded the saved source regressions to 13. All 13 were mechanically
valid and independently reviewed without a critical error (minimum factual
score 4/5). Its sealed fresh sample completed 36/36 calls and 24/24 eligible
outcomes for $0.04754, but four supported subjects were held. The common
cause was source loss: the critic received a bounded lead excerpt even when
another selected source contained the needed evidence. The 1,000-character
front clip also omitted decisive product names near the ends of long X posts.

V50 retains the complete bounded source ledger for the critic, keeps both
ends of long original posts within the same 1,000-character limit, and admits
long secondary product names only in nearby model/use context. It does not
infer a shared author, platform, or test from distinct posts. One response
had a harmless extra ledger clause about a third post, which the existing
source-preserving normalizer now aligns. Revalidating the raw V50 provider
responses under that correction gave 17/17 mechanically valid saved cases.
An independent reviewer then caught a remaining Q26 attribution error:
two posts with different opaque platform links were described as reporting
about “the same platform.” V52 removes that unsupported link in all three
locales while retaining both reported offers. The 17 raw provider responses
revalidated again under V52 with 17/17 mechanical success, no holds, and
byte-identical finals except for the Q26 attribution correction. Independent
GPT-5.6 Sol source review found zero critical errors and a minimum factual
score of 4/5 across the 17 finals. The first five unchanged cases reuse
their earlier review; Q26 was reviewed anew through OpenRouter, and Q27–Q261
were reviewed through OpenAI directly after OpenRouter's remaining credit
dropped to about $0.12. Case-level receipts and exact artifacts are under
`.context/headline-finance-cycle18/`. This is saved-case evidence, not fresh
qualification or deployment approval.

Cycle 18 froze a new read-only production source of 14 eligible one-day and
16 eligible seven-day brands, with zero stable-prefix overlaps against all
previous selected evidence. Its 24 case assignments (eight each for Sol,
Gemini 3.8 Flash, and Grok 4.7) and 17 required regressions were sealed before
generation. Source SHA-256:
`0edf091a9458d580474f741fbd2759f6fbbff3f47a49879206342e589c77ab7f`.
The V52 fresh generation and independent review are the remaining SC1–SC5
gate; none of the prior fresh runs count as a pass.

V52 completed the sealed fresh run with 40/40 provider calls, 30/30 eligible
terminal outcomes, all locale fields present, $0.06361713 billed generation
cost, and 248/272 seconds for one-day/seven-day generation windows. Two critic
responses failed the mechanical validator: one said “the same post” while
citing different posts, withholding Mistral and Doubao; another supplied
English source-ledger lines that differed from its final MiniMax narrative,
withholding MiniMax and GLM. All eight adversarial critic controls survived
without an unsupported false acceptance, but seven repaired controls still
needed independent source review at generation time.

The three sealed blind reviewers found four critical cases among 24. Q290
withheld a supported Mistral narrative after the cross-post wording failure.
Q294 attributed a Seedance 2.5 story to Doubao despite the cited source having
no Doubao alias. Q309 combined separate NVIDIA replies into a single claim
that engineering teams achieved a win *using* Nemotron 3 Ultra, though the
win reply never named the model. Q310's Japanese headline changed a joint
provider spending comparison into a Moonshot-only comparison. Dimension means
remained above 4/5, but four critical findings fail SC2; the two unrecovered
critic outputs fail SC3. All eight reviewed controls had no surviving
unsupported claim or new material error. This run is a diagnostic no-go,
not a staging candidate. The next correction is scoped to cross-source
identity/claim ownership, target-product attribution, group-measure scope in
translation, and the critic's exact source-ledger copy contract. The frozen
Cycle 18 source is now consumed; a later qualification needs another disjoint
source and sealed review assignments.

V53 ranked headline sources by a strong tracked-product identity link and
constrained headline citations to that list. Its five targeted probes were
4/5 mechanically valid; the Doubao output still borrowed Seedance's claim,
and the Nemotron output still borrowed an official account's action from a
different post. V54 therefore sent the final writer only the strong-identity
source subset while retaining the full packet for validation and audit. Five
targeted probes became 5/5 mechanically valid. Independent Sol review found
one critical Japanese inversion of who allegedly distilled whom (Q294).
V55 required explicit actors and targets in comparisons. A targeted Q294
rerun scored factual support 4/5 with no critical finding. The complete 22
saved regressions were 22/22 mechanically valid, but independent source
review found two critical secondary claims: Q247 inverted a conditional
about legal pre-approval, and Q302 assigned Video2X's frame interpolation to
CapCut and inferred unproven LoRA provenance. Thus V55 is a no-go despite
passing the mechanical and 154 focused PostgreSQL checks. Full case-level
source, final response, provider receipts, and review are under
`.context/headline-finance-cycle19/regression-reviews-v55/`.

Cycle 19 separately froze a new read-only production source at
`2026-09-24T22:02:24+00:00`: 15 eligible one-day and 17 eligible seven-day
brands, SHA-256
`d24b532ef5cb2daab2e11d304b6519c9e9306038d2df9cab2df87acffcedad19`.
Twenty-four reviewer assignments and the 22 required regressions were sealed
before generation. The V55 fresh process was interrupted after 38 logged
provider events and produced no complete candidate artifact. It is excluded
from qualification, and no V55 fresh responses were used for tuning.

V56 focuses on source-owned secondary claims: prefer a separate detail from
the headline source, do not turn an incidental brand list into news, preserve
conditional direction, assign each tool its exact role, and omit unverified
asset provenance. The Q247 and Q302 targeted reruns were 2/2 mechanically
valid; independent Sol review scored both factual support 5/5 with no
critical error.

The V56 22 saved-case replay completed 22/22 mechanically valid finals, all
`repair`. The Cycle 19 fresh bakeoff hung after provider logs at
`2026-09-24T22:22:48Z` with no `candidate-summary.json`; that incomplete
output is unused. On 2026-09-25 the owner stopped the zero-critical SC2
prompt loop. A twelve-case lead-sentence review of the saved V56 regressions
passed: each lead named the right company and the right main fact, including
the prior Q247 legal-conditional and Q302 CapCut/Video2X moles. V56 is the
frozen candidate (`headline-critic-finance-source-audit-source-ledger-only-v56-ja`).
Do not add another critic prompt version. No staging or production
activation has occurred.
