---
title: U18 OpenRouter two-role pilot results
date: 2026-09-14
status: blocked
---

# U18 OpenRouter two-role pilot results

## Plain-English Summary

The frozen three-model comparison completed without selecting a classifier.
Each candidate failed the mandatory 100% complete-pair gate: Qwen3.5 9B
returned malformed JSON, free Gemma 4 31B exhausted its one permitted transport
retry, and Qwen3 235B returned only one brand-interpretation row from each
batch. The 235B route completed all six calls within the cost and pilot-latency
caps, but none of its 45 posts had both required role results, so its quality
scores are ineligible.

The run spent $0.009550375 according to the evaluation key's cumulative usage
immediately after the run, below the frozen $0.042190175 ceiling. No model was
selected, the new two-role classifier remains disabled, and no staging or
production configuration changed. U18A and later activation stages remain
blocked by the plan's explicit gate.

## Frozen inputs

- Budget: `docs/analysis/2026-09-14-190649-u18-r97-two-role-pilot-contract.json`
- Budget SHA-256: `87561d0ac7c8c2610c2a4785e1cb3b377876ebb3006f43c82ee00b0a59559ace`
- Ordered cohort: 45 posts, with 15 EN, 15 JA, and 15 ZH-CN rows
- Batches: 20, 20, and 5 posts
- Roles: content and brand interpretation, run concurrently per batch
- Maximum envelope: 18 initial logical requests, 36 transports, and $0.042190175
- Prompt size: 5,885 combined UTF-8 system-prompt bytes
- Raw provider output: ignored private directory `.context/u18/openrouter-two-role-pilot-v1/`

Immediately before transport, public endpoint checks reconfirmed each exact
provider route, model alias, price, quantization, required JSON parameters,
context/output limits, and availability. All ten frozen local source receipts
also matched.

## Candidate results

| Candidate | Requests | Result | Complete pairs | Cost | Complete-batch p95 |
| --- | ---: | --- | ---: | ---: | ---: |
| Qwen3.5 9B / DeepInfra BF16 | 2 logical / 2 transport | malformed JSON; no semantic retry | 0/45 | $0.0026834975 upper bound | unavailable |
| Gemma 4 31B / Google AI Studio free | 2 logical / 4 transport | both roles exhausted one identical transport retry | 0/45 | $0 | unavailable |
| Qwen3 235B A22B / GMICloud FP8 | 6 logical / 6 transport | valid JSON envelopes, incomplete row sets | 0/45 | $0.0068668775 | 79.277 s |

The 235B content role returned 19/20, 20/20, and 5/5 rows. Its brand role
returned 1/20, 1/20, and 1/5 rows. The deterministic join correctly refused to
publish partial pairs. All six responses came from the pinned GMICloud route;
reported usage was 47,873 input tokens, 7,803 output tokens, and zero reasoning
tokens.

The 9B run exposed an evaluator evidence gap: the original adapter discarded
usage when model content was malformed. The candidate was stopped after its
first pair because coverage could no longer reach 100%. Its cost is therefore
the evaluation key's entire cumulative usage observed immediately after that
failure. The final $0.0026834975 upper bound reconciles the final key total less
the exact 235B charge; the first snapshot rounded it to $0.0026835. Token counts
and request IDs are unavailable. Commit `1aa9257` fixed future malformed-response usage retention
without changing prompts, candidates, caps, or retry policy. The failed request
was not resent.

## Gate decision

No candidate passed coverage, so none was eligible for the 61 quality floors,
the six-axis improvement requirement, per-label regression checks, or
production-capacity selection. Cost alone cannot overcome missing results.

The R97 rule therefore applies: keep the new classifier lane disabled and do
not proceed to U18A, live staging activation, or production promotion. Changing
the output contract, batch shape, prompt, candidate list, or budget would be a
new experiment with a new immutable identity; this consumed cohort cannot be
reported as an unseen validation set.

## Verification

- Expanded bakeoff runner: 14 focused tests passed before transport.
- U18 runner plus foundation after failure-accounting fix: 40 passed with both
  required PostgreSQL tests executed and no skips.
- Broader U18 conformance set before transport: 135 passed, including 45
  required PostgreSQL tests with no skips or errors.
- `makemigrations --check --dry-run`, `manage.py check`, Ruff, and
  `git diff --check` passed at their corresponding checkpoints.

Machine-readable companion:
`docs/analysis/2026-09-14-194529-u18-openrouter-two-role-pilot-results.json`.
