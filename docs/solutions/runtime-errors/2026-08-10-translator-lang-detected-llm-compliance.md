---
title: "Translator omitted lang_detected; allowlist + validate + one repair"
date: 2026-08-10
category: runtime-errors
module: x_monitor
problem_type: runtime_error
component: tooling
severity: medium
symptoms:
  - "lang_detected NULL on ~20-28% of fresh posts while text_en/text_zh_cn often populated"
  - "Server-side EN/ZH noop misbehaves when lang is missing"
root_cause: logic_error
resolution_type: code_fix
tags:
  - translator
  - lang_detected
  - deepseek
  - prompt-compliance
related_components:
  - x_monitor/translator.py
  - tests/test_translator_lang_detected_compliance.py
  - docs/plans/2026-08-10-004-fix-translator-lang-detected-llm-compliance-plan.md
---

# Translator omitted lang_detected; allowlist + validate + one repair

### written by Grok 4.5

## Problem

The pragmatics translator often left `lang_detected` empty while still writing translation text. Soft LLM schema omission (not full batch failure). Noop rules depend on lang, so missing lang corrupted column semantics.

## Solution

Plan `docs/plans/2026-08-10-004-fix-translator-lang-detected-llm-compliance-plan.md`:

1. Closed allowlist + normalize (`en`, `zh-Hans`, `zh-Hant`, `ja`, `ko`, `other`).
2. Language-first prompt; remove hard 280-char-per-post rule.
3. Post-parse validate; **one** repair LLM call for bad tweet_ids only.
4. Repair merge: keep first-pass texts if repair only fills lang.
5. Residual invalid → failed empty row (no null-lang success).
6. X API `lang` not used (unreliable).

## Prevention

- `tests/test_translator_lang_detected_compliance.py` (M18 call-chain through `translate_batch_pragmatics`).
- Never persist success rows with null `lang_detected`.
