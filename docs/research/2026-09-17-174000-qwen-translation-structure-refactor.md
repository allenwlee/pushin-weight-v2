# Qwen translation: request-shape correction

The owner directed continued Qwen optimization after three configurations. Delivery Exception 29 records the additional bounded block. These are development-set tests, not estimates of population error.

## Configuration 4: structured source lines

Kept the pinned Alibaba Qwen route, snapshot pricing and reasoning off. Separated system instructions from JSON source data. Each source/target call now returns an array with one translated string per source line; code restores paragraph markers and separators. Generic examples explain discounts, large numerical units, idioms and evidential comparisons without supplying any test-post answer. No retry or extra LLM call was added.

All 19 requests completed and all eight posts had structurally complete translations. This fixed the framing problem but did not establish semantic success. Parent inspection found at least six defective source posts:

- Chinese promotion: Japanese includes Korean prose `없이`.
- French price praise: English/Japanese translate slang literally as chicken; Chinese adds an implied currency via 三毛/3毛 rather than preserving ambiguous cents.
- GLM speculation: Chinese drops `ox` from the name; Japanese invents `If Its` as an entity.
- Mixed Indonesian/English: Japanese turns the addressed handle into the subject, loses first-person experience and the money-saving condition.
- Union Alpha: Japanese changes who wants to resemble whom.
- Korean article: Chinese reverses who wants to get ahead of China and who rejects slowing down; Japanese changes the comparison into being ahead within China.

The tokenizer sentence remains an ambiguity needing care; it must not turn identification evidence into a new model architecture. No uncertain item is counted as correct. Independent packet M review is pending.

## Configuration 5: interpretation before translation in the same call

The next request adds a short `source_reading` field before the translated `lines`. It asks the model to identify speaker/addressee, conditions, idiomatic tone, comparisons and numerical units, then translate the original fully. The note is retained only as diagnostic evidence, never shown as translation. This tests whether the errors arise while understanding the source or while rendering it. The adapter validates every protected placeholder per line as well as complete line count. It does not repair semantic content.

Retest the same eight difficult posts to measure correction, then run a wider 24-post diagnostic even if some edge cases remain. That expansion measures whether improvements generalize and reveals new failures; it does not waive the <=1% qualification threshold or count the wider cohort as passing. Keep spend, task identity and all failures explicit.

## Configuration 5 findings and next correction

All 19 transports completed, but two source posts had missing target translations. Short-request caps were above 1,000 output tokens and responses ended normally: these were not output-limit failures. The recorded source readings themselves misinterpreted idioms and opaque model names (including expanding an unknown name into OpenAI), and sometimes treated the addressed handle as the speaker. Japanese also changed singular first-person into plural. Thus asking for a visible interpretation did not fix the underlying interpretation.

Configuration 6 keeps the structured source/output separation, enables a 4,096-token reasoning budget with matching output headroom, and uses temperature 0. The saved Alibaba endpoint explicitly advertises temperature; its omission earlier was a profile choice, not a provider limitation. A small, source-relevant language note explains that contemporary French `poulet` may express praise for impressive content/products, with a distinct literal food meaning, and that ambiguous cent denominations must not become USD or RMB. This is an explicit development-derived glossary, so the old French example is no longer an unseen test. A wider diagnostic will assess generalization. No exact post answer or reference labels are supplied.

## Commentary configuration 3

Independent review K found 5/8 defective sources after the shorter grounding prompt: inconsistent discount rendering, literal/negative French slang plus invented USD, unsupported replacement relationship, the tokenizer-evidence/architecture confusion, and broadening platform adoption to market share. Configuration 3 separates system rules and source data, requires English explanation first with faithful Chinese/Japanese versions of the same claims, uses bounded 4,096-token reasoning and temperature 0, and explicitly preserves attribution, evidence, statistics scope and uncertainty. It reuses the same small development-derived language note. This still uses one commentary call per post, with no reviewer or repair call at runtime.
