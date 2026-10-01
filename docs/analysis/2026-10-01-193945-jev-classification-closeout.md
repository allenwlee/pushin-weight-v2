---
title: Jev classification evaluation closeout — keep 0731; reconsider newer Jev versions
recorded_at: 2026-10-01T19:39:45+09:00
publication_requested_at: 2026-10-01T19:51:39+09:00
publication_scope: documentation-and-evidence-only
status: closed-no-classifier-switch
decision: keep-0731-for-classification
candidate: jev-1.13.0
incumbent: deepseek-ai/DeepSeek-V4-Flash-0731
root_revision: 33f20b971b01dbb8d90939f975e5dbbd987a3d86
experiment_revision: 1edbc3adaa19b370498ef0fbb026319fc676d397
tags: [jev, typesafe, 0731, classification, promotion, geopolitics, evaluation]
---

# Jev classification evaluation closeout

## Decision and scope

**Keep 0731 for classification. Close this evaluation, not the option of using
Jev later.** The owner explicitly leaves a switch open if subsequent Jev
versions improve enough to justify it. No further test is running or authorized
by this record; old unused budgets are not continuing permission.

This is the agent entry point for the September 29–October 1 research. It
records the final decision, latest comparison, limitations, and how to reopen
the question without repeating the entire investigation. The
[comprehensive findings](2026-09-30-160557-jev-classification-findings.md)
retain the detailed journey and links to every earlier study.

Keeping 0731 is not a finding that it won every test. Jev had more valid outputs,
better positive-label detection overall, and substantially lower observed
request latency. The evidence did not establish a sufficient end-to-end reason
to replace the incumbent: quality varied by category, two important problem
areas remained weak, and extraction/integration costs were not measured.

The original promotion-ownership and country-tagging bugs remain unresolved in
the [ongoing issue record](../issues/2026-09-30-095324-promotion-attribution-and-untracked-company-ongoing-issues.md).
Closing the model comparison does not mark those issues fixed. No application
model, production prompt, database record, scheduler, or deployment was changed
by this closeout.

## Latest comparison: the baseline to find first

Use the [October 1 political-wording retest](2026-10-01-053425-political-framing-retest/report.md),
not the earlier eight-post score or the first multilingual score, when quoting
the final comparison.

- 117 posts: Japanese 20, Simplified Chinese 19, Korean 20, English 20,
  Spanish 19, Turkish 19. One selected target brand per post.
- 38 questions per post: 34 binary labels and four categorical choices.
- Jev `jev-1.13.0` used native typed decisions. 0731 used a compact
  probability-output wrapper, **not the unchanged production classifier**.
- These are agreements with frozen agent-written references, not independent
  human ground truth or representative production accuracy. The known cohort
  was reused after feedback; no simultaneous old-prompt control was run.
- No extractor was run, scored, or timed. This was classification with supplied
  source/context/catalog information, not an extraction-plus-classification
  system test.

| Final metric | Jev | 0731 |
| --- | ---: | ---: |
| All fields, invalid counted unsuccessful | 4,021/4,446 (90.4%) | 3,707/4,446 (83.4%) |
| Invalid/missing fields | 0 | 307 |
| Same fields where both outputs were valid | 3,742/4,139 (90.4%) | 3,707/4,139 (89.6%) |
| Entire 38-field post matches reference | 3/117 | 2/117 |
| Median observed request latency | 0.316 seconds | 10.765 seconds |
| Estimated model cost, 117 calls each | US$0.07685 | US$0.07165 |

Matched-valid comparison removes exactly the same fields on both sides. It
does **not** predict what repaired 0731 responses would say. Its net Jev
advantage is 35 fields, about 0.85 percentage points. Easy absent labels count
toward these totals; they do not establish reliable detection of rare positives.

| Family, matched-valid fields only | Jev | 0731 |
| --- | ---: | ---: |
| Outcome | 98/110 (89.1%) | 98/110 (89.1%) |
| Post type | 1,398/1,526 (91.6%) | 1,362/1,526 (89.3%) |
| Audience topic | 692/761 (90.9%) | 667/761 (87.6%) |
| Product categories | 515/545 (94.5%) | 503/545 (92.3%) |
| Sentiment | 75/110 (68.2%) | 62/110 (56.4%) |
| Political modes | 276/326 (84.7%) | 307/326 (94.2%) |
| China stance | 93/108 (86.1%) | 92/108 (85.2%) |
| US stance | 95/108 (88.0%) | 94/108 (87.0%) |
| Untracked-promotion categories | 500/545 (91.7%) | 522/545 (95.8%) |

Jev leads six families, 0731 two, and one ties. The two stance differences are
one answer each. **Tracked-brand advertising is a post-type question**, not
one of the five untracked-promotion fields in the last row. Do not use that
row as a direct tracked-advertising score.

