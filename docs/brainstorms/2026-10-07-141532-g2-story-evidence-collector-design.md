---
title: "G2 shared story evidence collector"
created_at: "2026-10-07T14:15:32+09:00"
workstream: "G2"
session: "g2-fork-mistral-20261007"
status: "proposal-for-main-g2-plan-integration"
---

# G2 shared story evidence collector

The owner's requirement is explicit: context added for a manual headline must
become part of normal sampling. This document proposes the abstraction for the
main G2 session to integrate into its existing plan. It is a design brief,
not a second implementation plan or a completed implementation.

The normal sampler should provide two connected operations: discover possible
stories, then gather evidence for the selected story. Automatic selection and
a manually supplied post must enter the same second operation. That operation
finds related reporting, reactions, contradictions and older background;
the writer receives the relevant material within a measured limit.

## What the samples establish

The [Mistral contextual sample](../analysis/2026-10-07-134227-g2-mistral-contextual-chatter-sample.md)
froze evidence at `2026-10-07T04:38:20.535445+00:00`. Reproducing the then-current
global sampler and trimming rules yielded 64 recent posts, zero Chaton
references, and no selected announcement, from 3,806 eligible day posts.
An operator supplement supplied 50 sources, including 39 Chaton mentions
and three photos. The resulting writer cited only two sources. Those counts
describe different things: retrieved material, writer input, and factual support.
The supplement did not demonstrate automatic retrieval or independently
verify every matching post. Its inclusion of all 39 mentions is not a target.

The independent [PewDiePie/Ajax diagnosis](../analysis/2026-10-07-135538-g2-chatter-context-diagnosis.md)
found 49 stored seven-day keyword matches, two matching editor sources, and
one actual Chatter source. Context can be lost during discovery, trimming,
and the writer's restriction to `event.post_ids`. Fixing only one stage
does not establish that surrounding evidence reaches the model.

## Proposed shared boundary

Use the existing evidence projection and one reusable collector, with
discovery and selected-story scopes. A minimal interface is:

```text
build_packet(cutoff, policy)                 -> discovery packet
story_packet(subject, discovery, policy)    -> bounded story evidence
writer_request(subject, story evidence, voice, policy)
```

Names are illustrative; reuse the main session's `story_packet` function
rather than introduce a parallel framework. A manual entry point resolves
supplied anchor IDs from the database using the same cutoff checks, then
calls this collector. It must work even when an anchor was absent from the
global sample. Operator scripts must not maintain separate topic queries,
alias lists, ranking rules, or packet assembly.

The subject carries source anchor IDs and source-grounded entity/name seeds.
Story identity and selection rationale remain separate from additional
context. Editor summaries can guide selection, but their prose must not
become factual source evidence or invent search aliases. Retrieval has three
reusable routes: direct source relationships, distinctive names/aliases,
and the subject's announcement timeline.

## How the collector expands a story

1. **Resolve and preserve anchors.** Read their original, quoted and available
   parent evidence under both creation and fetch cutoffs. Preserve author and
   quoted-speaker ownership. Missing anchors or an anchor set too large for
   the budget produce an explicit hold.
2. **Find nearby relevant evidence.** Query stored direct quotes/replies and
   exact product/version/person names or distinctive phrases from the anchors.
   Include related recent posts omitted by the global sample. Shared brands
   and recency influence ranking; a shared brand alone does not establish
   relevance. Relation links identify candidates, not automatic endorsement.
3. **Learn bounded aliases from relevant bridge posts.** A post that connects
   an anchor name with another distinctive name can introduce a search seed.
   Record its post ID, source field, exact span and connection. Allow a fixed
   number of added terms and one expansion round. Preserve multiword phrases
   and version identity; capitalized-word overlap alone is insufficient.
4. **Recover the announcement timeline.** Search relevant earlier teasers,
   expected availability, postponements and actual launch updates. Exact-name
   search alone can miss a teaser that does not name the final version. Use
   bounded time windows plus official subject/team accounts or stored entity
   associations to nominate those candidates; include them only when source
   relationships, a bridge post, or sufficiently specific product context
   links them to this release. An author/brand match alone is insufficient.
5. **Look backward for relevant history.** Search a bounded multi-month window
   using those supported names/phrases. Rank material links above brand and
   recency, and reserve room for useful historical context. An earlier model
   version may explain history without supporting claims about this release.
6. **Pack and explain omissions.** Deduplicate IDs and repeated content; favor
   useful source/author diversity, attributable reactions and contradictions.
   Exclude unrelated releases, name collisions, token promotions and generic
   brand chatter. Record inclusion reasons, query limits/timeouts, counts,
   rejected/truncated material and final bytes. Avoid claiming complete recall.

For Mistral, the route is the official “Mistral Large 4” / “Le Chonk” anchor,
relevant posts connecting it to “Le Chaton Fat,” then stored earlier references
to that phrase. “Chaton” must be discovered from evidence, not hardcoded or
supplied only by the operator. A nickname can establish cultural context
without proving a naming motive or official mascot status.

This can use bounded database queries and deterministic ranking first. It
does not require another model call, paid X search, vector database, or a
new collection job. Phrase/alias rules need negative fixtures before adoption.

