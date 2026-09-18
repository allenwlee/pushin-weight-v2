# Gemma 4 31B direct DeepInfra classifier diagnostic

Date: 2026-09-18  
Status: complete; candidate does not qualify for classifier activation

## Plain-English result

Gemma 4 31B reliably returned the required classifier format through the direct
DeepInfra endpoint, but its labels were not reliable enough to replace the
selected 0731 classifier. Three configurations completed all 48 calls for the
same 24 posts without a malformed response, transport error, fallback, or
retry. The best-looking mechanical score still contained important semantic
errors: missing independent labels, incorrect state for a brand absent from
the evidence, missed untracked-brand promotions, and unstable labels when the
prompt or sampling changed.

No runtime route, database row, staging setting, or production setting changed.
Cloud 0731 remains the selected classifier.

## Frozen comparison

All three Gemma configurations used the same 24 source posts and the same two
one-post roles as the retained direct DeepSeek V4.1 control. The content role
classified post types, Audience Topics, and Untracked Brand Promotions. The
brand role classified product labels, sentiment, geopolitical mode, and
country stance for each target brand.

| Run | Material configuration | Complete calls / sources | Structural or transport errors | Wall time | DeepInfra reported cost |
|---|---|---:|---:|---:|---:|
| Gemma v1 | Tagged fields; temperature 0.2; thinking disabled | 48/48; 24/24 | 0 | 166.846 s | $0.010620480041 |
| Gemma v2 | v1 plus an independent-axis and target-brand checklist | 48/48; 24/24 | 0 | 231.965 s | $0.011007940047 |
| Gemma v3 | v2 plus Gemma thinking control token and model-card sampling (`1.0`, `0.95`, `64`) | 48/48; 24/24 | 0 | 259.468 s | $0.012397540033 |
| Direct V4.1 control | Same 24 posts and two singleton roles | 48/48; 24/24 | 0 | 51.256 s | Direct billed cost unavailable |

The v3 provider responses exposed no `reasoning_content` and no inline thought
channel. The request followed the documented Gemma control-token convention,
but the receipt cannot prove that DeepInfra executed internal thinking.

The model-specific v3 settings came from Google's Gemma 4 documentation, which
recommends temperature 1.0, top-p 0.95, top-k 64 and activates thinking with a
`<|think|>` system token. DeepInfra documents the exact
`google/gemma-4-31B-it-turbo` OpenAI-compatible endpoint and standard prices of
$0.09/M input, $0.34/M output, and $0.05/M cached input:

- https://ai.google.dev/gemma/docs/core/model_card_4
- https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4
- https://deepinfra.com/google/gemma-4-31B-it-turbo/api

## Semantic result

The auxiliary owner-control score compares only nonblank historical owner
fields and maps the renamed legacy labels. It is useful for finding changes,
but it is not blinded gold and does not cover the current taxonomy completely.

| Output | Matching historical fields | Reviewed fields | Sources with at least one mismatch |
|---|---:|---:|---:|
| Gemma v1 | 142 | 209 | 21/24 |
| Gemma v2 | 142 | 209 | 21/24 |
| Gemma v3 | 146 | 209 | 21/24 |
| V4.1 control | 130 | 209 | 21/24 |

Gemma's higher field total does **not** establish parity. An independent v3
review initially found 9 Gemma error sources versus 13 for V4.1, but it treated
several explicit owner decisions as optional and incorrectly reported that
V4.1 missed the H8FA promotion even though its retained output contains
`general` and a promoted subject. Parent reconciliation against the owner's
nonblank controls and later target-brand rules supersedes that selection score:

| Parent-reconciled diagnostic24 result | Gemma v3 | V4.1 |
|---|---:|---:|
| Confirmed error sources | **19** | **18** |
| Additional uncertain sources | 2 | 2 |
| Conservative interval | [19, 21] | [18, 20] |

Sixteen confirmed failures are shared, three are Gemma-only, and two are
V4.1-only. The candidate upper bound does not clear the incumbent lower bound,
so R113 parity is not established. This intentionally strict development set
is not a production error-rate estimate. The controlling ledger is
`.context/model-task-20260918/gemma4-classifier-diagnostic24-direct-deepinfra-thinking-v3-2026-09-18-180000/parent-reconciliation.json`;
the independent review remains preserved beside it. The earlier v1/v2 audit is
retained at `.context/model-task-20260918/gemma4-classifier-semantic-audit.md`.

High-confidence examples across the three configurations include:

- `H-H0040D161174`: Gemma repeatedly omitted `cost_performance`; both models
  also miss owner-accepted dimensions in this older case.
- `H-H0DEC6F537E0`: it found `questions_requests` but omitted the accepted
  `ideas_requests` product label.
- `H-H1E48CCEEB2F`: it reduced a reported two-agent experiment to
  `hands_on_usage`, omitting independently supported interpretation/results.
- `H-H8FA9071508D`: it correctly found that Hunyuan context was missing, then
  contradicted that state with neutral/none brand fields and missed the visible
  outside-product promotion.
- `H-HFD61C2DE5BD`: it omitted `agents_tools` from a post centered on assigning
  multiple models to architecture, implementation, review, and arbitration.
- `L-L45-21`: it still read the China/U.S. argument as pro-China and no U.S.
  stance, contrary to the accepted anti-China and constructive-critical-U.S.
  reading.
- `L-L45-22`: both models missed the owner-accepted general untracked-brand
  promotion. Gemma correctly avoided transferring the unnamed competitor's
  release/API attributes to DeepSeek, while V4.1 transferred them.
- `L-L45-45`: v3 dropped `cost_performance` from a hands-on account containing
  both seven-billion-token spend and a $3,000 return.

V3 changed only nine role outputs from v2. Some changes were improvements, but
others were regressions: it restored the MiniMax testimonial on H356, then
dropped results analysis on H74 and H92, dropped `evals_benchmarks` on HFD, and
dropped `cost_performance` on L45-45. This instability matters because the
configuration was supposed to improve independent-axis completeness.

## Cost and speed interpretation

Gemma v3 was about 5.1 times slower than the matching direct V4.1 control in
these serial runs. V3 cost 16.7% more than v1 because it received fewer cache
hits and used the longer checklist; the output volume was nearly unchanged.
The three Gemma classifier runs together produced response-reported charges of
**$0.034025960121**. These are actual response receipts, not a monthly forecast.

Gemma's published standard rate is also above the selected 0731 route's saved
rate on both input and output. Since classification is input-heavy, direct
Gemma does not offer a cost reason to accept weaker or unresolved semantics.

## Decision

Close this bounded Gemma classifier experiment without activation. Its direct
DeepInfra route is mechanically dependable and Gemma remains the qualified
commentary candidate, but task performance is model-specific: this development
set does not establish classifier parity. Continue classifier integration and
staging work with the already selected 0731 two-role route.

## Evidence

- V1: `.context/model-task-20260918/gemma4-classifier-diagnostic24-direct-deepinfra-tagged-v1-2026-09-18-172000/`
- V2: `.context/model-task-20260918/gemma4-classifier-diagnostic24-direct-deepinfra-tagged-v2-2026-09-18-174000/`
- V3: `.context/model-task-20260918/gemma4-classifier-diagnostic24-direct-deepinfra-thinking-v3-2026-09-18-180000/`
- V4.1 control: `.context/model-task-20260917/deepseek-v41-incumbent-classification-v1-diagnostic24/`
- Control report: `docs/research/2026-09-17-201000-direct-deepseek-v41-classifier-diagnostic24-report.md`
