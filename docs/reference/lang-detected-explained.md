# How post language fields work

The Django `posts` table stores two distinct language facts:

- `lang` is the source-provider language metadata received with the post.
- `lang_detected` is the translator stage's canonical language family used for
  translation persistence and locale behavior.

The production translator does not copy `lang` into `lang_detected`. The model
detects language from the source text, then the application validates and
normalizes the result before persistence.

## Canonical values

`lang_detected` has six application-level values:

| Value | Meaning |
| --- | --- |
| `en` | English family |
| `zh-Hans` | Simplified Chinese family |
| `zh-Hant` | Traditional Chinese family |
| `ja` | Japanese family |
| `ko` | Korean family |
| `other` | Any other valid language family |

`normalize_lang_detected` in `x_monitor/translator.py` handles common aliases
and regional/script variants. Examples:

- `EN`, `eng`, and `en-US` become `en`.
- `zh`, `zh-CN`, and `zh_Hans` become `zh-Hans`.
- `zh-TW` and `zh-Hant` become `zh-Hant`.
- registered non-target ISO 639-1 language tags, optionally with conservative
  region/script subtags, such as `fr`, `ar`, `de`, `es-MX`, and `pt_BR` become
  `other`.
- blank values and free-form labels such as `esperanto` are invalid.

Undetermined, private-use, reserved, and merely tag-shaped values such as
`und`, `qaa`, `xx`, and `zz` remain invalid and take the bounded repair path.

The `other` normalization is deliberate. The model often returns a more
precise valid source language even when prompted to use the application's
coarser bucket. Rejecting that precision caused valid French, Arabic, and
German posts to spend a repair call and remain pending.

## Translation and repair flow

`translate_batch_pragmatics` asks for one result per input post containing:

- `lang_detected`;
- English and Simplified Chinese renderings;
- distinct English and Simplified Chinese analyst commentary;
- optional cultural annotation.

After parsing, the application normalizes language and validates every output
needed for persistence. Incomplete rows receive at most one targeted full-row
repair request. A row that remains incomplete is returned as
`translation_failed` and stays retryable in `PostEnrichmentState`; it is never
marked successful because a partial field happened to exist.

## Persistence invariants

`CycleRunner._run_post_fetch` validates the effective values after applying
source-serving behavior:

- an English source persists its source text in `text_en`;
- a Simplified Chinese source persists its source text in `text_zh_cn`;
- other languages require both generated translations;
- every non-empty post requires distinct `commentary_en` and
  `commentary_zh_cn`.

Only rows satisfying those invariants are marked translation-succeeded. Recent
legacy false successes are reopened within the configured enrichment age
window; historical rows outside that window are not resurrected automatically.

## Downstream use

The feed uses the persisted source, translation, and commentary layers.
`lang_detected` also determines source-serving noop behavior and supports
language-family filtering. It is an application control value, not a claim of
independent language-detection ground truth.

The provider `lang` column remains useful diagnostic evidence, but it is not a
fill source for `lang_detected`.
