---
title: G2 source-contract repair — three live iterations
created_at: "2026-10-07T12:23:29+09:00"
status: quality-not-qualified
scope: local implementation, offline regressions and bounded staging model trials
---

# G2 source-contract repair — three live iterations

The pipeline completed once and saved both Chatter and Pulse stories in staging,
but the final candidate is **not quality-qualified**. Three live iterations used
five model calls. The limit is exhausted; no fourth iteration was sent.

The owner requested implementing existing-headline safeguards, running tests,
and iterating on failures while recording the count and major changes. Before
paid work, the loop was bounded to three iterations, at most three calls each,
and $1.50 total staging-day reservations. All trials used the same frozen
105-post packet: `0eb40ba4dd0f2737cbd87918b588586c006371c7c2bfe1a9e62672488a596705`.
Acceptance covered source/brand/speaker ownership, truthful event framing and
numbers, recognizable Chatter wordplay, and substantive Pulse copy. Editor
proposals were reviewed as well as final stories. No external facts were added.

## Iteration count and changes

| Iteration | Result | Major changes tested |
| --- | --- | --- |
| 1 | Editor completed in 97.27s; all 20 proposals failed chart validation. No writers. | Complete source/brand/field/span schema alternatives; code-derived event brands; writer receives original sources without editor prose; supported-copy equality; separate schema budget. |
| 2 | Editor, Sol Chatter and Pulse completed. Two editions persisted in staging. Quality review found remaining defects. | Unavailable charts bound to `unavailable`/empty facts; no existing stories bound to `new`/null; absent people bound to empty IDs; six-development shortlist; grouping and attribution instructions. |
| 3 | Editor returned HTTP 200 in 48.21s but local ownership validation held it. No writers. | Code-derived audit speaker; repeated-author groups and unverified independence metadata; narrow rejection of observed independence overclaims and numeric prose with an all-empty audit; substantive byline instruction. Fresh-copy qualification preserved iteration 2's editions. |
| Offline follow-up | 82 final G2 tests passed. No additional model call. | Removed the redundant model-generated `post_ids` list. Code now derives canonical source IDs from validated source checks, as it already derives brands and speakers. |

Iteration 1 selected `chart_support=not_supported` without any chart facts, and
`change=unchanged` without existing stories. Those are invalid combinations,
not a transport failure. The schema now makes them unavailable. It also called
same-account reports independent and labeled third-party reporting as announcements.

Iteration 2 passed the pipeline. Its independent writers corrected attribution
in the final copy. However, the editor still described the DeepSeek reports as
independent and left number ownership as `none`; Pulse's byline was merely a
source credit, and its numeric source audit was empty. These are not a clean
quality pass.

Iteration 3's DeepSeek proposal listed five posts but checked only two. Other
proposals still used figures with `number_ownership=none`. The saved error is
`invalid_source_support`, with the precise diagnostic
`source_support_outside_cited_posts`. The original provider response is retained.
After adapting a **copy** of that response to the final source-ID contract by
removing the obsolete duplicate list, source ownership passes but numeric audit
validation still fails. This is an offline diagnosis, not a successful live rerun.

## What was borrowed from existing headlines

- Complete source/brand alternatives from `_bound_headline_format`, rather than
  unrelated lists of legal IDs. Both paths share `closed_object` construction.
- Final writing from source evidence without earlier draft prose, following the
  ledger-only branch of `build_per_brand_critic_request`.
- Exact agreement between supported copy and final fields, following
  `_validate_source_audit`.
- Code-owned availability of facts and identities, so missing measurements
  cannot become model-selected chart claims.
- Narrow checks for an observed false relationship between posts, following the
  approach of `_unsupported_unverified_post_link`. G2 additionally supplies
  repeated-author groups; different accounts alone do not prove independence.

The final code derives source IDs, collected brand choices and source-speaker
identity from the same support object. Original text, quoted text and parent
context remain separately bound. Grouped and multi-brand stories remain valid.
These checks establish reference ownership. They do not prove that every claim
is entailed by its cited passage.

## Remaining defect and next decision

