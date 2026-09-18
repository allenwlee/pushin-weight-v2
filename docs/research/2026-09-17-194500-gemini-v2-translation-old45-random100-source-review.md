---
title: Gemini translation v2 R113 old45 and random100 source review
date: 2026-09-17
status: candidate-review-amended
---

# Gemini translation v2: old45 and random100

Candidate-only, source-first diagnostic review. Every non-null locale output was reviewed; a wrapper `translation_failed` is not treated as three missing locales.

The first random100 JSON remains preserved as a rejected, incomplete pass. It missed direct source/output defects because it treated nearly every delivered field as good. The replacement review re-read all 100 sources and all 297 delivered fields.

| Cohort | Good fields | Material fields | Unknown fields | Missing fields | Source defects |
| --- | ---: | ---: | ---: | ---: | --- |
| old45 | 126 | 2 | 1 | 6 | 2 semantic + 6 coverage; the uncertain Chinese field shares a source with a confirmed Japanese error and is not an additional unknown source |
| random100 | 279 | 11 | 2 | 3 | 10 semantic + 3 coverage; 2 separate unresolved sources |

Old45 material findings: `2079575705646465078` Japanese reverses China from eater to being eaten; `2091583113914618174` Chinese renders Nvidia’s $6B investment/check and hiring as an acquisition.

The completed random100 review confirms 10 semantic-error sources: company/model-name substitutions, untranslated English and Hausa paragraphs, an explicit unsupported pronoun resolution, an unsupported attack claim, price-praise turned negative, and a Korean headline direction reversal in all three locales. The three null fields remain separate delivery defects. `2100339322025070971` Japanese drops the likely “.2” from stylized “5.2morrow”; it remains unresolved. So does the English “too slow” for Chinese “太笨”: English *slow* can mean slow-witted and the surrounding sentence can support that reading, so it is not counted as a confirmed latency claim.

### Random100 retained-incumbent pairing

Each candidate finding and null field was paired to the identical post/locale in the retained DeepSeek 4.1 result. The table is evidence of the paired raw output, not an assumption that the incumbent is correct.

| Candidate source / locale | Candidate finding | Retained incumbent result | Paired reading |
| --- | --- | --- | --- |
| `2100076637668913350` JA | `生数科技` → “Seesaw AI” | Retains `生数科技` | Candidate-only name substitution |
| `2100243502130971051` JA | “keeps junk off disk” → physical sticking | `ディスクに残さない` | Candidate-only minor distortion |
| `2100262531788832809` EN/ZH/JA | price praise becomes negative | literal “chicken” / invented `3毛钱` / literal chicken | Shared source failure, different forms |
| `2100264232721731936` ZH | `minimax` → `极小极大` | retains `minimax` | Candidate-only name substitution |
| `2100271964736696742` JA | adds `(AIは)` as referent | retains `それ` | Candidate-only unsupported resolution |
| `2100283207736332475` ZH/JA | English/Hausa paragraphs left untranslated | translated but omits “law-abiding” in ZH and treats `Yara` as a name in JA | Both have source defects |
| `2100314574721315014` ZH | `ox Alpha` → `牛阿尔法` | retains `ox Alpha` | Candidate-only name substitution |
| `2100339358398058923` ZH/JA | `got hit` → attacked | retained outputs also say attacked; JA is Chinese prose | Both have source defects |
| `2100404047882727911` ZH | `Deepseek` → `深寻` | retains `Deepseek` | Candidate-only name substitution |
| `2100430324899455118` EN/ZH/JA | makes China the party that must lead | “stay ahead of China” / equivalents | Candidate-only direction reversal |
| `2100158202914406749` JA; `2100343637012091332` JA; `2100404178355167577` EN | null candidate fields | all three values delivered | Candidate-only coverage losses |

The current candidate review is 10 confirmed semantic sources, 3 coverage sources, and 2 unresolved sources, versus the incumbent review's reported 9 confirmed semantic sources, no coverage source, and 1 unresolved source. These are current review counts, not a qualification result; the R113 decision requires an independent review and source-count bounds.

The provided incumbent random100 review reports 9 confirmed semantic errors, 1 unknown, and full coverage. Its comparison must remain separate from the pending independently reviewed old45 incumbent result; this report makes no qualification claim.

- [old45 JSON](../../.context/model-task-20260917/review-gemini-translation-v2-r113-old45.json)
- [rejected random100 v1 JSON](../../.context/model-task-20260917/review-gemini-translation-v2-r113-random100.json)
- [random100 v2 JSON](../../.context/model-task-20260917/review-gemini-translation-v2-r113-random100-v2.json)
- [random100 paired raw-output audit](../../.context/model-task-20260917/review-gemini-translation-v2-r113-random100-paired-incumbent.json)
