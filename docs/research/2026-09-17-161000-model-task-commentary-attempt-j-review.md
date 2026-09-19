# Commentary attempt J: blind diagnostic review

**Packet:** `.context/model-task-20260917/review-packet-j.json`  
**Rubric:** `.context/model-task-20260917/review-rubric.md`  
**Scope:** eight supplied posts × English, Simplified Chinese, and Japanese commentary (24 outputs). This is a diagnostic review, not a population-quality estimate.

## Result

Six outputs are reviewed good: all three locales for posts `2100249221484220856` and `2100346971144036571`. Eighteen outputs have confirmed semantic defects across six source posts. There are no unresolved outputs in this packet.

The supplied eight-post diagnostic therefore does not meet the rubric's zero-error diagnostic threshold. It cannot establish a population error rate.

## Confirmed error patterns

- A stored quote substituted `TaxGPT` for source text `Bhedbhav GPT`; commentary must keep the root post and stored quote distinct.
- A French colloquial reaction (`c'est quoi ce poulet`) means amazement at the offer, not doubt about its value. The Chinese commentary additionally names U.S. cents even though `cts` does not identify a currency. All locales turned a single price claim into a market-wide assertion that LLM costs are rapidly falling.
- Two terse conversational posts received unsupported identity/context: unnamed things were called models/features and AI releases; an opaque phrase was classified as a subscription service and used to define a subscriber segment; and `ox Alpha` was given an unsupported “brute strength” meaning.
- The Korean post's specific framing—Trump rejects slowing AI because the U.S. must get ahead of China—was flattened into a generic policy debate. Its source says price, latency, and tool integration outrank nationality as selection criteria; it does not say they outrank model performance.

## Durable prompt remedy

Add a short commentary-stage instruction: “Treat handles, product-like names, URLs, and opaque phrases as labels unless the supplied post or stored context defines them. Keep a stored quote separate from the root post. Do not generalize one company or product claim into an industry trend, and preserve named actors, countries, and comparison axes.”

The complete output-by-output record, exact spans, severities, and corrections are in `.context/model-task-20260917/review-j.json`.
