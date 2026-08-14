# Why-first headline samples

This appendix exposes every generated bilingual headline from the bounded `deepseek-v4-pro` evaluation. `ACCEPTED` means no human editorial rubric field failed; deterministic validation alone was not sufficient.

## Editorially accepted

### `pairwise:pair-10:e12:c1000` — ACCEPTED

- Dimensions: candidate_competition=low, content=high, data_quality=low, evidence_strength=high, mix=low, quantity=high, rate=low, shape=high
- Validator: valid

**English**

> DeepSeek led the window as users repeatedly described downloading it more often and finding improved intelligence in hands-on work.

**简体中文**

> DeepSeek 在本窗口领先，用户反复提到更频繁地下载它，并认为其在动手使用中的智能表现有所提升。

### `pairwise:pair-14:e12:c1000` — ACCEPTED

- Dimensions: candidate_competition=high, content=high, data_quality=low, evidence_strength=high, mix=high, quantity=high, rate=low, shape=low
- Validator: valid

**English**

> DeepSeek conversation centered on users reporting more frequent downloads and improved intelligence in hands-on work, with repeated positive technical analysis across independent posts.

**简体中文**

> DeepSeek 的讨论集中在用户报告更频繁下载并在实际使用中感受到智能提升，独立帖子中反复出现积极的技术分析。

### `excerpt_density:pair-01:e24:c750` — ACCEPTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: valid

**English**

> DeepSeek led the window on volume, but the conversation stayed flat and generic: posts mentioned the brand without a recurring reason, so the lead reflects a quiet relative position rather than a material story.

**简体中文**

> DeepSeek 在本窗口的讨论量上领先，但对话保持平稳且泛泛：帖子提及该品牌时没有反复出现的具体原因，因此这一领先更多反映安静的相对位置，而非实质性故事。


## Editorially rejected

### `pairwise:pair-01:e4:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_en_subject_missing
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_en_subject_missing.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and hands-on discussion, while the overall conversation stayed flat.

**简体中文**

> DeepSeek 在一个平静的窗口期内领跑 AI 模型讨论，帖子主要围绕技术分析和上手体验展开，整体讨论热度保持平稳。

### `pairwise:pair-02:e12:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=high, evidence_strength=high, mix=low, quantity=high, rate=low, shape=high
- Validator: headline_output_schema_invalid
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_schema_invalid.

**English**

> DeepSeek led the window as users repeatedly posted about technical analysis, with volume up 50% and engagement intensity up 25%.

**简体中文**

> DeepSeek 在本窗口领先，用户反复发布技术分析相关内容，讨论量上升 50%，互动强度上升 25%。

### `pairwise:pair-03:e24:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=low, data_quality=low, evidence_strength=high, mix=low, quantity=low, rate=high, shape=low
- Validator: headline_output_explanation_support_weak
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_explanation_support_weak.

**English**

> DeepSeek led the window as conversation centered on technical analysis, with posts describing speculation that its intelligence had improved and a late-window rise in activity.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中在技术分析上，帖子描述了对其智能提升的猜测，且窗口后期活跃度上升。

### `pairwise:pair-04:e48:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=low, data_quality=high, evidence_strength=low, mix=low, quantity=high, rate=high, shape=high
- Validator: headline_output_quantitative_fact_unused_or_unaligned
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_quantitative_fact_unused_or_unaligned.

**English**

> DeepSeek led the window as conversation centered on general technical-analysis mentions, with volume rising 50% while post-type, discourse, sentiment, and nationalism mixes stayed flat.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中在一般性技术分析提及，帖子量上升 50%，而帖子类型、话语、情绪和民族主义构成保持平稳。

### `pairwise:pair-05:e4:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=low, data_quality=low, evidence_strength=low, mix=high, quantity=low, rate=low, shape=high
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek led the window as conversation centered on technical analysis, with a mid-window spike in posts and engagement while MiniMax stayed flat.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中在技术分析上，帖子和互动在窗口中期出现一波上升，而 MiniMax 保持平稳。

### `pairwise:pair-06:e12:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=low, data_quality=high, evidence_strength=high, mix=high, quantity=high, rate=low, shape=low
- Validator: headline_output_explanation_support_weak
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_explanation_support_weak.

