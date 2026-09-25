# Post translation output
The current Django post-fetch pipeline separates literal translation from
analyst commentary. Literal translation is eager and makes a post readable in
English, Simplified Chinese, and Japanese. Commentary is generated later only
when there is bounded reader or operator demand; its separate contract is in
[`commenter.md`](commenter.md).

The normalized artifact contract is documented in
[`post-content-artifacts.md`](post-content-artifacts.md). The legacy columns on
`posts` remain compatibility projections so the previous application binary
can still read the migrated database.

## Current post-fetch translation

`translate_batch_literal` accepts at most the existing translation batch size
and returns exactly one row per input post:

| Field | Meaning |
| --- | --- |
| `tweet_id` | Exact input post identity |
| `lang_detected` | `en`, `zh-Hans`, `zh-Hant`, `ja`, `ko`, or `other` |
| `text_en` | Meaning-preserving English text |
| `text_zh_cn` | Meaning-preserving Simplified Chinese text |
| `text_ja` | Meaning-preserving Japanese text |

Every locale value is required. For the source locale, the service copies the
source text rather than asking the model to paraphrase it. The prompt forbids
commentary, added facts, and analysis.

A successful result creates one `post_translation_artifacts` parent and three
`post_translation_texts` children. The parent records the content fingerprint,
detected source language, prompt, model, provider role, state, attempts, token
usage, latency, and timestamps. A source edit or source-language correction
therefore has a different artifact identity.

`posts.text_en`, `posts.text_zh_cn`, and `posts.lang_detected` are still
updated on success. They are the minimum rollback projection. Japanese lives
in the normalized locale child; no new `posts.text_ja` column is required.

Failed attempts are stored on the artifact parent with a safe error code and
never replace the current successful artifact. Batch token usage is allocated
across the rows once, so a twenty-post request is not counted twenty times.

## Registry translation

`translate_registry_rows` remains a separate formal translation path for
lookup records such as brand names and account biographies. It does not write
post-content artifacts and does not create analyst commentary.

## Code map

| Responsibility | Location |
| --- | --- |
| Literal prompt, validation, transport | `x_monitor/translator.py` |
| Post-fetch orchestration and compatibility writes | `monitor/cycle.py` |
| Normalized artifact publication and reads | `monitor/post_artifacts.py` |
| Rich synthesis prompt and transport | `x_monitor/synthesis.py` |
| Durable synthesis demand and worker lifecycle | `monitor/post_synthesis.py` |
| Database schema | `core/models.py` |
