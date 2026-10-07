---
title: Chatter context diagnosis — available evidence lost before writing
created_at: "2026-10-07T13:55:38+09:00"
scope: read-only diagnosis
---

# Chatter context diagnosis

For the PewDiePie/Ajax sample, context delivery is demonstrably incomplete.
The database contains more surrounding material than the writer received.
This does not establish that more context alone will produce a good headline.

| Stage | Observed evidence |
| --- | --- |
| Database lookup | 49 rows matching PewDiePie, Ajax or Odysseus in original/quoted text during the seven days before the frozen cutoff. 21 latest-day rows; 28 older rows. All fetched before cutoff. |
| Frozen editor packet | 105 of 2,497 eligible latest-day posts; two keyword matches; zero context posts, people, stories, headline leads or chart groups. |
| Completed Chatter writer request, iteration 2 | One post, `2106428676351090913`, plus three downloaded image attachments. No surrounding posts. |

Read-only production (`pushinweight_shadow`) and staging (`pushinweight_staging`)
lookups returned identical rows. The query had a 100-row ceiling and returned 49;
these are keyword matches, not 49 independently verified accounts of the event.
There are 47 distinct author handles, with duplicates/quotes and irrelevant or
low-value material still requiring filtering. No match is authored or quoted
under the PewDiePie handle. The original video was not fetched or verified.
Cutoff: `2026-10-04T01:00:40.731920+00:00`.

## Where context is lost

1. `build_packet` samples the broad last-day stream by hour. This is discovery,
   not retrieval of a complete selected story. Nineteen of the 21 matching
   recent-day rows were outside the frozen editor packet.
2. Its older-context query uses shared tracked brands and recency, not the
   selected story's people/products. It searches only outside the latest day;
   it cannot recover relevant recent posts missed by discovery sampling.
3. The byte-budget loop removes `context` first, before reducing `posts`.
   The prior staging record explicitly records older context being trimmed;
   the frozen packet confirms zero surviving rows.
4. `writer_request` sends only rows whose IDs the editor put in `event.post_ids`.
   It performs no event-specific database expansion. Even the packet's second
   Ajax mention (`2106504203254268289`, a broad recap) did not reach Chatter.
5. Three images were actually attached by the Sol CLI adapter. They are
   third-party infographic cards with release/training/refusal details. The
   current source-check schema can cite only `original_text`, `stored_quote`
   and `local_parent`; image evidence has no owned reference. Thus image
   delivery and auditable image use are separate, and the latter is missing.

Code: `monitor/editorial/evidence.py:77` (selection), `:99` (older context),
`:214` (trimming); `monitor/editorial/writing.py:52` (writer source filter);
`monitor/editorial/grounding.py` (text-only support fields).

## What the database could add

The omitted rows include reports of a ban, appeal/reinstatement and a second
ban; reactions framing model-training restrictions as a double standard;
local-model/creator reactions; and conflicting release/download claims.
Examples: `2106250131570032978`, `2106094850697232611`,
`2106413331296768468`, `2106273901450023241`, `2105499386168164713`.

Those provide possible human-interest angles and contradictions to explain.
They remain source claims. Repeated reactions are not independent verification,
and some Ajax keyword matches concern opportunistic tokens or other topics.
The delivered images likewise add claims about training attempts and fan data
donations, but are attributed infographics, not direct verification of the video.

The saved successful September writing recipe included agent-selected nearby
context and image review. This test did not reproduce that input recipe. The
weak headline is therefore not a clean test of the Chatter voice alone.

## Recommended next change

After event selection, retrieve bounded surrounding evidence for that specific
story across the full eligible seven-day window, including recent rows missed
by discovery. Use named entities, original/quoted/parent relationships and
source relevance; a common brand alone is insufficient. Keep timestamps and
source ownership, distinguish anchor evidence from background/reactions and
contradictions, and reserve context space instead of trimming all of it first.
Pass the resulting original evidence directly to the writer without restoring
editor prose as factual evidence. Add owned references for actually attached
images before allowing image-grounded claims.

Regression proof should check the final writer request: relevant omitted rows
arrive, unrelated same-brand rows do not, core context survives the byte cap,
future-fetched rows remain excluded, and image claims reference an attached
asset. Then compare the same story/model/voice with the old and corrected
packets under a fresh bounded allowance. Do not claim quality improvement until
that comparison is actually run.

## Evidence and scope

Saved lookup SQL and full results: `.local/g2-context-diagnosis-20261007/`.
Saved writer request and downloaded image receipts:
`.local/g2-source-contract-live-20261007-iteration-2/`.
The direct staging CLI connection failed; the existing SSH/TLS route completed
the read-only query. No collection, model call, database mutation, runtime
change or deployment occurred. The prior three-iteration live ceiling remains
exhausted. Context repair is a distinct diagnosis from the pending numeric audit.
