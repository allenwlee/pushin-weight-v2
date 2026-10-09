---
title: "Verify evidence delivery before judging an editorial voice"
date: "2026-10-09"
category: workflow-issues
module: "G2 editorial evidence and writing"
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "A writer produces weak or misleading copy despite apparently sufficient database context"
  - "Comparing voices or models across a multi-stage editorial pipeline"
  - "Passing selected evidence from an editor to writers, charts or presentation"
tags: [editorial, context-retrieval, source-attribution, voice-evaluation, general-launch]
---

# Verify evidence delivery before judging an editorial voice

## Context

During General round one, an Ajax/PewDiePie Chatter result prompted a question
about whether the voice or database context was inadequate. The saved October 7
[diagnosis](../../analysis/2026-10-07-135538-g2-chatter-context-diagnosis.md)
traced the actual input through three stages:

| Stage | Keyword matches for the selected story |
| --- | --- |
| Eligible database lookup before the frozen cutoff | 49 |
| Frozen editor packet | 2 |
| Completed writer request | 1 |

These were keyword matches, not 49 independent confirmations. The database and
the writer were seeing materially different evidence. Broad discovery sampling
missed relevant recent posts; the old byte-cap loop removed background first;
the writer accepted only the editor's selected post IDs. A seven-day setting
therefore did not establish that seven days of context reached the writer.

The October 6–7 G2 session history corroborates the sequence: source/brand
validation was repaired first, then inspection of the saved writer request
exposed this separate context-delivery problem (session history). Improving
factual validation had not, by itself, restored the missing context.

This learning concerns the verified retrieval and attribution repair. The
repair's local results did not establish better live prose, complete discovery
recall, or a working image-claim citation system.

## Guidance

### Inspect the final input before changing the model or voice

Compare the available source population, discovery sample, selected story
evidence and actual writer request. Record which relevant items disappeared,
where they disappeared, and whether the loss came from sampling, filtering,
byte limits or a missing expansion step. Keep the original cutoff and source
identities so the comparison is reproducible.

Discovery and selected-story retrieval answer different questions. Discovery
chooses what deserves attention; retrieval supplies the evidence needed to
write the chosen story. A larger discovery sample alone cannot guarantee that
the writer receives the right backstory.

### Preserve relevant context within explicit limits

The repaired collector retains selected anchors, retrieves bounded related
background, records omitted context and timeouts, and uses evidenced names or
relationships to distinguish a story from unrelated posts about the same brand.
It reserves historical capacity when eligible history exists. It does not
silently substitute context for missing selected sources.

Verified source locations in the retained G2 checkout:

- [Story collector](../../../monitor/editorial/context.py),
  `story_packet` at line 278 and `_collect_story_packet` at line 293. The
  selection/coverage result at lines 470–514 retains anchor IDs, included IDs,
  omitted-context counts, byte limits and query-timeout state.
- [Writer request](../../../monitor/editorial/writing.py),
  line 64: the writer receives both selected anchor IDs and the collector's
  included context IDs. The prompt distinguishes supplied history from proof
  of a new event and excludes editor prose as factual evidence.
- [Service orchestration](../../../monitor/editorial/service.py),
  line 255: story evidence is saved before the voice loop and reused from the
  saved event-specific packet.

These paths were inspected on October 9. The root coordination checkout is
older; the linked G2 checkout is the source for these behavior claims.

### Keep three evidence populations distinct

1. **Anchors:** posts identifying the selected story.
2. **Retrieved background:** relevant material supplied to explain it.
3. **Cited support:** sources actually used to support the saved copy.

Use the last population for displayed source counts and links. Neither every
search hit nor every writer input automatically becomes a citation. An attached
image also needs an auditable claim reference before its contents can serve as
validated factual support; successful attachment proves delivery only.

### Test the boundary the user experiences

The [context regression tests](../../../tests/test_editorial_context.py)
check that old relevant material reaches `writer_request`, unrelated name
collisions and late-fetched posts stay out, selected anchors survive tight
limits, and the automatic and manual entry points share the same retrieval.
The test at line 39 explicitly checks the writer request's source-ID mapping;
testing only the collector's intermediate list would miss the original failure.

For a voice comparison, hold the selected story and frozen evidence constant,
then compare the intended voice/model change under a fixed rubric and allowance.
Record retrieval correctness and human copy quality separately.

## Why This Matters

A technically successful database query, editor call or media download can
coexist with an impoverished writer request. Without inspecting the handoff,
the next agent may spend another evaluation budget changing models or prompts
while reproducing the same input defect. The final code shows the repaired
path; the historical 49 → 2 → 1 trace explains why this diagnosis comes first.

## When to Apply

- Japanese and Chinese house-voice work using the established editorial path.
- Chart-setter work where source measurements must survive editorial selection.
- Graphicsed work distinguishing a supplied image from evidence for its subject.
- Page/API/share integrations where the final consumer must retain exact saved
  content, citations and locale.

The last three are applications proposed for round two, not claims that those
new integrations have already passed verification.

## Examples

The [repair results](../../analysis/2026-10-07-144000-g2-context-attribution-results.md)
record 118 local tests, including 56 requiring PostgreSQL, plus a separate
saved-source replay. The replay used 99 real saved posts with 20,000 synthetic
background posts; it recovered the Mistral backstory and excluded identified
token promotions. That dataset was not production, and its timings do not
establish production capacity. No fresh model-quality verdict followed from
those offline checks.

A round-two Japanese voice example should therefore retain the same selected
story and auditable evidence as its comparison case. Its review can then judge
Japanese expression while separately checking factual support, attribution and
uncertainty. A missing background item should be repaired before interpreting
the example as a voice failure.

## Related

- [OriginalContent cutover checks](../data-migration/2026-10-08-143200-original-content-cutover-checks.md)
  covers saved records and selection pointers; it addresses a different boundary.
- [Named-block photo attribution](2026-10-05-142500-staff-photo-named-block-attribution.md)
  separates source association, image attribution and file availability.
- [Round-one closeout](../../analysis/2026-10-09-110145-general-round-one-closeout.md)
  maps the broader round's evidence into the next workstreams.
