# Luna v2 source review

Reviewed 2026-09-17 17:49 JST using the supplied Smoke8 sources and stored context. The review did not compare any incumbent outputs.

Translation has four confirmed failing sources and one unresolved source. The French reaction's approving `poulet` slang becomes negative or literal in all three locales; the long Chinese discount post loses its English target because raw output ends in `[[PW:END]]`, not the required `[[PW0:END]]`; Japanese splits the OpenCode Go subscription; and the Korean headline reverses its actor/direction in English and Japanese. Chinese and Japanese tokenizer attachments remain unknown. This yields a conservative source interval of 4–5.

Commentary has two confirmed minor-error sources: Chinese turns `30 cts` into USD cents, and Japanese leaves ordinary `excited` untranslated. Its source interval is 2–2.

The machine-readable records are `.context/model-task-20260917/review-luna-v2-translation.json` and `.context/model-task-20260917/review-luna-v2-commentary.json`.