## Evidence, budgets and attribution

Keep three source sets explicit: selected anchors, additional writer context,
and sources actually supporting the final copy. Attach roles such as primary
announcement, reaction, background and contradiction to context, with dates
and inclusion reasons. These are retrieval labels, not verified truth labels.
Expand the writer's allowed evidence set beyond editor anchors; retain exact
support checks and derive cited IDs from validated source support.

Protect anchors and a measured allowance for high-value context when it
exists. Do not remove all context before trimming repetitive recent sources.
A single-post story remains valid when no relevant context is found. Bound
candidate counts, expansion rounds, historical range, database time, final
evidence bytes, image count, full request/schema size and model reservation.
Emit coverage facts when a limit or timeout reduces recall.

The main session is currently implementing 240,000 discovery bytes,
96,000 selected-story bytes, 24 context posts and a 180-day historical window.
These are its implementation choices, not numerical requirements introduced
by this fork. Measure actual request size and retained useful evidence before
claiming the limits are adequate. The October 7 staging ledger was already
$1.482914 in retained reservations after seven text calls; this fork authorizes
no further paid calls.

Chatter and Pulse should reuse a frozen story evidence bundle for the same
subject/cutoff/policy, while applying their own voice and selection rules.
Collect only for selected stories eligible to be written, preserving unchanged
story/hero checks. New reaction IDs must not automatically create a new story
or reset its age. Persist used-post IDs, their distinct count and every used
URL in existing edition evidence; keep candidate and input counts separate.

Images retain source-post ownership and actual delivery status. A URL is not
an inspected image, and an image description is not automatically claim
support. Main G2 has kept image claim references as a separate decision;
this proposal does not silently change that boundary.

## Owner's additional case: GLM teaser versus actual launch

While this brief was being prepared, the owner asked whether it would catch
a release like GLM 5.2: the team teased a weekend launch, but the release took
another five days. This is a user-supplied design case; the underlying posts
and exact dates have not been checked in this fork.

The collector should make the earlier teaser and actual release available
together, with any intervening postponement/update. Preserve the original
wording, source ownership, post timestamps, claimed launch date/window, and
date precision. Distinguish a tease, target, firm commitment and observed
availability. Never infer that a generic same-team teaser concerns this
version solely because it appeared nearby in time.

The writer can describe how expectations changed when those sources are
linked. A numerical delay requires compatible expected and actual dates;
“the weekend” may identify a range and depend on timezone. Use the supported
range or qualitative timing when the evidence cannot establish exactly five
days. API launch and open-weight availability are separate milestones.
This also covers renamed releases and a teaser with no final model name.
Store missing links or ambiguous dates as coverage/uncertainty facts, rather
than filling the gap with an assumed promise.

## Main G2 integration and regression net

The existing plan is
[`2026-09-30-051835-docs-g2-voices-corpus-plan.md`](../plans/2026-09-30-051835-docs-g2-voices-corpus-plan.md).
Integrate this contract into U3 gathering/grouping, U4 writer input, U6 manual
entry points, U8 call-chain verification, and existing edition-evidence
persistence. The active `g2-context-attribution-20261007` session owns code.
Its in-progress `monitor/editorial/context.py` already supplies a selected-story
stage, bounded name expansion and history lookup; service/writer changes
already pass expanded context. These are uncommitted observations, not a
completed qualification. Reconcile this brief with that work in place.

Acceptance should exercise the real service-to-request-to-edition path:

- Mistral's release anchor recovers relevant nickname backstory through a
  bridge post, with no Mistral-specific rule or operator-provided Chaton seed.
- Ajax/PewDiePie retains material ban chronology, contradictory claims and
  useful older background; not all 49 keyword matches must be included.
- A GLM-like fixture connects an unnamed weekend teaser, a relevant follow-up
  and the eventual named launch. A different same-team release is excluded.
  Exact-date fixtures support a delay calculation; an ambiguous weekend
  window retains its uncertainty and does not become an invented deadline.
- Unrelated same-brand posts, ambiguous names, different release versions,
  repeated promotions and unsupported alias expansions are excluded or
  correctly labeled as background.
- Future-created or late-fetched posts are excluded. Month-old relevant
  evidence survives a busy recent period; a single-source story stays valid.
- Under tight budgets anchors and useful context survive, or an explicit
  hold/coverage limit is recorded. Inspect full captured writer requests.
- Manual and automatic entry points invoke the same collector and produce
  the same evidence for the same anchors, cutoff and policy. Include a manual
  anchor absent from the discovery packet.
- Retrieved context is available to the writer without becoming an automatic
  citation. Final used IDs/count/URLs deduplicate and match validated support.
- Existing unchanged-story, publication-fence, budget and no-resend behavior
  remains covered. Collection adds no paid provider calls.

Discovery recall remains a separate acceptance concern: a selected-story
collector cannot rescue a release never nominated. Preserve the existing
quiet-brand/important-release discovery requirement and test primary-release
retention separately. No fresh headline-quality comparison is established
by this documentation or the earlier manual sample.
