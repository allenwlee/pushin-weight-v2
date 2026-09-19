# Commentary attempt L: source-only blind diagnostic review

**Packet:** `.context/model-task-20260917/review-packet-l.json`  
**Rubric:** `.context/model-task-20260917/review-rubric.md`  
**Evidence rule:** root-post source only. The packet's stored quote was not used as evidence.  
**Scope:** eight posts × English, Simplified Chinese, and Japanese commentary (24 outputs).

## Result

Nine outputs are reviewed good: every locale for posts `2100270972465008655`, `2100277491390951481`, and `2100346971144036571`. Fifteen outputs have confirmed semantic defects across five source posts. No output remains unresolved.

This eight-post diagnostic fails the rubric's zero-error diagnostic threshold. It is not a population-quality estimate.

## Error patterns

- The root post says `Bhedbhav GPT`, but every locale substituted `TaxGPT`.
- An unnamed linked platform was changed into TRON, turning tags and a hashtag into an unsupported offer-provider identity.
- The French `c'est quoi ce poulet` is impressed, colloquial disbelief at a striking offer. All locales recast it as skepticism or mockery; Chinese also made the unspecified `cts` into U.S. cents.
- A joking statement about Union Alpha wanting to be ox Alpha was recast as an unsupported separate comparison and as an objectively nonsensical wish.
- The Korean post's policy debate is about slowing AI, not the speed of regulation. It reports a 20%-to-55% change for Chinese models collectively and a separate Hy4 token total; each locale assigns the collective increase to Hy4.

## Short prompt remedy

For this commentary prompt, add: “Do not resolve URLs, tags, hashtags, abbreviations, or product-like labels into an organization, currency, capability, or identity unless the post states it. Keep statistics' population and time basis separate: never attach a collective trend to a named company/model without explicit support.”

The complete per-output record is `.context/model-task-20260917/review-l.json`.