The factual editor repeatedly generates numeric claims with an empty number
ownership audit. The final code holds those responses. Adding more prose
instructions did not resolve this in the bounded trial.

The next substantive work is a numeric evidence contract that binds each used
figure to its actual owner, meaning and source passage. Existing headline
`_validate_measurements` provides a useful pattern for code-owned chart facts;
source-reported figures require an adaptation, not blind reuse of chart values.
Keep source figures separate from our corpus measurements. Preserve the frozen
acceptance set and rerun the captured failures before any new model request.

A further paid iteration needs a new bounded allowance because the three-trial
limit is exhausted. The final source-ID derivation and latest writer instructions
have offline verification but have not completed a live editor/writer chain.
Do not deploy or activate this as quality-qualified.

## Saved iteration-2 output

**Chatter:** Ready, Set ... Wait: Post Says PewDiePie’s Ajax Isn’t Downloadable Yet

Supporting line: A post reports that PewDiePie announced a Qwen-based agent for
his Odysseus workspace, but its page says it will be available “when it’s ready.”

This keeps the story attributed to @codenameposhan and does not invent availability.
The article keeps the OpenAI ban claim attributed to that post. Source:
`2106428676351090913`. Staging edition: `bb1a73d2-0234-4c5c-ab0f-0c9d1ce86c4f`.

**Pulse:** Apex-flash-1 open-weights cybersecurity model released, post-trained on GLM-5.3-flash

Its byline was “Post by hrkrshnn and quoted announcement from cantinasecurity,”
which identifies the speakers but fails the intended supporting-line format.
The article distinguishes the original post from the quoted release and keeps
bounty/ranking claims attributed. Its numeric audit still needs repair. Source:
`2106545457027793177`. Staging edition: `c9135402-92d3-4fed-a0d3-3564f3857d6a`.

Neither edition was publicly activated or accepted by the owner.

## Verification, budget and artifacts

- Final G2 suite: **82 passed**, including **24 PostgreSQL tests**, zero skipped.
  Existing headline/DeepInfra verification adds 49 unchanged-scope tests from the
  earlier 119-test run: **131 distinct tests** across the work. Scoped Ruff and
  whitespace checks passed. `jsonschema` was added only to development dependencies
  to test the actual generated alternatives; `uv.lock` is updated.
- Final offline editor request: 105 sources, 201,437 bytes against 225,000;
  schema 63,794 bytes against 75,000. Full wire SHA-256:
  `198070daff7895937009badedf897fdb428f53a3b65a6e9fd23feb76f759e259`.
  No sources were dropped and the factual output allowance remains 65,536 tokens.
- Staging-day reservation: **$0.999359 / six calls**, including the pre-existing
  **$0.144390 / one call**. This loop added **$0.854969 / five calls**. Reservations
  are conservative ceilings, not actual charges. Four DeepInfra calls reported
  $0.01409715 in estimated cost; Sol CLI did not report a charge. No media calls.
- The final held response retains its reservation and is not retried. Global
  generation/public flags remain false. No deployment, collection or video job.
- [Machine-readable results and code/request identities](2026-10-07-122329-g2-source-contract-iterations.json).
  Local full requests/original HTTP responses: `.local/g2-source-contract-live-20261007-iteration-{1,2,3}/`.
  Final offline receipt: `.local/g2-source-contract-final-20261007/`.
- Code work remains uncommitted on `feat/g2-editorial` at base `bacbb433`; the live
  bundles used integration `f9276520` plus the exact local file hashes recorded
  in each preflight. The final offline changes are later than iteration 3.

Final G2 command:

```sh
DATABASE_URL=postgresql://localhost/g2_final_contract_20261007 \
STAFF_COLLECTION_NETWORK_ENABLED=false .venv-g2/bin/pytest \
  tests/test_editorial_source_contract.py tests/test_editorial_selection.py \
  tests/test_editorial_writing.py tests/test_editorial_provider_profiles.py \
  tests/test_editorial_end_to_end.py tests/test_editorial_persistence.py \
  tests/test_editorial_orchestration.py tests/test_editorial_config.py \
  --basetemp=/Users/fuchitalee/.cache/g2-final-contract-tests -q
```
