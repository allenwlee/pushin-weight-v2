---
title: Prodsimtest — repaired packets on GPT6.0 Sol/medium
created_at: "2026-10-13T22:43:24+09:00"
workstream: G2
status: completed-owner-quality-review-pending
---

# Prodsimtest — repaired packets on GPT6.0 Sol/medium

Both first English runs passed on GPT6.0 Sol/medium. The exact successful
[6.1/high experiment](2026-10-13-195747-g2-prodsimtest-evidence-attribution.md)
was reused: repaired Wang image/identity evidence, the catchy/punny sentence
and relaxed headline attribution. Only model and reasoning effort changed in
the complete API requests. [Browser comparison](http://fuchitalee:58713/?run=db-wang-587&tab=review)
retains all prior runs and compares these two pairs directly.

| Story | GPT6.0 Sol/medium | GPT6.1 Sol/high | New recorded cost |
| --- | --- | --- | --- |
| Wang | THE PRICE IS WANG | THRIFT HAPPENS! | $0.029113 |
| Mistral | CHONK NOW, WEIGHTS LATER | CHONK AND AWE | $0.017710 |

Wang's supporting line identifies Scale AI's founder and reports the photo's
$30 thrift label versus the crossed-out $5,699 Gucci label. Its article treats
the garment prices as Wang's image claims. Mistral retains API availability
versus planned end-of-October open weights, plus the model's total/active
parameter distinction. Replies are the first saved outputs, without editing.
Prior generated headlines, model replies or examples were not supplied as inputs.

## Conditions and evidence

The deployed headline worker at db5510ccc94ea326dd5f81e833a9c791e5e84d99
runs the shared production transport, accounting, source normalization and copy
validation. Route: direct OpenAI Chat Completions, model gpt-6-sol, effort medium,
default tier, 4096 completion tokens, 90-second timeout. Current configured
6.0 accounting rates apply; production daily/call/in-flight guards remain active.

Full wire equality is proved after restoring only model=gpt-6.1-sol and
reasoning_effort=high. All messages, original/supplemental evidence, image blocks,
source schema and other parameters are identical to the successful repaired pair.
No fresh collection, transcription or identity research was performed.

Two first calls, zero retries/publications; USD0.50 combined reservation ceiling,
USD0.046823 recorded ledger total. Read-only production postchecks verify both
complete saved requests, hashes, returned models and final copy, plus zero test
editions/text publications. The original edition and live English voice are
preserved. This test does not change the production prompt or choose a new favorite.

## Review verification

18 focused regressions, affected-file Ruff, syntax and whitespace checks pass.
The completed pair review has 12 saved results across 11 cases. All 96
desktop/mobile run/tab states and six clipboard/source/keyboard/reload/download
interaction groups pass, with no page errors. New desktop/mobile screenshots
were inspected. Existing owner Chrome window 919892289 was observed at the
new Wang URL; other windows/tabs and the owned preview service are preserved.
The isolated test browser is closed.

Private evidence remains under .local/g2-production-parity-20261013/packet-repair/
in the retained original G2 worktree: gpt60-model-delta-proof.json, both
*-gpt60-preflight.json and *-gpt60-result.json, gpt60-post-run-verification.json,
and browser-gpt60-pair/. Final manifest: database-repair-gpt60-pair-review-manifest.json.
The earlier Wang-only manifest and all previous replies are retained.

Canonical test tree/plan and local changes remain for repeated tests. No new
commit/push, production prompt change or application deployment was requested.
[Reusable instructions](../../tests/editorial_replay/README.md).
[Same plan](../plans/2026-10-09-064803-feat-g2-round2-voices-plan.md).
