---
title: Shared post interpretation — paired experiment result
date: 2026-09-29
status: complete-not-for-deployment
branch: experiment/post-interpretation
base_revision: 1edbc3adaa19b370498ef0fbb026319fc676d397
---
# Shared post interpretation — paired experiment result

## Outcome

This version did not improve the original advertising-ownership problem. It
did fix one broader attribution case: praise for GLM and a billing complaint
about B.AI were correctly separated. Moving interpretation upstream remains
worth investigating, but this run does not establish a net improvement or
justify deploying this candidate.

The important finding is that two different failures exist. The interpreter
sometimes omits the relevant entity; at other times it supplies the right
promotion provider and the classifier still applies advertising to the wrong
brand. A generic interpretation appended to the current classifier is not
enough to solve both.

## What was tested

- Fifteen fixed posts: seven observed posts and three synthetic positive
  controls from the existing ownership fixture, plus five new synthetic
  controls for comparison, quotation, ambiguity, release ownership, and mixed
  praise/complaint. No new X fetch or application-data write.
- Baseline: existing v6 two-role classifier. Candidate: the same real caller,
  prompts, source text, batch order and model settings, with an extra prior
  interpretation and instruction to consult it while checking the source.
- A separate model call extracted entities/roles, attributed claims, calls to
  action/offering/provider, source quotes and uncertainties. It received no
  tracked-brand list, reference answers or expected categories.
- Model: `deepseek-ai/DeepSeek-V4-Flash-0731`, direct `deepseek_0731`
  DeepInfra profile, temperature 1, top-p 1, seed 42, reasoning disabled.
- Three batches of five; both classifier roles received the interpretation.
  This tests an additional upstream call, not merely moving a paragraph
  earlier inside the existing prompt.
- Matched auxiliary calls produced English commentary, a literal Japanese
  translation and one English headline per post. These are exploratory probes,
  not tests of the production commentary model or aggregate headline pipeline.

The frozen contract is in the [experiment plan](../../plans/2026-09-29-014716-experiment-post-interpretation-plan.md).

## Admission failures and diagnostic follow-up

The initial strict run consumed 15 calls. Two posts had evidence-quote defects:
one B.AI quote was paraphrased, and the long Token Machine post had two quotes
with normalized line breaks. Because admission operated on whole batches,
these two posts withheld ten candidate results. This is not evidence that all
ten interpretations were semantically wrong. The strict failures remain saved.

A documented six-call follow-up bypassed only quote admission for those two
batches and reused their exact unedited interpretations. No extraction was
rerun, and no human-corrected interpretation or changed prompt entered the
follow-up. The original source remained available. This gives a complete
paired diagnostic without presenting it as a pass of the strict experiment.

## Fixed classification results

Counts below are posts, not model calls. Invalid/withheld results do not pass.
The diagnostic candidate combines the original third batch with the two
follow-up batches.

| Check | Baseline | Strict candidate | Diagnostic candidate |
|---|---:|---:|---:|
| Valid classification results | 15/15 | 5/15 | 15/15 |
| Correct tracked-brand advertising decision, original cases | 4/10 | 0/10 | 3/10 |
| Complete ownership boundary, original cases | 3/10 | 0/10 | 3/10 |
| Correct untracked-promotion category, original cases | 5/10 | 3/10 | 9/10 |
| Direct-ad / co-promotion positive controls | 3/3 | 0/3 | 3/3 |
| Broader attribution controls | 4/5 | 2/5 | 5/5 |

The complete ownership boundary requires the tracked-ad decision, untracked
promotion category and promoted-subject name to match. Name matching is
case-insensitive but otherwise exact: baseline `B.AI platform` fails the
fixture's `B.AI` name check even though it is recognizably the same entity.
That limitation does not explain the failed advertising decisions.

The existing full-result equality score is 0/10 in both baseline and diagnostic
candidate. It includes additional fields, evidence wording and array ordering;
it is not the same as the narrower ownership score or a defensible measure of
overall semantic accuracy.

| Case | Baseline → diagnostic finding |
|---|---|
| Qwen Token Machine win | Tracked-ad decision regressed from correctly false to incorrectly true; untracked category improved from crypto to general. |
| B.AI / GLM campaign | GLM advertising remained incorrectly true. Promoted name changed from `B.AI platform` to an unresolved short-URL platform. |
| Long Token Machine crypto post | Correctly kept crypto promotion, but still incorrectly assigned ads to tracked model targets. |
| Hunyuan no-luck post | Ads remained incorrectly true and category remained incorrectly crypto. |
| Three Hunyuan/DeepSeek win posts | All still incorrectly assigned tracked ads; category improved from crypto to general. |
| Three positive controls | All retained the correct advertising/ownership boundary. |
| Comparison, disputed quote, unresolved reply, release | The fixed checks passed in both arms. |
| GLM praise / B.AI billing complaint | GLM changed from mixed sentiment with a complaint label to positive sentiment without the complaint label. |

The broader-control checks cover specified attribution boundaries only, not
every possible taxonomy label. The GLM mixed case, for example, also changed
other post types; passing its fixed boundary is not a claim that all labels
are ideal.

## Interpretation review

1. In the Qwen win, the extraction explicitly named Token Machine as the
   promotional platform and call-to-action provider. Nevertheless, the
   candidate classifier assigned `advertising_marketing` to Qwen. The same
   downstream problem appears in the long crypto and Hunyuan no-luck cases,
   whose maps also name Token Machine. Better extraction alone is therefore
   not a demonstrated cure.
