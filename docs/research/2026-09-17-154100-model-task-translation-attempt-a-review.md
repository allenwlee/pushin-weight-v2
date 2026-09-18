# Translation attempt A: blind semantic review

**Review date:** 2026-09-17  
**Scope:** Eight supplied posts; all requested English, Simplified Chinese, and Japanese translation outputs.  
**Method:** Source-grounded semantic review using the frozen translation rubric. Candidate identity and other candidate outputs were not inspected.

This is an automated diagnostic of this supplied packet. It does not estimate population accuracy and does not qualify a model for production use.

## Result

All eight source posts were assessed. There were 24 required locale outputs, of which 23 were present and one was missing. Eighteen present outputs were semantically acceptable. Five findings affected four source posts, so the source-post error count is 4 of 8 (50%). The packet cannot pass the rubric’s zero-error diagnostic threshold.

| Locale | Required | Findings | Notes |
| --- | ---: | ---: | --- |
| English | 8 | 1 minor | An informal source interjection was carried over untranslated. |
| Simplified Chinese | 8 | 2 material | One output was copied from the foreign-language source; another narrowed the subject of a metric. |
| Japanese | 8 | 2 material | One discount amount changed direction; one required result was absent. |

## Diagnosis

The errors fall into three reliability gaps.

First, numeric commercial language needs explicit semantic handling. A discount expression can describe either the final price fraction or the percentage removed. A target-language phrase with a superficially similar number can reverse that relationship.

Second, translating claims with group nouns needs subject preservation. When a source attributes a metric to a broad class, the output must not narrow it to one named member merely because that member appears elsewhere in the text.

Third, output validation must distinguish a successful-looking response from a complete locale set. A copied foreign-language source is not a target translation, and a null target is a coverage failure even when a failure flag is supplied. Informal markers should also be translated when their meaning is clear; they carry stance and tone.

## Minimal generalizable remedies

- In the translation prompt, require preservation of every numeric relationship in normalized terms: state both the final-price fraction and the percent reduction when the source uses a discount idiom.
- Add a post-translation claim check for each sentence containing a percentage, ratio, amount, named entity, or collective subject. Verify the output retains the same subject scope and comparison direction.
- Enforce output shape before accepting a result: each requested locale must be a non-empty string in the target language, except where an explicitly supported protocol marker is returned and handled as a failed job.
- Add a lightweight source-language-versus-target-language check to catch near-exact foreign-language copies in non-native targets. Exempt URLs, handles, product names, and intentionally preserved opaque terms.
- Preserve informal interjections through a target-language equivalent when their meaning is clear; do not treat them as proper names by default.

## Limits

The review evaluates only the supplied outputs against their supplied source text and stored context. It does not fact-check authors’ statements or infer missing external context. Any ambiguous cultural wording was not treated as an error unless the observed output defect was independently clear.
