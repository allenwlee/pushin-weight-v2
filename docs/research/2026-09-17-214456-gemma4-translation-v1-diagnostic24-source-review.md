# Gemma 4 31B translation v1: diagnostic-24 source review

The frozen v1 diagnostic delivered all 24 posts and 72 locale outputs. This review reads each target only against its supplied source and stored context; it does not use any reference translation.

The review records 7 locale errors across 4 source posts: 5 semantic/source-fidelity errors and 2 coverage errors. The coverage errors are the untouched Hausa paragraph in the Chinese and Japanese outputs. The semantic failures are an untranslated English closing claim in Chinese, literal handling of a French colloquial phrase in all three targets, and English terms left inside a Chinese central comparison. There are no unknown locale results in this pass.

The exact evidence, including source and output spans, is in `.context/model-task-20260917/gemma4-translation-v1-diagnostic24-20260917-212808/source-grounded-review-v1.json`. It counts 24 reviewed source posts, 72 reviewed locale outputs, 65 reviewed-good locale outputs, 3 semantic-error sources, 1 coverage-error source, and 4 union-error sources.

This does not establish incumbent parity. The failures are consistent with trying the already-frozen source-bound v2 prompt while retaining the raw-text format and reasoning-disabled request.

## Reconciliation

The original own-review ledger remains unchanged. A separate reconciled ledger narrows the fourth source's evidence to source `divide` and output `Divide`. It counts that single untranslated ordinary noun as a minor Chinese coverage error; `vs` alone is common shorthand and is not separately counted. The reconciled ledger therefore still has four union-error sources, with two semantic and two coverage sources. This is not a claim of a semantic inversion.

## Provenance amendment

The original review and packets use `source_rows_sha256` for the inherited parent-source file hash `862076a5…`, which is a misleading field name. The additive amendment keeps those artifacts unchanged and records the diagnostic-24 file hash `6dd0f4b7…` and the normalized selected-row hash `74219a66…`, which matches the frozen contract and executed rows.
