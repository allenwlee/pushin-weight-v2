# U18 R99 DeepSeek batch-size pilot receipt

- Contract: `docs/analysis/2026-09-15-071753-u18-r99-deepseek-batch-size-pilot-contract.json`
- Frozen at: `2026-09-15T07:17:53+09:00`
- Purpose: provider-free design for the owner-authorized DeepSeek-only two-role test.
- Inference requests made: **0**; no provider endpoint, API key, or secret was used.
- Source manifest SHA-256: `50f46d0d8583f91c316583704efe314ddf98c6306032d9dfd3e0543da1497c91` (45 rows; order preserved)
- Owner-reference SHA-256: `d1c390c0f689e5aae4648a60f5a8878a82e5471fda1c9d6bfe72cee4ab215f80` (45 post-brand rows)
- Quality-floor SHA-256: `881a2e297bad803851a42d629b5519b5e0a200f38d055dd5951c194aefaf79ba`
- Prior R98 budget SHA-256: `b7eacdefbcf59c125fe796ef1585cbce2f2e3cbcb00193f0c23bf61bd531be6c` (`docs/analysis/2026-09-14-213123-u18-r98-control-fallback-pilot-contract.json`)
- Prior R98 result SHA-256: `be736ee1d1144cd917288009ab3f57aae6fc4577356797646a6efad437aba8c4` (`docs/analysis/2026-09-14-221023-u18-r98-control-fallback-pilot-results.json`)
- Prior R98 receipt SHA-256: `662b9421cf5b16dbe23f7605eb0b95aec6ae3820b80c85518f562bde4f5d4bf1` (`docs/research/2026-09-14-213123-u18-r98-control-fallback-receipt.md`)
- Prior R98 terminal evidence is immutable; R99 must not replay R98 responses.

## Frozen route and contract

The candidate is direct `deepseek-v4-flash` through the production Anthropic-compatible DeepSeek client, with provider `deepseek`, no fallback, no service tier, and reasoning disabled. The production two-role prompts, parser, merge contract, privacy packet, and owner-reference scoring remain those frozen by R98. R99 intentionally changes two controls: ordered batches are **40/5** rather than 20/20/5, and `max_tokens=8000` is frozen for each role call to provide enough output for the 40-row batch under the production scaling policy.

## Cap arithmetic

- Conservative combined input bounds: `122533 + 38768 = 161301` tokens per initial two-role batch pair.
- One identical retry envelope: `161301 * 2 = 322602` input tokens.
- Logical requests: `2 batches * 2 roles = 4`.
- Transport attempts: `4 logical * 2 attempts = 8`.
- Output ceiling: `4 logical * 2 attempts * 8000 = 64000` tokens.
- Reasoning ceiling: `0`.
- Spend hard cap: `(322602 * $0.44 + 64000 * $1.32) / 1000000 = $0.22642488 USD`.
- Cost per 1000 source posts at hard cap: `$0.22642488 * 1000 / 45 = $5.03166400 USD`.

All caps are global and per-model, reserved before dispatch; no inference or durable raw output exists for R99.
