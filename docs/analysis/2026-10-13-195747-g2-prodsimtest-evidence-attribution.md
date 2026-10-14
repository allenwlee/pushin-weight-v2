---
title: Prodsimtest — source evidence and headline attribution
created_at: "2026-10-13T19:57:47+09:00"
workstream: G2
status: completed-owner-quality-review-pending
---

# Prodsimtest — source evidence and headline attribution

The owner approves repairing Wang's missing image/identity evidence and relaxing
headline attribution for both English stories on GPT6.1 Sol/high. Two first
calls passed the existing source normalizer and copy validator, with no rewrite
or retry. [Review in the owner browser](http://fuchitalee:58713/?run=db-wang-574&tab=review).

| Story | First headline | Recorded ledger cost |
| --- | --- | --- |
| wang | THRIFT HAPPENS! | $0.040063 |
| mistral-first | CHONK AND AWE | $0.019360 |

Wang's supporting line now identifies Scale's founder and contrasts the shirt's
$30 Santa Cruz thrift label with the crossed-out$5,699 Gucci label. Its article
also reads the Crocs/glasses corrections and preserves that image labels are
the poster's claims rather than verified retail facts. All three supplied
records are cited. Mistral's supporting line preserves API availability versus
planned end-of-October open weights; its source packet is unchanged.

## Evidence repair

Wang retains the original database post, quote and source-image URL. Two
separately identified supplemental records add the reviewed image transcription
and an official identity excerpt. They are labelled supplemental_evidence,
with their own URL, source date, evidence kind and reviewed-text hash. They are
not invented X/database posts. Production's existing generic original_text
passage binding represents the text of each supplementary evidence record.
No deployed source module, transport or validator is patched.

The archived source image matches the prior G2 native-post manifest:
c0ddf32f548686cf725da584b8a253f20f63b2a16f98d9a59ada588d1344538e.
Tesseract OCR was followed by agent visual verification because OCR missed the
red handwriting. No target headline, interpretation of motive, verified retail
price or derived outfit total was supplied.

The identity excerpt comes from [Scale's June12,2025 announcement](https://scale.com/blog/scale-ai-announces-next-phase-of-company-evolution),
which identifies its founder and his move to Meta's AI efforts. It is historical
background, not proof of a current2026 role or a new personnel change. Supplemental
records were collected/reviewed for this test now; they are not claimed to have
been present in the database at the September24 cutoff.

## Prompt and conditions

The single changed system-prompt sentence now reads:

> Preserve whose claim it is in the supporting line and article in every language. The headline may use playful shorthand; preserve attribution or uncertainty in the headline whenever omitting it would mislead.

The earlier catchy/punny sentence remains. Complete comparison proves no other
system instruction changes. Model/effort, endpoint, tier, image blocks, output
allowance, timeout and primary source text are fixed. Mistral's full user
message/schema and packet are unchanged. Wang has only the two declared
supplements and their mechanically derived source options/schema. Prior model
replies and suggested target headlines never enter the writer request.

The worker imports deployeddb5510cc production request/projection, API transport,
normal accounting/fences and source/copy validators. One call per story, zero
retries, USD0.50 maximum combined reservation; actual ledger total
USD0.059423. Saved complete API requests and copy match both fixtures.
Zero test editions/canonical text publications; the original edition and live
English model/voice are preserved. Source Post/identity records were not changed.
No production deployment or new Git delivery endpoint is selected.

This fixes the observed missing price/identity facts in the Wang copy. Wang's
packet and attribution changed together, so the output does not isolate their
separate effects. Mistral's one-sentence comparison remains a single sampled
pair. Owner taste acceptance and any future production choice remain separate.

## Verification and retained review

17 focused regressions, affected-file Ruff, syntax and whitespace checks pass.
80 desktop/mobile run/tab states plus6 interaction groups pass with no page
errors. Exact copy, frozen request, source packet, comparisons, hashes, reload,
source navigation, keyboard/clipboard and JSON/portable HTML are checked.
New desktop/mobile screenshots are inspected. The initial browser check missed
the source-navigation button while only0.39px of it was visible; its failure is
retained. The verification wrapper now scrolls to top and requires the actual
target fully visible before a physical click. The corrected full run passes;
this was not a model retry or a public app change.

The same page now retains10 saved results across9 cases. Owner Chrome window
919892289 is observed at the new Wang URL. The17:36 published test branch remains
atcc75c569 remotely; these local test/renderer/report changes have no new commit/
push selection. Retain the canonical test worktree, original G2/private artifacts,
owned preview58713 and other owners.

Private evidence:.local/g2-production-parity-20261013/packet-repair/ under the
retained G2 tree. Latest manifest:database-repair-review-manifest.json beside it.
[Reusable instructions](../../tests/editorial_replay/README.md).
[Same plan](../plans/2026-10-09-064803-feat-g2-round2-voices-plan.md).
