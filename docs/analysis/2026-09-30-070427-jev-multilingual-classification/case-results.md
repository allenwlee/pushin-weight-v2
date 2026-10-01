# Per-case Jev results against frozen source review

Reference judgments are not independent human ground truth. Every mismatch is preserved, including contestable boundaries.

## ja_01 — deepseek — natural

[Source post](https://x.com/3K1/status/2098963821369217086); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Stored quotation explicitly ran DeepSeek; measured throughput; encouragement is product/local feasibility, not nation.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 31/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 51.0% |
| raw | type:research_explanations | False | True | 83.0% |
| raw | type:news_reporting | True | False | 84.0% |
| raw | topic:evals_benchmarks | True | False | 51.0% |
| raw | topic:api_developer_surface | False | True | 53.0% |
| raw | geo:reporting | False | True | 63.0% |
| raw | geo:framework | False | True | 74.0% |
| translated | type:releases_updates | False | True | 51.0% |
| translated | type:research_explanations | False | True | 84.0% |
| translated | type:news_reporting | True | False | 78.0% |
| translated | geo:reporting | False | True | 63.0% |
| translated | geo:framework | False | True | 78.0% |

## ja_02 — minimax — natural

[Source post](https://x.com/aidoga_lab/status/2091712099395461388); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Credits the tool used to generate a movie; not a MiniMax launch or explicit pitch.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | geo:reporting | False | True | 63.0% |
| translated | geo:framework | False | True | 72.0% |
| translated | promotion:general | False | True | 66.0% |
| raw | geo:reporting | False | True | 57.0% |
| raw | geo:framework | False | True | 56.0% |
| raw | promotion:general | False | True | 63.0% |

## ja_03 — deepseek — natural

[Source post](https://x.com/connect24h/status/2102595739474174316); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Reports malware using several LLMs; do not adopt malware actor's actions as author's firsthand usage or geopolitical claim.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:api_developer_surface | True | False | 52.0% |
| raw | sentiment | neutral | negative | 42.0% |
| raw | geo:framework | False | True | 55.0% |
| translated | type:research_explanations | True | False | 52.0% |
| translated | geo:reporting | False | True | 50.0% |
| translated | geo:framework | False | True | 55.0% |

## ja_04 — deepseek — natural

[Source post](https://x.com/mt_pb_ai/status/2085522812295643197); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Explicitly unconfirmed benchmark/pricing report; ordinary benchmark rumor is not investigate_claim under the current definition.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:results_analysis | True | False | 66.0% |
| translated | type:advertising_marketing | False | True | 50.0% |
| translated | type:business_finance | False | True | 52.0% |
| translated | product:testimonial | False | True | 64.0% |
| translated | geo:reporting | False | True | 52.0% |
| translated | geo:framework | False | True | 68.0% |
| raw | type:results_analysis | True | False | 62.0% |
| raw | type:advertising_marketing | False | True | 51.0% |
| raw | product:testimonial | False | True | 67.0% |
| raw | geo:reporting | False | True | 55.0% |
| raw | geo:framework | False | True | 75.0% |

## ja_05 — minimax — natural

[Source post](https://x.com/luche_whitewing/status/2089442141751902272); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Poetic creator output with tool credit; no expressed evaluation of MiniMax itself.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:reporting | False | True | 72.0% |
| raw | geo:framework | False | True | 77.0% |
| raw | promotion:general | False | True | 73.0% |
| raw | promotion:spam | False | True | 55.0% |
| raw | promotion:unauthorized | False | True | 55.0% |

## ja_06 — minimax — natural

[Source post](https://x.com/sidodtv/status/2089299406583726236); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Author observes motion blur quality failure; quality dissatisfaction, not necessarily a concrete software malfunction.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | product:ideas_requests | False | True | 59.0% |
| raw | geo:reporting | False | True | 56.0% |
| raw | geo:framework | False | True | 69.0% |

## ja_07 — minimax — natural

[Source post](https://x.com/kik0ai1jikake/status/2090270568532828380); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Actual comparative generation and costs; praises H3 while still liking the competing model.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:reporting | False | True | 59.0% |
| raw | geo:framework | False | True | 56.0% |
| raw | promotion:general | False | True | 54.0% |

## ja_08 — minimax — natural

[Source post](https://x.com/javawock7618/status/2090439924332032347); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Updates an H3 workflow with measured directional quality and a described frame-range technique.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:reporting | False | True | 73.0% |
| raw | geo:framework | False | True | 78.0% |

## ja_09 — minimax — natural

[Source post](https://x.com/__su888/status/2087298764583415883); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Third-party implementation results with specific quantization technique; no author's own test asserted.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 31/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 59.0% |
| raw | type:hands_on_usage | False | True | 56.0% |
| raw | type:news_reporting | True | False | 52.0% |
| raw | topic:openness_license | False | True | 55.0% |
| raw | sentiment | neutral | positive | 66.0% |
| raw | geo:reporting | False | True | 54.0% |
| raw | geo:framework | False | True | 75.0% |
| translated | type:releases_updates | False | True | 62.0% |
| translated | type:news_reporting | True | False | 56.0% |
| translated | sentiment | neutral | positive | 52.0% |
| translated | geo:reporting | False | True | 55.0% |
| translated | geo:framework | False | True | 70.0% |

## ja_10 — minimax — natural

[Source post](https://x.com/To_Vten_ozi/status/2087557406473744443); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Recommends small generation then upscaling from experience; not a service sales pitch.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 52.0% |
| raw | product:testimonial | True | False | 63.0% |
| raw | product:ideas_requests | False | True | 52.0% |
| raw | sentiment | positive | mixed | 43.0% |
| raw | geo:framework | False | True | 54.0% |

## ja_11 — deepseek — natural

[Source post](https://x.com/amano76_SEO/status/2097846114489962944); [verbatim source/translation packet](review-ja.md).

Frozen rationale: DeepSeek-specific part is a sourced government allegation and denial; unrelated OpenAI/Meta launches must not transfer.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 66.0% |
| raw | type:research_explanations | True | False | 82.0% |
| raw | topic:api_developer_surface | True | False | 60.0% |
| raw | sentiment | neutral | negative | 91.0% |
| raw | geo:framework | False | True | 54.0% |
| translated | type:opinions_reactions | False | True | 73.0% |
| translated | type:research_explanations | True | False | 87.0% |
| translated | sentiment | neutral | negative | 84.0% |
| translated | geo:framework | False | True | 55.0% |
| translated | geo:nationalism | False | True | 53.0% |

## ja_12 — minimax — natural

[Source post](https://x.com/toMion818/status/2086784629701521832); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Music-video release promotes the musician's work, not a new MiniMax release; MiniMax is the creation tool.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | sentiment | neutral | positive | 62.0% |
| translated | geo:reporting | False | True | 63.0% |
| translated | geo:framework | False | True | 72.0% |
| translated | promotion:general | True | False | 57.0% |
| raw | sentiment | neutral | positive | 63.0% |
| raw | geo:reporting | False | True | 70.0% |
| raw | geo:framework | False | True | 77.0% |
| raw | promotion:general | True | False | 54.0% |

## ja_13 — llama — coverage

[Source post](https://x.com/ai_hakase_/status/2103244089747554662); [verbatim source/translation packet](review-ja.md).

Frozen rationale: llama.cpp runtime bug is not evidence about Meta Llama models; the catalog target is Meta Llama.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 25/38 | 0 |
| translated | 26/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | context_missing | classified | 85.0% |
| raw | type:hands_on_usage | False | True | 54.0% |
| raw | type:results_analysis | False | True | 59.0% |
| raw | type:opinions_reactions | False | True | 62.0% |
| raw | type:research_explanations | False | True | 86.0% |
| raw | topic:local_inference | False | True | 93.0% |
| raw | topic:api_developer_surface | False | True | 73.0% |
| raw | product:complaint | False | True | 70.0% |
| raw | sentiment | unknown | negative | 50.0% |
| raw | geo:reporting | False | True | 68.0% |
| raw | geo:framework | False | True | 76.0% |
| raw | china_national_stance | unknown | none | 94.0% |
| raw | us_national_stance | unknown | none | 93.0% |
| translated | outcome | context_missing | classified | 73.0% |
| translated | type:results_analysis | False | True | 66.0% |
| translated | type:opinions_reactions | False | True | 56.0% |
| translated | type:research_explanations | False | True | 76.0% |
| translated | topic:local_inference | False | True | 87.0% |
| translated | topic:api_developer_surface | False | True | 62.0% |
| translated | product:complaint | False | True | 61.0% |
| translated | sentiment | unknown | negative | 56.0% |
| translated | geo:reporting | False | True | 62.0% |
| translated | geo:framework | False | True | 68.0% |
| translated | china_national_stance | unknown | none | 92.0% |
| translated | us_national_stance | unknown | none | 93.0% |

## ja_14 — minimax — coverage

[Source post](https://x.com/KimiAI_Studio/status/2102422720931844486); [verbatim source/translation packet](review-ja.md).

Frozen rationale: MiniMax CLI launch, reported performance, technical architecture and strong endorsement; no firsthand run stated.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:advertising_marketing | False | True | 77.0% |
| translated | geo:reporting | False | True | 60.0% |
| translated | geo:framework | False | True | 67.0% |
| translated | promotion:general | False | True | 63.0% |
| raw | type:advertising_marketing | False | True | 82.0% |
| raw | geo:reporting | False | True | 68.0% |
| raw | geo:framework | False | True | 77.0% |
| raw | geo:nationalism | False | True | 50.0% |
| raw | promotion:general | False | True | 52.0% |

## ja_15 — sakana_ai — coverage

[Source post](https://x.com/SakanaAILabs/status/2104928895627833438); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Specific official vacancy/application link. Delivering Japan-origin AI globally is not by itself national superiority or geopolitical framing.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:advertising_marketing | False | True | 90.0% |
| raw | type:opportunities | False | True | 85.0% |
| raw | sentiment | neutral | positive | 64.0% |
| raw | geo:framework | False | True | 57.0% |
| translated | type:advertising_marketing | False | True | 93.0% |
| translated | type:opportunities | False | True | 87.0% |
| translated | type:business_finance | False | True | 54.0% |
| translated | sentiment | neutral | positive | 52.0% |
| translated | geo:reporting | False | True | 50.0% |
| translated | geo:framework | False | True | 62.0% |

## ja_16 — mistral — coverage

[Source post](https://x.com/iwashi86/status/2105142699661652363); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Explicit support because company is European plus competitive national comparison; China/US leadership is descriptive, not adopted praise/hostility.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:business_finance | True | False | 64.0% |
| translated | product:testimonial | False | True | 54.0% |
| raw | type:business_finance | True | False | 71.0% |
| raw | product:testimonial | False | True | 50.0% |

## ja_17 — qwen — coverage

[Source post](https://x.com/HAI_h_jp/status/2104489492614942827); [verbatim source/translation packet](review-ja.md).

Frozen rationale: HAI service availability/price involving Qwen; HAI owns the pitch. Not Qwen-owned advertising.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:advertising_marketing | False | True | 50.0% |
| raw | type:opportunities | False | True | 60.0% |
| raw | type:news_reporting | True | False | 82.0% |
| raw | topic:api_developer_surface | True | False | 82.0% |
| raw | geo:reporting | False | True | 55.0% |
| raw | geo:framework | False | True | 51.0% |
| translated | type:advertising_marketing | False | True | 50.0% |
| translated | type:opportunities | False | True | 55.0% |
| translated | type:news_reporting | True | False | 78.0% |
| translated | topic:api_developer_surface | True | False | 66.0% |
| translated | geo:reporting | False | True | 52.0% |

## ja_18 — minimax — coverage

[Source post](https://x.com/HuurainoMoutoku/status/2103649257026904529); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Quote explicitly co-promotes MiniMax x SeaArt challenge/prize; author's complaint concerns SeaArt access, not MiniMax model quality.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 28/38 | 0 |
| translated | 28/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 70.0% |
| translated | type:hands_on_usage | False | True | 69.0% |
| translated | type:opinions_reactions | False | True | 89.0% |
| translated | topic:cost_performance | False | True | 61.0% |
| translated | product:bug | False | True | 56.0% |
| translated | product:complaint | False | True | 81.0% |
| translated | product:ideas_requests | False | True | 61.0% |
| translated | sentiment | neutral | negative | 94.0% |
| translated | geo:reporting | False | True | 63.0% |
| translated | geo:framework | False | True | 78.0% |
| raw | type:releases_updates | False | True | 66.0% |
| raw | type:hands_on_usage | False | True | 60.0% |
| raw | type:opinions_reactions | False | True | 88.0% |
| raw | topic:cost_performance | False | True | 65.0% |
| raw | product:bug | False | True | 51.0% |
| raw | product:complaint | False | True | 81.0% |
| raw | product:ideas_requests | False | True | 61.0% |
| raw | sentiment | neutral | negative | 95.0% |
| raw | geo:reporting | False | True | 60.0% |
| raw | geo:framework | False | True | 74.0% |

## ja_19 — moonshot_kimi — coverage

[Source post](https://x.com/xRINGx/status/2102626239794356686); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Chinese national capability denigrated, plus attributed copying/data-routing allegations. Not customer complaint.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:research_explanations | True | False | 61.0% |
| raw | topic:api_developer_surface | True | False | 85.0% |
| raw | geo:framework | False | True | 58.0% |
| translated | type:research_explanations | True | False | 69.0% |
| translated | topic:api_developer_surface | True | False | 75.0% |
| translated | geo:framework | False | True | 60.0% |
| translated | china_national_stance | anti | none | 45.0% |

## ja_20 — deepseek — coverage

[Source post](https://x.com/mikoto2000/status/2102656351302541457); [verbatim source/translation packet](review-ja.md).

Frozen rationale: Asks concurrency capacity; no firsthand test or requested new feature is established.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:opinions_reactions | False | True | 57.0% |
| translated | topic:local_inference | True | False | 57.0% |
| translated | geo:framework | False | True | 57.0% |
| raw | topic:local_inference | True | False | 76.0% |
| raw | geo:framework | False | True | 66.0% |

## zh_cn_01 — qwen — natural

[Source post](https://x.com/ScarletKc/status/2101132893225656517); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Explains activated versus total MoE parameters using Qwen; rhetorical teaching question is not a support request.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 56.0% |
| raw | geo:reporting | False | True | 60.0% |
| raw | geo:framework | False | True | 79.0% |
| translated | type:opinions_reactions | False | True | 65.0% |
| translated | geo:reporting | False | True | 51.0% |
| translated | geo:framework | False | True | 72.0% |

## zh_cn_02 — minimax — natural

[Source post](https://x.com/wugudehaore/status/2098964592680731131); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Valuation, free float, unlock and bearish investment view; no customer complaint.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:news_reporting | True | False | 64.0% |
| translated | geo:reporting | False | True | 59.0% |
| translated | geo:framework | False | True | 59.0% |
| raw | type:news_reporting | True | False | 74.0% |
| raw | geo:reporting | False | True | 51.0% |
| raw | geo:framework | False | True | 51.0% |

## zh_cn_03 — deepseek — natural

[Source post](https://x.com/vintcessun/status/2095452004709732479); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Specific DeepSeek benchmark improvement and training/verification explanation; not evidence the author ran it.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:news_reporting | True | False | 57.0% |
| raw | geo:reporting | False | True | 50.0% |
| raw | geo:framework | False | True | 63.0% |
| translated | type:news_reporting | True | False | 60.0% |
| translated | sentiment | positive | mixed | 54.0% |
| translated | geo:reporting | False | True | 60.0% |
| translated | geo:framework | False | True | 70.0% |

## zh_cn_04 — dots — natural

[Source post](https://x.com/realfxw/status/2101120516278849859); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: LightOnOCR is pitched; dots.ocr appears only as a speed comparison foil. Do not transfer competitor license/features.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:opinions_reactions | False | True | 67.0% |
| translated | type:news_reporting | True | False | 73.0% |
| raw | type:opinions_reactions | False | True | 69.0% |
| raw | type:news_reporting | True | False | 70.0% |

## zh_cn_05 — minimax — natural

[Source post](https://x.com/HueReasonegfo9/status/2096131230765105161); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Adult-product seller, unrelated Hailuo keyword collision. An ad alone is not repeated spam evidence.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |
| translated | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 72.0% |
| raw | us_national_stance | unknown | none | 68.0% |
| raw | promotion:general | True | False | 80.0% |
| raw | promotion:spam | False | True | 74.0% |
| raw | promotion:scam | False | True | 75.0% |
| raw | promotion:unauthorized | False | True | 71.0% |
| translated | china_national_stance | unknown | none | 72.0% |
| translated | us_national_stance | unknown | none | 75.0% |
| translated | promotion:general | True | False | 81.0% |
| translated | promotion:spam | False | True | 74.0% |
| translated | promotion:scam | False | True | 72.0% |
| translated | promotion:unauthorized | False | True | 68.0% |

## zh_cn_06 — minimax — natural

[Source post](https://x.com/ekll01/status/2085587083029356715); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Plugin compatibility dissatisfaction, without explicit firsthand use or confirmed software malfunction.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 61.0% |
| translated | topic:api_developer_surface | False | True | 79.0% |
| translated | geo:framework | False | True | 54.0% |
| raw | type:releases_updates | False | True | 54.0% |
| raw | topic:api_developer_surface | False | True | 79.0% |
| raw | geo:framework | False | True | 59.0% |

## zh_cn_07 — deepseek — natural

[Source post](https://x.com/YishaoRice/status/2094993005170286811); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: DeepSeek cost comparison in monetization/industry analysis; country origin is incidental, not political evaluation.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 31/38 | 0 |
| translated | 30/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 59.0% |
| raw | type:results_analysis | True | False | 53.0% |
| raw | type:research_explanations | True | False | 71.0% |
| raw | type:business_finance | True | False | 61.0% |
| raw | topic:evals_benchmarks | True | False | 72.0% |
| raw | topic:openness_license | True | False | 66.0% |
| raw | sentiment | positive | neutral | 44.0% |
| translated | outcome | classified | context_missing | 68.0% |
| translated | type:results_analysis | True | False | 54.0% |
| translated | type:research_explanations | True | False | 65.0% |
| translated | type:business_finance | True | False | 62.0% |
| translated | topic:evals_benchmarks | True | False | 74.0% |
| translated | topic:openness_license | True | False | 56.0% |
| translated | topic:api_developer_surface | False | True | 55.0% |
| translated | sentiment | positive | neutral | 41.0% |

## zh_cn_08 — deepseek — natural

[Source post](https://x.com/LShanrenM/status/2086763159180959889); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Criticizes the Chinese state-capital investment system; not a product malfunction. Stance intensity is separately flagged for sensitivity.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:framework | True | False | 52.0% |
| raw | geo:nationalism | True | False | 60.0% |
| raw | china_national_stance | anti | none | 68.0% |

## zh_cn_09 — deepseek — natural

[Source post](https://x.com/yabarich/status/2094358567365300351); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: B.AI infrastructure pitch with DeepSeek as supported backend; no new target-model release or target-owned CTA.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |
| translated | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 65.0% |
| raw | type:news_reporting | True | False | 76.0% |
| raw | topic:cost_performance | False | True | 66.0% |
| raw | sentiment | neutral | unknown | 47.0% |
| raw | promotion:crypto | False | True | 71.0% |
| raw | promotion:unauthorized | False | True | 54.0% |
| translated | outcome | classified | context_missing | 60.0% |
| translated | type:news_reporting | True | False | 78.0% |
| translated | topic:cost_performance | False | True | 54.0% |
| translated | sentiment | neutral | unknown | 39.0% |
| translated | promotion:general | True | False | 59.0% |
| translated | promotion:crypto | False | True | 80.0% |
| translated | promotion:unauthorized | False | True | 66.0% |

## zh_cn_10 — minimax — natural

[Source post](https://x.com/zuz84093219/status/2104885840367538431); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Anticipates a forthcoming update without naming a concrete changed capability; not a completed launch.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 78.0% |
| translated | topic:api_developer_surface | False | True | 51.0% |
| translated | geo:reporting | False | True | 51.0% |
| translated | geo:framework | False | True | 60.0% |
| raw | type:releases_updates | False | True | 73.0% |
| raw | geo:reporting | False | True | 51.0% |
| raw | geo:framework | False | True | 51.0% |

## zh_cn_11 — doubao — natural

[Source post](https://x.com/cy_xiaozhu/status/2100457097158885603); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Product quality comparison endorses Doubao; does not explicitly state a firsthand test.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 72.0% |
| raw | topic:evals_benchmarks | True | False | 60.0% |
| raw | geo:reporting | False | True | 57.0% |
| raw | geo:framework | False | True | 70.0% |
| translated | type:results_analysis | True | False | 58.0% |
| translated | topic:evals_benchmarks | True | False | 58.0% |
| translated | geo:reporting | False | True | 53.0% |
| translated | geo:framework | False | True | 63.0% |

## zh_cn_12 — excluded before inference

See reference_rows.json for the source-language mismatch.

## zh_cn_13 — mimo — coverage

[Source post](https://x.com/0xLogicrw/status/2104479508019745100); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Detailed repetition bug diagnosis, training remedy and release; no author customer complaint.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 54.0% |
| raw | topic:model_distillation | True | False | 84.0% |
| raw | sentiment | neutral | mixed | 71.0% |
| raw | geo:reporting | False | True | 76.0% |
| raw | geo:framework | False | True | 81.0% |
| translated | type:advertising_marketing | False | True | 59.0% |
| translated | type:opinions_reactions | False | True | 54.0% |
| translated | topic:model_distillation | True | False | 85.0% |
| translated | sentiment | neutral | mixed | 66.0% |
| translated | geo:reporting | False | True | 73.0% |
| translated | geo:framework | False | True | 84.0% |
| translated | geo:nationalism | False | True | 62.0% |

## zh_cn_14 — deepseek — coverage

[Source post](https://x.com/francis_cgl/status/2103775174508061032); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: B.AI limited free access plus explicit TRON ecosystem pitch; DeepSeek service-provider promotion must not transfer. Source contains mixed Chinese scripts.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 27/38 | 0 |
| translated | 28/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 80.0% |
| translated | type:advertising_marketing | False | True | 76.0% |
| translated | type:opinions_reactions | False | True | 73.0% |
| translated | type:news_reporting | True | False | 88.0% |
| translated | topic:agents_tools | False | True | 71.0% |
| translated | sentiment | neutral | positive | 86.0% |
| translated | geo:reporting | False | True | 57.0% |
| translated | geo:framework | False | True | 63.0% |
| translated | promotion:spam | False | True | 77.0% |
| translated | promotion:unauthorized | False | True | 70.0% |
| raw | type:releases_updates | False | True | 80.0% |
| raw | type:advertising_marketing | False | True | 76.0% |
| raw | type:opinions_reactions | False | True | 73.0% |
| raw | type:news_reporting | True | False | 87.0% |
| raw | topic:agents_tools | False | True | 72.0% |
| raw | product:testimonial | False | True | 53.0% |
| raw | sentiment | neutral | positive | 90.0% |
| raw | geo:reporting | False | True | 58.0% |
| raw | geo:framework | False | True | 65.0% |
| raw | promotion:spam | False | True | 72.0% |
| raw | promotion:unauthorized | False | True | 67.0% |

## zh_cn_15 — qwen — coverage

[Source post](https://x.com/Alan_jupiters/status/2101868706532094095); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Explicit Reddit firsthand test quoted/reported, 50 tokens/sec and local dual-card method.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 31/38 | 0 |
| translated | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:news_reporting | True | False | 62.0% |
| raw | topic:evals_benchmarks | True | False | 60.0% |
| raw | topic:openness_license | True | False | 70.0% |
| raw | topic:api_developer_surface | True | False | 73.0% |
| raw | geo:reporting | False | True | 64.0% |
| raw | geo:framework | False | True | 76.0% |
| raw | promotion:general | False | True | 63.0% |
| translated | type:news_reporting | True | False | 60.0% |
| translated | topic:evals_benchmarks | True | False | 52.0% |
| translated | topic:openness_license | True | False | 69.0% |
| translated | topic:api_developer_surface | True | False | 72.0% |
| translated | geo:reporting | False | True | 63.0% |
| translated | geo:framework | False | True | 73.0% |
| translated | promotion:general | False | True | 68.0% |

## zh_cn_16 — deepseek — coverage

[Source post](https://x.com/KhanAIBuilds/status/2103002792021594377); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Explains US model-IP versus Chinese sensitive-data concerns; no adopted national praise/hostility.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:research_explanations | True | False | 86.0% |
| translated | topic:api_developer_surface | True | False | 75.0% |
| translated | sentiment | negative | neutral | 54.0% |
| raw | type:research_explanations | True | False | 87.0% |
| raw | topic:api_developer_surface | True | False | 79.0% |

## zh_cn_17 — ernie — coverage

[Source post](https://x.com/daityn_rucker/status/2102965016924418336); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Repeated promotional keyword stuffing sells posting software/accounts; ERNIE name has no coherent target-brand predicate.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 83.0% |
| raw | us_national_stance | unknown | none | 80.0% |
| raw | promotion:scam | False | True | 71.0% |
| raw | promotion:unauthorized | False | True | 66.0% |
| translated | china_national_stance | unknown | none | 83.0% |
| translated | us_national_stance | unknown | none | 85.0% |
| translated | promotion:scam | False | True | 64.0% |
| translated | promotion:unauthorized | False | True | 61.0% |

## zh_cn_18 — qwen — coverage

[Source post](https://x.com/NFT_Chen/status/2102237798824902873); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Concrete announced Qwen family, conference, quoted formal leadership change and training results. Domestic ranking alone is not nationalism.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:advertising_marketing | False | True | 88.0% |
| translated | topic:agents_tools | True | False | 52.0% |
| translated | geo:reporting | False | True | 56.0% |
| translated | geo:framework | False | True | 68.0% |
| raw | type:advertising_marketing | False | True | 91.0% |
| raw | geo:reporting | False | True | 55.0% |
| raw | geo:framework | False | True | 70.0% |

## zh_cn_19 — mimo — coverage

[Source post](https://x.com/Sigma_ccc/status/2105141166572454356); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: New promotion of a named MiMo leader and model result; admiration of a person does not automatically yield product testimonial.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:hands_on_usage | False | True | 60.0% |
| raw | topic:cost_performance | True | False | 62.0% |
| raw | product:testimonial | False | True | 51.0% |
| raw | geo:framework | False | True | 54.0% |
| translated | product:testimonial | False | True | 52.0% |
| translated | geo:reporting | False | True | 54.0% |

## zh_cn_20 — deepseek — coverage

[Source post](https://x.com/tianyi/status/2104881693706653733); [verbatim source/translation packet](review-zh-cn.md).

Frozen rationale: Explicit team senior-engineer hiring and contactable poster/link; technical report title alone is not a substantive explanation.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:advertising_marketing | False | True | 91.0% |
| translated | type:opportunities | False | True | 78.0% |
| translated | sentiment | neutral | positive | 61.0% |
| translated | geo:reporting | False | True | 52.0% |
| translated | geo:framework | False | True | 75.0% |
| raw | type:advertising_marketing | False | True | 90.0% |
| raw | type:opportunities | False | True | 81.0% |
| raw | sentiment | neutral | positive | 73.0% |
| raw | geo:reporting | False | True | 68.0% |
| raw | geo:framework | False | True | 73.0% |

## ko_01 — deepseek — natural

[Source post](https://x.com/antfeedapp/status/2080523349114106360); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Company strategy, revenue, research structure and attributed China compute constraint. Reported national weakness is not author's adopted nationalism.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 91.0% |
| raw | type:research_explanations | True | False | 53.0% |
| raw | sentiment | neutral | positive | 75.0% |

## ko_02 — deepseek — natural

[Source post](https://x.com/lostland/status/2104541211021525328); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Actual local/API speed comparison; dissatisfaction with missing local multimodality but positive earlier experience.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 82.0% |
| translated | topic:evals_benchmarks | True | False | 63.0% |
| translated | product:bug | False | True | 50.0% |
| translated | geo:reporting | False | True | 55.0% |
| translated | geo:framework | False | True | 68.0% |
| raw | type:releases_updates | False | True | 77.0% |
| raw | topic:evals_benchmarks | True | False | 58.0% |
| raw | product:bug | False | True | 68.0% |
| raw | sentiment | mixed | negative | 53.0% |
| raw | geo:framework | False | True | 55.0% |

## ko_03 — qwen — natural

[Source post](https://x.com/midagedev/status/2097823171068264906); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Explicit Qwen run at 160 tok/s, favorable speed comparison and heat observation.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:research_explanations | False | True | 57.0% |
| raw | topic:evals_benchmarks | True | False | 66.0% |
| raw | product:testimonial | True | False | 53.0% |
| raw | geo:reporting | False | True | 61.0% |
| raw | geo:framework | False | True | 57.0% |
| translated | type:research_explanations | False | True | 58.0% |
| translated | topic:evals_benchmarks | True | False | 59.0% |
| translated | geo:reporting | False | True | 61.0% |
| translated | geo:framework | False | True | 67.0% |

## ko_04 — deepseek — natural

[Source post](https://x.com/pocopoco9876/status/2101277345336463807); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Jev is called faster/cheaper/more accurate than DeepSeek without detailed evidence; a comparison foil is not automatically negative or advertised.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | sentiment | neutral | negative | 78.0% |
| translated | geo:framework | False | True | 54.0% |
| raw | topic:agents_tools | False | True | 59.0% |
| raw | topic:api_developer_surface | False | True | 50.0% |
| raw | sentiment | neutral | negative | 85.0% |
| raw | promotion:general | False | True | 51.0% |

## ko_05 — deepseek — natural

[Source post](https://x.com/ilpyung98/status/2085941962327437459); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Long token-market report mentions DeepSeek only as an AgentKeys-supported model. Do not transfer unrelated crypto finance or risk reporting to DeepSeek.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 77.0% |
| raw | type:releases_updates | True | False | 53.0% |
| raw | type:news_reporting | True | False | 76.0% |
| raw | promotion:crypto | False | True | 69.0% |

## ko_06 — qwen — natural

[Source post](https://x.com/Jinnissive/status/2084102241221517450); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Excited Korean reaction plus official Qwen launch/CTA and specific reported agent outputs in quote. English quote means this is not Korean-only evidence.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 90.0% |
| raw | type:opportunities | False | True | 51.0% |
| raw | geo:reporting | False | True | 59.0% |
| raw | geo:framework | False | True | 74.0% |

## ko_07 — qwen — natural

[Source post](https://x.com/umeume12341/status/2078455321065054291); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Qwen appears only in comparison of fine-tuning ecosystem counts; Gemma-specific techniques/bugs must not transfer.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 84.0% |
| raw | type:news_reporting | True | False | 88.0% |
| raw | sentiment | neutral | unknown | 45.0% |

## ko_08 — deepseek — natural

[Source post](https://x.com/cozybearlog/status/2084596474801782964); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Token-usage ranking and pricing competition; Chinese origin alone does not create geopolitical meaning.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:business_finance | True | False | 60.0% |
| translated | type:news_reporting | True | False | 60.0% |
| translated | topic:api_developer_surface | False | True | 53.0% |
| translated | sentiment | positive | neutral | 58.0% |
| raw | type:business_finance | True | False | 52.0% |
| raw | type:news_reporting | True | False | 57.0% |
| raw | topic:api_developer_surface | False | True | 72.0% |
| raw | sentiment | positive | neutral | 46.0% |
| raw | geo:reporting | False | True | 55.0% |

## ko_09 — deepseek — natural

[Source post](https://x.com/_nodelay/status/2092525849564332104); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Uses DeepSeek but explicitly notes absence of vision and Qwen workaround; product limitation, not concrete malfunction.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 30/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:research_explanations | False | True | 72.0% |
| raw | topic:agents_tools | True | False | 74.0% |
| raw | product:complaint | True | False | 76.0% |
| raw | product:testimonial | False | True | 50.0% |
| raw | product:ideas_requests | True | False | 63.0% |
| raw | sentiment | mixed | positive | 65.0% |
| raw | geo:reporting | False | True | 61.0% |
| raw | geo:framework | False | True | 70.0% |

## ko_10 — deepseek — natural

[Source post](https://x.com/StarLibra07/status/2099593854886563913); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Actual gameplay test and bandwidth-limited speed disappointment; unseen video cannot establish model results.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | product:ideas_requests | False | True | 50.0% |
| translated | geo:framework | False | True | 62.0% |
| raw | product:ideas_requests | False | True | 59.0% |
| raw | geo:reporting | False | True | 51.0% |
| raw | geo:framework | False | True | 61.0% |

## ko_11 — deepseek — natural

[Source post](https://x.com/Cynical_L/status/2097644061775847486); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Says only DeepSeek deserves Flash name; generic praise not measured performance or geopolitics.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 72.0% |
| raw | type:questions_requests | False | True | 65.0% |
| raw | topic:cost_performance | True | False | 78.0% |
| raw | product:testimonial | True | False | 69.0% |
| translated | type:releases_updates | False | True | 69.0% |
| translated | type:questions_requests | False | True | 61.0% |
| translated | topic:cost_performance | True | False | 77.0% |

## ko_12 — deepseek — natural

[Source post](https://x.com/nacyotKim/status/2083196878079041932); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Surprise DeepSeek release and must-deploy reaction. US timezone comment is not geopolitical.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | product:testimonial | True | False | 82.0% |
| raw | sentiment | positive | neutral | 49.0% |

## ko_13 — upstage — coverage

[Source post](https://x.com/HyperAccelAI/status/2104484668662055096); [verbatim source/translation packet](review-ko.md).

Frozen rationale: HyperAccel event/device promotion with Upstage participating. Do not transfer HyperAccel product pitch to Upstage. Bilingual source retained.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 56.0% |
| raw | type:news_reporting | True | False | 79.0% |
| raw | topic:cost_performance | True | False | 71.0% |
| raw | topic:agents_tools | True | False | 71.0% |
| raw | promotion:spam | False | True | 55.0% |
| translated | outcome | classified | context_missing | 59.0% |
| translated | type:news_reporting | True | False | 78.0% |
| translated | topic:cost_performance | True | False | 57.0% |
| translated | topic:agents_tools | True | False | 74.0% |
| translated | promotion:spam | False | True | 83.0% |

## ko_14 — qwen — coverage

[Source post](https://x.com/USAnt_IDEA/status/2102365680897335503); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Explicit China self-sufficiency celebration and contempt for US restriction/monopoly narrative, with Qwen results and conference/company strategy.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 31/38 | 0 |
| translated | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:results_analysis | True | False | 54.0% |
| translated | type:advertising_marketing | False | True | 62.0% |
| translated | type:news_reporting | True | False | 58.0% |
| translated | topic:evals_benchmarks | True | False | 91.0% |
| translated | topic:agents_tools | True | False | 55.0% |
| translated | china_national_stance | pro | none | 68.0% |
| translated | promotion:general | False | True | 64.0% |
| raw | type:advertising_marketing | False | True | 54.0% |
| raw | type:events | True | False | 60.0% |
| raw | type:news_reporting | True | False | 56.0% |
| raw | topic:evals_benchmarks | True | False | 91.0% |
| raw | topic:agents_tools | True | False | 58.0% |
| raw | china_national_stance | pro | none | 62.0% |
| raw | promotion:general | False | True | 53.0% |

## ko_15 — llama — coverage

[Source post](https://x.com/zupet0/status/2101945590838178015); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Qwen failure after llama.cpp update is not evidence about Meta Llama, the target brand.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | False | True | 50.0% |
| raw | type:questions_requests | False | True | 66.0% |
| raw | topic:local_inference | False | True | 58.0% |
| raw | sentiment | unknown | negative | 43.0% |
| raw | china_national_stance | unknown | none | 91.0% |
| raw | us_national_stance | unknown | none | 93.0% |
| translated | topic:local_inference | False | True | 59.0% |
| translated | china_national_stance | unknown | none | 92.0% |
| translated | us_national_stance | unknown | none | 91.0% |

## ko_16 — deepseek — coverage

[Source post](https://x.com/igangsan54078/status/2105068856465109486); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Anuma memory/service pitch: DeepSeek is one interchangeable backend, not the promoted provider. No evidence the author personally tested DeepSeek.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | outcome | classified | context_missing | 82.0% |
| translated | type:research_explanations | True | False | 73.0% |
| translated | type:news_reporting | True | False | 85.0% |
| translated | sentiment | neutral | unknown | 51.0% |
| translated | promotion:crypto | False | True | 62.0% |
| raw | outcome | classified | context_missing | 74.0% |
| raw | type:research_explanations | True | False | 75.0% |
| raw | type:news_reporting | True | False | 83.0% |
| raw | promotion:unauthorized | False | True | 54.0% |

## ko_17 — qwen — coverage

[Source post](https://x.com/igangsan54078/status/2101867764013240794); [verbatim source/translation packet](review-ko.md).

Frozen rationale: ZetaChain blockchain/Anuma memory ecosystem is promoted; Qwen is a listed backend. Does not establish target-owned promotion.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 63.0% |
| raw | type:research_explanations | True | False | 76.0% |
| raw | type:news_reporting | True | False | 83.0% |
| raw | promotion:spam | False | True | 55.0% |
| raw | promotion:unauthorized | False | True | 57.0% |
| translated | outcome | classified | context_missing | 69.0% |
| translated | type:research_explanations | True | False | 79.0% |
| translated | type:news_reporting | True | False | 82.0% |
| translated | promotion:spam | False | True | 52.0% |
| translated | promotion:unauthorized | False | True | 56.0% |

## ko_18 — deepseek — coverage

[Source post](https://x.com/Coin_Scoop/status/2104586940729204961); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Attributed sensitive-data investigation, not adopted national hostility. Separate CoinScoop news-site CTA is untracked promotion.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | topic:api_developer_surface | True | False | 87.0% |
| translated | sentiment | neutral | negative | 93.0% |
| translated | geo:framework | False | True | 61.0% |
| translated | promotion:general | True | False | 76.0% |
| raw | topic:api_developer_surface | True | False | 85.0% |
| raw | sentiment | neutral | negative | 95.0% |
| raw | geo:framework | False | True | 61.0% |
| raw | promotion:general | True | False | 75.0% |

## ko_19 — qwen — coverage

[Source post](https://x.com/G_ameman/status/2102253901692993948); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Qwen distilled checkpoint release supported by MiMo quote; MiMo-specific RL benchmarks/organizational praise do not automatically describe Qwen.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | True | False | 51.0% |
| raw | type:news_reporting | True | False | 76.0% |
| raw | topic:cost_performance | False | True | 52.0% |
| translated | outcome | classified | context_missing | 57.0% |
| translated | type:research_explanations | True | False | 58.0% |
| translated | type:news_reporting | True | False | 75.0% |
| translated | topic:openness_license | True | False | 57.0% |

## ko_20 — qwen — coverage

[Source post](https://x.com/porysmail/status/2101910305882488899); [verbatim source/translation packet](review-ko.md).

Frozen rationale: Firsthand Qwen setup, strong real-image praise but anime-quality reservation; MiniMax speed problems do not transfer.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | topic:cost_performance | False | True | 67.0% |
| translated | product:complaint | True | False | 86.0% |
| translated | sentiment | mixed | positive | 63.0% |
| translated | geo:reporting | False | True | 73.0% |
| translated | geo:framework | False | True | 72.0% |
| raw | topic:cost_performance | False | True | 75.0% |
| raw | product:complaint | True | False | 94.0% |
| raw | sentiment | mixed | positive | 69.0% |
| raw | geo:reporting | False | True | 70.0% |
| raw | geo:framework | False | True | 74.0% |

## en_01 — qwen — natural

[Source post](https://x.com/abrakjamson/status/2092479075990528429); [verbatim source/translation packet](review-en.md).

Frozen rationale: Fine-tuning workflow and prior observed mediocre output; no new model release or claimed model malfunction.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:local_inference | False | True | 50.0% |
| raw | product:ideas_requests | False | True | 51.0% |
| raw | sentiment | negative | mixed | 53.0% |
| raw | geo:reporting | False | True | 57.0% |
| raw | geo:framework | False | True | 70.0% |

## en_02 — deepseek — natural

[Source post](https://x.com/BoreanTulip/status/2086733218263249195); [verbatim source/translation packet](review-en.md).

Frozen rationale: Rhetorical price/value endorsement of DeepSeek, not genuine help request or national stance.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:evals_benchmarks | True | False | 81.0% |
| raw | product:testimonial | False | True | 53.0% |

## en_03 — glm — natural

[Source post](https://x.com/TanbinFi/status/2079499139642183942); [verbatim source/translation packet](review-en.md).

Frozen rationale: TokenRouter owns the time-limited free-use offer; no GLM-owned pitch established.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 30/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 90.0% |
| raw | type:advertising_marketing | False | True | 93.0% |
| raw | type:news_reporting | True | False | 82.0% |
| raw | topic:openness_license | False | True | 60.0% |
| raw | topic:api_developer_surface | False | True | 63.0% |
| raw | sentiment | neutral | positive | 85.0% |
| raw | geo:reporting | False | True | 58.0% |
| raw | geo:framework | False | True | 74.0% |

## en_04 — qwen — natural

[Source post](https://x.com/Chris_Wozniczek/status/2091872180782923995); [verbatim source/translation packet](review-en.md).

Frozen rationale: Desires a specific Qwen size/variant and future test. Praise of Kimi must not become a Qwen testimonial.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:cost_performance | False | True | 53.0% |
| raw | product:testimonial | False | True | 55.0% |
| raw | geo:reporting | False | True | 51.0% |
| raw | geo:framework | False | True | 67.0% |

## en_05 — qwen — natural

[Source post](https://x.com/largePrawn/status/2093858708514308215); [verbatim source/translation packet](review-en.md).

Frozen rationale: Hypothetical joke about instructing Qwen; no completed use, bug, scam offer or national statement.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:hands_on_usage | False | True | 56.0% |
| raw | topic:agents_tools | True | False | 73.0% |
| raw | sentiment | neutral | negative | 66.0% |
| raw | geo:framework | False | True | 53.0% |

## en_06 — deepseek — natural

[Source post](https://x.com/JamieMcullough/status/2099241739970072946); [verbatim source/translation packet](review-en.md).

Frozen rationale: DeepSeek-linked stock-market fears, no customer complaint or country argument. Unseen confirmation is not a specific allegation.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 38/38 | 0 |

## en_07 — deepseek — natural

[Source post](https://x.com/seulgibair/status/2098073805113450594); [verbatim source/translation packet](review-en.md).

Frozen rationale: Requests availability of a named model, not an announcement.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 73.0% |
| raw | geo:reporting | False | True | 51.0% |
| raw | geo:framework | False | True | 50.0% |

## en_08 — qwen — natural

[Source post](https://x.com/CodeBuilder_/status/2094865755724509408); [verbatim source/translation packet](review-en.md).

Frozen rationale: Question plus stored parent's explicit local Qwen use/speed praise. Quoted/parent evidence is available, not unseen.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 79.0% |
| raw | topic:local_inference | True | False | 72.0% |
| raw | topic:evals_benchmarks | True | False | 90.0% |
| raw | geo:reporting | False | True | 66.0% |
| raw | geo:framework | False | True | 78.0% |

## en_09 — deepseek — natural

[Source post](https://x.com/LordRagnarao/status/2096553038433362425); [verbatim source/translation packet](review-en.md).

Frozen rationale: SOMA compression pitch and quoted measured DeepSeek-token savings; SOMA owns credits/CTA, not DeepSeek.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 29/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | True | False | 72.0% |
| raw | type:results_analysis | True | False | 61.0% |
| raw | type:opportunities | True | False | 56.0% |
| raw | type:opinions_reactions | False | True | 50.0% |
| raw | type:research_explanations | True | False | 53.0% |
| raw | type:news_reporting | True | False | 87.0% |
| raw | geo:reporting | False | True | 64.0% |
| raw | geo:framework | False | True | 70.0% |
| raw | promotion:unauthorized | False | True | 54.0% |

## en_10 — qwen — natural

[Source post](https://x.com/vulcantechteam/status/2100709210505826658); [verbatim source/translation packet](review-en.md).

Frozen rationale: Explains public-document Qwen retrieval, government warnings/removal and lack of sensitive-data evidence; does not adopt allegation as true.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 70.0% |
| raw | type:opinions_reactions | False | True | 64.0% |
| raw | product:investigate_claim | False | True | 68.0% |
| raw | geo:nationalism | False | True | 50.0% |

## en_11 — deepseek — natural

[Source post](https://x.com/mikeng_io/status/2093650413983764672); [verbatim source/translation packet](review-en.md).

Frozen rationale: Returns to DeepSeek after GLM language problems; bugs/complaints must not transfer to DeepSeek.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:evals_benchmarks | True | False | 84.0% |
| raw | product:testimonial | True | False | 65.0% |
| raw | geo:framework | False | True | 56.0% |

## en_12 — glm — natural

[Source post](https://x.com/WorkBudd/status/2097767041440567508); [verbatim source/translation packet](review-en.md).

Frozen rationale: WorkBuddy owns credits and signup pitch; GLM listed as an available model.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 52.0% |
| raw | sentiment | neutral | positive | 41.0% |
| raw | geo:framework | False | True | 53.0% |

## en_13 — mimo — coverage

[Source post](https://x.com/PratikPatel_227/status/2102211363586420906); [verbatim source/translation packet](review-en.md).

Frozen rationale: Release and explicit official model showcase in quote, performance/pricing comparison; third-party author endorses result.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:reporting | False | True | 64.0% |
| raw | geo:framework | False | True | 71.0% |

## en_14 — deepseek — coverage

[Source post](https://x.com/theinformation/status/2104269870560850346); [verbatim source/translation packet](review-en.md).

Frozen rationale: Regulator investigation is geopolitical reporting; Read more promotes the publisher, not DeepSeek.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:model_distillation | True | False | 67.0% |
| raw | topic:api_developer_surface | True | False | 85.0% |
| raw | sentiment | neutral | negative | 94.0% |
| raw | geo:framework | False | True | 60.0% |
| raw | promotion:general | True | False | 91.0% |

## en_15 — deepseek — coverage

[Source post](https://x.com/AdrianaCrosing/status/2105061978448572822); [verbatim source/translation packet](review-en.md).

Frozen rationale: B.AI availability/discount narrative. One post supplies no cross-post duplication evidence; no target-owned advertisement.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 27/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 88.0% |
| raw | type:advertising_marketing | False | True | 83.0% |
| raw | type:opportunities | False | True | 64.0% |
| raw | type:opinions_reactions | False | True | 88.0% |
| raw | type:news_reporting | True | False | 68.0% |
| raw | product:testimonial | False | True | 69.0% |
| raw | sentiment | neutral | positive | 99.0% |
| raw | geo:reporting | False | True | 52.0% |
| raw | geo:framework | False | True | 57.0% |
| raw | promotion:general | True | False | 54.0% |
| raw | promotion:crypto | False | True | 73.0% |

## en_16 — qwen — coverage

[Source post](https://x.com/Bitget_AI/status/2103047860602495198); [verbatim source/translation packet](review-en.md).

Frozen rationale: Qwen explicitly backs hackathon; quote supplies Qwen credits. Attendance venue/session absent, so not events by current definition. Crypto exchange promoted separately.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:api_developer_surface | False | True | 67.0% |
| raw | geo:reporting | False | True | 61.0% |
| raw | geo:framework | False | True | 62.0% |
| raw | promotion:spam | False | True | 72.0% |
| raw | promotion:unauthorized | False | True | 75.0% |

## en_17 — minimax — coverage

[Source post](https://x.com/Israfilv2/status/2104250069600116756); [verbatim source/translation packet](review-en.md).

Frozen rationale: Direct MiniMax plan recommendation and timed quota offer. Shared-key link does not itself prove fraud or authorization status; Telegram channel promoted separately.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:reporting | False | True | 74.0% |
| raw | geo:framework | False | True | 74.0% |
| raw | promotion:general | True | False | 77.0% |

## en_18 — glm — coverage

[Source post](https://x.com/AhmedAlNeaimy/status/2102393479766679876); [verbatim source/translation packet](review-en.md).

Frozen rationale: Actual response-time problem/comparison and explicit transparency request; no geopolitical content.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 68.0% |
| raw | geo:reporting | False | True | 60.0% |
| raw | geo:framework | False | True | 75.0% |

## en_19 — qwen — coverage

[Source post](https://x.com/taras_y_sereda/status/2102205025712058858); [verbatim source/translation packet](review-en.md).

Frozen rationale: Qwen compression excitement plus separate lab ecosystem showcase in quote; no confirmed measured target result.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:reporting | False | True | 63.0% |
| raw | geo:framework | False | True | 70.0% |

## en_20 — minimax — coverage

[Source post](https://x.com/_joncipher/status/2101906465418084591); [verbatim source/translation packet](review-en.md).

Frozen rationale: MiniMax appears only as a hashtag inside Engy/BlueTAO token-network promotion; Kimi metrics cannot transfer.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 23/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | context_missing | classified | 66.0% |
| raw | type:hands_on_usage | False | True | 57.0% |
| raw | type:results_analysis | False | True | 66.0% |
| raw | type:advertising_marketing | False | True | 62.0% |
| raw | type:opinions_reactions | False | True | 75.0% |
| raw | type:business_finance | False | True | 55.0% |
| raw | topic:api_developer_surface | False | True | 66.0% |
| raw | product:testimonial | False | True | 62.0% |
| raw | sentiment | unknown | positive | 73.0% |
| raw | geo:reporting | False | True | 59.0% |
| raw | geo:framework | False | True | 60.0% |
| raw | china_national_stance | unknown | none | 93.0% |
| raw | us_national_stance | unknown | none | 91.0% |
| raw | promotion:spam | False | True | 62.0% |
| raw | promotion:unauthorized | False | True | 77.0% |

## es_01 — deepseek — natural

[Source post](https://x.com/_garciaa1888/status/2092566125871497468); [verbatim source/translation packet](review-es.md).

Frozen rationale: Explicit favorable DeepSeek judgment; no explicit firsthand run or substantive result evidence.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:evals_benchmarks | True | False | 88.0% |
| raw | geo:reporting | False | True | 52.0% |

## es_02 — llama — natural

[Source post](https://x.com/yngthv/status/2076490444335448448); [verbatim source/translation packet](review-es.md).

Frozen rationale: Spanish se llama means is called; BTS fan page is unrelated to Meta Llama.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 75.0% |
| raw | us_national_stance | unknown | none | 75.0% |

## es_03 — minimax — natural

[Source post](https://x.com/Adamaestr0_/status/2084965725501116494); [verbatim source/translation packet](review-es.md).

Frozen rationale: Firsthand one-shot generation with observed perfect outcome; no numeric benchmark or launch.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 89.0% |
| raw | geo:reporting | False | True | 62.0% |
| raw | geo:framework | False | True | 75.0% |
| translated | type:results_analysis | True | False | 85.0% |
| translated | geo:reporting | False | True | 61.0% |
| translated | geo:framework | False | True | 75.0% |

## es_04 — qwen — natural

[Source post](https://x.com/oscarhbp1/status/2085410129696948485); [verbatim source/translation packet](review-es.md).

Frozen rationale: Qwen-focused article title plus creator subscription pitch. Do not assume unseen article technical explanation.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:advertising_marketing | False | True | 61.0% |
| translated | type:opinions_reactions | False | True | 70.0% |
| translated | type:other | True | False | 78.0% |
| translated | sentiment | neutral | positive | 48.0% |
| translated | geo:reporting | False | True | 64.0% |
| translated | geo:framework | False | True | 69.0% |
| translated | promotion:general | True | False | 58.0% |
| raw | type:advertising_marketing | False | True | 55.0% |
| raw | type:opinions_reactions | False | True | 76.0% |
| raw | type:other | True | False | 74.0% |
| raw | sentiment | neutral | positive | 63.0% |
| raw | geo:framework | False | True | 59.0% |

## es_05 — llama — natural

[Source post](https://x.com/donal_varo21/status/2076497260678987988); [verbatim source/translation packet](review-es.md).

Frozen rationale: Spanish se llama keyword collision in political criticism unrelated to Llama.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 72.0% |
| raw | us_national_stance | unknown | none | 72.0% |

## es_06 — deepseek — natural

[Source post](https://x.com/borjaperfra/status/2085654783319236980); [verbatim source/translation packet](review-es.md).

Frozen rationale: Promotes author's multi-model article; title does not supply actual instructions, completed hands-on use or model-owner pitch.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 30/38 | 0 |
| translated | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 50.0% |
| translated | type:opinions_reactions | False | True | 58.0% |
| translated | type:research_explanations | False | True | 79.0% |
| translated | type:other | True | False | 81.0% |
| translated | topic:api_developer_surface | False | True | 53.0% |
| translated | geo:framework | False | True | 69.0% |
| translated | promotion:general | True | False | 74.0% |
| raw | type:hands_on_usage | False | True | 53.0% |
| raw | type:opinions_reactions | False | True | 56.0% |
| raw | type:research_explanations | False | True | 78.0% |
| raw | type:other | True | False | 81.0% |
| raw | topic:api_developer_surface | False | True | 63.0% |
| raw | geo:reporting | False | True | 51.0% |
| raw | geo:framework | False | True | 64.0% |
| raw | promotion:general | True | False | 58.0% |

## es_07 — deepseek — natural

[Source post](https://x.com/mercado_negro/status/2089872473198129488); [verbatim source/translation packet](review-es.md).

Frozen rationale: Dated DeepSeek API pricing change and comparative price; publisher CTA separately promotes the article.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | sentiment | neutral | mixed | 62.0% |
| raw | geo:reporting | False | True | 50.0% |
| raw | promotion:general | True | False | 77.0% |

## es_08 — deepseek — natural

[Source post](https://x.com/LuisOrlandoDia1/status/2091294372935438846); [verbatim source/translation packet](review-es.md).

Frozen rationale: Roundup reports DeepSeek Harness release; author's linked article promoted, not target service CTA.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 51.0% |
| raw | promotion:general | True | False | 59.0% |

## es_09 — deepseek — natural

[Source post](https://x.com/barckcode/status/2083235322167456092); [verbatim source/translation packet](review-es.md).

Frozen rationale: Author deployed release; official supporting quote announces architecture/config; NaN hosting promoted separately.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | outcome | classified | context_missing | 62.0% |
| raw | type:hands_on_usage | True | False | 75.0% |
| raw | type:advertising_marketing | True | False | 58.0% |
| raw | product:testimonial | True | False | 63.0% |
| raw | promotion:general | True | False | 53.0% |

## es_10 — deepseek — natural

[Source post](https://x.com/YueRexie/status/2091691673092768218); [verbatim source/translation packet](review-es.md).

Frozen rationale: Pays for and endorses productive transparent Codex plus DeepSeek workflow; not an explicit sales offer.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:cost_performance | False | True | 60.0% |
| raw | geo:framework | False | True | 60.0% |

## es_11 — excluded before inference

See reference_rows.json for the source-language mismatch.

## es_12 — deepseek — natural

[Source post](https://x.com/CANAL44TV/status/2086987211434594668); [verbatim source/translation packet](review-es.md).

Frozen rationale: Country-bloc AI competition and profitability, not hostility or superiority of a nation; Chinese AI explicitly called effective/value for money.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 84.0% |
| raw | geo:nationalism | False | True | 65.0% |

## es_13 — deepseek — coverage

[Source post](https://x.com/Branidiaz/status/2104174772862984256); [verbatim source/translation packet](review-es.md).

Frozen rationale: Specific insecure-code finding and backdoor concern; political triggers and predicted policy exploitation, without adopted national hostility.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:evals_benchmarks | True | False | 55.0% |
| raw | topic:openness_license | True | False | 52.0% |
| raw | product:bug | True | False | 73.0% |
| translated | type:news_reporting | True | False | 53.0% |
| translated | product:bug | True | False | 67.0% |

## es_14 — llama — coverage

[Source post](https://x.com/DineroCOP/status/2104602365060071597); [verbatim source/translation packet](review-es.md).

Frozen rationale: Meta enterprise executive appointment concerns Muse/platform, not Llama. Company-to-specific-product attribution is disputed and sensitivity-scored separately.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 28/38 | 0 |
| translated | 27/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | outcome | context_missing | classified | 62.0% |
| translated | type:personnel_changes | False | True | 57.0% |
| translated | type:business_finance | False | True | 81.0% |
| translated | type:news_reporting | False | True | 64.0% |
| translated | topic:agents_tools | False | True | 68.0% |
| translated | topic:api_developer_surface | False | True | 77.0% |
| translated | sentiment | unknown | neutral | 38.0% |
| translated | geo:framework | False | True | 55.0% |
| translated | china_national_stance | unknown | none | 90.0% |
| translated | us_national_stance | unknown | none | 93.0% |
| translated | promotion:general | False | True | 57.0% |
| raw | outcome | context_missing | classified | 52.0% |
| raw | type:personnel_changes | False | True | 54.0% |
| raw | type:business_finance | False | True | 78.0% |
| raw | type:news_reporting | False | True | 57.0% |
| raw | topic:agents_tools | False | True | 60.0% |
| raw | topic:api_developer_surface | False | True | 72.0% |
| raw | sentiment | unknown | neutral | 38.0% |
| raw | china_national_stance | unknown | none | 89.0% |
| raw | us_national_stance | unknown | none | 90.0% |
| raw | promotion:general | False | True | 57.0% |

## es_15 — deepseek — coverage

[Source post](https://x.com/dolarsmallface/status/2105054738710417694); [verbatim source/translation packet](review-es.md).

Frozen rationale: Reports models lying/hiding task failure. Chinese/US product origin alone is not geopolitics or national sentiment.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 73.0% |
| raw | topic:evals_benchmarks | True | False | 84.0% |
| raw | topic:agents_tools | False | True | 72.0% |
| raw | sentiment | neutral | negative | 89.0% |
| raw | geo:reporting | False | True | 60.0% |
| translated | type:opinions_reactions | False | True | 77.0% |
| translated | topic:evals_benchmarks | True | False | 87.0% |
| translated | topic:agents_tools | False | True | 74.0% |
| translated | sentiment | neutral | negative | 92.0% |
| translated | geo:reporting | False | True | 59.0% |
| translated | geo:nationalism | False | True | 55.0% |

## es_16 — minimax — coverage

[Source post](https://x.com/0xJokker/status/2103525455748100373); [verbatim source/translation packet](review-es.md).

Frozen rationale: Concrete provider-compatibility question, with detailed saved parent about MiniMax CLI; not a new feature demand.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |
| translated | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:opinions_reactions | False | True | 78.0% |
| translated | topic:cost_performance | False | True | 57.0% |
| translated | sentiment | neutral | mixed | 50.0% |
| translated | geo:reporting | False | True | 60.0% |
| translated | geo:framework | False | True | 59.0% |
| translated | promotion:general | False | True | 61.0% |
| raw | type:opinions_reactions | False | True | 76.0% |
| raw | topic:cost_performance | False | True | 61.0% |
| raw | sentiment | neutral | mixed | 70.0% |
| raw | geo:reporting | False | True | 64.0% |
| raw | geo:framework | False | True | 63.0% |
| raw | promotion:general | False | True | 61.0% |

## es_17 — llama — coverage

[Source post](https://x.com/patoroco/status/2104125344055726117); [verbatim source/translation packet](review-es.md).

Frozen rationale: Spanish me llama means appeals to me in Tesla vehicle comparison; unrelated Meta Llama.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 82.0% |
| raw | us_national_stance | unknown | none | 82.0% |
| translated | china_national_stance | unknown | none | 84.0% |
| translated | us_national_stance | unknown | none | 83.0% |

## es_18 — qwen — coverage

[Source post](https://x.com/DR_JohnSmith_/status/2104106091751608487); [verbatim source/translation packet](review-es.md).

Frozen rationale: Qwen best among variants but hangs at harder tasks; concrete failure and mixed customer judgment.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | topic:local_inference | False | True | 73.0% |
| translated | topic:cost_performance | False | True | 73.0% |
| translated | product:ideas_requests | False | True | 53.0% |
| translated | geo:reporting | False | True | 55.0% |
| translated | geo:framework | False | True | 66.0% |
| raw | topic:local_inference | False | True | 72.0% |
| raw | topic:cost_performance | False | True | 63.0% |
| raw | geo:reporting | False | True | 62.0% |
| raw | geo:framework | False | True | 65.0% |

## es_19 — deepseek — coverage

[Source post](https://x.com/Legnatbird/status/2104555313730932820); [verbatim source/translation packet](review-es.md).

Frozen rationale: Wants better DeepSeek usage allowance in unnamed provider plan. Provider pricing criticism does not prove negative model sentiment/complaint.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:releases_updates | False | True | 55.0% |
| raw | topic:api_developer_surface | False | True | 55.0% |
| raw | product:complaint | False | True | 72.0% |
| raw | sentiment | neutral | negative | 53.0% |
| raw | geo:framework | False | True | 51.0% |
| translated | topic:api_developer_surface | False | True | 60.0% |
| translated | product:complaint | False | True | 65.0% |
| translated | sentiment | neutral | positive | 44.0% |
| translated | geo:reporting | False | True | 51.0% |
| translated | geo:framework | False | True | 53.0% |

## es_20 — deepseek — coverage

[Source post](https://x.com/Alec0Torres/status/2105118835195961663); [verbatim source/translation packet](review-es.md).

Frozen rationale: Paid for DeepSeek; unseen reaction media cannot establish approval, complaint or output quality.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:hands_on_usage | True | False | 51.0% |
| translated | type:opinions_reactions | False | True | 85.0% |
| translated | sentiment | neutral | unknown | 80.0% |
| translated | geo:framework | False | True | 50.0% |
| raw | type:opinions_reactions | False | True | 74.0% |
| raw | sentiment | neutral | unknown | 86.0% |
| raw | geo:framework | False | True | 52.0% |

## tr_01 — deepseek — natural

[Source post](https://x.com/dragonomi_ai/status/2085391573672427937); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Funding target and valuation report; yuan currency does not establish geopolitical meaning.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 38/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | geo:reporting | False | True | 53.0% |
| translated | geo:framework | False | True | 51.0% |

## tr_02 — deepseek — natural

[Source post](https://x.com/berattunca1/status/2090599728157249590); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Training-token quantities, not an actual performance evaluation or author's model use.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 72.0% |
| raw | geo:framework | False | True | 52.0% |

## tr_03 — minimax — natural

[Source post](https://x.com/robink78/status/2090827157593305387); [verbatim source/translation packet](review-tr.md).

Frozen rationale: MiniMax desktop failed for two days; irrelevant Gemini troubleshooting is not MiniMax technical truth.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | False | True | 69.0% |
| raw | type:questions_requests | False | True | 61.0% |
| raw | topic:local_inference | False | True | 62.0% |
| raw | topic:api_developer_surface | False | True | 64.0% |
| raw | geo:reporting | False | True | 61.0% |
| raw | geo:framework | False | True | 74.0% |

## tr_04 — deepseek — natural

[Source post](https://x.com/Nuvemmag/status/2092341276557394305); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Attributed Chinese-state-linked hacking and doubled attack volume; no author national hostility. Publisher link is a separate news promotion.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 31/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 83.0% |
| raw | type:opinions_reactions | False | True | 67.0% |
| raw | type:research_explanations | True | False | 76.0% |
| raw | sentiment | neutral | negative | 91.0% |
| raw | geo:framework | False | True | 61.0% |
| raw | geo:nationalism | False | True | 63.0% |
| raw | promotion:general | True | False | 88.0% |

## tr_05 — deepseek — natural

[Source post](https://x.com/Eofdred/status/2090915586184519870); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Describes useful DeepSeek willingness versus Western-provider licensing restrictions; nationality grouping alone insufficient for adopted national stance.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:results_analysis | True | False | 81.0% |
| raw | geo:reporting | False | True | 53.0% |

## tr_06 — moonshot_kimi — natural

[Source post](https://x.com/oguzcun/status/2068611963848905033); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Turkish kimi means whom; political opinion unrelated to Moonshot Kimi.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | geo:nationalism | False | True | 52.0% |
| raw | china_national_stance | unknown | none | 56.0% |
| raw | us_national_stance | unknown | none | 67.0% |

## tr_07 — moonshot_kimi — natural

[Source post](https://x.com/SauronAbi/status/2068751929107198091); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Turkish kimi/kimisi means some; racist-society remark unrelated to Moonshot Kimi and cannot give Kimi a geo tag.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 56.0% |
| raw | us_national_stance | unknown | none | 65.0% |

## tr_08 — deepseek — natural

[Source post](https://x.com/0xbo79/status/2090832112366538784); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Vision API release and attributed comparison plus try-today invitation, with explicit vendor-benchmark caveat.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:advertising_marketing | True | False | 51.0% |
| raw | type:opportunities | False | True | 52.0% |
| raw | geo:reporting | False | True | 60.0% |
| raw | geo:framework | False | True | 74.0% |

## tr_09 — minimax — natural

[Source post](https://x.com/aiproducers/status/2085657949033083095); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Quoted joint Luma/MiniMax offering with direct CTA; explicit branded co-promotion, not merely a backend-list prize.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:news_reporting | True | False | 51.0% |
| raw | geo:reporting | False | True | 57.0% |
| raw | geo:framework | False | True | 62.0% |
| translated | geo:reporting | False | True | 56.0% |
| translated | geo:framework | False | True | 66.0% |

## tr_10 — qwen — natural

[Source post](https://x.com/kahpeadam31/status/2089729529178673380); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Says uncensored Qwen should be banned but thanks for doctor recommendation; irony cannot be resolved from unseen media.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:questions_requests | False | True | 71.0% |
| raw | sentiment | mixed | negative | 94.0% |
| raw | geo:framework | False | True | 56.0% |

## tr_11 — excluded before inference

See reference_rows.json for the source-language mismatch.

## tr_12 — moonshot_kimi — natural

[Source post](https://x.com/piskopos1903/status/2068989747888837064); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Political insult and Turkish kimi keyword collision; unrelated Moonshot Kimi.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 73.0% |
| raw | us_national_stance | unknown | none | 78.0% |

## tr_13 — yi — coverage

[Source post](https://x.com/SnowballAlphaX/status/2105143897093538212); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Turkish suffix yi inside Morpho report is not 01.AI Yi. Balanced financial/technical analysis is not automatically crypto promotion.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | china_national_stance | unknown | none | 82.0% |
| raw | us_national_stance | unknown | none | 85.0% |
| raw | promotion:spam | False | True | 71.0% |
| raw | promotion:crypto | False | True | 93.0% |
| raw | promotion:unauthorized | False | True | 77.0% |
| translated | china_national_stance | unknown | none | 87.0% |
| translated | us_national_stance | unknown | none | 83.0% |
| translated | promotion:spam | False | True | 65.0% |
| translated | promotion:crypto | False | True | 92.0% |
| translated | promotion:unauthorized | False | True | 76.0% |

## tr_14 — deepseek — coverage

[Source post](https://x.com/ersinkoc/status/2103566802970460365); [verbatim source/translation packet](review-tr.md).

Frozen rationale: OpenCode subscription pitch, with independently favorable DeepSeek descriptor. Other provider's CTA does not transfer.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 36/38 | 0 |
| translated | 36/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | geo:framework | False | True | 52.0% |
| translated | promotion:unauthorized | False | True | 54.0% |
| raw | type:releases_updates | False | True | 51.0% |
| raw | geo:reporting | False | True | 53.0% |

## tr_15 — qwen — coverage

[Source post](https://x.com/KaanBahsi/status/2104141893483266390); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Explicit CPU TTS experiment and methods, qualified speed/quality observation; no NVIDIA hardware assumption.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 34/38 | 0 |
| translated | 34/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 83.0% |
| raw | topic:openness_license | False | True | 64.0% |
| raw | geo:reporting | False | True | 52.0% |
| raw | geo:framework | False | True | 78.0% |
| translated | type:opinions_reactions | False | True | 83.0% |
| translated | topic:openness_license | False | True | 65.0% |
| translated | geo:reporting | False | True | 56.0% |
| translated | geo:framework | False | True | 74.0% |

## tr_16 — deepseek — coverage

[Source post](https://x.com/morphysw/status/2105010970028343397); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Adopted copying/distillation allegation tied to entry/training cost; company allegation has no national framing.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 37/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:business_finance | True | False | 57.0% |
| raw | type:business_finance | True | False | 75.0% |
| raw | topic:cost_performance | True | False | 69.0% |
| raw | geo:framework | False | True | 54.0% |

## tr_17 — hunyuan — coverage

[Source post](https://x.com/CihadTurhan/status/2103991937531511073); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Asks RAM needs and result quality; no actual benchmark result or request for a new capability.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 33/38 | 0 |
| translated | 33/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | type:opinions_reactions | False | True | 60.0% |
| raw | topic:local_inference | False | True | 58.0% |
| raw | product:ideas_requests | False | True | 52.0% |
| raw | geo:reporting | False | True | 57.0% |
| raw | geo:framework | False | True | 62.0% |
| translated | type:opinions_reactions | False | True | 53.0% |
| translated | topic:local_inference | False | True | 69.0% |
| translated | product:ideas_requests | False | True | 55.0% |
| translated | geo:reporting | False | True | 61.0% |
| translated | geo:framework | False | True | 75.0% |

## tr_18 — mistral — coverage

[Source post](https://x.com/LotraHaber/status/2103784072757510238); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Attributes European AI autonomy argument to CEO; neutral report does not adopt CEO's national sentiment.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:opinions_reactions | False | True | 75.0% |
| translated | sentiment | neutral | positive | 57.0% |
| translated | geo:nationalism | False | True | 52.0% |
| raw | type:opinions_reactions | False | True | 78.0% |
| raw | sentiment | neutral | positive | 59.0% |
| raw | geo:nationalism | False | True | 51.0% |

## tr_19 — deepseek — coverage

[Source post](https://x.com/ZerefDragneell2/status/2105017603802407095); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Explicit generalization about Chinese-origin models; evaluates national-origin product group, not China/US country itself. Marked sensitivity case.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 35/38 | 0 |
| translated | 35/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| raw | topic:evals_benchmarks | True | False | 87.0% |
| raw | geo:framework | False | True | 57.0% |
| raw | geo:nationalism | True | False | 71.0% |
| translated | topic:evals_benchmarks | True | False | 84.0% |
| translated | geo:framework | False | True | 52.0% |
| translated | geo:nationalism | True | False | 57.0% |

## tr_20 — deepseek — coverage

[Source post](https://x.com/yapaymeraklisi/status/2104182137700106446); [verbatim source/translation packet](review-tr.md).

Frozen rationale: Reports sandbox-throughput number and preprint caveat; no substantive mechanism or firsthand experiment.

| Arm | Correct fields | Invalid fields |
| --- | ---: | ---: |
| raw | 32/38 | 0 |
| translated | 32/38 | 0 |

| Arm | Field | Reference | Jev | Selected probability |
| --- | --- | --- | --- | ---: |
| translated | type:releases_updates | False | True | 78.0% |
| translated | type:results_analysis | True | False | 76.0% |
| translated | type:opinions_reactions | False | True | 54.0% |
| translated | type:research_explanations | False | True | 52.0% |
| translated | geo:reporting | False | True | 62.0% |
| translated | geo:framework | False | True | 57.0% |
| raw | type:releases_updates | False | True | 82.0% |
| raw | type:results_analysis | True | False | 80.0% |
| raw | type:advertising_marketing | False | True | 50.0% |
| raw | type:opinions_reactions | False | True | 68.0% |
| raw | topic:api_developer_surface | False | True | 55.0% |
| raw | geo:framework | False | True | 51.0% |
