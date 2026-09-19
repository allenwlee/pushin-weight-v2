# Model-specific task trials — execution report

Status: current staging recommendations are settled for classification and commentary, with translation retaining the incumbent as the safest choice. DeepSeek V4 Flash 0731 **through OpenRouter, pinned to DeepInfra**, remains selected for classification. A true direct-DeepInfra replay did not qualify: its classifier lost 20 brand-role rows to an incompatible response shape, translation tied the V4.1 control at 10 confirmed errors plus one uncertain, and commentary had 14 confirmed affected sources versus V4.1's interval of [9,10]. Direct DeepInfra Gemma 4 31B tagged v2 remains the qualified commentary choice. The old fixed 1% threshold no longer controls selection; historical scores remain unchanged. No runtime route has been activated; production remains unchanged.

The owner extended Qwen optimization after the original three configurations. Delivery Exception 29 authorizes three additional Qwen configurations per task and wider diagnostics despite remaining hard-case failures. This supersedes older review wording that a failed eight-post smoke screen cannot advance to a wider diagnostic. It does not waive the qualification threshold.

The eight-post cohort deliberately contains difficult, previously consumed posts. The wider 24-post translation cohort adds 16 other posts, but is still purposive. Neither error fraction is a production-prevalence estimate. Native-language copies are included in locale completeness checks but require no inference.

## Current results so far

This table supersedes stale “in progress” interpretations elsewhere in this
execution log. It separates delivery, source-first semantic review, and cost.
No row authorizes activation.

| Model / route | Classifier | Translation | Commentary | Status and latest relevant receipt |
| --- | --- | --- | --- | --- |
| Cloud 0731 / OpenRouter → DeepInfra FP8 | **Selected** for classification on prior comparative evidence; alternative classifier work is closed. | Not the current translation choice; retained random100 reassessment fails parity. | Separate U20 evidence; not the current commentary choice. | Staging-only. [Bounded reassessment](2026-09-17-215000-0731-translation-random100-parity-reassessment.md). |
| 0731 / direct DeepInfra standard | Does not qualify: 6/6 HTTP responses, but only 45/45 content rows and 25/45 brand rows passed the exact R122 parser. | 215/215 responses; 10 confirmed + 1 uncertain, **[10,11]**, tied with V4.1 and unresolved. | 96/96 called responses; 94 application-complete sources; 8 semantic + 6 coverage = **[14,14]**, worse than V4.1's **[9,10]** and Gemma's **[4,5]**. | No activation. Main suites cost $0.02915772; one failed JSON-mode probe adds $0.00019284. |
| Direct DeepSeek V4.1 | Fresh expanded-taxonomy classifier: 24/24 strict delivery, no aggregate semantic score. | **Safest current choice / incumbent**: no cheaper candidate clearly qualified. Direct Gemma 4 31B ties at 10 confirmed + 1 uncertain, so strict parity remains unresolved. | Corrected T3: smoke8 4 confirmed, 0 unknown; full24 5 semantic + 2 pre-call coverage failures = 7 confirmed, 0 unknown. | Direct classifier price unavailable; $3 is allocation, not a receipt. |
| Qwen3.7 Flash | v6: 16/24 strict; 22/24 bounded mechanical replay; material semantic findings. | v4 diagnostic24: 11 confirmed + 1 unknown versus V4.1 7 + 1. | Best smoke8: 5/8 versus corrected V4.1 4/8. | Not selected. Classifier $0.002654116; v4 translation $0.00223058; best commentary (v2) $0.00030791. |
| Gemini 2.5 Flash-Lite Flex | v1: 7/8 strict; v2 prepared then cancelled unspent. | diagnostic24, parent-reconciled: 9 confirmed + 1 unknown (versus V4.1 7 + 1). Random100: 10 semantic + 3 coverage + 2 unknown, versus retained V4.1 review 9 + 0 + 1. Neither cohort qualifies Gemini. | diagnostic24 remains a separate historical count: candidate 5 semantic versus V4.1 5 semantic + 2 pre-call coverage. Parent-adjudicated old45 is 5 confirmed candidate sources versus 3 incumbent coverage failures, so it regresses. Versioned random100 v3 review is 10 confirmed + 3 unknown, [10,13], superseding its prior 8+2 review; old45+random100 is [15,18]. The identical-prompt v4 no-reasoning control is worse at 21 confirmed + 4 unknown, [21,25]; the paired control is closed with no quality pass. | Actual Gemini random100 commentary receipts: v3 $0.0299522; v4 $0.0069008 (76.96% lower). Direct V4.1 actual billing is unavailable. The $0.03019485/$0.06038970 off-/peak figures are OpenRouter reference estimates, not bills. [Parent checkpoint](2026-09-17-192500-model-task-parent-checkpoint.md). |
| Hy-MT2 1.8B / 7B | Not tested. | 1.8B: 3 paid configurations; 7B: 2; neither parity. | Not tested. | Latest receipts: $0.000659234 (1.8B v3), $0.001381363 (7B v3). |
| GPT-5.6 Luna / OpenAI Flex | Not tested. | v3 diagnostic24: 3 confirmed failing sources + 1 unknown, an observed diagnostic result only. Old45 has one confirmed ordinary-heading error; `白目` remains reviewer disagreement, so no full qualification. | v3 diagnostic24 review complete: 23/24 delivered; 3 minor semantic/locale sources plus one retained upstream 429 = 4/24 versus T3's 7/24, no unknown. This observed diagnostic result does not qualify Luna. | The cumulative reservation cap holds further work. v2 commentary receipt $0.006015325; v3 commentary $0.008572125. |
| Qwen3 235B Instruct 2507 / GMICloud FP8 | Not assigned; 0731 remains selected. | Latest recovery rerun diagnostic24: 10 confirmed + 1 uncertain versus V4.1 7 + 1; 52/55 targets delivered, four recovered. Original three variants [7,8], [18,24], [17,17] retained. | Not assigned. | Complete; no parity. 21m 44s, $0.0044253475 response-reported cost. Shared-provider overload confirmed. |
| HY-MT2 30B-A3B / Tencent FP8 | Not assigned. | Three diagnostic24 variants: [13,13], [7,7], [6,6]. Final structured-lines v3 random100: 14 affected sources versus incumbent 9 confirmed + 1 uncertain. | Not assigned. | Complete; no parity. 161.158 s, $0.022907190 retained charge. No activation. |
| Gemma 4 31B / direct DeepInfra FP4 | 19 confirmed + 2 uncertain, **[19,21]**, versus V4.1's 18 + 2, **[18,20]**; no classifier parity and no activation. [Detailed classifier diagnostic](2026-09-18-180500-gemma4-direct-classifier-diagnostic.md). | Closest cheaper candidate, but direct random100 remains tied at 10 confirmed + 1 uncertain with V4.1; strict parity unresolved, so V4.1 remains safest current choice. | **Qualifies:** 3 confirmed semantic + 1 coverage + 1 uncertain, **[4,5]**, versus V4.1's **[9,10]**. Tagged v2 returned 100/100 provider responses and 99/100 application-complete results. | Commentary qualifies for staging integration; no activation yet. Tagged v2 was 10m 11s serial and cost $0.011350240014. |