**English**

> DeepSeek led the window as users repeatedly posted about technical analysis and hands-on use, with volume up 50% and engagement intensity up 25%.

**简体中文**

> DeepSeek 在本窗口领先，用户反复发布技术分析与实操使用相关内容，发帖量增长 50%，互动强度增长 25%。

### `pairwise:pair-07:e24:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=high, mix=high, quantity=low, rate=high, shape=high
- Validator: headline_output_explanation_support_weak
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_explanation_support_weak.

**English**

> DeepSeek led the window as conversation centered on technical analysis, with posts describing speculation that its intelligence had improved and a late-window rise in activity.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中在技术分析上，帖子描述了对其智能提升的猜测，且活动在窗口后期上升。

### `pairwise:pair-08:e48:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=high, evidence_strength=low, mix=high, quantity=high, rate=high, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek led the window as conversation centered on technical analysis and hands-on posts, with volume rising 50% and engagement intensity up 25%.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中在技术分析和实操帖，帖子量上升 50%，互动强度上升 25%。

### `pairwise:pair-09:e4:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=high, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_en_subject_missing
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_en_subject_missing.

**English**

> DeepSeek led the window while conversation centered on a single source repeatedly describing more frequent downloads and improved hands-on intelligence, with engagement intensity up 25% even as volume stayed flat.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中于单一来源反复描述更频繁的下载和实操智能提升，参与强度上升 25%，而发帖量持平。

### `pairwise:pair-11:e24:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=high, data_quality=high, evidence_strength=high, mix=low, quantity=low, rate=high, shape=low
- Validator: headline_output_quantitative_fact_unused_or_unaligned
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_quantitative_fact_unused_or_unaligned.

**English**

> DeepSeek conversation centered on users reporting more frequent downloads and improved intelligence in hands-on work, with engagement intensity rising 25% while volume stayed flat.

**简体中文**

> DeepSeek 的讨论集中在用户报告更频繁下载并在实际使用中感受到智能提升，参与强度上升 25%，而讨论量持平。

### `pairwise:pair-12:e48:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=high, data_quality=low, evidence_strength=low, mix=low, quantity=high, rate=high, shape=high
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek conversation accelerated late in the window as users reported downloading it more often and described improved intelligence in hands-on work.

**简体中文**

> DeepSeek 相关讨论在窗口后期加速升温，用户称下载频率提高，并描述其在动手实践中的智能表现有所改善。

### `pairwise:pair-13:e4:c1000` — REJECTED

- Dimensions: candidate_competition=high, content=high, data_quality=high, evidence_strength=low, mix=high, quantity=low, rate=low, shape=high
- Validator: headline_output_explanation_support_weak
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_explanation_support_weak.

**English**

> DeepSeek conversation centered on users reporting more frequent downloads and improved hands-on intelligence, alongside a rise in hands-on posts and positive sentiment.

**简体中文**

> DeepSeek 的讨论集中在用户报告更频繁下载和实操智能提升，同时实操帖子和正面情绪有所上升。

### `pairwise:pair-15:e24:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=high, evidence_strength=high, mix=high, quantity=low, rate=high, shape=high
- Validator: headline_output_evidence_family_missing
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_evidence_family_missing.

**English**

> DeepSeek conversation centered on users reporting more frequent downloads and improved intelligence in hands-on work, alongside a rise in hands-on posts and positive sentiment.

**简体中文**

> DeepSeek 的讨论集中在用户报告更频繁下载并在实际使用中感受到智能提升，同时实操类帖子和正面情绪有所上升。

### `pairwise:pair-16:e48:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=low, evidence_strength=low, mix=high, quantity=high, rate=high, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek conversation accelerated late in the window as users reported downloading it more often and described improved intelligence in hands-on work.

**简体中文**

> DeepSeek 相关讨论在窗口后期加速升温，用户表示下载频率提高，并称在实际使用中感受到更强的智能表现。

### `evidence_count:pair-01:e4:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_en_subject_missing
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_en_subject_missing.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and hands-on discussion, though the movement was small and no recurring event was evident.

