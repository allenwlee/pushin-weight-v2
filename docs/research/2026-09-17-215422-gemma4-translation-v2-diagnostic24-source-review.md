# Gemma 4 31B translation v2: diagnostic-24 source review

The frozen source-bound v2 diagnostic was reviewed against its supplied source and stored context only. It delivers 55 provider responses but has four structurally failed source rows and is not a usable improvement over v1.

All 72 locale outcomes are classified in the review ledger. There are 18 locale errors across 10 source posts: 11 added-content errors from the synthetic `[[PQ...]]` placeholder, and 7 coverage errors. The coverage set includes five null target cells plus the bilingual Hausa post: its Chinese target repeats the English paragraph and its Japanese target leaves Hausa unchanged. No locale result is unknown.

The exact source/output spans and the complete 24-by-3 ledger are in `.context/model-task-20260917/gemma4-translation-v2-sourcebound-diagnostic24-20260917-225000/source-grounded-review-v1.json`. The `[[PQ...]]` token is absent from every matching source; it must be treated as delivered added text even though the harness did not classify it as a structural error.

V2 should not be used for wider testing. The source-bound prompt corrects several v1 semantic cases, but it introduces an unacceptable marker/coverage regression. Any v3 proposal needs evidence for a narrowly scoped marker-handling correction and a frozen validation before another paid call.

## Provenance amendment

The original review and packets use `source_rows_sha256` for the inherited parent-source file hash `862076a5…`, which is a misleading field name. The additive amendment keeps those artifacts unchanged and records the diagnostic-24 file hash `6dd0f4b7…` and the normalized selected-row hash `74219a66…`, which matches the frozen contract and executed rows.
