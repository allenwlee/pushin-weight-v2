---
title: Hy-MT2 translation trial rationale and 1.8B third-attempt assessment
date: 2026-09-17
type: research
---

# Hy-MT2 translation trial rationale and 1.8B third-attempt assessment

Hy-MT2 is evaluated only as a translation candidate. The route and prices are
fixed by `docs/research/2026-09-17-062006-model-specialist-endpoints/manifest.json`
(SHA-256 `46e265fd438f4f85d0766103987d8b10f310d4966f49dd04b3c8716d0e6b4c38`),
not by current catalog prices or official documentation. The selected route is
Tencent FP8 with `tencent/hy-mt2-1.8b-20260521` or
`tencent/hy-mt2-7b-20260521`; the snapshot permits only temperature, stop,
and the two completion-limit names.

Tencent's official model cards document a single user-message translation
template, full language names, a terminology form, delimiter preservation, a
4,096-token generation allowance, and temperature 0.7 as a recommendation.
The third 1.8B profile changes two relevant variables together: it returns to
that native one-user-message form and adds a deterministic glossary of only
source-visible names or version strings, while setting the route-supported
temperature to 0. This is a separately measured deterministic setting, not a
claim that Tencent recommends zero. It does not add an answer for any reviewed
post or infer a name's identity. It keeps the production caller's paragraph
protocol and protected-span checks unchanged.

## Hy-MT2-1.8B third attempt

The retained contract is
`.context/model-task-20260917/hy18-translation-v3-native-sourceonly-smoke8/contract.json`.
It froze 19 source/target requests from `smoke8.json`, reserved $0.006511614
from the saved $0.044/$0.177 per-million-token price, pinned
`tencent/fp8`, disabled fallback, and capped in-flight work at three.

All 19 requests were consumed once. Eighteen completed with `finish_reason`
`stop`; one English request for source `2100277491390951481` received HTTP
429 and is a transport and coverage failure because retries are prohibited.
The observed cost for received requests was $0.000659234. No database writes,
fallbacks, or retries occurred.

The source-only comparison uses the same eight posts as the incumbent. The
interim packet `.context/model-task-20260917/incumbent4.1-parent-smoke8-review.json`
is useful evidence but is not the final benchmark score; the S3 incumbent
review controls that decision. This assessment does not use matching output
strings as a standard. Hy18 repeats failures involving the one-tenth-price
claim, the French `poulet` praise and unspecified cents, the GLM-4
hypothetical, and the Indonesian Codex post. It also changes opaque `ox Alpha`
to “strong Alpha” and misattributes or reverses the Trump-China headline.
The tokenizer sentence remains source-ambiguous. These added source failures
mean Hy18 loses to the incumbent irrespective of whether an interim minor
finding is ultimately counted as an error or unresolved. Hy18 has exhausted
its three authorized configurations.

## 7B next trial

Hy-MT2-7B receives the same documented native interface in a separately
frozen profile (`hy7_translation_v2`), rather than spending a call on the
known-poor 1.8B v1-shaped trial. Its result must be reviewed source-first
against the incumbent on the same sources. It gets at most three distinct
profiles, each subject to the shared $3 model/task, $30 portfolio, no-retry,
no-fallback, and three-in-flight limits.

The retained 7B v2 result completed all 19 calls without a transport or
structural failure, for an observed cost of $0.001313511 (reservation
$0.010864614). It still repeats the price-fraction, French-praise/unspecified
cents, and Codex-use failures. It additionally reinterprets `ox Alpha` as a
bull or drops it, and the English and Simplified Chinese headline outputs
reverse the Trump-China relation. The Japanese GLM-4 output is complete and
retains a conditional reading; the tokenizer sentence remains unresolved.
This profile does not establish incumbent parity. Any final count remains
subject to the S3 incumbent review.