The political wording change reduced Jev's false positive mode labels from
136 to 49, while true positives fell from 24 to 20. Reporting still supplied
38 of the remaining false positives. 0731's final political totals were ten
true positives, eight false positives, and 17 missed positives including
invalid answers. It was more conservative, not uniformly more capable.

All matched-valid counts above were recomputed offline from the saved score
rows. The [closeout manifest](2026-10-01-193945-jev-classification-closeout-manifest.json)
contains the counts, source-file hashes, and evidence inventory.

## What future agents should retain

1. **Jev decides; it does not write arbitrary prose.** Its typed answers can
   select supplied options or score propositions. Arbitrary company names,
   source quotations, translations, commentary, and headlines need another
   mechanism. Native structured output does not guarantee correct meaning or
   consistency across answers.
2. **The observed speed advantage is real for these requests, not a pipeline
   promise.** The final median ratio was about 34×. Jev ran locally and 0731
   on Render; hosts, output contracts, cache state and service conditions were
   not controlled. Translation, extraction, queueing and publication were not
   timed. Waiting for a mandatory 0731 supplement can dominate completion
   time even if Jev runs concurrently.
3. **Cheaper was not established.** Output was unbilled under Jev's checked
   pricing, but its final estimated model cost was slightly higher here.
   0731 can answer many questions in one call and emit tiny answers. Cached
   input is not reuse of a previous semantic judgment. Estimates exclude
   Render compute and are not invoices.
4. **Probabilities are not verified correctness.** Jev's calibration for these
   categories/languages was not measured. 0731's self-reported percentages are
   not calibrated probabilities either. Noul P(yes), a Choice winning-option
   probability, and Choice distribution confidence are different quantities.
   Raising a cutoff can remove real positives as well as false positives.
5. **The failures have separable causes.** Promotion recognition, promoted
   offering/provider, publisher affiliation, and campaign exclusion are not
   the same decision. Multiple direct promotion targets are legitimate.
   Company criticism does not establish a national stance. Longer prompts,
   upstream interpretation, and explanation-visible review did not reliably
   settle those boundaries in these experiments.
6. **Do not overinterpret a small success.** Jev's earlier 21/22 result came
   from eight repeatedly inspected cases. It did not predict full-taxonomy
   quality. Neither political errors nor wording sensitivity established
   censorship, guardrails, or missing training data as their cause.

The configured classification route remains 0731 in [config.yaml](../../config.yaml).
Translation, commentary and headline generation are separate routes. This is
source/config inspection, not a fresh audit of deployed environment overrides.
The separately scoped rare-type Jev integration must not be confused with a
general classifier or second reviewer; its live activation requires its own
current check.

## Reopening the decision after a Jev update

These are proposed evaluation conditions, not a scheduled task or permission
to spend. A new model version is a reason to reconsider, not automatic proof
that it is smarter or that a migration is warranted.

1. Obtain a bounded new evaluation request and spending/call limit. Check
   current official model IDs, capabilities and prices; pin the exact version
   rather than a moving `latest` alias.
2. Replay this frozen corpus and its known promotion/political controls as a
   regression check. Preserve old labels, outputs, hashes and definitions.
   Do not overwrite this baseline or tune thresholds on its reported results.
3. Add a fresh, independently reviewed holdout covering the six languages,
   true political positives and company-only negatives, direct and indirect
   promotions, real co-promotion, and known/unknown author affiliations.
   Decide ambiguous boundaries before inference. An old development set alone
   cannot demonstrate general improvement.
4. Compare the new Jev against the then-current 0731 route. Keep an identical
   question diagnostic separate from a production-shaped comparison. If
   testing labels-only, probabilities or constrained output for 0731, declare
   them as different arms; do not silently repair historical failures.
5. Predeclare per-family acceptance, positive precision/recall, output and
   cross-field validity, and cost/latency criteria. Report corrections and
   newly broken answers, not just an aggregate winner. Numeric adoption
   thresholds were **not** settled by this conversation.
6. Before recommending replacement, measure the real extraction-plus-label
   workflow, including source fidelity, candidate coverage, timeouts, any
   fallback, and time until the reader sees a complete result. A switch still
   needs explicit implementation and deployment authority.

The original runners can make paid calls. Inspect their contracts first; do
not execute a saved runner merely to inspect or reproduce score arithmetic.

## Parked ideas: Jev for reader-requested headline interactions

These are possibilities, not approved G2/G5 requirements or tested features:
choose among prepared angles; identify what changed since prior coverage;
rank supplied evidence for a less promotional view; flag unsupported wording;
check a reader's proposed headline edit; and select relevant comparisons from
retrieved candidates. Any newly written prose still requires a generator.
Reader-specific changes should not silently replace the shared headline.

