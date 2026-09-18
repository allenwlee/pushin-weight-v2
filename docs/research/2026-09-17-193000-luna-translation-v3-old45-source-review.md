# Luna Translation v3 — old45 source-grounded review

**Reviewed:** 2026-09-17  
**Candidate:** `luna_translation_v3`  
**Scope:** 45 posts: 15 English, 15 Simplified Chinese, and 15 Japanese. Every `text_en`, `text_zh_cn`, and `text_ja` value was read against the supplied post and its supplied context.

The complete machine-readable review is [`source-grounded-review-v1.json`](../../.context/model-task-20260917/luna-translation-v3-r113-old45-20260917-184300/source-grounded-review-v1.json). It ties this review to packet SHA-256 `f07835074044c80583cc50331cd770f0af502fdf33f1cd805b4374b503dde352` and incumbent-report SHA-256 `963d7c41869e41294ee72353cc02bae434fed2edc9da975b0b600343874a4df4`.

The candidate has **one confirmed minor source error on one post**. For Japanese post `2089638284536496616`, the Chinese target renders `・・・（白目）` as `……（瞪大眼）`. The source conveys blank/rolled-back eyes after the surprising result; the output changes it to wide-eyed surprise. The English translation for that reaction is sound, and the Japanese field is the required exact native copy. The remaining 44 posts had no confirmed semantic, role/direction, uncertainty, numeric, locale, or coverage error in any target field. This count is semantic; it does not treat clean response structure as proof of translation quality.

The old incumbent report cannot be used as a fully comparable reference for ten Japanese-source posts: `2072636451452530811, 2081316109522014283, 2083451919134343546, 2084489786157621733, 2085572616203698466, 2089638284536496616, 2093192147700977838, 2093541597870956922, 2093747347859865794, 2094817863098126837`. In each, its `text_zh_cn` value is byte-for-byte the Japanese source while `text_ja` is also native. Luna instead keeps only `text_ja` native and supplies a Chinese translation. This is a reference-artifact mismatch, not a candidate failure and not a reason to score wording similarity. All other candidate/incumbent differences were evaluated against the source rather than treated as errors merely because the strings differ.

This review does not establish qualification, parity, or a production decision. It records the source evidence for the old45 cohort only.
