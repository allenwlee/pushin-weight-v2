# Compact translation-fidelity fixes and their limits

September 17, 2026 JST. U20 continuation of the [canonical plan](../plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md). [Detailed source/output evidence](2026-09-17-075000-u20-compact-fidelity-fixes.json).

## Outcome

Exact pronunciation spellings and source line boundaries now use the existing code-based protection rather than additional requests. The final probe returned five translations: every returned translation passed marker checks and retained its source line count; both returned pronunciation guides retained the source spelling/reading pairs. This is a bounded formatting/content-preservation result, **not a translation quality pass**. English still sometimes treats a model as a fictional character, and a Chinese heading was left untranslated. Three calls were rate-limited. U20 remains open and no provider, feature flag, staging service or production setting was activated.

## The shortest useful division of work

- **Exact copying belongs in code.** Reuse the quantity placeholder machinery for explicitly formatted Latin-name → katakana-reading examples and quoted katakana alternatives on those same lines. Code restores them exactly; missing or duplicated placeholders fail validation. The guide has 34 protected spans. Ordinary Japanese prose and quotations outside this narrow format remain available to translate.
- **Line boundaries belong in code.** Reuse the existing ordered markers at nonempty-source-line granularity, within the same full-post request. Code restores the original single newlines, blank lines and CRLF separators, and rejects inserted internal line breaks. There is no call per line. This framing remains opt-in through the existing `paragraph_tracking` flag; the new identity is `literal-translation-lines-v13`. Single-line input still uses the raw protocol.
- **Meaning belongs in the prompt.** One shared instruction covers whole-post context, entity roles, pronunciation spelling, hostile tone/identity references, monetary denomination, uncertainty and numerical fidelity. It replaces redundant instructions and removes “translate every block independently.” A concrete model/topic cue and “fen is not generic cents” helped in one trial, but their success did not establish consistency.

No post-ID exception, brand/character dictionary, general-purpose language detector, automatic repair, extra inference pass or provider fallback was added. Raw prompt identity is `literal-translation-plaintext-v12`. These are general fidelity requirements tested on 0731; there is no new model-agnostic comparison or evidence that the failures occur only on 0731. Existing numerical validation remains narrow, not a general semantic verifier.

The final framed instruction prefix is approximately 10% shorter than the prior v7 prefix (1,524 versus 1,692 characters in representative requests). Line markers add source/output overhead, so this does **not** establish a token or cost reduction. No full45 throughput or cost comparison was run for the final shape.

## Three bounded experiments

All experiments used the existing frozen source corpus and pinned 0731/DeepInfra route, serial execution, no retries and a 180-second socket-idle timeout. Different prompts/shapes have separate immutable contracts and outputs.

| Experiment | Responses / attempted calls | Time | Reported inference cost | Finding |
|---|---:|---:|---:|---|
| Compact shared instruction, v8/v9 | 16/16 | 4m55s | $0.00231120 | Chinese pronunciation and one newline improved; English pronunciation, roles and currency remained problematic. |
| Concrete short cues, v10/v11 | 11/12 | 2m14s | $0.00112596* | English model role and currency improved; pronunciation still changed; one HTTP 429. |
| Protected spellings + line framing, v12/v13 | 5/8 | 53s | $0.00061890* | Returned spelling pairs and line counts preserved; meaning failures remain; three HTTP 429 responses. |

\* Usage is absent for the rate-limited requests; those costs are the reported subtotal, not a complete billing reconciliation. Total known reported inference spend is $0.00405606, excluding reviewer-agent work. Conservative request reservations were $0.09167620, $0.06155776 and $0.04678608 respectively. Failed calls were retained and were not retried.

## Findings by issue

| Issue | Evidence and disposition |
|---|---|
| Pronunciation examples | Prompt-only changes still produced Claude → Claude and translated Cursor into its meaning; one trial introduced Dali (not Dali). Final protected spans preserve the 31 primary pairs and three quoted alternatives in both returned guide translations. Surrounding prose still needs quality review. |
| Model versus character | The explicit prompt corrected the English sentence in v10/v11, but it regressed in v12/v13. The final Chinese text treats MiniMax H3 as a separate topic before Phoebe/Carlotta, with awkward punctuation. The English failure remains confirmed; no universal role-parsing fix is claimed. |
| Currency | v10/v11 rendered 6 fen in English and specified renminbi in Japanese. Both currency calls in the final run received HTTP 429, so the latest request shape has no currency output evidence. The original 6 cents wording was ambiguous, not an explicit assertion of USD. |
| Tone, slang and ambiguity | The first rewrite retained goyslop; the second Chinese output dropped it again. “chat” as an address to readers remains awkward or wrongly literal. The Charlie/audit clause still conflates a person's death with an audit ending, though the preceding killing allegation is present. No per-word substitution table was added and these are not marked resolved. |
| Line breaks | Both previously merged English cases retain all source lines in the final run (45/45 and 4/4). The other returned texts also retain source line counts. Three rate-limited outputs are unavailable, not counted as passes. |
| Untranslated prose | Final Chinese guide leaves `今さら聞けない` in Japanese. Protected spelling spans do not include this heading: it is a separate model compliance failure. The unchanged-whole-source guard cannot detect every partially untranslated phrase. |

Two refinements are deliberately not presented as universal fixes: the pronunciation matcher recognizes an anchored mapping format, not the semantic intent of every arrow; and line markers prove structural preservation, not correct relationships inside a line. A hypothetical prose prefix before a Latin → katakana mapping can be protected with the pair. Future expansion requires evidence rather than a growing collection of language exceptions.

## Verification and next boundary

90 focused tests passed, including 17 required PostgreSQL tests and zero skips. New failures were reproduced before implementation. Tests cover both real translation formats, exactly-once/collision-safe mixed placeholders, unmasked ordinary prose, pronunciation-only source copies, preserved separators, rejection of added line breaks, token accounting and the actual CycleRunner-to-artifact failure path. Ruff and diff checks passed; an independent code review found no blocking implementation defect. Semantic review is automated, source-visible development evidence, not human gold or a population accuracy estimate.

Stop prompt growth here. Keep the deterministic preservation improvements as an inactive candidate. The remaining role/idiom/prose errors require a separately scoped translation-quality decision and reliable provider access; another routine second call is not silently introduced. Do not run a full45 purchase, select the translator for staging, or close U20 based on these probes. No additional owner-review gate was created.

Evidence directories:

- `.context/u20/semantic-probe-20260917-073100/`
- `.context/u20/semantic-explicit-probe-20260917-073700/`
- `.context/u20/protected-lines-probe-20260917-074500/`

Each includes frozen requests/contracts, original responses, measurements and `source-comparison.json`. First and final runs also have independent review files. Previous full45 artifacts remain unchanged.
