# Per-brand trend narrative evaluation

- Run: `2026-08-27-145235-per-brand-production-activation`
- Reviewer: `codex:fuchitalee:lfg`
- Model: `deepseek-v4-pro`
- Calls: 11
- Cost: $0.063359
- Stop reason: `completed`
- Publication writes: `False`

## Brand outcomes

### sparse-lab · 7d · repair

- EN: Sparse Lab draws light discussion around local inference and deployment
- ZH-CN: 稀疏实验室引发围绕本地推理与部署的轻度讨论
- Secondary EN: Across 3 posts in the current period, users discussed Sparse Lab local inference and practical deployment, with direction marked flat and no verified event or notable shift behind the conversation.
- Secondary ZH-CN: 在当前期间的3条帖子中，用户讨论了稀疏实验室的本地推理和实际部署，但没有明显变化或经核实的事件可以解释这一讨论。
- Hold code: ``

### zh-model · 7d · approve

- EN: ZH Model chatter rises on local inference and deployment
- ZH-CN: 中文模型围绕本地推理与部署的讨论升温
- Secondary EN: Two user posts discuss faster local inference and practical deployment, as post volume rises 15%.
- Secondary ZH-CN: 两条用户帖子讨论了更快的本地推理和实际部署，帖子量上升15%。
- Hold code: ``

### flat-model · 7d · approve

- EN: Flat Model discussion holds steady on local inference
- ZH-CN: 平稳模型围绕本地推理的讨论保持平稳
- Secondary EN: Two user posts discuss Flat Model local inference and deployment, with post volume unchanged at 0%.
- Secondary ZH-CN: 两条用户帖子讨论了平稳模型的本地推理和部署，帖子量持平，变化为0%。
- Hold code: ``

### sparse-lab · 7d · hold

- EN: —
- ZH-CN: —
- Secondary EN: —
- Secondary ZH-CN: —
- Hold code: `proportionality_failure`

### volume-ai · 7d · repair

- EN: Volume AI chatter surged on local inference and deployment.
- ZH-CN: 高量AI关于本地推理和部署的讨论激增。
- Secondary EN: User posts centered on local inference and deployment, with post volume rising from 3,000 to 4,500 week over week.
- Secondary ZH-CN: 用户帖子集中在本地推理和部署上，帖子量周环比从3,000增至4,500。
- Hold code: ``

### official-ai · 7d · repair

- EN: Official AI local inference talk grew alongside a 35% post-volume rise.
- ZH-CN: 官方AI本地推理讨论升温，帖子量增长35%。
- Secondary EN: Posts centered on local inference and deployment as volume rose from 200 to 270; official posts were present.
- Secondary ZH-CN: 帖子集中讨论本地推理和部署，帖子量从200增至270；存在官方帖子。
- Hold code: ``

### zh-model · 7d · approve

- EN: ZH Model users discussed faster local inference and practical deployment.
- ZH-CN: 中文模型用户讨论了更快的本地推理和实际部署。
- Secondary EN: The conversation concentrated on faster local inference and deployment, while post volume rose 15% from 100 to 115.
- Secondary ZH-CN: 讨论集中在更快的本地推理和部署上，帖子量从100增至115，增长15%。
- Hold code: ``

### flat-model · 7d · repair

- EN: Flat Model conversation stayed on local inference and deployment.
- ZH-CN: 平稳模型的讨论仍集中在本地推理和部署上。
- Secondary EN: User posts continued to cover local inference and deployment, with volume unchanged at 80 posts.
- Secondary ZH-CN: 用户帖子继续围绕本地推理和部署展开，帖子量保持在80条不变。
- Hold code: ``

### sparse-lab · 7d · repair

- EN: Sparse Lab discussion touched on local inference and deployment.
- ZH-CN: 稀疏实验室的讨论涉及本地推理和部署。
- Secondary EN: User activity amounted to 3 posts on local inference and deployment; prior-period comparison was unavailable.
- Secondary ZH-CN: 用户活动有3条关于本地推理和部署的帖子；无法进行上期比较。
- Hold code: ``

## Critic calibration

```json
{
  "activation_pass": true,
  "controls": [
    {
      "control": "supported_gold",
      "decision": "repair",
      "expected": "supported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": null
    },
    {
      "control": "unsupported_event",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "unsupported_event"
    }
  ],
  "supported_false_holds": 0,
  "unsupported_false_accepts": 0
}
```

The JSON sibling contains every closed packet, exact provider request, raw response, mechanical result, token count, latency, cost, and bilingual rubric.

## Pre-activation corrections

Earlier bounded runs exposed three critical contract defects before this pass:

- Python treated proposition claims as literal substrings of rendered copy,
  rejecting harmless paraphrases and punctuation changes.
- Python required every cited fact display string to appear verbatim, so valid
  wording such as “held steady” failed unless it also printed `0%`.
- The original supported critic control introduced the unsupported word
  “tradeoffs,” and the synthetic flat/sparse baselines were internally
  inconsistent.

The final contract leaves semantic support and numeric expression to the
closed-packet critic; Python owns schema, completeness, packet-owned IDs,
budgets, and independent per-brand persistence. Synthetic baselines and the
supported control now use only packet-supported content. Regression tests also
prove one malformed brand is held without discarding valid brands in the same
critic batch.
