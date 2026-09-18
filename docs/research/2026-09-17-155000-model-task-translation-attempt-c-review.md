# Translation attempt C: independent review

Reviewed the eight supplied source posts and all 24 required locale outputs against `review-rubric.md`, including exact native-language copies where supplied.

Six source posts have confirmed defects. The 13 findings comprise 11 material and 2 minor issues: three missing required outputs, incorrect one-tenth/discount amounts, dropped conditional speculation, mistranslated Indonesian-English meaning, a broken Japanese idiom, improper handling of the OpenRouter proper name, and a top-tier-to-ordinary-class Japanese reversal. Eleven outputs were reviewed as good.

| Locale | Outputs with findings | Required outputs |
| --- | ---: | ---: |
| English | 4 | 8 |
| Simplified Chinese | 3 | 8 |
| Japanese | 6 | 8 |

This diagnostic does not qualify: it has 6 erroneous source posts out of 8, while an eight-post diagnostic needs zero.

The durable changes indicated by these results are small and general. The translation instruction should explicitly preserve numerical relationships and units, proper names, links, speaker actions, and conditional or speculative language, while requiring complete idiomatic sentences. Source-language targets should be copied byte-for-byte outside the model path, and the interface should validate every requested locale independently so a partial result cannot appear complete.

The structured record, including exact source/output spans and all reviewed-good outputs, is in `.context/model-task-20260917/review-c.json`.
