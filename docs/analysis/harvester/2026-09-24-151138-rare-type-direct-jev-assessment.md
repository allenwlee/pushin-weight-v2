---
title: Rare-Type Direct TypeSafe Jev Assessment
date: 2026-09-24
topic: combined-rare-type-extra-search
status: partial-live-evidence
---

# Rare-Type Direct TypeSafe Jev Assessment

This is a direct-TypeSafe assessment of the provisional v3 rare-type search gate. It does not authorize enabling the lane or deploying it. The historical 37/56 OpenRouter response set is not mixed into these counts.

## Exact route and evidence

- API: `POST https://api.typesafe.ai/v1/systemone`, pinned `jev-1.13.0`, no OpenRouter fallback. The credential was loaded from the ignored, mode-600 app `.env`; its value is not in this report or Git.
- Questions: `rare-types-jev-questions-v1`, hash `2fd756cd9548eb0521066aa31fccd186ccf4d5daaeafdd4b4739f288fcc003df`. The questions did not change between the paid calls and the offline reroute.
- Final routing: `rare-types-jev-routing-v3`, threshold hash `1c6dc92d61493569059ba2ea2de6a0a3dd2bf660080689b98617f3be40a808d8`. It scopes junk flags to the types they contradict, uses explicit job/event route thresholds, and allows source-linked first-person role changes to survive a contradictory static-bio score.
- Frozen 56-case corpus: `tests/fixtures/rare_type_extra_search/gate_cases.json`. Private, append-only direct responses and summaries: `/Users/fuchitalee/.local/share/pushinweight/jev-assessments/20260924-direct-v3/`.
- Separate deterministic 56-post v3 live sample: selected by ascending SHA-256 of tweet ID from 1,337 unique historical TwitterAPI hits. Private corpus, responses, and summaries: `/Users/fuchitalee/.local/share/pushinweight/jev-assessments/20260924-direct-v3-live56/`. Its source selection manifest is `/Users/fuchitalee/.local/share/pushinweight/jev-assessments/v3-live-cohort-unlabeled.json`.

## Results

| Check | Result | Interpretation |
| --- | --- | --- |
| Frozen direct capture | 56/56 responses, zero errors | Full provider response set for this fixed corpus. |
| Frozen keeper routing before correction | 7 true keeps, 21 missed keeps, 0 false keeps, 28 true drops | The global static-bio veto wrongly discarded many non-personnel positives. |
| Frozen keeper routing after correction | 28 true keeps, 0 missed keeps, 0 false keeps, 28 true drops | In-sample result on the corpus used to correct routing; not a prospective accuracy estimate. |
| Frozen type labels after correction | 55/56 exact; no false type labels | One hackathon is kept as an opportunity but lacks its secondary event label. |
| Frozen hard negatives | 0 false keeps | All 18 explicitly tagged hard-negative cases remain unkept. |
| Separate live direct capture | 54/56 responses; two HTTP 529 errors | The runner recorded both errors and made no retry. This is incomplete provider evidence. |
| Live routing on 54 usable responses | 11 kept, 17 review-needed, 26 junk | The 11 kept posts are model-release *candidates*, mostly about Step 5 Preview; they are not 11 distinct releases or independently confirmed positives. |
| Exact-ID production overlap | 9/56 selected live post IDs already stored | Read-only query against `pushinweight-db-shadow`; overlap is not relevance. |

The two runs made 112 physical TypeSafe calls in total. Their conservative preflight reservations sum to **$0.036414462** against the assessment's $0.25 ceiling. Reported token usage for the 110 successful responses implies **$0.009196950** at the published input-token list price. TypeSafe provided no billed-dollar field, and the two 529 responses have no usage receipt; neither figure is an invoice. See the [TypeSafe API reference](https://docs.typesafe.ai/api) and [model/pricing reference](https://docs.typesafe.ai/models).

## Remaining evidence and operational limits

The frozen score was used to choose the routing correction, so it cannot independently validate that correction. The live 56-post sample has not been independently labeled; the two 529 responses also prevent a complete provider sample. Do not record a passing R17 quality assessment, assert live precision/recall, or enable scheduled collection from this report. Preserve the saved provider receipts and use a separately reviewed live cohort before enablement. Any explicit retry of the two 529 cases must have its own identity, budget, and receipt; the captured run itself remains unchanged.

The repo's separate read-only latest-20 production health check was repeated on the same IDs after 30 minutes: 20/20 remained missing both commentary fields, while 12/12 non-`zh-Hans` posts had Chinese translation. This branch was not deployed and the rare-type lane stayed disabled; that finding is not attributed to the Jev change.
