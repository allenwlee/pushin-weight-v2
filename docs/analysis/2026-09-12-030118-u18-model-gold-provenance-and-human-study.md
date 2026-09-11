# U18 model-gold provenance and human study checkpoint

## Decision

Run the candidate-blind human ambiguity study before any additional classifier
provider call. The current reference labels were created entirely by models,
so v18 through v26 measure development agreement with that reference rather
than accuracy against human judgment.

The classifier remains blocked from taxonomy-v3 staging activation and
production promotion. The 500-row development run and unopened release cohort
remain closed.

## Reference provenance

| Artifact | SHA-256 | Annotators | Adjudicator |
| --- | --- | --- | --- |
| `gold-v3-audited.json` | `d16034a58163b7f3121fc56950aa0932a5f611a7c42dff18a6397f8fc21e5a70` | Two DeepSeek Flash contract-review passes | DeepSeek Pro contract audit |
| `gold-v3-v18-three-pass-probe.json` | `1fb32d1b648b7bf393e3c88ba0feb29decca6084b33b30b043d13bc4ba333fd6` | Same model reviews, carried forward | Same model audit, carried forward |
| `gold-v3-v25-coupled-outcome-replay.json` | `ac6690ad5455db6ea607b4339ded63f2eb8885d57323aaf17864950c682e1a6f` | Same model reviews, carried forward | Same model audit, carried forward |

All three artifacts correctly record candidate blindness, but no human
annotator participated. Candidate blindness prevents direct copying from the
candidate; it does not turn a model judgment into human ground truth.

## Frozen human diagnostic

The provider-free builder selected 45 cases from the consumed 120-row
development cohort. Each of EN, JA, and ZH-CN contains five stable
model-versus-reference disagreements, five model-run conflicts, and five
model/reference agreement controls. The protocol and decision rule are in
`docs/reference/2026-09-12-030118-u18-human-ambiguity-study.md`.

- Source cohort SHA-256:
  `30ef30d3236984f6e6c00c8a427dcf4eeb25d32b1b7fdef4bf1f2c015fd0a12f`.
- Model-reference SHA-256:
  `ac6690ad5455db6ea607b4339ded63f2eb8885d57323aaf17864950c682e1a6f`.
- Preserved candidate SHA-256 values:
  `e4a2494f4d41d1397fe85185670480688e12da6ef5533e8ccba4d7f67a802406`,
  `62c91b885bbcc76089f045074f8d1c0fa4fec7e333c97649bab995b758db70b4`,
  `92543813bb74f94f3ea559456a51f1ed3d5aebf6a45e6dd89d6e1581ff1eb3bc`,
  and `b06088b52bef44d9f8ac1bd836c305ad8770ef5f3ba4dc20e29b80b4e109ef2e`.
- Private selection-manifest SHA-256:
  `50f46d0d8583f91c316583704efe314ddf98c6306032d9dfd3e0543da1497c91`.
- Private reviewer-A packet SHA-256:
  `f69557a8467579d49d601a37b8204768c597a635466a9b42dde788945bbded35`.
- Private reviewer-B packet SHA-256:
  `4ce7330d5976a0b968b6db7fb2271a441e540a59e0b3332cd749acc58a20ec1f`.
- Private human-attestation template SHA-256:
  `908f8ac03bb80995ff2504dea4e338e94d084f0df2ff2180a6730992d0d6046f`.

The ignored packets are under
`.context/u18/human-ambiguity-study-v1/`. The two reviewer CSV files have
different deterministic row orders. Neither contains source IDs, selection
groups, source hints, source roles, old labels, candidate outputs, model names,
or discovery hints.

Finalization also requires a completed per-language attestation of reviewer
proficiency, independent work, absence of model assistance, and distinct
reviewer/adjudicator identities. CSV validation rejects unknown columns so a
packet augmented with candidate or prior-label fields cannot pass unnoticed.
All four preserved candidate key sets must exactly match the fixed 120-row
model reference before selection.

## Gate and next action

Two independent qualified humans per source language complete the full v3
answer contract. A distinct human adjudicates disagreements without model
answers. Pre-adjudication exact `outcome` plus post-type-set agreement must be
at least 80% overall and 70% per language, with no unresolved taxonomy issue
code appearing in three or more cases.

The builder, validator, disagreement packet, and finalizer are provider-free.
The checkpoint used zero provider calls, tokens, and dollars. A passing result
authorizes only a separately budgeted 30-row DeepSeek Pro reviewer pilot against
the human reference. A failing result returns the work to taxonomy wording and
examples before any further provider spend.
