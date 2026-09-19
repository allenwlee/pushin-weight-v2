# SetFit and alternatives for PushinWeight: recent experience

Researched: 2026-09-15, Asia/Tokyo  
Window: 2026-08-16 through 2026-09-15  
Request: `$last30days experience with setfit and alternatives given our use-case`  
Status: research and candidate recommendations; no training or application change performed.

**Recommendation: pursue teacher–student classification, but treat SetFit as a baseline to beat.** Compare it with a directly trained multilingual encoder. Keep GLiClass as a bounded third candidate, particularly for changing Audience Topics. Recent experience establishes that small classifiers can be inexpensive; it does not establish frontier-quality performance on our overlapping, brand-specific labels.

## What recent users actually reported

| Recent source | Reported result | Relevance and limit |
|---|---|---|
| Daniel van Strien, September 10 | SetFit trained on 200 agent-labeled documents; 65.8% accuracy and 0.556 macro F1 on 120 held-out, also agent-labeled documents. Classified 191,724 documents for about $0.70 inference compute; training/model selection about $2.90. | Close to our proposed labeling workflow, but six exclusive English categories. Agent/storage costs excluded; evaluation is agreement with agent labels, not independent human truth. [Write-up](https://danielvanstrien.xyz/posts/2026/agents-data-curation/index.html) |
| Snival intent-router release, created August 28, updated August 31 | Chinese/English SetFit router: 5,237 training examples, 21 classes; 0.699 accuracy and 0.554 macro F1 on 695 test cases. Of its errors, 65.6% had raw confidence at least 0.99. | More multilingual and contextual, yet exclusive intent classification. Its rare-class results varied sharply between test slices. A raw confidence cutoff is not a demonstrated way to select safe automatic decisions. [Model card](https://huggingface.co/snival/intent-router-zh-setfit-v2) |
| SetFit maintainers, September 4 | v1.2.0 fixes compatibility with newer Transformers, Hugging Face Hub and Datasets versions, with additional Python and export support. | Active maintenance; old installation errors need not disqualify it. This release is not evidence of better semantic accuracy. [Release](https://github.com/huggingface/setfit/releases/tag/v1.2.0) |
| Daniel van Strien, August 17 | Generated 35,837 teacher summaries for $15.58, or $20.60 including preparation/calibration runs. | Demonstrates practical preparation of a training dataset without a local GPU. The article reports data generation, not completed student training or classification quality. [Write-up](https://danielvanstrien.xyz/posts/2026/distilling-qwen38-datatrove-jobs/index.html) |

Macro F1 gives each label equal weight when balancing correct detections against misses and false alarms; accuracy can look better when common categories dominate. These scores come from different datasets and are not comparable with each other or with our saved 45-case scores.

The X search returned three posts about the first SetFit experiment, not three independent successful deployments. The author's post had 46 likes; the other two were an amplification and a criticism of the small teacher-labeled seed set. A fourth author described ModernBERT-to-tree distillation, but the task and student results were insufficiently documented to select that design for us. Source links and search-reported engagement are preserved in the [source inventory](./2026-09-15-153103-u18-setfit-alternatives-last30days-sources.json).

A September 11 paper, DualMLC, combines encoder and decoder predictors for very large label vocabularies. It is relevant research, but its two-branch architecture and large-label ranking benchmarks do not establish an economical solution to our much smaller taxonomy. I would not add it to the first experiment. [Paper](https://arxiv.org/abs/2609.12915)

## Which alternatives fit our task

The following capability evidence includes older models and current documentation. It is not presented as last-month community consensus.

| Candidate | What we would actually run | Why test it | Main uncertainty |
|---|---|---|---|
| Frozen multilingual embeddings, then SetFit | First train inexpensive label predictors on unchanged embeddings; then adapt the same encoder with SetFit and compare. | Separates the value of task-specific training from simply using good embeddings. | Similar-looking posts can require different labels for different target brands. |
| Supervised mmBERT, with XLM-R as an alternate backbone | Train a multilingual text encoder and the label predictors together on Sol-labeled post-brand examples. | Directly optimizes the outputs we need; my strongest alternative when SetFit loses contextual distinctions. | More training work and no measured advantage on our data yet. |
| GLiClass Multilang Mini | Supply label descriptions and the target-brand context to a classifier that scores candidate labels. | Especially interesting for Audience Topics whose definitions change over time. | Japanese coverage and our subtle attribution rules are unproven. |
| Small generative model fine-tuned on Sol labels | Train a compact language model to emit our complete structured answer. | Reuses the same training data if the encoder approaches cannot learn enough context. | Serving cost and latency may be higher; must measure rather than assume savings. |
| GLiNER2 | Test its schema-based classification alongside entity extraction in a later, separately scoped comparison. | Potentially useful when jobs/personnel extraction becomes the objective. | Multilingual checkpoint coverage and our whole contract need verification; do not expand the first trial merely to include it. |

SetFit supports multiple simultaneous labels, including one-vs-rest and multi-output strategies. Our combination of overlapping labels, exclusive axes and unknown states still requires explicit integration. The library does not automatically implement the complete application contract. [SetFit documentation](https://huggingface.co/docs/setfit/how_to/multilabel)

A concrete inexpensive backbone to screen is `intfloat/multilingual-e5-small`. Its card documents 100-language support, a 512-token limit and the required `query: ` prefix for classification features. Preserve that preprocessing contract and measure how much post/quote/affiliation context would be truncated before choosing it. [Model card](https://huggingface.co/intfloat/multilingual-e5-small)

mmBERT offers multilingual small/base encoders with 140M/307M parameters and an 8,192-token context limit. Its classification fine-tuning examples make it a plausible direct-training alternative; the longer limit does not mean we should fill it on every post. XLM-R is another multilingual backbone designed for task fine-tuning. Neither documentation proves our intended accuracy or CPU cost. [mmBERT](https://huggingface.co/jhu-clsp/mmBERT-base), [XLM-R](https://huggingface.co/FacebookAI/xlm-roberta-base)

GLiClass accepts descriptions, task prompts and grouped labels, which could reduce the retraining burden when topics change. However, Japanese is absent from this checkpoint's stated training-language list and its presented multilingual benchmark. That gap matters to us. Mini is approximately 288M parameters; its vendor-reported multilingual benchmark is stronger than the smaller Edge model's. Those are vendor results on other tasks, and the published throughput uses a powerful GPU. [Mini](https://huggingface.co/knowledgator/gliclass-multilang-mini), [Edge](https://huggingface.co/knowledgator/gliclass-multilang-edge)

GLiNER2's documentation supports multiple classification fields, label descriptions and multilabel outputs. This is a capability check, not an independently verified deployment result for our use case. [Tutorial](https://github.com/fastino-ai/GLiNER2/blob/main/tutorial/1-classification.md)

## What this changes in our thinking

1. **Train a primary classifier that scores every required label.** It would substitute for the classification work now attempted by primary and follow-up calls. A fixed output for each label prevents omitted fields, but it can still assign too low a score to a valid secondary label. This addresses output mechanics, not accuracy by itself.
2. **“Simple posts” should mean empirically reliable decisions, not short text.** A short sarcastic post can be harder than a long explicit job listing. Rare categories can belong in the student if training examples and evaluation establish adequate performance.
3. **Training data should encode brand relationships, not just keywords.** Preserve target brand, reviewed author affiliation, source language, post text and available quote/parent evidence. Train with same-post/different-brand examples. DeepSeek promotion must not become MiniMax promotion merely because MiniMax is mentioned.
4. **Label absence and missing evidence are different.** Keep unsupported or unreviewed fields distinguishable from reliable negatives. Existing Sol trials do not automatically supply newly proposed Audience Topics, Geopolitical modes or promotion semantics.
5. **Frontier supervision is most economical offline.** Confidence-based escalation is an option to evaluate, not a free correctness guarantee. Also audit apparently confident decisions and rare labels; otherwise the most important misses may never reach the teacher.

These are recommendations inferred from the research and our existing errors, not claims that any student already passes our tests.

## Bounded comparison after the fresh 45-case review

The next scheduled evaluation remains Sol through OpenRouter on the owner's fresh 45-case packet. Keep those posts, duplicates and thread groups outside training, prompt examples and tuning. The earlier 45-case owner review remains complete.

After that evaluation, reuse the existing proposal of about 2,000 Sol-labeled post-brand examples as a starting experiment, not a sufficiency guarantee. Combine natural-frequency sampling with deliberate rare-label and attribution cases. Show how quality changes as more training examples are added; do not assume a few examples per category will cover rare labels across languages.

Start with frozen multilingual embeddings and SetFit on the same backbone, then compare a directly trained multilingual encoder. Give GLiClass a small preliminary language/brand-attribution check before investing in adaptation. Use the same evidence contract and grouped train/development/test partitions for all candidates. Teacher-labeled evaluation measures agreement with the teacher; retain the distinction from owner-confirmed judgments.

Measure missed and extra labels separately, including second/third post types; rare-label recall; exact complete-row correctness; language and target-brand errors; CPU memory, startup and batch latency; and total projected cost. Evaluate both a natural-frequency sample and a rare-case challenge set. A good aggregate score cannot compensate silently for losing job listings or personnel changes.

Use separate development data to choose per-label thresholds and check confidence calibration. Repeated training runs can expose instability. Any later taxonomy change needs versioned training/label updates; new prompt text alone does not teach an already-trained fixed-label student.

## Budget implication

Our saved R106 measurements were $0.136168 for Sol-low and $0.00600291 for DeepSeek primary at the recorded off-peak price, each on 45 examples. Sol was about 22.68 times as expensive in that comparison. These are historical trial costs, not current price quotes or population traffic estimates. [Saved results](../analysis/2026-09-15-134818-u18-r106-sol-reasoning-results.md)

Under that particular ratio, forwarding 10% of production examples to Sol would itself cost about 2.27 times the old classifier budget, before student compute. To achieve a tenfold classification-cost reduction, the theoretical fallback ceiling is about 0.44% even if the student is free and teaching costs are excluded. Real traffic and pricing may change the calculation, but frequent frontier fallback cannot be assumed compatible with the goal.

Prefer amortized offline teaching, then measure student serving and periodic refresh costs. The $150/month constraint still includes translation and other LLM calls. CPU/GPU hosting is a separate real operating expense even when generative API tokens disappear; measure it rather than moving cost off the LLM invoice and declaring success.

This report supplements the [existing teacher–student feasibility note](./2026-09-15-145139-u18-sol-teacher-small-classifier-feasibility.md); it does not start training or alter the canonical plan.

## Search method and limitations

Ran the requested last30days skill across Reddit, X, YouTube and web, then supplemented with direct primary-source searches, model cards, maintainer releases and public timestamp APIs.

- Reddit search timed out; supplementary searches found no verified relevant thread in the requested window.
- X returned four relevant posts. Direct web opening failed, so X dates/engagement are search-retrieved metadata; the central SetFit story was checked against its author's full article.
- YouTube search ran and returned zero. The compact renderer's contradictory “yt-dlp not installed” line is not treated as a verified installation failure.
- Twelve selected web pages support this report: five dated recent sources and seven background technical references. Multiple pages from a project do not count as independent experiments.
- Excluded undated search-index recency, mirrors, duplicate promotional announcements, irrelevant GitHub issues, and an article whose full text/date could not be reliably reopened. No exact-match independent production benchmark was found.

Evidence: [selected source inventory](./2026-09-15-153103-u18-setfit-alternatives-last30days-sources.json). Raw script report, stdout/stderr and date checks are archived under `.context/research/setfit-last30days-20260915/` in this worktree.

📊 Sources: 0 Reddit · 4 X · 0 YouTube · 12 Web

⏱️ Research time: 13m 52s