### Current recommendation

Use DeepSeek V4 Flash 0731 through OpenRouter pinned to DeepInfra for classification, retain DeepSeek V4.1 Flash for translation because no cheaper candidate clearly qualified, and use direct DeepInfra Gemma 4 31B tagged v2 for commentary. Do not replace the selected classifier route with direct DeepInfra: the direct checkpoint returned every HTTP response but violated the frozen brand-role schema on one 20-post batch. Direct 0731 translation and direct Gemma translation each remain tied with V4.1 under the conservative rule, while direct 0731 commentary is materially worse. These are staging recommendations only; no runtime route is activated.

### Gemini commentary: reasoning-on versus reasoning-disabled control

The owner-authorized fourth Gemini commentary profile is a narrow random100
control. It uses the same saved source rows
(`61cd2421f0c5bf8c17cbd73cc6ae231bb406a6c64f3c8b293d74f70cab4a2d0a`),
source-bound v3 prompt, JSON schema, model, Google AI Studio Flex route,
three-call concurrency, 180-second timeout, and 8,192-token output budget as
the completed v3 random100 run. Captured requests are byte-equivalent outside
the `reasoning` object. The only requested change is v3's
`{"enabled":true,"max_tokens":2048,"exclude":true}` to
`{"enabled":false,"exclude":true}`. The new profile and task-scoped
four-profile exception do not change Gemini translation or any other task.

| Measure | v3 reasoning enabled | v4 reasoning disabled control |
| --- | ---: | ---: |
| Source posts delivered | 100/100 | 100/100 |
| Input tokens | 57,340 | 57,340 |
| Completion tokens, including reasoning | 135,426 | 20,169 |
| Reported reasoning tokens | 114,584 | 8 |
| Visible completion tokens | 20,842 | 20,161 |
| Provider receipt | $0.0299522 | $0.0069008 |
| Artifact-derived wall time | about 176 s | 50.731 s |
| Per-request p50 latency | 5.199 s | 1.480 s |
| Per-request p95 latency | 6.817 s | 1.874 s |

The disabled request flag did not produce literal zero reported reasoning:
four raw receipts report two reasoning tokens each (eight total). Those are
posts `2100227899886587913`, `2100283207736332475`,
`2100313775937085598`, and `2100343550563025063`; the other 96 receipts
report zero. This is retained as provider telemetry, not repaired or retried.
The control's wall time is derived from the saved start marker and report-file
timestamp; it is not the 148.357-second sum of overlapping request latencies.

All 100 JSON fields were delivered with zero transport and JSON-validation
failures, but delivery is not a quality result. Parent reconciliation of two
full source-only reviews finds **21 confirmed affected sources**—13 material
semantic, seven minor semantic, and one incomplete-content source—plus four
uncertain sources, **[21,25]**. Locale totals are 229 good, 37 material, 19
minor, three incomplete, and 12 uncertain. The incomplete source is
`2100404047882727911`: all three fields are unfinished fragments despite valid
JSON, `finish_reason: stop`, and only 83 completion tokens, so it was not a
ceiling event.

The versioned re-review of the otherwise matched v3 reasoning-enabled control
is **10 confirmed plus three uncertain sources, [10,13]**, superseding the
older 8+2 record without altering its raw output. Ten affected sources are
shared; v4 adds 11 confirmed-only sources and v3 adds none. The disabled
profile therefore saves **76.96%** of the actual Gemini receipt and reduces
median request latency (1.481 s versus 5.199 s), but it has substantially more
reviewed source defects. This paired experiment is closed: it is neither a
quality pass nor a replacement for v3, and it authorizes no runtime change.

The DeepSeek V4.1 commentary comparison still has no actual direct-provider
billing receipt. Its OpenRouter figures remain saved-route usage-price proxies,
not direct-account charges, so this control does not establish an actual
cross-provider cost saving. The controlling artifacts are
`.context/model-task-20260917/gemini-commentary-v4-no-reasoning-r113-random100-20260917-220100/parent-reconciled-review.json`
and `parent-paired-comparison.json` in that same directory.

The original detailed trial table below remains a receipt ledger. Its early
review counts must be read through the later adjudications above: notably,
Gemini translation v2's preliminary 4+1 smoke result is superseded for
current status by the parent-reconciled diagnostic24 (9+1 versus V4.1 7+1)
and the completed random100 review. Those cohorts are diagnostic evidence,
not qualification.

## Translation and commentary results

| Trial | Source errors from review | Calls | Missing/invalid sources | Reported USD | Median post seconds | Run seconds |
|---|---|---:|---:|---:|---:|---:|
| gemini-commentary-v1-smoke8 | 6/8 | 8 | 0 | 0.00055925 | 2.03 | 17.32 |
| gemini-commentary-v2-smoke8 | 5/8 | 8 | 0 | 0.00050885 | 1.68 | 13.88 |
| gemini-translation-v1-smoke8 | 6/8 (parent adjudicated) | 19 | 0 | 0.00089675 | 2.32 | 23.51 |
| gemini-translation-v2-smoke8 | 4/8 | 19 | 0 | 0.00626375 | 13.00 | 47.17 |
| gemini-translation-v3-smoke8 | 7/8 | 19 | 2 | 0.00077430 | 2.26 | 11.91 |
| hy18-translation-v1-smoke8 | 6/8 | 19 | 2 | 0.00082947 | 2.12 | 10.30 |
| hy18-translation-v2-smoke8 | 5/8 | 19 | 1 | 0.00072864 | 1.97 | 10.32 |
| qwen-commentary-v1-smoke8 | 6/8 | 8 | 0 | 0.00034513 | 5.20 | 44.93 |
| qwen-commentary-v2-smoke8 | 5/8 | 8 | 0 | 0.00030791 | 4.06 | 31.77 |
| qwen-commentary-v3-smoke8-concurrent | 6/8 + 1 unresolved source | 8 | 0 | 0.00277856 | 35.07 | 111.64 |
| qwen-translation-v1-smoke8 | at least 4/8 | 19 | 1 | 0.00056394 | 2.57 | 47.28 |
| qwen-translation-v2-smoke8 | 6/8 | 19 | 1 | 0.00561707 | 62.22 | 241.99 |
| qwen-translation-v3-smoke8 | 5/8 + unresolved | 19 | 0 | 0.00049007 | 2.79 | 27.69 |
| qwen-translation-v4-diagnostic24-r2 | 11/24 + 1 unresolved source | 55 | 0 | 0.00223058 | 3.91 | 88.88 |
| qwen-translation-v4-smoke8 | 6/8 | 19 | 0 | 0.00054444 | 3.42 | 27.92 |
| qwen-translation-v5-smoke8 | 6/8 + unresolved | 19 | 2 | 0.00075002 | 7.00 | 44.10 |
| qwen-translation-v6-smoke8 | 6/8 + unresolved | 19 | 2 | 0.00886110 | 108.64 | 392.26 |

