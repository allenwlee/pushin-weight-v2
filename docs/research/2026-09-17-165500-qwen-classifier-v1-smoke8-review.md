---
title: Qwen classifier v1 smoke-8 review
date: 2026-09-17
type: experiment-review
---

# Qwen classifier v1 smoke-8 review

This review compares the raw output with the frozen source evidence and the
frozen U18A prompt. It does not use historical owner answers as a gold set:
the current 14 post types, seven Audience Topics, geopolitical modes,
`investigate_claim`, and post-level untracked-brand promotion identities are
not the same contract as older classifier material.

## Frozen run facts

- Contract: `.context/model-task-20260917/qwen-classification-v1-smoke8/contract.json`.
- Route: `qwen/qwen3.7-flash` through Alibaba, served as
  `qwen/qwen3.7-flash-20260727`; fallbacks disabled; reasoning reported zero.
- Four required calls completed with `finish_reason=stop`, exact fixed JSON
  roots, no transport exception, and no retry. Reported total cost was
  $0.00063658; the frozen reservation was $0.00384988.
- Every content response parsed. Neither brand-interpretation batch parsed:
  `taxonomy.parse` therefore made all eight sources unpublishable. This is a
  real runtime effect, not a semantic judgment.

The first brand batch made D03 (`H-H2B36BE298C6`) impossible by choosing
`["reporting"]` while assigning `china_national_stance="anti"` and
`us_national_stance="pro"`. The second made D01 and D02 impossible by using
`["none"]` with `unknown` country stances. The frozen parser correctly
requires `none` stances unless `nationalism` is present, and `unknown` only
with `["unavailable"]`.

## Source-evidence review

“Good” means supported by this source and prompt, not agreement with a prior
classifier. A source has an error when any raw output is structurally invalid
or misses/adds a clearly supported/unsupported current-contract axis.

| Source post | Raw output that is supported | Errors found from visible source evidence | Result |
| --- | --- | --- | --- |
| `H-H0040D161174` / Qwen | `classified`; Qwen is visibly named and the text supports an assessable non-national stance. Product label `none` and neutral brand sentiment are defensible. | It calls Qwen's self-hosted open-weight option a bare `news_reporting` item. It misses `research_explanations` and the authored operational recommendation; it misses the visible `local_inference`, `cost_performance`, and `openness_license` topics. | error |
| `H-H0DEC6F537E0` / Qwen | Qwen Meetup supports `events`; no Geopolitical mode is supported. | “I have some Issues, Can we discuss” is a genuine brand-related question/support request, so `questions_requests` is missing. Neutral sentiment is at best incomplete beside gratitude plus unresolved issues. | error |
| `H-H2B36BE298C6` / DeepSeek | `news_reporting`, `model_distillation`, `investigate_claim`, and `reporting` are supported: the author relays institutional allegations and does not adjudicate them. | `opinions_reactions` improperly treats reported allegations as the author's opinion. The source supports no adopted nationalism, so the China/U.S. directional stances are both structurally invalid and semantically unsupported; brand sentiment should remain neutral rather than negative from an attributed allegation alone. | error |
| `H-H7046A8A0689` / Qwen | `opinions_reactions`, product `none`, and non-geopolitical stances are supported. The unsupported "better than qwen 3.6" statement is an opinion, not a substantiated result under the current `results_analysis` definition. | The wording praises an external model relative to Qwen, so negative Qwen sentiment is defensible; the frozen evidence does not support calling neutral the only correct reading. | reviewed with sentiment uncertainty |
| `L-L45-01` / DeepSeek | `news_reporting`, `business_finance`, product `none`, neutral sentiment, and non-geopolitical stances are supported. The raw `context_missing` decisions for Doubao, GLM, and MiniMax are also supported: they only occur as prior investments, not current brand judgments. | The named, reported move to “DeepSeek CFO” is a formal employment transition. `personnel_changes` is missing for DeepSeek. | error (one of four brand decisions wrong) |
| `L-L45-02` / DeepSeek | `news_reporting`, `bug`, negative brand sentiment, and a non-geopolitical assessment are supported by the named CVE, concrete escape path, and fixed version. | The technical sandbox/control-API account also supports `research_explanations` and `agents_tools`; both are missed. The raw country `unknown` values make an otherwise good brand decision unparseable; both must be `none`. | error |
| `L-L45-09` / MiniMax | `hands_on_usage` is supported: the author describes making a 15-second animation with MiniMax H3. No geopolitical mode is supported. | The observed “fine movements” limitation supports `results_analysis`; it is missing. `ideas_requests` invents a request. The hands-on praise plus stated limitation supports mixed sentiment and a product-experience complaint more directly than neutral/ideas-request. Country stances are structurally invalid (`unknown` under `["none"]`). | error |
| `L-L45-21` / Kimi, DeepSeek, GLM | `opinions_reactions` is supported for each explicitly named Chinese-AI brand. The post also visibly makes a China-versus-U.S. technical comparison, a strategic prediction, and a China-linked ideological concern, so `framework` plus `nationalism` is plausible for all three rather than a cross-brand transfer. | The source's stance is not simple China-pro/U.S.-anti: it praises Chinese capability while warning about state-linked ideological influence, and urges avoiding U.S. stagnation. The identical `china=pro`, `us=anti` values are unsupported. Its comparison is opinion rather than a substantiated `results_analysis` result. | error (all three brand decisions need review) |

The smoke gate therefore fails at 8/8 source posts. The exact structural
error rate is 100%; the semantic review also finds a material source-evidence
error in every source. The result cannot proceed to the 24-source diagnostic
cohort.

## Adjustment for Qwen v2

The correction is deliberately narrower than adding a role or importing old
answers. The two-call architecture remains content plus brand interpretation.
Qwen v2 switches from JSON-object mode to documented plain JSON plus local
fixed-slot validation and adds two independent-axis checks:

1. Content must test every post type and every Audience Topic separately, so
   a broad news label cannot suppress technical, local-inference, cost, or
   openness labels.
2. Brand interpretation must select geopolitical modes before country stances
   and follow an explicit three-state table: `unavailable -> unknown`, no
   `nationalism -> none`, and directional stances only with `nationalism`.

The request stays on the saved Alibaba route, has no fallback or retry, keeps
the two roles, and is rejected at preparation if its complete serialized
request exceeds 32,000 bytes. The expected next improvement is publishable
brand output; it does not pre-claim semantic success. Qwen v3 is prepared as
a separately frozen bounded-thinking configuration only if v2 still has a
diagnosed semantic failure.