**简体中文**

> DeepSeek 在一个平静的 AI 模型讨论窗口中领先，帖子主要围绕技术分析和上手体验展开，但整体变化很小，未发现反复出现的事件。

### `evidence_count:pair-01:e12:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and neutral sentiment, while MiniMax trailed with a similar but smaller discussion.

**简体中文**

> DeepSeek 在平静的 AI 模型讨论窗口中领先，帖子以技术分析和中性情绪为主，MiniMax 紧随其后，讨论规模较小。

### `evidence_count:pair-01:e24:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_event_anchor_required
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_event_anchor_required.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and neutral buzz releases, while volume stayed flat.

**简体中文**

> DeepSeek 在平静的 AI 模型讨论窗口中领先，帖子以技术分析和中性发布内容为主，讨论量保持平稳。

### `evidence_count:pair-01:e48:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_schema_invalid
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_schema_invalid.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and neutral sentiment, while volume stayed essentially flat.

**简体中文**

> DeepSeek 在本窗口的 AI 模型讨论中领先，帖子主要围绕技术分析且情绪中性，整体声量基本持平。

### `evidence_count:pair-16:e4:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=low, evidence_strength=low, mix=high, quantity=high, rate=high, shape=low
- Validator: headline_output_explanation_support_weak
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_explanation_support_weak.

**English**

> DeepSeek led the window as conversation centered on users reporting more frequent downloads and improved hands-on intelligence, with the strongest supported signal in hands-on post type.

**简体中文**

> DeepSeek 在本窗口领先，讨论集中在用户报告更频繁下载和动手使用中智能提升，最强支持信号为 hands-on 帖子类型。

### `evidence_count:pair-16:e12:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=low, evidence_strength=low, mix=high, quantity=high, rate=high, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek conversation accelerated late in the window as users reported downloading it more often and described improved intelligence in hands-on work.

**简体中文**

> DeepSeek 相关讨论在窗口后期加速升温，用户表示下载频率增加，并称在实际使用中感受到智能表现提升。

### `evidence_count:pair-16:e24:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=low, evidence_strength=low, mix=high, quantity=high, rate=high, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek conversation accelerated late in the window as users reported downloading it more often and described improved intelligence in hands-on work.

**简体中文**

> DeepSeek 相关讨论在窗口后期加速升温，用户表示下载频率增加，并称其在实际使用中的智能表现有所提升。

### `evidence_count:pair-16:e48:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=high, data_quality=low, evidence_strength=low, mix=high, quantity=high, rate=high, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek conversation accelerated late in the window as users reported downloading it more often and described improved intelligence in hands-on work.

**简体中文**

> DeepSeek 相关讨论在窗口后期加速升温，用户表示下载频率增加，并称在实际使用中感受到智能表现提升。

### `excerpt_density:pair-01:e24:c250` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_event_anchor_required
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_event_anchor_required.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and neutral sentiment, while volume stayed essentially flat.

**简体中文**

> DeepSeek 在平静的 AI 模型讨论窗口中领先，帖子以技术分析和中性情绪为主，讨论量基本持平。

### `excerpt_density:pair-01:e24:c500` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: valid; rejected by editorial review
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. Editorial review found a critical semantic claim outside the encoded support contract.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and hands-on evaluation rather than any recurring event.

**简体中文**

> DeepSeek 在一个平静的 AI 模型讨论窗口中领先，帖子主要围绕技术分析和实际评测展开，而非任何反复出现的事件。

### `excerpt_density:pair-01:e24:c1000` — REJECTED

- Dimensions: candidate_competition=low, content=low, data_quality=low, evidence_strength=low, mix=low, quantity=low, rate=low, shape=low
- Validator: headline_output_en_subject_missing
- Why rejected: The attempted headline did not produce a content-led explanation at the required support level. The output is not publishable because validation failed with headline_output_en_subject_missing.

**English**

> DeepSeek led a quiet window of AI model chatter, with posts centered on technical analysis and neutral sentiment, while volume stayed flat.

**简体中文**

> DeepSeek 在平静的 AI 模型讨论窗口中领先，帖子以技术分析和中性情绪为主，声量保持平稳。