The second paid 7B configuration (`hy7_translation_v3`) added the compact
source-fidelity ledger and used Tencent's documented temperature 0.7. All 19
requests reached `stop`, with observed cost $0.001381363 (reservation
$0.011220332), but the Chinese long-post response changed the terminal
delimiter from `[[PW0:END]]` to `[[PW:END]]`. The existing parser rejected the
row, preserving the coverage failure. The semantic failures above persisted:
the price fraction, French praise and unspecified currency, Codex action,
opaque `ox Alpha`, and English headline relation remain wrong. The completed
S3 incumbent review records four erroneous smoke8 sources and one unresolved
source. Hy7 is worse on the same cohort. A third 7B configuration is not
currently justified: changing to per-paragraph transport would target the
delimiter failure while leaving the repeated semantic failures unaddressed.

## Exact source-only findings

These are source-first findings, not reference-answer matching. `v2` and `v3`
refer to the two paid 7B configurations. The following output spans are enough
to identify the defect in the retained reports without copying whole posts.

| Source | Source span | v2 / v3 output span | Finding |
| --- | --- | --- | --- |
| `2100249221484220856` | `给它打了个一折` | EN v2/v3: `offers a 10% discount`; JA v2/v3: `価格が1割引き` | The source says one tenth of the original price, consistent with its later 90% reduction. Both outputs instead say 10% off. |
| `2100262531788832809` | `30 cts … c'est quoi ce poulet` | EN v2/v3: `What kind of joke is this?`; ZH v2: `30美分`; ZH v3: `30美分`; JA v2: `何これ馬鹿げてる`; JA v3: `deepseekって一体何なんだ` | The surrounding low-price reaction is admiring slang, not ridicule or a neutral identity question. `cts` leaves the currency unspecified; `美分` asserts U.S. cents. |
| `2100277491390951481` | `gua udah make codex since gpt 5.5 release` | EN v2/v3: `I’ve been making codex`; ZH v2: `一直在使用Codex`; ZH v3: `一直在制作代码集`; JA v2/v3: `Codexを作ってきた` | The first-person speaker has used the opaque product Codex since the release; the English/Japanese turn that into making a codex, and v3 Chinese does so as well. |
| `2100314574721315014` | `Union Alpha wishes to be ox Alpha` | ZH v2: `Alpha的公牛`; ZH v3: `想变成 Alpha`; JA v2/v3: `Alphaになりたい` | `ox Alpha` is an opaque source-visible model name in this comparison. The outputs reinterpret or delete `ox`. |
| `2100430324899455118` | `“중국 앞서야” 트럼프 AI 속도조절론 일축` | EN v2: `Trump rejects “China must lead”`; EN v3: `Trump rejects Trump’s “China must lead”`; ZH v2/v3: `中国必须领先` | The headline says Trump rejects calls to slow AI while saying the United States must get ahead of China. These outputs make China the party that must lead and misstate the relation. |
| `2100430324899455118` | terminal `[[PW0:END]]` | ZH v3 raw response: `[[PW:END]]`; parsed output: `text_zh_cn: null` | The marker lost its namespace/sequence. The caller's existing parser correctly fails closed, so this is a coverage failure as well as a malformed delimiter response. |

`2100346971144036571` remains unresolved because the attachment of `based on
tokenizer` is source-ambiguous. The v3 Japanese long-post headline uses
`中国に先んじるべき`, which preserves getting ahead of China and is not counted
as an additional Japanese error.

## Terminal decision

Hy-MT2-1.8B has used three paid configurations. Hy-MT2-7B has used **two**:
`hy7_translation_v2` and `hy7_translation_v3`; its unrun v1-shaped profile is
not counted, and one configuration remains available. The remaining option is
intentionally unused. The evidence does not identify a source-general
correction likely to remove the repeated semantic errors. Per-paragraph caller
transport might prevent the v3 delimiter failure, but it does not correct the
price direction, idiom tone, opaque-name preservation, or role relation.
Spending the last configuration only to reach a numeric budget would not be a
useful trial. This conclusion is limited to these frozen routes and source
cohort; it does not claim that Hy-MT2 cannot translate other material.
