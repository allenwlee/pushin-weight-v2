# Parent reconciliation of the wider model trials

This is an interim evidence checkpoint for the September 17 translation and commentary trials. Model runs and agent reviews are separate stages. Successful delivery is not a quality pass, and automated review findings remain open to source-grounded correction. No runtime model route has changed.

## Corrections to the comparison

- Gemini translation's 24-post review initially missed three source errors. The reconciled result is nine confirmed erroneous sources plus one uncertain source, versus the incumbent's seven plus one. The earlier diagnostic-parity statement is superseded. The wider tests remain authorized diagnostic work.
- Gemini commentary's incumbent review initially omitted five previously confirmed semantic failures from the same saved outputs. Those findings were restored. The first corrected review appeared to meet the whole-post comparison, but independent review and parent reconciliation subsequently confirmed **five** candidate erroneous sources on old45 versus **three** incumbent coverage failures. The matched incumbent outputs for the newly identified candidate failures were rechecked. The earlier old45 `2 <= 3` and aggregate-pass interpretation is superseded: this configuration fails that regression cohort. Context may legitimately explain a post; two overstrict quote-context findings were rejected, while actual speaker attribution, a reversed comparison, and unsupported acquisition claims remain errors.
- A source with one missing translation is one failed source, but its other delivered locale fields still require review. Gemini old45 has six missing target fields, not eighteen missing locale fields.
- Luna old45 has two independent reviews. Untranslated ordinary English headings are a confirmed minor defect. The rendering of the Japanese reaction `白目` remains a reviewer disagreement about pragmatic equivalence; do not silently equate either review's one-error total with parent agreement on the same case.
- Luna commentary v3 diagnostic24 is now reviewed: 23/24 source posts were delivered, three source posts have minor semantic/locale findings, and the one consumed upstream 429 is retained as coverage-unavailable. That is 4/24 affected sources versus T3's 7/24, with no unknowns. It is an observed same-cohort diagnostic comparison, not a qualification decision.
- Gemini commentary random100 parent amendment is complete. Four packet output dictionaries match the saved live report exactly. It upgrades the spam account/software-promotion output `2100239765429801078` and Qwen tokenizer-identity output `2100346971144036571` to material errors: both invent unsupported claims (a denial of paid promotion and a release, respectively). `pi` and the Italian pronoun remain uncertain. The prior 6 confirmed + 4 uncertain record is retained as superseded; the amended result is 8 confirmed (6 material, 2 minor), 2 uncertain, `[8,10]`, with zero coverage failures.
- Gemini commentary v4 no-reasoning random100 is reconciled and closed. It has 21 confirmed affected sources plus four uncertain, `[21,25]`, compared with the versioned v3 paired-control review's 10 confirmed plus three uncertain, `[10,13]` (superseding v3's older 8+2 review). The disabled profile has the ten shared affected sources and 11 additional confirmed-only sources. Its $0.0069008 receipt is 76.96% below v3's $0.0299522 and its median latency is 1.481s versus 5.199s, but the cost/latency improvement is not a quality pass or an activation decision. The source `2100281384351015367` remains uncertain because the evidence can support either comparative evidence or a workload-causation reading.
- The ten Japanese strings found in the incumbent old45 Chinese fields are present in the saved raw model response, before report construction. They are actual saved-output failures, not evidence that Luna failed those translations. This older control also uses a different execution shape; do not call the comparison a pure model-capability experiment.

## Reasoning and actual workload cost

The Gemini OpenRouter receipts use `output_tokens` for the entire completion, including `reasoning_tokens`. Visible output can be derived by subtracting reasoning where both values are present. Do not add reasoning tokens to output tokens a second time.

For the completed random100 commentary run:

| Measure | Gemini commentary v3 | Retained direct DeepSeek 4.1 control |
|---|---:|---:|
| Input tokens recorded | 57,340 | 26,747 |
| Completion tokens, including reasoning | 135,426 | 43,638 |
| Reasoning tokens recorded | 114,584 | 0 |
| Visible completion tokens | 20,842 | 43,638 |
| Delivered source posts | 100 | 96 |
| Actual provider cost receipt | $0.0299522 | **Unavailable**: saved result has `billed_cost_usd: "0"` and `billed_cost_complete: false` |

