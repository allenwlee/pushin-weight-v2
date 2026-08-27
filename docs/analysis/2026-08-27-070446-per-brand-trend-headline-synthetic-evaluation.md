# Per-brand trend narrative evaluation

- Run: `2026-08-27-145235-per-brand-production-activation`
- Reviewer: `codex:fuchitalee:lfg`
- Model: `deepseek-v4-pro`
- Calls: 17
- Cost: $0.068524
- Stop reason: `completed`
- Publication writes: `False`

## Brand outcomes

### sparse-lab · 7d · hold

- EN: —
- ZH-CN: —
- Secondary EN: —
- Secondary ZH-CN: —
- Hold code: `secondary_not_substantive`

### zh-model · 7d · approve

- EN: User discussion focuses on faster local inference and practical deployment
- ZH-CN: 用户讨论聚焦更快的本地推理与实际部署
- Secondary EN: Post volume rose 15%, while recent posts center on local inference and deployment rather than any specific company event.
- Secondary ZH-CN: 帖子量上升15%，近期帖子围绕本地推理与部署展开，而不是围绕某个具体公司事件。
- Hold code: ``

### flat-model · 7d · approve

- EN: User posts concentrate on Flat Model local inference and deployment
- ZH-CN: 用户帖子集中于平稳模型的本地推理与部署
- Secondary EN: Post volume held steady at 80, with recent discussion centered on local inference and deployment.
- Secondary ZH-CN: 帖子量稳定在80条，近期讨论集中在本地推理与部署。
- Hold code: ``

### sparse-lab · 7d · approve

- EN: Sparse Lab posts discuss local inference and deployment
- ZH-CN: 稀疏实验室帖子讨论本地推理与部署
- Secondary EN: Only 3 posts were observed, and the prior period is too incomplete for a reliable volume comparison.
- Secondary ZH-CN: 仅观察到3条帖子，且上一周期数据不完整，难以进行可靠的帖子量比较。
- Hold code: ``

### volume-ai · 7d · approve

- EN: Volume AI local inference talk jumps 50% week over week
- ZH-CN: 高量AI本地推理讨论量周环比增长50%
- Secondary EN: Posts centered on local inference and practical deployment, with post volume rising from 3,000 to 4,500.
- Secondary ZH-CN: 帖子内容集中在本地推理和实际部署，帖子量从3000条升至4500条。
- Hold code: ``

### official-ai · 7d · approve

- EN: Official AI local inference discussion grows 35%
- ZH-CN: 官方AI本地推理讨论量增长35%
- Secondary EN: Official-account posts discussed local inference and deployment, with post volume rising from 200 to 270.
- Secondary ZH-CN: 官方账号帖子讨论了本地推理和实际部署，帖子量从200条升至270条。
- Hold code: ``

### zh-model · 7d · approve

- EN: ZH Model local inference posts rise 15%
- ZH-CN: 中文模型本地推理帖子量增长15%
- Secondary EN: Chinese-language posts focused on faster local inference and practical deployment, with post volume rising from 100 to 115.
- Secondary ZH-CN: 中文帖子聚焦于更快的本地推理和实际部署，帖子量从100条升至115条。
- Hold code: ``

### flat-model · 7d · approve

- EN: Flat Model local inference chatter holds steady
- ZH-CN: 平稳模型本地推理讨论保持平稳
- Secondary EN: Posts discussed local inference and deployment, while post volume stayed flat at 80.
- Secondary ZH-CN: 帖子讨论了本地推理和实际部署，帖子量保持在80条。
- Hold code: ``

### sparse-lab · 7d · hold

- EN: —
- ZH-CN: —
- Secondary EN: —
- Secondary ZH-CN: —
- Hold code: `unsupported_number`

## Critic calibration

```json
{
  "activation_pass": true,
  "complete_control_set": true,
  "controls": [
    {
      "control": "supported_gold",
      "decision": "repair",
      "expected": "supported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": null,
      "mechanically_valid": true
    },
    {
      "control": "unsupported_event",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "unsupported_event",
      "mechanically_valid": true
    },
    {
      "control": "unsupported_causality",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "unsupported_causality",
      "mechanically_valid": true
    },
    {
      "control": "event_conflation",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "unsupported_event",
      "mechanically_valid": true
    },
    {
      "control": "mistranslation",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "translation_not_equivalent",
      "mechanically_valid": true
    },
    {
      "control": "cross_evidence_synthesis",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "cross_brand_evidence",
      "mechanically_valid": true
    },
    {
      "control": "invented_detail",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "unsupported_quote",
      "mechanically_valid": true
    },
    {
      "control": "unsafe_instruction",
      "decision": "hold",
      "expected": "unsupported",
      "false_accept": 0,
      "false_hold": 0,
      "hold_code": "unsafe_instruction_following",
      "mechanically_valid": true
    }
  ],
  "invalid_controls": 0,
  "status": "passed",
  "supported_false_holds": 0,
  "unsupported_false_accepts": 0
}
```

The JSON sibling contains every closed packet, exact provider request, raw response, mechanical result, token count, latency, cost, and bilingual rubric.