Reported amounts are provider usage receipts. Forecasts and reservations use only the two explicitly adopted September 17 price snapshots. Raw requests pin the provider and disable fallback. There were no automatic repair/retry calls. Run time includes the actual configured concurrency: initial translation was serial, later translation used three source posts concurrently; commentary configurations 1/2 were serial and Qwen configuration 3 used at most three concurrent posts. Do not compare timing as if execution shape were identical.

## Qwen refactor findings

- Configuration 4 separated system instructions from JSON source lines and reconstructed paragraph formatting in code. All translation outputs were delivered on both the eight- and 24-post runs. Meaning errors remained.
- Configuration 5 asked for a short source interpretation before translating, within the same call. The interpretation itself sometimes misread slang, identity and grammatical roles. Two sources had missing targets despite normal provider completion.
- Configuration 6 added a 4,096-token reasoning allowance, temperature 0 and a small development-derived glossary. It still had six confirmed erroneous sources out of eight, plus unresolved syntax. The eight-post run took 392 seconds and cost $0.00886110, versus $0.00054444 for configuration 4. More reasoning was not a successful translation correction.
- On the wider 24-source fast run, all 55 generated outputs and 17 native copies were delivered. Reviews P/Q found 11 source posts with confirmed defects and one additional unresolved source. Across all 72 locale outputs: 55 good, 15 confirmed-error, two unresolved. This is diagnostic evidence, not a random-population estimate.
- Commentary configuration 3 separated source data from instructions and required the Chinese/Japanese explanations to preserve the English claims. Additional reasoning still left six confirmed defective sources and one unresolved source out of eight.

## Classifier work

The classifier uses the expanded current proposal: 14 post types, seven Audience Topics, investigate_claim, Geopolitical modes, and post-level untracked promotions with candidate identity. This is distinct from the older r123 runtime prompt. Trials retain two roles.

Six Qwen classifier configurations are complete, including two wider 24-source diagnostics. Sparse label arrays, named boolean maps and compact bit vectors were tested. The sixth configuration isolates one source per batch, with two roles and readable labels. All 48 calls completed normally; strict delivery was 16/24 sources. Offline restoration of a missing JSON wrapper yielded 20/24, and an exact singleton canonical-brand-ID-to-slot mapping yielded 22/24. These are mechanical delivery checks, not semantic accuracy. Missing semantic labels are never filled by code. Reported cost was $0.002654116 including observed cache hits.

The parent corrected automated review mistakes involving supplied quoted context and target-brand attribution in H7046, H4E3, H92, L45-17 and L45-22; the detailed reports preserve those corrections. H7046's unsupported “vibes” superiority claim does not require results_analysis. The paid v3/v4 prompts also accidentally discarded appended consistency checks; configuration 5 corrected that implementation defect. Historical raw requests and results remain unchanged.

See the timestamped classifier v1–v6 reports, especially `2026-09-17-200000-qwen-classifier-v6-singleton-diagnostic24-review.md`.

## Incumbent benchmark

The owner requires DeepSeek V4.1 Flash as the benchmark for all three tasks. The matching 24 translation/commentary sources already have incumbent outputs from the completed random100 run. Exact source/context and original caller hashes match; the reuse manifest is `.context/model-task-20260917/incumbent4.1-reuse-manifest.json`. Those outputs are being reviewed under this trial's rubric without repurchasing identical calls. The fresh expanded-taxonomy classifier control is complete: 48/48 calls, 24/24 strictly valid paired sources, identical logical prompts/source payloads to Qwen v6, 51.256 aggregate sequential seconds. Qwen v6 delivered 16/24 strictly and 22/24 after mechanical replay. At least five incumbent classifier sources have confirmed semantic failures; no full semantic accuracy score is claimed. See `2026-09-17-201000-direct-deepseek-v41-classifier-diagnostic24-report.md`. Translation/commentary source-only re-review is in progress. Initial reviewer drafts S/T were rejected for mismatched evidence and inconsistent counts; they must not be used as benchmark scores.

## Review provenance and remaining work

Automated reviewers inspect source text and supplied context, with exact cited output spans; they are not a new human gold standard. The parent adjudication exhibit records linguistic checks and corrections. Reviews A–R are retained alongside frozen requests and complete provider outputs in the private trial folder; a durable evidence export will accompany the completed results.

Complete the remaining bounded model/task trials, then run larger regression and fresh qualification only for eligible configurations. The owner-authorized wider diagnostics are allowed to characterize a failing model but do not qualify it. Other shortlisted models remain queued while Qwen receives the requested refactoring work.

Completed pre-benchmark trial evidence is preserved in `2026-09-17-170500-model-task-evidence-export-corrected/`; all 169 archived member checksums were verified. This replaces the earlier export whose manifest included an invalid self-entry. It does not include later 4.1 benchmark artifacts or rejected S/T drafts.

Incumbent raw evidence and exact-match receipt: `2026-09-17-171000-incumbent-benchmark-evidence/` (seven verified artifact checksums; reviewer drafts excluded). Temporary experiment directories are retained per the owner's stage-long no-deletion instruction.


Owner scope decision: 0731 classifier selection is settled; no further alternative classifier calls. Gemini classifier v1 is completed diagnostic evidence, while v2 was prepared before cancellation. Future experiments cover translation and commentary only. No temporary directory cleanup is permitted during the stage.


## September 17 — Expanded translation candidates (owner-authorized)

Delivery Exception 34 in the existing Stage 1 plan adds three translation trials, each owned by a separate Terra subagent. Astra integrates shared profiles and reviews evidence. Paid runs serialize under the existing portfolio lock; each uses at most three concurrent requests. The global $30 reservation ceiling and $3/model-task ceiling remain unchanged. These trials do not alter the selected 0731 classifier or any runtime default.

| Candidate | Pinned route | Saved catalog input/output $/M | Initial request shape |
| --- | --- | --- | --- |
| Qwen3 235B Instruct 2507 | GMICloud FP8, `gmicloud/fp8` | 0.0875 / 0.35 | Non-thinking; JSON line array restored in code; temperature 0; no hybrid reasoning flags |
| HY-MT2 30B-A3B | Tencent FP8, `tencent/fp8` | 0.074 / 0.295 | Native single-user translation/terminology prompt; raw marked text; temperature 0.7 |
| Gemma 4 31B | DeepInfra FP4, `deepinfra/turbo` | 0.09 / 0.34 | Raw literal translation; explicit reasoning disabled; unsupported/inherited samplers omitted |