The saved Gemini raw-response receipts reconcile exactly: 100 received requests report 57,340 input tokens, 135,426 completion tokens, and 114,584 reasoning tokens already included in those completion tokens. Visible completion is therefore 20,842; cache-read tokens are zero. Summing the 100 provider `usage.cost` values gives the actual billed total **$0.0299522** ($0.0028670 prompt plus $0.0270852 completion). Reasoning tokens must not be added to completion tokens or billed a second time.

The direct V4.1 control records 26,747 input and 43,638 output tokens with zero reasoning tokens, but no completed direct billing receipt. Its `billed_cost_usd: "0"` is explicitly marked incomplete, so it is not a zero-dollar bill. No credential-backed direct billing export is retained in this workspace, and no billing/network retrieval was performed. Applying the adopted September 17 OpenRouter reference prices to its usage gives $0.03019485 off-peak or $0.06038970 peak, but those are hypothetical OpenRouter repricings, **not direct-account bills**. Gemini's measured charge is approximately 0.8% below the off-peak proxy or 50.4% below the peak proxy only; no actual cross-provider saving can be confirmed. Differences in delivered coverage, execution shape, and provider route remain explicit.

### Gemini no-reasoning evidence

The saved commentary v1 and v2 smoke8 contracts explicitly disable reasoning and their receipts report zero reasoning tokens: v1 cost $0.00055925 with 6/8 historical reviewed affected sources; v2 cost $0.00050885 with 5/8. Translation v1 and v3 likewise report zero reasoning tokens, at $0.00089675 and $0.0007743. Commentary v3 smoke8 instead used 9,609 reasoning tokens and cost $0.00239105. The later commentary v3 prompt with reasoning disabled was not tested, so these observations do not isolate a causal reasoning-effect comparison.

Pricing sources are the September 17 immutable snapshots already adopted by the plan. No fresh web price, subscription price, or assumed direct-account price enters this calculation.

### Gemini commentary v4 no-reasoning random100 control

The owner-authorized fourth Gemini commentary profile uses the same random100
source rows, v3 source-bound prompt, JSON schema, model, Google AI Studio Flex
route, concurrency (three), timeout (180 seconds), and 8,192-token output
budget as v3. Captured requests are byte-equivalent except for the reasoning
object: v3 has `{"enabled":true,"max_tokens":2048,"exclude":true}` and
the control has `{"enabled":false,"exclude":true}`.

| Measure | v3 reasoning enabled | v4 reasoning disabled |
| --- | ---: | ---: |
| Delivery | 100/100 | 100/100 |
| Input / completion tokens | 57,340 / 135,426 | 57,340 / 20,169 |
| Reported reasoning tokens | 114,584 | 8 |
| Provider receipt | $0.0299522 | $0.0069008 |
| Artifact-derived wall time | about 176 s | 50.731 s |
| Per-request p50 / p95 latency | 5.199 s / 6.817 s | 1.480 s / 1.874 s |

The four control receipts with two reported reasoning tokens are
`2100227899886587913`, `2100283207736332475`, `2100313775937085598`, and
`2100343550563025063`; the other 96 report zero. This is a provider telemetry
discrepancy under a disabled request flag, retained without retry. The 50.731
seconds is start-marker-to-report-artifact time, not the 148.357 seconds of
summed overlapping request latency.

Schema-valid 100/100 delivery is not a quality result. Parent reconciliation
of two full source-only reviews finds 21 confirmed affected sources—13
material, seven minor, and one incomplete-content source—plus four uncertain
sources, **[21,25]**. Locale totals are 229 good, 37 material, 19 minor,
three incomplete, and 12 uncertain. `2100404047882727911` supplies the three
incomplete fields despite valid JSON, `finish_reason: stop`, and 83 completion
tokens, so this is not an output-ceiling event.

The versioned paired review of reasoning-enabled v3 is **10 confirmed +3
uncertain, [10,13]**, superseding its older 8+2 result while retaining that
original review. Ten errors are shared; v4 adds 11 confirmed-only sources and
v3 adds none. Reasoning disabled saves 76.96% ($0.0069008 versus $0.0299522),
reduces median request latency (1.481s versus 5.199s), and reduces artifact
wall time (50.731s versus about 176s), but it is substantially worse in this
review. The paired experiment is closed without a quality pass, selection, or
runtime activation. Direct DeepSeek V4.1 billing remains unavailable:
OpenRouter calculations are only saved-route proxies, not actual
direct-provider bills. Evidence: `parent-reconciled-review.json` and
`parent-paired-comparison.json` in the v4 experiment directory.

