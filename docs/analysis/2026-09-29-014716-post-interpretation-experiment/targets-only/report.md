# Promotion targets first — result

Date: 2026-09-29. Branch: `experiment/post-interpretation`.
Scope: identify promoted targets only; publisher relationship and UP/AM/OR
assignment are deliberately not evaluated. No automated software tests run.

## Owner decision after review — 2026-09-29

The owner rejected further pursuit of the compartmentalized/target-only
approach and asked to return to the original prompt baseline. The local
classifier prompt was already restored to the pre-expansion v5 text; this
experiment was never deployed. Preserve the results below as historical
evidence, not an approved direction. No further tests or model calls.

The next task is a read-only review of actual database post language from
recorded official/staff/community authors. The owner clarified that existing
class labels should not guide that review: inspect the text ourselves,
especially the language used for promotion. Do not substitute stored-label
counts for a text-based judgment. No prompt change or deployment is authorized
by this analysis request.

## Outcome

The separate target-only call found Token Machine in all six Token Machine
posts without treating prize-model names as promotion targets. Both direct
API pitches and both offerings in the co-promotion example were identified.
It did not invent a promotion target for the unresolved reply or disputed
allegation. The remaining clear-case error was treating factual release and
hosting news as promotion of Zhipu and Acme Cloud.

Manual semantic review matched 11 of the 12 expectations frozen before the
calls. The three predeclared boundary cases are displayed separately, not
counted as wins against the old advertising-label answers. These expectations
were assistant-authored, not an independently labelled acceptance set. This
small development run is promising evidence for separating the decisions,
not proof of general accuracy or production readiness.

This score is not comparable to the earlier 4/10 versus 3/10 tracked-advertising
score: the question, output, evaluation unit and reference criteria changed.

## All target decisions

| Case | Returned promotion targets | Semantic review |
|---|---|---|
| `token_machine_qwen_win` | Token Machine | Match; Qwen is a prize/spin reference. |
| `token_machine_long_crypto_boundary` | Token Machine, including its $MACHINE offering | Match; model names describe possible prizes. Supporting quote is not verbatim. |
| `token_machine_hunyuan_no_luck_boundary` | Token Machine | Match; Hunyuan is a spin reference. |
| `token_machine_hunyuan_win_day1` | Token Machine | Match; Hunyuan is a prize reference. |
| `token_machine_hunyuan_win_day2` | Token Machine | Match; Hunyuan is a prize reference. |
| `token_machine_deepseek_win` | Token Machine | Match; DeepSeek is a prize reference. |
| `direct_deepseek_api_pitch` | DeepSeek V4 Flash API offering | Match; no inference that the poster is official. |
| `direct_zhipu_api_pitch` | Zhipu GLM-5.3-Flash via its official API on Z.ai | Match for the offering; no independent catalog identity resolution was performed. |
| `tracked_and_untracked_co_promotion` | DeepSeek API and Token Machine | Match; both offerings retained. |
| `quoted_criticism_disputed` | None | Match; rebuttal not treated as promotion. An other-mention quote is not verbatim. |
| `unresolved_subject_reply` | None | Match; identity explicitly unresolved rather than invented as Qwen. |
| `release_actor_owner` | Zhipu and Acme Cloud | Miss against the frozen expectation of factual news without advocacy. It correctly names the actors but overcalls promotional intent. |
| `bai_glm_campaign` | Short-URL platform/guide and GLM-5.3-Flash | Boundary: treats GLM's positive feature description as promotion alongside the platform. It does not know the platform's canonical identity from the short URL. |
| `comparison_two_models` | Qwen | Boundary: treats “Qwen is my pick for this job” as a recommendation; DeepSeek remains a comparison mention. |
| `praise_model_complaint_platform` | None | Boundary: recognizes GLM praise and B.AI criticism, but treats the post as complaint-focused rather than GLM advocacy. |

The last case's rationale uses the post's dominant purpose to exclude GLM
promotion even though multiple targets are allowed. That may undercount a
secondary endorsement depending on the intended meaning. The B.AI/GLM case
uses a broader reading of positive mention. These outputs expose a remaining
promotion-versus-praise boundary; they do not settle it by themselves.

## Format and evidence are separate results

- All fifteen posts returned identifiable target arrays and no UP/AM/OR
  classification. Each batch receipt separately records promoter
  classification as `not_evaluated`.
- Only 4/15 rows satisfied the requested exact output shape. Eleven rows
  added an unrequested `reason` field inside `other_mentions`. The raw output
  is preserved; those rows were not silently repaired or declared valid.
- Two posts contain non-verbatim supporting evidence. The long crypto quote
  joins separated source passages; the disputed-allegation quote removes
  quotation punctuation. Exact-quote defects do not erase the target decision,
  but these strings must not be published as exact quotations.
- The runtime validator reports the extra-key defect before inspecting that
  item's quote. Manual review therefore identified the allegation quote
  defect in addition to the recorded long-crypto quote error.
- Applying both strict shape and clear-case semantic acceptance gives 3/12,
  not 11/12. The 11/12 figure is specifically manual target-selection review.
- One other-mention rationale speculates about possible sponsor handles;
  that is unnecessary for this stage and was not used to assign a category.

No repair iteration or additional model call was made. The strict defects
remain defects; this experiment is not a drop-in production output contract.

## Experiment and receipts

The model received only the same fifteen source/context packets in the same
three batches of five. It received no previous interpretation, old labels,
reference targets, tracked-brand list or author affiliation data. Unlike the
first experiment, this prompt explicitly asks for promoted target selections
instead of general entities/claims followed by the full classifier.

The prompt and review criteria were frozen in [the local manifest](manifest.local.json)
before submission and emitted again in [the job contract](event-001-target_contract.json)
before the first model call. Full [results](result.json) and all three
`event-*-call_finished.json` raw request/response envelopes are retained.

Model: `deepseek-ai/DeepSeek-V4-Flash-0731`, direct DeepInfra `deepseek_0731`
profile; same temperature 1, top-p 1, seed 42, reasoning disabled. No full
classifier invocation. The restored v5 classifier prompt is not part of this
target-only request, and the old staged v6 prompt is not used either.

Three actual calls; 2,017 input tokens, 2,788 output tokens; provider-reported
model cost $0.00062286. Latencies: 15.533, 12.137 and 11.027 seconds per batch.
Task-wide usage is 37/40 calls, leaving three unused. No retries or unknown
usage. All post-interpretation experiments together reported $0.00510102;
the separate earlier classifier cost and unknown-translator reserve remain
as recorded in the parent report. Render compute is not included.

One-off staging job `job-datj68093c1s73aqtt7g` succeeded, starting
03:40:19 UTC and finishing 03:41:30 UTC on September 29. Only the unchanged
transport/config/fixture runtime files were hash-checked, because the target
experiment does not call the changed classifier prompt or lineage. No service
configuration, scheduler, database, live classifier or deployed revision was
changed. No new X fetch, automated software test, commit or push was run.

## Conclusion

Keep target detection and promoter classification separate. This run isolates
a tractable remaining issue—advocacy versus factual reporting or praise—rather
than hiding it behind advertising-label disagreement. Publisher identity and
affiliation remain a later task; no civilian or official status is invented.