### Pro / General reading-level toggle

The owner additionally asked whether Jev could quickly make neutral commentary
more or less technical. The inspected G5 prototype
(`docs/ideation/mockups/2026-10-01-190859-g5-general-homepage/01-above-the-fold/screens/index.html`,
maintained by a separate session and not included in this research archive)
uses prewritten `pro` and `description` strings in `storySets`; `showStory`
selects one for `#story-description`. It does not rewrite the separate Chatter
commentary. The prototype is concurrently evolving; this observation is not
an implementation contract.

Recommendation: for two fixed reading levels, generate and store both versions
from the same source evidence, then switch them without an inference call.
Pro retains supported technical detail; General explains terms without changing
claims, caveats or attribution. Neutrality and technical depth are separate.
A technical rewrite cannot recover facts absent from a neutral summary; provide
the original evidence, and do not invent extra detail to make prose sound expert.

Jev cannot perform that rewrite. Its possible role is an optional suitability or
source-fidelity check, or selecting among supplied candidates. That merits a
trial only if an actual quality need is demonstrated; no reading-level quality
or latency test has been run. A fixed two-way preference needs no Jev decision
at click time. Current capability checked against the official
[System One](https://docs.typesafe.ai/concepts/system-one) and
[Choice](https://docs.typesafe.ai/primitives/choice) documentation on October 1.

## Evidence locations and preservation boundary

The published evidence lives in the eleven dated study directories under
`docs/analysis/`. The manifest covers 2,075 original files (87,815,275 bytes),
with their original SHA-256 hashes. They were imported byte-for-byte from
`.worktrees/experiment/post-interpretation` on fuchitalee. The local originals
remain untouched. This is now a portable repository archive; entry-point links
no longer require that hidden worktree. A manifest is an integrity inventory,
not an independent backup.

Start with these existing records:

- [Comprehensive findings and historical source map](2026-09-30-160557-jev-classification-findings.md)
- [Open promotion/company/geo issues](../issues/2026-09-30-095324-promotion-attribution-and-untracked-company-ongoing-issues.md)
- [Final frozen protocol](2026-10-01-053425-political-framing-retest/contract.md)
- [Exact final inputs](2026-10-01-053425-political-framing-retest/requests.json), [questions](2026-10-01-053425-political-framing-retest/questions.json), [references](2026-10-01-053425-political-framing-retest/references.json), [prompt diff](2026-10-01-053425-political-framing-retest/prompt-diff.json)
- [Jev score rows](2026-10-01-053425-political-framing-retest/jev/scores.json), [0731 score rows](2026-10-01-053425-political-framing-retest/0731/scores.json), [comparison](2026-10-01-053425-political-framing-retest/comparison.json)
- [Political-error reading copy](2026-10-01-053425-political-framing-retest/exports/2026-10-01-072030-jev-political-errors-verbatim.md), [sentiment comparison reading copy](2026-10-01-053425-political-framing-retest/exports/2026-10-01-171523-sentiment-jev-0731-comparison.md)
- [Dated vendor documentation](../external_vendors/typesafe_ai/README.md)

The owner subsequently requested **"commit/push to main"**. This publication
includes the closeout, findings, issue record, historical experiment plan,
manifest-listed evidence and inert source snapshots. It does not publish the
experimental application changes as active code.

The four pre-existing modified files remain in the original experiment
worktree: `tests/test_u18_runtime_0731.py`,
`tests/test_u18a_v4_classification_persistence.py`, `x_monitor/attribution.py`,
and `x_monitor/classifier_0731_prompts.py`. Their hashes are preserved in the
manifest, and their diff is saved as
[historical application/test changes](2026-09-29-014716-post-interpretation-experiment/historical-application-and-test-changes.patch).
The [experiment script](2026-09-29-014716-post-interpretation-experiment/historical-post-interpretation-experiment.py.txt),
[job wrapper](2026-09-29-014716-post-interpretation-experiment/historical-post-interpretation-job.py.txt),
and [software tests](2026-09-29-014716-post-interpretation-experiment/historical-test-post-interpretation-experiment.py.txt)
are inert snapshots, not new runtime modules or an instruction to run tests.
Historical runners can depend on the recorded old revision, absolute local
paths and old credentials/service availability; preserving them is not a
claim that executing them on current `main` is safe or reproducible unchanged.

`CONCEPTS.md` and the vendor README link here. The
[bounded publication record](../plans/2026-10-01-104958-docs-jev-classification-closeout-plan.md)
records the authorized Git endpoint and verification scope. The commit carries
`[skip render]` to skip automatic deployment, following
[Render's documented commit-message control](https://render.com/docs/deploys#skipping-an-auto-deploy).
There is no staging/production release, live reclassification, new inference,
or worktree removal in this documentation task.