The wider Gemini translation random100 run subsequently completed with 109,255 input tokens, 351,005 completion tokens including 298,556 reasoning tokens, and a $0.07566375 receipt. There were three source-level validation failures. The retained 4.1 translation control records 95,535 non-cache input tokens, 11,264 cache-read tokens, and 51,298 output tokens. Its OpenRouter reference repricing is $0.045142842 off-peak or $0.090285684 peak, not a direct-provider bill. Gemini therefore costs about 67.6% more than the off-peak proxy, or 16.2% less than the peak proxy. Its lower advertised token rates do not establish lower task cost.

| Gemini random100 task | Input charge | Visible-output charge | Reasoning charge | Reasoning share of receipt |
|---|---:|---:|---:|---:|
| Translation | $0.00546275 | $0.01048980 | $0.05971120 | 78.9% |
| Commentary | $0.00286700 | $0.00416840 | $0.02291680 | 76.5% |

These components reconcile to the provider receipts using the saved Flex rates. Commentary output is not negligible even without reported reasoning: the retained 4.1 control generated 43,638 output tokens across 96 completed three-language explanations, against 26,747 input tokens. Output accounts for about 86.7% of its off-peak reference repricing. Model selection should use these measured task totals rather than assume commentary is input-dominated.

Artifact completion time minus the retained start marker is approximately 191 seconds for Gemini translation old45, 418 seconds for translation random100, 176 seconds for commentary random100, and 238 seconds for Luna translation old45. These are artifact-derived wall-time observations; summed request latency is a different quantity when three calls overlap.

## Verification and remaining execution

The focused profile, experiment, and classifier harness suites completed with 49 tests passed, zero skipped, and no failures. They verify transport/configuration behavior, not model semantics.

Gemini translation old45 and random100 have completed with six and three source-level protected-span failures, respectively. Gemini commentary fresh100 completed all 100 posts without delivery failures for $0.03094585. The frozen stability20 repeat remains unspent because the reconciled old45 regression failed. In particular, the first translation random100 review missed plainly untranslated paragraphs and previously identified comparison-direction failures; its one-semantic-error conclusion was rejected and replaced by a full new review. First-pass reviews are not qualification evidence without reconciliation.

The replacement Gemini translation random100 audit records ten semantic-error sources, three additional coverage-error sources, and two additional uncertain sources: `[13,15]`. The retained incumbent source review records `[9,10]`, with no missing translation targets. The English word “slow” was conservatively left unresolved where it could mean slow-witted rather than response latency. This does not establish Gemini parity. The completed fresh commentary diagnostic has four source-error findings; the parent checked their supplied source/output spans, including a reply inheriting its parent's test, a quoted model release assigned to the quoting author, and a coding regression described as a success. It has no matched fresh incumbent run and is not a qualification result.

Luna's remaining runs are held by the explicit cumulative reservation ceiling in KTD59; actual spending must not be substituted for reserved spending to bypass that rule. Its current reservation is $1.45990660. Prepared remaining contracts reserve $1.66515660 for random100, $1.66986340 for fresh100, and $0.33762640 for stability20, for a cumulative requirement of $5.13255300. The parent asked the owner whether to raise only Luna translation's limit to $6 within the unchanged $30 portfolio ceiling; no dependent call or cap change precedes that answer. Prepared-but-unspent contracts are not completed tests.

Evidence remains in `.context/model-task-20260917/`, with the paired commentary report and translation reconciliation report under `docs/research/`. Original provider outputs and superseded review records are retained.

The final read-only check also reconsidered retained 0731 translation under the revised parity criterion. Its 100 source IDs match the incumbent cohort, but 12 sources have missing translations (15 null targets), already exceeding the incumbent's [9,10] interval. This proves the saved run fails the current end-to-end comparison without spending on another call or repeating a full semantic audit. It does not overturn the separate classifier selection. See [bounded reassessment](2026-09-17-215000-0731-translation-random100-parity-reassessment.md).

All queued calls and the available review work for this wave are complete. No model experiment is currently running. Gemini's stability repeat remains unspent after its regression failure; Luna's larger translation runs await the explicit reservation-limit decision described above.
