# Per-brand trend narrative evaluation

- Run: `2026-08-27-145235-per-brand-production-activation`
- Reviewer: `codex:fuchitalee:lfg`
- Model: `deepseek-v4-pro`
- Calls: 11
- Cost: $0.056639
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

- EN: ZH Model chatter rises 15% around faster local inference and real-world deployment
- ZH-CN: 围绕更快本地推理与实际部署，中文模型讨论量上升15%
- Secondary EN: Users discussed faster local inference and practical deployment, with post volume up 15% from the prior week.
- Secondary ZH-CN: 用户讨论了更快的本地推理和实际部署，帖子量较前一周上升15%。
- Hold code: ``

### flat-model · 7d · approve

- EN: Flat Model talk centers on local inference and deployment as post volume holds steady
- ZH-CN: 平稳模型讨论聚焦本地推理与部署，帖子量保持平稳
- Secondary EN: Users discussed Flat Model local inference and deployment, with post volume unchanged from the prior week.
- Secondary ZH-CN: 用户讨论了平稳模型的本地推理和实际部署，帖子量与上周持平。
- Hold code: ``

### sparse-lab · 7d · approve

- EN: Sparse Lab discussion touches on local inference and deployment amid sparse sample
- ZH-CN: 稀疏实验室讨论涉及本地推理与部署，样本量稀少
- Secondary EN: Users discussed Sparse Lab local inference and deployment, with 3 posts observed in the window.
- Secondary ZH-CN: 用户讨论了稀疏实验室的本地推理和实际部署，窗口内观察到3条帖子。
- Hold code: ``

### volume-ai · 7d · approve

- EN: AI local-inference chatter jumps 50%, with deployment at the center of the discussion
- ZH-CN: AI本地推理讨论量跃升50%，实际部署成为讨论焦点
- Secondary EN: Volume AI posts centered on local inference and deployment, rising from 3,000 to 4,500 posts this week.
- Secondary ZH-CN: 高量AI的帖子围绕本地推理与部署展开，本周从3,000条增至4,500条。
- Hold code: ``

### official-ai · 7d · approve

- EN: Official AI local-inference discussion grows 35% on first-party posts
- ZH-CN: 官方AI本地推理讨论量增长35%，由官方帖子带动
- Secondary EN: Official AI posts discussed local inference and deployment, moving from 200 to 270 posts, with contributions from @official-ai.
- Secondary ZH-CN: 官方AI帖子讨论了本地推理与部署，从200条增至270条，@official-ai也有发声。
- Hold code: ``

### zh-model · 7d · approve

- EN: ZH Model users highlight faster local inference as posts rise 15%
- ZH-CN: 中文模型用户关注更快的本地推理，帖子量增长15%
- Secondary EN: ZH Model discussion emphasized faster local inference and practical deployment, increasing from 100 to 115 Chinese-language posts.
- Secondary ZH-CN: 中文模型讨论强调更快的本地推理与实际部署，中文帖子从100条增至115条。
- Hold code: ``

### flat-model · 7d · approve

- EN: Flat Model sees steady local-inference talk, but no volume change
- ZH-CN: 平稳模型本地推理讨论保持平稳，帖子量无变化
- Secondary EN: Flat Model posts held at 80, with continued discussion of local inference and deployment.
- Secondary ZH-CN: 平稳模型帖子维持在80条，持续讨论本地推理与部署。
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
  "activation_pass": false,
  "controls": [
    {
      "control": "supported_gold",
      "decision": "hold",
      "expected": "supported",
      "false_accept": 0,
      "false_hold": 1,
      "hold_code": "secondary_not_substantive"
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
  "status": "failed",
  "supported_false_holds": 1,
  "unsupported_false_accepts": 0
}
```

The JSON sibling contains every closed packet, exact provider request, raw response, mechanical result, token count, latency, cost, and bilingual rubric.
