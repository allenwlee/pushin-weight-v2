# Translation attempt Q: source-only automated wider diagnostic

**Packet:** `.context/model-task-20260917/review-packet-q.json`  
**Rubric:** `.context/model-task-20260917/review-rubric.md`  
**Scope:** 12 supplied source posts × English, Simplified Chinese, and Japanese targets (36 outputs).  
**Evidence:** root-post source text only; supplied parent or quote context was not used.

## Result

Twenty-nine outputs are reviewed good, seven have confirmed defects, and none are unresolved. Five source posts contain at least one confirmed defect.

This remains an automated wider diagnostic under owner exception 29, which permits running it despite the earlier eight-post hard failures. It is not new human gold and cannot establish population accuracy. It also fails the rubric's zero-error diagnostic threshold.

## Confirmed failures

- The Japanese translation of `2100277491390951481` turns a personal money-saving assessment into a conditional product-performance claim and a recommendation to subscribe.
- The Chinese translation of `2100283207736332475` leaves its complete Hausa second paragraph untranslated. The target keeps the paragraph break, but it must translate both paragraphs.
- Japanese expands opaque `ox Alpha` into “Oxford's Alpha,” and turns opaque `fusion with fable 5.1` into literal technical fusion.
- The English, Chinese, and Japanese translations of Korean post `2100430324899455118` all distort Trump's “must get ahead of China” framing. Chinese also strengthens a relative comparison with nationality into nationality no longer being decisive.

## Formatting distinction

Removing leading spaces from model-list lines in the Freebuff post is a harmless spacing change, not an error: every list item and paragraph boundary remains present. Paragraph-boundary preservation is still required; the untranslated Hausa paragraph is a semantic coverage failure, not a spacing issue.

The exact per-output record is `.context/model-task-20260917/review-q.json`.