Prices come only from `2026-09-17-143812-openrouter-pricing-snapshot`; additive endpoint snapshots establish routing and supported parameters, not replacement prices. Maximum output caps are 8192 / 4096 / 8192 respectively; the actual caller requests a lower source-sized allowance. Initial timeouts are 180 seconds. No fallback, hidden retry or production write is allowed.

All three profiles passed the integrated profile and experiment suite (33 tests). Three new real-caller capture cases first failed for absent profiles, then passed after integration. They check model/route, price caps, reasoning controls, endpoint evidence hash, locale count and output representation. Existing caller/parser/ledger tests remain green. Any profile revision is frozen separately after all in-flight runs finish; consumed contracts and outputs are never edited.

Start with smoke8 and diagnostic24, review full source-bound outputs under the incumbent-parity rubric, then revise at most twice when a concrete failure supports it. A diagnostic match permits wider evaluation; it is not production qualification. Append terminal findings below as the three model reports complete.

### Expanded translation diagnostic results — three configurations per candidate

All three model agents completed their bounded diagnostic runs. The frozen profiles differ deliberately: the goal is each model's best workable configuration, not identical prompts. These counts include any missing or invalid required output; an affected source counts once. Intervals include additional unresolved sources. The matched V4.1 baseline is **[7,8]** on these 24 consumed, difficult posts. None of these results is a population error rate or a production qualification.

| Candidate / configuration | Specific change | Source-error interval /24 | Observed provider charge, USD |
| --- | --- | ---: | ---: |
| Qwen235 v1 | Non-thinking, structured lines, concurrency 3 | [7,8] | 0.0038490025 |
| Qwen235 v2 | Same wire prompt, concurrency 1 | [18,24] | 0.0015662325 |
| Qwen235 v3 | Same prompt, concurrency 1, four-second request-start spacing | [17,17] | 0.003277715 |
| HY30 v1 | Native translation plus source-derived terminology glossary | [13,13] | 0.005347684 |
| HY30 v2 | Native delimiter instructions without glossary | [7,7] | 0.005370665 |
| HY30 v3 | Structured line array; code restores framing; temperature 0.7 retained | [6,6] | 0.005762573 |
| Gemma4 v1 | Literal raw text; reasoning explicitly disabled | [4,4] | 0.006826900 |
| Gemma4 v2 | General source-fidelity instruction revision | [10,10] | 0.006408210 |
| Gemma4 v3 | Structured line array; original baseline controls | [6,6] | 0.005194390 |

Charges are the sum of retained provider usage receipts, not reservations; failures without usage do not establish a billing amount. Comparing charges without delivery would reward missing answers. The preceding smoke8 runs are additional costs and remain separate cohorts.

Qwen v3 delivered 29 of 55 requested generated targets; 26 HTTP 429s left 15 source posts incomplete. Source review found two further failing sources: primary union 17. The final amendment accounts for all 72 locale fields (55 generated targets, including failures, plus 17 exact native copies). Slower spacing did not resolve delivery on this pinned route and price ceiling; this does not prove Qwen's underlying translation ability is inadequate across providers.

HY v3 delivered every API response but one target was rejected as an untranslated source copy. Its primary union is six sources. The parent rejected an erroneous Japanese transliteration finding and a generic-cents currency allegation; the versioned amendment uses actual meaning changes instead. Gemma v1's reconciled count is four: untranslated ordinary English, literal French slang, untranslated Hausa, and the ordinary noun `Divide` left in Chinese. `vs` alone is not an error. Gemma v2 introduced protocol markers; v3 had seven 429 responses plus one transport timeout. The v3 primary count is six source posts, not eight transport requests. No evidence establishes that JSON itself caused the rate errors.

