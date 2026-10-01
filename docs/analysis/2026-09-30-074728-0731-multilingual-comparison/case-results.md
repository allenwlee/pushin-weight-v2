# Paired case results: 0731 and Jev

Frozen single-agent references, not independent human ground truth. Full source text/translation is linked for review. Every 0731 mismatch and every strict model-score difference is retained below; unchanged shared correct fields are omitted.

## ja_01 — deepseek — natural

[Source](https://x.com/3K1/status/2098963821369217086); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Stored quotation explicitly ran DeepSeek; measured throughput; encouragement is product/local feasibility, not nation.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 31 | 34 | 0 |
| translated | 33 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 80.0% | yes |
| raw | geo:reporting | False | True | False | 80.0% | yes |
| raw | product:testimonial | True | True | False | 80.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 90.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 90.0% | yes |
| raw | type:hands_on_usage | True | True | False | 70.0% | yes |
| raw | type:news_reporting | True | False | False | 90.0% | yes |
| raw | type:releases_updates | False | True | False | 90.0% | yes |
| raw | type:research_explanations | False | True | False | 90.0% | yes |
| translated | geo:framework | False | True | False | 95.0% | yes |
| translated | geo:reporting | False | True | False | 95.0% | yes |
| translated | product:testimonial | True | True | False | 95.0% | yes |
| translated | sentiment | positive | positive | neutral | 60.0% | yes |
| translated | topic:cost_performance | True | True | False | 95.0% | yes |
| translated | topic:evals_benchmarks | True | True | False | 95.0% | yes |
| translated | type:hands_on_usage | True | True | False | 95.0% | yes |
| translated | type:news_reporting | True | False | False | 95.0% | yes |
| translated | type:releases_updates | False | True | False | 95.0% | yes |
| translated | type:research_explanations | False | True | True | 90.0% | yes |

## ja_02 — minimax — natural

[Source](https://x.com/aidoga_lab/status/2091712099395461388); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Credits the tool used to generate a movie; not a MiniMax launch or explicit pitch.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 36 | 0 |
| translated | 35 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 90.0% | yes |
| translated | geo:reporting | False | True | False | 90.0% | yes |
| translated | promotion:general | False | True | False | 90.0% | yes |
| translated | type:hands_on_usage | True | True | False | 90.0% | yes |
| translated | type:other | False | False | True | 90.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | neutral | positive | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |

## ja_03 — deepseek — natural

[Source](https://x.com/connect24h/status/2102595739474174316); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Reports malware using several LLMs; do not adopt malware actor's actions as author's firsthand usage or geopolitical claim.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 33 | 0 |
| translated | 35 | 30 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | product:investigate_claim | True | True | False | 100.0% | yes |
| raw | sentiment | neutral | negative | neutral | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |
| translated | geo:framework | False | True | True | 90.0% | yes |
| translated | geo:reporting | False | True | True | 90.0% | yes |
| translated | product:investigate_claim | True | True | False | 100.0% | yes |
| translated | topic:agents_tools | True | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | False | False | True | 90.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |
| translated | type:results_analysis | False | False | True | 90.0% | yes |

## ja_04 — deepseek — natural

[Source](https://x.com/mt_pb_ai/status/2085522812295643197); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Explicitly unconfirmed benchmark/pricing report; ordinary benchmark rumor is not investigate_claim under the current definition.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 31 | 1 |
| translated | 32 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:testimonial | False | True | False | 100.0% | yes |
| translated | sentiment | positive | positive | neutral | 100.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 100.0% | yes |
| translated | type:advertising_marketing | False | True | False | 100.0% | yes |
| translated | type:business_finance | False | True | False | 100.0% | yes |
| translated | type:news_reporting | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:results_analysis | True | False | True | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | False | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | False | True | False | 100.0% | yes |
| raw | type:hands_on_usage | False | False | False | 0.0% | NO |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | False | True | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |

## ja_05 — minimax — natural

[Source](https://x.com/luche_whitewing/status/2089442141751902272); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Poetic creator output with tool credit; no expressed evaluation of MiniMax itself.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:other | False | False | True | 100.0% | yes |

## ja_06 — minimax — natural

[Source](https://x.com/sidodtv/status/2089299406583726236); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Author observes motion blur quality failure; quality dissatisfaction, not necessarily a concrete software malfunction.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:complaint | True | True | False | 100.0% | yes |
| raw | product:ideas_requests | False | True | False | 100.0% | yes |
| raw | sentiment | negative | negative | mixed | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |

## ja_07 — minimax — natural

[Source](https://x.com/kik0ai1jikake/status/2090270568532828380); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Actual comparative generation and costs; praises H3 while still liking the competing model.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | True | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |

## ja_08 — minimax — natural

[Source](https://x.com/javawock7618/status/2090439924332032347); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Updates an H3 workflow with measured directional quality and a described frame-range technique.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 34 | 1 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | sentiment | positive | positive | neutral | 100.0% | yes |
| raw | type:releases_updates | True | True | False | 0.0% | NO |
| raw | type:research_explanations | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |

## ja_09 — minimax — natural

[Source](https://x.com/__su888/status/2087298764583415883); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Third-party implementation results with specific quantization technique; no author's own test asserted.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 31 | 35 | 0 |
| translated | 33 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | geo:reporting | False | True | False | 90.0% | yes |
| raw | sentiment | neutral | positive | neutral | 90.0% | yes |
| raw | topic:evals_benchmarks | True | True | False | 90.0% | yes |
| raw | topic:openness_license | False | True | False | 90.0% | yes |
| raw | type:hands_on_usage | False | True | False | 90.0% | yes |
| raw | type:news_reporting | True | False | False | 90.0% | yes |
| raw | type:releases_updates | False | True | False | 90.0% | yes |
| raw | type:research_explanations | True | True | False | 90.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | positive | positive | 100.0% | yes |
| translated | topic:evals_benchmarks | True | True | False | 100.0% | yes |
| translated | type:hands_on_usage | False | False | True | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| translated | type:research_explanations | True | True | False | 100.0% | yes |

## ja_10 — minimax — natural

[Source](https://x.com/To_Vten_ozi/status/2087557406473744443); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Recommends small generation then upscaling from experience; not a service sales pitch.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 30 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | outcome | classified | classified | context_missing | 100.0% | yes |
| raw | product:ideas_requests | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | False | False | 100.0% | yes |
| raw | sentiment | positive | mixed | unknown | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |

## ja_11 — deepseek — natural

[Source](https://x.com/amano76_SEO/status/2097846114489962944); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: DeepSeek-specific part is a sourced government allegation and denial; unrelated OpenAI/Meta launches must not transfer.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 32 | 0 |
| translated | 33 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | True | 90.0% | yes |
| raw | geo:nationalism | False | False | True | 90.0% | yes |
| raw | sentiment | neutral | negative | neutral | 70.0% | yes |
| raw | topic:agents_tools | False | False | True | 80.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 90.0% | yes |
| raw | type:opinions_reactions | False | True | True | 80.0% | yes |
| raw | type:research_explanations | True | False | False | 90.0% | yes |
| translated | geo:framework | False | True | True | 90.0% | yes |
| translated | geo:nationalism | False | True | False | 100.0% | yes |
| translated | product:investigate_claim | True | True | False | 100.0% | yes |
| translated | sentiment | neutral | negative | unknown | 100.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |

## ja_12 — minimax — natural

[Source](https://x.com/toMion818/status/2086784629701521832); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Music-video release promotes the musician's work, not a new MiniMax release; MiniMax is the creation tool.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 34 | 0 |
| translated | 34 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | promotion:general | True | False | False | 100.0% | yes |
| translated | sentiment | neutral | positive | positive | 100.0% | yes |
| raw | geo:framework | False | True | False | 98.0% | yes |
| raw | geo:reporting | False | True | False | 98.0% | yes |
| raw | promotion:general | True | False | False | 98.0% | yes |
| raw | sentiment | neutral | positive | positive | 85.0% | yes |
| raw | type:hands_on_usage | True | True | False | 98.0% | yes |
| raw | type:other | False | False | True | 70.0% | yes |

## ja_13 — llama — coverage

[Source](https://x.com/ai_hakase_/status/2103244089747554662); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: llama.cpp runtime bug is not evidence about Meta Llama models; the catalog target is Meta Llama.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 25 | 31 | 0 |
| translated | 26 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 98.0% | yes |
| raw | geo:framework | False | True | False | 98.0% | yes |
| raw | geo:reporting | False | True | False | 98.0% | yes |
| raw | outcome | context_missing | classified | classified | 98.0% | yes |
| raw | product:bug | False | False | True | 90.0% | yes |
| raw | product:complaint | False | True | False | 90.0% | yes |
| raw | sentiment | unknown | negative | neutral | 85.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 98.0% | yes |
| raw | topic:local_inference | False | True | True | 95.0% | yes |
| raw | type:hands_on_usage | False | True | False | 98.0% | yes |
| raw | type:opinions_reactions | False | True | False | 90.0% | yes |
| raw | type:research_explanations | False | True | True | 95.0% | yes |
| raw | type:results_analysis | False | True | False | 90.0% | yes |
| raw | us_national_stance | unknown | none | none | 98.0% | yes |
| translated | china_national_stance | unknown | none | none | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | outcome | context_missing | classified | classified | 100.0% | yes |
| translated | product:bug | False | False | True | 100.0% | yes |
| translated | product:complaint | False | True | False | 100.0% | yes |
| translated | sentiment | unknown | negative | neutral | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | topic:local_inference | False | True | True | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | type:research_explanations | False | True | True | 100.0% | yes |
| translated | type:results_analysis | False | True | False | 100.0% | yes |
| translated | us_national_stance | unknown | none | none | 100.0% | yes |

## ja_14 — minimax — coverage

[Source](https://x.com/KimiAI_Studio/status/2102422720931844486); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: MiniMax CLI launch, reported performance, technical architecture and strong endorsement; no firsthand run stated.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 0 |
| translated | 34 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:testimonial | True | True | False | 100.0% | yes |
| translated | promotion:general | False | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | topic:local_inference | True | True | False | 100.0% | yes |
| translated | type:advertising_marketing | False | True | False | 100.0% | yes |
| translated | type:news_reporting | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:nationalism | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:local_inference | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | False | True | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |

## ja_15 — sakana_ai — coverage

[Source](https://x.com/SakanaAILabs/status/2104928895627833438); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Specific official vacancy/application link. Delivering Japan-origin AI globally is not by itself national superiority or geopolitical framing.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 38 | 0 |
| translated | 32 | 38 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | positive | neutral | 100.0% | yes |
| raw | type:advertising_marketing | False | True | False | 100.0% | yes |
| raw | type:opportunities | False | True | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | positive | neutral | 100.0% | yes |
| translated | type:advertising_marketing | False | True | False | 100.0% | yes |
| translated | type:business_finance | False | True | False | 100.0% | yes |
| translated | type:opportunities | False | True | False | 100.0% | yes |

## ja_16 — mistral — coverage

[Source](https://x.com/iwashi86/status/2105142699661652363); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Explicit support because company is European plus competitive national comparison; China/US leadership is descriptive, not adopted praise/hostility.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 0 | 38 |
| translated | 36 | 3 | 34 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | True | True | false | unmeasured | NO |
| translated | geo:nationalism | True | True | false | unmeasured | NO |
| translated | geo:reporting | True | True | false | unmeasured | NO |
| translated | product:bug | False | False | false | unmeasured | NO |
| translated | product:complaint | False | False | false | unmeasured | NO |
| translated | product:ideas_requests | False | False | false | unmeasured | NO |
| translated | product:investigate_claim | False | False | false | unmeasured | NO |
| translated | product:testimonial | False | True | true | unmeasured | NO |
| translated | promotion:crypto | False | False | false | unmeasured | NO |
| translated | promotion:general | False | False | false | unmeasured | NO |
| translated | promotion:scam | False | False | false | unmeasured | NO |
| translated | promotion:spam | False | False | false | unmeasured | NO |
| translated | promotion:unauthorized | False | False | false | unmeasured | NO |
| translated | sentiment | mixed | mixed | positive | 80.0% | yes |
| translated | topic:agents_tools | False | False | false | unmeasured | NO |
| translated | topic:api_developer_surface | False | False | false | unmeasured | NO |
| translated | topic:cost_performance | False | False | false | unmeasured | NO |
| translated | topic:evals_benchmarks | False | False | false | unmeasured | NO |
| translated | topic:local_inference | False | False | false | unmeasured | NO |
| translated | topic:model_distillation | False | False | false | unmeasured | NO |
| translated | topic:openness_license | True | True | false | unmeasured | NO |
| translated | type:advertising_marketing | False | False | false | unmeasured | NO |
| translated | type:business_finance | True | False | false | unmeasured | NO |
| translated | type:events | False | False | false | unmeasured | NO |
| translated | type:hands_on_usage | False | False | false | unmeasured | NO |
| translated | type:job_listings | False | False | false | unmeasured | NO |
| translated | type:news_reporting | False | False | false | unmeasured | NO |
| translated | type:opinions_reactions | True | True | true | unmeasured | NO |
| translated | type:opportunities | False | False | false | unmeasured | NO |
| translated | type:other | False | False | false | unmeasured | NO |
| translated | type:personnel_changes | False | False | false | unmeasured | NO |
| translated | type:questions_requests | False | False | false | unmeasured | NO |
| translated | type:releases_updates | False | False | false | unmeasured | NO |
| translated | type:research_explanations | False | False | false | unmeasured | NO |
| translated | type:results_analysis | False | False | true | unmeasured | NO |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | True | True | None | unmeasured | NO |
| raw | geo:nationalism | True | True | None | unmeasured | NO |
| raw | geo:reporting | True | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | True | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | mixed | mixed | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | False | False | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | True | True | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | True | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## ja_17 — qwen — coverage

[Source](https://x.com/HAI_h_jp/status/2104489492614942827); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: HAI service availability/price involving Qwen; HAI owns the pitch. Not Qwen-owned advertising.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 33 | 0 |
| translated | 33 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | False | True | True | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:opportunities | False | True | False | 100.0% | yes |
| raw | type:releases_updates | True | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 90.0% | yes |
| translated | promotion:general | True | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | True | False | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | type:advertising_marketing | False | True | False | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:opportunities | False | True | False | 100.0% | yes |

## ja_18 — minimax — coverage

[Source](https://x.com/HuurainoMoutoku/status/2103649257026904529); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Quote explicitly co-promotes MiniMax x SeaArt challenge/prize; author's complaint concerns SeaArt access, not MiniMax model quality.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 28 | 0 | 38 |
| translated | 28 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:bug | False | True | False | 100.0% | yes |
| translated | product:complaint | False | True | True | 100.0% | yes |
| translated | product:ideas_requests | False | True | False | 100.0% | yes |
| translated | promotion:general | True | True | False | 100.0% | yes |
| translated | sentiment | neutral | negative | negative | 100.0% | yes |
| translated | topic:cost_performance | False | True | False | 100.0% | yes |
| translated | type:advertising_marketing | True | True | False | 100.0% | yes |
| translated | type:hands_on_usage | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | type:opportunities | True | True | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | True | None | unmeasured | NO |
| raw | product:complaint | False | True | None | unmeasured | NO |
| raw | product:ideas_requests | False | True | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | False | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | True | True | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | neutral | negative | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | False | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | True | True | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | True | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | False | True | None | unmeasured | NO |
| raw | type:opportunities | True | True | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | True | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## ja_19 — moonshot_kimi — coverage

[Source](https://x.com/xRINGx/status/2102626239794356686); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Chinese national capability denigrated, plus attributed copying/data-routing allegations. Not customer complaint.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 32 | 0 |
| translated | 34 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | True | 80.0% | yes |
| raw | geo:reporting | True | True | False | 80.0% | yes |
| raw | product:investigate_claim | True | True | False | 80.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | False | False | 100.0% | yes |
| translated | china_national_stance | anti | none | anti | 80.0% | yes |
| translated | geo:framework | False | True | False | 90.0% | yes |
| translated | geo:reporting | True | True | False | 80.0% | yes |
| translated | topic:api_developer_surface | True | False | False | 90.0% | yes |
| translated | type:research_explanations | True | False | False | 90.0% | yes |

## ja_20 — deepseek — coverage

[Source](https://x.com/mikoto2000/status/2102656351302541457); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ja.md).

Frozen rationale: Asks concurrency capacity; no firsthand test or requested new feature is established.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 35 | 0 |
| translated | 35 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | topic:local_inference | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:local_inference | True | False | False | 100.0% | yes |
| raw | type:other | False | False | True | 90.0% | yes |

## zh_cn_01 — qwen — natural

[Source](https://x.com/ScarletKc/status/2101132893225656517); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Explains activated versus total MoE parameters using Qwen; rhetorical teaching question is not a support request.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 38 | 0 |
| translated | 35 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 98.0% | yes |
| raw | geo:reporting | False | True | False | 98.0% | yes |
| raw | type:opinions_reactions | False | True | False | 99.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |

## zh_cn_02 — minimax — natural

[Source](https://x.com/wugudehaore/status/2098964592680731131); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Valuation, free float, unlock and bearish investment view; no customer complaint.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 0 | 38 |
| translated | 35 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | False | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | negative | negative | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | False | False | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | True | True | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | True | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## zh_cn_03 — deepseek — natural

[Source](https://x.com/vintcessun/status/2095452004709732479); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Specific DeepSeek benchmark improvement and training/verification explanation; not evidence the author ran it.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |
| translated | 34 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | sentiment | positive | positive | neutral | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | sentiment | positive | mixed | positive | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:research_explanations | True | True | False | 100.0% | yes |

## zh_cn_04 — dots — natural

[Source](https://x.com/realfxw/status/2101120516278849859); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: LightOnOCR is pitched; dots.ocr appears only as a speed comparison foil. Do not transfer competitor license/features.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 31 | 0 |
| translated | 36 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | china_national_stance | none | none | None | unmeasured | NO |
| translated | geo:framework | False | False | None | unmeasured | NO |
| translated | geo:nationalism | False | False | None | unmeasured | NO |
| translated | geo:reporting | False | False | None | unmeasured | NO |
| translated | outcome | classified | classified | None | unmeasured | NO |
| translated | product:bug | False | False | None | unmeasured | NO |
| translated | product:complaint | False | False | None | unmeasured | NO |
| translated | product:ideas_requests | False | False | None | unmeasured | NO |
| translated | product:investigate_claim | False | False | None | unmeasured | NO |
| translated | product:testimonial | False | False | None | unmeasured | NO |
| translated | promotion:crypto | False | False | None | unmeasured | NO |
| translated | promotion:general | True | True | None | unmeasured | NO |
| translated | promotion:scam | False | False | None | unmeasured | NO |
| translated | promotion:spam | False | False | None | unmeasured | NO |
| translated | promotion:unauthorized | False | False | None | unmeasured | NO |
| translated | sentiment | neutral | neutral | None | unmeasured | NO |
| translated | topic:agents_tools | False | False | None | unmeasured | NO |
| translated | topic:api_developer_surface | False | False | None | unmeasured | NO |
| translated | topic:cost_performance | True | True | None | unmeasured | NO |
| translated | topic:evals_benchmarks | True | True | None | unmeasured | NO |
| translated | topic:local_inference | False | False | None | unmeasured | NO |
| translated | topic:model_distillation | False | False | None | unmeasured | NO |
| translated | topic:openness_license | False | False | None | unmeasured | NO |
| translated | type:advertising_marketing | False | False | None | unmeasured | NO |
| translated | type:business_finance | False | False | None | unmeasured | NO |
| translated | type:events | False | False | None | unmeasured | NO |
| translated | type:hands_on_usage | False | False | None | unmeasured | NO |
| translated | type:job_listings | False | False | None | unmeasured | NO |
| translated | type:news_reporting | True | False | None | unmeasured | NO |
| translated | type:opinions_reactions | False | True | None | unmeasured | NO |
| translated | type:opportunities | False | False | None | unmeasured | NO |
| translated | type:other | False | False | None | unmeasured | NO |
| translated | type:personnel_changes | False | False | None | unmeasured | NO |
| translated | type:questions_requests | False | False | None | unmeasured | NO |
| translated | type:releases_updates | False | False | None | unmeasured | NO |
| translated | type:research_explanations | False | False | None | unmeasured | NO |
| translated | type:results_analysis | True | True | None | unmeasured | NO |
| translated | us_national_stance | none | none | None | unmeasured | NO |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | sentiment | neutral | neutral | positive | 100.0% | yes |
| raw | topic:local_inference | False | False | True | 100.0% | yes |
| raw | topic:openness_license | False | False | True | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:releases_updates | False | False | True | 100.0% | yes |
| raw | type:research_explanations | False | False | True | 100.0% | yes |

## zh_cn_05 — minimax — natural

[Source](https://x.com/HueReasonegfo9/status/2096131230765105161); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Adult-product seller, unrelated Hailuo keyword collision. An ad alone is not repeated spam evidence.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 35 | 0 |
| translated | 32 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | promotion:scam | False | True | False | 100.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |
| translated | china_national_stance | unknown | none | none | 90.0% | yes |
| translated | promotion:general | True | False | True | 100.0% | yes |
| translated | promotion:scam | False | True | False | 100.0% | yes |
| translated | promotion:spam | False | True | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| translated | us_national_stance | unknown | none | none | 90.0% | yes |

## zh_cn_06 — minimax — natural

[Source](https://x.com/ekll01/status/2085587083029356715); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Plugin compatibility dissatisfaction, without explicit firsthand use or confirmed software malfunction.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 36 | 0 |
| translated | 35 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | product:complaint | True | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| translated | type:results_analysis | False | False | True | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | product:complaint | True | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | False | 100.0% | yes |

## zh_cn_07 — deepseek — natural

[Source](https://x.com/YishaoRice/status/2094993005170286811); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: DeepSeek cost comparison in monetization/industry analysis; country origin is incidental, not political evaluation.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 31 | 30 | 0 |
| translated | 30 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | False | True | 100.0% | yes |
| raw | outcome | classified | context_missing | classified | 100.0% | yes |
| raw | sentiment | positive | neutral | neutral | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | topic:openness_license | True | False | False | 100.0% | yes |
| raw | type:business_finance | True | False | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | False | False | 100.0% | yes |
| raw | type:results_analysis | True | False | True | 100.0% | yes |
| translated | outcome | classified | context_missing | classified | 100.0% | yes |
| translated | sentiment | positive | neutral | neutral | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| translated | topic:openness_license | True | False | False | 100.0% | yes |
| translated | type:business_finance | True | False | False | 100.0% | yes |
| translated | type:news_reporting | True | True | False | 100.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |
| translated | type:results_analysis | True | False | False | 100.0% | yes |

## zh_cn_08 — deepseek — natural

[Source](https://x.com/LShanrenM/status/2086763159180959889); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Criticizes the Chinese state-capital investment system; not a product malfunction. Stance intensity is separately flagged for sensitivity.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 31 | 2 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | anti | none | none | unmeasured | NO |
| raw | geo:framework | True | False | False | 80.0% | yes |
| raw | geo:nationalism | True | False | False | 80.0% | yes |
| raw | type:business_finance | True | True | False | 90.0% | yes |
| raw | type:opinions_reactions | True | True | False | 80.0% | yes |
| raw | type:other | False | False | True | 90.0% | yes |
| raw | us_national_stance | none | none | none | unmeasured | NO |

## zh_cn_09 — deepseek — natural

[Source](https://x.com/yabarich/status/2094358567365300351); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: B.AI infrastructure pitch with DeepSeek as supported backend; no new target-model release or target-owned CTA.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 33 | 1 |
| translated | 31 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | context_missing | classified | 100.0% | yes |
| raw | promotion:crypto | False | True | False | 0.0% | NO |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | unknown | positive | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | False | True | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| translated | outcome | classified | context_missing | classified | 100.0% | yes |
| translated | promotion:crypto | False | True | False | 100.0% | yes |
| translated | promotion:general | True | False | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | unknown | positive | 100.0% | yes |
| translated | topic:cost_performance | False | True | True | 100.0% | yes |
| translated | type:advertising_marketing | False | False | True | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |

## zh_cn_10 — minimax — natural

[Source](https://x.com/zuz84093219/status/2104885840367538431); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Anticipates a forthcoming update without naming a concrete changed capability; not a completed launch.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 36 | 0 |
| translated | 34 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:other | False | False | True | 100.0% | yes |
| translated | type:releases_updates | False | True | True | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | True | 100.0% | yes |

## zh_cn_11 — doubao — natural

[Source](https://x.com/cy_xiaozhu/status/2100457097158885603); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Product quality comparison endorses Doubao; does not explicitly state a firsthand test.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 35 | 0 |
| translated | 34 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| translated | type:results_analysis | True | False | False | 100.0% | yes |

## zh_cn_13 — mimo — coverage

[Source](https://x.com/0xLogicrw/status/2104479508019745100); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Detailed repetition bug diagnosis, training remedy and release; no author customer complaint.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 1 |
| translated | 31 | 30 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | geo:reporting | False | True | False | 90.0% | yes |
| raw | promotion:general | False | False | True | 60.0% | yes |
| raw | sentiment | neutral | mixed | positive | 60.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 80.0% | yes |
| raw | topic:model_distillation | True | False | False | 80.0% | yes |
| raw | type:opinions_reactions | False | True | False | 50.0% | NO |
| translated | geo:framework | False | True | False | 90.0% | yes |
| translated | geo:nationalism | False | True | False | 95.0% | yes |
| translated | geo:reporting | False | True | False | 90.0% | yes |
| translated | sentiment | neutral | mixed | neutral | 90.0% | yes |
| translated | topic:agents_tools | True | True | False | 90.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 80.0% | yes |
| translated | topic:cost_performance | True | True | False | 90.0% | yes |
| translated | topic:model_distillation | True | False | False | 80.0% | yes |
| translated | topic:openness_license | True | True | False | 100.0% | yes |
| translated | type:advertising_marketing | False | True | False | 90.0% | yes |
| translated | type:news_reporting | True | True | False | 90.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | type:releases_updates | True | True | False | 90.0% | yes |
| translated | type:research_explanations | True | True | False | 70.0% | yes |

## zh_cn_14 — deepseek — coverage

[Source](https://x.com/francis_cgl/status/2103775174508061032); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: B.AI limited free access plus explicit TRON ecosystem pitch; DeepSeek service-provider promotion must not transfer. Source contains mixed Chinese scripts.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 27 | 31 | 0 |
| translated | 28 | 30 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:testimonial | False | False | True | 100.0% | yes |
| translated | promotion:crypto | True | True | False | 100.0% | yes |
| translated | promotion:spam | False | True | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | positive | positive | 100.0% | yes |
| translated | topic:agents_tools | False | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | type:advertising_marketing | False | True | True | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | type:opportunities | True | True | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| raw | china_national_stance | none | none | pro | 100.0% | yes |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | geo:reporting | False | True | False | 90.0% | yes |
| raw | product:testimonial | False | True | False | 100.0% | yes |
| raw | promotion:crypto | True | True | False | 80.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | positive | positive | 90.0% | yes |
| raw | topic:agents_tools | False | True | True | 80.0% | yes |
| raw | topic:openness_license | False | False | True | 90.0% | yes |
| raw | type:advertising_marketing | False | True | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:opportunities | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | False | 100.0% | yes |

## zh_cn_15 — qwen — coverage

[Source](https://x.com/Alan_jupiters/status/2101868706532094095); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Explicit Reddit firsthand test quoted/reported, 50 tokens/sec and local dual-card method.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 31 | 0 | 38 |
| translated | 31 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | True | True | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | True | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | positive | positive | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | True | False | None | unmeasured | NO |
| raw | topic:cost_performance | True | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | True | False | None | unmeasured | NO |
| raw | topic:local_inference | True | True | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | True | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | True | True | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | True | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | True | True | None | unmeasured | NO |
| raw | type:results_analysis | True | True | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:testimonial | True | True | False | 100.0% | yes |
| translated | promotion:general | False | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | True | False | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | False | True | 100.0% | yes |
| translated | topic:openness_license | True | False | False | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:research_explanations | True | True | False | 100.0% | yes |

## zh_cn_16 — deepseek — coverage

[Source](https://x.com/KhanAIBuilds/status/2103002792021594377); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Explains US model-IP versus Chinese sensitive-data concerns; no adopted national praise/hostility.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 33 | 0 |
| translated | 35 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:reporting | True | True | False | 70.0% | yes |
| translated | sentiment | negative | neutral | neutral | 40.0% | yes |
| translated | topic:api_developer_surface | True | False | False | 100.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |
| raw | geo:reporting | True | True | False | 100.0% | yes |
| raw | product:investigate_claim | True | True | False | 100.0% | yes |
| raw | sentiment | negative | negative | neutral | 100.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 100.0% | yes |
| raw | type:research_explanations | True | False | False | 100.0% | yes |

## zh_cn_17 — ernie — coverage

[Source](https://x.com/daityn_rucker/status/2102965016924418336); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Repeated promotional keyword stuffing sells posting software/accounts; ERNIE name has no coherent target-brand predicate.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 34 | 0 |
| translated | 34 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | promotion:general | False | False | True | 100.0% | yes |
| raw | promotion:scam | False | True | False | 100.0% | yes |
| raw | promotion:spam | True | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |
| translated | china_national_stance | unknown | none | none | 100.0% | yes |
| translated | outcome | context_missing | context_missing | classified | 100.0% | yes |
| translated | promotion:scam | False | True | False | 100.0% | yes |
| translated | promotion:spam | True | True | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| translated | us_national_stance | unknown | none | none | 100.0% | yes |

## zh_cn_18 — qwen — coverage

[Source](https://x.com/NFT_Chen/status/2102237798824902873); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Concrete announced Qwen family, conference, quoted formal leadership change and training results. Domestic ranking alone is not nationalism.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 26 | 0 |
| translated | 34 | 28 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | china_national_stance | none | none | pro | 50.0% | yes |
| translated | geo:framework | False | True | True | 60.0% | yes |
| translated | geo:nationalism | False | False | True | 70.0% | yes |
| translated | geo:reporting | False | True | False | 90.0% | yes |
| translated | topic:agents_tools | True | False | False | 90.0% | yes |
| translated | topic:evals_benchmarks | True | True | False | 80.0% | yes |
| translated | topic:openness_license | True | True | False | 80.0% | yes |
| translated | type:advertising_marketing | False | True | False | 80.0% | yes |
| translated | type:business_finance | True | True | False | 70.0% | yes |
| translated | type:events | True | True | False | 80.0% | yes |
| translated | type:research_explanations | True | True | False | 80.0% | yes |
| translated | type:results_analysis | True | True | False | 80.0% | yes |
| raw | china_national_stance | none | none | pro | 100.0% | yes |
| raw | geo:framework | False | True | True | 90.0% | yes |
| raw | geo:nationalism | False | False | True | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | True | False | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | False | True | False | 100.0% | yes |
| raw | type:business_finance | True | True | False | 100.0% | yes |
| raw | type:events | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:personnel_changes | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |

## zh_cn_19 — mimo — coverage

[Source](https://x.com/Sigma_ccc/status/2105141166572454356); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: New promotion of a named MiMo leader and model result; admiration of a person does not automatically yield product testimonial.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 33 | 0 |
| translated | 36 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | product:testimonial | False | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | False | False | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:business_finance | True | True | False | 100.0% | yes |
| raw | type:hands_on_usage | False | True | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:testimonial | False | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | topic:openness_license | True | True | False | 100.0% | yes |
| translated | type:business_finance | True | True | False | 100.0% | yes |
| translated | type:news_reporting | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:personnel_changes | True | True | False | 100.0% | yes |

## zh_cn_20 — deepseek — coverage

[Source](https://x.com/tianyi/status/2104881693706653733); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-zh-cn.md).

Frozen rationale: Explicit team senior-engineer hiring and contactable poster/link; technical report title alone is not a substantive explanation.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 35 | 0 |
| translated | 33 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | positive | positive | 100.0% | yes |
| translated | type:advertising_marketing | False | True | False | 100.0% | yes |
| translated | type:job_listings | True | True | False | 100.0% | yes |
| translated | type:opportunities | False | True | False | 100.0% | yes |
| translated | type:research_explanations | False | False | True | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | positive | positive | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | False | True | False | 100.0% | yes |
| raw | type:job_listings | True | True | False | 100.0% | yes |
| raw | type:opportunities | False | True | False | 100.0% | yes |

## ko_01 — deepseek — natural

[Source](https://x.com/antfeedapp/status/2080523349114106360); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Company strategy, revenue, research structure and attributed China compute constraint. Reported national weakness is not author's adopted nationalism.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 29 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | True | True | False | 100.0% | yes |
| raw | geo:reporting | True | True | False | 100.0% | yes |
| raw | sentiment | neutral | positive | positive | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:business_finance | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | True | 100.0% | yes |
| raw | type:research_explanations | True | False | True | 100.0% | yes |

## ko_02 — deepseek — natural

[Source](https://x.com/lostland/status/2104541211021525328); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Actual local/API speed comparison; dissatisfaction with missing local multimodality but positive earlier experience.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 0 |
| translated | 33 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:bug | False | True | False | 90.0% | yes |
| translated | product:ideas_requests | True | True | False | 100.0% | yes |
| translated | sentiment | mixed | mixed | negative | 90.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 80.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| translated | type:results_analysis | True | True | False | 70.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | product:bug | False | True | False | 100.0% | yes |
| raw | product:ideas_requests | True | True | False | 100.0% | yes |
| raw | sentiment | mixed | negative | negative | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | False | 100.0% | yes |

## ko_03 — qwen — natural

[Source](https://x.com/midagedev/status/2097823171068264906); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Explicit Qwen run at 160 tok/s, favorable speed comparison and heat observation.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 0 |
| translated | 34 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | False | False | 100.0% | yes |
| raw | sentiment | positive | positive | neutral | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:research_explanations | False | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:testimonial | True | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:research_explanations | False | True | False | 100.0% | yes |
| translated | type:results_analysis | True | True | False | 100.0% | yes |

## ko_04 — deepseek — natural

[Source](https://x.com/pocopoco9876/status/2101277345336463807); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Jev is called faster/cheaper/more accurate than DeepSeek without detailed evidence; a comparison foil is not automatically negative or advertised.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 35 | 0 |
| translated | 36 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | product:testimonial | False | False | True | 100.0% | yes |
| translated | sentiment | neutral | negative | positive | 100.0% | yes |
| translated | topic:evals_benchmarks | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:results_analysis | False | False | True | 100.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | negative | positive | 100.0% | yes |
| raw | topic:agents_tools | False | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | False | False | True | 100.0% | yes |

## ko_05 — deepseek — natural

[Source](https://x.com/ilpyung98/status/2085941962327437459); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Long token-market report mentions DeepSeek only as an AgentKeys-supported model. Do not transfer unrelated crypto finance or risk reporting to DeepSeek.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | context_missing | context_missing | 100.0% | yes |
| raw | promotion:crypto | False | True | False | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:releases_updates | True | False | False | 100.0% | yes |

## ko_06 — qwen — natural

[Source](https://x.com/Jinnissive/status/2084102241221517450); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Excited Korean reaction plus official Qwen launch/CTA and specific reported agent outputs in quote. English quote means this is not Korean-only evidence.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | geo:reporting | False | True | False | 90.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | True | True | False | 100.0% | yes |
| raw | type:opportunities | False | True | False | 100.0% | yes |
| raw | type:releases_updates | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |

## ko_07 — qwen — natural

[Source](https://x.com/umeume12341/status/2078455321065054291); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Qwen appears only in comparison of fine-tuning ecosystem counts; Gemma-specific techniques/bugs must not transfer.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | context_missing | context_missing | 100.0% | yes |
| raw | sentiment | neutral | unknown | unknown | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |

## ko_08 — deepseek — natural

[Source](https://x.com/cozybearlog/status/2084596474801782964); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Token-usage ranking and pricing competition; Chinese origin alone does not create geopolitical meaning.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 34 | 0 |
| translated | 34 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | False | True | 100.0% | yes |
| translated | sentiment | positive | neutral | positive | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | type:business_finance | True | False | False | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| raw | geo:framework | False | False | True | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | sentiment | positive | neutral | neutral | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | type:business_finance | True | False | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |

## ko_09 — deepseek — natural

[Source](https://x.com/_nodelay/status/2092525849564332104); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Uses DeepSeek but explicitly notes absence of vision and Qwen workaround; product limitation, not concrete malfunction.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 30 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:complaint | True | False | False | 100.0% | yes |
| raw | product:ideas_requests | True | False | False | 100.0% | yes |
| raw | product:testimonial | False | True | True | 100.0% | yes |
| raw | sentiment | mixed | positive | positive | 100.0% | yes |
| raw | topic:agents_tools | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:research_explanations | False | True | False | 100.0% | yes |

## ko_10 — deepseek — natural

[Source](https://x.com/StarLibra07/status/2099593854886563913); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Actual gameplay test and bandwidth-limited speed disappointment; unseen video cannot establish model results.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 33 | 1 |
| translated | 36 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | product:ideas_requests | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:ideas_requests | False | True | False | 100.0% | yes |
| raw | product:testimonial | False | False | False | 0.0% | NO |
| raw | sentiment | neutral | neutral | positive | 100.0% | yes |
| raw | topic:evals_benchmarks | False | False | True | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | False | False | True | 100.0% | yes |

## ko_11 — deepseek — natural

[Source](https://x.com/Cynical_L/status/2097644061775847486); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Says only DeepSeek deserves Flash name; generic praise not measured performance or geopolitics.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 35 | 0 |
| translated | 35 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | product:testimonial | True | False | False | 100.0% | yes |
| raw | topic:cost_performance | True | False | False | 100.0% | yes |
| raw | type:questions_requests | False | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | True | 100.0% | yes |
| translated | product:testimonial | True | True | False | 95.0% | yes |
| translated | topic:cost_performance | True | False | False | 95.0% | yes |
| translated | type:questions_requests | False | True | False | 95.0% | yes |
| translated | type:releases_updates | False | True | False | 95.0% | yes |

## ko_12 — deepseek — natural

[Source](https://x.com/nacyotKim/status/2083196878079041932); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Surprise DeepSeek release and must-deploy reaction. US timezone comment is not geopolitical.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | product:testimonial | True | False | False | 95.0% | yes |
| raw | sentiment | positive | neutral | neutral | 70.0% | yes |

## ko_13 — upstage — coverage

[Source](https://x.com/HyperAccelAI/status/2104484668662055096); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: HyperAccel event/device promotion with Upstage participating. Do not transfer HyperAccel product pitch to Upstage. Bilingual source retained.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 31 | 0 |
| translated | 33 | 29 | 2 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | context_missing | context_missing | 100.0% | yes |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | neutral | unknown | 100.0% | yes |
| raw | topic:agents_tools | True | False | False | 100.0% | yes |
| raw | topic:cost_performance | True | False | False | 100.0% | yes |
| raw | type:events | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| translated | china_national_stance | none | none | none | 0.0% | NO |
| translated | outcome | classified | context_missing | context_missing | 100.0% | yes |
| translated | promotion:general | True | True | False | 100.0% | yes |
| translated | promotion:spam | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | neutral | unknown | 100.0% | yes |
| translated | topic:agents_tools | True | False | False | 100.0% | yes |
| translated | topic:cost_performance | True | False | False | 100.0% | yes |
| translated | type:events | True | True | False | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | us_national_stance | none | none | none | 0.0% | NO |

## ko_14 — qwen — coverage

[Source](https://x.com/USAnt_IDEA/status/2102365680897335503); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Explicit China self-sufficiency celebration and contempt for US restriction/monopoly narrative, with Qwen results and conference/company strategy.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 31 | 0 | 38 |
| translated | 31 | 30 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | china_national_stance | pro | none | pro | 45.0% | yes |
| translated | geo:reporting | True | True | False | 90.0% | yes |
| translated | product:testimonial | True | True | False | 90.0% | yes |
| translated | promotion:general | False | True | False | 90.0% | yes |
| translated | topic:agents_tools | True | False | False | 90.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 80.0% | yes |
| translated | topic:openness_license | True | True | False | 70.0% | yes |
| translated | type:advertising_marketing | False | True | False | 90.0% | yes |
| translated | type:events | True | True | False | 95.0% | yes |
| translated | type:news_reporting | True | False | False | 80.0% | yes |
| translated | type:releases_updates | True | True | False | 70.0% | yes |
| translated | type:results_analysis | True | False | True | 70.0% | yes |
| raw | china_national_stance | pro | none | None | unmeasured | NO |
| raw | geo:framework | True | True | None | unmeasured | NO |
| raw | geo:nationalism | True | True | None | unmeasured | NO |
| raw | geo:reporting | True | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | True | True | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | True | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | positive | positive | None | unmeasured | NO |
| raw | topic:agents_tools | True | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | True | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | True | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | True | True | None | unmeasured | NO |
| raw | type:advertising_marketing | False | True | None | unmeasured | NO |
| raw | type:business_finance | True | True | None | unmeasured | NO |
| raw | type:events | True | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | True | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | True | True | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | True | True | None | unmeasured | NO |
| raw | us_national_stance | anti | anti | None | unmeasured | NO |

## ko_15 — llama — coverage

[Source](https://x.com/zupet0/status/2101945590838178015); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Qwen failure after llama.cpp update is not evidence about Meta Llama, the target brand.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 32 | 0 |
| translated | 35 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 95.0% | yes |
| raw | outcome | context_missing | context_missing | classified | 95.0% | yes |
| raw | product:bug | False | False | True | 80.0% | yes |
| raw | sentiment | unknown | negative | negative | 70.0% | yes |
| raw | topic:local_inference | False | True | True | 90.0% | yes |
| raw | type:questions_requests | False | True | False | 90.0% | yes |
| raw | type:results_analysis | False | True | False | 95.0% | yes |
| raw | us_national_stance | unknown | none | none | 95.0% | yes |
| translated | china_national_stance | unknown | none | none | 100.0% | yes |
| translated | outcome | context_missing | context_missing | classified | 100.0% | yes |
| translated | product:bug | False | False | True | 100.0% | yes |
| translated | sentiment | unknown | unknown | negative | 100.0% | yes |
| translated | topic:local_inference | False | True | True | 100.0% | yes |
| translated | us_national_stance | unknown | none | none | 100.0% | yes |

## ko_16 — deepseek — coverage

[Source](https://x.com/igangsan54078/status/2105068856465109486); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Anuma memory/service pitch: DeepSeek is one interchangeable backend, not the promoted provider. No evidence the author personally tested DeepSeek.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 33 | 0 |
| translated | 33 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | outcome | classified | context_missing | context_missing | 100.0% | yes |
| translated | promotion:crypto | False | True | False | 100.0% | yes |
| translated | promotion:general | True | True | False | 100.0% | yes |
| translated | sentiment | neutral | unknown | unknown | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |
| raw | outcome | classified | context_missing | context_missing | 100.0% | yes |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | neutral | unknown | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:research_explanations | True | False | False | 100.0% | yes |

## ko_17 — qwen — coverage

[Source](https://x.com/igangsan54078/status/2101867764013240794); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: ZetaChain blockchain/Anuma memory ecosystem is promoted; Qwen is a listed backend. Does not establish target-owned promotion.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 0 |
| translated | 33 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | context_missing | context_missing | 100.0% | yes |
| raw | promotion:crypto | True | True | False | 100.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | neutral | unknown | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:research_explanations | True | False | False | 100.0% | yes |
| translated | outcome | classified | context_missing | context_missing | 100.0% | yes |
| translated | promotion:crypto | True | True | False | 100.0% | yes |
| translated | promotion:spam | False | True | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | neutral | unknown | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |

## ko_18 — deepseek — coverage

[Source](https://x.com/Coin_Scoop/status/2104586940729204961); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Attributed sensitive-data investigation, not adopted national hostility. Separate CoinScoop news-site CTA is untracked promotion.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 34 | 0 |
| translated | 34 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | promotion:general | True | False | False | 100.0% | yes |
| translated | sentiment | neutral | negative | negative | 100.0% | yes |
| translated | topic:api_developer_surface | True | False | False | 100.0% | yes |
| raw | geo:framework | False | True | True | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | neutral | negative | negative | 100.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 100.0% | yes |

## ko_19 — qwen — coverage

[Source](https://x.com/G_ameman/status/2102253901692993948); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Qwen distilled checkpoint release supported by MiMo quote; MiMo-specific RL benchmarks/organizational praise do not automatically describe Qwen.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 30 | 0 |
| translated | 34 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | classified | context_missing | 100.0% | yes |
| raw | sentiment | neutral | neutral | unknown | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | False | True | False | 100.0% | yes |
| raw | topic:model_distillation | True | True | False | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:releases_updates | True | False | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |
| translated | geo:framework | False | False | True | 100.0% | yes |
| translated | outcome | classified | context_missing | classified | 100.0% | yes |
| translated | topic:model_distillation | True | True | False | 100.0% | yes |
| translated | topic:openness_license | True | False | False | 100.0% | yes |
| translated | type:news_reporting | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | False | False | True | 100.0% | yes |
| translated | type:releases_updates | True | True | False | 100.0% | yes |
| translated | type:research_explanations | True | False | False | 100.0% | yes |

## ko_20 — qwen — coverage

[Source](https://x.com/porysmail/status/2101910305882488899); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-ko.md).

Frozen rationale: Firsthand Qwen setup, strong real-image praise but anime-quality reservation; MiniMax speed problems do not transfer.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 3 | 34 |
| translated | 33 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:complaint | True | False | False | 100.0% | yes |
| translated | sentiment | mixed | positive | positive | 100.0% | yes |
| translated | topic:cost_performance | False | True | False | 100.0% | yes |
| translated | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | geo:framework | False | True | false | unmeasured | NO |
| raw | geo:nationalism | False | False | false | unmeasured | NO |
| raw | geo:reporting | False | True | false | unmeasured | NO |
| raw | product:bug | False | False | false | unmeasured | NO |
| raw | product:complaint | True | False | false | unmeasured | NO |
| raw | product:ideas_requests | False | False | false | unmeasured | NO |
| raw | product:investigate_claim | False | False | false | unmeasured | NO |
| raw | product:testimonial | True | True | true | unmeasured | NO |
| raw | promotion:crypto | False | False | false | unmeasured | NO |
| raw | promotion:general | False | False | false | unmeasured | NO |
| raw | promotion:scam | False | False | false | unmeasured | NO |
| raw | promotion:spam | False | False | false | unmeasured | NO |
| raw | promotion:unauthorized | False | False | false | unmeasured | NO |
| raw | sentiment | mixed | positive | positive | 100.0% | yes |
| raw | topic:agents_tools | False | False | false | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | false | unmeasured | NO |
| raw | topic:cost_performance | False | True | false | unmeasured | NO |
| raw | topic:evals_benchmarks | True | True | true | unmeasured | NO |
| raw | topic:local_inference | True | True | true | unmeasured | NO |
| raw | topic:model_distillation | False | False | false | unmeasured | NO |
| raw | topic:openness_license | False | False | false | unmeasured | NO |
| raw | type:advertising_marketing | False | False | false | unmeasured | NO |
| raw | type:business_finance | False | False | false | unmeasured | NO |
| raw | type:events | False | False | false | unmeasured | NO |
| raw | type:hands_on_usage | True | True | true | unmeasured | NO |
| raw | type:job_listings | False | False | false | unmeasured | NO |
| raw | type:news_reporting | False | False | false | unmeasured | NO |
| raw | type:opinions_reactions | True | True | true | unmeasured | NO |
| raw | type:opportunities | False | False | false | unmeasured | NO |
| raw | type:other | False | False | false | unmeasured | NO |
| raw | type:personnel_changes | False | False | false | unmeasured | NO |
| raw | type:questions_requests | False | False | false | unmeasured | NO |
| raw | type:releases_updates | True | True | false | unmeasured | NO |
| raw | type:research_explanations | False | False | false | unmeasured | NO |
| raw | type:results_analysis | True | True | true | unmeasured | NO |

## en_01 — qwen — natural

[Source](https://x.com/abrakjamson/status/2092479075990528429); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Fine-tuning workflow and prior observed mediocre output; no new model release or claimed model malfunction.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:complaint | True | True | False | 100.0% | yes |
| raw | product:ideas_requests | False | True | False | 100.0% | yes |
| raw | sentiment | negative | mixed | neutral | 100.0% | yes |
| raw | topic:local_inference | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |

## en_02 — deepseek — natural

[Source](https://x.com/BoreanTulip/status/2086733218263249195); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Rhetorical price/value endorsement of DeepSeek, not genuine help request or national stance.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | product:testimonial | False | True | False | 100.0% | yes |
| raw | sentiment | positive | positive | negative | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | False | False | True | 100.0% | yes |

## en_03 — glm — natural

[Source](https://x.com/TanbinFi/status/2079499139642183942); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: TokenRouter owns the time-limited free-use offer; no GLM-owned pitch established.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 30 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | positive | positive | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:openness_license | False | True | False | 100.0% | yes |
| raw | type:advertising_marketing | False | True | True | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:opportunities | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | True | 100.0% | yes |

## en_04 — qwen — natural

[Source](https://x.com/Chris_Wozniczek/status/2091872180782923995); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Desires a specific Qwen size/variant and future test. Praise of Kimi must not become a Qwen testimonial.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | True | True | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | True | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | positive | positive | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | False | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | True | True | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## en_05 — qwen — natural

[Source](https://x.com/largePrawn/status/2093858708514308215); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Hypothetical joke about instructing Qwen; no completed use, bug, scam offer or national statement.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 2 | 34 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | false | unmeasured | NO |
| raw | geo:nationalism | False | False | false | unmeasured | NO |
| raw | geo:reporting | False | False | false | unmeasured | NO |
| raw | outcome | classified | classified | context_missing | 100.0% | yes |
| raw | product:bug | False | False | false | unmeasured | NO |
| raw | product:complaint | False | False | false | unmeasured | NO |
| raw | product:ideas_requests | False | False | false | unmeasured | NO |
| raw | product:investigate_claim | False | False | false | unmeasured | NO |
| raw | product:testimonial | False | False | false | unmeasured | NO |
| raw | promotion:crypto | False | False | false | unmeasured | NO |
| raw | promotion:general | False | False | false | unmeasured | NO |
| raw | promotion:scam | False | False | false | unmeasured | NO |
| raw | promotion:spam | False | False | false | unmeasured | NO |
| raw | promotion:unauthorized | False | False | false | unmeasured | NO |
| raw | sentiment | neutral | negative | unknown | 100.0% | yes |
| raw | topic:agents_tools | True | False | false | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | false | unmeasured | NO |
| raw | topic:cost_performance | False | False | false | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | false | unmeasured | NO |
| raw | topic:local_inference | False | False | false | unmeasured | NO |
| raw | topic:model_distillation | False | False | false | unmeasured | NO |
| raw | topic:openness_license | False | False | false | unmeasured | NO |
| raw | type:advertising_marketing | False | False | false | unmeasured | NO |
| raw | type:business_finance | False | False | false | unmeasured | NO |
| raw | type:events | False | False | false | unmeasured | NO |
| raw | type:hands_on_usage | False | True | false | unmeasured | NO |
| raw | type:job_listings | False | False | false | unmeasured | NO |
| raw | type:news_reporting | False | False | false | unmeasured | NO |
| raw | type:opinions_reactions | True | True | false | unmeasured | NO |
| raw | type:opportunities | False | False | false | unmeasured | NO |
| raw | type:other | False | False | false | unmeasured | NO |
| raw | type:personnel_changes | False | False | false | unmeasured | NO |
| raw | type:questions_requests | False | False | false | unmeasured | NO |
| raw | type:releases_updates | False | False | false | unmeasured | NO |
| raw | type:research_explanations | False | False | false | unmeasured | NO |
| raw | type:results_analysis | False | False | false | unmeasured | NO |

## en_06 — deepseek — natural

[Source](https://x.com/JamieMcullough/status/2099241739970072946); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: DeepSeek-linked stock-market fears, no customer complaint or country argument. Unseen confirmation is not a specific allegation.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 38 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | False | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | False | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | False | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | negative | negative | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | False | False | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | True | True | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## en_07 — deepseek — natural

[Source](https://x.com/seulgibair/status/2098073805113450594); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Requests availability of a named model, not an announcement.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:ideas_requests | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |

## en_08 — qwen — natural

[Source](https://x.com/CodeBuilder_/status/2094865755724509408); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Question plus stored parent's explicit local Qwen use/speed praise. Quoted/parent evidence is available, not unseen.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 29 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:ideas_requests | True | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | sentiment | positive | positive | neutral | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | topic:local_inference | True | False | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |

## en_09 — deepseek — natural

[Source](https://x.com/LordRagnarao/status/2096553038433362425); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: SOMA compression pitch and quoted measured DeepSeek-token savings; SOMA owns credits/CTA, not DeepSeek.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 29 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 95.0% | yes |
| raw | geo:reporting | False | True | False | 95.0% | yes |
| raw | promotion:unauthorized | False | True | False | 95.0% | yes |
| raw | sentiment | neutral | neutral | positive | 90.0% | yes |
| raw | type:advertising_marketing | False | False | True | 90.0% | yes |
| raw | type:news_reporting | True | False | False | 95.0% | yes |
| raw | type:opinions_reactions | False | True | False | 90.0% | yes |
| raw | type:opportunities | True | False | False | 95.0% | yes |
| raw | type:releases_updates | True | False | False | 90.0% | yes |
| raw | type:research_explanations | True | False | False | 90.0% | yes |
| raw | type:results_analysis | True | False | False | 95.0% | yes |

## en_10 — qwen — natural

[Source](https://x.com/vulcantechteam/status/2100709210505826658); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Explains public-document Qwen retrieval, government warnings/removal and lack of sensitive-data evidence; does not adopt allegation as true.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:nationalism | False | True | False | 80.0% | yes |
| raw | product:investigate_claim | False | True | False | 90.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |

## en_11 — deepseek — natural

[Source](https://x.com/mikeng_io/status/2093650413983764672); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Returns to DeepSeek after GLM language problems; bugs/complaints must not transfer to DeepSeek.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | product:bug | False | False | True | 85.0% | yes |
| raw | product:complaint | False | False | True | 90.0% | yes |
| raw | product:testimonial | True | False | False | 95.0% | yes |
| raw | sentiment | positive | positive | mixed | 70.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 90.0% | yes |
| raw | type:results_analysis | True | True | False | 90.0% | yes |

## en_12 — glm — natural

[Source](https://x.com/WorkBudd/status/2097767041440567508); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: WorkBuddy owns credits and signup pitch; GLM listed as an available model.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 98.0% | yes |
| raw | outcome | classified | context_missing | classified | 95.0% | yes |
| raw | promotion:general | True | True | False | 98.0% | yes |
| raw | sentiment | neutral | positive | neutral | 95.0% | yes |
| raw | type:opportunities | True | True | False | 99.0% | yes |
| raw | type:other | False | False | True | 95.0% | yes |

## en_13 — mimo — coverage

[Source](https://x.com/PratikPatel_227/status/2102211363586420906); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Release and explicit official model showcase in quote, performance/pricing comparison; third-party author endorses result.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:releases_updates | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |

## en_14 — deepseek — coverage

[Source](https://x.com/theinformation/status/2104269870560850346); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Regulator investigation is geopolitical reporting; Read more promotes the publisher, not DeepSeek.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | True | 90.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | neutral | negative | negative | 70.0% | yes |
| raw | topic:api_developer_surface | True | False | False | 100.0% | yes |
| raw | topic:model_distillation | True | False | False | 100.0% | yes |

## en_15 — deepseek — coverage

[Source](https://x.com/AdrianaCrosing/status/2105061978448572822); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: B.AI availability/discount narrative. One post supplies no cross-post duplication evidence; no target-owned advertisement.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 27 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | False | True | False | 100.0% | yes |
| raw | promotion:crypto | False | True | False | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | neutral | positive | positive | 70.0% | yes |
| raw | type:advertising_marketing | False | True | False | 80.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | True | 60.0% | yes |
| raw | type:opportunities | False | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | False | 80.0% | yes |

## en_16 — qwen — coverage

[Source](https://x.com/Bitget_AI/status/2103047860602495198); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Qwen explicitly backs hackathon; quote supplies Qwen credits. Attendance venue/session absent, so not events by current definition. Crypto exchange promoted separately.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | outcome | classified | classified | context_missing | 100.0% | yes |
| raw | promotion:crypto | True | True | False | 100.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | sentiment | positive | positive | unknown | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | type:advertising_marketing | True | True | False | 100.0% | yes |
| raw | type:opportunities | True | True | False | 100.0% | yes |

## en_17 — minimax — coverage

[Source](https://x.com/Israfilv2/status/2104250069600116756); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Direct MiniMax plan recommendation and timed quota offer. Shared-key link does not itself prove fraud or authorization status; Telegram channel promoted separately.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | topic:openness_license | False | False | True | 100.0% | yes |
| raw | type:advertising_marketing | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:opportunities | True | True | False | 100.0% | yes |

## en_18 — glm — coverage

[Source](https://x.com/AhmedAlNeaimy/status/2102393479766679876); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Actual response-time problem/comparison and explicit transparency request; no geopolitical content.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | geo:reporting | False | True | False | 90.0% | yes |
| raw | topic:evals_benchmarks | True | True | False | 80.0% | yes |
| raw | type:opinions_reactions | True | True | False | 70.0% | yes |
| raw | type:releases_updates | False | True | False | 60.0% | yes |
| raw | type:results_analysis | True | True | False | 70.0% | yes |

## en_19 — qwen — coverage

[Source](https://x.com/taras_y_sereda/status/2102205025712058858); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: Qwen compression excitement plus separate lab ecosystem showcase in quote; no confirmed measured target result.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:local_inference | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |

## en_20 — minimax — coverage

[Source](https://x.com/_joncipher/status/2101906465418084591); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-en.md).

Frozen rationale: MiniMax appears only as a hashtag inside Engy/BlueTAO token-network promotion; Kimi metrics cannot transfer.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 23 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 40.0% | yes |
| raw | geo:framework | False | True | False | 80.0% | yes |
| raw | geo:reporting | False | True | False | 80.0% | yes |
| raw | outcome | context_missing | classified | classified | 80.0% | yes |
| raw | product:testimonial | False | True | False | 80.0% | yes |
| raw | promotion:spam | False | True | False | 80.0% | yes |
| raw | promotion:unauthorized | False | True | False | 80.0% | yes |
| raw | sentiment | unknown | positive | neutral | 40.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 80.0% | yes |
| raw | type:advertising_marketing | False | True | False | 80.0% | yes |
| raw | type:business_finance | False | True | False | 80.0% | yes |
| raw | type:hands_on_usage | False | True | False | 80.0% | yes |
| raw | type:opinions_reactions | False | True | False | 80.0% | yes |
| raw | type:other | False | False | True | 80.0% | yes |
| raw | type:results_analysis | False | True | False | 80.0% | yes |
| raw | us_national_stance | unknown | none | none | 40.0% | yes |

## es_01 — deepseek — natural

[Source](https://x.com/_garciaa1888/status/2092566125871497468); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Explicit favorable DeepSeek judgment; no explicit firsthand run or substantive result evidence.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |

## es_02 — llama — natural

[Source](https://x.com/yngthv/status/2076490444335448448); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Spanish se llama means is called; BTS fan page is unrelated to Meta Llama.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |

## es_03 — minimax — natural

[Source](https://x.com/Adamaestr0_/status/2084965725501116494); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Firsthand one-shot generation with observed perfect outcome; no numeric benchmark or launch.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 36 | 0 |
| translated | 35 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:results_analysis | True | False | False | 100.0% | yes |

## es_04 — qwen — natural

[Source](https://x.com/oscarhbp1/status/2085410129696948485); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Qwen-focused article title plus creator subscription pitch. Do not assume unseen article technical explanation.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 36 | 0 |
| translated | 31 | 31 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | china_national_stance | none | none | mild_pro | 60.0% | yes |
| translated | geo:framework | False | True | False | 90.0% | yes |
| translated | geo:reporting | False | True | False | 90.0% | yes |
| translated | product:testimonial | False | False | True | 80.0% | yes |
| translated | promotion:general | True | False | True | 80.0% | yes |
| translated | sentiment | neutral | positive | positive | 60.0% | yes |
| translated | type:advertising_marketing | False | True | True | 80.0% | yes |
| translated | type:opinions_reactions | False | True | True | 80.0% | yes |
| translated | type:other | True | False | False | 90.0% | yes |
| translated | type:releases_updates | False | False | True | 80.0% | yes |
| raw | geo:framework | False | True | False | 80.0% | yes |
| raw | promotion:general | True | True | False | 90.0% | yes |
| raw | sentiment | neutral | positive | neutral | 60.0% | yes |
| raw | type:advertising_marketing | False | True | False | 80.0% | yes |
| raw | type:opinions_reactions | False | True | False | 80.0% | yes |
| raw | type:other | True | False | False | 80.0% | yes |

## es_05 — llama — natural

[Source](https://x.com/donal_varo21/status/2076497260678987988); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Spanish se llama keyword collision in political criticism unrelated to Llama.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |

## es_06 — deepseek — natural

[Source](https://x.com/borjaperfra/status/2085654783319236980); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Promotes author's multi-model article; title does not supply actual instructions, completed hands-on use or model-owner pitch.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 30 | 35 | 0 |
| translated | 31 | 33 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | promotion:general | True | False | False | 100.0% | yes |
| translated | sentiment | neutral | neutral | positive | 100.0% | yes |
| translated | topic:agents_tools | True | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | True | 100.0% | yes |
| translated | type:other | True | False | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| translated | type:research_explanations | False | True | False | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | neutral | neutral | positive | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | type:hands_on_usage | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:other | True | False | True | 100.0% | yes |
| raw | type:research_explanations | False | True | False | 100.0% | yes |

## es_07 — deepseek — natural

[Source](https://x.com/mercado_negro/status/2089872473198129488); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Dated DeepSeek API pricing change and comparative price; publisher CTA separately promotes the article.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | neutral | mixed | neutral | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |

## es_08 — deepseek — natural

[Source](https://x.com/LuisOrlandoDia1/status/2091294372935438846); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Roundup reports DeepSeek Harness release; author's linked article promoted, not target service CTA.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | False | True | 60.0% | yes |
| raw | outcome | classified | context_missing | classified | 95.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | positive | positive | neutral | 80.0% | yes |
| raw | type:opinions_reactions | True | True | False | 90.0% | yes |

## es_09 — deepseek — natural

[Source](https://x.com/barckcode/status/2083235322167456092); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Author deployed release; official supporting quote announces architecture/config; NaN hosting promoted separately.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 30 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | outcome | classified | context_missing | classified | 100.0% | yes |
| raw | product:testimonial | True | False | False | 100.0% | yes |
| raw | promotion:general | True | False | False | 100.0% | yes |
| raw | sentiment | positive | positive | neutral | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | True | False | False | 100.0% | yes |
| raw | type:hands_on_usage | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |

## es_10 — deepseek — natural

[Source](https://x.com/YueRexie/status/2091691673092768218); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Pays for and endorses productive transparent Codex plus DeepSeek workflow; not an explicit sales offer.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | False | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | True | True | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | positive | positive | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | True | True | None | unmeasured | NO |
| raw | topic:cost_performance | False | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | True | True | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## es_12 — deepseek — natural

[Source](https://x.com/CANAL44TV/status/2086987211434594668); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Country-bloc AI competition and profitability, not hostility or superiority of a nation; Chinese AI explicitly called effective/value for money.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 33 | 1 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | pro | 35.0% | NO |
| raw | geo:nationalism | False | True | True | 90.0% | yes |
| raw | geo:reporting | True | True | False | 90.0% | yes |
| raw | product:testimonial | True | True | False | 85.0% | yes |
| raw | type:opinions_reactions | False | True | True | 90.0% | yes |

## es_13 — deepseek — coverage

[Source](https://x.com/Branidiaz/status/2104174772862984256); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Specific insecure-code finding and backdoor concern; political triggers and predicted policy exploitation, without adopted national hostility.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 27 | 0 |
| translated | 36 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | True | True | False | 90.0% | yes |
| raw | geo:reporting | True | True | False | 90.0% | yes |
| raw | product:bug | True | False | False | 95.0% | yes |
| raw | product:investigate_claim | True | True | False | 90.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 80.0% | yes |
| raw | topic:local_inference | True | True | False | 80.0% | yes |
| raw | topic:openness_license | True | False | False | 70.0% | yes |
| raw | type:news_reporting | True | True | False | 90.0% | yes |
| raw | type:opinions_reactions | True | True | False | 70.0% | yes |
| raw | type:research_explanations | True | True | False | 80.0% | yes |
| raw | type:results_analysis | True | True | False | 80.0% | yes |
| translated | china_national_stance | none | none | constructive_critical | 35.0% | yes |
| translated | geo:nationalism | False | False | True | 70.0% | yes |
| translated | geo:reporting | True | True | False | 80.0% | yes |
| translated | product:bug | True | False | False | 90.0% | yes |
| translated | product:investigate_claim | True | True | False | 60.0% | yes |
| translated | type:news_reporting | True | False | False | 90.0% | yes |

## es_14 — llama — coverage

[Source](https://x.com/DineroCOP/status/2104602365060071597); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Meta enterprise executive appointment concerns Muse/platform, not Llama. Company-to-specific-product attribution is disputed and sensitivity-scored separately.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 28 | 35 | 0 |
| translated | 27 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | china_national_stance | unknown | none | none | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | outcome | context_missing | classified | context_missing | 100.0% | yes |
| translated | promotion:general | False | True | False | 100.0% | yes |
| translated | sentiment | unknown | neutral | unknown | 100.0% | yes |
| translated | topic:agents_tools | False | True | False | 100.0% | yes |
| translated | topic:api_developer_surface | False | True | False | 100.0% | yes |
| translated | type:business_finance | False | True | False | 100.0% | yes |
| translated | type:news_reporting | False | True | False | 100.0% | yes |
| translated | type:personnel_changes | False | True | False | 100.0% | yes |
| translated | us_national_stance | unknown | none | none | 100.0% | yes |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | outcome | context_missing | classified | context_missing | 90.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | sentiment | unknown | neutral | unknown | 90.0% | yes |
| raw | topic:agents_tools | False | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | type:business_finance | False | True | True | 100.0% | yes |
| raw | type:news_reporting | False | True | False | 90.0% | yes |
| raw | type:personnel_changes | False | True | False | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |

## es_15 — deepseek — coverage

[Source](https://x.com/dolarsmallface/status/2105054738710417694); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Reports models lying/hiding task failure. Chinese/US product origin alone is not geopolitics or national sentiment.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 34 | 0 |
| translated | 32 | 30 | 1 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:investigate_claim | True | True | False | 100.0% | yes |
| raw | sentiment | neutral | negative | negative | 100.0% | yes |
| raw | topic:agents_tools | False | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |
| translated | geo:framework | False | False | True | 80.0% | yes |
| translated | geo:nationalism | False | True | True | 90.0% | yes |
| translated | geo:reporting | False | True | False | 80.0% | yes |
| translated | product:complaint | False | False | True | 80.0% | yes |
| translated | sentiment | neutral | negative | negative | 80.0% | yes |
| translated | topic:agents_tools | False | True | True | 90.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 80.0% | yes |
| translated | type:opinions_reactions | False | True | False | 80.0% | yes |
| translated | type:results_analysis | True | True | False | 80.0% | yes |
| translated | us_national_stance | none | none | none | unmeasured | NO |

## es_16 — minimax — coverage

[Source](https://x.com/0xJokker/status/2103525455748100373); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Concrete provider-compatibility question, with detailed saved parent about MiniMax CLI; not a new feature demand.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 36 | 0 |
| translated | 32 | 33 | 1 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 85.0% | yes |
| translated | geo:reporting | False | True | False | 85.0% | yes |
| translated | outcome | classified | classified | context_missing | 80.0% | yes |
| translated | promotion:general | False | True | False | 95.0% | yes |
| translated | sentiment | neutral | mixed | neutral | 70.0% | yes |
| translated | topic:api_developer_surface | True | True | False | 80.0% | yes |
| translated | topic:cost_performance | False | True | False | 80.0% | yes |
| translated | topic:openness_license | True | True | False | 80.0% | yes |
| translated | type:opinions_reactions | False | True | False | 60.0% | yes |
| translated | type:questions_requests | True | True | False | 60.0% | yes |
| translated | us_national_stance | none | none | none | unmeasured | NO |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | mixed | neutral | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |

## es_17 — llama — coverage

[Source](https://x.com/patoroco/status/2104125344055726117); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Spanish me llama means appeals to me in Tesla vehicle comparison; unrelated Meta Llama.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |
| translated | 36 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |
| translated | china_national_stance | unknown | none | None | unmeasured | NO |
| translated | geo:framework | False | False | None | unmeasured | NO |
| translated | geo:nationalism | False | False | None | unmeasured | NO |
| translated | geo:reporting | False | False | None | unmeasured | NO |
| translated | outcome | context_missing | context_missing | None | unmeasured | NO |
| translated | product:bug | False | False | None | unmeasured | NO |
| translated | product:complaint | False | False | None | unmeasured | NO |
| translated | product:ideas_requests | False | False | None | unmeasured | NO |
| translated | product:investigate_claim | False | False | None | unmeasured | NO |
| translated | product:testimonial | False | False | None | unmeasured | NO |
| translated | promotion:crypto | False | False | None | unmeasured | NO |
| translated | promotion:general | False | False | None | unmeasured | NO |
| translated | promotion:scam | False | False | None | unmeasured | NO |
| translated | promotion:spam | False | False | None | unmeasured | NO |
| translated | promotion:unauthorized | False | False | None | unmeasured | NO |
| translated | sentiment | unknown | unknown | None | unmeasured | NO |
| translated | topic:agents_tools | False | False | None | unmeasured | NO |
| translated | topic:api_developer_surface | False | False | None | unmeasured | NO |
| translated | topic:cost_performance | False | False | None | unmeasured | NO |
| translated | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| translated | topic:local_inference | False | False | None | unmeasured | NO |
| translated | topic:model_distillation | False | False | None | unmeasured | NO |
| translated | topic:openness_license | False | False | None | unmeasured | NO |
| translated | type:advertising_marketing | False | False | None | unmeasured | NO |
| translated | type:business_finance | False | False | None | unmeasured | NO |
| translated | type:events | False | False | None | unmeasured | NO |
| translated | type:hands_on_usage | False | False | None | unmeasured | NO |
| translated | type:job_listings | False | False | None | unmeasured | NO |
| translated | type:news_reporting | False | False | None | unmeasured | NO |
| translated | type:opinions_reactions | False | False | None | unmeasured | NO |
| translated | type:opportunities | False | False | None | unmeasured | NO |
| translated | type:other | False | False | None | unmeasured | NO |
| translated | type:personnel_changes | False | False | None | unmeasured | NO |
| translated | type:questions_requests | False | False | None | unmeasured | NO |
| translated | type:releases_updates | False | False | None | unmeasured | NO |
| translated | type:research_explanations | False | False | None | unmeasured | NO |
| translated | type:results_analysis | False | False | None | unmeasured | NO |
| translated | us_national_stance | unknown | none | None | unmeasured | NO |

## es_18 — qwen — coverage

[Source](https://x.com/DR_JohnSmith_/status/2104106091751608487); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Qwen best among variants but hangs at harder tasks; concrete failure and mixed customer judgment.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 33 | 0 |
| translated | 33 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:ideas_requests | False | True | False | 100.0% | yes |
| translated | sentiment | mixed | mixed | negative | 90.0% | yes |
| translated | topic:cost_performance | False | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | True | False | 100.0% | yes |
| translated | topic:local_inference | False | True | True | 90.0% | yes |
| translated | type:hands_on_usage | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | True | True | False | 100.0% | yes |
| translated | type:results_analysis | True | True | False | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:complaint | True | True | False | 100.0% | yes |
| raw | sentiment | mixed | mixed | negative | 100.0% | yes |
| raw | topic:cost_performance | False | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | True | False | 100.0% | yes |
| raw | topic:local_inference | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |

## es_19 — deepseek — coverage

[Source](https://x.com/Legnatbird/status/2104555313730932820); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Wants better DeepSeek usage allowance in unnamed provider plan. Provider pricing criticism does not prove negative model sentiment/complaint.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 0 | 38 |
| translated | 33 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | False | None | unmeasured | NO |
| raw | geo:reporting | False | False | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | True | None | unmeasured | NO |
| raw | product:ideas_requests | True | True | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | False | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | neutral | negative | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | True | None | unmeasured | NO |
| raw | topic:cost_performance | True | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | True | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | True | True | None | unmeasured | NO |
| raw | type:releases_updates | False | True | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |
| translated | china_national_stance | none | none | None | unmeasured | NO |
| translated | geo:framework | False | True | None | unmeasured | NO |
| translated | geo:nationalism | False | False | None | unmeasured | NO |
| translated | geo:reporting | False | True | None | unmeasured | NO |
| translated | outcome | classified | classified | None | unmeasured | NO |
| translated | product:bug | False | False | None | unmeasured | NO |
| translated | product:complaint | False | True | None | unmeasured | NO |
| translated | product:ideas_requests | True | True | None | unmeasured | NO |
| translated | product:investigate_claim | False | False | None | unmeasured | NO |
| translated | product:testimonial | False | False | None | unmeasured | NO |
| translated | promotion:crypto | False | False | None | unmeasured | NO |
| translated | promotion:general | False | False | None | unmeasured | NO |
| translated | promotion:scam | False | False | None | unmeasured | NO |
| translated | promotion:spam | False | False | None | unmeasured | NO |
| translated | promotion:unauthorized | False | False | None | unmeasured | NO |
| translated | sentiment | neutral | positive | None | unmeasured | NO |
| translated | topic:agents_tools | False | False | None | unmeasured | NO |
| translated | topic:api_developer_surface | False | True | None | unmeasured | NO |
| translated | topic:cost_performance | True | True | None | unmeasured | NO |
| translated | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| translated | topic:local_inference | False | False | None | unmeasured | NO |
| translated | topic:model_distillation | False | False | None | unmeasured | NO |
| translated | topic:openness_license | False | False | None | unmeasured | NO |
| translated | type:advertising_marketing | False | False | None | unmeasured | NO |
| translated | type:business_finance | False | False | None | unmeasured | NO |
| translated | type:events | False | False | None | unmeasured | NO |
| translated | type:hands_on_usage | False | False | None | unmeasured | NO |
| translated | type:job_listings | False | False | None | unmeasured | NO |
| translated | type:news_reporting | False | False | None | unmeasured | NO |
| translated | type:opinions_reactions | True | True | None | unmeasured | NO |
| translated | type:opportunities | False | False | None | unmeasured | NO |
| translated | type:other | False | False | None | unmeasured | NO |
| translated | type:personnel_changes | False | False | None | unmeasured | NO |
| translated | type:questions_requests | True | True | None | unmeasured | NO |
| translated | type:releases_updates | False | False | None | unmeasured | NO |
| translated | type:research_explanations | False | False | None | unmeasured | NO |
| translated | type:results_analysis | False | False | None | unmeasured | NO |
| translated | us_national_stance | none | none | None | unmeasured | NO |

## es_20 — deepseek — coverage

[Source](https://x.com/Alec0Torres/status/2105118835195961663); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-es.md).

Frozen rationale: Paid for DeepSeek; unseen reaction media cannot establish approval, complaint or output quality.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 34 | 0 |
| translated | 34 | 34 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | product:complaint | False | False | True | 100.0% | yes |
| translated | sentiment | neutral | unknown | negative | 100.0% | yes |
| translated | type:hands_on_usage | True | False | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | True | 100.0% | yes |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | outcome | classified | classified | context_missing | 100.0% | yes |
| raw | sentiment | neutral | unknown | unknown | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |

## tr_01 — deepseek — natural

[Source](https://x.com/dragonomi_ai/status/2085391573672427937); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Funding target and valuation report; yuan currency does not establish geopolitical meaning.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 38 | 34 | 2 |
| translated | 36 | 38 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | none | unmeasured | NO |
| raw | geo:framework | False | False | True | 90.0% | yes |
| raw | geo:reporting | False | False | True | 90.0% | yes |
| raw | us_national_stance | none | none | none | unmeasured | NO |
| translated | geo:framework | False | True | False | 90.0% | yes |
| translated | geo:reporting | False | True | False | 90.0% | yes |

## tr_02 — deepseek — natural

[Source](https://x.com/berattunca1/status/2090599728157249590); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Training-token quantities, not an actual performance evaluation or author's model use.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | topic:cost_performance | False | False | True | 80.0% | yes |
| raw | type:opinions_reactions | False | True | False | 80.0% | yes |

## tr_03 — minimax — natural

[Source](https://x.com/robink78/status/2090827157593305387); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: MiniMax desktop failed for two days; irrelevant Gemini troubleshooting is not MiniMax technical truth.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 35 | 1 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | geo:reporting | False | True | False | 90.0% | yes |
| raw | product:bug | True | True | False | 50.0% | NO |
| raw | topic:api_developer_surface | False | True | False | 100.0% | yes |
| raw | topic:local_inference | False | True | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:questions_requests | False | True | False | 100.0% | yes |
| raw | type:results_analysis | False | True | False | 100.0% | yes |

## tr_04 — deepseek — natural

[Source](https://x.com/Nuvemmag/status/2092341276557394305); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Attributed Chinese-state-linked hacking and doubled attack volume; no author national hostility. Publisher link is a separate news promotion.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 31 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | None | unmeasured | NO |
| raw | geo:framework | False | True | None | unmeasured | NO |
| raw | geo:nationalism | False | True | None | unmeasured | NO |
| raw | geo:reporting | True | True | None | unmeasured | NO |
| raw | outcome | classified | classified | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | True | True | None | unmeasured | NO |
| raw | product:testimonial | False | False | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | True | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | neutral | negative | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | True | True | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | True | True | None | unmeasured | NO |
| raw | type:opinions_reactions | False | True | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | True | False | None | unmeasured | NO |
| raw | type:results_analysis | True | False | None | unmeasured | NO |
| raw | us_national_stance | none | none | None | unmeasured | NO |

## tr_05 — deepseek — natural

[Source](https://x.com/Eofdred/status/2090915586184519870); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Describes useful DeepSeek willingness versus Western-provider licensing restrictions; nationality grouping alone insufficient for adopted national stance.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | False | False | 100.0% | yes |

## tr_06 — moonshot_kimi — natural

[Source](https://x.com/oguzcun/status/2068611963848905033); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Turkish kimi means whom; political opinion unrelated to Moonshot Kimi.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 0 | 38 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | None | unmeasured | NO |
| raw | geo:framework | False | False | None | unmeasured | NO |
| raw | geo:nationalism | False | True | None | unmeasured | NO |
| raw | geo:reporting | False | False | None | unmeasured | NO |
| raw | outcome | context_missing | context_missing | None | unmeasured | NO |
| raw | product:bug | False | False | None | unmeasured | NO |
| raw | product:complaint | False | False | None | unmeasured | NO |
| raw | product:ideas_requests | False | False | None | unmeasured | NO |
| raw | product:investigate_claim | False | False | None | unmeasured | NO |
| raw | product:testimonial | False | False | None | unmeasured | NO |
| raw | promotion:crypto | False | False | None | unmeasured | NO |
| raw | promotion:general | False | False | None | unmeasured | NO |
| raw | promotion:scam | False | False | None | unmeasured | NO |
| raw | promotion:spam | False | False | None | unmeasured | NO |
| raw | promotion:unauthorized | False | False | None | unmeasured | NO |
| raw | sentiment | unknown | unknown | None | unmeasured | NO |
| raw | topic:agents_tools | False | False | None | unmeasured | NO |
| raw | topic:api_developer_surface | False | False | None | unmeasured | NO |
| raw | topic:cost_performance | False | False | None | unmeasured | NO |
| raw | topic:evals_benchmarks | False | False | None | unmeasured | NO |
| raw | topic:local_inference | False | False | None | unmeasured | NO |
| raw | topic:model_distillation | False | False | None | unmeasured | NO |
| raw | topic:openness_license | False | False | None | unmeasured | NO |
| raw | type:advertising_marketing | False | False | None | unmeasured | NO |
| raw | type:business_finance | False | False | None | unmeasured | NO |
| raw | type:events | False | False | None | unmeasured | NO |
| raw | type:hands_on_usage | False | False | None | unmeasured | NO |
| raw | type:job_listings | False | False | None | unmeasured | NO |
| raw | type:news_reporting | False | False | None | unmeasured | NO |
| raw | type:opinions_reactions | False | False | None | unmeasured | NO |
| raw | type:opportunities | False | False | None | unmeasured | NO |
| raw | type:other | False | False | None | unmeasured | NO |
| raw | type:personnel_changes | False | False | None | unmeasured | NO |
| raw | type:questions_requests | False | False | None | unmeasured | NO |
| raw | type:releases_updates | False | False | None | unmeasured | NO |
| raw | type:research_explanations | False | False | None | unmeasured | NO |
| raw | type:results_analysis | False | False | None | unmeasured | NO |
| raw | us_national_stance | unknown | none | None | unmeasured | NO |

## tr_07 — moonshot_kimi — natural

[Source](https://x.com/SauronAbi/status/2068751929107198091); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Turkish kimi/kimisi means some; racist-society remark unrelated to Moonshot Kimi and cannot give Kimi a geo tag.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |

## tr_08 — deepseek — natural

[Source](https://x.com/0xbo79/status/2090832112366538784); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Vision API release and attributed comparison plus try-today invitation, with explicit vendor-benchmark caveat.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | topic:agents_tools | True | True | False | 100.0% | yes |
| raw | topic:api_developer_surface | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | True | False | False | 100.0% | yes |
| raw | type:news_reporting | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | True | True | False | 100.0% | yes |
| raw | type:opportunities | False | True | False | 100.0% | yes |

## tr_09 — minimax — natural

[Source](https://x.com/aiproducers/status/2085657949033083095); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Quoted joint Luma/MiniMax offering with direct CTA; explicit branded co-promotion, not merely a backend-list prize.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |
| translated | 36 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | type:advertising_marketing | True | True | False | 100.0% | yes |
| raw | type:news_reporting | True | False | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | promotion:general | True | True | False | 100.0% | yes |
| translated | topic:agents_tools | True | True | False | 100.0% | yes |
| translated | type:news_reporting | True | True | False | 100.0% | yes |

## tr_10 — qwen — natural

[Source](https://x.com/kahpeadam31/status/2089729529178673380); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Says uncensored Qwen should be banned but thanks for doctor recommendation; irony cannot be resolved from unseen media.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | none | none | anti | 70.0% | yes |
| raw | geo:framework | False | True | False | 90.0% | yes |
| raw | product:complaint | False | False | True | 80.0% | yes |
| raw | sentiment | mixed | negative | negative | 90.0% | yes |
| raw | type:questions_requests | False | True | False | 90.0% | yes |

## tr_12 — moonshot_kimi — natural

[Source](https://x.com/piskopos1903/status/2068989747888837064); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Political insult and Turkish kimi keyword collision; unrelated Moonshot Kimi.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |

## tr_13 — yi — coverage

[Source](https://x.com/SnowballAlphaX/status/2105143897093538212); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Turkish suffix yi inside Morpho report is not 01.AI Yi. Balanced financial/technical analysis is not automatically crypto promotion.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 35 | 0 |
| translated | 33 | 35 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | china_national_stance | unknown | none | none | 100.0% | yes |
| raw | promotion:crypto | False | True | True | 100.0% | yes |
| raw | promotion:spam | False | True | False | 100.0% | yes |
| raw | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | us_national_stance | unknown | none | none | 100.0% | yes |
| translated | china_national_stance | unknown | none | none | 100.0% | yes |
| translated | promotion:crypto | False | True | True | 100.0% | yes |
| translated | promotion:spam | False | True | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| translated | us_national_stance | unknown | none | none | 100.0% | yes |

## tr_14 — deepseek — coverage

[Source](https://x.com/ersinkoc/status/2103566802970460365); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: OpenCode subscription pitch, with independently favorable DeepSeek descriptor. Other provider's CTA does not transfer.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 36 | 34 | 0 |
| translated | 36 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | promotion:general | True | True | False | 100.0% | yes |
| translated | promotion:unauthorized | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:testimonial | True | True | False | 100.0% | yes |
| raw | promotion:general | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | type:releases_updates | False | True | True | 100.0% | yes |

## tr_15 — qwen — coverage

[Source](https://x.com/KaanBahsi/status/2104141893483266390); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Explicit CPU TTS experiment and methods, qualified speed/quality observation; no NVIDIA hardware assumption.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 34 | 35 | 0 |
| translated | 34 | 4 | 34 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:openness_license | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | type:research_explanations | True | True | False | 100.0% | yes |
| raw | type:results_analysis | True | True | False | 100.0% | yes |
| translated | geo:framework | False | True | false | unmeasured | NO |
| translated | geo:nationalism | False | False | false | unmeasured | NO |
| translated | geo:reporting | False | True | false | unmeasured | NO |
| translated | product:bug | False | False | false | unmeasured | NO |
| translated | product:complaint | False | False | false | unmeasured | NO |
| translated | product:ideas_requests | False | False | false | unmeasured | NO |
| translated | product:investigate_claim | False | False | false | unmeasured | NO |
| translated | product:testimonial | False | False | false | unmeasured | NO |
| translated | promotion:crypto | False | False | false | unmeasured | NO |
| translated | promotion:general | False | False | false | unmeasured | NO |
| translated | promotion:scam | False | False | false | unmeasured | NO |
| translated | promotion:spam | False | False | false | unmeasured | NO |
| translated | promotion:unauthorized | False | False | false | unmeasured | NO |
| translated | topic:agents_tools | False | False | false | unmeasured | NO |
| translated | topic:api_developer_surface | False | False | false | unmeasured | NO |
| translated | topic:cost_performance | True | True | false | unmeasured | NO |
| translated | topic:evals_benchmarks | False | False | false | unmeasured | NO |
| translated | topic:local_inference | True | True | true | unmeasured | NO |
| translated | topic:model_distillation | False | False | false | unmeasured | NO |
| translated | topic:openness_license | False | True | false | unmeasured | NO |
| translated | type:advertising_marketing | False | False | false | unmeasured | NO |
| translated | type:business_finance | False | False | false | unmeasured | NO |
| translated | type:events | False | False | false | unmeasured | NO |
| translated | type:hands_on_usage | True | True | true | unmeasured | NO |
| translated | type:job_listings | False | False | false | unmeasured | NO |
| translated | type:news_reporting | False | False | false | unmeasured | NO |
| translated | type:opinions_reactions | False | True | false | unmeasured | NO |
| translated | type:opportunities | False | False | false | unmeasured | NO |
| translated | type:other | False | False | false | unmeasured | NO |
| translated | type:personnel_changes | False | False | false | unmeasured | NO |
| translated | type:questions_requests | False | False | false | unmeasured | NO |
| translated | type:releases_updates | False | False | false | unmeasured | NO |
| translated | type:research_explanations | True | True | false | unmeasured | NO |
| translated | type:results_analysis | True | True | false | unmeasured | NO |

## tr_16 — deepseek — coverage

[Source](https://x.com/morphysw/status/2105010970028343397); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Adopted copying/distillation allegation tied to entry/training cost; company allegation has no national framing.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |
| translated | 37 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | type:business_finance | True | False | False | 100.0% | yes |
| raw | geo:framework | False | True | True | 100.0% | yes |
| raw | topic:cost_performance | True | False | False | 100.0% | yes |
| raw | type:business_finance | True | False | False | 100.0% | yes |

## tr_17 — hunyuan — coverage

[Source](https://x.com/CihadTurhan/status/2103991937531511073); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Asks RAM needs and result quality; no actual benchmark result or request for a new capability.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 33 | 37 | 0 |
| translated | 33 | 37 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:reporting | False | True | False | 100.0% | yes |
| raw | product:ideas_requests | False | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:local_inference | False | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:reporting | False | True | False | 100.0% | yes |
| translated | product:ideas_requests | False | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | topic:local_inference | False | True | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |

## tr_18 — mistral — coverage

[Source](https://x.com/LotraHaber/status/2103784072757510238); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Attributes European AI autonomy argument to CEO; neutral report does not adopt CEO's national sentiment.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 35 | 0 |
| translated | 35 | 36 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | geo:nationalism | False | True | False | 100.0% | yes |
| translated | sentiment | neutral | positive | neutral | 100.0% | yes |
| translated | topic:openness_license | True | True | False | 100.0% | yes |
| translated | type:business_finance | True | True | False | 100.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| raw | geo:nationalism | False | True | False | 100.0% | yes |
| raw | sentiment | neutral | positive | positive | 100.0% | yes |
| raw | topic:openness_license | True | True | False | 100.0% | yes |
| raw | type:business_finance | True | True | False | 100.0% | yes |
| raw | type:opinions_reactions | False | True | False | 100.0% | yes |

## tr_19 — deepseek — coverage

[Source](https://x.com/ZerefDragneell2/status/2105017603802407095); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Explicit generalization about Chinese-origin models; evaluates national-origin product group, not China/US country itself. Marked sensitivity case.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 35 | 33 | 0 |
| translated | 35 | 32 | 0 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| raw | geo:framework | False | True | False | 100.0% | yes |
| raw | geo:nationalism | True | False | False | 100.0% | yes |
| raw | product:complaint | True | True | False | 100.0% | yes |
| raw | topic:cost_performance | True | True | False | 100.0% | yes |
| raw | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| raw | type:hands_on_usage | True | True | False | 100.0% | yes |
| translated | geo:framework | False | True | False | 100.0% | yes |
| translated | geo:nationalism | True | False | False | 100.0% | yes |
| translated | product:complaint | True | True | False | 100.0% | yes |
| translated | topic:cost_performance | True | True | False | 100.0% | yes |
| translated | topic:evals_benchmarks | True | False | False | 100.0% | yes |
| translated | type:hands_on_usage | True | True | False | 100.0% | yes |
| translated | type:results_analysis | True | True | False | 100.0% | yes |

## tr_20 — deepseek — coverage

[Source](https://x.com/yapaymeraklisi/status/2104182137700106446); [verbatim packet](../2026-09-30-070427-jev-multilingual-classification/review-tr.md).

Frozen rationale: Reports sandbox-throughput number and preprint caveat; no substantive mechanism or firsthand experiment.

| Arm | Jev matching fields | 0731 matching fields | 0731 invalid |
| --- | --- | --- | --- |
| raw | 32 | 33 | 2 |
| translated | 32 | 34 | 1 |

| Arm | Field | Reference | Jev | 0731 | 0731 selected probability | 0731 valid |
| --- | --- | --- | --- | --- | --- | --- |
| translated | china_national_stance | none | none | unknown | 30.0% | NO |
| translated | geo:framework | False | True | False | 90.0% | yes |
| translated | geo:reporting | False | True | True | 90.0% | yes |
| translated | type:opinions_reactions | False | True | False | 100.0% | yes |
| translated | type:releases_updates | False | True | False | 100.0% | yes |
| translated | type:research_explanations | False | True | True | 90.0% | yes |
| translated | type:results_analysis | True | False | False | 90.0% | yes |
| raw | china_national_stance | none | none | none | unmeasured | NO |
| raw | geo:framework | False | True | False | 80.0% | yes |
| raw | topic:agents_tools | True | True | False | 80.0% | yes |
| raw | topic:api_developer_surface | False | True | False | 90.0% | yes |
| raw | type:advertising_marketing | False | True | False | 90.0% | yes |
| raw | type:opinions_reactions | False | True | False | 80.0% | yes |
| raw | type:releases_updates | False | True | True | 80.0% | yes |
| raw | type:results_analysis | True | False | False | 90.0% | yes |
| raw | us_national_stance | none | none | none | unmeasured | NO |
