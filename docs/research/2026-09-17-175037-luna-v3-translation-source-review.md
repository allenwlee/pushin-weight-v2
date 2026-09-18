# Luna v3 translation source review

Reviewed 2026-09-17 17:50 JST against the supplied Smoke8 source records only. All 19 generated targets were structurally delivered, and five native copies were exact controls.

Three sources have confirmed material translation errors: English renders approving French `poulet` slang as literal `chicken`; Chinese changes opaque `ox Alpha` to `牛 Alpha`; and the Korean headline reverses its China/Trump directions in English and Japanese. The Chinese tokenizer attachment remains unresolved; Japanese correctly phrases it as a guess based on the tokenizer. Counts: 18 good, 4 material-error outputs, 1 unknown output; 3 confirmed failing sources and a conservative 3–4 source interval.

Machine-readable record: `.context/model-task-20260917/review-luna-v3-translation.json`.
