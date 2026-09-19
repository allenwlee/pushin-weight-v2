# Making 0731 translation and commentary requests smaller and more reliable

Status: researched proposals, not adopted runtime changes. September 16, 2026.

The owner asked how to change request shape so cloud 0731 can meet the existing quality, cost, and latency requirements. The immediate target is literal translation and rich commentary, not the selected two-call classifier architecture. A valid response alone does not establish faithful translation.

## Evidence from our complete repeat

The [raised-ceiling repeat](../analysis/2026-09-16-190600-u20-raised-ceiling-repeat.md) returned 45/45 structurally complete translations for both models. 0731 commentary improved from 40/45 to 44/45, while incumbent commentary fell from 45/45 to 42/45. 0731 still omitted the same two source paragraphs from one post in all three languages. Its longest repeat translation call took 478.120 seconds; the equivalent incumbent call took 100.511 seconds. This separates three problems: large/slow requests, invalid output packaging, and content omissions. Different changes address each problem.

The repeat source-locale fields account for 29,518 of 99,640 returned text characters (29.62%). This is a **character proxy**, not measured token, cost, or latency savings. The native field itself omitted 131 source characters on one English post. The source has 29,649 characters across all 45 declared native fields. Copying source text in code removes that unnecessary generation and makes exact source preservation deterministic. Apply this only where the language/copy contract is established; mixed-language or uncertain input must retain explicit treatment, and a source outside EN/ZH-CN/JA still needs all three translations.

## What other implementations and reports show

1. **Small groups and one target language are established translation designs.** Immersive Translate's published configuration uses text-length limits and small groups, including a four-segment setting for DeepSeek. This is evidence of an implementation pattern, not proof that four posts is optimal here. [Primary configuration](https://github.com/immersive-translate/immersive-translate/blob/main/dist/chrome/default_config.json).
2. **Plain translated text can avoid JSON generation entirely.** BabelDOC's basic translator asks for one target language, reads the returned text directly, caches it, and rate-limits requests. Its default translation temperature is zero. Its large retry allowance is not a recommendation for our bounded budget. [Primary implementation](https://github.com/funstory-ai/BabelDOC/blob/main/babeldoc/translator/translator.py).
3. **Structured-output support is endpoint-specific.** OpenRouter documents JSON Schema output and `require_parameters: true`. Our read-only live metadata check found `response_format` and `structured_outputs` on DeepInfra FP8, but advertisement is not a tested guarantee. [OpenRouter documentation](https://openrouter.ai/docs/guides/features/structured-outputs). A [Hermes issue](https://github.com/NousResearch/hermes-agent/issues/75669) reports stale capability metadata for this exact checkpoint; a [vLLM issue](https://github.com/vllm-project/vllm/issues/51467) reports a structured-output serving crash. These firsthand reports illustrate implementation differences; neither establishes the cause of our failures, and the vLLM issue is closed.
4. **JSON mode has limitations.** DeepSeek documents JSON mode, sufficient output allowance, and occasional empty-content behavior. [Official guide](https://api-docs.deepseek.com/guides/json_mode/). Our earlier classifier experiments already found that JSON modes changed behavior and did not solve completeness. Do not blindly re-enable them globally or confuse schema compliance with correct content.
5. **Segmentation, context, and formatting are separate controls.** DeepL exposes a target language, text units, context, sentence splitting, and formatting preservation. This supports treating formatting as part of the translation pipeline rather than asking one long generation to manage everything. It is not a recommendation to switch providers. [Official translation API](https://developers.deepl.com/api-reference/translate/request-translation).

## Recommended experiments, in order

### A. Reduce unnecessary generation and bound each request

- Fill the verified source-language field from immutable source text in code; ask only for the required target languages.
- Retain the three-language persisted artifact and its provenance. Do not drop JA or change audience coverage.
- Group by compatible source/target languages, and pack requests using estimated output tokens, with conservative language-specific headroom and a maximum post count. Test roughly 3,000–5,000 expected output tokens per call rather than blindly lowering the ceiling on a 26,000-token task. The suggested range is a hypothesis to calibrate, not a proven optimum.
- Isolate long or mixed-language posts. Preserve full-post context while mapping paragraph-sized segments; do not generate one call for every line.
- Limit provider concurrency initially and measure time to first token separately from generation time. A socket-idle timeout is not a wall-clock deadline. Smaller calls can reduce time to first usable result, but do not automatically reduce total serial runtime or cost.

### B. Compare two small output contracts

**Minimal structured output:** retain only required translation strings and stable request slots, using code for metadata and source-copy fields. Test a shallow schema on the exact provider. A deterministic adapter may record and discard extra fields only after validating every required field; it must reject missing text, wrong identities, or ambiguous payloads. The incumbent extra-note response is an example where this could avoid an unnecessary rejection without rewriting prose.

**Plain-text alternative:** one post, one requested target language, one plain-text response. Code already knows the post and locale and serializes the result for storage. There is no delimiter parser and the model need not escape prose as JSON. Our existing adapters parse JSON, so this needs an explicit raw-text transport path. It is a proposed controlled alternative or fallback for formatting failures, not permission to reinterpret old failures as passes. Literal translation would need two calls per ordinary EN/ZH-CN/JA source; commentary would need three calls if independently generated per locale. More calls increase input and request overhead, but do not inherently triple output tokens. Compare measured total cost and rate limits before adopting.

### C. Check completeness mechanically and retry narrowly

- Exact-copy the source locale; assert exact equality.
- For long posts, use a source segment manifest and require all expected segments to return once. Preserve whitespace/layout in code where possible. Segment presence does not prove its meaning was fully translated.
- Check URLs, handles, protected literal names, glossary terms, and normalized numeric values. Do not equate a Japanese name's uncertain Latin romanization with corruption of an explicit Latin source name.
- Retain raw provider text and failure classification so invalid JSON can be diagnosed precisely.
- Retry only failed posts/locales, under an explicit attempt and spend limit, with rate-limit backoff. Never replay an already consumed frozen experiment request or silently repeat an in-flight timed-out call. Successful artifacts remain reusable.
- A retry of the same malformed structure is less informative than the plain-text alternative; neither can guarantee semantic correctness. Do not add an unconditional LLM judge to every post.

## Cost and acceptance

The repeat's observed translation cost was $0.009265 for 0731 versus $0.056446 estimated for the incumbent, about 6.1 times cheaper before wallet fees. Eliminating native copying could improve this, but the 29.62% character fraction cannot be converted directly to dollar savings. The incumbent could benefit from the same optimization; compare equal output requirements and disclose any asymmetric baselines. Do not promise the owner's 10-times goal from token prices alone.

Start with the known omission, malformed-JSON examples, quoted text, long financial recap, mixed-language duplicate blocks, and short controls. Compare A with the small structured versus plain-text contracts, then repeat the complete frozen 45 with unchanged quality requirements. Measure accepted and faithful output, retained source segments, end-to-end latency, actual tokens, request count, retry spend, and total cost per completed post. Production language mix is broader than this deliberately balanced EN/ZH-CN/JA corpus; monthly projections require production-volume evidence.

No proposed request format, prompt, provider, retry policy, taxonomy, or database change was implemented by this research.