2. In all three win posts in batch 3, the extractor omitted Token Machine
   despite its presence in the source, called Hunyuan/DeepSeek a token provider,
   and left the call-to-action provider unknown. Exact quotes passed, but the
   role interpretation was incomplete and potentially misleading. Quote
   validity is not semantic validity.
3. The B.AI extraction named the short URL as platform/guide provider and
   treated `@BAI_AGI` only as a mentioned user. The supplied evidence did not
   include an expanded URL or verified handle-to-domain relationship. Failure
   to recover the canonical name is not proof that the model ignored a
   verified identity mapping; none was supplied. It still had enough to
   distinguish the guide platform from the featured GLM model.
4. Comparison claims retained the 19/20 versus 12/20 results and task-specific
   preference. The disputed allegation kept Mira separate from the author.
   The unresolved reply remained unresolved instead of inventing Qwen.
5. The release map retained Zhipu, GLM and Acme Cloud, but flattened Acme's
   nested attribution to a claim whose speaker was `author`. The quote still
   contained `Acme Cloud says`. A reusable record should retain that
   distinction structurally, not depend on downstream rereading the quote.
6. The mixed case correctly mapped GLM praise separately from B.AI billing.
   This is the clearest observed benefit in classification.

## Commentary, translation and headline probes

All 15 paired probe outputs are preserved. Manual inspection found examples
of clearer attribution, not a measured general quality improvement:

- Baseline commentary called the synthetic DeepSeek and Zhipu API pitches
  official announcements without evidence of author affiliation. Candidate
  commentary described an author's announcement or an announcement without
  that unsupported official-source claim.
- Candidate commentary on the three token wins described the author's win
  rather than announcing giveaway days. Candidate release commentary removed
  the baseline's confusing denial that the hosting plan was an Acme claim.
- Both arms' headlines incorrectly upgraded the long crypto post's “is
  building” into “launches.” Interpretation did not prevent that error, even
  though the extracted claim preserved “is building.”
- Both arms already separated GLM praise from B.AI billing in their prose,
  despite the baseline classifier getting that distinction wrong. This is
  further evidence that correct prose understanding need not produce correct
  structured labels.
- The reviewed Japanese translations retained the central entities, amounts,
  attribution and negation. No clear ownership-related improvement was
  established. This was not an independent native-speaker translation review.

## Cost, latency and execution evidence

| Phase | Actual calls | Provider-reported model cost |
|---|---:|---:|
| Baseline classifier | 6 | $0.00110274 |
| Interpretation | 3 | $0.00081996 |
| Candidate classifier, including follow-up | 6 | $0.00129648 |
| Baseline cross-task probes | 3 | $0.00051450 |
| Candidate cross-task probes | 3 | $0.00074448 |
| Total new experiment | 21 | $0.00447816 |

Usage: 40,472 input tokens and 13,564 output tokens; no unknown usage or
automatic retry. Task-wide calls are 34/40 including the prior 13. Remaining
six calls were not spent. Earlier known classifier cost plus this experiment
is $0.00539616; the earlier translator's exact cost remains unknown, with its
existing $0.05 reserve retained. These are model costs, not Render compute.

The interpretation call took 10.605–18.996 seconds per five-post batch,
averaging 14.492 seconds. Measured serial classifier latency was 37.276 seconds
across all baseline batches versus 80.507 seconds for extraction plus candidate
classification. Classification-path model cost was about 1.92 times baseline
($0.00211644 versus $0.00110274). This is one small run, not a production latency
or cost forecast; potential reuse savings across other consumers were not
measured.

Both one-off staging-harvest jobs succeeded:

- `job-dathl3093c1s73al21a0`: 01:55:24–01:58:24 UTC, September 29.
- `job-dathneid0e5s73c5ct20`: 02:00:42–02:02:37 UTC, September 29.

Runtime file hashes were checked before model calls. No deployment, scheduler
resume, environment change, application database write or production prompt
edit occurred. The frozen quality candidate remains at its existing revision.

Eight offline harness tests passed, including real classifier injection into
both roles, unchanged baseline input, no answer leakage, quote validation,
pre-network call-budget enforcement, raw invalid-output capture and stopping
on unknown usage. These are harness tests, not eight more model evaluations.

Evidence: [initial manifest](manifest.local.json), [strict results](result.json),
[follow-up contract](followup/event-001-followup_contract.json), and
[follow-up results](followup/result.json). All 21 raw requests and provider
envelopes are in the `event-*-call_finished.json` files in these two directories.
The initial source payload is also retained in its job receipt; later additions
to the harness for the diagnostic do not erase the original run's script hash.

## Decision and next useful experiment

Do not advance this candidate: it missed the predeclared requirement to
improve original-case ownership, and the tracked-ad decision regressed once.
The sample is small, unblinded, heavily weighted toward Token Machine, and
not independently repeated. It cannot establish general model accuracy or
prove that upstream interpretation is a bad architecture.

My inference is that the next discriminating test should separate extraction
quality from label application: compare the current classifier using a
model-generated interpretation versus a human-checked interpretation on the
same failed posts, explicitly marking the offering, provider and referenced
model/prize. Reference-answer assistance would be declared for that diagnostic,
never presented as production accuracy. If the checked interpretation still
fails, revise how downstream labels attach to particular claims and entities
before investing in a more elaborate extractor. This next test has not run.
