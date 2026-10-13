---
title: Prodsimtest — historical database scenarios
created_at: "2026-10-13T18:54:45+09:00"
workstream: G2
status: completed-local-review
---

# Prodsimtest — historical database scenarios

The owner requests Wang's wardrobe correction and the first official Mistral
announcement using database-built inputs. English6.0/medium runs were followed
by one added style sentence and then owner-selected6.1/high. Each version is
preserved without copy editing in the [local review](http://fuchitalee:58713/?run=db-wang-568&tab=review).

| Story | Model/effort | Prompt | First headline | Recorded ledger cost |
| --- | --- | --- | --- | --- |
| wang | gpt-6-sol/medium | locked | WANG SETS THE DRESS RECORD STRAIGHT | $0.019558 |
| mistral-first | gpt-6-sol/medium | locked | LE CHONK IS HERE — THE WEIGHTS AREN’T | $0.019423 |
| wang | gpt-6-sol/medium | catchy/punny | UNDERDRESSED? WANG CALLS FASHION FOUL | $0.018953 |
| mistral-first | gpt-6-sol/medium | catchy/punny | CHONK NOW, WEIGHTS LATER | $0.019938 |
| wang | gpt-6.1-sol/high | catchy/punny | WANG'S FASHION RE-DRESS | $0.030133 |
| mistral-first | gpt-6.1-sol/high | catchy/punny | Mistral touts ‘Le Chonk’: Big model, weights later | $0.028668 |

Six first calls, zero automatic/quality retries, USD0.136673
total recorded ledger cost. HTTP200/stop and normal source/copy validation pass.
Read-only postchecks confirm the complete saved API requests and headlines
match the fixtures/results, zero test editions or canonical text publications,
the original Mistral edition is preserved, and live English model/prompt remain
unchanged. Source-faithfulness validation does not certify humor or completeness.

## Database reconstruction and bounds

Deployed revision:db5510ccc94ea326dd5f81e833a9c791e5e84d99.
The harness executes on the actual headline worker and imports build_packet,
post_evidence, story_packet, writer_request, request_payload, json_call,
normalize_reply, validate_copy and normal accounting/fence guards. Production
application files are unchanged. Implementation is retained in the canonical
test/g2-production-replay-review checkout, based oncc75c569 with local test edits.

- Wang anchor2103127068318089313:posted September24 14:19:01UTC,
  fetched14:31:16UTC; cutoff14:45UTC. Its original price-label photo and embedded
  Goltra quote are supplied. The separate Goltra source and Wang follow-up rows
  were absent. The collector finds no distinctive terms, so no extra history.
- Official Mistral anchor2107457414387622310:posted October6 13:06:16UTC,
  fetched13:15:39UTC; cutoff13:30UTC. The history lookup reports a production query timeout and includes
  no additional posts. The stored video supplies no pixels through the current
  photo-only projection.
- Both anchors were outside the ordinary dispatch sample and explicitly
  nominated by the owner. These are writer simulations, not automatic editorial
  selection, queue execution, publication or a recovery of the original CLI
  conditions.
- Source authored and fetched timestamps must precede the cutoff. Today's
  stored profile/classification revisions and image URLs are used; historical
  revisions/pixels are not recovered. Retained editor metadata is not factual
  writer input. Packets are frozen once, and all reruns reuse them unchanged.

Wang copy still omits the image's price corrections in every version. That is a
remaining reading/context limitation, despite validation passing. Single first
calls do not establish a causal quality difference or justify a new production
writer selection.

## Controlled changes

The added sentence is exactly:

> Write a catchy, punny, tongue-in-cheek print headline and supporting byline.

It is verified against the deployed chatter-en-v1 source and earlier Mistral CLI
request, then added after the current voice opening. Full request comparison
proves that only this sentence changes in the style pair. The model pair proves
that only model/effort change on the wire; prompt, evidence, schema, images,
endpoint, tier, completion allowance and timeout remain fixed. Rates use the
deployed6.1 route. Normal production budgets and in-flight guards stay active.
Each authorized two-call round has USD0.50 maximum reservation/zero retries.

## Reusable review and evidence

The same HTML retains the original published/replay cohort and all six new
results:8 saved results across7 test cases. Each dropdown selection updates
copy, comparison, source packet, full request, wire hash and reply together.
Earlier CLI references are labelled as different conditions; style/model pairs
compare the same frozen packet. The page performs no provider calls.

15 focused pure tests, affected-file Ruff/syntax/whitespace checks pass.
64 desktop/mobile run/tab states plus6 interaction groups pass without page
errors, including reload, source navigation, keyboard tabs, clipboard and
reply/portable HTML downloads. Exact expectations come from recorded artifacts.
New desktop/mobile top-of-page screenshots are inspected; the existing owner
Chrome window919892289 is observed at the6.1 Wang review URL. No public app UI,
main/staging Git or application deployment action is selected.

Private first fixtures/results, delta proofs, accounting checks and browser
evidence remain under the retained G2 tree:
.local/g2-production-parity-20261013/database-scenarios/.
The latest private manifest is database-model-review-manifest.json beside that
directory. Entry points and usage: [README](../../tests/editorial_replay/README.md).
Same [plan](../plans/2026-10-09-064803-feat-g2-round2-voices-plan.md).
Keep the canonical test tree, original dirty G2, stable58713preview and other
owners' resources for future authorized tests.
