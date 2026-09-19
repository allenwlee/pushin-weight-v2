# Translation invariant fixes and full-cohort retest

Date: September 16, 2026 JST. Canonical plan: [AI enrichment](../plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md), U20. [Machine-readable evidence](2026-09-16-213715-u20-translation-invariant-retest.json).

## Result

The known token-magnitude, unchanged-source-language and extra paragraph-spacing failures now have deterministic protection. After a parser-only replay, all 45 posts have all required locales, all 45 native copies remain exact, and every source URL occurrence survives. The complete translation quality gate still **does not pass**: source-visible review confirms meaning-level defects in pronunciation examples and a model-versus-character relationship. No translator activation, provider setting, staging deploy or production change occurred.

## What changed

- Supported token quantities are extracted and normalized with Decimal arithmetic. Each occurrence is replaced by a collision-free placeholder, then restored to its exact target-language value. For example, 10.9 trillion becomes 10.9兆トークン or 10.9万亿个Token. The separate “next trillion” stays 1兆; surrounding qualifiers remain available to translation. Missing/duplicated placeholders and contradictory additional recognized values fail the locale. This is a deliberately narrow token-unit guard, not universal numeric or currency verification.
- Prompts distinguish explanatory prose from pronunciation examples. Code rejects substantial unchanged source copies across incompatible scripts. Short examples, names, code and same-script cases are not treated as proof of a wrong language. Partial untranslated prose can still escape this narrow detector.
- Paragraph parsing removes added blank framing lines while retaining content indentation, internal newlines and source separators. All numbered paragraphs remain mandatory and ordered. A missing terminal marker or the observed final `::END` variant is normalized in code after the provider has returned a complete response. Missing, duplicated or reordered paragraphs, unknown markers and terminal garbage still fail.
- The runtime call structure stays one post per target locale, with exact source-language copying, no automatic retry, no repair call and no routine model reviewer. Paragraph mode remains opt-in. Prompt identities are raw v6 and paragraph v7; the final framing adjustment changes only parsing, not the frozen prompts.

## Measured experiments

All paid runs below used the pinned cloud 0731 route, serial requests, a 180-second socket-idle limit and no retries. No database was queried or changed by these inference runs.

| Experiment | Calls | Complete posts | Wall time | Reported inference cost |
|---|---:|---:|---:|---:|
| Instructions + numeric validator, four-post probe | 8 | 3/4 | 2m06s | $0.00175404 |
| Protected quantities, same four-post probe | 8 | 4/4 | 2m24s | $0.00174786 |
| Protected quantities, full 45, strict parser as executed | 90 | 40/45 | 14m18s | $0.00960924 |
| Same saved 90 responses, final framing parser | **0 new calls** | **45/45** | Local replay only | **$0 additional** |

The first probe still produced 109兆 instead of 10.9兆; its validator rejected that locale. The second probe restored the correct quantity at every occurrence and retained the previously omitted bilingual sections and all five URL occurrences. Its four source/output line counts matched (47, 35, 87, 36).

The full run used 57,494 input and 35,500 output tokens and had zero provider/transport errors. Five locales were initially rejected only for missing or malformed ending markers. The subsequent replay asserted that all 90 requests were unchanged and every already-accepted string stayed byte-identical. Both the original result and the normalized result are retained separately; the paid run has not been relabelled as an original 45/45 pass.

Compared with the earlier 45-post plain-text run ($0.00723006; 12m40s), protection increased observed cost approximately **33%** and serial elapsed time **13%**. It uses no additional calls but adds instructions and markers. This balanced diagnostic sample is not a monthly production forecast, a tenfold cost reduction, or a concurrency/throughput proof. Costs exclude review-agent work and wallet fees. All three new paid runs together cost $0.01311114.

## Mechanical and semantic evidence

After replay, 90/90 non-native outputs are available and every source URL occurrence matches. The earlier 130-line bilingual English output is now 87 lines, matching its source. Two other English outputs merge one internal source newline each (posts 2066503919505977649 and 2093747347859865794); paragraph completeness is not exact line-count parity.

Four fresh automated reviewers assessed 90 source/output pairs with model identity withheld. Three initially unavailable pairs were reviewed again after code-only recovery, with separate original and follow-up judgments. Native copies were excluded from semantic rates.

| Target locale | Fidelity screening passes | Readability passes | Critical inversions flagged |
|---|---:|---:|---:|
| English | 26/30 | 30/30 | 0 |
| Simplified Chinese | 27/30 | 29/30 | 0 |
| Japanese | 27/30 | 30/30 | 0 |

These are automated screening judgments, not human gold, population accuracy or a clean quality pass. Parent inspection independently confirms:

- Post 2093192147700977838 now has English prose, but its pronunciation guide loses spelling-versus-reading distinctions. In Chinese, examples such as Copilot and Cursor become their word meanings rather than pronunciations.
- Post 2093747347859865794 describes using MiniMax H3 with characters other than Phoebe and Carlotta. Its English output instead says “characters other than MiniMax H3, Phoebe, and Carlotta,” incorrectly placing the model in the character list.

Other reviewer flags need caution. A later “died” clause becomes “failed/derailed,” but the earlier killing assertion survives. “6分钱” becomes “6 cents” without identifying yuan, which is ambiguous but does not explicitly assert USD. Two source name spellings become one romanization, which alone does not prove a different identity. The original review flags remain visible rather than being silently upgraded into confirmed errors.

The existing 100% entity/number/URL/polarity preservation contract is not met, and English fidelity screening is below the 90% floor. U20 remains open. No new human review is required by this work. The next quality work concerns pronunciation examples, entity roles, idioms and currency clarity; the current numerical guard must not be described as solving those semantic problems.

## Verification and saved evidence

82 focused tests passed, including 16 required PostgreSQL checks and no skips. Regression tests exercise the real CycleRunner-to-artifact path: invalid output cannot publish and failed token usage is retained. New tests first reproduced the original defects and terminal rejections before the fixes. Ruff, diff checks and independent code review passed. The browser packet passed the prescribed builder/validator and real Chromium checks: 45 tabs, one visible post, three locale outputs, independent scrolling, no horizontal overflow and no browser errors.

Implementation checkpoint: `28ac3f0`; final framing/retest evidence is saved in the following checkpoint. The unrelated fixture edit is preserved outside this work.

- First probe: `.context/u20/invariant-probe-20260916-211100/`.
- Protected probe: `.context/u20/quantity-probe-20260916-212100/`.
- Full run: `.context/u20/quantity-full45-20260916-212100/`.
- Original paid output: `arms/0731/result.json`; separate replay: `normalized-result.json`.
- Reproducible offline replay: `replay_normalization.py`; checks: `normalized-mechanical-audit.json`.
- Blind packets, original judgments and recovered-case review: `blind-review/`; summary: `blinded-review-summary.json`.
- The prepared v5 full45 directory `invariant-full45-20260916-211500` was **not executed**.
- [Browser review](http://100.102.74.50:18766/plaintext-translation-review.html) is served from fuchitalee and opened in Chrome on Allen’s MacBook. Original left; EN/ZH/JA translations and explicitly unchanged prior commentary right. No artifact was copied onto the MacBook.