A read-only OpenRouter account check found a paid account with no per-key credit cap. It does not identify the cause of a previous 429. [OpenRouter's official limits documentation](https://openrouter.ai/docs/api_reference/limits) distinguishes platform and upstream-provider limits using error metadata/headers; this harness retained status but not the non-200 body or headers. That observability gap remains explicit. Account evidence: `.context/model-task-20260917/openrouter-rate-limit-account-check-20260917-220506.json`.

Focused verification after the final shared changes: **58 tests passed** (37 profile/experiment tests and 21 classifier-harness regression tests). The added fake-clock test verifies actual request starts at 100, 104, 108 and 112 seconds, not just a configured pacing field. The experiment-only changes do not activate a runtime route.

The completed matched regression runs used frozen HY v3 and Gemma v1 on the same retained 100 sources as V4.1: 215 generated targets plus 85 exact native copies. Parent comparison verified every source text, language and context against the incumbent contract; the normalized candidate source hash is `61cd2421f0c5bf8c17cbd73cc6ae231bb406a6c64f3c8b293d74f70cab4a2d0a`. Proof: `.context/model-task-20260917/expanded-random100-incumbent-source-match.json`. No control inference is repurchased. Independent peer reviewers receive source-only packets without old answers; task assignments reveal model identity, so these are not claimed to be fully model-blind qualification reviews.

Detailed terminal diagnostics: [Qwen final review amendment](2026-09-17-131500-qwen235-translation-v3-review-amendment.md), [HY final diagnostic summary](2026-09-17-220130-hy30-final-translation-summary.md), [Gemma v1 review](2026-09-17-214456-gemma4-translation-v1-diagnostic24-source-review.md), [Gemma v2 review](2026-09-17-215422-gemma4-translation-v2-diagnostic24-source-review.md), [Gemma v3 review](2026-09-17-220627-gemma4-translation-v3-diagnostic24-source-review.md). Raw reviews remain immutable; amendments and corrected source-hash provenance are retained beside each run.


## September 17 — Expanded translation trials completed

**All three owner-authorized candidates completed three configurations each. None qualifies to replace V4.1 for translation.** Gemma is closest on the retained random100 regression; HY is faster but changes more source meanings. Qwen's pinned GMICloud route remains unreliable under the allowed price ceiling. Its failures do not establish how the same weights would perform on another provider.

| Model / selected configuration | Final cohort | Sources with any error | Missing-output sources | Whole-run elapsed | Retained provider charge, USD |
| --- | --- | ---: | ---: | ---: | ---: |
| DeepSeek V4.1 reference | Same random100 | 9 confirmed + 1 uncertain | 0 | Not remeasured | Direct bill unavailable |
| Gemma 4 31B v1, raw text, reasoning off | Same random100 | 11/100 | 6 | 715.0 s | 0.026888230 |
| HY-MT2 30B v3, structured lines | Same random100 | 14/100 | 8 | 161.158 s | 0.022907190 |
| Qwen235 v3, concurrency 1, four-second spacing | Diagnostic24 only | 17/24 | 15 | Not compared with random100 | 0.003277715 |

Each affected post counts once, even if multiple languages fail. Gemma has 10 coverage-error locale fields across seven sources, including one source whose Hausa paragraph was left untranslated despite non-null output. It also has seven semantic/protocol/minor-error fields across four other sources: literal French slang, leaked numeric markers, a Japanese typo and a changed company-versus-research-lab distinction. This yields 17 bad fields of 300, but the primary score is 11 affected posts. HY has ten missing locale fields across eight posts plus eleven semantic errors across seven posts, with one overlapping post: 14 affected posts and 21 bad fields of 300. Currency substitutions, a reversed discount, changed speaker attribution and a misread Korean headline are among HY's substantive errors.

Compared with the incumbent's confirmed errors, Gemma shares four affected posts, adds seven and fixes five. HY shares four, adds ten and fixes five. Neither candidate's error set includes the incumbent's one uncertain-only post. Thus resolving that incumbent uncertainty cannot establish parity for either candidate. These are reviewed observations on retained regression inputs, not estimates of production error prevalence or statistical proof of model superiority. All 300 fields per candidate were reviewed; 85 are exact native-language copies requiring no model call, while 215 require generated translations.

Initial automated reviews missed real defects. Parent source checks and additive amendments corrected them; the final canonical ledgers are `parent-reconciled-review.json` under `.context/model-task-20260917/gemma4-translation-v1-r113-random100-20260917-220700/` and `.context/model-task-20260917/hy30-translation-v3-random100-20260917-220225/`. Original reviews remain preserved. Independent reviewers received source/context and candidate output without incumbent answers, but knew the model from their assignments. These were not fully model-blind reviews or new owner adjudications.

### Configuration and cost record

All prices below come only from the saved September 17 pricing snapshot, not a new web price lookup. Official model/provider documentation informed request configuration. Provider routing and precision are part of each frozen contract; no silent fallback was allowed.

| Candidate / pinned route | USD per M input / output | Configurations tried in order | Common limits |
| --- | ---: | --- | --- |
| Qwen3-235B-A22B-Instruct-2507 / GMICloud FP8 | 0.0875 / 0.35 | Non-thinking structured JSON lines at concurrency 3; concurrency 1; concurrency 1 with four-second actual request-start spacing | Temperature 0, 8192 output tokens, 180 s timeout; no unsupported hybrid-reasoning flags |
| HY-MT2-30B-A3B / Tencent FP8 | 0.074 / 0.295 | Native single-user translation plus source-derived glossary; delimiter-only instructions without glossary; structured JSON lines with deterministic framing restoration | Temperature 0.7, 4096 output tokens, 180 s timeout, concurrency 3; no unsupported reasoning controls |
| Gemma 4 31B / direct DeepInfra FP4 | Not assigned. | Direct random100: 10 confirmed errors + the same 1 uncertain source as paired V4.1's 10 + 1. Confirmed and paired differences tie; strict R113 remains unresolved. 215/215 returned, with two fields rejected by application checks. | **Passes retained-random100 parity:** 4 confirmed + 1 uncertain versus V4.1's 9 + 1; candidate upper 5 <= incumbent lower 9. Tagged v2 returned 100/100 provider responses and 99/100 application-complete results. | Commentary qualifies for staging integration; no activation yet. Tagged v2 was 10m 11s serial and cost $0.011350240014. |

The selected HY100 run reported 105,600 input and 51,162 output tokens. Gemma100 reported 109,123 input and 52,878 output tokens, including 22,784 cached input tokens and zero reasoning tokens. Across all three candidates, initial smoke runs, all nine diagnostic configurations and both wider regressions total **14 runs, 982 frozen requests and $0.0975184795 in retained provider-reported charges**. Charges are not a verified account invoice: failed requests without usage receipts leave billing unknown. Lower bills caused by missing outputs are not a quality-adjusted saving. Portfolio reservations total $7.1749335725, below the $30 cap; each new candidate remains below its $3 reservation cap.

Experiment code passed 58 focused checks: 37 profile/transport tests and 21 classifier-harness compatibility tests. This includes testing actual request pacing with an injected clock. All paid runs are finished; no runtime route, database data or deployment was changed. Cloud 0731 remains the chosen classifier; translation/commentary selection and staging integration remain separate unfinished plan work. This closes this bounded three-model experiment, not the overall staging gate.

Evidence: [final reconciliation and paired source IDs](2026-09-17-224500-expanded-translation-final-reconciliation.json), [all run receipts and hashes](2026-09-17-223734-expanded-translation-trial-receipts.json), and [detailed diagnostic configurations](2026-09-17-160400-model-task-optimization-execution-report.md#expanded-translation-diagnostic-results--three-configurations-per-candidate).


### Gemma 429 investigation — attribution correction

The seven HTTP 429s affected **five** posts, not six, and clustered within about ten seconds of the 715-second run. The sixth missing-output post received a successful response copying Danish into the Chinese target; validation correctly rejected it. Total score remains 11/100, now described as five transport-affected posts plus six posts with output defects. No retry or fallback was enabled, and the client discarded HTTP error details, so transient capacity is the leading explanation but OpenRouter-versus-DeepInfra attribution remains unproven. [Investigation and proposed bounded recovery test](2026-09-17-230000-gemma-rate-limit-investigation.md). No new inference or runtime change.


## September 17 — Gemma and Qwen recovery reruns complete (Exception 35)

The owner requested two separate agents to rerun Gemma and Qwen after the rate-limit investigation. Each retained its original model, provider, prompts, source rows, output ceiling and saved-price cap. The only intended experimental change was bounded transport recovery: up to three attempts on HTTP 429/503, provider-wide cooldown, Retry-After when supplied, exponential backoff with jitter otherwise. Gemma used two workers and Qwen one; there were no semantic retries or fallback providers. All paid calls and reviews are complete. Neither candidate qualifies; production is unchanged.

| Translation run | Returned / requested targets | Recovered targets | Final source-post errors | Matching V4.1 control | Wall time | Response-reported cost |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| Gemma 4 31B / DeepInfra FP4, random100 | 186/215; 181 usable after validation | 12 | 25/100 confirmed | 10 confirmed + 1 uncertain after paired correction; historical review was 9 + 1 | 27m 37s | $0.02482317 |
| Qwen3 235B Instruct 2507 / GMICloud FP8, diagnostic24 | 52/55 | 4 | 10/24 confirmed + 1 uncertain | 7 confirmed + 1 uncertain | 21m 44s | $0.0044253475 |

These are different cohorts, so their percentages are not a direct model ranking or a fresh production error-rate estimate. Source-post errors count a post once if any required translation is wrong or missing. Gemma's 25 comprise 21 coverage-affected sources and four additional semantic sources. Qwen's ten comprise two coverage-affected sources and eight additional semantic sources; a separate tokenizer-attachment ambiguity remains uncertain. Reviews are agent judgments, not a new human gold set, and reviewer identities were not blinded.

**Gemma transport:** 286 attempts yielded 186 HTTP 200, 98 HTTP 429 and two 180-second read timeouts. Forty-one targets initially failed; twelve recovered, leaving 29 transport-missing. Five additional HTTP-successful outputs were rejected by the existing caller, producing 34 null fields across 20 posts. One more post retained an untranslated Hausa paragraph in Chinese/Japanese. The remaining four error posts contain an untranslated English phrase, literal French slang, a lost price relation, or leaked internal `[[PQ2B]]` markers. Final parent review is 256 passing and 44 erroneous fields across all 300 required fields, including 85 native copies. Parent reconciliation adds the two marker leaks missed in the first agent review; its preliminary 24-post count is superseded by 25.

**Qwen transport and review:** 66 attempts yielded 52 HTTP 200 and 14 HTTP 429. Four initially failing targets recovered and three remained missing across two posts. Parent reconciliation corrects the initial reviewer count: tokenizer attachment is uncertain in both candidate and incumbent, not a confirmed candidate error, while Chinese drops the named OpenCode Go subscription. Final field ledger is 38 generated passes, 17 native copies, 12 semantic errors, three missing fields and two uncertain fields. Paired source counts are four shared confirmed, six candidate-only confirmed, three incumbent-only confirmed and one shared uncertain-only.

**Provider diagnosis:** New captured error metadata identifies DeepInfra `engine_overloaded` and GMICloud `rate_limit_exceeded`, both with `limit_source=upstream_provider_shared_pool` and `is_byok=false`. GMICloud supplied Retry-After 60 seconds; observed retry waits respected it. DeepInfra generally supplied no Retry-After. This confirms shared-provider overload for these new responses, not an account credit failure. Old runs discarded error bodies, so their exact cause remains unavailable. Gemma's short fallback backoff did not overcome this sustained overload window; the rerun does not prove retrying made availability worse. Qwen delivered more targets than its original 29/55, but additional delivery still exposed translation errors. Neither is evidence of an inherent failure of every provider serving these weights.

**Consistent scoring:** Gemma translated the Japanese price question as “higher AI model” / “模型越高”; incumbent EN also says “higher AI models.” Because the full source explicitly compares prices, the same minor meaning error must count for both. The original incumbent review remains immutable. An additive paired amendment changes this comparison's incumbent interval from [9,10] to [10,11]. Gemma still fails by a wide margin. Four confirmed error posts are shared, 21 are Gemma-only and six are incumbent-only after that correction.

**Setup costs and billing limits:** Two short local-helper setup attempts were stopped and corrected before the full reruns: Qwen omitted the requested provider-metadata header (four HTTP successes, $0.0002031225); Gemma's redaction incorrectly scrubbed numeric usage fields (nine HTTP successes, $0.00055008). These are experiment-harness faults, not model quality failures; receipts and full reservations are retained separately. Corrected retry helpers passed fake-response tests before paid execution. Full Gemma receipts report 99,331 input and 49,266 completion tokens, with zero reasoning tokens. Reported costs are sums of returned usage receipts; timeouts or errors without usage have unknown charges, not proven zero. Portfolio reservations remain $8.6843634275; Qwen's task total is $0.4815640375 and Gemma's $1.56279353, below the existing limits. No live pricing was used.

Artifacts:

- [Machine-readable comparison](2026-09-17-235000-gemma-qwen-recovery-rerun-comparison.json).
- [Gemma rerun report](2026-09-17-234128-gemma4-random100-recovery-aware-rerun.md), with parent reconciliation.
- [Qwen rerun report](2026-09-17-233200-qwen235-translation-v3-recovery-diagnostic24-report.md), with parent reconciliation.
- [Captured provider error reproduction](2026-09-17-232236-model-provider-throttling-reproduction.json).

The decisive field ledgers are `parent-reconciled-review.json` inside `.context/model-task-20260917/gemma4-translation-v1-r113-random100-recovery-aware-revised-2026-09-17-231128/` and `.context/model-task-20260917/qwen235-translation-v3-recovery-rerun-diagnostic24-20260917-230735/`. The Gemma directory also contains `incumbent-paired-review-amendment.json`. No further paid runs, route activation, staging deployment or production change follows from these results.


## September 18 — Provider access diagnosis

[Routing and direct-access research](2026-09-18-001500-gemma-qwen-routing-research.md) confirms the experiment pinned a single provider and disabled same-model failover; exact price caps also exclude alternate routes. Gemma's one-/two-second retries did not adapt to sustained overload, while Qwen honored Retry-After. Current availability was captured without prices; all cost comparisons retain September 17 snapshots. Alternate routes and direct Google/Alibaba/DeepInfra/Together access are documented. Recommendations are research only: no further paid run or route change has been made.

## September 18 — Gemma 4 direct DeepInfra test

The owner supplied a direct DeepInfra credential and authorized one exact retained-random100 rerun after the OpenRouter diagnosis. Official DeepInfra documentation identified the OpenAI-compatible endpoint, exact model ID `google/gemma-4-31B-it-turbo`, FP4 route, 262,144-token context, zero-retention public endpoint and standard $0.09/M input plus $0.34/M output prices. The request retained Gemma v1's source rows, raw-text prompts and per-source output ceilings. It removed only OpenRouter's provider, reasoning, price-routing and metadata envelope and omitted JSON mode, temperature, top-p and explicit service tier. DeepInfra returned `service_tier: default`. References: [model endpoint](https://deepinfra.com/google/gemma-4-31B-it-turbo/api) and [rate limits](https://docs.deepinfra.com/account/rate-limits).

The direct route delivered **215/215 requests on the first attempt**, with zero HTTP errors, timeouts, fallbacks or retries. The same Gemma route through OpenRouter originally delivered 208/215 before application validation; the later recovery-aware OpenRouter run delivered 186/215 after 98 HTTP 429 responses and two transport errors. Direct account routing therefore fixed the observed shared-pool delivery failure on this bounded run. It does not prove permanent provider availability.

| Route / run | Concurrency | Provider responses | Retries | Application-failed sources | Wall time | Reported cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma v1 via OpenRouter, original | 3 | 208/215 | 0 | 6 | 715.0 s | $0.026888230 |
| Gemma v1 via OpenRouter, recovery-aware | 2 | 186/215 | 71 | 20 | 1,657 s | $0.024823170 |
| Gemma v1 direct DeepInfra | 1 | **215/215** | **0** | **2** | 1,781.804 s | **$0.029156410003** |

Timing reflects deliberately different concurrency and cannot rank provider throughput directly. On the serial direct run, median request latency was 3.457 seconds, p95 was 23.857 seconds and maximum was 131.437 seconds. Six unusually long targets dominated the early wall time. DeepInfra reported 111,835 input tokens, 57,171 output tokens and 8,672 cached input tokens. Direct total cost was $0.00226818 (8.44%) above the incomplete original run, or 4.91% higher per received response; stochastic output length and seven additional deliveries explain why equal published token rates do not yield equal totals.

The application parser rejected two otherwise complete `stop` responses because Gemma repeated `our` until the target was unusable. Full source review found ten confirmed-error posts and one additional ambiguous post. Seven sources contain semantic defects and three contain coverage defects. Examples include reversed `same or worse` sentiment, literal French slang, untranslated Hausa, changing the MiniMax proper name into a mathematical phrase, leaked internal quantity markers, and the two repetition loops. Parent reconciliation also reapplied the prior price-relation rule: Chinese `越高级` loses the source's more-expensive meaning. The sole uncertainty is shared with V4.1: `based on tokenizer` can attach to the model or the author's guess.

After symmetric correction, direct Gemma and incumbent V4.1 each have **10 confirmed-error sources plus the same one uncertain source**. Five confirmed failures are shared, five are Gemma-only and five are incumbent-only. This is confirmed-error and paired-difference parity on the retained random100. The literal conservative interval rule remains unresolved because both intervals are [10,11]; no runtime activation follows from the test. The direct route establishes that provider access, rather than Gemma weights alone, caused the earlier missing-output spike, while also showing that direct access does not remove Gemma's semantic failure modes.

Primary evidence: `.context/model-task-20260918/gemma4-translation-v1-random100-direct-deepinfra-2026-09-18-110000/`. `run-report.json` SHA-256 is `e9b12b9841f8d4ff03aeb43477769d1b0fbdba0ca83967e4e0ef70516ed52100`; `parent-reconciliation.json` holds the paired ledger. The isolated adapter's fake tests covered 429/503 recovery, 401 stop, response identity/usage/cost validation, truncated-output rejection and secret redaction. Shared runtime, databases and deployment configuration were unchanged.

## September 18 — Gemma 4 direct DeepInfra commentary test

The owner next authorized Gemma 4 31B on the retained random100 commentary cohort. The test reused the exact 100 source rows, stored context and source-bound semantic instructions used by the existing commentary comparisons. DeepInfra's current documentation advertises the exact `google/gemma-4-31B-it-turbo` OpenAI-compatible endpoint, strict structured output, reasoning controls and standard prices of $0.09/M input plus $0.34/M output. It recommends disabled reasoning for summarization and temperature below 0.7 for stable structured output. References: [model endpoint](https://deepinfra.com/google/gemma-4-31B-it-turbo/api), [structured outputs](https://deepinfra.mintlify.app/chat/structured-outputs), [reasoning controls](https://deepinfra.mintlify.app/chat/reasoning), and [rate limits](https://deepinfra.mintlify.app/account/rate-limits).

The first paid configuration used strict `json_schema`, reasoning disabled, temperature 0.2 and a 1,024-token ceiling. Its one-request probe returned HTTP 200, the exact model and `finish_reason: stop`, but Gemma omitted the closing quote on the final locale value. Application parsing rejected the malformed JSON. That $0.00008855 receipt remains preserved and was not retried.

Configuration v2 kept the same semantic prompt, route, temperature and disabled reasoning. It replaced provider JSON mode with four explicit tagged fields, raised the ceiling to 4,096 tokens because the incumbent had produced as many as 1,840, and ran serially. Application code parsed and validated the tags, post identity and three distinct nonempty locales before constructing the ordinary commentary object. Fake-transport tests covered tag success, wrong identity, locale duplication/incompleteness, non-stop completion, 429/503 recovery and credential redaction.

| Measure | Gemma direct commentary v2 |
| --- | ---: |
| Source posts / provider responses | 100 / 100 |
| Application-complete sources | 99 |
| Retries / transport failures | 0 / 0 |
| Input / output tokens | 63,540 / 20,622 |
| Cached input tokens | 34,496 |
| Response-reported cost | **$0.011350240014** |
| Full experiment cost including failed v1 probe | $0.011438790014 |
| Serial wall time | 611.232 s (10m 11s) |
| Request latency median / p95 / maximum | 5.696 s / 10.089 s / 23.742 s |

Two blind half-corpus reviews explicitly checked all 300 locale outputs against the source and stored context. A paired critic and parent reconciliation then applied the incumbent rules symmetrically. Parent review added one shared minor error where both models claimed an opaque link contained a video, counted the malformed tagged response as a whole-source coverage failure, and retained one ambiguous Italian referent as uncertain for both arms.

| Retained random100 commentary | Confirmed semantic sources | Coverage-failure sources | Additional uncertain sources | Conservative interval |
| --- | ---: | ---: | ---: | ---: |
| Gemma 4 31B direct DeepInfra | 3 | 1 | 1 | **[4,5]** |
| DeepSeek V4.1 Flash incumbent | 5 | 4 | 1 | **[9,10]** |

One confirmed error is shared. Gemma has three candidate-only confirmed errors; V4.1 has eight incumbent-only confirmed errors. Both share the same uncertain Italian-referent source. Gemma therefore passes the conservative R113 rule because its upper bound of five is below the incumbent's lower bound of nine. The observed errors remain useful: Gemma narrowed “more than 30%” to “30%” in English, changed optional switching into required switching in all locales, inferred video media from an opaque link, and malformed one tagged response.

This qualifies the direct Gemma tagged profile for commentary staging integration. It does not activate the model or change production, staging, database or shared runtime configuration. Primary evidence is `.context/model-task-20260918/gemma4-commentary-random100-direct-deepinfra-tagged-v2-2026-09-18-154000/`; `parent-reconciliation.json` is the controlling paired ledger.

## September 18 — Gemma 4 direct DeepInfra classifier diagnostic

The owner reopened a bounded Gemma classifier comparison after the earlier 0731
selection. Three configurations ran on the exact retained 24-post, two-role,
singleton control corpus. All three delivered 48/48 valid calls and 24/24
complete source pairs with no retry, transport failure, or parser failure.
Tagged v1 cost $0.010620480041 and took 166.846 seconds; checklist v2 cost
$0.011007940047 and took 231.965 seconds; model-card sampling/thinking-token v3
cost $0.012397540033 and took 259.468 seconds. The matching direct V4.1 control
took 51.256 seconds; its direct billed cost remains unavailable.

Mechanical delivery did not translate into semantic qualification. The
historical nonblank-owner comparison favored Gemma at field level, but all
three Gemma runs still disagreed on at least one reviewed field for 21/24
sources, and those controls are consumed and partly legacy. Parent
reconciliation of the full source set finds 19 confirmed Gemma error sources
and two additional uncertain sources, versus 18 plus the same two for V4.1;
their conservative intervals are [19,21] and [18,20]. V3 restored one clear
MiniMax testimonial but regressed results/topic labels elsewhere and exposed no
provider-attested reasoning content. The candidate does not establish
classifier parity and is not activated. Cloud 0731 remains selected. Full
evidence and limitations:
[direct Gemma classifier report](2026-09-18-180500-gemma4-direct-classifier-diagnostic.md).

## September 18 — DeepSeek V4 Flash 0731 direct DeepInfra provider isolation

The owner requested all three selected 0731 task shapes through DeepInfra's
direct OpenAI-compatible endpoint, removing OpenRouter from the path. Requests
pinned `deepseek-ai/DeepSeek-V4-Flash-0731`, used the existing
`DEEPINFRA_API_KEY`, disabled reasoning, retained temperature 1, top-p 1 and
seed 42, and ran serially. DeepInfra returned the requested checkpoint name on
every response. No main-suite call encountered HTTP 429/503, used a retry, or
fell back to another provider.

An initial classifier probe tested DeepInfra's native `json_object` response
mode. It returned HTTP 200 and the exact model but only `{}`, so the probe was
stopped and retained at a response-reported cost of $0.00019284. The successful
main suites omitted native JSON mode and used the established prompt plus local
parsing. This is a model-specific result: structured-output capability on an
endpoint does not establish that this checkpoint follows this complex schema
under native JSON mode.

| Direct 0731 task | Frozen workload | Provider delivery | Application result | Input / output tokens | Serial wall time | Response-reported cost |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Classifier, exact selected R122 shape | 45 posts, 20/20/5, two roles, 6 calls | 6/6 | 45 content rows; 25 brand rows; one 20-row brand response incompatible | 50,739 / 5,589 | 56.425 s | $0.00399276 |
| Translation | random100, 215 generated locale calls | 215/215 | 99/100 source rows complete; two generated fields on one source rejected | 106,799 / 51,652 | 1,133.675 s | $0.01517538 |
| Commentary | random100; 96 calls after four existing pre-call input caps | 96/96 | 94/100 source rows complete; two malformed responses plus four capped sources | 26,747 / 46,582 | 1,146.114 s | $0.00998958 |

The three main suites total $0.02915772. Including the failed JSON-mode probe,
the experiment total is $0.02935056. These are response `estimated_cost`
receipts, not an account invoice. Timing is descriptive: the direct suites were
serialized, while some historical controls used concurrency.

### Classifier

The exact provider-isolation replay used the previously selected R122
OpenRouter contract: the same 45 ordered posts, 20/20/5 batches, content and
brand roles, prompts, output ceilings and representation-only normalization.
All six direct requests returned, but the first 20-post brand response used
`product`, `geopolitical_stance` and a single `national_stance` field instead
of the required product-label, geopolitical-mode and separate China/U.S.
stance fields. This was not a lossless representation difference; the two
country dimensions had been collapsed. The frozen exception forbade parser or
semantic retries, so the raw response remains a failed call rather than being
repaired or repurchased.

The completed artifact therefore contains all 45 content rows and only 25
brand rows. On the consumed, incomplete owner controls, direct access matches
148 of 358 reviewed fields versus 249 of 358 for the historical OpenRouter
R122 run; 111 reviewed candidate values are absent because of the failed
20-post brand call. Those figures diagnose this replay only and are not a
production accuracy estimate. The direct run cost $0.00399276 versus the
historical OpenRouter upstream receipt of $0.00406692, but a slightly lower
receipt cannot compensate for an incomplete classification result.

A separate newer-taxonomy diagnostic24 run is retained as supplemental rather
than controlling evidence because it does not reproduce R122. Excluding one
operator-interrupted role, 47/47 provider responses returned; five needed only
lossless empty/sentinel normalization. Its source review found 100/193 exact
reviewed fields for direct 0731 versus 117/193 for V4.1. Both classifier
experiments point in the same operational direction: keep the selected
OpenRouter-pinned route until a fresh direct configuration passes the exact
contract.

### Translation

Direct DeepInfra delivered all 215 generated translations on the first
attempt. This removes the 12 failed source rows and 21 combined provider errors
seen in the earlier OpenRouter random100 execution, but it does not remove
semantic errors. One direct source row failed application validation because
the model copied English unchanged into both Chinese and Japanese.

Two half-corpus reviews checked all 300 locale fields. Parent reconciliation
retains the established matched V4.1 control rather than silently replacing it
with a fresh reviewer count. Direct 0731 and V4.1 each have ten confirmed-error
sources plus the same one uncertain source, intervals [10,11]. Six confirmed
errors are shared, four are direct-only and four are incumbent-only. Confirmed
counts and paired differences tie, but the conservative qualification remains
unresolved because candidate upper bound 11 is not at or below incumbent lower
bound 10. Direct 0731 therefore does not replace V4.1 for translation.

### Commentary

Direct DeepInfra returned every one of the 96 commentary calls made. Four long
posts were excluded before transport by the existing caller's input cap, and
two otherwise successful responses contained malformed JSON, leaving 94 of
100 source rows application-complete. The prior OpenRouter 0731 run had 13
failed rows, including the same four pre-call caps; direct access therefore
improved delivery but did not meet the quality gate.

Independent half-corpus reviews covered all 300 expected locale fields. Parent
reconciliation applies the accepted commentary rules symmetrically, including
the French `poulet` price reaction and tokenizer-as-evidence cases. Direct 0731
has 14 confirmed affected sources: eight semantic and six coverage failures,
with no remaining uncertainty. V4.1's fixed control is nine confirmed plus one
uncertain, interval [9,10]. Six confirmed sources are shared, eight are
direct-only and three are incumbent-only; one direct confirmed error is the
incumbent's uncertain Italian-referent case. Direct 0731 fails the V4.1 parity
gate and is also worse than direct Gemma tagged v2's [4,5]. Gemma remains the
commentary staging recommendation.

Controlling evidence:

- Classifier: `.context/model-task-20260918/0731-classifier-r122-fresh45-direct-deepinfra-2026-09-18-210000/`, especially `run-report.json` and `owner-control-score.json`.
- Translation: `.context/model-task-20260918/0731-translation-random100-direct-deepinfra-2026-09-18-193000/parent-reconciliation-v2.json`; the earlier `parent-reconciliation.json` is superseded.
- Commentary: `.context/model-task-20260918/0731-commentary-random100-direct-deepinfra-2026-09-18-203000/parent-reconciliation.json`.
- Failed native-JSON probe: `.context/model-task-20260918/0731-classifier-diagnostic24-direct-deepinfra-2026-09-18-190000/`.

The direct route is not activated for any task. No runtime configuration,
database, staging deployment or production setting changed.
